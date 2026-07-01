#!/usr/bin/env python3
"""Replay the MVP WorldStateDelta chain and optionally compare the final state.

This is an offline verification helper for review. It does not read .env and
does not call providers.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _common import load_json  # noqa: E402
from apply_world_delta import apply_delta  # noqa: E402
from validate_run_world_state import (  # noqa: E402
    validate_run_world_state,
    validate_with_jsonschema as validate_state_with_jsonschema,
)
from validate_world_delta import (  # noqa: E402
    validate_world_delta,
    validate_with_jsonschema as validate_delta_with_jsonschema,
)
from validate_world_delta_semantics import (  # noqa: E402
    DEFAULT_REVIEW_PACK,
    build_reference_registry,
    validate_world_delta_semantics,
)


DEFAULT_INITIAL_STATE = ROOT / "examples/run_world_states/demo_initial.run_world_state.json"
DEFAULT_EXPECTED_FINAL_STATE = (
    ROOT / "examples/run_world_states/demo_after_stage_04_wick_store.run_world_state.json"
)
DEFAULT_OUTPUT = Path("/tmp/mvp_replayed_stage_04_wick_store.run_world_state.json")
DEFAULT_DELTAS = [
    ROOT / "examples/world_deltas/repaired_first_battle_semantic_pass.world_delta.json",
    ROOT / "examples/world_deltas/stage_02_dawn_review_supply_line.world_delta.json",
    ROOT / "examples/world_deltas/stage_03_northern_road_scouting.world_delta.json",
    ROOT / "examples/world_deltas/stage_04_wick_store_pressure_battle.world_delta.json",
]


def _dedupe(errors: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for error in errors:
        if error not in seen:
            seen.add(error)
            out.append(error)
    return out


def _full_state_validation(state: dict[str, Any]) -> list[str]:
    return _dedupe([*validate_state_with_jsonschema(state), *validate_run_world_state(state)])


def _full_delta_validation(delta: dict[str, Any]) -> list[str]:
    return _dedupe([*validate_delta_with_jsonschema(delta), *validate_world_delta(delta)])


def replay_chain(
    initial_state_path: Path,
    delta_paths: list[Path],
    review_pack_path: Path,
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    state = load_json(initial_state_path)
    if not isinstance(state, dict):
        return {}, ["initial state root must be an object"]

    errors.extend(_full_state_validation(state))
    if errors:
        return state, errors

    for index, delta_path in enumerate(delta_paths, start=1):
        delta = load_json(delta_path)
        if not isinstance(delta, dict):
            return state, [f"delta[{index}] root must be an object: {delta_path}"]
        delta_errors = _full_delta_validation(delta)
        if delta_errors:
            return state, [f"{delta_path}: {error}" for error in delta_errors]
        registry = build_reference_registry(state, review_pack_path)
        semantic_errors = validate_world_delta_semantics(delta, state, registry)
        if semantic_errors:
            return state, [f"{delta_path}: {error}" for error in semantic_errors]
        state, apply_errors = apply_delta(state, delta)
        if apply_errors:
            return state, [f"{delta_path}: {error}" for error in apply_errors]
        next_errors = _full_state_validation(state)
        if next_errors:
            return state, [f"{delta_path}: output invalid: {error}" for error in next_errors]

    return state, []


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay MVP WorldStateDelta chain.")
    parser.add_argument("--initial-state", default=str(DEFAULT_INITIAL_STATE))
    parser.add_argument(
        "--delta",
        action="append",
        dest="deltas",
        help="Delta path. Can be supplied multiple times; defaults to the MVP chain.",
    )
    parser.add_argument("--review-pack", default=str(DEFAULT_REVIEW_PACK))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument(
        "--compare-final",
        default=str(DEFAULT_EXPECTED_FINAL_STATE),
        help="Expected final state JSON to compare against. Use empty string to skip.",
    )
    args = parser.parse_args()

    delta_paths = [Path(path) for path in args.deltas] if args.deltas else DEFAULT_DELTAS
    state, errors = replay_chain(
        Path(args.initial_state),
        delta_paths,
        Path(args.review_pack),
    )
    if errors:
        print("INVALID MVP delta chain")
        for error in errors:
            print(f"- {error}")
        return 1

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    if args.compare_final:
        expected = load_json(Path(args.compare_final))
        if state != expected:
            print("INVALID MVP delta chain")
            print(f"- replayed final state does not match {args.compare_final}")
            return 1

    print(f"OK: replayed {len(delta_paths)} deltas")
    print(f"- output: {output_path}")
    print(f"- phase: {state.get('progress', {}).get('phase')}")
    print(f"- tasks: {len(state.get('tasks', []))}")
    print(f"- random_events: {len(state.get('random_events', []))}")
    print(f"- blueprints: {len((state.get('research', {}) or {}).get('known_blueprints', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
