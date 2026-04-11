"""Async SQLAlchemy engine + session factory.

Exposes a FastAPI-friendly :func:`get_session` generator that yields an
:class:`~sqlalchemy.ext.asyncio.AsyncSession`. The session is rolled back on
any exception raised inside the dependency scope; the caller (route handler
or service) is responsible for explicit commits on success paths.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings
from app.core.errors import InfraError

__all__ = [
    "configure_engine",
    "dispose_engine",
    "get_session",
    "get_engine",
    "get_session_factory",
]


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def configure_engine(
    database_url: str | None = None,
    pool_size: int | None = None,
    max_overflow: int | None = None,
) -> AsyncEngine:
    """Create (or replace) the module-level async engine and session factory.

    Idempotent: if the engine is already configured and no arguments differ,
    the existing engine is returned.

    Args:
        database_url: Async SQLAlchemy URL. Defaults to
            :attr:`Settings.database_url`.
        pool_size: Connection pool size. Defaults to
            :attr:`Settings.database_pool_size`.
        max_overflow: Pool overflow. Defaults to
            :attr:`Settings.database_max_overflow`.

    Returns:
        AsyncEngine: The configured engine.
    """
    global _engine, _session_factory

    settings = get_settings()
    url = database_url if database_url is not None else settings.database_url
    size = pool_size if pool_size is not None else settings.database_pool_size
    overflow = max_overflow if max_overflow is not None else settings.database_max_overflow

    _engine = create_async_engine(
        url,
        pool_size=size,
        max_overflow=overflow,
        pool_pre_ping=True,
        future=True,
    )
    _session_factory = async_sessionmaker(
        bind=_engine,
        expire_on_commit=False,
        autoflush=False,
    )
    return _engine


async def dispose_engine() -> None:
    """Dispose the async engine and reset the module-level state.

    Called from FastAPI lifespan shutdown. Safe to call even when no engine
    was configured (idempotent).
    """
    global _engine, _session_factory

    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


def get_engine() -> AsyncEngine:
    """Return the module-level engine, configuring on demand.

    Returns:
        AsyncEngine: The active engine.

    Raises:
        InfraError: ``SYS_001`` if engine construction fails.
    """
    if _engine is None:
        try:
            configure_engine()
        except SQLAlchemyError as exc:  # pragma: no cover — config error
            raise InfraError("SYS_001", f"Engine configuration failed: {exc}") from exc
    assert _engine is not None
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the module-level session factory, configuring on demand.

    Returns:
        async_sessionmaker[AsyncSession]: Active session factory.
    """
    if _session_factory is None:
        get_engine()
    assert _session_factory is not None
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield a per-request :class:`AsyncSession`.

    Used as a FastAPI dependency (``Depends(get_session)``). On any exception
    raised inside the dependency scope, the session is rolled back before it
    is closed. On the clean-exit path, the session is closed without a
    commit — callers own commit timing.

    Yields:
        AsyncSession: An active database session.

    Raises:
        InfraError: ``SYS_001`` if the underlying driver fails to connect.
    """
    factory = get_session_factory()
    session: AsyncSession = factory()
    try:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
    except SQLAlchemyError as exc:
        raise InfraError("SYS_001", f"Database error: {exc}") from exc
    finally:
        await session.close()
