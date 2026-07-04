"""Builders for the cross-session Generation Scheduler shared prefetch cache."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any


ELIGIBLE_ACTIVATION_STATUS = "blocked_runtime_package_or_world_delta_required"
LIFECYCLE_STATUS = "promotion_allowed_pending_runtime_build"


def _stable_cache_key(item: dict[str, Any]) -> str:
    seed = {
        "object_kind": item.get("object_kind"),
        "object_ref": item.get("object_ref"),
        "activation_status": item.get("activation_status"),
        "required_next_gates": item.get("required_next_gates", []),
    }
    digest = hashlib.sha256(
        json.dumps(seed, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:24]
    return f"gshared_{digest}"


def _eligible_for_shared_cache(item: dict[str, Any]) -> bool:
    return (
        item.get("promotion_allowed") is True
        and item.get("activation_allowed") is False
        and item.get("runtime_ready") is False
        and item.get("activation_status") == ELIGIBLE_ACTIVATION_STATUS
    )


def build_shared_prefetch_cache_records(
    activation_gate_payload: dict[str, Any],
    *,
    indexed_at: str,
) -> list[dict[str, Any]]:
    """Build reusable cache records from an activation-gate read model."""

    gate = activation_gate_payload.get("generation_activation_gate")
    if not isinstance(gate, dict):
        return []
    items = gate.get("items")
    if not isinstance(items, list):
        return []
    run = activation_gate_payload.get("generation_schedule_run")
    run_id = run.get("run_id") if isinstance(run, dict) else None
    session_id = str(activation_gate_payload.get("session_id") or "")
    records: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict) or not _eligible_for_shared_cache(item):
            continue
        cache_key = _stable_cache_key(item)
        record = {
            "schema_version": "generation_shared_prefetch_cache_record.v0.1",
            "cache_key": cache_key,
            "source": {
                "source_session_id": session_id,
                "source_run_id": run_id,
                "source_schedule_item_id": item.get("schedule_item_id"),
            },
            "object_kind": item.get("object_kind"),
            "object_ref": item.get("object_ref"),
            "latency_class": item.get("latency_class"),
            "lifecycle_status": LIFECYCLE_STATUS,
            "cache_status": item.get("cache_status"),
            "activation_status": item.get("activation_status"),
            "promotion_allowed": True,
            "activation_allowed": False,
            "runtime_ready": False,
            "review_only": True,
            "required_next_gates": item.get("required_next_gates", []),
            "refs_present": item.get("refs_present", {}),
            "recorded_provider_call_count": int(
                item.get("recorded_provider_call_count", 0)
            ),
            "provider_call_count_by_this_request": 0,
            "world_mutation_count_by_this_request": 0,
            "safety": {
                "stores_raw_prompt": False,
                "stores_provider_response": False,
                "calls_provider": False,
                "writes_world_state": False,
                "activates_runtime": False,
            },
            "created_at": indexed_at,
            "updated_at": indexed_at,
        }
        records.append(record)
    return records


def compact_shared_prefetch_cache(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    status_counts = Counter(str(item.get("lifecycle_status")) for item in records)
    return {
        "summary": {
            "record_count": len(records),
            "lifecycle_status_counts": dict(sorted(status_counts.items())),
            "runtime_ready_count": 0,
            "activation_allowed_count": 0,
            "promotion_allowed_count": sum(
                1 for item in records if item.get("promotion_allowed") is True
            ),
            "provider_call_count_by_this_request": 0,
            "world_mutation_count_by_this_request": 0,
        },
        "records": records,
    }
