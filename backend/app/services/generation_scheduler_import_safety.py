"""Import safety helpers for Generation Scheduler review artifacts.

The scheduler accepts local JSON files from external review-only runners. This
module centralizes path restrictions and sensitive-key scans without touching
database state, providers, environment variables, or runtime activation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar


TError = TypeVar("TError", bound=Exception)

FORBIDDEN_IMPORT_KEYS = {
    "api_key",
    "secret",
    "token",
    "raw_prompt",
    "full_trace",
    "raw_json",
    "provider_response",
    "provider_body",
    "prompt_body",
}


def _raise(error_cls: type[TError], message: str) -> None:
    raise error_cls(message)


def resolve_import_path(
    value: Any,
    *,
    label: str,
    repo_root: Path,
    error_cls: type[TError] = ValueError,
) -> Path:
    if not isinstance(value, str) or not value.strip():
        _raise(error_cls, f"{label} is required")
    path = Path(value.strip())
    if not path.is_absolute():
        path = repo_root / path
    resolved = path.resolve()
    if ".env" in resolved.parts:
        _raise(error_cls, f"{label} must not reference .env")
    allowed_roots = (repo_root.resolve(), Path("/tmp").resolve())
    if not any(resolved == root or root in resolved.parents for root in allowed_roots):
        _raise(error_cls, f"{label} must be under repository root or /tmp")
    if not resolved.is_file():
        _raise(error_cls, f"{label} file not found: {value}")
    return resolved


def find_forbidden_import_keys(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if str(key).lower() in FORBIDDEN_IMPORT_KEYS:
                found.append(child_path)
            found.extend(find_forbidden_import_keys(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(find_forbidden_import_keys(child, f"{path}[{index}]"))
    return found


def load_safe_import_json(
    path: Path,
    *,
    label: str,
    error_cls: type[TError] = ValueError,
) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        _raise(error_cls, f"{label} must be a JSON object")
    forbidden = find_forbidden_import_keys(payload)
    if forbidden:
        _raise(
            error_cls,
            f"{label} contains forbidden sensitive keys: {', '.join(forbidden[:5])}",
        )
    return payload


def display_import_path(path: Path, *, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()
