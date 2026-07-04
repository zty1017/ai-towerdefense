"""Builder and validator for MapRuntimePackage v0.1.

MapRuntimePackage is the runtime-safe logical map contract for battles. It
keeps path routes, build slots, objectives, spawn points, and visual layer
references explicit so the frontend does not need to infer gameplay facts from
painted images.

Safety rules:

1. Reject unknown top-level and nested keys for the v0.1 shape.
2. Reject provider/trace/raw/secret-like fields anywhere.
3. Reject external URLs anywhere.
4. Keep visual layers local to /assets/map_visual_reference/.
5. Check all gameplay coordinates are inside the declared grid.
6. Check build slots do not overlap path cells or objectives.

This module never reads .env and never calls model or media providers.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

try:
    import map_path_geometry
except ModuleNotFoundError:  # pragma: no cover - supports package-style imports.
    from tools.asset_graph import map_path_geometry  # type: ignore


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

TOP_LEVEL_ALLOWED = frozenset(
    {
        "schema_version",
        "package_id",
        "worldbook_id",
        "node_id",
        "battle_config_version",
        "created_at",
        "source_refs",
        "grid",
        "path_routes",
        "build_slots",
        "objectives",
        "spawn_points",
        "visual_layers",
        "runtime_hints",
        "validation_report",
    }
)
SOURCE_REFS_ALLOWED = frozenset(
    {"battle_config_path", "visual_reference_manifest_path", "logic_authority"}
)
GRID_ALLOWED = frozenset({"projection", "width_cells", "height_cells", "cell_size"})
POINT_ALLOWED = frozenset({"x", "y"})
PATH_ROUTE_ALLOWED = frozenset(
    {"route_id", "display_name", "waypoints", "entry_label", "exit_label"}
)
BUILD_SLOT_ALLOWED = frozenset(
    {
        "slot_id",
        "position",
        "footprint",
        "allowed_asset_kinds",
        "placement_tags",
        "visual_hint",
    }
)
FOOTPRINT_ALLOWED = frozenset({"width_cells", "height_cells"})
OBJECTIVES_ALLOWED = frozenset({"core_target", "optional_targets"})
TARGET_ALLOWED = frozenset({"target_id", "display_name", "position", "durability"})
SPAWN_POINT_ALLOWED = frozenset({"spawn_id", "route_id", "position", "label"})
VISUAL_LAYER_ALLOWED = frozenset(
    {
        "layer_id",
        "role",
        "url",
        "local_path",
        "width",
        "height",
        "sha256",
        "authority",
        "review_status",
        "player_visible_quality",
        "logic_alignment_status",
    }
)
RUNTIME_HINTS_ALLOWED = frozenset(
    {
        "drag_deploy_enabled",
        "show_grid_policy",
        "path_preview_policy",
        "target_marker_policy",
    }
)
VALIDATION_REPORT_ALLOWED = frozenset({"gate_status", "runtime_loadable", "gates"})
VALIDATION_GATE_ALLOWED = frozenset({"gate_id", "status", "summary"})

ASSET_KINDS = frozenset(
    {"tower_blueprint", "temporary_trap_sample", "support_item", "temporary_mod"}
)
VISUAL_HINTS = frozenset({"ground_plate", "ruin_plinth", "roadside_marker"})
VISUAL_ROLES = frozenset(
    {
        "battle_control_sketch",
        "battle_reference_board",
        "battle_runtime_background",
        "painted_visual_layer",
        "strategic_control_sketch",
    }
)
VISUAL_AUTHORITIES = frozenset(
    {"reference_only", "published_visual_layer", "candidate_visual_layer"}
)
PLAYER_VISIBLE_QUALITIES = frozenset(
    {"passed", "warning", "failed", "not_applicable"}
)
LOGIC_ALIGNMENT_STATUSES = frozenset(
    {"passed", "needs_overlay_correction", "failed", "not_checked", "not_applicable"}
)
LOGIC_AUTHORITIES = frozenset({"battle_config", "certified_map_template"})
SHOW_GRID_POLICIES = frozenset({"hidden_until_drag", "subtle_overlay", "debug_only"})
PATH_PREVIEW_POLICIES = frozenset(
    {"subtle_highlight", "always_visible", "debug_only"}
)
TARGET_MARKER_POLICIES = frozenset(
    {"icon_overlay", "diegetic_marker", "debug_only"}
)
GATE_STATUSES = frozenset({"passed", "failed", "warning"})

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def reject_unknown_keys(
    obj: dict[str, Any], allowed: frozenset[str], path: str, errors: list[str]
) -> None:
    for key in obj:
        if key not in allowed:
            loc = f"{path}.{key}" if path else key
            errors.append(f"unknown field '{loc}' is not allowed")


def require_object(value: Any, path: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{path} must be an object")
        return {}
    return value


def require_string(value: Any, path: str, errors: list[str]) -> str:
    if not isinstance(value, str) or not value:
        errors.append(f"{path} must be a non-empty string")
        return ""
    return value


def require_int(value: Any, path: str, errors: list[str], minimum: int | None = None) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        errors.append(f"{path} must be an integer")
        return 0
    if minimum is not None and value < minimum:
        errors.append(f"{path} must be >= {minimum}")
    return value


def require_enum(
    value: Any, allowed: frozenset[str], path: str, errors: list[str]
) -> None:
    if value not in allowed:
        errors.append(f"{path}={value!r} must be one of {sorted(allowed)}")


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
        for marker in FORBIDDEN_URL_MARKERS:
            if marker in lowered:
                errors.append(f"{path}={value!r} must not contain '{marker}'")
                break


def _point_key(point: dict[str, Any]) -> tuple[int, int]:
    return (int(point.get("x", 0)), int(point.get("y", 0)))


def _in_grid(point: tuple[int, int], grid: dict[str, Any]) -> bool:
    width = int(grid.get("width_cells", 0))
    height = int(grid.get("height_cells", 0))
    x, y = point
    return 0 <= x < width and 0 <= y < height


def _segment_cells(a: tuple[int, int], b: tuple[int, int]) -> list[tuple[int, int]]:
    ax, ay = a
    bx, by = b
    dx = 0 if bx == ax else (1 if bx > ax else -1)
    dy = 0 if by == ay else (1 if by > ay else -1)
    steps = max(abs(bx - ax), abs(by - ay))
    return [(ax + dx * step, ay + dy * step) for step in range(steps + 1)]


def path_cells(path_routes: list[dict[str, Any]]) -> set[tuple[int, int]]:
    blocked: set[tuple[int, int]] = set()
    for route in path_routes:
        points = [_point_key(p) for p in route.get("waypoints", []) if isinstance(p, dict)]
        for index, point in enumerate(points):
            blocked.add(point)
            if index > 0:
                blocked.update(_segment_cells(points[index - 1], point))
    return blocked


def _normalize_point(raw: Any) -> dict[str, int]:
    if not isinstance(raw, dict):
        return {"x": 0, "y": 0}
    return {"x": int(raw.get("x", 0)), "y": int(raw.get("y", 0))}


def _target_from_config(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "target_id": str(raw.get("stable_internal_id", "target_unknown")),
        "display_name": str(raw.get("display_name", "Target")),
        "position": _normalize_point(raw.get("position")),
        "durability": int(raw.get("durability", 1)),
    }


def _build_path_routes(battle_config: dict[str, Any]) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    for index, raw in enumerate(battle_config.get("paths", [])):
        if not isinstance(raw, dict):
            continue
        route_id = str(raw.get("stable_internal_id") or f"path_{index + 1}")
        routes.append(
            {
                "route_id": route_id,
                "display_name": str(raw.get("display_name") or route_id),
                "waypoints": [
                    _normalize_point(p)
                    for p in raw.get("waypoints", [])
                    if isinstance(p, dict)
                ],
                "entry_label": str(raw.get("entry_label") or "enemy entry"),
                "exit_label": str(raw.get("exit_label") or "defense target"),
            }
        )
    return routes


def _derive_build_slots(
    grid: dict[str, Any],
    routes: list[dict[str, Any]],
    objectives: dict[str, Any],
    *,
    max_slots: int = 12,
) -> list[dict[str, Any]]:
    blocked = path_cells(routes)
    objective_points: set[tuple[int, int]] = set()
    core = objectives.get("core_target")
    if isinstance(core, dict):
        objective_points.add(_point_key(core.get("position", {})))
    for target in objectives.get("optional_targets", []):
        if isinstance(target, dict):
            objective_points.add(_point_key(target.get("position", {})))
    blocked.update(objective_points)

    candidates: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    offsets = [
        (0, -1),
        (0, 1),
        (-1, 0),
        (1, 0),
        (-1, -1),
        (1, -1),
        (-1, 1),
        (1, 1),
    ]
    for route in routes:
        for waypoint in route.get("waypoints", []):
            wx, wy = _point_key(waypoint)
            for ox, oy in offsets:
                candidate = (wx + ox, wy + oy)
                if candidate in seen or candidate in blocked:
                    continue
                if not _in_grid(candidate, grid):
                    continue
                seen.add(candidate)
                candidates.append(candidate)
                if len(candidates) >= max_slots:
                    break
            if len(candidates) >= max_slots:
                break
        if len(candidates) >= max_slots:
            break

    slots: list[dict[str, Any]] = []
    for index, (x, y) in enumerate(candidates, start=1):
        slots.append(
            {
                "slot_id": f"slot_{index:02d}",
                "position": {"x": x, "y": y},
                "footprint": {"width_cells": 1, "height_cells": 1},
                "allowed_asset_kinds": [
                    "tower_blueprint",
                    "temporary_trap_sample",
                    "support_item",
                ],
                "placement_tags": ["near_path", "mvp_auto_derived"],
                "visual_hint": "ground_plate",
            }
        )
    return slots


def _build_visual_layers(visual_manifest: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(visual_manifest, dict):
        return []
    layers: list[dict[str, Any]] = []
    for item in visual_manifest.get("items", []):
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", ""))
        if role not in VISUAL_ROLES:
            continue
        layer = {
            "layer_id": f"layer_{role}",
            "role": role,
            "url": str(item.get("url", "")),
            "local_path": str(item.get("local_path", "")),
            "width": int(item.get("width", 1)),
            "height": int(item.get("height", 1)),
            "sha256": str(item.get("sha256", "")),
            "authority": str(item.get("authority") or "reference_only"),
        }
        for key in ("review_status", "player_visible_quality", "logic_alignment_status"):
            if item.get(key):
                layer[key] = str(item[key])
        layers.append(layer)
    return layers


def build_map_runtime_package(
    battle_config: dict[str, Any],
    *,
    battle_config_path: str,
    visual_reference_manifest: dict[str, Any] | None = None,
    visual_reference_manifest_path: str | None = None,
    package_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build a MapRuntimePackage v0.1 from a battle config."""
    grid = dict(battle_config.get("grid") or {})
    routes = _build_path_routes(battle_config)
    objectives = {
        "core_target": _target_from_config(dict(battle_config.get("core_target") or {})),
        "optional_targets": [
            _target_from_config(t)
            for t in battle_config.get("optional_targets", [])
            if isinstance(t, dict)
        ],
    }
    node_id = str(battle_config.get("node_id", "unknown_node"))
    version = str(battle_config.get("battle_config_version", "battle_config.v0.1"))
    source_refs = {
        "battle_config_path": battle_config_path,
        "logic_authority": "battle_config",
    }
    if visual_reference_manifest_path:
        source_refs["visual_reference_manifest_path"] = visual_reference_manifest_path

    spawn_points: list[dict[str, Any]] = []
    for route in routes:
        waypoints = route.get("waypoints", [])
        if not waypoints:
            continue
        spawn_points.append(
            {
                "spawn_id": f"spawn_{route['route_id']}",
                "route_id": route["route_id"],
                "position": waypoints[0],
                "label": route.get("entry_label", "enemy entry"),
            }
        )

    package = {
        "schema_version": "map_runtime_package.v0.1",
        "package_id": package_id or f"map_pkg_{node_id}_v0_1",
        "worldbook_id": str(battle_config.get("worldbook_id", "")),
        "node_id": node_id,
        "battle_config_version": version,
        "created_at": created_at or now_iso(),
        "source_refs": source_refs,
        "grid": grid,
        "path_routes": routes,
        "build_slots": _derive_build_slots(grid, routes, objectives),
        "objectives": objectives,
        "spawn_points": spawn_points,
        "visual_layers": _build_visual_layers(visual_reference_manifest),
        "runtime_hints": {
            "drag_deploy_enabled": True,
            "show_grid_policy": "hidden_until_drag",
            "path_preview_policy": "subtle_highlight",
            "target_marker_policy": "icon_overlay",
        },
        "validation_report": {
            "gate_status": "passed",
            "runtime_loadable": True,
            "gates": [
                {
                    "gate_id": "logic_first_map_contract",
                    "status": "passed",
                    "summary": "Routes, objectives, spawn points, and build slots are explicit runtime data.",
                }
            ],
        },
    }
    return package


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
    return [f"schema: {'.'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in sorted(validator.iter_errors(package), key=str)]


def validate_package(package: dict[str, Any], schema: dict[str, Any] | None = None) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_with_jsonschema(package, schema))
    errors.extend(validate_pure_python(package))
    scan_forbidden_fields(package, "", errors)
    scan_external_urls(package, "", errors)
    return list(dict.fromkeys(errors))


def placement_review_warnings(package: dict[str, Any]) -> list[str]:
    """Return non-fatal placement geometry warnings for review output."""
    return map_path_geometry.placement_warning_messages(package)


def validate_pure_python(package: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    reject_unknown_keys(package, TOP_LEVEL_ALLOWED, "", errors)
    for key in TOP_LEVEL_ALLOWED:
        if key not in package:
            errors.append(f"missing top-level key: {key}")
    if package.get("schema_version") != "map_runtime_package.v0.1":
        errors.append("schema_version must be 'map_runtime_package.v0.1'")
    for key in ("package_id", "worldbook_id", "node_id", "battle_config_version"):
        require_string(package.get(key), key, errors)
    created_at = package.get("created_at")
    if not isinstance(created_at, str) or not DATETIME_RE.match(created_at):
        errors.append("created_at must be an ISO-8601 datetime string")

    source_refs = require_object(package.get("source_refs"), "source_refs", errors)
    if source_refs:
        reject_unknown_keys(source_refs, SOURCE_REFS_ALLOWED, "source_refs", errors)
        require_string(source_refs.get("battle_config_path"), "source_refs.battle_config_path", errors)
        require_enum(source_refs.get("logic_authority"), LOGIC_AUTHORITIES, "source_refs.logic_authority", errors)
        if "visual_reference_manifest_path" in source_refs:
            require_string(source_refs.get("visual_reference_manifest_path"), "source_refs.visual_reference_manifest_path", errors)

    grid = validate_grid(package.get("grid"), "grid", errors)
    routes = validate_routes(package.get("path_routes"), grid, errors)
    objectives = validate_objectives(package.get("objectives"), grid, errors)
    validate_spawn_points(package.get("spawn_points"), routes, grid, errors)
    validate_build_slots(package.get("build_slots"), routes, objectives, grid, errors)
    validate_visual_layers(package.get("visual_layers"), errors)
    validate_runtime_hints(package.get("runtime_hints"), errors)
    validate_report(package.get("validation_report"), errors)
    return errors


def validate_grid(raw: Any, path: str, errors: list[str]) -> dict[str, Any]:
    grid = require_object(raw, path, errors)
    if not grid:
        return {}
    reject_unknown_keys(grid, GRID_ALLOWED, path, errors)
    require_string(grid.get("projection"), f"{path}.projection", errors)
    require_int(grid.get("width_cells"), f"{path}.width_cells", errors, 1)
    require_int(grid.get("height_cells"), f"{path}.height_cells", errors, 1)
    require_int(grid.get("cell_size"), f"{path}.cell_size", errors, 1)
    return grid


def validate_point(raw: Any, path: str, grid: dict[str, Any], errors: list[str]) -> tuple[int, int]:
    point = require_object(raw, path, errors)
    if not point:
        return (0, 0)
    reject_unknown_keys(point, POINT_ALLOWED, path, errors)
    x = require_int(point.get("x"), f"{path}.x", errors)
    y = require_int(point.get("y"), f"{path}.y", errors)
    if grid and not _in_grid((x, y), grid):
        errors.append(f"{path}=({x},{y}) must be inside grid")
    return (x, y)


def validate_routes(raw: Any, grid: dict[str, Any], errors: list[str]) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        errors.append("path_routes must be a non-empty array")
        return []
    routes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, route_raw in enumerate(raw):
        path = f"path_routes[{index}]"
        route = require_object(route_raw, path, errors)
        if not route:
            continue
        reject_unknown_keys(route, PATH_ROUTE_ALLOWED, path, errors)
        route_id = require_string(route.get("route_id"), f"{path}.route_id", errors)
        if route_id in seen:
            errors.append(f"{path}.route_id={route_id!r} is duplicated")
        seen.add(route_id)
        require_string(route.get("display_name"), f"{path}.display_name", errors)
        require_string(route.get("entry_label"), f"{path}.entry_label", errors)
        require_string(route.get("exit_label"), f"{path}.exit_label", errors)
        waypoints = route.get("waypoints")
        if not isinstance(waypoints, list) or len(waypoints) < 2:
            errors.append(f"{path}.waypoints must contain at least 2 points")
        else:
            for p_index, point in enumerate(waypoints):
                validate_point(point, f"{path}.waypoints[{p_index}]", grid, errors)
        routes.append(route)
    return routes


def validate_target(raw: Any, path: str, grid: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    target = require_object(raw, path, errors)
    if not target:
        return {}
    reject_unknown_keys(target, TARGET_ALLOWED, path, errors)
    require_string(target.get("target_id"), f"{path}.target_id", errors)
    require_string(target.get("display_name"), f"{path}.display_name", errors)
    validate_point(target.get("position"), f"{path}.position", grid, errors)
    require_int(target.get("durability"), f"{path}.durability", errors, 1)
    return target


def validate_objectives(raw: Any, grid: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    objectives = require_object(raw, "objectives", errors)
    if not objectives:
        return {}
    reject_unknown_keys(objectives, OBJECTIVES_ALLOWED, "objectives", errors)
    validate_target(objectives.get("core_target"), "objectives.core_target", grid, errors)
    optional = objectives.get("optional_targets")
    if not isinstance(optional, list):
        errors.append("objectives.optional_targets must be an array")
    else:
        for index, target in enumerate(optional):
            validate_target(target, f"objectives.optional_targets[{index}]", grid, errors)
    return objectives


def validate_spawn_points(
    raw: Any, routes: list[dict[str, Any]], grid: dict[str, Any], errors: list[str]
) -> None:
    route_ids = {str(r.get("route_id")) for r in routes}
    if not isinstance(raw, list) or not raw:
        errors.append("spawn_points must be a non-empty array")
        return
    for index, raw_spawn in enumerate(raw):
        path = f"spawn_points[{index}]"
        spawn = require_object(raw_spawn, path, errors)
        if not spawn:
            continue
        reject_unknown_keys(spawn, SPAWN_POINT_ALLOWED, path, errors)
        require_string(spawn.get("spawn_id"), f"{path}.spawn_id", errors)
        route_id = require_string(spawn.get("route_id"), f"{path}.route_id", errors)
        if route_id not in route_ids:
            errors.append(f"{path}.route_id={route_id!r} does not match a route")
        validate_point(spawn.get("position"), f"{path}.position", grid, errors)
        require_string(spawn.get("label"), f"{path}.label", errors)


def validate_build_slots(
    raw: Any,
    routes: list[dict[str, Any]],
    objectives: dict[str, Any],
    grid: dict[str, Any],
    errors: list[str],
) -> None:
    if not isinstance(raw, list) or not raw:
        errors.append("build_slots must be a non-empty array")
        return
    blocked = path_cells(routes)
    core = objectives.get("core_target") if isinstance(objectives, dict) else None
    if isinstance(core, dict):
        blocked.add(_point_key(core.get("position", {})))
    for target in objectives.get("optional_targets", []) if isinstance(objectives, dict) else []:
        if isinstance(target, dict):
            blocked.add(_point_key(target.get("position", {})))
    seen_ids: set[str] = set()
    seen_positions: set[tuple[int, int]] = set()
    for index, raw_slot in enumerate(raw):
        path = f"build_slots[{index}]"
        slot = require_object(raw_slot, path, errors)
        if not slot:
            continue
        reject_unknown_keys(slot, BUILD_SLOT_ALLOWED, path, errors)
        slot_id = require_string(slot.get("slot_id"), f"{path}.slot_id", errors)
        if slot_id in seen_ids:
            errors.append(f"{path}.slot_id={slot_id!r} is duplicated")
        seen_ids.add(slot_id)
        position = validate_point(slot.get("position"), f"{path}.position", grid, errors)
        if position in seen_positions:
            errors.append(f"{path}.position={position!r} is duplicated")
        seen_positions.add(position)
        if position in blocked:
            errors.append(f"{path}.position={position!r} overlaps path or objective")
        footprint = require_object(slot.get("footprint"), f"{path}.footprint", errors)
        if footprint:
            reject_unknown_keys(footprint, FOOTPRINT_ALLOWED, f"{path}.footprint", errors)
            require_int(footprint.get("width_cells"), f"{path}.footprint.width_cells", errors, 1)
            require_int(footprint.get("height_cells"), f"{path}.footprint.height_cells", errors, 1)
        kinds = slot.get("allowed_asset_kinds")
        if not isinstance(kinds, list) or not kinds:
            errors.append(f"{path}.allowed_asset_kinds must be a non-empty array")
        else:
            for k_index, kind in enumerate(kinds):
                require_enum(kind, ASSET_KINDS, f"{path}.allowed_asset_kinds[{k_index}]", errors)
        tags = slot.get("placement_tags")
        if not isinstance(tags, list):
            errors.append(f"{path}.placement_tags must be an array")
        elif not all(isinstance(tag, str) and tag for tag in tags):
            errors.append(f"{path}.placement_tags must contain non-empty strings")
        require_enum(slot.get("visual_hint"), VISUAL_HINTS, f"{path}.visual_hint", errors)


def validate_visual_layers(raw: Any, errors: list[str]) -> None:
    if not isinstance(raw, list):
        errors.append("visual_layers must be an array")
        return
    for index, raw_layer in enumerate(raw):
        path = f"visual_layers[{index}]"
        layer = require_object(raw_layer, path, errors)
        if not layer:
            continue
        reject_unknown_keys(layer, VISUAL_LAYER_ALLOWED, path, errors)
        require_string(layer.get("layer_id"), f"{path}.layer_id", errors)
        require_enum(layer.get("role"), VISUAL_ROLES, f"{path}.role", errors)
        url = require_string(layer.get("url"), f"{path}.url", errors)
        if url and not url.startswith("/assets/map_visual_reference/"):
            errors.append(f"{path}.url must start with /assets/map_visual_reference/")
        require_string(layer.get("local_path"), f"{path}.local_path", errors)
        require_int(layer.get("width"), f"{path}.width", errors, 1)
        require_int(layer.get("height"), f"{path}.height", errors, 1)
        sha = require_string(layer.get("sha256"), f"{path}.sha256", errors)
        if sha and not SHA256_RE.match(sha):
            errors.append(f"{path}.sha256 must be a 64-character sha256 hex")
        authority = layer.get("authority")
        require_enum(authority, VISUAL_AUTHORITIES, f"{path}.authority", errors)
        quality = layer.get("player_visible_quality")
        if quality is not None:
            require_enum(quality, PLAYER_VISIBLE_QUALITIES, f"{path}.player_visible_quality", errors)
        alignment = layer.get("logic_alignment_status")
        if alignment is not None:
            require_enum(alignment, LOGIC_ALIGNMENT_STATUSES, f"{path}.logic_alignment_status", errors)
        if layer.get("role") in {"painted_visual_layer", "battle_runtime_background"}:
            if authority == "published_visual_layer" and quality != "passed":
                errors.append(f"{path} published player layer must have player_visible_quality=passed")
            if authority != "published_visual_layer" and quality == "passed":
                errors.append(f"{path} passed player quality requires published_visual_layer authority")


def validate_runtime_hints(raw: Any, errors: list[str]) -> None:
    hints = require_object(raw, "runtime_hints", errors)
    if not hints:
        return
    reject_unknown_keys(hints, RUNTIME_HINTS_ALLOWED, "runtime_hints", errors)
    if not isinstance(hints.get("drag_deploy_enabled"), bool):
        errors.append("runtime_hints.drag_deploy_enabled must be a boolean")
    require_enum(hints.get("show_grid_policy"), SHOW_GRID_POLICIES, "runtime_hints.show_grid_policy", errors)
    require_enum(hints.get("path_preview_policy"), PATH_PREVIEW_POLICIES, "runtime_hints.path_preview_policy", errors)
    require_enum(hints.get("target_marker_policy"), TARGET_MARKER_POLICIES, "runtime_hints.target_marker_policy", errors)


def validate_report(raw: Any, errors: list[str]) -> None:
    report = require_object(raw, "validation_report", errors)
    if not report:
        return
    reject_unknown_keys(report, VALIDATION_REPORT_ALLOWED, "validation_report", errors)
    require_enum(report.get("gate_status"), GATE_STATUSES, "validation_report.gate_status", errors)
    if not isinstance(report.get("runtime_loadable"), bool):
        errors.append("validation_report.runtime_loadable must be a boolean")
    gates = report.get("gates")
    if not isinstance(gates, list):
        errors.append("validation_report.gates must be an array")
        return
    for index, raw_gate in enumerate(gates):
        path = f"validation_report.gates[{index}]"
        gate = require_object(raw_gate, path, errors)
        if not gate:
            continue
        reject_unknown_keys(gate, VALIDATION_GATE_ALLOWED, path, errors)
        require_string(gate.get("gate_id"), f"{path}.gate_id", errors)
        require_enum(gate.get("status"), GATE_STATUSES, f"{path}.status", errors)
        require_string(gate.get("summary"), f"{path}.summary", errors)
