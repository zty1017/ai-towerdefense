#!/usr/bin/env python3
"""Normalize map candidates and build runtime overlay review artifacts.

This is a review-only tool. It creates normalized candidate PNGs and SVG overlay
files that draw MapRuntimePackage paths, build slots, objectives, and spawn
points over the candidate background. It does not update MapRuntimePackage and
does not publish visual layers.

The implementation intentionally uses only Python stdlib so it works in the
current minimal environment without Pillow, OpenCV, numpy, ImageMagick, or
ffmpeg.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import zlib
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPORT_VERSION = "map_candidate_overlay_review.v0.1"
DEFAULT_ALIGNMENT_REVIEW = ROOT / "examples/review_packs/map_candidate_alignment_review.v0.1.json"
DEFAULT_OUTPUT_DIR = ROOT / "game_data/media/map_visual_reference/node_candidates_v2_normalized"
DEFAULT_REPORT = ROOT / "examples/review_packs/map_candidate_overlay_review.v0.1.json"
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


def resolve_repo_path(value: Any) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def read_png(path: Path) -> tuple[int, int, int, list[bytearray]]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG")
    pos = 8
    width = height = bit_depth = color_type = interlace = None
    idat = bytearray()
    while pos < len(data):
        if pos + 8 > len(data):
            raise ValueError(f"{path} has truncated PNG chunk")
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        kind = data[pos + 4 : pos + 8]
        payload = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(">IIBBBBB", payload)
        elif kind == b"IDAT":
            idat.extend(payload)
        elif kind == b"IEND":
            break
    if None in (width, height, bit_depth, color_type, interlace):
        raise ValueError(f"{path} is missing IHDR")
    if bit_depth != 8 or color_type not in {2, 6} or interlace != 0:
        raise ValueError(
            f"{path} unsupported PNG format: bit_depth={bit_depth}, color_type={color_type}, interlace={interlace}"
        )
    channels = 3 if color_type == 2 else 4
    stride = width * channels
    raw = zlib.decompress(bytes(idat))
    expected = (stride + 1) * height
    if len(raw) != expected:
        raise ValueError(f"{path} unexpected decompressed size: {len(raw)} != {expected}")

    rows: list[bytearray] = []
    offset = 0
    prev = bytearray(stride)
    for _ in range(height):
        filter_type = raw[offset]
        offset += 1
        scanline = bytearray(raw[offset : offset + stride])
        offset += stride
        recon = bytearray(stride)
        for i, value in enumerate(scanline):
            left = recon[i - channels] if i >= channels else 0
            up = prev[i]
            up_left = prev[i - channels] if i >= channels else 0
            if filter_type == 0:
                recon[i] = value
            elif filter_type == 1:
                recon[i] = (value + left) & 0xFF
            elif filter_type == 2:
                recon[i] = (value + up) & 0xFF
            elif filter_type == 3:
                recon[i] = (value + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                recon[i] = (value + paeth(left, up, up_left)) & 0xFF
            else:
                raise ValueError(f"{path} unsupported PNG filter {filter_type}")
        rows.append(recon)
        prev = recon
    return width, height, color_type, rows


def write_png(path: Path, width: int, height: int, color_type: int, rows: list[bytearray]) -> None:
    channels = 3 if color_type == 2 else 4
    if len(rows) != height or any(len(row) != width * channels for row in rows):
        raise ValueError("PNG rows do not match target dimensions")

    def chunk(kind: bytes, payload: bytes) -> bytes:
        crc = zlib.crc32(kind + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)

    raw = bytearray()
    for row in rows:
        raw.append(0)
        raw.extend(row)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    output = bytearray(b"\x89PNG\r\n\x1a\n")
    output.extend(chunk(b"IHDR", ihdr))
    output.extend(chunk(b"IDAT", zlib.compress(bytes(raw), level=6)))
    output.extend(chunk(b"IEND", b""))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(output))


def crop_and_resize_rows(
    width: int,
    height: int,
    color_type: int,
    rows: list[bytearray],
    target_width: int,
    target_height: int,
) -> tuple[list[bytearray], dict[str, Any]]:
    channels = 3 if color_type == 2 else 4
    source_ratio = width / height
    target_ratio = target_width / target_height
    if source_ratio > target_ratio:
        crop_h = height
        crop_w = int(round(height * target_ratio))
    else:
        crop_w = width
        crop_h = int(round(width / target_ratio))
    crop_w = min(crop_w, width)
    crop_h = min(crop_h, height)
    crop_x = max(0, (width - crop_w) // 2)
    crop_y = max(0, (height - crop_h) // 2)

    out_rows: list[bytearray] = []
    for ty in range(target_height):
        sy = crop_y + min(crop_h - 1, int(ty * crop_h / target_height))
        source_row = rows[sy]
        output = bytearray(target_width * channels)
        for tx in range(target_width):
            sx = crop_x + min(crop_w - 1, int(tx * crop_w / target_width))
            src = sx * channels
            dst = tx * channels
            output[dst : dst + channels] = source_row[src : src + channels]
        out_rows.append(output)
    transform = {
        "method": "center_crop_nearest_neighbor_resize",
        "source_size": {"width": width, "height": height},
        "crop_rect": {"x": crop_x, "y": crop_y, "width": crop_w, "height": crop_h},
        "target_size": {"width": target_width, "height": target_height},
    }
    return out_rows, transform


def grid_to_pixel(position: dict[str, Any], grid: dict[str, Any], width: int, height: int) -> tuple[float, float]:
    width_cells = float(grid.get("width_cells") or 1)
    height_cells = float(grid.get("height_cells") or 1)
    x = float(position.get("x") or 0)
    y = float(position.get("y") or 0)
    return ((x + 0.5) / width_cells * width, (y + 0.5) / height_cells * height)


def points_attr(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)


def svg_escape(value: Any) -> str:
    text = str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_overlay_svg(
    path: Path,
    normalized_image: Path,
    package: dict[str, Any],
    width: int,
    height: int,
) -> None:
    grid = as_obj(package.get("grid"))
    href = normalized_image.name
    lines: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'  <image href="{svg_escape(href)}" x="0" y="0" width="{width}" height="{height}"/>',
        '  <rect x="0" y="0" width="1280" height="720" fill="none" stroke="#f8fafc" stroke-width="3" opacity="0.8"/>',
        '  <g id="runtime-paths" fill="none" stroke-linecap="round" stroke-linejoin="round">',
    ]
    for route in as_list(package.get("path_routes")):
        if not isinstance(route, dict):
            continue
        points = [
            grid_to_pixel(point, grid, width, height)
            for point in as_list(route.get("waypoints"))
            if isinstance(point, dict)
        ]
        if len(points) >= 2:
            label = svg_escape(route.get("route_id"))
            lines.append(
                f'    <polyline points="{points_attr(points)}" stroke="#facc15" stroke-width="13" opacity="0.62">'
                f'<title>{label}</title></polyline>'
            )
            lines.append(
                f'    <polyline points="{points_attr(points)}" stroke="#111827" stroke-width="4" opacity="0.75"/>'
            )
    lines.append("  </g>")
    lines.append('  <g id="build-slots" fill="rgba(34,211,238,0.16)" stroke="#22d3ee" stroke-width="4">')
    for slot in as_list(package.get("build_slots")):
        if not isinstance(slot, dict):
            continue
        x, y = grid_to_pixel(as_obj(slot.get("position")), grid, width, height)
        lines.append(
            f'    <circle cx="{x:.1f}" cy="{y:.1f}" r="20"><title>{svg_escape(slot.get("slot_id"))}</title></circle>'
        )
    lines.append("  </g>")
    lines.append('  <g id="spawn-points" fill="#a78bfa" stroke="#1f1147" stroke-width="3">')
    for spawn in as_list(package.get("spawn_points")):
        if not isinstance(spawn, dict):
            continue
        x, y = grid_to_pixel(as_obj(spawn.get("position")), grid, width, height)
        lines.append(
            f'    <polygon points="{x:.1f},{y - 24:.1f} {x - 22:.1f},{y + 18:.1f} {x + 22:.1f},{y + 18:.1f}">'
            f'<title>{svg_escape(spawn.get("spawn_id"))}</title></polygon>'
        )
    lines.append("  </g>")
    lines.append('  <g id="objectives" fill="#fb7185" stroke="#7f1d1d" stroke-width="4">')
    objectives = as_obj(package.get("objectives"))
    objective_items = []
    core = objectives.get("core_target")
    if isinstance(core, dict):
        objective_items.append(core)
    objective_items.extend(target for target in as_list(objectives.get("optional_targets")) if isinstance(target, dict))
    for target in objective_items:
        x, y = grid_to_pixel(as_obj(target.get("position")), grid, width, height)
        lines.append(
            f'    <rect x="{x - 22:.1f}" y="{y - 22:.1f}" width="44" height="44" transform="rotate(45 {x:.1f} {y:.1f})">'
            f'<title>{svg_escape(target.get("target_id"))}</title></rect>'
        )
    lines.append("  </g>")
    lines.append(
        '  <text x="16" y="30" font-family="monospace" font-size="18" fill="#f8fafc" '
        'stroke="#0f172a" stroke-width="4" paint-order="stroke">review overlay: path / build slot / spawn / objective</text>'
    )
    lines.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_package_index(alignment_review: dict[str, Any]) -> dict[str, dict[str, Any]]:
    packages: dict[str, dict[str, Any]] = {}
    for candidate in as_list(alignment_review.get("candidates")):
        if not isinstance(candidate, dict):
            continue
        package_path = resolve_repo_path(candidate.get("runtime_package_path"))
        if package_path and package_path.exists():
            package = load_json(package_path)
            node_id = package.get("node_id")
            if isinstance(node_id, str):
                packages[node_id] = package
    return packages


def build_candidate_artifact(
    candidate: dict[str, Any],
    package: dict[str, Any],
    output_dir: Path,
    target_width: int,
    target_height: int,
) -> dict[str, Any]:
    node_id = str(candidate.get("node_id") or "unknown_node")
    source_path = resolve_repo_path(candidate.get("candidate_path"))
    if source_path is None or not source_path.exists():
        return {
            "node_id": node_id,
            "status": "blocked",
            "issues": ["candidate_image_missing"],
        }
    width, height, color_type, rows = read_png(source_path)
    normalized_rows, transform = crop_and_resize_rows(
        width,
        height,
        color_type,
        rows,
        target_width,
        target_height,
    )
    normalized_path = output_dir / f"{node_id}.normalized_{target_width}x{target_height}.png"
    overlay_path = output_dir / f"{node_id}.overlay_review.svg"
    write_png(normalized_path, target_width, target_height, color_type, normalized_rows)
    build_overlay_svg(overlay_path, normalized_path, package, target_width, target_height)

    runtime_structure = as_obj(candidate.get("runtime_structure"))
    return {
        "node_id": node_id,
        "status": "overlay_artifact_ready",
        "source_candidate_path": candidate.get("candidate_path"),
        "normalized_path": rel(normalized_path),
        "overlay_review_path": rel(overlay_path),
        "normalized_sha256": sha256_file(normalized_path),
        "overlay_sha256": sha256_file(overlay_path),
        "transform": transform,
        "runtime_structure": runtime_structure,
        "review_notes": [
            "Overlay is approximate and uses logical grid-to-pixel projection.",
            "This artifact is for alignment review only and is not a published runtime visual layer.",
            "Overlay artifact readiness does not mean visual alignment approval.",
            "Promotion still requires visual readability approval and MapRuntimePackage update in a separate step.",
        ],
    }


def build_report(
    alignment_review_path: Path,
    output_dir: Path,
    target_width: int,
    target_height: int,
) -> dict[str, Any]:
    alignment_review = load_json(alignment_review_path)
    packages = build_package_index(alignment_review)
    artifacts: list[dict[str, Any]] = []
    for candidate in as_list(alignment_review.get("candidates")):
        if not isinstance(candidate, dict):
            continue
        node_id = str(candidate.get("node_id") or "")
        package = packages.get(node_id)
        if package is None:
            artifacts.append({"node_id": node_id, "status": "blocked", "issues": ["runtime_package_missing"]})
            continue
        artifacts.append(build_candidate_artifact(candidate, package, output_dir, target_width, target_height))

    status_counts = Counter(str(artifact.get("status")) for artifact in artifacts)
    blocked_count = status_counts.get("blocked", 0)
    return {
        "schema_version": REPORT_VERSION,
        "report_id": "mvp_map_candidate_overlay_review",
        "alignment_review_path": rel(alignment_review_path),
        "output_dir": rel(output_dir),
        "status": "blocked" if blocked_count else "overlay_artifacts_ready_review_required",
        "summary": {
            "candidate_count": len(artifacts),
            "overlay_artifact_ready_count": status_counts.get("overlay_artifact_ready", 0),
            "blocked_count": blocked_count,
            "status_counts": dict(sorted(status_counts.items())),
            "target_size": {"width": target_width, "height": target_height},
        },
        "artifacts": artifacts,
        "policy": [
            "Normalized PNGs and overlay SVGs are review-only artifacts.",
            "The frontend runtime must not consume these files unless a later promotion report updates the published visual layer.",
            "Runtime truth remains MapRuntimePackage; the overlay exists to inspect whether the visual candidate fits that truth.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build normalized map candidate overlay review artifacts.")
    parser.add_argument("--alignment-review", default=str(DEFAULT_ALIGNMENT_REVIEW))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--target-size", default=f"{TARGET_WIDTH}x{TARGET_HEIGHT}")
    args = parser.parse_args()

    alignment_review = Path(args.alignment_review)
    if not alignment_review.is_absolute():
        alignment_review = ROOT / alignment_review
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    try:
        target_width_s, target_height_s = args.target_size.lower().split("x", 1)
        target_width = int(target_width_s)
        target_height = int(target_height_s)
    except ValueError as exc:
        raise SystemExit(f"invalid --target-size {args.target_size!r}; expected WIDTHxHEIGHT") from exc

    report = build_report(alignment_review, output_dir, target_width, target_height)
    write_json(report_path, report)
    print(f"Wrote {report_path}")
    print(f"- status: {report['status']}")
    print(f"- overlay_artifacts: {report['summary']['overlay_artifact_ready_count']}")
    return 0 if report["summary"]["candidate_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
