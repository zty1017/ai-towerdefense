#!/usr/bin/env python3
"""Validate a GenerationSchedulePlan v0.1 JSON file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ASSET_GRAPH_DIR = ROOT / "tools" / "asset_graph"
if str(ASSET_GRAPH_DIR) not in sys.path:
    sys.path.insert(0, str(ASSET_GRAPH_DIR))

from validation_common import load_json, validate_json_schema  # noqa: E402


SCHEMA_PATH = ROOT / "shared/schemas/generation_schedule_plan.v0.1.schema.json"

FORBIDDEN_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "secret",
    "password",
    "auth_token",
    "access_token",
    "refresh_token",
    "raw_prompt",
    "full_prompt",
    "provider_response",
    "raw_response",
    "raw_json",
    "full_trace",
    "unreviewed_content",
)

PLAYER_VISIBLE_TECH_TERMS = (
    "provider",
    "prompt",
    "schema",
    "api key",
    "raw trace",
    "raw json",
)


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _repo_path(ref: str) -> Path:
    path = Path(ref)
    return path if path.is_absolute() else ROOT / ref


def _dedupe(errors: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for error in errors:
        if error not in seen:
            seen.add(error)
            out.append(error)
    return out


def _scan_forbidden_keys(value: Any, errors: list[str], path: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            lowered = key.lower()
            if any(fragment in lowered for fragment in FORBIDDEN_KEY_FRAGMENTS):
                errors.append(f"forbidden key in GenerationSchedulePlan: {child_path}")
            _scan_forbidden_keys(child, errors, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan_forbidden_keys(child, errors, f"{path}[{index}]")
    elif isinstance(value, str):
        lowered = value.lower()
        for fragment in FORBIDDEN_KEY_FRAGMENTS:
            if fragment in lowered:
                errors.append(f"forbidden string fragment {fragment!r} at {path}")


def _scan_player_visible_text(item: dict[str, Any], errors: list[str]) -> None:
    if item.get("player_visible") is not True:
        return
    visible_values = [
        str(item.get("purpose") or ""),
        str(as_obj(item.get("trigger")).get("description") or ""),
    ]
    for value in visible_values:
        lowered = value.lower()
        for term in PLAYER_VISIBLE_TECH_TERMS:
            if term in lowered:
                errors.append(
                    f"{item.get('schedule_item_id')} player-visible text leaks technical term {term!r}"
                )


def _check_source_refs(plan: dict[str, Any], errors: list[str]) -> None:
    source_refs = as_obj(plan.get("source_refs"))
    for key, ref in source_refs.items():
        if isinstance(ref, str):
            if not _repo_path(ref).is_file():
                errors.append(f"source_refs.{key} references missing file: {ref}")
        elif isinstance(ref, list):
            for index, item in enumerate(ref):
                if not isinstance(item, str) or not item:
                    errors.append(f"source_refs.{key}[{index}] must be a non-empty string")
                    continue
                if not _repo_path(item).is_file():
                    errors.append(f"source_refs.{key}[{index}] references missing file: {item}")


def _check_items(plan: dict[str, Any], errors: list[str]) -> None:
    items = [item for item in as_list(plan.get("items")) if isinstance(item, dict)]
    ids: set[str] = set()
    compile_ids: set[str] = set()
    duplicate_ids: set[str] = set()
    duplicate_compile_ids: set[str] = set()

    for item in items:
        item_id = item.get("schedule_item_id")
        compile_request_id = item.get("compile_request_id")
        if isinstance(item_id, str):
            if item_id in ids:
                duplicate_ids.add(item_id)
            ids.add(item_id)
        if isinstance(compile_request_id, str):
            if compile_request_id in compile_ids:
                duplicate_compile_ids.add(compile_request_id)
            compile_ids.add(compile_request_id)

    for item_id in sorted(duplicate_ids):
        errors.append(f"duplicate schedule_item_id: {item_id}")
    for compile_id in sorted(duplicate_compile_ids):
        errors.append(f"duplicate compile_request_id: {compile_id}")

    for index, item in enumerate(items):
        item_id = str(item.get("schedule_item_id") or f"items[{index}]")
        latency = item.get("latency_class")
        status = item.get("status")
        provider_policy = as_obj(item.get("provider_policy"))
        commit_policy = as_obj(item.get("commit_policy"))
        fallback_ref = item.get("fallback_ref")

        for dep in as_list(item.get("dependencies")):
            if dep not in ids:
                errors.append(f"{item_id} dependency {dep!r} does not reference a schedule_item_id")

        if latency == "sync_blocking":
            if status not in {"ready", "cached", "fallback_ready"}:
                errors.append(f"{item_id} sync_blocking item must already be ready/cached/fallback_ready")
            if not isinstance(fallback_ref, str) or not fallback_ref:
                errors.append(f"{item_id} sync_blocking item must declare fallback_ref")
            if provider_policy.get("mode") != "no_live_provider":
                errors.append(f"{item_id} sync_blocking item must not require live provider calls")

        if latency == "fallback_static":
            if provider_policy.get("mode") != "no_live_provider":
                errors.append(f"{item_id} fallback_static item must not require live provider calls")
            if status not in {"ready", "fallback_ready", "cached"}:
                errors.append(f"{item_id} fallback_static item must be ready, cached, or fallback_ready")

        if latency in {"background_prefetch", "background", "lazy"}:
            if commit_policy.get("world_commit") == "direct_world_commit":
                errors.append(f"{item_id} non-blocking item must not direct-commit world state")
            if commit_policy.get("runtime_activation") == "already_active":
                errors.append(f"{item_id} non-blocking item must not claim already_active runtime state")

        world_commit = commit_policy.get("world_commit")
        if world_commit in {"world_delta_semantic_gate", "manual_review_required"}:
            gates = " ".join(str(gate).lower() for gate in as_list(item.get("validation_gates")))
            if "world_delta" not in gates and "semantic" not in gates:
                errors.append(f"{item_id} world commit item must include WorldStateDelta/semantic gate")
            if commit_policy.get("revalidate_before_activation") is not True:
                errors.append(f"{item_id} world commit item must revalidate before activation")

        _scan_player_visible_text(item, errors)


def _check_summary(plan: dict[str, Any], errors: list[str]) -> None:
    items = [item for item in as_list(plan.get("items")) if isinstance(item, dict)]
    summary = as_obj(plan.get("summary"))
    latency_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    for item in items:
        latency = str(item.get("latency_class") or "")
        status = str(item.get("status") or "")
        latency_counts[latency] = latency_counts.get(latency, 0) + 1
        status_counts[status] = status_counts.get(status, 0) + 1

    expected = {
        "item_count": len(items),
        "sync_blocking_count": latency_counts.get("sync_blocking", 0),
        "background_prefetch_count": latency_counts.get("background_prefetch", 0),
        "background_count": latency_counts.get("background", 0),
        "lazy_count": latency_counts.get("lazy", 0),
        "fallback_static_count": latency_counts.get("fallback_static", 0),
        "live_provider_allowed_count": sum(
            1
            for item in items
            if as_obj(item.get("provider_policy")).get("mode") != "no_live_provider"
        ),
        "world_commit_gate_count": sum(
            1
            for item in items
            if as_obj(item.get("commit_policy")).get("world_commit")
            in {"world_delta_semantic_gate", "manual_review_required"}
        ),
        "fallback_covered_count": sum(1 for item in items if item.get("fallback_ref")),
    }
    for key, value in expected.items():
        if summary.get(key) != value:
            errors.append(f"summary.{key} mismatch: expected {value}, got {summary.get(key)}")
    if as_obj(summary.get("latency_class_counts")) != latency_counts:
        errors.append("summary.latency_class_counts mismatch")
    if as_obj(summary.get("status_counts")) != status_counts:
        errors.append("summary.status_counts mismatch")


def _check_validation_commands(plan: dict[str, Any], errors: list[str]) -> None:
    for index, command in enumerate(as_list(plan.get("validation_commands"))):
        text = str(as_obj(command).get("command") or "")
        if ".env" in text:
            errors.append(f"validation_commands[{index}] must not read .env")


def validate_generation_schedule_plan(plan: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(plan, dict):
        return ["plan root must be an object"]
    errors.extend(validate_json_schema(plan, SCHEMA_PATH))
    _scan_forbidden_keys(plan, errors)
    _check_source_refs(plan, errors)
    _check_items(plan, errors)
    _check_summary(plan, errors)
    _check_validation_commands(plan, errors)
    return _dedupe(errors)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a GenerationSchedulePlan v0.1 JSON file.")
    parser.add_argument("plan", help="Path to plan JSON.")
    args = parser.parse_args()

    try:
        plan = load_json(Path(args.plan))
    except FileNotFoundError:
        print("INVALID GenerationSchedulePlan")
        print(f"- plan file not found: {args.plan}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID GenerationSchedulePlan")
        print(f"- plan is not valid JSON: {exc}")
        return 1

    errors = validate_generation_schedule_plan(plan)
    if errors:
        print("INVALID GenerationSchedulePlan")
        for error in errors:
            print(f"- {error}")
        return 1

    summary = as_obj(plan.get("summary"))
    print("OK GenerationSchedulePlan")
    print(f"- plan_id: {plan.get('plan_id')}")
    print(f"- items: {summary.get('item_count')}")
    print(f"- latency: {summary.get('latency_class_counts')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
