#!/usr/bin/env python3
"""Validate BattleDragInteractionSmokeReport v0.1 files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from report_io import load_json_object


SCHEMA_VERSION = "battle_drag_interaction_smoke_report.v0.1"
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


def validate_safety(report: dict[str, Any]) -> None:
    safety = as_obj(report.get("safety_summary"))
    require(safety.get("reads_env_file") is False, "report must not read env files")
    require(int_value(safety.get("provider_call_count")) == 0, "report must not call providers")
    require(int_value(safety.get("world_mutation_count")) == 0, "report must not mutate world state")
    require(safety.get("runtime_activation_allowed") is False, "report must not activate runtime artifacts")
    require(safety.get("stores_provider_body") is False, "report must not store provider bodies")


def deployment_entity_count(snapshot: dict[str, Any]) -> int:
    return sum(int_value(snapshot.get(field)) for field in ("defensesCount", "trapsCount", "effectsCount"))


def validate_interaction(item: dict[str, Any], tool: str) -> None:
    path = Path(str(item.get("path") or ""))
    require(item.get("status") == "passed", f"interaction status is {item.get('status')}")
    require(path.exists(), f"interaction screenshot missing: {path}")
    require(path.suffix.lower() == ".png", f"interaction screenshot must be PNG: {path}")
    require(int_value(item.get("width")) > 0, f"screenshot width invalid: {path}")
    require(int_value(item.get("height")) > 0, f"screenshot height invalid: {path}")
    require(int_value(item.get("file_size_bytes")) > 5000, f"screenshot file too small: {path}")
    require(bool(item.get("sha256")), f"screenshot sha256 missing: {path}")
    source = as_obj(item.get("source"))
    target = as_obj(item.get("target"))
    before = as_obj(item.get("before"))
    preview = as_obj(item.get("preview"))
    preview_snapshot = as_obj(preview.get("snapshot"))
    after = as_obj(item.get("after"))
    require(item.get("tool") == tool, f"interaction tool mismatch: {item.get('tool')!r}")
    require(source.get("ok") is True, "tool source missing")
    require(int_value(source.get("client_x")) > 0 and int_value(source.get("client_y")) > 0, "tool source coordinates invalid")
    require(int_value(target.get("client_x")) > 0 and int_value(target.get("client_y")) > 0, "deployment target coordinates invalid")
    require(before.get("ok") is True and after.get("ok") is True, "smoke probe snapshots must be ok")
    preview_path = Path(str(preview.get("path") or ""))
    require(preview_path.exists(), f"drag preview screenshot missing: {preview_path}")
    require(int_value(preview.get("file_size_bytes")) > 5000, f"drag preview screenshot too small: {preview_path}")
    require(preview_snapshot.get("draggingTool") == tool, "drag preview must retain the requested tool")
    require(bool(as_obj(preview_snapshot.get("hoverCell"))), "drag preview must be snapped to a battlefield cell")
    require(before.get("mode") == "battleVisualSmoke", "before snapshot not in battle smoke mode")
    require(after.get("mode") == "battleVisualSmoke", "after snapshot not in battle smoke mode")
    require(before.get("requestedTool") == tool, "before snapshot requested tool mismatch")
    require(after.get("requestedTool") == tool, "after snapshot requested tool mismatch")
    require(
        deployment_entity_count(after) > deployment_entity_count(before),
        "battle entity count did not increase after drag",
    )
    require(
        int_value(after.get("deployedAssetCount")) > int_value(before.get("deployedAssetCount")),
        "deployed asset count did not increase after drag",
    )
    require(
        int_value(after.get("resources")) < int_value(before.get("resources"))
        or int_value(after.get("power")) < int_value(before.get("power"))
        or (
            tool == "sample"
            and int_value(after.get("sampleUses")) < int_value(before.get("sampleUses"))
        ),
        "neither deployment resources nor delivered sample charges decreased after drag",
    )
    if tool == "basic":
        require(
            int_value(after.get("basicUses")) < int_value(before.get("basicUses")),
            "basic tool use count did not decrease after drag",
        )
    require("已" in str(after.get("toast") or ""), "after-drag toast should be player-facing deployment feedback")
    require(after.get("selectedTool") is None, "successful drag must consume the selected deployment tool")
    require(after.get("hoverCell") is None, "ordinary movement after deployment must not restore placement preview")


def validate_captured(report: dict[str, Any], expected_tool: str | None) -> None:
    require(report.get("browser_available") is True, "captured report requires browser")
    tool = str(report.get("tool") or "")
    require(bool(tool), "captured report tool missing")
    if expected_tool:
        require(tool == expected_tool, f"expected tool {expected_tool!r}, got {tool!r}")
    viewport_ids = set(as_list(report.get("viewport_ids")))
    require(viewport_ids == EXPECTED_VIEWPORTS, f"unexpected viewports: {sorted(viewport_ids)}")
    expected_count = len(EXPECTED_VIEWPORTS)
    require(
        int_value(report.get("expected_interaction_count")) == expected_count,
        f"expected interaction count must be {expected_count}",
    )
    require(
        int_value(report.get("passed_interaction_count")) == expected_count,
        f"passed interaction count must be {expected_count}",
    )
    require(
        int_value(report.get("captured_screenshot_count")) == expected_count,
        f"captured screenshot count must be {expected_count}",
    )
    interactions = as_list(report.get("interactions"))
    require(len(interactions) == expected_count, f"interactions must include {expected_count} entries")
    observed = {item.get("viewport_id") for item in interactions if isinstance(item, dict)}
    require(observed == EXPECTED_VIEWPORTS, "interaction viewport matrix is incomplete")
    for item in interactions:
        if not isinstance(item, dict):
            raise ValueError("interactions entries must be objects")
        validate_interaction(item, tool)
    require(not as_list(report.get("failures")), "captured report must have no failures")


def validate_unavailable(report: dict[str, Any], allow_unavailable: bool) -> None:
    require(allow_unavailable, "browser_unavailable requires --allow-unavailable")
    require(report.get("browser_available") is False, "unavailable report must not have browser")
    require(not as_list(report.get("interactions")), "unavailable report must not contain interactions")
    require(as_list(report.get("failures")), "unavailable report must explain failure")


def validate(report: dict[str, Any], allow_unavailable: bool, expected_tool: str | None) -> None:
    require(report.get("schema_version") == SCHEMA_VERSION, "schema_version mismatch")
    validate_safety(report)
    status = report.get("status")
    if status == "captured":
        validate_captured(report, expected_tool)
    elif status == "browser_unavailable":
        validate_unavailable(report, allow_unavailable)
    else:
        raise ValueError(f"unsupported or failed report status: {status}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--allow-unavailable", action="store_true")
    parser.add_argument("--expected-tool", help="Require the report to cover this projected tool id.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        validate(
            load_json_object(args.report, label="report root"),
            args.allow_unavailable,
            args.expected_tool,
        )
    except Exception as exc:  # noqa: BLE001 - CLI validator should be concise.
        print(f"battle drag interaction smoke report validation failed: {exc}", file=sys.stderr)
        return 1
    print(f"battle drag interaction smoke report validation passed: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
