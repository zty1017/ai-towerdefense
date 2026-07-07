#!/usr/bin/env python3
"""Shared JSON report IO helpers for demo evidence tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_json_or_raise(path: Path, *, label: str) -> Any:
    try:
        return load_json(path)
    except FileNotFoundError as exc:
        raise ValueError(f"{label} does not exist: {path}") from exc


def load_json_object(path: Path, *, label: str = "JSON root") -> dict[str, Any]:
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be an object")
    return data


def write_json(path: Path, value: Any, *, sort_keys: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=sort_keys)
        handle.write("\n")
