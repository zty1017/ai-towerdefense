#!/usr/bin/env python3
"""Validate a StageCandidatePack v0.1 JSON file.

The pack is a review-only handoff artifact. It groups staged narrative,
WorldStateDelta, gameplay objects, assets, runtime package references, gates,
and next actions. It is not a frontend runtime package and must not carry raw
provider payloads.
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


SCHEMA_PATH = ROOT / "shared/schemas/stage_candidate_pack.v0.1.schema.json"
FORBIDDEN_KEY_TERMS = frozenset(
    {
        "provider",
        "model",
        "raw_prompt",
        "full_trace",
        "raw_json",
        "api_key",
        "secret",
        "unreviewed_content",
    }
)
FORBIDDEN_STRING_TERMS = FORBIDDEN_KEY_TERMS
KEY_SCAN_ALLOWLIST = frozenset({"pack_builder_calls_provider"})


def _dedupe(errors: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for error in errors:
        if error not in seen:
            seen.add(error)
            out.append(error)
    return out


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _repo_path(ref: str) -> Path:
    path = Path(ref)
    return path if path.is_absolute() else ROOT / ref


def _scan_forbidden_terms(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            lowered_key = str(key).lower()
            if str(key) not in KEY_SCAN_ALLOWLIST:
                for term in FORBIDDEN_KEY_TERMS:
                    if term in lowered_key:
                        errors.append(f"forbidden technical field '{child_path}' contains {term!r}")
                        break
            _scan_forbidden_terms(child, child_path, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan_forbidden_terms(child, f"{path}[{index}]", errors)
    elif isinstance(value, str):
        lowered = value.lower()
        for term in FORBIDDEN_STRING_TERMS:
            if term in lowered:
                errors.append(f"forbidden technical term {term!r} found in string at '{path}'")


def _check_file(ref: Any, path: str, errors: list[str]) -> None:
    if not isinstance(ref, str) or not ref:
        errors.append(f"{path} must be a non-empty string")
        return
    if not _repo_path(ref).is_file():
        errors.append(f"{path} references missing file: {ref}")


def _check_source_refs(pack: dict[str, Any], errors: list[str]) -> None:
    refs = pack.get("source_refs")
    if isinstance(refs, dict):
        for key in ("review_pack", "promotion_report", "final_run_state"):
            _check_file(refs.get(key), f"source_refs.{key}", errors)
        runtime_packages = refs.get("runtime_packages", [])
        if isinstance(runtime_packages, list):
            for index, ref in enumerate(runtime_packages):
                _check_file(ref, f"source_refs.runtime_packages[{index}]", errors)

    for stage_index, stage in enumerate(pack.get("stage_candidates", []) or []):
        if not isinstance(stage, dict):
            continue
        source_files = stage.get("source_files")
        if isinstance(source_files, dict):
            _check_file(
                source_files.get("narrative_bundle"),
                f"stage_candidates[{stage_index}].source_files.narrative_bundle",
                errors,
            )
            _check_file(
                source_files.get("world_delta"),
                f"stage_candidates[{stage_index}].source_files.world_delta",
                errors,
            )
            if source_files.get("battle_config"):
                _check_file(
                    source_files.get("battle_config"),
                    f"stage_candidates[{stage_index}].source_files.battle_config",
                    errors,
                )
        for asset_index, asset in enumerate(stage.get("asset_outputs", []) or []):
            if isinstance(asset, dict):
                _check_file(
                    asset.get("source_file"),
                    f"stage_candidates[{stage_index}].asset_outputs[{asset_index}].source_file",
                    errors,
                )
        for package_index, package in enumerate(stage.get("runtime_package_refs", []) or []):
            if isinstance(package, dict):
                _check_file(
                    package.get("package_file"),
                    f"stage_candidates[{stage_index}].runtime_package_refs[{package_index}].package_file",
                    errors,
                )


def _validate_stage_order(pack: dict[str, Any], errors: list[str]) -> None:
    stages = pack.get("stage_candidates")
    if not isinstance(stages, list) or not stages:
        errors.append("stage_candidates must be a non-empty array")
        return
    orders = [
        stage.get("stage_order")
        for stage in stages
        if isinstance(stage, dict) and isinstance(stage.get("stage_order"), int)
    ]
    expected = list(range(1, len(stages) + 1))
    if sorted(orders) != expected:
        errors.append(f"stage_order values must be continuous {expected}, got {sorted(orders)}")


def _validate_gate_readiness(pack: dict[str, Any], errors: list[str]) -> None:
    blocked_count = 0
    stage_ids: set[str] = set()
    stages = [stage for stage in as_list(pack.get("stage_candidates")) if isinstance(stage, dict)]
    readiness = pack.get("readiness_summary") if isinstance(pack.get("readiness_summary"), dict) else {}
    status_counts: Counter[str] = Counter()
    gate_counts: Counter[str] = Counter()
    playable_asset_count = 0
    runtime_package_count = 0
    for stage_index, stage in enumerate(pack.get("stage_candidates", []) or []):
        if not isinstance(stage, dict):
            continue
        status_counts[str(stage.get("status"))] += 1
        playable_asset_count += sum(
            1
            for asset in as_list(stage.get("asset_outputs"))
            if isinstance(asset, dict) and asset.get("playable") is True
        )
        runtime_package_count += sum(
            1
            for package in as_list(stage.get("runtime_package_refs"))
            if isinstance(package, dict)
        )
        stage_id = stage.get("stage_id")
        if isinstance(stage_id, str):
            if stage_id in stage_ids:
                errors.append(f"duplicate stage_id {stage_id!r}")
            stage_ids.add(stage_id)
        gates = stage.get("validation_gates")
        if not isinstance(gates, list) or not gates:
            errors.append(f"stage_candidates[{stage_index}].validation_gates must be non-empty")
            continue
        gate_names = {
            str(gate.get("gate"))
            for gate in gates
            if isinstance(gate, dict) and gate.get("gate")
        }
        required = {"narrative_bundle", "world_delta_structure", "narrative_gameplay_contract"}
        missing = sorted(required - gate_names)
        if missing:
            errors.append(
                f"stage_candidates[{stage_index}].validation_gates missing required gates: {missing}"
            )
        for gate in gates:
            if not isinstance(gate, dict):
                continue
            gate_status = str(gate.get("status"))
            gate_counts[gate_status] += 1
            if gate_status == "blocked":
                blocked_count += 1
        if stage.get("status") == "reviewed_fixture" and any(
            isinstance(gate, dict) and gate.get("status") == "blocked" for gate in gates
        ):
            errors.append(
                f"stage_candidates[{stage_index}] cannot be reviewed_fixture with blocked gates"
            )
    if isinstance(readiness, dict):
        if readiness.get("stage_count") != len(stages):
            errors.append(
                "readiness_summary.stage_count mismatch: "
                f"expected {len(stages)}, got {readiness.get('stage_count')}"
            )
        if readiness.get("status_counts") != dict(sorted(status_counts.items())):
            errors.append("readiness_summary.status_counts does not match stage_candidates")
        if readiness.get("validation_gate_counts") != dict(sorted(gate_counts.items())):
            errors.append("readiness_summary.validation_gate_counts does not match validation_gates")
        if readiness.get("playable_asset_reference_count") != playable_asset_count:
            errors.append(
                "readiness_summary.playable_asset_reference_count mismatch: "
                f"expected {playable_asset_count}, got {readiness.get('playable_asset_reference_count')}"
            )
        if readiness.get("runtime_package_reference_count") != runtime_package_count:
            errors.append(
                "readiness_summary.runtime_package_reference_count mismatch: "
                f"expected {runtime_package_count}, got {readiness.get('runtime_package_reference_count')}"
            )
    recommendation = readiness.get("review_recommendation") if isinstance(readiness, dict) else None
    if blocked_count and recommendation == "review_ready":
        errors.append("readiness_summary.review_recommendation cannot be review_ready with blocked gates")


def validate_stage_candidate_pack(pack: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(pack, dict):
        return ["stage candidate pack root must be an object"]
    errors.extend(validate_json_schema(pack, SCHEMA_PATH))
    _scan_forbidden_terms(pack, "", errors)
    _check_source_refs(pack, errors)
    _validate_stage_order(pack, errors)
    _validate_gate_readiness(pack, errors)
    return _dedupe(errors)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a StageCandidatePack v0.1 JSON file.")
    parser.add_argument("pack", help="Path to stage candidate pack JSON.")
    args = parser.parse_args()

    try:
        pack = load_json(Path(args.pack))
    except FileNotFoundError:
        print("INVALID StageCandidatePack")
        print(f"- pack file not found: {args.pack}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID StageCandidatePack")
        print(f"- pack is not valid JSON: {exc}")
        return 1

    errors = validate_stage_candidate_pack(pack)
    if errors:
        print("INVALID StageCandidatePack")
        for error in errors:
            print(f"- {error}")
        return 1

    print("OK StageCandidatePack")
    print(f"- pack_id: {pack.get('pack_id')}")
    print(f"- stages: {len(pack.get('stage_candidates', []))}")
    print(f"- recommendation: {(pack.get('readiness_summary') or {}).get('review_recommendation')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
