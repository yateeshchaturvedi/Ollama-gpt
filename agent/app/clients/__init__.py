"""Clients package — LLM provider abstraction layer."""
from app.clients.factory import get_llm_client

__all__ = ["get_llm_client"]
