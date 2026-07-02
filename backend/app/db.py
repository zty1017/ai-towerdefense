"""SQLite connection management and schema initialization.

Uses the standard library `sqlite3` module to avoid heavy dependencies.
All tables that carry per-session state include a `session_id` column so data
is isolated by anonymous session id.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .config import get_db_path

# A single module-level lock guarding writes. sqlite3 handles concurrency at
# the DB level for the same connection, but FastAPI may use different threads,
# so we serialize access to the shared connection handle.
_LOCK = threading.Lock()
_CONN: sqlite3.Connection | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_factory(cursor: sqlite3.Cursor, row: tuple) -> dict:
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def _connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = _row_factory
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(path: str | None = None) -> None:
    """Create the schema if it does not already exist.

    Safe to call multiple times. Uses `IF NOT EXISTS` for all DDL.
    """
    db_path = path or get_db_path()
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = _connect(db_path)
    try:
        cur = conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                display_name TEXT,
                created_at TEXT NOT NULL,
                last_active_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS world_instance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                payload TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS campaign_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                payload TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS asset_compile_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                status TEXT,
                payload TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS generation_schedule_runs (
                run_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                status TEXT NOT NULL,
                payload TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS battle_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                payload TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS provider_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                payload TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS studio_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                payload TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS research_proposals (
                proposal_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                node_id TEXT,
                intent_text TEXT,
                display_name TEXT,
                summary TEXT,
                risk_note TEXT,
                player_state_message TEXT,
                status TEXT NOT NULL,
                payload TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS research_jobs (
                job_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                proposal_id TEXT,
                status TEXT NOT NULL,
                player_state_message TEXT,
                runtime_package_path TEXT,
                delivery_payload_path TEXT,
                trace_paths TEXT,
                payload TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_world_instance_session
                ON world_instance(session_id);
            CREATE INDEX IF NOT EXISTS idx_campaign_state_session
                ON campaign_state(session_id);
            CREATE INDEX IF NOT EXISTS idx_asset_compile_runs_session
                ON asset_compile_runs(session_id);
            CREATE INDEX IF NOT EXISTS idx_generation_schedule_runs_session
                ON generation_schedule_runs(session_id);
            CREATE INDEX IF NOT EXISTS idx_battle_results_session
                ON battle_results(session_id);
            CREATE INDEX IF NOT EXISTS idx_provider_logs_session
                ON provider_logs(session_id);
            CREATE INDEX IF NOT EXISTS idx_studio_logs_session
                ON studio_logs(session_id);
            CREATE INDEX IF NOT EXISTS idx_research_proposals_session
                ON research_proposals(session_id);
            CREATE INDEX IF NOT EXISTS idx_research_jobs_session
                ON research_jobs(session_id);
            """
        )
        conn.commit()
    finally:
        conn.close()


def get_connection() -> sqlite3.Connection:
    """Return a shared connection, initializing the schema on first use.

    The connection is shared across requests because FastAPI runs in a single
    process by default for this MVP. `check_same_thread=False` plus the module
    lock keeps usage safe.
    """
    global _CONN
    if _CONN is None:
        with _LOCK:
            if _CONN is None:
                init_db()
                _CONN = _connect(get_db_path())
    return _CONN


def reset_connection() -> None:
    """Drop the cached connection. Used by tests to point at a fresh DB."""
    global _CONN
    with _LOCK:
        if _CONN is not None:
            _CONN.close()
            _CONN = None


@contextmanager
def db_cursor() -> Iterator[sqlite3.Cursor]:
    """Context manager yielding a cursor on the shared connection.

    The module-level ``_LOCK`` is held for the whole cursor lifetime so that
    concurrent FastAPI request threads cannot interleave writes on the shared
    connection. ``reset_connection`` re-acquires the same lock, so a reset
    cannot tear down a connection while a cursor is mid-flight.

    Commits on clean exit, rolls back on exception.
    """
    conn = get_connection()
    with _LOCK:
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


def touch_session(session_id: str) -> None:
    """Update last_active_at for a session without raising if missing."""
    with db_cursor() as cur:
        cur.execute(
            "UPDATE sessions SET last_active_at = ? WHERE session_id = ?",
            (_now_iso(), session_id),
        )


def now_iso() -> str:
    return _now_iso()
