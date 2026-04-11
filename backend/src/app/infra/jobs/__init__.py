"""Durable job runner — DB-backed queue using the ``job_runs`` table.

Three public surface areas live here:

* :func:`enqueue` — inserts a row into ``job_runs`` with ``status='queued'``.
* :func:`register_handler` — registers an async handler function for a job type.
* :func:`get_status` — fetches the latest row for a given job id.

Handlers are stored in a module-level dict and looked up by the worker
(see :mod:`app.infra.jobs.worker`). Callers must register handlers before
enqueueing — :func:`enqueue` raises :class:`ValueError` for unknown types.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID, uuid4

import structlog
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now_utc
from app.core.errors import InfraError, NotFoundError

__all__ = [
    "JobHandler",
    "enqueue",
    "register_handler",
    "get_handler",
    "unregister_all_handlers",
    "get_status",
    "register_all_handlers",
]


JobHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]

_HANDLERS: dict[str, JobHandler] = {}
_LOG = structlog.get_logger(__name__)


def register_handler(job_type: str, handler: JobHandler) -> None:
    """Register an async handler for ``job_type``.

    Args:
        job_type: Job type key. Callers pass the same value to :func:`enqueue`.
        handler: Async callable taking the payload dict and returning a result
            dict (stored in ``job_runs.result``).
    """
    _HANDLERS[job_type] = handler


def get_handler(job_type: str) -> JobHandler | None:
    """Return the handler registered for ``job_type`` or ``None``.

    Args:
        job_type: Job type key.

    Returns:
        JobHandler | None: Registered handler, or ``None`` if missing.
    """
    return _HANDLERS.get(job_type)


def unregister_all_handlers() -> None:
    """Clear the handler registry (used by test fixtures)."""
    _HANDLERS.clear()


def register_all_handlers() -> None:
    """Register every known job handler at app startup.

    Batch 0 ships no handlers — :class:`ReportExportHandler` (Batch 6) is the
    first real consumer. This function is still wired into FastAPI lifespan so
    that future batches only need to edit this single call site.
    """
    # Reason: The worker and API both need to see the same registry, so
    # handler registration is centralized here instead of scattered across
    # domain modules.
    return None


async def enqueue(
    job_type: str,
    payload: dict[str, Any],
    *,
    db: AsyncSession,
    user_id: UUID | None = None,
) -> UUID:
    """Insert a new queued row into ``job_runs`` and return its id.

    Args:
        job_type: Registered handler key.
        payload: JSON-serializable payload dict.
        db: Active async session. Caller owns commit timing.
        user_id: Optional initiating user id.

    Returns:
        UUID: New ``job_runs.id``.

    Raises:
        ValueError: If ``job_type`` has no registered handler.
        InfraError: ``SYS_001`` on database failure.
    """
    if job_type not in _HANDLERS:
        raise ValueError(f"No handler registered for job_type={job_type!r}")
    job_id = uuid4()
    enqueued_at = now_utc()
    try:
        await db.execute(
            text(
                "INSERT INTO job_runs (id, job_type, status, payload, enqueued_by, "
                "enqueued_at, attempts) "
                "VALUES (:id, :job_type, 'queued', CAST(:payload AS JSONB), :user_id, "
                ":enqueued_at, 0)"
            ),
            {
                "id": str(job_id),
                "job_type": job_type,
                "payload": _json_dumps(payload),
                "user_id": str(user_id) if user_id is not None else None,
                "enqueued_at": enqueued_at,
            },
        )
    except SQLAlchemyError as exc:
        raise InfraError("SYS_001", f"enqueue failed: {exc}") from exc
    _LOG.info("jobs.enqueued", job_id=str(job_id), job_type=job_type)
    return job_id


async def get_status(job_id: UUID, db: AsyncSession) -> dict[str, Any]:
    """Return the current metadata for a job.

    Args:
        job_id: ``job_runs.id``.
        db: Active async session.

    Returns:
        dict[str, Any]: Keys ``id``, ``status``, ``job_type``, ``enqueued_at``,
        ``started_at``, ``finished_at``, ``attempts``, ``error_message``,
        ``result``.

    Raises:
        NotFoundError: ``UPLOAD_008`` (generic 404 code) if no row matches.
        InfraError: ``SYS_001`` on database failure.
    """
    try:
        row = (
            (
                await db.execute(
                    text(
                        "SELECT id, job_type, status, enqueued_at, started_at, finished_at, "
                        "attempts, error_message, result FROM job_runs WHERE id = :id"
                    ),
                    {"id": str(job_id)},
                )
            )
            .mappings()
            .first()
        )
    except SQLAlchemyError as exc:
        raise InfraError("SYS_001", f"get_status failed: {exc}") from exc
    if row is None:
        raise NotFoundError("UPLOAD_008", f"Job not found: {job_id}")
    return dict(row)


def _json_dumps(value: dict[str, Any]) -> str:
    """Serialize ``value`` to a JSON string compatible with Postgres JSONB.

    Uses stdlib ``json`` with ``default=str`` so UUIDs and datetimes survive.

    Args:
        value: Dict payload.

    Returns:
        str: JSON-encoded string.
    """
    import json

    return json.dumps(value, default=str)
