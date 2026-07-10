#!/usr/bin/env python3
"""投递和读取临时 Agent Worker 任务。"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.dev.validate_worker_task_pack import validate as validate_task_pack  # noqa: E402


DIFFICULTIES = {"low", "medium_low", "medium_high", "high", "extreme"}
EXECUTORS = {"auto", "codebuddy", "codex"}
BUS_DIRS = ("inbox", "running", "results", "reports", "tasks", "logs")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_bus_root() -> Path:
    configured = os.environ.get("AI_TD_AGENT_BROKER_HOME")
    if configured:
        return Path(configured).expanduser()
    return Path(f"/tmp/ai-td-agent-broker-{os.getuid()}")


def initialize_bus(root: Path) -> None:
    for name in BUS_DIRS:
        (root / name).mkdir(parents=True, exist_ok=True)


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} 的 JSON 根节点必须是对象")
    return value


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def select_route(executor: str, difficulty: str) -> dict[str, str | None]:
    if executor == "codex" or (executor == "auto" and difficulty == "extreme"):
        return {"executor": "codex", "model": None}
    model = "glm-5.2" if difficulty in {"medium_high", "high"} else "hy3"
    return {"executor": "codebuddy", "model": model}


def dispatch_id(task_id: Any) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", str(task_id)).strip("-")[:52]
    timestamp = datetime.now(timezone.utc).strftime("%m%d-%H%M%S")
    return f"{slug or 'task'}-{timestamp}-{secrets.token_hex(2)}"


def locate(root: Path, task_id: str) -> tuple[str, Path] | None:
    for status in ("results", "running", "inbox"):
        path = root / status / f"{task_id}.json"
        if path.exists():
            return status, path
    return None


def wait_result(root: Path, task_id: str, timeout: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        path = root / "results" / f"{task_id}.json"
        if path.exists():
            return load_object(path)
        time.sleep(0.5)
    raise TimeoutError(f"等待任务 {task_id} 超时")


def command_delegate(args: argparse.Namespace, root: Path) -> int:
    source = args.task_pack.expanduser().resolve(strict=True)
    task_pack = load_object(source)
    validate_task_pack(task_pack)
    route = select_route(args.executor, args.difficulty)
    preview = {
        "task_id": task_pack.get("task_id"),
        "route": route,
        "branch": task_pack.get("branch"),
        "worktree": task_pack.get("worktree"),
        "acceptance_profile": args.profile,
    }
    if args.dry_run:
        print(json.dumps({"status": "dry_run", **preview}, ensure_ascii=False, indent=2))
        return 0
    if not args.authorize_external:
        raise ValueError("真实委派必须显式传入 --authorize-external")

    task_id = args.dispatch_id or dispatch_id(task_pack.get("task_id"))
    if locate(root, task_id) is not None or (root / "tasks" / f"{task_id}.json").exists():
        raise ValueError(f"dispatch id 已存在：{task_id}")
    copied_task = root / "tasks" / f"{task_id}.json"
    atomic_write(copied_task, task_pack)
    envelope = {
        "dispatch_id": task_id,
        "created_at": now_iso(),
        "task_pack_path": str(copied_task),
        "source_task_pack_path": str(source),
        "executor": args.executor,
        "difficulty": args.difficulty,
        "route": route,
        "acceptance_profile": args.profile,
        "external_agent_authorized": True,
    }
    atomic_write(root / "inbox" / f"{task_id}.json", envelope)
    response: dict[str, Any] = {"dispatch_id": task_id, "status": "queued", **preview}
    if args.wait:
        response["result"] = wait_result(root, task_id, args.timeout)
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0


def command_status(args: argparse.Namespace, root: Path) -> int:
    found = locate(root, args.dispatch_id)
    if found is None:
        raise FileNotFoundError(args.dispatch_id)
    status, path = found
    value = load_object(path)
    print(
        json.dumps(
            {
                "dispatch_id": args.dispatch_id,
                "status": value.get("status", status),
                "location": status,
                "worktree": value.get("worktree"),
                "tmux_session": value.get("tmux_session"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def command_result(args: argparse.Namespace, root: Path) -> int:
    path = root / "results" / f"{args.dispatch_id}.json"
    if not path.exists():
        raise FileNotFoundError(args.dispatch_id)
    print(json.dumps(load_object(path), ensure_ascii=False, indent=2))
    return 0


def command_wait(args: argparse.Namespace, root: Path) -> int:
    print(
        json.dumps(
            wait_result(root, args.dispatch_id, args.timeout),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def command_list(_: argparse.Namespace, root: Path) -> int:
    items = []
    seen: set[str] = set()
    for status in ("inbox", "running", "results"):
        for path in sorted((root / status).glob("*.json")):
            if path.stem in seen:
                continue
            seen.add(path.stem)
            value = load_object(path)
            items.append(
                {
                    "dispatch_id": path.stem,
                    "status": value.get("status", status),
                    "location": status,
                }
            )
    print(json.dumps({"tasks": items}, ensure_ascii=False, indent=2))
    return 0


def command_worker_complete(args: argparse.Namespace, root: Path) -> int:
    if not (root / "running" / f"{args.dispatch_id}.json").exists():
        raise FileNotFoundError(f"运行中任务不存在：{args.dispatch_id}")
    report = {
        "dispatch_id": args.dispatch_id,
        "status": args.status,
        "summary": args.summary[:500],
        "created_at": now_iso(),
    }
    atomic_write(root / "reports" / f"{args.dispatch_id}.json", report)
    print(json.dumps(report, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bus-root", type=Path, default=default_bus_root())
    commands = parser.add_subparsers(dest="command", required=True)

    delegate = commands.add_parser("delegate")
    delegate.add_argument("--task-pack", type=Path, required=True)
    delegate.add_argument("--dispatch-id")
    delegate.add_argument("--executor", choices=sorted(EXECUTORS), default="auto")
    delegate.add_argument("--difficulty", choices=sorted(DIFFICULTIES), default="medium_low")
    delegate.add_argument("--profile")
    delegate.add_argument("--authorize-external", action="store_true")
    delegate.add_argument("--dry-run", action="store_true")
    delegate.add_argument("--wait", action="store_true")
    delegate.add_argument("--timeout", type=int, default=3600)

    for name in ("status", "result"):
        command = commands.add_parser(name)
        command.add_argument("dispatch_id")
    wait = commands.add_parser("wait")
    wait.add_argument("dispatch_id")
    wait.add_argument("--timeout", type=int, default=3600)
    commands.add_parser("list")
    complete = commands.add_parser("worker-complete")
    complete.add_argument("dispatch_id")
    complete.add_argument("--status", choices=("success", "failed", "needs_human"), required=True)
    complete.add_argument("--summary", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = args.bus_root.expanduser().resolve(strict=False)
    initialize_bus(root)
    handlers = {
        "delegate": command_delegate,
        "status": command_status,
        "result": command_result,
        "wait": command_wait,
        "list": command_list,
        "worker-complete": command_worker_complete,
    }
    try:
        return handlers[args.command](args, root)
    except (FileNotFoundError, TimeoutError, ValueError) as exc:
        print(f"agentctl: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
