#!/usr/bin/env python3
"""Validate MapDecorationZonePolicy v0.1 using only the Python standard library."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "map_decoration_zone_policy.v0.1"
REQUIRED_USAGE_POLICY = {
    "review_only",
    "not_map_runtime_fact_source",
    "does_not_modify_map_runtime_package",
    "no_image_to_logic_inference",
}
REQUIRED_LAYER_CLASSES = {
    "A_strong_semantic",
    "B_weak_semantic",
    "C_decoration",
    "D_atmosphere",
}
SENSITIVE_KEYS = {
    "provider",
    "model",
    "raw_prompt",
    "full_trace",
    "raw_json",
    "api_key",
    "secret",
    "unreviewed_content",
}
STRONG_ZONE_TYPES = {
    "route_band",
    "spawn_clearance",
    "objective_clearance",
    "build_slot_footprint",
    "resource_node_clearance",
    "hazard_zone",
    "defense_anchor_marker",
    "blocked_area",
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("MapDecorationZonePolicy root must be an object")
    return data


def reject_sensitive_keys(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} contains non-string object key")
            if key.lower() in SENSITIVE_KEYS:
                raise ValueError(f"{path}.{key} uses forbidden sensitive key")
            reject_sensitive_keys(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            reject_sensitive_keys(item, f"{path}[{index}]")


def require_object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def require_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value


def require_string_list(value: Any, path: str, *, min_items: int = 1) -> list[str]:
    if not isinstance(value, list) or len(value) < min_items:
        raise ValueError(f"{path} must be an array with at least {min_items} item(s)")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{path} must contain only non-empty strings")
    if len(set(value)) != len(value):
        raise ValueError(f"{path} must not contain duplicates")
    return value


def require_nonnegative_number(value: Any, path: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{path} must be a number")
    if value < 0:
        raise ValueError(f"{path} must be >= 0")
    return float(value)


def validate_usage_policy(value: Any, path: str) -> None:
    policy = set(require_string_list(value, path, min_items=len(REQUIRED_USAGE_POLICY)))
    missing = sorted(REQUIRED_USAGE_POLICY.difference(policy))
    if missing:
        raise ValueError(f"{path} missing required policy item(s): {missing}")


def validate_source_policy(data: dict[str, Any]) -> None:
    source_policy = require_object(data.get("source_policy"), "source_policy")
    expected = {
        "policy_role": "review_only_renderer_helper",
        "semantic_source": "MapRuntimePackage v0.1/v0.2",
        "geometry_source": "MapRuntimePackage.path_routes.waypoints",
        "runtime_fact_source": False,
        "player_default_runtime": False,
        "image_to_logic_inference_allowed": False,
        "may_modify_map_runtime_package": False,
        "provider_call_count": 0,
    }
    for key, expected_value in expected.items():
        if source_policy.get(key) != expected_value:
            raise ValueError(f"source_policy.{key} must be {expected_value!r}")


def validate_bbox(value: Any, path: str) -> None:
    bbox = require_object(value, path)
    for field in ("min_x", "min_y", "max_x", "max_y"):
        if not isinstance(bbox.get(field), (int, float)) or isinstance(bbox.get(field), bool):
            raise ValueError(f"{path}.{field} must be a number")
    if float(bbox["max_x"]) < float(bbox["min_x"]):
        raise ValueError(f"{path}.max_x must be >= min_x")
    if float(bbox["max_y"]) < float(bbox["min_y"]):
        raise ValueError(f"{path}.max_y must be >= min_y")


def validate_cells(value: Any, path: str) -> None:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{path} must be a non-empty array")
    seen: set[tuple[int, int]] = set()
    for index, cell in enumerate(value):
        item = require_object(cell, f"{path}[{index}]")
        x = item.get("x")
        y = item.get("y")
        if not isinstance(x, int) or not isinstance(y, int):
            raise ValueError(f"{path}[{index}].x/y must be integers")
        if x < 0 or y < 0:
            raise ValueError(f"{path}[{index}].x/y must be >= 0")
        key = (x, y)
        if key in seen:
            raise ValueError(f"{path}[{index}] duplicates cell {key}")
        seen.add(key)


def validate_path_t_range(value: Any, path: str) -> None:
    item = require_object(value, path)
    start = item.get("start")
    end = item.get("end")
    for field, raw in (("start", start), ("end", end)):
        if not isinstance(raw, (int, float)) or isinstance(raw, bool):
            raise ValueError(f"{path}.{field} must be a number")
        if raw < 0 or raw > 1:
            raise ValueError(f"{path}.{field} must be in range 0..1")
    if float(end) < float(start):
        raise ValueError(f"{path}.end must be >= start")


def validate_reserved_zone(zone: Any, path: str) -> str:
    item = require_object(zone, path)
    zone_id = require_string(item.get("zone_id"), f"{path}.zone_id")
    zone_type = require_string(item.get("zone_type"), f"{path}.zone_type")
    if zone_type not in STRONG_ZONE_TYPES:
        raise ValueError(f"{path}.zone_type must be one of {sorted(STRONG_ZONE_TYPES)}")
    if item.get("semantic_class") != "A_strong_semantic":
        raise ValueError(f"{path}.semantic_class must be A_strong_semantic")
    require_string(item.get("source_ref"), f"{path}.source_ref")
    require_string(item.get("geometry_kind"), f"{path}.geometry_kind")
    require_nonnegative_number(item.get("clearance_cells"), f"{path}.clearance_cells")
    protection_policy = set(require_string_list(item.get("protection_policy"), f"{path}.protection_policy"))
    if "no_decoration_overlap" not in protection_policy:
        raise ValueError(f"{path}.protection_policy must include no_decoration_overlap")

    geometry_fields = [field for field in ("bbox_cells", "cells", "path_t_range") if field in item]
    if not geometry_fields:
        raise ValueError(f"{path} must include bbox_cells, cells, or path_t_range")
    if "bbox_cells" in item:
        validate_bbox(item["bbox_cells"], f"{path}.bbox_cells")
    if "cells" in item:
        validate_cells(item["cells"], f"{path}.cells")
    if "path_t_range" in item:
        validate_path_t_range(item["path_t_range"], f"{path}.path_t_range")
    return zone_id


def validate_allowed_zone(zone: Any, path: str) -> str:
    item = require_object(zone, path)
    zone_id = require_string(item.get("zone_id"), f"{path}.zone_id")
    zone_type = require_string(item.get("zone_type"), f"{path}.zone_type")
    if zone_type not in {
        "map_border_decoration",
        "route_shoulder_decoration",
        "empty_cell_decoration",
        "semantic_prop_shoulder",
        "atmosphere_overlay",
    }:
        raise ValueError(f"{path}.zone_type is not a supported decoration zone type")
    semantic_class = require_string(item.get("semantic_class"), f"{path}.semantic_class")
    if semantic_class not in {"B_weak_semantic", "C_decoration", "D_atmosphere"}:
        raise ValueError(f"{path}.semantic_class is not a weak/decorative/atmosphere class")
    require_string(item.get("anchor_ref"), f"{path}.anchor_ref")
    require_string(item.get("geometry_kind"), f"{path}.geometry_kind")
    require_string_list(item.get("allowed_prefab_tags"), f"{path}.allowed_prefab_tags")
    forbidden_overlap = set(require_string_list(item.get("forbidden_overlap"), f"{path}.forbidden_overlap"))
    if "route_band" not in forbidden_overlap or "build_slot_footprint" not in forbidden_overlap:
        raise ValueError(f"{path}.forbidden_overlap must include route_band and build_slot_footprint")
    require_string_list(item.get("placement_rules"), f"{path}.placement_rules")
    if item.get("density_hint") not in {"low", "medium", "high"}:
        raise ValueError(f"{path}.density_hint must be low, medium, or high")
    return zone_id


def validate_layer_rules(value: Any, path: str) -> None:
    if not isinstance(value, list) or len(value) < 4:
        raise ValueError(f"{path} must contain at least 4 layer rules")
    classes: set[str] = set()
    rule_ids: set[str] = set()
    for index, rule in enumerate(value):
        item = require_object(rule, f"{path}[{index}]")
        semantic_class = require_string(item.get("semantic_class"), f"{path}[{index}].semantic_class")
        if semantic_class not in REQUIRED_LAYER_CLASSES:
            raise ValueError(f"{path}[{index}].semantic_class is not supported")
        classes.add(semantic_class)
        rule_id = require_string(item.get("rule_id"), f"{path}[{index}].rule_id")
        if rule_id in rule_ids:
            raise ValueError(f"{path}[{index}].rule_id duplicates {rule_id}")
        rule_ids.add(rule_id)
        require_string(item.get("description"), f"{path}[{index}].description")
        require_string_list(item.get("must_obey"), f"{path}[{index}].must_obey")
    missing = sorted(REQUIRED_LAYER_CLASSES.difference(classes))
    if missing:
        raise ValueError(f"{path} missing semantic class rule(s): {missing}")


def validate_source_package(value: Any, path: str) -> None:
    package = require_object(value, path)
    source_path = require_string(package.get("path"), f"{path}.path")
    lowered_path = source_path.lower()
    if "://" in lowered_path or lowered_path.startswith("/"):
        raise ValueError(f"{path}.path must be a repo-relative local path")
    require_string(package.get("package_id"), f"{path}.package_id")
    require_string(package.get("node_id"), f"{path}.node_id")
    if package.get("schema_version") not in {"map_runtime_package.v0.1", "map_runtime_package.v0.2"}:
        raise ValueError(f"{path}.schema_version must be map_runtime_package.v0.1 or v0.2")


def validate_grid(value: Any, path: str) -> None:
    grid = require_object(value, path)
    require_string(grid.get("projection"), f"{path}.projection")
    for field in ("width_cells", "height_cells", "cell_size"):
        if not isinstance(grid.get(field), int) or grid[field] <= 0:
            raise ValueError(f"{path}.{field} must be a positive integer")


def validate_map(item: Any, path: str) -> tuple[int, int, str]:
    map_policy = require_object(item, path)
    map_id = require_string(map_policy.get("map_id"), f"{path}.map_id")
    validate_source_package(map_policy.get("source_package"), f"{path}.source_package")
    validate_grid(map_policy.get("grid"), f"{path}.grid")

    reserved = map_policy.get("reserved_zones")
    if not isinstance(reserved, list) or not reserved:
        raise ValueError(f"{path}.reserved_zones must be a non-empty array")
    allowed = map_policy.get("allowed_decoration_zones")
    if not isinstance(allowed, list) or not allowed:
        raise ValueError(f"{path}.allowed_decoration_zones must be a non-empty array")
    zone_ids: set[str] = set()
    reserved_types: set[str] = set()
    for index, zone in enumerate(reserved):
        zone_id = validate_reserved_zone(zone, f"{path}.reserved_zones[{index}]")
        if zone_id in zone_ids:
            raise ValueError(f"{path}.reserved_zones[{index}].zone_id duplicates {zone_id}")
        zone_ids.add(zone_id)
        reserved_types.add(require_object(zone, f"{path}.reserved_zones[{index}]").get("zone_type", ""))
    for index, zone in enumerate(allowed):
        zone_id = validate_allowed_zone(zone, f"{path}.allowed_decoration_zones[{index}]")
        if zone_id in zone_ids:
            raise ValueError(f"{path}.allowed_decoration_zones[{index}].zone_id duplicates {zone_id}")
        zone_ids.add(zone_id)

    if "route_band" not in reserved_types:
        raise ValueError(f"{path}.reserved_zones must include at least one route_band zone")
    if "build_slot_footprint" not in reserved_types:
        raise ValueError(f"{path}.reserved_zones must include at least one build_slot_footprint zone")
    validate_layer_rules(map_policy.get("layer_rules"), f"{path}.layer_rules")

    report = require_object(map_policy.get("validation_report"), f"{path}.validation_report")
    if report.get("reserved_zone_count") != len(reserved):
        raise ValueError(f"{path}.validation_report.reserved_zone_count mismatch")
    if report.get("allowed_decoration_zone_count") != len(allowed):
        raise ValueError(f"{path}.validation_report.allowed_decoration_zone_count mismatch")
    warnings = report.get("warnings")
    if not isinstance(warnings, list) or any(not isinstance(warning, str) for warning in warnings):
        raise ValueError(f"{path}.validation_report.warnings must be an array of strings")
    if report.get("warning_count") != len(warnings):
        raise ValueError(f"{path}.validation_report.warning_count mismatch")
    expected_status = "passed_with_warnings" if warnings else "passed"
    if report.get("status") != expected_status:
        raise ValueError(f"{path}.validation_report.status must be {expected_status}")
    return len(reserved), len(allowed), map_id


def validate(data: dict[str, Any]) -> None:
    reject_sensitive_keys(data)
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
    require_string(data.get("policy_id"), "policy_id")
    require_string(data.get("generated_at"), "generated_at")
    validate_source_policy(data)
    validate_usage_policy(data.get("usage_policy"), "usage_policy")

    maps = data.get("maps")
    if not isinstance(maps, list) or not maps:
        raise ValueError("maps must be a non-empty array")
    map_ids: set[str] = set()
    reserved_count = 0
    allowed_count = 0
    versions: set[str] = set()
    for index, item in enumerate(maps):
        reserved_item_count, allowed_item_count, map_id = validate_map(item, f"maps[{index}]")
        if map_id in map_ids:
            raise ValueError(f"maps[{index}].map_id duplicates {map_id}")
        map_ids.add(map_id)
        reserved_count += reserved_item_count
        allowed_count += allowed_item_count
        source = require_object(item, f"maps[{index}]").get("source_package")
        versions.add(require_object(source, f"maps[{index}].source_package").get("schema_version"))

    summary = require_object(data.get("summary"), "summary")
    if summary.get("map_count") != len(maps):
        raise ValueError("summary.map_count mismatch")
    if summary.get("reserved_zone_count") != reserved_count:
        raise ValueError("summary.reserved_zone_count mismatch")
    if summary.get("allowed_decoration_zone_count") != allowed_count:
        raise ValueError("summary.allowed_decoration_zone_count mismatch")
    source_versions = set(require_string_list(summary.get("source_schema_versions"), "summary.source_schema_versions"))
    if source_versions != versions:
        raise ValueError("summary.source_schema_versions mismatch")
    require_string(summary.get("strong_semantic_policy"), "summary.strong_semantic_policy")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("policy", type=Path)
    args = parser.parse_args()
    try:
        validate(load_json(args.policy))
    except Exception as exc:  # noqa: BLE001 - CLI validator should print concise failures.
        print(f"map decoration zone policy validation failed: {exc}", file=sys.stderr)
        return 1
    print(f"map decoration zone policy validation passed: {args.policy}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
