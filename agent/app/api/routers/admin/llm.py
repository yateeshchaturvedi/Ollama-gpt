from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.dependencies import get_db
from app.db.models import LLMProviderConfig, LLMProvider
from app.auth.dependencies import require_admin

logger = logging.getLogger(__name__)

router = APIRouter()

# ================================================================
# PYDANTIC SCHEMAS
# ================================================================

class LLMConfigCreate(BaseModel):
    provider: LLMProvider
    label: str = Field(..., min_length=1, max_length=100)
    model_name: str = Field(..., min_length=1)
    is_default: bool = False
    
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    
    temperature: float = Field(0.70, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(8192, ge=1)
    timeout_seconds: int = Field(60, ge=5, le=300)
    max_tool_steps: int = Field(5, ge=1, le=20)
    max_history: int = Field(12, ge=2, le=100)

class LLMConfigResponse(BaseModel):
    id: UUID
    provider: LLMProvider
    label: str
    is_default: bool
    model_name: str
    api_url: Optional[str]
    api_key_hint: Optional[str]
    
    temperature: float
    max_tokens: Optional[int]
    timeout_seconds: int
    max_tool_steps: int
    max_history: int
    
    is_active: bool
    last_test_status: str
    last_test_error: Optional[str]

# ================================================================
# ENDPOINTS
# ================================================================

@router.post("", response_model=LLMConfigResponse, tags=["admin-llm"])
async def create_llm_config(
    req: LLMConfigCreate,
    db: AsyncSession = Depends(get_db),
    admin: Dict[str, Any] = Depends(require_admin)
):
    org_id = UUID(admin["org_id"])
    user_id = UUID(admin["sub"])
    
    # Check duplicate labels
    res = await db.execute(
        select(LLMProviderConfig).where(
            LLMProviderConfig.org_id == org_id,
            LLMProviderConfig.provider == req.provider,
            LLMProviderConfig.label == req.label
        )
    )
    if res.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"LLM Config with label '{req.label}' already exists for provider {req.provider}"
        )
        
    # Reset other defaults if this is default
    if req.is_default:
        await db.execute(
            update(LLMProviderConfig)
            .where(
                LLMProviderConfig.org_id == org_id,
                LLMProviderConfig.provider == req.provider
            )
            .values(is_default=False)
        )
        
    encrypted_key = None
    hint = None
    if req.api_key:
        encryption_key = func.current_setting('app.encryption_key')
        encrypted_key = func.pgp_sym_encrypt(req.api_key, encryption_key)
        hint = f"●●●● {req.api_key[-4:]}" if len(req.api_key) >= 4 else "●●●●"
        
    new_config = LLMProviderConfig(
        org_id=org_id,
        created_by=user_id,
        provider=req.provider,
        label=req.label,
        is_default=req.is_default,
        model_name=req.model_name,
        api_url=req.api_url,
        api_key_encrypted=encrypted_key,
        api_key_hint=hint,
        temperature=req.temperature,
        max_tokens=req.max_tokens,
        timeout_seconds=req.timeout_seconds,
        max_tool_steps=req.max_tool_steps,
        max_history=req.max_history,
        is_active=True
    )
    
    db.add(new_config)
    await db.commit()
    await db.refresh(new_config)
    
    return new_config


@router.get("", response_model=List[LLMConfigResponse], tags=["admin-llm"])
async def list_llm_configs(
    db: AsyncSession = Depends(get_db),
    admin: Dict[str, Any] = Depends(require_admin)
):
    org_id = UUID(admin["org_id"])
    res = await db.execute(
        select(LLMProviderConfig).where(
            LLMProviderConfig.org_id == org_id,
            LLMProviderConfig.is_active == True
        )
    )
    return res.scalars().all()


@router.delete("/{config_id}", tags=["admin-llm"])
async def delete_llm_config(
    config_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: Dict[str, Any] = Depends(require_admin)
):
    org_id = UUID(admin["org_id"])
    
    res = await db.execute(
        select(LLMProviderConfig).where(
            LLMProviderConfig.id == config_id,
            LLMProviderConfig.org_id == org_id
        )
    )
    config = res.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="LLM Config not found")
        
    await db.delete(config)
    await db.commit()
    return {"status": "success", "message": "LLM configuration deleted successfully"}
