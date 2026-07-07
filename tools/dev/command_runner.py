"""Small subprocess helpers shared by local QA and demo evidence tools."""

from __future__ import annotations

import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.dev.report_status_contract import STATUS_FAILED, STATUS_PASSED


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def shorten_output(value: str, root: Path, limit: int) -> str:
    normalized = value.replace(str(root), "$REPO_ROOT").strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[-limit:]


def command_text(command: list[str]) -> str:
    return " ".join(command)


def run_command(
    name: str,
    command: list[str],
    *,
    root: Path,
    timeout_seconds: int,
    output_tail_limit: int,
    env: dict[str, str] | None = None,
    include_timestamps: bool = True,
    stdout_path: Path | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    started_at = now_iso()
    stdout_redirect_bytes: int | None = None
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            env={**os.environ, **(env or {})},
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        return_code = completed.returncode
        if stdout_path is not None:
            stdout_path.parent.mkdir(parents=True, exist_ok=True)
            stdout_path.write_text(completed.stdout, encoding="utf-8")
            stdout_redirect_bytes = len(completed.stdout.encode("utf-8"))
        stdout_tail = shorten_output(completed.stdout, root, output_tail_limit)
        stderr_tail = shorten_output(completed.stderr, root, output_tail_limit)
    except subprocess.TimeoutExpired as exc:
        return_code = 124
        stdout_text = exc.stdout or ""
        if stdout_path is not None:
            stdout_path.parent.mkdir(parents=True, exist_ok=True)
            stdout_path.write_text(stdout_text, encoding="utf-8")
            stdout_redirect_bytes = len(stdout_text.encode("utf-8"))
        stdout_tail = shorten_output(stdout_text, root, output_tail_limit)
        stderr_tail = shorten_output(
            (exc.stderr or "") + "\ncommand timed out",
            root,
            output_tail_limit,
        )
    result = {
        "name": name,
        "command": command_text(command),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "return_code": return_code,
        "status": STATUS_PASSED if return_code == 0 else STATUS_FAILED,
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
    }
    if include_timestamps:
        result["started_at"] = started_at
        result["finished_at"] = now_iso()
    if stdout_path is not None:
        result["stdout_path"] = str(stdout_path)
        result["stdout_redirect_bytes"] = stdout_redirect_bytes
    return result
