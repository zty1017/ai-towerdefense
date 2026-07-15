#!/usr/bin/env python3
"""Validate strategic map marker media frontend boundary."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from report_io import load_json


ROOT = Path(__file__).resolve().parents[2]
APP_JS = ROOT / "frontend/app.js"
FRONTEND_RUNTIME = ROOT / "frontend/runtime"
BACKEND_MAIN = ROOT / "backend/app/main.py"
MANIFEST = ROOT / "game_data/media/strategic_map_markers/strategic_map_marker_media_manifest.v0.1.json"

REQUIRED_USAGE_POLICY = {
    "review_gate_only",
    "not_runtime_semantic_source",
    "no_image_to_map_semantic_inference",
    "local_reviewed_marker_only",
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
        manifest.get("schema_version") == "strategic_map_marker_media_manifest.v0.1",
        "manifest schema_version must be strategic_map_marker_media_manifest.v0.1",
        errors,
    )
    require(
        manifest.get("public_url_prefix") == "/assets/strategic_map_markers",
        "manifest public_url_prefix must be /assets/strategic_map_markers",
        errors,
    )
    usage_policy = set(map(str, manifest.get("usage_policy") or []))
    missing_policy = sorted(REQUIRED_USAGE_POLICY - usage_policy)
    require(not missing_policy, f"manifest usage_policy missing: {', '.join(missing_policy)}", errors)

    atlas = manifest.get("atlas") if isinstance(manifest.get("atlas"), dict) else {}
    require(
        str(atlas.get("url") or "").startswith("/assets/strategic_map_markers/processed/"),
        "manifest atlas.url must use /assets/strategic_map_markers/processed/",
        errors,
    )
    require(
        str(atlas.get("local_path") or "").startswith(
            "game_data/media/strategic_map_markers/processed/"
        ),
        "manifest atlas.local_path must stay under game_data/media/strategic_map_markers/processed/",
        errors,
    )

    items = [item for item in manifest.get("items", []) if isinstance(item, dict)]
    require(items, "manifest must contain reviewed strategic marker items", errors)
    kinds = {str(item.get("node_kind") or "") for item in items}
    for kind in ("main_city", "battle_hotspot", "research_facility", "resource_storage", "generic"):
        require(kind in kinds, f"manifest must contain strategic marker kind: {kind}", errors)
    for index, item in enumerate(items):
        require(
            item.get("media_layer") == "reviewed_strategic_map_marker_media",
            f"items[{index}].media_layer must be reviewed_strategic_map_marker_media",
            errors,
        )
        require(
            item.get("source_kind") == "deterministic_developer_fixture_png_atlas",
            f"items[{index}].source_kind must stay explicit fixture atlas evidence",
            errors,
        )
        frame = item.get("atlas_frame") if isinstance(item.get("atlas_frame"), dict) else {}
        for key in ("x", "y", "width", "height", "anchor_x", "anchor_y"):
            require(key in frame, f"items[{index}].atlas_frame missing {key}", errors)


def validate_backend_mount(errors: list[str]) -> None:
    source = BACKEND_MAIN.read_text(encoding="utf-8")
    require(
        '"strategic_map_markers"' in source,
        "backend/app/main.py must register strategic_map_markers static namespace",
        errors,
    )
    require(
        "game_data/media/strategic_map_markers" in source,
        "backend/app/main.py strategic_map_markers mount must point to game_data/media/strategic_map_markers",
        errors,
    )


def validate_frontend_consumption(errors: list[str]) -> None:
    source = APP_JS.read_text(encoding="utf-8")
    frontend_source = "\n".join(
        [source]
        + [
            runtime_js.read_text(encoding="utf-8")
            for runtime_js in sorted(FRONTEND_RUNTIME.glob("*.js"))
        ]
    )
    for token in (
        "strategicMapMarkerManifest",
        "/assets/strategic_map_markers",
        "strategicMarkerManifest",
        "strategicMarkerAtlas",
        "strategicMarkerItem",
        "strategicNodeMarkerMarkup",
        "strategic-node-marker--atlas",
    ):
        require(
            token in frontend_source,
            f"frontend app/runtime must include strategic marker atlas flow: {token}",
            errors,
        )
    require(
        "strategicNodeGlyph(node, color, stateName)" in source,
        "frontend/app.js should keep SVG marker fallback for missing manifest",
        errors,
    )
    for forbidden in (
        "imageToMap",
        "markerToMapSemantic",
        "inferNodeFromMarker",
        "markerToSupplyLine",
    ):
        require(
            forbidden not in frontend_source,
            f"frontend app/runtime must not infer strategic map semantics from marker media: {forbidden}",
            errors,
        )


def main() -> int:
    errors: list[str] = []
    validate_manifest(errors)
    validate_backend_mount(errors)
    validate_frontend_consumption(errors)

    if errors:
        print("INVALID StrategicMapMarkerFrontendContract")
        for error in errors:
            print(f"- {error}")
        return 1

    print("OK StrategicMapMarkerFrontendContract")
    print("- backend static mount: /assets/strategic_map_markers")
    print("- frontend default consumption: reviewed strategic marker atlas")
    print("- runtime semantics: map JSON remains authoritative")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
