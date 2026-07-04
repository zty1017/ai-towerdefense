#!/usr/bin/env python3
"""Validate a GenerationScheduleRunReport v0.1 JSON file."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ASSET_GRAPH_DIR = ROOT / "tools" / "asset_graph"
if str(ASSET_GRAPH_DIR) not in sys.path:
    sys.path.insert(0, str(ASSET_GRAPH_DIR))

from validation_common import load_json, validate_json_schema  # noqa: E402


SCHEMA_PATH = ROOT / "shared/schemas/generation_schedule_run_report.v0.1.schema.json"

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


def _scan_forbidden(value: Any, errors: list[str], path: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            lowered = key.lower()
            if any(fragment in lowered for fragment in FORBIDDEN_KEY_FRAGMENTS):
                errors.append(f"forbidden key in GenerationScheduleRunReport: {child_path}")
            _scan_forbidden(child, errors, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan_forbidden(child, errors, f"{path}[{index}]")
    elif isinstance(value, str):
        lowered = value.lower()
        for fragment in FORBIDDEN_KEY_FRAGMENTS:
            if fragment in lowered:
                errors.append(f"forbidden string fragment {fragment!r} at {path}")


def _check_source_plan(report: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    source = as_obj(report.get("source_refs")).get("generation_schedule_plan")
    if not isinstance(source, str) or not source:
        errors.append("source_refs.generation_schedule_plan must be a non-empty string")
        return {}
    path = _repo_path(source)
    if not path.is_file():
        errors.append(f"source_refs.generation_schedule_plan references missing file: {source}")
        return {}
    try:
        plan = load_json(path)
    except Exception as exc:
        errors.append(f"cannot load generation schedule plan: {exc}")
        return {}
    return plan if isinstance(plan, dict) else {}


def _check_items_against_plan(report: dict[str, Any], plan: dict[str, Any], errors: list[str]) -> None:
    report_items = [item for item in as_list(report.get("items")) if isinstance(item, dict)]
    plan_items = [item for item in as_list(plan.get("items")) if isinstance(item, dict)]
    plan_ids = {
        str(item.get("schedule_item_id"))
        for item in plan_items
        if isinstance(item.get("schedule_item_id"), str)
    }
    report_ids = [
        str(item.get("schedule_item_id"))
        for item in report_items
        if isinstance(item.get("schedule_item_id"), str)
    ]
    if set(report_ids) != plan_ids:
        errors.append("report items must match generation schedule plan item ids exactly")
    duplicates = [item_id for item_id, count in Counter(report_ids).items() if count > 1]
    for item_id in sorted(duplicates):
        errors.append(f"duplicate report schedule_item_id: {item_id}")

    for item in report_items:
        item_id = str(item.get("schedule_item_id") or "unknown")
        if item.get("provider_call_planned") is not False:
            errors.append(f"{item_id} must not plan provider calls in dry-run report")
        if item.get("world_mutation_performed") is not False:
            errors.append(f"{item_id} must not mutate world state in dry-run report")
        if item.get("action") == "blocked" and item.get("dependencies_satisfied") is True:
            errors.append(f"{item_id} blocked action must have unsatisfied dependencies")


def _check_summary(report: dict[str, Any], errors: list[str]) -> None:
    items = [item for item in as_list(report.get("items")) if isinstance(item, dict)]
    summary = as_obj(report.get("summary"))
    action_counts = Counter(str(item.get("action") or "") for item in items)
    status_counts = Counter(str(item.get("result_status") or "") for item in items)
    expected = {
        "item_count": len(items),
        "ready_reused_count": action_counts.get("reuse_ready", 0),
        "fallback_selected_count": action_counts.get("select_fallback", 0),
        "scheduled_count": sum(
            action_counts.get(action, 0)
            for action in ["schedule_prefetch", "schedule_background", "schedule_lazy"]
        ),
        "blocked_count": action_counts.get("blocked", 0),
        "provider_call_count": 0,
        "world_mutation_count": 0,
    }
    for key, value in expected.items():
        if summary.get(key) != value:
            errors.append(f"summary.{key} mismatch: expected {value}, got {summary.get(key)}")
    if as_obj(summary.get("action_counts")) != dict(sorted(action_counts.items())):
        errors.append("summary.action_counts mismatch")
    if as_obj(summary.get("status_counts")) != dict(sorted(status_counts.items())):
        errors.append("summary.status_counts mismatch")


def validate_generation_schedule_run_report(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(report, dict):
        return ["report root must be an object"]
    errors.extend(validate_json_schema(report, SCHEMA_PATH))
    _scan_forbidden(report, errors)
    policy = as_obj(report.get("execution_policy"))
    if any(policy.get(key) is not False for key in policy):
        errors.append("execution_policy values must all be false for v0.1 dry-run report")
    plan = _check_source_plan(report, errors)
    if plan:
        _check_items_against_plan(report, plan, errors)
    _check_summary(report, errors)
    return _dedupe(errors)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a GenerationScheduleRunReport v0.1 JSON file.")
    parser.add_argument("report", help="Path to run report JSON.")
    args = parser.parse_args()

    try:
        report = load_json(Path(args.report))
    except FileNotFoundError:
        print("INVALID GenerationScheduleRunReport")
        print(f"- report file not found: {args.report}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID GenerationScheduleRunReport")
        print(f"- report is not valid JSON: {exc}")
        return 1

    errors = validate_generation_schedule_run_report(report)
    if errors:
        print("INVALID GenerationScheduleRunReport")
        for error in errors:
            print(f"- {error}")
        return 1

    summary = as_obj(report.get("summary"))
    print("OK GenerationScheduleRunReport")
    print(f"- report_id: {report.get('report_id')}")
    print(f"- items: {summary.get('item_count')}")
    print(f"- actions: {summary.get('action_counts')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
