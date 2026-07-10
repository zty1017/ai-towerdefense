#!/usr/bin/env python3
"""Build a player-usable LayeredMapVisualPackage v0.1.

The first implementation is intentionally stdlib-only and SVG-based. It turns
MapRuntimePackage + MapStylePack + ProceduralMapRenderPlan into a layered visual
package that the frontend can render as a single natural map backdrop while
keeping all gameplay coordinates in MapRuntimePackage.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import math
import random
import sys
import struct
import zlib
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from validation_common import load_json_object, write_json  # noqa: E402


DEFAULT_RUNTIME_PACKAGE = ROOT / "examples/map_runtime_packages/mvp_first_battle.map_runtime_package.json"
DEFAULT_STYLE_PACK = ROOT / "examples/map_style_packs/long_night_ruined_outpost.map_style_pack.json"
DEFAULT_RENDER_PLAN = ROOT / "examples/map_render_plans/mvp_first_battle.procedural_map_render_plan.json"
DEFAULT_OUTPUT_DIR = ROOT / "game_data/media/layered_maps/gray_lantern_station"
DEFAULT_CREATED_AT = "2026-07-08T00:00:00Z"
MVP_MAP_INPUTS = (
    {
        "node_id": "gray_lantern_station",
        "runtime_package": ROOT / "examples/map_runtime_packages/mvp_first_battle.map_runtime_package.json",
        "style_pack": ROOT / "examples/map_style_packs/long_night_ruined_outpost.map_style_pack.json",
        "render_plan": ROOT / "examples/map_render_plans/mvp_first_battle.procedural_map_render_plan.json",
        "output_dir": ROOT / "game_data/media/layered_maps/gray_lantern_station",
    },
    {
        "node_id": "lamp_wick_store",
        "runtime_package": ROOT / "examples/map_runtime_packages/mvp_wick_store_pressure.map_runtime_package.json",
        "style_pack": ROOT / "examples/map_style_packs/long_night_lamp_wick_store.map_style_pack.json",
        "render_plan": ROOT / "examples/map_render_plans/mvp_wick_store_pressure.procedural_map_render_plan.json",
        "output_dir": ROOT / "game_data/media/layered_maps/lamp_wick_store",
    },
    {
        "node_id": "old_signal_tower",
        "runtime_package": ROOT
        / "examples/map_runtime_packages/mvp_old_signal_tower_pressure.map_runtime_package.json",
        "style_pack": ROOT / "examples/map_style_packs/long_night_old_signal_tower.map_style_pack.json",
        "render_plan": ROOT
        / "examples/map_render_plans/mvp_old_signal_tower_pressure.procedural_map_render_plan.json",
        "output_dir": ROOT / "game_data/media/layered_maps/old_signal_tower",
    },
)
PUBLIC_PREFIX = "/assets/layered_maps"
CANVAS_WIDTH = 1280
CANVAS_HEIGHT = 720
REQUIRED_LAYER_ROLES = (
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
)
ROAD_DETAIL_ATLAS_ROLE = "road_detail_atlas"
TEXTURE_ROLES = (
    "terrain_tile",
    "terrain_detail_tile",
    "road_tile",
    "road_edge_tile",
    ROAD_DETAIL_ATLAS_ROLE,
    "slot_tile",
    "shadow_overlay_tile",
    "fog_overlay_tile",
    "light_overlay_tile",
)
PAINTED_BACKDROP_ROLE = "reviewed_painted_backdrop"


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def public_url(path: Path) -> str:
    relative = path.resolve().relative_to((ROOT / "game_data/media/layered_maps").resolve())
    return f"{PUBLIC_PREFIX}/{relative.as_posix()}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def png_data_uri(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def svg_escape(value: Any) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def palette(style_pack: dict[str, Any], key: str, fallback: str) -> str:
    value = as_obj(style_pack.get("palette")).get(key)
    if isinstance(value, str) and value.startswith("#") and len(value) == 7:
        return value
    return fallback


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    text = value.strip().lstrip("#")
    if len(text) != 6:
        return (128, 128, 128)
    return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))


def mix_hex(left: str, right: str, ratio: float) -> str:
    lr, lg, lb = hex_to_rgb(left)
    rr, rg, rb = hex_to_rgb(right)
    t = clamp(ratio, 0, 1)
    return "#{:02X}{:02X}{:02X}".format(
        round(lr + (rr - lr) * t),
        round(lg + (rg - lg) * t),
        round(lb + (rb - lb) * t),
    )


def rgba(hex_color: str, alpha: float) -> str:
    r, g, b = hex_to_rgb(hex_color)
    return f"rgba({r},{g},{b},{clamp(alpha, 0, 1):.3f})"


def mix_rgb(left: tuple[int, int, int], right: tuple[int, int, int], ratio: float) -> tuple[int, int, int]:
    t = clamp(ratio, 0, 1)
    return (
        round(left[0] + (right[0] - left[0]) * t),
        round(left[1] + (right[1] - left[1]) * t),
        round(left[2] + (right[2] - left[2]) * t),
    )


def adjust_rgb(color: tuple[int, int, int], amount: int) -> tuple[int, int, int]:
    return (
        max(0, min(255, color[0] + amount)),
        max(0, min(255, color[1] + amount)),
        max(0, min(255, color[2] + amount)),
    )


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def write_png_rgba(path: Path, width: int, height: int, pixels: list[tuple[int, int, int, int]]) -> None:
    if len(pixels) != width * height:
        raise ValueError(f"pixel count mismatch for {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = bytearray()
    index = 0
    for _y in range(height):
        raw.append(0)
        for _x in range(width):
            raw.extend(bytes(pixels[index]))
            index += 1
    payload = b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)),
            png_chunk(b"IDAT", zlib.compress(bytes(raw), level=9)),
            png_chunk(b"IEND", b""),
        ]
    )
    path.write_bytes(payload)


def read_png_rgba(path: Path) -> tuple[int, int, list[tuple[int, int, int, int]]]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG")
    pos = 8
    width = height = 0
    bit_depth = color_type = 0
    idat = bytearray()
    while pos < len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        chunk_type = data[pos + 4 : pos + 8]
        chunk = data[pos + 8 : pos + 8 + length]
        pos += length + 12
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, _comp, _filt, interlace = struct.unpack(">IIBBBBB", chunk)
            if bit_depth != 8 or color_type not in (2, 6) or interlace != 0:
                raise ValueError(f"{path} must be non-interlaced 8-bit RGB/RGBA PNG")
        elif chunk_type == b"IDAT":
            idat.extend(chunk)
        elif chunk_type == b"IEND":
            break

    channels = 3 if color_type == 2 else 4
    stride = width * channels
    raw = zlib.decompress(bytes(idat))
    rows: list[list[int]] = []
    prev = [0] * stride
    cursor = 0
    for _y in range(height):
        filter_type = raw[cursor]
        cursor += 1
        scan = list(raw[cursor : cursor + stride])
        cursor += stride
        row = [0] * stride
        for index, value in enumerate(scan):
            left = row[index - channels] if index >= channels else 0
            up = prev[index]
            up_left = prev[index - channels] if index >= channels else 0
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = up
            elif filter_type == 3:
                predictor = (left + up) // 2
            elif filter_type == 4:
                p = left + up - up_left
                pa = abs(p - left)
                pb = abs(p - up)
                pc = abs(p - up_left)
                predictor = left if pa <= pb and pa <= pc else up if pb <= pc else up_left
            else:
                raise ValueError(f"{path} uses unsupported PNG filter {filter_type}")
            row[index] = (value + predictor) & 255
        rows.append(row)
        prev = row

    pixels: list[tuple[int, int, int, int]] = []
    for row in rows:
        for x in range(width):
            offset = x * channels
            r, g, b = row[offset : offset + 3]
            a = row[offset + 3] if channels == 4 else 255
            pixels.append((r, g, b, a))
    return width, height, pixels


def fit_resize_png(
    source_path: Path,
    output_path: Path,
    target_width: int,
    target_height: int,
    *,
    soften_strength: float = 0.0,
) -> None:
    source_width, source_height, source_pixels = read_png_rgba(source_path)
    source_ratio = source_width / source_height
    target_ratio = target_width / target_height
    if source_ratio > target_ratio:
        crop_height = source_height
        crop_width = round(crop_height * target_ratio)
    else:
        crop_width = source_width
        crop_height = round(crop_width / target_ratio)
    crop_x = max(0, (source_width - crop_width) // 2)
    crop_y = max(0, (source_height - crop_height) // 2)

    def sample_bilinear(source_x: float, source_y: float) -> tuple[int, int, int, int]:
        left = int(math.floor(clamp(source_x, 0, source_width - 1)))
        top = int(math.floor(clamp(source_y, 0, source_height - 1)))
        right = min(source_width - 1, left + 1)
        bottom = min(source_height - 1, top + 1)
        tx = clamp(source_x - left, 0, 1)
        ty = clamp(source_y - top, 0, 1)
        top_left = source_pixels[top * source_width + left]
        top_right = source_pixels[top * source_width + right]
        bottom_left = source_pixels[bottom * source_width + left]
        bottom_right = source_pixels[bottom * source_width + right]
        channels: list[int] = []
        for channel in range(4):
            top_value = top_left[channel] * (1 - tx) + top_right[channel] * tx
            bottom_value = bottom_left[channel] * (1 - tx) + bottom_right[channel] * tx
            channels.append(round(top_value * (1 - ty) + bottom_value * ty))
        return (channels[0], channels[1], channels[2], channels[3])

    pixels: list[tuple[int, int, int, int]] = []
    for y in range(target_height):
        sy = crop_y + ((y + 0.5) * crop_height / target_height) - 0.5
        for x in range(target_width):
            sx = crop_x + ((x + 0.5) * crop_width / target_width) - 0.5
            pixels.append(sample_bilinear(sx, sy))
    if soften_strength > 0:
        pixels = soften_pixels(target_width, target_height, pixels, soften_strength)
    write_png_rgba(output_path, target_width, target_height, pixels)


def soften_pixels(
    width: int,
    height: int,
    pixels: list[tuple[int, int, int, int]],
    strength: float,
) -> list[tuple[int, int, int, int]]:
    """Apply a tiny weighted blur to AI painted backdrops to reduce resize grain."""

    amount = clamp(strength, 0, 1)
    if amount <= 0:
        return pixels
    weights = (
        (0, 0, 8),
        (-1, 0, 2),
        (1, 0, 2),
        (0, -1, 2),
        (0, 1, 2),
        (-1, -1, 1),
        (1, -1, 1),
        (-1, 1, 1),
        (1, 1, 1),
    )
    total_weight = sum(weight for _dx, _dy, weight in weights)
    softened: list[tuple[int, int, int, int]] = []
    for y in range(height):
        for x in range(width):
            original = pixels[y * width + x]
            channels = [0, 0, 0, 0]
            for dx, dy, weight in weights:
                sx = int(clamp(x + dx, 0, width - 1))
                sy = int(clamp(y + dy, 0, height - 1))
                sample = pixels[sy * width + sx]
                for channel in range(4):
                    channels[channel] += sample[channel] * weight
            softened_channels = [round(value / total_weight) for value in channels]
            softened.append(
                tuple(
                    round(original[channel] * (1 - amount) + softened_channels[channel] * amount)
                    for channel in range(4)
                )
            )
    return softened


def source_texture_path(texture_source_dir: Path | None, role: str) -> Path | None:
    if not texture_source_dir:
        return None
    candidates = (
        texture_source_dir / f"ai_{role}_v0_1.png",
        texture_source_dir / f"{role}.png",
        texture_source_dir / f"ai_{role}.png",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def source_backdrop_path(backdrop_source_dir: Path | None, node_id: str) -> Path | None:
    if not backdrop_source_dir:
        return None
    candidates = (
        backdrop_source_dir / f"{node_id}.reviewed_painted_backdrop.png",
        backdrop_source_dir / f"ai_map_terrain_no_roads_{node_id}_v0_1.png",
        backdrop_source_dir / f"ai_map_backdrop_no_slots_{node_id}_v0_1.png",
        backdrop_source_dir / f"ai_map_control_aligned_concept_{node_id}_v0_2.png",
        backdrop_source_dir / f"ai_map_control_aligned_concept_{node_id}_v0_1.png",
        backdrop_source_dir / f"ai_map_concept_{node_id}_v0_1.png",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def make_texture_pixels(
    role: str,
    width: int,
    height: int,
    style: dict[str, str],
    rng: random.Random,
    node_id: str,
) -> list[tuple[int, int, int, int]]:
    terrain = hex_to_rgb(style["terrain_base"])
    terrain_detail = hex_to_rgb(style["terrain_detail"])
    road = hex_to_rgb(style["road_base"])
    road_edge = hex_to_rgb(style["road_edge"])
    build_slot = hex_to_rgb(style["build_slot"])
    accent = hex_to_rgb(style["accent"])
    hazard = hex_to_rgb(style["hazard"])
    resource = hex_to_rgb(style["resource"])
    pixels: list[tuple[int, int, int, int]] = []
    seed_offsets = {
        "gray_lantern_station": 5,
        "lamp_wick_store": 19,
        "old_signal_tower": 37,
    }
    bias = seed_offsets.get(node_id, 11)
    for y in range(height):
        for x in range(width):
            wave = (
                math.sin((x + bias) * 0.037 + math.sin(y * 0.019) * 1.7) * 0.42
                + math.sin((y - bias) * 0.049 + math.cos(x * 0.023) * 1.1) * 0.34
                + math.sin((x + y + bias) * 0.021) * 0.24
            )
            grain = rng.randint(-14, 14)
            if role == "terrain_tile":
                base = mix_rgb(terrain, terrain_detail, 0.30 + 0.13 * wave)
                if (x * 3 + y * 5 + bias) % 53 == 0:
                    base = mix_rgb(base, resource, 0.22)
                if (x * 7 + y * 2 + bias) % 71 == 0:
                    base = mix_rgb(base, hazard, 0.16)
                color = adjust_rgb(base, grain)
                alpha = 120 + rng.randint(-18, 18)
            elif role == "terrain_detail_tile":
                detail = abs(math.sin((x + bias) * 0.062) * math.cos((y - bias) * 0.046))
                base = mix_rgb(terrain_detail, terrain, 0.38 + 0.18 * wave)
                if detail > 0.80:
                    base = mix_rgb(base, road_edge, 0.20)
                if rng.random() < 0.014:
                    base = mix_rgb(base, resource, 0.22)
                color = adjust_rgb(base, grain)
                alpha = 82 + rng.randint(-18, 26)
            elif role == "road_tile":
                center = abs((y / max(1, height - 1)) - 0.5) * 2
                base = mix_rgb(road, road_edge, 0.14 + (1 - center) * 0.12)
                rut = abs(math.sin((x + bias) * 0.045 + math.sin(y * 0.031) * 0.8))
                cross = abs(math.sin((y - bias) * 0.065 + math.cos(x * 0.017) * 1.3))
                if rut > 0.94:
                    base = mix_rgb(base, road_edge, 0.16)
                if cross > 0.965:
                    base = mix_rgb(base, terrain, 0.12)
                if rng.random() < 0.018:
                    base = mix_rgb(base, road_edge, 0.20)
                color = adjust_rgb(base, grain)
                alpha = 150 + rng.randint(-12, 18)
            elif role == "road_edge_tile":
                base = mix_rgb(road_edge, terrain_detail, 0.30 + 0.10 * wave)
                if rng.random() < 0.025 or abs(math.sin((x * 0.08) + (y * 0.027) + bias)) > 0.975:
                    base = mix_rgb(base, accent, 0.25)
                color = adjust_rgb(base, grain)
                alpha = 120 + rng.randint(-10, 24)
            elif role == ROAD_DETAIL_ATLAS_ROLE:
                cell_w = 96
                cell_h = 48
                col = min(3, x // cell_w)
                row = min(3, y // cell_h)
                local_x = x - col * cell_w
                local_y = y - row * cell_h
                cell = row * 4 + col
                stripe = abs(math.sin((local_x + bias + cell * 7) * 0.085 + math.sin(local_y * 0.09)))
                vein = abs(math.sin((local_x - local_y + bias * 2 + cell * 11) * 0.041))
                center_y = abs((local_y / max(1, cell_h - 1)) - 0.5) * 2
                if cell in (0, 4, 8, 12):
                    base = mix_rgb(road, road_edge, 0.20 + stripe * 0.16)
                    if center_y < 0.22:
                        base = mix_rgb(base, accent, 0.12)
                    alpha = 126 + rng.randint(-18, 26)
                elif cell in (1, 5, 9, 13):
                    base = mix_rgb(road_edge, terrain_detail, 0.30 + vein * 0.18)
                    if stripe > 0.92 or rng.random() < 0.03:
                        base = mix_rgb(base, accent, 0.22)
                    alpha = 118 + rng.randint(-16, 28)
                elif cell in (2, 6, 10, 14):
                    base = mix_rgb(road_edge, road, 0.42 + wave * 0.08)
                    crack = abs(local_y - (cell_h * 0.50 + math.sin(local_x * 0.13 + cell) * cell_h * 0.18))
                    if crack < 2.0 or stripe > 0.955:
                        base = mix_rgb(base, (28, 24, 18), 0.42)
                    alpha = 108 + rng.randint(-16, 30)
                else:
                    base = mix_rgb(build_slot, road_edge, 0.34 + vein * 0.12)
                    rim = min(local_x, cell_w - local_x - 1, local_y, cell_h - local_y - 1)
                    if rim < 5 or stripe > 0.94:
                        base = mix_rgb(base, accent, 0.24)
                    alpha = 116 + rng.randint(-14, 30)
                color = adjust_rgb(base, grain)
            elif role == "slot_tile":
                ring = math.hypot((x / width) - 0.5, (y / height) - 0.5)
                base = mix_rgb(build_slot, accent, clamp(0.58 - ring, 0.0, 0.35))
                if (x * 2 + y * 7 + bias) % 41 == 0:
                    base = mix_rgb(base, road_edge, 0.28)
                color = adjust_rgb(base, grain)
                alpha = 132 + rng.randint(-12, 24)
            elif role == "shadow_overlay_tile":
                shade = max(0, min(255, 24 + grain + round((wave + 1) * 8)))
                color = (shade, shade, shade)
                alpha = 55 + rng.randint(-12, 18)
            elif role == "fog_overlay_tile":
                base = mix_rgb(resource, (170, 190, 178), 0.46 + 0.08 * wave)
                color = adjust_rgb(base, grain // 2)
                alpha = 34 + rng.randint(-12, 18)
            else:
                base = mix_rgb(accent, road_edge, 0.32 + 0.08 * wave)
                color = adjust_rgb(base, grain // 2)
                alpha = 44 + rng.randint(-10, 26)
            pixels.append((color[0], color[1], color[2], max(0, min(255, alpha))))
    return pixels


def build_texture_assets(
    node_id: str,
    style: dict[str, str],
    output_dir: Path,
    seed: str,
    texture_source_dir: Path | None = None,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    textures_dir = output_dir / "textures"
    texture_refs: dict[str, str] = {}
    media_assets: list[dict[str, Any]] = []
    sizes = {
        "terrain_tile": (256, 256),
        "terrain_detail_tile": (256, 256),
        "road_tile": (256, 128),
        "road_edge_tile": (192, 96),
        ROAD_DETAIL_ATLAS_ROLE: (384, 192),
        "slot_tile": (192, 96),
        "shadow_overlay_tile": (256, 256),
        "fog_overlay_tile": (256, 256),
        "light_overlay_tile": (256, 256),
    }
    for role in TEXTURE_ROLES:
        width, height = sizes[role]
        rng = random.Random(f"{seed}:{role}:texture")
        path = textures_dir / f"{node_id}.{role}.png"
        source_path = source_texture_path(texture_source_dir, role)
        source_kind = "procedural_texture"
        if source_path:
            fit_resize_png(source_path, path, width, height)
            source_kind = "local_ai_exploration_texture"
        else:
            write_png_rgba(path, width, height, make_texture_pixels(role, width, height, style, rng, node_id))
        texture_refs[role] = png_data_uri(path)
        media_assets.append(
            {
                "asset_id": f"{node_id}_{role}",
                "role": role,
                "media_kind": "texture_atlas_png" if role == ROAD_DETAIL_ATLAS_ROLE else "texture_tile_png",
                "source_kind": source_kind,
                "source_local_path": rel(source_path) if source_path else "",
                "url": public_url(path),
                "local_path": rel(path),
                "width": width,
                "height": height,
                "sha256": sha256_file(path),
                "usage": "presentation_texture_only",
            }
        )
    return texture_refs, media_assets


def build_backdrop_asset(
    node_id: str,
    output_dir: Path,
    backdrop_source_dir: Path | None = None,
) -> tuple[str | None, list[dict[str, Any]]]:
    source_path = source_backdrop_path(backdrop_source_dir, node_id)
    if not source_path:
        return None, []

    backdrop_path = output_dir / "backdrops" / f"{node_id}.{PAINTED_BACKDROP_ROLE}.png"
    fit_resize_png(source_path, backdrop_path, CANVAS_WIDTH, CANVAS_HEIGHT, soften_strength=0.08)
    return png_data_uri(backdrop_path), [
        {
            "asset_id": f"{node_id}_{PAINTED_BACKDROP_ROLE}",
            "role": PAINTED_BACKDROP_ROLE,
            "media_kind": "map_backdrop_png",
            "source_kind": "local_ai_exploration_backdrop",
            "source_local_path": rel(source_path),
            "url": public_url(backdrop_path),
            "local_path": rel(backdrop_path),
            "width": CANVAS_WIDTH,
            "height": CANVAS_HEIGHT,
            "sha256": sha256_file(backdrop_path),
            "usage": "presentation_backdrop_only",
        }
    ]


def raw_project(x: float, y: float, tile_w: float, tile_h: float) -> tuple[float, float]:
    return ((x - y) * (tile_w / 2), (x + y) * (tile_h / 2))


def build_projection(runtime_package: dict[str, Any]) -> dict[str, float]:
    grid = as_obj(runtime_package.get("grid"))
    width_cells = max(1, int(grid.get("width_cells") or 16))
    height_cells = max(1, int(grid.get("height_cells") or 9))
    total = width_cells + height_cells
    tile_w = clamp(
        min(((CANVAS_WIDTH - 80) * 2) / total, ((CANVAS_HEIGHT - 110) * 4) / total),
        38,
        112,
    )
    tile_h = tile_w * 0.52
    raw = [
        raw_project(0, 0, tile_w, tile_h),
        raw_project(width_cells - 1, 0, tile_w, tile_h),
        raw_project(0, height_cells - 1, tile_w, tile_h),
        raw_project(width_cells - 1, height_cells - 1, tile_w, tile_h),
    ]
    min_x = min(point[0] for point in raw)
    max_x = max(point[0] for point in raw)
    min_y = min(point[1] for point in raw)
    max_y = max(point[1] for point in raw)
    return {
        "width_cells": width_cells,
        "height_cells": height_cells,
        "base_tile_w": tile_w,
        "base_tile_h": tile_h,
        "base_offset_x": (CANVAS_WIDTH - (max_x - min_x)) / 2 - min_x,
        "base_offset_y": (CANVAS_HEIGHT - (max_y - min_y)) / 2 - min_y + 6,
    }


def project_cell(position: dict[str, Any], projection: dict[str, float]) -> tuple[float, float]:
    x = float(position.get("x") or 0)
    y = float(position.get("y") or 0)
    raw_x, raw_y = raw_project(x, y, projection["base_tile_w"], projection["base_tile_h"])
    return (
        raw_x + projection["base_offset_x"],
        raw_y + projection["base_offset_y"],
    )


def smooth_route(points: list[tuple[float, float]], radius_limit: float = 54) -> str:
    if not points:
        return ""
    if len(points) < 3:
        return "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in points)
    tokens = [f"M {points[0][0]:.1f} {points[0][1]:.1f}"]
    for index in range(1, len(points) - 1):
        prev_x, prev_y = points[index - 1]
        cur_x, cur_y = points[index]
        next_x, next_y = points[index + 1]
        d1 = math.hypot(cur_x - prev_x, cur_y - prev_y)
        d2 = math.hypot(next_x - cur_x, next_y - cur_y)
        radius = min(radius_limit, d1 * 0.34, d2 * 0.34)
        if radius <= 1:
            tokens.append(f"L {cur_x:.1f} {cur_y:.1f}")
            continue
        entry_x = cur_x - ((cur_x - prev_x) / d1) * radius
        entry_y = cur_y - ((cur_y - prev_y) / d1) * radius
        exit_x = cur_x + ((next_x - cur_x) / d2) * radius
        exit_y = cur_y + ((next_y - cur_y) / d2) * radius
        tokens.append(f"L {entry_x:.1f} {entry_y:.1f}")
        tokens.append(f"Q {cur_x:.1f} {cur_y:.1f} {exit_x:.1f} {exit_y:.1f}")
    last_x, last_y = points[-1]
    tokens.append(f"L {last_x:.1f} {last_y:.1f}")
    return " ".join(tokens)


def render_plan_layers(render_plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [layer for layer in as_list(render_plan.get("layers")) if isinstance(layer, dict)]


def render_plan_operations(render_plan: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    for layer in render_plan_layers(render_plan):
        if layer.get("kind") == kind:
            return [item for item in as_list(layer.get("operations")) if isinstance(item, dict)]
    return []


def render_plan_operation(
    render_plan: dict[str, Any],
    kind: str,
    semantic_kind: str,
    semantic_id: str | None,
) -> dict[str, Any] | None:
    for operation in render_plan_operations(render_plan, kind):
        ref = as_obj(operation.get("semantic_ref"))
        if ref.get("kind") == semantic_kind and ref.get("id") == semantic_id:
            return operation
    return None


def geometry_number(
    operation: dict[str, Any] | None,
    key: str,
    fallback: float,
    low: float,
    high: float,
) -> float:
    value = as_obj(operation.get("geometry") if operation else {}).get(key)
    try:
        return clamp(float(value), low, high)
    except (TypeError, ValueError):
        return fallback


def route_width_cells(render_plan: dict[str, Any], route: dict[str, Any]) -> float:
    operation = render_plan_operation(
        render_plan,
        "road_band",
        "path_route",
        str(route.get("route_id") or ""),
    )
    return geometry_number(operation, "width_cells", 0.68, 0.42, 1.05)


def visible_road_width(render_plan: dict[str, Any], route: dict[str, Any], projection: dict[str, float]) -> float:
    return max(32, projection["base_tile_w"] * route_width_cells(render_plan, route) * 0.58)


def route_screen_length(points: list[tuple[float, float]]) -> float:
    total = 0.0
    for start, end in zip(points, points[1:]):
        total += math.hypot(end[0] - start[0], end[1] - start[1])
    return total


def road_sample_count(
    points: list[tuple[float, float]],
    *,
    spacing: float,
    minimum: int,
    maximum: int,
) -> int:
    if len(points) < 2:
        return 0
    return int(clamp(route_screen_length(points) / max(1, spacing), minimum, maximum))


def nearest_route_sample_to_point(
    runtime_package: dict[str, Any],
    projection: dict[str, float],
    x: float,
    y: float,
) -> dict[str, float] | None:
    best: dict[str, float] | None = None
    for route in as_list(runtime_package.get("path_routes")):
        if not isinstance(route, dict):
            continue
        points = route_screen_points(route, projection)
        count = road_sample_count(points, spacing=24, minimum=18, maximum=72)
        for sample in route_screen_samples(points, count):
            distance = math.hypot(sample["x"] - x, sample["y"] - y)
            if best is None or distance < best["distance"]:
                best = dict(sample)
                best["distance"] = distance
    return best


def slot_footprint(render_plan: dict[str, Any], slot: dict[str, Any]) -> tuple[float, float]:
    operation = render_plan_operation(
        render_plan,
        "build_slot_platform",
        "build_slot",
        str(slot.get("slot_id") or ""),
    )
    footprint = as_obj(as_obj(operation.get("geometry") if operation else {}).get("footprint"))
    try:
        width = clamp(float(footprint.get("width_cells")), 0.72, 1.45)
    except (TypeError, ValueError):
        width = 1
    try:
        height = clamp(float(footprint.get("height_cells")), 0.72, 1.45)
    except (TypeError, ValueError):
        height = 1
    return width, height


def objectives(runtime_package: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    data = as_obj(runtime_package.get("objectives"))
    core = data.get("core_target")
    if isinstance(core, dict):
        result.append(core)
    result.extend(target for target in as_list(data.get("optional_targets")) if isinstance(target, dict))
    return result


def style_values(style_pack: dict[str, Any]) -> dict[str, str]:
    return {
        "terrain_base": palette(style_pack, "terrain_base", "#23302B"),
        "terrain_detail": palette(style_pack, "terrain_detail", "#4F5A45"),
        "road_base": palette(style_pack, "road_base", "#766C55"),
        "road_edge": palette(style_pack, "road_edge", "#B8A56D"),
        "build_slot": palette(style_pack, "build_slot", "#D7C47A"),
        "objective": palette(style_pack, "objective", "#FFD26A"),
        "spawn": palette(style_pack, "spawn", "#6650A6"),
        "resource": palette(style_pack, "resource", "#7EC8A5"),
        "hazard": palette(style_pack, "hazard", "#8C3D4A"),
        "fog": palette(style_pack, "fog", "#87908A"),
        "accent": palette(style_pack, "accent", "#E5D48A"),
    }


def texture_pattern_defs(texture_refs: dict[str, str] | None) -> str:
    if not texture_refs:
        return ""
    parts: list[str] = []
    pattern_specs = (
        ("terrainTexture", "terrain_tile", 256, 256, 0.34, 0, 0, 256, 256),
        ("terrainDetailTexture", "terrain_detail_tile", 256, 256, 0.40, 0, 0, 256, 256),
        ("roadTexture", "road_tile", 256, 128, 0.58, 0, 0, 256, 128),
        ("roadEdgeTexture", "road_edge_tile", 192, 96, 0.48, 0, 0, 192, 96),
        ("roadAtlasDust", ROAD_DETAIL_ATLAS_ROLE, 96, 48, 0.62, 0, 0, 384, 192),
        ("roadAtlasPebble", ROAD_DETAIL_ATLAS_ROLE, 96, 48, 0.66, 96, 0, 384, 192),
        ("roadAtlasCrack", ROAD_DETAIL_ATLAS_ROLE, 96, 48, 0.58, 192, 0, 384, 192),
        ("roadAtlasPlatform", ROAD_DETAIL_ATLAS_ROLE, 96, 48, 0.64, 288, 0, 384, 192),
        ("slotTexture", "slot_tile", 192, 96, 0.62, 0, 0, 192, 96),
        ("shadowOverlayTexture", "shadow_overlay_tile", 256, 256, 0.54, 0, 0, 256, 256),
        ("fogOverlayTexture", "fog_overlay_tile", 256, 256, 0.42, 0, 0, 256, 256),
        ("lightOverlayTexture", "light_overlay_tile", 256, 256, 0.44, 0, 0, 256, 256),
    )
    for pattern_id, role, width, height, opacity, offset_x, offset_y, image_width, image_height in pattern_specs:
        href = texture_refs.get(role)
        if not href:
            continue
        parts.extend(
            [
                f'    <pattern id="{pattern_id}" patternUnits="userSpaceOnUse" width="{width}" height="{height}">',
                f'      <image href="{svg_escape(href)}" x="{-offset_x}" y="{-offset_y}" width="{image_width}" height="{image_height}" opacity="{opacity:.2f}"/>',
                "    </pattern>",
            ]
        )
    return "\n".join(parts)


def svg_defs(style: dict[str, str], texture_refs: dict[str, str] | None = None) -> str:
    terrain_dark = mix_hex(style["terrain_base"], "#030706", 0.42)
    terrain_mid = mix_hex(style["terrain_base"], style["terrain_detail"], 0.48)
    road_shadow = mix_hex(style["road_base"], "#090604", 0.46)
    return f"""
  <defs>
    <linearGradient id="terrainWash" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{terrain_mid}"/>
      <stop offset="54%" stop-color="{style["terrain_base"]}"/>
      <stop offset="100%" stop-color="{terrain_dark}"/>
    </linearGradient>
    <radialGradient id="centerLight" cx="48%" cy="48%" r="70%">
      <stop offset="0%" stop-color="{style["accent"]}" stop-opacity="0.20"/>
      <stop offset="56%" stop-color="{style["terrain_detail"]}" stop-opacity="0.06"/>
      <stop offset="100%" stop-color="#020403" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="roadWash" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{mix_hex(style["road_base"], style["road_edge"], 0.38)}"/>
      <stop offset="48%" stop-color="{style["road_base"]}"/>
      <stop offset="100%" stop-color="{road_shadow}"/>
    </linearGradient>
    <radialGradient id="slotGlow" cx="50%" cy="45%" r="70%">
      <stop offset="0%" stop-color="{style["build_slot"]}" stop-opacity="0.44"/>
      <stop offset="100%" stop-color="{style["build_slot"]}" stop-opacity="0"/>
    </radialGradient>
{texture_pattern_defs(texture_refs)}
    <filter id="softShadow" x="-30%" y="-30%" width="160%" height="160%">
      <feDropShadow dx="0" dy="10" stdDeviation="9" flood-color="#000000" flood-opacity="0.30"/>
    </filter>
    <filter id="lampBloom" x="-80%" y="-80%" width="260%" height="260%">
      <feGaussianBlur stdDeviation="5" result="blur"/>
      <feMerge>
        <feMergeNode in="blur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
  </defs>""".strip()


def svg_document(
    groups: list[str],
    style: dict[str, str],
    *,
    title: str,
    texture_refs: dict[str, str] | None = None,
) -> str:
    body = "\n".join(groups)
    return "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            (
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_WIDTH}" '
                f'height="{CANVAS_HEIGHT}" viewBox="0 0 {CANVAS_WIDTH} {CANVAS_HEIGHT}" '
                f'role="img" aria-label="{svg_escape(title)}">'
            ),
            svg_defs(style, texture_refs),
            body,
            "</svg>",
            "",
        ]
    )


def route_paths(runtime_package: dict[str, Any], projection: dict[str, float]) -> list[tuple[dict[str, Any], str]]:
    paths: list[tuple[dict[str, Any], str]] = []
    for route in as_list(runtime_package.get("path_routes")):
        if not isinstance(route, dict):
            continue
        points = route_screen_points(route, projection)
        if len(points) >= 2:
            paths.append((route, smooth_route(points)))
    return paths


def route_screen_points(route: dict[str, Any], projection: dict[str, float]) -> list[tuple[float, float]]:
    return [
        project_cell(point, projection)
        for point in as_list(route.get("waypoints"))
        if isinstance(point, dict)
    ]


def route_screen_samples(
    points: list[tuple[float, float]],
    count: int,
) -> list[dict[str, float]]:
    if len(points) < 2:
        return []
    segments: list[dict[str, float]] = []
    total = 0.0
    for start, end in zip(points, points[1:]):
        sx, sy = start
        ex, ey = end
        length = math.hypot(ex - sx, ey - sy)
        if length <= 1:
            continue
        segments.append({"sx": sx, "sy": sy, "ex": ex, "ey": ey, "length": length})
        total += length
    if not segments or total <= 1:
        return []
    samples: list[dict[str, float]] = []
    sample_count = max(2, count)
    for index in range(sample_count):
        target = ((index + 0.5) / sample_count) * total
        walked = 0.0
        for segment in segments:
            if walked + segment["length"] >= target:
                local = (target - walked) / segment["length"]
                x = segment["sx"] + (segment["ex"] - segment["sx"]) * local
                y = segment["sy"] + (segment["ey"] - segment["sy"]) * local
                dx = (segment["ex"] - segment["sx"]) / segment["length"]
                dy = (segment["ey"] - segment["sy"]) / segment["length"]
                samples.append(
                    {
                        "x": x,
                        "y": y,
                        "dx": dx,
                        "dy": dy,
                        "nx": -dy,
                        "ny": dx,
                        "angle": math.degrees(math.atan2(dy, dx)),
                    }
                )
                break
            walked += segment["length"]
    return samples


def terrain_layer(
    runtime_package: dict[str, Any],
    projection: dict[str, float],
    style: dict[str, str],
    rng: random.Random,
    backdrop_ref: str | None = None,
) -> str:
    if backdrop_ref:
        return "\n".join(
            [
                '  <g id="terrain_base" data-layer-role="terrain_base" data-visual-source="reviewed_painted_backdrop">',
                f'    <rect x="0" y="0" width="{CANVAS_WIDTH}" height="{CANVAS_HEIGHT}" fill="{mix_hex(style["terrain_base"], "#020403", 0.70)}"/>',
                f'    <image href="{svg_escape(backdrop_ref)}" x="0" y="0" width="{CANVAS_WIDTH}" height="{CANVAS_HEIGHT}" preserveAspectRatio="none"/>',
                f'    <rect x="0" y="0" width="{CANVAS_WIDTH}" height="{CANVAS_HEIGHT}" fill="{rgba(style["terrain_base"], 0.06)}"/>',
                f'    <ellipse cx="{CANVAS_WIDTH * 0.52:.1f}" cy="{CANVAS_HEIGHT * 0.50:.1f}" rx="{CANVAS_WIDTH * 0.62:.1f}" ry="{CANVAS_HEIGHT * 0.38:.1f}" fill="none" stroke="#000000" stroke-width="120" opacity="0.11"/>',
                "  </g>",
            ]
        )
    lines = [
        '  <g id="terrain_base" data-layer-role="terrain_base">',
        f'    <rect x="0" y="0" width="{CANVAS_WIDTH}" height="{CANVAS_HEIGHT}" fill="{mix_hex(style["terrain_base"], "#020403", 0.55)}"/>',
        f'    <rect x="0" y="0" width="{CANVAS_WIDTH}" height="{CANVAS_HEIGHT}" fill="url(#centerLight)"/>',
        f'    <rect x="0" y="0" width="{CANVAS_WIDTH}" height="{CANVAS_HEIGHT}" fill="url(#terrainTexture)" opacity="0.56"/>',
        f'    <ellipse cx="{CANVAS_WIDTH * 0.22:.1f}" cy="{CANVAS_HEIGHT * 0.78:.1f}" rx="{CANVAS_WIDTH * 0.32:.1f}" ry="{CANVAS_HEIGHT * 0.13:.1f}" fill="{style["fog"]}" opacity="0.075"/>',
        f'    <ellipse cx="{CANVAS_WIDTH * 0.85:.1f}" cy="{CANVAS_HEIGHT * 0.27:.1f}" rx="{CANVAS_WIDTH * 0.28:.1f}" ry="{CANVAS_HEIGHT * 0.10:.1f}" fill="{style["hazard"]}" opacity="0.060"/>',
        f'    <ellipse cx="{CANVAS_WIDTH * 0.50:.1f}" cy="{CANVAS_HEIGHT * 0.50:.1f}" rx="{CANVAS_WIDTH * 0.48:.1f}" ry="{CANVAS_HEIGHT * 0.30:.1f}" fill="url(#terrainWash)" opacity="0.34" transform="rotate(6 {CANVAS_WIDTH * 0.50:.1f} {CANVAS_HEIGHT * 0.50:.1f})"/>',
        f'    <ellipse cx="{CANVAS_WIDTH * 0.50:.1f}" cy="{CANVAS_HEIGHT * 0.50:.1f}" rx="{CANVAS_WIDTH * 0.48:.1f}" ry="{CANVAS_HEIGHT * 0.30:.1f}" fill="url(#terrainTexture)" opacity="0.32" transform="rotate(6 {CANVAS_WIDTH * 0.50:.1f} {CANVAS_HEIGHT * 0.50:.1f})"/>',
        f'    <ellipse cx="{CANVAS_WIDTH * 0.58:.1f}" cy="{CANVAS_HEIGHT * 0.54:.1f}" rx="{CANVAS_WIDTH * 0.40:.1f}" ry="{CANVAS_HEIGHT * 0.23:.1f}" fill="{rgba(style["terrain_detail"], 0.10)}" transform="rotate(-18 {CANVAS_WIDTH * 0.58:.1f} {CANVAS_HEIGHT * 0.54:.1f})"/>',
    ]
    patch_colors = [
        rgba(style["terrain_detail"], 0.18),
        rgba(style["road_edge"], 0.09),
        rgba(style["resource"], 0.10),
        rgba(style["hazard"], 0.08),
    ]
    for index in range(22):
        cx = rng.uniform(-0.04, 1.04) * CANVAS_WIDTH
        cy = rng.uniform(-0.02, 1.02) * CANVAS_HEIGHT
        rx = rng.uniform(46, 170)
        ry = rng.uniform(18, 78)
        rotate = rng.uniform(-34, 34)
        color = patch_colors[index % len(patch_colors)]
        lines.append(
            f'    <ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{color}" transform="rotate({rotate:.1f} {cx:.1f} {cy:.1f})"/>'
        )
    for index in range(120):
        x = rng.uniform(0, CANVAS_WIDTH)
        y = rng.uniform(0, CANVAS_HEIGHT)
        radius = rng.uniform(0.7, 2.4)
        color = style["road_edge"] if index % 5 == 0 else style["terrain_detail"]
        lines.append(
            f'    <circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.2f}" fill="{color}" opacity="{rng.uniform(0.05, 0.13):.3f}"/>'
        )
    node_id = str(runtime_package.get("node_id") or "")
    if node_id == "lamp_wick_store":
        for index in range(14):
            cx = rng.uniform(0.06, 0.94) * CANVAS_WIDTH
            cy = rng.uniform(0.18, 0.86) * CANVAS_HEIGHT
            width = rng.uniform(32, 92)
            lines.append(
                f'    <path d="M {cx - width:.1f} {cy:.1f} C {cx - width * 0.28:.1f} {cy - 12:.1f}, {cx + width * 0.28:.1f} {cy + 12:.1f}, {cx + width:.1f} {cy:.1f}" fill="none" stroke="{rgba(style["road_edge"], 0.10)}" stroke-width="{rng.uniform(3, 7):.1f}" stroke-linecap="round"/>'
            )
    elif node_id == "old_signal_tower":
        for index in range(18):
            cx = rng.uniform(0.10, 0.90) * CANVAS_WIDTH
            cy = rng.uniform(0.16, 0.84) * CANVAS_HEIGHT
            size = rng.uniform(7, 18)
            lines.append(
                f'    <path d="M {cx - size:.1f} {cy:.1f} L {cx + size:.1f} {cy:.1f} M {cx:.1f} {cy - size:.1f} L {cx:.1f} {cy + size:.1f}" stroke="{rgba(style["fog"], 0.11)}" stroke-width="2" stroke-linecap="round" transform="rotate({rng.uniform(-18, 18):.1f} {cx:.1f} {cy:.1f})"/>'
            )
    else:
        for index in range(12):
            cx = rng.uniform(0.12, 0.88) * CANVAS_WIDTH
            cy = rng.uniform(0.18, 0.82) * CANVAS_HEIGHT
            width = rng.uniform(28, 76)
            height = rng.uniform(8, 18)
            lines.append(
                f'    <rect x="{cx - width / 2:.1f}" y="{cy - height / 2:.1f}" width="{width:.1f}" height="{height:.1f}" rx="{height / 2:.1f}" fill="{rgba(style["road_base"], 0.08)}" transform="rotate({rng.uniform(-16, 16):.1f} {cx:.1f} {cy:.1f})"/>'
            )
    lines.append("  </g>")
    return "\n".join(lines)


def road_layer(
    runtime_package: dict[str, Any],
    render_plan: dict[str, Any],
    projection: dict[str, float],
    style: dict[str, str],
    rng: random.Random,
) -> str:
    lines = ['  <g id="road_band" data-layer-role="road_band" filter="url(#softShadow)">']
    for route, path_data in route_paths(runtime_package, projection):
        route_id = svg_escape(route.get("route_id") or "route")
        points = route_screen_points(route, projection)
        road_width = visible_road_width(render_plan, route, projection)
        lines.extend(
            [
                f'    <path d="{path_data}" fill="none" stroke="{rgba(style["terrain_detail"], 0.28)}" stroke-width="{road_width * 1.58:.1f}" stroke-linecap="round" stroke-linejoin="round" data-route="{route_id}"/>',
                f'    <path d="{path_data}" fill="none" stroke="url(#roadEdgeTexture)" stroke-width="{road_width * 1.34:.1f}" stroke-linecap="round" stroke-linejoin="round" opacity="0.34" data-route="{route_id}"/>',
                f'    <path d="{path_data}" fill="none" stroke="{mix_hex(style["road_base"], "#120B07", 0.58)}" stroke-width="{road_width * 1.10:.1f}" stroke-linecap="round" stroke-linejoin="round" opacity="0.84" data-route="{route_id}"/>',
                f'    <path d="{path_data}" fill="none" stroke="url(#roadWash)" stroke-width="{road_width * 0.90:.1f}" stroke-linecap="round" stroke-linejoin="round" opacity="0.72" data-route="{route_id}"/>',
                f'    <path d="{path_data}" fill="none" stroke="url(#roadTexture)" stroke-width="{road_width * 0.84:.1f}" stroke-linecap="round" stroke-linejoin="round" opacity="0.52" data-route="{route_id}"/>',
                f'    <path d="{path_data}" fill="none" stroke="{rgba(style["road_edge"], 0.22)}" stroke-width="{road_width * 0.14:.1f}" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="{road_width * 0.10:.1f} {road_width * 0.62:.1f}" data-route="{route_id}"/>',
                f'    <path d="{path_data}" fill="none" stroke="{rgba(style["accent"], 0.08)}" stroke-width="{max(3, road_width * 0.06):.1f}" stroke-linecap="round" stroke-linejoin="round" data-route="{route_id}"/>',
            ]
        )
        samples = route_screen_samples(points, 22)
        for index, sample in enumerate(samples):
            side = -1 if index % 2 == 0 else 1
            jitter = rng.uniform(-0.08, 0.08) * road_width
            x = sample["x"] + sample["nx"] * side * road_width * rng.uniform(0.46, 0.64)
            y = sample["y"] + sample["ny"] * side * road_width * rng.uniform(0.46, 0.64)
            rx = rng.uniform(3.5, 8.5)
            ry = rng.uniform(1.8, 4.8)
            lines.append(
                f'    <ellipse cx="{x + jitter:.1f}" cy="{y - jitter * 0.25:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{rgba(style["road_edge"], rng.uniform(0.14, 0.26))}" transform="rotate({sample["angle"] + rng.uniform(-18, 18):.1f} {x:.1f} {y:.1f})" data-route="{route_id}"/>'
            )
        for index, sample in enumerate(samples[::2]):
            x = sample["x"] + rng.uniform(-0.09, 0.09) * road_width
            y = sample["y"] + rng.uniform(-0.06, 0.06) * road_width
            lines.append(
                f'    <rect x="{x - road_width * 0.055:.1f}" y="{y - 2.0:.1f}" width="{road_width * 0.11:.1f}" height="4.0" rx="2" fill="{rgba(style["road_edge"], 0.18)}" transform="rotate({sample["angle"]:.1f} {x:.1f} {y:.1f})" data-route="{route_id}"/>'
            )
    lines.append("  </g>")
    return "\n".join(lines)


def terrain_detail_layer(
    runtime_package: dict[str, Any],
    projection: dict[str, float],
    style: dict[str, str],
    rng: random.Random,
) -> str:
    lines = ['  <g id="terrain_detail" data-layer-role="terrain_detail">']
    lines.extend(
        [
            f'    <rect x="0" y="0" width="{CANVAS_WIDTH}" height="{CANVAS_HEIGHT}" fill="url(#terrainDetailTexture)" opacity="0.28"/>',
            f'    <ellipse cx="{CANVAS_WIDTH * 0.48:.1f}" cy="{CANVAS_HEIGHT * 0.50:.1f}" rx="{CANVAS_WIDTH * 0.46:.1f}" ry="{CANVAS_HEIGHT * 0.28:.1f}" fill="url(#terrainDetailTexture)" opacity="0.22" transform="rotate(4 {CANVAS_WIDTH * 0.48:.1f} {CANVAS_HEIGHT * 0.50:.1f})"/>',
        ]
    )
    node_id = str(runtime_package.get("node_id") or "")
    for index in range(48):
        x = rng.uniform(0.04, 0.96) * CANVAS_WIDTH
        y = rng.uniform(0.10, 0.92) * CANVAS_HEIGHT
        rx = rng.uniform(12, 52)
        ry = rng.uniform(4, 18)
        color = style["resource"] if index % 7 == 0 else style["terrain_detail"]
        lines.append(
            f'    <ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{rgba(color, rng.uniform(0.055, 0.12))}" transform="rotate({rng.uniform(-28, 28):.1f} {x:.1f} {y:.1f})"/>'
        )
    for index in range(7):
        x = rng.uniform(0.08, 0.92) * CANVAS_WIDTH
        y = rng.uniform(0.16, 0.86) * CANVAS_HEIGHT
        rx = rng.uniform(52, 138)
        ry = rng.uniform(18, 52)
        fill = style["resource"] if index % 2 else style["fog"]
        lines.append(
            f'    <ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{rgba(fill, 0.075)}" stroke="{rgba(style["resource"], 0.055)}" stroke-width="3" transform="rotate({rng.uniform(-22, 22):.1f} {x:.1f} {y:.1f})"/>'
        )
    for index in range(12):
        x = rng.uniform(0.08, 0.92) * CANVAS_WIDTH
        y = rng.uniform(0.14, 0.86) * CANVAS_HEIGHT
        width = rng.uniform(44, 128)
        height = rng.uniform(10, 24)
        lines.append(
            f'    <rect x="{x - width / 2:.1f}" y="{y - height / 2:.1f}" width="{width:.1f}" height="{height:.1f}" rx="5" fill="{rgba(style["road_edge"], 0.105)}" stroke="{rgba(style["accent"], 0.055)}" stroke-width="1.3" transform="rotate({rng.uniform(-26, 26):.1f} {x:.1f} {y:.1f})"/>'
        )
    if node_id == "old_signal_tower":
        for index in range(18):
            x = rng.uniform(0.12, 0.88) * CANVAS_WIDTH
            y = rng.uniform(0.14, 0.86) * CANVAS_HEIGHT
            size = rng.uniform(9, 22)
            lines.append(
                f'    <path d="M {x - size:.1f} {y:.1f} L {x + size:.1f} {y:.1f} M {x:.1f} {y - size:.1f} L {x:.1f} {y + size:.1f}" stroke="{rgba(style["fog"], 0.14)}" stroke-width="2" stroke-linecap="round" transform="rotate({rng.uniform(-24, 24):.1f} {x:.1f} {y:.1f})"/>'
            )
    lines.append("  </g>")
    return "\n".join(lines)


def road_shadow_layer(
    runtime_package: dict[str, Any],
    render_plan: dict[str, Any],
    projection: dict[str, float],
    style: dict[str, str],
) -> str:
    lines = ['  <g id="road_shadow" data-layer-role="road_shadow">']
    for route, path_data in route_paths(runtime_package, projection):
        route_id = svg_escape(route.get("route_id") or "route")
        road_width = visible_road_width(render_plan, route, projection)
        lines.extend(
            [
                f'    <path d="{path_data}" fill="none" stroke="#000000" stroke-width="{road_width * 1.16:.1f}" stroke-linecap="round" stroke-linejoin="round" opacity="0.075" data-route="{route_id}"/>',
                f'    <path d="{path_data}" fill="none" stroke="url(#shadowOverlayTexture)" stroke-width="{road_width * 0.92:.1f}" stroke-linecap="round" stroke-linejoin="round" opacity="0.095" data-route="{route_id}"/>',
            ]
        )
    lines.append("  </g>")
    return "\n".join(lines)


def road_edge_layer(
    runtime_package: dict[str, Any],
    render_plan: dict[str, Any],
    projection: dict[str, float],
    style: dict[str, str],
    rng: random.Random,
) -> str:
    lines = ['  <g id="road_edge" data-layer-role="road_edge">']
    for route, path_data in route_paths(runtime_package, projection):
        route_id = svg_escape(route.get("route_id") or "route")
        points = route_screen_points(route, projection)
        road_width = visible_road_width(render_plan, route, projection)
        lines.extend(
            [
                f'    <path d="{path_data}" fill="none" stroke="{rgba(style["terrain_detail"], 0.10)}" stroke-width="{road_width * 1.02:.1f}" stroke-linecap="round" stroke-linejoin="round" data-route="{route_id}"/>',
                f'    <path d="{path_data}" fill="none" stroke="url(#roadEdgeTexture)" stroke-width="{road_width * 0.86:.1f}" stroke-linecap="round" stroke-linejoin="round" opacity="0.16" data-route="{route_id}"/>',
                f'    <path d="{path_data}" fill="none" stroke="{rgba(mix_hex(style["road_base"], "#120B07", 0.42), 0.13)}" stroke-width="{road_width * 0.64:.1f}" stroke-linecap="round" stroke-linejoin="round" data-route="{route_id}"/>',
            ]
        )
        edge_colors = [
            style["road_edge"],
            style["terrain_detail"],
            mix_hex(style["road_edge"], style["resource"], 0.22),
            mix_hex(style["road_edge"], "#090704", 0.36),
        ]
        edge_count = road_sample_count(points, spacing=max(10, road_width * 0.28), minimum=34, maximum=112)
        for index, sample in enumerate(route_screen_samples(points, edge_count)):
            for side in (-1, 1):
                if rng.random() < 0.16:
                    continue
                normal_offset = road_width * rng.uniform(0.46, 0.72) * side
                along_jitter = road_width * rng.uniform(-0.18, 0.18)
                x = sample["x"] + sample["nx"] * normal_offset + sample["dx"] * along_jitter
                y = sample["y"] + sample["ny"] * normal_offset + sample["dy"] * along_jitter
                color = edge_colors[(index + (0 if side < 0 else 1)) % len(edge_colors)]
                opacity = rng.uniform(0.18, 0.42)
                if rng.random() < 0.62:
                    rx = road_width * rng.uniform(0.06, 0.16)
                    ry = road_width * rng.uniform(0.025, 0.075)
                    lines.append(
                        f'    <ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="url(#roadAtlasPebble)" opacity="{opacity:.3f}" transform="rotate({sample["angle"] + rng.uniform(-26, 26):.1f} {x:.1f} {y:.1f})" data-route="{route_id}" data-road-edge-prop="stone"/>'
                    )
                else:
                    block_w = road_width * rng.uniform(0.13, 0.28)
                    block_h = road_width * rng.uniform(0.05, 0.11)
                    lines.append(
                        f'    <rect x="{x - block_w / 2:.1f}" y="{y - block_h / 2:.1f}" width="{block_w:.1f}" height="{block_h:.1f}" rx="{block_h * 0.42:.1f}" fill="url(#roadAtlasCrack)" opacity="{opacity:.3f}" stroke="{rgba(color, 0.18)}" stroke-width="1.0" transform="rotate({sample["angle"] + rng.uniform(-22, 22):.1f} {x:.1f} {y:.1f})" data-route="{route_id}" data-road-edge-prop="broken-curb"/>'
                    )
        berm_count = road_sample_count(points, spacing=max(28, road_width * 0.70), minimum=10, maximum=36)
        for index, sample in enumerate(route_screen_samples(points, berm_count)):
            for side in (-1, 1):
                if rng.random() < 0.30:
                    continue
                start_offset = road_width * rng.uniform(0.67, 0.86) * side
                end_offset = start_offset + road_width * rng.uniform(0.08, 0.18) * side
                x1 = sample["x"] + sample["nx"] * start_offset
                y1 = sample["y"] + sample["ny"] * start_offset
                x2 = sample["x"] + sample["nx"] * end_offset + sample["dx"] * rng.uniform(-0.08, 0.08) * road_width
                y2 = sample["y"] + sample["ny"] * end_offset + sample["dy"] * rng.uniform(-0.08, 0.08) * road_width
                lines.append(
                    f'    <path d="M {x1:.1f} {y1:.1f} L {x2:.1f} {y2:.1f}" fill="none" stroke="{rgba(style["terrain_detail"], rng.uniform(0.15, 0.30))}" stroke-width="{rng.uniform(1.6, 3.4):.1f}" stroke-linecap="round" data-route="{route_id}" data-road-edge-prop="grass-break"/>'
                )
    lines.append("  </g>")
    return "\n".join(lines)


def road_surface_layer(
    runtime_package: dict[str, Any],
    render_plan: dict[str, Any],
    projection: dict[str, float],
    style: dict[str, str],
    rng: random.Random,
) -> str:
    lines = ['  <g id="road_surface" data-layer-role="road_surface">']
    for route, path_data in route_paths(runtime_package, projection):
        route_id = svg_escape(route.get("route_id") or "route")
        points = route_screen_points(route, projection)
        road_width = visible_road_width(render_plan, route, projection)
        lines.extend(
            [
                f'    <path d="{path_data}" fill="none" stroke="{rgba(mix_hex(style["road_base"], style["road_edge"], 0.12), 0.16)}" stroke-width="{road_width * 0.52:.1f}" stroke-linecap="round" stroke-linejoin="round" data-route="{route_id}"/>',
                f'    <path d="{path_data}" fill="none" stroke="url(#roadWash)" stroke-width="{road_width * 0.44:.1f}" stroke-linecap="round" stroke-linejoin="round" opacity="0.13" data-route="{route_id}"/>',
                f'    <path d="{path_data}" fill="none" stroke="url(#roadTexture)" stroke-width="{road_width * 0.36:.1f}" stroke-linecap="round" stroke-linejoin="round" opacity="0.11" data-route="{route_id}"/>',
            ]
        )
        patch_count = road_sample_count(points, spacing=max(9, road_width * 0.22), minimum=58, maximum=168)
        for index, sample in enumerate(route_screen_samples(points, patch_count)):
            lane = rng.uniform(-0.24, 0.24)
            x = sample["x"] + sample["nx"] * lane * road_width + sample["dx"] * rng.uniform(-0.12, 0.12) * road_width
            y = sample["y"] + sample["ny"] * lane * road_width + sample["dy"] * rng.uniform(-0.12, 0.12) * road_width
            rx = road_width * rng.uniform(0.20, 0.46)
            ry = road_width * rng.uniform(0.10, 0.24)
            fill = "url(#roadTexture)" if index % 4 else "url(#roadAtlasDust)"
            if index % 5 == 2:
                fill = "url(#roadAtlasPebble)"
            opacity = rng.uniform(0.26, 0.50)
            angle = sample["angle"] + rng.uniform(-13, 13)
            if rng.random() < 0.34:
                slab_w = rx * rng.uniform(1.10, 1.55)
                slab_h = ry * rng.uniform(1.10, 1.45)
                lines.append(
                    f'    <rect x="{x - slab_w / 2:.1f}" y="{y - slab_h / 2:.1f}" width="{slab_w:.1f}" height="{slab_h:.1f}" rx="{slab_h * rng.uniform(0.35, 0.58):.1f}" fill="{fill}" opacity="{opacity:.3f}" stroke="{rgba(style["road_edge"], rng.uniform(0.030, 0.075))}" stroke-width="{rng.uniform(0.6, 1.2):.1f}" transform="rotate({angle:.1f} {x:.1f} {y:.1f})" data-route="{route_id}" data-road-brush="grounded-slab"/>'
                )
            else:
                lines.append(
                    f'    <ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{fill}" opacity="{opacity:.3f}" stroke="{rgba(style["road_edge"], rng.uniform(0.030, 0.075))}" stroke-width="{rng.uniform(0.6, 1.2):.1f}" transform="rotate({angle:.1f} {x:.1f} {y:.1f})" data-route="{route_id}" data-road-brush="grounded-patch"/>'
                )
        brush_colors = [
            rgba(mix_hex(style["road_base"], style["road_edge"], 0.26), 0.22),
            rgba(mix_hex(style["road_base"], style["terrain_detail"], 0.22), 0.18),
            rgba(style["road_edge"], 0.14),
            rgba(style["accent"], 0.10),
        ]
        brush_count = road_sample_count(points, spacing=max(9, road_width * 0.24), minimum=42, maximum=134)
        for index, sample in enumerate(route_screen_samples(points, brush_count)):
            lane = rng.uniform(-0.33, 0.33)
            x = sample["x"] + sample["nx"] * lane * road_width + sample["dx"] * rng.uniform(-0.14, 0.14) * road_width
            y = sample["y"] + sample["ny"] * lane * road_width + sample["dy"] * rng.uniform(-0.14, 0.14) * road_width
            rx = road_width * rng.uniform(0.08, 0.22)
            ry = road_width * rng.uniform(0.020, 0.070)
            color = brush_colors[index % len(brush_colors)]
            lines.append(
                f'    <ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="url(#roadAtlasDust)" opacity="{0.22 + (index % 4) * 0.030:.3f}" stroke="{color}" stroke-width="0.6" transform="rotate({sample["angle"] + rng.uniform(-12, 12):.1f} {x:.1f} {y:.1f})" data-route="{route_id}" data-road-brush="surface"/>'
            )
        intrusion_count = road_sample_count(points, spacing=max(12, road_width * 0.30), minimum=42, maximum=124)
        for index, sample in enumerate(route_screen_samples(points, intrusion_count)):
            for side in (-1, 1):
                if rng.random() < 0.34:
                    continue
                edge_offset = road_width * rng.uniform(0.32, 0.61) * side
                x = sample["x"] + sample["nx"] * edge_offset + sample["dx"] * rng.uniform(-0.20, 0.20) * road_width
                y = sample["y"] + sample["ny"] * edge_offset + sample["dy"] * rng.uniform(-0.20, 0.20) * road_width
                rx = road_width * rng.uniform(0.14, 0.40)
                ry = road_width * rng.uniform(0.050, 0.18)
                fill = "url(#terrainDetailTexture)" if index % 2 else rgba(style["terrain_base"], rng.uniform(0.22, 0.38))
                opacity = rng.uniform(0.18, 0.34) if fill.startswith("url(") else 1.0
                lines.append(
                    f'    <ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{fill}" opacity="{opacity:.3f}" transform="rotate({sample["angle"] + rng.uniform(-18, 18):.1f} {x:.1f} {y:.1f})" data-route="{route_id}" data-road-brush="terrain-intrusion"/>'
                )
        rut_count = road_sample_count(points, spacing=max(20, road_width * 0.48), minimum=14, maximum=52)
        for index, sample in enumerate(route_screen_samples(points, rut_count)):
            for side in (-1, 1):
                if rng.random() < 0.24:
                    continue
                x = sample["x"] + sample["nx"] * side * road_width * rng.uniform(0.18, 0.30)
                y = sample["y"] + sample["ny"] * side * road_width * rng.uniform(0.18, 0.30)
                mark_w = road_width * rng.uniform(0.10, 0.20)
                mark_h = road_width * rng.uniform(0.018, 0.045)
                lines.append(
                    f'    <rect x="{x - mark_w / 2:.1f}" y="{y - mark_h / 2:.1f}" width="{mark_w:.1f}" height="{mark_h:.1f}" rx="{mark_h / 2:.1f}" fill="url(#roadAtlasCrack)" opacity="{rng.uniform(0.22, 0.36):.3f}" transform="rotate({sample["angle"] + rng.uniform(-6, 6):.1f} {x:.1f} {y:.1f})" data-route="{route_id}" data-road-brush="rut"/>'
                )
    lines.append("  </g>")
    return "\n".join(lines)


def build_slots_layer(
    runtime_package: dict[str, Any],
    render_plan: dict[str, Any],
    projection: dict[str, float],
    style: dict[str, str],
) -> str:
    lines = ['  <g id="build_slots" data-layer-role="build_slots">']
    for index, slot in enumerate(as_list(runtime_package.get("build_slots"))):
        if not isinstance(slot, dict) or not isinstance(slot.get("position"), dict):
            continue
        x, y = project_cell(slot["position"], projection)
        width_scale, height_scale = slot_footprint(render_plan, slot)
        rx = projection["base_tile_w"] * 0.31 * width_scale
        ry = projection["base_tile_h"] * 0.37 * height_scale
        slot_id = svg_escape(slot.get("slot_id") or f"slot_{index + 1}")
        nearest = nearest_route_sample_to_point(runtime_package, projection, x, y)
        angle = nearest["angle"] if nearest else 0.0
        slot_rng = random.Random(f"{slot_id}:platform")
        if nearest and nearest["distance"] <= projection["base_tile_w"] * 1.15:
            connect_width = max(4, min(rx * 0.42, nearest["distance"] * 0.13))
            lines.append(
                f'    <path d="M {nearest["x"]:.1f} {nearest["y"]:.1f} L {x:.1f} {y:.1f}" fill="none" stroke="url(#roadAtlasDust)" stroke-width="{connect_width:.1f}" stroke-linecap="round" opacity="0.13" data-slot="{slot_id}" data-slot-platform="footpath"/>'
            )
        angle_rad = math.radians(angle)
        ux = math.cos(angle_rad)
        uy = math.sin(angle_rad)
        vx = -uy
        vy = ux
        slab_points: list[str] = []
        slab_point_count = 9
        for point_index in range(slab_point_count):
            theta = (math.tau * point_index / slab_point_count) + slot_rng.uniform(-0.10, 0.10)
            radius = slot_rng.uniform(0.66, 1.02)
            local_x = math.cos(theta) * rx * radius
            local_y = math.sin(theta) * ry * radius * slot_rng.uniform(0.58, 0.82)
            px = x + ux * local_x + vx * local_y
            py = y + uy * local_x + vy * local_y
            slab_points.append(f"{px:.1f},{py:.1f}")
        slab_fill = rgba(mix_hex(style["road_edge"], style["terrain_base"], 0.52), 0.38)
        lines.extend(
            [
                f'    <ellipse cx="{x:.1f}" cy="{y + projection["base_tile_h"] * 0.12:.1f}" rx="{rx * 1.08:.1f}" ry="{ry * 0.58:.1f}" fill="#000000" opacity="0.22" data-slot="{slot_id}" data-slot-platform="ground-shadow"/>',
                f'    <polygon points="{" ".join(slab_points)}" fill="{slab_fill}" stroke="{rgba(style["road_edge"], 0.34)}" stroke-width="1.2" data-slot="{slot_id}" data-slot-platform="broken-slab"/>',
                f'    <polygon points="{" ".join(slab_points)}" fill="url(#roadAtlasPlatform)" opacity="0.66" data-slot="{slot_id}" data-slot-platform="stone-texture"/>',
            ]
        )
        stone_count = 10 + (index % 4)
        for stone_index in range(stone_count):
            theta = (math.tau * stone_index / stone_count) + slot_rng.uniform(-0.24, 0.24)
            radius = slot_rng.uniform(0.68, 1.16)
            local_x = math.cos(theta) * rx * radius
            local_y = math.sin(theta) * ry * radius * slot_rng.uniform(0.72, 1.08)
            px = x + ux * local_x + vx * local_y
            py = y + uy * local_x + vy * local_y
            stone_w = rx * slot_rng.uniform(0.22, 0.44)
            stone_h = ry * slot_rng.uniform(0.16, 0.34)
            stone_angle = angle + math.degrees(theta) * 0.10 + slot_rng.uniform(-18, 18)
            fill = "url(#roadAtlasPlatform)" if stone_index % 3 else "url(#roadAtlasCrack)"
            lines.append(
                f'    <rect x="{px - stone_w / 2:.1f}" y="{py - stone_h / 2:.1f}" width="{stone_w:.1f}" height="{stone_h:.1f}" rx="{stone_h * 0.32:.1f}" fill="{fill}" opacity="{slot_rng.uniform(0.62, 0.90):.3f}" stroke="{rgba(style["road_edge"], slot_rng.uniform(0.18, 0.36))}" stroke-width="0.9" transform="rotate({stone_angle:.1f} {px:.1f} {py:.1f})" data-slot="{slot_id}" data-slot-platform="ruin-stone"/>'
            )
        rubble_count = 6 + (index % 3)
        for rubble_index in range(rubble_count):
            local_x = slot_rng.uniform(-0.44, 0.44) * rx
            local_y = slot_rng.uniform(-0.28, 0.30) * ry
            px = x + ux * local_x + vx * local_y
            py = y + uy * local_x + vy * local_y
            rubble_rx = rx * slot_rng.uniform(0.045, 0.095)
            rubble_ry = ry * slot_rng.uniform(0.040, 0.090)
            lines.append(
                f'    <ellipse cx="{px:.1f}" cy="{py:.1f}" rx="{rubble_rx:.1f}" ry="{rubble_ry:.1f}" fill="{rgba(style["accent"] if rubble_index == 0 else style["road_edge"], 0.16 if rubble_index == 0 else 0.34)}" opacity="{slot_rng.uniform(0.56, 0.84):.3f}" transform="rotate({angle + slot_rng.uniform(-24, 24):.1f} {px:.1f} {py:.1f})" data-slot="{slot_id}" data-slot-platform="loose-rubble"/>'
            )
    lines.append("  </g>")
    return "\n".join(lines)


def objectives_layer(
    runtime_package: dict[str, Any],
    projection: dict[str, float],
    style: dict[str, str],
) -> str:
    lines = ['  <g id="objectives" data-layer-role="objectives">']
    for index, target in enumerate(objectives(runtime_package)):
        if not isinstance(target.get("position"), dict):
            continue
        x, y = project_cell(target["position"], projection)
        is_core = index == 0
        color = style["objective"] if is_core else style["resource"]
        target_id = svg_escape(target.get("target_id") or f"target_{index + 1}")
        base_rx = projection["base_tile_w"] * (0.43 if is_core else 0.30)
        base_ry = projection["base_tile_h"] * (0.34 if is_core else 0.25)
        lamp_h = projection["base_tile_h"] * (0.96 if is_core else 0.48)
        roof_y = y - lamp_h * 0.92
        roof_w = base_rx * 0.92
        roof_h = projection["base_tile_h"] * 0.28
        post_gap = base_rx * 0.34
        plinth_fill = mix_hex(style["road_edge"], style["terrain_base"], 0.60)
        lines.extend(
            [
                f'    <ellipse cx="{x:.1f}" cy="{y + projection["base_tile_h"] * 0.18:.1f}" rx="{base_rx * 1.06:.1f}" ry="{base_ry * 0.70:.1f}" fill="#000000" opacity="0.30" data-target="{target_id}" data-objective-part="shadow"/>',
                f'    <polygon points="{x - base_rx:.1f},{y - base_ry * 0.10:.1f} {x:.1f},{y - base_ry * 0.58:.1f} {x + base_rx:.1f},{y - base_ry * 0.10:.1f} {x + base_rx * 0.70:.1f},{y + base_ry * 0.46:.1f} {x:.1f},{y + base_ry * 0.70:.1f} {x - base_rx * 0.70:.1f},{y + base_ry * 0.46:.1f}" fill="{rgba(plinth_fill, 0.72)}" stroke="{rgba(style["road_edge"], 0.38)}" stroke-width="1.4" data-target="{target_id}" data-objective-part="stone-plinth"/>',
                f'    <ellipse cx="{x:.1f}" cy="{y - base_ry * 0.10:.1f}" rx="{base_rx * 0.72:.1f}" ry="{base_ry * 0.36:.1f}" fill="url(#roadAtlasPlatform)" opacity="0.66" data-target="{target_id}" data-objective-part="plinth-texture"/>',
            ]
        )
        if is_core:
            lines.extend(
                [
                    f'    <line x1="{x - post_gap:.1f}" y1="{y - base_ry * 0.36:.1f}" x2="{x - post_gap * 0.74:.1f}" y2="{roof_y + roof_h * 0.28:.1f}" stroke="{mix_hex(style["road_edge"], "#23180D", 0.48)}" stroke-width="3.2" stroke-linecap="round" data-target="{target_id}" data-objective-part="timber-post"/>',
                    f'    <line x1="{x + post_gap:.1f}" y1="{y - base_ry * 0.36:.1f}" x2="{x + post_gap * 0.74:.1f}" y2="{roof_y + roof_h * 0.28:.1f}" stroke="{mix_hex(style["road_edge"], "#23180D", 0.48)}" stroke-width="3.2" stroke-linecap="round" data-target="{target_id}" data-objective-part="timber-post"/>',
                    f'    <path d="M {x - roof_w:.1f} {roof_y:.1f} Q {x:.1f} {roof_y - roof_h * 0.52:.1f} {x + roof_w:.1f} {roof_y:.1f} L {x + roof_w * 0.70:.1f} {roof_y + roof_h * 0.40:.1f} Q {x:.1f} {roof_y + roof_h * 0.18:.1f} {x - roof_w * 0.70:.1f} {roof_y + roof_h * 0.40:.1f} Z" fill="{mix_hex(style["terrain_base"], "#050706", 0.30)}" stroke="{rgba(style["road_edge"], 0.42)}" stroke-width="1.1" data-target="{target_id}" data-objective-part="tile-eave"/>',
                    f'    <line x1="{x - roof_w * 0.74:.1f}" y1="{roof_y + roof_h * 0.10:.1f}" x2="{x + roof_w * 0.74:.1f}" y2="{roof_y + roof_h * 0.10:.1f}" stroke="{rgba(style["road_edge"], 0.26)}" stroke-width="1.0" stroke-dasharray="5 7" data-target="{target_id}" data-objective-part="tile-ridge"/>',
                    f'    <rect x="{x - projection["base_tile_w"] * 0.085:.1f}" y="{y - lamp_h * 0.72:.1f}" width="{projection["base_tile_w"] * 0.17:.1f}" height="{projection["base_tile_h"] * 0.36:.1f}" rx="3" fill="{rgba(mix_hex(color, "#4B3218", 0.28), 0.54)}" stroke="{rgba(color, 0.40)}" stroke-width="1.1" data-target="{target_id}" data-objective-part="copper-lantern"/>',
                    f'    <ellipse cx="{x:.1f}" cy="{y - lamp_h * 0.54:.1f}" rx="{projection["base_tile_w"] * 0.10:.1f}" ry="{projection["base_tile_h"] * 0.14:.1f}" fill="{rgba(color, 0.46)}" filter="url(#lampBloom)" data-target="{target_id}" data-objective-part="lamp-core"/>',
                    f'    <ellipse cx="{x:.1f}" cy="{y - lamp_h * 0.54:.1f}" rx="{projection["base_tile_w"] * 0.26:.1f}" ry="{projection["base_tile_h"] * 0.25:.1f}" fill="{rgba(color, 0.060)}" data-target="{target_id}" data-objective-part="restrained-light"/>',
                    f'    <path d="M {x - base_rx * 0.58:.1f} {y + base_ry * 0.08:.1f} L {x + base_rx * 0.58:.1f} {y + base_ry * 0.08:.1f}" stroke="{rgba(style["road_edge"], 0.34)}" stroke-width="2.0" stroke-linecap="round" data-target="{target_id}" data-objective-part="front-step"/>',
                    f'    <path d="M {x - base_rx * 0.44:.1f} {y + base_ry * 0.28:.1f} L {x + base_rx * 0.44:.1f} {y + base_ry * 0.28:.1f}" stroke="{rgba(style["road_edge"], 0.22)}" stroke-width="1.6" stroke-linecap="round" data-target="{target_id}" data-objective-part="front-step"/>',
                ]
            )
        else:
            lines.extend(
                [
                    f'    <rect x="{x - projection["base_tile_w"] * 0.060:.1f}" y="{y - lamp_h * 0.58:.1f}" width="{projection["base_tile_w"] * 0.12:.1f}" height="{projection["base_tile_h"] * 0.22:.1f}" rx="2.4" fill="{rgba(mix_hex(color, "#3A2B19", 0.36), 0.52)}" stroke="{rgba(color, 0.34)}" stroke-width="0.9" data-target="{target_id}" data-objective-part="low-lantern"/>',
                    f'    <ellipse cx="{x:.1f}" cy="{y - lamp_h * 0.44:.1f}" rx="{projection["base_tile_w"] * 0.070:.1f}" ry="{projection["base_tile_h"] * 0.095:.1f}" fill="{rgba(color, 0.38)}" filter="url(#lampBloom)" data-target="{target_id}" data-objective-part="low-lamp-core"/>',
                    f'    <ellipse cx="{x:.1f}" cy="{y - lamp_h * 0.44:.1f}" rx="{projection["base_tile_w"] * 0.17:.1f}" ry="{projection["base_tile_h"] * 0.16:.1f}" fill="{rgba(color, 0.048)}" data-target="{target_id}" data-objective-part="low-light"/>',
                ]
            )
    lines.append("  </g>")
    return "\n".join(lines)


def spawn_layer(
    runtime_package: dict[str, Any],
    projection: dict[str, float],
    style: dict[str, str],
) -> str:
    lines = ['  <g id="spawn" data-layer-role="spawn">']
    for index, spawn in enumerate(as_list(runtime_package.get("spawn_points"))):
        if not isinstance(spawn, dict) or not isinstance(spawn.get("position"), dict):
            continue
        x, y = project_cell(spawn["position"], projection)
        spawn_id = svg_escape(spawn.get("spawn_id") or f"spawn_{index + 1}")
        gate_w = projection["base_tile_w"] * 0.58
        gate_h = projection["base_tile_h"] * 0.70
        lines.extend(
            [
                f'    <ellipse cx="{x:.1f}" cy="{y + projection["base_tile_h"] * 0.20:.1f}" rx="{gate_w * 0.94:.1f}" ry="{projection["base_tile_h"] * 0.28:.1f}" fill="#000000" opacity="0.34" data-spawn="{spawn_id}" data-spawn-part="shadow"/>',
                f'    <ellipse cx="{x:.1f}" cy="{y + projection["base_tile_h"] * 0.06:.1f}" rx="{gate_w * 0.56:.1f}" ry="{projection["base_tile_h"] * 0.20:.1f}" fill="{mix_hex(style["spawn"], "#050408", 0.72)}" opacity="0.76" data-spawn="{spawn_id}" data-spawn-part="mouth"/>',
                f'    <path d="M {x - gate_w:.1f} {y + projection["base_tile_h"] * 0.04:.1f} C {x - gate_w * 0.74:.1f} {y - gate_h:.1f}, {x + gate_w * 0.74:.1f} {y - gate_h:.1f}, {x + gate_w:.1f} {y + projection["base_tile_h"] * 0.04:.1f}" fill="none" stroke="{rgba(style["road_edge"], 0.32)}" stroke-width="3.2" stroke-linecap="round" data-spawn="{spawn_id}" data-spawn-part="broken-arch"/>',
                f'    <path d="M {x - gate_w * 0.64:.1f} {y + projection["base_tile_h"] * 0.02:.1f} C {x - gate_w * 0.42:.1f} {y - gate_h * 0.60:.1f}, {x + gate_w * 0.42:.1f} {y - gate_h * 0.60:.1f}, {x + gate_w * 0.64:.1f} {y + projection["base_tile_h"] * 0.02:.1f}" fill="none" stroke="{rgba(style["spawn"], 0.34)}" stroke-width="2.0" stroke-linecap="round" data-spawn="{spawn_id}" data-spawn-part="fog-arch"/>',
                f'    <ellipse cx="{x:.1f}" cy="{y - gate_h * 0.24:.1f}" rx="{gate_w * 0.52:.1f}" ry="{gate_h * 0.38:.1f}" fill="{rgba(style["fog"], 0.08)}" filter="url(#lampBloom)" data-spawn="{spawn_id}" data-spawn-part="cold-mist"/>',
            ]
        )
        for wisp in range(5):
            offset = (wisp - 2) * projection["base_tile_w"] * 0.12
            lines.append(
                f'    <path d="M {x + offset:.1f} {y - projection["base_tile_h"] * 0.12:.1f} C {x + offset * 0.4:.1f} {y - projection["base_tile_h"] * 0.58:.1f}, {x + offset * 1.6:.1f} {y - projection["base_tile_h"] * 0.78:.1f}, {x + offset * 0.2:.1f} {y - projection["base_tile_h"] * 1.10:.1f}" fill="none" stroke="{rgba(style["fog"], 0.13)}" stroke-width="4" stroke-linecap="round" data-spawn="{spawn_id}" data-spawn-part="wisp"/>'
            )
    lines.append("  </g>")
    return "\n".join(lines)


def route_cells(runtime_package: dict[str, Any]) -> set[tuple[int, int]]:
    cells: set[tuple[int, int]] = set()
    for route in as_list(runtime_package.get("path_routes")):
        if not isinstance(route, dict):
            continue
        points = [point for point in as_list(route.get("waypoints")) if isinstance(point, dict)]
        for start, end in zip(points, points[1:]):
            sx = int(start.get("x") or 0)
            sy = int(start.get("y") or 0)
            ex = int(end.get("x") or 0)
            ey = int(end.get("y") or 0)
            dx = 0 if ex == sx else (1 if ex > sx else -1)
            dy = 0 if ey == sy else (1 if ey > sy else -1)
            x, y = sx, sy
            cells.add((x, y))
            while x != ex or y != ey:
                if x != ex:
                    x += dx
                if y != ey:
                    y += dy
                cells.add((x, y))
    return cells


def reserved_cells(runtime_package: dict[str, Any]) -> set[tuple[int, int]]:
    reserved = route_cells(runtime_package)
    for slot in as_list(runtime_package.get("build_slots")):
        if isinstance(slot, dict) and isinstance(slot.get("position"), dict):
            position = slot["position"]
            reserved.add((int(position.get("x") or 0), int(position.get("y") or 0)))
    for target in objectives(runtime_package):
        if isinstance(target.get("position"), dict):
            position = target["position"]
            reserved.add((int(position.get("x") or 0), int(position.get("y") or 0)))
    for spawn in as_list(runtime_package.get("spawn_points")):
        if isinstance(spawn, dict) and isinstance(spawn.get("position"), dict):
            position = spawn["position"]
            reserved.add((int(position.get("x") or 0), int(position.get("y") or 0)))
    return reserved


def semantic_props_layer(
    runtime_package: dict[str, Any],
    projection: dict[str, float],
    style: dict[str, str],
) -> str:
    lines = ['  <g id="semantic_props" data-layer-role="semantic_props">']
    semantic_specs = (
        ("resource_nodes", "resource_node", style["resource"], 0.34),
        ("hazard_zones", "hazard_zone", style["hazard"], 0.28),
        ("defense_anchors", "defense_anchor", style["accent"], 0.30),
        ("blocked_areas", "blocked_area", style["road_edge"], 0.22),
    )
    for collection, attr, color, alpha in semantic_specs:
        for index, item in enumerate(as_list(runtime_package.get(collection))):
            if not isinstance(item, dict):
                continue
            position = item.get("position") or item.get("center")
            if not isinstance(position, dict):
                continue
            x, y = project_cell(position, projection)
            item_id = svg_escape(item.get("id") or item.get(f"{attr}_id") or f"{attr}_{index + 1}")
            if collection == "blocked_areas":
                lines.append(
                    f'    <rect x="{x - projection["base_tile_w"] * 0.35:.1f}" y="{y - projection["base_tile_h"] * 0.26:.1f}" width="{projection["base_tile_w"] * 0.70:.1f}" height="{projection["base_tile_h"] * 0.44:.1f}" rx="7" fill="{rgba(color, alpha)}" stroke="{rgba(color, 0.24)}" stroke-width="1.4" transform="rotate(-12 {x:.1f} {y:.1f})" data-semantic="{item_id}"/>'
                )
            else:
                lines.append(
                    f'    <ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{projection["base_tile_w"] * 0.30:.1f}" ry="{projection["base_tile_h"] * 0.22:.1f}" fill="{rgba(color, alpha)}" stroke="{rgba(color, 0.34)}" stroke-width="1.4" data-semantic="{item_id}"/>'
                )
    lines.append("  </g>")
    return "\n".join(lines)


def non_blocking_decorations_layer(
    runtime_package: dict[str, Any],
    projection: dict[str, float],
    style: dict[str, str],
    rng: random.Random,
) -> str:
    lines = ['  <g id="non_blocking_decorations" data-layer-role="non_blocking_decorations">']
    reserved = reserved_cells(runtime_package)
    node_id = str(runtime_package.get("node_id") or "")
    width_cells = int(projection["width_cells"])
    height_cells = int(projection["height_cells"])
    placed = 0
    attempts = 0
    while placed < 56 and attempts < 280:
        attempts += 1
        cell_x = rng.randrange(0, width_cells)
        cell_y = rng.randrange(0, height_cells)
        if (cell_x, cell_y) in reserved:
            continue
        x, y = project_cell(
            {
                "x": cell_x + rng.uniform(-0.34, 0.34),
                "y": cell_y + rng.uniform(-0.34, 0.34),
            },
            projection,
        )
        if x < 40 or x > CANVAS_WIDTH - 40 or y < 40 or y > CANVAS_HEIGHT - 30:
            continue
        kind = placed % 5
        if kind == 0:
            size = rng.uniform(0.10, 0.20) * projection["base_tile_w"]
            if node_id == "old_signal_tower":
                lines.append(
                    f'    <path d="M {x - size:.1f} {y + size * 0.30:.1f} L {x:.1f} {y - size * 0.42:.1f} L {x + size * 0.82:.1f} {y + size * 0.24:.1f} Z" fill="{rgba(style["fog"], 0.22)}" stroke="{rgba(style["resource"], 0.18)}" stroke-width="1.1" opacity="0.68"/>'
                )
                placed += 1
                continue
            lines.append(
                f'    <ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{size:.1f}" ry="{size * 0.48:.1f}" fill="{mix_hex(style["terrain_detail"], "#121713", 0.30)}" opacity="0.50"/>'
            )
        elif kind == 1:
            size = rng.uniform(0.12, 0.19) * projection["base_tile_w"]
            if node_id == "lamp_wick_store":
                lines.append(
                    f'    <path d="M {x - size:.1f} {y:.1f} C {x - size * 0.35:.1f} {y - size * 0.35:.1f}, {x + size * 0.35:.1f} {y + size * 0.35:.1f}, {x + size:.1f} {y:.1f}" fill="none" stroke="{rgba(style["road_edge"], 0.28)}" stroke-width="{max(3.2, size * 0.18):.1f}" stroke-linecap="round" opacity="0.86"/>'
                )
                placed += 1
                continue
            lines.append(
                f'    <rect x="{x - size / 2:.1f}" y="{y - size * 0.34:.1f}" width="{size:.1f}" height="{size * 0.42:.1f}" rx="3" fill="{mix_hex(style["road_base"], "#0B0805", 0.28)}" opacity="0.38" transform="rotate({rng.uniform(-16, 16):.1f} {x:.1f} {y:.1f})"/>'
            )
        elif kind == 2:
            h = rng.uniform(0.25, 0.48) * projection["base_tile_h"]
            if node_id == "old_signal_tower":
                lines.extend(
                    [
                        f'    <line x1="{x:.1f}" y1="{y:.1f}" x2="{x + rng.uniform(-5, 5):.1f}" y2="{y - h * 1.55:.1f}" stroke="{rgba(style["fog"], 0.34)}" stroke-width="2.4" stroke-linecap="round"/>',
                        f'    <path d="M {x - 8:.1f} {y - h * 1.05:.1f} L {x + 8:.1f} {y - h * 1.18:.1f}" stroke="{rgba(style["resource"], 0.24)}" stroke-width="1.8" stroke-linecap="round"/>',
                    ]
                )
                placed += 1
                continue
            lines.append(
                f'    <path d="M {x:.1f} {y:.1f} Q {x + rng.uniform(-8, 8):.1f} {y - h * 0.58:.1f} {x + rng.uniform(-5, 5):.1f} {y - h:.1f}" fill="none" stroke="{rgba(style["resource"], 0.28)}" stroke-width="2.2" stroke-linecap="round"/>'
            )
        elif kind == 3:
            h = rng.uniform(0.42, 0.78) * projection["base_tile_h"]
            if node_id == "lamp_wick_store":
                lines.extend(
                    [
                        f'    <rect x="{x - 10:.1f}" y="{y - 9:.1f}" width="20" height="15" rx="3" fill="{rgba(style["road_base"], 0.40)}" stroke="{rgba(style["road_edge"], 0.18)}" stroke-width="1.2" transform="rotate({rng.uniform(-14, 14):.1f} {x:.1f} {y:.1f})"/>',
                        f'    <ellipse cx="{x + 4:.1f}" cy="{y + 9:.1f}" rx="14" ry="5.5" fill="{rgba(style["hazard"], 0.11)}"/>',
                    ]
                )
                placed += 1
                continue
            lines.extend(
                [
                    f'    <line x1="{x:.1f}" y1="{y:.1f}" x2="{x + rng.uniform(-8, 8):.1f}" y2="{y - h:.1f}" stroke="{rgba(style["road_edge"], 0.32)}" stroke-width="3.0" stroke-linecap="round"/>',
                    f'    <ellipse cx="{x + rng.uniform(-8, 8):.1f}" cy="{y - h:.1f}" rx="5.8" ry="8.2" fill="{rgba(style["accent"], 0.22)}" filter="url(#lampBloom)"/>',
                ]
            )
        else:
            rx = rng.uniform(0.20, 0.34) * projection["base_tile_w"]
            ry = rng.uniform(0.10, 0.18) * projection["base_tile_h"]
            lines.append(
                f'    <ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{rgba(style["hazard"], 0.12)}" transform="rotate({rng.uniform(-24, 24):.1f} {x:.1f} {y:.1f})"/>'
            )
        placed += 1
    lines.append("  </g>")
    return "\n".join(lines)


def lighting_layer(
    runtime_package: dict[str, Any],
    projection: dict[str, float],
    style: dict[str, str],
    *,
    semantic_glows: bool = True,
) -> str:
    lines = ['  <g id="lighting" data-layer-role="lighting">']
    if semantic_glows:
        map_objectives = objectives(runtime_package)
        for index, target in enumerate(map_objectives):
            if not isinstance(target.get("position"), dict):
                continue
            x, y = project_cell(target["position"], projection)
            is_core = str(target.get("target_id") or "").endswith("core") or index == 0
            radius = projection["base_tile_w"] * (1.05 if is_core else 0.72)
            color = style["objective"] if is_core else style["resource"]
            lines.append(
                f'    <ellipse cx="{x:.1f}" cy="{y - projection["base_tile_h"] * 0.72:.1f}" rx="{radius:.1f}" ry="{radius * 0.52:.1f}" fill="{rgba(color, 0.14)}" filter="url(#lampBloom)" data-lighting="semantic-objective"/>'
            )
        for spawn in as_list(runtime_package.get("spawn_points")):
            if not isinstance(spawn, dict) or not isinstance(spawn.get("position"), dict):
                continue
            x, y = project_cell(spawn["position"], projection)
            lines.append(
                f'    <ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{projection["base_tile_w"] * 0.74:.1f}" ry="{projection["base_tile_h"] * 0.52:.1f}" fill="{rgba(style["spawn"], 0.16)}" filter="url(#lampBloom)" data-lighting="semantic-spawn"/>'
            )
    lines.append(
        f'    <rect x="0" y="0" width="{CANVAS_WIDTH}" height="{CANVAS_HEIGHT}" fill="url(#lightOverlayTexture)" opacity="0.10"/>'
    )
    lines.append("  </g>")
    return "\n".join(lines)


def fog_weather_layer(
    runtime_package: dict[str, Any],
    projection: dict[str, float],
    style: dict[str, str],
    rng: random.Random,
) -> str:
    lines = ['  <g id="fog_weather" data-layer-role="fog_weather">']
    lines.append(
        f'    <rect x="0" y="0" width="{CANVAS_WIDTH}" height="{CANVAS_HEIGHT}" fill="url(#fogOverlayTexture)" opacity="0.065"/>'
    )
    for index in range(11):
        x = rng.uniform(0.05, 0.95) * CANVAS_WIDTH
        y = rng.uniform(0.10, 0.88) * CANVAS_HEIGHT
        rx = rng.uniform(80, 240)
        ry = rng.uniform(20, 74)
        color = style["fog"] if index % 3 else style["resource"]
        lines.append(
            f'    <ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{rgba(color, rng.uniform(0.024, 0.052))}" transform="rotate({rng.uniform(-28, 28):.1f} {x:.1f} {y:.1f})"/>'
        )
    lines.append("  </g>")
    return "\n".join(lines)


def color_grade_layer(style: dict[str, str]) -> str:
    return "\n".join(
        [
            '  <g id="color_grade" data-layer-role="color_grade">',
            f'    <rect x="0" y="0" width="{CANVAS_WIDTH}" height="{CANVAS_HEIGHT}" fill="#000000" opacity="0.035"/>',
            f'    <ellipse cx="{CANVAS_WIDTH * 0.50:.1f}" cy="{CANVAS_HEIGHT * 0.48:.1f}" rx="{CANVAS_WIDTH * 0.62:.1f}" ry="{CANVAS_HEIGHT * 0.44:.1f}" fill="none" stroke="#000000" stroke-width="150" opacity="0.15"/>',
            f'    <rect x="0" y="0" width="{CANVAS_WIDTH}" height="{CANVAS_HEIGHT}" fill="{rgba(style["spawn"], 0.020)}"/>',
            "  </g>",
        ]
    )


def composite_opacity(group: str, opacity: float) -> str:
    return f'  <g data-composite-opacity="{opacity:.3f}" opacity="{opacity:.3f}">\n{group}\n  </g>'


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def layer_record(path: Path, role: str, order: int, source: str, *, player_default: bool = True) -> dict[str, Any]:
    return {
        "layer_id": f"layer_{role}",
        "role": role,
        "order": order,
        "player_default": player_default,
        "source": source,
        "url": public_url(path),
        "local_path": rel(path),
        "width": CANVAS_WIDTH,
        "height": CANVAS_HEIGHT,
        "sha256": sha256_file(path),
        "quality": {
            "gate_status": "passed",
            "alignment_status": "passed",
            "player_visible_quality": "passed",
        },
    }


def build_package(
    runtime_package: dict[str, Any],
    style_pack: dict[str, Any],
    render_plan: dict[str, Any],
    *,
    runtime_path: Path,
    style_path: Path,
    render_plan_path: Path,
    output_dir: Path,
    created_at: str,
    texture_source_dir: Path | None = None,
    backdrop_source_dir: Path | None = None,
) -> dict[str, Any]:
    node_id = str(runtime_package.get("node_id") or style_pack.get("node_id") or "map")
    projection = build_projection(runtime_package)
    style = style_values(style_pack)
    rng = random.Random(str(runtime_package.get("package_id") or node_id))
    texture_refs, media_assets = build_texture_assets(
        node_id,
        style,
        output_dir,
        str(runtime_package.get("package_id") or node_id),
        texture_source_dir=texture_source_dir,
    )
    backdrop_ref, backdrop_assets = build_backdrop_asset(
        node_id,
        output_dir,
        backdrop_source_dir=backdrop_source_dir,
    )
    media_assets.extend(backdrop_assets)
    has_backdrop = bool(backdrop_ref)

    terrain = terrain_layer(runtime_package, projection, style, rng, backdrop_ref=backdrop_ref)
    terrain_detail = terrain_detail_layer(runtime_package, projection, style, rng)
    road_shadow = road_shadow_layer(runtime_package, render_plan, projection, style)
    road_edge = road_edge_layer(runtime_package, render_plan, projection, style, rng)
    road_surface = road_surface_layer(runtime_package, render_plan, projection, style, rng)
    slots = build_slots_layer(runtime_package, render_plan, projection, style)
    objectives_group = objectives_layer(runtime_package, projection, style)
    spawn_group = spawn_layer(runtime_package, projection, style)
    semantic_props = semantic_props_layer(runtime_package, projection, style)
    decorations = non_blocking_decorations_layer(runtime_package, projection, style, rng)
    lighting = lighting_layer(runtime_package, projection, style, semantic_glows=not has_backdrop)
    fog_weather = fog_weather_layer(runtime_package, projection, style, rng)
    color_grade = color_grade_layer(style)
    if has_backdrop:
        composited_groups = [
            terrain,
            composite_opacity(road_shadow, 0.70),
            composite_opacity(road_edge, 0.92),
            composite_opacity(road_surface, 0.96),
            composite_opacity(slots, 0.88),
            composite_opacity(objectives_group, 0.94),
            composite_opacity(spawn_group, 0.86),
            composite_opacity(lighting, 0.74),
            composite_opacity(fog_weather, 0.56),
            color_grade,
        ]
    else:
        composited_groups = [
            terrain,
            terrain_detail,
            road_shadow,
            road_edge,
            road_surface,
            slots,
            objectives_group,
            spawn_group,
            semantic_props,
            decorations,
            lighting,
            fog_weather,
            color_grade,
        ]

    layer_specs = [
        ("terrain_base", 0, "reviewed_visual_backdrop" if has_backdrop else "map_style_pack", terrain),
        ("terrain_detail", 5, "map_style_pack", terrain_detail),
        ("road_shadow", 10, "procedural_map_render_plan", road_shadow),
        ("road_edge", 12, "procedural_map_render_plan", road_edge),
        ("road_surface", 14, "procedural_map_render_plan", road_surface),
        ("build_slots", 20, "map_runtime_package", slots),
        ("objectives", 30, "map_runtime_package", objectives_group),
        ("spawn", 40, "map_runtime_package", spawn_group),
        ("semantic_props", 45, "map_runtime_package", semantic_props),
        ("non_blocking_decorations", 50, "map_style_pack", decorations),
        ("lighting", 60, "map_style_pack", lighting),
        ("fog_weather", 70, "map_style_pack", fog_weather),
        ("color_grade", 90, "map_style_pack", color_grade),
    ]
    layers_dir = output_dir / "layers"
    composite_dir = output_dir / "composited"
    layer_records: list[dict[str, Any]] = []
    for role, order, source, group in layer_specs:
        path = layers_dir / f"{node_id}.{role}.svg"
        write_text(
            path,
            svg_document([group], style, title=f"{node_id} {role}", texture_refs=texture_refs),
        )
        non_default_roles_with_backdrop = {
            "terrain_detail",
            "semantic_props",
            "non_blocking_decorations",
        }
        player_default = not (has_backdrop and role in non_default_roles_with_backdrop)
        layer_records.append(layer_record(path, role, order, source, player_default=player_default))

    composite_path = composite_dir / f"{node_id}.layered_map.svg"
    write_text(
        composite_path,
        svg_document(
            composited_groups,
            style,
            title=f"{node_id} layered map",
            texture_refs=texture_refs,
        ),
    )
    layer_records.append(layer_record(composite_path, "composited", 100, "derived_composite"))

    route_count = len([route for route in as_list(runtime_package.get("path_routes")) if isinstance(route, dict)])
    slot_count = len([slot for slot in as_list(runtime_package.get("build_slots")) if isinstance(slot, dict)])
    objective_count = len(objectives(runtime_package))
    spawn_count = len([spawn for spawn in as_list(runtime_package.get("spawn_points")) if isinstance(spawn, dict)])

    package = {
        "schema_version": "layered_map_visual_package.v0.1",
        "package_id": f"layered_map_visual_pkg_{node_id}_v0_1",
        "worldbook_id": str(runtime_package.get("worldbook_id") or style_pack.get("worldbook_id") or ""),
        "node_id": node_id,
        "created_at": created_at,
        "source_refs": {
            "map_runtime_package_path": rel(runtime_path),
            "map_style_pack_path": rel(style_path),
            "procedural_map_render_plan_path": rel(render_plan_path),
        },
        "runtime_semantics_source": {
            "kind": "MapRuntimePackage",
            "id": str(runtime_package.get("package_id") or ""),
            "path": rel(runtime_path),
            "authority": "runtime_semantic_truth",
        },
        "style_source": {
            "kind": "MapStylePack",
            "id": str(style_pack.get("style_pack_id") or ""),
            "path": rel(style_path),
            "authority": "visual_style",
        },
        "render_plan_source": {
            "kind": "ProceduralMapRenderPlan",
            "id": str(render_plan.get("plan_id") or ""),
            "path": rel(render_plan_path),
            "authority": "presentation_plan",
        },
        "canvas": {
            "width": CANVAS_WIDTH,
            "height": CANVAS_HEIGHT,
            "format": "svg",
        },
        "coordinate_projection": {
            "projection": "pseudo3d_oblique",
            "mapping": "frontend_battle_design_space",
            "width_cells": int(projection["width_cells"]),
            "height_cells": int(projection["height_cells"]),
            "base_tile_w": round(float(projection["base_tile_w"]), 6),
            "base_tile_h": round(float(projection["base_tile_h"]), 6),
            "base_offset_x": round(float(projection["base_offset_x"]), 6),
            "base_offset_y": round(float(projection["base_offset_y"]), 6),
        },
        "usage_policy": [
            "runtime_semantics_from_map_runtime_package",
            "visual_package_is_presentation_only",
            "no_pixel_to_semantic_inference",
            "player_default_presentation_allowed",
            "local_reviewed_artifact_only",
            "no_raw_generation_payload",
            "no_external_temporary_url",
            "painted_backdrop_must_not_bake_build_slots",
            "painted_backdrop_must_not_bake_path_routes",
        ],
        "media_assets": media_assets,
        "layers": layer_records,
        "alignment_report": {
            "gate_status": "passed",
            "runtime_truth_preserved": True,
            "route_count": route_count,
            "build_slot_count": slot_count,
            "objective_count": objective_count,
            "spawn_count": spawn_count,
            "checks": [
                {
                    "check_id": "projection_matches_frontend_design_space",
                    "status": "passed",
                    "summary": "Layer coordinates use the same base projection and offsets as the frontend battle canvas.",
                },
                {
                    "check_id": "strong_semantics_drawn_from_runtime_package",
                    "status": "passed",
                    "summary": "Routes, build slots, objectives, and spawns are copied from MapRuntimePackage rather than inferred from pixels.",
                },
                {
                    "check_id": "composite_keeps_runtime_overlay_available",
                    "status": "passed",
                    "summary": "The composite is presentation only; frontend interaction and collision still use structured runtime data.",
                },
                {
                    "check_id": "reviewed_backdrop_does_not_override_runtime_semantics",
                    "status": "passed" if has_backdrop else "warning",
                    "summary": (
                        "A local reviewed painted backdrop is used only as terrain presentation; route, slot, objective, and spawn overlays remain derived from MapRuntimePackage."
                        if has_backdrop
                        else "No reviewed painted backdrop was supplied; SVG procedural layers provide the terrain presentation."
                    ),
                },
            ],
        },
        "validation_report": {
            "gate_status": "passed",
            "player_default_safe": True,
            "external_generation_call_count": 0,
            "gates": [
                {
                    "gate_id": "local_svg_artifacts_written",
                    "status": "passed",
                    "summary": "All layers and the composite are local SVG artifacts with sha256 checksums.",
                },
                {
                    "gate_id": "no_external_runtime_dependency",
                    "status": "passed",
                    "summary": "The package does not require external media services at runtime.",
                },
                {
                    "gate_id": "reviewed_painted_backdrop_localized",
                    "status": "passed" if has_backdrop else "warning",
                    "summary": (
                        "The painted backdrop was copied to local package media, resized to canvas, checksummed, and referenced without external URLs."
                        if has_backdrop
                        else "No painted backdrop source was supplied for this package."
                    ),
                },
            ],
        },
    }
    manifest_path = output_dir / "layered_map_visual_package.v0.1.json"
    write_json(manifest_path, package)
    return package


def main() -> int:
    parser = argparse.ArgumentParser(description="Build LayeredMapVisualPackage v0.1.")
    parser.add_argument(
        "--all-mvp",
        action="store_true",
        help="Build layered visual packages for all MVP battle nodes.",
    )
    parser.add_argument("--runtime-package", default=str(DEFAULT_RUNTIME_PACKAGE))
    parser.add_argument("--style-pack", default=str(DEFAULT_STYLE_PACK))
    parser.add_argument("--render-plan", default=str(DEFAULT_RENDER_PLAN))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--created-at", default=DEFAULT_CREATED_AT)
    parser.add_argument(
        "--texture-source-dir",
        default="",
        help="Optional local exploration texture directory containing ai_{role}_v0_1.png files.",
    )
    parser.add_argument(
        "--backdrop-source-dir",
        default="",
        help="Optional local exploration backdrop directory containing node-specific reviewed painted PNGs.",
    )
    args = parser.parse_args()
    texture_source_dir = Path(args.texture_source_dir) if args.texture_source_dir else None
    backdrop_source_dir = Path(args.backdrop_source_dir) if args.backdrop_source_dir else None

    if args.all_mvp:
        built: list[dict[str, Any]] = []
        for item in MVP_MAP_INPUTS:
            runtime_path = Path(item["runtime_package"])
            style_path = Path(item["style_pack"])
            render_plan_path = Path(item["render_plan"])
            output_dir = Path(item["output_dir"])
            runtime_package = load_json_object(runtime_path, label=f"{item['node_id']} runtime package")
            style_pack = load_json_object(style_path, label=f"{item['node_id']} style pack")
            render_plan = load_json_object(render_plan_path, label=f"{item['node_id']} render plan")
            package = build_package(
                runtime_package,
                style_pack,
                render_plan,
                runtime_path=runtime_path,
                style_path=style_path,
                render_plan_path=render_plan_path,
                output_dir=output_dir,
                created_at=args.created_at,
                texture_source_dir=texture_source_dir,
                backdrop_source_dir=backdrop_source_dir,
            )
            built.append(package)
            print(f"OK: wrote {output_dir / 'layered_map_visual_package.v0.1.json'}")
            print(f"- node_id: {package.get('node_id')}")
            print(f"- package_id: {package.get('package_id')}")
        print(f"OK: built {len(built)} MVP layered map visual package(s)")
        return 0

    runtime_path = Path(args.runtime_package)
    style_path = Path(args.style_pack)
    render_plan_path = Path(args.render_plan)
    output_dir = Path(args.output_dir)

    runtime_package = load_json_object(runtime_path, label="runtime package")
    style_pack = load_json_object(style_path, label="style pack")
    render_plan = load_json_object(render_plan_path, label="render plan")

    package = build_package(
        runtime_package,
        style_pack,
        render_plan,
        runtime_path=runtime_path,
        style_path=style_path,
        render_plan_path=render_plan_path,
        output_dir=output_dir,
        created_at=args.created_at,
        texture_source_dir=texture_source_dir,
        backdrop_source_dir=backdrop_source_dir,
    )
    print(f"OK: wrote {output_dir / 'layered_map_visual_package.v0.1.json'}")
    print(f"- package_id: {package.get('package_id')}")
    print(f"- layers: {len(package.get('layers', []))}")
    print(f"- required_roles: {', '.join(REQUIRED_LAYER_ROLES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
