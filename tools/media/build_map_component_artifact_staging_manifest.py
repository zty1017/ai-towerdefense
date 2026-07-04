#!/usr/bin/env python3
"""Build review-only MapComponent artifact staging slots.

This builder derives empty local-artifact staging slots from a
MapComponentGenerationRequestPack. It does not call providers, read .env,
copy candidate files, or modify the manifest/StylePacks/RenderPlans/frontend
defaults/runtime map truth.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPORT_VERSION = "map_component_artifact_staging_manifest.v0.1"
DEFAULT_REQUEST_PACK = ROOT / "examples/review_packs/map_component_generation_request_pack.v0.1.json"
DEFAULT_OUTPUT = ROOT / "examples/review_packs/map_component_artifact_staging_manifest.v0.1.json"

USAGE_POLICY = [
    "review_gate_only",
    "local_artifact_import_only",
    "not_runtime_semantic_source",
    "no_image_to_map_semantic_inference",
    "no_frontend_default_consumption",
    "no_manifest_or_style_pack_or_render_plan_mutation",
    "no_provider_or_prompt_payload",
    "no_external_temporary_url",
]
ACCEPTED_INPUT_KINDS = ["png", "svg", "webp"]
REQUIRED_NEXT_GATES = [
    "local_artifact_import",
    "candidate_review",
    "visual_qa",
    "cutout_normalization",
    "map_style_component_binding_report_refresh",
    "explicit_promotion_gate",
]
RUNTIME_EFFECT = {
    "manifest_replacement_written": False,
    "style_pack_modified": False,
    "render_plan_modified": False,
    "frontend_default_modified": False,
    "runtime_map_truth_modified": False,
}


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


def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def build_slot(request: dict[str, Any], source_request_pack_path: str) -> dict[str, Any]:
    request_id = str(request.get("request_id") or "")
    return {
        "slot_id": f"{request_id}.artifact_staging",
        "request_id": request_id,
        "component_id": str(request.get("component_id") or ""),
        "component_role": str(request.get("component_role") or ""),
        "style_pack_id": str(request.get("style_pack_id") or ""),
        "node_id": str(request.get("node_id") or ""),
        "source_request_pack_path": source_request_pack_path,
        "expected_size": as_obj(request.get("target_size")),
        "accepted_input_kinds": ACCEPTED_INPUT_KINDS,
        "candidate_local_path": None,
        "candidate_sha256": None,
        "import_status": "awaiting_local_artifact",
        "review_status": "not_imported",
        "required_next_gates": REQUIRED_NEXT_GATES,
        "usage_policy": USAGE_POLICY,
    }


def build_manifest(
    request_pack_path: Path,
    *,
    output_path: Path,
    created_at: str | None,
) -> dict[str, Any]:
    request_pack = as_obj(load_json(request_pack_path))
    source_request_pack = rel(request_pack_path)
    requests = [
        request
        for request in as_list(request_pack.get("requests"))
        if isinstance(request, dict)
    ]
    slots = [build_slot(request, source_request_pack) for request in requests]
    status_counts = Counter(str(slot.get("review_status")) for slot in slots)
    import_status_counts = Counter(str(slot.get("import_status")) for slot in slots)
    review_status_counts = Counter(str(slot.get("review_status")) for slot in slots)
    accepted_input_kind_counts = Counter(
        kind
        for slot in slots
        for kind in as_list(slot.get("accepted_input_kinds"))
    )
    imported_count = import_status_counts.get("imported", 0)
    awaiting_count = import_status_counts.get("awaiting_local_artifact", 0)
    not_imported_count = review_status_counts.get("not_imported", 0)
    if imported_count == len(slots) and slots:
        status = "imported_for_review"
    elif imported_count:
        status = "partially_imported"
    elif slots:
        status = "awaiting_local_artifacts"
    else:
        status = "blocked"
    manifest = {
        "schema_version": REPORT_VERSION,
        "manifest_id": "map_component_artifact_staging_manifest_v0_1",
        "created_at": created_at or str(request_pack.get("created_at") or "2026-07-05T00:00:00Z"),
        "source_request_pack_path": source_request_pack,
        "source_manifest_path": str(request_pack.get("source_manifest_path") or ""),
        "status": status,
        "usage_policy": USAGE_POLICY,
        "summary": {
            "slot_count": len(slots),
            "request_count": len(requests),
            "component_count": len({slot.get("component_id") for slot in slots}),
            "style_pack_count": len({slot.get("style_pack_id") for slot in slots}),
            "node_count": len({slot.get("node_id") for slot in slots}),
            "imported_count": imported_count,
            "awaiting_count": awaiting_count,
            "not_imported_count": not_imported_count,
            "status_counts": dict(sorted(status_counts.items())),
            "import_status_counts": dict(sorted(import_status_counts.items())),
            "review_status_counts": dict(sorted(review_status_counts.items())),
            "accepted_input_kind_counts": dict(sorted(accepted_input_kind_counts.items())),
        },
        "staging_slots": slots,
        "runtime_effect": RUNTIME_EFFECT,
        "validation": {
            "validator": "tools/media/validate_map_component_artifact_staging_manifest.py",
            "commands": [
                f"python3 tools/media/validate_map_component_artifact_staging_manifest.py {rel(output_path)}"
            ],
        },
    }
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build MapComponentArtifactStagingManifest v0.1.")
    parser.add_argument("--request-pack", default=str(DEFAULT_REQUEST_PACK))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--created-at", default=None)
    args = parser.parse_args()

    request_pack_path = resolve_path(args.request_pack)
    output_path = resolve_path(args.output)
    manifest = build_manifest(
        request_pack_path,
        output_path=output_path,
        created_at=args.created_at,
    )
    write_json(output_path, manifest)
    print(f"OK: wrote {output_path}")
    print(f"- status: {manifest['status']}")
    print(f"- slot_count: {manifest['summary']['slot_count']}")
    print(f"- imported_count: {manifest['summary']['imported_count']}")
    print(f"- awaiting_count: {manifest['summary']['awaiting_count']}")
    return 0 if manifest["summary"]["slot_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
