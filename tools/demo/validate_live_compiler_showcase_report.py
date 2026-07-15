#!/usr/bin/env python3
"""Validate redacted live compiler showcase reports."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEV_TOOLS = ROOT / "tools" / "dev"
if str(DEV_TOOLS) not in sys.path:
    sys.path.insert(0, str(DEV_TOOLS))

from report_io import load_json_object  # noqa: E402


EXPECTED_SCHEMA = "live_compiler_showcase_report.v0.1"
EXPECTED_CASES = {
    "chain_tower": "tower_blueprint",
    "slow_trap": "temporary_trap_sample",
    "support_field": "support_item",
}
REQUIRED_EFFECTS = {
    "chain_tower": {"damage"},
    "slow_trap": {"damage", "slow"},
    "support_field": {"damage", "slow"},
}
FORBIDDEN_KEYS = {"api_key", "secret", "provider_body", "provider_response", "session_id", "job_id"}


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def walk_keys(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [str(key) for key in value] + [
            nested_key for nested in value.values() for nested_key in walk_keys(nested)
        ]
    if isinstance(value, list):
        return [nested_key for nested in value for nested_key in walk_keys(nested)]
    return []


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def validate_report(report: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    require(report.get("schema_version") == EXPECTED_SCHEMA, "schema_version mismatch", failures)
    require(report.get("status") == "passed", "report status is not passed", failures)
    require(int(report.get("case_count") or 0) == 3, "case_count must be 3", failures)
    require(int(report.get("passed_count") or 0) == 3, "passed_count must be 3", failures)
    require(report.get("failed_count") == 0, "failed_count must be 0", failures)
    forbidden = sorted(set(walk_keys(report)).intersection(FORBIDDEN_KEYS))
    require(not forbidden, f"forbidden keys leaked: {forbidden}", failures)

    cases = {str(case.get("case_id")): case for case in as_list(report.get("cases")) if isinstance(case, dict)}
    require(set(cases) == set(EXPECTED_CASES), "showcase case ids mismatch", failures)
    for case_id, expected_kind in EXPECTED_CASES.items():
        case = as_obj(cases.get(case_id))
        generation = as_obj(case.get("generation"))
        gates = as_obj(case.get("gates"))
        evidence = as_obj(case.get("evidence"))
        behavior = as_obj(case.get("behavior_abi"))
        effect_blocks = [as_obj(item) for item in as_list(behavior.get("effect_blocks"))]
        effect_kinds = {str(item.get("kind")) for item in effect_blocks}
        require(case.get("status") == "passed", f"{case_id}: status is not passed", failures)
        require(case.get("runtime_asset_kind") == expected_kind, f"{case_id}: runtime kind mismatch", failures)
        require(generation.get("mode") == "live", f"{case_id}: generation was not live", failures)
        require(generation.get("provider_call_performed") is True, f"{case_id}: provider call missing", failures)
        require(generation.get("raw_prompt_stored") is False, f"{case_id}: raw prompt stored", failures)
        require(generation.get("raw_response_stored") is False, f"{case_id}: raw response stored", failures)
        for gate in ("package_schema", "runtime_safety", "semantic", "behavior_abi", "promotion"):
            require(gates.get(gate) == "passed", f"{case_id}: {gate} gate did not pass", failures)
        require(gates.get("media") in {"passed", "degraded"}, f"{case_id}: media gate invalid", failures)
        require(int(evidence.get("trace_count") or 0) >= 2, f"{case_id}: trace evidence missing", failures)
        require(evidence.get("promotion_report_present") is True, f"{case_id}: promotion report missing", failures)
        require(evidence.get("runtime_package_present") is True, f"{case_id}: runtime package missing", failures)
        require(
            REQUIRED_EFFECTS[case_id].issubset(effect_kinds),
            f"{case_id}: required runtime effects missing",
            failures,
        )
        if case_id == "chain_tower":
            damage = next((item for item in effect_blocks if item.get("kind") == "damage"), {})
            require(int(damage.get("max_targets") or 1) >= 2, "chain_tower: chain target count missing", failures)
        require(int(case.get("runtime_mutation_count") or 0) == 1, f"{case_id}: runtime mutation count mismatch", failures)

    safety = as_obj(report.get("safety_summary"))
    require(safety.get("stores_raw_prompt") is False, "safety stores_raw_prompt must be false", failures)
    require(safety.get("stores_raw_response") is False, "safety stores_raw_response must be false", failures)
    require(int(safety.get("successful_provider_call_count") or 0) == 3, "provider call count must be 3", failures)
    require(int(safety.get("runtime_mutation_count") or 0) == 3, "runtime mutation count must be 3", failures)
    require(safety.get("world_state_mutation_count") == 0, "world mutation count must be 0", failures)
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    report = load_json_object(args.report, label=f"{args.report} root")
    failures = validate_report(report)
    if failures:
        for failure in failures:
            print(f"ERROR: {failure}")
        return 1
    print(f"live compiler showcase report passed: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
