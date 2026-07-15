#!/usr/bin/env python3
"""Validate the LayeredMapVisualPackage frontend contract.

This is an offline structural check. Browser smoke tests still prove actual
rendering; this script prevents simple regressions such as dropping a node
manifest, removing the static mount, or bypassing MapRuntimePackage semantics.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from report_io import load_json


ROOT = Path(__file__).resolve().parents[2]
APP_JS = ROOT / "frontend/app.js"
FRONTEND_RUNTIME = ROOT / "frontend/runtime"
BACKEND_MAIN = ROOT / "backend/app/main.py"
NODE_MANIFESTS = {
    "gray_lantern_station": ROOT
    / "game_data/media/layered_maps/gray_lantern_station/layered_map_visual_package.v0.1.json",
    "lamp_wick_store": ROOT
    / "game_data/media/layered_maps/lamp_wick_store/layered_map_visual_package.v0.1.json",
    "old_signal_tower": ROOT
    / "game_data/media/layered_maps/old_signal_tower/layered_map_visual_package.v0.1.json",
}
REQUIRED_LAYER_ROLES = {
    "terrain_base",
    "terrain_detail",
    "road_shadow",
    "road_edge",
    "road_surface",
    "build_slots",
    "objectives",
    "spawn",
    "semantic_props",
    "non_blocking_decorations",
    "lighting",
    "fog_weather",
    "color_grade",
    "composited",
}
REQUIRED_MEDIA_ROLES = {
    "terrain_tile",
    "terrain_detail_tile",
    "road_tile",
    "road_edge_tile",
    "road_detail_atlas",
    "slot_tile",
    "shadow_overlay_tile",
    "fog_overlay_tile",
    "light_overlay_tile",
}
COMPONENT_MEDIA_ROLES = {
    "objective_foundation",
    "spawn_marker",
    "non_blocking_decoration",
}
OPTIONAL_MEDIA_ROLES = {"reviewed_painted_backdrop", *COMPONENT_MEDIA_ROLES}
REQUIRED_USAGE_POLICY = {
    "runtime_semantics_from_map_runtime_package",
    "visual_package_is_presentation_only",
    "no_pixel_to_semantic_inference",
    "player_default_presentation_allowed",
    "local_reviewed_artifact_only",
    "no_raw_generation_payload",
    "no_external_temporary_url",
    "painted_backdrop_must_not_bake_build_slots",
    "painted_backdrop_must_not_bake_path_routes",
}


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def validate_manifest(node_id: str, manifest_path: Path, errors: list[str]) -> None:
    require(manifest_path.exists(), f"{node_id} layered map manifest must exist", errors)
    if not manifest_path.exists():
        return
    manifest = load_json(manifest_path)
    require(
        manifest.get("schema_version") == "layered_map_visual_package.v0.1",
        f"{node_id} manifest schema_version must be layered_map_visual_package.v0.1",
        errors,
    )
    require(manifest.get("node_id") == node_id, f"{node_id} manifest node_id mismatch", errors)
    require(
        as_obj(manifest.get("runtime_semantics_source")).get("kind") == "MapRuntimePackage",
        f"{node_id} runtime semantics source must remain MapRuntimePackage",
        errors,
    )
    require(
        as_obj(manifest.get("runtime_semantics_source")).get("authority") == "runtime_semantic_truth",
        f"{node_id} runtime semantics authority must remain runtime_semantic_truth",
        errors,
    )
    usage_policy = set(map(str, as_list(manifest.get("usage_policy"))))
    missing_policy = sorted(REQUIRED_USAGE_POLICY - usage_policy)
    require(
        not missing_policy,
        f"{node_id} usage_policy missing: {', '.join(missing_policy)}",
        errors,
    )
    layers = [layer for layer in as_list(manifest.get("layers")) if isinstance(layer, dict)]
    roles = {str(layer.get("role")) for layer in layers}
    missing_roles = sorted(REQUIRED_LAYER_ROLES - roles)
    require(not missing_roles, f"{node_id} layers missing: {', '.join(missing_roles)}", errors)
    composited = [layer for layer in layers if layer.get("role") == "composited"]
    require(len(composited) == 1, f"{node_id} must contain exactly one composited layer", errors)
    for index, layer in enumerate(layers):
        url = str(layer.get("url") or "")
        local_path = str(layer.get("local_path") or "")
        quality = as_obj(layer.get("quality"))
        require(
            url.startswith("/assets/layered_maps/"),
            f"{node_id} layers[{index}].url must use /assets/layered_maps/",
            errors,
        )
        require(
            local_path.startswith("game_data/media/layered_maps/"),
            f"{node_id} layers[{index}].local_path must stay under game_data/media/layered_maps/",
            errors,
        )
        require(
            (ROOT / local_path).exists(),
            f"{node_id} layers[{index}].local_path must exist: {local_path}",
            errors,
        )
        if layer.get("player_default") is True:
            require(
                quality.get("gate_status") == "passed"
                and quality.get("alignment_status") == "passed"
                and quality.get("player_visible_quality") == "passed",
                f"{node_id} player_default layers[{index}] must pass gate/alignment/player quality",
                errors,
            )
    media_assets = [item for item in as_list(manifest.get("media_assets")) if isinstance(item, dict)]
    media_roles = {str(item.get("role")) for item in media_assets}
    missing_media = sorted(REQUIRED_MEDIA_ROLES - media_roles)
    require(not missing_media, f"{node_id} media_assets missing: {', '.join(missing_media)}", errors)
    for index, item in enumerate(media_assets):
        local_path = str(item.get("local_path") or "")
        role = str(item.get("role") or "")
        if role == "reviewed_painted_backdrop":
            expected_media_kind = "map_backdrop_png"
        elif role == "road_detail_atlas":
            expected_media_kind = "texture_atlas_png"
        elif role in COMPONENT_MEDIA_ROLES:
            expected_media_kind = "component_sprite_png"
        else:
            expected_media_kind = "texture_tile_png"
        if role == "reviewed_painted_backdrop":
            expected_usage = "presentation_backdrop_only"
        elif role in COMPONENT_MEDIA_ROLES:
            expected_usage = "presentation_component_only"
        else:
            expected_usage = "presentation_texture_only"
        require(
            item.get("media_kind") == expected_media_kind,
            f"{node_id} media_assets[{index}].media_kind must be {expected_media_kind}",
            errors,
        )
        require(
            item.get("usage") == expected_usage,
            f"{node_id} media_assets[{index}].usage must be {expected_usage}",
            errors,
        )
        source_kind = item.get("source_kind")
        require(
            source_kind
            in (
                None,
                "",
                "procedural_texture",
                "local_ai_exploration_texture",
                "local_ai_exploration_backdrop",
                "compiled_reviewed_texture",
                "compiled_reviewed_backdrop",
                "compiled_reviewed_component",
            ),
            f"{node_id} media_assets[{index}].source_kind must be controlled when present",
            errors,
        )
        require(
            role in REQUIRED_MEDIA_ROLES or role in OPTIONAL_MEDIA_ROLES,
            f"{node_id} media_assets[{index}].role must be supported: {role}",
            errors,
        )
        require(
            local_path.endswith(".png") and (ROOT / local_path).exists(),
            f"{node_id} media_assets[{index}].local_path must point to an existing PNG: {local_path}",
            errors,
        )


def validate_backend_mount(errors: list[str]) -> None:
    source = BACKEND_MAIN.read_text(encoding="utf-8")
    require(
        '"layered_maps"' in source,
        "backend/app/main.py must register layered_maps static namespace",
        errors,
    )
    require(
        "game_data/media/layered_maps" in source,
        "backend/app/main.py layered_maps mount must point to game_data/media/layered_maps",
        errors,
    )
    require(
        'f"/assets/{namespace}"' in source or '"/assets/layered_maps"' in source,
        "backend must mount /assets/layered_maps",
        errors,
    )


def validate_frontend_consumption(errors: list[str]) -> None:
    app_source = APP_JS.read_text(encoding="utf-8")
    frontend_source = "\n".join(
        [app_source]
        + [
            runtime_js.read_text(encoding="utf-8")
            for runtime_js in sorted(FRONTEND_RUNTIME.glob("*.js"))
        ]
    )
    require(
        "/assets/layered_maps" in frontend_source,
        "frontend app/runtime must resolve /assets/layered_maps assets",
        errors,
    )
    for node_id in NODE_MANIFESTS:
        require(
            f"/game_data/media/layered_maps/{node_id}/layered_map_visual_package.v0.1.json"
            in frontend_source,
            f"frontend app/runtime sources must include layeredMapVisualPackage for {node_id}",
            errors,
        )
    for name in (
        "layeredMapVisualPackage",
        "playerReadyLayeredMapLayer",
        "layeredMapVisualLayer",
        "layeredMapVisualUrl",
        "layeredMapBackdropImage",
        "layeredMapVisualPreloadUrls",
        "drawLayeredMapBackdrop",
    ):
        require(
            f"function {name}" in frontend_source,
            f"frontend app/runtime must include LayeredMapVisualPackage flow: {name}",
            errors,
        )
    require(
        "const layeredBackdrop = drawLayeredMapBackdrop(ctx, metrics)" in frontend_source,
        "drawBackdrop must attempt layered map before procedural fallback",
        errors,
    )
    require(
        "if (!layeredBackdrop) drawProceduralTerrain(ctx, metrics)" in frontend_source,
        "drawBackdrop must retain procedural fallback for missing/invalid layered package",
        errors,
    )
    require(
        "drawBuildableTerraces(ctx)" in frontend_source and "if (!layeredBackdrop)" in frontend_source,
        "drawBattle must avoid duplicating baked build slots when layered backdrop is active",
        errors,
    )
    require(
        "if (!layeredBackdrop) drawBattlefieldLandmarks(ctx)" in frontend_source,
        "battle renderer must avoid duplicating reviewed non-blocking decorations",
        errors,
    )
    require(
        "if (!layeredBackdrop) drawSpawnMarkers(ctx)" in frontend_source,
        "battle renderer must avoid duplicating reviewed spawn markers",
        errors,
    )
    require(
        "if (!layeredBackdrop) {" in frontend_source
        and "drawTargetFoundation(ctx" in frontend_source,
        "battle renderer must avoid duplicating reviewed objective components",
        errors,
    )
    forbidden = (
        "inferMapFromLayeredImage",
        "layeredMapToCollision",
        "imageToMapRuntimePackage",
        "pixelToBuildSlot",
    )
    for name in forbidden:
        require(
            name not in frontend_source,
            f"frontend/app.js must not infer map semantics from layered images: {name}",
            errors,
        )


def main() -> int:
    errors: list[str] = []
    for node_id, manifest_path in NODE_MANIFESTS.items():
        validate_manifest(node_id, manifest_path, errors)
    validate_backend_mount(errors)
    validate_frontend_consumption(errors)

    if errors:
        print("INVALID LayeredMapFrontendContract")
        for error in errors:
            print(f"- {error}")
        return 1

    print("OK LayeredMapFrontendContract")
    print(f"- node manifests: {len(NODE_MANIFESTS)}")
    print("- backend static mount: /assets/layered_maps")
    print("- frontend default consumption: composited presentation layer first")
    print("- runtime semantics: MapRuntimePackage remains authoritative")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
