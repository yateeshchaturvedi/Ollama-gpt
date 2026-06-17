from __future__ import annotations

from typing import Dict, Any
from uuid import UUID
import httpx
from fastapi import APIRouter, HTTPException, Query, status, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.utils import get_platform_credentials
from app.db.dependencies import get_db
from app.auth.dependencies import require_viewer_or_above

router = APIRouter()


def _get_headers(token: str) -> dict[str, str]:
    headers = {}
    if token:
        headers["PRIVATE-TOKEN"] = token
    return headers


@router.get("/{project_id}/pipelines")
async def list_pipelines(
    project_id: str,
    per_page: int = Query(default=10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(require_viewer_or_above)
):
    org_id = UUID(current_user["org_id"])
    creds = await get_platform_credentials("gitlab", project_id, org_id, db)
    api_url = creds.get("url") or "https://gitlab.com"
    token = creds.get("token")

    url = f"{api_url}/api/v4/projects/{project_id}/pipelines"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=_get_headers(token),
                params={"per_page": per_page},
                timeout=15.0
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code if exc.response is not None else 500,
            detail=f"GitLab API Error: {exc}"
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{project_id}/pipelines/{pipeline_id}/logs", response_class=PlainTextResponse)
async def get_pipeline_logs(
    project_id: str,
    pipeline_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(require_viewer_or_above)
):
    org_id = UUID(current_user["org_id"])
    creds = await get_platform_credentials("gitlab", project_id, org_id, db)
    api_url = creds.get("url") or "https://gitlab.com"
    token = creds.get("token")
    headers = _get_headers(token)

    try:
        async with httpx.AsyncClient() as client:
            # 1. Fetch jobs for the pipeline
            jobs_url = f"{api_url}/api/v4/projects/{project_id}/pipelines/{pipeline_id}/jobs"
            response = await client.get(jobs_url, headers=headers, timeout=15.0)
            response.raise_for_status()
            jobs = response.json()

            merged_logs = []
            for job in jobs:
                job_name = job.get("name")
                job_id = job.get("id")
                job_status = job.get("status")

                # 2. Get trace log for this job
                trace_url = f"{api_url}/api/v4/projects/{project_id}/jobs/{job_id}/trace"
                trace_res = await client.get(trace_url, headers=headers, timeout=15.0)
                if trace_res.status_code == 200:
                    trace_content = trace_res.text
                    merged_logs.append(
                        f"--- GitLab Job: {job_name} (ID: {job_id}, Status: {job_status}) ---\n{trace_content}\n"
                    )

            if not merged_logs:
                return "No job logs found for this pipeline."
            return "\n".join(merged_logs)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code if exc.response is not None else 500,
            detail=f"GitLab API Error fetching logs: {exc}"
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
