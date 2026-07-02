#!/usr/bin/env python3
"""Promote reviewed sprite regeneration candidates into a runtime media manifest.

This is an explicit promotion gate. It does not call providers and does not use
raw prompts. By default it only writes a report; `--apply` is required before it
copies PNGs and rewrites the runtime manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MEDIA_DIR = Path(__file__).resolve().parent
if str(MEDIA_DIR) not in sys.path:
    sys.path.insert(0, str(MEDIA_DIR))

import png_pipeline  # noqa: E402


REPORT_VERSION = "sprite_regeneration_promotion_report.v0.1"
DEFAULT_PROMOTED_AT = "2026-07-02T00:00:00+08:00"


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


def resolve(path_value: str | Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else ROOT / path


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


def item_key(item: dict[str, Any]) -> tuple[str, str]:
    return str(item.get("asset_id") or ""), str(item.get("media_role") or "")


def quality_status_by_key(report: dict[str, Any]) -> dict[tuple[str, str], str]:
    statuses: dict[tuple[str, str], str] = {}
    for item in as_list(report.get("items")):
        if isinstance(item, dict):
            statuses[item_key(item)] = str(item.get("status") or "")
    return statuses


def runtime_items_by_key(manifest: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    items: dict[tuple[str, str], dict[str, Any]] = {}
    for item in as_list(manifest.get("items")):
        if isinstance(item, dict):
            key = item_key(item)
            if key[0] and key[1]:
                items[key] = item
    return items


def selected_candidates(
    candidate_manifest: dict[str, Any],
    quality_report: dict[str, Any],
    asset_ids: set[str],
    media_roles: set[str],
) -> list[dict[str, Any]]:
    statuses = quality_status_by_key(quality_report)
    selected: list[dict[str, Any]] = []
    for item in as_list(candidate_manifest.get("items")):
        if not isinstance(item, dict):
            continue
        key = item_key(item)
        if asset_ids and key[0] not in asset_ids:
            continue
        if media_roles and key[1] not in media_roles:
            continue
        if item.get("status") != "generated_review_candidate":
            continue
        if statuses.get(key) != "passed":
            continue
        selected.append(item)
    return selected


def make_world_readable(path: Path) -> None:
    try:
        path.chmod(0o644)
    except OSError:
        pass


def promote_candidate(
    candidate: dict[str, Any],
    target_item: dict[str, Any],
    *,
    candidate_manifest: dict[str, Any],
    candidate_manifest_path: Path,
    quality_report_path: Path,
    apply: bool,
    promoted_at: str,
) -> dict[str, Any]:
    source_path = resolve(str(candidate.get("local_path") or ""))
    target_path = resolve(str(target_item.get("local_path") or ""))
    if not source_path.exists():
        raise FileNotFoundError(f"candidate source missing: {source_path}")
    if not target_path.exists():
        raise FileNotFoundError(f"runtime target missing: {target_path}")

    old_sha = str(target_item.get("sha256") or "")
    old_width = target_item.get("width")
    old_height = target_item.get("height")
    candidate_sha = sha256_file(source_path)

    if apply:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, target_path)
        make_world_readable(target_path)

    promoted_image = png_pipeline.read_png(target_path if apply else source_path)
    new_sha = sha256_file(target_path if apply else source_path)

    if apply:
        target_item["width"] = promoted_image.width
        target_item["height"] = promoted_image.height
        target_item["sha256"] = new_sha
        target_item["fallback_used"] = False
        target_item["source_kind"] = "promoted_sprite_regeneration_candidate"
        target_item["promotion"] = {
            "state": "promoted_from_review_candidate",
            "promoted_at": promoted_at,
            "candidate_pack_id": candidate_manifest.get("candidate_pack_id"),
            "candidate_id": candidate.get("candidate_id"),
            "source_task_id": candidate.get("source_task_id"),
            "candidate_manifest": rel(candidate_manifest_path),
            "quality_report": rel(quality_report_path),
        }

    return {
        "asset_id": candidate.get("asset_id"),
        "asset_name": candidate.get("asset_name"),
        "media_role": candidate.get("media_role"),
        "candidate_id": candidate.get("candidate_id"),
        "source_task_id": candidate.get("source_task_id"),
        "source_candidate_path": rel(source_path),
        "runtime_target_path": rel(target_path),
        "applied": apply,
        "old_sha256": old_sha,
        "old_width": old_width,
        "old_height": old_height,
        "candidate_sha256": candidate_sha,
        "new_sha256": new_sha,
        "new_width": promoted_image.width,
        "new_height": promoted_image.height,
    }


def build_report(
    *,
    candidate_manifest: dict[str, Any],
    candidate_manifest_path: Path,
    quality_report: dict[str, Any],
    quality_report_path: Path,
    runtime_manifest_path: Path,
    selected: list[dict[str, Any]],
    promoted_items: list[dict[str, Any]],
    apply: bool,
    promoted_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": REPORT_VERSION,
        "report_id": "frontend_runtime_sprite_regeneration_promotion_v0_1",
        "created_at": promoted_at,
        "mode": "applied" if apply else "dry_run",
        "source_candidate_manifest": rel(candidate_manifest_path),
        "source_candidate_pack_id": candidate_manifest.get("candidate_pack_id"),
        "source_quality_report": rel(quality_report_path),
        "source_quality_status": quality_report.get("status"),
        "runtime_manifest": rel(runtime_manifest_path),
        "selected_candidate_count": len(selected),
        "promoted_count": len(promoted_items) if apply else 0,
        "would_promote_count": len(promoted_items),
        "items": promoted_items,
        "runtime_effect": {
            "manifest_rewritten": apply,
            "runtime_png_replaced": apply,
            "atlas_rebuild_required": bool(promoted_items),
        },
        "notes": [
            "This report contains bounded promotion metadata only.",
            "It does not include provider responses, full prompts, API keys, or raw traces.",
            "Promotion is explicit and review-gated; candidates are never promoted automatically.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote reviewed sprite regeneration candidates.")
    parser.add_argument("--candidate-manifest", required=True)
    parser.add_argument("--candidate-quality-report", required=True)
    parser.add_argument("--runtime-manifest", required=True)
    parser.add_argument("--output-manifest", required=True)
    parser.add_argument("--promotion-report", required=True)
    parser.add_argument("--asset-id", action="append", default=[])
    parser.add_argument("--media-role", action="append", default=[])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--promoted-at", default=DEFAULT_PROMOTED_AT)
    args = parser.parse_args()

    candidate_manifest_path = resolve(args.candidate_manifest)
    quality_report_path = resolve(args.candidate_quality_report)
    runtime_manifest_path = resolve(args.runtime_manifest)
    output_manifest_path = resolve(args.output_manifest)
    promotion_report_path = resolve(args.promotion_report)

    candidate_manifest = load_json(candidate_manifest_path)
    quality_report = load_json(quality_report_path)
    runtime_manifest = load_json(runtime_manifest_path)
    if not isinstance(candidate_manifest, dict):
        print("candidate manifest root must be object", file=sys.stderr)
        return 1
    if not isinstance(quality_report, dict):
        print("quality report root must be object", file=sys.stderr)
        return 1
    if not isinstance(runtime_manifest, dict):
        print("runtime manifest root must be object", file=sys.stderr)
        return 1
    if candidate_manifest.get("media_layer") != "review_candidate_media":
        print("candidate manifest must be review_candidate_media", file=sys.stderr)
        return 1
    if quality_report.get("status") != "passed":
        print("candidate quality report must be passed", file=sys.stderr)
        return 1

    selected = selected_candidates(
        candidate_manifest,
        quality_report,
        set(args.asset_id),
        set(args.media_role),
    )
    runtime_by_key = runtime_items_by_key(runtime_manifest)
    promoted_items: list[dict[str, Any]] = []
    for candidate in selected:
        key = item_key(candidate)
        target_item = runtime_by_key.get(key)
        if not target_item:
            raise SystemExit(f"runtime manifest has no item for {key[0]}/{key[1]}")
        promoted_items.append(
            promote_candidate(
                candidate,
                target_item,
                candidate_manifest=candidate_manifest,
                candidate_manifest_path=candidate_manifest_path,
                quality_report_path=quality_report_path,
                apply=args.apply,
                promoted_at=args.promoted_at,
            )
        )

    report = build_report(
        candidate_manifest=candidate_manifest,
        candidate_manifest_path=candidate_manifest_path,
        quality_report=quality_report,
        quality_report_path=quality_report_path,
        runtime_manifest_path=runtime_manifest_path,
        selected=selected,
        promoted_items=promoted_items,
        apply=args.apply,
        promoted_at=args.promoted_at,
    )
    write_json(promotion_report_path, report)
    if args.apply:
        write_json(output_manifest_path, runtime_manifest)

    print(f"OK: wrote {promotion_report_path}")
    print(f"- mode: {report['mode']}")
    print(f"- selected: {report['selected_candidate_count']}")
    print(f"- promoted: {report['promoted_count']}")
    if args.apply:
        print(f"- manifest: {output_manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
