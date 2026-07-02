#!/usr/bin/env python3
"""Generate review-only sprite regeneration candidates from a repair plan.

The tool is live-only by explicit flag. It never replaces frontend manifests or
runtime atlases; generated PNGs are review candidates that must pass quality and
human/vision review before promotion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MEDIA_DIR = Path(__file__).resolve().parent
if str(MEDIA_DIR) not in sys.path:
    sys.path.insert(0, str(MEDIA_DIR))

import image_provider  # noqa: E402
import png_pipeline  # noqa: E402
import runtime_mock_art_prompt  # noqa: E402


MANIFEST_VERSION = "sprite_regeneration_candidate_manifest.v0.1"
DEFAULT_KIT = ROOT / "examples/frontend_mock/frontend_battle_mock_art_kit.v0.1.json"
DEFAULT_CREATED_AT = "2026-07-02T00:00:00+08:00"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_world_readable(path: Path) -> None:
    try:
        path.chmod(0o644)
    except OSError:
        pass


def asset_by_id(kit: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for asset in as_list(kit.get("art_assets")):
        if isinstance(asset, dict) and isinstance(asset.get("stable_internal_id"), str):
            out[str(asset["stable_internal_id"])] = asset
    return out


def anchor_for_role(role: str) -> dict[str, float | str]:
    if role.endswith("_sprite") or role in {"tower_sprite", "unit_sprite", "defense_sprite", "objective_sprite"}:
        return {"preset": "bottom_center", "x": 0.5, "y": 1.0}
    return {"preset": "center", "x": 0.5, "y": 0.5}


def prompt_for_task(asset: dict[str, Any], task: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    role = str(task.get("media_role") or "")
    base = runtime_mock_art_prompt.build_prompt(asset, role)
    constraints = [str(value) for value in as_list(task.get("regeneration_prompt_constraints"))]
    extra = [
        "strict clean cutout source for browser tower-defense gameplay",
        "solid readable silhouette with intentional geometry only",
        "white matte background must be blank and easy to remove",
        "do not include smoke, projectile, explosion, aura, magic circle, or attack effects",
        "do not include enemies, humans, scenery, UI, text, labels, watermark, or logo",
        "keep subject fully visible with generous empty padding",
    ]
    if role == "defense_sprite":
        extra.extend(
            [
                "main subject is one portable sawhorse roadblock, a compact X-frame deployable obstacle",
                "one single straight obstacle segment for a tower-defense build slot",
                "waist-high roadblock shape with crossed supports, two short lantern posts, and solid planks",
                "not a fence, not a railing, not a gate, not a corral, not a closed square pen, not an enclosure",
                "no floor tile, no platform slab, no base plate, no scenery under the barricade",
                "no floating glow orbs, no particle sparks, no magic effects, no attack effects",
                "compact solid silhouette with very few interior openings",
                "avoid large interior holes and avoid white gaps between object parts",
            ]
        )
    if role == "objective_sprite":
        extra.extend(
            [
                "fragile objective prop with compact tripod or base",
                "avoid huge hollow white regions inside the subject",
                "glass highlights are allowed but should be painted as part of the object",
            ]
        )
    prompt = ", ".join([base, *constraints, *extra])
    summary = {
        "role": role,
        "asset_id": asset.get("stable_internal_id"),
        "asset_kind": asset.get("asset_kind"),
        "constraint_count": len(constraints) + len(extra),
        "repair_action": task.get("recommended_action"),
        "source_warnings": as_list(task.get("warnings")),
    }
    return prompt, summary


def postprocess_raw_sprite(
    raw_path: Path,
    output_path: Path,
    *,
    role: str,
    matte_threshold: int,
    alpha_threshold: int,
    padding: int,
    min_size: int,
    keep_largest_component: bool,
) -> tuple[int, int]:
    image = png_pipeline.read_png(raw_path)
    processed = png_pipeline.remove_edge_matte_background(
        image,
        threshold=matte_threshold,
    )
    processed = png_pipeline.remove_small_alpha_components(
        processed,
        alpha_threshold=alpha_threshold,
        min_pixels=96,
    )
    if keep_largest_component:
        processed = png_pipeline.keep_largest_alpha_component(
            processed,
            alpha_threshold=alpha_threshold,
        )
    processed = png_pipeline.crop_and_pad(
        processed,
        padding=padding,
        alpha_threshold=alpha_threshold,
    )
    processed = png_pipeline.normalize_canvas(
        processed,
        square=True,
        min_size=min_size,
        align="bottom_center" if role.endswith("_sprite") else "center",
        bottom_padding=padding if role.endswith("_sprite") else 0,
    )
    processed = png_pipeline.clear_transparent_rgb(
        processed,
        alpha_threshold=alpha_threshold,
    )
    png_pipeline.write_png(output_path, processed)
    make_world_readable(output_path)
    return processed.width, processed.height


def selected_tasks(
    plan: dict[str, Any],
    priorities: set[str],
    limit: int | None,
    asset_ids: set[str],
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for task in as_list(plan.get("tasks")):
        if not isinstance(task, dict):
            continue
        if priorities and str(task.get("priority")) not in priorities:
            continue
        if asset_ids and str(task.get("asset_id")) not in asset_ids:
            continue
        tasks.append(task)
        if limit is not None and len(tasks) >= limit:
            break
    return tasks


def item_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(item.get("source_task_id") or ""),
        str(item.get("asset_id") or ""),
        str(item.get("media_role") or ""),
    )


def merge_existing_items(existing_manifest: dict[str, Any], new_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing_items = [item for item in as_list(existing_manifest.get("items")) if isinstance(item, dict)]
    by_key = {item_key(item): item for item in existing_items}
    for item in new_items:
        by_key[item_key(item)] = item

    ordered: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in existing_items:
        key = item_key(item)
        if key in by_key and key not in seen:
            ordered.append(by_key[key])
            seen.add(key)
    for item in new_items:
        key = item_key(item)
        if key not in seen:
            ordered.append(item)
            seen.add(key)
    return ordered


def safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in value).strip("_") or "asset"


def generate_candidate(
    *,
    profile: image_provider.ImageProfile,
    task: dict[str, Any],
    asset: dict[str, Any],
    raw_dir: Path,
    processed_dir: Path,
    size: str,
    timeout: int,
    retries: int,
    retry_delay: float,
    reuse_raw_if_exists: bool,
    matte_threshold: int,
    alpha_threshold: int,
    padding: int,
    min_size: int,
    keep_largest_component: bool,
    live: bool,
) -> dict[str, Any]:
    role = str(task.get("media_role") or "")
    asset_id = str(task.get("asset_id") or asset.get("stable_internal_id") or "asset")
    prompt, prompt_summary = prompt_for_task(asset, task)
    filename_stem = f"{safe_name(asset_id)}__{safe_name(role)}__regenerated"
    raw_path = raw_dir / f"{filename_stem}.png"
    processed_path = processed_dir / f"{filename_stem}.processed.png"

    if not live:
        return {
            "candidate_id": f"{task.get('task_id')}.regenerated",
            "source_task_id": task.get("task_id"),
            "asset_id": asset_id,
            "asset_name": task.get("asset_name") or asset.get("display_name"),
            "asset_type": task.get("asset_type") or asset.get("asset_kind"),
            "media_role": role,
            "priority": task.get("priority"),
            "status": "planned_not_generated",
            "provider_profile": profile.name,
            "model": profile.model,
            "prompt_summary": prompt_summary,
            "review_policy": "review_only_not_runtime",
        }

    reused_raw = reuse_raw_if_exists and raw_path.exists()
    if not reused_raw:
        last_error: Exception | None = None
        for attempt in range(max(0, retries) + 1):
            try:
                response = image_provider.generate_image(profile, prompt, size=size, timeout=timeout)
                image_url = image_provider.extract_image_url(response)
                image_provider.download_image(image_url, raw_path, timeout=timeout)
                make_world_readable(raw_path)
                break
            except Exception as exc:  # pragma: no cover - live provider dependent
                last_error = exc
                if attempt >= retries:
                    raise RuntimeError(f"failed to generate {asset_id}/{role}: {last_error}") from exc
                time.sleep(max(0.0, retry_delay) * (attempt + 1))
    if raw_path.exists():
        make_world_readable(raw_path)

    width, height = postprocess_raw_sprite(
        raw_path,
        processed_path,
        role=role,
        matte_threshold=matte_threshold,
        alpha_threshold=alpha_threshold,
        padding=padding,
        min_size=min_size,
        keep_largest_component=keep_largest_component,
    )
    return {
        "candidate_id": f"{task.get('task_id')}.regenerated",
        "source_task_id": task.get("task_id"),
        "asset_id": asset_id,
        "asset_name": task.get("asset_name") or asset.get("display_name"),
        "asset_type": task.get("asset_type") or asset.get("asset_kind"),
        "media_role": role,
        "priority": task.get("priority"),
        "status": "generated_review_candidate",
        "provider_profile": profile.name,
        "model": profile.model,
        "prompt_summary": prompt_summary,
        "raw_local_path": rel(raw_path),
        "local_path": rel(processed_path),
        "width": width,
        "height": height,
        "sha256": sha256_file(processed_path),
        "anchor": anchor_for_role(role),
        "generation_source": "existing_raw_reprocessed" if reused_raw else "provider_generated",
        "source_repair_action": task.get("recommended_action"),
        "source_warnings": as_list(task.get("warnings")),
        "review_policy": "review_only_not_runtime",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate review-only sprite regeneration candidates.")
    parser.add_argument("--repair-plan", required=True)
    parser.add_argument("--kit", default=str(DEFAULT_KIT))
    parser.add_argument("--output-manifest", required=True)
    parser.add_argument("--raw-output-dir", required=True)
    parser.add_argument("--processed-output-dir", required=True)
    parser.add_argument("--candidate-pack-id", required=True)
    parser.add_argument("--priority", action="append", default=["P1"])
    parser.add_argument("--asset-id", action="append", default=[])
    parser.add_argument("--limit", type=int)
    parser.add_argument("--merge-existing", action="store_true")
    parser.add_argument("--image-profile", default="agnes_image_flash", choices=sorted(image_provider.PROFILES))
    parser.add_argument("--size", default=None)
    parser.add_argument("--dotenv", default=str(ROOT / ".env"))
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--request-timeout", type=int, default=240)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--retry-delay", type=float, default=8.0)
    parser.add_argument("--inter-request-delay", type=float, default=1.0)
    parser.add_argument("--reuse-raw-if-exists", action="store_true")
    parser.add_argument("--keep-detached-components", action="store_true")
    parser.add_argument("--matte-threshold", type=int, default=24)
    parser.add_argument("--alpha-threshold", type=int, default=8)
    parser.add_argument("--padding", type=int, default=40)
    parser.add_argument("--min-size", type=int, default=512)
    parser.add_argument("--created-at", default=DEFAULT_CREATED_AT)
    args = parser.parse_args()

    plan_path = Path(args.repair_plan)
    if not plan_path.is_absolute():
        plan_path = ROOT / plan_path
    kit_path = Path(args.kit)
    if not kit_path.is_absolute():
        kit_path = ROOT / kit_path
    output_manifest = Path(args.output_manifest)
    if not output_manifest.is_absolute():
        output_manifest = ROOT / output_manifest
    raw_dir = Path(args.raw_output_dir)
    if not raw_dir.is_absolute():
        raw_dir = ROOT / raw_dir
    processed_dir = Path(args.processed_output_dir)
    if not processed_dir.is_absolute():
        processed_dir = ROOT / processed_dir

    plan = load_json(plan_path)
    kit = load_json(kit_path)
    if not isinstance(plan, dict):
        print("repair plan root must be object", file=sys.stderr)
        return 1
    if not isinstance(kit, dict):
        print("kit root must be object", file=sys.stderr)
        return 1

    profile = image_provider.PROFILES[args.image_profile]
    size = args.size or profile.default_size
    image_provider.parse_size(size)
    if args.live:
        image_provider.load_dotenv(Path(args.dotenv))

    assets = asset_by_id(kit)
    tasks = selected_tasks(plan, set(args.priority), args.limit, set(args.asset_id))
    items: list[dict[str, Any]] = []
    for index, task in enumerate(tasks):
        asset_id = str(task.get("asset_id") or "")
        asset = assets.get(asset_id)
        if not asset:
            raise SystemExit(f"repair task references unknown art asset: {asset_id}")
        role = str(task.get("media_role") or "")
        if role not in as_list(asset.get("media_roles")):
            raise SystemExit(f"asset {asset_id} does not declare media_role {role}")
        item = generate_candidate(
            profile=profile,
            task=task,
            asset=asset,
            raw_dir=raw_dir,
            processed_dir=processed_dir,
            size=size,
            timeout=max(1, args.request_timeout),
            retries=max(0, args.retries),
            retry_delay=max(0.0, args.retry_delay),
            reuse_raw_if_exists=args.reuse_raw_if_exists,
            matte_threshold=max(0, args.matte_threshold),
            alpha_threshold=max(0, args.alpha_threshold),
            padding=max(0, args.padding),
            min_size=max(1, args.min_size),
            keep_largest_component=not args.keep_detached_components,
            live=args.live,
        )
        items.append(item)
        if args.live and args.inter_request_delay > 0 and index + 1 < len(tasks):
            time.sleep(args.inter_request_delay)

    if args.merge_existing and output_manifest.exists():
        existing = load_json(output_manifest)
        if not isinstance(existing, dict):
            print("existing manifest root must be object", file=sys.stderr)
            return 1
        items = merge_existing_items(existing, items)

    generated_count = sum(1 for item in items if item.get("status") == "generated_review_candidate")
    manifest = {
        "schema_version": MANIFEST_VERSION,
        "candidate_pack_id": args.candidate_pack_id,
        "created_at": args.created_at,
        "source_repair_plan": rel(plan_path),
        "source_kit": rel(kit_path),
        "media_layer": "review_candidate_media",
        "generation_mode": "live" if args.live else "planned_dry_run",
        "promotion_policy": "Regenerated candidates must pass cutout quality and human/vision review before replacing runtime media.",
        "items": items,
        "summary": {
            "candidate_count": len(items),
            "generated_count": generated_count,
            "planned_count": len(items) - generated_count,
            "asset_count": len({item.get("asset_id") for item in items}),
            "profile": profile.name,
            "model": profile.model,
            "size": size,
        },
        "notes": [
            "This manifest is review-only.",
            "It does not contain API keys or provider raw responses.",
            "The full prompts are intentionally not stored; prompt_summary contains only bounded metadata.",
        ],
    }
    write_json(output_manifest, manifest)
    print(f"OK: wrote {output_manifest}")
    print(f"- mode: {manifest['generation_mode']}")
    print(f"- candidates: {manifest['summary']['candidate_count']}")
    print(f"- generated: {generated_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
