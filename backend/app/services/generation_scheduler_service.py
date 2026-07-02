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
_PROVIDER_OUTPUT_ENVELOPE_EXAMPLE = (
    _REPO_ROOT
    / "examples/provider_artifact_staging/p1b_provider_artifact_staging.source_envelope.json"
)
_PROVIDER_ARTIFACT_STAGING_EXAMPLE = (
    _REPO_ROOT / "examples/provider_artifact_staging/p1b_provider_artifact_staging.example.json"
)
_PROVIDER_ARTIFACT_PROMOTION_REPORT_EXAMPLE = (
    _REPO_ROOT
    / "examples/provider_artifact_staging/p1b_provider_artifact_promotion_report.example.json"
)
_MVP_CONTEXT_PACKAGE_EXAMPLE = (
    _REPO_ROOT / "examples/review_packs/mvp_first_battle.context_package.json"
)
_MVP_CGOP_EXAMPLE = (
    _REPO_ROOT / "examples/review_packs/mvp_light_snare.compiled_game_object_package.json"
)
_TOOLS_DEV_DIR = _REPO_ROOT / "tools" / "dev"
if str(_TOOLS_DEV_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DEV_DIR))

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


class GenerationSchedulerFixtureNotFoundError(LookupError):
    """Raised when scheduler fixture/session state is missing."""


class InvalidQueueTransitionError(ValueError):
    """Raised when a scheduler queue transition violates the current state."""


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _dump_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _rel(path: Path) -> str:
    return path.relative_to(_REPO_ROOT).as_posix()


def _new_generation_schedule_run_id() -> str:
    return f"gsrun_{secrets.token_urlsafe(12)}"


def _safe_id_fragment(value: Any) -> str:
    return "".join(
        ch if ch.isalnum() or ch in {"_", "-"} else "_"
        for ch in str(value or "")
    )


def _generation_schedule_refs() -> dict[str, str]:
    return {
        "plan": _rel(_GENERATION_SCHEDULE_PLAN),
        "run_report": _rel(_GENERATION_SCHEDULE_RUN_REPORT),
    }


def _load_generation_schedule_plan() -> dict[str, Any]:
    return _load_json(_GENERATION_SCHEDULE_PLAN)


def _load_generation_schedule_run_report() -> dict[str, Any]:
    return _load_json(_GENERATION_SCHEDULE_RUN_REPORT)


def _build_generation_schedule_buffer(
    plan: dict[str, Any], run_report: dict[str, Any]
) -> dict[str, Any]:
    plan_items = [item for item in plan.get("items", []) if isinstance(item, dict)]
    report_items = [
        item for item in run_report.get("items", []) if isinstance(item, dict)
    ]
    report_by_item_id = {
        str(item.get("schedule_item_id")): item
        for item in report_items
        if item.get("schedule_item_id")
    }
    latency_counts = Counter(
        str(item.get("latency_class", "unknown")) for item in plan_items
    )
    result_counts = Counter(
        str(item.get("result_status", "unknown")) for item in report_items
    )
    provider_review_required_count = sum(
        1 for item in report_items if item.get("provider_review_required") is True
    )
    world_commit_candidate_count = sum(
        1
        for item in plan_items
        if isinstance(item.get("commit_policy"), dict)
        and item["commit_policy"].get("world_commit") not in (None, "none")
    )
    buffer_items = []
    for item in plan_items:
        item_id = str(item.get("schedule_item_id", ""))
        report_item = report_by_item_id.get(item_id, {})
        buffer_items.append(
            {
                "schedule_item_id": item_id,
                "object_kind": item.get("object_kind"),
                "object_ref": item.get("object_ref"),
                "latency_class": item.get("latency_class"),
                "plan_status": item.get("status"),
                "priority": item.get("priority"),
                "dry_run_action": report_item.get("action"),
                "dry_run_status": report_item.get("result_status"),
                "provider_policy": item.get("provider_policy", {}),
                "provider_review_required": (
                    report_item.get("provider_review_required") is True
                ),
                "player_visible": item.get("player_visible") is True,
                "fallback_ref": item.get("fallback_ref"),
                "revalidate_before_activation": (
                    isinstance(item.get("commit_policy"), dict)
                    and item["commit_policy"].get("revalidate_before_activation") is True
                ),
            }
        )
    summary = run_report.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    return {
        "status": "fixture_backed_scheduler_buffer_ready",
        "control_plane_mode": "review_only_dry_run",
        "plan_id": plan.get("plan_id"),
        "report_id": run_report.get("report_id"),
        "item_count": len(plan_items),
        "latency_class_counts": dict(sorted(latency_counts.items())),
        "result_status_counts": dict(sorted(result_counts.items())),
        "ready_reused_count": int(summary.get("ready_reused_count", 0)),
        "fallback_selected_count": int(summary.get("fallback_selected_count", 0)),
        "scheduled_count": int(summary.get("scheduled_count", 0)),
        "provider_call_count": int(summary.get("provider_call_count", 0)),
        "world_mutation_count": int(summary.get("world_mutation_count", 0)),
        "provider_review_required_count": provider_review_required_count,
        "world_commit_candidate_count": world_commit_candidate_count,
        "activation_requires_revalidation": (
            isinstance(plan.get("authority"), dict)
            and plan["authority"].get("activation_requires_revalidation") is True
        ),
        "items": buffer_items,
    }


def _build_generation_schedule_payload(
    plan: dict[str, Any], run_report: dict[str, Any]
) -> dict[str, Any]:
    return {
        "refs": _generation_schedule_refs(),
        "buffer": _build_generation_schedule_buffer(plan, run_report),
        "plan": plan,
        "run_report": run_report,
    }


def _build_generation_schedule_run_payload(
    session_id: str, run_id: str, ts: str
) -> dict[str, Any]:
    plan = _load_generation_schedule_plan()
    run_report = _load_generation_schedule_run_report()
    return {
        "run_id": run_id,
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "status": "completed",
        "scheduler_mode": "fixture_backed_dry_run",
        "created_at": ts,
        "updated_at": ts,
        "completed_at": ts,
        "generation_schedule": {
            "refs": _generation_schedule_refs(),
            "buffer": _build_generation_schedule_buffer(plan, run_report),
        },
        "execution_policy": run_report.get("execution_policy", {}),
        "source_report_summary": run_report.get("summary", {}),
        "notes": [
            "本次运行只复用已审 fixture、静态 fallback 与 dry-run 报告。",
            "本次运行不调用外部模型，不写入世界状态，不激活预生成候选。",
        ],
    }


def _generation_queue_status(item: dict[str, Any]) -> str:
    dry_run_status = item.get("dry_run_status")
    if dry_run_status == "passed":
        return "completed"
    if dry_run_status == "fallback":
        return "fallback_ready"
    if dry_run_status == "scheduled":
        return "queued"
    return "blocked"


def _build_generation_queue_item_payload(
    session_id: str, run_id: str, item: dict[str, Any], position: int, ts: str
) -> dict[str, Any]:
    status = _generation_queue_status(item)
    return {
        "queue_item_id": f"gq_{run_id}_{position:02d}",
        "run_id": run_id,
        "session_id": session_id,
        "schedule_item_id": item.get("schedule_item_id"),
        "object_kind": item.get("object_kind"),
        "object_ref": item.get("object_ref"),
        "latency_class": item.get("latency_class"),
        "status": status,
        "action": item.get("dry_run_action"),
        "dry_run_status": item.get("dry_run_status"),
        "provider_review_required": item.get("provider_review_required") is True,
        "player_visible": item.get("player_visible") is True,
        "fallback_ref": item.get("fallback_ref"),
        "provider_policy": item.get("provider_policy", {}),
        "max_attempts": int(
            item.get("provider_policy", {}).get("max_attempts", 0)
            if isinstance(item.get("provider_policy"), dict)
            else 0
        ),
        "attempt_count": 0,
        "revalidate_before_activation": item.get("revalidate_before_activation") is True,
        "created_at": ts,
        "updated_at": ts,
    }


def _build_generation_queue_items_from_run(
    run_payload: dict[str, Any], ts: str
) -> list[dict[str, Any]]:
    schedule = run_payload.get("generation_schedule", {})
    buffer = schedule.get("buffer", {}) if isinstance(schedule, dict) else {}
    items = buffer.get("items", []) if isinstance(buffer, dict) else []
    if not isinstance(items, list):
        return []
    return [
        _build_generation_queue_item_payload(
            str(run_payload["session_id"]),
            str(run_payload["run_id"]),
            item,
            position,
            ts,
        )
        for position, item in enumerate(items, start=1)
        if isinstance(item, dict)
    ]


def _insert_generation_queue_items(items: list[dict[str, Any]]) -> None:
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


def _load_latest_generation_schedule_run(session_id: str) -> dict[str, Any] | None:
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


def _load_generation_queue_items(
    session_id: str, run_id: str | None = None
) -> list[dict[str, Any]]:
    if run_id is None:
        latest = _load_latest_generation_schedule_run(session_id)
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


def _generation_queue_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(item.get("status", "unknown")) for item in items)
    latency_counts = Counter(str(item.get("latency_class", "unknown")) for item in items)
    return {
        "item_count": len(items),
        "status_counts": dict(sorted(status_counts.items())),
        "latency_class_counts": dict(sorted(latency_counts.items())),
        "claimable_count": sum(1 for item in items if item.get("status") == "queued"),
        "completed_count": sum(1 for item in items if item.get("status") == "completed"),
        "fallback_ready_count": sum(
            1 for item in items if item.get("status") == "fallback_ready"
        ),
        "waiting_review_count": sum(
            1 for item in items if item.get("status") == "waiting_review"
        ),
        "failed_count": sum(1 for item in items if item.get("status") == "failed"),
        "provider_review_required_count": sum(
            1 for item in items if item.get("provider_review_required") is True
        ),
    }


def _worker_cache_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(item.get("status", "unknown")) for item in items)
    kind_counts = Counter(str(item.get("object_kind", "unknown")) for item in items)
    return {
        "item_count": len(items),
        "status_counts": dict(sorted(status_counts.items())),
        "object_kind_counts": dict(sorted(kind_counts.items())),
        "provider_call_count": sum(
            1 for item in items if item.get("provider_call_performed") is True
        ),
        "world_mutation_count": sum(
            1 for item in items if item.get("world_mutation_performed") is True
        ),
        "activation_allowed_count": sum(
            1 for item in items if item.get("activation_allowed_now") is True
        ),
        "review_required_count": sum(
            1 for item in items if item.get("review_required") is True
        ),
    }


def _compact_worker_cache(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "summary": _worker_cache_summary(items),
        "items": items,
    }


def _provider_guard_log_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(item.get("status", "unknown")) for item in items)
    profile_counts = Counter(str(item.get("provider_profile", "unknown")) for item in items)
    return {
        "item_count": len(items),
        "status_counts": dict(sorted(status_counts.items())),
        "provider_profile_counts": dict(sorted(profile_counts.items())),
        "provider_call_count": sum(
            1 for item in items if item.get("provider_call_performed") is True
        ),
        "world_mutation_count": sum(
            1 for item in items if item.get("world_mutation_performed") is True
        ),
        "activation_allowed_count": sum(
            1 for item in items if item.get("activation_allowed_now") is True
        ),
    }


def _compact_provider_guard_logs(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "summary": _provider_guard_log_summary(items),
        "items": items,
    }


def _compact_generation_schedule_run(run: dict[str, Any] | None) -> dict[str, Any] | None:
    if run is None:
        return None
    schedule = run.get("generation_schedule", {})
    buffer = schedule.get("buffer", {}) if isinstance(schedule, dict) else {}
    return {
        "run_id": run.get("run_id"),
        "status": run.get("status"),
        "scheduler_mode": run.get("scheduler_mode"),
        "created_at": run.get("created_at"),
        "completed_at": run.get("completed_at"),
        "provider_call_count": buffer.get("provider_call_count"),
        "world_mutation_count": buffer.get("world_mutation_count"),
        "scheduled_count": buffer.get("scheduled_count"),
        "fallback_selected_count": buffer.get("fallback_selected_count"),
    }


def _compact_generation_queue(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "summary": _generation_queue_summary(items),
        "items": items,
    }


def _load_generation_queue_item_row(
    session_id: str, schedule_item_id: str
) -> dict[str, Any]:
    latest = _load_latest_generation_schedule_run(session_id)
    if latest is None:
        raise GenerationSchedulerFixtureNotFoundError("generation_schedule_queue")
    run_id = str(latest.get("run_id", ""))
    with db_cursor() as cur:
        cur.execute(
            "SELECT id, run_id, schedule_item_id, status, payload FROM "
            "generation_schedule_queue_items "
            "WHERE session_id = ? AND run_id = ? AND schedule_item_id = ?",
            (session_id, run_id, schedule_item_id),
        )
        row = cur.fetchone()
    if row is None or not row.get("payload"):
        raise GenerationSchedulerFixtureNotFoundError(schedule_item_id)
    payload = json.loads(row["payload"])
    return {
        "id": row["id"],
        "run_id": row["run_id"],
        "schedule_item_id": row["schedule_item_id"],
        "status": row["status"],
        "payload": payload,
    }


def _worker_cache_id(run_id: str, schedule_item_id: str) -> str:
    safe_item_id = "".join(
        ch if ch.isalnum() or ch in {"_", "-"} else "_"
        for ch in str(schedule_item_id)
    )
    return f"gcache_{run_id}_{safe_item_id}"


def _activation_blocked_reason(payload: dict[str, Any]) -> str:
    if payload.get("provider_review_required") is True:
        return "review_required_before_activation"
    if payload.get("revalidate_before_activation") is True:
        return "revalidation_required_before_activation"
    return "fixture_worker_does_not_activate_content"


def _build_worker_cache_payload(payload: dict[str, Any], ts: str) -> dict[str, Any]:
    run_id = str(payload.get("run_id") or "")
    session_id = str(payload.get("session_id") or "")
    schedule_item_id = str(payload.get("schedule_item_id") or "")
    review_required = payload.get("provider_review_required") is True
    return {
        "cache_id": _worker_cache_id(run_id, schedule_item_id),
        "run_id": run_id,
        "session_id": session_id,
        "schedule_item_id": schedule_item_id,
        "object_kind": payload.get("object_kind"),
        "object_ref": payload.get("object_ref"),
        "latency_class": payload.get("latency_class"),
        "worker_id": payload.get("worker_id"),
        "attempt_count": int(payload.get("attempt_count", 0)),
        "max_attempts": int(payload.get("max_attempts", 0)),
        "status": payload.get("status"),
        "review_required": review_required,
        "provider_review_required": review_required,
        "provider_call_performed": False,
        "world_mutation_performed": False,
        "activation_allowed_now": False,
        "artifact_placeholder": {
            "status": "review_only_placeholder",
            "artifact_id": f"placeholder:{schedule_item_id}:{payload.get('attempt_count', 0)}",
            "provider_call_performed": False,
            "world_mutation_performed": False,
            "activation_allowed_now": False,
            "generated_content_ref": None,
        },
        "activation_gate": {
            "revalidate_before_activation": (
                payload.get("revalidate_before_activation") is True
            ),
            "blocked_reason": _activation_blocked_reason(payload),
        },
        "safe_content_policy": {
            "reads_env": False,
            "calls_provider": False,
            "writes_world_state": False,
            "stores_raw_prompt": False,
            "stores_provider_response": False,
        },
        "created_at": ts,
        "updated_at": ts,
    }


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
    with db_cursor() as cur:
        cur.execute(
            "UPDATE generation_schedule_queue_items "
            "SET status = ?, payload = ?, updated_at = ? WHERE id = ?",
            (next_status, _dump_payload(payload), ts, row["id"]),
        )
    return payload


def _load_next_queued_generation_item_row(session_id: str) -> dict[str, Any] | None:
    return _load_next_generation_item_row_by_status(session_id, "queued")


def _load_next_generation_item_row_by_status(
    session_id: str, status: str
) -> dict[str, Any] | None:
    latest = _load_latest_generation_schedule_run(session_id)
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
    if row is None or not row.get("payload"):
        return None
    return {
        "id": row["id"],
        "run_id": row["run_id"],
        "schedule_item_id": row["schedule_item_id"],
        "status": row["status"],
        "payload": json.loads(row["payload"]),
    }


def _provider_guard_id(payload: dict[str, Any], attempt_count: int) -> str:
    run_id = str(payload.get("run_id") or "")
    schedule_item_id = str(payload.get("schedule_item_id") or "")
    safe_item_id = _safe_id_fragment(schedule_item_id)
    return f"pguard_{run_id}_{safe_item_id}_{attempt_count:02d}"


def _generation_executor_request_id(payload: dict[str, Any], attempt_count: int) -> str:
    run_id = str(payload.get("run_id") or "")
    schedule_item_id = str(payload.get("schedule_item_id") or "")
    return f"gexec_{run_id}_{_safe_id_fragment(schedule_item_id)}_{attempt_count:02d}"


def _build_live_executor_guard_payload(
    payload: dict[str, Any],
    metadata: dict[str, Any] | None,
    ts: str,
) -> dict[str, Any]:
    provider_policy = payload.get("provider_policy")
    if not isinstance(provider_policy, dict):
        provider_policy = {}
    attempt_count = int(payload.get("attempt_count", 0))
    provider_mode = str(provider_policy.get("mode") or "unknown")
    provider_profile = str(provider_policy.get("profile") or "unknown")
    return {
        "guard_id": _provider_guard_id(payload, attempt_count),
        "schema_version": "generation_live_executor_guard.v0.1",
        "status": "blocked_pending_explicit_authorization",
        "run_id": payload.get("run_id"),
        "session_id": payload.get("session_id"),
        "schedule_item_id": payload.get("schedule_item_id"),
        "object_kind": payload.get("object_kind"),
        "object_ref": payload.get("object_ref"),
        "latency_class": payload.get("latency_class"),
        "provider_mode": provider_mode,
        "provider_profile": provider_profile,
        "worker_id": (metadata or {}).get("worker_id") or "live_executor_guard",
        "note": (metadata or {}).get("note"),
        "attempt_count": attempt_count,
        "max_attempts": int(payload.get("max_attempts", 0)),
        "provider_call_performed": False,
        "world_mutation_performed": False,
        "activation_allowed_now": False,
        "raw_prompt_stored": False,
        "provider_response_stored": False,
        "authorization": {
            "required": True,
            "granted": False,
            "reason": "explicit_user_authorization_required_before_live_provider_call",
        },
        "required_next_gates": [
            "explicit_user_authorization",
            "provider_adapter_execution",
            "artifact_manifest_write",
            "schema_or_media_validation",
            "manual_or_semantic_review",
            "activation_or_promotion_gate",
        ],
        "artifact_manifest_placeholder": {
            "status": "not_created",
            "reason": "provider_call_blocked_by_guard",
            "review_only": True,
        },
        "safe_content_policy": {
            "reads_env": False,
            "calls_provider": False,
            "writes_world_state": False,
            "stores_raw_prompt": False,
            "stores_provider_response": False,
        },
        "created_at": ts,
    }


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


def _compact_provider_output_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    source = envelope.get("source", {})
    if not isinstance(source, dict):
        source = {}
    provider_call = envelope.get("provider_call", {})
    if not isinstance(provider_call, dict):
        provider_call = {}
    result = envelope.get("redacted_result_summary", {})
    if not isinstance(result, dict):
        result = {}
    artifact_manifest = envelope.get("artifact_manifest", {})
    if not isinstance(artifact_manifest, dict):
        artifact_manifest = {}
    output_refs = artifact_manifest.get("output_refs", [])
    if not isinstance(output_refs, list):
        output_refs = []
    activation = envelope.get("activation_gate", {})
    if not isinstance(activation, dict):
        activation = {}
    return {
        "schema_version": envelope.get("schema_version"),
        "envelope_id": envelope.get("envelope_id"),
        "source": {
            "run_id": source.get("run_id"),
            "schedule_item_id": source.get("schedule_item_id"),
            "object_kind": source.get("object_kind"),
            "object_ref": source.get("object_ref"),
            "provider_profile": source.get("provider_profile"),
            "provider_mode": source.get("provider_mode"),
        },
        "provider_call": {
            "status": provider_call.get("status"),
            "performed": provider_call.get("performed"),
            "authorization_required": provider_call.get("authorization_required"),
            "authorization_granted": provider_call.get("authorization_granted"),
            "attempt_count": provider_call.get("attempt_count"),
            "max_attempts": provider_call.get("max_attempts"),
        },
        "result": {
            "result_kind": result.get("result_kind"),
            "status": result.get("status"),
            "finish_reason": result.get("finish_reason"),
        },
        "artifact_manifest": {
            "status": artifact_manifest.get("status"),
            "output_ref_count": len(output_refs),
            "review_only": artifact_manifest.get("review_only"),
        },
        "activation_gate": {
            "activation_allowed": activation.get("activation_allowed"),
            "blocked_reason": activation.get("blocked_reason"),
            "required_next_gates": activation.get("required_next_gates", []),
        },
    }


def _infer_executor_result_kind(object_kind: Any) -> str:
    lowered = str(object_kind or "").lower()
    if any(token in lowered for token in ("image", "sprite", "visual", "map")):
        return "image_candidate"
    if any(token in lowered for token in ("video", "animation")):
        return "video_candidate"
    if any(token in lowered for token in ("story", "narrative", "quest", "dialogue")):
        return "text_candidate"
    if any(token in lowered for token in ("json", "package", "manifest", "cgop")):
        return "json_candidate"
    return "mixed_candidate"


def _build_generation_executor_run_request_payload(
    queue_payload: dict[str, Any],
    guard_payload: dict[str, Any],
    metadata: dict[str, Any] | None,
    ts: str,
) -> dict[str, Any]:
    safe_metadata = metadata if isinstance(metadata, dict) else {}
    provider_policy = queue_payload.get("provider_policy")
    if not isinstance(provider_policy, dict):
        provider_policy = {}
    attempt_count = int(queue_payload.get("attempt_count", 0))
    max_attempts = int(queue_payload.get("max_attempts", 0))
    latency_class = str(queue_payload.get("latency_class") or "unknown")
    object_kind = str(queue_payload.get("object_kind") or "unknown")
    worker_id = str(safe_metadata.get("worker_id") or "generation_executor_request_preparer")
    return {
        "schema_version": "generation_executor_run_request.v0.1",
        "request_id": _generation_executor_request_id(queue_payload, attempt_count),
        "created_at": ts,
        "source": {
            "session_id": queue_payload.get("session_id"),
            "run_id": queue_payload.get("run_id"),
            "schedule_item_id": queue_payload.get("schedule_item_id"),
            "object_kind": object_kind,
            "object_ref": queue_payload.get("object_ref"),
            "latency_class": latency_class,
            "guard_id": guard_payload.get("guard_id"),
            "worker_id": worker_id,
            "note": safe_metadata.get("note"),
        },
        "authority": {
            "visibility": "internal_evidence",
            "review_only": True,
            "provider_call_allowed_by_request_builder": False,
            "runtime_activation_allowed": False,
            "world_mutation_allowed": False,
            "player_visible": False,
        },
        "provider_execution_intent": {
            "status": "prepared_pending_explicit_authorization",
            "provider_mode": str(
                guard_payload.get("provider_mode")
                or provider_policy.get("mode")
                or "unknown"
            ),
            "provider_profile": str(
                guard_payload.get("provider_profile")
                or provider_policy.get("profile")
                or "unknown"
            ),
            "authorization_required": True,
            "authorization_granted": False,
            "authorization_ref": None,
            "provider_call_performed_by_request_builder": False,
        },
        "execution_budget": {
            "attempt_count": attempt_count,
            "max_attempts": max_attempts,
            "remaining_attempts": max(0, max_attempts - attempt_count),
            "latency_class": latency_class,
            "fallback_ref": queue_payload.get("fallback_ref"),
        },
        "input_refs": [
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
        "context_refs": [
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
        "requested_output": {
            "intent_class": f"prepare_review_only_{object_kind}_candidate",
            "result_kind": _infer_executor_result_kind(object_kind),
            "artifact_policy": "review_only_local_refs_required",
            "activation_policy": "promotion_required_before_runtime_or_world_state",
            "notes": [
                "Future executor must write ProviderOutputEnvelope and local staging refs before promotion."
            ],
        },
        "required_gates": {
            "before_provider_execution": [
                "explicit_user_authorization",
                "provider_adapter_selected",
                "sanitized_prompt_or_request_materialized_outside_request_record",
            ],
            "after_provider_execution": [
                "provider_output_envelope",
                "local_artifact_staging_manifest",
                "schema_or_media_validation",
            ],
            "before_activation": [
                "semantic_gate",
                "human_review",
                "promotion_report",
                "runtime_package_or_world_delta_transaction_builder",
            ],
        },
        "retention_policy": {
            "prompt_body_storage": "forbidden",
            "provider_body_storage": "forbidden",
            "secret_storage": "forbidden",
            "temporary_url_policy": "download_then_local_ref_only",
            "executor_result_storage": "provider_output_envelope_redacted_only",
        },
        "request_builder_safety": {
            "reads_env": False,
            "calls_provider": False,
            "stores_prompt_body": False,
            "stores_provider_body": False,
            "writes_world_state": False,
            "activates_runtime": False,
        },
    }


def _compact_generation_executor_run_request(request: dict[str, Any]) -> dict[str, Any]:
    source = request.get("source", {})
    if not isinstance(source, dict):
        source = {}
    intent = request.get("provider_execution_intent", {})
    if not isinstance(intent, dict):
        intent = {}
    budget = request.get("execution_budget", {})
    if not isinstance(budget, dict):
        budget = {}
    output = request.get("requested_output", {})
    if not isinstance(output, dict):
        output = {}
    gates = request.get("required_gates", {})
    if not isinstance(gates, dict):
        gates = {}
    return {
        "schema_version": request.get("schema_version"),
        "request_id": request.get("request_id"),
        "source": {
            "run_id": source.get("run_id"),
            "schedule_item_id": source.get("schedule_item_id"),
            "object_kind": source.get("object_kind"),
            "object_ref": source.get("object_ref"),
            "latency_class": source.get("latency_class"),
            "guard_id": source.get("guard_id"),
            "worker_id": source.get("worker_id"),
        },
        "provider_execution_intent": {
            "status": intent.get("status"),
            "provider_mode": intent.get("provider_mode"),
            "provider_profile": intent.get("provider_profile"),
            "authorization_required": intent.get("authorization_required"),
            "authorization_granted": intent.get("authorization_granted"),
            "provider_call_performed_by_request_builder": intent.get(
                "provider_call_performed_by_request_builder"
            ),
        },
        "execution_budget": {
            "attempt_count": budget.get("attempt_count"),
            "max_attempts": budget.get("max_attempts"),
            "remaining_attempts": budget.get("remaining_attempts"),
            "fallback_ref": budget.get("fallback_ref"),
        },
        "input_ref_count": len(request.get("input_refs", []))
        if isinstance(request.get("input_refs"), list)
        else 0,
        "context_ref_count": len(request.get("context_refs", []))
        if isinstance(request.get("context_refs"), list)
        else 0,
        "requested_output": {
            "intent_class": output.get("intent_class"),
            "result_kind": output.get("result_kind"),
            "artifact_policy": output.get("artifact_policy"),
            "activation_policy": output.get("activation_policy"),
        },
        "required_gate_counts": {
            "before_provider_execution": len(gates.get("before_provider_execution", []))
            if isinstance(gates.get("before_provider_execution"), list)
            else 0,
            "after_provider_execution": len(gates.get("after_provider_execution", []))
            if isinstance(gates.get("after_provider_execution"), list)
            else 0,
            "before_activation": len(gates.get("before_activation", []))
            if isinstance(gates.get("before_activation"), list)
            else 0,
        },
        "authority": request.get("authority", {}),
        "request_builder_safety": request.get("request_builder_safety", {}),
    }


def _compact_provider_artifact_staging(manifest: dict[str, Any]) -> dict[str, Any]:
    artifacts = manifest.get("staged_artifacts", [])
    if not isinstance(artifacts, list):
        artifacts = []
    validation = manifest.get("validation_results", {})
    if not isinstance(validation, dict):
        validation = {}
    promotion = manifest.get("promotion_gate", {})
    if not isinstance(promotion, dict):
        promotion = {}
    authority = manifest.get("authority", {})
    if not isinstance(authority, dict):
        authority = {}
    return {
        "schema_version": manifest.get("schema_version"),
        "manifest_id": manifest.get("manifest_id"),
        "source_envelope_id": manifest.get("source_envelope_id"),
        "source_envelope_ref": manifest.get("source_envelope_ref"),
        "staging_status": manifest.get("staging_status"),
        "staged_artifact_count": len(artifacts),
        "staged_artifacts": [
            {
                "artifact_id": artifact.get("artifact_id"),
                "source_artifact_id": artifact.get("source_artifact_id"),
                "kind": artifact.get("kind"),
                "path": artifact.get("path"),
                "media_layer": artifact.get("media_layer"),
                "review_status": artifact.get("review_status"),
                "runtime_visible": artifact.get("runtime_visible"),
                "player_visible": artifact.get("player_visible"),
            }
            for artifact in artifacts
            if isinstance(artifact, dict)
        ],
        "gate_statuses": {
            gate_name: gate.get("status")
            for gate_name, gate in validation.items()
            if isinstance(gate, dict)
        },
        "promotion_gate": {
            "promotion_allowed": promotion.get("promotion_allowed"),
            "blocked_reason": promotion.get("blocked_reason"),
            "required_next_gates": promotion.get("required_next_gates", []),
        },
        "authority": {
            "review_only": authority.get("review_only"),
            "runtime_activation_allowed": authority.get("runtime_activation_allowed"),
            "world_mutation_allowed": authority.get("world_mutation_allowed"),
            "player_visible": authority.get("player_visible"),
        },
    }


def _compact_provider_artifact_promotion_report(report: dict[str, Any]) -> dict[str, Any]:
    decision = report.get("decision", {})
    if not isinstance(decision, dict):
        decision = {}
    gates = report.get("gate_results", {})
    if not isinstance(gates, dict):
        gates = {}
    targets = report.get("promotion_targets", {})
    if not isinstance(targets, dict):
        targets = {}
    safety = report.get("safety_summary", {})
    if not isinstance(safety, dict):
        safety = {}
    reviewed = report.get("reviewed_artifacts", [])
    if not isinstance(reviewed, list):
        reviewed = []
    return {
        "schema_version": report.get("schema_version"),
        "report_id": report.get("report_id"),
        "source_staging_id": report.get("source_staging_id"),
        "source_staging_ref": report.get("source_staging_ref"),
        "promotion_decision": decision.get("promotion_decision"),
        "promotion_allowed": decision.get("promotion_allowed"),
        "blocked_reason": decision.get("blocked_reason"),
        "required_next_actions": decision.get("required_next_actions", []),
        "reviewed_artifact_count": len(reviewed),
        "gate_statuses": {
            gate_name: gate.get("status")
            for gate_name, gate in gates.items()
            if isinstance(gate, dict)
        },
        "promotion_targets": {
            "target_kind": targets.get("target_kind"),
            "runtime_package_ref_count": len(
                targets.get("runtime_package_refs", [])
                if isinstance(targets.get("runtime_package_refs"), list)
                else []
            ),
            "world_transaction_ref_count": len(
                targets.get("world_transaction_refs", [])
                if isinstance(targets.get("world_transaction_refs"), list)
                else []
            ),
            "published_media_ref_count": len(
                targets.get("published_media_refs", [])
                if isinstance(targets.get("published_media_refs"), list)
                else []
            ),
        },
        "safety_summary": {
            "provider_call_count_by_report": safety.get("provider_call_count_by_report"),
            "world_mutation_count_by_report": safety.get("world_mutation_count_by_report"),
            "runtime_mutation_count_by_report": safety.get(
                "runtime_mutation_count_by_report"
            ),
            "stores_prompt_body": safety.get("stores_prompt_body"),
            "stores_provider_body": safety.get("stores_provider_body"),
            "stores_sensitive_value": safety.get("stores_secret"),
            "uses_temporary_url": safety.get("uses_temporary_url"),
        },
    }


def _build_artifact_ledger_payload(
    *,
    session_id: str,
    artifact_kind: str,
    source_id: str,
    status: str,
    compact: dict[str, Any],
    ts: str,
    latest_run: dict[str, Any] | None,
    schedule_item_id: str | None,
    worker_id: str,
    note: str | None,
) -> dict[str, Any]:
    run_id = str(latest_run.get("run_id")) if latest_run is not None else None
    return {
        "schema_version": "generation_artifact_ledger_entry.v0.1",
        "ledger_id": f"gled_{session_id}_{artifact_kind}_{source_id}",
        "session_id": session_id,
        "run_id": run_id,
        "schedule_item_id": schedule_item_id,
        "artifact_kind": artifact_kind,
        "source_id": source_id,
        "status": status,
        "worker_id": worker_id,
        "note": note,
        "created_at": ts,
        "updated_at": ts,
        "provider_call_performed_by_this_request": False,
        "world_mutation_performed_by_this_request": False,
        "activation_allowed_now": False,
        "ledger_write_policy": {
            "mode": "fixture_backed_review_only",
            "reads_env": False,
            "calls_provider": False,
            "stores_raw_prompt": False,
            "stores_provider_response": False,
            "writes_world_state": False,
        },
        "compact": compact,
    }


def _upsert_generation_artifact_ledger(payload: dict[str, Any]) -> None:
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


def _load_generation_artifact_ledger_items(
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


def _artifact_ledger_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    kind_counts = Counter(str(item.get("artifact_kind", "unknown")) for item in items)
    status_counts = Counter(str(item.get("status", "unknown")) for item in items)
    recorded_provider_call_count = 0
    promotion_allowed_count = 0
    activation_allowed_count = 0
    for item in items:
        compact = item.get("compact", {})
        if not isinstance(compact, dict):
            continue
        provider_call = compact.get("provider_call", {})
        if isinstance(provider_call, dict) and provider_call.get("performed") is True:
            recorded_provider_call_count += 1
        if compact.get("promotion_allowed") is True:
            promotion_allowed_count += 1
        promotion_gate = compact.get("promotion_gate", {})
        if isinstance(promotion_gate, dict) and promotion_gate.get("promotion_allowed") is True:
            promotion_allowed_count += 1
        activation_gate = compact.get("activation_gate", {})
        if isinstance(activation_gate, dict) and activation_gate.get("activation_allowed") is True:
            activation_allowed_count += 1
    return {
        "item_count": len(items),
        "artifact_kind_counts": dict(sorted(kind_counts.items())),
        "status_counts": dict(sorted(status_counts.items())),
        "recorded_provider_call_count": recorded_provider_call_count,
        "provider_call_count_by_this_request": 0,
        "world_mutation_count_by_this_request": 0,
        "activation_allowed_count": activation_allowed_count,
        "promotion_allowed_count": promotion_allowed_count,
    }


def _compact_generation_artifact_ledger(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "summary": _artifact_ledger_summary(items),
        "items": [
            {
                "ledger_id": item.get("ledger_id"),
                "run_id": item.get("run_id"),
                "schedule_item_id": item.get("schedule_item_id"),
                "artifact_kind": item.get("artifact_kind"),
                "source_id": item.get("source_id"),
                "status": item.get("status"),
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
                "provider_call_performed_by_this_request": item.get(
                    "provider_call_performed_by_this_request"
                ),
                "world_mutation_performed_by_this_request": item.get(
                    "world_mutation_performed_by_this_request"
                ),
                "activation_allowed_now": item.get("activation_allowed_now"),
                "compact": item.get("compact"),
            }
            for item in items
        ],
    }


def _latest_generation_executor_request_ledger_entry(
    session_id: str,
    run_id: str,
) -> dict[str, Any] | None:
    items = _load_generation_artifact_ledger_items(session_id, run_id)
    executor_requests = [
        item
        for item in items
        if item.get("artifact_kind") == "generation_executor_run_request"
        and item.get("status") == "prepared_pending_explicit_authorization"
    ]
    return executor_requests[-1] if executor_requests else None


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
    row = _load_next_generation_item_row_by_status(session_id, "waiting_review")
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
    with db_cursor() as cur:
        cur.execute(
            "UPDATE generation_schedule_queue_items "
            "SET payload = ?, updated_at = ? WHERE id = ?",
            (_dump_payload(payload), ts, row["id"]),
        )
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
    row = _load_next_generation_item_row_by_status(session_id, "waiting_review")
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
    with db_cursor() as cur:
        cur.execute(
            "UPDATE generation_schedule_queue_items "
            "SET payload = ?, updated_at = ? WHERE id = ?",
            (_dump_payload(payload), ts, row["id"]),
        )
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
    row = _load_next_queued_generation_item_row(session_id)
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
    with db_cursor() as cur:
        cur.execute(
            "UPDATE generation_schedule_queue_items "
            "SET status = ?, payload = ?, updated_at = ? WHERE id = ?",
            (next_status, _dump_payload(payload), ts, row["id"]),
        )
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
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO generation_schedule_runs "
            "(run_id, session_id, status, payload, created_at, updated_at, completed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                session_id,
                payload["status"],
                _dump_payload(payload),
                ts,
                ts,
                ts,
            ),
        )
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


def stage_provider_artifacts_fixture(
    session_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ts = now_iso()
    safe_metadata = metadata if isinstance(metadata, dict) else {}
    worker_id = safe_metadata.get("worker_id") or "provider_artifact_fixture_stager"
    note = safe_metadata.get("note")
    latest_run = _load_latest_generation_schedule_run(session_id)
    if latest_run is None:
        raise InvalidQueueTransitionError(
            "generation schedule run is required before staging provider artifacts"
        )
    run_id = str(latest_run.get("run_id"))
    executor_request_entry = _latest_generation_executor_request_ledger_entry(
        session_id,
        run_id,
    )
    if executor_request_entry is None:
        raise InvalidQueueTransitionError(
            "generation executor request is required before staging provider artifacts"
        )
    envelope = _load_json(_PROVIDER_OUTPUT_ENVELOPE_EXAMPLE)
    staging = _load_json(_PROVIDER_ARTIFACT_STAGING_EXAMPLE)
    promotion = _load_json(_PROVIDER_ARTIFACT_PROMOTION_REPORT_EXAMPLE)
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
        },
        "generation_executor_run_request": executor_request_entry.get("compact"),
        "provider_output_envelope": envelope_entry["compact"],
        "provider_artifact_staging": staging_entry["compact"],
        "provider_artifact_promotion_report": promotion_entry["compact"],
        "generation_artifact_ledger": _compact_generation_artifact_ledger(items),
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
