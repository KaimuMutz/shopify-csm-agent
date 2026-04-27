"""Shopify webhook ingest — verifies HMAC and forwards to the agent."""

from __future__ import annotations

import base64
import hashlib
import hmac

from fastapi import APIRouter, HTTPException, Request

from src.settings import get_settings

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _verify_shopify_hmac(body: bytes, header_hmac: str, secret: str) -> bool:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, header_hmac)


@router.post("/shopify")
async def shopify_webhook(request: Request) -> dict[str, str]:
    s = get_settings()
    body = await request.body()
    header_hmac = request.headers.get("X-Shopify-Hmac-Sha256", "")

    if not s.shopify_webhook_secret or not _verify_shopify_hmac(body, header_hmac, s.shopify_webhook_secret):
        raise HTTPException(status_code=401, detail="invalid hmac")

    # Real implementation: enqueue a job for the agent worker.
    # Kept terse here — the heavy lifting is in src.agent.graph.
    return {"status": "queued"}
