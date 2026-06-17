from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import RefreshToken

def hash_token(token: str) -> str:
    """Return the SHA-256 hash of a raw token string."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

async def create_refresh_token(
    db: AsyncSession,
    user_id: UUID,
    org_id: UUID,
    portal: str,
    family_id: Optional[UUID] = None,
    device_label: Optional[str] = None,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None
) -> str:
    """Create a new refresh token and store its hash in the database.
    
    Returns the raw UUID token (returned to client only once).
    """
    raw_token = str(uuid.uuid4())
    token_hash = hash_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    
    db_token = RefreshToken(
        user_id=user_id,
        org_id=org_id,
        token_hash=token_hash,
        family_id=family_id or uuid.uuid4(),
        portal=portal,
        device_label=device_label,
        user_agent=user_agent,
        ip_address=ip_address,
        expires_at=expires_at
    )
    db.add(db_token)
    await db.commit()
    return raw_token

async def rotate_refresh_token(
    db: AsyncSession,
    raw_token: str,
    device_label: Optional[str] = None,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None
) -> tuple[str, RefreshToken]:
    """Rotate an existing active refresh token, issuing a new one in the same family.
    
    If the presented token is already revoked, reuse/theft detection is triggered,
    revoking all tokens sharing the same family_id immediately.
    """
    token_hash = hash_token(raw_token)
    
    # Query token regardless of revocation state to check for reuse
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    db_token = result.scalar_one_or_none()
    
    if not db_token:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
        
    # REUSE / THEFT DETECTION
    if db_token.is_revoked:
        # Revoke entire token family
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == db_token.family_id)
            .values(
                is_revoked=True,
                revoked_at=datetime.now(timezone.utc),
                revoke_reason="theft_detected"
            )
        )
        await db.commit()
        raise HTTPException(
            status_code=401,
            detail="Security Alert: Reuse of rotated refresh token detected. All sessions revoked."
        )
        
    # EXPIRY CHECK
    if db_token.expires_at < datetime.now(timezone.utc):
        db_token.is_revoked = True
        db_token.revoked_at = datetime.now(timezone.utc)
        db_token.revoke_reason = "expired"
        await db.commit()
        raise HTTPException(status_code=401, detail="Refresh token expired")
        
    # Create new rotated token
    new_raw_token = str(uuid.uuid4())
    new_hash = hash_token(new_raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    
    new_db_token = RefreshToken(
        user_id=db_token.user_id,
        org_id=db_token.org_id,
        token_hash=new_hash,
        family_id=db_token.family_id,
        portal=db_token.portal,
        device_label=device_label or db_token.device_label,
        user_agent=user_agent or db_token.user_agent,
        ip_address=ip_address or db_token.ip_address,
        expires_at=expires_at,
        rotation_count=db_token.rotation_count + 1
    )
    db.add(new_db_token)
    await db.flush() # populate ID for linkage
    
    # Revoke old token and chain it
    db_token.is_revoked = True
    db_token.revoked_at = datetime.now(timezone.utc)
    db_token.revoke_reason = "rotated"
    db_token.replaced_by = new_db_token.id
    
    await db.commit()
    return new_raw_token, new_db_token

async def revoke_refresh_token(db: AsyncSession, raw_token: str) -> None:
    """Revoke a specific refresh token (e.g., on logout)."""
    token_hash = hash_token(raw_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    db_token = result.scalar_one_or_none()
    if db_token and not db_token.is_revoked:
        db_token.is_revoked = True
        db_token.revoked_at = datetime.now(timezone.utc)
        db_token.revoke_reason = "logout"
        await db.commit()
