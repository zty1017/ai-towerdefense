#!/usr/bin/env python3
"""Validate MapComponentVisualQualityReport v0.1."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MEDIA_DIR = Path(__file__).resolve().parent
if str(MEDIA_DIR) not in sys.path:
    sys.path.insert(0, str(MEDIA_DIR))

import validate_map_component_candidate_review_report as candidate_validator  # noqa: E402


DEFAULT_SCHEMA = ROOT / "shared/schemas/map_component_visual_quality_report.v0.1.schema.json"
DEFAULT_CANDIDATE_SCHEMA = ROOT / "shared/schemas/map_component_candidate_review_report.v0.1.schema.json"
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
    "generated_candidates_only",
    "baseline_fixture_is_not_generated_candidate",
    "no_frontend_default_consumption",
    "no_manifest_or_style_pack_or_render_plan_mutation",
    "no_provider_or_prompt_payload",
    "no_external_temporary_url",
}
FALSE_EFFECT_FIELDS = {
    "manifest_replacement_written",
    "style_pack_modified",
    "render_plan_modified",
    "frontend_default_modified",
    "runtime_map_truth_modified",
    "generated_candidate_promoted",
    "promotion_gate_bypassed",
    "candidate_marked_runtime_ready",
}
APPROVAL_RECORD_FIELDS = {
    "approval_status",
    "approval_scope",
    "approved_at",
    "reviewer",
    "rationale",
    "source_approval_plan_path",
}
VISUAL_APPROVAL_SCOPES = {"visual_quality", "cutout_review"}


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


def validate_approval_record(approval_record: Any, *, path: str, errors: list[str]) -> None:
    if not isinstance(approval_record, dict):
        errors.append(f"{path} must be an object")
        return

    unexpected_keys = sorted(set(approval_record) - APPROVAL_RECORD_FIELDS)
    for key in unexpected_keys:
        errors.append(f"{path} contains unsupported field: {key}")
    missing_keys = sorted(APPROVAL_RECORD_FIELDS - set(approval_record))
    for key in missing_keys:
        errors.append(f"{path}.{key} is required")

    if approval_record.get("approval_status") != "approved":
        errors.append(f"{path}.approval_status must be approved")

    scope_values = [str(scope) for scope in as_list(approval_record.get("approval_scope"))]
    if not scope_values:
        errors.append(f"{path}.approval_scope must not be empty")
    if not VISUAL_APPROVAL_SCOPES.intersection(scope_values):
        errors.append(
            f"{path}.approval_scope must include one of "
            f"{', '.join(sorted(VISUAL_APPROVAL_SCOPES))}"
        )

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


def generated_candidates(candidate_review: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        candidate
        for candidate in as_list(candidate_review.get("candidates"))
        if isinstance(candidate, dict) and candidate.get("candidate_kind") == "generated_candidate"
    ]


def load_and_validate_candidate_review(report: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    source_value = report.get("source_candidate_review_report_path")
    if not isinstance(source_value, str) or not source_value.strip():
        errors.append("source_candidate_review_report_path must be a non-empty string")
        return {}
    source_path = resolve_repo_path(source_value)
    if not source_path.exists():
        errors.append(f"source_candidate_review_report_path does not exist: {source_value}")
        return {}
    try:
        candidate_review = load_json(source_path)
    except json.JSONDecodeError as exc:
        errors.append(f"source_candidate_review_report_path is not valid JSON: {exc}")
        return {}
    if not isinstance(candidate_review, dict):
        errors.append("source candidate review root must be an object")
        return {}
    if candidate_review.get("schema_version") != "map_component_candidate_review_report.v0.1":
        errors.append("source candidate review must be MapComponentCandidateReviewReport v0.1")
        return candidate_review

    schema = load_json(DEFAULT_CANDIDATE_SCHEMA) if DEFAULT_CANDIDATE_SCHEMA.exists() else None
    if not isinstance(schema, dict):
        schema = None
    for source_error in candidate_validator.validate_report(candidate_review, schema):
        errors.append(f"source candidate review invalid: {source_error}")
    return candidate_review


def validate_usage_policy(report: dict[str, Any], errors: list[str]) -> None:
    usage_policy = set(map(str, as_list(report.get("usage_policy"))))
    missing_policy = sorted(REQUIRED_USAGE_POLICY - usage_policy)
    if missing_policy:
        errors.append(f"usage_policy missing required policies: {', '.join(missing_policy)}")
    for index, item in enumerate(as_list(report.get("items"))):
        if not isinstance(item, dict):
            continue
        item_policy = set(map(str, as_list(item.get("usage_policy"))))
        missing_item_policy = sorted(REQUIRED_USAGE_POLICY - item_policy)
        if missing_item_policy:
            errors.append(
                f"items[{index}].usage_policy missing required policies: {', '.join(missing_item_policy)}"
            )


def validate_effects(report: dict[str, Any], errors: list[str]) -> None:
    for object_name in ("runtime_effect", "promotion_effect"):
        effect = as_obj(report.get(object_name))
        for key, value in effect.items():
            if key in FALSE_EFFECT_FIELDS and value is not False:
                errors.append(f"{object_name}.{key} must be false; this report is review-only")


def validate_items_against_candidate_review(
    report: dict[str, Any],
    candidate_review: dict[str, Any],
    errors: list[str],
) -> None:
    generated = generated_candidates(candidate_review)
    generated_by_id = {
        str(candidate.get("candidate_id") or ""): candidate
        for candidate in generated
    }
    items = [item for item in as_list(report.get("items")) if isinstance(item, dict)]
    item_ids = [str(item.get("candidate_id") or "") for item in items]

    if len(items) != len(generated):
        errors.append("items length must match generated candidate count from source candidate review")
    if set(item_ids) != set(generated_by_id):
        errors.append("items candidate_id set must match generated candidates from source candidate review")
    duplicates = sorted({candidate_id for candidate_id in item_ids if item_ids.count(candidate_id) > 1})
    for candidate_id in duplicates:
        errors.append(f"duplicate item candidate_id: {candidate_id}")

    for index, item in enumerate(items):
        candidate = generated_by_id.get(str(item.get("candidate_id") or ""))
        if not candidate:
            continue
        expected_pairs = {
            "request_id": candidate.get("request_id"),
            "component_id": candidate.get("component_id"),
            "component_role": candidate.get("component_role"),
            "style_pack_id": candidate.get("style_pack_id"),
            "node_id": candidate.get("node_id"),
            "source_candidate_local_path": candidate.get("candidate_local_path"),
            "source_candidate_sha256": candidate.get("candidate_sha256"),
            "target_size": as_obj(candidate.get("target_size")),
        }
        for key, expected in expected_pairs.items():
            actual = as_obj(item.get(key)) if key == "target_size" else item.get(key)
            if actual != expected:
                errors.append(f"items[{index}].{key} must match source candidate review")

        if item.get("candidate_kind") != "generated_candidate":
            errors.append(f"items[{index}].candidate_kind must be generated_candidate")
        if item.get("promotion_allowed_now") is not False:
            errors.append(f"items[{index}].promotion_allowed_now must be false")
        if item.get("runtime_ready") is not False:
            errors.append(f"items[{index}].runtime_ready must be false")
        if item.get("review_status") == "passed":
            validate_approval_record(
                item.get("approval_record"),
                path=f"items[{index}].approval_record",
                errors=errors,
            )
            if as_list(item.get("issues")):
                errors.append(f"items[{index}] passed visual quality item must not have issues")
            passed_file_checks = as_obj(item.get("file_checks"))
            if passed_file_checks.get("local_file_exists") is not True:
                errors.append(f"items[{index}] passed visual quality item must have a local file")
            if passed_file_checks.get("sha256_matches_declared") is not True:
                errors.append(f"items[{index}] passed visual quality item must match declared sha256")
            if passed_file_checks.get("file_type_matches_extension") is False:
                errors.append(f"items[{index}] passed visual quality item must not have file type mismatch")
        elif "approval_record" in item:
            errors.append(f"items[{index}] approval_record is only allowed for passed visual quality items")

        path_value = item.get("source_candidate_local_path")
        declared_sha = item.get("source_candidate_sha256")
        file_checks = as_obj(item.get("file_checks"))
        if isinstance(path_value, str):
            candidate_path = resolve_repo_path(path_value)
            if not candidate_path.exists():
                errors.append(f"items[{index}].source_candidate_local_path does not exist: {path_value}")
            else:
                actual_sha = sha256_file(candidate_path)
                if declared_sha != actual_sha:
                    errors.append(f"items[{index}].source_candidate_sha256 does not match local file")
                if file_checks.get("actual_sha256") != actual_sha:
                    errors.append(f"items[{index}].file_checks.actual_sha256 must match local file")
                if file_checks.get("file_size_bytes") != candidate_path.stat().st_size:
                    errors.append(f"items[{index}].file_checks.file_size_bytes must match local file size")
        if file_checks.get("declared_sha256") != declared_sha:
            errors.append(f"items[{index}].file_checks.declared_sha256 must match source_candidate_sha256")
        if file_checks.get("sha256_matches_declared") is True and file_checks.get("actual_sha256") != declared_sha:
            errors.append(f"items[{index}].file_checks.sha256_matches_declared cannot be true with mismatched sha")

        if not as_list(item.get("required_next_actions")):
            errors.append(f"items[{index}].required_next_actions must not be empty")


def validate_summary_and_status(
    report: dict[str, Any],
    candidate_review: dict[str, Any],
    errors: list[str],
) -> None:
    generated = generated_candidates(candidate_review)
    source_candidates = [
        candidate
        for candidate in as_list(candidate_review.get("candidates"))
        if isinstance(candidate, dict)
    ]
    items = [item for item in as_list(report.get("items")) if isinstance(item, dict)]
    status_counts = Counter(str(item.get("review_status")) for item in items)
    file_type_counts = Counter(str(as_obj(item.get("file_checks")).get("extension")) for item in items)
    issue_counts: Counter[str] = Counter()
    for item in items:
        issue_counts.update(str(issue) for issue in as_list(item.get("issues")))
    summary = as_obj(report.get("summary"))
    expected = {
        "source_candidate_count": len(source_candidates),
        "generated_candidate_count": len(generated),
        "checked_candidate_count": len(items),
        "passed_count": status_counts.get("passed", 0),
        "blocked_pending_quality_gates_count": status_counts.get("blocked_pending_quality_gates", 0),
        "needs_review_count": status_counts.get("needs_review", 0),
        "unsupported_decode_count": status_counts.get("needs_review_unsupported_decode", 0),
    }
    for key, value in expected.items():
        if summary.get(key) != value:
            errors.append(f"summary.{key} must be {value}")
    if as_obj(summary.get("status_counts")) != dict(sorted(status_counts.items())):
        errors.append("summary.status_counts must match item review statuses")
    if as_obj(summary.get("file_type_counts")) != dict(sorted(file_type_counts.items())):
        errors.append("summary.file_type_counts must match checked item file types")
    if as_obj(summary.get("issue_counts")) != dict(sorted(issue_counts.items())):
        errors.append("summary.issue_counts must match item issues")

    if not generated:
        expected_status = "awaiting_generated_candidates"
    elif expected["blocked_pending_quality_gates_count"]:
        expected_status = "blocked_pending_quality_gates"
    elif expected["passed_count"] == len(items):
        expected_status = "passed"
    else:
        expected_status = "needs_review"
    if report.get("status") != expected_status:
        errors.append(f"status must be {expected_status!r} based on generated candidate checks")


def validate_report(report: dict[str, Any], schema: dict[str, Any] | None = None) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_with_jsonschema(report, schema))
    scan_forbidden_key_fragments(report, "", errors)
    scan_external_urls(report, "", errors)

    if report.get("schema_version") != "map_component_visual_quality_report.v0.1":
        errors.append("schema_version must be 'map_component_visual_quality_report.v0.1'")

    validate_usage_policy(report, errors)
    validate_effects(report, errors)
    candidate_review = load_and_validate_candidate_review(report, errors)
    validate_items_against_candidate_review(report, candidate_review, errors)
    validate_summary_and_status(report, candidate_review, errors)
    return list(dict.fromkeys(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate MapComponentVisualQualityReport v0.1.")
    parser.add_argument("report", help="Report JSON path.")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    args = parser.parse_args()

    report_path = Path(args.report)
    schema_path = Path(args.schema)
    try:
        report = load_json(report_path)
    except FileNotFoundError:
        print("INVALID MapComponentVisualQualityReport")
        print(f"- report file not found: {report_path}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID MapComponentVisualQualityReport")
        print(f"- report is not valid JSON: {exc}")
        return 1
    if not isinstance(report, dict):
        print("INVALID MapComponentVisualQualityReport")
        print("- report root must be an object")
        return 1

    schema = load_json(schema_path) if schema_path.exists() else None
    if not isinstance(schema, dict):
        schema = None
    errors = validate_report(report, schema)
    if errors:
        print("INVALID MapComponentVisualQualityReport")
        for error in errors:
            print(f"- {error}")
        return 1

    summary = as_obj(report.get("summary"))
    print(f"OK: {report_path}")
    print(f"- status: {report.get('status')}")
    print(f"- generated_candidate_count: {summary.get('generated_candidate_count')}")
    print(f"- checked_candidate_count: {summary.get('checked_candidate_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
