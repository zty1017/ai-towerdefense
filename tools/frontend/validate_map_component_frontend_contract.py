#!/usr/bin/env python3
"""Validate the map component media frontend boundary.

Map component media is reviewed presentation evidence for MapStylePack entries.
The player-default frontend may load the v0.1 reviewed component manifest for
presentation stamps, but it must not treat those images as map semantic truth.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from report_io import load_json


ROOT = Path(__file__).resolve().parents[2]
APP_JS = ROOT / "frontend/app.js"
FRONTEND_RUNTIME = ROOT / "frontend/runtime"
BACKEND_MAIN = ROOT / "backend/app/main.py"
MANIFEST = ROOT / "game_data/media/map_components/map_component_media_manifest.v0.1.json"

REQUIRED_USAGE_POLICY = {
    "review_gate_only",
    "not_runtime_semantic_source",
    "no_image_to_map_semantic_inference",
    "local_reviewed_component_only",
    "frontend_default_presentation_allowed",
    "no_provider_or_prompt_payload",
    "no_external_temporary_url",
}

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


def validate_frontend_default_presentation_consumption(errors: list[str]) -> None:
    source = APP_JS.read_text(encoding="utf-8")
    frontend_source = "\n".join(
        [source]
        + [
            runtime_js.read_text(encoding="utf-8")
            for runtime_js in sorted(FRONTEND_RUNTIME.glob("*.js"))
        ]
    )
    require(
        "/assets/map_components" in frontend_source,
        "frontend app/runtime must resolve /assets/map_components assets for reviewed presentation components",
        errors,
    )
    require(
        "map_component_media_manifest" in frontend_source and "mapComponentManifest" in frontend_source,
        "frontend app/runtime must default-load MapComponentMediaManifest v0.1 for presentation components",
        errors,
    )
    required_names = (
        "mapComponentItems",
        "mapComponentPreloadUrls",
        "mapComponentImage",
        "drawComponentTextureEllipse",
    )
    for name in required_names:
        require(
            name in frontend_source,
            f"frontend app/runtime must include player-default presentation flow: {name}",
            errors,
        )
    require(
        "createFrontendMediaCatalog" in frontend_source
        and "getData" in frontend_source
        and "resolveAssetUrl" in frontend_source,
        "reviewed component lookup must pass through the injected frontend media catalog",
        errors,
    )
    for role in (
        "terrain_base",
        "road_band",
        "build_slot_platform",
        "objective_foundation",
        "spawn_marker",
        "resource_marker",
        "hazard_marker",
        "blocking_prop",
    ):
        require(
            f'"{role}"' in frontend_source,
            f"frontend app/runtime must consume reviewed component role for presentation: {role}",
            errors,
        )
    static_paths_match = re.search(
        r"const\s+STATIC_PATHS\s*=\s*\{(?P<body>.*?)\n\s*\};",
        frontend_source,
        re.S,
    )
    if static_paths_match:
        body = static_paths_match.group("body")
        require(
            "mapComponentManifest" in body and "map_components" in body,
            "STATIC_PATHS must include reviewed map component media manifest",
            errors,
        )
    semantic_forbidden = (
        "imageToMap",
        "inferMapFromImage",
        "reverseMapComponent",
        "componentToPath",
        "componentToCollision",
    )
    for name in semantic_forbidden:
        require(
            name not in frontend_source,
            f"frontend app/runtime must not include image-to-map semantic inference flow: {name}",
            errors,
        )


def main() -> int:
    errors: list[str] = []
    validate_manifest(errors)
    validate_backend_mount(errors)
    validate_frontend_default_presentation_consumption(errors)

    if errors:
        print("INVALID MapComponentFrontendContract")
        for error in errors:
            print(f"- {error}")
        return 1

    print("OK MapComponentFrontendContract")
    print("- backend static mount: /assets/map_components")
    print("- frontend default consumption: reviewed presentation components only")
    print("- manifest usage: presentation allowed, not runtime semantic source")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
