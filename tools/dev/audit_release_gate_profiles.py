#!/usr/bin/env python3
"""Audit WorkerTaskPack release_gate profiles for downgraded evidence commands.

This tool is intentionally read-only. It scans WorkerTaskPack JSON files and
checks only the optional acceptance_profile.profiles.release_gate command list.
It does not execute any command from the scanned task packs.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.dev.audit_common import (  # noqa: E402
    display_path,
    load_json_object,
    normalize_command,
    require_tmp_output,
    string_list,
    write_json,
)
from tools.dev.command_runner import now_iso
from tools.dev.run_worker_acceptance_profile import parse_command
from tools.dev.validate_worker_task_pack import validate


REPORT_SCHEMA_VERSION = "release_gate_profile_audit_report.v0.1"
DEFAULT_TASK_PACK_DIR = Path("examples/worker_task_packs")
DEFAULT_OUTPUT = Path("/tmp/release_gate_profile_audit_report.v0.1.json")
RUNNER_MODE_EXCEPTION_TASK_IDS = {
    "P1-D-35-demo-suite-scheduler-runner-selection",
}


def load_json(path: Path) -> dict[str, Any]:
    try:
        return load_json_object(path)
    except ValueError as exc:
        raise ValueError("WorkerTaskPack root must be an object") from exc


def contains_flag(command: str, *flags: str) -> bool:
    normalized = normalize_command(command)
    return any(flag in normalized for flag in flags)


def is_demo_suite(command: str) -> bool:
    return "tools/demo/run_demo_evidence_suite.py" in normalize_command(command)


def is_demo_suite_validator(command: str) -> bool:
    return "tools/demo/validate_demo_evidence_suite_report.py" in normalize_command(command)


def is_full_evidence_export(command: str) -> bool:
    normalized = normalize_command(command)
    return (
        "tools/demo/export_evidence.py" in normalized
        and "--output-dir" in normalized
        and not contains_flag(
            normalized,
            "--validation-profile summary-only",
            "--validation-profile=summary-only",
        )
    )


def release_gate_commands(data: dict[str, Any]) -> list[str] | None:
    acceptance_profile = data.get("acceptance_profile")
    if not isinstance(acceptance_profile, dict):
        return None
    profiles = acceptance_profile.get("profiles")
    if not isinstance(profiles, dict):
        return None
    profile = profiles.get("release_gate")
    if not isinstance(profile, dict):
        return None
    return string_list(profile.get("commands"))


def issue(
    *,
    path: Path,
    task_id: str | None,
    kind: str,
    message: str,
    command_index: int | None = None,
    command: str | None = None,
) -> dict[str, Any]:
    return {
        "path": display_path(path),
        "task_id": task_id,
        "kind": kind,
        "message": message,
        "command_index": command_index,
        "command": command,
    }


def analyze_release_gate(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = {}
    validation_status = "failed"
    validation_error: str | None = None
    issues: list[dict[str, Any]] = []
    try:
        data = load_json(path)
        validate(data)
        validation_status = "passed"
    except Exception as exc:  # noqa: BLE001 - keep scanning all packs.
        validation_error = str(exc)

    task_id = data.get("task_id") if isinstance(data.get("task_id"), str) else None
    if validation_status != "passed":
        issues.append(
            issue(
                path=path,
                task_id=task_id,
                kind="invalid_worker_task_pack",
                message=str(validation_error),
            )
        )

    commands = release_gate_commands(data)
    if commands is None:
        return {
            "path": display_path(path),
            "task_id": task_id,
            "has_release_gate": False,
            "validation_status": validation_status,
            "validation_error": validation_error,
            "command_count": 0,
            "has_demo_suite": False,
            "has_demo_suite_validator": False,
            "has_full_evidence_export": False,
            "issues": issues,
        }

    has_demo_suite = False
    has_demo_suite_validator = False
    has_full_evidence_export = False
    validator_requires_browser = False
    validator_requires_scheduler = False
    validator_requires_outbox = False

    if not commands:
        issues.append(
            issue(
                path=path,
                task_id=task_id,
                kind="empty_release_gate",
                message="release_gate.commands must not be empty",
            )
        )

    for index, command in enumerate(commands, start=1):
        try:
            parse_command(command)
        except Exception as exc:  # noqa: BLE001 - report unsupported syntax as a gate issue.
            issues.append(
                issue(
                    path=path,
                    task_id=task_id,
                    kind="unsupported_release_gate_command_syntax",
                    message=f"{exc.__class__.__name__}: {exc}",
                    command_index=index,
                    command=command,
                )
            )

        if contains_flag(command, "--allow-missing-browser"):
            issues.append(
                issue(
                    path=path,
                    task_id=task_id,
                    kind="browser_missing_downgrade_allowed",
                    message="release_gate must not allow missing browser evidence",
                    command_index=index,
                    command=command,
                )
            )
        if contains_flag(command, "--allow-browser-unavailable"):
            issues.append(
                issue(
                    path=path,
                    task_id=task_id,
                    kind="browser_unavailable_validator_downgrade",
                    message="release_gate validator must require captured browser evidence",
                    command_index=index,
                    command=command,
                )
            )
        if contains_flag(
            command,
            "--validation-profile summary-only",
            "--validation-profile=summary-only",
        ):
            issues.append(
                issue(
                    path=path,
                    task_id=task_id,
                    kind="summary_only_evidence_in_release_gate",
                    message="release_gate must not use summary-only evidence export",
                    command_index=index,
                    command=command,
                )
            )
        if contains_flag(
            command,
            "--require-scheduler-runner-mode",
            "--require-outbox-runner-mode",
        ) and task_id not in RUNNER_MODE_EXCEPTION_TASK_IDS:
            issues.append(
                issue(
                    path=path,
                    task_id=task_id,
                    kind="generic_release_gate_runner_mode_locked",
                    message="generic release_gate must not pin scheduler/outbox runner mode",
                    command_index=index,
                    command=command,
                )
            )

        has_demo_suite = has_demo_suite or is_demo_suite(command)
        has_demo_suite_validator = has_demo_suite_validator or is_demo_suite_validator(command)
        has_full_evidence_export = has_full_evidence_export or is_full_evidence_export(command)
        if is_demo_suite_validator(command):
            validator_requires_browser = validator_requires_browser or contains_flag(
                command,
                "--require-browser-captured",
            )
            validator_requires_scheduler = validator_requires_scheduler or contains_flag(
                command,
                "--require-scheduler-pipeline-smoke",
            )
            validator_requires_outbox = validator_requires_outbox or contains_flag(
                command,
                "--require-outbox-import-smoke",
            )

    if has_demo_suite and not has_demo_suite_validator:
        issues.append(
            issue(
                path=path,
                task_id=task_id,
                kind="demo_suite_without_validator",
                message="release_gate demo suite should be followed by validate_demo_evidence_suite_report.py",
            )
        )
    if has_demo_suite and has_demo_suite_validator and not validator_requires_browser:
        issues.append(
            issue(
                path=path,
                task_id=task_id,
                kind="demo_suite_validator_missing_browser_requirement",
                message="release_gate demo suite validator must include --require-browser-captured",
            )
        )
    if has_demo_suite and has_demo_suite_validator and not validator_requires_scheduler:
        issues.append(
            issue(
                path=path,
                task_id=task_id,
                kind="demo_suite_validator_missing_scheduler_requirement",
                message="release_gate demo suite validator should include --require-scheduler-pipeline-smoke",
            )
        )
    if has_demo_suite and has_demo_suite_validator and not validator_requires_outbox:
        issues.append(
            issue(
                path=path,
                task_id=task_id,
                kind="demo_suite_validator_missing_outbox_requirement",
                message="release_gate demo suite validator should include --require-outbox-import-smoke",
            )
        )
    if not has_demo_suite and not has_full_evidence_export:
        issues.append(
            issue(
                path=path,
                task_id=task_id,
                kind="release_gate_without_release_evidence",
                message=(
                    "release_gate should include run_demo_evidence_suite.py or a full "
                    "tools/demo/export_evidence.py --output-dir command"
                ),
            )
        )

    return {
        "path": display_path(path),
        "task_id": task_id,
        "has_release_gate": True,
        "validation_status": validation_status,
        "validation_error": validation_error,
        "command_count": len(commands),
        "has_demo_suite": has_demo_suite,
        "has_demo_suite_validator": has_demo_suite_validator,
        "has_full_evidence_export": has_full_evidence_export,
        "demo_suite_validator_requirements": {
            "browser_captured": validator_requires_browser,
            "scheduler_pipeline_smoke": validator_requires_scheduler,
            "outbox_import_smoke": validator_requires_outbox,
        },
        "issues": issues,
    }


def sample_issues(issues: list[dict[str, Any]], max_samples: int) -> list[dict[str, Any]]:
    if max_samples <= 0:
        return []
    return issues[:max_samples]


def build_report(task_pack_dir: Path, max_samples: int) -> dict[str, Any]:
    task_pack_dir = task_pack_dir if task_pack_dir.is_absolute() else ROOT / task_pack_dir
    paths = sorted(task_pack_dir.glob("*.json"))
    packs = [analyze_release_gate(path) for path in paths]
    issues = [issue for pack in packs for issue in pack["issues"]]
    issue_counts = Counter(str(item["kind"]) for item in issues)
    with_release_gate = [pack for pack in packs if pack["has_release_gate"]]
    summary = {
        "total_pack_count": len(packs),
        "valid_pack_count": sum(1 for pack in packs if pack["validation_status"] == "passed"),
        "invalid_pack_count": sum(1 for pack in packs if pack["validation_status"] != "passed"),
        "release_gate_profile_count": len(with_release_gate),
        "without_release_gate_profile_count": len(packs) - len(with_release_gate),
        "release_gate_command_count": sum(pack["command_count"] for pack in with_release_gate),
        "release_gate_with_demo_suite_count": sum(1 for pack in with_release_gate if pack["has_demo_suite"]),
        "release_gate_with_demo_suite_validator_count": sum(
            1 for pack in with_release_gate if pack["has_demo_suite_validator"]
        ),
        "release_gate_with_full_evidence_export_count": sum(
            1 for pack in with_release_gate if pack["has_full_evidence_export"]
        ),
        "issue_count": len(issues),
        "issues_by_kind": dict(sorted(issue_counts.items())),
    }
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": now_iso(),
        "task_pack_dir": display_path(task_pack_dir),
        "status": "passed" if not issues else "failed",
        "summary": summary,
        "issue_samples": sample_issues(issues, max_samples),
        "packs": packs,
        "boundary": {
            "read_only": True,
            "acceptance_commands_executed": False,
            "release_gate_commands_executed": False,
            "provider_call_count": 0,
            "env_file_read": False,
            "repo_files_modified": False,
            "browser_automation_started": False,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--task-pack-dir",
        type=Path,
        default=DEFAULT_TASK_PACK_DIR,
        help="Directory containing WorkerTaskPack JSON files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Write the audit report to this path.",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=20,
        help="Maximum issue samples to include in the top-level report.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        output_path = require_tmp_output(args.output)
    except ValueError as exc:
        print(f"release gate profile audit failed: {exc}", file=sys.stderr)
        return 2

    report = build_report(args.task_pack_dir, max(0, int(args.max_samples)))
    write_json(output_path, report)
    summary = report["summary"]
    print(f"release gate profile audit report: {output_path}")
    print(
        "audited {total_pack_count} packs: {release_gate_profile_count} release_gate "
        "profiles, {issue_count} issues".format(**summary)
    )
    if summary["issue_count"]:
        for item in report["issue_samples"][:5]:
            print(
                f"issue: {item['path']} {item['kind']} {item['message']}",
                file=sys.stderr,
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
