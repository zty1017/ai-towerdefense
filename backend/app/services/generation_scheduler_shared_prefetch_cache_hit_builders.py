"""Read-model builders for shared prefetch cache hits."""

from __future__ import annotations

from collections import Counter
from typing import Any


def _record_key(record: dict[str, Any]) -> tuple[str, str]:
    return (str(record.get("object_kind") or ""), str(record.get("object_ref") or ""))


def _compact_hit(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "cache_key": record.get("cache_key"),
        "object_kind": record.get("object_kind"),
        "object_ref": record.get("object_ref"),
        "lifecycle_status": record.get("lifecycle_status"),
        "source": record.get("source", {}),
        "required_next_gates": record.get("required_next_gates", []),
        "promotion_allowed": record.get("promotion_allowed") is True,
        "activation_allowed": False,
        "runtime_ready": False,
        "review_only": True,
    }


def build_shared_prefetch_cache_hit_payload(
    prefetch_payload: dict[str, Any],
    shared_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a read-only hit view for current queue items vs shared records."""

    prefetch_cache = prefetch_payload.get("generation_prefetch_cache")
    if not isinstance(prefetch_cache, dict):
        prefetch_cache = {}
    prefetch_items = prefetch_cache.get("items")
    if not isinstance(prefetch_items, list):
        prefetch_items = []

    records_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in shared_records:
        if not isinstance(record, dict):
            continue
        if record.get("lifecycle_status") != "promotion_allowed_pending_runtime_build":
            continue
        records_by_key.setdefault(_record_key(record), []).append(record)

    items: list[dict[str, Any]] = []
    for item in prefetch_items:
        if not isinstance(item, dict):
            continue
        key = (
            str(item.get("object_kind") or ""),
            str(item.get("object_ref") or ""),
        )
        hits = [_compact_hit(record) for record in records_by_key.get(key, [])]
        hit_status = (
            "shared_candidate_available_pending_runtime_build"
            if hits
            else "no_shared_candidate"
        )
        items.append(
            {
                "schedule_item_id": item.get("schedule_item_id"),
                "object_kind": item.get("object_kind"),
                "object_ref": item.get("object_ref"),
                "latency_class": item.get("latency_class"),
                "queue_status": item.get("queue_status"),
                "cache_status": item.get("cache_status"),
                "hit_status": hit_status,
                "hit_count": len(hits),
                "hits": hits,
                "activation_allowed": False,
                "runtime_ready": False,
                "provider_call_count_by_this_request": 0,
                "world_mutation_count_by_this_request": 0,
            }
        )

    hit_status_counts = Counter(str(item.get("hit_status")) for item in items)
    hit_count = sum(1 for item in items if item.get("hit_count", 0) > 0)
    return {
        "session_id": prefetch_payload.get("session_id"),
        "mode": prefetch_payload.get("mode") or "frontend_mock_fixture",
        "generation_schedule_run": prefetch_payload.get("generation_schedule_run"),
        "generation_shared_prefetch_cache_hits": {
            "summary": {
                "schedule_item_count": len(items),
                "shared_record_count": len(shared_records),
                "hit_count": hit_count,
                "hit_status_counts": dict(sorted(hit_status_counts.items())),
                "runtime_ready_count": 0,
                "activation_allowed_count": 0,
                "provider_call_count_by_this_request": 0,
                "world_mutation_count_by_this_request": 0,
            },
            "items": items,
            "safety": {
                "reads_env": False,
                "calls_provider": False,
                "writes_world_state": False,
                "activates_runtime": False,
                "source_read_models": [
                    "generation_prefetch_cache",
                    "generation_shared_prefetch_cache",
                ],
            },
        },
    }
