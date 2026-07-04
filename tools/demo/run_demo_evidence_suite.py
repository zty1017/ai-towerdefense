#!/usr/bin/env python3
"""Run the repeatable MVP demo evidence suite.

This orchestrator intentionally delegates to existing tools:

1. capture the browser player-flow visual smoke report;
2. validate that report;
3. export the redacted demo evidence bundle with the browser report attached;
4. write a compact suite report for recording and judge Q&A.

It does not call providers, read .env, mutate world state, or activate runtime
artifacts. It only produces local review/evidence files under the output root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = Path("/tmp/ai_td_demo_evidence_suite")
REPORT_NAME = "demo_evidence_suite_report.v0.1.json"
FRONTEND_REPORT_NAME = "frontend_flow_visual_smoke_report.v0.1.json"
MAX_OUTPUT_TAIL = 1800


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_ref(path: Path, role: str) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(path),
            "role": role,
            "exists": False,
        }
    return {
        "path": str(path),
        "role": role,
        "exists": True,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def shorten(value: str, limit: int = MAX_OUTPUT_TAIL) -> str:
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
) -> dict[str, Any]:
    started = time.monotonic()
    started_at = now_iso()
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
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
        "started_at": started_at,
        "finished_at": now_iso(),
        "elapsed_seconds": elapsed,
        "return_code": return_code,
        "status": "passed" if return_code == 0 else "failed",
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
    }


def build_capture_command(args: argparse.Namespace, frontend_output: Path) -> list[str]:
    command = [
        sys.executable,
        "tools/frontend/capture_frontend_flow_visual_smoke.py",
        "--output-dir",
        str(frontend_output),
        "--timeout",
        str(args.browser_timeout),
    ]
    if args.browser_bin:
        command.extend(["--browser-bin", str(args.browser_bin)])
    if args.allow_missing_browser:
        command.append("--allow-missing-browser")
    return command


def build_validate_command(
    report_path: Path,
    allow_unavailable: bool,
) -> list[str]:
    command = [
        sys.executable,
        "tools/frontend/validate_frontend_flow_visual_smoke_report.py",
        str(report_path),
    ]
    if allow_unavailable:
        command.append("--allow-unavailable")
    return command


def build_export_command(evidence_output: Path, report_path: Path) -> list[str]:
    return [
        sys.executable,
        "tools/demo/export_evidence.py",
        "--output-dir",
        str(evidence_output),
        "--frontend-flow-smoke-report",
        str(report_path),
    ]


def browser_flow_summary(report: dict[str, Any] | None) -> dict[str, Any]:
    if report is None:
        return {
            "status": "missing",
            "captured_screenshot_count": 0,
            "expected_screenshot_count": 0,
            "viewport_count": 0,
            "failure_count": 0,
            "safety_summary": {},
        }
    screenshots = as_list(report.get("screenshots"))
    return {
        "schema_version": report.get("schema_version"),
        "status": report.get("status"),
        "browser_available": report.get("browser_available"),
        "viewport_count": report.get("viewport_count"),
        "captured_screenshot_count": report.get("captured_screenshot_count"),
        "expected_screenshot_count": report.get("expected_screenshot_count"),
        "step_ids": as_list(report.get("step_ids")),
        "screenshot_matrix": [
            f"{item.get('viewport_id')}:{item.get('step_id')}"
            for item in screenshots
            if isinstance(item, dict)
        ],
        "failure_count": len(as_list(report.get("failures"))),
        "safety_summary": as_obj(report.get("safety_summary")),
    }


def evidence_summary(evidence: dict[str, Any] | None) -> dict[str, Any]:
    if evidence is None:
        return {
            "export_validation_status": "missing",
            "readiness_status": "missing",
            "frontend_flow_status": "missing",
        }
    validation = as_obj(evidence.get("validation_summary"))
    export_validation = as_obj(validation.get("current_export_validation"))
    readiness = as_obj(evidence.get("mvp_demo_readiness"))
    frontend_flow = as_obj(
        as_obj(evidence.get("browser_visual_evidence")).get("frontend_flow")
    )
    return {
        "export_validation_status": export_validation.get("status"),
        "readiness_status": readiness.get("overall_status"),
        "frontend_flow_status": frontend_flow.get("status"),
        "frontend_flow_captured_screenshot_count": frontend_flow.get(
            "captured_screenshot_count"
        ),
        "frontend_flow_expected_screenshot_count": frontend_flow.get(
            "expected_screenshot_count"
        ),
        "frontend_flow_failure_count": frontend_flow.get("failure_count"),
    }


def derive_suite_status(
    commands: list[dict[str, Any]],
    frontend_report: dict[str, Any] | None,
    evidence: dict[str, Any] | None,
    allow_missing_browser: bool,
) -> tuple[str, list[str]]:
    failures: list[str] = [
        f"command_failed:{item['name']}"
        for item in commands
        if item.get("status") != "passed"
    ]
    frontend_status = (frontend_report or {}).get("status")
    evidence_status = evidence_summary(evidence).get("export_validation_status")

    if frontend_status == "captured":
        captured = int((frontend_report or {}).get("captured_screenshot_count") or 0)
        expected = int((frontend_report or {}).get("expected_screenshot_count") or 0)
        if captured != 14 or expected != 14:
            failures.append("frontend_flow_screenshot_count_not_14")
    elif frontend_status == "browser_unavailable" and allow_missing_browser:
        if evidence_status != "passed":
            failures.append("evidence_export_not_passed")
        return ("browser_unavailable_allowed", failures)
    else:
        failures.append(f"frontend_flow_status:{frontend_status or 'missing'}")

    if evidence_status != "passed":
        failures.append(f"evidence_export_status:{evidence_status}")

    return ("passed" if not failures else "failed", failures)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="输出根目录，默认 /tmp/ai_td_demo_evidence_suite。",
    )
    parser.add_argument(
        "--browser-timeout",
        type=int,
        default=45,
        help="传给浏览器截图脚本的单步浏览器超时秒数。",
    )
    parser.add_argument(
        "--command-timeout",
        type=int,
        default=180,
        help="每个子命令的最大运行秒数。",
    )
    parser.add_argument(
        "--browser-bin",
        type=Path,
        help="可选：Chromium 兼容浏览器路径。",
    )
    parser.add_argument(
        "--allow-missing-browser",
        action="store_true",
        help="允许没有本地浏览器时生成 browser_unavailable 证据；默认会失败。",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    output_root = args.output_root.expanduser()
    frontend_output = output_root / "frontend_flow_visual_smoke"
    frontend_report_path = frontend_output / FRONTEND_REPORT_NAME
    evidence_output = output_root / "demo_evidence"
    suite_report_path = output_root / REPORT_NAME
    output_root.mkdir(parents=True, exist_ok=True)

    commands: list[dict[str, Any]] = []
    frontend_report: dict[str, Any] | None = None
    evidence: dict[str, Any] | None = None

    capture_command = build_capture_command(args, frontend_output)
    commands.append(
        run_command("frontend_flow_visual_smoke_capture", capture_command, args.command_timeout)
    )

    if frontend_report_path.exists():
        frontend_report = load_json(frontend_report_path)

    if frontend_report_path.exists():
        validate_command = build_validate_command(
            frontend_report_path,
            args.allow_missing_browser,
        )
        commands.append(
            run_command(
                "frontend_flow_visual_smoke_validate",
                validate_command,
                args.command_timeout,
            )
        )

        export_command = build_export_command(evidence_output, frontend_report_path)
        commands.append(
            run_command("demo_evidence_export", export_command, args.command_timeout)
        )
        evidence_path = evidence_output / "evidence.json"
        if evidence_path.exists():
            evidence = load_json(evidence_path)

    status, failures = derive_suite_status(
        commands,
        frontend_report,
        evidence,
        args.allow_missing_browser,
    )
    report = {
        "schema_version": "demo_evidence_suite_report.v0.1",
        "suite_id": "mvp_demo_evidence_suite",
        "status": status,
        "generated_at": now_iso(),
        "output_root": str(output_root),
        "commands": commands,
        "outputs": {
            "frontend_flow_report": file_ref(
                frontend_report_path,
                "frontend_flow_visual_smoke_report",
            ),
            "demo_evidence_json": file_ref(
                evidence_output / "evidence.json",
                "demo_evidence_json",
            ),
            "demo_summary_markdown": file_ref(
                evidence_output / "summary.md",
                "demo_summary_markdown",
            ),
            "demo_index_html": file_ref(
                evidence_output / "index.html",
                "demo_index_html",
            ),
            "suite_report": {
                "path": str(suite_report_path),
                "role": "demo_evidence_suite_report",
                "exists": True,
            },
        },
        "frontend_flow_visual_smoke": browser_flow_summary(frontend_report),
        "demo_evidence": evidence_summary(evidence),
        "failures": failures,
        "safety_summary": {
            "reads_env_file": False,
            "provider_call_count_during_suite": 0,
            "world_mutation_count_during_suite": 0,
            "runtime_activation_count_during_suite": 0,
            "stores_provider_body": False,
            "uses_localhost_browser_only": True,
        },
    }
    write_json(suite_report_path, report)
    print(f"demo evidence suite {status}: {suite_report_path}")
    print(f"- frontend report: {frontend_report_path}")
    print(f"- evidence bundle: {evidence_output}")
    return 0 if status == "passed" or status == "browser_unavailable_allowed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
