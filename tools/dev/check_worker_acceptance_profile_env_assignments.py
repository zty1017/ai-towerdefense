#!/usr/bin/env python3
"""Smoke-check profile runner parsing and execution of prefix env assignments."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.dev.command_runner import now_iso  # noqa: E402
from tools.dev.report_io import write_json  # noqa: E402
from tools.dev.run_worker_acceptance_profile import (  # noqa: E402
    UnsupportedCommandSyntax,
    parse_command,
    run_profile_commands,
)


REPORT_SCHEMA_VERSION = "worker_acceptance_profile_env_assignment_smoke.v0.1"
DEFAULT_OUTPUT = Path("/tmp/worker_acceptance_profile_env_assignment_smoke.v0.1.json")
SMOKE_STDOUT_TARGET = Path("/tmp/worker_acceptance_profile_env_assignment_value.txt")
SMOKE_PYCACHE_PREFIX = "/tmp/worker_acceptance_profile_env_assignment_pycache"


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
    raise AssertionError(f"unexpectedly accepted invalid env command: {command}")


def run_smoke() -> dict[str, Any]:
    command = (
        f"PYTHONPYCACHEPREFIX={SMOKE_PYCACHE_PREFIX} AI_TD_ENV_SMOKE=ok "
        "python3 -c \"import os; print(os.environ['AI_TD_ENV_SMOKE'])\" "
        ">/tmp/worker_acceptance_profile_env_assignment_value.txt"
    )
    parsed = parse_command(command)
    assert parsed.env == {
        "PYTHONPYCACHEPREFIX": SMOKE_PYCACHE_PREFIX,
        "AI_TD_ENV_SMOKE": "ok",
    }
    assert parsed.argv == [
        "python3",
        "-c",
        "import os; print(os.environ['AI_TD_ENV_SMOKE'])",
    ]
    assert parsed.stdout_path == SMOKE_STDOUT_TARGET

    if SMOKE_STDOUT_TARGET.exists():
        SMOKE_STDOUT_TARGET.unlink()
    results = run_profile_commands(
        command_strings=[command],
        dry_run=False,
        fail_fast=True,
        timeout_seconds=30,
    )
    assert len(results) == 1, results
    assert results[0]["status"] == "passed", results
    assert results[0]["env"] == parsed.env, results
    assert SMOKE_STDOUT_TARGET.read_text(encoding="utf-8") == "ok\n"

    rejected = {
        "assignment_without_executable": expect_rejected("AI_TD_ENV_SMOKE=ok"),
        "empty_command": expect_rejected(""),
    }
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": now_iso(),
        "status": "passed",
        "parsed": {
            "argv": parsed.argv,
            "env": parsed.env,
            "stdout_path": str(parsed.stdout_path),
        },
        "execution_result": results[0],
        "rejected": rejected,
        "safety_summary": {
            "provider_call_count": 0,
            "env_file_read": False,
            "repo_files_modified": False,
            "world_mutation_count": 0,
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
        print(f"worker acceptance env assignment smoke failed: {exc}", file=sys.stderr)
        return 1
    print(f"worker acceptance env assignment smoke passed: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
