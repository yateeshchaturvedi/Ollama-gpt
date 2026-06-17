from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.dependencies import get_db
from app.db.models import PlatformCredential, PlatformType
from app.auth.dependencies import require_admin
from app.api.db_utils import check_plan_limit

logger = logging.getLogger(__name__)

router = APIRouter()

# ================================================================
# PYDANTIC SCHEMAS
# ================================================================

class CredentialCreate(BaseModel):
    platform: PlatformType
    label: str = Field(..., min_length=1, max_length=100)
    token: str = Field(..., min_length=1)
    
    api_url: Optional[str] = None
    github_owner: Optional[str] = None
    github_app_id: Optional[str] = None
    gitlab_group_id: Optional[str] = None
    jenkins_username: Optional[str] = None
    azure_organisation: Optional[str] = None
    azure_project: Optional[str] = None
    token_scopes: List[str] = []

class CredentialResponse(BaseModel):
    id: UUID
    platform: PlatformType
    label: str
    token_hint: Optional[str]
    
    api_url: Optional[str]
    github_owner: Optional[str]
    github_app_id: Optional[str]
    gitlab_group_id: Optional[str]
    jenkins_username: Optional[str]
    azure_organisation: Optional[str]
    azure_project: Optional[str]
    token_scopes: Optional[List[str]]
    
    is_active: bool
    last_test_status: str
    last_test_error: Optional[str]

# ================================================================
# ENDPOINTS
# ================================================================

@router.post("", response_model=CredentialResponse, tags=["admin-credentials"])
async def create_credential(
    req: CredentialCreate,
    db: AsyncSession = Depends(get_db),
    admin: Dict[str, Any] = Depends(require_admin)
):
    org_id = UUID(admin["org_id"])
    user_id = UUID(admin["sub"])
    
    # Enforce plan limit
    can_add = await check_plan_limit(org_id, db, "credentials")
    if not can_add:
        raise HTTPException(
            status_code=403,
            detail="Your organization has reached the maximum number of credentials allowed by its plan."
        )
    
    # Check duplicate labels for this platform
    res = await db.execute(
        select(PlatformCredential).where(
            PlatformCredential.org_id == org_id,
            PlatformCredential.platform == req.platform,
            PlatformCredential.label == req.label
        )
    )
    if res.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"Credential with label '{req.label}' already exists for platform {req.platform}"
        )
        
    # Encrypt the token using pgcrypto pgp_sym_encrypt
    encryption_key = func.current_setting('app.encryption_key')
    encrypted_token = func.pgp_sym_encrypt(req.token, encryption_key)
    
    # Generate token hint (last 4 chars)
    hint = f"●●●● {req.token[-4:]}" if len(req.token) >= 4 else "●●●●"
    
    new_cred = PlatformCredential(
        org_id=org_id,
        created_by=user_id,
        platform=req.platform,
        label=req.label,
        api_url=req.api_url,
        github_owner=req.github_owner,
        github_app_id=req.github_app_id,
        gitlab_group_id=req.gitlab_group_id,
        jenkins_username=req.jenkins_username,
        azure_organisation=req.azure_organisation,
        azure_project=req.azure_project,
        token_encrypted=encrypted_token,
        token_hint=hint,
        token_scopes=req.token_scopes,
        is_active=True
    )
    
    db.add(new_cred)
    await db.commit()
    await db.refresh(new_cred)
    
    return new_cred


@router.get("", response_model=List[CredentialResponse], tags=["admin-credentials"])
async def list_credentials(
    db: AsyncSession = Depends(get_db),
    admin: Dict[str, Any] = Depends(require_admin)
):
    org_id = UUID(admin["org_id"])
    res = await db.execute(
        select(PlatformCredential).where(
            PlatformCredential.org_id == org_id,
            PlatformCredential.is_active == True
        )
    )
    return res.scalars().all()


@router.delete("/{cred_id}", tags=["admin-credentials"])
async def delete_credential(
    cred_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: Dict[str, Any] = Depends(require_admin)
):
    org_id = UUID(admin["org_id"])
    
    res = await db.execute(
        select(PlatformCredential).where(
            PlatformCredential.id == cred_id,
            PlatformCredential.org_id == org_id
        )
    )
    cred = res.scalar_one_or_none()
    if not cred:
        raise HTTPException(status_code=404, detail="Credential not found")
        
    await db.delete(cred)
    await db.commit()
    return {"status": "success", "message": "Credential deleted successfully"}
