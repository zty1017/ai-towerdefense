#!/usr/bin/env python3
"""Validate a CompilableObjectCatalog v0.1 JSON file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ASSET_GRAPH_DIR = ROOT / "tools" / "asset_graph"
if str(ASSET_GRAPH_DIR) not in sys.path:
    sys.path.insert(0, str(ASSET_GRAPH_DIR))

from validation_common import load_json, scan_forbidden_terms, validate_json_schema  # noqa: E402


SCHEMA_PATH = ROOT / "shared/schemas/compilable_object_catalog.v0.1.schema.json"
REQUIRED_MVP_LAYERS = frozenset({"entity", "level", "narrative", "progression", "economy"})


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _repo_path(ref: str) -> Path:
    path = Path(ref)
    return path if path.is_absolute() else ROOT / ref


def _dedupe(errors: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for error in errors:
        if error not in seen:
            seen.add(error)
            out.append(error)
    return out


def _check_source_files(catalog: dict[str, Any], errors: list[str]) -> None:
    for obj_index, obj in enumerate(as_list(catalog.get("objects"))):
        if not isinstance(obj, dict):
            continue
        for file_index, file_ref in enumerate(as_list(obj.get("source_files"))):
            if not isinstance(file_ref, str) or not file_ref:
                errors.append(f"objects[{obj_index}].source_files[{file_index}] must be a non-empty string")
                continue
            if not _repo_path(file_ref).is_file():
                errors.append(
                    f"objects[{obj_index}].source_files[{file_index}] references missing file: {file_ref}"
                )


def _check_uniqueness_and_coverage(catalog: dict[str, Any], errors: list[str]) -> None:
    ids: set[str] = set()
    duplicate_ids: set[str] = set()
    layers: set[str] = set()
    permission_levels: set[str] = set()
    player_visible_count = 0
    review_required_count = 0
    for obj in as_list(catalog.get("objects")):
        if not isinstance(obj, dict):
            continue
        object_id = obj.get("object_id")
        if isinstance(object_id, str):
            if object_id in ids:
                duplicate_ids.add(object_id)
            ids.add(object_id)
        layer = obj.get("object_layer")
        if isinstance(layer, str):
            layers.add(layer)
        level = obj.get("compile_permission_level")
        if isinstance(level, str):
            permission_levels.add(level)
        contract = obj.get("runtime_contract")
        if isinstance(contract, dict):
            if contract.get("player_visible") is True:
                player_visible_count += 1
            if contract.get("export_status") in {"candidate_only", "review_only", "not_exported"}:
                review_required_count += 1
    for object_id in sorted(duplicate_ids):
        errors.append(f"duplicate object_id: {object_id}")
    missing_layers = sorted(REQUIRED_MVP_LAYERS - layers)
    if missing_layers:
        errors.append(f"catalog missing MVP object layers: {missing_layers}")
    if "L5_engine" in permission_levels:
        errors.append("catalog must not include L5_engine objects in MVP review pack")

    summary = catalog.get("summary")
    if isinstance(summary, dict):
        if summary.get("total_objects") != len(ids):
            errors.append(
                f"summary.total_objects mismatch: expected {len(ids)}, got {summary.get('total_objects')}"
            )
        if summary.get("player_exposed_count") != player_visible_count:
            errors.append(
                "summary.player_exposed_count mismatch: "
                f"expected {player_visible_count}, got {summary.get('player_exposed_count')}"
            )
        if summary.get("review_required_count") != review_required_count:
            errors.append(
                "summary.review_required_count mismatch: "
                f"expected {review_required_count}, got {summary.get('review_required_count')}"
            )


def validate_compilable_object_catalog(catalog: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(catalog, dict):
        return ["catalog root must be an object"]
    errors.extend(validate_json_schema(catalog, SCHEMA_PATH))
    scan_forbidden_terms(catalog, "", errors, context="CompilableObjectCatalog")
    _check_source_files(catalog, errors)
    _check_uniqueness_and_coverage(catalog, errors)
    return _dedupe(errors)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a CompilableObjectCatalog v0.1 JSON file.")
    parser.add_argument("catalog", help="Path to catalog JSON.")
    args = parser.parse_args()

    try:
        catalog = load_json(Path(args.catalog))
    except FileNotFoundError:
        print("INVALID CompilableObjectCatalog")
        print(f"- catalog file not found: {args.catalog}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID CompilableObjectCatalog")
        print(f"- catalog is not valid JSON: {exc}")
        return 1

    errors = validate_compilable_object_catalog(catalog)
    if errors:
        print("INVALID CompilableObjectCatalog")
        for error in errors:
            print(f"- {error}")
        return 1

    print("OK CompilableObjectCatalog")
    print(f"- catalog_id: {catalog.get('catalog_id')}")
    print(f"- objects: {len(catalog.get('objects', []))}")
    print(f"- layers: {sorted((catalog.get('summary') or {}).get('layer_counts', {}).keys())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
