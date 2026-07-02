#!/usr/bin/env python3
"""Build deterministic repair plans from sprite cutout quality reports."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PLAN_VERSION = "sprite_cutout_repair_plan.v0.1"


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


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def priority_for(item: dict[str, Any]) -> str:
    warnings = set(str(value) for value in as_list(item.get("warnings")))
    issues = set(str(value) for value in as_list(item.get("issues")))
    metrics = as_obj(item.get("metrics"))
    if issues:
        return "P0"
    if "large_interior_transparent_holes" in warnings:
        return "P1"
    if "sprite_fragmented_visible_components" in warnings:
        largest = float(metrics.get("largest_visible_component_ratio") or 1)
        return "P1" if largest < 0.96 else "P2"
    if warnings:
        return "P2"
    return "P3"


def action_for(item: dict[str, Any]) -> str:
    warnings = set(str(value) for value in as_list(item.get("warnings")))
    issues = set(str(value) for value in as_list(item.get("issues")))
    if issues:
        return "repair_manifest_or_regenerate_source"
    if "large_interior_transparent_holes" in warnings:
        return "regenerate_or_reprocess_cutout"
    if "interior_transparent_holes_need_review" in warnings:
        return "manual_review_then_reprocess_if_needed"
    if "sprite_fragmented_visible_components" in warnings:
        return "rerun_postprocess_component_cleanup"
    if "subject_touches_canvas_edge" in warnings:
        return "rerun_crop_pad_with_more_padding"
    return "manual_review"


def repair_steps_for(item: dict[str, Any]) -> list[str]:
    warnings = set(str(value) for value in as_list(item.get("warnings")))
    issues = set(str(value) for value in as_list(item.get("issues")))
    steps: list[str] = []
    if issues:
        steps.append("verify local_path, sha256, and manifest entry before any media regeneration")
    if "large_interior_transparent_holes" in warnings:
        steps.extend(
            [
                "inspect whether holes are intentional open geometry such as fence gaps or windows",
                "if not intentional, regenerate clean cutout source with solid object body and plain matte background",
                "rerun postprocess with conservative internal island removal disabled for this role",
                "rebuild multiframe atlas after the processed PNG changes",
            ]
        )
    if "interior_transparent_holes_need_review" in warnings:
        steps.extend(
            [
                "review subject interior against intended gameplay silhouette",
                "prefer reprocessing from original generated image before regenerating with a provider",
            ]
        )
    if "sprite_fragmented_visible_components" in warnings:
        steps.extend(
            [
                "rerun component cleanup and keep only intentional attached ornaments",
                "if detached pieces are part of baked effects, move the effect to visual_recipe instead of sprite pixels",
                "regenerate cutout prompt with single connected object and no surrounding particles",
            ]
        )
    if "subject_touches_canvas_edge" in warnings:
        steps.append("increase crop padding and rebuild processed PNG")
    if not steps:
        steps.append("manual review only; no deterministic repair is required")
    return list(dict.fromkeys(steps))


def prompt_constraints_for(item: dict[str, Any]) -> list[str]:
    warnings = set(str(value) for value in as_list(item.get("warnings")))
    constraints = [
        "single isolated game sprite",
        "plain pure white or transparent-friendly matte background",
        "no UI, no labels, no text, no watermark",
        "no enemies, no battlefield scenery, no surrounding characters",
    ]
    if "large_interior_transparent_holes" in warnings or "interior_transparent_holes_need_review" in warnings:
        constraints.extend(
            [
                "solid readable body silhouette",
                "avoid white gaps inside the object unless they are intentional windows or fence gaps",
                "keep glow and magical effects as separate effect layers rather than baked into the sprite",
            ]
        )
    if "sprite_fragmented_visible_components" in warnings:
        constraints.extend(
            [
                "one connected subject",
                "no detached floating particles",
                "no loose smoke or debris around the object",
            ]
        )
    return list(dict.fromkeys(constraints))


def acceptance_checks_for(item: dict[str, Any]) -> list[str]:
    return [
        "audit_sprite_cutout_quality status for this item is passed or manually accepted",
        "validate_frontend_mock_media_pack or validate_frontend_runtime_art_pack passes",
        "validate_media_atlas_manifest passes after atlas rebuild",
        "frontend battle visual contract still passes if runtime art changed",
    ]


def task_from_item(item: dict[str, Any], index: int) -> dict[str, Any]:
    metrics = as_obj(item.get("metrics"))
    asset_id = str(item.get("asset_id") or "unknown_asset")
    role = str(item.get("media_role") or "unknown_role")
    priority = priority_for(item)
    action = action_for(item)
    return {
        "task_id": f"sprite_repair_{index:03d}_{asset_id}_{role}",
        "priority": priority,
        "recommended_action": action,
        "asset_id": asset_id,
        "asset_name": item.get("asset_name"),
        "asset_type": item.get("asset_type"),
        "media_role": role,
        "source_status": item.get("status"),
        "source_file": item.get("file"),
        "warnings": as_list(item.get("warnings")),
        "issues": as_list(item.get("issues")),
        "metrics": {
            "visible_component_count": metrics.get("visible_component_count"),
            "largest_visible_component_ratio": metrics.get("largest_visible_component_ratio"),
            "interior_transparent_hole_ratio": metrics.get("interior_transparent_hole_ratio"),
            "max_interior_transparent_hole_ratio": metrics.get("max_interior_transparent_hole_ratio"),
        },
        "repair_steps": repair_steps_for(item),
        "regeneration_prompt_constraints": prompt_constraints_for(item),
        "acceptance_checks": acceptance_checks_for(item),
    }


def build_plan(report: dict[str, Any], *, source_report_path: Path) -> dict[str, Any]:
    review_items = [
        item
        for item in as_list(report.get("items"))
        if isinstance(item, dict) and item.get("status") in {"needs_review", "failed"}
    ]
    tasks = [task_from_item(item, index + 1) for index, item in enumerate(review_items)]
    priority_counts = Counter(str(task.get("priority")) for task in tasks)
    action_counts = Counter(str(task.get("recommended_action")) for task in tasks)
    status = "empty" if not tasks else "ready"
    if any(task.get("priority") == "P0" for task in tasks):
        status = "blocked_until_manifest_or_file_fix"
    return {
        "schema_version": PLAN_VERSION,
        "plan_id": f"{report.get('media_pack_id', 'media_pack')}_sprite_cutout_repair_plan_v0_1",
        "source_report": rel(source_report_path),
        "source_report_status": report.get("status"),
        "status": status,
        "task_count": len(tasks),
        "priority_counts": dict(sorted(priority_counts.items())),
        "action_counts": dict(sorted(action_counts.items())),
        "tasks": tasks,
        "notes": [
            "This plan is deterministic and offline; it does not call providers.",
            "P1 tasks should be fixed before using these sprites as final visual evidence.",
            "If gameplay is already functional, these tasks should not block fallback-ready MVP flow.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a sprite cutout repair plan from a quality report.")
    parser.add_argument("quality_report")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report_path = Path(args.quality_report)
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    report = load_json(report_path)
    if not isinstance(report, dict):
        print("quality report root must be object")
        return 1
    plan = build_plan(report, source_report_path=report_path)
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    write_json(output, plan)
    print(f"OK: wrote {output}")
    print(f"- status: {plan['status']}")
    print(f"- tasks: {plan['task_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
