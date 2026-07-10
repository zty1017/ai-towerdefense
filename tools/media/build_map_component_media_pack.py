#!/usr/bin/env python3
"""Build deterministic reviewed SVG media for MapStylePack components.

This fixture builder is offline by design: it never calls providers, never
reads .env, and never derives gameplay facts from component media. The output
only gives MapStylePack material/prefab entries stable local presentation refs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STYLE_PACKS = sorted((ROOT / "examples/map_style_packs").glob("*.map_style_pack.json"))
DEFAULT_OUTPUT_DIR = ROOT / "game_data/media/map_components/processed"
DEFAULT_MANIFEST = ROOT / "game_data/media/map_components/map_component_media_manifest.v0.1.json"
PUBLIC_PREFIX = "/assets/map_components/processed"
WIDTH = 256
HEIGHT = 256

PREFAB_KEYS = (
    "build_slot_platforms",
    "objective_prefabs",
    "spawn_prefabs",
    "resource_prefabs",
    "hazard_prefabs",
    "blocking_props",
    "non_blocking_props",
    "decorative_props",
)
USAGE_POLICY = [
    "review_gate_only",
    "not_runtime_semantic_source",
    "no_image_to_map_semantic_inference",
    "local_reviewed_component_only",
    "frontend_default_presentation_allowed",
    "no_provider_or_prompt_payload",
    "no_external_temporary_url",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_text(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding="utf-8")


def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return normalized or "component"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clamp_color(value: Any, fallback: str) -> str:
    if isinstance(value, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
        return value.lower()
    return fallback


def shade(hex_color: str, amount: int) -> str:
    raw = hex_color.lstrip("#")
    values = [int(raw[i : i + 2], 16) for i in (0, 2, 4)]
    shifted = [max(0, min(255, value + amount)) for value in values]
    return "#" + "".join(f"{value:02x}" for value in shifted)


def svg_component(owner_id: str, role: str, base_color: str, accent_color: str, binding: str) -> str:
    base = clamp_color(base_color, "#45505a")
    accent = clamp_color(accent_color, "#d2a84a")
    dark = shade(base, -34)
    light = shade(base, 42)
    line = shade(accent, -26)
    role_slug = slug(role)

    if binding == "material.component_ref":
        pattern = (
            "<path d=\"M-20 214 C48 176 82 242 148 204 S248 188 288 134\" "
            f"fill=\"none\" stroke=\"{escape(line)}\" stroke-width=\"18\" stroke-linecap=\"round\" opacity=\"0.42\"/>"
            "<path d=\"M-8 70 C38 52 74 82 118 58 S206 34 270 76\" "
            f"fill=\"none\" stroke=\"{escape(light)}\" stroke-width=\"12\" stroke-linecap=\"round\" opacity=\"0.36\"/>"
        )
    elif role_slug in {"build_slot_platform", "objective_foundation"}:
        pattern = (
            f"<ellipse cx=\"128\" cy=\"146\" rx=\"78\" ry=\"42\" fill=\"{escape(dark)}\" opacity=\"0.7\"/>"
            f"<ellipse cx=\"128\" cy=\"128\" rx=\"86\" ry=\"48\" fill=\"none\" stroke=\"{escape(accent)}\" stroke-width=\"13\"/>"
            f"<ellipse cx=\"128\" cy=\"128\" rx=\"49\" ry=\"27\" fill=\"{escape(light)}\" opacity=\"0.36\"/>"
        )
    elif role_slug in {"spawn_marker", "resource_marker", "hazard_marker"}:
        pattern = (
            f"<circle cx=\"128\" cy=\"128\" r=\"68\" fill=\"{escape(dark)}\" opacity=\"0.72\"/>"
            f"<path d=\"M128 42 L190 154 H66 Z\" fill=\"{escape(light)}\" opacity=\"0.5\"/>"
            f"<circle cx=\"128\" cy=\"128\" r=\"33\" fill=\"none\" stroke=\"{escape(accent)}\" stroke-width=\"12\"/>"
        )
    elif role_slug == "blocking_prop":
        pattern = (
            f"<path d=\"M52 168 L86 78 L154 64 L206 126 L176 192 L96 202 Z\" fill=\"{escape(dark)}\"/>"
            f"<path d=\"M86 78 L176 192\" stroke=\"{escape(accent)}\" stroke-width=\"12\" opacity=\"0.55\"/>"
            f"<path d=\"M58 166 L206 126\" stroke=\"{escape(light)}\" stroke-width=\"10\" opacity=\"0.35\"/>"
        )
    else:
        pattern = (
            f"<circle cx=\"78\" cy=\"145\" r=\"28\" fill=\"{escape(light)}\" opacity=\"0.55\"/>"
            f"<circle cx=\"148\" cy=\"104\" r=\"22\" fill=\"{escape(accent)}\" opacity=\"0.48\"/>"
            f"<path d=\"M52 184 C86 156 134 172 202 136\" fill=\"none\" stroke=\"{escape(dark)}\" stroke-width=\"14\" stroke-linecap=\"round\"/>"
        )

    return (
        "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"256\" height=\"256\" viewBox=\"0 0 256 256\" role=\"img\">"
        "<rect width=\"256\" height=\"256\" rx=\"0\" "
        f"fill=\"{escape(base)}\"/>"
        f"<circle cx=\"26\" cy=\"30\" r=\"58\" fill=\"{escape(light)}\" opacity=\"0.18\"/>"
        f"<circle cx=\"226\" cy=\"226\" r=\"76\" fill=\"{escape(dark)}\" opacity=\"0.28\"/>"
        f"{pattern}"
        f"<path d=\"M24 226 H232\" stroke=\"{escape(accent)}\" stroke-width=\"8\" opacity=\"0.35\"/>"
        f"<metadata>{escape(owner_id)}|{escape(role)}|reviewed-map-component</metadata>"
        "</svg>\n"
    )


def component_id(style_pack: dict[str, Any], owner_id: str) -> str:
    return f"map_component_{slug(str(style_pack.get('node_id') or 'node'))}_{slug(owner_id)}"


def material_items(style_pack: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for collection in ("terrain_materials", "road_materials"):
        for material in style_pack.get(collection, []):
            if not isinstance(material, dict):
                continue
            items.append(
                {
                    "owner_id": str(material.get("material_id") or material.get("role") or "material"),
                    "role": str(material.get("role") or "material"),
                    "base_color": material.get("base_color"),
                    "binding": "material.component_ref",
                    "media_role": "map_component_material",
                    "source": material,
                }
            )
    return items


def prefab_items(style_pack: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    palette = style_pack.get("palette") if isinstance(style_pack.get("palette"), dict) else {}
    for key in PREFAB_KEYS:
        for prefab in style_pack.get(key, []):
            if not isinstance(prefab, dict):
                continue
            role = str(prefab.get("role") or "prefab")
            items.append(
                {
                    "owner_id": str(prefab.get("prefab_id") or role),
                    "role": role,
                    "base_color": palette.get(role) or palette.get("accent") or palette.get("terrain_detail"),
                    "binding": "prefab.visual_ref",
                    "media_role": "map_component_prefab",
                    "source": prefab,
                }
            )
    return items


def build_pack(
    style_pack_paths: list[Path],
    output_dir: Path,
    manifest_path: Path,
    *,
    created_at: str,
    update_style_packs: bool,
) -> dict[str, Any]:
    style_packs = [load_json(path) for path in style_pack_paths]
    items: list[dict[str, Any]] = []

    for style_pack, style_path in zip(style_packs, style_pack_paths):
        if not isinstance(style_pack, dict):
            continue
        palette = style_pack.get("palette") if isinstance(style_pack.get("palette"), dict) else {}
        accent = str(palette.get("accent") or "#d2a84a")
        components = material_items(style_pack) + prefab_items(style_pack)
        for component in components:
            owner_id = component["owner_id"]
            stable_id = component_id(style_pack, owner_id)
            local_path = output_dir / f"{stable_id}.svg"
            svg = svg_component(
                owner_id,
                component["role"],
                str(component.get("base_color") or palette.get("terrain_base") or "#45505a"),
                accent,
                component["binding"],
            )
            write_text(local_path, svg)

            source = component["source"]
            media_ref = f"media:{stable_id}"
            if update_style_packs and isinstance(source, dict):
                if component["binding"] == "material.component_ref":
                    source["texture_policy"] = "reviewed_component_optional"
                    source["component_ref"] = media_ref
                else:
                    source["visual_ref"] = {
                        "kind": "reviewed_component_ref",
                        "value": media_ref,
                    }

            items.append(
                {
                    "stable_internal_id": stable_id,
                    "asset_id": stable_id,
                    "asset_type": "map_component",
                    "media_role": component["media_role"],
                    "media_layer": "reviewed_map_component_media",
                    "component_role": component["role"],
                    "style_pack_id": str(style_pack.get("style_pack_id") or ""),
                    "node_id": str(style_pack.get("node_id") or ""),
                    "source_owner_id": owner_id,
                    "source_binding": component["binding"],
                    "url": f"{PUBLIC_PREFIX}/{local_path.name}",
                    "local_path": rel(local_path),
                    "width": WIDTH,
                    "height": HEIGHT,
                    "sha256": sha256_file(local_path),
                    "usage_policy": USAGE_POLICY,
                    "source_kind": "deterministic_developer_fixture_svg",
                }
            )

        if update_style_packs:
            write_json(style_path, style_pack)

    roles = Counter(str(item["component_role"]) for item in items)
    manifest = {
        "schema_version": "map_component_media_manifest.v0.1",
        "media_pack_id": "map_component_media_pack_v0_1",
        "created_at": created_at,
        "source_style_pack_paths": [rel(path) for path in style_pack_paths],
        "public_url_prefix": "/assets/map_components",
        "media_layer": "reviewed_map_component_media",
        "usage_policy": USAGE_POLICY,
        "items": items,
        "summary": {
            "style_pack_count": len(style_packs),
            "node_count": len({item["node_id"] for item in items}),
            "component_count": len(items),
            "material_component_count": len(
                [item for item in items if item["source_binding"] == "material.component_ref"]
            ),
            "prefab_component_count": len(
                [item for item in items if item["source_binding"] == "prefab.visual_ref"]
            ),
            "roles": dict(sorted(roles.items())),
        },
        "validation": {
            "validator": "tools/media/validate_map_component_media_pack.py",
            "commands": [
                "python3 tools/media/validate_map_component_media_pack.py game_data/media/map_components/map_component_media_manifest.v0.1.json"
            ],
        },
    }
    write_json(manifest_path, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build deterministic reviewed map component SVG media and manifest."
    )
    parser.add_argument(
        "--style-pack",
        action="append",
        default=[],
        help="MapStylePack JSON path. Defaults to all examples/map_style_packs/*.json.",
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--created-at", default=now_iso())
    parser.add_argument(
        "--no-update-style-packs",
        action="store_true",
        help="Only build media/manifest; do not write component refs back to StylePacks.",
    )
    args = parser.parse_args()

    style_pack_paths = (
        [resolve_path(path) for path in args.style_pack]
        if args.style_pack
        else DEFAULT_STYLE_PACKS
    )
    output_dir = resolve_path(args.output_dir)
    manifest_path = resolve_path(args.manifest)
    manifest = build_pack(
        style_pack_paths,
        output_dir,
        manifest_path,
        created_at=args.created_at,
        update_style_packs=not args.no_update_style_packs,
    )
    print(f"OK: wrote {manifest_path}")
    print(f"- component_count: {manifest['summary']['component_count']}")
    print(f"- material_component_count: {manifest['summary']['material_component_count']}")
    print(f"- prefab_component_count: {manifest['summary']['prefab_component_count']}")
    print(f"- style_packs_updated: {not args.no_update_style_packs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
