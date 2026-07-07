"""Builders for review-only runtime build request ledger records."""

from __future__ import annotations

import hashlib
import json
from typing import Any


RUNTIME_BUILD_REQUEST_SCHEMA_VERSION = "generation_runtime_build_request.v0.1"
RUNTIME_BUILD_REQUEST_LEDGER_KIND = "generation_runtime_build_request"
RUNTIME_BUILD_REQUEST_LEDGER_STATUS = "runtime_build_request_prepared_review_only"
RUNTIME_BUILD_REQUEST_CACHE_STATUS = "runtime_build_request_prepared"
RUNTIME_BUILD_REQUIRED_NEXT_GATES = (
    "runtime_package_or_world_delta_transaction_builder",
    "runtime_package_validation",
    "world_state_delta_transaction_validation",
    "media_or_semantic_gate_if_applicable",
    "explicit_activation_gate",
)


def _stable_request_id(
    *,
    session_id: str,
    run_id: str | None,
    schedule_item_id: str | None,
    source_artifact_kind: str | None,
    source_id: str | None,
) -> str:
    seed = {
        "session_id": session_id,
        "run_id": run_id,
        "schedule_item_id": schedule_item_id,
        "source_artifact_kind": source_artifact_kind,
        "source_id": source_id,
    }
    digest = hashlib.sha256(
        json.dumps(seed, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:24]
    return f"gruntime_build_{digest}"


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


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _source_kind_and_id(source_ref: dict[str, Any]) -> tuple[str, str]:
    return (
        str(source_ref.get("artifact_kind") or ""),
        str(source_ref.get("source_id") or ""),
    )


def _source_compact(source_ref: dict[str, Any]) -> dict[str, Any]:
    return _safe_dict(source_ref.get("compact"))


def _source_required_gates(source_ref: dict[str, Any]) -> list[Any]:
    compact = _source_compact(source_ref)
    promotion_gate = _safe_dict(compact.get("promotion_gate"))
    reuse_gate = _safe_dict(compact.get("reuse_gate"))
    return [
        *_safe_list(compact.get("required_next_actions")),
        *_safe_list(promotion_gate.get("required_next_gates")),
        *_safe_list(reuse_gate.get("required_next_gates")),
    ]


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def build_runtime_build_request(
    *,
    session_id: str,
    latest_run: dict[str, Any],
    queue_item: dict[str, Any],
    source_ref: dict[str, Any],
    ts: str,
    worker_id: str,
    note: str | None,
) -> dict[str, Any]:
    """Build a review-only request for a future runtime/world-delta builder."""

    run_id = str(latest_run.get("run_id") or "")
    schedule_item_id = str(queue_item.get("schedule_item_id") or "")
    source_artifact_kind, source_id = _source_kind_and_id(source_ref)
    required_next_gates = _dedupe_texts(
        [*_source_required_gates(source_ref), *RUNTIME_BUILD_REQUIRED_NEXT_GATES]
    )
    return {
        "schema_version": RUNTIME_BUILD_REQUEST_SCHEMA_VERSION,
        "request_id": _stable_request_id(
            session_id=session_id,
            run_id=run_id,
            schedule_item_id=schedule_item_id,
            source_artifact_kind=source_artifact_kind,
            source_id=source_id,
        ),
        "request_status": RUNTIME_BUILD_REQUEST_LEDGER_STATUS,
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
        "source_candidate_ref": {
            "artifact_kind": source_artifact_kind,
            "ledger_id": source_ref.get("ledger_id"),
            "source_id": source_id,
            "status": source_ref.get("status"),
            "updated_at": source_ref.get("updated_at"),
        },
        "build_targets": {
            "runtime_package_build_requested": True,
            "world_state_delta_transaction_build_requested": True,
            "published_media_update_requested": False,
            "runtime_activation_requested": False,
            "queue_completion_requested": False,
        },
        "build_gate": {
            "build_request_recorded": True,
            "runtime_ready": False,
            "activation_allowed": False,
            "world_mutation_allowed": False,
            "blocked_reason": "runtime_builder_not_executed",
            "required_next_gates": required_next_gates,
        },
        "safety": {
            "reads_env": False,
            "calls_provider": False,
            "stores_raw_prompt": False,
            "stores_provider_response": False,
            "writes_world_state": False,
            "activates_runtime": False,
            "completes_queue_item": False,
        },
    }


def compact_runtime_build_request(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": request.get("schema_version"),
        "request_id": request.get("request_id"),
        "request_status": request.get("request_status"),
        "current_run_ref": request.get("current_run_ref", {}),
        "object": request.get("object", {}),
        "source_candidate_ref": request.get("source_candidate_ref", {}),
        "build_targets": request.get("build_targets", {}),
        "build_gate": request.get("build_gate", {}),
        "safety": request.get("safety", {}),
    }
