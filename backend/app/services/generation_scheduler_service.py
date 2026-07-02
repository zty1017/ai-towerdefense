"""Fixture-backed Generation Scheduler service.

This module owns the MVP scheduler control-plane state: review-only schedule
plans, dry-run reports, per-session dry-run records, item queues, transitions,
retry/fallback guards, and the local dry worker step. It deliberately does not
call providers, read `.env`, mutate world state, or activate generated content.
"""

from __future__ import annotations

import json
import secrets
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
            (session_id, run_id, "queued"),
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
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "generation_schedule_run": run,
        "generation_schedule_queue": _compact_generation_queue(queue_items),
    }


def get_generation_schedule_queue(session_id: str) -> dict[str, Any]:
    run = _load_latest_generation_schedule_run(session_id)
    queue_items = _load_generation_queue_items(session_id) if run is not None else []
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "generation_schedule_run": _compact_generation_schedule_run(run),
        "generation_schedule_queue": _compact_generation_queue(queue_items),
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
    }


def get_generation_scheduler_evidence(session_id: str) -> dict[str, Any]:
    plan = _load_generation_schedule_plan()
    run_report = _load_generation_schedule_run_report()
    latest_run = _load_latest_generation_schedule_run(session_id)
    latest_queue = _load_generation_queue_items(session_id) if latest_run is not None else []
    return {
        "refs": _generation_schedule_refs(),
        "buffer": _build_generation_schedule_buffer(plan, run_report),
        "latest_run": _compact_generation_schedule_run(latest_run),
        "latest_queue": _compact_generation_queue(latest_queue),
    }
