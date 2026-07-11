"""One-command, resumable orchestration for map compilation.

The orchestrator owns no map semantics and performs no provider calls. It
connects the existing fact-source builders and records their outputs. Provider
media may be imported only through reviewed local source directories.
"""

from __future__ import annotations

import hashlib
import json
import shutil
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
    visual_generation = value.get("visual_generation") or {}
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

    outputs = [runtime_path, render_path, semantic_report_path, layered_path, visual_manifest_path, compile_path]
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
