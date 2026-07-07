"""Read-model builders for Generation Scheduler activation gate views."""

from __future__ import annotations

from collections import Counter
from typing import Any


_NOT_APPLICABLE_STATUSES = {"completed", "fallback_ready"}


def _compact_refs(item: dict[str, Any]) -> dict[str, bool]:
    refs = item.get("refs")
    if not isinstance(refs, dict):
        return {}
    return {str(kind): value is not None for kind, value in sorted(refs.items())}


def _item_promotion_allowed(item: dict[str, Any]) -> bool:
    promotion_gate = item.get("promotion_gate")
    if not isinstance(promotion_gate, dict):
        return False
    return promotion_gate.get("promotion_allowed") is True


def _activation_status(item: dict[str, Any]) -> tuple[str, str | None, list[str]]:
    cache_status = str(item.get("cache_status") or "")
    queue_status = str(item.get("queue_status") or "")
    promotion_gate = item.get("promotion_gate")
    if not isinstance(promotion_gate, dict):
        promotion_gate = {}
    activation_gate = item.get("activation_gate")
    if not isinstance(activation_gate, dict):
        activation_gate = {}

    if cache_status == "promotion_allowed_pending_activation":
        return (
            "blocked_runtime_package_or_world_delta_required",
            "promotion_report_allows_next_build_but_runtime_activation_is_still_forbidden",
            [
                "runtime_package_or_world_delta_transaction_build",
                "runtime_package_validation",
                "explicit_activation_gate",
            ],
        )
    if cache_status == "runtime_build_request_prepared":
        return (
            "blocked_runtime_builder_execution_required",
            "runtime_build_request_recorded_but_builder_has_not_produced_runtime_artifacts",
            [
                "runtime_package_or_world_delta_transaction_builder",
                "runtime_package_validation",
                "world_state_delta_transaction_validation",
                "explicit_activation_gate",
            ],
        )
    if cache_status == "runtime_artifact_build_report_ready":
        return (
            "blocked_explicit_activation_required",
            "runtime_artifact_build_report_is_review_only_and_requires_activation_gate",
            [
                "runtime_artifact_validation_review",
                "media_or_semantic_gate_if_applicable",
                "explicit_activation_gate",
            ],
        )
    if cache_status == "promotion_blocked":
        blocked_reason = promotion_gate.get("blocked_reason") or "promotion_blocked"
        return (
            "blocked_promotion_report",
            str(blocked_reason),
            [
                "fix_failed_promotion_gate",
                "rerun_provider_artifact_promotion_report",
            ],
        )
    if cache_status == "staged_review_only":
        return (
            "blocked_promotion_required",
            "review_only_staging_requires_promotion_report",
            ["provider_artifact_promotion_report"],
        )
    if cache_status == "review_only_envelope_ready":
        blocked_reason = activation_gate.get("blocked_reason")
        return (
            "blocked_staging_or_promotion_required",
            str(blocked_reason or "review_only_envelope_requires_staging_and_promotion"),
            [
                "provider_artifact_staging_manifest",
                "provider_artifact_promotion_report",
            ],
        )
    if cache_status == "adapter_receipt_recorded":
        return (
            "blocked_provider_output_envelope_required",
            "adapter_receipt_must_be_wrapped_in_provider_output_envelope",
            ["provider_output_envelope"],
        )
    if cache_status == "authorized_pending_adapter":
        return (
            "blocked_provider_adapter_required",
            "provider_authorization_does_not_activate_runtime",
            ["provider_adapter_execution_receipt", "provider_output_envelope"],
        )
    if cache_status == "executor_request_prepared":
        return (
            "blocked_provider_authorization_required",
            "executor_request_requires_explicit_provider_authorization",
            ["provider_execution_authorization", "provider_adapter_execution_receipt"],
        )
    if cache_status == "waiting_review_without_envelope":
        return (
            "blocked_provider_output_envelope_required",
            "waiting_review_item_has_no_provider_output_envelope",
            ["provider_output_envelope"],
        )
    if queue_status in _NOT_APPLICABLE_STATUSES:
        return (
            "not_applicable_locked_or_fallback_source",
            None,
            [],
        )
    return (
        "queued_or_not_ready",
        "generation_item_has_not_reached_reviewable_artifact_boundary",
        ["review_only_dispatcher_or_safe_fallback"],
    )


def _gate_item(item: dict[str, Any]) -> dict[str, Any]:
    activation_status, blocked_reason, required_next_gates = _activation_status(item)
    activation_gate = item.get("activation_gate")
    if not isinstance(activation_gate, dict):
        activation_gate = {}
    required_from_gate = activation_gate.get("required_next_gates")
    if not isinstance(required_from_gate, list):
        required_from_gate = []
    merged_required = list(
        dict.fromkeys(
            [
                str(gate)
                for gate in [*required_next_gates, *required_from_gate]
                if str(gate)
            ]
        )
    )
    return {
        "schedule_item_id": item.get("schedule_item_id"),
        "object_kind": item.get("object_kind"),
        "object_ref": item.get("object_ref"),
        "latency_class": item.get("latency_class"),
        "queue_status": item.get("queue_status"),
        "cache_status": item.get("cache_status"),
        "runtime_ready": False,
        "activation_allowed": False,
        "promotion_allowed": _item_promotion_allowed(item),
        "activation_status": activation_status,
        "blocked_reason": blocked_reason,
        "required_next_gates": merged_required,
        "review_only": True,
        "provider_call_count_by_this_request": 0,
        "world_mutation_count_by_this_request": 0,
        "recorded_provider_call_count": int(
            item.get("recorded_provider_call_count", 0)
        ),
        "refs_present": _compact_refs(item),
    }


def build_generation_activation_gate_payload(
    prefetch_payload: dict[str, Any],
) -> dict[str, Any]:
    """Build a read-only activation gate view from an existing prefetch cache."""

    prefetch_cache = prefetch_payload.get("generation_prefetch_cache")
    if not isinstance(prefetch_cache, dict):
        prefetch_cache = {}
    prefetch_summary = prefetch_cache.get("summary")
    if not isinstance(prefetch_summary, dict):
        prefetch_summary = {}
    prefetch_items = prefetch_cache.get("items")
    if not isinstance(prefetch_items, list):
        prefetch_items = []

    items = [_gate_item(item) for item in prefetch_items if isinstance(item, dict)]
    status_counts = Counter(str(item.get("activation_status")) for item in items)
    blocked_count = sum(
        1
        for item in items
        if str(item.get("activation_status", "")).startswith("blocked_")
    )
    return {
        "session_id": prefetch_payload.get("session_id"),
        "mode": prefetch_payload.get("mode") or "frontend_mock_fixture",
        "generation_schedule_run": prefetch_payload.get("generation_schedule_run"),
        "generation_activation_gate": {
            "summary": {
                "item_count": len(items),
                "gate_status_counts": dict(sorted(status_counts.items())),
                "blocked_count": blocked_count,
                "not_applicable_count": sum(
                    1
                    for item in items
                    if item.get("activation_status")
                    == "not_applicable_locked_or_fallback_source"
                ),
                "runtime_ready_count": 0,
                "activation_allowed_count": 0,
                "promotion_allowed_count": sum(
                    1 for item in items if item.get("promotion_allowed") is True
                ),
                "recorded_provider_call_count": int(
                    prefetch_summary.get("recorded_provider_call_count", 0)
                ),
                "provider_call_count_by_this_request": 0,
                "world_mutation_count_by_this_request": 0,
            },
            "items": items,
            "safety": {
                "reads_env": False,
                "calls_provider": False,
                "stages_artifacts": False,
                "promotes_artifacts": False,
                "completes_queue_items": False,
                "writes_world_state": False,
                "activates_runtime": False,
                "source_read_model": "generation_prefetch_cache",
            },
        },
    }
