#!/usr/bin/env python3
"""Validate battle-screen visual contracts without a browser.

This is not a screenshot test. It catches regressions that made earlier MVP
builds look like debug tools: control maps leaking into player view, missing
painted map layers, and battle canvas layouts that collapse into a small panel.
"""

from __future__ import annotations

import argparse
import re
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from report_io import load_json, write_json


ROOT = Path(__file__).resolve().parents[2]
APP_JS = ROOT / "frontend/app.js"
STYLES_CSS = ROOT / "frontend/styles.css"
MAP_MANIFEST = ROOT / "game_data/media/map_visual_reference/map_visual_reference_manifest.v0.1.json"
MAP_RUNTIME_PACKAGES = sorted((ROOT / "examples/map_runtime_packages").glob("*.map_runtime_package.json"))
MAP_RUNTIME_PACKAGES_V02 = sorted(
    (ROOT / "examples/map_runtime_packages_v02").glob("*.map_runtime_package_v02.json")
)

def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG file")
    return struct.unpack(">II", header[16:24])


def css_block(css: str, selector: str) -> str:
    match = re.search(rf"{re.escape(selector)}\s*\{{(?P<body>.*?)\n\}}", css, re.S)
    return match.group("body") if match else ""


def css_blocks(css: str, selector: str) -> list[str]:
    return [
        match.group("body")
        for match in re.finditer(rf"{re.escape(selector)}\s*\{{(?P<body>.*?)\n\}}", css, re.S)
    ]


def js_section(source: str, start_name: str, end_name: str | None = None) -> str:
    start = source.find(f"function {start_name}")
    if start < 0:
        return ""
    if end_name:
        end = source.find(f"\n  function {end_name}", start + 1)
        if end > start:
            return source[start:end]
    next_match = re.search(r"\n  function\s+\w+", source[start + 1 :])
    if next_match:
        return source[start : start + 1 + next_match.start()]
    return source[start:]


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def validate_app_contract(errors: list[str]) -> None:
    app = APP_JS.read_text(encoding="utf-8")
    preload = js_section(app, "preloadBattleImages", "resizeBattleCanvas")
    backdrop = js_section(app, "drawBackdrop", "drawProceduralTerrain")
    path = js_section(app, "drawPath", "traceRoutePath")
    profile = js_section(app, "battleNodeVisualProfile", "terrainFeatureSet")
    metrics = js_section(app, "computeBattleMetrics", "battleCanvasSafeArea")
    spawn = js_section(app, "spawnEnemies", "updateEnemies")
    update_enemies = js_section(app, "updateEnemies", "updateDefenses")
    deploy = js_section(app, "drawDeployHints", "drawDeploymentBase")
    build_terrace = js_section(app, "drawBuildableTerrace", "drawDeployHints")
    deploy_base = js_section(app, "drawDeploymentBase", "suggestedSockets")
    spawn_markers = js_section(app, "drawSpawnMarkers", "drawSpawnRift")
    strong_semantics = js_section(app, "drawMapRuntimeStrongSemantics", "drawWorldObjects")

    for name in (
        "battleNodeVisualProfile",
        "terrainFeatureSet",
        "drawProceduralTerrain",
        "drawScenicBackplate",
        "drawTerrainDepthBands",
        "drawPlayableFieldBoundary",
        "drawFieldEdgeBreakup",
        "drawDarkTidePools",
        "drawBuildableTerraces",
        "battleCanvasSafeArea",
        "battleFitBounds",
        "drawRouteShoulders",
        "drawRoadTerrainBlend",
        "drawRoadPebbles",
        "drawRoadRuts",
        "drawRouteFlowCues",
        "drawRouteEdgeProps",
        "drawSlotAccessTrails",
        "drawBattlefieldLandmarks",
        "drawObjectiveDefensiveZone",
        "drawDeploymentBase",
        "drawPlatformGroundStitch",
        "drawTargetFoundation",
        "drawSpawnRift",
        "mapRenderPlanBundle",
        "mapRenderPlan",
        "mapRenderPlanLayer",
        "mapRenderPlanOperation",
        "renderGeometryNumber",
        "routeRoadWidthCells",
        "routeShoulderWidthScale",
        "buildSlotPlatformOperation",
        "slotFootprintScale",
        "mapStylePack",
        "mapStylePalette",
        "colorFromStyle",
        "rgbaFromStyle",
        "mapRenderPlanHasLayer",
        "mapResourceNodes",
        "mapHazardZones",
        "mapDefenseAnchors",
        "mapBlockedAreas",
        "routePointAtT",
        "routeSamplesBetween",
        "drawMapRuntimeStrongSemantics",
        "drawMapResourceNodes",
        "drawMapHazardZones",
        "drawMapDefenseAnchors",
        "drawMapBlockedAreas",
    ):
        require(f"function {name}" in app, f"missing {name}() procedural battle layer", errors)

    require("playerBattleMapVisualUrl()" not in preload, "default preload must not fetch whole-map player images", errors)
    require('"map-v02-preview"' not in app, "default frontend must not fetch review-only v0.2 preview endpoint", errors)
    require(
        '"map-v02-opt-in-dry-run"' not in app,
        "default frontend must not fetch review-only v0.2 opt-in dry-run endpoint",
        errors,
    )
    require("drawProceduralTerrain(ctx, m)" in backdrop, "drawBackdrop must start from procedural terrain", errors)
    require("drawMapDebugOverlay(ctx, m)" in backdrop, "debug map overlay must be isolated behind its own helper", errors)
    require("playerBattleMapVisualUrl" not in backdrop, "drawBackdrop must not draw whole-map player images by default", errors)
    require("drawScenicBackplate(ctx, m, features)" in app, "procedural terrain must render scenic world backplate outside the playable field", errors)
    require("drawPlayableFieldBoundary(ctx, m)" in app, "procedural terrain must render a playable field boundary", errors)
    require("drawFieldEdgeBreakup(ctx, m, features)" in app, "procedural terrain must break up the playable-field edge with diegetic props", errors)
    require("drawDarkTidePools" in app, "procedural terrain must include world-space dark tide pools", errors)
    require("drawBuildableTerraces(ctx)" in app, "battle view must render buildable terraces below deployment bases", errors)
    require("battleFitBounds(baseTileW, baseTileH)" in metrics, "battle metrics must fit runtime map bounds, not only cover the viewport", errors)
    require("battleCanvasSafeArea(width, height)" in metrics, "battle metrics must reserve HUD safe area", errors)
    require("drawRouteShoulders" in path, "drawPath must render terrain shoulders around roads", errors)
    require("drawRoadTerrainBlend(ctx, route, points, roadWidth)" in path, "drawPath must blend roads into terrain before drawing the readable road band", errors)
    require("drawRoadPebbles" in path, "drawPath must render textured world road details", errors)
    require("drawRoadRuts" in path, "drawPath must render road ruts or plank details", errors)
    require("drawRouteFlowCues" in path, "drawPath must render subtle route direction cues", errors)
    require("drawRouteEdgeProps" in path, "drawPath must integrate world props along road edges", errors)
    require("setLineDash" not in path, "drawPath must not render dashed control lines", errors)
    require("const road = profile.road || {}" in path, "drawPath must consume map style road colors when available", errors)
    require("road.base" in path and "road.crown" in path, "drawPath must map StylePack road colors onto player roads", errors)
    require("routeRoadWidthCells(route)" in path, "drawPath must consume RenderPlan road width geometry", errors)
    require('"width_cells"' in app, "frontend must read road_band geometry.width_cells from RenderPlan", errors)
    require("routeShoulderWidthScale(route)" in app, "route shoulders must consume RenderPlan road_edge shoulder geometry", errors)
    require('"shoulder_width_cells"' in app, "frontend must read road_edge geometry.shoulder_width_cells from RenderPlan", errors)
    require("drawSlotAccessTrails(ctx)" in app, "battle view must visually connect deployment bases to runtime roads", errors)
    require(
        "drawMapRuntimeStrongSemantics(ctx)" in app,
        "battle view must render v0.2 strong semantics when present in MapRuntimePackage",
        errors,
    )
    require("mapRuntimePackage().resource_nodes" in app, "resource_nodes must be read only from MapRuntimePackage", errors)
    require("mapRuntimePackage().hazard_zones" in app, "hazard_zones must be read only from MapRuntimePackage", errors)
    require("mapRuntimePackage().defense_anchors" in app, "defense_anchors must be read only from MapRuntimePackage", errors)
    require("mapRuntimePackage().blocked_areas" in app, "blocked_areas must be read only from MapRuntimePackage", errors)
    require(
        "drawMapBlockedAreas(ctx)" in strong_semantics,
        "strong semantic layer must draw blocked areas before gameplay entities",
        errors,
    )
    require(
        "drawMapHazardZones(ctx)" in strong_semantics,
        "strong semantic layer must draw hazard zones from runtime fields",
        errors,
    )
    require(
        "drawMapResourceNodes(ctx)" in strong_semantics,
        "strong semantic layer must draw resource nodes from runtime fields",
        errors,
    )
    require(
        "drawMapDefenseAnchors(ctx)" in strong_semantics,
        "strong semantic layer must draw defense anchors from runtime fields",
        errors,
    )
    require("zone.anchor_route_id" in strong_semantics, "hazard zones must bind to runtime route ids", errors)
    require(
        "zone.path_t_range" in strong_semantics and "routeSamplesBetween(route" in app,
        "hazard zones must render route-t ranges, not image-derived masks",
        errors,
    )
    require(
        "area.cells" in strong_semantics and "drawCollapsedWall(ctx" in strong_semantics,
        "blocked areas must render from structured cells",
        errors,
    )
    require("node.position" in strong_semantics, "resource nodes must render from structured positions", errors)
    require("anchor.position" in strong_semantics, "defense anchors must render from structured positions", errors)
    require("drawBattlefieldLandmarks(ctx)" in app, "battle view must render world-space landmarks", errors)
    require("drawObjectiveDefensiveZone(ctx" in app, "battle view must ground objectives in a defense zone", errors)
    require("drawDeploymentBase" in deploy, "deploy hints must render world-space deployment bases", errors)
    require("drawPlatformGroundStitch" in build_terrace, "buildable terraces must stitch platforms into surrounding terrain", errors)
    require("drawSpawnRift" in spawn_markers, "spawn markers must render ambient entry effects, not arrows", errors)
    require("slotFootprintScale(slot" in build_terrace, "buildable terraces must consume RenderPlan slot footprint", errors)
    require("slotFootprintScale(slot" in deploy_base, "deployment bases must consume RenderPlan slot footprint", errors)
    require("geometry.footprint" in app and '"width_cells"' in app and '"height_cells"' in app, "frontend must read build_slot_platform footprint geometry from RenderPlan", errors)
    require('schema_version !== "map_style_pack.v0.1"' in profile, "battle visual profile must gate StylePack schema version", errors)
    require("renderPlanLayersReady" in profile, "battle visual profile must expose render plan layer readiness", errors)
    require('mapRenderPlanHasLayer("road_band")' in profile, "battle visual profile must require road_band layer readiness", errors)
    require('mapRenderPlanHasLayer("build_slot_platform")' in profile, "battle visual profile must require build_slot_platform layer readiness", errors)
    require('mapRenderPlanHasLayer("objective_foundation")' in profile, "battle visual profile must require objective_foundation layer readiness", errors)
    require('mapRenderPlanHasLayer("spawn_atmosphere")' in profile, "battle visual profile must require spawn_atmosphere layer readiness", errors)
    require("battleNodeVisualProfile().platform" in app, "deployment bases must consume StylePack platform colors", errors)
    require("battleNodeVisualProfile().objective" in app, "target foundations must consume StylePack objective colors", errors)
    require("battleNodeVisualProfile().spawn" in app, "spawn effects must consume StylePack spawn colors", errors)
    require("function drawGrid" not in app and "function drawDiamond" not in app, "battle view must not keep checkerboard/grid drawing helpers", errors)
    require("routeForSpawn(battle.spawned)" in spawn, "enemy spawn must bind to runtime route/spawn ids", errors)
    require("enemyWaypoints(enemy)" in update_enemies, "enemy movement must use the enemy route, not only the first path", errors)

    debug = re.search(r"function\s+debugBattleMapVisualUrls\(\)\s*\{(?P<body>.*?)\n\s*\}", app, re.S)
    require(debug is not None, "missing debugBattleMapVisualUrls()", errors)
    if debug:
        body = debug.group("body")
        require("allowsDebugMapVisuals()" in body, "debug map visuals must be gated by query params", errors)
        require("battle_reference_board" in body and "battle_control_sketch" in body, "debug map visuals should expose reference/control layers only in debug", errors)


def validate_css_contract(errors: list[str]) -> None:
    css = STYLES_CSS.read_text(encoding="utf-8")
    battle_screen = css_block(css, ".battle-screen")
    battle_stage = css_block(css, ".battle-stage")
    battle_canvas = css_block(css, "#battleCanvas")
    battle_tools_blocks = css_blocks(css, ".battle-tools")
    battle_tools = next((block for block in battle_tools_blocks if "position: absolute" in block), battle_tools_blocks[0] if battle_tools_blocks else "")
    battle_side = css_block(css, ".battle-side")

    require("height: 100vh" in battle_screen, ".battle-screen must fill the viewport height", errors)
    require("overflow: hidden" in battle_screen, ".battle-screen must not scroll like a dashboard page", errors)
    require("inset: 0" in battle_stage, ".battle-stage must cover the battle shell", errors)
    require("width: 100%" in battle_canvas and "height: 100%" in battle_canvas, "#battleCanvas must fill battle stage", errors)
    require("bottom: 12px" in battle_tools or "bottom: 10px" in battle_tools, ".battle-tools should stay low and avoid the main battlefield", errors)

    width_match = re.search(r"width:\s*(\d+)px", battle_side)
    require(width_match is not None, ".battle-side width must be explicit and auditable", errors)
    if width_match:
        require(int(width_match.group(1)) <= 220, ".battle-side is too wide for player-first battle view", errors)


def validate_map_layers(errors: list[str]) -> None:
    manifest = load_json(MAP_MANIFEST)
    items = manifest.get("items", [])
    by_role = {item.get("role"): item for item in items if isinstance(item, dict)}

    def is_player_ready(item: dict | None) -> bool:
        return bool(
            item
            and item.get("authority") == "published_visual_layer"
            and item.get("player_visible_quality") == "passed"
        )

    def validate_player_candidate(item: dict | None, label: str) -> None:
        if not item:
            return
        authority = item.get("authority")
        quality = item.get("player_visible_quality")
        if authority == "published_visual_layer":
            require(quality == "passed", f"{label} published layer must have player_visible_quality=passed", errors)
        if quality == "passed":
            require(authority == "published_visual_layer", f"{label} passed visual quality must be published", errors)
        if quality == "failed":
            require(authority != "published_visual_layer", f"{label} failed visual quality must not be published", errors)
        local_path = ROOT / str(item.get("local_path", ""))
        require(local_path.exists(), f"visual layer file missing: {local_path}", errors)
        if local_path.exists():
            width, height = png_dimensions(local_path)
            require(width == item.get("width") and height == item.get("height"), f"{label} manifest dimensions do not match PNG header", errors)
            require(width / height > 1.65 and width / height < 1.85, f"{label} must be a wide battle-map image", errors)

    for role in ("battle_control_sketch", "battle_reference_board"):
        item = by_role.get(role)
        require(item is not None, f"missing {role} in map visual manifest", errors)
        if item:
            require(item.get("authority") == "reference_only", f"{role} must stay reference_only", errors)

    painted = by_role.get("painted_visual_layer")
    runtime = by_role.get("battle_runtime_background")
    require(painted is not None, "missing painted_visual_layer in map visual manifest", errors)
    require(runtime is not None, "missing battle_runtime_background fallback in map visual manifest", errors)
    validate_player_candidate(painted, "painted_visual_layer")
    validate_player_candidate(runtime, "battle_runtime_background")
    for item in items:
        if isinstance(item, dict) and item.get("role") not in {"strategic_control_sketch", "battle_control_sketch", "battle_reference_board"}:
            validate_player_candidate(item, str(item.get("role") or "visual_layer"))

    require(MAP_RUNTIME_PACKAGES, "no map runtime packages found", errors)
    for package_path in MAP_RUNTIME_PACKAGES:
        package = load_json(package_path)
        grid = package.get("grid") or {}
        require(grid.get("width_cells") and grid.get("height_cells"), f"{package_path.name} missing runtime grid", errors)
        require(package.get("path_routes"), f"{package_path.name} missing path_routes", errors)
        require(package.get("build_slots"), f"{package_path.name} missing build_slots", errors)
        require((package.get("objectives") or {}).get("core_target"), f"{package_path.name} missing core objective", errors)
        require(package.get("spawn_points"), f"{package_path.name} missing spawn_points", errors)
        layers = package.get("visual_layers", [])
        roles = {layer.get("role"): layer for layer in layers if isinstance(layer, dict)}
        require("painted_visual_layer" in roles, f"{package_path.name} missing painted_visual_layer", errors)
        require("battle_runtime_background" in roles, f"{package_path.name} missing battle_runtime_background", errors)
        validate_player_candidate(roles.get("painted_visual_layer"), f"{package_path.name} painted_visual_layer")
        validate_player_candidate(roles.get("battle_runtime_background"), f"{package_path.name} battle_runtime_background")
        for layer in layers:
            if isinstance(layer, dict):
                validate_player_candidate(layer, f"{package_path.name} {layer.get('role') or 'visual_layer'}")
        for role in ("battle_control_sketch", "battle_reference_board"):
            layer = roles.get(role)
            require(layer is not None and layer.get("authority") == "reference_only", f"{package_path.name} {role} must stay reference_only", errors)

    require(MAP_RUNTIME_PACKAGES_V02, "no map runtime v0.2 preview packages found", errors)
    for package_path in MAP_RUNTIME_PACKAGES_V02:
        package = load_json(package_path)
        require(
            package.get("schema_version") == "map_runtime_package.v0.2",
            f"{package_path.name} must be v0.2 schema",
            errors,
        )
        for key in ("resource_nodes", "hazard_zones", "defense_anchors", "blocked_areas"):
            value = package.get(key)
            require(
                isinstance(value, list) and bool(value),
                f"{package_path.name} missing v0.2 strong semantic field {key}",
                errors,
            )


def build_report(generated_at: str) -> dict[str, Any]:
    app_errors: list[str] = []
    css_errors: list[str] = []
    map_errors: list[str] = []
    validate_app_contract(app_errors)
    validate_css_contract(css_errors)
    validate_map_layers(map_errors)
    errors = app_errors + css_errors + map_errors
    status = "passed" if not errors else "failed"
    source_files = [
        APP_JS,
        STYLES_CSS,
        MAP_MANIFEST,
        *MAP_RUNTIME_PACKAGES,
        *MAP_RUNTIME_PACKAGES_V02,
    ]
    return {
        "schema_version": "battle_visual_contract_report.v0.1",
        "report_id": "battle_visual_contract_report_v0_1",
        "generated_at": generated_at,
        "status": status,
        "summary": {
            "app_contract_error_count": len(app_errors),
            "css_contract_error_count": len(css_errors),
            "map_layer_error_count": len(map_errors),
            "error_count": len(errors),
            "map_runtime_package_count": len(MAP_RUNTIME_PACKAGES),
            "map_runtime_v02_preview_package_count": len(MAP_RUNTIME_PACKAGES_V02),
            "source_file_count": len(source_files),
        },
        "contract_claims": {
            "default_battle_backdrop": "MapRuntimePackage-driven procedural terrain",
            "full_screen_battle_canvas": True,
            "no_default_whole_map_image_preload": True,
            "no_default_control_or_reference_map": True,
            "no_checkerboard_or_dashed_control_path": True,
            "runtime_semantics_source": "MapRuntimePackage",
            "style_source": "MapStylePack and ProceduralMapRenderPlan presentation geometry",
            "v02_strong_semantics_source": "activated MapRuntimePackage v0.2 runtime fields only",
            "review_only_v02_endpoints_isolated": True,
        },
        "safety_summary": {
            "reads_env_file": False,
            "provider_call_count": 0,
            "stores_prompt_body": False,
            "stores_provider_body": False,
            "world_mutation_count": 0,
            "runtime_mutation_count": 0,
            "default_runtime_v02_fetch_allowed": False,
        },
        "error_groups": {
            "app_contract": app_errors,
            "css_contract": css_errors,
            "map_layers": map_errors,
        },
        "source_files": [
            {
                "path": rel(path),
                "exists": path.exists(),
            }
            for path in source_files
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-output", type=Path)
    parser.add_argument("--generated-at", default=now_iso())
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args.generated_at)
    errors = (
        report["error_groups"]["app_contract"]
        + report["error_groups"]["css_contract"]
        + report["error_groups"]["map_layers"]
    )
    if args.report_output:
        write_json(args.report_output, report)

    if errors:
        print("INVALID battle visual contract")
        for error in errors:
            print(f"- {error}")
        return 1

    print("OK battle visual contract")
    print(f"- map runtime packages: {len(MAP_RUNTIME_PACKAGES)}")
    print(f"- map runtime v0.2 preview packages: {len(MAP_RUNTIME_PACKAGES_V02)}")
    print("- default battle backdrop: MapRuntimePackage-driven procedural terrain")
    print("- map style: optional MapRenderPlan geometry and StylePack colors, runtime semantics stay in MapRuntimePackage")
    print("- v0.2 strong semantics: consumed from activated runtime package only; review-only endpoints stay isolated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
