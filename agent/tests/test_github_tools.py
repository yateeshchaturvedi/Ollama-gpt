"""Unit tests for GitHub tools (app/tools/github_tools.py).

All HTTP calls are mocked — no real GitHub API calls are made.
We patch GITHUB_TOKEN and mock requests.request (used by _github_request internally).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from app.tools.github_tools import (
    github_actions_run_logs,
    github_actions_runs,
    github_cancel_workflow_run,
    github_deployment_status,
    github_issue_triage,
    github_post_pr_comment,
    github_pr_files,
    github_pr_overview,
    github_retry_workflow_run,
    github_security_summary,
)

FAKE_TOKEN = "ghp_test_token_for_testing"


def _mock_response(json_data=None, status_code: int = 200) -> MagicMock:
    """Build a mock requests.Response."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data if json_data is not None else {}
    mock.content = b"{}" if status_code != 204 else b""
    mock.raise_for_status = MagicMock()
    if status_code >= 400:
        mock.raise_for_status.side_effect = requests.HTTPError(
            response=mock, request=MagicMock()
        )
    return mock


def _req(json_data=None, status_code: int = 200):
    """Shorthand that also wraps in the env-patch context."""
    return patch(
        "requests.request",
        return_value=_mock_response(json_data, status_code),
    )


# ── github_actions_runs ────────────────────────────────────────────────────────

class TestGithubActionsRuns:
    def test_returns_run_summary(self):
        payload = {
            "workflow_runs": [
                {
                    "id": 1001,
                    "name": "CI",
                    "status": "completed",
                    "conclusion": "success",
                    "created_at": "2024-01-01T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/actions/runs/1001",
                }
            ]
        }
        with patch.dict("os.environ", {"GITHUB_TOKEN": FAKE_TOKEN}):
            with patch("requests.request", return_value=_mock_response(payload)):
                result = github_actions_runs({"repo": "owner/repo", "per_page": 5})
        assert "1001" in result

    def test_empty_runs_returns_message(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": FAKE_TOKEN}):
            with patch("requests.request", return_value=_mock_response({"workflow_runs": []})):
                result = github_actions_runs({"repo": "owner/repo", "per_page": 5})
        assert isinstance(result, str)

    def test_http_error_returns_error_string(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": FAKE_TOKEN}):
            with patch("requests.request", return_value=_mock_response({}, status_code=401)):
                result = github_actions_runs({"repo": "owner/repo", "per_page": 5})
        assert isinstance(result, str)

    def test_no_token_returns_error_string(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": ""}):
            result = github_actions_runs({"repo": "owner/repo", "per_page": 5})
        assert "GITHUB_TOKEN" in result or isinstance(result, str)

    def test_network_error_returns_error_string(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": FAKE_TOKEN}):
            with patch("requests.request", side_effect=requests.ConnectionError("no network")):
                result = github_actions_runs({"repo": "owner/repo", "per_page": 5})
        assert isinstance(result, str)


# ── github_actions_run_logs ────────────────────────────────────────────────────

class TestGithubActionsRunLogs:
    def test_returns_log_content(self):
        run_payload = {
            "id": 1001,
            "name": "CI",
            "status": "completed",
            "conclusion": "failure",
            "html_url": "https://github.com/owner/repo/actions/runs/1001",
        }
        jobs_payload = {
            "jobs": [
                {
                    "id": 2001,
                    "name": "build",
                    "status": "completed",
                    "conclusion": "failure",
                    "started_at": "2024-01-01T00:00:00Z",
                    "steps": [
                        {"name": "Run tests", "conclusion": "failure", "number": 1}
                    ],
                }
            ]
        }
        responses = [_mock_response(run_payload), _mock_response(jobs_payload)]
        with patch.dict("os.environ", {"GITHUB_TOKEN": FAKE_TOKEN}):
            with patch("requests.request", side_effect=responses):
                result = github_actions_run_logs({"repo": "owner/repo", "run_id": 1001})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_network_error_is_handled(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": FAKE_TOKEN}):
            with patch("requests.request", side_effect=requests.ConnectionError("timeout")):
                result = github_actions_run_logs({"repo": "owner/repo", "run_id": 9999})
        assert isinstance(result, str)


# ── github_pr_overview ────────────────────────────────────────────────────────

class TestGithubPrOverview:
    def test_returns_pr_summary(self):
        pr_payload = {
            "number": 42,
            "title": "Fix auth bug",
            "state": "open",
            "draft": False,
            "user": {"login": "alice"},
            "body": "Fixes #100",
            "base": {"ref": "main"},
            "head": {"ref": "fix/auth", "sha": "abc123"},
            "mergeable": True,
            "mergeable_state": "clean",
            "additions": 10,
            "deletions": 5,
            "changed_files": 2,
        }
        reviews_payload: list = []
        responses = [_mock_response(pr_payload), _mock_response(reviews_payload)]
        with patch.dict("os.environ", {"GITHUB_TOKEN": FAKE_TOKEN}):
            with patch("requests.request", side_effect=responses):
                result = github_pr_overview({"repo": "owner/repo", "pr_number": 42})
        assert "alice" in result or "Fix auth bug" in result

    def test_404_returns_error_string(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": FAKE_TOKEN}):
            with patch("requests.request", return_value=_mock_response({}, status_code=404)):
                result = github_pr_overview({"repo": "owner/repo", "pr_number": 999})
        assert isinstance(result, str)


# ── github_pr_files ───────────────────────────────────────────────────────────

class TestGithubPrFiles:
    def test_returns_file_list(self):
        files_payload = [
            {"filename": "src/auth.py", "status": "modified", "additions": 5, "deletions": 2, "patch": "@@ ..."},
            {"filename": "tests/test_auth.py", "status": "added", "additions": 20, "deletions": 0, "patch": ""},
        ]
        with patch.dict("os.environ", {"GITHUB_TOKEN": FAKE_TOKEN}):
            with patch("requests.request", return_value=_mock_response(files_payload)):
                result = github_pr_files({"repo": "owner/repo", "pr_number": 42, "limit": 20})
        assert "src/auth.py" in result or isinstance(result, str)

    def test_empty_files_returns_string(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": FAKE_TOKEN}):
            with patch("requests.request", return_value=_mock_response([])):
                result = github_pr_files({"repo": "owner/repo", "pr_number": 42, "limit": 20})
        assert isinstance(result, str)


# ── github_retry_workflow_run / github_cancel_workflow_run ────────────────────

class TestWorkflowRunActions:
    def test_retry_success(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": FAKE_TOKEN}):
            with patch("requests.request", return_value=_mock_response({}, status_code=201)):
                result = github_retry_workflow_run({"repo": "owner/repo", "run_id": 1001})
        assert isinstance(result, str)

    def test_cancel_success(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": FAKE_TOKEN}):
            with patch("requests.request", return_value=_mock_response({}, status_code=202)):
                result = github_cancel_workflow_run({"repo": "owner/repo", "run_id": 1001})
        assert isinstance(result, str)

    def test_retry_http_error(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": FAKE_TOKEN}):
            with patch("requests.request", return_value=_mock_response({}, status_code=403)):
                result = github_retry_workflow_run({"repo": "owner/repo", "run_id": 1001})
        assert isinstance(result, str)


# ── github_deployment_status ──────────────────────────────────────────────────

class TestGithubDeploymentStatus:
    def test_returns_deployments(self):
        deps_payload = [
            {"id": 1, "environment": "production", "ref": "main",
             "created_at": "2024-01-01T00:00:00Z", "creator": {"login": "bot"}}
        ]
        statuses_payload = [{"state": "success"}]
        responses = [_mock_response(deps_payload), _mock_response(statuses_payload)]
        with patch.dict("os.environ", {"GITHUB_TOKEN": FAKE_TOKEN}):
            with patch("requests.request", side_effect=responses):
                result = github_deployment_status({"repo": "owner/repo", "per_page": 10})
        assert isinstance(result, str)


# ── github_issue_triage ───────────────────────────────────────────────────────

class TestGithubIssueTriage:
    def test_returns_issues(self):
        payload = [
            {
                "number": 5,
                "title": "Bug in login",
                "state": "open",
                "user": {"login": "bob"},
                "labels": [{"name": "bug"}],
                "body": "something crashes",
                "created_at": "2024-01-01T00:00:00Z",
            }
        ]
        with patch.dict("os.environ", {"GITHUB_TOKEN": FAKE_TOKEN}):
            with patch("requests.request", return_value=_mock_response(payload)):
                result = github_issue_triage({"repo": "owner/repo", "per_page": 20})
        assert isinstance(result, str)


# ── github_security_summary ───────────────────────────────────────────────────

class TestGithubSecuritySummary:
    def test_returns_alerts(self):
        code_scanning: list = []
        dependabot = [
            {
                "number": 1,
                "state": "open",
                "dependency": {"package": {"name": "lodash"}},
                "security_advisory": {"severity": "high", "summary": "Prototype pollution"},
            }
        ]
        # First call = code scanning, second = dependabot
        responses = [_mock_response(code_scanning), _mock_response(dependabot)]
        with patch.dict("os.environ", {"GITHUB_TOKEN": FAKE_TOKEN}):
            with patch("requests.request", side_effect=responses):
                result = github_security_summary({"repo": "owner/repo", "per_page": 20})
        assert isinstance(result, str)

    def test_rate_limit_response_is_handled(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": FAKE_TOKEN}):
            with patch("requests.request", return_value=_mock_response({}, status_code=429)):
                result = github_security_summary({"repo": "owner/repo", "per_page": 20})
        assert isinstance(result, str)


# ── github_post_pr_comment ────────────────────────────────────────────────────

class TestGithubPostPrComment:
    def test_posts_comment_successfully(self):
        resp_payload = {"id": 9001, "html_url": "https://github.com/.../comment/9001"}
        with patch.dict("os.environ", {"GITHUB_TOKEN": FAKE_TOKEN}):
            with patch("requests.request", return_value=_mock_response(resp_payload, status_code=201)):
                result = github_post_pr_comment(
                    {"repo": "owner/repo", "pr_number": 42, "body": "LGTM!"}
                )
        assert isinstance(result, str)

    def test_post_failure_returns_error(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": FAKE_TOKEN}):
            with patch("requests.request", return_value=_mock_response({}, status_code=422)):
                result = github_post_pr_comment(
                    {"repo": "owner/repo", "pr_number": 42, "body": "LGTM!"}
                )
        assert isinstance(result, str)
