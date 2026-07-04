#!/usr/bin/env python3
"""Validate MapComponentCandidateReviewReport v0.1."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA = ROOT / "shared/schemas/map_component_candidate_review_report.v0.1.schema.json"
FORBIDDEN_KEY_FRAGMENTS = (
    "provider",
    "model",
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


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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

        if candidate.get("candidate_kind") == "baseline_fixture_candidate":
            if candidate.get("promotion_allowed_now") is not False:
                errors.append(f"candidates[{index}] baseline fixture cannot allow promotion")
            if candidate.get("review_status") != "no_generated_candidate_yet":
                errors.append(f"candidates[{index}] baseline fixture status must be no_generated_candidate_yet")
            if candidate.get("promotion_recommendation") != "do_not_promote":
                errors.append(f"candidates[{index}] baseline fixture recommendation must be do_not_promote")

        local_path_value = candidate.get("baseline_local_path")
        if not isinstance(local_path_value, str):
            errors.append(f"candidates[{index}].baseline_local_path must be a string")
            continue
        local_path = ROOT / local_path_value
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
