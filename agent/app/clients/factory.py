"""LLM provider factory.

Usage:
    from app.clients.factory import get_llm_client
    client = get_llm_client()
    response = client.generate(messages, tools)

Switching providers = one env-var change:
    LLM_PROVIDER=gemini      → GeminiLLMClient
    LLM_PROVIDER=openai      → OpenAILLMClient  (stub, set OPENAI_API_KEY)
    LLM_PROVIDER=anthropic   → AnthropicLLMClient (stub, set ANTHROPIC_API_KEY)
    LLM_PROVIDER=ollama      → falls back to legacy Ollama HTTP client
"""
from __future__ import annotations

import logging

from app.clients.base import BaseLLMClient
from app.config import settings

_cached_client: BaseLLMClient | None = None


def get_llm_client(
    force_new: bool = False,
    provider: str | None = None,
    api_key: str | None = None,
    model_name: str | None = None,
) -> BaseLLMClient:
    """Return the LLM client singleton for the configured provider.

    The client is cached after first construction.
    Pass force_new=True to re-initialise (useful in tests).
    """
    global _cached_client
    if _cached_client is not None and not force_new and provider is None and api_key is None and model_name is None:
        return _cached_client

    provider_to_use = (provider or settings.llm_provider).lower()
    logging.info("Initialising LLM provider: %s", provider_to_use)

    if provider_to_use == "gemini":
        from app.clients.gemini import GeminiLLMClient
        _cached_client = GeminiLLMClient(api_key=api_key, model_name=model_name)

    elif provider == "openai":
        from app.clients.openai_client import OpenAILLMClient
        _cached_client = OpenAILLMClient()

    elif provider == "anthropic":
        from app.clients.anthropic_client import AnthropicLLMClient
        _cached_client = AnthropicLLMClient()

    elif provider == "ollama":
        # Legacy Ollama mode — returns a thin shim so the rest of the
        # runtime doesn't need special-casing.
        from app.clients.ollama_shim import OllamaLLMClient
        _cached_client = OllamaLLMClient()

    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER '{provider}'. "
            "Valid values: gemini, openai, anthropic, ollama"
        )

    return _cached_client
