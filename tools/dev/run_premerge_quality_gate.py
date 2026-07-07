#!/usr/bin/env python3
"""Run the local pre-merge quality gate.

This orchestrator intentionally reuses existing local tools instead of adding
new validation logic. The default profile stays offline and browserless:
fast gate, fast report validation, WorkerTaskPack batch dry-run, profile audit,
migration dry-run, and git diff checks. The optional full profile adds the
normal full evidence export.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.dev.command_runner import now_iso, run_command  # noqa: E402


REPORT_SCHEMA_VERSION = "premerge_quality_gate_report.v0.1"
DEFAULT_OUTPUT = Path("/tmp/ai_td_premerge_quality_gate_report.v0.1.json")
DEFAULT_GENERATED_AT = "2026-07-07T00:00:00+00:00"
OUTPUT_TAIL_LIMIT = 1800
PROFILES = {"premerge", "full"}


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def command_specs(args: argparse.Namespace) -> list[dict[str, Any]]:
    prefix = args.tmp_prefix.rstrip("/")
    full_evidence_dir = f"{prefix}_full_evidence"
    fast_gate_report = f"{prefix}_fast_quality_gate.json"
    batch_report = f"{prefix}_worker_acceptance_batch_all_dry.json"
    audit_report = f"{prefix}_worker_acceptance_profile_audit.json"
    release_gate_audit_report = f"{prefix}_release_gate_profile_audit.json"
    migration_report = f"{prefix}_worker_acceptance_profile_migration_dry.json"
    pycache_prefix = f"{prefix}_pycache"

    fast_gate_command = [
        sys.executable,
        "tools/dev/run_fast_quality_gate.py",
        "--output",
        fast_gate_report,
        "--generated-at",
        args.generated_at,
    ]
    if args.fail_fast:
        fast_gate_command.append("--fail-fast")

    specs: list[dict[str, Any]] = [
        {
            "name": "python_compile_premerge_tools",
            "timeout_seconds": 20,
            "command": [
                sys.executable,
                "-m",
                "py_compile",
                "tools/dev/run_premerge_quality_gate.py",
                "tools/dev/validate_premerge_quality_gate_report.py",
                "tools/dev/run_fast_quality_gate.py",
                "tools/dev/validate_fast_quality_gate_report.py",
                "tools/dev/run_worker_acceptance_batch.py",
                "tools/dev/validate_worker_acceptance_batch_report.py",
                "tools/dev/audit_common.py",
                "tools/dev/audit_worker_acceptance_profiles.py",
                "tools/dev/audit_release_gate_profiles.py",
                "tools/dev/migrate_worker_acceptance_profiles.py",
                "tools/dev/command_runner.py",
                "tools/dev/check_worker_acceptance_profile_env_assignments.py",
                "tools/frontend/validate_battle_interaction_contract.py",
                "tools/frontend/capture_battle_drag_interaction_smoke.py",
                "tools/frontend/validate_battle_drag_interaction_smoke_report.py",
                "tools/frontend/check_browser_smoke_environment.py",
                "tools/frontend/capture_frontend_multinode_visual_smoke.py",
                "tools/frontend/validate_frontend_multinode_visual_smoke_report.py",
                "tools/demo/run_demo_evidence_suite.py",
                "tools/demo/validate_demo_evidence_suite_report.py",
            ],
            "env": {"PYTHONPYCACHEPREFIX": pycache_prefix},
        },
        {
            "name": "fast_quality_gate",
            "timeout_seconds": 90,
            "command": fast_gate_command,
        },
        {
            "name": "fast_quality_gate_report_validator",
            "timeout_seconds": 20,
            "command": [
                sys.executable,
                "tools/dev/validate_fast_quality_gate_report.py",
                fast_gate_report,
                "--expect-status",
                "passed",
                "--expect-failed-count",
                "0",
                "--require-worker-env-smoke",
                "--require-release-gate-audit",
                "--require-complete-command-order",
            ],
        },
        {
            "name": "worker_acceptance_batch_all_dry_run",
            "timeout_seconds": 60,
            "command": [
                sys.executable,
                "tools/dev/run_worker_acceptance_batch.py",
                "--all",
                "--profile",
                "daily_fast",
                "--dry-run",
                "--output",
                batch_report,
            ],
        },
        {
            "name": "worker_acceptance_batch_report_validator",
            "timeout_seconds": 20,
            "command": [
                sys.executable,
                "tools/dev/validate_worker_acceptance_batch_report.py",
                batch_report,
                "--expect-status",
                "dry_run",
                "--expect-failed-count",
                "0",
                "--min-pack-count",
                str(args.min_pack_count),
            ],
        },
        {
            "name": "worker_acceptance_profile_audit",
            "timeout_seconds": 30,
            "command": [
                sys.executable,
                "tools/dev/audit_worker_acceptance_profiles.py",
                "--output",
                audit_report,
                "--max-samples",
                "300",
            ],
        },
        {
            "name": "release_gate_profile_audit",
            "timeout_seconds": 30,
            "command": [
                sys.executable,
                "tools/dev/audit_release_gate_profiles.py",
                "--output",
                release_gate_audit_report,
                "--max-samples",
                "100",
            ],
        },
        {
            "name": "worker_acceptance_profile_migration_dry_run",
            "timeout_seconds": 30,
            "command": [
                sys.executable,
                "tools/dev/migrate_worker_acceptance_profiles.py",
                "--output",
                migration_report,
            ],
        },
        {
            "name": "git_diff_check",
            "timeout_seconds": 20,
            "command": ["git", "diff", "--check"],
        },
    ]

    if args.profile == "full":
        specs.append(
            {
                "name": "demo_evidence_full_export",
                "timeout_seconds": args.full_evidence_timeout,
                "command": [
                    sys.executable,
                    "tools/demo/export_evidence.py",
                    "--output-dir",
                    full_evidence_dir,
                ],
            }
        )

    return specs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--profile", choices=sorted(PROFILES), default="premerge")
    parser.add_argument("--generated-at", default=DEFAULT_GENERATED_AT)
    parser.add_argument("--tmp-prefix", default="/tmp/ai_td_premerge_quality_gate")
    parser.add_argument("--min-pack-count", type=int, default=100)
    parser.add_argument("--full-evidence-timeout", type=int, default=300)
    parser.add_argument("--fail-fast", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.min_pack_count < 1:
        print("--min-pack-count must be >= 1", file=sys.stderr)
        return 2

    specs = command_specs(args)
    started_at = now_iso()
    results: list[dict[str, Any]] = []
    for spec in specs:
        result = run_command(
            str(spec["name"]),
            list(spec["command"]),
            root=ROOT,
            timeout_seconds=int(spec["timeout_seconds"]),
            output_tail_limit=OUTPUT_TAIL_LIMIT,
            env=spec.get("env") if isinstance(spec.get("env"), dict) else None,
        )
        results.append(result)
        status_icon = "OK" if result["status"] == "passed" else "FAIL"
        print(f"{status_icon} {result['name']} ({result['elapsed_seconds']}s)")
        if args.fail_fast and result["status"] != "passed":
            break

    failed = [item for item in results if item.get("status") != "passed"]
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "report_id": "premerge_quality_gate_report_v0_1",
        "generated_at": now_iso(),
        "started_at": started_at,
        "status": "passed" if not failed else "failed",
        "profile": args.profile,
        "summary": {
            "configured_command_count": len(specs),
            "executed_command_count": len(results),
            "passed_count": len(results) - len(failed),
            "failed_count": len(failed),
            "fail_fast": bool(args.fail_fast),
            "full_evidence_included": args.profile == "full",
            "provider_call_count": 0,
            "reads_env_file": False,
            "world_mutation_count": 0,
            "runtime_activation_allowed": False,
        },
        "results": results,
        "boundary": {
            "no_provider_calls": True,
            "no_env_file_reads": True,
            "no_world_state_writes": True,
            "no_runtime_activation": True,
            "default_profile_no_browser_automation": args.profile == "premerge",
            "does_not_replace_demo_evidence_suite": True,
        },
    }
    write_json(args.output, report)
    print(f"premerge quality gate report: {args.output}")
    if failed:
        for item in failed:
            print(f"failed: {item['name']}", file=sys.stderr)
            if item.get("stderr_tail"):
                print(item["stderr_tail"], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
