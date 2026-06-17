"""Tool registry and dispatcher.

Each tool is described by a ToolDescriptor that captures its metadata.
execute_tool() is a single generic dispatcher — no per-tool if-blocks.

Adding a new tool requires only:
  1. Implement the function in app/tools/
  2. Add a ToolDescriptor to TOOL_REGISTRY below.
  3. Export it from app/tools/__init__.py.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from app.security import (
    audit_tool_call,
    is_confirmation_valid,
    is_rate_limited,
    truncate_shell_output,
)
from app.tools import (
    azure_devops_recent_runs,
    azure_devops_run_log,
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
    gitlab_pipeline_log,
    gitlab_recent_pipelines,
    jenkins_build_log,
    jenkins_recent_builds,
    read_file,
    run_shell,
    write_file,
)

# ── Descriptor ────────────────────────────────────────────────────────────────


@dataclass
class ToolDescriptor:
    """Declarative description of a single agent tool.

    Attributes:
        name:               Tool identifier used in JSON protocol.
        fn:                 Callable that accepts a validated ``args`` dict
                            and returns a string result.
        required_str:       Arg names that must be non-empty strings.
        required_int:       Arg names that must be integers.
        required_str_any:   Arg names that must be strings (may be empty).
        required_list_or_str: Arg names that must be a list or non-empty str.
        optional_args:      Mapping of optional arg name → default value.
        needs_confirmation: Whether the ``confirmation`` token is required.
        description:        Human-readable summary (used for schema generation).
    """

    name: str
    fn: Callable[[dict[str, Any]], str]
    required_str: list[str] = field(default_factory=list)
    required_int: list[str] = field(default_factory=list)
    required_str_any: list[str] = field(default_factory=list)
    required_list_or_str: list[str] = field(default_factory=list)
    optional_args: dict[str, Any] = field(default_factory=dict)
    needs_confirmation: bool = False
    description: str = ""


# ── Registry ──────────────────────────────────────────────────────────────────

TOOL_REGISTRY: dict[str, ToolDescriptor] = {
    # ── Local ───────────────────────────────────────────────────────────────
    "run_shell": ToolDescriptor(
        name="run_shell",
        fn=lambda a: run_shell(a["command"]),
        required_str=["command"],
        needs_confirmation=True,
        description="Run a shell command and return stdout/stderr (allowlist-restricted).",
    ),
    "read_file": ToolDescriptor(
        name="read_file",
        fn=lambda a: read_file(a["path"]),
        required_str=["path"],
        description="Read a UTF-8 text file within the workspace.",
    ),
    "write_file": ToolDescriptor(
        name="write_file",
        fn=lambda a: write_file(a),
        required_str=["path"],
        required_str_any=["content"],
        needs_confirmation=True,
        description="Write UTF-8 text content to a file within the workspace.",
    ),
    # ── GitHub ───────────────────────────────────────────────────────────────
    "github_actions_runs": ToolDescriptor(
        name="github_actions_runs",
        fn=github_actions_runs,
        required_str=["repo"],
        optional_args={"per_page": 5},
        description="List recent GitHub Actions workflow runs for a repository.",
    ),
    "github_actions_run_logs": ToolDescriptor(
        name="github_actions_run_logs",
        fn=github_actions_run_logs,
        required_str=["repo"],
        required_int=["run_id"],
        description="Fetch logs for a specific GitHub Actions run.",
    ),
    "github_pr_overview": ToolDescriptor(
        name="github_pr_overview",
        fn=github_pr_overview,
        required_str=["repo"],
        required_int=["pr_number"],
        description="Get an overview of a GitHub pull request.",
    ),
    "github_pr_files": ToolDescriptor(
        name="github_pr_files",
        fn=github_pr_files,
        required_str=["repo"],
        required_int=["pr_number"],
        optional_args={"limit": 20},
        description="List files changed in a GitHub pull request.",
    ),
    "github_retry_workflow_run": ToolDescriptor(
        name="github_retry_workflow_run",
        fn=github_retry_workflow_run,
        required_str=["repo"],
        required_int=["run_id"],
        description="Retry a failed GitHub Actions workflow run.",
    ),
    "github_cancel_workflow_run": ToolDescriptor(
        name="github_cancel_workflow_run",
        fn=github_cancel_workflow_run,
        required_str=["repo"],
        required_int=["run_id"],
        description="Cancel an in-progress GitHub Actions workflow run.",
    ),
    "github_required_checks_gate": ToolDescriptor(
        name="github_required_checks_gate",
        fn=github_required_checks_gate,
        required_str=["repo"],
        required_int=["pr_number"],
        description="Check if all required status checks pass for a pull request.",
    ),
    "github_deployment_status": ToolDescriptor(
        name="github_deployment_status",
        fn=github_deployment_status,
        required_str=["repo"],
        optional_args={"per_page": 20},
        description="List recent deployment statuses for a repository.",
    ),
    "github_issue_triage": ToolDescriptor(
        name="github_issue_triage",
        fn=github_issue_triage,
        required_str=["repo"],
        optional_args={"per_page": 20},
        description="List open issues in a repository for triage.",
    ),
    "github_security_summary": ToolDescriptor(
        name="github_security_summary",
        fn=github_security_summary,
        required_str=["repo"],
        optional_args={"per_page": 20},
        description="Summarize Dependabot and security alerts for a repository.",
    ),
    "github_changelog": ToolDescriptor(
        name="github_changelog",
        fn=github_changelog,
        required_str=["repo", "base", "head"],
        description="Generate a changelog between two Git refs.",
    ),
    "github_release_notes_to_pr_comment": ToolDescriptor(
        name="github_release_notes_to_pr_comment",
        fn=github_release_notes_to_pr_comment,
        required_str=["repo", "base", "head"],
        required_int=["pr_number"],
        description="Post release notes as a PR comment.",
    ),
    "github_post_pr_comment": ToolDescriptor(
        name="github_post_pr_comment",
        fn=github_post_pr_comment,
        required_str=["repo", "body"],
        required_int=["pr_number"],
        description="Post a comment on a GitHub pull request.",
    ),
    "github_pr_review_suggestions": ToolDescriptor(
        name="github_pr_review_suggestions",
        fn=github_pr_review_suggestions,
        required_str=["repo"],
        required_int=["pr_number"],
        optional_args={"limit": 20},
        description="Fetch AI-friendly review suggestion data for a pull request.",
    ),
    "github_multi_repo_dashboard": ToolDescriptor(
        name="github_multi_repo_dashboard",
        fn=github_multi_repo_dashboard,
        required_list_or_str=["repos"],
        description="Summarise health across multiple GitHub repositories.",
    ),
    "github_daily_digest": ToolDescriptor(
        name="github_daily_digest",
        fn=github_daily_digest,
        required_list_or_str=["repos"],
        description="Generate a daily digest for multiple GitHub repositories.",
    ),
    # ── Jenkins ──────────────────────────────────────────────────────────────
    "jenkins_recent_builds": ToolDescriptor(
        name="jenkins_recent_builds",
        fn=jenkins_recent_builds,
        required_str=["job_name"],
        optional_args={"limit": 10},
        description="List recent Jenkins builds for a job.",
    ),
    "jenkins_build_log": ToolDescriptor(
        name="jenkins_build_log",
        fn=jenkins_build_log,
        required_str=["job_name"],
        required_int=["build_number"],
        optional_args={"max_chars": 8_000},
        description="Fetch the console log of a Jenkins build.",
    ),
    # ── Azure DevOps ─────────────────────────────────────────────────────────
    "azure_devops_recent_runs": ToolDescriptor(
        name="azure_devops_recent_runs",
        fn=azure_devops_recent_runs,
        required_str=["project"],
        required_int=["pipeline_id"],
        optional_args={"limit": 10},
        description="List recent Azure DevOps pipeline runs.",
    ),
    "azure_devops_run_log": ToolDescriptor(
        name="azure_devops_run_log",
        fn=azure_devops_run_log,
        required_str=["project"],
        required_int=["pipeline_id", "run_id"],
        optional_args={"max_chars": 10_000},
        description="Fetch the log of an Azure DevOps pipeline run.",
    ),
    # ── GitLab ───────────────────────────────────────────────────────────────
    "gitlab_recent_pipelines": ToolDescriptor(
        name="gitlab_recent_pipelines",
        fn=gitlab_recent_pipelines,
        required_str=["project_id"],
        optional_args={"limit": 10},
        description="List recent GitLab CI pipelines for a project.",
    ),
    "gitlab_pipeline_log": ToolDescriptor(
        name="gitlab_pipeline_log",
        fn=gitlab_pipeline_log,
        required_str=["project_id"],
        required_int=["pipeline_id"],
        optional_args={"max_chars": 10_000},
        description="Fetch the log of a GitLab CI pipeline.",
    ),
}


# ── Validation helpers ────────────────────────────────────────────────────────


def _validate_args(descriptor: ToolDescriptor, args: dict[str, Any]) -> str | None:
    """Validate *args* against the descriptor rules.

    Returns an error string on failure, or None if valid.
    """
    # Non-empty string args
    for name in descriptor.required_str:
        value = args.get(name)
        if not isinstance(value, str) or not value.strip():
            return f"Tool error: '{name}' must be a non-empty string."

    # Integer args
    for name in descriptor.required_int:
        value = args.get(name)
        if not isinstance(value, int):
            return f"Tool error: '{name}' must be an integer."

    # Any-string args (may be empty, e.g. file content)
    for name in descriptor.required_str_any:
        value = args.get(name)
        if not isinstance(value, str):
            return f"Tool error: '{name}' must be a string."

    # List-or-string args
    for name in descriptor.required_list_or_str:
        value = args.get(name)
        if not isinstance(value, (list, str)):
            return f"Tool error: '{name}' must be a list or comma-separated string."

    return None


def _build_call_args(descriptor: ToolDescriptor, args: dict[str, Any]) -> dict[str, Any]:
    """Merge validated required args with optional defaults."""
    call_args: dict[str, Any] = {}
    # Start with optional defaults
    call_args.update(descriptor.optional_args)
    # Override with any provided values (required + any provided optional)
    call_args.update(args)
    return call_args


# ── Public API ────────────────────────────────────────────────────────────────


def build_tool_registry() -> dict[str, ToolDescriptor]:
    """Return the tool registry.

    Callers that only need tool names can call `registry.keys()`.
    Callers that need to dispatch use `execute_tool()`.
    """
    return TOOL_REGISTRY


def execute_tool(tool_name: str, args: dict[str, Any]) -> str:
    """Execute one supported tool with full validation, rate-limiting and audit."""

    # ── Rate limit ────────────────────────────────────────────────────────────
    if is_rate_limited():
        audit_tool_call(tool_name, False, "rate_limited", args)
        return "Tool error: rate limit exceeded. Please retry shortly."

    # ── Lookup ────────────────────────────────────────────────────────────────
    descriptor = TOOL_REGISTRY.get(tool_name)
    if descriptor is None:
        audit_tool_call(tool_name, False, "unknown_tool", args)
        return f"Tool error: unknown tool '{tool_name}'."

    audit_tool_call(tool_name, True, "attempt", args)
    logging.info("Executing tool '%s' with arg keys=%s", tool_name, sorted(args.keys()))

    try:
        # ── Validate args ─────────────────────────────────────────────────────
        error = _validate_args(descriptor, args)
        if error:
            audit_tool_call(tool_name, False, "invalid_args", args)
            return error

        # ── Confirmation check ────────────────────────────────────────────────
        if descriptor.needs_confirmation and not is_confirmation_valid(args):
            audit_tool_call(tool_name, False, "missing_confirmation", args)
            return "Tool error: dangerous action confirmation required."

        # ── Dispatch ──────────────────────────────────────────────────────────
        call_args = _build_call_args(descriptor, args)
        audit_tool_call(tool_name, True, "ok", args)
        result = descriptor.fn(call_args)

        # ── Shell output guard ────────────────────────────────────────────────
        if tool_name == "run_shell":
            result = truncate_shell_output(result)

        return result

    except Exception as exc:
        audit_tool_call(tool_name, False, f"exception:{type(exc).__name__}", args)
        logging.exception("Unexpected tool execution error for '%s': %s", tool_name, exc)
        return f"Tool error: unexpected exception: {exc}"
