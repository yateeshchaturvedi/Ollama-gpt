from __future__ import annotations

import logging
import secrets
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.dependencies import get_db
from app.db.models import AgentSettings
from app.auth.dependencies import require_admin

logger = logging.getLogger(__name__)

router = APIRouter()

# ================================================================
# PYDANTIC SCHEMAS
# ================================================================

class AgentSettingsUpdate(BaseModel):
    dangerous_actions_require_confirm: bool = True
    confirmation_token: str = Field(default_factory=lambda: secrets.token_urlsafe(8), min_length=1)
    safe_workspace_root: str = Field("/app")
    allowed_shell_prefixes: List[str] = ["ls", "dir", "pwd", "echo", "cat", "type"]
    max_shell_output_chars: int = Field(8000, ge=500, le=50000)
    
    tool_rate_limit_count: int = Field(60, ge=1, le=1000)
    tool_rate_limit_window_secs: int = Field(60, ge=5, le=3600)
    
    log_level: str = Field("INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    audit_log_retention_days: int = Field(90, ge=7, le=365)

class AgentSettingsResponse(BaseModel):
    dangerous_actions_require_confirm: bool
    confirmation_token: str
    safe_workspace_root: str
    allowed_shell_prefixes: List[str]
    max_shell_output_chars: int
    tool_rate_limit_count: int
    tool_rate_limit_window_secs: int
    log_level: str
    audit_log_retention_days: int

# ================================================================
# ENDPOINTS
# ================================================================

@router.get("", response_model=AgentSettingsResponse, tags=["admin-settings"])
async def get_agent_settings(
    db: AsyncSession = Depends(get_db),
    admin: Dict[str, Any] = Depends(require_admin)
):
    org_id = UUID(admin["org_id"])
    res = await db.execute(select(AgentSettings).where(AgentSettings.org_id == org_id))
    settings = res.scalar_one_or_none()
    
    if not settings:
        # Fallback create defaults if not generated during register
        settings = AgentSettings(
            org_id=org_id,
            dangerous_actions_require_confirm=True,
            confirmation_token=secrets.token_urlsafe(8),
            safe_workspace_root="/app"
        )
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
        
    return settings


@router.post("", response_model=AgentSettingsResponse, tags=["admin-settings"])
async def update_agent_settings(
    req: AgentSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    admin: Dict[str, Any] = Depends(require_admin)
):
    org_id = UUID(admin["org_id"])
    user_id = UUID(admin["sub"])
    
    res = await db.execute(select(AgentSettings).where(AgentSettings.org_id == org_id))
    settings = res.scalar_one_or_none()
    
    if not settings:
        settings = AgentSettings(org_id=org_id)
        db.add(settings)
        
    settings.dangerous_actions_require_confirm = req.dangerous_actions_require_confirm
    settings.confirmation_token = req.confirmation_token
    settings.safe_workspace_root = req.safe_workspace_root
    settings.allowed_shell_prefixes = req.allowed_shell_prefixes
    settings.max_shell_output_chars = req.max_shell_output_chars
    settings.tool_rate_limit_count = req.tool_rate_limit_count
    settings.tool_rate_limit_window_secs = req.tool_rate_limit_window_secs
    settings.log_level = req.log_level
    settings.audit_log_retention_days = req.audit_log_retention_days
    settings.updated_by = user_id
    
    await db.commit()
    await db.refresh(settings)
    return settings
