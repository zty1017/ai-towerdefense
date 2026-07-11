"""One-command, resumable orchestration for map compilation.

The orchestrator owns no map semantics and performs no provider calls. It
connects the existing fact-source builders and records their outputs. Provider
media may be imported only through reviewed local source directories.
"""

from __future__ import annotations

import hashlib
import json
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


def _style_prompt_pack(
    runtime: dict[str, Any], style: dict[str, Any], *, runtime_path: Path
) -> dict[str, Any]:
    tags = [str(item).replace("_", " ") for item in style.get("node_theme_tags", [])]
    palette = style.get("palette") if isinstance(style.get("palette"), dict) else {}
    lighting = style.get("lighting") if isinstance(style.get("lighting"), dict) else {}
    topology = topology_sketches.runtime_summary(runtime)
    prompt_brief = " ".join(
        [
            "EMPTY ENVIRONMENT CLEAN PLATE for a polished 2D or pseudo-3D strategy game, elevated three-quarter top-down camera.",
            "This is an environment asset sheet with no narrative action and no gameplay entities.",
            f"Worldbook: {style.get('worldbook_id') or runtime.get('worldbook_id')}.",
            f"Scene direction: {', '.join(tags) or 'worldbook-consistent frontier environment'}.",
            f"Lighting: {lighting.get('time_of_day', 'night')}, {lighting.get('contrast_policy', 'high gameplay readability')}.",
            f"Palette anchors: {', '.join(str(value) for value in palette.values())}.",
            "Use Chinese-inspired architecture and material language when the scene tags request it; do not drift into generic western fantasy.",
            "Keep all playable space empty, calm, and readable; interactive content will be composed later by deterministic runtime layers.",
        ]
    )
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
    common_prompt = str(prompt_pack["prompts"][0]["prompt_brief"])
    common_negative = list(prompt_pack["prompts"][0]["negative_constraints"])
    layer_specs = [
        (
            "terrain_base",
            "full_frame_backdrop",
            {"width": 1280, "height": 720, "transparent": False},
            "PRIMARY TASK: create one wide EMPTY TERRAIN CLEAN PLATE. Paint only natural ground materials, quiet boundary architecture around the outer edges, sparse vegetation, distant mountains, and restrained atmosphere. Keep the central seventy percent open and low-detail. Do not paint roads, trails, paths, platforms, pads, objectives, monuments, portals, lamps, people, creatures, weapons, action, magic, or combat effects anywhere.",
        ),
        (
            "road_surface",
            "tile_or_brush_atlas",
            {"width": 1024, "height": 1024, "transparent": True},
            "PRIMARY TASK: create one isolated reusable old Chinese post-road material strip with soft dirt-and-stone edges, seen from an elevated top-down angle, centered on a completely plain pure-white background. Asset cutout source only. No complete map, landscape, buildings, lamps, characters, symbols, arrows, text, glow, shadowy scenery, or decorative frame.",
        ),
        (
            "build_slot_platform",
            "component_atlas",
            {"width": 1024, "height": 1024, "transparent": True},
            "PRIMARY TASK: create one single empty low circular stone-and-timber deployment foundation, elevated top-down view, centered on a completely plain pure-white background. Asset cutout source only. It must be flat, unoccupied, understated, and contain no building, tower, weapon, lantern, character, text, aura, ring, selection glow, scenery, or frame.",
        ),
        (
            "objective_foundation",
            "component_atlas",
            {"width": 1024, "height": 1024, "transparent": True},
            "Create compact protected-objective foundations or structures with a clear bottom-center anchor. Do not include runtime health bars, halos, units, text, or oversized monuments.",
        ),
        (
            "spawn_marker",
            "component_atlas",
            {"width": 1024, "height": 1024, "transparent": True},
            "Create restrained enemy entrance terrain markers that remain secondary to the battlefield. No enemies, arrows, warning icons, text, or large magical glow baked into the sprite.",
        ),
        (
            "non_blocking_decoration",
            "component_atlas",
            {"width": 1024, "height": 1024, "transparent": True},
            "Create small non-blocking edge decorations and material props. Keep silhouettes compact and avoid anything that reads as a unit, tower, objective, projectile, or UI icon.",
        ),
    ]
    requests = []
    for index, (role, output_kind, dimensions, role_prompt) in enumerate(layer_specs, start=1):
        requests.append(
            {
                "request_id": f"map_layer_{runtime.get('node_id', 'map')}_{index:02d}_{role}",
                "role": role,
                "status": "ready_for_provider_or_manual_generation",
                "prompt_profile": "worldbook_style_plus_runtime_topology_v0_1",
                "prompt_brief": f"{role_prompt} Art direction: {common_prompt}",
                "negative_constraints": common_negative,
                "output_contract": {"kind": output_kind, **dimensions},
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
    ]
    return generated_paths, request_pack


def plan(input_path: Path, output_dir: Path) -> dict[str, Any]:
    value = _load(input_path)
    battle_path, style_path = _check_input(value, input_path)
    battle = _load(battle_path)
    style = _load(style_path)
    node_id = str(battle.get("node_id") or "")
    if not node_id or style.get("node_id") != node_id:
        raise MapCompilationError("battle config and MapStylePack must share a non-empty node_id")
    expected = (LAYERED_ROOT / node_id).resolve()
    if output_dir.resolve() != expected:
        raise MapCompilationError(f"output directory must be {expected}")
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
) -> dict[str, Any]:
    compile_plan = plan(input_path, output_dir)
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
        battle_config_path=_rel(battle_path),
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

    started = time.monotonic()
    render = render_plan.build_render_plan(
        runtime,
        style,
        map_runtime_package_path=_rel(runtime_path),
        map_style_pack_path=_rel(style_path),
        created_at=created_at,
    )
    semantic = render_plan.build_consistency_report(
        runtime,
        style,
        render,
        map_runtime_package_path=_rel(runtime_path),
        map_style_pack_path=_rel(style_path),
        procedural_map_render_plan_path=_rel(render_path),
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
    )
    layered_errors = layered_validator.validate_manifest(
        layered, SCHEMAS / "layered_map_visual_package.v0.1.schema.json"
    )
    if layered_errors:
        raise MapCompilationError(f"LayeredMapVisualPackage validation failed: {layered_errors[0]}")
    warnings = []
    if not any(item.get("role") == "reviewed_painted_backdrop" for item in layered.get("media_assets", [])):
        warnings.append("reviewed_or_ai_painted_backdrop_missing; procedural_visual_is_fallback_only")
    stages.append(_stage("layered_map_visual_package", started, [layered_path], warnings))

    started = time.monotonic()
    visual_manifest = _visual_reference_manifest(layered)
    _write(visual_manifest_path, visual_manifest)
    compiled = compile_package.build_map_compile_package(
        runtime,
        map_runtime_package_path=_rel(runtime_path),
        battle_config_path=_rel(battle_path),
        visual_reference_manifest=visual_manifest,
        visual_reference_manifest_path=_rel(visual_manifest_path),
        layered_visual_package=layered,
        layered_visual_package_path=_rel(layered_path),
        created_at=created_at,
    )
    compile_errors = compile_package.validate_package(
        compiled, _schema("map_compile_package.v0.2.schema.json")
    )
    if compile_errors:
        raise MapCompilationError(f"MapCompilePackage validation failed: {compile_errors[0]}")
    _write(compile_path, compiled)
    stages.append(_stage("map_compile_package", started, [visual_manifest_path, compile_path]))

    outputs = [
        runtime_path,
        *visual_handoff_paths,
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
        "input_ref": _rel(input_path),
        "worldbook_id": compile_plan["worldbook_id"],
        "node_id": compile_plan["node_id"],
        "stages": stages,
        "output_refs": [_output_ref(path, path.stem) for path in outputs],
        "provider_execution": {
            "call_count": 0,
            "handoff_requested": bool(visual_generation.get("provider_handoff")),
            "handoff_status": (
                visual_handoff.get("status") if visual_handoff else "not_requested"
            ),
            "reviewed_local_media_imported": bool(texture_dir or backdrop_dir),
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
