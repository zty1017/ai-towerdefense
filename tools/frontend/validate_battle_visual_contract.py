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
RUNTIME_JS_DIR = ROOT / "frontend/runtime"
RUNTIME_JS_FILES = sorted(RUNTIME_JS_DIR.glob("*.js"))
STYLES_CSS = ROOT / "frontend/styles.css"
MAP_MANIFEST = ROOT / "game_data/media/map_visual_reference/map_visual_reference_manifest.v0.1.json"
LAYERED_MAP_MANIFESTS = sorted(
    (ROOT / "game_data/media/layered_maps").glob("*/layered_map_visual_package.v0.1.json")
)
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


def frontend_js_files() -> list[Path]:
    return [APP_JS, *RUNTIME_JS_FILES]


def read_frontend_sources() -> dict[Path, str]:
    return {path: path.read_text(encoding="utf-8") for path in frontend_js_files()}


def frontend_source_bundle(sources: dict[Path, str]) -> str:
    return "\n\n".join(
        f"/* frontend source: {rel(path)} */\n{source}" for path, source in sources.items()
    )


def runtime_module_sources(sources: dict[Path, str]) -> dict[str, str]:
    return {path.name: source for path, source in sources.items() if path.parent == RUNTIME_JS_DIR}


def frontend_source_bundle_report(sources: dict[Path, str]) -> dict[str, Any]:
    runtime_paths = [path for path in sources if path.parent == RUNTIME_JS_DIR]
    return {
        "entrypoint": rel(APP_JS),
        "source_file_count": len(sources),
        "source_files": [rel(path) for path in sources],
        "runtime_source_file_count": len(runtime_paths),
        "runtime_source_files": [rel(path) for path in runtime_paths],
    }


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
    start_match = re.search(
        rf"(?m)^[ \t]*(?:export\s+)?(?:async\s+)?function\s+{re.escape(start_name)}\s*\(",
        source,
    )
    if not start_match:
        return ""
    start = start_match.start()
    if end_name:
        end_match = re.search(
            rf"(?m)^[ \t]*(?:export\s+)?(?:async\s+)?function\s+{re.escape(end_name)}\s*\(",
            source[start + 1 :],
        )
        if end_match:
            return source[start : start + 1 + end_match.start()]
    search_start = start_match.end()
    next_match = re.search(r"(?m)^[ \t]*(?:export\s+)?(?:async\s+)?function\s+\w+\s*\(", source[search_start:])
    if next_match:
        return source[start : search_start + next_match.start()]
    return source[start:]


def has_named_export(source: str, name: str) -> bool:
    escaped = re.escape(name)
    return bool(
        re.search(rf"(?m)^[ \t]*export\s+(?:async\s+)?function\s+{escaped}\s*\(", source)
        or re.search(rf"(?s)\bexport\s*\{{[^}}]*\b{escaped}\b[^}}]*\}}", source)
    )


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def contains_in_order(source: str, tokens: list[str]) -> bool:
    cursor = 0
    for token in tokens:
        index = source.find(token, cursor)
        if index < 0:
            return False
        cursor = index + len(token)
    return True


def validate_runtime_module_contract(runtime_sources: dict[str, str], errors: list[str]) -> None:
    battle_rules = runtime_sources.get("battle-rules.js", "")
    battle_actions = runtime_sources.get("battle-actions.js", "")
    app_flow_orchestrator = runtime_sources.get("app-flow-orchestrator.js", "")
    battle_map_adapter = runtime_sources.get("battle-map-adapter.js", "")
    battle_dom_controller = runtime_sources.get("battle-dom-controller.js", "")
    battle_renderer = runtime_sources.get("battle-renderer.js", "")
    battle_entity_renderer = runtime_sources.get("battle-entity-renderer.js", "")
    battle_deployment_renderer = runtime_sources.get("battle-deployment-renderer.js", "")
    battle_road_renderer = runtime_sources.get("battle-road-renderer.js", "")
    battle_semantic_renderer = runtime_sources.get("battle-semantic-renderer.js", "")
    battle_terrain_renderer = runtime_sources.get("battle-terrain-renderer.js", "")
    battle_world_renderer = runtime_sources.get("battle-world-renderer.js", "")
    battle_simulation = runtime_sources.get("battle-simulation.js", "")
    battle_orchestrator = runtime_sources.get("battle-orchestrator.js", "")
    battle_hud = runtime_sources.get("battle-hud-view-model.js", "")
    frontend_media_catalog = runtime_sources.get("frontend-media-catalog.js", "")
    feature_gates = runtime_sources.get("feature-gates.js", "")
    onboarding_feature_controller = runtime_sources.get("onboarding-feature-controller.js", "")
    workshop_feature_controller = runtime_sources.get("workshop-feature-controller.js", "")
    settlement_feature_controller = runtime_sources.get("settlement-feature-controller.js", "")
    strategic_map_feature_controller = runtime_sources.get("strategic-map-feature-controller.js", "")
    strategic_map_projection = runtime_sources.get("strategic-map-projection.js", "")
    map_runtime_accessors = runtime_sources.get("map-runtime-accessors.js", "")
    projection_adapter = runtime_sources.get("runtime-projection-adapter.js", "")
    battle_rule_exports = [
        "createBattleStateFactory",
        "canPlaceToolAt",
        "toolReady",
        "buildSpawnSchedule",
    ]
    battle_action_exports = [
        "toolUnavailableText",
        "placeBasicDefense",
        "placeSampleTrap",
        "useSupportPulse",
        "canPreviewRuntimeToolAt",
        "deployRuntimeTool",
    ]
    battle_map_adapter_exports = ["createBattleMapAdapter"]
    battle_dom_controller_exports = ["createBattleDomController"]
    battle_simulation_exports = [
        "advanceBattleStep",
        "spawnEnemies",
        "updateEnemies",
        "updateDefenses",
        "updateTraps",
        "nearestEnemy",
        "addEffect",
        "addBeam",
        "addFloating",
        "updateEffects",
        "resolveBattleOutcome",
    ]
    battle_renderer_exports = [
        "drawBattleFrame",
    ]
    battle_entity_renderer_exports = ["createBattleEntityRenderer"]
    battle_deployment_renderer_exports = ["createBattleDeploymentRenderer"]
    battle_road_renderer_exports = ["createBattleRoadRenderer"]
    battle_semantic_renderer_exports = ["createBattleSemanticRenderer"]
    battle_terrain_renderer_exports = ["createBattleTerrainRenderer", "imageRenderable"]
    battle_world_renderer_exports = ["createBattleWorldRenderer"]
    battle_orchestrator_exports = [
        "runBattleUpdate",
        "createBattleOrchestrator",
    ]
    battle_hud_exports = [
        "battleWaveLabel",
        "sampleProgressMessage",
        "nextWaveText",
        "toolCooldownFill",
        "buildBattleToolbarViewModel",
        "buildBattleHudViewModel",
    ]
    frontend_media_catalog_exports = ["createFrontendMediaCatalog"]
    feature_gate_exports = ["createFeatureGateRegistry"]
    page_feature_controller_contracts = [
        (onboarding_feature_controller, "onboarding-feature-controller.js", "createOnboardingFeatureController"),
        (workshop_feature_controller, "workshop-feature-controller.js", "createWorkshopFeatureController"),
        (settlement_feature_controller, "settlement-feature-controller.js", "createSettlementFeatureController"),
        (strategic_map_feature_controller, "strategic-map-feature-controller.js", "createStrategicMapFeatureController"),
    ]
    map_runtime_accessor_exports = [
        "battleConfigFromData",
        "activatedRuntimeBundleFromData",
        "mapRuntimePackageFromData",
        "mapGridFromRuntime",
        "mapObjectivesFromRuntime",
        "normalizeMapTarget",
        "pathWaypointsFromRuntime",
        "allPathRoutesFromRuntime",
        "runtimeSemanticList",
        "mapRenderPlanBundleFromData",
        "mapRenderPlanFromBundle",
        "mapRenderPlanLayersFromPlan",
        "mapRenderPlanLayerFromPlan",
        "mapRenderPlanOperationsFromPlan",
        "mapRenderPlanOperationFromPlan",
        "buildSlotPlatformOperationFromPlan",
        "renderGeometryNumber",
        "routeRoadWidthCellsFromPlan",
        "routeShoulderWidthScaleFromPlan",
        "slotFootprintScaleFromPlan",
        "mapStylePackFromBundle",
        "mapStylePaletteFromPack",
        "hexToRgbValue",
        "colorFromStylePack",
        "rgbaFromStylePack",
        "mapRenderPlanHasLayerInPlan",
    ]
    projection_exports = [
        "buildBattleToolProjection",
        "assetKindForToolId",
    ]

    require(bool(runtime_sources), "frontend source bundle must include frontend/runtime/*.js modules", errors)
    require(bool(battle_rules), "frontend/runtime/battle-rules.js missing from frontend source bundle", errors)
    require(
        bool(battle_rules) and all(has_named_export(battle_rules, name) for name in battle_rule_exports),
        "battle-rules.js must export createBattleStateFactory/canPlaceToolAt/toolReady/buildSpawnSchedule",
        errors,
    )
    require(bool(battle_actions), "frontend/runtime/battle-actions.js missing from frontend source bundle", errors)
    require(
        bool(battle_actions) and all(has_named_export(battle_actions, name) for name in battle_action_exports),
        "battle-actions.js must export tool unavailable text, MVP deployment actions, and runtime tool deployment helpers",
        errors,
    )
    require(
        bool(app_flow_orchestrator)
        and has_named_export(app_flow_orchestrator, "createAppFlowOrchestrator")
        and "SURFACE_TO_VIEW" in app_flow_orchestrator
        and "arbitrary" not in app_flow_orchestrator
        and "document." not in app_flow_orchestrator
        and "window." not in app_flow_orchestrator
        and "fetch(" not in app_flow_orchestrator,
        "app-flow-orchestrator.js must expose allowlisted player-surface navigation without browser, network, or arbitrary route ownership",
        errors,
    )
    require(
        bool(battle_map_adapter)
        and all(has_named_export(battle_map_adapter, name) for name in battle_map_adapter_exports),
        "battle-map-adapter.js must export createBattleMapAdapter",
        errors,
    )
    require(
        "mapGridFromRuntime" in battle_map_adapter
        and "pathWaypointsFromRuntime" in battle_map_adapter
        and "routeForSpawnRule" in battle_map_adapter
        and "slotAtRule" in battle_map_adapter
        and "document." not in battle_map_adapter
        and ".innerHTML" not in battle_map_adapter
        and "fetch(" not in battle_map_adapter
        and "state." not in battle_map_adapter,
        "battle-map-adapter.js must bridge runtime map accessors and pure battle rules without owning DOM, network, or global state",
        errors,
    )
    require(
        bool(battle_dom_controller)
        and all(has_named_export(battle_dom_controller, name) for name in battle_dom_controller_exports),
        "battle-dom-controller.js must export createBattleDomController",
        errors,
    )
    require(
        bool(battle_simulation),
        "frontend/runtime/battle-simulation.js missing from frontend source bundle",
        errors,
    )
    require(
        bool(battle_simulation) and all(has_named_export(battle_simulation, name) for name in battle_simulation_exports),
        "battle-simulation.js must export battle step, spawn, entity, defense, trap, effect, and outcome helpers",
        errors,
    )
    require(
        bool(battle_orchestrator),
        "frontend/runtime/battle-orchestrator.js missing from frontend source bundle",
        errors,
    )
    require(
        bool(battle_orchestrator)
        and all(has_named_export(battle_orchestrator, name) for name in battle_orchestrator_exports),
        "battle-orchestrator.js must export runBattleUpdate/createBattleOrchestrator",
        errors,
    )
    require(
        bool(battle_renderer),
        "frontend/runtime/battle-renderer.js missing from frontend source bundle",
        errors,
    )
    require(
        bool(battle_renderer) and all(has_named_export(battle_renderer, name) for name in battle_renderer_exports),
        "battle-renderer.js must export drawBattleFrame",
        errors,
    )
    for source, label, exports in (
        (battle_deployment_renderer, "battle-deployment-renderer.js", battle_deployment_renderer_exports),
        (battle_entity_renderer, "battle-entity-renderer.js", battle_entity_renderer_exports),
        (battle_road_renderer, "battle-road-renderer.js", battle_road_renderer_exports),
        (battle_semantic_renderer, "battle-semantic-renderer.js", battle_semantic_renderer_exports),
        (battle_terrain_renderer, "battle-terrain-renderer.js", battle_terrain_renderer_exports),
        (battle_world_renderer, "battle-world-renderer.js", battle_world_renderer_exports),
    ):
        require(bool(source), f"frontend/runtime/{label} missing from frontend source bundle", errors)
        require(
            bool(source) and all(has_named_export(source, name) for name in exports),
            f"{label} must export its renderer factory contract",
            errors,
        )
    require(
        bool(battle_hud),
        "frontend/runtime/battle-hud-view-model.js missing from frontend source bundle",
        errors,
    )
    require(
        bool(battle_hud) and all(has_named_export(battle_hud, name) for name in battle_hud_exports),
        "battle-hud-view-model.js must export wave/sample/next-wave/cooldown and HUD toolbar view-model helpers",
        errors,
    )
    require(
        bool(frontend_media_catalog)
        and all(has_named_export(frontend_media_catalog, name) for name in frontend_media_catalog_exports)
        and "state." not in frontend_media_catalog
        and "document." not in frontend_media_catalog
        and "fetch(" not in frontend_media_catalog,
        "frontend-media-catalog.js must export an injected catalog without owning global state, DOM, or network loading",
        errors,
    )
    require(
        bool(feature_gates)
        and all(has_named_export(feature_gates, name) for name in feature_gate_exports)
        and "runtime_safe_scan" in feature_gates
        and "activation_applied" in feature_gates
        and "SURFACE_KIND_SLOTS" in feature_gates
        and "PAYLOAD_FIELDS" in feature_gates
        and "document." not in feature_gates
        and "window." not in feature_gates
        and "fetch(" not in feature_gates,
        "feature-gates.js must enforce activation/quarantine and allowlisted declarative surface contributions without browser or network ownership",
        errors,
    )
    for source, label, factory in page_feature_controller_contracts:
        require(bool(source), f"frontend/runtime/{label} missing from frontend source bundle", errors)
        require(
            has_named_export(source, factory)
            and "fetch(" not in source
            and "apiGet(" not in source
            and "apiPost(" not in source
            and "localStorage" not in source
            and "window." not in source
            and "document." not in source,
            f"{label} must export its injected page controller without owning network, storage, or browser globals",
            errors,
        )
    require(
        bool(strategic_map_projection)
        and has_named_export(strategic_map_projection, "createStrategicMapProjection")
        and "getSurfaceContributions" in strategic_map_projection
        and "activated_runtime" in strategic_map_projection
        and "world_state" in strategic_map_projection
        and "document." not in strategic_map_projection
        and "window." not in strategic_map_projection
        and "fetch(" not in strategic_map_projection,
        "strategic-map-projection.js must merge activated contributions, world state, and map data without browser or network ownership",
        errors,
    )
    require(
        bool(map_runtime_accessors),
        "frontend/runtime/map-runtime-accessors.js missing from frontend source bundle",
        errors,
    )
    require(
        bool(map_runtime_accessors)
        and all(has_named_export(map_runtime_accessors, name) for name in map_runtime_accessor_exports),
        "map-runtime-accessors.js must export runtime package, route, RenderPlan, StylePack, and semantic-list accessors",
        errors,
    )
    require(
        bool(projection_adapter),
        "frontend/runtime/runtime-projection-adapter.js missing from frontend source bundle",
        errors,
    )
    require(
        bool(projection_adapter) and all(has_named_export(projection_adapter, name) for name in projection_exports),
        "runtime-projection-adapter.js must export buildBattleToolProjection/assetKindForToolId",
        errors,
    )
    require(
        "hotbarObjects(" in projection_adapter
        and '"battle_hotbar"' in projection_adapter
        and "cooldownMsFromAbi" in projection_adapter
        and "costFromAbi" in projection_adapter
        and "dynamicToolFromRuntimeObject" in projection_adapter,
        "runtime-projection-adapter.js must project battle_hotbar runtime objects plus ABI cost/cooldown metadata",
        errors,
    )


def validate_app_contract(errors: list[str]) -> None:
    frontend_sources = read_frontend_sources()
    runtime_sources = runtime_module_sources(frontend_sources)
    app = frontend_source_bundle(frontend_sources)
    battle_actions = runtime_sources.get("battle-actions.js", "")
    battle_map_adapter = runtime_sources.get("battle-map-adapter.js", "")
    battle_dom_controller = runtime_sources.get("battle-dom-controller.js", "")
    battle_simulation = runtime_sources.get("battle-simulation.js", "")
    battle_orchestrator = runtime_sources.get("battle-orchestrator.js", "")
    battle_entity_renderer = runtime_sources.get("battle-entity-renderer.js", "")
    battle_deployment_renderer = runtime_sources.get("battle-deployment-renderer.js", "")
    battle_road_renderer = runtime_sources.get("battle-road-renderer.js", "")
    battle_semantic_renderer = runtime_sources.get("battle-semantic-renderer.js", "")
    battle_terrain_renderer = runtime_sources.get("battle-terrain-renderer.js", "")
    battle_world_renderer = runtime_sources.get("battle-world-renderer.js", "")
    battle_hud = runtime_sources.get("battle-hud-view-model.js", "")
    map_runtime_accessors = runtime_sources.get("map-runtime-accessors.js", "")
    validate_runtime_module_contract(runtime_sources, errors)
    preload = js_section(app, "preloadBattleImages", "resizeBattleCanvas")
    backdrop = battle_terrain_renderer
    procedural_terrain = js_section(battle_terrain_renderer, "drawProceduralTerrain", "drawEdgeFog")
    path = js_section(battle_road_renderer, "drawPath", "drawSlotAccessTrails")
    profile = js_section(app, "battleNodeVisualProfile", "terrainFeatureSet")
    metrics = js_section(battle_map_adapter, "computeBattleMetrics", "projectCell")
    update_battle = js_section(battle_orchestrator, "runBattleUpdate", "createBattleOrchestrator")
    spawn = js_section(battle_simulation, "spawnEnemies")
    update_enemies = js_section(battle_simulation, "updateEnemies")
    update_defenses = js_section(battle_simulation, "updateDefenses")
    update_traps = js_section(battle_simulation, "updateTraps")
    add_effect = js_section(app, "addEffect", "addFloating")
    add_floating = js_section(app, "addFloating", "waveLabel")
    update_effects = js_section(battle_simulation, "updateEffects")
    tool_unavailable_text = js_section(app, "toolUnavailableText", "canPreviewToolAt")
    place_basic = js_section(app, "placeBasicDefense", "placeSampleTrap")
    place_sample = js_section(app, "placeSampleTrap", "useSupportPulse")
    support_pulse = js_section(app, "useSupportPulse", "setBattleToast")
    update_battle_dom = js_section(battle_dom_controller, "updateBattleDom")
    battle_tools_markup = js_section(app, "battleToolsMarkup", "drawBattle")
    deploy = js_section(battle_deployment_renderer, "drawDeployHints")
    build_terrace = js_section(battle_deployment_renderer, "drawBuildableTerrace")
    deploy_base = js_section(battle_deployment_renderer, "drawDeploymentBase")
    spawn_markers = js_section(battle_world_renderer, "drawSpawnMarkers")
    strong_semantics = battle_semantic_renderer
    renderer_frame = js_section(runtime_sources.get("battle-renderer.js", ""), "drawBattleFrame")

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

    require(
        "layeredMapVisualPreloadUrls()" in preload,
        "default preload must include reviewed LayeredMapVisualPackage presentation layers",
        errors,
    )
    require(
        "playerBattleMapVisualUrl()" not in preload,
        "default preload must not fetch legacy whole-map player image URLs",
        errors,
    )
    require('"map-v02-preview"' not in app, "default frontend must not fetch review-only v0.2 preview endpoint", errors)
    require(
        '"map-v02-opt-in-dry-run"' not in app,
        "default frontend must not fetch review-only v0.2 opt-in dry-run endpoint",
        errors,
    )
    require(
        "const layeredBackdrop = drawLayeredMapBackdrop(ctx, metrics)" in backdrop,
        "drawBackdrop must attempt reviewed layered map presentation before fallback terrain",
        errors,
    )
    require(
        "if (!layeredBackdrop) drawProceduralTerrain(ctx, metrics)" in backdrop,
        "drawBackdrop must retain procedural terrain fallback for missing/invalid layered packages",
        errors,
    )
    require(
        "drawMapDebugOverlay(ctx, m)" not in backdrop,
        "debug/reference map overlay must not be drawn in the default player backdrop",
        errors,
    )
    require(
        "playerBattleMapVisualUrl" not in backdrop,
        "drawBackdrop must not draw legacy whole-map player images; reviewed layered packages are the presentation path",
        errors,
    )
    require(
        "if (!layeredBackdrop)" in app
        and "drawDeployHints(ctx, { layeredBackdrop })" in app
        and "drawWorldObjects(ctx, { layeredBackdrop })" in app,
        "drawBattle must avoid duplicating baked map layers while still rendering runtime deployment/entity overlays",
        errors,
    )
    require(
        contains_in_order(
            renderer_frame,
            [
                "ctx.clearRect(0, 0, m.width, m.height)",
                "const layeredBackdrop = drawBackdrop(ctx, m)",
                "if (!layeredBackdrop)",
                "drawBuildableTerraces(ctx)",
                "drawSlotAccessTrails(ctx)",
                "drawPath(ctx)",
                "drawMapRuntimeStrongSemantics(ctx)",
                "drawDeployHints(ctx, { layeredBackdrop })",
                "drawWorldObjects(ctx, { layeredBackdrop })",
                "if (!layeredBackdrop) drawSpawnMarkers(ctx)",
                "drawEntities(ctx)",
                "drawEffects(ctx)",
                "drawDragGhost(ctx)",
            ],
        ),
        "drawBattleFrame must keep static baked-map layers gated by layeredBackdrop while runtime overlays/entities/effects stay outside the skip branch",
        errors,
    )
    require("drawScenicBackplate(ctx, metrics, features)" in procedural_terrain, "procedural terrain must render scenic world backplate outside the playable field", errors)
    require("drawPlayableFieldBoundary(ctx, metrics)" in procedural_terrain, "procedural terrain must render a playable field boundary", errors)
    require("drawFieldEdgeBreakup(ctx, metrics, features)" in procedural_terrain, "procedural terrain must break up the playable-field edge with diegetic props", errors)
    require("drawDarkTidePools(ctx, features)" in procedural_terrain, "procedural terrain must include world-space dark tide pools", errors)
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
    require("const road = getVisualProfile().road || {}" in path, "drawPath must consume map style road colors when available", errors)
    require("road.base" in path and "road.crown" in path, "drawPath must map StylePack road colors onto player roads", errors)
    require("routeRoadWidthCells(route)" in path, "drawPath must consume RenderPlan road width geometry", errors)
    require('"width_cells"' in app, "frontend must read road_band geometry.width_cells from RenderPlan", errors)
    require("routeShoulderWidthScale(route)" in app, "route shoulders must consume RenderPlan road_edge shoulder geometry", errors)
    require('"shoulder_width_cells"' in app, "frontend must read road_edge geometry.shoulder_width_cells from RenderPlan", errors)
    require("drawSlotAccessTrails(ctx)" in app, "battle view must visually connect deployment bases to runtime roads", errors)
    require(
        "createBattleTerrainRenderer({" in app
        and "createBattleRoadRenderer({" in app
        and "createBattleEntityRenderer({" in app
        and "createBattleDeploymentRenderer({" in app
        and "createBattleSemanticRenderer({" in app
        and "createBattleWorldRenderer({" in app
        and "battleTerrainRenderer.drawBackdrop(ctx, m)" in app
        and "battleRoadRenderer.drawPath(ctx)" in app
        and "battleEntityRenderer.drawEntities(ctx)" in app
        and "battleDeploymentRenderer.drawDeployHints(ctx, options)" in app
        and "battleSemanticRenderer.drawMapRuntimeStrongSemantics(ctx)" in app
        and "battleWorldRenderer.drawWorldObjects(ctx, options)" in app,
        "app.js must delegate battle presentation through runtime renderer factories",
        errors,
    )
    for source, label in (
        (battle_deployment_renderer, "battle-deployment-renderer"),
        (battle_terrain_renderer, "battle-terrain-renderer"),
        (battle_road_renderer, "battle-road-renderer"),
        (battle_entity_renderer, "battle-entity-renderer"),
        (battle_semantic_renderer, "battle-semantic-renderer"),
        (battle_world_renderer, "battle-world-renderer"),
    ):
        require(
            "fetch(" not in source
            and "document." not in source
            and ".innerHTML" not in source
            and "state." not in source
            and "deployToolAt(" not in source
            and "finishBattle(" not in source,
            f"{label} must remain presentation-only and not own network, DOM panels, gameplay deployment, or settlement state",
            errors,
        )
    require(
        "drawMapRuntimeStrongSemantics(ctx)" in app,
        "battle view must render v0.2 strong semantics when present in MapRuntimePackage",
        errors,
    )
    require(
        'featureGateRegistry.activeBundleFor("battle")' in app
        and 'featureGateRegistry.capabilityList("battle_objects", "battle")' in app
        and 'surfaceContributions("strategic_map"' in app,
        "battle and strategic map must consume AI-compiled runtime content through the feature gate registry",
        errors,
    )
    require(
        "createAppFlowOrchestrator({" in app
        and "appFlowOrchestrator.renderCurrent()" in app
        and "appFlowOrchestrator.setCurrentView(view)" in app
        and "switch (state.view)" not in app,
        "app.js must delegate player view rendering and navigation to app-flow-orchestrator",
        errors,
    )
    require(
        'runtimeSemanticList(mapPackage(), "resource_nodes")' in battle_map_adapter
        and 'runtimeSemanticList(mapPackage(), "hazard_zones")' in battle_map_adapter
        and 'runtimeSemanticList(mapPackage(), "defense_anchors")' in battle_map_adapter
        and 'runtimeSemanticList(mapPackage(), "blocked_areas")' in battle_map_adapter
        and "battleMapAdapter.mapResourceNodes()" in app
        and "battleMapAdapter.mapBlockedAreas()" in app,
        "strong semantic lists must be centralized in battle-map-adapter and delegated by app.js",
        errors,
    )
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
        "zone.path_t_range" in strong_semantics and "routeSamplesBetween(route" in strong_semantics,
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
    require("drawBattlefieldLandmarks(ctx)" in battle_world_renderer, "battle view must render world-space landmarks", errors)
    require("drawObjectiveDefensiveZone(ctx" in battle_world_renderer, "battle view must ground objectives in a defense zone", errors)
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
    require("getVisualProfile().platform" in battle_deployment_renderer, "deployment bases must consume StylePack platform colors", errors)
    require("getVisualProfile().objective" in battle_world_renderer, "target foundations must consume StylePack objective colors", errors)
    require("getVisualProfile().spawn" in battle_world_renderer, "spawn effects must consume StylePack spawn colors", errors)
    require(
        "resolveBattleObjectSpriteRef(defense)" in battle_world_renderer
        and "resolveToolSpriteRef(tool)" in battle_deployment_renderer
        and "resolveToolSpriteRef" in battle_entity_renderer,
        "compiled defenses, deployment previews, and drag ghosts must resolve runtime media identity before fallback art",
        errors,
    )
    require("function drawGrid" not in app and "function drawDiamond" not in app, "battle view must not keep checkerboard/grid drawing helpers", errors)
    require(
        contains_in_order(
            update_battle,
            [
                "const step = advanceBattleStep({ battle, dt })",
                "if (step.sampleDelivered) onSampleDelivered({ battle, step })",
                "spawnEnemies({ battle })",
                "updateEnemies({ battle, dt })",
                "updateDefenses({ battle, dt })",
                "updateTraps({ battle, dt })",
                "updateEffects({ battle, dt })",
                "const outcome = resolveBattleOutcome({ battle })",
                "if (outcome) void finishBattle(outcome)",
            ],
        ),
        "battle orchestrator must keep simulation order: advance clock/sample, notify UI, update entities/effects, then resolve outcome",
        errors,
    )
    require("routeForSpawn(battle.spawned)" in spawn, "enemy spawn must bind to runtime route/spawn ids", errors)
    require("enemyWaypoints(enemy)" in update_enemies, "enemy movement must use the enemy route, not only the first path", errors)
    require(
        "spawnEnemies: ({ battle }) => spawnEnemiesStep({ battle, routeForSpawn, pathWaypoints })" in app
        and "battle.enemies.push" in spawn
        and "battle.spawned += 1" in spawn,
        "battle orchestrator wiring must delegate spawn to battle-simulation while preserving schedule-driven enemy creation",
        errors,
    )
    require(
        "updateEnemies: ({ battle, dt }) => updateEnemiesStep({ battle, dt, enemyWaypoints })" in app
        and "battle.coreHp -= 1" in update_enemies
        and "battle.leaks += 1" in update_enemies
        and "battle.kills += 1" in update_enemies,
        "battle orchestrator wiring must delegate enemy updates while preserving leak/kill accounting",
        errors,
    )
    require(
        "updateDefenses: ({ battle }) => updateDefensesStep({ battle })" in app
        and "const attackRange = Number(defense.range) > 0" in update_defenses
        and "nearestEnemy({ battle, x: defense.x, y: defense.y, radius: attackRange })" in update_defenses
        and "enemy.hp -= damage" in update_defenses
        and "splashRadius" in update_defenses
        and "addBeam(battle" in update_defenses,
        "battle orchestrator wiring must delegate defenses while preserving ABI-driven single-target/radius attacks",
        errors,
    )
    require(
        "updateTraps: ({ battle }) => updateTrapsStep({ battle })" in app
        and "const radius = Number(trap.radius) > 0" in update_traps
        and "nearestEnemy({ battle, x: trap.x, y: trap.y, radius: triggerRadius })" in update_traps
        and "trap.armed = false" in update_traps
        and "slowDurationMs" in update_traps
        and "enemy.slowUntil" in update_traps,
        "battle orchestrator wiring must delegate traps while preserving ABI-driven trigger and slow behavior",
        errors,
    )
    require(
        "updateEffects: ({ battle, dt }) => updateEffectsStep({ battle, dt })" in app
        and "effect.age += dt" in update_effects
        and "effect.age < effect.duration" in update_effects,
        "battle orchestrator wiring must delegate effects while preserving effect aging and cleanup",
        errors,
    )
    require(
        "addBattleEffect(state.battle, type, x, y, color, duration, scale)" in add_effect,
        "addEffect wrapper must bind battle-simulation effect queue to current state.battle",
        errors,
    )
    require(
        "addBattleFloating(state.battle, x, y, text, color)" in add_floating,
        "addFloating wrapper must bind battle-simulation floating text to current state.battle",
        errors,
    )
    require(
        "setBattleToast(" not in battle_simulation
        and "showDialogue(" not in battle_simulation
        and "finishBattle(" not in battle_simulation
        and "document." not in battle_simulation
        and ".innerHTML" not in battle_simulation,
        "battle-simulation module must not own UI, DOM, or settlement side effects",
        errors,
    )
    require(
        "document." not in battle_orchestrator
        and ".innerHTML" not in battle_orchestrator
        and "fetch(" not in battle_orchestrator
        and "setBattleToast(" not in battle_orchestrator
        and "showDialogue(" not in battle_orchestrator,
        "battle-orchestrator module must own timing and call order without DOM, network, or narrative side effects",
        errors,
    )
    require(
        "createBattleOrchestrator({" in app
        and "battleOrchestrator.start()" in app
        and "battleOrchestrator.stop()" in app
        and "finishBattle: (outcome) => finishBattle(outcome)" in app,
        "app.js must wire battle lifecycle through battle-orchestrator",
        errors,
    )
    require(
        "toolUnavailableTextAction(findBattleToolProjection(tool, battleToolProjection()) || tool)" in tool_unavailable_text
        and "placeBasicDefenseAction({" in place_basic
        and "battle: state.battle" in place_basic
        and "placeSampleTrapAction({" in place_sample
        and "battle: state.battle" in place_sample
        and "useSupportPulseAction({" in support_pulse
        and "battle: state.battle" in support_pulse
        and "deployRuntimeToolAction({" in app
        and "canPreviewRuntimeToolAt({" in app,
        "battle deployment/tool behavior must delegate from app.js into battle-actions.js, including dynamic runtime tools",
        errors,
    )
    require(
        "document." not in battle_actions
        and ".innerHTML" not in battle_actions
        and "fetch(" not in battle_actions
        and "provider" not in battle_actions.lower()
        and ".env" not in battle_actions
        and "api_key" not in battle_actions.lower()
        and "prompt" not in battle_actions.lower(),
        "battle-actions module must stay runtime-only: no DOM, fetch, provider/api key, or prompt terms",
        errors,
    )
    require(
        "buildBattleHudViewModel({" in app
        and "buildHudViewModel()" in update_battle_dom
        and "hud.stats" in update_battle_dom
        and "hud.taskItems" in update_battle_dom
        and "hud.info.items" in update_battle_dom
        and "renderToolbar(hud.toolbarTools)" in update_battle_dom,
        "updateBattleDom must render battle HUD from battle-hud-view-model output instead of assembling panel state inline",
        errors,
    )
    require(
        "buildBattleToolbarViewModel({" in app
        and "battleToolProjection({" in app
        and "isToolReady: toolReady" in app,
        "battle toolbar state must be projected through buildBattleToolbarViewModel for AI-compiled tool packages",
        errors,
    )
    require(
        "buildToolCooldownFill({" in app
        and "cooldownMs: Number(projected && projected.cooldownMs) || fallbackToolCooldownMs(tool)" in app,
        "tool cooldown display must derive from projected runtime package metadata with local fallback",
        errors,
    )
    require(
        "tool.isSelected" in battle_tools_markup
        and "tool.isDragging" in battle_tools_markup
        and "tool.isLocked" in battle_tools_markup
        and "tool.cooldownFill" in battle_tools_markup,
        "battleToolsMarkup must consume toolbar view-model flags rather than recomputing interaction state",
        errors,
    )
    require(
        "battleWaveLabel(state.battle)" not in update_battle_dom
        and "sampleProgressMessage({" not in update_battle_dom
        and "nextWaveText(state.battle)" not in update_battle_dom,
        "updateBattleDom must not bypass HUD view-model helpers for wave/sample/next-wave text",
        errors,
    )
    require(
        "document." not in battle_hud
        and ".innerHTML" not in battle_hud
        and "fetch(" not in battle_hud
        and "provider" not in battle_hud.lower()
        and ".env" not in battle_hud
        and "api_key" not in battle_hud.lower()
        and "prompt" not in battle_hud.lower(),
        "battle-hud-view-model module must stay pure: no DOM, fetch, provider/api key, or prompt terms",
        errors,
    )
    require(
        "mapGridFromRuntime({" in app
        and "mapObjectivesFromRuntime({" in app
        and "pathWaypointsFromRuntime({" in app
        and "allPathRoutesFromRuntime({" in app,
        "app.js must route runtime map config, objectives, and routes through map-runtime-accessors",
        errors,
    )
    require(
        "routeRoadWidthCellsFromPlan(mapRenderPlan(), route)" in app
        and "routeShoulderWidthScaleFromPlan(mapRenderPlan(), route)" in app
        and "slotFootprintScaleFromPlan(mapRenderPlan(), slot, axis)" in app
        and "colorFromStylePack(mapStylePack(), key, fallback)" in app
        and "rgbaFromStylePack(mapStylePack(), key, alpha, fallback)" in app,
        "app.js must route RenderPlan geometry and StylePack colors through map-runtime-accessors",
        errors,
    )
    require(
        "document." not in map_runtime_accessors
        and ".innerHTML" not in map_runtime_accessors
        and "fetch(" not in map_runtime_accessors
        and "provider" not in map_runtime_accessors.lower()
        and ".env" not in map_runtime_accessors
        and "api_key" not in map_runtime_accessors.lower()
        and "prompt" not in map_runtime_accessors.lower(),
        "map-runtime-accessors module must stay pure: no DOM, fetch, provider/api key, or prompt terms",
        errors,
    )

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


def validate_layered_map_packages(errors: list[str]) -> None:
    if not LAYERED_MAP_MANIFESTS:
        return
    forbidden_player_roles = {"battle_control_sketch", "battle_reference_board", "strategic_control_sketch"}
    required_policy = {
        "runtime_semantics_from_map_runtime_package",
        "visual_package_is_presentation_only",
        "no_pixel_to_semantic_inference",
        "player_default_presentation_allowed",
        "local_reviewed_artifact_only",
        "no_raw_generation_payload",
        "no_external_temporary_url",
    }
    for manifest_path in LAYERED_MAP_MANIFESTS:
        manifest = load_json(manifest_path)
        label = manifest_path.parent.name
        require(
            manifest.get("schema_version") == "layered_map_visual_package.v0.1",
            f"{label} layered map manifest must be layered_map_visual_package.v0.1",
            errors,
        )
        runtime_semantics = manifest.get("runtime_semantics_source") or {}
        require(
            runtime_semantics.get("kind") == "MapRuntimePackage",
            f"{label} layered map runtime semantics source must be MapRuntimePackage",
            errors,
        )
        require(
            runtime_semantics.get("authority") == "runtime_semantic_truth",
            f"{label} layered map semantics authority must remain runtime_semantic_truth",
            errors,
        )
        usage_policy = set(map(str, manifest.get("usage_policy") or []))
        missing_policy = sorted(required_policy - usage_policy)
        require(
            not missing_policy,
            f"{label} layered map usage_policy missing: {', '.join(missing_policy)}",
            errors,
        )
        layers = [layer for layer in manifest.get("layers") or [] if isinstance(layer, dict)]
        player_layers = [layer for layer in layers if layer.get("player_default") is True]
        composited_layers = [layer for layer in layers if layer.get("role") == "composited"]
        require(player_layers, f"{label} layered map must expose player_default presentation layers", errors)
        require(
            any(layer.get("player_default") is True for layer in composited_layers),
            f"{label} layered map must expose a player_default composited layer",
            errors,
        )
        for index, layer in enumerate(player_layers):
            role = str(layer.get("role") or "")
            quality = layer.get("quality") or {}
            local_path = str(layer.get("local_path") or "")
            url = str(layer.get("url") or "")
            require(
                role not in forbidden_player_roles,
                f"{label} player_default layer must not expose control/reference role: {role}",
                errors,
            )
            require(
                url.startswith("/assets/layered_maps/"),
                f"{label} player_default layer[{index}] must use /assets/layered_maps URL",
                errors,
            )
            require(
                local_path.startswith("game_data/media/layered_maps/")
                and (ROOT / local_path).exists(),
                f"{label} player_default layer[{index}] local_path missing: {local_path}",
                errors,
            )
            require(
                quality.get("gate_status") == "passed"
                and quality.get("alignment_status") == "passed"
                and quality.get("player_visible_quality") == "passed",
                f"{label} player_default layer[{index}] must pass gate/alignment/player quality",
                errors,
            )


def build_report(generated_at: str) -> dict[str, Any]:
    app_errors: list[str] = []
    css_errors: list[str] = []
    map_errors: list[str] = []
    layered_map_errors: list[str] = []
    validate_app_contract(app_errors)
    validate_css_contract(css_errors)
    validate_map_layers(map_errors)
    validate_layered_map_packages(layered_map_errors)
    errors = app_errors + css_errors + map_errors + layered_map_errors
    status = "passed" if not errors else "failed"
    frontend_sources = read_frontend_sources()
    frontend_source_files = list(frontend_sources)
    runtime_source_files = [path for path in frontend_source_files if path.parent == RUNTIME_JS_DIR]
    source_files = [
        *frontend_source_files,
        STYLES_CSS,
        MAP_MANIFEST,
        *LAYERED_MAP_MANIFESTS,
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
            "layered_map_error_count": len(layered_map_errors),
            "error_count": len(errors),
            "layered_map_package_count": len(LAYERED_MAP_MANIFESTS),
            "map_runtime_package_count": len(MAP_RUNTIME_PACKAGES),
            "map_runtime_v02_preview_package_count": len(MAP_RUNTIME_PACKAGES_V02),
            "runtime_source_file_count": len(runtime_source_files),
            "source_file_count": len(source_files),
        },
        "frontend_source_bundle": frontend_source_bundle_report(frontend_sources),
        "contract_claims": {
            "default_battle_backdrop": "reviewed LayeredMapVisualPackage presentation first; MapRuntimePackage-driven procedural fallback",
            "full_screen_battle_canvas": True,
            "reviewed_layered_map_preload_allowed": True,
            "no_default_legacy_whole_map_image_preload": True,
            "no_default_control_or_reference_map": True,
            "no_checkerboard_or_dashed_control_path": True,
            "runtime_semantics_source": "MapRuntimePackage",
            "presentation_source": "LayeredMapVisualPackage, MapStylePack, and ProceduralMapRenderPlan geometry",
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
            "layered_maps": layered_map_errors,
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
        + report["error_groups"]["layered_maps"]
    )
    if args.report_output:
        write_json(args.report_output, report)

    if errors:
        print("INVALID battle visual contract")
        for error in errors:
            print(f"- {error}")
        return 1

    print("OK battle visual contract")
    print(f"- layered map packages: {report['summary']['layered_map_package_count']}")
    print(f"- map runtime packages: {len(MAP_RUNTIME_PACKAGES)}")
    print(f"- map runtime v0.2 preview packages: {len(MAP_RUNTIME_PACKAGES_V02)}")
    print("- default battle backdrop: reviewed LayeredMapVisualPackage presentation with procedural fallback")
    print("- map style: optional MapRenderPlan geometry and StylePack colors, runtime semantics stay in MapRuntimePackage")
    print("- v0.2 strong semantics: consumed from activated runtime package only; review-only endpoints stay isolated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
