#!/usr/bin/env python3
"""Validate MapTemplateCatalog v0.1 using only the Python standard library."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "map_template_catalog.v0.1"
REQUIRED_TEMPLATE_IDS = {
    "s_curve_single_path",
    "two_lane_merge",
    "zigzag_long_path",
    "short_pressure_path",
    "central_loop",
}
REQUIRED_USAGE_POLICY = {
    "developer_side_candidate_only",
    "not_runtime_fact_source",
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


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("MapTemplateCatalog root must be an object")
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


def validate_usage_policy(value: Any, path: str) -> None:
    usage_policy = set(require_string_list(value, path, min_items=2))
    missing = sorted(REQUIRED_USAGE_POLICY.difference(usage_policy))
    if missing:
        raise ValueError(f"{path} missing required policy item(s): {missing}")


def validate_source_policy(data: dict[str, Any]) -> None:
    source_policy = require_object(data.get("source_policy"), "source_policy")
    expected = {
        "catalog_role": "developer_side_template_candidate_seed_catalog",
        "runtime_fact_source": False,
        "player_default_runtime": False,
        "image_to_logic_inference_allowed": False,
        "may_modify_map_runtime_package": False,
    }
    for key, expected_value in expected.items():
        if source_policy.get(key) != expected_value:
            raise ValueError(f"source_policy.{key} must be {expected_value!r}")


def validate_point(point: Any, path: str) -> None:
    point_obj = require_object(point, path)
    for axis in ("x", "y"):
        value = point_obj.get(axis)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"{path}.{axis} must be a number")
        if value < 0 or value > 1:
            raise ValueError(f"{path}.{axis} must be in normalized range 0..1")


def validate_template(template: Any, path: str) -> str:
    item = require_object(template, path)
    template_id = require_string(item.get("id"), f"{path}.id")
    require_string(item.get("display_label"), f"{path}.display_label")
    require_string(item.get("description"), f"{path}.description")
    require_string(item.get("topology_kind"), f"{path}.topology_kind")
    require_string_list(item.get("recommended_node_uses"), f"{path}.recommended_node_uses")
    validate_usage_policy(item.get("usage_policy"), f"{path}.usage_policy")

    grid = require_object(item.get("grid_constraints"), f"{path}.grid_constraints")
    for field in ("min_width_cells", "min_height_cells"):
        value = grid.get(field)
        if not isinstance(value, int) or value < 5:
            raise ValueError(f"{path}.grid_constraints.{field} must be an integer >= 5")
    require_string(grid.get("preferred_aspect"), f"{path}.grid_constraints.preferred_aspect")
    require_string(grid.get("notes"), f"{path}.grid_constraints.notes")

    blueprint = require_object(item.get("route_blueprint"), f"{path}.route_blueprint")
    if blueprint.get("coordinate_space") != "normalized_0_1":
        raise ValueError(f"{path}.route_blueprint.coordinate_space must be normalized_0_1")
    road_width = blueprint.get("suggested_road_width_normalized")
    if not isinstance(road_width, (int, float)) or isinstance(road_width, bool):
        raise ValueError(f"{path}.route_blueprint.suggested_road_width_normalized must be a number")
    if road_width <= 0 or road_width > 0.25:
        raise ValueError(
            f"{path}.route_blueprint.suggested_road_width_normalized must be > 0 and <= 0.25"
        )
    routes = blueprint.get("routes")
    if not isinstance(routes, list) or not routes:
        raise ValueError(f"{path}.route_blueprint.routes must be a non-empty array")
    route_ids: set[str] = set()
    for route_index, route in enumerate(routes):
        route_path = f"{path}.route_blueprint.routes[{route_index}]"
        route_obj = require_object(route, route_path)
        route_id = require_string(route_obj.get("route_id"), f"{route_path}.route_id")
        if route_id in route_ids:
            raise ValueError(f"{route_path}.route_id duplicates {route_id}")
        route_ids.add(route_id)
        require_string(route_obj.get("role"), f"{route_path}.role")
        points = route_obj.get("normalized_control_points")
        if not isinstance(points, list) or len(points) < 2:
            raise ValueError(f"{route_path}.normalized_control_points must contain at least 2 points")
        for point_index, point in enumerate(points):
            validate_point(point, f"{route_path}.normalized_control_points[{point_index}]")
    require_string(blueprint.get("notes"), f"{path}.route_blueprint.notes")

    slot_strategy = require_object(item.get("slot_strategy"), f"{path}.slot_strategy")
    require_string(slot_strategy.get("summary"), f"{path}.slot_strategy.summary")
    require_string_list(slot_strategy.get("preferred_zones"), f"{path}.slot_strategy.preferred_zones")
    require_string_list(slot_strategy.get("avoid_zones"), f"{path}.slot_strategy.avoid_zones")

    hooks = require_object(item.get("semantic_hooks"), f"{path}.semantic_hooks")
    for hook_name in ("resource", "hazard", "defense", "blocking"):
        hook = require_object(hooks.get(hook_name), f"{path}.semantic_hooks.{hook_name}")
        if hook.get("allowed") not in {True, False}:
            raise ValueError(f"{path}.semantic_hooks.{hook_name}.allowed must be boolean")
        require_string(hook.get("rules_summary"), f"{path}.semantic_hooks.{hook_name}.rules_summary")
    return template_id


def validate(data: dict[str, Any]) -> None:
    reject_sensitive_keys(data)
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
    require_string(data.get("catalog_id"), "catalog_id")
    require_string(data.get("generated_at"), "generated_at")
    validate_source_policy(data)
    validate_usage_policy(data.get("usage_policy"), "usage_policy")

    templates = data.get("templates")
    if not isinstance(templates, list) or len(templates) < 5:
        raise ValueError("templates must contain at least 5 templates")
    ids = [validate_template(template, f"templates[{index}]") for index, template in enumerate(templates)]
    if len(set(ids)) != len(ids):
        raise ValueError("template ids must be unique")
    missing = sorted(REQUIRED_TEMPLATE_IDS.difference(ids))
    if missing:
        raise ValueError(f"templates missing required ids: {missing}")

    summary = require_object(data.get("summary"), "summary")
    if summary.get("template_count") != len(templates):
        raise ValueError("summary.template_count must match templates length")
    required_ids = set(require_string_list(summary.get("required_template_ids"), "summary.required_template_ids"))
    missing_summary_ids = sorted(REQUIRED_TEMPLATE_IDS.difference(required_ids))
    if missing_summary_ids:
        raise ValueError(f"summary.required_template_ids missing required ids: {missing_summary_ids}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    args = parser.parse_args()
    try:
        validate(load_json(args.catalog))
    except Exception as exc:  # noqa: BLE001 - CLI validator should print concise failures.
        print(f"map template catalog validation failed: {exc}", file=sys.stderr)
        return 1
    print(f"map template catalog validation passed: {args.catalog}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
