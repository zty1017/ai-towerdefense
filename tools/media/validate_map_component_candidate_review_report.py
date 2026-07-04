#!/usr/bin/env python3
"""Validate MapComponentCandidateReviewReport v0.1."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA = ROOT / "shared/schemas/map_component_candidate_review_report.v0.1.schema.json"
FORBIDDEN_KEY_FRAGMENTS = (
    "provider",
    "model",
    "prompt",
    "raw_prompt",
    "full_prompt",
    "full_trace",
    "raw_json",
    "api_key",
    "secret",
    "unreviewed_content",
    "temporary_url",
)
EXTERNAL_URL_MARKERS = ("http://", "https://", "://")
REQUIRED_USAGE_POLICY = {
    "review_gate_only",
    "not_runtime_semantic_source",
    "no_image_to_map_semantic_inference",
    "baseline_fixture_is_not_generated_candidate",
    "no_frontend_default_consumption",
    "no_provider_or_prompt_payload",
    "no_external_temporary_url",
}
GENERATED_STAGING_FIELDS = (
    "staging_slot_id",
    "candidate_local_path",
    "candidate_sha256",
    "staging_import_status",
    "artifact_review_status",
)
APPROVAL_RECORD_FIELDS = {
    "approval_status",
    "approval_scope",
    "approved_at",
    "reviewer",
    "rationale",
    "source_approval_plan_path",
}
APPROVAL_SCOPE_CANDIDATE_REVIEW = "candidate_review"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def resolve_repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_valid_datetime(value: str) -> bool:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def scan_forbidden_key_fragments(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            lowered = key.lower()
            if any(fragment in lowered for fragment in FORBIDDEN_KEY_FRAGMENTS):
                errors.append(f"forbidden field '{child_path}' is not allowed")
            scan_forbidden_key_fragments(child, child_path, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_forbidden_key_fragments(child, f"{path}[{index}]", errors)


def scan_external_urls(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            scan_external_urls(child, f"{path}.{key}" if path else key, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_external_urls(child, f"{path}[{index}]", errors)
    elif isinstance(value, str):
        lowered = value.lower()
        if any(marker in lowered for marker in EXTERNAL_URL_MARKERS):
            errors.append(f"{path} must not contain an external URL")


def validate_approval_record(
    approval_record: Any,
    *,
    path: str,
    required_scope: str,
    errors: list[str],
) -> bool:
    if not isinstance(approval_record, dict):
        errors.append(f"{path} must be an object")
        return False

    unexpected_keys = sorted(set(approval_record) - APPROVAL_RECORD_FIELDS)
    for key in unexpected_keys:
        errors.append(f"{path} contains unsupported field: {key}")
    missing_keys = sorted(APPROVAL_RECORD_FIELDS - set(approval_record))
    for key in missing_keys:
        errors.append(f"{path}.{key} is required")

    approval_status = approval_record.get("approval_status")
    if approval_status != "approved":
        errors.append(f"{path}.approval_status must be approved")

    approval_scope = approval_record.get("approval_scope")
    scope_values = [str(scope) for scope in as_list(approval_scope)]
    if not scope_values:
        errors.append(f"{path}.approval_scope must not be empty")
    if required_scope not in scope_values:
        errors.append(f"{path}.approval_scope must include {required_scope}")

    approved_at = approval_record.get("approved_at")
    if not isinstance(approved_at, str) or not approved_at.strip():
        errors.append(f"{path}.approved_at must be a non-empty string")
    elif not is_valid_datetime(approved_at):
        errors.append(f"{path}.approved_at must be an ISO 8601 date-time")

    for key in ("reviewer", "rationale", "source_approval_plan_path"):
        value = approval_record.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{path}.{key} must be a non-empty string")

    source_path = approval_record.get("source_approval_plan_path")
    if isinstance(source_path, str) and source_path.strip():
        resolved_source_path = resolve_repo_path(source_path)
        if not resolved_source_path.exists():
            errors.append(f"{path}.source_approval_plan_path does not exist: {source_path}")

    return not any(error.startswith(path) for error in errors)


def validate_with_jsonschema(value: dict[str, Any], schema: dict[str, Any] | None) -> list[str]:
    if not schema:
        return []
    try:
        import jsonschema  # type: ignore
    except Exception:
        return []
    validator_cls = getattr(jsonschema, "Draft202012Validator", None)
    if validator_cls is None:
        validator_cls = getattr(jsonschema, "Draft7Validator", None)
    if validator_cls is None:
        return []
    validator = validator_cls(schema)
    return [
        f"schema: {'.'.join(map(str, error.path)) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(value), key=str)
    ]


def load_artifact_staging_manifest(report: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    staging_path_value = report.get("source_artifact_staging_manifest_path")
    if not isinstance(staging_path_value, str) or not staging_path_value.strip():
        errors.append("source_artifact_staging_manifest_path must be a non-empty string")
        return {}
    staging_path = resolve_repo_path(staging_path_value)
    if not staging_path.exists():
        errors.append(f"source_artifact_staging_manifest_path does not exist: {staging_path_value}")
        return {}
    try:
        staging_manifest = load_json(staging_path)
    except json.JSONDecodeError as exc:
        errors.append(f"source_artifact_staging_manifest_path is not valid JSON: {exc}")
        return {}
    if not isinstance(staging_manifest, dict):
        errors.append("source artifact staging manifest root must be an object")
        return {}
    if staging_manifest.get("schema_version") != "map_component_artifact_staging_manifest.v0.1":
        errors.append("source artifact staging manifest must be MapComponentArtifactStagingManifest v0.1")
    if report.get("source_request_pack_path") != staging_manifest.get("source_request_pack_path"):
        errors.append("source_request_pack_path must match artifact staging source_request_pack_path")
    if report.get("source_manifest_path") != staging_manifest.get("source_manifest_path"):
        errors.append("source_manifest_path must match artifact staging source_manifest_path")
    return staging_manifest


def validate_baseline_candidate(candidate: dict[str, Any], index: int, errors: list[str]) -> None:
    if candidate.get("promotion_allowed_now") is not False:
        errors.append(f"candidates[{index}] baseline fixture cannot allow promotion")
    if candidate.get("review_status") != "no_generated_candidate_yet":
        errors.append(f"candidates[{index}] baseline fixture status must be no_generated_candidate_yet")
    if candidate.get("promotion_recommendation") != "do_not_promote":
        errors.append(f"candidates[{index}] baseline fixture recommendation must be do_not_promote")
    for field in GENERATED_STAGING_FIELDS:
        if field in candidate:
            errors.append(f"candidates[{index}] baseline fixture must not include {field}")
    if "approval_record" in candidate:
        errors.append(f"candidates[{index}] baseline fixture must not include approval_record")


def validate_generated_candidate(
    candidate: dict[str, Any],
    index: int,
    slots_by_id: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    slot_id = candidate.get("staging_slot_id")
    if not isinstance(slot_id, str) or not slot_id.strip():
        errors.append(f"candidates[{index}].staging_slot_id must be a non-empty string")
        return
    slot = slots_by_id.get(slot_id)
    if not slot:
        errors.append(f"candidates[{index}] generated candidate has no matching artifact staging slot: {slot_id}")
        return

    if slot.get("import_status") != "imported" or slot.get("review_status") != "staged_for_review":
        errors.append(
            f"candidates[{index}] generated candidate must come from an imported + staged_for_review slot"
        )
    if not slot.get("candidate_local_path"):
        errors.append(f"candidates[{index}] generated candidate staging slot has no candidate_local_path")

    expected_pairs = {
        "request_id": slot.get("request_id"),
        "component_id": slot.get("component_id"),
        "component_role": slot.get("component_role"),
        "style_pack_id": slot.get("style_pack_id"),
        "node_id": slot.get("node_id"),
        "target_size": as_obj(slot.get("expected_size")),
        "candidate_local_path": slot.get("candidate_local_path"),
        "candidate_sha256": slot.get("candidate_sha256"),
        "staging_import_status": slot.get("import_status"),
        "artifact_review_status": slot.get("review_status"),
    }
    for key, expected in expected_pairs.items():
        actual = as_obj(candidate.get(key)) if key == "target_size" else candidate.get(key)
        if actual != expected:
            errors.append(f"candidates[{index}].{key} must match artifact staging slot")

    is_approved_tuple = (
        candidate.get("review_status") == "passed"
        and candidate.get("promotion_recommendation") == "eligible_for_promotion"
        and candidate.get("promotion_allowed_now") is True
    )
    is_blocked_tuple = (
        candidate.get("review_status") == "blocked_from_promotion"
        and candidate.get("promotion_recommendation") == "do_not_promote"
        and candidate.get("promotion_allowed_now") is False
    )
    approval_record = candidate.get("approval_record")
    if is_approved_tuple:
        validate_approval_record(
            approval_record,
            path=f"candidates[{index}].approval_record",
            required_scope=APPROVAL_SCOPE_CANDIDATE_REVIEW,
            errors=errors,
        )
    elif is_blocked_tuple:
        if "approval_record" in candidate:
            errors.append(f"candidates[{index}] blocked generated candidate must not include approval_record")
    else:
        errors.append(
            f"candidates[{index}] generated candidate must be either blocked_from_promotion/"
            "do_not_promote/false or passed/eligible_for_promotion/true with approval_record"
        )

    candidate_path_value = candidate.get("candidate_local_path")
    candidate_sha = candidate.get("candidate_sha256")
    if isinstance(candidate_path_value, str) and isinstance(candidate_sha, str):
        candidate_path = resolve_repo_path(candidate_path_value)
        if not candidate_path.exists():
            errors.append(f"candidates[{index}].candidate_local_path does not exist: {candidate_path_value}")
        elif candidate_sha != sha256_file(candidate_path):
            errors.append(f"candidates[{index}].candidate_sha256 does not match local file")


def validate_report(report: dict[str, Any], schema: dict[str, Any] | None = None) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_with_jsonschema(report, schema))
    scan_forbidden_key_fragments(report, "", errors)
    scan_external_urls(report, "", errors)

    if report.get("schema_version") != "map_component_candidate_review_report.v0.1":
        errors.append("schema_version must be 'map_component_candidate_review_report.v0.1'")

    usage_policy = set(map(str, as_list(report.get("usage_policy"))))
    missing_policy = sorted(REQUIRED_USAGE_POLICY - usage_policy)
    if missing_policy:
        errors.append(f"usage_policy missing required policies: {', '.join(missing_policy)}")

    artifact_staging = load_artifact_staging_manifest(report, errors)
    slots_by_id = {
        str(slot.get("slot_id") or ""): slot
        for slot in as_list(artifact_staging.get("staging_slots"))
        if isinstance(slot, dict)
    }

    candidates = [item for item in as_list(report.get("candidates")) if isinstance(item, dict)]
    candidate_ids: set[str] = set()
    duplicate_ids: set[str] = set()
    for index, candidate in enumerate(candidates):
        candidate_id = str(candidate.get("candidate_id") or "")
        if candidate_id in candidate_ids:
            duplicate_ids.add(candidate_id)
        candidate_ids.add(candidate_id)

        item_policy = set(map(str, as_list(candidate.get("usage_policy"))))
        missing_item_policy = sorted(REQUIRED_USAGE_POLICY - item_policy)
        if missing_item_policy:
            errors.append(
                f"candidates[{index}].usage_policy missing required policies: {', '.join(missing_item_policy)}"
            )

        candidate_kind = candidate.get("candidate_kind")
        if candidate_kind == "baseline_fixture_candidate":
            validate_baseline_candidate(candidate, index, errors)
        elif candidate_kind == "generated_candidate":
            validate_generated_candidate(candidate, index, slots_by_id, errors)
        else:
            errors.append(f"candidates[{index}].candidate_kind must be baseline_fixture_candidate or generated_candidate")

        local_path_value = candidate.get("baseline_local_path")
        if not isinstance(local_path_value, str):
            errors.append(f"candidates[{index}].baseline_local_path must be a string")
            continue
        local_path = resolve_repo_path(local_path_value)
        if not local_path.exists():
            errors.append(f"candidates[{index}].baseline_local_path does not exist: {local_path_value}")
        elif candidate.get("baseline_sha256") != sha256_file(local_path):
            errors.append(f"candidates[{index}].baseline_sha256 does not match local file")

        if not as_list(candidate.get("findings")):
            errors.append(f"candidates[{index}].findings must not be empty")
        if not as_list(candidate.get("required_next_actions")):
            errors.append(f"candidates[{index}].required_next_actions must not be empty")

    for candidate_id in sorted(duplicate_ids):
        errors.append(f"duplicate candidate_id: {candidate_id}")

    summary = as_obj(report.get("summary"))
    status_counts = Counter(str(candidate.get("review_status")) for candidate in candidates)
    kind_counts = Counter(str(candidate.get("candidate_kind")) for candidate in candidates)
    promotable_count = len(
        [
            candidate
            for candidate in candidates
            if candidate.get("promotion_allowed_now") is True
            and candidate.get("promotion_recommendation") == "eligible_for_promotion"
        ]
    )
    expected = {
        "candidate_count": len(candidates),
        "baseline_fixture_candidate_count": kind_counts.get("baseline_fixture_candidate", 0),
        "generated_candidate_count": kind_counts.get("generated_candidate", 0),
        "promotable_count": promotable_count,
        "blocked_from_promotion_count": len(candidates) - promotable_count,
        "no_generated_candidate_yet_count": status_counts.get("no_generated_candidate_yet", 0),
    }
    for key, value in expected.items():
        if summary.get(key) != value:
            errors.append(f"summary.{key} must be {value}")
    if as_obj(summary.get("status_counts")) != dict(sorted(status_counts.items())):
        errors.append("summary.status_counts must match candidate review statuses")
    if as_obj(summary.get("candidate_kind_counts")) != dict(sorted(kind_counts.items())):
        errors.append("summary.candidate_kind_counts must match candidate kinds")

    expected_status = "blocked_from_promotion" if expected["blocked_from_promotion_count"] else "passed"
    if report.get("status") != expected_status:
        errors.append(f"status must be {expected_status!r} based on candidate promotion state")
    return list(dict.fromkeys(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate MapComponentCandidateReviewReport v0.1.")
    parser.add_argument("report", help="Report JSON path.")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    args = parser.parse_args()

    report_path = Path(args.report)
    schema_path = Path(args.schema)
    try:
        report = load_json(report_path)
    except FileNotFoundError:
        print("INVALID MapComponentCandidateReviewReport")
        print(f"- report file not found: {report_path}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID MapComponentCandidateReviewReport")
        print(f"- report is not valid JSON: {exc}")
        return 1
    if not isinstance(report, dict):
        print("INVALID MapComponentCandidateReviewReport")
        print("- report root must be an object")
        return 1

    schema = load_json(schema_path) if schema_path.exists() else None
    if not isinstance(schema, dict):
        schema = None
    errors = validate_report(report, schema)
    if errors:
        print("INVALID MapComponentCandidateReviewReport")
        for error in errors:
            print(f"- {error}")
        return 1

    summary = as_obj(report.get("summary"))
    print(f"OK: {report_path}")
    print(f"- status: {report.get('status')}")
    print(f"- candidate_count: {summary.get('candidate_count')}")
    print(f"- generated_candidate_count: {summary.get('generated_candidate_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
