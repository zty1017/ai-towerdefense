#!/usr/bin/env python3
"""Derive an approved alternate MapComponent candidate review report."""

from __future__ import annotations

import argparse
import copy
import json
from collections import Counter
from pathlib import Path
from typing import Any

import validate_map_component_candidate_review_report as candidate_validator


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA = ROOT / "shared/schemas/map_component_candidate_review_report.v0.1.schema.json"
DEFAULT_APPROVAL_PLAN = ROOT / "examples/review_packs/map_component_candidate_approval_plan.v0.1.json"
APPROVAL_PLAN_VERSION = "map_component_candidate_approval_plan.v0.1"
PLAN_ROOT_KEYS = {"schema_version", "approvals", "entries"}
PLAN_ENTRY_KEYS = {
    "candidate_id",
    "approval_status",
    "approval_scope",
    "approved_at",
    "reviewer",
    "rationale",
}
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


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def rel_or_abs(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def scan_forbidden_key_fragments(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            lowered = key.lower()
            if any(fragment in lowered for fragment in FORBIDDEN_KEY_FRAGMENTS):
                errors.append(f"forbidden field '{child_path}' is not allowed in approval plan")
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


def plan_entries(plan: Any, errors: list[str]) -> list[dict[str, Any]]:
    if not isinstance(plan, dict):
        errors.append("approval plan root must be an object")
        return []

    unexpected_root_keys = sorted(set(plan) - PLAN_ROOT_KEYS)
    for key in unexpected_root_keys:
        errors.append(f"approval plan root contains unsupported field: {key}")
    if plan.get("schema_version") != APPROVAL_PLAN_VERSION:
        errors.append(f"approval plan schema_version must be {APPROVAL_PLAN_VERSION}")
    if "approvals" in plan and "entries" in plan:
        errors.append("approval plan must use only one of approvals or entries")
        return []

    entries = plan.get("approvals", plan.get("entries"))
    if not isinstance(entries, list) or not entries:
        errors.append("approval plan must contain a non-empty approvals array")
        return []

    normalized: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"approvals[{index}] must be an object")
            continue
        unexpected_entry_keys = sorted(set(entry) - PLAN_ENTRY_KEYS)
        for key in unexpected_entry_keys:
            errors.append(f"approvals[{index}] contains unsupported field: {key}")
        normalized.append(entry)
    return normalized


def select_entry(
    entries: list[dict[str, Any]],
    *,
    candidate_id: str | None,
    errors: list[str],
) -> tuple[str, dict[str, Any] | None]:
    if candidate_id is None:
        if len(entries) != 1:
            errors.append("--candidate-id is required when approval plan has multiple entries")
            return "", None
        candidate_id = str(entries[0].get("candidate_id") or "")
    if not candidate_id.strip():
        errors.append("candidate_id must be a non-empty string")
        return "", None

    matches = [entry for entry in entries if entry.get("candidate_id") == candidate_id]
    if len(matches) != 1:
        errors.append(f"approval plan must contain exactly one entry for candidate_id: {candidate_id}")
        return candidate_id, None
    return candidate_id, matches[0]


def approval_record_from_entry(entry: dict[str, Any], *, plan_path: Path) -> dict[str, Any]:
    return {
        "approval_status": entry.get("approval_status"),
        "approval_scope": as_list(entry.get("approval_scope")),
        "approved_at": entry.get("approved_at"),
        "reviewer": entry.get("reviewer"),
        "rationale": entry.get("rationale"),
        "source_approval_plan_path": rel_or_abs(plan_path),
    }


def refresh_summary_and_status(report: dict[str, Any]) -> None:
    candidates = [candidate for candidate in as_list(report.get("candidates")) if isinstance(candidate, dict)]
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
    blocked_count = len(candidates) - promotable_count
    report["status"] = "blocked_from_promotion" if blocked_count else "passed"
    report["summary"] = {
        "candidate_count": len(candidates),
        "baseline_fixture_candidate_count": kind_counts.get("baseline_fixture_candidate", 0),
        "generated_candidate_count": kind_counts.get("generated_candidate", 0),
        "promotable_count": promotable_count,
        "blocked_from_promotion_count": blocked_count,
        "no_generated_candidate_yet_count": status_counts.get("no_generated_candidate_yet", 0),
        "status_counts": dict(sorted(status_counts.items())),
        "candidate_kind_counts": dict(sorted(kind_counts.items())),
    }


def approve_candidate(
    report: dict[str, Any],
    *,
    candidate_id: str,
    approval_record: dict[str, Any],
    output_path: Path,
    created_at: str | None,
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    updated = copy.deepcopy(report)
    candidates = [candidate for candidate in as_list(updated.get("candidates")) if isinstance(candidate, dict)]
    matches = [candidate for candidate in candidates if candidate.get("candidate_id") == candidate_id]
    if len(matches) != 1:
        return updated, [f"candidate review report must contain exactly one candidate_id: {candidate_id}"]
    candidate = matches[0]
    if candidate.get("candidate_kind") != "generated_candidate":
        return updated, [f"candidate_id is not a generated_candidate: {candidate_id}"]
    if candidate.get("review_status") != "blocked_from_promotion":
        errors.append(f"candidate_id must start from review_status=blocked_from_promotion: {candidate_id}")
    if candidate.get("promotion_allowed_now") is not False:
        errors.append(f"candidate_id must start from promotion_allowed_now=false: {candidate_id}")
    if "approval_record" in candidate:
        errors.append(f"candidate_id already has approval_record: {candidate_id}")
    if errors:
        return updated, errors

    candidate["review_status"] = "passed"
    candidate["promotion_recommendation"] = "eligible_for_promotion"
    candidate["promotion_allowed_now"] = True
    candidate["approval_record"] = approval_record
    candidate["findings"] = list(
        dict.fromkeys(
            as_list(candidate.get("findings"))
            + ["Candidate review approval record permits this generated candidate to enter promotion gate evaluation."]
        )
    )
    updated["report_id"] = f"{updated.get('report_id', 'map_component_candidate_review_report')}_candidate_approved"
    if created_at:
        updated["created_at"] = created_at
    updated["validation"] = {
        "validator": "tools/media/validate_map_component_candidate_review_report.py",
        "commands": [
            f"python3 tools/media/validate_map_component_candidate_review_report.py {rel_or_abs(output_path)}"
        ],
    }
    refresh_summary_and_status(updated)
    return updated, []


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Derive an approved alternate MapComponentCandidateReviewReport v0.1."
    )
    parser.add_argument("--candidate-review-report", required=True, help="Source candidate review report JSON.")
    parser.add_argument("--approval-plan", default=str(DEFAULT_APPROVAL_PLAN))
    parser.add_argument("--candidate-id", default=None)
    parser.add_argument("--output", required=True)
    parser.add_argument("--created-at", default=None)
    args = parser.parse_args()

    report_path = resolve_path(args.candidate_review_report)
    plan_path = resolve_path(args.approval_plan)
    output_path = resolve_path(args.output)

    try:
        report = load_json(report_path)
        plan = load_json(plan_path)
    except FileNotFoundError as exc:
        print(f"ERROR: file not found: {exc.filename}")
        return 1
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON: {exc}")
        return 1
    if not isinstance(report, dict):
        print("ERROR: candidate review report root must be an object")
        return 1

    errors: list[str] = []
    scan_forbidden_key_fragments(plan, "", errors)
    scan_external_urls(plan, "", errors)
    entries = plan_entries(plan, errors)
    candidate_id, entry = select_entry(entries, candidate_id=args.candidate_id, errors=errors)
    if errors or entry is None:
        print("INVALID MapComponent candidate approval plan")
        for error in errors:
            print(f"- {error}")
        return 1

    schema = load_json(DEFAULT_SCHEMA) if DEFAULT_SCHEMA.exists() else None
    schema_obj = schema if isinstance(schema, dict) else None
    source_errors = candidate_validator.validate_report(report, schema_obj)
    if source_errors:
        print("INVALID source MapComponentCandidateReviewReport")
        for error in source_errors:
            print(f"- {error}")
        return 1

    approval_record = approval_record_from_entry(entry, plan_path=plan_path)
    record_errors: list[str] = []
    candidate_validator.validate_approval_record(
        approval_record,
        path="approval_record",
        required_scope=candidate_validator.APPROVAL_SCOPE_CANDIDATE_REVIEW,
        errors=record_errors,
    )
    if record_errors:
        print("INVALID MapComponent candidate approval record")
        for error in record_errors:
            print(f"- {error}")
        return 1

    updated, approve_errors = approve_candidate(
        report,
        candidate_id=candidate_id,
        approval_record=approval_record,
        output_path=output_path,
        created_at=args.created_at,
    )
    if approve_errors:
        print("INVALID MapComponent candidate approval")
        for error in approve_errors:
            print(f"- {error}")
        return 1

    output_errors = candidate_validator.validate_report(updated, schema_obj)
    if output_errors:
        print("INVALID approved MapComponentCandidateReviewReport")
        for error in output_errors:
            print(f"- {error}")
        return 1

    write_json(output_path, updated)
    summary = as_obj(updated.get("summary"))
    print(f"OK: wrote {output_path}")
    print(f"- status: {updated.get('status')}")
    print(f"- generated_candidate_count: {summary.get('generated_candidate_count')}")
    print(f"- promotable_count: {summary.get('promotable_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
