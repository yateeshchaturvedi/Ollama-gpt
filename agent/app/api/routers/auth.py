from __future__ import annotations

import logging
import uuid
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.rate_limit import limiter

from app.config import settings
from app.db.dependencies import get_db
from app.db.models import (
    Organisation, User, UserRole, AgentSettings, VerificationToken,
    OAuthConnection, OAuthProvider
)
from app.auth.password import hash_password, verify_password
from app.auth.jwt import create_access_token
from app.auth.refresh import create_refresh_token, rotate_refresh_token, revoke_refresh_token
from app.auth.oauth import get_github_authorize_url, exchange_github_code, get_github_user_profile
from app.utils.email import send_verification_email

logger = logging.getLogger(__name__)

router = APIRouter()

# ================================================================
# PYDANTIC SCHEMAS
# ================================================================

class RegisterRequest(BaseModel):
    org_slug: str = Field(..., pattern="^[a-z0-9][a-z0-9\\-]{1,48}[a-z0-9]$")
    org_display_name: str
    email: str
    username: str
    password: str = Field(..., min_length=8)
    first_name: Optional[str] = None
    last_name: Optional[str] = None

class RegisterResponse(BaseModel):
    status: str
    message: str
    org_id: UUID
    user_id: UUID

class VerifyEmailRequest(BaseModel):
    token: str

class LoginRequest(BaseModel):
    org_slug: str
    username_or_email: str
    password: str

class UserResponse(BaseModel):
    id: UUID
    username: str
    email: str
    role: str
    org_id: UUID

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse

class RefreshRequest(BaseModel):
    refresh_token: str

class LogoutRequest(BaseModel):
    refresh_token: str

# ================================================================
# REGISTER & VERIFY ENDPOINTS
# ================================================================

@router.post("/register", response_model=RegisterResponse, tags=["auth"])
@limiter.limit("5/minute")
async def register(req: RegisterRequest, request: Request, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    # Check if slug is unique
    org_exists = await db.execute(
        select(Organisation).where(Organisation.slug == req.org_slug)
    )
    if org_exists.scalars().first():
        raise HTTPException(status_code=400, detail="Organisation slug is already taken")

    # Check if email is already in use globally (across all orgs)
    email_exists = await db.execute(select(User).where(User.email == req.email))
    if email_exists.scalars().first():
        raise HTTPException(status_code=400, detail="An account with this email address already exists.")

    # Create new Organisation (defaults to plan_tier_id=1, which is "free")
    new_org = Organisation(
        slug=req.org_slug,
        display_name=req.org_display_name,
        is_email_verified=False
    )
    db.add(new_org)
    await db.flush() # Populate new_org.id

    # Compute display name from first/last name or username fallback
    display_name_parts = " ".join(p for p in [req.first_name, req.last_name] if p)
    display_name = display_name_parts.strip() if display_name_parts.strip() else req.username.capitalize()

    # Create owner User
    new_user = User(
        org_id=new_org.id,
        email=req.email,
        username=req.username,
        display_name=display_name,
        first_name=req.first_name,
        last_name=req.last_name,
        password_hash=hash_password(req.password),
        role=UserRole.owner,
        is_email_verified=False
    )
    db.add(new_user)
    await db.flush() # Populate new_user.id

    # Create default AgentSettings for the new org
    default_settings = AgentSettings(
        org_id=new_org.id,
        dangerous_actions_require_confirm=True,
        confirmation_token=secrets.token_urlsafe(8),
        safe_workspace_root="/app"
    )
    db.add(default_settings)

    # Generate one-time email verification token
    raw_token = str(uuid.uuid4())
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

    verification_token = VerificationToken(
        user_id=new_user.id,
        org_id=new_org.id,
        token_hash=token_hash,
        purpose="email_verify",
        expires_at=expires_at
    )
    db.add(verification_token)
    
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Registration failed. Email or organisation already exists.")

    # Dispatch the verification email asynchronously via background tasks
    background_tasks.add_task(send_verification_email, req.email, raw_token)

    return RegisterResponse(
        status="success",
        message="Registration successful. Please verify your email.",
        org_id=new_org.id,
        user_id=new_user.id
    )


@router.post("/verify-email", tags=["auth"])
async def verify_email(req: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    token_hash = hashlib.sha256(req.token.encode("utf-8")).hexdigest()
    
    result = await db.execute(
        select(VerificationToken).where(
            VerificationToken.token_hash == token_hash,
            VerificationToken.purpose == "email_verify",
            VerificationToken.used_at.is_(None)
        )
    )
    vt = result.scalars().first()
    
    if not vt or vt.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")
        
    # Mark as verified
    vt.used_at = datetime.now(timezone.utc)
    
    # Verify User
    res_user = await db.execute(select(User).where(User.id == vt.user_id))
    user = res_user.scalar_one()
    user.is_email_verified = True
    
    # Verify Org
    res_org = await db.execute(select(Organisation).where(Organisation.id == vt.org_id))
    org = res_org.scalar_one()
    org.is_email_verified = True
    
    await db.commit()
    return {"status": "success", "message": "Email verified successfully"}

# ================================================================
# PASSWORD LOGIN ENDPOINT
# ================================================================

@router.post("/login", response_model=TokenResponse, tags=["auth"])
@limiter.limit("10/minute")
async def login(req: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    # Find Org
    res_org = await db.execute(select(Organisation).where(Organisation.slug == req.org_slug))
    org = res_org.scalars().first()
    if not org or not org.is_active:
        raise HTTPException(status_code=401, detail="Invalid organisation or credentials")
        
    # Find User (username OR email)
    res_user = await db.execute(
        select(User).where(
            User.org_id == org.id,
            (User.username == req.username_or_email) | (User.email == req.username_or_email)
        )
    )
    user = res_user.scalars().first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid organisation or credentials")

    # Lockout check
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Account is temporarily locked. Try again later.")
        
    # Verify Password
    if not user.password_hash or not verify_password(req.password, user.password_hash):
        # Update failed login count
        user.failed_login_count += 1
        if user.failed_login_count >= 5:
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
        await db.commit()
        raise HTTPException(status_code=401, detail="Invalid organisation or credentials")
        
    # Verify email
    if not user.is_email_verified:
        raise HTTPException(status_code=403, detail="Please verify your email before logging in")
        
    # Reset lockouts and updates last login info
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = datetime.now(timezone.utc)
    user.last_login_ip = request.client.host if request.client else None
    user.login_count += 1
    
    # Generate stateless access token (JWT)
    access_token = create_access_token(
        user_id=str(user.id),
        org_id=str(org.id),
        role=str(user.role),
        username=user.username
    )
    
    # Generate db-stored refresh token
    refresh_token = await create_refresh_token(
        db=db,
        user_id=user.id,
        org_id=org.id,
        portal="admin" if user.can_access_admin_portal else "user",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent")
    )
    
    # Set secure cookies
    response.set_cookie("access_token", access_token, httponly=True, secure=True, samesite="strict", max_age=15*60, path="/")
    response.set_cookie("refresh_token", refresh_token, httponly=True, secure=True, samesite="strict", max_age=30*86400, path="/")
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            role=user.role,
            org_id=org.id
        )
    )

# ================================================================
# REFRESH & LOGOUT
# ================================================================

@router.post("/refresh", tags=["auth"])
@limiter.limit("20/minute")
async def refresh(req: RefreshRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    # Rotate refresh token (triggers theft detection inside helper if reused)
    new_refresh, db_token = await rotate_refresh_token(
        db, 
        req.refresh_token,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent")
    )
    
    # Load User
    res_user = await db.execute(select(User).where(User.id == db_token.user_id))
    user = res_user.scalar_one()
    
    # Verify portal
    expected_portal = "admin" if user.can_access_admin_portal else "user"
    if db_token.portal != expected_portal:
        raise HTTPException(status_code=403, detail="Token not valid for this portal")
    
    # Generate new access token
    new_access = create_access_token(
        user_id=str(user.id),
        org_id=str(db_token.org_id),
        role=str(user.role),
        username=user.username
    )
    
    # Set secure cookies
    response.set_cookie("access_token", new_access, httponly=True, secure=True, samesite="strict", max_age=15*60, path="/")
    response.set_cookie("refresh_token", new_refresh, httponly=True, secure=True, samesite="strict", max_age=30*86400, path="/")
    
    return {
        "access_token": new_access,
        "refresh_token": new_refresh,
        "token_type": "bearer"
    }


@router.post("/logout", tags=["auth"])
async def logout(req: LogoutRequest, response: Response, db: AsyncSession = Depends(get_db)):
    await revoke_refresh_token(db, req.refresh_token)
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"status": "success", "message": "Logged out successfully"}

# ================================================================
# GITHUB OAUTH LOGIN FLOW
# ================================================================

@router.get("/github", tags=["auth"])
async def github_login(response: Response):
    """Redirect frontend to GitHub authorization page."""
    state = secrets.token_urlsafe(32)
    response.set_cookie("oauth_state", state, httponly=True, secure=True, samesite="lax", max_age=600, path="/")
    auth_url = await get_github_authorize_url(state=state)
    return {"url": auth_url}


@router.get("/github/callback", tags=["auth"])
async def github_callback(code: str, request: Request, response: Response, state: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """Handle code exchange and sign in/register user."""
    cookie_state = request.cookies.get("oauth_state")
    if not cookie_state or cookie_state != state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state token. Possible CSRF attack.")
    response.delete_cookie("oauth_state", path="/")

    # 1. Exchange code for access token
    token_data = await exchange_github_code(code)
    if not token_data or "access_token" not in token_data:
        raise HTTPException(status_code=400, detail="Failed to retrieve OAuth token from GitHub")
        
    access_token = token_data["access_token"]
    
    # 2. Get user profile
    profile = await get_github_user_profile(access_token)
    if not profile or "id" not in profile:
        raise HTTPException(status_code=400, detail="Failed to fetch GitHub profile")
        
    github_user_id = str(profile["id"])
    github_username = profile["login"]
    github_email = profile.get("email") or f"{github_username}@github.com"
    github_avatar = profile.get("avatar_url")
    
    # 3. Lookup existing OAuth connection
    res_conn = await db.execute(
        select(OAuthConnection).where(
            OAuthConnection.provider == OAuthProvider.github,
            OAuthConnection.provider_user_id == github_user_id
        )
    )
    oauth_conn = res_conn.scalars().first()
    
    if oauth_conn:
        # User exists and is linked. Log them in!
        res_user = await db.execute(select(User).where(User.id == oauth_conn.user_id))
        user = res_user.scalar_one()
        res_org = await db.execute(select(Organisation).where(Organisation.id == user.org_id))
        org = res_org.scalar_one()
    else:
        # No OAuth link. Check if a user with this email exists in any organization
        res_user_by_email = await db.execute(select(User).where(User.email == github_email))
        user = res_user_by_email.scalars().first()
        
        if user:
            # User exists by email! Bind this GitHub account to this user
            org = await db.get(Organisation, user.org_id)
            oauth_conn = OAuthConnection(
                user_id=user.id,
                org_id=org.id,
                provider=OAuthProvider.github,
                provider_user_id=github_user_id,
                provider_username=github_username,
                provider_email=github_email,
                provider_avatar_url=github_avatar
            )
            db.add(oauth_conn)
        else:
            # New register onboarding! Create a new organisation + owner user
            # Find a unique slug
            base_slug = github_username.lower().replace("_", "-")
            if not base_slug.isalnum():
                base_slug = "".join([c for c in base_slug if c.isalnum() or c == "-"])
            # Ensure slug conforms
            if not base_slug:
                base_slug = "github-user"
            slug = base_slug
            
            # Check unique slug
            slug_index = 1
            while True:
                res_slug = await db.execute(select(Organisation).where(Organisation.slug == slug))
                if not res_slug.scalars().first():
                    break
                slug = f"{base_slug}-{slug_index}"
                slug_index += 1
                
            org = Organisation(
                slug=slug,
                display_name=f"{github_username}'s Team",
                is_email_verified=True # Trusted email from GitHub OAuth
            )
            db.add(org)
            await db.flush()
            
            user = User(
                org_id=org.id,
                email=github_email,
                username=github_username,
                display_name=profile.get("name") or github_username.capitalize(),
                avatar_url=github_avatar,
                password_hash=None, # OAuth only user
                role=UserRole.owner,
                is_email_verified=True # Trusted from GitHub OAuth
            )
            db.add(user)
            await db.flush()
            
            # Default AgentSettings
            default_settings = AgentSettings(
                org_id=org.id,
                dangerous_actions_require_confirm=True,
                confirmation_token="CONFIRM",
                safe_workspace_root="/app"
            )
            db.add(default_settings)
            
            # Create OAuth connection link
            oauth_conn = OAuthConnection(
                user_id=user.id,
                org_id=org.id,
                provider=OAuthProvider.github,
                provider_user_id=github_user_id,
                provider_username=github_username,
                provider_email=github_email,
                provider_avatar_url=github_avatar
            )
            db.add(oauth_conn)
            
        await db.commit()
        
    # Generate access & refresh tokens
    access_token = create_access_token(
        user_id=str(user.id),
        org_id=str(org.id),
        role=str(user.role),
        username=user.username
    )
    
    refresh_token = await create_refresh_token(
        db=db,
        user_id=user.id,
        org_id=org.id,
        portal="admin" if user.can_access_admin_portal else "user",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent")
    )
    
    # Set secure cookies
    response.set_cookie("access_token", access_token, httponly=True, secure=True, samesite="strict", max_age=15*60, path="/")
    response.set_cookie("refresh_token", refresh_token, httponly=True, secure=True, samesite="strict", max_age=30*86400, path="/")
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            role=user.role,
            org_id=org.id
        )
    )
