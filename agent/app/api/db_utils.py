from __future__ import annotations

import logging
from typing import Any, Dict
from uuid import UUID
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Repository, PlatformCredential, PlatformType
from app.config import settings

logger = logging.getLogger(__name__)

async def ensure_encryption_key(db: AsyncSession) -> None:
    """Ensure the connection-local app.encryption_key is set for pgcrypto operations."""
    if settings.db_encryption_key:
        try:
            await db.execute(
                text("SELECT set_config('app.encryption_key', :key, true)"),
                {"key": settings.db_encryption_key}
            )
        except Exception as e:
            logger.error(f"Failed to set db encryption key config: {e}")

async def get_platform_credentials_from_db(
    platform_type: str,
    repo_name: str,
    org_id: UUID,
    db: AsyncSession
) -> Dict[str, Any]:
    """Find credentials for a configured repository in the database, or fall back to system defaults."""
    # Map 'azure' platform type to database enum value 'azure_devops'
    db_platform = "azure_devops" if platform_type == "azure" else platform_type

    await ensure_encryption_key(db)

    # Query Repository and its linked PlatformCredential
    stmt = (
        select(Repository, PlatformCredential)
        .outerjoin(PlatformCredential, Repository.credential_id == PlatformCredential.id)
        .where(
            Repository.org_id == org_id,
            Repository.platform == db_platform,
            Repository.name == repo_name,
            Repository.is_active == True
        )
    )
    
    try:
        result = await db.execute(stmt)
        row = result.first()
    except Exception as e:
        logger.error(f"Database query failed in get_platform_credentials_from_db: {e}")
        row = None

    if row:
        repo, cred = row
        token = ""
        url = ""
        
        if cred:
            if cred.token_encrypted:
                try:
                    decrypt_stmt = select(
                        func.pgp_sym_decrypt(
                            PlatformCredential.token_encrypted,
                            func.current_setting('app.encryption_key')
                        )
                    ).where(PlatformCredential.id == cred.id)
                    token_res = await db.execute(decrypt_stmt)
                    token = token_res.scalar() or ""
                except Exception as e:
                    logger.error(f"Failed to decrypt credential token for {platform_type}/{repo_name}: {e}")
                    token = ""
            url = cred.api_url or ""
            
        extra = repo.extra or {}
        res = {
            "token": token,
            "url": url,
            "extra": extra
        }
        if cred and cred.jenkins_username:
            res["user"] = cred.jenkins_username
        return res

    # Enforce tenant isolation: Do not fall back to system-level environment variables
    # if the organization has not configured its own credentials.
    return {"token": "", "url": "", "extra": {}}

async def get_llm_config_from_db(org_id: UUID, db: AsyncSession) -> Dict[str, Any]:
    """Find the LLM provider configuration for the organization."""
    from app.db.models import LLMProviderConfig
    
    await ensure_encryption_key(db)
    
    stmt = (
        select(
            LLMProviderConfig.provider,
            LLMProviderConfig.model_name,
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
    
    try:
        res = await db.execute(stmt)
        row = res.first()
    except Exception as e:
        logger.error(f"Database query failed in get_llm_config_from_db: {e}")
        row = None

    if row:
        provider, model_name, api_key = row
        return {
            "provider": str(provider) if provider else None,
            "model_name": model_name,
            "api_key": api_key
        }
    return {}

async def check_plan_limit(
    org_id: UUID,
    db: AsyncSession,
    resource_type: str
) -> bool:
    """Check if the organization has reached its plan limit for a resource type.
    resource_type can be 'users', 'repos', 'credentials'.
    Returns True if limit is NOT reached (can proceed), False if limit is reached.
    """
    from app.db.models import Organisation, PlanTier, User, Repository, PlatformCredential
    
    # Get org plan limits
    stmt = (
        select(PlanTier)
        .join(Organisation, Organisation.plan_tier_id == PlanTier.id)
        .where(Organisation.id == org_id)
    )
    plan = (await db.execute(stmt)).scalar_one_or_none()
    if not plan:
        return False
        
    if resource_type == "users":
        count_stmt = select(func.count(User.id)).where(User.org_id == org_id, User.is_active == True)
        current = (await db.execute(count_stmt)).scalar() or 0
        return current < plan.max_users
    elif resource_type == "repos":
        count_stmt = select(func.count(Repository.id)).where(Repository.org_id == org_id, Repository.is_active == True)
        current = (await db.execute(count_stmt)).scalar() or 0
        return current < plan.max_repos
    elif resource_type == "credentials":
        count_stmt = select(func.count(PlatformCredential.id)).where(PlatformCredential.org_id == org_id, PlatformCredential.is_active == True)
        current = (await db.execute(count_stmt)).scalar() or 0
        return current < plan.max_credentials
        
    return False
