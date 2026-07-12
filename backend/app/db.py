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

            CREATE TABLE IF NOT EXISTS generation_schedule_queue_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                schedule_item_id TEXT NOT NULL,
                latency_class TEXT NOT NULL,
                status TEXT NOT NULL,
                action TEXT,
                payload TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES generation_schedule_runs(run_id) ON DELETE CASCADE,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE,
                UNIQUE (run_id, schedule_item_id)
            );

            CREATE TABLE IF NOT EXISTS generation_schedule_worker_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cache_id TEXT UNIQUE NOT NULL,
                run_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                schedule_item_id TEXT NOT NULL,
                status TEXT NOT NULL,
                payload TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES generation_schedule_runs(run_id) ON DELETE CASCADE,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS generation_artifact_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ledger_id TEXT UNIQUE NOT NULL,
                run_id TEXT,
                session_id TEXT NOT NULL,
                schedule_item_id TEXT,
                artifact_kind TEXT NOT NULL,
                status TEXT NOT NULL,
                payload TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS generation_shared_prefetch_cache (
                cache_key TEXT PRIMARY KEY,
                source_session_id TEXT NOT NULL,
                source_run_id TEXT,
                source_schedule_item_id TEXT,
                object_kind TEXT,
                object_ref TEXT,
                lifecycle_status TEXT NOT NULL,
                payload TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS battle_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                idempotency_key TEXT,
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

            CREATE TABLE IF NOT EXISTS runtime_activations (
                activation_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                source_id TEXT NOT NULL,
                status TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                rolled_back_at TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE,
                UNIQUE (session_id, source_kind, source_id)
            );

            CREATE INDEX IF NOT EXISTS idx_world_instance_session
                ON world_instance(session_id);
            CREATE INDEX IF NOT EXISTS idx_campaign_state_session
                ON campaign_state(session_id);
            CREATE INDEX IF NOT EXISTS idx_asset_compile_runs_session
                ON asset_compile_runs(session_id);
            CREATE INDEX IF NOT EXISTS idx_generation_schedule_runs_session
                ON generation_schedule_runs(session_id);
            CREATE INDEX IF NOT EXISTS idx_generation_schedule_queue_items_session
                ON generation_schedule_queue_items(session_id);
            CREATE INDEX IF NOT EXISTS idx_generation_schedule_queue_items_run
                ON generation_schedule_queue_items(run_id);
            CREATE INDEX IF NOT EXISTS idx_generation_schedule_queue_items_status
                ON generation_schedule_queue_items(status);
            CREATE INDEX IF NOT EXISTS idx_generation_schedule_worker_cache_session
                ON generation_schedule_worker_cache(session_id);
            CREATE INDEX IF NOT EXISTS idx_generation_schedule_worker_cache_run
                ON generation_schedule_worker_cache(run_id);
            CREATE INDEX IF NOT EXISTS idx_generation_schedule_worker_cache_status
                ON generation_schedule_worker_cache(status);
            CREATE INDEX IF NOT EXISTS idx_generation_artifact_ledger_session
                ON generation_artifact_ledger(session_id);
            CREATE INDEX IF NOT EXISTS idx_generation_artifact_ledger_run
                ON generation_artifact_ledger(run_id);
            CREATE INDEX IF NOT EXISTS idx_generation_artifact_ledger_status
                ON generation_artifact_ledger(status);
            CREATE INDEX IF NOT EXISTS idx_generation_shared_prefetch_cache_object
                ON generation_shared_prefetch_cache(object_kind, object_ref);
            CREATE INDEX IF NOT EXISTS idx_generation_shared_prefetch_cache_status
                ON generation_shared_prefetch_cache(lifecycle_status);
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
            CREATE INDEX IF NOT EXISTS idx_runtime_activations_session
                ON runtime_activations(session_id);
            CREATE INDEX IF NOT EXISTS idx_runtime_activations_status
                ON runtime_activations(status);
            """
        )
        # Older builds could leave more than one historical job for a proposal.
        # Preserve those audit rows but detach all except the newest canonical
        # job before introducing the idempotency constraint.
        cur.execute(
            "UPDATE research_jobs SET proposal_id = NULL "
            "WHERE proposal_id IS NOT NULL AND job_id NOT IN ("
            "SELECT job_id FROM research_jobs AS candidate "
            "WHERE candidate.proposal_id = research_jobs.proposal_id "
            "ORDER BY CASE WHEN candidate.status = 'completed' THEN 0 ELSE 1 END, "
            "candidate.updated_at DESC, candidate.job_id DESC LIMIT 1"
            ")"
        )
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_research_jobs_proposal "
            "ON research_jobs(proposal_id)"
        )
        battle_result_columns = {
            row["name"]
            for row in cur.execute("PRAGMA table_info(battle_results)").fetchall()
        }
        if "idempotency_key" not in battle_result_columns:
            cur.execute("ALTER TABLE battle_results ADD COLUMN idempotency_key TEXT")
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_battle_results_idempotency "
            "ON battle_results(session_id, idempotency_key)"
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
