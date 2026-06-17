import json
import logging
import os
import re
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import requests
from slack_sdk import WebClient
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse

from app.agent_runtime import run_turn
from app.config import settings
from app.logging_utils import setup_logging
from app.tools import (
    azure_devops_recent_runs,
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
    gitlab_recent_pipelines,
    jenkins_recent_builds,
)
from app.tools.github_tools import github_list_open_prs

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
GITHUB_PR_MONITOR_REPOS = [
    r.strip() for r in os.getenv("GITHUB_PR_MONITOR_REPOS", "").split(",") if r.strip()
]
GITHUB_PR_ALERT_CHANNEL = os.getenv("GITHUB_PR_ALERT_CHANNEL", "").strip()
GITHUB_PR_POLL_SECONDS = int(os.getenv("GITHUB_PR_POLL_SECONDS", "180"))
GITHUB_DIGEST_REPOS = [
    r.strip() for r in os.getenv("GITHUB_DIGEST_REPOS", "").split(",") if r.strip()
]
GITHUB_DIGEST_CHANNEL = os.getenv("GITHUB_DIGEST_CHANNEL", "").strip()
GITHUB_DIGEST_HOUR = int(os.getenv("GITHUB_DIGEST_HOUR", "9"))
GITHUB_DIGEST_MINUTE = int(os.getenv("GITHUB_DIGEST_MINUTE", "0"))
GITHUB_TZ_OFFSET_MINUTES = int(os.getenv("GITHUB_TZ_OFFSET_MINUTES", "330"))
JENKINS_MONITOR_JOBS = [
    j.strip() for j in os.getenv("JENKINS_MONITOR_JOBS", "").split(",") if j.strip()
]
JENKINS_ALERT_CHANNEL = os.getenv("JENKINS_ALERT_CHANNEL", "").strip()
JENKINS_POLL_SECONDS = int(os.getenv("JENKINS_POLL_SECONDS", "180"))
GITLAB_MONITOR_PROJECTS = [
    p.strip() for p in os.getenv("GITLAB_MONITOR_PROJECTS", "").split(",") if p.strip()
]
GITLAB_ALERT_CHANNEL = os.getenv("GITLAB_ALERT_CHANNEL", "").strip()
GITLAB_POLL_SECONDS = int(os.getenv("GITLAB_POLL_SECONDS", "180"))
AZDO_MONITOR_PIPELINES = [
    p.strip() for p in os.getenv("AZDO_MONITOR_PIPELINES", "").split(",") if p.strip()
]
AZDO_ALERT_CHANNEL = os.getenv("AZDO_ALERT_CHANNEL", "").strip()
AZDO_POLL_SECONDS = int(os.getenv("AZDO_POLL_SECONDS", "180"))
MONITOR_STATE_PATH = os.getenv("MONITOR_STATE_PATH", "/workspace/monitor_state.json")

MENTION_PATTERN = re.compile(r"<@[^>]+>")
MONITOR_STATE_LOCK = threading.Lock()


def _load_monitor_state() -> dict:
    path = Path(MONITOR_STATE_PATH)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logging.warning("Failed to load monitor state from %s: %s", path, exc)
        return {}


def _save_monitor_state(state: dict) -> None:
    path = Path(MONITOR_STATE_PATH)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    except Exception as exc:
        logging.warning("Failed to save monitor state to %s: %s", path, exc)


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


def _parse_kv_line(line: str) -> dict[str, str]:
    pairs = re.findall(r"(\\w+)=([^\\s]+)", line)
    return {k: v for k, v in pairs}


def _get_state_bucket(state: dict, key: str) -> dict:
    bucket = state.get(key)
    if not isinstance(bucket, dict):
        bucket = {}
        state[key] = bucket
    return bucket


def _update_seen_ids(bucket: dict, scope: str, new_ids: set[int], keep: int = 200) -> None:
    existing = bucket.get(scope, [])
    if not isinstance(existing, list):
        existing = []
    merged = set(int(x) for x in existing if str(x).isdigit())
    merged.update(new_ids)
    bucket[scope] = sorted(merged)[-keep:]


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


def _start_github_pr_worker(web_client: WebClient) -> None:
    repos = GITHUB_PR_MONITOR_REPOS or GITHUB_MONITOR_REPOS
    channel = GITHUB_PR_ALERT_CHANNEL or GITHUB_ALERT_CHANNEL
    if not repos or not channel:
        logging.info("GitHub PR monitoring disabled (set GITHUB_PR_MONITOR_REPOS and GITHUB_PR_ALERT_CHANNEL).")
        return

    state = _load_monitor_state()

    def loop() -> None:
        logging.info("GitHub PR monitor worker started repos=%s", repos)
        while True:
            try:
                with MONITOR_STATE_LOCK:
                    bucket = _get_state_bucket(state, "github_prs")
                for repo in repos:
                    prs = github_list_open_prs(repo, per_page=20)
                    if not prs:
                        continue
                    seen_list = bucket.get(repo, [])
                    seen = set(int(x) for x in seen_list if str(x).isdigit())
                    new_seen: set[int] = set()
                    for pr in prs:
                        number = pr.get("number")
                        if not isinstance(number, int) or number in seen:
                            continue
                        new_seen.add(number)
                        title = pr.get("title") or ""
                        author = ((pr.get("user") or {}).get("login")) or "unknown"
                        url = pr.get("html_url") or ""
                        _post_channel_message(
                            web_client,
                            channel,
                            f":sparkles: New PR in {repo} #{number} by {author}\n{title}\n{url}",
                        )
                    if new_seen:
                        with MONITOR_STATE_LOCK:
                            _update_seen_ids(bucket, repo, new_seen)
                            _save_monitor_state(state)
            except Exception as exc:
                logging.exception("GitHub PR monitor error: %s", exc)
            time.sleep(max(30, GITHUB_PR_POLL_SECONDS))

    threading.Thread(target=loop, daemon=True, name="github-pr-monitor-worker").start()


def _start_jenkins_worker(web_client: WebClient) -> None:
    if not JENKINS_MONITOR_JOBS or not JENKINS_ALERT_CHANNEL:
        logging.info("Jenkins monitoring disabled (set JENKINS_MONITOR_JOBS and JENKINS_ALERT_CHANNEL).")
        return

    state = _load_monitor_state()

    def loop() -> None:
        logging.info("Jenkins monitor worker started jobs=%s", JENKINS_MONITOR_JOBS)
        while True:
            try:
                with MONITOR_STATE_LOCK:
                    last_seen = _get_state_bucket(state, "jenkins_last_seen")
                    seen_failures = _get_state_bucket(state, "jenkins_failures")
                for job in JENKINS_MONITOR_JOBS:
                    output = jenkins_recent_builds({"job_name": job, "limit": 10})
                    if output.startswith("Jenkins"):
                        logging.info("Jenkins monitor skipped for job=%s reason=%s", job, output)
                        continue
                    builds = []
                    for line in output.splitlines():
                        kv = _parse_kv_line(line)
                        if "build" not in kv:
                            continue
                        builds.append(kv)
                    if not builds:
                        continue
                    newest = max(int(b.get("build", "0")) for b in builds)
                    previous = int(last_seen.get(job, 0))
                    for build in builds:
                        build_num = int(build.get("build", "0"))
                        if build_num <= previous:
                            continue
                        result = (build.get("result") or "").upper()
                        if result and result not in {"SUCCESS"}:
                            seen_list = seen_failures.get(job, [])
                            seen_set = set(int(x) for x in seen_list if str(x).isdigit())
                            if build_num in seen_set:
                                continue
                            seen_set.add(build_num)
                            seen_failures[job] = sorted(seen_set)[-200:]
                            url = build.get("url", "")
                            _post_channel_message(
                                web_client,
                                JENKINS_ALERT_CHANNEL,
                                f":warning: Jenkins failure job={job} build={build_num} result={result}\n{url}",
                            )
                    last_seen[job] = max(previous, newest)
                with MONITOR_STATE_LOCK:
                    _save_monitor_state(state)
            except Exception as exc:
                logging.exception("Jenkins monitor error: %s", exc)
            time.sleep(max(30, JENKINS_POLL_SECONDS))

    threading.Thread(target=loop, daemon=True, name="jenkins-monitor-worker").start()


def _start_gitlab_worker(web_client: WebClient) -> None:
    if not GITLAB_MONITOR_PROJECTS or not GITLAB_ALERT_CHANNEL:
        logging.info("GitLab monitoring disabled (set GITLAB_MONITOR_PROJECTS and GITLAB_ALERT_CHANNEL).")
        return

    state = _load_monitor_state()

    def loop() -> None:
        logging.info("GitLab monitor worker started projects=%s", GITLAB_MONITOR_PROJECTS)
        while True:
            try:
                with MONITOR_STATE_LOCK:
                    last_seen = _get_state_bucket(state, "gitlab_last_seen")
                    seen_failures = _get_state_bucket(state, "gitlab_failures")
                for project_id in GITLAB_MONITOR_PROJECTS:
                    output = gitlab_recent_pipelines({"project_id": project_id, "limit": 10})
                    if output.startswith("GitLab"):
                        logging.info("GitLab monitor skipped for project=%s reason=%s", project_id, output)
                        continue
                    pipelines = []
                    for line in output.splitlines():
                        kv = _parse_kv_line(line)
                        if "id" not in kv:
                            continue
                        pipelines.append(kv)
                    if not pipelines:
                        continue
                    newest = max(int(p.get("id", "0")) for p in pipelines)
                    previous = int(last_seen.get(project_id, 0))
                    for pipeline in pipelines:
                        pipeline_id = int(pipeline.get("id", "0"))
                        if pipeline_id <= previous:
                            continue
                        status = (pipeline.get("status") or "").lower()
                        if status in {"failed", "canceled"}:
                            seen_list = seen_failures.get(project_id, [])
                            seen_set = set(int(x) for x in seen_list if str(x).isdigit())
                            if pipeline_id in seen_set:
                                continue
                            seen_set.add(pipeline_id)
                            seen_failures[project_id] = sorted(seen_set)[-200:]
                            _post_channel_message(
                                web_client,
                                GITLAB_ALERT_CHANNEL,
                                f":warning: GitLab pipeline failure project={project_id} id={pipeline_id} status={status}",
                            )
                    last_seen[project_id] = max(previous, newest)
                with MONITOR_STATE_LOCK:
                    _save_monitor_state(state)
            except Exception as exc:
                logging.exception("GitLab monitor error: %s", exc)
            time.sleep(max(30, GITLAB_POLL_SECONDS))

    threading.Thread(target=loop, daemon=True, name="gitlab-monitor-worker").start()


def _parse_azdo_pipeline(item: str) -> tuple[str, int] | None:
    if ":" not in item:
        return None
    project, pipeline_raw = item.split(":", 1)
    project = project.strip()
    pipeline_raw = pipeline_raw.strip()
    if not project or not pipeline_raw.isdigit():
        return None
    return project, int(pipeline_raw)


def _start_azdo_worker(web_client: WebClient) -> None:
    if not AZDO_MONITOR_PIPELINES or not AZDO_ALERT_CHANNEL:
        logging.info("Azure DevOps monitoring disabled (set AZDO_MONITOR_PIPELINES and AZDO_ALERT_CHANNEL).")
        return

    state = _load_monitor_state()

    def loop() -> None:
        logging.info("Azure DevOps monitor worker started pipelines=%s", AZDO_MONITOR_PIPELINES)
        while True:
            try:
                with MONITOR_STATE_LOCK:
                    last_seen = _get_state_bucket(state, "azdo_last_seen")
                    seen_failures = _get_state_bucket(state, "azdo_failures")
                for item in AZDO_MONITOR_PIPELINES:
                    parsed = _parse_azdo_pipeline(item)
                    if not parsed:
                        logging.info("Azure DevOps monitor skipped invalid pipeline format=%s", item)
                        continue
                    project, pipeline_id = parsed
                    key = f"{project}:{pipeline_id}"
                    output = azure_devops_recent_runs(
                        {"project": project, "pipeline_id": pipeline_id, "limit": 10}
                    )
                    if output.startswith("Azure DevOps"):
                        logging.info("Azure DevOps monitor skipped key=%s reason=%s", key, output)
                        continue
                    runs = []
                    for line in output.splitlines():
                        kv = _parse_kv_line(line)
                        if "run_id" not in kv:
                            continue
                        runs.append(kv)
                    if not runs:
                        continue
                    newest = max(int(r.get("run_id", "0")) for r in runs)
                    previous = int(last_seen.get(key, 0))
                    for run in runs:
                        run_id = int(run.get("run_id", "0"))
                        if run_id <= previous:
                            continue
                        result = (run.get("result") or "").lower()
                        if result in {"failed", "canceled"}:
                            seen_list = seen_failures.get(key, [])
                            seen_set = set(int(x) for x in seen_list if str(x).isdigit())
                            if run_id in seen_set:
                                continue
                            seen_set.add(run_id)
                            seen_failures[key] = sorted(seen_set)[-200:]
                            _post_channel_message(
                                web_client,
                                AZDO_ALERT_CHANNEL,
                                f":warning: Azure DevOps run failed key={key} run_id={run_id} result={result}",
                            )
                    last_seen[key] = max(previous, newest)
                with MONITOR_STATE_LOCK:
                    _save_monitor_state(state)
            except Exception as exc:
                logging.exception("Azure DevOps monitor error: %s", exc)
            time.sleep(max(30, AZDO_POLL_SECONDS))

    threading.Thread(target=loop, daemon=True, name="azdo-monitor-worker").start()


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
    _start_github_pr_worker(web_client)
    _start_jenkins_worker(web_client)
    _start_gitlab_worker(web_client)
    _start_azdo_worker(web_client)

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
