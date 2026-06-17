from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.dependencies import get_db
from app.db.models import User
from app.auth.dependencies import require_viewer_or_above
from app.auth.password import hash_password, verify_password

logger = logging.getLogger(__name__)

router = APIRouter()

# ================================================================
# PYDANTIC SCHEMAS
# ================================================================

class ProfileResponse(BaseModel):
    id: UUID
    username: str
    email: str
    display_name: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    role: str
    org_id: UUID
    is_email_verified: bool
    login_count: int

class ProfileUpdateRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    display_name: Optional[str] = None

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str

# ================================================================
# CURRENT USER ENDPOINTS
# ================================================================

@router.get("/me", response_model=ProfileResponse, tags=["users"])
async def get_profile(
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(require_viewer_or_above)
):
    """Get the currently authenticated user's profile."""
    user_id = UUID(current_user["sub"])
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return ProfileResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        first_name=user.first_name,
        last_name=user.last_name,
        role=str(user.role),
        org_id=user.org_id,
        is_email_verified=user.is_email_verified,
        login_count=user.login_count,
    )


@router.patch("/me", response_model=ProfileResponse, tags=["users"])
async def update_profile(
    req: ProfileUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(require_viewer_or_above)
):
    """Update the currently authenticated user's profile fields."""
    user_id = UUID(current_user["sub"])
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if req.first_name is not None:
        user.first_name = req.first_name.strip() or None
    if req.last_name is not None:
        user.last_name = req.last_name.strip() or None
    if req.display_name is not None:
        user.display_name = req.display_name.strip() or None

    # Auto-update display_name from first+last if not explicitly set
    if req.display_name is None and (req.first_name is not None or req.last_name is not None):
        parts = " ".join(p for p in [user.first_name, user.last_name] if p)
        if parts:
            user.display_name = parts

    await db.commit()
    await db.refresh(user)
    return ProfileResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        first_name=user.first_name,
        last_name=user.last_name,
        role=str(user.role),
        org_id=user.org_id,
        is_email_verified=user.is_email_verified,
        login_count=user.login_count,
    )


@router.post("/me/change-password", tags=["users"])
async def change_password(
    req: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(require_viewer_or_above)
):
    """Change the current user's password."""
    if req.new_password != req.confirm_password:
        raise HTTPException(status_code=400, detail="New passwords do not match")

    if len(req.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")

    user_id = UUID(current_user["sub"])
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.password_hash or not verify_password(req.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    user.password_hash = hash_password(req.new_password)
    await db.commit()
    return {"status": "success", "message": "Password changed successfully"}
