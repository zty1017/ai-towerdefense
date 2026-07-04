#!/usr/bin/env python3
"""Validate ProviderOutputEnvelope v0.1 artifacts."""

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

from validation_common import load_json, validate_json_schema  # noqa: E402


SCHEMA_PATH = ROOT / "shared/schemas/provider_output_envelope.v0.1.schema.json"
SCHEMA_VERSION = "provider_output_envelope.v0.1"
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
                errors.append(f"forbidden key in ProviderOutputEnvelope: {child_path}")
            scan_forbidden(child, errors, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_forbidden(child, errors, f"{path}[{index}]")
    elif isinstance(value, str):
        lowered = value.lower()
        for fragment in FORBIDDEN_STRING_FRAGMENTS:
            if fragment in lowered:
                errors.append(f"forbidden string fragment {fragment!r} at {path}")


def check_authority(envelope: dict[str, Any], errors: list[str]) -> None:
    authority = as_obj(envelope.get("authority"))
    if authority.get("review_only") is not True:
        errors.append("authority.review_only must be true")
    if authority.get("runtime_activation_allowed") is not False:
        errors.append("authority.runtime_activation_allowed must be false")
    if authority.get("world_mutation_allowed") is not False:
        errors.append("authority.world_mutation_allowed must be false")
    if authority.get("player_visible") is not False:
        errors.append("authority.player_visible must be false")


def check_retention(envelope: dict[str, Any], errors: list[str]) -> None:
    retention = as_obj(envelope.get("retention_policy"))
    expected_forbidden = {
        "prompt_body_storage",
        "provider_body_storage",
        "secret_storage",
    }
    for key in sorted(expected_forbidden):
        if retention.get(key) != "forbidden":
            errors.append(f"retention_policy.{key} must be forbidden")
    if retention.get("temporary_url_policy") not in {
        "forbidden",
        "download_then_local_ref_only",
    }:
        errors.append("retention_policy.temporary_url_policy is invalid")


def check_provider_call(envelope: dict[str, Any], errors: list[str]) -> None:
    call = as_obj(envelope.get("provider_call"))
    performed = call.get("performed")
    status = call.get("status")
    authorization_granted = call.get("authorization_granted")
    authorization_ref = call.get("authorization_ref")
    if call.get("authorization_required") is not True:
        errors.append("provider_call.authorization_required must be true")
    if performed is True:
        if status not in {"performed_redacted", "failed_redacted"}:
            errors.append("performed provider calls must use performed_redacted or failed_redacted status")
        if authorization_granted is not True or not authorization_ref:
            errors.append("performed provider calls require granted authorization_ref")
    elif performed is False:
        if status not in {"not_performed_guarded", "cancelled"}:
            errors.append("unperformed provider calls must be guarded or cancelled")
        if authorization_granted is not False:
            errors.append("unperformed provider calls must not claim authorization_granted")
    else:
        errors.append("provider_call.performed must be boolean")


def check_artifacts(envelope: dict[str, Any], errors: list[str]) -> None:
    manifest = as_obj(envelope.get("artifact_manifest"))
    output_refs = as_list(manifest.get("output_refs"))
    if manifest.get("review_only") is not True:
        errors.append("artifact_manifest.review_only must be true")
    if manifest.get("status") == "review_only_artifacts_ready" and not output_refs:
        errors.append("review_only_artifacts_ready requires output_refs")
    if manifest.get("status") == "not_created" and output_refs:
        errors.append("not_created artifact manifest must not contain output_refs")
    for index, ref in enumerate(output_refs):
        if not isinstance(ref, dict):
            errors.append(f"artifact_manifest.output_refs[{index}] must be object")
            continue
        path = ref.get("path")
        if not isinstance(path, str) or not path:
            errors.append(f"artifact_manifest.output_refs[{index}].path must be non-empty")
            continue
        if path.startswith(("http://", "https://", "data:")):
            errors.append(f"artifact_manifest.output_refs[{index}] must use local artifact refs, not URLs")
        if not repo_path(path).exists():
            errors.append(f"artifact_manifest.output_refs[{index}] references missing file: {path}")
        if ref.get("media_layer") == "raw_media":
            errors.append(f"artifact_manifest.output_refs[{index}] must not expose raw_media")


def check_gates(envelope: dict[str, Any], errors: list[str]) -> None:
    activation = as_obj(envelope.get("activation_gate"))
    if activation.get("activation_allowed") is not False:
        errors.append("activation_gate.activation_allowed must be false")
    if not as_list(activation.get("required_next_gates")):
        errors.append("activation_gate.required_next_gates must be non-empty")
    validation = as_obj(envelope.get("validation"))
    for gate_name in ("schema_gate", "semantic_gate", "media_gate", "human_review"):
        gate = as_obj(validation.get(gate_name))
        if gate.get("required_before_activation") is not True and gate.get("status") not in {
            "not_applicable",
        }:
            errors.append(f"validation.{gate_name}.required_before_activation must be true")


def check_consistency(envelope: dict[str, Any], errors: list[str]) -> None:
    call = as_obj(envelope.get("provider_call"))
    result = as_obj(envelope.get("redacted_result_summary"))
    manifest = as_obj(envelope.get("artifact_manifest"))
    if call.get("performed") is False:
        if result.get("status") != "blocked_before_provider_call":
            errors.append("unperformed provider calls must have blocked_before_provider_call result status")
        if manifest.get("status") != "not_created":
            errors.append("unperformed provider calls must not create artifact manifests")
    if call.get("performed") is True:
        if result.get("status") == "blocked_before_provider_call":
            errors.append("performed provider calls must not use blocked_before_provider_call result status")
        if manifest.get("status") == "not_created":
            errors.append("performed provider calls must produce or fail a review-only artifact manifest")


def validate_provider_output_envelope(envelope: dict[str, Any]) -> list[str]:
    errors = validate_json_schema(envelope, SCHEMA_PATH)
    if envelope.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    scan_forbidden(envelope, errors)
    check_authority(envelope, errors)
    check_retention(envelope, errors)
    check_provider_call(envelope, errors)
    check_artifacts(envelope, errors)
    check_gates(envelope, errors)
    check_consistency(envelope, errors)
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("envelope", type=Path)
    args = parser.parse_args()
    envelope = load_json(args.envelope)
    if not isinstance(envelope, dict):
        print("ProviderOutputEnvelope root must be an object", file=sys.stderr)
        return 1
    errors = validate_provider_output_envelope(envelope)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"ProviderOutputEnvelope validation passed: {args.envelope}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
