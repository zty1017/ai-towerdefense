#!/usr/bin/env python3
"""Validate a MapStylePack component binding review report."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import procedural_map_render_plan as pmrp  # noqa: E402


DEFAULT_SCHEMA = ROOT / "shared/schemas/map_style_component_binding_report.v0.1.schema.json"
FORBIDDEN_KEY_FRAGMENTS = (
    "provider",
    "model",
    "raw_prompt",
    "full_trace",
    "raw_json",
    "api_key",
    "secret",
    "unreviewed_content",
)
EXTERNAL_URL_MARKERS = ("http://", "https://")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def scan_forbidden_key_fragments(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            lowered = key.lower()
            if any(fragment in lowered for fragment in FORBIDDEN_KEY_FRAGMENTS):
                errors.append(f"forbidden field '{child_path}' is not allowed")
            scan_forbidden_key_fragments(child, child_path, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_forbidden_key_fragments(child, f"{path}[{index}]", errors)


def scan_external_urls(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            scan_external_urls(child, f"{path}.{key}" if path else key, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_external_urls(child, f"{path}[{index}]", errors)
    elif isinstance(value, str):
        lowered = value.lower()
        if any(marker in lowered for marker in EXTERNAL_URL_MARKERS):
            errors.append(f"{path} must not contain an external URL")


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def validate_report(report: dict[str, Any], schema: dict[str, Any] | None = None) -> list[str]:
    errors: list[str] = []
    errors.extend(pmrp.validate_with_jsonschema(report, schema))
    scan_forbidden_key_fragments(report, "", errors)
    scan_external_urls(report, "", errors)

    if report.get("schema_version") != "map_style_component_binding_report.v0.1":
        errors.append("schema_version must be 'map_style_component_binding_report.v0.1'")

    bindings = [item for item in as_list(report.get("bindings")) if isinstance(item, dict)]
    gaps = [item for item in as_list(report.get("coverage_gaps")) if isinstance(item, dict)]
    summary = as_obj(report.get("summary"))
    status_counts = Counter(str(item.get("resolution_status")) for item in bindings)

    expected = {
        "material_component_ref_count": len(
            [item for item in bindings if item.get("binding_source") == "material.component_ref"]
        ),
        "prefab_reviewed_component_ref_count": len(
            [item for item in bindings if item.get("binding_source") == "prefab.visual_ref"]
        ),
        "resolved_ref_count": status_counts.get("resolved", 0),
        "missing_ref_count": status_counts.get("missing", 0),
        "procedural_fallback_count": status_counts.get("procedural_fallback", 0),
        "ambiguous_ref_count": status_counts.get("ambiguous", 0),
        "external_url_rejected_count": status_counts.get("external_url_rejected", 0),
        "component_coverage_gap_count": len(gaps),
    }
    for key, value in expected.items():
        if summary.get(key) != value:
            errors.append(f"summary.{key} must be {value}")
    if as_obj(summary.get("status_counts")) != dict(sorted(status_counts.items())):
        errors.append("summary.status_counts must match binding resolution statuses")

    failed_statuses = {
        "missing",
        "ambiguous",
        "external_url_rejected",
    }
    expected_status = (
        "failed"
        if any(status_counts.get(status, 0) for status in failed_statuses)
        else "warning"
        if gaps
        else "passed"
    )
    if report.get("status") != expected_status:
        errors.append(f"status must be {expected_status!r} based on binding results")

    usage_policy = set(map(str, as_list(report.get("usage_policy"))))
    for required in (
        "review_gate_only",
        "not_runtime_semantic_source",
        "no_image_to_map_semantic_inference",
        "no_external_temporary_url_pass",
    ):
        if required not in usage_policy:
            errors.append(f"usage_policy must include {required}")

    for binding in bindings:
        status = binding.get("resolution_status")
        resolved_ref = binding.get("resolved_ref")
        if status == "resolved" and not isinstance(resolved_ref, dict):
            errors.append(f"{binding.get('owner_id')}: resolved binding must include resolved_ref")
        if status != "resolved" and resolved_ref is not None:
            errors.append(f"{binding.get('owner_id')}: unresolved binding must not include resolved_ref")
        if binding.get("binding_source") == "procedural_fallback" and binding.get("ref") is not None:
            errors.append(f"{binding.get('owner_id')}: procedural fallback binding must not have ref")
        if binding.get("binding_source") == "prefab.visual_ref" and not binding.get("ref"):
            errors.append(f"{binding.get('owner_id')}: reviewed prefab binding must have ref")

    return list(dict.fromkeys(errors))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a MapStylePack component binding report."
    )
    parser.add_argument("report", help="Report JSON path.")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA), help="Optional schema path.")
    args = parser.parse_args()

    report_path = Path(args.report)
    schema_path = Path(args.schema)
    try:
        report = load_json(report_path)
    except FileNotFoundError:
        print("INVALID MapStyleComponentBindingReport")
        print(f"- report file not found: {report_path}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID MapStyleComponentBindingReport")
        print(f"- report is not valid JSON: {exc}")
        return 1

    if not isinstance(report, dict):
        print("INVALID MapStyleComponentBindingReport")
        print("- report root must be an object")
        return 1

    schema = load_json(schema_path) if schema_path.exists() else None
    if not isinstance(schema, dict):
        schema = None
    errors = validate_report(report, schema)
    if errors:
        print("INVALID MapStyleComponentBindingReport")
        for error in errors:
            print(f"- {error}")
        return 1

    summary = as_obj(report.get("summary"))
    print(f"OK: {report_path}")
    print(f"- status: {report.get('status')}")
    print(f"- style_pack_count: {summary.get('style_pack_count')}")
    print(f"- resolved_ref_count: {summary.get('resolved_ref_count')}")
    print(f"- procedural_fallback_count: {summary.get('procedural_fallback_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
