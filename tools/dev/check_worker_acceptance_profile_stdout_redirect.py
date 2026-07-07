#!/usr/bin/env python3
"""Smoke-check profile runner parsing and execution of safe stdout redirects."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.dev.command_runner import now_iso  # noqa: E402
from tools.dev.run_worker_acceptance_profile import (  # noqa: E402
    UnsupportedCommandSyntax,
    parse_command,
    run_profile_commands,
)


REPORT_SCHEMA_VERSION = "worker_acceptance_profile_stdout_redirect_smoke.v0.1"
DEFAULT_OUTPUT = Path("/tmp/worker_acceptance_profile_stdout_redirect_smoke.v0.1.json")
SMOKE_STDOUT_TARGET = Path("/tmp/worker_acceptance_profile_stdout_redirect_value.txt")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def require_tmp_output(path: Path) -> Path:
    resolved = path.expanduser().resolve(strict=False)
    tmp_root = Path("/tmp").resolve(strict=False)
    if resolved != tmp_root and tmp_root not in resolved.parents:
        raise ValueError("--output must be under /tmp")
    return resolved


def expect_rejected(command: str) -> str:
    try:
        parse_command(command)
    except UnsupportedCommandSyntax as exc:
        return str(exc)
    raise AssertionError(f"unexpectedly accepted shell-only command: {command}")


def run_smoke() -> dict[str, Any]:
    compact = parse_command(
        "python3 -m json.tool shared/schemas/provider_output_envelope.v0.1.schema.json "
        ">/tmp/provider_output_envelope.schema.pretty.smoke.json"
    )
    assert compact.argv == [
        "python3",
        "-m",
        "json.tool",
        "shared/schemas/provider_output_envelope.v0.1.schema.json",
    ]
    assert compact.stdout_path == Path(
        "/tmp/provider_output_envelope.schema.pretty.smoke.json"
    )

    spaced = parse_command('python3 -c "print(42)" > /tmp/worker_acceptance_redirect_spaced.txt')
    assert spaced.argv == ["python3", "-c", "print(42)"]
    assert spaced.stdout_path == Path("/tmp/worker_acceptance_redirect_spaced.txt")

    if SMOKE_STDOUT_TARGET.exists():
        SMOKE_STDOUT_TARGET.unlink()
    results = run_profile_commands(
        command_strings=[
            'python3 -c "print(42)" >/tmp/worker_acceptance_profile_stdout_redirect_value.txt'
        ],
        dry_run=False,
        fail_fast=True,
        timeout_seconds=30,
    )
    assert len(results) == 1, results
    assert results[0]["status"] == "passed", results
    assert SMOKE_STDOUT_TARGET.read_text(encoding="utf-8") == "42\n"

    existing_dir = Path("/tmp/worker_acceptance_profile_stdout_redirect_dir")
    existing_dir.mkdir(parents=True, exist_ok=True)
    rejected = {
        "relative_stdout_redirect": expect_rejected("python3 -m json.tool a.json > out.json"),
        "missing_stdout_target": expect_rejected("python3 -m json.tool a.json >"),
        "stdout_target_is_tmp_root": expect_rejected("python3 -m json.tool a.json > /tmp"),
        "stdout_target_is_existing_dir": expect_rejected(
            "python3 -m json.tool a.json > /tmp/worker_acceptance_profile_stdout_redirect_dir"
        ),
        "redirect_not_final": expect_rejected(
            "python3 -m json.tool a.json >/tmp/worker_acceptance_redirect.json extra"
        ),
        "stderr_redirect": expect_rejected(
            "python3 -m json.tool a.json 2>/tmp/worker_acceptance_redirect.json"
        ),
        "stdin_redirect": expect_rejected("python3 -m json.tool < a.json"),
        "append_redirect": expect_rejected(
            "python3 -m json.tool a.json >>/tmp/worker_acceptance_redirect.json"
        ),
    }
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": now_iso(),
        "status": "passed",
        "safe_compact_redirect": {
            "argv": compact.argv,
            "stdout_path": str(compact.stdout_path),
        },
        "safe_spaced_redirect": {
            "argv": spaced.argv,
            "stdout_path": str(spaced.stdout_path),
        },
        "execution_result": results[0],
        "rejected": rejected,
        "safety_summary": {
            "provider_call_count": 0,
            "env_file_read": False,
            "acceptance_commands_executed": False,
            "repo_files_modified": False,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        output = require_tmp_output(args.output)
        report = run_smoke()
        write_json(output, report)
    except Exception as exc:  # noqa: BLE001 - smoke should report concise failure.
        print(f"worker acceptance stdout redirect smoke failed: {exc}", file=sys.stderr)
        return 1
    print(f"worker acceptance stdout redirect smoke passed: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
