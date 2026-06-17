"""Ollama compatibility shim implementing BaseLLMClient.

Wraps the existing call_ollama() function so the legacy Ollama backend
continues working via the same interface as Gemini/OpenAI/Claude.
Active when LLM_PROVIDER=ollama (the current default).

This shim will be removed once Gemini is fully validated in production.
"""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from app.clients.base import BaseLLMClient
from app.clients.ollama import call_ollama
from app.config import settings
from app.protocol import parse_action
from app.tooling import TOOL_REGISTRY


class OllamaLLMClient(BaseLLMClient):
    """Wraps the old call_ollama() function as a BaseLLMClient."""

    def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[Any] | None = None,
    ) -> str | dict[str, Any]:
        """Blocking Ollama call; returns parsed action dict or text."""
        from app.protocol import tool_schema_text
        from app.prompts import load_system_prompt

        lines = [load_system_prompt(), "", tool_schema_text(), ""]
        for msg in messages[-settings.max_history:]:
            role = msg["role"].upper()
            lines.append(f"{role}: {msg['content']}")
        lines.append("ASSISTANT:")
        prompt = "\n".join(lines)

        raw = call_ollama(prompt, settings.ollama_model)
        action = parse_action(raw, set(TOOL_REGISTRY.keys()))
        return action  # already a dict with type/tool/args or type/final

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[Any] | None = None,
    ) -> AsyncIterator[str]:
        """Ollama doesn't support streaming in this shim — returns full response."""
        result = self.generate(messages, tools)
        if isinstance(result, dict) and result.get("type") == "final":
            yield result.get("content", "")
        elif isinstance(result, str):
            yield result

    def parse_tool_call(self, response: Any) -> dict[str, Any] | None:
        """Not used — generate() returns parsed dicts directly."""
        return None
