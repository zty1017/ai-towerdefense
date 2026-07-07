#!/usr/bin/env python3
"""Validate a ProceduralMapPreview report.

The report is a review-only evidence artifact. Validation checks that the SVG
exists, its digest matches, and the report keeps gameplay semantics anchored in
MapRuntimePackage rather than in the preview renderer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

try:
    from validate_map_decoration_zone_policy import validate as validate_decoration_policy
except ModuleNotFoundError:  # pragma: no cover - supports package-style imports.
    from tools.asset_graph.validate_map_decoration_zone_policy import validate as validate_decoration_policy  # type: ignore


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_repo_path(value: Any) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def validate(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    require(report.get("schema_version") == "procedural_map_preview_report.v0.1", "schema_version must be procedural_map_preview_report.v0.1", errors)
    require(report.get("status") == "preview_ready_review_only", "status must be preview_ready_review_only", errors)

    svg_path = resolve_repo_path(report.get("preview_svg_path"))
    require(svg_path is not None and svg_path.exists(), "preview_svg_path must point to an existing SVG file", errors)
    if svg_path is not None and svg_path.exists():
        require(svg_path.suffix.lower() == ".svg", "preview artifact must be an SVG file", errors)
        require(sha256_file(svg_path) == report.get("preview_svg_sha256"), "preview_svg_sha256 does not match SVG file", errors)
        svg = svg_path.read_text(encoding="utf-8", errors="replace")
        require("<svg" in svg and "runtime-routes" in svg, "preview SVG must contain runtime route layer", errors)
        require("debug_control_overlay" not in svg, "preview SVG must not include debug control overlay", errors)
    else:
        svg = ""

    policy = report.get("semantic_source_policy")
    require(isinstance(policy, dict), "semantic_source_policy must be an object", errors)
    if isinstance(policy, dict):
        for key in ("routes", "build_slots", "objectives", "spawn_points"):
            require(policy.get(key) == "map_runtime_package", f"semantic_source_policy.{key} must be map_runtime_package", errors)
        for key in ("resource_nodes", "hazard_zones", "defense_anchors", "blocked_areas"):
            if key in policy:
                require(policy.get(key) == "map_runtime_package", f"semantic_source_policy.{key} must be map_runtime_package", errors)
        require(policy.get("colors") == "map_style_pack", "semantic_source_policy.colors must be map_style_pack", errors)
        require(
            policy.get("road_width_and_slot_footprint") == "procedural_map_render_plan",
            "semantic_source_policy.road_width_and_slot_footprint must be procedural_map_render_plan",
            errors,
        )
        if "resource_hazard_and_blocking_style" in policy:
            require(
                policy.get("resource_hazard_and_blocking_style") == "procedural_map_render_plan",
                "semantic_source_policy.resource_hazard_and_blocking_style must be procedural_map_render_plan",
                errors,
            )
        if "decoration_zones" in policy:
            require(
                policy.get("decoration_zones") == "map_decoration_zone_policy_review_only",
                "semantic_source_policy.decoration_zones must be map_decoration_zone_policy_review_only",
                errors,
            )
            require(
                policy.get("decoration_policy_runtime_fact_source") is False,
                "semantic_source_policy.decoration_policy_runtime_fact_source must be false",
                errors,
            )
            require(
                policy.get("decoration_policy_may_modify_map_runtime_package") is False,
                "semantic_source_policy.decoration_policy_may_modify_map_runtime_package must be false",
                errors,
            )

    usage = report.get("usage_policy")
    require(isinstance(usage, list), "usage_policy must be an array", errors)
    if isinstance(usage, list):
        for required in ("review_only", "not_player_runtime", "not_published_visual_layer", "does_not_modify_map_runtime_package"):
            require(required in usage, f"usage_policy missing {required}", errors)

    summary = report.get("render_summary")
    require(isinstance(summary, dict), "render_summary must be an object", errors)
    if isinstance(summary, dict):
        require(int(summary.get("route_count") or 0) >= 1, "render_summary.route_count must be >= 1", errors)
        require(int(summary.get("build_slot_count") or 0) >= 1, "render_summary.build_slot_count must be >= 1", errors)
        require(int(summary.get("objective_count") or 0) >= 1, "render_summary.objective_count must be >= 1", errors)
        require(int(summary.get("spawn_point_count") or 0) >= 1, "render_summary.spawn_point_count must be >= 1", errors)
        for key in ("resource_node_count", "hazard_zone_count", "defense_anchor_count", "blocked_area_count"):
            if key in summary:
                require(int(summary.get(key) or 0) >= 0, f"render_summary.{key} must be >= 0", errors)
        decoration = as_obj(summary.get("decoration_policy"))
        if decoration:
            require(
                decoration.get("decoration_policy_runtime_fact_source") is False,
                "render_summary.decoration_policy.decoration_policy_runtime_fact_source must be false",
                errors,
            )
            require(
                decoration.get("decoration_policy_may_modify_map_runtime_package") is False,
                "render_summary.decoration_policy.decoration_policy_may_modify_map_runtime_package must be false",
                errors,
            )
            require(
                int(decoration.get("decoration_policy_provider_call_count") or 0) == 0,
                "render_summary.decoration_policy.decoration_policy_provider_call_count must be 0",
                errors,
            )
            for key in ("allowed_decoration_zone_count", "reserved_zone_count", "decoration_policy_drawn_item_count"):
                require(int(decoration.get(key) or 0) >= 0, f"render_summary.decoration_policy.{key} must be >= 0", errors)
            if decoration.get("decoration_policy_consumed") is True:
                require(
                    "decoration-policy-layer" in svg,
                    "preview SVG must contain decoration-policy-layer when decoration policy is consumed",
                    errors,
                )

    source_refs = report.get("source_refs")
    if isinstance(source_refs, dict) and source_refs.get("map_decoration_zone_policy_path"):
        decoration_policy_path = resolve_repo_path(source_refs.get("map_decoration_zone_policy_path"))
        require(
            decoration_policy_path is not None and decoration_policy_path.exists(),
            "source_refs.map_decoration_zone_policy_path must point to an existing policy file",
            errors,
        )
        if decoration_policy_path is not None and decoration_policy_path.exists():
            try:
                decoration_policy = load_json(decoration_policy_path)
                if not isinstance(decoration_policy, dict):
                    errors.append("map decoration zone policy root must be an object")
                else:
                    validate_decoration_policy(decoration_policy)
            except Exception as exc:  # noqa: BLE001 - validator should report concise failures.
                errors.append(f"map decoration zone policy validation failed: {exc}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a procedural map preview report.")
    parser.add_argument("report", help="Procedural map preview report JSON path.")
    args = parser.parse_args()

    report_path = Path(args.report)
    try:
        report = load_json(report_path)
    except FileNotFoundError:
        print("INVALID ProceduralMapPreviewReport")
        print(f"- report file not found: {report_path}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID ProceduralMapPreviewReport")
        print(f"- report is not valid JSON: {exc}")
        return 1
    if not isinstance(report, dict):
        print("INVALID ProceduralMapPreviewReport")
        print("- report root must be an object")
        return 1
    errors = validate(report)
    if errors:
        print("INVALID ProceduralMapPreviewReport")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"OK: {report_path}")
    print(f"- status: {report.get('status')}")
    print(f"- preview_svg_path: {report.get('preview_svg_path')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
