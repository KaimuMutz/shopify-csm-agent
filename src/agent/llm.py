"""Thin LLM-provider wrapper.

Keeps the rest of the codebase free of provider-specific imports so we can
swap Anthropic for OpenAI or a self-hosted model without touching the agent
graph.
"""

from __future__ import annotations

from typing import Protocol

from anthropic import AsyncAnthropic


class LLMComplete(Protocol):
    async def __call__(self, system: str, user: str) -> str: ...


class AnthropicLLM:
    def __init__(self, api_key: str, model: str, temperature: float = 0.2) -> None:
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model
        self._temperature = temperature

    async def __call__(self, system: str, user: str) -> str:
        msg = await self._client.messages.create(
            model=self._model,
            system=system,
            temperature=self._temperature,
            max_tokens=1024,
            messages=[{"role": "user", "content": user}],
        )
        # Concatenate text blocks; ignore tool_use blocks (not used here).
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
