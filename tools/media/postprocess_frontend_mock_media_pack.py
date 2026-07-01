#!/usr/bin/env python3
"""Post-process frontend mock media into runtime-friendly PNG cutouts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MEDIA_DIR = Path(__file__).resolve().parent
if str(MEDIA_DIR) not in sys.path:
    sys.path.insert(0, str(MEDIA_DIR))

import png_pipeline  # noqa: E402


DEFAULT_MANIFEST = ROOT / "game_data/media/frontend_mock/frontend_media_manifest.v0.1.json"
DEFAULT_RAW_COPY_MANIFEST = ROOT / "game_data/media/frontend_mock/frontend_raw_media_manifest.v0.1.json"
DEFAULT_SEED_MANIFEST = ROOT / "game_data/media/frontend_mock/frontend_animation_seed_manifest.v0.1.json"
DEFAULT_OUTPUT_DIR = ROOT / "game_data/media/frontend_mock/processed"
PUBLIC_PREFIX = "/assets/frontend_mock/processed"
SEED_PUBLIC_PREFIX = "/assets/frontend_mock/generated"
BOTTOM_CENTER_ROLES = {
    "tower_sprite",
    "unit_sprite",
    "enemy_sprite",
    "monster_sprite",
    "objective_sprite",
    "defense_sprite",
    "npc_sprite",
}
CENTER_ROLES = {"icon", "ui_card", "portrait"}


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


def role_anchor(role: str) -> dict[str, float | str]:
    if role in BOTTOM_CENTER_ROLES:
        return {"preset": "bottom_center", "x": 0.5, "y": 1.0}
    return {"preset": "center", "x": 0.5, "y": 0.5}


def process_png(
    source_path: Path,
    output_path: Path,
    *,
    role: str,
    matte_threshold: int,
    alpha_threshold: int,
    padding: int,
    min_size: int,
) -> tuple[int, int]:
    image = png_pipeline.read_png(source_path)
    processed = png_pipeline.remove_edge_matte_background(image, threshold=matte_threshold)
    if role in BOTTOM_CENTER_ROLES:
        processed = png_pipeline.remove_near_white_background_islands(
            processed,
            alpha_threshold=alpha_threshold,
            min_luma=246,
            max_chroma=10,
            min_pixels=48,
        )
    processed = png_pipeline.remove_small_alpha_components(
        processed,
        alpha_threshold=alpha_threshold,
        min_pixels=96,
    )
    processed = png_pipeline.crop_and_pad(processed, padding=padding, alpha_threshold=alpha_threshold)
    processed = png_pipeline.normalize_canvas(
        processed,
        square=True,
        min_size=min_size,
        align="bottom_center" if role in BOTTOM_CENTER_ROLES else "center",
        bottom_padding=padding if role in BOTTOM_CENTER_ROLES else 0,
    )
    processed = png_pipeline.clear_transparent_rgb(processed, alpha_threshold=alpha_threshold)
    png_pipeline.write_png(output_path, processed)
    return processed.width, processed.height


def seed_manifest_from_raw(
    manifest: dict[str, Any],
    *,
    created_from: Path,
    public_prefix: str,
) -> dict[str, Any]:
    items = []
    for item in manifest.get("items", []):
        if not isinstance(item, dict):
            continue
        seed_item = {
            key: value
            for key, value in item.items()
            if key
            in {
                "stable_internal_id",
                "asset_id",
                "asset_name",
                "asset_type",
                "media_role",
                "url",
                "local_path",
                "width",
                "height",
                "sha256",
                "source_kind",
            }
        }
        local_path = seed_item.get("local_path")
        if isinstance(local_path, str):
            seed_item["url"] = f"{public_prefix.rstrip('/')}/{Path(local_path).name}"
        seed_item["seed_kind"] = "image_to_video_or_animation_card"
        items.append(seed_item)
    source_media_pack_id = str(manifest.get("media_pack_id", "frontend_media_pack_v0_1"))
    return {
        "schema_version": "frontend_animation_seed_manifest.v0.1",
        "media_pack_id": f"{source_media_pack_id}_animation_seed",
        "created_from": created_from.relative_to(ROOT).as_posix()
        if created_from.is_relative_to(ROOT)
        else str(created_from),
        "source_pack_id": manifest.get("source_pack_id"),
        "public_url_prefix": public_prefix.rstrip("/"),
        "media_layer": "published_media",
        "usage_policy": "Animation seeds may contain expressive glow or ornament and are not the default runtime sprite source.",
        "items": items,
        "summary": {
            "asset_count": len({item.get("asset_id") for item in items}),
            "media_count": len(items),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument(
        "--output-manifest",
        default=None,
        help="Write processed manifest to this path. Defaults to replacing --manifest.",
    )
    parser.add_argument("--raw-copy-manifest", default=str(DEFAULT_RAW_COPY_MANIFEST))
    parser.add_argument("--seed-manifest", default=str(DEFAULT_SEED_MANIFEST))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--public-prefix", default=PUBLIC_PREFIX)
    parser.add_argument("--seed-public-prefix", default=SEED_PUBLIC_PREFIX)
    parser.add_argument("--matte-threshold", type=int, default=24)
    parser.add_argument("--alpha-threshold", type=int, default=8)
    parser.add_argument("--padding", type=int, default=36)
    parser.add_argument("--min-size", type=int, default=512)
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = ROOT / manifest_path
    output_manifest_path = Path(args.output_manifest) if args.output_manifest else manifest_path
    if not output_manifest_path.is_absolute():
        output_manifest_path = ROOT / output_manifest_path
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    raw_copy_manifest_path = Path(args.raw_copy_manifest)
    if not raw_copy_manifest_path.is_absolute():
        raw_copy_manifest_path = ROOT / raw_copy_manifest_path
    seed_manifest_path = Path(args.seed_manifest)
    if not seed_manifest_path.is_absolute():
        seed_manifest_path = ROOT / seed_manifest_path

    manifest = load_json(manifest_path)
    if not isinstance(manifest, dict):
        print("frontend media manifest root must be object", file=sys.stderr)
        return 1
    items = manifest.get("items")
    if not isinstance(items, list) or not items:
        print("frontend media manifest must contain items", file=sys.stderr)
        return 1
    non_raw_items = [
        str(item.get("local_path", ""))
        for item in items
        if isinstance(item, dict) and "/generated/" not in str(item.get("local_path", ""))
    ]
    if non_raw_items:
        print(
            "postprocess input must reference generated raw media files; "
            "run build_frontend_mock_media_pack.py first",
            file=sys.stderr,
        )
        for path in non_raw_items[:5]:
            print(f"- non-raw media path: {path}", file=sys.stderr)
        return 1

    write_json(raw_copy_manifest_path, manifest)
    write_json(
        seed_manifest_path,
        seed_manifest_from_raw(
            manifest,
            created_from=manifest_path,
            public_prefix=args.seed_public_prefix,
        ),
    )

    processed_items: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            print(f"items[{index}] must be object", file=sys.stderr)
            return 1
        local_path = item.get("local_path")
        stable_id = item.get("stable_internal_id")
        role = str(item.get("media_role", ""))
        if not isinstance(local_path, str) or not local_path:
            print(f"items[{index}].local_path must be string", file=sys.stderr)
            return 1
        if not isinstance(stable_id, str) or not stable_id:
            print(f"items[{index}].stable_internal_id must be string", file=sys.stderr)
            return 1

        source_path = Path(local_path)
        if not source_path.is_absolute():
            source_path = ROOT / source_path
        if not source_path.exists():
            print(f"source file missing: {source_path}", file=sys.stderr)
            return 1

        output_path = output_dir / f"{stable_id}.png"
        width, height = process_png(
            source_path,
            output_path,
            role=role,
            matte_threshold=max(args.matte_threshold, 0),
            alpha_threshold=max(args.alpha_threshold, 0),
            padding=max(args.padding, 0),
            min_size=max(args.min_size, 1),
        )

        new_item = dict(item)
        new_item["url"] = f"{args.public_prefix.rstrip('/')}/{output_path.name}"
        new_item["local_path"] = output_path.relative_to(ROOT).as_posix()
        new_item["width"] = width
        new_item["height"] = height
        new_item["sha256"] = sha256_file(output_path)
        new_item["anchor"] = role_anchor(role)
        new_item["source_kind"] = "processed_generated_image"
        processed_items.append(new_item)

    manifest["public_url_prefix"] = args.public_prefix.rstrip("/")
    manifest["items"] = processed_items
    summary = manifest.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    summary["media_count"] = len(processed_items)
    summary["processed_count"] = len(processed_items)
    manifest["summary"] = summary
    write_json(output_manifest_path, manifest)

    print(f"Wrote {output_manifest_path}")
    print(f"- processed media: {len(processed_items)}")
    print(f"- output dir: {output_dir}")
    print(f"- raw copy manifest: {raw_copy_manifest_path}")
    print(f"- animation seed manifest: {seed_manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
