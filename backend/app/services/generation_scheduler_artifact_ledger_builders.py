"""Pure artifact ledger and provider artifact compact builders."""

from __future__ import annotations

from collections import Counter
from typing import Any


def compact_provider_output_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
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


def compact_provider_artifact_staging(manifest: dict[str, Any]) -> dict[str, Any]:
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


def compact_provider_artifact_promotion_report(
    report: dict[str, Any],
) -> dict[str, Any]:
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

    def compact_local_refs(value: Any) -> list[dict[str, Any]]:
        refs = value if isinstance(value, list) else []
        return [
            {
                "path": ref.get("path"),
                "kind": ref.get("kind"),
                "sha256": ref.get("sha256"),
            }
            for ref in refs
            if isinstance(ref, dict)
        ]

    runtime_package_refs = compact_local_refs(targets.get("runtime_package_refs"))
    world_transaction_refs = compact_local_refs(
        targets.get("world_transaction_refs")
    )
    published_media_refs = compact_local_refs(targets.get("published_media_refs"))
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
            "runtime_package_refs": runtime_package_refs,
            "world_transaction_refs": world_transaction_refs,
            "published_media_refs": published_media_refs,
            "runtime_package_ref_count": len(runtime_package_refs),
            "world_transaction_ref_count": len(world_transaction_refs),
            "published_media_ref_count": len(published_media_refs),
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
            "stores_secret": safety.get("stores_secret"),
            "uses_temporary_url": safety.get("uses_temporary_url"),
        },
    }


def build_artifact_ledger_payload(
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


def artifact_ledger_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
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


def compact_generation_artifact_ledger(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "summary": artifact_ledger_summary(items),
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
