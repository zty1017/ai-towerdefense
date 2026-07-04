"""MapStylePack, ProceduralMapRenderPlan, and semantic visual report helpers.

This module keeps map presentation deterministic and logic-first:

1. MapRuntimePackage remains the source of gameplay truth.
2. MapStylePack only controls visual style and component choices.
3. ProceduralMapRenderPlan turns the two packages into layered draw operations.
4. SemanticVisualConsistencyReport proves strong gameplay semantics are visible.

It never reads .env and never calls model or media providers.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


FORBIDDEN_FIELDS = frozenset(
    {
        "provider",
        "model",
        "raw_prompt",
        "full_trace",
        "raw_json",
        "api_key",
        "secret",
        "unreviewed_content",
    }
)
FORBIDDEN_URL_MARKERS = ("http://", "https://", "://")
DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)

PLAYER_FORBIDDEN_LAYER_KINDS = frozenset(
    {"debug_control_overlay", "debug_reference_overlay"}
)
REQUIRED_RENDER_LAYER_KINDS = frozenset(
    {
        "terrain_base",
        "road_band",
        "road_edge",
        "build_slot_platform",
        "objective_foundation",
        "spawn_atmosphere",
        "runtime_interaction_overlay",
    }
)
REQUIRED_REPORT_CHECKS = frozenset(
    {
        "route_road_band_coverage",
        "build_slot_platform_coverage",
        "objective_marker_coverage",
        "spawn_marker_coverage",
        "debug_reference_excluded_from_player_default",
    }
)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def scan_forbidden_fields(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key in FORBIDDEN_FIELDS:
                errors.append(f"forbidden field '{child_path}' is not allowed")
            scan_forbidden_fields(child, child_path, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_forbidden_fields(child, f"{path}[{index}]", errors)


def scan_external_urls(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            scan_external_urls(child, child_path, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_external_urls(child, f"{path}[{index}]", errors)
    elif isinstance(value, str):
        lowered = value.lower()
        if any(marker in lowered for marker in FORBIDDEN_URL_MARKERS):
            errors.append(f"{path}={value!r} must not contain external URL markers")


def validate_with_jsonschema(
    package: dict[str, Any], schema: dict[str, Any] | None
) -> list[str]:
    if not schema:
        return []
    try:
        import jsonschema  # type: ignore
    except Exception:
        return []
    validator_cls = getattr(jsonschema, "Draft202012Validator", None)
    if validator_cls is None:
        validator_cls = getattr(jsonschema, "Draft7Validator", None)
    if validator_cls is None:
        return []
    validator = validator_cls(schema)
    return [
        f"schema: {'.'.join(map(str, e.path)) or '<root>'}: {e.message}"
        for e in sorted(validator.iter_errors(package), key=str)
    ]


def _require_object(value: Any, path: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{path} must be an object")
        return {}
    return value


def _require_array(
    value: Any, path: str, errors: list[str], *, minimum: int = 0
) -> list[Any]:
    if not isinstance(value, list):
        errors.append(f"{path} must be an array")
        return []
    if len(value) < minimum:
        errors.append(f"{path} must contain at least {minimum} item(s)")
    return value


def _require_string(value: Any, path: str, errors: list[str]) -> str:
    if not isinstance(value, str) or not value:
        errors.append(f"{path} must be a non-empty string")
        return ""
    return value


def _material_id(style_pack: dict[str, Any], role: str) -> str:
    for item in style_pack.get("terrain_materials", []) + style_pack.get("road_materials", []):
        if isinstance(item, dict) and item.get("role") == role:
            return str(item.get("material_id") or role)
    return role


def _material_style_binding(style_pack: dict[str, Any], role: str) -> dict[str, Any]:
    for item in style_pack.get("terrain_materials", []) + style_pack.get("road_materials", []):
        if isinstance(item, dict) and item.get("role") == role:
            return {
                "source": "map_style_pack.material",
                "owner_id": str(item.get("material_id") or role),
                "role": role,
                "texture_policy": item.get("texture_policy"),
                "component_ref": item.get("component_ref"),
            }
    return {
        "source": "map_style_pack.material",
        "owner_id": role,
        "role": role,
        "texture_policy": "procedural_only",
        "component_ref": None,
    }


def _prefab_id(style_pack: dict[str, Any], key: str, role: str) -> str:
    for item in style_pack.get(key, []):
        if isinstance(item, dict) and item.get("role") == role:
            return str(item.get("prefab_id") or role)
    return role


def _prefab_style_binding(style_pack: dict[str, Any], key: str, role: str) -> dict[str, Any]:
    for item in style_pack.get(key, []):
        if isinstance(item, dict) and item.get("role") == role:
            visual_ref = item.get("visual_ref") if isinstance(item.get("visual_ref"), dict) else {}
            return {
                "source": "map_style_pack.prefab",
                "owner_id": str(item.get("prefab_id") or role),
                "role": role,
                "visual_ref": {
                    "kind": visual_ref.get("kind"),
                    "value": visual_ref.get("value"),
                },
            }
    return {
        "source": "map_style_pack.prefab",
        "owner_id": role,
        "role": role,
        "visual_ref": {"kind": "procedural_shape", "value": None},
    }


def _prefab_id_any(
    style_pack: dict[str, Any],
    key: str,
    roles: list[str],
    fallback: str,
) -> str:
    role_set = {role for role in roles if role}
    for item in style_pack.get(key, []):
        if isinstance(item, dict) and item.get("role") in role_set:
            return str(item.get("prefab_id") or item.get("role") or fallback)
    return fallback


def _prefab_style_binding_any(
    style_pack: dict[str, Any],
    key: str,
    roles: list[str],
    fallback: str,
) -> dict[str, Any]:
    role_set = {role for role in roles if role}
    for item in style_pack.get(key, []):
        if isinstance(item, dict) and item.get("role") in role_set:
            visual_ref = item.get("visual_ref") if isinstance(item.get("visual_ref"), dict) else {}
            return {
                "source": "map_style_pack.prefab",
                "owner_id": str(item.get("prefab_id") or item.get("role") or fallback),
                "role": str(item.get("role") or fallback),
                "visual_ref": {
                    "kind": visual_ref.get("kind"),
                    "value": visual_ref.get("value"),
                },
            }
    return {
        "source": "map_style_pack.prefab",
        "owner_id": fallback,
        "role": fallback,
        "visual_ref": {"kind": "procedural_shape", "value": None},
    }


def _atmosphere_id(style_pack: dict[str, Any]) -> str | None:
    for item in style_pack.get("atmosphere_layers", []):
        if isinstance(item, dict):
            return str(item.get("layer_id") or "atmosphere")
    return None


def _target_ids(runtime_package: dict[str, Any]) -> list[str]:
    objectives = runtime_package.get("objectives") or {}
    ids: list[str] = []
    core = objectives.get("core_target") if isinstance(objectives, dict) else None
    if isinstance(core, dict):
        ids.append(str(core.get("target_id") or "core_target"))
    optional = objectives.get("optional_targets") if isinstance(objectives, dict) else []
    if isinstance(optional, list):
        for target in optional:
            if isinstance(target, dict):
                ids.append(str(target.get("target_id") or "optional_target"))
    return ids


def _operation(
    op_id: str,
    op_type: str,
    semantic_kind: str,
    semantic_id: str | None,
    style_kind: str,
    style_id: str | None,
    geometry: dict[str, Any],
) -> dict[str, Any]:
    return {
        "op_id": op_id,
        "op_type": op_type,
        "semantic_ref": {"kind": semantic_kind, "id": semantic_id},
        "style_ref": {"kind": style_kind, "id": style_id},
        "geometry": geometry,
    }


def build_render_plan(
    runtime_package: dict[str, Any],
    style_pack: dict[str, Any],
    *,
    map_runtime_package_path: str,
    map_style_pack_path: str,
    plan_id: str | None = None,
    created_at: str | None = None,
    canvas_width: int = 1280,
    canvas_height: int = 720,
) -> dict[str, Any]:
    grid = dict(runtime_package.get("grid") or {})
    node_id = str(runtime_package.get("node_id") or "unknown_node")
    style_pack_id = str(style_pack.get("style_pack_id") or "unknown_style_pack")
    package_id = str(runtime_package.get("package_id") or "unknown_map_runtime_package")

    layers: list[dict[str, Any]] = []

    def add_layer(
        layer_id: str,
        kind: str,
        authority: str,
        player_default: bool,
        source: str,
        operations: list[dict[str, Any]],
    ) -> None:
        layers.append(
            {
                "layer_id": layer_id,
                "kind": kind,
                "authority": authority,
                "player_default": player_default,
                "source": source,
                "operations": operations,
            }
        )

    add_layer(
        "terrain_base",
        "terrain_base",
        "visual_style",
        True,
        "map_style_pack",
        [
            _operation(
                "fill_grid_terrain",
                "fill_grid",
                "grid",
                "grid",
                "material",
                _material_id(style_pack, "terrain_base"),
                {
                    "grid": grid,
                    "palette_key": "terrain_base",
                    "style_component_binding": _material_style_binding(style_pack, "terrain_base"),
                },
            )
        ],
    )

    road_band_ops: list[dict[str, Any]] = []
    road_edge_ops: list[dict[str, Any]] = []
    for route in runtime_package.get("path_routes", []):
        if not isinstance(route, dict):
            continue
        route_id = str(route.get("route_id") or "route")
        waypoints = [p for p in route.get("waypoints", []) if isinstance(p, dict)]
        road_band_ops.append(
            _operation(
                f"road_band_{route_id}",
                "draw_polyline_band",
                "path_route",
                route_id,
                "material",
                _material_id(style_pack, "road_band"),
                {
                    "waypoints": waypoints,
                    "width_cells": 0.85,
                    "style_component_binding": _material_style_binding(style_pack, "road_band"),
                },
            )
        )
        road_edge_ops.append(
            _operation(
                f"road_edge_{route_id}",
                "draw_polyline_edge",
                "path_route",
                route_id,
                "material",
                _material_id(style_pack, "road_edge"),
                {
                    "waypoints": waypoints,
                    "edge_style": (style_pack.get("road_edge_rules") or {}).get(
                        "edge_style", "soft_embedded"
                    ),
                    "shoulder_width_cells": (style_pack.get("road_edge_rules") or {}).get(
                        "shoulder_width_cells", 0.25
                    ),
                    "style_component_binding": _material_style_binding(style_pack, "road_edge"),
                },
            )
        )
    add_layer("road_band", "road_band", "runtime_semantic", True, "map_runtime_package", road_band_ops)
    add_layer("road_edge", "road_edge", "runtime_semantic", True, "map_runtime_package", road_edge_ops)

    slot_ops: list[dict[str, Any]] = []
    for slot in runtime_package.get("build_slots", []):
        if not isinstance(slot, dict):
            continue
        slot_id = str(slot.get("slot_id") or "slot")
        slot_ops.append(
            _operation(
                f"platform_{slot_id}",
                "place_prefab",
                "build_slot",
                slot_id,
                "prefab",
                _prefab_id(style_pack, "build_slot_platforms", "build_slot_platform"),
                {
                    "position": slot.get("position", {}),
                    "footprint": slot.get("footprint", {}),
                    "visual_hint": slot.get("visual_hint"),
                    "style_component_binding": _prefab_style_binding(
                        style_pack, "build_slot_platforms", "build_slot_platform"
                    ),
                },
            )
        )
    add_layer(
        "build_slot_platform",
        "build_slot_platform",
        "runtime_semantic",
        True,
        "map_runtime_package",
        slot_ops,
    )

    objective_ops: list[dict[str, Any]] = []
    objectives = runtime_package.get("objectives") or {}
    for target in [objectives.get("core_target")] + list(objectives.get("optional_targets") or []):
        if not isinstance(target, dict):
            continue
        target_id = str(target.get("target_id") or "target")
        objective_ops.append(
            _operation(
                f"objective_{target_id}",
                "place_prefab",
                "objective",
                target_id,
                "prefab",
                _prefab_id(style_pack, "objective_prefabs", "objective_foundation"),
                {
                    "position": target.get("position", {}),
                    "durability": target.get("durability"),
                    "style_component_binding": _prefab_style_binding(
                        style_pack, "objective_prefabs", "objective_foundation"
                    ),
                },
            )
        )
    add_layer(
        "objective_foundation",
        "objective_foundation",
        "runtime_semantic",
        True,
        "map_runtime_package",
        objective_ops,
    )

    spawn_ops: list[dict[str, Any]] = []
    for spawn in runtime_package.get("spawn_points", []):
        if not isinstance(spawn, dict):
            continue
        spawn_id = str(spawn.get("spawn_id") or "spawn")
        spawn_ops.append(
            _operation(
                f"spawn_{spawn_id}",
                "place_prefab",
                "spawn_point",
                spawn_id,
                "prefab",
                _prefab_id(style_pack, "spawn_prefabs", "spawn_marker"),
                {
                    "position": spawn.get("position", {}),
                    "route_id": spawn.get("route_id"),
                    "style_component_binding": _prefab_style_binding(
                        style_pack, "spawn_prefabs", "spawn_marker"
                    ),
                },
            )
        )
    add_layer(
        "spawn_atmosphere",
        "spawn_atmosphere",
        "runtime_semantic",
        True,
        "map_runtime_package",
        spawn_ops,
    )

    resource_hazard_ops: list[dict[str, Any]] = []
    for resource in runtime_package.get("resource_nodes", []):
        if not isinstance(resource, dict):
            continue
        resource_id = str(resource.get("resource_node_id") or "resource_node")
        prefab_id = _prefab_id_any(
            style_pack,
            "resource_prefabs",
            [
                str(resource.get("visual_hint") or ""),
                str(resource.get("resource_tag") or ""),
                str(resource.get("resource_type") or ""),
                "resource_marker",
            ],
            "resource_marker",
        )
        resource_hazard_ops.append(
            _operation(
                f"resource_{resource_id}",
                "place_prefab",
                "resource_node",
                resource_id,
                "prefab",
                prefab_id,
                {
                    "position": resource.get("position", {}),
                    "footprint": resource.get("footprint", {}),
                    "resource_type": resource.get("resource_type"),
                    "resource_tag": resource.get("resource_tag"),
                    "blocking": resource.get("blocking"),
                    "interactable": resource.get("interactable"),
                    "visual_hint": resource.get("visual_hint"),
                    "style_component_binding": _prefab_style_binding_any(
                        style_pack,
                        "resource_prefabs",
                        [
                            str(resource.get("visual_hint") or ""),
                            str(resource.get("resource_tag") or ""),
                            str(resource.get("resource_type") or ""),
                            "resource_marker",
                        ],
                        "resource_marker",
                    ),
                },
            )
        )
    for hazard_zone in runtime_package.get("hazard_zones", []):
        if not isinstance(hazard_zone, dict):
            continue
        hazard_id = str(hazard_zone.get("hazard_zone_id") or "hazard_zone")
        prefab_id = _prefab_id_any(
            style_pack,
            "hazard_prefabs",
            [
                str(hazard_zone.get("visual_hint") or ""),
                str(hazard_zone.get("hazard_type") or ""),
                "hazard_marker",
            ],
            "hazard_marker",
        )
        resource_hazard_ops.append(
            _operation(
                f"hazard_{hazard_id}",
                "draw_zone",
                "hazard_zone",
                hazard_id,
                "prefab",
                prefab_id,
                {
                    "anchor_route_id": hazard_zone.get("anchor_route_id"),
                    "path_t_range": hazard_zone.get("path_t_range", {}),
                    "affected_area": hazard_zone.get("affected_area"),
                    "effect": hazard_zone.get("effect", {}),
                    "hazard_type": hazard_zone.get("hazard_type"),
                    "visual_hint": hazard_zone.get("visual_hint"),
                    "style_component_binding": _prefab_style_binding_any(
                        style_pack,
                        "hazard_prefabs",
                        [
                            str(hazard_zone.get("visual_hint") or ""),
                            str(hazard_zone.get("hazard_type") or ""),
                            "hazard_marker",
                        ],
                        "hazard_marker",
                    ),
                },
            )
        )
    for defense_anchor in runtime_package.get("defense_anchors", []):
        if not isinstance(defense_anchor, dict):
            continue
        anchor_id = str(defense_anchor.get("defense_anchor_id") or "defense_anchor")
        resource_hazard_ops.append(
            _operation(
                f"defense_anchor_{anchor_id}",
                "draw_anchor_marker",
                "defense_anchor",
                anchor_id,
                "palette",
                "accent",
                {
                    "position": defense_anchor.get("position", {}),
                    "anchor_type": defense_anchor.get("anchor_type"),
                    "influence_radius_cells": defense_anchor.get("influence_radius_cells"),
                    "related_route_ids": defense_anchor.get("related_route_ids", []),
                    "recommended_tags": defense_anchor.get("recommended_tags", []),
                },
            )
        )
    if resource_hazard_ops:
        add_layer(
            "resource_or_hazard",
            "resource_or_hazard",
            "runtime_semantic",
            True,
            "map_runtime_package",
            resource_hazard_ops,
        )

    blocking_ops: list[dict[str, Any]] = []
    for blocked_area in runtime_package.get("blocked_areas", []):
        if not isinstance(blocked_area, dict):
            continue
        blocked_id = str(blocked_area.get("blocked_area_id") or "blocked_area")
        prefab_id = _prefab_id_any(
            style_pack,
            "blocking_props",
            [
                str(blocked_area.get("visual_hint") or ""),
                str(blocked_area.get("blocked_type") or ""),
                "blocking_prop",
            ],
            "blocking_prop",
        )
        blocking_ops.append(
            _operation(
                f"blocking_{blocked_id}",
                "draw_blocked_cells",
                "blocked_area",
                blocked_id,
                "prefab",
                prefab_id,
                {
                    "cells": blocked_area.get("cells", []),
                    "blocked_type": blocked_area.get("blocked_type"),
                    "blocking_policy": blocked_area.get("blocking_policy"),
                    "visual_hint": blocked_area.get("visual_hint"),
                    "style_component_binding": _prefab_style_binding_any(
                        style_pack,
                        "blocking_props",
                        [
                            str(blocked_area.get("visual_hint") or ""),
                            str(blocked_area.get("blocked_type") or ""),
                            "blocking_prop",
                        ],
                        "blocking_prop",
                    ),
                },
            )
        )
    if blocking_ops:
        add_layer(
            "blocking_prop",
            "blocking_prop",
            "runtime_semantic",
            True,
            "map_runtime_package",
            blocking_ops,
        )

    decorative_prefab = _prefab_id(
        style_pack, "decorative_props", "non_blocking_decoration"
    )
    add_layer(
        "non_blocking_decoration",
        "non_blocking_decoration",
        "visual_style",
        True,
        "map_style_pack",
        [
            _operation(
                "scatter_edge_decoration",
                "scatter_decoration",
                "decoration_zone",
                "non_semantic_edges",
                "prefab",
                decorative_prefab,
                {
                    "allowed_zone": "map_edges_only",
                    "forbidden": ["path_route", "build_slot", "objective"],
                    "style_component_binding": _prefab_style_binding(
                        style_pack, "decorative_props", "non_blocking_decoration"
                    ),
                },
            )
        ],
    )

    atmosphere = _atmosphere_id(style_pack)
    add_layer(
        "fog_light_weather",
        "fog_light_weather",
        "visual_style",
        True,
        "map_style_pack",
        [
            _operation(
                "apply_atmosphere",
                "apply_overlay",
                "none",
                None,
                "atmosphere_layer" if atmosphere else "none",
                atmosphere,
                {"placement_policy": "non_semantic_zones"},
            )
        ],
    )

    add_layer(
        "runtime_interaction_overlay",
        "runtime_interaction_overlay",
        "runtime_overlay",
        True,
        "derived",
        [
            _operation(
                "runtime_drag_overlay",
                "draw_runtime_overlay",
                "runtime_overlay",
                "drag_deploy_and_path_preview",
                "none",
                None,
                runtime_package.get("runtime_hints", {}),
            )
        ],
    )

    add_layer(
        "debug_control_overlay",
        "debug_control_overlay",
        "debug_reference",
        False,
        "derived",
        [
            _operation(
                "debug_grid_and_semantics",
                "draw_runtime_overlay",
                "runtime_overlay",
                "debug_grid_and_semantics",
                "none",
                None,
                {"visible_in_player_default": False},
            )
        ],
    )

    player_default_layer_ids = [
        str(layer["layer_id"]) for layer in layers if layer.get("player_default") is True
    ]
    debug_layer_ids = [
        str(layer["layer_id"])
        for layer in layers
        if layer.get("kind") in PLAYER_FORBIDDEN_LAYER_KINDS
    ]

    plan = {
        "schema_version": "procedural_map_render_plan.v0.1",
        "plan_id": plan_id or f"render_plan_{node_id}_v0_1",
        "map_runtime_package_id": package_id,
        "style_pack_id": style_pack_id,
        "worldbook_id": str(runtime_package.get("worldbook_id") or style_pack.get("worldbook_id") or ""),
        "node_id": node_id,
        "created_at": created_at or now_iso(),
        "source_refs": {
            "map_runtime_package_path": map_runtime_package_path,
            "map_style_pack_path": map_style_pack_path,
            "logic_authority": "map_runtime_package",
            "style_authority": "map_style_pack",
        },
        "canvas": {
            "width": canvas_width,
            "height": canvas_height,
            "safe_area": {"left": 32, "top": 32, "right": 32, "bottom": 32},
        },
        "coordinate_projection": {
            "projection": str(grid.get("projection") or "pseudo3d_oblique"),
            "grid": {
                "width_cells": int(grid.get("width_cells", 1)),
                "height_cells": int(grid.get("height_cells", 1)),
                "cell_size": int(grid.get("cell_size", 64)),
            },
            "mapping": "map_runtime_cell_to_visual_plane",
        },
        "layers": layers,
        "player_default_layer_ids": player_default_layer_ids,
        "debug_layer_ids": debug_layer_ids,
        "validation_report": {
            "gate_status": "passed",
            "runtime_truth_preserved": True,
            "player_default_safe": True,
            "gates": [
                {
                    "gate_id": "runtime_truth_source",
                    "status": "passed",
                    "summary": "Strong semantic operations are derived from MapRuntimePackage.",
                },
                {
                    "gate_id": "style_pack_is_visual_only",
                    "status": "passed",
                    "summary": "MapStylePack contributes materials, prefabs, atmosphere, and readability only.",
                },
                {
                    "gate_id": "debug_layers_not_player_default",
                    "status": "passed",
                    "summary": "Debug/reference layers are excluded from player_default_layer_ids.",
                },
            ],
        },
    }
    return plan


def _ops_by_kind(plan: dict[str, Any], layer_kind: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for layer in plan.get("layers", []):
        if isinstance(layer, dict) and layer.get("kind") == layer_kind:
            result.extend([op for op in layer.get("operations", []) if isinstance(op, dict)])
    return result


def _semantic_ids(ops: list[dict[str, Any]], kind: str) -> set[str]:
    ids: set[str] = set()
    for op in ops:
        ref = op.get("semantic_ref") if isinstance(op, dict) else None
        if isinstance(ref, dict) and ref.get("kind") == kind and ref.get("id"):
            ids.add(str(ref["id"]))
    return ids


def _check(
    check_id: str,
    status: str,
    summary: str,
    refs: list[str],
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "status": status,
        "summary": summary,
        "refs": sorted(set(refs)),
    }


def build_consistency_report(
    runtime_package: dict[str, Any],
    style_pack: dict[str, Any],
    render_plan: dict[str, Any],
    *,
    map_runtime_package_path: str,
    map_style_pack_path: str,
    procedural_map_render_plan_path: str,
    report_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    route_ids = {
        str(route.get("route_id"))
        for route in runtime_package.get("path_routes", [])
        if isinstance(route, dict) and route.get("route_id")
    }
    road_ids = _semantic_ids(_ops_by_kind(render_plan, "road_band"), "path_route")
    missing_routes = sorted(route_ids - road_ids)
    checks.append(
        _check(
            "route_road_band_coverage",
            "failed" if missing_routes else "passed",
            "Every route has a road_band render operation."
            if not missing_routes
            else f"Missing road_band operations for routes: {', '.join(missing_routes)}",
            [f"path_route:{item}" for item in sorted(route_ids)],
        )
    )

    slot_ids = {
        str(slot.get("slot_id"))
        for slot in runtime_package.get("build_slots", [])
        if isinstance(slot, dict) and slot.get("slot_id")
    }
    platform_ids = _semantic_ids(_ops_by_kind(render_plan, "build_slot_platform"), "build_slot")
    missing_slots = sorted(slot_ids - platform_ids)
    checks.append(
        _check(
            "build_slot_platform_coverage",
            "failed" if missing_slots else "passed",
            "Every build slot has a platform render operation."
            if not missing_slots
            else f"Missing platform operations for slots: {', '.join(missing_slots)}",
            [f"build_slot:{item}" for item in sorted(slot_ids)],
        )
    )

    target_ids = set(_target_ids(runtime_package))
    objective_ids = _semantic_ids(_ops_by_kind(render_plan, "objective_foundation"), "objective")
    missing_targets = sorted(target_ids - objective_ids)
    checks.append(
        _check(
            "objective_marker_coverage",
            "failed" if missing_targets else "passed",
            "Every objective has a foundation/marker render operation."
            if not missing_targets
            else f"Missing objective operations for targets: {', '.join(missing_targets)}",
            [f"objective:{item}" for item in sorted(target_ids)],
        )
    )

    spawn_ids = {
        str(spawn.get("spawn_id"))
        for spawn in runtime_package.get("spawn_points", [])
        if isinstance(spawn, dict) and spawn.get("spawn_id")
    }
    marker_ids = _semantic_ids(_ops_by_kind(render_plan, "spawn_atmosphere"), "spawn_point")
    missing_spawns = sorted(spawn_ids - marker_ids)
    checks.append(
        _check(
            "spawn_marker_coverage",
            "failed" if missing_spawns else "passed",
            "Every spawn point has a marker/atmosphere render operation."
            if not missing_spawns
            else f"Missing spawn operations for spawn points: {', '.join(missing_spawns)}",
            [f"spawn_point:{item}" for item in sorted(spawn_ids)],
        )
    )

    resource_ids = {
        str(resource.get("resource_node_id"))
        for resource in runtime_package.get("resource_nodes", [])
        if isinstance(resource, dict) and resource.get("resource_node_id")
    }
    if resource_ids:
        rendered_resource_ids = _semantic_ids(
            _ops_by_kind(render_plan, "resource_or_hazard"), "resource_node"
        )
        missing_resources = sorted(resource_ids - rendered_resource_ids)
        checks.append(
            _check(
                "resource_marker_coverage",
                "failed" if missing_resources else "passed",
                "Every resource node has a visible runtime-semantic render operation."
                if not missing_resources
                else f"Missing resource operations for nodes: {', '.join(missing_resources)}",
                [f"resource_node:{item}" for item in sorted(resource_ids)],
            )
        )

    hazard_ids = {
        str(hazard.get("hazard_zone_id"))
        for hazard in runtime_package.get("hazard_zones", [])
        if isinstance(hazard, dict) and hazard.get("hazard_zone_id")
    }
    if hazard_ids:
        rendered_hazard_ids = _semantic_ids(
            _ops_by_kind(render_plan, "resource_or_hazard"), "hazard_zone"
        )
        missing_hazards = sorted(hazard_ids - rendered_hazard_ids)
        checks.append(
            _check(
                "hazard_zone_coverage",
                "failed" if missing_hazards else "passed",
                "Every hazard zone has a visible runtime-semantic render operation."
                if not missing_hazards
                else f"Missing hazard operations for zones: {', '.join(missing_hazards)}",
                [f"hazard_zone:{item}" for item in sorted(hazard_ids)],
            )
        )

    anchor_ids = {
        str(anchor.get("defense_anchor_id"))
        for anchor in runtime_package.get("defense_anchors", [])
        if isinstance(anchor, dict) and anchor.get("defense_anchor_id")
    }
    if anchor_ids:
        rendered_anchor_ids = _semantic_ids(
            _ops_by_kind(render_plan, "resource_or_hazard"), "defense_anchor"
        )
        missing_anchors = sorted(anchor_ids - rendered_anchor_ids)
        checks.append(
            _check(
                "defense_anchor_marker_coverage",
                "failed" if missing_anchors else "passed",
                "Every defense anchor has a player-default marker operation."
                if not missing_anchors
                else f"Missing defense anchor operations for anchors: {', '.join(missing_anchors)}",
                [f"defense_anchor:{item}" for item in sorted(anchor_ids)],
            )
        )

    blocked_ids = {
        str(blocked.get("blocked_area_id"))
        for blocked in runtime_package.get("blocked_areas", [])
        if isinstance(blocked, dict) and blocked.get("blocked_area_id")
    }
    if blocked_ids:
        rendered_blocked_ids = _semantic_ids(
            _ops_by_kind(render_plan, "blocking_prop"), "blocked_area"
        )
        missing_blocked = sorted(blocked_ids - rendered_blocked_ids)
        checks.append(
            _check(
                "blocked_area_visual_coverage",
                "failed" if missing_blocked else "passed",
                "Every blocked area has a visible blocking_prop render operation."
                if not missing_blocked
                else f"Missing blocking operations for blocked areas: {', '.join(missing_blocked)}",
                [f"blocked_area:{item}" for item in sorted(blocked_ids)],
            )
        )

    player_default = set(map(str, render_plan.get("player_default_layer_ids", [])))
    debug_ids = set(map(str, render_plan.get("debug_layer_ids", [])))
    debug_in_player = sorted(player_default & debug_ids)
    checks.append(
        _check(
            "debug_reference_excluded_from_player_default",
            "failed" if debug_in_player else "passed",
            "Debug/reference layers are excluded from player default layers."
            if not debug_in_player
            else f"Debug layers leaked into player default: {', '.join(debug_in_player)}",
            [f"debug_layer:{item}" for item in sorted(debug_ids)],
        )
    )

    readability = style_pack.get("readability_rules") or {}
    style_ok = (
        readability.get("no_baked_ui_text") is True
        and readability.get("no_baked_enemy_or_tower") is True
        and readability.get("debug_layers_player_default_allowed") is False
    )
    checks.append(
        _check(
            "style_readability_contract",
            "passed" if style_ok else "failed",
            "StylePack forbids baked UI/text/enemies/towers and debug player-default leakage."
            if style_ok
            else "StylePack readability rules do not enforce the required visual safety boundary.",
            ["map_style_pack:readability_rules"],
        )
    )

    failed = [c for c in checks if c.get("status") == "failed"]
    warnings = [c for c in checks if c.get("status") == "warning"]
    status = "failed" if failed else "warning" if warnings else "passed"
    return {
        "schema_version": "semantic_visual_consistency_report.v0.1",
        "report_id": report_id or f"semantic_visual_{render_plan.get('node_id', 'unknown')}_v0_1",
        "render_plan_id": str(render_plan.get("plan_id") or ""),
        "map_runtime_package_id": str(render_plan.get("map_runtime_package_id") or ""),
        "style_pack_id": str(render_plan.get("style_pack_id") or ""),
        "worldbook_id": str(render_plan.get("worldbook_id") or ""),
        "node_id": str(render_plan.get("node_id") or ""),
        "created_at": created_at or now_iso(),
        "source_refs": {
            "map_runtime_package_path": map_runtime_package_path,
            "map_style_pack_path": map_style_pack_path,
            "procedural_map_render_plan_path": procedural_map_render_plan_path,
        },
        "status": status,
        "checks": checks,
        "summary": {
            "passed_count": len([c for c in checks if c.get("status") == "passed"]),
            "warning_count": len(warnings),
            "failed_count": len(failed),
        },
        "blocking_issues": [str(c.get("summary")) for c in failed],
        "warnings": [str(c.get("summary")) for c in warnings],
    }


def validate_style_pack(
    style_pack: dict[str, Any], schema: dict[str, Any] | None = None
) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_with_jsonschema(style_pack, schema))
    scan_forbidden_fields(style_pack, "", errors)
    scan_external_urls(style_pack, "", errors)
    if style_pack.get("schema_version") != "map_style_pack.v0.1":
        errors.append("schema_version must be 'map_style_pack.v0.1'")
    if style_pack.get("source_refs", {}).get("logic_authority") != "map_runtime_package":
        errors.append("source_refs.logic_authority must be 'map_runtime_package'")
    for collection_name in ("terrain_materials", "road_materials"):
        for index, material in enumerate(style_pack.get(collection_name, [])):
            if not isinstance(material, dict):
                continue
            if material.get("texture_policy") == "reviewed_component_required":
                component_ref = material.get("component_ref")
                if not isinstance(component_ref, str) or not component_ref.strip():
                    errors.append(
                        f"{collection_name}[{index}].component_ref must be non-empty when texture_policy is reviewed_component_required"
                    )
    prefab_collection_names = (
        "build_slot_platforms",
        "objective_prefabs",
        "spawn_prefabs",
        "resource_prefabs",
        "hazard_prefabs",
        "blocking_props",
        "non_blocking_props",
        "decorative_props",
    )
    for collection_name in prefab_collection_names:
        for index, prefab in enumerate(style_pack.get(collection_name, [])):
            if not isinstance(prefab, dict):
                continue
            visual_ref = prefab.get("visual_ref")
            if not isinstance(visual_ref, dict):
                continue
            if visual_ref.get("kind") == "reviewed_component_ref":
                value = visual_ref.get("value")
                if not isinstance(value, str) or not value.strip():
                    errors.append(
                        f"{collection_name}[{index}].visual_ref.value must be non-empty when visual_ref.kind is reviewed_component_ref"
                    )
    rules = style_pack.get("readability_rules")
    if isinstance(rules, dict):
        if rules.get("no_baked_ui_text") is not True:
            errors.append("readability_rules.no_baked_ui_text must be true")
        if rules.get("no_baked_enemy_or_tower") is not True:
            errors.append("readability_rules.no_baked_enemy_or_tower must be true")
        if rules.get("debug_layers_player_default_allowed") is not False:
            errors.append(
                "readability_rules.debug_layers_player_default_allowed must be false"
            )
    report = style_pack.get("validation_report")
    if isinstance(report, dict):
        if report.get("style_only") is not True:
            errors.append("validation_report.style_only must be true")
        gate_ids = {
            str(gate.get("gate_id"))
            for gate in report.get("gates", [])
            if isinstance(gate, dict)
        }
        if "style_only_visual_boundary" not in gate_ids:
            errors.append("validation_report.gates must include style_only_visual_boundary")
    return list(dict.fromkeys(errors))


def validate_render_plan(
    render_plan: dict[str, Any], schema: dict[str, Any] | None = None
) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_with_jsonschema(render_plan, schema))
    scan_forbidden_fields(render_plan, "", errors)
    scan_external_urls(render_plan, "", errors)
    if render_plan.get("schema_version") != "procedural_map_render_plan.v0.1":
        errors.append("schema_version must be 'procedural_map_render_plan.v0.1'")
    layers = [layer for layer in render_plan.get("layers", []) if isinstance(layer, dict)]
    layer_ids = {str(layer.get("layer_id")) for layer in layers if layer.get("layer_id")}
    layer_kinds = {str(layer.get("kind")) for layer in layers if layer.get("kind")}
    missing_kinds = sorted(REQUIRED_RENDER_LAYER_KINDS - layer_kinds)
    if missing_kinds:
        errors.append(f"render plan missing required layer kinds: {', '.join(missing_kinds)}")
    player_default = set(map(str, render_plan.get("player_default_layer_ids", [])))
    debug_ids = set(map(str, render_plan.get("debug_layer_ids", [])))
    unknown_player = sorted(player_default - layer_ids)
    unknown_debug = sorted(debug_ids - layer_ids)
    if unknown_player:
        errors.append(f"player_default_layer_ids contain unknown layers: {', '.join(unknown_player)}")
    if unknown_debug:
        errors.append(f"debug_layer_ids contain unknown layers: {', '.join(unknown_debug)}")
    leaked = sorted(player_default & debug_ids)
    if leaked:
        errors.append(f"debug/reference layers leaked into player default: {', '.join(leaked)}")
    for layer in layers:
        if layer.get("layer_id") in player_default and layer.get("kind") in PLAYER_FORBIDDEN_LAYER_KINDS:
            errors.append(f"player default layer {layer.get('layer_id')} has debug/reference kind")
        if layer.get("authority") == "debug_reference" and layer.get("player_default") is True:
            errors.append(f"debug_reference layer {layer.get('layer_id')} cannot be player_default")
        for operation in layer.get("operations", []):
            if not isinstance(operation, dict):
                continue
            semantic_ref = operation.get("semantic_ref")
            if not isinstance(semantic_ref, dict):
                continue
            for ref_key in ("kind", "id"):
                ref_value = semantic_ref.get(ref_key)
                if isinstance(ref_value, str) and (
                    ref_value.startswith("media:") or ref_value.startswith("atlas:")
                ):
                    errors.append(
                        f"{operation.get('op_id')}.semantic_ref.{ref_key} must not contain media or atlas refs"
                    )
    report = render_plan.get("validation_report")
    if isinstance(report, dict):
        if report.get("runtime_truth_preserved") is not True:
            errors.append("validation_report.runtime_truth_preserved must be true")
        gate_ids = {
            str(gate.get("gate_id"))
            for gate in report.get("gates", [])
            if isinstance(gate, dict)
        }
        for required in (
            "runtime_truth_source",
            "style_pack_is_visual_only",
            "debug_layers_not_player_default",
        ):
            if required not in gate_ids:
                errors.append(f"validation_report.gates must include {required}")
    return list(dict.fromkeys(errors))


def validate_consistency_report(
    report: dict[str, Any],
    schema: dict[str, Any] | None = None,
    *,
    render_plan: dict[str, Any] | None = None,
    runtime_package: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_with_jsonschema(report, schema))
    scan_forbidden_fields(report, "", errors)
    scan_external_urls(report, "", errors)
    if report.get("schema_version") != "semantic_visual_consistency_report.v0.1":
        errors.append("schema_version must be 'semantic_visual_consistency_report.v0.1'")
    checks = [check for check in report.get("checks", []) if isinstance(check, dict)]
    check_ids = {str(check.get("check_id")) for check in checks if check.get("check_id")}
    missing_checks = sorted(REQUIRED_REPORT_CHECKS - check_ids)
    if missing_checks:
        errors.append(f"report missing required checks: {', '.join(missing_checks)}")
    counts = {
        "passed_count": len([c for c in checks if c.get("status") == "passed"]),
        "warning_count": len([c for c in checks if c.get("status") == "warning"]),
        "failed_count": len([c for c in checks if c.get("status") == "failed"]),
    }
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    for key, expected in counts.items():
        if summary.get(key) != expected:
            errors.append(f"summary.{key} must be {expected}")
    expected_status = (
        "failed"
        if counts["failed_count"]
        else "warning"
        if counts["warning_count"]
        else "passed"
    )
    if report.get("status") != expected_status:
        errors.append(f"status must be {expected_status!r} based on check counts")
    if render_plan is not None and report.get("render_plan_id") != render_plan.get("plan_id"):
        errors.append("render_plan_id must match provided render plan")
    if runtime_package is not None and report.get("map_runtime_package_id") != runtime_package.get("package_id"):
        errors.append("map_runtime_package_id must match provided runtime package")
    return list(dict.fromkeys(errors))
