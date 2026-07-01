#!/usr/bin/env python3
"""Semantic gate for WorldStateDelta v0.1.

This validator runs after the structural WorldStateDelta validator and before
apply_world_delta.py. It checks references and small state-machine semantics
that JSON Schema cannot express well.

The gate never reads .env and never calls a real provider.

Usage:
    python3 tools/world_state/validate_world_delta_semantics.py <delta.json> \
        --run-state examples/run_world_states/demo_initial.run_world_state.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _common import BANNED_PLAYER_WORDS, load_json  # noqa: E402
from validate_run_world_state import (  # noqa: E402
    validate_run_world_state,
    validate_with_jsonschema as validate_state_with_jsonschema,
)
from validate_world_delta import (  # noqa: E402
    validate_world_delta,
    validate_with_jsonschema as validate_delta_with_jsonschema,
)

DEFAULT_REVIEW_PACK = ROOT / "examples/review_packs/mvp_story_asset_review_pack.v0.1.json"


@dataclass(frozen=True)
class ReferenceRegistry:
    run_map_node_ids: frozenset[str]
    run_resource_ids: frozenset[str]
    registered_resource_ids: frozenset[str]
    run_npc_ids: frozenset[str]
    canonical_npc_ids: frozenset[str]
    candidate_npc_ids: frozenset[str]
    legacy_npc_ids: frozenset[str]

    @property
    def allowed_resource_ids(self) -> frozenset[str]:
        return self.run_resource_ids | self.registered_resource_ids

    @property
    def allowed_npc_ids(self) -> frozenset[str]:
        return (
            self.run_npc_ids | self.canonical_npc_ids | self.candidate_npc_ids
        ) - self.legacy_npc_ids


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _string_set(values: Iterable[Any]) -> set[str]:
    return {value for value in values if isinstance(value, str) and value}


def _load_optional_json(path: Path) -> Any | None:
    try:
        return load_json(path)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _extract_worldbook_npcs(worldbook_id: str) -> set[str]:
    ids: set[str] = set()
    base = ROOT / "content/worldbooks" / worldbook_id

    npcs = _load_optional_json(base / "npcs.json")
    if isinstance(npcs, dict):
        for npc in npcs.get("npcs", []) or []:
            if isinstance(npc, dict):
                ids.update(_string_set([npc.get("stable_internal_id"), npc.get("npc_id")]))

    worldbook = _load_optional_json(base / "worldbook.json")
    if isinstance(worldbook, dict):
        for npc in worldbook.get("npc_archetypes", []) or []:
            if isinstance(npc, dict):
                ids.update(_string_set([npc.get("stable_internal_id"), npc.get("npc_id")]))
    return ids


def _extract_worldbook_resources(worldbook_id: str) -> set[str]:
    ids: set[str] = set()
    base = ROOT / "content/worldbooks" / worldbook_id

    materials = _load_optional_json(base / "materials.json")
    if isinstance(materials, dict):
        for item in materials.get("materials", []) or []:
            if isinstance(item, dict):
                ids.update(
                    _string_set([item.get("stable_internal_id"), item.get("material_id")])
                )
        for origin_items in (materials.get("origin_initial_materials", {}) or {}).values():
            if isinstance(origin_items, list):
                for item in origin_items:
                    if isinstance(item, dict):
                        ids.update(_string_set([item.get("material_id")]))

    worldbook = _load_optional_json(base / "worldbook.json")
    if isinstance(worldbook, dict):
        mapping = worldbook.get("resource_mapping")
        if isinstance(mapping, dict):
            ids.update(_string_set(mapping.keys()))
    return ids


def _extract_review_pack_boundaries(path: Path) -> tuple[set[str], set[str], set[str], set[str]]:
    canonical_npcs: set[str] = set()
    candidate_npcs: set[str] = set()
    legacy_npcs: set[str] = set()
    resources: set[str] = set()

    review_pack = _load_optional_json(path)
    if not isinstance(review_pack, dict):
        return canonical_npcs, candidate_npcs, legacy_npcs, resources

    boundaries = review_pack.get("canonical_boundaries")
    if not isinstance(boundaries, dict):
        return canonical_npcs, candidate_npcs, legacy_npcs, resources

    for npc in boundaries.get("canonical_npcs", []) or []:
        if isinstance(npc, dict):
            canonical_npcs.update(_string_set([npc.get("npc_id"), npc.get("stable_internal_id")]))
    for npc in boundaries.get("candidate_functional_npcs", []) or []:
        if isinstance(npc, dict):
            candidate_npcs.update(_string_set([npc.get("npc_id"), npc.get("stable_internal_id")]))
    for ref in boundaries.get("compatibility_refs", []) or []:
        if isinstance(ref, dict) and ref.get("status") == "legacy_fixture_ref":
            legacy_npcs.update(_string_set([ref.get("ref_id"), ref.get("npc_id")]))

    resources.update(_string_set(boundaries.get("canonical_materials", []) or []))
    for item in boundaries.get("candidate_only_materials", []) or []:
        if isinstance(item, dict):
            resources.update(_string_set([item.get("material_id"), item.get("resource_id")]))
    return canonical_npcs, candidate_npcs, legacy_npcs, resources


def build_reference_registry(run_state: dict[str, Any], review_pack_path: Path) -> ReferenceRegistry:
    worldbook_id = str(run_state.get("worldbook_id") or "")
    review_canonical, review_candidates, legacy_npcs, review_resources = (
        _extract_review_pack_boundaries(review_pack_path)
    )

    return ReferenceRegistry(
        run_map_node_ids=frozenset(
            _string_set(
                node.get("node_id")
                for node in run_state.get("map_nodes", []) or []
                if isinstance(node, dict)
            )
        ),
        run_resource_ids=frozenset(
            _string_set(
                res.get("resource_id")
                for res in run_state.get("resources", []) or []
                if isinstance(res, dict)
            )
        ),
        registered_resource_ids=frozenset(
            _extract_worldbook_resources(worldbook_id) | review_resources
        ),
        run_npc_ids=frozenset(
            _string_set(
                npc.get("npc_id")
                for npc in run_state.get("npcs", []) or []
                if isinstance(npc, dict)
            )
        ),
        canonical_npc_ids=frozenset(_extract_worldbook_npcs(worldbook_id) | review_canonical),
        candidate_npc_ids=frozenset(review_candidates),
        legacy_npc_ids=frozenset(legacy_npcs),
    )


def _full_delta_validation(delta: dict[str, Any]) -> list[str]:
    return _dedupe([*validate_delta_with_jsonschema(delta), *validate_world_delta(delta)])


def _full_state_validation(state: dict[str, Any]) -> list[str]:
    return _dedupe([*validate_state_with_jsonschema(state), *validate_run_world_state(state)])


def _word_boundary_regex(word: str) -> re.Pattern[str]:
    return re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)


_BANNED_WORD_REGEXES: list[tuple[str, re.Pattern[str]]] = [
    (word, _word_boundary_regex(word)) for word in sorted(BANNED_PLAYER_WORDS)
]


def _scan_text_value(text: Any, path: str, errors: list[str]) -> None:
    if not isinstance(text, str) or not text:
        return
    for word, pattern in _BANNED_WORD_REGEXES:
        if pattern.search(text):
            errors.append(
                f"{path}: player/world visible text contains technical word "
                f"{word!r}; keep provider/schema/prompt/raw_json/api_key/trace "
                "terms out of player-facing delta text"
            )


def _scan_semantic_visible_text(delta: dict[str, Any], errors: list[str]) -> None:
    _scan_text_value(delta.get("summary"), "summary", errors)
    for i, op in enumerate(delta.get("operations", []) or []):
        if not isinstance(op, dict):
            continue
        op_name = op.get("op")
        base = f"operations[{i}]"
        if op_name == "append_event" and isinstance(op.get("event"), dict):
            _scan_text_value(op["event"].get("summary"), f"{base}.event.summary", errors)
        elif op_name == "unlock_fact" and isinstance(op.get("fact"), dict):
            _scan_text_value(op["fact"].get("summary"), f"{base}.fact.summary", errors)
        elif op_name == "add_temporary_sample" and isinstance(op.get("sample"), dict):
            sample = op["sample"]
            _scan_text_value(sample.get("display_name"), f"{base}.sample.display_name", errors)
            _scan_text_value(sample.get("summary"), f"{base}.sample.summary", errors)


def validate_world_delta_semantics(
    delta: dict[str, Any], run_state: dict[str, Any], registry: ReferenceRegistry
) -> list[str]:
    """Return semantic errors; empty list means the delta may proceed to apply."""
    errors: list[str] = []

    if delta.get("run_id") != run_state.get("run_id"):
        errors.append(
            "delta.run_id must match run_state.run_id "
            f"(delta={delta.get('run_id')!r}, run_state={run_state.get('run_id')!r})"
        )
    if delta.get("worldbook_id") != run_state.get("worldbook_id"):
        errors.append(
            "delta.worldbook_id must match run_state.worldbook_id "
            f"(delta={delta.get('worldbook_id')!r}, "
            f"run_state={run_state.get('worldbook_id')!r})"
        )

    delta_id = delta.get("delta_id")
    source = delta.get("source")
    available_map_node_ids = set(registry.run_map_node_ids)
    available_npc_ids = set(registry.run_npc_ids)
    for i, op in enumerate(delta.get("operations", []) or []):
        if not isinstance(op, dict):
            continue
        op_name = op.get("op")
        path = f"operations[{i}]"

        if op_name == "set_map_node_state":
            node_id = op.get("node_id")
            if node_id not in available_map_node_ids:
                errors.append(
                    f"{path}.node_id={node_id!r} is not in current or newly introduced "
                    f"run_state.map_nodes (known: {sorted(available_map_node_ids)})"
                )

        elif op_name == "adjust_resource":
            resource_id = op.get("resource_id")
            if resource_id not in registry.allowed_resource_ids:
                errors.append(
                    f"{path}.resource_id={resource_id!r} is not a current run "
                    "resource or registered worldbook/review-pack resource "
                    f"(run resources: {sorted(registry.run_resource_ids)})"
                )
            if (
                resource_id not in registry.run_resource_ids
                and isinstance(op.get("amount_delta"), (int, float))
                and not isinstance(op.get("amount_delta"), bool)
                and op["amount_delta"] < 0
            ):
                errors.append(
                    f"{path}.resource_id={resource_id!r} is not present in the "
                    "current run state and cannot be consumed with a negative delta"
                )

        elif op_name == "introduce_map_node":
            node = op.get("node")
            if isinstance(node, dict):
                node_id = node.get("node_id")
                if isinstance(node_id, str) and node_id:
                    available_map_node_ids.add(node_id)

        elif op_name == "update_npc_relationship":
            npc_id = op.get("npc_id")
            if npc_id in registry.legacy_npc_ids:
                errors.append(
                    f"{path}.npc_id={npc_id!r} is a legacy fixture NPC ref; "
                    "replace it with a canonical or explicitly reviewed candidate NPC id"
                )
            elif npc_id not in available_npc_ids:
                if npc_id in registry.canonical_npc_ids or npc_id in registry.candidate_npc_ids:
                    errors.append(
                        f"{path}.npc_id={npc_id!r} is registered or whitelisted but "
                        "is not present in current or newly introduced run_state.npcs; introduce the NPC "
                        "into the run state before applying a relationship update"
                    )
                else:
                    errors.append(
                        f"{path}.npc_id={npc_id!r} is not in run state, canonical "
                        "worldbook NPCs, or explicit candidate whitelist "
                        f"(allowed references: {sorted(registry.allowed_npc_ids)})"
                    )
            elif npc_id not in registry.allowed_npc_ids:
                errors.append(
                    f"{path}.npc_id={npc_id!r} is present in run state but blocked "
                    "by the current review-pack boundary"
                )

        elif op_name == "introduce_npc":
            npc = op.get("npc")
            if isinstance(npc, dict):
                npc_id = npc.get("npc_id")
                location_node_id = npc.get("location_node_id")
                if npc_id in registry.legacy_npc_ids:
                    errors.append(
                        f"{path}.npc.npc_id={npc_id!r} is a legacy fixture NPC ref; "
                        "do not introduce it into the formal run state"
                    )
                elif npc_id not in registry.allowed_npc_ids:
                    errors.append(
                        f"{path}.npc.npc_id={npc_id!r} is not canonical, already "
                        "present, or explicitly whitelisted as a candidate NPC "
                        f"(allowed references: {sorted(registry.allowed_npc_ids)})"
                    )
                if (
                    isinstance(location_node_id, str)
                    and location_node_id
                    and location_node_id not in available_map_node_ids
                ):
                    errors.append(
                        f"{path}.npc.location_node_id={location_node_id!r} is not "
                        "in current or newly introduced map nodes"
                    )
                if isinstance(npc_id, str) and npc_id:
                    available_npc_ids.add(npc_id)

        elif op_name == "add_temporary_sample":
            sample = op.get("sample")
            if isinstance(sample, dict):
                sample_id = sample.get("sample_id")
                if not isinstance(sample_id, str) or not sample_id.strip():
                    errors.append(f"{path}.sample.sample_id must be non-empty")
                source_delta_id = sample.get("source_delta_id")
                if source_delta_id != delta_id:
                    errors.append(
                        f"{path}.sample.source_delta_id={source_delta_id!r} must "
                        f"match delta_id={delta_id!r}"
                    )

        elif op_name == "set_progress_phase":
            phase = op.get("phase")
            if not isinstance(phase, str) or not phase.strip():
                errors.append(f"{path}.phase must be non-empty")

        elif op_name == "set_flag":
            flag = op.get("flag")
            if (
                source == "battle_result"
                and isinstance(flag, str)
                and flag.endswith("_started")
                and op.get("value") is True
            ):
                suggested = flag[: -len("_started")] + "_completed"
                errors.append(
                    f"{path}.flag={flag!r} sets a *_started flag to true after "
                    f"source='battle_result'; use a completion flag such as "
                    f"{suggested!r} instead"
                )

    _scan_semantic_visible_text(delta, errors)
    return _dedupe(errors)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate WorldStateDelta v0.1 semantics before apply_world_delta.py."
    )
    parser.add_argument("delta", help="Path to a WorldStateDelta JSON file.")
    parser.add_argument(
        "--run-state",
        required=True,
        help="Path to the current RunWorldState JSON file used as semantic context.",
    )
    parser.add_argument(
        "--review-pack",
        default=str(DEFAULT_REVIEW_PACK),
        help="Optional review pack containing canonical/candidate boundaries.",
    )
    args = parser.parse_args()

    delta_path = Path(args.delta)
    run_state_path = Path(args.run_state)
    review_pack_path = Path(args.review_pack)

    try:
        delta = load_json(delta_path)
    except FileNotFoundError:
        print("INVALID WorldStateDelta semantics")
        print(f"- delta file not found: {delta_path}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID WorldStateDelta semantics")
        print(f"- delta is not valid JSON: {exc}")
        return 1
    if not isinstance(delta, dict):
        print("INVALID WorldStateDelta semantics")
        print("- delta root must be an object")
        return 1

    structural_errors = _full_delta_validation(delta)
    if structural_errors:
        print("INVALID WorldStateDelta structure")
        for error in structural_errors:
            print(f"- {error}")
        return 1

    try:
        run_state = load_json(run_state_path)
    except FileNotFoundError:
        print("INVALID WorldStateDelta semantics")
        print(f"- run state file not found: {run_state_path}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID WorldStateDelta semantics")
        print(f"- run state is not valid JSON: {exc}")
        return 1
    if not isinstance(run_state, dict):
        print("INVALID WorldStateDelta semantics")
        print("- run state root must be an object")
        return 1

    state_errors = _full_state_validation(run_state)
    if state_errors:
        print("INVALID RunWorldState context")
        for error in state_errors:
            print(f"- {error}")
        return 1

    registry = build_reference_registry(run_state, review_pack_path)
    errors = validate_world_delta_semantics(delta, run_state, registry)
    if errors:
        print("INVALID WorldStateDelta semantics")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"OK: {delta_path}")
    print("- semantic_gate: world_state_delta_semantic_gate.v0.1")
    print(f"- run_state: {run_state_path}")
    print(f"- delta_id: {delta.get('delta_id')}")
    print(f"- operations: {len(delta.get('operations', []))}")
    print(f"- run_map_nodes: {len(registry.run_map_node_ids)}")
    print(f"- allowed_resources: {len(registry.allowed_resource_ids)}")
    print(f"- allowed_npcs: {len(registry.allowed_npc_ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
