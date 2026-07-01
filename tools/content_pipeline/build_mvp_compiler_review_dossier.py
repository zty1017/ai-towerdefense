#!/usr/bin/env python3
"""Build the MVP compiler review dossier.

The dossier is a review-only handoff artifact. It gathers the current staged
content pack, promotion report, world-state deltas, final run state, compiled
assets, runtime fixture, workflows, and validation commands into one JSON file.

It does not read .env, does not call providers, and does not build a frontend
runtime bundle.
"""

from __future__ import annotations

import argparse
import hashlib
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


DOSSIER_VERSION = "mvp_compiler_review_dossier.v0.1"
DEFAULT_REVIEW_PACK = ROOT / "examples/review_packs/mvp_story_asset_review_pack.v0.1.json"
DEFAULT_PROMOTION_REPORT = ROOT / "examples/review_packs/mvp_story_asset_promotion_report.v0.1.json"
DEFAULT_FINAL_STATE = ROOT / "examples/run_world_states/demo_after_stage_04_wick_store.run_world_state.json"
DEFAULT_STAGE_CANDIDATE_PACK = ROOT / "examples/review_packs/mvp_stage_candidate_pack.v0.1.json"
DEFAULT_COMPILABLE_OBJECT_CATALOG = ROOT / "examples/review_packs/mvp_compilable_object_catalog.v0.1.json"
DEFAULT_COMPILABLE_OBJECT_PLAN = ROOT / "examples/review_packs/mvp_next_stage_compilable_object_plan.v0.1.json"
DEFAULT_STAGE05_PLAN_REALIZATION_REPORT = ROOT / "examples/review_packs/mvp_stage05_plan_realization_report.v0.1.json"
DEFAULT_MULTISTAGE_CONTENT_PACK = ROOT / "examples/review_packs/mvp_multistage_content_pack.v0.1.json"
DEFAULT_MULTISTAGE_STAGE_CANDIDATE_PACK = ROOT / "examples/review_packs/mvp_multistage_stage_candidate_pack.v0.1.json"
DEFAULT_RUNTIME_PACKAGES = [
    ROOT / "examples/runtime_packages/mvp_demo.runtime_package.json",
    ROOT / "examples/runtime_packages/mvp_wick_store_pressure.runtime_package.json",
]
DEFAULT_OUTPUT = ROOT / "examples/review_packs/mvp_compiler_review_dossier.v0.1.json"
SCHEMA_PATH = ROOT / "shared/schemas/mvp_compiler_review_dossier.v0.1.schema.json"

STAGE_DELTA_MAP = {
    "act_1_stage_01_gray_lantern_first_defense": (
        "examples/world_deltas/stage_01_gray_lantern_first_defense.world_delta.json"
    ),
    "act_1_stage_02_dawn_review_supply_line": (
        "examples/world_deltas/stage_02_dawn_review_supply_line.world_delta.json"
    ),
    "act_1_stage_03_northern_road_scouting": (
        "examples/world_deltas/stage_03_northern_road_scouting.world_delta.json"
    ),
    "act_1_stage_04_wick_store_pressure_battle": (
        "examples/world_deltas/stage_04_wick_store_pressure_battle.world_delta.json"
    ),
}

CORE_WORKFLOWS = [
    "examples/workflows/mvp_controlled_narrative_world_progression.workflow.json",
    "examples/workflows/mvp_world_delta_semantic_gate_demo.workflow.json",
    "examples/workflows/mvp_live_world_delta_guarded.workflow.json",
    "examples/workflows/mvp_defense_asset_compile.workflow.json",
    "examples/workflows/mvp_live_asset_compile_guarded.workflow.json",
    "examples/workflows/mvp_live_asset_media_repair_guarded.workflow.json",
    "examples/workflows/mvp_image_to_video_sprite_compile.workflow.json",
]


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def repo_path(ref: str) -> Path:
    path = Path(ref)
    return path if path.is_absolute() else ROOT / ref


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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_evidence(path_ref: str, kind: str) -> dict[str, Any]:
    path = repo_path(path_ref)
    return {
        "path": rel(path),
        "kind": kind,
        "exists": path.is_file(),
        "sha256": sha256_file(path) if path.is_file() else "0" * 64,
    }


def stable_strings(values: list[Any]) -> list[str]:
    return sorted({str(value) for value in values if isinstance(value, str) and value})


def stage_promotion_assets(promotion_report: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    by_stage: dict[str, list[dict[str, Any]]] = {}
    for stage in as_list(promotion_report.get("stages")):
        if not isinstance(stage, dict):
            continue
        stage_id = str(stage.get("stage_id") or "")
        assets: list[dict[str, Any]] = []
        for asset in as_list(stage.get("assets")):
            if not isinstance(asset, dict):
                continue
            assets.append(asset_summary_from_promotion(asset))
        by_stage[stage_id] = assets
    return by_stage


def runtime_asset_summary(asset: dict[str, Any]) -> dict[str, Any]:
    display = as_obj(asset.get("display"))
    availability = as_obj(asset.get("battle_availability"))
    return {
        "stable_internal_id": str(asset.get("stable_internal_id") or "unknown_runtime_asset"),
        "asset_kind": str(asset.get("asset_kind") or "unknown"),
        "lifecycle_state": str(asset.get("lifecycle_state") or "unknown"),
        "display_name": str(display.get("name") or asset.get("stable_internal_id") or "unknown"),
        "battle_surfaces": stable_strings(as_list(availability.get("surfaces"))),
        "visual_recipe_kinds": stable_strings(
            [
                recipe.get("kind")
                for recipe in as_list(asset.get("visual_recipes"))
                if isinstance(recipe, dict)
            ]
        ),
    }


def compiled_asset_gameplay_summary(source_file: str) -> dict[str, Any] | None:
    path = repo_path(source_file)
    if not path.is_file() or "compiled_assets/" not in source_file:
        return None
    data = load_json(path)
    gameplay = as_obj(data.get("gameplay"))
    provenance = as_obj(data.get("provenance"))
    return {
        "lifecycle": str(data.get("lifecycle") or "unknown"),
        "asset_type": str(gameplay.get("asset_type") or "unknown"),
        "base_stats": as_obj(gameplay.get("base_stats")),
        "effect_blocks": stable_strings(
            [
                effect.get("type")
                for effect in as_list(gameplay.get("effect_blocks"))
                if isinstance(effect, dict)
            ]
        ),
        "constraints": as_obj(gameplay.get("constraints")),
        "type_specific": as_obj(gameplay.get("type_specific")),
        "material_ids": stable_strings(as_list(provenance.get("material_ids"))),
        "npc_ids": stable_strings(as_list(provenance.get("npc_ids"))),
        "provenance_mode": str(provenance.get("mode") or "unknown"),
        "worldbook_id": str(provenance.get("worldbook_id") or "unknown"),
        "validation_status": str(provenance.get("validation_status") or "unknown"),
    }


def runtime_asset_summary_for_source(source_file: str, asset_id: str) -> dict[str, Any] | None:
    path = repo_path(source_file)
    if not path.is_file() or "runtime_packages/" not in source_file:
        return None
    package = load_json(path)
    for asset in as_list(as_obj(package).get("assets")):
        if isinstance(asset, dict) and asset.get("stable_internal_id") == asset_id:
            return runtime_asset_summary(asset)
    return None


def asset_summary_from_promotion(asset: dict[str, Any]) -> dict[str, Any]:
    asset_id = str(asset.get("asset_id") or "unknown_asset")
    source_file = str(asset.get("source_file") or "unknown")
    summary = {
        "asset_id": asset_id,
        "asset_kind": str(asset.get("asset_kind") or "unknown"),
        "source_file": source_file,
        "promotion_state": str(asset.get("promotion_state") or "unknown"),
        "playable": bool(asset.get("playable")),
        "uses_fallback_media": bool(asset.get("uses_fallback_media")),
        "gameplay_role": str(asset.get("gameplay_role") or "待审查用途"),
    }
    gameplay = compiled_asset_gameplay_summary(source_file)
    if gameplay is not None:
        summary["gameplay_summary"] = gameplay
    runtime_summary = runtime_asset_summary_for_source(source_file, asset_id)
    if runtime_summary is not None:
        summary["runtime_asset_summary"] = runtime_summary
    return summary


def summarize_bundle(bundle_file: str) -> dict[str, Any]:
    path = repo_path(bundle_file)
    if not path.is_file():
        return {
            "lane_counts": {},
            "gameplay_purposes": [],
            "gameplay_hooks": [],
        }
    bundle = load_json(path)
    nodes = [node for node in as_list(bundle.get("nodes")) if isinstance(node, dict)]
    lane_counts = Counter(str(node.get("lane") or "unknown") for node in nodes)
    purposes: list[str] = []
    hooks: list[str] = []
    for node in nodes:
        purposes.extend(stable_strings(as_list(node.get("gameplay_purpose"))))
        for hook in as_list(node.get("gameplay_hooks")):
            if isinstance(hook, dict) and hook.get("hook"):
                hooks.append(str(hook["hook"]))
    return {
        "lane_counts": dict(sorted(lane_counts.items())),
        "gameplay_purposes": stable_strings(purposes),
        "gameplay_hooks": stable_strings(hooks),
    }


def summarize_delta(delta_file: str | None) -> dict[str, int]:
    if not delta_file:
        return {}
    path = repo_path(delta_file)
    if not path.is_file():
        return {}
    delta = load_json(path)
    counts = Counter(
        str(op.get("op") or "unknown")
        for op in as_list(delta.get("operations"))
        if isinstance(op, dict)
    )
    return dict(sorted(counts.items()))


def simple_refs(values: list[Any], *, kind: str, status: str) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for value in values:
        if isinstance(value, str):
            refs.append({"id": value, "kind": kind, "status": status})
        elif isinstance(value, dict):
            item_id = (
                value.get("npc_id")
                or value.get("material_id")
                or value.get("node_id")
                or value.get("blueprint_id")
                or value.get("id")
            )
            if item_id:
                ref = {"id": str(item_id), "kind": kind, "status": status}
                if value.get("display_name"):
                    ref["display_name"] = str(value["display_name"])
                if value.get("source_file"):
                    ref["source_file"] = str(value["source_file"])
                if value.get("summary"):
                    ref["summary"] = str(value["summary"])
                refs.append(ref)
    return refs


def stage_review(
    stage: dict[str, Any],
    assets_by_stage: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    stage_id = str(stage.get("stage_id") or "unknown_stage")
    bundle_file = str(stage.get("bundle_file") or "")
    delta_file = STAGE_DELTA_MAP.get(stage_id)
    bundle_summary = summarize_bundle(bundle_file)
    npcs = []
    npc_block = as_obj(stage.get("npcs"))
    npcs.extend(simple_refs(as_list(npc_block.get("canonical")), kind="npc", status="canonical"))
    npcs.extend(simple_refs(as_list(npc_block.get("candidate")), kind="npc", status="candidate"))
    materials = []
    material_block = as_obj(stage.get("materials"))
    materials.extend(
        simple_refs(as_list(material_block.get("canonical")), kind="material", status="canonical")
    )
    materials.extend(
        simple_refs(
            as_list(material_block.get("candidate_only")),
            kind="material",
            status="candidate_only",
        )
    )
    return {
        "stage_order": int(stage.get("order") or 0),
        "stage_id": stage_id,
        "title": str(stage.get("title") or stage_id),
        "bundle_file": bundle_file,
        "world_delta_file": delta_file,
        "lane_counts": bundle_summary["lane_counts"],
        "gameplay_purposes": bundle_summary["gameplay_purposes"],
        "gameplay_hooks": bundle_summary["gameplay_hooks"],
        "delta_operation_counts": summarize_delta(delta_file),
        "assets": assets_by_stage.get(stage_id, []),
        "npcs": npcs,
        "materials": materials,
        "map_nodes": simple_refs(as_list(stage.get("map_nodes")), kind="map_node", status="stage_ref"),
        "research_hooks": stable_strings(as_list(stage.get("research_hooks"))),
        "gameplay_service": stable_strings(as_list(stage.get("gameplay_service"))),
    }


def gameplay_task_summary(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(task.get("task_id") or "unknown_task"),
        "kind": str(task.get("kind") or "task"),
        "status": str(task.get("status") or "unknown"),
        "summary": str(task.get("title") or task.get("summary") or "待审查任务"),
        "node_id": task.get("node_id"),
        "npc_id": task.get("npc_id"),
    }


def random_event_summary(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(event.get("random_event_id") or "unknown_event"),
        "kind": str(event.get("event_type") or "random_event"),
        "status": str(event.get("status") or "unknown"),
        "summary": str(event.get("summary") or "待审查事件"),
        "node_id": event.get("node_id"),
    }


def research_job_summary(job: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "id": str(job.get("job_id") or "unknown_job"),
        "kind": "research_job",
        "status": str(job.get("status") or "unknown"),
        "summary": str(job.get("expected_output") or "待审查研发结果"),
    }
    if job.get("source_task_id"):
        summary["source_task_id"] = str(job["source_task_id"])
    if job.get("source_sample_id"):
        summary["source_sample_id"] = str(job["source_sample_id"])
    return summary


def build_inventory(
    review_pack: dict[str, Any],
    promotion_report: dict[str, Any],
    final_state: dict[str, Any],
) -> dict[str, Any]:
    boundaries = as_obj(review_pack.get("canonical_boundaries"))
    assets: dict[str, dict[str, Any]] = {}
    for stage in as_list(promotion_report.get("stages")):
        if not isinstance(stage, dict):
            continue
        for asset in as_list(stage.get("assets")):
            if not isinstance(asset, dict):
                continue
            asset_id = str(asset.get("asset_id") or "")
            if not asset_id or asset_id in assets:
                continue
            assets[asset_id] = asset_summary_from_promotion(asset)
    research = as_obj(final_state.get("research"))
    return {
        "assets": sorted(assets.values(), key=lambda item: item["asset_id"]),
        "npcs": (
            simple_refs(as_list(boundaries.get("canonical_npcs")), kind="npc", status="canonical")
            + simple_refs(
                as_list(boundaries.get("candidate_functional_npcs")),
                kind="npc",
                status="candidate",
            )
        ),
        "materials": (
            simple_refs(
                as_list(boundaries.get("canonical_materials")),
                kind="material",
                status="canonical",
            )
            + simple_refs(
                as_list(boundaries.get("candidate_only_materials")),
                kind="material",
                status="candidate_only",
            )
        ),
        "map_nodes": simple_refs(
            as_list(final_state.get("map_nodes")),
            kind="map_node",
            status="final_run_state",
        ),
        "tasks": [
            gameplay_task_summary(task)
            for task in as_list(final_state.get("tasks"))
            if isinstance(task, dict)
        ],
        "random_events": [
            random_event_summary(event)
            for event in as_list(final_state.get("random_events"))
            if isinstance(event, dict)
        ],
        "research_jobs": [
            research_job_summary(job)
            for job in as_list(research.get("active_jobs"))
            if isinstance(job, dict)
        ],
        "blueprints": simple_refs(
            as_list(research.get("known_blueprints")),
            kind="blueprint",
            status="known",
        ),
    }


def workflow_step(workflow_file: str) -> dict[str, Any]:
    workflow = load_json(repo_path(workflow_file))
    return {
        "step_id": Path(workflow_file).stem,
        "name": Path(workflow_file).stem,
        "purpose": str(workflow.get("description") or workflow.get("mode") or "workflow"),
        "inputs": [workflow_file],
        "outputs": ["execution_trace"],
        "gate": f"validate_workflow.py; mode={workflow.get('mode')}; nodes={len(as_list(workflow.get('nodes')))}",
    }


def runtime_package_summary(package_path: Path) -> dict[str, Any]:
    package = load_json(package_path)
    context = as_obj(package.get("battle_context"))
    grid = as_obj(context.get("grid"))
    sample_delivery = as_obj(context.get("sample_delivery"))
    return {
        "package_file": rel(package_path),
        "package_id": str(package.get("package_id") or "unknown_package"),
        "session_id": str(package.get("session_id") or "unknown_session"),
        "worldbook_id": str(package.get("worldbook_id") or "unknown_worldbook"),
        "node_id": str(package.get("node_id") or "unknown_node"),
        "asset_count": len(as_list(package.get("assets"))),
        "assets": [
            runtime_asset_summary(asset)
            for asset in as_list(package.get("assets"))
            if isinstance(asset, dict)
        ],
        "battle_context_summary": {
            "projection": str(grid.get("projection") or "unknown"),
            "width_cells": int(grid.get("width_cells") or 0),
            "height_cells": int(grid.get("height_cells") or 0),
            "path_count": len(as_list(context.get("paths"))),
            "optional_target_count": len(as_list(context.get("optional_targets"))),
            "sample_delivery_delay_ms": int(sample_delivery.get("delivery_delay_ms") or 0),
        },
    }


def workflow_reviews() -> list[dict[str, Any]]:
    reviews: list[dict[str, Any]] = []
    for path in sorted((ROOT / "examples/workflows").glob("*.json")):
        workflow = load_json(path)
        nodes = [
            {
                "id": str(node.get("id") or "unknown_node"),
                "node_type": str(node.get("node_type") or "unknown"),
                "runtime_public": bool(node.get("runtime_public", False)),
            }
            for node in as_list(workflow.get("nodes"))
            if isinstance(node, dict)
        ]
        mode = str(workflow.get("mode") or "unknown")
        description = str(workflow.get("description") or path.stem)
        live_provider_risk = mode == "live" or "provider" in description.lower()
        reviews.append(
            {
                "workflow_file": rel(path),
                "workflow_id": str(workflow.get("workflow_id") or path.stem),
                "mode": mode,
                "description": description,
                "node_count": len(nodes),
                "edge_count": len(as_list(workflow.get("edges"))),
                "live_provider_risk": live_provider_risk,
                "nodes": nodes,
            }
        )
    return reviews


def pipeline_overview() -> list[dict[str, Any]]:
    return [
        {
            "step_id": "01_narrative_bundle",
            "name": "阶段剧情节点编译",
            "purpose": "把世界书、运行态、战斗结果和玩家线索整理成 NarrativeEventBundle。",
            "inputs": [
                "RunWorldState",
                "BattleResult",
                "SessionContext",
                "BaseWorldbook",
            ],
            "outputs": ["NarrativeEventBundle"],
            "gate": "validate_narrative_bundle.py; worldbook_base_mutation_allowed=false",
        },
        {
            "step_id": "02_world_state_delta",
            "name": "世界状态变化提交",
            "purpose": "把可接受的剧情与玩法意图转成受控 WorldStateDelta。",
            "inputs": ["NarrativeEventBundle", "current RunWorldState"],
            "outputs": ["WorldStateDelta", "next RunWorldState"],
            "gate": "validate_world_delta.py + validate_world_delta_semantics.py + apply_world_delta.py",
        },
        {
            "step_id": "03_narrative_gameplay_contract",
            "name": "剧情玩法联合契约",
            "purpose": "证明剧情节点不是纯文本，而是闭环到任务、随机事件、研究、资源、NPC、地图节点或蓝图。",
            "inputs": ["NarrativeEventBundle", "WorldStateDelta", "final RunWorldState"],
            "outputs": ["contract validation report"],
            "gate": "validate_narrative_gameplay_contract.py",
        },
        {
            "step_id": "04_asset_compile",
            "name": "游戏资产编译",
            "purpose": "把提案或玩家构想编译为防御塔、道具、情报资产或临时改造候选。",
            "inputs": ["Proposal", "worldbook boundary", "effect catalog"],
            "outputs": ["CompiledAssetCandidate", "promotion report"],
            "gate": "validate_asset_candidate.py + simulate_asset_candidate.py + score_asset_candidate.py + asset_promotion_policy.py",
        },
        {
            "step_id": "05_media_compile",
            "name": "媒体与特效管线",
            "purpose": "为可用资产生成图像、视频帧、抠图后处理和 runtime media manifest。",
            "inputs": ["CompiledAssetCandidate", "visual identity", "media prompt"],
            "outputs": ["processed media", "runtime readiness report"],
            "gate": "media consistency / readiness validators; MVP 可 fallback",
        },
        {
            "step_id": "06_review_dossier",
            "name": "阶段候选包构建",
            "purpose": "把单阶段剧情、状态变化、玩法对象、资产和 runtime 引用合并成可审查候选单元。",
            "inputs": ["review pack", "world deltas", "promotion report", "runtime packages"],
            "outputs": ["StageCandidatePack"],
            "gate": "stage_candidate_pack.v0.1 schema + validate_stage_candidate_pack.py",
        },
        {
            "step_id": "07_review_dossier",
            "name": "总审查交付包构建",
            "purpose": "把阶段候选包、可编译对象目录、运行态、资产和验证命令汇总成总审查证据。",
            "inputs": ["StageCandidatePack", "CompilableObjectCatalog", "final run state", "workflows"],
            "outputs": ["MVP Compiler Review Dossier"],
            "gate": "mvp_compiler_review_dossier.v0.1 schema",
        },
        {
            "step_id": "08_stage05_plan_realization",
            "name": "下一阶段计划落地样例",
            "purpose": "把 CompilableObjectPlan 中的 Stage 05 计划转成可审查叙事包、世界状态变化、下一运行态和资产候选，证明叙事、任务、资产都可作为受控可编译对象。",
            "inputs": ["CompilableObjectPlan", "current RunWorldState", "review boundaries"],
            "outputs": ["NarrativeEventBundle", "WorldStateDelta", "next RunWorldState", "Proposal", "CompiledAssetCandidate"],
            "gate": "build_stage05_plan_realization.py --validate",
        },
        {
            "step_id": "09_multistage_content_pack",
            "name": "多阶段内容生产包",
            "purpose": "串行生成 Stage 05/06/07 的世界线、玩家线、任务、随机事件、样本和多类型资产候选，并导出详细内容包与标准阶段候选包供人工审查。",
            "inputs": ["Stage 04 RunWorldState", "review boundaries", "effect registry"],
            "outputs": ["MultistageContentPack", "StageCandidatePack", "Stage 05-07 artifacts"],
            "gate": "build_multistage_content_pack.py --validate + validate_stage_candidate_pack.py",
        },
    ] + [workflow_step(path) for path in CORE_WORKFLOWS if repo_path(path).is_file()]


def validation_commands() -> list[dict[str, str]]:
    return [
        {
            "purpose": "构建并校验总审查交付包",
            "command": "python3 tools/content_pipeline/build_mvp_compiler_review_dossier.py --validate",
        },
        {
            "purpose": "校验故事资产审查包",
            "command": "python3 tools/content_pipeline/validate_mvp_story_asset_review_pack.py examples/review_packs/mvp_story_asset_review_pack.v0.1.json",
        },
        {
            "purpose": "校验剧情到玩法对象的跨文件契约",
            "command": "python3 tools/narrative/validate_narrative_gameplay_contract.py examples/review_packs/mvp_story_asset_review_pack.v0.1.json",
        },
        {
            "purpose": "构建并校验阶段候选包",
            "command": "python3 tools/content_pipeline/build_stage_candidate_pack.py --validate",
        },
        {
            "purpose": "校验阶段候选包",
            "command": "python3 tools/content_pipeline/validate_stage_candidate_pack.py examples/review_packs/mvp_stage_candidate_pack.v0.1.json",
        },
        {
            "purpose": "构建并校验可编译对象目录",
            "command": "python3 tools/content_pipeline/build_compilable_object_catalog.py --validate",
        },
        {
            "purpose": "校验可编译对象目录",
            "command": "python3 tools/content_pipeline/validate_compilable_object_catalog.py examples/review_packs/mvp_compilable_object_catalog.v0.1.json",
        },
        {
            "purpose": "构建并校验下一阶段可编译对象计划",
            "command": "python3 tools/content_pipeline/build_compilable_object_plan.py --validate",
        },
        {
            "purpose": "校验下一阶段可编译对象计划",
            "command": "python3 tools/content_pipeline/validate_compilable_object_plan.py examples/review_packs/mvp_next_stage_compilable_object_plan.v0.1.json",
        },
        {
            "purpose": "构建并校验 Stage 05 计划落地样例",
            "command": "python3 tools/content_pipeline/build_stage05_plan_realization.py --validate",
        },
        {
            "purpose": "校验 Stage 05 叙事包",
            "command": "python3 tools/narrative/validate_narrative_bundle.py examples/narrative_bundles/stage_05_old_signal_tower_pressure.narrative_event_bundle.json",
        },
        {
            "purpose": "校验 Stage 05 WorldStateDelta 语义门",
            "command": "python3 tools/world_state/validate_world_delta_semantics.py examples/world_deltas/stage_05_old_signal_tower_pressure.world_delta.json --run-state examples/run_world_states/demo_after_stage_04_wick_store.run_world_state.json",
        },
        {
            "purpose": "校验 Stage 05 资产提案和候选资产",
            "command": "python3 tools/content_pipeline/validate_proposal.py examples/proposals/echo_prism_relay.proposal.json && python3 tools/content_pipeline/validate_asset_candidate.py examples/compiled_assets/echo_prism_relay.compiled_asset.json",
        },
        {
            "purpose": "构建并校验多阶段内容生产包",
            "command": "python3 tools/content_pipeline/build_multistage_content_pack.py --validate",
        },
        {
            "purpose": "校验多阶段阶段候选包",
            "command": "python3 tools/content_pipeline/validate_stage_candidate_pack.py examples/review_packs/mvp_multistage_stage_candidate_pack.v0.1.json",
        },
        {
            "purpose": "重建资产晋升报告到 /tmp",
            "command": "python3 tools/content_pipeline/build_mvp_review_pack_promotion_report.py examples/review_packs/mvp_story_asset_review_pack.v0.1.json --output /tmp/mvp_story_asset_promotion_report.check.json",
        },
        {
            "purpose": "校验全部编译资产候选",
            "command": "find examples/compiled_assets -name '*.json' -exec python3 tools/content_pipeline/validate_asset_candidate.py {} \\;",
        },
        {
            "purpose": "校验 runtime package",
            "command": "python3 tools/asset_graph/validate_runtime_package.py examples/runtime_packages/mvp_demo.runtime_package.json",
        },
        {
            "purpose": "校验阶段 1 WorldStateDelta",
            "command": "python3 tools/world_state/validate_world_delta.py examples/world_deltas/stage_01_gray_lantern_first_defense.world_delta.json",
        },
        {
            "purpose": "校验阶段 2 WorldStateDelta",
            "command": "python3 tools/world_state/validate_world_delta.py examples/world_deltas/stage_02_dawn_review_supply_line.world_delta.json",
        },
        {
            "purpose": "校验阶段 3 WorldStateDelta",
            "command": "python3 tools/world_state/validate_world_delta.py examples/world_deltas/stage_03_northern_road_scouting.world_delta.json",
        },
        {
            "purpose": "校验阶段 4 WorldStateDelta",
            "command": "python3 tools/world_state/validate_world_delta.py examples/world_deltas/stage_04_wick_store_pressure_battle.world_delta.json",
        },
        {
            "purpose": "校验最终运行态",
            "command": "python3 tools/world_state/validate_run_world_state.py examples/run_world_states/demo_after_stage_04_wick_store.run_world_state.json",
        },
        {
            "purpose": "校验语义门 DAG 示例",
            "command": "python3 tools/asset_graph/run_workflow.py examples/workflows/mvp_world_delta_semantic_gate_demo.workflow.json --output-dir /tmp/mvp_world_delta_semantic_gate_demo",
        },
        {
            "purpose": "校验全部 workflow 图",
            "command": "for f in examples/workflows/*.json; do python3 tools/asset_graph/validate_workflow.py \"$f\" || exit 1; done",
        },
        {
            "purpose": "重放完整 WorldStateDelta 链并对比最终快照",
            "command": "python3 tools/world_state/replay_mvp_delta_chain.py --compare-final examples/run_world_states/demo_after_stage_04_wick_store.run_world_state.json",
        },
    ]


def stage_candidate_pack_summary(pack_path: Path) -> dict[str, Any]:
    pack = load_json(pack_path)
    readiness = as_obj(pack.get("readiness_summary"))
    return {
        "pack_file": rel(pack_path),
        "stage_count": int(readiness.get("stage_count") or len(as_list(pack.get("stage_candidates")))),
        "status_counts": as_obj(readiness.get("status_counts")),
        "validation_gate_counts": as_obj(readiness.get("validation_gate_counts")),
        "runtime_package_reference_count": int(
            readiness.get("runtime_package_reference_count") or 0
        ),
        "review_recommendation": str(readiness.get("review_recommendation") or "needs_human_review"),
    }


def compilable_object_catalog_summary(catalog_path: Path) -> dict[str, Any]:
    catalog = load_json(catalog_path)
    summary = as_obj(catalog.get("summary"))
    return {
        "catalog_file": rel(catalog_path),
        "total_objects": int(summary.get("total_objects") or 0),
        "layer_counts": as_obj(summary.get("layer_counts")),
        "permission_level_counts": as_obj(summary.get("permission_level_counts")),
        "runtime_export_counts": as_obj(summary.get("runtime_export_counts")),
        "risk_counts": as_obj(summary.get("risk_counts")),
        "player_exposed_count": int(summary.get("player_exposed_count") or 0),
        "review_required_count": int(summary.get("review_required_count") or 0),
    }


def compilable_object_plan_summary(plan_path: Path) -> dict[str, Any]:
    plan = load_json(plan_path)
    summary = as_obj(plan.get("summary"))
    context = as_obj(plan.get("planning_context"))
    return {
        "plan_file": rel(plan_path),
        "target_stage_id": str(context.get("target_stage_id") or "unknown_stage"),
        "request_count": int(summary.get("request_count") or 0),
        "layer_counts": as_obj(summary.get("layer_counts")),
        "permission_level_counts": as_obj(summary.get("permission_level_counts")),
        "compile_actor_counts": as_obj(summary.get("compile_actor_counts")),
        "risk_counts": as_obj(summary.get("risk_counts")),
        "requires_llm_count": int(summary.get("requires_llm_count") or 0),
        "requires_media_count": int(summary.get("requires_media_count") or 0),
        "requires_human_review_count": int(summary.get("requires_human_review_count") or 0),
    }


def stage05_plan_realization_evidence(report_path: Path) -> list[tuple[str, str]]:
    evidence = [
        ("tools/content_pipeline/build_stage05_plan_realization.py", "builder"),
        ("docs/STAGE05_PLAN_REALIZATION_V0_1.md", "architecture_doc"),
        (rel(report_path), "stage05_plan_realization_report"),
    ]
    if not report_path.is_file():
        return evidence

    report = load_json(report_path)
    outputs = as_obj(report.get("outputs"))
    for key, kind in (
        ("narrative_bundle", "narrative_bundle"),
        ("world_delta", "world_delta"),
        ("next_run_state", "run_world_state"),
        ("proposal", "proposal"),
        ("compiled_asset_candidate", "asset_source"),
    ):
        value = outputs.get(key)
        if isinstance(value, str) and value:
            evidence.append((value, kind))
    return evidence


def multistage_content_pack_evidence(
    content_pack_path: Path,
    stage_candidate_pack_path: Path,
) -> list[tuple[str, str]]:
    evidence = [
        ("tools/content_pipeline/build_multistage_content_pack.py", "builder"),
        ("docs/MULTISTAGE_CONTENT_PACK_V0_1.md", "architecture_doc"),
        (rel(content_pack_path), "multistage_content_pack"),
        (rel(stage_candidate_pack_path), "stage_candidate_pack"),
    ]
    if not content_pack_path.is_file():
        return evidence

    pack = load_json(content_pack_path)
    for stage in as_list(pack.get("stage_summaries")):
        if not isinstance(stage, dict):
            continue
        for key, kind in (
            ("bundle_file", "narrative_bundle"),
            ("world_delta_file", "world_delta"),
            ("next_state_file", "run_world_state"),
            ("proposal_file", "proposal"),
            ("compiled_asset_file", "asset_source"),
        ):
            value = stage.get(key)
            if isinstance(value, str) and value:
                evidence.append((value, kind))
    return evidence


def known_risks(promotion_report: dict[str, Any]) -> list[dict[str, str]]:
    summary = as_obj(promotion_report.get("summary"))
    candidate_count = int(summary.get("candidate_or_blocked_reference_count") or 0)
    return [
        {
            "risk_id": "legacy_initial_npcs",
            "severity": "medium",
            "summary": "初始 demo run state 仍保留早期兼容 NPC ID；语义门已阻止新 delta 继续引用它们。",
            "next_action": "后续单独迁移 demo_initial 到 canonical / candidate NPC 体系。",
        },
        {
            "risk_id": "fallback_media",
            "severity": "medium",
            "summary": "多数可玩资产目前依赖 fallback media 或已生成但未全部晋升到正式 runtime media manifest。",
            "next_action": "继续迭代图像/视频帧/抠图/一致性审查管线，优先处理 MVP 默认资产。",
        },
        {
            "risk_id": "candidate_or_blocked_assets",
            "severity": "medium" if candidate_count else "low",
            "summary": f"审查包仍有 {candidate_count} 个候选或受阻资产引用，不能默认进入 MVP 战斗。",
            "next_action": "保留为支线或高风险研发候选，默认教学关只用 fallback_ready / runtime fixture 资产。",
        },
    ]


def build_dossier(
    review_pack_path: Path,
    promotion_report_path: Path,
    final_state_path: Path,
    stage_candidate_pack_path: Path,
    compilable_object_catalog_path: Path,
    compilable_object_plan_path: Path,
    runtime_package_paths: list[Path],
) -> dict[str, Any]:
    review_pack = load_json(review_pack_path)
    promotion_report = load_json(promotion_report_path)
    final_state = load_json(final_state_path)
    assets_by_stage = stage_promotion_assets(promotion_report)
    stages = [
        stage_review(stage, assets_by_stage)
        for stage in as_list(review_pack.get("stages"))
        if isinstance(stage, dict)
    ]
    inventory = build_inventory(review_pack, promotion_report, final_state)
    research = as_obj(final_state.get("research"))
    promotion_summary = as_obj(promotion_report.get("summary"))
    all_workflows = [rel(path) for path in sorted((ROOT / "examples/workflows").glob("*.json"))]
    evidence_paths = [
        (rel(review_pack_path), "review_pack"),
        (rel(promotion_report_path), "promotion_report"),
        (rel(final_state_path), "run_world_state"),
        ("shared/schemas/mvp_compiler_review_dossier.v0.1.schema.json", "schema"),
        ("docs/GAMEPLAY_OBJECT_COMPILER_V0_1.md", "architecture_doc"),
        ("docs/NARRATIVE_GAMEPLAY_CONTRACT_V0_1.md", "architecture_doc"),
        ("docs/MVP_WORLD_STATE_DELTA_REVIEW_PACK_V0_1.md", "architecture_doc"),
        ("docs/MVP_STORY_ASSET_PROMOTION_REPORT_V0_1.md", "architecture_doc"),
        ("docs/MVP_COMPILER_REVIEW_DOSSIER_V0_1.md", "architecture_doc"),
        ("docs/COMPILABLE_OBJECT_MODEL_V0_1.md", "architecture_doc"),
        ("docs/COMPILABLE_OBJECT_PLAN_V0_1.md", "architecture_doc"),
        ("docs/STAGE05_PLAN_REALIZATION_V0_1.md", "architecture_doc"),
        ("docs/MULTISTAGE_CONTENT_PACK_V0_1.md", "architecture_doc"),
        ("docs/STAGE_CANDIDATE_PACK_V0_1.md", "architecture_doc"),
        ("docs/MEDIA_ASSET_QUALITY_PIPELINE_V0_2.md", "architecture_doc"),
        ("shared/schemas/compilable_object_catalog.v0.1.schema.json", "schema"),
        ("shared/schemas/compilable_object_plan.v0.1.schema.json", "schema"),
        ("shared/schemas/stage_candidate_pack.v0.1.schema.json", "schema"),
        ("tools/content_pipeline/build_compilable_object_catalog.py", "builder"),
        ("tools/content_pipeline/build_compilable_object_plan.py", "builder"),
        ("tools/content_pipeline/build_stage05_plan_realization.py", "builder"),
        ("tools/content_pipeline/build_multistage_content_pack.py", "builder"),
        ("tools/content_pipeline/build_stage_candidate_pack.py", "builder"),
        ("tools/content_pipeline/validate_compilable_object_catalog.py", "validator"),
        ("tools/content_pipeline/validate_compilable_object_plan.py", "validator"),
        ("tools/content_pipeline/validate_stage_candidate_pack.py", "validator"),
        ("tools/narrative/validate_narrative_gameplay_contract.py", "validator"),
        ("tools/world_state/replay_mvp_delta_chain.py", "validator"),
        (rel(stage_candidate_pack_path), "stage_candidate_pack"),
        (rel(compilable_object_catalog_path), "compilable_object_catalog"),
        (rel(compilable_object_plan_path), "compilable_object_plan"),
    ]
    evidence_paths.extend(
        stage05_plan_realization_evidence(DEFAULT_STAGE05_PLAN_REALIZATION_REPORT)
    )
    evidence_paths.extend(
        multistage_content_pack_evidence(
            DEFAULT_MULTISTAGE_CONTENT_PACK,
            DEFAULT_MULTISTAGE_STAGE_CANDIDATE_PACK,
        )
    )
    for runtime_package_path in runtime_package_paths:
        evidence_paths.append((rel(runtime_package_path), "runtime_package"))
    for stage in stages:
        evidence_paths.append((stage["bundle_file"], "narrative_bundle"))
        if stage["world_delta_file"]:
            evidence_paths.append((stage["world_delta_file"], "world_delta"))
        for asset in stage["assets"]:
            evidence_paths.append((asset["source_file"], "asset_source"))
    for workflow in all_workflows:
        evidence_paths.append((workflow, "workflow"))

    deduped_evidence: dict[str, str] = {}
    for path, kind in evidence_paths:
        if path and path not in deduped_evidence:
            deduped_evidence[path] = kind

    return {
        "schema_version": DOSSIER_VERSION,
        "dossier_id": "mvp_compiler_review_dossier_001",
        "visibility": "review_only",
        "worldbook_id": str(review_pack.get("worldbook_id") or final_state.get("worldbook_id")),
        "run_id": str(review_pack.get("run_id") or final_state.get("run_id")),
        "created_at": "2026-07-01T00:00:00+08:00",
        "generation_boundary": {
            "front_end_integration": "not_included",
            "dossier_builder_reads_env": False,
            "dossier_builder_calls_provider": False,
            "base_worldbook_mutation": False,
            "runtime_package_included": "referenced_only",
        },
        "pipeline_overview": pipeline_overview(),
        "stage_reviews": stages,
        "content_inventory": inventory,
        "runtime_package_summaries": [
            runtime_package_summary(path) for path in runtime_package_paths
        ],
        "workflow_reviews": workflow_reviews(),
        "stage_candidate_pack_summary": stage_candidate_pack_summary(stage_candidate_pack_path),
        "compilable_object_catalog_summary": compilable_object_catalog_summary(
            compilable_object_catalog_path
        ),
        "compilable_object_plan_summary": compilable_object_plan_summary(
            compilable_object_plan_path
        ),
        "runtime_state_summary": {
            "state_file": rel(final_state_path),
            "progress": as_obj(final_state.get("progress")),
            "global_state": as_obj(final_state.get("global_state")),
            "map_node_count": len(as_list(final_state.get("map_nodes"))),
            "npc_count": len(as_list(final_state.get("npcs"))),
            "event_count": len(as_list(final_state.get("event_log"))),
            "task_count": len(as_list(final_state.get("tasks"))),
            "random_event_count": len(as_list(final_state.get("random_events"))),
            "temporary_sample_count": len(as_list(research.get("temporary_samples"))),
            "blueprint_count": len(as_list(research.get("known_blueprints"))),
        },
        "readiness_summary": {
            "stage_count": len(stages),
            "playable_asset_references": int(promotion_summary.get("playable_reference_count") or 0),
            "fallback_ready_asset_references": int(
                promotion_summary.get("fallback_ready_reference_count") or 0
            ),
            "runtime_fixture_asset_references": int(
                promotion_summary.get("runtime_fixture_reference_count") or 0
            ),
            "candidate_or_blocked_asset_references": int(
                promotion_summary.get("candidate_or_blocked_reference_count") or 0
            ),
            "task_count": len(inventory["tasks"]),
            "random_event_count": len(inventory["random_events"]),
            "research_job_count": len(inventory["research_jobs"]),
            "blueprint_count": len(inventory["blueprints"]),
            "mvp_support_level": "reviewable_vertical_slice",
        },
        "source_evidence": [
            source_evidence(path, kind)
            for path, kind in sorted(deduped_evidence.items(), key=lambda item: item[0])
        ],
        "validation_commands": validation_commands(),
        "known_risks": known_risks(promotion_report),
    }


def validate_dossier(dossier: dict[str, Any]) -> list[str]:
    errors = validate_json_schema(dossier, SCHEMA_PATH)
    for evidence in as_list(dossier.get("source_evidence")):
        if isinstance(evidence, dict) and evidence.get("exists") is not True:
            errors.append(f"source_evidence missing file: {evidence.get('path')}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Build MVP compiler review dossier.")
    parser.add_argument("--review-pack", default=str(DEFAULT_REVIEW_PACK))
    parser.add_argument("--promotion-report", default=str(DEFAULT_PROMOTION_REPORT))
    parser.add_argument("--final-state", default=str(DEFAULT_FINAL_STATE))
    parser.add_argument("--stage-candidate-pack", default=str(DEFAULT_STAGE_CANDIDATE_PACK))
    parser.add_argument("--compilable-object-catalog", default=str(DEFAULT_COMPILABLE_OBJECT_CATALOG))
    parser.add_argument("--compilable-object-plan", default=str(DEFAULT_COMPILABLE_OBJECT_PLAN))
    parser.add_argument(
        "--runtime-package",
        action="append",
        dest="runtime_packages",
        help="Runtime package path. May be supplied multiple times; defaults to MVP packages.",
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate the generated dossier after writing it.",
    )
    args = parser.parse_args()

    runtime_package_paths = (
        [Path(path) for path in args.runtime_packages]
        if args.runtime_packages
        else DEFAULT_RUNTIME_PACKAGES
    )
    dossier = build_dossier(
        Path(args.review_pack),
        Path(args.promotion_report),
        Path(args.final_state),
        Path(args.stage_candidate_pack),
        Path(args.compilable_object_catalog),
        Path(args.compilable_object_plan),
        runtime_package_paths,
    )
    output = Path(args.output)
    write_json(output, dossier)

    errors = validate_dossier(dossier) if args.validate else []
    if errors:
        print("INVALID MVP compiler review dossier")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"OK: {output}")
    print(f"- schema_version: {dossier.get('schema_version')}")
    print(f"- stages: {len(dossier.get('stage_reviews', []))}")
    print(f"- assets: {len(dossier.get('content_inventory', {}).get('assets', []))}")
    print(f"- tasks: {dossier.get('readiness_summary', {}).get('task_count')}")
    print(f"- random_events: {dossier.get('readiness_summary', {}).get('random_event_count')}")
    print(f"- source_evidence: {len(dossier.get('source_evidence', []))}")
    if args.validate:
        print("- validation: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
