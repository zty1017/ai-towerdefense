"""Prompt helpers for LLM-generated WorldStateDelta artifacts."""

from __future__ import annotations

import json
import re
from typing import Any


SYSTEM_PROMPT = """你是塔防世界状态与玩法对象编译器。你负责根据战斗结果、会话上下文和当前世界状态，生成一个 WorldStateDelta v0.1。

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

只允许以下 17 种 operation：
1. append_event
2. set_map_node_state
3. adjust_resource
4. introduce_map_node
5. set_flag
6. unlock_fact
7. update_npc_relationship
8. introduce_npc
9. add_temporary_sample
10. upsert_task
11. set_task_status
12. schedule_random_event
13. set_random_event_status
14. upsert_research_job
15. unlock_blueprint
16. set_progress_phase
17. adjust_global_state

剧情推进必须服务玩法。不要只写 append_event；如果阶段推进、战斗结果或世界线变化会影响玩家行动，必须同时使用任务、随机事件、研究任务、样品、蓝图、资源、NPC 或地图节点相关 op 承接。

必须严格使用嵌套结构，不要把嵌套字段拍平：
- set_map_node_state 必须是 {"op":"set_map_node_state","node_id":"...","patch":{"status":"secured","threat_level":0,"visibility":"visible","available_actions":["field_research"]}}
- introduce_map_node 必须把 node_id/status/threat_level/visibility/available_actions 放进 node 对象。
- set_flag 必须使用字段 flag，不要使用 flag_id。
- unlock_fact 必须把 fact_id/source/visibility/summary 放进 fact 对象。
- update_npc_relationship 必须把 trust 放进 relationship_delta 对象。
- introduce_npc 必须把 npc_id/location_node_id/narrative_roles/gameplay_roles/relationship/availability 放进 npc 对象。
- upsert_task 必须把 task_id/kind/status/title/summary 放进 task 对象。
- schedule_random_event 必须把 random_event_id/event_type/status/summary 放进 random_event 对象。
- upsert_research_job 必须把 job_id/status/started_turn/expected_turns/expected_output 放进 job 对象。
- unlock_blueprint 必须把 blueprint_id/unlocked_turn/source 放进 blueprint 对象。
- adjust_global_state 每条 operation 只能调整一个 field，必须使用 field 和 amount_delta；如果要调整 hope 与 pressure，请写成两条 operation。

引用约束：
- 只能引用当前 run state 已有对象，或在同一个 delta 中先 introduce/upsert/schedule 的对象。
- 不要更新 legacy fixture NPC。若 allowed_reference_boundary 标出 legacy_npc_ids，这些 NPC 不能被 update_npc_relationship、任务 npc_id 或 introduce_npc 使用。
- 若需要功能 NPC，优先使用 allowed_reference_boundary 中的 canonical_npc_ids 或 candidate_npc_ids，并先 introduce_npc。
- source_delta_id 必须等于本次 delta_id。
- battle_result 之后不要把 *_started flag 设置为 true；应写完成或结算类 flag。

不要包含 provider/model/raw_prompt/full_trace/raw_json/api_key/secret/unreviewed_content 等字段。
所有玩家可见文本必须使用世界内语言（中文叙事风格），不能出现技术术语。
"""


def _safe_delta_id(raw: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_]+", "_", raw).strip("_").lower()
    return safe[:96] or "delta_live_world_state"


def build_review_boundary_context(review_pack: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(review_pack, dict):
        return {
            "canonical_npc_ids": [],
            "candidate_npc_ids": [],
            "legacy_npc_ids": [],
            "canonical_material_ids": [],
            "candidate_material_ids": [],
        }
    boundaries = review_pack.get("canonical_boundaries")
    if not isinstance(boundaries, dict):
        return {
            "canonical_npc_ids": [],
            "candidate_npc_ids": [],
            "legacy_npc_ids": [],
            "canonical_material_ids": [],
            "candidate_material_ids": [],
        }
    canonical_npcs = []
    for npc in boundaries.get("canonical_npcs", []) or []:
        if isinstance(npc, dict) and isinstance(npc.get("npc_id"), str):
            canonical_npcs.append(npc["npc_id"])
    candidate_npcs = []
    for npc in boundaries.get("candidate_functional_npcs", []) or []:
        if isinstance(npc, dict) and isinstance(npc.get("npc_id"), str):
            candidate_npcs.append(npc["npc_id"])
    legacy_npcs = []
    for ref in boundaries.get("compatibility_refs", []) or []:
        if not isinstance(ref, dict) or ref.get("status") != "legacy_fixture_ref":
            continue
        for key in ("ref_id", "npc_id"):
            if isinstance(ref.get(key), str):
                legacy_npcs.append(ref[key])
    candidate_materials = []
    for item in boundaries.get("candidate_only_materials", []) or []:
        if isinstance(item, dict) and isinstance(item.get("material_id"), str):
            candidate_materials.append(item["material_id"])
    return {
        "canonical_npc_ids": sorted(set(canonical_npcs)),
        "candidate_npc_ids": sorted(set(candidate_npcs)),
        "legacy_npc_ids": sorted(set(legacy_npcs)),
        "canonical_material_ids": sorted(
            str(item)
            for item in boundaries.get("canonical_materials", []) or []
            if isinstance(item, str)
        ),
        "candidate_material_ids": sorted(set(candidate_materials)),
    }


def build_user_prompt(
    run_world_state: dict[str, Any],
    battle_result: dict[str, Any],
    session_context: dict[str, Any],
    review_pack: dict[str, Any] | None = None,
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
        "instruction": "根据输入生成一个合法 WorldStateDelta v0.1。必须复制 required_output 中的固定字段值，并让剧情推进落到玩法对象或状态变化上。",
        "compiler_contract": {
            "worldbook_base_mutation_allowed": False,
            "narrative_must_bind_gameplay": True,
            "do_not_output_only_story_text": True,
            "semantic_gate_after_generation": "validate_world_delta_semantics.py",
            "recommended_gameplay_outputs": [
                "task",
                "random_event",
                "research_job",
                "temporary_sample",
                "blueprint",
                "resource_change",
                "npc_state",
                "map_node_state",
            ],
        },
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
                "op": "introduce_map_node",
                "node": {
                    "node_id": "new_or_reviewed_node_id",
                    "status": "known",
                    "threat_level": 1,
                    "visibility": "known",
                    "available_actions": ["scout", "field_research"],
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
                "npc_id": "npc_id_current_or_introduced_in_same_delta",
                "relationship_delta": {"trust": 0.05},
            },
            {
                "op": "introduce_npc",
                "npc": {
                    "npc_id": "candidate_or_canonical_npc_id",
                    "location_node_id": target_node_id,
                    "narrative_roles": ["witness"],
                    "gameplay_roles": ["research_review"],
                    "relationship": {"trust": 0.15},
                    "availability": "present",
                },
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
            {
                "op": "upsert_task",
                "task": {
                    "task_id": "task_unique_id",
                    "kind": "research",
                    "status": "active",
                    "title": "世界内任务名",
                    "summary": "世界内任务摘要",
                    "node_id": target_node_id,
                    "objective_refs": [target_node_id],
                    "reward_refs": ["sample_or_blueprint_id"],
                },
            },
            {
                "op": "set_task_status",
                "task_id": "existing_or_new_task_id",
                "status": "completed",
            },
            {
                "op": "schedule_random_event",
                "random_event": {
                    "random_event_id": "random_event_unique_id",
                    "event_type": "map_pressure",
                    "status": "pending",
                    "summary": "世界内压力事件摘要",
                    "node_id": target_node_id,
                    "trigger_turn": created_turn + 1,
                    "related_task_id": "existing_or_new_task_id",
                },
            },
            {
                "op": "set_random_event_status",
                "random_event_id": "existing_or_new_random_event_id",
                "status": "resolved",
            },
            {
                "op": "upsert_research_job",
                "job": {
                    "job_id": "research_unique_id",
                    "status": "running",
                    "started_turn": created_turn,
                    "source_task_id": "existing_or_new_task_id",
                    "expected_turns": 1,
                    "expected_output": "世界内研发产物名",
                },
            },
            {
                "op": "unlock_blueprint",
                "blueprint": {
                    "blueprint_id": "asset_or_blueprint_id",
                    "unlocked_turn": created_turn,
                    "source": "research_unique_id",
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
            {"op": "introduce_map_node", "node_id": "node_id", "status": "known"},
            {"op": "set_flag", "flag_id": "flag_name", "value": True},
            {"op": "unlock_fact", "fact_id": "fact_id"},
            {"op": "update_npc_relationship", "npc_id": "npc_id", "trust_delta": 0.1},
            {"op": "introduce_npc", "npc_id": "npc_id"},
            {"op": "upsert_task", "task_id": "task_id"},
            {"op": "schedule_random_event", "random_event_id": "event_id"},
            {"op": "upsert_research_job", "job_id": "job_id"},
            {"op": "unlock_blueprint", "blueprint_id": "blueprint_id"},
            {"op": "adjust_global_state", "hope": 0.1, "pressure": -0.1},
        ],
        "allowed_reference_boundary": build_review_boundary_context(review_pack),
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
                    "narrative_roles": n.get("narrative_roles"),
                    "gameplay_roles": n.get("gameplay_roles"),
                    "availability": n.get("availability"),
                }
                for n in (run_world_state.get("npcs") or [])
            ],
            "unlocked_facts": run_world_state.get("unlocked_facts"),
            "event_log": run_world_state.get("event_log"),
            "flags": run_world_state.get("flags"),
            "tasks": run_world_state.get("tasks", []),
            "random_events": run_world_state.get("random_events", []),
            "research": run_world_state.get("research"),
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
