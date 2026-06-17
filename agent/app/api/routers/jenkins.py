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


@router.get("/{job_name}/builds")
async def list_builds(
    job_name: str,
    limit: int = Query(default=10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(require_viewer_or_above)
):
    org_id = UUID(current_user["org_id"])
    creds = await get_platform_credentials("jenkins", job_name, org_id, db)
    jenkins_url = creds.get("url") or ""
    user = creds.get("user") or ""
    token = creds.get("token") or ""

    if not jenkins_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Jenkins URL is not configured. Set JENKINS_URL or add this job to your repository configurations."
        )

    # Jenkins JSON API
    url = f"{jenkins_url.rstrip('/')}/job/{job_name}/api/json"
    auth = (user, token) if user and token else None
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                params={"tree": "builds[number,url,result,timestamp,building,duration]"},
                auth=auth,
                timeout=15.0
            )
            response.raise_for_status()
            data = response.json()
            builds = data.get("builds", [])
            return builds[:limit]
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code if exc.response is not None else 500,
            detail=f"Jenkins API Error: {exc}"
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{job_name}/builds/{build_number}/logs", response_class=PlainTextResponse)
async def get_build_logs(
    job_name: str,
    build_number: int,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(require_viewer_or_above)
):
    org_id = UUID(current_user["org_id"])
    creds = await get_platform_credentials("jenkins", job_name, org_id, db)
    jenkins_url = creds.get("url") or ""
    user = creds.get("user") or ""
    token = creds.get("token") or ""

    if not jenkins_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Jenkins URL is not configured."
        )

    # Jenkins plain text console log
    url = f"{jenkins_url.rstrip('/')}/job/{job_name}/{build_number}/consoleText"
    auth = (user, token) if user and token else None
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, auth=auth, timeout=20.0)
            response.raise_for_status()
            return response.text
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code if exc.response is not None else 500,
            detail=f"Jenkins API Error fetching console logs: {exc}"
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
