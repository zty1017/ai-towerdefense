"""Prompt helpers for LLM-generated CompiledAssetCandidate artifacts."""

from __future__ import annotations

import json
from typing import Any


SYSTEM_PROMPT = """你是塔防资产编译器。你负责根据研发提案和效果注册表，生成一个 CompiledAssetCandidate v0.1。

你必须只返回一个 JSON 对象，不能返回 Markdown、解释文字或数组。

顶层字段只能且必须包含：
- id
- lifecycle
- gameplay
- presentation
- provenance

id 必须是新的游戏资产内部 ID，不能直接复用 proposal.id，不能以 "proposal_" 开头。
建议使用 "asset_"、"mod_" 或 "intel_" 等清晰前缀。

lifecycle 只允许以下值：
- "ephemeral"
- "session_blueprint"
- "stabilized_blueprint"

gameplay.asset_type 只允许以下值：
- "tower_blueprint"
- "support_item"
- "temporary_mod"
- "intel_asset"

应优先遵循 proposal 中的 intended_asset_type。

effect_blocks 只能使用提供的 effect_registry 中的 effect type。每个 effect 必须包含该 type 的 required_fields，数值必须在 numeric_ranges 内。不要发明新的 effect type。

不同 asset_type 必须填写适合该类型的 base_stats 和 type_specific：
- tower_blueprint: base_stats 建议包含 build_cost、range、cooldown、targeting；type_specific 建议包含 tower_slot、upgrade_from。
- support_item: base_stats 建议包含 deploy_cost、cooldown、use_count 或 charges、cast_range；type_specific 建议包含 item_slot、delivery_method、target_rule。
- temporary_mod: base_stats 建议包含 activation_cost、duration_seconds、cooldown；type_specific 建议包含 target_asset_type、stacking、rollback_behavior。
- intel_asset: base_stats 建议包含 action_cost、valid_turns、confidence；type_specific 建议包含 reveal_mode、applies_to、consumer_hint。

如果资产没有直接伤害，也应通过 scouting、control、defense、risk 等 effect_blocks 表达它对塔防玩法的贡献。

provenance 必须包含以下字段：
- proposal_id
- mode
- worldbook_id
- provider（可填 "selected_profile"，系统会在本地回填）
- model（可填 "selected_model"，系统会在本地回填）
- npc_ids（数组）
- material_ids（数组）
- validation_status（初始填 "pending"）
- simulation_report_id（初始填 null）

不要包含 raw_prompt/full_trace/raw_json/api_key/secret/unreviewed_content 等字段。
"""


def _registry_summary(registry: dict[str, Any]) -> dict[str, Any]:
    effects = registry.get("effect_blocks", {})
    if not isinstance(effects, dict):
        return {}
    summary: dict[str, Any] = {}
    for etype, spec in effects.items():
        if not isinstance(spec, dict):
            continue
        entry: dict[str, Any] = {}
        if spec.get("required_fields"):
            entry["required_fields"] = spec["required_fields"]
        if spec.get("numeric_ranges"):
            entry["numeric_ranges"] = spec["numeric_ranges"]
        if spec.get("allowed_asset_types"):
            entry["allowed_asset_types"] = spec["allowed_asset_types"]
        summary[etype] = entry
    return summary


def build_user_prompt(
    proposal: dict[str, Any],
    effect_registry: dict[str, Any],
) -> str:
    payload: dict[str, Any] = {
        "instruction": "根据以下研发提案和 effect 注册表，生成一个合法的 CompiledAssetCandidate v0.1。",
        "proposal": {
            "id": proposal.get("id"),
            "mode": proposal.get("mode"),
            "title": proposal.get("title"),
            "summary": proposal.get("summary"),
            "intended_asset_type": proposal.get("intended_asset_type"),
            "expected_effect": proposal.get("expected_effect"),
            "risk_level": proposal.get("risk_level"),
            "estimated_cost": proposal.get("estimated_cost"),
            "required_inputs": proposal.get("required_inputs"),
            "known_tradeoffs": proposal.get("known_tradeoffs"),
            "player_prompt": proposal.get("player_prompt"),
            "worldbook_id": proposal.get("worldbook_id"),
        },
        "effect_registry": _registry_summary(effect_registry),
        "example_shape": {
            "id": "asset_light_slow_field",
            "lifecycle": "ephemeral",
            "gameplay": {
                "asset_type": "tower_blueprint",
                "base_stats": {
                    "build_cost": 160,
                    "range": 140,
                    "cooldown": 1.0,
                    "targeting": "nearest",
                },
                "effect_blocks": [
                    {
                        "type": "slow",
                        "slow_ratio": 0.35,
                        "duration": 1.8,
                        "stacking": "refresh",
                    },
                    {
                        "type": "aura_buff",
                        "radius": 110,
                        "target": "enemy",
                        "effect_ref": "slow",
                    },
                    {
                        "type": "power_cost",
                        "power_per_second": 4.0,
                        "shutdown_behavior": "disable_effects",
                    },
                ],
                "constraints": {
                    "requires_power_grid": True,
                    "max_instances": 2,
                    "allowed_phases": ["battle"],
                },
                "type_specific": {
                    "tower_slot": "standard",
                    "upgrade_from": "basic_tower",
                },
            },
            "presentation": {
                "name": "光幕迟滞塔",
                "short_description": "用持续灯光形成减速场，压制高速敌人，但需要稳定供电。",
                "icon_prompt": "2D game icon, compact tower-defense turret with light field, readable silhouette, clean background",
                "animation_card_prompt": "2D animation card for light slow field tower, tower defense strategy game",
                "visual_tags": ["tower_blueprint", "compiled_asset"],
            },
            "provenance": {
                "proposal_id": "proposal_light_slow_field_001",
                "mode": "runtime_safe",
                "worldbook_id": "long_night_lanterns",
                "provider": "live_llm",
                "model": "live_llm",
                "npc_ids": ["engineer_001"],
                "material_ids": ["focusing_lens"],
                "validation_status": "pending",
                "simulation_report_id": None,
            },
        },
        "asset_type_guidance": {
            "support_item": {
                "base_stats": ["deploy_cost", "cooldown", "use_count", "cast_range"],
                "type_specific": ["item_slot", "delivery_method", "target_rule"]
            },
            "temporary_mod": {
                "base_stats": ["activation_cost", "duration_seconds", "cooldown"],
                "type_specific": ["target_asset_type", "stacking", "rollback_behavior"]
            },
            "intel_asset": {
                "base_stats": ["action_cost", "valid_turns", "confidence"],
                "type_specific": ["reveal_mode", "applies_to", "consumer_hint"]
            },
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def normalize_candidate_provenance(
    candidate: dict[str, Any],
    proposal: dict[str, Any],
    *,
    provider: str,
    model: str,
) -> dict[str, Any]:
    """Fill deterministic provenance fields before validation.

    The model is responsible for gameplay/presentation structure, but these
    fields are known locally and should not depend on model memory.
    """
    provenance = candidate.get("provenance")
    if not isinstance(provenance, dict):
        return candidate
    required_inputs = proposal.get("required_inputs")
    if not isinstance(required_inputs, dict):
        required_inputs = {}
    npc_ids = required_inputs.get("npc_ids")
    material_ids = required_inputs.get("materials")
    provenance.update(
        {
            "proposal_id": proposal.get("id"),
            "mode": proposal.get("mode"),
            "worldbook_id": proposal.get("worldbook_id"),
            "provider": provider,
            "model": model,
            "npc_ids": npc_ids if isinstance(npc_ids, list) else [],
            "material_ids": material_ids if isinstance(material_ids, list) else [],
            "validation_status": "pending",
            "simulation_report_id": None,
        }
    )
    return candidate
