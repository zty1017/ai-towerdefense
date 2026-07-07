#!/usr/bin/env python3
"""Render a review-only SVG preview from MapRuntimePackage + RenderPlan.

This tool is intentionally stdlib-only. It proves that a
ProceduralMapRenderPlan is executable as a deterministic presentation plan
without letting the plan become gameplay truth:

- route, slot, objective, and spawn coordinates come from MapRuntimePackage;
- visual colors come from MapStylePack;
- road width, shoulder width, and slot footprint come from ProceduralMapRenderPlan.

The SVG is a review/evidence artifact, not a published player background.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNTIME_PACKAGE = ROOT / "examples/map_runtime_packages/mvp_first_battle.map_runtime_package.json"
DEFAULT_STYLE_PACK = ROOT / "examples/map_style_packs/long_night_ruined_outpost.map_style_pack.json"
DEFAULT_RENDER_PLAN = ROOT / "examples/map_render_plans/mvp_first_battle.procedural_map_render_plan.json"
DEFAULT_DECORATION_POLICY = ROOT / "examples/map_decoration_zone_policies/mvp_map_decoration_zone_policy.v0.1.json"
DEFAULT_OUTPUT = ROOT / "examples/map_render_previews/mvp_first_battle.procedural_map_preview.svg"
DEFAULT_REPORT = ROOT / "examples/map_render_previews/mvp_first_battle.procedural_map_preview_report.json"

try:
    from validate_map_decoration_zone_policy import validate as validate_decoration_policy
except ModuleNotFoundError:  # pragma: no cover - supports package-style imports.
    from tools.asset_graph.validate_map_decoration_zone_policy import validate as validate_decoration_policy  # type: ignore


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else ROOT / value


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def svg_escape(value: Any) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def palette(style_pack: dict[str, Any], key: str, fallback: str) -> str:
    value = as_obj(style_pack.get("palette")).get(key)
    if isinstance(value, str) and len(value) == 7 and value.startswith("#"):
        return value
    return fallback


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    text = value.strip().lstrip("#")
    if len(text) != 6:
        return (120, 120, 120)
    return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))


def mix_hex(a: str, b: str, t: float) -> str:
    ar, ag, ab = hex_to_rgb(a)
    br, bg, bb = hex_to_rgb(b)
    ratio = clamp(t, 0, 1)
    return "#{:02X}{:02X}{:02X}".format(
        round(ar + (br - ar) * ratio),
        round(ag + (bg - ag) * ratio),
        round(ab + (bb - ab) * ratio),
    )


def render_plan_layers(render_plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [layer for layer in as_list(render_plan.get("layers")) if isinstance(layer, dict)]


def render_plan_operations(render_plan: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    for layer in render_plan_layers(render_plan):
        if layer.get("kind") == kind:
            return [op for op in as_list(layer.get("operations")) if isinstance(op, dict)]
    return []


def render_plan_operation(
    render_plan: dict[str, Any],
    kind: str,
    semantic_kind: str,
    semantic_id: str | None,
) -> dict[str, Any] | None:
    for operation in render_plan_operations(render_plan, kind):
        semantic_ref = as_obj(operation.get("semantic_ref"))
        if semantic_ref.get("kind") == semantic_kind and semantic_ref.get("id") == semantic_id:
            return operation
    return None


def geometry_number(operation: dict[str, Any] | None, key: str, fallback: float, low: float, high: float) -> float:
    value = as_obj(operation.get("geometry") if operation else {}).get(key)
    try:
        return clamp(float(value), low, high)
    except (TypeError, ValueError):
        return fallback


def route_width_cells(render_plan: dict[str, Any], route: dict[str, Any]) -> float:
    operation = render_plan_operation(render_plan, "road_band", "path_route", str(route.get("route_id") or ""))
    return geometry_number(operation, "width_cells", 0.48, 0.42, 0.95)


def route_shoulder_scale(render_plan: dict[str, Any], route: dict[str, Any]) -> float:
    operation = render_plan_operation(render_plan, "road_edge", "path_route", str(route.get("route_id") or ""))
    width_cells = geometry_number(operation, "shoulder_width_cells", 0.25, 0.12, 0.44)
    return clamp(width_cells / 0.25, 0.72, 1.58)


def slot_footprint(render_plan: dict[str, Any], slot: dict[str, Any]) -> tuple[float, float]:
    operation = render_plan_operation(render_plan, "build_slot_platform", "build_slot", str(slot.get("slot_id") or ""))
    footprint = as_obj(as_obj(operation.get("geometry") if operation else {}).get("footprint"))
    try:
        width = clamp(float(footprint.get("width_cells")), 0.72, 1.45)
    except (TypeError, ValueError):
        width = 1
    try:
        height = clamp(float(footprint.get("height_cells")), 0.72, 1.45)
    except (TypeError, ValueError):
        height = 1
    return width, height


def objectives(package: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    data = as_obj(package.get("objectives"))
    core = data.get("core_target")
    if isinstance(core, dict):
        result.append(core)
    result.extend(target for target in as_list(data.get("optional_targets")) if isinstance(target, dict))
    return result


def source_package_matches_runtime(source_package: dict[str, Any], runtime_package: dict[str, Any]) -> bool:
    if source_package.get("package_id") == runtime_package.get("package_id"):
        return True
    return (
        source_package.get("node_id") == runtime_package.get("node_id")
        and source_package.get("schema_version") == runtime_package.get("schema_version")
    )


def matching_decoration_map_policy(
    decoration_policy: dict[str, Any] | None,
    runtime_package: dict[str, Any],
) -> dict[str, Any] | None:
    if not isinstance(decoration_policy, dict):
        return None
    for item in as_list(decoration_policy.get("maps")):
        if not isinstance(item, dict):
            continue
        if source_package_matches_runtime(as_obj(item.get("source_package")), runtime_package):
            return item
    return None


def zone_type_counts(zones: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        zone_type = str(zone.get("zone_type") or "unknown")
        counts[zone_type] = counts.get(zone_type, 0) + 1
    return dict(sorted(counts.items()))


def decoration_policy_summary(
    decoration_policy: dict[str, Any] | None,
    map_policy: dict[str, Any] | None,
    drawn_item_count: int,
) -> dict[str, Any]:
    source_policy = as_obj(decoration_policy.get("source_policy") if decoration_policy else {})
    allowed_zones = as_list(map_policy.get("allowed_decoration_zones") if map_policy else [])
    reserved_zones = as_list(map_policy.get("reserved_zones") if map_policy else [])
    return {
        "decoration_policy_consumed": map_policy is not None,
        "decoration_policy_match_status": "matched" if map_policy is not None else "not_matched",
        "decoration_policy_map_id": map_policy.get("map_id") if map_policy else None,
        "allowed_decoration_zone_count": len(allowed_zones),
        "reserved_zone_count": len(reserved_zones),
        "decoration_policy_drawn_item_count": drawn_item_count,
        "decoration_policy_zone_type_counts": zone_type_counts(allowed_zones),
        "decoration_policy_runtime_fact_source": source_policy.get("runtime_fact_source"),
        "decoration_policy_may_modify_map_runtime_package": source_policy.get("may_modify_map_runtime_package"),
        "decoration_policy_provider_call_count": source_policy.get("provider_call_count"),
    }


def route_point_for_decoration(runtime_package: dict[str, Any], route_index: int, t: float) -> dict[str, float]:
    routes = [route for route in as_list(runtime_package.get("path_routes")) if isinstance(route, dict)]
    if not routes:
        return {"x": 0.0, "y": 0.0}
    return interpolate_route_position(routes[route_index % len(routes)], t)


def render_decoration_policy_layer(
    runtime_package: dict[str, Any],
    map_policy: dict[str, Any] | None,
    projection: dict[str, float],
    *,
    width: int,
    height: int,
    terrain_detail: str,
    fog: str,
    accent: str,
    hazard: str,
    rng: random.Random,
) -> tuple[list[str], int]:
    if map_policy is None:
        return [], 0
    lines = [
        '  <g id="decoration-policy-layer" data-source="map_decoration_zone_policy_review_only">',
    ]
    drawn = 0
    grid = as_obj(runtime_package.get("grid"))
    width_cells = max(1, int(grid.get("width_cells") or 1))
    height_cells = max(1, int(grid.get("height_cells") or 1))
    zones = [zone for zone in as_list(map_policy.get("allowed_decoration_zones")) if isinstance(zone, dict)]
    for zone_index, zone in enumerate(zones):
        zone_type = str(zone.get("zone_type") or "")
        if zone_type == "map_border_decoration":
            points = [
                {"x": 0.35, "y": 0.35},
                {"x": width_cells - 0.65, "y": 0.45},
                {"x": width_cells - 0.55, "y": height_cells - 0.65},
                {"x": 0.45, "y": height_cells - 0.55},
            ]
            for point_index, point in enumerate(points):
                x, y = project_cell(point, projection)
                rx = projection["tile_w"] * (0.10 + 0.025 * ((zone_index + point_index) % 3))
                ry = projection["tile_h"] * (0.10 + 0.018 * ((zone_index + point_index) % 2))
                color = mix_hex(terrain_detail, accent, 0.22)
                lines.append(
                    f'    <ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{color}" opacity="0.28"/>'
                )
                drawn += 1
        elif zone_type == "route_shoulder_decoration":
            for item_index, t in enumerate((0.18, 0.38, 0.62, 0.82)):
                point = route_point_for_decoration(runtime_package, item_index, t)
                x, y = project_cell(point, projection)
                offset_x = projection["tile_w"] * (0.30 if item_index % 2 == 0 else -0.30)
                offset_y = projection["tile_h"] * (0.18 if item_index % 2 == 0 else -0.12)
                radius = max(2.2, projection["tile_w"] * 0.026)
                lines.append(
                    f'    <circle cx="{x + offset_x:.1f}" cy="{y + offset_y:.1f}" r="{radius:.1f}" fill="{mix_hex(terrain_detail, "#000000", 0.18)}" opacity="0.34"/>'
                )
                drawn += 1
        elif zone_type == "empty_cell_decoration":
            for item_index in range(4):
                cell = {
                    "x": 1 + ((zone_index * 3 + item_index * 5) % max(1, width_cells - 2)),
                    "y": 1 + ((zone_index * 5 + item_index * 2) % max(1, height_cells - 2)),
                }
                x, y = project_cell(cell, projection)
                w = projection["tile_w"] * 0.08
                h = projection["tile_h"] * 0.04
                rotate = rng.uniform(-20, 20)
                lines.append(
                    f'    <rect x="{x - w / 2:.1f}" y="{y - h / 2:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{h / 2:.1f}" fill="{mix_hex(terrain_detail, fog, 0.25)}" opacity="0.22" transform="rotate({rotate:.1f} {x:.1f} {y:.1f})"/>'
                )
                drawn += 1
        elif zone_type == "semantic_prop_shoulder":
            for collection_name, id_key in (
                ("resource_nodes", "resource_node_id"),
                ("hazard_zones", "hazard_zone_id"),
                ("defense_anchors", "defense_anchor_id"),
            ):
                for item in as_list(runtime_package.get(collection_name))[:1]:
                    if not isinstance(item, dict):
                        continue
                    position = hazard_midpoint(runtime_package, item) if collection_name == "hazard_zones" else as_obj(item.get("position"))
                    if not position:
                        continue
                    x, y = project_cell(position, projection)
                    size = max(3.0, projection["tile_w"] * 0.04)
                    lines.append(
                        f'    <path d="M {x - size:.1f} {y + size:.1f} L {x:.1f} {y - size:.1f} L {x + size:.1f} {y + size:.1f} Z" fill="{mix_hex(accent, hazard, 0.25)}" opacity="0.28" data-anchor="{svg_escape(item.get(id_key) or collection_name)}"/>'
                    )
                    drawn += 1
        elif zone_type == "atmosphere_overlay":
            lines.append(
                f'    <ellipse cx="{width * 0.18:.1f}" cy="{height * 0.22:.1f}" rx="{width * 0.28:.1f}" ry="{height * 0.10:.1f}" fill="{fog}" opacity="0.07"/>'
            )
            lines.append(
                f'    <ellipse cx="{width * 0.82:.1f}" cy="{height * 0.78:.1f}" rx="{width * 0.26:.1f}" ry="{height * 0.09:.1f}" fill="{hazard}" opacity="0.05"/>'
            )
            drawn += 2
    lines.append("  </g>")
    return lines, drawn


def semantic_points(package: dict[str, Any]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    grid = as_obj(package.get("grid"))
    max_x = max(0, int(grid.get("width_cells") or 1) - 1)
    max_y = max(0, int(grid.get("height_cells") or 1) - 1)
    points.extend(
        [
            {"x": -0.9, "y": -0.9},
            {"x": max_x + 0.9, "y": -0.9},
            {"x": -0.9, "y": max_y + 0.9},
            {"x": max_x + 0.9, "y": max_y + 0.9},
        ]
    )
    for route in as_list(package.get("path_routes")):
        if isinstance(route, dict):
            points.extend(point for point in as_list(route.get("waypoints")) if isinstance(point, dict))
    for slot in as_list(package.get("build_slots")):
        if isinstance(slot, dict) and isinstance(slot.get("position"), dict):
            points.append(slot["position"])
    for target in objectives(package):
        if isinstance(target.get("position"), dict):
            points.append(target["position"])
    for spawn in as_list(package.get("spawn_points")):
        if isinstance(spawn, dict) and isinstance(spawn.get("position"), dict):
            points.append(spawn["position"])
    for resource in as_list(package.get("resource_nodes")):
        if isinstance(resource, dict) and isinstance(resource.get("position"), dict):
            points.append(resource["position"])
    for anchor in as_list(package.get("defense_anchors")):
        if isinstance(anchor, dict) and isinstance(anchor.get("position"), dict):
            points.append(anchor["position"])
    for blocked_area in as_list(package.get("blocked_areas")):
        if isinstance(blocked_area, dict):
            points.extend(
                cell for cell in as_list(blocked_area.get("cells")) if isinstance(cell, dict)
            )
    return points


def raw_project(x: float, y: float, tile_w: float, tile_h: float) -> tuple[float, float]:
    return ((x - y) * (tile_w / 2), (x + y) * (tile_h / 2))


def build_projection(package: dict[str, Any], width: int, height: int) -> dict[str, float]:
    grid = as_obj(package.get("grid"))
    width_cells = max(1, int(grid.get("width_cells") or 16))
    height_cells = max(1, int(grid.get("height_cells") or 9))
    total = width_cells + height_cells
    base_tile_w = clamp(min(((width - 80) * 2) / total, ((height - 110) * 4) / total), 38, 112)
    base_tile_h = base_tile_w * 0.52
    projected = [raw_project(float(p.get("x") or 0), float(p.get("y") or 0), base_tile_w, base_tile_h) for p in semantic_points(package)]
    min_x = min(x for x, _ in projected) - base_tile_w * 0.92
    max_x = max(x for x, _ in projected) + base_tile_w * 0.92
    min_y = min(y for _, y in projected) - base_tile_h * 2.35
    max_y = max(y for _, y in projected) + base_tile_h * 2.35
    scale = clamp(min((width - 96) / max(1, max_x - min_x), (height - 96) / max(1, max_y - min_y)), 0.32, 1.22)
    return {
        "tile_w": base_tile_w * scale,
        "tile_h": base_tile_h * scale,
        "base_tile_w": base_tile_w,
        "base_tile_h": base_tile_h,
        "scale": scale,
        "offset_x": width / 2 - ((min_x + max_x) / 2) * scale,
        "offset_y": height / 2 - ((min_y + max_y) / 2) * scale + 8,
    }


def project_cell(position: dict[str, Any], projection: dict[str, float]) -> tuple[float, float]:
    x = float(position.get("x") or 0)
    y = float(position.get("y") or 0)
    raw_x, raw_y = raw_project(x, y, projection["base_tile_w"], projection["base_tile_h"])
    return (
        projection["offset_x"] + raw_x * projection["scale"],
        projection["offset_y"] + raw_y * projection["scale"],
    )


def smooth_path(points: list[tuple[float, float]]) -> str:
    if not points:
        return ""
    if len(points) < 3:
        return "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in points)
    tokens = [f"M {points[0][0]:.1f} {points[0][1]:.1f}"]
    for index in range(1, len(points) - 1):
        prev_x, prev_y = points[index - 1]
        cur_x, cur_y = points[index]
        next_x, next_y = points[index + 1]
        d1 = math.hypot(cur_x - prev_x, cur_y - prev_y)
        d2 = math.hypot(next_x - cur_x, next_y - cur_y)
        radius = min(48, d1 * 0.32, d2 * 0.32)
        entry_x = cur_x - ((cur_x - prev_x) / max(1, d1)) * radius
        entry_y = cur_y - ((cur_y - prev_y) / max(1, d1)) * radius
        exit_x = cur_x + ((next_x - cur_x) / max(1, d2)) * radius
        exit_y = cur_y + ((next_y - cur_y) / max(1, d2)) * radius
        tokens.append(f"L {entry_x:.1f} {entry_y:.1f}")
        tokens.append(f"Q {cur_x:.1f} {cur_y:.1f} {exit_x:.1f} {exit_y:.1f}")
    last_x, last_y = points[-1]
    tokens.append(f"L {last_x:.1f} {last_y:.1f}")
    return " ".join(tokens)


def route_points(route: dict[str, Any], projection: dict[str, float]) -> list[tuple[float, float]]:
    return [
        project_cell(point, projection)
        for point in as_list(route.get("waypoints"))
        if isinstance(point, dict)
    ]


def route_by_id(package: dict[str, Any], route_id: str) -> dict[str, Any] | None:
    for route in as_list(package.get("path_routes")):
        if isinstance(route, dict) and route.get("route_id") == route_id:
            return route
    return None


def interpolate_route_position(route: dict[str, Any], t: float) -> dict[str, float]:
    waypoints = [point for point in as_list(route.get("waypoints")) if isinstance(point, dict)]
    if not waypoints:
        return {"x": 0.0, "y": 0.0}
    if len(waypoints) == 1:
        return {
            "x": float(waypoints[0].get("x") or 0),
            "y": float(waypoints[0].get("y") or 0),
        }
    segments: list[tuple[dict[str, Any], dict[str, Any], float]] = []
    total = 0.0
    for start, end in zip(waypoints, waypoints[1:]):
        length = math.hypot(
            float(end.get("x") or 0) - float(start.get("x") or 0),
            float(end.get("y") or 0) - float(start.get("y") or 0),
        )
        segments.append((start, end, length))
        total += length
    target = clamp(t, 0, 1) * total
    walked = 0.0
    for start, end, length in segments:
        if walked + length >= target or length <= 0:
            ratio = 0 if length <= 0 else (target - walked) / length
            return {
                "x": float(start.get("x") or 0)
                + (float(end.get("x") or 0) - float(start.get("x") or 0)) * ratio,
                "y": float(start.get("y") or 0)
                + (float(end.get("y") or 0) - float(start.get("y") or 0)) * ratio,
            }
        walked += length
    last = waypoints[-1]
    return {"x": float(last.get("x") or 0), "y": float(last.get("y") or 0)}


def hazard_midpoint(package: dict[str, Any], hazard_zone: dict[str, Any]) -> dict[str, float]:
    route = route_by_id(package, str(hazard_zone.get("anchor_route_id") or ""))
    if route is None:
        return {"x": 0.0, "y": 0.0}
    path_range = as_obj(hazard_zone.get("path_t_range"))
    try:
        start = float(path_range.get("start"))
        end = float(path_range.get("end"))
    except (TypeError, ValueError):
        start, end = 0.45, 0.55
    return interpolate_route_position(route, (start + end) / 2)


def render_svg(
    runtime_package: dict[str, Any],
    style_pack: dict[str, Any],
    render_plan: dict[str, Any],
    decoration_policy: dict[str, Any] | None,
    output_path: Path,
    width: int,
    height: int,
) -> dict[str, Any]:
    projection = build_projection(runtime_package, width, height)
    terrain = palette(style_pack, "terrain_base", "#23302B")
    terrain_detail = palette(style_pack, "terrain_detail", "#4F5A45")
    road_base = palette(style_pack, "road_base", "#766C55")
    road_edge = palette(style_pack, "road_edge", "#B8A56D")
    build_slot = palette(style_pack, "build_slot", "#D7C47A")
    objective = palette(style_pack, "objective", "#FFD26A")
    spawn_color = palette(style_pack, "spawn", "#6650A6")
    resource_color = palette(style_pack, "resource", "#7EC8A5")
    fog = palette(style_pack, "fog", "#87908A")
    accent = palette(style_pack, "accent", "#E5D48A")
    hazard = palette(style_pack, "hazard", "#8C3D4A")
    rng = random.Random(str(runtime_package.get("package_id") or runtime_package.get("node_id") or "map"))
    map_decoration_policy = matching_decoration_map_policy(decoration_policy, runtime_package)

    grid = as_obj(runtime_package.get("grid"))
    corners = [
        project_cell({"x": -0.8, "y": -0.8}, projection),
        project_cell({"x": max(1, int(grid.get("width_cells") or 1)) - 0.2, "y": -0.8}, projection),
        project_cell(
            {
                "x": max(1, int(grid.get("width_cells") or 1)) - 0.2,
                "y": max(1, int(grid.get("height_cells") or 1)) - 0.2,
            },
            projection,
        ),
        project_cell({"x": -0.8, "y": max(1, int(grid.get("height_cells") or 1)) - 0.2}, projection),
    ]
    island = " ".join(f"{x:.1f},{y:.1f}" for x, y in corners)

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "  <defs>",
        f'    <radialGradient id="mapGlow" cx="50%" cy="45%" r="65%"><stop offset="0%" stop-color="{accent}" stop-opacity="0.18"/><stop offset="100%" stop-color="#050807" stop-opacity="0"/></radialGradient>',
        f'    <linearGradient id="terrainWash" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="{terrain_detail}" stop-opacity="0.5"/><stop offset="55%" stop-color="{terrain}" stop-opacity="0.92"/><stop offset="100%" stop-color="{hazard}" stop-opacity="0.24"/></linearGradient>',
        "  </defs>",
        f'  <rect x="0" y="0" width="{width}" height="{height}" fill="{mix_hex(terrain, "#050807", 0.42)}"/>',
        f'  <rect x="0" y="0" width="{width}" height="{height}" fill="url(#mapGlow)"/>',
        '  <g id="non-semantic-terrain-wash">',
    ]
    for index in range(12):
        cx = rng.uniform(-0.05, 1.05) * width
        cy = rng.uniform(-0.04, 1.08) * height
        rx = rng.uniform(90, 220)
        ry = rng.uniform(36, 105)
        color = [terrain_detail, fog, hazard, accent][index % 4]
        opacity = [0.10, 0.08, 0.07, 0.06][index % 4]
        rotate = rng.uniform(-28, 28)
        lines.append(
            f'    <ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{color}" opacity="{opacity:.2f}" transform="rotate({rotate:.1f} {cx:.1f} {cy:.1f})"/>'
        )
    lines.extend(
        [
            "  </g>",
            f'  <polygon id="playable-field" points="{island}" fill="url(#terrainWash)" stroke="{mix_hex(terrain_detail, "#000000", 0.45)}" stroke-width="{max(3, projection["tile_w"] * 0.045):.1f}" opacity="0.88"/>',
        ]
    )
    decoration_lines, decoration_item_count = render_decoration_policy_layer(
        runtime_package,
        map_decoration_policy,
        projection,
        width=width,
        height=height,
        terrain_detail=terrain_detail,
        fog=fog,
        accent=accent,
        hazard=hazard,
        rng=rng,
    )
    lines.extend(decoration_lines)
    lines.append('  <g id="runtime-routes" fill="none" stroke-linecap="round" stroke-linejoin="round">')
    route_count = 0
    for route in as_list(runtime_package.get("path_routes")):
        if not isinstance(route, dict):
            continue
        points = route_points(route, projection)
        if len(points) < 2:
            continue
        route_count += 1
        path = smooth_path(points)
        road_width = max(34, projection["tile_w"] * route_width_cells(render_plan, route))
        shoulder_scale = route_shoulder_scale(render_plan, route)
        lines.append(f'    <path d="{path}" stroke="#070806" stroke-opacity="0.48" stroke-width="{road_width * (1.24 + shoulder_scale * 0.46):.1f}"/>')
        lines.append(f'    <path d="{path}" stroke="{mix_hex(terrain_detail, "#111111", 0.25)}" stroke-opacity="0.58" stroke-width="{road_width * (1.08 + shoulder_scale * 0.36):.1f}"/>')
        lines.append(f'    <path d="{path}" stroke="{road_base}" stroke-opacity="0.86" stroke-width="{road_width:.1f}"/>')
        lines.append(f'    <path d="{path}" stroke="{road_edge}" stroke-opacity="0.58" stroke-width="{road_width * 0.68:.1f}"/>')
        lines.append(f'    <path d="{path}" stroke="{accent}" stroke-opacity="0.18" stroke-width="{max(5, road_width * 0.14):.1f}"/>')
    lines.extend(['  </g>', '  <g id="runtime-build-slot-platforms">'])
    slot_count = 0
    for slot in as_list(runtime_package.get("build_slots")):
        if not isinstance(slot, dict):
            continue
        position = as_obj(slot.get("position"))
        if not position:
            continue
        slot_count += 1
        x, y = project_cell(position, projection)
        footprint_x, footprint_y = slot_footprint(render_plan, slot)
        rx = projection["tile_w"] * 0.46 * footprint_x
        ry = projection["tile_h"] * 0.50 * footprint_y
        lines.append(f'    <ellipse cx="{x:.1f}" cy="{y + projection["tile_h"] * 0.16:.1f}" rx="{rx * 1.08:.1f}" ry="{ry * 0.76:.1f}" fill="#000000" opacity="0.25"/>')
        lines.append(f'    <ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{build_slot}" fill-opacity="0.32" stroke="{build_slot}" stroke-opacity="0.38" stroke-width="{max(1.5, projection["tile_w"] * 0.018):.1f}"/>')
    lines.extend(['  </g>', '  <g id="runtime-v02-strong-semantics">'])
    resource_count = 0
    hazard_count = 0
    defense_anchor_count = 0
    blocked_area_count = 0
    for blocked_area in as_list(runtime_package.get("blocked_areas")):
        if not isinstance(blocked_area, dict):
            continue
        blocked_id = str(blocked_area.get("blocked_area_id") or "")
        if render_plan_operation(render_plan, "blocking_prop", "blocked_area", blocked_id) is None:
            continue
        blocked_area_count += 1
        for cell in as_list(blocked_area.get("cells")):
            if not isinstance(cell, dict):
                continue
            x, y = project_cell(cell, projection)
            half_w = projection["tile_w"] * 0.34
            half_h = projection["tile_h"] * 0.31
            shadow_y = y + projection["tile_h"] * 0.12
            points = (
                f"{x:.1f},{(y - half_h):.1f} "
                f"{(x + half_w):.1f},{y:.1f} "
                f"{x:.1f},{(y + half_h):.1f} "
                f"{(x - half_w):.1f},{y:.1f}"
            )
            lines.append(f'    <ellipse cx="{x:.1f}" cy="{shadow_y:.1f}" rx="{half_w * 0.88:.1f}" ry="{half_h * 0.62:.1f}" fill="#000000" opacity="0.24"/>')
            lines.append(f'    <polygon points="{points}" fill="{mix_hex(terrain_detail, "#10100E", 0.36)}" fill-opacity="0.78" stroke="{mix_hex(road_edge, "#000000", 0.42)}" stroke-width="{max(1.5, projection["tile_w"] * 0.016):.1f}"/>')
    for hazard_zone in as_list(runtime_package.get("hazard_zones")):
        if not isinstance(hazard_zone, dict):
            continue
        hazard_id = str(hazard_zone.get("hazard_zone_id") or "")
        if render_plan_operation(render_plan, "resource_or_hazard", "hazard_zone", hazard_id) is None:
            continue
        hazard_count += 1
        x, y = project_cell(hazard_midpoint(runtime_package, hazard_zone), projection)
        rx = projection["tile_w"] * 0.64
        ry = projection["tile_h"] * 0.42
        lines.append(f'    <ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{hazard}" fill-opacity="0.22" stroke="{hazard}" stroke-opacity="0.52" stroke-width="{max(2, projection["tile_w"] * 0.018):.1f}"/>')
        lines.append(f'    <ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{rx * 0.54:.1f}" ry="{ry * 0.48:.1f}" fill="{mix_hex(hazard, "#050807", 0.22)}" fill-opacity="0.34"/>')
    for resource in as_list(runtime_package.get("resource_nodes")):
        if not isinstance(resource, dict):
            continue
        resource_id = str(resource.get("resource_node_id") or "")
        if render_plan_operation(render_plan, "resource_or_hazard", "resource_node", resource_id) is None:
            continue
        position = as_obj(resource.get("position"))
        if not position:
            continue
        resource_count += 1
        x, y = project_cell(position, projection)
        stem_h = projection["tile_h"] * 0.28
        crystal_w = projection["tile_w"] * 0.18
        crystal_h = projection["tile_h"] * 0.48
        points = (
            f"{x:.1f},{(y - crystal_h):.1f} "
            f"{(x + crystal_w):.1f},{(y - stem_h * 0.2):.1f} "
            f"{x:.1f},{(y + crystal_h * 0.18):.1f} "
            f"{(x - crystal_w):.1f},{(y - stem_h * 0.2):.1f}"
        )
        lines.append(f'    <ellipse cx="{x:.1f}" cy="{y + projection["tile_h"] * 0.16:.1f}" rx="{projection["tile_w"] * 0.30:.1f}" ry="{projection["tile_h"] * 0.20:.1f}" fill="#000000" opacity="0.22"/>')
        lines.append(f'    <polygon points="{points}" fill="{resource_color}" fill-opacity="0.62" stroke="{mix_hex(resource_color, "#FFFFFF", 0.32)}" stroke-opacity="0.74" stroke-width="{max(1.4, projection["tile_w"] * 0.014):.1f}"/>')
        lines.append(f'    <ellipse cx="{x:.1f}" cy="{y - crystal_h * 0.18:.1f}" rx="{projection["tile_w"] * 0.36:.1f}" ry="{projection["tile_h"] * 0.22:.1f}" fill="{resource_color}" opacity="0.13"/>')
    for anchor in as_list(runtime_package.get("defense_anchors")):
        if not isinstance(anchor, dict):
            continue
        anchor_id = str(anchor.get("defense_anchor_id") or "")
        if render_plan_operation(render_plan, "resource_or_hazard", "defense_anchor", anchor_id) is None:
            continue
        position = as_obj(anchor.get("position"))
        if not position:
            continue
        defense_anchor_count += 1
        x, y = project_cell(position, projection)
        try:
            radius_cells = float(anchor.get("influence_radius_cells") or 1)
        except (TypeError, ValueError):
            radius_cells = 1
        lines.append(f'    <ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{projection["tile_w"] * radius_cells * 0.34:.1f}" ry="{projection["tile_h"] * radius_cells * 0.30:.1f}" fill="none" stroke="{accent}" stroke-opacity="0.50" stroke-dasharray="6 6" stroke-width="{max(1.6, projection["tile_w"] * 0.015):.1f}"/>')
        lines.append(f'    <circle cx="{x:.1f}" cy="{y:.1f}" r="{max(3.0, projection["tile_w"] * 0.035):.1f}" fill="{accent}" fill-opacity="0.62"/>')
    lines.extend(['  </g>', '  <g id="runtime-objectives">'])
    objective_count = 0
    for target in objectives(runtime_package):
        position = as_obj(target.get("position"))
        if not position:
            continue
        objective_count += 1
        x, y = project_cell(position, projection)
        core = target == objectives(runtime_package)[0]
        rx = projection["tile_w"] * (0.76 if core else 0.56)
        ry = projection["tile_h"] * (0.58 if core else 0.44)
        lines.append(f'    <ellipse cx="{x:.1f}" cy="{y + projection["tile_h"] * 0.06:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{objective}" fill-opacity="{0.18 if core else 0.12}" stroke="{objective}" stroke-opacity="{0.30 if core else 0.22}" stroke-width="{max(2, projection["tile_w"] * 0.02):.1f}"/>')
        lines.append(f'    <ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{projection["tile_w"] * 0.32:.1f}" ry="{projection["tile_h"] * 0.30:.1f}" fill="{mix_hex(objective, "#202018", 0.48)}" stroke="{objective}" stroke-opacity="0.55" stroke-width="{max(1.5, projection["tile_w"] * 0.018):.1f}"/>')
    lines.extend(['  </g>', '  <g id="runtime-spawns">'])
    spawn_count = 0
    for spawn in as_list(runtime_package.get("spawn_points")):
        if not isinstance(spawn, dict):
            continue
        position = as_obj(spawn.get("position"))
        if not position:
            continue
        spawn_count += 1
        x, y = project_cell(position, projection)
        lines.append(f'    <ellipse cx="{x:.1f}" cy="{y + projection["tile_h"] * 0.04:.1f}" rx="{projection["tile_w"] * 0.34:.1f}" ry="{projection["tile_h"] * 0.25:.1f}" fill="{spawn_color}" fill-opacity="0.30" stroke="{spawn_color}" stroke-opacity="0.55" stroke-width="{max(1.5, projection["tile_w"] * 0.015):.1f}"/>')
        for ring in range(1, 4):
            lines.append(f'    <ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{projection["tile_w"] * (0.22 + ring * 0.09):.1f}" ry="{projection["tile_h"] * (0.16 + ring * 0.06):.1f}" fill="none" stroke="{spawn_color}" stroke-opacity="{0.18 / ring:.3f}" stroke-width="{max(1, projection["tile_w"] * 0.01):.1f}"/>')
    lines.extend(
        [
            "  </g>",
            '  <g id="preview-boundary" fill="none">',
            f'    <rect x="2" y="2" width="{width - 4}" height="{height - 4}" stroke="{accent}" stroke-opacity="0.18" stroke-width="4"/>',
            "  </g>",
            "</svg>",
        ]
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "route_count": route_count,
        "build_slot_count": slot_count,
        "objective_count": objective_count,
        "spawn_point_count": spawn_count,
        "resource_node_count": resource_count,
        "hazard_zone_count": hazard_count,
        "defense_anchor_count": defense_anchor_count,
        "blocked_area_count": blocked_area_count,
        "projection": {
            "type": "pseudo3d_oblique_svg_preview",
            "scale": round(projection["scale"], 4),
            "tile_w": round(projection["tile_w"], 3),
            "tile_h": round(projection["tile_h"], 3),
        },
        "decoration_policy": decoration_policy_summary(
            decoration_policy,
            map_decoration_policy,
            decoration_item_count,
        ),
    }


def validate_inputs(runtime_package: dict[str, Any], style_pack: dict[str, Any], render_plan: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if runtime_package.get("schema_version") not in {
        "map_runtime_package.v0.1",
        "map_runtime_package.v0.2",
    }:
        errors.append("runtime package schema_version must be map_runtime_package.v0.1 or map_runtime_package.v0.2")
    if style_pack.get("schema_version") != "map_style_pack.v0.1":
        errors.append("style pack schema_version must be map_style_pack.v0.1")
    if render_plan.get("schema_version") != "procedural_map_render_plan.v0.1":
        errors.append("render plan schema_version must be procedural_map_render_plan.v0.1")
    if render_plan.get("map_runtime_package_id") != runtime_package.get("package_id"):
        errors.append("render plan map_runtime_package_id does not match runtime package package_id")
    if render_plan.get("style_pack_id") != style_pack.get("style_pack_id"):
        errors.append("render plan style_pack_id does not match style pack style_pack_id")
    if render_plan.get("node_id") != runtime_package.get("node_id"):
        errors.append("render plan node_id does not match runtime package node_id")
    if render_plan.get("node_id") != style_pack.get("node_id"):
        errors.append("render plan node_id does not match style pack node_id")
    if as_obj(render_plan.get("validation_report")).get("runtime_truth_preserved") is not True:
        errors.append("render plan validation_report.runtime_truth_preserved must be true")
    return errors


def validate_optional_decoration_policy(decoration_policy: dict[str, Any] | None) -> list[str]:
    if decoration_policy is None:
        return []
    try:
        validate_decoration_policy(decoration_policy)
    except Exception as exc:  # noqa: BLE001 - render CLI should surface concise input errors.
        return [f"decoration policy validation failed: {exc}"]
    return []


def build_report(
    runtime_path: Path,
    style_path: Path,
    render_plan_path: Path,
    decoration_policy_path: Path | None,
    output_path: Path,
    summary: dict[str, Any],
    width: int,
    height: int,
) -> dict[str, Any]:
    source_refs = {
        "map_runtime_package_path": rel(runtime_path),
        "map_style_pack_path": rel(style_path),
        "procedural_map_render_plan_path": rel(render_plan_path),
    }
    if decoration_policy_path is not None:
        source_refs["map_decoration_zone_policy_path"] = rel(decoration_policy_path)
    return {
        "schema_version": "procedural_map_preview_report.v0.1",
        "report_id": f"{output_path.stem}_report",
        "status": "preview_ready_review_only",
        "preview_svg_path": rel(output_path),
        "preview_svg_sha256": sha256_file(output_path),
        "canvas": {"width": width, "height": height},
        "source_refs": source_refs,
        "render_summary": summary,
        "semantic_source_policy": {
            "routes": "map_runtime_package",
            "build_slots": "map_runtime_package",
            "objectives": "map_runtime_package",
            "spawn_points": "map_runtime_package",
            "resource_nodes": "map_runtime_package",
            "hazard_zones": "map_runtime_package",
            "defense_anchors": "map_runtime_package",
            "blocked_areas": "map_runtime_package",
            "colors": "map_style_pack",
            "road_width_and_slot_footprint": "procedural_map_render_plan",
            "resource_hazard_and_blocking_style": "procedural_map_render_plan",
            "decoration_zones": "map_decoration_zone_policy_review_only",
            "decoration_policy_runtime_fact_source": False,
            "decoration_policy_may_modify_map_runtime_package": False,
        },
        "usage_policy": [
            "review_only",
            "not_player_runtime",
            "not_published_visual_layer",
            "does_not_modify_map_runtime_package",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a review-only SVG preview from a ProceduralMapRenderPlan.")
    parser.add_argument("--runtime-package", default=str(DEFAULT_RUNTIME_PACKAGE))
    parser.add_argument("--style-pack", default=str(DEFAULT_STYLE_PACK))
    parser.add_argument("--render-plan", default=str(DEFAULT_RENDER_PLAN))
    parser.add_argument(
        "--decoration-policy",
        default=str(DEFAULT_DECORATION_POLICY),
        help="Optional MapDecorationZonePolicy v0.1 path. Use 'none' to disable.",
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--report-output", default=str(DEFAULT_REPORT))
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    args = parser.parse_args()

    runtime_path = resolve(args.runtime_package)
    style_path = resolve(args.style_pack)
    render_plan_path = resolve(args.render_plan)
    decoration_policy_path = None if str(args.decoration_policy).strip().lower() in {"", "none", "null"} else resolve(args.decoration_policy)
    output_path = resolve(args.output)
    report_path = resolve(args.report_output)

    try:
        runtime_package = load_json(runtime_path)
        style_pack = load_json(style_path)
        render_plan = load_json(render_plan_path)
        decoration_policy = load_json(decoration_policy_path) if decoration_policy_path is not None else None
    except FileNotFoundError as exc:
        print(f"input file not found: {exc.filename}")
        return 1
    except json.JSONDecodeError as exc:
        print(f"input file is not valid JSON: {exc}")
        return 1

    if not isinstance(runtime_package, dict) or not isinstance(style_pack, dict) or not isinstance(render_plan, dict):
        print("runtime package, style pack, and render plan roots must be objects")
        return 1
    if decoration_policy is not None and not isinstance(decoration_policy, dict):
        print("decoration policy root must be an object")
        return 1

    errors = validate_inputs(runtime_package, style_pack, render_plan)
    errors.extend(validate_optional_decoration_policy(decoration_policy))
    if errors:
        print("INVALID procedural map preview inputs")
        for error in errors:
            print(f"- {error}")
        return 1

    summary = render_svg(runtime_package, style_pack, render_plan, decoration_policy, output_path, args.width, args.height)
    report = build_report(
        runtime_path,
        style_path,
        render_plan_path,
        decoration_policy_path,
        output_path,
        summary,
        args.width,
        args.height,
    )
    write_json(report_path, report)
    print(f"OK: wrote {output_path}")
    print(f"OK: wrote {report_path}")
    print(f"- status: {report['status']}")
    print(f"- routes: {summary['route_count']}, build_slots: {summary['build_slot_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
