"""Read-model builders for Generation Scheduler daemon readiness."""

from __future__ import annotations

from typing import Any


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _run_present(prefetch_payload: dict[str, Any]) -> bool:
    return isinstance(prefetch_payload.get("generation_schedule_run"), dict)


def _prefetch_items(prefetch_payload: dict[str, Any]) -> list[dict[str, Any]]:
    cache = _safe_dict(prefetch_payload.get("generation_prefetch_cache"))
    return [item for item in _safe_list(cache.get("items")) if isinstance(item, dict)]


def _shared_hit_summary(shared_hit_payload: dict[str, Any]) -> dict[str, Any]:
    hit_view = _safe_dict(shared_hit_payload.get("generation_shared_prefetch_cache_hits"))
    return _safe_dict(hit_view.get("summary"))


def _activation_summary(activation_payload: dict[str, Any]) -> dict[str, Any]:
    activation_gate = _safe_dict(activation_payload.get("generation_activation_gate"))
    return _safe_dict(activation_gate.get("summary"))


def _queue_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    queued_provider_review_required_count = sum(
        1
        for item in items
        if item.get("queue_status") == "queued"
        and item.get("provider_review_required") is True
    )
    waiting_review_count = sum(
        1 for item in items if item.get("queue_status") == "waiting_review"
    )
    review_only_envelope_ready_count = sum(
        1 for item in items if item.get("cache_status") == "review_only_envelope_ready"
    )
    staged_or_reviewed_count = sum(
        1
        for item in items
        if item.get("cache_status")
        in {
            "staged_review_only",
            "promotion_blocked",
            "promotion_allowed_pending_activation",
            "shared_cache_reuse_pending_runtime_build",
            "runtime_build_request_prepared",
            "runtime_artifact_build_report_ready",
            "runtime_activation_authorization_recorded",
        }
    )
    runtime_build_request_count = sum(
        1
        for item in items
        if isinstance(item.get("refs"), dict)
        and item["refs"].get("generation_runtime_build_request") is not None
    )
    runtime_artifact_build_report_count = sum(
        1
        for item in items
        if isinstance(item.get("refs"), dict)
        and item["refs"].get("generation_runtime_artifact_build_report") is not None
    )
    runtime_activation_authorization_count = sum(
        1
        for item in items
        if isinstance(item.get("refs"), dict)
        and item["refs"].get("generation_runtime_activation_authorization") is not None
    )
    runtime_activation_receipt_count = sum(
        1
        for item in items
        if isinstance(item.get("refs"), dict)
        and item["refs"].get("generation_runtime_activation_receipt") is not None
    )
    runtime_activated_count = sum(
        1 for item in items if item.get("cache_status") == "runtime_activated"
    )
    shared_cache_reuse_candidate_count = sum(
        1
        for item in items
        if isinstance(item.get("refs"), dict)
        and item["refs"].get("shared_prefetch_cache_reuse_candidate") is not None
    )
    return {
        "queued_provider_review_required_count": queued_provider_review_required_count,
        "waiting_review_count": waiting_review_count,
        "review_only_envelope_ready_count": review_only_envelope_ready_count,
        "staged_or_reviewed_count": staged_or_reviewed_count,
        "runtime_build_request_count": runtime_build_request_count,
        "runtime_artifact_build_report_count": runtime_artifact_build_report_count,
        "runtime_activation_authorization_count": (
            runtime_activation_authorization_count
        ),
        "runtime_activation_receipt_count": runtime_activation_receipt_count,
        "runtime_activated_count": runtime_activated_count,
        "shared_cache_reuse_candidate_count": shared_cache_reuse_candidate_count,
    }


def _manual_tick_status(
    *,
    has_run: bool,
    queue_counts: dict[str, int],
    shared_hit_count: int,
    promotion_allowed_count: int,
) -> str:
    if not has_run:
        return "ready_initial_tick_can_create_run"
    if queue_counts["queued_provider_review_required_count"] > 0:
        return "ready_to_dispatch_queued_provider_review_items"
    if queue_counts["review_only_envelope_ready_count"] > 0:
        return "waiting_for_external_runner_or_artifact_review"
    if (
        queue_counts["runtime_activation_authorization_count"]
        > queue_counts["runtime_activation_receipt_count"]
    ):
        return "waiting_for_runtime_activation_apply_gate"
    if queue_counts["runtime_artifact_build_report_count"] > 0:
        return "waiting_for_explicit_runtime_activation_gate"
    if queue_counts["runtime_build_request_count"] > 0:
        return "waiting_for_runtime_builder_execution"
    if queue_counts["shared_cache_reuse_candidate_count"] > 0:
        return "ready_to_prepare_runtime_build_request"
    if shared_hit_count > 0:
        return "ready_to_record_shared_cache_reuse_candidate"
    if promotion_allowed_count > 0:
        return "ready_to_prepare_runtime_build_request"
    if queue_counts["staged_or_reviewed_count"] > 0:
        return "waiting_for_promotion_or_runtime_followup"
    return "idle_no_eligible_generation_work"


def _recommended_next_actions(
    *,
    has_run: bool,
    queue_counts: dict[str, int],
    shared_hit_count: int,
    promotion_allowed_count: int,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if not has_run or queue_counts["queued_provider_review_required_count"] > 0:
        actions.append(
            {
                "action": "run_review_only_background_handoff_tick",
                "endpoint": (
                    "POST /api/sessions/{session_id}/generation-schedule/"
                    "workers/run-review-only-background-handoff-tick"
                ),
                "reason": "seed_or_drain_bounded_review_only_provider_queue",
                "provider_call_count_by_this_request": 0,
                "world_mutation_count_by_this_request": 0,
                "activation_allowed_count": 0,
            }
        )
    if shared_hit_count > queue_counts["shared_cache_reuse_candidate_count"]:
        actions.append(
            {
                "action": "record_shared_prefetch_cache_reuse_candidate",
                "endpoint": (
                    "POST /api/sessions/{session_id}/generation-schedule/"
                    "workers/record-shared-prefetch-cache-reuse-candidate"
                ),
                "reason": "reuse_review_only_cross_session_candidate_before_new_provider_work",
                "provider_call_count_by_this_request": 0,
                "world_mutation_count_by_this_request": 0,
                "activation_allowed_count": 0,
            }
        )
    if queue_counts["review_only_envelope_ready_count"] > 0:
        actions.append(
            {
                "action": "import_provider_artifact_review_output",
                "endpoint": (
                    "POST /api/sessions/{session_id}/generation-schedule/"
                    "workers/import-provider-artifact-review-output"
                ),
                "reason": "provider_output_envelope_requires_staging_and_promotion_review",
                "provider_call_count_by_this_request": 0,
                "world_mutation_count_by_this_request": 0,
                "activation_allowed_count": 0,
            }
        )
    runtime_build_source_count = (
        promotion_allowed_count + queue_counts["shared_cache_reuse_candidate_count"]
    )
    if (
        runtime_build_source_count > 0
        and queue_counts["runtime_activation_authorization_count"]
        < runtime_build_source_count
    ):
        actions.append(
            {
                "action": "run_runtime_activation_readiness_chain",
                "endpoint": (
                    "POST /api/sessions/{session_id}/generation-schedule/"
                    "workers/run-runtime-activation-readiness-chain"
                ),
                "reason": "shortcut_prepare_runtime_report_and_activation_authorization_without_bypassing_gates",
                "provider_call_count_by_this_request": 0,
                "world_mutation_count_by_this_request": 0,
                "activation_allowed_count": 0,
            }
        )
    if queue_counts["runtime_build_request_count"] < runtime_build_source_count:
        actions.append(
            {
                "action": "prepare_runtime_build_request",
                "endpoint": (
                    "POST /api/sessions/{session_id}/generation-schedule/"
                    "workers/prepare-runtime-build-request"
                ),
                "reason": "promotion_allowed_candidate_needs_review_only_runtime_build_request",
                "provider_call_count_by_this_request": 0,
                "world_mutation_count_by_this_request": 0,
                "activation_allowed_count": 0,
            }
        )
    if (
        queue_counts["runtime_build_request_count"]
        > queue_counts["runtime_artifact_build_report_count"]
    ):
        actions.append(
            {
                "action": "run_runtime_artifact_build_report",
                "endpoint": (
                    "POST /api/sessions/{session_id}/generation-schedule/"
                    "workers/run-runtime-artifact-build-report"
                ),
                "reason": "runtime_build_request_needs_review_only_target_resolution",
                "provider_call_count_by_this_request": 0,
                "world_mutation_count_by_this_request": 0,
                "activation_allowed_count": 0,
            }
        )
    if (
        queue_counts["runtime_artifact_build_report_count"]
        > queue_counts["runtime_activation_authorization_count"]
    ):
        actions.append(
            {
                "action": "record_runtime_activation_authorization",
                "endpoint": (
                    "POST /api/sessions/{session_id}/generation-schedule/"
                    "workers/record-runtime-activation-authorization"
                ),
                "reason": "runtime_artifact_build_report_requires_explicit_activation_record",
                "provider_call_count_by_this_request": 0,
                "world_mutation_count_by_this_request": 0,
                "activation_allowed_count": 0,
            }
        )
    if (
        queue_counts["runtime_activation_authorization_count"]
        > queue_counts["runtime_activation_receipt_count"]
    ):
        actions.append(
            {
                "action": "wait_for_runtime_activation_apply_gate",
                "endpoint": None,
                "reason": "runtime_activation_authorization_is_review_only",
                "provider_call_count_by_this_request": 0,
                "world_mutation_count_by_this_request": 0,
                "activation_allowed_count": 0,
            }
        )
    elif queue_counts["runtime_artifact_build_report_count"] > 0:
        actions.append(
            {
                "action": "wait_for_explicit_runtime_activation_gate",
                "endpoint": None,
                "reason": "runtime_artifact_build_report_is_review_only",
                "provider_call_count_by_this_request": 0,
                "world_mutation_count_by_this_request": 0,
                "activation_allowed_count": 0,
            }
        )
    if not actions:
        actions.append(
            {
                "action": "no_background_generation_action",
                "endpoint": None,
                "reason": "no_eligible_review_only_generation_work",
                "provider_call_count_by_this_request": 0,
                "world_mutation_count_by_this_request": 0,
                "activation_allowed_count": 0,
            }
        )
    return actions


def _readiness_gates(
    *,
    has_run: bool,
    queue_counts: dict[str, int],
    shared_hit_count: int,
) -> list[dict[str, Any]]:
    return [
        {
            "gate": "automatic_daemon_enabled",
            "status": "blocked",
            "reason": "mvp_uses_manual_bounded_ticks_not_an_always_on_daemon",
        },
        {
            "gate": "session_generation_schedule_run",
            "status": "present" if has_run else "missing_but_manual_tick_can_create",
            "reason": None if has_run else "review_only_tick_seeds_latest_run_from_fixture_plan",
        },
        {
            "gate": "queued_provider_review_work",
            "status": (
                "ready"
                if queue_counts["queued_provider_review_required_count"] > 0
                else "idle"
            ),
            "reason": None
            if queue_counts["queued_provider_review_required_count"] > 0
            else "no_queued_provider_review_items_in_latest_run",
        },
        {
            "gate": "shared_prefetch_cache_reuse",
            "status": "ready" if shared_hit_count > 0 else "idle",
            "reason": None
            if shared_hit_count > 0
            else "no_cross_session_candidate_matches_current_run",
        },
        {
            "gate": "provider_dispatch",
            "status": "blocked_external_runner_required",
            "reason": "backend_readiness_view_must_not_call_provider_or_read_env",
        },
        {
            "gate": "artifact_promotion",
            "status": "blocked_explicit_review_required",
            "reason": "staging_and_promotion_reports_must_be_imported_or_built_explicitly",
        },
        {
            "gate": "runtime_builder_execution",
            "status": (
                "resolved_review_only"
                if queue_counts["runtime_artifact_build_report_count"] > 0
                else "waiting_for_builder"
                if queue_counts["runtime_build_request_count"] > 0
                else "blocked_request_required"
            ),
            "reason": "runtime_build_request_does_not_build_or_activate_runtime",
        },
        {
            "gate": "runtime_activation",
            "status": (
                "activated"
                if queue_counts["runtime_activated_count"] > 0
                else "authorized_review_only_blocked_apply"
                if queue_counts["runtime_activation_authorization_count"] > 0
                else "blocked_explicit_activation_required"
            ),
            "reason": (
                "runtime_activation_receipt_confirms_session_patch"
                if queue_counts["runtime_activated_count"] > 0
                else "runtime_activation_authorization_record_does_not_apply_runtime"
                if queue_counts["runtime_activation_authorization_count"] > 0
                else "promotion_allowed_does_not_activate_runtime_or_write_world_state"
            ),
        },
    ]


def build_generation_daemon_readiness_payload(
    *,
    session_id: str,
    prefetch_payload: dict[str, Any],
    activation_payload: dict[str, Any],
    shared_hit_payload: dict[str, Any],
) -> dict[str, Any]:
    """Build a safe control-plane view for future background executor daemons."""

    items = _prefetch_items(prefetch_payload)
    queue_counts = _queue_counts(items)
    activation_summary = _activation_summary(activation_payload)
    hit_summary = _shared_hit_summary(shared_hit_payload)
    has_run = _run_present(prefetch_payload)
    shared_hit_count = int(hit_summary.get("hit_count", 0) or 0)
    promotion_allowed_count = int(
        activation_summary.get("promotion_allowed_count", 0) or 0
    )
    manual_tick_status = _manual_tick_status(
        has_run=has_run,
        queue_counts=queue_counts,
        shared_hit_count=shared_hit_count,
        promotion_allowed_count=promotion_allowed_count,
    )
    manual_tick_ready = manual_tick_status.startswith("ready_")
    return {
        "session_id": session_id,
        "mode": prefetch_payload.get("mode") or "frontend_mock_fixture",
        "generation_schedule_run": prefetch_payload.get("generation_schedule_run"),
        "generation_daemon_readiness": {
            "schema_version": "generation_daemon_readiness.v0.1",
            "readiness_mode": "review_only_control_plane",
            "automatic_daemon_status": "blocked_not_enabled_in_mvp",
            "manual_tick_status": manual_tick_status,
            "manual_tick_ready": manual_tick_ready,
            "summary": {
                "has_generation_schedule_run": has_run,
                "schedule_item_count": len(items),
                **queue_counts,
                "shared_cache_hit_count": shared_hit_count,
                "activation_blocked_count": int(
                    activation_summary.get("blocked_count", 0) or 0
                ),
                "promotion_allowed_count": promotion_allowed_count,
                "runtime_ready_count": int(
                    activation_summary.get("runtime_ready_count", 0) or 0
                ),
                "activation_allowed_count": int(
                    activation_summary.get("activation_allowed_count", 0) or 0
                ),
                "provider_call_count_by_this_request": 0,
                "world_mutation_count_by_this_request": 0,
            },
            "readiness_gates": _readiness_gates(
                has_run=has_run,
                queue_counts=queue_counts,
                shared_hit_count=shared_hit_count,
            ),
            "recommended_next_actions": _recommended_next_actions(
                has_run=has_run,
                queue_counts=queue_counts,
                shared_hit_count=shared_hit_count,
                promotion_allowed_count=promotion_allowed_count,
            ),
            "safety": {
                "reads_env": False,
                "calls_provider": False,
                "runs_always_on_loop": False,
                "auto_provider_dispatch_allowed": False,
                "external_runner_required_for_provider_calls": True,
                "stores_raw_prompt": False,
                "stores_provider_response": False,
                "stages_artifacts": False,
                "promotes_artifacts": False,
                "completes_queue_items": False,
                "writes_world_state": False,
                "activates_runtime": False,
                "source_read_models": [
                    "generation_prefetch_cache",
                    "generation_activation_gate",
                    "generation_shared_prefetch_cache_hits",
                ],
            },
        },
    }
