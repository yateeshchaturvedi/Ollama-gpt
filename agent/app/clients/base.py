"""Abstract LLM client interface.

All LLM provider implementations (Gemini, OpenAI, Claude, …) must
implement this interface. The agent runtime only talks to this interface
— swapping providers is a single env-var change.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator


class BaseLLMClient(ABC):
    """Protocol-agnostic interface for an LLM backend.

    Methods
    -------
    generate(messages, tools)
        Blocking single-turn call. Returns the full response as a string
        OR a dict when the model has chosen to call a tool.

    stream(messages, tools)
        Async generator that yields text chunks as they arrive.
        Used for real-time WebSocket streaming to the frontend.

    parse_tool_call(response)
        Extract a structured tool-call dict from a provider-native response
        object.  Returns None if the response is a text reply (not a tool
        call).
    """

    @abstractmethod
    def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[Any] | None = None,
    ) -> str | dict[str, Any]:
        """Return the model's response.

        If the model decides to call a tool, return:
            {"type": "tool_call", "tool": <name>, "args": {…}}
        Otherwise return the response text as a plain string.
        """
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[Any] | None = None,
    ) -> AsyncIterator[str]:
        """Yield text chunks as they arrive from the model.

        Yields raw text strings (not JSON).
        """
        ...

    @abstractmethod
    def parse_tool_call(self, response: Any) -> dict[str, Any] | None:
        """Extract a tool-call dict from a provider-native response object.

        Returns None when the response is a plain text reply.

        The returned dict always has this shape:
            {"type": "tool_call", "tool": <str>, "args": <dict>}
        """
        ...
