#!/usr/bin/env python3
"""Validate raw_video_sequence.v0.1 local video metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MEDIA_DIR = Path(__file__).resolve().parent
if str(MEDIA_DIR) not in sys.path:
    sys.path.insert(0, str(MEDIA_DIR))

from png_pipeline import read_png  # noqa: E402


RAW_VIDEO_SEQUENCE_VERSION = "raw_video_sequence.v0.1"
SCHEMA_PATH = ROOT / "shared/schemas/raw_video_sequence.v0.1.schema.json"
REMOTE_URL_RE = re.compile(r"https?://", re.IGNORECASE)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "auth_token",
    "access_token",
    "refresh_token",
    "secret",
    "provider",
    "model",
    "prompt",
    "raw_json",
    "raw_response",
    "full_trace",
    "trace_json",
    "unreviewed_content",
    "temporary_public_url",
    "public_url",
)


@dataclass(frozen=True)
class FixtureFrameRecord:
    """Validated fixture PNG frame metadata for extractor reuse."""

    frame: dict[str, Any]
    source_position: int
    frame_index: int
    local_path: Path
    width: int
    height: int
    sha256: str


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_local_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _json_path(parts: Any) -> str:
    out = "$"
    for part in parts:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += f".{part}"
    return out


def validate_with_jsonschema(data: Any) -> list[str]:
    try:
        import jsonschema  # type: ignore  # noqa: F401
    except ImportError:
        return []

    schema = load_json(SCHEMA_PATH)
    validator_cls = getattr(jsonschema, "Draft202012Validator", None)
    if validator_cls is None:
        validator_cls = getattr(jsonschema, "Draft7Validator")
    validator = validator_cls(schema)
    errors: list[str] = []
    for error in sorted(validator.iter_errors(data), key=lambda item: list(item.path)):
        errors.append(f"schema {_json_path(error.path)}: {error.message}")
        for cause in error.context:
            errors.append(f"schema {_json_path(cause.path)}: {cause.message}")
    return errors


def scan_forbidden_payload(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            lowered = key.lower()
            if any(fragment in lowered for fragment in FORBIDDEN_KEY_FRAGMENTS):
                errors.append(f"forbidden key in raw_video_sequence: {child_path}")
            scan_forbidden_payload(child, child_path, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_forbidden_payload(child, f"{path}[{index}]", errors)
    elif isinstance(value, str) and REMOTE_URL_RE.search(value):
        errors.append(f"remote URL is not allowed in raw_video_sequence: {path}")


def _string_contains_fixture(value: Any) -> bool:
    return "fixture" in str(value or "").lower()


def fixture_declared(raw_video_sequence: dict[str, Any]) -> bool:
    summary = raw_video_sequence.get("summary") if isinstance(raw_video_sequence.get("summary"), dict) else {}
    return (
        raw_video_sequence.get("fixture_only") is True
        or _string_contains_fixture(raw_video_sequence.get("source_kind"))
        or summary.get("fixture") is True
    )


def is_fixture_raw_video_sequence(raw_video_sequence: dict[str, Any]) -> bool:
    return fixture_declared(raw_video_sequence) or isinstance(raw_video_sequence.get("fixture_frames"), list)


def validate_fixture_markers(raw_video_sequence: dict[str, Any]) -> list[str]:
    if not is_fixture_raw_video_sequence(raw_video_sequence):
        return []
    errors: list[str] = []
    if raw_video_sequence.get("review_only") is not True:
        errors.append("review_only must be true for fixture raw video sequences")
    notice = raw_video_sequence.get("fixture_notice")
    if not isinstance(notice, str) or not notice:
        errors.append("fixture_notice must be a non-empty string for fixture raw video sequences")
    frames = raw_video_sequence.get("fixture_frames") if isinstance(raw_video_sequence.get("fixture_frames"), list) else []
    for index, frame in enumerate(frames):
        if isinstance(frame, dict) and frame.get("review_only") is not True:
            errors.append(f"fixture_frames[{index}].review_only must be true for fixture raw video sequences")
    return errors


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_required_strings(raw_video_sequence: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required_strings = (
        "metadata_version",
        "sequence_id",
        "source_kind",
        "asset_id",
        "media_role",
        "animation_state",
        "target_animation_id",
    )
    for key in required_strings:
        value = raw_video_sequence.get(key)
        if not isinstance(value, str) or not value:
            errors.append(f"{key} must be a non-empty string")
    if raw_video_sequence.get("metadata_version") != RAW_VIDEO_SEQUENCE_VERSION:
        errors.append(f"metadata_version must be {RAW_VIDEO_SEQUENCE_VERSION}")
    if raw_video_sequence.get("media_layer") not in (None, "raw_media"):
        errors.append("media_layer must be raw_media when provided")
    if not isinstance(raw_video_sequence.get("review_only"), bool):
        errors.append("review_only must be a boolean")
    return errors


def _validate_video_ref(raw_video_sequence: dict[str, Any], *, is_fixture: bool) -> list[str]:
    errors: list[str] = []
    video_ref = raw_video_sequence.get("video_ref")
    if not isinstance(video_ref, dict):
        return ["video_ref must be an object"]

    local_value = video_ref.get("local_path")
    local_path: Path | None = None
    if not isinstance(local_value, str) or not local_value:
        errors.append("video_ref.local_path must be a non-empty string")
    elif REMOTE_URL_RE.search(local_value):
        errors.append("video_ref.local_path must be local, not remote")
    else:
        local_path = resolve_local_path(local_value)
        if not local_path.exists():
            errors.append(f"video_ref.local_path does not exist: {local_value}")

    mime_type = video_ref.get("mime_type")
    if not isinstance(mime_type, str) or not mime_type:
        errors.append("video_ref.mime_type must be a non-empty string")
    elif not is_fixture and not mime_type.startswith("video/"):
        errors.append("video_ref.mime_type must start with video/ for non-fixture raw videos")

    declared_sha = video_ref.get("sha256")
    if not isinstance(declared_sha, str) or not SHA256_RE.match(declared_sha):
        errors.append("video_ref.sha256 must be a lowercase sha256")
    elif local_path is not None and local_path.exists():
        actual_sha = sha256_file(local_path)
        if actual_sha != declared_sha:
            errors.append("video_ref.sha256 does not match local_path")

    duration_ms = video_ref.get("duration_ms")
    if duration_ms is not None and (not _is_int(duration_ms) or duration_ms <= 0):
        errors.append("video_ref.duration_ms must be a positive integer when provided")
    return errors


def _validate_extraction_plan(raw_video_sequence: dict[str, Any]) -> tuple[int | None, int | None, list[str]]:
    errors: list[str] = []
    plan = raw_video_sequence.get("extraction_plan")
    if not isinstance(plan, dict):
        return None, None, ["extraction_plan must be an object"]

    fps = plan.get("fps")
    if not _is_int(fps):
        errors.append("extraction_plan.fps must be an integer")
        fps_value = None
    elif fps < 1 or fps > 60:
        errors.append("extraction_plan.fps must be between 1 and 60")
        fps_value = fps
    else:
        fps_value = fps

    max_frames = plan.get("max_frames")
    if not _is_int(max_frames):
        errors.append("extraction_plan.max_frames must be an integer")
        max_frames_value = None
    elif max_frames < 2 or max_frames > 240:
        errors.append("extraction_plan.max_frames must be between 2 and 240")
        max_frames_value = max_frames
    else:
        max_frames_value = max_frames

    if plan.get("loop") is not True:
        errors.append("extraction_plan.loop must be true for runtime sprite keyframe extraction")
    for key in ("prefer_keyframes", "reject_blurry_frames"):
        if key in plan and not isinstance(plan.get(key), bool):
            errors.append(f"extraction_plan.{key} must be a boolean when provided")
    return fps_value, max_frames_value, errors


def fixture_frame_records(raw_video_sequence: dict[str, Any]) -> tuple[list[FixtureFrameRecord], list[str]]:
    errors: list[str] = []
    raw_frames = raw_video_sequence.get("fixture_frames")
    if raw_frames is None:
        return [], []
    if not isinstance(raw_frames, list):
        return [], ["fixture_frames must be an array"]
    if len(raw_frames) < 2:
        errors.append("fixture_frames must contain at least 2 frames")

    records: list[FixtureFrameRecord] = []
    seen_indices: set[int] = set()
    seen_ids: set[str] = set()
    expected_size: tuple[int, int] | None = None
    for source_position, frame in enumerate(raw_frames):
        frame_path = f"fixture_frames[{source_position}]"
        if not isinstance(frame, dict):
            errors.append(f"{frame_path} must be an object")
            continue

        stable_id = frame.get("stable_internal_id")
        if not isinstance(stable_id, str) or not stable_id:
            errors.append(f"{frame_path}.stable_internal_id must be a non-empty string")
        elif stable_id in seen_ids:
            errors.append(f"duplicate fixture frame stable_internal_id: {stable_id}")
        else:
            seen_ids.add(stable_id)

        frame_index = frame.get("frame_index")
        if not _is_int(frame_index):
            errors.append(f"{frame_path}.frame_index must be an integer")
            frame_index_int = source_position
        else:
            frame_index_int = frame_index
            if frame_index_int in seen_indices:
                errors.append(f"duplicate fixture frame_index: {frame_index_int}")
            seen_indices.add(frame_index_int)

        timestamp_ms = frame.get("timestamp_ms")
        if not _is_int(timestamp_ms) or timestamp_ms < 0:
            errors.append(f"{frame_path}.timestamp_ms must be a non-negative integer")

        url = frame.get("url")
        if url is not None and (not isinstance(url, str) or not url.startswith("/assets/")):
            errors.append(f"{frame_path}.url must start with /assets/ when provided")

        local_value = frame.get("local_path")
        local_path: Path | None = None
        if not isinstance(local_value, str) or not local_value:
            errors.append(f"{frame_path}.local_path must be a non-empty string")
        elif REMOTE_URL_RE.search(local_value):
            errors.append(f"{frame_path}.local_path must be local, not remote")
        else:
            local_path = resolve_local_path(local_value)
            if not local_path.exists():
                errors.append(f"{frame_path}.local_path does not exist: {local_value}")

        declared_width = frame.get("width")
        declared_height = frame.get("height")
        for key, value in (("width", declared_width), ("height", declared_height)):
            if not _is_int(value) or value <= 0:
                errors.append(f"{frame_path}.{key} must be a positive integer")

        declared_sha = frame.get("sha256")
        if not isinstance(declared_sha, str) or not SHA256_RE.match(declared_sha):
            errors.append(f"{frame_path}.sha256 must be a lowercase sha256")

        if local_path is None or not local_path.exists():
            continue
        try:
            image = read_png(local_path)
        except Exception as exc:  # noqa: BLE001 - report concise PNG gate failures.
            errors.append(f"{frame_path}.local_path is not a supported PNG: {exc}")
            continue

        size = (image.width, image.height)
        if expected_size is None:
            expected_size = size
        elif size != expected_size:
            errors.append(
                f"{frame_path} canvas must match first fixture frame: "
                f"expected {expected_size[0]}x{expected_size[1]}, got {image.width}x{image.height}"
            )
        if _is_int(declared_width) and declared_width != image.width:
            errors.append(f"{frame_path}.width does not match PNG")
        if _is_int(declared_height) and declared_height != image.height:
            errors.append(f"{frame_path}.height does not match PNG")
        actual_sha = sha256_file(local_path)
        if isinstance(declared_sha, str) and SHA256_RE.match(declared_sha) and declared_sha != actual_sha:
            errors.append(f"{frame_path}.sha256 does not match PNG")
        records.append(
            FixtureFrameRecord(
                frame=frame,
                source_position=source_position,
                frame_index=frame_index_int,
                local_path=local_path,
                width=image.width,
                height=image.height,
                sha256=actual_sha,
            )
        )

    if len(records) != len(raw_frames):
        errors.append("fixture_frames must all reference existing supported PNG files")
    return sorted(records, key=lambda record: (record.frame_index, record.source_position)), errors


def _validate_fixture_frames_policy(
    raw_video_sequence: dict[str, Any],
    *,
    fps: int | None,
    max_frames: int | None,
) -> list[str]:
    errors: list[str] = []
    has_fixture_frames = isinstance(raw_video_sequence.get("fixture_frames"), list)
    if has_fixture_frames and not fixture_declared(raw_video_sequence):
        errors.append("fixture_frames requires source_kind containing fixture, fixture_only=true, or summary.fixture=true")
    if is_fixture_raw_video_sequence(raw_video_sequence) and not has_fixture_frames:
        errors.append("fixture raw video sequences must include fixture_frames")

    records, frame_errors = fixture_frame_records(raw_video_sequence)
    errors.extend(frame_errors)
    if records and max_frames is not None and len(records) > max_frames:
        errors.append("fixture_frames length must not exceed extraction_plan.max_frames")
    if records and fps is not None:
        summary = raw_video_sequence.get("summary") if isinstance(raw_video_sequence.get("summary"), dict) else {}
        summary_fps = summary.get("fps")
        if _is_int(summary_fps) and summary_fps != fps:
            errors.append("summary.fps must match extraction_plan.fps")
    return errors


def _validate_summary(raw_video_sequence: dict[str, Any], *, fps: int | None) -> list[str]:
    errors: list[str] = []
    summary = raw_video_sequence.get("summary")
    if not isinstance(summary, dict):
        return ["summary must be an object"]
    if summary.get("review_only") != raw_video_sequence.get("review_only"):
        errors.append("summary.review_only must match review_only")
    if is_fixture_raw_video_sequence(raw_video_sequence) and summary.get("fixture") is not True:
        errors.append("summary.fixture must be true for fixture raw video sequences")

    frames = raw_video_sequence.get("fixture_frames") if isinstance(raw_video_sequence.get("fixture_frames"), list) else []
    summary_count = summary.get("frame_count")
    if frames and _is_int(summary_count) and summary_count != len(frames):
        errors.append("summary.frame_count must match fixture_frames length")
    summary_fps = summary.get("fps")
    if fps is not None and _is_int(summary_fps) and summary_fps != fps:
        errors.append("summary.fps must match extraction_plan.fps")
    duration_ms = summary.get("duration_ms")
    if fps is not None and frames and _is_int(duration_ms):
        min_duration = int(round(1000 * len(frames) / fps))
        if duration_ms < min_duration:
            errors.append("summary.duration_ms is shorter than fixture frame_count/fps")
    return errors


def validate_raw_video_sequence_document(
    raw_video_sequence: Any,
    *,
    run_schema: bool = True,
) -> list[str]:
    errors: list[str] = []
    if run_schema:
        errors.extend(validate_with_jsonschema(raw_video_sequence))
    scan_forbidden_payload(raw_video_sequence, "", errors)
    if not isinstance(raw_video_sequence, dict):
        return errors + ["root must be object"]

    is_fixture = is_fixture_raw_video_sequence(raw_video_sequence)
    errors.extend(_validate_required_strings(raw_video_sequence))
    errors.extend(validate_fixture_markers(raw_video_sequence))
    errors.extend(_validate_video_ref(raw_video_sequence, is_fixture=is_fixture))
    fps, max_frames, plan_errors = _validate_extraction_plan(raw_video_sequence)
    errors.extend(plan_errors)
    errors.extend(_validate_fixture_frames_policy(raw_video_sequence, fps=fps, max_frames=max_frames))
    errors.extend(_validate_summary(raw_video_sequence, fps=fps))
    return errors


def load_validated_raw_video_sequence(path: Path) -> dict[str, Any]:
    data = load_json(path)
    errors = validate_raw_video_sequence_document(data)
    if errors:
        joined = "\n- ".join(errors)
        raise ValueError(f"invalid raw_video_sequence:\n- {joined}")
    if not isinstance(data, dict):
        raise ValueError("invalid raw_video_sequence:\n- root must be object")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw_video_sequence", help="raw_video_sequence.v0.1 JSON path.")
    args = parser.parse_args()
    path = Path(args.raw_video_sequence)
    try:
        data = load_json(path)
    except Exception as exc:  # noqa: BLE001 - CLI should report parse/load failures.
        print("INVALID RawVideoSequence")
        print(f"- cannot load JSON: {exc}")
        return 1
    errors = validate_raw_video_sequence_document(data)
    if errors:
        print("INVALID RawVideoSequence")
        for error in errors:
            print(f"- {error}")
        return 1
    fixture = is_fixture_raw_video_sequence(data) if isinstance(data, dict) else False
    frame_count = len(data.get("fixture_frames") or []) if isinstance(data, dict) else 0
    print(f"OK: {path}")
    print(f"- fixture: {fixture}")
    print(f"- fixture_frames: {frame_count}")
    print("- local_only_contract: enforced")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
