from __future__ import annotations

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

# Create async engine for PostgreSQL using asyncpg
engine = create_async_engine(
    settings.database_url,
    echo=False,  # Set to True for SQL queries logging
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=10,
)

# Create Session factory for async sessions
SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Base class for all SQLAlchemy ORM models
class Base(DeclarativeBase):
    pass
