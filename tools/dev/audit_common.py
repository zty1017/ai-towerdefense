#!/usr/bin/env python3
"""Shared helpers for read-only development audit tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.dev.report_io import load_json_object, write_json


ROOT = Path(__file__).resolve().parents[2]


def require_tmp_output(path: Path) -> Path:
    resolved = path.expanduser().resolve(strict=False)
    tmp_root = Path("/tmp").resolve(strict=False)
    repo_root = ROOT.resolve(strict=False)
    if resolved != tmp_root and tmp_root not in resolved.parents:
        raise ValueError("--output must point under /tmp; audit must not write repo files")
    if resolved == repo_root or repo_root in resolved.parents:
        raise ValueError("--output must not point inside the repository; use /tmp outside the worktree")
    return resolved


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def normalize_command(command: str) -> str:
    return " ".join(command.lower().split())
