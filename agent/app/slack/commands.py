"""Slack slash command handlers.

Handles: /models, /model, /gh and all GitHub sub-commands.
Each handler returns a string reply; posting is done by the caller.
"""
from __future__ import annotations

import logging

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
)
from app.slack.utils import list_ollama_models


# ── /models ───────────────────────────────────────────────────────────────────

def handle_models_command() -> str:
    names = list_ollama_models()
    if not names:
        return "No models found or unable to fetch model list from Ollama."
    return "Available models:\n- " + "\n- ".join(names)


# ── /model ────────────────────────────────────────────────────────────────────

def handle_model_command(
    user_prompt: str,
    conversation_key: str,
    model_selection: dict[str, str],
    default_model: str,
) -> str:
    parts = user_prompt.split(maxsplit=1)
    if len(parts) == 1:
        current = model_selection[conversation_key]
        return f"Current model for this thread: `{current}`"
    requested_model = parts[1].strip()
    if requested_model.lower() == "reset":
        model_selection[conversation_key] = default_model
        return f"Model reset. Using default model `{default_model}` for this thread."
    model_selection[conversation_key] = requested_model
    return f"Model set to `{requested_model}` for this thread."


# ── /gh ───────────────────────────────────────────────────────────────────────

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


def handle_github_command(user_prompt: str) -> str | None:
    """Handle a /gh command.

    Returns the reply string, or None if the input is not a /gh command.
    """
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
