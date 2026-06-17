"""Slack Socket Mode event handler and bot main loop."""
from __future__ import annotations

import logging
import os
import time
from collections import defaultdict

from slack_sdk import WebClient
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse

from app.agent_runtime import run_turn
from app.config import settings
from app.logging_utils import setup_logging
from app.security import run_startup_checks
from app.slack.commands import handle_github_command, handle_model_command, handle_models_command
from app.slack.monitors import start_all_monitors
from app.slack.utils import (
    SLACK_ALLOWED_CHANNEL,
    SLACK_APP_TOKEN,
    SLACK_BOT_TOKEN,
    SLACK_REQUIRE_MENTION,
    is_dm,
    post_reply,
    sanitize_text,
    should_skip_event,
)


def main() -> None:
    setup_logging(settings.log_level)
    run_startup_checks()

    if not SLACK_BOT_TOKEN or not SLACK_APP_TOKEN:
        raise RuntimeError(
            "Missing Slack tokens. Set SLACK_BOT_TOKEN and SLACK_APP_TOKEN environment variables."
        )

    web_client = WebClient(token=SLACK_BOT_TOKEN)
    socket_client = SocketModeClient(app_token=SLACK_APP_TOKEN, web_client=web_client)

    # Per-thread conversation history and per-thread model selection
    histories: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    model_selection: defaultdict[str, str] = defaultdict(lambda: settings.ollama_model)

    auth = web_client.auth_test()
    bot_user_id = auth["user_id"]
    logging.info("Slack bot authenticated as user_id=%s", bot_user_id)

    # Start all CI/CD background monitors
    start_all_monitors(web_client)

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
            event_type, channel, channel_type, thread_ts,
        )

        skip, skip_reason = should_skip_event(event)
        if skip:
            logging.debug("Skipped Slack event: %s", skip_reason)
            return

        if SLACK_ALLOWED_CHANNEL and channel != SLACK_ALLOWED_CHANNEL:
            if not is_dm(channel_type):
                logging.debug(
                    "Skipped Slack event: channel %s is not allowed channel %s",
                    channel, SLACK_ALLOWED_CHANNEL,
                )
                return

        is_mention = f"<@{bot_user_id}>" in text
        if not is_dm(channel_type) and SLACK_REQUIRE_MENTION and not is_mention:
            logging.debug("Skipped Slack event: missing @mention in channel message")
            return

        user_prompt = sanitize_text(text)
        if not user_prompt:
            logging.debug("Skipped Slack event: prompt empty after sanitization")
            return

        conversation_key = thread_ts if thread_ts else channel
        lowered = user_prompt.lower()

        # ── Built-in slash commands ──────────────────────────────────────────
        if lowered == "/models":
            post_reply(web_client, channel, thread_ts, handle_models_command())
            return

        if lowered.startswith("/model"):
            reply = handle_model_command(
                user_prompt, conversation_key, model_selection, settings.ollama_model
            )
            post_reply(web_client, channel, thread_ts, reply)
            return

        if lowered.startswith("/gh"):
            result = handle_github_command(user_prompt) or "Unknown GitHub command. Use /gh help."
            post_reply(web_client, channel, thread_ts, result)
            return

        # ── Agent turn ───────────────────────────────────────────────────────
        conversation = histories[conversation_key]
        conversation.append({"role": "user", "content": user_prompt})
        active_model = model_selection[conversation_key]

        logging.info(
            "Processing Slack message channel=%s thread=%s model=%s",
            channel, thread_ts, active_model,
        )

        response_text = run_turn(conversation, model=active_model)
        conversation.append({"role": "assistant", "content": response_text})

        try:
            post_reply(web_client, channel, thread_ts, response_text)
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
