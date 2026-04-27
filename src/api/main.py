"""FastAPI entrypoint."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr, Field

from src.agent.graph import GraphDeps, build_graph
from src.agent.llm import AnthropicLLM
from src.settings import get_settings
from src.tools.shopify import ShopifyClient, ShopifyCredentials
from src.tools.slack import SlackTool

log = structlog.get_logger()


class IncomingMessage(BaseModel):
    customer_email: EmailStr
    body: str = Field(..., min_length=1, max_length=4000)


class AgentRunResult(BaseModel):
    conversation_id: str
    intent: str
    decision: str
    auto_reply: str | None


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    s = get_settings()
    shopify = ShopifyClient(
        ShopifyCredentials(
            store=s.shopify_store,
            admin_token=s.shopify_admin_token,
            api_version=s.shopify_api_version,
        )
    )
    slack = SlackTool(s.slack_bot_token, s.slack_review_channel)
    llm = AnthropicLLM(s.anthropic_api_key, s.llm_model, s.llm_temperature)

    app.state.deps = GraphDeps(
        llm_complete=llm,
        shopify=shopify,
        slack=slack,
        confidence_threshold=s.default_confidence_threshold,
        escalate_refunds=s.escalate_refunds,
        escalate_address_changes=s.escalate_address_changes,
    )
    app.state.graph = build_graph(app.state.deps)

    yield

    await shopify.aclose()


app = FastAPI(title="Shopify CSM Agent", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/messages", response_model=AgentRunResult)
async def ingest_message(msg: IncomingMessage) -> AgentRunResult:
    conversation_id = uuid.uuid4().hex
    log.info("message.received", conversation_id=conversation_id, email=msg.customer_email)

    try:
        result = await app.state.graph.ainvoke(
            {
                "conversation_id": conversation_id,
                "customer_email": msg.customer_email,
                "message": msg.body,
            }
        )
    except Exception as exc:  # pragma: no cover — defensive
        log.error("agent.failed", conversation_id=conversation_id, error=str(exc))
        raise HTTPException(status_code=500, detail="agent failed") from exc

    return AgentRunResult(
        conversation_id=conversation_id,
        intent=result.get("intent", "unknown"),
        decision=result.get("decision", "escalate"),
        auto_reply=result.get("final_reply"),
    )
