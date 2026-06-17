"""Shared utilities for the Slack bot.

Contains helpers for message posting, text sanitization, monitor state
persistence, and internal parsing helpers used by monitors.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from pathlib import Path

import requests
from slack_sdk import WebClient

from app.config import settings

# ── Constants ─────────────────────────────────────────────────────────────────

SLACK_BOT_TOKEN: str = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_APP_TOKEN: str = os.getenv("SLACK_APP_TOKEN", "")
SLACK_ALLOWED_CHANNEL: str = os.getenv("SLACK_ALLOWED_CHANNEL", "").strip()
MAX_SLACK_REPLY_CHARS: int = int(os.getenv("MAX_SLACK_REPLY_CHARS", "38000"))
SLACK_REQUIRE_MENTION: bool = os.getenv("SLACK_REQUIRE_MENTION", "true").strip().lower() in {
    "1", "true", "yes", "on",
}
MONITOR_STATE_PATH: str = os.getenv("MONITOR_STATE_PATH", "/workspace/monitor_state.json")

MENTION_PATTERN = re.compile(r"<@[^>]+>")
MONITOR_STATE_LOCK = threading.Lock()


# ── Monitor state persistence ─────────────────────────────────────────────────

def load_monitor_state() -> dict:
    path = Path(MONITOR_STATE_PATH)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logging.warning("Failed to load monitor state from %s: %s", path, exc)
        return {}


def save_monitor_state(state: dict) -> None:
    path = Path(MONITOR_STATE_PATH)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    except Exception as exc:
        logging.warning("Failed to save monitor state to %s: %s", path, exc)


# ── Text helpers ──────────────────────────────────────────────────────────────

def sanitize_text(text: str) -> str:
    """Strip Slack @mention tokens from user messages."""
    return MENTION_PATTERN.sub("", text).strip()


def is_dm(channel_type: str | None) -> bool:
    return channel_type == "im"


def chunk_text(text: str, size: int) -> list[str]:
    if len(text) <= size:
        return [text]
    return [text[i: i + size] for i in range(0, len(text), size)]


def post_reply(web_client: WebClient, channel: str, thread_ts: str, message: str) -> None:
    for chunk in chunk_text(message, MAX_SLACK_REPLY_CHARS):
        web_client.chat_postMessage(channel=channel, text=chunk, thread_ts=thread_ts)


def post_channel_message(web_client: WebClient, channel: str, message: str) -> None:
    for chunk in chunk_text(message, MAX_SLACK_REPLY_CHARS):
        web_client.chat_postMessage(channel=channel, text=chunk)


def should_skip_event(event: dict) -> tuple[bool, str]:
    if event.get("subtype") is not None:
        return True, "message subtype event"
    if event.get("bot_id"):
        return True, "bot-authored message"
    if not event.get("text"):
        return True, "empty text"
    return False, ""


# ── Ollama model listing (used until Phase 2 Gemini migration) ────────────────

def list_ollama_models() -> list[str]:
    try:
        response = requests.get(
            f"{settings.ollama_url}/api/tags", timeout=settings.ollama_timeout_seconds
        )
        response.raise_for_status()
        payload = response.json()
        models = payload.get("models", [])
        names = [m.get("name", "") for m in models if isinstance(m, dict) and m.get("name")]
        return sorted(names)
    except Exception as exc:
        logging.exception("Failed to list Ollama models: %s", exc)
        return []


# ── Monitor parsing helpers ────────────────────────────────────────────────────

def parse_failed_run_ids(runs_output: str) -> list[int]:
    failed: list[int] = []
    for line in runs_output.splitlines():
        if "conclusion=failure" not in line:
            continue
        match = re.search(r"id=(\d+)", line)
        if match:
            failed.append(int(match.group(1)))
    return failed


def parse_kv_line(line: str) -> dict[str, str]:
    pairs = re.findall(r"(\w+)=([^\s]+)", line)
    return {k: v for k, v in pairs}


def get_state_bucket(state: dict, key: str) -> dict:
    bucket = state.get(key)
    if not isinstance(bucket, dict):
        bucket = {}
        state[key] = bucket
    return bucket


def update_seen_ids(bucket: dict, scope: str, new_ids: set[int], keep: int = 200) -> None:
    existing = bucket.get(scope, [])
    if not isinstance(existing, list):
        existing = []
    merged = {int(x) for x in existing if str(x).isdigit()}
    merged.update(new_ids)
    bucket[scope] = sorted(merged)[-keep:]
