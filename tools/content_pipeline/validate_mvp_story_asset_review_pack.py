#!/usr/bin/env python3
"""Validate an MVP Story Asset Review Pack v0.1.

The review pack is a human-facing delivery artifact for staged narrative,
NPC/material boundaries, research hooks, and gameplay asset readiness. This
validator turns it from ordinary JSON into a checked artifact:

- JSON parses and matches shared/schemas/mvp_story_asset_review_pack.v0.1.schema.json.
- Forbidden provider/raw payload fields and strings are rejected recursively.
- Every stage bundle file exists and validates as NarrativeEventBundle v0.1.
- Stage asset source_file refs and concrete battle fixture refs exist.
- Canonical NPC/material IDs must exist in the current worldbook registries.
- Candidate-only NPC/material IDs may be absent from registries only when the
  review pack marks them as candidate/review items.
- Stage lane coverage is non-empty, and the whole pack covers both world_line
  and player_line.

The validator never reads .env and never calls a real provider.

Usage:
    python3 tools/content_pipeline/validate_mvp_story_asset_review_pack.py \
        examples/review_packs/mvp_story_asset_review_pack.v0.1.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ASSET_GRAPH_DIR = ROOT / "tools" / "asset_graph"
NARRATIVE_DIR = ROOT / "tools" / "narrative"
for path in (ASSET_GRAPH_DIR, NARRATIVE_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from validation_common import load_json, validate_json_schema  # noqa: E402
from validate_narrative_bundle import validate_narrative_bundle  # noqa: E402

SCHEMA_PATH = ROOT / "shared/schemas/mvp_story_asset_review_pack.v0.1.schema.json"
NPC_REGISTRY_PATH = ROOT / "content/worldbooks/long_night_lanterns/npcs.json"
MATERIAL_REGISTRY_PATH = ROOT / "content/worldbooks/long_night_lanterns/materials.json"

FORBIDDEN_KEY_TERMS = frozenset(
    {
        "provider",
        "model",
        "raw_prompt",
        "full_trace",
        "raw_json",
        "api_key",
        "secret",
        "unreviewed_content",
    }
)

FORBIDDEN_STRING_TERMS = FORBIDDEN_KEY_TERMS
PLAYER_VISIBLE_KEYS = frozenset(
    {
        "title",
        "display_name",
        "purpose",
        "gameplay_role",
        "gameplay_service",
    }
)
OPTIONAL_PLACEHOLDER_REFS = frozenset({"needed", "pending", "todo", "tbd"})


def _dedupe(errors: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for error in errors:
        if error not in seen:
            seen.add(error)
            out.append(error)
    return out


def _path_key(path: str) -> str:
    tail = path.rsplit(".", 1)[-1]
    if "[" in tail:
        tail = tail.split("[", 1)[0]
    return tail


def _is_player_visible_path(path: str) -> bool:
    parts = path.replace("]", "").replace("[", ".").split(".")
    return any(part in PLAYER_VISIBLE_KEYS for part in parts)


def scan_forbidden_terms(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            lowered_key = str(key).lower()
            for term in FORBIDDEN_KEY_TERMS:
                if term in lowered_key:
                    errors.append(
                        f"forbidden technical field '{child_path}' contains {term!r}"
                    )
                    break
            scan_forbidden_terms(child, child_path, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_forbidden_terms(child, f"{path}[{index}]", errors)
    elif isinstance(value, str):
        lowered = value.lower()
        if _path_key(path) != "pack_version":
            for term in FORBIDDEN_STRING_TERMS:
                if term in lowered:
                    errors.append(
                        f"forbidden technical term {term!r} found in string at '{path}'"
                    )
        if "schema" in lowered and _is_player_visible_path(path):
            errors.append(
                f"forbidden player-visible technical term 'schema' found at '{path}'"
            )


def _repo_path(ref: str) -> Path:
    return ROOT / ref


def _check_repo_file(ref: str, path: str, errors: list[str]) -> None:
    if ref.lower() in OPTIONAL_PLACEHOLDER_REFS:
        return
    if "*" in ref or "?" in ref:
        errors.append(f"{path} must be a concrete file path, got glob {ref!r}")
        return
    target = _repo_path(ref)
    if not target.is_file():
        errors.append(f"{path} references missing file: {ref}")


def _check_source_files(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key == "source_file":
                if isinstance(child, str):
                    _check_repo_file(child, child_path, errors)
                else:
                    errors.append(f"{child_path} must be a string")
            else:
                _check_source_files(child, child_path, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _check_source_files(child, f"{path}[{index}]", errors)


def _load_id_registry(
    registry_path: Path,
    *,
    array_key: str,
    id_key: str,
    label: str,
    errors: list[str],
) -> set[str]:
    try:
        data = load_json(registry_path)
    except Exception as exc:
        errors.append(f"cannot load {label} registry {registry_path}: {exc}")
        return set()
    entries = data.get(array_key)
    if not isinstance(entries, list):
        errors.append(f"{label} registry {registry_path} missing array {array_key!r}")
        return set()
    ids: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"{label} registry {array_key}[{index}] must be object")
            continue
        item_id = entry.get(id_key)
        if isinstance(item_id, str) and item_id:
            ids.add(item_id)
        else:
            errors.append(
                f"{label} registry {array_key}[{index}].{id_key} must be non-empty string"
            )
    return ids


def _candidate_npcs(pack: dict[str, Any]) -> dict[str, dict[str, Any]]:
    boundaries = pack.get("canonical_boundaries", {})
    candidates = boundaries.get("candidate_functional_npcs", [])
    if not isinstance(candidates, list):
        return {}
    return {
        str(candidate.get("npc_id")): candidate
        for candidate in candidates
        if isinstance(candidate, dict) and candidate.get("npc_id")
    }


def _candidate_materials(pack: dict[str, Any]) -> dict[str, dict[str, Any]]:
    boundaries = pack.get("canonical_boundaries", {})
    candidates = boundaries.get("candidate_only_materials", [])
    if not isinstance(candidates, list):
        return {}
    return {
        str(candidate.get("material_id")): candidate
        for candidate in candidates
        if isinstance(candidate, dict) and candidate.get("material_id")
    }


def _validate_generation_boundary(pack: dict[str, Any], errors: list[str]) -> None:
    boundary = pack.get("generation_boundary")
    if not isinstance(boundary, dict):
        errors.append("generation_boundary must be an object")
        return
    if boundary.get("front_end_integration") != "not_included":
        errors.append("generation_boundary.front_end_integration must be not_included")
    if boundary.get("base_worldbook_mutation") is not False:
        errors.append("generation_boundary.base_worldbook_mutation must be false")


def _validate_exclusions(pack: dict[str, Any], errors: list[str]) -> None:
    exclusions = pack.get("excluded_from_mvp_story_pack")
    if not isinstance(exclusions, list) or not exclusions:
        errors.append("excluded_from_mvp_story_pack must be a non-empty array")
        return
    for index, exclusion in enumerate(exclusions):
        path = f"excluded_from_mvp_story_pack[{index}]"
        if not isinstance(exclusion, dict):
            errors.append(f"{path} must be object")
            continue
        for key in ("ref", "reason"):
            value = exclusion.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{path}.{key} must be a non-empty string")


def _validate_canonical_boundaries(
    pack: dict[str, Any],
    *,
    known_npcs: set[str],
    known_materials: set[str],
    stage_ids: set[str],
    errors: list[str],
) -> None:
    boundaries = pack.get("canonical_boundaries")
    if not isinstance(boundaries, dict):
        errors.append("canonical_boundaries must be an object")
        return

    for index, npc in enumerate(boundaries.get("canonical_npcs", [])):
        path = f"canonical_boundaries.canonical_npcs[{index}]"
        if not isinstance(npc, dict):
            errors.append(f"{path} must be object")
            continue
        npc_id = npc.get("npc_id")
        if npc_id not in known_npcs:
            errors.append(f"{path}.npc_id={npc_id!r} is not registered canonical NPC")

    for index, material_id in enumerate(boundaries.get("canonical_materials", [])):
        if material_id not in known_materials:
            errors.append(
                "canonical_boundaries.canonical_materials"
                f"[{index}]={material_id!r} is not registered canonical material"
            )

    for npc_id, candidate in _candidate_npcs(pack).items():
        status = str(candidate.get("review_status", ""))
        if "candidate" not in status and "review" not in status:
            errors.append(
                f"candidate NPC {npc_id!r} must carry candidate/review review_status"
            )
        first_hint_stage = candidate.get("first_hint_stage")
        if first_hint_stage not in stage_ids:
            errors.append(
                f"candidate NPC {npc_id!r} first_hint_stage={first_hint_stage!r} "
                "does not match any stage_id"
            )

    for material_id, candidate in _candidate_materials(pack).items():
        reason = candidate.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            errors.append(f"candidate material {material_id!r} must carry reason")


def _validate_stage_bundle(
    stage: dict[str, Any],
    *,
    path: str,
    errors: list[str],
) -> None:
    bundle_file = stage.get("bundle_file")
    if not isinstance(bundle_file, str) or not bundle_file:
        errors.append(f"{path}.bundle_file must be a non-empty string")
        return
    bundle_path = _repo_path(bundle_file)
    if not bundle_path.is_file():
        errors.append(f"{path}.bundle_file references missing file: {bundle_file}")
        return
    try:
        bundle = load_json(bundle_path)
    except json.JSONDecodeError as exc:
        errors.append(f"{path}.bundle_file is invalid JSON: {exc}")
        return
    except Exception as exc:
        errors.append(f"{path}.bundle_file cannot be loaded: {exc}")
        return

    bundle_errors = validate_narrative_bundle(bundle)
    errors.extend(f"{path}.bundle_file {bundle_file}: {error}" for error in bundle_errors)

    stage_id = stage.get("stage_id")
    if bundle.get("stage") != stage_id:
        errors.append(
            f"{path}.bundle_file stage mismatch: pack has {stage_id!r}, "
            f"bundle has {bundle.get('stage')!r}"
        )


def _validate_stage_refs(
    stage: dict[str, Any],
    *,
    path: str,
    known_npcs: set[str],
    known_materials: set[str],
    candidate_npcs: dict[str, dict[str, Any]],
    candidate_materials: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    canonical_npcs = stage.get("npcs", {}).get("canonical", [])
    if isinstance(canonical_npcs, list):
        for index, npc_id in enumerate(canonical_npcs):
            if npc_id not in known_npcs:
                errors.append(
                    f"{path}.npcs.canonical[{index}]={npc_id!r} is not registered"
                )

    candidate_stage_npcs = stage.get("npcs", {}).get("candidate", [])
    if isinstance(candidate_stage_npcs, list):
        for index, npc_id in enumerate(candidate_stage_npcs):
            candidate = candidate_npcs.get(str(npc_id))
            if not candidate:
                errors.append(
                    f"{path}.npcs.candidate[{index}]={npc_id!r} is not declared "
                    "in canonical_boundaries.candidate_functional_npcs"
                )
                continue
            status = str(candidate.get("review_status", ""))
            if "candidate" not in status and "review" not in status:
                errors.append(
                    f"{path}.npcs.candidate[{index}]={npc_id!r} lacks candidate/review status"
                )

    canonical_materials = stage.get("materials", {}).get("canonical", [])
    if isinstance(canonical_materials, list):
        for index, material_id in enumerate(canonical_materials):
            if material_id not in known_materials:
                errors.append(
                    f"{path}.materials.canonical[{index}]={material_id!r} is not registered"
                )

    stage_candidate_materials = stage.get("materials", {}).get("candidate_only", [])
    if isinstance(stage_candidate_materials, list):
        for index, material_id in enumerate(stage_candidate_materials):
            candidate = candidate_materials.get(str(material_id))
            if not candidate:
                errors.append(
                    f"{path}.materials.candidate_only[{index}]={material_id!r} is not "
                    "declared in canonical_boundaries.candidate_only_materials"
                )
                continue
            reason = candidate.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                errors.append(
                    f"{path}.materials.candidate_only[{index}]={material_id!r} lacks reason"
                )

    for index, battle in enumerate(stage.get("battle_nodes", [])):
        if not isinstance(battle, dict):
            continue
        fixture = battle.get("fixture")
        if isinstance(fixture, str):
            _check_repo_file(fixture, f"{path}.battle_nodes[{index}].fixture", errors)


def _validate_stages(
    pack: dict[str, Any],
    *,
    known_npcs: set[str],
    known_materials: set[str],
    errors: list[str],
) -> None:
    stages = pack.get("stages")
    if not isinstance(stages, list) or not stages:
        errors.append("stages must be a non-empty array")
        return

    stage_ids = {str(stage.get("stage_id")) for stage in stages if isinstance(stage, dict)}
    candidate_npcs = _candidate_npcs(pack)
    candidate_materials = _candidate_materials(pack)
    lane_union: set[str] = set()
    orders: list[int] = []

    for index, stage in enumerate(stages):
        path = f"stages[{index}]"
        if not isinstance(stage, dict):
            errors.append(f"{path} must be object")
            continue

        order = stage.get("order")
        if isinstance(order, int):
            orders.append(order)

        lanes = stage.get("lane_coverage")
        if not isinstance(lanes, list) or not lanes:
            errors.append(f"{path}.lane_coverage must be a non-empty array")
        else:
            lane_union.update(str(lane) for lane in lanes)
            if not ({"world_line", "player_line"} & set(lanes)):
                errors.append(
                    f"{path}.lane_coverage must include world_line or player_line"
                )

        _validate_stage_bundle(stage, path=path, errors=errors)
        _validate_stage_refs(
            stage,
            path=path,
            known_npcs=known_npcs,
            known_materials=known_materials,
            candidate_npcs=candidate_npcs,
            candidate_materials=candidate_materials,
            errors=errors,
        )

    expected_orders = list(range(1, len(stages) + 1))
    if sorted(orders) != expected_orders:
        errors.append(
            f"stage order values must be continuous {expected_orders}, got {sorted(orders)}"
        )

    if "world_line" not in lane_union or "player_line" not in lane_union:
        errors.append("stages overall must cover both world_line and player_line")

    _validate_canonical_boundaries(
        pack,
        known_npcs=known_npcs,
        known_materials=known_materials,
        stage_ids=stage_ids,
        errors=errors,
    )


def validate_review_pack(pack: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(pack, dict):
        return ["review pack root must be an object"]

    errors.extend(validate_json_schema(pack, SCHEMA_PATH))
    scan_forbidden_terms(pack, "", errors)
    _validate_generation_boundary(pack, errors)
    _validate_exclusions(pack, errors)
    _check_source_files(pack, "", errors)

    known_npcs = _load_id_registry(
        NPC_REGISTRY_PATH,
        array_key="npcs",
        id_key="stable_internal_id",
        label="NPC",
        errors=errors,
    )
    known_materials = _load_id_registry(
        MATERIAL_REGISTRY_PATH,
        array_key="materials",
        id_key="stable_internal_id",
        label="material",
        errors=errors,
    )

    _validate_stages(
        pack,
        known_npcs=known_npcs,
        known_materials=known_materials,
        errors=errors,
    )
    return _dedupe(errors)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate an MVP Story Asset Review Pack v0.1 JSON file."
    )
    parser.add_argument("pack", help="Path to the review pack JSON file.")
    args = parser.parse_args()

    pack_path = Path(args.pack)
    try:
        pack = load_json(pack_path)
    except FileNotFoundError:
        print("INVALID MVPStoryAssetReviewPack")
        print(f"- pack file not found: {pack_path}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID MVPStoryAssetReviewPack")
        print(f"- pack is not valid JSON: {exc}")
        return 1

    errors = validate_review_pack(pack)
    if errors:
        print("INVALID MVPStoryAssetReviewPack")
        for error in errors:
            print(f"- {error}")
        return 1

    stages = pack.get("stages", [])
    print("OK MVPStoryAssetReviewPack")
    print(f"- pack_id: {pack.get('pack_id')}")
    print(f"- stages: {len(stages)}")
    print(f"- worldbook_id: {pack.get('worldbook_id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
