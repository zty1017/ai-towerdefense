"""Pure provider execution boundary payload builders."""

from __future__ import annotations

from typing import Any


def safe_id_fragment(value: Any) -> str:
    return "".join(
        ch if ch.isalnum() or ch in {"_", "-"} else "_"
        for ch in str(value or "")
    )


def provider_guard_id(payload: dict[str, Any], attempt_count: int) -> str:
    run_id = str(payload.get("run_id") or "")
    schedule_item_id = str(payload.get("schedule_item_id") or "")
    return f"pguard_{run_id}_{safe_id_fragment(schedule_item_id)}_{attempt_count:02d}"


def generation_executor_request_id(
    payload: dict[str, Any], attempt_count: int
) -> str:
    run_id = str(payload.get("run_id") or "")
    schedule_item_id = str(payload.get("schedule_item_id") or "")
    return f"gexec_{run_id}_{safe_id_fragment(schedule_item_id)}_{attempt_count:02d}"


def provider_authorization_ref(schedule_item_id: str) -> str:
    return f"auth_{safe_id_fragment(schedule_item_id)}_fixture_001"


def provider_adapter_execution_receipt_id(schedule_item_id: str) -> str:
    return f"padapter_{safe_id_fragment(schedule_item_id)}_fixture_001"


def build_live_executor_guard_payload(
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
        "guard_id": provider_guard_id(payload, attempt_count),
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


def infer_executor_result_kind(object_kind: Any) -> str:
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


def build_generation_executor_run_request_payload(
    queue_payload: dict[str, Any],
    guard_payload: dict[str, Any],
    metadata: dict[str, Any] | None,
    ts: str,
    *,
    input_refs: list[dict[str, Any]],
    context_refs: list[dict[str, Any]],
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
        "request_id": generation_executor_request_id(queue_payload, attempt_count),
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
        "input_refs": input_refs,
        "context_refs": context_refs,
        "requested_output": {
            "intent_class": f"prepare_review_only_{object_kind}_candidate",
            "result_kind": infer_executor_result_kind(object_kind),
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


def compact_generation_executor_run_request(
    request: dict[str, Any],
) -> dict[str, Any]:
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


def build_provider_execution_authorization_payload(
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
        or provider_authorization_ref(schedule_item_id)
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


def compact_provider_execution_authorization(
    record: dict[str, Any],
) -> dict[str, Any]:
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


def rehydrate_generation_executor_request_for_runner(
    entry: dict[str, Any],
    *,
    created_at: str,
    schedule_plan_ref: str,
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
        "created_at": str(entry.get("created_at") or entry.get("updated_at") or created_at),
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
                "path": schedule_plan_ref,
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


def rehydrate_provider_authorization_for_runner(
    entry: dict[str, Any],
    *,
    created_at: str,
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
        "created_at": str(entry.get("created_at") or entry.get("updated_at") or created_at),
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


def build_provider_adapter_execution_receipt_payload(
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
        "execution_receipt_id": provider_adapter_execution_receipt_id(
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


def compact_provider_adapter_execution_receipt(
    record: dict[str, Any],
) -> dict[str, Any]:
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
