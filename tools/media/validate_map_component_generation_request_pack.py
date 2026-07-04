#!/usr/bin/env python3
"""Validate MapComponentGenerationRequestPack v0.1."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA = ROOT / "shared/schemas/map_component_generation_request_pack.v0.1.schema.json"
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
    "not_runtime_semantic_source",
    "no_image_to_map_semantic_inference",
    "no_frontend_default_consumption",
    "redacted_prompt_summary_only",
    "no_provider_or_prompt_payload",
    "no_external_temporary_url",
}
REQUIRED_GATES = {
    "generation_artifact_import",
    "candidate_review",
    "visual_qa",
    "cutout_normalization",
    "map_style_component_binding_report_refresh",
    "explicit_promotion_gate",
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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


def validate_pack(pack: dict[str, Any], schema: dict[str, Any] | None = None) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_with_jsonschema(pack, schema))
    scan_forbidden_key_fragments(pack, "", errors)
    scan_external_urls(pack, "", errors)

    if pack.get("schema_version") != "map_component_generation_request_pack.v0.1":
        errors.append("schema_version must be 'map_component_generation_request_pack.v0.1'")

    usage_policy = set(map(str, as_list(pack.get("usage_policy"))))
    missing_policy = sorted(REQUIRED_USAGE_POLICY - usage_policy)
    if missing_policy:
        errors.append(f"usage_policy missing required policies: {', '.join(missing_policy)}")

    requests = [item for item in as_list(pack.get("requests")) if isinstance(item, dict)]
    request_ids: set[str] = set()
    duplicate_ids: set[str] = set()
    for index, request in enumerate(requests):
        request_id = str(request.get("request_id") or "")
        if request_id in request_ids:
            duplicate_ids.add(request_id)
        request_ids.add(request_id)

        item_policy = set(map(str, as_list(request.get("usage_policy"))))
        missing_item_policy = sorted(REQUIRED_USAGE_POLICY - item_policy)
        if missing_item_policy:
            errors.append(
                f"requests[{index}].usage_policy missing required policies: {', '.join(missing_item_policy)}"
            )

        gates = set(map(str, as_list(request.get("required_gates"))))
        missing_gates = sorted(REQUIRED_GATES - gates)
        if missing_gates:
            errors.append(f"requests[{index}].required_gates missing: {', '.join(missing_gates)}")

        if not as_list(request.get("structured_prompt_tokens")):
            errors.append(f"requests[{index}].structured_prompt_tokens must not be empty")
        if not str(request.get("redacted_prompt_summary") or "").strip():
            errors.append(f"requests[{index}].redacted_prompt_summary must not be empty")

        local_path_value = request.get("baseline_local_path")
        if not isinstance(local_path_value, str):
            errors.append(f"requests[{index}].baseline_local_path must be a string")
            continue
        local_path = ROOT / local_path_value
        if not local_path.exists():
            errors.append(f"requests[{index}].baseline_local_path does not exist: {local_path_value}")
        elif request.get("baseline_sha256") != sha256_file(local_path):
            errors.append(f"requests[{index}].baseline_sha256 does not match local file")

        target_size = as_obj(request.get("target_size"))
        for dim_key in ("width", "height"):
            if not isinstance(target_size.get(dim_key), int) or target_size.get(dim_key) <= 0:
                errors.append(f"requests[{index}].target_size.{dim_key} must be a positive integer")

    for request_id in sorted(duplicate_ids):
        errors.append(f"duplicate request_id: {request_id}")

    summary = as_obj(pack.get("summary"))
    status_counts = Counter(str(request.get("status")) for request in requests)
    role_counts = Counter(str(request.get("component_role")) for request in requests)
    target_media_kind_counts = Counter(str(request.get("target_media_kind")) for request in requests)
    expected = {
        "request_count": len(requests),
        "component_count": len({request.get("component_id") for request in requests}),
        "style_pack_count": len({request.get("style_pack_id") for request in requests}),
        "node_count": len({request.get("node_id") for request in requests}),
    }
    for key, value in expected.items():
        if summary.get(key) != value:
            errors.append(f"summary.{key} must be {value}")
    if as_obj(summary.get("status_counts")) != dict(sorted(status_counts.items())):
        errors.append("summary.status_counts must match request statuses")
    if as_obj(summary.get("component_role_counts")) != dict(sorted(role_counts.items())):
        errors.append("summary.component_role_counts must match request roles")
    if as_obj(summary.get("target_media_kind_counts")) != dict(sorted(target_media_kind_counts.items())):
        errors.append("summary.target_media_kind_counts must match target media kinds")
    return list(dict.fromkeys(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate MapComponentGenerationRequestPack v0.1.")
    parser.add_argument("pack", help="Pack JSON path.")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    args = parser.parse_args()

    pack_path = Path(args.pack)
    schema_path = Path(args.schema)
    try:
        pack = load_json(pack_path)
    except FileNotFoundError:
        print("INVALID MapComponentGenerationRequestPack")
        print(f"- pack file not found: {pack_path}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID MapComponentGenerationRequestPack")
        print(f"- pack is not valid JSON: {exc}")
        return 1
    if not isinstance(pack, dict):
        print("INVALID MapComponentGenerationRequestPack")
        print("- pack root must be an object")
        return 1

    schema = load_json(schema_path) if schema_path.exists() else None
    if not isinstance(schema, dict):
        schema = None
    errors = validate_pack(pack, schema)
    if errors:
        print("INVALID MapComponentGenerationRequestPack")
        for error in errors:
            print(f"- {error}")
        return 1

    summary = as_obj(pack.get("summary"))
    print(f"OK: {pack_path}")
    print(f"- status: {pack.get('status')}")
    print(f"- request_count: {summary.get('request_count')}")
    print(f"- component_count: {summary.get('component_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
