"""Deterministic path geometry helpers for MapRuntimePackage review.

This module derives geometry from ``path_routes.waypoints`` only. It does not
read images, previews, SVGs, .env files, or provider output, and it never writes
back to a runtime package.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any


DEFAULT_ROAD_WIDTH_CELLS = 0.85
DEFAULT_SHOULDER_WIDTH_CELLS = 0.25
DEFAULT_SAMPLE_STEP_CELLS = 0.5
NEAR_TURN_RADIUS_CELLS = 1.5
TURN_HINT_MIN_DEGREES = 35.0
EPSILON = 1e-9


Point = tuple[float, float]
Rect = tuple[float, float, float, float]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _point(raw: Any) -> Point:
    if not isinstance(raw, dict):
        return (0.0, 0.0)
    return (float(raw.get("x", 0)), float(raw.get("y", 0)))


def _point_dict(point: Point) -> dict[str, float]:
    x, y = point
    return {"x": round(x, 4), "y": round(y, 4)}


def _cell_key(raw: Any) -> tuple[int, int]:
    x, y = _point(raw)
    return (int(x), int(y))


def _dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _segment_length(a: Point, b: Point) -> float:
    return _dist(a, b)


def _point_segment_distance(point: Point, a: Point, b: Point) -> float:
    ax, ay = a
    bx, by = b
    px, py = point
    dx = bx - ax
    dy = by - ay
    length_sq = dx * dx + dy * dy
    if length_sq <= EPSILON:
        return _dist(point, a)
    t = ((px - ax) * dx + (py - ay) * dy) / length_sq
    t = max(0.0, min(1.0, t))
    projected = (ax + t * dx, ay + t * dy)
    return _dist(point, projected)


def _point_rect_distance(point: Point, rect: Rect) -> float:
    x, y = point
    left, top, right, bottom = rect
    dx = max(left - x, 0.0, x - right)
    dy = max(top - y, 0.0, y - bottom)
    return math.hypot(dx, dy)


def _rect_from_position(position: Any, footprint: Any) -> Rect:
    x, y = _point(position)
    width = 1.0
    height = 1.0
    if isinstance(footprint, dict):
        width = max(1.0, float(footprint.get("width_cells", 1)))
        height = max(1.0, float(footprint.get("height_cells", 1)))
    half_w = width / 2.0
    half_h = height / 2.0
    return (x - half_w, y - half_h, x + half_w, y + half_h)


def _rect_corners(rect: Rect) -> list[Point]:
    left, top, right, bottom = rect
    return [(left, top), (right, top), (right, bottom), (left, bottom)]


def _segment_intersects_rect(a: Point, b: Point, rect: Rect) -> bool:
    left, top, right, bottom = rect
    ax, ay = a
    bx, by = b
    dx = bx - ax
    dy = by - ay
    t0 = 0.0
    t1 = 1.0
    checks = [
        (-dx, ax - left),
        (dx, right - ax),
        (-dy, ay - top),
        (dy, bottom - ay),
    ]
    for p, q in checks:
        if abs(p) <= EPSILON:
            if q < 0:
                return False
            continue
        r = q / p
        if p < 0:
            if r > t1:
                return False
            t0 = max(t0, r)
        else:
            if r < t0:
                return False
            t1 = min(t1, r)
    return True


def _rect_segment_distance(rect: Rect, a: Point, b: Point) -> float:
    if _segment_intersects_rect(a, b, rect):
        return 0.0
    corner_distances = [_point_segment_distance(corner, a, b) for corner in _rect_corners(rect)]
    endpoint_distances = [_point_rect_distance(a, rect), _point_rect_distance(b, rect)]
    return min(corner_distances + endpoint_distances)


def _route_points(route: dict[str, Any]) -> list[Point]:
    return [_point(p) for p in route.get("waypoints", []) if isinstance(p, dict)]


def _segments(points: list[Point]) -> list[tuple[Point, Point]]:
    return [
        (points[index - 1], points[index])
        for index in range(1, len(points))
        if _segment_length(points[index - 1], points[index]) > EPSILON
    ]


def _polyline_length(points: list[Point]) -> float:
    return sum(_segment_length(a, b) for a, b in _segments(points))


def _sample_polyline(points: list[Point], step_cells: float) -> list[dict[str, float]]:
    segments = _segments(points)
    total_length = sum(_segment_length(a, b) for a, b in segments)
    if not segments:
        return []
    step = max(0.05, float(step_cells))
    samples: list[dict[str, float]] = []
    distance_so_far = 0.0
    next_sample = 0.0
    for a, b in segments:
        segment_length = _segment_length(a, b)
        while next_sample <= distance_so_far + segment_length + EPSILON:
            local = 0.0 if segment_length <= EPSILON else (next_sample - distance_so_far) / segment_length
            local = max(0.0, min(1.0, local))
            point = (a[0] + (b[0] - a[0]) * local, a[1] + (b[1] - a[1]) * local)
            samples.append(
                {
                    "x": round(point[0], 4),
                    "y": round(point[1], 4),
                    "distance_cells": round(min(next_sample, total_length), 4),
                    "t": round(0.0 if total_length <= EPSILON else min(next_sample, total_length) / total_length, 4),
                }
            )
            next_sample += step
        distance_so_far += segment_length
    end = points[-1]
    if not samples or _dist((samples[-1]["x"], samples[-1]["y"]), end) > 0.001:
        samples.append(
            {
                "x": round(end[0], 4),
                "y": round(end[1], 4),
                "distance_cells": round(total_length, 4),
                "t": 1.0,
            }
        )
    return samples


def _turn_angle_degrees(prev_point: Point, point: Point, next_point: Point) -> float:
    in_vec = (point[0] - prev_point[0], point[1] - prev_point[1])
    out_vec = (next_point[0] - point[0], next_point[1] - point[1])
    in_len = math.hypot(in_vec[0], in_vec[1])
    out_len = math.hypot(out_vec[0], out_vec[1])
    if in_len <= EPSILON or out_len <= EPSILON:
        return 0.0
    dot = (in_vec[0] * out_vec[0] + in_vec[1] * out_vec[1]) / (in_len * out_len)
    dot = max(-1.0, min(1.0, dot))
    return math.degrees(math.acos(dot))


def _route_turns(points: list[Point], total_length: float) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    distance_so_far = 0.0
    for index in range(1, len(points) - 1):
        distance_so_far += _segment_length(points[index - 1], points[index])
        angle = _turn_angle_degrees(points[index - 1], points[index], points[index + 1])
        if angle < TURN_HINT_MIN_DEGREES:
            continue
        turns.append(
            {
                "waypoint_index": index,
                "position": _point_dict(points[index]),
                "turn_angle_degrees": round(angle, 2),
                "t": round(0.0 if total_length <= EPSILON else distance_so_far / total_length, 4),
                "hint": "near_turn",
            }
        )
    return turns


def _route_envelope(points: list[Point], radius: float) -> dict[str, float]:
    if not points:
        return {"min_x": 0.0, "min_y": 0.0, "max_x": 0.0, "max_y": 0.0}
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return {
        "min_x": round(min(xs) - radius, 4),
        "min_y": round(min(ys) - radius, 4),
        "max_x": round(max(xs) + radius, 4),
        "max_y": round(max(ys) + radius, 4),
    }


def route_distance_to_point(route: dict[str, Any], point: Any) -> float:
    points = _route_points(route)
    segments = _segments(points)
    if not segments:
        return math.inf
    p = _point(point)
    return min(_point_segment_distance(p, a, b) for a, b in segments)


def route_distance_to_rect(route: dict[str, Any], rect: Rect) -> float:
    points = _route_points(route)
    segments = _segments(points)
    if not segments:
        return math.inf
    return min(_rect_segment_distance(rect, a, b) for a, b in segments)


def nearest_route_distance_to_rect(path_routes: list[dict[str, Any]], rect: Rect) -> tuple[str, float]:
    nearest_route_id = ""
    nearest_distance = math.inf
    for route in path_routes:
        if not isinstance(route, dict):
            continue
        distance = route_distance_to_rect(route, rect)
        if distance < nearest_distance:
            nearest_route_id = str(route.get("route_id") or "")
            nearest_distance = distance
    return nearest_route_id, nearest_distance


def derive_path_geometry(
    runtime_package: dict[str, Any],
    *,
    sample_step_cells: float = DEFAULT_SAMPLE_STEP_CELLS,
    road_width_cells: float = DEFAULT_ROAD_WIDTH_CELLS,
    shoulder_width_cells: float = DEFAULT_SHOULDER_WIDTH_CELLS,
) -> dict[str, Any]:
    """Derive review geometry from path_routes.waypoints."""
    road_half_width = float(road_width_cells) / 2.0
    envelope_radius = road_half_width + float(shoulder_width_cells)
    route_geometries: list[dict[str, Any]] = []
    total_length = 0.0
    for route in runtime_package.get("path_routes", []):
        if not isinstance(route, dict):
            continue
        points = _route_points(route)
        length = _polyline_length(points)
        total_length += length
        route_geometries.append(
            {
                "route_id": str(route.get("route_id") or ""),
                "route_length_cells": round(length, 4),
                "sampled_centerline": _sample_polyline(points, sample_step_cells),
                "turns": _route_turns(points, length),
                "road_band_envelope": _route_envelope(points, envelope_radius),
            }
        )
    return {
        "source": "map_runtime_package.path_routes.waypoints",
        "road_width_cells": round(float(road_width_cells), 4),
        "road_half_width_cells": round(road_half_width, 4),
        "shoulder_width_cells": round(float(shoulder_width_cells), 4),
        "sample_step_cells": round(float(sample_step_cells), 4),
        "total_route_length_cells": round(total_length, 4),
        "routes": route_geometries,
    }


def _all_turns(geometry: dict[str, Any]) -> list[tuple[str, Point, float]]:
    turns: list[tuple[str, Point, float]] = []
    for route in geometry.get("routes", []):
        if not isinstance(route, dict):
            continue
        route_id = str(route.get("route_id") or "")
        for turn in route.get("turns", []):
            if not isinstance(turn, dict):
                continue
            turns.append((route_id, _point(turn.get("position")), float(turn.get("turn_angle_degrees", 0.0))))
    return turns


def _slot_distance_record(
    slot: dict[str, Any],
    path_routes: list[dict[str, Any]],
    road_half_width: float,
    turns: list[tuple[str, Point, float]],
) -> dict[str, Any]:
    rect = _rect_from_position(slot.get("position"), slot.get("footprint"))
    nearest_route_id, centerline_distance = nearest_route_distance_to_rect(path_routes, rect)
    road_band_gap = centerline_distance - road_half_width
    center = _point(slot.get("position"))
    near_turns = [
        {
            "route_id": route_id,
            "turn_angle_degrees": round(angle, 2),
            "distance_cells": round(_dist(center, turn_point), 4),
        }
        for route_id, turn_point, angle in turns
        if _dist(center, turn_point) <= NEAR_TURN_RADIUS_CELLS
    ]
    tags = ["near_turn"] if near_turns else []
    if near_turns and road_band_gap >= 0:
        tags.append("good_for_aoe")
    return {
        "slot_id": str(slot.get("slot_id") or ""),
        "nearest_route_id": nearest_route_id,
        "centerline_distance_cells": round(centerline_distance, 4),
        "road_band_gap_cells": round(road_band_gap, 4),
        "near_turns": near_turns,
        "derived_tags": tags,
    }


def _object_distance_to_slot(slot: dict[str, Any], raw: Any) -> float:
    return _point_rect_distance(_point(raw), _rect_from_position(slot.get("position"), slot.get("footprint")))


def _distance_stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "max": None, "average": None}
    return {
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "average": round(sum(values) / len(values), 4),
    }


def review_placement_geometry(
    runtime_package: dict[str, Any],
    *,
    road_width_cells: float = DEFAULT_ROAD_WIDTH_CELLS,
    shoulder_width_cells: float = DEFAULT_SHOULDER_WIDTH_CELLS,
) -> dict[str, Any]:
    """Review build slots and strong semantics against derived path geometry."""
    path_routes = [
        route for route in runtime_package.get("path_routes", []) if isinstance(route, dict)
    ]
    geometry = derive_path_geometry(
        runtime_package,
        road_width_cells=road_width_cells,
        shoulder_width_cells=shoulder_width_cells,
    )
    road_half_width = float(geometry["road_half_width_cells"])
    turns = _all_turns(geometry)
    warnings: list[str] = []
    slot_distances: list[dict[str, Any]] = []
    for index, slot in enumerate(runtime_package.get("build_slots", [])):
        if not isinstance(slot, dict):
            continue
        record = _slot_distance_record(slot, path_routes, road_half_width, turns)
        slot_distances.append(record)
        if record["road_band_gap_cells"] < -0.001:
            warnings.append(
                f"build_slots[{index}] {record['slot_id']} footprint overlaps derived road band by "
                f"{abs(float(record['road_band_gap_cells'])):.4f} cells"
            )
    objectives = runtime_package.get("objectives") if isinstance(runtime_package.get("objectives"), dict) else {}
    protected_points: list[tuple[str, Any]] = []
    core = objectives.get("core_target") if isinstance(objectives, dict) else None
    if isinstance(core, dict):
        protected_points.append(("objectives.core_target", core.get("position")))
    for index, target in enumerate(objectives.get("optional_targets", []) if isinstance(objectives, dict) else []):
        if isinstance(target, dict):
            protected_points.append((f"objectives.optional_targets[{index}]", target.get("position")))
    for index, spawn in enumerate(runtime_package.get("spawn_points", [])):
        if isinstance(spawn, dict):
            protected_points.append((f"spawn_points[{index}]", spawn.get("position")))
    for slot_index, slot in enumerate(runtime_package.get("build_slots", [])):
        if not isinstance(slot, dict):
            continue
        for label, point in protected_points:
            if _object_distance_to_slot(slot, point) < 0.001:
                warnings.append(f"build_slots[{slot_index}] overlaps {label}")

    blocked_cells: set[tuple[int, int]] = set()
    for area_index, area in enumerate(runtime_package.get("blocked_areas", [])):
        if not isinstance(area, dict):
            continue
        for cell_index, cell in enumerate(area.get("cells", [])):
            if not isinstance(cell, dict):
                continue
            blocked_cells.add(_cell_key(cell))
            nearest_route_distance = min(
                (route_distance_to_point(route, cell) for route in path_routes),
                default=math.inf,
            )
            if nearest_route_distance - road_half_width < -0.001:
                warnings.append(f"blocked_areas[{area_index}].cells[{cell_index}] overlaps derived road band")
    for slot_index, slot in enumerate(runtime_package.get("build_slots", [])):
        if not isinstance(slot, dict):
            continue
        if _cell_key(slot.get("position")) in blocked_cells:
            warnings.append(f"build_slots[{slot_index}] overlaps blocked_areas")

    resource_cells: set[tuple[int, int]] = set()
    for resource_index, resource in enumerate(runtime_package.get("resource_nodes", [])):
        if not isinstance(resource, dict):
            continue
        resource_cells.add(_cell_key(resource.get("position")))
        nearest_route_distance = min(
            (route_distance_to_point(route, resource.get("position")) for route in path_routes),
            default=math.inf,
        )
        if resource.get("blocking") is True and nearest_route_distance - road_half_width < -0.001:
            warnings.append(f"resource_nodes[{resource_index}] blocking resource overlaps derived road band")
    for slot_index, slot in enumerate(runtime_package.get("build_slots", [])):
        if not isinstance(slot, dict):
            continue
        if _cell_key(slot.get("position")) in resource_cells:
            warnings.append(f"build_slots[{slot_index}] overlaps resource_nodes")

    near_turn_slots = [
        {
            "slot_id": record["slot_id"],
            "nearest_route_id": record["nearest_route_id"],
            "derived_tags": record["derived_tags"],
            "near_turns": record["near_turns"],
        }
        for record in slot_distances
        if record["near_turns"]
    ]
    gaps = [float(record["road_band_gap_cells"]) for record in slot_distances]
    return {
        "geometry": geometry,
        "slot_distances": slot_distances,
        "slot_distance_stats": {
            "road_band_gap_cells": _distance_stats(gaps),
        },
        "near_turn_slots": near_turn_slots,
        "warnings": list(dict.fromkeys(warnings)),
    }


def placement_warning_messages(runtime_package: dict[str, Any]) -> list[str]:
    return [str(warning) for warning in review_placement_geometry(runtime_package).get("warnings", [])]


def build_map_summary(
    runtime_package: dict[str, Any],
    *,
    map_runtime_package_path: str,
) -> dict[str, Any]:
    review = review_placement_geometry(runtime_package)
    geometry = review["geometry"]
    route_summaries: list[dict[str, Any]] = []
    for route in geometry.get("routes", []):
        if not isinstance(route, dict):
            continue
        route_summaries.append(
            {
                "route_id": route.get("route_id"),
                "route_length_cells": route.get("route_length_cells"),
                "sampled_centerline": route.get("sampled_centerline", []),
                "sampled_point_count": len(route.get("sampled_centerline", [])),
                "turns": route.get("turns", []),
                "turn_count": len(route.get("turns", [])),
                "road_band_envelope": route.get("road_band_envelope", {}),
            }
        )
    return {
        "map_runtime_package_path": map_runtime_package_path,
        "schema_version": runtime_package.get("schema_version"),
        "package_id": runtime_package.get("package_id"),
        "node_id": runtime_package.get("node_id"),
        "route_count": len(route_summaries),
        "build_slot_count": len(runtime_package.get("build_slots", [])),
        "total_route_length_cells": geometry.get("total_route_length_cells"),
        "route_summaries": route_summaries,
        "slot_distances": review.get("slot_distances", []),
        "slot_distance_stats": review.get("slot_distance_stats", {}),
        "near_turn_slots": review.get("near_turn_slots", []),
        "warnings": review.get("warnings", []),
        "warning_count": len(review.get("warnings", [])),
    }


def build_geometry_report(
    runtime_packages: list[tuple[str, dict[str, Any]]],
    *,
    report_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    map_summaries = [
        build_map_summary(package, map_runtime_package_path=path)
        for path, package in runtime_packages
    ]
    warning_count = sum(int(summary.get("warning_count", 0)) for summary in map_summaries)
    total_route_length = sum(
        float(summary.get("total_route_length_cells", 0.0))
        for summary in map_summaries
    )
    route_count = sum(int(summary.get("route_count", 0)) for summary in map_summaries)
    build_slot_count = sum(int(summary.get("build_slot_count", 0)) for summary in map_summaries)
    return {
        "schema_version": "map_path_geometry_report.v0.1",
        "report_id": report_id or "map_path_geometry_report_v0_1",
        "created_at": created_at or now_iso(),
        "status": "warning" if warning_count else "passed",
        "source_policy": {
            "geometry_source": "MapRuntimePackage.path_routes.waypoints",
            "no_image_or_preview_reverse_inference": True,
            "does_not_modify_runtime_package": True,
        },
        "summary": {
            "map_count": len(map_summaries),
            "route_count": route_count,
            "build_slot_count": build_slot_count,
            "total_route_length_cells": round(total_route_length, 4),
            "warning_count": warning_count,
        },
        "maps": map_summaries,
        "usage_policy": [
            "review_only",
            "not_player_runtime",
            "not_map_runtime_fact_source",
            "does_not_modify_map_runtime_package",
        ],
    }


def validate_geometry_report(
    report: dict[str, Any],
    schema: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    if schema:
        try:
            import jsonschema  # type: ignore
        except Exception:
            jsonschema = None  # type: ignore
        if jsonschema is not None:
            validator_cls = getattr(jsonschema, "Draft202012Validator", None)
            if validator_cls is None:
                validator_cls = getattr(jsonschema, "Draft7Validator", None)
            if validator_cls is not None:
                validator = validator_cls(schema)
                errors.extend(
                    f"schema: {'.'.join(map(str, e.path)) or '<root>'}: {e.message}"
                    for e in sorted(validator.iter_errors(report), key=str)
                )
    if report.get("schema_version") != "map_path_geometry_report.v0.1":
        errors.append("schema_version must be 'map_path_geometry_report.v0.1'")
    source_policy = report.get("source_policy") if isinstance(report.get("source_policy"), dict) else {}
    if source_policy.get("geometry_source") != "MapRuntimePackage.path_routes.waypoints":
        errors.append("source_policy.geometry_source must be MapRuntimePackage.path_routes.waypoints")
    if source_policy.get("no_image_or_preview_reverse_inference") is not True:
        errors.append("source_policy.no_image_or_preview_reverse_inference must be true")
    if source_policy.get("does_not_modify_runtime_package") is not True:
        errors.append("source_policy.does_not_modify_runtime_package must be true")
    maps = report.get("maps")
    if not isinstance(maps, list) or not maps:
        errors.append("maps must be a non-empty array")
        maps = []
    warning_count = 0
    route_count = 0
    build_slot_count = 0
    total_route_length = 0.0
    for index, item in enumerate(maps):
        if not isinstance(item, dict):
            errors.append(f"maps[{index}] must be an object")
            continue
        warnings = item.get("warnings", [])
        if not isinstance(warnings, list):
            errors.append(f"maps[{index}].warnings must be an array")
            warnings = []
        warning_count += len(warnings)
        route_count += int(item.get("route_count", 0))
        build_slot_count += int(item.get("build_slot_count", 0))
        total_route_length += float(item.get("total_route_length_cells", 0.0))
        for route_index, route in enumerate(item.get("route_summaries", [])):
            if not isinstance(route, dict):
                errors.append(f"maps[{index}].route_summaries[{route_index}] must be an object")
                continue
            samples = route.get("sampled_centerline", [])
            if not isinstance(samples, list) or not samples:
                errors.append(f"maps[{index}].route_summaries[{route_index}].sampled_centerline must be non-empty")
            if route.get("sampled_point_count") != len(samples):
                errors.append(f"maps[{index}].route_summaries[{route_index}].sampled_point_count mismatch")
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    if summary.get("map_count") != len(maps):
        errors.append("summary.map_count mismatch")
    if summary.get("route_count") != route_count:
        errors.append("summary.route_count mismatch")
    if summary.get("build_slot_count") != build_slot_count:
        errors.append("summary.build_slot_count mismatch")
    if summary.get("warning_count") != warning_count:
        errors.append("summary.warning_count mismatch")
    if round(float(summary.get("total_route_length_cells", 0.0)), 4) != round(total_route_length, 4):
        errors.append("summary.total_route_length_cells mismatch")
    expected_status = "warning" if warning_count else "passed"
    if report.get("status") != expected_status:
        errors.append(f"status must be {expected_status!r} for current warning count")
    usage_policy = report.get("usage_policy")
    if not isinstance(usage_policy, list) or "not_map_runtime_fact_source" not in usage_policy:
        errors.append("usage_policy must include not_map_runtime_fact_source")
    return list(dict.fromkeys(errors))
