import os
from dataclasses import dataclass


@dataclass
class Settings:
    ollama_url: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3")
    ollama_timeout_seconds: int = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60"))
    ollama_retries: int = int(os.getenv("OLLAMA_RETRIES", "3"))
    max_tool_steps: int = int(os.getenv("MAX_TOOL_STEPS", "5"))
    max_history: int = int(os.getenv("MAX_HISTORY", "12"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()


settings = Settings()
