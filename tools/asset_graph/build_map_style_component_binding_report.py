#!/usr/bin/env python3
"""Build a MapStylePack component binding review report.

The report is an audit gate for explicit style-layer media refs only. It does
not infer map semantics from media and does not modify runtime packages.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import procedural_map_render_plan as pmrp  # noqa: E402


DEFAULT_STYLE_PACKS = sorted((ROOT / "examples/map_style_packs").glob("*.map_style_pack.json"))
DEFAULT_MEDIA_MANIFESTS = [
    ROOT / "game_data/media/frontend_runtime_mock/frontend_runtime_art_media_manifest.v0.1.json",
]
DEFAULT_ATLAS_MANIFESTS = [
    ROOT / "game_data/media/frontend_runtime_mock/frontend_runtime_art_atlas_manifest.v0.1.json",
    ROOT / "game_data/media/frontend_mock/frontend_media_atlas_manifest.v0.1.json",
]
DEFAULT_OUTPUT = ROOT / "examples/review_packs/map_style_component_binding_report.v0.1.json"

EXTERNAL_URL_MARKERS = ("http://", "https://")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def resolve_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return ROOT / path


def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def has_external_url(value: Any) -> bool:
    if isinstance(value, dict):
        return any(has_external_url(child) for child in value.values())
    if isinstance(value, list):
        return any(has_external_url(child) for child in value)
    if isinstance(value, str):
        lowered = value.lower()
        return any(marker in lowered for marker in EXTERNAL_URL_MARKERS)
    return False


def normalize_ref(ref: str | None) -> tuple[str, str | None]:
    if not ref:
        return "none", None
    if ref.startswith("media:"):
        return "media", ref.removeprefix("media:")
    if ref.startswith("atlas:"):
        return "atlas", ref.removeprefix("atlas:")
    if "://" in ref:
        return "invalid", ref
    return "bare", ref


def media_summary(item: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
    return {
        "manifest_path": rel(manifest_path),
        "manifest_kind": "media_manifest",
        "stable_internal_id": item.get("stable_internal_id"),
        "asset_id": item.get("asset_id"),
        "asset_type": item.get("asset_type"),
        "media_role": item.get("media_role"),
        "media_layer": item.get("media_layer"),
        "local_path": item.get("local_path"),
        "url": item.get("url"),
        "sha256": item.get("sha256"),
    }


def atlas_summary(item: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
    sheet = as_obj(item.get("spritesheet"))
    return {
        "manifest_path": rel(manifest_path),
        "manifest_kind": "atlas_manifest",
        "animation_id": item.get("animation_id"),
        "asset_id": item.get("asset_id"),
        "asset_type": item.get("asset_type"),
        "media_role": item.get("media_role"),
        "media_layer": item.get("media_layer"),
        "local_path": sheet.get("local_path"),
        "url": sheet.get("url"),
        "sha256": sheet.get("sha256"),
    }


def build_indexes(
    media_manifest_paths: list[Path], atlas_manifest_paths: list[Path]
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]], list[str]]:
    media_index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    atlas_index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    notes: list[str] = []

    for path in media_manifest_paths:
        manifest = load_json(path)
        pmrp.scan_forbidden_fields(manifest, rel(path), notes)
        for item in as_list(as_obj(manifest).get("items")):
            if not isinstance(item, dict):
                continue
            stable_id = item.get("stable_internal_id")
            if stable_id:
                media_index[str(stable_id)].append(media_summary(item, path))

    for path in atlas_manifest_paths:
        manifest = load_json(path)
        pmrp.scan_forbidden_fields(manifest, rel(path), notes)
        for item in as_list(as_obj(manifest).get("items")):
            if not isinstance(item, dict):
                continue
            animation_id = item.get("animation_id")
            if animation_id:
                atlas_index[str(animation_id)].append(atlas_summary(item, path))

    return media_index, atlas_index, notes


def resolve_component_ref(
    ref: str | None,
    media_index: dict[str, list[dict[str, Any]]],
    atlas_index: dict[str, list[dict[str, Any]]],
) -> tuple[str, str, dict[str, Any] | None, list[str]]:
    ref_kind, ref_value = normalize_ref(ref)
    if ref_kind == "none":
        return ref_kind, "procedural_fallback", None, ["No reviewed component ref provided."]
    if ref_kind == "invalid":
        return ref_kind, "external_url_rejected", None, ["External or malformed component refs cannot pass review."]

    matches: list[dict[str, Any]] = []
    if ref_kind == "media" and ref_value:
        matches = media_index.get(ref_value, [])
    elif ref_kind == "atlas" and ref_value:
        matches = atlas_index.get(ref_value, [])
    elif ref_kind == "bare" and ref_value:
        matches = media_index.get(ref_value, []) + atlas_index.get(ref_value, [])

    if not matches:
        return ref_kind, "missing", None, ["Explicit reviewed component ref was not found in supplied manifests."]
    if len(matches) > 1:
        return ref_kind, "ambiguous", None, ["Bare or duplicated ref matched multiple manifest entries."]
    resolved = matches[0]
    if has_external_url(resolved):
        return ref_kind, "external_url_rejected", None, ["Resolved manifest entry contains an external URL."]
    return ref_kind, "resolved", resolved, ["Resolved from reviewed local media/atlas manifest."]


def binding_record(
    *,
    style_pack: dict[str, Any],
    binding_source: str,
    owner_id: str,
    role: str,
    ref: str | None,
    media_index: dict[str, list[dict[str, Any]]],
    atlas_index: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    ref_kind, resolution_status, resolved_ref, notes = resolve_component_ref(
        ref, media_index, atlas_index
    )
    return {
        "style_pack_id": str(style_pack.get("style_pack_id") or "unknown_style_pack"),
        "node_id": str(style_pack.get("node_id") or "unknown_node"),
        "binding_source": binding_source,
        "owner_id": owner_id,
        "role": role,
        "ref": ref,
        "ref_kind": ref_kind,
        "resolution_status": resolution_status,
        "resolved_ref": resolved_ref,
        "notes": notes,
    }


def collect_style_bindings(
    style_pack: dict[str, Any],
    media_index: dict[str, list[dict[str, Any]]],
    atlas_index: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    bindings: list[dict[str, Any]] = []
    coverage_gaps: list[dict[str, Any]] = []

    for material in as_list(style_pack.get("terrain_materials")) + as_list(
        style_pack.get("road_materials")
    ):
        if not isinstance(material, dict):
            continue
        material_id = str(material.get("material_id") or "unknown_material")
        role = str(material.get("role") or "unknown_role")
        ref = material.get("component_ref")
        has_ref = isinstance(ref, str) and bool(ref.strip())
        if has_ref:
            bindings.append(
                binding_record(
                    style_pack=style_pack,
                    binding_source="material.component_ref",
                    owner_id=material_id,
                    role=role,
                    ref=ref,
                    media_index=media_index,
                    atlas_index=atlas_index,
                )
            )
        else:
            bindings.append(
                binding_record(
                    style_pack=style_pack,
                    binding_source="procedural_fallback",
                    owner_id=material_id,
                    role=role,
                    ref=None,
                    media_index=media_index,
                    atlas_index=atlas_index,
                )
            )
            coverage_gaps.append(
                {
                    "style_pack_id": str(style_pack.get("style_pack_id") or "unknown_style_pack"),
                    "node_id": str(style_pack.get("node_id") or "unknown_node"),
                    "owner_id": material_id,
                    "role": role,
                    "reason": "material uses procedural fallback; no reviewed component_ref bound yet",
                }
            )

    prefab_keys = (
        "build_slot_platforms",
        "objective_prefabs",
        "spawn_prefabs",
        "resource_prefabs",
        "hazard_prefabs",
        "blocking_props",
        "non_blocking_props",
        "decorative_props",
    )
    for key in prefab_keys:
        for prefab in as_list(style_pack.get(key)):
            if not isinstance(prefab, dict):
                continue
            visual_ref = as_obj(prefab.get("visual_ref"))
            prefab_id = str(prefab.get("prefab_id") or "unknown_prefab")
            role = str(prefab.get("role") or "unknown_role")
            if visual_ref.get("kind") == "reviewed_component_ref":
                bindings.append(
                    binding_record(
                        style_pack=style_pack,
                        binding_source="prefab.visual_ref",
                        owner_id=prefab_id,
                        role=role,
                        ref=visual_ref.get("value"),
                        media_index=media_index,
                        atlas_index=atlas_index,
                    )
                )
            else:
                bindings.append(
                    binding_record(
                        style_pack=style_pack,
                        binding_source="procedural_fallback",
                        owner_id=prefab_id,
                        role=role,
                        ref=None,
                        media_index=media_index,
                        atlas_index=atlas_index,
                    )
                )
                coverage_gaps.append(
                    {
                        "style_pack_id": str(style_pack.get("style_pack_id") or "unknown_style_pack"),
                        "node_id": str(style_pack.get("node_id") or "unknown_node"),
                        "owner_id": prefab_id,
                        "role": role,
                        "reason": "prefab uses procedural visual_ref; no reviewed component media bound yet",
                    }
                )

    return bindings, coverage_gaps


def build_report(
    style_pack_paths: list[Path],
    media_manifest_paths: list[Path],
    atlas_manifest_paths: list[Path],
    *,
    report_id: str,
    created_at: str,
) -> dict[str, Any]:
    media_index, atlas_index, index_notes = build_indexes(
        media_manifest_paths, atlas_manifest_paths
    )
    style_packs = [load_json(path) for path in style_pack_paths]

    bindings: list[dict[str, Any]] = []
    coverage_gaps: list[dict[str, Any]] = []
    for style_pack in style_packs:
        if not isinstance(style_pack, dict):
            continue
        pack_bindings, pack_gaps = collect_style_bindings(
            style_pack, media_index, atlas_index
        )
        bindings.extend(pack_bindings)
        coverage_gaps.extend(pack_gaps)

    status_counts = Counter(str(item.get("resolution_status")) for item in bindings)
    missing_count = status_counts.get("missing", 0)
    ambiguous_count = status_counts.get("ambiguous", 0)
    external_count = status_counts.get("external_url_rejected", 0)
    explicit_count = len(
        [
            item
            for item in bindings
            if item.get("binding_source")
            in {"material.component_ref", "prefab.visual_ref"}
        ]
    )
    status = "failed" if missing_count or ambiguous_count or external_count else "passed"
    if coverage_gaps and status == "passed":
        status = "warning"

    review_notes = [
        "This report only resolves explicit MapStylePack media refs; MapRuntimePackage remains the map logic source.",
        "No image, atlas, or media entry may create or override routes, build slots, objectives, spawn points, resources, hazards, or collision.",
    ]
    if not explicit_count:
        review_notes.append(
            "Current StylePacks have no explicit reviewed component media refs; procedural fallback remains in use and component coverage is a known gap."
        )
    review_notes.extend(index_notes)

    return {
        "schema_version": "map_style_component_binding_report.v0.1",
        "report_id": report_id,
        "created_at": created_at,
        "source_refs": {
            "map_style_pack_paths": [rel(path) for path in style_pack_paths],
            "media_manifest_paths": [rel(path) for path in media_manifest_paths],
            "atlas_manifest_paths": [rel(path) for path in atlas_manifest_paths],
        },
        "status": status,
        "summary": {
            "style_pack_count": len(style_packs),
            "material_component_ref_count": len(
                [item for item in bindings if item.get("binding_source") == "material.component_ref"]
            ),
            "prefab_reviewed_component_ref_count": len(
                [item for item in bindings if item.get("binding_source") == "prefab.visual_ref"]
            ),
            "resolved_ref_count": status_counts.get("resolved", 0),
            "missing_ref_count": missing_count,
            "procedural_fallback_count": status_counts.get("procedural_fallback", 0),
            "ambiguous_ref_count": ambiguous_count,
            "external_url_rejected_count": external_count,
            "component_coverage_gap_count": len(coverage_gaps),
            "status_counts": dict(sorted(status_counts.items())),
        },
        "usage_policy": [
            "review_gate_only",
            "not_runtime_semantic_source",
            "no_image_to_map_semantic_inference",
            "no_external_temporary_url_pass",
            "redacted_summary_only",
        ],
        "review_notes": review_notes,
        "bindings": bindings,
        "coverage_gaps": coverage_gaps,
        "validation": {
            "validator": "tools/asset_graph/validate_map_style_component_binding_report.py",
            "commands": [
                "python3 tools/asset_graph/validate_map_style_component_binding_report.py examples/review_packs/map_style_component_binding_report.v0.1.json"
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a MapStylePack component media binding review report."
    )
    parser.add_argument(
        "--style-pack",
        action="append",
        default=[],
        help="MapStylePack JSON path. May be passed multiple times.",
    )
    parser.add_argument(
        "--media-manifest",
        action="append",
        default=[],
        help="Media manifest path. May be passed multiple times.",
    )
    parser.add_argument(
        "--atlas-manifest",
        action="append",
        default=[],
        help="Atlas manifest path. May be passed multiple times.",
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output report path.")
    parser.add_argument(
        "--report-id",
        default="map_style_component_binding_report_v0_1",
        help="Report id to write.",
    )
    parser.add_argument("--created-at", default=now_iso(), help="Created timestamp.")
    args = parser.parse_args()

    style_pack_paths = (
        [resolve_path(path) for path in args.style_pack]
        if args.style_pack
        else DEFAULT_STYLE_PACKS
    )
    media_manifest_paths = (
        [resolve_path(path) for path in args.media_manifest]
        if args.media_manifest
        else DEFAULT_MEDIA_MANIFESTS
    )
    atlas_manifest_paths = (
        [resolve_path(path) for path in args.atlas_manifest]
        if args.atlas_manifest
        else DEFAULT_ATLAS_MANIFESTS
    )
    output_path = resolve_path(args.output)

    report = build_report(
        style_pack_paths,
        media_manifest_paths,
        atlas_manifest_paths,
        report_id=args.report_id,
        created_at=args.created_at,
    )
    write_json(output_path, report)
    print(f"OK: wrote {output_path}")
    print(f"- status: {report['status']}")
    print(f"- style_pack_count: {report['summary']['style_pack_count']}")
    print(f"- resolved_ref_count: {report['summary']['resolved_ref_count']}")
    print(f"- procedural_fallback_count: {report['summary']['procedural_fallback_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
