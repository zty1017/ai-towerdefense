"""Durable queue operations for asynchronous research compilation jobs."""

from __future__ import annotations

import os
from typing import Any

from ..db import db_cursor, now_iso


def worker_mode() -> str:
    """Return the explicit worker mode; background is the production default."""
    value = os.environ.get("AI_TD_RESEARCH_WORKER_MODE", "background")
    return value.strip().lower()


def recover_running_jobs() -> int:
    """Return interrupted jobs to the durable queue during process startup."""
    ts = now_iso()
    with db_cursor() as cur:
        cur.execute(
            "UPDATE research_jobs SET status = 'queued', player_state_message = ?, "
            "updated_at = ?, completed_at = NULL WHERE status = 'running'",
            ("工坊已重新接续这份试作，请稍候。", ts),
        )
        return cur.rowcount


def claim_next_job() -> dict[str, Any] | None:
    """Atomically claim the oldest queued job across competing processes."""
    ts = now_iso()
    with db_cursor() as cur:
        cur.execute(
            "UPDATE research_jobs SET status = 'running', player_state_message = ?, "
            "updated_at = ? WHERE job_id = ("
            "SELECT job_id FROM research_jobs WHERE status = 'queued' "
            "ORDER BY created_at, job_id LIMIT 1"
            ") AND status = 'queued' RETURNING job_id, session_id, proposal_id, status",
            ("工坊正在准备这份试作，请稍候。", ts),
        )
        row = cur.fetchone()
    return dict(row) if row is not None else None


def claim_job(job_id: str) -> dict[str, Any] | None:
    """Atomically claim a specific queued job for explicit inline execution."""
    with db_cursor() as cur:
        cur.execute(
            "UPDATE research_jobs SET status = 'running', player_state_message = ?, "
            "updated_at = ? WHERE job_id = ? AND status = 'queued' "
            "RETURNING job_id, session_id, proposal_id, status",
            ("工坊正在准备这份试作，请稍候。", now_iso(), job_id),
        )
        row = cur.fetchone()
    return dict(row) if row is not None else None


def requeue_interrupted_job(job_id: str) -> None:
    """Best-effort recovery when the worker fails outside workflow handling."""
    with db_cursor() as cur:
        cur.execute(
            "UPDATE research_jobs SET status = 'queued', player_state_message = ?, "
            "updated_at = ?, completed_at = NULL "
            "WHERE job_id = ? AND status = 'running'",
            ("工坊暂时停顿，正在重新接续这份试作。", now_iso(), job_id),
        )
