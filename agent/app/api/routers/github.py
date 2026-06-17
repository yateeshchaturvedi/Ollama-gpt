from __future__ import annotations

import io
import zipfile
import httpx
from typing import Dict, Any
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query, status, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.utils import get_platform_credentials
from app.tooling import execute_tool
from app.db.dependencies import get_db
from app.auth.dependencies import require_viewer_or_above

router = APIRouter()


def _get_headers(token: str) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


@router.get("/{owner}/{repo}/runs")
async def list_runs(
    owner: str,
    repo: str,
    per_page: int = Query(default=10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(require_viewer_or_above)
):
    org_id = UUID(current_user["org_id"])
    repo_name = f"{owner}/{repo}"
    creds = await get_platform_credentials("github", repo_name, org_id, db)
    api_url = creds.get("url") or "https://api.github.com"
    token = creds.get("token")

    url = f"{api_url}/repos/{owner}/{repo}/actions/runs"
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
            detail=f"GitHub API Error: {exc}"
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{owner}/{repo}/runs/{run_id}/logs", response_class=PlainTextResponse)
async def get_run_logs(
    owner: str,
    repo: str,
    run_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(require_viewer_or_above)
):
    org_id = UUID(current_user["org_id"])
    repo_name = f"{owner}/{repo}"
    creds = await get_platform_credentials("github", repo_name, org_id, db)
    api_url = creds.get("url") or "https://api.github.com"
    token = creds.get("token")

    # GitHub log endpoint redirects to a zip file download url
    url = f"{api_url}/repos/{owner}/{repo}/actions/runs/{run_id}/logs"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=_get_headers(token),
                timeout=20.0,
                follow_redirects=True
            )
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="Logs not found or not ready yet.")
            response.raise_for_status()

            # Unzip log contents in-memory
            z = zipfile.ZipFile(io.BytesIO(response.content))
            merged_logs = []
            for name in sorted(z.namelist()):
                # Filter logs
                if name.endswith(".txt"):
                    content = z.read(name).decode("utf-8", errors="replace")
                    # Format to look clean in frontend terminal viewer
                    merged_logs.append(f"--- Log File: {name} ---\n{content}\n")

            if not merged_logs:
                return "No text logs found in the archive."
            return "\n".join(merged_logs)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code if exc.response is not None else 500,
            detail=f"GitHub API Error fetching logs: {exc}"
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/{owner}/{repo}/runs/{run_id}/retry")
async def retry_run(
    owner: str,
    repo: str,
    run_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(require_viewer_or_above)
):
    org_id = UUID(current_user["org_id"])
    repo_name = f"{owner}/{repo}"
    creds = await get_platform_credentials("github", repo_name, org_id, db)
    api_url = creds.get("url") or "https://api.github.com"
    token = creds.get("token")

    url = f"{api_url}/repos/{owner}/{repo}/actions/runs/{run_id}/rerun"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=_get_headers(token), timeout=15.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code if exc.response is not None else 500,
            detail=f"GitHub API Error retrying run: {exc}"
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/{owner}/{repo}/runs/{run_id}/cancel")
async def cancel_run(
    owner: str,
    repo: str,
    run_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(require_viewer_or_above)
):
    org_id = UUID(current_user["org_id"])
    repo_name = f"{owner}/{repo}"
    creds = await get_platform_credentials("github", repo_name, org_id, db)
    api_url = creds.get("url") or "https://api.github.com"
    token = creds.get("token")

    url = f"{api_url}/repos/{owner}/{repo}/actions/runs/{run_id}/cancel"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=_get_headers(token), timeout=15.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code if exc.response is not None else 500,
            detail=f"GitHub API Error cancelling run: {exc}"
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{owner}/{repo}/prs")
async def list_prs(
    owner: str,
    repo: str,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(require_viewer_or_above)
):
    org_id = UUID(current_user["org_id"])
    repo_name = f"{owner}/{repo}"
    creds = await get_platform_credentials("github", repo_name, org_id, db)
    api_url = creds.get("url") or "https://api.github.com"
    token = creds.get("token")

    url = f"{api_url}/repos/{owner}/{repo}/pulls"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=_get_headers(token), timeout=15.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code if exc.response is not None else 500,
            detail=f"GitHub API Error listing PRs: {exc}"
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{owner}/{repo}/prs/{pr_number}/overview")
async def get_pr_overview(
    owner: str,
    repo: str,
    pr_number: int,
    current_user: Dict[str, Any] = Depends(require_viewer_or_above)
):
    repo_name = f"{owner}/{repo}"
    overview = execute_tool("github_pr_overview", {"repo": repo_name, "pr_number": pr_number})
    files = execute_tool("github_pr_files", {"repo": repo_name, "pr_number": pr_number})
    return {"overview": overview, "files": files}


@router.get("/{owner}/{repo}/security")
async def get_security_alerts(
    owner: str,
    repo: str,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(require_viewer_or_above)
):
    org_id = UUID(current_user["org_id"])
    repo_name = f"{owner}/{repo}"
    creds = await get_platform_credentials("github", repo_name, org_id, db)
    api_url = creds.get("url") or "https://api.github.com"
    token = creds.get("token")

    # Dependabot alerts API
    url = f"{api_url}/repos/{owner}/{repo}/dependabot/alerts"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=_get_headers(token), timeout=15.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        if exc.response is not None and exc.response.status_code in (403, 404):
            return []
        raise HTTPException(
            status_code=exc.response.status_code if exc.response is not None else 500,
            detail=f"GitHub API Error fetching security alerts: {exc}"
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{owner}/{repo}/deployments")
async def get_deployments(
    owner: str,
    repo: str,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(require_viewer_or_above)
):
    org_id = UUID(current_user["org_id"])
    repo_name = f"{owner}/{repo}"
    creds = await get_platform_credentials("github", repo_name, org_id, db)
    api_url = creds.get("url") or "https://api.github.com"
    token = creds.get("token")

    url = f"{api_url}/repos/{owner}/{repo}/deployments"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=_get_headers(token), timeout=15.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code if exc.response is not None else 500,
            detail=f"GitHub API Error fetching deployments: {exc}"
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{owner}/{repo}/changelog")
async def get_changelog(
    owner: str,
    repo: str,
    base: str = "main",
    head: str = "dev",
    current_user: Dict[str, Any] = Depends(require_viewer_or_above)
):
    repo_name = f"{owner}/{repo}"
    changelog = execute_tool("github_changelog", {"repo": repo_name, "base": base, "head": head})
    return {"changelog": changelog}


@router.get("/{owner}/{repo}/digest")
async def get_digest(
    owner: str,
    repo: str,
    current_user: Dict[str, Any] = Depends(require_viewer_or_above)
):
    repo_name = f"{owner}/{repo}"
    digest = execute_tool("github_daily_digest", {"repos": [repo_name]})
    return {"digest": digest}
