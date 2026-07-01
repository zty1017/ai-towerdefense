#!/usr/bin/env python3
"""Validate a CompilableObjectPlan v0.1 JSON file."""

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

from validation_common import load_json, scan_forbidden_terms, validate_json_schema  # noqa: E402


SCHEMA_PATH = ROOT / "shared/schemas/compilable_object_plan.v0.1.schema.json"


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


def _check_source_refs(plan: dict[str, Any], errors: list[str]) -> set[str]:
    existing_object_ids: set[str] = set()
    source_refs = as_obj(plan.get("source_refs"))
    for key, ref in source_refs.items():
        if not isinstance(ref, str) or not ref:
            errors.append(f"source_refs.{key} must be a non-empty string")
            continue
        path = _repo_path(ref)
        if not path.is_file():
            errors.append(f"source_refs.{key} references missing file: {ref}")
            continue
        if key == "compilable_object_catalog":
            catalog = load_json(path)
            for obj in as_list(catalog.get("objects")):
                if isinstance(obj, dict) and isinstance(obj.get("object_id"), str):
                    existing_object_ids.add(obj["object_id"])
    return existing_object_ids


def _check_requests(plan: dict[str, Any], existing_object_ids: set[str], errors: list[str]) -> None:
    request_ids: set[str] = set()
    duplicate_request_ids: set[str] = set()
    planned_object_ids: set[str] = set()
    l5_requests: list[str] = []
    for request in as_list(plan.get("object_requests")):
        if not isinstance(request, dict):
            continue
        request_id = request.get("request_id")
        if isinstance(request_id, str):
            if request_id in request_ids:
                duplicate_request_ids.add(request_id)
            request_ids.add(request_id)
        object_id = request.get("requested_object_id")
        if isinstance(object_id, str):
            planned_object_ids.add(object_id)
        if request.get("compile_permission_level") == "L5_engine":
            l5_requests.append(str(request.get("request_id") or object_id or "unknown_request"))

    for request_id in sorted(duplicate_request_ids):
        errors.append(f"duplicate request_id: {request_id}")
    if l5_requests:
        errors.append(f"plan must not request L5_engine objects: {sorted(l5_requests)}")

    available_refs = existing_object_ids | planned_object_ids
    for index, request in enumerate(as_list(plan.get("object_requests"))):
        if not isinstance(request, dict):
            continue
        for dep in as_list(request.get("dependency_refs")):
            if not isinstance(dep, str) or not dep:
                errors.append(f"object_requests[{index}].dependency_refs contains empty dependency")
                continue
            if dep.startswith(("evidence:", "delta:", "runtime_package:", "validator:")):
                continue
            if dep not in available_refs:
                errors.append(
                    f"object_requests[{index}] dependency_ref {dep!r} is not in catalog or this plan"
                )


def _check_summary(plan: dict[str, Any], errors: list[str]) -> None:
    requests = [item for item in as_list(plan.get("object_requests")) if isinstance(item, dict)]
    summary = as_obj(plan.get("summary"))
    if summary.get("request_count") != len(requests):
        errors.append(
            f"summary.request_count mismatch: expected {len(requests)}, got {summary.get('request_count')}"
        )
    requires_llm = sum(1 for item in requests if item.get("requires_llm") is True)
    requires_media = sum(1 for item in requests if item.get("requires_media") is True)
    requires_review = sum(1 for item in requests if item.get("requires_human_review") is True)
    if summary.get("requires_llm_count") != requires_llm:
        errors.append(
            f"summary.requires_llm_count mismatch: expected {requires_llm}, got {summary.get('requires_llm_count')}"
        )
    if summary.get("requires_media_count") != requires_media:
        errors.append(
            f"summary.requires_media_count mismatch: expected {requires_media}, got {summary.get('requires_media_count')}"
        )
    if summary.get("requires_human_review_count") != requires_review:
        errors.append(
            "summary.requires_human_review_count mismatch: "
            f"expected {requires_review}, got {summary.get('requires_human_review_count')}"
        )


def validate_compilable_object_plan(plan: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(plan, dict):
        return ["plan root must be an object"]
    errors.extend(validate_json_schema(plan, SCHEMA_PATH))
    scan_forbidden_terms(plan, "", errors, context="CompilableObjectPlan")
    existing_object_ids = _check_source_refs(plan, errors)
    _check_requests(plan, existing_object_ids, errors)
    _check_summary(plan, errors)
    return _dedupe(errors)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a CompilableObjectPlan v0.1 JSON file.")
    parser.add_argument("plan", help="Path to plan JSON.")
    args = parser.parse_args()

    try:
        plan = load_json(Path(args.plan))
    except FileNotFoundError:
        print("INVALID CompilableObjectPlan")
        print(f"- plan file not found: {args.plan}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID CompilableObjectPlan")
        print(f"- plan is not valid JSON: {exc}")
        return 1

    errors = validate_compilable_object_plan(plan)
    if errors:
        print("INVALID CompilableObjectPlan")
        for error in errors:
            print(f"- {error}")
        return 1

    print("OK CompilableObjectPlan")
    print(f"- plan_id: {plan.get('plan_id')}")
    print(f"- requests: {len(plan.get('object_requests', []))}")
    print(f"- target_stage: {as_obj(plan.get('planning_context')).get('target_stage_id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
