#!/usr/bin/env python3
"""Run a command that is expected to fail, with optional /tmp output absence checks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.dev.command_runner import now_iso, run_command  # noqa: E402


REPORT_SCHEMA_VERSION = "expected_command_failure_report.v0.1"
OUTPUT_TAIL_LIMIT = 1600


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def require_tmp_path(path: Path, *, label: str) -> Path:
    resolved = path.expanduser().resolve(strict=False)
    tmp_root = Path("/tmp").resolve(strict=False)
    repo_root = ROOT.resolve(strict=False)
    if resolved == tmp_root or tmp_root not in resolved.parents:
        raise ValueError(f"{label} must be a file under /tmp")
    if resolved == repo_root or repo_root in resolved.parents:
        raise ValueError(f"{label} must not be inside the repository")
    return resolved


def normalize_command(command: list[str]) -> list[str]:
    if command and command[0] == "--":
        return command[1:]
    return command


def run_expected_failure(
    *,
    name: str,
    command: list[str],
    absent_paths: list[Path],
    output: Path | None,
    timeout_seconds: int,
) -> dict[str, Any]:
    checked_absent_paths = [require_tmp_path(path, label="--expect-output-absent") for path in absent_paths]
    removed_before_run: list[str] = []
    for path in checked_absent_paths:
        if path.exists() and path.is_file():
            path.unlink()
            removed_before_run.append(str(path))
        elif path.exists():
            raise ValueError(f"--expect-output-absent path exists and is not a file: {path}")

    result = run_command(
        name,
        command,
        root=ROOT,
        timeout_seconds=timeout_seconds,
        output_tail_limit=OUTPUT_TAIL_LIMIT,
    )
    missing_after_run = [str(path) for path in checked_absent_paths if not path.exists()]
    present_after_run = [str(path) for path in checked_absent_paths if path.exists()]
    status = "passed" if result["return_code"] not in {0, None} and not present_after_run else "failed"
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": now_iso(),
        "name": name,
        "status": status,
        "expected_failure": True,
        "command_result": result,
        "removed_before_run": removed_before_run,
        "absent_path_count": len(checked_absent_paths),
        "missing_after_run": missing_after_run,
        "present_after_run": present_after_run,
        "safety_summary": {
            "provider_call_count": 0,
            "env_file_read": False,
            "repo_files_modified": False,
            "tmp_files_removed_before_run": len(removed_before_run),
        },
    }
    if output is not None:
        write_json(output, report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--expect-output-absent", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        command = normalize_command(args.command)
        if not command:
            raise ValueError("expected command after --")
        output = require_tmp_path(args.output, label="--output") if args.output else None
        report = run_expected_failure(
            name=args.name,
            command=command,
            absent_paths=args.expect_output_absent,
            output=output,
            timeout_seconds=args.timeout,
        )
    except Exception as exc:  # noqa: BLE001 - CLI reports concise failure.
        print(f"expected command failure check failed: {exc}", file=sys.stderr)
        return 2
    if report["status"] != "passed":
        result = report["command_result"]
        print(
            f"expected {args.name} to fail without forbidden outputs; "
            f"return_code={result['return_code']} present_after_run={report['present_after_run']}",
            file=sys.stderr,
        )
        return 1
    print(f"expected command failure passed: {args.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
