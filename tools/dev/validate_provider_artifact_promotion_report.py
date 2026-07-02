#!/usr/bin/env python3
"""Validate ProviderArtifactPromotionReport v0.1 artifacts."""

from __future__ import annotations

import argparse
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
from validate_provider_artifact_staging_manifest import (  # noqa: E402
    validate_provider_artifact_staging_manifest,
)


SCHEMA_PATH = ROOT / "shared/schemas/provider_artifact_promotion_report.v0.1.schema.json"
SCHEMA_VERSION = "provider_artifact_promotion_report.v0.1"
STAGING_SCHEMA_VERSION = "provider_artifact_staging_manifest.v0.1"
APPROVED_DECISIONS = {
    "approved_for_runtime_package_build",
    "approved_for_world_transaction_build",
    "approved_for_runtime_and_world_build",
}
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
    "runtime-ready",
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
                errors.append(f"forbidden key in ProviderArtifactPromotionReport: {child_path}")
            scan_forbidden(child, errors, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_forbidden(child, errors, f"{path}[{index}]")
    elif isinstance(value, str):
        lowered = value.lower()
        for fragment in FORBIDDEN_STRING_FRAGMENTS:
            if fragment in lowered:
                errors.append(f"forbidden string fragment {fragment!r} at {path}")


def load_source_staging(report: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    ref = report.get("source_staging_ref")
    if not isinstance(ref, str) or not ref:
        errors.append("source_staging_ref must be non-empty")
        return {}
    if ref.startswith(("http://", "https://", "data:")):
        errors.append("source_staging_ref must be a local path, not a URL")
        return {}
    path = repo_path(ref)
    if not path.exists():
        errors.append(f"source_staging_ref references missing file: {ref}")
        return {}
    try:
        staging = load_json(path)
    except Exception as exc:  # noqa: BLE001 - CLI validator should surface file errors.
        errors.append(f"cannot load source_staging_ref {ref}: {exc}")
        return {}
    if not isinstance(staging, dict):
        errors.append("source_staging_ref must point to a JSON object")
        return {}
    staging_errors = validate_provider_artifact_staging_manifest(staging)
    for staging_error in staging_errors:
        errors.append(f"source ProviderArtifactStagingManifest invalid: {staging_error}")
    return staging


def staging_artifact_ids(staging: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for artifact in as_list(staging.get("staged_artifacts")):
        if isinstance(artifact, dict) and isinstance(artifact.get("artifact_id"), str):
            ids.add(artifact["artifact_id"])
    return ids


def check_authority(report: dict[str, Any], errors: list[str]) -> None:
    authority = as_obj(report.get("authority"))
    if authority.get("report_only") is not True:
        errors.append("authority.report_only must be true")
    if authority.get("direct_runtime_mutation_allowed") is not False:
        errors.append("authority.direct_runtime_mutation_allowed must be false")
    if authority.get("direct_world_mutation_allowed") is not False:
        errors.append("authority.direct_world_mutation_allowed must be false")
    if authority.get("player_visible") is not False:
        errors.append("authority.player_visible must be false")


def check_retention(report: dict[str, Any], errors: list[str]) -> None:
    retention = as_obj(report.get("retention_policy"))
    for key in ("prompt_body_storage", "provider_body_storage", "secret_storage"):
        if retention.get(key) != "forbidden":
            errors.append(f"retention_policy.{key} must be forbidden")
    if retention.get("temporary_url_policy") != "local_ref_required":
        errors.append("retention_policy.temporary_url_policy must be local_ref_required")


def check_safety(report: dict[str, Any], errors: list[str]) -> None:
    safety = as_obj(report.get("safety_summary"))
    for key in (
        "provider_call_count_by_report",
        "world_mutation_count_by_report",
        "runtime_mutation_count_by_report",
    ):
        if safety.get(key) != 0:
            errors.append(f"safety_summary.{key} must be 0")
    for key in (
        "stores_prompt_body",
        "stores_provider_body",
        "stores_secret",
        "uses_temporary_url",
    ):
        if safety.get(key) is not False:
            errors.append(f"safety_summary.{key} must be false")


def check_refs_are_local(refs: list[Any], errors: list[str], path: str) -> None:
    for index, ref in enumerate(refs):
        if not isinstance(ref, dict):
            errors.append(f"{path}[{index}] must be object")
            continue
        ref_path = ref.get("path")
        if not isinstance(ref_path, str) or not ref_path:
            errors.append(f"{path}[{index}].path must be non-empty")
            continue
        if ref_path.startswith(("http://", "https://", "data:")):
            errors.append(f"{path}[{index}] must use local refs, not URLs")
        if not repo_path(ref_path).exists():
            errors.append(f"{path}[{index}] references missing file: {ref_path}")


def check_reviewed_artifacts(
    report: dict[str, Any],
    staging: dict[str, Any],
    errors: list[str],
) -> None:
    source_ids = staging_artifact_ids(staging)
    reviewed = as_list(report.get("reviewed_artifacts"))
    if not reviewed:
        errors.append("reviewed_artifacts must be non-empty")
    for index, artifact in enumerate(reviewed):
        if not isinstance(artifact, dict):
            errors.append(f"reviewed_artifacts[{index}] must be object")
            continue
        artifact_id = artifact.get("staged_artifact_id")
        if artifact_id not in source_ids:
            errors.append(f"reviewed_artifacts[{index}].staged_artifact_id must exist in source staging")
        ref_path = artifact.get("path")
        if not isinstance(ref_path, str) or not ref_path:
            errors.append(f"reviewed_artifacts[{index}].path must be non-empty")
            continue
        if ref_path.startswith(("http://", "https://", "data:")):
            errors.append(f"reviewed_artifacts[{index}] must use local refs, not URLs")
        if not repo_path(ref_path).exists():
            errors.append(f"reviewed_artifacts[{index}] references missing file: {ref_path}")


def check_gate_logic(report: dict[str, Any], staging: dict[str, Any], errors: list[str]) -> None:
    if staging.get("schema_version") != STAGING_SCHEMA_VERSION:
        errors.append(f"source staging schema_version must be {STAGING_SCHEMA_VERSION}")
    if report.get("source_staging_id") != staging.get("manifest_id"):
        errors.append("source_staging_id must match source staging manifest_id")

    decision = as_obj(report.get("decision"))
    promotion_decision = decision.get("promotion_decision")
    promotion_allowed = decision.get("promotion_allowed")
    gates = as_obj(report.get("gate_results"))
    required_gates = [
        gate_name
        for gate_name, gate in gates.items()
        if isinstance(gate, dict) and gate.get("required_before_promotion") is True
    ]
    not_passed_required = [
        gate_name
        for gate_name in required_gates
        if as_obj(gates.get(gate_name)).get("status") != "passed"
    ]

    staging_promotion = as_obj(staging.get("promotion_gate"))
    if staging_promotion.get("promotion_allowed") is False and promotion_allowed is True:
        errors.append("report cannot allow promotion while source staging promotion gate is false")

    if promotion_decision in APPROVED_DECISIONS:
        if promotion_allowed is not True:
            errors.append("approved promotion decisions require decision.promotion_allowed true")
        if not_passed_required:
            errors.append(f"approved promotion decisions require all required gates passed: {not_passed_required}")
        targets = as_obj(report.get("promotion_targets"))
        target_kind = targets.get("target_kind")
        if target_kind == "none":
            errors.append("approved promotion decisions require a non-none promotion_targets.target_kind")
    else:
        if promotion_allowed is not False:
            errors.append("blocked or rejected promotion decisions require decision.promotion_allowed false")
        if not decision.get("blocked_reason"):
            errors.append("blocked or rejected promotion decisions require decision.blocked_reason")
        if promotion_decision == "blocked_review_required" and not not_passed_required:
            errors.append("blocked_review_required requires at least one required gate not passed")


def check_targets(report: dict[str, Any], errors: list[str]) -> None:
    targets = as_obj(report.get("promotion_targets"))
    target_kind = targets.get("target_kind")
    runtime_refs = as_list(targets.get("runtime_package_refs"))
    world_refs = as_list(targets.get("world_transaction_refs"))
    media_refs = as_list(targets.get("published_media_refs"))
    check_refs_are_local(runtime_refs, errors, "promotion_targets.runtime_package_refs")
    check_refs_are_local(world_refs, errors, "promotion_targets.world_transaction_refs")
    check_refs_are_local(media_refs, errors, "promotion_targets.published_media_refs")
    if target_kind == "none" and (runtime_refs or world_refs or media_refs):
        errors.append("promotion_targets.target_kind none must not include target refs")


def validate_provider_artifact_promotion_report(report: dict[str, Any]) -> list[str]:
    errors = validate_json_schema(report, SCHEMA_PATH)
    if report.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    scan_forbidden(report, errors)
    staging = load_source_staging(report, errors)
    check_authority(report, errors)
    check_retention(report, errors)
    check_safety(report, errors)
    check_reviewed_artifacts(report, staging, errors)
    check_targets(report, errors)
    check_gate_logic(report, staging, errors)
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    report = load_json(args.report)
    if not isinstance(report, dict):
        print("ProviderArtifactPromotionReport root must be an object", file=sys.stderr)
        return 1
    errors = validate_provider_artifact_promotion_report(report)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"ProviderArtifactPromotionReport validation passed: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
