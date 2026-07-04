#!/usr/bin/env python3
"""Build a deterministic Stage 05 realization draft from CompilableObjectPlan.

This builder is deliberately offline: it does not read .env, call providers, or
promote the result into the player runtime. Its job is to prove that a planned
set of compilable objects can become reviewable artifacts:

CompilableObjectPlan -> NarrativeEventBundle -> WorldStateDelta -> next
RunWorldState, plus a Proposal -> CompiledAssetCandidate draft.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CONTENT_DIR = ROOT / "tools" / "content_pipeline"
NARRATIVE_DIR = ROOT / "tools" / "narrative"
WORLD_STATE_DIR = ROOT / "tools" / "world_state"

for path in (CONTENT_DIR, NARRATIVE_DIR, WORLD_STATE_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from apply_world_delta import apply_delta  # noqa: E402
from mock_compile_proposal import compile_candidate  # noqa: E402
from validate_asset_candidate import validate as validate_asset_candidate  # noqa: E402
from validate_narrative_bundle import validate_narrative_bundle  # noqa: E402
from validate_proposal import validate as validate_proposal  # noqa: E402
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


DEFAULT_PLAN = ROOT / "examples/review_packs/mvp_next_stage_compilable_object_plan.v0.1.json"
DEFAULT_RUN_STATE = ROOT / "examples/run_world_states/demo_after_stage_04_wick_store.run_world_state.json"
DEFAULT_REVIEW_PACK = ROOT / "examples/review_packs/mvp_story_asset_review_pack.v0.1.json"
DEFAULT_BUNDLE_OUT = ROOT / "examples/narrative_bundles/stage_05_old_signal_tower_pressure.narrative_event_bundle.json"
DEFAULT_DELTA_OUT = ROOT / "examples/world_deltas/stage_05_old_signal_tower_pressure.world_delta.json"
DEFAULT_NEXT_STATE_OUT = ROOT / "examples/run_world_states/demo_after_stage_05_old_signal_tower.run_world_state.json"
DEFAULT_PROPOSAL_OUT = ROOT / "examples/proposals/echo_prism_relay.proposal.json"
DEFAULT_CANDIDATE_OUT = ROOT / "examples/compiled_assets/echo_prism_relay.compiled_asset.json"
DEFAULT_REPORT_OUT = ROOT / "examples/review_packs/mvp_stage05_plan_realization_report.v0.1.json"
DEFAULT_EFFECT_REGISTRY = ROOT / "shared/module_registry/effect_blocks.v0.1.json"

STAGE_ID = "act_1_stage_05_old_signal_tower_pressure"
DELTA_ID = "delta_stage_05_old_signal_tower_pressure"


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


def next_turn(run_state: dict[str, Any]) -> int:
    event_turns = [
        event.get("turn")
        for event in as_list(run_state.get("event_log"))
        if isinstance(event, dict) and isinstance(event.get("turn"), int)
    ]
    progress_turn = as_obj(run_state.get("progress")).get("turn")
    if isinstance(progress_turn, int):
        event_turns.append(progress_turn)
    return (max(event_turns) if event_turns else 0) + 1


def stage_context(plan: dict[str, Any]) -> dict[str, Any]:
    context = as_obj(plan.get("planning_context"))
    if context.get("target_stage_id") != STAGE_ID:
        raise ValueError(
            "Stage 05 realization builder expects target_stage_id "
            f"{STAGE_ID!r}, got {context.get('target_stage_id')!r}"
        )
    return context


def proposed_delta_summary(ops: list[str], summary: str) -> dict[str, Any]:
    return {"expected_operations": ops, "summary": summary}


def build_narrative_bundle(plan: dict[str, Any], run_state: dict[str, Any]) -> dict[str, Any]:
    context = stage_context(plan)
    run_id = str(plan.get("run_id") or run_state.get("run_id"))
    worldbook_id = str(plan.get("worldbook_id") or run_state.get("worldbook_id"))
    turn = next_turn(run_state)

    return {
        "schema_version": "narrative_event_bundle.v0.1",
        "bundle_id": "bundle_stage_05_old_signal_tower_pressure",
        "run_id": run_id,
        "worldbook_id": worldbook_id,
        "source": "world_tick",
        "created_turn": turn,
        "stage": STAGE_ID,
        "lane": "shared",
        "commit_policy": {
            "candidate_generation": "parallel_allowed",
            "commit_gate": "world_state_delta_required",
            "commit_order": "manual_review_then_serial",
        },
        "worldbook_base_mutation_allowed": False,
        "nodes": [
            {
                "node_id": "node_stage05_world_pressure_visible",
                "stage": STAGE_ID,
                "phase": "old_signal_tower_pressure_planned",
                "lane": "world_line",
                "scope": "map",
                "trigger": {
                    "kind": "world_tick",
                    "ref": "random_event_old_signal_tower_pressure",
                    "summary": str(context.get("world_line_seed") or "旧信号塔压力被重新标记。"),
                },
                "prerequisites": [
                    "old_signal_tower_pressure_hint",
                    "stage_04_wick_store_defense_completed",
                ],
                "visibility": "player_visible",
                "presentation": {
                    "scene_type": "map_event",
                    "title": "旧信号塔的回光抬升",
                    "blocks": [
                        {
                            "text": "北路尽头的旧信号塔被一圈冷白余光托起，塔脚下的影潮像被折回的潮线，开始沿旧路聚集。"
                        }
                    ],
                },
                "gameplay_purpose": [
                    "advance_main_pressure",
                    "modify_map_node_state",
                    "trigger_random_event",
                ],
                "gameplay_hooks": [
                    {
                        "hook": "modify_map_node_state",
                        "target_ref": "old_signal_tower",
                        "summary": "旧信号塔从已侦察节点升级为受压节点。",
                    },
                    {
                        "hook": "trigger_random_event",
                        "target_ref": "random_event_old_signal_tower_pressure",
                        "summary": "旧信号塔压力事件由等待转为可处理。",
                    },
                ],
                "npc_refs": ["npc_road_scout"],
                "npc_introductions": [],
                "proposed_world_delta_ref": DELTA_ID,
                "proposed_delta_summary": proposed_delta_summary(
                    ["set_map_node_state", "set_random_event_status", "adjust_global_state"],
                    "推动旧信号塔地图节点和压力事件进入可审查状态。",
                ),
            },
            {
                "node_id": "node_stage05_player_stabilize_task",
                "stage": STAGE_ID,
                "phase": "old_signal_tower_pressure_planned",
                "lane": "player_line",
                "scope": "quest",
                "trigger": {
                    "kind": "map_entered",
                    "ref": "old_signal_tower",
                    "summary": str(context.get("player_line_seed") or "玩家线获得旧信号塔稳定目标。"),
                },
                "prerequisites": ["npc_road_scout", "glow_crystal_discovered"],
                "visibility": "player_visible",
                "presentation": {
                    "scene_type": "dialogue",
                    "title": "斥候的短旗",
                    "blocks": [
                        {
                            "speaker_id": "npc_road_scout",
                            "speaker_name": "北路斥候",
                            "text": "旧塔的回光会把影子拖出原路。若把辉晶压进临时棱座，也许能让来敌先显形，再慢下来。",
                        },
                        {
                            "text": "新的稳定任务被记入路牌，样品会先在现场小规模试作。"
                        },
                    ],
                },
                "gameplay_purpose": [
                    "create_quest_hook",
                    "create_research_need",
                    "offer_workshop_hook",
                ],
                "gameplay_hooks": [
                    {
                        "hook": "create_quest_hook",
                        "target_ref": "task_stabilize_old_signal_tower",
                        "summary": "创建稳定旧信号塔的玩家线任务。",
                    },
                    {
                        "hook": "create_research_need",
                        "target_ref": "research_echo_prism_relay_trial",
                        "summary": "把现场样品接入一次可回滚研发任务。",
                    },
                ],
                "npc_refs": ["npc_road_scout"],
                "npc_introductions": [],
                "proposed_world_delta_ref": DELTA_ID,
                "proposed_delta_summary": proposed_delta_summary(
                    ["upsert_task", "upsert_research_job", "update_npc_relationship"],
                    "生成可完成任务，并把后续试作挂到当前运行态。",
                ),
            },
            {
                "node_id": "node_stage05_resonant_sample_and_asset",
                "stage": STAGE_ID,
                "phase": "old_signal_tower_pressure_planned",
                "lane": "shared",
                "scope": "workshop",
                "trigger": {
                    "kind": "player_choice",
                    "ref": "task_stabilize_old_signal_tower",
                    "summary": "玩家选择把辉晶用于旧塔现场试作。",
                },
                "prerequisites": ["glow_crystal", "old_signal_tower_pressure_hint"],
                "visibility": "player_visible",
                "presentation": {
                    "scene_type": "workshop_notice",
                    "title": "回光玻片样本",
                    "blocks": [
                        {
                            "text": "一枚辉晶被磨成薄片后贴上旧塔铜槽，表面浮出断续的回声纹。它还不是稳定材料，只能先当试作样本。"
                        }
                    ],
                },
                "gameplay_purpose": [
                    "introduce_material",
                    "create_research_need",
                    "reward_player_choice",
                ],
                "gameplay_hooks": [
                    {
                        "hook": "introduce_material",
                        "target_ref": "sample_resonant_glass_shard_trial",
                        "summary": "用临时样本承载候选材料，不直接注册为正式库存资源。",
                    },
                    {
                        "hook": "reward_player_choice",
                        "target_ref": "asset_echo_prism_relay",
                        "summary": "为下一次试作防御塔方案提供候选资产。",
                    },
                ],
                "npc_refs": ["npc_road_scout"],
                "npc_introductions": [],
                "proposed_world_delta_ref": DELTA_ID,
                "proposed_delta_summary": proposed_delta_summary(
                    ["adjust_resource", "add_temporary_sample", "unlock_fact", "schedule_random_event"],
                    "消耗现有辉晶，生成临时样本和后续回流风险事件。",
                ),
            },
        ],
    }


def build_world_delta(plan: dict[str, Any], run_state: dict[str, Any]) -> dict[str, Any]:
    run_id = str(plan.get("run_id") or run_state.get("run_id"))
    worldbook_id = str(plan.get("worldbook_id") or run_state.get("worldbook_id"))
    turn = next_turn(run_state)
    return {
        "schema_version": "world_state_delta.v0.1",
        "delta_id": DELTA_ID,
        "run_id": run_id,
        "worldbook_id": worldbook_id,
        "source": "narrative_event",
        "created_turn": turn,
        "summary": "旧信号塔的回光压力被转为可处理节点，并开启一次现场稳定试作。",
        "operations": [
            {"op": "set_progress_phase", "phase": "old_signal_tower_pressure_planned"},
            {
                "op": "set_map_node_state",
                "node_id": "old_signal_tower",
                "patch": {
                    "status": "contested",
                    "threat_level": 3,
                    "visibility": "visible",
                    "available_actions": [
                        "prepare_defense",
                        "field_research",
                        "stabilize_signal",
                    ],
                },
            },
            {
                "op": "set_random_event_status",
                "random_event_id": "random_event_old_signal_tower_pressure",
                "status": "available",
            },
            {
                "op": "update_npc_relationship",
                "npc_id": "npc_road_scout",
                "relationship_delta": {"trust": 0.08},
            },
            {
                "op": "upsert_task",
                "task": {
                    "task_id": "task_stabilize_old_signal_tower",
                    "kind": "defense",
                    "status": "active",
                    "title": "稳定旧信号塔回光",
                    "summary": "旧信号塔的回光扰动正在引来新的影潮，需要在塔脚布置临时棱座，并保护样品完成一次现场稳定试作。",
                    "node_id": "old_signal_tower",
                    "npc_id": "npc_road_scout",
                    "objective_refs": ["old_signal_tower", "glow_crystal"],
                    "reward_refs": [
                        "sample_resonant_glass_shard_trial",
                        "asset_echo_prism_relay",
                    ],
                },
            },
            {"op": "adjust_resource", "resource_id": "glow_crystal", "amount_delta": -1},
            {
                "op": "add_temporary_sample",
                "sample": {
                    "sample_id": "sample_resonant_glass_shard_trial",
                    "display_name": "回光玻片样本",
                    "source_delta_id": DELTA_ID,
                    "summary": "辉晶被磨成薄片并贴合旧塔铜槽后，形成一份只能支撑现场试作的回光样本。",
                },
            },
            {
                "op": "upsert_research_job",
                "job": {
                    "job_id": "research_echo_prism_relay_trial",
                    "status": "queued",
                    "started_turn": turn,
                    "source_task_id": "task_stabilize_old_signal_tower",
                    "source_sample_id": "sample_resonant_glass_shard_trial",
                    "expected_turns": 1,
                    "expected_output": "回光棱镜中继塔试作",
                },
            },
            {
                "op": "unlock_fact",
                "fact": {
                    "fact_id": "old_signal_tower_resonance_measured",
                    "source": "old_signal_tower_pressure",
                    "visibility": "player_known",
                    "summary": "旧信号塔的回光扰动可以短暂显形来敌，也会让影潮更快锁定塔脚。",
                },
            },
            {
                "op": "schedule_random_event",
                "random_event": {
                    "random_event_id": "random_event_signal_backwash",
                    "event_type": "research_opportunity",
                    "status": "pending",
                    "summary": "回光玻片完成试作后，可能出现一次短暂回流，可用于强化折射类装置，也可能提高旧塔压力。",
                    "node_id": "old_signal_tower",
                    "trigger_turn": turn,
                    "related_task_id": "task_stabilize_old_signal_tower",
                },
            },
            {
                "op": "append_event",
                "event": {
                    "event_id": "old_signal_tower_pressure_planned",
                    "turn": turn,
                    "kind": "world",
                    "summary": "旧信号塔的回光压力被纳入下一轮防守计划，现场试作任务开启。",
                },
            },
            {"op": "set_flag", "flag": "stage_05_old_signal_tower_pressure_planned", "value": True},
            {"op": "adjust_global_state", "field": "pressure", "amount_delta": 0.08},
            {"op": "adjust_global_state", "field": "visibility", "amount_delta": 0.05},
            {"op": "adjust_global_state", "field": "hope", "amount_delta": -0.02},
        ],
    }


def build_proposal(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "proposal_echo_prism_relay",
        "mode": "runtime_experimental",
        "title": "回光棱镜中继塔方案",
        "summary": "把辉晶压入临时棱镜底座，引导旧信号塔的回光扰动，使来敌短暂显形并减速。",
        "intended_asset_type": "tower_blueprint",
        "expected_effect": ["control", "scouting"],
        "risk_level": "medium",
        "estimated_cost": "medium",
        "required_inputs": {
            "npc_ids": ["npc_road_scout"],
            "materials": ["glow_crystal", "conductor_filament"],
            "facility": "field_workshop",
            "knowledge_tags": [
                "old_signal_tower_pressure_hint",
                "glow_crystal_discovered",
            ],
        },
        "known_tradeoffs": [
            "需要消耗辉晶样本，正式蓝图前只能少量试作。",
            "控制效果依赖旧信号塔附近的回光环境，离开该区域后需要重新校准。",
        ],
        "player_prompt": "我想把辉晶做成一个能标记并拖慢敌人的折射中继塔，帮助守住旧信号塔。",
        "worldbook_id": str(plan.get("worldbook_id") or "long_night_lanterns"),
    }


def build_report(
    plan: dict[str, Any],
    bundle_path: Path,
    delta_path: Path,
    next_state_path: Path,
    proposal_path: Path,
    candidate_path: Path,
    validation_results: dict[str, str],
) -> dict[str, Any]:
    requests = [req for req in as_list(plan.get("object_requests")) if isinstance(req, dict)]
    request_types = Counter(str(req.get("object_type") or "unknown") for req in requests)
    compile_actors = Counter(str(req.get("compile_actor") or "unknown") for req in requests)
    return {
        "schema_version": "stage05_plan_realization_report.v0.1",
        "report_id": "mvp_stage05_plan_realization_report_001",
        "visibility": "review_only",
        "source_plan": rel(DEFAULT_PLAN),
        "target_stage_id": STAGE_ID,
        "core_artifact_alignment": {
            "alignment_state": "review_only_not_applicable",
            "reason": (
                "Stage05PlanRealizationReport 是 review-only 计划落地审查报告；它证明 plan 可以落地成 "
                "NarrativeEventBundle、WorldStateDelta、next RunWorldState、Proposal 和 "
                "CompiledAssetCandidate，但自身不是 ContextPackage、FactEntry、CGOP 或 "
                "WorldStateDeltaTransaction。"
            ),
            "expected_core_artifacts": [],
            "present_core_artifacts": [],
            "runtime_activation_allowed": False,
            "world_mutation_allowed": False,
            "next_action": (
                "后续核心对象迁移应针对该 report 引用的 NarrativeEventBundle、WorldStateDelta、"
                "WorldStateDeltaTransaction、CompiledAssetCandidate、StageCandidatePack 或 runtime package，"
                "而不是激活整个 realization report。"
            ),
        },
        "core_decisions": [
            "叙事对象按状态转移对象处理，必须落到 WorldStateDelta 或可审查的后续对象。",
            "本阶段只使用已在运行态或审查边界内的 NPC 和资源；候选材料先进入临时样本。",
            "对象依赖由 Object Graph 表达，单个对象的生成再进入 Compile DAG。",
            "玩家侧运行时不暴露底层调用、调试记录或审查字段。",
        ],
        "planned_request_counts": dict(sorted(request_types.items())),
        "compile_actor_counts": dict(sorted(compile_actors.items())),
        "outputs": {
            "narrative_bundle": rel(bundle_path),
            "world_delta": rel(delta_path),
            "next_run_state": rel(next_state_path),
            "proposal": rel(proposal_path),
            "compiled_asset_candidate": rel(candidate_path),
        },
        "runtime_contract_summary": {
            "new_task_id": "task_stabilize_old_signal_tower",
            "new_sample_id": "sample_resonant_glass_shard_trial",
            "new_research_job_id": "research_echo_prism_relay_trial",
            "asset_candidate_id": "asset_echo_prism_relay",
            "state_commit": "review_draft_delta_applied_to_next_state_snapshot",
            "promotion_status": "not_promoted_to_stage_candidate_pack",
        },
        "validation_results": validation_results,
    }


def validate_all(
    plan: dict[str, Any],
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
        "stage_context": [],
        "narrative_bundle": validate_narrative_bundle(bundle),
        "world_delta": [*validate_delta_jsonschema(delta), *validate_world_delta(delta)],
        "proposal": validate_proposal(proposal),
        "asset_candidate": validate_asset_candidate(candidate, effect_registry),
        "next_run_state": [
            *validate_run_state_jsonschema(next_state),
            *validate_run_world_state(next_state),
        ],
    }
    try:
        stage_context(plan)
    except ValueError as exc:
        checks["stage_context"].append(str(exc))

    registry = build_reference_registry(run_state, review_pack_path)
    checks["world_delta_semantics"] = validate_world_delta_semantics(
        delta, run_state, registry
    )
    _applied_state, apply_errors = apply_delta(run_state, delta)
    checks["world_delta_apply"] = apply_errors

    results: dict[str, str] = {}
    for name, errors in checks.items():
        unique_errors = list(dict.fromkeys(errors))
        if unique_errors:
            results[name] = "FAILED: " + "; ".join(unique_errors)
        else:
            results[name] = "passed"
    return results


def build_outputs(
    plan_path: Path,
    run_state_path: Path,
    review_pack_path: Path,
    bundle_out: Path,
    delta_out: Path,
    next_state_out: Path,
    proposal_out: Path,
    candidate_out: Path,
    report_out: Path,
    effect_registry_path: Path,
    validate: bool,
) -> tuple[dict[str, Any], dict[str, str]]:
    plan = load_json(plan_path)
    run_state = load_json(run_state_path)
    effect_registry = load_json(effect_registry_path)

    bundle = build_narrative_bundle(plan, run_state)
    delta = build_world_delta(plan, run_state)
    proposal = build_proposal(plan)
    candidate = compile_candidate(proposal, provider="mock", model="mock_compiler_v0.1")
    next_state, apply_errors = apply_delta(run_state, delta)
    if apply_errors:
        raise ValueError("Stage 05 delta could not be applied: " + "; ".join(apply_errors))

    validation_results = (
        validate_all(
            plan,
            run_state,
            review_pack_path,
            bundle,
            delta,
            next_state,
            proposal,
            candidate,
            effect_registry,
        )
        if validate
        else {}
    )
    if validate:
        failed = {k: v for k, v in validation_results.items() if v != "passed"}
        if failed:
            for name, result in failed.items():
                print(f"INVALID {name}: {result}")
            raise SystemExit(1)

    write_json(bundle_out, bundle)
    write_json(delta_out, delta)
    write_json(next_state_out, next_state)
    write_json(proposal_out, proposal)
    write_json(candidate_out, candidate)

    report = build_report(
        plan,
        bundle_out,
        delta_out,
        next_state_out,
        proposal_out,
        candidate_out,
        validation_results,
    )
    write_json(report_out, report)
    return report, validation_results


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Stage 05 plan realization artifacts.")
    parser.add_argument("--plan", default=str(DEFAULT_PLAN))
    parser.add_argument("--run-state", default=str(DEFAULT_RUN_STATE))
    parser.add_argument("--review-pack", default=str(DEFAULT_REVIEW_PACK))
    parser.add_argument("--bundle-out", default=str(DEFAULT_BUNDLE_OUT))
    parser.add_argument("--delta-out", default=str(DEFAULT_DELTA_OUT))
    parser.add_argument("--next-state-out", default=str(DEFAULT_NEXT_STATE_OUT))
    parser.add_argument("--proposal-out", default=str(DEFAULT_PROPOSAL_OUT))
    parser.add_argument("--candidate-out", default=str(DEFAULT_CANDIDATE_OUT))
    parser.add_argument("--report-out", default=str(DEFAULT_REPORT_OUT))
    parser.add_argument("--effect-registry", default=str(DEFAULT_EFFECT_REGISTRY))
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()

    report, validation_results = build_outputs(
        Path(args.plan),
        Path(args.run_state),
        Path(args.review_pack),
        Path(args.bundle_out),
        Path(args.delta_out),
        Path(args.next_state_out),
        Path(args.proposal_out),
        Path(args.candidate_out),
        Path(args.report_out),
        Path(args.effect_registry),
        args.validate,
    )

    outputs = as_obj(report.get("outputs"))
    print(f"OK: {args.report_out}")
    print(f"- target_stage_id: {report.get('target_stage_id')}")
    print(f"- outputs: {len(outputs)}")
    print(f"- validation: {'passed' if args.validate else 'not requested'}")
    if args.validate:
        for name in sorted(validation_results):
            print(f"  - {name}: {validation_results[name]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
