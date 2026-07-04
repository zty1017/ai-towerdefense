#!/usr/bin/env python3
"""Validate MapComponentPromotionGateReport v0.1."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MEDIA_DIR = Path(__file__).resolve().parent
if str(MEDIA_DIR) not in sys.path:
    sys.path.insert(0, str(MEDIA_DIR))

import validate_map_component_candidate_review_report as candidate_validator  # noqa: E402
import validate_map_component_visual_quality_report as visual_quality_validator  # noqa: E402


DEFAULT_SCHEMA = ROOT / "shared/schemas/map_component_promotion_gate_report.v0.1.schema.json"
DEFAULT_CANDIDATE_SCHEMA = ROOT / "shared/schemas/map_component_candidate_review_report.v0.1.schema.json"
DEFAULT_VISUAL_QUALITY_SCHEMA = ROOT / "shared/schemas/map_component_visual_quality_report.v0.1.schema.json"
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
    "baseline_preserved_until_generated_candidate_passes",
    "no_frontend_default_consumption",
    "no_manifest_or_style_pack_or_render_plan_mutation",
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


def resolve_repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


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


def load_and_validate_visual_quality_report(report: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    source_value = report.get("source_visual_quality_report_path")
    if not isinstance(source_value, str) or not source_value.strip():
        errors.append("source_visual_quality_report_path must be a non-empty string")
        return {}
    source_path = resolve_repo_path(source_value)
    if not source_path.exists():
        errors.append(f"source_visual_quality_report_path does not exist: {source_value}")
        return {}
    try:
        visual_report = load_json(source_path)
    except json.JSONDecodeError as exc:
        errors.append(f"source_visual_quality_report_path is not valid JSON: {exc}")
        return {}
    if not isinstance(visual_report, dict):
        errors.append("source visual quality report root must be an object")
        return {}
    if visual_report.get("schema_version") != "map_component_visual_quality_report.v0.1":
        errors.append("source visual quality report must be MapComponentVisualQualityReport v0.1")
        return visual_report

    schema = load_json(DEFAULT_VISUAL_QUALITY_SCHEMA) if DEFAULT_VISUAL_QUALITY_SCHEMA.exists() else None
    if not isinstance(schema, dict):
        schema = None
    for source_error in visual_quality_validator.validate_report(visual_report, schema):
        errors.append(f"source visual quality report invalid: {source_error}")
    return visual_report


def visual_items_by_candidate_id(visual_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("candidate_id") or ""): item
        for item in as_list(visual_report.get("items"))
        if isinstance(item, dict)
    }


def validate_decisions_against_sources(
    report: dict[str, Any],
    candidate_review: dict[str, Any],
    visual_report: dict[str, Any],
    errors: list[str],
) -> None:
    if visual_report.get("source_candidate_review_report_path") != report.get("source_candidate_review_report_path"):
        errors.append(
            "source_visual_quality_report_path must reference a report whose "
            "source_candidate_review_report_path matches promotion source_candidate_review_report_path"
        )

    candidates = [
        candidate
        for candidate in as_list(candidate_review.get("candidates"))
        if isinstance(candidate, dict)
    ]
    candidates_by_id = {
        str(candidate.get("candidate_id") or ""): candidate
        for candidate in candidates
    }
    visual_items = visual_items_by_candidate_id(visual_report)
    decisions = [item for item in as_list(report.get("decisions")) if isinstance(item, dict)]
    decision_ids = [str(decision.get("candidate_id") or "") for decision in decisions]
    if set(decision_ids) != set(candidates_by_id):
        errors.append("decisions candidate_id set must match source candidate review candidates")
    duplicate_ids = sorted({candidate_id for candidate_id in decision_ids if decision_ids.count(candidate_id) > 1})
    for candidate_id in duplicate_ids:
        errors.append(f"duplicate decision candidate_id: {candidate_id}")

    for index, decision in enumerate(decisions):
        candidate_id = str(decision.get("candidate_id") or "")
        candidate = candidates_by_id.get(candidate_id)
        if not candidate:
            continue
        expected_pairs = {
            "component_id": candidate.get("component_id"),
            "candidate_kind": candidate.get("candidate_kind"),
        }
        for key, expected in expected_pairs.items():
            if decision.get(key) != expected:
                errors.append(f"decisions[{index}].{key} must match source candidate review")

        candidate_kind = candidate.get("candidate_kind")
        visual_required = candidate_kind == "generated_candidate"
        if decision.get("visual_quality_status") != visual_report.get("status"):
            errors.append(f"decisions[{index}].visual_quality_status must match source visual quality status")
        if decision.get("visual_quality_required") is not visual_required:
            errors.append(f"decisions[{index}].visual_quality_required must reflect candidate kind")

        visual_item = visual_items.get(candidate_id) if visual_required else None
        if not visual_required:
            if decision.get("visual_quality_checked") is not False:
                errors.append(f"decisions[{index}] baseline fixture must not be visual_quality_checked")
            if decision.get("visual_quality_item_status") is not None:
                errors.append(f"decisions[{index}] baseline fixture must not have visual_quality_item_status")
            if decision.get("visual_quality_blocker") is not None:
                errors.append(f"decisions[{index}] baseline fixture must not have visual_quality_blocker")
            continue

        if not visual_item:
            errors.append(f"decisions[{index}] generated candidate must have a matching visual quality item")
            if decision.get("visual_quality_checked") is not False:
                errors.append(f"decisions[{index}].visual_quality_checked must be false without a visual item")
            if decision.get("visual_quality_item_status") is not None:
                errors.append(f"decisions[{index}].visual_quality_item_status must be null without a visual item")
        else:
            if decision.get("visual_quality_checked") is not True:
                errors.append(f"decisions[{index}].visual_quality_checked must be true for generated candidate item")
            if decision.get("visual_quality_item_status") != visual_item.get("review_status"):
                errors.append(f"decisions[{index}].visual_quality_item_status must match visual quality item")
            if visual_item.get("runtime_ready") is not False:
                errors.append(f"visual quality item for decisions[{index}] must keep runtime_ready false")
            if visual_item.get("review_status") in {
                "blocked_pending_quality_gates",
                "needs_review_unsupported_decode",
            } and not decision.get("visual_quality_blocker"):
                errors.append(f"decisions[{index}].visual_quality_blocker must explain blocked visual quality item")

        candidate_allowed = (
            candidate.get("review_status") == "passed"
            and candidate.get("promotion_recommendation") == "eligible_for_promotion"
            and candidate.get("promotion_allowed_now") is True
        )
        visual_status = visual_item.get("review_status") if visual_item else None
        visual_complete = visual_status == "passed"
        expected_allowed = candidate_allowed and visual_complete
        if decision.get("promotion_allowed") is not expected_allowed:
            errors.append(
                f"decisions[{index}].promotion_allowed must require both candidate review and visual quality completion"
            )
        if expected_allowed and decision.get("decision") != "allowed":
            errors.append(f"decisions[{index}] allowed candidate must use decision=allowed")
        if not expected_allowed and decision.get("decision") == "allowed":
            errors.append(f"decisions[{index}] cannot use decision=allowed while required gates are incomplete")


def validate_report(report: dict[str, Any], schema: dict[str, Any] | None = None) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_with_jsonschema(report, schema))
    scan_forbidden_key_fragments(report, "", errors)
    scan_external_urls(report, "", errors)

    if report.get("schema_version") != "map_component_promotion_gate_report.v0.1":
        errors.append("schema_version must be 'map_component_promotion_gate_report.v0.1'")

    usage_policy = set(map(str, as_list(report.get("usage_policy"))))
    missing_policy = sorted(REQUIRED_USAGE_POLICY - usage_policy)
    if missing_policy:
        errors.append(f"usage_policy missing required policies: {', '.join(missing_policy)}")

    runtime_effect = as_obj(report.get("runtime_effect"))
    for key, value in runtime_effect.items():
        if value is not False:
            errors.append(f"runtime_effect.{key} must be false; this gate is report-only")

    candidate_review = load_and_validate_candidate_review(report, errors)
    visual_report = load_and_validate_visual_quality_report(report, errors)
    validate_decisions_against_sources(report, candidate_review, visual_report, errors)

    decisions = [item for item in as_list(report.get("decisions")) if isinstance(item, dict)]
    decision_counts = Counter(str(decision.get("decision")) for decision in decisions)
    allowed_count = len([decision for decision in decisions if decision.get("promotion_allowed") is True])
    blocked_count = len(decisions) - allowed_count
    baseline_preserved_count = len(
        [decision for decision in decisions if decision.get("baseline_preserved") is True]
    )
    generated_count = len(
        [decision for decision in decisions if decision.get("candidate_kind") == "generated_candidate"]
    )

    for index, decision in enumerate(decisions):
        allowed = decision.get("promotion_allowed") is True
        if decision.get("candidate_kind") == "baseline_fixture_candidate" and allowed:
            errors.append(f"decisions[{index}] baseline fixture cannot be promotion_allowed")
        if allowed and decision.get("decision") != "allowed":
            errors.append(f"decisions[{index}] promotion_allowed requires decision=allowed")
        if not allowed and decision.get("baseline_preserved") is not True:
            errors.append(f"decisions[{index}] blocked decisions must preserve baseline")
        if allowed and decision.get("baseline_preserved") is not False:
            errors.append(f"decisions[{index}] allowed decisions must not preserve baseline")
        if not as_list(decision.get("required_before_future_promotion")):
            errors.append(f"decisions[{index}].required_before_future_promotion must not be empty")
        if decision.get("visual_quality_required") is True and "visual quality" not in str(
            decision.get("reason") or ""
        ).lower():
            errors.append(f"decisions[{index}].reason must mention visual quality when it is required")

    summary = as_obj(report.get("summary"))
    expected = {
        "candidate_count": len(decisions),
        "generated_candidate_count": generated_count,
        "promotion_allowed_count": allowed_count,
        "promotion_blocked_count": blocked_count,
        "baseline_preserved_count": baseline_preserved_count,
    }
    for key, value in expected.items():
        if summary.get(key) != value:
            errors.append(f"summary.{key} must be {value}")
    if as_obj(summary.get("decision_counts")) != dict(sorted(decision_counts.items())):
        errors.append("summary.decision_counts must match decisions")
    if summary.get("visual_quality_report_status") != visual_report.get("status"):
        errors.append("summary.visual_quality_report_status must match source visual quality report status")

    expected_status = "blocked" if blocked_count else "passed"
    if report.get("status") != expected_status:
        errors.append(f"status must be {expected_status!r} based on promotion decisions")
    if blocked_count and not as_list(report.get("blocked_reasons")):
        errors.append("blocked reports must include blocked_reasons")
    return list(dict.fromkeys(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate MapComponentPromotionGateReport v0.1.")
    parser.add_argument("report", help="Report JSON path.")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    args = parser.parse_args()

    report_path = Path(args.report)
    schema_path = Path(args.schema)
    try:
        report = load_json(report_path)
    except FileNotFoundError:
        print("INVALID MapComponentPromotionGateReport")
        print(f"- report file not found: {report_path}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID MapComponentPromotionGateReport")
        print(f"- report is not valid JSON: {exc}")
        return 1
    if not isinstance(report, dict):
        print("INVALID MapComponentPromotionGateReport")
        print("- report root must be an object")
        return 1

    schema = load_json(schema_path) if schema_path.exists() else None
    if not isinstance(schema, dict):
        schema = None
    errors = validate_report(report, schema)
    if errors:
        print("INVALID MapComponentPromotionGateReport")
        for error in errors:
            print(f"- {error}")
        return 1

    summary = as_obj(report.get("summary"))
    print(f"OK: {report_path}")
    print(f"- status: {report.get('status')}")
    print(f"- promotion_allowed_count: {summary.get('promotion_allowed_count')}")
    print(f"- baseline_preserved_count: {summary.get('baseline_preserved_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
