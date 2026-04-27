"""Tests for the agent graph that don't hit any external API."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.agent.graph import GraphDeps, build_graph


class FakeShopify:
    async def find_order_by_name(self, name: str) -> dict[str, Any] | None:
        if name in {"#1042", "1042"}:
            return {
                "name": "#1042",
                "financial_status": "paid",
                "fulfillment_status": "fulfilled",
                "created_at": "2026-04-20T08:14:00Z",
            }
        return None

    async def list_orders_for_email(self, email: str, limit: int = 5):
        return []

    async def search_products(self, query: str, limit: int = 5):
        return []

    async def find_customer_by_email(self, email: str):
        return {"first_name": "Sam", "orders_count": 3, "total_spent": "212.30"}


class FakeSlack:
    def __init__(self) -> None:
        self.posted: list[dict[str, Any]] = []

    async def post_review(self, **kwargs):
        self.posted.append(kwargs)
        return "1700000000.000100"


def fake_llm(responses: list[str]):
    """Return an async callable that yields each response in order."""

    iterator = iter(responses)

    async def _call(system: str, user: str) -> str:  # noqa: ARG001
        return next(iterator)

    return _call


@pytest.mark.asyncio
async def test_order_status_high_confidence_auto_sends():
    slack = FakeSlack()
    deps = GraphDeps(
        llm_complete=fake_llm(
            [
                json.dumps({"intent": "order_status", "confidence": 0.95, "summary": "where is order"}),
                "Hi Sam, your order #1042 was paid and fulfilled on 2026-04-20.",
                json.dumps({"grounded": True, "tone_ok": True, "risk": "low", "issues": [], "score": 0.92}),
            ]
        ),
        shopify=FakeShopify(),  # type: ignore[arg-type]
        slack=slack,  # type: ignore[arg-type]
        confidence_threshold=0.78,
    )
    graph = build_graph(deps)

    state = await graph.ainvoke(
        {
            "conversation_id": "c1",
            "customer_email": "sam@example.com",
            "message": "Hey, where is order #1042?",
        }
    )

    assert state["intent"] == "order_status"
    assert state["decision"] == "auto_send"
    assert state["final_reply"].startswith("Hi Sam")
    assert slack.posted == []


@pytest.mark.asyncio
async def test_refund_request_always_escalates():
    slack = FakeSlack()
    deps = GraphDeps(
        llm_complete=fake_llm(
            [
                json.dumps({"intent": "refund_request", "confidence": 0.95, "summary": "wants refund"}),
                "I've noted your refund request and an operator will confirm shortly.",
                json.dumps({"grounded": True, "tone_ok": True, "risk": "low", "issues": [], "score": 0.95}),
            ]
        ),
        shopify=FakeShopify(),  # type: ignore[arg-type]
        slack=slack,  # type: ignore[arg-type]
        confidence_threshold=0.78,
        escalate_refunds=True,
    )
    graph = build_graph(deps)

    state = await graph.ainvoke(
        {
            "conversation_id": "c2",
            "customer_email": "sam@example.com",
            "message": "I want a refund on order #1042",
        }
    )

    assert state["decision"] == "escalate"
    assert state["final_reply"] is None
    assert len(slack.posted) == 1


@pytest.mark.asyncio
async def test_low_self_grade_escalates():
    slack = FakeSlack()
    deps = GraphDeps(
        llm_complete=fake_llm(
            [
                json.dumps({"intent": "order_status", "confidence": 0.9, "summary": "order"}),
                "Some draft reply.",
                json.dumps({"grounded": False, "tone_ok": True, "risk": "low", "issues": ["x"], "score": 0.4}),
            ]
        ),
        shopify=FakeShopify(),  # type: ignore[arg-type]
        slack=slack,  # type: ignore[arg-type]
        confidence_threshold=0.78,
    )
    graph = build_graph(deps)

    state = await graph.ainvoke(
        {"conversation_id": "c3", "customer_email": "sam@example.com", "message": "Hi"}
    )

    assert state["decision"] == "escalate"
    assert len(slack.posted) == 1
