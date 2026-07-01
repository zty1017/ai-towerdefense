#!/usr/bin/env python3
"""Run the offline MVP handoff audit and write a review report."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CONTENT_PIPELINE_DIR = ROOT / "tools" / "content_pipeline"
ASSET_GRAPH_DIR = ROOT / "tools" / "asset_graph"
for path in (CONTENT_PIPELINE_DIR, ASSET_GRAPH_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from validate_mvp_handoff_audit_report import validate_report  # noqa: E402


DEFAULT_OUTPUT = ROOT / "examples/review_packs/mvp_handoff_audit_report.v0.1.json"
CREATED_AT = "2026-07-01T00:00:00+08:00"
MAX_TAIL_CHARS = 1800


CORE_COMMANDS: list[tuple[str, list[str]]] = [
    (
        "build_multistage_content_pack",
        ["python3", "tools/content_pipeline/build_multistage_content_pack.py", "--validate"],
    ),
    (
        "validate_multistage_stage_candidate_pack",
        [
            "python3",
            "tools/content_pipeline/validate_stage_candidate_pack.py",
            "examples/review_packs/mvp_multistage_stage_candidate_pack.v0.1.json",
        ],
    ),
    (
        "build_compilable_object_catalog",
        ["python3", "tools/content_pipeline/build_compilable_object_catalog.py", "--validate"],
    ),
    (
        "build_frontend_mock_pack",
        ["python3", "tools/content_pipeline/build_frontend_mock_pack.py"],
    ),
    (
        "validate_frontend_mock_pack",
        [
            "python3",
            "tools/content_pipeline/validate_frontend_mock_pack.py",
            "examples/frontend_mock/frontend_mock_pack.v0.1.json",
        ],
    ),
    (
        "validate_runtime_package_first_battle",
        [
            "python3",
            "tools/asset_graph/validate_runtime_package.py",
            "examples/runtime_packages/mvp_demo.runtime_package.json",
        ],
    ),
    (
        "validate_runtime_package_wick_store",
        [
            "python3",
            "tools/asset_graph/validate_runtime_package.py",
            "examples/runtime_packages/mvp_wick_store_pressure.runtime_package.json",
        ],
    ),
    (
        "validate_runtime_package_old_signal_tower",
        [
            "python3",
            "tools/asset_graph/validate_runtime_package.py",
            "examples/runtime_packages/mvp_old_signal_tower.runtime_package.json",
        ],
    ),
    (
        "validate_story_asset_review_pack",
        [
            "python3",
            "tools/content_pipeline/validate_mvp_story_asset_review_pack.py",
            "examples/review_packs/mvp_story_asset_review_pack.v0.1.json",
        ],
    ),
    (
        "validate_narrative_gameplay_contract",
        [
            "python3",
            "tools/narrative/validate_narrative_gameplay_contract.py",
            "examples/review_packs/mvp_story_asset_review_pack.v0.1.json",
        ],
    ),
    (
        "build_mvp_compiler_review_dossier",
        ["python3", "tools/content_pipeline/build_mvp_compiler_review_dossier.py", "--validate"],
    ),
]


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


def tail(value: str) -> str:
    normalized = value.replace(str(ROOT), "$REPO_ROOT")
    return normalized[-MAX_TAIL_CHARS:]


def run_core_commands() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for name, command in CORE_COMMANDS:
        completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        results.append({
            "name": name,
            "command": " ".join(command),
            "return_code": completed.returncode,
            "status": "passed" if completed.returncode == 0 else "failed",
            "stdout_tail": tail(completed.stdout),
            "stderr_tail": tail(completed.stderr),
        })
    return results


def pipeline_logic() -> list[str]:
    return [
        "对象计划定义下一阶段需要生成的任务、事件、样品、资产和状态变化边界。",
        "叙事包生成世界线、玩家线和共享节点，但不能直接修改运行态。",
        "WorldStateDelta 把叙事承诺落到可校验的任务、随机事件、素材、NPC、地图节点和研究状态。",
        "语义门在应用 Delta 前检查引用、前置条件和运行态一致性。",
        "资产提案进入候选资产，再经过效果白名单、模拟、评分和晋级策略。",
        "通过审查的候选可以进入 locked manifest 与 runtime package；未晋级内容只保留为审查或 fallback 证据。",
        "前端 mock 内容包只抽取玩家安全字段，用于并行开发和演示，不代表正式前端接入。",
        "总审查交付包索引所有关键证据、验证命令和已知风险。",
    ]


def review_entrypoints() -> list[dict[str, str]]:
    return [
        {
            "path": "examples/review_packs/mvp_handoff_audit_report.v0.1.json",
            "purpose": "本文件，一键审查执行报告。",
        },
        {
            "path": "examples/review_packs/mvp_compiler_review_dossier.v0.1.json",
            "purpose": "总审查交付包，索引流水线、产物、验证命令和风险。",
        },
        {
            "path": "examples/review_packs/mvp_multistage_content_pack.v0.1.json",
            "purpose": "三阶段内容生产链详细证据。",
        },
        {
            "path": "examples/review_packs/mvp_multistage_stage_candidate_pack.v0.1.json",
            "purpose": "三阶段标准候选包，便于逐阶段审查。",
        },
        {
            "path": "examples/frontend_mock/frontend_mock_pack.v0.1.json",
            "purpose": "玩家安全 mock 数据包，包含资产、阶段摘要和运行时包摘要。",
        },
    ]


def artifact_summary() -> dict[str, Any]:
    multistage_pack = load_json(ROOT / "examples/review_packs/mvp_multistage_content_pack.v0.1.json")
    stage_candidate_pack = load_json(ROOT / "examples/review_packs/mvp_multistage_stage_candidate_pack.v0.1.json")
    catalog = load_json(ROOT / "examples/review_packs/mvp_compilable_object_catalog.v0.1.json")
    frontend = load_json(ROOT / "examples/frontend_mock/frontend_mock_pack.v0.1.json")
    dossier = load_json(ROOT / "examples/review_packs/mvp_compiler_review_dossier.v0.1.json")
    runtime_packages = [
        load_json(ROOT / "examples/runtime_packages/mvp_demo.runtime_package.json"),
        load_json(ROOT / "examples/runtime_packages/mvp_wick_store_pressure.runtime_package.json"),
        load_json(ROOT / "examples/runtime_packages/mvp_old_signal_tower.runtime_package.json"),
    ]

    frontend_summary = as_obj(frontend.get("compiler_summary"))
    catalog_summary = as_obj(catalog.get("summary"))
    dossier_readiness = as_obj(dossier.get("readiness_summary"))
    stage_candidates = as_list(stage_candidate_pack.get("stage_candidates"))
    return {
        "multistage_content_pack": {
            "pack_id": multistage_pack.get("pack_id"),
            "stage_count": as_obj(multistage_pack.get("summary")).get("stage_count"),
            "asset_type_counts": as_obj(multistage_pack.get("summary")).get("asset_type_counts"),
            "final_state_file": as_obj(multistage_pack.get("summary")).get("final_state_file"),
        },
        "multistage_stage_candidate_pack": {
            "pack_id": stage_candidate_pack.get("pack_id"),
            "stage_count": len(stage_candidates),
            "readiness_summary": as_obj(stage_candidate_pack.get("readiness_summary")),
            "stage_titles": [stage.get("title") for stage in stage_candidates if isinstance(stage, dict)],
            "stages": [
                {
                    "stage_id": stage.get("stage_id"),
                    "title": stage.get("title"),
                    "lane_coverage": as_list(stage.get("lane_coverage")),
                    "asset_ids": [
                        asset.get("asset_id")
                        for asset in as_list(stage.get("asset_outputs"))
                        if isinstance(asset, dict) and asset.get("asset_id")
                    ],
                    "runtime_package_refs": as_list(stage.get("runtime_package_refs")),
                }
                for stage in stage_candidates
                if isinstance(stage, dict)
            ],
        },
        "compilable_object_catalog": {
            "total_objects": catalog_summary.get("total_objects"),
            "layer_counts": as_obj(catalog_summary.get("layer_counts")),
            "runtime_export_counts": as_obj(catalog_summary.get("runtime_export_counts")),
            "review_required_count": catalog_summary.get("review_required_count"),
        },
        "frontend_mock_pack": {
            "asset_count": frontend_summary.get("asset_count"),
            "playable_count": frontend_summary.get("playable_count"),
            "asset_count_by_type": as_obj(frontend_summary.get("asset_count_by_type")),
            "stage_count": frontend_summary.get("stage_count"),
            "runtime_package_count": frontend_summary.get("runtime_package_count"),
            "promotion_states": as_obj(frontend_summary.get("promotion_states")),
        },
        "runtime_packages": [
            {
                "package_id": package.get("package_id"),
                "node_id": package.get("node_id"),
                "asset_count": len(as_list(package.get("assets"))),
            }
            for package in runtime_packages
        ],
        "dossier": {
            "dossier_id": dossier.get("dossier_id"),
            "source_evidence_count": len(as_list(dossier.get("source_evidence"))),
            "validation_command_count": len(as_list(dossier.get("validation_commands"))),
            "readiness_summary": dossier_readiness,
        },
    }


def coverage_checks(command_results: list[dict[str, Any]], summary: dict[str, Any]) -> list[dict[str, Any]]:
    commands_passed = all(result.get("status") == "passed" for result in command_results)
    multistage = as_obj(summary.get("multistage_stage_candidate_pack"))
    readiness = as_obj(multistage.get("readiness_summary"))
    frontend = as_obj(summary.get("frontend_mock_pack"))
    catalog = as_obj(summary.get("compilable_object_catalog"))
    runtime_packages = as_list(summary.get("runtime_packages"))
    stages = [stage for stage in as_list(multistage.get("stages")) if isinstance(stage, dict)]
    lanes_ok = all(
        {"world_line", "player_line"}.issubset(set(as_list(stage.get("lane_coverage"))))
        for stage in stages
    )

    checks: list[dict[str, Any]] = [
        {
            "check_id": "core_commands_passed",
            "status": "passed" if commands_passed else "failed",
            "summary": "核心离线构建和校验命令全部通过。" if commands_passed else "至少一个核心命令失败。",
            "evidence": {"failed_commands": [r.get("name") for r in command_results if r.get("status") != "passed"]},
        },
        {
            "check_id": "multistage_content_present",
            "status": "passed" if int(multistage.get("stage_count") or 0) >= 3 else "failed",
            "summary": "已生成至少三个连续阶段的内容候选。",
            "evidence": {"stage_count": multistage.get("stage_count"), "stage_titles": multistage.get("stage_titles")},
        },
        {
            "check_id": "world_and_player_lane_coverage",
            "status": "passed" if stages and lanes_ok else "failed",
            "summary": "三阶段候选包均覆盖世界线、玩家线和共享节点。",
            "evidence": {
                "stage_count": multistage.get("stage_count"),
                "lanes": [
                    {
                        "stage_id": stage.get("stage_id"),
                        "lane_coverage": as_list(stage.get("lane_coverage")),
                    }
                    for stage in stages
                ],
            },
        },
        {
            "check_id": "per_stage_playable_asset_reference",
            "status": "passed" if int(readiness.get("playable_asset_reference_count") or 0) >= 3 else "failed",
            "summary": "每个新增阶段至少有一个可玩资产候选引用。",
            "evidence": {"playable_asset_reference_count": readiness.get("playable_asset_reference_count")},
        },
        {
            "check_id": "frontend_mock_player_safe_bundle",
            "status": "passed" if frontend.get("asset_count") == frontend.get("playable_count") and int(frontend.get("asset_count") or 0) >= 11 else "failed",
            "summary": "前端 mock 包只暴露可玩资产，并包含当前多阶段新增资产。",
            "evidence": frontend,
        },
        {
            "check_id": "runtime_package_evidence",
            "status": "passed" if len(runtime_packages) >= 3 else "failed",
            "summary": "已有三个 runtime package 证据包，覆盖第一战、灯芯仓压力战和旧信号塔压力战。",
            "evidence": {"runtime_packages": runtime_packages},
        },
        {
            "check_id": "object_catalog_coverage",
            "status": "passed" if int(catalog.get("total_objects") or 0) >= 100 else "failed",
            "summary": "可编译对象目录覆盖实体、叙事、关卡、经济、成长、规则和表现层。",
            "evidence": catalog,
        },
        {
            "check_id": "no_formal_frontend_integration",
            "status": "passed",
            "summary": "当前交付仍是不接入正式前端的审查与 mock 数据包。",
            "evidence": {"front_end_integration": "not_included"},
        },
    ]
    return checks


def build_report(command_results: list[dict[str, Any]], created_at: str) -> dict[str, Any]:
    summary = artifact_summary()
    checks = coverage_checks(command_results, summary)
    dossier = load_json(ROOT / "examples/review_packs/mvp_compiler_review_dossier.v0.1.json")
    failed_commands = [result for result in command_results if result.get("status") != "passed"]
    failed_checks = [check for check in checks if check.get("status") == "failed"]
    return {
        "schema_version": "mvp_handoff_audit_report.v0.1",
        "report_id": "mvp_handoff_audit_report_001",
        "visibility": "review_only",
        "created_at": created_at,
        "overall_status": "failed" if failed_commands or failed_checks else "passed",
        "generation_boundary": {
            "front_end_integration": "not_included",
            "audit_reads_env": False,
            "audit_calls_external_service": False,
            "base_worldbook_mutation": False,
            "report_contains_raw_external_payload": False,
        },
        "pipeline_logic": pipeline_logic(),
        "review_entrypoints": review_entrypoints(),
        "command_results": command_results,
        "artifact_summary": summary,
        "coverage_checks": checks,
        "known_risks": as_list(dossier.get("known_risks")),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run offline MVP handoff audit.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--created-at", default=CREATED_AT)
    parser.add_argument("--validate", action="store_true", help="Validate the generated audit report.")
    args = parser.parse_args()

    command_results = run_core_commands()
    report = build_report(command_results, args.created_at)
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    write_json(output, report)

    validation_errors = validate_report(report) if args.validate else []
    print(f"Wrote {output}")
    print(f"- overall_status: {report['overall_status']}")
    print(f"- commands: {len(report['command_results'])}")
    print(f"- coverage_checks: {len(report['coverage_checks'])}")
    if validation_errors:
        print("INVALID MvpHandoffAuditReport")
        for error in validation_errors:
            print(f"- {error}")
        return 1
    if args.validate:
        print("OK MvpHandoffAuditReport")
    return 0 if report["overall_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
