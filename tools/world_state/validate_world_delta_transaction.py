#!/usr/bin/env python3
"""Validate a WorldStateDeltaTransaction v0.1 JSON file.

The transaction is a wrapper around an existing WorldStateDelta v0.1. It must
not replace the delta schema or introduce a generic effects[] mechanism. This
validator checks:

- transaction schema and forbidden internal fields;
- referenced WorldStateDelta path, sha256, delta_id, run/worldbook/source/turn;
- operation_effects_mapping covers every delta operation by index and op;
- optional semantic gate and runtime apply checks when source refs are present.

The validator never reads .env and never prints API keys or secrets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _common import get_jsonschema_validator, load_json, scan_forbidden_fields  # noqa: E402
from apply_world_delta import apply_delta  # noqa: E402
from validate_world_delta import (  # noqa: E402
    validate_with_jsonschema as validate_delta_with_jsonschema,
    validate_world_delta,
)
from validate_world_delta_semantics import (  # noqa: E402
    DEFAULT_REVIEW_PACK,
    build_reference_registry,
    validate_world_delta_semantics,
)


SCHEMA_PATH = ROOT / "shared/schemas/world_state_delta_transaction.v0.1.schema.json"
FORBIDDEN_TRANSACTION_KEYS: frozenset[str] = frozenset(
    {
        "effects",
        "raw_patch",
        "json_patch",
        "arbitrary_patch",
        "mutate_base_worldbook",
        "set_worldbook",
        "replace_worldbook",
        "eval",
        "script",
        "provider_call",
    }
)


def repo_path(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else ROOT / path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dedupe(errors: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for error in errors:
        if error not in seen:
            seen.add(error)
            result.append(error)
    return result


def scan_forbidden_transaction_keys(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key in FORBIDDEN_TRANSACTION_KEYS:
                errors.append(
                    f"forbidden transaction field '{child_path}' is not allowed; "
                    "use WorldStateDelta.operations[] and operation_effects_mapping instead"
                )
            scan_forbidden_transaction_keys(child, child_path, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_forbidden_transaction_keys(child, f"{path}[{index}]", errors)


def validate_with_jsonschema(transaction: dict[str, Any]) -> list[str]:
    try:
        schema = load_json(SCHEMA_PATH)
    except FileNotFoundError:
        return [f"transaction schema file not found: {SCHEMA_PATH}"]
    validator = get_jsonschema_validator(schema)
    if validator is None:
        return []
    return [
        f"schema: {'.'.join(str(p) for p in err.absolute_path) or '<root>'}: {err.message}"
        for err in validator.iter_errors(transaction)
    ]


def load_referenced_delta(transaction: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    ref = transaction.get("world_state_delta_ref")
    if not isinstance(ref, dict):
        errors.append("world_state_delta_ref must be an object")
        return {}
    raw_path = ref.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        errors.append("world_state_delta_ref.path must be a non-empty string")
        return {}
    delta_path = repo_path(raw_path)
    try:
        actual_sha = sha256_file(delta_path)
    except FileNotFoundError:
        errors.append(f"referenced WorldStateDelta file not found: {raw_path}")
        return {}
    expected_sha = ref.get("sha256")
    if isinstance(expected_sha, str) and expected_sha and expected_sha != actual_sha:
        errors.append(
            "world_state_delta_ref.sha256 does not match referenced file "
            f"(expected={expected_sha}, actual={actual_sha})"
        )
    try:
        delta = load_json(delta_path)
    except json.JSONDecodeError as exc:
        errors.append(f"referenced WorldStateDelta is not valid JSON: {exc}")
        return {}
    if not isinstance(delta, dict):
        errors.append("referenced WorldStateDelta root must be an object")
        return {}
    return delta


def validate_delta_ref(transaction: dict[str, Any], delta: dict[str, Any], errors: list[str]) -> None:
    ref = transaction.get("world_state_delta_ref")
    if not isinstance(ref, dict) or not delta:
        return
    expected_pairs = [
        ("schema_version", "schema_version", "world_state_delta_ref.schema_version"),
        ("delta_id", "delta_id", "world_state_delta_ref.delta_id"),
    ]
    for delta_key, ref_key, label in expected_pairs:
        if ref.get(ref_key) != delta.get(delta_key):
            errors.append(f"{label} must match delta.{delta_key}")
    for key in ("run_id", "worldbook_id", "source", "created_turn"):
        if transaction.get(key) != delta.get(key):
            errors.append(f"{key} must match referenced WorldStateDelta.{key}")


def validate_operation_mapping(transaction: dict[str, Any], delta: dict[str, Any], errors: list[str]) -> None:
    raw_mapping = transaction.get("operation_effects_mapping")
    operations = delta.get("operations", []) if isinstance(delta, dict) else []
    if not isinstance(raw_mapping, list):
        errors.append("operation_effects_mapping must be an array")
        return
    if not isinstance(operations, list):
        errors.append("referenced WorldStateDelta.operations must be an array")
        return
    by_index: dict[int, dict[str, Any]] = {}
    for item in raw_mapping:
        if not isinstance(item, dict):
            continue
        index = item.get("operation_index")
        if isinstance(index, int) and not isinstance(index, bool):
            if index in by_index:
                errors.append(f"operation_effects_mapping has duplicate operation_index={index}")
            by_index[index] = item

    expected_indices = set(range(len(operations)))
    actual_indices = set(by_index)
    missing = sorted(expected_indices - actual_indices)
    extra = sorted(actual_indices - expected_indices)
    if missing:
        errors.append(f"operation_effects_mapping missing operation indices: {missing}")
    if extra:
        errors.append(f"operation_effects_mapping has indices outside delta.operations: {extra}")

    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            continue
        mapping = by_index.get(index)
        if not mapping:
            continue
        if mapping.get("op") != operation.get("op"):
            errors.append(
                f"operation_effects_mapping[{index}].op={mapping.get('op')!r} "
                f"must match delta.operations[{index}].op={operation.get('op')!r}"
            )


def validate_source_paths(transaction: dict[str, Any], errors: list[str]) -> dict[str, Path]:
    refs = transaction.get("source_refs")
    result: dict[str, Path] = {}
    if not isinstance(refs, dict):
        errors.append("source_refs must be an object")
        return result
    for key, raw in refs.items():
        if not isinstance(raw, str) or not raw:
            continue
        path = repo_path(raw)
        result[key] = path
        if not path.exists():
            errors.append(f"source_refs.{key} file not found: {raw}")
    return result


def validate_report_claims(
    transaction: dict[str, Any],
    *,
    structure_errors: list[str],
    semantic_errors: list[str],
    apply_errors: list[str],
    mapping_errors: list[str],
    errors: list[str],
) -> None:
    report = transaction.get("validation_report")
    if not isinstance(report, dict):
        return
    if report.get("world_delta_structure") == "passed" and structure_errors:
        errors.append("validation_report.world_delta_structure claims passed but delta structure validation failed")
    if report.get("world_delta_semantics") == "passed" and semantic_errors:
        errors.append("validation_report.world_delta_semantics claims passed but semantic validation failed")
    if report.get("operation_mapping") == "passed" and mapping_errors:
        errors.append("validation_report.operation_mapping claims passed but operation mapping failed")
    if report.get("runtime_apply_checked") is True and apply_errors:
        errors.append("validation_report.runtime_apply_checked claims true but apply check failed")
    if report.get("gate_status") == "passed" and (
        structure_errors or semantic_errors or apply_errors or mapping_errors
    ):
        errors.append("validation_report.gate_status claims passed but one or more gates failed")


def validate_transaction(transaction: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(transaction, dict):
        return ["transaction root must be an object"]

    errors.extend(validate_with_jsonschema(transaction))
    scan_forbidden_fields(transaction, "", errors)
    scan_forbidden_transaction_keys(transaction, "", errors)

    source_paths = validate_source_paths(transaction, errors)
    delta = load_referenced_delta(transaction, errors)
    validate_delta_ref(transaction, delta, errors)

    structure_errors: list[str] = []
    semantic_errors: list[str] = []
    apply_errors: list[str] = []
    mapping_errors: list[str] = []

    if delta:
        structure_errors.extend(validate_delta_with_jsonschema(delta))
        structure_errors.extend(validate_world_delta(delta))
        mapping_errors_before = len(errors)
        validate_operation_mapping(transaction, delta, errors)
        mapping_errors = errors[mapping_errors_before:]

    run_state_path = source_paths.get("run_state_before_path")
    if delta and run_state_path and run_state_path.exists():
        try:
            run_state = load_json(run_state_path)
        except json.JSONDecodeError as exc:
            semantic_errors.append(f"run_state_before_path is not valid JSON: {exc}")
            run_state = None
        if isinstance(run_state, dict):
            registry = build_reference_registry(run_state, DEFAULT_REVIEW_PACK)
            semantic_errors.extend(validate_world_delta_semantics(delta, run_state, registry))
            if transaction.get("validation_report", {}).get("runtime_apply_checked") is True:
                _, apply_errors = apply_delta(run_state, delta)
        else:
            semantic_errors.append("run_state_before_path root must be an object")

    for error in structure_errors:
        errors.append(f"referenced WorldStateDelta invalid: {error}")
    for error in semantic_errors:
        errors.append(f"referenced WorldStateDelta semantic gate failed: {error}")
    for error in apply_errors:
        errors.append(f"referenced WorldStateDelta apply check failed: {error}")

    validate_report_claims(
        transaction,
        structure_errors=structure_errors,
        semantic_errors=semantic_errors,
        apply_errors=apply_errors,
        mapping_errors=mapping_errors,
        errors=errors,
    )
    return dedupe(errors)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a WorldStateDeltaTransaction v0.1 JSON file."
    )
    parser.add_argument("transaction", help="Path to a transaction JSON file.")
    args = parser.parse_args()

    transaction_path = Path(args.transaction)
    try:
        transaction = load_json(transaction_path)
    except FileNotFoundError:
        print("INVALID WorldStateDeltaTransaction")
        print(f"- transaction file not found: {transaction_path}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID WorldStateDeltaTransaction")
        print(f"- transaction is not valid JSON: {exc}")
        return 1

    if not isinstance(transaction, dict):
        print("INVALID WorldStateDeltaTransaction")
        print("- transaction root must be an object")
        return 1

    errors = validate_transaction(transaction)
    if errors:
        print("INVALID WorldStateDeltaTransaction")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"OK: {transaction_path}")
    print(f"- schema_version: {transaction.get('schema_version')}")
    print(f"- transaction_id: {transaction.get('transaction_id')}")
    print(f"- status: {transaction.get('status')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
