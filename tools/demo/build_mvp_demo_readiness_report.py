#!/usr/bin/env python3
"""Build an offline MVP demo readiness report from reviewed evidence packs."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = (
    ROOT / "examples/review_packs/mvp_demo_readiness_report.v0.1.json"
)

PATHS = {
    "mvp_primary_api_flow": ROOT
    / "examples/review_packs/mvp_primary_api_flow_smoke_report.v0.1.json",
    "map_v02_preview_api": ROOT
    / "examples/review_packs/map_v02_preview_api_smoke_report.v0.1.json",
    "map_runtime_v02_opt_in_contract": ROOT
    / "examples/review_packs/map_runtime_v02_opt_in_contract_smoke_report.v0.1.json",
    "map_runtime_activation_gate": ROOT
    / "examples/review_packs/map_runtime_activation_gate_report.v0.1.json",
    "map_runtime_v02_activation_contract_plan": ROOT
    / "examples/review_packs/map_runtime_v02_activation_contract_plan.v0.1.json",
    "map_runtime_v02_semantic_geometry": ROOT
    / "examples/review_packs/map_runtime_v02_semantic_geometry_report.v0.1.json",
    "core_artifact_alignment": ROOT
    / "examples/review_packs/core_artifact_alignment_report.v0.1.json",
    "map_visual_promotion_gate": ROOT
    / "examples/review_packs/map_visual_promotion_gate_report.v0.1.json",
    "map_visual_quality": ROOT
    / "examples/review_packs/map_visual_quality_report.v0.1.json",
    "runtime_sprite_cutout_quality": ROOT
    / "examples/review_packs/frontend_runtime_sprite_cutout_quality_report.v0.1.json",
    "runtime_loop_continuity": ROOT
    / "examples/review_packs/frontend_runtime_loop_continuity_report.v0.1.json",
    "provider_video_runner_receipt": ROOT
    / "examples/provider_adapter_runs/p1a_provider_adapter_video_runner.receipt.json",
    "provider_video_runner_envelope": ROOT
    / "examples/provider_adapter_runs/p1a_provider_adapter_video_runner.envelope.json",
    "provider_video_adapter_task_pack": ROOT
    / "examples/worker_task_packs/p1a_provider_video_adapter_boundary.v0.1.json",
    "provider_video_handoff_task_pack": ROOT
    / "examples/worker_task_packs/p1b_provider_video_handoff_template.v0.1.json",
    "controlled_map_candidate_review": ROOT
    / "examples/review_packs/controlled_map_candidate_review.v0.1.json",
    "controlled_map_text_fallback_review": ROOT
    / "examples/review_packs/controlled_map_text_fallback_candidate_review.v0.1.json",
    "map_candidate_overlay_visual_review": ROOT
    / "examples/review_packs/map_candidate_overlay_visual_review.v0.1.json",
    "frontend_flow_visual_smoke_tool": ROOT
    / "tools/frontend/capture_frontend_flow_visual_smoke.py",
    "frontend_flow_visual_smoke_validator": ROOT
    / "tools/frontend/validate_frontend_flow_visual_smoke_report.py",
    "frontend_flow_visual_smoke_task_pack": ROOT
    / "examples/worker_task_packs/p1d_browser_flow_visual_smoke.v0.1.json",
}

PASSING_STATUSES = {"passed", "passed_with_warnings"}
NON_BLOCKING_STATUSES = {"passed", "passed_with_warnings", "blocked_as_expected"}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def source_ref(path: Path) -> dict[str, Any]:
    return {
        "path": rel(path),
        "exists": path.exists(),
    }


def gate(
    gate_id: str,
    title: str,
    status: str,
    required_for_mvp_demo: bool,
    summary: str,
    evidence_keys: list[str],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "gate_id": gate_id,
        "title": title,
        "status": status,
        "required_for_mvp_demo": required_for_mvp_demo,
        "summary": summary,
        "evidence_refs": [
            source_ref(PATHS[key])
            for key in evidence_keys
        ],
        "metrics": metrics,
    }


def primary_api_gate(report: dict[str, Any]) -> dict[str, Any]:
    safety = as_obj(report.get("safety_summary"))
    step_count = int(report.get("step_count") or 0)
    passed_step_count = int(report.get("passed_step_count") or 0)
    checks = as_obj(report.get("checks"))
    ok = (
        report.get("status") == "passed"
        and step_count > 0
        and passed_step_count == step_count
        and all(value is True for value in checks.values())
        and int(safety.get("provider_call_count") or 0) == 0
        and int(safety.get("runtime_activation_mutation_count") or 0) == 0
    )
    return gate(
        gate_id="primary_api_flow",
        title="MVP 玩家主流程 API",
        status="passed" if ok else "not_ready",
        required_for_mvp_demo=True,
        summary="本地 HTTP smoke 已走通匿名 session、世界实例、研发、战斗、结算与 session evidence。",
        evidence_keys=["mvp_primary_api_flow"],
        metrics={
            "report_status": report.get("status"),
            "step_count": step_count,
            "passed_step_count": passed_step_count,
            "provider_call_count": safety.get("provider_call_count"),
            "runtime_activation_mutation_count": safety.get(
                "runtime_activation_mutation_count"
            ),
            "research_job_completed": as_obj(report.get("research")).get(
                "job_status"
            )
            == "completed",
        },
    )


def map_v02_api_gate(report: dict[str, Any]) -> dict[str, Any]:
    safety = as_obj(report.get("safety_summary"))
    node_count = int(report.get("node_count") or 0)
    default_count = int(report.get("default_runtime_v01_preserved_count") or 0)
    ok = (
        report.get("status") == "passed"
        and node_count >= 3
        and default_count == node_count
        and int(safety.get("provider_call_count") or 0) == 0
        and report.get("runtime_activation_allowed") is False
    )
    return gate(
        gate_id="map_v02_preview_api",
        title="MapRuntimePackage v0.2 预览 API",
        status="passed" if ok else "not_ready",
        required_for_mvp_demo=True,
        summary="v0.2 强语义地图预览已可通过后端 API 读取，且不会替换玩家默认 v0.1 运行时地图。",
        evidence_keys=["map_v02_preview_api"],
        metrics={
            "report_status": report.get("status"),
            "node_count": node_count,
            "default_runtime_v01_preserved_count": default_count,
            "provider_call_count": safety.get("provider_call_count"),
            "runtime_activation_allowed": report.get("runtime_activation_allowed"),
        },
    )


def map_runtime_v02_opt_in_gate(report: dict[str, Any]) -> dict[str, Any]:
    summary = as_obj(report.get("summary"))
    safety = as_obj(report.get("safety"))
    node_count = int(report.get("node_count") or 0)
    ok = (
        report.get("status") == "passed"
        and node_count >= 3
        and int(summary.get("default_runtime_v01_preserved_count") or 0) == node_count
        and int(summary.get("api_pending_authorization_count") or 0) == node_count
        and int(summary.get("approved_candidate_available_count") or 0) == node_count
        and int(summary.get("runtime_activation_allowed_count") or 0) == 0
        and int(safety.get("provider_call_count") or 0) == 0
        and int(safety.get("default_runtime_mutation_count") or 0) == 0
    )
    return gate(
        gate_id="map_runtime_v02_opt_in_contract",
        title="MapRuntimePackage v0.2 opt-in dry-run 合同",
        status="passed" if ok else "not_ready",
        required_for_mvp_demo=False,
        summary="v0.2 强语义地图已有 opt-in dry-run 证据：默认 API 仍 pending/v0.1，临时授权夹具可读取候选，但不会激活 runtime。",
        evidence_keys=["map_runtime_v02_opt_in_contract"],
        metrics={
            "report_status": report.get("status"),
            "node_count": node_count,
            "default_runtime_v01_preserved_count": summary.get(
                "default_runtime_v01_preserved_count"
            ),
            "api_pending_authorization_count": summary.get(
                "api_pending_authorization_count"
            ),
            "approved_candidate_available_count": summary.get(
                "approved_candidate_available_count"
            ),
            "runtime_activation_allowed_count": summary.get(
                "runtime_activation_allowed_count"
            ),
            "provider_call_count": safety.get("provider_call_count"),
            "default_runtime_mutation_count": safety.get(
                "default_runtime_mutation_count"
            ),
        },
    )


def map_runtime_activation_contract_gate(
    activation_gate_report: dict[str, Any],
    contract_plan_report: dict[str, Any],
) -> dict[str, Any]:
    gate_summary = as_obj(activation_gate_report.get("summary"))
    gate_safety = as_obj(activation_gate_report.get("safety_summary"))
    plan_summary = as_obj(contract_plan_report.get("summary"))
    plan_safety = as_obj(contract_plan_report.get("safety_summary"))
    frontend_status = plan_summary.get("frontend_contract_status") or gate_summary.get(
        "frontend_v02_contract_status"
    )
    activation_allowed_count = int(plan_summary.get("activation_allowed_count") or 0)
    activation_apply_now_count = int(plan_summary.get("activation_apply_now_count") or 0)
    runtime_mutation_count = int(plan_summary.get("runtime_mutation_count_by_plan") or 0)
    ok = (
        activation_gate_report.get("status") == "blocked"
        and contract_plan_report.get("status") == "plan_ready_activation_not_applied"
        and frontend_status == "pre_activation_ready"
        and activation_allowed_count == 0
        and activation_apply_now_count == 0
        and runtime_mutation_count == 0
        and plan_safety.get("default_runtime_mutation_performed") is False
        and gate_safety.get("default_runtime_mutation_performed") is False
    )
    return gate(
        gate_id="map_runtime_activation_contract",
        title="MapRuntimePackage v0.2 激活合同门",
        status="passed_with_warnings" if ok else "not_ready",
        required_for_mvp_demo=False,
        summary=(
            "v0.2 强语义前端消费已预接入，但默认 runtime 仍保持 v0.1；"
            "正式激活仍需要开发者授权、后端默认选择器和激活后证据复跑。"
        ),
        evidence_keys=[
            "map_runtime_activation_gate",
            "map_runtime_v02_activation_contract_plan",
        ],
        metrics={
            "activation_gate_status": activation_gate_report.get("status"),
            "contract_plan_status": plan_summary.get("contract_plan_status"),
            "frontend_contract_status": frontend_status,
            "frontend_pre_activation_ready_count": plan_summary.get(
                "frontend_pre_activation_ready_count"
            ),
            "frontend_post_activation_evidence_required_count": plan_summary.get(
                "frontend_post_activation_evidence_required_count"
            ),
            "activation_allowed_count": activation_allowed_count,
            "activation_apply_now_count": activation_apply_now_count,
            "backend_required_change_count": plan_summary.get(
                "backend_required_change_count"
            ),
            "runtime_mutation_count_by_plan": runtime_mutation_count,
            "default_runtime_mutation_performed": plan_safety.get(
                "default_runtime_mutation_performed"
            ),
            "blocker_counts": as_obj(gate_summary.get("blocker_counts")),
        },
    )


def map_runtime_v02_semantic_geometry_gate(report: dict[str, Any]) -> dict[str, Any]:
    summary = as_obj(report.get("summary"))
    source_policy = as_obj(report.get("source_policy"))
    map_count = int(summary.get("map_count") or 0)
    error_count = int(summary.get("error_count") or 0)
    warning_count = int(summary.get("warning_count") or 0)
    ok = (
        report.get("status") in PASSING_STATUSES
        and map_count >= 3
        and error_count == 0
        and int(report.get("provider_call_count") or 0) == 0
        and report.get("runtime_effect") is False
        and report.get("default_runtime_mutation") is False
        and source_policy.get("runtime_package_schema_version")
        == "map_runtime_package.v0.2"
        and source_policy.get("no_image_or_preview_reverse_inference") is True
        and source_policy.get("does_not_modify_runtime_package") is True
        and source_policy.get("does_not_read_env") is True
        and source_policy.get("does_not_call_provider") is True
    )
    status = "not_ready"
    if ok:
        status = "passed_with_warnings" if warning_count else "passed"
    return gate(
        gate_id="map_runtime_v02_semantic_geometry",
        title="MapRuntimePackage v0.2 强语义几何审查",
        status=status,
        required_for_mvp_demo=True,
        summary=(
            "v0.2 资源点、机关区、防守锚点和阻挡区已通过结构化几何审查；"
            "warning 只作为 review evidence，不会修改默认 v0.1 runtime。"
        ),
        evidence_keys=["map_runtime_v02_semantic_geometry"],
        metrics={
            "report_status": report.get("status"),
            "map_count": map_count,
            "resource_node_count": summary.get("resource_node_count"),
            "hazard_zone_count": summary.get("hazard_zone_count"),
            "defense_anchor_count": summary.get("defense_anchor_count"),
            "blocked_area_count": summary.get("blocked_area_count"),
            "warning_count": warning_count,
            "error_count": error_count,
            "status_counts": as_obj(summary.get("status_counts")),
            "provider_call_count": report.get("provider_call_count"),
            "runtime_effect": report.get("runtime_effect"),
            "default_runtime_mutation": report.get("default_runtime_mutation"),
            "semantic_source": source_policy.get("semantic_source"),
            "geometry_source": source_policy.get("geometry_source"),
        },
    )


def core_alignment_gate(report: dict[str, Any]) -> dict[str, Any]:
    summary = as_obj(report.get("summary"))
    ok = (
        summary.get("overall_status") == "passed"
        and int(summary.get("missing_core_alignment_count") or 0) == 0
        and int(summary.get("validation_failed_count") or 0) == 0
    )
    return gate(
        gate_id="core_artifact_alignment",
        title="AI 编译核心对象对齐",
        status="passed" if ok else "not_ready",
        required_for_mvp_demo=True,
        summary="ContextPackage、FactEntry、CGOP 与事务链证据已完成核心对齐审计。",
        evidence_keys=["core_artifact_alignment"],
        metrics={
            "overall_status": summary.get("overall_status"),
            "target_count": summary.get("target_count"),
            "missing_core_alignment_count": summary.get(
                "missing_core_alignment_count"
            ),
            "validation_failed_count": summary.get("validation_failed_count"),
            "native_snapshot_ready_count": summary.get(
                "native_snapshot_ready_count"
            ),
        },
    )


def map_visual_gate(
    promotion_report: dict[str, Any],
    quality_report: dict[str, Any],
) -> dict[str, Any]:
    promotion_summary = as_obj(promotion_report.get("summary"))
    quality_summary = as_obj(quality_report.get("summary"))
    violation_count = int(promotion_summary.get("violation_count") or 0)
    quality_status = quality_report.get("status")
    if promotion_report.get("status") == "passed" and violation_count == 0:
        status = "passed_with_warnings" if quality_status == "passed_with_warnings" else "passed"
    else:
        status = "not_ready"
    return gate(
        gate_id="map_visual_runtime_safety",
        title="地图视觉发布安全",
        status=status,
        required_for_mvp_demo=True,
        summary="候选地图被 promotion gate 隔离，玩家侧不会误用 review-only 或失败地图；地图美术质量仍有 warning。",
        evidence_keys=["map_visual_promotion_gate", "map_visual_quality"],
        metrics={
            "promotion_status": promotion_report.get("status"),
            "quality_status": quality_status,
            "blocked_candidate_count": promotion_summary.get(
                "blocked_candidate_count"
            ),
            "published_player_layer_count": promotion_summary.get(
                "published_player_layer_count"
            ),
            "violation_count": violation_count,
            "warning_counts": as_obj(quality_summary.get("warning_counts")),
        },
    )


def runtime_sprite_gate(report: dict[str, Any]) -> dict[str, Any]:
    summary = as_obj(report.get("summary")) or report
    ok = report.get("status") == "passed" and int(summary.get("failed_count") or 0) == 0
    return gate(
        gate_id="runtime_sprite_geometry",
        title="战斗运行时 sprite 几何质量",
        status="passed" if ok else "not_ready",
        required_for_mvp_demo=True,
        summary="战斗运行时素材已通过 cutout quality gate，可供当前 MVP 战斗画面使用。",
        evidence_keys=["runtime_sprite_cutout_quality"],
        metrics={
            "report_status": report.get("status"),
            "sprite_item_count": summary.get("sprite_item_count"),
            "passed_count": summary.get("passed_count"),
            "needs_review_count": summary.get("needs_review_count"),
            "failed_count": summary.get("failed_count"),
        },
    )


def loop_continuity_gate(report: dict[str, Any]) -> dict[str, Any]:
    summary = as_obj(report.get("summary"))
    failed_count = int(summary.get("failed_count") or 0)
    checked_count = int(summary.get("checked_count") or 0)
    status = "not_ready"
    if report.get("status") in PASSING_STATUSES and failed_count == 0:
        status = "passed_with_warnings"
    return gate(
        gate_id="runtime_loop_continuity",
        title="运行时循环动画连续性",
        status=status,
        required_for_mvp_demo=False,
        summary="当前 atlas 可循环播放，但帧序列仍是确定性占位，不等同于真实图生视频关键帧。",
        evidence_keys=["runtime_loop_continuity"],
        metrics={
            "report_status": report.get("status"),
            "animation_count": summary.get("animation_count"),
            "checked_count": checked_count,
            "passed_with_warnings_count": summary.get("passed_with_warnings_count"),
            "failed_count": failed_count,
            "frame_source_counts": as_obj(summary.get("frame_source_counts")),
        },
    )


def provider_video_boundary_gate(
    receipt: dict[str, Any],
    envelope: dict[str, Any],
    adapter_task_pack: dict[str, Any],
    handoff_task_pack: dict[str, Any],
) -> dict[str, Any]:
    receipt_source = as_obj(receipt.get("source"))
    receipt_authority = as_obj(receipt.get("authority"))
    receipt_execution = as_obj(receipt.get("execution"))
    receipt_safety = as_obj(receipt.get("adapter_safety"))
    envelope_source = as_obj(envelope.get("source"))
    envelope_authority = as_obj(envelope.get("authority"))
    provider_call = as_obj(envelope.get("provider_call"))
    result_summary = as_obj(envelope.get("redacted_result_summary"))
    activation_gate = as_obj(envelope.get("activation_gate"))
    adapter_policy = as_obj(adapter_task_pack.get("provider_policy"))
    handoff_policy = as_obj(handoff_task_pack.get("provider_policy"))
    checks = {
        "receipt_video_mode": receipt_source.get("provider_mode")
        == "video_boundary_dry_run",
        "receipt_review_only": receipt_authority.get("review_only") is True,
        "receipt_provider_call_not_performed": receipt_execution.get(
            "provider_call_performed_by_receipt_builder"
        )
        is False,
        "receipt_finish_reason": receipt_execution.get("finish_reason")
        == "video_live_provider_not_implemented",
        "receipt_safety_no_provider_call": receipt_safety.get("calls_provider")
        is False,
        "envelope_video_mode": envelope_source.get("provider_mode")
        == "video_boundary_dry_run",
        "envelope_review_only": envelope_authority.get("review_only") is True,
        "envelope_provider_call_not_performed": provider_call.get("performed")
        is False,
        "envelope_result_blocked_before_provider": result_summary.get("status")
        == "blocked_before_provider_call",
        "envelope_finish_reason": result_summary.get("finish_reason")
        == "video_live_provider_not_implemented",
        "activation_not_allowed": activation_gate.get("activation_allowed") is False,
        "adapter_task_pack_no_provider_calls": adapter_policy.get(
            "provider_calls_allowed"
        )
        is False,
        "handoff_task_pack_no_provider_calls": handoff_policy.get(
            "provider_calls_allowed"
        )
        is False,
    }
    ok = all(checks.values())
    return gate(
        gate_id="provider_video_boundary",
        title="视频 provider 离线边界",
        status="passed_with_warnings" if ok else "not_ready",
        required_for_mvp_demo=False,
        summary=(
            "图生视频 provider 尚未接入玩家 runtime；当前只证明 video adapter "
            "dry boundary、receipt/envelope 和 scheduler handoff 模板可见且不调用 provider。"
        ),
        evidence_keys=[
            "provider_video_runner_receipt",
            "provider_video_runner_envelope",
            "provider_video_adapter_task_pack",
            "provider_video_handoff_task_pack",
        ],
        metrics={
            "checks": checks,
            "receipt_execution_status": receipt_execution.get("status"),
            "receipt_finish_reason": receipt_execution.get("finish_reason"),
            "envelope_result_kind": result_summary.get("result_kind"),
            "envelope_result_status": result_summary.get("status"),
            "provider_call_performed": provider_call.get("performed"),
            "activation_allowed": activation_gate.get("activation_allowed"),
            "live_video_provider_ready": False,
        },
    )


def blocked_map_candidate_gate(
    controlled_review: dict[str, Any],
    text_fallback_review: dict[str, Any],
    overlay_visual_review: dict[str, Any],
) -> dict[str, Any]:
    controlled_summary = as_obj(controlled_review.get("summary"))
    text_summary = as_obj(text_fallback_review.get("summary"))
    overlay_summary = as_obj(overlay_visual_review.get("summary"))
    ok = (
        int(controlled_summary.get("runtime_promotion_count") or 0) == 0
        and int(text_summary.get("runtime_promotion_count") or 0) == 0
        and int(overlay_summary.get("promotable_count") or 0) == 0
    )
    return gate(
        gate_id="negative_map_candidates_isolated",
        title="失败地图候选隔离",
        status="blocked_as_expected" if ok else "not_ready",
        required_for_mvp_demo=True,
        summary="已知失败或未完成对齐的地图候选只作为负样本证据，不会晋升到玩家 runtime。",
        evidence_keys=[
            "controlled_map_candidate_review",
            "controlled_map_text_fallback_review",
            "map_candidate_overlay_visual_review",
        ],
        metrics={
            "controlled_runtime_promotion_count": controlled_summary.get(
                "runtime_promotion_count"
            ),
            "text_fallback_runtime_promotion_count": text_summary.get(
                "runtime_promotion_count"
            ),
            "overlay_promotable_count": overlay_summary.get("promotable_count"),
            "text_fallback_candidate_status": text_fallback_review.get("status"),
            "overlay_visual_status": overlay_visual_review.get("status"),
        },
    )


def frontend_flow_smoke_gate() -> dict[str, Any]:
    tool_ready = PATHS["frontend_flow_visual_smoke_tool"].exists()
    validator_ready = PATHS["frontend_flow_visual_smoke_validator"].exists()
    task_pack_ready = PATHS["frontend_flow_visual_smoke_task_pack"].exists()
    status = "passed" if tool_ready and validator_ready and task_pack_ready else "not_ready"
    return gate(
        gate_id="frontend_flow_visual_smoke_harness",
        title="浏览器玩家链路截图门禁",
        status=status,
        required_for_mvp_demo=True,
        summary="玩家入口、开局配置、开场、大地图、工坊、战斗和结算已具备真实 Chromium 截图 smoke harness；截图报告是运行时 evidence，需要按任务包命令复跑生成。",
        evidence_keys=[
            "frontend_flow_visual_smoke_tool",
            "frontend_flow_visual_smoke_validator",
            "frontend_flow_visual_smoke_task_pack",
        ],
        metrics={
            "tool_ready": tool_ready,
            "validator_ready": validator_ready,
            "task_pack_ready": task_pack_ready,
            "expected_viewports": ["desktop", "mobile"],
            "expected_step_count_per_viewport": 7,
            "expected_screenshot_count": 14,
            "provider_call_count": 0,
        },
    )


def build_report(generated_at: str) -> dict[str, Any]:
    reports = {
        key: load_json(path)
        for key, path in PATHS.items()
        if path.suffix == ".json"
    }
    gates = [
        primary_api_gate(reports["mvp_primary_api_flow"]),
        map_v02_api_gate(reports["map_v02_preview_api"]),
        map_runtime_v02_opt_in_gate(reports["map_runtime_v02_opt_in_contract"]),
        map_runtime_activation_contract_gate(
            reports["map_runtime_activation_gate"],
            reports["map_runtime_v02_activation_contract_plan"],
        ),
        map_runtime_v02_semantic_geometry_gate(
            reports["map_runtime_v02_semantic_geometry"]
        ),
        core_alignment_gate(reports["core_artifact_alignment"]),
        map_visual_gate(
            reports["map_visual_promotion_gate"],
            reports["map_visual_quality"],
        ),
        runtime_sprite_gate(reports["runtime_sprite_cutout_quality"]),
        loop_continuity_gate(reports["runtime_loop_continuity"]),
        provider_video_boundary_gate(
            reports["provider_video_runner_receipt"],
            reports["provider_video_runner_envelope"],
            reports["provider_video_adapter_task_pack"],
            reports["provider_video_handoff_task_pack"],
        ),
        blocked_map_candidate_gate(
            reports["controlled_map_candidate_review"],
            reports["controlled_map_text_fallback_review"],
            reports["map_candidate_overlay_visual_review"],
        ),
        frontend_flow_smoke_gate(),
    ]

    required_gates = [item for item in gates if item["required_for_mvp_demo"]]
    blocking_gates = [
        item
        for item in required_gates
        if item["status"] not in NON_BLOCKING_STATUSES
    ]
    warning_gates = [item for item in gates if item["status"] == "passed_with_warnings"]
    expected_blocks = [item for item in gates if item["status"] == "blocked_as_expected"]
    if blocking_gates:
        overall_status = "not_ready_for_mvp_demo"
    elif warning_gates or expected_blocks:
        overall_status = "ready_for_mvp_demo_with_known_limitations"
    else:
        overall_status = "ready_for_mvp_demo"

    return {
        "schema_version": "mvp_demo_readiness_report.v0.1",
        "report_id": "mvp_demo_readiness_report_v0_1",
        "generated_at": generated_at,
        "overall_status": overall_status,
        "summary": {
            "required_gate_count": len(required_gates),
            "required_gate_passed_or_expected_count": len(required_gates)
            - len(blocking_gates),
            "blocking_gate_count": len(blocking_gates),
            "warning_gate_count": len(warning_gates),
            "expected_block_count": len(expected_blocks),
            "evidence_source_count": len(PATHS),
            "provider_call_count_by_report": 0,
            "world_mutation_count_by_report": 0,
            "runtime_mutation_count_by_report": 0,
        },
        "demo_claim": {
            "player_experience": "当前 reviewed fixture 与本地 API 已足以支撑一条 MVP 教学演示闭环。",
            "compiler_evidence": "证据包可展示 AI 编译对象、调度、地图预览、素材门禁和失败候选隔离。",
            "boundary": "本报告不声称地图美术、真实视频关键帧或实时 provider 调度已经完成。",
        },
        "gates": gates,
        "known_limitations": [
            {
                "limitation_id": "map_player_visual_quality",
                "severity": "medium",
                "summary": "当前玩家地图底图仍有共享底图和非节点专属 warning；程序化地图可演示，但不是最终美术目标。",
                "evidence_refs": [source_ref(PATHS["map_visual_quality"])],
            },
            {
                "limitation_id": "map_candidate_promotion",
                "severity": "medium",
                "summary": "多轮真实或受控地图候选仍未通过坐标对齐和视觉复核，已被隔离为负样本证据。",
                "evidence_refs": [
                    source_ref(PATHS["map_candidate_overlay_visual_review"]),
                    source_ref(PATHS["controlled_map_text_fallback_review"]),
                ],
            },
            {
                "limitation_id": "video_keyframes",
                "severity": "low",
                "summary": "当前循环动画为 deterministic frame sequence；video provider 只有离线 dry boundary 与 handoff 模板，真实图生视频关键帧尚未接入 atlas 晋升流程。",
                "evidence_refs": [
                    source_ref(PATHS["runtime_loop_continuity"]),
                    source_ref(PATHS["provider_video_runner_receipt"]),
                    source_ref(PATHS["provider_video_runner_envelope"]),
                    source_ref(PATHS["provider_video_adapter_task_pack"]),
                    source_ref(PATHS["provider_video_handoff_task_pack"]),
                ],
            },
            {
                "limitation_id": "map_runtime_v02_activation",
                "severity": "low",
                "summary": "v0.2 地图强语义已形成候选且前端消费已预接入，但默认 runtime 仍保持 v0.1；正式激活仍需开发者授权、后端选择器和复跑证据。",
                "evidence_refs": [
                    source_ref(PATHS["map_runtime_activation_gate"]),
                    source_ref(PATHS["map_runtime_v02_activation_contract_plan"]),
                ],
            },
            {
                "limitation_id": "live_provider_runtime",
                "severity": "low",
                "summary": "MVP 玩家主路径仍使用 reviewed fixture 与本地 mock API；实时 provider 调度应继续走 review / staging / promotion 门禁。",
                "evidence_refs": [
                    source_ref(PATHS["mvp_primary_api_flow"]),
                    source_ref(PATHS["core_artifact_alignment"]),
                ],
            },
        ],
        "recommended_next_actions": [
            "补 reference-image / paintover / 分层程序化地图路线，而不是继续纯文本整图生成。",
            "把真实图生视频关键帧接入 LoopContinuityReport、atlas contract 和浏览器视觉烟测。",
            "把浏览器全链路截图报告纳入演示归档流程，保留每次录屏前的可复跑证据目录。",
            "将实时 provider 调度继续保持在 staging / promotion / activation gate 后面，不直接污染玩家 runtime。",
        ],
        "safety_summary": {
            "reads_env_file": False,
            "provider_call_count": 0,
            "stores_prompt_body": False,
            "stores_provider_body": False,
            "stores_sensitive_value": False,
            "world_mutation_count_by_report": 0,
            "runtime_mutation_count_by_report": 0,
            "runtime_activation_allowed": False,
        },
        "source_files": [source_ref(path) for path in PATHS.values()],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output report path.",
    )
    parser.add_argument(
        "--generated-at",
        default=now_iso(),
        help="ISO timestamp to store in the report.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args.generated_at)
    write_json(args.output, report)
    print(
        "MVP demo readiness report written: "
        f"{args.output} ({report['overall_status']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
