#!/usr/bin/env python3
"""Validate intent-compile artifacts against their JSON Schema.

Accepts one or more JSON file paths. Auto-detects schema_version from each
file and selects the corresponding schema from shared/schemas/.

If jsonschema library is not installed, degrades gracefully to basic field
checks (required top-level keys, schema_version match, forbidden field scan).

Usage:
  python3 tools/asset_graph/validate_intent_compile_artifacts.py <file1.json> [file2.json ...]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS_DIR = ROOT / "shared/schemas"

# Map schema_version prefix -> schema filename
SCHEMA_VERSION_MAP: dict[str, str] = {
    "player_utterance.v0.1": "player_utterance.v0.1.schema.json",
    "player_intent.v0.1": "player_intent.v0.1.schema.json",
    "asset_design_spec.v0.1": "asset_design_spec.v0.1.schema.json",
    "legalized_design_spec.v0.1": "legalized_design_spec.v0.1.schema.json",
    "legalization_report.v0.1": "legalization_report.v0.1.schema.json",
    "asset_plan.v0.1": "asset_plan.v0.1.schema.json",
    "compile_template_selection.v0.1": "compile_template_selection.v0.1.schema.json",
    "repair_action_plan.v0.1": "repair_action_plan.v0.1.schema.json",
}

FORBIDDEN_FIELDS = frozenset({
    "provider",
    "model",
    "raw_prompt",
    "full_trace",
    "raw_json",
    "api_key",
    "secret",
    "unreviewed_content",
})

_jsonschema = None  # lazy import


def _get_jsonschema():
    global _jsonschema
    if _jsonschema is None:
        try:
            import jsonschema as _jsonschema
        except ImportError:
            _jsonschema = False
    return _jsonschema


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def scan_forbidden_fields(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key in FORBIDDEN_FIELDS:
                errors.append(
                    f"forbidden field '{child_path}' found in artifact"
                )
            scan_forbidden_fields(child, child_path, errors)
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            scan_forbidden_fields(child, f"{path}[{idx}]", errors)
    elif isinstance(value, str):
        lowered = value.lower()
        for term in FORBIDDEN_FIELDS:
            if term in lowered:
                errors.append(
                    f"forbidden term {term!r} found in string value at '{path}'"
                )


def basic_field_check(data: dict, path: str, errors: list[str]) -> None:
    if not isinstance(data, dict):
        errors.append(f"{path}: root must be a JSON object")
        return
    sv = data.get("schema_version")
    if not isinstance(sv, str) or not sv:
        errors.append(f"{path}: missing or invalid 'schema_version'")
    else:
        if sv not in SCHEMA_VERSION_MAP:
            errors.append(
                f"{path}: unknown schema_version={sv!r} "
                f"(known: {sorted(SCHEMA_VERSION_MAP)})"
            )
    scan_forbidden_fields(data, path, errors)


def validate_with_schema(data: dict, schema_path: Path, file_path: Path) -> list[str]:
    errors: list[str] = []
    js = _get_jsonschema()
    if js is False:
        basic_field_check(data, str(file_path), errors)
        errors.insert(
            0,
            f"jsonschema library not available; "
            f"falling back to basic field check for {file_path.name}",
        )
        return errors

    try:
        schema = load_json(schema_path)
    except Exception as exc:
        errors.append(f"cannot load schema {schema_path}: {exc}")
        basic_field_check(data, str(file_path), errors)
        return errors

    try:
        js.validate(data, schema)
    except js.ValidationError as exc:
        errors.append(f"schema validation failed: {exc.message}")
        for cause in exc.context:
            errors.append(f"  - {cause.message}")
    except Exception as exc:
        errors.append(f"unexpected validation error: {exc}")

    return errors


def validate_file(file_path: Path) -> list[str]:
    errors: list[str] = []

    try:
        data = load_json(file_path)
    except FileNotFoundError:
        return [f"file not found: {file_path}"]
    except json.JSONDecodeError as exc:
        return [f"invalid JSON: {exc}"]

    if not isinstance(data, dict):
        return [f"root must be a JSON object, got {type(data).__name__}"]

    sv = data.get("schema_version")
    if not isinstance(sv, str) or sv not in SCHEMA_VERSION_MAP:
        basic_field_check(data, str(file_path), errors)
        if not errors:
            errors.append(f"unknown or missing schema_version={sv!r}")
        return errors

    schema_filename = SCHEMA_VERSION_MAP[sv]
    schema_path = SCHEMAS_DIR / schema_filename
    if not schema_path.exists():
        errors.append(f"schema file not found: {schema_path}")
        basic_field_check(data, str(file_path), errors)
        return errors

    errors = validate_with_schema(data, schema_path, file_path)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate intent-compile artifacts against JSON Schema."
    )
    parser.add_argument(
        "files", nargs="+", help="One or more JSON artifact file paths."
    )
    args = parser.parse_args()

    has_errors = False
    for file_path_str in args.files:
        file_path = Path(file_path_str)
        errors = validate_file(file_path)
        if errors:
            has_errors = True
            print(f"FAIL: {file_path}")
            for err in errors:
                print(f"  - {err}")
        else:
            print(f"OK: {file_path}")

    return 1 if has_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
