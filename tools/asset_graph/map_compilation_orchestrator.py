"""One-command, resumable orchestration for map compilation.

The orchestrator owns no map semantics and performs no provider calls. It
connects the existing fact-source builders and records their outputs. Provider
media may be imported only through reviewed local source directories.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import build_layered_map_visual_package as layered_builder
    import map_compile_package as compile_package
    import map_runtime_package_v02 as runtime_v02
    import procedural_map_render_plan as render_plan
    import validate_layered_map_visual_package as layered_validator
except ModuleNotFoundError:  # pragma: no cover - package imports in tests.
    from tools.asset_graph import build_layered_map_visual_package as layered_builder
    from tools.asset_graph import map_compile_package as compile_package
    from tools.asset_graph import map_runtime_package_v02 as runtime_v02
    from tools.asset_graph import procedural_map_render_plan as render_plan
    from tools.asset_graph import validate_layered_map_visual_package as layered_validator


ROOT = Path(__file__).resolve().parents[2]
LAYERED_ROOT = ROOT / "game_data" / "media" / "layered_maps"
SCHEMAS = ROOT / "shared" / "schemas"
MEDIA_TOOLS = ROOT / "tools" / "media"
if str(MEDIA_TOOLS) not in sys.path:
    sys.path.insert(0, str(MEDIA_TOOLS))

import build_map_topology_control_sketch_pack as topology_sketches  # noqa: E402
import image_provider  # noqa: E402
import map_visual_job_queue  # noqa: E402
import map_visual_closed_loop  # noqa: E402
import vision_review  # noqa: E402

REPORT_SCHEMA_VERSION = "map_compilation_run_report.v0.1"
INPUT_SCHEMA_VERSION = "map_compilation_input.v0.1"


class MapCompilationError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise MapCompilationError(f"JSON root must be an object: {path}")
    return value


def _write(path: Path, value: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve(raw: str, *, base: Path = ROOT) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else base / path


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _artifact_ref(path: Path, repository_root: Path) -> str:
    try:
        return path.resolve().relative_to(repository_root.resolve()).as_posix()
    except ValueError:
        return _rel(path)


def _schema(name: str) -> dict[str, Any] | None:
    path = SCHEMAS / name
    return _load(path) if path.exists() else None


def _check_input(value: dict[str, Any], input_path: Path) -> tuple[Path, Path]:
    schema_errors = render_plan.validate_with_jsonschema(
        value, _schema("map_compilation_input.v0.1.schema.json")
    )
    if schema_errors:
        raise MapCompilationError(f"MapCompilationInput validation failed: {schema_errors[0]}")
    if value.get("schema_version") != INPUT_SCHEMA_VERSION:
        raise MapCompilationError(f"schema_version must be {INPUT_SCHEMA_VERSION}")
    battle_path = _resolve(str(value.get("battle_config_path") or ""), base=input_path.parent)
    style_path = _resolve(str(value.get("map_style_pack_path") or ""), base=input_path.parent)
    for path in (battle_path, style_path):
        if not path.is_file():
            raise MapCompilationError(f"map compilation input is missing: {path}")
    return battle_path, style_path


def _fingerprint(input_value: dict[str, Any], battle_path: Path, style_path: Path) -> str:
    stable = json.dumps(input_value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(stable.encode("utf-8"))
    digest.update(_sha(battle_path).encode("ascii"))
    digest.update(_sha(style_path).encode("ascii"))
    return digest.hexdigest()


def _output_ref(path: Path, kind: str) -> dict[str, Any]:
    return {"kind": kind, "path": _rel(path), "sha256": _sha(path)}


def _output_refs_are_current(refs: Any) -> bool:
    if not isinstance(refs, list) or not refs:
        return False
    for ref in refs:
        if not isinstance(ref, dict):
            return False
        path = _resolve(str(ref.get("path") or ""))
        if not path.is_file() or ref.get("sha256") != _sha(path):
            return False
    return True


def _stage(stage_id: str, started: float, outputs: list[Path], warnings: list[str] | None = None) -> dict[str, Any]:
    return {
        "stage_id": stage_id,
        "status": "passed",
        "duration_ms": int((time.monotonic() - started) * 1000),
        "output_paths": [_rel(path) for path in outputs],
        "warnings": warnings or [],
    }


def _visual_reference_manifest(layered: dict[str, Any]) -> dict[str, Any]:
    road = next(
        (item for item in layered.get("layers", []) if item.get("role") == "road_surface"),
        None,
    )
    if not isinstance(road, dict):
        raise MapCompilationError("layered package has no road_surface control layer")
    return {
        "schema_version": "map_visual_reference_pack.v0.1",
        "pack_id": f"map_visual_reference_{layered.get('node_id', 'map')}_v0_1",
        "source_map": str(layered.get("runtime_semantics_source", {}).get("path") or ""),
        "source_battle_config": str(layered.get("runtime_semantics_source", {}).get("path") or ""),
        "usage": {
            "authority": "runtime_derived_control_reference",
            "logic_source": "map_runtime_package_remains_authoritative",
            "next_step": "provider media requires review and promotion before import",
        },
        "items": [{
            "role": "battle_control_sketch",
            "url": road["url"],
            "local_path": road["local_path"],
            "width": road["width"],
            "height": road["height"],
            "sha256": road["sha256"],
            "authority": "reference_only",
            "review_status": "derived_from_runtime_truth",
            "player_visible_quality": "not_applicable",
            "logic_alignment_status": "passed",
            "source_kind": "procedural_runtime_control_layer",
        }],
    }


def _validate_style(style: dict[str, Any]) -> list[str]:
    return render_plan.validate_style_pack(style, _schema("map_style_pack.v0.1.schema.json"))


def _compose_visual_prompt(sections: dict[str, str]) -> str:
    order = ("subject", "environment", "style", "lighting", "composition", "quality")
    return " ".join(
        f"{key.replace('_', ' ').title()}: {sections[key].strip().rstrip('.')}."
        for key in order
        if sections.get(key, "").strip()
    )


def _identifier_terms(values: list[Any]) -> list[str]:
    return [
        str(value).replace("_", " ").strip()
        for value in values
        if str(value).strip()
    ]


def _material_terms(style: dict[str, Any], key: str) -> list[str]:
    items = style.get(key)
    if not isinstance(items, list):
        return []
    return _identifier_terms(
        [item.get("material_id") for item in items if isinstance(item, dict)]
    )


def _prefab_terms(style: dict[str, Any], key: str) -> list[str]:
    items = style.get(key)
    if not isinstance(items, list):
        return []
    values: list[Any] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        values.append(item.get("prefab_id"))
        visual_ref = item.get("visual_ref")
        if isinstance(visual_ref, dict):
            values.append(str(visual_ref.get("value") or "").rsplit(":", 1)[-1])
    return list(dict.fromkeys(_identifier_terms(values)))


def _visual_style_contract(style: dict[str, Any]) -> dict[str, Any]:
    lighting = style.get("lighting") if isinstance(style.get("lighting"), dict) else {}
    palette = style.get("palette") if isinstance(style.get("palette"), dict) else {}
    briefs = (
        style.get("visual_generation_briefs")
        if isinstance(style.get("visual_generation_briefs"), dict)
        else {}
    )
    return {
        "worldbook_id": str(style.get("worldbook_id") or "unknown_world"),
        "theme_terms": _identifier_terms(list(style.get("node_theme_tags") or [])),
        "terrain_material_terms": _material_terms(style, "terrain_materials"),
        "road_material_terms": _material_terms(style, "road_materials"),
        "lighting": {
            "time_of_day": str(lighting.get("time_of_day") or "neutral"),
            "contrast_policy": str(lighting.get("contrast_policy") or "gameplay_readable"),
            "shadow_policy": str(lighting.get("shadow_policy") or "soft"),
            "intensity": lighting.get("intensity"),
        },
        "palette": {str(key): str(value) for key, value in palette.items()},
        "generation_briefs": {
            str(key): str(value)
            for key, value in briefs.items()
            if isinstance(value, str) and value.strip()
        },
        "role_terms": {
            "build_slot_platform": _prefab_terms(style, "build_slot_platforms"),
            "objective_foundation": _prefab_terms(style, "objective_prefabs"),
            "spawn_marker": _prefab_terms(style, "spawn_prefabs"),
            "non_blocking_decoration": list(
                dict.fromkeys(
                    [
                        *_prefab_terms(style, "non_blocking_props"),
                        *_prefab_terms(style, "decorative_props"),
                    ]
                )
            ),
        },
    }


def _joined(values: Any, fallback: str) -> str:
    terms = [str(value) for value in values if str(value).strip()] if isinstance(values, list) else []
    return ", ".join(terms) or fallback


def _style_prompt_pack(
    runtime: dict[str, Any], style: dict[str, Any], *, runtime_path: Path
) -> dict[str, Any]:
    contract = _visual_style_contract(style)
    tags = contract["theme_terms"]
    palette = contract["palette"]
    lighting = contract["lighting"]
    terrain = _joined(contract["terrain_material_terms"], "worldbook terrain materials")
    topology = topology_sketches.runtime_summary(runtime)
    prompt_sections = {
        "subject": f"an uninhabited tower-defense environment plate for worldbook {contract['worldbook_id']}",
        "environment": f"quiet {terrain} ground and boundary structures shaped only by {_joined(tags, 'the supplied world themes')}",
        "style": f"polished production 2D game environment with semi-realistic material response, natural edges and restrained pseudo-3D depth; preserve exactly these world identity terms: {_joined(tags, 'the supplied world themes')}",
        "lighting": f"{lighting.get('time_of_day', 'night')} with {lighting.get('contrast_policy', 'clear gameplay readability')} and palette anchors {', '.join(str(value) for value in palette.values())}",
        "composition": "wide elevated three-quarter top-down view with the central playable area calm, open, and free of focal subjects",
        "quality": "production game background, crisp material separation, low grain, no narrative action or gameplay entities",
    }
    prompt_brief = _compose_visual_prompt(prompt_sections)
    return {
        "schema_version": "topology_constrained_map_prompt_pack.v0.1",
        "pack_id": f"map_prompt_{runtime.get('node_id', 'map')}_v0_1",
        "layout_plan_path": _rel(runtime_path),
        "status": "prompt_pack_ready",
        "summary": {
            "prompt_count": 1,
            "status_counts": {"prompt_ready": 1},
            "primary_prompt_count": 1,
            "fallback_prompt_count": 0,
        },
        "prompts": [
            {
                "node_id": runtime.get("node_id"),
                "status": "prompt_ready",
                "primary_use": "topology_constrained_generation",
                "topology_policy": "preserve_runtime_topology",
                "recommendation_source": "map_style_pack_and_runtime_truth",
                "runtime_package_path": _rel(runtime_path),
                "runtime_topology_summary": topology,
                "prompt_sections": prompt_sections,
                "prompt_brief": prompt_brief,
                "negative_constraints": [
                    "no_generic_western_castle_unless_worldbook_tags_request_it",
                    "no_baked_deployed_towers_or_enemies",
                    "no_baked_combat_effects_or_projectiles",
                    "no_people_humanoids_warriors_soldiers_or_character_silhouettes",
                    "no_weapons_battle_pose_combat_scene_or_story_action",
                    "no_magic_beams_auras_explosions_or_glowing_selection_rings",
                    "no_text_signs_talismans_letters_numbers_or_watermarks",
                    "no_ui_text_arrows_grid_or_route_markings",
                    "no_large_landmark_covering_runtime_combat_space",
                    "no_build_pad_or_objective_positions_invented_outside_reference",
                ],
                "required_review_gates": [
                    "worldbook_style_alignment",
                    "paths_visually_match_runtime_topology",
                    "objective_landmark_matches_runtime_policy",
                    "build_pads_distributed_near_routes",
                    "no_baked_units_towers_effects_or_ui",
                    "overlay_review_generated_before_promotion",
                ],
            }
        ],
        "policy": [
            "This prompt pack is compiled from MapStylePack and MapRuntimePackage, not handwritten per node.",
            "It is a provider handoff artifact and never a player runtime visual layer.",
            "Generated candidates must pass alignment, visual review, promotion, and local publication gates.",
        ],
    }


def _build_visual_handoff(
    runtime: dict[str, Any], style: dict[str, Any], *, runtime_path: Path,
    output_dir: Path,
) -> tuple[list[Path], dict[str, Any]]:
    handoff_dir = output_dir / "visual_handoff"
    control_dir = handoff_dir / "control"
    sketch = topology_sketches.build_sketch(runtime_path, control_dir, 1280, 720)
    control_pack = {
        "schema_version": topology_sketches.REPORT_VERSION,
        "pack_id": f"map_topology_{runtime.get('node_id', 'map')}_v0_1",
        "runtime_package_dir": _rel(runtime_path.parent),
        "output_dir": _rel(control_dir),
        "status": "control_sketches_ready_review_only",
        "summary": {
            "sketch_count": 1,
            "ready_count": 1,
            "blocked_count": 0,
            "status_counts": {"control_sketch_ready": 1},
            "target_size": {"width": 1280, "height": 720},
        },
        "sketches": [sketch],
        "policy": [
            "Control sketches are compile-time references only.",
            "Generated candidates must preserve MapRuntimePackage topology.",
            "No control sketch is a published player visual layer.",
        ],
    }
    control_pack_path = _write(
        handoff_dir / "map_topology_control_sketch_pack.v0.1.json", control_pack
    )
    prompt_pack = _style_prompt_pack(runtime, style, runtime_path=runtime_path)
    prompt_pack_path = _write(
        handoff_dir / "topology_constrained_map_prompt_pack.v0.1.json",
        prompt_pack,
    )
    common_negative = list(prompt_pack["prompts"][0]["negative_constraints"])
    contract = _visual_style_contract(style)
    terrain_materials = _joined(
        contract["terrain_material_terms"], "the supplied terrain materials"
    )
    road_materials = _joined(
        contract["road_material_terms"], "the supplied road materials"
    )
    lighting_contract = contract["lighting"]
    palette_contract = ", ".join(contract["palette"].values())
    role_terms = contract["role_terms"]
    generation_briefs = contract["generation_briefs"]
    # Rendering quality is engine-owned. World generation supplies culture and
    # materials, but cannot inject style labels that push providers toward flat
    # mobile-game or storybook illustration.
    rendering_style = (
        "high-end production game-environment rendering, semi-realistic physically coherent "
        "materials, nuanced roughness, controlled micro-detail, natural unoutlined edges, "
        "unified pseudo-3D scale and polished PC strategy-game screenshot finish"
    )
    world_motifs = _joined(contract["theme_terms"], "the supplied world identity")
    terrain_substrate_style = (
        f"{rendering_style}; "
        f"palette anchors {palette_contract or 'from the supplied style pack'}; "
        "do not depict any named landmark, architecture, settlement, road, bridge, platform, cliff wall, "
        "large vegetation cluster or complete scene; no cartoon, anime, cel shading, thick outlines or toy-like forms"
    )
    common_lighting = (
        f"{lighting_contract['time_of_day']} lighting, {lighting_contract['contrast_policy']} contrast, "
        f"{lighting_contract['shadow_policy']} shadows, readable midtones, no unrequested magical glow"
    )
    component_style = (
        "premium production game-asset rendering with semi-realistic readable materials, "
        "unified pseudo-3D scale and polished PC-game detail; "
        f"palette anchors {palette_contract or 'from the supplied style pack'}; "
        "render only the requested reusable asset, never a scene, setting, settlement, architecture group or diorama; "
        "no cartoon, anime, cel shading, thick outlines or toy-like forms"
    )
    component_negative_extra = [
        "no_building_clusters_complexes_or_cityscapes",
        "no_floating_islands_or_suspended_landmasses",
        "no_bridges_viaducts_or_elevated_connectors",
        "no_complete_scene_diorama_or_miniature_environment",
        "no_people_characters_or_humanoids",
    ]
    component_reference_paths: dict[str, Path] = {}
    for role in (
        "road_surface",
        "build_slot_platform",
        "objective_foundation",
        "spawn_marker",
        "non_blocking_decoration",
        "non_blocking_decoration_architecture",
        "non_blocking_decoration_natural",
        "non_blocking_decoration_debris",
        "non_blocking_decoration_prop",
    ):
        path = control_dir / f"{runtime.get('node_id', 'map')}.{role}.geometry_reference.png"
        topology_sketches.draw_component_geometry_reference(path, role)
        component_reference_paths[role] = path
    terrain_composition_reference = _resolve(
        str(sketch["terrain_composition_reference_path"])
    )
    style_reference_path = _resolve(
        str((style.get("source_refs") or {}).get("visual_style_reference_path") or "")
    )
    style_reference = (
        {
            "usage": "world_style_and_render_finish_reference_only",
            "local_path": _rel(style_reference_path),
            "sha256": _sha(style_reference_path),
        }
        if style_reference_path.is_file()
        else None
    )
    layer_specs = [
        {
            "role": "terrain_base",
            "output_kind": "tile_or_material_atlas",
            "output": {"width": 1024, "height": 1024, "size_tier": "1K", "ratio": "1:1", "transparent": False},
            "generation_mode": "text_to_image",
            "sections": {
                "subject": f"one seamless square PBR terrain albedo texture made only from {terrain_materials}",
                "environment": f"the same ground material fills every pixel with uniform texel density; use only fine diffuse surface variation from {generation_briefs.get('terrain_base', terrain_materials)}, such as small weathering, tiny cracks, moisture specks, dust or short flat moss; no object or patch may occupy more than eight percent of the tile",
                "style": f"photogrammetric high-end production game material rendering with semi-realistic physically coherent materials, controlled roughness and micro-detail, neutral albedo response and natural color variation; palette anchors {palette_contract or 'from the supplied style pack'}",
                "lighting": "flat neutral top-down albedo capture with even exposure and no baked directional light, cast shadow, ambient occlusion vignette, bloom or highlight",
                "composition": "strict orthographic macro material swatch filling all four edges at one uniform scale; no perspective, horizon, frame, border vegetation, wall, stairs, bridge, building, cliff, tree, rock pile, foreground prop, focal patch or recognizable symbol; absolutely no road, trail, route, lane, circle, ring, rune, deployment pad, socket, objective, spawn portal, unit or interaction marker",
                "quality": "sharp low-grain near-seamless terrain texture source for deterministic material-field composition, uniform edge statistics and no baked scene, large object or semantic marking",
            },
        },
        {
            "role": "road_surface", "output_kind": "tile_or_brush_atlas",
            "output": {"width": 1024, "height": 1024, "size_tier": "1K", "ratio": "1:1", "transparent": False},
            "generation_mode": "text_to_image",
            "sections": {
                "subject": f"a flat matte game-environment paving albedo material swatch made from {road_materials}, using restrained medium-value colors from {world_motifs}",
                "environment": "the requested road-surface material fills the entire rectangular image edge to edge; no white background, transparent margin, surrounding terrain, scenery, ground plate, decorative frame or border",
                "style": f"{component_style}; derive only world identity and material category from these road material ids: {road_materials}; render a weathered matte paving surface appropriate to the world, using muted charcoal, gray-green and restrained palette colors; do not copy any luminous or magical wording from upstream content; no cyan, bright blue, glow, radiant cracks or luminous seams; ignore any shape, winding, strip, endpoint or scene implied by the material ids",
                "lighting": "flat top-down albedo capture with neutral diffuse illumination, no cast shadows, perspective depth, dramatic highlights, bloom or emissive glow",
                "composition": "strict orthographic top-down macro material swatch, not an object; continuous paving texture reaches all four edges; uniform repeatable rhythm without a unique center, endpoint, bend, curb, border or perspective horizon",
                "quality": "sharp low-glare near-seamless texture source designed to be cropped to 2:1 and repeatedly filled along a deterministic vector path; medium contrast and matte surface are mandatory; this is a material sample, never a complete road object or scene",
            },
        },
        {
            "role": "build_slot_platform", "output_kind": "component_atlas",
            "output": {"width": 1024, "height": 1024, "size_tier": "1K", "ratio": "1:1", "transparent": True},
            "generation_mode": "image_to_image",
            "sections": {
                "subject": f"one empty low defense foundation for {_joined(role_terms['build_slot_platform'], 'the build-slot prefab contract')} in a {world_motifs} world; build an irregular low weathered charcoal-stone foundation with a broken octagonal silhouette, restrained shallow carvings, an empty dark inset center and a darker outer rim",
                "environment": "an isolated flat construction base on a completely plain pure-white studio background; no terrain, no ground plate, no scenery",
                "style": component_style,
                "lighting": "neutral soft asset lighting with no aura, selection glow or magical light",
                "composition": "consistent elevated three-quarter top-down pseudo-3D game asset view; exactly one centered object; compact oval footprint occupying between 18% and 38% of canvas area; at least 18% pure-white margin on every edge; no horizon, map or complete scene",
                "quality": "sharp clean high-contrast cutout source with a solid uninterrupted asymmetrical foundation silhouette, empty and unoccupied; gameplay readability overrides conflicting worldbook adjectives; explicitly forbidden: polished white jade, white or ivory main material, perfect circular disk, concentric rings, porcelain plate appearance, holes caused by background-colored material, towers, weapons, lanterns, characters, people, building clusters, bridges, floating islands, text, selection rings, scenery, frame, or any miniature scene",
            },
        },
        {
            "role": "objective_foundation", "output_kind": "component_atlas",
            "output": {"width": 1024, "height": 1024, "size_tier": "1K", "ratio": "1:1", "transparent": True},
            "generation_mode": "image_to_image",
            "sections": {
                "subject": f"one complete compact protected battlefield ward anchor for {_joined(role_terms['objective_foundation'], 'the objective prefab contract')} in a {world_motifs} world; build one short solid opaque weathered monolith secured by restrained world-appropriate braces on a low irregular footing; the vertical core is sealed, inert and completely solid",
                "environment": "isolated on a pure-white studio background; no terrain patch, mud puddle, floor tile, wooden deck, square base plate, surrounding scenery or detached props",
                "style": component_style,
                "lighting": "neutral soft asset lighting",
                "composition": "consistent elevated three-quarter top-down pseudo-3D game asset view; exactly one centered compact structure rooted on a low foundation; footprint occupies between 18% and 34% of canvas area and height stays below 48% of canvas; at least 18% pure-white margin on every edge; no horizon, map or complete scene",
                "quality": "clean cutout source with a clear bottom-center anchor; a visible compact opaque vertical core above the low base is mandatory; the object must read as a protected gameplay objective, not an empty pad; explicitly forbidden: glass, transparent chamber, crystal, flame, furnace, lamp, glow, smoke, machinery, dome, roof, doorway, platform deck, health bars, units, people, text, oversized monuments, scenery, frame or any miniature scene",
            },
        },
        {
            "role": "spawn_marker", "output_kind": "component_atlas",
            "output": {"width": 1024, "height": 1024, "size_tier": "1K", "ratio": "1:1", "transparent": True},
            "generation_mode": "image_to_image",
            "sections": {
                "subject": f"one restrained low-profile physical entrance marker based on {_joined(role_terms['spawn_marker'], 'the spawn prefab contract')}; motif vocabulary only: {generation_briefs.get('spawn_marker', world_motifs)}; depict inert material only, without portal activity or effects",
                "environment": "isolated on a pure-white studio background; no terrain, no ground plate, no scenery",
                "style": component_style,
                "lighting": "neutral dim asset lighting without magical glow",
                "composition": "consistent elevated three-quarter top-down pseudo-3D game asset view; exactly one centered low-profile object; footprint occupies between 8% and 22% of canvas area; at least 20% pure-white margin on every edge; no horizon, map or complete scene",
                "quality": "clean cutout source; explicitly forbidden: enemies, arrows, warning icons, people, characters, text, large effects, building clusters, bridges, floating islands, scenery, frame, or any miniature scene",
            },
        },
    ]
    decoration_terms = _joined(
        role_terms["non_blocking_decoration"],
        "the current world's border scenery vocabulary",
    )
    decoration_brief = str(
        generation_briefs.get("non_blocking_decoration") or decoration_terms
    )
    decoration_items = [
        item.strip(" ;,.")
        for item in re.findall(
            r"(?:^|\s)\d+\.\s*(.*?)(?=(?:\s+\d+\.)|$)",
            decoration_brief,
        )
        if item.strip(" ;,.")
    ]
    fallback_decoration_items = [
        "one short world-appropriate broken fence or wall fragment",
        "one broken world-appropriate wheel, beam or machine fragment",
        "one closed world-appropriate barrel, crate, urn or tied supply bundle",
        "one isolated world-appropriate dead stump, shrub, reed tuft or rock",
    ]
    decoration_items = (
        decoration_items[:4]
        if len(decoration_items) >= 4
        else fallback_decoration_items
    )
    # World prose often describes an object inside a scene (for example
    # "half-submerged"). Component compilation must preserve the object while
    # removing placement language that causes the provider to bake terrain into
    # the reusable sprite.
    decoration_items = [
        re.sub(
            r"\b(?:half[- ]submerged|partly[- ]submerged|half[- ]buried|partly[- ]buried)\b",
            "detached weathered",
            item,
            flags=re.IGNORECASE,
        )
        for item in decoration_items
    ]
    decoration_specs = {
        "non_blocking_decoration_architecture": (
            f"exactly one isolated reusable asset depicting {decoration_items[0]}; show that named object only, "
            "with no second prop category and no surrounding landscape"
        ),
        "non_blocking_decoration_natural": (
            f"exactly one isolated reusable asset depicting {decoration_items[3]}; show that named natural "
            "object only, with no fence, wheel, extra stone pile or surrounding landscape"
        ),
        "non_blocking_decoration_debris": (
            f"exactly one isolated reusable asset depicting {decoration_items[1]}; show that named broken object "
            "only; it rests directly on white with no rubble pile or manufactured base"
        ),
        "non_blocking_decoration_prop": (
            f"exactly one isolated reusable asset depicting {decoration_items[2]}; show that named object only; "
            "never add a wagon, cart, vehicle, building or gameplay device"
        ),
    }
    for role, subject in decoration_specs.items():
        layer_specs.append(
            {
                "role": role,
                "output_kind": "component_atlas",
                "output": {
                    "width": 1024,
                    "height": 1024,
                    "size_tier": "1K",
                    "ratio": "1:1",
                    "transparent": True,
                },
                "generation_mode": "text_to_image",
                "sections": {
                    "subject": subject,
                    "environment": (
                        "isolated on a completely flat pure-white studio background; no terrain patch, "
                        "square floor tile, shared base plate, surrounding scene or horizon"
                    ),
                    "style": component_style,
                    "lighting": "neutral soft asset lighting with a restrained built-in contact shadow only",
                    "composition": (
                        "consistent elevated three-quarter top-down pseudo-3D game asset view; exactly one "
                        "centered reusable object with a compact irregular silhouette; at least "
                        "16% pure-white margin on every edge; no circular disk, soil mound, puddle, floor tile, "
                        "platform, map, diorama or decorative frame"
                    ),
                    "quality": (
                        "high-end production game prop with physically coherent PBR material response, one clean silhouette, "
                        "a bottom-center anchor and no gameplay "
                        "semantics; explicitly forbidden: roads, paths, tower bases, deployment pads, objectives, "
                        "spawn portals, multiple object categories, scene composition, soil patch, shared base, units, "
                        "people, creatures, text, magic circles, glow, UI or large effects"
                    ),
                },
            }
        )
    requests = []
    component_roles = {
        "road_surface",
        "build_slot_platform",
        "objective_foundation",
        "spawn_marker",
        "non_blocking_decoration",
        "non_blocking_decoration_architecture",
        "non_blocking_decoration_natural",
        "non_blocking_decoration_debris",
        "non_blocking_decoration_prop",
    }
    for index, spec in enumerate(layer_specs, start=1):
        role = str(spec["role"])
        sections = dict(spec["sections"])
        role_contract = contract
        if role in {
            "road_surface",
            "build_slot_platform",
            "objective_foundation",
            *decoration_specs.keys(),
        }:
            role_contract = {
                **contract,
                "generation_briefs": {role: sections["subject"]},
            }
        negative = list(common_negative)
        if role in component_roles:
            negative = [*negative, *component_negative_extra]
        generation_reference_path: Path | None = None
        generation_reference_usage: str | None = None
        if spec["generation_mode"] == "image_to_image":
            if role == "terrain_base":
                generation_reference_path = terrain_composition_reference
                generation_reference_usage = (
                    "neutral_open_center_and_edge_framing_geometry_only"
                )
            else:
                generation_reference_path = component_reference_paths[role]
                generation_reference_usage = "single_component_geometry_and_occupancy_only"
        requests.append(
            {
                "request_id": f"map_layer_{runtime.get('node_id', 'map')}_{index:02d}_{role}",
                "role": role,
                "status": "ready_for_provider_or_manual_generation",
                "prompt_profile": "agnes_official_structured_prompt_v0_1",
                "prompt_sections": sections,
                "style_contract": role_contract,
                "prompt_brief": _compose_visual_prompt(sections),
                "negative_constraints": negative,
                "generation_mode": spec["generation_mode"],
                "image_profile_candidates": ["agnes_image_flash", "agnes_image_20_flash"],
                "output_contract": {"kind": spec["output_kind"], **spec["output"]},
                "generation_reference": (
                    {
                        "usage": generation_reference_usage,
                        "local_path": _rel(generation_reference_path),
                        "sha256": _sha(generation_reference_path),
                    }
                    if generation_reference_path is not None
                    else None
                ),
                "style_reference": style_reference if role == "terrain_base" else None,
                "control_reference": {
                    "usage": "reserved_zone_and_alignment_reference",
                    "local_path": sketch["control_sketch_png_path"],
                    "sha256": sketch["png_sha256"],
                    "semantic_authority": False,
                },
                "required_gates": [
                    "local_artifact_import",
                    "worldbook_style_review",
                    "cutout_or_texture_quality_review",
                    "runtime_overlay_alignment_review",
                    "explicit_promotion",
                ],
            }
        )
    request_pack = {
        "schema_version": "map_layered_visual_generation_request_pack.v0.1",
        "pack_id": f"map_layered_visual_requests_{runtime.get('node_id', 'map')}_v0_1",
        "status": "request_pack_ready_review_only",
        "node_id": runtime.get("node_id"),
        "worldbook_id": style.get("worldbook_id") or runtime.get("worldbook_id"),
        "source_refs": {
            "map_runtime_package": _rel(runtime_path),
            "map_style_pack": style.get("style_pack_id"),
            "topology_control_pack": _rel(control_pack_path),
            "prompt_pack": _rel(prompt_pack_path),
        },
        "requests": requests,
        "assembly_contract": {
            "semantic_authority": "map_runtime_package",
            "layer_order": [
                "terrain_base",
                "road_surface",
                "build_slot_platform",
                "objective_foundation",
                "spawn_marker",
                "non_blocking_decoration",
                "runtime_interaction_overlay",
            ],
            "forbid_image_to_semantic_inference": True,
            "unreviewed_media_player_visible": False,
        },
        "policy": [
            "This pack records the previously manual layered visual generation handoff.",
            "No request or provider output is a published player layer until review and promotion pass.",
            "Roads, slots, objectives, and spawns are placed from runtime anchors, never recovered from pixels.",
        ],
    }
    request_pack_path = _write(
        handoff_dir / "map_layered_visual_generation_request_pack.v0.1.json",
        request_pack,
    )
    generated_paths = [
        control_pack_path,
        prompt_pack_path,
        request_pack_path,
        _resolve(str(sketch["control_sketch_png_path"])),
        _resolve(str(sketch["control_sketch_svg_path"])),
        _resolve(str(sketch["terrain_composition_reference_path"])),
        *component_reference_paths.values(),
    ]
    return generated_paths, request_pack


def plan(input_path: Path, output_dir: Path, *, layered_root: Path | None = None) -> dict[str, Any]:
    value = _load(input_path)
    battle_path, style_path = _check_input(value, input_path)
    battle = _load(battle_path)
    style = _load(style_path)
    node_id = str(battle.get("node_id") or "")
    if not node_id or style.get("node_id") != node_id:
        raise MapCompilationError("battle config and MapStylePack must share a non-empty node_id")
    allowed_root = (layered_root or LAYERED_ROOT).resolve()
    try:
        output_dir.resolve().relative_to(allowed_root)
    except ValueError as exc:
        raise MapCompilationError(
            f"output directory must stay under {allowed_root}"
        ) from exc
    if output_dir.name != node_id:
        raise MapCompilationError(
            f"output directory name must match node_id '{node_id}': {output_dir}"
        )
    style_errors = _validate_style(style)
    if style_errors:
        raise MapCompilationError(f"MapStylePack validation failed: {style_errors[0]}")
    return {
        "schema_version": INPUT_SCHEMA_VERSION,
        "input_id": value.get("input_id"),
        "node_id": node_id,
        "worldbook_id": battle.get("worldbook_id"),
        "input_fingerprint": _fingerprint(value, battle_path, style_path),
        "battle_config_path": _rel(battle_path),
        "map_style_pack_path": _rel(style_path),
        "output_dir": _rel(output_dir),
        "stages": [
            "map_runtime_package",
            "procedural_map_render_plan",
            "semantic_visual_consistency",
            "visual_generation_handoff",
            "layered_map_visual_package",
            "map_compile_package",
        ],
        "provider_calls": 0,
        "provider_handoff_requested": bool(value.get("visual_generation", {}).get("provider_handoff")),
    }


def compile_map(
    input_path: Path,
    output_dir: Path,
    *,
    resume: bool = False,
    force: bool = False,
    live_visuals: bool = False,
    image_profile: str = "agnes_image_flash",
    dotenv_path: Path | None = None,
    visual_request_timeout: int = 240,
    visual_max_workers: int = 3,
    visual_review_profile: str = "agnes_multimodal_flash",
    visual_review_timeout: int = 180,
    visual_max_attempts: int = 2,
    layered_root: Path | None = None,
    artifact_repo_root: Path | None = None,
    public_prefix: str = "/assets/layered_maps",
) -> dict[str, Any]:
    allowed_root = layered_root or LAYERED_ROOT
    repository_root = artifact_repo_root or ROOT
    compile_plan = plan(input_path, output_dir, layered_root=allowed_root)
    report_path = output_dir / "map_compilation_run_report.v0.1.json"
    if resume and report_path.exists():
        previous = _load(report_path)
        refs = previous.get("output_refs") or []
        if (
            previous.get("input_fingerprint") == compile_plan["input_fingerprint"]
            and previous.get("status") == "completed"
            and _output_refs_are_current(refs)
        ):
            previous["resume"] = {"reused": True, "checked_at": _now()}
            return previous
    if output_dir.exists() and any(output_dir.iterdir()):
        if not force:
            raise MapCompilationError("output directory is not empty; use --resume or --force")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    value = _load(input_path)
    battle_path, style_path = _check_input(value, input_path)
    battle = _load(battle_path)
    style = _load(style_path)
    created_at = str(value.get("created_at") or _now())
    runtime_path = output_dir / "map_runtime_package.v0.2.json"
    render_path = output_dir / "procedural_map_render_plan.v0.1.json"
    semantic_report_path = output_dir / "semantic_visual_consistency_report.v0.1.json"
    layered_path = output_dir / "layered_map_visual_package.v0.1.json"
    visual_manifest_path = output_dir / "map_visual_reference_manifest.v0.1.json"
    compile_path = output_dir / "map_compile_package.v0.2.json"
    stages: list[dict[str, Any]] = []

    started = time.monotonic()
    runtime = runtime_v02.build_map_runtime_package_v02(
        battle,
        battle_config_path=_artifact_ref(battle_path, repository_root),
        package_id=f"map_pkg_{battle['node_id']}_v0_2",
        created_at=created_at,
    )
    errors = runtime_v02.validate_package_v02(runtime, _schema("map_runtime_package.v0.2.schema.json"))
    if errors:
        raise MapCompilationError(f"MapRuntimePackage validation failed: {errors[0]}")
    _write(runtime_path, runtime)
    stages.append(_stage("map_runtime_package", started, [runtime_path]))

    visual_generation = value.get("visual_generation") or {}
    visual_handoff_paths: list[Path] = []
    visual_handoff: dict[str, Any] | None = None
    visual_generation_report: dict[str, Any] | None = None
    visual_generation_paths: list[Path] = []
    if visual_generation.get("provider_handoff"):
        started = time.monotonic()
        visual_handoff_paths, visual_handoff = _build_visual_handoff(
            runtime,
            style,
            runtime_path=runtime_path,
            output_dir=output_dir,
        )
        stages.append(
            _stage(
                "visual_generation_handoff",
                started,
                visual_handoff_paths,
                ["provider_execution_and_candidate_review_are_pending"],
            )
        )
        if live_visuals:
            started = time.monotonic()
            profile = image_provider.PROFILES.get(image_profile)
            if profile is None:
                raise MapCompilationError(f"unknown image profile: {image_profile}")
            reviewer = vision_review.PROFILES.get(visual_review_profile)
            if reviewer is None:
                raise MapCompilationError(f"unknown visual review profile: {visual_review_profile}")
            env_path = dotenv_path or ROOT / ".env"
            image_provider.load_dotenv(env_path)
            vision_review.load_dotenv(env_path)
            request_pack_path = output_dir / "visual_handoff" / "map_layered_visual_generation_request_pack.v0.1.json"
            candidate_dir = output_dir / "visual_candidates"
            reviewed_dir = output_dir / "reviewed_visual_staging"
            visual_generation_report = map_visual_closed_loop.run_closed_loop(
                request_pack_path,
                visual_handoff,
                candidate_dir,
                reviewed_dir,
                profile,
                reviewer,
                max_attempts=visual_max_attempts,
                max_workers=visual_max_workers,
                generation_timeout=visual_request_timeout,
                review_timeout=visual_review_timeout,
                reviewed_fallback_dir=allowed_root / str(runtime.get("node_id") or ""),
                cache_dir=map_visual_closed_loop.resolve_cache_dir(),
            )
            closed_loop_report_path = Path(str(visual_generation_report["report_path"]))
            closed_loop_errors = render_plan.validate_with_jsonschema(
                _load(closed_loop_report_path),
                _schema("map_visual_closed_loop_report.v0.1.schema.json"),
            )
            if closed_loop_errors:
                raise MapCompilationError(
                    f"MapVisualClosedLoopReport validation failed: {closed_loop_errors[0]}"
                )
            visual_generation_paths = sorted(
                path for path in [*candidate_dir.rglob("*"), *reviewed_dir.rglob("*")] if path.is_file()
            )
            stages.append(
                _stage(
                    "visual_generate_review_repair_promote",
                    started,
                    visual_generation_paths,
                    []
                    if visual_generation_report.get("runtime_critical_roles_ready")
                    else ["visual_candidates_failed_review_after_retries; procedural_visual_fallback_used"],
                )
            )

    started = time.monotonic()
    render = render_plan.build_render_plan(
        runtime,
        style,
        map_runtime_package_path=_artifact_ref(runtime_path, repository_root),
        map_style_pack_path=_artifact_ref(style_path, repository_root),
        created_at=created_at,
    )
    semantic = render_plan.build_consistency_report(
        runtime,
        style,
        render,
        map_runtime_package_path=_artifact_ref(runtime_path, repository_root),
        map_style_pack_path=_artifact_ref(style_path, repository_root),
        procedural_map_render_plan_path=_artifact_ref(render_path, repository_root),
        created_at=created_at,
    )
    render_errors = render_plan.validate_render_plan(render, _schema("procedural_map_render_plan.v0.1.schema.json"))
    semantic_errors = render_plan.validate_consistency_report(
        semantic,
        _schema("semantic_visual_consistency_report.v0.1.schema.json"),
        render_plan=render,
        runtime_package=runtime,
    )
    if render_errors or semantic_errors:
        raise MapCompilationError(f"render plan validation failed: {(render_errors + semantic_errors)[0]}")
    _write(render_path, render)
    _write(semantic_report_path, semantic)
    stages.append(_stage("render_plan_and_semantic_consistency", started, [render_path, semantic_report_path]))

    started = time.monotonic()
    texture_dir = _resolve(str(visual_generation["reviewed_texture_source_dir"]), base=input_path.parent) if visual_generation.get("reviewed_texture_source_dir") else None
    backdrop_dir = _resolve(str(visual_generation["reviewed_backdrop_source_dir"]), base=input_path.parent) if visual_generation.get("reviewed_backdrop_source_dir") else None
    component_dir = _resolve(str(visual_generation["reviewed_component_source_dir"]), base=input_path.parent) if visual_generation.get("reviewed_component_source_dir") else None
    if visual_generation_report and visual_generation_report.get("runtime_critical_roles_ready"):
        texture_dir = Path(str(visual_generation_report["reviewed_texture_source_dir"]))
        reviewed_backdrop_dir = visual_generation_report.get("reviewed_backdrop_source_dir")
        backdrop_dir = Path(str(reviewed_backdrop_dir)) if reviewed_backdrop_dir else None
        reviewed_component_dir = visual_generation_report.get("reviewed_component_source_dir")
        component_dir = Path(str(reviewed_component_dir)) if reviewed_component_dir else None
    layered = layered_builder.build_package(
        runtime,
        style,
        render,
        runtime_path=runtime_path,
        style_path=style_path,
        render_plan_path=render_path,
        output_dir=output_dir,
        created_at=created_at,
        texture_source_dir=texture_dir,
        backdrop_source_dir=backdrop_dir,
        component_source_dir=component_dir,
        public_root=allowed_root,
        repository_root=repository_root,
        public_prefix=public_prefix,
        external_generation_call_count=(
            (
                int((visual_generation_report or {}).get("summary", {}).get("provider_call_count") or 0)
                + int((visual_generation_report or {}).get("summary", {}).get("cache_hit_count") or 0)
            )
            if (visual_generation_report or {}).get("runtime_critical_roles_ready")
            else 0
        ),
    )
    layered_errors = layered_validator.validate_manifest(
        layered,
        SCHEMAS / "layered_map_visual_package.v0.1.schema.json",
        repository_root=repository_root,
        media_root=allowed_root,
        public_prefix=public_prefix,
        validate_static_mount=repository_root.resolve() == ROOT.resolve(),
    )
    if layered_errors:
        raise MapCompilationError(f"LayeredMapVisualPackage validation failed: {layered_errors[0]}")
    warnings = []
    has_reviewed_terrain_visual = any(
        item.get("role") in {"reviewed_painted_backdrop", "terrain_tile"}
        and str(item.get("source_kind") or "").startswith(
            ("local_ai_", "compiled_reviewed_")
        )
        for item in layered.get("media_assets", [])
        if isinstance(item, dict)
    )
    if not has_reviewed_terrain_visual:
        warnings.append("reviewed_or_ai_painted_backdrop_missing; procedural_visual_is_fallback_only")
    stages.append(_stage("layered_map_visual_package", started, [layered_path], warnings))

    started = time.monotonic()
    visual_manifest = _visual_reference_manifest(layered)
    _write(visual_manifest_path, visual_manifest)
    compiled = compile_package.build_map_compile_package(
        runtime,
        map_runtime_package_path=_artifact_ref(runtime_path, repository_root),
        battle_config_path=_artifact_ref(battle_path, repository_root),
        visual_reference_manifest=visual_manifest,
        visual_reference_manifest_path=_artifact_ref(visual_manifest_path, repository_root),
        layered_visual_package=layered,
        layered_visual_package_path=_artifact_ref(layered_path, repository_root),
        created_at=created_at,
    )
    compile_errors = compile_package.validate_package(
        compiled, _schema("map_compile_package.v0.2.schema.json")
    )
    if compile_errors:
        raise MapCompilationError(f"MapCompilePackage validation failed: {compile_errors[0]}")
    _write(compile_path, compiled)
    stages.append(_stage("map_compile_package", started, [visual_manifest_path, compile_path]))

    background_job_path: Path | None = None
    if (
        visual_generation.get("provider_handoff")
        and visual_generation.get("background_execution", True)
        and not live_visuals
    ):
        background_job_path = map_visual_job_queue.enqueue_job(
            input_path=input_path,
            output_dir=output_dir,
            request_pack_path=(
                output_dir
                / "visual_handoff"
                / "map_layered_visual_generation_request_pack.v0.1.json"
            ),
            image_profile=image_profile,
            vision_profile=visual_review_profile,
            max_attempts=visual_max_attempts,
            max_workers=visual_max_workers,
            generation_timeout=visual_request_timeout,
            review_timeout=visual_review_timeout,
        )

    outputs = [
        runtime_path,
        *visual_handoff_paths,
        *visual_generation_paths,
        render_path,
        semantic_report_path,
        layered_path,
        visual_manifest_path,
        compile_path,
    ]
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "run_id": f"maprun_{compile_plan['input_fingerprint'][:20]}",
        "created_at": created_at,
        "completed_at": _now(),
        "status": "completed",
        "input_fingerprint": compile_plan["input_fingerprint"],
        "input_ref": _artifact_ref(input_path, repository_root),
        "worldbook_id": compile_plan["worldbook_id"],
        "node_id": compile_plan["node_id"],
        "stages": stages,
        "output_refs": [_output_ref(path, path.stem) for path in outputs],
        "provider_execution": {
            "call_count": (
                visual_generation_report.get("summary", {}).get("provider_call_count", 0)
                if visual_generation_report
                else 0
            ),
            "handoff_requested": bool(visual_generation.get("provider_handoff")),
            "handoff_status": (
                visual_handoff.get("status") if visual_handoff else "not_requested"
            ),
            "reviewed_local_media_imported": bool(texture_dir or backdrop_dir),
            "candidate_generation_status": (
                visual_generation_report.get("status")
                if visual_generation_report
                else "not_requested"
            ),
            "vision_review_call_count": (
                visual_generation_report.get("summary", {}).get("vision_review_call_count", 0)
                if visual_generation_report
                else 0
            ),
            "automatic_reviewed_staging_ready": bool(
                visual_generation_report
                and visual_generation_report.get("runtime_critical_roles_ready")
            ),
            "background_job_status": "pending" if background_job_path else "not_requested",
            "background_job_ref": (
                _artifact_ref(background_job_path, repository_root)
                if background_job_path
                else None
            ),
        },
        "quality": {
            "runtime_truth_preserved": True,
            "logic_visual_alignment": semantic.get("status"),
            "player_visual_status": compiled.get("validation_report", {}).get("gate_status"),
            "warnings": warnings,
        },
        "resume": {"reused": False, "checked_at": None},
    }
    report_errors = render_plan.validate_with_jsonschema(
        report, _schema("map_compilation_run_report.v0.1.schema.json")
    )
    if report_errors:
        raise MapCompilationError(f"MapCompilationRunReport validation failed: {report_errors[0]}")
    _write(report_path, report)
    return report


def apply_reviewed_visuals(
    input_path: Path,
    output_dir: Path,
    visual_report: dict[str, Any],
    *,
    layered_root: Path | None = None,
    artifact_repo_root: Path | None = None,
    public_prefix: str = "/assets/layered_maps",
) -> dict[str, Any]:
    """Rebuild presentation artifacts after the background visual gate passes."""
    if not visual_report.get("runtime_critical_roles_ready"):
        raise MapCompilationError("reviewed critical visual roles are not ready")
    value = _load(input_path)
    battle_path, style_path = _check_input(value, input_path)
    style = _load(style_path)
    runtime_path = output_dir / "map_runtime_package.v0.2.json"
    render_path = output_dir / "procedural_map_render_plan.v0.1.json"
    layered_path = output_dir / "layered_map_visual_package.v0.1.json"
    visual_manifest_path = output_dir / "map_visual_reference_manifest.v0.1.json"
    compile_path = output_dir / "map_compile_package.v0.2.json"
    report_path = output_dir / "map_compilation_run_report.v0.1.json"
    runtime = _load(runtime_path)
    render = _load(render_path)
    created_at = str(value.get("created_at") or _now())
    allowed_root = layered_root or output_dir.parent
    repository_root = artifact_repo_root or ROOT
    started = time.monotonic()

    layered = layered_builder.build_package(
        runtime,
        style,
        render,
        runtime_path=runtime_path,
        style_path=style_path,
        render_plan_path=render_path,
        output_dir=output_dir,
        created_at=created_at,
        texture_source_dir=Path(str(visual_report["reviewed_texture_source_dir"])),
        backdrop_source_dir=(
            Path(str(visual_report["reviewed_backdrop_source_dir"]))
            if visual_report.get("reviewed_backdrop_source_dir")
            else None
        ),
        component_source_dir=(
            Path(str(visual_report["reviewed_component_source_dir"]))
            if visual_report.get("reviewed_component_source_dir")
            else None
        ),
        public_root=allowed_root,
        repository_root=repository_root,
        public_prefix=public_prefix,
        external_generation_call_count=(
            int(visual_report.get("summary", {}).get("provider_call_count") or 0)
            + int(visual_report.get("summary", {}).get("cache_hit_count") or 0)
        ),
    )
    layered_errors = layered_validator.validate_manifest(
        layered,
        SCHEMAS / "layered_map_visual_package.v0.1.schema.json",
        repository_root=repository_root,
        media_root=allowed_root,
        public_prefix=public_prefix,
        validate_static_mount=repository_root.resolve() == ROOT.resolve(),
    )
    if layered_errors:
        raise MapCompilationError(f"LayeredMapVisualPackage validation failed: {layered_errors[0]}")
    visual_manifest = _visual_reference_manifest(layered)
    _write(visual_manifest_path, visual_manifest)
    compiled = compile_package.build_map_compile_package(
        runtime,
        map_runtime_package_path=_artifact_ref(runtime_path, repository_root),
        battle_config_path=_artifact_ref(battle_path, repository_root),
        visual_reference_manifest=visual_manifest,
        visual_reference_manifest_path=_artifact_ref(
            visual_manifest_path, repository_root
        ),
        layered_visual_package=layered,
        layered_visual_package_path=_artifact_ref(layered_path, repository_root),
        created_at=created_at,
    )
    compile_errors = compile_package.validate_package(
        compiled, _schema("map_compile_package.v0.2.schema.json")
    )
    if compile_errors:
        raise MapCompilationError(f"MapCompilePackage validation failed: {compile_errors[0]}")
    _write(compile_path, compiled)

    report = _load(report_path)
    report["completed_at"] = _now()
    report["stages"].append(
        _stage(
            "background_visual_activation",
            started,
            [layered_path, visual_manifest_path, compile_path],
        )
    )
    provider_execution = report.setdefault("provider_execution", {})
    provider_execution.update(
        {
            "call_count": visual_report.get("summary", {}).get("provider_call_count", 0),
            "vision_review_call_count": visual_report.get("summary", {}).get(
                "vision_review_call_count", 0
            ),
            "candidate_generation_status": visual_report.get("status"),
            "reviewed_local_media_imported": True,
            "automatic_reviewed_staging_ready": True,
            "background_job_status": "completed",
        }
    )
    report["quality"]["player_visual_status"] = compiled.get("validation_report", {}).get(
        "gate_status"
    )
    report["quality"]["warnings"] = [
        warning
        for warning in report.get("quality", {}).get("warnings", [])
        if warning
        != "reviewed_or_ai_painted_backdrop_missing; procedural_visual_is_fallback_only"
    ]
    refreshed = {
        str(path.resolve()): _output_ref(path, path.stem)
        for path in (layered_path, visual_manifest_path, compile_path)
    }
    report["output_refs"] = [
        refreshed.get(str(_resolve(str(item.get("path") or "")).resolve()), item)
        if isinstance(item, dict)
        else item
        for item in report.get("output_refs", [])
    ]
    report_errors = render_plan.validate_with_jsonschema(
        report, _schema("map_compilation_run_report.v0.1.schema.json")
    )
    if report_errors:
        raise MapCompilationError(f"MapCompilationRunReport validation failed: {report_errors[0]}")
    _write(report_path, report)
    return report
