#!/usr/bin/env python3
"""Validate a Proposal v0.1 file without third-party dependencies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


MODES = {"runtime_safe", "runtime_experimental", "studio_mode"}
ASSET_TYPES = {"tower_blueprint", "support_item", "temporary_mod", "intel_asset"}
EXPECTED_EFFECTS = {"damage", "control", "support", "scouting", "economy", "defense", "risk"}
RISK_LEVELS = {"low", "medium", "high", "unstable"}
ESTIMATED_COSTS = {"low", "medium", "high"}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate(proposal: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = (
        "id",
        "mode",
        "title",
        "summary",
        "intended_asset_type",
        "expected_effect",
        "risk_level",
        "estimated_cost",
        "required_inputs",
        "known_tradeoffs",
        "player_prompt",
        "worldbook_id",
    )
    for key in required:
        if key not in proposal:
            errors.append(f"missing key: {key}")

    if proposal.get("mode") not in MODES:
        errors.append(f"mode must be one of {sorted(MODES)}")
    if proposal.get("intended_asset_type") not in ASSET_TYPES:
        errors.append(f"intended_asset_type must be one of {sorted(ASSET_TYPES)}")
    if proposal.get("risk_level") not in RISK_LEVELS:
        errors.append(f"risk_level must be one of {sorted(RISK_LEVELS)}")
    if proposal.get("estimated_cost") not in ESTIMATED_COSTS:
        errors.append(f"estimated_cost must be one of {sorted(ESTIMATED_COSTS)}")

    expected_effect = proposal.get("expected_effect")
    if not isinstance(expected_effect, list) or not expected_effect:
        errors.append("expected_effect must be a non-empty array")
    else:
        for index, effect in enumerate(expected_effect):
            if effect not in EXPECTED_EFFECTS:
                errors.append(f"expected_effect[{index}]={effect!r} is not allowed")

    required_inputs = proposal.get("required_inputs")
    if not isinstance(required_inputs, dict):
        errors.append("required_inputs must be an object")

    known_tradeoffs = proposal.get("known_tradeoffs")
    if not isinstance(known_tradeoffs, list):
        errors.append("known_tradeoffs must be an array")

    for key in ("id", "title", "summary", "player_prompt", "worldbook_id"):
        if not proposal.get(key):
            errors.append(f"{key} must be non-empty")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("proposal", help="Path to a Proposal JSON file.")
    args = parser.parse_args()

    proposal_path = Path(args.proposal)
    proposal = load_json(proposal_path)
    if not isinstance(proposal, dict):
        print("INVALID Proposal")
        print("- proposal root must be an object")
        return 1

    errors = validate(proposal)
    if errors:
        print("INVALID Proposal")
        for error in errors:
            print(f"- {error}")
        return 1

    print("OK Proposal")
    print(f"- proposal: {proposal_path}")
    print(f"- intended_asset_type: {proposal['intended_asset_type']}")
    print(f"- expected_effect: {', '.join(proposal['expected_effect'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

