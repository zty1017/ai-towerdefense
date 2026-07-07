#!/usr/bin/env python3
"""Build a temporary controlled map candidate artifact import smoke plan."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


DEFAULT_OUTPUT = Path("/tmp/controlled_map_import_smoke_plan.json")


def build_plan() -> dict[str, object]:
    return {
        "schema_version": "controlled_map_candidate_artifact_import_plan.v0.1",
        "plan_id": "tmp_controlled_map_import_smoke",
        "status": "one_validated_not_copied",
        "approvals": [],
        "imports": [
            {
                "node_id": "gray_lantern_station",
                "source_png_path": (
                    "game_data/media/map_visual_reference/topology_control_sketches/"
                    "gray_lantern_station.topology_control_sketch.png"
                ),
                "source_kind": "local_review_fixture",
                "approved_by": "codex_smoke",
                "notes": "no copy smoke for importer path validation",
            }
        ],
        "policy": ["temporary smoke only"],
        "notes": [],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(build_plan(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001 - CLI reports concise failures.
        print(f"controlled map import smoke plan build failed: {exc}", file=sys.stderr)
        return 1
    print(f"controlled map import smoke plan written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
