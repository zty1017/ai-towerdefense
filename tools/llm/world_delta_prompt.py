"""Prompt helpers for LLM-generated WorldStateDelta artifacts."""

from __future__ import annotations

import json
import re
from typing import Any


SYSTEM_PROMPT = """你是塔防世界状态编译器。你负责根据战斗结果、会话上下文和当前世界状态，生成一个 WorldStateDelta v0.1。

你必须只返回一个 JSON 对象，不能返回 Markdown、解释文字或数组。

顶层字段只能且必须包含：
- schema_version
- delta_id
- run_id
- worldbook_id
- source
- created_turn
- summary
- operations

只允许以下 9 种 operation：
1. append_event
2. set_map_node_state
3. adjust_resource
4. set_flag
5. unlock_fact
6. update_npc_relationship
7. add_temporary_sample
8. set_progress_phase
9. adjust_global_state

必须严格使用嵌套结构，不要把嵌套字段拍平：
- set_map_node_state 必须是 {"op":"set_map_node_state","node_id":"...","patch":{"status":"secured","threat_level":0,"visibility":"visible","available_actions":["field_research"]}}
- set_flag 必须使用字段 flag，不要使用 flag_id。
- unlock_fact 必须把 fact_id/source/visibility/summary 放进 fact 对象。
- update_npc_relationship 必须把 trust 放进 relationship_delta 对象。
- adjust_global_state 每条 operation 只能调整一个 field，必须使用 field 和 amount_delta；如果要调整 hope 与 pressure，请写成两条 operation。

不要包含 provider/model/raw_prompt/full_trace/raw_json/api_key/secret/unreviewed_content 等字段。
所有玩家可见文本必须使用世界内语言（中文叙事风格），不能出现技术术语。
"""


def _safe_delta_id(raw: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_]+", "_", raw).strip("_").lower()
    return safe[:96] or "delta_live_world_state"


def build_user_prompt(
    run_world_state: dict[str, Any],
    battle_result: dict[str, Any],
    session_context: dict[str, Any],
) -> str:
    progress = run_world_state.get("progress") or {}
    current_turn = progress.get("turn", 1)
    if not isinstance(current_turn, int):
        current_turn = 1
    created_turn = current_turn + 1
    run_id = run_world_state.get("run_id")
    worldbook_id = run_world_state.get("worldbook_id")
    target_node_id = battle_result.get("node_id") or session_context.get("node_id")
    delta_id_hint = _safe_delta_id(
        f"delta_{run_id}_{target_node_id}_{created_turn}_battle_result"
    )

    payload = {
        "instruction": "根据输入生成一个合法 WorldStateDelta v0.1。必须复制 required_output 中的固定字段值。",
        "required_output": {
            "schema_version": "world_state_delta.v0.1",
            "delta_id": delta_id_hint,
            "run_id": run_id,
            "worldbook_id": worldbook_id,
            "source": "battle_result",
            "created_turn": created_turn,
        },
        "valid_operation_templates": [
            {
                "op": "append_event",
                "event": {
                    "event_id": "event_unique_id",
                    "turn": created_turn,
                    "kind": "battle",
                    "summary": "世界内叙事摘要",
                },
            },
            {
                "op": "set_map_node_state",
                "node_id": target_node_id,
                "patch": {
                    "status": "secured",
                    "threat_level": 0,
                    "visibility": "visible",
                    "available_actions": ["field_research", "rest"],
                },
            },
            {
                "op": "adjust_resource",
                "resource_id": "lamp_oil",
                "amount_delta": -1,
            },
            {"op": "set_flag", "flag": "flag_name", "value": True},
            {
                "op": "unlock_fact",
                "fact": {
                    "fact_id": "fact_unique_id",
                    "source": "first_battle",
                    "visibility": "player_known",
                    "summary": "世界内事实摘要",
                },
            },
            {
                "op": "update_npc_relationship",
                "npc_id": "engineer_001",
                "relationship_delta": {"trust": 0.05},
            },
            {
                "op": "add_temporary_sample",
                "sample": {
                    "sample_id": "sample_unique_id",
                    "display_name": "世界内样品名",
                    "source_delta_id": delta_id_hint,
                    "summary": "世界内样品摘要",
                },
            },
            {"op": "set_progress_phase", "phase": "post_first_defense"},
            {
                "op": "adjust_global_state",
                "field": "hope",
                "amount_delta": 0.05,
            },
        ],
        "forbidden_operation_shapes": [
            {"op": "set_map_node_state", "node_id": target_node_id, "status": "secured"},
            {"op": "set_flag", "flag_id": "flag_name", "value": True},
            {"op": "unlock_fact", "fact_id": "fact_id"},
            {"op": "update_npc_relationship", "npc_id": "npc_id", "trust_delta": 0.1},
            {"op": "adjust_global_state", "hope": 0.1, "pressure": -0.1},
        ],
        "run_world_state": {
            "run_id": run_id,
            "worldbook_id": worldbook_id,
            "progress": progress,
            "global_state": run_world_state.get("global_state"),
            "resources": run_world_state.get("resources"),
            "map_nodes": [
                {
                    "node_id": n.get("node_id"),
                    "status": n.get("status"),
                    "threat_level": n.get("threat_level"),
                    "visibility": n.get("visibility"),
                    "available_actions": n.get("available_actions"),
                }
                for n in (run_world_state.get("map_nodes") or [])
            ],
            "npcs": [
                {
                    "npc_id": n.get("npc_id"),
                    "relationship": n.get("relationship"),
                }
                for n in (run_world_state.get("npcs") or [])
            ],
            "unlocked_facts": run_world_state.get("unlocked_facts"),
            "event_log": run_world_state.get("event_log"),
            "flags": run_world_state.get("flags"),
        },
        "battle_result": {
            "winner": battle_result.get("winner"),
            "core_damaged": battle_result.get("core_damaged"),
            "enemies_leaked": battle_result.get("enemies_leaked"),
            "waves_survived": battle_result.get("waves_survived"),
            "sample_triggered": battle_result.get("sample_triggered"),
            "node_id": target_node_id,
            "sample_performance": battle_result.get("sample_performance"),
        },
        "session_context": {
            "player_origin": session_context.get("player_origin"),
            "node_id": session_context.get("node_id"),
            "prior_events": session_context.get("prior_events"),
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
