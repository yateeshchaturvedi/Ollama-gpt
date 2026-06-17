from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.dependencies import get_db
from app.db.models import SlackConfig
from app.auth.dependencies import require_admin

logger = logging.getLogger(__name__)

router = APIRouter()

# ================================================================
# PYDANTIC SCHEMAS
# ================================================================

class SlackConfigUpdate(BaseModel):
    slack_workspace_id: Optional[str] = None
    slack_workspace_name: Optional[str] = None
    
    bot_token: Optional[str] = None
    app_token: Optional[str] = None
    
    default_alert_channel: Optional[str] = None
    allowed_channel: Optional[str] = None
    require_mention: bool = True
    max_reply_chars: int = Field(38000, ge=500, le=100000)
    is_active: bool = False

class SlackConfigResponse(BaseModel):
    slack_workspace_id: Optional[str]
    slack_workspace_name: Optional[str]
    bot_token_hint: Optional[str]
    app_token_hint: Optional[str]
    default_alert_channel: Optional[str]
    allowed_channel: Optional[str]
    require_mention: bool
    max_reply_chars: int
    is_active: bool
    last_test_status: str
    last_test_error: Optional[str]

# ================================================================
# ENDPOINTS
# ================================================================

@router.get("", response_model=Optional[SlackConfigResponse], tags=["admin-slack"])
async def get_slack_config(
    db: AsyncSession = Depends(get_db),
    admin: Dict[str, Any] = Depends(require_admin)
):
    org_id = UUID(admin["org_id"])
    res = await db.execute(select(SlackConfig).where(SlackConfig.org_id == org_id))
    return res.scalar_one_or_none()


@router.post("", response_model=SlackConfigResponse, tags=["admin-slack"])
async def update_slack_config(
    req: SlackConfigUpdate,
    db: AsyncSession = Depends(get_db),
    admin: Dict[str, Any] = Depends(require_admin)
):
    org_id = UUID(admin["org_id"])
    user_id = UUID(admin["sub"])
    
    # Check if config already exists
    res = await db.execute(select(SlackConfig).where(SlackConfig.org_id == org_id))
    config = res.scalar_one_or_none()
    
    encryption_key = func.current_setting('app.encryption_key')
    
    # Encrypt tokens if provided
    bot_encrypted = None
    bot_hint = None
    if req.bot_token:
        bot_encrypted = func.pgp_sym_encrypt(req.bot_token, encryption_key)
        bot_hint = f"●●●● {req.bot_token[-4:]}" if len(req.bot_token) >= 4 else "●●●●"
        
    app_encrypted = None
    app_hint = None
    if req.app_token:
        app_encrypted = func.pgp_sym_encrypt(req.app_token, encryption_key)
        app_hint = f"●●●● {req.app_token[-4:]}" if len(req.app_token) >= 4 else "●●●●"
        
    if config:
        # Update existing config
        config.slack_workspace_id = req.slack_workspace_id or config.slack_workspace_id
        config.slack_workspace_name = req.slack_workspace_name or config.slack_workspace_name
        
        if req.bot_token:
            config.bot_token_encrypted = bot_encrypted
            config.bot_token_hint = bot_hint
        if req.app_token:
            config.app_token_encrypted = app_encrypted
            config.app_token_hint = app_hint
            
        config.default_alert_channel = req.default_alert_channel or config.default_alert_channel
        config.allowed_channel = req.allowed_channel or config.allowed_channel
        config.require_mention = req.require_mention
        config.max_reply_chars = req.max_reply_chars
        config.is_active = req.is_active
        config.updated_by = user_id
    else:
        # Create new config
        config = SlackConfig(
            org_id=org_id,
            created_by=user_id,
            slack_workspace_id=req.slack_workspace_id,
            slack_workspace_name=req.slack_workspace_name,
            bot_token_encrypted=bot_encrypted,
            bot_token_hint=bot_hint,
            app_token_encrypted=app_encrypted,
            app_token_hint=app_hint,
            default_alert_channel=req.default_alert_channel,
            allowed_channel=req.allowed_channel,
            require_mention=req.require_mention,
            max_reply_chars=req.max_reply_chars,
            is_active=req.is_active
        )
        db.add(config)
        
    await db.commit()
    await db.refresh(config)
    return config
