#!/usr/bin/env python3
"""Validate a MultistageContentPack v0.1 JSON file.

The pack is review-only. This validator checks the schema, source file refs,
summary counters, stage uniqueness, validation result status, and the linked
StageCandidatePack handoff file.
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
WORLD_STATE_DIR = ROOT / "tools" / "world_state"
for path in (ASSET_GRAPH_DIR, WORLD_STATE_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from apply_world_delta import apply_delta  # noqa: E402
from validation_common import load_json, scan_forbidden_terms, validate_json_schema  # noqa: E402


SCHEMA_PATH = ROOT / "shared/schemas/multistage_content_pack.v0.1.schema.json"


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def repo_path(ref: str) -> Path:
    path = Path(ref)
    return path if path.is_absolute() else ROOT / ref


def dedupe(errors: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for error in errors:
        if error not in seen:
            seen.add(error)
            out.append(error)
    return out


def check_file(ref: Any, path: str, errors: list[str]) -> None:
    if not isinstance(ref, str) or not ref:
        errors.append(f"{path} must be a non-empty string")
        return
    if not repo_path(ref).is_file():
        errors.append(f"{path} references missing file: {ref}")


def check_stage_files(pack: dict[str, Any], errors: list[str]) -> None:
    for index, stage in enumerate(as_list(pack.get("stage_summaries"))):
        if not isinstance(stage, dict):
            continue
        base = f"stage_summaries[{index}]"
        for key in (
            "bundle_file",
            "world_delta_file",
            "next_state_file",
            "proposal_file",
            "compiled_asset_file",
        ):
            check_file(stage.get(key), f"{base}.{key}", errors)
    summary = as_obj(pack.get("summary"))
    check_file(summary.get("initial_state_file"), "summary.initial_state_file", errors)
    check_file(summary.get("final_state_file"), "summary.final_state_file", errors)
    check_file(summary.get("stage_candidate_pack_file"), "summary.stage_candidate_pack_file", errors)


def check_stage_uniqueness(pack: dict[str, Any], errors: list[str]) -> None:
    labels: set[str] = set()
    stage_ids: set[str] = set()
    for index, stage in enumerate(as_list(pack.get("stage_summaries"))):
        if not isinstance(stage, dict):
            continue
        label = stage.get("stage_label")
        stage_id = stage.get("stage_id")
        if isinstance(label, str):
            if label in labels:
                errors.append(f"duplicate stage_label: {label!r}")
            labels.add(label)
        if isinstance(stage_id, str):
            if stage_id in stage_ids:
                errors.append(f"duplicate stage_id: {stage_id!r}")
            stage_ids.add(stage_id)
        lane_counts = as_obj(stage.get("lane_counts"))
        for lane in ("world_line", "player_line", "shared"):
            if int(lane_counts.get(lane, 0)) <= 0:
                errors.append(f"stage_summaries[{index}].lane_counts missing lane {lane!r}")


def check_summary(pack: dict[str, Any], errors: list[str]) -> None:
    stages = [stage for stage in as_list(pack.get("stage_summaries")) if isinstance(stage, dict)]
    summary = as_obj(pack.get("summary"))
    if summary.get("stage_count") != len(stages):
        errors.append(
            "summary.stage_count mismatch: "
            f"expected {len(stages)}, got {summary.get('stage_count')}"
        )

    asset_types = Counter(str(stage.get("asset_type")) for stage in stages)
    if as_obj(summary.get("asset_type_counts")) != dict(sorted(asset_types.items())):
        errors.append("summary.asset_type_counts does not match stage_summaries")

    effect_counts = Counter(
        str(effect)
        for stage in stages
        for effect in as_list(stage.get("effect_blocks"))
    )
    if as_obj(summary.get("effect_block_counts")) != dict(sorted(effect_counts.items())):
        errors.append("summary.effect_block_counts does not match stage_summaries")

    if stages and summary.get("final_state_file") != stages[-1].get("next_state_file"):
        errors.append("summary.final_state_file must equal the final stage next_state_file")


def check_delta_replay(pack: dict[str, Any], errors: list[str]) -> None:
    summary = as_obj(pack.get("summary"))
    initial_ref = summary.get("initial_state_file")
    if not isinstance(initial_ref, str) or not repo_path(initial_ref).is_file():
        return
    try:
        current_state = load_json(repo_path(initial_ref))
    except json.JSONDecodeError as exc:
        errors.append(f"summary.initial_state_file is not valid JSON: {exc}")
        return

    for index, stage in enumerate(as_list(pack.get("stage_summaries"))):
        if not isinstance(stage, dict):
            continue
        delta_ref = stage.get("world_delta_file")
        next_state_ref = stage.get("next_state_file")
        if not isinstance(delta_ref, str) or not repo_path(delta_ref).is_file():
            continue
        if not isinstance(next_state_ref, str) or not repo_path(next_state_ref).is_file():
            continue
        try:
            delta = load_json(repo_path(delta_ref))
            expected_next_state = load_json(repo_path(next_state_ref))
        except json.JSONDecodeError as exc:
            errors.append(f"stage_summaries[{index}] replay input is not valid JSON: {exc}")
            return
        applied_state, apply_errors = apply_delta(current_state, delta)
        if apply_errors:
            errors.append(
                f"stage_summaries[{index}] replay failed: " + "; ".join(apply_errors)
            )
            return
        if applied_state != expected_next_state:
            errors.append(f"stage_summaries[{index}] replay output does not match next_state_file")
            return
        current_state = applied_state

    final_ref = summary.get("final_state_file")
    if isinstance(final_ref, str) and repo_path(final_ref).is_file():
        try:
            final_state = load_json(repo_path(final_ref))
        except json.JSONDecodeError as exc:
            errors.append(f"summary.final_state_file is not valid JSON: {exc}")
            return
        if current_state != final_state:
            errors.append("full multistage replay output does not match summary.final_state_file")


def check_asset_policy_evidence(pack: dict[str, Any], errors: list[str]) -> None:
    allowed_schema_statuses = {"passed", "passed_legacy_jsonschema"}
    for index, stage in enumerate(as_list(pack.get("stage_summaries"))):
        if not isinstance(stage, dict):
            continue
        evidence = as_obj(stage.get("asset_policy_evidence"))
        base = f"stage_summaries[{index}].asset_policy_evidence"
        if not evidence:
            errors.append(f"{base} is required")
            continue
        if evidence.get("candidate_id") != stage.get("asset_candidate_id"):
            errors.append(f"{base}.candidate_id must match stage asset_candidate_id")
        if evidence.get("asset_type") != stage.get("asset_type"):
            errors.append(f"{base}.asset_type must match stage asset_type")

        validation = as_obj(evidence.get("validation"))
        if validation.get("status") != "passed":
            errors.append(f"{base}.validation.status must be passed")
        if validation.get("error_count") != len(as_list(validation.get("errors"))):
            errors.append(f"{base}.validation.error_count must match errors length")

        simulation = as_obj(evidence.get("simulation"))
        if simulation.get("status") != "passed":
            errors.append(f"{base}.simulation.status must be passed")

        score = as_obj(evidence.get("score"))
        if score.get("status") != "passed":
            errors.append(f"{base}.score.status must be passed")
        if not as_obj(score.get("dimension_scores")):
            errors.append(f"{base}.score.dimension_scores must be non-empty")

        promotion = as_obj(evidence.get("promotion"))
        schema_status = promotion.get("schema_check_status")
        if schema_status not in allowed_schema_statuses:
            errors.append(f"{base}.promotion.schema_check_status must be passed")
        promotion_state = promotion.get("promotion_state")
        if promotion_state == "failed":
            errors.append(f"{base}.promotion.promotion_state must not be failed")
        if promotion_state == "runtime_ready" and promotion.get("uses_fallback_media"):
            errors.append(f"{base}.promotion runtime_ready cannot use fallback media")
        if not as_list(promotion.get("required_next_actions")):
            errors.append(f"{base}.promotion.required_next_actions must be non-empty")


def check_validation_results(pack: dict[str, Any], errors: list[str]) -> None:
    results = as_obj(pack.get("validation_results"))
    failed = {key: value for key, value in results.items() if value != "passed"}
    if failed:
        for key, value in sorted(failed.items()):
            errors.append(f"validation_results.{key} is not passed: {value}")

    labels = [
        stage.get("stage_label")
        for stage in as_list(pack.get("stage_summaries"))
        if isinstance(stage, dict) and isinstance(stage.get("stage_label"), str)
    ]
    required_suffixes = (
        "narrative_bundle",
        "world_delta",
        "next_run_state",
        "proposal",
        "asset_candidate",
        "asset_policy_evidence",
        "world_delta_semantics",
        "world_delta_apply",
    )
    for label in labels:
        for suffix in required_suffixes:
            key = f"{label}.{suffix}"
            if results.get(key) != "passed":
                errors.append(f"validation_results missing passed check: {key}")


def check_stage_candidate_pack(pack: dict[str, Any], errors: list[str]) -> None:
    summary = as_obj(pack.get("summary"))
    ref = summary.get("stage_candidate_pack_file")
    if not isinstance(ref, str) or not ref:
        return
    path = repo_path(ref)
    if not path.is_file():
        return
    try:
        stage_pack = load_json(path)
    except json.JSONDecodeError as exc:
        errors.append(f"summary.stage_candidate_pack_file is not valid JSON: {exc}")
        return
    if stage_pack.get("schema_version") != "stage_candidate_pack.v0.1":
        errors.append("linked stage_candidate_pack_file must be stage_candidate_pack.v0.1")
    if as_obj(stage_pack.get("readiness_summary")).get("stage_count") != as_obj(pack.get("summary")).get("stage_count"):
        errors.append("linked StageCandidatePack stage_count must match multistage pack")


def validate_multistage_content_pack(pack: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(pack, dict):
        return ["multistage content pack root must be an object"]
    errors.extend(validate_json_schema(pack, SCHEMA_PATH))
    scan_forbidden_terms(pack, "", errors, context="MultistageContentPack")
    check_stage_files(pack, errors)
    check_stage_uniqueness(pack, errors)
    check_summary(pack, errors)
    check_asset_policy_evidence(pack, errors)
    check_delta_replay(pack, errors)
    check_validation_results(pack, errors)
    check_stage_candidate_pack(pack, errors)
    return dedupe(errors)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a MultistageContentPack v0.1 JSON file.")
    parser.add_argument("pack", help="Path to multistage content pack JSON.")
    args = parser.parse_args()

    try:
        pack = load_json(Path(args.pack))
    except FileNotFoundError:
        print("INVALID MultistageContentPack")
        print(f"- pack file not found: {args.pack}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID MultistageContentPack")
        print(f"- pack is not valid JSON: {exc}")
        return 1

    errors = validate_multistage_content_pack(pack)
    if errors:
        print("INVALID MultistageContentPack")
        for error in errors:
            print(f"- {error}")
        return 1

    print("OK MultistageContentPack")
    print(f"- pack_id: {pack.get('pack_id')}")
    print(f"- stages: {as_obj(pack.get('summary')).get('stage_count')}")
    print(f"- final_state_file: {as_obj(pack.get('summary')).get('final_state_file')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
