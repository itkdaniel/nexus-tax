"""
Async database layer using SQLAlchemy 2.x async engine.

Drivers:
  - Production: asyncpg (PostgreSQL)
  - Tests:      aiosqlite (SQLite in-memory)

Config injection: call configure_engine(settings) once at startup so all
subsequent callers share the same engine without re-reading env vars.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


_engine: Optional[AsyncEngine] = None
_session_factory = None


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass


def configure_engine(settings) -> None:
    """
    Initialize (or reinitialize) the shared engine from given Settings.
    Called once at app startup by create_app lifespan.
    """
    global _engine, _session_factory

    url = settings.database_url
    is_sqlite = url.startswith("sqlite")

    kwargs: dict = {
        "echo": settings.debug,
    }
    if not is_sqlite:
        kwargs.update({"pool_size": 2, "max_overflow": 8, "pool_pre_ping": True})

    _engine = create_async_engine(url, **kwargs)
    _session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


def get_engine() -> AsyncEngine:
    """Return the shared engine, lazily creating from get_settings() if needed."""
    global _engine
    if _engine is None:
        from app.config import get_settings
        configure_engine(get_settings())
    return _engine


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


@asynccontextmanager
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager for a database session."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db_dep() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session."""
    async with get_db() as session:
        yield session


async def create_tables() -> None:
    """Create all tables if they don't exist (dev/test convenience)."""
    from app.models import (  # noqa: F401 — registers all models
        TaxPeriodModel,
        FederalFormModel,
        StateFormModel,
        TaxBracketModel,
        StandardDeductionModel,
        SpecialTaxRateModel,
        TaxQuestionModel,
        FormRequirementRuleModel,
        QuestionnaireSessionModel,
    )
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_engine() -> None:
    """Dispose connection pool on shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
