"""Durable job worker loop — polls ``job_runs`` for queued rows and runs handlers.

Runs in its own OS process (``python -m app.infra.jobs.worker``) or, during
tests, as an in-process task that advances by a fixed number of iterations.
The loop uses ``SELECT ... FOR UPDATE SKIP LOCKED`` so that multiple worker
processes can share the same ``job_runs`` table without double-claiming a
job.
"""

from __future__ import annotations

import asyncio
import json
import signal
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.core.clock import now_utc
from app.core.errors import InfraError
from app.core.logging import configure_logging
from app.infra.db.session import (
    configure_engine,
    dispose_engine,
    get_session_factory,
)
from app.infra.jobs import get_handler, register_all_handlers

__all__ = ["run_worker", "process_once", "main"]


_LOG = structlog.get_logger(__name__)


async def process_once() -> bool:
    """Attempt to claim and run a single queued job.

    Returns:
        bool: ``True`` if a job was processed, ``False`` if the queue was
        empty.
    """
    settings = get_settings()
    factory = get_session_factory()
    async with factory() as db:
        try:
            row = (
                (
                    await db.execute(
                        text(
                            "SELECT id, job_type, payload, attempts FROM job_runs "
                            "WHERE status = 'queued' ORDER BY enqueued_at "
                            "FOR UPDATE SKIP LOCKED LIMIT 1"
                        )
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                await db.rollback()
                return False
            job_id = UUID(str(row["id"]))
            job_type = row["job_type"]
            payload_raw = row["payload"]
            payload: dict[str, Any] = (
                json.loads(payload_raw) if isinstance(payload_raw, str) else dict(payload_raw or {})
            )
            attempts = int(row["attempts"])

            worker_id = settings.jobs_worker_id or "worker-default"
            await db.execute(
                text(
                    "UPDATE job_runs SET status = 'running', started_at = :started_at, "
                    "worker_id = :worker_id, attempts = :attempts WHERE id = :id"
                ),
                {
                    "started_at": now_utc(),
                    "worker_id": worker_id,
                    "attempts": attempts + 1,
                    "id": str(job_id),
                },
            )
            await db.commit()
        except SQLAlchemyError as exc:
            await db.rollback()
            raise InfraError("SYS_001", f"worker claim failed: {exc}") from exc

    handler = get_handler(job_type)
    if handler is None:
        async with factory() as db:
            await db.execute(
                text(
                    "UPDATE job_runs SET status = 'failed', finished_at = :finished_at, "
                    "error_message = :error_message WHERE id = :id"
                ),
                {
                    "finished_at": now_utc(),
                    "error_message": f"No handler for job_type={job_type}",
                    "id": str(job_id),
                },
            )
            await db.commit()
        _LOG.error("jobs.unknown_handler", job_id=str(job_id), job_type=job_type)
        return True

    try:
        result = await handler(payload)
    except Exception as exc:
        _LOG.error(
            "jobs.handler_failed",
            job_id=str(job_id),
            job_type=job_type,
            error=str(exc),
        )
        async with factory() as db:
            if attempts + 1 >= settings.jobs_max_attempts:
                await db.execute(
                    text(
                        "UPDATE job_runs SET status = 'failed', finished_at = :finished_at, "
                        "error_message = :error_message WHERE id = :id"
                    ),
                    {
                        "finished_at": now_utc(),
                        "error_message": str(exc),
                        "id": str(job_id),
                    },
                )
            else:
                await db.execute(
                    text(
                        "UPDATE job_runs SET status = 'queued', started_at = NULL, "
                        "worker_id = NULL, error_message = :error_message WHERE id = :id"
                    ),
                    {"error_message": str(exc), "id": str(job_id)},
                )
            await db.commit()
        return True

    async with factory() as db:
        await db.execute(
            text(
                "UPDATE job_runs SET status = 'succeeded', finished_at = :finished_at, "
                "result = CAST(:result AS JSONB) WHERE id = :id"
            ),
            {
                "finished_at": now_utc(),
                "result": json.dumps(result, default=str),
                "id": str(job_id),
            },
        )
        await db.commit()
    _LOG.info("jobs.succeeded", job_id=str(job_id), job_type=job_type)
    return True


async def run_worker(stop_event: asyncio.Event | None = None) -> None:
    """Main poll loop — process jobs until ``stop_event`` is set.

    Args:
        stop_event: When set, the loop exits after finishing the current
            job. When ``None``, the loop runs indefinitely (production mode).
    """
    settings = get_settings()
    register_all_handlers()
    while stop_event is None or not stop_event.is_set():
        processed = await process_once()
        if not processed:
            try:
                if stop_event is not None:
                    await asyncio.wait_for(
                        stop_event.wait(),
                        timeout=settings.jobs_poll_interval_seconds,
                    )
                else:
                    await asyncio.sleep(settings.jobs_poll_interval_seconds)
            except TimeoutError:
                continue


def main() -> None:  # pragma: no cover — entrypoint
    """Synchronous entrypoint for ``python -m app.infra.jobs.worker``."""
    configure_logging(get_settings().log_level)
    configure_engine()
    stop = asyncio.Event()

    def _request_stop(*_: Any) -> None:
        stop.set()

    # Reason: Windows test runners may not support SIGTERM; on failure we
    # fall back to Event-based shutdown driven by the caller.
    signal_install_error: str | None = None
    try:
        signal.signal(signal.SIGINT, _request_stop)
        signal.signal(signal.SIGTERM, _request_stop)
    except (ValueError, OSError) as exc:
        signal_install_error = str(exc)
    if signal_install_error is not None:
        _LOG.info("worker.signal_handler_unavailable", error=signal_install_error)
    try:
        asyncio.run(run_worker(stop))
    finally:
        asyncio.run(dispose_engine())


if __name__ == "__main__":  # pragma: no cover
    main()
