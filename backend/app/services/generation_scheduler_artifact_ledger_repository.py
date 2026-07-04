"""SQLite repository helpers for Generation Scheduler artifact ledger rows."""

from __future__ import annotations

import json
from typing import Any

from ..db import db_cursor


def _dump_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def upsert_generation_artifact_ledger(payload: dict[str, Any]) -> None:
    with db_cursor() as cur:
        cur.execute(
            "SELECT created_at FROM generation_artifact_ledger WHERE ledger_id = ?",
            (payload["ledger_id"],),
        )
        existing = cur.fetchone()
        if existing is not None and existing.get("created_at"):
            payload["created_at"] = str(existing["created_at"])
        cur.execute(
            "INSERT INTO generation_artifact_ledger "
            "(ledger_id, run_id, session_id, schedule_item_id, artifact_kind, status, "
            "payload, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(ledger_id) DO UPDATE SET "
            "run_id = excluded.run_id, schedule_item_id = excluded.schedule_item_id, "
            "artifact_kind = excluded.artifact_kind, status = excluded.status, "
            "payload = excluded.payload, updated_at = excluded.updated_at",
            (
                payload["ledger_id"],
                payload.get("run_id"),
                payload["session_id"],
                payload.get("schedule_item_id"),
                payload["artifact_kind"],
                payload["status"],
                _dump_payload(payload),
                payload["created_at"],
                payload["updated_at"],
            ),
        )


def load_generation_artifact_ledger_items(
    session_id: str, run_id: str | None = None
) -> list[dict[str, Any]]:
    query = (
        "SELECT payload FROM generation_artifact_ledger "
        "WHERE session_id = ? ORDER BY id ASC"
    )
    params: tuple[Any, ...] = (session_id,)
    if run_id is not None:
        query = (
            "SELECT payload FROM generation_artifact_ledger "
            "WHERE session_id = ? AND run_id = ? ORDER BY id ASC"
        )
        params = (session_id, run_id)
    with db_cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        payload_text = row.get("payload") if isinstance(row, dict) else None
        if payload_text:
            items.append(json.loads(payload_text))
    return items


def latest_generation_executor_request_ledger_entry(
    session_id: str,
    run_id: str,
    schedule_item_id: str | None = None,
) -> dict[str, Any] | None:
    items = load_generation_artifact_ledger_items(session_id, run_id)
    executor_requests = [
        item
        for item in items
        if item.get("artifact_kind") == "generation_executor_run_request"
        and item.get("status") == "prepared_pending_explicit_authorization"
        and (
            schedule_item_id is None
            or str(item.get("schedule_item_id")) == str(schedule_item_id)
        )
    ]
    return executor_requests[-1] if executor_requests else None


def latest_provider_authorization_ledger_entry(
    session_id: str,
    run_id: str,
    schedule_item_id: str,
    authorization_ref: str,
) -> dict[str, Any] | None:
    items = load_generation_artifact_ledger_items(session_id, run_id)
    authorizations = [
        item
        for item in items
        if item.get("artifact_kind") == "provider_execution_authorization"
        and item.get("status") == "granted_for_provider_adapter"
        and str(item.get("schedule_item_id")) == str(schedule_item_id)
        and str(item.get("source_id")) == str(authorization_ref)
    ]
    return authorizations[-1] if authorizations else None


def latest_provider_adapter_execution_ledger_entry(
    session_id: str,
    run_id: str,
    schedule_item_id: str,
    authorization_ref: str,
) -> dict[str, Any] | None:
    items = load_generation_artifact_ledger_items(session_id, run_id)
    receipts = []
    for item in items:
        if item.get("artifact_kind") != "provider_adapter_execution_receipt":
            continue
        if item.get("status") not in {
            "fixture_output_ready_for_envelope",
            "performed_redacted_live",
        }:
            continue
        if str(item.get("schedule_item_id")) != str(schedule_item_id):
            continue
        compact = item.get("compact")
        if not isinstance(compact, dict):
            continue
        execution = compact.get("execution")
        if not isinstance(execution, dict):
            continue
        if str(execution.get("authorization_ref")) != str(authorization_ref):
            continue
        receipts.append(item)
    return receipts[-1] if receipts else None


def latest_provider_output_envelope_ledger_entry(
    session_id: str,
    run_id: str,
    schedule_item_id: str,
    envelope_id: str,
) -> dict[str, Any] | None:
    items = load_generation_artifact_ledger_items(session_id, run_id)
    envelopes = [
        item
        for item in items
        if item.get("artifact_kind") == "provider_output_envelope"
        and str(item.get("schedule_item_id")) == str(schedule_item_id)
        and str(item.get("source_id")) == str(envelope_id)
    ]
    return envelopes[-1] if envelopes else None
