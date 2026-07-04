#!/usr/bin/env python3
"""Validate a CompileTemplateSelection v0.1 JSON file.

Checks:
- JSON parses and matches compile_template_selection.v0.1 schema.
- template_name is from the allowed list (enum in schema).
- Does NOT carry an embedded unvalidated workflow graph.
- Must contain budgets: max_iterations, max_provider_calls, max_seconds (or equivalent).
- Must NOT contain forbidden fields: provider/model/raw_prompt/full_trace/raw_json/
  api_key/secret/unreviewed_content.

The validator never reads .env and never prints API keys or secrets.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from validation_common import load_json, scan_forbidden_terms, validate_json_schema

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "shared/schemas/compile_template_selection.v0.1.schema.json"

ALLOWED_TEMPLATE_NAMES = frozenset({
    "TowerCompileGraph",
    "SupportItemCompileGraph",
    "TemporaryModCompileGraph",
    "IntelAssetCompileGraph",
    "SkillVFXCompileGraph",
    "IconCompileGraph",
    "MapModifierCompileGraph",
})

REQUIRED_BUDGET_FIELDS = frozenset({"max_iterations", "max_provider_calls", "max_seconds"})
ALLOWED_PARAMETER_OVERRIDE_KEYS = frozenset({
    "proposal_path",
    "max_tokens",
    "request_timeout",
    "simulation_duration_seconds",
})

# Top-level keys allowed by the schema (additionalProperties: false).
ALLOWED_TOP_KEYS = frozenset({
    "schema_version",
    "template_name",
    "template_version",
    "confidence",
    "rationale",
    "parameter_overrides",
    "budgets",
    "selected_branch",
})


def validate_selection(
    data: dict[str, Any]
) -> list[str]:
    errors = validate_json_schema(data, SCHEMA_PATH)

    # --- schema_version ---
    sv = data.get("schema_version")
    if sv != "compile_template_selection.v0.1":
        errors.append(
            f"schema_version must be 'compile_template_selection.v0.1' "
            f"(got {sv!r})"
        )

    # --- unknown top-level keys ---
    for key in data:
        if key not in ALLOWED_TOP_KEYS:
            errors.append(
                f"unknown field '{key}' is not allowed "
                f"(allowed: {sorted(ALLOWED_TOP_KEYS)})"
            )

    # --- template_name ---
    tname = data.get("template_name")
    if not isinstance(tname, str) or not tname:
        errors.append("template_name must be a non-empty string")
    elif tname not in ALLOWED_TEMPLATE_NAMES:
        errors.append(
            f"template_name={tname!r} is not in the allowed list "
            f"(allowed: {sorted(ALLOWED_TEMPLATE_NAMES)})"
        )

    # --- No embedded unvalidated workflow ---
    if "nodes" in data or "edges" in data:
        errors.append(
            "compile_template_selection must not contain an embedded workflow "
            "graph (nodes/edges are not allowed here)"
        )
    if "workflow" in data:
        errors.append(
            "compile_template_selection must not contain an embedded 'workflow' field"
        )

    overrides = data.get("parameter_overrides")
    if overrides is not None:
        if not isinstance(overrides, dict):
            errors.append("parameter_overrides must be an object when present")
        else:
            for key in overrides:
                if key not in ALLOWED_PARAMETER_OVERRIDE_KEYS:
                    errors.append(
                        f"parameter_overrides.{key} is not allowed "
                        f"(allowed: {sorted(ALLOWED_PARAMETER_OVERRIDE_KEYS)})"
                    )

    # --- budgets ---
    budgets = data.get("budgets")
    if not isinstance(budgets, dict):
        errors.append("budgets must be an object")
    else:
        for req in REQUIRED_BUDGET_FIELDS:
            if req not in budgets:
                errors.append(
                    f"budgets must contain '{req}' "
                    f"(required: {sorted(REQUIRED_BUDGET_FIELDS)})"
                )
        # Type checks on required budget fields
        if "max_iterations" in budgets:
            val = budgets["max_iterations"]
            if not isinstance(val, int) or val < 1:
                errors.append(
                    f"budgets.max_iterations must be a positive integer "
                    f"(got {val!r})"
                )
        if "max_provider_calls" in budgets:
            val = budgets["max_provider_calls"]
            if not isinstance(val, int) or val < 0:
                errors.append(
                    f"budgets.max_provider_calls must be a non-negative integer "
                    f"(got {val!r})"
                )
        if "max_seconds" in budgets:
            val = budgets["max_seconds"]
            if not isinstance(val, (int, float)) or val < 1:
                errors.append(
                    f"budgets.max_seconds must be a positive number "
                    f"(got {val!r})"
                )

    # --- Forbidden fields scan ---
    scan_forbidden_terms(data, "", errors, context="compile_template_selection")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a CompileTemplateSelection v0.1 JSON file."
    )
    parser.add_argument("selection", help="Path to a compile_template_selection JSON file.")
    args = parser.parse_args()

    path = Path(args.selection)
    try:
        data = load_json(path)
    except FileNotFoundError:
        print("INVALID CompileTemplateSelection")
        print(f"- file not found: {path}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID CompileTemplateSelection")
        print(f"- not valid JSON: {exc}")
        return 1

    if not isinstance(data, dict):
        print("INVALID CompileTemplateSelection")
        print("- root must be an object")
        return 1

    errors = validate_selection(data)
    if errors:
        print("INVALID CompileTemplateSelection")
        for e in errors:
            print(f"- {e}")
        return 1

    print(f"OK: {path}")
    print(f"- schema_version: {data.get('schema_version')}")
    print(f"- template_name: {data.get('template_name')}")
    print(f"- budgets: {data.get('budgets', {})}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
