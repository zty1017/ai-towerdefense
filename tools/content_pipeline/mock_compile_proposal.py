#!/usr/bin/env python3
"""Compile a Proposal v0.1 into a conservative CompiledAssetCandidate.

This is a deterministic placeholder for the future LLM compiler. Its job is
to prove the pipeline shape: Proposal -> CompiledAssetCandidate -> validation.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def slug_from_id(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_").lower()
    if slug.startswith("proposal_"):
        slug = slug[len("proposal_") :]
    return slug or "compiled_asset"


def collect_required_inputs(proposal: dict[str, Any], key: str) -> list[str]:
    required_inputs = proposal.get("required_inputs")
    if not isinstance(required_inputs, dict):
        return []
    values = required_inputs.get(key)
    if not isinstance(values, list):
        return []
    return [str(value) for value in values]


def compile_tower(proposal: dict[str, Any]) -> dict[str, Any]:
    text = " ".join(
        str(proposal.get(key, ""))
        for key in ("title", "summary", "player_prompt")
    )
    expected = set(proposal.get("expected_effect", []))
    effects: list[dict[str, Any]] = []

    if "control" in expected or "减速" in text or "slow" in text.lower():
        effects.append({
            "type": "slow",
            "slow_ratio": 0.35,
            "duration": 1.8,
            "stacking": "refresh"
        })
        effects.append({
            "type": "aura_buff",
            "radius": 110,
            "target": "enemy",
            "effect_ref": "slow"
        })

    if "damage" in expected or "伤害" in text:
        effects.append({
            "type": "damage",
            "amount": 24,
            "damage_type": "kinetic"
        })

    if "support" in expected or "电" in text or "power" in text.lower():
        effects.append({
            "type": "power_cost",
            "power_per_second": 4,
            "shutdown_behavior": "disable_effects"
        })

    if not effects:
        effects.append({
            "type": "damage",
            "amount": 18,
            "damage_type": "generic"
        })

    return {
        "asset_type": "tower_blueprint",
        "base_stats": {
            "build_cost": 160,
            "range": 140,
            "cooldown": 1.0,
            "targeting": "nearest"
        },
        "effect_blocks": effects,
        "constraints": {
            "requires_power_grid": any(effect["type"] == "power_cost" for effect in effects),
            "max_instances": 2,
            "allowed_phases": ["battle"]
        },
        "type_specific": {
            "tower_slot": "standard",
            "upgrade_from": "basic_tower"
        }
    }


def compile_support_item(proposal: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset_type": "support_item",
        "base_stats": {
            "deploy_cost": 35,
            "use_count": 1,
            "cooldown": 0
        },
        "effect_blocks": [
            {
                "type": "scout_reveal",
                "reveal_scope": "next_wave"
            },
            {
                "type": "countermeasure_hint",
                "hint_scope": "current_node"
            }
        ],
        "constraints": {
            "allowed_phases": ["preparation"]
        },
        "type_specific": {
            "item_slot": "tactical",
            "delivery_method": "pre_battle_consumable",
            "target_rule": "current_node_or_next_wave"
        }
    }


def compile_temporary_mod(proposal: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset_type": "temporary_mod",
        "base_stats": {
            "activation_cost": 45,
            "duration_seconds": 20,
            "cooldown": 60
        },
        "effect_blocks": [
            {
                "type": "charge_burst",
                "charge_seconds": 4,
                "burst_multiplier": 1.8
            },
            {
                "type": "risk_modifier",
                "risk_delta": 10
            }
        ],
        "constraints": {
            "allowed_phases": ["battle"]
        },
        "type_specific": {
            "attach_to": "tower",
            "target_asset_type": "tower_blueprint",
            "stacking": "replace_same_source",
            "rollback_behavior": "expire_and_restore_base_tower"
        }
    }


def compile_intel_asset(proposal: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset_type": "intel_asset",
        "base_stats": {
            "action_cost": 1,
            "valid_turns": 1,
            "confidence": 0.65
        },
        "effect_blocks": [
            {
                "type": "scout_reveal",
                "reveal_scope": "next_wave"
            },
            {
                "type": "weakness_tag",
                "tag_key": "light_sensitive",
                "confidence": 0.65
            },
            {
                "type": "path_prediction",
                "prediction_horizon": 2
            }
        ],
        "constraints": {
            "allowed_phases": ["preparation"]
        },
        "type_specific": {
            "intel_channel": "scout_report",
            "reveal_mode": "next_wave_preview",
            "applies_to": "current_node",
            "consumer_hint": "show_countermeasure_tags"
        }
    }


def gameplay_for(proposal: dict[str, Any]) -> dict[str, Any]:
    asset_type = proposal.get("intended_asset_type")
    if asset_type == "tower_blueprint":
        return compile_tower(proposal)
    if asset_type == "support_item":
        return compile_support_item(proposal)
    if asset_type == "temporary_mod":
        return compile_temporary_mod(proposal)
    if asset_type == "intel_asset":
        return compile_intel_asset(proposal)
    raise ValueError(f"unsupported intended_asset_type: {asset_type!r}")


def presentation_for(proposal: dict[str, Any], gameplay: dict[str, Any]) -> dict[str, Any]:
    title = str(proposal.get("title") or "未命名方案")
    summary = str(proposal.get("summary") or "由研发提案编译出的资产候选。")
    asset_type = gameplay.get("asset_type")
    if asset_type == "tower_blueprint":
        icon_prompt = "2D game icon, compact tower-defense turret, readable silhouette, clean background"
    elif asset_type == "intel_asset":
        icon_prompt = "2D game icon, folded scout report with glowing marks, clean background"
    elif asset_type == "support_item":
        icon_prompt = "2D game icon, tactical support device, clean background"
    else:
        icon_prompt = "2D game icon, unstable modification module, clean background"

    return {
        "name": title.replace("方案", "资产"),
        "short_description": summary,
        "icon_prompt": icon_prompt,
        "animation_card_prompt": f"2D animation card for {title}, tower defense strategy game",
        "visual_tags": [str(gameplay.get("asset_type")), "compiled_asset"]
    }


def compile_candidate(proposal: dict[str, Any], provider: str | None, model: str | None) -> dict[str, Any]:
    slug = slug_from_id(str(proposal.get("id", "proposal")))
    gameplay = gameplay_for(proposal)
    return {
        "id": f"asset_{slug}",
        "lifecycle": "ephemeral",
        "gameplay": gameplay,
        "presentation": presentation_for(proposal, gameplay),
        "provenance": {
            "proposal_id": proposal.get("id"),
            "mode": proposal.get("mode"),
            "worldbook_id": proposal.get("worldbook_id"),
            "provider": provider or "mock",
            "model": model or "mock_compiler_v0.1",
            "npc_ids": collect_required_inputs(proposal, "npc_ids"),
            "material_ids": collect_required_inputs(proposal, "materials"),
            "validation_status": "pending",
            "simulation_report_id": None
        }
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("proposal", help="Path to a Proposal JSON file.")
    parser.add_argument("--output", help="Write the compiled candidate to this path. Defaults to stdout.")
    parser.add_argument("--provider", default="mock")
    parser.add_argument("--model", default="mock_compiler_v0.1")
    args = parser.parse_args()

    proposal = load_json(Path(args.proposal))
    if not isinstance(proposal, dict):
        print("Proposal root must be an object")
        return 1

    candidate = compile_candidate(proposal, args.provider, args.model)
    if args.output:
        output_path = Path(args.output)
        write_json(output_path, candidate)
        print(f"Wrote {output_path}")
    else:
        print(json.dumps(candidate, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
