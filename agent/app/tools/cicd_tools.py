import os
from typing import Any

import requests


def jenkins_recent_builds(data: dict[str, Any]) -> str:
    """Fetch recent Jenkins builds for a job."""
    try:
        base_url = os.getenv("JENKINS_URL", "").rstrip("/")
        user = os.getenv("JENKINS_USER", "")
        token = os.getenv("JENKINS_API_TOKEN", "")
        job_name = str(data.get("job_name", "")).strip()
        limit = int(data.get("limit", 10))
        if not base_url or not user or not token:
            return "Jenkins config missing. Set JENKINS_URL, JENKINS_USER, JENKINS_API_TOKEN."
        if not job_name:
            return "job_name is required."

        url = (
            f"{base_url}/job/{job_name}/api/json"
            "?tree=builds[number,result,timestamp,duration,url]{0,50}"
        )
        response = requests.get(url, auth=(user, token), timeout=30)
        response.raise_for_status()
        builds = response.json().get("builds", [])
        if not builds:
            return "No Jenkins builds found."

        lines = []
        for build in builds[: max(1, min(limit, 50))]:
            lines.append(
                (
                    f"build={build.get('number')} result={build.get('result')} "
                    f"duration_ms={build.get('duration')} url={build.get('url')}"
                )
            )
        return "\n".join(lines)
    except requests.HTTPError as exc:
        return f"Jenkins API HTTP error: {exc}"
    except Exception as exc:
        return f"Unexpected Jenkins monitoring error: {exc}"


def azure_devops_recent_runs(data: dict[str, Any]) -> str:
    """Fetch recent Azure DevOps pipeline runs."""
    try:
        org_url = os.getenv("AZDO_ORG_URL", "").rstrip("/")
        pat = os.getenv("AZDO_PAT", "")
        project = str(data.get("project", "")).strip()
        pipeline_id = int(data.get("pipeline_id", 0))
        limit = int(data.get("limit", 10))
        if not org_url or not pat:
            return "Azure DevOps config missing. Set AZDO_ORG_URL and AZDO_PAT."
        if not project or pipeline_id <= 0:
            return "project and positive pipeline_id are required."

        url = f"{org_url}/{project}/_apis/pipelines/{pipeline_id}/runs"
        params = {"api-version": "7.1", "$top": max(1, min(limit, 50))}
        # Azure DevOps PAT uses basic auth with empty username.
        response = requests.get(url, params=params, auth=("", pat), timeout=30)
        response.raise_for_status()
        runs = response.json().get("value", [])
        if not runs:
            return "No Azure DevOps runs found."

        lines = []
        for run in runs[: max(1, min(limit, 50))]:
            result = (run.get("result") or "<pending>").lower()
            state = (run.get("state") or "").lower()
            lines.append(
                (
                    f"run_id={run.get('id')} name={run.get('name')} state={state} "
                    f"result={result} created={run.get('createdDate')}"
                )
            )
        return "\n".join(lines)
    except requests.HTTPError as exc:
        return f"Azure DevOps API HTTP error: {exc}"
    except Exception as exc:
        return f"Unexpected Azure DevOps monitoring error: {exc}"


def gitlab_recent_pipelines(data: dict[str, Any]) -> str:
    """Fetch recent GitLab pipelines for a project."""
    try:
        base_url = os.getenv("GITLAB_URL", "https://gitlab.com").rstrip("/")
        token = os.getenv("GITLAB_TOKEN", "")
        project_id = str(data.get("project_id", "")).strip()
        limit = int(data.get("limit", 10))
        if not token:
            return "GitLab config missing. Set GITLAB_TOKEN."
        if not project_id:
            return "project_id is required."

        url = f"{base_url}/api/v4/projects/{project_id}/pipelines"
        headers = {"PRIVATE-TOKEN": token}
        params = {"per_page": max(1, min(limit, 50))}
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        pipelines = response.json()
        if not isinstance(pipelines, list) or not pipelines:
            return "No GitLab pipelines found."

        lines = []
        for pipeline in pipelines[: max(1, min(limit, 50))]:
            lines.append(
                (
                    f"id={pipeline.get('id')} ref={pipeline.get('ref')} "
                    f"status={pipeline.get('status')} source={pipeline.get('source')} "
                    f"updated_at={pipeline.get('updated_at')}"
                )
            )
        return "\n".join(lines)
    except requests.HTTPError as exc:
        return f"GitLab API HTTP error: {exc}"
    except Exception as exc:
        return f"Unexpected GitLab monitoring error: {exc}"


def jenkins_build_log(data: dict[str, Any]) -> str:
    """Fetch Jenkins console log for a specific build."""
    try:
        base_url = os.getenv("JENKINS_URL", "").rstrip("/")
        user = os.getenv("JENKINS_USER", "")
        token = os.getenv("JENKINS_API_TOKEN", "")
        job_name = str(data.get("job_name", "")).strip()
        build_number = int(data.get("build_number", 0))
        max_chars = int(data.get("max_chars", 8000))
        if not base_url or not user or not token:
            return "Jenkins config missing. Set JENKINS_URL, JENKINS_USER, JENKINS_API_TOKEN."
        if not job_name or build_number <= 0:
            return "job_name and positive build_number are required."

        url = f"{base_url}/job/{job_name}/{build_number}/consoleText"
        response = requests.get(url, auth=(user, token), timeout=45)
        response.raise_for_status()
        text = response.text or ""
        if len(text) > max(1000, max_chars):
            text = text[-max(1000, max_chars) :]
            text = "...<truncated, showing tail>...\n" + text
        return text if text.strip() else "No Jenkins console output available."
    except requests.HTTPError as exc:
        return f"Jenkins API HTTP error while fetching build log: {exc}"
    except Exception as exc:
        return f"Unexpected Jenkins log error: {exc}"


def azure_devops_run_log(data: dict[str, Any]) -> str:
    """Fetch Azure DevOps pipeline run logs."""
    try:
        org_url = os.getenv("AZDO_ORG_URL", "").rstrip("/")
        pat = os.getenv("AZDO_PAT", "")
        project = str(data.get("project", "")).strip()
        pipeline_id = int(data.get("pipeline_id", 0))
        run_id = int(data.get("run_id", 0))
        max_chars = int(data.get("max_chars", 10000))
        if not org_url or not pat:
            return "Azure DevOps config missing. Set AZDO_ORG_URL and AZDO_PAT."
        if not project or pipeline_id <= 0 or run_id <= 0:
            return "project, positive pipeline_id, and positive run_id are required."

        # Discover log URLs for the run.
        logs_url = f"{org_url}/{project}/_apis/pipelines/{pipeline_id}/runs/{run_id}/logs"
        logs_resp = requests.get(
            logs_url,
            params={"api-version": "7.1-preview.1"},
            auth=("", pat),
            timeout=30,
        )
        logs_resp.raise_for_status()
        logs = logs_resp.json().get("value", [])
        if not logs:
            return "No Azure DevOps run logs found."

        chunks: list[str] = []
        for item in logs[:5]:
            log_id = item.get("id")
            log_url = item.get("url")
            if not log_url:
                continue
            content_resp = requests.get(log_url, auth=("", pat), timeout=45)
            content_resp.raise_for_status()
            content = content_resp.text or ""
            if len(content) > 2500:
                content = content[-2500:]
                content = "...<truncated log tail>...\n" + content
            chunks.append(f"log_id={log_id}\n{content}")

        combined = "\n\n".join(chunks)
        if len(combined) > max(2000, max_chars):
            combined = combined[-max(2000, max_chars) :]
            combined = "...<truncated aggregate tail>...\n" + combined
        return combined if combined.strip() else "No Azure DevOps log text available."
    except requests.HTTPError as exc:
        return f"Azure DevOps API HTTP error while fetching run log: {exc}"
    except Exception as exc:
        return f"Unexpected Azure DevOps log error: {exc}"


def gitlab_pipeline_log(data: dict[str, Any]) -> str:
    """Fetch GitLab pipeline job trace tails."""
    try:
        base_url = os.getenv("GITLAB_URL", "https://gitlab.com").rstrip("/")
        token = os.getenv("GITLAB_TOKEN", "")
        project_id = str(data.get("project_id", "")).strip()
        pipeline_id = int(data.get("pipeline_id", 0))
        max_chars = int(data.get("max_chars", 10000))
        if not token:
            return "GitLab config missing. Set GITLAB_TOKEN."
        if not project_id or pipeline_id <= 0:
            return "project_id and positive pipeline_id are required."

        headers = {"PRIVATE-TOKEN": token}
        jobs_url = f"{base_url}/api/v4/projects/{project_id}/pipelines/{pipeline_id}/jobs"
        jobs_resp = requests.get(jobs_url, headers=headers, timeout=30)
        jobs_resp.raise_for_status()
        jobs = jobs_resp.json()
        if not isinstance(jobs, list) or not jobs:
            return "No jobs found for GitLab pipeline."

        chunks: list[str] = []
        for job in jobs[:5]:
            job_id = job.get("id")
            trace_url = f"{base_url}/api/v4/projects/{project_id}/jobs/{job_id}/trace"
            trace_resp = requests.get(trace_url, headers=headers, timeout=45)
            if trace_resp.status_code == 404:
                continue
            trace_resp.raise_for_status()
            trace = trace_resp.text or ""
            if len(trace) > 2500:
                trace = trace[-2500:]
                trace = "...<truncated trace tail>...\n" + trace
            chunks.append(
                (
                    f"job_id={job_id} name={job.get('name')} status={job.get('status')}\n"
                    f"{trace}"
                )
            )

        combined = "\n\n".join(chunks)
        if len(combined) > max(2000, max_chars):
            combined = combined[-max(2000, max_chars) :]
            combined = "...<truncated aggregate tail>...\n" + combined
        return combined if combined.strip() else "No GitLab job trace available."
    except requests.HTTPError as exc:
        return f"GitLab API HTTP error while fetching pipeline log: {exc}"
    except Exception as exc:
        return f"Unexpected GitLab pipeline log error: {exc}"
