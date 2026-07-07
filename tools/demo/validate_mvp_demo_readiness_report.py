#!/usr/bin/env python3
"""Validate an MVP demo readiness report.

This validator is intentionally independent from the readiness report builder:
it recomputes gate counts, safety invariants, source counts, and overall
status from the report JSON instead of trusting the builder output.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from report_io import load_json_object


ROOT = Path(__file__).resolve().parents[2]

EXPECTED_SCHEMA_VERSION = "mvp_demo_readiness_report.v0.1"
EXPECTED_REPORT_ID = "mvp_demo_readiness_report_v0_1"
EXPECTED_GATE_IDS = [
    "primary_api_flow",
    "map_v02_preview_api",
    "map_runtime_v02_opt_in_contract",
    "map_runtime_activation_contract",
    "map_runtime_v02_semantic_geometry",
    "core_artifact_alignment",
    "map_visual_runtime_safety",
    "battle_visual_contract",
    "runtime_sprite_geometry",
    "runtime_loop_continuity",
    "generation_scheduler_review_only",
    "provider_video_boundary",
    "negative_map_candidates_isolated",
    "frontend_flow_visual_smoke_harness",
]

ALLOWED_OVERALL_STATUSES = {
    "ready_for_mvp_demo",
    "ready_for_mvp_demo_with_known_limitations",
    "not_ready_for_mvp_demo",
}
ALLOWED_GATE_STATUSES = {
    "passed",
    "passed_with_warnings",
    "blocked_as_expected",
    "not_ready",
}
NON_BLOCKING_GATE_STATUSES = {
    "passed",
    "passed_with_warnings",
    "blocked_as_expected",
}
FORBIDDEN_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "secret",
    "password",
    "auth_token",
    "access_token",
    "raw_prompt",
    "full_trace",
    "raw_json",
    "unreviewed_content",
)


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def require(condition: bool, errors: list[str], message: str) -> None:
    if not condition:
        errors.append(message)


def validate_no_forbidden_keys(value: Any, errors: list[str], path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key).lower()
            if any(fragment in key_text for fragment in FORBIDDEN_KEY_FRAGMENTS):
                errors.append(f"{path}.{key}: forbidden sensitive key")
            validate_no_forbidden_keys(child, errors, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            validate_no_forbidden_keys(child, errors, f"{path}[{index}]")


def validate_generated_at(value: Any, errors: list[str]) -> None:
    require(
        isinstance(value, str) and bool(value.strip()),
        errors,
        "generated_at must be a string",
    )
    if not isinstance(value, str):
        return
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append("generated_at must be ISO-8601 compatible")


def validate_ref(ref: Any, errors: list[str], path: str) -> None:
    require(isinstance(ref, dict), errors, f"{path} must be an object")
    if not isinstance(ref, dict):
        return
    ref_path = ref.get("path")
    exists = ref.get("exists")
    require(
        isinstance(ref_path, str) and bool(ref_path.strip()),
        errors,
        f"{path}.path must be a nonempty string",
    )
    require(isinstance(exists, bool), errors, f"{path}.exists must be boolean")
    if isinstance(ref_path, str) and isinstance(exists, bool):
        actual_exists = (ROOT / ref_path).exists()
        require(
            actual_exists == exists,
            errors,
            f"{path}.exists={exists!r} does not match filesystem existence for {ref_path}",
        )


def validate_gate(gate: Any, errors: list[str], index: int) -> dict[str, Any] | None:
    path = f"gates[{index}]"
    require(isinstance(gate, dict), errors, f"{path} must be an object")
    if not isinstance(gate, dict):
        return None

    gate_id = gate.get("gate_id")
    status = gate.get("status")
    required = gate.get("required_for_mvp_demo")
    metrics = gate.get("metrics")
    evidence_refs = gate.get("evidence_refs")

    require(
        isinstance(gate_id, str) and bool(gate_id.strip()),
        errors,
        f"{path}.gate_id must be nonempty",
    )
    require(
        isinstance(gate.get("title"), str) and bool(gate.get("title", "").strip()),
        errors,
        f"{path}.title must be nonempty",
    )
    require(status in ALLOWED_GATE_STATUSES, errors, f"{path}.status is not allowed: {status!r}")
    require(isinstance(required, bool), errors, f"{path}.required_for_mvp_demo must be boolean")
    require(
        isinstance(gate.get("summary"), str) and bool(gate.get("summary", "").strip()),
        errors,
        f"{path}.summary must be nonempty",
    )
    require(isinstance(metrics, dict), errors, f"{path}.metrics must be an object")
    require(
        isinstance(evidence_refs, list) and len(evidence_refs) > 0,
        errors,
        f"{path}.evidence_refs must be a nonempty list",
    )
    for ref_index, ref in enumerate(as_list(evidence_refs)):
        validate_ref(ref, errors, f"{path}.evidence_refs[{ref_index}]")

    return gate


def expected_overall_status(
    blocking_count: int,
    warning_count: int,
    expected_block_count: int,
) -> str:
    if blocking_count > 0:
        return "not_ready_for_mvp_demo"
    if warning_count > 0 or expected_block_count > 0:
        return "ready_for_mvp_demo_with_known_limitations"
    return "ready_for_mvp_demo"


def validate_summary(
    report: dict[str, Any],
    gates: list[dict[str, Any]],
    errors: list[str],
) -> None:
    summary = as_obj(report.get("summary"))
    require(bool(summary), errors, "summary must be an object")

    required_gates = [gate for gate in gates if gate.get("required_for_mvp_demo") is True]
    blocking_gates = [
        gate
        for gate in required_gates
        if gate.get("status") not in NON_BLOCKING_GATE_STATUSES
    ]
    warning_gates = [
        gate for gate in gates if gate.get("status") == "passed_with_warnings"
    ]
    expected_blocks = [
        gate for gate in gates if gate.get("status") == "blocked_as_expected"
    ]
    source_files = as_list(report.get("source_files"))

    expected_counts = {
        "required_gate_count": len(required_gates),
        "required_gate_passed_or_expected_count": len(required_gates)
        - len(blocking_gates),
        "blocking_gate_count": len(blocking_gates),
        "warning_gate_count": len(warning_gates),
        "expected_block_count": len(expected_blocks),
        "evidence_source_count": len(source_files),
        "provider_call_count_by_report": 0,
        "world_mutation_count_by_report": 0,
        "runtime_mutation_count_by_report": 0,
    }
    for key, expected in expected_counts.items():
        require(
            summary.get(key) == expected,
            errors,
            f"summary.{key} must be {expected!r}, got {summary.get(key)!r}",
        )

    expected_status = expected_overall_status(
        len(blocking_gates),
        len(warning_gates),
        len(expected_blocks),
    )
    require(
        report.get("overall_status") == expected_status,
        errors,
        f"overall_status must be {expected_status!r} from gate counts, got {report.get('overall_status')!r}",
    )


def validate_safety(report: dict[str, Any], errors: list[str]) -> None:
    safety = as_obj(report.get("safety_summary"))
    require(bool(safety), errors, "safety_summary must be an object")
    expected = {
        "reads_env_file": False,
        "provider_call_count": 0,
        "stores_prompt_body": False,
        "stores_provider_body": False,
        "stores_sensitive_value": False,
        "world_mutation_count_by_report": 0,
        "runtime_mutation_count_by_report": 0,
        "runtime_activation_allowed": False,
    }
    for key, expected_value in expected.items():
        require(
            safety.get(key) == expected_value,
            errors,
            f"safety_summary.{key} must be {expected_value!r}, got {safety.get(key)!r}",
        )


def validate_named_text_object(
    value: Any,
    errors: list[str],
    field: str,
    required_keys: list[str],
) -> None:
    obj = as_obj(value)
    require(bool(obj), errors, f"{field} must be an object")
    for key in required_keys:
        require(
            isinstance(obj.get(key), str) and bool(obj.get(key, "").strip()),
            errors,
            f"{field}.{key} must be a nonempty string",
        )


def validate_known_limitations(report: dict[str, Any], errors: list[str]) -> None:
    limitations = as_list(report.get("known_limitations"))
    require(len(limitations) > 0, errors, "known_limitations must be nonempty")
    seen: set[str] = set()
    for index, item in enumerate(limitations):
        path = f"known_limitations[{index}]"
        require(isinstance(item, dict), errors, f"{path} must be an object")
        if not isinstance(item, dict):
            continue
        limitation_id = item.get("limitation_id")
        require(
            isinstance(limitation_id, str) and bool(limitation_id.strip()),
            errors,
            f"{path}.limitation_id must be nonempty",
        )
        if isinstance(limitation_id, str):
            require(
                limitation_id not in seen,
                errors,
                f"{path}.limitation_id is duplicated: {limitation_id}",
            )
            seen.add(limitation_id)
        require(
            item.get("severity") in {"low", "medium", "high"},
            errors,
            f"{path}.severity must be low/medium/high",
        )
        require(
            isinstance(item.get("summary"), str) and bool(item.get("summary", "").strip()),
            errors,
            f"{path}.summary must be nonempty",
        )
        refs = as_list(item.get("evidence_refs"))
        require(len(refs) > 0, errors, f"{path}.evidence_refs must be nonempty")
        for ref_index, ref in enumerate(refs):
            validate_ref(ref, errors, f"{path}.evidence_refs[{ref_index}]")


def validate_report(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    validate_no_forbidden_keys(report, errors)
    require(report.get("schema_version") == EXPECTED_SCHEMA_VERSION, errors, "schema_version mismatch")
    require(report.get("report_id") == EXPECTED_REPORT_ID, errors, "report_id mismatch")
    require(report.get("overall_status") in ALLOWED_OVERALL_STATUSES, errors, "overall_status is not allowed")
    validate_generated_at(report.get("generated_at"), errors)

    validate_named_text_object(
        report.get("demo_claim"),
        errors,
        "demo_claim",
        ["player_experience", "compiler_evidence", "boundary"],
    )

    gates_raw = as_list(report.get("gates"))
    require(
        len(gates_raw) == len(EXPECTED_GATE_IDS),
        errors,
        f"gates must contain {len(EXPECTED_GATE_IDS)} items",
    )
    gates: list[dict[str, Any]] = []
    for index, gate_raw in enumerate(gates_raw):
        gate = validate_gate(gate_raw, errors, index)
        if gate is not None:
            gates.append(gate)

    gate_ids = [str(gate.get("gate_id")) for gate in gates]
    require(
        gate_ids == EXPECTED_GATE_IDS,
        errors,
        f"gate ids must match expected MVP order: {gate_ids!r}",
    )
    require(len(set(gate_ids)) == len(gate_ids), errors, "gate_id values must be unique")
    validate_summary(report, gates, errors)
    validate_safety(report, errors)
    validate_known_limitations(report, errors)

    actions = as_list(report.get("recommended_next_actions"))
    require(len(actions) > 0, errors, "recommended_next_actions must be nonempty")
    for index, action in enumerate(actions):
        require(
            isinstance(action, str) and bool(action.strip()),
            errors,
            f"recommended_next_actions[{index}] must be a nonempty string",
        )

    source_files = as_list(report.get("source_files"))
    require(len(source_files) > 0, errors, "source_files must be nonempty")
    for index, ref in enumerate(source_files):
        validate_ref(ref, errors, f"source_files[{index}]")

    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="MVP demo readiness report JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = load_json_object(args.report, label=f"{args.report}: report")
    except ValueError as exc:
        print(f"ERROR {args.report}: invalid JSON: {exc}", file=sys.stderr)
        return 1

    errors = validate_report(report)
    if errors:
        for error in errors:
            print(f"ERROR {error}", file=sys.stderr)
        return 1

    summary = as_obj(report.get("summary"))
    print("OK MvpDemoReadinessReport")
    print(f"- overall_status: {report.get('overall_status')}")
    print(f"- gates: {len(as_list(report.get('gates')))}")
    print(
        "- required: "
        f"{summary.get('required_gate_passed_or_expected_count')}/"
        f"{summary.get('required_gate_count')}"
    )
    print(f"- warnings: {summary.get('warning_gate_count')}")
    print(f"- expected_blocks: {summary.get('expected_block_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
