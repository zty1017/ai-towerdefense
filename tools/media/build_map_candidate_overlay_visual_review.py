#!/usr/bin/env python3
"""Build a visual review report for raster map candidate overlays.

This report records the current human review of overlay PNG artifacts. It is
not a promotion report. Its purpose is to stop attractive map images from
entering runtime when their visual landmarks and MapRuntimePackage coordinates
still disagree.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPORT_VERSION = "map_candidate_overlay_visual_review.v0.1"
DEFAULT_OVERLAY_REVIEW = ROOT / "examples/review_packs/map_candidate_overlay_review.v0.1.json"
DEFAULT_OUTPUT = ROOT / "examples/review_packs/map_candidate_overlay_visual_review.v0.1.json"


VISUAL_REVIEW_NOTES: dict[str, dict[str, Any]] = {
    "gray_lantern_station": {
        "status": "needs_layout_reconciliation",
        "promotion_recommendation": "do_not_promote",
        "findings": [
            "runtime_path_partly_follows_painted_road_but_has_mechanical_right_angle_segments",
            "core_objective_marker_does_not_land_on_the_visible_station_core",
            "optional_objective_marker_lands_near_the_station_area_but_needs_repositioning",
            "build_slots_are_mostly_near_playable_terrain_but_need_spacing_review",
        ],
        "strengths": [
            "clean_full_frame_map_without_units_or_projectiles",
            "road_network_and_build_clearings_are_readable",
            "world_style_matches_lantern_frontier",
        ],
        "next_action": "adjust runtime package objective/path coordinates to the painted station layout or regenerate from a stricter topology prompt",
    },
    "lamp_wick_store": {
        "status": "needs_path_reprojection",
        "promotion_recommendation": "do_not_promote",
        "findings": [
            "painted_map_is_clean_but_runtime_paths_are_too_angular_for_the_visible_dirt_trails",
            "some_build_slot_markers_align_with_round_pads_but_right_side_cluster_needs_spacing_review",
            "left_side_objective_markers_do_not_clearly_attach_to_a_unique_core_inventory_landmark",
        ],
        "strengths": [
            "clean_background_without_arrows_units_or_projectiles",
            "large_empty_pads_are_readable_for_tower_defense",
            "supply_depot_style_is_clear",
        ],
        "next_action": "reproject runtime paths and objectives onto the visible dirt trails before considering promotion",
    },
    "old_signal_tower": {
        "status": "needs_layout_reconciliation",
        "promotion_recommendation": "do_not_promote",
        "findings": [
            "visual_primary_objective_is_centered_but_runtime_core_objective_marker_is_left_of_center",
            "runtime_paths_cross_the_central_tower_platform_instead_of_cleanly_following_painted_roads",
            "build_slots_clustered_top_right_while_visible_build_pads_are_distributed",
            "central_objective_size_may_reduce_combat_readability_without_layout_specific_runtime_package",
        ],
        "strengths": [
            "strong_node_identity_and_painted_quality",
            "clear roads_and_empty_pads",
            "no_visible_arrows_or_units",
        ],
        "next_action": "either move runtime objectives/routes around the central signal tower or regenerate a map with the objective located at the current runtime core coordinate",
    },
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def build_artifact_review(artifact: dict[str, Any]) -> dict[str, Any]:
    node_id = str(artifact.get("node_id") or "")
    notes = VISUAL_REVIEW_NOTES.get(
        node_id,
        {
            "status": "needs_manual_review",
            "promotion_recommendation": "do_not_promote",
            "findings": ["no_review_notes_available"],
            "strengths": [],
            "next_action": "inspect raster overlay before promotion",
        },
    )
    return {
        "node_id": node_id,
        "source_status": artifact.get("status"),
        "normalized_path": artifact.get("normalized_path"),
        "overlay_review_path": artifact.get("overlay_review_path"),
        "overlay_review_png_path": artifact.get("overlay_review_png_path"),
        "status": notes["status"],
        "promotion_recommendation": notes["promotion_recommendation"],
        "findings": notes["findings"],
        "strengths": notes["strengths"],
        "next_action": notes["next_action"],
    }


def build_report(overlay_review_path: Path) -> dict[str, Any]:
    overlay_review = load_json(overlay_review_path)
    reviews = [
        build_artifact_review(artifact)
        for artifact in as_list(overlay_review.get("artifacts"))
        if isinstance(artifact, dict)
    ]
    status_counts = Counter(str(review.get("status")) for review in reviews)
    recommendation_counts = Counter(str(review.get("promotion_recommendation")) for review in reviews)
    promotable_count = recommendation_counts.get("promote", 0)
    return {
        "schema_version": REPORT_VERSION,
        "report_id": "mvp_map_candidate_overlay_visual_review",
        "overlay_review_path": rel(overlay_review_path),
        "status": "needs_layout_reconciliation" if promotable_count == 0 else "partially_promotable",
        "summary": {
            "candidate_count": len(reviews),
            "promotable_count": promotable_count,
            "blocked_from_promotion_count": len(reviews) - promotable_count,
            "status_counts": dict(sorted(status_counts.items())),
            "promotion_recommendation_counts": dict(sorted(recommendation_counts.items())),
        },
        "reviews": reviews,
        "policy": [
            "This is a visual review report, not a promotion report.",
            "All candidates remain review-only until a later promotion report updates published visual layers.",
            "Beautiful map art is insufficient when runtime paths, tower slots, objectives, or spawn points do not align with visible landmarks.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build map candidate overlay visual review report.")
    parser.add_argument("--overlay-review", default=str(DEFAULT_OVERLAY_REVIEW))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    overlay_review = Path(args.overlay_review)
    if not overlay_review.is_absolute():
        overlay_review = ROOT / overlay_review
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    report = build_report(overlay_review)
    write_json(output, report)
    print(f"Wrote {output}")
    print(f"- status: {report['status']}")
    print(f"- promotable: {report['summary']['promotable_count']}")
    return 0 if report["summary"]["candidate_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
