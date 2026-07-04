#!/usr/bin/env python3
"""Validate MapComponentArtifactStagingManifest v0.1."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA = ROOT / "shared/schemas/map_component_artifact_staging_manifest.v0.1.schema.json"
EXPECTED_SLOT_COUNT = 36
ALLOWED_REPO_CANDIDATE_DIR = ROOT / "game_data/media/map_components/candidates"
ALLOWED_TMP_DIR = Path("/tmp")
ALLOWED_EXTENSIONS = {".png", ".svg", ".webp"}
FORBIDDEN_KEY_FRAGMENTS = (
    "provider",
    "model",
    "raw_prompt",
    "full_prompt",
    "full_trace",
    "raw_json",
    "api_key",
    "secret",
    "unreviewed_content",
    "temporary_url",
)
EXTERNAL_URL_MARKERS = ("http://", "https://", "://")
REQUIRED_USAGE_POLICY = {
    "review_gate_only",
    "local_artifact_import_only",
    "not_runtime_semantic_source",
    "no_image_to_map_semantic_inference",
    "no_frontend_default_consumption",
    "no_manifest_or_style_pack_or_render_plan_mutation",
    "no_provider_or_prompt_payload",
    "no_external_temporary_url",
}
REQUIRED_NEXT_GATES = {
    "local_artifact_import",
    "candidate_review",
    "visual_qa",
    "cutout_normalization",
    "map_style_component_binding_report_refresh",
    "explicit_promotion_gate",
}
RUNTIME_EFFECT_KEYS = (
    "manifest_replacement_written",
    "style_pack_modified",
    "render_plan_modified",
    "frontend_default_modified",
    "runtime_map_truth_modified",
)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def resolve_repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scan_forbidden_key_fragments(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            lowered = key.lower()
            if any(fragment in lowered for fragment in FORBIDDEN_KEY_FRAGMENTS):
                errors.append(f"forbidden field '{child_path}' is not allowed")
            scan_forbidden_key_fragments(child, child_path, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_forbidden_key_fragments(child, f"{path}[{index}]", errors)


def scan_external_urls(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            scan_external_urls(child, f"{path}.{key}" if path else key, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_external_urls(child, f"{path}[{index}]", errors)
    elif isinstance(value, str):
        lowered = value.lower()
        if any(marker in lowered for marker in EXTERNAL_URL_MARKERS):
            errors.append(f"{path} must not contain an external URL")


def validate_with_jsonschema(value: dict[str, Any], schema: dict[str, Any] | None) -> list[str]:
    if not schema:
        return []
    try:
        import jsonschema  # type: ignore
    except Exception:
        return []
    validator_cls = getattr(jsonschema, "Draft202012Validator", None)
    if validator_cls is None:
        validator_cls = getattr(jsonschema, "Draft7Validator", None)
    if validator_cls is None:
        return []
    validator = validator_cls(schema)
    return [
        f"schema: {'.'.join(map(str, error.path)) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(value), key=str)
    ]


def load_source_request_pack(manifest: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    request_pack_value = manifest.get("source_request_pack_path")
    if not isinstance(request_pack_value, str) or not request_pack_value.strip():
        errors.append("source_request_pack_path must be a non-empty string")
        return {}
    request_pack_path = resolve_repo_path(request_pack_value)
    if not request_pack_path.exists():
        errors.append(f"source_request_pack_path does not exist: {request_pack_value}")
        return {}
    try:
        request_pack = load_json(request_pack_path)
    except json.JSONDecodeError as exc:
        errors.append(f"source_request_pack_path is not valid JSON: {exc}")
        return {}
    if not isinstance(request_pack, dict):
        errors.append("source request pack root must be an object")
        return {}
    if request_pack.get("schema_version") != "map_component_generation_request_pack.v0.1":
        errors.append("source request pack must be MapComponentGenerationRequestPack v0.1")
    source_manifest = request_pack.get("source_manifest_path")
    if manifest.get("source_manifest_path") != source_manifest:
        errors.append("source_manifest_path must match the source request pack")
    if isinstance(source_manifest, str) and source_manifest.strip():
        source_manifest_path = resolve_repo_path(source_manifest)
        if not source_manifest_path.exists():
            errors.append(f"source_manifest_path does not exist: {source_manifest}")
    return request_pack


def validate_candidate_file(slot: dict[str, Any], index: int, errors: list[str]) -> None:
    candidate_path_value = slot.get("candidate_local_path")
    candidate_sha = slot.get("candidate_sha256")
    if candidate_path_value is None:
        if candidate_sha is not None:
            errors.append(f"staging_slots[{index}].candidate_sha256 must be null when no file is imported")
        if slot.get("import_status") != "awaiting_local_artifact":
            errors.append(
                f"staging_slots[{index}].import_status must be awaiting_local_artifact when candidate_local_path is null"
            )
        if slot.get("review_status") != "not_imported":
            errors.append(
                f"staging_slots[{index}].review_status must be not_imported when candidate_local_path is null"
            )
        return

    if not isinstance(candidate_path_value, str) or not candidate_path_value.strip():
        errors.append(f"staging_slots[{index}].candidate_local_path must be null or a non-empty string")
        return
    if not isinstance(candidate_sha, str) or not candidate_sha.strip():
        errors.append(f"staging_slots[{index}].candidate_sha256 is required when candidate_local_path is set")
        return

    candidate_path = resolve_repo_path(candidate_path_value)
    allowed_repo_path = is_relative_to(candidate_path, ALLOWED_REPO_CANDIDATE_DIR)
    allowed_tmp_path = candidate_path.is_absolute() and is_relative_to(candidate_path, ALLOWED_TMP_DIR)
    if not allowed_repo_path and not allowed_tmp_path:
        errors.append(
            f"staging_slots[{index}].candidate_local_path must be under "
            "game_data/media/map_components/candidates/ or /tmp"
        )
    if candidate_path.suffix.lower() not in ALLOWED_EXTENSIONS:
        errors.append(
            f"staging_slots[{index}].candidate_local_path extension must be one of "
            f"{', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
    if not candidate_path.exists():
        errors.append(f"staging_slots[{index}].candidate_local_path does not exist: {candidate_path_value}")
    elif candidate_sha != sha256_file(candidate_path):
        errors.append(f"staging_slots[{index}].candidate_sha256 does not match local file")
    if slot.get("import_status") != "imported":
        errors.append(f"staging_slots[{index}].import_status must be imported when candidate_local_path is set")
    if slot.get("review_status") != "staged_for_review":
        errors.append(f"staging_slots[{index}].review_status must be staged_for_review when candidate_local_path is set")


def validate_request_alignment(
    manifest: dict[str, Any],
    request_pack: dict[str, Any],
    errors: list[str],
) -> list[dict[str, Any]]:
    requests = [
        item
        for item in as_list(request_pack.get("requests"))
        if isinstance(item, dict)
    ]
    slots = [
        item
        for item in as_list(manifest.get("staging_slots"))
        if isinstance(item, dict)
    ]
    if len(requests) != EXPECTED_SLOT_COUNT:
        errors.append(f"source request pack must contain {EXPECTED_SLOT_COUNT} requests")
    if len(slots) != EXPECTED_SLOT_COUNT:
        errors.append(f"staging_slots must contain {EXPECTED_SLOT_COUNT} slots")

    requests_by_id = {str(request.get("request_id") or ""): request for request in requests}
    slots_by_request_id: dict[str, dict[str, Any]] = {}
    duplicate_request_ids: set[str] = set()
    for slot in slots:
        request_id = str(slot.get("request_id") or "")
        if request_id in slots_by_request_id:
            duplicate_request_ids.add(request_id)
        slots_by_request_id[request_id] = slot

    missing_slots = sorted(set(requests_by_id) - set(slots_by_request_id))
    extra_slots = sorted(set(slots_by_request_id) - set(requests_by_id))
    for request_id in missing_slots:
        errors.append(f"missing staging slot for request_id: {request_id}")
    for request_id in extra_slots:
        errors.append(f"staging slot has no matching request_id: {request_id}")
    for request_id in sorted(duplicate_request_ids):
        errors.append(f"duplicate staging slot request_id: {request_id}")

    source_request_pack_path = manifest.get("source_request_pack_path")
    for index, slot in enumerate(slots):
        request = requests_by_id.get(str(slot.get("request_id") or ""))
        if not request:
            continue
        if slot.get("source_request_pack_path") != source_request_pack_path:
            errors.append(f"staging_slots[{index}].source_request_pack_path must match manifest")
        for key in ("component_id", "component_role", "style_pack_id", "node_id"):
            if slot.get(key) != request.get(key):
                errors.append(f"staging_slots[{index}].{key} must match source request")
        if as_obj(slot.get("expected_size")) != as_obj(request.get("target_size")):
            errors.append(f"staging_slots[{index}].expected_size must match source request target_size")
    return slots


def validate_manifest(manifest: dict[str, Any], schema: dict[str, Any] | None = None) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_with_jsonschema(manifest, schema))
    scan_forbidden_key_fragments(manifest, "", errors)
    scan_external_urls(manifest, "", errors)

    if manifest.get("schema_version") != "map_component_artifact_staging_manifest.v0.1":
        errors.append("schema_version must be 'map_component_artifact_staging_manifest.v0.1'")

    usage_policy = set(map(str, as_list(manifest.get("usage_policy"))))
    missing_policy = sorted(REQUIRED_USAGE_POLICY - usage_policy)
    if missing_policy:
        errors.append(f"usage_policy missing required policies: {', '.join(missing_policy)}")

    runtime_effect = as_obj(manifest.get("runtime_effect"))
    for key in RUNTIME_EFFECT_KEYS:
        if runtime_effect.get(key) is not False:
            errors.append(f"runtime_effect.{key} must be false; artifact staging is review-only")

    request_pack = load_source_request_pack(manifest, errors)
    slots = validate_request_alignment(manifest, request_pack, errors) if request_pack else []
    slot_ids: set[str] = set()
    duplicate_slot_ids: set[str] = set()
    for index, slot in enumerate(slots):
        slot_id = str(slot.get("slot_id") or "")
        if slot_id in slot_ids:
            duplicate_slot_ids.add(slot_id)
        slot_ids.add(slot_id)

        item_policy = set(map(str, as_list(slot.get("usage_policy"))))
        missing_item_policy = sorted(REQUIRED_USAGE_POLICY - item_policy)
        if missing_item_policy:
            errors.append(
                f"staging_slots[{index}].usage_policy missing required policies: {', '.join(missing_item_policy)}"
            )

        gates = set(map(str, as_list(slot.get("required_next_gates"))))
        missing_gates = sorted(REQUIRED_NEXT_GATES - gates)
        if missing_gates:
            errors.append(f"staging_slots[{index}].required_next_gates missing: {', '.join(missing_gates)}")

        accepted_input_kinds = {str(kind).lower() for kind in as_list(slot.get("accepted_input_kinds"))}
        if not accepted_input_kinds:
            errors.append(f"staging_slots[{index}].accepted_input_kinds must not be empty")
        unexpected_kinds = sorted(accepted_input_kinds - {ext.lstrip(".") for ext in ALLOWED_EXTENSIONS})
        if unexpected_kinds:
            errors.append(
                f"staging_slots[{index}].accepted_input_kinds contains unsupported kinds: "
                f"{', '.join(unexpected_kinds)}"
            )
        validate_candidate_file(slot, index, errors)

    for slot_id in sorted(duplicate_slot_ids):
        errors.append(f"duplicate slot_id: {slot_id}")

    summary = as_obj(manifest.get("summary"))
    import_status_counts = Counter(str(slot.get("import_status")) for slot in slots)
    review_status_counts = Counter(str(slot.get("review_status")) for slot in slots)
    accepted_input_kind_counts = Counter(
        str(kind)
        for slot in slots
        for kind in as_list(slot.get("accepted_input_kinds"))
    )
    imported_count = import_status_counts.get("imported", 0)
    awaiting_count = import_status_counts.get("awaiting_local_artifact", 0)
    not_imported_count = review_status_counts.get("not_imported", 0)
    expected = {
        "slot_count": len(slots),
        "request_count": len(as_list(request_pack.get("requests"))) if request_pack else 0,
        "component_count": len({slot.get("component_id") for slot in slots}),
        "style_pack_count": len({slot.get("style_pack_id") for slot in slots}),
        "node_count": len({slot.get("node_id") for slot in slots}),
        "imported_count": imported_count,
        "awaiting_count": awaiting_count,
        "not_imported_count": not_imported_count,
    }
    for key, value in expected.items():
        if summary.get(key) != value:
            errors.append(f"summary.{key} must be {value}")
    if as_obj(summary.get("status_counts")) != dict(sorted(review_status_counts.items())):
        errors.append("summary.status_counts must match slot review statuses")
    if as_obj(summary.get("import_status_counts")) != dict(sorted(import_status_counts.items())):
        errors.append("summary.import_status_counts must match slot import statuses")
    if as_obj(summary.get("review_status_counts")) != dict(sorted(review_status_counts.items())):
        errors.append("summary.review_status_counts must match slot review statuses")
    if as_obj(summary.get("accepted_input_kind_counts")) != dict(sorted(accepted_input_kind_counts.items())):
        errors.append("summary.accepted_input_kind_counts must match slot accepted input kinds")

    if imported_count == len(slots) and slots:
        expected_status = "imported_for_review"
    elif imported_count:
        expected_status = "partially_imported"
    elif slots:
        expected_status = "awaiting_local_artifacts"
    else:
        expected_status = "blocked"
    if manifest.get("status") != expected_status:
        errors.append(f"status must be {expected_status!r} based on import state")
    return list(dict.fromkeys(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate MapComponentArtifactStagingManifest v0.1.")
    parser.add_argument("manifest", help="Manifest JSON path.")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    schema_path = Path(args.schema)
    try:
        manifest = load_json(manifest_path)
    except FileNotFoundError:
        print("INVALID MapComponentArtifactStagingManifest")
        print(f"- manifest file not found: {manifest_path}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID MapComponentArtifactStagingManifest")
        print(f"- manifest is not valid JSON: {exc}")
        return 1
    if not isinstance(manifest, dict):
        print("INVALID MapComponentArtifactStagingManifest")
        print("- manifest root must be an object")
        return 1

    schema = load_json(schema_path) if schema_path.exists() else None
    if not isinstance(schema, dict):
        schema = None
    errors = validate_manifest(manifest, schema)
    if errors:
        print("INVALID MapComponentArtifactStagingManifest")
        for error in errors:
            print(f"- {error}")
        return 1

    summary = as_obj(manifest.get("summary"))
    print(f"OK: {manifest_path}")
    print(f"- status: {manifest.get('status')}")
    print(f"- slot_count: {summary.get('slot_count')}")
    print(f"- imported_count: {summary.get('imported_count')}")
    print(f"- awaiting_count: {summary.get('awaiting_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
