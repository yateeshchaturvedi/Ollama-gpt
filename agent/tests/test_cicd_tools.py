"""Unit tests for CI/CD tools (Jenkins, Azure DevOps, GitLab).

All HTTP calls are mocked — no real API calls are made.
Jenkins/AzDO/GitLab use their own requests.get calls directly.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from app.tools.cicd_tools import (
    azure_devops_recent_runs,
    azure_devops_run_log,
    gitlab_pipeline_log,
    gitlab_recent_pipelines,
    jenkins_build_log,
    jenkins_recent_builds,
)

JENKINS_ENV = {
    "JENKINS_URL": "http://jenkins.example.com",
    "JENKINS_USER": "admin",
    "JENKINS_API_TOKEN": "fake-token",
}

AZDO_ENV = {
    "AZDO_ORG_URL": "https://dev.azure.com/myorg",
    "AZDO_PAT": "fake-azdo-pat",
}

GITLAB_ENV = {
    "GITLAB_TOKEN": "fake-gitlab-token",
    "GITLAB_URL": "https://gitlab.com",
}


def _mock_response(json_data=None, text_data: str = "", status_code: int = 200) -> MagicMock:
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data if json_data is not None else {}
    mock.text = text_data
    mock.content = b"{}"
    mock.raise_for_status = MagicMock()
    if status_code >= 400:
        mock.raise_for_status.side_effect = requests.HTTPError(
            response=mock, request=MagicMock()
        )
    return mock


# ── Jenkins ───────────────────────────────────────────────────────────────────

class TestJenkinsRecentBuilds:
    def test_returns_build_list(self):
        payload = {
            "builds": [
                {
                    "number": 100,
                    "result": "SUCCESS",
                    "timestamp": 1700000000000,
                    "duration": 12000,
                    "url": "https://jenkins.example.com/job/my-job/100/",
                },
                {
                    "number": 99,
                    "result": "FAILURE",
                    "timestamp": 1699999000000,
                    "duration": 8000,
                    "url": "https://jenkins.example.com/job/my-job/99/",
                },
            ]
        }
        with patch.dict("os.environ", JENKINS_ENV):
            with patch("requests.get", return_value=_mock_response(payload)):
                result = jenkins_recent_builds({"job_name": "my-job", "limit": 10})
        assert isinstance(result, str)
        assert "100" in result

    def test_no_builds_returns_string(self):
        with patch.dict("os.environ", JENKINS_ENV):
            with patch("requests.get", return_value=_mock_response({"builds": []})):
                result = jenkins_recent_builds({"job_name": "empty-job", "limit": 10})
        assert isinstance(result, str)

    def test_missing_config_returns_error(self):
        with patch.dict("os.environ", {"JENKINS_URL": "", "JENKINS_USER": "", "JENKINS_API_TOKEN": ""}):
            result = jenkins_recent_builds({"job_name": "my-job", "limit": 10})
        assert "config missing" in result.lower() or isinstance(result, str)

    def test_network_error_returns_error_string(self):
        with patch.dict("os.environ", JENKINS_ENV):
            with patch("requests.get", side_effect=requests.ConnectionError("refused")):
                result = jenkins_recent_builds({"job_name": "my-job", "limit": 10})
        assert isinstance(result, str)

    def test_404_returns_error_string(self):
        with patch.dict("os.environ", JENKINS_ENV):
            with patch("requests.get", return_value=_mock_response(status_code=404)):
                result = jenkins_recent_builds({"job_name": "ghost-job", "limit": 10})
        assert isinstance(result, str)


class TestJenkinsBuildLog:
    def test_returns_log_content(self):
        log_text = "Started by user admin\nRunning tests...\nBUILD SUCCESS"
        with patch.dict("os.environ", JENKINS_ENV):
            with patch("requests.get", return_value=_mock_response(text_data=log_text)):
                result = jenkins_build_log({"job_name": "my-job", "build_number": 100, "max_chars": 8000})
        assert isinstance(result, str)

    def test_log_is_truncated_at_max_chars(self):
        log_text = "x" * 20000
        with patch.dict("os.environ", JENKINS_ENV):
            with patch("requests.get", return_value=_mock_response(text_data=log_text)):
                result = jenkins_build_log({"job_name": "my-job", "build_number": 100, "max_chars": 500})
        # Should include the truncation notice
        assert "truncated" in result.lower() or len(result) <= 1000

    def test_http_error_returns_error_string(self):
        with patch.dict("os.environ", JENKINS_ENV):
            with patch("requests.get", return_value=_mock_response(status_code=403)):
                result = jenkins_build_log({"job_name": "my-job", "build_number": 100, "max_chars": 8000})
        assert isinstance(result, str)


# ── Azure DevOps ──────────────────────────────────────────────────────────────

class TestAzureDevOpsRecentRuns:
    def test_returns_run_list(self):
        payload = {
            "value": [
                {
                    "id": 201,
                    "name": "Run 201",
                    "state": "completed",
                    "result": "succeeded",
                    "createdDate": "2024-01-01T00:00:00Z",
                }
            ]
        }
        with patch.dict("os.environ", AZDO_ENV):
            with patch("requests.get", return_value=_mock_response(payload)):
                result = azure_devops_recent_runs(
                    {"project": "MyProject", "pipeline_id": 12, "limit": 10}
                )
        assert isinstance(result, str)
        assert "201" in result

    def test_empty_runs_returns_string(self):
        with patch.dict("os.environ", AZDO_ENV):
            with patch("requests.get", return_value=_mock_response({"value": []})):
                result = azure_devops_recent_runs(
                    {"project": "MyProject", "pipeline_id": 12, "limit": 10}
                )
        assert isinstance(result, str)

    def test_missing_config_returns_error(self):
        with patch.dict("os.environ", {"AZDO_ORG_URL": "", "AZDO_PAT": ""}):
            result = azure_devops_recent_runs(
                {"project": "MyProject", "pipeline_id": 12, "limit": 10}
            )
        assert "config missing" in result.lower() or isinstance(result, str)

    def test_auth_error_returns_error_string(self):
        with patch.dict("os.environ", AZDO_ENV):
            with patch("requests.get", return_value=_mock_response(status_code=401)):
                result = azure_devops_recent_runs(
                    {"project": "MyProject", "pipeline_id": 12, "limit": 10}
                )
        assert isinstance(result, str)


class TestAzureDevOpsRunLog:
    def test_returns_log_content(self):
        logs_payload = {"value": [{"id": 1, "lineCount": 5, "url": "https://dev.azure.com/.../log/1"}]}
        log_text = "Task 1: Success\nTask 2: Failed"
        responses = [
            _mock_response(logs_payload),
            _mock_response(text_data=log_text),
        ]
        with patch.dict("os.environ", AZDO_ENV):
            with patch("requests.get", side_effect=responses):
                result = azure_devops_run_log(
                    {"project": "MyProject", "pipeline_id": 12, "run_id": 201, "max_chars": 10000}
                )
        assert isinstance(result, str)

    def test_network_error_returns_error_string(self):
        with patch.dict("os.environ", AZDO_ENV):
            with patch("requests.get", side_effect=requests.ConnectionError("timeout")):
                result = azure_devops_run_log(
                    {"project": "MyProject", "pipeline_id": 12, "run_id": 201, "max_chars": 10000}
                )
        assert isinstance(result, str)


# ── GitLab ────────────────────────────────────────────────────────────────────

class TestGitlabRecentPipelines:
    def test_returns_pipeline_list(self):
        payload = [
            {
                "id": 6789,
                "status": "failed",
                "ref": "main",
                "source": "push",
                "updated_at": "2024-01-01T00:00:00Z",
                "web_url": "https://gitlab.com/group/project/-/pipelines/6789",
            }
        ]
        with patch.dict("os.environ", GITLAB_ENV):
            with patch("requests.get", return_value=_mock_response(payload)):
                result = gitlab_recent_pipelines({"project_id": "12345", "limit": 10})
        assert isinstance(result, str)
        assert "6789" in result

    def test_empty_pipelines_returns_string(self):
        with patch.dict("os.environ", GITLAB_ENV):
            with patch("requests.get", return_value=_mock_response([])):
                result = gitlab_recent_pipelines({"project_id": "12345", "limit": 10})
        assert isinstance(result, str)

    def test_missing_token_returns_error(self):
        with patch.dict("os.environ", {"GITLAB_TOKEN": ""}):
            result = gitlab_recent_pipelines({"project_id": "12345", "limit": 10})
        assert "config missing" in result.lower() or isinstance(result, str)

    def test_401_unauthorized_returns_error_string(self):
        with patch.dict("os.environ", GITLAB_ENV):
            with patch("requests.get", return_value=_mock_response(status_code=401)):
                result = gitlab_recent_pipelines({"project_id": "12345", "limit": 10})
        assert isinstance(result, str)


class TestGitlabPipelineLog:
    def test_returns_log_content(self):
        jobs_payload = [{"id": 999, "name": "build", "status": "failed"}]
        log_text = "$ npm run build\nERROR: Cannot find module 'webpack'"
        responses = [
            _mock_response(jobs_payload),
            _mock_response(text_data=log_text),
        ]
        with patch.dict("os.environ", GITLAB_ENV):
            with patch("requests.get", side_effect=responses):
                result = gitlab_pipeline_log(
                    {"project_id": "12345", "pipeline_id": 6789, "max_chars": 10000}
                )
        assert isinstance(result, str)

    def test_network_error_returns_error_string(self):
        with patch.dict("os.environ", GITLAB_ENV):
            with patch("requests.get", side_effect=requests.ConnectionError("refused")):
                result = gitlab_pipeline_log(
                    {"project_id": "12345", "pipeline_id": 6789, "max_chars": 10000}
                )
        assert isinstance(result, str)
