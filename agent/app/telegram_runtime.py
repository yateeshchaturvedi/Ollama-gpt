import json
import logging
import os
import re
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta

import requests
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

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

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ALLOWED_USER_IDS = settings.telegram_allowed_user_ids
MAX_TELEGRAM_REPLY_CHARS = settings.max_telegram_reply_chars
GITHUB_MONITOR_REPOS = [
    r.strip() for r in os.getenv("GITHUB_MONITOR_REPOS", "").split(",") if r.strip()
]
GITHUB_ALERT_CHAT_ID = os.getenv("GITHUB_ALERT_CHAT_ID", "").strip()
GITHUB_ALERT_POLL_SECONDS = int(os.getenv("GITHUB_ALERT_POLL_SECONDS", "120"))
GITHUB_DIGEST_REPOS = [
    r.strip() for r in os.getenv("GITHUB_DIGEST_REPOS", "").split(",") if r.strip()
]
GITHUB_DIGEST_CHAT_ID = os.getenv("GITHUB_DIGEST_CHAT_ID", "").strip()
GITHUB_DIGEST_HOUR = int(os.getenv("GITHUB_DIGEST_HOUR", "9"))
GITHUB_DIGEST_MINUTE = int(os.getenv("GITHUB_DIGEST_MINUTE", "0"))
GITHUB_TZ_OFFSET_MINUTES = int(os.getenv("GITHUB_TZ_OFFSET_MINUTES", "330"))

MENTION_PATTERN = re.compile(r"@\w+")


def _sanitize_text(text: str) -> str:
    return MENTION_PATTERN.sub("", text).strip()


def _is_allowed_user(user_id: int) -> bool:
    if not TELEGRAM_ALLOWED_USER_IDS:
        return True
    return user_id in TELEGRAM_ALLOWED_USER_IDS


def _chunk_text(text: str, size: int) -> list[str]:
    if len(text) <= size:
        return [text]
    return [text[i : i + size] for i in range(0, len(text), size)]


async def _post_reply(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, reply_to_message_id: int, message: str
) -> None:
    for chunk in _chunk_text(message, MAX_TELEGRAM_REPLY_CHARS):
        try:
            await context.bot.send_message(
                chat_id=chat_id, text=chunk, reply_to_message_id=reply_to_message_id, parse_mode=None
            )
        except Exception as exc:
            logging.exception("Failed to send Telegram message: %s", exc)


async def _send_chat_message(context: ContextTypes.DEFAULT_TYPE, chat_id: str | int, message: str) -> None:
    for chunk in _chunk_text(message, MAX_TELEGRAM_REPLY_CHARS):
        try:
            await context.bot.send_message(chat_id=chat_id, text=chunk, parse_mode=None)
        except Exception as exc:
            logging.exception("Failed to send Telegram channel message: %s", exc)


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


def _start_failure_alert_worker(app: Application) -> None:
    if not GITHUB_MONITOR_REPOS or not GITHUB_ALERT_CHAT_ID:
        logging.info("GitHub failure alerts disabled (set GITHUB_MONITOR_REPOS and GITHUB_ALERT_CHAT_ID).")
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

                        async def send_alert() -> None:
                            await _send_chat_message(
                                app,
                                GITHUB_ALERT_CHAT_ID,
                                f"🚨 Workflow failure detected in {repo}\n{details}",
                            )

                        # Schedule the async task
                        try:
                            app.bot.loop.create_task(send_alert())
                        except RuntimeError:
                            logging.warning("Event loop not available for alert")
            except Exception as exc:
                logging.exception("Failure alert worker error: %s", exc)
            time.sleep(max(30, GITHUB_ALERT_POLL_SECONDS))

    threading.Thread(target=loop, daemon=True, name="github-failure-alert-worker").start()


def _start_daily_digest_worker(app: Application) -> None:
    if not GITHUB_DIGEST_REPOS or not GITHUB_DIGEST_CHAT_ID:
        logging.info("GitHub daily digest disabled (set GITHUB_DIGEST_REPOS and GITHUB_DIGEST_CHAT_ID).")
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

                    async def send_digest() -> None:
                        await _send_chat_message(app, GITHUB_DIGEST_CHAT_ID, digest)

                    # Schedule the async task
                    try:
                        app.bot.loop.create_task(send_digest())
                    except RuntimeError:
                        logging.warning("Event loop not available for digest")
                    last_sent_date.add(date_key)
            except Exception as exc:
                logging.exception("Digest worker error: %s", exc)
            time.sleep(30)

    threading.Thread(target=loop, daemon=True, name="github-digest-worker").start()


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    message_id = update.message.message_id
    text = update.message.text

    if not _is_allowed_user(user_id):
        logging.warning("Message from unauthorized user_id=%s", user_id)
        await _post_reply(context, chat_id, message_id, "You are not authorized to use this bot.")
        return

    conversation_key = f"telegram_{chat_id}"
    user_prompt = _sanitize_text(text)

    if not user_prompt:
        logging.debug("Skipped empty message")
        return

    lowered = user_prompt.lower()

    logging.info(
        "Incoming Telegram message from user_id=%s chat_id=%s message_id=%s",
        user_id,
        chat_id,
        message_id,
    )

    if lowered == "/models":
        names = _list_ollama_models()
        if not names:
            await _post_reply(
                context,
                chat_id,
                message_id,
                "No models found or unable to fetch model list from Ollama.",
            )
            return
        await _post_reply(context, chat_id, message_id, "Available models:\n- " + "\n- ".join(names))
        return

    if lowered.startswith("/model"):
        parts = user_prompt.split(maxsplit=1)
        if len(parts) == 1:
            current = context.user_data.get(f"{conversation_key}_model", settings.ollama_model)
            await _post_reply(context, chat_id, message_id, f"Current model for this chat: `{current}`")
            return
        requested_model = parts[1].strip()
        if requested_model.lower() == "reset":
            context.user_data[f"{conversation_key}_model"] = settings.ollama_model
            await _post_reply(
                context,
                chat_id,
                message_id,
                f"Model reset. Using default model `{settings.ollama_model}` for this chat.",
            )
            return
        context.user_data[f"{conversation_key}_model"] = requested_model
        await _post_reply(context, chat_id, message_id, f"Model set to `{requested_model}` for this chat.")
        return

    if lowered.startswith("/gh"):
        result = _handle_github_command(user_prompt) or "Unknown GitHub command. Use /gh help."
        await _post_reply(context, chat_id, message_id, result)
        return

    # Get or initialize conversation history for this chat
    if f"{conversation_key}_history" not in context.user_data:
        context.user_data[f"{conversation_key}_history"] = []

    conversation = context.user_data[f"{conversation_key}_history"]
    conversation.append({"role": "user", "content": user_prompt})
    active_model = context.user_data.get(f"{conversation_key}_model", settings.ollama_model)

    logging.info("Processing Telegram message chat_id=%s model=%s", chat_id, active_model)

    try:
        response_text = run_turn(conversation, model=active_model)
        conversation.append({"role": "assistant", "content": response_text})
        await _post_reply(context, chat_id, message_id, response_text)
        logging.info("Posted Telegram reply chat_id=%s", chat_id)
    except Exception as exc:
        logging.exception("Failed processing Telegram message: %s", exc)
        await _post_reply(context, chat_id, message_id, f"Error: {str(exc)}")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed_user(update.message.from_user.id):
        await update.message.reply_text("You are not authorized to use this bot.")
        return

    help_text = (
        "🤖 AI Assistant Bot\n\n"
        "Commands:\n"
        "/models - List available Ollama models\n"
        "/model <name> - Set the model for this chat\n"
        "/model reset - Reset to default model\n"
        "/gh help - GitHub commands\n\n"
        "Send any message to chat with the AI assistant."
    )
    await update.message.reply_text(help_text)


def main() -> None:
    setup_logging(settings.log_level)

    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("Missing Telegram bot token. Set TELEGRAM_BOT_TOKEN environment variable.")

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add handlers
    application.add_handler(MessageHandler(filters.COMMAND, start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # Start background workers
    _start_failure_alert_worker(application)
    _start_daily_digest_worker(application)

    logging.info("Telegram bot starting with polling...")
    application.run_polling()


if __name__ == "__main__":
    main()
