"""
Async SQLAlchemy engine + session factory.
Supports both SQLite (dev) and PostgreSQL (production) via DATABASE_URL.
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.config import settings
from .models import Base

engine = create_async_engine(
    settings.db.url,
    echo=settings.db.echo,
    future=True,
    # PostgreSQL connection pool settings (ignored by SQLite)
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,   # auto-reconnect on stale connections
)

AsyncSessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """
    Create all tables on startup.
    In production with Alembic, this is a no-op safety net —
    Alembic handles the actual schema. Still useful for fresh SQLite dev DBs.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
