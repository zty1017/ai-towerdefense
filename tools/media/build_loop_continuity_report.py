#!/usr/bin/env python3
"""Build LoopContinuityReport v0.1 from a MediaAtlasManifest.

This is a deterministic media gate for animation frame sequences. It does not
judge visual taste and does not call providers; it only checks whether existing
frames look mechanically plausible as looping game sprites.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MEDIA_DIR = Path(__file__).resolve().parent
if str(MEDIA_DIR) not in sys.path:
    sys.path.insert(0, str(MEDIA_DIR))

from png_pipeline import PngImage, read_png  # noqa: E402


REPORT_VERSION = "loop_continuity_report.v0.1"
DEFAULT_CREATED_AT = "2026-07-03T00:00:00+08:00"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def resolve_local_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def alpha_bbox(image: PngImage, *, alpha_threshold: int) -> dict[str, int] | None:
    min_x = image.width
    min_y = image.height
    max_x = -1
    max_y = -1
    for y in range(image.height):
        row = y * image.width
        for x in range(image.width):
            if image.pixels[(row + x) * 4 + 3] <= alpha_threshold:
                continue
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
    if max_x < 0:
        return None
    return {"x": min_x, "y": min_y, "w": max_x - min_x + 1, "h": max_y - min_y + 1}


def alpha_coverage(image: PngImage, *, alpha_threshold: int) -> float:
    visible = 0
    for index in range(3, len(image.pixels), 4):
        if image.pixels[index] > alpha_threshold:
            visible += 1
    return visible / max(image.width * image.height, 1)


def bbox_delta_ratio(
    first: dict[str, int] | None,
    last: dict[str, int] | None,
    *,
    canvas_width: int,
    canvas_height: int,
) -> float:
    if first is None or last is None:
        return 1.0
    denom = max(canvas_width, canvas_height, 1)
    return max(
        abs(first["x"] - last["x"]),
        abs(first["y"] - last["y"]),
        abs(first["w"] - last["w"]),
        abs(first["h"] - last["h"]),
    ) / denom


def anchor_delta(first: dict[str, Any], last: dict[str, Any]) -> float:
    fx = float(first.get("x", 0.5))
    fy = float(first.get("y", 0.5))
    lx = float(last.get("x", 0.5))
    ly = float(last.get("y", 0.5))
    return abs(fx - lx) + abs(fy - ly)


def mean_rgba_delta(first: PngImage, last: PngImage) -> float:
    if first.width != last.width or first.height != last.height:
        return 1.0
    total = first.width * first.height * 4
    if total <= 0:
        return 1.0
    diff = 0
    for index, value in enumerate(first.pixels):
        diff += abs(value - last.pixels[index])
    return diff / (total * 255)


def animation_report(
    item: dict[str, Any],
    *,
    atlas_ref: str,
    alpha_threshold: int,
    max_bbox_delta_ratio: float,
    max_anchor_delta: float,
    max_alpha_coverage_delta: float,
    max_mean_rgba_delta: float,
) -> dict[str, Any]:
    frames = item.get("frames") if isinstance(item.get("frames"), list) else []
    playback = item.get("playback") if isinstance(item.get("playback"), dict) else {}
    frame_source_kind = str(item.get("frame_source_kind") or "unknown")
    base = {
        "animation_id": item.get("animation_id"),
        "asset_id": item.get("asset_id"),
        "asset_name": item.get("asset_name"),
        "asset_type": item.get("asset_type"),
        "media_role": item.get("media_role"),
        "frame_source_kind": frame_source_kind,
        "atlas_ref": f"{atlas_ref}#{item.get('animation_id')}",
        "frame_count": len(frames),
        "playback": {
            "state": playback.get("state"),
            "fps": playback.get("fps"),
            "loop": playback.get("loop"),
        },
    }
    if len(frames) <= 1 or playback.get("loop") is not True:
        return {
            **base,
            "status": "skipped_static",
            "issues": [],
            "warnings": [],
            "metrics": {"reason": "not_looping_animation"},
        }

    issues: list[str] = []
    warnings: list[str] = []
    first_frame = frames[0] if isinstance(frames[0], dict) else {}
    last_frame = frames[-1] if isinstance(frames[-1], dict) else {}
    first_path = resolve_local_path(str(first_frame.get("local_path") or ""))
    last_path = resolve_local_path(str(last_frame.get("local_path") or ""))
    if not first_path.exists():
        issues.append("missing_first_frame")
    if not last_path.exists():
        issues.append("missing_last_frame")
    if issues:
        return {
            **base,
            "status": "failed",
            "issues": issues,
            "warnings": warnings,
            "metrics": {
                "first_frame": rel(first_path),
                "last_frame": rel(last_path),
            },
        }

    first_image = read_png(first_path)
    last_image = read_png(last_path)
    first_bbox = alpha_bbox(first_image, alpha_threshold=alpha_threshold)
    last_bbox = alpha_bbox(last_image, alpha_threshold=alpha_threshold)
    first_coverage = alpha_coverage(first_image, alpha_threshold=alpha_threshold)
    last_coverage = alpha_coverage(last_image, alpha_threshold=alpha_threshold)
    bbox_delta = bbox_delta_ratio(
        first_bbox,
        last_bbox,
        canvas_width=max(first_image.width, last_image.width),
        canvas_height=max(first_image.height, last_image.height),
    )
    anchor = anchor_delta(
        first_frame.get("anchor") if isinstance(first_frame.get("anchor"), dict) else {},
        last_frame.get("anchor") if isinstance(last_frame.get("anchor"), dict) else {},
    )
    coverage_delta = abs(first_coverage - last_coverage)
    rgba_delta = mean_rgba_delta(first_image, last_image)

    if first_image.width != last_image.width or first_image.height != last_image.height:
        issues.append("frame_canvas_size_changed")
    if first_bbox is None or last_bbox is None:
        issues.append("transparent_endpoint_frame")
    if bbox_delta > max_bbox_delta_ratio:
        issues.append("endpoint_bbox_delta_too_large")
    if anchor > max_anchor_delta:
        issues.append("endpoint_anchor_delta_too_large")
    if coverage_delta > max_alpha_coverage_delta:
        issues.append("endpoint_alpha_coverage_delta_too_large")
    if rgba_delta > max_mean_rgba_delta:
        warnings.append("endpoint_pixel_delta_noticeable")
    if first_frame.get("sha256") != last_frame.get("sha256"):
        warnings.append("endpoint_frame_sha_differs")
    if frame_source_kind == "deterministic_frame_sequence":
        warnings.append("deterministic_placeholder_not_real_video_keyframes")

    status = "failed" if issues else "passed_with_warnings" if warnings else "passed"
    return {
        **base,
        "status": status,
        "issues": issues,
        "warnings": warnings,
        "metrics": {
            "first_frame": rel(first_path),
            "last_frame": rel(last_path),
            "canvas": {
                "first_width": first_image.width,
                "first_height": first_image.height,
                "last_width": last_image.width,
                "last_height": last_image.height,
            },
            "first_alpha_bbox": first_bbox,
            "last_alpha_bbox": last_bbox,
            "bbox_delta_ratio": round(bbox_delta, 6),
            "anchor_delta": round(anchor, 6),
            "first_alpha_coverage": round(first_coverage, 6),
            "last_alpha_coverage": round(last_coverage, 6),
            "alpha_coverage_delta": round(coverage_delta, 6),
            "mean_rgba_delta": round(rgba_delta, 6),
        },
    }


def build_report(
    atlas: dict[str, Any],
    *,
    atlas_path: Path,
    report_id: str,
    created_at: str,
    alpha_threshold: int,
    max_bbox_delta_ratio: float,
    max_anchor_delta: float,
    max_alpha_coverage_delta: float,
    max_mean_rgba_delta: float,
) -> dict[str, Any]:
    atlas_ref = rel(atlas_path)
    items = [
        animation_report(
            item,
            atlas_ref=atlas_ref,
            alpha_threshold=alpha_threshold,
            max_bbox_delta_ratio=max_bbox_delta_ratio,
            max_anchor_delta=max_anchor_delta,
            max_alpha_coverage_delta=max_alpha_coverage_delta,
            max_mean_rgba_delta=max_mean_rgba_delta,
        )
        for item in atlas.get("items") or []
        if isinstance(item, dict)
    ]
    counts = Counter(str(item.get("status") or "unknown") for item in items)
    source_counts = Counter(str(item.get("frame_source_kind") or "unknown") for item in items)
    failed = counts.get("failed", 0)
    warnings = counts.get("passed_with_warnings", 0)
    status = "failed" if failed else "passed_with_warnings" if warnings else "passed"
    return {
        "report_version": REPORT_VERSION,
        "report_id": report_id,
        "created_at": created_at,
        "atlas_ref": atlas_ref,
        "source_atlas_id": atlas.get("atlas_id"),
        "status": status,
        "summary": {
            "animation_count": len(items),
            "checked_count": len(items) - counts.get("skipped_static", 0),
            "passed_count": counts.get("passed", 0),
            "passed_with_warnings_count": warnings,
            "failed_count": failed,
            "skipped_static_count": counts.get("skipped_static", 0),
            "frame_source_counts": dict(sorted(source_counts.items())),
        },
        "thresholds": {
            "alpha_threshold": alpha_threshold,
            "max_bbox_delta_ratio": max_bbox_delta_ratio,
            "max_anchor_delta": max_anchor_delta,
            "max_alpha_coverage_delta": max_alpha_coverage_delta,
            "max_mean_rgba_delta": max_mean_rgba_delta,
        },
        "items": items,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--atlas", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report-id", default="frontend_runtime_loop_continuity_report_v0_1")
    parser.add_argument("--created-at", default=DEFAULT_CREATED_AT)
    parser.add_argument("--alpha-threshold", type=int, default=8)
    parser.add_argument("--max-bbox-delta-ratio", type=float, default=0.08)
    parser.add_argument("--max-anchor-delta", type=float, default=0.03)
    parser.add_argument("--max-alpha-coverage-delta", type=float, default=0.08)
    parser.add_argument("--max-mean-rgba-delta", type=float, default=0.2)
    args = parser.parse_args()

    atlas_path = Path(args.atlas)
    if not atlas_path.is_absolute():
        atlas_path = ROOT / atlas_path
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = ROOT / output_path
    atlas = load_json(atlas_path)
    if not isinstance(atlas, dict):
        raise SystemExit("atlas root must be an object")
    report = build_report(
        atlas,
        atlas_path=atlas_path,
        report_id=args.report_id,
        created_at=args.created_at,
        alpha_threshold=args.alpha_threshold,
        max_bbox_delta_ratio=args.max_bbox_delta_ratio,
        max_anchor_delta=args.max_anchor_delta,
        max_alpha_coverage_delta=args.max_alpha_coverage_delta,
        max_mean_rgba_delta=args.max_mean_rgba_delta,
    )
    write_json(output_path, report)
    print(f"OK: wrote {output_path}")
    print(f"- status: {report['status']}")
    print(f"- checked: {report['summary']['checked_count']}")
    print(f"- warnings: {report['summary']['passed_with_warnings_count']}")
    print(f"- failed: {report['summary']['failed_count']}")
    return 0 if report["status"] != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
