#!/usr/bin/env python3
"""Generate images for a CompiledAssetCandidate using a live image provider.

Default mode is dry-run and refuses to contact any remote service.
Live mode requires --live so API keys and quotas are not used by accident.

Outputs a raw_media_sequence.v0.1 JSON file compatible with the
mvp_media_processing_publish pipeline chain.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MEDIA_DIR = Path(__file__).resolve().parent

# Ensure content_pipeline is importable for candidate validation.
CONTENT_PIPELINE = ROOT / "tools" / "content_pipeline"
if str(CONTENT_PIPELINE) not in sys.path:
    sys.path.insert(0, str(CONTENT_PIPELINE))

import validate_asset_candidate  # noqa: E402
import asset_media_prompt  # noqa: E402
import image_provider  # noqa: E402

DEFAULT_REGISTRY = ROOT / "shared/module_registry/effect_blocks.v0.1.json"


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate images for a CompiledAssetCandidate using a live image provider."
    )
    parser.add_argument("--candidate", required=True, help="Path to a CompiledAssetCandidate JSON file.")
    parser.add_argument("--output", default=None, help="Path for the output raw_media_sequence JSON.")
    parser.add_argument("--output-dir", default=None, help="Directory to store downloaded images.")
    parser.add_argument(
        "--image-profile",
        default="agnes_image_flash",
        choices=sorted(image_provider.PROFILES),
        help="Image provider profile.",
    )
    parser.add_argument("--size", default=None, help="Image size (e.g. 1024x1024).")
    parser.add_argument("--request-timeout", type=int, default=180, help="Request timeout in seconds.")
    parser.add_argument(
        "--roles",
        default="icon,tower_sprite",
        help="Comma-separated list of media roles to generate.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Actually contact the image provider API. Without this flag, the tool refuses to run.",
    )
    args = parser.parse_args()

    if not args.live:
        print(
            "Refusing to contact image provider without --live. "
            "Pass --live only when you explicitly intend to make a live API call.",
            file=sys.stderr,
        )
        return 2

    candidate_path = Path(args.candidate)
    if not candidate_path.exists():
        print(f"Candidate file not found: {candidate_path}", file=sys.stderr)
        return 1

    candidate = _load_json(candidate_path)
    if not isinstance(candidate, dict):
        print("Candidate must be a JSON object.", file=sys.stderr)
        return 1

    # Validate candidate before generating.
    registry_path = DEFAULT_REGISTRY
    registry = _load_json(registry_path) if registry_path.exists() else {}
    errs = validate_asset_candidate.validate(candidate, registry)
    if errs:
        print("INVALID CompiledAssetCandidate:", file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        return 1

    # Resolve output paths.
    output_dir: Path | None = None
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = Path(tempfile.mkdtemp(prefix="asset_media_"))

    output_path: Path | None = None
    if args.output:
        output_path = Path(args.output)

    roles = [r.strip() for r in args.roles.split(",") if r.strip()]
    profile_name = args.image_profile
    profile = image_provider.PROFILES.get(profile_name)
    if profile is None:
        print(f"Unknown image profile: {profile_name}", file=sys.stderr)
        return 1

    size = args.size or profile.default_size
    width, height = (int(x) for x in size.split("x", 1))

    # Load dotenv (do not print keys).
    image_provider.load_dotenv(ROOT / ".env")

    items: list[dict[str, Any]] = []
    for role in roles:
        if role == "icon":
            prompt = asset_media_prompt.build_icon_prompt(candidate)
        elif role == "tower_sprite":
            prompt = asset_media_prompt.build_tower_sprite_prompt(candidate)
        else:
            print(f"Unknown role: {role!r}, skipping.", file=sys.stderr)
            continue

        prompt_summary = prompt[:120] + "..." if len(prompt) > 120 else prompt

        try:
            response = image_provider.generate_image(profile, prompt, size=size, timeout=args.request_timeout)
        except Exception as exc:
            print(f"Image generation failed for role={role!r}: {exc}", file=sys.stderr)
            return 1

        try:
            image_url = image_provider.extract_image_url(response)
        except RuntimeError as exc:
            print(f"Failed to extract image URL for role={role!r}: {exc}", file=sys.stderr)
            return 1

        # Download image to local path.
        stable_id = f"{candidate.get('id', 'unknown')}_{role}"
        local_filename = f"{stable_id}.png"
        local_path = output_dir / local_filename
        try:
            image_provider.download_image(image_url, local_path, timeout=args.request_timeout)
        except Exception as exc:
            print(f"Failed to download image for role={role!r}: {exc}", file=sys.stderr)
            return 1

        item = asset_media_prompt.build_raw_media_item(
            candidate,
            role,
            provider_profile=profile_name,
            model=profile.model,
            width=width,
            height=height,
            local_path=str(local_path),
            prompt_summary=prompt_summary,
        )
        items.append(item)

    if not items:
        print("No media items were generated.", file=sys.stderr)
        return 1

    sequence = asset_media_prompt.build_raw_media_sequence(candidate, items)

    if output_path:
        _write_json(output_path, sequence)
        print(f"Wrote raw_media_sequence to: {output_path}")
    else:
        # Write to output_dir by default.
        default_output = output_dir / "raw_media_sequence.v0.1.json"
        _write_json(default_output, sequence)
        print(f"Wrote raw_media_sequence to: {default_output}")

    print(f"Generated {len(items)} media item(s) for roles: {roles}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
