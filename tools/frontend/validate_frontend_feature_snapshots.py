#!/usr/bin/env python3
"""Validate player-safe FrontendFeatureSnapshot contributions in a runtime bundle."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
FEATURE_SCHEMA_PATH = ROOT / "shared/schemas/frontend_feature_snapshot.v0.1.schema.json"
CONTRIBUTION_SCHEMA_PATH = ROOT / "shared/schemas/frontend_surface_contribution.v0.1.schema.json"
EXPECTED_SURFACES = {
    "strategic_map": "strategic_map",
    "workshop": "prototype_workshop",
    "battle": "battle_canvas",
    "narrative": "dialogue_modal",
    "settlement": "settlement_panel",
}
EXECUTABLE_KEYS = {
    "html",
    "script",
    "javascript",
    "css",
    "style",
    "component_code",
    "event_handler",
    "raw_prompt",
    "raw_json",
    "full_trace",
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} root must be an object")
    return value


def schema_errors(value: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    try:
        import jsonschema  # type: ignore
    except ImportError:
        return []
    validator_cls = getattr(jsonschema, "Draft202012Validator", None) or getattr(
        jsonschema, "Draft7Validator"
    )
    return [
        f"{'/'.join(map(str, error.absolute_path)) or '$'}: {error.message}"
        for error in sorted(validator_cls(schema).iter_errors(value), key=lambda item: list(item.absolute_path))
    ]


def executable_key_hits(value: Any, path: tuple[str, ...] = ()) -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower()
            if normalized in EXECUTABLE_KEYS:
                hits.append("$." + ".".join((*path, str(key))))
            hits.extend(executable_key_hits(child, (*path, str(key))))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            hits.extend(executable_key_hits(child, (*path, str(index))))
    return hits


def validate_bundle(bundle: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    feature_schema = load_json(FEATURE_SCHEMA_PATH)
    contribution_schema = load_json(CONTRIBUTION_SCHEMA_PATH)
    snapshot_schema = copy.deepcopy(feature_schema)
    snapshot_schema["properties"]["contributions"]["items"] = {}
    snapshots = bundle.get("feature_snapshots")
    if not isinstance(snapshots, dict):
        return ["$.feature_snapshots must be an object"]
    seen_ids: set[str] = set()
    for feature_id, snapshot_value in snapshots.items():
        label = f"$.feature_snapshots.{feature_id}"
        if not isinstance(snapshot_value, dict):
            failures.append(f"{label} must be an object")
            continue
        failures.extend(f"{label}: {error}" for error in schema_errors(snapshot_value, snapshot_schema))
        if snapshot_value.get("feature_id") != feature_id:
            failures.append(f"{label}.feature_id must match its object key")
        expected_surface = EXPECTED_SURFACES.get(feature_id)
        if expected_surface and snapshot_value.get("surface") != expected_surface:
            failures.append(f"{label}.surface must be {expected_surface}")
        contributions = snapshot_value.get("contributions")
        if not isinstance(contributions, list):
            failures.append(f"{label}.contributions must be an array")
            continue
        for index, contribution in enumerate(contributions):
            item_label = f"{label}.contributions[{index}]"
            if not isinstance(contribution, dict):
                failures.append(f"{item_label} must be an object")
                continue
            failures.extend(
                f"{item_label}: {error}" for error in schema_errors(contribution, contribution_schema)
            )
            contribution_id = str(contribution.get("contribution_id") or "")
            if contribution_id in seen_ids:
                failures.append(f"{item_label}.contribution_id duplicated: {contribution_id}")
            seen_ids.add(contribution_id)
            if contribution.get("feature_id") != feature_id:
                failures.append(f"{item_label}.feature_id must match {feature_id}")
            if contribution.get("surface") != snapshot_value.get("surface"):
                failures.append(f"{item_label}.surface must match parent snapshot")
            for hit in executable_key_hits(contribution):
                failures.append(f"{item_label} contains forbidden executable field at {hit}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    failures = validate_bundle(load_json(args.bundle))
    if failures:
        print("frontend feature snapshot validation failed", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(f"frontend feature snapshot validation passed: {args.bundle}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
