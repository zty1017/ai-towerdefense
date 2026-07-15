"""Shared anonymous-session guard for session-scoped API routers."""

from __future__ import annotations

from fastapi import HTTPException, status

from ..db import db_cursor


def require_session(session_id: str) -> None:
    """Raise a stable 404 when an anonymous session does not exist."""
    with db_cursor() as cur:
        cur.execute(
            "SELECT session_id FROM sessions WHERE session_id = ?",
            (session_id,),
        )
        if cur.fetchone() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"session not found: {session_id}",
            )
