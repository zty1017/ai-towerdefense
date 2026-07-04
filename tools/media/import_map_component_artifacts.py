#!/usr/bin/env python3
"""Import local MapComponent generated artifact candidates into staging slots.

This tool only fills existing MapComponentArtifactStagingManifest v0.1 slots
with reviewed local file references. It does not call providers, read .env,
upload files, or mutate runtime map truth / frontend defaults / the formal
MapComponent media manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import validate_map_component_artifact_staging_manifest as staging_validator


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STAGING_MANIFEST = ROOT / "examples/review_packs/map_component_artifact_staging_manifest.v0.1.json"
ALLOWED_REPO_CANDIDATE_DIR = ROOT / "game_data/media/map_components/candidates"
ALLOWED_TMP_DIR = Path("/tmp")
ALLOWED_EXTENSIONS = {".png", ".svg", ".webp"}
FORBIDDEN_KEY_FRAGMENTS = (
    "provider",
    "model",
    "prompt",
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
PLAN_ROOT_KEYS = {"schema_version", "imports", "entries"}
PLAN_ENTRY_KEYS = {"request_id", "slot_id", "candidate_local_path"}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def rel_or_abs(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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
                errors.append(f"forbidden field '{child_path}' is not allowed in import plan")
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


def plan_entries(plan: Any, errors: list[str]) -> list[dict[str, Any]]:
    if isinstance(plan, list):
        entries = plan
    elif isinstance(plan, dict):
        unexpected_root_keys = sorted(set(plan) - PLAN_ROOT_KEYS)
        for key in unexpected_root_keys:
            errors.append(f"import plan root contains unsupported field: {key}")
        if "imports" in plan and "entries" in plan:
            errors.append("import plan must use only one of 'imports' or 'entries'")
            return []
        entries = plan.get("imports", plan.get("entries"))
    else:
        errors.append("import plan root must be an object or array")
        return []

    if not isinstance(entries, list):
        errors.append("import plan must contain an imports array")
        return []

    normalized: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"imports[{index}] must be an object")
            continue
        unexpected_entry_keys = sorted(set(entry) - PLAN_ENTRY_KEYS)
        for key in unexpected_entry_keys:
            errors.append(f"imports[{index}] contains unsupported field: {key}")
        has_request_id = isinstance(entry.get("request_id"), str) and bool(entry.get("request_id", "").strip())
        has_slot_id = isinstance(entry.get("slot_id"), str) and bool(entry.get("slot_id", "").strip())
        if has_request_id == has_slot_id:
            errors.append(f"imports[{index}] must specify exactly one of request_id or slot_id")
        if not isinstance(entry.get("candidate_local_path"), str) or not entry.get("candidate_local_path", "").strip():
            errors.append(f"imports[{index}].candidate_local_path must be a non-empty string")
        normalized.append(entry)
    return normalized


def validate_candidate_path(path_value: str, index: int, errors: list[str]) -> tuple[Path | None, str | None]:
    path = resolve_path(path_value)
    suffix = path.suffix
    if suffix.lower() not in ALLOWED_EXTENSIONS:
        errors.append(
            f"imports[{index}].candidate_local_path extension must be one of "
            f"{', '.join(sorted(ext.lstrip('.') for ext in ALLOWED_EXTENSIONS))}"
        )
    if suffix != suffix.lower():
        errors.append(f"imports[{index}].candidate_local_path extension must be lowercase")

    allowed_repo_path = is_relative_to(path, ALLOWED_REPO_CANDIDATE_DIR)
    allowed_tmp_path = path.is_absolute() and is_relative_to(path, ALLOWED_TMP_DIR)
    if not allowed_repo_path and not allowed_tmp_path:
        errors.append(
            f"imports[{index}].candidate_local_path must be under "
            "game_data/media/map_components/candidates/ or /tmp"
        )
    if not path.exists():
        errors.append(f"imports[{index}].candidate_local_path does not exist: {path_value}")
        return None, None
    if not path.is_file():
        errors.append(f"imports[{index}].candidate_local_path must be a file: {path_value}")
        return None, None
    return path, rel_or_abs(path)


def refresh_summary_and_status(manifest: dict[str, Any]) -> None:
    slots = [slot for slot in as_list(manifest.get("staging_slots")) if isinstance(slot, dict)]
    import_status_counts = Counter(str(slot.get("import_status")) for slot in slots)
    review_status_counts = Counter(str(slot.get("review_status")) for slot in slots)
    accepted_input_kind_counts = Counter(
        str(kind)
        for slot in slots
        for kind in as_list(slot.get("accepted_input_kinds"))
    )
    imported_count = import_status_counts.get("imported", 0)
    if imported_count == len(slots) and slots:
        status = "imported_for_review"
    elif imported_count:
        status = "partially_imported"
    elif slots:
        status = "awaiting_local_artifacts"
    else:
        status = "blocked"

    manifest["status"] = status
    manifest["summary"] = {
        "slot_count": len(slots),
        "request_count": as_obj(manifest.get("summary")).get("request_count", len(slots)),
        "component_count": len({slot.get("component_id") for slot in slots}),
        "style_pack_count": len({slot.get("style_pack_id") for slot in slots}),
        "node_count": len({slot.get("node_id") for slot in slots}),
        "imported_count": imported_count,
        "awaiting_count": import_status_counts.get("awaiting_local_artifact", 0),
        "not_imported_count": review_status_counts.get("not_imported", 0),
        "status_counts": dict(sorted(review_status_counts.items())),
        "import_status_counts": dict(sorted(import_status_counts.items())),
        "review_status_counts": dict(sorted(review_status_counts.items())),
        "accepted_input_kind_counts": dict(sorted(accepted_input_kind_counts.items())),
    }


def slots_by_key(manifest: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    slots = [slot for slot in as_list(manifest.get("staging_slots")) if isinstance(slot, dict)]
    return (
        {str(slot.get("request_id") or ""): slot for slot in slots},
        {str(slot.get("slot_id") or ""): slot for slot in slots},
    )


def apply_import_plan(manifest: dict[str, Any], plan: Any, *, output_path: Path) -> tuple[dict[str, Any], int, list[str]]:
    errors: list[str] = []
    scan_forbidden_key_fragments(plan, "", errors)
    scan_external_urls(plan, "", errors)
    entries = plan_entries(plan, errors)
    by_request_id, by_slot_id = slots_by_key(manifest)
    targeted_slot_ids: set[str] = set()
    imports: list[tuple[dict[str, Any], Path, str]] = []

    for index, entry in enumerate(entries):
        if errors:
            continue
        request_id = entry.get("request_id")
        slot_id = entry.get("slot_id")
        slot = by_request_id.get(str(request_id)) if request_id else by_slot_id.get(str(slot_id))
        if not slot:
            identifier = request_id if request_id else slot_id
            id_field = "request_id" if request_id else "slot_id"
            errors.append(f"imports[{index}] has no matching staging slot for {id_field}: {identifier}")
            continue
        resolved_path, stored_path = validate_candidate_path(str(entry.get("candidate_local_path")), index, errors)
        if resolved_path is None or stored_path is None:
            continue
        resolved_slot_id = str(slot.get("slot_id") or "")
        if resolved_slot_id in targeted_slot_ids:
            errors.append(f"imports[{index}] duplicates staging slot: {resolved_slot_id}")
            continue
        targeted_slot_ids.add(resolved_slot_id)
        imports.append((slot, resolved_path, stored_path))

    if errors:
        return manifest, 0, errors

    for slot, resolved_path, stored_path in imports:
        slot["candidate_local_path"] = stored_path
        slot["candidate_sha256"] = sha256_file(resolved_path)
        slot["import_status"] = "imported"
        slot["review_status"] = "staged_for_review"

    manifest["validation"] = {
        "validator": "tools/media/validate_map_component_artifact_staging_manifest.py",
        "commands": [
            f"python3 tools/media/validate_map_component_artifact_staging_manifest.py {rel_or_abs(output_path)}"
        ],
    }
    refresh_summary_and_status(manifest)
    schema_path = staging_validator.DEFAULT_SCHEMA
    schema = load_json(schema_path) if schema_path.exists() else None
    schema_obj = schema if isinstance(schema, dict) else None
    errors.extend(staging_validator.validate_manifest(manifest, schema_obj))
    return manifest, len(imports), errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Import local MapComponent artifacts into staging slots.")
    parser.add_argument("--staging-manifest", default=str(DEFAULT_STAGING_MANIFEST))
    parser.add_argument("--import-plan", required=True, help="JSON plan with imports[].")
    parser.add_argument(
        "--output",
        default=None,
        help="Output manifest path. Defaults to writing back --staging-manifest.",
    )
    args = parser.parse_args()

    staging_path = resolve_path(args.staging_manifest)
    plan_path = resolve_path(args.import_plan)
    output_path = resolve_path(args.output) if args.output else staging_path

    try:
        manifest = load_json(staging_path)
        plan = load_json(plan_path)
    except FileNotFoundError as exc:
        print(f"ERROR: file not found: {exc.filename}")
        return 1
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON: {exc}")
        return 1
    if not isinstance(manifest, dict):
        print("ERROR: staging manifest root must be an object")
        return 1

    updated_manifest, imported_count, errors = apply_import_plan(manifest, plan, output_path=output_path)
    if errors:
        print("INVALID MapComponent artifact import")
        for error in errors:
            print(f"- {error}")
        return 1

    write_json(output_path, updated_manifest)
    print(f"OK: wrote {output_path}")
    print(f"- status: {updated_manifest['status']}")
    print(f"- imported_this_run: {imported_count}")
    print(f"- imported_count: {updated_manifest['summary']['imported_count']}")
    print(f"- awaiting_count: {updated_manifest['summary']['awaiting_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
