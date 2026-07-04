#!/usr/bin/env python3
"""Validate frame_sequence.v0.1 local PNG frame sequences."""

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


FRAME_SEQUENCE_VERSION = "frame_sequence.v0.1"
SCHEMA_PATH = ROOT / "shared/schemas/frame_sequence.v0.1.schema.json"
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
)


@dataclass(frozen=True)
class RuntimeFrameRecord:
    """Validated local PNG frame metadata for importer reuse."""

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
        import jsonschema  # type: ignore
    except ImportError:
        return []

    schema = load_json(SCHEMA_PATH)
    validator_cls = getattr(jsonschema, "Draft202012Validator", None)
    if validator_cls is None:
        validator_cls = getattr(jsonschema, "Draft7Validator")
    validator = validator_cls(schema)
    errors: list[str] = []
    for error in sorted(validator.iter_errors(data), key=lambda item: list(item.path)):
        if error.validator == "oneOf":
            errors.append(f"schema {_json_path(error.path)}: document must match FrameSequence or FrameSequence bundle")
        else:
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
                errors.append(f"forbidden key in frame_sequence: {child_path}")
            scan_forbidden_payload(child, child_path, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_forbidden_payload(child, f"{path}[{index}]", errors)
    elif isinstance(value, str) and REMOTE_URL_RE.search(value):
        errors.append(f"remote URL is not allowed in frame_sequence: {path}")


def sequence_entries(frame_sequence: dict[str, Any]) -> list[dict[str, Any]]:
    sequences = frame_sequence.get("sequences")
    if isinstance(sequences, list):
        entries: list[dict[str, Any]] = []
        for entry in sequences:
            if not isinstance(entry, dict):
                continue
            normalized = dict(entry)
            normalized.setdefault("metadata_version", frame_sequence.get("metadata_version"))
            entries.append(normalized)
        return entries
    return [frame_sequence]


def _extract_sequence_entries(frame_sequence: Any) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(frame_sequence, dict):
        return [], ["root must be object"]
    if isinstance(frame_sequence.get("sequences"), list):
        if frame_sequence.get("metadata_version") != FRAME_SEQUENCE_VERSION:
            return [], [f"metadata_version must be {FRAME_SEQUENCE_VERSION}"]
        entries = sequence_entries(frame_sequence)
        if len(entries) != len(frame_sequence.get("sequences") or []):
            return entries, ["sequences must contain only objects"]
        if not entries:
            return entries, ["sequences must be non-empty"]
        return entries, []
    if frame_sequence.get("metadata_version") != FRAME_SEQUENCE_VERSION:
        return [], [f"metadata_version must be {FRAME_SEQUENCE_VERSION}"]
    return [frame_sequence], []


def _string_contains_fixture(value: Any) -> bool:
    return "fixture" in str(value or "").lower()


def is_fixture_sequence(sequence: dict[str, Any]) -> bool:
    if sequence.get("fixture_only") is True:
        return True
    if _string_contains_fixture(sequence.get("source_kind")):
        return True
    summary = sequence.get("summary") if isinstance(sequence.get("summary"), dict) else {}
    if summary.get("fixture") is True:
        return True
    for frame in sequence.get("frames") or []:
        if not isinstance(frame, dict):
            continue
        if frame.get("fixture_only") is True or _string_contains_fixture(frame.get("source_kind")):
            return True
    return False


def validate_fixture_markers(sequence: dict[str, Any], prefix: str = "sequence") -> list[str]:
    if not is_fixture_sequence(sequence):
        return []
    errors: list[str] = []
    if sequence.get("review_only") is not True:
        errors.append(f"{prefix}.review_only must be true for fixture sequences")
    notice = sequence.get("fixture_notice")
    if not isinstance(notice, str) or not notice:
        errors.append(f"{prefix}.fixture_notice must be a non-empty string for fixture sequences")
    frames = sequence.get("frames") if isinstance(sequence.get("frames"), list) else []
    for index, frame in enumerate(frames):
        if isinstance(frame, dict) and frame.get("review_only") is not True:
            errors.append(f"{prefix}.frames[{index}].review_only must be true for fixture sequences")
    return errors


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _collect_int_field(
    owner: dict[str, Any],
    key: str,
    path: str,
    values: list[tuple[str, int]],
    errors: list[str],
) -> None:
    if key not in owner:
        return
    value = owner.get(key)
    if not _is_int(value):
        errors.append(f"{path} must be an integer")
        return
    values.append((path, value))


def _collect_bool_field(
    owner: dict[str, Any],
    key: str,
    path: str,
    values: list[tuple[str, bool]],
    errors: list[str],
) -> None:
    if key not in owner:
        return
    value = owner.get(key)
    if not isinstance(value, bool):
        errors.append(f"{path} must be a boolean")
        return
    values.append((path, value))


def runtime_playback_settings(
    sequence: dict[str, Any],
    prefix: str = "sequence",
) -> tuple[int | None, bool | None, list[str]]:
    errors: list[str] = []
    fps_values: list[tuple[str, int]] = []
    loop_values: list[tuple[str, bool]] = []
    playback = sequence.get("playback") if isinstance(sequence.get("playback"), dict) else {}
    summary = sequence.get("summary") if isinstance(sequence.get("summary"), dict) else {}

    _collect_int_field(sequence, "fps", f"{prefix}.fps", fps_values, errors)
    _collect_int_field(playback, "fps", f"{prefix}.playback.fps", fps_values, errors)
    _collect_int_field(summary, "fps", f"{prefix}.summary.fps", fps_values, errors)
    _collect_bool_field(sequence, "loop", f"{prefix}.loop", loop_values, errors)
    _collect_bool_field(playback, "loop", f"{prefix}.playback.loop", loop_values, errors)

    fps = fps_values[0][1] if fps_values else None
    if fps is None:
        errors.append(f"{prefix}.fps must be declared for runtime sprite import")
    elif fps < 1:
        errors.append(f"{prefix}.fps must be >= 1")
    for path, value in fps_values[1:]:
        if value != fps:
            errors.append(f"{path} must match {fps_values[0][0]}")

    loop = loop_values[0][1] if loop_values else None
    if loop is None:
        errors.append(f"{prefix}.loop must be declared for runtime sprite import")
    elif loop is not True:
        errors.append(f"{prefix}.loop must be true for runtime sprite import")
    for path, value in loop_values[1:]:
        if value != loop:
            errors.append(f"{path} must match {loop_values[0][0]}")
    return fps, loop, errors


def _validate_sequence_structure(sequence: dict[str, Any], prefix: str) -> list[str]:
    errors: list[str] = []
    required_strings = (
        "metadata_version",
        "sequence_id",
        "asset_id",
        "media_role",
        "animation_state",
        "frame_source_kind",
    )
    for key in required_strings:
        value = sequence.get(key)
        if not isinstance(value, str) or not value:
            errors.append(f"{prefix}.{key} must be a non-empty string")
    if sequence.get("metadata_version") != FRAME_SEQUENCE_VERSION:
        errors.append(f"{prefix}.metadata_version must be {FRAME_SEQUENCE_VERSION}")
    if sequence.get("frame_source_kind") != "video_keyframe_sequence":
        errors.append(f"{prefix}.frame_source_kind must be video_keyframe_sequence")
    frames = sequence.get("frames")
    if not isinstance(frames, list):
        errors.append(f"{prefix}.frames must be an array")
    elif len(frames) < 2:
        errors.append(f"{prefix}.frames must contain at least 2 frames")
    summary = sequence.get("summary")
    if not isinstance(summary, dict):
        errors.append(f"{prefix}.summary must be an object")
    return errors


def runtime_frame_records(
    sequence: dict[str, Any],
    prefix: str = "sequence",
) -> tuple[list[RuntimeFrameRecord], list[str]]:
    errors: list[str] = []
    raw_frames = sequence.get("frames")
    if not isinstance(raw_frames, list):
        return [], [f"{prefix}.frames must be an array"]
    if len(raw_frames) < 2:
        errors.append(f"{prefix}.frames must contain at least 2 frames")

    records: list[RuntimeFrameRecord] = []
    seen_indices: set[int] = set()
    seen_ids: set[str] = set()
    expected_size: tuple[int, int] | None = None
    sequence_role = sequence.get("media_role")
    for source_position, frame in enumerate(raw_frames):
        frame_path = f"{prefix}.frames[{source_position}]"
        if not isinstance(frame, dict):
            errors.append(f"{frame_path} must be an object")
            continue

        stable_id = frame.get("stable_internal_id")
        if not isinstance(stable_id, str) or not stable_id:
            errors.append(f"{frame_path}.stable_internal_id must be a non-empty string")
        elif stable_id in seen_ids:
            errors.append(f"duplicate stable_internal_id: {stable_id}")
        else:
            seen_ids.add(stable_id)

        frame_index = frame.get("frame_index")
        if not _is_int(frame_index):
            errors.append(f"{frame_path}.frame_index must be an integer")
            frame_index_int = source_position
        else:
            frame_index_int = frame_index
            if frame_index_int in seen_indices:
                errors.append(f"duplicate frame_index: {frame_index_int}")
            seen_indices.add(frame_index_int)

        frame_role = frame.get("media_role")
        if not isinstance(frame_role, str) or not frame_role:
            errors.append(f"{frame_path}.media_role must be a non-empty string")
        elif isinstance(sequence_role, str) and sequence_role and frame_role != sequence_role:
            errors.append(f"{frame_path}.media_role must match {prefix}.media_role")

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
                f"{frame_path} canvas must match first frame: "
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
            RuntimeFrameRecord(
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
        errors.append(f"{prefix}.frames must all reference existing supported PNG files")
    return sorted(records, key=lambda record: (record.frame_index, record.source_position)), errors


def _validate_summary(sequence: dict[str, Any], prefix: str, frame_count: int, fps: int | None) -> list[str]:
    errors: list[str] = []
    summary = sequence.get("summary") if isinstance(sequence.get("summary"), dict) else {}
    playback = sequence.get("playback") if isinstance(sequence.get("playback"), dict) else {}
    summary_count = summary.get("frame_count")
    playback_count = playback.get("frame_count")
    if _is_int(summary_count) and summary_count != frame_count:
        errors.append(f"{prefix}.summary.frame_count must match frames length")
    if _is_int(playback_count) and playback_count != frame_count:
        errors.append(f"{prefix}.playback.frame_count must match frames length")
    if isinstance(playback.get("state"), str) and playback.get("state") != sequence.get("animation_state"):
        errors.append(f"{prefix}.playback.state must match {prefix}.animation_state")
    if fps is not None and _is_int(summary.get("duration_ms")):
        min_duration = int(round(1000 * frame_count / fps))
        if summary["duration_ms"] < min_duration:
            errors.append(f"{prefix}.summary.duration_ms is shorter than frame_count/fps")
    return errors


def validate_frame_sequence_document(
    frame_sequence: Any,
    *,
    require_runtime_import: bool = True,
    run_schema: bool = True,
) -> list[str]:
    errors: list[str] = []
    if run_schema:
        errors.extend(validate_with_jsonschema(frame_sequence))
    scan_forbidden_payload(frame_sequence, "", errors)
    entries, entry_errors = _extract_sequence_entries(frame_sequence)
    errors.extend(entry_errors)
    for index, sequence in enumerate(entries):
        prefix = "sequence" if len(entries) == 1 else f"sequences[{index}]"
        errors.extend(_validate_sequence_structure(sequence, prefix))
        errors.extend(validate_fixture_markers(sequence, prefix))
        fps, _loop, playback_errors = runtime_playback_settings(sequence, prefix)
        errors.extend(playback_errors)
        frame_count = len(sequence.get("frames") or []) if isinstance(sequence.get("frames"), list) else 0
        errors.extend(_validate_summary(sequence, prefix, frame_count, fps))
        if require_runtime_import:
            _records, frame_errors = runtime_frame_records(sequence, prefix)
            errors.extend(frame_errors)
    return errors


def load_validated_frame_sequences(
    path: Path,
    *,
    require_runtime_import: bool = True,
) -> list[dict[str, Any]]:
    data = load_json(path)
    errors = validate_frame_sequence_document(data, require_runtime_import=require_runtime_import)
    if errors:
        joined = "\n- ".join(errors)
        raise ValueError(f"invalid frame_sequence:\n- {joined}")
    if not isinstance(data, dict):
        raise ValueError("invalid frame_sequence:\n- root must be object")
    return sequence_entries(data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frame_sequence", help="frame_sequence.v0.1 JSON path.")
    args = parser.parse_args()
    path = Path(args.frame_sequence)
    try:
        data = load_json(path)
    except Exception as exc:  # noqa: BLE001 - CLI should report parse/load failures.
        print("INVALID FrameSequence")
        print(f"- cannot load JSON: {exc}")
        return 1
    errors = validate_frame_sequence_document(data)
    if errors:
        print("INVALID FrameSequence")
        for error in errors:
            print(f"- {error}")
        return 1
    entries = sequence_entries(data) if isinstance(data, dict) else []
    frame_count = sum(len(entry.get("frames") or []) for entry in entries)
    fixture_count = sum(1 for entry in entries if is_fixture_sequence(entry))
    print(f"OK: {path}")
    print(f"- sequences: {len(entries)}")
    print(f"- frames: {frame_count}")
    print(f"- fixture_sequences: {fixture_count}")
    print("- runtime_import_contract: enforced")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
