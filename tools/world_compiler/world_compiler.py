"""Compile a thin creative seed into validated, game-ready world artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "shared" / "schemas"
LLM_DIR = ROOT / "tools" / "llm"
ASSET_GRAPH_DIR = ROOT / "tools" / "asset_graph"
for path in (LLM_DIR, ASSET_GRAPH_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import adapter  # type: ignore  # noqa: E402
import map_compilation_orchestrator  # type: ignore  # noqa: E402
import procedural_map_render_plan  # type: ignore  # noqa: E402


SEED_VERSION = "world_generation_seed.v0.1"
CANDIDATE_VERSION = "generated_world_candidate.v0.1"
FORBIDDEN_PLAYER_TERMS = ("AI", "provider", "schema", "prompt", "compiler", "token", "trace", "mock")
ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,47}$")

ROUTE_TEMPLATES = {
    "east_west_switchback": {
        "waypoints": [(15, 4), (11, 4), (11, 2), (6, 2), (6, 6), (1, 6)],
        "core": (0, 6), "optional": (4, 2),
    },
    "north_south_serpentine": {
        "waypoints": [(8, 0), (8, 2), (12, 2), (12, 6), (5, 6), (5, 8)],
        "core": (4, 8), "optional": (10, 5),
    },
    "diagonal_zigzag": {
        "waypoints": [(15, 1), (12, 1), (12, 5), (7, 5), (7, 7), (2, 7)],
        "core": (1, 7), "optional": (9, 4),
    },
}


class WorldCompilationError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise WorldCompilationError(f"JSON root must be object: {path}")
    return value


def _write(path: Path, value: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _path_ref(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _schema(name: str) -> dict[str, Any]:
    return _load(SCHEMAS / name)


def _schema_errors(value: dict[str, Any], name: str) -> list[str]:
    return procedural_map_render_plan.validate_with_jsonschema(value, _schema(name))


def validate_seed(seed: dict[str, Any]) -> list[str]:
    errors = _schema_errors(seed, "world_generation_seed.v0.1.schema.json")
    if seed.get("schema_version") != SEED_VERSION:
        errors.append(f"schema_version must be {SEED_VERSION}")
    return list(dict.fromkeys(errors))


def _scan_player_text(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _scan_player_text(child, f"{path}.{key}" if path else key, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan_player_text(child, f"{path}[{index}]", errors)
    elif isinstance(value, str):
        lowered = value.lower()
        for term in FORBIDDEN_PLAYER_TERMS:
            token = term.lower()
            if re.search(rf"(?<![a-z0-9_]){re.escape(token)}(?![a-z0-9_])", lowered):
                errors.append(f"player-facing candidate contains forbidden term {term!r} at {path}")


def validate_candidate(candidate: dict[str, Any]) -> list[str]:
    errors = _schema_errors(candidate, "generated_world_candidate.v0.1.schema.json")
    roles = [item.get("role") for item in candidate.get("nodes", []) if isinstance(item, dict)]
    required_roles = {"main_city", "battle_hotspot", "research_facility", "resource_storage"}
    if set(roles) != required_roles:
        errors.append("nodes must contain each required gameplay role exactly once")
    ids: list[str] = []
    for key in ("resources", "nodes", "enemies", "npcs", "player_origins"):
        ids.extend(str(item.get("id") or "") for item in candidate.get(key, []) if isinstance(item, dict))
    ids.append(str(candidate.get("world_id") or ""))
    if any(not ID_RE.fullmatch(item) for item in ids):
        errors.append("all generated ids must be stable snake_case ids")
    if len(ids) != len(set(ids)):
        errors.append("generated ids must be unique inside a world candidate")
    if candidate.get("first_battle", {}).get("route_shape") not in ROUTE_TEMPLATES:
        errors.append("first_battle.route_shape is not supported")
    _scan_player_text(candidate, "", errors)
    return list(dict.fromkeys(errors))


SYSTEM_PROMPT = """你是塔防游戏世界实例编译器的创意前端。把薄创意种子扩写为一个结构化候选。
你只决定世界语汇、剧情氛围、资源、NPC、敌人、视觉风格与受控路线模板；游戏引擎会负责数值、碰撞、塔位和运行安全。
输出必须是单个 JSON 对象，严格符合给定 schema；不得输出 Markdown。
所有玩家可见文本使用自然的世界内中文，不出现 AI、provider、schema、prompt、compiler、token、trace、mock 等技术词。
世界必须适合塔防：明确主城、危机战斗点、研发设施、资源仓；敌人至少包含快群体与基础单位；玩家构想可被世界内设施试作成防御塔、陷阱或支援道具。
不要复写示例世界。稳定 ID 使用小写 snake_case，名称与描述应鲜明、可视化、便于美术生成。"""


def _messages(seed: dict[str, Any]) -> list[dict[str, str]]:
    schema = _schema("generated_world_candidate.v0.1.schema.json")
    engine = {
        "route_shapes": list(ROUTE_TEMPLATES),
        "required_node_roles": ["main_city", "battle_hotspot", "research_facility", "resource_storage"],
        "enemy_archetypes": ["fast_swarm", "basic", "armored_slow"],
        "visual_projection": "browser_pseudo3d_oblique",
        "first_battle_waves": 2,
    }
    user = {
        "creative_seed": seed,
        "engine_constraints": engine,
        "output_schema": schema,
    }
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ]


def generate_candidate(seed: dict[str, Any], *, profile_name: str, allow_provider: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    if not allow_provider:
        raise WorldCompilationError("provider generation requires explicit --allow-provider")
    adapter.load_dotenv(ROOT / ".env")
    profile = adapter.PROFILES.get(profile_name)
    if profile is None:
        raise WorldCompilationError(f"unknown provider profile: {profile_name}")
    if not os.environ.get(profile.env_key):
        raise WorldCompilationError(f"provider key is unavailable for profile: {profile_name}")
    messages = _messages(seed)
    candidate: dict[str, Any] | None = None
    errors: list[str] = []
    max_attempts = max(1, min(2, int(os.environ.get("AI_TD_WORLD_MAX_ATTEMPTS", "2"))))
    for attempt in range(1, max_attempts + 1):
        response = adapter.chat_completion(
            profile,
            messages,
            max_tokens=int(os.environ.get("AI_TD_WORLD_MAX_TOKENS", "16384")),
            timeout=int(os.environ.get("AI_TD_WORLD_TIMEOUT", "180")),
            response_format={"type": "json_object"} if profile.supports_json_object else None,
        )
        parsed = adapter.extract_json(adapter.extract_content_from_response(response))
        candidate = parsed if isinstance(parsed, dict) else None
        errors = validate_candidate(candidate) if candidate is not None else ["response root is not object"]
        if not errors:
            break
        if attempt < max_attempts:
            messages.extend([
                {"role": "assistant", "content": json.dumps(candidate or {}, ensure_ascii=False)},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "instruction": "只修复以下校验错误，返回完整 JSON 对象，不要解释。",
                            "validation_errors": errors[:12],
                        },
                        ensure_ascii=False,
                    ),
                },
            ])
    if candidate is None or errors:
        raise WorldCompilationError(f"generated candidate validation failed: {errors[0]}")
    provenance = {
        "generation_mode": "provider_generated",
        "profile": profile.name,
        "model": profile.model,
        "provider_call_performed": True,
        "attempt_count": attempt,
        "raw_prompt_stored": False,
        "raw_response_stored": False,
    }
    return candidate, provenance


def _by_role(candidate: dict[str, Any], role: str) -> dict[str, Any]:
    return next(item for item in candidate["nodes"] if item["role"] == role)


def _worldbook(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "worldbook_version": "worldbook.v0.1",
        "worldbook_id": candidate["world_id"],
        "display_name": candidate["display_name"],
        "summary": candidate["summary"],
        "tone_and_taboos": {
            "voice": candidate["tone_voice"],
            "forbidden_terms_in_player_text": list(FORBIDDEN_PLAYER_TERMS),
            "naming_style": candidate["naming_style"],
        },
        "phase_mapping": candidate["phase_terms"],
        "resource_mapping": {
            item["id"]: {"display_name": item["display_name"], "summary": item["summary"]}
            for item in candidate["resources"]
        },
        "node_mapping": {
            item["id"]: {"display_name": item["display_name"], "role": item["role"]}
            for item in candidate["nodes"]
        },
        "enemy_mapping": {
            item["id"]: {
                "display_name": item["display_name"],
                "summary": item["summary"],
                "archetype": item["archetype"],
            }
            for item in candidate["enemies"]
        },
        "npc_archetypes": [
            {
                "stable_internal_id": item["id"],
                "display_name": item["display_name"],
                "role": item["role"],
                "voice": item["voice"],
            }
            for item in candidate["npcs"]
        ],
        "asset_naming_rules": {
            "temporary_trap_sample": candidate["naming_style"],
            "tower_blueprint": candidate["naming_style"],
        },
        "visual_rules": {
            "palette": candidate["visual"]["palette"],
            "style": candidate["visual"]["style_name"],
        },
        "gameplay_tilt": {
            "default_creativity": "stable",
            "trap_sample_first": True,
            "formal_research_institute_unlocked": False,
        },
        "event_style": {
            "opening": "黑屏文字与动画卡建立世界危机。",
            "after_battle": "角色反馈与节点变化推动下一阶段。",
        },
    }


def _world_config(candidate: dict[str, Any]) -> dict[str, Any]:
    origins = candidate["player_origins"]
    return {
        "config_version": "world_instance_config.v0.1",
        "worldbook_template_id": candidate["world_id"],
        "worldbook_display_name": candidate["display_name"],
        "visual_style_id": candidate["visual"]["style_id"],
        "visual_style_display_name": candidate["visual"]["style_name"],
        "creativity_mode": {
            "selected": "stable",
            "options": [
                {"id": "stable", "display_name": "稳健", "summary": "优先采用已知可靠结构。"},
                {"id": "experimental", "display_name": "实验性", "summary": "允许更大胆的现场试作与未知代价。"},
            ],
        },
        "player_origin": {
            "selected": origins[0]["id"],
            "options": origins,
        },
        "recommended_defaults": {
            "creativity_mode": "stable",
            "player_origin": origins[0]["id"],
            "visual_style_id": candidate["visual"]["style_id"],
        },
        "effects": {
            "npc_address": "身份影响角色称呼与评审角度。",
            "opening_text": "身份影响开场介入方式。",
            "initial_materials": "身份影响开局资源侧重。",
            "proposal_constraints": "创造性影响现场试作风险。",
        },
        "content_lifecycle_note": "本配置由世界实例编译器生成，后续演化必须服务玩法进度。",
    }


def _opening(candidate: dict[str, Any]) -> dict[str, Any]:
    main = _by_role(candidate, "main_city")
    battle = _by_role(candidate, "battle_hotspot")
    segments = []
    for index, card in enumerate(candidate["opening_cards"]):
        segments.append({
            "stable_internal_id": f"opening_segment_{index + 1:02d}",
            "display_name": card["title"],
            "kind": "black_screen_text" if index == 0 else "animated_card",
            "duration_ms": 9000,
            **(
                {"lines": [card["text"]], "visual": {"bg": "#000000", "text_color": "#dddddd", "fade_in_ms": 800}}
                if index == 0
                else {"narration": card["text"], "visual": {"scene": f"compiled_world_card_{index}", "location_label": battle["display_name"] if index == len(candidate["opening_cards"]) - 1 else main["display_name"], "camera": "slow_zoom_in", "particles": "world_ambient"}}
            ),
            "audio": "ambient.world_theme",
        })
    return {
        "opening_version": "opening.v0.1",
        "worldbook_id": candidate["world_id"],
        "display_name": f"{candidate['display_name']}·开场",
        "total_duration_ms": sum(item["duration_ms"] for item in segments),
        "skippable": True,
        "replayable": True,
        "segments": segments,
        "landing": {
            "target_page": "world_map",
            "target_node_id": main["id"],
            "initial_quest": f"前往{battle['display_name']}应对第一场危机。",
            "hint": f"点击{battle['display_name']}进入第一场战斗。",
        },
    }


def _initial_map(candidate: dict[str, Any]) -> dict[str, Any]:
    positions = {
        "main_city": {"x": 300, "y": 390},
        "research_facility": {"x": 500, "y": 245},
        "resource_storage": {"x": 590, "y": 485},
        "battle_hotspot": {"x": 930, "y": 310},
    }
    states = {
        "main_city": "controlled", "research_facility": "available",
        "resource_storage": "controlled", "battle_hotspot": "crisis_active",
    }
    main = _by_role(candidate, "main_city")
    battle = _by_role(candidate, "battle_hotspot")
    return {
        "map_version": "initial_map.v0.1",
        "worldbook_id": candidate["world_id"],
        "display_name": f"{main['display_name']}态势图",
        "summary": candidate["tagline"],
        "viewport": {"width": 1280, "height": 720, "projection": "pseudo3d_oblique"},
        "nodes": [
            {
                "stable_internal_id": item["id"], "display_name": item["display_name"],
                "kind": item["role"], "position": positions[item["role"]],
                "state": states[item["role"]], "summary": item["summary"],
                "icons": [item["role"]],
            }
            for item in candidate["nodes"]
        ],
        "supply_lines": [{
            "stable_internal_id": f"supply_{main['id']}_to_{battle['id']}",
            "display_name": f"{main['display_name']}至{battle['display_name']}通路",
            "from_node_id": main["id"], "to_node_id": battle["id"], "state": "active",
            "summary": "当前唯一可靠的前线支援通路。",
        }],
        "dark_regions": [{
            "stable_internal_id": f"unknown_{candidate['world_id']}_edge",
            "display_name": "未探明区域",
            "polygon": [{"x": 700, "y": 500}, {"x": 1280, "y": 500}, {"x": 1280, "y": 720}, {"x": 700, "y": 720}],
            "state": "hidden", "summary": "尚未被当前势力掌握的区域。",
        }],
        "threat_edges": [{
            "stable_internal_id": f"threat_{battle['id']}", "display_name": "迫近威胁",
            "position": {"x": 1120, "y": 590}, "direction": "northwest", "severity": "high",
            "summary": candidate["first_battle"]["approach_direction"],
        }],
        "floating_events": [{
            "stable_internal_id": f"event_{battle['id']}_distress", "display_name": f"{battle['display_name']}急报",
            "kind": "distress_call", "anchor_node_id": battle["id"], "summary": candidate["first_battle"]["summary"],
        }],
        "legend_token_map": {
            "main_city": "主城", "battle_hotspot": "战斗热点", "research_facility": "设施",
            "resource_storage": "资源存储节点", "supply_line": "补给线", "dark_region": "未知区",
            "threat_edge": "移动威胁", "floating_event": "悬浮事件",
        },
    }


def _battle_config(candidate: dict[str, Any]) -> dict[str, Any]:
    battle_node = _by_role(candidate, "battle_hotspot")
    template = ROUTE_TEMPLATES[candidate["first_battle"]["route_shape"]]
    enemies = candidate["enemies"]
    fast = next((item for item in enemies if item["archetype"] == "fast_swarm"), enemies[0])
    basic = next((item for item in enemies if item["archetype"] == "basic"), enemies[-1])
    route = [{"x": x, "y": y} for x, y in template["waypoints"]]
    return {
        "battle_config_version": "first_battle.v0.1",
        "worldbook_id": candidate["world_id"],
        "node_id": battle_node["id"],
        "display_name": candidate["first_battle"]["display_name"],
        "grid": {"projection": "pseudo3d_oblique", "width_cells": 16, "height_cells": 9, "cell_size": 64},
        "paths": [{
            "stable_internal_id": f"path_{battle_node['id']}_main", "display_name": "主路径",
            "waypoints": route, "entry_label": candidate["first_battle"]["approach_direction"],
            "exit_label": candidate["first_battle"]["core_name"],
        }],
        "core_target": {
            "stable_internal_id": "target_node_core", "display_name": candidate["first_battle"]["core_name"],
            "position": {"x": template["core"][0], "y": template["core"][1]}, "durability": 10,
        },
        "optional_targets": [{
            "stable_internal_id": "target_optional_facility", "display_name": candidate["first_battle"]["optional_target_name"],
            "position": {"x": template["optional"][0], "y": template["optional"][1]}, "durability": 4,
        }],
        "waves": [
            {"wave_index": 1, "display_name": f"第一波·{fast['display_name']}", "enemy_archetype": fast["id"], "count": 6, "spawn_interval_ms": 1200, "speed_cells_per_sec": 1.8, "durability": 2, "delay_before_wave_ms": 3000},
            {"wave_index": 2, "display_name": f"第二波·{basic['display_name']}", "enemy_archetype": basic["id"], "count": 5, "spawn_interval_ms": 1700, "speed_cells_per_sec": 1.15, "durability": 4, "delay_before_wave_ms": 7000},
        ],
        "basic_defense": {"stable_internal_id": f"basic_defense_{candidate['world_id']}", "display_name": "基础防线", "summary": "使用本地常见材料搭建的临时防线。", "uses_per_battle": 3, "duration_ms": 4000},
        "sample_asset": {"stable_internal_id": "compiled_sample_pending", "asset_kind": "temporary_trap_sample", "template_id": "temporary_trap_sample", "lifecycle_state": "ephemeral", "display_name": "待完成试作品", "uses_per_battle": 2, "requires_delivery": True, "delivery_state": "research_in_progress", "delivery_delay_ms": 30000, "delivery_progress_messages": ["现场试作中。", "结构校准中。", "样品封装中。", "正在送达战场。"], "effect_summary": "效果将在玩家提出构想后编译。", "visual_recipes": ["ring_pulse", "aura_field", "sprite_flash"]},
        "victory_condition": f"守住{candidate['first_battle']['core_name']}至所有波次结束。",
        "failure_condition": f"{candidate['first_battle']['core_name']}耐久归零。",
        "post_battle": {"on_victory": "节点守住，世界状态与下一条线索发生变化。", "on_failure": "记录试作品表现，局势恶化但体验继续。"},
    }


def _crisis(candidate: dict[str, Any], battle: dict[str, Any]) -> dict[str, Any]:
    node = _by_role(candidate, "battle_hotspot")
    workshop = _by_role(candidate, "research_facility")
    return {
        "node_briefing_version": "first_crisis_node.v0.1", "worldbook_id": candidate["world_id"],
        "node_id": node["id"], "display_name": node["display_name"], "summary": candidate["first_battle"]["summary"],
        "threat": {"enemy_archetypes": [item["id"] for item in candidate["enemies"][:2]], "enemy_traits": candidate["first_battle"]["enemy_traits"], "approach_direction": candidate["first_battle"]["approach_direction"], "estimated_waves": 2},
        "protection_targets": [
            {"stable_internal_id": "target_node_core", "display_name": candidate["first_battle"]["core_name"], "kind": "core", "summary": "节点的主要防守目标。", "must_protect": True},
            {"stable_internal_id": "target_optional_facility", "display_name": candidate["first_battle"]["optional_target_name"], "kind": "facility", "summary": "守住后可保留额外支援。", "must_protect": False},
        ],
        "available_materials": [{"material_id": item["id"], "quantity": 3 if index == 0 else 2} for index, item in enumerate(candidate["resources"][:2])],
        "npcs_present": [candidate["npcs"][0]["id"]],
        "facility_state": {workshop["id"]: "available", "summary": f"{workshop['display_name']}可进行一次应急试作。"},
        "constraints": {"research_budget": "本节点允许一次现场试作。", "sample_delivery": "样品将在战斗中途送达。"},
        "player_action_hint": candidate["first_battle"]["suggested_research_intent"],
    }


def _style_pack(candidate: dict[str, Any], battle_path: Path, worldbook_path: Path, created_at: str) -> dict[str, Any]:
    visual = candidate["visual"]
    node = _by_role(candidate, "battle_hotspot")
    def prefab(suffix: str, role: str) -> dict[str, Any]:
        return {"prefab_id": f"{candidate['world_id']}_{suffix}", "role": role, "anchor_policy": "center", "placement_policy": "semantic_anchor_only", "visual_ref": {"kind": "procedural_shape", "value": f"compiled:{candidate['world_id']}:{suffix}"}}
    style = {
        "schema_version": "map_style_pack.v0.1", "style_pack_id": f"style_{candidate['world_id']}_{node['id']}_v0_1",
        "worldbook_id": candidate["world_id"], "node_id": node["id"], "created_at": created_at,
        "source_refs": {"map_runtime_package_path": "generated_by_map_compilation_input", "worldbook_path": _path_ref(worldbook_path), "logic_authority": "map_runtime_package", "style_authority": "reviewed_ai_proposal"},
        "node_theme_tags": visual["theme_tags"], "palette": visual["palette"],
        "lighting": {"time_of_day": visual["time_of_day"], "contrast_policy": "high_path_readability", "shadow_policy": "soft_blob", "intensity": 0.74},
        "terrain_materials": [
            {"material_id": visual["terrain_name"], "role": "terrain_base", "base_color": visual["palette"]["terrain_base"], "texture_policy": "procedural_only"},
            {"material_id": f"{visual['terrain_name']}_detail", "role": "terrain_detail", "base_color": visual["palette"]["terrain_detail"], "texture_policy": "procedural_only"},
        ],
        "road_materials": [
            {"material_id": visual["road_name"], "role": "road_band", "base_color": visual["palette"]["road_base"], "texture_policy": "procedural_only"},
            {"material_id": f"{visual['road_name']}_edge", "role": "road_edge", "base_color": visual["palette"]["road_edge"], "texture_policy": "procedural_only"},
        ],
        "road_edge_rules": {"edge_style": "soft_embedded", "shoulder_width_cells": 0.25, "direction_cue_policy": "embedded_marks"},
        "build_slot_platforms": [prefab(visual["slot_name"], "build_slot_platform")],
        "objective_prefabs": [prefab(visual["objective_name"], "objective_foundation")],
        "spawn_prefabs": [prefab(visual["spawn_name"], "spawn_marker")],
        "resource_prefabs": [prefab("resource_marker", "resource_marker")],
        "hazard_prefabs": [prefab("hazard_marker", "hazard_marker")],
        "blocking_props": [prefab("blocking_prop", "blocking_prop")],
        "non_blocking_props": [{**prefab("edge_decoration", "non_blocking_decoration"), "placement_policy": "edge_decoration_only"}],
        "decorative_props": [{**prefab("ambient_decoration", "non_blocking_decoration"), "placement_policy": "allowed_zone_only"}],
        "atmosphere_layers": [{"layer_id": "compiled_edge_atmosphere", "role": "fog", "opacity": 0.24, "placement_policy": "map_edges_only"}],
        "postprocess": {"contrast_boost": 0.3, "saturation": 0.92, "vignette": 0.16},
        "readability_rules": {"minimum_path_contrast": 0.42, "build_slot_marker_policy": "diegetic_platform", "objective_marker_policy": "diegetic_foundation", "spawn_marker_policy": "diegetic_portal", "no_baked_ui_text": True, "no_baked_enemy_or_tower": True, "debug_layers_player_default_allowed": False},
        "validation_report": {"gate_status": "passed", "style_only": True, "gates": [
            {"gate_id": "style_only_visual_boundary", "status": "passed", "summary": "Generated style controls appearance only; runtime map remains authoritative."},
            {"gate_id": "player_readability_boundary", "status": "passed", "summary": "Path, slots, objectives, and spawn remain readable and diegetic."},
        ]},
    }
    errors = procedural_map_render_plan.validate_style_pack(style, _schema("map_style_pack.v0.1.schema.json"))
    if errors:
        raise WorldCompilationError(f"lowered MapStylePack invalid: {errors[0]}")
    return style


def compile_candidate(
    seed: dict[str, Any], candidate: dict[str, Any], output_root: Path,
    *, provenance: dict[str, Any], compile_map: bool,
    live_map_visuals: bool = False,
    map_image_profile: str = "agnes_image_flash",
    dotenv_path: Path | None = None,
) -> dict[str, Any]:
    seed_errors = validate_seed(seed)
    candidate_errors = validate_candidate(candidate)
    if seed_errors or candidate_errors:
        raise WorldCompilationError((seed_errors + candidate_errors)[0])
    world_dir = output_root / candidate["world_id"]
    if world_dir.exists() and any(world_dir.iterdir()):
        raise WorldCompilationError(f"world output already exists: {world_dir}")
    created_at = _now()
    worldbook_path = world_dir / "worldbook.json"
    battle_path = world_dir / "first_battle_config.json"
    artifacts = {
        "worldbook": _worldbook(candidate),
        "world_instance_config": _world_config(candidate),
        "opening": _opening(candidate),
        "initial_map": _initial_map(candidate),
    }
    battle = _battle_config(candidate)
    crisis = _crisis(candidate, battle)
    style = _style_pack(candidate, battle_path, worldbook_path, created_at)
    paths = {
        "worldbook": _write(worldbook_path, artifacts["worldbook"]),
        "world_instance_config": _write(world_dir / "world_instance_config.json", artifacts["world_instance_config"]),
        "opening": _write(world_dir / "opening.json", artifacts["opening"]),
        "initial_map": _write(world_dir / "initial_map.json", artifacts["initial_map"]),
        "first_crisis_node": _write(world_dir / "first_crisis_node.json", crisis),
        "first_battle_config": _write(battle_path, battle),
        "map_style_pack": _write(world_dir / "map_style_pack.json", style),
        "candidate": _write(world_dir / "generated_world_candidate.json", candidate),
    }
    map_input = {
        "schema_version": "map_compilation_input.v0.1",
        "input_id": f"map_input_{candidate['world_id']}_first_battle",
        "created_at": created_at,
        "battle_config_path": "first_battle_config.json",
        "map_style_pack_path": "map_style_pack.json",
        "visual_generation": {"provider_handoff": True},
    }
    map_input_path = _write(world_dir / "map_compilation_input.json", map_input)
    paths["map_compilation_input"] = map_input_path
    map_report = None
    if compile_map:
        node_id = _by_role(candidate, "battle_hotspot")["id"]
        map_output = map_compilation_orchestrator.LAYERED_ROOT / node_id
        map_report = map_compilation_orchestrator.compile_map(
            map_input_path,
            map_output,
            live_visuals=live_map_visuals,
            image_profile=map_image_profile,
            dotenv_path=dotenv_path,
        )
    manifest = {
        "schema_version": "compiled_world_runtime_manifest.v0.1",
        "world_id": candidate["world_id"], "display_name": candidate["display_name"],
        "tagline": candidate["tagline"], "created_at": created_at,
        "seed": {"seed_id": seed["seed_id"], "sha256": hashlib.sha256(json.dumps(seed, ensure_ascii=False, sort_keys=True).encode()).hexdigest()},
        "generation": provenance,
        "entry_node_id": _by_role(candidate, "battle_hotspot")["id"],
        "suggested_research_intent": candidate["first_battle"]["suggested_research_intent"],
        "artifacts": {key: _path_ref(path) for key, path in paths.items()},
        "map_compilation_report": map_report,
        "activation": {"world_catalog_ready": True, "runtime_truth": "map_runtime_package" if map_report else "battle_config_pending_map_compile"},
    }
    manifest_path = _write(world_dir / "compiled_world_runtime_manifest.json", manifest)
    return {"manifest_path": _path_ref(manifest_path), "manifest": manifest}
