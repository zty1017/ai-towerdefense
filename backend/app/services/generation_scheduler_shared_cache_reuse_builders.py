"""Builders for review-only shared cache reuse candidate ledger records."""

from __future__ import annotations

import hashlib
import json
from typing import Any


REUSE_CANDIDATE_SCHEMA_VERSION = (
    "generation_shared_prefetch_cache_reuse_candidate.v0.1"
)
REUSE_CANDIDATE_STATUS = "review_only_reuse_candidate"
REUSE_CANDIDATE_LEDGER_KIND = "shared_prefetch_cache_reuse_candidate"
REUSE_CANDIDATE_LEDGER_STATUS = "reuse_candidate_pending_runtime_build"
REUSE_CANDIDATE_CACHE_STATUS = "shared_cache_reuse_pending_runtime_build"
REUSE_REQUIRED_NEXT_GATES = (
    "runtime_package_or_world_delta_transaction_build",
    "runtime_package_validation",
    "world_state_delta_transaction_validation",
    "activation_revalidation",
)


def _stable_candidate_id(
    *,
    session_id: str,
    run_id: str | None,
    schedule_item_id: str | None,
    cache_key: str | None,
) -> str:
    seed = {
        "session_id": session_id,
        "run_id": run_id,
        "schedule_item_id": schedule_item_id,
        "cache_key": cache_key,
    }
    digest = hashlib.sha256(
        json.dumps(seed, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:24]
    return f"gshared_reuse_{digest}"


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


def build_shared_cache_reuse_candidate(
    *,
    session_id: str,
    latest_run: dict[str, Any],
    queue_item: dict[str, Any],
    hit: dict[str, Any],
    ts: str,
    worker_id: str,
    note: str | None,
) -> dict[str, Any]:
    """Build a compact review-only candidate from a shared-cache hit."""

    run_id = str(latest_run.get("run_id") or "")
    schedule_item_id = str(queue_item.get("schedule_item_id") or "")
    cache_key = str(hit.get("cache_key") or "")
    hit_required_gates = hit.get("required_next_gates", [])
    if not isinstance(hit_required_gates, list):
        hit_required_gates = []
    required_next_gates = _dedupe_texts(
        [*hit_required_gates, *REUSE_REQUIRED_NEXT_GATES]
    )
    source = hit.get("source", {})
    if not isinstance(source, dict):
        source = {}
    return {
        "schema_version": REUSE_CANDIDATE_SCHEMA_VERSION,
        "candidate_id": _stable_candidate_id(
            session_id=session_id,
            run_id=run_id,
            schedule_item_id=schedule_item_id,
            cache_key=cache_key,
        ),
        "reuse_status": REUSE_CANDIDATE_STATUS,
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
        "shared_cache_ref": {
            "cache_key": cache_key,
            "lifecycle_status": hit.get("lifecycle_status"),
            "source": source,
            "promotion_allowed": hit.get("promotion_allowed") is True,
            "activation_allowed": False,
            "runtime_ready": False,
            "review_only": True,
        },
        "reuse_gate": {
            "reuse_available": True,
            "reuse_allowed_for_review_chain": True,
            "runtime_ready": False,
            "activation_allowed": False,
            "blocked_reason": "runtime_package_or_world_delta_transaction_required",
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


def compact_shared_cache_reuse_candidate(
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """Return the stable compact form stored in generation_artifact_ledger."""

    return {
        "schema_version": candidate.get("schema_version"),
        "candidate_id": candidate.get("candidate_id"),
        "reuse_status": candidate.get("reuse_status"),
        "current_run_ref": candidate.get("current_run_ref", {}),
        "object": candidate.get("object", {}),
        "shared_cache_ref": candidate.get("shared_cache_ref", {}),
        "reuse_gate": candidate.get("reuse_gate", {}),
        "safety": candidate.get("safety", {}),
    }
