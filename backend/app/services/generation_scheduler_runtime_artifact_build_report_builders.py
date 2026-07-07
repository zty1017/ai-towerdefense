"""Builders for review-only runtime artifact build report ledger records."""

from __future__ import annotations

import hashlib
import json
from typing import Any


RUNTIME_ARTIFACT_BUILD_REPORT_SCHEMA_VERSION = (
    "generation_runtime_artifact_build_report.v0.1"
)
RUNTIME_ARTIFACT_BUILD_REPORT_LEDGER_KIND = (
    "generation_runtime_artifact_build_report"
)
RUNTIME_ARTIFACT_BUILD_REPORT_LEDGER_STATUS = (
    "runtime_artifacts_built_review_only"
)
RUNTIME_ARTIFACT_BUILD_REPORT_CACHE_STATUS = (
    "runtime_artifact_build_report_ready"
)
RUNTIME_ARTIFACT_REQUIRED_NEXT_GATES = (
    "runtime_artifact_validation_review",
    "media_or_semantic_gate_if_applicable",
    "explicit_activation_gate",
)


def _stable_report_id(
    *,
    session_id: str,
    run_id: str | None,
    schedule_item_id: str | None,
    request_id: str | None,
) -> str:
    seed = {
        "session_id": session_id,
        "run_id": run_id,
        "schedule_item_id": schedule_item_id,
        "request_id": request_id,
    }
    digest = hashlib.sha256(
        json.dumps(seed, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:24]
    return f"gruntime_artifacts_{digest}"


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


def _count_targets(resolved_targets: dict[str, Any]) -> int:
    count = 0
    for key in (
        "runtime_package_refs",
        "map_runtime_package_refs",
        "world_delta_transaction_refs",
        "published_media_update_refs",
    ):
        count += len(_safe_list(resolved_targets.get(key)))
    return count


def _request_required_gates(request_ref: dict[str, Any]) -> list[Any]:
    compact = _safe_dict(request_ref.get("compact"))
    build_gate = _safe_dict(compact.get("build_gate"))
    return _safe_list(build_gate.get("required_next_gates"))


def build_runtime_artifact_build_report(
    *,
    session_id: str,
    latest_run: dict[str, Any],
    queue_item: dict[str, Any],
    runtime_build_request_ref: dict[str, Any],
    resolved_targets: dict[str, Any],
    ts: str,
    worker_id: str,
    note: str | None,
) -> dict[str, Any]:
    """Build a review-only report for resolved runtime artifact targets."""

    run_id = str(latest_run.get("run_id") or "")
    schedule_item_id = str(queue_item.get("schedule_item_id") or "")
    request_compact = _safe_dict(runtime_build_request_ref.get("compact"))
    request_id = str(request_compact.get("request_id") or "")
    target_count = _count_targets(resolved_targets)
    unresolved_targets = _safe_list(resolved_targets.get("unresolved_targets"))
    required_next_gates = _dedupe_texts(
        [*_request_required_gates(runtime_build_request_ref), *RUNTIME_ARTIFACT_REQUIRED_NEXT_GATES]
    )
    build_status = (
        "resolved_review_only"
        if target_count > 0
        else "not_resolved_review_required"
    )
    return {
        "schema_version": RUNTIME_ARTIFACT_BUILD_REPORT_SCHEMA_VERSION,
        "report_id": _stable_report_id(
            session_id=session_id,
            run_id=run_id,
            schedule_item_id=schedule_item_id,
            request_id=request_id,
        ),
        "report_status": RUNTIME_ARTIFACT_BUILD_REPORT_LEDGER_STATUS,
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
        "source_request_ref": {
            "artifact_kind": runtime_build_request_ref.get("artifact_kind"),
            "ledger_id": runtime_build_request_ref.get("ledger_id"),
            "source_id": runtime_build_request_ref.get("source_id"),
            "request_id": request_id,
            "status": runtime_build_request_ref.get("status"),
            "updated_at": runtime_build_request_ref.get("updated_at"),
        },
        "source_candidate_ref": request_compact.get("source_candidate_ref", {}),
        "resolved_targets": {
            "build_status": build_status,
            "target_count": target_count,
            "runtime_package_refs": _safe_list(
                resolved_targets.get("runtime_package_refs")
            ),
            "map_runtime_package_refs": _safe_list(
                resolved_targets.get("map_runtime_package_refs")
            ),
            "world_delta_transaction_refs": _safe_list(
                resolved_targets.get("world_delta_transaction_refs")
            ),
            "published_media_update_refs": _safe_list(
                resolved_targets.get("published_media_update_refs")
            ),
            "unresolved_targets": unresolved_targets,
        },
        "build_gate": {
            "build_report_recorded": True,
            "runtime_artifact_target_count": target_count,
            "runtime_ready": False,
            "activation_allowed": False,
            "world_mutation_allowed": False,
            "blocked_reason": (
                "explicit_activation_gate_required"
                if target_count > 0
                else "no_resolved_runtime_artifact_target"
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


def compact_runtime_artifact_build_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report.get("schema_version"),
        "report_id": report.get("report_id"),
        "report_status": report.get("report_status"),
        "current_run_ref": report.get("current_run_ref", {}),
        "object": report.get("object", {}),
        "source_request_ref": report.get("source_request_ref", {}),
        "source_candidate_ref": report.get("source_candidate_ref", {}),
        "resolved_targets": report.get("resolved_targets", {}),
        "build_gate": report.get("build_gate", {}),
        "safety": report.get("safety", {}),
    }
