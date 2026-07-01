#!/usr/bin/env python3
"""Validate a NarrativeEventBundle v0.1 JSON file.

Checks:
- JSON parses and matches shared/schemas/narrative_event_bundle.v0.1.schema.json.
- All narrative nodes are staged, laned, visible-scoped, and gameplay-bound.
- gameplay_purpose and gameplay_hooks are non-empty and whitelist-only.
- Every commit-capable node carries at least one gameplay hook.
- The bundle only proposes WorldStateDelta intent and may not mutate the
  BaseWorldbook directly.
- Technical/studio/provider terms are rejected recursively. schema_version is
  allowed as a structural key, but player-visible text may not contain schema,
  prompt, provider, trace, simulation, or related terms.

The validator never reads .env and never calls a real provider.

Usage:
    python3 tools/narrative/validate_narrative_bundle.py <bundle_path>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
ASSET_GRAPH_DIR = ROOT / "tools" / "asset_graph"
if str(ASSET_GRAPH_DIR) not in sys.path:
    sys.path.insert(0, str(ASSET_GRAPH_DIR))

from validation_common import load_json, validate_json_schema  # noqa: E402

SCHEMA_PATH = ROOT / "shared/schemas/narrative_event_bundle.v0.1.schema.json"

ALLOWED_GAMEPLAY_PURPOSES: frozenset[str] = frozenset(
    {
        "unlock_battle_node",
        "introduce_functional_npc",
        "introduce_generic_npc",
        "introduce_material",
        "create_research_need",
        "modify_map_node_state",
        "offer_workshop_hook",
        "advance_main_pressure",
        "explain_battle_result",
        "trigger_random_event",
        "teach_mechanic",
        "reward_player_choice",
        "increase_threat",
        "open_resource_route",
        "create_quest_hook",
    }
)

ALLOWED_GAMEPLAY_HOOKS = ALLOWED_GAMEPLAY_PURPOSES

ALLOWED_WORLD_DELTA_OPS: frozenset[str] = frozenset(
    {
        "append_event",
        "set_map_node_state",
        "adjust_resource",
        "set_flag",
        "unlock_fact",
        "update_npc_relationship",
        "add_temporary_sample",
        "set_progress_phase",
        "adjust_global_state",
    }
)

FORBIDDEN_KEY_TERMS: frozenset[str] = frozenset(
    {
        "provider",
        "model",
        "prompt",
        "schema",
        "raw_prompt",
        "full_trace",
        "raw_json",
        "api_key",
        "secret",
        "unreviewed_content",
        "traceback",
        "simulation",
        "trace",
    }
)

FORBIDDEN_STRING_TERMS = FORBIDDEN_KEY_TERMS

FORBIDDEN_WORLD_MUTATION_TERMS: frozenset[str] = frozenset(
    {
        "mutate_base_worldbook",
        "set_worldbook",
        "replace_worldbook",
        "worldbook_patch",
        "base_worldbook_patch",
        "raw_json_patch",
        "arbitrary_patch",
        "eval",
        "script",
        "provider_call",
    }
)

KEY_SCAN_ALLOWLIST: frozenset[str] = frozenset(
    {
        "schema_version",
    }
)


def _dedupe(errors: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for error in errors:
        if error not in seen:
            seen.add(error)
            out.append(error)
    return out


def _term_regex(term: str) -> re.Pattern[str]:
    return re.compile(re.escape(term), re.IGNORECASE)


_FORBIDDEN_STRING_REGEXES = [
    (term, _term_regex(term)) for term in sorted(FORBIDDEN_STRING_TERMS)
]


def _scan_forbidden_terms(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            lowered_key = key.lower() if isinstance(key, str) else ""
            if key not in KEY_SCAN_ALLOWLIST:
                for term in FORBIDDEN_KEY_TERMS:
                    if term in lowered_key:
                        errors.append(
                            f"forbidden technical field '{child_path}' contains term {term!r}"
                        )
                        break
                for term in FORBIDDEN_WORLD_MUTATION_TERMS:
                    if term in lowered_key:
                        errors.append(
                            f"forbidden world mutation field '{child_path}' contains term {term!r}"
                        )
                        break
            _scan_forbidden_terms(child, child_path, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan_forbidden_terms(child, f"{path}[{index}]", errors)
    elif isinstance(value, str):
        for term, pattern in _FORBIDDEN_STRING_REGEXES:
            if pattern.search(value):
                errors.append(
                    f"forbidden technical term {term!r} found in string at '{path}'"
                )
        lowered = value.lower()
        for term in FORBIDDEN_WORLD_MUTATION_TERMS:
            if term in lowered:
                errors.append(
                    f"forbidden world mutation term {term!r} found in string at '{path}'"
                )


def _validate_gameplay_gate(bundle: dict[str, Any], errors: list[str]) -> None:
    nodes = bundle.get("nodes", [])
    if not isinstance(nodes, list) or not nodes:
        errors.append("nodes must be a non-empty array")
        return

    for index, node in enumerate(nodes):
        path = f"nodes[{index}]"
        if not isinstance(node, dict):
            errors.append(f"{path} must be an object")
            continue

        purposes = node.get("gameplay_purpose")
        if not isinstance(purposes, list) or not purposes:
            errors.append(f"{path}.gameplay_purpose must be a non-empty array")
            purposes = []
        for purpose in purposes:
            if purpose not in ALLOWED_GAMEPLAY_PURPOSES:
                errors.append(
                    f"{path}.gameplay_purpose contains {purpose!r}, allowed: "
                    f"{sorted(ALLOWED_GAMEPLAY_PURPOSES)}"
                )

        hooks = node.get("gameplay_hooks")
        if not isinstance(hooks, list) or not hooks:
            errors.append(f"{path}.gameplay_hooks must be a non-empty array")
            hooks = []
        for hook_index, hook in enumerate(hooks):
            hpath = f"{path}.gameplay_hooks[{hook_index}]"
            if not isinstance(hook, dict):
                errors.append(f"{hpath} must be an object")
                continue
            hook_name = hook.get("hook")
            if hook_name not in ALLOWED_GAMEPLAY_HOOKS:
                errors.append(
                    f"{hpath}.hook={hook_name!r} is not allowed; allowed: "
                    f"{sorted(ALLOWED_GAMEPLAY_HOOKS)}"
                )

        proposed = node.get("proposed_delta_summary")
        if not isinstance(proposed, dict):
            errors.append(f"{path}.proposed_delta_summary must be an object")
            continue
        ops = proposed.get("expected_operations")
        if not isinstance(ops, list) or not ops:
            errors.append(
                f"{path}.proposed_delta_summary.expected_operations must be non-empty"
            )
            continue
        for op in ops:
            if op not in ALLOWED_WORLD_DELTA_OPS:
                errors.append(
                    f"{path}.proposed_delta_summary.expected_operations contains "
                    f"{op!r}, allowed: {sorted(ALLOWED_WORLD_DELTA_OPS)}"
                )


def _validate_worldbook_gate(bundle: dict[str, Any], errors: list[str]) -> None:
    if bundle.get("worldbook_base_mutation_allowed") is not False:
        errors.append("worldbook_base_mutation_allowed must be false")

    policy = bundle.get("commit_policy")
    if isinstance(policy, dict):
        if policy.get("commit_gate") != "world_state_delta_required":
            errors.append(
                "commit_policy.commit_gate must be 'world_state_delta_required'"
            )


def validate_narrative_bundle(bundle: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(bundle, dict):
        return ["bundle root must be an object"]

    errors.extend(validate_json_schema(bundle, SCHEMA_PATH))
    _scan_forbidden_terms(bundle, "", errors)
    _validate_gameplay_gate(bundle, errors)
    _validate_worldbook_gate(bundle, errors)
    return _dedupe(errors)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a NarrativeEventBundle v0.1 JSON file."
    )
    parser.add_argument("bundle", help="Path to a narrative event bundle JSON file.")
    args = parser.parse_args()

    bundle_path = Path(args.bundle)
    try:
        bundle = load_json(bundle_path)
    except FileNotFoundError:
        print("INVALID NarrativeEventBundle")
        print(f"- bundle file not found: {bundle_path}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID NarrativeEventBundle")
        print(f"- bundle is not valid JSON: {exc}")
        return 1

    errors = validate_narrative_bundle(bundle)
    if errors:
        print("INVALID NarrativeEventBundle")
        for error in errors:
            print(f"- {error}")
        return 1

    print("OK NarrativeEventBundle")
    print(f"- bundle_id: {bundle.get('bundle_id')}")
    print(f"- nodes: {len(bundle.get('nodes', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
