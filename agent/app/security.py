import json
import os
import threading
import time
from collections import deque
from pathlib import Path


SAFE_WORKSPACE_ROOT = Path(
    os.getenv("SAFE_WORKSPACE_ROOT", str(Path.cwd()))
).resolve()
ALLOWED_SHELL_PREFIXES = [
    item.strip()
    for item in os.getenv(
        "ALLOWED_SHELL_PREFIXES",
        "ls,dir,pwd,echo,cat,type,python -c",
    ).split(",")
    if item.strip()
]
TOOL_RATE_LIMIT_COUNT = int(os.getenv("TOOL_RATE_LIMIT_COUNT", "60"))
TOOL_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("TOOL_RATE_LIMIT_WINDOW_SECONDS", "60"))
TOOL_AUDIT_LOG_PATH = Path(os.getenv("TOOL_AUDIT_LOG_PATH", "logs/tool_audit.log"))
DANGEROUS_ACTIONS_REQUIRE_CONFIRMATION = (
    os.getenv("DANGEROUS_ACTIONS_REQUIRE_CONFIRMATION", "true").strip().lower()
    in {"1", "true", "yes", "on"}
)
DANGEROUS_CONFIRMATION_TOKEN = os.getenv("DANGEROUS_CONFIRMATION_TOKEN", "CONFIRM")

_rate_lock = threading.Lock()
_tool_calls = deque()


def is_within_workspace(path_value: str) -> bool:
    try:
        candidate = Path(path_value).resolve()
        return candidate == SAFE_WORKSPACE_ROOT or SAFE_WORKSPACE_ROOT in candidate.parents
    except OSError:
        return False


def is_command_allowed(command: str) -> bool:
    normalized = command.strip().lower()
    if not normalized:
        return False
    return any(normalized.startswith(prefix.lower()) for prefix in ALLOWED_SHELL_PREFIXES)


def is_rate_limited() -> bool:
    now = time.time()
    with _rate_lock:
        while _tool_calls and now - _tool_calls[0] > TOOL_RATE_LIMIT_WINDOW_SECONDS:
            _tool_calls.popleft()
        if len(_tool_calls) >= TOOL_RATE_LIMIT_COUNT:
            return True
        _tool_calls.append(now)
    return False


def audit_tool_call(tool: str, allowed: bool, reason: str, args: dict) -> None:
    event = {
        "ts": int(time.time()),
        "tool": tool,
        "allowed": allowed,
        "reason": reason,
        "arg_keys": sorted(list(args.keys())),
    }
    TOOL_AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TOOL_AUDIT_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=True) + "\n")


def is_confirmation_valid(args: dict) -> bool:
    if not DANGEROUS_ACTIONS_REQUIRE_CONFIRMATION:
        return True
    confirmation = args.get("confirmation")
    return isinstance(confirmation, str) and confirmation.strip() == DANGEROUS_CONFIRMATION_TOKEN

