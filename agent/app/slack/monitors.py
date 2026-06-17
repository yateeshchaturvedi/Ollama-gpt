"""Background CI/CD monitor workers for the Slack bot.

Each worker runs as a daemon thread and posts failure alerts to Slack
channels when new failures are detected. Workers persist dedup state to
MONITOR_STATE_PATH so alerts are not re-sent after a restart.

Workers started:
  - GitHub Actions failure alerts
  - GitHub daily digest (scheduled)
  - GitHub PR new-PR notifications
  - Jenkins build failure alerts
  - GitLab pipeline failure alerts
  - Azure DevOps pipeline failure alerts
"""
from __future__ import annotations

import logging
import os
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta

from slack_sdk import WebClient

from app.tools import (
    azure_devops_recent_runs,
    github_actions_run_logs,
    github_actions_runs,
    github_daily_digest,
    gitlab_recent_pipelines,
    jenkins_recent_builds,
)
from app.tools.github_tools import github_list_open_prs
from app.slack.utils import (
    MONITOR_STATE_LOCK,
    get_state_bucket,
    load_monitor_state,
    parse_failed_run_ids,
    parse_kv_line,
    post_channel_message,
    save_monitor_state,
    update_seen_ids,
)

# ── Environment config ────────────────────────────────────────────────────────

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


# ── GitHub Actions failure alerts ─────────────────────────────────────────────

def start_failure_alert_worker(web_client: WebClient) -> None:
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
                    for run_id in parse_failed_run_ids(runs_output):
                        if run_id in seen_failures[repo]:
                            continue
                        seen_failures[repo].add(run_id)
                        details = github_actions_run_logs({"repo": repo, "run_id": run_id})
                        post_channel_message(
                            web_client,
                            GITHUB_ALERT_CHANNEL,
                            f":rotating_light: Workflow failure detected in {repo}\n{details}",
                        )
            except Exception as exc:
                logging.exception("Failure alert worker error: %s", exc)
            time.sleep(max(30, GITHUB_ALERT_POLL_SECONDS))

    threading.Thread(target=loop, daemon=True, name="github-failure-alert-worker").start()


# ── GitHub daily digest ────────────────────────────────────────────────────────

def start_daily_digest_worker(web_client: WebClient) -> None:
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
                    post_channel_message(web_client, GITHUB_DIGEST_CHANNEL, digest)
                    last_sent_date.add(date_key)
            except Exception as exc:
                logging.exception("Digest worker error: %s", exc)
            time.sleep(30)

    threading.Thread(target=loop, daemon=True, name="github-digest-worker").start()


# ── GitHub PR new-PR notifications ────────────────────────────────────────────

def start_github_pr_worker(web_client: WebClient) -> None:
    repos = GITHUB_PR_MONITOR_REPOS or GITHUB_MONITOR_REPOS
    channel = GITHUB_PR_ALERT_CHANNEL or GITHUB_ALERT_CHANNEL
    if not repos or not channel:
        logging.info("GitHub PR monitoring disabled (set GITHUB_PR_MONITOR_REPOS and GITHUB_PR_ALERT_CHANNEL).")
        return

    state = load_monitor_state()

    def loop() -> None:
        logging.info("GitHub PR monitor worker started repos=%s", repos)
        while True:
            try:
                with MONITOR_STATE_LOCK:
                    bucket = get_state_bucket(state, "github_prs")
                for repo in repos:
                    prs = github_list_open_prs(repo, per_page=20)
                    if not prs:
                        continue
                    seen_list = bucket.get(repo, [])
                    seen = {int(x) for x in seen_list if str(x).isdigit()}
                    new_seen: set[int] = set()
                    for pr in prs:
                        number = pr.get("number")
                        if not isinstance(number, int) or number in seen:
                            continue
                        new_seen.add(number)
                        title = pr.get("title") or ""
                        author = ((pr.get("user") or {}).get("login")) or "unknown"
                        url = pr.get("html_url") or ""
                        post_channel_message(
                            web_client,
                            channel,
                            f":sparkles: New PR in {repo} #{number} by {author}\n{title}\n{url}",
                        )
                    if new_seen:
                        with MONITOR_STATE_LOCK:
                            update_seen_ids(bucket, repo, new_seen)
                            save_monitor_state(state)
            except Exception as exc:
                logging.exception("GitHub PR monitor error: %s", exc)
            time.sleep(max(30, GITHUB_PR_POLL_SECONDS))

    threading.Thread(target=loop, daemon=True, name="github-pr-monitor-worker").start()


# ── Jenkins failure alerts ────────────────────────────────────────────────────

def start_jenkins_worker(web_client: WebClient) -> None:
    if not JENKINS_MONITOR_JOBS or not JENKINS_ALERT_CHANNEL:
        logging.info("Jenkins monitoring disabled (set JENKINS_MONITOR_JOBS and JENKINS_ALERT_CHANNEL).")
        return

    state = load_monitor_state()

    def loop() -> None:
        logging.info("Jenkins monitor worker started jobs=%s", JENKINS_MONITOR_JOBS)
        while True:
            try:
                with MONITOR_STATE_LOCK:
                    last_seen = get_state_bucket(state, "jenkins_last_seen")
                    seen_failures = get_state_bucket(state, "jenkins_failures")
                for job in JENKINS_MONITOR_JOBS:
                    output = jenkins_recent_builds({"job_name": job, "limit": 10})
                    if output.startswith("Jenkins"):
                        logging.info("Jenkins monitor skipped for job=%s reason=%s", job, output)
                        continue
                    builds = []
                    for line in output.splitlines():
                        kv = parse_kv_line(line)
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
                            seen_set = {int(x) for x in seen_list if str(x).isdigit()}
                            if build_num in seen_set:
                                continue
                            seen_set.add(build_num)
                            seen_failures[job] = sorted(seen_set)[-200:]
                            url = build.get("url", "")
                            post_channel_message(
                                web_client,
                                JENKINS_ALERT_CHANNEL,
                                f":warning: Jenkins failure job={job} build={build_num} result={result}\n{url}",
                            )
                    last_seen[job] = max(previous, newest)
                with MONITOR_STATE_LOCK:
                    save_monitor_state(state)
            except Exception as exc:
                logging.exception("Jenkins monitor error: %s", exc)
            time.sleep(max(30, JENKINS_POLL_SECONDS))

    threading.Thread(target=loop, daemon=True, name="jenkins-monitor-worker").start()


# ── GitLab failure alerts ─────────────────────────────────────────────────────

def start_gitlab_worker(web_client: WebClient) -> None:
    if not GITLAB_MONITOR_PROJECTS or not GITLAB_ALERT_CHANNEL:
        logging.info("GitLab monitoring disabled (set GITLAB_MONITOR_PROJECTS and GITLAB_ALERT_CHANNEL).")
        return

    state = load_monitor_state()

    def loop() -> None:
        logging.info("GitLab monitor worker started projects=%s", GITLAB_MONITOR_PROJECTS)
        while True:
            try:
                with MONITOR_STATE_LOCK:
                    last_seen = get_state_bucket(state, "gitlab_last_seen")
                    seen_failures = get_state_bucket(state, "gitlab_failures")
                for project_id in GITLAB_MONITOR_PROJECTS:
                    output = gitlab_recent_pipelines({"project_id": project_id, "limit": 10})
                    if output.startswith("GitLab"):
                        logging.info("GitLab monitor skipped for project=%s reason=%s", project_id, output)
                        continue
                    pipelines = []
                    for line in output.splitlines():
                        kv = parse_kv_line(line)
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
                            seen_set = {int(x) for x in seen_list if str(x).isdigit()}
                            if pipeline_id in seen_set:
                                continue
                            seen_set.add(pipeline_id)
                            seen_failures[project_id] = sorted(seen_set)[-200:]
                            post_channel_message(
                                web_client,
                                GITLAB_ALERT_CHANNEL,
                                f":warning: GitLab pipeline failure project={project_id} id={pipeline_id} status={status}",
                            )
                    last_seen[project_id] = max(previous, newest)
                with MONITOR_STATE_LOCK:
                    save_monitor_state(state)
            except Exception as exc:
                logging.exception("GitLab monitor error: %s", exc)
            time.sleep(max(30, GITLAB_POLL_SECONDS))

    threading.Thread(target=loop, daemon=True, name="gitlab-monitor-worker").start()


# ── Azure DevOps failure alerts ───────────────────────────────────────────────

def _parse_azdo_pipeline(item: str) -> tuple[str, int] | None:
    if ":" not in item:
        return None
    project, pipeline_raw = item.split(":", 1)
    project = project.strip()
    pipeline_raw = pipeline_raw.strip()
    if not project or not pipeline_raw.isdigit():
        return None
    return project, int(pipeline_raw)


def start_azdo_worker(web_client: WebClient) -> None:
    if not AZDO_MONITOR_PIPELINES or not AZDO_ALERT_CHANNEL:
        logging.info("Azure DevOps monitoring disabled (set AZDO_MONITOR_PIPELINES and AZDO_ALERT_CHANNEL).")
        return

    state = load_monitor_state()

    def loop() -> None:
        logging.info("Azure DevOps monitor worker started pipelines=%s", AZDO_MONITOR_PIPELINES)
        while True:
            try:
                with MONITOR_STATE_LOCK:
                    last_seen = get_state_bucket(state, "azdo_last_seen")
                    seen_failures = get_state_bucket(state, "azdo_failures")
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
                        kv = parse_kv_line(line)
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
                            seen_set = {int(x) for x in seen_list if str(x).isdigit()}
                            if run_id in seen_set:
                                continue
                            seen_set.add(run_id)
                            seen_failures[key] = sorted(seen_set)[-200:]
                            post_channel_message(
                                web_client,
                                AZDO_ALERT_CHANNEL,
                                f":warning: Azure DevOps run failed key={key} run_id={run_id} result={result}",
                            )
                    last_seen[key] = max(previous, newest)
                with MONITOR_STATE_LOCK:
                    save_monitor_state(state)
            except Exception as exc:
                logging.exception("Azure DevOps monitor error: %s", exc)
            time.sleep(max(30, AZDO_POLL_SECONDS))

    threading.Thread(target=loop, daemon=True, name="azdo-monitor-worker").start()


# ── Public entry point ────────────────────────────────────────────────────────

def start_all_monitors(web_client: WebClient) -> None:
    """Start all 6 CI/CD background monitor workers."""
    start_failure_alert_worker(web_client)
    start_daily_digest_worker(web_client)
    start_github_pr_worker(web_client)
    start_jenkins_worker(web_client)
    start_gitlab_worker(web_client)
    start_azdo_worker(web_client)
