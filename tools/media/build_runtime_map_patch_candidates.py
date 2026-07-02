#!/usr/bin/env python3
"""Build review-only runtime map patch candidates from reconciliation plans."""

from __future__ import annotations

import argparse
import copy
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPORT_VERSION = "runtime_map_patch_candidates.v0.1"
DEFAULT_PLAN = ROOT / "examples/review_packs/map_layout_reconciliation_plan.v0.1.json"
DEFAULT_OUTPUT = ROOT / "examples/review_packs/runtime_map_patch_candidates.v0.1.json"


PATCH_NOTES: dict[str, dict[str, Any]] = {
    "gray_lantern_station": {
        "status": "review_candidate",
        "patch_strategy": "hybrid_runtime_reprojection",
        "risk_level": "medium",
        "patch_operations": [
            {
                "op": "replace_path_waypoints",
                "route_id": "path_main_road",
                "waypoints": [
                    {"x": 15, "y": 4},
                    {"x": 13, "y": 4},
                    {"x": 11, "y": 4},
                    {"x": 9, "y": 4},
                    {"x": 7, "y": 4},
                    {"x": 5, "y": 4},
                    {"x": 4, "y": 3},
                    {"x": 3, "y": 2},
                ],
                "reason": "Follow the painted road toward the station instead of preserving the old right-angle grid route.",
            },
            {
                "op": "move_objective",
                "target_id": "target_node_core",
                "position": {"x": 3, "y": 2},
                "reason": "Place the core marker on the visible station/outpost area.",
            },
            {
                "op": "move_objective",
                "target_id": "target_signal_beacon",
                "position": {"x": 4, "y": 1},
                "reason": "Keep the optional beacon near the station-side landmark cluster.",
            },
            {
                "op": "move_spawn_point",
                "spawn_id": "spawn_path_main_road",
                "position": {"x": 15, "y": 4},
                "reason": "Preserve the right-edge enemy entry.",
            },
            {
                "op": "move_build_slot",
                "slot_id": "slot_06",
                "position": {"x": 8, "y": 3},
                "reason": "Keep slot_06 adjacent to the reprojected road without overlapping the new path cells.",
            },
        ],
    },
    "lamp_wick_store": {
        "status": "review_candidate",
        "patch_strategy": "runtime_path_reprojection",
        "risk_level": "medium",
        "patch_operations": [
            {
                "op": "replace_path_waypoints",
                "route_id": "path_wick_store_main_pipe",
                "waypoints": [
                    {"x": 17, "y": 4},
                    {"x": 15, "y": 4},
                    {"x": 13, "y": 4},
                    {"x": 11, "y": 4},
                    {"x": 9, "y": 5},
                    {"x": 7, "y": 5},
                    {"x": 5, "y": 5},
                    {"x": 3, "y": 5},
                    {"x": 1, "y": 5},
                ],
                "reason": "Trace the broad visible central trail instead of a grid-like upper zigzag.",
            },
            {
                "op": "replace_path_waypoints",
                "route_id": "path_wick_store_service_lane",
                "waypoints": [
                    {"x": 17, "y": 8},
                    {"x": 15, "y": 8},
                    {"x": 13, "y": 8},
                    {"x": 11, "y": 7},
                    {"x": 9, "y": 7},
                    {"x": 7, "y": 7},
                    {"x": 5, "y": 6},
                    {"x": 3, "y": 6},
                    {"x": 2, "y": 5},
                ],
                "reason": "Keep the secondary route on the lower visible trail band.",
            },
            {
                "op": "move_objective",
                "target_id": "target_wick_store_core",
                "position": {"x": 1, "y": 5},
                "reason": "Attach the core inventory to the left-side depot approach.",
            },
            {
                "op": "move_objective",
                "target_id": "target_supply_line_coupler",
                "position": {"x": 2, "y": 7},
                "reason": "Keep the coupler near the lower-left supply linkage.",
            },
            {
                "op": "move_objective",
                "target_id": "target_lamp_oil_shelf",
                "position": {"x": 4, "y": 3},
                "reason": "Keep the oil shelf near the upper-left visible depot pad.",
            },
            {
                "op": "move_build_slot",
                "slot_id": "slot_06",
                "position": {"x": 12, "y": 6},
                "reason": "Move the old roadside slot off the reprojected main route while keeping it near the central service band.",
            },
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


def resolve_repo_path(value: Any) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def apply_patch_candidate(runtime_package: dict[str, Any], operations: list[dict[str, Any]]) -> dict[str, Any]:
    patched = copy.deepcopy(runtime_package)
    route_by_id = {
        route.get("route_id"): route
        for route in as_list(patched.get("path_routes"))
        if isinstance(route, dict)
    }
    objectives = patched.get("objectives") if isinstance(patched.get("objectives"), dict) else {}
    objective_items: dict[str, dict[str, Any]] = {}
    core = objectives.get("core_target")
    if isinstance(core, dict):
        objective_items[str(core.get("target_id"))] = core
    for target in as_list(objectives.get("optional_targets")):
        if isinstance(target, dict):
            objective_items[str(target.get("target_id"))] = target
    spawn_by_id = {
        spawn.get("spawn_id"): spawn
        for spawn in as_list(patched.get("spawn_points"))
        if isinstance(spawn, dict)
    }
    slot_by_id = {
        slot.get("slot_id"): slot
        for slot in as_list(patched.get("build_slots"))
        if isinstance(slot, dict)
    }
    for op in operations:
        kind = op.get("op")
        if kind == "replace_path_waypoints" and op.get("route_id") in route_by_id:
            route_by_id[op.get("route_id")]["waypoints"] = op.get("waypoints")
        elif kind == "move_objective" and op.get("target_id") in objective_items:
            objective_items[op.get("target_id")]["position"] = op.get("position")
        elif kind == "move_spawn_point" and op.get("spawn_id") in spawn_by_id:
            spawn_by_id[op.get("spawn_id")]["position"] = op.get("position")
        elif kind == "move_build_slot" and op.get("slot_id") in slot_by_id:
            slot_by_id[op.get("slot_id")]["position"] = op.get("position")
    return patched


def route_bounds(package: dict[str, Any]) -> dict[str, Any]:
    points = []
    for route in as_list(package.get("path_routes")):
        if isinstance(route, dict):
            points.extend(point for point in as_list(route.get("waypoints")) if isinstance(point, dict))
    if not points:
        return {}
    xs = [point.get("x", 0) for point in points]
    ys = [point.get("y", 0) for point in points]
    return {"min_x": min(xs), "max_x": max(xs), "min_y": min(ys), "max_y": max(ys)}


def build_candidate(node_plan: dict[str, Any]) -> dict[str, Any]:
    node_id = str(node_plan.get("node_id") or "")
    notes = PATCH_NOTES.get(node_id)
    if notes is None:
        return {
            "node_id": node_id,
            "status": "skipped",
            "reason": "No runtime patch candidate is proposed for this node; use topology-constrained prompt pack instead.",
            "recommendation": node_plan.get("recommendation"),
            "promotion_allowed_now": False,
        }
    package_path = resolve_repo_path(node_plan.get("runtime_summary", {}).get("runtime_package_path"))
    runtime_package = load_json(package_path) if package_path and package_path.exists() else {}
    patched = apply_patch_candidate(runtime_package, notes["patch_operations"]) if runtime_package else {}
    return {
        "node_id": node_id,
        "status": notes["status"],
        "patch_strategy": notes["patch_strategy"],
        "risk_level": notes["risk_level"],
        "source_runtime_package": rel(package_path) if package_path else None,
        "overlay_review_png_path": node_plan.get("overlay_artifacts", {}).get("overlay_review_png_path"),
        "promotion_allowed_now": False,
        "patch_operations": notes["patch_operations"],
        "before_summary": {
            "route_bounds": route_bounds(runtime_package),
            "path_route_count": len(as_list(runtime_package.get("path_routes"))) if runtime_package else 0,
        },
        "after_summary": {
            "route_bounds": route_bounds(patched),
            "path_route_count": len(as_list(patched.get("path_routes"))) if patched else 0,
        },
        "acceptance_gates": [
            "patch_schema_reviewed",
            "overlay_png_regenerated_from_patched_runtime",
            "runtime_paths_follow_visible_roads",
            "objectives_land_on_unique_visible_landmarks",
            "build_slots_land_on_visible_empty_pads",
            "battle_simulation_still_valid",
            "explicit_promotion_report_updates_MapRuntimePackage",
        ],
    }


def build_report(plan_path: Path) -> dict[str, Any]:
    plan = load_json(plan_path)
    candidates = [
        build_candidate(node_plan)
        for node_plan in as_list(plan.get("node_plans"))
        if isinstance(node_plan, dict)
    ]
    status_counts = Counter(str(candidate.get("status")) for candidate in candidates)
    return {
        "schema_version": REPORT_VERSION,
        "report_id": "mvp_runtime_map_patch_candidates",
        "layout_plan_path": rel(plan_path),
        "status": "review_only_patch_candidates_ready",
        "summary": {
            "candidate_count": len(candidates),
            "review_candidate_count": status_counts.get("review_candidate", 0),
            "skipped_count": status_counts.get("skipped", 0),
            "status_counts": dict(sorted(status_counts.items())),
        },
        "candidates": candidates,
        "policy": [
            "These are review-only patch candidates; they do not mutate MapRuntimePackage.",
            "Candidates must be rendered into fresh overlay artifacts and reviewed before any runtime patch is accepted.",
            "A later explicit promotion report is required before published visual layers or runtime packages change.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build review-only runtime map patch candidates.")
    parser.add_argument("--layout-plan", default=str(DEFAULT_PLAN))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    layout_plan = Path(args.layout_plan)
    if not layout_plan.is_absolute():
        layout_plan = ROOT / layout_plan
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    report = build_report(layout_plan)
    write_json(output, report)
    print(f"Wrote {output}")
    print(f"- status: {report['status']}")
    print(f"- review_candidates: {report['summary']['review_candidate_count']}")
    return 0 if report["summary"]["candidate_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
