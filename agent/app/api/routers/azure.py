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


@router.get("/{project}/{pipeline_id}/runs")
async def list_runs(
    project: str,
    pipeline_id: int,
    limit: int = Query(default=10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(require_viewer_or_above)
):
    org_id = UUID(current_user["org_id"])
    creds = await get_platform_credentials("azure", project, org_id, db)
    org_url = creds.get("url") or ""
    pat = creds.get("token") or ""

    if not org_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Azure DevOps Organization URL is not configured. Set AZDO_ORG_URL or add this repository to your configs."
        )

    # Azure DevOps pipelines runs list API
    url = f"{org_url.rstrip('/')}/{project}/_apis/pipelines/{pipeline_id}/runs"
    auth = ("", pat) if pat else None
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                params={"api-version": "7.1-preview.1", "$top": limit},
                auth=auth,
                timeout=15.0
            )
            response.raise_for_status()
            data = response.json()
            return data.get("value", [])
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code if exc.response is not None else 500,
            detail=f"Azure DevOps API Error: {exc}"
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{project}/{pipeline_id}/runs/{run_id}/logs", response_class=PlainTextResponse)
async def get_run_logs(
    project: str,
    pipeline_id: int,
    run_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(require_viewer_or_above)
):
    org_id = UUID(current_user["org_id"])
    creds = await get_platform_credentials("azure", project, org_id, db)
    org_url = creds.get("url") or ""
    pat = creds.get("token") or ""

    if not org_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Azure DevOps Organization URL is not configured."
        )

    # Get pipeline run logs references
    url = f"{org_url.rstrip('/')}/{project}/_apis/pipelines/{pipeline_id}/runs/{run_id}/logs"
    auth = ("", pat) if pat else None
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                params={"api-version": "7.1-preview.1"},
                auth=auth,
                timeout=15.0
            )
            response.raise_for_status()
            logs_list = response.json().get("value", [])

            merged_logs = []
            for log_ref in logs_list:
                log_id = log_ref.get("id")
                log_url = log_ref.get("url")

                # Fetch raw log contents
                if log_url:
                    log_res = await client.get(f"{log_url}?$expand=signedContent", auth=auth, timeout=15.0)
                    if log_res.status_code == 200:
                        merged_logs.append(
                            f"--- Azure DevOps Log ID: {log_id} ---\n{log_res.text}\n"
                        )

            if not merged_logs:
                return "No run logs found or they have expired."
            return "\n".join(merged_logs)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code if exc.response is not None else 500,
            detail=f"Azure DevOps API Error fetching logs: {exc}"
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
