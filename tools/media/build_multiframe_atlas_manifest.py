#!/usr/bin/env python3
"""Build a deterministic multi-frame MediaAtlasManifest from published PNGs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from png_pipeline import PngImage, read_png, transparent_image, write_png


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CREATED_AT = "2026-07-02T00:00:00+08:00"
ANIMATED_ROLES = {"tower_sprite", "unit_sprite", "defense_sprite", "objective_sprite"}
STATIC_ROLES = {"icon", "portrait", "ui_card"}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("_") or "asset"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def animation_state_for_role(role: str) -> str:
    if role in ANIMATED_ROLES or role.endswith("_sprite"):
        return "idle"
    if role in STATIC_ROLES:
        return "static"
    return "default"


def should_animate(role: str, frame_count: int) -> bool:
    return frame_count > 1 and (role in ANIMATED_ROLES or role.endswith("_sprite"))


def anchor_for_item(item: dict[str, Any], role: str) -> dict[str, Any]:
    anchor = item.get("anchor") if isinstance(item.get("anchor"), dict) else {}
    anchor_y_default = 1.0 if role.endswith("_sprite") else 0.5
    anchor_x = float(anchor.get("x", 0.5))
    anchor_y = float(anchor.get("y", anchor_y_default))
    preset = str(anchor.get("preset") or ("bottom_center" if anchor_y >= 0.95 else "center"))
    return {"preset": preset, "x": anchor_x, "y": anchor_y}


def translate(image: PngImage, *, dx: int, dy: int) -> PngImage:
    out = transparent_image(image.width, image.height)
    for y in range(image.height):
        target_y = y + dy
        if target_y < 0 or target_y >= image.height:
            continue
        for x in range(image.width):
            target_x = x + dx
            if target_x < 0 or target_x >= image.width:
                continue
            src = (y * image.width + x) * 4
            dst = (target_y * image.width + target_x) * 4
            out.pixels[dst : dst + 4] = image.pixels[src : src + 4]
    return out


def pulse(image: PngImage, *, amount: int) -> PngImage:
    out = bytearray(image.pixels)
    for index in range(0, len(out), 4):
        if out[index + 3] == 0:
            continue
        out[index] = max(0, min(255, out[index] + amount))
        out[index + 1] = max(0, min(255, out[index + 1] + amount))
        out[index + 2] = max(0, min(255, out[index + 2] + amount))
    return PngImage(image.width, image.height, out)


def frame_offsets(role: str, frame_count: int) -> list[tuple[int, int, int]]:
    if frame_count <= 1:
        return [(0, 0, 0)]
    if role == "unit_sprite":
        base = [(0, 0, 0), (1, -2, 7), (0, -4, 12), (-1, -2, 7)]
    elif role in {"tower_sprite", "defense_sprite", "objective_sprite"} or role.endswith("_sprite"):
        base = [(0, 0, 0), (0, -1, 5), (0, -2, 9), (0, -1, 5)]
    else:
        base = [(0, 0, 0)]
    return [base[index % len(base)] for index in range(frame_count)]


def build_frames(
    *,
    source_path: Path,
    source_url: str,
    source_local_path: str,
    source_sha: str,
    source_width: int,
    source_height: int,
    frames_dir: Path,
    frames_url_prefix: str,
    asset_id: str,
    role: str,
    frame_count: int,
    fps: int,
) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    duration_ms = int(round(1000 / fps)) if frame_count > 1 else 1000
    frames_url_prefix = frames_url_prefix.rstrip("/")
    image: PngImage | None = None
    for index, (dx, dy, amount) in enumerate(frame_offsets(role, frame_count)):
        if index == 0:
            frames.append(
                {
                    "frame_id": f"{asset_id}.{role}.{animation_state_for_role(role)}.frame_{index:03d}",
                    "index": index,
                    "url": source_url,
                    "local_path": source_local_path,
                    "x": 0,
                    "y": 0,
                    "width": source_width,
                    "height": source_height,
                    "duration_ms": duration_ms,
                    "sha256": source_sha or sha256_file(source_path),
                    "anchor": {},
                }
            )
            continue
        if image is None:
            image = read_png(source_path)
        frame_image = pulse(translate(image, dx=dx, dy=dy), amount=amount)
        filename = f"{slug(asset_id)}__{slug(role)}__frame_{index:03d}.png"
        output_path = frames_dir / filename
        write_png(output_path, frame_image)
        frames.append(
            {
                "frame_id": f"{asset_id}.{role}.{animation_state_for_role(role)}.frame_{index:03d}",
                "index": index,
                "url": f"{frames_url_prefix}/{filename}",
                "local_path": rel(output_path),
                "x": 0,
                "y": 0,
                "width": frame_image.width,
                "height": frame_image.height,
                "duration_ms": duration_ms,
                "sha256": sha256_file(output_path),
                "anchor": {},
            }
        )
    return frames


def pack_animation_spritesheet(
    *,
    frames: list[dict[str, Any]],
    output_dir: Path,
    url_prefix: str,
    asset_id: str,
    role: str,
    animation_state: str,
) -> dict[str, Any]:
    loaded: list[tuple[dict[str, Any], PngImage]] = []
    for frame in frames:
        local_path = Path(str(frame.get("local_path") or ""))
        if not local_path.is_absolute():
            local_path = ROOT / local_path
        if not local_path.exists():
            raise FileNotFoundError(f"missing atlas frame for spritesheet: {local_path}")
        loaded.append((frame, read_png(local_path)))

    width = sum(image.width for _, image in loaded)
    height = max((image.height for _, image in loaded), default=1)
    spritesheet = transparent_image(max(width, 1), max(height, 1))
    cursor = 0
    for frame, image in loaded:
        for y in range(image.height):
            for x in range(image.width):
                src = (y * image.width + x) * 4
                dst = (y * spritesheet.width + cursor + x) * 4
                spritesheet.pixels[dst : dst + 4] = image.pixels[src : src + 4]
        frame["x"] = cursor
        frame["y"] = 0
        cursor += image.width

    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{slug(asset_id)}__{slug(role)}__{slug(animation_state)}__spritesheet.png"
    output_path = output_dir / filename
    write_png(output_path, spritesheet)
    return {
        "url": f"{url_prefix.rstrip('/')}/{filename}",
        "local_path": rel(output_path),
        "width": spritesheet.width,
        "height": spritesheet.height,
        "sha256": sha256_file(output_path),
    }


def build_atlas_manifest(
    media_manifest: dict[str, Any],
    *,
    source_manifest_path: str,
    atlas_id: str,
    frames_dir: Path,
    frames_url_prefix: str,
    spritesheet_dir: Path,
    spritesheet_url_prefix: str,
    animated_frame_count: int,
    animated_fps: int,
    loop_continuity_report_ref: str | None = None,
    created_at: str = DEFAULT_CREATED_AT,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    roles: Counter[str] = Counter()
    asset_ids: set[str] = set()
    source_items = media_manifest.get("items")
    if not isinstance(source_items, list):
        source_items = []
    frames_dir.mkdir(parents=True, exist_ok=True)
    for item in source_items:
        if not isinstance(item, dict):
            continue
        asset_id = str(item.get("asset_id") or item.get("source_game_id") or "")
        role = str(item.get("media_role") or "")
        url = str(item.get("url") or "")
        local_path = str(item.get("local_path") or "")
        sha = str(item.get("sha256") or "")
        width = int(item.get("width") or 0)
        height = int(item.get("height") or 0)
        if not asset_id or not role or not url or not local_path or width <= 0 or height <= 0:
            continue
        source_path = Path(local_path)
        if not source_path.is_absolute():
            source_path = ROOT / source_path
        if not source_path.exists():
            raise FileNotFoundError(f"missing source media: {source_path}")
        frame_count = animated_frame_count if should_animate(role, animated_frame_count) else 1
        frames = build_frames(
            source_path=source_path,
            source_url=url,
            source_local_path=local_path,
            source_sha=sha,
            source_width=width,
            source_height=height,
            frames_dir=frames_dir,
            frames_url_prefix=frames_url_prefix,
            asset_id=asset_id,
            role=role,
            frame_count=frame_count,
            fps=animated_fps,
        )
        anchor = anchor_for_item(item, role)
        for frame in frames:
            frame["anchor"] = dict(anchor)
        animation_state = animation_state_for_role(role)
        is_animated = frame_count > 1
        frame_source_kind = "deterministic_frame_sequence" if is_animated else "single_frame_static"
        loop_ref = (
            f"{loop_continuity_report_ref}#{asset_id}.{role}.{animation_state}"
            if loop_continuity_report_ref and is_animated
            else None
        )
        spritesheet = pack_animation_spritesheet(
            frames=frames,
            output_dir=spritesheet_dir,
            url_prefix=spritesheet_url_prefix,
            asset_id=asset_id,
            role=role,
            animation_state=animation_state,
        )
        items.append(
            {
                "animation_id": f"{asset_id}.{role}.{animation_state}",
                "asset_id": asset_id,
                "source_game_id": item.get("source_game_id"),
                "asset_name": item.get("asset_name"),
                "asset_type": item.get("asset_type"),
                "media_role": role,
                "frame_source_kind": frame_source_kind,
                "loop_continuity_ref": loop_ref,
                "playback": {
                    "state": animation_state,
                    "fps": animated_fps if frame_count > 1 else 1,
                    "loop": frame_count > 1,
                    "frame_count": frame_count,
                },
                "spritesheet": spritesheet,
                "frames": frames,
            }
        )
        roles[role] += 1
        asset_ids.add(asset_id)

    return {
        "schema_version": "media_atlas_manifest.v0.1",
        "atlas_id": atlas_id,
        "created_at": created_at,
        "source_manifest": source_manifest_path,
        "source_media_pack_id": str(media_manifest.get("media_pack_id") or media_manifest.get("source_pack_id") or ""),
        "media_layer": "published_media",
        "atlas_mode": "spritesheet",
        "public_url_prefix": str(media_manifest.get("public_url_prefix") or "/assets"),
        "items": items,
        "summary": {
            "animation_count": len(items),
            "frame_count": sum(len(item.get("frames") or []) for item in items),
            "asset_count": len(asset_ids),
            "roles": dict(sorted(roles.items())),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a deterministic multi-frame MediaAtlasManifest v0.1.")
    parser.add_argument("--manifest", required=True, help="Input media manifest path.")
    parser.add_argument("--output", required=True, help="Output atlas manifest path.")
    parser.add_argument("--atlas-id", required=True, help="Atlas manifest id.")
    parser.add_argument("--frames-output-dir", required=True, help="Directory for generated frame PNGs.")
    parser.add_argument("--frames-url-prefix", required=True, help="Public URL prefix for generated frame PNGs.")
    parser.add_argument("--spritesheet-output-dir", help="Directory for generated spritesheet PNGs.")
    parser.add_argument("--spritesheet-url-prefix", help="Public URL prefix for generated spritesheet PNGs.")
    parser.add_argument("--animated-frame-count", type=int, default=4)
    parser.add_argument("--animated-fps", type=int, default=6)
    parser.add_argument("--loop-continuity-report-ref", default="")
    parser.add_argument("--created-at", default=DEFAULT_CREATED_AT)
    args = parser.parse_args()

    if args.animated_frame_count < 1:
        raise SystemExit("--animated-frame-count must be >= 1")
    if args.animated_fps < 1:
        raise SystemExit("--animated-fps must be >= 1")

    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = ROOT / manifest_path
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = ROOT / output_path
    frames_dir = Path(args.frames_output_dir)
    if not frames_dir.is_absolute():
        frames_dir = ROOT / frames_dir
    spritesheet_dir = Path(args.spritesheet_output_dir or args.frames_output_dir)
    if not spritesheet_dir.is_absolute():
        spritesheet_dir = ROOT / spritesheet_dir
    spritesheet_url_prefix = args.spritesheet_url_prefix or args.frames_url_prefix
    source = load_json(manifest_path)
    if not isinstance(source, dict):
        raise SystemExit("input media manifest root must be an object")
    atlas = build_atlas_manifest(
        source,
        source_manifest_path=rel(manifest_path),
        atlas_id=args.atlas_id,
        frames_dir=frames_dir,
        frames_url_prefix=args.frames_url_prefix,
        spritesheet_dir=spritesheet_dir,
        spritesheet_url_prefix=spritesheet_url_prefix,
        animated_frame_count=args.animated_frame_count,
        animated_fps=args.animated_fps,
        loop_continuity_report_ref=args.loop_continuity_report_ref or None,
        created_at=args.created_at,
    )
    write_json(output_path, atlas)
    print(f"OK: wrote {output_path}")
    print(f"- animations: {atlas['summary']['animation_count']}")
    print(f"- frames: {atlas['summary']['frame_count']}")
    print(f"- mode: {atlas['atlas_mode']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
