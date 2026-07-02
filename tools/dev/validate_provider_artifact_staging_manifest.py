#!/usr/bin/env python3
"""Validate ProviderArtifactStagingManifest v0.1 artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
ASSET_GRAPH_DIR = ROOT / "tools" / "asset_graph"
DEV_DIR = ROOT / "tools" / "dev"
for path in (ASSET_GRAPH_DIR, DEV_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from validation_common import load_json, validate_json_schema  # noqa: E402
from validate_provider_output_envelope import validate_provider_output_envelope  # noqa: E402


SCHEMA_PATH = ROOT / "shared/schemas/provider_artifact_staging_manifest.v0.1.schema.json"
SCHEMA_VERSION = "provider_artifact_staging_manifest.v0.1"
SOURCE_ENVELOPE_VERSION = "provider_output_envelope.v0.1"
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
                errors.append(f"forbidden key in ProviderArtifactStagingManifest: {child_path}")
            scan_forbidden(child, errors, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_forbidden(child, errors, f"{path}[{index}]")
    elif isinstance(value, str):
        lowered = value.lower()
        for fragment in FORBIDDEN_STRING_FRAGMENTS:
            if fragment in lowered:
                errors.append(f"forbidden string fragment {fragment!r} at {path}")


def load_source_envelope(manifest: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    ref = manifest.get("source_envelope_ref")
    if not isinstance(ref, str) or not ref:
        errors.append("source_envelope_ref must be non-empty")
        return {}
    if ref.startswith(("http://", "https://", "data:")):
        errors.append("source_envelope_ref must be a local path, not a URL")
        return {}
    path = repo_path(ref)
    if not path.exists():
        errors.append(f"source_envelope_ref references missing file: {ref}")
        return {}
    try:
        source = load_json(path)
    except Exception as exc:  # noqa: BLE001 - validator should surface file errors.
        errors.append(f"cannot load source_envelope_ref {ref}: {exc}")
        return {}
    if not isinstance(source, dict):
        errors.append("source_envelope_ref must point to a JSON object")
        return {}
    source_errors = validate_provider_output_envelope(source)
    for source_error in source_errors:
        errors.append(f"source ProviderOutputEnvelope invalid: {source_error}")
    return source


def check_authority(manifest: dict[str, Any], errors: list[str]) -> None:
    authority = as_obj(manifest.get("authority"))
    if authority.get("review_only") is not True:
        errors.append("authority.review_only must be true")
    if authority.get("runtime_activation_allowed") is not False:
        errors.append("authority.runtime_activation_allowed must be false")
    if authority.get("world_mutation_allowed") is not False:
        errors.append("authority.world_mutation_allowed must be false")
    if authority.get("player_visible") is not False:
        errors.append("authority.player_visible must be false")


def check_retention(manifest: dict[str, Any], errors: list[str]) -> None:
    retention = as_obj(manifest.get("retention_policy"))
    for key in ("prompt_body_storage", "provider_body_storage", "secret_storage"):
        if retention.get(key) != "forbidden":
            errors.append(f"retention_policy.{key} must be forbidden")
    if retention.get("temporary_url_policy") != "local_ref_required":
        errors.append("retention_policy.temporary_url_policy must be local_ref_required")
    if retention.get("local_refs_only") is not True:
        errors.append("retention_policy.local_refs_only must be true")
    if retention.get("runtime_claim_policy") != "forbidden_before_promotion":
        errors.append("retention_policy.runtime_claim_policy must be forbidden_before_promotion")


def source_artifact_ids(source_envelope: dict[str, Any]) -> set[str]:
    manifest = as_obj(source_envelope.get("artifact_manifest"))
    refs = as_list(manifest.get("output_refs"))
    ids: set[str] = set()
    for ref in refs:
        if isinstance(ref, dict) and isinstance(ref.get("artifact_id"), str):
            ids.add(ref["artifact_id"])
    return ids


def check_staged_artifacts(
    manifest: dict[str, Any],
    source_envelope: dict[str, Any],
    errors: list[str],
) -> None:
    status = manifest.get("staging_status")
    artifacts = as_list(manifest.get("staged_artifacts"))
    if status == "review_only_artifacts_staged" and not artifacts:
        errors.append("review_only_artifacts_staged requires staged_artifacts")
    if status == "no_artifacts_guarded" and artifacts:
        errors.append("no_artifacts_guarded must not contain staged_artifacts")

    source_ids = source_artifact_ids(source_envelope)
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            errors.append(f"staged_artifacts[{index}] must be object")
            continue
        if artifact.get("source_artifact_id") not in source_ids:
            errors.append(f"staged_artifacts[{index}].source_artifact_id must exist in source envelope output_refs")
        path = artifact.get("path")
        if not isinstance(path, str) or not path:
            errors.append(f"staged_artifacts[{index}].path must be non-empty")
            continue
        if path.startswith(("http://", "https://", "data:")):
            errors.append(f"staged_artifacts[{index}] must use local refs, not URLs")
        if not repo_path(path).exists():
            errors.append(f"staged_artifacts[{index}] references missing file: {path}")
        if artifact.get("media_layer") not in {"candidate_ref", "processed_preview", "staging_report"}:
            errors.append(f"staged_artifacts[{index}].media_layer is invalid")
        if artifact.get("runtime_visible") is not False:
            errors.append(f"staged_artifacts[{index}].runtime_visible must be false")
        if artifact.get("player_visible") is not False:
            errors.append(f"staged_artifacts[{index}].player_visible must be false")


def check_gates(manifest: dict[str, Any], errors: list[str]) -> None:
    validation = as_obj(manifest.get("validation_results"))
    for gate_name in (
        "source_envelope_gate",
        "local_ref_gate",
        "schema_gate",
        "media_gate",
        "semantic_gate",
        "human_review",
    ):
        gate = as_obj(validation.get(gate_name))
        if gate.get("status") != "not_applicable" and gate.get("required_before_promotion") is not True:
            errors.append(f"validation_results.{gate_name}.required_before_promotion must be true")
    promotion = as_obj(manifest.get("promotion_gate"))
    if promotion.get("promotion_allowed") is not False:
        errors.append("promotion_gate.promotion_allowed must be false")
    if not as_list(promotion.get("required_next_gates")):
        errors.append("promotion_gate.required_next_gates must be non-empty")


def check_source_consistency(
    manifest: dict[str, Any],
    source_envelope: dict[str, Any],
    errors: list[str],
) -> None:
    if not source_envelope:
        return
    if source_envelope.get("schema_version") != SOURCE_ENVELOPE_VERSION:
        errors.append(f"source envelope schema_version must be {SOURCE_ENVELOPE_VERSION}")
    if manifest.get("source_envelope_id") != source_envelope.get("envelope_id"):
        errors.append("source_envelope_id must match source envelope envelope_id")
    source_manifest = as_obj(source_envelope.get("artifact_manifest"))
    source_refs = as_list(source_manifest.get("output_refs"))
    if manifest.get("staging_status") == "review_only_artifacts_staged" and not source_refs:
        errors.append("review_only_artifacts_staged requires source envelope output_refs")
    authority = as_obj(source_envelope.get("authority"))
    if authority.get("review_only") is not True:
        errors.append("source envelope must also be review_only")
    activation = as_obj(source_envelope.get("activation_gate"))
    if activation.get("activation_allowed") is not False:
        errors.append("source envelope activation_gate.activation_allowed must be false")


def validate_provider_artifact_staging_manifest(manifest: dict[str, Any]) -> list[str]:
    errors = validate_json_schema(manifest, SCHEMA_PATH)
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    scan_forbidden(manifest, errors)
    source_envelope = load_source_envelope(manifest, errors)
    check_source_consistency(manifest, source_envelope, errors)
    check_authority(manifest, errors)
    check_retention(manifest, errors)
    check_staged_artifacts(manifest, source_envelope, errors)
    check_gates(manifest, errors)
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    manifest = load_json(args.manifest)
    if not isinstance(manifest, dict):
        print("ProviderArtifactStagingManifest root must be an object", file=sys.stderr)
        return 1
    errors = validate_provider_artifact_staging_manifest(manifest)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"ProviderArtifactStagingManifest validation passed: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
