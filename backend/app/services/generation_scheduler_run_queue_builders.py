"""Pure payload builders for Generation Scheduler run, queue, and cache views."""

from __future__ import annotations

from collections import Counter
from typing import Any


def safe_id_fragment(value: Any) -> str:
    return "".join(
        ch if ch.isalnum() or ch in {"_", "-"} else "_"
        for ch in str(value or "")
    )


def build_generation_schedule_buffer(
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


def build_generation_schedule_payload(
    plan: dict[str, Any],
    run_report: dict[str, Any],
    *,
    refs: dict[str, str],
) -> dict[str, Any]:
    return {
        "refs": refs,
        "buffer": build_generation_schedule_buffer(plan, run_report),
        "plan": plan,
        "run_report": run_report,
    }


def build_generation_schedule_run_payload(
    session_id: str,
    run_id: str,
    ts: str,
    *,
    plan: dict[str, Any],
    run_report: dict[str, Any],
    refs: dict[str, str],
) -> dict[str, Any]:
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
            "refs": refs,
            "buffer": build_generation_schedule_buffer(plan, run_report),
        },
        "execution_policy": run_report.get("execution_policy", {}),
        "source_report_summary": run_report.get("summary", {}),
        "notes": [
            "本次运行只复用已审 fixture、静态 fallback 与 dry-run 报告。",
            "本次运行不调用外部模型，不写入世界状态，不激活预生成候选。",
        ],
    }


def generation_queue_status(item: dict[str, Any]) -> str:
    dry_run_status = item.get("dry_run_status")
    if dry_run_status == "passed":
        return "completed"
    if dry_run_status == "fallback":
        return "fallback_ready"
    if dry_run_status == "scheduled":
        return "queued"
    return "blocked"


def build_generation_queue_item_payload(
    session_id: str, run_id: str, item: dict[str, Any], position: int, ts: str
) -> dict[str, Any]:
    status = generation_queue_status(item)
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


def build_generation_queue_items_from_run(
    run_payload: dict[str, Any], ts: str
) -> list[dict[str, Any]]:
    schedule = run_payload.get("generation_schedule", {})
    buffer = schedule.get("buffer", {}) if isinstance(schedule, dict) else {}
    items = buffer.get("items", []) if isinstance(buffer, dict) else []
    if not isinstance(items, list):
        return []
    return [
        build_generation_queue_item_payload(
            str(run_payload["session_id"]),
            str(run_payload["run_id"]),
            item,
            position,
            ts,
        )
        for position, item in enumerate(items, start=1)
        if isinstance(item, dict)
    ]


def generation_queue_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
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


def worker_cache_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
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


def compact_worker_cache(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "summary": worker_cache_summary(items),
        "items": items,
    }


def provider_guard_log_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
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


def compact_provider_guard_logs(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "summary": provider_guard_log_summary(items),
        "items": items,
    }


def compact_generation_schedule_run(
    run: dict[str, Any] | None,
) -> dict[str, Any] | None:
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


def compact_generation_queue(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "summary": generation_queue_summary(items),
        "items": items,
    }


def worker_cache_id(run_id: str, schedule_item_id: str) -> str:
    return f"gcache_{run_id}_{safe_id_fragment(schedule_item_id)}"


def activation_blocked_reason(payload: dict[str, Any]) -> str:
    if payload.get("provider_review_required") is True:
        return "review_required_before_activation"
    if payload.get("revalidate_before_activation") is True:
        return "revalidation_required_before_activation"
    return "fixture_worker_does_not_activate_content"


def build_worker_cache_payload(payload: dict[str, Any], ts: str) -> dict[str, Any]:
    run_id = str(payload.get("run_id") or "")
    session_id = str(payload.get("session_id") or "")
    schedule_item_id = str(payload.get("schedule_item_id") or "")
    review_required = payload.get("provider_review_required") is True
    return {
        "cache_id": worker_cache_id(run_id, schedule_item_id),
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
            "blocked_reason": activation_blocked_reason(payload),
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
