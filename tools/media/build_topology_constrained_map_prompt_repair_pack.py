#!/usr/bin/env python3
"""Build a repaired topology-constrained map prompt pack.

The repair pack turns visual-review failures into stricter provider prompts.
It is deterministic and review-only: it does not call providers and does not
modify runtime packages.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_PACK = ROOT / "examples/review_packs/topology_constrained_map_prompt_pack.v0.1.json"
DEFAULT_VISUAL_REVIEW = ROOT / "examples/review_packs/topology_constrained_map_overlay_visual_review.v0.1.json"
DEFAULT_OUTPUT = ROOT / "examples/review_packs/topology_constrained_map_prompt_pack.v0.2.json"


OLD_SIGNAL_REPAIR_APPENDIX = (
    " Repair pass v2: reduce the signal tower landmark to a small or medium ruined relay landmark, "
    "never a dominant central monument, occupying less than 15 percent of image height. "
    "Place the protected objective landmark on the left lower-mid ridge as a compact broken relay base or bunker, "
    "with routes curving around it instead of crossing through or under it. "
    "Keep the central combat field open. Remove all people, silhouettes, bodies, camp props that read as characters, "
    "vehicles, weapons, flags, UI-like signs, and tiny story props. "
    "Use only terrain, snow, rocks, fences, broken antenna debris as scenery, dirt/snow paths, and flat empty build pads."
)

OLD_SIGNAL_EXTRA_NEGATIVE = [
    "no_visible_people_or_silhouettes",
    "no_tiny_character_like_props",
    "no_large_central_signal_tower",
    "no_vehicle_or_weapon_props",
    "no_route_crossing_under_objective_landmark",
    "no_busy_story_debris_in_combat_space",
]


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


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def build_repair_pack(source_pack_path: Path, visual_review_path: Path) -> dict[str, Any]:
    source = load_json(source_pack_path)
    visual_review = load_json(visual_review_path)
    pack = copy.deepcopy(source)
    pack["schema_version"] = "topology_constrained_map_prompt_pack.v0.2"
    pack["pack_id"] = "mvp_topology_constrained_map_prompt_pack_v2"
    pack["repair_source"] = {
        "source_prompt_pack_path": rel(source_pack_path),
        "visual_review_path": rel(visual_review_path),
        "visual_review_status": visual_review.get("status"),
        "visual_review_summary": visual_review.get("summary"),
    }
    pack["policy"] = list(as_list(pack.get("policy"))) + [
        "v0.2 prompt repairs are derived from visual review failures and remain review-only.",
        "Generated images from v0.2 must re-enter candidate, alignment, overlay, and visual review gates.",
    ]
    for prompt in as_list(pack.get("prompts")):
        if not isinstance(prompt, dict) or prompt.get("node_id") != "old_signal_tower":
            continue
        prompt["status"] = "prompt_ready_repair_v2"
        prompt["repair_version"] = "v2_reduce_tower_and_remove_figures"
        prompt["repair_source_findings"] = [
            finding
            for review in as_list(visual_review.get("reviews"))
            if isinstance(review, dict) and review.get("node_id") == "old_signal_tower"
            for finding in as_list(review.get("findings"))
        ]
        prompt["prompt_brief"] = str(prompt.get("prompt_brief") or "") + OLD_SIGNAL_REPAIR_APPENDIX
        negatives = list(as_list(prompt.get("negative_constraints")))
        for item in OLD_SIGNAL_EXTRA_NEGATIVE:
            if item not in negatives:
                negatives.append(item)
        prompt["negative_constraints"] = negatives
        prompt["required_review_gates"] = list(as_list(prompt.get("required_review_gates"))) + [
            "no_tiny_people_or_character_like_marks",
            "objective_landmark_is_compact_and_left_lower_mid",
            "routes_do_not_cross_under_objective_landmark",
        ]
    pack["summary"] = {
        "prompt_count": len(as_list(pack.get("prompts"))),
        "repair_prompt_count": sum(
            1
            for prompt in as_list(pack.get("prompts"))
            if isinstance(prompt, dict) and prompt.get("repair_version")
        ),
        "source_pack": rel(source_pack_path),
    }
    return pack


def main() -> int:
    parser = argparse.ArgumentParser(description="Build repaired topology-constrained prompt pack.")
    parser.add_argument("--source-pack", default=str(DEFAULT_SOURCE_PACK))
    parser.add_argument("--visual-review", default=str(DEFAULT_VISUAL_REVIEW))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    source_pack = Path(args.source_pack)
    if not source_pack.is_absolute():
        source_pack = ROOT / source_pack
    visual_review = Path(args.visual_review)
    if not visual_review.is_absolute():
        visual_review = ROOT / visual_review
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output

    pack = build_repair_pack(source_pack, visual_review)
    write_json(output, pack)
    print(f"Wrote {output}")
    print(f"- schema_version: {pack['schema_version']}")
    print(f"- repair prompts: {pack['summary']['repair_prompt_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
