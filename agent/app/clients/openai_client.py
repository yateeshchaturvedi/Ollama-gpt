"""OpenAI LLM client — STUB (not yet active).

This module is ready to implement. To activate:
1. pip install openai
2. Set LLM_PROVIDER=openai and OPENAI_API_KEY=sk-... in your .env
3. Uncomment the implementation below and fill in the SDK calls.

The interface is identical to GeminiLLMClient — no other code needs to change.
"""
from __future__ import annotations

from typing import Any, AsyncIterator

from app.clients.base import BaseLLMClient


class OpenAILLMClient(BaseLLMClient):
    """OpenAI GPT client (stub — activate when needed).

    Implementation notes for future:
    - Use `openai.OpenAI()` for sync calls (generate)
    - Use `openai.AsyncOpenAI()` for async streaming (stream)
    - Tool calls come via `response.choices[0].message.tool_calls`
    - Messages format: [{"role": "user"|"assistant"|"system"|"tool", "content": ...}]
    - Tool schema format: [{"type": "function", "function": {"name": ..., "parameters": ...}}]
    """

    def __init__(self) -> None:
        raise NotImplementedError(
            "OpenAI provider is not yet implemented. "
            "To use OpenAI: uncomment the implementation in app/clients/openai_client.py, "
            "set LLM_PROVIDER=openai, and add OPENAI_API_KEY to your .env file."
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
