#!/usr/bin/env python3
"""Build a layout reconciliation plan for map candidates.

The plan turns overlay visual review findings into actionable next work. It is
not a runtime patch and does not promote any visual layer. It decides whether a
node should first try runtime-coordinate reprojection, topology-constrained
regeneration, or a hybrid path.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPORT_VERSION = "map_layout_reconciliation_plan.v0.1"
DEFAULT_VISUAL_REVIEW = ROOT / "examples/review_packs/map_candidate_overlay_visual_review.v0.1.json"
DEFAULT_RUNTIME_PACKAGE_DIR = ROOT / "examples/map_runtime_packages"
DEFAULT_OUTPUT = ROOT / "examples/review_packs/map_layout_reconciliation_plan.v0.1.json"


PLAN_NOTES: dict[str, dict[str, Any]] = {
    "gray_lantern_station": {
        "recommendation": "hybrid_reproject_then_review",
        "priority": "P0",
        "rationale": [
            "painted road is readable and close enough for runtime path reprojection",
            "core objective currently misses the visible station core",
            "station-side landmarks can support a small layout-specific runtime patch",
        ],
        "proposed_actions": [
            {
                "action": "reproject_core_objective",
                "target": "target_node_core",
                "intent": "move core marker onto the visible station/outpost core area",
                "requires_manual_or_vision_confirmation": True,
            },
            {
                "action": "smooth_main_path",
                "target": "path_main_road",
                "intent": "replace hard right-angle bends with waypoints following the painted dirt road",
                "requires_manual_or_vision_confirmation": True,
            },
            {
                "action": "review_build_slot_spacing",
                "target": "build_slots",
                "intent": "keep slots near readable clearings and remove edge-clustered slots if they do not map to visible pads",
                "requires_manual_or_vision_confirmation": True,
            },
        ],
        "fallback": "regenerate_with_strict_station_core_at_runtime_coordinate",
    },
    "lamp_wick_store": {
        "recommendation": "runtime_path_reprojection",
        "priority": "P0",
        "rationale": [
            "candidate image is clean and has readable pads",
            "main blocker is path geometry being too angular for visible dirt trails",
            "runtime objectives can likely be retargeted without regenerating the whole map",
        ],
        "proposed_actions": [
            {
                "action": "reproject_two_routes",
                "target": "path_wick_store_main_pipe,path_wick_store_service_lane",
                "intent": "trace the visible dirt trail network instead of preserving grid-like zigzags",
                "requires_manual_or_vision_confirmation": True,
            },
            {
                "action": "retarget_left_side_objectives",
                "target": "target_wick_store_core,target_supply_line_coupler,target_lamp_oil_shelf",
                "intent": "attach objectives to unique visible depot or pad landmarks",
                "requires_manual_or_vision_confirmation": True,
            },
            {
                "action": "deduplicate_right_slot_cluster",
                "target": "build_slots",
                "intent": "avoid stacking too many deployable slots on the same visible pad cluster",
                "requires_manual_or_vision_confirmation": True,
            },
        ],
        "fallback": "regenerate_from_topology_control_sketch_if_reprojection_fails",
    },
    "old_signal_tower": {
        "recommendation": "topology_constrained_regeneration_preferred",
        "priority": "P0",
        "rationale": [
            "visual primary objective is centered while runtime core objective is left of center",
            "moving runtime core to the visual tower would materially alter route/objective topology",
            "current route overlays cross the central tower platform and reduce combat readability",
        ],
        "proposed_actions": [
            {
                "action": "choose_topology_policy",
                "target": "node_layout",
                "intent": "decide whether old signal tower core should be central in gameplay or remain left-side as current runtime data",
                "requires_manual_or_vision_confirmation": True,
            },
            {
                "action": "regenerate_or_recompose_map",
                "target": "painted_candidate",
                "intent": "if runtime topology is preserved, regenerate a map with core objective near the current runtime coordinate",
                "requires_manual_or_vision_confirmation": True,
            },
            {
                "action": "layout_specific_runtime_patch",
                "target": "path_routes,objectives,build_slots",
                "intent": "if central tower becomes the gameplay core, rebuild routes and slots around the central objective",
                "requires_manual_or_vision_confirmation": True,
            },
        ],
        "fallback": "keep_current_published_visual_layer_until_topology_decision",
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


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def runtime_package_index(package_dir: Path) -> dict[str, dict[str, Any]]:
    packages: dict[str, dict[str, Any]] = {}
    for path in sorted(package_dir.glob("*.map_runtime_package.json")):
        package = load_json(path)
        node_id = package.get("node_id")
        if isinstance(node_id, str) and node_id:
            package["_path"] = rel(path)
            packages[node_id] = package
    return packages


def runtime_summary(package: dict[str, Any] | None) -> dict[str, Any]:
    if not package:
        return {}
    objectives = as_obj(package.get("objectives"))
    objective_count = (1 if isinstance(objectives.get("core_target"), dict) else 0) + len(
        [item for item in as_list(objectives.get("optional_targets")) if isinstance(item, dict)]
    )
    return {
        "runtime_package_path": package.get("_path"),
        "grid": as_obj(package.get("grid")),
        "path_route_count": len(as_list(package.get("path_routes"))),
        "build_slot_count": len(as_list(package.get("build_slots"))),
        "spawn_point_count": len(as_list(package.get("spawn_points"))),
        "objective_count": objective_count,
    }


def build_node_plan(review: dict[str, Any], package: dict[str, Any] | None) -> dict[str, Any]:
    node_id = str(review.get("node_id") or "")
    notes = PLAN_NOTES.get(
        node_id,
        {
            "recommendation": "manual_layout_review_required",
            "priority": "P1",
            "rationale": ["no deterministic plan notes available"],
            "proposed_actions": [
                {
                    "action": "manual_layout_review",
                    "target": "node_layout",
                    "intent": "inspect overlay and choose reproject or regenerate",
                    "requires_manual_or_vision_confirmation": True,
                }
            ],
            "fallback": "keep_current_published_visual_layer",
        },
    )
    blockers = as_list(review.get("findings"))
    can_auto_promote = False
    return {
        "node_id": node_id,
        "priority": notes["priority"],
        "recommendation": notes["recommendation"],
        "promotion_allowed_now": can_auto_promote,
        "runtime_summary": runtime_summary(package),
        "overlay_artifacts": {
            "normalized_path": review.get("normalized_path"),
            "overlay_review_png_path": review.get("overlay_review_png_path"),
        },
        "visual_review_status": review.get("status"),
        "promotion_recommendation": review.get("promotion_recommendation"),
        "blocking_findings": blockers,
        "strengths": as_list(review.get("strengths")),
        "rationale": notes["rationale"],
        "proposed_actions": notes["proposed_actions"],
        "fallback": notes["fallback"],
        "acceptance_gates": [
            "normalized_png_exists",
            "overlay_png_exists",
            "runtime_paths_follow_visible_roads",
            "objectives_land_on_unique_visible_landmarks",
            "build_slots_land_on_visible_empty_pads",
            "visual_readability_passed",
            "explicit_promotion_report_updates_published_visual_layer",
        ],
    }


def build_plan(visual_review_path: Path, package_dir: Path) -> dict[str, Any]:
    visual_review = load_json(visual_review_path)
    packages = runtime_package_index(package_dir)
    plans = [
        build_node_plan(review, packages.get(str(review.get("node_id") or "")))
        for review in as_list(visual_review.get("reviews"))
        if isinstance(review, dict)
    ]
    recommendation_counts = Counter(str(plan.get("recommendation")) for plan in plans)
    blocked_from_promotion = sum(1 for plan in plans if not plan.get("promotion_allowed_now"))
    return {
        "schema_version": REPORT_VERSION,
        "plan_id": "mvp_map_layout_reconciliation_plan",
        "visual_review_path": rel(visual_review_path),
        "runtime_package_dir": rel(package_dir),
        "status": "ready_for_reconciliation_work" if plans else "blocked",
        "summary": {
            "node_count": len(plans),
            "promotion_allowed_now_count": len(plans) - blocked_from_promotion,
            "blocked_from_promotion_count": blocked_from_promotion,
            "recommendation_counts": dict(sorted(recommendation_counts.items())),
            "p0_count": sum(1 for plan in plans if plan.get("priority") == "P0"),
        },
        "node_plans": plans,
        "policy": [
            "This plan does not mutate runtime packages or published visual layers.",
            "Runtime truth remains MapRuntimePackage until a later patch and promotion report are reviewed.",
            "A map image can be high quality and still be blocked when its visible landmarks do not match gameplay coordinates.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build map layout reconciliation plan.")
    parser.add_argument("--visual-review", default=str(DEFAULT_VISUAL_REVIEW))
    parser.add_argument("--runtime-package-dir", default=str(DEFAULT_RUNTIME_PACKAGE_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    visual_review = Path(args.visual_review)
    if not visual_review.is_absolute():
        visual_review = ROOT / visual_review
    package_dir = Path(args.runtime_package_dir)
    if not package_dir.is_absolute():
        package_dir = ROOT / package_dir
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output

    plan = build_plan(visual_review, package_dir)
    write_json(output, plan)
    print(f"Wrote {output}")
    print(f"- status: {plan['status']}")
    print(f"- nodes: {plan['summary']['node_count']}")
    return 0 if plan["summary"]["node_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
