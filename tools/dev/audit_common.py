#!/usr/bin/env python3
"""Shared helpers for read-only development audit tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def load_json_object(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object")
    return data


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


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
