import json
import os
from typing import Any, TypedDict

import requests


class GitHubPayload(TypedDict, total=False):
    repo: str
    run_id: int
    pr_number: int
    per_page: int
    limit: int


def _parse_repo(repo: str) -> tuple[str, str]:
    if "/" not in repo:
        raise ValueError("repo must be in 'owner/repo' format.")
    owner, name = repo.split("/", 1)
    if not owner or not name:
        raise ValueError("repo must be in 'owner/repo' format.")
    return owner, name


def _github_request(
    method: str,
    endpoint: str,
    params: dict | None = None,
    json_body: dict | None = None,
) -> Any:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not token:
        raise RuntimeError("GITHUB_TOKEN is not set.")

    base_url = os.getenv("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    url = f"{base_url}{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    response = requests.request(
        method,
        url,
        headers=headers,
        params=params,
        json=json_body,
        timeout=30,
    )
    response.raise_for_status()
    if response.status_code == 204:
        return {}
    if not response.content:
        return {}
    return response.json()


def github_actions_runs(data: GitHubPayload) -> str:
    try:
        repo = data.get("repo", "")
        per_page = int(data.get("per_page", 5))
        owner, name = _parse_repo(repo)
        payload = _github_request(
            "GET",
            f"/repos/{owner}/{name}/actions/runs",
            params={"per_page": per_page},
        )
        runs = payload.get("workflow_runs", [])
        if not runs:
            return "No workflow runs found."

        lines = []
        for run in runs[:per_page]:
            lines.append(
                (
                    f"id={run.get('id')} name={run.get('name')} "
                    f"status={run.get('status')} conclusion={run.get('conclusion')} "
                    f"branch={run.get('head_branch')} event={run.get('event')} "
                    f"created_at={run.get('created_at')}"
                )
            )
        return "\n".join(lines)
    except requests.HTTPError as exc:
        return f"GitHub API HTTP error while listing runs: {exc}"
    except (ValueError, RuntimeError) as exc:
        return f"GitHub runs error: {exc}"
    except Exception as exc:
        return f"Unexpected GitHub runs error: {exc}"


def github_actions_run_logs(data: GitHubPayload) -> str:
    try:
        repo = data.get("repo", "")
        run_id = int(data.get("run_id", 0))
        owner, name = _parse_repo(repo)
        if run_id <= 0:
            return "run_id must be a positive integer."

        run = _github_request("GET", f"/repos/{owner}/{name}/actions/runs/{run_id}")
        jobs = _github_request("GET", f"/repos/{owner}/{name}/actions/runs/{run_id}/jobs")
        lines = [
            (
                f"run_id={run.get('id')} status={run.get('status')} "
                f"conclusion={run.get('conclusion')} html_url={run.get('html_url')}"
            )
        ]
        for job in jobs.get("jobs", []):
            lines.append(
                (
                    f"job={job.get('name')} status={job.get('status')} "
                    f"conclusion={job.get('conclusion')} started_at={job.get('started_at')}"
                )
            )
            for step in job.get("steps", []):
                if step.get("conclusion") == "failure":
                    lines.append(f"  failed_step={step.get('name')}")
        return "\n".join(lines)
    except requests.HTTPError as exc:
        return f"GitHub API HTTP error while fetching run logs: {exc}"
    except (ValueError, RuntimeError) as exc:
        return f"GitHub run logs error: {exc}"
    except Exception as exc:
        return f"Unexpected GitHub run logs error: {exc}"


def github_pr_overview(data: GitHubPayload) -> str:
    try:
        repo = data.get("repo", "")
        pr_number = int(data.get("pr_number", 0))
        owner, name = _parse_repo(repo)
        if pr_number <= 0:
            return "pr_number must be a positive integer."

        pr = _github_request("GET", f"/repos/{owner}/{name}/pulls/{pr_number}")
        reviews = _github_request("GET", f"/repos/{owner}/{name}/pulls/{pr_number}/reviews")

        review_states = {}
        for review in reviews:
            user = (review.get("user") or {}).get("login", "unknown")
            review_states[user] = review.get("state")

        lines = [
            f"title={pr.get('title')}",
            f"state={pr.get('state')} draft={pr.get('draft')}",
            f"author={(pr.get('user') or {}).get('login')}",
            f"base={((pr.get('base') or {}).get('ref'))} head={((pr.get('head') or {}).get('ref'))}",
            f"mergeable={pr.get('mergeable')} mergeable_state={pr.get('mergeable_state')}",
            f"additions={pr.get('additions')} deletions={pr.get('deletions')} changed_files={pr.get('changed_files')}",
        ]
        if review_states:
            lines.append("review_states=" + json.dumps(review_states, ensure_ascii=True))
        return "\n".join(lines)
    except requests.HTTPError as exc:
        return f"GitHub API HTTP error while fetching PR overview: {exc}"
    except (ValueError, RuntimeError) as exc:
        return f"GitHub PR overview error: {exc}"
    except Exception as exc:
        return f"Unexpected GitHub PR overview error: {exc}"


def github_pr_files(data: GitHubPayload) -> str:
    try:
        repo = data.get("repo", "")
        pr_number = int(data.get("pr_number", 0))
        limit = int(data.get("limit", 20))
        owner, name = _parse_repo(repo)
        if pr_number <= 0:
            return "pr_number must be a positive integer."
        if limit <= 0:
            return "limit must be a positive integer."

        files = _github_request(
            "GET",
            f"/repos/{owner}/{name}/pulls/{pr_number}/files",
            params={"per_page": min(limit, 100)},
        )
        if not isinstance(files, list):
            return "No PR files found."

        lines = []
        for item in files[:limit]:
            patch = item.get("patch", "")
            if patch and len(patch) > 1200:
                patch = patch[:1200] + "\n...<truncated>..."
            lines.append(
                (
                    f"file={item.get('filename')} status={item.get('status')} "
                    f"additions={item.get('additions')} deletions={item.get('deletions')}\n"
                    f"patch:\n{patch if patch else '<no patch available>'}"
                )
            )
        return "\n\n".join(lines)
    except requests.HTTPError as exc:
        return f"GitHub API HTTP error while fetching PR files: {exc}"
    except (ValueError, RuntimeError) as exc:
        return f"GitHub PR files error: {exc}"
    except Exception as exc:
        return f"Unexpected GitHub PR files error: {exc}"


def github_retry_workflow_run(data: GitHubPayload) -> str:
    try:
        repo = data.get("repo", "")
        run_id = int(data.get("run_id", 0))
        owner, name = _parse_repo(repo)
        if run_id <= 0:
            return "run_id must be a positive integer."
        _github_request("POST", f"/repos/{owner}/{name}/actions/runs/{run_id}/rerun")
        return f"Triggered rerun for workflow run {run_id}."
    except requests.HTTPError as exc:
        return f"GitHub API HTTP error while retrying run: {exc}"
    except (ValueError, RuntimeError) as exc:
        return f"GitHub retry run error: {exc}"
    except Exception as exc:
        return f"Unexpected GitHub retry run error: {exc}"


def github_cancel_workflow_run(data: GitHubPayload) -> str:
    try:
        repo = data.get("repo", "")
        run_id = int(data.get("run_id", 0))
        owner, name = _parse_repo(repo)
        if run_id <= 0:
            return "run_id must be a positive integer."
        _github_request("POST", f"/repos/{owner}/{name}/actions/runs/{run_id}/cancel")
        return f"Cancel requested for workflow run {run_id}."
    except requests.HTTPError as exc:
        return f"GitHub API HTTP error while canceling run: {exc}"
    except (ValueError, RuntimeError) as exc:
        return f"GitHub cancel run error: {exc}"
    except Exception as exc:
        return f"Unexpected GitHub cancel run error: {exc}"


def github_post_pr_comment(data: dict[str, Any]) -> str:
    try:
        repo = str(data.get("repo", ""))
        pr_number = int(data.get("pr_number", 0))
        body = str(data.get("body", "")).strip()
        owner, name = _parse_repo(repo)
        if pr_number <= 0:
            return "pr_number must be a positive integer."
        if not body:
            return "body must be a non-empty string."
        _github_request(
            "POST",
            f"/repos/{owner}/{name}/issues/{pr_number}/comments",
            json_body={"body": body},
        )
        return f"Posted PR comment on {repo}#{pr_number}."
    except requests.HTTPError as exc:
        return f"GitHub API HTTP error while posting PR comment: {exc}"
    except (ValueError, RuntimeError) as exc:
        return f"GitHub PR comment error: {exc}"
    except Exception as exc:
        return f"Unexpected GitHub PR comment error: {exc}"


def github_required_checks_gate(data: GitHubPayload) -> str:
    try:
        repo = data.get("repo", "")
        pr_number = int(data.get("pr_number", 0))
        owner, name = _parse_repo(repo)
        if pr_number <= 0:
            return "pr_number must be a positive integer."

        pr = _github_request("GET", f"/repos/{owner}/{name}/pulls/{pr_number}")
        base_branch = (pr.get("base") or {}).get("ref")
        head_sha = (pr.get("head") or {}).get("sha")
        if not base_branch or not head_sha:
            return "Unable to determine base branch or head SHA for PR."

        try:
            protection = _github_request(
                "GET", f"/repos/{owner}/{name}/branches/{base_branch}/protection"
            )
            required = (
                (protection.get("required_status_checks") or {}).get("contexts") or []
            )
        except requests.HTTPError:
            required = []

        status = _github_request("GET", f"/repos/{owner}/{name}/commits/{head_sha}/status")
        checks = _github_request(
            "GET",
            f"/repos/{owner}/{name}/commits/{head_sha}/check-runs",
            params={"per_page": 100},
        )

        statuses = {
            item.get("context"): item.get("state") for item in status.get("statuses", [])
        }
        check_runs = {
            item.get("name"): item.get("conclusion")
            for item in checks.get("check_runs", [])
        }

        blocking = []
        for context in required:
            state = statuses.get(context) or check_runs.get(context)
            if state not in {"success", "neutral", "skipped"}:
                blocking.append(f"{context}={state or 'missing'}")

        lines = [
            f"repo={repo} pr={pr_number} base={base_branch}",
            "required_checks="
            + (", ".join(required) if required else "<none found or no permission>"),
            "blocking=" + (", ".join(blocking) if blocking else "<none>"),
        ]
        return "\n".join(lines)
    except requests.HTTPError as exc:
        return f"GitHub API HTTP error while checking required gates: {exc}"
    except (ValueError, RuntimeError) as exc:
        return f"GitHub required checks error: {exc}"
    except Exception as exc:
        return f"Unexpected GitHub required checks error: {exc}"


def github_deployment_status(data: GitHubPayload) -> str:
    try:
        repo = data.get("repo", "")
        per_page = int(data.get("per_page", 10))
        owner, name = _parse_repo(repo)
        deployments = _github_request(
            "GET",
            f"/repos/{owner}/{name}/deployments",
            params={"per_page": min(per_page, 30)},
        )
        if not isinstance(deployments, list) or not deployments:
            return "No deployments found."

        lines = []
        for dep in deployments[:per_page]:
            dep_id = dep.get("id")
            env = dep.get("environment")
            statuses = _github_request(
                "GET",
                f"/repos/{owner}/{name}/deployments/{dep_id}/statuses",
                params={"per_page": 1},
            )
            latest = statuses[0] if isinstance(statuses, list) and statuses else {}
            state = latest.get("state", "unknown")
            rollback_signal = "yes" if state in {"failure", "error"} else "no"
            lines.append(
                (
                    f"deployment_id={dep_id} env={env} ref={dep.get('ref')} "
                    f"state={state} rollback_signal={rollback_signal}"
                )
            )
        return "\n".join(lines)
    except requests.HTTPError as exc:
        return f"GitHub API HTTP error while fetching deployments: {exc}"
    except (ValueError, RuntimeError) as exc:
        return f"GitHub deployment status error: {exc}"
    except Exception as exc:
        return f"Unexpected GitHub deployment status error: {exc}"


def github_issue_triage(data: GitHubPayload) -> str:
    try:
        repo = data.get("repo", "")
        per_page = int(data.get("per_page", 20))
        owner, name = _parse_repo(repo)
        issues = _github_request(
            "GET",
            f"/repos/{owner}/{name}/issues",
            params={"state": "open", "per_page": min(per_page, 50)},
        )
        if not isinstance(issues, list):
            return "No issues found."

        triaged = []
        for item in issues:
            if item.get("pull_request"):
                continue
            title = (item.get("title") or "").lower()
            body = (item.get("body") or "").lower()
            text = f"{title}\n{body}"
            area = "general"
            priority = "P3"
            if any(k in text for k in ["security", "vulnerability", "cve", "auth bypass"]):
                area = "security"
                priority = "P0"
            elif any(k in text for k in ["crash", "down", "data loss", "urgent"]):
                area = "reliability"
                priority = "P1"
            elif any(k in text for k in ["performance", "slow", "latency"]):
                area = "performance"
                priority = "P2"
            elif any(k in text for k in ["docs", "documentation"]):
                area = "docs"
                priority = "P3"
            triaged.append(
                f"#{item.get('number')} [{priority}] area={area} title={item.get('title')}"
            )

        return "\n".join(triaged[:per_page]) if triaged else "No open issues (excluding PRs)."
    except requests.HTTPError as exc:
        return f"GitHub API HTTP error while triaging issues: {exc}"
    except (ValueError, RuntimeError) as exc:
        return f"GitHub issue triage error: {exc}"
    except Exception as exc:
        return f"Unexpected GitHub issue triage error: {exc}"


def github_security_summary(data: GitHubPayload) -> str:
    try:
        repo = data.get("repo", "")
        per_page = int(data.get("per_page", 20))
        owner, name = _parse_repo(repo)
        code_scanning = _github_request(
            "GET",
            f"/repos/{owner}/{name}/code-scanning/alerts",
            params={"state": "open", "per_page": min(per_page, 100)},
        )
        try:
            dependabot = _github_request(
                "GET",
                f"/repos/{owner}/{name}/dependabot/alerts",
                params={"state": "open", "per_page": min(per_page, 100)},
            )
        except requests.HTTPError:
            dependabot = []

        cs_count = len(code_scanning) if isinstance(code_scanning, list) else 0
        db_count = len(dependabot) if isinstance(dependabot, list) else 0
        lines = [
            f"open_code_scanning_alerts={cs_count}",
            f"open_dependabot_alerts={db_count}",
        ]

        if isinstance(code_scanning, list):
            for alert in code_scanning[:5]:
                rule = ((alert.get("rule") or {}).get("id")) or "unknown-rule"
                sev = ((alert.get("rule") or {}).get("security_severity_level")) or "unknown"
                lines.append(f"codeql rule={rule} severity={sev}")
        if isinstance(dependabot, list):
            for alert in dependabot[:5]:
                pkg = ((alert.get("dependency") or {}).get("package") or {}).get(
                    "name", "unknown"
                )
                sev = ((alert.get("security_advisory") or {}).get("severity")) or "unknown"
                lines.append(f"dependabot package={pkg} severity={sev}")

        lines.append(
            "suggestion: prioritize critical/high first, patch vulnerable deps, and add regression tests."
        )
        return "\n".join(lines)
    except requests.HTTPError as exc:
        return f"GitHub API HTTP error while summarizing security: {exc}"
    except (ValueError, RuntimeError) as exc:
        return f"GitHub security summary error: {exc}"
    except Exception as exc:
        return f"Unexpected GitHub security summary error: {exc}"


def github_changelog(data: dict[str, Any]) -> str:
    try:
        repo = str(data.get("repo", ""))
        base = str(data.get("base", "")).strip()
        head = str(data.get("head", "")).strip()
        owner, name = _parse_repo(repo)
        if not base or not head:
            return "base and head are required (tag/branch/SHA)."

        compare = _github_request("GET", f"/repos/{owner}/{name}/compare/{base}...{head}")
        commits = compare.get("commits", [])
        lines = [
            f"repo={repo}",
            f"range={base}...{head}",
            f"status={compare.get('status')} total_commits={compare.get('total_commits')}",
        ]
        for commit in commits[:30]:
            sha = (commit.get("sha") or "")[:7]
            msg = ((commit.get("commit") or {}).get("message") or "").splitlines()[0]
            author = ((commit.get("author") or {}).get("login")) or "unknown"
            lines.append(f"- {sha} {msg} (by {author})")
        return "\n".join(lines)
    except requests.HTTPError as exc:
        return f"GitHub API HTTP error while generating changelog: {exc}"
    except (ValueError, RuntimeError) as exc:
        return f"GitHub changelog error: {exc}"
    except Exception as exc:
        return f"Unexpected GitHub changelog error: {exc}"


def github_release_notes_to_pr_comment(data: dict[str, Any]) -> str:
    try:
        repo = str(data.get("repo", ""))
        pr_number = int(data.get("pr_number", 0))
        base = str(data.get("base", "")).strip()
        head = str(data.get("head", "")).strip()
        if pr_number <= 0:
            return "pr_number must be a positive integer."

        changelog = github_changelog({"repo": repo, "base": base, "head": head})
        if (
            changelog.startswith("GitHub")
            or changelog.startswith("Unexpected")
            or "required" in changelog
        ):
            return changelog
        return github_post_pr_comment(
            {
                "repo": repo,
                "pr_number": pr_number,
                "body": f"## Changelog\n\n```\n{changelog}\n```",
            }
        )
    except Exception as exc:
        return f"Unexpected GitHub release notes posting error: {exc}"


def github_pr_review_suggestions(data: GitHubPayload) -> str:
    try:
        files_output = github_pr_files(data)
        if files_output.startswith("GitHub") or files_output.startswith("Unexpected"):
            return files_output

        findings = []
        for block in files_output.split("\n\n"):
            lowered = block.lower()
            if "password" in lowered or "secret" in lowered or "token" in lowered:
                findings.append("Potential secret exposure found in patch.")
            if "console.log(" in lowered or "print(" in lowered:
                findings.append("Debug logging detected; verify it should remain.")
            if "todo" in lowered or "fixme" in lowered:
                findings.append("TODO/FIXME marker present in changes.")
            if "status=removed" in lowered and "test" in lowered:
                findings.append("Test file removal detected; verify coverage/regression risk.")

        if not findings:
            return "No obvious heuristic issues found. Perform a semantic/manual review for logic and edge cases."
        unique = list(dict.fromkeys(findings))
        return "PR review suggestions:\n- " + "\n- ".join(unique)
    except Exception as exc:
        return f"Unexpected GitHub PR review suggestions error: {exc}"


def github_multi_repo_dashboard(data: dict[str, Any]) -> str:
    try:
        repos = data.get("repos", [])
        if isinstance(repos, str):
            repos = [r.strip() for r in repos.split(",") if r.strip()]
        if not isinstance(repos, list) or not repos:
            return "repos must be a non-empty list or comma-separated string."

        lines = []
        for repo in repos:
            runs = github_actions_runs({"repo": repo, "per_page": 3})
            owner, name = _parse_repo(repo)
            prs = _github_request(
                "GET",
                f"/repos/{owner}/{name}/pulls",
                params={"state": "open", "per_page": 20},
            )
            open_prs = len(prs) if isinstance(prs, list) else 0
            failing = sum(
                1 for line in runs.splitlines() if "conclusion=failure" in line
            )
            lines.append(f"{repo}: open_prs={open_prs} recent_failed_runs={failing}")
        return "\n".join(lines)
    except requests.HTTPError as exc:
        return f"GitHub API HTTP error while building dashboard: {exc}"
    except (ValueError, RuntimeError) as exc:
        return f"GitHub dashboard error: {exc}"
    except Exception as exc:
        return f"Unexpected GitHub dashboard error: {exc}"


def github_daily_digest(data: dict[str, Any]) -> str:
    try:
        repos = data.get("repos", [])
        if isinstance(repos, str):
            repos = [r.strip() for r in repos.split(",") if r.strip()]
        if not isinstance(repos, list) or not repos:
            return "repos must be a non-empty list or comma-separated string."

        lines = ["Daily GitHub Digest"]
        for repo in repos:
            owner, name = _parse_repo(repo)
            runs = _github_request(
                "GET",
                f"/repos/{owner}/{name}/actions/runs",
                params={"per_page": 10},
            )
            prs = _github_request(
                "GET",
                f"/repos/{owner}/{name}/pulls",
                params={
                    "state": "open",
                    "per_page": 20,
                    "sort": "updated",
                    "direction": "asc",
                },
            )
            failing = [
                r for r in runs.get("workflow_runs", []) if r.get("conclusion") == "failure"
            ]
            stale_prs = []
            for pr in prs if isinstance(prs, list) else []:
                updated = (pr.get("updated_at") or "")[:10]
                stale_prs.append(
                    f"#{pr.get('number')} updated={updated} title={pr.get('title')}"
                )

            sec = github_security_summary({"repo": repo, "per_page": 5})
            lines.append(f"\n[{repo}]")
            lines.append(f"failing_runs={len(failing)}")
            lines.append("stale_or_oldest_open_prs:")
            for row in stale_prs[:5]:
                lines.append(f"- {row}")
            lines.append("security_snapshot:")
            lines.extend(f"- {line}" for line in sec.splitlines()[:6])
        return "\n".join(lines)
    except requests.HTTPError as exc:
        return f"GitHub API HTTP error while building digest: {exc}"
    except (ValueError, RuntimeError) as exc:
        return f"GitHub digest error: {exc}"
    except Exception as exc:
        return f"Unexpected GitHub digest error: {exc}"

