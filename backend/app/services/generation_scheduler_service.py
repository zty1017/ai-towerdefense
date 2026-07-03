"""Fixture-backed Generation Scheduler service.

This module owns the MVP scheduler control-plane state: review-only schedule
plans, dry-run reports, per-session dry-run records, item queues, transitions,
retry/fallback guards, and the local dry worker step. It deliberately does not
call providers, read `.env`, mutate world state, or activate generated content.
"""

from __future__ import annotations

import json
import secrets
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from ..db import db_cursor, now_iso


_REPO_ROOT = Path(__file__).resolve().parents[3]
_GENERATION_SCHEDULE_PLAN = (
    _REPO_ROOT / "examples/review_packs/mvp_generation_schedule_plan.v0.1.json"
)
_GENERATION_SCHEDULE_RUN_REPORT = (
    _REPO_ROOT / "examples/review_packs/mvp_generation_schedule_run_report.v0.1.json"
)
_MVP_CONTEXT_PACKAGE_EXAMPLE = (
    _REPO_ROOT / "examples/review_packs/mvp_first_battle.context_package.json"
)
_MVP_CGOP_EXAMPLE = (
    _REPO_ROOT / "examples/review_packs/mvp_light_snare.compiled_game_object_package.json"
)
_TOOLS_DEV_DIR = _REPO_ROOT / "tools" / "dev"
_TOOLS_PROVIDER_ADAPTER_DIR = _REPO_ROOT / "tools" / "provider_adapter"
if str(_TOOLS_DEV_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DEV_DIR))
if str(_TOOLS_PROVIDER_ADAPTER_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_PROVIDER_ADAPTER_DIR))

from validate_provider_artifact_staging_manifest import (  # noqa: E402
    validate_provider_artifact_staging_manifest,
)
from validate_provider_artifact_promotion_report import (  # noqa: E402
    validate_provider_artifact_promotion_report,
)
from validate_provider_output_envelope import validate_provider_output_envelope  # noqa: E402
from validate_generation_executor_run_request import (  # noqa: E402
    validate_generation_executor_run_request,
)
from validate_provider_execution_authorization import (  # noqa: E402
    validate_provider_execution_authorization,
)
from validate_provider_adapter_execution_receipt import (  # noqa: E402
    validate_provider_adapter_execution_receipt,
)
from run_provider_adapter import (  # noqa: E402
    build_dry_run_artifacts as build_provider_adapter_runner_dry_run_artifacts,
    validate_outputs as validate_provider_adapter_runner_outputs,
)
from .generation_scheduler_artifact_fixtures import (  # noqa: E402
    provider_artifact_fixture_metadata,
    provider_artifact_fixture_paths,
)
from .generation_scheduler_artifact_ledger_builders import (  # noqa: E402
    build_artifact_ledger_payload as _build_artifact_ledger_payload,
    compact_generation_artifact_ledger as _compact_generation_artifact_ledger,
    compact_provider_artifact_promotion_report as _compact_provider_artifact_promotion_report,
    compact_provider_artifact_staging as _compact_provider_artifact_staging,
    compact_provider_output_envelope as _compact_provider_output_envelope,
)
from .generation_scheduler_artifact_ledger_repository import (  # noqa: E402
    latest_generation_executor_request_ledger_entry as _latest_generation_executor_request_ledger_entry,
    latest_provider_adapter_execution_ledger_entry as _latest_provider_adapter_execution_ledger_entry,
    latest_provider_authorization_ledger_entry as _latest_provider_authorization_ledger_entry,
    latest_provider_output_envelope_ledger_entry as _latest_provider_output_envelope_ledger_entry,
    load_generation_artifact_ledger_items as _load_generation_artifact_ledger_items,
    upsert_generation_artifact_ledger as _upsert_generation_artifact_ledger,
)
from .generation_scheduler_handoff_builders import (  # noqa: E402
    build_provider_adapter_runner_handoff,
    build_provider_adapter_runner_handoff_outbox,
    provider_runner_outbox_safety,
)
from .generation_scheduler_import_safety import (  # noqa: E402
    display_import_path,
    load_safe_import_json,
    resolve_import_path,
)
from .generation_scheduler_provider_execution_builders import (  # noqa: E402
    build_generation_executor_run_request_payload as _build_generation_executor_run_request_payload_base,
    build_live_executor_guard_payload as _build_live_executor_guard_payload,
    build_provider_adapter_execution_receipt_payload as _build_provider_adapter_execution_receipt_payload,
    build_provider_execution_authorization_payload as _build_provider_execution_authorization_payload,
    compact_generation_executor_run_request as _compact_generation_executor_run_request,
    compact_provider_adapter_execution_receipt as _compact_provider_adapter_execution_receipt,
    compact_provider_execution_authorization as _compact_provider_execution_authorization,
    provider_authorization_ref as _provider_authorization_ref,
    rehydrate_generation_executor_request_for_runner as _rehydrate_generation_executor_request_for_runner_base,
    rehydrate_provider_authorization_for_runner as _rehydrate_provider_authorization_for_runner_base,
)
from .generation_scheduler_run_queue_repository import (  # noqa: E402
    insert_generation_queue_items as _insert_generation_queue_items,
    insert_generation_schedule_run as _insert_generation_schedule_run,
    load_generation_queue_item_row as _load_generation_queue_item_row_base,
    load_generation_queue_items as _load_generation_queue_items,
    load_latest_generation_schedule_run as _load_latest_generation_schedule_run,
    load_next_generation_item_row_by_status as _load_next_generation_item_row_by_status,
    update_generation_queue_item as _update_generation_queue_item,
)
from .generation_scheduler_run_queue_builders import (  # noqa: E402
    build_generation_queue_items_from_run as _build_generation_queue_items_from_run,
    build_generation_schedule_buffer as _build_generation_schedule_buffer,
    build_generation_schedule_payload as _build_generation_schedule_payload_base,
    build_generation_schedule_run_payload as _build_generation_schedule_run_payload_base,
    build_worker_cache_payload as _build_worker_cache_payload,
    compact_generation_queue as _compact_generation_queue,
    compact_generation_schedule_run as _compact_generation_schedule_run,
    compact_provider_guard_logs as _compact_provider_guard_logs,
    compact_worker_cache as _compact_worker_cache,
    worker_cache_summary as _worker_cache_summary,
)


class GenerationSchedulerFixtureNotFoundError(LookupError):
    """Raised when scheduler fixture/session state is missing."""


class InvalidQueueTransitionError(ValueError):
    """Raised when a scheduler queue transition violates the current state."""


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _resolve_import_path(value: Any, *, label: str) -> Path:
    return resolve_import_path(
        value,
        label=label,
        repo_root=_REPO_ROOT,
        error_cls=InvalidQueueTransitionError,
    )


def _load_runner_import_json(path: Path, *, label: str) -> dict[str, Any]:
    return load_safe_import_json(
        path,
        label=label,
        error_cls=InvalidQueueTransitionError,
    )


def _provider_artifact_fixture_paths(profile: str | None) -> tuple[Path, Path, Path, str]:
    return provider_artifact_fixture_paths(
        profile,
        repo_root=_REPO_ROOT,
        error_cls=InvalidQueueTransitionError,
    )


def _provider_artifact_fixture_metadata(
    profile: str | None,
) -> dict[str, str]:
    return provider_artifact_fixture_metadata(
        profile,
        repo_root=_REPO_ROOT,
        load_json=_load_json,
        rel_path=_rel,
        error_cls=InvalidQueueTransitionError,
    )


def _dump_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _rel(path: Path) -> str:
    return path.relative_to(_REPO_ROOT).as_posix()


def _new_generation_schedule_run_id() -> str:
    return f"gsrun_{secrets.token_hex(12)}"


def _generation_schedule_refs() -> dict[str, str]:
    return {
        "plan": _rel(_GENERATION_SCHEDULE_PLAN),
        "run_report": _rel(_GENERATION_SCHEDULE_RUN_REPORT),
    }


def _load_generation_schedule_plan() -> dict[str, Any]:
    return _load_json(_GENERATION_SCHEDULE_PLAN)


def _load_generation_schedule_run_report() -> dict[str, Any]:
    return _load_json(_GENERATION_SCHEDULE_RUN_REPORT)


def _build_generation_schedule_payload(
    plan: dict[str, Any], run_report: dict[str, Any]
) -> dict[str, Any]:
    return _build_generation_schedule_payload_base(
        plan,
        run_report,
        refs=_generation_schedule_refs(),
    )


def _build_generation_schedule_run_payload(
    session_id: str, run_id: str, ts: str
) -> dict[str, Any]:
    plan = _load_generation_schedule_plan()
    run_report = _load_generation_schedule_run_report()
    return _build_generation_schedule_run_payload_base(
        session_id,
        run_id,
        ts,
        plan=plan,
        run_report=run_report,
        refs=_generation_schedule_refs(),
    )


def _load_generation_queue_item_row(
    session_id: str, schedule_item_id: str
) -> dict[str, Any]:
    row = _load_generation_queue_item_row_base(session_id, schedule_item_id)
    if row is None:
        raise GenerationSchedulerFixtureNotFoundError(schedule_item_id)
    return row


def _upsert_worker_cache_from_queue_item(payload: dict[str, Any], ts: str) -> dict[str, Any]:
    cache_payload = _build_worker_cache_payload(payload, ts)
    with db_cursor() as cur:
        cur.execute(
            "SELECT created_at FROM generation_schedule_worker_cache WHERE cache_id = ?",
            (cache_payload["cache_id"],),
        )
        existing = cur.fetchone()
        created_at = (
            str(existing["created_at"])
            if existing is not None and existing.get("created_at")
            else ts
        )
        cache_payload["created_at"] = created_at
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


def _load_worker_cache_items(
    session_id: str, run_id: str | None = None
) -> list[dict[str, Any]]:
    if run_id is None:
        latest = _load_latest_generation_schedule_run(session_id)
        if latest is None:
            return []
        run_id = str(latest.get("run_id", ""))
    with db_cursor() as cur:
        cur.execute(
            "SELECT payload FROM generation_schedule_worker_cache "
            "WHERE session_id = ? AND run_id = ? ORDER BY id ASC",
            (session_id, run_id),
        )
        rows = cur.fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        payload = row.get("payload") if isinstance(row, dict) else None
        if payload:
            items.append(json.loads(payload))
    return items


def _next_generation_queue_status(current_status: str, transition: str) -> str:
    if transition == "claim":
        if current_status != "queued":
            raise InvalidQueueTransitionError(
                f"cannot claim scheduler item in status {current_status}"
            )
        return "claimed"
    if transition == "complete":
        if current_status not in ("queued", "claimed", "waiting_review"):
            raise InvalidQueueTransitionError(
                f"cannot complete scheduler item in status {current_status}"
            )
        return "completed"
    if transition == "fail":
        if current_status not in ("queued", "claimed", "waiting_review"):
            raise InvalidQueueTransitionError(
                f"cannot fail scheduler item in status {current_status}"
            )
        return "failed"
    if transition == "retry":
        if current_status != "failed":
            raise InvalidQueueTransitionError(
                f"cannot retry scheduler item in status {current_status}"
            )
        return "queued"
    if transition == "fallback":
        if current_status not in ("failed", "waiting_review"):
            raise InvalidQueueTransitionError(
                f"cannot fallback scheduler item in status {current_status}"
            )
        return "fallback_ready"
    raise InvalidQueueTransitionError(f"unknown scheduler queue transition {transition}")


def _transition_generation_queue_item(
    session_id: str,
    schedule_item_id: str,
    transition: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = _load_generation_queue_item_row(session_id, schedule_item_id)
    payload = row["payload"]
    current_status = str(row["status"])
    next_status = _next_generation_queue_status(current_status, transition)
    if transition == "retry":
        attempt_count = int(payload.get("attempt_count", 0))
        max_attempts = int(payload.get("max_attempts", 0))
        if attempt_count >= max_attempts:
            raise InvalidQueueTransitionError(
                f"cannot retry scheduler item after {attempt_count}/{max_attempts} attempts"
            )
    if transition == "fallback" and not payload.get("fallback_ref"):
        raise InvalidQueueTransitionError("cannot fallback scheduler item without fallback_ref")
    ts = now_iso()
    safe_metadata = metadata if isinstance(metadata, dict) else {}
    transition_entry = {
        "transition": transition,
        "from_status": current_status,
        "to_status": next_status,
        "worker_id": safe_metadata.get("worker_id") or "frontend_mock_scheduler",
        "note": safe_metadata.get("note"),
        "created_at": ts,
    }
    transitions = payload.setdefault("transitions", [])
    if isinstance(transitions, list):
        transitions.append(transition_entry)
    payload["status"] = next_status
    payload["updated_at"] = ts
    if transition == "claim":
        payload["claimed_at"] = ts
        payload["claimed_by"] = transition_entry["worker_id"]
    elif transition == "complete":
        payload["completed_at"] = ts
    elif transition == "fail":
        payload["failed_at"] = ts
    elif transition == "retry":
        payload["retried_at"] = ts
    elif transition == "fallback":
        payload["fallback_selected_at"] = ts
    _update_generation_queue_item(int(row["id"]), next_status, payload, ts)
    return payload


def _load_next_queued_generation_item_row(session_id: str) -> dict[str, Any] | None:
    return _load_next_generation_item_row_by_status(session_id, "queued")


def _requested_schedule_item_id(metadata: dict[str, Any] | None) -> str | None:
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("schedule_item_id")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _load_generation_item_row_by_status(
    session_id: str,
    status: str,
    schedule_item_id: str | None,
) -> dict[str, Any] | None:
    if schedule_item_id is None:
        return _load_next_generation_item_row_by_status(session_id, status)
    row = _load_generation_queue_item_row(session_id, schedule_item_id)
    if str(row["status"]) != status:
        raise InvalidQueueTransitionError(
            f"schedule item {schedule_item_id} must be {status}, got {row['status']}"
        )
    return row


def _insert_provider_guard_log(guard_payload: dict[str, Any]) -> None:
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO provider_logs (session_id, payload, created_at) VALUES (?, ?, ?)",
            (
                str(guard_payload.get("session_id", "")),
                _dump_payload(guard_payload),
                str(guard_payload.get("created_at", now_iso())),
            ),
        )


def _load_provider_guard_logs(
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


def _build_generation_executor_run_request_payload(
    queue_payload: dict[str, Any],
    guard_payload: dict[str, Any],
    metadata: dict[str, Any] | None,
    ts: str,
) -> dict[str, Any]:
    return _build_generation_executor_run_request_payload_base(
        queue_payload,
        guard_payload,
        metadata,
        ts,
        input_refs=[
            {
                "ref_id": "generation_schedule_plan",
                "kind": "schedule_plan",
                "path": _rel(_GENERATION_SCHEDULE_PLAN),
                "notes": [
                    "Use only scheduler item structure and refs; prompt body storage is forbidden."
                ],
            },
            {
                "ref_id": "generation_schedule_run_report",
                "kind": "schedule_run_report",
                "path": _rel(_GENERATION_SCHEDULE_RUN_REPORT),
            },
        ],
        context_refs=[
            {
                "ref_id": "context_package",
                "kind": "context_package",
                "path": _rel(_MVP_CONTEXT_PACKAGE_EXAMPLE),
            },
            {
                "ref_id": "target_cgop",
                "kind": "compiled_game_object_package",
                "path": _rel(_MVP_CGOP_EXAMPLE),
            },
        ],
    )


def _rehydrate_generation_executor_request_for_runner(
    entry: dict[str, Any],
) -> dict[str, Any]:
    return _rehydrate_generation_executor_request_for_runner_base(
        entry,
        created_at=now_iso(),
        schedule_plan_ref=_rel(_GENERATION_SCHEDULE_PLAN),
    )


def _rehydrate_provider_authorization_for_runner(
    entry: dict[str, Any],
) -> dict[str, Any]:
    return _rehydrate_provider_authorization_for_runner_base(
        entry,
        created_at=now_iso(),
    )


def _attach_live_executor_guard_to_cache(
    queue_payload: dict[str, Any],
    guard_payload: dict[str, Any],
    ts: str,
) -> dict[str, Any]:
    cache_payload = _build_worker_cache_payload(queue_payload, ts)
    cache_payload["executor_guard"] = {
        "guard_id": guard_payload["guard_id"],
        "status": guard_payload["status"],
        "provider_mode": guard_payload["provider_mode"],
        "provider_profile": guard_payload["provider_profile"],
        "authorization_required": True,
        "provider_call_performed": False,
        "world_mutation_performed": False,
        "activation_allowed_now": False,
    }
    cache_payload["activation_gate"] = {
        "revalidate_before_activation": (
            queue_payload.get("revalidate_before_activation") is True
        ),
        "blocked_reason": "explicit_provider_authorization_required",
    }
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
                ts,
            ),
        )
    return cache_payload


def _run_live_executor_guard(
    session_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    row = _load_generation_item_row_by_status(
        session_id,
        "waiting_review",
        _requested_schedule_item_id(metadata),
    )
    if row is None:
        return None
    payload = row["payload"]
    ts = now_iso()
    guard_payload = _build_live_executor_guard_payload(payload, metadata, ts)
    transition_entry = {
        "transition": "live_executor_guard",
        "from_status": row["status"],
        "to_status": row["status"],
        "worker_id": guard_payload["worker_id"],
        "note": guard_payload.get("note"),
        "created_at": ts,
        "provider_call_performed": False,
        "world_mutation_performed": False,
    }
    transitions = payload.setdefault("transitions", [])
    if isinstance(transitions, list):
        transitions.append(transition_entry)
    payload["live_executor_guard"] = {
        "guard_id": guard_payload["guard_id"],
        "status": guard_payload["status"],
        "created_at": ts,
    }
    payload["updated_at"] = ts
    _update_generation_queue_item(int(row["id"]), str(row["status"]), payload, ts)
    _insert_provider_guard_log(guard_payload)
    _attach_live_executor_guard_to_cache(payload, guard_payload, ts)
    return guard_payload


def _find_guard_payload_for_queue_payload(
    session_id: str,
    queue_payload: dict[str, Any],
) -> dict[str, Any] | None:
    guard = queue_payload.get("live_executor_guard")
    if not isinstance(guard, dict):
        return None
    guard_id = guard.get("guard_id")
    if not guard_id:
        return None
    logs = _load_provider_guard_logs(session_id, str(queue_payload.get("run_id") or ""))
    for log in logs:
        if log.get("guard_id") == guard_id:
            return log
    return None


def _prepare_generation_executor_run_request(
    session_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    row = _load_generation_item_row_by_status(
        session_id,
        "waiting_review",
        _requested_schedule_item_id(metadata),
    )
    if row is None:
        return None
    payload = row["payload"]
    guard_payload = _find_guard_payload_for_queue_payload(session_id, payload)
    if guard_payload is None:
        raise InvalidQueueTransitionError(
            "live executor guard is required before preparing executor request"
        )
    ts = now_iso()
    request_payload = _build_generation_executor_run_request_payload(
        payload,
        guard_payload,
        metadata,
        ts,
    )
    request_errors = validate_generation_executor_run_request(request_payload)
    if request_errors:
        raise ValueError(
            "generation executor request failed validation: "
            + "; ".join(request_errors)
        )
    transition_entry = {
        "transition": "prepare_executor_request",
        "from_status": row["status"],
        "to_status": row["status"],
        "worker_id": request_payload["source"]["worker_id"],
        "note": request_payload["source"].get("note"),
        "created_at": ts,
        "provider_call_performed": False,
        "world_mutation_performed": False,
    }
    transitions = payload.setdefault("transitions", [])
    if isinstance(transitions, list):
        transitions.append(transition_entry)
    payload["executor_request"] = {
        "request_id": request_payload["request_id"],
        "status": request_payload["provider_execution_intent"]["status"],
        "created_at": ts,
    }
    payload["updated_at"] = ts
    _update_generation_queue_item(int(row["id"]), str(row["status"]), payload, ts)
    latest_run = _load_latest_generation_schedule_run(session_id)
    ledger_entry = _build_artifact_ledger_payload(
        session_id=session_id,
        artifact_kind="generation_executor_run_request",
        source_id=str(request_payload["request_id"]),
        status="prepared_pending_explicit_authorization",
        compact=_compact_generation_executor_run_request(request_payload),
        ts=ts,
        latest_run=latest_run,
        schedule_item_id=str(payload.get("schedule_item_id") or ""),
        worker_id=str(request_payload["source"]["worker_id"]),
        note=(
            str(request_payload["source"].get("note"))
            if request_payload["source"].get("note") is not None
            else None
        ),
    )
    _upsert_generation_artifact_ledger(ledger_entry)
    return request_payload


def _run_generation_dry_worker_step(
    session_id: str, metadata: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    row = _load_generation_item_row_by_status(
        session_id,
        "queued",
        _requested_schedule_item_id(metadata),
    )
    if row is None:
        return None
    payload = row["payload"]
    current_status = str(row["status"])
    ts = now_iso()
    safe_metadata = metadata if isinstance(metadata, dict) else {}
    worker_id = safe_metadata.get("worker_id") or "frontend_mock_dry_worker"
    attempt_count = int(payload.get("attempt_count", 0)) + 1
    requires_review = payload.get("provider_review_required") is True
    next_status = "waiting_review" if requires_review else "completed"
    transition_entry = {
        "transition": "dry_run_worker_step",
        "from_status": current_status,
        "to_status": next_status,
        "worker_id": worker_id,
        "note": safe_metadata.get("note"),
        "created_at": ts,
    }
    transitions = payload.setdefault("transitions", [])
    if isinstance(transitions, list):
        transitions.append(transition_entry)
    payload["status"] = next_status
    payload["updated_at"] = ts
    payload["worker_step_at"] = ts
    payload["worker_id"] = worker_id
    payload["attempt_count"] = attempt_count
    payload["attempt_budget_exhausted"] = attempt_count >= int(payload.get("max_attempts", 0))
    payload["provider_call_performed"] = False
    payload["world_mutation_performed"] = False
    if next_status == "waiting_review":
        payload["waiting_review_since"] = ts
        payload["review_reason"] = "provider_or_manual_review_required_before_activation"
    else:
        payload["completed_at"] = ts
    _update_generation_queue_item(int(row["id"]), next_status, payload, ts)
    _upsert_worker_cache_from_queue_item(payload, ts)
    return payload


def get_generation_schedule(session_id: str) -> dict[str, Any]:
    plan = _load_generation_schedule_plan()
    run_report = _load_generation_schedule_run_report()
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "generation_schedule": _build_generation_schedule_payload(plan, run_report),
        "latest_generation_schedule_run": _load_latest_generation_schedule_run(session_id),
    }


def create_generation_schedule_run(session_id: str) -> dict[str, Any]:
    run_id = _new_generation_schedule_run_id()
    ts = now_iso()
    payload = _build_generation_schedule_run_payload(session_id, run_id, ts)
    _insert_generation_schedule_run(payload, ts)
    queue_items = _build_generation_queue_items_from_run(payload, ts)
    _insert_generation_queue_items(queue_items)
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "generation_schedule_run": payload,
        "generation_schedule_queue": _compact_generation_queue(queue_items),
    }


def get_latest_generation_schedule_run(session_id: str) -> dict[str, Any]:
    run = _load_latest_generation_schedule_run(session_id)
    queue_items = _load_generation_queue_items(session_id) if run is not None else []
    cache_items = _load_worker_cache_items(session_id) if run is not None else []
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "generation_schedule_run": run,
        "generation_schedule_queue": _compact_generation_queue(queue_items),
        "generation_schedule_worker_cache": _compact_worker_cache(cache_items),
    }


def get_generation_schedule_queue(session_id: str) -> dict[str, Any]:
    run = _load_latest_generation_schedule_run(session_id)
    queue_items = _load_generation_queue_items(session_id) if run is not None else []
    cache_items = _load_worker_cache_items(session_id) if run is not None else []
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "generation_schedule_run": _compact_generation_schedule_run(run),
        "generation_schedule_queue": _compact_generation_queue(queue_items),
        "generation_schedule_worker_cache_summary": _worker_cache_summary(cache_items),
    }


def get_generation_schedule_worker_cache(session_id: str) -> dict[str, Any]:
    run = _load_latest_generation_schedule_run(session_id)
    cache_items = _load_worker_cache_items(session_id) if run is not None else []
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "generation_schedule_run": _compact_generation_schedule_run(run),
        "generation_schedule_worker_cache": _compact_worker_cache(cache_items),
    }


def transition_generation_schedule_queue_item(
    session_id: str,
    schedule_item_id: str,
    transition: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item = _transition_generation_queue_item(
        session_id,
        schedule_item_id,
        transition,
        metadata,
    )
    queue_items = _load_generation_queue_items(session_id, str(item["run_id"]))
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "generation_schedule_queue_item": item,
        "generation_schedule_queue": _compact_generation_queue(queue_items),
    }


def run_generation_schedule_dry_worker_step(
    session_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item = _run_generation_dry_worker_step(session_id, metadata)
    queue_items = _load_generation_queue_items(session_id)
    cache_items = _load_worker_cache_items(session_id)
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "worker_step": {
            "status": "idle" if item is None else "processed",
            "worker_mode": "fixture_backed_dry_worker",
            "provider_call_count": 0,
            "world_mutation_count": 0,
        },
        "generation_schedule_queue_item": item,
        "generation_schedule_queue": _compact_generation_queue(queue_items),
        "generation_schedule_worker_cache": _compact_worker_cache(cache_items),
    }


def run_generation_schedule_live_executor_guard(
    session_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    guard_payload = _run_live_executor_guard(session_id, metadata)
    run = _load_latest_generation_schedule_run(session_id)
    run_id = str(run.get("run_id", "")) if run is not None else None
    queue_items = _load_generation_queue_items(session_id, run_id)
    cache_items = _load_worker_cache_items(session_id, run_id) if run_id else []
    guard_logs = _load_provider_guard_logs(session_id, run_id)
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "worker_step": {
            "status": "idle" if guard_payload is None else "blocked",
            "worker_mode": "live_executor_guard",
            "provider_call_count": 0,
            "world_mutation_count": 0,
            "activation_allowed_count": 0,
        },
        "live_executor_guard": guard_payload,
        "generation_schedule_queue": _compact_generation_queue(queue_items),
        "generation_schedule_worker_cache": _compact_worker_cache(cache_items),
        "provider_guard_logs": _compact_provider_guard_logs(guard_logs),
    }


def prepare_generation_executor_run_request(
    session_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request_payload = _prepare_generation_executor_run_request(session_id, metadata)
    latest_run = _load_latest_generation_schedule_run(session_id)
    run_id = str(latest_run.get("run_id")) if latest_run is not None else None
    queue_items = _load_generation_queue_items(session_id, run_id)
    ledger_items = _load_generation_artifact_ledger_items(session_id, run_id)
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "worker_step": {
            "status": "idle" if request_payload is None else "prepared",
            "worker_mode": "generation_executor_request_preparer",
            "provider_call_count": 0,
            "world_mutation_count": 0,
            "activation_allowed_count": 0,
        },
        "generation_executor_run_request": request_payload,
        "generation_schedule_queue": _compact_generation_queue(queue_items),
        "generation_artifact_ledger": _compact_generation_artifact_ledger(ledger_items),
    }


def grant_provider_execution_authorization(
    session_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    latest_run = _load_latest_generation_schedule_run(session_id)
    if latest_run is None:
        raise InvalidQueueTransitionError(
            "generation schedule run is required before provider authorization"
        )
    run_id = str(latest_run.get("run_id"))
    executor_request_entry = _latest_generation_executor_request_ledger_entry(
        session_id,
        run_id,
        _requested_schedule_item_id(metadata),
    )
    if executor_request_entry is None:
        raise InvalidQueueTransitionError(
            "matching generation executor request is required before provider authorization"
        )
    ts = now_iso()
    authorization_payload = _build_provider_execution_authorization_payload(
        executor_request_entry,
        metadata,
        ts,
    )
    authorization_errors = validate_provider_execution_authorization(
        authorization_payload
    )
    if authorization_errors:
        raise ValueError(
            "provider execution authorization failed validation: "
            + "; ".join(authorization_errors)
        )
    source = authorization_payload["source"]
    ledger_entry = _build_artifact_ledger_payload(
        session_id=session_id,
        artifact_kind="provider_execution_authorization",
        source_id=str(authorization_payload["authorization_ref"]),
        status="granted_for_provider_adapter",
        compact=_compact_provider_execution_authorization(authorization_payload),
        ts=ts,
        latest_run=latest_run,
        schedule_item_id=str(source["schedule_item_id"]),
        worker_id=str(source["worker_id"]),
        note=str(source.get("note")) if source.get("note") is not None else None,
    )
    _upsert_generation_artifact_ledger(ledger_entry)
    ledger_items = _load_generation_artifact_ledger_items(session_id, run_id)
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "worker_step": {
            "status": "authorized",
            "worker_mode": "provider_authorization_grant",
            "provider_call_count": 0,
            "world_mutation_count": 0,
            "activation_allowed_count": 0,
            "authorization_ref": authorization_payload["authorization_ref"],
            "upstream_request_id": source["executor_request_id"],
        },
        "provider_execution_authorization": authorization_payload,
        "generation_artifact_ledger": _compact_generation_artifact_ledger(ledger_items),
    }


def run_provider_adapter_fixture(
    session_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    latest_run = _load_latest_generation_schedule_run(session_id)
    if latest_run is None:
        raise InvalidQueueTransitionError(
            "generation schedule run is required before provider adapter execution"
        )
    run_id = str(latest_run.get("run_id"))
    schedule_item_id = _requested_schedule_item_id(metadata)
    safe_metadata = metadata if isinstance(metadata, dict) else {}
    authorization_ref = str(safe_metadata.get("authorization_ref") or "")
    if not authorization_ref and schedule_item_id:
        authorization_ref = _provider_authorization_ref(schedule_item_id)
    if not schedule_item_id or not authorization_ref:
        raise InvalidQueueTransitionError(
            "schedule_item_id and authorization_ref are required before provider adapter execution"
        )
    authorization_entry = _latest_provider_authorization_ledger_entry(
        session_id,
        run_id,
        schedule_item_id,
        authorization_ref,
    )
    if authorization_entry is None:
        raise InvalidQueueTransitionError(
            "matching provider execution authorization is required before provider adapter execution"
        )
    ts = now_iso()
    receipt_payload = _build_provider_adapter_execution_receipt_payload(
        authorization_entry,
        metadata,
        ts,
    )
    receipt_errors = validate_provider_adapter_execution_receipt(receipt_payload)
    if receipt_errors:
        raise ValueError(
            "provider adapter execution receipt failed validation: "
            + "; ".join(receipt_errors)
        )
    source = receipt_payload["source"]
    ledger_entry = _build_artifact_ledger_payload(
        session_id=session_id,
        artifact_kind="provider_adapter_execution_receipt",
        source_id=str(receipt_payload["execution_receipt_id"]),
        status="fixture_output_ready_for_envelope",
        compact=_compact_provider_adapter_execution_receipt(receipt_payload),
        ts=ts,
        latest_run=latest_run,
        schedule_item_id=str(source["schedule_item_id"]),
        worker_id=str(source["worker_id"]),
        note=str(source.get("note")) if source.get("note") is not None else None,
    )
    _upsert_generation_artifact_ledger(ledger_entry)
    ledger_items = _load_generation_artifact_ledger_items(session_id, run_id)
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "worker_step": {
            "status": "adapter_recorded",
            "worker_mode": "provider_adapter_fixture_runner",
            "provider_call_count": 0,
            "world_mutation_count": 0,
            "activation_allowed_count": 0,
            "authorization_ref": source["authorization_ref"],
            "upstream_request_id": source["executor_request_id"],
            "execution_receipt_id": receipt_payload["execution_receipt_id"],
        },
        "provider_execution_authorization": authorization_entry.get("compact"),
        "provider_adapter_execution_receipt": receipt_payload,
        "generation_artifact_ledger": _compact_generation_artifact_ledger(ledger_items),
    }


def run_provider_adapter_runner_fixture(
    session_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    latest_run = _load_latest_generation_schedule_run(session_id)
    if latest_run is None:
        raise InvalidQueueTransitionError(
            "generation schedule run is required before provider adapter runner"
        )
    run_id = str(latest_run.get("run_id"))
    schedule_item_id = _requested_schedule_item_id(metadata)
    safe_metadata = metadata if isinstance(metadata, dict) else {}
    authorization_ref = str(safe_metadata.get("authorization_ref") or "")
    if not authorization_ref and schedule_item_id:
        authorization_ref = _provider_authorization_ref(schedule_item_id)
    if not schedule_item_id or not authorization_ref:
        raise InvalidQueueTransitionError(
            "schedule_item_id and authorization_ref are required before provider adapter runner"
        )
    executor_request_entry = _latest_generation_executor_request_ledger_entry(
        session_id,
        run_id,
        schedule_item_id,
    )
    if executor_request_entry is None:
        raise InvalidQueueTransitionError(
            "matching generation executor request is required before provider adapter runner"
        )
    authorization_entry = _latest_provider_authorization_ledger_entry(
        session_id,
        run_id,
        schedule_item_id,
        authorization_ref,
    )
    if authorization_entry is None:
        raise InvalidQueueTransitionError(
            "matching provider execution authorization is required before provider adapter runner"
        )
    ts = now_iso()
    executor_request = _rehydrate_generation_executor_request_for_runner(
        executor_request_entry
    )
    authorization = _rehydrate_provider_authorization_for_runner(authorization_entry)
    receipt_payload, envelope_payload = build_provider_adapter_runner_dry_run_artifacts(
        executor_request,
        authorization,
        created_at=ts,
        note=safe_metadata.get("note"),
    )
    validate_provider_adapter_runner_outputs(receipt_payload, envelope_payload)
    receipt_source = receipt_payload["source"]
    envelope_source = envelope_payload["source"]
    receipt_entry = _build_artifact_ledger_payload(
        session_id=session_id,
        artifact_kind="provider_adapter_execution_receipt",
        source_id=str(receipt_payload["execution_receipt_id"]),
        status="runner_fixture_output_ready_for_envelope",
        compact=_compact_provider_adapter_execution_receipt(receipt_payload),
        ts=ts,
        latest_run=latest_run,
        schedule_item_id=str(receipt_source["schedule_item_id"]),
        worker_id=str(receipt_source["worker_id"]),
        note=str(receipt_source.get("note"))
        if receipt_source.get("note") is not None
        else None,
    )
    envelope_entry = _build_artifact_ledger_payload(
        session_id=session_id,
        artifact_kind="provider_output_envelope",
        source_id=str(envelope_payload["envelope_id"]),
        status="runner_recorded_review_only",
        compact=_compact_provider_output_envelope(envelope_payload),
        ts=ts,
        latest_run=latest_run,
        schedule_item_id=str(envelope_source["schedule_item_id"]),
        worker_id=str(envelope_source["worker_id"]),
        note=str(safe_metadata.get("note"))
        if safe_metadata.get("note") is not None
        else None,
    )
    _upsert_generation_artifact_ledger(receipt_entry)
    _upsert_generation_artifact_ledger(envelope_entry)
    ledger_items = _load_generation_artifact_ledger_items(session_id, run_id)
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "worker_step": {
            "status": "runner_recorded",
            "worker_mode": "provider_adapter_runner_fixture",
            "provider_call_count": 0,
            "world_mutation_count": 0,
            "activation_allowed_count": 0,
            "schedule_item_id": schedule_item_id,
            "authorization_ref": authorization_ref,
            "upstream_request_id": executor_request_entry.get("source_id"),
            "execution_receipt_id": receipt_payload["execution_receipt_id"],
            "envelope_id": envelope_payload["envelope_id"],
        },
        "generation_executor_run_request": executor_request_entry.get("compact"),
        "provider_execution_authorization": authorization_entry.get("compact"),
        "provider_adapter_execution_receipt": receipt_entry["compact"],
        "provider_output_envelope": envelope_entry["compact"],
        "generation_artifact_ledger": _compact_generation_artifact_ledger(ledger_items),
    }


def export_provider_adapter_runner_handoff(
    session_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    latest_run = _load_latest_generation_schedule_run(session_id)
    if latest_run is None:
        raise InvalidQueueTransitionError(
            "generation schedule run is required before exporting provider adapter runner handoff"
        )
    run_id = str(latest_run.get("run_id"))
    schedule_item_id = _requested_schedule_item_id(metadata)
    safe_metadata = metadata if isinstance(metadata, dict) else {}
    authorization_ref = str(safe_metadata.get("authorization_ref") or "")
    if not authorization_ref and schedule_item_id:
        authorization_ref = _provider_authorization_ref(schedule_item_id)
    if not schedule_item_id or not authorization_ref:
        raise InvalidQueueTransitionError(
            "schedule_item_id and authorization_ref are required before exporting provider adapter runner handoff"
        )
    executor_request_entry = _latest_generation_executor_request_ledger_entry(
        session_id,
        run_id,
        schedule_item_id,
    )
    if executor_request_entry is None:
        raise InvalidQueueTransitionError(
            "matching generation executor request is required before exporting provider adapter runner handoff"
        )
    authorization_entry = _latest_provider_authorization_ledger_entry(
        session_id,
        run_id,
        schedule_item_id,
        authorization_ref,
    )
    if authorization_entry is None:
        raise InvalidQueueTransitionError(
            "matching provider execution authorization is required before exporting provider adapter runner handoff"
        )
    executor_request = _rehydrate_generation_executor_request_for_runner(
        executor_request_entry
    )
    authorization = _rehydrate_provider_authorization_for_runner(authorization_entry)
    validate_or_raise_errors = validate_generation_executor_run_request(executor_request)
    if validate_or_raise_errors:
        raise ValueError(
            "generation executor handoff request failed validation: "
            + "; ".join(validate_or_raise_errors)
        )
    authorization_errors = validate_provider_execution_authorization(authorization)
    if authorization_errors:
        raise ValueError(
            "provider execution handoff authorization failed validation: "
            + "; ".join(authorization_errors)
        )
    ts = now_iso()
    provider_profile = str(
        authorization.get("source", {}).get("provider_profile") or "unknown"
    )
    safe_note = safe_metadata.get("note")
    ledger_items = _load_generation_artifact_ledger_items(session_id, run_id)
    handoff_payload = build_provider_adapter_runner_handoff(
        session_id=session_id,
        run_id=run_id,
        schedule_item_id=schedule_item_id,
        authorization_ref=authorization_ref,
        executor_request_id=executor_request_entry.get("source_id"),
        executor_request=executor_request,
        authorization=authorization,
        provider_profile=provider_profile,
        created_at=ts,
        note=safe_note,
    )
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "worker_step": {
            "status": "handoff_exported",
            "worker_mode": "provider_adapter_runner_handoff_export",
            "provider_call_count": 0,
            "world_mutation_count": 0,
            "activation_allowed_count": 0,
            "schedule_item_id": schedule_item_id,
            "authorization_ref": authorization_ref,
            "upstream_request_id": executor_request_entry.get("source_id"),
        },
        "provider_adapter_runner_handoff": handoff_payload,
        "generation_artifact_ledger": _compact_generation_artifact_ledger(ledger_items),
    }


def run_review_only_dispatcher_step(
    session_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Dispatch one queued item through the review-only provider runner boundary."""
    safe_metadata = metadata if isinstance(metadata, dict) else {}
    requested_schedule_item_id = _requested_schedule_item_id(safe_metadata)
    worker_prefix = str(
        safe_metadata.get("worker_id") or "review_only_dispatcher"
    )
    note = safe_metadata.get("note")
    latest_run = _load_latest_generation_schedule_run(session_id)
    created_run = latest_run is None
    run_payload = (
        create_generation_schedule_run(session_id)["generation_schedule_run"]
        if created_run
        else latest_run
    )
    run_id = str(run_payload.get("run_id") or "") if run_payload else ""

    def _idle_response(
        schedule_item_id: str | None,
        steps: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        latest_run_for_idle = _load_latest_generation_schedule_run(session_id)
        idle_run_id = (
            str(latest_run_for_idle.get("run_id"))
            if latest_run_for_idle is not None
            else run_id
        )
        queue_items = _load_generation_queue_items(session_id, idle_run_id)
        cache_items = (
            _load_worker_cache_items(session_id, idle_run_id)
            if idle_run_id
            else []
        )
        ledger_items = _load_generation_artifact_ledger_items(
            session_id,
            idle_run_id,
        )
        return {
            "session_id": session_id,
            "mode": "frontend_mock_fixture",
            "worker_step": {
                "status": "idle",
                "worker_mode": "review_only_dispatcher_step",
                "created_generation_schedule_run": created_run,
                "run_id": run_payload.get("run_id") if run_payload else None,
                "schedule_item_id": schedule_item_id,
                "provider_call_count": 0,
                "world_mutation_count": 0,
                "activation_allowed_count": 0,
                "promotion_allowed_count": 0,
                "staging_performed": False,
                "promotion_performed": False,
                "queue_completed": False,
            },
            "steps": steps or {},
            "generation_schedule_run": _compact_generation_schedule_run(
                latest_run_for_idle
            ),
            "generation_schedule_queue": _compact_generation_queue(queue_items),
            "generation_schedule_worker_cache": _compact_worker_cache(cache_items),
            "generation_artifact_ledger": _compact_generation_artifact_ledger(
                ledger_items
            ),
        }

    if requested_schedule_item_id:
        requested_row = _load_generation_queue_item_row(
            session_id,
            requested_schedule_item_id,
        )
        if (
            requested_row["status"] == "queued"
            and requested_row["payload"].get("provider_review_required") is not True
        ):
            raise InvalidQueueTransitionError(
                "review-only dispatcher requires a provider-review queue item"
            )
    else:
        for candidate in _load_generation_queue_items(session_id, run_id):
            if (
                candidate.get("status") == "queued"
                and candidate.get("provider_review_required") is True
            ):
                requested_schedule_item_id = str(
                    candidate.get("schedule_item_id") or ""
                )
                break
    if not requested_schedule_item_id:
        return _idle_response(None)

    def _step_metadata(
        step_name: str,
        schedule_item_id: str | None = None,
        authorization_ref: str | None = None,
    ) -> dict[str, Any]:
        step_metadata: dict[str, Any] = {
            "worker_id": f"{worker_prefix}_{step_name}",
            "note": note,
        }
        if schedule_item_id:
            step_metadata["schedule_item_id"] = schedule_item_id
        if authorization_ref:
            step_metadata["authorization_ref"] = authorization_ref
        return step_metadata

    dry_step = run_generation_schedule_dry_worker_step(
        session_id,
        _step_metadata("dry_run", requested_schedule_item_id),
    )
    queue_item = dry_step.get("generation_schedule_queue_item")
    if queue_item is None:
        return _idle_response(
            requested_schedule_item_id,
            {"dry_run_step": dry_step["worker_step"]},
        )

    schedule_item_id = str(queue_item.get("schedule_item_id") or "")
    if not schedule_item_id:
        raise InvalidQueueTransitionError(
            "review-only dispatcher requires a concrete schedule_item_id"
        )
    if queue_item.get("status") != "waiting_review":
        raise InvalidQueueTransitionError(
            "review-only dispatcher requires a provider-review queue item"
        )
    authorization_ref = str(
        safe_metadata.get("authorization_ref")
        or _provider_authorization_ref(schedule_item_id)
    )

    guard_step = run_generation_schedule_live_executor_guard(
        session_id,
        _step_metadata("live_guard", schedule_item_id),
    )
    executor_request_step = prepare_generation_executor_run_request(
        session_id,
        _step_metadata("executor_request", schedule_item_id),
    )
    authorization_step = grant_provider_execution_authorization(
        session_id,
        _step_metadata("provider_authorization", schedule_item_id, authorization_ref),
    )
    authorization_ref = str(
        authorization_step["worker_step"].get("authorization_ref")
        or authorization_ref
    )
    runner_step = run_provider_adapter_runner_fixture(
        session_id,
        _step_metadata("provider_runner", schedule_item_id, authorization_ref),
    )
    latest_after_dispatch = _load_latest_generation_schedule_run(session_id)
    run_id = (
        str(latest_after_dispatch.get("run_id"))
        if latest_after_dispatch is not None
        else None
    )
    queue_items = _load_generation_queue_items(session_id, run_id)
    cache_items = _load_worker_cache_items(session_id, run_id) if run_id else []
    ledger_items = _load_generation_artifact_ledger_items(session_id, run_id)
    queue_row = _load_generation_queue_item_row(session_id, schedule_item_id)

    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "worker_step": {
            "status": "dispatched_review_only",
            "worker_mode": "review_only_dispatcher_step",
            "created_generation_schedule_run": created_run,
            "run_id": run_payload.get("run_id") if run_payload else None,
            "schedule_item_id": schedule_item_id,
            "authorization_ref": authorization_ref,
            "execution_receipt_id": runner_step["worker_step"][
                "execution_receipt_id"
            ],
            "envelope_id": runner_step["worker_step"]["envelope_id"],
            "provider_call_count": 0,
            "world_mutation_count": 0,
            "activation_allowed_count": 0,
            "promotion_allowed_count": 0,
            "staging_performed": False,
            "promotion_performed": False,
            "queue_completed": queue_row["status"] == "completed",
        },
        "steps": {
            "dry_run_step": dry_step["worker_step"],
            "live_executor_guard": guard_step["worker_step"],
            "generation_executor_run_request": executor_request_step["worker_step"],
            "provider_execution_authorization": authorization_step["worker_step"],
            "provider_adapter_runner": runner_step["worker_step"],
        },
        "generation_schedule_run": _compact_generation_schedule_run(
            latest_after_dispatch
        ),
        "generation_schedule_queue_item": queue_row["payload"],
        "generation_schedule_queue": _compact_generation_queue(queue_items),
        "generation_schedule_worker_cache": _compact_worker_cache(cache_items),
        "provider_guard_logs": guard_step["provider_guard_logs"],
        "live_executor_guard": guard_step["live_executor_guard"],
        "generation_executor_run_request": executor_request_step[
            "generation_executor_run_request"
        ],
        "provider_execution_authorization": authorization_step[
            "provider_execution_authorization"
        ],
        "provider_adapter_execution_receipt": runner_step[
            "provider_adapter_execution_receipt"
        ],
        "provider_output_envelope": runner_step["provider_output_envelope"],
        "generation_artifact_ledger": _compact_generation_artifact_ledger(
            ledger_items
        ),
    }


def _requested_max_items(
    metadata: dict[str, Any] | None,
    *,
    default: int,
    maximum: int,
) -> int:
    if not isinstance(metadata, dict) or metadata.get("max_items") is None:
        return default
    try:
        value = int(metadata["max_items"])
    except (TypeError, ValueError) as exc:
        raise InvalidQueueTransitionError("max_items must be an integer") from exc
    if value < 1 or value > maximum:
        raise InvalidQueueTransitionError(
            f"max_items must be between 1 and {maximum}"
        )
    return value


def run_review_only_dispatcher_drain(
    session_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Dispatch several queued review-only items through the runner boundary."""
    safe_metadata = metadata if isinstance(metadata, dict) else {}
    unsupported_keys = [
        key
        for key in (
            "schedule_item_id",
            "authorization_ref",
            "artifact_profile",
            "receipt_path",
            "envelope_path",
            "staging_path",
            "promotion_report_path",
        )
        if safe_metadata.get(key) not in (None, "")
    ]
    if unsupported_keys:
        raise InvalidQueueTransitionError(
            "review-only dispatcher drain does not accept targeted metadata: "
            + ", ".join(unsupported_keys)
        )
    max_items = _requested_max_items(safe_metadata, default=4, maximum=16)
    worker_prefix = str(
        safe_metadata.get("worker_id") or "review_only_dispatcher_drain"
    )
    note = safe_metadata.get("note")
    created_run = _load_latest_generation_schedule_run(session_id) is None
    dispatches: list[dict[str, Any]] = []
    idle_reached = False

    for index in range(max_items):
        dispatch = run_review_only_dispatcher_step(
            session_id,
            {
                "worker_id": f"{worker_prefix}_{index + 1:02d}",
                "note": note,
            },
        )
        worker_step = dispatch.get("worker_step", {})
        if worker_step.get("status") == "idle":
            idle_reached = True
            break
        if worker_step.get("status") != "dispatched_review_only":
            raise InvalidQueueTransitionError(
                "review-only dispatcher drain received unexpected worker status: "
                f"{worker_step.get('status')}"
            )
        dispatches.append(
            {
                "status": worker_step.get("status"),
                "schedule_item_id": worker_step.get("schedule_item_id"),
                "authorization_ref": worker_step.get("authorization_ref"),
                "execution_receipt_id": worker_step.get("execution_receipt_id"),
                "envelope_id": worker_step.get("envelope_id"),
                "provider_call_count": worker_step.get("provider_call_count"),
                "world_mutation_count": worker_step.get("world_mutation_count"),
                "activation_allowed_count": worker_step.get(
                    "activation_allowed_count"
                ),
                "promotion_allowed_count": worker_step.get(
                    "promotion_allowed_count"
                ),
                "staging_performed": worker_step.get("staging_performed"),
                "promotion_performed": worker_step.get("promotion_performed"),
                "queue_completed": worker_step.get("queue_completed"),
            }
        )

    latest_run = _load_latest_generation_schedule_run(session_id)
    run_id = str(latest_run.get("run_id")) if latest_run is not None else None
    queue_items = _load_generation_queue_items(session_id, run_id)
    cache_items = _load_worker_cache_items(session_id, run_id) if run_id else []
    ledger_items = _load_generation_artifact_ledger_items(session_id, run_id)
    dispatched_count = len(dispatches)
    status = "drained_review_only" if dispatched_count else "idle"
    remaining_eligible_count = sum(
        1
        for item in queue_items
        if item.get("status") == "queued"
        and item.get("provider_review_required") is True
    )
    stop_reason = (
        "budget_exhausted"
        if remaining_eligible_count > 0 and dispatched_count >= max_items
        else "no_eligible_items"
    )

    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "worker_step": {
            "status": status,
            "worker_mode": "review_only_dispatcher_drain",
            "created_generation_schedule_run": created_run,
            "run_id": run_id,
            "max_items": max_items,
            "dispatched_count": dispatched_count,
            "idle_reached": idle_reached,
            "stop_reason": stop_reason,
            "remaining_eligible_count": remaining_eligible_count,
            "provider_call_count": 0,
            "world_mutation_count": 0,
            "activation_allowed_count": 0,
            "promotion_allowed_count": 0,
            "staging_performed": False,
            "promotion_performed": False,
            "queue_completed_count": sum(
                1 for item in dispatches if item.get("queue_completed") is True
            ),
        },
        "dispatcher_steps": dispatches,
        "generation_schedule_run": _compact_generation_schedule_run(latest_run),
        "generation_schedule_queue": _compact_generation_queue(queue_items),
        "generation_schedule_worker_cache": _compact_worker_cache(cache_items),
        "generation_artifact_ledger": _compact_generation_artifact_ledger(
            ledger_items
        ),
    }


def run_review_only_background_executor_tick(
    session_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one bounded review-only background executor tick.

    This is the stable API-shaped shell for a future daemon loop. The actual
    work is still delegated to the existing dispatcher drain so the guard,
    authorization, runner, and ledger boundaries stay in one place.
    """
    safe_metadata = metadata if isinstance(metadata, dict) else {}
    max_items = _requested_max_items(safe_metadata, default=2, maximum=8)
    worker_id = str(
        safe_metadata.get("worker_id") or "review_only_background_executor_tick"
    )
    note = safe_metadata.get("note") or "manual review-only background tick"
    drain = run_review_only_dispatcher_drain(
        session_id,
        {
            **safe_metadata,
            "worker_id": worker_id,
            "note": note,
            "max_items": max_items,
        },
    )
    drain_step = drain.get("worker_step", {})
    prefetch_cache = get_generation_prefetch_cache(session_id)
    prefetch_summary = (
        prefetch_cache.get("generation_prefetch_cache", {}).get("summary", {})
        if isinstance(prefetch_cache, dict)
        else {}
    )
    status = (
        "ticked_review_only"
        if drain_step.get("status") == "drained_review_only"
        else "idle"
    )
    tick_step = {
        "status": status,
        "worker_mode": "review_only_background_executor_tick",
        "trigger": "manual_api_tick",
        "created_generation_schedule_run": drain_step.get(
            "created_generation_schedule_run"
        ),
        "run_id": drain_step.get("run_id"),
        "max_items": max_items,
        "dispatched_count": drain_step.get("dispatched_count", 0),
        "idle_reached": drain_step.get("idle_reached"),
        "stop_reason": drain_step.get("stop_reason"),
        "remaining_eligible_count": drain_step.get("remaining_eligible_count"),
        "provider_call_count": 0,
        "world_mutation_count": 0,
        "activation_allowed_count": 0,
        "promotion_allowed_count": 0,
        "staging_performed": False,
        "promotion_performed": False,
        "queue_completed_count": drain_step.get("queue_completed_count", 0),
    }
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "worker_step": tick_step,
        "background_executor_tick": {
            "tick_mode": "review_only_background_executor_tick",
            "dispatcher_worker_step": drain_step,
            "prefetch_cache_summary": prefetch_summary,
            "safety": {
                "api_reads_env": False,
                "api_calls_provider": False,
                "api_stages_provider_artifacts": False,
                "api_promotes_provider_artifacts": False,
                "api_completes_queue_items": False,
                "api_writes_world_state": False,
                "api_activates_runtime": False,
                "prompt_body_stored": False,
                "provider_response_body_stored": False,
            },
        },
        "dispatcher_steps": drain.get("dispatcher_steps", []),
        "generation_schedule_run": drain.get("generation_schedule_run"),
        "generation_schedule_queue": drain.get("generation_schedule_queue"),
        "generation_schedule_worker_cache": drain.get(
            "generation_schedule_worker_cache"
        ),
        "generation_artifact_ledger": drain.get("generation_artifact_ledger"),
        "generation_prefetch_cache": prefetch_cache.get(
            "generation_prefetch_cache", {}
        ),
    }


def run_review_only_background_handoff_tick(
    session_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one review-only background tick and export runner handoffs.

    This builds the safe outbox shape for future external provider workers.
    It still does not run the provider adapter; each handoff must be consumed
    by an explicitly authorized external runner and imported back afterwards.
    """
    safe_metadata = metadata if isinstance(metadata, dict) else {}
    max_items = _requested_max_items(safe_metadata, default=2, maximum=8)
    worker_id = str(
        safe_metadata.get("worker_id") or "review_only_background_handoff_tick"
    )
    note = safe_metadata.get("note") or "manual review-only background handoff tick"
    tick = run_review_only_background_executor_tick(
        session_id,
        {
            **safe_metadata,
            "worker_id": worker_id,
            "note": note,
            "max_items": max_items,
        },
    )
    runner_handoffs: list[dict[str, Any]] = []
    for index, dispatched in enumerate(tick.get("dispatcher_steps", []), start=1):
        if not isinstance(dispatched, dict):
            continue
        schedule_item_id = str(dispatched.get("schedule_item_id") or "")
        authorization_ref = str(dispatched.get("authorization_ref") or "")
        if not schedule_item_id or not authorization_ref:
            continue
        handoff = export_provider_adapter_runner_handoff(
            session_id,
            {
                "worker_id": f"{worker_id}_handoff_{index:02d}",
                "note": note,
                "schedule_item_id": schedule_item_id,
                "authorization_ref": authorization_ref,
            },
        )
        runner_handoffs.append(handoff["provider_adapter_runner_handoff"])

    base_step = tick.get("worker_step", {})
    status = (
        "handoff_tick_exported"
        if runner_handoffs
        else "idle"
    )
    handoff_step = {
        "status": status,
        "worker_mode": "review_only_background_handoff_tick",
        "trigger": "manual_api_tick",
        "run_id": base_step.get("run_id"),
        "max_items": max_items,
        "dispatched_count": base_step.get("dispatched_count", 0),
        "runner_handoff_count": len(runner_handoffs),
        "stop_reason": base_step.get("stop_reason"),
        "remaining_eligible_count": base_step.get("remaining_eligible_count"),
        "provider_call_count": 0,
        "world_mutation_count": 0,
        "activation_allowed_count": 0,
        "promotion_allowed_count": 0,
        "staging_performed": False,
        "promotion_performed": False,
        "queue_completed_count": base_step.get("queue_completed_count", 0),
    }
    outbox_safety = provider_runner_outbox_safety()
    outbox = build_provider_adapter_runner_handoff_outbox(
        session_id=session_id,
        run_id=str(base_step.get("run_id") or ""),
        worker_id=worker_id,
        max_items=max_items,
        dispatched_count=int(base_step.get("dispatched_count", 0) or 0),
        stop_reason=base_step.get("stop_reason"),
        runner_handoffs=runner_handoffs,
        created_at=now_iso(),
    )
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "worker_step": handoff_step,
        "background_handoff_tick": {
            "tick_mode": "review_only_background_handoff_tick",
            "background_executor_tick": tick.get("background_executor_tick"),
            "runner_handoff_count": len(runner_handoffs),
            "handoff_mode": "external_runner_required",
            "safety": outbox_safety,
        },
        "provider_adapter_runner_handoff_outbox": outbox,
        "runner_handoffs": runner_handoffs,
        "dispatcher_steps": tick.get("dispatcher_steps", []),
        "generation_schedule_run": tick.get("generation_schedule_run"),
        "generation_schedule_queue": tick.get("generation_schedule_queue"),
        "generation_schedule_worker_cache": tick.get(
            "generation_schedule_worker_cache"
        ),
        "generation_artifact_ledger": tick.get("generation_artifact_ledger"),
        "generation_prefetch_cache": tick.get("generation_prefetch_cache"),
    }


def _display_import_path(path: Path) -> str:
    return display_import_path(path, repo_root=_REPO_ROOT)


def import_provider_adapter_runner_outputs(
    session_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    latest_run = _load_latest_generation_schedule_run(session_id)
    if latest_run is None:
        raise InvalidQueueTransitionError(
            "generation schedule run is required before importing provider adapter outputs"
        )
    safe_metadata = metadata if isinstance(metadata, dict) else {}
    run_id = str(latest_run.get("run_id"))
    schedule_item_id = _requested_schedule_item_id(safe_metadata)
    authorization_ref = str(safe_metadata.get("authorization_ref") or "")
    if not schedule_item_id or not authorization_ref:
        raise InvalidQueueTransitionError(
            "schedule_item_id and authorization_ref are required before importing provider adapter outputs"
        )
    receipt_path = _resolve_import_path(
        safe_metadata.get("receipt_path"),
        label="receipt_path",
    )
    envelope_path = _resolve_import_path(
        safe_metadata.get("envelope_path"),
        label="envelope_path",
    )
    receipt_payload = _load_runner_import_json(
        receipt_path,
        label="receipt_path",
    )
    envelope_payload = _load_runner_import_json(
        envelope_path,
        label="envelope_path",
    )
    validate_provider_adapter_runner_outputs(receipt_payload, envelope_payload)
    executor_request_entry = _latest_generation_executor_request_ledger_entry(
        session_id,
        run_id,
        schedule_item_id,
    )
    if executor_request_entry is None:
        raise InvalidQueueTransitionError(
            "matching generation executor request is required before importing provider adapter outputs"
        )
    authorization_entry = _latest_provider_authorization_ledger_entry(
        session_id,
        run_id,
        schedule_item_id,
        authorization_ref,
    )
    if authorization_entry is None:
        raise InvalidQueueTransitionError(
            "matching provider execution authorization is required before importing provider adapter outputs"
        )
    receipt_source = (
        receipt_payload.get("source", {})
        if isinstance(receipt_payload.get("source"), dict)
        else {}
    )
    envelope_source = (
        envelope_payload.get("source", {})
        if isinstance(envelope_payload.get("source"), dict)
        else {}
    )
    provider_call = (
        envelope_payload.get("provider_call", {})
        if isinstance(envelope_payload.get("provider_call"), dict)
        else {}
    )
    execution = (
        receipt_payload.get("execution", {})
        if isinstance(receipt_payload.get("execution"), dict)
        else {}
    )
    alignment_checks = {
        "receipt_schedule_item_id": receipt_source.get("schedule_item_id")
        == schedule_item_id,
        "receipt_authorization_ref": receipt_source.get("authorization_ref")
        == authorization_ref,
        "receipt_executor_request_id": receipt_source.get("executor_request_id")
        == executor_request_entry.get("source_id"),
        "envelope_schedule_item_id": envelope_source.get("schedule_item_id")
        == schedule_item_id,
        "envelope_object_kind": envelope_source.get("object_kind")
        == receipt_source.get("object_kind"),
        "envelope_object_ref": envelope_source.get("object_ref")
        == receipt_source.get("object_ref"),
        "envelope_provider_profile": envelope_source.get("provider_profile")
        == receipt_source.get("provider_profile"),
        "envelope_provider_mode": envelope_source.get("provider_mode")
        == receipt_source.get("provider_mode"),
        "provider_performed_matches_receipt": provider_call.get("performed")
        == execution.get("provider_call_performed_by_receipt_builder"),
    }
    if provider_call.get("performed") is True:
        alignment_checks["performed_authorization_ref"] = (
            provider_call.get("authorization_ref") == authorization_ref
        )
    failed = [name for name, passed in alignment_checks.items() if not passed]
    if failed:
        raise InvalidQueueTransitionError(
            "provider adapter runner outputs do not match ledger authorization chain: "
            + ", ".join(failed)
        )
    ts = now_iso()
    receipt_entry = _build_artifact_ledger_payload(
        session_id=session_id,
        artifact_kind="provider_adapter_execution_receipt",
        source_id=str(receipt_payload["execution_receipt_id"]),
        status="imported_runner_output_ready_for_envelope",
        compact=_compact_provider_adapter_execution_receipt(receipt_payload),
        ts=ts,
        latest_run=latest_run,
        schedule_item_id=schedule_item_id,
        worker_id=str(safe_metadata.get("worker_id") or receipt_source.get("worker_id")),
        note=str(safe_metadata.get("note"))
        if safe_metadata.get("note") is not None
        else None,
    )
    envelope_entry = _build_artifact_ledger_payload(
        session_id=session_id,
        artifact_kind="provider_output_envelope",
        source_id=str(envelope_payload["envelope_id"]),
        status="imported_runner_recorded_review_only",
        compact=_compact_provider_output_envelope(envelope_payload),
        ts=ts,
        latest_run=latest_run,
        schedule_item_id=schedule_item_id,
        worker_id=str(safe_metadata.get("worker_id") or envelope_source.get("worker_id")),
        note=str(safe_metadata.get("note"))
        if safe_metadata.get("note") is not None
        else None,
    )
    _upsert_generation_artifact_ledger(receipt_entry)
    _upsert_generation_artifact_ledger(envelope_entry)
    ledger_items = _load_generation_artifact_ledger_items(session_id, run_id)
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "worker_step": {
            "status": "imported",
            "worker_mode": "provider_adapter_runner_output_import",
            "provider_call_count": 0,
            "world_mutation_count": 0,
            "activation_allowed_count": 0,
            "schedule_item_id": schedule_item_id,
            "authorization_ref": authorization_ref,
            "upstream_request_id": executor_request_entry.get("source_id"),
            "execution_receipt_id": receipt_payload["execution_receipt_id"],
            "envelope_id": envelope_payload["envelope_id"],
            "import_refs": {
                "receipt_path": _display_import_path(receipt_path),
                "envelope_path": _display_import_path(envelope_path),
            },
        },
        "generation_executor_run_request": executor_request_entry.get("compact"),
        "provider_execution_authorization": authorization_entry.get("compact"),
        "provider_adapter_execution_receipt": receipt_entry["compact"],
        "provider_output_envelope": envelope_entry["compact"],
        "generation_artifact_ledger": _compact_generation_artifact_ledger(ledger_items),
    }


def import_provider_artifact_review_outputs(
    session_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    latest_run = _load_latest_generation_schedule_run(session_id)
    if latest_run is None:
        raise InvalidQueueTransitionError(
            "generation schedule run is required before importing provider artifact review outputs"
        )
    safe_metadata = metadata if isinstance(metadata, dict) else {}
    run_id = str(latest_run.get("run_id"))
    schedule_item_id = _requested_schedule_item_id(safe_metadata)
    if not schedule_item_id:
        raise InvalidQueueTransitionError(
            "schedule_item_id is required before importing provider artifact review outputs"
        )
    staging_path = _resolve_import_path(
        safe_metadata.get("staging_path"),
        label="staging_path",
    )
    promotion_path = _resolve_import_path(
        safe_metadata.get("promotion_report_path"),
        label="promotion_report_path",
    )
    staging = _load_runner_import_json(staging_path, label="staging_path")
    promotion = _load_runner_import_json(
        promotion_path,
        label="promotion_report_path",
    )
    staging_errors = validate_provider_artifact_staging_manifest(staging)
    promotion_errors = validate_provider_artifact_promotion_report(promotion)
    if staging_errors or promotion_errors:
        raise ValueError(
            "provider artifact review outputs failed validation: "
            f"staging={staging_errors}; promotion={promotion_errors}"
        )
    source_staging_ref = promotion.get("source_staging_ref")
    source_staging_path = _resolve_import_path(
        source_staging_ref,
        label="promotion_report.source_staging_ref",
    )
    if source_staging_path != staging_path:
        raise InvalidQueueTransitionError(
            "promotion_report.source_staging_ref must reference staging_path"
        )
    source_envelope_id = str(staging.get("source_envelope_id") or "")
    envelope_entry = _latest_provider_output_envelope_ledger_entry(
        session_id,
        run_id,
        schedule_item_id,
        source_envelope_id,
    )
    if envelope_entry is None:
        raise InvalidQueueTransitionError(
            "matching provider output envelope is required before importing provider artifact review outputs"
        )
    if str(promotion.get("source_staging_id") or "") != str(staging.get("manifest_id") or ""):
        raise InvalidQueueTransitionError(
            "promotion_report.source_staging_id must match staging manifest_id"
        )
    staged_ids = {
        artifact.get("artifact_id")
        for artifact in staging.get("staged_artifacts", [])
        if isinstance(artifact, dict)
    }
    reviewed_ids = {
        artifact.get("staged_artifact_id")
        for artifact in promotion.get("reviewed_artifacts", [])
        if isinstance(artifact, dict)
    }
    missing_review_refs = sorted(str(item) for item in reviewed_ids - staged_ids)
    if missing_review_refs:
        raise InvalidQueueTransitionError(
            "promotion reviewed_artifacts must reference staged_artifacts: "
            + ", ".join(missing_review_refs)
        )
    ts = now_iso()
    worker_id = str(safe_metadata.get("worker_id") or "provider_artifact_review_import")
    note = str(safe_metadata.get("note")) if safe_metadata.get("note") is not None else None
    staging_entry = _build_artifact_ledger_payload(
        session_id=session_id,
        artifact_kind="provider_artifact_staging_manifest",
        source_id=str(staging["manifest_id"]),
        status="imported_staged_review_only",
        compact=_compact_provider_artifact_staging(staging),
        ts=ts,
        latest_run=latest_run,
        schedule_item_id=schedule_item_id,
        worker_id=worker_id,
        note=note,
    )
    decision = promotion.get("decision", {})
    if not isinstance(decision, dict):
        decision = {}
    promotion_allowed = decision.get("promotion_allowed") is True
    promotion_entry = _build_artifact_ledger_payload(
        session_id=session_id,
        artifact_kind="provider_artifact_promotion_report",
        source_id=str(promotion["report_id"]),
        status="promotion_allowed" if promotion_allowed else "promotion_blocked",
        compact=_compact_provider_artifact_promotion_report(promotion),
        ts=ts,
        latest_run=latest_run,
        schedule_item_id=schedule_item_id,
        worker_id=worker_id,
        note=note,
    )
    _upsert_generation_artifact_ledger(staging_entry)
    _upsert_generation_artifact_ledger(promotion_entry)
    ledger_items = _load_generation_artifact_ledger_items(session_id, run_id)
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "worker_step": {
            "status": "imported",
            "worker_mode": "provider_artifact_review_output_import",
            "provider_call_count": 0,
            "world_mutation_count": 0,
            "activation_allowed_count": 0,
            "schedule_item_id": schedule_item_id,
            "source_envelope_id": source_envelope_id,
            "staging_manifest_id": staging["manifest_id"],
            "promotion_report_id": promotion["report_id"],
            "promotion_allowed": promotion_allowed,
            "import_refs": {
                "staging_path": _display_import_path(staging_path),
                "promotion_report_path": _display_import_path(promotion_path),
            },
        },
        "provider_output_envelope": envelope_entry.get("compact"),
        "provider_artifact_staging": staging_entry["compact"],
        "provider_artifact_promotion_report": promotion_entry["compact"],
        "generation_artifact_ledger": _compact_generation_artifact_ledger(ledger_items),
    }


def get_generation_artifact_ledger(session_id: str) -> dict[str, Any]:
    latest_run = _load_latest_generation_schedule_run(session_id)
    run_id = str(latest_run.get("run_id")) if latest_run is not None else None
    items = _load_generation_artifact_ledger_items(session_id, run_id)
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "generation_schedule_run": _compact_generation_schedule_run(latest_run),
        "generation_artifact_ledger": _compact_generation_artifact_ledger(items),
    }


def _ledger_entry_ref(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    compact = item.get("compact")
    if not isinstance(compact, dict):
        compact = {}
    return {
        "ledger_id": item.get("ledger_id"),
        "artifact_kind": item.get("artifact_kind"),
        "source_id": item.get("source_id"),
        "status": item.get("status"),
        "updated_at": item.get("updated_at"),
        "compact": compact,
    }


def _prefetch_cache_status(
    queue_item: dict[str, Any],
    refs: dict[str, dict[str, Any] | None],
) -> str:
    promotion_ref = refs.get("provider_artifact_promotion_report")
    if promotion_ref is not None:
        promotion_compact = promotion_ref.get("compact")
        if isinstance(promotion_compact, dict):
            if promotion_compact.get("promotion_allowed") is True:
                return "promotion_allowed_pending_activation"
            decision = promotion_compact.get("promotion_decision")
            if decision is not None:
                return "promotion_blocked"
        if promotion_ref.get("status") == "promotion_allowed":
            return "promotion_allowed_pending_activation"
        return "promotion_blocked"
    if refs.get("provider_artifact_staging_manifest") is not None:
        return "staged_review_only"
    if refs.get("provider_output_envelope") is not None:
        return "review_only_envelope_ready"
    if refs.get("provider_adapter_execution_receipt") is not None:
        return "adapter_receipt_recorded"
    if refs.get("provider_execution_authorization") is not None:
        return "authorized_pending_adapter"
    if refs.get("generation_executor_run_request") is not None:
        return "executor_request_prepared"
    queue_status = str(queue_item.get("queue_status") or queue_item.get("status") or "")
    if queue_status == "waiting_review":
        return "waiting_review_without_envelope"
    if queue_status in {"queued", "completed", "fallback_ready", "failed", "claimed"}:
        return queue_status
    return "not_started"


def get_generation_prefetch_cache(session_id: str) -> dict[str, Any]:
    latest_run = _load_latest_generation_schedule_run(session_id)
    run_id = str(latest_run.get("run_id")) if latest_run is not None else None
    queue_items = _load_generation_queue_items(session_id, run_id) if run_id else []
    ledger_items = _load_generation_artifact_ledger_items(session_id, run_id)
    by_schedule_item: dict[str, dict[str, Any]] = {}
    for queue_item in queue_items:
        schedule_item_id = str(queue_item.get("schedule_item_id") or "")
        if not schedule_item_id:
            continue
        by_schedule_item[schedule_item_id] = {
            "schedule_item_id": schedule_item_id,
            "object_kind": queue_item.get("object_kind"),
            "object_ref": queue_item.get("object_ref"),
            "latency_class": queue_item.get("latency_class"),
            "queue_status": queue_item.get("status"),
            "provider_review_required": queue_item.get(
                "provider_review_required"
            )
            is True,
            "attempt_count": int(queue_item.get("attempt_count", 0)),
            "max_attempts": int(queue_item.get("max_attempts", 0)),
            "fallback_ref": queue_item.get("fallback_ref"),
            "revalidate_before_activation": queue_item.get(
                "revalidate_before_activation"
            )
            is True,
            "refs": {
                "generation_executor_run_request": None,
                "provider_execution_authorization": None,
                "provider_adapter_execution_receipt": None,
                "provider_output_envelope": None,
                "provider_artifact_staging_manifest": None,
                "provider_artifact_promotion_report": None,
            },
        }
    for ledger_item in ledger_items:
        schedule_item_id = str(ledger_item.get("schedule_item_id") or "")
        if not schedule_item_id or schedule_item_id not in by_schedule_item:
            continue
        artifact_kind = str(ledger_item.get("artifact_kind") or "")
        refs = by_schedule_item[schedule_item_id]["refs"]
        if artifact_kind in refs:
            refs[artifact_kind] = _ledger_entry_ref(ledger_item)
    cache_items: list[dict[str, Any]] = []
    for item in by_schedule_item.values():
        refs = item["refs"]
        envelope_ref = refs.get("provider_output_envelope")
        envelope_compact = (
            envelope_ref.get("compact")
            if isinstance(envelope_ref, dict)
            and isinstance(envelope_ref.get("compact"), dict)
            else {}
        )
        activation_gate = (
            envelope_compact.get("activation_gate")
            if isinstance(envelope_compact, dict)
            and isinstance(envelope_compact.get("activation_gate"), dict)
            else {}
        )
        promotion_ref = refs.get("provider_artifact_promotion_report")
        promotion_compact = (
            promotion_ref.get("compact")
            if isinstance(promotion_ref, dict)
            and isinstance(promotion_ref.get("compact"), dict)
            else {}
        )
        promotion_gate = (
            promotion_compact.get("promotion_gate")
            if isinstance(promotion_compact.get("promotion_gate"), dict)
            else {}
        )
        item["cache_status"] = _prefetch_cache_status(item, refs)
        item["runtime_ready"] = False
        item["recorded_provider_call_count"] = 1 if (
            isinstance(envelope_compact.get("provider_call"), dict)
            and envelope_compact["provider_call"].get("performed") is True
        ) else 0
        item["provider_call_count_by_this_request"] = 0
        item["world_mutation_count_by_this_request"] = 0
        item["activation_gate"] = {
            "activation_allowed": activation_gate.get("activation_allowed") is True,
            "blocked_reason": activation_gate.get("blocked_reason"),
            "required_next_gates": activation_gate.get("required_next_gates", []),
        }
        item["promotion_gate"] = {
            "promotion_allowed": promotion_compact.get("promotion_allowed") is True,
            "promotion_decision": promotion_compact.get("promotion_decision"),
            "blocked_reason": promotion_compact.get("blocked_reason")
            or promotion_gate.get("blocked_reason"),
            "required_next_actions": promotion_compact.get("required_next_actions", []),
            "gate_statuses": promotion_compact.get("gate_statuses", []),
        }
        item["activation_allowed"] = item["activation_gate"]["activation_allowed"]
        item["promotion_allowed"] = item["promotion_gate"]["promotion_allowed"]
        item["review_only"] = True
        cache_items.append(item)
    summary_counts = Counter(str(item.get("cache_status")) for item in cache_items)
    ready_count = sum(
        1 for item in cache_items if item.get("cache_status") == "review_only_envelope_ready"
    )
    staged_count = sum(
        1
        for item in cache_items
        if item.get("cache_status")
        in {
            "staged_review_only",
            "promotion_blocked",
            "promotion_allowed_pending_activation",
        }
    )
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "generation_schedule_run": _compact_generation_schedule_run(latest_run),
        "generation_prefetch_cache": {
            "summary": {
                "item_count": len(cache_items),
                "cache_status_counts": dict(sorted(summary_counts.items())),
                "review_only_envelope_ready_count": ready_count,
                "staged_or_reviewed_count": staged_count,
                "runtime_ready_count": 0,
                "recorded_provider_call_count": sum(
                    int(item.get("recorded_provider_call_count", 0))
                    for item in cache_items
                ),
                "provider_call_count_by_this_request": 0,
                "world_mutation_count_by_this_request": 0,
                "activation_allowed_count": sum(
                    1 for item in cache_items if item.get("activation_allowed") is True
                ),
                "promotion_allowed_count": sum(
                    1 for item in cache_items if item.get("promotion_allowed") is True
                ),
            },
            "items": cache_items,
        },
    }


def stage_provider_artifacts_fixture(
    session_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ts = now_iso()
    safe_metadata = metadata if isinstance(metadata, dict) else {}
    worker_id = safe_metadata.get("worker_id") or "provider_artifact_fixture_stager"
    note = safe_metadata.get("note")
    profile = str(safe_metadata.get("artifact_profile") or "default")
    latest_run = _load_latest_generation_schedule_run(session_id)
    if latest_run is None:
        raise InvalidQueueTransitionError(
            "generation schedule run is required before staging provider artifacts"
        )
    run_id = str(latest_run.get("run_id"))
    envelope_path, staging_path, promotion_path, normalized_profile = (
        _provider_artifact_fixture_paths(profile)
    )
    envelope = _load_json(envelope_path)
    staging = _load_json(staging_path)
    promotion = _load_json(promotion_path)
    envelope_errors = validate_provider_output_envelope(envelope)
    staging_errors = validate_provider_artifact_staging_manifest(staging)
    promotion_errors = validate_provider_artifact_promotion_report(promotion)
    if envelope_errors or staging_errors or promotion_errors:
        raise ValueError(
            "provider artifact fixtures failed validation: "
            f"envelope={envelope_errors}; staging={staging_errors}; "
            f"promotion={promotion_errors}"
        )
    source = envelope.get("source", {}) if isinstance(envelope.get("source"), dict) else {}
    schedule_item_id = source.get("schedule_item_id")
    executor_request_entry = _latest_generation_executor_request_ledger_entry(
        session_id,
        run_id,
        str(schedule_item_id) if schedule_item_id else None,
    )
    if executor_request_entry is None:
        raise InvalidQueueTransitionError(
            "matching generation executor request is required before staging provider artifacts"
        )
    provider_call = envelope.get("provider_call", {})
    if not isinstance(provider_call, dict):
        provider_call = {}
    authorization_ref = str(provider_call.get("authorization_ref") or "")
    authorization_entry = _latest_provider_authorization_ledger_entry(
        session_id,
        run_id,
        str(schedule_item_id or ""),
        authorization_ref,
    )
    if authorization_entry is None:
        raise InvalidQueueTransitionError(
            "matching provider execution authorization is required before staging provider artifacts"
        )
    adapter_execution_entry = _latest_provider_adapter_execution_ledger_entry(
        session_id,
        run_id,
        str(schedule_item_id or ""),
        authorization_ref,
    )
    if adapter_execution_entry is None:
        raise InvalidQueueTransitionError(
            "matching provider adapter execution receipt is required before staging provider artifacts"
        )
    envelope_entry = _build_artifact_ledger_payload(
        session_id=session_id,
        artifact_kind="provider_output_envelope",
        source_id=str(envelope.get("envelope_id")),
        status="recorded_review_only",
        compact=_compact_provider_output_envelope(envelope),
        ts=ts,
        latest_run=latest_run,
        schedule_item_id=str(schedule_item_id) if schedule_item_id else None,
        worker_id=str(worker_id),
        note=str(note) if note is not None else None,
    )
    staging_entry = _build_artifact_ledger_payload(
        session_id=session_id,
        artifact_kind="provider_artifact_staging_manifest",
        source_id=str(staging.get("manifest_id")),
        status="staged_review_only",
        compact=_compact_provider_artifact_staging(staging),
        ts=ts,
        latest_run=latest_run,
        schedule_item_id=str(schedule_item_id) if schedule_item_id else None,
        worker_id=str(worker_id),
        note=str(note) if note is not None else None,
    )
    promotion_decision = promotion.get("decision", {})
    promotion_allowed = (
        isinstance(promotion_decision, dict)
        and promotion_decision.get("promotion_allowed") is True
    )
    promotion_entry = _build_artifact_ledger_payload(
        session_id=session_id,
        artifact_kind="provider_artifact_promotion_report",
        source_id=str(promotion.get("report_id")),
        status="promotion_allowed" if promotion_allowed else "promotion_blocked",
        compact=_compact_provider_artifact_promotion_report(promotion),
        ts=ts,
        latest_run=latest_run,
        schedule_item_id=str(schedule_item_id) if schedule_item_id else None,
        worker_id=str(worker_id),
        note=str(note) if note is not None else None,
    )
    _upsert_generation_artifact_ledger(envelope_entry)
    _upsert_generation_artifact_ledger(staging_entry)
    _upsert_generation_artifact_ledger(promotion_entry)
    items = _load_generation_artifact_ledger_items(session_id, run_id)
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "worker_step": {
            "status": "staged",
            "worker_mode": "fixture_backed_provider_artifact_stager",
            "provider_call_count": 0,
            "world_mutation_count": 0,
            "activation_allowed_count": 0,
            "upstream_request_id": executor_request_entry.get("source_id"),
            "authorization_ref": authorization_ref,
            "artifact_profile": normalized_profile,
            "fixture_refs": {
                "provider_output_envelope": _rel(envelope_path),
                "provider_artifact_staging": _rel(staging_path),
                "provider_artifact_promotion_report": _rel(promotion_path),
            },
        },
        "generation_executor_run_request": executor_request_entry.get("compact"),
        "provider_execution_authorization": authorization_entry.get("compact"),
        "provider_adapter_execution_receipt": adapter_execution_entry.get("compact"),
        "provider_output_envelope": envelope_entry["compact"],
        "provider_artifact_staging": staging_entry["compact"],
        "provider_artifact_promotion_report": promotion_entry["compact"],
        "generation_artifact_ledger": _compact_generation_artifact_ledger(items),
    }


def run_fixture_executor_chain(
    session_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    safe_metadata = metadata if isinstance(metadata, dict) else {}
    requested_profile = str(safe_metadata.get("artifact_profile") or "default")
    fixture_metadata = _provider_artifact_fixture_metadata(requested_profile)
    requested_schedule_item_id = _requested_schedule_item_id(safe_metadata)
    schedule_item_id = fixture_metadata["schedule_item_id"]
    if requested_schedule_item_id and requested_schedule_item_id != schedule_item_id:
        raise InvalidQueueTransitionError(
            "artifact_profile fixture schedule_item_id does not match requested "
            f"schedule_item_id: {requested_schedule_item_id}"
        )
    authorization_ref = str(
        safe_metadata.get("authorization_ref")
        or fixture_metadata["authorization_ref"]
    )
    if authorization_ref != fixture_metadata["authorization_ref"]:
        raise InvalidQueueTransitionError(
            "authorization_ref does not match selected artifact_profile fixture"
        )
    worker_prefix = str(
        safe_metadata.get("worker_id") or "fixture_executor_chain"
    )
    note = safe_metadata.get("note")
    latest_run = _load_latest_generation_schedule_run(session_id)
    created_run = latest_run is None
    run_payload = (
        create_generation_schedule_run(session_id)["generation_schedule_run"]
        if created_run
        else latest_run
    )

    def _step_metadata(step_name: str, include_authorization: bool = False) -> dict[str, Any]:
        step_metadata: dict[str, Any] = {
            "worker_id": f"{worker_prefix}_{step_name}",
            "schedule_item_id": schedule_item_id,
            "note": note,
        }
        if include_authorization:
            step_metadata["authorization_ref"] = authorization_ref
        return step_metadata

    dry_step = run_generation_schedule_dry_worker_step(
        session_id,
        _step_metadata("dry_run"),
    )
    waiting_row = _load_generation_item_row_by_status(
        session_id,
        "waiting_review",
        schedule_item_id,
    )
    if waiting_row is None:
        raise InvalidQueueTransitionError(
            "fixture executor chain requires the schedule item to reach waiting_review"
        )
    guard_step = run_generation_schedule_live_executor_guard(
        session_id,
        _step_metadata("live_guard"),
    )
    executor_request_step = prepare_generation_executor_run_request(
        session_id,
        _step_metadata("executor_request"),
    )
    authorization_step = grant_provider_execution_authorization(
        session_id,
        _step_metadata("provider_authorization", include_authorization=True),
    )
    adapter_step = run_provider_adapter_fixture(
        session_id,
        _step_metadata("provider_adapter", include_authorization=True),
    )
    staging_step = stage_provider_artifacts_fixture(
        session_id,
        {
            "worker_id": f"{worker_prefix}_artifact_staging",
            "schedule_item_id": schedule_item_id,
            "artifact_profile": fixture_metadata["artifact_profile"],
            "note": note,
        },
    )
    ledger_summary = staging_step["generation_artifact_ledger"]["summary"]
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "executor_chain": {
            "status": "completed_review_only_promotion_blocked",
            "worker_mode": "fixture_backed_executor_chain",
            "created_generation_schedule_run": created_run,
            "run_id": run_payload.get("run_id"),
            "schedule_item_id": schedule_item_id,
            "artifact_profile": fixture_metadata["artifact_profile"],
            "authorization_ref": authorization_ref,
            "provider_call_count": 0,
            "world_mutation_count": 0,
            "activation_allowed_count": 0,
            "promotion_allowed_count": int(
                ledger_summary.get("promotion_allowed_count", 0)
            ),
            "fixture_refs": {
                "provider_output_envelope": fixture_metadata[
                    "provider_output_envelope"
                ],
                **staging_step["worker_step"]["fixture_refs"],
            },
        },
        "steps": {
            "dry_run_step": dry_step["worker_step"],
            "live_executor_guard": guard_step["worker_step"],
            "generation_executor_run_request": executor_request_step["worker_step"],
            "provider_execution_authorization": authorization_step["worker_step"],
            "provider_adapter_execution_receipt": adapter_step["worker_step"],
            "provider_artifact_staging": staging_step["worker_step"],
        },
        "generation_schedule_run": _compact_generation_schedule_run(
            _load_latest_generation_schedule_run(session_id)
        ),
        "generation_schedule_queue": staging_step.get("generation_schedule_queue")
        or get_generation_schedule_queue(session_id)["generation_schedule_queue"],
        "generation_executor_run_request": staging_step[
            "generation_executor_run_request"
        ],
        "provider_execution_authorization": staging_step[
            "provider_execution_authorization"
        ],
        "provider_adapter_execution_receipt": staging_step[
            "provider_adapter_execution_receipt"
        ],
        "provider_output_envelope": staging_step["provider_output_envelope"],
        "provider_artifact_staging": staging_step["provider_artifact_staging"],
        "provider_artifact_promotion_report": staging_step[
            "provider_artifact_promotion_report"
        ],
        "generation_artifact_ledger": staging_step["generation_artifact_ledger"],
    }


def get_generation_scheduler_evidence(session_id: str) -> dict[str, Any]:
    plan = _load_generation_schedule_plan()
    run_report = _load_generation_schedule_run_report()
    latest_run = _load_latest_generation_schedule_run(session_id)
    latest_queue = _load_generation_queue_items(session_id) if latest_run is not None else []
    latest_worker_cache = (
        _load_worker_cache_items(session_id) if latest_run is not None else []
    )
    latest_provider_guard_logs = (
        _load_provider_guard_logs(session_id, str(latest_run.get("run_id")))
        if latest_run is not None
        else []
    )
    latest_artifact_ledger = (
        _load_generation_artifact_ledger_items(session_id, str(latest_run.get("run_id")))
        if latest_run is not None
        else []
    )
    return {
        "refs": _generation_schedule_refs(),
        "buffer": _build_generation_schedule_buffer(plan, run_report),
        "latest_run": _compact_generation_schedule_run(latest_run),
        "latest_queue": _compact_generation_queue(latest_queue),
        "latest_worker_cache": _compact_worker_cache(latest_worker_cache),
        "latest_provider_guard_logs": _compact_provider_guard_logs(
            latest_provider_guard_logs
        ),
        "latest_artifact_ledger": _compact_generation_artifact_ledger(
            latest_artifact_ledger
        ),
    }
