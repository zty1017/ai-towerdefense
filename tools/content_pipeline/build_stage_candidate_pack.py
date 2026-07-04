#!/usr/bin/env python3
"""Build a StageCandidatePack v0.1 from existing MVP review artifacts.

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
NARRATIVE_DIR = ROOT / "tools" / "narrative"
WORLD_STATE_DIR = ROOT / "tools" / "world_state"
for path in (ASSET_GRAPH_DIR, NARRATIVE_DIR, WORLD_STATE_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from validation_common import load_json, validate_json_schema  # noqa: E402
from validate_narrative_bundle import validate_narrative_bundle  # noqa: E402
from validate_narrative_gameplay_contract import validate_contract  # noqa: E402
from validate_stage_candidate_pack import validate_stage_candidate_pack  # noqa: E402
import validate_world_delta as v_wd  # noqa: E402


PACK_VERSION = "stage_candidate_pack.v0.1"
SCHEMA_PATH = ROOT / "shared/schemas/stage_candidate_pack.v0.1.schema.json"
DEFAULT_REVIEW_PACK = ROOT / "examples/review_packs/mvp_story_asset_review_pack.v0.1.json"
DEFAULT_PROMOTION_REPORT = ROOT / "examples/review_packs/mvp_story_asset_promotion_report.v0.1.json"
DEFAULT_FINAL_STATE = ROOT / "examples/run_world_states/demo_after_stage_04_wick_store.run_world_state.json"
DEFAULT_OUTPUT = ROOT / "examples/review_packs/mvp_stage_candidate_pack.v0.1.json"
DEFAULT_RUNTIME_PACKAGES = [
    ROOT / "examples/runtime_packages/mvp_demo.runtime_package.json",
    ROOT / "examples/runtime_packages/mvp_wick_store_pressure.runtime_package.json",
]

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


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def repo_path(ref: str | Path) -> Path:
    path = Path(ref)
    return path if path.is_absolute() else ROOT / path


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


def validation_status(errors: list[str], *, warning_if_errors: bool = False) -> str:
    if not errors:
        return "passed"
    return "warning" if warning_if_errors else "blocked"


def gate(gate_id: str, errors: list[str], success_summary: str) -> dict[str, str]:
    if errors:
        return {
            "gate": gate_id,
            "status": "blocked",
            "summary": "; ".join(errors[:3]),
        }
    return {
        "gate": gate_id,
        "status": "passed",
        "summary": success_summary,
    }


def summarize_bundle(bundle_file: str) -> tuple[dict[str, Any], list[str]]:
    path = repo_path(bundle_file)
    if not path.is_file():
        return (
            {"node_count": 0, "gameplay_purposes": [], "gameplay_hooks": []},
            [f"missing narrative bundle: {bundle_file}"],
        )
    bundle = load_json(path)
    errors = validate_narrative_bundle(bundle)
    nodes = [node for node in as_list(bundle.get("nodes")) if isinstance(node, dict)]
    purposes: list[str] = []
    hooks: list[str] = []
    for node in nodes:
        purposes.extend(stable_strings(as_list(node.get("gameplay_purpose"))))
        for hook in as_list(node.get("gameplay_hooks")):
            if isinstance(hook, dict) and hook.get("hook"):
                hooks.append(str(hook["hook"]))
    return (
        {
            "node_count": len(nodes),
            "gameplay_purposes": stable_strings(purposes),
            "gameplay_hooks": stable_strings(hooks),
        },
        errors,
    )


def full_delta_validation(delta: dict[str, Any]) -> list[str]:
    errors = [*v_wd.validate_with_jsonschema(delta), *v_wd.validate_world_delta(delta)]
    seen: set[str] = set()
    out: list[str] = []
    for error in errors:
        if error not in seen:
            seen.add(error)
            out.append(error)
    return out


def summarize_delta(delta_file: str) -> tuple[dict[str, Any], dict[str, list[str]], list[str]]:
    path = repo_path(delta_file)
    if not path.is_file():
        return (
            {"operation_count": 0, "operation_counts": {}},
            empty_gameplay_outputs(),
            [f"missing world delta: {delta_file}"],
        )
    delta = load_json(path)
    errors = full_delta_validation(delta)
    operations = [op for op in as_list(delta.get("operations")) if isinstance(op, dict)]
    counts = Counter(str(op.get("op") or "unknown") for op in operations)
    return (
        {
            "operation_count": len(operations),
            "operation_counts": dict(sorted(counts.items())),
        },
        gameplay_outputs_from_operations(operations),
        errors,
    )


def empty_gameplay_outputs() -> dict[str, list[str]]:
    return {
        "map_nodes": [],
        "npcs": [],
        "resources": [],
        "facts": [],
        "flags": [],
        "tasks": [],
        "random_events": [],
        "research_jobs": [],
        "samples": [],
        "blueprints": [],
    }


def gameplay_outputs_from_operations(operations: list[dict[str, Any]]) -> dict[str, list[str]]:
    out = {key: set() for key in empty_gameplay_outputs()}
    for op in operations:
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


def promotion_assets_by_stage(promotion_report: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    by_stage: dict[str, list[dict[str, Any]]] = {}
    for stage in as_list(promotion_report.get("stages")):
        if not isinstance(stage, dict):
            continue
        stage_id = str(stage.get("stage_id") or "")
        assets: list[dict[str, Any]] = []
        for asset in as_list(stage.get("assets")):
            if not isinstance(asset, dict):
                continue
            assets.append(
                {
                    "asset_id": str(asset.get("asset_id") or "unknown_asset"),
                    "asset_kind": str(asset.get("asset_kind") or "unknown"),
                    "source_file": str(asset.get("source_file") or ""),
                    "promotion_state": str(asset.get("promotion_state") or "unknown"),
                    "playable": bool(asset.get("playable")),
                    "uses_fallback_media": bool(asset.get("uses_fallback_media")),
                    "required_next_actions": stable_strings(as_list(asset.get("required_next_actions"))),
                }
            )
        by_stage[stage_id] = assets
    return by_stage


def runtime_refs_by_node(runtime_package_paths: list[Path]) -> dict[str, list[dict[str, Any]]]:
    by_node: dict[str, list[dict[str, Any]]] = {}
    for path in runtime_package_paths:
        if not path.is_file():
            continue
        package = load_json(path)
        node_id = str(package.get("node_id") or "")
        if not node_id:
            continue
        by_node.setdefault(node_id, []).append(
            {
                "package_file": rel(path),
                "package_id": str(package.get("package_id") or "unknown_package"),
                "node_id": node_id,
                "asset_count": len(as_list(package.get("assets"))),
            }
        )
    return by_node


def stage_runtime_refs(stage: dict[str, Any], runtime_by_node: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    node_ids: set[str] = set()
    for battle in as_list(stage.get("battle_nodes")):
        if isinstance(battle, dict) and isinstance(battle.get("node_id"), str):
            node_ids.add(battle["node_id"])
    for node_id in sorted(node_ids):
        refs.extend(runtime_by_node.get(node_id, []))
    return refs


def stage_battle_config(stage: dict[str, Any]) -> str | None:
    for battle in as_list(stage.get("battle_nodes")):
        if isinstance(battle, dict) and isinstance(battle.get("fixture"), str):
            fixture = battle["fixture"]
            if fixture.lower() not in {"needed", "pending", "todo", "tbd"}:
                return fixture
    return None


def asset_gate(assets: list[dict[str, Any]]) -> dict[str, str]:
    if not assets:
        return {
            "gate": "asset_promotion_policy",
            "status": "not_applicable",
            "summary": "该阶段没有登记资产输出。",
        }
    blocked = [asset["asset_id"] for asset in assets if not asset.get("playable")]
    if blocked:
        return {
            "gate": "asset_promotion_policy",
            "status": "warning",
            "summary": f"存在候选或受阻资产，不能默认进入 runtime: {', '.join(blocked)}",
        }
    return {
        "gate": "asset_promotion_policy",
        "status": "passed",
        "summary": "阶段资产均可作为 runtime fixture 或 fallback-ready 候选审查。",
    }


def runtime_gate(refs: list[dict[str, Any]]) -> dict[str, str]:
    if not refs:
        return {
            "gate": "runtime_package_ref",
            "status": "not_applicable",
            "summary": "该阶段不是战斗 runtime package 阶段。",
        }
    return {
        "gate": "runtime_package_ref",
        "status": "passed",
        "summary": f"该阶段已引用 {len(refs)} 个 runtime package。",
    }


def next_actions_for_stage(stage: dict[str, Any], assets: list[dict[str, Any]], runtime_refs: list[dict[str, Any]]) -> list[str]:
    actions: list[str] = []
    for asset in assets:
        actions.extend(as_list(asset.get("required_next_actions")))
    if as_list(stage.get("battle_nodes")) and not runtime_refs:
        actions.append("build_runtime_package_for_battle_stage")
    if not actions:
        actions.append("ready_for_human_review")
    return stable_strings(actions)


def build_stage_candidate(
    stage: dict[str, Any],
    assets_by_stage: dict[str, list[dict[str, Any]]],
    runtime_by_node: dict[str, list[dict[str, Any]]],
    contract_status: str,
    contract_summary: str,
) -> dict[str, Any]:
    stage_id = str(stage.get("stage_id") or "unknown_stage")
    bundle_file = str(stage.get("bundle_file") or "")
    delta_file = STAGE_DELTA_MAP.get(stage_id, "")
    narrative_summary, narrative_errors = summarize_bundle(bundle_file)
    delta_summary, gameplay_outputs, delta_errors = summarize_delta(delta_file)
    assets = assets_by_stage.get(stage_id, [])
    runtime_refs = stage_runtime_refs(stage, runtime_by_node)
    source_files: dict[str, str] = {
        "narrative_bundle": bundle_file,
        "world_delta": delta_file,
    }
    battle_config = stage_battle_config(stage)
    if battle_config:
        source_files["battle_config"] = battle_config
    gates = [
        gate("narrative_bundle", narrative_errors, "NarrativeEventBundle 结构与玩法 hook 校验通过。"),
        gate("world_delta_structure", delta_errors, "WorldStateDelta 结构与基础规则校验通过。"),
        {
            "gate": "narrative_gameplay_contract",
            "status": contract_status,
            "summary": contract_summary,
        },
        asset_gate(assets),
        runtime_gate(runtime_refs),
    ]
    blocked = any(item["status"] == "blocked" for item in gates)
    return {
        "stage_order": int(stage.get("order") or 0),
        "stage_id": stage_id,
        "title": str(stage.get("title") or stage_id),
        "status": "blocked" if blocked else "reviewed_fixture",
        "source_files": source_files,
        "lane_coverage": stable_strings(as_list(stage.get("lane_coverage"))),
        "narrative_summary": narrative_summary,
        "delta_summary": delta_summary,
        "gameplay_outputs": gameplay_outputs,
        "asset_outputs": assets,
        "runtime_package_refs": runtime_refs,
        "validation_gates": gates,
        "next_actions": next_actions_for_stage(stage, assets, runtime_refs),
    }


def validation_commands() -> list[dict[str, str]]:
    return [
        {
            "purpose": "构建并校验阶段候选包",
            "command": "python3 tools/content_pipeline/build_stage_candidate_pack.py --validate",
        },
        {
            "purpose": "单独校验阶段候选包",
            "command": "python3 tools/content_pipeline/validate_stage_candidate_pack.py examples/review_packs/mvp_stage_candidate_pack.v0.1.json",
        },
        {
            "purpose": "校验剧情到玩法对象的跨文件契约",
            "command": "python3 tools/narrative/validate_narrative_gameplay_contract.py examples/review_packs/mvp_story_asset_review_pack.v0.1.json --warnings-as-errors",
        },
    ]


def build_pack(
    review_pack_path: Path,
    promotion_report_path: Path,
    final_state_path: Path,
    runtime_package_paths: list[Path],
    created_at: str,
) -> dict[str, Any]:
    review_pack = load_json(review_pack_path)
    promotion_report = load_json(promotion_report_path)
    assets_by_stage = promotion_assets_by_stage(promotion_report)
    runtime_by_node = runtime_refs_by_node(runtime_package_paths)
    contract_errors, contract_warnings, contract_stats = validate_contract(
        review_pack_path=review_pack_path,
        world_delta_dir=ROOT / "examples/world_deltas",
        final_state_path=final_state_path,
    )
    if contract_errors:
        contract_status = "blocked"
        contract_summary = "; ".join(contract_errors[:3])
    elif contract_warnings:
        contract_status = "warning"
        contract_summary = f"契约通过但有 {len(contract_warnings)} 条告警。"
    else:
        contract_status = "passed"
        contract_summary = "剧情 hook、WorldStateDelta 与最终运行态玩法对象闭环通过。"

    stages = [
        build_stage_candidate(stage, assets_by_stage, runtime_by_node, contract_status, contract_summary)
        for stage in as_list(review_pack.get("stages"))
        if isinstance(stage, dict)
    ]
    status_counts = Counter(stage["status"] for stage in stages)
    gate_counts = Counter(
        gate_item["status"]
        for stage in stages
        for gate_item in stage["validation_gates"]
    )
    playable_count = sum(
        1
        for stage in stages
        for asset in stage["asset_outputs"]
        if asset.get("playable")
    )
    runtime_ref_count = sum(len(stage["runtime_package_refs"]) for stage in stages)
    recommendation = "review_ready"
    if gate_counts.get("blocked", 0):
        recommendation = "blocked"
    elif gate_counts.get("warning", 0):
        recommendation = "needs_human_review"
    return {
        "schema_version": PACK_VERSION,
        "pack_id": "mvp_stage_candidate_pack_001",
        "visibility": "review_only",
        "worldbook_id": str(review_pack.get("worldbook_id") or "unknown_worldbook"),
        "run_id": str(review_pack.get("run_id") or "unknown_run"),
        "created_at": created_at,
        "generation_boundary": {
            "front_end_integration": "not_included",
            "pack_builder_reads_env": False,
            "pack_builder_calls_provider": False,
            "base_worldbook_mutation": False,
            "runtime_package_included": "referenced_only",
            "llm_candidate_shape_supported": True,
        },
        "source_refs": {
            "review_pack": rel(review_pack_path),
            "promotion_report": rel(promotion_report_path),
            "final_run_state": rel(final_state_path),
            "runtime_packages": [rel(path) for path in runtime_package_paths],
        },
        "core_artifact_alignment": {
            "alignment_state": "review_only_not_applicable",
            "reason": (
                "StageCandidatePack 是 review-only 阶段候选容器；它聚合 narrative bundle、"
                "WorldStateDelta、玩法对象摘要和 runtime package 引用，但自身不是 "
                "ContextPackage、FactEntry、CGOP 或 WorldStateDeltaTransaction。"
            ),
            "expected_core_artifacts": [],
            "present_core_artifacts": [],
            "runtime_activation_allowed": False,
            "world_mutation_allowed": False,
            "next_action": (
                "后续核心对象迁移应针对每个 stage candidate 引用的 WorldStateDelta / "
                "WorldStateDeltaTransaction / runtime package，而不是激活整个 review pack。"
            ),
        },
        "stage_candidates": stages,
        "readiness_summary": {
            "stage_count": len(stages),
            "status_counts": dict(sorted(status_counts.items())),
            "validation_gate_counts": dict(sorted(gate_counts.items())),
            "playable_asset_reference_count": playable_count,
            "runtime_package_reference_count": runtime_ref_count,
            "contract_warnings": int(contract_stats.get("warnings", len(contract_warnings))),
            "review_recommendation": recommendation,
        },
        "validation_commands": validation_commands(),
    }


def validate_pack(pack: dict[str, Any]) -> list[str]:
    errors = validate_json_schema(pack, SCHEMA_PATH)
    errors.extend(validate_stage_candidate_pack(pack))
    seen: set[str] = set()
    out: list[str] = []
    for error in errors:
        if error not in seen:
            seen.add(error)
            out.append(error)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Build StageCandidatePack v0.1.")
    parser.add_argument("--review-pack", default=str(DEFAULT_REVIEW_PACK))
    parser.add_argument("--promotion-report", default=str(DEFAULT_PROMOTION_REPORT))
    parser.add_argument("--final-state", default=str(DEFAULT_FINAL_STATE))
    parser.add_argument("--runtime-package", action="append", dest="runtime_packages")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--created-at", default="2026-07-01T00:00:00+08:00")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()

    runtime_package_paths = (
        [repo_path(path) for path in args.runtime_packages]
        if args.runtime_packages
        else DEFAULT_RUNTIME_PACKAGES
    )
    pack = build_pack(
        repo_path(args.review_pack),
        repo_path(args.promotion_report),
        repo_path(args.final_state),
        runtime_package_paths,
        args.created_at,
    )
    output = repo_path(args.output)
    write_json(output, pack)
    errors = validate_pack(pack) if args.validate else []
    if errors:
        print("INVALID StageCandidatePack")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"OK: {output}")
    print(f"- schema_version: {pack.get('schema_version')}")
    print(f"- stages: {len(pack.get('stage_candidates', []))}")
    print(f"- recommendation: {pack.get('readiness_summary', {}).get('review_recommendation')}")
    print(f"- runtime_package_refs: {pack.get('readiness_summary', {}).get('runtime_package_reference_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
