#!/usr/bin/env python3
"""Build deterministic map control/reference images from logical map data.

This is the first executable slice of the map-as-compiled-object pipeline:
logical battle/map data remains authoritative, while these generated PNGs are
reference material for future image/video providers and for human review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MAP = ROOT / "game_data/demo/initial_map.json"
DEFAULT_BATTLE = ROOT / "game_data/demo/first_battle_config.json"
DEFAULT_OUT = ROOT / "game_data/media/map_visual_reference"

import sys

MEDIA_DIR = Path(__file__).resolve().parent
if str(MEDIA_DIR) not in sys.path:
    sys.path.insert(0, str(MEDIA_DIR))

import png_pipeline  # noqa: E402


Color = tuple[int, int, int, int]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rgba(hex_color: str, alpha: int = 255) -> Color:
    value = hex_color.strip().lstrip("#")
    return int(value[:2], 16), int(value[2:4], 16), int(value[4:6], 16), alpha


def new_image(width: int, height: int, color: Color) -> png_pipeline.PngImage:
    return png_pipeline.PngImage(width, height, bytearray(color * width * height))


def blend_pixel(image: png_pipeline.PngImage, x: int, y: int, color: Color) -> None:
    if x < 0 or y < 0 or x >= image.width or y >= image.height:
        return
    index = (y * image.width + x) * 4
    sr, sg, sb, sa = color
    if sa >= 255:
        image.pixels[index : index + 4] = bytes(color)
        return
    alpha = sa / 255
    dr, dg, db, da = image.pixels[index : index + 4]
    image.pixels[index] = int(sr * alpha + dr * (1 - alpha))
    image.pixels[index + 1] = int(sg * alpha + dg * (1 - alpha))
    image.pixels[index + 2] = int(sb * alpha + db * (1 - alpha))
    image.pixels[index + 3] = max(da, sa)


def fill_rect(image: png_pipeline.PngImage, x: int, y: int, w: int, h: int, color: Color) -> None:
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            blend_pixel(image, xx, yy, color)


def fill_circle(image: png_pipeline.PngImage, cx: float, cy: float, radius: float, color: Color) -> None:
    min_x = int(cx - radius - 1)
    max_x = int(cx + radius + 1)
    min_y = int(cy - radius - 1)
    max_y = int(cy + radius + 1)
    r2 = radius * radius
    for y in range(min_y, max_y + 1):
        for x in range(min_x, max_x + 1):
            if (x - cx) ** 2 + (y - cy) ** 2 <= r2:
                blend_pixel(image, x, y, color)


def fill_ellipse(image: png_pipeline.PngImage, cx: float, cy: float, rx: float, ry: float, color: Color) -> None:
    min_x = int(cx - rx - 1)
    max_x = int(cx + rx + 1)
    min_y = int(cy - ry - 1)
    max_y = int(cy + ry + 1)
    rx2 = max(1, rx * rx)
    ry2 = max(1, ry * ry)
    for y in range(min_y, max_y + 1):
        for x in range(min_x, max_x + 1):
            if ((x - cx) ** 2) / rx2 + ((y - cy) ** 2) / ry2 <= 1:
                blend_pixel(image, x, y, color)


def stroke_circle(image: png_pipeline.PngImage, cx: float, cy: float, radius: float, width: int, color: Color) -> None:
    outer = radius + width / 2
    inner = max(0, radius - width / 2)
    outer2 = outer * outer
    inner2 = inner * inner
    for y in range(int(cy - outer - 1), int(cy + outer + 2)):
        for x in range(int(cx - outer - 1), int(cx + outer + 2)):
            d2 = (x - cx) ** 2 + (y - cy) ** 2
            if inner2 <= d2 <= outer2:
                blend_pixel(image, x, y, color)


def fill_polygon(image: png_pipeline.PngImage, points: list[tuple[float, float]], color: Color) -> None:
    if len(points) < 3:
        return
    min_x = max(0, int(min(p[0] for p in points)))
    max_x = min(image.width - 1, int(max(p[0] for p in points)) + 1)
    min_y = max(0, int(min(p[1] for p in points)))
    max_y = min(image.height - 1, int(max(p[1] for p in points)) + 1)
    for y in range(min_y, max_y + 1):
        intersections: list[float] = []
        for i, p1 in enumerate(points):
            p2 = points[(i + 1) % len(points)]
            if (p1[1] <= y < p2[1]) or (p2[1] <= y < p1[1]):
                if p2[1] != p1[1]:
                    x = p1[0] + (y - p1[1]) * (p2[0] - p1[0]) / (p2[1] - p1[1])
                    intersections.append(x)
        intersections.sort()
        for i in range(0, len(intersections), 2):
            if i + 1 >= len(intersections):
                continue
            for x in range(max(min_x, int(intersections[i])), min(max_x, int(intersections[i + 1]) + 1) + 1):
                blend_pixel(image, x, y, color)


def draw_line(image: png_pipeline.PngImage, p1: tuple[float, float], p2: tuple[float, float], width: int, color: Color) -> None:
    x1, y1 = p1
    x2, y2 = p2
    length = max(1, int(math.hypot(x2 - x1, y2 - y1)))
    for step in range(length + 1):
        t = step / length
        x = x1 + (x2 - x1) * t
        y = y1 + (y2 - y1) * t
        fill_circle(image, x, y, width / 2, color)


def project(x: float, y: float, tile_w: float, tile_h: float, ox: float, oy: float) -> tuple[float, float]:
    return (x - y) * (tile_w / 2) + ox, (x + y) * (tile_h / 2) + oy


def battle_metrics(width: int, height: int, grid: dict[str, Any]) -> dict[str, float]:
    gw = int(grid.get("width_cells", 16))
    gh = int(grid.get("height_cells", 9))
    span = max(1, gw + gh - 2)
    tile_w = min((width - 150) * 2 / span, (height - 110) * 4 / span)
    tile_w = max(62, min(104, tile_w))
    tile_h = tile_w * 0.54
    raw = [
        ((0 - 0) * tile_w / 2, (0 + 0) * tile_h / 2),
        (((gw - 1) - 0) * tile_w / 2, ((gw - 1) + 0) * tile_h / 2),
        ((0 - (gh - 1)) * tile_w / 2, (0 + (gh - 1)) * tile_h / 2),
        (((gw - 1) - (gh - 1)) * tile_w / 2, ((gw - 1) + (gh - 1)) * tile_h / 2),
    ]
    min_x = min(p[0] for p in raw)
    max_x = max(p[0] for p in raw)
    min_y = min(p[1] for p in raw)
    max_y = max(p[1] for p in raw)
    return {
        "tile_w": tile_w,
        "tile_h": tile_h,
        "offset_x": (width - (max_x - min_x)) / 2 - min_x,
        "offset_y": (height - (max_y - min_y)) / 2 - min_y + 20,
    }


def diamond(cx: float, cy: float, w: float, h: float) -> list[tuple[float, float]]:
    return [(cx, cy - h / 2), (cx + w / 2, cy), (cx, cy + h / 2), (cx - w / 2, cy)]


def iter_path_cells(points: list[dict[str, Any]]) -> list[tuple[int, int]]:
    cells: list[tuple[int, int]] = []
    for i in range(len(points) - 1):
        ax, ay = int(points[i]["x"]), int(points[i]["y"])
        bx, by = int(points[i + 1]["x"]), int(points[i + 1]["y"])
        dx = 1 if bx > ax else -1 if bx < ax else 0
        dy = 1 if by > ay else -1 if by < ay else 0
        x, y = ax, ay
        cells.append((x, y))
        while x != bx or y != by:
            if x != bx:
                x += dx
            if y != by:
                y += dy
            cells.append((x, y))
    seen: set[tuple[int, int]] = set()
    ordered: list[tuple[int, int]] = []
    for cell in cells:
        if cell not in seen:
            ordered.append(cell)
            seen.add(cell)
    return ordered


def build_battle_control(battle: dict[str, Any], path: Path) -> None:
    image = new_image(1280, 720, rgba("101010"))
    grid = battle.get("grid", {})
    metrics = battle_metrics(image.width, image.height, grid)
    tile_w = metrics["tile_w"]
    tile_h = metrics["tile_h"]
    ox = metrics["offset_x"]
    oy = metrics["offset_y"]
    gw = int(grid.get("width_cells", 16))
    gh = int(grid.get("height_cells", 9))
    for y in range(gh):
        for x in range(gw):
            cx, cy = project(x, y, tile_w, tile_h, ox, oy)
            fill_polygon(image, diamond(cx, cy, tile_w * 0.96, tile_h * 0.96), rgba("242424", 255))
    waypoints = ((battle.get("paths") or [{}])[0]).get("waypoints", [])
    for x, y in iter_path_cells(waypoints):
        cx, cy = project(x, y, tile_w, tile_h, ox, oy)
        fill_polygon(image, diamond(cx, cy, tile_w * 1.08, tile_h * 1.08), rgba("ffffff", 255))
    for cell in suggested_slots():
        cx, cy = project(cell[0], cell[1], tile_w, tile_h, ox, oy)
        stroke_circle(image, cx, cy, 20, 7, rgba("48b8ff", 255))
    core = battle.get("core_target", {}).get("position", {"x": 1, "y": 6})
    cx, cy = project(core["x"], core["y"], tile_w, tile_h, ox, oy)
    fill_circle(image, cx, cy, 28, rgba("ffd24d", 255))
    for target in battle.get("optional_targets", []):
        pos = target.get("position", {})
        cx, cy = project(pos.get("x", 0), pos.get("y", 0), tile_w, tile_h, ox, oy)
        fill_rect(image, int(cx - 18), int(cy - 18), 36, 36, rgba("8ff0a4", 255))
    first = waypoints[0] if waypoints else {"x": 15, "y": 4}
    sx, sy = project(first["x"], first["y"], tile_w, tile_h, ox, oy)
    fill_polygon(image, [(sx + 42, sy), (sx + 4, sy - 24), (sx + 4, sy + 24)], rgba("ff4c66", 255))
    png_pipeline.write_png(path, image)


def suggested_slots() -> list[tuple[int, int]]:
    return [(12, 3), (9, 3), (8, 1), (5, 1), (6, 5), (3, 5)]


def build_battle_reference(battle: dict[str, Any], path: Path) -> None:
    image = new_image(1280, 720, rgba("182016"))
    grid = battle.get("grid", {})
    metrics = battle_metrics(image.width, image.height, grid)
    tile_w = metrics["tile_w"]
    tile_h = metrics["tile_h"]
    ox = metrics["offset_x"]
    oy = metrics["offset_y"]

    # Player-facing reference art: full terrain scene, not a visible logic grid.
    fill_polygon(
        image,
        [(0, 470), (180, 390), (360, 430), (590, 338), (790, 386), (1280, 250), (1280, 720), (0, 720)],
        rgba("2f3e2a", 210),
    )
    fill_polygon(
        image,
        [(0, 0), (1280, 0), (1280, 220), (1020, 250), (760, 190), (420, 235), (210, 168), (0, 220)],
        rgba("263323", 190),
    )
    fill_ellipse(image, 145, 610, 380, 120, rgba("455c31", 90))
    fill_ellipse(image, 1010, 135, 330, 92, rgba("20271f", 160))
    fill_ellipse(image, 1090, 560, 300, 150, rgba("161224", 145))

    for i in range(170):
        x = (i * 97 + 43) % image.width
        y = (i * 53 + 71) % image.height
        if 110 < y < 650:
            color = "556847" if i % 3 else "6b6947"
            fill_circle(image, x, y, 1 + (i % 3), rgba(color, 70))

    waypoints = ((battle.get("paths") or [{}])[0]).get("waypoints", [])
    path_points = [project(p["x"], p["y"], tile_w, tile_h, ox, oy) for p in waypoints]
    for a, b in zip(path_points, path_points[1:]):
        draw_line(image, a, b, int(tile_w * 0.82), rgba("4c4030", 170))
    for a, b in zip(path_points, path_points[1:]):
        draw_line(image, a, b, int(tile_w * 0.62), rgba("8d7351", 245))
    for a, b in zip(path_points, path_points[1:]):
        draw_line(image, a, b, int(tile_w * 0.38), rgba("b9955d", 130))
    for a, b in zip(path_points, path_points[1:]):
        draw_line(image, a, b, 7, rgba("f2cc78", 82))

    for index, (cx, cy) in enumerate(path_points):
        fill_circle(image, cx, cy, 28 + (index % 2) * 8, rgba("b9955d", 90))

    for cell in suggested_slots():
        cx, cy = project(cell[0], cell[1], tile_w, tile_h, ox, oy)
        fill_ellipse(image, cx, cy + 2, 34, 15, rgba("161d18", 150))
        stroke_circle(image, cx, cy, 20, 3, rgba("e5c878", 150))
        stroke_circle(image, cx, cy, 10, 2, rgba("64d2c8", 110))

    for x, y in [(13, 1), (11, 7), (7, 7), (4, 0), (2, 3), (14, 6), (8, 0), (1, 4), (12, 5)]:
        cx, cy = project(x, y, tile_w, tile_h, ox, oy)
        draw_prop(image, cx, cy, (x + y) % 3)

    core = battle.get("core_target", {}).get("position", {"x": 1, "y": 6})
    cx, cy = project(core["x"], core["y"], tile_w, tile_h, ox, oy)
    fill_ellipse(image, cx, cy + 4, 64, 24, rgba("080908", 100))
    fill_circle(image, cx, cy - 28, 38, rgba("ffd37a", 100))
    fill_rect(image, int(cx - 28), int(cy - 52), 56, 50, rgba("b78136", 255))
    fill_rect(image, int(cx - 14), int(cy - 68), 28, 22, rgba("ffd37a", 255))

    for target in battle.get("optional_targets", []):
        pos = target.get("position", {})
        tx, ty = project(pos.get("x", 0), pos.get("y", 0), tile_w, tile_h, ox, oy)
        fill_ellipse(image, tx, ty + 4, 42, 16, rgba("080908", 90))
        fill_rect(image, int(tx - 9), int(ty - 72), 18, 60, rgba("9b743a", 255))
        fill_circle(image, tx, ty - 72, 16, rgba("ffd37a", 180))

    first = waypoints[0] if waypoints else {"x": 15, "y": 4}
    sx, sy = project(first["x"], first["y"], tile_w, tile_h, ox, oy)
    fill_circle(image, sx + 72, sy, 112, rgba("1b1026", 150))
    fill_circle(image, sx + 72, sy, 54, rgba("5d4aff", 85))

    fill_polygon(image, [(0, 0), (1280, 0), (1280, 36), (0, 96)], rgba("050705", 80))
    fill_polygon(image, [(0, 720), (0, 646), (1280, 690), (1280, 720)], rgba("050705", 95))
    png_pipeline.write_png(path, image)


def draw_prop(image: png_pipeline.PngImage, x: float, y: float, variant: int) -> None:
    if variant == 0:
        fill_rect(image, int(x - 10), int(y - 38), 20, 36, rgba("8a6b39", 255))
        fill_circle(image, x, y - 44, 13, rgba("ffd37a", 170))
    elif variant == 1:
        fill_polygon(image, [(x - 28, y), (x + 12, y - 22), (x + 30, y - 3), (x - 8, y + 17)], rgba("5a574b", 230))
        fill_circle(image, x + 6, y - 5, 5, rgba("d2c4a4", 130))
    else:
        draw_line(image, (x - 36, y + 8), (x + 42, y - 12), 4, rgba("4a4232", 220))
        fill_circle(image, x - 37, y + 8, 5, rgba("d6b46c", 160))
        fill_circle(image, x + 43, y - 12, 5, rgba("d6b46c", 160))


def build_strategic_control(map_data: dict[str, Any], path: Path) -> None:
    image = new_image(1280, 720, rgba("151817"))
    for region in map_data.get("dark_regions", []):
        points = [(p["x"], p["y"]) for p in region.get("polygon", [])]
        fill_polygon(image, points, rgba("05070a", 210))
    nodes = {node.get("stable_internal_id"): node for node in map_data.get("nodes", [])}
    for line in map_data.get("supply_lines", []):
        a = nodes.get(line.get("from_node_id"))
        b = nodes.get(line.get("to_node_id"))
        if not a or not b:
            continue
        pa = a.get("position", {})
        pb = b.get("position", {})
        draw_line(image, (pa.get("x", 0), pa.get("y", 0)), (pb.get("x", 0), pb.get("y", 0)), 18, rgba("c8a358", 170))
        draw_line(image, (pa.get("x", 0), pa.get("y", 0)), (pb.get("x", 0), pb.get("y", 0)), 7, rgba("ffe1a1", 190))
    for edge in map_data.get("threat_edges", []):
        pos = edge.get("position", {})
        fill_circle(image, pos.get("x", 0), pos.get("y", 0), 120, rgba("563a8f", 90))
        stroke_circle(image, pos.get("x", 0), pos.get("y", 0), 82, 8, rgba("ff5b66", 190))
    for node in map_data.get("nodes", []):
        pos = node.get("position", {})
        kind = node.get("kind")
        color = "ffd24d" if kind == "main_city" else "ff4c66" if kind == "battle_hotspot" else "48d6c9" if kind == "research_facility" else "8ff0a4"
        radius = 34 if kind == "main_city" else 26
        fill_circle(image, pos.get("x", 0), pos.get("y", 0), radius + 11, rgba("ffffff", 70))
        fill_circle(image, pos.get("x", 0), pos.get("y", 0), radius, rgba(color, 230))
    png_pipeline.write_png(path, image)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map", default=str(DEFAULT_MAP))
    parser.add_argument("--battle", default=str(DEFAULT_BATTLE))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    map_path = Path(args.map)
    battle_path = Path(args.battle)
    output_dir = Path(args.output_dir)
    if not map_path.is_absolute():
        map_path = ROOT / map_path
    if not battle_path.is_absolute():
        battle_path = ROOT / battle_path
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir

    map_data = load_json(map_path)
    battle = load_json(battle_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "strategic_control_sketch": output_dir / "mvp_strategic_control_sketch.png",
        "battle_control_sketch": output_dir / "mvp_battle_control_sketch.png",
        "battle_reference_board": output_dir / "mvp_battle_reference_board.png",
    }
    build_strategic_control(map_data, files["strategic_control_sketch"])
    build_battle_control(battle, files["battle_control_sketch"])
    build_battle_reference(battle, files["battle_reference_board"])
    items = []
    for role, file_path in files.items():
        items.append(
            {
                "role": role,
                "url": f"/assets/map_visual_reference/{file_path.name}",
                "local_path": file_path.relative_to(ROOT).as_posix(),
                "width": 1280,
                "height": 720,
                "sha256": sha256_file(file_path),
                "source_kind": "deterministic_logical_map_reference",
            }
        )
    manifest = {
        "schema_version": "map_visual_reference_pack.v0.1",
        "pack_id": "mvp_gray_lantern_map_visual_reference_v0_1",
        "source_map": map_path.relative_to(ROOT).as_posix(),
        "source_battle_config": battle_path.relative_to(ROOT).as_posix(),
        "usage": {
            "authority": "reference_only",
            "logic_source": "battle_config_and_initial_map_remain_authoritative",
            "next_step": "send control sketch plus style references to image provider, then re-align and publish visual layers",
        },
        "items": items,
    }
    manifest_path = output_dir / "map_visual_reference_manifest.v0.1.json"
    write_json(manifest_path, manifest)
    print(f"Wrote {manifest_path}")
    for item in items:
        print(f"- {item['role']}: {item['local_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
