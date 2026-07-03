"""SQLite repository helpers for Generation Scheduler runs and queue rows."""

from __future__ import annotations

import json
from typing import Any

from ..db import db_cursor


def _dump_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _row_to_queue_item(row: dict[str, Any]) -> dict[str, Any] | None:
    payload_text = row.get("payload") if isinstance(row, dict) else None
    if not payload_text:
        return None
    return {
        "id": row["id"],
        "run_id": row["run_id"],
        "schedule_item_id": row["schedule_item_id"],
        "status": row["status"],
        "payload": json.loads(payload_text),
    }


def insert_generation_schedule_run(payload: dict[str, Any], ts: str) -> None:
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO generation_schedule_runs "
            "(run_id, session_id, status, payload, created_at, updated_at, completed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                payload["run_id"],
                payload["session_id"],
                payload["status"],
                _dump_payload(payload),
                ts,
                ts,
                ts,
            ),
        )


def insert_generation_queue_items(items: list[dict[str, Any]]) -> None:
    with db_cursor() as cur:
        for item in items:
            cur.execute(
                "INSERT INTO generation_schedule_queue_items "
                "(run_id, session_id, schedule_item_id, latency_class, status, action, "
                "payload, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item["run_id"],
                    item["session_id"],
                    item["schedule_item_id"],
                    item["latency_class"],
                    item["status"],
                    item.get("action"),
                    _dump_payload(item),
                    item["created_at"],
                    item["updated_at"],
                ),
            )


def load_latest_generation_schedule_run(session_id: str) -> dict[str, Any] | None:
    with db_cursor() as cur:
        cur.execute(
            "SELECT payload FROM generation_schedule_runs WHERE session_id = ? "
            "ORDER BY updated_at DESC LIMIT 1",
            (session_id,),
        )
        row = cur.fetchone()
    if row is None or not row.get("payload"):
        return None
    return json.loads(row["payload"])


def load_generation_queue_items(
    session_id: str, run_id: str | None = None
) -> list[dict[str, Any]]:
    if run_id is None:
        latest = load_latest_generation_schedule_run(session_id)
        if latest is None:
            return []
        run_id = str(latest.get("run_id", ""))
    with db_cursor() as cur:
        cur.execute(
            "SELECT payload FROM generation_schedule_queue_items "
            "WHERE session_id = ? AND run_id = ? ORDER BY id ASC",
            (session_id, run_id),
        )
        rows = cur.fetchall()
    items = []
    for row in rows:
        payload = row.get("payload") if isinstance(row, dict) else None
        if payload:
            items.append(json.loads(payload))
    return items


def load_generation_queue_item_row(
    session_id: str, schedule_item_id: str, run_id: str | None = None
) -> dict[str, Any] | None:
    if run_id is None:
        latest = load_latest_generation_schedule_run(session_id)
        if latest is None:
            return None
        run_id = str(latest.get("run_id", ""))
    with db_cursor() as cur:
        cur.execute(
            "SELECT id, run_id, schedule_item_id, status, payload FROM "
            "generation_schedule_queue_items "
            "WHERE session_id = ? AND run_id = ? AND schedule_item_id = ?",
            (session_id, run_id, schedule_item_id),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return _row_to_queue_item(row)


def update_generation_queue_item(
    row_id: int, status: str, payload: dict[str, Any], ts: str
) -> None:
    with db_cursor() as cur:
        cur.execute(
            "UPDATE generation_schedule_queue_items "
            "SET status = ?, payload = ?, updated_at = ? WHERE id = ?",
            (status, _dump_payload(payload), ts, row_id),
        )


def load_next_generation_item_row_by_status(
    session_id: str, status: str
) -> dict[str, Any] | None:
    latest = load_latest_generation_schedule_run(session_id)
    if latest is None:
        return None
    run_id = str(latest.get("run_id", ""))
    with db_cursor() as cur:
        cur.execute(
            "SELECT id, run_id, schedule_item_id, status, payload FROM "
            "generation_schedule_queue_items "
            "WHERE session_id = ? AND run_id = ? AND status = ? "
            "ORDER BY id ASC LIMIT 1",
            (session_id, run_id, status),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return _row_to_queue_item(row)
