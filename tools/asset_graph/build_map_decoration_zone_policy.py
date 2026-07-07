#!/usr/bin/env python3
"""Build the deterministic MapDecorationZonePolicy v0.1 example."""

from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

import map_path_geometry  # noqa: E402
import map_runtime_package as mrp_v01  # noqa: E402
import map_runtime_package_v02 as mrp_v02  # noqa: E402
from validation_common import load_json_object, write_json  # noqa: E402
from tools.asset_graph.validate_map_decoration_zone_policy import validate  # noqa: E402


DEFAULT_OUTPUT = ROOT / "examples/map_decoration_zone_policies/mvp_map_decoration_zone_policy.v0.1.json"
GENERATED_AT = "2026-07-07T00:00:00+00:00"
DEFAULT_PACKAGE_GLOBS = [
    "examples/map_runtime_packages/*.json",
    "examples/map_runtime_packages_v02/*.json",
]
CORE_FORBIDDEN_OVERLAP = [
    "route_band",
    "spawn_clearance",
    "objective_clearance",
    "build_slot_footprint",
    "resource_node_clearance",
    "hazard_zone",
    "defense_anchor_marker",
    "blocked_area",
]
STRONG_PROTECTION_POLICY = [
    "no_decoration_overlap",
    "no_visual_mimicry",
    "keep_player_readability",
]


def repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def slug(value: Any) -> str:
    raw = str(value or "unknown").strip().lower()
    safe = []
    for char in raw:
        safe.append(char if char.isalnum() else "_")
    return "_".join("".join(safe).split("_"))


def point(raw: Any) -> tuple[float, float]:
    if not isinstance(raw, dict):
        return (0.0, 0.0)
    return (float(raw.get("x", 0)), float(raw.get("y", 0)))


def bbox_from_point(raw: Any, radius: float) -> dict[str, float]:
    x, y = point(raw)
    return {
        "min_x": round(x - radius, 4),
        "min_y": round(y - radius, 4),
        "max_x": round(x + radius, 4),
        "max_y": round(y + radius, 4),
    }


def bbox_from_rect(rect: tuple[float, float, float, float], padding: float = 0.0) -> dict[str, float]:
    left, top, right, bottom = rect
    return {
        "min_x": round(left - padding, 4),
        "min_y": round(top - padding, 4),
        "max_x": round(right + padding, 4),
        "max_y": round(bottom + padding, 4),
    }


def validate_runtime_package(package: dict[str, Any], path: Path) -> None:
    version = package.get("schema_version")
    if version == "map_runtime_package.v0.2":
        errors = mrp_v02.validate_package_v02(package, None)
    elif version == "map_runtime_package.v0.1":
        errors = mrp_v01.validate_package(package, None)
    else:
        raise ValueError(f"{path} has unsupported schema_version {version!r}")
    if errors:
        joined = "; ".join(errors)
        raise ValueError(f"{path} failed runtime package validation: {joined}")


def reserved_zone(
    *,
    zone_id: str,
    zone_type: str,
    source_ref: str,
    geometry_kind: str,
    clearance_cells: float,
    bbox_cells: dict[str, float] | None = None,
    cells: list[dict[str, int]] | None = None,
    path_t_range: dict[str, float] | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "zone_id": zone_id,
        "zone_type": zone_type,
        "semantic_class": "A_strong_semantic",
        "source_ref": source_ref,
        "geometry_kind": geometry_kind,
        "clearance_cells": round(clearance_cells, 4),
        "protection_policy": STRONG_PROTECTION_POLICY,
    }
    if bbox_cells is not None:
        item["bbox_cells"] = bbox_cells
    if cells is not None:
        item["cells"] = cells
    if path_t_range is not None:
        item["path_t_range"] = path_t_range
    return item


def allowed_zone(
    *,
    zone_id: str,
    zone_type: str,
    semantic_class: str,
    anchor_ref: str,
    geometry_kind: str,
    allowed_prefab_tags: list[str],
    placement_rules: list[str],
    density_hint: str,
) -> dict[str, Any]:
    return {
        "zone_id": zone_id,
        "zone_type": zone_type,
        "semantic_class": semantic_class,
        "anchor_ref": anchor_ref,
        "geometry_kind": geometry_kind,
        "allowed_prefab_tags": allowed_prefab_tags,
        "forbidden_overlap": CORE_FORBIDDEN_OVERLAP,
        "placement_rules": placement_rules,
        "density_hint": density_hint,
    }


def layer_rules() -> list[dict[str, Any]]:
    return [
        {
            "semantic_class": "A_strong_semantic",
            "rule_id": "strong_semantics_are_protected",
            "description": "路径、出生点、目标、塔位、资源点、机关区、防守锚点和阻挡区只来自 MapRuntimePackage。",
            "must_obey": [
                "render_from_structured_anchor",
                "no_decoration_overlap",
                "no_image_reverse_inference",
            ],
        },
        {
            "semantic_class": "B_weak_semantic",
            "rule_id": "weak_semantics_attach_to_anchors",
            "description": "路边护栏、塔位碎石和资源点附属物可以随机，但必须依附结构化 anchor。",
            "must_obey": [
                "anchor_ref_required",
                "obey_allowed_and_forbidden_zones",
                "do_not_hide_strong_semantics",
            ],
        },
        {
            "semantic_class": "C_decoration",
            "rule_id": "decoration_must_not_mislead",
            "description": "远景、污渍和非阻挡杂物不能看起来像道路、塔位、资源点或阻挡物。",
            "must_obey": [
                "no_road_mimicry",
                "no_build_slot_mimicry",
                "no_resource_mimicry",
            ],
        },
        {
            "semantic_class": "D_atmosphere",
            "rule_id": "atmosphere_preserves_readability",
            "description": "雾、火花、光照和天气只能增强气质，不能遮挡核心交互信息。",
            "must_obey": [
                "keep_route_readable",
                "keep_build_slots_readable",
                "keep_objective_readable",
            ],
        },
    ]


def route_reserved_zones(prefix: str, package: dict[str, Any]) -> list[dict[str, Any]]:
    geometry = map_path_geometry.derive_path_geometry(package)
    zones: list[dict[str, Any]] = []
    clearance = float(geometry.get("road_half_width_cells", 0.0)) + float(
        geometry.get("shoulder_width_cells", 0.0)
    )
    for route in geometry.get("routes", []):
        if not isinstance(route, dict):
            continue
        route_id = slug(route.get("route_id"))
        zones.append(
            reserved_zone(
                zone_id=f"{prefix}_route_{route_id}_band",
                zone_type="route_band",
                source_ref=f"path_routes.{route_id}",
                geometry_kind="derived_road_band_envelope",
                clearance_cells=clearance,
                bbox_cells=dict(route.get("road_band_envelope") or {}),
            )
        )
    return zones


def build_slot_reserved_zones(prefix: str, package: dict[str, Any]) -> list[dict[str, Any]]:
    zones: list[dict[str, Any]] = []
    for index, slot in enumerate(package.get("build_slots", [])):
        if not isinstance(slot, dict):
            continue
        slot_id = slug(slot.get("slot_id") or f"slot_{index}")
        rect = map_path_geometry.footprint_rect(slot.get("position"), slot.get("footprint"))
        zones.append(
            reserved_zone(
                zone_id=f"{prefix}_build_slot_{slot_id}",
                zone_type="build_slot_footprint",
                source_ref=f"build_slots.{slot_id}",
                geometry_kind="footprint_bbox",
                clearance_cells=0.25,
                bbox_cells=bbox_from_rect(rect, padding=0.1),
            )
        )
    return zones


def spawn_and_objective_reserved_zones(prefix: str, package: dict[str, Any]) -> list[dict[str, Any]]:
    zones: list[dict[str, Any]] = []
    for index, spawn in enumerate(package.get("spawn_points", [])):
        if not isinstance(spawn, dict):
            continue
        spawn_id = slug(spawn.get("spawn_id") or f"spawn_{index}")
        zones.append(
            reserved_zone(
                zone_id=f"{prefix}_spawn_{spawn_id}",
                zone_type="spawn_clearance",
                source_ref=f"spawn_points.{spawn_id}",
                geometry_kind="point_clearance_bbox",
                clearance_cells=1.0,
                bbox_cells=bbox_from_point(spawn.get("position"), 1.0),
            )
        )
    objectives = package.get("objectives") if isinstance(package.get("objectives"), dict) else {}
    core = objectives.get("core_target") if isinstance(objectives, dict) else None
    if isinstance(core, dict):
        core_id = slug(core.get("target_id") or "core_target")
        zones.append(
            reserved_zone(
                zone_id=f"{prefix}_objective_{core_id}",
                zone_type="objective_clearance",
                source_ref=f"objectives.core_target.{core_id}",
                geometry_kind="point_clearance_bbox",
                clearance_cells=1.15,
                bbox_cells=bbox_from_point(core.get("position"), 1.15),
            )
        )
    optional_targets = objectives.get("optional_targets", []) if isinstance(objectives, dict) else []
    for index, target in enumerate(optional_targets):
        if not isinstance(target, dict):
            continue
        target_id = slug(target.get("target_id") or f"optional_target_{index}")
        zones.append(
            reserved_zone(
                zone_id=f"{prefix}_objective_{target_id}",
                zone_type="objective_clearance",
                source_ref=f"objectives.optional_targets.{target_id}",
                geometry_kind="point_clearance_bbox",
                clearance_cells=0.9,
                bbox_cells=bbox_from_point(target.get("position"), 0.9),
            )
        )
    return zones


def v02_reserved_zones(prefix: str, package: dict[str, Any]) -> list[dict[str, Any]]:
    zones: list[dict[str, Any]] = []
    for index, resource in enumerate(package.get("resource_nodes", [])):
        if not isinstance(resource, dict):
            continue
        resource_id = slug(resource.get("resource_node_id") or f"resource_{index}")
        rect = map_path_geometry.footprint_rect(resource.get("position"), resource.get("footprint"))
        zones.append(
            reserved_zone(
                zone_id=f"{prefix}_resource_{resource_id}",
                zone_type="resource_node_clearance",
                source_ref=f"resource_nodes.{resource_id}",
                geometry_kind="footprint_clearance_bbox",
                clearance_cells=0.5,
                bbox_cells=bbox_from_rect(rect, padding=0.3),
            )
        )
    for index, hazard in enumerate(package.get("hazard_zones", [])):
        if not isinstance(hazard, dict):
            continue
        hazard_id = slug(hazard.get("hazard_zone_id") or f"hazard_{index}")
        raw_range = hazard.get("path_t_range") if isinstance(hazard.get("path_t_range"), dict) else {}
        zones.append(
            reserved_zone(
                zone_id=f"{prefix}_hazard_{hazard_id}",
                zone_type="hazard_zone",
                source_ref=f"hazard_zones.{hazard_id}",
                geometry_kind="route_path_t_range",
                clearance_cells=0.35,
                path_t_range={
                    "start": round(float(raw_range.get("start", 0.0)), 4),
                    "end": round(float(raw_range.get("end", 1.0)), 4),
                },
            )
        )
    for index, anchor in enumerate(package.get("defense_anchors", [])):
        if not isinstance(anchor, dict):
            continue
        anchor_id = slug(anchor.get("defense_anchor_id") or f"anchor_{index}")
        radius = float(anchor.get("influence_radius_cells", 1.0))
        zones.append(
            reserved_zone(
                zone_id=f"{prefix}_defense_anchor_{anchor_id}",
                zone_type="defense_anchor_marker",
                source_ref=f"defense_anchors.{anchor_id}",
                geometry_kind="influence_radius_bbox",
                clearance_cells=0.25,
                bbox_cells=bbox_from_point(anchor.get("position"), radius),
            )
        )
    for index, area in enumerate(package.get("blocked_areas", [])):
        if not isinstance(area, dict):
            continue
        area_id = slug(area.get("blocked_area_id") or f"blocked_{index}")
        cells = [
            {"x": int(cell.get("x", 0)), "y": int(cell.get("y", 0))}
            for cell in area.get("cells", [])
            if isinstance(cell, dict)
        ]
        if cells:
            zones.append(
                reserved_zone(
                    zone_id=f"{prefix}_blocked_{area_id}",
                    zone_type="blocked_area",
                    source_ref=f"blocked_areas.{area_id}",
                    geometry_kind="blocked_cells",
                    clearance_cells=0.2,
                    cells=cells,
                )
            )
    return zones


def allowed_decoration_zones(prefix: str, package: dict[str, Any]) -> list[dict[str, Any]]:
    zones = [
        allowed_zone(
            zone_id=f"{prefix}_map_border_decoration",
            zone_type="map_border_decoration",
            semantic_class="C_decoration",
            anchor_ref="grid.outer_margin",
            geometry_kind="rule_based_grid_border_band",
            allowed_prefab_tags=["background_ruin", "tree_line", "broken_wall", "distant_light"],
            placement_rules=[
                "prefer_outer_two_cells",
                "never_create_walkable_road_shape",
                "keep_hud_safe_area_clear",
            ],
            density_hint="medium",
        ),
        allowed_zone(
            zone_id=f"{prefix}_route_shoulder_decoration",
            zone_type="route_shoulder_decoration",
            semantic_class="B_weak_semantic",
            anchor_ref="path_routes.*",
            geometry_kind="derived_route_shoulder_without_reserved_overlap",
            allowed_prefab_tags=["roadside_pebble", "fence_fragment", "mud_track", "small_lamp"],
            placement_rules=[
                "attach_to_route_band_edge",
                "stay_outside_derived_road_band",
                "do_not_hide_enemy_centerline",
            ],
            density_hint="low",
        ),
        allowed_zone(
            zone_id=f"{prefix}_empty_cell_decoration",
            zone_type="empty_cell_decoration",
            semantic_class="C_decoration",
            anchor_ref="grid.cells_minus_reserved_zones",
            geometry_kind="rule_based_empty_cell_fill",
            allowed_prefab_tags=["ground_stain", "small_scrap", "grass_patch", "nonblocking_stone"],
            placement_rules=[
                "avoid_platform_like_silhouette",
                "avoid_resource_like_color",
                "use_low_contrast_against_ground",
            ],
            density_hint="medium",
        ),
        allowed_zone(
            zone_id=f"{prefix}_atmosphere_overlay",
            zone_type="atmosphere_overlay",
            semantic_class="D_atmosphere",
            anchor_ref="viewport_and_world_theme",
            geometry_kind="screen_space_overlay_with_runtime_mask",
            allowed_prefab_tags=["fog_soft", "embers_small", "light_falloff", "shadow_vignette"],
            placement_rules=[
                "mask_out_objective_and_build_slots",
                "keep_route_readability",
                "no_full_screen_opaque_overlay",
            ],
            density_hint="low",
        ),
    ]
    if package.get("schema_version") == "map_runtime_package.v0.2":
        zones.append(
            allowed_zone(
                zone_id=f"{prefix}_semantic_prop_shoulder",
                zone_type="semantic_prop_shoulder",
                semantic_class="B_weak_semantic",
                anchor_ref="resource_nodes|hazard_zones|defense_anchors|blocked_areas",
                geometry_kind="strong_semantic_adjacent_ring_without_overlap",
                allowed_prefab_tags=["warning_marker", "resource_crate", "anchor_rubble", "hazard_sign"],
                placement_rules=[
                    "attach_to_v02_semantic_anchor",
                    "never_change_blocking_or_interaction_truth",
                    "keep_resource_and_hazard_icons_distinct",
                ],
                density_hint="low",
            )
        )
    return zones


def build_map_policy(path: Path, package: dict[str, Any]) -> dict[str, Any]:
    prefix = slug(package.get("node_id") or package.get("package_id"))
    reserved = []
    reserved.extend(route_reserved_zones(prefix, package))
    reserved.extend(build_slot_reserved_zones(prefix, package))
    reserved.extend(spawn_and_objective_reserved_zones(prefix, package))
    if package.get("schema_version") == "map_runtime_package.v0.2":
        reserved.extend(v02_reserved_zones(prefix, package))
    allowed = allowed_decoration_zones(prefix, package)
    review = map_path_geometry.review_placement_geometry(package)
    warnings = [str(warning) for warning in review.get("warnings", [])]
    return {
        "map_id": f"{prefix}_{slug(package.get('schema_version'))}_decoration_policy",
        "source_package": {
            "path": repo_path(path),
            "package_id": str(package.get("package_id") or ""),
            "node_id": str(package.get("node_id") or ""),
            "schema_version": str(package.get("schema_version") or ""),
        },
        "grid": dict(package.get("grid") or {}),
        "reserved_zones": reserved,
        "allowed_decoration_zones": allowed,
        "layer_rules": layer_rules(),
        "validation_report": {
            "status": "passed_with_warnings" if warnings else "passed",
            "reserved_zone_count": len(reserved),
            "allowed_decoration_zone_count": len(allowed),
            "warning_count": len(warnings),
            "warnings": warnings,
        },
    }


def default_runtime_package_paths() -> list[Path]:
    paths: list[Path] = []
    for pattern in DEFAULT_PACKAGE_GLOBS:
        paths.extend(Path(item) for item in glob.glob(str(ROOT / pattern)))
    return sorted({path.resolve() for path in paths})


def build_policy(package_paths: list[Path]) -> dict[str, Any]:
    maps: list[dict[str, Any]] = []
    versions: set[str] = set()
    for path in package_paths:
        package = load_json_object(path)
        validate_runtime_package(package, path)
        maps.append(build_map_policy(path, package))
        versions.add(str(package.get("schema_version") or ""))
    reserved_count = sum(len(item.get("reserved_zones", [])) for item in maps)
    allowed_count = sum(len(item.get("allowed_decoration_zones", [])) for item in maps)
    return {
        "schema_version": "map_decoration_zone_policy.v0.1",
        "policy_id": "mvp_map_decoration_zone_policy_v0_1",
        "generated_at": GENERATED_AT,
        "source_policy": {
            "policy_role": "review_only_renderer_helper",
            "semantic_source": "MapRuntimePackage v0.1/v0.2",
            "geometry_source": "MapRuntimePackage.path_routes.waypoints",
            "runtime_fact_source": False,
            "player_default_runtime": False,
            "image_to_logic_inference_allowed": False,
            "may_modify_map_runtime_package": False,
            "provider_call_count": 0,
        },
        "summary": {
            "map_count": len(maps),
            "reserved_zone_count": reserved_count,
            "allowed_decoration_zone_count": allowed_count,
            "source_schema_versions": sorted(versions),
            "strong_semantic_policy": "强语义来自 MapRuntimePackage；装饰和氛围只能在派生 allowed zones 中表现，不能反向决定路径、塔位、资源、机关、防守或阻挡事实。",
        },
        "maps": maps,
        "usage_policy": [
            "review_only",
            "renderer_helper",
            "not_player_runtime",
            "not_map_runtime_fact_source",
            "does_not_modify_map_runtime_package",
            "no_image_to_logic_inference",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runtime-package",
        action="append",
        type=Path,
        help="MapRuntimePackage v0.1/v0.2 JSON path. Can be passed multiple times.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output policy JSON path.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate the generated policy before writing.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    package_paths = [path.resolve() for path in args.runtime_package] if args.runtime_package else default_runtime_package_paths()
    if not package_paths:
        print("no map runtime packages found", file=sys.stderr)
        return 1
    try:
        policy = build_policy(package_paths)
        if args.validate:
            validate(policy)
        output = args.output if args.output.is_absolute() else ROOT / args.output
        write_json(output, policy, sort_keys=True)
    except Exception as exc:  # noqa: BLE001 - CLI builder should print concise failures.
        print(f"map decoration zone policy build failed: {exc}", file=sys.stderr)
        return 1
    print(f"map decoration zone policy written: {output}")
    print(f"- maps: {policy['summary']['map_count']}")
    print(f"- reserved_zones: {policy['summary']['reserved_zone_count']}")
    print(f"- allowed_decoration_zones: {policy['summary']['allowed_decoration_zone_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
