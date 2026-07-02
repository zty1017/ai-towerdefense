#!/usr/bin/env python3
"""Build review-only topology control sketches from MapRuntimePackage files.

Control sketches are developer/evidence artifacts for map generation. They are
not player-facing map backgrounds and must not be consumed as published visual
layers. The PNG intentionally avoids text labels so it can be used as a clean
composition reference for image models or manual paintover.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MEDIA_DIR = Path(__file__).resolve().parent
if str(MEDIA_DIR) not in sys.path:
    sys.path.insert(0, str(MEDIA_DIR))

import build_map_candidate_overlay_review as overlay  # noqa: E402


REPORT_VERSION = "map_topology_control_sketch_pack.v0.1"
DEFAULT_RUNTIME_PACKAGE_DIR = ROOT / "examples/map_runtime_packages"
DEFAULT_OUTPUT_DIR = ROOT / "game_data/media/map_visual_reference/topology_control_sketches"
DEFAULT_REPORT = ROOT / "examples/review_packs/map_topology_control_sketch_pack.v0.1.json"
TARGET_WIDTH = 1280
TARGET_HEIGHT = 720


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_canvas(width: int, height: int, color: tuple[int, int, int]) -> list[bytearray]:
    row = bytearray()
    for _ in range(width):
        row.extend(color)
    return [bytearray(row) for _ in range(height)]


def draw_soft_grid(rows: list[bytearray], width: int, height: int, grid: dict[str, Any]) -> None:
    width_cells = int(grid.get("width_cells") or 1)
    height_cells = int(grid.get("height_cells") or 1)
    for index in range(1, width_cells):
        x = int(index / width_cells * width)
        for y in range(height):
            overlay.blend_pixel(rows, width, height, x, y, (179, 191, 205), 0.18)
    for index in range(1, height_cells):
        y = int(index / height_cells * height)
        for x in range(width):
            overlay.blend_pixel(rows, width, height, x, y, (179, 191, 205), 0.18)


def objective_items(package: dict[str, Any]) -> list[dict[str, Any]]:
    objectives = as_obj(package.get("objectives"))
    items = []
    core = objectives.get("core_target")
    if isinstance(core, dict):
        items.append(core)
    items.extend(target for target in as_list(objectives.get("optional_targets")) if isinstance(target, dict))
    return items


def draw_control_png(path: Path, package: dict[str, Any], width: int, height: int) -> None:
    rows = make_canvas(width, height, (224, 232, 238))
    grid = as_obj(package.get("grid"))
    draw_soft_grid(rows, width, height, grid)

    # Broad terrain-safe route corridors.
    route_colors = [(230, 166, 49), (174, 128, 207), (89, 160, 220)]
    for index, route in enumerate(as_list(package.get("path_routes"))):
        if not isinstance(route, dict):
            continue
        points = [
            overlay.grid_to_pixel(point, grid, width, height)
            for point in as_list(route.get("waypoints"))
            if isinstance(point, dict)
        ]
        if len(points) >= 2:
            color = route_colors[index % len(route_colors)]
            overlay.draw_polyline(rows, width, height, points, 24, (82, 93, 104), 0.55)
            overlay.draw_polyline(rows, width, height, points, 17, color, 0.82)
            overlay.draw_polyline(rows, width, height, points, 5, (255, 249, 196), 0.55)

    # Empty build pads.
    for slot in as_list(package.get("build_slots")):
        if not isinstance(slot, dict):
            continue
        x, y = overlay.grid_to_pixel(as_obj(slot.get("position")), grid, width, height)
        overlay.draw_disc(rows, width, height, x, y, 25, (25, 118, 210), 0.55)
        overlay.draw_disc(rows, width, height, x, y, 17, (224, 247, 250), 0.9)
        overlay.draw_disc(rows, width, height, x, y, 8, (25, 118, 210), 0.38)

    # Spawns.
    for spawn in as_list(package.get("spawn_points")):
        if not isinstance(spawn, dict):
            continue
        x, y = overlay.grid_to_pixel(as_obj(spawn.get("position")), grid, width, height)
        overlay.draw_disc(rows, width, height, x, y, 29, (104, 58, 183), 0.75)
        overlay.draw_disc(rows, width, height, x, y, 14, (237, 231, 246), 0.8)

    # Objectives.
    for target in objective_items(package):
        x, y = overlay.grid_to_pixel(as_obj(target.get("position")), grid, width, height)
        overlay.draw_square(rows, width, height, x, y, 30, (198, 40, 40), 0.74)
        overlay.draw_square(rows, width, height, x, y, 15, (255, 235, 238), 0.86)

    overlay.write_png(path, width, height, 2, rows)


def svg_escape(value: Any) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def label_position(x: float, y: float, width: int, height: int) -> tuple[float, float]:
    return (
        min(max(x, 12), width - 360),
        min(max(y, 24), height - 18),
    )


def build_control_svg(path: Path, package: dict[str, Any], png_path: Path, width: int, height: int) -> None:
    grid = as_obj(package.get("grid"))
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'  <image href="{svg_escape(png_path.name)}" x="0" y="0" width="{width}" height="{height}"/>',
        '  <g id="developer-labels" font-family="monospace" font-size="18" fill="#0f172a" stroke="#f8fafc" stroke-width="4" paint-order="stroke">',
    ]
    for route in as_list(package.get("path_routes")):
        if not isinstance(route, dict):
            continue
        waypoints = [point for point in as_list(route.get("waypoints")) if isinstance(point, dict)]
        if waypoints:
            x, y = overlay.grid_to_pixel(waypoints[0], grid, width, height)
            label_x, label_y = label_position(x + 20, y - 20, width, height)
            lines.append(
                f'    <text x="{label_x:.1f}" y="{label_y:.1f}">{svg_escape(route.get("route_id"))}</text>'
            )
    for target in objective_items(package):
        x, y = overlay.grid_to_pixel(as_obj(target.get("position")), grid, width, height)
        label_x, label_y = label_position(x + 28, y + 8, width, height)
        lines.append(
            f'    <text x="{label_x:.1f}" y="{label_y:.1f}">{svg_escape(target.get("target_id"))}</text>'
        )
    lines.extend(["  </g>", "</svg>"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def runtime_summary(package: dict[str, Any]) -> dict[str, Any]:
    return {
        "grid": as_obj(package.get("grid")),
        "path_route_count": len(as_list(package.get("path_routes"))),
        "build_slot_count": len(as_list(package.get("build_slots"))),
        "spawn_point_count": len(as_list(package.get("spawn_points"))),
        "objective_count": len(objective_items(package)),
    }


def build_sketch(package_path: Path, output_dir: Path, width: int, height: int) -> dict[str, Any]:
    package = load_json(package_path)
    if not isinstance(package, dict):
        return {
            "package_path": rel(package_path),
            "status": "blocked",
            "issues": ["runtime_package_root_not_object"],
        }
    node_id = str(package.get("node_id") or package_path.stem)
    png_path = output_dir / f"{node_id}.topology_control_sketch.png"
    svg_path = output_dir / f"{node_id}.topology_control_sketch.svg"
    draw_control_png(png_path, package, width, height)
    build_control_svg(svg_path, package, png_path, width, height)
    return {
        "node_id": node_id,
        "status": "control_sketch_ready",
        "runtime_package_path": rel(package_path),
        "control_sketch_png_path": rel(png_path),
        "control_sketch_svg_path": rel(svg_path),
        "png_sha256": sha256_file(png_path),
        "svg_sha256": sha256_file(svg_path),
        "dimensions": {"width": width, "height": height},
        "runtime_summary": runtime_summary(package),
        "usage_policy": [
            "developer_reference_only",
            "not_player_visible",
            "not_a_published_visual_layer",
            "image_provider_reference_or_manual_paintover_input",
        ],
        "composition_constraints": [
            "preserve route directions and branch structure",
            "keep build pads near routes but visually empty",
            "keep objectives compact and readable",
            "do not include characters, enemies, projectiles, UI, arrows, or text in generated painted map",
        ],
    }


def runtime_package_paths(runtime_package_dir: Path, selected_nodes: list[str]) -> list[Path]:
    all_paths = sorted(runtime_package_dir.glob("*.map_runtime_package.json"))
    if not selected_nodes:
        return all_paths
    selected = set(selected_nodes)
    result = []
    for path in all_paths:
        package = load_json(path)
        if isinstance(package, dict) and package.get("node_id") in selected:
            result.append(path)
    return result


def build_pack(runtime_package_dir: Path, output_dir: Path, width: int, height: int, selected_nodes: list[str]) -> dict[str, Any]:
    sketches = [
        build_sketch(path, output_dir, width, height)
        for path in runtime_package_paths(runtime_package_dir, selected_nodes)
    ]
    status_counts = Counter(str(sketch.get("status")) for sketch in sketches)
    blocked_count = status_counts.get("blocked", 0)
    return {
        "schema_version": REPORT_VERSION,
        "pack_id": "mvp_map_topology_control_sketch_pack",
        "runtime_package_dir": rel(runtime_package_dir),
        "output_dir": rel(output_dir),
        "status": "blocked" if blocked_count else "control_sketches_ready_review_only",
        "summary": {
            "sketch_count": len(sketches),
            "ready_count": status_counts.get("control_sketch_ready", 0),
            "blocked_count": blocked_count,
            "status_counts": dict(sorted(status_counts.items())),
            "target_size": {"width": width, "height": height},
        },
        "sketches": sketches,
        "policy": [
            "Control sketches are compile-time references only.",
            "The frontend player runtime must not consume these sketches as map backgrounds.",
            "Painted candidates generated from these sketches must still pass candidate, alignment, overlay, visual, and promotion gates.",
        ],
    }


def parse_target_size(value: str) -> tuple[int, int]:
    try:
        width_s, height_s = value.lower().split("x", 1)
        width = int(width_s)
        height = int(height_s)
    except ValueError as exc:
        raise SystemExit(f"invalid --target-size {value!r}; expected WIDTHxHEIGHT") from exc
    if width <= 0 or height <= 0:
        raise SystemExit("--target-size dimensions must be positive")
    return width, height


def main() -> int:
    parser = argparse.ArgumentParser(description="Build topology control sketch pack from MapRuntimePackage files.")
    parser.add_argument("--runtime-package-dir", default=str(DEFAULT_RUNTIME_PACKAGE_DIR))
    parser.add_argument("--node-id", action="append", default=[], help="Restrict to node id. May be repeated.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--output", default=str(DEFAULT_REPORT))
    parser.add_argument("--target-size", default=f"{TARGET_WIDTH}x{TARGET_HEIGHT}")
    args = parser.parse_args()

    runtime_package_dir = Path(args.runtime_package_dir)
    if not runtime_package_dir.is_absolute():
        runtime_package_dir = ROOT / runtime_package_dir
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    width, height = parse_target_size(args.target_size)

    pack = build_pack(runtime_package_dir, output_dir, width, height, args.node_id)
    write_json(output, pack)
    print(f"Wrote {output}")
    print(f"- status: {pack['status']}")
    print(f"- sketches: {pack['summary']['sketch_count']}")
    return 0 if pack["summary"]["sketch_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
