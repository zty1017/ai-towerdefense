"""Read-model builders for Generation Scheduler prefetch cache views."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .generation_scheduler_run_queue_builders import compact_generation_schedule_run


PREFETCH_CACHE_REF_KINDS = (
    "generation_executor_run_request",
    "provider_execution_authorization",
    "provider_adapter_execution_receipt",
    "provider_output_envelope",
    "provider_artifact_staging_manifest",
    "provider_artifact_promotion_report",
    "shared_prefetch_cache_reuse_candidate",
    "generation_runtime_build_request",
)


def ledger_entry_ref(item: dict[str, Any] | None) -> dict[str, Any] | None:
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


def prefetch_cache_status(
    queue_item: dict[str, Any],
    refs: dict[str, dict[str, Any] | None],
) -> str:
    if refs.get("generation_runtime_build_request") is not None:
        return "runtime_build_request_prepared"
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
    if refs.get("shared_prefetch_cache_reuse_candidate") is not None:
        return "shared_cache_reuse_pending_runtime_build"
    queue_status = str(queue_item.get("queue_status") or queue_item.get("status") or "")
    if queue_status == "waiting_review":
        return "waiting_review_without_envelope"
    if queue_status in {"queued", "completed", "fallback_ready", "failed", "claimed"}:
        return queue_status
    return "not_started"


def build_generation_prefetch_cache_payload(
    session_id: str,
    latest_run: dict[str, Any] | None,
    queue_items: list[dict[str, Any]],
    ledger_items: list[dict[str, Any]],
) -> dict[str, Any]:
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
            "refs": {artifact_kind: None for artifact_kind in PREFETCH_CACHE_REF_KINDS},
        }
    for ledger_item in ledger_items:
        schedule_item_id = str(ledger_item.get("schedule_item_id") or "")
        if not schedule_item_id or schedule_item_id not in by_schedule_item:
            continue
        artifact_kind = str(ledger_item.get("artifact_kind") or "")
        refs = by_schedule_item[schedule_item_id]["refs"]
        if artifact_kind in refs:
            refs[artifact_kind] = ledger_entry_ref(ledger_item)

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
        item["cache_status"] = prefetch_cache_status(item, refs)
        item["runtime_ready"] = False
        item["recorded_provider_call_count"] = (
            1
            if (
                isinstance(envelope_compact.get("provider_call"), dict)
                and envelope_compact["provider_call"].get("performed") is True
            )
            else 0
        )
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
        reuse_ref = refs.get("shared_prefetch_cache_reuse_candidate")
        reuse_compact = (
            reuse_ref.get("compact")
            if isinstance(reuse_ref, dict)
            and isinstance(reuse_ref.get("compact"), dict)
            else {}
        )
        reuse_gate = (
            reuse_compact.get("reuse_gate")
            if isinstance(reuse_compact.get("reuse_gate"), dict)
            else {}
        )
        item["shared_cache_reuse"] = {
            "reuse_candidate_recorded": reuse_ref is not None,
            "reuse_available": reuse_gate.get("reuse_available") is True,
            "cache_key": (
                reuse_compact.get("shared_cache_ref", {}).get("cache_key")
                if isinstance(reuse_compact.get("shared_cache_ref"), dict)
                else None
            ),
            "blocked_reason": reuse_gate.get("blocked_reason"),
            "required_next_gates": reuse_gate.get("required_next_gates", []),
            "runtime_ready": False,
            "activation_allowed": False,
        }
        runtime_build_ref = refs.get("generation_runtime_build_request")
        runtime_build_compact = (
            runtime_build_ref.get("compact")
            if isinstance(runtime_build_ref, dict)
            and isinstance(runtime_build_ref.get("compact"), dict)
            else {}
        )
        runtime_build_gate = (
            runtime_build_compact.get("build_gate")
            if isinstance(runtime_build_compact.get("build_gate"), dict)
            else {}
        )
        item["runtime_build_request"] = {
            "request_recorded": runtime_build_ref is not None,
            "request_id": runtime_build_compact.get("request_id"),
            "source_candidate_ref": runtime_build_compact.get(
                "source_candidate_ref", {}
            ),
            "blocked_reason": runtime_build_gate.get("blocked_reason"),
            "required_next_gates": runtime_build_gate.get("required_next_gates", []),
            "runtime_ready": False,
            "activation_allowed": False,
            "world_mutation_allowed": False,
        }
        item["activation_allowed"] = item["activation_gate"]["activation_allowed"]
        item["promotion_allowed"] = item["promotion_gate"]["promotion_allowed"]
        item["review_only"] = True
        cache_items.append(item)

    summary_counts = Counter(str(item.get("cache_status")) for item in cache_items)
    ready_count = sum(
        1
        for item in cache_items
        if item.get("cache_status") == "review_only_envelope_ready"
    )
    staged_count = sum(
        1
        for item in cache_items
        if item.get("cache_status")
        in {
            "staged_review_only",
            "promotion_blocked",
            "promotion_allowed_pending_activation",
            "shared_cache_reuse_pending_runtime_build",
            "runtime_build_request_prepared",
        }
    )
    return {
        "session_id": session_id,
        "mode": "frontend_mock_fixture",
        "generation_schedule_run": compact_generation_schedule_run(latest_run),
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
                "shared_cache_reuse_candidate_count": sum(
                    1
                    for item in cache_items
                    if isinstance(item.get("refs"), dict)
                    and item["refs"].get("shared_prefetch_cache_reuse_candidate")
                    is not None
                ),
                "runtime_build_request_count": sum(
                    1
                    for item in cache_items
                    if item.get("cache_status") == "runtime_build_request_prepared"
                ),
            },
            "items": cache_items,
        },
    }
