"""Builders for review-only runtime activation authorization ledger records."""

from __future__ import annotations

import hashlib
import json
from typing import Any


RUNTIME_ACTIVATION_AUTHORIZATION_SCHEMA_VERSION = (
    "generation_runtime_activation_authorization.v0.1"
)
RUNTIME_ACTIVATION_AUTHORIZATION_LEDGER_KIND = (
    "generation_runtime_activation_authorization"
)
RUNTIME_ACTIVATION_AUTHORIZATION_LEDGER_STATUS = (
    "runtime_activation_authorization_recorded_review_only"
)
RUNTIME_ACTIVATION_AUTHORIZATION_CACHE_STATUS = (
    "runtime_activation_authorization_recorded"
)
RUNTIME_ACTIVATION_AUTHORIZATION_ALLOWED_DECISIONS = {
    "approved_for_manual_apply",
    "needs_more_review",
    "rejected",
}
RUNTIME_ACTIVATION_REQUIRED_NEXT_GATES = (
    "runtime_activation_apply_gate",
    "post_activation_validation_evidence",
    "queue_completion_after_runtime_effect_if_applicable",
)


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dedupe_texts(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _stable_authorization_id(
    *,
    session_id: str,
    run_id: str | None,
    schedule_item_id: str | None,
    report_id: str | None,
    decision: str,
) -> str:
    seed = {
        "session_id": session_id,
        "run_id": run_id,
        "schedule_item_id": schedule_item_id,
        "report_id": report_id,
        "decision": decision,
    }
    digest = hashlib.sha256(
        json.dumps(seed, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:24]
    return f"gruntime_activation_auth_{digest}"


def normalize_runtime_activation_decision(value: Any) -> str:
    decision = str(value or "approved_for_manual_apply").strip()
    if decision not in RUNTIME_ACTIVATION_AUTHORIZATION_ALLOWED_DECISIONS:
        allowed = ", ".join(sorted(RUNTIME_ACTIVATION_AUTHORIZATION_ALLOWED_DECISIONS))
        raise ValueError(f"unsupported runtime activation decision {decision}; allowed: {allowed}")
    return decision


def _target_count(report_compact: dict[str, Any]) -> int:
    resolved_targets = _safe_dict(report_compact.get("resolved_targets"))
    return int(resolved_targets.get("target_count", 0) or 0)


def _source_required_gates(report_compact: dict[str, Any]) -> list[Any]:
    build_gate = _safe_dict(report_compact.get("build_gate"))
    return _safe_list(build_gate.get("required_next_gates"))


def build_runtime_activation_authorization(
    *,
    session_id: str,
    latest_run: dict[str, Any],
    queue_item: dict[str, Any],
    runtime_artifact_report_ref: dict[str, Any],
    decision: str,
    ts: str,
    worker_id: str,
    note: str | None,
) -> dict[str, Any]:
    """Build a review-only authorization record for later runtime activation."""

    run_id = str(latest_run.get("run_id") or "")
    schedule_item_id = str(queue_item.get("schedule_item_id") or "")
    report_compact = _safe_dict(runtime_artifact_report_ref.get("compact"))
    report_id = str(report_compact.get("report_id") or "")
    target_count = _target_count(report_compact)
    approval_recorded = decision == "approved_for_manual_apply"
    required_next_gates = _dedupe_texts(
        [*_source_required_gates(report_compact), *RUNTIME_ACTIVATION_REQUIRED_NEXT_GATES]
    )
    return {
        "schema_version": RUNTIME_ACTIVATION_AUTHORIZATION_SCHEMA_VERSION,
        "authorization_id": _stable_authorization_id(
            session_id=session_id,
            run_id=run_id,
            schedule_item_id=schedule_item_id,
            report_id=report_id,
            decision=decision,
        ),
        "authorization_status": RUNTIME_ACTIVATION_AUTHORIZATION_LEDGER_STATUS,
        "created_at": ts,
        "updated_at": ts,
        "worker_id": worker_id,
        "note": note,
        "current_run_ref": {
            "session_id": session_id,
            "run_id": run_id,
            "schedule_item_id": schedule_item_id,
        },
        "object": {
            "object_kind": queue_item.get("object_kind"),
            "object_ref": queue_item.get("object_ref"),
            "latency_class": queue_item.get("latency_class"),
        },
        "source_report_ref": {
            "artifact_kind": runtime_artifact_report_ref.get("artifact_kind"),
            "ledger_id": runtime_artifact_report_ref.get("ledger_id"),
            "source_id": runtime_artifact_report_ref.get("source_id"),
            "report_id": report_id,
            "status": runtime_artifact_report_ref.get("status"),
            "updated_at": runtime_artifact_report_ref.get("updated_at"),
        },
        "resolved_targets": report_compact.get("resolved_targets", {}),
        "decision": {
            "decision": decision,
            "developer_approval_recorded": approval_recorded,
            "approval_scope": "review_only_runtime_activation_record",
            "target_count": target_count,
            "blocked_reason": (
                "runtime_activation_apply_gate_required"
                if approval_recorded
                else "runtime_activation_not_approved"
            ),
            "required_next_gates": required_next_gates,
        },
        "activation_gate": {
            "authorization_recorded": True,
            "runtime_ready": False,
            "activation_allowed": False,
            "runtime_apply_allowed": False,
            "world_mutation_allowed": False,
            "queue_completion_allowed": False,
            "blocked_reason": (
                "authorization_recorded_but_runtime_apply_is_not_executed"
                if approval_recorded
                else "runtime_activation_not_approved"
            ),
            "required_next_gates": required_next_gates,
        },
        "safety": {
            "reads_env": False,
            "calls_provider": False,
            "stores_raw_prompt": False,
            "stores_provider_response": False,
            "writes_runtime_package": False,
            "writes_world_state": False,
            "activates_runtime": False,
            "completes_queue_item": False,
        },
    }


def compact_runtime_activation_authorization(
    authorization: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": authorization.get("schema_version"),
        "authorization_id": authorization.get("authorization_id"),
        "authorization_status": authorization.get("authorization_status"),
        "current_run_ref": authorization.get("current_run_ref", {}),
        "object": authorization.get("object", {}),
        "source_report_ref": authorization.get("source_report_ref", {}),
        "resolved_targets": authorization.get("resolved_targets", {}),
        "decision": authorization.get("decision", {}),
        "activation_gate": authorization.get("activation_gate", {}),
        "safety": authorization.get("safety", {}),
    }
