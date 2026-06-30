#!/usr/bin/env python3
"""Validate a CompiledAssetCandidate against the v0.1 effect registry.

This intentionally avoids third-party dependencies. It is not a full JSON
Schema validator; it checks the project-specific contract that matters most
for AI output: top-level sections, asset type, lifecycle, mode, effect
whitelist membership, required effect fields, numeric ranges, and allowed
asset-type usage.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = ROOT / "shared/module_registry/effect_blocks.v0.1.json"

LIFECYCLES = {"ephemeral", "session_blueprint", "stabilized_blueprint"}
ASSET_TYPES = {"tower_blueprint", "support_item", "temporary_mod", "intel_asset"}
MODES = {"runtime_safe", "runtime_experimental", "studio_mode"}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def require_object(value: Any, path: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{path} must be an object")
        return {}
    return value


def check_number_range(value: Any, minimum: float, maximum: float, path: str, errors: list[str]) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        errors.append(f"{path} must be a number")
        return
    if value < minimum or value > maximum:
        errors.append(f"{path}={value} is outside [{minimum}, {maximum}]")


def validate(candidate: dict[str, Any], registry: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    for key in ("id", "lifecycle", "gameplay", "presentation", "provenance"):
        if key not in candidate:
            errors.append(f"missing top-level key: {key}")

    if candidate.get("lifecycle") not in LIFECYCLES:
        errors.append(f"lifecycle must be one of {sorted(LIFECYCLES)}")

    candidate_id = candidate.get("id")
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        errors.append("id must be a non-empty string")
    elif candidate_id.startswith("proposal_"):
        errors.append("id must be a compiled asset id, not a proposal id")

    gameplay = require_object(candidate.get("gameplay"), "gameplay", errors)
    presentation = require_object(candidate.get("presentation"), "presentation", errors)
    provenance = require_object(candidate.get("provenance"), "provenance", errors)

    asset_type = gameplay.get("asset_type")
    if asset_type not in ASSET_TYPES:
        errors.append(f"gameplay.asset_type must be one of {sorted(ASSET_TYPES)}")

    if not presentation.get("name"):
        errors.append("presentation.name is required")
    if not presentation.get("short_description"):
        errors.append("presentation.short_description is required")

    mode = provenance.get("mode")
    if mode not in MODES:
        errors.append(f"provenance.mode must be one of {sorted(MODES)}")
    if not provenance.get("worldbook_id"):
        errors.append("provenance.worldbook_id is required")
    if isinstance(candidate_id, str) and candidate_id == provenance.get("proposal_id"):
        errors.append("id must not equal provenance.proposal_id")

    effects = gameplay.get("effect_blocks")
    if not isinstance(effects, list) or not effects:
        errors.append("gameplay.effect_blocks must be a non-empty array")
        return errors

    registry_effects = registry.get("effect_blocks", {})
    if not isinstance(registry_effects, dict):
        errors.append("registry.effect_blocks must be an object")
        return errors

    for index, effect in enumerate(effects):
        effect_path = f"gameplay.effect_blocks[{index}]"
        if not isinstance(effect, dict):
            errors.append(f"{effect_path} must be an object")
            continue
        effect_type = effect.get("type")
        if not effect_type:
            errors.append(f"{effect_path}.type is required")
            continue
        spec = registry_effects.get(effect_type)
        if spec is None:
            errors.append(f"{effect_path}.type={effect_type!r} is not in the v0.1 whitelist")
            continue

        allowed_asset_types = spec.get("allowed_asset_types", [])
        if asset_type in ASSET_TYPES and asset_type not in allowed_asset_types:
            errors.append(f"{effect_path}.type={effect_type!r} is not allowed for asset_type={asset_type!r}")

        for field in spec.get("required_fields", []):
            if field not in effect:
                errors.append(f"{effect_path}.{field} is required for effect {effect_type!r}")

        numeric_ranges = spec.get("numeric_ranges", {})
        if isinstance(numeric_ranges, dict):
            for field, limits in numeric_ranges.items():
                if field in effect and isinstance(limits, list) and len(limits) == 2:
                    check_number_range(effect[field], limits[0], limits[1], f"{effect_path}.{field}", errors)

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", help="Path to a CompiledAssetCandidate JSON file.")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY), help="Path to effect registry JSON.")
    args = parser.parse_args()

    candidate_path = Path(args.candidate)
    registry_path = Path(args.registry)
    candidate = require_object(load_json(candidate_path), str(candidate_path), [])
    registry = require_object(load_json(registry_path), str(registry_path), [])

    errors = validate(candidate, registry)
    if errors:
        print("INVALID CompiledAssetCandidate")
        for error in errors:
            print(f"- {error}")
        return 1

    print("OK CompiledAssetCandidate")
    print(f"- candidate: {candidate_path}")
    print(f"- registry: {registry_path}")
    print(f"- effects: {len(candidate['gameplay']['effect_blocks'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
