#!/usr/bin/env python3
"""Export a redacted demo evidence bundle for the compiler MVP.

The exporter is intentionally offline and fixture-backed. It reads reviewed
runtime packages, manifests, and review reports from the current repository,
then writes a compact bundle for demos and judge Q&A.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

DEFAULT_OUTPUT_DIR = ROOT / "demo_evidence"
MAX_VALIDATION_OUTPUT_CHARS = 1400
MAX_SAMPLE_ITEMS = 12
MAP_RUNTIME_PACKAGE_DIR = ROOT / "examples/map_runtime_packages"
MAP_RUNTIME_PACKAGE_V02_DIR = ROOT / "examples/map_runtime_packages_v02"
MAP_COMPILE_PACKAGE_DIR = ROOT / "examples/map_compile_packages"
MAP_RENDER_PREVIEW_DIR = ROOT / "examples/map_render_previews"
MAP_RENDER_PREVIEW_V02_DIR = ROOT / "examples/map_render_previews_v02"
WORLD_DELTA_TRANSACTION_DIR = ROOT / "examples/world_delta_transactions"
STAGE_WORLD_DELTA_TRANSACTION_PATHS = [
    WORLD_DELTA_TRANSACTION_DIR
    / "stage_01_gray_lantern_first_defense.world_delta_transaction.json",
    WORLD_DELTA_TRANSACTION_DIR
    / "stage_02_dawn_review_supply_line.world_delta_transaction.json",
    WORLD_DELTA_TRANSACTION_DIR
    / "stage_03_northern_road_scouting.world_delta_transaction.json",
    WORLD_DELTA_TRANSACTION_DIR
    / "stage_04_wick_store_pressure_battle.world_delta_transaction.json",
    WORLD_DELTA_TRANSACTION_DIR
    / "stage_05_old_signal_tower_pressure.world_delta_transaction.json",
    WORLD_DELTA_TRANSACTION_DIR
    / "stage_06_signal_resonance_trial.world_delta_transaction.json",
    WORLD_DELTA_TRANSACTION_DIR
    / "stage_07_split_tide_containment.world_delta_transaction.json",
]


PATHS = {
    "readme": ROOT / "README.md",
    "architecture_index": ROOT / "docs/CURRENT_ARCHITECTURE_INDEX.md",
    "ai_compilation_doc": ROOT / "docs/AI_COMPILATION_SYSTEM_V0_1.md",
    "asset_graph_doc": ROOT / "docs/ASSET_GRAPH_COMPILER_V0_1.md",
    "generation_scheduler_doc": ROOT / "docs/GENERATION_SCHEDULER_V0_1.md",
    "frontend_mock_api_doc": ROOT / "docs/FRONTEND_MOCK_API_V0_1.md",
    "frontend_runtime_art_doc": ROOT / "docs/FRONTEND_RUNTIME_MOCK_ART_KIT_V0_1.md",
    "core_artifact_alignment_doc": ROOT
    / "docs/CORE_ARTIFACT_ALIGNMENT_REPORT_V0_1.md",
    "demo_vertical_slice_doc": ROOT / "docs/DEMO_VERTICAL_SLICE.md",
    "frontend_mock_pack": ROOT / "examples/frontend_mock/frontend_mock_pack.v0.1.json",
    "runtime_art_kit": ROOT
    / "examples/frontend_mock/frontend_battle_mock_art_kit.v0.1.json",
    "runtime_package": ROOT / "examples/runtime_packages/mvp_demo.runtime_package.json",
    "frontend_media_manifest": ROOT
    / "game_data/media/frontend_mock/frontend_media_manifest.v0.1.json",
    "frontend_media_atlas_manifest": ROOT
    / "game_data/media/frontend_mock/frontend_media_atlas_manifest.v0.1.json",
    "frontend_loop_continuity_report": ROOT
    / "examples/review_packs/frontend_loop_continuity_report.v0.1.json",
    "runtime_art_media_manifest": ROOT
    / "game_data/media/frontend_runtime_mock/frontend_runtime_art_media_manifest.v0.1.json",
    "runtime_art_atlas_manifest": ROOT
    / "game_data/media/frontend_runtime_mock/frontend_runtime_art_atlas_manifest.v0.1.json",
    "runtime_loop_continuity_report": ROOT
    / "examples/review_packs/frontend_runtime_loop_continuity_report.v0.1.json",
    "frontend_sprite_cutout_quality_report": ROOT
    / "examples/review_packs/frontend_sprite_cutout_quality_report.v0.1.json",
    "runtime_sprite_cutout_quality_report": ROOT
    / "examples/review_packs/frontend_runtime_sprite_cutout_quality_report.v0.1.json",
    "frontend_sprite_cutout_repair_plan": ROOT
    / "examples/review_packs/frontend_sprite_cutout_repair_plan.v0.1.json",
    "runtime_sprite_cutout_repair_plan": ROOT
    / "examples/review_packs/frontend_runtime_sprite_cutout_repair_plan.v0.1.json",
    "frontend_sprite_repair_candidates": ROOT
    / "examples/review_packs/frontend_sprite_repair_candidates.v0.1.json",
    "runtime_sprite_repair_candidates": ROOT
    / "examples/review_packs/frontend_runtime_sprite_repair_candidates.v0.1.json",
    "frontend_sprite_repair_candidate_quality_report": ROOT
    / "examples/review_packs/frontend_sprite_repair_candidate_quality_report.v0.1.json",
    "runtime_sprite_repair_candidate_quality_report": ROOT
    / "examples/review_packs/frontend_runtime_sprite_repair_candidate_quality_report.v0.1.json",
    "runtime_sprite_regeneration_candidates": ROOT
    / "examples/review_packs/frontend_runtime_sprite_regeneration_candidates.v0.1.json",
    "runtime_sprite_regeneration_candidate_quality_report": ROOT
    / "examples/review_packs/frontend_runtime_sprite_regeneration_candidate_quality_report.v0.1.json",
    "runtime_sprite_regeneration_promotion_report": ROOT
    / "examples/review_packs/frontend_runtime_sprite_regeneration_promotion_report.v0.1.json",
    "generation_schedule_plan": ROOT
    / "examples/review_packs/mvp_generation_schedule_plan.v0.1.json",
    "generation_schedule_run_report": ROOT
    / "examples/review_packs/mvp_generation_schedule_run_report.v0.1.json",
    "generation_executor_run_request": ROOT
    / "examples/generation_executor_requests/p1b_generation_executor_run_request.example.json",
    "provider_execution_authorization": ROOT
    / "examples/provider_authorizations/p1b_provider_execution_authorization.example.json",
    "provider_adapter_execution_receipt": ROOT
    / "examples/provider_adapter_executions/p1b_provider_adapter_execution_receipt.example.json",
    "provider_adapter_runner_executor_request": ROOT
    / "examples/provider_adapter_runs/p1b_provider_adapter_runner.executor_request.json",
    "provider_adapter_runner_receipt": ROOT
    / "examples/provider_adapter_runs/p1b_provider_adapter_runner.receipt.json",
    "provider_adapter_runner_envelope": ROOT
    / "examples/provider_adapter_runs/p1b_provider_adapter_runner.envelope.json",
    "provider_adapter_image_runner_executor_request": ROOT
    / "examples/provider_adapter_runs/p1b_provider_adapter_image_runner.executor_request.json",
    "provider_adapter_image_runner_authorization": ROOT
    / "examples/provider_authorizations/p1b_provider_execution_authorization_image.example.json",
    "provider_adapter_image_runner_receipt": ROOT
    / "examples/provider_adapter_runs/p1b_provider_adapter_image_runner.receipt.json",
    "provider_adapter_image_runner_envelope": ROOT
    / "examples/provider_adapter_runs/p1b_provider_adapter_image_runner.envelope.json",
    "provider_runner_handoff_export_task_pack": ROOT
    / "examples/worker_task_packs/p1b_provider_runner_handoff_export.v0.1.json",
    "provider_runner_handoff_roundtrip_task_pack": ROOT
    / "examples/worker_task_packs/p1b_provider_runner_handoff_roundtrip.v0.1.json",
    "scheduler_background_tick_task_pack": ROOT
    / "examples/worker_task_packs/p1b_scheduler_background_executor_tick.v0.1.json",
    "scheduler_background_handoff_tick_task_pack": ROOT
    / "examples/worker_task_packs/p1b_scheduler_background_handoff_tick.v0.1.json",
    "provider_runner_handoff_outbox_task_pack": ROOT
    / "examples/worker_task_packs/p1b_provider_runner_handoff_outbox.v0.1.json",
    "provider_runner_handoff_outbox_schema": ROOT
    / "shared/schemas/provider_adapter_runner_handoff_outbox.v0.1.schema.json",
    "provider_runner_handoff_outbox_validator": ROOT
    / "tools/dev/validate_provider_adapter_runner_handoff_outbox.py",
    "context_package_example": ROOT
    / "examples/review_packs/mvp_first_battle.context_package.json",
    "fact_entry_example": ROOT
    / "examples/review_packs/mvp_gray_lantern.fact_entry.json",
    "cgop_example": ROOT
    / "examples/review_packs/mvp_light_snare.compiled_game_object_package.json",
    "world_delta_transaction_example": ROOT
    / "examples/world_delta_transactions/first_battle_result.world_delta_transaction.json",
    "map_visual_manifest": ROOT
    / "game_data/media/map_visual_reference/map_visual_reference_manifest.v0.1.json",
    "map_visual_quality_report": ROOT
    / "examples/review_packs/map_visual_quality_report.v0.1.json",
    "map_visual_promotion_gate_report": ROOT
    / "examples/review_packs/map_visual_promotion_gate_report.v0.1.json",
    "map_runtime_promotion_readiness_report": ROOT
    / "examples/review_packs/map_runtime_promotion_readiness_report.v0.1.json",
    "map_runtime_activation_gate_report": ROOT
    / "examples/review_packs/map_runtime_activation_gate_report.v0.1.json",
    "map_path_geometry_report": ROOT
    / "examples/review_packs/map_path_geometry_report.v0.1.json",
    "map_component_media_manifest": ROOT
    / "game_data/media/map_components/map_component_media_manifest.v0.1.json",
    "map_component_media_manifest_v02": ROOT
    / "game_data/media/map_components/map_component_media_manifest.v0.2.json",
    "map_style_component_binding_report": ROOT
    / "examples/review_packs/map_style_component_binding_report.v0.1.json",
    "map_component_generation_request_pack": ROOT
    / "examples/review_packs/map_component_generation_request_pack.v0.1.json",
    "map_component_artifact_staging_manifest": ROOT
    / "examples/review_packs/map_component_artifact_staging_manifest.v0.1.json",
    "map_component_candidate_review_report": ROOT
    / "examples/review_packs/map_component_candidate_review_report.v0.1.json",
    "map_component_visual_quality_report": ROOT
    / "examples/review_packs/map_component_visual_quality_report.v0.1.json",
    "map_component_promotion_gate_report": ROOT
    / "examples/review_packs/map_component_promotion_gate_report.v0.1.json",
    "map_component_manifest_patch_plan": ROOT
    / "examples/review_packs/map_component_manifest_patch_plan.v0.1.json",
    "map_component_manifest_apply_report": ROOT
    / "examples/review_packs/map_component_manifest_apply_report.v0.1.json",
    "node_map_candidate_review": ROOT
    / "examples/review_packs/node_map_painted_candidate_review.v0.2.json",
    "map_candidate_alignment_review": ROOT
    / "examples/review_packs/map_candidate_alignment_review.v0.1.json",
    "map_candidate_overlay_review": ROOT
    / "examples/review_packs/map_candidate_overlay_review.v0.1.json",
    "map_candidate_overlay_visual_review": ROOT
    / "examples/review_packs/map_candidate_overlay_visual_review.v0.1.json",
    "map_layout_reconciliation_plan": ROOT
    / "examples/review_packs/map_layout_reconciliation_plan.v0.1.json",
    "runtime_map_patch_candidates": ROOT
    / "examples/review_packs/runtime_map_patch_candidates.v0.1.json",
    "map_patch_overlay_review": ROOT
    / "examples/review_packs/map_patch_overlay_review.v0.1.json",
    "topology_constrained_map_prompt_pack": ROOT
    / "examples/review_packs/topology_constrained_map_prompt_pack.v0.1.json",
    "topology_constrained_map_candidate_review": ROOT
    / "examples/review_packs/topology_constrained_map_candidate_review.v0.1.json",
    "topology_constrained_map_alignment_review": ROOT
    / "examples/review_packs/topology_constrained_map_alignment_review.v0.1.json",
    "topology_constrained_map_overlay_review": ROOT
    / "examples/review_packs/topology_constrained_map_overlay_review.v0.1.json",
    "topology_constrained_map_overlay_visual_review": ROOT
    / "examples/review_packs/topology_constrained_map_overlay_visual_review.v0.1.json",
    "map_topology_control_sketch_pack": ROOT
    / "examples/review_packs/map_topology_control_sketch_pack.v0.1.json",
    "map_controlled_regeneration_request_pack": ROOT
    / "examples/review_packs/map_controlled_regeneration_request_pack.v0.1.json",
    "controlled_map_candidate_generation_run": ROOT
    / "examples/review_packs/controlled_map_candidate_generation_run.v0.1.json",
    "controlled_map_candidate_review": ROOT
    / "examples/review_packs/controlled_map_candidate_review.v0.1.json",
    "controlled_map_text_fallback_generation_run": ROOT
    / "examples/review_packs/controlled_map_text_fallback_generation_run.v0.1.json",
    "controlled_map_text_fallback_candidate_review": ROOT
    / "examples/review_packs/controlled_map_text_fallback_candidate_review.v0.1.json",
    "handoff_audit": ROOT / "examples/review_packs/mvp_handoff_audit_report.v0.1.json",
    "compiler_dossier": ROOT
    / "examples/review_packs/mvp_compiler_review_dossier.v0.1.json",
    "multistage_content_pack": ROOT
    / "examples/review_packs/mvp_multistage_content_pack.v0.1.json",
    "provider_artifact_staging_manifest": ROOT
    / "examples/provider_artifact_staging/p1b_provider_artifact_staging.example.json",
    "provider_artifact_staging_source_envelope": ROOT
    / "examples/provider_artifact_staging/p1b_provider_artifact_staging.source_envelope.json",
    "provider_artifact_staging_candidate_summary": ROOT
    / "examples/provider_artifact_staging/artifacts/p1b_stage05_map_visual_candidate.summary.json",
    "provider_artifact_promotion_report": ROOT
    / "examples/provider_artifact_staging/p1b_provider_artifact_promotion_report.example.json",
    "provider_artifact_promotion_negative_fixture": ROOT
    / "examples/provider_artifact_staging/p1b_provider_artifact_promotion_report.invalid_blocked_validation_without_failed_gate.json",
    "provider_image_artifact_staging_manifest": ROOT
    / "examples/provider_artifact_staging/p1b_provider_image_artifact_staging.example.json",
    "provider_image_artifact_staging_source_envelope": ROOT
    / "examples/provider_artifact_staging/p1b_provider_image_artifact_staging.source_envelope.json",
    "provider_image_artifact_promotion_report": ROOT
    / "examples/provider_artifact_staging/p1b_provider_image_artifact_promotion_report.example.json",
    "core_artifact_alignment_report": ROOT
    / "examples/review_packs/core_artifact_alignment_report.v0.1.json",
    "mvp_primary_api_flow_smoke_report": ROOT
    / "examples/review_packs/mvp_primary_api_flow_smoke_report.v0.1.json",
    "map_v02_preview_api_smoke_report": ROOT
    / "examples/review_packs/map_v02_preview_api_smoke_report.v0.1.json",
    "mvp_demo_readiness_report": ROOT
    / "examples/review_packs/mvp_demo_readiness_report.v0.1.json",
}

STATIC_VALIDATION_COMMANDS = [
    {
        "name": "frontend_mock_pack",
        "command": [
            "python3",
            "tools/content_pipeline/validate_frontend_mock_pack.py",
            "examples/frontend_mock/frontend_mock_pack.v0.1.json",
        ],
    },
    {
        "name": "frontend_campaign_router_contract",
        "command": [
            "python3",
            "tools/frontend/validate_campaign_router_frontend_contract.py",
        ],
    },
    {
        "name": "multinode_battle_settlement",
        "command": [
            "python3",
            "tools/dev/validate_multinode_battle_settlement.py",
        ],
    },
    {
        "name": "frontend_media_manifest",
        "command": [
            "python3",
            "tools/media/validate_frontend_mock_media_pack.py",
            "game_data/media/frontend_mock/frontend_media_manifest.v0.1.json",
        ],
    },
    {
        "name": "frontend_runtime_art_pack",
        "command": ["python3", "tools/media/validate_frontend_runtime_art_pack.py"],
    },
    {
        "name": "frontend_media_atlas",
        "command": [
            "python3",
            "tools/media/validate_media_atlas_manifest.py",
            "game_data/media/frontend_mock/frontend_media_atlas_manifest.v0.1.json",
        ],
    },
    {
        "name": "frontend_media_multiframe_atlas_contract",
        "command": [
            "python3",
            "tools/media/validate_multiframe_atlas_contract.py",
            "game_data/media/frontend_mock/frontend_media_atlas_manifest.v0.1.json",
        ],
    },
    {
        "name": "frontend_loop_continuity_report",
        "command": [
            "python3",
            "tools/media/validate_loop_continuity_report.py",
            "examples/review_packs/frontend_loop_continuity_report.v0.1.json",
        ],
    },
    {
        "name": "frontend_runtime_art_atlas",
        "command": [
            "python3",
            "tools/media/validate_media_atlas_manifest.py",
            "game_data/media/frontend_runtime_mock/frontend_runtime_art_atlas_manifest.v0.1.json",
        ],
    },
    {
        "name": "frontend_runtime_art_multiframe_atlas_contract",
        "command": [
            "python3",
            "tools/media/validate_multiframe_atlas_contract.py",
            "game_data/media/frontend_runtime_mock/frontend_runtime_art_atlas_manifest.v0.1.json",
        ],
    },
    {
        "name": "frontend_runtime_loop_continuity_report",
        "command": [
            "python3",
            "tools/media/validate_loop_continuity_report.py",
            "examples/review_packs/frontend_runtime_loop_continuity_report.v0.1.json",
        ],
    },
    {
        "name": "frontend_sprite_cutout_quality",
        "command": [
            "python3",
            "tools/media/audit_sprite_cutout_quality.py",
            "game_data/media/frontend_mock/frontend_media_manifest.v0.1.json",
            "--output",
            "/tmp/ai_td_frontend_sprite_cutout_quality_report.json",
        ],
    },
    {
        "name": "frontend_runtime_sprite_cutout_quality",
        "command": [
            "python3",
            "tools/media/audit_sprite_cutout_quality.py",
            "game_data/media/frontend_runtime_mock/frontend_runtime_art_media_manifest.v0.1.json",
            "--output",
            "/tmp/ai_td_frontend_runtime_sprite_cutout_quality_report.json",
        ],
    },
    {
        "name": "frontend_sprite_cutout_repair_plan",
        "command": [
            "python3",
            "tools/media/build_sprite_cutout_repair_plan.py",
            "examples/review_packs/frontend_sprite_cutout_quality_report.v0.1.json",
            "--output",
            "/tmp/ai_td_frontend_sprite_cutout_repair_plan.json",
        ],
    },
    {
        "name": "frontend_runtime_sprite_cutout_repair_plan",
        "command": [
            "python3",
            "tools/media/build_sprite_cutout_repair_plan.py",
            "examples/review_packs/frontend_runtime_sprite_cutout_quality_report.v0.1.json",
            "--output",
            "/tmp/ai_td_frontend_runtime_sprite_cutout_repair_plan.json",
        ],
    },
    {
        "name": "frontend_sprite_repair_candidates",
        "command": [
            "python3",
            "tools/media/build_sprite_repair_candidates.py",
            "examples/review_packs/frontend_sprite_cutout_repair_plan.v0.1.json",
            "--output-manifest",
            "/tmp/ai_td_frontend_sprite_repair_candidates.json",
            "--output-dir",
            "/tmp/ai_td_frontend_sprite_repair_candidates",
            "--candidate-pack-id",
            "frontend_sprite_repair_candidates_validation",
        ],
    },
    {
        "name": "frontend_runtime_sprite_repair_candidates",
        "command": [
            "python3",
            "tools/media/build_sprite_repair_candidates.py",
            "examples/review_packs/frontend_runtime_sprite_cutout_repair_plan.v0.1.json",
            "--output-manifest",
            "/tmp/ai_td_frontend_runtime_sprite_repair_candidates.json",
            "--output-dir",
            "/tmp/ai_td_frontend_runtime_sprite_repair_candidates",
            "--candidate-pack-id",
            "frontend_runtime_sprite_repair_candidates_validation",
        ],
    },
    {
        "name": "frontend_sprite_repair_candidate_quality",
        "command": [
            "python3",
            "tools/media/audit_sprite_cutout_quality.py",
            "examples/review_packs/frontend_sprite_repair_candidates.v0.1.json",
            "--output",
            "/tmp/ai_td_frontend_sprite_repair_candidate_quality.json",
        ],
    },
    {
        "name": "frontend_runtime_sprite_repair_candidate_quality",
        "command": [
            "python3",
            "tools/media/audit_sprite_cutout_quality.py",
            "examples/review_packs/frontend_runtime_sprite_repair_candidates.v0.1.json",
            "--output",
            "/tmp/ai_td_frontend_runtime_sprite_repair_candidate_quality.json",
        ],
    },
    {
        "name": "frontend_runtime_sprite_regeneration_candidates_dry_run",
        "command": [
            "python3",
            "tools/media/generate_sprite_regeneration_candidates.py",
            "--repair-plan",
            "examples/review_packs/frontend_runtime_sprite_cutout_repair_plan.v0.1.json",
            "--output-manifest",
            "/tmp/ai_td_frontend_runtime_sprite_regeneration_candidates_dry_run.json",
            "--raw-output-dir",
            "/tmp/ai_td_frontend_runtime_sprite_regeneration_raw",
            "--processed-output-dir",
            "/tmp/ai_td_frontend_runtime_sprite_regeneration_processed",
            "--candidate-pack-id",
            "frontend_runtime_sprite_regeneration_candidates_validation",
            "--priority",
            "P1",
        ],
    },
    {
        "name": "frontend_runtime_sprite_regeneration_candidate_quality",
        "command": [
            "python3",
            "tools/media/audit_sprite_cutout_quality.py",
            "examples/review_packs/frontend_runtime_sprite_regeneration_candidates.v0.1.json",
            "--output",
            "/tmp/ai_td_frontend_runtime_sprite_regeneration_candidate_quality.json",
        ],
    },
    {
        "name": "frontend_runtime_sprite_regeneration_promotion_dry_run",
        "command": [
            "python3",
            "tools/media/promote_sprite_regeneration_candidates.py",
            "--candidate-manifest",
            "examples/review_packs/frontend_runtime_sprite_regeneration_candidates.v0.1.json",
            "--candidate-quality-report",
            "examples/review_packs/frontend_runtime_sprite_regeneration_candidate_quality_report.v0.1.json",
            "--runtime-manifest",
            "game_data/media/frontend_runtime_mock/frontend_runtime_art_media_manifest.v0.1.json",
            "--output-manifest",
            "/tmp/ai_td_frontend_runtime_art_media_manifest_promoted_dry_run.json",
            "--promotion-report",
            "/tmp/ai_td_frontend_runtime_sprite_regeneration_promotion_dry_run.json",
            "--asset-id",
            "objective_signal_beacon",
            "--asset-id",
            "defense_basic_lantern_barricade",
            "--asset-id",
            "objective_station_core",
        ],
    },
    {
        "name": "map_visual_quality_audit",
        "command": [
            "python3",
            "tools/media/audit_map_visual_quality.py",
            "--output",
            "/tmp/ai_td_map_visual_quality_report.json",
        ],
    },
    {
        "name": "map_visual_promotion_gate",
        "command": [
            "python3",
            "tools/media/build_map_visual_promotion_gate_report.py",
            "--output",
            "/tmp/ai_td_map_visual_promotion_gate_report.json",
        ],
    },
    {
        "name": "map_runtime_promotion_readiness",
        "command": [
            "python3",
            "tools/media/validate_map_runtime_promotion_readiness_report.py",
            "examples/review_packs/map_runtime_promotion_readiness_report.v0.1.json",
        ],
    },
    {
        "name": "map_runtime_activation_gate",
        "command": [
            "python3",
            "tools/media/validate_map_runtime_activation_gate_report.py",
            "examples/review_packs/map_runtime_activation_gate_report.v0.1.json",
        ],
    },
    {
        "name": "map_path_geometry_report",
        "command": [
            "python3",
            "tools/asset_graph/validate_map_path_geometry_report.py",
            "examples/review_packs/map_path_geometry_report.v0.1.json",
        ],
    },
    {
        "name": "map_component_media_manifest",
        "command": [
            "python3",
            "tools/media/validate_map_component_media_pack.py",
            "game_data/media/map_components/map_component_media_manifest.v0.1.json",
        ],
    },
    {
        "name": "map_component_media_manifest_v02_preview",
        "command": [
            "python3",
            "tools/media/validate_map_component_media_pack_v02.py",
            "game_data/media/map_components/map_component_media_manifest.v0.2.json",
        ],
    },
    {
        "name": "map_component_frontend_contract",
        "command": [
            "python3",
            "tools/frontend/validate_map_component_frontend_contract.py",
        ],
    },
    {
        "name": "map_style_component_binding_report",
        "command": [
            "python3",
            "tools/asset_graph/validate_map_style_component_binding_report.py",
            "examples/review_packs/map_style_component_binding_report.v0.1.json",
        ],
    },
    {
        "name": "map_component_generation_request_pack",
        "command": [
            "python3",
            "tools/media/validate_map_component_generation_request_pack.py",
            "examples/review_packs/map_component_generation_request_pack.v0.1.json",
        ],
    },
    {
        "name": "map_component_artifact_staging_manifest",
        "command": [
            "python3",
            "tools/media/validate_map_component_artifact_staging_manifest.py",
            "examples/review_packs/map_component_artifact_staging_manifest.v0.1.json",
        ],
    },
    {
        "name": "map_component_candidate_review_report",
        "command": [
            "python3",
            "tools/media/validate_map_component_candidate_review_report.py",
            "examples/review_packs/map_component_candidate_review_report.v0.1.json",
        ],
    },
    {
        "name": "map_component_visual_quality_report",
        "command": [
            "python3",
            "tools/media/validate_map_component_visual_quality_report.py",
            "examples/review_packs/map_component_visual_quality_report.v0.1.json",
        ],
    },
    {
        "name": "map_component_promotion_gate_report",
        "command": [
            "python3",
            "tools/media/validate_map_component_promotion_gate_report.py",
            "examples/review_packs/map_component_promotion_gate_report.v0.1.json",
        ],
    },
    {
        "name": "map_component_manifest_patch_plan",
        "command": [
            "python3",
            "tools/media/validate_map_component_manifest_patch_plan.py",
            "examples/review_packs/map_component_manifest_patch_plan.v0.1.json",
        ],
    },
    {
        "name": "map_component_manifest_apply_report",
        "command": [
            "python3",
            "tools/media/validate_map_component_manifest_apply_report.py",
            "examples/review_packs/map_component_manifest_apply_report.v0.1.json",
        ],
    },
    {
        "name": "node_map_candidate_review_pack",
        "command": [
            "python3",
            "tools/media/build_node_map_candidate_review_pack.py",
            "--candidate-dir",
            "game_data/media/map_visual_reference/node_candidates_v2",
            "--review-profile",
            "clean_scene_v2",
            "--output",
            "/tmp/ai_td_node_map_painted_candidate_review.json",
        ],
    },
    {
        "name": "map_candidate_alignment_review",
        "command": [
            "python3",
            "tools/media/build_map_candidate_alignment_review.py",
            "--output",
            "/tmp/ai_td_map_candidate_alignment_review.json",
        ],
    },
    {
        "name": "map_candidate_overlay_review",
        "command": [
            "python3",
            "tools/media/build_map_candidate_overlay_review.py",
            "--output-dir",
            "/tmp/ai_td_map_candidate_overlay_artifacts",
            "--report",
            "/tmp/ai_td_map_candidate_overlay_review.json",
        ],
    },
    {
        "name": "map_candidate_overlay_visual_review",
        "command": [
            "python3",
            "tools/media/build_map_candidate_overlay_visual_review.py",
            "--output",
            "/tmp/ai_td_map_candidate_overlay_visual_review.json",
        ],
    },
    {
        "name": "map_layout_reconciliation_plan",
        "command": [
            "python3",
            "tools/media/build_map_layout_reconciliation_plan.py",
            "--output",
            "/tmp/ai_td_map_layout_reconciliation_plan.json",
        ],
    },
    {
        "name": "runtime_map_patch_candidates",
        "command": [
            "python3",
            "tools/media/build_runtime_map_patch_candidates.py",
            "--output",
            "/tmp/ai_td_runtime_map_patch_candidates.json",
        ],
    },
    {
        "name": "map_patch_overlay_review",
        "command": [
            "python3",
            "tools/media/build_map_patch_overlay_review.py",
            "--output-dir",
            "/tmp/ai_td_map_patch_overlay_artifacts",
            "--output",
            "/tmp/ai_td_map_patch_overlay_review.json",
        ],
    },
    {
        "name": "topology_constrained_map_prompt_pack",
        "command": [
            "python3",
            "tools/media/build_topology_constrained_map_prompt_pack.py",
            "--output",
            "/tmp/ai_td_topology_constrained_map_prompt_pack.json",
        ],
    },
    {
        "name": "topology_constrained_map_candidate_dry_run",
        "command": [
            "python3",
            "tools/media/generate_topology_constrained_map_candidates.py",
            "--output-dir",
            "/tmp/ai_td_topology_constrained_map_candidates_dry_run",
        ],
    },
    {
        "name": "topology_constrained_map_candidate_review",
        "command": [
            "python3",
            "tools/media/build_node_map_candidate_review_pack.py",
            "--candidate-dir",
            "game_data/media/map_visual_reference/node_candidates_topology_v1",
            "--review-profile",
            "topology_constrained_v1",
            "--output",
            "/tmp/ai_td_topology_constrained_map_candidate_review.json",
        ],
    },
    {
        "name": "topology_constrained_map_alignment_review",
        "command": [
            "python3",
            "tools/media/build_map_candidate_alignment_review.py",
            "--candidate-review",
            "examples/review_packs/topology_constrained_map_candidate_review.v0.1.json",
            "--output",
            "/tmp/ai_td_topology_constrained_map_alignment_review.json",
        ],
    },
    {
        "name": "topology_constrained_map_overlay_review",
        "command": [
            "python3",
            "tools/media/build_map_candidate_overlay_review.py",
            "--alignment-review",
            "examples/review_packs/topology_constrained_map_alignment_review.v0.1.json",
            "--output-dir",
            "/tmp/ai_td_topology_constrained_map_overlay_artifacts",
            "--report",
            "/tmp/ai_td_topology_constrained_map_overlay_review.json",
        ],
    },
    {
        "name": "topology_constrained_map_overlay_visual_review",
        "command": [
            "python3",
            "tools/media/build_map_candidate_overlay_visual_review.py",
            "--overlay-review",
            "examples/review_packs/topology_constrained_map_overlay_review.v0.1.json",
            "--review-profile",
            "topology_constrained_v1",
            "--output",
            "/tmp/ai_td_topology_constrained_map_overlay_visual_review.json",
        ],
    },
    {
        "name": "map_topology_control_sketch_pack",
        "command": [
            "python3",
            "tools/media/build_map_topology_control_sketch_pack.py",
            "--output-dir",
            "/tmp/ai_td_map_topology_control_sketches",
            "--output",
            "/tmp/ai_td_map_topology_control_sketch_pack.json",
        ],
    },
    {
        "name": "map_controlled_regeneration_request_pack",
        "command": [
            "python3",
            "tools/media/build_map_controlled_regeneration_request_pack.py",
            "--prompt-dir",
            "/tmp/ai_td_map_controlled_regeneration_requests",
            "--output",
            "/tmp/ai_td_map_controlled_regeneration_request_pack.json",
        ],
    },
    {
        "name": "controlled_map_candidate_generation_dry_run",
        "command": [
            "python3",
            "tools/media/generate_controlled_map_candidates.py",
            "--output-dir",
            "/tmp/ai_td_controlled_map_candidates",
            "--output",
            "/tmp/ai_td_controlled_map_candidate_generation_run.json",
        ],
    },
    {
        "name": "controlled_map_candidate_review",
        "command": [
            "python3",
            "tools/media/build_node_map_candidate_review_pack.py",
            "--candidate-dir",
            "game_data/media/map_visual_reference/node_candidates_controlled_v1",
            "--review-profile",
            "controlled_reference_handoff_v1",
            "--output",
            "/tmp/ai_td_controlled_map_candidate_review.json",
        ],
    },
    {
        "name": "controlled_map_text_fallback_candidate_review",
        "command": [
            "python3",
            "tools/media/build_node_map_candidate_review_pack.py",
            "--candidate-dir",
            "game_data/media/map_visual_reference/node_candidates_controlled_text_v1",
            "--review-profile",
            "controlled_text_fallback_v1",
            "--output",
            "/tmp/ai_td_controlled_map_text_fallback_candidate_review.json",
        ],
    },
    {
        "name": "generation_schedule_plan",
        "command": [
            "python3",
            "tools/scheduler/validate_generation_schedule_plan.py",
            "examples/review_packs/mvp_generation_schedule_plan.v0.1.json",
        ],
    },
    {
        "name": "generation_schedule_run_report",
        "command": [
            "python3",
            "tools/scheduler/validate_generation_schedule_run_report.py",
            "examples/review_packs/mvp_generation_schedule_run_report.v0.1.json",
        ],
    },
    {
        "name": "generation_executor_run_request",
        "command": [
            "python3",
            "tools/dev/validate_generation_executor_run_request.py",
            "examples/generation_executor_requests/p1b_generation_executor_run_request.example.json",
        ],
    },
    {
        "name": "provider_execution_authorization",
        "command": [
            "python3",
            "tools/dev/validate_provider_execution_authorization.py",
            "examples/provider_authorizations/p1b_provider_execution_authorization.example.json",
        ],
    },
    {
        "name": "provider_adapter_execution_receipt",
        "command": [
            "python3",
            "tools/dev/validate_provider_adapter_execution_receipt.py",
            "examples/provider_adapter_executions/p1b_provider_adapter_execution_receipt.example.json",
        ],
    },
    {
        "name": "provider_adapter_runner_dry_run",
        "command": [
            "python3",
            "tools/provider_adapter/run_provider_adapter.py",
            "--executor-request",
            "examples/provider_adapter_runs/p1b_provider_adapter_runner.executor_request.json",
            "--authorization",
            "examples/provider_authorizations/p1b_provider_execution_authorization.example.json",
            "--receipt-output",
            "/tmp/p1b_provider_adapter_runner.receipt.json",
            "--envelope-output",
            "/tmp/p1b_provider_adapter_runner.envelope.json",
            "--created-at",
            "2026-07-03T00:00:00Z",
        ],
    },
    {
        "name": "provider_adapter_runner_receipt",
        "command": [
            "python3",
            "tools/dev/validate_provider_adapter_execution_receipt.py",
            "examples/provider_adapter_runs/p1b_provider_adapter_runner.receipt.json",
        ],
    },
    {
        "name": "provider_adapter_runner_envelope",
        "command": [
            "python3",
            "tools/dev/validate_provider_output_envelope.py",
            "examples/provider_adapter_runs/p1b_provider_adapter_runner.envelope.json",
        ],
    },
    {
        "name": "provider_adapter_image_runner_request",
        "command": [
            "python3",
            "tools/dev/validate_generation_executor_run_request.py",
            "examples/provider_adapter_runs/p1b_provider_adapter_image_runner.executor_request.json",
        ],
    },
    {
        "name": "provider_adapter_image_runner_authorization",
        "command": [
            "python3",
            "tools/dev/validate_provider_execution_authorization.py",
            "examples/provider_authorizations/p1b_provider_execution_authorization_image.example.json",
        ],
    },
    {
        "name": "provider_adapter_image_runner_dry_run",
        "command": [
            "python3",
            "tools/provider_adapter/run_provider_adapter.py",
            "--executor-request",
            "examples/provider_adapter_runs/p1b_provider_adapter_image_runner.executor_request.json",
            "--authorization",
            "examples/provider_authorizations/p1b_provider_execution_authorization_image.example.json",
            "--receipt-output",
            "/tmp/p1b_provider_adapter_image_runner.receipt.json",
            "--envelope-output",
            "/tmp/p1b_provider_adapter_image_runner.envelope.json",
            "--created-at",
            "2026-07-03T00:00:00Z",
        ],
    },
    {
        "name": "provider_adapter_image_runner_receipt",
        "command": [
            "python3",
            "tools/dev/validate_provider_adapter_execution_receipt.py",
            "examples/provider_adapter_runs/p1b_provider_adapter_image_runner.receipt.json",
        ],
    },
    {
        "name": "provider_adapter_image_runner_envelope",
        "command": [
            "python3",
            "tools/dev/validate_provider_output_envelope.py",
            "examples/provider_adapter_runs/p1b_provider_adapter_image_runner.envelope.json",
        ],
    },
    {
        "name": "provider_artifact_staging_manifest",
        "command": [
            "python3",
            "tools/dev/validate_provider_artifact_staging_manifest.py",
            "examples/provider_artifact_staging/p1b_provider_artifact_staging.example.json",
        ],
    },
    {
        "name": "provider_artifact_promotion_report",
        "command": [
            "python3",
            "tools/dev/validate_provider_artifact_promotion_report.py",
            "examples/provider_artifact_staging/p1b_provider_artifact_promotion_report.example.json",
        ],
    },
    {
        "name": "provider_artifact_promotion_negative_fixture",
        "command": [
            "python3",
            "tools/dev/check_provider_artifact_promotion_report_negative_fixture.py",
            "examples/provider_artifact_staging/p1b_provider_artifact_promotion_report.invalid_blocked_validation_without_failed_gate.json",
            "--expected-error",
            "blocked_validation_failed requires at least one required gate failed",
        ],
    },
    {
        "name": "provider_image_artifact_staging_source_envelope",
        "command": [
            "python3",
            "tools/dev/validate_provider_output_envelope.py",
            "examples/provider_artifact_staging/p1b_provider_image_artifact_staging.source_envelope.json",
        ],
    },
    {
        "name": "provider_image_artifact_staging_manifest",
        "command": [
            "python3",
            "tools/dev/validate_provider_artifact_staging_manifest.py",
            "examples/provider_artifact_staging/p1b_provider_image_artifact_staging.example.json",
        ],
    },
    {
        "name": "provider_image_artifact_promotion_report",
        "command": [
            "python3",
            "tools/dev/validate_provider_artifact_promotion_report.py",
            "examples/provider_artifact_staging/p1b_provider_image_artifact_promotion_report.example.json",
        ],
    },
    {
        "name": "ai_compile_core_artifacts",
        "command": [
            "python3",
            "tools/content_pipeline/validate_ai_compile_core_artifacts.py",
            "examples/review_packs/mvp_first_battle.context_package.json",
            "examples/review_packs/mvp_gray_lantern.fact_entry.json",
            "examples/review_packs/mvp_light_snare.compiled_game_object_package.json",
        ],
    },
    {
        "name": "core_artifact_alignment_report",
        "command": [
            "python3",
            "tools/content_pipeline/validate_core_artifact_alignment_report.py",
            "examples/review_packs/core_artifact_alignment_report.v0.1.json",
        ],
    },
    {
        "name": "world_delta_transaction",
        "command": [
            "python3",
            "tools/world_state/validate_world_delta_transaction.py",
            "examples/world_delta_transactions/first_battle_result.world_delta_transaction.json",
        ],
    },
    {
        "name": "world_delta_transaction_chain",
        "command": [
            "python3",
            "tools/world_state/validate_world_delta_transaction.py",
            *[
                str(path.relative_to(ROOT))
                for path in STAGE_WORLD_DELTA_TRANSACTION_PATHS
            ],
        ],
    },
    {
        "name": "runtime_package_first_battle",
        "command": [
            "python3",
            "tools/asset_graph/validate_runtime_package.py",
            "examples/runtime_packages/mvp_demo.runtime_package.json",
        ],
    },
    {
        "name": "mvp_demo_readiness_report",
        "command": [
            "python3",
            "tools/demo/build_mvp_demo_readiness_report.py",
            "--output",
            "/tmp/ai_td_mvp_demo_readiness_report.json",
            "--generated-at",
            "2026-07-04T00:00:00+00:00",
        ],
    },
]

REVIEWED_WORKFLOW_FILES = [
    ROOT / "examples/workflows/mvp_mock_asset_compile.workflow.json",
    ROOT / "examples/workflows/mvp_defense_asset_compile.workflow.json",
    ROOT / "examples/workflows/mvp_player_intent_to_asset_plan.workflow.json",
    ROOT / "examples/workflows/mvp_player_intent_to_asset_plan_deterministic.workflow.json",
]

FORBIDDEN_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "secret",
    "password",
    "auth_token",
    "access_token",
    "refresh_token",
    "raw_prompt",
    "full_prompt",
    "provider_response",
    "raw_response",
    "raw_json",
    "full_trace",
    "trace_paths",
    "unreviewed_content",
)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_ref(path: Path, role: str) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": rel(path),
            "role": role,
            "exists": False,
        }
    return {
        "path": rel(path),
        "role": role,
        "exists": True,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def external_file_ref(path: Path, role: str) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(path),
            "role": role,
            "exists": False,
        }
    return {
        "path": str(path),
        "role": role,
        "exists": True,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def shorten(value: str, limit: int = MAX_VALIDATION_OUTPUT_CHARS) -> str:
    normalized = value.replace(str(ROOT), "$REPO_ROOT").strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[-limit:]


def count_by(items: list[Any], key: str) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for item in items:
        if isinstance(item, dict) and item.get(key):
            counter[str(item[key])] += 1
    return dict(sorted(counter.items()))


def command_text(command: list[str]) -> str:
    return " ".join(command)


def map_runtime_package_paths() -> list[Path]:
    return sorted(MAP_RUNTIME_PACKAGE_DIR.glob("*.map_runtime_package.json"))


def map_runtime_package_v02_paths() -> list[Path]:
    return sorted(MAP_RUNTIME_PACKAGE_V02_DIR.glob("*.map_runtime_package_v02.json"))


def map_compile_package_paths() -> list[Path]:
    return sorted(MAP_COMPILE_PACKAGE_DIR.glob("*.map_compile_package.json"))


def map_render_preview_report_paths() -> list[Path]:
    return sorted(MAP_RENDER_PREVIEW_DIR.glob("*.procedural_map_preview_report.json"))


def map_render_preview_v02_report_paths() -> list[Path]:
    return sorted(MAP_RENDER_PREVIEW_V02_DIR.glob("*.procedural_map_preview_report.json"))


def validation_commands() -> list[dict[str, Any]]:
    commands = list(STATIC_VALIDATION_COMMANDS)
    for path in map_runtime_package_paths():
        commands.append(
            {
                "name": f"map_runtime_package_{path.stem.replace('.', '_')}",
                "command": [
                    "python3",
                    "tools/asset_graph/validate_map_runtime_package.py",
                    rel(path),
                ],
            }
        )
    for path in map_runtime_package_v02_paths():
        commands.append(
            {
                "name": f"map_runtime_package_v02_{path.stem.replace('.', '_')}",
                "command": [
                    "python3",
                    "tools/asset_graph/validate_map_runtime_package_v02.py",
                    rel(path),
                ],
            }
        )
    for path in map_compile_package_paths():
        commands.append(
            {
                "name": f"map_compile_package_{path.stem.replace('.', '_')}",
                "command": [
                    "python3",
                    "tools/asset_graph/validate_map_compile_package.py",
                    rel(path),
                ],
            }
        )
    for path in map_render_preview_report_paths():
        commands.append(
            {
                "name": f"procedural_map_preview_report_{path.stem.replace('.', '_')}",
                "command": [
                    "python3",
                    "tools/asset_graph/validate_procedural_map_preview_report.py",
                    rel(path),
                ],
            }
        )
    for path in map_render_preview_v02_report_paths():
        commands.append(
            {
                "name": f"procedural_map_preview_v02_report_{path.stem.replace('.', '_')}",
                "command": [
                    "python3",
                    "tools/asset_graph/validate_procedural_map_preview_report.py",
                    rel(path),
                ],
            }
        )
    return commands


def run_validation_commands() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for entry in validation_commands():
        command = entry["command"]
        try:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=45,
                check=False,
            )
            return_code = completed.returncode
            stdout = shorten(completed.stdout)
            stderr = shorten(completed.stderr)
        except subprocess.TimeoutExpired as exc:
            return_code = 124
            stdout = shorten(exc.stdout or "")
            stderr = shorten((exc.stderr or "") + "\n命令超时。")
        results.append(
            {
                "name": entry["name"],
                "command": command_text(command),
                "return_code": return_code,
                "status": "passed" if return_code == 0 else "failed",
                "stdout_tail": stdout,
                "stderr_tail": stderr,
            }
        )
    return results


def safe_asset_summary(asset: dict[str, Any]) -> dict[str, Any]:
    display = as_obj(asset.get("display"))
    promotion = as_obj(asset.get("promotion"))
    frontend_usage = as_obj(asset.get("frontend_usage"))
    visual_recipes = as_list(asset.get("visual_recipes"))
    media_refs = as_obj(asset.get("media_refs"))
    generated_roles = as_obj(media_refs.get("generated_roles"))
    return {
        "stable_internal_id": asset.get("stable_internal_id"),
        "display_name": display.get("name") or asset.get("display_name") or asset.get("name"),
        "asset_type": asset.get("asset_type"),
        "playable": promotion.get("playable"),
        "promotion_state": promotion.get("promotion_state"),
        "battle_toolbar": frontend_usage.get("battle_toolbar"),
        "visual_recipe_types": sorted(
            {
                str(recipe.get("type"))
                for recipe in visual_recipes
                if isinstance(recipe, dict) and recipe.get("type")
            }
        ),
        "published_media_roles": sorted(
            role for role, ref in generated_roles.items() if isinstance(ref, dict)
        ),
    }


def media_manifest_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    items = as_list(manifest.get("items"))
    sample_items = []
    for item in items[:MAX_SAMPLE_ITEMS]:
        if not isinstance(item, dict):
            continue
        sample_items.append(
            {
                "asset_id": item.get("asset_id"),
                "asset_name": item.get("asset_name"),
                "asset_type": item.get("asset_type"),
                "media_role": item.get("media_role"),
                "url": item.get("url"),
                "local_path": item.get("local_path"),
                "width": item.get("width"),
                "height": item.get("height"),
                "sha256": item.get("sha256"),
            }
        )
    summary = as_obj(manifest.get("summary"))
    return {
        "schema_version": manifest.get("schema_version"),
        "media_pack_id": manifest.get("media_pack_id"),
        "source_pack_id": manifest.get("source_pack_id"),
        "public_url_prefix": manifest.get("public_url_prefix"),
        "media_layer": manifest.get("media_layer"),
        "item_count": len(items),
        "asset_count": summary.get("asset_count")
        or len({item.get("asset_id") for item in items if isinstance(item, dict)}),
        "media_count": summary.get("media_count") or len(items),
        "roles": count_by(items, "media_role"),
        "asset_types": count_by(items, "asset_type"),
        "sample_items": sample_items,
    }


def map_component_media_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    items = [item for item in as_list(manifest.get("items")) if isinstance(item, dict)]
    summary = as_obj(manifest.get("summary"))
    return {
        "schema_version": manifest.get("schema_version"),
        "media_pack_id": manifest.get("media_pack_id"),
        "media_layer": manifest.get("media_layer"),
        "public_url_prefix": manifest.get("public_url_prefix"),
        "component_count": summary.get("component_count") or len(items),
        "material_component_count": summary.get("material_component_count"),
        "prefab_component_count": summary.get("prefab_component_count"),
        "style_pack_count": summary.get("style_pack_count"),
        "node_count": summary.get("node_count"),
        "component_roles": as_obj(summary.get("roles")),
        "media_kind_counts": as_obj(summary.get("media_kind_counts")),
        "single_image_count": summary.get("single_image_count"),
        "atlas_animation_count": summary.get("atlas_animation_count"),
        "media_roles": count_by(items, "media_role"),
        "usage_policy": as_list(manifest.get("usage_policy")),
        "sample_items": [
            {
                "stable_internal_id": item.get("stable_internal_id"),
                "style_pack_id": item.get("style_pack_id"),
                "node_id": item.get("node_id"),
                "source_owner_id": item.get("source_owner_id"),
                "component_role": item.get("component_role"),
                "media_kind": item.get("media_kind"),
                "url": item.get("url"),
                "local_path": item.get("local_path"),
                "sha256": item.get("sha256"),
            }
            for item in items[:MAX_SAMPLE_ITEMS]
        ],
    }


def atlas_manifest_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    items = as_list(manifest.get("items"))
    summary = as_obj(manifest.get("summary"))
    return {
        "schema_version": manifest.get("schema_version"),
        "atlas_id": manifest.get("atlas_id"),
        "atlas_mode": manifest.get("atlas_mode"),
        "source_media_pack_id": manifest.get("source_media_pack_id"),
        "animation_count": summary.get("animation_count") or len(items),
        "frame_count": summary.get("frame_count")
        or sum(len(as_list(as_obj(item).get("frames"))) for item in items),
        "asset_count": summary.get("asset_count"),
        "roles": as_obj(summary.get("roles")),
        "sample_animations": [
            {
                "animation_id": item.get("animation_id"),
                "asset_id": item.get("asset_id"),
                "media_role": item.get("media_role"),
                "frame_count": len(as_list(item.get("frames"))),
            }
            for item in items[:MAX_SAMPLE_ITEMS]
            if isinstance(item, dict)
        ],
    }


def sprite_cutout_quality_summary(report: dict[str, Any]) -> dict[str, Any]:
    items = [item for item in as_list(report.get("items")) if isinstance(item, dict)]
    review_items = [
        item
        for item in items
        if item.get("status") in {"needs_review", "failed"}
    ]
    return {
        "report_version": report.get("report_version"),
        "media_pack_id": report.get("media_pack_id"),
        "status": report.get("status"),
        "sprite_item_count": report.get("sprite_item_count"),
        "passed_count": report.get("passed_count"),
        "needs_review_count": report.get("needs_review_count"),
        "failed_count": report.get("failed_count"),
        "warning_counts": as_obj(report.get("warning_counts")),
        "issue_counts": as_obj(report.get("issue_counts")),
        "review_samples": [
            {
                "asset_id": item.get("asset_id"),
                "media_role": item.get("media_role"),
                "status": item.get("status"),
                "warnings": as_list(item.get("warnings")),
                "issues": as_list(item.get("issues")),
                "metrics": {
                    "visible_components": as_obj(item.get("metrics")).get("visible_component_count"),
                    "largest_component_ratio": as_obj(item.get("metrics")).get(
                        "largest_visible_component_ratio"
                    ),
                    "hole_ratio": as_obj(item.get("metrics")).get(
                        "interior_transparent_hole_ratio"
                    ),
                    "max_hole_ratio": as_obj(item.get("metrics")).get(
                        "max_interior_transparent_hole_ratio"
                    ),
                },
            }
            for item in review_items[:MAX_SAMPLE_ITEMS]
        ],
    }


def loop_continuity_summary(report: dict[str, Any]) -> dict[str, Any]:
    items = [item for item in as_list(report.get("items")) if isinstance(item, dict)]
    warning_items = [
        item
        for item in items
        if item.get("status") in {"passed_with_warnings", "failed"}
    ]
    return {
        "report_version": report.get("report_version"),
        "report_id": report.get("report_id"),
        "source_atlas_id": report.get("source_atlas_id"),
        "status": report.get("status"),
        "summary": as_obj(report.get("summary")),
        "warning_samples": [
            {
                "animation_id": item.get("animation_id"),
                "asset_id": item.get("asset_id"),
                "media_role": item.get("media_role"),
                "frame_source_kind": item.get("frame_source_kind"),
                "status": item.get("status"),
                "warnings": as_list(item.get("warnings")),
                "issues": as_list(item.get("issues")),
                "metrics": {
                    "bbox_delta_ratio": as_obj(item.get("metrics")).get("bbox_delta_ratio"),
                    "anchor_delta": as_obj(item.get("metrics")).get("anchor_delta"),
                    "alpha_coverage_delta": as_obj(item.get("metrics")).get(
                        "alpha_coverage_delta"
                    ),
                    "mean_rgba_delta": as_obj(item.get("metrics")).get("mean_rgba_delta"),
                },
            }
            for item in warning_items[:MAX_SAMPLE_ITEMS]
        ],
    }


def sprite_repair_plan_summary(plan: dict[str, Any]) -> dict[str, Any]:
    tasks = [task for task in as_list(plan.get("tasks")) if isinstance(task, dict)]
    return {
        "schema_version": plan.get("schema_version"),
        "plan_id": plan.get("plan_id"),
        "status": plan.get("status"),
        "source_report": plan.get("source_report"),
        "task_count": plan.get("task_count") if plan.get("task_count") is not None else len(tasks),
        "priority_counts": as_obj(plan.get("priority_counts")),
        "action_counts": as_obj(plan.get("action_counts")),
        "task_samples": [
            {
                "task_id": task.get("task_id"),
                "priority": task.get("priority"),
                "asset_id": task.get("asset_id"),
                "media_role": task.get("media_role"),
                "recommended_action": task.get("recommended_action"),
                "warnings": as_list(task.get("warnings")),
            }
            for task in tasks[:MAX_SAMPLE_ITEMS]
        ],
    }


def sprite_repair_candidate_summary(
    manifest: dict[str, Any],
    quality_report: dict[str, Any],
) -> dict[str, Any]:
    items = [item for item in as_list(manifest.get("items")) if isinstance(item, dict)]
    summary = as_obj(manifest.get("summary"))
    return {
        "schema_version": manifest.get("schema_version"),
        "candidate_pack_id": manifest.get("candidate_pack_id"),
        "media_layer": manifest.get("media_layer"),
        "generation_mode": manifest.get("generation_mode"),
        "promotion_policy": manifest.get("promotion_policy"),
        "candidate_count": summary.get("candidate_count", len(items)),
        "generated_count": summary.get("generated_count"),
        "planned_count": summary.get("planned_count"),
        "asset_count": summary.get("asset_count"),
        "profile": summary.get("profile"),
        "model": summary.get("model"),
        "priority_counts": as_obj(summary.get("priority_counts")),
        "strategy_counts": as_obj(summary.get("strategy_counts")),
        "quality_status": quality_report.get("status"),
        "quality_needs_review_count": quality_report.get("needs_review_count"),
        "quality_failed_count": quality_report.get("failed_count"),
        "promoted_to_runtime": False,
        "candidate_samples": [
            {
                "candidate_id": item.get("candidate_id"),
                "asset_id": item.get("asset_id"),
                "media_role": item.get("media_role"),
                "priority": item.get("priority"),
                "status": item.get("status"),
                "strategy": item.get("strategy"),
                "provider_profile": item.get("provider_profile"),
                "generation_source": item.get("generation_source"),
                "local_path": item.get("local_path"),
                "review_policy": item.get("review_policy"),
            }
            for item in items[:MAX_SAMPLE_ITEMS]
        ],
    }


def sprite_regeneration_promotion_summary(report: dict[str, Any]) -> dict[str, Any]:
    items = [item for item in as_list(report.get("items")) if isinstance(item, dict)]
    return {
        "schema_version": report.get("schema_version"),
        "report_id": report.get("report_id"),
        "mode": report.get("mode"),
        "source_candidate_pack_id": report.get("source_candidate_pack_id"),
        "source_quality_status": report.get("source_quality_status"),
        "selected_candidate_count": report.get("selected_candidate_count"),
        "promoted_count": report.get("promoted_count"),
        "would_promote_count": report.get("would_promote_count"),
        "runtime_effect": as_obj(report.get("runtime_effect")),
        "promoted_assets": [
            {
                "asset_id": item.get("asset_id"),
                "media_role": item.get("media_role"),
                "candidate_id": item.get("candidate_id"),
                "runtime_target_path": item.get("runtime_target_path"),
                "new_sha256": item.get("new_sha256"),
            }
            for item in items[:MAX_SAMPLE_ITEMS]
        ],
    }


def map_visual_quality_summary(report: dict[str, Any]) -> dict[str, Any]:
    summary = as_obj(report.get("summary"))
    return {
        "schema_version": report.get("schema_version"),
        "report_id": report.get("report_id"),
        "status": report.get("status"),
        "map_package_count": summary.get("map_package_count"),
        "node_ids": as_list(summary.get("node_ids")),
        "manifest_player_ready_layer_count": summary.get("manifest_player_ready_layer_count"),
        "shared_player_visual_layer_group_count": summary.get(
            "shared_player_visual_layer_group_count"
        ),
        "package_status_counts": as_obj(summary.get("package_status_counts")),
        "issue_counts": as_obj(summary.get("issue_counts")),
        "warning_counts": as_obj(summary.get("warning_counts")),
        "shared_player_visual_layer_groups": as_list(
            report.get("shared_player_visual_layer_groups")
        ),
    }


def map_visual_promotion_gate_summary(report: dict[str, Any]) -> dict[str, Any]:
    summary = as_obj(report.get("summary"))
    blocked = [
        candidate
        for candidate in as_list(report.get("blocked_candidates"))
        if isinstance(candidate, dict)
    ]
    violations = [
        violation
        for violation in as_list(report.get("violations"))
        if isinstance(violation, dict)
    ]
    return {
        "schema_version": report.get("schema_version"),
        "report_id": report.get("report_id"),
        "status": report.get("status"),
        "blocked_candidate_count": summary.get("blocked_candidate_count"),
        "published_player_layer_count": summary.get("published_player_layer_count"),
        "violation_count": summary.get("violation_count"),
        "blocking_reason_counts": as_obj(summary.get("blocking_reason_counts")),
        "next_required_gate": report.get("next_required_gate"),
        "blocked_candidate_samples": [
            {
                "candidate_path": candidate.get("candidate_path"),
                "node_ids": as_list(candidate.get("node_ids")),
                "blocking_reasons": as_list(candidate.get("blocking_reasons")),
            }
            for candidate in blocked[:MAX_SAMPLE_ITEMS]
        ],
        "violation_samples": violations[:MAX_SAMPLE_ITEMS],
    }


def map_runtime_promotion_readiness_summary(report: dict[str, Any]) -> dict[str, Any]:
    summary = as_obj(report.get("summary"))
    safety = as_obj(report.get("safety_summary"))
    nodes = [node for node in as_list(report.get("nodes")) if isinstance(node, dict)]
    return {
        "schema_version": report.get("schema_version"),
        "report_id": report.get("report_id"),
        "status": report.get("status"),
        "node_count": summary.get("node_count"),
        "promotion_candidate_count": summary.get("promotion_candidate_count"),
        "activation_allowed_count": summary.get("activation_allowed_count"),
        "status_counts": as_obj(summary.get("status_counts")),
        "gate_status_counts": as_obj(summary.get("gate_status_counts")),
        "blocker_counts": as_obj(summary.get("blocker_counts")),
        "v02_preview_count": summary.get("v02_preview_count"),
        "v02_render_plan_count": summary.get("v02_render_plan_count"),
        "semantic_report_count": summary.get("semantic_report_count"),
        "map_compile_package_count": summary.get("map_compile_package_count"),
        "visual_promotion_violation_count": summary.get(
            "visual_promotion_violation_count"
        ),
        "runtime_activation_allowed": as_obj(report.get("scope")).get(
            "runtime_activation_allowed"
        ),
        "required_next_gates": as_list(report.get("next_required_gates")),
        "safety": {
            "reads_env_file": safety.get("reads_env_file"),
            "provider_call_count_by_report": safety.get(
                "provider_call_count_by_report"
            ),
            "world_mutation_count_by_report": safety.get(
                "world_mutation_count_by_report"
            ),
            "runtime_mutation_count_by_report": safety.get(
                "runtime_mutation_count_by_report"
            ),
            "player_runtime_update_performed": safety.get(
                "player_runtime_update_performed"
            ),
        },
        "node_samples": [
            {
                "node_id": node.get("node_id"),
                "status": node.get("status"),
                "blocking_reasons": as_list(node.get("blocking_reasons")),
                "v02_package_id": as_obj(node.get("runtime_v02_preview")).get(
                    "package_id"
                ),
                "render_plan_id": as_obj(node.get("render_plan_v02")).get("plan_id"),
                "semantic_status": as_obj(
                    node.get("semantic_visual_consistency")
                ).get("status"),
                "published_player_layer_count": as_obj(
                    node.get("visual_promotion_gate")
                ).get("published_player_layer_count"),
            }
            for node in nodes[:MAX_SAMPLE_ITEMS]
        ],
    }


def map_runtime_activation_gate_summary(report: dict[str, Any]) -> dict[str, Any]:
    summary = as_obj(report.get("summary"))
    safety = as_obj(report.get("safety_summary"))
    decisions = [
        decision
        for decision in as_list(report.get("decisions"))
        if isinstance(decision, dict)
    ]
    return {
        "schema_version": report.get("schema_version"),
        "report_id": report.get("report_id"),
        "status": report.get("status"),
        "node_count": summary.get("node_count"),
        "activation_allowed_count": summary.get("activation_allowed_count"),
        "activation_blocked_count": summary.get("activation_blocked_count"),
        "decision_counts": as_obj(summary.get("decision_counts")),
        "decision_reason_counts": as_obj(summary.get("decision_reason_counts")),
        "check_status_counts": as_obj(summary.get("check_status_counts")),
        "blocker_counts": as_obj(summary.get("blocker_counts")),
        "readiness_status": summary.get("readiness_status"),
        "readiness_promotion_candidate_count": summary.get(
            "readiness_promotion_candidate_count"
        ),
        "api_default_runtime_v01_preserved_count": summary.get(
            "api_default_runtime_v01_preserved_count"
        ),
        "visual_promotion_violation_count": summary.get(
            "visual_promotion_violation_count"
        ),
        "required_authorization_kind": as_obj(
            report.get("next_activation_task_contract")
        ).get("required_authorization_kind"),
        "safety": {
            "reads_env_file": safety.get("reads_env_file"),
            "provider_call_count_by_report": safety.get(
                "provider_call_count_by_report"
            ),
            "world_mutation_count_by_report": safety.get(
                "world_mutation_count_by_report"
            ),
            "runtime_mutation_count_by_report": safety.get(
                "runtime_mutation_count_by_report"
            ),
            "default_runtime_mutation_performed": safety.get(
                "default_runtime_mutation_performed"
            ),
            "backend_api_contract_mutation_performed": safety.get(
                "backend_api_contract_mutation_performed"
            ),
            "frontend_contract_mutation_performed": safety.get(
                "frontend_contract_mutation_performed"
            ),
        },
        "decision_samples": [
            {
                "node_id": decision.get("node_id"),
                "activation_decision": decision.get("activation_decision"),
                "decision_reason": decision.get("decision_reason"),
                "blockers": as_list(decision.get("blockers")),
                "from_package_id": as_obj(decision.get("target_candidate")).get(
                    "from_package_id"
                ),
                "to_package_id": as_obj(decision.get("target_candidate")).get(
                    "to_package_id"
                ),
            }
            for decision in decisions[:MAX_SAMPLE_ITEMS]
        ],
    }


def map_path_geometry_summary(report: dict[str, Any]) -> dict[str, Any]:
    summary = as_obj(report.get("summary"))
    maps = [item for item in as_list(report.get("maps")) if isinstance(item, dict)]
    warning_maps = [item for item in maps if int(item.get("warning_count") or 0) > 0]
    return {
        "schema_version": report.get("schema_version"),
        "report_id": report.get("report_id"),
        "status": report.get("status"),
        "map_count": summary.get("map_count"),
        "route_count": summary.get("route_count"),
        "build_slot_count": summary.get("build_slot_count"),
        "total_route_length_cells": summary.get("total_route_length_cells"),
        "warning_count": summary.get("warning_count"),
        "source_policy": as_obj(report.get("source_policy")),
        "usage_policy": as_list(report.get("usage_policy")),
        "warning_map_samples": [
            {
                "node_id": item.get("node_id"),
                "schema_version": item.get("schema_version"),
                "warning_count": item.get("warning_count"),
                "warnings": as_list(item.get("warnings"))[:MAX_SAMPLE_ITEMS],
            }
            for item in warning_maps[:MAX_SAMPLE_ITEMS]
        ],
        "map_samples": [
            {
                "node_id": item.get("node_id"),
                "schema_version": item.get("schema_version"),
                "route_count": item.get("route_count"),
                "build_slot_count": item.get("build_slot_count"),
                "total_route_length_cells": item.get("total_route_length_cells"),
                "near_turn_slot_count": len(as_list(item.get("near_turn_slots"))),
                "warning_count": item.get("warning_count"),
            }
            for item in maps[:MAX_SAMPLE_ITEMS]
        ],
    }


def map_style_component_binding_summary(report: dict[str, Any]) -> dict[str, Any]:
    summary = as_obj(report.get("summary"))
    bindings = [
        binding
        for binding in as_list(report.get("bindings"))
        if isinstance(binding, dict)
    ]
    gaps = [
        gap
        for gap in as_list(report.get("coverage_gaps"))
        if isinstance(gap, dict)
    ]
    return {
        "schema_version": report.get("schema_version"),
        "report_id": report.get("report_id"),
        "status": report.get("status"),
        "style_pack_count": summary.get("style_pack_count"),
        "material_component_ref_count": summary.get("material_component_ref_count"),
        "prefab_reviewed_component_ref_count": summary.get(
            "prefab_reviewed_component_ref_count"
        ),
        "resolved_ref_count": summary.get("resolved_ref_count"),
        "missing_ref_count": summary.get("missing_ref_count"),
        "procedural_fallback_count": summary.get("procedural_fallback_count"),
        "component_coverage_gap_count": summary.get("component_coverage_gap_count"),
        "status_counts": as_obj(summary.get("status_counts")),
        "usage_policy": as_list(report.get("usage_policy")),
        "validation_commands": as_list(as_obj(report.get("validation")).get("commands")),
        "binding_samples": [
            {
                "style_pack_id": binding.get("style_pack_id"),
                "node_id": binding.get("node_id"),
                "binding_source": binding.get("binding_source"),
                "owner_id": binding.get("owner_id"),
                "role": binding.get("role"),
                "ref_kind": binding.get("ref_kind"),
                "resolution_status": binding.get("resolution_status"),
                "resolved_asset_id": as_obj(binding.get("resolved_ref")).get("asset_id"),
                "resolved_media_role": as_obj(binding.get("resolved_ref")).get("media_role"),
            }
            for binding in bindings[:MAX_SAMPLE_ITEMS]
        ],
        "coverage_gap_samples": gaps[:MAX_SAMPLE_ITEMS],
    }


def map_component_generation_request_summary(pack: dict[str, Any]) -> dict[str, Any]:
    summary = as_obj(pack.get("summary"))
    requests = [
        request
        for request in as_list(pack.get("requests"))
        if isinstance(request, dict)
    ]
    return {
        "schema_version": pack.get("schema_version"),
        "pack_id": pack.get("pack_id"),
        "status": pack.get("status"),
        "source_manifest_path": pack.get("source_manifest_path"),
        "request_count": summary.get("request_count"),
        "component_count": summary.get("component_count"),
        "style_pack_count": summary.get("style_pack_count"),
        "node_count": summary.get("node_count"),
        "target_media_kind_counts": as_obj(summary.get("target_media_kind_counts")),
        "component_role_counts": as_obj(summary.get("component_role_counts")),
        "status_counts": as_obj(summary.get("status_counts")),
        "usage_policy": as_list(pack.get("usage_policy")),
        "validation_commands": as_list(as_obj(pack.get("validation")).get("commands")),
        "request_samples": [
            {
                "request_id": request.get("request_id"),
                "component_id": request.get("component_id"),
                "component_role": request.get("component_role"),
                "style_pack_id": request.get("style_pack_id"),
                "node_id": request.get("node_id"),
                "baseline_local_path": request.get("baseline_local_path"),
                "target_size": as_obj(request.get("target_size")),
                "target_media_kind": request.get("target_media_kind"),
                "prompt_profile_id": request.get("prompt_profile_id"),
                "structured_prompt_tokens": as_list(request.get("structured_prompt_tokens")),
                "required_gates": as_list(request.get("required_gates")),
            }
            for request in requests[:MAX_SAMPLE_ITEMS]
        ],
    }


def map_component_artifact_staging_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    summary = as_obj(manifest.get("summary"))
    slots = [
        slot
        for slot in as_list(manifest.get("staging_slots"))
        if isinstance(slot, dict)
    ]
    return {
        "schema_version": manifest.get("schema_version"),
        "manifest_id": manifest.get("manifest_id"),
        "status": manifest.get("status"),
        "source_request_pack_path": manifest.get("source_request_pack_path"),
        "source_manifest_path": manifest.get("source_manifest_path"),
        "slot_count": summary.get("slot_count"),
        "request_count": summary.get("request_count"),
        "component_count": summary.get("component_count"),
        "style_pack_count": summary.get("style_pack_count"),
        "node_count": summary.get("node_count"),
        "imported_count": summary.get("imported_count"),
        "awaiting_count": summary.get("awaiting_count"),
        "not_imported_count": summary.get("not_imported_count"),
        "status_counts": as_obj(summary.get("status_counts")),
        "import_status_counts": as_obj(summary.get("import_status_counts")),
        "review_status_counts": as_obj(summary.get("review_status_counts")),
        "accepted_input_kind_counts": as_obj(summary.get("accepted_input_kind_counts")),
        "runtime_effect": as_obj(manifest.get("runtime_effect")),
        "usage_policy": as_list(manifest.get("usage_policy")),
        "validation_commands": as_list(as_obj(manifest.get("validation")).get("commands")),
        "slot_samples": [
            {
                "slot_id": slot.get("slot_id"),
                "request_id": slot.get("request_id"),
                "component_id": slot.get("component_id"),
                "component_role": slot.get("component_role"),
                "style_pack_id": slot.get("style_pack_id"),
                "node_id": slot.get("node_id"),
                "expected_size": as_obj(slot.get("expected_size")),
                "accepted_input_kinds": as_list(slot.get("accepted_input_kinds")),
                "candidate_local_path": slot.get("candidate_local_path"),
                "import_status": slot.get("import_status"),
                "review_status": slot.get("review_status"),
                "required_next_gates": as_list(slot.get("required_next_gates")),
            }
            for slot in slots[:MAX_SAMPLE_ITEMS]
        ],
    }


def map_component_candidate_review_summary(report: dict[str, Any]) -> dict[str, Any]:
    summary = as_obj(report.get("summary"))
    candidates = [
        candidate
        for candidate in as_list(report.get("candidates"))
        if isinstance(candidate, dict)
    ]
    return {
        "schema_version": report.get("schema_version"),
        "report_id": report.get("report_id"),
        "status": report.get("status"),
        "source_request_pack_path": report.get("source_request_pack_path"),
        "source_artifact_staging_manifest_path": report.get(
            "source_artifact_staging_manifest_path"
        ),
        "candidate_count": summary.get("candidate_count"),
        "baseline_fixture_candidate_count": summary.get("baseline_fixture_candidate_count"),
        "generated_candidate_count": summary.get("generated_candidate_count"),
        "promotable_count": summary.get("promotable_count"),
        "blocked_from_promotion_count": summary.get("blocked_from_promotion_count"),
        "no_generated_candidate_yet_count": summary.get("no_generated_candidate_yet_count"),
        "status_counts": as_obj(summary.get("status_counts")),
        "candidate_kind_counts": as_obj(summary.get("candidate_kind_counts")),
        "usage_policy": as_list(report.get("usage_policy")),
        "validation_commands": as_list(as_obj(report.get("validation")).get("commands")),
        "candidate_samples": [
            {
                "candidate_id": candidate.get("candidate_id"),
                "component_id": candidate.get("component_id"),
                "component_role": candidate.get("component_role"),
                "candidate_kind": candidate.get("candidate_kind"),
                "review_status": candidate.get("review_status"),
                "promotion_recommendation": candidate.get("promotion_recommendation"),
                "promotion_allowed_now": candidate.get("promotion_allowed_now"),
                "staging_slot_id": candidate.get("staging_slot_id"),
                "candidate_local_path": candidate.get("candidate_local_path"),
                "staging_import_status": candidate.get("staging_import_status"),
                "artifact_review_status": candidate.get("artifact_review_status"),
                "required_next_actions": as_list(candidate.get("required_next_actions")),
            }
            for candidate in candidates[:MAX_SAMPLE_ITEMS]
        ],
    }


def map_component_visual_quality_summary(report: dict[str, Any]) -> dict[str, Any]:
    summary = as_obj(report.get("summary"))
    items = [
        item
        for item in as_list(report.get("items"))
        if isinstance(item, dict)
    ]
    return {
        "schema_version": report.get("schema_version"),
        "report_id": report.get("report_id"),
        "status": report.get("status"),
        "source_candidate_review_report_path": report.get(
            "source_candidate_review_report_path"
        ),
        "source_candidate_count": summary.get("source_candidate_count"),
        "generated_candidate_count": summary.get("generated_candidate_count"),
        "checked_candidate_count": summary.get("checked_candidate_count"),
        "passed_count": summary.get("passed_count"),
        "blocked_pending_quality_gates_count": summary.get(
            "blocked_pending_quality_gates_count"
        ),
        "needs_review_count": summary.get("needs_review_count"),
        "unsupported_decode_count": summary.get("unsupported_decode_count"),
        "status_counts": as_obj(summary.get("status_counts")),
        "file_type_counts": as_obj(summary.get("file_type_counts")),
        "issue_counts": as_obj(summary.get("issue_counts")),
        "runtime_effect": as_obj(report.get("runtime_effect")),
        "promotion_effect": as_obj(report.get("promotion_effect")),
        "usage_policy": as_list(report.get("usage_policy")),
        "validation_commands": as_list(as_obj(report.get("validation")).get("commands")),
        "item_samples": [
            {
                "candidate_id": item.get("candidate_id"),
                "component_id": item.get("component_id"),
                "component_role": item.get("component_role"),
                "review_status": item.get("review_status"),
                "source_candidate_local_path": item.get("source_candidate_local_path"),
                "file_checks": as_obj(item.get("file_checks")),
                "cutout_normalization_status": item.get("cutout_normalization_status"),
                "issues": as_list(item.get("issues")),
                "warnings": as_list(item.get("warnings")),
            }
            for item in items[:MAX_SAMPLE_ITEMS]
        ],
    }


def map_component_promotion_gate_summary(report: dict[str, Any]) -> dict[str, Any]:
    summary = as_obj(report.get("summary"))
    decisions = [
        decision
        for decision in as_list(report.get("decisions"))
        if isinstance(decision, dict)
    ]
    return {
        "schema_version": report.get("schema_version"),
        "report_id": report.get("report_id"),
        "status": report.get("status"),
        "source_candidate_review_report_path": report.get(
            "source_candidate_review_report_path"
        ),
        "source_visual_quality_report_path": report.get(
            "source_visual_quality_report_path"
        ),
        "candidate_count": summary.get("candidate_count"),
        "generated_candidate_count": summary.get("generated_candidate_count"),
        "promotion_allowed_count": summary.get("promotion_allowed_count"),
        "promotion_blocked_count": summary.get("promotion_blocked_count"),
        "baseline_preserved_count": summary.get("baseline_preserved_count"),
        "visual_quality_report_status": summary.get("visual_quality_report_status"),
        "decision_counts": as_obj(summary.get("decision_counts")),
        "blocked_reasons": as_list(report.get("blocked_reasons")),
        "runtime_effect": as_obj(report.get("runtime_effect")),
        "usage_policy": as_list(report.get("usage_policy")),
        "validation_commands": as_list(as_obj(report.get("validation")).get("commands")),
        "decision_samples": [
            {
                "component_id": decision.get("component_id"),
                "candidate_id": decision.get("candidate_id"),
                "candidate_kind": decision.get("candidate_kind"),
                "decision": decision.get("decision"),
                "promotion_allowed": decision.get("promotion_allowed"),
                "baseline_preserved": decision.get("baseline_preserved"),
                "reason": decision.get("reason"),
                "visual_quality_status": decision.get("visual_quality_status"),
                "visual_quality_item_status": decision.get("visual_quality_item_status"),
                "visual_quality_checked": decision.get("visual_quality_checked"),
                "visual_quality_required": decision.get("visual_quality_required"),
                "visual_quality_blocker": decision.get("visual_quality_blocker"),
            }
            for decision in decisions[:MAX_SAMPLE_ITEMS]
        ],
    }


def map_component_manifest_patch_plan_summary(plan: dict[str, Any]) -> dict[str, Any]:
    summary = as_obj(plan.get("summary"))
    patches = [
        patch
        for patch in as_list(plan.get("patches"))
        if isinstance(patch, dict)
    ]
    return {
        "schema_version": plan.get("schema_version"),
        "plan_id": plan.get("plan_id"),
        "status": plan.get("status"),
        "source_promotion_gate_report_path": plan.get(
            "source_promotion_gate_report_path"
        ),
        "source_candidate_review_report_path": plan.get(
            "source_candidate_review_report_path"
        ),
        "source_visual_quality_report_path": plan.get(
            "source_visual_quality_report_path"
        ),
        "source_manifest_path": plan.get("source_manifest_path"),
        "allowed_decision_count": summary.get("allowed_decision_count"),
        "patch_count": summary.get("patch_count"),
        "blocked_patch_count": summary.get("blocked_patch_count"),
        "ready_patch_count": summary.get("ready_patch_count"),
        "manifest_item_count": summary.get("manifest_item_count"),
        "runtime_effect": as_obj(plan.get("runtime_effect")),
        "usage_policy": as_list(plan.get("usage_policy")),
        "validation_commands": as_list(as_obj(plan.get("validation")).get("commands")),
        "patch_samples": [
            {
                "patch_id": patch.get("patch_id"),
                "candidate_id": patch.get("candidate_id"),
                "component_id": patch.get("component_id"),
                "stable_internal_id": patch.get("stable_internal_id"),
                "patch_status": patch.get("patch_status"),
                "manifest_schema_compatible_now": patch.get(
                    "manifest_schema_compatible_now"
                ),
                "target_manifest_item_found": patch.get(
                    "target_manifest_item_found"
                ),
                "replacement_source": as_obj(patch.get("replacement_source")),
                "proposed_processed_local_path": patch.get(
                    "proposed_processed_local_path"
                ),
                "proposed_public_url": patch.get("proposed_public_url"),
            }
            for patch in patches[:MAX_SAMPLE_ITEMS]
        ],
    }


def map_component_manifest_apply_report_summary(report: dict[str, Any]) -> dict[str, Any]:
    summary = as_obj(report.get("summary"))
    manifest_sha = as_obj(report.get("manifest_sha"))
    return {
        "schema_version": report.get("schema_version"),
        "report_id": report.get("report_id"),
        "status": report.get("status"),
        "approval_id": report.get("approval_id"),
        "source_patch_plan_path": report.get("source_patch_plan_path"),
        "source_manifest_path": report.get("source_manifest_path"),
        "source_approval_plan_path": report.get("source_approval_plan_path"),
        "output_manifest_path": report.get("output_manifest_path"),
        "source_patch_count": summary.get("source_patch_count"),
        "approved_patch_count": summary.get("approved_patch_count"),
        "applied_patch_count": summary.get("applied_patch_count"),
        "skipped_patch_count": summary.get("skipped_patch_count"),
        "blocked_patch_count": summary.get("blocked_patch_count"),
        "ready_patch_count": summary.get("ready_patch_count"),
        "manifest_item_count": summary.get("manifest_item_count"),
        "runtime_effect": as_obj(report.get("runtime_effect")),
        "source_manifest_file_sha256_before": manifest_sha.get(
            "source_manifest_file_sha256_before"
        ),
        "replacement_manifest_content_sha256_after": manifest_sha.get(
            "replacement_manifest_content_sha256_after"
        ),
        "replacement_manifest_file_sha256_after": manifest_sha.get(
            "replacement_manifest_file_sha256_after"
        ),
        "usage_policy": as_list(report.get("usage_policy")),
        "validation_commands": as_list(as_obj(report.get("validation")).get("commands")),
    }


def node_map_candidate_review_summary(report: dict[str, Any]) -> dict[str, Any]:
    summary = as_obj(report.get("summary"))
    candidates = [candidate for candidate in as_list(report.get("candidates")) if isinstance(candidate, dict)]
    return {
        "schema_version": report.get("schema_version"),
        "report_id": report.get("report_id"),
        "status": report.get("status"),
        "candidate_count": summary.get("candidate_count"),
        "runtime_promotion_count": summary.get("runtime_promotion_count"),
        "blocking_candidate_count": summary.get("blocking_candidate_count"),
        "review_status_counts": as_obj(summary.get("review_status_counts")),
        "candidate_samples": [
            {
                "node_id": candidate.get("node_id"),
                "candidate_path": candidate.get("candidate_path"),
                "review_status": candidate.get("review_status"),
                "blocking_findings": as_list(candidate.get("blocking_findings")),
                "recommended_next_action": candidate.get("recommended_next_action"),
            }
            for candidate in candidates[:MAX_SAMPLE_ITEMS]
        ],
    }


def map_candidate_alignment_summary(report: dict[str, Any]) -> dict[str, Any]:
    summary = as_obj(report.get("summary"))
    candidates = [candidate for candidate in as_list(report.get("candidates")) if isinstance(candidate, dict)]
    return {
        "schema_version": report.get("schema_version"),
        "report_id": report.get("report_id"),
        "status": report.get("status"),
        "candidate_count": summary.get("candidate_count"),
        "blocked_count": summary.get("blocked_count"),
        "transform_required_count": summary.get("transform_required_count"),
        "status_counts": as_obj(summary.get("status_counts")),
        "warning_counts": as_obj(summary.get("warning_counts")),
        "candidate_samples": [
            {
                "node_id": candidate.get("node_id"),
                "candidate_path": candidate.get("candidate_path"),
                "runtime_package_path": candidate.get("runtime_package_path"),
                "status": candidate.get("status"),
                "transform_required": candidate.get("transform_required"),
                "runtime_structure": as_obj(candidate.get("runtime_structure")),
            }
            for candidate in candidates[:MAX_SAMPLE_ITEMS]
        ],
    }


def map_candidate_overlay_summary(report: dict[str, Any]) -> dict[str, Any]:
    summary = as_obj(report.get("summary"))
    artifacts = [artifact for artifact in as_list(report.get("artifacts")) if isinstance(artifact, dict)]
    return {
        "schema_version": report.get("schema_version"),
        "report_id": report.get("report_id"),
        "status": report.get("status"),
        "candidate_count": summary.get("candidate_count"),
        "overlay_artifact_ready_count": summary.get("overlay_artifact_ready_count"),
        "blocked_count": summary.get("blocked_count"),
        "target_size": as_obj(summary.get("target_size")),
        "status_counts": as_obj(summary.get("status_counts")),
        "artifact_samples": [
            {
                "node_id": artifact.get("node_id"),
                "status": artifact.get("status"),
                "normalized_path": artifact.get("normalized_path"),
                "overlay_review_path": artifact.get("overlay_review_path"),
                "transform": as_obj(artifact.get("transform")),
            }
            for artifact in artifacts[:MAX_SAMPLE_ITEMS]
        ],
    }


def map_candidate_overlay_visual_summary(report: dict[str, Any]) -> dict[str, Any]:
    summary = as_obj(report.get("summary"))
    reviews = [review for review in as_list(report.get("reviews")) if isinstance(review, dict)]
    return {
        "schema_version": report.get("schema_version"),
        "report_id": report.get("report_id"),
        "status": report.get("status"),
        "candidate_count": summary.get("candidate_count"),
        "promotable_count": summary.get("promotable_count"),
        "blocked_from_promotion_count": summary.get("blocked_from_promotion_count"),
        "status_counts": as_obj(summary.get("status_counts")),
        "promotion_recommendation_counts": as_obj(summary.get("promotion_recommendation_counts")),
        "review_samples": [
            {
                "node_id": review.get("node_id"),
                "status": review.get("status"),
                "promotion_recommendation": review.get("promotion_recommendation"),
                "findings": as_list(review.get("findings")),
                "overlay_review_png_path": review.get("overlay_review_png_path"),
            }
            for review in reviews[:MAX_SAMPLE_ITEMS]
        ],
    }


def map_layout_reconciliation_summary(plan: dict[str, Any]) -> dict[str, Any]:
    summary = as_obj(plan.get("summary"))
    node_plans = [node_plan for node_plan in as_list(plan.get("node_plans")) if isinstance(node_plan, dict)]
    return {
        "schema_version": plan.get("schema_version"),
        "plan_id": plan.get("plan_id"),
        "status": plan.get("status"),
        "node_count": summary.get("node_count"),
        "p0_count": summary.get("p0_count"),
        "promotion_allowed_now_count": summary.get("promotion_allowed_now_count"),
        "blocked_from_promotion_count": summary.get("blocked_from_promotion_count"),
        "recommendation_counts": as_obj(summary.get("recommendation_counts")),
        "node_samples": [
            {
                "node_id": node_plan.get("node_id"),
                "priority": node_plan.get("priority"),
                "recommendation": node_plan.get("recommendation"),
                "promotion_allowed_now": node_plan.get("promotion_allowed_now"),
                "proposed_actions": as_list(node_plan.get("proposed_actions")),
            }
            for node_plan in node_plans[:MAX_SAMPLE_ITEMS]
        ],
    }


def runtime_map_patch_candidate_summary(report: dict[str, Any]) -> dict[str, Any]:
    summary = as_obj(report.get("summary"))
    candidates = [candidate for candidate in as_list(report.get("candidates")) if isinstance(candidate, dict)]
    return {
        "schema_version": report.get("schema_version"),
        "report_id": report.get("report_id"),
        "status": report.get("status"),
        "candidate_count": summary.get("candidate_count"),
        "review_candidate_count": summary.get("review_candidate_count"),
        "skipped_count": summary.get("skipped_count"),
        "status_counts": as_obj(summary.get("status_counts")),
        "candidate_samples": [
            {
                "node_id": candidate.get("node_id"),
                "status": candidate.get("status"),
                "patch_strategy": candidate.get("patch_strategy"),
                "promotion_allowed_now": candidate.get("promotion_allowed_now"),
                "operation_count": len(as_list(candidate.get("patch_operations"))),
            }
            for candidate in candidates[:MAX_SAMPLE_ITEMS]
        ],
    }


def map_patch_overlay_review_summary(report: dict[str, Any]) -> dict[str, Any]:
    summary = as_obj(report.get("summary"))
    artifacts = [artifact for artifact in as_list(report.get("artifacts")) if isinstance(artifact, dict)]
    return {
        "schema_version": report.get("schema_version"),
        "report_id": report.get("report_id"),
        "status": report.get("status"),
        "candidate_count": summary.get("candidate_count"),
        "patched_overlay_artifact_ready_count": summary.get(
            "patched_overlay_artifact_ready_count"
        ),
        "validation_failed_count": summary.get("validation_failed_count"),
        "skipped_count": summary.get("skipped_count"),
        "blocked_count": summary.get("blocked_count"),
        "promotion_allowed_now_count": summary.get("promotion_allowed_now_count"),
        "target_size": as_obj(summary.get("target_size")),
        "status_counts": as_obj(summary.get("status_counts")),
        "artifact_samples": [
            {
                "node_id": artifact.get("node_id"),
                "status": artifact.get("status"),
                "patch_operation_count": artifact.get("patch_operation_count"),
                "patched_overlay_review_png_path": artifact.get(
                    "patched_overlay_review_png_path"
                ),
                "validation": as_obj(artifact.get("validation")),
            }
            for artifact in artifacts[:MAX_SAMPLE_ITEMS]
        ],
    }


def topology_constrained_prompt_pack_summary(pack: dict[str, Any]) -> dict[str, Any]:
    summary = as_obj(pack.get("summary"))
    prompts = [prompt for prompt in as_list(pack.get("prompts")) if isinstance(prompt, dict)]
    return {
        "schema_version": pack.get("schema_version"),
        "pack_id": pack.get("pack_id"),
        "status": pack.get("status"),
        "prompt_count": summary.get("prompt_count"),
        "primary_prompt_count": summary.get("primary_prompt_count"),
        "fallback_prompt_count": summary.get("fallback_prompt_count"),
        "status_counts": as_obj(summary.get("status_counts")),
        "prompt_samples": [
            {
                "node_id": prompt.get("node_id"),
                "status": prompt.get("status"),
                "primary_use": prompt.get("primary_use"),
                "topology_policy": prompt.get("topology_policy"),
                "negative_constraints": as_list(prompt.get("negative_constraints")),
            }
            for prompt in prompts[:MAX_SAMPLE_ITEMS]
        ],
    }


def map_topology_control_sketch_pack_summary(pack: dict[str, Any]) -> dict[str, Any]:
    summary = as_obj(pack.get("summary"))
    sketches = [sketch for sketch in as_list(pack.get("sketches")) if isinstance(sketch, dict)]
    return {
        "schema_version": pack.get("schema_version"),
        "pack_id": pack.get("pack_id"),
        "status": pack.get("status"),
        "sketch_count": summary.get("sketch_count"),
        "ready_count": summary.get("ready_count"),
        "blocked_count": summary.get("blocked_count"),
        "target_size": as_obj(summary.get("target_size")),
        "status_counts": as_obj(summary.get("status_counts")),
        "policy": as_list(pack.get("policy")),
        "sketch_samples": [
            {
                "node_id": sketch.get("node_id"),
                "status": sketch.get("status"),
                "control_sketch_png_path": sketch.get("control_sketch_png_path"),
                "control_sketch_svg_path": sketch.get("control_sketch_svg_path"),
                "runtime_summary": as_obj(sketch.get("runtime_summary")),
                "usage_policy": as_list(sketch.get("usage_policy")),
            }
            for sketch in sketches[:MAX_SAMPLE_ITEMS]
        ],
    }


def procedural_map_preview_summary(reports: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(
        str(report.get("status") or "unknown")
        for report in reports
        if isinstance(report, dict)
    )
    usage_counts: Counter[str] = Counter()
    source_policy_counts: Counter[str] = Counter()
    for report in reports:
        if not isinstance(report, dict):
            continue
        usage_counts.update(str(policy) for policy in as_list(report.get("usage_policy")))
        semantic_policy = as_obj(report.get("semantic_source_policy"))
        source_policy_counts.update(
            f"{key}:{value}" for key, value in sorted(semantic_policy.items())
        )

    samples = []
    for report in reports[:MAX_SAMPLE_ITEMS]:
        if not isinstance(report, dict):
            continue
        source_refs = as_obj(report.get("source_refs"))
        runtime_path = str(source_refs.get("map_runtime_package_path") or "")
        node_id = Path(runtime_path).name.replace(".map_runtime_package.json", "")
        samples.append(
            {
                "report_id": report.get("report_id"),
                "status": report.get("status"),
                "node_id": node_id or None,
                "preview_svg_path": report.get("preview_svg_path"),
                "preview_svg_sha256": report.get("preview_svg_sha256"),
                "render_summary": as_obj(report.get("render_summary")),
                "semantic_source_policy": as_obj(report.get("semantic_source_policy")),
                "source_refs": source_refs,
                "usage_policy": as_list(report.get("usage_policy")),
            }
        )

    return {
        "schema_version": "procedural_map_preview_report.v0.1",
        "report_count": len(reports),
        "ready_count": status_counts.get("preview_ready_review_only", 0),
        "status_counts": dict(sorted(status_counts.items())),
        "usage_policy_counts": dict(sorted(usage_counts.items())),
        "semantic_source_policy_counts": dict(sorted(source_policy_counts.items())),
        "preview_samples": samples,
        "runtime_activation_policy": "review_only_not_player_runtime",
    }


def map_controlled_regeneration_request_pack_summary(pack: dict[str, Any]) -> dict[str, Any]:
    summary = as_obj(pack.get("summary"))
    requests = [request for request in as_list(pack.get("requests")) if isinstance(request, dict)]
    return {
        "schema_version": pack.get("schema_version"),
        "pack_id": pack.get("pack_id"),
        "status": pack.get("status"),
        "request_count": summary.get("request_count"),
        "ready_count": summary.get("ready_count"),
        "blocked_count": summary.get("blocked_count"),
        "reference_image_request_count": summary.get("reference_image_request_count"),
        "status_counts": as_obj(summary.get("status_counts")),
        "policy": as_list(pack.get("policy")),
        "request_samples": [
            {
                "request_id": request.get("request_id"),
                "node_id": request.get("node_id"),
                "status": request.get("status"),
                "primary_use": request.get("primary_use"),
                "topology_policy": request.get("topology_policy"),
                "control_sketch_png_path": as_obj(request.get("control_sketch")).get("png_path"),
                "manual_prompt_markdown_path": request.get("manual_prompt_markdown_path"),
                "provider_reference_contract": as_obj(
                    request.get("provider_reference_contract")
                ),
                "target_candidate": as_obj(request.get("target_candidate")),
            }
            for request in requests[:MAX_SAMPLE_ITEMS]
        ],
    }


def controlled_map_candidate_generation_summary(report: dict[str, Any]) -> dict[str, Any]:
    summary = as_obj(report.get("summary"))
    results = [result for result in as_list(report.get("results")) if isinstance(result, dict)]
    return {
        "schema_version": report.get("schema_version"),
        "report_id": report.get("report_id"),
        "status": report.get("status"),
        "provider_mode": report.get("provider_mode"),
        "live": report.get("live"),
        "provider_profile": report.get("provider_profile"),
        "request_count": summary.get("request_count"),
        "result_count": summary.get("result_count"),
        "failure_count": summary.get("failure_count"),
        "image_exists_count": summary.get("image_exists_count"),
        "provider_call_count": summary.get("provider_call_count"),
        "handoff_ready_count": summary.get("handoff_ready_count"),
        "status_counts": as_obj(summary.get("status_counts")),
        "result_samples": [
            {
                "node_id": result.get("node_id"),
                "status": result.get("status"),
                "provider_mode": result.get("provider_mode"),
                "image_exists": result.get("image_exists"),
                "sidecar_path": result.get("sidecar_path"),
                "control_sketch_png_path": result.get("control_sketch_png_path"),
                "control_sketch_public_url": result.get("control_sketch_public_url"),
                "review_status": result.get("review_status"),
            }
            for result in results[:MAX_SAMPLE_ITEMS]
        ],
    }


def collect_map_runtime_package(map_package: dict[str, Any]) -> dict[str, Any]:
    visual_layers = as_list(map_package.get("visual_layers"))
    return {
        "schema_version": map_package.get("schema_version"),
        "package_id": map_package.get("package_id"),
        "worldbook_id": map_package.get("worldbook_id"),
        "node_id": map_package.get("node_id"),
        "battle_config_version": map_package.get("battle_config_version"),
        "grid": as_obj(map_package.get("grid")),
        "path_route_count": len(as_list(map_package.get("path_routes"))),
        "build_slot_count": len(as_list(map_package.get("build_slots"))),
        "spawn_point_count": len(as_list(map_package.get("spawn_points"))),
        "objective_count": 1
        + len(as_list(as_obj(map_package.get("objectives")).get("optional_targets"))),
        "resource_node_count": len(as_list(map_package.get("resource_nodes"))),
        "hazard_zone_count": len(as_list(map_package.get("hazard_zones"))),
        "defense_anchor_count": len(as_list(map_package.get("defense_anchors"))),
        "blocked_area_count": len(as_list(map_package.get("blocked_areas"))),
        "runtime_hints": as_obj(map_package.get("runtime_hints")),
        "visual_layer_count": len(visual_layers),
        "published_visual_layer_count": sum(
            1
            for layer in visual_layers
            if isinstance(layer, dict)
            and layer.get("authority") == "published_visual_layer"
        ),
        "visual_layers": [
            {
                "layer_id": layer.get("layer_id"),
                "role": layer.get("role"),
                "authority": layer.get("authority"),
                "url": layer.get("url"),
                "local_path": layer.get("local_path"),
                "width": layer.get("width"),
                "height": layer.get("height"),
                "sha256": layer.get("sha256"),
            }
            for layer in visual_layers
            if isinstance(layer, dict)
        ],
        "validation_report": as_obj(map_package.get("validation_report")),
    }


def collect_map_runtime_packages(map_packages: list[dict[str, Any]]) -> dict[str, Any]:
    packages = [collect_map_runtime_package(package) for package in map_packages]
    return {
        "package_count": len(packages),
        "node_ids": [package.get("node_id") for package in packages],
        "total_path_route_count": sum(int(package.get("path_route_count") or 0) for package in packages),
        "total_build_slot_count": sum(int(package.get("build_slot_count") or 0) for package in packages),
        "total_spawn_point_count": sum(int(package.get("spawn_point_count") or 0) for package in packages),
        "total_resource_node_count": sum(int(package.get("resource_node_count") or 0) for package in packages),
        "total_hazard_zone_count": sum(int(package.get("hazard_zone_count") or 0) for package in packages),
        "total_defense_anchor_count": sum(int(package.get("defense_anchor_count") or 0) for package in packages),
        "total_blocked_area_count": sum(int(package.get("blocked_area_count") or 0) for package in packages),
        "published_visual_layer_count": sum(
            int(package.get("published_visual_layer_count") or 0) for package in packages
        ),
        "packages": packages,
    }


def collect_map_v02_preview_api_smoke(report: dict[str, Any]) -> dict[str, Any]:
    safety = as_obj(report.get("safety_summary"))
    return {
        "schema_version": report.get("schema_version"),
        "report_id": report.get("report_id"),
        "status": report.get("status"),
        "endpoint": report.get("endpoint"),
        "response_wrapper_mode": report.get("response_wrapper_mode"),
        "node_count": report.get("node_count"),
        "node_ids": as_list(report.get("node_ids")),
        "semantic_totals": as_obj(report.get("semantic_totals")),
        "default_runtime_v01_preserved_count": report.get(
            "default_runtime_v01_preserved_count"
        ),
        "unknown_node_status_code": report.get("unknown_node_status_code"),
        "review_only": report.get("review_only"),
        "runtime_activation_allowed": report.get("runtime_activation_allowed"),
        "safety": {
            "reads_env_file": safety.get("reads_env_file"),
            "provider_call_count": safety.get("provider_call_count"),
            "player_default_runtime_mutation_count": safety.get(
                "player_default_runtime_mutation_count"
            ),
            "world_state_mutation_count": safety.get("world_state_mutation_count"),
        },
        "node_samples": [
            {
                "node_id": item.get("node_id"),
                "v02_package_id": item.get("v02_package_id"),
                "counts": as_obj(item.get("counts")),
                "preview_svg_ref": item.get("preview_svg_ref"),
                "default_runtime_schema_version": item.get(
                    "default_runtime_schema_version"
                ),
                "default_runtime_v02_field_leak_count": item.get(
                    "default_runtime_v02_field_leak_count"
                ),
            }
            for item in as_list(report.get("nodes"))
            if isinstance(item, dict)
        ],
    }


def collect_mvp_primary_api_flow_smoke(report: dict[str, Any]) -> dict[str, Any]:
    safety = as_obj(report.get("safety_summary"))
    summary = as_obj(report.get("summary"))
    research = as_obj(report.get("research"))
    core_artifacts = as_obj(report.get("core_artifacts"))
    return {
        "schema_version": report.get("schema_version"),
        "report_id": report.get("report_id"),
        "status": report.get("status"),
        "flow_id": report.get("flow_id"),
        "transport": report.get("transport"),
        "node_id": report.get("node_id"),
        "step_count": report.get("step_count"),
        "passed_step_count": report.get("passed_step_count"),
        "endpoint_steps": as_list(report.get("endpoint_steps")),
        "summary": {
            "world_phase": summary.get("world_phase"),
            "opening_card_count": summary.get("opening_card_count"),
            "frontend_asset_count": summary.get("frontend_asset_count"),
            "runtime_art_asset_count": summary.get("runtime_art_asset_count"),
            "map_node_count": summary.get("map_node_count"),
            "campaign_current_node": summary.get("campaign_current_node"),
            "campaign_next_node": summary.get("campaign_next_node"),
            "battle_enemy_wave_count": summary.get("battle_enemy_wave_count"),
            "battle_toolbar_asset_count": summary.get("battle_toolbar_asset_count"),
            "runtime_asset_count": summary.get("runtime_asset_count"),
            "map_build_slot_count": summary.get("map_build_slot_count"),
            "settlement_mode": summary.get("settlement_mode"),
            "settlement_phase": summary.get("settlement_phase"),
        },
        "research": {
            "proposal_created": research.get("proposal_created"),
            "job_status": research.get("job_status"),
            "job_fetch_status": research.get("job_fetch_status"),
            "job_trace_count": research.get("job_trace_count"),
            "runtime_package_exists": research.get("runtime_package_exists"),
            "delivery_payload_exists": research.get("delivery_payload_exists"),
            "job_gate_status": research.get("job_gate_status"),
            "player_text_safety": research.get("player_text_safety"),
        },
        "core_artifacts": {
            "proposal_status": core_artifacts.get("proposal_status"),
            "job_status": core_artifacts.get("job_status"),
            "settlement_status": core_artifacts.get("settlement_status"),
            "world_delta_transaction_id": core_artifacts.get(
                "world_delta_transaction_id"
            ),
        },
        "checks": as_obj(report.get("checks")),
        "safety": {
            "reads_env_file": safety.get("reads_env_file"),
            "provider_call_count": safety.get("provider_call_count"),
            "runtime_activation_mutation_count": safety.get(
                "runtime_activation_mutation_count"
            ),
            "world_state_write_scope": safety.get("world_state_write_scope"),
        },
    }


def collect_map_compile_package(package: dict[str, Any]) -> dict[str, Any]:
    logical = as_obj(package.get("logical_map_layer"))
    control = as_obj(package.get("control_layer"))
    painted = as_obj(package.get("painted_visual_layer"))
    alignment = as_obj(package.get("alignment_layer"))
    validation = as_obj(package.get("validation_report"))
    quality_gates = as_list(package.get("quality_gates"))
    return {
        "schema_version": package.get("schema_version"),
        "package_id": package.get("package_id"),
        "worldbook_id": package.get("worldbook_id"),
        "node_id": package.get("node_id"),
        "map_runtime_package_path": as_obj(package.get("source_refs")).get("map_runtime_package_path"),
        "logical_counts": {
            "path_routes": logical.get("path_route_count"),
            "build_slots": logical.get("build_slot_count"),
            "objectives": logical.get("objective_count"),
            "spawn_points": logical.get("spawn_point_count"),
        },
        "control_artifact_count": len(as_list(control.get("artifacts"))),
        "painted_visual_status": painted.get("status"),
        "painted_visual_role": as_obj(painted.get("artifact")).get("role"),
        "alignment_status": alignment.get("alignment_status"),
        "alignment_checkpoint_count": len(as_list(alignment.get("checkpoints"))),
        "quality_gate_count": len(quality_gates),
        "quality_gate_statuses": count_by(quality_gates, "status"),
        "validation_report": {
            "gate_status": validation.get("gate_status"),
            "runtime_truth_preserved": validation.get("runtime_truth_preserved"),
            "player_visual_safe": validation.get("player_visual_safe"),
        },
    }


def collect_map_compile_packages(packages: list[dict[str, Any]]) -> dict[str, Any]:
    summaries = [collect_map_compile_package(package) for package in packages]
    return {
        "package_count": len(summaries),
        "node_ids": [package.get("node_id") for package in summaries],
        "total_quality_gate_count": sum(int(package.get("quality_gate_count") or 0) for package in summaries),
        "packages": summaries,
    }


def collect_runtime_package(runtime_package: dict[str, Any]) -> dict[str, Any]:
    assets = as_list(runtime_package.get("assets"))
    visual_recipe_counts: Counter[str] = Counter()
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        for recipe in as_list(asset.get("visual_recipes")):
            if isinstance(recipe, dict) and recipe.get("kind"):
                visual_recipe_counts[str(recipe["kind"])] += 1
    return {
        "schema_version": runtime_package.get("schema_version"),
        "package_id": runtime_package.get("package_id"),
        "session_id": runtime_package.get("session_id"),
        "worldbook_id": runtime_package.get("worldbook_id"),
        "node_id": runtime_package.get("node_id"),
        "battle_display_name": runtime_package.get("battle_display_name"),
        "asset_count": len(assets),
        "asset_summaries": [
            {
                "stable_internal_id": asset.get("stable_internal_id"),
                "asset_kind": asset.get("asset_kind"),
                "lifecycle_state": asset.get("lifecycle_state"),
                "display_name": as_obj(asset.get("display")).get("name"),
                "availability_surfaces": as_list(
                    as_obj(asset.get("battle_availability")).get("surfaces")
                ),
            }
            for asset in assets
            if isinstance(asset, dict)
        ],
        "visual_recipe_kinds": dict(sorted(visual_recipe_counts.items())),
    }


def collect_ai_compilation_link(
    frontend_pack: dict[str, Any],
    dossier: dict[str, Any],
    multistage_pack: dict[str, Any],
) -> dict[str, Any]:
    compiler_summary = as_obj(frontend_pack.get("compiler_summary"))
    stage_summaries = as_list(multistage_pack.get("stage_summaries"))
    pipeline_overview = as_list(dossier.get("pipeline_overview"))
    workflow_files = [file_ref(path, "reviewed_workflow") for path in REVIEWED_WORKFLOW_FILES]
    source_boundary = as_obj(as_obj(frontend_pack.get("content_sources")).get("source_boundary"))
    return {
        "claim": "玩家自然语言与世界上下文进入受控内容编译链路，产出审查后的可玩资产、运行时包和世界状态变化。",
        "compiled_artifact_counts": {
            "frontend_assets": compiler_summary.get("asset_count"),
            "playable_assets": compiler_summary.get("playable_count"),
            "runtime_packages": compiler_summary.get("runtime_package_count"),
            "stages": compiler_summary.get("stage_count"),
        },
        "pipeline_steps": as_list(compiler_summary.get("pipeline")),
        "reviewed_workflow_files": workflow_files,
        "dossier_pipeline_step_count": len(pipeline_overview),
        "multistage_stage_count": len(stage_summaries),
        "source_boundary": {
            "player_safe": source_boundary.get("player_safe"),
            "reads_environment": source_boundary.get("reads_env"),
            "calls_external_service": source_boundary.get("calls_external_service"),
            "contains_original_external_payload": source_boundary.get(
                "contains_raw_external_payload"
            ),
        },
        "redacted_internal_details": [
            "凭据字段值",
            "原始提示词",
            "外部生成器原始响应",
            "完整执行轨迹",
            "未审长文本内容",
        ],
    }


def collect_provider_runner_handoff_summary() -> dict[str, Any]:
    export_task = load_json(PATHS["provider_runner_handoff_export_task_pack"])
    roundtrip_task = load_json(PATHS["provider_runner_handoff_roundtrip_task_pack"])
    return {
        "status": "fixture_roundtrip_covered",
        "export_endpoint": (
            "POST /api/sessions/{session_id}/generation-schedule/workers/"
            "export-provider-adapter-runner-handoff"
        ),
        "import_endpoint": (
            "POST /api/sessions/{session_id}/generation-schedule/workers/"
            "import-provider-adapter-runner-output"
        ),
        "prefetch_cache_endpoint": (
            "GET /api/sessions/{session_id}/generation-schedule/prefetch-cache"
        ),
        "runner_tool": "tools/provider_adapter/run_provider_adapter.py",
        "handoff_outputs": [
            "runner_inputs.executor_request",
            "runner_inputs.provider_execution_authorization",
            "suggested_paths",
            "command_templates.dry_run_fixture",
            "command_templates.live_llm_text",
            "command_templates.live_image",
            "import_after_runner.body",
        ],
        "roundtrip_evidence": {
            "test_name": (
                "test_provider_adapter_runner_handoff_roundtrip_import_updates_"
                "prefetch_cache"
            ),
            "expected_cache_status": "review_only_envelope_ready",
            "staging_performed": False,
            "promotion_performed": False,
            "runtime_activation_allowed": False,
        },
        "safety": {
            "api_reads_env": False,
            "api_calls_provider": False,
            "prompt_body_stored": False,
            "provider_body_stored": False,
            "writes_world_state": False,
            "activates_runtime": False,
            "live_templates_require_external_authorization": True,
        },
        "task_packs": [
            file_ref(PATHS["provider_runner_handoff_export_task_pack"], "worker_task_pack"),
            file_ref(PATHS["provider_runner_handoff_roundtrip_task_pack"], "worker_task_pack"),
        ],
        "acceptance_commands": sorted(
            set(as_list(export_task.get("acceptance_commands")))
            | set(as_list(roundtrip_task.get("acceptance_commands")))
        ),
    }


def collect_scheduler_background_tick_summary() -> dict[str, Any]:
    task = load_json(PATHS["scheduler_background_tick_task_pack"])
    return {
        "status": "review_only_tick_api_ready",
        "endpoint": (
            "POST /api/sessions/{session_id}/generation-schedule/workers/"
            "run-review-only-background-executor-tick"
        ),
        "default_max_items": 2,
        "max_items_limit": 8,
        "dispatch_boundary": "ProviderAdapterExecutionReceipt / ProviderOutputEnvelope",
        "prefetch_cache_status": "review_only_envelope_ready",
        "safety": {
            "api_reads_env": False,
            "api_calls_provider": False,
            "api_stages_provider_artifacts": False,
            "api_promotes_provider_artifacts": False,
            "api_completes_queue_items": False,
            "api_writes_world_state": False,
            "api_activates_runtime": False,
        },
        "opencode_headless_attempt": {
            "attempted": True,
            "status": "rejected_by_execution_policy",
            "reason": "external_model_context_disclosure_risk",
            "fallback": "local_codex_safe_fallback",
        },
        "task_pack": file_ref(PATHS["scheduler_background_tick_task_pack"], "worker_task_pack"),
        "acceptance_commands": as_list(task.get("acceptance_commands")),
    }


def collect_scheduler_background_handoff_tick_summary() -> dict[str, Any]:
    task = load_json(PATHS["scheduler_background_handoff_tick_task_pack"])
    outbox_task = load_json(PATHS["provider_runner_handoff_outbox_task_pack"])
    return {
        "status": "review_only_handoff_tick_ready",
        "outbox_status": "provider_adapter_runner_handoff_outbox_v0_1_ready",
        "endpoint": (
            "POST /api/sessions/{session_id}/generation-schedule/workers/"
            "run-review-only-background-handoff-tick"
        ),
        "default_max_items": 2,
        "max_items_limit": 8,
        "handoff_mode": "external_runner_required",
        "expected_runner_handoff_count": 2,
        "handoff_outputs": [
            "runner_inputs.executor_request",
            "runner_inputs.provider_execution_authorization",
            "suggested_paths",
            "command_templates.dry_run_fixture",
            "command_templates.live_llm_text",
            "command_templates.live_image",
            "import_after_runner.body",
        ],
        "safety": {
            "api_reads_env": False,
            "api_calls_provider": False,
            "api_runs_provider_adapter": False,
            "api_stages_provider_artifacts": False,
            "api_promotes_provider_artifacts": False,
            "api_completes_queue_items": False,
            "api_writes_world_state": False,
            "api_activates_runtime": False,
            "live_templates_require_external_authorization": True,
        },
        "opencode_headless_attempt": {
            "attempted": True,
            "status": "rejected_by_execution_policy",
            "reason": "external_model_context_disclosure_risk",
            "fallback": "local_codex_safe_fallback",
        },
        "task_pack": file_ref(
            PATHS["scheduler_background_handoff_tick_task_pack"],
            "worker_task_pack",
        ),
        "outbox_schema": file_ref(
            PATHS["provider_runner_handoff_outbox_schema"],
            "schema",
        ),
        "outbox_validator": file_ref(
            PATHS["provider_runner_handoff_outbox_validator"],
            "validator",
        ),
        "outbox_task_pack": file_ref(
            PATHS["provider_runner_handoff_outbox_task_pack"],
            "worker_task_pack",
        ),
        "acceptance_commands": as_list(task.get("acceptance_commands")),
        "outbox_acceptance_commands": as_list(outbox_task.get("acceptance_commands")),
    }


def collect_generation_scheduler(plan: dict[str, Any], run_report: dict[str, Any]) -> dict[str, Any]:
    items = [item for item in as_list(plan.get("items")) if isinstance(item, dict)]
    provider_modes: Counter[str] = Counter()
    for item in items:
        provider_modes[str(as_obj(item.get("provider_policy")).get("mode") or "unknown")] += 1
    return {
        "plan_id": plan.get("plan_id"),
        "schema_version": plan.get("schema_version"),
        "visibility": plan.get("visibility"),
        "summary": as_obj(plan.get("summary")),
        "provider_mode_counts": dict(sorted(provider_modes.items())),
        "run_report": {
            "report_id": run_report.get("report_id"),
            "run_mode": run_report.get("run_mode"),
            "summary": as_obj(run_report.get("summary")),
            "provider_call_count": as_obj(run_report.get("summary")).get("provider_call_count"),
            "world_mutation_count": as_obj(run_report.get("summary")).get("world_mutation_count"),
        },
        "provider_runner_handoff": collect_provider_runner_handoff_summary(),
        "background_executor_tick": collect_scheduler_background_tick_summary(),
        "background_handoff_tick": collect_scheduler_background_handoff_tick_summary(),
        "control_plane_only": as_obj(plan.get("authority")).get("control_plane_only"),
        "calls_provider_during_build": as_obj(plan.get("authority")).get("schedule_builder_calls_provider"),
        "reads_env_during_build": as_obj(plan.get("authority")).get("schedule_builder_reads_env"),
        "items": [
            {
                "schedule_item_id": item.get("schedule_item_id"),
                "object_ref": item.get("object_ref"),
                "object_kind": item.get("object_kind"),
                "latency_class": item.get("latency_class"),
                "status": item.get("status"),
                "priority": item.get("priority"),
                "provider_mode": as_obj(item.get("provider_policy")).get("mode"),
                "world_commit": as_obj(item.get("commit_policy")).get("world_commit"),
                "fallback_ref": item.get("fallback_ref"),
            }
            for item in items
        ],
    }


def collect_generation_executor_run_request(request: dict[str, Any]) -> dict[str, Any]:
    source = as_obj(request.get("source"))
    intent = as_obj(request.get("provider_execution_intent"))
    budget = as_obj(request.get("execution_budget"))
    gates = as_obj(request.get("required_gates"))
    authority = as_obj(request.get("authority"))
    safety = as_obj(request.get("request_builder_safety"))
    return {
        "request_id": request.get("request_id"),
        "schema_version": request.get("schema_version"),
        "source": {
            "run_id": source.get("run_id"),
            "schedule_item_id": source.get("schedule_item_id"),
            "object_kind": source.get("object_kind"),
            "object_ref": source.get("object_ref"),
            "latency_class": source.get("latency_class"),
            "guard_id": source.get("guard_id"),
        },
        "provider_execution_intent": {
            "status": intent.get("status"),
            "provider_mode": intent.get("provider_mode"),
            "provider_profile": intent.get("provider_profile"),
            "authorization_required": intent.get("authorization_required"),
            "authorization_granted": intent.get("authorization_granted"),
            "provider_call_performed_by_request_builder": intent.get(
                "provider_call_performed_by_request_builder"
            ),
        },
        "execution_budget": {
            "attempt_count": budget.get("attempt_count"),
            "max_attempts": budget.get("max_attempts"),
            "remaining_attempts": budget.get("remaining_attempts"),
            "fallback_ref": budget.get("fallback_ref"),
        },
        "input_ref_count": len(as_list(request.get("input_refs"))),
        "context_ref_count": len(as_list(request.get("context_refs"))),
        "required_gate_counts": {
            "before_provider_execution": len(as_list(gates.get("before_provider_execution"))),
            "after_provider_execution": len(as_list(gates.get("after_provider_execution"))),
            "before_activation": len(as_list(gates.get("before_activation"))),
        },
        "evidence_boundary": {
            "review_only": authority.get("review_only"),
            "provider_call_allowed_by_request_builder": authority.get(
                "provider_call_allowed_by_request_builder"
            ),
            "runtime_activation_allowed": authority.get("runtime_activation_allowed"),
            "world_mutation_allowed": authority.get("world_mutation_allowed"),
            "player_visible": authority.get("player_visible"),
            "reads_env": safety.get("reads_env"),
            "calls_provider": safety.get("calls_provider"),
            "writes_world_state": safety.get("writes_world_state"),
            "activates_runtime": safety.get("activates_runtime"),
        },
    }


def collect_provider_execution_authorization(record: dict[str, Any]) -> dict[str, Any]:
    source = as_obj(record.get("source"))
    authorization = as_obj(record.get("authorization"))
    constraints = as_obj(record.get("execution_constraints"))
    authority = as_obj(record.get("authority"))
    safety = as_obj(record.get("authorization_builder_safety"))
    return {
        "authorization_ref": record.get("authorization_ref"),
        "schema_version": record.get("schema_version"),
        "source": {
            "run_id": source.get("run_id"),
            "schedule_item_id": source.get("schedule_item_id"),
            "object_kind": source.get("object_kind"),
            "object_ref": source.get("object_ref"),
            "executor_request_id": source.get("executor_request_id"),
            "guard_id": source.get("guard_id"),
            "provider_mode": source.get("provider_mode"),
            "provider_profile": source.get("provider_profile"),
        },
        "authorization": {
            "status": authorization.get("status"),
            "granted": authorization.get("granted"),
            "scope": authorization.get("scope"),
            "requires_provider_output_envelope": authorization.get(
                "requires_provider_output_envelope"
            ),
        },
        "execution_constraints": {
            "attempt_count": constraints.get("attempt_count"),
            "max_attempts": constraints.get("max_attempts"),
            "remaining_attempts": constraints.get("remaining_attempts"),
            "required_next_gates": as_list(constraints.get("required_next_gates")),
        },
        "evidence_boundary": {
            "review_only": authority.get("review_only"),
            "provider_execution_authorized": authority.get("provider_execution_authorized"),
            "runtime_activation_allowed": authority.get("runtime_activation_allowed"),
            "world_mutation_allowed": authority.get("world_mutation_allowed"),
            "player_visible": authority.get("player_visible"),
            "reads_env": safety.get("reads_env"),
            "calls_provider": safety.get("calls_provider"),
            "writes_world_state": safety.get("writes_world_state"),
            "activates_runtime": safety.get("activates_runtime"),
        },
    }


def collect_provider_adapter_execution_receipt(record: dict[str, Any]) -> dict[str, Any]:
    source = as_obj(record.get("source"))
    execution = as_obj(record.get("execution"))
    contract = as_obj(record.get("output_contract"))
    authority = as_obj(record.get("authority"))
    safety = as_obj(record.get("adapter_safety"))
    return {
        "execution_receipt_id": record.get("execution_receipt_id"),
        "schema_version": record.get("schema_version"),
        "source": {
            "run_id": source.get("run_id"),
            "schedule_item_id": source.get("schedule_item_id"),
            "object_kind": source.get("object_kind"),
            "object_ref": source.get("object_ref"),
            "executor_request_id": source.get("executor_request_id"),
            "authorization_ref": source.get("authorization_ref"),
            "guard_id": source.get("guard_id"),
            "provider_mode": source.get("provider_mode"),
            "provider_profile": source.get("provider_profile"),
        },
        "execution": {
            "status": execution.get("status"),
            "mode": execution.get("mode"),
            "authorization_ref": execution.get("authorization_ref"),
            "provider_call_performed_by_receipt_builder": execution.get(
                "provider_call_performed_by_receipt_builder"
            ),
            "requires_provider_output_envelope": execution.get(
                "requires_provider_output_envelope"
            ),
            "finish_reason": execution.get("finish_reason"),
        },
        "output_contract": {
            "must_write_provider_output_envelope": contract.get(
                "must_write_provider_output_envelope"
            ),
            "allowed_result_storage": contract.get("allowed_result_storage"),
            "temporary_url_policy": contract.get("temporary_url_policy"),
            "required_next_gates": as_list(contract.get("required_next_gates")),
        },
        "evidence_boundary": {
            "review_only": authority.get("review_only"),
            "provider_adapter_boundary_entered": authority.get(
                "provider_adapter_boundary_entered"
            ),
            "runtime_activation_allowed": authority.get("runtime_activation_allowed"),
            "world_mutation_allowed": authority.get("world_mutation_allowed"),
            "player_visible": authority.get("player_visible"),
            "reads_env": safety.get("reads_env"),
            "calls_provider": safety.get("calls_provider"),
            "writes_world_state": safety.get("writes_world_state"),
            "activates_runtime": safety.get("activates_runtime"),
        },
    }


def collect_provider_adapter_runner(
    request: dict[str, Any],
    receipt: dict[str, Any],
    envelope: dict[str, Any],
) -> dict[str, Any]:
    request_source = as_obj(request.get("source"))
    receipt_execution = as_obj(receipt.get("execution"))
    envelope_call = as_obj(envelope.get("provider_call"))
    envelope_result = as_obj(envelope.get("redacted_result_summary"))
    envelope_manifest = as_obj(envelope.get("artifact_manifest"))
    envelope_activation = as_obj(envelope.get("activation_gate"))
    return {
        "mode": "deterministic_dry_run_example",
        "request": {
            "request_id": request.get("request_id"),
            "schedule_item_id": request_source.get("schedule_item_id"),
            "object_kind": request_source.get("object_kind"),
            "object_ref": request_source.get("object_ref"),
        },
        "receipt": {
            "execution_receipt_id": receipt.get("execution_receipt_id"),
            "status": receipt_execution.get("status"),
            "mode": receipt_execution.get("mode"),
            "authorization_ref": receipt_execution.get("authorization_ref"),
            "provider_call_performed_by_receipt_builder": receipt_execution.get(
                "provider_call_performed_by_receipt_builder"
            ),
        },
        "envelope": {
            "envelope_id": envelope.get("envelope_id"),
            "provider_call_status": envelope_call.get("status"),
            "provider_call_performed": envelope_call.get("performed"),
            "authorization_granted": envelope_call.get("authorization_granted"),
            "result_status": envelope_result.get("status"),
            "result_kind": envelope_result.get("result_kind"),
            "artifact_manifest_status": envelope_manifest.get("status"),
            "output_ref_count": len(as_list(envelope_manifest.get("output_refs"))),
            "activation_allowed": envelope_activation.get("activation_allowed"),
            "blocked_reason": envelope_activation.get("blocked_reason"),
        },
        "safety": {
            "reads_env": False,
            "calls_external_services": False,
            "stores_prompt_body": False,
            "stores_provider_body": False,
            "writes_world_state": False,
            "activates_runtime": False,
        },
    }


def collect_provider_artifact_staging(
    manifest: dict[str, Any],
    source_envelope: dict[str, Any],
) -> dict[str, Any]:
    staged_artifacts = as_list(manifest.get("staged_artifacts"))
    validation = as_obj(manifest.get("validation_results"))
    promotion = as_obj(manifest.get("promotion_gate"))
    source_call = as_obj(source_envelope.get("provider_call"))
    source_result = as_obj(source_envelope.get("redacted_result_summary"))
    source_artifact_manifest = as_obj(source_envelope.get("artifact_manifest"))
    source_output_refs = as_list(source_artifact_manifest.get("output_refs"))
    gate_statuses = {
        name: as_obj(gate).get("status")
        for name, gate in validation.items()
        if isinstance(gate, dict)
    }
    authority = as_obj(manifest.get("authority"))
    return {
        "manifest_id": manifest.get("manifest_id"),
        "schema_version": manifest.get("schema_version"),
        "source_envelope_id": manifest.get("source_envelope_id"),
        "source_envelope_ref": manifest.get("source_envelope_ref"),
        "staging_status": manifest.get("staging_status"),
        "staged_artifact_count": len(staged_artifacts),
        "staged_artifacts": [
            {
                "artifact_id": artifact.get("artifact_id"),
                "source_artifact_id": artifact.get("source_artifact_id"),
                "kind": artifact.get("kind"),
                "path": artifact.get("path"),
                "media_layer": artifact.get("media_layer"),
                "review_status": artifact.get("review_status"),
                "runtime_visible": artifact.get("runtime_visible"),
                "player_visible": artifact.get("player_visible"),
            }
            for artifact in staged_artifacts
            if isinstance(artifact, dict)
        ],
        "source": {
            "provider_call_status": source_call.get("status"),
            "provider_call_performed": source_call.get("performed"),
            "authorization_granted": source_call.get("authorization_granted"),
            "result_kind": source_result.get("result_kind"),
            "result_status": source_result.get("status"),
            "source_output_ref_count": len(source_output_refs),
        },
        "gate_statuses": gate_statuses,
        "promotion_gate": {
            "promotion_allowed": promotion.get("promotion_allowed"),
            "blocked_reason": promotion.get("blocked_reason"),
            "required_next_gates": as_list(promotion.get("required_next_gates")),
        },
        "evidence_boundary": {
            "review_only": authority.get("review_only"),
            "runtime_activation_allowed": authority.get("runtime_activation_allowed"),
            "world_mutation_allowed": authority.get("world_mutation_allowed"),
            "player_visible": authority.get("player_visible"),
        },
    }


def collect_provider_artifact_promotion_report(report: dict[str, Any]) -> dict[str, Any]:
    decision = as_obj(report.get("decision"))
    targets = as_obj(report.get("promotion_targets"))
    safety = as_obj(report.get("safety_summary"))
    gates = as_obj(report.get("gate_results"))
    safe_safety_summary = {
        "provider_call_count_by_report": safety.get("provider_call_count_by_report"),
        "world_mutation_count_by_report": safety.get("world_mutation_count_by_report"),
        "runtime_mutation_count_by_report": safety.get("runtime_mutation_count_by_report"),
        "stores_prompt_body": safety.get("stores_prompt_body"),
        "stores_provider_body": safety.get("stores_provider_body"),
        "stores_sensitive_value": safety.get("stores_secret"),
        "uses_temporary_url": safety.get("uses_temporary_url"),
    }
    return {
        "report_id": report.get("report_id"),
        "schema_version": report.get("schema_version"),
        "source_staging_id": report.get("source_staging_id"),
        "source_staging_ref": report.get("source_staging_ref"),
        "promotion_decision": decision.get("promotion_decision"),
        "promotion_allowed": decision.get("promotion_allowed"),
        "blocked_reason": decision.get("blocked_reason"),
        "required_next_actions": as_list(decision.get("required_next_actions")),
        "reviewed_artifact_count": len(as_list(report.get("reviewed_artifacts"))),
        "gate_statuses": {
            gate_name: as_obj(gate).get("status")
            for gate_name, gate in gates.items()
            if isinstance(gate, dict)
        },
        "promotion_targets": {
            "target_kind": targets.get("target_kind"),
            "runtime_package_ref_count": len(as_list(targets.get("runtime_package_refs"))),
            "world_transaction_ref_count": len(as_list(targets.get("world_transaction_refs"))),
            "published_media_ref_count": len(as_list(targets.get("published_media_refs"))),
        },
        "safety_summary": safe_safety_summary,
    }


def collect_core_artifact_alignment_report(report: dict[str, Any]) -> dict[str, Any]:
    summary = as_obj(report.get("summary"))
    targets = as_list(report.get("target_reports"))
    migration_tasks = as_list(report.get("migration_tasks"))
    sample_targets = [
        {
            "target_id": target.get("target_id"),
            "target_kind": target.get("target_kind"),
            "alignment_state": target.get("alignment_state"),
            "present_artifacts": as_list(target.get("present_artifacts")),
            "next_action": target.get("next_action"),
        }
        for target in targets
        if isinstance(target, dict)
        and target.get("alignment_state") in {"missing_core_alignment", "refs_only"}
    ][:MAX_SAMPLE_ITEMS]
    return {
        "report_id": report.get("report_id"),
        "schema_version": report.get("schema_version"),
        "overall_status": summary.get("overall_status"),
        "target_count": summary.get("target_count"),
        "status_counts": as_obj(summary.get("status_counts")),
        "native_snapshot_ready_count": summary.get("native_snapshot_ready_count"),
        "refs_only_count": summary.get("refs_only_count"),
        "missing_core_alignment_count": summary.get("missing_core_alignment_count"),
        "validation_failed_count": summary.get("validation_failed_count"),
        "review_only_not_applicable_count": summary.get("review_only_not_applicable_count"),
        "migration_task_count": len(migration_tasks),
        "sample_migration_targets": sample_targets,
        "safety_summary": as_obj(report.get("safety_summary")),
    }


def collect_mvp_demo_readiness_report(report: dict[str, Any]) -> dict[str, Any]:
    summary = as_obj(report.get("summary"))
    gates = [
        {
            "gate_id": gate.get("gate_id"),
            "title": gate.get("title"),
            "status": gate.get("status"),
            "required_for_mvp_demo": gate.get("required_for_mvp_demo"),
            "summary": gate.get("summary"),
            "metrics": as_obj(gate.get("metrics")),
        }
        for gate in as_list(report.get("gates"))
        if isinstance(gate, dict)
    ]
    limitations = [
        {
            "limitation_id": item.get("limitation_id"),
            "severity": item.get("severity"),
            "summary": item.get("summary"),
        }
        for item in as_list(report.get("known_limitations"))
        if isinstance(item, dict)
    ]
    return {
        "report_id": report.get("report_id"),
        "schema_version": report.get("schema_version"),
        "overall_status": report.get("overall_status"),
        "summary": {
            "required_gate_count": summary.get("required_gate_count"),
            "required_gate_passed_or_expected_count": summary.get(
                "required_gate_passed_or_expected_count"
            ),
            "blocking_gate_count": summary.get("blocking_gate_count"),
            "warning_gate_count": summary.get("warning_gate_count"),
            "expected_block_count": summary.get("expected_block_count"),
            "evidence_source_count": summary.get("evidence_source_count"),
            "provider_call_count_by_report": summary.get(
                "provider_call_count_by_report"
            ),
            "world_mutation_count_by_report": summary.get(
                "world_mutation_count_by_report"
            ),
            "runtime_mutation_count_by_report": summary.get(
                "runtime_mutation_count_by_report"
            ),
        },
        "demo_claim": as_obj(report.get("demo_claim")),
        "gates": gates,
        "known_limitations": limitations,
        "recommended_next_actions": as_list(report.get("recommended_next_actions")),
        "safety_summary": as_obj(report.get("safety_summary")),
    }


def collect_frontend_flow_visual_smoke_report(
    report: dict[str, Any],
    report_path: Path,
) -> dict[str, Any]:
    screenshots = [
        {
            "viewport_id": item.get("viewport_id"),
            "step_id": item.get("step_id"),
            "label": item.get("label"),
            "path": item.get("path"),
            "width": item.get("width"),
            "height": item.get("height"),
            "file_size_bytes": item.get("file_size_bytes"),
            "sha256": item.get("sha256"),
            "title": item.get("title"),
            "canvas_count": item.get("canvas_count"),
            "button_count": item.get("button_count"),
            "image_count": item.get("image_count"),
        }
        for item in as_list(report.get("screenshots"))
        if isinstance(item, dict)
    ]
    viewport_results = as_list(report.get("viewport_results"))
    return {
        "schema_version": report.get("schema_version"),
        "task_id": report.get("task_id"),
        "status": report.get("status"),
        "report_ref": external_file_ref(report_path, "frontend_flow_visual_smoke_report"),
        "browser_available": report.get("browser_available"),
        "browser_executable": report.get("browser_executable"),
        "viewport_count": report.get("viewport_count"),
        "step_ids": as_list(report.get("step_ids")),
        "expected_screenshot_count": report.get("expected_screenshot_count"),
        "captured_screenshot_count": report.get("captured_screenshot_count"),
        "viewport_status_counts": dict(
            sorted(Counter(str(item.get("status")) for item in viewport_results if isinstance(item, dict)).items())
        ),
        "screenshots": screenshots,
        "screenshot_matrix": [
            f"{item.get('viewport_id')}:{item.get('step_id')}"
            for item in screenshots
        ],
        "failure_count": len(as_list(report.get("failures"))),
        "smoke_mode": as_obj(report.get("smoke_mode")),
        "safety_summary": as_obj(report.get("safety_summary")),
    }


def collect_browser_visual_evidence(
    frontend_flow_visual_smoke_report_path: Path | None,
) -> dict[str, Any]:
    if not frontend_flow_visual_smoke_report_path:
        return {
            "frontend_flow": {
                "status": "not_provided",
                "expected_command": (
                    "python3 tools/frontend/capture_frontend_flow_visual_smoke.py "
                    "--output-dir /tmp/frontend_flow_visual_smoke --timeout 45"
                ),
                "validation_command": (
                    "python3 tools/frontend/validate_frontend_flow_visual_smoke_report.py "
                    "/tmp/frontend_flow_visual_smoke/frontend_flow_visual_smoke_report.v0.1.json"
                ),
            }
        }
    return {
        "frontend_flow": collect_frontend_flow_visual_smoke_report(
            load_json(frontend_flow_visual_smoke_report_path),
            frontend_flow_visual_smoke_report_path,
        )
    }


def collect_world_delta_transaction(transaction: dict[str, Any]) -> dict[str, Any]:
    delta_ref = as_obj(transaction.get("world_state_delta_ref"))
    report = as_obj(transaction.get("validation_report"))
    scope = as_obj(transaction.get("scope"))
    rollback = as_obj(transaction.get("rollback_policy"))
    conflict = as_obj(transaction.get("conflict_policy"))
    return {
        "schema_version": transaction.get("schema_version"),
        "transaction_id": transaction.get("transaction_id"),
        "status": transaction.get("status"),
        "run_id": transaction.get("run_id"),
        "worldbook_id": transaction.get("worldbook_id"),
        "source": transaction.get("source"),
        "actor": transaction.get("actor"),
        "delta_id": delta_ref.get("delta_id"),
        "delta_path": delta_ref.get("path"),
        "scope_kind": scope.get("kind"),
        "node_ids": as_list(scope.get("node_ids")),
        "operation_mapping_count": len(as_list(transaction.get("operation_effects_mapping"))),
        "conflict_policy": conflict.get("mode"),
        "rollback_policy": rollback.get("mode"),
        "validation_report": {
            "gate_status": report.get("gate_status"),
            "world_delta_structure": report.get("world_delta_structure"),
            "world_delta_semantics": report.get("world_delta_semantics"),
            "operation_mapping": report.get("operation_mapping"),
            "runtime_apply_checked": report.get("runtime_apply_checked"),
        },
    }


def collect_world_delta_transaction_chain(
    transactions: list[dict[str, Any]],
) -> dict[str, Any]:
    summaries = [collect_world_delta_transaction(transaction) for transaction in transactions]
    statuses = Counter(str(item.get("status")) for item in summaries)
    sources = Counter(str(item.get("source")) for item in summaries)
    scope_kinds = Counter(str(item.get("scope_kind")) for item in summaries)
    return {
        "transaction_count": len(summaries),
        "status_counts": dict(sorted(statuses.items())),
        "source_counts": dict(sorted(sources.items())),
        "scope_kind_counts": dict(sorted(scope_kinds.items())),
        "total_operation_mapping_count": sum(
            int(item.get("operation_mapping_count") or 0) for item in summaries
        ),
        "transaction_ids": [item.get("transaction_id") for item in summaries],
        "transactions": summaries,
    }


def collect_assets_and_media(
    frontend_pack: dict[str, Any],
    frontend_media_manifest: dict[str, Any],
    frontend_media_atlas_manifest: dict[str, Any],
    frontend_loop_continuity_report: dict[str, Any],
    frontend_sprite_quality_report: dict[str, Any],
    frontend_sprite_repair_plan: dict[str, Any],
    frontend_sprite_repair_candidates: dict[str, Any],
    frontend_sprite_repair_candidate_quality_report: dict[str, Any],
    runtime_art_kit: dict[str, Any],
    runtime_art_media_manifest: dict[str, Any],
    runtime_art_atlas_manifest: dict[str, Any],
    runtime_loop_continuity_report: dict[str, Any],
    runtime_sprite_quality_report: dict[str, Any],
    runtime_sprite_repair_plan: dict[str, Any],
    runtime_sprite_repair_candidates: dict[str, Any],
    runtime_sprite_repair_candidate_quality_report: dict[str, Any],
    runtime_sprite_regeneration_candidates: dict[str, Any],
    runtime_sprite_regeneration_candidate_quality_report: dict[str, Any],
    runtime_sprite_regeneration_promotion_report: dict[str, Any],
    map_visual_manifest: dict[str, Any],
    map_visual_quality_report: dict[str, Any],
    map_visual_promotion_gate_report: dict[str, Any],
    node_map_candidate_review: dict[str, Any],
    map_candidate_alignment_review: dict[str, Any],
    map_candidate_overlay_review: dict[str, Any],
    map_candidate_overlay_visual_review: dict[str, Any],
    map_layout_reconciliation_plan: dict[str, Any],
    runtime_map_patch_candidates: dict[str, Any],
    map_patch_overlay_review: dict[str, Any],
    topology_constrained_map_prompt_pack: dict[str, Any],
    topology_constrained_map_candidate_review: dict[str, Any],
    topology_constrained_map_alignment_review: dict[str, Any],
    topology_constrained_map_overlay_review: dict[str, Any],
    topology_constrained_map_overlay_visual_review: dict[str, Any],
    map_topology_control_sketch_pack: dict[str, Any],
    map_controlled_regeneration_request_pack: dict[str, Any],
    controlled_map_candidate_generation_run: dict[str, Any],
    controlled_map_candidate_review: dict[str, Any],
    controlled_map_text_fallback_generation_run: dict[str, Any],
    controlled_map_text_fallback_candidate_review: dict[str, Any],
    procedural_map_preview_reports: list[dict[str, Any]],
    procedural_map_preview_v02_reports: list[dict[str, Any]],
) -> dict[str, Any]:
    assets = [asset for asset in as_list(frontend_pack.get("assets")) if isinstance(asset, dict)]
    compiler_summary = as_obj(frontend_pack.get("compiler_summary"))
    core_artifacts = as_obj(frontend_pack.get("core_artifacts"))
    runtime_art_assets = as_list(runtime_art_kit.get("art_assets"))
    map_tokens = as_list(runtime_art_kit.get("map_tokens"))
    procedural_effects = as_list(runtime_art_kit.get("procedural_effects"))
    map_visual_items = as_list(map_visual_manifest.get("items"))
    return {
        "frontend_pack": {
            "pack_id": frontend_pack.get("pack_id"),
            "worldbook_id": frontend_pack.get("worldbook_id"),
            "asset_count": len(assets),
            "playable_count": compiler_summary.get("playable_count"),
            "asset_count_by_type": as_obj(compiler_summary.get("asset_count_by_type")),
            "promotion_states": as_obj(compiler_summary.get("promotion_states")),
            "core_artifacts": {
                "status": core_artifacts.get("status"),
                "review_only": core_artifacts.get("review_only"),
                "ref_count": len(as_obj(core_artifacts.get("refs"))),
                "schema_versions": {
                    key: as_obj(core_artifacts.get(key)).get("schema_version")
                    for key in (
                        "context_package",
                        "fact_entry",
                        "compiled_game_object_package",
                        "world_delta_transaction",
                    )
                },
            },
            "asset_samples": [safe_asset_summary(asset) for asset in assets[:MAX_SAMPLE_ITEMS]],
        },
        "published_asset_media": media_manifest_summary(frontend_media_manifest),
        "published_asset_atlas": atlas_manifest_summary(frontend_media_atlas_manifest),
        "published_asset_loop_continuity": loop_continuity_summary(
            frontend_loop_continuity_report
        ),
        "published_sprite_cutout_quality": sprite_cutout_quality_summary(frontend_sprite_quality_report),
        "published_sprite_repair_plan": sprite_repair_plan_summary(frontend_sprite_repair_plan),
        "published_sprite_repair_candidates": sprite_repair_candidate_summary(
            frontend_sprite_repair_candidates,
            frontend_sprite_repair_candidate_quality_report,
        ),
        "runtime_art": {
            "kit_id": runtime_art_kit.get("kit_id"),
            "mode": runtime_art_kit.get("mode"),
            "art_asset_count": len(runtime_art_assets),
            "map_token_count": len(map_tokens),
            "procedural_effect_count": len(procedural_effects),
            "art_asset_types": count_by(runtime_art_assets, "asset_kind"),
            "procedural_effect_ids": [
                effect.get("effect_id")
                for effect in procedural_effects
                if isinstance(effect, dict)
            ],
            "media_manifest": media_manifest_summary(runtime_art_media_manifest),
            "atlas_manifest": atlas_manifest_summary(runtime_art_atlas_manifest),
            "loop_continuity": loop_continuity_summary(runtime_loop_continuity_report),
            "sprite_cutout_quality": sprite_cutout_quality_summary(runtime_sprite_quality_report),
            "sprite_repair_plan": sprite_repair_plan_summary(runtime_sprite_repair_plan),
            "sprite_repair_candidates": sprite_repair_candidate_summary(
                runtime_sprite_repair_candidates,
                runtime_sprite_repair_candidate_quality_report,
            ),
            "sprite_regeneration_candidates": sprite_repair_candidate_summary(
                runtime_sprite_regeneration_candidates,
                runtime_sprite_regeneration_candidate_quality_report,
            ),
            "sprite_regeneration_promotion": sprite_regeneration_promotion_summary(
                runtime_sprite_regeneration_promotion_report
            ),
        },
        "map_visual_reference": {
            "pack_id": map_visual_manifest.get("pack_id"),
            "schema_version": map_visual_manifest.get("schema_version"),
            "item_count": len(map_visual_items),
            "quality_audit": map_visual_quality_summary(map_visual_quality_report),
            "promotion_gate": map_visual_promotion_gate_summary(
                map_visual_promotion_gate_report
            ),
            "candidate_review": node_map_candidate_review_summary(node_map_candidate_review),
            "alignment_review": map_candidate_alignment_summary(map_candidate_alignment_review),
            "overlay_review": map_candidate_overlay_summary(map_candidate_overlay_review),
            "overlay_visual_review": map_candidate_overlay_visual_summary(
                map_candidate_overlay_visual_review
            ),
            "layout_reconciliation_plan": map_layout_reconciliation_summary(
                map_layout_reconciliation_plan
            ),
            "runtime_patch_candidates": runtime_map_patch_candidate_summary(
                runtime_map_patch_candidates
            ),
            "patch_overlay_review": map_patch_overlay_review_summary(
                map_patch_overlay_review
            ),
            "topology_prompt_pack": topology_constrained_prompt_pack_summary(
                topology_constrained_map_prompt_pack
            ),
            "topology_candidate_review": node_map_candidate_review_summary(
                topology_constrained_map_candidate_review
            ),
            "topology_alignment_review": map_candidate_alignment_summary(
                topology_constrained_map_alignment_review
            ),
            "topology_overlay_review": map_candidate_overlay_summary(
                topology_constrained_map_overlay_review
            ),
            "topology_overlay_visual_review": map_candidate_overlay_visual_summary(
                topology_constrained_map_overlay_visual_review
            ),
            "topology_control_sketch_pack": map_topology_control_sketch_pack_summary(
                map_topology_control_sketch_pack
            ),
            "procedural_map_previews": procedural_map_preview_summary(
                procedural_map_preview_reports
            ),
            "procedural_map_previews_v02": procedural_map_preview_summary(
                procedural_map_preview_v02_reports
            ),
            "controlled_regeneration_request_pack": map_controlled_regeneration_request_pack_summary(
                map_controlled_regeneration_request_pack
            ),
            "controlled_candidate_generation_run": controlled_map_candidate_generation_summary(
                controlled_map_candidate_generation_run
            ),
            "controlled_candidate_review": node_map_candidate_review_summary(
                controlled_map_candidate_review
            ),
            "controlled_text_fallback_generation_run": controlled_map_candidate_generation_summary(
                controlled_map_text_fallback_generation_run
            ),
            "controlled_text_fallback_candidate_review": node_map_candidate_review_summary(
                controlled_map_text_fallback_candidate_review
            ),
            "published_visual_layers": [
                {
                    "role": item.get("role"),
                    "authority": item.get("authority"),
                    "url": item.get("url"),
                    "local_path": item.get("local_path"),
                    "width": item.get("width"),
                    "height": item.get("height"),
                    "sha256": item.get("sha256"),
                }
                for item in map_visual_items
                if isinstance(item, dict)
            ],
        },
    }


def collect_frontend_entry(frontend_pack: dict[str, Any]) -> dict[str, Any]:
    contract = as_obj(frontend_pack.get("frontend_contract"))
    return {
        "current_mode": "FastAPI fixture-backed mock API + 浏览器前端静态入口。",
        "local_frontend_entry": "frontend/index.html",
        "backend_entry": "backend/app/api/frontend_mock.py",
        "primary_flow": as_list(contract.get("primary_flow")),
        "first_screen": contract.get("first_screen"),
        "runtime_assumption": contract.get("runtime_assumption"),
        "api_entrypoints": [
            "POST /api/sessions",
            "POST /api/sessions/{session_id}/world-instance",
            "GET /api/sessions/{session_id}/frontend-mock-pack",
            "GET /api/sessions/{session_id}/runtime-art-kit",
            "GET /api/sessions/{session_id}/map",
            "GET /api/sessions/{session_id}/nodes/{node_id}/briefing",
            "GET /api/sessions/{session_id}/battles/{node_id}/config",
            "GET /api/sessions/{session_id}/battles/{node_id}/runtime-package",
            "GET /api/sessions/{session_id}/battles/{node_id}/map-runtime-package",
            "POST /api/sessions/{session_id}/battles/{node_id}/results",
            "GET /api/sessions/{session_id}/settlement/latest",
            "GET /api/sessions/{session_id}/evidence",
        ],
        "static_media_mounts": [
            "/assets/frontend_mock/processed",
            "/assets/frontend_mock/generated",
            "/assets/frontend_mock/atlas_frames",
            "/assets/frontend_mock/atlas_sheets",
            "/assets/frontend_runtime_mock/processed",
            "/assets/frontend_runtime_mock/generated",
            "/assets/frontend_runtime_mock/atlas_frames",
            "/assets/frontend_runtime_mock/atlas_sheets",
            "/assets/map_visual_reference",
        ],
        "player_safe_boundary": {
            "frontend_contract_avoids_internal_terms": True,
            "evidence_bundle_is_review_surface": True,
            "internal_generation_details_are_summarized_only": True,
        },
    }


def collect_validation_summary(
    validation_results: list[dict[str, Any]],
    audit_report: dict[str, Any],
    dossier: dict[str, Any],
    map_packages: list[dict[str, Any]],
    map_compile_packages: list[dict[str, Any]],
) -> dict[str, Any]:
    command_results = as_list(audit_report.get("command_results"))
    coverage_checks = as_list(audit_report.get("coverage_checks"))
    known_risks = as_list(audit_report.get("known_risks"))
    all_passed = all(result.get("status") == "passed" for result in validation_results)
    return {
        "current_export_validation": {
            "status": "passed" if all_passed else "failed",
            "command_count": len(validation_results),
            "results": validation_results,
        },
        "handoff_audit_report": {
            "report_id": audit_report.get("report_id"),
            "overall_status": audit_report.get("overall_status"),
            "recorded_command_count": len(command_results),
            "coverage_check_count": len(coverage_checks),
            "known_risk_count": len(known_risks),
        },
        "compiler_review_dossier": {
            "dossier_id": dossier.get("dossier_id"),
            "visibility": dossier.get("visibility"),
            "readiness_summary": as_obj(dossier.get("readiness_summary")),
            "known_risk_count": len(as_list(dossier.get("known_risks"))),
        },
        "map_runtime_validation_reports": [
            {
                "package_id": package.get("package_id"),
                "node_id": package.get("node_id"),
                "validation_report": as_obj(package.get("validation_report")),
            }
            for package in map_packages
        ],
        "map_compile_validation_reports": [
            {
                "package_id": package.get("package_id"),
                "node_id": package.get("node_id"),
                "validation_report": as_obj(package.get("validation_report")),
            }
            for package in map_compile_packages
        ],
    }


def collect_source_files() -> list[dict[str, Any]]:
    source_paths = [
        ("project_entry", PATHS["readme"]),
        ("architecture_fact_index", PATHS["architecture_index"]),
        ("ai_compilation_design", PATHS["ai_compilation_doc"]),
        ("asset_graph_design", PATHS["asset_graph_doc"]),
        ("generation_scheduler_design", PATHS["generation_scheduler_doc"]),
        ("frontend_mock_api_design", PATHS["frontend_mock_api_doc"]),
        ("frontend_runtime_art_design", PATHS["frontend_runtime_art_doc"]),
        ("core_artifact_alignment_design", PATHS["core_artifact_alignment_doc"]),
        ("demo_vertical_slice", PATHS["demo_vertical_slice_doc"]),
        ("frontend_mock_pack", PATHS["frontend_mock_pack"]),
        ("runtime_art_kit", PATHS["runtime_art_kit"]),
        ("runtime_package", PATHS["runtime_package"]),
        ("frontend_media_manifest", PATHS["frontend_media_manifest"]),
        ("frontend_media_atlas_manifest", PATHS["frontend_media_atlas_manifest"]),
        ("frontend_loop_continuity_report", PATHS["frontend_loop_continuity_report"]),
        ("runtime_art_media_manifest", PATHS["runtime_art_media_manifest"]),
        ("runtime_art_atlas_manifest", PATHS["runtime_art_atlas_manifest"]),
        ("runtime_loop_continuity_report", PATHS["runtime_loop_continuity_report"]),
        ("frontend_sprite_cutout_quality_report", PATHS["frontend_sprite_cutout_quality_report"]),
        ("runtime_sprite_cutout_quality_report", PATHS["runtime_sprite_cutout_quality_report"]),
        ("frontend_sprite_cutout_repair_plan", PATHS["frontend_sprite_cutout_repair_plan"]),
        ("runtime_sprite_cutout_repair_plan", PATHS["runtime_sprite_cutout_repair_plan"]),
        ("frontend_sprite_repair_candidates", PATHS["frontend_sprite_repair_candidates"]),
        ("runtime_sprite_repair_candidates", PATHS["runtime_sprite_repair_candidates"]),
        (
            "frontend_sprite_repair_candidate_quality_report",
            PATHS["frontend_sprite_repair_candidate_quality_report"],
        ),
        (
            "runtime_sprite_repair_candidate_quality_report",
            PATHS["runtime_sprite_repair_candidate_quality_report"],
        ),
        ("runtime_sprite_regeneration_candidates", PATHS["runtime_sprite_regeneration_candidates"]),
        (
            "runtime_sprite_regeneration_candidate_quality_report",
            PATHS["runtime_sprite_regeneration_candidate_quality_report"],
        ),
        (
            "runtime_sprite_regeneration_promotion_report",
            PATHS["runtime_sprite_regeneration_promotion_report"],
        ),
        ("generation_schedule_plan", PATHS["generation_schedule_plan"]),
        ("generation_schedule_run_report", PATHS["generation_schedule_run_report"]),
        (
            "generation_executor_run_request",
            PATHS["generation_executor_run_request"],
        ),
        (
            "provider_execution_authorization",
            PATHS["provider_execution_authorization"],
        ),
        (
            "provider_adapter_execution_receipt",
            PATHS["provider_adapter_execution_receipt"],
        ),
        (
            "provider_adapter_runner_executor_request",
            PATHS["provider_adapter_runner_executor_request"],
        ),
        (
            "provider_adapter_runner_receipt",
            PATHS["provider_adapter_runner_receipt"],
        ),
        (
            "provider_adapter_runner_envelope",
            PATHS["provider_adapter_runner_envelope"],
        ),
        (
            "provider_adapter_image_runner_executor_request",
            PATHS["provider_adapter_image_runner_executor_request"],
        ),
        (
            "provider_adapter_image_runner_authorization",
            PATHS["provider_adapter_image_runner_authorization"],
        ),
        (
            "provider_adapter_image_runner_receipt",
            PATHS["provider_adapter_image_runner_receipt"],
        ),
        (
            "provider_adapter_image_runner_envelope",
            PATHS["provider_adapter_image_runner_envelope"],
        ),
        (
            "provider_artifact_staging_manifest",
            PATHS["provider_artifact_staging_manifest"],
        ),
        (
            "provider_artifact_staging_source_envelope",
            PATHS["provider_artifact_staging_source_envelope"],
        ),
        (
            "provider_artifact_staging_candidate_summary",
            PATHS["provider_artifact_staging_candidate_summary"],
        ),
        (
            "provider_artifact_promotion_report",
            PATHS["provider_artifact_promotion_report"],
        ),
        (
            "provider_artifact_promotion_negative_fixture",
            PATHS["provider_artifact_promotion_negative_fixture"],
        ),
        (
            "provider_image_artifact_staging_manifest",
            PATHS["provider_image_artifact_staging_manifest"],
        ),
        (
            "provider_image_artifact_staging_source_envelope",
            PATHS["provider_image_artifact_staging_source_envelope"],
        ),
        (
            "provider_image_artifact_promotion_report",
            PATHS["provider_image_artifact_promotion_report"],
        ),
        (
            "core_artifact_alignment_report",
            PATHS["core_artifact_alignment_report"],
        ),
        (
            "mvp_primary_api_flow_smoke_report",
            PATHS["mvp_primary_api_flow_smoke_report"],
        ),
        (
            "map_v02_preview_api_smoke_report",
            PATHS["map_v02_preview_api_smoke_report"],
        ),
        (
            "mvp_demo_readiness_report",
            PATHS["mvp_demo_readiness_report"],
        ),
        ("context_package_example", PATHS["context_package_example"]),
        ("fact_entry_example", PATHS["fact_entry_example"]),
        ("cgop_example", PATHS["cgop_example"]),
        ("world_delta_transaction_example", PATHS["world_delta_transaction_example"]),
        ("map_visual_manifest", PATHS["map_visual_manifest"]),
        ("map_visual_quality_report", PATHS["map_visual_quality_report"]),
        (
            "map_visual_promotion_gate_report",
            PATHS["map_visual_promotion_gate_report"],
        ),
        (
            "map_runtime_promotion_readiness_report",
            PATHS["map_runtime_promotion_readiness_report"],
        ),
        (
            "map_runtime_activation_gate_report",
            PATHS["map_runtime_activation_gate_report"],
        ),
        ("map_path_geometry_report", PATHS["map_path_geometry_report"]),
        ("map_component_media_manifest", PATHS["map_component_media_manifest"]),
        (
            "map_component_media_manifest_v02_preview",
            PATHS["map_component_media_manifest_v02"],
        ),
        (
            "map_style_component_binding_report",
            PATHS["map_style_component_binding_report"],
        ),
        (
            "map_component_generation_request_pack",
            PATHS["map_component_generation_request_pack"],
        ),
        (
            "map_component_artifact_staging_manifest",
            PATHS["map_component_artifact_staging_manifest"],
        ),
        (
            "map_component_candidate_review_report",
            PATHS["map_component_candidate_review_report"],
        ),
        (
            "map_component_visual_quality_report",
            PATHS["map_component_visual_quality_report"],
        ),
        (
            "map_component_promotion_gate_report",
            PATHS["map_component_promotion_gate_report"],
        ),
        (
            "map_component_manifest_patch_plan",
            PATHS["map_component_manifest_patch_plan"],
        ),
        (
            "map_component_manifest_apply_report",
            PATHS["map_component_manifest_apply_report"],
        ),
        ("node_map_candidate_review", PATHS["node_map_candidate_review"]),
        ("map_candidate_alignment_review", PATHS["map_candidate_alignment_review"]),
        ("map_candidate_overlay_review", PATHS["map_candidate_overlay_review"]),
        ("map_candidate_overlay_visual_review", PATHS["map_candidate_overlay_visual_review"]),
        ("map_layout_reconciliation_plan", PATHS["map_layout_reconciliation_plan"]),
        ("runtime_map_patch_candidates", PATHS["runtime_map_patch_candidates"]),
        ("map_patch_overlay_review", PATHS["map_patch_overlay_review"]),
        (
            "topology_constrained_map_prompt_pack",
            PATHS["topology_constrained_map_prompt_pack"],
        ),
        (
            "topology_constrained_map_candidate_review",
            PATHS["topology_constrained_map_candidate_review"],
        ),
        (
            "topology_constrained_map_alignment_review",
            PATHS["topology_constrained_map_alignment_review"],
        ),
        (
            "topology_constrained_map_overlay_review",
            PATHS["topology_constrained_map_overlay_review"],
        ),
        (
            "topology_constrained_map_overlay_visual_review",
            PATHS["topology_constrained_map_overlay_visual_review"],
        ),
        (
            "map_topology_control_sketch_pack",
            PATHS["map_topology_control_sketch_pack"],
        ),
        (
            "map_controlled_regeneration_request_pack",
            PATHS["map_controlled_regeneration_request_pack"],
        ),
        (
            "controlled_map_candidate_generation_run",
            PATHS["controlled_map_candidate_generation_run"],
        ),
        (
            "controlled_map_candidate_review",
            PATHS["controlled_map_candidate_review"],
        ),
        (
            "controlled_map_text_fallback_generation_run",
            PATHS["controlled_map_text_fallback_generation_run"],
        ),
        (
            "controlled_map_text_fallback_candidate_review",
            PATHS["controlled_map_text_fallback_candidate_review"],
        ),
        ("handoff_audit", PATHS["handoff_audit"]),
        ("compiler_dossier", PATHS["compiler_dossier"]),
        ("multistage_content_pack", PATHS["multistage_content_pack"]),
    ]
    source_paths.extend(
        ("world_delta_transaction", path)
        for path in STAGE_WORLD_DELTA_TRANSACTION_PATHS
    )
    source_paths.extend(
        ("locked_manifest", path)
        for path in sorted((ROOT / "examples/locked_manifests").glob("*.json"))
    )
    source_paths.extend(
        ("map_runtime_package", path) for path in map_runtime_package_paths()
    )
    source_paths.extend(
        ("map_runtime_package_v02", path) for path in map_runtime_package_v02_paths()
    )
    source_paths.extend(
        ("map_compile_package", path) for path in map_compile_package_paths()
    )
    source_paths.extend(
        ("procedural_map_preview_report", path)
        for path in map_render_preview_report_paths()
    )
    source_paths.extend(
        ("procedural_map_preview_v02_report", path)
        for path in map_render_preview_v02_report_paths()
    )
    source_paths.extend(("reviewed_workflow", path) for path in REVIEWED_WORKFLOW_FILES)
    return [file_ref(path, role) for role, path in source_paths]


def assert_no_forbidden_keys(value: Any, path: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = key.lower()
            if any(fragment in lowered for fragment in FORBIDDEN_KEY_FRAGMENTS):
                raise ValueError(f"evidence contains forbidden key: {path}.{key}".strip("."))
            assert_no_forbidden_keys(child, f"{path}.{key}" if path else key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            assert_no_forbidden_keys(child, f"{path}[{index}]")


def build_evidence(
    frontend_flow_visual_smoke_report_path: Path | None = None,
) -> dict[str, Any]:
    frontend_pack = load_json(PATHS["frontend_mock_pack"])
    runtime_art_kit = load_json(PATHS["runtime_art_kit"])
    runtime_package = load_json(PATHS["runtime_package"])
    map_packages = [
        package
        for package in (load_json(path) for path in map_runtime_package_paths())
        if isinstance(package, dict)
    ]
    map_packages_v02 = [
        package
        for package in (load_json(path) for path in map_runtime_package_v02_paths())
        if isinstance(package, dict)
    ]
    map_compile_packages = [
        package
        for package in (load_json(path) for path in map_compile_package_paths())
        if isinstance(package, dict)
    ]
    procedural_map_preview_reports = [
        report
        for report in (load_json(path) for path in map_render_preview_report_paths())
        if isinstance(report, dict)
    ]
    procedural_map_preview_v02_reports = [
        report
        for report in (load_json(path) for path in map_render_preview_v02_report_paths())
        if isinstance(report, dict)
    ]
    frontend_media_manifest = load_json(PATHS["frontend_media_manifest"])
    frontend_media_atlas_manifest = load_json(PATHS["frontend_media_atlas_manifest"])
    frontend_loop_continuity_report = load_json(PATHS["frontend_loop_continuity_report"])
    frontend_sprite_quality_report = load_json(PATHS["frontend_sprite_cutout_quality_report"])
    frontend_sprite_repair_plan = load_json(PATHS["frontend_sprite_cutout_repair_plan"])
    frontend_sprite_repair_candidates = load_json(PATHS["frontend_sprite_repair_candidates"])
    frontend_sprite_repair_candidate_quality_report = load_json(
        PATHS["frontend_sprite_repair_candidate_quality_report"]
    )
    runtime_art_media_manifest = load_json(PATHS["runtime_art_media_manifest"])
    runtime_art_atlas_manifest = load_json(PATHS["runtime_art_atlas_manifest"])
    runtime_loop_continuity_report = load_json(PATHS["runtime_loop_continuity_report"])
    runtime_sprite_quality_report = load_json(PATHS["runtime_sprite_cutout_quality_report"])
    runtime_sprite_repair_plan = load_json(PATHS["runtime_sprite_cutout_repair_plan"])
    runtime_sprite_repair_candidates = load_json(PATHS["runtime_sprite_repair_candidates"])
    runtime_sprite_repair_candidate_quality_report = load_json(
        PATHS["runtime_sprite_repair_candidate_quality_report"]
    )
    runtime_sprite_regeneration_candidates = load_json(
        PATHS["runtime_sprite_regeneration_candidates"]
    )
    runtime_sprite_regeneration_candidate_quality_report = load_json(
        PATHS["runtime_sprite_regeneration_candidate_quality_report"]
    )
    runtime_sprite_regeneration_promotion_report = load_json(
        PATHS["runtime_sprite_regeneration_promotion_report"]
    )
    generation_schedule_plan = load_json(PATHS["generation_schedule_plan"])
    generation_schedule_run_report = load_json(PATHS["generation_schedule_run_report"])
    generation_executor_run_request = load_json(
        PATHS["generation_executor_run_request"]
    )
    provider_execution_authorization = load_json(
        PATHS["provider_execution_authorization"]
    )
    provider_adapter_execution_receipt = load_json(
        PATHS["provider_adapter_execution_receipt"]
    )
    provider_adapter_runner_executor_request = load_json(
        PATHS["provider_adapter_runner_executor_request"]
    )
    provider_adapter_runner_receipt = load_json(
        PATHS["provider_adapter_runner_receipt"]
    )
    provider_adapter_runner_envelope = load_json(
        PATHS["provider_adapter_runner_envelope"]
    )
    provider_adapter_image_runner_executor_request = load_json(
        PATHS["provider_adapter_image_runner_executor_request"]
    )
    provider_adapter_image_runner_receipt = load_json(
        PATHS["provider_adapter_image_runner_receipt"]
    )
    provider_adapter_image_runner_envelope = load_json(
        PATHS["provider_adapter_image_runner_envelope"]
    )
    world_delta_transaction = load_json(PATHS["world_delta_transaction_example"])
    world_delta_transactions = [
        load_json(path) for path in STAGE_WORLD_DELTA_TRANSACTION_PATHS
    ]
    map_visual_manifest = load_json(PATHS["map_visual_manifest"])
    map_visual_quality_report = load_json(PATHS["map_visual_quality_report"])
    map_visual_promotion_gate_report = load_json(
        PATHS["map_visual_promotion_gate_report"]
    )
    map_runtime_promotion_readiness_report = load_json(
        PATHS["map_runtime_promotion_readiness_report"]
    )
    map_runtime_activation_gate_report = load_json(
        PATHS["map_runtime_activation_gate_report"]
    )
    map_path_geometry_report = load_json(PATHS["map_path_geometry_report"])
    map_component_media_manifest = load_json(PATHS["map_component_media_manifest"])
    map_component_media_manifest_v02 = load_json(
        PATHS["map_component_media_manifest_v02"]
    )
    map_style_component_binding_report = load_json(
        PATHS["map_style_component_binding_report"]
    )
    map_component_generation_request_pack = load_json(
        PATHS["map_component_generation_request_pack"]
    )
    map_component_artifact_staging_manifest = load_json(
        PATHS["map_component_artifact_staging_manifest"]
    )
    map_component_candidate_review_report = load_json(
        PATHS["map_component_candidate_review_report"]
    )
    map_component_visual_quality_report = load_json(
        PATHS["map_component_visual_quality_report"]
    )
    map_component_promotion_gate_report = load_json(
        PATHS["map_component_promotion_gate_report"]
    )
    map_component_manifest_patch_plan = load_json(
        PATHS["map_component_manifest_patch_plan"]
    )
    map_component_manifest_apply_report = load_json(
        PATHS["map_component_manifest_apply_report"]
    )
    node_map_candidate_review = load_json(PATHS["node_map_candidate_review"])
    map_candidate_alignment_review = load_json(PATHS["map_candidate_alignment_review"])
    map_candidate_overlay_review = load_json(PATHS["map_candidate_overlay_review"])
    map_candidate_overlay_visual_review = load_json(PATHS["map_candidate_overlay_visual_review"])
    map_layout_reconciliation_plan = load_json(PATHS["map_layout_reconciliation_plan"])
    runtime_map_patch_candidates = load_json(PATHS["runtime_map_patch_candidates"])
    map_patch_overlay_review = load_json(PATHS["map_patch_overlay_review"])
    topology_constrained_map_prompt_pack = load_json(
        PATHS["topology_constrained_map_prompt_pack"]
    )
    topology_constrained_map_candidate_review = load_json(
        PATHS["topology_constrained_map_candidate_review"]
    )
    topology_constrained_map_alignment_review = load_json(
        PATHS["topology_constrained_map_alignment_review"]
    )
    topology_constrained_map_overlay_review = load_json(
        PATHS["topology_constrained_map_overlay_review"]
    )
    topology_constrained_map_overlay_visual_review = load_json(
        PATHS["topology_constrained_map_overlay_visual_review"]
    )
    map_topology_control_sketch_pack = load_json(
        PATHS["map_topology_control_sketch_pack"]
    )
    map_controlled_regeneration_request_pack = load_json(
        PATHS["map_controlled_regeneration_request_pack"]
    )
    controlled_map_candidate_generation_run = load_json(
        PATHS["controlled_map_candidate_generation_run"]
    )
    controlled_map_candidate_review = load_json(
        PATHS["controlled_map_candidate_review"]
    )
    controlled_map_text_fallback_generation_run = load_json(
        PATHS["controlled_map_text_fallback_generation_run"]
    )
    controlled_map_text_fallback_candidate_review = load_json(
        PATHS["controlled_map_text_fallback_candidate_review"]
    )
    provider_artifact_staging_manifest = load_json(
        PATHS["provider_artifact_staging_manifest"]
    )
    provider_artifact_staging_source_envelope = load_json(
        PATHS["provider_artifact_staging_source_envelope"]
    )
    provider_artifact_promotion_report = load_json(
        PATHS["provider_artifact_promotion_report"]
    )
    provider_image_artifact_staging_manifest = load_json(
        PATHS["provider_image_artifact_staging_manifest"]
    )
    provider_image_artifact_staging_source_envelope = load_json(
        PATHS["provider_image_artifact_staging_source_envelope"]
    )
    provider_image_artifact_promotion_report = load_json(
        PATHS["provider_image_artifact_promotion_report"]
    )
    core_artifact_alignment_report = load_json(
        PATHS["core_artifact_alignment_report"]
    )
    mvp_primary_api_flow_smoke_report = load_json(
        PATHS["mvp_primary_api_flow_smoke_report"]
    )
    map_v02_preview_api_smoke_report = load_json(
        PATHS["map_v02_preview_api_smoke_report"]
    )
    mvp_demo_readiness_report = load_json(PATHS["mvp_demo_readiness_report"])
    audit_report = load_json(PATHS["handoff_audit"])
    dossier = load_json(PATHS["compiler_dossier"])
    multistage_pack = load_json(PATHS["multistage_content_pack"])
    validation_results = run_validation_commands()

    evidence = {
        "schema_version": "demo_evidence_bundle.v0.1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "repository_root": str(ROOT),
        "redaction_policy": {
            "mode": "summary_only",
            "reads_env_files": False,
            "calls_external_services": False,
            "omitted_internal_details": [
                "凭据字段值",
                "原始提示词",
                "外部生成器原始响应",
                "完整执行轨迹",
                "未审长文本内容",
            ],
            "included_content": "仅包含已审 fixture 的结构摘要、计数、公开媒体路径和 sha256 指纹。",
        },
        "project_positioning": {
            "name": "通用 AI 编译塔防游戏 MVP",
            "mvp_worldbook": frontend_pack.get("worldbook_id"),
            "positioning": (
                "本项目不是单一《长夜灯火》游戏，而是用该世界书模板验证"
                "玩家想法、世界上下文、受控内容编译、运行时战斗和战后世界生长的闭环。"
            ),
            "runtime_mode": "FastAPI + SQLite 后端，前端当前消费 fixture-backed mock API。",
            "player_boundary": "玩家侧只看到世界内研发和战斗结果；本证据包是评审/录屏用内部摘要。",
        },
        "mvp_demo_readiness": collect_mvp_demo_readiness_report(
            mvp_demo_readiness_report
        ),
        "browser_visual_evidence": collect_browser_visual_evidence(
            frontend_flow_visual_smoke_report_path
        ),
        "ai_compilation_link": collect_ai_compilation_link(
            frontend_pack, dossier, multistage_pack
        ),
        "generation_scheduler": collect_generation_scheduler(
            generation_schedule_plan,
            generation_schedule_run_report,
        ),
        "generation_executor_run_request": collect_generation_executor_run_request(
            generation_executor_run_request
        ),
        "provider_execution_authorization": collect_provider_execution_authorization(
            provider_execution_authorization
        ),
        "provider_adapter_execution_receipt": collect_provider_adapter_execution_receipt(
            provider_adapter_execution_receipt
        ),
        "provider_adapter_runner": collect_provider_adapter_runner(
            provider_adapter_runner_executor_request,
            provider_adapter_runner_receipt,
            provider_adapter_runner_envelope,
        ),
        "provider_adapter_image_runner": collect_provider_adapter_runner(
            provider_adapter_image_runner_executor_request,
            provider_adapter_image_runner_receipt,
            provider_adapter_image_runner_envelope,
        ),
        "provider_artifact_staging": collect_provider_artifact_staging(
            provider_artifact_staging_manifest,
            provider_artifact_staging_source_envelope,
        ),
        "provider_artifact_promotion_report": collect_provider_artifact_promotion_report(
            provider_artifact_promotion_report
        ),
        "provider_image_artifact_staging": collect_provider_artifact_staging(
            provider_image_artifact_staging_manifest,
            provider_image_artifact_staging_source_envelope,
        ),
        "provider_image_artifact_promotion_report": collect_provider_artifact_promotion_report(
            provider_image_artifact_promotion_report
        ),
        "core_artifact_alignment_report": collect_core_artifact_alignment_report(
            core_artifact_alignment_report
        ),
        "world_delta_transaction": collect_world_delta_transaction(world_delta_transaction),
        "world_delta_transaction_chain": collect_world_delta_transaction_chain(
            world_delta_transactions
        ),
        "map_runtime_packages": collect_map_runtime_packages(map_packages),
        "map_runtime_packages_v02": collect_map_runtime_packages(map_packages_v02),
        "backend_api_evidence": {
            "mvp_primary_flow": collect_mvp_primary_api_flow_smoke(
                mvp_primary_api_flow_smoke_report
            ),
            "map_v02_preview": collect_map_v02_preview_api_smoke(
                map_v02_preview_api_smoke_report
            ),
        },
        "map_runtime_promotion_readiness": map_runtime_promotion_readiness_summary(
            map_runtime_promotion_readiness_report
        ),
        "map_runtime_activation_gate": map_runtime_activation_gate_summary(
            map_runtime_activation_gate_report
        ),
        "map_path_geometry": map_path_geometry_summary(map_path_geometry_report),
        "map_component_media": map_component_media_summary(map_component_media_manifest),
        "map_component_media_v02_preview": map_component_media_summary(
            map_component_media_manifest_v02
        ),
        "map_style_component_bindings": map_style_component_binding_summary(
            map_style_component_binding_report
        ),
        "map_component_generation_pipeline": {
            "request_pack": map_component_generation_request_summary(
                map_component_generation_request_pack
            ),
            "artifact_staging": map_component_artifact_staging_summary(
                map_component_artifact_staging_manifest
            ),
            "candidate_review": map_component_candidate_review_summary(
                map_component_candidate_review_report
            ),
            "visual_quality_gate": map_component_visual_quality_summary(
                map_component_visual_quality_report
            ),
            "promotion_gate": map_component_promotion_gate_summary(
                map_component_promotion_gate_report
            ),
            "manifest_patch_plan": map_component_manifest_patch_plan_summary(
                map_component_manifest_patch_plan
            ),
            "manifest_apply_report": map_component_manifest_apply_report_summary(
                map_component_manifest_apply_report
            ),
        },
        "map_compile_packages": collect_map_compile_packages(map_compile_packages),
        "runtime_package": collect_runtime_package(runtime_package),
        "assets_and_media": collect_assets_and_media(
            frontend_pack,
            frontend_media_manifest,
            frontend_media_atlas_manifest,
            frontend_loop_continuity_report,
            frontend_sprite_quality_report,
            frontend_sprite_repair_plan,
            frontend_sprite_repair_candidates,
            frontend_sprite_repair_candidate_quality_report,
            runtime_art_kit,
            runtime_art_media_manifest,
            runtime_art_atlas_manifest,
            runtime_loop_continuity_report,
            runtime_sprite_quality_report,
            runtime_sprite_repair_plan,
            runtime_sprite_repair_candidates,
            runtime_sprite_repair_candidate_quality_report,
            runtime_sprite_regeneration_candidates,
            runtime_sprite_regeneration_candidate_quality_report,
            runtime_sprite_regeneration_promotion_report,
            map_visual_manifest,
            map_visual_quality_report,
            map_visual_promotion_gate_report,
            node_map_candidate_review,
            map_candidate_alignment_review,
            map_candidate_overlay_review,
            map_candidate_overlay_visual_review,
            map_layout_reconciliation_plan,
            runtime_map_patch_candidates,
            map_patch_overlay_review,
            topology_constrained_map_prompt_pack,
            topology_constrained_map_candidate_review,
            topology_constrained_map_alignment_review,
            topology_constrained_map_overlay_review,
            topology_constrained_map_overlay_visual_review,
            map_topology_control_sketch_pack,
            map_controlled_regeneration_request_pack,
            controlled_map_candidate_generation_run,
            controlled_map_candidate_review,
            controlled_map_text_fallback_generation_run,
            controlled_map_text_fallback_candidate_review,
            procedural_map_preview_reports,
            procedural_map_preview_v02_reports,
        ),
        "validation_summary": collect_validation_summary(
            validation_results, audit_report, dossier, map_packages, map_compile_packages
        ),
        "frontend_entry": collect_frontend_entry(frontend_pack),
        "source_files": collect_source_files(),
    }
    assert_no_forbidden_keys(evidence)
    return evidence


def md_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)


def render_summary_markdown(evidence: dict[str, Any]) -> str:
    project = as_obj(evidence.get("project_positioning"))
    readiness = as_obj(evidence.get("mvp_demo_readiness"))
    readiness_summary = as_obj(readiness.get("summary"))
    frontend_flow_visual = as_obj(
        as_obj(evidence.get("browser_visual_evidence")).get("frontend_flow")
    )
    ai_link = as_obj(evidence.get("ai_compilation_link"))
    primary_flow_api = as_obj(
        as_obj(evidence.get("backend_api_evidence")).get("mvp_primary_flow")
    )
    map_packages = as_obj(evidence.get("map_runtime_packages"))
    map_packages_v02 = as_obj(evidence.get("map_runtime_packages_v02"))
    map_v02_api = as_obj(
        as_obj(evidence.get("backend_api_evidence")).get("map_v02_preview")
    )
    map_compile_packages = as_obj(evidence.get("map_compile_packages"))
    map_runtime_promotion_readiness = as_obj(
        evidence.get("map_runtime_promotion_readiness")
    )
    map_runtime_activation_gate = as_obj(evidence.get("map_runtime_activation_gate"))
    map_path_geometry = as_obj(evidence.get("map_path_geometry"))
    map_component_media = as_obj(evidence.get("map_component_media"))
    map_component_media_v02 = as_obj(evidence.get("map_component_media_v02_preview"))
    map_style_component_bindings = as_obj(
        evidence.get("map_style_component_bindings")
    )
    map_component_generation_pipeline = as_obj(
        evidence.get("map_component_generation_pipeline")
    )
    map_component_generation_request = as_obj(
        map_component_generation_pipeline.get("request_pack")
    )
    map_component_artifact_staging = as_obj(
        map_component_generation_pipeline.get("artifact_staging")
    )
    map_component_candidate_review = as_obj(
        map_component_generation_pipeline.get("candidate_review")
    )
    map_component_visual_quality = as_obj(
        map_component_generation_pipeline.get("visual_quality_gate")
    )
    map_component_promotion_gate = as_obj(
        map_component_generation_pipeline.get("promotion_gate")
    )
    map_component_manifest_patch_plan = as_obj(
        map_component_generation_pipeline.get("manifest_patch_plan")
    )
    map_component_manifest_apply_report = as_obj(
        map_component_generation_pipeline.get("manifest_apply_report")
    )
    map_visual_quality = as_obj(
        as_obj(as_obj(evidence.get("assets_and_media")).get("map_visual_reference")).get(
            "quality_audit"
        )
    )
    map_visual_promotion_gate = as_obj(
        as_obj(as_obj(evidence.get("assets_and_media")).get("map_visual_reference")).get(
            "promotion_gate"
        )
    )
    node_map_candidate_review = as_obj(
        as_obj(as_obj(evidence.get("assets_and_media")).get("map_visual_reference")).get(
            "candidate_review"
        )
    )
    map_candidate_alignment = as_obj(
        as_obj(as_obj(evidence.get("assets_and_media")).get("map_visual_reference")).get(
            "alignment_review"
        )
    )
    map_candidate_overlay = as_obj(
        as_obj(as_obj(evidence.get("assets_and_media")).get("map_visual_reference")).get(
            "overlay_review"
        )
    )
    map_candidate_overlay_visual = as_obj(
        as_obj(as_obj(evidence.get("assets_and_media")).get("map_visual_reference")).get(
            "overlay_visual_review"
        )
    )
    map_layout_reconciliation = as_obj(
        as_obj(as_obj(evidence.get("assets_and_media")).get("map_visual_reference")).get(
            "layout_reconciliation_plan"
        )
    )
    runtime_map_patches = as_obj(
        as_obj(as_obj(evidence.get("assets_and_media")).get("map_visual_reference")).get(
            "runtime_patch_candidates"
        )
    )
    map_patch_overlay = as_obj(
        as_obj(as_obj(evidence.get("assets_and_media")).get("map_visual_reference")).get(
            "patch_overlay_review"
        )
    )
    topology_prompt_pack = as_obj(
        as_obj(as_obj(evidence.get("assets_and_media")).get("map_visual_reference")).get(
            "topology_prompt_pack"
        )
    )
    topology_candidate_review = as_obj(
        as_obj(as_obj(evidence.get("assets_and_media")).get("map_visual_reference")).get(
            "topology_candidate_review"
        )
    )
    topology_alignment_review = as_obj(
        as_obj(as_obj(evidence.get("assets_and_media")).get("map_visual_reference")).get(
            "topology_alignment_review"
        )
    )
    topology_overlay_review = as_obj(
        as_obj(as_obj(evidence.get("assets_and_media")).get("map_visual_reference")).get(
            "topology_overlay_review"
        )
    )
    topology_overlay_visual_review = as_obj(
        as_obj(as_obj(evidence.get("assets_and_media")).get("map_visual_reference")).get(
            "topology_overlay_visual_review"
        )
    )
    topology_control_sketch = as_obj(
        as_obj(as_obj(evidence.get("assets_and_media")).get("map_visual_reference")).get(
            "topology_control_sketch_pack"
        )
    )
    procedural_map_previews = as_obj(
        as_obj(as_obj(evidence.get("assets_and_media")).get("map_visual_reference")).get(
            "procedural_map_previews"
        )
    )
    procedural_map_previews_v02 = as_obj(
        as_obj(as_obj(evidence.get("assets_and_media")).get("map_visual_reference")).get(
            "procedural_map_previews_v02"
        )
    )
    controlled_regeneration_request = as_obj(
        as_obj(as_obj(evidence.get("assets_and_media")).get("map_visual_reference")).get(
            "controlled_regeneration_request_pack"
        )
    )
    controlled_candidate_generation = as_obj(
        as_obj(as_obj(evidence.get("assets_and_media")).get("map_visual_reference")).get(
            "controlled_candidate_generation_run"
        )
    )
    controlled_candidate_review = as_obj(
        as_obj(as_obj(evidence.get("assets_and_media")).get("map_visual_reference")).get(
            "controlled_candidate_review"
        )
    )
    controlled_text_fallback_generation = as_obj(
        as_obj(as_obj(evidence.get("assets_and_media")).get("map_visual_reference")).get(
            "controlled_text_fallback_generation_run"
        )
    )
    controlled_text_fallback_review = as_obj(
        as_obj(as_obj(evidence.get("assets_and_media")).get("map_visual_reference")).get(
            "controlled_text_fallback_candidate_review"
        )
    )
    scheduler = as_obj(evidence.get("generation_scheduler"))
    scheduler_summary = as_obj(scheduler.get("summary"))
    scheduler_run = as_obj(scheduler.get("run_report"))
    scheduler_run_summary = as_obj(scheduler_run.get("summary"))
    provider_runner_handoff = as_obj(scheduler.get("provider_runner_handoff"))
    provider_runner_handoff_roundtrip = as_obj(
        provider_runner_handoff.get("roundtrip_evidence")
    )
    background_tick = as_obj(scheduler.get("background_executor_tick"))
    background_tick_safety = as_obj(background_tick.get("safety"))
    background_handoff_tick = as_obj(scheduler.get("background_handoff_tick"))
    background_handoff_safety = as_obj(background_handoff_tick.get("safety"))
    provider_staging = as_obj(evidence.get("provider_artifact_staging"))
    provider_staging_source = as_obj(provider_staging.get("source"))
    provider_staging_promotion = as_obj(provider_staging.get("promotion_gate"))
    provider_promotion_report = as_obj(evidence.get("provider_artifact_promotion_report"))
    provider_image_staging = as_obj(evidence.get("provider_image_artifact_staging"))
    provider_image_staging_source = as_obj(provider_image_staging.get("source"))
    provider_image_staging_promotion = as_obj(
        provider_image_staging.get("promotion_gate")
    )
    provider_image_promotion_report = as_obj(
        evidence.get("provider_image_artifact_promotion_report")
    )
    core_alignment = as_obj(evidence.get("core_artifact_alignment_report"))
    world_transaction = as_obj(evidence.get("world_delta_transaction"))
    world_transaction_report = as_obj(world_transaction.get("validation_report"))
    world_transaction_chain = as_obj(evidence.get("world_delta_transaction_chain"))
    runtime_pkg = as_obj(evidence.get("runtime_package"))
    assets = as_obj(as_obj(evidence.get("assets_and_media")).get("frontend_pack"))
    media = as_obj(as_obj(evidence.get("assets_and_media")).get("published_asset_media"))
    atlas = as_obj(as_obj(evidence.get("assets_and_media")).get("published_asset_atlas"))
    sprite_quality = as_obj(
        as_obj(evidence.get("assets_and_media")).get("published_sprite_cutout_quality")
    )
    sprite_repair = as_obj(
        as_obj(evidence.get("assets_and_media")).get("published_sprite_repair_plan")
    )
    sprite_candidates = as_obj(
        as_obj(evidence.get("assets_and_media")).get("published_sprite_repair_candidates")
    )
    frontend_pack_core = as_obj(assets.get("core_artifacts"))
    runtime_art = as_obj(as_obj(evidence.get("assets_and_media")).get("runtime_art"))
    runtime_art_atlas = as_obj(runtime_art.get("atlas_manifest"))
    runtime_sprite_quality = as_obj(runtime_art.get("sprite_cutout_quality"))
    runtime_sprite_repair = as_obj(runtime_art.get("sprite_repair_plan"))
    runtime_sprite_candidates = as_obj(runtime_art.get("sprite_repair_candidates"))
    runtime_sprite_regeneration = as_obj(runtime_art.get("sprite_regeneration_candidates"))
    runtime_sprite_promotion = as_obj(runtime_art.get("sprite_regeneration_promotion"))
    validation = as_obj(evidence.get("validation_summary"))
    export_validation = as_obj(validation.get("current_export_validation"))
    frontend_entry = as_obj(evidence.get("frontend_entry"))

    validation_rows = [
        [
            item.get("name"),
            item.get("status"),
            item.get("return_code"),
            f"`{item.get('command')}`",
        ]
        for item in as_list(export_validation.get("results"))
    ]
    package_rows = [
        [
            package.get("node_id"),
            package.get("package_id"),
            package.get("path_route_count"),
            package.get("build_slot_count"),
            package.get("published_visual_layer_count"),
        ]
        for package in as_list(map_packages.get("packages"))
    ]
    layer_rows = [
        [
            package.get("node_id"),
            layer.get("role"),
            layer.get("authority") or "reference_only",
            f"{layer.get('width')}x{layer.get('height')}",
            layer.get("local_path"),
        ]
        for package in as_list(map_packages.get("packages"))
        for layer in as_list(as_obj(package).get("visual_layers"))
    ]
    compile_rows = [
        [
            package.get("node_id"),
            package.get("package_id"),
            package.get("painted_visual_status"),
            package.get("alignment_status"),
            package.get("quality_gate_count"),
            as_obj(package.get("validation_report")).get("runtime_truth_preserved"),
        ]
        for package in as_list(map_compile_packages.get("packages"))
    ]
    map_runtime_readiness_rows = [
        [
            node.get("node_id"),
            node.get("status"),
            node.get("semantic_status"),
            node.get("published_player_layer_count"),
            ", ".join(str(reason) for reason in as_list(node.get("blocking_reasons"))),
        ]
        for node in as_list(map_runtime_promotion_readiness.get("node_samples"))
    ]
    map_runtime_activation_rows = [
        [
            decision.get("node_id"),
            decision.get("activation_decision"),
            decision.get("decision_reason"),
            decision.get("to_package_id"),
            ", ".join(str(reason) for reason in as_list(decision.get("blockers"))),
        ]
        for decision in as_list(map_runtime_activation_gate.get("decision_samples"))
    ]
    schedule_rows = [
        [
            item.get("schedule_item_id"),
            item.get("latency_class"),
            item.get("status"),
            item.get("provider_mode"),
            item.get("world_commit"),
        ]
        for item in as_list(scheduler.get("items"))
    ]
    staged_artifact_rows = [
        [
            artifact.get("artifact_id"),
            artifact.get("kind"),
            artifact.get("media_layer"),
            artifact.get("review_status"),
            artifact.get("path"),
        ]
        for artifact in as_list(provider_staging.get("staged_artifacts"))
    ]
    image_staged_artifact_rows = [
        [
            artifact.get("artifact_id"),
            artifact.get("kind"),
            artifact.get("media_layer"),
            artifact.get("review_status"),
            artifact.get("path"),
        ]
        for artifact in as_list(provider_image_staging.get("staged_artifacts"))
    ]
    readiness_rows = [
        [
            gate.get("gate_id"),
            gate.get("status"),
            gate.get("required_for_mvp_demo"),
            gate.get("summary"),
        ]
        for gate in as_list(readiness.get("gates"))
    ]
    limitation_rows = [
        [
            item.get("limitation_id"),
            item.get("severity"),
            item.get("summary"),
        ]
        for item in as_list(readiness.get("known_limitations"))
    ]
    core_alignment_rows = [
        [
            target.get("target_id"),
            target.get("target_kind"),
            target.get("alignment_state"),
            ", ".join(str(item) for item in as_list(target.get("present_artifacts"))),
            target.get("next_action"),
        ]
        for target in as_list(core_alignment.get("sample_migration_targets"))
    ]
    world_transaction_rows = [
        [
            item.get("transaction_id"),
            item.get("source"),
            item.get("scope_kind"),
            item.get("operation_mapping_count"),
            item.get("status"),
        ]
        for item in as_list(world_transaction_chain.get("transactions"))
    ]
    lines = [
        "# AI 编译塔防 MVP 演示证据包",
        "",
        f"- 生成时间：`{evidence.get('generated_at')}`",
        f"- 项目定位：{project.get('positioning')}",
        f"- 当前运行模式：{project.get('runtime_mode')}",
        f"- 证据边界：{project.get('player_boundary')}",
        "",
        "## 1. AI 编译链路存在性",
        "",
        f"- MVP 演示 readiness：`{readiness.get('overall_status')}`",
        f"- 必需 gate：`{readiness_summary.get('required_gate_passed_or_expected_count')}` / `{readiness_summary.get('required_gate_count')}`；阻断 `{readiness_summary.get('blocking_gate_count')}`；warning `{readiness_summary.get('warning_gate_count')}`；预期阻断 `{readiness_summary.get('expected_block_count')}`",
        f"- readiness 报告自身 provider 调用：`{readiness_summary.get('provider_call_count_by_report')}`，世界修改：`{readiness_summary.get('world_mutation_count_by_report')}`，runtime 修改：`{readiness_summary.get('runtime_mutation_count_by_report')}`",
        f"- 浏览器玩家链路截图：`{frontend_flow_visual.get('status')}`，截图 `{frontend_flow_visual.get('captured_screenshot_count')}` / `{frontend_flow_visual.get('expected_screenshot_count')}`，报告 `{as_obj(frontend_flow_visual.get('report_ref')).get('path') or 'not_provided'}`",
        "",
        md_table(["Gate", "状态", "MVP 必需", "摘要"], readiness_rows),
        "",
        md_table(["限制", "严重度", "说明"], limitation_rows),
        "",
        f"- 受控链路说明：{ai_link.get('claim')}",
        f"- MVP 主流程 API smoke：`{primary_flow_api.get('status')}`，步骤 `{primary_flow_api.get('passed_step_count')}` / `{primary_flow_api.get('step_count')}`，节点 `{primary_flow_api.get('node_id')}`，transport `{primary_flow_api.get('transport')}`",
        f"- 可玩资产数：`{as_obj(ai_link.get('compiled_artifact_counts')).get('playable_assets')}`",
        f"- runtime package 数：`{as_obj(ai_link.get('compiled_artifact_counts')).get('runtime_packages')}`",
        f"- 多阶段内容阶段数：`{ai_link.get('multistage_stage_count')}`",
        f"- 证据 workflow 文件数：`{len(as_list(ai_link.get('reviewed_workflow_files')))}`",
        f"- 摘要链路步骤：`{', '.join(as_list(ai_link.get('pipeline_steps')))}`",
        "",
        "## 2. Generation Scheduler",
        "",
        f"- 调度计划：`{scheduler.get('plan_id')}`，调度项 `{scheduler_summary.get('item_count')}` 个",
        f"- 延迟分布：`{scheduler_summary.get('latency_class_counts')}`",
        f"- fallback 覆盖：`{scheduler_summary.get('fallback_covered_count')}` / `{scheduler_summary.get('item_count')}`",
        f"- dry-run 动作分布：`{scheduler_run_summary.get('action_counts')}`",
        f"- dry-run provider 调用：`{scheduler_run.get('provider_call_count')}`，世界修改：`{scheduler_run.get('world_mutation_count')}`",
        f"- 构建期读取环境：`{scheduler.get('reads_env_during_build')}`，构建期调用 provider：`{scheduler.get('calls_provider_during_build')}`",
        f"- runner handoff：`{provider_runner_handoff.get('status')}`，roundtrip cache：`{provider_runner_handoff_roundtrip.get('expected_cache_status')}`，runtime 激活：`{provider_runner_handoff_roundtrip.get('runtime_activation_allowed')}`",
        f"- background tick：`{background_tick.get('status')}`，默认预算：`{background_tick.get('default_max_items')}`，provider 调用：`{background_tick_safety.get('api_calls_provider')}`，runtime 激活：`{background_tick_safety.get('api_activates_runtime')}`",
        f"- background handoff tick：`{background_handoff_tick.get('status')}`，outbox：`{background_handoff_tick.get('outbox_status')}`，handoff 数：`{background_handoff_tick.get('expected_runner_handoff_count')}`，运行 adapter：`{background_handoff_safety.get('api_runs_provider_adapter')}`",
        "",
        md_table(["调度项", "延迟等级", "状态", "Provider 模式", "世界提交"], schedule_rows),
        "",
        "## 2.1 Provider 产物暂存",
        "",
        f"- 暂存清单：`{provider_staging.get('manifest_id')}`，状态：`{provider_staging.get('staging_status')}`",
        f"- source envelope：`{provider_staging.get('source_envelope_id')}`，provider 调用状态：`{provider_staging_source.get('provider_call_status')}`，已执行：`{provider_staging_source.get('provider_call_performed')}`",
        f"- 暂存 artifact：`{provider_staging.get('staged_artifact_count')}` 个；source output refs：`{provider_staging_source.get('source_output_ref_count')}`",
        f"- gate 状态：`{provider_staging.get('gate_statuses')}`",
        f"- promotion：允许 `{provider_staging_promotion.get('promotion_allowed')}`，阻断：`{provider_staging_promotion.get('blocked_reason')}`，下一步：`{', '.join(str(gate) for gate in as_list(provider_staging_promotion.get('required_next_gates')))}`",
        "",
        md_table(["Artifact", "类型", "媒体层", "审查状态", "本地路径"], staged_artifact_rows),
        "",
        "## 2.2 Provider 晋升报告",
        "",
        f"- 报告：`{provider_promotion_report.get('report_id')}`，source staging：`{provider_promotion_report.get('source_staging_id')}`",
        f"- 决策：`{provider_promotion_report.get('promotion_decision')}`，允许晋升：`{provider_promotion_report.get('promotion_allowed')}`，阻断：`{provider_promotion_report.get('blocked_reason')}`",
        f"- gate 状态：`{provider_promotion_report.get('gate_statuses')}`",
        f"- target：`{as_obj(provider_promotion_report.get('promotion_targets')).get('target_kind')}`，reviewed artifacts `{provider_promotion_report.get('reviewed_artifact_count')}`",
        f"- 报告自身 provider 调用：`{as_obj(provider_promotion_report.get('safety_summary')).get('provider_call_count_by_report')}`，世界修改：`{as_obj(provider_promotion_report.get('safety_summary')).get('world_mutation_count_by_report')}`，runtime 修改：`{as_obj(provider_promotion_report.get('safety_summary')).get('runtime_mutation_count_by_report')}`",
        "",
        "## 2.3 Provider 图片候选失败门",
        "",
        f"- 图片暂存清单：`{provider_image_staging.get('manifest_id')}`，状态：`{provider_image_staging.get('staging_status')}`",
        f"- source envelope：`{provider_image_staging.get('source_envelope_id')}`，provider 调用状态：`{provider_image_staging_source.get('provider_call_status')}`，已执行：`{provider_image_staging_source.get('provider_call_performed')}`",
        f"- gate 状态：`{provider_image_staging.get('gate_statuses')}`",
        f"- promotion：允许 `{provider_image_staging_promotion.get('promotion_allowed')}`，阻断：`{provider_image_staging_promotion.get('blocked_reason')}`，下一步：`{', '.join(str(gate) for gate in as_list(provider_image_staging_promotion.get('required_next_gates')))}`",
        "",
        md_table(["Artifact", "类型", "媒体层", "审查状态", "本地路径"], image_staged_artifact_rows),
        "",
        f"- 图片晋升报告：`{provider_image_promotion_report.get('report_id')}`，决策：`{provider_image_promotion_report.get('promotion_decision')}`，允许晋升：`{provider_image_promotion_report.get('promotion_allowed')}`，阻断：`{provider_image_promotion_report.get('blocked_reason')}`",
        f"- 图片 gate 状态：`{provider_image_promotion_report.get('gate_statuses')}`",
        f"- target：`{as_obj(provider_image_promotion_report.get('promotion_targets')).get('target_kind')}`，reviewed artifacts `{provider_image_promotion_report.get('reviewed_artifact_count')}`",
        "",
        "## 2.4 核心对象对齐报告",
        "",
        f"- 报告：`{core_alignment.get('report_id')}`，状态：`{core_alignment.get('overall_status')}`，目标 `{core_alignment.get('target_count')}` 个",
        f"- 原生快照 ready：`{core_alignment.get('native_snapshot_ready_count')}`；refs-only：`{core_alignment.get('refs_only_count')}`；待迁移：`{core_alignment.get('missing_core_alignment_count')}`；校验失败：`{core_alignment.get('validation_failed_count')}`",
        f"- review-only / 不适用：`{core_alignment.get('review_only_not_applicable_count')}`；迁移任务：`{core_alignment.get('migration_task_count')}`",
        f"- 安全边界：读环境 `{as_obj(core_alignment.get('safety_summary')).get('reads_env')}`，调用外部服务 `{as_obj(core_alignment.get('safety_summary')).get('calls_external_service')}`，runtime 修改 `{as_obj(core_alignment.get('safety_summary')).get('runtime_mutation_count')}`，世界修改 `{as_obj(core_alignment.get('safety_summary')).get('world_mutation_count')}`",
        "",
        md_table(["目标", "类型", "状态", "已有核心对象", "下一步"], core_alignment_rows),
        "",
        "## 2.5 世界状态事务",
        "",
        f"- 事务：`{world_transaction.get('transaction_id')}`，状态：`{world_transaction.get('status')}`",
        f"- Delta：`{world_transaction.get('delta_id')}`，来源：`{world_transaction.get('source')}`，节点：`{', '.join(str(node) for node in as_list(world_transaction.get('node_ids')))}`",
        f"- operation 映射数：`{world_transaction.get('operation_mapping_count')}`，冲突策略：`{world_transaction.get('conflict_policy')}`，回滚策略：`{world_transaction.get('rollback_policy')}`",
        f"- 验证：结构 `{world_transaction_report.get('world_delta_structure')}`，语义 `{world_transaction_report.get('world_delta_semantics')}`，映射 `{world_transaction_report.get('operation_mapping')}`，apply `{world_transaction_report.get('runtime_apply_checked')}`",
        f"- 事务链：`{world_transaction_chain.get('transaction_count')}` 个阶段事务，合计映射 `{world_transaction_chain.get('total_operation_mapping_count')}` 个 WorldStateDelta operation",
        f"- 来源分布：`{world_transaction_chain.get('source_counts')}`；状态分布：`{world_transaction_chain.get('status_counts')}`",
        "",
        md_table(["事务", "来源", "提交范围", "op 数", "状态"], world_transaction_rows),
        "",
        "## 3. Runtime 与地图包",
        "",
        f"- RuntimePackage：`{runtime_pkg.get('package_id')}`，战斗：{runtime_pkg.get('battle_display_name')}，资产数：`{runtime_pkg.get('asset_count')}`",
        f"- MapRuntimePackage 数：`{map_packages.get('package_count')}`，节点：`{', '.join(str(node) for node in as_list(map_packages.get('node_ids')))}`",
        f"- MapRuntimePackage v0.2 preview：`{map_packages_v02.get('package_count')}`，资源点 `{map_packages_v02.get('total_resource_node_count')}`，机关区 `{map_packages_v02.get('total_hazard_zone_count')}`，防守锚点 `{map_packages_v02.get('total_defense_anchor_count')}`，阻挡区 `{map_packages_v02.get('total_blocked_area_count')}`",
        f"- MapRuntimePackage v0.2 API smoke：`{map_v02_api.get('status')}`，节点 `{map_v02_api.get('node_count')}`，默认 v0.1 保留 `{map_v02_api.get('default_runtime_v01_preserved_count')}`，provider calls `{as_obj(map_v02_api.get('safety')).get('provider_call_count')}`，runtime 激活 `{map_v02_api.get('runtime_activation_allowed')}`",
        f"- Map runtime 晋升准备度：`{map_runtime_promotion_readiness.get('status')}`，候选 `{map_runtime_promotion_readiness.get('promotion_candidate_count')}` / `{map_runtime_promotion_readiness.get('node_count')}`，activation allowed `{map_runtime_promotion_readiness.get('activation_allowed_count')}`，blockers `{map_runtime_promotion_readiness.get('blocker_counts')}`",
        f"- Map runtime 激活门：`{map_runtime_activation_gate.get('status')}`，允许 `{map_runtime_activation_gate.get('activation_allowed_count')}`，阻断 `{map_runtime_activation_gate.get('activation_blocked_count')}`，原因 `{map_runtime_activation_gate.get('decision_reason_counts')}`，runtime 修改 `{as_obj(map_runtime_activation_gate.get('safety')).get('default_runtime_mutation_performed')}`",
        f"- 地图路径几何审查：`{map_path_geometry.get('status')}`，地图 `{map_path_geometry.get('map_count')}`，路线 `{map_path_geometry.get('route_count')}`，塔位 `{map_path_geometry.get('build_slot_count')}`，总长度 `{map_path_geometry.get('total_route_length_cells')}`，warning `{map_path_geometry.get('warning_count')}`，来源 `{as_obj(map_path_geometry.get('source_policy')).get('geometry_source')}`",
        f"- MapComponentMediaManifest：`{map_component_media.get('media_pack_id')}`，components `{map_component_media.get('component_count')}`，materials `{map_component_media.get('material_component_count')}`，prefabs `{map_component_media.get('prefab_component_count')}`，URL prefix `{map_component_media.get('public_url_prefix')}`，策略 `{', '.join(str(item) for item in as_list(map_component_media.get('usage_policy'))[:4])}`",
        f"- MapComponentMediaManifest v0.2 preview：`{map_component_media_v02.get('media_pack_id')}`，components `{map_component_media_v02.get('component_count')}`，single images `{map_component_media_v02.get('single_image_count')}`，atlas animations `{map_component_media_v02.get('atlas_animation_count')}`，media kinds `{map_component_media_v02.get('media_kind_counts')}`，默认前端消费 `{('no_frontend_default_consumption' in as_list(map_component_media_v02.get('usage_policy')))}`",
        f"- MapStylePack component binding gate：`{map_style_component_bindings.get('status')}`，StylePack `{map_style_component_bindings.get('style_pack_count')}`，显式 material refs `{map_style_component_bindings.get('material_component_ref_count')}`，显式 prefab refs `{map_style_component_bindings.get('prefab_reviewed_component_ref_count')}`，resolved `{map_style_component_bindings.get('resolved_ref_count')}`，fallback `{map_style_component_bindings.get('procedural_fallback_count')}`，策略 `{', '.join(str(item) for item in as_list(map_style_component_bindings.get('usage_policy'))[:4])}`",
        f"- MapComponent generation request pack：`{map_component_generation_request.get('status')}`，requests `{map_component_generation_request.get('request_count')}`，components `{map_component_generation_request.get('component_count')}`，target kinds `{map_component_generation_request.get('target_media_kind_counts')}`",
        f"- MapComponent artifact staging：`{map_component_artifact_staging.get('status')}`，slots `{map_component_artifact_staging.get('slot_count')}`，imported `{map_component_artifact_staging.get('imported_count')}`，awaiting `{map_component_artifact_staging.get('awaiting_count')}`，not imported `{map_component_artifact_staging.get('not_imported_count')}`，runtime/manifest 写入 `{map_component_artifact_staging.get('runtime_effect')}`",
        f"- MapComponent candidate review：`{map_component_candidate_review.get('status')}`，读取 staging `{map_component_candidate_review.get('source_artifact_staging_manifest_path')}`，candidates `{map_component_candidate_review.get('candidate_count')}`，baseline fixtures `{map_component_candidate_review.get('baseline_fixture_candidate_count')}`，generated `{map_component_candidate_review.get('generated_candidate_count')}`，可晋升 `{map_component_candidate_review.get('promotable_count')}`",
        f"- MapComponent visual quality / cutout gate：`{map_component_visual_quality.get('status')}`，读取 candidate review `{map_component_visual_quality.get('source_candidate_review_report_path')}`，generated `{map_component_visual_quality.get('generated_candidate_count')}`，checked `{map_component_visual_quality.get('checked_candidate_count')}`，blocked `{map_component_visual_quality.get('blocked_pending_quality_gates_count')}`，runtime/manifest 写入 `{map_component_visual_quality.get('runtime_effect')}`，promotion effect `{map_component_visual_quality.get('promotion_effect')}`",
        f"- MapComponent promotion gate：`{map_component_promotion_gate.get('status')}`，读取 visual quality `{map_component_promotion_gate.get('source_visual_quality_report_path')}` / `{map_component_promotion_gate.get('visual_quality_report_status')}`，允许晋升 `{map_component_promotion_gate.get('promotion_allowed_count')}`，阻断 `{map_component_promotion_gate.get('promotion_blocked_count')}`，baseline 保留 `{map_component_promotion_gate.get('baseline_preserved_count')}`，runtime/manifest 写入 `{map_component_promotion_gate.get('runtime_effect')}`",
        f"- MapComponent manifest patch plan：`{map_component_manifest_patch_plan.get('status')}`，读取 promotion gate `{map_component_manifest_patch_plan.get('source_promotion_gate_report_path')}`，allowed `{map_component_manifest_patch_plan.get('allowed_decision_count')}`，patches `{map_component_manifest_patch_plan.get('patch_count')}`，ready `{map_component_manifest_patch_plan.get('ready_patch_count')}`，runtime/manifest 写入 `{map_component_manifest_patch_plan.get('runtime_effect')}`",
        f"- MapComponent manifest apply report：`{map_component_manifest_apply_report.get('status')}`，approval `{map_component_manifest_apply_report.get('approval_id')}`，applied `{map_component_manifest_apply_report.get('applied_patch_count')}`，blocked `{map_component_manifest_apply_report.get('blocked_patch_count')}`，output manifest `{map_component_manifest_apply_report.get('output_manifest_path')}`，runtime/manifest 写入 `{map_component_manifest_apply_report.get('runtime_effect')}`",
        f"- MapCompilePackage 数：`{map_compile_packages.get('package_count')}`，节点：`{', '.join(str(node) for node in as_list(map_compile_packages.get('node_ids')))}`",
        f"- 总塔位：`{map_packages.get('total_build_slot_count')}`，总路径：`{map_packages.get('total_path_route_count')}`，出生点：`{map_packages.get('total_spawn_point_count')}`",
        f"- published visual layer 总数：`{map_packages.get('published_visual_layer_count')}`",
        f"- 地图视觉审计：`{map_visual_quality.get('status')}`，共享玩家底图组 `{map_visual_quality.get('shared_player_visual_layer_group_count')}`，警告 `{map_visual_quality.get('warning_counts')}`",
        f"- 地图视觉发布闸门：`{map_visual_promotion_gate.get('status')}`，阻断候选 `{map_visual_promotion_gate.get('blocked_candidate_count')}`，published 玩家图层 `{map_visual_promotion_gate.get('published_player_layer_count')}`，违规 `{map_visual_promotion_gate.get('violation_count')}`",
        f"- 节点地图候选：`{node_map_candidate_review.get('status')}`，候选 `{node_map_candidate_review.get('candidate_count')}`，晋升 runtime `{node_map_candidate_review.get('runtime_promotion_count')}`，状态 `{node_map_candidate_review.get('review_status_counts')}`",
        f"- 地图候选对齐审查：`{map_candidate_alignment.get('status')}`，需尺寸标准化 `{map_candidate_alignment.get('transform_required_count')}`，阻断 `{map_candidate_alignment.get('blocked_count')}`",
        f"- 地图候选 overlay 审查：`{map_candidate_overlay.get('status')}`，overlay artifacts `{map_candidate_overlay.get('overlay_artifact_ready_count')}`，目标尺寸 `{map_candidate_overlay.get('target_size')}`",
        f"- 地图候选视觉复核：`{map_candidate_overlay_visual.get('status')}`，可晋升 `{map_candidate_overlay_visual.get('promotable_count')}`，禁止晋升 `{map_candidate_overlay_visual.get('blocked_from_promotion_count')}`",
        f"- 地图布局修订计划：`{map_layout_reconciliation.get('status')}`，P0 `{map_layout_reconciliation.get('p0_count')}`，推荐分布 `{map_layout_reconciliation.get('recommendation_counts')}`",
        f"- Runtime 地图补丁候选：`{runtime_map_patches.get('status')}`，review candidates `{runtime_map_patches.get('review_candidate_count')}`，skipped `{runtime_map_patches.get('skipped_count')}`",
        f"- 地图补丁后 overlay 审查：`{map_patch_overlay.get('status')}`，可复核 `{map_patch_overlay.get('patched_overlay_artifact_ready_count')}`，校验失败 `{map_patch_overlay.get('validation_failed_count')}`，禁止直接晋升 `{map_patch_overlay.get('promotion_allowed_now_count')}`",
        f"- 拓扑约束地图 prompt pack：`{topology_prompt_pack.get('status')}`，主 prompt `{topology_prompt_pack.get('primary_prompt_count')}`，fallback `{topology_prompt_pack.get('fallback_prompt_count')}`",
        f"- 旧信号塔拓扑候选：candidate `{topology_candidate_review.get('status')}`，alignment `{topology_alignment_review.get('status')}`，overlay `{topology_overlay_review.get('status')}`，visual `{topology_overlay_visual_review.get('status')}`，可晋升 `{topology_overlay_visual_review.get('promotable_count')}`",
        f"- 地图 topology control sketch：`{topology_control_sketch.get('status')}`，sketch `{topology_control_sketch.get('sketch_count')}`，ready `{topology_control_sketch.get('ready_count')}`，目标尺寸 `{topology_control_sketch.get('target_size')}`",
        f"- 地图 RenderPlan 离线预览：report `{procedural_map_previews.get('report_count')}`，ready `{procedural_map_previews.get('ready_count')}`，状态 `{procedural_map_previews.get('status_counts')}`，runtime 策略 `{procedural_map_previews.get('runtime_activation_policy')}`",
        f"- 地图 RenderPlan v0.2 语义预览：report `{procedural_map_previews_v02.get('report_count')}`，ready `{procedural_map_previews_v02.get('ready_count')}`，状态 `{procedural_map_previews_v02.get('status_counts')}`，runtime 策略 `{procedural_map_previews_v02.get('runtime_activation_policy')}`",
        f"- 地图受控重生请求包：`{controlled_regeneration_request.get('status')}`，request `{controlled_regeneration_request.get('request_count')}`，reference image request `{controlled_regeneration_request.get('reference_image_request_count')}`，blocked `{controlled_regeneration_request.get('blocked_count')}`",
        f"- 地图受控候选生成 dry-run：`{controlled_candidate_generation.get('status')}`，handoff `{controlled_candidate_generation.get('handoff_ready_count')}`，图片 `{controlled_candidate_generation.get('image_exists_count')}`，provider calls `{controlled_candidate_generation.get('provider_call_count')}`",
        f"- 地图受控候选审查：`{controlled_candidate_review.get('status')}`，候选 `{controlled_candidate_review.get('candidate_count')}`，晋升 runtime `{controlled_candidate_review.get('runtime_promotion_count')}`，状态 `{controlled_candidate_review.get('review_status_counts')}`",
        f"- 地图 text-fallback 真实生成：`{controlled_text_fallback_generation.get('status')}`，图片 `{controlled_text_fallback_generation.get('image_exists_count')}`，provider calls `{controlled_text_fallback_generation.get('provider_call_count')}`，provider `{controlled_text_fallback_generation.get('provider_profile')}`",
        f"- 地图 text-fallback 审查：`{controlled_text_fallback_review.get('status')}`，候选 `{controlled_text_fallback_review.get('candidate_count')}`，晋升 runtime `{controlled_text_fallback_review.get('runtime_promotion_count')}`，状态 `{controlled_text_fallback_review.get('review_status_counts')}`",
        "",
        md_table(["节点", "地图包", "路径", "塔位", "发布底图层"], package_rows),
        "",
        md_table(["节点", "地图编译包", "发布图状态", "对齐状态", "质量门", "玩法真相保留"], compile_rows),
        "",
        md_table(["节点", "晋升状态", "语义一致性", "发布图层", "阻断原因"], map_runtime_readiness_rows),
        "",
        md_table(["节点", "激活决策", "原因", "目标 v0.2 包", "阻断项"], map_runtime_activation_rows),
        "",
        md_table(["节点", "层角色", "权威性", "尺寸", "本地路径"], layer_rows),
        "",
        "## 4. 可用资产与媒体",
        "",
        f"- Frontend mock pack：`{assets.get('pack_id')}`",
        f"- 资产数：`{assets.get('asset_count')}`，可玩：`{assets.get('playable_count')}`",
        f"- Frontend mock core artifacts：`{frontend_pack_core.get('status')}`，review-only：`{frontend_pack_core.get('review_only')}`，schema：`{frontend_pack_core.get('schema_versions')}`",
        f"- published PNG 媒体：`{media.get('media_count')}` 个，覆盖资产：`{media.get('asset_count')}`",
        f"- published atlas：动画 `{atlas.get('animation_count')}` 个，帧 `{atlas.get('frame_count')}` 个，模式 `{atlas.get('atlas_mode')}`",
        f"- published sprite cutout 质量：`{sprite_quality.get('status')}`，需复核 `{sprite_quality.get('needs_review_count')}` / `{sprite_quality.get('sprite_item_count')}`",
        f"- published sprite repair plan：任务 `{sprite_repair.get('task_count')}` 个，优先级 `{as_obj(sprite_repair.get('priority_counts'))}`",
        f"- published sprite repair candidates：候选 `{sprite_candidates.get('candidate_count')}` 个，候选质量 `{sprite_candidates.get('quality_status')}`，已晋升 runtime：`{sprite_candidates.get('promoted_to_runtime')}`",
        f"- runtime art：美术对象 `{runtime_art.get('art_asset_count')}` 个，地图 token `{runtime_art.get('map_token_count')}` 个，程序化特效 `{runtime_art.get('procedural_effect_count')}` 个",
        f"- runtime art atlas：动画 `{runtime_art_atlas.get('animation_count')}` 个，帧 `{runtime_art_atlas.get('frame_count')}` 个，模式 `{runtime_art_atlas.get('atlas_mode')}`",
        f"- runtime sprite cutout 质量：`{runtime_sprite_quality.get('status')}`，需复核 `{runtime_sprite_quality.get('needs_review_count')}` / `{runtime_sprite_quality.get('sprite_item_count')}`",
        f"- runtime sprite repair plan：任务 `{runtime_sprite_repair.get('task_count')}` 个，优先级 `{as_obj(runtime_sprite_repair.get('priority_counts'))}`",
        f"- runtime sprite repair candidates：候选 `{runtime_sprite_candidates.get('candidate_count')}` 个，候选质量 `{runtime_sprite_candidates.get('quality_status')}`，已晋升 runtime：`{runtime_sprite_candidates.get('promoted_to_runtime')}`",
        f"- runtime sprite live regeneration：候选 `{runtime_sprite_regeneration.get('candidate_count')}` 个，真实生成 `{runtime_sprite_regeneration.get('generated_count')}` 个，候选质量 `{runtime_sprite_regeneration.get('quality_status')}`，已晋升 runtime：`{runtime_sprite_regeneration.get('promoted_to_runtime')}`",
        f"- runtime sprite promotion：显式晋升 `{runtime_sprite_promotion.get('promoted_count')}` 个，模式 `{runtime_sprite_promotion.get('mode')}`，atlas 需重建：`{as_obj(runtime_sprite_promotion.get('runtime_effect')).get('atlas_rebuild_required')}`",
        "",
        "## 5. 校验摘要",
        "",
        f"- 本次导出校验状态：`{export_validation.get('status')}`",
        f"- 历史 handoff audit：`{as_obj(validation.get('handoff_audit_report')).get('overall_status')}`",
        "",
        md_table(["校验项", "状态", "返回码", "命令"], validation_rows),
        "",
        "## 6. 前端入口说明",
        "",
        f"- 静态入口：`{frontend_entry.get('local_frontend_entry')}`",
        f"- 后端路由：`{frontend_entry.get('backend_entry')}`",
        f"- 主流程：`{' -> '.join(as_list(frontend_entry.get('primary_flow')))}`",
        f"- 静态媒体挂载：`{', '.join(as_list(frontend_entry.get('static_media_mounts')))}`",
        "",
        "## 7. 过滤策略",
        "",
        "本证据包只保留结构摘要、计数、公开媒体路径和文件指纹；不输出凭据字段值、原始提示词、外部生成器原始响应、完整执行轨迹或未审长文本内容。",
        "",
        "详细机器可读证据见 `evidence.json`；录屏/评审快速浏览见 `index.html`。",
        "",
    ]
    return "\n".join(lines)


def html_escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def render_validation_cards(results: list[Any]) -> str:
    cards = []
    for result in results:
        if not isinstance(result, dict):
            continue
        status = result.get("status")
        cards.append(
            f"""
            <article class="card">
              <div class="eyebrow">{html_escape(result.get("name"))}</div>
              <h3 class="{html_escape(status)}">{html_escape(status)}</h3>
              <p><code>{html_escape(result.get("command"))}</code></p>
              <p>返回码：{html_escape(result.get("return_code"))}</p>
            </article>
            """
        )
    return "\n".join(cards)


def render_layers(layers: list[Any]) -> str:
    rows = []
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        rows.append(
            "<tr>"
            f"<td>{html_escape(layer.get('role'))}</td>"
            f"<td>{html_escape(layer.get('authority') or 'reference_only')}</td>"
            f"<td>{html_escape(layer.get('width'))}x{html_escape(layer.get('height'))}</td>"
            f"<td><code>{html_escape(layer.get('local_path'))}</code></td>"
            "</tr>"
        )
    return "\n".join(rows)


def render_map_packages(packages: list[Any]) -> str:
    rows = []
    for package in packages:
        if not isinstance(package, dict):
            continue
        rows.append(
            "<tr>"
            f"<td><code>{html_escape(package.get('node_id'))}</code></td>"
            f"<td><code>{html_escape(package.get('package_id'))}</code></td>"
            f"<td>{html_escape(package.get('path_route_count'))}</td>"
            f"<td>{html_escape(package.get('build_slot_count'))}</td>"
            f"<td>{html_escape(package.get('published_visual_layer_count'))}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def render_map_compile_packages(packages: list[Any]) -> str:
    rows = []
    for package in packages:
        if not isinstance(package, dict):
            continue
        report = as_obj(package.get("validation_report"))
        rows.append(
            "<tr>"
            f"<td><code>{html_escape(package.get('node_id'))}</code></td>"
            f"<td><code>{html_escape(package.get('package_id'))}</code></td>"
            f"<td>{html_escape(package.get('painted_visual_status'))}</td>"
            f"<td>{html_escape(package.get('alignment_status'))}</td>"
            f"<td>{html_escape(package.get('quality_gate_count'))}</td>"
            f"<td>{html_escape(report.get('runtime_truth_preserved'))}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def render_asset_samples(samples: list[Any]) -> str:
    rows = []
    for item in samples:
        if not isinstance(item, dict):
            continue
        rows.append(
            "<tr>"
            f"<td>{html_escape(item.get('display_name'))}</td>"
            f"<td><code>{html_escape(item.get('stable_internal_id'))}</code></td>"
            f"<td>{html_escape(item.get('asset_type'))}</td>"
            f"<td>{html_escape(item.get('promotion_state'))}</td>"
            f"<td>{html_escape(', '.join(as_list(item.get('visual_recipe_types'))))}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def render_index_html(evidence: dict[str, Any]) -> str:
    project = as_obj(evidence.get("project_positioning"))
    readiness = as_obj(evidence.get("mvp_demo_readiness"))
    readiness_summary = as_obj(readiness.get("summary"))
    frontend_flow_visual = as_obj(
        as_obj(evidence.get("browser_visual_evidence")).get("frontend_flow")
    )
    ai_link = as_obj(evidence.get("ai_compilation_link"))
    counts = as_obj(ai_link.get("compiled_artifact_counts"))
    primary_flow_api = as_obj(
        as_obj(evidence.get("backend_api_evidence")).get("mvp_primary_flow")
    )
    map_packages = as_obj(evidence.get("map_runtime_packages"))
    map_packages_v02 = as_obj(evidence.get("map_runtime_packages_v02"))
    map_v02_api = as_obj(
        as_obj(evidence.get("backend_api_evidence")).get("map_v02_preview")
    )
    map_compile_packages = as_obj(evidence.get("map_compile_packages"))
    map_runtime_promotion_readiness = as_obj(
        evidence.get("map_runtime_promotion_readiness")
    )
    map_runtime_activation_gate = as_obj(evidence.get("map_runtime_activation_gate"))
    map_path_geometry = as_obj(evidence.get("map_path_geometry"))
    map_component_media_v02 = as_obj(evidence.get("map_component_media_v02_preview"))
    map_component_generation_pipeline = as_obj(
        evidence.get("map_component_generation_pipeline")
    )
    map_component_visual_quality = as_obj(
        map_component_generation_pipeline.get("visual_quality_gate")
    )
    map_component_promotion_gate = as_obj(
        map_component_generation_pipeline.get("promotion_gate")
    )
    map_component_manifest_patch_plan = as_obj(
        map_component_generation_pipeline.get("manifest_patch_plan")
    )
    scheduler = as_obj(evidence.get("generation_scheduler"))
    scheduler_summary = as_obj(scheduler.get("summary"))
    scheduler_run = as_obj(scheduler.get("run_report"))
    scheduler_run_summary = as_obj(scheduler_run.get("summary"))
    provider_runner_handoff = as_obj(scheduler.get("provider_runner_handoff"))
    provider_runner_handoff_roundtrip = as_obj(
        provider_runner_handoff.get("roundtrip_evidence")
    )
    background_tick = as_obj(scheduler.get("background_executor_tick"))
    background_tick_safety = as_obj(background_tick.get("safety"))
    background_handoff_tick = as_obj(scheduler.get("background_handoff_tick"))
    background_handoff_safety = as_obj(background_handoff_tick.get("safety"))
    provider_staging = as_obj(evidence.get("provider_artifact_staging"))
    provider_staging_source = as_obj(provider_staging.get("source"))
    provider_staging_promotion = as_obj(provider_staging.get("promotion_gate"))
    provider_promotion_report = as_obj(evidence.get("provider_artifact_promotion_report"))
    provider_image_staging = as_obj(evidence.get("provider_image_artifact_staging"))
    provider_image_staging_source = as_obj(provider_image_staging.get("source"))
    provider_image_staging_promotion = as_obj(
        provider_image_staging.get("promotion_gate")
    )
    provider_image_promotion_report = as_obj(
        evidence.get("provider_image_artifact_promotion_report")
    )
    world_transaction = as_obj(evidence.get("world_delta_transaction"))
    world_transaction_report = as_obj(world_transaction.get("validation_report"))
    world_transaction_chain = as_obj(evidence.get("world_delta_transaction_chain"))
    assets_media = as_obj(evidence.get("assets_and_media"))
    map_visual_quality = as_obj(
        as_obj(assets_media.get("map_visual_reference")).get("quality_audit")
    )
    map_visual_promotion_gate = as_obj(
        as_obj(assets_media.get("map_visual_reference")).get("promotion_gate")
    )
    node_map_candidate_review = as_obj(
        as_obj(assets_media.get("map_visual_reference")).get("candidate_review")
    )
    map_candidate_alignment = as_obj(
        as_obj(assets_media.get("map_visual_reference")).get("alignment_review")
    )
    map_candidate_overlay = as_obj(
        as_obj(assets_media.get("map_visual_reference")).get("overlay_review")
    )
    map_candidate_overlay_visual = as_obj(
        as_obj(assets_media.get("map_visual_reference")).get("overlay_visual_review")
    )
    map_layout_reconciliation = as_obj(
        as_obj(assets_media.get("map_visual_reference")).get("layout_reconciliation_plan")
    )
    runtime_map_patches = as_obj(
        as_obj(assets_media.get("map_visual_reference")).get("runtime_patch_candidates")
    )
    map_patch_overlay = as_obj(
        as_obj(assets_media.get("map_visual_reference")).get("patch_overlay_review")
    )
    topology_prompt_pack = as_obj(
        as_obj(assets_media.get("map_visual_reference")).get("topology_prompt_pack")
    )
    topology_candidate_review = as_obj(
        as_obj(assets_media.get("map_visual_reference")).get("topology_candidate_review")
    )
    topology_alignment_review = as_obj(
        as_obj(assets_media.get("map_visual_reference")).get("topology_alignment_review")
    )
    topology_overlay_visual_review = as_obj(
        as_obj(assets_media.get("map_visual_reference")).get(
            "topology_overlay_visual_review"
        )
    )
    topology_control_sketch = as_obj(
        as_obj(assets_media.get("map_visual_reference")).get(
            "topology_control_sketch_pack"
        )
    )
    procedural_map_previews = as_obj(
        as_obj(assets_media.get("map_visual_reference")).get("procedural_map_previews")
    )
    procedural_map_previews_v02 = as_obj(
        as_obj(assets_media.get("map_visual_reference")).get("procedural_map_previews_v02")
    )
    controlled_regeneration_request = as_obj(
        as_obj(assets_media.get("map_visual_reference")).get(
            "controlled_regeneration_request_pack"
        )
    )
    controlled_candidate_generation = as_obj(
        as_obj(assets_media.get("map_visual_reference")).get(
            "controlled_candidate_generation_run"
        )
    )
    controlled_candidate_review = as_obj(
        as_obj(assets_media.get("map_visual_reference")).get(
            "controlled_candidate_review"
        )
    )
    controlled_text_fallback_generation = as_obj(
        as_obj(assets_media.get("map_visual_reference")).get(
            "controlled_text_fallback_generation_run"
        )
    )
    controlled_text_fallback_review = as_obj(
        as_obj(assets_media.get("map_visual_reference")).get(
            "controlled_text_fallback_candidate_review"
        )
    )
    frontend_pack = as_obj(assets_media.get("frontend_pack"))
    published_media = as_obj(assets_media.get("published_asset_media"))
    published_atlas = as_obj(assets_media.get("published_asset_atlas"))
    published_sprite_quality = as_obj(assets_media.get("published_sprite_cutout_quality"))
    published_sprite_repair = as_obj(assets_media.get("published_sprite_repair_plan"))
    published_sprite_candidates = as_obj(assets_media.get("published_sprite_repair_candidates"))
    runtime_art = as_obj(assets_media.get("runtime_art"))
    runtime_art_atlas = as_obj(runtime_art.get("atlas_manifest"))
    runtime_sprite_quality = as_obj(runtime_art.get("sprite_cutout_quality"))
    runtime_sprite_repair = as_obj(runtime_art.get("sprite_repair_plan"))
    runtime_sprite_candidates = as_obj(runtime_art.get("sprite_repair_candidates"))
    runtime_sprite_regeneration = as_obj(runtime_art.get("sprite_regeneration_candidates"))
    runtime_sprite_promotion = as_obj(runtime_art.get("sprite_regeneration_promotion"))
    validation = as_obj(evidence.get("validation_summary"))
    export_validation = as_obj(validation.get("current_export_validation"))
    frontend_entry = as_obj(evidence.get("frontend_entry"))
    html_doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI 编译塔防 MVP 演示证据</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f7f4;
      --ink: #202124;
      --muted: #5f6368;
      --line: #d9d9d2;
      --panel: #ffffff;
      --accent: #2f6f6d;
      --good: #237044;
      --bad: #a5362f;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    header, main {{
      width: min(1120px, calc(100vw - 32px));
      margin: 0 auto;
    }}
    header {{
      padding: 42px 0 24px;
      border-bottom: 1px solid var(--line);
    }}
    h1 {{
      margin: 0 0 12px;
      font-size: 32px;
      line-height: 1.15;
      letter-spacing: 0;
    }}
    h2 {{
      margin: 34px 0 14px;
      font-size: 20px;
      letter-spacing: 0;
    }}
    h3 {{
      margin: 4px 0 10px;
      font-size: 18px;
      letter-spacing: 0;
    }}
    p {{ margin: 0 0 10px; }}
    code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 0.92em;
      word-break: break-word;
    }}
    .muted {{ color: var(--muted); }}
    .grid {{
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      margin: 18px 0 8px;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }}
    .metric {{
      font-size: 28px;
      line-height: 1;
      font-weight: 700;
      color: var(--accent);
    }}
    .status-metric {{
      font-size: 18px;
      line-height: 1.25;
      overflow-wrap: anywhere;
    }}
    .eyebrow {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }}
    th, td {{
      padding: 10px 12px;
      text-align: left;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
    }}
    th {{ background: #ecece6; font-weight: 650; }}
    tr:last-child td {{ border-bottom: 0; }}
    .passed {{ color: var(--good); }}
    .failed {{ color: var(--bad); }}
    .links a {{
      color: var(--accent);
      margin-right: 16px;
    }}
    footer {{
      margin: 38px 0 48px;
      color: var(--muted);
      border-top: 1px solid var(--line);
      padding-top: 18px;
    }}
  </style>
</head>
<body>
  <header>
    <h1>AI 编译塔防 MVP 演示证据</h1>
    <p>{html_escape(project.get("positioning"))}</p>
    <p class="muted">生成时间：<code>{html_escape(evidence.get("generated_at"))}</code></p>
    <p class="links"><a href="summary.md">summary.md</a><a href="evidence.json">evidence.json</a></p>
  </header>
  <main>
    <section>
      <h2>核心证据</h2>
      <div class="grid">
        <article class="card">
          <div class="eyebrow">MVP Readiness</div>
          <div class="metric status-metric">{html_escape(readiness.get("overall_status"))}</div>
          <p class="muted">必需 gate {html_escape(readiness_summary.get("required_gate_passed_or_expected_count"))} / {html_escape(readiness_summary.get("required_gate_count"))}；阻断 {html_escape(readiness_summary.get("blocking_gate_count"))}；warning {html_escape(readiness_summary.get("warning_gate_count"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">Browser Flow</div>
          <div class="metric status-metric">{html_escape(frontend_flow_visual.get("status"))}</div>
          <p class="muted">截图 {html_escape(frontend_flow_visual.get("captured_screenshot_count"))} / {html_escape(frontend_flow_visual.get("expected_screenshot_count"))}；视口 {html_escape(frontend_flow_visual.get("viewport_count"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">可玩资产</div>
          <div class="metric">{html_escape(counts.get("playable_assets"))}</div>
          <p class="muted">来自 frontend mock pack 的 reviewed playable 资产。</p>
        </article>
        <article class="card">
          <div class="eyebrow">MVP API Flow</div>
          <div class="metric">{html_escape(primary_flow_api.get("status"))}</div>
          <p class="muted">步骤 {html_escape(primary_flow_api.get("passed_step_count"))} / {html_escape(primary_flow_api.get("step_count"))}；节点 {html_escape(primary_flow_api.get("node_id"))}；transport {html_escape(primary_flow_api.get("transport"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">RuntimePackage</div>
          <div class="metric">{html_escape(counts.get("runtime_packages"))}</div>
          <p class="muted">已审 runtime package 摘要可供前端消费。</p>
        </article>
        <article class="card">
          <div class="eyebrow">调度项</div>
          <div class="metric">{html_escape(scheduler_summary.get("item_count"))}</div>
          <p class="muted">Generation Scheduler 计划包，包含同步、预取、后台、懒加载和静态 fallback。</p>
        </article>
        <article class="card">
          <div class="eyebrow">Provider 暂存</div>
          <div class="metric">{html_escape(provider_staging.get("staged_artifact_count"))}</div>
          <p class="muted">状态：{html_escape(provider_staging.get("staging_status"))}；promotion：{html_escape(provider_staging_promotion.get("blocked_reason"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">Provider 晋升</div>
          <div class="metric">{html_escape(provider_promotion_report.get("promotion_allowed"))}</div>
          <p class="muted">决策：{html_escape(provider_promotion_report.get("promotion_decision"))}；阻断：{html_escape(provider_promotion_report.get("blocked_reason"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">世界事务</div>
          <div class="metric">{html_escape(world_transaction_chain.get("transaction_count"))}</div>
          <p class="muted">{html_escape(world_transaction_report.get("gate_status"))}；事务链映射 {html_escape(world_transaction_chain.get("total_operation_mapping_count"))} 个 delta operation。</p>
        </article>
        <article class="card">
          <div class="eyebrow">MapRuntimePackage</div>
          <div class="metric">{html_escape(map_packages.get("package_count"))}</div>
          <p class="muted">地图包数量；包含路径、塔位、目标、出生点和视觉层。</p>
        </article>
        <article class="card">
          <div class="eyebrow">MapRuntime v0.2</div>
          <div class="metric">{html_escape(map_packages_v02.get("package_count"))}</div>
          <p class="muted">preview 旁路包；资源 {html_escape(map_packages_v02.get("total_resource_node_count"))}，机关 {html_escape(map_packages_v02.get("total_hazard_zone_count"))}，锚点 {html_escape(map_packages_v02.get("total_defense_anchor_count"))}，阻挡 {html_escape(map_packages_v02.get("total_blocked_area_count"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">Map v0.2 API</div>
          <div class="metric">{html_escape(map_v02_api.get("status"))}</div>
          <p class="muted">节点 {html_escape(map_v02_api.get("node_count"))}；默认 v0.1 保留 {html_escape(map_v02_api.get("default_runtime_v01_preserved_count"))}；provider calls {html_escape(as_obj(map_v02_api.get("safety")).get("provider_call_count"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">Map Runtime 晋升准备度</div>
          <div class="metric">{html_escape(map_runtime_promotion_readiness.get("promotion_candidate_count"))}/{html_escape(map_runtime_promotion_readiness.get("node_count"))}</div>
          <p class="muted">状态：{html_escape(map_runtime_promotion_readiness.get("status"))}；activation allowed {html_escape(map_runtime_promotion_readiness.get("activation_allowed_count"))}；blockers {html_escape(map_runtime_promotion_readiness.get("blocker_counts"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">Map Runtime 激活门</div>
          <div class="metric">{html_escape(map_runtime_activation_gate.get("status"))}</div>
          <p class="muted">允许 {html_escape(map_runtime_activation_gate.get("activation_allowed_count"))}；阻断 {html_escape(map_runtime_activation_gate.get("activation_blocked_count"))}；runtime 修改 {html_escape(as_obj(map_runtime_activation_gate.get("safety")).get("default_runtime_mutation_performed"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">地图路径几何审查</div>
          <div class="metric">{html_escape(map_path_geometry.get("status"))}</div>
          <p class="muted">地图 {html_escape(map_path_geometry.get("map_count"))}；路线 {html_escape(map_path_geometry.get("route_count"))}；塔位 {html_escape(map_path_geometry.get("build_slot_count"))}；warning {html_escape(map_path_geometry.get("warning_count"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">MapComponent v0.2 Preview</div>
          <div class="metric">{html_escape(map_component_media_v02.get("component_count"))}</div>
          <p class="muted">single images {html_escape(map_component_media_v02.get("single_image_count"))}；atlas {html_escape(map_component_media_v02.get("atlas_animation_count"))}；media kinds {html_escape(map_component_media_v02.get("media_kind_counts"))}；默认消费 {html_escape("no_frontend_default_consumption" in as_list(map_component_media_v02.get("usage_policy")))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">MapComponent Visual Gate</div>
          <div class="metric status-metric">{html_escape(map_component_visual_quality.get("status"))}</div>
          <p class="muted">generated {html_escape(map_component_visual_quality.get("generated_candidate_count"))}；checked {html_escape(map_component_visual_quality.get("checked_candidate_count"))}；runtime 修改 {html_escape(as_obj(map_component_visual_quality.get("runtime_effect")).get("runtime_map_truth_modified"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">MapComponent Promotion Gate</div>
          <div class="metric status-metric">{html_escape(map_component_promotion_gate.get("status"))}</div>
          <p class="muted">读取 visual gate {html_escape(map_component_promotion_gate.get("source_visual_quality_report_path"))}；状态 {html_escape(map_component_promotion_gate.get("visual_quality_report_status"))}；允许 {html_escape(map_component_promotion_gate.get("promotion_allowed_count"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">MapComponent Patch Plan</div>
          <div class="metric status-metric">{html_escape(map_component_manifest_patch_plan.get("status"))}</div>
          <p class="muted">patches {html_escape(map_component_manifest_patch_plan.get("patch_count"))}；ready {html_escape(map_component_manifest_patch_plan.get("ready_patch_count"))}；manifest 写入 {html_escape(as_obj(map_component_manifest_patch_plan.get("runtime_effect")).get("manifest_replacement_written"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">MapCompilePackage</div>
          <div class="metric">{html_escape(map_compile_packages.get("package_count"))}</div>
          <p class="muted">地图编译证据包；包含控制层、发布图、对齐和质量门。</p>
        </article>
        <article class="card">
          <div class="eyebrow">地图视觉审计</div>
          <div class="metric">{html_escape(map_visual_quality.get("status"))}</div>
          <p class="muted">共享玩家底图组：{html_escape(map_visual_quality.get("shared_player_visual_layer_group_count"))}；警告：{html_escape(map_visual_quality.get("warning_counts"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">地图发布闸门</div>
          <div class="metric">{html_escape(map_visual_promotion_gate.get("status"))}</div>
          <p class="muted">阻断候选：{html_escape(map_visual_promotion_gate.get("blocked_candidate_count"))}；published 图层：{html_escape(map_visual_promotion_gate.get("published_player_layer_count"))}；违规：{html_escape(map_visual_promotion_gate.get("violation_count"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">节点地图候选</div>
          <div class="metric">{html_escape(node_map_candidate_review.get("status"))}</div>
          <p class="muted">候选：{html_escape(node_map_candidate_review.get("candidate_count"))}；晋升 runtime：{html_escape(node_map_candidate_review.get("runtime_promotion_count"))}；状态：{html_escape(node_map_candidate_review.get("review_status_counts"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">地图候选对齐</div>
          <div class="metric">{html_escape(map_candidate_alignment.get("status"))}</div>
          <p class="muted">需尺寸标准化：{html_escape(map_candidate_alignment.get("transform_required_count"))}；阻断：{html_escape(map_candidate_alignment.get("blocked_count"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">地图候选 Overlay</div>
          <div class="metric">{html_escape(map_candidate_overlay.get("status"))}</div>
          <p class="muted">overlay artifacts：{html_escape(map_candidate_overlay.get("overlay_artifact_ready_count"))}；目标尺寸：{html_escape(map_candidate_overlay.get("target_size"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">地图候选复核</div>
          <div class="metric">{html_escape(map_candidate_overlay_visual.get("status"))}</div>
          <p class="muted">可晋升：{html_escape(map_candidate_overlay_visual.get("promotable_count"))}；禁止晋升：{html_escape(map_candidate_overlay_visual.get("blocked_from_promotion_count"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">地图布局修订</div>
          <div class="metric">{html_escape(map_layout_reconciliation.get("status"))}</div>
          <p class="muted">P0：{html_escape(map_layout_reconciliation.get("p0_count"))}；推荐：{html_escape(map_layout_reconciliation.get("recommendation_counts"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">地图补丁候选</div>
          <div class="metric">{html_escape(runtime_map_patches.get("status"))}</div>
          <p class="muted">review candidates：{html_escape(runtime_map_patches.get("review_candidate_count"))}；skipped：{html_escape(runtime_map_patches.get("skipped_count"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">补丁后 Overlay</div>
          <div class="metric">{html_escape(map_patch_overlay.get("status"))}</div>
          <p class="muted">可复核：{html_escape(map_patch_overlay.get("patched_overlay_artifact_ready_count"))}；校验失败：{html_escape(map_patch_overlay.get("validation_failed_count"))}；直接晋升：{html_escape(map_patch_overlay.get("promotion_allowed_now_count"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">拓扑 Prompt</div>
          <div class="metric">{html_escape(topology_prompt_pack.get("status"))}</div>
          <p class="muted">主 prompt：{html_escape(topology_prompt_pack.get("primary_prompt_count"))}；fallback：{html_escape(topology_prompt_pack.get("fallback_prompt_count"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">旧信号塔拓扑候选</div>
          <div class="metric">{html_escape(topology_overlay_visual_review.get("status"))}</div>
          <p class="muted">candidate：{html_escape(topology_candidate_review.get("status"))}；alignment：{html_escape(topology_alignment_review.get("status"))}；可晋升：{html_escape(topology_overlay_visual_review.get("promotable_count"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">Topology Control Sketch</div>
          <div class="metric">{html_escape(topology_control_sketch.get("status"))}</div>
          <p class="muted">sketch：{html_escape(topology_control_sketch.get("sketch_count"))}；ready：{html_escape(topology_control_sketch.get("ready_count"))}；目标尺寸：{html_escape(topology_control_sketch.get("target_size"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">RenderPlan 预览</div>
          <div class="metric">{html_escape(procedural_map_previews.get("ready_count"))}/{html_escape(procedural_map_previews.get("report_count"))}</div>
          <p class="muted">离线 SVG 预览只作为 review-only evidence；策略：{html_escape(procedural_map_previews.get("runtime_activation_policy"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">RenderPlan v0.2 语义预览</div>
          <div class="metric">{html_escape(procedural_map_previews_v02.get("ready_count"))}/{html_escape(procedural_map_previews_v02.get("report_count"))}</div>
          <p class="muted">资源/危险/防守锚点/阻挡区旁路预览；策略：{html_escape(procedural_map_previews_v02.get("runtime_activation_policy"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">受控重生请求</div>
          <div class="metric">{html_escape(controlled_regeneration_request.get("status"))}</div>
          <p class="muted">request：{html_escape(controlled_regeneration_request.get("request_count"))}；reference image：{html_escape(controlled_regeneration_request.get("reference_image_request_count"))}；blocked：{html_escape(controlled_regeneration_request.get("blocked_count"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">受控候选 Dry-run</div>
          <div class="metric">{html_escape(controlled_candidate_generation.get("status"))}</div>
          <p class="muted">handoff：{html_escape(controlled_candidate_generation.get("handoff_ready_count"))}；图片：{html_escape(controlled_candidate_generation.get("image_exists_count"))}；provider calls：{html_escape(controlled_candidate_generation.get("provider_call_count"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">受控候选审查</div>
          <div class="metric">{html_escape(controlled_candidate_review.get("status"))}</div>
          <p class="muted">候选：{html_escape(controlled_candidate_review.get("candidate_count"))}；晋升 runtime：{html_escape(controlled_candidate_review.get("runtime_promotion_count"))}；状态：{html_escape(controlled_candidate_review.get("review_status_counts"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">Text-fallback 真实生成</div>
          <div class="metric">{html_escape(controlled_text_fallback_generation.get("status"))}</div>
          <p class="muted">图片：{html_escape(controlled_text_fallback_generation.get("image_exists_count"))}；provider calls：{html_escape(controlled_text_fallback_generation.get("provider_call_count"))}；provider：{html_escape(controlled_text_fallback_generation.get("provider_profile"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">Text-fallback 审查</div>
          <div class="metric">{html_escape(controlled_text_fallback_review.get("status"))}</div>
          <p class="muted">候选：{html_escape(controlled_text_fallback_review.get("candidate_count"))}；晋升 runtime：{html_escape(controlled_text_fallback_review.get("runtime_promotion_count"))}；状态：{html_escape(controlled_text_fallback_review.get("review_status_counts"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">媒体</div>
          <div class="metric">{html_escape(published_media.get("media_count"))}</div>
          <p class="muted">published PNG，可由前端静态挂载读取。</p>
        </article>
        <article class="card">
          <div class="eyebrow">Atlas 动画</div>
          <div class="metric">{html_escape(published_atlas.get("animation_count"))}</div>
          <p class="muted">{html_escape(published_atlas.get("atlas_mode"))} 动画入口；sprite 已可按帧播放。</p>
        </article>
        <article class="card">
          <div class="eyebrow">Sprite 复核</div>
          <div class="metric">{html_escape(published_sprite_quality.get("needs_review_count"))}/{html_escape(published_sprite_quality.get("sprite_item_count"))}</div>
          <p class="muted">前端 mock sprite cutout 自动审查，状态：{html_escape(published_sprite_quality.get("status"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">Runtime Sprite 复核</div>
          <div class="metric">{html_escape(runtime_sprite_quality.get("needs_review_count"))}/{html_escape(runtime_sprite_quality.get("sprite_item_count"))}</div>
          <p class="muted">战斗运行时 sprite cutout 自动审查，状态：{html_escape(runtime_sprite_quality.get("status"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">Sprite 修复任务</div>
          <div class="metric">{html_escape(published_sprite_repair.get("task_count"))}</div>
          <p class="muted">前端 mock sprite repair plan，优先级：{html_escape(published_sprite_repair.get("priority_counts"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">Runtime 修复任务</div>
          <div class="metric">{html_escape(runtime_sprite_repair.get("task_count"))}</div>
          <p class="muted">战斗运行时 sprite repair plan，优先级：{html_escape(runtime_sprite_repair.get("priority_counts"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">Sprite 候选</div>
          <div class="metric">{html_escape(published_sprite_candidates.get("candidate_count"))}</div>
          <p class="muted">候选质量：{html_escape(published_sprite_candidates.get("quality_status"))}；未晋升 runtime。</p>
        </article>
        <article class="card">
          <div class="eyebrow">Runtime 候选</div>
          <div class="metric">{html_escape(runtime_sprite_candidates.get("candidate_count"))}</div>
          <p class="muted">候选质量：{html_escape(runtime_sprite_candidates.get("quality_status"))}；未替换正式战斗素材。</p>
        </article>
        <article class="card">
          <div class="eyebrow">Runtime 真实重生</div>
          <div class="metric">{html_escape(runtime_sprite_regeneration.get("generated_count"))}</div>
          <p class="muted">review-only 候选：{html_escape(runtime_sprite_regeneration.get("candidate_count"))}；质量：{html_escape(runtime_sprite_regeneration.get("quality_status"))}。</p>
        </article>
        <article class="card">
          <div class="eyebrow">Runtime 显式晋升</div>
          <div class="metric">{html_escape(runtime_sprite_promotion.get("promoted_count"))}</div>
          <p class="muted">模式：{html_escape(runtime_sprite_promotion.get("mode"))}；候选通过审查后才替换 runtime 素材。</p>
        </article>
      </div>
    </section>
    <section>
      <h2>AI 编译链路</h2>
      <p>演示 readiness：<code>{html_escape(readiness.get("overall_status"))}</code>；预期阻断：<code>{html_escape(readiness_summary.get("expected_block_count"))}</code>；报告自身 provider 调用：<code>{html_escape(readiness_summary.get("provider_call_count_by_report"))}</code>。</p>
      <p>{html_escape(ai_link.get("claim"))}</p>
      <p>链路步骤：<code>{html_escape(" -> ".join(as_list(ai_link.get("pipeline_steps"))))}</code></p>
      <p class="muted">本页面只展示摘要、路径和文件指纹；内部生成细节已过滤。</p>
    </section>
    <section>
      <h2>Generation Scheduler</h2>
      <p>计划包：<code>{html_escape(scheduler.get("plan_id"))}</code>；延迟分布：<code>{html_escape(scheduler_summary.get("latency_class_counts"))}</code></p>
      <p>dry-run：<code>{html_escape(scheduler_run.get("report_id"))}</code>；动作分布：<code>{html_escape(scheduler_run_summary.get("action_counts"))}</code></p>
      <p>runner handoff：<code>{html_escape(provider_runner_handoff.get("status"))}</code>；roundtrip cache：<code>{html_escape(provider_runner_handoff_roundtrip.get("expected_cache_status"))}</code>；runtime 激活：<code>{html_escape(provider_runner_handoff_roundtrip.get("runtime_activation_allowed"))}</code></p>
      <p>background tick：<code>{html_escape(background_tick.get("status"))}</code>；默认预算：<code>{html_escape(background_tick.get("default_max_items"))}</code>；provider 调用：<code>{html_escape(background_tick_safety.get("api_calls_provider"))}</code>；runtime 激活：<code>{html_escape(background_tick_safety.get("api_activates_runtime"))}</code></p>
      <p>background handoff tick：<code>{html_escape(background_handoff_tick.get("status"))}</code>；outbox：<code>{html_escape(background_handoff_tick.get("outbox_status"))}</code>；handoff 数：<code>{html_escape(background_handoff_tick.get("expected_runner_handoff_count"))}</code>；运行 adapter：<code>{html_escape(background_handoff_safety.get("api_runs_provider_adapter"))}</code></p>
      <p class="muted">构建器不读取环境、不调用 provider；预取内容启用前必须重新通过对应校验门。</p>
    </section>
    <section>
      <h2>ProviderArtifactStaging</h2>
      <p>暂存清单：<code>{html_escape(provider_staging.get("manifest_id"))}</code>；source envelope：<code>{html_escape(provider_staging.get("source_envelope_id"))}</code></p>
      <p>调用状态：<code>{html_escape(provider_staging_source.get("provider_call_status"))}</code>；暂存 artifact：<code>{html_escape(provider_staging.get("staged_artifact_count"))}</code>；promotion allowed：<code>{html_escape(provider_staging_promotion.get("promotion_allowed"))}</code></p>
      <p class="muted">该层只展示本地 review-only refs 和 gate 状态，不能被前端或战斗运行时直接消费。</p>
    </section>
    <section>
      <h2>ProviderArtifactPromotionReport</h2>
      <p>报告：<code>{html_escape(provider_promotion_report.get("report_id"))}</code>；source staging：<code>{html_escape(provider_promotion_report.get("source_staging_id"))}</code></p>
      <p>决策：<code>{html_escape(provider_promotion_report.get("promotion_decision"))}</code>；允许晋升：<code>{html_escape(provider_promotion_report.get("promotion_allowed"))}</code>；target：<code>{html_escape(as_obj(provider_promotion_report.get("promotion_targets")).get("target_kind"))}</code></p>
      <p class="muted">当前报告阻断候选继续进入 runtime / world 构建，因为媒体、语义和人工审查尚未完成。</p>
    </section>
    <section>
      <h2>Image Artifact Gate</h2>
      <p>图片暂存：<code>{html_escape(provider_image_staging.get("manifest_id"))}</code>；source envelope：<code>{html_escape(provider_image_staging.get("source_envelope_id"))}</code></p>
      <p>调用状态：<code>{html_escape(provider_image_staging_source.get("provider_call_status"))}</code>；暂存状态：<code>{html_escape(provider_image_staging.get("staging_status"))}</code>；阻断：<code>{html_escape(provider_image_staging_promotion.get("blocked_reason"))}</code></p>
      <p>晋升报告：<code>{html_escape(provider_image_promotion_report.get("report_id"))}</code>；决策：<code>{html_escape(provider_image_promotion_report.get("promotion_decision"))}</code>；允许晋升：<code>{html_escape(provider_image_promotion_report.get("promotion_allowed"))}</code></p>
      <p class="muted">真实图片候选可以进入本地 evidence，但质量门失败后必须保留为负样本，不能进入 MapRuntimePackage、published media 或玩家 runtime。</p>
    </section>
    <section>
      <h2>MapRuntimePackage 覆盖</h2>
      <table>
        <thead><tr><th>节点</th><th>地图包</th><th>路径</th><th>塔位</th><th>发布底图层</th></tr></thead>
        <tbody>{render_map_packages(as_list(map_packages.get("packages")))}</tbody>
      </table>
    </section>
    <section>
      <h2>MapCompilePackage 编译证据</h2>
      <table>
        <thead><tr><th>节点</th><th>地图编译包</th><th>发布图状态</th><th>对齐状态</th><th>质量门</th><th>玩法真相保留</th></tr></thead>
        <tbody>{render_map_compile_packages(as_list(map_compile_packages.get("packages")))}</tbody>
      </table>
    </section>
    <section>
      <h2>MapRuntimePackage 视觉层</h2>
      <table>
        <thead><tr><th>角色</th><th>权威性</th><th>尺寸</th><th>本地路径</th></tr></thead>
        <tbody>{render_layers([layer for package in as_list(map_packages.get("packages")) if isinstance(package, dict) for layer in as_list(package.get("visual_layers"))])}</tbody>
      </table>
    </section>
    <section>
      <h2>资产样例</h2>
      <table>
        <thead><tr><th>名称</th><th>ID</th><th>类型</th><th>状态</th><th>视觉 recipe</th></tr></thead>
        <tbody>{render_asset_samples(as_list(frontend_pack.get("asset_samples")))}</tbody>
      </table>
    </section>
    <section>
      <h2>运行时美术</h2>
      <div class="grid">
        <article class="card"><div class="eyebrow">美术对象</div><div class="metric">{html_escape(runtime_art.get("art_asset_count"))}</div></article>
        <article class="card"><div class="eyebrow">地图 token</div><div class="metric">{html_escape(runtime_art.get("map_token_count"))}</div></article>
        <article class="card"><div class="eyebrow">程序化特效</div><div class="metric">{html_escape(runtime_art.get("procedural_effect_count"))}</div></article>
        <article class="card"><div class="eyebrow">Runtime Atlas</div><div class="metric">{html_escape(runtime_art_atlas.get("animation_count"))}</div></article>
      </div>
    </section>
    <section>
      <h2>校验结果</h2>
      <p>本次导出校验状态：<strong class="{html_escape(export_validation.get("status"))}">{html_escape(export_validation.get("status"))}</strong></p>
      <div class="grid">{render_validation_cards(as_list(export_validation.get("results")))}</div>
    </section>
    <section>
      <h2>前端入口</h2>
      <p>静态入口：<code>{html_escape(frontend_entry.get("local_frontend_entry"))}</code></p>
      <p>后端路由：<code>{html_escape(frontend_entry.get("backend_entry"))}</code></p>
      <p>主流程：<code>{html_escape(" -> ".join(as_list(frontend_entry.get("primary_flow"))))}</code></p>
    </section>
    <footer>
      <p>过滤边界：不输出凭据字段值、原始提示词、外部生成器原始响应、完整执行轨迹或未审长文本内容。</p>
    </footer>
  </main>
</body>
</html>
"""
    return html_doc


def export_bundle(
    output_dir: Path,
    frontend_flow_visual_smoke_report_path: Path | None = None,
) -> dict[str, Any]:
    evidence = build_evidence(frontend_flow_visual_smoke_report_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "evidence.json", evidence)
    write_text(output_dir / "summary.md", render_summary_markdown(evidence))
    write_text(output_dir / "index.html", render_index_html(evidence))
    return evidence


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="导出 AI 编译塔防 MVP 演示证据包。"
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="输出目录，默认写入仓库内 demo_evidence/。",
    )
    parser.add_argument(
        "--frontend-flow-smoke-report",
        type=Path,
        help="可选：浏览器玩家链路截图 smoke report 路径；传入后纳入 evidence 摘要。",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    output_dir = Path(args.output_dir).expanduser()
    frontend_flow_report = (
        args.frontend_flow_smoke_report.expanduser()
        if args.frontend_flow_smoke_report
        else None
    )
    evidence = export_bundle(output_dir, frontend_flow_report)
    validation = as_obj(evidence.get("validation_summary"))
    export_validation = as_obj(validation.get("current_export_validation"))
    print("演示证据包已导出")
    print(f"- 输出目录: {output_dir}")
    print(f"- summary.md: {output_dir / 'summary.md'}")
    print(f"- evidence.json: {output_dir / 'evidence.json'}")
    print(f"- index.html: {output_dir / 'index.html'}")
    print(f"- 校验状态: {export_validation.get('status')}")
    return 0 if export_validation.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
