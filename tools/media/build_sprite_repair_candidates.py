#!/usr/bin/env python3
"""Generate review-only sprite repair candidate PNGs from repair plans."""

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


MANIFEST_VERSION = "sprite_repair_candidate_manifest.v0.1"
DEFAULT_CREATED_AT = "2026-07-02T00:00:00+08:00"


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


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_path(task: dict[str, Any]) -> Path:
    raw = str(task.get("source_file") or "")
    if not raw:
        raise ValueError(f"task {task.get('task_id')} missing source_file")
    path = Path(raw)
    return path if path.is_absolute() else ROOT / path


def pixel_index(width: int, x: int, y: int) -> int:
    return (y * width + x) * 4


def enclosed_hole_components(
    image: png_pipeline.PngImage,
    *,
    alpha_threshold: int,
    min_pixels: int,
) -> list[list[int]]:
    bbox = png_pipeline.alpha_bbox(image, alpha_threshold=alpha_threshold)
    if bbox is None:
        return []
    x0, y0, x1, y1 = bbox
    bbox_w = x1 - x0
    bbox_h = y1 - y0
    total = bbox_w * bbox_h
    visited = bytearray(total)
    holes: list[list[int]] = []

    def local_to_image_pos(local_pos: int) -> int:
        local_x = local_pos % bbox_w
        local_y = local_pos // bbox_w
        return (y0 + local_y) * image.width + (x0 + local_x)

    def transparent(local_pos: int) -> bool:
        return image.pixels[local_to_image_pos(local_pos) * 4 + 3] <= alpha_threshold

    for start in range(total):
        if visited[start] or not transparent(start):
            continue
        visited[start] = 1
        stack = [start]
        component: list[int] = []
        touches_bbox_edge = False
        while stack:
            pos = stack.pop()
            component.append(local_to_image_pos(pos))
            x = pos % bbox_w
            y = pos // bbox_w
            if x == 0 or y == 0 or x + 1 == bbox_w or y + 1 == bbox_h:
                touches_bbox_edge = True
            neighbors = []
            if x > 0:
                neighbors.append(pos - 1)
            if x + 1 < bbox_w:
                neighbors.append(pos + 1)
            if y > 0:
                neighbors.append(pos - bbox_w)
            if y + 1 < bbox_h:
                neighbors.append(pos + bbox_w)
            for nxt in neighbors:
                if not visited[nxt] and transparent(nxt):
                    visited[nxt] = 1
                    stack.append(nxt)
        if not touches_bbox_edge and len(component) >= min_pixels:
            holes.append(component)
    return sorted(holes, key=len, reverse=True)


def boundary_rgb_for_component(
    image: png_pipeline.PngImage,
    component: list[int],
    *,
    alpha_threshold: int,
) -> tuple[int, int, int]:
    component_set = set(component)
    samples: list[tuple[int, int, int]] = []
    for pos in component:
        x = pos % image.width
        y = pos // image.width
        neighbors = []
        if x > 0:
            neighbors.append(pos - 1)
        if x + 1 < image.width:
            neighbors.append(pos + 1)
        if y > 0:
            neighbors.append(pos - image.width)
        if y + 1 < image.height:
            neighbors.append(pos + image.width)
        for neighbor in neighbors:
            if neighbor in component_set:
                continue
            idx = neighbor * 4
            if image.pixels[idx + 3] > alpha_threshold:
                samples.append((image.pixels[idx], image.pixels[idx + 1], image.pixels[idx + 2]))
    if not samples:
        return (32, 32, 32)
    count = len(samples)
    return (
        sum(sample[0] for sample in samples) // count,
        sum(sample[1] for sample in samples) // count,
        sum(sample[2] for sample in samples) // count,
    )


def fill_interior_holes(
    image: png_pipeline.PngImage,
    *,
    alpha_threshold: int,
    min_pixels: int,
) -> png_pipeline.PngImage:
    out = png_pipeline.PngImage(image.width, image.height, bytearray(image.pixels))
    for component in enclosed_hole_components(image, alpha_threshold=alpha_threshold, min_pixels=min_pixels):
        r, g, b = boundary_rgb_for_component(out, component, alpha_threshold=alpha_threshold)
        for pos in component:
            idx = pos * 4
            out.pixels[idx] = r
            out.pixels[idx + 1] = g
            out.pixels[idx + 2] = b
            out.pixels[idx + 3] = 255
    return png_pipeline.clear_transparent_rgb(out, alpha_threshold=alpha_threshold)


def strategy_for_task(task: dict[str, Any]) -> str:
    action = str(task.get("recommended_action") or "")
    warnings = set(str(warning) for warning in as_list(task.get("warnings")))
    if action == "rerun_postprocess_component_cleanup" or "sprite_fragmented_visible_components" in warnings:
        return "keep_largest_component"
    if (
        action in {"regenerate_or_reprocess_cutout", "manual_review_then_reprocess_if_needed"}
        or "large_interior_transparent_holes" in warnings
        or "interior_transparent_holes_need_review" in warnings
    ):
        return "fill_interior_holes"
    if "subject_touches_canvas_edge" in warnings:
        return "normalize_canvas_padding"
    return "copy_review_candidate"


def apply_strategy(
    image: png_pipeline.PngImage,
    *,
    strategy: str,
    role: str,
    alpha_threshold: int,
    min_hole_pixels: int,
) -> png_pipeline.PngImage:
    if strategy == "keep_largest_component":
        repaired = png_pipeline.keep_largest_alpha_component(image, alpha_threshold=alpha_threshold)
        return png_pipeline.clear_transparent_rgb(repaired, alpha_threshold=alpha_threshold)
    if strategy == "fill_interior_holes":
        return fill_interior_holes(image, alpha_threshold=alpha_threshold, min_pixels=min_hole_pixels)
    if strategy == "normalize_canvas_padding":
        align = "bottom_center" if role.endswith("_sprite") else "center"
        repaired = png_pipeline.crop_and_pad(image, padding=48, alpha_threshold=alpha_threshold)
        repaired = png_pipeline.normalize_canvas(repaired, square=True, min_size=max(image.width, image.height), align=align)
        return png_pipeline.clear_transparent_rgb(repaired, alpha_threshold=alpha_threshold)
    return png_pipeline.PngImage(image.width, image.height, bytearray(image.pixels))


def candidate_filename(task: dict[str, Any], strategy: str) -> str:
    asset_id = str(task.get("asset_id") or "asset").replace("/", "_")
    role = str(task.get("media_role") or "role").replace("/", "_")
    return f"{asset_id}__{role}__{strategy}.png"


def anchor_for_role(role: str) -> dict[str, float | str]:
    if role.endswith("_sprite") or role in {"tower_sprite", "unit_sprite", "defense_sprite", "objective_sprite"}:
        return {"preset": "bottom_center", "x": 0.5, "y": 1.0}
    return {"preset": "center", "x": 0.5, "y": 0.5}


def build_candidates(
    plan: dict[str, Any],
    *,
    plan_path: Path,
    output_dir: Path,
    pack_id: str,
    alpha_threshold: int,
    min_hole_pixels: int,
    include_priorities: set[str],
    created_at: str,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    strategy_counts: Counter[str] = Counter()
    priority_counts: Counter[str] = Counter()
    for task in as_list(plan.get("tasks")):
        if not isinstance(task, dict):
            continue
        priority = str(task.get("priority") or "")
        if include_priorities and priority not in include_priorities:
            continue
        src = source_path(task)
        if not src.exists():
            raise FileNotFoundError(f"missing source sprite for {task.get('task_id')}: {src}")
        role = str(task.get("media_role") or "")
        strategy = strategy_for_task(task)
        image = png_pipeline.read_png(src)
        candidate = apply_strategy(
            image,
            strategy=strategy,
            role=role,
            alpha_threshold=alpha_threshold,
            min_hole_pixels=min_hole_pixels,
        )
        output_path = output_dir / candidate_filename(task, strategy)
        png_pipeline.write_png(output_path, candidate)
        strategy_counts[strategy] += 1
        priority_counts[priority] += 1
        items.append(
            {
                "candidate_id": f"{task.get('task_id')}.{strategy}",
                "source_task_id": task.get("task_id"),
                "source_repair_plan": rel(plan_path),
                "asset_id": task.get("asset_id"),
                "asset_name": task.get("asset_name"),
                "asset_type": task.get("asset_type"),
                "media_role": role,
                "priority": priority,
                "source_file": rel(src),
                "local_path": rel(output_path),
                "width": candidate.width,
                "height": candidate.height,
                "sha256": sha256_file(output_path),
                "anchor": anchor_for_role(role),
                "strategy": strategy,
                "recommended_action": task.get("recommended_action"),
                "source_warnings": as_list(task.get("warnings")),
                "source_metrics": task.get("metrics"),
                "review_policy": "review_only_not_runtime",
            }
        )
    return {
        "schema_version": MANIFEST_VERSION,
        "candidate_pack_id": pack_id,
        "created_at": created_at,
        "source_repair_plan": rel(plan_path),
        "source_repair_plan_status": plan.get("status"),
        "media_layer": "review_candidate_media",
        "promotion_policy": "Candidates must pass quality audit and manual/vision review before replacing processed runtime media.",
        "items": items,
        "summary": {
            "candidate_count": len(items),
            "asset_count": len({item.get("asset_id") for item in items}),
            "priority_counts": dict(sorted(priority_counts.items())),
            "strategy_counts": dict(sorted(strategy_counts.items())),
        },
        "notes": [
            "This manifest is review-only. It does not alter frontend media manifests or runtime atlases.",
            "Regenerated candidates should be compared visually before promotion.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build review-only sprite repair candidates from a repair plan.")
    parser.add_argument("repair_plan")
    parser.add_argument("--output-manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--candidate-pack-id", required=True)
    parser.add_argument("--priority", action="append", default=[], help="Priority to include. Repeatable. Defaults to all.")
    parser.add_argument("--alpha-threshold", type=int, default=8)
    parser.add_argument("--min-hole-pixels", type=int, default=48)
    parser.add_argument("--created-at", default=DEFAULT_CREATED_AT)
    args = parser.parse_args()

    plan_path = Path(args.repair_plan)
    if not plan_path.is_absolute():
        plan_path = ROOT / plan_path
    plan = load_json(plan_path)
    if not isinstance(plan, dict):
        print("repair plan root must be object")
        return 1
    output_manifest = Path(args.output_manifest)
    if not output_manifest.is_absolute():
        output_manifest = ROOT / output_manifest
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    manifest = build_candidates(
        plan,
        plan_path=plan_path,
        output_dir=output_dir,
        pack_id=args.candidate_pack_id,
        alpha_threshold=max(0, args.alpha_threshold),
        min_hole_pixels=max(1, args.min_hole_pixels),
        include_priorities=set(str(priority) for priority in args.priority),
        created_at=args.created_at,
    )
    write_json(output_manifest, manifest)
    print(f"OK: wrote {output_manifest}")
    print(f"- candidates: {manifest['summary']['candidate_count']}")
    print(f"- strategies: {manifest['summary']['strategy_counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
