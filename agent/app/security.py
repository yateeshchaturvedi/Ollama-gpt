"""Security controls for the agent.

Responsibilities:
- Workspace path sandboxing (read_file / write_file)
- Shell command allowlist (run_shell)
- Per-window rate limiting on tool calls
- Structured audit logging with automatic rotation
- Dangerous-action confirmation token validation
- Startup safety checks
"""
from __future__ import annotations

import json
import logging
import threading
import time
import warnings
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.config import settings

# ── Resolved constants (cached once at import time) ──────────────────────────

SAFE_WORKSPACE_ROOT: Path = Path(settings.safe_workspace_root).resolve()

# NOTE: 'python -c' has been intentionally removed from the default allowlist.
# It is equivalent to arbitrary code execution and must not be a default.
ALLOWED_SHELL_PREFIXES: list[str] = settings.allowed_shell_prefixes_list()

TOOL_RATE_LIMIT_COUNT: int = settings.tool_rate_limit_count
TOOL_RATE_LIMIT_WINDOW_SECONDS: int = settings.tool_rate_limit_window_seconds
DANGEROUS_ACTIONS_REQUIRE_CONFIRMATION: bool = settings.dangerous_actions_require_confirmation
DANGEROUS_CONFIRMATION_TOKEN: str = settings.dangerous_confirmation_token
MAX_SHELL_OUTPUT_CHARS: int = settings.max_shell_output_chars

# ── Rate-limiter state ────────────────────────────────────────────────────────

_rate_lock = threading.Lock()
_tool_calls: list[float] = []

# ── Audit logger (separate from root logger, with rotation) ──────────────────

_audit_logger = logging.getLogger("tool_audit")
_audit_logger.setLevel(logging.INFO)
_audit_logger.propagate = False  # don't pollute the root logger

_audit_log_path = Path(settings.tool_audit_log_path)
_audit_log_path.parent.mkdir(parents=True, exist_ok=True)

_audit_handler = RotatingFileHandler(
    _audit_log_path,
    maxBytes=settings.tool_audit_log_max_bytes,
    backupCount=settings.tool_audit_log_backup_count,
    encoding="utf-8",
)
_audit_handler.setFormatter(logging.Formatter("%(message)s"))
_audit_logger.addHandler(_audit_handler)


# ── Startup safety checks ─────────────────────────────────────────────────────

def run_startup_checks() -> None:
    """Emit warnings for insecure or misconfigured settings.

    Called once from agent entrypoints (agent.py / slack_bot.py).
    Does not raise — warnings are logged so the agent still starts.
    """
    if DANGEROUS_CONFIRMATION_TOKEN == "CONFIRM" and settings.log_level != "DEBUG":
        warnings.warn(
            "DANGEROUS_CONFIRMATION_TOKEN is still set to the default value 'CONFIRM'. "
            "Change this to a random secret in production to prevent prompt-injection attacks.",
            stacklevel=2,
        )
        logging.warning(
            "[SECURITY] DANGEROUS_CONFIRMATION_TOKEN is the insecure default 'CONFIRM'. "
            "Set a strong random value in production."
        )

    if any(prefix.lower().startswith("python") for prefix in ALLOWED_SHELL_PREFIXES):
        logging.warning(
            "[SECURITY] ALLOWED_SHELL_PREFIXES contains a 'python' prefix. "
            "This allows arbitrary code execution. Remove it unless intentional."
        )

    logging.info(
        "[SECURITY] Workspace root: %s | Shell prefixes: %s | Rate limit: %s/%ss",
        SAFE_WORKSPACE_ROOT,
        ALLOWED_SHELL_PREFIXES,
        TOOL_RATE_LIMIT_COUNT,
        TOOL_RATE_LIMIT_WINDOW_SECONDS,
    )


# ── Path sandbox ──────────────────────────────────────────────────────────────

def is_within_workspace(path_value: str) -> bool:
    """Return True only if *path_value* is inside SAFE_WORKSPACE_ROOT."""
    try:
        candidate = Path(path_value).resolve()
        return candidate == SAFE_WORKSPACE_ROOT or SAFE_WORKSPACE_ROOT in candidate.parents
    except OSError:
        return False


# ── Shell allowlist ───────────────────────────────────────────────────────────

def is_command_allowed(command: str) -> bool:
    """Return True only if *command* starts with an approved prefix.

    The check is case-insensitive and strips leading whitespace.
    Note: 'python -c' is NOT in the default allowlist — it is a code-execution bypass.
    """
    normalized = command.strip().lower()
    if not normalized:
        return False
    return any(normalized.startswith(prefix.lower()) for prefix in ALLOWED_SHELL_PREFIXES)


# ── Rate limiter ──────────────────────────────────────────────────────────────

def is_rate_limited() -> bool:
    """Sliding-window rate limiter. Thread-safe."""
    now = time.monotonic()
    with _rate_lock:
        cutoff = now - TOOL_RATE_LIMIT_WINDOW_SECONDS
        # Purge expired entries
        while _tool_calls and _tool_calls[0] < cutoff:
            _tool_calls.pop(0)
        if len(_tool_calls) >= TOOL_RATE_LIMIT_COUNT:
            return True
        _tool_calls.append(now)
    return False


# ── Audit logging ─────────────────────────────────────────────────────────────

def audit_tool_call(tool: str, allowed: bool, reason: str, args: dict) -> None:
    """Write a structured audit event.

    The RotatingFileHandler takes care of log rotation automatically.
    Args keys are logged (not values) to avoid leaking secrets.
    """
    event = {
        "ts": int(time.time()),
        "tool": tool,
        "allowed": allowed,
        "reason": reason,
        "arg_keys": sorted(args.keys()),
    }
    _audit_logger.info(json.dumps(event, ensure_ascii=True))


# ── Confirmation token ────────────────────────────────────────────────────────

def is_confirmation_valid(args: dict) -> bool:
    """Return True if dangerous-action confirmation is satisfied."""
    if not DANGEROUS_ACTIONS_REQUIRE_CONFIRMATION:
        return True
    confirmation = args.get("confirmation")
    return isinstance(confirmation, str) and confirmation.strip() == DANGEROUS_CONFIRMATION_TOKEN


# ── Shell output guard ────────────────────────────────────────────────────────

def truncate_shell_output(output: str) -> str:
    """Cap shell command output before it is passed to the LLM."""
    if len(output) <= MAX_SHELL_OUTPUT_CHARS:
        return output
    return (
        output[:MAX_SHELL_OUTPUT_CHARS]
        + f"\n\n[Output truncated at {MAX_SHELL_OUTPUT_CHARS} characters. "
        "Set MAX_SHELL_OUTPUT_CHARS to increase the limit.]"
    )
