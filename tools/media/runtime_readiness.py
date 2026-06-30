#!/usr/bin/env python3
"""Deterministic runtime-readiness checks for published game media.

This module answers a narrower question than semantic vision review:
"Can the frontend load and place this media asset as game runtime material?"

It checks local published PNG files, /assets paths, hashes, anchors, atlas
frames, alpha coverage, subject bounds, and simple role-specific constraints.
It does not call providers and does not judge aesthetics.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from . import png_pipeline
except ImportError:  # pragma: no cover - direct script execution
    import png_pipeline  # type: ignore[no-redef]


REPORT_VERSION = "media_runtime_readiness_report.v0.1"
SPRITE_ROLES = {"icon", "tower_sprite", "unit_sprite", "npc_sprite", "monster_sprite", "subject_sprite", "cutout_source"}
PREVIEW_ROLES = {"ui_card", "effect_preview", "battle_preview"}


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_media_file(item: dict[str, Any], artifact_dir: Path) -> Path | None:
    local_path = item.get("local_path")
    if isinstance(local_path, str) and local_path:
        path = Path(local_path)
        return path if path.is_absolute() else artifact_dir / path

    rel_file = item.get("file")
    if isinstance(rel_file, str) and rel_file:
        path = Path(rel_file)
        return path if path.is_absolute() else artifact_dir / path

    url = item.get("url")
    if isinstance(url, str) and url.startswith("/assets/generated/"):
        return artifact_dir / "published" / Path(url).name
    return None


def alpha_edge_counts(image: png_pipeline.PngImage, *, alpha_threshold: int) -> dict[str, int]:
    top = bottom = left = right = 0
    for x in range(image.width):
        if image.pixels[(x * 4) + 3] > alpha_threshold:
            top += 1
        if image.pixels[((image.height - 1) * image.width + x) * 4 + 3] > alpha_threshold:
            bottom += 1
    for y in range(image.height):
        if image.pixels[(y * image.width) * 4 + 3] > alpha_threshold:
            left += 1
        if image.pixels[(y * image.width + image.width - 1) * 4 + 3] > alpha_threshold:
            right += 1
    return {"top": top, "bottom": bottom, "left": left, "right": right}


def inspect_png(path: Path, *, alpha_threshold: int) -> dict[str, Any]:
    image = png_pipeline.read_png(path)
    alpha_values = image.pixels[3::4]
    total = len(alpha_values)
    transparent = sum(1 for alpha in alpha_values if alpha <= alpha_threshold)
    visible = total - transparent
    bbox = png_pipeline.alpha_bbox(image, alpha_threshold=alpha_threshold)
    bbox_area = 0
    bbox_payload: dict[str, int] | None = None
    if bbox:
        x0, y0, x1, y1 = bbox
        bbox_area = (x1 - x0) * (y1 - y0)
        bbox_payload = {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}
    return {
        "width": image.width,
        "height": image.height,
        "alpha_transparent_ratio": round(transparent / total, 4) if total else 0,
        "alpha_visible_ratio": round(visible / total, 4) if total else 0,
        "subject_bbox": bbox_payload,
        "subject_bbox_coverage": round(bbox_area / total, 4) if total else 0,
        "edge_alpha_counts": alpha_edge_counts(image, alpha_threshold=alpha_threshold),
    }


def item_readiness(
    item: dict[str, Any],
    artifact_dir: Path,
    *,
    alpha_threshold: int,
    min_size: int,
    max_size: int,
    min_subject_coverage: float,
    max_subject_coverage: float,
) -> dict[str, Any]:
    role = str(item.get("media_role", "unknown"))
    issues: list[str] = []
    warnings: list[str] = []

    url = item.get("url")
    if not isinstance(url, str) or not url.startswith("/assets/generated/"):
        issues.append("missing_or_invalid_runtime_asset_url")

    file_path = resolve_media_file(item, artifact_dir)
    if file_path is None:
        issues.append("missing_local_published_file_reference")
        return {
            "stable_internal_id": item.get("stable_internal_id"),
            "media_role": role,
            "status": "failed",
            "issues": issues,
            "warnings": warnings,
        }
    if not file_path.exists():
        issues.append("published_file_missing")
        return {
            "stable_internal_id": item.get("stable_internal_id"),
            "media_role": role,
            "file": str(file_path),
            "status": "failed",
            "issues": issues,
            "warnings": warnings,
        }

    try:
        metrics = inspect_png(file_path, alpha_threshold=alpha_threshold)
    except ValueError as exc:
        return {
            "stable_internal_id": item.get("stable_internal_id"),
            "media_role": role,
            "file": str(file_path),
            "status": "failed",
            "issues": [*issues, f"png_read_failed:{exc}"],
            "warnings": warnings,
        }

    width = int(metrics["width"])
    height = int(metrics["height"])
    if width < min_size or height < min_size:
        issues.append("canvas_too_small_for_runtime")
    if width > max_size or height > max_size:
        issues.append("canvas_too_large_for_runtime")

    declared_width = item.get("width")
    declared_height = item.get("height")
    if declared_width is not None and int(declared_width) != width:
        warnings.append("declared_width_mismatch")
    if declared_height is not None and int(declared_height) != height:
        warnings.append("declared_height_mismatch")

    declared_sha = item.get("sha256")
    actual_sha = sha256_file(file_path)
    if isinstance(declared_sha, str) and declared_sha and declared_sha != actual_sha:
        issues.append("sha256_mismatch")
    elif not declared_sha:
        warnings.append("sha256_missing")

    if role in SPRITE_ROLES:
        transparent_ratio = float(metrics["alpha_transparent_ratio"])
        subject_coverage = float(metrics["subject_bbox_coverage"])
        if transparent_ratio < 0.15:
            issues.append("sprite_lacks_transparent_background")
        if subject_coverage < min_subject_coverage:
            issues.append("subject_too_small_after_cutout")
        if subject_coverage > max_subject_coverage:
            warnings.append("subject_too_tight_or_no_padding")
        edges = as_obj(metrics["edge_alpha_counts"])
        if any(int(edges.get(edge, 0)) > 0 for edge in ("top", "left", "right")):
            warnings.append("subject_touches_canvas_edge")
        if role == "tower_sprite":
            anchor = as_obj(item.get("anchor"))
            if anchor.get("preset") != "bottom_center":
                issues.append("tower_sprite_anchor_not_bottom_center")
            if item.get("atlas_frame") is None:
                issues.append("tower_sprite_missing_atlas_frame")
            if not item.get("texture_key"):
                issues.append("tower_sprite_missing_texture_key")
    elif role in PREVIEW_ROLES:
        if item.get("atlas_frame") is None:
            warnings.append("preview_missing_atlas_frame")
    else:
        warnings.append("unknown_media_role_runtime_policy")

    status = "passed"
    if issues:
        status = "failed"
    elif warnings:
        status = "needs_review"

    return {
        "stable_internal_id": item.get("stable_internal_id"),
        "media_role": role,
        "file": str(file_path),
        "status": status,
        "width": width,
        "height": height,
        "sha256": actual_sha,
        "metrics": metrics,
        "issues": issues,
        "warnings": warnings,
        "runtime_refs": {
            "url": url,
            "texture_key": item.get("texture_key"),
            "atlas_frame": item.get("atlas_frame"),
            "anchor": item.get("anchor"),
        },
    }


def assess_runtime_readiness(
    published_manifest: dict[str, Any],
    *,
    artifact_dir: Path,
    alpha_threshold: int = 8,
    min_size: int = 16,
    max_size: int = 1024,
    min_subject_coverage: float = 0.05,
    max_subject_coverage: float = 0.92,
) -> dict[str, Any]:
    items = [
        item
        for item in as_list(published_manifest.get("published_media"))
        if isinstance(item, dict)
    ]
    item_reports = [
        item_readiness(
            item,
            artifact_dir,
            alpha_threshold=alpha_threshold,
            min_size=min_size,
            max_size=max_size,
            min_subject_coverage=min_subject_coverage,
            max_subject_coverage=max_subject_coverage,
        )
        for item in items
    ]

    manifest_issues: list[str] = []
    if published_manifest.get("media_layer") != "published_media":
        manifest_issues.append("media_layer_not_published_media")
    if not items:
        manifest_issues.append("published_media_empty")

    failed_count = sum(1 for item in item_reports if item.get("status") == "failed")
    review_count = sum(1 for item in item_reports if item.get("status") == "needs_review")
    passed_count = sum(1 for item in item_reports if item.get("status") == "passed")
    status = "passed"
    if failed_count or manifest_issues:
        status = "failed"
    elif review_count:
        status = "needs_review"

    atlas = as_obj(published_manifest.get("atlas"))
    atlas_issues: list[str] = []
    atlas_warnings: list[str] = []
    if atlas:
        image_file = atlas.get("image_file")
        descriptor_file = atlas.get("descriptor_file")
        for key, value in (("image_file", image_file), ("descriptor_file", descriptor_file)):
            if not isinstance(value, str) or not value:
                atlas_issues.append(f"atlas_{key}_missing")
                continue
            path = Path(value)
            if not path.is_absolute():
                path = artifact_dir / path
            if not path.exists():
                atlas_issues.append(f"atlas_{key}_file_missing")
        if not atlas.get("image", "").startswith("/assets/generated/"):
            atlas_issues.append("atlas_image_runtime_url_invalid")
        if not atlas.get("descriptor", "").startswith("/assets/generated/"):
            atlas_issues.append("atlas_descriptor_runtime_url_invalid")
    else:
        atlas_warnings.append("atlas_manifest_missing")

    if atlas_issues:
        status = "failed"
    elif atlas_warnings and status == "passed":
        status = "needs_review"

    return {
        "report_version": REPORT_VERSION,
        "media_layer": published_manifest.get("media_layer"),
        "status": status,
        "passed_count": passed_count,
        "needs_review_count": review_count,
        "failed_count": failed_count,
        "manifest_issues": manifest_issues,
        "items_total": len(item_reports),
        "items": item_reports,
        "atlas": {
            "status": "failed" if atlas_issues else ("needs_review" if atlas_warnings else "passed"),
            "issues": atlas_issues,
            "warnings": atlas_warnings,
            "texture_key": atlas.get("texture_key"),
            "image": atlas.get("image"),
            "descriptor": atlas.get("descriptor"),
        },
        "thresholds": {
            "alpha_threshold": alpha_threshold,
            "min_size": min_size,
            "max_size": max_size,
            "min_subject_coverage": min_subject_coverage,
            "max_subject_coverage": max_subject_coverage,
        },
        "notes": [
            "This deterministic report checks runtime loadability and cutout geometry.",
            "It does not replace vision review for semantic consistency, OCR, watermark, or world fit.",
        ],
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("--output")
    args = parser.parse_args()
    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    report = assess_runtime_readiness(manifest, artifact_dir=manifest_path.parent)
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0 if report["status"] != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
