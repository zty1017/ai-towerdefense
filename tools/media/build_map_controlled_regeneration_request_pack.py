#!/usr/bin/env python3
"""Build reference-image request briefs for controlled map regeneration.

This pack is the handoff layer between deterministic MapRuntimePackage topology
and image generation. It does not call providers and does not publish visual
layers. Each request points to a clean topology control sketch PNG that can be
used by a reference-image-capable provider, or by a human paintover workflow.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPORT_VERSION = "map_controlled_regeneration_request_pack.v0.1"
DEFAULT_CONTROL_SKETCH_PACK = ROOT / "examples/review_packs/map_topology_control_sketch_pack.v0.1.json"
DEFAULT_PROMPT_PACK_V2 = ROOT / "examples/review_packs/topology_constrained_map_prompt_pack.v0.2.json"
DEFAULT_PROMPT_PACK_V1 = ROOT / "examples/review_packs/topology_constrained_map_prompt_pack.v0.1.json"
DEFAULT_OUTPUT = ROOT / "examples/review_packs/map_controlled_regeneration_request_pack.v0.1.json"
DEFAULT_PROMPT_DIR = ROOT / "examples/review_packs/map_controlled_regeneration_requests"


UNIVERSAL_NEGATIVE_CONSTRAINTS = [
    "no UI, frame, panel, card, menu, icon bar, watermark, logo, or text",
    "no arrows, chevrons, direction marks, labels, numbers, or grid lines",
    "no enemies, NPCs, human figures, monsters, animals, projectiles, explosions, or combat effects",
    "no deployed towers, turrets, watchtowers, castles, large central monument towers, or raised build structures",
    "no asphalt highways, lane markings, sci-fi HUD overlays, or technical diagram style",
]

REQUIRED_REVIEW_GATES = [
    "candidate_review",
    "alignment_review",
    "overlay_review",
    "overlay_visual_review",
    "explicit_promotion_report",
]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def resolve_repo_path(value: Any) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def default_prompt_pack() -> Path:
    return DEFAULT_PROMPT_PACK_V2 if DEFAULT_PROMPT_PACK_V2.exists() else DEFAULT_PROMPT_PACK_V1


def prompt_index(prompt_pack: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for prompt in as_list(prompt_pack.get("prompts")):
        if isinstance(prompt, dict) and prompt.get("node_id") not in result:
            result[str(prompt["node_id"])] = prompt
    return result


def compact_runtime_topology(sketch: dict[str, Any], prompt: dict[str, Any]) -> dict[str, Any]:
    sketch_summary = as_obj(sketch.get("runtime_summary"))
    prompt_summary = as_obj(prompt.get("runtime_topology_summary"))
    return {
        "grid": as_obj(sketch_summary.get("grid")) or as_obj(prompt_summary.get("grid")),
        "path_route_count": sketch_summary.get("path_route_count") or prompt_summary.get("path_route_count"),
        "build_slot_count": sketch_summary.get("build_slot_count") or prompt_summary.get("build_slot_count"),
        "objective_count": sketch_summary.get("objective_count") or prompt_summary.get("objective_count"),
        "spawn_point_count": sketch_summary.get("spawn_point_count") or prompt_summary.get("spawn_point_count"),
    }


def build_provider_instruction(sketch: dict[str, Any], prompt: dict[str, Any]) -> str:
    runtime_topology = compact_runtime_topology(sketch, prompt)
    prompt_brief = str(prompt.get("prompt_brief") or "Create an empty tower-defense map background.")
    return "\n".join(
        [
            "Use the attached topology control sketch PNG as the exact composition reference.",
            "Transform it into a natural, polished, hand-painted 2D / pseudo-3D tower-defense battlefield background.",
            "The final image must not show the control sketch style; it should look like a finished game map.",
            "",
            "World and scene brief:",
            prompt_brief,
            "",
            "Topology that must remain readable:",
            f"- grid: {runtime_topology.get('grid')}",
            f"- route count: {runtime_topology.get('path_route_count')}",
            f"- build pad count target: {runtime_topology.get('build_slot_count')}",
            f"- objective count target: {runtime_topology.get('objective_count')}",
            f"- spawn point count target: {runtime_topology.get('spawn_point_count')}",
            "",
            "Hard output requirements:",
            "- wide 16:9 full-frame battlefield background, no UI, no border, no text",
            "- paths, objectives, and flat empty build pads must align visually with the reference sketch",
            "- build pads should be terrain-integrated clearings or flush stone foundations, not towers",
            "- enemy entrances and protected objectives should be implied by terrain landmarks, not arrows",
            "- leave enough readable ground around routes and pads for runtime overlays",
            "",
            "Forbidden elements:",
            *[f"- {item}" for item in UNIVERSAL_NEGATIVE_CONSTRAINTS],
        ]
    )


def build_fallback_instruction(sketch: dict[str, Any], prompt: dict[str, Any]) -> str:
    runtime_topology = compact_runtime_topology(sketch, prompt)
    return "\n".join(
        [
            str(prompt.get("prompt_brief") or "Create an empty tower-defense map background."),
            "",
            "Additional text-only topology constraints:",
            f"- preserve {runtime_topology.get('path_route_count')} readable route(s)",
            f"- provide roughly {runtime_topology.get('build_slot_count')} flat empty build pads near routes",
            f"- show {runtime_topology.get('objective_count')} protected objective landmark(s)",
            f"- show {runtime_topology.get('spawn_point_count')} enemy entrance area(s) at map edges",
            "- no UI, no arrows, no labels, no enemies, no placed towers, no combat effects",
            "",
            "Note: text-only fallback is lower confidence than using the control sketch reference image.",
        ]
    )


def markdown_prompt(
    request: dict[str, Any],
    provider_instruction: str,
    fallback_instruction: str,
) -> str:
    control = as_obj(request.get("control_sketch"))
    return "\n".join(
        [
            f"# Controlled Map Regeneration Request: {request.get('node_id')}",
            "",
            "## Reference Image",
            "",
            f"- PNG: `{control.get('png_path')}`",
            f"- SVG review: `{control.get('svg_path')}`",
            "",
            "Attach the PNG as a reference / control image when the provider supports it.",
            "",
            "## Provider Instruction",
            "",
            "```text",
            provider_instruction,
            "```",
            "",
            "## Text-Only Fallback",
            "",
            "```text",
            fallback_instruction,
            "```",
            "",
            "## Review Policy",
            "",
            "- This request is review-only.",
            "- Generated output must re-enter candidate, alignment, overlay, visual, and promotion gates.",
            "- Do not update MapRuntimePackage or published visual layers directly.",
            "",
        ]
    )


def build_request(
    sketch: dict[str, Any],
    prompt: dict[str, Any] | None,
    control_sketch_pack_path: Path,
    prompt_pack_path: Path,
    prompt_dir: Path,
) -> dict[str, Any]:
    node_id = str(sketch.get("node_id") or "unknown_node")
    png_path = resolve_repo_path(sketch.get("control_sketch_png_path"))
    svg_path = resolve_repo_path(sketch.get("control_sketch_svg_path"))
    issues = []
    if prompt is None:
        issues.append("topology_prompt_entry_missing")
        prompt = {}
    if png_path is None or not png_path.exists():
        issues.append("control_sketch_png_missing")
    if svg_path is None or not svg_path.exists():
        issues.append("control_sketch_svg_missing")

    provider_instruction = build_provider_instruction(sketch, prompt)
    fallback_instruction = build_fallback_instruction(sketch, prompt)
    prompt_md_path = prompt_dir / f"{node_id}.controlled_map_regeneration_request.md"
    request_status = "blocked" if issues else "request_ready_reference_image_preferred"

    request: dict[str, Any] = {
        "request_id": f"{node_id}.controlled_map_regeneration_request",
        "node_id": node_id,
        "status": request_status,
        "issues": issues,
        "runtime_package_path": sketch.get("runtime_package_path") or prompt.get("runtime_package_path"),
        "source_control_sketch_pack": rel(control_sketch_pack_path),
        "source_prompt_pack": rel(prompt_pack_path),
        "source_prompt_status": prompt.get("status"),
        "primary_use": prompt.get("primary_use") or "controlled_regeneration",
        "topology_policy": prompt.get("topology_policy") or "preserve_existing_runtime_topology",
        "control_sketch": {
            "png_path": rel(png_path) if png_path else sketch.get("control_sketch_png_path"),
            "svg_path": rel(svg_path) if svg_path else sketch.get("control_sketch_svg_path"),
            "png_sha256": sha256_file(png_path) if png_path else None,
            "svg_sha256": sha256_file(svg_path) if svg_path else None,
            "dimensions": as_obj(sketch.get("dimensions")),
            "usage_policy": as_list(sketch.get("usage_policy")),
        },
        "provider_reference_contract": {
            "preferred_mode": "image_reference_plus_text",
            "reference_image_role": "topology_control_sketch",
            "reference_image_must_not_be_copied_as_final_style": True,
            "fallback_mode": "text_only_topology_brief",
            "fallback_expected_quality": "lower_than_reference_image_mode",
            "public_url_required_by_some_providers": True,
            "safe_to_send": "topology_only_no_secret_no_player_private_text",
        },
        "runtime_topology_summary": compact_runtime_topology(sketch, prompt),
        "provider_instruction_sha256": sha256_text(provider_instruction),
        "fallback_instruction_sha256": sha256_text(fallback_instruction),
        "manual_prompt_markdown_path": rel(prompt_md_path),
        "negative_constraints": sorted(
            {
                *[str(item) for item in as_list(prompt.get("negative_constraints"))],
                *UNIVERSAL_NEGATIVE_CONSTRAINTS,
            }
        ),
        "required_review_gates": REQUIRED_REVIEW_GATES,
        "target_candidate": {
            "recommended_output_dir": "game_data/media/map_visual_reference/node_candidates_controlled_v1",
            "candidate_role": "review_only_controlled_map_candidate",
            "promotion_allowed_now": False,
            "promotion_policy": "must pass explicit review and promotion report before runtime or player use",
        },
    }
    write_text(prompt_md_path, markdown_prompt(request, provider_instruction, fallback_instruction))
    request["manual_prompt_markdown_sha256"] = sha256_file(prompt_md_path)
    return request


def build_pack(control_sketch_pack_path: Path, prompt_pack_path: Path, prompt_dir: Path) -> dict[str, Any]:
    control_pack = load_json(control_sketch_pack_path)
    prompt_pack = load_json(prompt_pack_path)
    prompts = prompt_index(as_obj(prompt_pack))
    requests = [
        build_request(
            sketch,
            prompts.get(str(sketch.get("node_id"))),
            control_sketch_pack_path,
            prompt_pack_path,
            prompt_dir,
        )
        for sketch in as_list(as_obj(control_pack).get("sketches"))
        if isinstance(sketch, dict)
    ]
    status_counts = Counter(str(request.get("status")) for request in requests)
    return {
        "schema_version": REPORT_VERSION,
        "pack_id": "mvp_map_controlled_regeneration_request_pack",
        "status": "blocked" if status_counts.get("blocked") else "request_pack_ready_review_only",
        "source_control_sketch_pack": rel(control_sketch_pack_path),
        "source_prompt_pack": rel(prompt_pack_path),
        "prompt_dir": rel(prompt_dir),
        "summary": {
            "request_count": len(requests),
            "ready_count": status_counts.get("request_ready_reference_image_preferred", 0),
            "blocked_count": status_counts.get("blocked", 0),
            "reference_image_request_count": len(requests),
            "status_counts": dict(sorted(status_counts.items())),
        },
        "requests": requests,
        "policy": [
            "This pack is an input contract for controlled map regeneration, not a published visual layer.",
            "Reference images are deterministic topology sketches derived from MapRuntimePackage.",
            "Generated map candidates must pass candidate, alignment, overlay, visual, and promotion gates before runtime use.",
            "If a provider requires public URLs for reference images, expose only the control sketch PNGs, never secrets or raw traces.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build controlled map regeneration request pack.")
    parser.add_argument("--control-sketch-pack", default=str(DEFAULT_CONTROL_SKETCH_PACK))
    parser.add_argument("--prompt-pack", default=str(default_prompt_pack()))
    parser.add_argument("--prompt-dir", default=str(DEFAULT_PROMPT_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    control_sketch_pack = Path(args.control_sketch_pack)
    if not control_sketch_pack.is_absolute():
        control_sketch_pack = ROOT / control_sketch_pack
    prompt_pack = Path(args.prompt_pack)
    if not prompt_pack.is_absolute():
        prompt_pack = ROOT / prompt_pack
    prompt_dir = Path(args.prompt_dir)
    if not prompt_dir.is_absolute():
        prompt_dir = ROOT / prompt_dir
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output

    pack = build_pack(control_sketch_pack, prompt_pack, prompt_dir)
    write_json(output, pack)
    print(f"Wrote {output}")
    print(f"- status: {pack['status']}")
    print(f"- requests: {pack['summary']['request_count']}")
    return 0 if pack["summary"]["request_count"] and pack["status"] != "blocked" else 1


if __name__ == "__main__":
    raise SystemExit(main())
