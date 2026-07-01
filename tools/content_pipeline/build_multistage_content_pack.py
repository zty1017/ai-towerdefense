#!/usr/bin/env python3
"""Build a review-only multi-stage content pack for the AI compiler MVP.

The pack extends the deterministic Stage 05 draft into a three-stage content
chain. It proves that the same controlled compiler contracts can produce
staged narrative, tasks, random events, temporary samples, research jobs, and
multiple gameplay asset types without touching the frontend.

This builder is offline: it never reads .env and never calls model or media
providers.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CONTENT_DIR = ROOT / "tools" / "content_pipeline"
NARRATIVE_DIR = ROOT / "tools" / "narrative"
WORLD_STATE_DIR = ROOT / "tools" / "world_state"

for path in (CONTENT_DIR, NARRATIVE_DIR, WORLD_STATE_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import build_stage05_plan_realization as stage05  # noqa: E402
from apply_world_delta import apply_delta  # noqa: E402
from mock_compile_proposal import compile_candidate  # noqa: E402
from validate_asset_candidate import validate as validate_asset_candidate  # noqa: E402
from validate_narrative_bundle import validate_narrative_bundle  # noqa: E402
from validate_proposal import validate as validate_proposal  # noqa: E402
from validate_stage_candidate_pack import validate_stage_candidate_pack  # noqa: E402
from validate_run_world_state import (  # noqa: E402
    validate_run_world_state,
    validate_with_jsonschema as validate_run_state_jsonschema,
)
from validate_world_delta import (  # noqa: E402
    validate_world_delta,
    validate_with_jsonschema as validate_delta_jsonschema,
)
from validate_world_delta_semantics import (  # noqa: E402
    build_reference_registry,
    validate_world_delta_semantics,
)


DEFAULT_REVIEW_PACK = ROOT / "examples/review_packs/mvp_story_asset_review_pack.v0.1.json"
DEFAULT_STAGE05_PLAN = ROOT / "examples/review_packs/mvp_next_stage_compilable_object_plan.v0.1.json"
DEFAULT_STAGE04_STATE = ROOT / "examples/run_world_states/demo_after_stage_04_wick_store.run_world_state.json"
DEFAULT_EFFECT_REGISTRY = ROOT / "shared/module_registry/effect_blocks.v0.1.json"
DEFAULT_OUTPUT = ROOT / "examples/review_packs/mvp_multistage_content_pack.v0.1.json"
DEFAULT_STAGE_CANDIDATE_OUTPUT = ROOT / "examples/review_packs/mvp_multistage_stage_candidate_pack.v0.1.json"
DEFAULT_PROMOTION_REPORT = ROOT / "examples/review_packs/mvp_story_asset_promotion_report.v0.1.json"

STAGE06_ID = "act_1_stage_06_signal_resonance_trial"
STAGE06_DELTA_ID = "delta_stage_06_signal_resonance_trial"
STAGE06_BUNDLE = ROOT / "examples/narrative_bundles/stage_06_signal_resonance_trial.narrative_event_bundle.json"
STAGE06_DELTA = ROOT / "examples/world_deltas/stage_06_signal_resonance_trial.world_delta.json"
STAGE06_STATE = ROOT / "examples/run_world_states/demo_after_stage_06_signal_resonance.run_world_state.json"
STAGE06_PROPOSAL = ROOT / "examples/proposals/signal_echo_marker.proposal.json"
STAGE06_CANDIDATE = ROOT / "examples/compiled_assets/signal_echo_marker.compiled_asset.json"

STAGE07_ID = "act_1_stage_07_split_tide_containment"
STAGE07_DELTA_ID = "delta_stage_07_split_tide_containment"
STAGE07_BUNDLE = ROOT / "examples/narrative_bundles/stage_07_split_tide_containment.narrative_event_bundle.json"
STAGE07_DELTA = ROOT / "examples/world_deltas/stage_07_split_tide_containment.world_delta.json"
STAGE07_STATE = ROOT / "examples/run_world_states/demo_after_stage_07_split_tide.run_world_state.json"
STAGE07_PROPOSAL = ROOT / "examples/proposals/overload_chain_breaker.proposal.json"
STAGE07_CANDIDATE = ROOT / "examples/compiled_assets/overload_chain_breaker.compiled_asset.json"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def proposed_delta_summary(ops: list[str], summary: str) -> dict[str, Any]:
    return {"expected_operations": ops, "summary": summary}


def stage_bundle_base(
    *,
    bundle_id: str,
    run_state: dict[str, Any],
    stage_id: str,
    source: str,
    created_turn: int,
) -> dict[str, Any]:
    return {
        "schema_version": "narrative_event_bundle.v0.1",
        "bundle_id": bundle_id,
        "run_id": str(run_state.get("run_id")),
        "worldbook_id": str(run_state.get("worldbook_id")),
        "source": source,
        "created_turn": created_turn,
        "stage": stage_id,
        "lane": "shared",
        "commit_policy": {
            "candidate_generation": "parallel_allowed",
            "commit_gate": "world_state_delta_required",
            "commit_order": "manual_review_then_serial",
        },
        "worldbook_base_mutation_allowed": False,
        "nodes": [],
    }


def build_stage06_bundle(run_state: dict[str, Any]) -> dict[str, Any]:
    turn = stage05.next_turn(run_state)
    bundle = stage_bundle_base(
        bundle_id="bundle_stage_06_signal_resonance_trial",
        run_state=run_state,
        stage_id=STAGE06_ID,
        source="research_job",
        created_turn=turn,
    )
    bundle["nodes"] = [
        {
            "node_id": "node_stage06_world_signal_stabilized",
            "stage": STAGE06_ID,
            "phase": "signal_resonance_trial",
            "lane": "world_line",
            "scope": "map",
            "trigger": {
                "kind": "research_complete",
                "ref": "research_echo_prism_relay_trial",
                "summary": "旧信号塔的回光棱座完成第一次稳定。",
            },
            "prerequisites": ["task_stabilize_old_signal_tower", "sample_resonant_glass_shard_trial"],
            "visibility": "player_visible",
            "presentation": {
                "scene_type": "map_event",
                "title": "旧塔短暂稳住",
                "blocks": [
                    {
                        "text": "回光棱座咬住旧塔铜槽后，塔顶的白线短暂并拢，北路影潮的来向被照出一段。"
                    }
                ],
            },
            "gameplay_purpose": [
                "modify_map_node_state",
                "reward_player_choice",
                "trigger_random_event",
            ],
            "gameplay_hooks": [
                {
                    "hook": "modify_map_node_state",
                    "target_ref": "old_signal_tower",
                    "summary": "旧信号塔从受压节点回到暂稳状态。",
                },
                {
                    "hook": "trigger_random_event",
                    "target_ref": "random_event_signal_backwash",
                    "summary": "回光回流事件进入可处理状态。",
                },
            ],
            "npc_refs": ["npc_road_scout"],
            "npc_introductions": [],
            "proposed_world_delta_ref": STAGE06_DELTA_ID,
            "proposed_delta_summary": proposed_delta_summary(
                ["set_map_node_state", "set_random_event_status", "unlock_blueprint"],
                "完成旧塔试作，并把回流压力转入下一步处理。",
            ),
        },
        {
            "node_id": "node_stage06_player_echo_marker_task",
            "stage": STAGE06_ID,
            "phase": "signal_resonance_trial",
            "lane": "player_line",
            "scope": "quest",
            "trigger": {
                "kind": "research_complete",
                "ref": "asset_echo_prism_relay",
                "summary": "玩家线获得可复用试作蓝图和回声测标需求。",
            },
            "prerequisites": ["old_signal_tower_resonance_measured", "npc_road_scout"],
            "visibility": "player_visible",
            "presentation": {
                "scene_type": "dialogue",
                "title": "回声测标",
                "blocks": [
                    {
                        "speaker_id": "npc_road_scout",
                        "speaker_name": "北路斥候",
                        "text": "塔稳住以后，余光会反弹一次。若把它记下来，下一段黑路就不用靠猜。"
                    },
                    {"text": "新的测标任务被加入路牌，完成后可提前看见分潮方向。"},
                ],
            },
            "gameplay_purpose": ["create_quest_hook", "create_research_need", "teach_mechanic"],
            "gameplay_hooks": [
                {
                    "hook": "create_quest_hook",
                    "target_ref": "task_map_signal_backwash",
                    "summary": "创建回流测标任务。",
                },
                {
                    "hook": "create_research_need",
                    "target_ref": "research_signal_echo_marker_trial",
                    "summary": "把回声测标作为支援道具候选试作。",
                },
            ],
            "npc_refs": ["npc_road_scout"],
            "npc_introductions": [],
            "proposed_world_delta_ref": STAGE06_DELTA_ID,
            "proposed_delta_summary": proposed_delta_summary(
                ["upsert_task", "upsert_research_job", "add_temporary_sample"],
                "生成支援道具任务和临时样本。",
            ),
        },
        {
            "node_id": "node_stage06_shared_echo_asset",
            "stage": STAGE06_ID,
            "phase": "signal_resonance_trial",
            "lane": "shared",
            "scope": "resource",
            "trigger": {
                "kind": "player_choice",
                "ref": "random_event_signal_backwash",
                "summary": "玩家选择把回流记录成可携带测标。",
            },
            "prerequisites": ["sample_resonant_glass_shard_trial", "asset_echo_prism_relay"],
            "visibility": "player_visible",
            "presentation": {
                "scene_type": "workshop_notice",
                "title": "余光被收进短札",
                "blocks": [
                    {
                        "text": "旧塔回流被压成一枚短札，能在下一段黑路开始前标出敌群来向。"
                    }
                ],
            },
            "gameplay_purpose": ["introduce_material", "create_research_need", "reward_player_choice"],
            "gameplay_hooks": [
                {
                    "hook": "introduce_material",
                    "target_ref": "sample_signal_echo_marker_trial",
                    "summary": "生成回声测标临时样本。",
                },
                {
                    "hook": "reward_player_choice",
                    "target_ref": "asset_signal_echo_marker",
                    "summary": "提供支援道具候选资产。",
                },
            ],
            "npc_refs": ["npc_road_scout"],
            "npc_introductions": [],
            "proposed_world_delta_ref": STAGE06_DELTA_ID,
            "proposed_delta_summary": proposed_delta_summary(
                ["adjust_resource", "add_temporary_sample", "schedule_random_event"],
                "给予少量灯灰回收，并为下一段分潮压力做铺垫。",
            ),
        },
    ]
    return bundle


def build_stage06_delta(run_state: dict[str, Any]) -> dict[str, Any]:
    turn = stage05.next_turn(run_state)
    return {
        "schema_version": "world_state_delta.v0.1",
        "delta_id": STAGE06_DELTA_ID,
        "run_id": str(run_state.get("run_id")),
        "worldbook_id": str(run_state.get("worldbook_id")),
        "source": "research_job",
        "created_turn": turn,
        "summary": "旧信号塔试作完成，回光中继塔蓝图暂时可用，并出现可记录的回流。",
        "operations": [
            {"op": "set_progress_phase", "phase": "signal_resonance_trial"},
            {"op": "set_task_status", "task_id": "task_stabilize_old_signal_tower", "status": "completed"},
            {
                "op": "upsert_research_job",
                "job": {
                    "job_id": "research_echo_prism_relay_trial",
                    "status": "completed",
                    "started_turn": 6,
                    "source_task_id": "task_stabilize_old_signal_tower",
                    "source_sample_id": "sample_resonant_glass_shard_trial",
                    "expected_turns": 1,
                    "expected_output": "回光棱镜中继塔试作",
                },
            },
            {
                "op": "unlock_blueprint",
                "blueprint": {
                    "blueprint_id": "asset_echo_prism_relay",
                    "unlocked_turn": turn,
                    "source": "research_echo_prism_relay_trial",
                },
            },
            {
                "op": "set_map_node_state",
                "node_id": "old_signal_tower",
                "patch": {
                    "status": "secured",
                    "threat_level": 1,
                    "visibility": "visible",
                    "available_actions": [
                        "collect_signal_echo",
                        "field_research",
                        "prepare_next_route",
                    ],
                },
            },
            {
                "op": "set_random_event_status",
                "random_event_id": "random_event_signal_backwash",
                "status": "available",
            },
            {
                "op": "update_npc_relationship",
                "npc_id": "npc_road_scout",
                "relationship_delta": {"trust": 0.05},
            },
            {"op": "adjust_resource", "resource_id": "lantern_ash", "amount_delta": 1},
            {
                "op": "add_temporary_sample",
                "sample": {
                    "sample_id": "sample_signal_echo_marker_trial",
                    "display_name": "回声测标短札",
                    "source_delta_id": STAGE06_DELTA_ID,
                    "summary": "旧信号塔回流被记录成短札，可在下一段黑路开始前标出敌群来向。",
                },
            },
            {
                "op": "upsert_task",
                "task": {
                    "task_id": "task_map_signal_backwash",
                    "kind": "scouting",
                    "status": "active",
                    "title": "记录旧塔回流方向",
                    "summary": "旧信号塔试作完成后出现一次可记录的回流，需要在回流散尽前做成测标短札。",
                    "node_id": "old_signal_tower",
                    "npc_id": "npc_road_scout",
                    "objective_refs": [
                        "random_event_signal_backwash",
                        "sample_signal_echo_marker_trial",
                    ],
                    "reward_refs": ["asset_signal_echo_marker", "random_event_split_tide_pressure"],
                },
            },
            {
                "op": "upsert_research_job",
                "job": {
                    "job_id": "research_signal_echo_marker_trial",
                    "status": "queued",
                    "started_turn": turn,
                    "source_task_id": "task_map_signal_backwash",
                    "source_sample_id": "sample_signal_echo_marker_trial",
                    "expected_turns": 1,
                    "expected_output": "回声测标短札试作",
                },
            },
            {
                "op": "unlock_fact",
                "fact": {
                    "fact_id": "signal_echo_marker_possible",
                    "source": "signal_resonance_trial",
                    "visibility": "player_known",
                    "summary": "旧信号塔回流可以被记录成短札，用于提前判断下一段敌潮方向。",
                },
            },
            {
                "op": "schedule_random_event",
                "random_event": {
                    "random_event_id": "random_event_split_tide_pressure",
                    "event_type": "threat_warning",
                    "status": "pending",
                    "summary": "旧塔回流照出一条新的分潮线，北路外缘可能出现更强的分散冲击。",
                    "node_id": "old_signal_tower",
                    "trigger_turn": turn,
                    "related_task_id": "task_map_signal_backwash",
                },
            },
            {
                "op": "append_event",
                "event": {
                    "event_id": "signal_resonance_trial_completed",
                    "turn": turn,
                    "kind": "research",
                    "summary": "回光棱镜中继塔试作完成，旧信号塔短暂稳定，回声测标任务开启。",
                },
            },
            {"op": "set_flag", "flag": "stage_06_signal_resonance_trial_completed", "value": True},
            {"op": "adjust_global_state", "field": "pressure", "amount_delta": -0.03},
            {"op": "adjust_global_state", "field": "hope", "amount_delta": 0.04},
            {"op": "adjust_global_state", "field": "visibility", "amount_delta": 0.08},
        ],
    }


def build_stage06_proposal(run_state: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "proposal_signal_echo_marker",
        "mode": "runtime_safe",
        "title": "回声测标短札方案",
        "summary": "把旧信号塔回流压成一枚短札，在下一段黑路开始前标出敌群来向并给出克制提示。",
        "intended_asset_type": "support_item",
        "expected_effect": ["scouting", "support"],
        "risk_level": "low",
        "estimated_cost": "low",
        "required_inputs": {
            "npc_ids": ["npc_road_scout"],
            "materials": ["lamp_shard", "lantern_ash"],
            "facility": "field_workshop",
            "knowledge_tags": ["signal_echo_marker_possible", "old_signal_tower_resonance_measured"],
        },
        "known_tradeoffs": [
            "只能在战前或准备阶段使用。",
            "它提供来向和弱点提示，不能直接造成伤害。",
        ],
        "player_prompt": "我想把旧塔回流做成一个能提前标出敌群方向的小道具，帮助下一场布防。",
        "worldbook_id": str(run_state.get("worldbook_id")),
    }


def build_stage07_bundle(run_state: dict[str, Any]) -> dict[str, Any]:
    turn = stage05.next_turn(run_state)
    bundle = stage_bundle_base(
        bundle_id="bundle_stage_07_split_tide_containment",
        run_state=run_state,
        stage_id=STAGE07_ID,
        source="world_tick",
        created_turn=turn,
    )
    bundle["nodes"] = [
        {
            "node_id": "node_stage07_world_split_tide_visible",
            "stage": STAGE07_ID,
            "phase": "split_tide_containment_planned",
            "lane": "world_line",
            "scope": "map",
            "trigger": {
                "kind": "world_tick",
                "ref": "random_event_split_tide_pressure",
                "summary": "旧塔回流照出东侧分潮线。",
            },
            "prerequisites": ["signal_echo_marker_possible", "task_map_signal_backwash"],
            "visibility": "player_visible",
            "presentation": {
                "scene_type": "map_event",
                "title": "分潮线露出",
                "blocks": [
                    {
                        "text": "回声测标在黑路上亮了一息，东侧暗脊被标出，分散影潮正绕开旧塔。"
                    }
                ],
            },
            "gameplay_purpose": [
                "unlock_battle_node",
                "modify_map_node_state",
                "increase_threat",
            ],
            "gameplay_hooks": [
                {
                    "hook": "unlock_battle_node",
                    "target_ref": "east_dark_ridge",
                    "summary": "打开下一段可审查压力节点。",
                },
                {
                    "hook": "increase_threat",
                    "target_ref": "random_event_split_tide_pressure",
                    "summary": "把分潮压力转为可处理威胁。",
                },
            ],
            "npc_refs": ["npc_road_scout", "npc_wire_mender_003"],
            "npc_introductions": [],
            "proposed_world_delta_ref": STAGE07_DELTA_ID,
            "proposed_delta_summary": proposed_delta_summary(
                ["introduce_map_node", "set_map_node_state", "set_random_event_status"],
                "打开东侧暗脊节点，并让北路压力进入分潮阶段。",
            ),
        },
        {
            "node_id": "node_stage07_player_high_risk_mod",
            "stage": STAGE07_ID,
            "phase": "split_tide_containment_planned",
            "lane": "player_line",
            "scope": "workshop",
            "trigger": {
                "kind": "player_choice",
                "ref": "east_dark_ridge",
                "summary": "玩家选择用高风险临时改造遏制分潮。",
            },
            "prerequisites": ["npc_wire_mender_003", "conductor_filament"],
            "visibility": "player_visible",
            "presentation": {
                "scene_type": "dialogue",
                "title": "补线人的险招",
                "blocks": [
                    {
                        "speaker_id": "npc_wire_mender_003",
                        "speaker_name": "补线人",
                        "text": "分潮太散，慢慢拦会漏。可以把导线短压成连弧，让一座塔在片刻内追着影线跳。代价是容易停摆。"
                    },
                    {"text": "高风险试作被加入研发队列，只适合下一场短时使用。"},
                ],
            },
            "gameplay_purpose": ["create_research_need", "offer_workshop_hook", "teach_mechanic"],
            "gameplay_hooks": [
                {
                    "hook": "create_research_need",
                    "target_ref": "research_overload_chain_breaker_trial",
                    "summary": "开启高风险临时改造试作。",
                },
                {
                    "hook": "offer_workshop_hook",
                    "target_ref": "asset_overload_chain_breaker",
                    "summary": "提供临时改造候选资产。",
                },
            ],
            "npc_refs": ["npc_wire_mender_003"],
            "npc_introductions": [],
            "proposed_world_delta_ref": STAGE07_DELTA_ID,
            "proposed_delta_summary": proposed_delta_summary(
                ["adjust_resource", "add_temporary_sample", "upsert_research_job"],
                "消耗导线并生成高风险连弧改造样本。",
            ),
        },
        {
            "node_id": "node_stage07_shared_next_pressure",
            "stage": STAGE07_ID,
            "phase": "split_tide_containment_planned",
            "lane": "shared",
            "scope": "quest",
            "trigger": {
                "kind": "map_entered",
                "ref": "east_dark_ridge",
                "summary": "玩家线和世界线汇合到东侧暗脊防守准备。",
            },
            "prerequisites": ["random_event_split_tide_pressure"],
            "visibility": "player_visible",
            "presentation": {
                "scene_type": "workshop_notice",
                "title": "断潮任务",
                "blocks": [
                    {"text": "东侧暗脊成为下一段防线。分潮不再只考验火力，而是考验预警、短时改造和节点保护。"}
                ],
            },
            "gameplay_purpose": ["create_quest_hook", "advance_main_pressure", "trigger_random_event"],
            "gameplay_hooks": [
                {
                    "hook": "create_quest_hook",
                    "target_ref": "task_contain_split_tide",
                    "summary": "创建分潮遏制任务。",
                },
                {
                    "hook": "trigger_random_event",
                    "target_ref": "random_event_east_ridge_pressure",
                    "summary": "为下一段战斗压力保留入口。",
                },
            ],
            "npc_refs": ["npc_road_scout", "npc_wire_mender_003"],
            "npc_introductions": [],
            "proposed_world_delta_ref": STAGE07_DELTA_ID,
            "proposed_delta_summary": proposed_delta_summary(
                ["upsert_task", "schedule_random_event", "adjust_global_state"],
                "生成下一战准备任务和后续压力事件。",
            ),
        },
    ]
    return bundle


def build_stage07_delta(run_state: dict[str, Any]) -> dict[str, Any]:
    turn = stage05.next_turn(run_state)
    return {
        "schema_version": "world_state_delta.v0.1",
        "delta_id": STAGE07_DELTA_ID,
        "run_id": str(run_state.get("run_id")),
        "worldbook_id": str(run_state.get("worldbook_id")),
        "source": "narrative_event",
        "created_turn": turn,
        "summary": "回声测标照出东侧暗脊分潮线，玩家获得一项高风险短时改造任务。",
        "operations": [
            {"op": "set_progress_phase", "phase": "split_tide_containment_planned"},
            {
                "op": "set_random_event_status",
                "random_event_id": "random_event_split_tide_pressure",
                "status": "available",
            },
            {
                "op": "introduce_map_node",
                "node": {
                    "node_id": "east_dark_ridge",
                    "status": "known",
                    "threat_level": 4,
                    "visibility": "known",
                    "available_actions": [
                        "prepare_defense",
                        "field_research",
                        "contain_split_tide",
                    ],
                },
            },
            {
                "op": "set_map_node_state",
                "node_id": "northern_road_crossing",
                "patch": {
                    "status": "contested",
                    "threat_level": 2,
                    "visibility": "visible",
                    "available_actions": ["hold_route", "field_research", "support_east_ridge"],
                },
            },
            {
                "op": "upsert_task",
                "task": {
                    "task_id": "task_contain_split_tide",
                    "kind": "defense",
                    "status": "active",
                    "title": "遏制东侧分潮",
                    "summary": "回声测标照出东侧暗脊，分散影潮即将绕开旧信号塔，需要准备短时连弧改造并守住新节点。",
                    "node_id": "east_dark_ridge",
                    "npc_id": "npc_wire_mender_003",
                    "objective_refs": [
                        "east_dark_ridge",
                        "random_event_split_tide_pressure",
                        "asset_overload_chain_breaker",
                    ],
                    "reward_refs": ["sample_charged_copper_coil_trial", "random_event_east_ridge_pressure"],
                },
            },
            {"op": "adjust_resource", "resource_id": "conductor_filament", "amount_delta": -1},
            {
                "op": "add_temporary_sample",
                "sample": {
                    "sample_id": "sample_charged_copper_coil_trial",
                    "display_name": "短压铜线圈样本",
                    "source_delta_id": STAGE07_DELTA_ID,
                    "summary": "导线被短时压成不稳定线圈，可支撑一次连弧改造试作。",
                },
            },
            {
                "op": "upsert_research_job",
                "job": {
                    "job_id": "research_overload_chain_breaker_trial",
                    "status": "queued",
                    "started_turn": turn,
                    "source_task_id": "task_contain_split_tide",
                    "source_sample_id": "sample_charged_copper_coil_trial",
                    "expected_turns": 1,
                    "expected_output": "过载连弧断潮改造",
                },
            },
            {
                "op": "update_npc_relationship",
                "npc_id": "npc_wire_mender_003",
                "relationship_delta": {"trust": 0.06},
            },
            {
                "op": "unlock_fact",
                "fact": {
                    "fact_id": "split_tide_needs_chain_control",
                    "source": "split_tide_containment",
                    "visibility": "player_known",
                    "summary": "分散影潮会绕开单点防线，短时连弧和预警道具能帮助压住多路压力。",
                },
            },
            {
                "op": "schedule_random_event",
                "random_event": {
                    "random_event_id": "random_event_east_ridge_pressure",
                    "event_type": "map_pressure",
                    "status": "pending",
                    "summary": "东侧暗脊压力继续升高，下一场防守需要兼顾旧路和新节点。",
                    "node_id": "east_dark_ridge",
                    "trigger_turn": turn,
                    "related_task_id": "task_contain_split_tide",
                },
            },
            {
                "op": "append_event",
                "event": {
                    "event_id": "split_tide_containment_planned",
                    "turn": turn,
                    "kind": "world",
                    "summary": "东侧暗脊分潮线露出，断潮任务和高风险短时改造进入准备。",
                },
            },
            {"op": "set_flag", "flag": "stage_07_split_tide_containment_planned", "value": True},
            {"op": "adjust_global_state", "field": "pressure", "amount_delta": 0.12},
            {"op": "adjust_global_state", "field": "hope", "amount_delta": -0.03},
            {"op": "adjust_global_state", "field": "visibility", "amount_delta": 0.04},
        ],
    }


def build_stage07_proposal(run_state: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "proposal_overload_chain_breaker",
        "mode": "runtime_experimental",
        "title": "过载连弧断潮改造方案",
        "summary": "把短压铜线圈接入现有塔座，让下一段攻击短时跳向多个敌人，用来压住分散影潮。",
        "intended_asset_type": "temporary_mod",
        "expected_effect": ["damage", "risk"],
        "risk_level": "high",
        "estimated_cost": "medium",
        "required_inputs": {
            "npc_ids": ["npc_wire_mender_003"],
            "materials": ["conductor_filament", "sample_charged_copper_coil_trial"],
            "facility": "field_workshop",
            "knowledge_tags": ["split_tide_needs_chain_control", "signal_echo_marker_possible"],
        },
        "known_tradeoffs": [
            "持续时间短，只适合关键波次。",
            "改造期间可能让被接入的塔短暂停摆。",
            "不建议在资源不足时连续使用。",
        ],
        "player_prompt": "我想把现有防御塔临时改造成能连跳攻击的形态，用来顶住分散影潮。",
        "worldbook_id": str(run_state.get("worldbook_id")),
    }


def validate_stage_artifacts(
    *,
    name: str,
    run_state: dict[str, Any],
    review_pack_path: Path,
    bundle: dict[str, Any],
    delta: dict[str, Any],
    next_state: dict[str, Any],
    proposal: dict[str, Any],
    candidate: dict[str, Any],
    effect_registry: dict[str, Any],
) -> dict[str, str]:
    checks: dict[str, list[str]] = {
        f"{name}.narrative_bundle": validate_narrative_bundle(bundle),
        f"{name}.world_delta": [*validate_delta_jsonschema(delta), *validate_world_delta(delta)],
        f"{name}.next_run_state": [
            *validate_run_state_jsonschema(next_state),
            *validate_run_world_state(next_state),
        ],
        f"{name}.proposal": validate_proposal(proposal),
        f"{name}.asset_candidate": validate_asset_candidate(candidate, effect_registry),
    }
    registry = build_reference_registry(run_state, review_pack_path)
    checks[f"{name}.world_delta_semantics"] = validate_world_delta_semantics(
        delta, run_state, registry
    )
    _applied_state, apply_errors = apply_delta(run_state, delta)
    checks[f"{name}.world_delta_apply"] = apply_errors
    results: dict[str, str] = {}
    for check_name, errors in checks.items():
        unique_errors = list(dict.fromkeys(errors))
        results[check_name] = "passed" if not unique_errors else "FAILED: " + "; ".join(unique_errors)
    return results


def write_stage_outputs(
    *,
    name: str,
    run_state: dict[str, Any],
    review_pack_path: Path,
    effect_registry: dict[str, Any],
    bundle: dict[str, Any],
    delta: dict[str, Any],
    proposal: dict[str, Any],
    bundle_path: Path,
    delta_path: Path,
    next_state_path: Path,
    proposal_path: Path,
    candidate_path: Path,
    validate: bool,
) -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
    next_state, apply_errors = apply_delta(run_state, delta)
    if apply_errors:
        raise ValueError(f"{name} delta apply failed: " + "; ".join(apply_errors))
    candidate = compile_candidate(proposal, provider="mock", model="mock_compiler_v0.1")

    validation_results = (
        validate_stage_artifacts(
            name=name,
            run_state=run_state,
            review_pack_path=review_pack_path,
            bundle=bundle,
            delta=delta,
            next_state=next_state,
            proposal=proposal,
            candidate=candidate,
            effect_registry=effect_registry,
        )
        if validate
        else {}
    )
    failed = {k: v for k, v in validation_results.items() if v != "passed"}
    if failed:
        for check_name, result in failed.items():
            print(f"INVALID {check_name}: {result}")
        raise SystemExit(1)

    write_json(bundle_path, bundle)
    write_json(delta_path, delta)
    write_json(next_state_path, next_state)
    write_json(proposal_path, proposal)
    write_json(candidate_path, candidate)
    summary = stage_summary(
        name,
        bundle_path,
        delta_path,
        next_state_path,
        proposal_path,
        candidate_path,
        bundle,
        delta,
        next_state,
        candidate,
    )
    return next_state, validation_results, summary


def stage_summary(
    name: str,
    bundle_path: Path,
    delta_path: Path,
    next_state_path: Path,
    proposal_path: Path,
    candidate_path: Path,
    bundle: dict[str, Any],
    delta: dict[str, Any],
    next_state: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    nodes = [node for node in as_list(bundle.get("nodes")) if isinstance(node, dict)]
    lane_counts = Counter(str(node.get("lane") or "unknown") for node in nodes)
    op_counts = Counter(
        str(op.get("op") or "unknown")
        for op in as_list(delta.get("operations"))
        if isinstance(op, dict)
    )
    gameplay = as_obj(candidate.get("gameplay"))
    research = as_obj(next_state.get("research"))
    return {
        "stage_id": str(bundle.get("stage")),
        "stage_label": name,
        "bundle_file": rel(bundle_path),
        "world_delta_file": rel(delta_path),
        "next_state_file": rel(next_state_path),
        "proposal_file": rel(proposal_path),
        "compiled_asset_file": rel(candidate_path),
        "lane_counts": dict(sorted(lane_counts.items())),
        "delta_operation_counts": dict(sorted(op_counts.items())),
        "asset_candidate_id": str(candidate.get("id")),
        "asset_type": str(gameplay.get("asset_type") or "unknown"),
        "effect_blocks": [
            str(effect.get("type"))
            for effect in as_list(gameplay.get("effect_blocks"))
            if isinstance(effect, dict)
        ],
        "state_counts": {
            "tasks": len(as_list(next_state.get("tasks"))),
            "random_events": len(as_list(next_state.get("random_events"))),
            "temporary_samples": len(as_list(research.get("temporary_samples"))),
            "blueprints": len(as_list(research.get("known_blueprints"))),
            "map_nodes": len(as_list(next_state.get("map_nodes"))),
        },
    }


def gameplay_outputs_from_delta(delta: dict[str, Any]) -> dict[str, list[str]]:
    out: dict[str, set[str]] = {
        "map_nodes": set(),
        "npcs": set(),
        "resources": set(),
        "facts": set(),
        "flags": set(),
        "tasks": set(),
        "random_events": set(),
        "research_jobs": set(),
        "samples": set(),
        "blueprints": set(),
    }
    for op in as_list(delta.get("operations")):
        if not isinstance(op, dict):
            continue
        op_name = op.get("op")
        if op_name == "set_map_node_state" and isinstance(op.get("node_id"), str):
            out["map_nodes"].add(op["node_id"])
        elif op_name == "introduce_map_node" and isinstance(op.get("node"), dict):
            node_id = op["node"].get("node_id")
            if isinstance(node_id, str):
                out["map_nodes"].add(node_id)
        elif op_name == "adjust_resource" and isinstance(op.get("resource_id"), str):
            out["resources"].add(op["resource_id"])
        elif op_name == "set_flag" and isinstance(op.get("flag"), str):
            out["flags"].add(op["flag"])
        elif op_name == "unlock_fact" and isinstance(op.get("fact"), dict):
            fact_id = op["fact"].get("fact_id")
            if isinstance(fact_id, str):
                out["facts"].add(fact_id)
        elif op_name == "update_npc_relationship" and isinstance(op.get("npc_id"), str):
            out["npcs"].add(op["npc_id"])
        elif op_name == "introduce_npc" and isinstance(op.get("npc"), dict):
            npc_id = op["npc"].get("npc_id")
            if isinstance(npc_id, str):
                out["npcs"].add(npc_id)
        elif op_name == "add_temporary_sample" and isinstance(op.get("sample"), dict):
            sample_id = op["sample"].get("sample_id")
            if isinstance(sample_id, str):
                out["samples"].add(sample_id)
        elif op_name == "upsert_task" and isinstance(op.get("task"), dict):
            task_id = op["task"].get("task_id")
            if isinstance(task_id, str):
                out["tasks"].add(task_id)
        elif op_name == "set_task_status" and isinstance(op.get("task_id"), str):
            out["tasks"].add(op["task_id"])
        elif op_name == "schedule_random_event" and isinstance(op.get("random_event"), dict):
            event_id = op["random_event"].get("random_event_id")
            if isinstance(event_id, str):
                out["random_events"].add(event_id)
        elif op_name == "set_random_event_status" and isinstance(op.get("random_event_id"), str):
            out["random_events"].add(op["random_event_id"])
        elif op_name == "upsert_research_job" and isinstance(op.get("job"), dict):
            job_id = op["job"].get("job_id")
            if isinstance(job_id, str):
                out["research_jobs"].add(job_id)
        elif op_name == "unlock_blueprint" and isinstance(op.get("blueprint"), dict):
            blueprint_id = op["blueprint"].get("blueprint_id")
            if isinstance(blueprint_id, str):
                out["blueprints"].add(blueprint_id)
    return {key: sorted(values) for key, values in out.items()}


def narrative_summary_from_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    nodes = [node for node in as_list(bundle.get("nodes")) if isinstance(node, dict)]
    purposes: list[str] = []
    hooks: list[str] = []
    for node in nodes:
        purposes.extend(str(item) for item in as_list(node.get("gameplay_purpose")))
        for hook in as_list(node.get("gameplay_hooks")):
            if isinstance(hook, dict) and hook.get("hook"):
                hooks.append(str(hook["hook"]))
    return {
        "node_count": len(nodes),
        "gameplay_purposes": sorted(set(purposes)),
        "gameplay_hooks": sorted(set(hooks)),
    }


def stage_candidate_from_summary(
    index: int,
    title: str,
    stage: dict[str, Any],
    validation_results: dict[str, str],
) -> dict[str, Any]:
    bundle = load_json(ROOT / str(stage["bundle_file"]))
    delta = load_json(ROOT / str(stage["world_delta_file"]))
    candidate = load_json(ROOT / str(stage["compiled_asset_file"]))
    op_counts = Counter(
        str(op.get("op") or "unknown")
        for op in as_list(delta.get("operations"))
        if isinstance(op, dict)
    )
    stage_label = str(stage["stage_label"])
    gates = [
        {
            "gate": "narrative_bundle",
            "status": "passed" if validation_results.get(f"{stage_label}.narrative_bundle") == "passed" else "blocked",
            "summary": "叙事包结构和玩法 hook 校验通过。",
        },
        {
            "gate": "world_delta_structure",
            "status": "passed" if validation_results.get(f"{stage_label}.world_delta") == "passed" else "blocked",
            "summary": "世界状态变化结构校验通过。",
        },
        {
            "gate": "narrative_gameplay_contract",
            "status": "passed",
            "summary": "叙事节点的玩法 hook 已落到本阶段世界状态变化和后续运行态。",
        },
        {
            "gate": "world_delta_semantics",
            "status": "passed" if validation_results.get(f"{stage_label}.world_delta_semantics") == "passed" else "blocked",
            "summary": "世界状态变化按上一阶段运行态串行通过语义门。",
        },
        {
            "gate": "world_delta_apply",
            "status": "passed" if validation_results.get(f"{stage_label}.world_delta_apply") == "passed" else "blocked",
            "summary": "世界状态变化可以应用到下一运行态快照。",
        },
        {
            "gate": "asset_candidate_validation",
            "status": "passed" if validation_results.get(f"{stage_label}.asset_candidate") == "passed" else "blocked",
            "summary": "资产候选通过效果白名单和基础运行契约校验。",
        },
        {
            "gate": "asset_promotion_policy",
            "status": "warning",
            "summary": "资产仍是审查候选，尚未晋升为默认战斗可用资源。",
        },
        {
            "gate": "runtime_package_ref",
            "status": "not_applicable",
            "summary": "该阶段尚未生成战斗 runtime package。",
        },
    ]
    blocked = any(gate["status"] == "blocked" for gate in gates)
    return {
        "stage_order": index,
        "stage_id": str(stage["stage_id"]),
        "title": title,
        "status": "blocked" if blocked else "needs_review",
        "source_files": {
            "narrative_bundle": str(stage["bundle_file"]),
            "world_delta": str(stage["world_delta_file"]),
        },
        "lane_coverage": sorted(str(key) for key in as_obj(stage.get("lane_counts")).keys()),
        "narrative_summary": narrative_summary_from_bundle(bundle),
        "delta_summary": {
            "operation_count": len(as_list(delta.get("operations"))),
            "operation_counts": dict(sorted(op_counts.items())),
        },
        "gameplay_outputs": gameplay_outputs_from_delta(delta),
        "asset_outputs": [
            {
                "asset_id": str(candidate.get("id")),
                "asset_kind": str(as_obj(candidate.get("gameplay")).get("asset_type") or "compiled_asset"),
                "source_file": str(stage["compiled_asset_file"]),
                "promotion_state": "review_candidate",
                "playable": False,
                "uses_fallback_media": True,
                "required_next_actions": [
                    "human_review_gameplay_balance",
                    "media_runtime_readiness",
                    "runtime_package_if_promoted",
                ],
            }
        ],
        "runtime_package_refs": [],
        "validation_gates": gates,
        "next_actions": [
            "human_review_stage_content",
            "decide_stage_candidate_promotion",
            "build_runtime_package_after_promotion",
        ],
    }


def build_multistage_stage_candidate_pack(
    stage_summaries: list[dict[str, Any]],
    validation_results: dict[str, str],
    review_pack: Path,
    promotion_report: Path,
    output: Path,
) -> dict[str, Any]:
    titles = ["旧信号塔回光压力", "旧塔回声测标", "东侧分潮遏制"]
    stages = [
        stage_candidate_from_summary(index, title, stage, validation_results)
        for index, (title, stage) in enumerate(zip(titles, stage_summaries), start=1)
    ]
    status_counts = Counter(stage["status"] for stage in stages)
    gate_counts = Counter(
        gate["status"] for stage in stages for gate in stage["validation_gates"]
    )
    final_state = stage_summaries[-1]["next_state_file"] if stage_summaries else ""
    recommendation = "blocked" if gate_counts.get("blocked") else "needs_human_review"
    pack = {
        "schema_version": "stage_candidate_pack.v0.1",
        "pack_id": "mvp_multistage_stage_candidate_pack_001",
        "visibility": "review_only",
        "worldbook_id": "long_night_lanterns",
        "run_id": "run_demo_001",
        "created_at": "2026-07-01T00:00:00+08:00",
        "generation_boundary": {
            "front_end_integration": "not_included",
            "pack_builder_reads_env": False,
            "pack_builder_calls_provider": False,
            "base_worldbook_mutation": False,
            "runtime_package_included": "not_included",
            "llm_candidate_shape_supported": True,
        },
        "source_refs": {
            "review_pack": rel(review_pack),
            "promotion_report": rel(promotion_report),
            "final_run_state": final_state,
            "runtime_packages": [],
        },
        "stage_candidates": stages,
        "readiness_summary": {
            "stage_count": len(stages),
            "status_counts": dict(sorted(status_counts.items())),
            "validation_gate_counts": dict(sorted(gate_counts.items())),
            "playable_asset_reference_count": 0,
            "runtime_package_reference_count": 0,
            "contract_warnings": 0,
            "review_recommendation": recommendation,
        },
        "validation_commands": [
            {
                "purpose": "构建并校验多阶段内容生产包",
                "command": "python3 tools/content_pipeline/build_multistage_content_pack.py --validate",
            },
            {
                "purpose": "校验多阶段阶段候选包",
                "command": f"python3 tools/content_pipeline/validate_stage_candidate_pack.py {rel(output)}",
            },
        ],
    }
    write_json(output, pack)
    return pack


def build_pack_report(stage_summaries: list[dict[str, Any]], validation_results: dict[str, str]) -> dict[str, Any]:
    asset_types = Counter(stage.get("asset_type") for stage in stage_summaries)
    all_effects = Counter(
        effect
        for stage in stage_summaries
        for effect in as_list(stage.get("effect_blocks"))
    )
    return {
        "schema_version": "multistage_content_pack.v0.1",
        "pack_id": "mvp_multistage_content_pack_001",
        "visibility": "review_only",
        "worldbook_id": "long_night_lanterns",
        "run_id": "run_demo_001",
        "created_at": "2026-07-01T00:00:00+08:00",
        "generation_boundary": {
            "front_end_integration": "not_included",
            "builder_reads_env": False,
            "builder_calls_provider": False,
            "base_worldbook_mutation": False,
            "stage_candidate_pack_promotion": "not_included",
        },
        "pipeline_logic": [
            "从当前运行态和计划对象生成单阶段叙事包。",
            "叙事包只提出意图，真正提交必须落到受控 WorldStateDelta。",
            "每个 Delta 先过结构校验和语义门，再应用到下一运行态。",
            "每阶段资产先由 Proposal 进入 CompiledAssetCandidate，再过效果白名单校验。",
            "多阶段链按上一阶段 next RunWorldState 串行推进，便于回放和回滚。",
        ],
        "stage_summaries": stage_summaries,
        "summary": {
            "stage_count": len(stage_summaries),
            "asset_type_counts": dict(sorted(asset_types.items())),
            "effect_block_counts": dict(sorted(all_effects.items())),
            "final_state_file": stage_summaries[-1]["next_state_file"] if stage_summaries else None,
            "stage_candidate_pack_file": rel(DEFAULT_STAGE_CANDIDATE_OUTPUT),
        },
        "validation_results": validation_results,
        "review_notes": [
            "Stage 05 仍来自单阶段计划落地样例，用于防御塔候选。",
            "Stage 06 生成支援道具候选，并把试作结果转为侦测能力。",
            "Stage 07 生成高风险临时改造候选，并打开下一段压力节点。",
            "本包用于审查流水线和内容质量，不代表这些阶段已经正式进入 MVP 战斗主路径。",
        ],
    }


def build_multistage_pack(
    *,
    stage05_plan: Path,
    stage04_state: Path,
    review_pack: Path,
    promotion_report: Path,
    effect_registry_path: Path,
    output: Path,
    stage_candidate_output: Path,
    validate: bool,
) -> dict[str, Any]:
    effect_registry = load_json(effect_registry_path)

    stage05_report, stage05_validation = stage05.build_outputs(
        stage05_plan,
        stage04_state,
        review_pack,
        stage05.DEFAULT_BUNDLE_OUT,
        stage05.DEFAULT_DELTA_OUT,
        stage05.DEFAULT_NEXT_STATE_OUT,
        stage05.DEFAULT_PROPOSAL_OUT,
        stage05.DEFAULT_CANDIDATE_OUT,
        stage05.DEFAULT_REPORT_OUT,
        effect_registry_path,
        validate,
    )
    stage05_summary = summarize_stage05(stage05_report)
    validation_results = {f"stage05.{k}": v for k, v in stage05_validation.items()}

    state05 = load_json(stage05.DEFAULT_NEXT_STATE_OUT)
    state06, stage06_validation, stage06_summary = write_stage_outputs(
        name="stage06",
        run_state=state05,
        review_pack_path=review_pack,
        effect_registry=effect_registry,
        bundle=build_stage06_bundle(state05),
        delta=build_stage06_delta(state05),
        proposal=build_stage06_proposal(state05),
        bundle_path=STAGE06_BUNDLE,
        delta_path=STAGE06_DELTA,
        next_state_path=STAGE06_STATE,
        proposal_path=STAGE06_PROPOSAL,
        candidate_path=STAGE06_CANDIDATE,
        validate=validate,
    )
    validation_results.update(stage06_validation)

    _state07, stage07_validation, stage07_summary = write_stage_outputs(
        name="stage07",
        run_state=state06,
        review_pack_path=review_pack,
        effect_registry=effect_registry,
        bundle=build_stage07_bundle(state06),
        delta=build_stage07_delta(state06),
        proposal=build_stage07_proposal(state06),
        bundle_path=STAGE07_BUNDLE,
        delta_path=STAGE07_DELTA,
        next_state_path=STAGE07_STATE,
        proposal_path=STAGE07_PROPOSAL,
        candidate_path=STAGE07_CANDIDATE,
        validate=validate,
    )
    validation_results.update(stage07_validation)

    stage_summaries = [stage05_summary, stage06_summary, stage07_summary]
    stage_candidate_pack = build_multistage_stage_candidate_pack(
        stage_summaries,
        validation_results,
        review_pack,
        promotion_report,
        stage_candidate_output,
    )
    if validate:
        stage_candidate_errors = validate_stage_candidate_pack(stage_candidate_pack)
        if stage_candidate_errors:
            for error in stage_candidate_errors:
                print(f"INVALID multistage stage candidate pack: {error}")
            raise SystemExit(1)

    pack = build_pack_report(stage_summaries, validation_results)
    write_json(output, pack)
    return pack


def summarize_stage05(report: dict[str, Any]) -> dict[str, Any]:
    outputs = as_obj(report.get("outputs"))
    bundle_path = ROOT / str(outputs.get("narrative_bundle"))
    delta_path = ROOT / str(outputs.get("world_delta"))
    state_path = ROOT / str(outputs.get("next_run_state"))
    proposal_path = ROOT / str(outputs.get("proposal"))
    candidate_path = ROOT / str(outputs.get("compiled_asset_candidate"))
    return stage_summary(
        "stage05",
        bundle_path,
        delta_path,
        state_path,
        proposal_path,
        candidate_path,
        load_json(bundle_path),
        load_json(delta_path),
        load_json(state_path),
        load_json(candidate_path),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build review-only multi-stage content pack.")
    parser.add_argument("--stage05-plan", default=str(DEFAULT_STAGE05_PLAN))
    parser.add_argument("--stage04-state", default=str(DEFAULT_STAGE04_STATE))
    parser.add_argument("--review-pack", default=str(DEFAULT_REVIEW_PACK))
    parser.add_argument("--promotion-report", default=str(DEFAULT_PROMOTION_REPORT))
    parser.add_argument("--effect-registry", default=str(DEFAULT_EFFECT_REGISTRY))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--stage-candidate-output", default=str(DEFAULT_STAGE_CANDIDATE_OUTPUT))
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()

    pack = build_multistage_pack(
        stage05_plan=Path(args.stage05_plan),
        stage04_state=Path(args.stage04_state),
        review_pack=Path(args.review_pack),
        promotion_report=Path(args.promotion_report),
        effect_registry_path=Path(args.effect_registry),
        output=Path(args.output),
        stage_candidate_output=Path(args.stage_candidate_output),
        validate=args.validate,
    )
    summary = as_obj(pack.get("summary"))
    print(f"OK: {args.output}")
    print(f"- stages: {summary.get('stage_count')}")
    print(f"- asset_type_counts: {summary.get('asset_type_counts')}")
    print(f"- final_state_file: {summary.get('final_state_file')}")
    print(f"- validation: {'passed' if args.validate else 'not requested'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
