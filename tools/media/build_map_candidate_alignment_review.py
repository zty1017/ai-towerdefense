#!/usr/bin/env python3
"""Build a review-only alignment report for node map painted candidates.

This tool does not promote candidate images into MapRuntimePackage. It checks
whether a candidate has enough structural evidence to enter the next alignment
stage: crop/resize normalization, path overlay review, build-slot overlay
review, objective overlay review, and explicit human or stronger vision-model
promotion.
"""

from __future__ import annotations

import argparse
import json
import struct
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPORT_VERSION = "map_candidate_alignment_review.v0.1"
DEFAULT_CANDIDATE_REVIEW = ROOT / "examples/review_packs/node_map_painted_candidate_review.v0.2.json"
DEFAULT_RUNTIME_PACKAGE_DIR = ROOT / "examples/map_runtime_packages"
DEFAULT_OUTPUT = ROOT / "examples/review_packs/map_candidate_alignment_review.v0.1.json"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def resolve_repo_path(value: Any) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def png_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        with path.open("rb") as handle:
            header = handle.read(24)
    except FileNotFoundError:
        return None
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", header[16:24])


def parse_size(size: Any) -> tuple[int, int] | None:
    if not isinstance(size, str) or "x" not in size:
        return None
    left, right = size.lower().split("x", 1)
    try:
        width = int(left)
        height = int(right)
    except ValueError:
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


def runtime_package_by_node(package_dir: Path) -> dict[str, dict[str, Any]]:
    packages: dict[str, dict[str, Any]] = {}
    for path in sorted(package_dir.glob("*.map_runtime_package.json")):
        package = load_json(path)
        node_id = package.get("node_id")
        if isinstance(node_id, str) and node_id:
            package["_package_path"] = rel(path)
            packages[node_id] = package
    return packages


def cell_to_pixel_scale(package: dict[str, Any], target_size: tuple[int, int]) -> dict[str, float]:
    grid = as_obj(package.get("grid"))
    width_cells = float(grid.get("width_cells") or 0)
    height_cells = float(grid.get("height_cells") or 0)
    width, height = target_size
    return {
        "x_pixels_per_cell": round(width / width_cells, 4) if width_cells else 0,
        "y_pixels_per_cell": round(height / height_cells, 4) if height_cells else 0,
    }


def count_objectives(package: dict[str, Any]) -> int:
    objectives = as_obj(package.get("objectives"))
    return (1 if isinstance(objectives.get("core_target"), dict) else 0) + len(
        [target for target in as_list(objectives.get("optional_targets")) if isinstance(target, dict)]
    )


def build_candidate_alignment(
    candidate: dict[str, Any],
    packages: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    node_id = str(candidate.get("node_id") or "")
    candidate_path = resolve_repo_path(candidate.get("candidate_path"))
    sidecar_path = resolve_repo_path(candidate.get("sidecar_path"))
    sidecar = load_json(sidecar_path) if sidecar_path and sidecar_path.exists() else {}
    requested_size = parse_size(sidecar.get("size"))
    actual_size = png_dimensions(candidate_path) if candidate_path else None
    package = packages.get(node_id)

    issues: list[str] = []
    warnings: list[str] = []
    next_steps: list[str] = []

    if package is None:
        issues.append("missing_runtime_package_for_node")
    if candidate_path is None or not candidate_path.exists():
        issues.append("candidate_image_missing")
    elif actual_size is None:
        issues.append("candidate_image_not_png")
    if not sidecar:
        warnings.append("candidate_sidecar_missing")
    if candidate.get("review_status") != "alignment_review_ready":
        warnings.append("candidate_not_marked_alignment_review_ready")

    transform_required = False
    if requested_size and actual_size:
        if requested_size != actual_size:
            warnings.append("candidate_size_differs_from_requested_size")
            transform_required = True
    elif actual_size:
        warnings.append("requested_size_unavailable")

    target_size = requested_size or actual_size or (0, 0)
    if package:
        if not as_list(package.get("path_routes")):
            issues.append("runtime_package_has_no_path_routes")
        if not as_list(package.get("build_slots")):
            issues.append("runtime_package_has_no_build_slots")
        if not as_list(package.get("spawn_points")):
            issues.append("runtime_package_has_no_spawn_points")
        if count_objectives(package) <= 0:
            issues.append("runtime_package_has_no_objectives")

    if not issues:
        next_steps.extend(
            [
                "normalize_candidate_to_target_size",
                "overlay_runtime_paths_for_visual_alignment_review",
                "overlay_build_slots_for_drag_deploy_review",
                "overlay_objectives_and_spawn_points_for_combat_readability_review",
                "require_explicit_promotion_before_published_visual_layer",
            ]
        )

    status = (
        "blocked"
        if issues
        else ("alignment_prerequisites_passed_with_transform_required" if transform_required else "alignment_prerequisites_passed")
    )

    return {
        "node_id": node_id,
        "candidate_path": candidate.get("candidate_path"),
        "sidecar_path": candidate.get("sidecar_path"),
        "runtime_package_path": package.get("_package_path") if package else None,
        "candidate_review_status": candidate.get("review_status"),
        "requested_size": {"width": requested_size[0], "height": requested_size[1]} if requested_size else None,
        "actual_size": {"width": actual_size[0], "height": actual_size[1]} if actual_size else None,
        "target_size": {"width": target_size[0], "height": target_size[1]} if target_size != (0, 0) else None,
        "transform_required": transform_required,
        "runtime_structure": {
            "path_route_count": len(as_list(package.get("path_routes"))) if package else 0,
            "build_slot_count": len(as_list(package.get("build_slots"))) if package else 0,
            "spawn_point_count": len(as_list(package.get("spawn_points"))) if package else 0,
            "objective_count": count_objectives(package) if package else 0,
            "grid": as_obj(package.get("grid")) if package else {},
            "target_pixel_scale": cell_to_pixel_scale(package, target_size) if package and target_size != (0, 0) else {},
        },
        "issues": sorted(set(issues)),
        "warnings": sorted(set(warnings)),
        "status": status,
        "next_steps": next_steps,
        "promotion_policy": "review_only; do not update MapRuntimePackage or published visual layers",
    }


def build_report(candidate_review_path: Path, package_dir: Path) -> dict[str, Any]:
    candidate_review = load_json(candidate_review_path)
    packages = runtime_package_by_node(package_dir)
    candidates = [
        build_candidate_alignment(candidate, packages)
        for candidate in as_list(candidate_review.get("candidates"))
        if isinstance(candidate, dict)
    ]
    status_counts = Counter(str(candidate.get("status")) for candidate in candidates)
    issue_counts = Counter(issue for candidate in candidates for issue in as_list(candidate.get("issues")))
    warning_counts = Counter(warning for candidate in candidates for warning in as_list(candidate.get("warnings")))
    blocked_count = sum(1 for candidate in candidates if candidate.get("status") == "blocked")
    transform_required_count = sum(1 for candidate in candidates if candidate.get("transform_required"))
    status = "blocked" if blocked_count else (
        "ready_for_overlay_review_with_transform_required"
        if transform_required_count
        else "ready_for_overlay_review"
    )
    return {
        "schema_version": REPORT_VERSION,
        "report_id": "mvp_map_candidate_alignment_review",
        "candidate_review_path": rel(candidate_review_path),
        "runtime_package_dir": rel(package_dir),
        "status": status,
        "summary": {
            "candidate_count": len(candidates),
            "blocked_count": blocked_count,
            "transform_required_count": transform_required_count,
            "status_counts": dict(sorted(status_counts.items())),
            "issue_counts": dict(sorted(issue_counts.items())),
            "warning_counts": dict(sorted(warning_counts.items())),
        },
        "candidates": candidates,
        "policy": [
            "This report checks alignment prerequisites only; it does not perform pixel-level semantic recognition.",
            "Candidate images must be normalized and reviewed with runtime overlays before promotion.",
            "MapRuntimePackage remains authoritative for paths, build slots, objectives, spawn points, and combat logic.",
            "A candidate cannot become a published visual layer without an explicit promotion step.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build map candidate alignment review report.")
    parser.add_argument("--candidate-review", default=str(DEFAULT_CANDIDATE_REVIEW))
    parser.add_argument("--runtime-package-dir", default=str(DEFAULT_RUNTIME_PACKAGE_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    candidate_review = Path(args.candidate_review)
    if not candidate_review.is_absolute():
        candidate_review = ROOT / candidate_review
    runtime_package_dir = Path(args.runtime_package_dir)
    if not runtime_package_dir.is_absolute():
        runtime_package_dir = ROOT / runtime_package_dir
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output

    report = build_report(candidate_review, runtime_package_dir)
    write_json(output, report)
    print(f"Wrote {output}")
    print(f"- status: {report['status']}")
    print(f"- candidates: {report['summary']['candidate_count']}")
    return 0 if report["summary"]["candidate_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
