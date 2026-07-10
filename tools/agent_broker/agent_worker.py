#!/usr/bin/env python3
"""从本地文件总线领取一个任务并启动 CodeBuddy 或 Codex。"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.agent_broker.agentctl import (  # noqa: E402
    atomic_write,
    default_bus_root,
    initialize_bus,
    load_object,
    now_iso,
    select_route,
)
from tools.dev.validate_worker_task_pack import validate as validate_task_pack  # noqa: E402


def run(
    command: list[str],
    *,
    cwd: Path,
    timeout: int,
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        input=stdin,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return run(["git", *args], cwd=cwd, timeout=60)


def claim_next(bus_root: Path) -> tuple[Path, dict[str, Any]] | None:
    for queued in sorted((bus_root / "inbox").glob("*.json")):
        running = bus_root / "running" / queued.name
        try:
            os.replace(queued, running)
        except FileNotFoundError:
            continue
        envelope = load_object(running)
        envelope["status"] = "running"
        envelope["started_at"] = now_iso()
        atomic_write(running, envelope)
        return running, envelope
    return None


def repository_root(repository: Path) -> Path:
    common = git(repository, "rev-parse", "--git-common-dir")
    if common.returncode != 0:
        raise ValueError("repository 不是 Git worktree")
    common_path = Path(common.stdout.strip())
    if not common_path.is_absolute():
        common_path = repository / common_path
    return common_path.resolve().parent


def is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def prepare_worktree(repository: Path, task: dict[str, Any]) -> Path:
    main_repository = repository_root(repository)
    default_root = main_repository.parent / f"{main_repository.name}-worktrees"
    worktree_root = Path(
        os.environ.get("AI_TD_AGENT_WORKTREE_ROOT", str(default_root))
    ).expanduser().resolve(strict=False)
    worktree = Path(str(task["worktree"])).expanduser().resolve(strict=False)
    if not is_within(worktree, worktree_root):
        raise ValueError(f"worktree 必须位于 {worktree_root}")
    branch = str(task["branch"])
    if task.get("base_branch") != "develop" or not branch.startswith("task/"):
        raise ValueError("只允许从 develop 派生 task/* worktree")

    if not worktree.exists():
        worktree.parent.mkdir(parents=True, exist_ok=True)
        exists = git(main_repository, "show-ref", "--verify", f"refs/heads/{branch}")
        command = ["worktree", "add"]
        if exists.returncode == 0:
            command.extend([str(worktree), branch])
        else:
            command.extend(["-b", branch, str(worktree), "develop"])
        created = git(main_repository, *command)
        if created.returncode != 0:
            raise RuntimeError(created.stderr.strip() or "创建 worktree 失败")

    current = git(worktree, "branch", "--show-current")
    if current.returncode != 0 or current.stdout.strip() != branch:
        raise ValueError(f"worktree 不在预期分支 {branch}")
    dirty = git(worktree, "status", "--porcelain=v1", "--untracked-files=all")
    if dirty.returncode != 0:
        raise RuntimeError(dirty.stderr.strip() or "读取 worktree 状态失败")
    if dirty.stdout.strip():
        raise ValueError("worker 启动前 worktree 必须干净")
    return worktree


def completion_command(bus_root: Path, dispatch_id: str, status: str) -> str:
    return shlex.join(
        [
            sys.executable,
            str(ROOT / "tools/agent_broker/agentctl.py"),
            "--bus-root",
            str(bus_root),
            "worker-complete",
            dispatch_id,
            "--status",
            status,
            "--summary",
            "worker finished",
        ]
    )


def build_prompt(task: dict[str, Any], bus_root: Path, dispatch_id: str) -> str:
    def lines(key: str) -> str:
        return "\n".join(f"- {value}" for value in task.get(key, [])) or "- 无"

    return f"""你在隔离的 task worktree 中执行一个已确认任务。

任务：{task['title']}
目标：{task['objective']}

必须先读：
{lines('required_reading')}

允许修改：
{lines('allowed_paths')}

禁止修改：
{lines('forbidden_paths')}

验收命令：
{lines('acceptance_commands')}

硬性规则：
- 不读取或打印 .env、API key、secret、token。
- 不提交、不合并、不推送，不修改 main 或 develop。
- 不扩大任务范围；需要产品或架构决策时停止。
- 完成实现和验收后必须执行：
  {completion_command(bus_root, dispatch_id, 'success')}
- 无法继续或需要人类处理时执行：
  {completion_command(bus_root, dispatch_id, 'needs_human')}
"""


def tmux_session_name(dispatch_id: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", dispatch_id).strip("-")[:44]
    return f"ai-td-{slug}"


def run_codebuddy(
    *,
    worktree: Path,
    prompt: str,
    dispatch_id: str,
    model: str,
    bus_root: Path,
    timeout: int,
) -> tuple[dict[str, Any], str]:
    session = tmux_session_name(dispatch_id)
    permission_mode = os.environ.get("AI_TD_CODEBUDDY_PERMISSION_MODE", "auto")
    command = shlex.join(
        [
            "codebuddy",
            "--model",
            model,
            "--permission-mode",
            permission_mode,
            "--subagent-permission-mode",
            permission_mode,
            "--tools",
            "default",
        ]
    )
    for argv in (
        ["tmux", "new-session", "-d", "-s", session, "-c", str(worktree)],
        ["tmux", "send-keys", "-t", session, "-l", command],
        ["tmux", "send-keys", "-t", session, "C-m"],
    ):
        completed = run(argv, cwd=worktree, timeout=30)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "启动 CodeBuddy tmux 失败")

    time.sleep(float(os.environ.get("AI_TD_CODEBUDDY_STARTUP_SECONDS", "3")))
    prompt_path = bus_root / f".prompt-{dispatch_id}.txt"
    prompt_path.write_text(prompt, encoding="utf-8")
    os.chmod(prompt_path, 0o600)
    try:
        for argv in (
            ["tmux", "load-buffer", "-b", dispatch_id, str(prompt_path)],
            ["tmux", "paste-buffer", "-b", dispatch_id, "-t", session],
            ["tmux", "send-keys", "-t", session, "C-m"],
            ["tmux", "delete-buffer", "-b", dispatch_id],
        ):
            completed = run(argv, cwd=worktree, timeout=30)
            if completed.returncode != 0:
                raise RuntimeError(completed.stderr.strip() or "注入 CodeBuddy 任务失败")
    finally:
        prompt_path.unlink(missing_ok=True)

    report_path = bus_root / "reports" / f"{dispatch_id}.json"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if report_path.exists():
            report = load_object(report_path)
            if report.get("status") == "success":
                run(["tmux", "kill-session", "-t", session], cwd=worktree, timeout=30)
            return report, session
        alive = run(["tmux", "has-session", "-t", session], cwd=worktree, timeout=30)
        if alive.returncode != 0:
            return {
                "status": "failed",
                "summary": "CodeBuddy 会话退出但没有写完成标记",
            }, session
        time.sleep(1)
    return {
        "status": "needs_human",
        "summary": f"等待超时；请执行 tmux attach -t {session}",
    }, session


def run_codex(
    *, worktree: Path, prompt: str, dispatch_id: str, bus_root: Path, timeout: int
) -> tuple[dict[str, Any], None]:
    last_message = bus_root / "logs" / f"{dispatch_id}.last_message.txt"
    command = [
        "codex",
        "exec",
        "-C",
        str(worktree),
        "--sandbox",
        "workspace-write",
        "--ephemeral",
        "--output-last-message",
        str(last_message),
        "-",
    ]
    completed = run(command, cwd=worktree, timeout=timeout, stdin=prompt)
    return {
        "status": "success" if completed.returncode == 0 else "failed",
        "summary": "Codex headless 已结束",
        "return_code": completed.returncode,
        "last_message_path": str(last_message),
        "stderr_tail": completed.stderr[-800:],
    }, None


def changed_files(worktree: Path) -> list[str]:
    status = git(worktree, "status", "--porcelain=v1", "--untracked-files=all")
    if status.returncode != 0:
        raise RuntimeError(status.stderr.strip() or "读取改动失败")
    result: list[str] = []
    for line in status.stdout.splitlines():
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if path:
            result.append(path.strip('"'))
    return sorted(set(result))


def path_matches(path: str, roots: list[Any]) -> bool:
    normalized = path.strip("/")
    return any(
        normalized == str(root).strip("/")
        or normalized.startswith(f"{str(root).strip('/')}/")
        for root in roots
    )


def scope_report(task: dict[str, Any], files: list[str]) -> dict[str, Any]:
    out_of_scope = [
        path for path in files if not path_matches(path, task.get("allowed_paths", []))
    ]
    forbidden = [
        path for path in files if path_matches(path, task.get("forbidden_paths", []))
    ]
    return {
        "changed_files": files,
        "out_of_scope_files": out_of_scope,
        "forbidden_files": forbidden,
        "passed": not out_of_scope and not forbidden,
    }


def run_acceptance(
    *,
    worktree: Path,
    task_path: Path,
    task: dict[str, Any],
    profile: str | None,
    output: Path,
    timeout: int,
) -> dict[str, Any]:
    acceptance = task.get("acceptance_profile")
    if not isinstance(acceptance, dict):
        return {
            "status": "not_run",
            "reason": "任务包没有 acceptance_profile；worker 已按顶层命令自检",
        }
    command = [
        sys.executable,
        str(worktree / "tools/dev/run_worker_acceptance_profile.py"),
        str(task_path),
        "--output",
        str(output),
        "--fail-fast",
    ]
    if profile:
        command.extend(["--profile", profile])
    completed = run(command, cwd=worktree, timeout=timeout)
    report = load_object(output) if output.exists() else {}
    return {
        "status": report.get("status", "failed"),
        "return_code": completed.returncode,
        "report_path": str(output),
        "stderr_tail": completed.stderr[-800:],
    }


def finish(
    *, bus_root: Path, running_path: Path, envelope: dict[str, Any], result: dict[str, Any]
) -> dict[str, Any]:
    result.update(
        {
            "dispatch_id": envelope.get("dispatch_id"),
            "finished_at": now_iso(),
            "external_agent_authorized": True,
            "auto_commit": False,
            "auto_merge": False,
            "auto_push": False,
            "auto_worktree_cleanup": False,
        }
    )
    atomic_write(bus_root / "results" / f"{envelope['dispatch_id']}.json", result)
    running_path.unlink(missing_ok=True)
    return result


def process_once(args: argparse.Namespace) -> dict[str, Any] | None:
    claimed = claim_next(args.bus_root)
    if claimed is None:
        return None
    running_path, envelope = claimed
    task_path = Path(str(envelope["task_pack_path"]))
    route = select_route(str(envelope["executor"]), str(envelope["difficulty"]))
    base_result: dict[str, Any] = {"route": route, "status": "failed"}
    try:
        task = load_object(task_path)
        validate_task_pack(task)
        if args.plan_only:
            return finish(
                bus_root=args.bus_root,
                running_path=running_path,
                envelope=envelope,
                result={
                    **base_result,
                    "status": "planned",
                    "worktree": task.get("worktree"),
                    "branch": task.get("branch"),
                },
            )
        if not args.allow_external or envelope.get("external_agent_authorized") is not True:
            raise PermissionError("worker 未启用外部 agent 权限")

        worktree = prepare_worktree(args.repository, task)
        prompt = build_prompt(task, args.bus_root, str(envelope["dispatch_id"]))
        envelope["worktree"] = str(worktree)
        if route["executor"] == "codebuddy":
            envelope["tmux_session"] = tmux_session_name(
                str(envelope["dispatch_id"])
            )
            atomic_write(running_path, envelope)
            worker_report, session = run_codebuddy(
                worktree=worktree,
                prompt=prompt,
                dispatch_id=str(envelope["dispatch_id"]),
                model=str(route["model"]),
                bus_root=args.bus_root,
                timeout=args.timeout,
            )
        else:
            atomic_write(running_path, envelope)
            worker_report, session = run_codex(
                worktree=worktree,
                prompt=prompt,
                dispatch_id=str(envelope["dispatch_id"]),
                bus_root=args.bus_root,
                timeout=args.timeout,
            )

        if worker_report.get("status") != "success":
            terminal = (
                "needs_human"
                if worker_report.get("status") == "needs_human"
                else "failed"
            )
            return finish(
                bus_root=args.bus_root,
                running_path=running_path,
                envelope=envelope,
                result={
                    **base_result,
                    "status": terminal,
                    "worktree": str(worktree),
                    "tmux_session": session,
                    "worker_report": worker_report,
                },
            )

        acceptance = run_acceptance(
            worktree=worktree,
            task_path=task_path,
            task=task,
            profile=envelope.get("acceptance_profile"),
            output=args.bus_root
            / "logs"
            / f"{envelope['dispatch_id']}.acceptance.json",
            timeout=args.timeout,
        )
        scope = scope_report(task, changed_files(worktree))
        acceptance_passed = acceptance["status"] in {"passed", "not_run"}
        status = "completed" if acceptance_passed and scope["passed"] else "failed"
        return finish(
            bus_root=args.bus_root,
            running_path=running_path,
            envelope=envelope,
            result={
                **base_result,
                "status": status,
                "worktree": str(worktree),
                "tmux_session": session,
                "worker_report": worker_report,
                "acceptance": acceptance,
                "scope": scope,
            },
        )
    except Exception as exc:  # noqa: BLE001 - worker must always emit a result.
        return finish(
            bus_root=args.bus_root,
            running_path=running_path,
            envelope=envelope,
            result={
                **base_result,
                "status": "failed",
                "error_type": type(exc).__name__,
                "message": str(exc),
            },
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=ROOT)
    parser.add_argument("--bus-root", type=Path, default=default_bus_root())
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--allow-external", action="store_true")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument("--poll", type=float, default=1.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.repository = args.repository.expanduser().resolve(strict=True)
    args.bus_root = args.bus_root.expanduser().resolve(strict=False)
    initialize_bus(args.bus_root)
    while True:
        result = process_once(args)
        if result is not None:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        if not args.loop:
            return 0
        time.sleep(args.poll)


if __name__ == "__main__":
    raise SystemExit(main())
