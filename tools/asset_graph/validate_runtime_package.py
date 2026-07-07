#!/usr/bin/env python3
"""Validate a RuntimePackage v0.1 JSON file.

Usage:
    python3 tools/asset_graph/validate_runtime_package.py <package_path>

Checks:
- JSON parses and matches runtime_package.v0.1 schema (additionalProperties:false
  at every layer) via jsonschema if available.
- Pure-Python fallback enforces the same contract (reject_unknown_keys at each
  object layer) regardless of jsonschema availability.
- Recursive forbidden field name scan: provider, model, raw_prompt, full_trace,
  raw_json, api_key, secret, unreviewed_content, source_layer.
- Recursive forbidden URL string scan: http://, https://, ://.
- Recursive forbidden media-layer value scan: raw_media, processed_media.
- media_refs URLs must start with /assets/.
- visual_recipes.kind must be in the 8-value v0.1 whitelist.

Exit 0 with "OK: <path>" on success; exit 1 with concrete error paths on
failure. Supports --help.

The validator never reads .env and never prints API keys or secrets.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import runtime_package as rp  # noqa: E402
from validation_common import load_json  # noqa: E402

DEFAULT_SCHEMA = ROOT / "shared/schemas/runtime_package.v0.1.schema.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a RuntimePackage v0.1 JSON file."
    )
    parser.add_argument(
        "package", help="Path to a runtime package JSON file to validate."
    )
    parser.add_argument(
        "--schema",
        default=str(DEFAULT_SCHEMA),
        help="Path to the runtime_package v0.1 JSON Schema (optional).",
    )
    args = parser.parse_args()

    package_path = Path(args.package)
    schema_path = Path(args.schema)

    try:
        package = load_json(package_path)
    except FileNotFoundError:
        print("INVALID RuntimePackage")
        print(f"- package file not found: {package_path}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID RuntimePackage")
        print(f"- package is not valid JSON: {exc}")
        return 1

    if not isinstance(package, dict):
        print("INVALID RuntimePackage")
        print("- package root must be an object")
        return 1

    schema: dict[str, Any] | None = None
    if schema_path.exists():
        try:
            loaded = load_json(schema_path)
            if isinstance(loaded, dict):
                schema = loaded
        except (FileNotFoundError, json.JSONDecodeError):
            # Schema is optional; fall back to pure-Python only.
            pass

    errors = rp.validate_package(package, schema)
    if errors:
        print("INVALID RuntimePackage")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"OK: {package_path}")
    print(f"- schema_version: {package.get('schema_version')}")
    print(f"- package_id: {package.get('package_id')}")
    print(f"- assets: {len(package.get('assets', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
