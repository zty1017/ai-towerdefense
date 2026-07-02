#!/usr/bin/env python3
"""Audit sprite cutout quality for reviewed frontend media manifests.

This deterministic check is narrower than vision review and a little broader
than runtime loadability. It looks for geometry issues that make generated
PNG cutouts awkward as game sprites: fragmented subjects, edge contact, and
large interior transparent holes after matte removal.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MEDIA_DIR = Path(__file__).resolve().parent
if str(MEDIA_DIR) not in sys.path:
    sys.path.insert(0, str(MEDIA_DIR))

import png_pipeline  # noqa: E402


REPORT_VERSION = "sprite_cutout_quality_report.v0.1"
SPRITE_ROLES = {
    "tower_sprite",
    "unit_sprite",
    "enemy_sprite",
    "monster_sprite",
    "objective_sprite",
    "defense_sprite",
    "npc_sprite",
    "subject_sprite",
    "cutout_source",
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_local_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def visible_components(
    image: png_pipeline.PngImage,
    *,
    alpha_threshold: int,
) -> list[int]:
    width, height = image.width, image.height
    total = width * height
    visited = bytearray(total)
    components: list[int] = []

    def visible(pos: int) -> bool:
        return image.pixels[pos * 4 + 3] > alpha_threshold

    for start in range(total):
        if visited[start] or not visible(start):
            continue
        visited[start] = 1
        stack = [start]
        size = 0
        while stack:
            pos = stack.pop()
            size += 1
            x = pos % width
            y = pos // width
            neighbors = []
            if x > 0:
                neighbors.append(pos - 1)
            if x + 1 < width:
                neighbors.append(pos + 1)
            if y > 0:
                neighbors.append(pos - width)
            if y + 1 < height:
                neighbors.append(pos + width)
            for nxt in neighbors:
                if not visited[nxt] and visible(nxt):
                    visited[nxt] = 1
                    stack.append(nxt)
        components.append(size)
    return sorted(components, reverse=True)


def enclosed_transparent_components(
    image: png_pipeline.PngImage,
    bbox: tuple[int, int, int, int] | None,
    *,
    alpha_threshold: int,
) -> list[int]:
    if bbox is None:
        return []
    x0, y0, x1, y1 = bbox
    bbox_width = x1 - x0
    bbox_height = y1 - y0
    total = bbox_width * bbox_height
    if total <= 0:
        return []
    visited = bytearray(total)
    holes: list[int] = []

    def local_to_image_pos(local_pos: int) -> int:
        local_x = local_pos % bbox_width
        local_y = local_pos // bbox_width
        return (y0 + local_y) * image.width + (x0 + local_x)

    def transparent(local_pos: int) -> bool:
        return image.pixels[local_to_image_pos(local_pos) * 4 + 3] <= alpha_threshold

    for start in range(total):
        if visited[start] or not transparent(start):
            continue
        visited[start] = 1
        stack = [start]
        size = 0
        touches_bbox_edge = False
        while stack:
            pos = stack.pop()
            size += 1
            x = pos % bbox_width
            y = pos // bbox_width
            if x == 0 or y == 0 or x + 1 == bbox_width or y + 1 == bbox_height:
                touches_bbox_edge = True
            neighbors = []
            if x > 0:
                neighbors.append(pos - 1)
            if x + 1 < bbox_width:
                neighbors.append(pos + 1)
            if y > 0:
                neighbors.append(pos - bbox_width)
            if y + 1 < bbox_height:
                neighbors.append(pos + bbox_width)
            for nxt in neighbors:
                if not visited[nxt] and transparent(nxt):
                    visited[nxt] = 1
                    stack.append(nxt)
        if not touches_bbox_edge:
            holes.append(size)
    return sorted(holes, reverse=True)


def edge_visible_counts(
    image: png_pipeline.PngImage,
    *,
    alpha_threshold: int,
) -> dict[str, int]:
    top = bottom = left = right = 0
    for x in range(image.width):
        if image.pixels[x * 4 + 3] > alpha_threshold:
            top += 1
        if image.pixels[((image.height - 1) * image.width + x) * 4 + 3] > alpha_threshold:
            bottom += 1
    for y in range(image.height):
        if image.pixels[(y * image.width) * 4 + 3] > alpha_threshold:
            left += 1
        if image.pixels[(y * image.width + image.width - 1) * 4 + 3] > alpha_threshold:
            right += 1
    return {"top": top, "bottom": bottom, "left": left, "right": right}


def item_report(
    item: dict[str, Any],
    *,
    alpha_threshold: int,
    min_largest_component_ratio: float,
    review_hole_ratio: float,
    review_max_hole_ratio: float,
    severe_hole_ratio: float,
) -> dict[str, Any]:
    role = str(item.get("media_role") or "")
    local_path = item.get("local_path")
    issues: list[str] = []
    warnings: list[str] = []
    if role not in SPRITE_ROLES and not role.endswith("_sprite"):
        return {
            "asset_id": item.get("asset_id"),
            "asset_name": item.get("asset_name"),
            "media_role": role,
            "status": "skipped",
            "reason": "not_sprite_role",
        }
    if not isinstance(local_path, str) or not local_path:
        return {
            "asset_id": item.get("asset_id"),
            "asset_name": item.get("asset_name"),
            "media_role": role,
            "status": "failed",
            "issues": ["missing_local_path"],
            "warnings": warnings,
        }

    path = resolve_local_path(local_path)
    if not path.exists():
        return {
            "asset_id": item.get("asset_id"),
            "asset_name": item.get("asset_name"),
            "media_role": role,
            "file": str(path),
            "status": "failed",
            "issues": ["local_path_missing"],
            "warnings": warnings,
        }

    try:
        image = png_pipeline.read_png(path)
    except ValueError as exc:
        return {
            "asset_id": item.get("asset_id"),
            "asset_name": item.get("asset_name"),
            "media_role": role,
            "file": str(path),
            "status": "failed",
            "issues": [f"png_read_failed:{exc}"],
            "warnings": warnings,
        }

    declared_sha = item.get("sha256")
    actual_sha = sha256_file(path)
    if isinstance(declared_sha, str) and declared_sha and declared_sha != actual_sha:
        issues.append("sha256_mismatch")
    elif not declared_sha:
        warnings.append("sha256_missing")

    alpha_values = image.pixels[3::4]
    total_pixels = len(alpha_values)
    visible_pixels = sum(1 for alpha in alpha_values if alpha > alpha_threshold)
    transparent_pixels = total_pixels - visible_pixels
    bbox = png_pipeline.alpha_bbox(image, alpha_threshold=alpha_threshold)
    bbox_area = 0
    bbox_payload: dict[str, int] | None = None
    if bbox:
        x0, y0, x1, y1 = bbox
        bbox_area = (x1 - x0) * (y1 - y0)
        bbox_payload = {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}
    if visible_pixels <= 0:
        issues.append("sprite_has_no_visible_pixels")

    components = visible_components(image, alpha_threshold=alpha_threshold)
    largest_component_ratio = round(components[0] / visible_pixels, 4) if components and visible_pixels else 0.0
    detached_component_count = max(0, len(components) - 1)
    detached_visible_ratio = round(1 - largest_component_ratio, 4) if components else 0.0
    if detached_component_count >= 8 or largest_component_ratio < min_largest_component_ratio:
        warnings.append("sprite_fragmented_visible_components")

    holes = enclosed_transparent_components(image, bbox, alpha_threshold=alpha_threshold)
    hole_pixel_count = sum(holes)
    hole_area_ratio = round(hole_pixel_count / bbox_area, 4) if bbox_area else 0.0
    max_hole_area_ratio = round((holes[0] if holes else 0) / bbox_area, 4) if bbox_area else 0.0
    if hole_area_ratio >= severe_hole_ratio:
        warnings.append("large_interior_transparent_holes")
    elif hole_area_ratio >= review_hole_ratio or max_hole_area_ratio >= review_max_hole_ratio:
        warnings.append("interior_transparent_holes_need_review")

    edge_counts = edge_visible_counts(image, alpha_threshold=alpha_threshold)
    if any(int(edge_counts.get(edge, 0)) > 0 for edge in ("top", "left", "right")):
        warnings.append("subject_touches_canvas_edge")

    if role in {"tower_sprite", "defense_sprite", "objective_sprite", "unit_sprite"}:
        anchor = as_obj(item.get("anchor"))
        if anchor.get("preset") not in {"bottom_center", "center"}:
            warnings.append("sprite_anchor_unexpected")

    status = "passed"
    if issues:
        status = "failed"
    elif warnings:
        status = "needs_review"

    return {
        "asset_id": item.get("asset_id"),
        "asset_name": item.get("asset_name"),
        "asset_type": item.get("asset_type"),
        "media_role": role,
        "file": str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path),
        "status": status,
        "issues": issues,
        "warnings": warnings,
        "metrics": {
            "width": image.width,
            "height": image.height,
            "alpha_visible_ratio": round(visible_pixels / total_pixels, 4) if total_pixels else 0,
            "alpha_transparent_ratio": round(transparent_pixels / total_pixels, 4) if total_pixels else 0,
            "subject_bbox": bbox_payload,
            "subject_bbox_coverage": round(bbox_area / total_pixels, 4) if total_pixels else 0,
            "visible_component_count": len(components),
            "largest_visible_component_ratio": largest_component_ratio,
            "detached_visible_component_count": detached_component_count,
            "detached_visible_ratio": detached_visible_ratio,
            "interior_transparent_component_count": len(holes),
            "interior_transparent_hole_ratio": hole_area_ratio,
            "max_interior_transparent_hole_ratio": max_hole_area_ratio,
            "edge_visible_counts": edge_counts,
        },
    }


def audit_manifest(
    manifest: dict[str, Any],
    *,
    manifest_path: Path,
    alpha_threshold: int,
    min_largest_component_ratio: float,
    review_hole_ratio: float,
    review_max_hole_ratio: float,
    severe_hole_ratio: float,
) -> dict[str, Any]:
    items = [item for item in as_list(manifest.get("items")) if isinstance(item, dict)]
    reports = [
        item_report(
            item,
            alpha_threshold=alpha_threshold,
            min_largest_component_ratio=min_largest_component_ratio,
            review_hole_ratio=review_hole_ratio,
            review_max_hole_ratio=review_max_hole_ratio,
            severe_hole_ratio=severe_hole_ratio,
        )
        for item in items
    ]
    sprite_reports = [report for report in reports if report.get("status") != "skipped"]
    counts = Counter(str(report.get("status")) for report in sprite_reports)
    warning_counts: Counter[str] = Counter()
    issue_counts: Counter[str] = Counter()
    for report in sprite_reports:
        warning_counts.update(str(warning) for warning in as_list(report.get("warnings")))
        issue_counts.update(str(issue) for issue in as_list(report.get("issues")))
    status = "passed"
    if counts.get("failed", 0):
        status = "failed"
    elif counts.get("needs_review", 0):
        status = "needs_review"
    return {
        "report_version": REPORT_VERSION,
        "schema_version": manifest.get("schema_version"),
        "media_pack_id": manifest.get("media_pack_id"),
        "manifest_path": str(manifest_path.relative_to(ROOT) if manifest_path.is_relative_to(ROOT) else manifest_path),
        "status": status,
        "sprite_item_count": len(sprite_reports),
        "passed_count": counts.get("passed", 0),
        "needs_review_count": counts.get("needs_review", 0),
        "failed_count": counts.get("failed", 0),
        "warning_counts": dict(sorted(warning_counts.items())),
        "issue_counts": dict(sorted(issue_counts.items())),
        "items": sprite_reports,
        "thresholds": {
            "alpha_threshold": alpha_threshold,
            "min_largest_component_ratio": min_largest_component_ratio,
            "review_hole_ratio": review_hole_ratio,
            "review_max_hole_ratio": review_max_hole_ratio,
            "severe_hole_ratio": severe_hole_ratio,
        },
        "notes": [
            "This report is deterministic and offline.",
            "needs_review does not block the MVP; it orders assets for repair/regeneration.",
            "Large transparent holes may be intentional for fences/windows, so this report flags them for review instead of failing by default.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit sprite cutout geometry in a frontend media manifest.")
    parser.add_argument("manifest")
    parser.add_argument("--output")
    parser.add_argument("--alpha-threshold", type=int, default=8)
    parser.add_argument("--min-largest-component-ratio", type=float, default=0.94)
    parser.add_argument("--review-hole-ratio", type=float, default=0.015)
    parser.add_argument("--review-max-hole-ratio", type=float, default=0.006)
    parser.add_argument("--severe-hole-ratio", type=float, default=0.05)
    parser.add_argument("--fail-on-review", action="store_true")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = ROOT / manifest_path
    manifest = load_json(manifest_path)
    if not isinstance(manifest, dict):
        print("INVALID sprite cutout quality input")
        print("- manifest root must be object")
        return 1
    report = audit_manifest(
        manifest,
        manifest_path=manifest_path,
        alpha_threshold=max(0, args.alpha_threshold),
        min_largest_component_ratio=max(0.0, min(1.0, args.min_largest_component_ratio)),
        review_hole_ratio=max(0.0, args.review_hole_ratio),
        review_max_hole_ratio=max(0.0, args.review_max_hole_ratio),
        severe_hole_ratio=max(0.0, args.severe_hole_ratio),
    )
    summary = (
        f"{report['status'].upper()}: {report['manifest_path']} "
        f"sprites={report['sprite_item_count']} review={report['needs_review_count']} failed={report['failed_count']}"
    )
    if args.output:
        write_json(Path(args.output), report)
        print(summary)
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(summary, file=sys.stderr)
    if report["status"] == "failed":
        return 1
    if args.fail_on_review and report["status"] == "needs_review":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
