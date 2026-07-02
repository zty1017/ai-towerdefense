#!/usr/bin/env python3
"""Validate ProviderExecutionAuthorization v0.1 artifacts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
ASSET_GRAPH_DIR = ROOT / "tools" / "asset_graph"
if str(ASSET_GRAPH_DIR) not in sys.path:
    sys.path.insert(0, str(ASSET_GRAPH_DIR))

from validation_common import load_json, validate_json_schema  # noqa: E402


SCHEMA_PATH = ROOT / "shared/schemas/provider_execution_authorization.v0.1.schema.json"
SCHEMA_VERSION = "provider_execution_authorization.v0.1"
FORBIDDEN_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "secret_key",
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
    "unreviewed_content",
)
FORBIDDEN_STRING_FRAGMENTS = (
    "api_key=",
    "apikey=",
    "bearer ",
    "sk-",
    "raw_prompt",
    "full_prompt",
    "provider_response",
    "raw_response",
    "raw json",
    "full trace",
)


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def scan_forbidden(value: Any, errors: list[str], path: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            lowered = key.lower()
            if any(fragment in lowered for fragment in FORBIDDEN_KEY_FRAGMENTS):
                errors.append(f"forbidden key in ProviderExecutionAuthorization: {child_path}")
            scan_forbidden(child, errors, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_forbidden(child, errors, f"{path}[{index}]")
    elif isinstance(value, str):
        lowered = value.lower()
        for fragment in FORBIDDEN_STRING_FRAGMENTS:
            if fragment in lowered:
                errors.append(f"forbidden string fragment {fragment!r} at {path}")


def check_authority(record: dict[str, Any], errors: list[str]) -> None:
    authority = as_obj(record.get("authority"))
    expected = {
        "review_only": True,
        "provider_execution_authorized": True,
        "runtime_activation_allowed": False,
        "world_mutation_allowed": False,
        "player_visible": False,
    }
    for key, expected_value in expected.items():
        if authority.get(key) is not expected_value:
            errors.append(f"authority.{key} must be {str(expected_value).lower()}")


def check_authorization(record: dict[str, Any], errors: list[str]) -> None:
    authorization = as_obj(record.get("authorization"))
    if authorization.get("granted") is not True:
        errors.append("authorization.granted must be true")
    if authorization.get("requires_provider_output_envelope") is not True:
        errors.append("authorization.requires_provider_output_envelope must be true")
    if authorization.get("scope") != "provider_adapter_execution_only":
        errors.append("authorization.scope must be provider_adapter_execution_only")


def check_budget(record: dict[str, Any], errors: list[str]) -> None:
    constraints = as_obj(record.get("execution_constraints"))
    attempt_count = constraints.get("attempt_count")
    max_attempts = constraints.get("max_attempts")
    remaining = constraints.get("remaining_attempts")
    if all(isinstance(value, int) for value in (attempt_count, max_attempts, remaining)):
        if remaining != max(0, max_attempts - attempt_count):
            errors.append(
                "execution_constraints.remaining_attempts must equal "
                "max(0, max_attempts - attempt_count)"
            )


def check_gates(record: dict[str, Any], errors: list[str]) -> None:
    gates = as_list(as_obj(record.get("execution_constraints")).get("required_next_gates"))
    for gate in (
        "provider_output_envelope",
        "local_artifact_staging_manifest",
        "promotion_report",
    ):
        if gate not in gates:
            errors.append(f"execution_constraints.required_next_gates must include {gate}")


def check_retention_and_safety(record: dict[str, Any], errors: list[str]) -> None:
    retention = as_obj(record.get("retention_policy"))
    for key in ("prompt_body_storage", "provider_body_storage", "secret_storage"):
        if retention.get(key) != "forbidden":
            errors.append(f"retention_policy.{key} must be forbidden")
    if retention.get("executor_result_storage") != "provider_output_envelope_redacted_only":
        errors.append("retention_policy.executor_result_storage must be provider_output_envelope_redacted_only")
    safety = as_obj(record.get("authorization_builder_safety"))
    for key in (
        "reads_env",
        "calls_provider",
        "stores_prompt_body",
        "stores_provider_body",
        "writes_world_state",
        "activates_runtime",
    ):
        if safety.get(key) is not False:
            errors.append(f"authorization_builder_safety.{key} must be false")


def validate_provider_execution_authorization(record: dict[str, Any]) -> list[str]:
    errors = validate_json_schema(record, SCHEMA_PATH)
    if record.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    scan_forbidden(record, errors)
    check_authority(record, errors)
    check_authorization(record, errors)
    check_budget(record, errors)
    check_gates(record, errors)
    check_retention_and_safety(record, errors)
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path)
    args = parser.parse_args()
    record = load_json(args.record)
    if not isinstance(record, dict):
        print("ProviderExecutionAuthorization root must be an object", file=sys.stderr)
        return 1
    errors = validate_provider_execution_authorization(record)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"ProviderExecutionAuthorization validation passed: {args.record}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
