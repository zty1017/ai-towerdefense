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
MAP_COMPILE_PACKAGE_DIR = ROOT / "examples/map_compile_packages"


PATHS = {
    "readme": ROOT / "README.md",
    "architecture_index": ROOT / "docs/CURRENT_ARCHITECTURE_INDEX.md",
    "ai_compilation_doc": ROOT / "docs/AI_COMPILATION_SYSTEM_V0_1.md",
    "asset_graph_doc": ROOT / "docs/ASSET_GRAPH_COMPILER_V0_1.md",
    "frontend_mock_api_doc": ROOT / "docs/FRONTEND_MOCK_API_V0_1.md",
    "frontend_runtime_art_doc": ROOT / "docs/FRONTEND_RUNTIME_MOCK_ART_KIT_V0_1.md",
    "demo_vertical_slice_doc": ROOT / "docs/DEMO_VERTICAL_SLICE.md",
    "frontend_mock_pack": ROOT / "examples/frontend_mock/frontend_mock_pack.v0.1.json",
    "runtime_art_kit": ROOT
    / "examples/frontend_mock/frontend_battle_mock_art_kit.v0.1.json",
    "runtime_package": ROOT / "examples/runtime_packages/mvp_demo.runtime_package.json",
    "frontend_media_manifest": ROOT
    / "game_data/media/frontend_mock/frontend_media_manifest.v0.1.json",
    "frontend_media_atlas_manifest": ROOT
    / "game_data/media/frontend_mock/frontend_media_atlas_manifest.v0.1.json",
    "runtime_art_media_manifest": ROOT
    / "game_data/media/frontend_runtime_mock/frontend_runtime_art_media_manifest.v0.1.json",
    "runtime_art_atlas_manifest": ROOT
    / "game_data/media/frontend_runtime_mock/frontend_runtime_art_atlas_manifest.v0.1.json",
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
    "map_visual_manifest": ROOT
    / "game_data/media/map_visual_reference/map_visual_reference_manifest.v0.1.json",
    "handoff_audit": ROOT / "examples/review_packs/mvp_handoff_audit_report.v0.1.json",
    "compiler_dossier": ROOT
    / "examples/review_packs/mvp_compiler_review_dossier.v0.1.json",
    "multistage_content_pack": ROOT
    / "examples/review_packs/mvp_multistage_content_pack.v0.1.json",
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


def map_compile_package_paths() -> list[Path]:
    return sorted(MAP_COMPILE_PACKAGE_DIR.glob("*.map_compile_package.json"))


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
        "published_visual_layer_count": sum(
            int(package.get("published_visual_layer_count") or 0) for package in packages
        ),
        "packages": packages,
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


def collect_assets_and_media(
    frontend_pack: dict[str, Any],
    frontend_media_manifest: dict[str, Any],
    frontend_media_atlas_manifest: dict[str, Any],
    frontend_sprite_quality_report: dict[str, Any],
    frontend_sprite_repair_plan: dict[str, Any],
    frontend_sprite_repair_candidates: dict[str, Any],
    frontend_sprite_repair_candidate_quality_report: dict[str, Any],
    runtime_art_kit: dict[str, Any],
    runtime_art_media_manifest: dict[str, Any],
    runtime_art_atlas_manifest: dict[str, Any],
    runtime_sprite_quality_report: dict[str, Any],
    runtime_sprite_repair_plan: dict[str, Any],
    runtime_sprite_repair_candidates: dict[str, Any],
    runtime_sprite_repair_candidate_quality_report: dict[str, Any],
    runtime_sprite_regeneration_candidates: dict[str, Any],
    runtime_sprite_regeneration_candidate_quality_report: dict[str, Any],
    runtime_sprite_regeneration_promotion_report: dict[str, Any],
    map_visual_manifest: dict[str, Any],
) -> dict[str, Any]:
    assets = [asset for asset in as_list(frontend_pack.get("assets")) if isinstance(asset, dict)]
    compiler_summary = as_obj(frontend_pack.get("compiler_summary"))
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
            "asset_samples": [safe_asset_summary(asset) for asset in assets[:MAX_SAMPLE_ITEMS]],
        },
        "published_asset_media": media_manifest_summary(frontend_media_manifest),
        "published_asset_atlas": atlas_manifest_summary(frontend_media_atlas_manifest),
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
            "/assets/frontend_runtime_mock/processed",
            "/assets/frontend_runtime_mock/generated",
            "/assets/frontend_runtime_mock/atlas_frames",
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
        ("frontend_mock_api_design", PATHS["frontend_mock_api_doc"]),
        ("frontend_runtime_art_design", PATHS["frontend_runtime_art_doc"]),
        ("demo_vertical_slice", PATHS["demo_vertical_slice_doc"]),
        ("frontend_mock_pack", PATHS["frontend_mock_pack"]),
        ("runtime_art_kit", PATHS["runtime_art_kit"]),
        ("runtime_package", PATHS["runtime_package"]),
        ("frontend_media_manifest", PATHS["frontend_media_manifest"]),
        ("frontend_media_atlas_manifest", PATHS["frontend_media_atlas_manifest"]),
        ("runtime_art_media_manifest", PATHS["runtime_art_media_manifest"]),
        ("runtime_art_atlas_manifest", PATHS["runtime_art_atlas_manifest"]),
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
        ("map_visual_manifest", PATHS["map_visual_manifest"]),
        ("handoff_audit", PATHS["handoff_audit"]),
        ("compiler_dossier", PATHS["compiler_dossier"]),
        ("multistage_content_pack", PATHS["multistage_content_pack"]),
    ]
    source_paths.extend(
        ("locked_manifest", path)
        for path in sorted((ROOT / "examples/locked_manifests").glob("*.json"))
    )
    source_paths.extend(
        ("map_runtime_package", path) for path in map_runtime_package_paths()
    )
    source_paths.extend(
        ("map_compile_package", path) for path in map_compile_package_paths()
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


def build_evidence() -> dict[str, Any]:
    frontend_pack = load_json(PATHS["frontend_mock_pack"])
    runtime_art_kit = load_json(PATHS["runtime_art_kit"])
    runtime_package = load_json(PATHS["runtime_package"])
    map_packages = [
        package
        for package in (load_json(path) for path in map_runtime_package_paths())
        if isinstance(package, dict)
    ]
    map_compile_packages = [
        package
        for package in (load_json(path) for path in map_compile_package_paths())
        if isinstance(package, dict)
    ]
    frontend_media_manifest = load_json(PATHS["frontend_media_manifest"])
    frontend_media_atlas_manifest = load_json(PATHS["frontend_media_atlas_manifest"])
    frontend_sprite_quality_report = load_json(PATHS["frontend_sprite_cutout_quality_report"])
    frontend_sprite_repair_plan = load_json(PATHS["frontend_sprite_cutout_repair_plan"])
    frontend_sprite_repair_candidates = load_json(PATHS["frontend_sprite_repair_candidates"])
    frontend_sprite_repair_candidate_quality_report = load_json(
        PATHS["frontend_sprite_repair_candidate_quality_report"]
    )
    runtime_art_media_manifest = load_json(PATHS["runtime_art_media_manifest"])
    runtime_art_atlas_manifest = load_json(PATHS["runtime_art_atlas_manifest"])
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
    map_visual_manifest = load_json(PATHS["map_visual_manifest"])
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
        "ai_compilation_link": collect_ai_compilation_link(
            frontend_pack, dossier, multistage_pack
        ),
        "map_runtime_packages": collect_map_runtime_packages(map_packages),
        "map_compile_packages": collect_map_compile_packages(map_compile_packages),
        "runtime_package": collect_runtime_package(runtime_package),
        "assets_and_media": collect_assets_and_media(
            frontend_pack,
            frontend_media_manifest,
            frontend_media_atlas_manifest,
            frontend_sprite_quality_report,
            frontend_sprite_repair_plan,
            frontend_sprite_repair_candidates,
            frontend_sprite_repair_candidate_quality_report,
            runtime_art_kit,
            runtime_art_media_manifest,
            runtime_art_atlas_manifest,
            runtime_sprite_quality_report,
            runtime_sprite_repair_plan,
            runtime_sprite_repair_candidates,
            runtime_sprite_repair_candidate_quality_report,
            runtime_sprite_regeneration_candidates,
            runtime_sprite_regeneration_candidate_quality_report,
            runtime_sprite_regeneration_promotion_report,
            map_visual_manifest,
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
    ai_link = as_obj(evidence.get("ai_compilation_link"))
    map_packages = as_obj(evidence.get("map_runtime_packages"))
    map_compile_packages = as_obj(evidence.get("map_compile_packages"))
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
        f"- 受控链路说明：{ai_link.get('claim')}",
        f"- 可玩资产数：`{as_obj(ai_link.get('compiled_artifact_counts')).get('playable_assets')}`",
        f"- runtime package 数：`{as_obj(ai_link.get('compiled_artifact_counts')).get('runtime_packages')}`",
        f"- 多阶段内容阶段数：`{ai_link.get('multistage_stage_count')}`",
        f"- 证据 workflow 文件数：`{len(as_list(ai_link.get('reviewed_workflow_files')))}`",
        f"- 摘要链路步骤：`{', '.join(as_list(ai_link.get('pipeline_steps')))}`",
        "",
        "## 2. Runtime 与地图包",
        "",
        f"- RuntimePackage：`{runtime_pkg.get('package_id')}`，战斗：{runtime_pkg.get('battle_display_name')}，资产数：`{runtime_pkg.get('asset_count')}`",
        f"- MapRuntimePackage 数：`{map_packages.get('package_count')}`，节点：`{', '.join(str(node) for node in as_list(map_packages.get('node_ids')))}`",
        f"- MapCompilePackage 数：`{map_compile_packages.get('package_count')}`，节点：`{', '.join(str(node) for node in as_list(map_compile_packages.get('node_ids')))}`",
        f"- 总塔位：`{map_packages.get('total_build_slot_count')}`，总路径：`{map_packages.get('total_path_route_count')}`，出生点：`{map_packages.get('total_spawn_point_count')}`",
        f"- published visual layer 总数：`{map_packages.get('published_visual_layer_count')}`",
        "",
        md_table(["节点", "地图包", "路径", "塔位", "发布底图层"], package_rows),
        "",
        md_table(["节点", "地图编译包", "发布图状态", "对齐状态", "质量门", "玩法真相保留"], compile_rows),
        "",
        md_table(["节点", "层角色", "权威性", "尺寸", "本地路径"], layer_rows),
        "",
        "## 3. 可用资产与媒体",
        "",
        f"- Frontend mock pack：`{assets.get('pack_id')}`",
        f"- 资产数：`{assets.get('asset_count')}`，可玩：`{assets.get('playable_count')}`",
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
        "## 4. 校验摘要",
        "",
        f"- 本次导出校验状态：`{export_validation.get('status')}`",
        f"- 历史 handoff audit：`{as_obj(validation.get('handoff_audit_report')).get('overall_status')}`",
        "",
        md_table(["校验项", "状态", "返回码", "命令"], validation_rows),
        "",
        "## 5. 前端入口说明",
        "",
        f"- 静态入口：`{frontend_entry.get('local_frontend_entry')}`",
        f"- 后端路由：`{frontend_entry.get('backend_entry')}`",
        f"- 主流程：`{' -> '.join(as_list(frontend_entry.get('primary_flow')))}`",
        f"- 静态媒体挂载：`{', '.join(as_list(frontend_entry.get('static_media_mounts')))}`",
        "",
        "## 6. 过滤策略",
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
    ai_link = as_obj(evidence.get("ai_compilation_link"))
    counts = as_obj(ai_link.get("compiled_artifact_counts"))
    map_packages = as_obj(evidence.get("map_runtime_packages"))
    map_compile_packages = as_obj(evidence.get("map_compile_packages"))
    assets_media = as_obj(evidence.get("assets_and_media"))
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
          <div class="eyebrow">可玩资产</div>
          <div class="metric">{html_escape(counts.get("playable_assets"))}</div>
          <p class="muted">来自 frontend mock pack 的 reviewed playable 资产。</p>
        </article>
        <article class="card">
          <div class="eyebrow">RuntimePackage</div>
          <div class="metric">{html_escape(counts.get("runtime_packages"))}</div>
          <p class="muted">已审 runtime package 摘要可供前端消费。</p>
        </article>
        <article class="card">
          <div class="eyebrow">MapRuntimePackage</div>
          <div class="metric">{html_escape(map_packages.get("package_count"))}</div>
          <p class="muted">地图包数量；包含路径、塔位、目标、出生点和视觉层。</p>
        </article>
        <article class="card">
          <div class="eyebrow">MapCompilePackage</div>
          <div class="metric">{html_escape(map_compile_packages.get("package_count"))}</div>
          <p class="muted">地图编译证据包；包含控制层、发布图、对齐和质量门。</p>
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
      <p>{html_escape(ai_link.get("claim"))}</p>
      <p>链路步骤：<code>{html_escape(" -> ".join(as_list(ai_link.get("pipeline_steps"))))}</code></p>
      <p class="muted">本页面只展示摘要、路径和文件指纹；内部生成细节已过滤。</p>
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


def export_bundle(output_dir: Path) -> dict[str, Any]:
    evidence = build_evidence()
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
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    output_dir = Path(args.output_dir).expanduser()
    evidence = export_bundle(output_dir)
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
