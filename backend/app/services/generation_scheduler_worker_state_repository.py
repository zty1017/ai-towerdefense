"""SQLite repository helpers for Generation Scheduler worker state evidence."""

from __future__ import annotations

import json
from typing import Any

from ..db import db_cursor


def _dump_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def upsert_worker_cache_payload(cache_payload: dict[str, Any], ts: str) -> dict[str, Any]:
    with db_cursor() as cur:
        cur.execute(
            "SELECT created_at FROM generation_schedule_worker_cache WHERE cache_id = ?",
            (cache_payload["cache_id"],),
        )
        existing = cur.fetchone()
        if existing is not None and existing.get("created_at"):
            cache_payload["created_at"] = str(existing["created_at"])
        cur.execute(
            "INSERT INTO generation_schedule_worker_cache "
            "(cache_id, run_id, session_id, schedule_item_id, status, payload, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(cache_id) DO UPDATE SET "
            "status = excluded.status, payload = excluded.payload, updated_at = excluded.updated_at",
            (
                cache_payload["cache_id"],
                cache_payload["run_id"],
                cache_payload["session_id"],
                cache_payload["schedule_item_id"],
                str(cache_payload["status"]),
                _dump_payload(cache_payload),
                cache_payload["created_at"],
                cache_payload["updated_at"],
            ),
        )
    return cache_payload


def load_worker_cache_items(
    session_id: str, run_id: str | None = None
) -> list[dict[str, Any]]:
    if run_id is None:
        query = (
            "SELECT payload FROM generation_schedule_worker_cache "
            "WHERE session_id = ? ORDER BY id ASC"
        )
        params: tuple[Any, ...] = (session_id,)
    else:
        query = (
            "SELECT payload FROM generation_schedule_worker_cache "
            "WHERE session_id = ? AND run_id = ? ORDER BY id ASC"
        )
        params = (session_id, run_id)
    with db_cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        payload = row.get("payload") if isinstance(row, dict) else None
        if payload:
            items.append(json.loads(payload))
    return items


def insert_provider_guard_log(guard_payload: dict[str, Any], ts: str) -> None:
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO provider_logs (session_id, payload, created_at) VALUES (?, ?, ?)",
            (
                str(guard_payload.get("session_id", "")),
                _dump_payload(guard_payload),
                ts,
            ),
        )


def load_provider_guard_logs(
    session_id: str, run_id: str | None = None
) -> list[dict[str, Any]]:
    with db_cursor() as cur:
        cur.execute(
            "SELECT payload FROM provider_logs WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        )
        rows = cur.fetchall()
    logs: list[dict[str, Any]] = []
    for row in rows:
        payload_text = row.get("payload") if isinstance(row, dict) else None
        if not payload_text:
            continue
        payload = json.loads(payload_text)
        if payload.get("schema_version") != "generation_live_executor_guard.v0.1":
            continue
        if run_id is not None and str(payload.get("run_id")) != str(run_id):
            continue
        logs.append(payload)
    return logs
