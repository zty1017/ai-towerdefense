#!/usr/bin/env python3
"""Run a fast offline quality gate for day-to-day development.

This command intentionally avoids browser automation, provider calls, .env reads,
database writes, and runtime activation. It delegates to existing validators so
small changes can get a quick signal before the heavier demo evidence export.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = Path("/tmp/ai_td_fast_quality_gate_report.v0.1.json")
DEFAULT_GENERATED_AT = "2026-07-07T00:00:00+00:00"
OUTPUT_TAIL_LIMIT = 1200


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def shorten(value: str, limit: int = OUTPUT_TAIL_LIMIT) -> str:
    normalized = value.replace(str(ROOT), "$REPO_ROOT").strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[-limit:]


def command_text(command: list[str]) -> str:
    return " ".join(command)


def run_command(
    name: str,
    command: list[str],
    timeout_seconds: int,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env={**os.environ, **(env or {})},
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        return_code = completed.returncode
        stdout_tail = shorten(completed.stdout)
        stderr_tail = shorten(completed.stderr)
    except subprocess.TimeoutExpired as exc:
        return_code = 124
        stdout_tail = shorten(exc.stdout or "")
        stderr_tail = shorten((exc.stderr or "") + "\ncommand timed out")
    elapsed = round(time.monotonic() - started, 3)
    return {
        "name": name,
        "command": command_text(command),
        "elapsed_seconds": elapsed,
        "return_code": return_code,
        "status": "passed" if return_code == 0 else "failed",
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
    }


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
                "tools/dev/run_fast_quality_gate.py",
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
            int(item["timeout_seconds"]),
            item.get("env") if isinstance(item.get("env"), dict) else None,
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
