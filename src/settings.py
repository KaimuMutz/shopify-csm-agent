"""Centralised pydantic settings — values loaded from environment or .env file."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    anthropic_api_key: str = Field(..., alias="ANTHROPIC_API_KEY")
    llm_model: str = Field("claude-sonnet-4-6", alias="LLM_MODEL")
    llm_temperature: float = Field(0.2, alias="LLM_TEMPERATURE")

    # Shopify (default client; per-client values override at runtime)
    shopify_store: str = Field("", alias="SHOPIFY_STORE")
    shopify_admin_token: str = Field("", alias="SHOPIFY_ADMIN_TOKEN")
    shopify_api_version: str = Field("2025-01", alias="SHOPIFY_API_VERSION")
    shopify_webhook_secret: str = Field("", alias="SHOPIFY_WEBHOOK_SECRET")

    # Slack
    slack_bot_token: str = Field("", alias="SLACK_BOT_TOKEN")
    slack_signing_secret: str = Field("", alias="SLACK_SIGNING_SECRET")
    slack_review_channel: str = Field("#csm-review", alias="SLACK_REVIEW_CHANNEL")

    # Storage
    database_url: str = Field("sqlite:///./data/csm.db", alias="DATABASE_URL")
    redis_url: str = Field("redis://localhost:6379/0", alias="REDIS_URL")

    # Server
    host: str = Field("0.0.0.0", alias="HOST")
    port: int = Field(8000, alias="PORT")
    log_level: str = Field("info", alias="LOG_LEVEL")

    # Policy
    default_confidence_threshold: float = Field(0.78, alias="DEFAULT_CONFIDENCE_THRESHOLD")
    daily_token_budget_usd: float = Field(5.0, alias="DAILY_TOKEN_BUDGET_USD")
    escalate_refunds: bool = Field(True, alias="ESCALATE_REFUNDS")
    escalate_address_changes: bool = Field(True, alias="ESCALATE_ADDRESS_CHANGES")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
