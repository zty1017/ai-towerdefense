#!/usr/bin/env python3
"""Build review-only geometry evidence for MapRuntimePackage v0.2 semantics."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import map_path_geometry as mpg  # noqa: E402
import map_runtime_package_v02 as mrp_v02  # noqa: E402


DEFAULT_SCHEMA = ROOT / "shared/schemas/map_runtime_v02_semantic_geometry_report.v0.1.schema.json"
DEFAULT_RUNTIME_V02_SCHEMA = ROOT / "shared/schemas/map_runtime_package.v0.2.schema.json"
DEFAULT_OUTPUT = ROOT / "examples/review_packs/map_runtime_v02_semantic_geometry_report.v0.1.json"
DEFAULT_PACKAGE_GLOB = "examples/map_runtime_packages_v02/*.json"
ANCHOR_DISTANCE_WARNING_CELLS = 3.25
EPSILON = 1e-9


Point = tuple[float, float]
Cell = tuple[int, int]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    path.write_text(payload + "\n", encoding="utf-8")


def resolve(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else ROOT / candidate


def rel(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def load_schema(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    loaded = load_json(path)
    return loaded if isinstance(loaded, dict) else None


def default_package_paths() -> list[Path]:
    return sorted(ROOT.glob(DEFAULT_PACKAGE_GLOB))


def as_point(raw: Any) -> Point:
    if not isinstance(raw, dict):
        return (0.0, 0.0)
    return (float(raw.get("x", 0)), float(raw.get("y", 0)))


def point_dict(point: Point) -> dict[str, float]:
    return {"x": round(point[0], 4), "y": round(point[1], 4)}


def cell_key(raw: Any) -> Cell:
    x, y = as_point(raw)
    return (int(x), int(y))


def in_grid(cell: Cell, grid: dict[str, Any]) -> bool:
    width = int(grid.get("width_cells", 0))
    height = int(grid.get("height_cells", 0))
    return 0 <= cell[0] < width and 0 <= cell[1] < height


def footprint_cells(position: Any, footprint: Any) -> set[Cell]:
    x, y = cell_key(position)
    width = 1
    height = 1
    if isinstance(footprint, dict):
        width = max(1, int(footprint.get("width_cells", 1)))
        height = max(1, int(footprint.get("height_cells", 1)))
    return {(x + dx, y + dy) for dx in range(width) for dy in range(height)}


def point_distance(a: Any, b: Any) -> float:
    ax, ay = as_point(a)
    bx, by = as_point(b)
    return math.hypot(ax - bx, ay - by)


def add_finding(
    findings: list[dict[str, str]],
    *,
    severity: str,
    check_id: str,
    object_ref: str,
    message: str,
) -> None:
    findings.append(
        {
            "severity": severity,
            "check_id": check_id,
            "object_ref": object_ref,
            "message": message,
        }
    )


def objective_cells(package: dict[str, Any]) -> set[Cell]:
    cells: set[Cell] = set()
    objectives = package.get("objectives") if isinstance(package.get("objectives"), dict) else {}
    core = objectives.get("core_target")
    if isinstance(core, dict):
        cells.add(cell_key(core.get("position")))
    for target in objectives.get("optional_targets", []) if isinstance(objectives, dict) else []:
        if isinstance(target, dict):
            cells.add(cell_key(target.get("position")))
    return cells


def spawn_cells(package: dict[str, Any]) -> set[Cell]:
    cells: set[Cell] = set()
    for spawn in package.get("spawn_points", []):
        if isinstance(spawn, dict):
            cells.add(cell_key(spawn.get("position")))
    return cells


def build_slot_cells(package: dict[str, Any]) -> set[Cell]:
    cells: set[Cell] = set()
    for slot in package.get("build_slots", []):
        if isinstance(slot, dict):
            cells.update(footprint_cells(slot.get("position"), slot.get("footprint")))
    return cells


def blocked_cells(package: dict[str, Any]) -> set[Cell]:
    cells: set[Cell] = set()
    for area in package.get("blocked_areas", []):
        if not isinstance(area, dict):
            continue
        for cell in area.get("cells", []):
            if isinstance(cell, dict):
                cells.add(cell_key(cell))
    return cells


def route_by_id(package: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(route.get("route_id")): route
        for route in package.get("path_routes", [])
        if isinstance(route, dict) and route.get("route_id")
    }


def nearest_route_to_point(path_routes: list[dict[str, Any]], position: Any) -> tuple[str, float]:
    nearest_route_id = ""
    nearest_distance = math.inf
    for route in path_routes:
        distance = mpg.route_distance_to_point(route, position)
        if distance < nearest_distance:
            nearest_route_id = str(route.get("route_id") or "")
            nearest_distance = distance
    return nearest_route_id, nearest_distance


def review_resources(
    package: dict[str, Any],
    *,
    findings: list[dict[str, str]],
    grid: dict[str, Any],
    path_routes: list[dict[str, Any]],
    blocked: set[Cell],
    build_slots: set[Cell],
    objectives: set[Cell],
    spawns: set[Cell],
) -> list[dict[str, Any]]:
    reviews: list[dict[str, Any]] = []
    road_half_width = mpg.DEFAULT_ROAD_WIDTH_CELLS / 2.0
    for index, resource in enumerate(package.get("resource_nodes", [])):
        if not isinstance(resource, dict):
            continue
        finding_start = len(findings)
        object_ref = f"resource_nodes[{index}]"
        resource_id = str(resource.get("resource_node_id") or "")
        cells = footprint_cells(resource.get("position"), resource.get("footprint"))
        nearest_route_id, centerline_distance, road_gap = mpg.nearest_road_band_gap(
            path_routes,
            resource.get("position"),
            resource.get("footprint"),
        )
        conflicts: list[str] = []
        if any(not in_grid(cell, grid) for cell in cells):
            conflicts.append("out_of_grid")
            add_finding(
                findings,
                severity="error",
                check_id="resource_footprint_in_grid",
                object_ref=object_ref,
                message=f"{resource_id} footprint has cells outside grid",
            )
        for label, other_cells in (
            ("build_slot", build_slots),
            ("objective", objectives),
            ("spawn", spawns),
            ("blocked_area", blocked),
        ):
            if cells & other_cells:
                conflicts.append(label)
                add_finding(
                    findings,
                    severity="error",
                    check_id=f"resource_no_{label}_overlap",
                    object_ref=object_ref,
                    message=f"{resource_id} overlaps {label} cells",
                )
        if road_gap < -EPSILON:
            conflicts.append("derived_road_band")
            severity = "error" if resource.get("blocking") is True else "warning"
            add_finding(
                findings,
                severity=severity,
                check_id="resource_road_band_clearance",
                object_ref=object_ref,
                message=(
                    f"{resource_id} footprint overlaps derived road band by "
                    f"{abs(road_gap):.4f} cells"
                ),
            )
        interactable = resource.get("interactable") is True
        interactable_area_status = "available"
        if not interactable:
            interactable_area_status = "not_interactable"
        elif conflicts and any(item != "derived_road_band" for item in conflicts):
            interactable_area_status = "blocked"
        object_findings = findings[finding_start:]
        status = "error" if any(f["severity"] == "error" for f in object_findings) else (
            "warning" if object_findings else "passed"
        )
        reviews.append(
            {
                "resource_node_id": resource_id,
                "status": status,
                "position": point_dict(as_point(resource.get("position"))),
                "nearest_route_id": nearest_route_id,
                "centerline_distance_cells": round(centerline_distance, 4),
                "road_band_gap_cells": round(centerline_distance - road_half_width, 4)
                if math.isfinite(centerline_distance)
                else 9999.0,
                "interactable_area_status": interactable_area_status,
                "conflicts": sorted(set(conflicts)),
            }
        )
    return reviews


def review_hazards(
    package: dict[str, Any],
    *,
    findings: list[dict[str, str]],
    routes: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    reviews: list[dict[str, Any]] = []
    for index, hazard in enumerate(package.get("hazard_zones", [])):
        if not isinstance(hazard, dict):
            continue
        finding_start = len(findings)
        object_ref = f"hazard_zones[{index}]"
        hazard_id = str(hazard.get("hazard_zone_id") or "")
        route_id = str(hazard.get("anchor_route_id") or "")
        span = hazard.get("path_t_range") if isinstance(hazard.get("path_t_range"), dict) else {}
        start = float(span.get("start", 0.0))
        end = float(span.get("end", 0.0))
        route_binding_status = "bound"
        if route_id not in routes:
            route_binding_status = "missing_route"
            add_finding(
                findings,
                severity="error",
                check_id="hazard_anchor_route_exists",
                object_ref=object_ref,
                message=f"{hazard_id} references missing route {route_id!r}",
            )
        elif not (0 <= start < end <= 1):
            route_binding_status = "invalid_range"
            add_finding(
                findings,
                severity="error",
                check_id="hazard_path_t_range_valid",
                object_ref=object_ref,
                message=f"{hazard_id} path_t_range must satisfy 0 <= start < end <= 1",
            )
        object_findings = findings[finding_start:]
        status = "error" if any(f["severity"] == "error" for f in object_findings) else (
            "warning" if object_findings else "passed"
        )
        reviews.append(
            {
                "hazard_zone_id": hazard_id,
                "status": status,
                "anchor_route_id": route_id,
                "path_t_range": {"start": round(start, 4), "end": round(end, 4)},
                "affected_area": str(hazard.get("affected_area") or ""),
                "route_binding_status": route_binding_status,
            }
        )
    return reviews


def review_defense_anchors(
    package: dict[str, Any],
    *,
    findings: list[dict[str, str]],
    grid: dict[str, Any],
    path_routes: list[dict[str, Any]],
    routes: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    reviews: list[dict[str, Any]] = []
    for index, anchor in enumerate(package.get("defense_anchors", [])):
        if not isinstance(anchor, dict):
            continue
        finding_start = len(findings)
        object_ref = f"defense_anchors[{index}]"
        anchor_id = str(anchor.get("defense_anchor_id") or "")
        position = anchor.get("position")
        related = [
            str(route_id)
            for route_id in anchor.get("related_route_ids", [])
            if isinstance(route_id, str) and route_id
        ]
        nearest_route_id, nearest_distance = nearest_route_to_point(path_routes, position)
        related_distances = [
            mpg.route_distance_to_point(routes[route_id], position)
            for route_id in related
            if route_id in routes
        ]
        nearest_related = min(related_distances, default=math.inf)
        route_binding_status = "bound"
        if any(route_id not in routes for route_id in related) or not related:
            route_binding_status = "missing_route"
            add_finding(
                findings,
                severity="error",
                check_id="defense_anchor_related_routes_exist",
                object_ref=object_ref,
                message=f"{anchor_id} has missing or empty related_route_ids",
            )
        if not in_grid(cell_key(position), grid):
            add_finding(
                findings,
                severity="error",
                check_id="defense_anchor_in_grid",
                object_ref=object_ref,
                message=f"{anchor_id} position is outside grid",
            )
        if math.isfinite(nearest_related) and nearest_related > ANCHOR_DISTANCE_WARNING_CELLS:
            route_binding_status = "too_far_from_related_route"
            add_finding(
                findings,
                severity="warning",
                check_id="defense_anchor_near_related_route",
                object_ref=object_ref,
                message=(
                    f"{anchor_id} is {nearest_related:.4f} cells from its nearest related route"
                ),
            )
        object_findings = findings[finding_start:]
        status = "error" if any(f["severity"] == "error" for f in object_findings) else (
            "warning" if object_findings else "passed"
        )
        reviews.append(
            {
                "defense_anchor_id": anchor_id,
                "status": status,
                "position": point_dict(as_point(position)),
                "related_route_ids": related,
                "nearest_route_id": nearest_route_id,
                "nearest_related_route_distance_cells": round(nearest_related, 4)
                if math.isfinite(nearest_related)
                else 9999.0,
                "route_binding_status": route_binding_status,
            }
        )
    return reviews


def review_blocked_areas(
    package: dict[str, Any],
    *,
    findings: list[dict[str, str]],
    grid: dict[str, Any],
    path_routes: list[dict[str, Any]],
    build_slots: set[Cell],
    objectives: set[Cell],
    spawns: set[Cell],
    resources: set[Cell],
) -> list[dict[str, Any]]:
    reviews: list[dict[str, Any]] = []
    road_half_width = mpg.DEFAULT_ROAD_WIDTH_CELLS / 2.0
    for area_index, area in enumerate(package.get("blocked_areas", [])):
        if not isinstance(area, dict):
            continue
        finding_start = len(findings)
        object_ref = f"blocked_areas[{area_index}]"
        area_id = str(area.get("blocked_area_id") or "")
        conflicts: list[str] = []
        raw_cells = [cell for cell in area.get("cells", []) if isinstance(cell, dict)]
        for cell_index, raw_cell in enumerate(raw_cells):
            cell = cell_key(raw_cell)
            cell_ref = f"{object_ref}.cells[{cell_index}]"
            if not in_grid(cell, grid):
                conflicts.append("out_of_grid")
                add_finding(
                    findings,
                    severity="error",
                    check_id="blocked_area_cell_in_grid",
                    object_ref=cell_ref,
                    message=f"{area_id} has a blocked cell outside grid",
                )
            for label, other_cells in (
                ("build_slot", build_slots),
                ("objective", objectives),
                ("spawn", spawns),
                ("resource", resources),
            ):
                if cell in other_cells:
                    conflicts.append(label)
                    add_finding(
                        findings,
                        severity="error",
                        check_id=f"blocked_area_no_{label}_overlap",
                        object_ref=cell_ref,
                        message=f"{area_id} overlaps {label} cells",
                    )
            nearest_distance = min(
                (mpg.route_distance_to_point(route, raw_cell) for route in path_routes),
                default=math.inf,
            )
            if nearest_distance - road_half_width < -EPSILON:
                conflicts.append("derived_road_band")
                add_finding(
                    findings,
                    severity="error",
                    check_id="blocked_area_no_road_band_overlap",
                    object_ref=cell_ref,
                    message=f"{area_id} overlaps derived road band",
                )
        object_findings = findings[finding_start:]
        status = "error" if any(f["severity"] == "error" for f in object_findings) else (
            "warning" if object_findings else "passed"
        )
        reviews.append(
            {
                "blocked_area_id": area_id,
                "status": status,
                "cell_count": len(raw_cells),
                "conflicts": sorted(set(conflicts)),
            }
        )
    return reviews


def review_map(package: dict[str, Any], *, package_path: str) -> dict[str, Any]:
    grid = package.get("grid") if isinstance(package.get("grid"), dict) else {}
    path_routes = [
        route for route in package.get("path_routes", []) if isinstance(route, dict)
    ]
    routes = route_by_id(package)
    findings: list[dict[str, str]] = []
    build_cells = build_slot_cells(package)
    objective_cell_set = objective_cells(package)
    spawn_cell_set = spawn_cells(package)
    blocked_cell_set = blocked_cells(package)
    resource_cell_set = set()
    for resource in package.get("resource_nodes", []):
        if isinstance(resource, dict):
            resource_cell_set.update(footprint_cells(resource.get("position"), resource.get("footprint")))

    resource_reviews = review_resources(
        package,
        findings=findings,
        grid=grid,
        path_routes=path_routes,
        blocked=blocked_cell_set,
        build_slots=build_cells,
        objectives=objective_cell_set,
        spawns=spawn_cell_set,
    )
    hazard_reviews = review_hazards(package, findings=findings, routes=routes)
    defense_anchor_reviews = review_defense_anchors(
        package,
        findings=findings,
        grid=grid,
        path_routes=path_routes,
        routes=routes,
    )
    blocked_area_reviews = review_blocked_areas(
        package,
        findings=findings,
        grid=grid,
        path_routes=path_routes,
        build_slots=build_cells,
        objectives=objective_cell_set,
        spawns=spawn_cell_set,
        resources=resource_cell_set,
    )

    severities = Counter(finding["severity"] for finding in findings)
    status = "passed"
    if severities.get("error", 0):
        status = "blocked"
    elif severities.get("warning", 0):
        status = "passed_with_warnings"
    return {
        "map_runtime_package_path": package_path,
        "schema_version": str(package.get("schema_version") or ""),
        "package_id": str(package.get("package_id") or ""),
        "node_id": str(package.get("node_id") or ""),
        "status": status,
        "grid": grid,
        "counts": {
            "resource_node_count": len(resource_reviews),
            "hazard_zone_count": len(hazard_reviews),
            "defense_anchor_count": len(defense_anchor_reviews),
            "blocked_area_count": len(blocked_area_reviews),
        },
        "resource_nodes": resource_reviews,
        "hazard_zones": hazard_reviews,
        "defense_anchors": defense_anchor_reviews,
        "blocked_areas": blocked_area_reviews,
        "findings": findings,
        "error_count": severities.get("error", 0),
        "warning_count": severities.get("warning", 0),
    }


def build_report(
    runtime_packages: list[tuple[str, dict[str, Any]]],
    *,
    report_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    maps = [review_map(package, package_path=path) for path, package in runtime_packages]
    status_counts = Counter(str(item.get("status")) for item in maps)
    error_count = sum(int(item.get("error_count", 0)) for item in maps)
    warning_count = sum(int(item.get("warning_count", 0)) for item in maps)
    status = "passed"
    if error_count:
        status = "blocked"
    elif warning_count:
        status = "passed_with_warnings"
    return {
        "schema_version": "map_runtime_v02_semantic_geometry_report.v0.1",
        "report_id": report_id or "map_runtime_v02_semantic_geometry_report_v0_1",
        "created_at": created_at or now_iso(),
        "status": status,
        "source_policy": {
            "runtime_package_schema_version": "map_runtime_package.v0.2",
            "semantic_source": "MapRuntimePackage.v0.2.resource_nodes/hazard_zones/defense_anchors/blocked_areas",
            "geometry_source": "MapRuntimePackage.path_routes.waypoints",
            "no_image_or_preview_reverse_inference": True,
            "does_not_modify_runtime_package": True,
            "does_not_read_env": True,
            "does_not_call_provider": True,
        },
        "runtime_effect": False,
        "provider_call_count": 0,
        "default_runtime_mutation": False,
        "summary": {
            "map_count": len(maps),
            "resource_node_count": sum(len(item.get("resource_nodes", [])) for item in maps),
            "hazard_zone_count": sum(len(item.get("hazard_zones", [])) for item in maps),
            "defense_anchor_count": sum(len(item.get("defense_anchors", [])) for item in maps),
            "blocked_area_count": sum(len(item.get("blocked_areas", [])) for item in maps),
            "error_count": error_count,
            "warning_count": warning_count,
            "status_counts": dict(sorted(status_counts.items())),
        },
        "maps": maps,
        "usage_policy": [
            "review_only",
            "not_player_runtime",
            "not_map_runtime_fact_source",
            "does_not_modify_map_runtime_package",
            "no_image_or_preview_reverse_inference",
        ],
    }


def validate_report(report: dict[str, Any], schema: dict[str, Any] | None = None) -> list[str]:
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
    if report.get("schema_version") != "map_runtime_v02_semantic_geometry_report.v0.1":
        errors.append("schema_version must be 'map_runtime_v02_semantic_geometry_report.v0.1'")
    source_policy = report.get("source_policy") if isinstance(report.get("source_policy"), dict) else {}
    if source_policy.get("runtime_package_schema_version") != "map_runtime_package.v0.2":
        errors.append("source_policy.runtime_package_schema_version must be map_runtime_package.v0.2")
    if source_policy.get("semantic_source") != "MapRuntimePackage.v0.2.resource_nodes/hazard_zones/defense_anchors/blocked_areas":
        errors.append("source_policy.semantic_source must identify MapRuntimePackage.v0.2 strong semantic fields")
    if source_policy.get("geometry_source") != "MapRuntimePackage.path_routes.waypoints":
        errors.append("source_policy.geometry_source must be MapRuntimePackage.path_routes.waypoints")
    if source_policy.get("no_image_or_preview_reverse_inference") is not True:
        errors.append("source_policy.no_image_or_preview_reverse_inference must be true")
    if source_policy.get("does_not_modify_runtime_package") is not True:
        errors.append("source_policy.does_not_modify_runtime_package must be true")
    if source_policy.get("does_not_read_env") is not True:
        errors.append("source_policy.does_not_read_env must be true")
    if source_policy.get("does_not_call_provider") is not True:
        errors.append("source_policy.does_not_call_provider must be true")
    if report.get("runtime_effect") is not False:
        errors.append("runtime_effect must be false")
    if report.get("provider_call_count") != 0:
        errors.append("provider_call_count must be 0")
    if report.get("default_runtime_mutation") is not False:
        errors.append("default_runtime_mutation must be false")
    maps = report.get("maps")
    if not isinstance(maps, list) or not maps:
        errors.append("maps must be a non-empty array")
        maps = []
    status_counts = Counter()
    error_count = 0
    warning_count = 0
    resource_count = 0
    hazard_count = 0
    anchor_count = 0
    blocked_count = 0
    for index, item in enumerate(maps):
        if not isinstance(item, dict):
            errors.append(f"maps[{index}] must be an object")
            continue
        status = item.get("status")
        status_counts[str(status)] += 1
        findings = item.get("findings", [])
        if not isinstance(findings, list):
            errors.append(f"maps[{index}].findings must be an array")
            findings = []
        item_errors = sum(1 for finding in findings if isinstance(finding, dict) and finding.get("severity") == "error")
        item_warnings = sum(1 for finding in findings if isinstance(finding, dict) and finding.get("severity") == "warning")
        if item.get("error_count") != item_errors:
            errors.append(f"maps[{index}].error_count does not match findings")
        if item.get("warning_count") != item_warnings:
            errors.append(f"maps[{index}].warning_count does not match findings")
        if item_errors and status != "blocked":
            errors.append(f"maps[{index}].status must be blocked when errors exist")
        if not item_errors and item_warnings and status != "passed_with_warnings":
            errors.append(f"maps[{index}].status must be passed_with_warnings when only warnings exist")
        if not item_errors and not item_warnings and status != "passed":
            errors.append(f"maps[{index}].status must be passed when no findings exist")
        error_count += item_errors
        warning_count += item_warnings
        resource_count += len(item.get("resource_nodes", []) if isinstance(item.get("resource_nodes"), list) else [])
        hazard_count += len(item.get("hazard_zones", []) if isinstance(item.get("hazard_zones"), list) else [])
        anchor_count += len(item.get("defense_anchors", []) if isinstance(item.get("defense_anchors"), list) else [])
        blocked_count += len(item.get("blocked_areas", []) if isinstance(item.get("blocked_areas"), list) else [])
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    expected_status = "blocked" if error_count else ("passed_with_warnings" if warning_count else "passed")
    if report.get("status") != expected_status:
        errors.append("status does not match aggregate finding severity")
    expected_summary = {
        "map_count": len(maps),
        "resource_node_count": resource_count,
        "hazard_zone_count": hazard_count,
        "defense_anchor_count": anchor_count,
        "blocked_area_count": blocked_count,
        "error_count": error_count,
        "warning_count": warning_count,
        "status_counts": dict(sorted(status_counts.items())),
    }
    for key, expected in expected_summary.items():
        if summary.get(key) != expected:
            errors.append(f"summary.{key}={summary.get(key)!r} does not match expected {expected!r}")
    usage_policy = report.get("usage_policy")
    if not isinstance(usage_policy, list) or "not_map_runtime_fact_source" not in usage_policy:
        errors.append("usage_policy must include not_map_runtime_fact_source")
    return list(dict.fromkeys(errors))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a review-only semantic geometry report for MapRuntimePackage v0.2 files."
    )
    parser.add_argument(
        "--runtime-package",
        action="append",
        dest="runtime_packages",
        help="MapRuntimePackage v0.2 JSON path. Repeat to include multiple maps. Defaults to all examples.",
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Report output path.")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA), help="Report schema path.")
    parser.add_argument("--runtime-schema", default=str(DEFAULT_RUNTIME_V02_SCHEMA), help="MapRuntimePackage v0.2 schema path.")
    parser.add_argument("--report-id", default=None)
    parser.add_argument("--created-at", default=None)
    args = parser.parse_args()

    package_paths = (
        [resolve(path) for path in args.runtime_packages]
        if args.runtime_packages
        else default_package_paths()
    )
    if not package_paths:
        print("no MapRuntimePackage v0.2 packages found")
        return 1

    runtime_schema = load_schema(resolve(args.runtime_schema))
    input_errors: list[str] = []
    runtime_packages: list[tuple[str, dict[str, Any]]] = []
    for package_path in package_paths:
        try:
            package = load_json(package_path)
        except FileNotFoundError:
            input_errors.append(f"{package_path}: file not found")
            continue
        except json.JSONDecodeError as exc:
            input_errors.append(f"{package_path}: invalid JSON: {exc}")
            continue
        if not isinstance(package, dict):
            input_errors.append(f"{package_path}: package root must be an object")
            continue
        errors = mrp_v02.validate_package_v02(package, runtime_schema)
        if errors:
            input_errors.extend(f"{package_path}: {error}" for error in errors)
            continue
        runtime_packages.append((rel(package_path), package))
    if input_errors:
        print("INVALID semantic geometry report inputs")
        for error in input_errors:
            print(f"- {error}")
        return 1

    report = build_report(
        runtime_packages,
        report_id=args.report_id,
        created_at=args.created_at,
    )
    report_errors = validate_report(report, load_schema(resolve(args.schema)))
    if report_errors:
        print("INVALID MapRuntimeV02SemanticGeometryReport; not writing")
        for error in report_errors:
            print(f"- {error}")
        return 1

    output_path = resolve(args.output)
    write_json(output_path, report)
    summary = report.get("summary", {})
    print(f"OK: wrote {output_path}")
    print(f"- report_id: {report.get('report_id')}")
    print(f"- status: {report.get('status')}")
    print(f"- maps: {summary.get('map_count')}")
    print(f"- errors: {summary.get('error_count')}")
    print(f"- warnings: {summary.get('warning_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
