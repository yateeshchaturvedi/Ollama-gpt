import logging
import os
import re
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta

import requests
from slack_sdk import WebClient
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse

from app.agent_runtime import run_turn
from app.config import settings
from app.logging_utils import setup_logging
from app.tools import (
    github_actions_run_logs,
    github_actions_runs,
    github_cancel_workflow_run,
    github_changelog,
    github_daily_digest,
    github_deployment_status,
    github_issue_triage,
    github_multi_repo_dashboard,
    github_post_pr_comment,
    github_pr_files,
    github_pr_overview,
    github_pr_review_suggestions,
    github_release_notes_to_pr_comment,
    github_required_checks_gate,
    github_retry_workflow_run,
    github_security_summary,
)

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN", "")
SLACK_ALLOWED_CHANNEL = os.getenv("SLACK_ALLOWED_CHANNEL", "").strip()
MAX_SLACK_REPLY_CHARS = int(os.getenv("MAX_SLACK_REPLY_CHARS", "38000"))
SLACK_REQUIRE_MENTION = os.getenv("SLACK_REQUIRE_MENTION", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
GITHUB_MONITOR_REPOS = [
    r.strip() for r in os.getenv("GITHUB_MONITOR_REPOS", "").split(",") if r.strip()
]
GITHUB_ALERT_CHANNEL = os.getenv("GITHUB_ALERT_CHANNEL", "").strip()
GITHUB_ALERT_POLL_SECONDS = int(os.getenv("GITHUB_ALERT_POLL_SECONDS", "120"))
GITHUB_DIGEST_REPOS = [
    r.strip() for r in os.getenv("GITHUB_DIGEST_REPOS", "").split(",") if r.strip()
]
GITHUB_DIGEST_CHANNEL = os.getenv("GITHUB_DIGEST_CHANNEL", "").strip()
GITHUB_DIGEST_HOUR = int(os.getenv("GITHUB_DIGEST_HOUR", "9"))
GITHUB_DIGEST_MINUTE = int(os.getenv("GITHUB_DIGEST_MINUTE", "0"))
GITHUB_TZ_OFFSET_MINUTES = int(os.getenv("GITHUB_TZ_OFFSET_MINUTES", "330"))

MENTION_PATTERN = re.compile(r"<@[^>]+>")


def _sanitize_text(text: str) -> str:
    return MENTION_PATTERN.sub("", text).strip()


def _is_dm(channel_type: str | None) -> bool:
    return channel_type == "im"


def _chunk_text(text: str, size: int) -> list[str]:
    if len(text) <= size:
        return [text]
    return [text[i : i + size] for i in range(0, len(text), size)]


def _post_reply(web_client: WebClient, channel: str, thread_ts: str, message: str) -> None:
    for chunk in _chunk_text(message, MAX_SLACK_REPLY_CHARS):
        web_client.chat_postMessage(channel=channel, text=chunk, thread_ts=thread_ts)


def _post_channel_message(web_client: WebClient, channel: str, message: str) -> None:
    for chunk in _chunk_text(message, MAX_SLACK_REPLY_CHARS):
        web_client.chat_postMessage(channel=channel, text=chunk)


def _should_skip_event(event: dict) -> tuple[bool, str]:
    if event.get("subtype") is not None:
        return True, "message subtype event"
    if event.get("bot_id"):
        return True, "bot-authored message"
    if not event.get("text"):
        return True, "empty text"
    return False, ""


def _list_ollama_models() -> list[str]:
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


def _parse_failed_run_ids(runs_output: str) -> list[int]:
    failed: list[int] = []
    for line in runs_output.splitlines():
        if "conclusion=failure" not in line:
            continue
        match = re.search(r"id=(\d+)", line)
        if match:
            failed.append(int(match.group(1)))
    return failed


def _github_help_text() -> str:
    return (
        "GitHub commands:\n"
        "/gh runs owner/repo\n"
        "/gh run owner/repo <run_id>\n"
        "/gh retry owner/repo <run_id>\n"
        "/gh cancel owner/repo <run_id>\n"
        "/gh pr overview owner/repo <pr_number>\n"
        "/gh pr files owner/repo <pr_number> [limit]\n"
        "/gh pr review owner/repo <pr_number> [limit]\n"
        "/gh pr comment owner/repo <pr_number> <comment text>\n"
        "/gh checks owner/repo <pr_number>\n"
        "/gh deploy owner/repo\n"
        "/gh issues owner/repo\n"
        "/gh security owner/repo\n"
        "/gh changelog owner/repo <base> <head>\n"
        "/gh release-note owner/repo <pr_number> <base> <head>\n"
        "/gh dashboard owner/repo,owner/repo2\n"
        "/gh digest owner/repo,owner/repo2"
    )


def _handle_github_command(user_prompt: str) -> str | None:
    if not user_prompt.lower().startswith("/gh"):
        return None

    parts = user_prompt.split()
    if len(parts) == 1 or (len(parts) > 1 and parts[1].lower() == "help"):
        return _github_help_text()

    sub = parts[1].lower()
    try:
        if sub == "runs" and len(parts) >= 3:
            return github_actions_runs({"repo": parts[2], "per_page": 10})
        if sub == "run" and len(parts) >= 4:
            return github_actions_run_logs({"repo": parts[2], "run_id": int(parts[3])})
        if sub == "retry" and len(parts) >= 4:
            return github_retry_workflow_run({"repo": parts[2], "run_id": int(parts[3])})
        if sub == "cancel" and len(parts) >= 4:
            return github_cancel_workflow_run({"repo": parts[2], "run_id": int(parts[3])})
        if sub == "checks" and len(parts) >= 4:
            return github_required_checks_gate({"repo": parts[2], "pr_number": int(parts[3])})
        if sub == "deploy" and len(parts) >= 3:
            return github_deployment_status({"repo": parts[2], "per_page": 10})
        if sub == "issues" and len(parts) >= 3:
            return github_issue_triage({"repo": parts[2], "per_page": 20})
        if sub == "security" and len(parts) >= 3:
            return github_security_summary({"repo": parts[2], "per_page": 20})
        if sub == "changelog" and len(parts) >= 5:
            return github_changelog({"repo": parts[2], "base": parts[3], "head": parts[4]})
        if sub == "release-note" and len(parts) >= 6:
            return github_release_notes_to_pr_comment(
                {"repo": parts[2], "pr_number": int(parts[3]), "base": parts[4], "head": parts[5]}
            )
        if sub == "dashboard" and len(parts) >= 3:
            return github_multi_repo_dashboard({"repos": parts[2]})
        if sub == "digest" and len(parts) >= 3:
            return github_daily_digest({"repos": parts[2]})
        if sub == "pr" and len(parts) >= 5:
            pr_sub = parts[2].lower()
            repo = parts[3]
            pr_number = int(parts[4])
            if pr_sub == "overview":
                return github_pr_overview({"repo": repo, "pr_number": pr_number})
            if pr_sub == "files":
                limit = int(parts[5]) if len(parts) >= 6 else 20
                return github_pr_files({"repo": repo, "pr_number": pr_number, "limit": limit})
            if pr_sub == "review":
                limit = int(parts[5]) if len(parts) >= 6 else 20
                return github_pr_review_suggestions(
                    {"repo": repo, "pr_number": pr_number, "limit": limit}
                )
            if pr_sub == "comment" and len(parts) >= 6:
                comment = " ".join(parts[5:])
                return github_post_pr_comment({"repo": repo, "pr_number": pr_number, "body": comment})
    except ValueError:
        return "Invalid numeric value in command. Use /gh help for command formats."
    return "Unknown GitHub command. Use /gh help."


def _start_failure_alert_worker(web_client: WebClient) -> None:
    if not GITHUB_MONITOR_REPOS or not GITHUB_ALERT_CHANNEL:
        logging.info("GitHub failure alerts disabled (set GITHUB_MONITOR_REPOS and GITHUB_ALERT_CHANNEL).")
        return

    seen_failures: dict[str, set[int]] = defaultdict(set)

    def loop() -> None:
        logging.info("GitHub failure alert worker started for repos=%s", GITHUB_MONITOR_REPOS)
        while True:
            try:
                for repo in GITHUB_MONITOR_REPOS:
                    runs_output = github_actions_runs({"repo": repo, "per_page": 10})
                    for run_id in _parse_failed_run_ids(runs_output):
                        if run_id in seen_failures[repo]:
                            continue
                        seen_failures[repo].add(run_id)
                        details = github_actions_run_logs({"repo": repo, "run_id": run_id})
                        _post_channel_message(
                            web_client,
                            GITHUB_ALERT_CHANNEL,
                            f":rotating_light: Workflow failure detected in {repo}\n{details}",
                        )
            except Exception as exc:
                logging.exception("Failure alert worker error: %s", exc)
            time.sleep(max(30, GITHUB_ALERT_POLL_SECONDS))

    threading.Thread(target=loop, daemon=True, name="github-failure-alert-worker").start()


def _start_daily_digest_worker(web_client: WebClient) -> None:
    if not GITHUB_DIGEST_REPOS or not GITHUB_DIGEST_CHANNEL:
        logging.info("GitHub daily digest disabled (set GITHUB_DIGEST_REPOS and GITHUB_DIGEST_CHANNEL).")
        return

    last_sent_date: set[str] = set()

    def loop() -> None:
        logging.info("GitHub digest worker started repos=%s", GITHUB_DIGEST_REPOS)
        while True:
            try:
                now_local = datetime.utcnow() + timedelta(minutes=GITHUB_TZ_OFFSET_MINUTES)
                date_key = now_local.strftime("%Y-%m-%d")
                if (
                    now_local.hour == GITHUB_DIGEST_HOUR
                    and now_local.minute == GITHUB_DIGEST_MINUTE
                    and date_key not in last_sent_date
                ):
                    digest = github_daily_digest({"repos": GITHUB_DIGEST_REPOS})
                    _post_channel_message(web_client, GITHUB_DIGEST_CHANNEL, digest)
                    last_sent_date.add(date_key)
            except Exception as exc:
                logging.exception("Digest worker error: %s", exc)
            time.sleep(30)

    threading.Thread(target=loop, daemon=True, name="github-digest-worker").start()


def main() -> None:
    setup_logging(settings.log_level)

    if not SLACK_BOT_TOKEN or not SLACK_APP_TOKEN:
        raise RuntimeError(
            "Missing Slack tokens. Set SLACK_BOT_TOKEN and SLACK_APP_TOKEN environment variables."
        )

    web_client = WebClient(token=SLACK_BOT_TOKEN)
    socket_client = SocketModeClient(app_token=SLACK_APP_TOKEN, web_client=web_client)
    histories: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    model_selection: defaultdict[str, str] = defaultdict(lambda: settings.ollama_model)

    auth = web_client.auth_test()
    bot_user_id = auth["user_id"]
    logging.info("Slack bot authenticated as user_id=%s", bot_user_id)

    _start_failure_alert_worker(web_client)
    _start_daily_digest_worker(web_client)

    def process(client: SocketModeClient, req: SocketModeRequest) -> None:
        if req.type != "events_api":
            logging.debug("Ignoring non-events_api request type=%s", req.type)
            return

        client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))

        event = req.payload.get("event", {})
        event_type = event.get("type")
        channel = event.get("channel", "")
        channel_type = event.get("channel_type")
        text = event.get("text", "")
        thread_ts = event.get("thread_ts") or event.get("ts")
        logging.info(
            "Incoming Slack event type=%s channel=%s channel_type=%s thread=%s",
            event_type,
            channel,
            channel_type,
            thread_ts,
        )

        should_skip, skip_reason = _should_skip_event(event)
        if should_skip:
            logging.debug("Skipped Slack event: %s", skip_reason)
            return

        if SLACK_ALLOWED_CHANNEL and channel != SLACK_ALLOWED_CHANNEL:
            if not _is_dm(channel_type):
                logging.debug(
                    "Skipped Slack event: channel %s is not allowed channel %s",
                    channel,
                    SLACK_ALLOWED_CHANNEL,
                )
                return

        is_mention = f"<@{bot_user_id}>" in text
        if not _is_dm(channel_type) and SLACK_REQUIRE_MENTION and not is_mention:
            logging.debug("Skipped Slack event: missing @mention in channel message")
            return

        user_prompt = _sanitize_text(text)
        if not user_prompt:
            logging.debug("Skipped Slack event: prompt empty after sanitization")
            return

        conversation_key = thread_ts if thread_ts else channel
        lowered = user_prompt.lower()

        if lowered == "/models":
            names = _list_ollama_models()
            if not names:
                _post_reply(
                    web_client,
                    channel,
                    thread_ts,
                    "No models found or unable to fetch model list from Ollama.",
                )
                return
            _post_reply(web_client, channel, thread_ts, "Available models:\n- " + "\n- ".join(names))
            return

        if lowered.startswith("/model"):
            parts = user_prompt.split(maxsplit=1)
            if len(parts) == 1:
                current = model_selection[conversation_key]
                _post_reply(web_client, channel, thread_ts, f"Current model for this thread: `{current}`")
                return
            requested_model = parts[1].strip()
            if requested_model.lower() == "reset":
                model_selection[conversation_key] = settings.ollama_model
                _post_reply(
                    web_client,
                    channel,
                    thread_ts,
                    f"Model reset. Using default model `{settings.ollama_model}` for this thread.",
                )
                return
            model_selection[conversation_key] = requested_model
            _post_reply(web_client, channel, thread_ts, f"Model set to `{requested_model}` for this thread.")
            return

        if lowered.startswith("/gh"):
            result = _handle_github_command(user_prompt) or "Unknown GitHub command. Use /gh help."
            _post_reply(web_client, channel, thread_ts, result)
            return

        conversation = histories[conversation_key]
        conversation.append({"role": "user", "content": user_prompt})
        active_model = model_selection[conversation_key]
        logging.info(
            "Processing Slack message channel=%s thread=%s model=%s",
            channel,
            thread_ts,
            active_model,
        )
        response_text = run_turn(conversation, model=active_model)
        conversation.append({"role": "assistant", "content": response_text})
        try:
            _post_reply(web_client, channel, thread_ts, response_text)
            logging.info("Posted Slack reply channel=%s thread=%s", channel, thread_ts)
        except Exception as exc:
            logging.exception("Failed posting Slack reply: %s", exc)

    socket_client.socket_mode_request_listeners.append(process)
    socket_client.connect()
    logging.info("Slack Socket Mode client connected.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Slack bot stopped.")

