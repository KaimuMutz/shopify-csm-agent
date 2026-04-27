"""LangGraph state machine for the CSM agent.

Nodes:
    classify  -> gather  -> draft  -> self_grade  -> decide
                                                     ├─ auto_send
                                                     └─ escalate

Each node is small, side-effect-isolated, and unit-testable in `tests/`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph

from src.agent.prompts import CLASSIFY_SYSTEM, DRAFT_SYSTEM, SELF_GRADE_SYSTEM
from src.tools.shopify import ShopifyClient
from src.tools.slack import SlackTool


Intent = Literal[
    "order_status",
    "refund_request",
    "return_request",
    "product_question",
    "availability",
    "shipping_change",
    "discount_enquiry",
    "general",
    "unknown",
]


class AgentState(TypedDict, total=False):
    conversation_id: str
    customer_email: str
    message: str
    intent: Intent
    intent_confidence: float
    context: dict[str, Any]
    context_summary: str
    draft: str
    self_grade: dict[str, Any]
    decision: Literal["auto_send", "escalate"]
    final_reply: str | None


@dataclass
class GraphDeps:
    llm_complete: Any  # async (system: str, user: str) -> str
    shopify: ShopifyClient
    slack: SlackTool
    confidence_threshold: float = 0.78
    escalate_refunds: bool = True
    escalate_address_changes: bool = True
    metrics: dict[str, int] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Nodes                                                                       #
# --------------------------------------------------------------------------- #


async def classify(state: AgentState, deps: GraphDeps) -> AgentState:
    raw = await deps.llm_complete(CLASSIFY_SYSTEM, state["message"])
    parsed = json.loads(raw)
    return {
        **state,
        "intent": parsed["intent"],
        "intent_confidence": float(parsed.get("confidence", 0.0)),
        "context_summary": parsed.get("summary", ""),
    }


async def gather(state: AgentState, deps: GraphDeps) -> AgentState:
    """Pull the minimum context needed to answer this intent."""
    intent = state["intent"]
    email = state["customer_email"]
    ctx: dict[str, Any] = {}

    if intent in {"order_status", "refund_request", "return_request", "shipping_change"}:
        # naive order-name extraction; the real version uses a regex helper
        msg = state["message"]
        token = next((w for w in msg.split() if w.startswith("#")), None)
        if token:
            order = await deps.shopify.find_order_by_name(token)
            if order:
                ctx["order"] = order
        if "order" not in ctx and email:
            recent = await deps.shopify.list_orders_for_email(email, limit=3)
            if recent:
                ctx["recent_orders"] = recent

    elif intent in {"product_question", "availability"}:
        # let the draft step rely on the message + product search
        products = await deps.shopify.search_products(_extract_product_query(state["message"]))
        if products:
            ctx["products"] = products[:3]

    customer = await deps.shopify.find_customer_by_email(email) if email else None
    if customer:
        ctx["customer"] = {
            "first_name": customer.get("first_name"),
            "orders_count": customer.get("orders_count"),
            "total_spent": customer.get("total_spent"),
        }

    summary = _summarise_context(intent, ctx) or state.get("context_summary", "")
    return {**state, "context": ctx, "context_summary": summary}


async def draft(state: AgentState, deps: GraphDeps) -> AgentState:
    user_block = (
        f"Customer message:\n{state['message']}\n\n"
        f"Intent: {state['intent']}\n\n"
        f"Gathered context:\n{json.dumps(state.get('context', {}), default=str)[:4000]}"
    )
    reply = await deps.llm_complete(DRAFT_SYSTEM, user_block)
    return {**state, "draft": reply.strip()}


async def self_grade(state: AgentState, deps: GraphDeps) -> AgentState:
    user_block = (
        f"Original message:\n{state['message']}\n\n"
        f"Context:\n{json.dumps(state.get('context', {}), default=str)[:4000]}\n\n"
        f"Draft reply:\n{state['draft']}"
    )
    raw = await deps.llm_complete(SELF_GRADE_SYSTEM, user_block)
    return {**state, "self_grade": json.loads(raw)}


async def decide(state: AgentState, deps: GraphDeps) -> AgentState:
    grade = state.get("self_grade", {})
    intent = state["intent"]

    risky_intent = (
        (intent == "refund_request" and deps.escalate_refunds)
        or (intent == "shipping_change" and deps.escalate_address_changes)
    )
    grounded = grade.get("grounded") is True
    score = float(grade.get("score", 0.0))
    risk = grade.get("risk", "high")

    auto_ok = (
        not risky_intent
        and grounded
        and risk == "low"
        and score >= deps.confidence_threshold
        and state.get("intent_confidence", 0.0) >= 0.6
    )

    return {**state, "decision": "auto_send" if auto_ok else "escalate"}


async def auto_send(state: AgentState, deps: GraphDeps) -> AgentState:
    # In production this would call the customer-channel sender (email,
    # Shopify chat, etc). Here we just record the decision.
    deps.metrics["auto_sent"] = deps.metrics.get("auto_sent", 0) + 1
    return {**state, "final_reply": state["draft"]}


async def escalate(state: AgentState, deps: GraphDeps) -> AgentState:
    await deps.slack.post_review(
        conversation_id=state["conversation_id"],
        customer_email=state["customer_email"],
        intent=state["intent"],
        confidence=float(state.get("self_grade", {}).get("score", 0.0)),
        original_message=state["message"],
        draft_reply=state["draft"],
        context_summary=state.get("context_summary", ""),
    )
    deps.metrics["escalated"] = deps.metrics.get("escalated", 0) + 1
    return {**state, "final_reply": None}


# --------------------------------------------------------------------------- #
# Graph                                                                       #
# --------------------------------------------------------------------------- #


def build_graph(deps: GraphDeps):
    g = StateGraph(AgentState)

    g.add_node("classify", lambda s: classify(s, deps))
    g.add_node("gather", lambda s: gather(s, deps))
    g.add_node("draft", lambda s: draft(s, deps))
    g.add_node("self_grade", lambda s: self_grade(s, deps))
    g.add_node("decide", lambda s: decide(s, deps))
    g.add_node("auto_send", lambda s: auto_send(s, deps))
    g.add_node("escalate", lambda s: escalate(s, deps))

    g.set_entry_point("classify")
    g.add_edge("classify", "gather")
    g.add_edge("gather", "draft")
    g.add_edge("draft", "self_grade")
    g.add_edge("self_grade", "decide")
    g.add_conditional_edges(
        "decide",
        lambda s: s["decision"],
        {"auto_send": "auto_send", "escalate": "escalate"},
    )
    g.add_edge("auto_send", END)
    g.add_edge("escalate", END)

    return g.compile()


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _extract_product_query(message: str) -> str:
    # Keep it simple — the LLM-side draft step does the heavy lifting.
    return " ".join(w for w in message.split() if w.isalpha())[:80] or message[:80]


def _summarise_context(intent: str, ctx: dict[str, Any]) -> str:
    if "order" in ctx:
        o = ctx["order"]
        return (
            f"Order {o.get('name')} — status {o.get('financial_status')}/"
            f"{o.get('fulfillment_status') or 'unfulfilled'}, "
            f"placed {o.get('created_at', '')[:10]}."
        )
    if "recent_orders" in ctx:
        return f"{len(ctx['recent_orders'])} recent orders found for the customer."
    if "products" in ctx:
        names = ", ".join(p.get("title", "") for p in ctx["products"])
        return f"Matched products: {names}."
    return ""
