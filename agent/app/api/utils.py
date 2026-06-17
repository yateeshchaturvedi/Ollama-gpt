from __future__ import annotations

from typing import Any, Dict
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.db_utils import get_platform_credentials_from_db

async def get_platform_credentials(
    platform_type: str,
    repo_name: str,
    org_id: UUID,
    db: AsyncSession
) -> Dict[str, Any]:
    """Find credentials for a configured repository, or fall back to default settings."""
    return await get_platform_credentials_from_db(platform_type, repo_name, org_id, db)
