#!/usr/bin/env python3
"""Validate StrategicMapInteractionSmokeReport v0.1 files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from report_io import load_json_object


SCHEMA_VERSION = "strategic_map_interaction_smoke_report.v0.1"
EXPECTED_VIEWPORTS = {"desktop", "mobile"}
EXPECTED_CHECKS = {
    "initial_snapshot_valid",
    "zoom_reduces_view_box",
    "drag_changes_camera_center",
    "drag_class_released",
    "reset_restores_auto_camera",
}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def valid_view_box(snapshot: dict[str, Any]) -> bool:
    values = snapshot.get("viewBox")
    return isinstance(values, list) and len(values) == 4 and all(isinstance(value, (int, float)) for value in values)


def validate_safety(report: dict[str, Any]) -> None:
    safety = as_obj(report.get("safety_summary"))
    require(safety.get("reads_env_file") is False, "report must not read env files")
    require(int_value(safety.get("provider_call_count")) == 0, "report must not call providers")
    require(int_value(safety.get("world_mutation_count")) == 0, "report must not mutate world state")
    require(safety.get("runtime_activation_allowed") is False, "report must not activate runtime artifacts")
    require(safety.get("stores_provider_body") is False, "report must not store provider bodies")


def validate_interaction(item: dict[str, Any]) -> None:
    viewport_id = str(item.get("viewport_id") or "")
    require(item.get("status") == "passed", f"{viewport_id} interaction did not pass")
    checks = as_obj(item.get("checks"))
    require(set(checks) == EXPECTED_CHECKS, f"{viewport_id} check set mismatch")
    require(all(value is True for value in checks.values()), f"{viewport_id} has a failed camera check")
    for phase in ("initial", "zoomed", "dragged", "reset"):
        require(valid_view_box(as_obj(item.get(phase))), f"{viewport_id} {phase} viewBox invalid")
    screenshots = as_list(item.get("screenshots"))
    require(len(screenshots) == 3, f"{viewport_id} must include three screenshots")
    require({entry.get("phase") for entry in screenshots if isinstance(entry, dict)} == {"initial", "dragged", "reset"}, f"{viewport_id} screenshot phases mismatch")
    for screenshot in screenshots:
        require(isinstance(screenshot, dict), f"{viewport_id} screenshot must be an object")
        path = Path(str(screenshot.get("path") or ""))
        require(path.exists(), f"screenshot missing: {path}")
        require(path.suffix.lower() == ".png", f"screenshot must be PNG: {path}")
        require(int_value(screenshot.get("width")) > 0, f"screenshot width invalid: {path}")
        require(int_value(screenshot.get("height")) > 0, f"screenshot height invalid: {path}")
        require(int_value(screenshot.get("file_size_bytes")) > 5000, f"screenshot file too small: {path}")
        require(bool(screenshot.get("sha256")), f"screenshot sha256 missing: {path}")


def validate(report: dict[str, Any], allow_unavailable: bool) -> None:
    require(report.get("schema_version") == SCHEMA_VERSION, "schema_version mismatch")
    validate_safety(report)
    if report.get("status") == "browser_unavailable":
        require(allow_unavailable, "browser_unavailable requires --allow-unavailable")
        require(report.get("browser_available") is False, "unavailable report must not have browser")
        require(as_list(report.get("failures")), "unavailable report must explain failure")
        return
    require(report.get("status") == "captured", f"unsupported or failed report status: {report.get('status')}")
    require(report.get("browser_available") is True, "captured report requires browser")
    interactions = as_list(report.get("interactions"))
    viewport_ids = {item.get("viewport_id") for item in interactions if isinstance(item, dict)}
    require(viewport_ids == EXPECTED_VIEWPORTS, f"unexpected viewports: {sorted(viewport_ids)}")
    require(int_value(report.get("expected_interaction_count")) == 2, "expected interaction count must be 2")
    require(int_value(report.get("passed_interaction_count")) == 2, "passed interaction count must be 2")
    require(int_value(report.get("captured_screenshot_count")) == 6, "captured screenshot count must be 6")
    require(not as_list(report.get("failures")), "captured report must have no failures")
    for item in interactions:
        require(isinstance(item, dict), "interaction entries must be objects")
        validate_interaction(item)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--allow-unavailable", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        validate(load_json_object(args.report, label="report root"), args.allow_unavailable)
    except Exception as exc:  # noqa: BLE001 - CLI validator should be concise.
        print(f"strategic map interaction smoke report validation failed: {exc}", file=sys.stderr)
        return 1
    print(f"strategic map interaction smoke report validation passed: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
