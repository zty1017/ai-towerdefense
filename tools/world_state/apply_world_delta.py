#!/usr/bin/env python3
"""Apply a WorldStateDelta v0.1 to a RunWorldState v0.1 deterministically.

Pipeline:
1. Load and validate the input state (validate_run_world_state).
2. Load and validate the delta (validate_world_delta).
3. Check delta.run_id == state.run_id and delta.worldbook_id == state.worldbook_id.
4. Apply each operation in order. Each op is a controlled, side-effect-free
   mutation of the state dict. The worldbook_id is never changed.
5. Write the next state to output_path.
6. Re-validate the next state.

Determinism: operations are applied in the order given. Numeric adjustments
are added (not assigned). Resource adjustments create the resource if absent.

The applier never reads .env, never calls a real provider, and never mutates
the BaseWorldbook.

Usage:
    python3 tools/world_state/apply_world_delta.py <state_path> <delta_path> <output_path>
"""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _common import load_json  # noqa: E402
from validate_run_world_state import (  # noqa: E402
    validate_run_world_state,
    validate_with_jsonschema as validate_state_with_jsonschema,
)
from validate_world_delta import (  # noqa: E402
    validate_world_delta,
    validate_with_jsonschema as validate_delta_with_jsonschema,
)


def _full_state_validation(state: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_state_with_jsonschema(state))
    errors.extend(validate_run_world_state(state))
    seen: set[str] = set()
    out: list[str] = []
    for e in errors:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out


def _full_delta_validation(delta: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_delta_with_jsonschema(delta))
    errors.extend(validate_world_delta(delta))
    seen: set[str] = set()
    out: list[str] = []
    for e in errors:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out


def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _apply_append_event(state: dict[str, Any], op: dict[str, Any]) -> list[str]:
    event = op["event"]
    state.setdefault("event_log", []).append(deepcopy(event))
    return []


def _apply_set_map_node_state(state: dict[str, Any], op: dict[str, Any]) -> list[str]:
    node_id = op["node_id"]
    patch = op["patch"]
    nodes = state.setdefault("map_nodes", [])
    for node in nodes:
        if node.get("node_id") == node_id:
            for key in ("status", "threat_level", "visibility", "available_actions"):
                if key in patch:
                    node[key] = deepcopy(patch[key])
            return []
    return [f"set_map_node_state: node_id={node_id!r} not found in map_nodes"]


def _apply_adjust_resource(state: dict[str, Any], op: dict[str, Any]) -> list[str]:
    resource_id = op["resource_id"]
    delta = op["amount_delta"]
    resources = state.setdefault("resources", [])
    for res in resources:
        if res.get("resource_id") == resource_id:
            current = res.get("amount", 0)
            next_amount = current + delta
            if next_amount < 0:
                return [
                    f"adjust_resource: resource_id={resource_id!r} would become "
                    f"negative ({current} + {delta} = {next_amount})"
                ]
            res["amount"] = next_amount
            return []
    # not found: create it (controlled creation is allowed; the resource is
    # part of run state, not the BaseWorldbook).
    if delta < 0:
        return [
            f"adjust_resource: resource_id={resource_id!r} is absent and cannot "
            f"be adjusted by a negative amount ({delta})"
        ]
    resources.append({"resource_id": resource_id, "amount": delta})
    return []


def _apply_set_flag(state: dict[str, Any], op: dict[str, Any]) -> list[str]:
    flag = op["flag"]
    value = op["value"]
    state.setdefault("flags", {})[flag] = deepcopy(value)
    return []


def _apply_unlock_fact(state: dict[str, Any], op: dict[str, Any]) -> list[str]:
    fact = op["fact"]
    facts = state.setdefault("unlocked_facts", [])
    # de-duplicate by fact_id: if it exists, update visibility/summary instead
    # of appending a duplicate.
    fact_id = fact.get("fact_id")
    for existing in facts:
        if existing.get("fact_id") == fact_id:
            if "visibility" in fact:
                existing["visibility"] = fact["visibility"]
            if "summary" in fact:
                existing["summary"] = fact["summary"]
            return []
    facts.append(deepcopy(fact))
    return []


def _apply_update_npc_relationship(state: dict[str, Any], op: dict[str, Any]) -> list[str]:
    npc_id = op["npc_id"]
    rd = op["relationship_delta"]
    for npc in state.setdefault("npcs", []):
        if npc.get("npc_id") == npc_id:
            rel = npc.setdefault("relationship", {})
            if "trust" in rd:
                rel["trust"] = _clamp01(rel.get("trust", 0.0) + rd["trust"])
            return []
    return [f"update_npc_relationship: npc_id={npc_id!r} not found in npcs"]


def _apply_add_temporary_sample(state: dict[str, Any], op: dict[str, Any]) -> list[str]:
    sample = op["sample"]
    samples = state.setdefault("research", {}).setdefault("temporary_samples", [])
    sample_id = sample.get("sample_id")
    for existing in samples:
        if existing.get("sample_id") == sample_id:
            # already exists; do not duplicate
            return []
    samples.append(deepcopy(sample))
    return []


def _apply_set_progress_phase(state: dict[str, Any], op: dict[str, Any]) -> list[str]:
    phase = op["phase"]
    state.setdefault("progress", {})["phase"] = phase
    return []


def _apply_adjust_global_state(state: dict[str, Any], op: dict[str, Any]) -> list[str]:
    field = op["field"]
    delta = op["amount_delta"]
    gs = state.setdefault("global_state", {})
    if field not in gs:
        return [f"adjust_global_state: field={field!r} not present in global_state"]
    gs[field] = _clamp01(gs[field] + delta)
    return []


_OP_APPLIERS = {
    "append_event": _apply_append_event,
    "set_map_node_state": _apply_set_map_node_state,
    "adjust_resource": _apply_adjust_resource,
    "set_flag": _apply_set_flag,
    "unlock_fact": _apply_unlock_fact,
    "update_npc_relationship": _apply_update_npc_relationship,
    "add_temporary_sample": _apply_add_temporary_sample,
    "set_progress_phase": _apply_set_progress_phase,
    "adjust_global_state": _apply_adjust_global_state,
}


def apply_delta(state: dict[str, Any], delta: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Apply a validated delta to a validated state.

    Returns (next_state, apply_errors). The input state is not mutated; a deep
    copy is returned as next_state.
    """
    next_state = deepcopy(state)
    apply_errors: list[str] = []
    for i, op in enumerate(delta.get("operations", [])):
        op_name = op.get("op")
        applier = _OP_APPLIERS.get(op_name)
        if applier is None:
            # Should be unreachable because the delta was validated first, but
            # guard anyway: never silently skip an unknown op.
            apply_errors.append(
                f"operations[{i}].op={op_name!r} has no applier (should have "
                f"been rejected by the validator)"
            )
            continue
        apply_errors.extend(applier(next_state, op))
    # worldbook_id must never change as a side effect of applying a delta.
    if next_state.get("worldbook_id") != state.get("worldbook_id"):
        apply_errors.append(
            "worldbook_id must not change as a result of applying a delta"
        )
        next_state["worldbook_id"] = state["worldbook_id"]
    # run_id must never change either.
    if next_state.get("run_id") != state.get("run_id"):
        apply_errors.append(
            "run_id must not change as a result of applying a delta"
        )
        next_state["run_id"] = state["run_id"]
    return next_state, apply_errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply a WorldStateDelta v0.1 to a RunWorldState v0.1 "
        "deterministically and write the next state."
    )
    parser.add_argument("state", help="Path to the input RunWorldState JSON file.")
    parser.add_argument("delta", help="Path to the WorldStateDelta JSON file.")
    parser.add_argument("output", help="Path to write the next RunWorldState JSON file.")
    args = parser.parse_args()

    state_path = Path(args.state)
    delta_path = Path(args.delta)
    output_path = Path(args.output)

    # --- load + validate state ---
    try:
        state = load_json(state_path)
    except FileNotFoundError:
        print("INVALID apply: state file not found:", state_path)
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID apply: state is not valid JSON:", exc)
        return 1

    state_errors = _full_state_validation(state)
    if state_errors:
        print("INVALID RunWorldState (input)")
        for e in state_errors:
            print(f"- {e}")
        return 1

    # --- load + validate delta ---
    try:
        delta = load_json(delta_path)
    except FileNotFoundError:
        print("INVALID apply: delta file not found:", delta_path)
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID apply: delta is not valid JSON:", exc)
        return 1

    delta_errors = _full_delta_validation(delta)
    if delta_errors:
        print("INVALID WorldStateDelta (input)")
        for e in delta_errors:
            print(f"- {e}")
        return 1

    # --- run_id / worldbook_id consistency ---
    if delta.get("run_id") != state.get("run_id"):
        print(
            "INVALID apply: delta.run_id "
            f"({delta.get('run_id')!r}) does not match state.run_id "
            f"({state.get('run_id')!r})"
        )
        return 1
    if delta.get("worldbook_id") != state.get("worldbook_id"):
        print(
            "INVALID apply: delta.worldbook_id "
            f"({delta.get('worldbook_id')!r}) does not match state.worldbook_id "
            f"({state.get('worldbook_id')!r})"
        )
        return 1

    # --- apply ---
    next_state, apply_errors = apply_delta(state, delta)
    if apply_errors:
        print("INVALID apply: errors while applying operations")
        for e in apply_errors:
            print(f"- {e}")
        return 1

    # --- re-validate next state ---
    next_errors = _full_state_validation(next_state)
    if next_errors:
        print("INVALID RunWorldState (output after apply)")
        for e in next_errors:
            print(f"- {e}")
        return 1

    # --- write ---
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(next_state, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    print(
        f"OK: applied {len(delta.get('operations', []))} operations, "
        f"next state written to {output_path}"
    )
    print(f"- run_id: {next_state.get('run_id')}")
    print(f"- worldbook_id: {next_state.get('worldbook_id')}")
    print(f"- phase: {next_state.get('progress', {}).get('phase')}")
    print(f"- events: {len(next_state.get('event_log', []))}")
    print(f"- unlocked_facts: {len(next_state.get('unlocked_facts', []))}")
    print(
        f"- temporary_samples: "
        f"{len(next_state.get('research', {}).get('temporary_samples', []))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
