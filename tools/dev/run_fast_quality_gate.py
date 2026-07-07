#!/usr/bin/env python3
"""Run a fast offline quality gate for day-to-day development.

This command intentionally avoids browser automation, provider calls, .env reads,
database writes, and runtime activation. It delegates to existing validators so
small changes can get a quick signal before the heavier demo evidence export.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.dev.command_runner import now_iso, run_command


DEFAULT_OUTPUT = Path("/tmp/ai_td_fast_quality_gate_report.v0.1.json")
DEFAULT_GENERATED_AT = "2026-07-07T00:00:00+00:00"
OUTPUT_TAIL_LIMIT = 1200


def default_commands(generated_at: str) -> list[dict[str, Any]]:
    readiness_tmp = "/tmp/ai_td_fast_gate_mvp_demo_readiness_report.json"
    battle_visual_tmp = "/tmp/ai_td_fast_gate_battle_visual_contract_report.json"
    pycache_prefix = "/tmp/ai_td_pycache_fast_quality_gate"
    return [
        {
            "name": "python_compile_core_tools",
            "timeout_seconds": 20,
            "command": [
                sys.executable,
                "-m",
                "py_compile",
                "tools/demo/build_mvp_demo_readiness_report.py",
                "tools/demo/validate_mvp_demo_readiness_report.py",
                "tools/demo/export_evidence.py",
                "tools/frontend/validate_battle_visual_contract.py",
                "tools/frontend/validate_campaign_router_frontend_contract.py",
                "tools/frontend/validate_map_component_frontend_contract.py",
                "tools/dev/command_runner.py",
                "tools/dev/audit_worker_acceptance_profiles.py",
                "tools/dev/run_fast_quality_gate.py",
                "tools/dev/run_worker_acceptance_profile.py",
                "tools/asset_graph/build_map_template_catalog.py",
                "tools/asset_graph/validate_map_template_catalog.py",
                "tools/asset_graph/build_map_decoration_zone_policy.py",
                "tools/asset_graph/validate_map_decoration_zone_policy.py",
            ],
            "env": {"PYTHONPYCACHEPREFIX": pycache_prefix},
        },
        {
            "name": "frontend_app_syntax",
            "timeout_seconds": 20,
            "command": ["node", "--check", "frontend/app.js"],
        },
        {
            "name": "battle_visual_contract",
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
            "name": "campaign_router_frontend_contract",
            "timeout_seconds": 10,
            "command": [
                sys.executable,
                "tools/frontend/validate_campaign_router_frontend_contract.py",
            ],
        },
        {
            "name": "map_component_frontend_contract",
            "timeout_seconds": 10,
            "command": [
                sys.executable,
                "tools/frontend/validate_map_component_frontend_contract.py",
            ],
        },
        {
            "name": "map_decoration_zone_policy_validator",
            "timeout_seconds": 10,
            "command": [
                sys.executable,
                "tools/asset_graph/validate_map_decoration_zone_policy.py",
                "examples/map_decoration_zone_policies/mvp_map_decoration_zone_policy.v0.1.json",
            ],
        },
        {
            "name": "mvp_demo_readiness_build",
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
            "name": "mvp_demo_readiness_validator_repo_fixture",
            "timeout_seconds": 10,
            "command": [
                sys.executable,
                "tools/demo/validate_mvp_demo_readiness_report.py",
                "examples/review_packs/mvp_demo_readiness_report.v0.1.json",
            ],
        },
        {
            "name": "mvp_demo_readiness_validator_rebuilt_report",
            "timeout_seconds": 10,
            "command": [
                sys.executable,
                "tools/demo/validate_mvp_demo_readiness_report.py",
                readiness_tmp,
            ],
        },
    ]


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


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
    results: list[dict[str, Any]] = []
    started_at = now_iso()
    for item in commands:
        result = run_command(
            str(item["name"]),
            list(item["command"]),
            root=ROOT,
            timeout_seconds=int(item["timeout_seconds"]),
            output_tail_limit=OUTPUT_TAIL_LIMIT,
            env=item.get("env") if isinstance(item.get("env"), dict) else None,
            include_timestamps=False,
        )
        results.append(result)
        status_icon = "OK" if result["status"] == "passed" else "FAIL"
        print(f"{status_icon} {result['name']} ({result['elapsed_seconds']}s)")
        if args.fail_fast and result["status"] != "passed":
            break

    failed = [item for item in results if item["status"] != "passed"]
    report = {
        "schema_version": "fast_quality_gate_report.v0.1",
        "report_id": "fast_quality_gate_report_v0_1",
        "generated_at": now_iso(),
        "started_at": started_at,
        "status": "passed" if not failed else "failed",
        "summary": {
            "command_count": len(results),
            "configured_command_count": len(commands),
            "passed_count": len(results) - len(failed),
            "failed_count": len(failed),
            "fail_fast": bool(args.fail_fast),
            "provider_call_count": 0,
            "reads_env_file": False,
            "world_mutation_count": 0,
            "runtime_activation_allowed": False,
        },
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
    if failed:
        for item in failed:
            print(f"failed: {item['name']}", file=sys.stderr)
            if item.get("stderr_tail"):
                print(item["stderr_tail"], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
