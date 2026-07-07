#!/usr/bin/env python3
"""Validate FrontendMultinodeVisualSmokeReport v0.1 files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from report_io import load_json_object


SCHEMA_VERSION = "frontend_multinode_visual_smoke_report.v0.1"
EXPECTED_NODES = {
    "gray_lantern_station": "灰灯驿站",
    "lamp_wick_store": "灯芯仓",
    "old_signal_tower": "旧信号塔",
}
EXPECTED_VIEWPORTS = {"desktop", "mobile"}

def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_safety(report: dict[str, Any]) -> None:
    safety = as_obj(report.get("safety_summary"))
    require(safety.get("reads_env_file") is False, "report must not read env files")
    require(
        int(safety.get("provider_call_count") or 0) == 0,
        "report must not call providers",
    )
    require(
        int(safety.get("world_mutation_count") or 0) == 0,
        "report must not mutate world state",
    )
    require(
        safety.get("runtime_activation_allowed") is False,
        "report must not activate runtime artifacts",
    )
    require(
        safety.get("stores_provider_body") is False,
        "report must not store provider bodies",
    )


def validate_captured(report: dict[str, Any]) -> None:
    require(report.get("browser_available") is True, "captured report requires browser")
    node_ids = set(as_list(report.get("node_ids")))
    viewport_ids = set(as_list(report.get("viewport_ids")))
    require(node_ids == set(EXPECTED_NODES), f"unexpected node ids: {sorted(node_ids)}")
    require(viewport_ids == EXPECTED_VIEWPORTS, f"unexpected viewports: {sorted(viewport_ids)}")

    expected_count = len(EXPECTED_NODES) * len(EXPECTED_VIEWPORTS)
    require(
        int(report.get("expected_screenshot_count") or 0) == expected_count,
        f"expected screenshot count must be {expected_count}",
    )
    require(
        int(report.get("captured_screenshot_count") or 0) == expected_count,
        f"captured screenshot count must be {expected_count}",
    )
    screenshots = as_list(report.get("screenshots"))
    require(len(screenshots) == expected_count, f"screenshots must include {expected_count} entries")
    observed = {
        (item.get("node_id"), item.get("viewport_id"))
        for item in screenshots
        if isinstance(item, dict)
    }
    expected = {
        (node_id, viewport_id)
        for node_id in EXPECTED_NODES
        for viewport_id in EXPECTED_VIEWPORTS
    }
    require(observed == expected, "screenshot matrix is incomplete")

    for item in screenshots:
        if not isinstance(item, dict):
            raise ValueError("screenshots entries must be objects")
        path = Path(str(item.get("path") or ""))
        require(path.exists(), f"screenshot path missing: {path}")
        require(path.suffix.lower() == ".png", f"screenshot must be PNG: {path}")
        require(int(item.get("width") or 0) > 0, f"screenshot width invalid: {path}")
        require(int(item.get("height") or 0) > 0, f"screenshot height invalid: {path}")
        require(
            int(item.get("file_size_bytes") or 0) > 5000,
            f"screenshot file too small: {path}",
        )
        require(bool(item.get("sha256")), f"screenshot sha256 missing: {path}")
        require(
            int(item.get("canvas_count") or 0) >= 1,
            f"screenshot must contain the battle canvas: {path}",
        )
        require(
            int(item.get("battle_canvas_client_width") or 0) > 0,
            f"battle canvas client width invalid: {path}",
        )
        require(
            int(item.get("battle_canvas_client_height") or 0) > 0,
            f"battle canvas client height invalid: {path}",
        )
        node_id = str(item.get("node_id") or "")
        node_title = str(item.get("node_title") or "")
        expected_label = EXPECTED_NODES.get(node_id, "")
        require(
            expected_label in node_title,
            f"node title {node_title!r} does not include expected label {expected_label!r}",
        )
    require(not as_list(report.get("failures")), "captured report must have no failures")


def validate_unavailable(report: dict[str, Any], allow_unavailable: bool) -> None:
    require(allow_unavailable, "browser_unavailable requires --allow-unavailable")
    require(report.get("browser_available") is False, "unavailable report must not have browser")
    require(not as_list(report.get("screenshots")), "unavailable report must not contain screenshots")
    require(as_list(report.get("failures")), "unavailable report must explain failure")


def validate(report: dict[str, Any], allow_unavailable: bool) -> None:
    require(report.get("schema_version") == SCHEMA_VERSION, "schema_version mismatch")
    validate_safety(report)
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
        print(f"frontend multinode visual smoke report validation failed: {exc}", file=sys.stderr)
        return 1
    print(f"frontend multinode visual smoke report validation passed: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
