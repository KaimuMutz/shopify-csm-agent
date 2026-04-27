"""Thin wrapper around the Shopify Admin REST + GraphQL API.

Only the calls the agent currently uses are implemented. The wrapper is
deliberately small — adding a new endpoint is one method, one fixture, one
test.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential


@dataclass(frozen=True)
class ShopifyCredentials:
    store: str  # e.g. "your-store.myshopify.com"
    admin_token: str  # shpat_xxx
    api_version: str = "2025-01"

    @property
    def base_url(self) -> str:
        return f"https://{self.store}/admin/api/{self.api_version}"

    @property
    def headers(self) -> dict[str, str]:
        return {
            "X-Shopify-Access-Token": self.admin_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }


class ShopifyClient:
    """Minimal Shopify Admin API client used by agent tools."""

    def __init__(self, creds: ShopifyCredentials, *, timeout: float = 15.0) -> None:
        self._creds = creds
        self._client = httpx.AsyncClient(
            base_url=creds.base_url,
            headers=creds.headers,
            timeout=timeout,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    # ----------- internal helpers -----------

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=0.5, max=4))
    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = await self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    # ----------- agent-facing tool methods -----------

    async def find_order_by_name(self, order_name: str) -> dict[str, Any] | None:
        """Look up an order by its human name (e.g. '#1042').

        Returns the first match or None.
        """
        name = order_name if order_name.startswith("#") else f"#{order_name}"
        data = await self._get(
            "/orders.json",
            params={"name": name, "status": "any", "limit": 1},
        )
        orders = data.get("orders", [])
        return orders[0] if orders else None

    async def list_orders_for_email(self, email: str, limit: int = 5) -> list[dict[str, Any]]:
        """Recent orders for a customer email — used to disambiguate when no
        order number is supplied."""
        data = await self._get(
            "/orders.json",
            params={"email": email, "status": "any", "limit": limit, "order": "created_at desc"},
        )
        return data.get("orders", [])

    async def get_product(self, product_id: int) -> dict[str, Any] | None:
        try:
            data = await self._get(f"/products/{product_id}.json")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise
        return data.get("product")

    async def search_products(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        data = await self._get("/products.json", params={"title": query, "limit": limit})
        return data.get("products", [])

    async def find_customer_by_email(self, email: str) -> dict[str, Any] | None:
        data = await self._get("/customers/search.json", params={"query": f"email:{email}"})
        customers = data.get("customers", [])
        return customers[0] if customers else None
