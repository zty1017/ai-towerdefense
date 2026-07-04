#!/usr/bin/env python3
"""Generate and publish image files for the frontend mock content pack.

The output is a frontend-safe media manifest. It intentionally does not store
provider names, model names, full prompts, temporary provider URLs, or API keys.
"""

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
CONTENT_PIPELINE = ROOT / "tools" / "content_pipeline"

for path in (MEDIA_DIR, CONTENT_PIPELINE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import asset_media_prompt  # noqa: E402
import image_provider  # noqa: E402
import validate_asset_candidate  # noqa: E402


DEFAULT_PACK = ROOT / "examples/frontend_mock/frontend_mock_pack.v0.1.json"
DEFAULT_OUTPUT_DIR = ROOT / "game_data/media/frontend_mock/generated"
DEFAULT_MANIFEST = ROOT / "game_data/media/frontend_mock/frontend_media_manifest.v0.1.json"
DEFAULT_REGISTRY = ROOT / "shared/module_registry/effect_blocks.v0.1.json"
PUBLIC_PREFIX = "/assets/frontend_mock/generated"


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
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG file")
    return struct.unpack(">II", header[16:24])


def load_candidates() -> dict[str, dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    for path in sorted((ROOT / "examples/compiled_assets").glob("*.compiled_asset.json")):
        data = load_json(path)
        if isinstance(data, dict) and isinstance(data.get("id"), str):
            candidates[data["id"]] = data
    return candidates


def roles_for_asset(candidate: dict[str, Any], roles_arg: str) -> list[str]:
    if roles_arg.strip().lower() == "auto":
        return asset_media_prompt.default_media_roles(candidate)
    roles = [role.strip() for role in roles_arg.split(",") if role.strip()]
    unknown = [role for role in roles if role not in asset_media_prompt.MEDIA_ROLES]
    if unknown:
        raise ValueError(f"unknown media roles: {', '.join(unknown)}")
    return roles


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
    asset_id: str,
    asset_name: str,
    asset_type: str,
    role: str,
    stable_id: str,
    local_path: Path,
    output_dir: Path,
    width: int,
    height: int,
) -> dict[str, Any]:
    relative_path = local_path.relative_to(ROOT).as_posix()
    public_url = f"{PUBLIC_PREFIX}/{local_path.name}"
    return {
        "stable_internal_id": stable_id,
        "asset_id": asset_id,
        "asset_name": asset_name,
        "asset_type": asset_type,
        "media_role": role,
        "media_layer": "published_media",
        "url": public_url,
        "local_path": relative_path,
        "width": width,
        "height": height,
        "sha256": sha256_file(local_path),
        "fallback_used": False,
        "source_kind": "generated_image",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", default=str(DEFAULT_PACK))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--image-profile", default="agnes_image_flash", choices=sorted(image_provider.PROFILES))
    parser.add_argument("--size", default=None)
    parser.add_argument("--roles", default="auto")
    parser.add_argument("--dotenv", default=str(ROOT / ".env"))
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--force-roles",
        default="",
        help="Comma-separated role names to regenerate even if files already exist.",
    )
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--retry-delay", type=float, default=15.0)
    parser.add_argument("--inter-request-delay", type=float, default=3.5)
    parser.add_argument("--request-timeout", type=int, default=180)
    parser.add_argument("--created-at", default="2026-07-01T00:00:00+08:00")
    args = parser.parse_args()

    pack_path = Path(args.pack)
    output_dir = Path(args.output_dir)
    manifest_path = Path(args.manifest)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    if not manifest_path.is_absolute():
        manifest_path = ROOT / manifest_path

    pack = load_json(pack_path)
    if not isinstance(pack, dict):
        print("frontend mock pack root must be object", file=sys.stderr)
        return 1
    assets = pack.get("assets")
    if not isinstance(assets, list) or not assets:
        print("frontend mock pack must contain assets", file=sys.stderr)
        return 1

    registry = load_json(DEFAULT_REGISTRY)
    candidates = load_candidates()
    profile = image_provider.PROFILES[args.image_profile]
    size = args.size or profile.default_size
    try:
        default_width, default_height = image_provider.parse_size(size)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    image_provider.load_dotenv(Path(args.dotenv))
    force_roles = {role.strip() for role in args.force_roles.split(",") if role.strip()}
    unknown_force_roles = sorted(force_roles - asset_media_prompt.MEDIA_ROLES)
    if unknown_force_roles:
        print(f"unknown --force-roles value(s): {', '.join(unknown_force_roles)}", file=sys.stderr)
        return 1

    items: list[dict[str, Any]] = []
    generated_count = 0
    reused_count = 0
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        asset_id = str(asset.get("stable_internal_id", ""))
        candidate = candidates.get(asset_id)
        if not candidate:
            print(f"missing compiled asset for frontend asset id: {asset_id}", file=sys.stderr)
            return 1
        errors = validate_asset_candidate.validate(candidate, registry)
        if errors:
            print(f"invalid compiled asset {asset_id}:", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
            return 1

        presentation = candidate.get("presentation") if isinstance(candidate.get("presentation"), dict) else {}
        gameplay = candidate.get("gameplay") if isinstance(candidate.get("gameplay"), dict) else {}
        asset_name = str(presentation.get("name", asset_id))
        asset_type = str(gameplay.get("asset_type", "unknown"))
        try:
            roles = roles_for_asset(candidate, args.roles)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        for role in roles:
            stable_id = asset_media_prompt.stable_media_id(candidate, role)
            local_path = output_dir / f"{stable_id}.png"
            should_force = args.force or role in force_roles
            if local_path.exists() and not should_force:
                try:
                    width, height = png_dimensions(local_path)
                except ValueError:
                    width, height = default_width, default_height
                reused_count += 1
            else:
                if not args.live:
                    print(
                        f"missing media file and --live is not set: {local_path}",
                        file=sys.stderr,
                    )
                    return 2
                prompt = asset_media_prompt.build_prompt_for_role(candidate, role)
                try:
                    generate_with_retries(
                        profile,
                        prompt,
                        size=size,
                        output_path=local_path,
                        timeout=args.request_timeout,
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
                    asset_id=asset_id,
                    asset_name=asset_name,
                    asset_type=asset_type,
                    role=role,
                    stable_id=stable_id,
                    local_path=local_path,
                    output_dir=output_dir,
                    width=width,
                    height=height,
                )
            )

    manifest = {
        "schema_version": "frontend_media_manifest.v0.1",
        "media_pack_id": "frontend_mock_media_pack_v0_1",
        "created_at": args.created_at,
        "source_pack_id": pack.get("pack_id"),
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
