from __future__ import annotations

import logging
from typing import Literal, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
import google.generativeai as genai
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.dependencies import get_db
from app.db.models import LLMProviderConfig, AgentSettings, LLMProvider
from app.auth.dependencies import require_viewer_or_above, require_admin
from app.api.db_utils import ensure_encryption_key

logger = logging.getLogger(__name__)

router = APIRouter()


class ConfigModel(BaseModel):
    llm_provider: Literal["gemini", "openai", "anthropic", "ollama"]
    google_model: str
    google_api_key: str | None = None
    max_tool_steps: int = Field(ge=1, le=20)
    max_history: int = Field(ge=2, le=100)
    dangerous_actions_require_confirmation: bool


@router.get("")
async def get_config(
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(require_viewer_or_above)
):
    """Get current configuration, with sensitive values masked."""
    org_id = UUID(current_user["org_id"])
    
    # Get LLM config
    llm_stmt = select(LLMProviderConfig).where(
        LLMProviderConfig.org_id == org_id,
        LLMProviderConfig.is_default == True,
        LLMProviderConfig.is_active == True
    )
    llm_res = await db.execute(llm_stmt)
    llm_conf = llm_res.scalar_one_or_none()
    
    # Get Agent Settings
    settings_stmt = select(AgentSettings).where(
        AgentSettings.org_id == org_id
    )
    settings_res = await db.execute(settings_stmt)
    agent_sett = settings_res.scalar_one_or_none()
    
    # Determine values (DB first, fallback to settings)
    provider = llm_conf.provider if llm_conf else settings.llm_provider
    model = llm_conf.model_name if llm_conf else settings.google_model
    
    has_key = False
    if llm_conf:
        has_key = llm_conf.api_key_encrypted is not None
    else:
        has_key = bool(settings.google_api_key)
        
    masked_key = "********" if has_key else ""
    
    max_steps = llm_conf.max_tool_steps if llm_conf else settings.max_tool_steps
    max_hist = llm_conf.max_history if llm_conf else settings.max_history
    
    req_confirm = agent_sett.dangerous_actions_require_confirm if agent_sett else settings.dangerous_actions_require_confirmation
    
    return {
        "llm_provider": provider,
        "google_model": model,
        "google_api_key": masked_key,
        "max_tool_steps": max_steps,
        "max_history": max_hist,
        "dangerous_actions_require_confirmation": req_confirm,
    }


@router.post("")
async def update_config(
    cfg: ConfigModel,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(require_admin)
):
    """Update configurations dynamically and persist in database."""
    org_id = UUID(current_user["org_id"])
    user_id = UUID(current_user["sub"])
    
    # 1. Update/Upsert AgentSettings
    settings_stmt = select(AgentSettings).where(
        AgentSettings.org_id == org_id
    )
    settings_res = await db.execute(settings_stmt)
    agent_sett = settings_res.scalar_one_or_none()
    
    if agent_sett:
        agent_sett.dangerous_actions_require_confirm = cfg.dangerous_actions_require_confirmation
    else:
        agent_sett = AgentSettings(
            org_id=org_id,
            dangerous_actions_require_confirm=cfg.dangerous_actions_require_confirmation,
            safe_workspace_root=settings.safe_workspace_root or "/workspace",
            log_level="INFO"
        )
        db.add(agent_sett)
        
    # 2. Update/Upsert LLMProviderConfig
    llm_stmt = select(LLMProviderConfig).where(
        LLMProviderConfig.org_id == org_id,
        LLMProviderConfig.is_default == True,
        LLMProviderConfig.is_active == True
    )
    llm_res = await db.execute(llm_stmt)
    llm_conf = llm_res.scalar_one_or_none()
    
    db_provider = LLMProvider(cfg.llm_provider)
    
    # Encrypt key if new key provided
    encrypted_key = None
    key_hint = None
    has_new_key = cfg.google_api_key is not None and cfg.google_api_key != "********" and cfg.google_api_key != ""
    
    if has_new_key:
        await ensure_encryption_key(db)
        encrypted_key = func.pgp_sym_encrypt(cfg.google_api_key, func.current_setting('app.encryption_key'))
        key_hint = f"●●●● {cfg.google_api_key[-4:]}" if len(cfg.google_api_key) >= 4 else "●●●●"
        
    if llm_conf:
        llm_conf.provider = db_provider
        llm_conf.model_name = cfg.google_model
        llm_conf.max_tool_steps = cfg.max_tool_steps
        llm_conf.max_history = cfg.max_history
        llm_conf.updated_by = user_id
        if has_new_key:
            llm_conf.api_key_encrypted = encrypted_key
            llm_conf.api_key_hint = key_hint
    else:
        llm_conf = LLMProviderConfig(
            org_id=org_id,
            created_by=user_id,
            provider=db_provider,
            label="default",
            is_default=True,
            model_name=cfg.google_model,
            max_tool_steps=cfg.max_tool_steps,
            max_history=cfg.max_history,
            api_key_encrypted=encrypted_key,
            api_key_hint=key_hint,
            is_active=True
        )
        db.add(llm_conf)
        
    await db.commit()
    
    return {"status": "success", "message": "Configuration updated successfully."}


@router.get("/models")
async def get_available_models(
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(require_viewer_or_above)
):
    """List standard or dynamically fetched Gemini model options depending on API key availability."""
    org_id = UUID(current_user["org_id"])
    fallback_models = [
        {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro (Recommended)"},
        {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash"},
        {"id": "gemini-2.5-pro", "name": "Gemini 2.5 Pro"},
        {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash"},
    ]

    # Try fetching default LLM provider config from DB
    await ensure_encryption_key(db)
    stmt = (
        select(
            func.pgp_sym_decrypt(
                LLMProviderConfig.api_key_encrypted,
                func.current_setting('app.encryption_key')
            ).label("api_key")
        )
        .where(
            LLMProviderConfig.org_id == org_id,
            LLMProviderConfig.is_default == True,
            LLMProviderConfig.is_active == True
        )
    )
    res = await db.execute(stmt)
    row = res.first()
    
    api_key = None
    if row and row[0]:
        api_key = row[0]
    else:
        # Fallback to system env
        api_key = settings.google_api_key

    if not api_key:
        return fallback_models

    try:
        genai.configure(api_key=api_key)
        # Fetch the models list from Google
        models = genai.list_models()
        
        dynamic_models = []
        for model in models:
            # We filter for models that support generating content (i.e. LLMs)
            if "generateContent" in model.supported_generation_methods:
                # Format model.name (e.g. models/gemini-1.5-pro -> gemini-1.5-pro)
                model_id = model.name.split("/")[-1]
                dynamic_models.append({
                    "id": model_id,
                    "name": f"{model.display_name} ({model_id})"
                })
        
        if dynamic_models:
            return dynamic_models
    except Exception as exc:
        logger.warning("Failed to dynamically fetch Gemini models: %s", exc)

    return fallback_models
