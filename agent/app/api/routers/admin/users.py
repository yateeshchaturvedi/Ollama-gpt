from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.dependencies import get_db
from app.db.models import User, UserRole, OrgInvite, Organisation
from app.auth.dependencies import require_admin
from app.auth.password import hash_password
from app.rate_limit import limiter
from app.api.db_utils import check_plan_limit
from app.utils.email import send_invite_email

logger = logging.getLogger(__name__)

router = APIRouter()

# ================================================================
# PYDANTIC SCHEMAS
# ================================================================

class InviteCreate(BaseModel):
    email: str
    role: UserRole = UserRole.viewer
    note: Optional[str] = None

class InviteResponse(BaseModel):
    id: UUID
    invited_email: str
    assigned_role: UserRole
    invite_code: str
    expires_at: datetime
    created_at: datetime

class InviteAccept(BaseModel):
    invite_code: str
    username: str
    password: str = Field(..., min_length=8)
    display_name: Optional[str] = None

class MemberResponse(BaseModel):
    id: UUID
    username: str
    email: str
    display_name: Optional[str]
    role: UserRole
    is_active: bool
    is_invited: bool
    created_at: datetime

class RoleUpdateRequest(BaseModel):
    role: UserRole

# ================================================================
# ADMIN-ONLY MEMBER MANAGEMENT
# ================================================================

@router.get("", response_model=List[MemberResponse], tags=["admin-users"])
async def list_members(
    db: AsyncSession = Depends(get_db),
    admin: Dict[str, Any] = Depends(require_admin)
):
    org_id = UUID(admin["org_id"])
    res = await db.execute(select(User).where(User.org_id == org_id).order_by(User.created_at))
    return res.scalars().all()


@router.delete("/{user_id}", tags=["admin-users"])
async def delete_member(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: Dict[str, Any] = Depends(require_admin)
):
    org_id = UUID(admin["org_id"])
    caller_id = UUID(admin["sub"])

    if user_id == caller_id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")

    res = await db.execute(
        select(User).where(
            User.id == user_id,
            User.org_id == org_id
        )
    )
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent deleting the owner
    if user.role == UserRole.owner:
        raise HTTPException(status_code=400, detail="The organisation owner cannot be deleted")

    await db.delete(user)
    await db.commit()
    return {"status": "success", "message": "User removed from organisation successfully"}


@router.patch("/{user_id}/role", response_model=MemberResponse, tags=["admin-users"])
async def update_member_role(
    user_id: UUID,
    req: RoleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin: Dict[str, Any] = Depends(require_admin)
):
    """Change a member's role. Owners cannot be demoted, and you cannot change your own role."""
    org_id = UUID(admin["org_id"])
    caller_id = UUID(admin["sub"])
    caller_role = admin.get("role")

    if user_id == caller_id:
        raise HTTPException(status_code=400, detail="You cannot change your own role")

    res = await db.execute(
        select(User).where(User.id == user_id, User.org_id == org_id)
    )
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.role == UserRole.owner:
        raise HTTPException(status_code=400, detail="The organisation owner's role cannot be changed")

    # Prevent non-owners from assigning admin role
    if req.role in (UserRole.owner, UserRole.admin) and caller_role != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can assign admin or owner roles")

    user.role = req.role
    await db.commit()
    await db.refresh(user)
    return user

# ================================================================
# INVITES MANAGEMENT
# ================================================================

@router.get("/invites", response_model=List[InviteResponse], tags=["admin-users"])
async def list_invites(
    db: AsyncSession = Depends(get_db),
    admin: Dict[str, Any] = Depends(require_admin)
):
    """List all pending (non-expired, non-accepted, non-revoked) invites for this org."""
    org_id = UUID(admin["org_id"])
    now = datetime.now(timezone.utc)
    res = await db.execute(
        select(OrgInvite).where(
            OrgInvite.org_id == org_id,
            OrgInvite.accepted_at.is_(None),
            OrgInvite.revoked_at.is_(None),
            OrgInvite.expires_at > now
        ).order_by(OrgInvite.created_at.desc())
    )
    return res.scalars().all()


@router.post("/invites", response_model=InviteResponse, tags=["admin-users"])
async def create_invite(
    req: InviteCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    admin: Dict[str, Any] = Depends(require_admin)
):
    org_id = UUID(admin["org_id"])
    invited_by_id = UUID(admin["sub"])
    invited_by_username = admin.get("username", "an admin")

    # Enforce plan limit
    can_invite = await check_plan_limit(org_id, db, "users")
    if not can_invite:
        raise HTTPException(
            status_code=403,
            detail="Your organization has reached the maximum number of users allowed by its plan."
        )

    # Check if email is already registered in this org
    res_user = await db.execute(
        select(User).where(
            User.org_id == org_id,
            User.email == req.email
        )
    )
    if res_user.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User with this email is already registered")

    # Check for existing pending invite to this email
    now = datetime.now(timezone.utc)
    res_existing = await db.execute(
        select(OrgInvite).where(
            OrgInvite.org_id == org_id,
            OrgInvite.invited_email == req.email,
            OrgInvite.accepted_at.is_(None),
            OrgInvite.revoked_at.is_(None),
            OrgInvite.expires_at > now
        )
    )
    if res_existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="A pending invite already exists for this email address")

    # Generate highly secure invite code
    invite_code = secrets.token_urlsafe(32)
    expires_at = now + timedelta(days=7)

    invite = OrgInvite(
        org_id=org_id,
        invited_email=req.email,
        assigned_role=req.role,
        invite_note=req.note,
        invite_code=invite_code,
        invited_by=invited_by_id,
        expires_at=expires_at
    )

    db.add(invite)
    await db.commit()
    await db.refresh(invite)

    # Send invite email in the background
    background_tasks.add_task(send_invite_email, req.email, invite_code, invited_by_username)

    return invite


@router.delete("/invites/{invite_id}", tags=["admin-users"])
async def revoke_invite(
    invite_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: Dict[str, Any] = Depends(require_admin)
):
    """Revoke a pending invite."""
    org_id = UUID(admin["org_id"])
    caller_id = UUID(admin["sub"])

    res = await db.execute(
        select(OrgInvite).where(OrgInvite.id == invite_id, OrgInvite.org_id == org_id)
    )
    invite = res.scalar_one_or_none()
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")

    if invite.accepted_at:
        raise HTTPException(status_code=400, detail="Invite has already been accepted")

    invite.revoked_at = datetime.now(timezone.utc)
    invite.revoked_by = caller_id
    await db.commit()
    return {"status": "success", "message": "Invite revoked"}


@router.post("/invites/accept", tags=["auth"])
@limiter.limit("10/minute")
async def accept_invite(req: InviteAccept, request: Request, db: AsyncSession = Depends(get_db)):
    """Public endpoint to accept an invite code, registering a new user."""
    # Find active invite
    res = await db.execute(
        select(OrgInvite).where(
            OrgInvite.invite_code == req.invite_code,
            OrgInvite.accepted_at.is_(None),
            OrgInvite.revoked_at.is_(None)
        )
    )
    invite = res.scalar_one_or_none()

    if not invite or invite.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid or expired invite code")

    # Enforce plan limit
    can_accept = await check_plan_limit(invite.org_id, db, "users")
    if not can_accept:
        raise HTTPException(
            status_code=403,
            detail="The organization has reached the maximum number of users allowed by its plan."
        )

    # Check username uniqueness in the org
    res_username = await db.execute(
        select(User).where(User.org_id == invite.org_id, User.username == req.username)
    )
    if res_username.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username is already taken in this organisation")

    # Create new User
    new_user = User(
        org_id=invite.org_id,
        email=invite.invited_email,
        username=req.username,
        display_name=req.display_name or req.username.capitalize(),
        password_hash=hash_password(req.password),
        role=invite.assigned_role,
        is_email_verified=True,  # Trust because the invite was sent to their email
        is_invited=True,
        invited_by=invite.invited_by
    )
    db.add(new_user)
    await db.flush()  # Populate user ID

    # Mark invite as accepted
    invite.accepted_at = datetime.now(timezone.utc)
    invite.accepted_by = new_user.id

    await db.commit()
    return {"status": "success", "message": "Invite accepted. You can now login."}
