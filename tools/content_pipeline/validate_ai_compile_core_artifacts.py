#!/usr/bin/env python3
"""Validate AI compilation core artifacts: ContextPackage, FactEntry, and CGOP."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ASSET_GRAPH_DIR = ROOT / "tools" / "asset_graph"
if str(ASSET_GRAPH_DIR) not in sys.path:
    sys.path.insert(0, str(ASSET_GRAPH_DIR))

from validation_common import load_json, scan_forbidden_terms, validate_json_schema  # noqa: E402


SCHEMA_BY_VERSION = {
    "context_package.v0.1": ROOT / "shared/schemas/context_package.v0.1.schema.json",
    "fact_entry.v0.1": ROOT / "shared/schemas/fact_entry.v0.1.schema.json",
    "compiled_game_object_package.v0.1": ROOT
    / "shared/schemas/compiled_game_object_package.v0.1.schema.json",
}

FORBIDDEN_BOUNDARY_KEYS = frozenset(
    {
        "full_worldbook",
        "worldbook_snapshot",
        "long_term_memory",
        "memory_dump",
        "runtime_instances",
        "mutable_instance_state",
        "save_state",
        "transaction_log",
        "arbitrary_effects",
        "effects",
        "raw_patch",
        "json_patch",
    }
)

RUNTIME_LIFECYCLE_STATES = frozenset({"locked", "published", "active"})


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _repo_path(ref: str) -> Path:
    path = Path(ref)
    return path if path.is_absolute() else ROOT / ref


def _dedupe(errors: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for error in errors:
        if error not in seen:
            seen.add(error)
            out.append(error)
    return out


def _scan_forbidden_boundary_keys(value: Any, errors: list[str], path: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key in FORBIDDEN_BOUNDARY_KEYS:
                errors.append(f"forbidden boundary field in AI compile core artifact: {child_path}")
            _scan_forbidden_boundary_keys(child, errors, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan_forbidden_boundary_keys(child, errors, f"{path}[{index}]")


def _check_artifact_refs(refs: list[Any], errors: list[str], path: str) -> None:
    for index, ref in enumerate(refs):
        if not isinstance(ref, dict):
            continue
        ref_path = ref.get("path")
        if not isinstance(ref_path, str) or not ref_path:
            continue
        if not _repo_path(ref_path).exists():
            errors.append(f"{path}[{index}].path references missing file: {ref_path}")


def _validate_context_package(data: dict[str, Any], errors: list[str]) -> None:
    authority = as_obj(data.get("authority"))
    if authority.get("advisory_only") is not True:
        errors.append("ContextPackage authority.advisory_only must be true")
    if authority.get("can_mutate_world") is not False:
        errors.append("ContextPackage must not mutate world state")
    if authority.get("can_publish_runtime") is not False:
        errors.append("ContextPackage must not publish runtime content")

    blocks = [block for block in as_list(data.get("blocks")) if isinstance(block, dict)]
    block_ids: set[str] = set()
    duplicate_ids: set[str] = set()
    for block in blocks:
        block_id = block.get("block_id")
        if isinstance(block_id, str):
            if block_id in block_ids:
                duplicate_ids.add(block_id)
            block_ids.add(block_id)
    for block_id in sorted(duplicate_ids):
        errors.append(f"duplicate context block_id: {block_id}")

    for plan_index, insertion in enumerate(as_list(data.get("insertion_plan"))):
        if not isinstance(insertion, dict):
            continue
        for block_id in as_list(insertion.get("block_ids")):
            if block_id not in block_ids:
                errors.append(
                    f"insertion_plan[{plan_index}] references missing context block_id: {block_id}"
                )

    _check_artifact_refs(as_list(data.get("source_refs")), errors, "source_refs")
    _check_artifact_refs(as_list(data.get("policy_refs")), errors, "policy_refs")


def _validate_fact_entry(data: dict[str, Any], errors: list[str]) -> None:
    policy = as_obj(data.get("submission_policy"))
    if policy.get("can_mutate_run_world_state") is not False:
        errors.append("FactEntry must not directly mutate RunWorldState")
    if policy.get("commit_requires_world_state_delta") is not True:
        errors.append("FactEntry commit must require WorldStateDelta")

    commit_state = data.get("commit_state")
    source_tx_id = data.get("source_tx_id")
    allowed_context_use = policy.get("allowed_context_use")
    if commit_state == "candidate" and allowed_context_use != "context_only_until_committed":
        errors.append("candidate FactEntry must remain context_only_until_committed")
    if commit_state == "committed":
        if not isinstance(source_tx_id, str) or not source_tx_id:
            errors.append("committed FactEntry must declare source_tx_id")
        if data.get("source") != "world_state_delta":
            errors.append("committed FactEntry source must be world_state_delta")
        if allowed_context_use != "committed_world_fact":
            errors.append("committed FactEntry must use committed_world_fact policy")

    if data.get("source") == "player_claim" and data.get("confidence") not in {
        "player_claim",
        "rumor",
    }:
        errors.append("player_claim FactEntry must use player_claim or rumor confidence")


def _validate_cgop(data: dict[str, Any], errors: list[str]) -> None:
    authority = as_obj(data.get("authority"))
    if authority.get("direct_world_mutation_allowed") is not False:
        errors.append("CGOP must not directly mutate world state")

    runtime_contract = as_obj(data.get("runtime_contract"))
    validation_report = as_obj(data.get("validation_report"))
    runtime_loadable = runtime_contract.get("runtime_loadable")
    report_loadable = validation_report.get("runtime_loadable")
    lifecycle_state = data.get("lifecycle_state")
    gate_status = validation_report.get("gate_status")

    if runtime_loadable != report_loadable:
        errors.append("CGOP runtime_contract.runtime_loadable must match validation_report.runtime_loadable")
    if runtime_loadable is True:
        if lifecycle_state not in RUNTIME_LIFECYCLE_STATES:
            errors.append("runtime-loadable CGOP must be locked, published, or active")
        if gate_status != "passed":
            errors.append("runtime-loadable CGOP must have passed validation_report.gate_status")
    if lifecycle_state in {"draft", "compiled", "validated", "reviewed"} and runtime_loadable is True:
        errors.append(f"{lifecycle_state} CGOP must not be runtime_loadable")

    _check_artifact_refs(as_list(data.get("source_refs")), errors, "source_refs")
    _check_artifact_refs(as_list(data.get("policy_refs")), errors, "policy_refs")
    _check_artifact_refs(as_list(runtime_contract.get("manifest_refs")), errors, "runtime_contract.manifest_refs")
    _check_artifact_refs(as_list(runtime_contract.get("world_delta_refs")), errors, "runtime_contract.world_delta_refs")

    world_context = as_obj(data.get("world_context"))
    forbidden_mutations = as_list(world_context.get("forbidden_world_mutations"))
    if not forbidden_mutations:
        errors.append("CGOP world_context.forbidden_world_mutations must document blocked mutation classes")


def validate_ai_compile_core_artifact(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["artifact root must be an object"]
    schema_version = data.get("schema_version")
    schema_path = SCHEMA_BY_VERSION.get(str(schema_version))
    if schema_path is None:
        return [f"unsupported schema_version: {schema_version!r}"]

    errors.extend(validate_json_schema(data, schema_path))
    scan_forbidden_terms(data, "", errors, context=str(schema_version))
    _scan_forbidden_boundary_keys(data, errors)

    if schema_version == "context_package.v0.1":
        _validate_context_package(data, errors)
    elif schema_version == "fact_entry.v0.1":
        _validate_fact_entry(data, errors)
    elif schema_version == "compiled_game_object_package.v0.1":
        _validate_cgop(data, errors)

    return _dedupe(errors)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate ContextPackage, FactEntry, and CompiledGameObjectPackage v0.1 artifacts."
    )
    parser.add_argument("artifacts", nargs="+", help="Artifact JSON path(s).")
    args = parser.parse_args()

    failed = False
    for artifact_path in args.artifacts:
        try:
            data = load_json(Path(artifact_path))
        except FileNotFoundError:
            print(f"INVALID {artifact_path}")
            print(f"- file not found: {artifact_path}")
            failed = True
            continue
        except json.JSONDecodeError as exc:
            print(f"INVALID {artifact_path}")
            print(f"- not valid JSON: {exc}")
            failed = True
            continue

        errors = validate_ai_compile_core_artifact(data)
        if errors:
            print(f"INVALID {artifact_path}")
            for error in errors:
                print(f"- {error}")
            failed = True
            continue

        print(f"OK {artifact_path}")
        print(f"- schema_version: {data.get('schema_version')}")
        print(f"- id: {data.get('package_id') or data.get('context_package_id') or data.get('fact_id')}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
