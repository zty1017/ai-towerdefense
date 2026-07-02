#!/usr/bin/env python3
"""Validate battle-screen visual contracts without a browser.

This is not a screenshot test. It catches regressions that made earlier MVP
builds look like debug tools: control maps leaking into player view, missing
painted map layers, and battle canvas layouts that collapse into a small panel.
"""

from __future__ import annotations

import json
import re
import struct
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
APP_JS = ROOT / "frontend/app.js"
STYLES_CSS = ROOT / "frontend/styles.css"
MAP_MANIFEST = ROOT / "game_data/media/map_visual_reference/map_visual_reference_manifest.v0.1.json"
MAP_RUNTIME_PACKAGES = sorted((ROOT / "examples/map_runtime_packages").glob("*.map_runtime_package.json"))


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


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
    deploy = js_section(app, "drawDeployHints", "drawDeploymentBase")
    spawn = js_section(app, "drawSpawnMarkers", "drawSpawnRift")

    for name in (
        "terrainFeatureSet",
        "drawProceduralTerrain",
        "drawRoadPebbles",
        "drawDeploymentBase",
        "drawTargetFoundation",
        "drawSpawnRift",
    ):
        require(f"function {name}" in app, f"missing {name}() procedural battle layer", errors)

    require("playerBattleMapVisualUrl()" not in preload, "default preload must not fetch whole-map player images", errors)
    require("drawProceduralTerrain(ctx, m)" in backdrop, "drawBackdrop must start from procedural terrain", errors)
    require("drawMapDebugOverlay(ctx, m)" in backdrop, "debug map overlay must be isolated behind its own helper", errors)
    require("playerBattleMapVisualUrl" not in backdrop, "drawBackdrop must not draw whole-map player images by default", errors)
    require("drawRoadPebbles" in path, "drawPath must render textured world road details", errors)
    require("setLineDash" not in path, "drawPath must not render dashed control lines", errors)
    require("drawDeploymentBase" in deploy, "deploy hints must render world-space deployment bases", errors)
    require("drawSpawnRift" in spawn, "spawn markers must render ambient entry effects, not arrows", errors)
    require("function drawGrid" not in app and "function drawDiamond" not in app, "battle view must not keep checkerboard/grid drawing helpers", errors)

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


def main() -> int:
    errors: list[str] = []
    validate_app_contract(errors)
    validate_css_contract(errors)
    validate_map_layers(errors)

    if errors:
        print("INVALID battle visual contract")
        for error in errors:
            print(f"- {error}")
        return 1

    print("OK battle visual contract")
    print(f"- map runtime packages: {len(MAP_RUNTIME_PACKAGES)}")
    print("- default battle backdrop: MapRuntimePackage-driven procedural terrain")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
