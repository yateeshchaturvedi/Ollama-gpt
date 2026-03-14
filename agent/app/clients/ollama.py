import json
import logging
import time

import requests

from app.config import settings


def call_ollama(prompt: str, model: str) -> str:
    """Call Ollama with retries and simple backoff."""
    last_error: Exception | None = None

    for attempt in range(1, settings.ollama_retries + 1):
        try:
            response = requests.post(
                f"{settings.ollama_url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=settings.ollama_timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            if "response" not in data:
                raise ValueError("Ollama response missing 'response' field.")
            return data["response"]
        except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            logging.warning(
                "Ollama call failed (attempt %s/%s): %s",
                attempt,
                settings.ollama_retries,
                exc,
            )
            if attempt < settings.ollama_retries:
                time.sleep(attempt)

    raise RuntimeError(
        f"Ollama request failed after {settings.ollama_retries} retries: {last_error}"
    )

