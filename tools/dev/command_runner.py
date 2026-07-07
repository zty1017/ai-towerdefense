"""Small subprocess helpers shared by local QA and demo evidence tools."""

from __future__ import annotations

import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
) -> dict[str, Any]:
    started = time.monotonic()
    started_at = now_iso()
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
        stdout_tail = shorten_output(completed.stdout, root, output_tail_limit)
        stderr_tail = shorten_output(completed.stderr, root, output_tail_limit)
    except subprocess.TimeoutExpired as exc:
        return_code = 124
        stdout_tail = shorten_output(exc.stdout or "", root, output_tail_limit)
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
        "status": "passed" if return_code == 0 else "failed",
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
    }
    if include_timestamps:
        result["started_at"] = started_at
        result["finished_at"] = now_iso()
    return result
