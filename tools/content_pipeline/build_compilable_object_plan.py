#!/usr/bin/env python3
"""Build a deterministic CompilableObjectPlan v0.1 for the next MVP stage.

The plan is a review-only bridge between the current object catalog and later
LLM/DAG generation. It does not read .env, call providers, or export runtime
content.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ASSET_GRAPH_DIR = ROOT / "tools" / "asset_graph"
if str(ASSET_GRAPH_DIR) not in sys.path:
    sys.path.insert(0, str(ASSET_GRAPH_DIR))

from validation_common import load_json, validate_json_schema  # noqa: E402
from validate_compilable_object_plan import validate_compilable_object_plan  # noqa: E402


PLAN_VERSION = "compilable_object_plan.v0.1"
SCHEMA_PATH = ROOT / "shared/schemas/compilable_object_plan.v0.1.schema.json"
DEFAULT_CATALOG = ROOT / "examples/review_packs/mvp_compilable_object_catalog.v0.1.json"
DEFAULT_STAGE_CANDIDATE_PACK = ROOT / "examples/review_packs/mvp_stage_candidate_pack.v0.1.json"
DEFAULT_FINAL_STATE = ROOT / "examples/run_world_states/demo_after_stage_04_wick_store.run_world_state.json"
DEFAULT_REVIEW_PACK = ROOT / "examples/review_packs/mvp_story_asset_review_pack.v0.1.json"
DEFAULT_PROMOTION_REPORT = ROOT / "examples/review_packs/mvp_story_asset_promotion_report.v0.1.json"
DEFAULT_OUTPUT = ROOT / "examples/review_packs/mvp_next_stage_compilable_object_plan.v0.1.json"


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def stable_strings(values: list[Any]) -> list[str]:
    return sorted({str(value) for value in values if isinstance(value, str) and value})


def contract(
    *,
    load_surface: str,
    state_effects: list[str],
    target_export_status: str,
    rollback_policy: str,
    player_visible: bool,
    risk_level: str,
) -> dict[str, Any]:
    return {
        "load_surface": load_surface,
        "state_effects": stable_strings(state_effects),
        "target_export_status": target_export_status,
        "rollback_policy": rollback_policy,
        "player_visible": player_visible,
        "risk_level": risk_level,
    }


def fallback(strategy: str, player_visible_result: str, blocked_result: str) -> dict[str, str]:
    return {
        "strategy": strategy,
        "player_visible_result": player_visible_result,
        "blocked_result": blocked_result,
    }


def request(
    *,
    request_id: str,
    requested_object_id: str,
    object_type: str,
    object_layer: str,
    compile_permission_level: str,
    compile_actor: str,
    intent_summary: str,
    source_signals: list[str],
    dependency_refs: list[str],
    target_outputs: list[str],
    required_validators: list[str],
    acceptance_gates: list[str],
    runtime_contract: dict[str, Any],
    fallback_policy: dict[str, str],
    next_compile_steps: list[str],
    requires_llm: bool,
    requires_media: bool,
    requires_human_review: bool,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    obj = {
        "request_id": request_id,
        "requested_object_id": requested_object_id,
        "object_type": object_type,
        "object_layer": object_layer,
        "compile_permission_level": compile_permission_level,
        "compile_actor": compile_actor,
        "intent_summary": intent_summary,
        "source_signals": stable_strings(source_signals),
        "dependency_refs": stable_strings(dependency_refs),
        "target_outputs": stable_strings(target_outputs),
        "required_validators": stable_strings(required_validators),
        "acceptance_gates": stable_strings(acceptance_gates),
        "runtime_contract": runtime_contract,
        "fallback_policy": fallback_policy,
        "next_compile_steps": stable_strings(next_compile_steps),
        "requires_llm": requires_llm,
        "requires_media": requires_media,
        "requires_human_review": requires_human_review,
    }
    if notes:
        obj["notes"] = stable_strings(notes)
    return obj


def catalog_has(catalog: dict[str, Any], object_id: str) -> bool:
    return any(
        isinstance(obj, dict) and obj.get("object_id") == object_id
        for obj in as_list(catalog.get("objects"))
    )


def build_requests(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    required_seed_refs = [
        "map_node:old_signal_tower",
        "random_event:random_event_old_signal_tower_pressure",
        "fact:old_signal_tower_pressure_hint",
        "material:glow_crystal",
        "npc:npc_road_scout",
    ]
    missing = [ref for ref in required_seed_refs if not catalog_has(catalog, ref)]
    if missing:
        raise ValueError(f"catalog missing required next-stage seed refs: {missing}")

    return [
        request(
            request_id="req_stage_05_old_signal_tower_candidate",
            requested_object_id="stage:act_1_stage_05_old_signal_tower_pressure",
            object_type="stage_candidate",
            object_layer="narrative",
            compile_permission_level="L4_system_rule",
            compile_actor="system",
            intent_summary="把旧信号塔的 pending 压力事件升级为第五阶段候选，同时继续维护世界线与玩家线双线推进。",
            source_signals=[
                "map_node:old_signal_tower",
                "random_event:random_event_old_signal_tower_pressure",
                "fact:old_signal_tower_pressure_hint",
            ],
            dependency_refs=[
                "map_node:old_signal_tower",
                "random_event:random_event_old_signal_tower_pressure",
                "fact:old_signal_tower_pressure_hint",
                "npc:npc_road_scout",
            ],
            target_outputs=[
                "NarrativeEventBundle",
                "WorldStateDelta",
                "StageCandidatePack entry",
            ],
            required_validators=[
                "validate_narrative_bundle.py",
                "validate_world_delta.py",
                "validate_world_delta_semantics.py",
                "validate_narrative_gameplay_contract.py",
                "validate_stage_candidate_pack.py",
            ],
            acceptance_gates=[
                "stage must create or resolve at least one concrete gameplay object",
                "stage must not only append story text",
                "stage must reference no legacy fixture NPC",
            ],
            runtime_contract=contract(
                load_surface="stage_candidate_pack",
                state_effects=["world_line_progress", "player_line_progress", "map_pressure"],
                target_export_status="review_only",
                rollback_policy="delta_replay",
                player_visible=False,
                risk_level="medium",
            ),
            fallback_policy=fallback(
                "keep old signal tower as scouted pending node",
                "旧信号塔仍保持侦察标记，暂不进入下一战。",
                "do_not_emit_stage_05_delta",
            ),
            next_compile_steps=[
                "generate NarrativeEventBundle candidate",
                "generate WorldStateDelta candidate",
                "run semantic gate",
                "append to StageCandidatePack only after review",
            ],
            requires_llm=True,
            requires_media=False,
            requires_human_review=True,
        ),
        request(
            request_id="req_task_stabilize_old_signal_tower",
            requested_object_id="task:task_stabilize_old_signal_tower",
            object_type="quest_task",
            object_layer="narrative",
            compile_permission_level="L3_behavior",
            compile_actor="system",
            intent_summary="生成一个可完成的旧信号塔稳定任务，作为玩家线承接，不允许直接改写主线终局。",
            source_signals=[
                "random_event:random_event_old_signal_tower_pressure",
                "npc:npc_road_scout",
            ],
            dependency_refs=[
                "map_node:old_signal_tower",
                "random_event:random_event_old_signal_tower_pressure",
                "npc:npc_road_scout",
            ],
            target_outputs=["WorldStateDelta.upsert_task", "RunWorldState.tasks[]"],
            required_validators=[
                "validate_world_delta.py",
                "validate_world_delta_semantics.py",
                "validate_narrative_gameplay_contract.py",
            ],
            acceptance_gates=[
                "task node_id must exist",
                "task objective refs must be detectable by game systems",
                "task reward refs must not grant final victory",
            ],
            runtime_contract=contract(
                load_surface="run_world_state",
                state_effects=["objective_chain", "map_pressure_resolution"],
                target_export_status="runtime_ready",
                rollback_policy="delta_replay",
                player_visible=True,
                risk_level="low",
            ),
            fallback_policy=fallback(
                "convert to scouting hint if objective chain is invalid",
                "斥候只标记旧信号塔风险，任务暂不开放。",
                "skip upsert_task",
            ),
            next_compile_steps=[
                "include in WorldStateDelta as upsert_task",
                "link random event or research job",
                "verify final RunWorldState contains task",
            ],
            requires_llm=True,
            requires_media=False,
            requires_human_review=False,
        ),
        request(
            request_id="req_material_resonant_glass_candidate",
            requested_object_id="material:resonant_glass_shard",
            object_type="material",
            object_layer="economy",
            compile_permission_level="L4_system_rule",
            compile_actor="system",
            intent_summary="根据辉晶和旧信号塔回光扰动规划一个候选材料，用作后续折射/回声类资产编译约束。",
            source_signals=["material:glow_crystal", "fact:old_signal_tower_pressure_hint"],
            dependency_refs=["material:glow_crystal", "map_node:old_signal_tower"],
            target_outputs=["WorldStateDelta.adjust_resource or candidate material registration", "future material affordance"],
            required_validators=[
                "validate_run_world_state.py",
                "validate_narrative_gameplay_contract.py",
                "CompilableObjectCatalog review",
            ],
            acceptance_gates=[
                "material must be introduced as candidate until canonicalized",
                "material affordance must map to existing effect families",
            ],
            runtime_contract=contract(
                load_surface="run_world_state",
                state_effects=["compile_capability", "resource_budget"],
                target_export_status="candidate_only",
                rollback_policy="delta_replay",
                player_visible=True,
                risk_level="medium",
            ),
            fallback_policy=fallback(
                "use existing glow_crystal only",
                "本阶段只使用辉晶线索，不新增材料。",
                "do_not_adjust_resource_for_candidate_material",
            ),
            next_compile_steps=[
                "ask LLM to propose material affordances",
                "map affordances to effect catalog",
                "human review before canonical material registration",
            ],
            requires_llm=True,
            requires_media=False,
            requires_human_review=True,
        ),
        request(
            request_id="req_npc_signal_keeper_candidate",
            requested_object_id="npc:npc_signal_keeper_candidate",
            object_type="npc",
            object_layer="narrative",
            compile_permission_level="L3_behavior",
            compile_actor="system",
            intent_summary="规划一个功能 NPC 候选，用于旧信号塔阶段的路线解释、风险提示和研发评审。",
            source_signals=["map_node:old_signal_tower", "npc:npc_road_scout"],
            dependency_refs=["map_node:old_signal_tower", "npc:npc_road_scout"],
            target_outputs=["WorldStateDelta.introduce_npc", "NarrativeEventBundle participant"],
            required_validators=[
                "validate_world_delta.py",
                "validate_world_delta_semantics.py",
                "validate_narrative_gameplay_contract.py",
            ],
            acceptance_gates=[
                "npc id must be candidate-prefixed or review-approved",
                "npc gameplay role must serve route, research, or risk explanation",
                "npc cannot overwrite legacy fixture NPC",
            ],
            runtime_contract=contract(
                load_surface="run_world_state",
                state_effects=["npc_state", "strategy_explanation", "research_review"],
                target_export_status="candidate_only",
                rollback_policy="delta_replay",
                player_visible=True,
                risk_level="medium",
            ),
            fallback_policy=fallback(
                "reuse npc_road_scout as adviser",
                "北路斥候继续承担旧信号塔提示，不新增 NPC。",
                "skip introduce_npc",
            ),
            next_compile_steps=[
                "generate NPC role card",
                "introduce via WorldStateDelta only if semantic gate accepts candidate NPC",
                "record in StageCandidatePack next actions",
            ],
            requires_llm=True,
            requires_media=False,
            requires_human_review=True,
        ),
        request(
            request_id="req_asset_echo_prism_relay",
            requested_object_id="asset:asset_echo_prism_relay",
            object_type="tower_blueprint",
            object_layer="entity",
            compile_permission_level="L2_entity",
            compile_actor="player",
            intent_summary="规划一个利用辉晶/回光扰动的折射中继塔候选，用于旧信号塔压力战的路径控制或弱点揭示。",
            source_signals=[
                "material:glow_crystal",
                "map_node:old_signal_tower",
                "random_event:random_event_old_signal_tower_pressure",
            ],
            dependency_refs=[
                "material:glow_crystal",
                "map_node:old_signal_tower",
                "random_event:random_event_old_signal_tower_pressure",
                "task:task_stabilize_old_signal_tower",
            ],
            target_outputs=[
                "Proposal",
                "CompiledAssetCandidate",
                "expected media roles: tower_sprite/icon/battle_preview",
                "promotion report entry",
            ],
            required_validators=[
                "validate_proposal.py",
                "validate_asset_candidate.py",
                "simulate_asset_candidate.py",
                "score_asset_candidate.py",
                "asset_promotion_policy.py",
            ],
            acceptance_gates=[
                "asset must fit existing effect catalog",
                "asset must pass simulation or remain candidate_only",
                "media can use fallback skin until real media readiness passes",
            ],
            runtime_contract=contract(
                load_surface="battle_runtime",
                state_effects=["battle_capability", "path_control", "weakness_hint"],
                target_export_status="fallback_ready",
                rollback_policy="remove_from_runtime_package",
                player_visible=True,
                risk_level="medium",
            ),
            fallback_policy=fallback(
                "compile support item instead of tower if stats are unstable",
                "工坊只交付一次性回光标记器，不交付完整塔。",
                "keep as candidate_only asset",
            ),
            next_compile_steps=[
                "generate player-visible Proposal",
                "compile asset candidate with LLM",
                "validate/simulate/score candidate",
                "run media prompt and fallback media plan",
            ],
            requires_llm=True,
            requires_media=True,
            requires_human_review=True,
        ),
        request(
            request_id="req_report_old_signal_compile_review",
            requested_object_id="report:old_signal_compile_review",
            object_type="compile_report",
            object_layer="ui_explanation",
            compile_permission_level="L1_presentation",
            compile_actor="system",
            intent_summary="生成一份玩家可见的世界内研发说明，解释为什么旧信号塔阶段只能交付候选或 fallback 资产。",
            source_signals=[
                "asset:asset_echo_prism_relay",
                "material:resonant_glass_shard",
                "npc:npc_signal_keeper_candidate",
            ],
            dependency_refs=[
                "asset:asset_echo_prism_relay",
                "material:resonant_glass_shard",
                "npc:npc_signal_keeper_candidate",
            ],
            target_outputs=["player-safe compile report", "review dossier note"],
            required_validators=["player_text_technical_term_filter", "CompilableObjectPlan review"],
            acceptance_gates=[
                "text must not expose world-external implementation terms",
                "text must explain limitations as world-internal research uncertainty",
            ],
            runtime_contract=contract(
                load_surface="review_pack",
                state_effects=["player_explanation", "review_note"],
                target_export_status="review_only",
                rollback_policy="not_needed",
                player_visible=True,
                risk_level="low",
            ),
            fallback_policy=fallback(
                "use deterministic generic report text",
                "工坊记录：样品仍在校准，暂以保守方案交付。",
                "omit report from runtime",
            ),
            next_compile_steps=[
                "generate player-safe report text",
                "scan for technical terms",
                "attach to StageCandidatePack notes after review",
            ],
            requires_llm=True,
            requires_media=False,
            requires_human_review=False,
        ),
    ]


def validation_commands() -> list[dict[str, str]]:
    return [
        {
            "purpose": "构建并校验下一阶段可编译对象计划",
            "command": "python3 tools/content_pipeline/build_compilable_object_plan.py --validate",
        },
        {
            "purpose": "单独校验下一阶段可编译对象计划",
            "command": "python3 tools/content_pipeline/validate_compilable_object_plan.py examples/review_packs/mvp_next_stage_compilable_object_plan.v0.1.json",
        },
    ]


def summarize(requests: list[dict[str, Any]]) -> dict[str, Any]:
    layer_counts = Counter(str(item.get("object_layer")) for item in requests)
    level_counts = Counter(str(item.get("compile_permission_level")) for item in requests)
    actor_counts = Counter(str(item.get("compile_actor")) for item in requests)
    risk_counts = Counter(str(as_obj(item.get("runtime_contract")).get("risk_level")) for item in requests)
    return {
        "request_count": len(requests),
        "layer_counts": dict(sorted(layer_counts.items())),
        "permission_level_counts": dict(sorted(level_counts.items())),
        "compile_actor_counts": dict(sorted(actor_counts.items())),
        "risk_counts": dict(sorted(risk_counts.items())),
        "requires_llm_count": sum(1 for item in requests if item.get("requires_llm") is True),
        "requires_media_count": sum(1 for item in requests if item.get("requires_media") is True),
        "requires_human_review_count": sum(
            1 for item in requests if item.get("requires_human_review") is True
        ),
    }


def build_plan(
    catalog_path: Path,
    stage_candidate_pack_path: Path,
    final_state_path: Path,
    review_pack_path: Path,
    promotion_report_path: Path,
    created_at: str,
) -> dict[str, Any]:
    catalog = load_json(catalog_path)
    final_state = load_json(final_state_path)
    requests = build_requests(catalog)
    return {
        "schema_version": PLAN_VERSION,
        "plan_id": "mvp_next_stage_compilable_object_plan_001",
        "visibility": "review_only",
        "worldbook_id": str(catalog.get("worldbook_id") or final_state.get("worldbook_id")),
        "run_id": str(catalog.get("run_id") or final_state.get("run_id")),
        "created_at": created_at,
        "generation_boundary": {
            "front_end_integration": "not_included",
            "plan_builder_reads_env": False,
            "plan_builder_calls_provider": False,
            "base_worldbook_mutation": False,
            "runtime_export_included": "not_included",
            "llm_fill_allowed_after_review": True,
        },
        "source_refs": {
            "compilable_object_catalog": rel(catalog_path),
            "stage_candidate_pack": rel(stage_candidate_pack_path),
            "final_run_state": rel(final_state_path),
            "review_pack": rel(review_pack_path),
            "promotion_report": rel(promotion_report_path),
        },
        "planning_context": {
            "target_stage_id": "act_1_stage_05_old_signal_tower_pressure",
            "target_stage_title": "旧信号塔回光压力",
            "stage_intent": "把旧信号塔 pending 压力从线索推进为可审查阶段候选，并引导一次受控资产编译。",
            "world_line_seed": "旧信号塔附近的回光扰动增强，可能暴露新的路径压力或捷径。",
            "player_line_seed": "玩家可通过侦察、稳定任务和辉晶材料尝试研发折射/回声类防御方案。",
            "active_constraints": [
                "不修改基础世界书",
                "不直接给出最终胜利或终局神器",
                "候选 NPC 和候选材料必须先保留为 candidate_only",
                "默认战斗资产最多 fallback_ready，真实媒体仍需后续 readiness",
                "玩家侧文本不得暴露底层调用、结构模板或调试记录等世界外细节",
            ],
            "evidence_object_refs": [
                "map_node:old_signal_tower",
                "random_event:random_event_old_signal_tower_pressure",
                "fact:old_signal_tower_pressure_hint",
                "material:glow_crystal",
                "npc:npc_road_scout",
            ],
        },
        "object_requests": requests,
        "summary": summarize(requests),
        "validation_commands": validation_commands(),
    }


def validate_plan(plan: dict[str, Any]) -> list[str]:
    errors = validate_json_schema(plan, SCHEMA_PATH)
    errors.extend(validate_compilable_object_plan(plan))
    seen: set[str] = set()
    out: list[str] = []
    for error in errors:
        if error not in seen:
            seen.add(error)
            out.append(error)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Build CompilableObjectPlan v0.1.")
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    parser.add_argument("--stage-candidate-pack", default=str(DEFAULT_STAGE_CANDIDATE_PACK))
    parser.add_argument("--final-state", default=str(DEFAULT_FINAL_STATE))
    parser.add_argument("--review-pack", default=str(DEFAULT_REVIEW_PACK))
    parser.add_argument("--promotion-report", default=str(DEFAULT_PROMOTION_REPORT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--created-at", default="2026-07-01T00:00:00+08:00")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()

    try:
        plan = build_plan(
            Path(args.catalog),
            Path(args.stage_candidate_pack),
            Path(args.final_state),
            Path(args.review_pack),
            Path(args.promotion_report),
            args.created_at,
        )
    except ValueError as exc:
        print(f"INVALID CompilableObjectPlan seed: {exc}")
        return 1

    output = Path(args.output)
    write_json(output, plan)

    errors = validate_plan(plan) if args.validate else []
    if errors:
        print("INVALID CompilableObjectPlan")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"OK: {output}")
    print(f"- schema_version: {plan.get('schema_version')}")
    print(f"- requests: {plan.get('summary', {}).get('request_count')}")
    print(f"- target_stage: {plan.get('planning_context', {}).get('target_stage_id')}")
    if args.validate:
        print("- validation: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
