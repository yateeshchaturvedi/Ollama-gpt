"""Anthropic Claude LLM client — STUB (not yet active).

This module is ready to implement. To activate:
1. pip install anthropic
2. Set LLM_PROVIDER=anthropic and ANTHROPIC_API_KEY=sk-ant-... in your .env
3. Uncomment the implementation below and fill in the SDK calls.

The interface is identical to GeminiLLMClient — no other code needs to change.
"""
from __future__ import annotations

from typing import Any, AsyncIterator

from app.clients.base import BaseLLMClient


class AnthropicLLMClient(BaseLLMClient):
    """Anthropic Claude client (stub — activate when needed).

    Implementation notes for future:
    - Use `anthropic.Anthropic()` for sync calls (generate)
    - Use `anthropic.AsyncAnthropic()` for async streaming (stream)
    - Tool calls come via `response.content` blocks of type `tool_use`
    - Messages format: [{"role": "user"|"assistant", "content": ...}]
      (Claude doesn't support system messages in the messages array —
       pass system prompt separately via `system=` parameter)
    - Tool schema: [{"name": ..., "description": ..., "input_schema": {...}}]
    """

    def __init__(self) -> None:
        raise NotImplementedError(
            "Anthropic Claude provider is not yet implemented. "
            "To use Claude: uncomment the implementation in app/clients/anthropic_client.py, "
            "set LLM_PROVIDER=anthropic, and add ANTHROPIC_API_KEY to your .env file."
        )

    def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[Any] | None = None,
    ) -> str | dict[str, Any]:
        raise NotImplementedError

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[Any] | None = None,
    ) -> AsyncIterator[str]:
        raise NotImplementedError

    def parse_tool_call(self, response: Any) -> dict[str, Any] | None:
        raise NotImplementedError
