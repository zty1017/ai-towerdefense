#!/usr/bin/env python3
"""Validate GenerationExecutorRunRequest v0.1 artifacts."""

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


SCHEMA_PATH = ROOT / "shared/schemas/generation_executor_run_request.v0.1.schema.json"
SCHEMA_VERSION = "generation_executor_run_request.v0.1"
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


def repo_path(ref: str) -> Path:
    path = Path(ref)
    return path if path.is_absolute() else ROOT / ref


def scan_forbidden(value: Any, errors: list[str], path: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            lowered = key.lower()
            if any(fragment in lowered for fragment in FORBIDDEN_KEY_FRAGMENTS):
                errors.append(f"forbidden key in GenerationExecutorRunRequest: {child_path}")
            scan_forbidden(child, errors, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_forbidden(child, errors, f"{path}[{index}]")
    elif isinstance(value, str):
        lowered = value.lower()
        for fragment in FORBIDDEN_STRING_FRAGMENTS:
            if fragment in lowered:
                errors.append(f"forbidden string fragment {fragment!r} at {path}")


def check_authority(request: dict[str, Any], errors: list[str]) -> None:
    authority = as_obj(request.get("authority"))
    expected = {
        "review_only": True,
        "provider_call_allowed_by_request_builder": False,
        "runtime_activation_allowed": False,
        "world_mutation_allowed": False,
        "player_visible": False,
    }
    for key, expected_value in expected.items():
        if authority.get(key) is not expected_value:
            errors.append(f"authority.{key} must be {str(expected_value).lower()}")


def check_provider_intent(request: dict[str, Any], errors: list[str]) -> None:
    intent = as_obj(request.get("provider_execution_intent"))
    if intent.get("authorization_required") is not True:
        errors.append("provider_execution_intent.authorization_required must be true")
    if intent.get("authorization_granted") is not False:
        errors.append("provider_execution_intent.authorization_granted must be false")
    if intent.get("authorization_ref") is not None:
        errors.append("provider_execution_intent.authorization_ref must be null before authorization")
    if intent.get("provider_call_performed_by_request_builder") is not False:
        errors.append(
            "provider_execution_intent.provider_call_performed_by_request_builder must be false"
        )


def check_budget(request: dict[str, Any], errors: list[str]) -> None:
    budget = as_obj(request.get("execution_budget"))
    attempt_count = budget.get("attempt_count")
    max_attempts = budget.get("max_attempts")
    remaining = budget.get("remaining_attempts")
    if all(isinstance(value, int) for value in (attempt_count, max_attempts, remaining)):
        if remaining != max(0, max_attempts - attempt_count):
            errors.append("execution_budget.remaining_attempts must equal max(0, max_attempts - attempt_count)")


def check_refs(request: dict[str, Any], errors: list[str]) -> None:
    refs = as_list(request.get("input_refs")) + as_list(request.get("context_refs"))
    for index, ref in enumerate(refs):
        if not isinstance(ref, dict):
            errors.append(f"refs[{index}] must be object")
            continue
        path = ref.get("path")
        if not isinstance(path, str) or not path:
            errors.append(f"refs[{index}].path must be non-empty")
            continue
        if path.startswith(("http://", "https://", "data:")):
            errors.append(f"refs[{index}] must use local refs, not URLs")
        if not repo_path(path).exists():
            errors.append(f"refs[{index}] references missing file: {path}")


def check_gates(request: dict[str, Any], errors: list[str]) -> None:
    gates = as_obj(request.get("required_gates"))
    if "explicit_user_authorization" not in as_list(gates.get("before_provider_execution")):
        errors.append("required_gates.before_provider_execution must include explicit_user_authorization")
    if "provider_output_envelope" not in as_list(gates.get("after_provider_execution")):
        errors.append("required_gates.after_provider_execution must include provider_output_envelope")
    if "promotion_report" not in as_list(gates.get("before_activation")):
        errors.append("required_gates.before_activation must include promotion_report")


def check_retention_and_safety(request: dict[str, Any], errors: list[str]) -> None:
    retention = as_obj(request.get("retention_policy"))
    for key in ("prompt_body_storage", "provider_body_storage", "secret_storage"):
        if retention.get(key) != "forbidden":
            errors.append(f"retention_policy.{key} must be forbidden")
    if retention.get("executor_result_storage") != "provider_output_envelope_redacted_only":
        errors.append("retention_policy.executor_result_storage must be provider_output_envelope_redacted_only")
    safety = as_obj(request.get("request_builder_safety"))
    for key in (
        "reads_env",
        "calls_provider",
        "stores_prompt_body",
        "stores_provider_body",
        "writes_world_state",
        "activates_runtime",
    ):
        if safety.get(key) is not False:
            errors.append(f"request_builder_safety.{key} must be false")


def validate_generation_executor_run_request(request: dict[str, Any]) -> list[str]:
    errors = validate_json_schema(request, SCHEMA_PATH)
    if request.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    scan_forbidden(request, errors)
    check_authority(request, errors)
    check_provider_intent(request, errors)
    check_budget(request, errors)
    check_refs(request, errors)
    check_gates(request, errors)
    check_retention_and_safety(request, errors)
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    args = parser.parse_args()
    request = load_json(args.request)
    if not isinstance(request, dict):
        print("GenerationExecutorRunRequest root must be an object", file=sys.stderr)
        return 1
    errors = validate_generation_executor_run_request(request)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"GenerationExecutorRunRequest validation passed: {args.request}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
