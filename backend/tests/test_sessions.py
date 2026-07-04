"""Tests for anonymous session lifecycle and per-session data isolation."""
from __future__ import annotations

import sqlite3
from datetime import datetime


def test_create_session_returns_opaque_id(client):
    resp = client.post("/api/sessions")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "session_id" in body
    sid = body["session_id"]
    # Hex ids stay opaque while avoiding secret-like fragments such as "sk-".
    assert isinstance(sid, str) and len(sid) >= 32
    assert "-" not in sid
    info = body["session"]
    assert info["session_id"] == sid
    assert info["display_name"] is None
    # created_at parses as ISO datetime. Pydantic v2 serializes with a "Z"
    # suffix; Python <3.11 fromisoformat does not accept "Z", so normalize.
    def _parse(s: str) -> datetime:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))

    _parse(info["created_at"])
    _parse(info["last_active_at"])


def test_create_session_with_display_name(client):
    resp = client.post("/api/sessions", json={"display_name": "demo"})
    assert resp.status_code == 201
    assert resp.json()["session"]["display_name"] == "demo"


def test_create_session_ids_are_unique(client):
    ids = set()
    for _ in range(5):
        resp = client.post("/api/sessions")
        assert resp.status_code == 201
        ids.add(resp.json()["session_id"])
    assert len(ids) == 5


def test_get_existing_session(client):
    create = client.post("/api/sessions").json()
    sid = create["session_id"]
    resp = client.get(f"/api/sessions/{sid}")
    assert resp.status_code == 200, resp.text
    info = resp.json()
    assert info["session_id"] == sid
    assert info["created_at"] == create["session"]["created_at"]


def test_get_missing_session_returns_404(client):
    resp = client.get("/api/sessions/does-not-exist")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_reset_missing_session_returns_404(client):
    resp = client.post("/api/sessions/nope/reset")
    assert resp.status_code == 404


def test_reset_clears_session_scoped_data(client, raw_conn: sqlite3.Connection):
    create = client.post("/api/sessions").json()
    sid = create["session_id"]

    # Seed a couple of per-session tables with rows for this session and one
    # other session to prove reset is scoped.
    other = client.post("/api/sessions").json()["session_id"]

    raw_conn.execute(
        "INSERT INTO world_instance (session_id, payload, created_at, updated_at) "
        "VALUES (?, ?, '', '')",
        (sid, "{}"),
    )
    raw_conn.execute(
        "INSERT INTO world_instance (session_id, payload, created_at, updated_at) "
        "VALUES (?, ?, '', '')",
        (other, "{}"),
    )
    raw_conn.execute(
        "INSERT INTO studio_logs (session_id, payload, created_at) "
        "VALUES (?, ?, '')",
        (sid, "{}"),
    )
    raw_conn.execute(
        "INSERT INTO generation_schedule_runs "
        "(run_id, session_id, status, payload, created_at, updated_at, completed_at) "
        "VALUES (?, ?, ?, ?, '', '', '')",
        ("gsrun_test", sid, "completed", "{}"),
    )
    raw_conn.execute(
        "INSERT INTO generation_schedule_queue_items "
        "(run_id, session_id, schedule_item_id, latency_class, status, action, payload, "
        "created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, '', '')",
        ("gsrun_test", sid, "sched_test", "background", "queued", "schedule_background", "{}"),
    )
    raw_conn.execute(
        "INSERT INTO generation_shared_prefetch_cache "
        "(cache_key, source_session_id, source_run_id, source_schedule_item_id, "
        "object_kind, object_ref, lifecycle_status, payload, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', '')",
        (
            "gshared_reset_survives",
            sid,
            "gsrun_test",
            "sched_test",
            "map_visual_layer",
            "map_compile_package:test",
            "promotion_allowed_pending_runtime_build",
            "{}",
        ),
    )
    raw_conn.commit()

    def count(table, session_id):
        return raw_conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE session_id = ?", (session_id,)
        ).fetchone()[0]

    assert count("world_instance", sid) == 1
    assert count("studio_logs", sid) == 1
    assert count("generation_schedule_runs", sid) == 1
    assert count("generation_schedule_queue_items", sid) == 1
    assert count("world_instance", other) == 1
    assert (
        raw_conn.execute(
            "SELECT COUNT(*) FROM generation_shared_prefetch_cache "
            "WHERE cache_key = ?",
            ("gshared_reset_survives",),
        ).fetchone()[0]
        == 1
    )

    resp = client.post(f"/api/sessions/{sid}/reset")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["reset"] is True
    assert body["session_id"] == sid

    # Reset cleared this session's rows but left other sessions untouched.
    assert count("world_instance", sid) == 0
    assert count("studio_logs", sid) == 0
    assert count("generation_schedule_runs", sid) == 0
    assert count("generation_schedule_queue_items", sid) == 0
    assert count("world_instance", other) == 1
    assert (
        raw_conn.execute(
            "SELECT COUNT(*) FROM generation_shared_prefetch_cache "
            "WHERE cache_key = ?",
            ("gshared_reset_survives",),
        ).fetchone()[0]
        == 1
    )


def test_reset_keeps_session_row_itself(client):
    create = client.post("/api/sessions").json()
    sid = create["session_id"]
    resp = client.post(f"/api/sessions/{sid}/reset")
    assert resp.status_code == 200
    # Session should still be readable after reset.
    get_resp = client.get(f"/api/sessions/{sid}")
    assert get_resp.status_code == 200
    assert get_resp.json()["session_id"] == sid


def test_sessions_are_data_isolated(client, raw_conn: sqlite3.Connection):
    """Rows written for one session must not be visible to another."""
    a = client.post("/api/sessions").json()["session_id"]
    b = client.post("/api/sessions").json()["session_id"]

    raw_conn.execute(
        "INSERT INTO campaign_state (session_id, payload, created_at, updated_at) "
        "VALUES (?, ?, '', '')",
        (a, "{\"owner\":\"a\"}"),
    )
    raw_conn.commit()

    rows_a = raw_conn.execute(
        "SELECT COUNT(*) FROM campaign_state WHERE session_id = ?", (a,)
    ).fetchone()[0]
    rows_b = raw_conn.execute(
        "SELECT COUNT(*) FROM campaign_state WHERE session_id = ?", (b,)
    ).fetchone()[0]
    assert rows_a == 1
    assert rows_b == 0


def test_health_endpoint(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_all_session_tables_carry_session_id(raw_conn: sqlite3.Connection):
    """Every per-session table must have a session_id column per the task spec."""
    tables = raw_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    names = {r[0] for r in tables}
    expected = {
        "sessions",
        "world_instance",
        "campaign_state",
        "asset_compile_runs",
        "generation_schedule_runs",
        "generation_schedule_queue_items",
        "generation_schedule_worker_cache",
        "generation_artifact_ledger",
        "battle_results",
        "provider_logs",
        "studio_logs",
    }
    assert expected.issubset(names)
    for table in expected:
        cols = {
            r[1]
            for r in raw_conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        assert "session_id" in cols, f"table {table} missing session_id"
