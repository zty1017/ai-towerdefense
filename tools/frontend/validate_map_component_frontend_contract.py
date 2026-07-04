#!/usr/bin/env python3
"""Validate the map component media frontend boundary.

Map component media is reviewed presentation evidence for MapStylePack entries.
It may be served by the backend, but the player-default frontend must not load
or draw it until a separate runtime publication contract exists.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
APP_JS = ROOT / "frontend/app.js"
BACKEND_MAIN = ROOT / "backend/app/main.py"
MANIFEST = ROOT / "game_data/media/map_components/map_component_media_manifest.v0.1.json"

REQUIRED_USAGE_POLICY = {
    "review_gate_only",
    "not_runtime_semantic_source",
    "no_image_to_map_semantic_inference",
    "local_reviewed_component_only",
    "no_frontend_default_consumption",
    "no_provider_or_prompt_payload",
    "no_external_temporary_url",
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def validate_manifest(errors: list[str]) -> None:
    manifest = load_json(MANIFEST)
    require(
        manifest.get("schema_version") == "map_component_media_manifest.v0.1",
        "manifest schema_version must be map_component_media_manifest.v0.1",
        errors,
    )
    require(
        manifest.get("public_url_prefix") == "/assets/map_components",
        "manifest public_url_prefix must be /assets/map_components",
        errors,
    )
    usage_policy = set(map(str, manifest.get("usage_policy") or []))
    missing_policy = sorted(REQUIRED_USAGE_POLICY - usage_policy)
    require(
        not missing_policy,
        f"manifest usage_policy missing: {', '.join(missing_policy)}",
        errors,
    )
    items = [item for item in manifest.get("items", []) if isinstance(item, dict)]
    require(items, "manifest must contain reviewed map component items", errors)
    for index, item in enumerate(items):
        require(
            item.get("media_layer") == "reviewed_map_component_media",
            f"items[{index}].media_layer must be reviewed_map_component_media",
            errors,
        )
        require(
            item.get("source_kind") == "deterministic_developer_fixture_svg",
            f"items[{index}].source_kind must stay explicit fixture evidence",
            errors,
        )
        require(
            str(item.get("url") or "").startswith("/assets/map_components/processed/"),
            f"items[{index}].url must use /assets/map_components/processed/",
            errors,
        )
        require(
            str(item.get("local_path") or "").startswith(
                "game_data/media/map_components/processed/"
            ),
            f"items[{index}].local_path must stay under game_data/media/map_components/processed/",
            errors,
        )


def validate_backend_mount(errors: list[str]) -> None:
    source = BACKEND_MAIN.read_text(encoding="utf-8")
    require(
        '"map_components"' in source,
        "backend/app/main.py must register map_components static namespace",
        errors,
    )
    require(
        "game_data/media/map_components" in source,
        "backend/app/main.py map_components mount must point to game_data/media/map_components",
        errors,
    )
    require(
        'f"/assets/{namespace}"' in source or '"/assets/map_components"' in source,
        "backend must mount /assets/map_components",
        errors,
    )


def validate_frontend_default_non_consumption(errors: list[str]) -> None:
    source = APP_JS.read_text(encoding="utf-8")
    require(
        "/assets/map_components" not in source,
        "frontend/app.js must not default-load /assets/map_components assets",
        errors,
    )
    require(
        "map_component_media_manifest" not in source
        and "mapComponentMediaManifest" not in source,
        "frontend/app.js must not default-load MapComponentMediaManifest",
        errors,
    )
    forbidden_names = (
        "drawMapComponent",
        "loadMapComponent",
        "mapComponentImage",
        "styleComponentImage",
    )
    for name in forbidden_names:
        require(
            name not in source,
            f"frontend/app.js must not include player-default {name} flow",
            errors,
        )
    static_paths_match = re.search(r"const\s+STATIC_PATHS\s*=\s*\{(?P<body>.*?)\n\s*\};", source, re.S)
    if static_paths_match:
        body = static_paths_match.group("body")
        require(
            "mapComponent" not in body and "map_components" not in body,
            "STATIC_PATHS must not include map component media before publication",
            errors,
        )


def main() -> int:
    errors: list[str] = []
    validate_manifest(errors)
    validate_backend_mount(errors)
    validate_frontend_default_non_consumption(errors)

    if errors:
        print("INVALID MapComponentFrontendContract")
        for error in errors:
            print(f"- {error}")
        return 1

    print("OK MapComponentFrontendContract")
    print("- backend static mount: /assets/map_components")
    print("- frontend default consumption: disabled")
    print("- manifest usage: review-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
