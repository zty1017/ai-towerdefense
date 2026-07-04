#!/usr/bin/env python3
"""Validate LoopContinuityReport v0.1."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPORT_VERSION = "loop_continuity_report.v0.1"
ALLOWED_STATUS = {"passed", "passed_with_warnings", "failed", "skipped_static"}
ALLOWED_SOURCE_KINDS = {
    "single_frame_static",
    "deterministic_frame_sequence",
    "video_keyframe_sequence",
    "unknown",
}
FORBIDDEN_KEYS = {
    "provider",
    "model",
    "raw_prompt",
    "full_trace",
    "raw_json",
    "api_key",
    "secret",
    "unreviewed_content",
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def scan_forbidden(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key in FORBIDDEN_KEYS:
                errors.append(f"forbidden key: {child_path}")
            scan_forbidden(child, child_path, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_forbidden(child, f"{path}[{index}]", errors)


def validate(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("report_version") != REPORT_VERSION:
        errors.append(f"report_version must be {REPORT_VERSION}")
    if not isinstance(report.get("report_id"), str) or not report.get("report_id"):
        errors.append("report_id must be non-empty string")
    if not isinstance(report.get("atlas_ref"), str) or not report.get("atlas_ref"):
        errors.append("atlas_ref must be non-empty string")
    if report.get("status") not in {"passed", "passed_with_warnings", "failed"}:
        errors.append("status must be passed, passed_with_warnings, or failed")
    summary = report.get("summary")
    items = report.get("items")
    if not isinstance(summary, dict):
        errors.append("summary must be object")
        summary = {}
    if not isinstance(items, list):
        errors.append("items must be array")
        items = []

    counts = {key: 0 for key in ALLOWED_STATUS}
    animated_checked = 0
    seen_ids: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"items[{index}] must be object")
            continue
        animation_id = item.get("animation_id")
        if not isinstance(animation_id, str) or not animation_id:
            errors.append(f"items[{index}].animation_id must be non-empty string")
        elif animation_id in seen_ids:
            errors.append(f"duplicate animation_id: {animation_id}")
        else:
            seen_ids.add(animation_id)
        status = item.get("status")
        if status not in ALLOWED_STATUS:
            errors.append(f"items[{index}].status is invalid")
        else:
            counts[status] += 1
        source_kind = item.get("frame_source_kind")
        if source_kind not in ALLOWED_SOURCE_KINDS:
            errors.append(f"items[{index}].frame_source_kind is invalid")
        frame_count = item.get("frame_count")
        if not isinstance(frame_count, int) or frame_count < 1:
            errors.append(f"items[{index}].frame_count must be positive integer")
        if status != "skipped_static":
            animated_checked += 1
            metrics = item.get("metrics")
            if not isinstance(metrics, dict):
                errors.append(f"items[{index}].metrics must be object")
            else:
                for key in ("bbox_delta_ratio", "anchor_delta", "alpha_coverage_delta", "mean_rgba_delta"):
                    value = metrics.get(key)
                    if not isinstance(value, (int, float)) or value < 0:
                        errors.append(f"items[{index}].metrics.{key} must be non-negative number")
        for field in ("issues", "warnings"):
            value = item.get(field)
            if not isinstance(value, list) or any(not isinstance(entry, str) for entry in value):
                errors.append(f"items[{index}].{field} must be string array")

    if summary:
        expected = {
            "animation_count": len(items),
            "checked_count": animated_checked,
            "passed_count": counts["passed"],
            "passed_with_warnings_count": counts["passed_with_warnings"],
            "failed_count": counts["failed"],
            "skipped_static_count": counts["skipped_static"],
        }
        for key, value in expected.items():
            if summary.get(key) != value:
                errors.append(f"summary.{key} mismatch: expected {value}, got {summary.get(key)}")
        frame_source_counts = summary.get("frame_source_counts")
        if not isinstance(frame_source_counts, dict) or not frame_source_counts:
            errors.append("summary.frame_source_counts must be non-empty object")
    if counts["failed"] and report.get("status") != "failed":
        errors.append("report.status must be failed when any item failed")
    if counts["failed"] == 0 and report.get("status") == "failed":
        errors.append("report.status must not be failed when no item failed")
    if counts["failed"] == 0 and counts["passed_with_warnings"] and report.get("status") != "passed_with_warnings":
        errors.append("report.status must be passed_with_warnings when warnings exist and no failures")
    if counts["failed"] == 0 and counts["passed_with_warnings"] == 0 and report.get("status") != "passed":
        errors.append("report.status must be passed when no failures or warnings exist")
    scan_forbidden(report, "", errors)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report")
    args = parser.parse_args()
    data = load_json(Path(args.report))
    if not isinstance(data, dict):
        print("INVALID LoopContinuityReport")
        print("- root must be object")
        return 1
    errors = validate(data)
    if errors:
        print("INVALID LoopContinuityReport")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"OK: {args.report}")
    print(f"- status: {data.get('status')}")
    print(f"- checked: {data.get('summary', {}).get('checked_count')}")
    print(f"- warnings: {data.get('summary', {}).get('passed_with_warnings_count')}")
    print(f"- failed: {data.get('summary', {}).get('failed_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
