"""Shared helpers for AssetGraph validation scripts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FORBIDDEN_ARTIFACT_TERMS = frozenset({
    "provider",
    "model",
    "raw_prompt",
    "full_trace",
    "raw_json",
    "api_key",
    "secret",
    "unreviewed_content",
})

_jsonschema = None


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any, *, sort_keys: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=sort_keys)
        handle.write("\n")


def scan_forbidden_terms(
    value: Any,
    path: str,
    errors: list[str],
    *,
    context: str,
) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key in FORBIDDEN_ARTIFACT_TERMS:
                errors.append(
                    f"forbidden field '{child_path}' must not appear in {context}"
                )
            scan_forbidden_terms(child, child_path, errors, context=context)
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            scan_forbidden_terms(child, f"{path}[{idx}]", errors, context=context)
    elif isinstance(value, str):
        lowered = value.lower()
        for term in FORBIDDEN_ARTIFACT_TERMS:
            if term in lowered:
                errors.append(
                    f"forbidden term {term!r} found in string value at '{path}'"
                )


def validate_json_schema(data: Any, schema_path: Path) -> list[str]:
    js = _get_jsonschema()
    if js is False:
        return []

    try:
        schema = load_json(schema_path)
    except Exception as exc:
        return [f"cannot load schema {schema_path}: {exc}"]

    try:
        js.validate(data, schema)
    except js.ValidationError as exc:
        errors = [f"schema validation failed: {exc.message}"]
        errors.extend(f"  - {cause.message}" for cause in exc.context)
        return errors
    except Exception as exc:
        return [f"unexpected validation error: {exc}"]

    return []


def _get_jsonschema():
    global _jsonschema
    if _jsonschema is None:
        try:
            import jsonschema as _jsonschema
        except ImportError:
            _jsonschema = False
    return _jsonschema
