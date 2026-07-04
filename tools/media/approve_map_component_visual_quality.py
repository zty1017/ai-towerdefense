#!/usr/bin/env python3
"""Derive an approved alternate MapComponent visual quality report."""

from __future__ import annotations

import argparse
import copy
import json
from collections import Counter
from pathlib import Path
from typing import Any

import validate_map_component_visual_quality_report as visual_validator


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA = ROOT / "shared/schemas/map_component_visual_quality_report.v0.1.schema.json"
DEFAULT_APPROVAL_PLAN = ROOT / "examples/review_packs/map_component_visual_quality_approval_plan.v0.1.json"
APPROVAL_PLAN_VERSION = "map_component_visual_quality_approval_plan.v0.1"
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
    items = [item for item in as_list(report.get("items")) if isinstance(item, dict)]
    status_counts = Counter(str(item.get("review_status")) for item in items)
    file_type_counts = Counter(str(as_obj(item.get("file_checks")).get("extension")) for item in items)
    issue_counts: Counter[str] = Counter()
    for item in items:
        issue_counts.update(str(issue) for issue in as_list(item.get("issues")))

    passed_count = status_counts.get("passed", 0)
    blocked_count = status_counts.get("blocked_pending_quality_gates", 0)
    if not items:
        status = "awaiting_generated_candidates"
    elif blocked_count:
        status = "blocked_pending_quality_gates"
    elif passed_count == len(items):
        status = "passed"
    else:
        status = "needs_review"

    previous_summary = as_obj(report.get("summary"))
    report["status"] = status
    report["summary"] = {
        "source_candidate_count": previous_summary.get("source_candidate_count", len(items)),
        "generated_candidate_count": previous_summary.get("generated_candidate_count", len(items)),
        "checked_candidate_count": len(items),
        "passed_count": passed_count,
        "blocked_pending_quality_gates_count": blocked_count,
        "needs_review_count": status_counts.get("needs_review", 0),
        "unsupported_decode_count": status_counts.get("needs_review_unsupported_decode", 0),
        "status_counts": dict(sorted(status_counts.items())),
        "file_type_counts": dict(sorted(file_type_counts.items())),
        "issue_counts": dict(sorted(issue_counts.items())),
    }


def validate_item_can_pass(item: dict[str, Any], *, candidate_id: str) -> list[str]:
    errors: list[str] = []
    if item.get("review_status") != "needs_review":
        errors.append(f"candidate_id must start from review_status=needs_review: {candidate_id}")
    if as_list(item.get("issues")):
        errors.append(f"candidate_id cannot pass visual quality with item issues: {candidate_id}")
    file_checks = as_obj(item.get("file_checks"))
    if file_checks.get("local_file_exists") is not True:
        errors.append(f"candidate_id cannot pass visual quality without a local file: {candidate_id}")
    if file_checks.get("sha256_matches_declared") is not True:
        errors.append(f"candidate_id cannot pass visual quality without matching sha256: {candidate_id}")
    if file_checks.get("file_type_matches_extension") is False:
        errors.append(f"candidate_id cannot pass visual quality with file type mismatch: {candidate_id}")
    if "approval_record" in item:
        errors.append(f"candidate_id already has approval_record: {candidate_id}")
    return errors


def approve_item(
    report: dict[str, Any],
    *,
    candidate_id: str,
    approval_record: dict[str, Any],
    output_path: Path,
    created_at: str | None,
) -> tuple[dict[str, Any], list[str]]:
    updated = copy.deepcopy(report)
    items = [item for item in as_list(updated.get("items")) if isinstance(item, dict)]
    matches = [item for item in items if item.get("candidate_id") == candidate_id]
    if len(matches) != 1:
        return updated, [f"visual quality report must contain exactly one candidate_id: {candidate_id}"]
    item = matches[0]
    errors = validate_item_can_pass(item, candidate_id=candidate_id)
    if errors:
        return updated, errors

    item["review_status"] = "passed"
    item["promotion_allowed_now"] = False
    item["runtime_ready"] = False
    item["approval_record"] = approval_record
    item["required_next_actions"] = [
        "run explicit MapComponentPromotionGateReport before any manifest replacement"
    ]
    updated["report_id"] = f"{updated.get('report_id', 'map_component_visual_quality_report')}_visual_approved"
    if created_at:
        updated["created_at"] = created_at
    updated["validation"] = {
        "validator": "tools/media/validate_map_component_visual_quality_report.py",
        "commands": [
            f"python3 tools/media/validate_map_component_visual_quality_report.py {rel_or_abs(output_path)}"
        ],
    }
    refresh_summary_and_status(updated)
    return updated, []


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Derive an approved alternate MapComponentVisualQualityReport v0.1."
    )
    parser.add_argument("--visual-quality-report", required=True, help="Source visual quality report JSON.")
    parser.add_argument("--approval-plan", default=str(DEFAULT_APPROVAL_PLAN))
    parser.add_argument("--candidate-id", default=None)
    parser.add_argument("--output", required=True)
    parser.add_argument("--created-at", default=None)
    args = parser.parse_args()

    report_path = resolve_path(args.visual_quality_report)
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
        print("ERROR: visual quality report root must be an object")
        return 1

    errors: list[str] = []
    scan_forbidden_key_fragments(plan, "", errors)
    scan_external_urls(plan, "", errors)
    entries = plan_entries(plan, errors)
    candidate_id, entry = select_entry(entries, candidate_id=args.candidate_id, errors=errors)
    if errors or entry is None:
        print("INVALID MapComponent visual quality approval plan")
        for error in errors:
            print(f"- {error}")
        return 1

    schema = load_json(DEFAULT_SCHEMA) if DEFAULT_SCHEMA.exists() else None
    schema_obj = schema if isinstance(schema, dict) else None
    source_errors = visual_validator.validate_report(report, schema_obj)
    if source_errors:
        print("INVALID source MapComponentVisualQualityReport")
        for error in source_errors:
            print(f"- {error}")
        return 1

    approval_record = approval_record_from_entry(entry, plan_path=plan_path)
    record_errors: list[str] = []
    visual_validator.validate_approval_record(
        approval_record,
        path="approval_record",
        errors=record_errors,
    )
    if record_errors:
        print("INVALID MapComponent visual quality approval record")
        for error in record_errors:
            print(f"- {error}")
        return 1

    updated, approve_errors = approve_item(
        report,
        candidate_id=candidate_id,
        approval_record=approval_record,
        output_path=output_path,
        created_at=args.created_at,
    )
    if approve_errors:
        print("INVALID MapComponent visual quality approval")
        for error in approve_errors:
            print(f"- {error}")
        return 1

    output_errors = visual_validator.validate_report(updated, schema_obj)
    if output_errors:
        print("INVALID approved MapComponentVisualQualityReport")
        for error in output_errors:
            print(f"- {error}")
        return 1

    write_json(output_path, updated)
    summary = as_obj(updated.get("summary"))
    print(f"OK: wrote {output_path}")
    print(f"- status: {updated.get('status')}")
    print(f"- checked_candidate_count: {summary.get('checked_candidate_count')}")
    print(f"- passed_count: {summary.get('passed_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
