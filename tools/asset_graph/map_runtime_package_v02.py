"""MapRuntimePackage v0.2 extension helpers.

v0.2 is a logic-first preview extension. It reuses the reviewed v0.1 map
contract, then adds resource nodes, hazard zones, defense anchors, and blocked
areas so map compilation can express more tower-defense semantics without
asking image generation to decide gameplay truth.

This module never reads .env and never calls model or media providers.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import map_runtime_package as v01


TOP_LEVEL_ALLOWED_V02 = frozenset(v01.TOP_LEVEL_ALLOWED | {
    "resource_nodes",
    "hazard_zones",
    "defense_anchors",
    "blocked_areas",
})

RESOURCE_NODE_ALLOWED = frozenset(
    {
        "resource_node_id",
        "resource_type",
        "position",
        "footprint",
        "resource_tag",
        "blocking",
        "interactable",
        "visual_hint",
    }
)
HAZARD_ZONE_ALLOWED = frozenset(
    {
        "hazard_zone_id",
        "hazard_type",
        "anchor_route_id",
        "path_t_range",
        "affected_area",
        "effect",
        "visual_hint",
    }
)
DEFENSE_ANCHOR_ALLOWED = frozenset(
    {
        "defense_anchor_id",
        "anchor_type",
        "position",
        "influence_radius_cells",
        "related_route_ids",
        "recommended_tags",
    }
)
BLOCKED_AREA_ALLOWED = frozenset(
    {
        "blocked_area_id",
        "blocked_type",
        "cells",
        "blocking_policy",
        "visual_hint",
    }
)
PATH_T_RANGE_ALLOWED = frozenset({"start", "end"})
HAZARD_EFFECT_ALLOWED = frozenset({"effect_type", "value", "duration_ms"})

RESOURCE_TYPES = frozenset({"crystal_vein", "scrap_cache", "power_relay"})
RESOURCE_TAGS = frozenset({"energy", "material", "power"})
RESOURCE_VISUAL_HINTS = frozenset({"crystal_cluster", "scrap_pile", "relay_box"})
HAZARD_TYPES = frozenset({"shadow_pressure", "steam_vent", "unstable_current"})
HAZARD_AREAS = frozenset({"road_band", "roadside", "build_slot_zone"})
HAZARD_EFFECTS = frozenset({"slow_enemy", "pulse_damage", "visibility_drop"})
HAZARD_VISUAL_HINTS = frozenset({"dark_pool", "steam_rift", "electric_arc"})
DEFENSE_ANCHOR_TYPES = frozenset({"choke_point", "route_turn", "target_perimeter"})
BLOCKED_TYPES = frozenset({"ruin_wall", "dark_growth", "collapsed_device"})
BLOCKING_POLICIES = frozenset({"blocks_building", "blocks_decoration"})
BLOCKED_VISUAL_HINTS = frozenset({"broken_wall", "dark_brambles", "machine_wreck"})


def _footprint_cells(position: dict[str, Any], footprint: dict[str, Any]) -> set[tuple[int, int]]:
    x = int(position.get("x", 0))
    y = int(position.get("y", 0))
    width = int(footprint.get("width_cells", 1))
    height = int(footprint.get("height_cells", 1))
    return {(x + dx, y + dy) for dx in range(width) for dy in range(height)}


def _occupied_cells(package: dict[str, Any]) -> set[tuple[int, int]]:
    occupied = v01.path_cells(package.get("path_routes", []))
    for slot in package.get("build_slots", []):
        if isinstance(slot, dict):
            occupied.update(
                _footprint_cells(
                    v01.require_object(slot.get("position"), "slot.position", []),
                    v01.require_object(slot.get("footprint"), "slot.footprint", []),
                )
            )
    objectives = package.get("objectives") if isinstance(package.get("objectives"), dict) else {}
    for target in [objectives.get("core_target")] + list(objectives.get("optional_targets") or []):
        if isinstance(target, dict):
            occupied.add(v01._point_key(target.get("position", {})))
    for spawn in package.get("spawn_points", []):
        if isinstance(spawn, dict):
            occupied.add(v01._point_key(spawn.get("position", {})))
    return occupied


def _first_free_cell(
    grid: dict[str, Any],
    occupied: set[tuple[int, int]],
    preferred: list[tuple[int, int]],
) -> tuple[int, int]:
    for cell in preferred:
        if cell not in occupied and v01._in_grid(cell, grid):
            occupied.add(cell)
            return cell
    width = int(grid.get("width_cells", 1))
    height = int(grid.get("height_cells", 1))
    for y in range(height):
        for x in range(width):
            cell = (x, y)
            if cell not in occupied and v01._in_grid(cell, grid):
                occupied.add(cell)
                return cell
    return (0, 0)


def _route_midpoint(route: dict[str, Any]) -> dict[str, int]:
    waypoints = [p for p in route.get("waypoints", []) if isinstance(p, dict)]
    if not waypoints:
        return {"x": 0, "y": 0}
    return v01._normalize_point(waypoints[len(waypoints) // 2])


def build_map_runtime_package_v02(
    battle_config: dict[str, Any],
    *,
    battle_config_path: str,
    visual_reference_manifest: dict[str, Any] | None = None,
    visual_reference_manifest_path: str | None = None,
    package_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build a MapRuntimePackage v0.2 preview package from a battle config."""
    package = v01.build_map_runtime_package(
        battle_config,
        battle_config_path=battle_config_path,
        visual_reference_manifest=visual_reference_manifest,
        visual_reference_manifest_path=visual_reference_manifest_path,
        package_id=package_id,
        created_at=created_at,
    )
    node_id = str(package.get("node_id") or "unknown_node")
    package["schema_version"] = "map_runtime_package.v0.2"
    package["package_id"] = package_id or f"map_pkg_{node_id}_v0_2"

    grid = dict(package.get("grid") or {})
    routes = [route for route in package.get("path_routes", []) if isinstance(route, dict)]
    occupied = _occupied_cells(package)

    optional_targets = package.get("objectives", {}).get("optional_targets", [])
    target_positions = [
        v01._point_key(target.get("position", {}))
        for target in optional_targets
        if isinstance(target, dict)
    ]
    resource_preferred = []
    for x, y in target_positions:
        resource_preferred.extend([(x + 1, y), (x, y + 1), (x - 1, y), (x, y - 1)])
    if not resource_preferred and routes:
        mid = _route_midpoint(routes[0])
        mx, my = v01._point_key(mid)
        resource_preferred.extend([(mx + 2, my), (mx - 2, my), (mx, my + 2)])
    resource_cell = _first_free_cell(grid, occupied, resource_preferred)

    blocked_preferred = [(0, 0), (1, 0), (0, int(grid.get("height_cells", 1)) - 1)]
    blocked_cell = _first_free_cell(grid, occupied, blocked_preferred)

    anchor_route_ids = [str(route.get("route_id")) for route in routes if route.get("route_id")]
    anchor_pos = _route_midpoint(routes[0]) if routes else {"x": 0, "y": 0}

    package["resource_nodes"] = [
        {
            "resource_node_id": f"resource_{node_id}_primary",
            "resource_type": "crystal_vein",
            "position": {"x": resource_cell[0], "y": resource_cell[1]},
            "footprint": {"width_cells": 1, "height_cells": 1},
            "resource_tag": "energy",
            "blocking": False,
            "interactable": True,
            "visual_hint": "crystal_cluster",
        }
    ]
    package["hazard_zones"] = [
        {
            "hazard_zone_id": f"hazard_{node_id}_road_pressure",
            "hazard_type": "shadow_pressure",
            "anchor_route_id": anchor_route_ids[0] if anchor_route_ids else "",
            "path_t_range": {"start": 0.42, "end": 0.58},
            "affected_area": "road_band",
            "effect": {
                "effect_type": "slow_enemy",
                "value": 0.18,
                "duration_ms": 2600,
            },
            "visual_hint": "dark_pool",
        }
    ]
    package["defense_anchors"] = [
        {
            "defense_anchor_id": f"anchor_{node_id}_mid_choke",
            "anchor_type": "choke_point",
            "position": anchor_pos,
            "influence_radius_cells": 2,
            "related_route_ids": anchor_route_ids[:2],
            "recommended_tags": ["control", "aoe", "near_path"],
        }
    ]
    package["blocked_areas"] = [
        {
            "blocked_area_id": f"blocked_{node_id}_edge_ruin",
            "blocked_type": "ruin_wall",
            "cells": [{"x": blocked_cell[0], "y": blocked_cell[1]}],
            "blocking_policy": "blocks_building",
            "visual_hint": "broken_wall",
        }
    ]

    gates = package.get("validation_report", {}).get("gates")
    if isinstance(gates, list):
        gates.append(
            {
                "gate_id": "v0_2_strong_semantic_extensions",
                "status": "passed",
                "summary": "Resource nodes, hazard zones, defense anchors, and blocked areas are explicit runtime semantics.",
            }
        )
    return package


def _strip_v02_extensions(package: dict[str, Any]) -> dict[str, Any]:
    base = deepcopy(package)
    base["schema_version"] = "map_runtime_package.v0.1"
    for key in ("resource_nodes", "hazard_zones", "defense_anchors", "blocked_areas"):
        base.pop(key, None)
    gates = base.get("validation_report", {}).get("gates")
    if isinstance(gates, list):
        base["validation_report"]["gates"] = [
            gate
            for gate in gates
            if not (
                isinstance(gate, dict)
                and gate.get("gate_id") == "v0_2_strong_semantic_extensions"
            )
        ]
    return base


def validate_package_v02(package: dict[str, Any], schema: dict[str, Any] | None = None) -> list[str]:
    errors: list[str] = []
    if schema:
        errors.extend(v01.validate_with_jsonschema(package, schema))
    errors.extend(validate_pure_python_v02(package))
    v01.scan_forbidden_fields(package, "", errors)
    v01.scan_external_urls(package, "", errors)
    return list(dict.fromkeys(errors))


def validate_pure_python_v02(package: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    v01.reject_unknown_keys(package, TOP_LEVEL_ALLOWED_V02, "", errors)
    if package.get("schema_version") != "map_runtime_package.v0.2":
        errors.append("schema_version must be 'map_runtime_package.v0.2'")

    base_errors = v01.validate_pure_python(_strip_v02_extensions(package))
    errors.extend(base_errors)

    grid = package.get("grid") if isinstance(package.get("grid"), dict) else {}
    routes = [route for route in package.get("path_routes", []) if isinstance(route, dict)]
    objectives = package.get("objectives") if isinstance(package.get("objectives"), dict) else {}
    build_slots = [slot for slot in package.get("build_slots", []) if isinstance(slot, dict)]
    occupied_by_core = _occupied_cells(_strip_v02_extensions(package))
    blocked_cells = validate_blocked_areas(package.get("blocked_areas"), grid, occupied_by_core, errors)
    resource_cells = validate_resource_nodes(
        package.get("resource_nodes"),
        grid,
        occupied_by_core | blocked_cells,
        errors,
    )
    validate_hazard_zones(package.get("hazard_zones"), routes, errors)
    validate_defense_anchors(package.get("defense_anchors"), routes, grid, errors)
    validate_build_slots_against_blocked(build_slots, blocked_cells, errors)
    validate_objectives_against_blocked(objectives, blocked_cells, errors)
    if blocked_cells & resource_cells:
        errors.append("blocked_areas must not overlap resource_nodes")
    return errors


def validate_resource_nodes(
    raw: Any,
    grid: dict[str, Any],
    forbidden_cells: set[tuple[int, int]],
    errors: list[str],
) -> set[tuple[int, int]]:
    cells: set[tuple[int, int]] = set()
    if not isinstance(raw, list) or not raw:
        errors.append("resource_nodes must be a non-empty array")
        return cells
    seen: set[str] = set()
    for index, raw_node in enumerate(raw):
        path = f"resource_nodes[{index}]"
        node = v01.require_object(raw_node, path, errors)
        if not node:
            continue
        v01.reject_unknown_keys(node, RESOURCE_NODE_ALLOWED, path, errors)
        node_id = v01.require_string(node.get("resource_node_id"), f"{path}.resource_node_id", errors)
        if node_id in seen:
            errors.append(f"{path}.resource_node_id={node_id!r} is duplicated")
        seen.add(node_id)
        v01.require_enum(node.get("resource_type"), RESOURCE_TYPES, f"{path}.resource_type", errors)
        position = v01.validate_point(node.get("position"), f"{path}.position", grid, errors)
        footprint = v01.require_object(node.get("footprint"), f"{path}.footprint", errors)
        if footprint:
            v01.reject_unknown_keys(footprint, v01.FOOTPRINT_ALLOWED, f"{path}.footprint", errors)
            v01.require_int(footprint.get("width_cells"), f"{path}.footprint.width_cells", errors, 1)
            v01.require_int(footprint.get("height_cells"), f"{path}.footprint.height_cells", errors, 1)
        node_cells = _footprint_cells(node.get("position", {}), node.get("footprint", {}))
        cells.update(node_cells)
        if position in forbidden_cells:
            errors.append(f"{path}.position={position!r} overlaps route/build/objective/spawn/blocked cells")
        v01.require_enum(node.get("resource_tag"), RESOURCE_TAGS, f"{path}.resource_tag", errors)
        if not isinstance(node.get("blocking"), bool):
            errors.append(f"{path}.blocking must be a boolean")
        if not isinstance(node.get("interactable"), bool):
            errors.append(f"{path}.interactable must be a boolean")
        v01.require_enum(node.get("visual_hint"), RESOURCE_VISUAL_HINTS, f"{path}.visual_hint", errors)
    return cells


def validate_hazard_zones(raw: Any, routes: list[dict[str, Any]], errors: list[str]) -> None:
    route_ids = {str(route.get("route_id")) for route in routes}
    if not isinstance(raw, list) or not raw:
        errors.append("hazard_zones must be a non-empty array")
        return
    seen: set[str] = set()
    for index, raw_zone in enumerate(raw):
        path = f"hazard_zones[{index}]"
        zone = v01.require_object(raw_zone, path, errors)
        if not zone:
            continue
        v01.reject_unknown_keys(zone, HAZARD_ZONE_ALLOWED, path, errors)
        zone_id = v01.require_string(zone.get("hazard_zone_id"), f"{path}.hazard_zone_id", errors)
        if zone_id in seen:
            errors.append(f"{path}.hazard_zone_id={zone_id!r} is duplicated")
        seen.add(zone_id)
        v01.require_enum(zone.get("hazard_type"), HAZARD_TYPES, f"{path}.hazard_type", errors)
        route_id = v01.require_string(zone.get("anchor_route_id"), f"{path}.anchor_route_id", errors)
        if route_id not in route_ids:
            errors.append(f"{path}.anchor_route_id={route_id!r} does not match a route")
        span = v01.require_object(zone.get("path_t_range"), f"{path}.path_t_range", errors)
        if span:
            v01.reject_unknown_keys(span, PATH_T_RANGE_ALLOWED, f"{path}.path_t_range", errors)
            start = span.get("start")
            end = span.get("end")
            if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
                errors.append(f"{path}.path_t_range start/end must be numbers")
            elif not (0 <= float(start) < float(end) <= 1):
                errors.append(f"{path}.path_t_range must satisfy 0 <= start < end <= 1")
        v01.require_enum(zone.get("affected_area"), HAZARD_AREAS, f"{path}.affected_area", errors)
        effect = v01.require_object(zone.get("effect"), f"{path}.effect", errors)
        if effect:
            v01.reject_unknown_keys(effect, HAZARD_EFFECT_ALLOWED, f"{path}.effect", errors)
            v01.require_enum(effect.get("effect_type"), HAZARD_EFFECTS, f"{path}.effect.effect_type", errors)
            if not isinstance(effect.get("value"), (int, float)):
                errors.append(f"{path}.effect.value must be a number")
            v01.require_int(effect.get("duration_ms"), f"{path}.effect.duration_ms", errors, 1)
        v01.require_enum(zone.get("visual_hint"), HAZARD_VISUAL_HINTS, f"{path}.visual_hint", errors)


def validate_defense_anchors(
    raw: Any, routes: list[dict[str, Any]], grid: dict[str, Any], errors: list[str]
) -> None:
    route_ids = {str(route.get("route_id")) for route in routes}
    if not isinstance(raw, list) or not raw:
        errors.append("defense_anchors must be a non-empty array")
        return
    seen: set[str] = set()
    for index, raw_anchor in enumerate(raw):
        path = f"defense_anchors[{index}]"
        anchor = v01.require_object(raw_anchor, path, errors)
        if not anchor:
            continue
        v01.reject_unknown_keys(anchor, DEFENSE_ANCHOR_ALLOWED, path, errors)
        anchor_id = v01.require_string(anchor.get("defense_anchor_id"), f"{path}.defense_anchor_id", errors)
        if anchor_id in seen:
            errors.append(f"{path}.defense_anchor_id={anchor_id!r} is duplicated")
        seen.add(anchor_id)
        v01.require_enum(anchor.get("anchor_type"), DEFENSE_ANCHOR_TYPES, f"{path}.anchor_type", errors)
        v01.validate_point(anchor.get("position"), f"{path}.position", grid, errors)
        radius = anchor.get("influence_radius_cells")
        if not isinstance(radius, (int, float)) or float(radius) <= 0:
            errors.append(f"{path}.influence_radius_cells must be a positive number")
        related = anchor.get("related_route_ids")
        if not isinstance(related, list) or not related:
            errors.append(f"{path}.related_route_ids must be a non-empty array")
        else:
            for route_index, route_id in enumerate(related):
                if route_id not in route_ids:
                    errors.append(f"{path}.related_route_ids[{route_index}]={route_id!r} does not match a route")
        tags = anchor.get("recommended_tags")
        if not isinstance(tags, list) or not all(isinstance(tag, str) and tag for tag in tags):
            errors.append(f"{path}.recommended_tags must contain non-empty strings")


def validate_blocked_areas(
    raw: Any,
    grid: dict[str, Any],
    forbidden_cells: set[tuple[int, int]],
    errors: list[str],
) -> set[tuple[int, int]]:
    cells: set[tuple[int, int]] = set()
    if not isinstance(raw, list) or not raw:
        errors.append("blocked_areas must be a non-empty array")
        return cells
    seen: set[str] = set()
    for index, raw_area in enumerate(raw):
        path = f"blocked_areas[{index}]"
        area = v01.require_object(raw_area, path, errors)
        if not area:
            continue
        v01.reject_unknown_keys(area, BLOCKED_AREA_ALLOWED, path, errors)
        area_id = v01.require_string(area.get("blocked_area_id"), f"{path}.blocked_area_id", errors)
        if area_id in seen:
            errors.append(f"{path}.blocked_area_id={area_id!r} is duplicated")
        seen.add(area_id)
        v01.require_enum(area.get("blocked_type"), BLOCKED_TYPES, f"{path}.blocked_type", errors)
        raw_cells = area.get("cells")
        if not isinstance(raw_cells, list) or not raw_cells:
            errors.append(f"{path}.cells must be a non-empty array")
        else:
            for cell_index, raw_cell in enumerate(raw_cells):
                cell = v01.validate_point(raw_cell, f"{path}.cells[{cell_index}]", grid, errors)
                cells.add(cell)
                if cell in forbidden_cells:
                    errors.append(f"{path}.cells[{cell_index}]={cell!r} overlaps route/build/objective/spawn cells")
        v01.require_enum(area.get("blocking_policy"), BLOCKING_POLICIES, f"{path}.blocking_policy", errors)
        v01.require_enum(area.get("visual_hint"), BLOCKED_VISUAL_HINTS, f"{path}.visual_hint", errors)
    return cells


def validate_build_slots_against_blocked(
    build_slots: list[dict[str, Any]], blocked_cells: set[tuple[int, int]], errors: list[str]
) -> None:
    for index, slot in enumerate(build_slots):
        if v01._point_key(slot.get("position", {})) in blocked_cells:
            errors.append(f"build_slots[{index}].position overlaps blocked_areas")


def validate_objectives_against_blocked(
    objectives: dict[str, Any], blocked_cells: set[tuple[int, int]], errors: list[str]
) -> None:
    for label, target in [("core_target", objectives.get("core_target"))]:
        if isinstance(target, dict) and v01._point_key(target.get("position", {})) in blocked_cells:
            errors.append(f"objectives.{label}.position overlaps blocked_areas")
    for index, target in enumerate(objectives.get("optional_targets", []) if isinstance(objectives, dict) else []):
        if isinstance(target, dict) and v01._point_key(target.get("position", {})) in blocked_cells:
            errors.append(f"objectives.optional_targets[{index}].position overlaps blocked_areas")
