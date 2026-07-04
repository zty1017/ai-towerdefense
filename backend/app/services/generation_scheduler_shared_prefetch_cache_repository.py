"""Repository helpers for cross-session shared prefetch cache records."""

from __future__ import annotations

import json
from typing import Any

from ..db import db_cursor


def _dump_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def upsert_shared_prefetch_cache_records(records: list[dict[str, Any]]) -> None:
    if not records:
        return
    with db_cursor() as cur:
        for record in records:
            cur.execute(
                "SELECT created_at FROM generation_shared_prefetch_cache "
                "WHERE cache_key = ?",
                (record["cache_key"],),
            )
            existing = cur.fetchone()
            created_at = (
                str(existing["created_at"])
                if existing is not None and existing.get("created_at")
                else record["created_at"]
            )
            record["created_at"] = created_at
            cur.execute(
                "INSERT INTO generation_shared_prefetch_cache "
                "(cache_key, source_session_id, source_run_id, "
                "source_schedule_item_id, object_kind, object_ref, "
                "lifecycle_status, payload, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(cache_key) DO UPDATE SET "
                "source_session_id = excluded.source_session_id, "
                "source_run_id = excluded.source_run_id, "
                "source_schedule_item_id = excluded.source_schedule_item_id, "
                "object_kind = excluded.object_kind, "
                "object_ref = excluded.object_ref, "
                "lifecycle_status = excluded.lifecycle_status, "
                "payload = excluded.payload, "
                "updated_at = excluded.updated_at",
                (
                    record["cache_key"],
                    record["source"]["source_session_id"],
                    record["source"].get("source_run_id"),
                    record["source"].get("source_schedule_item_id"),
                    record.get("object_kind"),
                    record.get("object_ref"),
                    record["lifecycle_status"],
                    _dump_payload(record),
                    record["created_at"],
                    record["updated_at"],
                ),
            )


def load_shared_prefetch_cache_records() -> list[dict[str, Any]]:
    with db_cursor() as cur:
        cur.execute(
            "SELECT payload FROM generation_shared_prefetch_cache "
            "ORDER BY updated_at DESC, cache_key ASC"
        )
        rows = cur.fetchall()
    records: list[dict[str, Any]] = []
    for row in rows:
        payload_text = row.get("payload") if isinstance(row, dict) else None
        if payload_text:
            records.append(json.loads(payload_text))
    return records
