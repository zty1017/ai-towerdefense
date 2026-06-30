#!/usr/bin/env python3
"""Build a player-safe frontend mock content pack from compiled assets.

The pack is intended for frontend/backend parallel development. It embeds
world, map, NPC, story, and compiled playable assets while stripping provider,
model, prompt, and raw trace fields from frontend-facing data.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import asset_promotion_policy
import score_asset_candidate
import simulate_asset_candidate
import validate_asset_candidate


ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_FRONTEND_KEYS = {
    "provider",
    "model",
    "raw_prompt",
    "full_trace",
    "raw_json",
    "api_key",
    "secret",
    "unreviewed_content",
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def visual_recipe_for_effect(effect: dict[str, Any], index: int) -> dict[str, Any] | None:
    effect_type = str(effect.get("type", ""))
    if effect_type == "slow":
        return {
            "recipe_id": f"visual_slow_{index}",
            "type": "aura_field",
            "palette": "cold_blue",
            "summary": "冷蓝色减速光场，作用于范围内敌人。"
        }
    if effect_type == "aura_buff":
        return {
            "recipe_id": f"visual_aura_{index}",
            "type": "ring_pulse",
            "palette": "cold_blue",
            "summary": "从塔底向外扩散的环形灯纹。"
        }
    if effect_type == "area_damage":
        return {
            "recipe_id": f"visual_area_damage_{index}",
            "type": "particle_burst",
            "palette": "red_orange",
            "summary": "范围命中时爆开短促粒子。"
        }
    if effect_type == "damage":
        return {
            "recipe_id": f"visual_damage_{index}",
            "type": "sprite_flash",
            "palette": "warm_gold",
            "summary": "命中时短促闪光。"
        }
    if effect_type == "shield":
        return {
            "recipe_id": f"visual_shield_{index}",
            "type": "aura_field",
            "palette": "warm_gold",
            "summary": "保护目标周围形成暖金色护幕。"
        }
    if effect_type == "repair":
        return {
            "recipe_id": f"visual_repair_{index}",
            "type": "floating_text",
            "palette": "white",
            "summary": "维修触发时显示短暂恢复反馈。"
        }
    if effect_type == "pierce_or_chain":
        return {
            "recipe_id": f"visual_chain_{index}",
            "type": "chain_arc",
            "palette": "red_orange",
            "summary": "过载能量在多个目标间跳转。"
        }
    if effect_type == "charge_burst":
        return {
            "recipe_id": f"visual_burst_{index}",
            "type": "particle_burst",
            "palette": "red_orange",
            "summary": "短时蓄能后爆发火花。"
        }
    if effect_type == "trap_tile_effect":
        return {
            "recipe_id": f"visual_trap_{index}",
            "type": "ring_pulse",
            "palette": "warm_gold",
            "summary": "地面陷阱触发时亮起灯纹。"
        }
    if effect_type in {"scout_reveal", "path_prediction", "threat_forecast"}:
        return {
            "recipe_id": f"visual_intel_{index}",
            "type": "floating_text",
            "palette": "white",
            "summary": "地图上浮现短暂情报标记。"
        }
    if effect_type == "weakness_tag":
        return {
            "recipe_id": f"visual_weakness_{index}",
            "type": "sprite_flash",
            "palette": "white",
            "summary": "目标弱点被短暂描边。"
        }
    if effect_type == "countermeasure_hint":
        return {
            "recipe_id": f"visual_countermeasure_{index}",
            "type": "floating_text",
            "palette": "white",
            "summary": "路径附近浮现短暂战术提示。"
        }
    if effect_type == "risk_modifier":
        return {
            "recipe_id": f"visual_risk_modifier_{index}",
            "type": "screen_shake",
            "palette": "cold_blue",
            "summary": "威胁压力变化时触发轻量反馈。"
        }
    return None


def visual_recipes(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    effects = as_list(as_obj(candidate.get("gameplay")).get("effect_blocks"))
    recipes: list[dict[str, Any]] = []
    for index, effect in enumerate(effects):
        if not isinstance(effect, dict):
            continue
        recipe = visual_recipe_for_effect(effect, index)
        if recipe:
            recipes.append(recipe)
    if not recipes:
        recipes.append({
            "recipe_id": "visual_default_flash",
            "type": "sprite_flash",
            "palette": "warm_gold",
            "summary": "默认命中反馈。"
        })
    return recipes


def frontend_usage(asset_type: str) -> dict[str, Any]:
    if asset_type == "tower_blueprint":
        return {
            "workshop_slot": "tower",
            "battle_toolbar": True,
            "deployment_surface": "tower_socket",
            "ui_pages": ["workshop", "battle", "settlement"]
        }
    if asset_type == "support_item":
        return {
            "workshop_slot": "item",
            "battle_toolbar": True,
            "deployment_surface": "ground_tile",
            "ui_pages": ["workshop", "battle", "settlement"]
        }
    if asset_type == "temporary_mod":
        return {
            "workshop_slot": "mod",
            "battle_toolbar": True,
            "deployment_surface": "existing_tower",
            "ui_pages": ["workshop", "battle", "settlement"]
        }
    return {
        "workshop_slot": "intel",
        "battle_toolbar": False,
        "deployment_surface": "map_overlay",
        "ui_pages": ["world_map", "workshop", "battle"]
    }


def fallback_media(candidate: dict[str, Any], promotion: dict[str, Any]) -> dict[str, Any]:
    asset_type = str(as_obj(candidate.get("gameplay")).get("asset_type", "unknown"))
    tags = as_list(as_obj(candidate.get("presentation")).get("visual_tags"))
    return {
        "mode": "fallback" if promotion.get("uses_fallback_media") else "generated_or_fallback",
        "icon_token": f"fallback_icon.{asset_type}",
        "sprite_token": f"fallback_sprite.{asset_type}",
        "palette_hint": tags[:4] or ["warm_gold", "cold_blue"],
        "readiness": promotion.get("promotion_state"),
        "note": "前端可用内置形状、色板和 visual_recipes 渲染占位资产。"
    }


def build_compiled_asset_entry(candidate: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    validation_errors = validate_asset_candidate.validate(candidate, registry)
    validation = {
        "status": "passed" if not validation_errors else "failed",
        "errors": validation_errors,
        "candidate_id": candidate.get("id"),
    }
    simulation = simulate_asset_candidate.simulate(candidate, simulate_asset_candidate.DEFAULT_DURATION_SECONDS)
    score = score_asset_candidate.score_candidate(
        candidate,
        validation=validation,
        simulation=simulation,
        media_metadata=None,
    )
    promotion = asset_promotion_policy.evaluate_promotion(
        candidate,
        validation=validation,
        simulation=simulation,
        candidate_score=score,
        runtime_readiness=None,
    )
    gameplay = as_obj(candidate.get("gameplay"))
    presentation = as_obj(candidate.get("presentation"))
    asset_type = str(gameplay.get("asset_type", "unknown"))
    return {
        "stable_internal_id": candidate.get("id"),
        "asset_type": asset_type,
        "lifecycle": candidate.get("lifecycle"),
        "display": {
            "name": presentation.get("name"),
            "summary": presentation.get("short_description"),
            "tags": as_list(presentation.get("visual_tags")),
            "rarity_hint": presentation.get("rarity_hint", "prototype")
        },
        "gameplay": gameplay,
        "visual_recipes": visual_recipes(candidate),
        "media_refs": fallback_media(candidate, promotion),
        "promotion": {
            "promotion_state": promotion.get("promotion_state"),
            "playable": promotion.get("playable"),
            "uses_fallback_media": promotion.get("uses_fallback_media"),
            "required_next_actions": promotion.get("required_next_actions"),
        },
        "compiler_reports": {
            "validation": validation,
            "simulation": {
                "simulation_focus": simulation.get("simulation_focus"),
                "estimated_dps": simulation.get("estimated_dps"),
                "utility_score": simulation.get("utility_score"),
                "cost_efficiency": simulation.get("cost_efficiency"),
                "balance_flags": simulation.get("balance_flags"),
            },
            "score": {
                "total_score": score.get("total_score"),
                "recommendation": score.get("recommendation"),
                "reasons": score.get("reasons"),
                "expected_media_roles": score.get("expected_media_roles"),
            }
        },
        "frontend_usage": frontend_usage(asset_type),
    }


def build_story(opening: dict[str, Any], first_crisis: dict[str, Any]) -> dict[str, Any]:
    return {
        "opening": opening,
        "questline": [
            {
                "quest_id": "quest_first_crisis",
                "display_name": "驰援灰灯驿站",
                "state": "active",
                "target_node_id": first_crisis.get("node_id"),
                "summary": first_crisis.get("summary"),
                "steps": [
                    "进入灰灯驿站",
                    "查看威胁与保护目标",
                    "提交一个现场试作构想",
                    "守住第一波影潮",
                    "查看战后反馈与世界状态变化"
                ]
            }
        ],
        "battle_dialogue_beats": [
            {
                "beat_id": "battle_intro",
                "speaker_id": "npc_gray_lantern_keeper",
                "line": "影潮已经靠近东南路口，信标还亮着，但撑不了太久。"
            },
            {
                "beat_id": "research_delivery",
                "speaker_id": "npc_workshop_mentor",
                "line": "样品封装完了。别指望它漂亮，能拖住影潮才算数。"
            },
            {
                "beat_id": "settlement",
                "speaker_id": "npc_gray_lantern_keeper",
                "line": "灰灯还亮着。我们有时间把这次试作记录下来。"
            }
        ]
    }


def scan_forbidden_keys(value: Any, path: str = "") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key in FORBIDDEN_FRONTEND_KEYS:
                errors.append(f"forbidden frontend key: {child_path}")
            errors.extend(scan_forbidden_keys(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(scan_forbidden_keys(child, f"{path}[{index}]"))
    return errors


def build_pack(created_at: str) -> dict[str, Any]:
    registry = load_json(ROOT / "shared/module_registry/effect_blocks.v0.1.json")
    worldbook = load_json(ROOT / "content/worldbooks/long_night_lanterns/worldbook.json")
    npcs = load_json(ROOT / "content/worldbooks/long_night_lanterns/npcs.json")
    materials = load_json(ROOT / "content/worldbooks/long_night_lanterns/materials.json")
    opening = load_json(ROOT / "content/worldbooks/long_night_lanterns/opening.json")
    initial_map = load_json(ROOT / "game_data/demo/initial_map.json")
    first_crisis = load_json(ROOT / "game_data/demo/first_crisis_node.json")
    run_world_state = load_json(ROOT / "examples/run_world_states/demo_initial.run_world_state.json")

    asset_paths = sorted((ROOT / "examples/compiled_assets").glob("*.compiled_asset.json"))
    assets = [
        build_compiled_asset_entry(load_json(path), registry)
        for path in asset_paths
    ]
    playable_count = sum(1 for asset in assets if asset["promotion"].get("playable"))
    by_type: dict[str, int] = {}
    for asset in assets:
        by_type[asset["asset_type"]] = by_type.get(asset["asset_type"], 0) + 1

    return {
        "schema_version": "frontend_mock_pack.v0.1",
        "pack_id": "frontend_mock_pack_long_night_lanterns_v0_1",
        "created_at": created_at,
        "worldbook_id": "long_night_lanterns",
        "compiler_summary": {
            "asset_count": len(assets),
            "playable_count": playable_count,
            "asset_count_by_type": by_type,
            "promotion_states": {
                state: sum(1 for asset in assets if asset["promotion"].get("promotion_state") == state)
                for state in ("runtime_ready", "fallback_ready", "preview_only", "failed")
            },
            "pipeline": [
                "compiled_asset",
                "validate_candidate",
                "simulate_candidate",
                "score_candidate",
                "evaluate_promotion_policy"
            ],
            "media_policy": "Generated media is optional for mock pack; fallback media tokens guarantee frontend renderability."
        },
        "frontend_contract": {
            "first_screen": "local_profile_or_world_start",
            "primary_flow": ["opening", "world_map", "node_briefing", "workshop", "battle", "settlement"],
            "runtime_assumption": "Every asset with promotion.playable=true can be rendered with fallback media tokens and visual_recipes.",
            "forbidden_player_terms": worldbook.get("tone_and_taboos", {}).get("forbidden_terms_in_player_text", []),
        },
        "world": {
            "display_name": worldbook.get("display_name"),
            "summary": worldbook.get("summary"),
            "tone_and_taboos": worldbook.get("tone_and_taboos"),
            "visual_rules": worldbook.get("visual_rules"),
            "run_world_state": run_world_state,
        },
        "map": {
            "initial_map": initial_map,
            "first_crisis_node": first_crisis,
        },
        "npcs": as_list(npcs.get("npcs")),
        "materials": as_list(materials.get("materials")),
        "story": build_story(opening, first_crisis),
        "assets": assets,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="examples/frontend_mock/frontend_mock_pack.v0.1.json")
    parser.add_argument("--created-at", default="2026-07-01T00:00:00+08:00")
    args = parser.parse_args()

    pack = build_pack(args.created_at)
    errors = scan_forbidden_keys(pack)
    if errors:
        for error in errors:
            print(error)
        return 1
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    write_json(output, pack)
    print(f"Wrote {output}")
    print(f"- assets: {pack['compiler_summary']['asset_count']}")
    print(f"- playable: {pack['compiler_summary']['playable_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
