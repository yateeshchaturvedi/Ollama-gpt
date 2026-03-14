import logging
from typing import Any, Callable

from app.security import (
    audit_tool_call,
    is_confirmation_valid,
    is_rate_limited,
)
from app.tools import (
    azure_devops_run_log,
    azure_devops_recent_runs,
    gitlab_pipeline_log,
    gitlab_recent_pipelines,
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
    jenkins_build_log,
    jenkins_recent_builds,
    read_file,
    run_shell,
    write_file,
)

ToolFunc = Callable[[Any], str]


def build_tool_registry() -> dict[str, ToolFunc]:
    return {
        "run_shell": run_shell,
        "read_file": read_file,
        "write_file": write_file,
        "github_actions_runs": github_actions_runs,
        "github_actions_run_logs": github_actions_run_logs,
        "github_pr_overview": github_pr_overview,
        "github_pr_files": github_pr_files,
        "github_retry_workflow_run": github_retry_workflow_run,
        "github_cancel_workflow_run": github_cancel_workflow_run,
        "github_required_checks_gate": github_required_checks_gate,
        "github_deployment_status": github_deployment_status,
        "github_issue_triage": github_issue_triage,
        "github_security_summary": github_security_summary,
        "github_changelog": github_changelog,
        "github_release_notes_to_pr_comment": github_release_notes_to_pr_comment,
        "github_post_pr_comment": github_post_pr_comment,
        "github_pr_review_suggestions": github_pr_review_suggestions,
        "github_multi_repo_dashboard": github_multi_repo_dashboard,
        "github_daily_digest": github_daily_digest,
        "jenkins_recent_builds": jenkins_recent_builds,
        "jenkins_build_log": jenkins_build_log,
        "azure_devops_recent_runs": azure_devops_recent_runs,
        "azure_devops_run_log": azure_devops_run_log,
        "gitlab_recent_pipelines": gitlab_recent_pipelines,
        "gitlab_pipeline_log": gitlab_pipeline_log,
    }


def execute_tool(tool_name: str, args: dict[str, Any]) -> str:
    """Execute one supported tool with validation."""
    if is_rate_limited():
        audit_tool_call(tool_name, False, "rate_limited", args)
        return "Tool error: rate limit exceeded. Please retry shortly."
    audit_tool_call(tool_name, True, "attempt", args)

    try:
        if tool_name == "run_shell":
            command = args.get("command")
            if not isinstance(command, str) or not command.strip():
                audit_tool_call(tool_name, False, "invalid_command", args)
                return "Tool error: 'command' must be a non-empty string."
            if not is_confirmation_valid(args):
                audit_tool_call(tool_name, False, "missing_confirmation", args)
                return "Tool error: dangerous action confirmation required."
            audit_tool_call(tool_name, True, "ok", args)
            return run_shell(command)

        if tool_name == "read_file":
            path = args.get("path")
            if not isinstance(path, str) or not path.strip():
                audit_tool_call(tool_name, False, "invalid_path", args)
                return "Tool error: 'path' must be a non-empty string."
            audit_tool_call(tool_name, True, "ok", args)
            return read_file(path)

        if tool_name == "write_file":
            path = args.get("path")
            content = args.get("content")
            if not isinstance(path, str) or not path.strip():
                audit_tool_call(tool_name, False, "invalid_path", args)
                return "Tool error: 'path' must be a non-empty string."
            if not isinstance(content, str):
                audit_tool_call(tool_name, False, "invalid_content", args)
                return "Tool error: 'content' must be a string."
            if not is_confirmation_valid(args):
                audit_tool_call(tool_name, False, "missing_confirmation", args)
                return "Tool error: dangerous action confirmation required."
            audit_tool_call(tool_name, True, "ok", args)
            return write_file({"path": path, "content": content})

        if tool_name == "github_actions_runs":
            repo = args.get("repo")
            if not isinstance(repo, str) or not repo.strip():
                return "Tool error: 'repo' must be in 'owner/repo' format."
            per_page = args.get("per_page", 5)
            return github_actions_runs({"repo": repo, "per_page": per_page})

        if tool_name == "github_actions_run_logs":
            repo = args.get("repo")
            run_id = args.get("run_id")
            if not isinstance(repo, str) or not repo.strip():
                return "Tool error: 'repo' must be in 'owner/repo' format."
            if not isinstance(run_id, int):
                return "Tool error: 'run_id' must be an integer."
            return github_actions_run_logs({"repo": repo, "run_id": run_id})

        if tool_name == "github_pr_overview":
            repo = args.get("repo")
            pr_number = args.get("pr_number")
            if not isinstance(repo, str) or not repo.strip():
                return "Tool error: 'repo' must be in 'owner/repo' format."
            if not isinstance(pr_number, int):
                return "Tool error: 'pr_number' must be an integer."
            return github_pr_overview({"repo": repo, "pr_number": pr_number})

        if tool_name == "github_pr_files":
            repo = args.get("repo")
            pr_number = args.get("pr_number")
            limit = args.get("limit", 20)
            if not isinstance(repo, str) or not repo.strip():
                return "Tool error: 'repo' must be in 'owner/repo' format."
            if not isinstance(pr_number, int):
                return "Tool error: 'pr_number' must be an integer."
            if not isinstance(limit, int):
                return "Tool error: 'limit' must be an integer."
            return github_pr_files({"repo": repo, "pr_number": pr_number, "limit": limit})

        if tool_name in {"github_retry_workflow_run", "github_cancel_workflow_run"}:
            repo = args.get("repo")
            run_id = args.get("run_id")
            if not isinstance(repo, str) or not repo.strip():
                return "Tool error: 'repo' must be in 'owner/repo' format."
            if not isinstance(run_id, int):
                return "Tool error: 'run_id' must be an integer."
            if tool_name == "github_retry_workflow_run":
                return github_retry_workflow_run({"repo": repo, "run_id": run_id})
            return github_cancel_workflow_run({"repo": repo, "run_id": run_id})

        if tool_name == "github_required_checks_gate":
            repo = args.get("repo")
            pr_number = args.get("pr_number")
            if not isinstance(repo, str) or not repo.strip():
                return "Tool error: 'repo' must be in 'owner/repo' format."
            if not isinstance(pr_number, int):
                return "Tool error: 'pr_number' must be an integer."
            return github_required_checks_gate({"repo": repo, "pr_number": pr_number})

        if tool_name in {"github_deployment_status", "github_issue_triage", "github_security_summary"}:
            repo = args.get("repo")
            per_page = args.get("per_page", 20)
            if not isinstance(repo, str) or not repo.strip():
                return "Tool error: 'repo' must be in 'owner/repo' format."
            if not isinstance(per_page, int):
                return "Tool error: 'per_page' must be an integer."
            if tool_name == "github_deployment_status":
                return github_deployment_status({"repo": repo, "per_page": per_page})
            if tool_name == "github_issue_triage":
                return github_issue_triage({"repo": repo, "per_page": per_page})
            return github_security_summary({"repo": repo, "per_page": per_page})

        if tool_name in {"github_changelog", "github_release_notes_to_pr_comment"}:
            repo = args.get("repo")
            base = args.get("base")
            head = args.get("head")
            if not isinstance(repo, str) or not repo.strip():
                return "Tool error: 'repo' must be in 'owner/repo' format."
            if not isinstance(base, str) or not isinstance(head, str):
                return "Tool error: 'base' and 'head' must be strings."
            if tool_name == "github_changelog":
                return github_changelog({"repo": repo, "base": base, "head": head})
            pr_number = args.get("pr_number")
            if not isinstance(pr_number, int):
                return "Tool error: 'pr_number' must be an integer."
            return github_release_notes_to_pr_comment(
                {"repo": repo, "pr_number": pr_number, "base": base, "head": head}
            )

        if tool_name == "github_post_pr_comment":
            repo = args.get("repo")
            pr_number = args.get("pr_number")
            body = args.get("body")
            if not isinstance(repo, str) or not repo.strip():
                return "Tool error: 'repo' must be in 'owner/repo' format."
            if not isinstance(pr_number, int):
                return "Tool error: 'pr_number' must be an integer."
            if not isinstance(body, str) or not body.strip():
                return "Tool error: 'body' must be a non-empty string."
            return github_post_pr_comment({"repo": repo, "pr_number": pr_number, "body": body})

        if tool_name == "github_pr_review_suggestions":
            repo = args.get("repo")
            pr_number = args.get("pr_number")
            limit = args.get("limit", 20)
            if not isinstance(repo, str) or not repo.strip():
                return "Tool error: 'repo' must be in 'owner/repo' format."
            if not isinstance(pr_number, int):
                return "Tool error: 'pr_number' must be an integer."
            if not isinstance(limit, int):
                return "Tool error: 'limit' must be an integer."
            return github_pr_review_suggestions({"repo": repo, "pr_number": pr_number, "limit": limit})

        if tool_name in {"github_multi_repo_dashboard", "github_daily_digest"}:
            repos = args.get("repos")
            if not isinstance(repos, (list, str)):
                return "Tool error: 'repos' must be a list or comma-separated string."
            if tool_name == "github_multi_repo_dashboard":
                return github_multi_repo_dashboard({"repos": repos})
            return github_daily_digest({"repos": repos})

        if tool_name == "jenkins_recent_builds":
            job_name = args.get("job_name")
            limit = args.get("limit", 10)
            if not isinstance(job_name, str) or not job_name.strip():
                return "Tool error: 'job_name' must be a non-empty string."
            if not isinstance(limit, int):
                return "Tool error: 'limit' must be an integer."
            return jenkins_recent_builds({"job_name": job_name, "limit": limit})

        if tool_name == "jenkins_build_log":
            job_name = args.get("job_name")
            build_number = args.get("build_number")
            max_chars = args.get("max_chars", 8000)
            if not isinstance(job_name, str) or not job_name.strip():
                return "Tool error: 'job_name' must be a non-empty string."
            if not isinstance(build_number, int):
                return "Tool error: 'build_number' must be an integer."
            if not isinstance(max_chars, int):
                return "Tool error: 'max_chars' must be an integer."
            return jenkins_build_log(
                {"job_name": job_name, "build_number": build_number, "max_chars": max_chars}
            )

        if tool_name == "azure_devops_recent_runs":
            project = args.get("project")
            pipeline_id = args.get("pipeline_id")
            limit = args.get("limit", 10)
            if not isinstance(project, str) or not project.strip():
                return "Tool error: 'project' must be a non-empty string."
            if not isinstance(pipeline_id, int):
                return "Tool error: 'pipeline_id' must be an integer."
            if not isinstance(limit, int):
                return "Tool error: 'limit' must be an integer."
            return azure_devops_recent_runs(
                {"project": project, "pipeline_id": pipeline_id, "limit": limit}
            )

        if tool_name == "azure_devops_run_log":
            project = args.get("project")
            pipeline_id = args.get("pipeline_id")
            run_id = args.get("run_id")
            max_chars = args.get("max_chars", 10000)
            if not isinstance(project, str) or not project.strip():
                return "Tool error: 'project' must be a non-empty string."
            if not isinstance(pipeline_id, int):
                return "Tool error: 'pipeline_id' must be an integer."
            if not isinstance(run_id, int):
                return "Tool error: 'run_id' must be an integer."
            if not isinstance(max_chars, int):
                return "Tool error: 'max_chars' must be an integer."
            return azure_devops_run_log(
                {
                    "project": project,
                    "pipeline_id": pipeline_id,
                    "run_id": run_id,
                    "max_chars": max_chars,
                }
            )

        if tool_name == "gitlab_recent_pipelines":
            project_id = args.get("project_id")
            limit = args.get("limit", 10)
            if not isinstance(project_id, str) or not project_id.strip():
                return "Tool error: 'project_id' must be a non-empty string."
            if not isinstance(limit, int):
                return "Tool error: 'limit' must be an integer."
            return gitlab_recent_pipelines({"project_id": project_id, "limit": limit})

        if tool_name == "gitlab_pipeline_log":
            project_id = args.get("project_id")
            pipeline_id = args.get("pipeline_id")
            max_chars = args.get("max_chars", 10000)
            if not isinstance(project_id, str) or not project_id.strip():
                return "Tool error: 'project_id' must be a non-empty string."
            if not isinstance(pipeline_id, int):
                return "Tool error: 'pipeline_id' must be an integer."
            if not isinstance(max_chars, int):
                return "Tool error: 'max_chars' must be an integer."
            return gitlab_pipeline_log(
                {"project_id": project_id, "pipeline_id": pipeline_id, "max_chars": max_chars}
            )
    except Exception as exc:
        audit_tool_call(tool_name, False, f"exception:{type(exc).__name__}", args)
        logging.exception("Unexpected tool execution error: %s", exc)
        return f"Tool error: unexpected exception: {exc}"

    return f"Tool error: unknown tool '{tool_name}'."
