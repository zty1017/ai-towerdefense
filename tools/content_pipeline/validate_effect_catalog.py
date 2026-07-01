#!/usr/bin/env python3
"""Validate the MVP runtime effect catalog without third-party dependencies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


EXPECTED_PRIMITIVES = {
    "ring_pulse",
    "beam",
    "chain_arc",
    "sprite_flash",
    "particle_burst",
    "aura_field",
    "screen_shake",
    "floating_text",
}
FORBIDDEN_KEYS = {
    "provider",
    "model",
    "raw_prompt",
    "full_trace",
    "raw_json",
    "api_key",
    "secret",
    "unreviewed_content",
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def scan_forbidden(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key in FORBIDDEN_KEYS:
                errors.append(f"forbidden key in effect catalog: {child_path}")
            scan_forbidden(child, child_path, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_forbidden(child, f"{path}[{index}]", errors)
    elif isinstance(value, str) and (value.startswith("http://") or value.startswith("https://")):
        errors.append(f"external URL is not allowed in effect catalog: {path}")


def validate(catalog: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if catalog.get("schema_version") != "effect_catalog.v0.1":
        errors.append("schema_version must be effect_catalog.v0.1")
    for key in ("catalog_id", "runtime_target", "policy", "palettes", "texture_tokens", "primitives"):
        if key not in catalog:
            errors.append(f"missing top-level key: {key}")

    palettes = as_list(catalog.get("palettes"))
    palette_ids = [str(item.get("id")) for item in palettes if isinstance(item, dict)]
    if len(palette_ids) != len(set(palette_ids)):
        errors.append("palette ids must be unique")
    if not palette_ids:
        errors.append("palettes must not be empty")

    texture_tokens = as_list(catalog.get("texture_tokens"))
    token_ids = [str(item.get("token")) for item in texture_tokens if isinstance(item, dict)]
    if len(token_ids) != len(set(token_ids)):
        errors.append("texture tokens must be unique")
    for index, texture in enumerate(texture_tokens):
        if not isinstance(texture, dict):
            errors.append(f"texture_tokens[{index}] must be object")
            continue
        source_type = texture.get("source_type")
        if source_type not in {"procedural", "bundled_local"}:
            errors.append(f"texture_tokens[{index}].source_type is invalid: {source_type!r}")
        local_path = texture.get("local_path")
        if source_type == "bundled_local" and not local_path:
            errors.append(f"texture_tokens[{index}] bundled_local texture requires local_path")
        if isinstance(local_path, str) and (local_path.startswith("http://") or local_path.startswith("https://")):
            errors.append(f"texture_tokens[{index}].local_path must be local, not URL")
        license_name = str(texture.get("license", ""))
        if not license_name:
            errors.append(f"texture_tokens[{index}] missing license")

    primitives = as_list(catalog.get("primitives"))
    primitive_types = [str(item.get("type")) for item in primitives if isinstance(item, dict)]
    if set(primitive_types) != EXPECTED_PRIMITIVES:
        missing = sorted(EXPECTED_PRIMITIVES - set(primitive_types))
        extra = sorted(set(primitive_types) - EXPECTED_PRIMITIVES)
        if missing:
            errors.append(f"missing MVP primitive types: {', '.join(missing)}")
        if extra:
            errors.append(f"unexpected primitive types: {', '.join(extra)}")
    if len(primitive_types) != len(set(primitive_types)):
        errors.append("primitive types must be unique")

    palette_set = set(palette_ids)
    token_set = set(token_ids)
    for index, primitive in enumerate(primitives):
        if not isinstance(primitive, dict):
            errors.append(f"primitives[{index}] must be object")
            continue
        primitive_type = primitive.get("type")
        allowed_palettes = primitive.get("allowed_palettes")
        if not isinstance(allowed_palettes, list) or not allowed_palettes:
            errors.append(f"primitives[{index}] allowed_palettes must be non-empty")
        else:
            unknown_palettes = sorted(str(item) for item in allowed_palettes if str(item) not in palette_set)
            if unknown_palettes:
                errors.append(f"{primitive_type} references unknown palettes: {', '.join(unknown_palettes)}")
        texture_token = primitive.get("default_texture_token")
        if texture_token is not None and str(texture_token) not in token_set:
            errors.append(f"{primitive_type} references unknown default_texture_token: {texture_token}")
        budget = primitive.get("budget")
        if not isinstance(budget, dict) or not budget:
            errors.append(f"{primitive_type} budget must be non-empty object")
        params = primitive.get("default_params")
        if not isinstance(params, dict):
            errors.append(f"{primitive_type} default_params must be object")

    scan_forbidden(catalog, "", errors)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("catalog")
    args = parser.parse_args()

    data = load_json(Path(args.catalog))
    if not isinstance(data, dict):
        print("effect catalog root must be object")
        return 1
    errors = validate(data)
    if errors:
        print("INVALID EffectCatalog")
        for error in errors:
            print(f"- {error}")
        return 1
    print("OK EffectCatalog")
    print(f"- catalog: {args.catalog}")
    print(f"- primitives: {len(data.get('primitives', []))}")
    print(f"- texture_tokens: {len(data.get('texture_tokens', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
