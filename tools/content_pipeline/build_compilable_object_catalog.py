#!/usr/bin/env python3
"""Build a CompilableObjectCatalog v0.1 from current MVP review artifacts.

This builder is deterministic. It does not read .env, does not call providers,
and does not build a frontend runtime package.
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
from validate_compilable_object_catalog import validate_compilable_object_catalog  # noqa: E402


CATALOG_VERSION = "compilable_object_catalog.v0.1"
SCHEMA_PATH = ROOT / "shared/schemas/compilable_object_catalog.v0.1.schema.json"
DEFAULT_STAGE_CANDIDATE_PACK = ROOT / "examples/review_packs/mvp_stage_candidate_pack.v0.1.json"
DEFAULT_PROMOTION_REPORT = ROOT / "examples/review_packs/mvp_story_asset_promotion_report.v0.1.json"
DEFAULT_FINAL_STATE = ROOT / "examples/run_world_states/demo_after_stage_04_wick_store.run_world_state.json"
DEFAULT_OUTPUT = ROOT / "examples/review_packs/mvp_compilable_object_catalog.v0.1.json"


PERMISSION_LEVELS = [
    {
        "level": "L1_presentation",
        "name": "表现编译",
        "player_open_policy": "open",
        "description": "名称、说明、图标、外观、特效等低风险表现对象。",
    },
    {
        "level": "L2_entity",
        "name": "实体编译",
        "player_open_policy": "guarded",
        "description": "防御塔、道具、陷阱、NPC、怪物等完整运行实体，需要运行时契约。",
    },
    {
        "level": "L3_behavior",
        "name": "行为与局部叙事编译",
        "player_open_policy": "guarded",
        "description": "技能、Buff、任务、随机事件、NPC 建议等状态机对象，必须 DSL 化或 Delta 化。",
    },
    {
        "level": "L4_system_rule",
        "name": "系统规则编译",
        "player_open_policy": "system_assisted",
        "description": "地图、经济、进度、科技树、关卡规则等影响面较大的系统对象。",
    },
    {
        "level": "L5_engine",
        "name": "引擎与底层编译",
        "player_open_policy": "developer_only",
        "description": "存档、寻路、渲染、底层代码和安全策略；MVP 不进入玩家侧编译。",
    },
]

OBJECT_LAYERS = [
    {
        "layer": "visual",
        "default_permission_level": "L1_presentation",
        "player_exposure": "player_visible",
        "description": "图像、图标、动画、特效、音效和表现文本。",
        "example_types": ["icon", "tower_sprite", "attack_vfx", "dialogue_text"],
    },
    {
        "layer": "entity",
        "default_permission_level": "L2_entity",
        "player_exposure": "player_visible",
        "description": "可部署、可交互、可被运行时加载的游戏实体。",
        "example_types": ["tower_blueprint", "support_item", "temporary_sample", "npc"],
    },
    {
        "layer": "behavior",
        "default_permission_level": "L3_behavior",
        "player_exposure": "player_influenced",
        "description": "技能、触发器、状态效果、临时改制和可执行行为片段。",
        "example_types": ["temporary_mod", "skill", "buff", "target_selector"],
    },
    {
        "layer": "rule",
        "default_permission_level": "L4_system_rule",
        "player_exposure": "system_side",
        "description": "影响全局或多对象交互的系统规则。",
        "example_types": ["synergy_rule", "unlock_rule", "world_flag"],
    },
    {
        "layer": "level",
        "default_permission_level": "L4_system_rule",
        "player_exposure": "player_visible",
        "description": "地图节点、路线、战斗节点、波次和关卡环境。",
        "example_types": ["map_node", "battle_node", "encounter", "wave"],
    },
    {
        "layer": "narrative",
        "default_permission_level": "L3_behavior",
        "player_exposure": "player_influenced",
        "description": "剧情节点、任务、随机事件、事实、对话和分支。",
        "example_types": ["stage_candidate", "quest_task", "random_event", "world_fact"],
    },
    {
        "layer": "progression",
        "default_permission_level": "L4_system_rule",
        "player_exposure": "player_visible",
        "description": "研发任务、蓝图、解锁路线、科技节点和长期成长。",
        "example_types": ["research_job", "blueprint", "tech_node"],
    },
    {
        "layer": "economy",
        "default_permission_level": "L4_system_rule",
        "player_exposure": "player_visible",
        "description": "素材、资源、掉落、成本、配方和库存压力。",
        "example_types": ["material", "resource", "drop_table", "recipe"],
    },
    {
        "layer": "adaptive",
        "default_permission_level": "L4_system_rule",
        "player_exposure": "system_side",
        "description": "玩家画像、难度调节、AI Director 和推荐策略。",
        "example_types": ["difficulty_director", "player_profile"],
    },
    {
        "layer": "ui_explanation",
        "default_permission_level": "L1_presentation",
        "player_exposure": "player_visible",
        "description": "教程、报告、复盘、提示和编译解释文本。",
        "example_types": ["compile_report", "battle_report", "tooltip"],
    },
    {
        "layer": "toolchain",
        "default_permission_level": "L5_engine",
        "player_exposure": "developer_side",
        "description": "测试、DAG 模板、Validator、Prompt 模板和调试报告。",
        "example_types": ["validator", "workflow_graph", "test_suite"],
    },
]


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


def object_model() -> dict[str, Any]:
    return {
        "definition": (
            "AI 可编译对象是能被描述、结构化、分解、校验、导出并被运行时或审查流程执行的游戏对象。"
        ),
        "permission_levels": PERMISSION_LEVELS,
        "object_layers": OBJECT_LAYERS,
    }


def runtime_contract(
    *,
    load_surface: str,
    state_effects: list[str],
    export_status: str,
    rollback_policy: str,
    player_visible: bool,
    risk_level: str,
) -> dict[str, Any]:
    return {
        "load_surface": load_surface,
        "state_effects": stable_strings(state_effects),
        "export_status": export_status,
        "rollback_policy": rollback_policy,
        "player_visible": player_visible,
        "risk_level": risk_level,
    }


def make_object(
    *,
    object_id: str,
    object_type: str,
    object_layer: str,
    compile_permission_level: str,
    compile_actor: str,
    source_kind: str,
    source_files: list[str],
    source_ids: list[str],
    stage_refs: list[str],
    dependency_refs: list[str],
    validators: list[str],
    contract: dict[str, Any],
    review_status: str,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    obj = {
        "object_id": object_id,
        "object_type": object_type,
        "object_layer": object_layer,
        "compile_permission_level": compile_permission_level,
        "compile_actor": compile_actor,
        "source_kind": source_kind,
        "source_files": stable_strings(source_files),
        "source_ids": stable_strings(source_ids),
        "stage_refs": stable_strings(stage_refs),
        "dependency_refs": stable_strings(dependency_refs),
        "validators": stable_strings(validators),
        "runtime_contract": contract,
        "review_status": review_status,
    }
    if notes:
        obj["notes"] = stable_strings(notes)
    return obj


def asset_layer_and_level(asset_kind: str) -> tuple[str, str, str]:
    if asset_kind == "temporary_mod":
        return "behavior", "L3_behavior", "player"
    return "entity", "L2_entity", "player"


def asset_export_status(asset: dict[str, Any]) -> str:
    state = str(asset.get("promotion_state") or "")
    if state == "usable_runtime_fixture":
        return "runtime_ready"
    if state == "fallback_ready":
        return "fallback_ready"
    if state.startswith("candidate_only"):
        return "candidate_only"
    return "review_only"


def asset_risk(asset: dict[str, Any]) -> str:
    if asset_export_status(asset) == "candidate_only" or asset.get("blocking_reasons"):
        return "high"
    if asset.get("warnings") or asset.get("uses_fallback_media"):
        return "medium"
    return "low"


def asset_objects(promotion_report: dict[str, Any]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    stage_refs: dict[str, set[str]] = {}
    gameplay_roles: dict[str, set[str]] = {}
    for stage in as_list(promotion_report.get("stages")):
        if not isinstance(stage, dict):
            continue
        stage_id = str(stage.get("stage_id") or "")
        for asset in as_list(stage.get("assets")):
            if not isinstance(asset, dict):
                continue
            asset_id = str(asset.get("asset_id") or "")
            if not asset_id:
                continue
            by_id.setdefault(asset_id, asset)
            stage_refs.setdefault(asset_id, set()).add(stage_id)
            if asset.get("gameplay_role"):
                gameplay_roles.setdefault(asset_id, set()).add(str(asset["gameplay_role"]))

    objects: list[dict[str, Any]] = []
    for asset_id, asset in sorted(by_id.items()):
        asset_kind = str(asset.get("asset_kind") or "compiled_asset")
        layer, level, actor = asset_layer_and_level(asset_kind)
        world_registration = as_obj(asset.get("world_registration"))
        deps = [
            *(f"npc:{item}" for item in as_list(world_registration.get("npc_ids"))),
            *(f"material:{item}" for item in as_list(world_registration.get("material_ids"))),
        ]
        export_status = asset_export_status(asset)
        objects.append(
            make_object(
                object_id=f"asset:{asset_id}",
                object_type=asset_kind,
                object_layer=layer,
                compile_permission_level=level,
                compile_actor=actor,
                source_kind=str(asset.get("source_kind") or "asset"),
                source_files=[
                    str(asset.get("source_file") or ""),
                    rel(DEFAULT_PROMOTION_REPORT),
                ],
                source_ids=[asset_id, str(asset.get("compiled_candidate_id") or "")],
                stage_refs=sorted(stage_refs.get(asset_id, set())),
                dependency_refs=deps,
                validators=[
                    "validate_asset_candidate.py",
                    "simulate_asset_candidate.py",
                    "score_asset_candidate.py",
                    "asset_promotion_policy.py",
                ],
                contract=runtime_contract(
                    load_surface="battle_runtime" if export_status in {"runtime_ready", "fallback_ready"} else "review_pack",
                    state_effects=["battle_capability", asset_kind],
                    export_status=export_status,
                    rollback_policy="remove_from_runtime_package",
                    player_visible=bool(asset.get("playable")),
                    risk_level=asset_risk(asset),
                ),
                review_status=str(asset.get("review_status") or asset.get("promotion_state") or "review_needed"),
                notes=[
                    *stable_strings(as_list(asset.get("warnings"))),
                    *stable_strings(as_list(asset.get("blocking_reasons"))),
                    *stable_strings(list(gameplay_roles.get(asset_id, set()))),
                ],
            )
        )
        score = as_obj(as_obj(asset.get("policy_evidence")).get("score"))
        for role in stable_strings(as_list(score.get("expected_media_roles"))):
            objects.append(
                make_object(
                    object_id=f"visual:{asset_id}:{role}",
                    object_type=role,
                    object_layer="visual",
                    compile_permission_level="L1_presentation",
                    compile_actor="system",
                    source_kind="expected_media_role",
                    source_files=[
                        str(asset.get("source_file") or ""),
                        rel(DEFAULT_PROMOTION_REPORT),
                    ],
                    source_ids=[asset_id, role],
                    stage_refs=sorted(stage_refs.get(asset_id, set())),
                    dependency_refs=[f"asset:{asset_id}"],
                    validators=[
                        "asset_promotion_policy.py",
                        "media_consistency_report.v0.1",
                        "media_runtime_readiness_report.v0.1",
                    ],
                    contract=runtime_contract(
                        load_surface=(
                            "battle_runtime"
                            if asset_export_status(asset) in {"runtime_ready", "fallback_ready"}
                            else "review_pack"
                        ),
                        state_effects=["visual_presentation", role],
                        export_status=asset_export_status(asset),
                        rollback_policy="remove_from_runtime_package",
                        player_visible=bool(asset.get("playable")),
                        risk_level=asset_risk(asset),
                    ),
                    review_status=(
                        "fallback_media_role"
                        if asset.get("uses_fallback_media")
                        else str(asset.get("review_status") or "media_review_needed")
                    ),
                    notes=[
                        "expected_media_role",
                        *stable_strings(as_list(asset.get("warnings"))),
                    ],
                )
            )
    return objects


def stage_objects(stage_pack: dict[str, Any]) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for stage in as_list(stage_pack.get("stage_candidates")):
        if not isinstance(stage, dict):
            continue
        stage_id = str(stage.get("stage_id") or "")
        gameplay_outputs = as_obj(stage.get("gameplay_outputs"))
        state_effects = [
            key
            for key, values in sorted(gameplay_outputs.items())
            if isinstance(values, list) and values
        ]
        source_files = as_obj(stage.get("source_files"))
        objects.append(
            make_object(
                object_id=f"stage:{stage_id}",
                object_type="stage_candidate",
                object_layer="narrative",
                compile_permission_level="L4_system_rule",
                compile_actor="system",
                source_kind="stage_candidate_pack",
                source_files=[
                    rel(DEFAULT_STAGE_CANDIDATE_PACK),
                    str(source_files.get("narrative_bundle") or ""),
                    str(source_files.get("world_delta") or ""),
                    str(source_files.get("battle_config") or ""),
                ],
                source_ids=[stage_id],
                stage_refs=[stage_id],
                dependency_refs=[
                    *(f"asset:{asset.get('asset_id')}" for asset in as_list(stage.get("asset_outputs")) if isinstance(asset, dict)),
                    *(f"runtime_package:{ref.get('package_id')}" for ref in as_list(stage.get("runtime_package_refs")) if isinstance(ref, dict)),
                ],
                validators=[
                    "validate_narrative_bundle.py",
                    "validate_world_delta.py",
                    "validate_narrative_gameplay_contract.py",
                    "validate_stage_candidate_pack.py",
                ],
                contract=runtime_contract(
                    load_surface="stage_candidate_pack",
                    state_effects=state_effects,
                    export_status="review_only",
                    rollback_policy="delta_replay",
                    player_visible=False,
                    risk_level="medium" if stage.get("status") != "reviewed_fixture" else "low",
                ),
                review_status=str(stage.get("status") or "review_needed"),
            )
        )
    return objects


def run_state_objects(final_state: dict[str, Any]) -> list[dict[str, Any]]:
    source = rel(DEFAULT_FINAL_STATE)
    objects: list[dict[str, Any]] = []
    for node in as_list(final_state.get("map_nodes")):
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("node_id") or "")
        objects.append(
            make_object(
                object_id=f"map_node:{node_id}",
                object_type="map_node",
                object_layer="level",
                compile_permission_level="L4_system_rule",
                compile_actor="system",
                source_kind="run_world_state",
                source_files=[source],
                source_ids=[node_id],
                stage_refs=[],
                dependency_refs=[],
                validators=["validate_run_world_state.py", "validate_world_delta_semantics.py"],
                contract=runtime_contract(
                    load_surface="run_world_state",
                    state_effects=["map_visibility", "available_actions", "threat_level"],
                    export_status="runtime_ready",
                    rollback_policy="delta_replay",
                    player_visible=True,
                    risk_level="low" if int(node.get("threat_level") or 0) <= 1 else "medium",
                ),
                review_status=str(node.get("status") or "known"),
            )
        )
    for npc in as_list(final_state.get("npcs")):
        if not isinstance(npc, dict):
            continue
        npc_id = str(npc.get("npc_id") or "")
        objects.append(
            make_object(
                object_id=f"npc:{npc_id}",
                object_type="npc",
                object_layer="narrative",
                compile_permission_level="L3_behavior",
                compile_actor="system",
                source_kind="run_world_state",
                source_files=[source],
                source_ids=[npc_id],
                stage_refs=[],
                dependency_refs=[f"map_node:{npc.get('location_node_id')}"] if npc.get("location_node_id") else [],
                validators=["validate_run_world_state.py", "validate_world_delta_semantics.py"],
                contract=runtime_contract(
                    load_surface="run_world_state",
                    state_effects=[
                        *stable_strings(as_list(npc.get("narrative_roles"))),
                        *stable_strings(as_list(npc.get("gameplay_roles"))),
                    ],
                    export_status="runtime_ready",
                    rollback_policy="delta_replay",
                    player_visible=True,
                    risk_level="medium" if str(npc_id).startswith(("engineer_", "scout_")) else "low",
                ),
                review_status=str(npc.get("availability") or "present"),
            )
        )
    for resource in as_list(final_state.get("resources")):
        if not isinstance(resource, dict):
            continue
        resource_id = str(resource.get("resource_id") or "")
        objects.append(
            make_object(
                object_id=f"material:{resource_id}",
                object_type="material",
                object_layer="economy",
                compile_permission_level="L4_system_rule",
                compile_actor="system",
                source_kind="run_world_state",
                source_files=[source],
                source_ids=[resource_id],
                stage_refs=[],
                dependency_refs=[],
                validators=["validate_run_world_state.py", "validate_narrative_gameplay_contract.py"],
                contract=runtime_contract(
                    load_surface="run_world_state",
                    state_effects=["compile_capability", "resource_budget"],
                    export_status="runtime_ready",
                    rollback_policy="delta_replay",
                    player_visible=True,
                    risk_level="low",
                ),
                review_status="available" if int(resource.get("amount") or 0) > 0 else "depleted",
            )
        )
    for task in as_list(final_state.get("tasks")):
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("task_id") or "")
        objects.append(
            make_object(
                object_id=f"task:{task_id}",
                object_type="quest_task",
                object_layer="narrative",
                compile_permission_level="L3_behavior",
                compile_actor="system",
                source_kind="run_world_state",
                source_files=[source],
                source_ids=[task_id],
                stage_refs=[],
                dependency_refs=[
                    *(f"ref:{item}" for item in as_list(task.get("objective_refs"))),
                    *(f"ref:{item}" for item in as_list(task.get("reward_refs"))),
                    *([f"map_node:{task.get('node_id')}"] if task.get("node_id") else []),
                    *([f"npc:{task.get('npc_id')}"] if task.get("npc_id") else []),
                ],
                validators=[
                    "validate_run_world_state.py",
                    "validate_world_delta_semantics.py",
                    "validate_narrative_gameplay_contract.py",
                ],
                contract=runtime_contract(
                    load_surface="run_world_state",
                    state_effects=["objective_chain", "reward_refs", "world_progress"],
                    export_status="runtime_ready",
                    rollback_policy="delta_replay",
                    player_visible=True,
                    risk_level="low",
                ),
                review_status=str(task.get("status") or "unknown"),
            )
        )
    for event in as_list(final_state.get("random_events")):
        if not isinstance(event, dict):
            continue
        event_id = str(event.get("random_event_id") or "")
        objects.append(
            make_object(
                object_id=f"random_event:{event_id}",
                object_type="random_event",
                object_layer="narrative",
                compile_permission_level="L3_behavior",
                compile_actor="system",
                source_kind="run_world_state",
                source_files=[source],
                source_ids=[event_id],
                stage_refs=[],
                dependency_refs=[
                    *([f"map_node:{event.get('node_id')}"] if event.get("node_id") else []),
                    *([f"task:{event.get('related_task_id')}"] if event.get("related_task_id") else []),
                ],
                validators=[
                    "validate_run_world_state.py",
                    "validate_world_delta_semantics.py",
                    "validate_narrative_gameplay_contract.py",
                ],
                contract=runtime_contract(
                    load_surface="run_world_state",
                    state_effects=["pressure_event", "branch_trigger", "world_progress"],
                    export_status="runtime_ready",
                    rollback_policy="delta_replay",
                    player_visible=True,
                    risk_level="medium" if event.get("status") in {"pending", "available"} else "low",
                ),
                review_status=str(event.get("status") or "unknown"),
            )
        )
    research = as_obj(final_state.get("research"))
    for job in as_list(research.get("active_jobs")):
        if not isinstance(job, dict):
            continue
        job_id = str(job.get("job_id") or "")
        objects.append(
            make_object(
                object_id=f"research_job:{job_id}",
                object_type="research_job",
                object_layer="progression",
                compile_permission_level="L4_system_rule",
                compile_actor="system",
                source_kind="run_world_state",
                source_files=[source],
                source_ids=[job_id],
                stage_refs=[],
                dependency_refs=[
                    *([f"task:{job.get('source_task_id')}"] if job.get("source_task_id") else []),
                    *([f"sample:{job.get('source_sample_id')}"] if job.get("source_sample_id") else []),
                ],
                validators=["validate_run_world_state.py", "validate_narrative_gameplay_contract.py"],
                contract=runtime_contract(
                    load_surface="run_world_state",
                    state_effects=["research_progress", "unlock_candidate"],
                    export_status="runtime_ready",
                    rollback_policy="delta_replay",
                    player_visible=True,
                    risk_level="low",
                ),
                review_status=str(job.get("status") or "unknown"),
            )
        )
    for blueprint in as_list(research.get("known_blueprints")):
        if not isinstance(blueprint, dict):
            continue
        blueprint_id = str(blueprint.get("blueprint_id") or "")
        objects.append(
            make_object(
                object_id=f"blueprint:{blueprint_id}",
                object_type="blueprint",
                object_layer="progression",
                compile_permission_level="L4_system_rule",
                compile_actor="system",
                source_kind="run_world_state",
                source_files=[source],
                source_ids=[blueprint_id],
                stage_refs=[],
                dependency_refs=[f"research_job:{blueprint.get('source')}"] if blueprint.get("source") else [],
                validators=["validate_run_world_state.py", "validate_narrative_gameplay_contract.py"],
                contract=runtime_contract(
                    load_surface="run_world_state",
                    state_effects=["unlock_asset", "future_compile_capability"],
                    export_status="runtime_ready",
                    rollback_policy="delta_replay",
                    player_visible=True,
                    risk_level="low",
                ),
                review_status="known",
            )
        )
    for sample in as_list(research.get("temporary_samples")):
        if not isinstance(sample, dict):
            continue
        sample_id = str(sample.get("sample_id") or "")
        objects.append(
            make_object(
                object_id=f"sample:{sample_id}",
                object_type="temporary_sample",
                object_layer="entity",
                compile_permission_level="L2_entity",
                compile_actor="system",
                source_kind="run_world_state",
                source_files=[source],
                source_ids=[sample_id],
                stage_refs=[],
                dependency_refs=[f"delta:{sample.get('source_delta_id')}"] if sample.get("source_delta_id") else [],
                validators=["validate_run_world_state.py", "validate_narrative_gameplay_contract.py"],
                contract=runtime_contract(
                    load_surface="run_world_state",
                    state_effects=["temporary_asset", "research_input"],
                    export_status="runtime_ready",
                    rollback_policy="delta_replay",
                    player_visible=True,
                    risk_level="low",
                ),
                review_status="available",
                notes=[str(sample.get("summary") or "")],
            )
        )
    for fact in as_list(final_state.get("unlocked_facts")):
        if not isinstance(fact, dict):
            continue
        fact_id = str(fact.get("fact_id") or "")
        objects.append(
            make_object(
                object_id=f"fact:{fact_id}",
                object_type="world_fact",
                object_layer="narrative",
                compile_permission_level="L3_behavior",
                compile_actor="system",
                source_kind="run_world_state",
                source_files=[source],
                source_ids=[fact_id],
                stage_refs=[],
                dependency_refs=[],
                validators=["validate_run_world_state.py", "validate_narrative_gameplay_contract.py"],
                contract=runtime_contract(
                    load_surface="run_world_state",
                    state_effects=["knowledge_gate", "future_trigger_context"],
                    export_status="runtime_ready",
                    rollback_policy="delta_replay",
                    player_visible=str(fact.get("visibility")) == "player_known",
                    risk_level="low",
                ),
                review_status=str(fact.get("visibility") or "known"),
            )
        )
    for flag_id, value in sorted(as_obj(final_state.get("flags")).items()):
        objects.append(
            make_object(
                object_id=f"flag:{flag_id}",
                object_type="world_flag",
                object_layer="rule",
                compile_permission_level="L4_system_rule",
                compile_actor="system",
                source_kind="run_world_state",
                source_files=[source],
                source_ids=[flag_id],
                stage_refs=[],
                dependency_refs=[],
                validators=["validate_run_world_state.py", "validate_world_delta_semantics.py"],
                contract=runtime_contract(
                    load_surface="run_world_state",
                    state_effects=["branch_condition", "progress_gate"],
                    export_status="runtime_ready",
                    rollback_policy="delta_replay",
                    player_visible=False,
                    risk_level="low",
                ),
                review_status=f"value:{bool(value)}",
            )
        )
    return objects


def validation_commands() -> list[dict[str, str]]:
    return [
        {
            "purpose": "构建并校验可编译对象目录",
            "command": "python3 tools/content_pipeline/build_compilable_object_catalog.py --validate",
        },
        {
            "purpose": "单独校验可编译对象目录",
            "command": "python3 tools/content_pipeline/validate_compilable_object_catalog.py examples/review_packs/mvp_compilable_object_catalog.v0.1.json",
        },
    ]


def summarize(objects: list[dict[str, Any]]) -> dict[str, Any]:
    layer_counts = Counter(str(obj.get("object_layer")) for obj in objects)
    level_counts = Counter(str(obj.get("compile_permission_level")) for obj in objects)
    export_counts = Counter(str(as_obj(obj.get("runtime_contract")).get("export_status")) for obj in objects)
    risk_counts = Counter(str(as_obj(obj.get("runtime_contract")).get("risk_level")) for obj in objects)
    player_exposed_count = sum(
        1 for obj in objects if as_obj(obj.get("runtime_contract")).get("player_visible") is True
    )
    review_required_count = sum(
        1
        for obj in objects
        if as_obj(obj.get("runtime_contract")).get("export_status")
        in {"candidate_only", "review_only", "not_exported"}
    )
    return {
        "total_objects": len(objects),
        "layer_counts": dict(sorted(layer_counts.items())),
        "permission_level_counts": dict(sorted(level_counts.items())),
        "runtime_export_counts": dict(sorted(export_counts.items())),
        "risk_counts": dict(sorted(risk_counts.items())),
        "player_exposed_count": player_exposed_count,
        "review_required_count": review_required_count,
    }


def merge_objects(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for obj in objects:
        object_id = str(obj.get("object_id") or "")
        if not object_id:
            continue
        if object_id not in by_id:
            by_id[object_id] = obj
            continue
        current = by_id[object_id]
        for key in ("source_files", "source_ids", "stage_refs", "dependency_refs", "validators", "notes"):
            current[key] = stable_strings(as_list(current.get(key)) + as_list(obj.get(key)))
    return [by_id[key] for key in sorted(by_id)]


def build_catalog(
    stage_candidate_pack_path: Path,
    promotion_report_path: Path,
    final_state_path: Path,
    created_at: str,
) -> dict[str, Any]:
    stage_pack = load_json(stage_candidate_pack_path)
    promotion_report = load_json(promotion_report_path)
    final_state = load_json(final_state_path)
    objects = merge_objects([
        *stage_objects(stage_pack),
        *asset_objects(promotion_report),
        *run_state_objects(final_state),
    ])
    return {
        "schema_version": CATALOG_VERSION,
        "catalog_id": "mvp_compilable_object_catalog_001",
        "visibility": "review_only",
        "worldbook_id": str(stage_pack.get("worldbook_id") or final_state.get("worldbook_id")),
        "run_id": str(stage_pack.get("run_id") or final_state.get("run_id")),
        "created_at": created_at,
        "generation_boundary": {
            "front_end_integration": "not_included",
            "catalog_builder_reads_env": False,
            "catalog_builder_calls_provider": False,
            "base_worldbook_mutation": False,
            "runtime_export_included": "referenced_only",
        },
        "object_model": object_model(),
        "objects": objects,
        "summary": summarize(objects),
        "validation_commands": validation_commands(),
    }


def validate_catalog(catalog: dict[str, Any]) -> list[str]:
    errors = validate_json_schema(catalog, SCHEMA_PATH)
    errors.extend(validate_compilable_object_catalog(catalog))
    seen: set[str] = set()
    out: list[str] = []
    for error in errors:
        if error not in seen:
            seen.add(error)
            out.append(error)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Build CompilableObjectCatalog v0.1.")
    parser.add_argument("--stage-candidate-pack", default=str(DEFAULT_STAGE_CANDIDATE_PACK))
    parser.add_argument("--promotion-report", default=str(DEFAULT_PROMOTION_REPORT))
    parser.add_argument("--final-state", default=str(DEFAULT_FINAL_STATE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--created-at", default="2026-07-01T00:00:00+08:00")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()

    catalog = build_catalog(
        Path(args.stage_candidate_pack),
        Path(args.promotion_report),
        Path(args.final_state),
        args.created_at,
    )
    output = Path(args.output)
    write_json(output, catalog)

    errors = validate_catalog(catalog) if args.validate else []
    if errors:
        print("INVALID CompilableObjectCatalog")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"OK: {output}")
    print(f"- schema_version: {catalog.get('schema_version')}")
    print(f"- objects: {catalog.get('summary', {}).get('total_objects')}")
    print(f"- layers: {catalog.get('summary', {}).get('layer_counts')}")
    if args.validate:
        print("- validation: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
