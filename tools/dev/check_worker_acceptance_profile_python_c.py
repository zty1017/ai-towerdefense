#!/usr/bin/env python3
"""Smoke-check profile runner parsing of Python -c code arguments."""

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
)


REPORT_SCHEMA_VERSION = "worker_acceptance_profile_python_c_smoke.v0.1"
DEFAULT_OUTPUT = Path("/tmp/worker_acceptance_profile_python_c_smoke.v0.1.json")


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
    safe = parse_command('python3 -c "import json; print(json.dumps({\\\"ok\\\": True}))"')
    assert safe.argv == [
        "python3",
        "-c",
        'import json; print(json.dumps({"ok": True}))',
    ]

    rejected = {
        "python_c_then_extra_args": expect_rejected('python3 -c "print(1)"; git status'),
        "standalone_semicolon": expect_rejected("python3 -m compileall tools; git status"),
        "unsafe_redirect": expect_rejected("python3 -m json.tool a.json > out.json"),
    }
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": now_iso(),
        "status": "passed",
        "safe_python_c_argv": safe.argv,
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
        print(f"worker acceptance python -c smoke failed: {exc}", file=sys.stderr)
        return 1
    print(f"worker acceptance python -c smoke passed: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
