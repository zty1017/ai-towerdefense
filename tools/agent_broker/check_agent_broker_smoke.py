#!/usr/bin/env python3
"""不调用外部 agent 的文件总线与路由 smoke。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.agent_broker.agentctl import select_route  # noqa: E402
from tools.agent_broker.agent_worker import (  # noqa: E402
    codebuddy_prompt_ready,
    codebuddy_trust_prompt_visible,
)


TASK_PACK = ROOT / "examples/worker_task_packs/p1e_premerge_quality_gate.v0.1.json"


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/tmp/ai_td_agent_broker_smoke.json"),
    )
    args = parser.parse_args()
    checks: list[dict[str, object]] = []

    for difficulty, executor, model in (
        ("medium_low", "codebuddy", "hy3"),
        ("medium_high", "codebuddy", "glm-5.2"),
        ("extreme", "codex", None),
    ):
        actual = select_route("auto", difficulty)
        passed = actual == {"executor": executor, "model": model}
        checks.append(
            {
                "name": f"route_{difficulty}",
                "passed": passed,
                "actual": actual,
            }
        )

    readiness_cases = {
        "ready": "CodeBuddy Code\n>\n⏵⏵ auto mode on (shift+Tab to cycle)\n",
        "splash_only": "CodeBuddy Code\nTips for getting started\n",
        "mode_without_prompt": "CodeBuddy Code\n⏵⏵ auto mode on\n",
    }
    checks.append(
        {
            "name": "codebuddy_prompt_readiness",
            "passed": (
                codebuddy_prompt_ready(readiness_cases["ready"])
                and not codebuddy_prompt_ready(readiness_cases["splash_only"])
                and not codebuddy_prompt_ready(readiness_cases["mode_without_prompt"])
            ),
        }
    )
    trust_prompt = """
Do you trust the files in this folder?
  > 1. Trust folder only (task-worktree)
Enter to confirm • Esc to exit
"""
    checks.append(
        {
            "name": "codebuddy_trust_prompt_detection",
            "passed": (
                codebuddy_trust_prompt_visible(trust_prompt)
                and not codebuddy_trust_prompt_visible(readiness_cases["ready"])
            ),
        }
    )

    with tempfile.TemporaryDirectory(prefix="ai-td-agent-broker-", dir="/tmp") as tmp:
        bus = Path(tmp)
        dispatch_id = "smoke-plan-only"
        delegate = run(
            [
                sys.executable,
                "tools/agent_broker/agentctl.py",
                "--bus-root",
                str(bus),
                "delegate",
                "--task-pack",
                str(TASK_PACK),
                "--dispatch-id",
                dispatch_id,
                "--difficulty",
                "medium_low",
                "--authorize-external",
            ]
        )
        worker = run(
            [
                sys.executable,
                "tools/agent_broker/agent_worker.py",
                "--repository",
                str(ROOT),
                "--bus-root",
                str(bus),
                "--plan-only",
            ]
        )
        result_path = bus / "results" / f"{dispatch_id}.json"
        result = (
            json.loads(result_path.read_text(encoding="utf-8"))
            if result_path.exists()
            else {}
        )
        roundtrip_passed = (
            delegate.returncode == 0
            and worker.returncode == 0
            and result.get("status") == "planned"
            and result.get("route") == {"executor": "codebuddy", "model": "hy3"}
            and not list((bus / "inbox").glob("*.json"))
            and not list((bus / "running").glob("*.json"))
            and not list(bus.glob(".prompt-*"))
        )
        checks.append(
            {
                "name": "plan_only_file_bus_roundtrip",
                "passed": roundtrip_passed,
                "delegate_return_code": delegate.returncode,
                "worker_return_code": worker.returncode,
                "result_status": result.get("status"),
            }
        )

    failed = [item for item in checks if item.get("passed") is not True]
    report = {
        "status": "passed" if not failed else "failed",
        "summary": {"check_count": len(checks), "failed_count": len(failed)},
        "checks": checks,
        "external_agent_call_count": 0,
        "worktree_create_count": 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
