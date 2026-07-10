#!/usr/bin/env python3
"""Build deterministic reviewed PNG atlas markers for the strategic map.

This builder is offline by design. It does not call providers, does not read
.env, and does not derive map gameplay semantics from images. The source map
only determines which node kinds need presentation markers.
"""

from __future__ import annotations

import argparse
import binascii
import hashlib
import json
import math
import struct
import zlib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_MAP = ROOT / "game_data/demo/initial_map.json"
DEFAULT_OUTPUT_DIR = ROOT / "game_data/media/strategic_map_markers/processed"
DEFAULT_MANIFEST = (
    ROOT / "game_data/media/strategic_map_markers/strategic_map_marker_media_manifest.v0.1.json"
)
PUBLIC_PREFIX = "/assets/strategic_map_markers/processed"
FRAME_SIZE = 128
SCALE = 4
USAGE_POLICY = [
    "review_gate_only",
    "not_runtime_semantic_source",
    "no_image_to_map_semantic_inference",
    "local_reviewed_marker_only",
    "frontend_default_presentation_allowed",
    "no_provider_or_prompt_payload",
    "no_external_temporary_url",
]
MARKER_PROFILES = {
    "main_city": {
        "state_hint": "controlled",
        "color": "#e0b85d",
        "display": 42,
        "priority": 10,
    },
    "battle_hotspot": {
        "state_hint": "crisis_active",
        "color": "#d96a5d",
        "display": 42,
        "priority": 20,
    },
    "research_facility": {
        "state_hint": "available",
        "color": "#71cbbf",
        "display": 38,
        "priority": 30,
    },
    "resource_storage": {
        "state_hint": "controlled",
        "color": "#a1c66c",
        "display": 38,
        "priority": 40,
    },
    "generic": {
        "state_hint": "available",
        "color": "#d6c27e",
        "display": 36,
        "priority": 99,
    },
}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_hex(value: str, alpha: int = 255) -> tuple[int, int, int, int]:
    raw = value.lstrip("#")
    return (int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16), alpha)


def shade(color: tuple[int, int, int, int], delta: int, alpha: int | None = None) -> tuple[int, int, int, int]:
    return (
        max(0, min(255, color[0] + delta)),
        max(0, min(255, color[1] + delta)),
        max(0, min(255, color[2] + delta)),
        color[3] if alpha is None else alpha,
    )


class Canvas:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.pixels = bytearray(width * height * 4)

    def blend_pixel(self, x: int, y: int, color: tuple[int, int, int, int]) -> None:
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return
        sr, sg, sb, sa = color
        if sa <= 0:
            return
        offset = (y * self.width + x) * 4
        dr, dg, db, da = self.pixels[offset : offset + 4]
        src_a = sa / 255
        dst_a = da / 255
        out_a = src_a + dst_a * (1 - src_a)
        if out_a <= 0:
            return
        self.pixels[offset] = round((sr * src_a + dr * dst_a * (1 - src_a)) / out_a)
        self.pixels[offset + 1] = round((sg * src_a + dg * dst_a * (1 - src_a)) / out_a)
        self.pixels[offset + 2] = round((sb * src_a + db * dst_a * (1 - src_a)) / out_a)
        self.pixels[offset + 3] = round(out_a * 255)

    def fill_ellipse(
        self,
        cx: float,
        cy: float,
        rx: float,
        ry: float,
        color: tuple[int, int, int, int],
    ) -> None:
        min_x = max(0, math.floor(cx - rx))
        max_x = min(self.width - 1, math.ceil(cx + rx))
        min_y = max(0, math.floor(cy - ry))
        max_y = min(self.height - 1, math.ceil(cy + ry))
        rx2 = max(1, rx * rx)
        ry2 = max(1, ry * ry)
        for y in range(min_y, max_y + 1):
            yy = ((y + 0.5 - cy) ** 2) / ry2
            if yy > 1:
                continue
            for x in range(min_x, max_x + 1):
                if ((x + 0.5 - cx) ** 2) / rx2 + yy <= 1:
                    self.blend_pixel(x, y, color)

    def stroke_line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        width: float,
        color: tuple[int, int, int, int],
    ) -> None:
        length = max(1, math.hypot(x2 - x1, y2 - y1))
        steps = max(1, math.ceil(length / max(1, width * 0.35)))
        radius = width / 2
        for index in range(steps + 1):
            t = index / steps
            self.fill_ellipse(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, radius, radius, color)

    def stroke_polyline(
        self,
        points: list[tuple[float, float]],
        width: float,
        color: tuple[int, int, int, int],
    ) -> None:
        for p1, p2 in zip(points, points[1:]):
            self.stroke_line(p1[0], p1[1], p2[0], p2[1], width, color)

    def stroke_circle(
        self,
        cx: float,
        cy: float,
        radius: float,
        width: float,
        color: tuple[int, int, int, int],
    ) -> None:
        steps = max(32, int(radius * 2.4))
        previous = None
        for index in range(steps + 1):
            angle = math.tau * index / steps
            point = (cx + math.cos(angle) * radius, cy + math.sin(angle) * radius)
            if previous is not None:
                self.stroke_line(previous[0], previous[1], point[0], point[1], width, color)
            previous = point

    def paste(self, other: "Canvas", x0: int, y0: int) -> None:
        for y in range(other.height):
            for x in range(other.width):
                offset = (y * other.width + x) * 4
                self.blend_pixel(x0 + x, y0 + y, tuple(other.pixels[offset : offset + 4]))


def scaled(value: float) -> float:
    return value * SCALE


def downsample(canvas: Canvas, scale: int) -> Canvas:
    out = Canvas(canvas.width // scale, canvas.height // scale)
    for y in range(out.height):
        for x in range(out.width):
            total = [0, 0, 0, 0]
            for sy in range(scale):
                for sx in range(scale):
                    offset = ((y * scale + sy) * canvas.width + x * scale + sx) * 4
                    for channel in range(4):
                        total[channel] += canvas.pixels[offset + channel]
            count = scale * scale
            out_offset = (y * out.width + x) * 4
            for channel in range(4):
                out.pixels[out_offset + channel] = round(total[channel] / count)
    return out


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF)
    )


def write_png(path: Path, canvas: Canvas) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = bytearray()
    stride = canvas.width * 4
    for y in range(canvas.height):
        raw.append(0)
        raw.extend(canvas.pixels[y * stride : (y + 1) * stride])
    payload = (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", struct.pack(">IIBBBBB", canvas.width, canvas.height, 8, 6, 0, 0, 0))
        + png_chunk(b"IDAT", zlib.compress(bytes(raw), level=9))
        + png_chunk(b"IEND", b"")
    )
    path.write_bytes(payload)


def marker_canvas(kind: str, color_hex: str) -> Canvas:
    canvas = Canvas(FRAME_SIZE * SCALE, FRAME_SIZE * SCALE)
    color = parse_hex(color_hex)
    warm = (255, 239, 196, 230)
    dark = (7, 11, 10, 186)
    cx = scaled(64)
    cy = scaled(62)

    canvas.fill_ellipse(cx, scaled(82), scaled(31), scaled(11), (0, 0, 0, 82))
    for index, alpha in enumerate((26, 18, 12)):
        canvas.fill_ellipse(cx, cy, scaled(38 + index * 8), scaled(38 + index * 8), shade(color, 0, alpha))
    canvas.fill_ellipse(cx, cy, scaled(24), scaled(24), dark)
    canvas.stroke_circle(cx, cy, scaled(22), scaled(3.0), shade(color, 16, 214))
    canvas.stroke_circle(cx, cy, scaled(15), scaled(1.5), shade(color, 38, 122))
    canvas.fill_ellipse(cx, cy, scaled(11), scaled(11), shade(color, 22, 54))

    if kind == "main_city":
        canvas.stroke_line(scaled(54), scaled(55), scaled(74), scaled(55), scaled(2.4), warm)
        canvas.stroke_line(scaled(58), scaled(47), scaled(56), scaled(69), scaled(2.4), warm)
        canvas.stroke_line(scaled(70), scaled(47), scaled(72), scaled(69), scaled(2.4), warm)
        canvas.stroke_line(scaled(57), scaled(68), scaled(71), scaled(68), scaled(2.4), warm)
        canvas.stroke_line(scaled(53), scaled(61), scaled(75), scaled(61), scaled(1.8), warm)
        canvas.fill_ellipse(scaled(64), scaled(62), scaled(4), scaled(7), (255, 218, 125, 214))
    elif kind == "battle_hotspot":
        canvas.stroke_polyline(
            [(scaled(51), scaled(72)), (scaled(64), scaled(47)), (scaled(77), scaled(72))],
            scaled(3.0),
            warm,
        )
        canvas.stroke_line(scaled(64), scaled(55), scaled(64), scaled(64), scaled(2.6), warm)
        canvas.fill_ellipse(scaled(64), scaled(70), scaled(2.4), scaled(2.4), warm)
        canvas.stroke_polyline(
            [(scaled(47), scaled(75)), (scaled(58), scaled(80)), (scaled(70), scaled(80)), (scaled(81), scaled(75))],
            scaled(1.8),
            shade(color, 40, 160),
        )
    elif kind == "research_facility":
        canvas.stroke_line(scaled(52), scaled(70), scaled(76), scaled(70), scaled(2.4), warm)
        canvas.stroke_polyline(
            [(scaled(56), scaled(70)), (scaled(59), scaled(50)), (scaled(69), scaled(50)), (scaled(72), scaled(70))],
            scaled(2.4),
            warm,
        )
        canvas.stroke_line(scaled(58), scaled(60), scaled(70), scaled(60), scaled(1.6), warm)
        canvas.stroke_line(scaled(66), scaled(50), scaled(66), scaled(42), scaled(2.1), warm)
        canvas.stroke_line(scaled(66), scaled(42), scaled(75), scaled(42), scaled(2.1), warm)
    elif kind == "resource_storage":
        canvas.stroke_polyline(
            [(scaled(53), scaled(53)), (scaled(64), scaled(48)), (scaled(75), scaled(53)), (scaled(75), scaled(69)), (scaled(64), scaled(76)), (scaled(53), scaled(69)), (scaled(53), scaled(53))],
            scaled(2.4),
            warm,
        )
        canvas.stroke_polyline(
            [(scaled(53), scaled(53)), (scaled(64), scaled(60)), (scaled(75), scaled(53))],
            scaled(1.7),
            warm,
        )
        canvas.stroke_line(scaled(57), scaled(66), scaled(71), scaled(66), scaled(1.8), warm)
    else:
        canvas.fill_ellipse(cx, cy, scaled(5), scaled(5), warm)

    return downsample(canvas, SCALE)


def marker_kinds(source_map: dict[str, Any]) -> list[str]:
    kinds = {
        str(node.get("kind") or "generic")
        for node in source_map.get("nodes", [])
        if isinstance(node, dict)
    }
    kinds.add("generic")
    return sorted(kinds, key=lambda kind: MARKER_PROFILES.get(kind, MARKER_PROFILES["generic"])["priority"])


def build_pack(source_map_path: Path, output_dir: Path, manifest_path: Path, *, created_at: str) -> dict[str, Any]:
    source_map = load_json(source_map_path)
    if not isinstance(source_map, dict):
        raise ValueError(f"source map root must be an object: {source_map_path}")

    kinds = marker_kinds(source_map)
    atlas = Canvas(FRAME_SIZE * len(kinds), FRAME_SIZE)
    items: list[dict[str, Any]] = []

    for index, kind in enumerate(kinds):
        profile = MARKER_PROFILES.get(kind, MARKER_PROFILES["generic"])
        marker = marker_canvas(kind, str(profile["color"]))
        atlas.paste(marker, index * FRAME_SIZE, 0)
        state_hint = str(profile["state_hint"])
        stable_id = f"strategic_map_marker_{kind}_{state_hint}"
        items.append(
            {
                "stable_internal_id": stable_id,
                "asset_id": stable_id,
                "asset_type": "strategic_map_marker",
                "media_role": "strategic_node_marker",
                "media_layer": "reviewed_strategic_map_marker_media",
                "node_kind": kind,
                "state_hint": state_hint,
                "atlas_frame": {
                    "x": index * FRAME_SIZE,
                    "y": 0,
                    "width": FRAME_SIZE,
                    "height": FRAME_SIZE,
                    "anchor_x": 64,
                    "anchor_y": 64,
                    "display_width": int(profile["display"]),
                    "display_height": int(profile["display"]),
                },
                "usage_policy": USAGE_POLICY,
                "source_kind": "deterministic_developer_fixture_png_atlas",
            }
        )

    atlas_path = output_dir / "strategic_map_markers.atlas.png"
    write_png(atlas_path, atlas)
    kind_counts = Counter(item["node_kind"] for item in items)
    manifest = {
        "schema_version": "strategic_map_marker_media_manifest.v0.1",
        "media_pack_id": "strategic_map_marker_media_pack_v0_1",
        "created_at": created_at,
        "source_map_path": rel(source_map_path),
        "public_url_prefix": "/assets/strategic_map_markers",
        "media_layer": "reviewed_strategic_map_marker_media",
        "usage_policy": USAGE_POLICY,
        "atlas": {
            "url": f"{PUBLIC_PREFIX}/{atlas_path.name}",
            "local_path": rel(atlas_path),
            "width": atlas.width,
            "height": atlas.height,
            "sha256": sha256_file(atlas_path),
        },
        "items": items,
        "summary": {
            "marker_count": len(items),
            "atlas_frame_count": len(items),
            "node_kinds": dict(sorted(kind_counts.items())),
        },
        "validation": {
            "validator": "tools/media/validate_strategic_map_marker_media_pack.py",
            "commands": [
                "python3 tools/media/validate_strategic_map_marker_media_pack.py game_data/media/strategic_map_markers/strategic_map_marker_media_manifest.v0.1.json"
            ],
        },
    }
    write_json(manifest_path, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build strategic map marker PNG atlas and manifest.")
    parser.add_argument("--source-map", default=str(DEFAULT_SOURCE_MAP))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--created-at", default=now_iso())
    args = parser.parse_args()

    manifest = build_pack(
        resolve_path(args.source_map),
        resolve_path(args.output_dir),
        resolve_path(args.manifest),
        created_at=args.created_at,
    )
    print(f"OK: wrote {args.manifest}")
    print(f"- marker_count: {manifest['summary']['marker_count']}")
    print(f"- atlas: {manifest['atlas']['local_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
