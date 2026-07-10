"""Validate a scheduler evidence chain and invoke the shared runtime apply gate."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..db import now_iso
from .generation_scheduler_artifact_ledger_repository import (
    load_generation_artifact_ledger_items,
    upsert_generation_artifact_ledger,
)
from .generation_scheduler_run_queue_repository import (
    load_generation_queue_item_row,
    load_latest_generation_schedule_run,
)
from .runtime_activation_service import apply_runtime_package


_REPO_ROOT = Path(__file__).resolve().parents[3]
RUNTIME_ACTIVATION_RECEIPT_LEDGER_KIND = "generation_runtime_activation_receipt"
RUNTIME_ACTIVATION_RECEIPT_CACHE_STATUS = "runtime_activated"


def _obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _latest(
    items: list[dict[str, Any]], artifact_kind: str, schedule_item_id: str
) -> dict[str, Any] | None:
    matches = [
        item
        for item in items
        if item.get("artifact_kind") == artifact_kind
        and str(item.get("schedule_item_id") or "") == schedule_item_id
    ]
    return matches[-1] if matches else None


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _require_link(
    ref: dict[str, Any], entry: dict[str, Any], *, label: str
) -> None:
    _require(ref.get("ledger_id") == entry.get("ledger_id"), f"{label} ledger link changed")
    _require(ref.get("source_id") == entry.get("source_id"), f"{label} source link changed")
    _require(ref.get("artifact_kind") == entry.get("artifact_kind"), f"{label} kind changed")


def _require_run_ref(
    compact: dict[str, Any], *, session_id: str, run_id: str, schedule_item_id: str
) -> None:
    ref = _obj(compact.get("current_run_ref"))
    _require(ref.get("session_id") == session_id, "scheduler evidence session changed")
    _require(ref.get("run_id") == run_id, "scheduler evidence run changed")
    _require(
        ref.get("schedule_item_id") == schedule_item_id,
        "scheduler evidence item changed",
    )


def _require_object_ref(
    compact: dict[str, Any], *, object_kind: str, object_ref: str, label: str
) -> None:
    candidate = _obj(compact.get("object"))
    _require(candidate.get("object_kind") == object_kind, f"{label} object kind changed")
    _require(candidate.get("object_ref") == object_ref, f"{label} object ref changed")


def _require_safe_flags(compact: dict[str, Any], *, label: str) -> None:
    safety = _obj(compact.get("safety"))
    for key in (
        "reads_env",
        "calls_provider",
        "stores_raw_prompt",
        "stores_provider_response",
        "writes_world_state",
        "activates_runtime",
        "completes_queue_item",
    ):
        _require(safety.get(key) is False, f"{label} safety flag {key} is not false")


def _repo_package_path(ref: dict[str, Any]) -> Path:
    raw_path = str(ref.get("path") or "")
    _require(bool(raw_path), "runtime package target path is missing")
    path = Path(raw_path)
    path = path if path.is_absolute() else _REPO_ROOT / path
    try:
        path.resolve().relative_to(_REPO_ROOT.resolve())
    except (OSError, ValueError) as exc:
        raise ValueError("runtime package target escaped the repository") from exc
    return path


def _receipt_ledger_entry(
    *,
    session_id: str,
    run_id: str,
    schedule_item_id: str,
    worker_id: str,
    note: str | None,
    receipt: dict[str, Any],
) -> dict[str, Any]:
    activation_id = str(receipt.get("activation_id") or "")
    timestamp = now_iso()
    return {
        "schema_version": "generation_artifact_ledger_entry.v0.1",
        "ledger_id": f"gled_{session_id}_{RUNTIME_ACTIVATION_RECEIPT_LEDGER_KIND}_{activation_id}",
        "session_id": session_id,
        "run_id": run_id,
        "schedule_item_id": schedule_item_id,
        "artifact_kind": RUNTIME_ACTIVATION_RECEIPT_LEDGER_KIND,
        "source_id": activation_id,
        "status": (
            "runtime_activated"
            if receipt.get("status") == "activated"
            else "runtime_activation_blocked"
        ),
        "worker_id": worker_id,
        "note": note,
        "created_at": timestamp,
        "updated_at": timestamp,
        "provider_call_performed_by_this_request": False,
        "world_mutation_performed_by_this_request": False,
        "activation_allowed_now": receipt.get("status") == "activated",
        "ledger_write_policy": {
            "mode": "explicit_runtime_apply_receipt",
            "reads_env": False,
            "calls_provider": False,
            "stores_raw_prompt": False,
            "stores_provider_response": False,
            "writes_world_state": False,
        },
        "compact": receipt,
    }


def apply_generation_runtime_activation(
    session_id: str,
    *,
    schedule_item_id: str | None,
    worker_id: str,
    note: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply one explicitly authorized runtime package and record its receipt."""

    latest_run = load_latest_generation_schedule_run(session_id)
    _require(latest_run is not None, "generation schedule run is required before runtime apply")
    run_id = str(_obj(latest_run).get("run_id") or "")
    items = load_generation_artifact_ledger_items(session_id, run_id)

    if not schedule_item_id:
        approved_items: list[str] = []
        for item in items:
            if item.get("artifact_kind") != "generation_runtime_activation_authorization":
                continue
            compact = _obj(item.get("compact"))
            decision = _obj(compact.get("decision"))
            if (
                decision.get("decision") == "approved_for_manual_apply"
                and decision.get("developer_approval_recorded") is True
            ):
                approved_items.append(str(item.get("schedule_item_id") or ""))
        _require(bool(approved_items), "no approved runtime activation authorization is available")
        schedule_item_id = approved_items[-1]

    queue_row = load_generation_queue_item_row(session_id, schedule_item_id, run_id)
    _require(queue_row is not None, "scheduler queue item no longer exists")
    queue_item = _obj(_obj(queue_row).get("payload"))
    object_kind = str(queue_item.get("object_kind") or "")
    object_ref = str(queue_item.get("object_ref") or "")

    authorization = _latest(
        items, "generation_runtime_activation_authorization", schedule_item_id
    )
    _require(authorization is not None, "runtime activation authorization is required")
    authorization_compact = _obj(_obj(authorization).get("compact"))
    _require(
        authorization_compact.get("schema_version")
        == "generation_runtime_activation_authorization.v0.1",
        "runtime activation authorization schema is not accepted",
    )
    _require_run_ref(
        authorization_compact,
        session_id=session_id,
        run_id=run_id,
        schedule_item_id=schedule_item_id,
    )
    decision = _obj(authorization_compact.get("decision"))
    _require(
        decision.get("decision") == "approved_for_manual_apply"
        and decision.get("developer_approval_recorded") is True,
        "runtime activation was not explicitly approved for manual apply",
    )
    _require(
        decision.get("approval_scope") == "review_only_runtime_activation_record",
        "runtime activation approval scope is not accepted",
    )
    authorization_gate = _obj(authorization_compact.get("activation_gate"))
    _require(
        authorization_gate.get("authorization_recorded") is True
        and authorization_gate.get("runtime_apply_allowed") is False
        and authorization_gate.get("world_mutation_allowed") is False,
        "authorization record attempted to bypass the apply gate",
    )
    _require_object_ref(
        authorization_compact,
        object_kind=object_kind,
        object_ref=object_ref,
        label="authorization",
    )
    _require_safe_flags(authorization_compact, label="authorization")

    build_report = _latest(
        items, "generation_runtime_artifact_build_report", schedule_item_id
    )
    _require(build_report is not None, "runtime artifact build report is required")
    _require_link(
        _obj(authorization_compact.get("source_report_ref")),
        _obj(build_report),
        label="authorization to build report",
    )
    report_compact = _obj(_obj(build_report).get("compact"))
    _require(
        report_compact.get("schema_version")
        == "generation_runtime_artifact_build_report.v0.1",
        "runtime artifact build report schema is not accepted",
    )
    _require_run_ref(
        report_compact,
        session_id=session_id,
        run_id=run_id,
        schedule_item_id=schedule_item_id,
    )
    _require_object_ref(
        report_compact,
        object_kind=object_kind,
        object_ref=object_ref,
        label="build report",
    )
    _require_safe_flags(report_compact, label="build report")

    build_request = _latest(items, "generation_runtime_build_request", schedule_item_id)
    _require(build_request is not None, "runtime build request is required")
    _require_link(
        _obj(report_compact.get("source_request_ref")),
        _obj(build_request),
        label="build report to request",
    )
    request_compact = _obj(_obj(build_request).get("compact"))
    _require(
        request_compact.get("schema_version") == "generation_runtime_build_request.v0.1",
        "runtime build request schema is not accepted",
    )
    _require_run_ref(
        request_compact,
        session_id=session_id,
        run_id=run_id,
        schedule_item_id=schedule_item_id,
    )
    _require_object_ref(
        request_compact,
        object_kind=object_kind,
        object_ref=object_ref,
        label="build request",
    )
    _require_safe_flags(request_compact, label="build request")

    promotion = _latest(items, "provider_artifact_promotion_report", schedule_item_id)
    _require(promotion is not None, "provider promotion report is required")
    _require_link(
        _obj(request_compact.get("source_candidate_ref")),
        _obj(promotion),
        label="build request to promotion report",
    )
    promotion_compact = _obj(_obj(promotion).get("compact"))
    _require(promotion.get("status") == "promotion_allowed", "promotion ledger is not allowed")
    _require(
        report_compact.get("source_candidate_ref")
        == request_compact.get("source_candidate_ref"),
        "build report promotion source changed",
    )
    _require(
        promotion_compact.get("schema_version")
        == "provider_artifact_promotion_report.v0.1",
        "provider promotion report schema is not accepted",
    )
    _require(
        promotion_compact.get("promotion_allowed") is True
        and promotion_compact.get("promotion_decision")
        == "approved_for_runtime_package_build",
        "provider promotion report did not approve a runtime package",
    )
    promotion_safety = _obj(promotion_compact.get("safety_summary"))
    for key in (
        "provider_call_count_by_report",
        "world_mutation_count_by_report",
        "runtime_mutation_count_by_report",
    ):
        _require(promotion_safety.get(key) == 0, f"promotion safety count {key} is not zero")
    for key in (
        "stores_prompt_body",
        "stores_provider_body",
        "stores_secret",
        "uses_temporary_url",
    ):
        _require(promotion_safety.get(key) is False, f"promotion safety flag {key} is not false")
    gate_statuses = _obj(promotion_compact.get("gate_statuses"))
    for gate_name in (
        "source_staging_gate",
        "local_ref_gate",
        "media_gate",
        "semantic_gate",
        "human_review",
    ):
        _require(
            gate_statuses.get(gate_name) == "passed",
            f"promotion gate {gate_name} did not pass",
        )
    _require(
        gate_statuses.get("simulation_gate") in {"passed", "not_applicable"},
        "promotion simulation gate did not pass",
    )

    targets = _obj(report_compact.get("resolved_targets"))
    runtime_refs = [_obj(ref) for ref in _list(targets.get("runtime_package_refs"))]
    _require(targets.get("build_status") == "resolved_review_only", "runtime build did not resolve")
    _require(len(runtime_refs) == 1, "runtime apply v0.1 requires exactly one runtime package")
    _require(targets.get("target_count") == 1, "runtime build target count is inconsistent")
    for key in (
        "map_runtime_package_refs",
        "world_delta_transaction_refs",
        "published_media_update_refs",
        "unresolved_targets",
    ):
        _require(not _list(targets.get(key)), f"runtime apply cannot consume {key}")
    package_ref = runtime_refs[0]
    _require(
        package_ref.get("ref_kind") == "runtime_package",
        "resolved target is not a runtime package",
    )
    package_hash = str(package_ref.get("sha256") or "")
    _require(len(package_hash) == 64, "resolved runtime package has no immutable hash")

    promotion_targets = _obj(promotion_compact.get("promotion_targets"))
    _require(
        promotion_targets.get("target_kind") == "runtime_package",
        "promotion report target kind is not runtime_package",
    )
    promoted_refs = [
        _obj(ref) for ref in _list(promotion_targets.get("runtime_package_refs"))
    ]
    _require(len(promoted_refs) == 1, "promotion report must name exactly one runtime package")
    promoted_ref = promoted_refs[0]
    _require(
        promoted_ref.get("kind") == "runtime_package",
        "promotion target ref kind is not runtime_package",
    )
    _require(
        promoted_ref.get("path") == package_ref.get("path")
        and promoted_ref.get("sha256") == package_hash,
        "promotion and build report runtime package refs differ",
    )
    _require(
        _obj(authorization_compact.get("resolved_targets")).get("runtime_package_refs")
        == runtime_refs,
        "authorized runtime package refs changed after review",
    )

    _require(object_ref.startswith("runtime_package:"), "queue item is not a runtime package build")
    package_path = _repo_package_path(package_ref)
    authorization_id = str(authorization_compact.get("authorization_id") or "")
    receipt = apply_runtime_package(
        session_id,
        source_kind="generation_schedule",
        source_id=authorization_id,
        package_path=package_path,
        allowed_root=_REPO_ROOT,
        expected_package_sha256=package_hash,
        promotion_mode="provider_promotion_report",
        promotion_evidence_id=str(promotion_compact.get("report_id") or ""),
        promotion_ok=True,
    )
    ledger_entry = _receipt_ledger_entry(
        session_id=session_id,
        run_id=run_id,
        schedule_item_id=schedule_item_id,
        worker_id=worker_id,
        note=note,
        receipt=receipt,
    )
    upsert_generation_artifact_ledger(ledger_entry)
    return receipt, ledger_entry
