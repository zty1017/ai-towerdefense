"""Anonymous session routes.

Sessions are identified by an opaque, cryptographically-random `session_id`.
There is no registration, login, or PII. All per-session state in other tables
is scoped by `session_id` and cleared on reset.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from ..db import db_cursor, now_iso, touch_session
from ..models import (
    SessionCreateRequest,
    SessionCreateResponse,
    SessionInfo,
    SessionResetResponse,
)

router = APIRouter()

# Tables whose rows belong to a session and should be wiped on reset.
_SESSION_SCOPED_TABLES = (
    "generation_artifact_ledger",
    "generation_schedule_worker_cache",
    "generation_schedule_queue_items",
    "generation_schedule_runs",
    "research_jobs",
    "research_proposals",
    "studio_logs",
    "provider_logs",
    "battle_results",
    "asset_compile_runs",
    "campaign_state",
    "world_instance",
)


def _new_session_id() -> str:
    """Generate a fresh opaque session id using a cryptographically secure RNG."""
    return secrets.token_urlsafe(32)


def _parse_iso(value: str) -> datetime:
    # `datetime.fromisoformat` handles the offset form we write in db.py.
    return datetime.fromisoformat(value)


def _row_to_session(row: dict) -> SessionInfo:
    return SessionInfo(
        session_id=row["session_id"],
        display_name=row["display_name"],
        created_at=_parse_iso(row["created_at"]),
        last_active_at=_parse_iso(row["last_active_at"]),
    )


@router.post(
    "/api/sessions",
    response_model=SessionCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_session(body: SessionCreateRequest | None = None) -> SessionCreateResponse:
    """Create a new anonymous session."""
    session_id = _new_session_id()
    display_name = body.display_name if body is not None else None
    ts = now_iso()
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO sessions (session_id, display_name, created_at, last_active_at) "
            "VALUES (?, ?, ?, ?)",
            (session_id, display_name, ts, ts),
        )
        cur.execute(
            "SELECT session_id, display_name, created_at, last_active_at "
            "FROM sessions WHERE session_id = ?",
            (session_id,),
        )
        row = cur.fetchone()
    assert row is not None  # we just inserted it
    return SessionCreateResponse(session_id=session_id, session=_row_to_session(row))


@router.get("/api/sessions/{session_id}", response_model=SessionInfo)
def get_session(session_id: str) -> SessionInfo:
    """Return info for an existing session, or 404 if it does not exist."""
    with db_cursor() as cur:
        cur.execute(
            "SELECT session_id, display_name, created_at, last_active_at "
            "FROM sessions WHERE session_id = ?",
            (session_id,),
        )
        row = cur.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"session not found: {session_id}",
        )
    touch_session(session_id)
    # Re-read so last_active_at reflects the touch for the response.
    with db_cursor() as cur:
        cur.execute(
            "SELECT session_id, display_name, created_at, last_active_at "
            "FROM sessions WHERE session_id = ?",
            (session_id,),
        )
        row = cur.fetchone()
    assert row is not None
    return _row_to_session(row)


@router.post(
    "/api/sessions/{session_id}/reset",
    response_model=SessionResetResponse,
)
def reset_session(session_id: str) -> SessionResetResponse:
    """Reset demo data for a session.

    Clears all per-session rows in scoped tables but keeps the session row
    itself. Returns 404 if the session does not exist.
    """
    with db_cursor() as cur:
        cur.execute(
            "SELECT session_id, display_name, created_at, last_active_at "
            "FROM sessions WHERE session_id = ?",
            (session_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"session not found: {session_id}",
            )
        for table in _SESSION_SCOPED_TABLES:
            cur.execute(
                f"DELETE FROM {table} WHERE session_id = ?",  # noqa: S608
                (session_id,),
            )
        new_ts = now_iso()
        cur.execute(
            "UPDATE sessions SET last_active_at = ? WHERE session_id = ?",
            (new_ts, session_id),
        )
        cur.execute(
            "SELECT session_id, display_name, created_at, last_active_at "
            "FROM sessions WHERE session_id = ?",
            (session_id,),
        )
        row = cur.fetchone()
    assert row is not None
    return SessionResetResponse(
        session_id=session_id, session=_row_to_session(row), reset=True
    )
