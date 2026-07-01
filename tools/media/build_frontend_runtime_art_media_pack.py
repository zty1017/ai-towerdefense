#!/usr/bin/env python3
"""Generate image media for the developer-compiled frontend battle art kit."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MEDIA_DIR = Path(__file__).resolve().parent
if str(MEDIA_DIR) not in sys.path:
    sys.path.insert(0, str(MEDIA_DIR))

import image_provider  # noqa: E402
import runtime_mock_art_prompt  # noqa: E402


DEFAULT_KIT = ROOT / "examples/frontend_mock/frontend_battle_mock_art_kit.v0.1.json"
DEFAULT_OUTPUT_DIR = ROOT / "game_data/media/frontend_runtime_mock/generated"
DEFAULT_MANIFEST = ROOT / "game_data/media/frontend_runtime_mock/frontend_runtime_art_media_manifest.v0.1.json"
PUBLIC_PREFIX = "/assets/frontend_runtime_mock/generated"


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


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG file")
    return struct.unpack(">II", header[16:24])


def generate_with_retries(
    profile: image_provider.ImageProfile,
    prompt: str,
    *,
    size: str,
    output_path: Path,
    timeout: int,
    retries: int,
    retry_delay: float,
) -> None:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = image_provider.generate_image(profile, prompt, size=size, timeout=timeout)
            image_url = image_provider.extract_image_url(response)
            image_provider.download_image(image_url, output_path, timeout=timeout)
            return
        except Exception as exc:  # pragma: no cover - live provider dependent
            last_error = exc
            if attempt >= retries:
                break
            time.sleep(retry_delay * (attempt + 1))
    raise RuntimeError(f"failed after {retries + 1} attempt(s): {last_error}")


def manifest_item(
    *,
    asset: dict[str, Any],
    role: str,
    stable_id: str,
    local_path: Path,
    width: int,
    height: int,
) -> dict[str, Any]:
    return {
        "stable_internal_id": stable_id,
        "asset_id": asset["stable_internal_id"],
        "source_game_id": asset.get("source_game_id"),
        "asset_name": asset.get("display_name"),
        "asset_type": asset.get("asset_kind"),
        "media_role": role,
        "media_layer": "published_media",
        "url": f"{PUBLIC_PREFIX}/{local_path.name}",
        "local_path": local_path.relative_to(ROOT).as_posix(),
        "width": width,
        "height": height,
        "sha256": sha256_file(local_path),
        "fallback_used": False,
        "source_kind": "developer_generated_image",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kit", default=str(DEFAULT_KIT))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--image-profile", default="agnes_image_flash", choices=sorted(image_provider.PROFILES))
    parser.add_argument("--size", default=None)
    parser.add_argument("--dotenv", default=str(ROOT / ".env"))
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--retry-delay", type=float, default=10.0)
    parser.add_argument("--inter-request-delay", type=float, default=1.0)
    parser.add_argument("--request-timeout", type=int, default=240)
    parser.add_argument("--created-at", default="2026-07-01T00:00:00+08:00")
    args = parser.parse_args()

    kit_path = Path(args.kit)
    if not kit_path.is_absolute():
        kit_path = ROOT / kit_path
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = ROOT / manifest_path

    kit = load_json(kit_path)
    assets = kit.get("art_assets")
    if not isinstance(assets, list) or not assets:
        print("art kit must contain art_assets", file=sys.stderr)
        return 1

    profile = image_provider.PROFILES[args.image_profile]
    size = args.size or profile.default_size
    try:
        default_width, default_height = image_provider.parse_size(size)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    image_provider.load_dotenv(Path(args.dotenv))

    items: list[dict[str, Any]] = []
    generated_count = 0
    reused_count = 0
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        asset_id = asset.get("stable_internal_id")
        roles = asset.get("media_roles")
        if not isinstance(asset_id, str) or not asset_id:
            print("art asset missing stable_internal_id", file=sys.stderr)
            return 1
        if not isinstance(roles, list) or not roles:
            print(f"art asset {asset_id} missing media_roles", file=sys.stderr)
            return 1
        unknown = [str(role) for role in roles if role not in runtime_mock_art_prompt.MEDIA_ROLES]
        if unknown:
            print(f"art asset {asset_id} has unknown media roles: {', '.join(unknown)}", file=sys.stderr)
            return 1

        for role in roles:
            role = str(role)
            stable_id = runtime_mock_art_prompt.stable_media_id(asset, role)
            local_path = output_dir / f"{stable_id}.png"
            if local_path.exists() and not args.force:
                try:
                    width, height = png_dimensions(local_path)
                except ValueError:
                    width, height = default_width, default_height
                reused_count += 1
            else:
                if not args.live:
                    print(f"missing media file and --live is not set: {local_path}", file=sys.stderr)
                    return 2
                prompt = runtime_mock_art_prompt.build_prompt(asset, role)
                try:
                    generate_with_retries(
                        profile,
                        prompt,
                        size=size,
                        output_path=local_path,
                        timeout=max(args.request_timeout, 1),
                        retries=max(args.retries, 0),
                        retry_delay=max(args.retry_delay, 0.0),
                    )
                except Exception as exc:
                    print(f"image generation failed for {asset_id}/{role}: {exc}", file=sys.stderr)
                    return 1
                width, height = png_dimensions(local_path)
                generated_count += 1
                if args.inter_request_delay > 0:
                    time.sleep(args.inter_request_delay)

            items.append(
                manifest_item(
                    asset=asset,
                    role=role,
                    stable_id=stable_id,
                    local_path=local_path,
                    width=width,
                    height=height,
                )
            )

    manifest = {
        "schema_version": "frontend_runtime_art_media_manifest.v0.1",
        "media_pack_id": "frontend_runtime_art_media_pack_v0_1",
        "created_at": args.created_at,
        "source_pack_id": kit.get("kit_id"),
        "public_url_prefix": PUBLIC_PREFIX,
        "media_layer": "published_media",
        "items": items,
        "summary": {
            "asset_count": len({item["asset_id"] for item in items}),
            "media_count": len(items),
            "generated_count": generated_count,
            "reused_count": reused_count,
        },
    }
    write_json(manifest_path, manifest)
    print(f"Wrote {manifest_path}")
    print(f"- assets: {manifest['summary']['asset_count']}")
    print(f"- media: {manifest['summary']['media_count']}")
    print(f"- generated: {generated_count}")
    print(f"- reused: {reused_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
