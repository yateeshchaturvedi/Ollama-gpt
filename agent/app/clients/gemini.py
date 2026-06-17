import json
import asyncio
import logging
import time
from typing import Any, AsyncIterator

import google.generativeai as genai
from google.api_core import exceptions as google_exceptions

from app.clients.base import BaseLLMClient
from app.config import settings
from app.prompts import load_system_prompt

# ── Retry config ─────────────────────────────────────────────────────────────

_RETRY_EXCEPTIONS = (
    google_exceptions.ResourceExhausted,  # 429
    google_exceptions.ServiceUnavailable,  # 503
    google_exceptions.InternalServerError,  # 500
)
_MAX_RETRIES = 4
_BACKOFF_BASE = 1.5  # seconds; doubles each retry


# ── Prompt for CI/CD failure analysis ────────────────────────────────────────

_FAILURE_ANALYSIS_SYSTEM = (
    "You are a senior DevOps engineer and CI/CD expert. "
    "Your job is to analyze failure logs from CI/CD pipelines and provide "
    "clear, actionable diagnoses and fixes.\n\n"
    "Structure every response exactly as:\n"
    "## Root Cause\n"
    "<concise explanation of what failed and why>\n\n"
    "## Affected Files / Services\n"
    "<specific files, configs, services involved>\n\n"
    "## Step-by-Step Fix\n"
    "<numbered, exact commands or code changes>\n\n"
    "## Prevention\n"
    "<how to stop this happening again>\n"
    "Be direct and precise. Do NOT pad your response."
)

_FAILURE_ANALYSIS_USER_TEMPLATE = """\
Platform: {platform}
Repository: {repo}
Job / Pipeline: {job}
Triggered by: {trigger}

--- FAILURE LOG START ---
{log}
--- FAILURE LOG END ---

Analyze this failure and provide a structured diagnosis."""


class GeminiLLMClient(BaseLLMClient):
    """Google Gemini client with native function calling."""

    def __init__(self, api_key: str | None = None, model_name: str | None = None) -> None:
        key = api_key or settings.google_api_key
        if not key:
            raise RuntimeError(
                "GOOGLE_API_KEY is not set. "
                "Get a free key at https://aistudio.google.com and add it to your .env file."
            )
        genai.configure(api_key=key)
        self._model_name = model_name or settings.google_model
        logging.info("GeminiLLMClient initialised with model=%s", self._model_name)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _build_model(
        self,
        tools: list[Any] | None = None,
        system_instruction: str | None = None,
    ) -> genai.GenerativeModel:
        kwargs: dict[str, Any] = {"model_name": self._model_name}
        if tools:
            kwargs["tools"] = tools
        if system_instruction:
            kwargs["system_instruction"] = system_instruction
        return genai.GenerativeModel(**kwargs)

    def _messages_to_gemini(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert our internal message format to Gemini Content objects/dicts.

        This handles:
          - Standard user/assistant text messages.
          - Assistant tool calls (mapping JSON strings to native FunctionCall parts).
          - Tool results (mapping JSON strings/dicts to native FunctionResponse parts).
        """
        gemini_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "assistant":
                # Check if it is a JSON tool call
                try:
                    data = json.loads(content) if isinstance(content, str) else content
                    if isinstance(data, dict) and data.get("type") == "tool_call":
                        gemini_messages.append({
                            "role": "model",
                            "parts": [{
                                "function_call": {
                                    "name": data.get("tool"),
                                    "args": data.get("args", {})
                                }
                            }]
                        })
                        continue
                except Exception:
                    pass

                gemini_messages.append({"role": "model", "parts": [content]})

            elif role == "tool":
                # Check if it is a JSON tool result
                try:
                    data = json.loads(content) if isinstance(content, str) else content
                    if isinstance(data, dict) and "tool" in data:
                        gemini_messages.append({
                            "role": "user",
                            "parts": [{
                                "function_response": {
                                    "name": data.get("tool"),
                                    "response": {"result": data.get("result", "")}
                                }
                            }]
                        })
                        continue
                except Exception:
                    pass

                gemini_messages.append({"role": "user", "parts": [content]})

            elif role == "system":
                # System instructions are set globally at model build time
                continue

            else:
                gemini_messages.append({"role": "user", "parts": [content]})

        return gemini_messages

    def _retry(self, fn, *args, **kwargs):
        """Run *fn* with exponential backoff on transient Gemini errors."""
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                return fn(*args, **kwargs)
            except _RETRY_EXCEPTIONS as exc:
                last_exc = exc
                wait = _BACKOFF_BASE ** attempt
                logging.warning(
                    "Gemini transient error (attempt %s/%s): %s — retrying in %.1fs",
                    attempt + 1,
                    _MAX_RETRIES,
                    exc,
                    wait,
                )
                time.sleep(wait)
            except Exception:
                raise
        raise RuntimeError(
            f"Gemini request failed after {_MAX_RETRIES} retries: {last_exc}"
        )

    def _parse_response(self, response) -> str | dict[str, Any]:
        """Extract text or tool-call from a Gemini GenerateContentResponse."""
        candidate = response.candidates[0] if response.candidates else None
        if not candidate:
            return "No response from Gemini."

        # Check for function call parts first
        for part in candidate.content.parts:
            if hasattr(part, "function_call") and part.function_call:
                fc = part.function_call
                return {
                    "type": "tool_call",
                    "tool": fc.name,
                    "args": dict(fc.args),
                }

        # Otherwise it's a text response
        try:
            return response.text or ""
        except Exception:
            return ""

    # ── BaseLLMClient interface ───────────────────────────────────────────────

    def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[Any] | None = None,
    ) -> str | dict[str, Any]:
        """Blocking call — returns text string or tool-call dict."""
        gemini_messages = self._messages_to_gemini(messages)
        model = self._build_model(tools=tools, system_instruction=load_system_prompt())
        chat = model.start_chat(history=gemini_messages[:-1])
        last_message = gemini_messages[-1]["parts"] if gemini_messages else ""

        response = self._retry(chat.send_message, last_message)
        return self._parse_response(response)

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[Any] | None = None,
    ) -> AsyncIterator[str]:
        """Async generator — yields text chunks as they arrive."""
        gemini_messages = self._messages_to_gemini(messages)
        model = self._build_model(tools=tools, system_instruction=load_system_prompt())
        chat = model.start_chat(history=gemini_messages[:-1])
        last_message = gemini_messages[-1]["parts"] if gemini_messages else ""

        # google-generativeai streaming is synchronous; run in thread pool
        loop = asyncio.get_event_loop()
        response_iter = await loop.run_in_executor(
            None,
            lambda: chat.send_message(last_message, stream=True),
        )
        for chunk in response_iter:
            try:
                text = chunk.text
                if text:
                    yield text
            except Exception:
                continue

    def parse_tool_call(self, response: Any) -> dict[str, Any] | None:
        """Not needed for Gemini — _parse_response() handles it inline."""
        return None

    # ── Failure log analysis ──────────────────────────────────────────────────

    async def analyze_failure_log(
        self,
        log: str,
        platform: str = "unknown",
        repo: str = "unknown",
        job: str = "unknown",
        trigger: str = "unknown",
    ) -> AsyncIterator[str]:
        """Stream a structured analysis of a CI/CD failure log.

        Yields text chunks as Gemini processes the log.
        This is the core of the real-time AI analysis feature in the frontend.
        """
        user_message = _FAILURE_ANALYSIS_USER_TEMPLATE.format(
            platform=platform,
            repo=repo,
            job=job,
            trigger=trigger,
            log=log[:12_000],  # cap to avoid exceeding context window
        )
        model = self._build_model(system_instruction=_FAILURE_ANALYSIS_SYSTEM)
        loop = asyncio.get_event_loop()
        response_iter = await loop.run_in_executor(
            None,
            lambda: model.generate_content(user_message, stream=True),
        )
        for chunk in response_iter:
            try:
                text = chunk.text
                if text:
                    yield text
            except Exception:
                continue
