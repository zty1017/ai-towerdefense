#!/usr/bin/env python3
"""Import a local frame_sequence.v0.1 into a MediaAtlasManifest spritesheet.

The importer is intentionally local-only. It reads already-downloaded PNG
frames, replaces the matching deterministic atlas animation with
``frame_source_kind=video_keyframe_sequence``, gates the candidate with the
existing LoopContinuityReport builder, and only writes the output atlas when no
continuity failures are present.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MEDIA_DIR = Path(__file__).resolve().parent
if str(MEDIA_DIR) not in sys.path:
    sys.path.insert(0, str(MEDIA_DIR))

from build_loop_continuity_report import build_report  # noqa: E402
from build_multiframe_atlas_manifest import pack_animation_spritesheet, rel, slug  # noqa: E402
from validate_frame_sequence import (  # noqa: E402
    FRAME_SEQUENCE_VERSION,
    load_validated_frame_sequences,
    runtime_frame_records,
    runtime_playback_settings,
)
from validate_multiframe_atlas_contract import validate_contract  # noqa: E402


DEFAULT_CREATED_AT = "2026-07-04T00:00:00+08:00"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve_local_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def normalize_sequence_frames(
    sequence: dict[str, Any],
    *,
    animation_id: str,
    asset_id: str,
    media_role: str,
    animation_state: str,
    fps: int,
    frames_url_prefix: str,
    anchor: dict[str, Any],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    duration_ms = int(round(1000 / fps))
    records, record_errors = runtime_frame_records(sequence)
    if record_errors:
        raise ValueError("; ".join(record_errors))
    for normalized_index, record in enumerate(records):
        frame = record.frame
        source_url = str(frame.get("url") or "")
        url = source_url or (
            f"{frames_url_prefix.rstrip('/')}/"
            f"{slug(asset_id)}__{slug(media_role)}__{slug(animation_state)}__frame_{normalized_index:03d}.png"
        )
        normalized.append(
            {
                "frame_id": str(frame.get("stable_internal_id") or f"{animation_id}.frame_{normalized_index:03d}"),
                "index": normalized_index,
                "url": url,
                "local_path": rel(record.local_path),
                "x": 0,
                "y": 0,
                "width": record.width,
                "height": record.height,
                "duration_ms": int(frame.get("duration_ms") or duration_ms),
                "sha256": record.sha256,
                "anchor": dict(anchor),
            }
        )

    if len({frame["url"] for frame in normalized}) != len(normalized):
        raise ValueError("imported frame URLs must be unique")
    return normalized


def find_target_item(atlas: dict[str, Any], sequence: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    asset_id = str(sequence.get("asset_id") or "")
    media_role = str(sequence.get("media_role") or "")
    playback = sequence.get("playback") if isinstance(sequence.get("playback"), dict) else {}
    animation_state = str(sequence.get("animation_state") or playback.get("state") or "idle")
    target_animation_id = str(sequence.get("target_animation_id") or f"{asset_id}.{media_role}.{animation_state}")
    if not asset_id or not media_role or not animation_state:
        raise ValueError("frame_sequence must include asset_id, media_role, and animation_state")

    matches: list[tuple[int, dict[str, Any]]] = []
    for index, item in enumerate(atlas.get("items") or []):
        if not isinstance(item, dict):
            continue
        item_playback = item.get("playback") if isinstance(item.get("playback"), dict) else {}
        if item.get("animation_id") == target_animation_id:
            matches.append((index, item))
            continue
        if (
            item.get("asset_id") == asset_id
            and item.get("media_role") == media_role
            and item_playback.get("state") == animation_state
        ):
            matches.append((index, item))
    if not matches:
        raise ValueError(f"no matching atlas item found for {target_animation_id}")
    if len(matches) > 1:
        raise ValueError(f"multiple atlas items matched {target_animation_id}")
    target_index, target = matches[0]
    if target.get("asset_id") != asset_id or target.get("media_role") != media_role:
        raise ValueError(f"target atlas item metadata does not match frame_sequence: {target_animation_id}")
    return target_index, target


def derive_continuity_report_ref(output_atlas: Path) -> str:
    stem = output_atlas.name[:-5] if output_atlas.name.endswith(".json") else output_atlas.name
    replacements = (
        ("art_atlas_manifest", "loop_continuity_report"),
        ("media_atlas_manifest", "loop_continuity_report"),
        ("atlas_manifest", "loop_continuity_report"),
    )
    for before, after in replacements:
        if before in stem:
            stem = stem.replace(before, after, 1)
            break
    else:
        stem = f"{stem}.loop_continuity_report"
    report_path = output_atlas.with_name(f"{stem}.json")
    return rel(report_path) if report_path.is_relative_to(ROOT) else report_path.as_posix()


def recompute_summary(atlas: dict[str, Any]) -> None:
    roles: Counter[str] = Counter()
    asset_ids: set[str] = set()
    frame_count = 0
    for item in atlas.get("items") or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("media_role") or "")
        asset_id = str(item.get("asset_id") or "")
        if role:
            roles[role] += 1
        if asset_id:
            asset_ids.add(asset_id)
        frames = item.get("frames") if isinstance(item.get("frames"), list) else []
        frame_count += len(frames)
    atlas["summary"] = {
        "animation_count": len(atlas.get("items") or []),
        "frame_count": frame_count,
        "asset_count": len(asset_ids),
        "roles": dict(sorted(roles.items())),
    }


def apply_sequence_imports(
    atlas: dict[str, Any],
    sequences: list[dict[str, Any]],
    *,
    frames_url_prefix: str,
    loop_continuity_report_ref: str,
) -> list[dict[str, Any]]:
    imported: list[dict[str, Any]] = []
    for sequence in sequences:
        if sequence.get("metadata_version") != FRAME_SEQUENCE_VERSION:
            raise ValueError(f"frame_sequence entries must use metadata_version={FRAME_SEQUENCE_VERSION}")
        target_index, target = find_target_item(atlas, sequence)
        fps, loop, playback_errors = runtime_playback_settings(sequence)
        if playback_errors or fps is None:
            raise ValueError("; ".join(playback_errors))
        if loop is not True:
            raise ValueError("video keyframe atlas import requires loop=true for runtime sprite contract")

        animation_id = str(target.get("animation_id") or "")
        asset_id = str(sequence.get("asset_id") or target.get("asset_id") or "")
        media_role = str(sequence.get("media_role") or target.get("media_role") or "")
        animation_state = str(sequence.get("animation_state") or playback.get("state") or "idle")
        existing_frames = target.get("frames") if isinstance(target.get("frames"), list) else []
        first_frame = existing_frames[0] if existing_frames and isinstance(existing_frames[0], dict) else {}
        anchor = first_frame.get("anchor") if isinstance(first_frame.get("anchor"), dict) else {"preset": "center", "x": 0.5, "y": 0.5}
        frames = normalize_sequence_frames(
            sequence,
            animation_id=animation_id,
            asset_id=asset_id,
            media_role=media_role,
            animation_state=animation_state,
            fps=fps,
            frames_url_prefix=frames_url_prefix,
            anchor=anchor,
        )

        replacement = copy.deepcopy(target)
        replacement["frame_source_kind"] = "video_keyframe_sequence"
        replacement["loop_continuity_ref"] = str(
            sequence.get("loop_continuity_ref") or f"{loop_continuity_report_ref}#{animation_id}"
        )
        replacement["playback"] = {
            "state": animation_state,
            "fps": fps,
            "loop": True,
            "frame_count": len(frames),
        }
        replacement["frames"] = frames
        atlas["items"][target_index] = replacement
        imported.append(
            {
                "animation_id": animation_id,
                "asset_id": asset_id,
                "media_role": media_role,
                "frame_count": len(frames),
            }
        )
    recompute_summary(atlas)
    return imported


def pack_imported_spritesheets(
    atlas: dict[str, Any],
    imported: list[dict[str, Any]],
    *,
    output_dir: Path,
    url_prefix: str,
) -> None:
    imported_ids = {entry["animation_id"] for entry in imported}
    for item in atlas.get("items") or []:
        if not isinstance(item, dict) or item.get("animation_id") not in imported_ids:
            continue
        playback = item.get("playback") if isinstance(item.get("playback"), dict) else {}
        item["spritesheet"] = pack_animation_spritesheet(
            frames=item["frames"],
            output_dir=output_dir,
            url_prefix=url_prefix,
            asset_id=str(item.get("asset_id") or "asset"),
            role=str(item.get("media_role") or "sprite"),
            animation_state=str(playback.get("state") or "idle"),
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-atlas", required=True, help="Input MediaAtlasManifest path.")
    parser.add_argument("--frame-sequence", required=True, help="Input frame_sequence.v0.1 path.")
    parser.add_argument("--output-atlas", required=True, help="Output MediaAtlasManifest path.")
    parser.add_argument("--spritesheet-output-dir", required=True, help="Directory for imported spritesheet PNGs.")
    parser.add_argument("--spritesheet-url-prefix", required=True, help="Public URL prefix for imported spritesheets.")
    parser.add_argument("--frames-url-prefix", default="", help="Optional public URL prefix for imported frames.")
    parser.add_argument("--atlas-id", default="", help="Optional output atlas_id override.")
    parser.add_argument("--created-at", default=DEFAULT_CREATED_AT)
    parser.add_argument("--loop-continuity-report-ref", default="", help="Expected LoopContinuityReport ref.")
    parser.add_argument("--failure-report-output", default="", help="Where to write the failure report if gate fails.")
    args = parser.parse_args()

    source_atlas_path = resolve_local_path(args.source_atlas)
    frame_sequence_path = resolve_local_path(args.frame_sequence)
    output_atlas_path = Path(args.output_atlas)
    if not output_atlas_path.is_absolute():
        output_atlas_path = ROOT / output_atlas_path
    spritesheet_dir = Path(args.spritesheet_output_dir)
    if not spritesheet_dir.is_absolute():
        spritesheet_dir = ROOT / spritesheet_dir
    frames_url_prefix = args.frames_url_prefix or f"{args.spritesheet_url_prefix.rstrip('/')}/frames"
    loop_report_ref = args.loop_continuity_report_ref or derive_continuity_report_ref(output_atlas_path)
    failure_report_path = Path(args.failure_report_output) if args.failure_report_output else output_atlas_path.with_name(
        f"{output_atlas_path.stem}.loop_continuity_failure_report.json"
    )
    if not failure_report_path.is_absolute():
        failure_report_path = ROOT / failure_report_path

    atlas = load_json(source_atlas_path)
    if not isinstance(atlas, dict):
        raise SystemExit("source atlas root must be an object")

    try:
        sequences = load_validated_frame_sequences(frame_sequence_path)
        candidate = copy.deepcopy(atlas)
        candidate["atlas_id"] = args.atlas_id or f"{atlas.get('atlas_id', 'media_atlas')}_video_keyframe_import"
        candidate["created_at"] = args.created_at
        imported = apply_sequence_imports(
            candidate,
            sequences,
            frames_url_prefix=frames_url_prefix,
            loop_continuity_report_ref=loop_report_ref,
        )
        gate_report = build_report(
            candidate,
            atlas_path=output_atlas_path,
            report_id=f"{candidate['atlas_id']}_continuity_gate",
            created_at=args.created_at,
            alpha_threshold=8,
            max_bbox_delta_ratio=0.08,
            max_anchor_delta=0.03,
            max_alpha_coverage_delta=0.08,
            max_mean_rgba_delta=0.2,
        )
        if gate_report["summary"]["failed_count"] > 0:
            write_json(failure_report_path, gate_report)
            print("FAILED: video keyframe sequence continuity gate failed")
            print(f"- failure_report: {failure_report_path}")
            print(f"- failed: {gate_report['summary']['failed_count']}")
            return 1

        pack_imported_spritesheets(
            candidate,
            imported,
            output_dir=spritesheet_dir,
            url_prefix=args.spritesheet_url_prefix,
        )
        recompute_summary(candidate)
        contract_errors = validate_contract(candidate)
        if contract_errors:
            print("INVALID imported atlas")
            for error in contract_errors:
                print(f"- {error}")
            return 1
        write_json(output_atlas_path, candidate)
    except Exception as exc:  # noqa: BLE001 - CLI should report concise import failures.
        print(f"video keyframe sequence import failed: {exc}")
        return 1

    print(f"OK: wrote {output_atlas_path}")
    print(f"- imported_sequences: {len(imported)}")
    print(f"- video_keyframe_sequence_items: {', '.join(entry['animation_id'] for entry in imported)}")
    print(f"- continuity_gate_status: {gate_report['status']}")
    print(f"- continuity_gate_failed: {gate_report['summary']['failed_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
