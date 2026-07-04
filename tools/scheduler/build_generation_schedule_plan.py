#!/usr/bin/env python3
"""Build the deterministic MVP GenerationSchedulePlan v0.1.

The schedule plan is a review-only control-plane artifact. It does not read
.env, call providers, or start background jobs.
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

from validation_common import load_json  # noqa: E402
from validate_generation_schedule_plan import validate_generation_schedule_plan  # noqa: E402


SCHEMA_VERSION = "generation_schedule_plan.v0.1"
DEFAULT_OUTPUT = ROOT / "examples/review_packs/mvp_generation_schedule_plan.v0.1.json"

SOURCE_REFS = {
    "architecture_index": "docs/CURRENT_ARCHITECTURE_INDEX.md",
    "ai_compilation_system": "docs/AI_COMPILATION_SYSTEM_V0_1.md",
    "compilable_object_plan": "examples/review_packs/mvp_next_stage_compilable_object_plan.v0.1.json",
    "final_run_state": "examples/run_world_states/demo_after_stage_07_split_tide.run_world_state.json",
    "frontend_mock_pack": "examples/frontend_mock/frontend_mock_pack.v0.1.json",
    "runtime_art_manifest": "game_data/media/frontend_runtime_mock/frontend_runtime_art_media_manifest.v0.1.json",
    "runtime_art_atlas_manifest": "game_data/media/frontend_runtime_mock/frontend_runtime_art_atlas_manifest.v0.1.json",
    "runtime_sprite_repair_plan": "examples/review_packs/frontend_runtime_sprite_cutout_repair_plan.v0.1.json",
    "runtime_sprite_regeneration_promotion_report": "examples/review_packs/frontend_runtime_sprite_regeneration_promotion_report.v0.1.json",
    "map_runtime_packages": [
        "examples/map_runtime_packages/mvp_first_battle.map_runtime_package.json",
        "examples/map_runtime_packages/mvp_old_signal_tower_pressure.map_runtime_package.json",
        "examples/map_runtime_packages/mvp_wick_store_pressure.map_runtime_package.json",
    ],
    "map_compile_packages": [
        "examples/map_compile_packages/mvp_first_battle.map_compile_package.json",
        "examples/map_compile_packages/mvp_old_signal_tower_pressure.map_compile_package.json",
        "examples/map_compile_packages/mvp_wick_store_pressure.map_compile_package.json",
    ],
}


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def trigger(mode: str, description: str) -> dict[str, str]:
    return {"mode": mode, "description": description}


def cache(cache_key: str, reuse: str, invalidation_refs: list[str]) -> dict[str, Any]:
    return {
        "cache_key": cache_key,
        "reuse": reuse,
        "invalidation_refs": sorted(invalidation_refs),
    }


def provider(mode: str, max_attempts: int, profile: str) -> dict[str, Any]:
    return {"mode": mode, "max_attempts": max_attempts, "profile": profile}


def commit(
    world_commit: str,
    runtime_activation: str,
    revalidate_before_activation: bool,
) -> dict[str, Any]:
    return {
        "world_commit": world_commit,
        "runtime_activation": runtime_activation,
        "revalidate_before_activation": revalidate_before_activation,
    }


def item(
    *,
    schedule_item_id: str,
    compile_request_id: str,
    object_ref: str,
    object_kind: str,
    purpose: str,
    latency_class: str,
    priority: int,
    status: str,
    trigger_mode: str,
    trigger_description: str,
    dependencies: list[str],
    cache_key: str,
    cache_reuse: str,
    invalidation_refs: list[str],
    provider_mode: str,
    provider_attempts: int,
    provider_profile: str,
    validation_gates: list[str],
    fallback_ref: str,
    world_commit: str,
    runtime_activation: str,
    revalidate_before_activation: bool,
    player_visible: bool,
) -> dict[str, Any]:
    return {
        "schedule_item_id": schedule_item_id,
        "compile_request_id": compile_request_id,
        "object_ref": object_ref,
        "object_kind": object_kind,
        "purpose": purpose,
        "latency_class": latency_class,
        "priority": priority,
        "status": status,
        "trigger": trigger(trigger_mode, trigger_description),
        "dependencies": sorted(dependencies),
        "cache_policy": cache(cache_key, cache_reuse, invalidation_refs),
        "provider_policy": provider(provider_mode, provider_attempts, provider_profile),
        "validation_gates": sorted(validation_gates),
        "fallback_ref": fallback_ref,
        "commit_policy": commit(
            world_commit,
            runtime_activation,
            revalidate_before_activation,
        ),
        "player_visible": player_visible,
    }


def build_items() -> list[dict[str, Any]]:
    return [
        item(
            schedule_item_id="sched_session_frontend_mock_bootstrap",
            compile_request_id="compile_session_frontend_mock_bootstrap",
            object_ref="frontend_mock_pack:mvp",
            object_kind="frontend_mock_pack",
            purpose="让新档案、世界实例、大地图、首战和结算主链路在会话开始时立即可用。",
            latency_class="sync_blocking",
            priority=100,
            status="ready",
            trigger_mode="session_start",
            trigger_description="会话创建后立即加载 reviewed fixture 主链路。",
            dependencies=[],
            cache_key="frontend_mock_pack:mvp:v0.1",
            cache_reuse="always_static",
            invalidation_refs=["examples/frontend_mock/frontend_mock_pack.v0.1.json"],
            provider_mode="no_live_provider",
            provider_attempts=0,
            provider_profile="offline_fixture",
            validation_gates=["validate_frontend_mock_pack.py"],
            fallback_ref="examples/frontend_mock/frontend_mock_pack.v0.1.json",
            world_commit="none",
            runtime_activation="already_active",
            revalidate_before_activation=True,
            player_visible=True,
        ),
        item(
            schedule_item_id="sched_first_battle_map_runtime_package",
            compile_request_id="compile_first_battle_map_runtime_package",
            object_ref="map_runtime_package:mvp_first_battle",
            object_kind="map_runtime_package",
            purpose="保证第一场战斗路线、塔位、目标、出生点和发布底图在进入战斗前已经锁定。",
            latency_class="sync_blocking",
            priority=100,
            status="ready",
            trigger_mode="node_visible",
            trigger_description="第一个战斗节点可见时读取已发布地图运行包。",
            dependencies=["sched_session_frontend_mock_bootstrap"],
            cache_key="map_runtime_package:mvp_first_battle:v0.1",
            cache_reuse="always_static",
            invalidation_refs=["examples/map_runtime_packages/mvp_first_battle.map_runtime_package.json"],
            provider_mode="no_live_provider",
            provider_attempts=0,
            provider_profile="offline_fixture",
            validation_gates=["validate_map_runtime_package.py", "validate_battle_visual_contract.py"],
            fallback_ref="examples/map_runtime_packages/mvp_first_battle.map_runtime_package.json",
            world_commit="none",
            runtime_activation="already_active",
            revalidate_before_activation=True,
            player_visible=True,
        ),
        item(
            schedule_item_id="sched_runtime_art_atlas_ready",
            compile_request_id="compile_runtime_art_atlas_ready",
            object_ref="media_atlas:frontend_runtime_art_atlas_v0_1",
            object_kind="media_atlas_manifest",
            purpose="保证战斗敌人、目标物、防御件、NPC 头像、地图 token 和特效入口可被前端读取。",
            latency_class="sync_blocking",
            priority=98,
            status="ready",
            trigger_mode="battle_started",
            trigger_description="战斗场景启动前读取 published runtime art manifest 与 atlas。",
            dependencies=["sched_first_battle_map_runtime_package"],
            cache_key="media_atlas:frontend_runtime_art_atlas_v0_1",
            cache_reuse="reuse_if_inputs_match",
            invalidation_refs=[
                "game_data/media/frontend_runtime_mock/frontend_runtime_art_media_manifest.v0.1.json",
                "game_data/media/frontend_runtime_mock/frontend_runtime_art_atlas_manifest.v0.1.json",
            ],
            provider_mode="no_live_provider",
            provider_attempts=0,
            provider_profile="published_runtime_media",
            validation_gates=[
                "validate_frontend_runtime_art_pack.py",
                "validate_media_atlas_manifest.py",
                "validate_multiframe_atlas_contract.py",
                "audit_sprite_cutout_quality.py",
            ],
            fallback_ref="game_data/media/frontend_runtime_mock/frontend_runtime_art_media_manifest.v0.1.json",
            world_commit="none",
            runtime_activation="already_active",
            revalidate_before_activation=True,
            player_visible=True,
        ),
        item(
            schedule_item_id="sched_static_fallback_runtime_route",
            compile_request_id="compile_static_fallback_runtime_route",
            object_ref="runtime_package:mvp_demo",
            object_kind="fallback_static",
            purpose="当实时生成或后台生成失败时，维持首战、样品和结算可继续游玩。",
            latency_class="fallback_static",
            priority=96,
            status="fallback_ready",
            trigger_mode="battle_started",
            trigger_description="任何后台内容未按时完成时，继续使用已审运行包与确定性表现。",
            dependencies=[
                "sched_session_frontend_mock_bootstrap",
                "sched_runtime_art_atlas_ready",
            ],
            cache_key="fallback_static:mvp_demo_runtime",
            cache_reuse="always_static",
            invalidation_refs=["examples/runtime_packages/mvp_demo.runtime_package.json"],
            provider_mode="no_live_provider",
            provider_attempts=0,
            provider_profile="locked_static_fallback",
            validation_gates=["validate_runtime_package.py"],
            fallback_ref="examples/runtime_packages/mvp_demo.runtime_package.json",
            world_commit="none",
            runtime_activation="already_active",
            revalidate_before_activation=True,
            player_visible=True,
        ),
        item(
            schedule_item_id="sched_stage05_worldline_prefetch",
            compile_request_id="compile_stage05_worldline_prefetch",
            object_ref="compilable_object_plan:act_1_stage_05_old_signal_tower_pressure",
            object_kind="narrative_world_delta_prefetch",
            purpose="在玩家结算和返回大地图前准备下一阶段剧情、任务、随机事件和世界状态变化候选。",
            latency_class="background_prefetch",
            priority=82,
            status="review_only",
            trigger_mode="battle_settlement",
            trigger_description="首战结算后进入后台预取，只产出候选，启用前重新校验。",
            dependencies=["sched_static_fallback_runtime_route"],
            cache_key="prefetch:stage05_old_signal_tower:review_only",
            cache_reuse="reuse_if_inputs_match",
            invalidation_refs=[
                "examples/review_packs/mvp_next_stage_compilable_object_plan.v0.1.json",
                "examples/run_world_states/demo_after_stage_07_split_tide.run_world_state.json",
            ],
            provider_mode="allowed_after_review",
            provider_attempts=2,
            provider_profile="llm_world_delta_guarded",
            validation_gates=[
                "validate_compilable_object_plan.py",
                "validate_narrative_bundle.py",
                "validate_world_delta.py",
                "validate_world_delta_semantics.py",
                "validate_narrative_gameplay_contract.py",
            ],
            fallback_ref="examples/review_packs/mvp_next_stage_compilable_object_plan.v0.1.json",
            world_commit="world_delta_semantic_gate",
            runtime_activation="review_only",
            revalidate_before_activation=True,
            player_visible=False,
        ),
        item(
            schedule_item_id="sched_next_map_visual_prefetch",
            compile_request_id="compile_next_map_visual_prefetch",
            object_ref="map_compile_package:old_signal_tower_pressure",
            object_kind="map_visual_prefetch",
            purpose="为后续旧信号塔压力节点准备自然战斗底图候选，路线和塔位仍以地图运行包为准。",
            latency_class="background_prefetch",
            priority=76,
            status="planned",
            trigger_mode="node_visible",
            trigger_description="旧信号塔节点出现在大地图后，后台准备可审地图底图候选。",
            dependencies=["sched_stage05_worldline_prefetch"],
            cache_key="prefetch:map_visual:old_signal_tower_pressure",
            cache_reuse="reuse_if_inputs_match",
            invalidation_refs=[
                "examples/map_runtime_packages/mvp_old_signal_tower_pressure.map_runtime_package.json",
                "examples/map_compile_packages/mvp_old_signal_tower_pressure.map_compile_package.json",
            ],
            provider_mode="manual_only",
            provider_attempts=1,
            provider_profile="image_map_visual_after_review",
            validation_gates=[
                "validate_map_runtime_package.py",
                "validate_map_compile_package.py",
                "validate_battle_visual_contract.py",
            ],
            fallback_ref="examples/map_compile_packages/mvp_old_signal_tower_pressure.map_compile_package.json",
            world_commit="none",
            runtime_activation="activate_after_validation",
            revalidate_before_activation=True,
            player_visible=False,
        ),
        item(
            schedule_item_id="sched_video_frame_background_compile",
            compile_request_id="compile_video_frame_background_compile",
            object_ref="media_pipeline:image_to_video_sprite_frames",
            object_kind="video_frame_asset_pipeline",
            purpose="把已发布 sprite 种子升级为真实图生视频关键帧和实体 spritesheet，不阻塞当前战斗。",
            latency_class="background",
            priority=62,
            status="planned",
            trigger_mode="idle_window",
            trigger_description="玩家停留在非战斗页面或结算阅读时，后台处理可替换动画帧候选。",
            dependencies=["sched_runtime_art_atlas_ready"],
            cache_key="background:video_frame_asset_pipeline:v0.1",
            cache_reuse="reuse_if_inputs_match",
            invalidation_refs=[
                "docs/VIDEO_FRAME_ASSET_PIPELINE_V0_1.md",
                "game_data/media/frontend_runtime_mock/frontend_runtime_art_atlas_manifest.v0.1.json",
            ],
            provider_mode="manual_only",
            provider_attempts=1,
            provider_profile="image_to_video_after_review",
            validation_gates=[
                "LoopContinuityCheck",
                "validate_media_atlas_manifest.py",
                "validate_multiframe_atlas_contract.py",
                "audit_sprite_cutout_quality.py",
            ],
            fallback_ref="game_data/media/frontend_runtime_mock/frontend_runtime_art_atlas_manifest.v0.1.json",
            world_commit="none",
            runtime_activation="activate_after_validation",
            revalidate_before_activation=True,
            player_visible=False,
        ),
        item(
            schedule_item_id="sched_frontend_mock_sprite_repair_lazy",
            compile_request_id="compile_frontend_mock_sprite_repair_lazy",
            object_ref="review_pack:frontend_sprite_cutout_repair_plan",
            object_kind="sprite_repair_lazy",
            purpose="修复非 runtime 的前端 mock sprite 复核项；它不影响当前首战运行，低优先级懒加载处理。",
            latency_class="lazy",
            priority=38,
            status="planned",
            trigger_mode="idle_window",
            trigger_description="只有在 runtime 资产和下一节点预取都空闲时处理非阻塞 sprite 修复。",
            dependencies=["sched_static_fallback_runtime_route"],
            cache_key="lazy:frontend_mock_sprite_repair_plan:v0.1",
            cache_reuse="reuse_if_inputs_match",
            invalidation_refs=[
                "examples/review_packs/frontend_sprite_cutout_quality_report.v0.1.json",
                "examples/review_packs/frontend_sprite_cutout_repair_plan.v0.1.json",
            ],
            provider_mode="allowed_after_review",
            provider_attempts=1,
            provider_profile="image_repair_after_review",
            validation_gates=[
                "build_sprite_cutout_repair_plan.py",
                "build_sprite_repair_candidates.py",
                "audit_sprite_cutout_quality.py",
            ],
            fallback_ref="game_data/media/frontend_mock/frontend_media_manifest.v0.1.json",
            world_commit="none",
            runtime_activation="activate_after_validation",
            revalidate_before_activation=True,
            player_visible=False,
        ),
    ]


def summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
    latency_counts = Counter(str(item.get("latency_class") or "") for item in items)
    status_counts = Counter(str(item.get("status") or "") for item in items)
    return {
        "item_count": len(items),
        "latency_class_counts": dict(sorted(latency_counts.items())),
        "status_counts": dict(sorted(status_counts.items())),
        "sync_blocking_count": latency_counts.get("sync_blocking", 0),
        "background_prefetch_count": latency_counts.get("background_prefetch", 0),
        "background_count": latency_counts.get("background", 0),
        "lazy_count": latency_counts.get("lazy", 0),
        "fallback_static_count": latency_counts.get("fallback_static", 0),
        "live_provider_allowed_count": sum(
            1
            for item in items
            if as_obj(item.get("provider_policy")).get("mode") != "no_live_provider"
        ),
        "world_commit_gate_count": sum(
            1
            for item in items
            if as_obj(item.get("commit_policy")).get("world_commit")
            in {"world_delta_semantic_gate", "manual_review_required"}
        ),
        "fallback_covered_count": sum(1 for item in items if item.get("fallback_ref")),
    }


def _assert_required_sources_exist() -> None:
    refs: list[str] = []
    for value in SOURCE_REFS.values():
        if isinstance(value, list):
            refs.extend(value)
        elif isinstance(value, str):
            refs.append(value)
    missing = [ref for ref in refs if not (ROOT / ref).is_file()]
    if missing:
        raise FileNotFoundError(f"missing schedule source refs: {missing}")


def build_generation_schedule_plan() -> dict[str, Any]:
    _assert_required_sources_exist()
    frontend_pack = load_json(ROOT / SOURCE_REFS["frontend_mock_pack"])
    run_id = str(frontend_pack.get("run_id") or "demo_run_001")
    worldbook_id = str(frontend_pack.get("worldbook_id") or "long_night_lanterns")
    items = build_items()
    return {
        "schema_version": SCHEMA_VERSION,
        "plan_id": "mvp_generation_schedule_plan_v0_1",
        "visibility": "review_only",
        "worldbook_id": worldbook_id,
        "run_id": run_id,
        "created_at": "2026-07-02T00:00:00Z",
        "authority": {
            "control_plane_only": True,
            "content_truth_owner": "schemas_validators_and_reviewed_packages",
            "schedule_builder_reads_env": False,
            "schedule_builder_calls_provider": False,
            "runtime_world_mutation_allowed": False,
            "activation_requires_revalidation": True,
        },
        "source_refs": SOURCE_REFS,
        "budget_profile": {
            "max_sync_blocking_items": 4,
            "max_parallel_background_items": 2,
            "max_live_provider_items": 1,
            "default_timeout_seconds": 90,
            "retry_policy": {"max_attempts_per_item": 2, "backoff_seconds": 5},
            "degrade_on_budget_exhaustion": True,
        },
        "fallback_policy": {
            "player_safe_error_mode": "world_explanation_only",
            "technical_error_visibility": "internal_only",
            "default_fallback_refs": [
                "examples/frontend_mock/frontend_mock_pack.v0.1.json",
                "examples/runtime_packages/mvp_demo.runtime_package.json",
                "game_data/media/frontend_runtime_mock/frontend_runtime_art_atlas_manifest.v0.1.json",
            ],
        },
        "items": items,
        "summary": summarize(items),
        "validation_commands": [
            {
                "purpose": "validate schedule plan",
                "command": "python3 tools/scheduler/validate_generation_schedule_plan.py examples/review_packs/mvp_generation_schedule_plan.v0.1.json",
            },
            {
                "purpose": "export demo evidence with schedule summary",
                "command": "python3 tools/demo/export_evidence.py --output-dir /tmp/ai-td-generation-scheduler-evidence",
            },
        ],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the MVP GenerationSchedulePlan v0.1.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output plan JSON path.")
    parser.add_argument("--validate", action="store_true", help="Validate the generated plan before writing.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    plan = build_generation_schedule_plan()
    if args.validate:
        errors = validate_generation_schedule_plan(plan)
        if errors:
            print("INVALID generated GenerationSchedulePlan")
            for error in errors:
                print(f"- {error}")
            return 1
    output = Path(args.output)
    write_json(output, plan)
    print("OK built GenerationSchedulePlan")
    print(f"- output: {output}")
    print(f"- items: {plan['summary']['item_count']}")
    print(f"- latency: {plan['summary']['latency_class_counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
