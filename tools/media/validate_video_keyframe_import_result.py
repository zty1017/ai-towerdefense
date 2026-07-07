#!/usr/bin/env python3
"""Validate a video keyframe atlas import result and its loop report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def fail(message: str) -> None:
    raise ValueError(message)


def validate_import_result(atlas_path: Path, loop_report_path: Path) -> dict[str, Any]:
    atlas = load_json(atlas_path)
    report = load_json(loop_report_path)
    items = atlas.get("items") if isinstance(atlas, dict) else None
    if not isinstance(items, list):
        fail("atlas.items must be a list")
    imported = [
        item
        for item in items
        if isinstance(item, dict) and item.get("frame_source_kind") == "video_keyframe_sequence"
    ]
    if not imported:
        fail("atlas must contain at least one video_keyframe_sequence item")

    summary = report.get("summary") if isinstance(report, dict) else None
    if not isinstance(summary, dict):
        fail("loop report summary must be an object")
    frame_source_counts = summary.get("frame_source_counts")
    if not isinstance(frame_source_counts, dict):
        fail("loop report summary.frame_source_counts must be an object")
    imported_count = int(frame_source_counts.get("video_keyframe_sequence") or 0)
    if imported_count < len(imported):
        fail("loop report video_keyframe_sequence count is lower than imported atlas item count")
    if int(summary.get("failed_count") or 0) != 0:
        fail("loop report failed_count must be 0")

    return {
        "atlas_path": str(atlas_path),
        "loop_report_path": str(loop_report_path),
        "imported_item_count": len(imported),
        "loop_report_video_keyframe_sequence_count": imported_count,
        "failed_count": int(summary.get("failed_count") or 0),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--atlas", type=Path, required=True)
    parser.add_argument("--loop-report", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        summary = validate_import_result(args.atlas, args.loop_report)
    except Exception as exc:  # noqa: BLE001 - CLI reports concise failure.
        print(f"video keyframe import result validation failed: {exc}", file=sys.stderr)
        return 1
    print(
        "video keyframe import result validation passed: "
        f"{summary['imported_item_count']} imported item(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
