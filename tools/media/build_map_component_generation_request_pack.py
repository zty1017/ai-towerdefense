#!/usr/bin/env python3
"""Build review-only MapComponent generation request summaries.

This builder derives request metadata from the deterministic
MapComponentMediaManifest baseline. It does not call providers, read .env,
write prompts, or modify the manifest/StylePacks/RenderPlans/runtime map truth.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPORT_VERSION = "map_component_generation_request_pack.v0.1"
DEFAULT_MANIFEST = ROOT / "game_data/media/map_components/map_component_media_manifest.v0.1.json"
DEFAULT_OUTPUT = ROOT / "examples/review_packs/map_component_generation_request_pack.v0.1.json"

USAGE_POLICY = [
    "review_gate_only",
    "not_runtime_semantic_source",
    "no_image_to_map_semantic_inference",
    "no_frontend_default_consumption",
    "redacted_prompt_summary_only",
    "no_provider_or_prompt_payload",
    "no_external_temporary_url",
]
NEGATIVE_CONSTRAINTS = [
    "no UI, frame, panel, menu, watermark, logo, visible text, labels, or numbers",
    "no route, tower slot, objective, spawn, resource, hazard, blocking, or collision semantic changes",
    "no enemies, NPCs, projectiles, combat effects, or deployed towers",
    "no external temporary URL, unreviewed content, raw response, trace, or secret material",
]
REQUIRED_GATES = [
    "generation_artifact_import",
    "candidate_review",
    "visual_qa",
    "cutout_normalization",
    "map_style_component_binding_report_refresh",
    "explicit_promotion_gate",
]


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


def prompt_profile_id(component_role: str, target_media_kind: str) -> str:
    return f"map_component_{component_role}_{target_media_kind}_review_v0_1"


def prompt_summary(item: dict[str, Any]) -> str:
    return (
        "Generate a reviewed presentation component candidate matching the "
        f"{item.get('component_role')} role for node {item.get('node_id')}; "
        "preserve all gameplay semantics from MapRuntimePackage and use the SVG "
        "baseline only as a style/shape reference."
    )


def prompt_tokens(item: dict[str, Any]) -> list[str]:
    return sorted(
        {
            "map_component",
            "presentation_layer",
            "style_pack:" + str(item.get("style_pack_id")),
            "node:" + str(item.get("node_id")),
            "role:" + str(item.get("component_role")),
            "baseline_reference_only",
            "transparent_or_cutout_ready",
            "runtime_semantics_preserved",
        }
    )


def build_request(item: dict[str, Any], target_media_kind: str) -> dict[str, Any]:
    component_id = str(item.get("stable_internal_id") or item.get("asset_id"))
    component_role = str(item.get("component_role") or "unknown_component_role")
    return {
        "request_id": f"{component_id}.{target_media_kind}.request",
        "component_id": component_id,
        "component_role": component_role,
        "style_pack_id": str(item.get("style_pack_id") or "unknown_style_pack"),
        "node_id": str(item.get("node_id") or "unknown_node"),
        "source_manifest_item_id": component_id,
        "baseline_local_path": item.get("local_path"),
        "baseline_sha256": item.get("sha256"),
        "target_size": {
            "width": int(item.get("width") or 256),
            "height": int(item.get("height") or 256),
        },
        "target_media_kind": target_media_kind,
        "prompt_profile_id": prompt_profile_id(component_role, target_media_kind),
        "redacted_prompt_summary": prompt_summary(item),
        "structured_prompt_tokens": prompt_tokens(item),
        "negative_constraints": NEGATIVE_CONSTRAINTS,
        "required_gates": REQUIRED_GATES,
        "usage_policy": USAGE_POLICY,
        "status": "request_ready_review_only",
    }


def build_pack(
    manifest_path: Path,
    *,
    output_path: Path,
    created_at: str | None,
    target_media_kind: str,
) -> dict[str, Any]:
    manifest = as_obj(load_json(manifest_path))
    requests = [
        build_request(item, target_media_kind)
        for item in as_list(manifest.get("items"))
        if isinstance(item, dict)
    ]
    status_counts = Counter(str(request.get("status")) for request in requests)
    role_counts = Counter(str(request.get("component_role")) for request in requests)
    target_media_kind_counts = Counter(str(request.get("target_media_kind")) for request in requests)
    pack = {
        "schema_version": REPORT_VERSION,
        "pack_id": "map_component_generation_request_pack_v0_1",
        "created_at": created_at or str(manifest.get("created_at") or "2026-07-05T00:00:00Z"),
        "source_manifest_path": rel(manifest_path),
        "status": "request_pack_ready_review_only" if requests else "blocked",
        "usage_policy": USAGE_POLICY,
        "summary": {
            "request_count": len(requests),
            "component_count": len({request.get("component_id") for request in requests}),
            "style_pack_count": len({request.get("style_pack_id") for request in requests}),
            "node_count": len({request.get("node_id") for request in requests}),
            "target_media_kind_counts": dict(sorted(target_media_kind_counts.items())),
            "component_role_counts": dict(sorted(role_counts.items())),
            "status_counts": dict(sorted(status_counts.items())),
        },
        "requests": requests,
        "validation": {
            "validator": "tools/media/validate_map_component_generation_request_pack.py",
            "commands": [
                f"python3 tools/media/validate_map_component_generation_request_pack.py {rel(output_path)}"
            ],
        },
    }
    return pack


def main() -> int:
    parser = argparse.ArgumentParser(description="Build MapComponentGenerationRequestPack v0.1.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--created-at", default=None)
    parser.add_argument("--target-media-kind", choices=["image", "video"], default="image")
    args = parser.parse_args()

    manifest_path = resolve_path(args.manifest)
    output_path = resolve_path(args.output)
    pack = build_pack(
        manifest_path,
        output_path=output_path,
        created_at=args.created_at,
        target_media_kind=args.target_media_kind,
    )
    write_json(output_path, pack)
    print(f"OK: wrote {output_path}")
    print(f"- status: {pack['status']}")
    print(f"- request_count: {pack['summary']['request_count']}")
    return 0 if pack["summary"]["request_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
