#!/usr/bin/env python3
"""Extract raw_video_sequence.v0.1 into frame_sequence.v0.1 keyframes."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MEDIA_DIR = Path(__file__).resolve().parent
if str(MEDIA_DIR) not in sys.path:
    sys.path.insert(0, str(MEDIA_DIR))

from png_pipeline import read_png  # noqa: E402
from validate_frame_sequence import validate_frame_sequence_document  # noqa: E402
from validate_raw_video_sequence import (  # noqa: E402
    RAW_VIDEO_SEQUENCE_VERSION,
    fixture_frame_records,
    is_fixture_raw_video_sequence,
    load_validated_raw_video_sequence,
    resolve_local_path,
    sha256_file,
)


FRAME_SEQUENCE_VERSION = "frame_sequence.v0.1"


class ExtractionError(RuntimeError):
    """Expected extraction failure with a concise user-facing message."""


def write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def resolve_output_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("_") or "asset"


def frame_filename(raw_video_sequence: dict[str, Any], index: int) -> str:
    asset_id = slug(str(raw_video_sequence.get("asset_id") or "asset"))
    role = slug(str(raw_video_sequence.get("media_role") or "sprite"))
    state = slug(str(raw_video_sequence.get("animation_state") or "idle"))
    return f"{asset_id}__{role}__{state}__raw_video_frame_{index:03d}.png"


def build_frame_sequence(
    raw_video_sequence: dict[str, Any],
    frames: list[dict[str, Any]],
    *,
    source_kind: str,
) -> dict[str, Any]:
    plan = raw_video_sequence.get("extraction_plan") if isinstance(raw_video_sequence.get("extraction_plan"), dict) else {}
    fps = int(plan.get("fps") or 1)
    duration_ms = int(round(1000 * len(frames) / fps))
    frame_sequence: dict[str, Any] = {
        "metadata_version": FRAME_SEQUENCE_VERSION,
        "sequence_id": f"{raw_video_sequence.get('sequence_id')}.frame_sequence",
        "source_kind": source_kind,
        "review_only": bool(raw_video_sequence.get("review_only")),
        "source_video_id": str(raw_video_sequence.get("sequence_id") or ""),
        "media_layer": "raw_media",
        "asset_id": str(raw_video_sequence.get("asset_id") or ""),
        "source_game_id": raw_video_sequence.get("source_game_id"),
        "asset_name": raw_video_sequence.get("asset_name"),
        "asset_type": raw_video_sequence.get("asset_type"),
        "media_role": str(raw_video_sequence.get("media_role") or ""),
        "animation_state": str(raw_video_sequence.get("animation_state") or ""),
        "target_animation_id": str(raw_video_sequence.get("target_animation_id") or ""),
        "frame_source_kind": "video_keyframe_sequence",
        "fps": fps,
        "loop": True,
        "playback": {
            "state": str(raw_video_sequence.get("animation_state") or ""),
            "fps": fps,
            "loop": True,
            "frame_count": len(frames),
        },
        "frames": frames,
        "summary": {
            "frame_count": len(frames),
            "fps": fps,
            "duration_ms": duration_ms,
            "review_only": bool(raw_video_sequence.get("review_only")),
            "fixture": is_fixture_raw_video_sequence(raw_video_sequence),
        },
    }
    if raw_video_sequence.get("fixture_only") is True:
        frame_sequence["fixture_only"] = True
    if raw_video_sequence.get("fixture_notice"):
        frame_sequence["fixture_notice"] = raw_video_sequence.get("fixture_notice")
    return frame_sequence


def validate_candidate_frame_sequence(frame_sequence: dict[str, Any]) -> None:
    errors = validate_frame_sequence_document(frame_sequence)
    if errors:
        joined = "\n- ".join(errors)
        raise ExtractionError(f"generated frame_sequence failed validation:\n- {joined}")


def copy_fixture_frames(
    raw_video_sequence: dict[str, Any],
    *,
    frames_output_dir: Path,
    frames_url_prefix: str,
) -> dict[str, Any]:
    records, errors = fixture_frame_records(raw_video_sequence)
    if errors:
        joined = "\n- ".join(errors)
        raise ExtractionError(f"fixture_frames invalid:\n- {joined}")
    if not records:
        raise ExtractionError("fixture_frames_required: fixture extraction requires fixture_frames")

    frames_output_dir.mkdir(parents=True, exist_ok=True)
    fps = int(raw_video_sequence["extraction_plan"]["fps"])
    default_duration_ms = int(round(1000 / fps))
    frames: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        filename = frame_filename(raw_video_sequence, index)
        destination = frames_output_dir / filename
        shutil.copyfile(record.local_path, destination)
        image = read_png(destination)
        sha = sha256_file(destination)
        frame = record.frame
        frames.append(
            {
                "stable_internal_id": str(
                    frame.get("stable_internal_id")
                    or f"{raw_video_sequence.get('target_animation_id')}.raw_video.frame_{index:03d}"
                ),
                "frame_index": index,
                "timestamp_ms": int(frame.get("timestamp_ms") or round(index * 1000 / fps)),
                "media_role": str(raw_video_sequence.get("media_role") or ""),
                "local_path": destination.as_posix(),
                "url": f"{frames_url_prefix.rstrip('/')}/{filename}",
                "width": image.width,
                "height": image.height,
                "duration_ms": int(frame.get("duration_ms") or default_duration_ms),
                "sha256": sha,
                "source_kind": "fixture_extracted_from_raw_video_sequence",
                "review_only": True,
                "fixture_only": True,
            }
        )
    return build_frame_sequence(
        raw_video_sequence,
        frames,
        source_kind="fixture_raw_video_sequence_extraction",
    )


def run_ffmpeg_extraction(
    raw_video_sequence: dict[str, Any],
    *,
    frames_output_dir: Path,
    frames_url_prefix: str,
) -> dict[str, Any]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise ExtractionError("ffmpeg_not_available: install ffmpeg to extract non-fixture local raw videos")

    plan = raw_video_sequence["extraction_plan"]
    fps = int(plan["fps"])
    max_frames = int(plan["max_frames"])
    video_path = resolve_local_path(str(raw_video_sequence["video_ref"]["local_path"]))
    frames_output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="raw-video-keyframes-") as tmp_name:
        tmp_dir = Path(tmp_name)
        pattern = tmp_dir / "frame_%03d.png"
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            video_path.as_posix(),
            "-vf",
            f"fps={fps}",
            "-frames:v",
            str(max_frames),
            pattern.as_posix(),
        ]
        result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "ffmpeg returned non-zero status").strip()
            raise ExtractionError(f"ffmpeg_failed: {detail}")

        extracted = sorted(tmp_dir.glob("frame_*.png"))
        if len(extracted) < 2:
            raise ExtractionError("ffmpeg_extracted_too_few_frames: need at least 2 PNG frames")

        frames: list[dict[str, Any]] = []
        default_duration_ms = int(round(1000 / fps))
        for index, source in enumerate(extracted[:max_frames]):
            filename = frame_filename(raw_video_sequence, index)
            destination = frames_output_dir / filename
            shutil.move(source.as_posix(), destination.as_posix())
            image = read_png(destination)
            sha = sha256_file(destination)
            frames.append(
                {
                    "stable_internal_id": f"{raw_video_sequence.get('target_animation_id')}.raw_video.frame_{index:03d}",
                    "frame_index": index,
                    "timestamp_ms": int(round(index * 1000 / fps)),
                    "media_role": str(raw_video_sequence.get("media_role") or ""),
                    "local_path": destination.as_posix(),
                    "url": f"{frames_url_prefix.rstrip('/')}/{filename}",
                    "width": image.width,
                    "height": image.height,
                    "duration_ms": default_duration_ms,
                    "sha256": sha,
                    "source_kind": "ffmpeg_extracted_local_raw_video",
                    "review_only": bool(raw_video_sequence.get("review_only")),
                }
            )
    return build_frame_sequence(
        raw_video_sequence,
        frames,
        source_kind="local_raw_video_ffmpeg_extraction",
    )


def extract(raw_video_sequence: dict[str, Any], *, frames_output_dir: Path, frames_url_prefix: str) -> dict[str, Any]:
    if raw_video_sequence.get("metadata_version") != RAW_VIDEO_SEQUENCE_VERSION:
        raise ExtractionError(f"raw_video_sequence must use metadata_version={RAW_VIDEO_SEQUENCE_VERSION}")
    if is_fixture_raw_video_sequence(raw_video_sequence):
        return copy_fixture_frames(
            raw_video_sequence,
            frames_output_dir=frames_output_dir,
            frames_url_prefix=frames_url_prefix,
        )
    return run_ffmpeg_extraction(
        raw_video_sequence,
        frames_output_dir=frames_output_dir,
        frames_url_prefix=frames_url_prefix,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-video-sequence", required=True, help="Input raw_video_sequence.v0.1 path.")
    parser.add_argument("--output-frame-sequence", required=True, help="Output frame_sequence.v0.1 path.")
    parser.add_argument("--frames-output-dir", required=True, help="Directory for extracted PNG frames.")
    parser.add_argument("--frames-url-prefix", required=True, help="Public /assets URL prefix for extracted frames.")
    args = parser.parse_args()

    raw_video_path = resolve_output_path(args.raw_video_sequence)
    output_path = resolve_output_path(args.output_frame_sequence)
    frames_output_dir = resolve_output_path(args.frames_output_dir)

    try:
        raw_video_sequence = load_validated_raw_video_sequence(raw_video_path)
        frame_sequence = extract(
            raw_video_sequence,
            frames_output_dir=frames_output_dir,
            frames_url_prefix=args.frames_url_prefix,
        )
        validate_candidate_frame_sequence(frame_sequence)
        write_json_atomic(output_path, frame_sequence)
    except Exception as exc:  # noqa: BLE001 - CLI should report concise extraction failures.
        print(f"extract_video_keyframes failed: {exc}")
        return 1

    print(f"OK: wrote {output_path}")
    print(f"- source_raw_video_sequence: {raw_video_path}")
    print(f"- frame_count: {len(frame_sequence.get('frames') or [])}")
    print(f"- fixture_mode: {is_fixture_raw_video_sequence(raw_video_sequence)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
