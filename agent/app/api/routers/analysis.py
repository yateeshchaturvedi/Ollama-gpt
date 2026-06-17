from __future__ import annotations

import uuid
from typing import Any
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Depends
from pydantic import BaseModel
from app.agent_runtime import analyze_failure_log

from app.db.dependencies import get_db
from app.auth.dependencies import require_viewer_or_above
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.db_utils import get_llm_config_from_db

router = APIRouter()

import time

# In-memory store for pending log analyses
# (org_id, analysis_id) -> { "log": str, "context": dict, "llm_config": dict, "created_at": float }
PENDING_ANALYSES: dict[tuple[str, str], dict[str, Any]] = {}

def cleanup_stale_analyses():
    now = time.time()
    stale_keys = [k for k, v in PENDING_ANALYSES.items() if now - v.get("created_at", now) > 3600]
    for k in stale_keys:
        del PENDING_ANALYSES[k]


class AnalysisRequest(BaseModel):
    log: str
    platform: str = "unknown"
    repo: str = "unknown"
    job: str = "unknown"
    trigger: str = "unknown"


@router.post("/log")
async def trigger_log_analysis(
    req: AnalysisRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_viewer_or_above)
):
    """Store log text and context in memory, return an analysis ID for WebSocket streaming."""
    if not req.log.strip():
        raise HTTPException(status_code=400, detail="Log content cannot be empty.")

    org_id = uuid.UUID(current_user["org_id"])
    llm_config = await get_llm_config_from_db(org_id, db)

    cleanup_stale_analyses()
    org_id_str = str(org_id)
    analysis_id = str(uuid.uuid4())
    PENDING_ANALYSES[(org_id_str, analysis_id)] = {
        "log": req.log,
        "platform": req.platform,
        "repo": req.repo,
        "job": req.job,
        "trigger": req.trigger,
        "llm_config": llm_config,
        "created_at": time.time()
    }
    return {"analysis_id": analysis_id}


async def stream_analysis_websocket(websocket: WebSocket, analysis_id: str, org_id: str):
    """Accepts WebSocket connection and streams Gemini analysis tokens for the ID."""
    await websocket.accept()

    analysis_data = PENDING_ANALYSES.pop((org_id, analysis_id), None)
    if not analysis_data:
        await websocket.send_text("Error: Analysis ID not found or already consumed.")
        await websocket.close()
        return

    try:
        # Stream from agent_runtime's analyze_failure_log
        async for chunk in analyze_failure_log(
            log=analysis_data["log"],
            platform=analysis_data["platform"],
            repo=analysis_data["repo"],
            job=analysis_data["job"],
            trigger=analysis_data["trigger"],
            llm_config=analysis_data.get("llm_config", {})
        ):
            await websocket.send_text(chunk)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await websocket.send_text(f"\nAI Analysis Error: {exc}")
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
