#!/usr/bin/env python3
"""Validate MapComponentPromotionGateReport v0.1."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA = ROOT / "shared/schemas/map_component_promotion_gate_report.v0.1.schema.json"
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
