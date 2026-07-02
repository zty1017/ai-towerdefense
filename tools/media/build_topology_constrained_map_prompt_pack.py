#!/usr/bin/env python3
"""Build topology-constrained prompt briefs for map regeneration."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPORT_VERSION = "topology_constrained_map_prompt_pack.v0.1"
DEFAULT_PLAN = ROOT / "examples/review_packs/map_layout_reconciliation_plan.v0.1.json"
DEFAULT_OUTPUT = ROOT / "examples/review_packs/topology_constrained_map_prompt_pack.v0.1.json"


PROMPT_NOTES: dict[str, dict[str, Any]] = {
    "old_signal_tower": {
        "status": "prompt_ready",
        "primary_use": "topology_constrained_regeneration",
        "topology_policy": "preserve_existing_runtime_topology",
        "prompt_brief": (
            "Wide 16:9 hand-painted fantasy strategy game terrain background, high three-quarter camera, "
            "empty playable map art, no UI. Scene: cold mountain ridge with ruined signal tower structures, "
            "snow patches, blue-violet echo light, broken antenna debris. Preserve gameplay topology: the protected "
            "core objective must read visually near the left-side lower-mid approach area, not as a huge centered tower; "
            "two enemy routes should enter from the right side and curve naturally toward the left-side objective. "
            "Show visible dirt or ridge paths matching those routes. Place empty flat build clearings distributed along "
            "the two routes, not clustered only in the top-right. No arrows, no text, no units, no projectiles, no UI, "
            "no deployed towers, no road lane markings. The map must be ready for runtime overlays."
        ),
        "negative_constraints": [
            "no_centered_primary_tower_objective",
            "no_arrows_or_direction_symbols",
            "no_units_or_projectiles",
            "no_top_right_only_build_slot_cluster",
            "no_paths_crossing_through_objective_platform",
        ],
    },
    "gray_lantern_station": {
        "status": "fallback_prompt_ready",
        "primary_use": "fallback_if_runtime_reprojection_fails",
        "topology_policy": "station_core_near_runtime_objective_or_reprojected_station_core",
        "prompt_brief": (
            "Wide 16:9 empty fantasy lantern frontier map. The station/outpost must be a clear protected objective "
            "near the left upper side, with one natural road entering from the right and curving toward it. "
            "Use flat empty build clearings beside the road. No arrows, no units, no projectiles, no deployed towers, no UI."
        ),
        "negative_constraints": [
            "no_disconnected_core_landmark",
            "no_mechanical_right_angle_road",
            "no_edge_only_build_slot_cluster",
        ],
    },
    "lamp_wick_store": {
        "status": "fallback_prompt_ready",
        "primary_use": "fallback_if_runtime_path_reprojection_fails",
        "topology_policy": "preserve_two_right_to_left_routes",
        "prompt_brief": (
            "Wide 16:9 empty lamp-wick supply depot map. Preserve two readable routes entering from the right and "
            "leading toward distinct left-side depot landmarks. Use natural dirt trails and empty round build pads "
            "beside them. Avoid angular diagram roads. No arrows, no units, no projectiles, no deployed towers, no UI."
        ),
        "negative_constraints": [
            "no_grid_like_zigzag_paths",
            "no_unclear_left_side_objective",
            "no_duplicate_right_side_pad_cluster",
        ],
    },
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def build_prompt_item(node_plan: dict[str, Any]) -> dict[str, Any]:
    node_id = str(node_plan.get("node_id") or "")
    notes = PROMPT_NOTES.get(
        node_id,
        {
            "status": "manual_prompt_required",
            "primary_use": "manual_regeneration",
            "topology_policy": "manual",
            "prompt_brief": "Manual topology-constrained prompt is required.",
            "negative_constraints": [],
        },
    )
    runtime_summary = node_plan.get("runtime_summary") if isinstance(node_plan.get("runtime_summary"), dict) else {}
    return {
        "node_id": node_id,
        "status": notes["status"],
        "primary_use": notes["primary_use"],
        "topology_policy": notes["topology_policy"],
        "recommendation_source": node_plan.get("recommendation"),
        "runtime_package_path": runtime_summary.get("runtime_package_path"),
        "runtime_topology_summary": {
            "path_route_count": runtime_summary.get("path_route_count"),
            "build_slot_count": runtime_summary.get("build_slot_count"),
            "objective_count": runtime_summary.get("objective_count"),
            "spawn_point_count": runtime_summary.get("spawn_point_count"),
            "grid": runtime_summary.get("grid"),
        },
        "prompt_brief": notes["prompt_brief"],
        "negative_constraints": notes["negative_constraints"],
        "required_review_gates": [
            "no_visible_arrows_text_units_projectiles",
            "paths_visually_match_runtime_topology",
            "objective_landmark_matches_runtime_policy",
            "build_pads_distributed_near_routes",
            "overlay_review_generated_before_promotion",
        ],
    }


def build_pack(plan_path: Path) -> dict[str, Any]:
    plan = load_json(plan_path)
    prompts = [
        build_prompt_item(node_plan)
        for node_plan in as_list(plan.get("node_plans"))
        if isinstance(node_plan, dict)
    ]
    status_counts = Counter(str(item.get("status")) for item in prompts)
    return {
        "schema_version": REPORT_VERSION,
        "pack_id": "mvp_topology_constrained_map_prompt_pack",
        "layout_plan_path": rel(plan_path),
        "status": "prompt_pack_ready",
        "summary": {
            "prompt_count": len(prompts),
            "status_counts": dict(sorted(status_counts.items())),
            "primary_prompt_count": status_counts.get("prompt_ready", 0),
            "fallback_prompt_count": status_counts.get("fallback_prompt_ready", 0),
        },
        "prompts": prompts,
        "policy": [
            "Prompt briefs are developer/review artifacts; they are not player-visible content.",
            "Generated images from this pack must re-enter candidate review, alignment review, overlay review, and promotion gates.",
            "Prompt briefs must not override MapRuntimePackage topology unless a separate runtime patch is approved.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build topology-constrained map prompt pack.")
    parser.add_argument("--layout-plan", default=str(DEFAULT_PLAN))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    layout_plan = Path(args.layout_plan)
    if not layout_plan.is_absolute():
        layout_plan = ROOT / layout_plan
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    pack = build_pack(layout_plan)
    write_json(output, pack)
    print(f"Wrote {output}")
    print(f"- status: {pack['status']}")
    print(f"- prompts: {pack['summary']['prompt_count']}")
    return 0 if pack["summary"]["prompt_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
