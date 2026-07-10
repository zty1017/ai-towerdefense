#!/usr/bin/env python3
"""Validate BattleVisualSmokeReport v0.1 files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from report_io import load_json_object


SCHEMA_VERSION = "battle_visual_smoke_report.v0.1"
EXPECTED_VIEWPORTS = {"desktop", "mobile"}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_screenshot(item: dict[str, Any]) -> None:
    viewport_id = str(item.get("viewport_id") or "")
    require(
        viewport_id in EXPECTED_VIEWPORTS,
        f"screenshot viewport_id must be one of {sorted(EXPECTED_VIEWPORTS)}: {viewport_id!r}",
    )
    require(item.get("status") == "captured", f"screenshot status is {item.get('status')}")
    path = Path(str(item.get("path") or ""))
    require(path.exists(), f"screenshot file missing: {path}")
    require(path.suffix.lower() == ".png", f"screenshot must be PNG: {path}")
    require(int_value(item.get("width")) > 0, f"screenshot width invalid: {path}")
    require(int_value(item.get("height")) > 0, f"screenshot height invalid: {path}")
    require(int_value(item.get("file_size_bytes")) > 5000, f"screenshot file too small: {path}")
    require(bool(item.get("sha256")), f"screenshot sha256 missing: {path}")


def validate_captured(report: dict[str, Any]) -> None:
    require(report.get("browser_available") is True, "captured report requires browser")
    screenshots = as_list(report.get("screenshots"))
    observed = {
        str(item.get("viewport_id"))
        for item in screenshots
        if isinstance(item, dict)
    }
    require(
        observed == EXPECTED_VIEWPORTS,
        f"captured report must cover viewports {sorted(EXPECTED_VIEWPORTS)}: got {sorted(observed)}",
    )
    require(
        len(screenshots) == len(EXPECTED_VIEWPORTS),
        f"screenshot count must be {len(EXPECTED_VIEWPORTS)}",
    )
    for item in screenshots:
        if not isinstance(item, dict):
            raise ValueError("screenshots entries must be objects")
        validate_screenshot(item)
    require(not as_list(report.get("failures")), "captured report must have no failures")


def validate_unavailable(report: dict[str, Any], allow_unavailable: bool) -> None:
    require(allow_unavailable, "browser_unavailable requires --allow-unavailable")
    require(report.get("browser_available") is False, "unavailable report must not have browser")
    require(not as_list(report.get("screenshots")), "unavailable report must not contain screenshots")
    require(as_list(report.get("failures")), "unavailable report must explain failure")


def validate(report: dict[str, Any], allow_unavailable: bool) -> None:
    require(report.get("schema_version") == SCHEMA_VERSION, "schema_version mismatch")
    status = report.get("status")
    if status == "captured":
        validate_captured(report)
    elif status == "browser_unavailable":
        validate_unavailable(report, allow_unavailable)
    else:
        raise ValueError(f"unsupported or failed report status: {status}")


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
        print(f"battle visual smoke report validation failed: {exc}", file=sys.stderr)
        return 1
    print(f"battle visual smoke report validation passed: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
