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
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.dev.command_runner import now_iso  # noqa: E402
from tools.dev.premerge_quality_gate_contract import (  # noqa: E402
    COMMAND_DEMO_EVIDENCE_FULL_EXPORT,
    COMMAND_FAST_QUALITY_GATE,
    COMMAND_FAST_QUALITY_GATE_REPORT_VALIDATOR,
    COMMAND_GIT_DIFF_CHECK,
    COMMAND_PYTHON_COMPILE_PREMERGE_TOOLS,
    COMMAND_RELEASE_GATE_PROFILE_AUDIT,
    COMMAND_WORKER_ACCEPTANCE_BATCH_ALL_DRY_RUN,
    COMMAND_WORKER_ACCEPTANCE_BATCH_REPORT_VALIDATOR,
    COMMAND_WORKER_ACCEPTANCE_PROFILE_AUDIT,
    COMMAND_WORKER_ACCEPTANCE_PROFILE_MIGRATION_DRY_RUN,
    PREMERGE_QUALITY_GATE_PROFILES,
    PREMERGE_QUALITY_GATE_REPORT_ID,
    PREMERGE_QUALITY_GATE_SCHEMA_VERSION,
    PREMERGE_REQUIRED_BOUNDARY_FLAGS,
    PREMERGE_REQUIRED_ZERO_FIELDS,
    PROFILE_FULL,
    PROFILE_PREMERGE,
)
from tools.dev.quality_gate_report_helpers import (  # noqa: E402
    collect_command_failures,
    print_failed_command_details,
    report_status_from_failures,
    run_quality_gate_commands,
    summarize_command_results,
)
from tools.dev.quality_gate_compile_targets import (  # noqa: E402
    PREMERGE_QUALITY_GATE_COMPILE_TARGETS,
    py_compile_command,
)
from tools.dev.validate_premerge_quality_gate_report import (  # noqa: E402
    validate_report as validate_premerge_quality_gate_report,
)
from tools.dev.report_io import write_json  # noqa: E402


DEFAULT_OUTPUT = Path("/tmp/ai_td_premerge_quality_gate_report.v0.1.json")
DEFAULT_GENERATED_AT = "2026-07-07T00:00:00+00:00"
OUTPUT_TAIL_LIMIT = 1800


def self_validate_report(report: dict[str, Any], *, profile: str) -> bool:
    try:
        validate_premerge_quality_gate_report(
            report,
            expect_status=None,
            expect_profile=profile,
            expect_failed_count=None,
        )
    except Exception as exc:  # noqa: BLE001 - CLI reports concise failures.
        print(f"premerge quality gate report self-validation failed: {exc}", file=sys.stderr)
        return False
    print("premerge quality gate report self-validation passed")
    return True


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
            "name": COMMAND_PYTHON_COMPILE_PREMERGE_TOOLS,
            "timeout_seconds": 20,
            "command": py_compile_command(sys.executable, PREMERGE_QUALITY_GATE_COMPILE_TARGETS),
            "env": {"PYTHONPYCACHEPREFIX": pycache_prefix},
        },
        {
            "name": COMMAND_FAST_QUALITY_GATE,
            "timeout_seconds": 90,
            "command": fast_gate_command,
        },
        {
            "name": COMMAND_FAST_QUALITY_GATE_REPORT_VALIDATOR,
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
                "--require-worker-profile-audit",
                "--require-release-gate-audit",
                "--require-complete-command-order",
            ],
        },
        {
            "name": COMMAND_WORKER_ACCEPTANCE_BATCH_ALL_DRY_RUN,
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
            "name": COMMAND_WORKER_ACCEPTANCE_BATCH_REPORT_VALIDATOR,
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
            "name": COMMAND_WORKER_ACCEPTANCE_PROFILE_AUDIT,
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
            "name": COMMAND_RELEASE_GATE_PROFILE_AUDIT,
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
            "name": COMMAND_WORKER_ACCEPTANCE_PROFILE_MIGRATION_DRY_RUN,
            "timeout_seconds": 30,
            "command": [
                sys.executable,
                "tools/dev/migrate_worker_acceptance_profiles.py",
                "--output",
                migration_report,
            ],
        },
        {
            "name": COMMAND_GIT_DIFF_CHECK,
            "timeout_seconds": 20,
            "command": ["git", "diff", "--check"],
        },
    ]

    if args.profile == PROFILE_FULL:
        specs.append(
            {
                "name": COMMAND_DEMO_EVIDENCE_FULL_EXPORT,
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
    parser.add_argument(
        "--profile",
        choices=sorted(PREMERGE_QUALITY_GATE_PROFILES),
        default=PROFILE_PREMERGE,
    )
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
    results = run_quality_gate_commands(
        specs,
        root=ROOT,
        output_tail_limit=OUTPUT_TAIL_LIMIT,
        fail_fast=bool(args.fail_fast),
    )

    failed = collect_command_failures(results)
    zero_summary_fields = {field: expected for field, expected in PREMERGE_REQUIRED_ZERO_FIELDS}
    report = {
        "schema_version": PREMERGE_QUALITY_GATE_SCHEMA_VERSION,
        "report_id": PREMERGE_QUALITY_GATE_REPORT_ID,
        "generated_at": now_iso(),
        "started_at": started_at,
        "status": report_status_from_failures(failed),
        "profile": args.profile,
        "summary": summarize_command_results(
            results=results,
            configured_count=len(specs),
            fail_fast=bool(args.fail_fast),
            configured_count_field="configured_command_count",
            executed_count_field="executed_command_count",
            extra_fields={
                "full_evidence_included": args.profile == PROFILE_FULL,
                **zero_summary_fields,
            },
        ),
        "results": results,
        "boundary": {
            **{field: True for field in PREMERGE_REQUIRED_BOUNDARY_FLAGS},
            "default_profile_no_browser_automation": args.profile == PROFILE_PREMERGE,
        },
    }
    write_json(args.output, report)
    print(f"premerge quality gate report: {args.output}")
    report_valid = self_validate_report(report, profile=str(args.profile))
    if failed:
        print_failed_command_details(failed)
        return 1
    if not report_valid:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
