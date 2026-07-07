#!/usr/bin/env python3
"""Run a fast offline quality gate for day-to-day development.

This command intentionally avoids browser automation, provider calls, .env reads,
database writes, and runtime activation. It delegates to existing validators so
small changes can get a quick signal before the heavier demo evidence export.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.dev.command_runner import now_iso
from tools.dev.fast_quality_gate_contract import (
    COMMAND_BATTLE_INTERACTION_CONTRACT,
    COMMAND_BATTLE_VISUAL_CONTRACT,
    COMMAND_CAMPAIGN_ROUTER_FRONTEND_CONTRACT,
    COMMAND_FRONTEND_APP_SYNTAX,
    COMMAND_MAP_COMPONENT_FRONTEND_CONTRACT,
    COMMAND_MAP_DECORATION_ZONE_POLICY_VALIDATOR,
    COMMAND_MVP_DEMO_READINESS_BUILD,
    COMMAND_MVP_DEMO_READINESS_VALIDATOR_REBUILT_REPORT,
    COMMAND_MVP_DEMO_READINESS_VALIDATOR_REPO_FIXTURE,
    COMMAND_PYTHON_COMPILE_CORE_TOOLS,
    COMMAND_RELEASE_GATE_PROFILE_AUDIT,
    COMMAND_WORKER_ACCEPTANCE_PROFILE_AUDIT,
    COMMAND_WORKER_PROFILE_ENV_ASSIGNMENT_SMOKE,
    FAST_QUALITY_GATE_REPORT_ID,
    FAST_QUALITY_GATE_REQUIRED_ZERO_FIELDS,
    FAST_QUALITY_GATE_SCHEMA_VERSION,
)
from tools.dev.quality_gate_report_helpers import (
    collect_command_failures,
    print_failed_command_details,
    report_status_from_failures,
    run_quality_gate_commands,
    summarize_command_results,
)
from tools.dev.quality_gate_compile_targets import (
    FAST_QUALITY_GATE_COMPILE_TARGETS,
    py_compile_command,
)
from tools.dev.validate_fast_quality_gate_report import (
    validate_report as validate_fast_quality_gate_report,
)
from tools.dev.report_io import write_json


DEFAULT_OUTPUT = Path("/tmp/ai_td_fast_quality_gate_report.v0.1.json")
DEFAULT_GENERATED_AT = "2026-07-07T00:00:00+00:00"
OUTPUT_TAIL_LIMIT = 1200


def default_commands(generated_at: str) -> list[dict[str, Any]]:
    readiness_tmp = "/tmp/ai_td_fast_gate_mvp_demo_readiness_report.json"
    battle_visual_tmp = "/tmp/ai_td_fast_gate_battle_visual_contract_report.json"
    battle_interaction_tmp = "/tmp/ai_td_fast_gate_battle_interaction_contract_report.json"
    worker_profile_audit_tmp = "/tmp/ai_td_fast_gate_worker_acceptance_profile_audit.json"
    release_gate_audit_tmp = "/tmp/ai_td_fast_gate_release_gate_profile_audit.json"
    worker_env_smoke_tmp = "/tmp/ai_td_fast_gate_worker_profile_env_assignment_smoke.json"
    pycache_prefix = "/tmp/ai_td_pycache_fast_quality_gate"
    return [
        {
            "name": COMMAND_PYTHON_COMPILE_CORE_TOOLS,
            "timeout_seconds": 20,
            "command": py_compile_command(sys.executable, FAST_QUALITY_GATE_COMPILE_TARGETS),
            "env": {"PYTHONPYCACHEPREFIX": pycache_prefix},
        },
        {
            "name": COMMAND_FRONTEND_APP_SYNTAX,
            "timeout_seconds": 20,
            "command": ["node", "--check", "frontend/app.js"],
        },
        {
            "name": COMMAND_BATTLE_VISUAL_CONTRACT,
            "timeout_seconds": 20,
            "command": [
                sys.executable,
                "tools/frontend/validate_battle_visual_contract.py",
                "--report-output",
                battle_visual_tmp,
                "--generated-at",
                generated_at,
            ],
        },
        {
            "name": COMMAND_BATTLE_INTERACTION_CONTRACT,
            "timeout_seconds": 20,
            "command": [
                sys.executable,
                "tools/frontend/validate_battle_interaction_contract.py",
                "--report-output",
                battle_interaction_tmp,
                "--generated-at",
                generated_at,
            ],
        },
        {
            "name": COMMAND_CAMPAIGN_ROUTER_FRONTEND_CONTRACT,
            "timeout_seconds": 10,
            "command": [
                sys.executable,
                "tools/frontend/validate_campaign_router_frontend_contract.py",
            ],
        },
        {
            "name": COMMAND_MAP_COMPONENT_FRONTEND_CONTRACT,
            "timeout_seconds": 10,
            "command": [
                sys.executable,
                "tools/frontend/validate_map_component_frontend_contract.py",
            ],
        },
        {
            "name": COMMAND_MAP_DECORATION_ZONE_POLICY_VALIDATOR,
            "timeout_seconds": 10,
            "command": [
                sys.executable,
                "tools/asset_graph/validate_map_decoration_zone_policy.py",
                "examples/map_decoration_zone_policies/mvp_map_decoration_zone_policy.v0.1.json",
            ],
        },
        {
            "name": COMMAND_WORKER_PROFILE_ENV_ASSIGNMENT_SMOKE,
            "timeout_seconds": 10,
            "command": [
                sys.executable,
                "tools/dev/check_worker_acceptance_profile_env_assignments.py",
                "--output",
                worker_env_smoke_tmp,
            ],
        },
        {
            "name": COMMAND_WORKER_ACCEPTANCE_PROFILE_AUDIT,
            "timeout_seconds": 20,
            "command": [
                sys.executable,
                "tools/dev/audit_worker_acceptance_profiles.py",
                "--output",
                worker_profile_audit_tmp,
                "--max-samples",
                "20",
            ],
        },
        {
            "name": COMMAND_RELEASE_GATE_PROFILE_AUDIT,
            "timeout_seconds": 20,
            "command": [
                sys.executable,
                "tools/dev/audit_release_gate_profiles.py",
                "--output",
                release_gate_audit_tmp,
                "--max-samples",
                "20",
            ],
        },
        {
            "name": COMMAND_MVP_DEMO_READINESS_BUILD,
            "timeout_seconds": 20,
            "command": [
                sys.executable,
                "tools/demo/build_mvp_demo_readiness_report.py",
                "--output",
                readiness_tmp,
                "--generated-at",
                generated_at,
            ],
        },
        {
            "name": COMMAND_MVP_DEMO_READINESS_VALIDATOR_REPO_FIXTURE,
            "timeout_seconds": 10,
            "command": [
                sys.executable,
                "tools/demo/validate_mvp_demo_readiness_report.py",
                "examples/review_packs/mvp_demo_readiness_report.v0.1.json",
            ],
        },
        {
            "name": COMMAND_MVP_DEMO_READINESS_VALIDATOR_REBUILT_REPORT,
            "timeout_seconds": 10,
            "command": [
                sys.executable,
                "tools/demo/validate_mvp_demo_readiness_report.py",
                readiness_tmp,
            ],
        },
    ]


def self_validate_report(report: dict[str, Any], *, fail_fast: bool) -> bool:
    failed_count = int(report.get("summary", {}).get("failed_count") or 0)
    partial_fail_fast = bool(fail_fast and failed_count > 0)
    try:
        validate_fast_quality_gate_report(
            report,
            expect_status=None,
            expect_failed_count=None,
            require_worker_env_smoke=not partial_fail_fast,
            require_worker_profile_audit=not partial_fail_fast,
            require_release_gate_audit=not partial_fail_fast,
            require_complete_command_order=not partial_fail_fast,
        )
    except Exception as exc:  # noqa: BLE001 - CLI reports concise failures.
        print(f"fast quality gate report self-validation failed: {exc}", file=sys.stderr)
        return False
    print("fast quality gate report self-validation passed")
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Write a structured fast gate report to this path.",
    )
    parser.add_argument(
        "--generated-at",
        default=DEFAULT_GENERATED_AT,
        help="Deterministic timestamp passed to generated review reports.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop after the first failing command.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    commands = default_commands(args.generated_at)
    started_at = now_iso()
    results = run_quality_gate_commands(
        commands,
        root=ROOT,
        output_tail_limit=OUTPUT_TAIL_LIMIT,
        fail_fast=bool(args.fail_fast),
        include_timestamps=False,
    )

    failed = collect_command_failures(results)
    report = {
        "schema_version": FAST_QUALITY_GATE_SCHEMA_VERSION,
        "report_id": FAST_QUALITY_GATE_REPORT_ID,
        "generated_at": now_iso(),
        "started_at": started_at,
        "status": report_status_from_failures(failed),
        "summary": summarize_command_results(
            results=results,
            configured_count=len(commands),
            fail_fast=bool(args.fail_fast),
            configured_count_field="configured_command_count",
            executed_count_field="command_count",
            extra_fields=dict(FAST_QUALITY_GATE_REQUIRED_ZERO_FIELDS),
        ),
        "results": results,
        "boundary": {
            "no_browser_automation": True,
            "no_provider_calls": True,
            "no_env_file_reads": True,
            "no_world_state_writes": True,
            "no_runtime_activation": True,
            "does_not_replace_full_demo_evidence_export": True,
        },
    }
    write_json(args.output, report)
    print(f"fast quality gate report: {args.output}")
    report_valid = self_validate_report(report, fail_fast=bool(args.fail_fast))
    if failed:
        print_failed_command_details(failed)
        return 1
    if not report_valid:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
