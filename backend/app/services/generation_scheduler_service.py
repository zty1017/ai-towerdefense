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
_PROVIDER_IMAGE_OUTPUT_ENVELOPE_EXAMPLE = (
    _REPO_ROOT
    / "examples/provider_artifact_staging/p1b_provider_image_artifact_staging.source_envelope.json"
)
_PROVIDER_IMAGE_ARTIFACT_STAGING_EXAMPLE = (
    _REPO_ROOT
    / "examples/provider_artifact_staging/p1b_provider_image_artifact_staging.example.json"
)
_PROVIDER_IMAGE_ARTIFACT_PROMOTION_REPORT_EXAMPLE = (
    _REPO_ROOT
    / "examples/provider_artifact_staging/p1b_provider_image_artifact_promotion_report.example.json"
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


class GenerationSchedulerFixtureNotFoundError(LookupError):
    """Raised when scheduler fixture/session state is missing."""


class InvalidQueueTransitionError(ValueError):
    """Raised when a scheduler queue transition violates the current state."""


_FORBIDDEN_IMPORT_KEYS = {
    "api_key",
    "secret",
    "token",
    "raw_prompt",
    "full_trace",
    "raw_json",
    "provider_response",
    "provider_body",
    "prompt_body",
}


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _resolve_import_path(value: Any, *, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise InvalidQueueTransitionError(f"{label} is required")
    path = Path(value.strip())
    if not path.is_absolute():
        path = _REPO_ROOT / path
    resolved = path.resolve()
    if ".env" in resolved.parts:
        raise InvalidQueueTransitionError(f"{label} must not reference .env")
    allowed_roots = (_REPO_ROOT.resolve(), Path("/tmp").resolve())
    if not any(resolved == root or root in resolved.parents for root in allowed_roots):
        raise InvalidQueueTransitionError(
            f"{label} must be under repository root or /tmp"
        )
    if not resolved.is_file():
        raise InvalidQueueTransitionError(f"{label} file not found: {value}")
    return resolved


def _find_forbidden_import_keys(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if str(key).lower() in _FORBIDDEN_IMPORT_KEYS:
                found.append(child_path)
            found.extend(_find_forbidden_import_keys(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_find_forbidden_import_keys(child, f"{path}[{index}]"))
    return found


def _load_runner_import_json(path: Path, *, label: str) -> dict[str, Any]:
    payload = _load_json(path)
    if not isinstance(payload, dict):
        raise InvalidQueueTransitionError(f"{label} must be a JSON object")
    forbidden = _find_forbidden_import_keys(payload)
    if forbidden:
        raise InvalidQueueTransitionError(
            f"{label} contains forbidden sensitive keys: {', '.join(forbidden[:5])}"
        )
    return payload


def _provider_artifact_fixture_paths(profile: str | None) -> tuple[Path, Path, Path, str]:
    if profile in {None, "", "default", "summary"}:
        return (
            _PROVIDER_OUTPUT_ENVELOPE_EXAMPLE,
            _PROVIDER_ARTIFACT_STAGING_EXAMPLE,
            _PROVIDER_ARTIFACT_PROMOTION_REPORT_EXAMPLE,
            "default",
        )
    if profile in {"image_failure", "image"}:
        return (
            _PROVIDER_IMAGE_OUTPUT_ENVELOPE_EXAMPLE,
            _PROVIDER_IMAGE_ARTIFACT_STAGING_EXAMPLE,
            _PROVIDER_IMAGE_ARTIFACT_PROMOTION_REPORT_EXAMPLE,
            "image_failure",
        )
    raise InvalidQueueTransitionError(f"unknown provider artifact profile: {profile}")


def _provider_artifact_fixture_metadata(
    profile: str | None,
) -> dict[str, str]:
    envelope_path, _, _, normalized_profile = _provider_artifact_fixture_paths(profile)
    envelope = _load_json(envelope_path)
    source = envelope.get("source", {}) if isinstance(envelope.get("source"), dict) else {}
    provider_call = (
        envelope.get("provider_call", {})
        if isinstance(envelope.get("provider_call"), dict)
        else {}
    )
    schedule_item_id = str(source.get("schedule_item_id") or "")
    authorization_ref = str(provider_call.get("authorization_ref") or "")
    if not schedule_item_id or not authorization_ref:
        raise InvalidQueueTransitionError(
            f"provider artifact fixture profile is missing source refs: {normalized_profile}"
        )
    return {
        "artifact_profile": normalized_profile,
        "schedule_item_id": schedule_item_id,
        "authorization_ref": authorization_ref,
        "provider_output_envelope": _rel(envelope_path),
    }


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


def _requested_schedule_item_id(metadata: dict[str, Any] | None) -> str | None:
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("schedule_item_id")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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


def _provider_guard_id(payload: dict[str, Any], attempt_count: int) -> str:
    run_id = str(payload.get("run_id") or "")
    schedule_item_id = str(payload.get("schedule_item_id") or "")
    safe_item_id = _safe_id_fragment(schedule_item_id)
    return f"pguard_{run_id}_{safe_item_id}_{attempt_count:02d}"


def _generation_executor_request_id(payload: dict[str, Any], attempt_count: int) -> str:
    run_id = str(payload.get("run_id") or "")
    schedule_item_id = str(payload.get("schedule_item_id") or "")
    return f"gexec_{run_id}_{_safe_id_fragment(schedule_item_id)}_{attempt_count:02d}"


def _provider_authorization_ref(schedule_item_id: str) -> str:
    return f"auth_{_safe_id_fragment(schedule_item_id)}_fixture_001"


def _provider_adapter_execution_receipt_id(schedule_item_id: str) -> str:
    return f"padapter_{_safe_id_fragment(schedule_item_id)}_fixture_001"


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
            "authorization_ref": provider_call.get("authorization_ref"),
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


def _build_provider_execution_authorization_payload(
    executor_request_entry: dict[str, Any],
    metadata: dict[str, Any] | None,
    ts: str,
) -> dict[str, Any]:
    safe_metadata = metadata if isinstance(metadata, dict) else {}
    request_compact = executor_request_entry.get("compact")
    if not isinstance(request_compact, dict):
        request_compact = {}
    request_source = request_compact.get("source")
    if not isinstance(request_source, dict):
        request_source = {}
    intent = request_compact.get("provider_execution_intent")
    if not isinstance(intent, dict):
        intent = {}
    budget = request_compact.get("execution_budget")
    if not isinstance(budget, dict):
        budget = {}
    schedule_item_id = str(
        executor_request_entry.get("schedule_item_id")
        or request_source.get("schedule_item_id")
        or ""
    )
    authorization_ref = str(
        safe_metadata.get("authorization_ref")
        or _provider_authorization_ref(schedule_item_id)
    )
    provider_mode = str(intent.get("provider_mode") or "unknown")
    provider_profile = str(intent.get("provider_profile") or "unknown")
    return {
        "schema_version": "provider_execution_authorization.v0.1",
        "authorization_ref": authorization_ref,
        "created_at": ts,
        "source": {
            "session_id": executor_request_entry.get("session_id"),
            "run_id": executor_request_entry.get("run_id"),
            "schedule_item_id": schedule_item_id,
            "object_kind": request_source.get("object_kind"),
            "object_ref": request_source.get("object_ref"),
            "executor_request_id": executor_request_entry.get("source_id"),
            "guard_id": request_source.get("guard_id"),
            "provider_mode": provider_mode,
            "provider_profile": provider_profile,
            "worker_id": safe_metadata.get("worker_id")
            or "provider_authorization_grant",
            "note": safe_metadata.get("note"),
        },
        "authority": {
            "visibility": "internal_evidence",
            "review_only": True,
            "provider_execution_authorized": True,
            "runtime_activation_allowed": False,
            "world_mutation_allowed": False,
            "player_visible": False,
        },
        "authorization": {
            "status": "granted_for_provider_adapter",
            "granted": True,
            "scope": "provider_adapter_execution_only",
            "requires_provider_output_envelope": True,
            "expires_at": None,
            "reason": safe_metadata.get("note")
            or "explicit_authorization_recorded_for_guarded_provider_adapter",
        },
        "execution_constraints": {
            "attempt_count": int(budget.get("attempt_count", 0)),
            "max_attempts": int(budget.get("max_attempts", 0)),
            "remaining_attempts": int(budget.get("remaining_attempts", 0)),
            "allowed_provider_mode": provider_mode,
            "allowed_provider_profile": provider_profile,
            "required_next_gates": [
                "provider_output_envelope",
                "local_artifact_staging_manifest",
                "media_gate",
                "semantic_gate",
                "human_review",
                "promotion_report",
            ],
        },
        "retention_policy": {
            "prompt_body_storage": "forbidden",
            "provider_body_storage": "forbidden",
            "secret_storage": "forbidden",
            "temporary_url_policy": "download_then_local_ref_only",
            "executor_result_storage": "provider_output_envelope_redacted_only",
        },
        "authorization_builder_safety": {
            "reads_env": False,
            "calls_provider": False,
            "stores_prompt_body": False,
            "stores_provider_body": False,
            "writes_world_state": False,
            "activates_runtime": False,
        },
    }


def _compact_provider_execution_authorization(record: dict[str, Any]) -> dict[str, Any]:
    source = record.get("source")
    if not isinstance(source, dict):
        source = {}
    authorization = record.get("authorization")
    if not isinstance(authorization, dict):
        authorization = {}
    constraints = record.get("execution_constraints")
    if not isinstance(constraints, dict):
        constraints = {}
    return {
        "schema_version": record.get("schema_version"),
        "authorization_ref": record.get("authorization_ref"),
        "source": {
            "run_id": source.get("run_id"),
            "schedule_item_id": source.get("schedule_item_id"),
            "object_kind": source.get("object_kind"),
            "object_ref": source.get("object_ref"),
            "executor_request_id": source.get("executor_request_id"),
            "guard_id": source.get("guard_id"),
            "provider_mode": source.get("provider_mode"),
            "provider_profile": source.get("provider_profile"),
            "worker_id": source.get("worker_id"),
        },
        "authorization": {
            "status": authorization.get("status"),
            "granted": authorization.get("granted"),
            "scope": authorization.get("scope"),
            "requires_provider_output_envelope": authorization.get(
                "requires_provider_output_envelope"
            ),
        },
        "execution_constraints": {
            "attempt_count": constraints.get("attempt_count"),
            "max_attempts": constraints.get("max_attempts"),
            "remaining_attempts": constraints.get("remaining_attempts"),
            "allowed_provider_mode": constraints.get("allowed_provider_mode"),
            "allowed_provider_profile": constraints.get("allowed_provider_profile"),
            "required_next_gates": constraints.get("required_next_gates", []),
        },
        "authority": record.get("authority", {}),
        "authorization_builder_safety": record.get("authorization_builder_safety", {}),
    }


def _rehydrate_generation_executor_request_for_runner(
    entry: dict[str, Any],
) -> dict[str, Any]:
    compact = entry.get("compact") if isinstance(entry.get("compact"), dict) else {}
    source = compact.get("source") if isinstance(compact.get("source"), dict) else {}
    intent = (
        compact.get("provider_execution_intent")
        if isinstance(compact.get("provider_execution_intent"), dict)
        else {}
    )
    budget = (
        compact.get("execution_budget")
        if isinstance(compact.get("execution_budget"), dict)
        else {}
    )
    output = (
        compact.get("requested_output")
        if isinstance(compact.get("requested_output"), dict)
        else {}
    )
    latency_class = str(source.get("latency_class") or "background_prefetch")
    return {
        "schema_version": "generation_executor_run_request.v0.1",
        "request_id": str(entry.get("source_id") or compact.get("request_id") or ""),
        "created_at": str(entry.get("created_at") or entry.get("updated_at") or now_iso()),
        "source": {
            "session_id": str(entry.get("session_id") or ""),
            "run_id": str(entry.get("run_id") or source.get("run_id") or ""),
            "schedule_item_id": str(
                entry.get("schedule_item_id")
                or source.get("schedule_item_id")
                or ""
            ),
            "object_kind": str(source.get("object_kind") or ""),
            "object_ref": str(source.get("object_ref") or ""),
            "latency_class": latency_class,
            "guard_id": str(source.get("guard_id") or ""),
            "worker_id": str(source.get("worker_id") or "generation_executor_request"),
        },
        "authority": compact.get("authority")
        if isinstance(compact.get("authority"), dict)
        else {
            "visibility": "internal_evidence",
            "review_only": True,
            "provider_call_allowed_by_request_builder": False,
            "runtime_activation_allowed": False,
            "world_mutation_allowed": False,
            "player_visible": False,
        },
        "provider_execution_intent": {
            "status": str(
                intent.get("status") or "prepared_pending_explicit_authorization"
            ),
            "provider_mode": str(intent.get("provider_mode") or "manual_authorized_demo"),
            "provider_profile": str(intent.get("provider_profile") or "unknown"),
            "authorization_required": True,
            "authorization_granted": False,
            "authorization_ref": None,
            "provider_call_performed_by_request_builder": False,
        },
        "execution_budget": {
            "attempt_count": int(budget.get("attempt_count", 0)),
            "max_attempts": int(budget.get("max_attempts", 0)),
            "remaining_attempts": int(budget.get("remaining_attempts", 0)),
            "latency_class": latency_class,
            "fallback_ref": budget.get("fallback_ref"),
        },
        "input_refs": [
            {
                "ref_id": "generation_schedule_plan",
                "kind": "schedule_plan",
                "path": _rel(_GENERATION_SCHEDULE_PLAN),
                "notes": [
                    "Rehydrated from ledger compact for provider adapter runner dry-run; no prompt body is stored."
                ],
            }
        ],
        "context_refs": [],
        "requested_output": {
            "intent_class": str(
                output.get("intent_class") or "provider_adapter_runner_dry_run"
            ),
            "result_kind": str(output.get("result_kind") or "mixed_candidate"),
            "artifact_policy": "review_only_local_refs_required",
            "activation_policy": "promotion_required_before_runtime_or_world_state",
            "notes": [
                "Provider adapter runner must emit ProviderOutputEnvelope before staging."
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
        "request_builder_safety": compact.get("request_builder_safety")
        if isinstance(compact.get("request_builder_safety"), dict)
        else {
            "reads_env": False,
            "calls_provider": False,
            "stores_prompt_body": False,
            "stores_provider_body": False,
            "writes_world_state": False,
            "activates_runtime": False,
        },
    }


def _rehydrate_provider_authorization_for_runner(
    entry: dict[str, Any],
) -> dict[str, Any]:
    compact = entry.get("compact") if isinstance(entry.get("compact"), dict) else {}
    source = compact.get("source") if isinstance(compact.get("source"), dict) else {}
    authorization = (
        compact.get("authorization")
        if isinstance(compact.get("authorization"), dict)
        else {}
    )
    constraints = (
        compact.get("execution_constraints")
        if isinstance(compact.get("execution_constraints"), dict)
        else {}
    )
    return {
        "schema_version": "provider_execution_authorization.v0.1",
        "authorization_ref": str(
            entry.get("source_id")
            or compact.get("authorization_ref")
            or source.get("authorization_ref")
            or ""
        ),
        "created_at": str(entry.get("created_at") or entry.get("updated_at") or now_iso()),
        "source": {
            "session_id": str(entry.get("session_id") or ""),
            "run_id": str(entry.get("run_id") or source.get("run_id") or ""),
            "schedule_item_id": str(
                entry.get("schedule_item_id")
                or source.get("schedule_item_id")
                or ""
            ),
            "object_kind": str(source.get("object_kind") or ""),
            "object_ref": str(source.get("object_ref") or ""),
            "executor_request_id": str(source.get("executor_request_id") or ""),
            "guard_id": str(source.get("guard_id") or ""),
            "provider_mode": str(source.get("provider_mode") or "manual_authorized_demo"),
            "provider_profile": str(source.get("provider_profile") or "unknown"),
            "worker_id": str(source.get("worker_id") or "provider_authorization_grant"),
        },
        "authority": compact.get("authority")
        if isinstance(compact.get("authority"), dict)
        else {
            "visibility": "internal_evidence",
            "review_only": True,
            "provider_execution_authorized": True,
            "runtime_activation_allowed": False,
            "world_mutation_allowed": False,
            "player_visible": False,
        },
        "authorization": {
            "status": str(authorization.get("status") or "granted_for_provider_adapter"),
            "granted": True,
            "scope": "provider_adapter_execution_only",
            "requires_provider_output_envelope": True,
            "expires_at": None,
            "reason": "Rehydrated authorization for provider adapter runner dry-run.",
        },
        "execution_constraints": {
            "attempt_count": int(constraints.get("attempt_count", 0)),
            "max_attempts": int(constraints.get("max_attempts", 0)),
            "remaining_attempts": int(constraints.get("remaining_attempts", 0)),
            "allowed_provider_mode": str(
                constraints.get("allowed_provider_mode")
                or source.get("provider_mode")
                or "manual_authorized_demo"
            ),
            "allowed_provider_profile": str(
                constraints.get("allowed_provider_profile")
                or source.get("provider_profile")
                or "unknown"
            ),
            "required_next_gates": constraints.get("required_next_gates")
            if isinstance(constraints.get("required_next_gates"), list)
            else [
                "provider_output_envelope",
                "local_artifact_staging_manifest",
                "media_gate",
                "semantic_gate",
                "human_review",
                "promotion_report",
            ],
        },
        "retention_policy": {
            "prompt_body_storage": "forbidden",
            "provider_body_storage": "forbidden",
            "secret_storage": "forbidden",
            "temporary_url_policy": "download_then_local_ref_only",
            "executor_result_storage": "provider_output_envelope_redacted_only",
        },
        "authorization_builder_safety": compact.get("authorization_builder_safety")
        if isinstance(compact.get("authorization_builder_safety"), dict)
        else {
            "reads_env": False,
            "calls_provider": False,
            "stores_prompt_body": False,
            "stores_provider_body": False,
            "writes_world_state": False,
            "activates_runtime": False,
        },
    }


def _build_provider_adapter_execution_receipt_payload(
    authorization_entry: dict[str, Any],
    metadata: dict[str, Any] | None,
    ts: str,
) -> dict[str, Any]:
    safe_metadata = metadata if isinstance(metadata, dict) else {}
    authorization_compact = authorization_entry.get("compact")
    if not isinstance(authorization_compact, dict):
        authorization_compact = {}
    source = authorization_compact.get("source")
    if not isinstance(source, dict):
        source = {}
    constraints = authorization_compact.get("execution_constraints")
    if not isinstance(constraints, dict):
        constraints = {}
    schedule_item_id = str(
        authorization_entry.get("schedule_item_id")
        or source.get("schedule_item_id")
        or ""
    )
    authorization_ref = str(
        authorization_entry.get("source_id")
        or authorization_compact.get("authorization_ref")
        or source.get("authorization_ref")
        or ""
    )
    return {
        "schema_version": "provider_adapter_execution_receipt.v0.1",
        "execution_receipt_id": _provider_adapter_execution_receipt_id(
            schedule_item_id
        ),
        "created_at": ts,
        "source": {
            "session_id": authorization_entry.get("session_id"),
            "run_id": authorization_entry.get("run_id"),
            "schedule_item_id": schedule_item_id,
            "object_kind": source.get("object_kind"),
            "object_ref": source.get("object_ref"),
            "executor_request_id": source.get("executor_request_id"),
            "authorization_ref": authorization_ref,
            "guard_id": source.get("guard_id"),
            "provider_mode": source.get("provider_mode"),
            "provider_profile": source.get("provider_profile"),
            "worker_id": safe_metadata.get("worker_id")
            or "provider_adapter_fixture_runner",
            "note": safe_metadata.get("note"),
        },
        "authority": {
            "visibility": "internal_evidence",
            "review_only": True,
            "provider_adapter_boundary_entered": True,
            "runtime_activation_allowed": False,
            "world_mutation_allowed": False,
            "player_visible": False,
        },
        "execution": {
            "status": "fixture_output_ready_for_envelope",
            "mode": "fixture_backed_no_provider_call",
            "authorization_ref": authorization_ref,
            "provider_call_performed_by_receipt_builder": False,
            "requires_provider_output_envelope": True,
            "request_digest": None,
            "result_digest": None,
            "finish_reason": "fixture_ready",
            "redacted_summary": (
                "A review-only fixture has crossed the provider adapter boundary; "
                "the backend worker did not call a provider or retain prompt/provider bodies."
            ),
        },
        "output_contract": {
            "must_write_provider_output_envelope": True,
            "allowed_result_storage": "provider_output_envelope_redacted_only",
            "temporary_url_policy": "download_then_local_ref_only",
            "required_next_gates": [
                "provider_output_envelope",
                "local_artifact_staging_manifest",
                "schema_or_media_validation",
                "semantic_gate",
                "human_review",
                "promotion_report",
            ],
        },
        "retention_policy": {
            "prompt_body_storage": "forbidden",
            "provider_body_storage": "forbidden",
            "secret_storage": "forbidden",
            "temporary_url_policy": "download_then_local_ref_only",
            "executor_result_storage": "provider_output_envelope_redacted_only",
        },
        "adapter_safety": {
            "reads_env": False,
            "calls_provider": False,
            "stores_prompt_body": False,
            "stores_provider_body": False,
            "writes_world_state": False,
            "activates_runtime": False,
        },
    }


def _compact_provider_adapter_execution_receipt(record: dict[str, Any]) -> dict[str, Any]:
    source = record.get("source")
    if not isinstance(source, dict):
        source = {}
    execution = record.get("execution")
    if not isinstance(execution, dict):
        execution = {}
    contract = record.get("output_contract")
    if not isinstance(contract, dict):
        contract = {}
    return {
        "schema_version": record.get("schema_version"),
        "execution_receipt_id": record.get("execution_receipt_id"),
        "source": {
            "run_id": source.get("run_id"),
            "schedule_item_id": source.get("schedule_item_id"),
            "object_kind": source.get("object_kind"),
            "object_ref": source.get("object_ref"),
            "executor_request_id": source.get("executor_request_id"),
            "authorization_ref": source.get("authorization_ref"),
            "guard_id": source.get("guard_id"),
            "provider_mode": source.get("provider_mode"),
            "provider_profile": source.get("provider_profile"),
            "worker_id": source.get("worker_id"),
        },
        "execution": {
            "status": execution.get("status"),
            "mode": execution.get("mode"),
            "authorization_ref": execution.get("authorization_ref"),
            "provider_call_performed_by_receipt_builder": execution.get(
                "provider_call_performed_by_receipt_builder"
            ),
            "requires_provider_output_envelope": execution.get(
                "requires_provider_output_envelope"
            ),
            "finish_reason": execution.get("finish_reason"),
        },
        "output_contract": {
            "must_write_provider_output_envelope": contract.get(
                "must_write_provider_output_envelope"
            ),
            "allowed_result_storage": contract.get("allowed_result_storage"),
            "temporary_url_policy": contract.get("temporary_url_policy"),
            "required_next_gates": contract.get("required_next_gates", []),
        },
        "authority": record.get("authority", {}),
        "adapter_safety": record.get("adapter_safety", {}),
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
    schedule_item_id: str | None = None,
) -> dict[str, Any] | None:
    items = _load_generation_artifact_ledger_items(session_id, run_id)
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


def _latest_provider_authorization_ledger_entry(
    session_id: str,
    run_id: str,
    schedule_item_id: str,
    authorization_ref: str,
) -> dict[str, Any] | None:
    items = _load_generation_artifact_ledger_items(session_id, run_id)
    authorizations = [
        item
        for item in items
        if item.get("artifact_kind") == "provider_execution_authorization"
        and item.get("status") == "granted_for_provider_adapter"
        and str(item.get("schedule_item_id")) == str(schedule_item_id)
        and str(item.get("source_id")) == str(authorization_ref)
    ]
    return authorizations[-1] if authorizations else None


def _latest_provider_adapter_execution_ledger_entry(
    session_id: str,
    run_id: str,
    schedule_item_id: str,
    authorization_ref: str,
) -> dict[str, Any] | None:
    items = _load_generation_artifact_ledger_items(session_id, run_id)
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


def _latest_provider_output_envelope_ledger_entry(
    session_id: str,
    run_id: str,
    schedule_item_id: str,
    envelope_id: str,
) -> dict[str, Any] | None:
    items = _load_generation_artifact_ledger_items(session_id, run_id)
    envelopes = [
        item
        for item in items
        if item.get("artifact_kind") == "provider_output_envelope"
        and str(item.get("schedule_item_id")) == str(schedule_item_id)
        and str(item.get("source_id")) == str(envelope_id)
    ]
    return envelopes[-1] if envelopes else None


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


def _safe_runner_handoff_slug(*parts: str) -> str:
    raw = "_".join(part for part in parts if part)
    slug = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in raw)
    return slug[:120] or "provider_runner_handoff"


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
    slug = _safe_runner_handoff_slug(schedule_item_id, authorization_ref)
    paths = {
        "executor_request_path": f"/tmp/{slug}.executor_request.json",
        "authorization_path": f"/tmp/{slug}.authorization.json",
        "receipt_output_path": f"/tmp/{slug}.receipt.json",
        "envelope_output_path": f"/tmp/{slug}.envelope.json",
        "llm_summary_artifact_path": f"/tmp/{slug}.redacted_text_summary.json",
        "image_artifact_path": f"/tmp/{slug}.image_candidate.png",
        "prompt_file_path": f"/tmp/{slug}.prompt.txt",
    }
    provider_profile = str(
        authorization.get("source", {}).get("provider_profile") or "unknown"
    )
    safe_note = safe_metadata.get("note")
    base_args = [
        "python3",
        "tools/provider_adapter/run_provider_adapter.py",
        "--executor-request",
        paths["executor_request_path"],
        "--authorization",
        paths["authorization_path"],
        "--receipt-output",
        paths["receipt_output_path"],
        "--envelope-output",
        paths["envelope_output_path"],
        "--created-at",
        ts,
    ]
    if safe_note:
        base_args.extend(["--note", str(safe_note)])
    dry_run_args = [*base_args, "--mode", "fixture"]
    live_llm_args = [
        *base_args,
        "--mode",
        "llm_text",
        "--live",
        "--llm-profile",
        provider_profile if provider_profile != "unknown" else "<llm-profile>",
        "--prompt-file",
        paths["prompt_file_path"],
        "--artifact-output",
        paths["llm_summary_artifact_path"],
        "--max-tokens",
        "4096",
        "--load-dotenv",
        "<authorized-dotenv-path>",
    ]
    live_image_args = [
        *base_args,
        "--mode",
        "image",
        "--live",
        "--image-profile",
        provider_profile if provider_profile != "unknown" else "<image-profile>",
        "--prompt-file",
        paths["prompt_file_path"],
        "--artifact-output",
        paths["image_artifact_path"],
        "--size",
        "1024x1024",
        "--load-dotenv",
        "<authorized-dotenv-path>",
    ]
    ledger_items = _load_generation_artifact_ledger_items(session_id, run_id)
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
        "provider_adapter_runner_handoff": {
            "schema_version": "provider_adapter_runner_handoff.v0.1",
            "created_at": ts,
            "handoff_mode": "external_runner_required",
            "review_only": True,
            "source": {
                "session_id": session_id,
                "run_id": run_id,
                "schedule_item_id": schedule_item_id,
                "authorization_ref": authorization_ref,
                "executor_request_id": executor_request_entry.get("source_id"),
                "provider_profile": provider_profile,
            },
            "runner_inputs": {
                "executor_request": executor_request,
                "provider_execution_authorization": authorization,
            },
            "suggested_paths": paths,
            "command_templates": {
                "dry_run_fixture": dry_run_args,
                "live_llm_text": live_llm_args,
                "live_image": live_image_args,
            },
            "import_after_runner": {
                "endpoint": (
                    f"/api/sessions/{session_id}/generation-schedule/workers/"
                    "import-provider-adapter-runner-output"
                ),
                "method": "POST",
                "body": {
                    "worker_id": "provider-runner-output-import",
                    "schedule_item_id": schedule_item_id,
                    "authorization_ref": authorization_ref,
                    "receipt_path": paths["receipt_output_path"],
                    "envelope_path": paths["envelope_output_path"],
                },
            },
            "safety": {
                "api_reads_env": False,
                "api_calls_provider": False,
                "api_writes_world_state": False,
                "api_activates_runtime": False,
                "prompt_body_included": False,
                "provider_response_body_included": False,
                "live_templates_require_external_explicit_authorization": True,
            },
        },
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


def _display_import_path(path: Path) -> str:
    try:
        return _rel(path)
    except ValueError:
        return path.as_posix()


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
