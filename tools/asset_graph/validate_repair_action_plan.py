#!/usr/bin/env python3
"""Validate a RepairActionPlan v0.1 JSON file.

Checks:
- JSON parses and matches repair_action_plan.v0.1 schema.
- repair actions are from the finite allowed action set.
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
SCHEMA_PATH = ROOT / "shared/schemas/repair_action_plan.v0.1.schema.json"

ALLOWED_ACTIONS = frozenset({
    "inspect_spec",
    "inspect_artifact",
    "inspect_validation_report",
    "patch_spec",
    "patch_prompt",
    "rerun_node",
    "increase_candidates",
    "replace_with_template",
    "split_asset_layer",
    "fallback_to_preset",
    "accept_with_warning",
    "abort_compile",
})

REQUIRED_BUDGET_FIELDS = frozenset({"max_iterations", "max_provider_calls", "max_seconds"})

ALLOWED_TOP_KEYS = frozenset({
    "schema_version",
    "plan_id",
    "triggered_by",
    "budgets",
    "actions",
    "overall_rationale",
})

ALLOWED_TRIGGER_KEYS = frozenset({
    "type",
    "message",
    "node_id",
    "severity",
})

ALLOWED_ACTION_KEYS = frozenset({
    "action_type",
    "target_node_id",
    "target_field",
    "patch_value",
    "rationale",
    "order",
})


def validate_plan(data: dict[str, Any]) -> list[str]:
    errors = validate_json_schema(data, SCHEMA_PATH)

    # --- schema_version ---
    sv = data.get("schema_version")
    if sv != "repair_action_plan.v0.1":
        errors.append(
            f"schema_version must be 'repair_action_plan.v0.1' "
            f"(got {sv!r})"
        )

    # --- unknown top-level keys ---
    for key in data:
        if key not in ALLOWED_TOP_KEYS:
            errors.append(
                f"unknown field '{key}' is not allowed "
                f"(allowed: {sorted(ALLOWED_TOP_KEYS)})"
            )

    # --- plan_id ---
    pid = data.get("plan_id")
    if not isinstance(pid, str) or not pid:
        errors.append("plan_id must be a non-empty string")

    # --- triggered_by ---
    triggered = data.get("triggered_by")
    if not isinstance(triggered, list) or len(triggered) == 0:
        errors.append("triggered_by must be a non-empty array")
    elif triggered:
        for i, item in enumerate(triggered):
            if not isinstance(item, dict):
                errors.append(f"triggered_by[{i}] must be an object")
                continue
            for key in item:
                if key not in ALLOWED_TRIGGER_KEYS:
                    errors.append(
                        f"triggered_by[{i}] unknown field '{key}' "
                        f"(allowed: {sorted(ALLOWED_TRIGGER_KEYS)})"
                    )
            if "type" not in item:
                errors.append(f"triggered_by[{i}] missing required field 'type'")
            if "message" not in item:
                errors.append(f"triggered_by[{i}] missing required field 'message'")

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

    # --- actions ---
    actions = data.get("actions")
    if not isinstance(actions, list) or len(actions) == 0:
        errors.append("actions must be a non-empty array")
    elif actions:
        orders: list[int] = []
        for i, action in enumerate(actions):
            apath = f"actions[{i}]"
            if not isinstance(action, dict):
                errors.append(f"{apath} must be an object")
                continue
            for key in action:
                if key not in ALLOWED_ACTION_KEYS:
                    errors.append(
                        f"{apath} unknown field '{key}' "
                        f"(allowed: {sorted(ALLOWED_ACTION_KEYS)})"
                    )
            atype = action.get("action_type")
            if not isinstance(atype, str) or not atype:
                errors.append(f"{apath}.action_type must be a non-empty string")
            elif atype not in ALLOWED_ACTIONS:
                errors.append(
                    f"{apath}.action_type={atype!r} is not in the allowed "
                    f"action set (allowed: {sorted(ALLOWED_ACTIONS)})"
                )
            order = action.get("order")
            if order is not None:
                if not isinstance(order, int) or order < 0:
                    errors.append(f"{apath}.order must be a non-negative integer")
                else:
                    orders.append(order)
        if orders:
            if len(orders) != len(set(orders)):
                errors.append("actions[].order values must be unique")
            expected = list(range(len(orders)))
            if sorted(orders) != expected:
                errors.append(
                    "actions[].order values must be continuous from 0 "
                    f"(expected {expected}, got {sorted(orders)})"
                )

    # --- Forbidden fields scan ---
    scan_forbidden_terms(data, "", errors, context="repair_action_plan")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a RepairActionPlan v0.1 JSON file."
    )
    parser.add_argument("plan", help="Path to a repair_action_plan JSON file.")
    args = parser.parse_args()

    path = Path(args.plan)
    try:
        data = load_json(path)
    except FileNotFoundError:
        print("INVALID RepairActionPlan")
        print(f"- file not found: {path}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID RepairActionPlan")
        print(f"- not valid JSON: {exc}")
        return 1

    if not isinstance(data, dict):
        print("INVALID RepairActionPlan")
        print("- root must be an object")
        return 1

    errors = validate_plan(data)
    if errors:
        print("INVALID RepairActionPlan")
        for e in errors:
            print(f"- {e}")
        return 1

    print(f"OK: {path}")
    print(f"- schema_version: {data.get('schema_version')}")
    print(f"- plan_id: {data.get('plan_id')}")
    print(f"- actions: {len(data.get('actions', []))}")
    print(f"- budgets: {data.get('budgets', {})}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
