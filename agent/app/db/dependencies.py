from __future__ import annotations

import logging
from typing import AsyncGenerator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.base import SessionLocal
from app.config import settings

logger = logging.getLogger(__name__)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency to yield database sessions.
    
    Sets the database session-level app.encryption_key for pg_sym_encrypt/decrypt usage.
    """
    async with SessionLocal() as session:
        try:
            if settings.db_encryption_key:
                # Use PostgreSQL set_config to securely set connection-local app.encryption_key
                # with parameter binding. The third parameter (is_local) is true, meaning
                # it only lasts for the duration of the current transaction/session.
                await session.execute(
                    text("SELECT set_config('app.encryption_key', :key, true)"),
                    {"key": settings.db_encryption_key}
                )
            yield session
        except Exception as e:
            logger.error(f"Error in database session lifecycle: {e}")
            await session.rollback()
            raise
