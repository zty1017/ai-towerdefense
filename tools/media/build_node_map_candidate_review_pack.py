#!/usr/bin/env python3
"""Build a review-only report for node-specific painted map candidates."""

from __future__ import annotations

import argparse
import json
import struct
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPORT_VERSION = "node_map_painted_candidate_review.v0.1"
DEFAULT_CANDIDATE_DIR = ROOT / "game_data/media/map_visual_reference/node_candidates"
DEFAULT_OUTPUT = ROOT / "examples/review_packs/node_map_painted_candidate_review.v0.1.json"


REVIEW_NOTES: dict[str, dict[str, Any]] = {
    "gray_lantern_station": {
        "status": "needs_regeneration",
        "blocking_findings": [
            "visible_arrow_symbols_on_path",
            "prebuilt_vertical_tower_structures",
            "route_direction_marks_baked_into_background",
        ],
        "strengths": [
            "readable_full-frame_tower_defense_composition",
            "world_style_is_close_to_lantern_frontier",
            "empty_foundations_are_visually_clear",
        ],
        "recommended_next_action": "regenerate_with_stronger_no_arrows_and_no_prebuilt_towers_constraints",
    },
    "lamp_wick_store": {
        "status": "needs_regeneration",
        "blocking_findings": [
            "visible_arrow_symbols_on_path",
            "modern_asphalt_roads_and_lane_markings",
            "too_many_baked_buildings_inside_play_area",
        ],
        "strengths": [
            "supply_depot_identity_is_clear",
            "roads_and_pad_areas_are_readable",
        ],
        "recommended_next_action": "regenerate_from_a_clean_control_sketch_with_no_road_markings",
    },
    "old_signal_tower": {
        "status": "near_promotable_after_cleanup",
        "blocking_findings": [
            "small_visible_arrow_symbol_on_path",
            "some_pad_markers_are_too_diagram_like",
        ],
        "strengths": [
            "node_objective_is_clear_and_world_appropriate",
            "terrain_and_paths_fit_a_tower_defense_battlefield",
            "empty_foundations_are_readable",
        ],
        "recommended_next_action": "attempt_inpaint_or_regenerate_one_cleanup_pass_before_runtime_promotion",
    },
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def png_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        with path.open("rb") as handle:
            header = handle.read(24)
    except FileNotFoundError:
        return None
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", header[16:24])


def build_candidate(sidecar_path: Path) -> dict[str, Any]:
    sidecar = load_json(sidecar_path)
    node_id = str(sidecar.get("node_id") or "")
    candidate_path = ROOT / str(sidecar.get("candidate_path") or "")
    notes = REVIEW_NOTES.get(
        node_id,
        {
            "status": "needs_manual_review",
            "blocking_findings": ["no_review_notes_available"],
            "strengths": [],
            "recommended_next_action": "inspect_candidate_before_any_runtime_promotion",
        },
    )
    dims = png_dimensions(candidate_path)
    file_status = "present_png" if dims else ("missing" if not candidate_path.exists() else "not_png")
    return {
        "node_id": node_id,
        "display_name": sidecar.get("display_name"),
        "candidate_path": rel(candidate_path),
        "sidecar_path": rel(sidecar_path),
        "battle_config": sidecar.get("battle_config"),
        "provider_profile": sidecar.get("provider_profile"),
        "model": sidecar.get("model"),
        "prompt_sha256": sidecar.get("prompt_sha256"),
        "generation_status": sidecar.get("generation_status"),
        "file_status": file_status,
        "dimensions": {"width": dims[0], "height": dims[1]} if dims else None,
        "image_size_bytes": sidecar.get("image_size_bytes"),
        "review_status": notes["status"],
        "blocking_findings": notes["blocking_findings"],
        "strengths": notes["strengths"],
        "recommended_next_action": notes["recommended_next_action"],
        "runtime_promotion": "blocked_until_explicit_review",
    }


def build_report(candidate_dir: Path) -> dict[str, Any]:
    sidecars = sorted(candidate_dir.glob("*.painted_candidate.png.candidate.json"))
    candidates = [build_candidate(path) for path in sidecars]
    status_counts = Counter(str(candidate.get("review_status")) for candidate in candidates)
    blocking_count = sum(1 for candidate in candidates if candidate.get("blocking_findings"))
    promotable_count = sum(
        1
        for candidate in candidates
        if candidate.get("review_status") in {"promoted", "runtime_ready"}
    )
    return {
        "schema_version": REPORT_VERSION,
        "report_id": "mvp_node_map_painted_candidate_review",
        "candidate_dir": rel(candidate_dir),
        "status": "review_only_not_runtime_ready" if promotable_count == 0 else "partially_promotable",
        "summary": {
            "candidate_count": len(candidates),
            "runtime_promotion_count": promotable_count,
            "blocking_candidate_count": blocking_count,
            "review_status_counts": dict(sorted(status_counts.items())),
        },
        "candidates": candidates,
        "policy": [
            "This report reviews provider-generated map candidates only.",
            "Candidates do not update MapRuntimePackage or player runtime visual layers.",
            "Runtime truth remains paths, build slots, objectives, spawn points, and explicitly published visual layers.",
            "Bad candidates are useful compiler evidence: they tune prompts, control sketches, and review gates.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build node map candidate review report.")
    parser.add_argument("--candidate-dir", default=str(DEFAULT_CANDIDATE_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    candidate_dir = Path(args.candidate_dir)
    if not candidate_dir.is_absolute():
        candidate_dir = ROOT / candidate_dir
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    report = build_report(candidate_dir)
    write_json(output, report)
    print(f"Wrote {output}")
    print(f"- status: {report['status']}")
    print(f"- candidates: {report['summary']['candidate_count']}")
    return 0 if report["summary"]["candidate_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
