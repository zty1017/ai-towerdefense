"""Small pure-Python PNG media pipeline for MVP sprite processing.

This is intentionally narrow: 8-bit, non-interlaced RGB/RGBA PNG only. It is
enough for controlled `sprite_source` / `cutout_source` assets with a pure matte
background, and keeps the MVP pipeline runnable without Pillow.
"""

from __future__ import annotations

import binascii
import json
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PNG_SIG = b"\x89PNG\r\n\x1a\n"


@dataclass
class PngImage:
    width: int
    height: int
    pixels: bytearray  # RGBA, row-major


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def read_png(path: Path) -> PngImage:
    data = path.read_bytes()
    if not data.startswith(PNG_SIG):
        raise ValueError(f"{path} is not a PNG file")

    pos = len(PNG_SIG)
    width = height = bit_depth = color_type = None
    idat = bytearray()

    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        chunk_type = data[pos + 4 : pos + 8]
        payload = data[pos + 8 : pos + 8 + length]
        pos += 12 + length

        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(
                ">IIBBBBB", payload
            )
            if bit_depth != 8:
                raise ValueError("only 8-bit PNG files are supported")
            if color_type not in {2, 6}:
                raise ValueError("only RGB/RGBA PNG files are supported")
            if compression != 0 or filter_method != 0 or interlace != 0:
                raise ValueError("only non-interlaced standard PNG files are supported")
        elif chunk_type == b"IDAT":
            idat.extend(payload)
        elif chunk_type == b"IEND":
            break

    if width is None or height is None or color_type is None:
        raise ValueError("PNG missing IHDR")

    channels = 4 if color_type == 6 else 3
    bpp = channels
    stride = width * channels
    raw = zlib.decompress(bytes(idat))
    expected = (stride + 1) * height
    if len(raw) != expected:
        raise ValueError(f"unexpected PNG scanline size: got {len(raw)}, expected {expected}")

    recon = bytearray(width * height * channels)
    src = 0
    prev = bytearray(stride)
    for row in range(height):
        filter_type = raw[src]
        src += 1
        line = bytearray(raw[src : src + stride])
        src += stride
        for i in range(stride):
            left = line[i - bpp] if i >= bpp else 0
            up = prev[i]
            up_left = prev[i - bpp] if i >= bpp else 0
            if filter_type == 0:
                value = line[i]
            elif filter_type == 1:
                value = (line[i] + left) & 0xFF
            elif filter_type == 2:
                value = (line[i] + up) & 0xFF
            elif filter_type == 3:
                value = (line[i] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                value = (line[i] + _paeth(left, up, up_left)) & 0xFF
            else:
                raise ValueError(f"unsupported PNG filter type: {filter_type}")
            line[i] = value
        start = row * stride
        recon[start : start + stride] = line
        prev = line

    if channels == 4:
        pixels = recon
    else:
        pixels = bytearray(width * height * 4)
        for i in range(width * height):
            pixels[i * 4 : i * 4 + 3] = recon[i * 3 : i * 3 + 3]
            pixels[i * 4 + 3] = 255
    return PngImage(width=width, height=height, pixels=pixels)


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF)
    )


def write_png(path: Path, image: PngImage) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = bytearray()
    stride = image.width * 4
    for y in range(image.height):
        rows.append(0)
        start = y * stride
        rows.extend(image.pixels[start : start + stride])
    payload = struct.pack(">IIBBBBB", image.width, image.height, 8, 6, 0, 0, 0)
    data = PNG_SIG + _chunk(b"IHDR", payload) + _chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + _chunk(b"IEND", b"")
    path.write_bytes(data)


def _idx(width: int, x: int, y: int) -> int:
    return (y * width + x) * 4


def _rgb_at(image: PngImage, x: int, y: int) -> tuple[int, int, int]:
    i = _idx(image.width, x, y)
    return image.pixels[i], image.pixels[i + 1], image.pixels[i + 2]


def estimate_background_rgb(image: PngImage) -> tuple[int, int, int]:
    coords = [
        (0, 0),
        (image.width - 1, 0),
        (0, image.height - 1),
        (image.width - 1, image.height - 1),
    ]
    samples = [_rgb_at(image, x, y) for x, y in coords]
    return tuple(sorted(channel)[len(channel) // 2] for channel in zip(*samples))  # type: ignore[return-value]


def remove_matte_background(
    image: PngImage,
    *,
    threshold: int = 28,
    background_rgb: tuple[int, int, int] | None = None,
) -> PngImage:
    bg = background_rgb or estimate_background_rgb(image)
    out = bytearray(image.pixels)
    for p in range(0, len(out), 4):
        r, g, b, a = out[p], out[p + 1], out[p + 2], out[p + 3]
        if a == 0:
            continue
        dist = max(abs(r - bg[0]), abs(g - bg[1]), abs(b - bg[2]))
        if dist <= threshold:
            out[p + 3] = 0
    return PngImage(image.width, image.height, out)


def remove_edge_matte_background(
    image: PngImage,
    *,
    threshold: int = 36,
    background_rgb: tuple[int, int, int] | None = None,
) -> PngImage:
    """Remove matte background only when it is connected to canvas edges.

    Unlike global matte removal, this preserves light-colored details inside
    the subject, such as pale stone, glass highlights, or paper-like props.
    """
    bg = background_rgb or estimate_background_rgb(image)
    width, height = image.width, image.height
    total = width * height
    visited = bytearray(total)
    stack: list[int] = []

    def near_bg(pos: int) -> bool:
        p = pos * 4
        if image.pixels[p + 3] == 0:
            return True
        r, g, b = image.pixels[p], image.pixels[p + 1], image.pixels[p + 2]
        dist = max(abs(r - bg[0]), abs(g - bg[1]), abs(b - bg[2]))
        return dist <= threshold

    for x in range(width):
        stack.append(x)
        stack.append((height - 1) * width + x)
    for y in range(height):
        stack.append(y * width)
        stack.append(y * width + width - 1)

    background = bytearray(total)
    while stack:
        pos = stack.pop()
        if visited[pos]:
            continue
        visited[pos] = 1
        if not near_bg(pos):
            continue
        background[pos] = 1
        x = pos % width
        y = pos // width
        if x > 0:
            stack.append(pos - 1)
        if x + 1 < width:
            stack.append(pos + 1)
        if y > 0:
            stack.append(pos - width)
        if y + 1 < height:
            stack.append(pos + width)

    out = bytearray(image.pixels)
    for pos, is_background in enumerate(background):
        if is_background:
            out[pos * 4 + 3] = 0
    return PngImage(width, height, out)


def clear_transparent_rgb(image: PngImage, *, alpha_threshold: int = 0) -> PngImage:
    """Set RGB to black for transparent pixels while preserving alpha."""
    out = bytearray(image.pixels)
    for p in range(0, len(out), 4):
        if out[p + 3] <= alpha_threshold:
            out[p] = 0
            out[p + 1] = 0
            out[p + 2] = 0
    return PngImage(image.width, image.height, out)


def alpha_bbox(image: PngImage, *, alpha_threshold: int = 8) -> tuple[int, int, int, int] | None:
    min_x, min_y = image.width, image.height
    max_x, max_y = -1, -1
    for y in range(image.height):
        row = y * image.width * 4
        for x in range(image.width):
            if image.pixels[row + x * 4 + 3] > alpha_threshold:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
    if max_x < min_x or max_y < min_y:
        return None
    return min_x, min_y, max_x + 1, max_y + 1


def keep_largest_alpha_component(image: PngImage, *, alpha_threshold: int = 8) -> PngImage:
    """Keep only the largest connected visible alpha component.

    This removes detached generation artifacts such as floating debris,
    watermark islands, loose smoke wisps, and stray UI marks after matte
    removal. It is intentionally conservative and uses 4-neighbour
    connectivity.
    """
    width, height = image.width, image.height
    total = width * height
    visited = bytearray(total)
    largest: list[int] = []

    def visible(pos: int) -> bool:
        return image.pixels[pos * 4 + 3] > alpha_threshold

    for start in range(total):
        if visited[start] or not visible(start):
            continue
        visited[start] = 1
        stack = [start]
        component: list[int] = []
        while stack:
            pos = stack.pop()
            component.append(pos)
            x = pos % width
            y = pos // width
            if x > 0:
                nxt = pos - 1
                if not visited[nxt] and visible(nxt):
                    visited[nxt] = 1
                    stack.append(nxt)
            if x + 1 < width:
                nxt = pos + 1
                if not visited[nxt] and visible(nxt):
                    visited[nxt] = 1
                    stack.append(nxt)
            if y > 0:
                nxt = pos - width
                if not visited[nxt] and visible(nxt):
                    visited[nxt] = 1
                    stack.append(nxt)
            if y + 1 < height:
                nxt = pos + width
                if not visited[nxt] and visible(nxt):
                    visited[nxt] = 1
                    stack.append(nxt)
        if len(component) > len(largest):
            largest = component

    if not largest:
        return image

    keep = bytearray(total)
    for pos in largest:
        keep[pos] = 1

    out = bytearray(image.pixels)
    for pos in range(total):
        if not keep[pos]:
            out[pos * 4 + 3] = 0
    return PngImage(width, height, out)


def remove_small_alpha_components(
    image: PngImage,
    *,
    alpha_threshold: int = 8,
    min_pixels: int = 96,
) -> PngImage:
    """Remove detached visible components smaller than `min_pixels`."""
    width, height = image.width, image.height
    total = width * height
    visited = bytearray(total)
    keep = bytearray(total)

    def visible(pos: int) -> bool:
        return image.pixels[pos * 4 + 3] > alpha_threshold

    for start in range(total):
        if visited[start] or not visible(start):
            continue
        visited[start] = 1
        stack = [start]
        component: list[int] = []
        while stack:
            pos = stack.pop()
            component.append(pos)
            x = pos % width
            y = pos // width
            if x > 0:
                nxt = pos - 1
                if not visited[nxt] and visible(nxt):
                    visited[nxt] = 1
                    stack.append(nxt)
            if x + 1 < width:
                nxt = pos + 1
                if not visited[nxt] and visible(nxt):
                    visited[nxt] = 1
                    stack.append(nxt)
            if y > 0:
                nxt = pos - width
                if not visited[nxt] and visible(nxt):
                    visited[nxt] = 1
                    stack.append(nxt)
            if y + 1 < height:
                nxt = pos + width
                if not visited[nxt] and visible(nxt):
                    visited[nxt] = 1
                    stack.append(nxt)
        if len(component) >= min_pixels:
            for pos in component:
                keep[pos] = 1

    out = bytearray(image.pixels)
    for pos in range(total):
        if visible(pos) and not keep[pos]:
            out[pos * 4 + 3] = 0
    return PngImage(width, height, out)


def remove_near_white_background_islands(
    image: PngImage,
    *,
    alpha_threshold: int = 8,
    min_luma: int = 238,
    max_chroma: int = 22,
    min_pixels: int = 48,
) -> PngImage:
    """Remove enclosed near-white matte islands after edge background removal.

    Generated assets often contain white matte pockets inside tower lattice,
    between an object and a baked glow, or inside open mechanical frames. Edge
    flood-fill cannot reach those pockets. This pass removes only low-chroma,
    high-luma components large enough to be background rather than tiny specular
    highlights.
    """
    width, height = image.width, image.height
    total = width * height
    visited = bytearray(total)
    remove = bytearray(total)

    def candidate(pos: int) -> bool:
        p = pos * 4
        if image.pixels[p + 3] <= alpha_threshold:
            return False
        r, g, b = image.pixels[p], image.pixels[p + 1], image.pixels[p + 2]
        luma = (r * 299 + g * 587 + b * 114) // 1000
        chroma = max(r, g, b) - min(r, g, b)
        return luma >= min_luma and chroma <= max_chroma

    for start in range(total):
        if visited[start] or not candidate(start):
            continue
        visited[start] = 1
        stack = [start]
        component: list[int] = []
        while stack:
            pos = stack.pop()
            component.append(pos)
            x = pos % width
            y = pos // width
            if x > 0:
                nxt = pos - 1
                if not visited[nxt] and candidate(nxt):
                    visited[nxt] = 1
                    stack.append(nxt)
            if x + 1 < width:
                nxt = pos + 1
                if not visited[nxt] and candidate(nxt):
                    visited[nxt] = 1
                    stack.append(nxt)
            if y > 0:
                nxt = pos - width
                if not visited[nxt] and candidate(nxt):
                    visited[nxt] = 1
                    stack.append(nxt)
            if y + 1 < height:
                nxt = pos + width
                if not visited[nxt] and candidate(nxt):
                    visited[nxt] = 1
                    stack.append(nxt)
        if len(component) >= min_pixels:
            for pos in component:
                remove[pos] = 1

    out = bytearray(image.pixels)
    for pos, should_remove in enumerate(remove):
        if should_remove:
            out[pos * 4 + 3] = 0
    return PngImage(width, height, out)


def crop_and_pad(image: PngImage, *, padding: int = 24, alpha_threshold: int = 8) -> PngImage:
    bbox = alpha_bbox(image, alpha_threshold=alpha_threshold)
    if bbox is None:
        return image
    x0, y0, x1, y1 = bbox
    out_w = (x1 - x0) + padding * 2
    out_h = (y1 - y0) + padding * 2
    out = bytearray(out_w * out_h * 4)
    for y in range(y0, y1):
        for x in range(x0, x1):
            src = _idx(image.width, x, y)
            dst = _idx(out_w, x - x0 + padding, y - y0 + padding)
            out[dst : dst + 4] = image.pixels[src : src + 4]
    return PngImage(out_w, out_h, out)


def center_crop_to_ratio(image: PngImage, ratio: float) -> PngImage:
    if ratio <= 0:
        raise ValueError("ratio must be positive")
    current = image.width / image.height
    if abs(current - ratio) < 0.001:
        return image
    if current > ratio:
        target_w = max(1, round(image.height * ratio))
        target_h = image.height
        x0 = (image.width - target_w) // 2
        y0 = 0
    else:
        target_w = image.width
        target_h = max(1, round(image.width / ratio))
        x0 = 0
        y0 = (image.height - target_h) // 2
    out = bytearray(target_w * target_h * 4)
    for y in range(target_h):
        src = _idx(image.width, x0, y0 + y)
        dst = _idx(target_w, 0, y)
        out[dst : dst + target_w * 4] = image.pixels[src : src + target_w * 4]
    return PngImage(target_w, target_h, out)


def normalize_canvas(
    image: PngImage,
    *,
    square: bool = True,
    min_size: int = 1,
    align: str = "center",
    bottom_padding: int = 0,
) -> PngImage:
    target_w = max(image.width, min_size)
    target_h = max(image.height, min_size)
    if square:
        target_w = target_h = max(target_w, target_h)
    out = bytearray(target_w * target_h * 4)
    offset_x = (target_w - image.width) // 2
    if align == "bottom_center":
        offset_y = max(0, target_h - image.height - bottom_padding)
    else:
        offset_y = (target_h - image.height) // 2
    for y in range(image.height):
        if 0 <= y + offset_y < target_h:
            for x in range(image.width):
                if 0 <= x + offset_x < target_w:
                    src = _idx(image.width, x, y)
                    dst = _idx(target_w, x + offset_x, y + offset_y)
                    out[dst : dst + 4] = image.pixels[src : src + 4]
    return PngImage(target_w, target_h, out)


def transparent_image(width: int, height: int) -> PngImage:
    return PngImage(width, height, bytearray(width * height * 4))


def paste(base: PngImage, image: PngImage, x0: int, y0: int) -> None:
    for y in range(image.height):
        for x in range(image.width):
            src = _idx(image.width, x, y)
            dst = _idx(base.width, x0 + x, y0 + y)
            base.pixels[dst : dst + 4] = image.pixels[src : src + 4]


def pack_horizontal(items: list[tuple[str, Path, dict[str, Any]]]) -> tuple[PngImage, dict[str, Any]]:
    loaded: list[tuple[str, PngImage, dict[str, Any]]] = []
    for stable_id, path, metadata in items:
        loaded.append((stable_id, read_png(path), metadata))
    width = sum(img.width for _, img, _ in loaded)
    height = max((img.height for _, img, _ in loaded), default=1)
    atlas = transparent_image(max(width, 1), max(height, 1))
    frames: dict[str, Any] = {}
    cursor = 0
    for stable_id, img, metadata in loaded:
        paste(atlas, img, cursor, 0)
        frames[stable_id] = {
            "frame": {"x": cursor, "y": 0, "w": img.width, "h": img.height},
            "sourceSize": {"w": img.width, "h": img.height},
            "spriteSourceSize": {"x": 0, "y": 0, "w": img.width, "h": img.height},
            "anchor": metadata.get("anchor", {"preset": "center", "x": 0.5, "y": 0.5}),
            "media_role": metadata.get("media_role", "unknown"),
        }
        cursor += img.width
    descriptor = {"frames": frames, "meta": {"format": "RGBA8888", "scale": "1"}}
    return atlas, descriptor


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
