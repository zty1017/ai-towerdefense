#!/usr/bin/env python3
"""Build a stage-by-stage promotion report for the MVP story asset review pack.

This tool is intentionally offline. It does not read .env, does not call
providers, and does not build a frontend/runtime package. It combines the
existing deterministic asset promotion policy with the stricter review-pack
governance layer: runtime fixtures remain fixtures, candidate-only assets stay
candidate-only, and high-risk assets are blocked from default MVP inclusion.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CONTENT_PIPELINE_DIR = Path(__file__).resolve().parent
if str(CONTENT_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(CONTENT_PIPELINE_DIR))

import asset_promotion_policy  # noqa: E402
import score_asset_candidate  # noqa: E402
import simulate_asset_candidate  # noqa: E402
import validate_asset_candidate  # noqa: E402


REPORT_VERSION = "mvp_story_asset_promotion_report.v0.1"
DEFAULT_REVIEW_PACK = ROOT / "examples/review_packs/mvp_story_asset_review_pack.v0.1.json"
DEFAULT_OUTPUT = ROOT / "examples/review_packs/mvp_story_asset_promotion_report.v0.1.json"
EFFECT_REGISTRY = ROOT / "shared/module_registry/effect_blocks.v0.1.json"
ASSET_PROMOTION_SCHEMA = ROOT / "shared/schemas/asset_promotion_report.v0.1.schema.json"


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


def stable_list(values: list[str]) -> list[str]:
    return sorted({value for value in values if value})


def resolve_repo_path(raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else ROOT / path


def canonical_sets(review_pack: dict[str, Any]) -> tuple[set[str], set[str], set[str], set[str]]:
    boundaries = as_obj(review_pack.get("canonical_boundaries"))
    canonical_npcs = {
        str(item.get("npc_id"))
        for item in as_list(boundaries.get("canonical_npcs"))
        if isinstance(item, dict) and item.get("npc_id")
    }
    candidate_npcs = {
        str(item.get("npc_id"))
        for item in as_list(boundaries.get("candidate_functional_npcs"))
        if isinstance(item, dict) and item.get("npc_id")
    }
    canonical_materials = {str(item) for item in as_list(boundaries.get("canonical_materials"))}
    candidate_materials = {
        str(item.get("material_id"))
        for item in as_list(boundaries.get("candidate_only_materials"))
        if isinstance(item, dict) and item.get("material_id")
    }
    return canonical_npcs, candidate_npcs, canonical_materials, candidate_materials


def validate_promotion_report_schema(report: dict[str, Any]) -> dict[str, Any]:
    if not ASSET_PROMOTION_SCHEMA.exists():
        return {"status": "missing_schema", "schema_path": str(ASSET_PROMOTION_SCHEMA.relative_to(ROOT))}

    try:
        import jsonschema
    except ImportError:
        required = {
            "promotion_version",
            "candidate_id",
            "asset_type",
            "promotion_state",
            "playable",
            "uses_fallback_media",
            "gameplay_core_state",
            "media_state",
            "blockers",
            "warnings",
            "required_next_actions",
            "fallback_media_strategy",
            "source_summary",
        }
        missing = sorted(required - set(report))
        return {
            "status": "fallback_required_field_check",
            "schema_path": str(ASSET_PROMOTION_SCHEMA.relative_to(ROOT)),
            "missing_required_fields": missing,
        }

    schema = load_json(ASSET_PROMOTION_SCHEMA)
    validator_cls = getattr(jsonschema, "Draft202012Validator", None)
    if validator_cls is None:
        try:
            jsonschema.validate(report, schema)
        except jsonschema.ValidationError as error:
            return {
                "status": "failed",
                "schema_path": str(ASSET_PROMOTION_SCHEMA.relative_to(ROOT)),
                "errors": [
                    {
                        "path": ".".join(str(part) for part in error.path),
                        "message": error.message,
                    }
                ],
            }
        return {
            "status": "passed_legacy_jsonschema",
            "schema_path": str(ASSET_PROMOTION_SCHEMA.relative_to(ROOT)),
            "errors": [],
        }

    validator = validator_cls(schema)
    errors = sorted(validator.iter_errors(report), key=lambda error: list(error.path))
    return {
        "status": "passed" if not errors else "failed",
        "schema_path": str(ASSET_PROMOTION_SCHEMA.relative_to(ROOT)),
        "errors": [
            {
                "path": ".".join(str(part) for part in error.path),
                "message": error.message,
            }
            for error in errors
        ],
    }


def build_policy_report(candidate: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    validation_errors = validate_asset_candidate.validate(candidate, registry)
    validation = {
        "status": "passed" if not validation_errors else "failed",
        "errors": validation_errors,
        "candidate_id": candidate.get("id"),
    }
    simulation = simulate_asset_candidate.simulate(
        candidate,
        simulate_asset_candidate.DEFAULT_DURATION_SECONDS,
    )
    score = score_asset_candidate.score_candidate(
        candidate,
        validation=validation,
        simulation=simulation,
        media_metadata=None,
    )
    promotion = asset_promotion_policy.evaluate_promotion(
        candidate,
        validation=validation,
        simulation=simulation,
        candidate_score=score,
        runtime_readiness=None,
    )
    return {
        "validation": validation,
        "simulation": simulation,
        "score": score,
        "promotion": promotion,
        "promotion_schema_check": validate_promotion_report_schema(promotion),
    }


def runtime_package_contains_asset(package: dict[str, Any], asset_id: str) -> bool:
    for asset in as_list(package.get("assets")):
        if isinstance(asset, dict) and asset.get("stable_internal_id") == asset_id:
            return True
    return False


def runtime_fixture_entry(stage: dict[str, Any], asset_ref: dict[str, Any], source_path: Path) -> dict[str, Any]:
    asset_id = str(asset_ref.get("asset_id", "unknown_asset"))
    blockers: list[str] = []
    warnings: list[str] = []
    source_exists = source_path.exists()
    package_id = None
    asset_found = False
    if source_exists:
        package = load_json(source_path)
        package_id = package.get("package_id") if isinstance(package, dict) else None
        asset_found = isinstance(package, dict) and runtime_package_contains_asset(package, asset_id)
        if not asset_found:
            blockers.append("runtime_package_asset_not_found")
    else:
        blockers.append("source_file_missing")

    state = "usable_runtime_fixture" if source_exists and asset_found else "missing_source"
    playable = state == "usable_runtime_fixture"
    return {
        "stage_id": stage.get("stage_id"),
        "stage_order": stage.get("order"),
        "asset_id": asset_id,
        "asset_kind": asset_ref.get("asset_kind"),
        "source_file": asset_ref.get("source_file"),
        "source_kind": "runtime_package_fixture",
        "source_exists": source_exists,
        "source_asset_found": asset_found,
        "package_id": package_id,
        "review_status": asset_ref.get("review_status"),
        "promotion_state": state,
        "policy_promotion_state": None,
        "playable": playable,
        "uses_fallback_media": False,
        "blocking_reasons": blockers,
        "warnings": warnings,
        "required_next_actions": [
            "keep_as_first_battle_mid_delivery_fixture",
            "do_not_treat_as_compiled_asset_promotion",
        ] if playable else [
            "repair_or_restore_runtime_package_fixture",
        ],
        "gameplay_role": asset_ref.get("gameplay_role"),
    }


def final_compiled_asset_state(
    asset_ref: dict[str, Any],
    policy_promotion: dict[str, Any],
    unregistered_materials: list[str],
    unregistered_npcs: list[str],
) -> tuple[str, bool, bool, list[str], list[str], list[str]]:
    review_status = str(asset_ref.get("review_status", ""))
    blockers: list[str] = []
    warnings: list[str] = []
    actions: list[str] = []

    if unregistered_materials:
        blockers.append(f"unregistered_materials:{','.join(unregistered_materials)}")
        actions.append(f"register_or_replace_materials:{','.join(unregistered_materials)}")
    if unregistered_npcs:
        blockers.append(f"unregistered_npcs:{','.join(unregistered_npcs)}")
        actions.append(f"register_or_replace_npc_refs:{','.join(unregistered_npcs)}")

    if "candidate_only_high_risk" in review_status:
        blockers.append("candidate_only_high_risk")
        actions.extend([
            "keep_out_of_default_mvp_battle",
            "defer_until_power_grid_and_risk_context_exists",
            "run_deeper_balance_simulation_before_player_delivery",
        ])
        return "candidate_only_high_risk", False, False, blockers, warnings, stable_list(actions)

    if "candidate_only" in review_status:
        blockers.append(f"review_pack_status:{review_status}")
        actions.append("resolve_review_pack_candidate_status_before_runtime_package")
        state = "candidate_only_needs_world_registration" if (unregistered_materials or unregistered_npcs) else "candidate_only"
        return state, False, False, blockers, warnings, stable_list(actions)

    if blockers:
        actions.append("do_not_promote_until_world_registration_gate_passes")
        return "needs_world_registration", False, False, blockers, warnings, stable_list(actions)

    policy_state = str(policy_promotion.get("promotion_state", "failed"))
    policy_playable = bool(policy_promotion.get("playable"))
    policy_fallback = bool(policy_promotion.get("uses_fallback_media"))
    if policy_state == "runtime_ready":
        actions.append("promote_to_runtime_package_after_stage_review")
        return "runtime_ready", policy_playable, False, blockers, warnings, stable_list(actions)
    if policy_state == "fallback_ready":
        warnings.append("real_media_not_generated_or_not_runtime_ready")
        actions.extend(as_list(policy_promotion.get("required_next_actions")))
        actions.append("generate_or_promote_real_media_before_final_runtime_package")
        return "fallback_ready", policy_playable, policy_fallback, blockers, warnings, stable_list(actions)
    if policy_state == "preview_only":
        warnings.append("policy_requires_review_before_battle_delivery")
        actions.extend(as_list(policy_promotion.get("required_next_actions")))
        return "preview_only", False, policy_fallback, blockers, warnings, stable_list(actions)

    blockers.extend(str(item) for item in as_list(policy_promotion.get("blockers")))
    actions.extend(as_list(policy_promotion.get("required_next_actions")))
    return "failed", False, False, blockers, warnings, stable_list(actions)


def compiled_asset_entry(
    stage: dict[str, Any],
    asset_ref: dict[str, Any],
    source_path: Path,
    registry: dict[str, Any],
    canonical_npcs: set[str],
    candidate_npcs: set[str],
    canonical_materials: set[str],
    candidate_materials: set[str],
) -> dict[str, Any]:
    asset_id = str(asset_ref.get("asset_id", "unknown_asset"))
    if not source_path.exists():
        return {
            "stage_id": stage.get("stage_id"),
            "stage_order": stage.get("order"),
            "asset_id": asset_id,
            "asset_kind": asset_ref.get("asset_kind"),
            "source_file": asset_ref.get("source_file"),
            "source_kind": "compiled_asset",
            "source_exists": False,
            "review_status": asset_ref.get("review_status"),
            "promotion_state": "missing_source",
            "policy_promotion_state": None,
            "playable": False,
            "uses_fallback_media": False,
            "blocking_reasons": ["source_file_missing"],
            "warnings": [],
            "required_next_actions": ["restore_or_generate_compiled_asset_source"],
            "gameplay_role": asset_ref.get("gameplay_role"),
        }

    candidate = load_json(source_path)
    reports = build_policy_report(candidate, registry)
    provenance = as_obj(candidate.get("provenance"))
    material_ids = [str(item) for item in as_list(provenance.get("material_ids"))]
    npc_ids = [str(item) for item in as_list(provenance.get("npc_ids"))]
    unregistered_materials = [
        material_id
        for material_id in material_ids
        if material_id not in canonical_materials
    ]
    unregistered_npcs = [
        npc_id
        for npc_id in npc_ids
        if npc_id not in canonical_npcs and npc_id not in candidate_npcs
    ]
    candidate_only_material_hits = [
        material_id for material_id in unregistered_materials if material_id in candidate_materials
    ]
    candidate_only_npc_hits = [
        npc_id for npc_id in npc_ids if npc_id in candidate_npcs
    ]

    policy_promotion = as_obj(reports.get("promotion"))
    state, playable, fallback, blockers, warnings, actions = final_compiled_asset_state(
        asset_ref,
        policy_promotion,
        stable_list(unregistered_materials),
        stable_list(unregistered_npcs),
    )
    warnings.extend(str(item) for item in as_list(policy_promotion.get("warnings")))
    schema_check = as_obj(reports.get("promotion_schema_check"))
    if schema_check.get("status") == "failed":
        blockers.append("asset_promotion_report_schema_failed")
        actions.append("repair_asset_promotion_policy_output_schema")

    return {
        "stage_id": stage.get("stage_id"),
        "stage_order": stage.get("order"),
        "asset_id": asset_id,
        "compiled_candidate_id": candidate.get("id"),
        "asset_kind": asset_ref.get("asset_kind"),
        "source_file": asset_ref.get("source_file"),
        "source_kind": "compiled_asset",
        "source_exists": True,
        "review_status": asset_ref.get("review_status"),
        "promotion_state": state,
        "policy_promotion_state": policy_promotion.get("promotion_state"),
        "playable": playable,
        "uses_fallback_media": fallback,
        "blocking_reasons": stable_list(blockers),
        "warnings": stable_list(warnings),
        "required_next_actions": stable_list(actions),
        "gameplay_role": asset_ref.get("gameplay_role"),
        "world_registration": {
            "npc_ids": npc_ids,
            "material_ids": material_ids,
            "unregistered_npcs": stable_list(unregistered_npcs),
            "unregistered_materials": stable_list(unregistered_materials),
            "candidate_only_npc_hits": stable_list(candidate_only_npc_hits),
            "candidate_only_material_hits": stable_list(candidate_only_material_hits),
        },
        "policy_evidence": {
            "validation": reports["validation"],
            "simulation": {
                "simulation_focus": reports["simulation"].get("simulation_focus"),
                "estimated_dps": reports["simulation"].get("estimated_dps"),
                "utility_score": reports["simulation"].get("utility_score"),
                "cost_efficiency": reports["simulation"].get("cost_efficiency"),
                "balance_flags": reports["simulation"].get("balance_flags"),
            },
            "score": {
                "total_score": reports["score"].get("total_score"),
                "recommendation": reports["score"].get("recommendation"),
                "dimension_scores": reports["score"].get("dimension_scores"),
                "reasons": reports["score"].get("reasons"),
                "expected_media_roles": reports["score"].get("expected_media_roles"),
            },
            "promotion": policy_promotion,
            "promotion_schema_check": schema_check,
        },
    }


def evaluate_asset_ref(
    stage: dict[str, Any],
    asset_ref: dict[str, Any],
    registry: dict[str, Any],
    canonical_npcs: set[str],
    candidate_npcs: set[str],
    canonical_materials: set[str],
    candidate_materials: set[str],
) -> dict[str, Any]:
    raw_source = str(asset_ref.get("source_file", ""))
    source_path = resolve_repo_path(raw_source) if raw_source else ROOT
    if raw_source.startswith("examples/runtime_packages/"):
        return runtime_fixture_entry(stage, asset_ref, source_path)
    if raw_source.startswith("examples/compiled_assets/") and raw_source.endswith(".compiled_asset.json"):
        return compiled_asset_entry(
            stage,
            asset_ref,
            source_path,
            registry,
            canonical_npcs,
            candidate_npcs,
            canonical_materials,
            candidate_materials,
        )
    return {
        "stage_id": stage.get("stage_id"),
        "stage_order": stage.get("order"),
        "asset_id": asset_ref.get("asset_id"),
        "asset_kind": asset_ref.get("asset_kind"),
        "source_file": raw_source,
        "source_kind": "unsupported_source",
        "source_exists": bool(raw_source and source_path.exists()),
        "review_status": asset_ref.get("review_status"),
        "promotion_state": "unsupported_source",
        "policy_promotion_state": None,
        "playable": False,
        "uses_fallback_media": False,
        "blocking_reasons": ["unsupported_source_kind"],
        "warnings": [],
        "required_next_actions": ["add_source_kind_handler_or_fix_review_pack_ref"],
        "gameplay_role": asset_ref.get("gameplay_role"),
    }


def summarize(stage_reports: list[dict[str, Any]]) -> dict[str, Any]:
    all_assets = [
        asset
        for stage in stage_reports
        for asset in as_list(stage.get("assets"))
        if isinstance(asset, dict)
    ]
    by_state = Counter(str(asset.get("promotion_state")) for asset in all_assets)
    by_source_kind = Counter(str(asset.get("source_kind")) for asset in all_assets)
    unique_sources = {
        str(asset.get("source_file"))
        for asset in all_assets
        if asset.get("source_file")
    }
    unique_compiled_sources = {
        str(asset.get("source_file"))
        for asset in all_assets
        if asset.get("source_kind") == "compiled_asset" and asset.get("source_file")
    }
    return {
        "stage_count": len(stage_reports),
        "asset_reference_count": len(all_assets),
        "unique_source_count": len(unique_sources),
        "unique_compiled_asset_source_count": len(unique_compiled_sources),
        "playable_reference_count": sum(1 for asset in all_assets if asset.get("playable") is True),
        "fallback_ready_reference_count": by_state.get("fallback_ready", 0),
        "runtime_fixture_reference_count": by_state.get("usable_runtime_fixture", 0),
        "candidate_or_blocked_reference_count": sum(
            count
            for state, count in by_state.items()
            if state.startswith("candidate_only") or state in {"needs_world_registration", "failed", "missing_source"}
        ),
        "promotion_states": dict(sorted(by_state.items())),
        "source_kinds": dict(sorted(by_source_kind.items())),
    }


def rollup_assets(stage_reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for stage in stage_reports:
        for asset in as_list(stage.get("assets")):
            if isinstance(asset, dict):
                grouped[str(asset.get("asset_id"))].append(asset)

    rollup: list[dict[str, Any]] = []
    for asset_id, refs in sorted(grouped.items()):
        states = stable_list([str(ref.get("promotion_state")) for ref in refs])
        blockers: list[str] = []
        warnings: list[str] = []
        actions: list[str] = []
        for ref in refs:
            blockers.extend(str(item) for item in as_list(ref.get("blocking_reasons")))
            warnings.extend(str(item) for item in as_list(ref.get("warnings")))
            actions.extend(str(item) for item in as_list(ref.get("required_next_actions")))
        rollup.append({
            "asset_id": asset_id,
            "source_file": refs[0].get("source_file"),
            "source_kind": refs[0].get("source_kind"),
            "appears_in_stages": [
                {
                    "stage_order": ref.get("stage_order"),
                    "stage_id": ref.get("stage_id"),
                    "promotion_state": ref.get("promotion_state"),
                    "playable": ref.get("playable"),
                }
                for ref in refs
            ],
            "overall_state": states[0] if len(states) == 1 else "mixed",
            "playable_anywhere": any(ref.get("playable") is True for ref in refs),
            "uses_fallback_media_anywhere": any(ref.get("uses_fallback_media") is True for ref in refs),
            "blocking_reasons": stable_list(blockers),
            "warnings": stable_list(warnings),
            "required_next_actions": stable_list(actions),
        })
    return rollup


def build_report(review_pack_path: Path, created_at: str) -> dict[str, Any]:
    review_pack = load_json(review_pack_path)
    registry = load_json(EFFECT_REGISTRY)
    canonical_npcs, candidate_npcs, canonical_materials, candidate_materials = canonical_sets(review_pack)

    stage_reports: list[dict[str, Any]] = []
    for stage in as_list(review_pack.get("stages")):
        if not isinstance(stage, dict):
            continue
        assets = [
            evaluate_asset_ref(
                stage,
                asset_ref,
                registry,
                canonical_npcs,
                candidate_npcs,
                canonical_materials,
                candidate_materials,
            )
            for asset_ref in as_list(stage.get("assets"))
            if isinstance(asset_ref, dict)
        ]
        stage_reports.append({
            "stage_order": stage.get("order"),
            "stage_id": stage.get("stage_id"),
            "title": stage.get("title"),
            "bundle_file": stage.get("bundle_file"),
            "assets": assets,
        })

    return {
        "report_version": REPORT_VERSION,
        "report_id": "mvp_story_asset_promotion_report_001",
        "created_at": created_at,
        "input_review_pack": str(review_pack_path.relative_to(ROOT)) if review_pack_path.is_relative_to(ROOT) else str(review_pack_path),
        "worldbook_id": review_pack.get("worldbook_id"),
        "run_id": review_pack.get("run_id"),
        "generation_boundary": {
            "front_end_integration": "not_included",
            "real_service_calls": False,
            "env_file_read": False,
            "provider_calls": False,
            "base_worldbook_mutation": False,
            "runtime_package_build": False,
        },
        "core_artifact_alignment": {
            "alignment_state": "review_only_not_applicable",
            "reason": (
                "StoryAssetPromotionReport 是 review-only 资产晋升决策报告；它记录 fallback_ready、"
                "candidate_only、blocked 等晋升判断，但自身不是 ContextPackage、FactEntry、CGOP 或 "
                "WorldStateDeltaTransaction。"
            ),
            "expected_core_artifacts": [],
            "present_core_artifacts": [],
            "runtime_activation_allowed": False,
            "world_mutation_allowed": False,
            "next_action": (
                "后续核心对象迁移应针对被批准的具体 CGOP、runtime package、media manifest 或 "
                "WorldStateDeltaTransaction，而不是激活整个 promotion report。"
            ),
        },
        "promotion_pipeline": [
            "load_mvp_story_asset_review_pack",
            "for_each_stage_asset",
            "runtime_fixture_probe_or_compiled_asset_load",
            "validate_asset_candidate",
            "simulate_asset_candidate",
            "score_asset_candidate",
            "asset_promotion_policy.evaluate_promotion",
            "stage_governance_gate",
            "emit_review_only_promotion_report",
        ],
        "governance_rules": [
            "runtime package samples are marked usable_runtime_fixture only; they are not fake compiled promotions",
            "candidate_only assets stay candidate-only even if the deterministic policy can make them fallback-playable",
            "high-risk temporary mods stay out of default MVP battles until power-grid and risk context exists",
            "unregistered materials or NPC refs block runtime package promotion",
            "fallback_ready means playable for demo with deterministic media, not final generated-media readiness",
        ],
        "canonical_boundaries_snapshot": {
            "canonical_npcs": sorted(canonical_npcs),
            "candidate_functional_npcs": sorted(candidate_npcs),
            "canonical_materials": sorted(canonical_materials),
            "candidate_only_materials": sorted(candidate_materials),
        },
        "summary": summarize(stage_reports),
        "stages": stage_reports,
        "asset_rollup": rollup_assets(stage_reports),
        "next_review_questions": [
            "是否允许 fallback_ready 资产先进入 MVP 演示包，真实媒体继续后台生成？",
            "是否把 npc_wire_mender_003 或 npc_road_scout 提升为 canonical 功能 NPC？",
            "是否登记 shadow_tide_survey 依赖的材料，还是把它改写为现有 canonical 材料？",
            "overload_chain_mod 是否推迟到高风险研发机制完成后再开放？",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("review_pack", nargs="?", default=str(DEFAULT_REVIEW_PACK))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--created-at", default="2026-07-01T00:00:00+08:00")
    args = parser.parse_args()

    review_pack_path = resolve_repo_path(args.review_pack)
    output_path = resolve_repo_path(args.output)
    report = build_report(review_pack_path, args.created_at)
    write_json(output_path, report)

    summary = report["summary"]
    print(f"Wrote {output_path}")
    print(f"- stages: {summary['stage_count']}")
    print(f"- asset refs: {summary['asset_reference_count']}")
    print(f"- playable refs: {summary['playable_reference_count']}")
    print(f"- promotion states: {summary['promotion_states']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
