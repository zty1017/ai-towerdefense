"""Builder and validator for MapCompilePackage v0.2.

MapCompilePackage is compile-time evidence for map-as-compiled-object. It does
not replace MapRuntimePackage. Runtime gameplay truth stays in
MapRuntimePackage; this package records how logical map data, control images,
painted visual candidates, alignment, and visual quality gates relate.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any


FORBIDDEN_FIELDS = frozenset(
    {
        "provider",
        "model",
        "raw_prompt",
        "full_trace",
        "raw_json",
        "api_key",
        "secret",
        "unreviewed_content",
    }
)
FORBIDDEN_URL_MARKERS = ("http://", "https://", "://")
CONTROL_ROLES = frozenset(
    {"strategic_control_sketch", "battle_control_sketch", "battle_reference_board"}
)
PUBLISHED_ROLES = frozenset({"battle_runtime_background", "painted_visual_layer"})
VISUAL_ROLES = CONTROL_ROLES | PUBLISHED_ROLES
QUALITY_STATUSES = frozenset({"passed", "warning", "failed"})

DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def scan_forbidden_fields(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key in FORBIDDEN_FIELDS:
                errors.append(f"forbidden field '{child_path}' is not allowed")
            scan_forbidden_fields(child, child_path, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_forbidden_fields(child, f"{path}[{index}]", errors)


def scan_external_urls(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            scan_external_urls(child, child_path, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_external_urls(child, f"{path}[{index}]", errors)
    elif isinstance(value, str):
        lowered = value.lower()
        if any(marker in lowered for marker in FORBIDDEN_URL_MARKERS):
            errors.append(f"{path}={value!r} must not contain external URL markers")


def _require_object(value: Any, path: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{path} must be an object")
        return {}
    return value


def _require_array(value: Any, path: str, errors: list[str], *, minimum: int = 0) -> list[Any]:
    if not isinstance(value, list):
        errors.append(f"{path} must be an array")
        return []
    if len(value) < minimum:
        errors.append(f"{path} must contain at least {minimum} item(s)")
    return value


def _require_string(value: Any, path: str, errors: list[str]) -> str:
    if not isinstance(value, str) or not value:
        errors.append(f"{path} must be a non-empty string")
        return ""
    return value


def _require_int(value: Any, path: str, errors: list[str], *, minimum: int | None = None) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        errors.append(f"{path} must be an integer")
        return 0
    if minimum is not None and value < minimum:
        errors.append(f"{path} must be >= {minimum}")
    return value


def _point_key(raw: Any) -> tuple[int, int]:
    if not isinstance(raw, dict):
        return (0, 0)
    return (int(raw.get("x", 0)), int(raw.get("y", 0)))


def _visual_artifact(raw: dict[str, Any]) -> dict[str, Any]:
    role = str(raw.get("role", ""))
    authority = str(raw.get("authority") or "reference_only")
    if role in PUBLISHED_ROLES and authority == "reference_only":
        authority = "published_visual_layer"
    return {
        "artifact_id": f"artifact_{role}",
        "role": role,
        "url": str(raw.get("url", "")),
        "local_path": str(raw.get("local_path", "")),
        "width": int(raw.get("width", 1)),
        "height": int(raw.get("height", 1)),
        "sha256": str(raw.get("sha256", "")),
        "authority": authority,
    }


def _iter_manifest_artifacts(visual_manifest: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(visual_manifest, dict):
        return []
    artifacts: list[dict[str, Any]] = []
    for item in visual_manifest.get("items", []):
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", ""))
        if role in VISUAL_ROLES:
            artifacts.append(_visual_artifact(item))
    return artifacts


def _first_artifact_by_role(artifacts: list[dict[str, Any]], roles: set[str] | frozenset[str]) -> dict[str, Any] | None:
    for artifact in artifacts:
        if artifact.get("role") in roles:
            return artifact
    return None


def _published_source_kinds(visual_manifest: dict[str, Any] | None) -> set[str]:
    if not isinstance(visual_manifest, dict):
        return set()
    source_kinds: set[str] = set()
    for item in visual_manifest.get("items", []):
        if not isinstance(item, dict):
            continue
        if item.get("role") in PUBLISHED_ROLES:
            source_kinds.add(str(item.get("source_kind") or ""))
    return source_kinds


def _project_cell_to_pixel(
    point: dict[str, Any],
    grid: dict[str, Any],
    reference_size: dict[str, int],
) -> dict[str, int]:
    """Match the frontend's pseudo-isometric base projection for checkpoints."""
    width = int(reference_size.get("width", 1280))
    height = int(reference_size.get("height", 720))
    grid_w = max(1, int(grid.get("width_cells", 16)))
    grid_h = max(1, int(grid.get("height_cells", 9)))
    x = int(point.get("x", 0))
    y = int(point.get("y", 0))

    span = max(1, grid_w + grid_h)
    tile_w = min(((width - 80) * 2) / span, ((height - 110) * 4) / span)
    tile_w = max(38, min(112, tile_w))
    tile_h = tile_w * 0.52

    def raw_project(px: int, py: int) -> tuple[float, float]:
        return (px - py) * (tile_w / 2), (px + py) * (tile_h / 2)

    corners = [
        raw_project(0, 0),
        raw_project(grid_w - 1, 0),
        raw_project(0, grid_h - 1),
        raw_project(grid_w - 1, grid_h - 1),
    ]
    min_x = min(p[0] for p in corners)
    max_x = max(p[0] for p in corners)
    min_y = min(p[1] for p in corners)
    max_y = max(p[1] for p in corners)
    offset_x = (width - (max_x - min_x)) / 2 - min_x
    offset_y = (height - (max_y - min_y)) / 2 - min_y + 6
    raw_x, raw_y = raw_project(x, y)
    px = raw_x + offset_x
    py = raw_y + offset_y
    return {"x": int(round(px)), "y": int(round(py))}


def _alignment_checkpoints(
    runtime_package: dict[str, Any],
    reference_size: dict[str, int],
    *,
    max_points: int = 8,
) -> list[dict[str, Any]]:
    grid = dict(runtime_package.get("grid") or {})
    checkpoints: list[dict[str, Any]] = []

    for route in runtime_package.get("path_routes", []):
        if not isinstance(route, dict):
            continue
        waypoints = [p for p in route.get("waypoints", []) if isinstance(p, dict)]
        if not waypoints:
            continue
        selected = [
            ("route_start", waypoints[0]),
            ("route_end", waypoints[-1]),
        ]
        if len(waypoints) > 2:
            selected.insert(1, ("route_turn", waypoints[len(waypoints) // 2]))
        for kind, point in selected:
            checkpoints.append(
                {
                    "checkpoint_id": f"{kind}_{len(checkpoints) + 1:02d}",
                    "kind": kind,
                    "logic_position": {"x": int(point["x"]), "y": int(point["y"])},
                    "expected_pixel": _project_cell_to_pixel(point, grid, reference_size),
                }
            )
            if len(checkpoints) >= max_points:
                return checkpoints

    core = ((runtime_package.get("objectives") or {}).get("core_target") or {}).get("position")
    if isinstance(core, dict):
        checkpoints.append(
            {
                "checkpoint_id": f"objective_{len(checkpoints) + 1:02d}",
                "kind": "objective",
                "logic_position": {"x": int(core.get("x", 0)), "y": int(core.get("y", 0))},
                "expected_pixel": _project_cell_to_pixel(core, grid, reference_size),
            }
        )

    for slot in runtime_package.get("build_slots", []):
        if len(checkpoints) >= max_points:
            break
        if not isinstance(slot, dict) or not isinstance(slot.get("position"), dict):
            continue
        point = slot["position"]
        checkpoints.append(
            {
                "checkpoint_id": f"build_slot_{len(checkpoints) + 1:02d}",
                "kind": "build_slot",
                "logic_position": {"x": int(point.get("x", 0)), "y": int(point.get("y", 0))},
                "expected_pixel": _project_cell_to_pixel(point, grid, reference_size),
            }
        )

    return checkpoints


def build_map_compile_package(
    runtime_package: dict[str, Any],
    *,
    map_runtime_package_path: str,
    battle_config_path: str,
    visual_reference_manifest: dict[str, Any] | None,
    visual_reference_manifest_path: str,
    package_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    artifacts = _iter_manifest_artifacts(visual_reference_manifest)
    control_artifacts = [item for item in artifacts if item.get("role") in CONTROL_ROLES]
    painted_artifact = _first_artifact_by_role(artifacts, PUBLISHED_ROLES)
    published_source_kinds = _published_source_kinds(visual_reference_manifest)
    logic_aligned_visual = bool(published_source_kinds & {
        "deterministic_logic_aligned_runtime_background",
        "certified_logic_aligned_runtime_background",
        "human_reviewed_painted_visual_runtime_overlay",
    })
    reference_size = {
        "width": int((painted_artifact or {}).get("width") or 1280),
        "height": int((painted_artifact or {}).get("height") or 720),
    }
    objectives = runtime_package.get("objectives") or {}
    optional_targets = objectives.get("optional_targets") if isinstance(objectives, dict) else []
    objective_count = 1 + (len(optional_targets) if isinstance(optional_targets, list) else 0)

    quality_gates = [
        {
            "gate_id": "runtime_truth_source",
            "status": "passed",
            "summary": "Routes, build slots, objectives, and spawn points are copied from MapRuntimePackage, not inferred from pixels.",
        },
        {
            "gate_id": "control_layers_not_player_default",
            "status": "passed",
            "summary": "Control sketches and reference boards are reference_only and must remain debug/evidence material.",
        },
        {
            "gate_id": "published_visual_layer_present",
            "status": "passed" if painted_artifact else "warning",
            "summary": "A player-facing painted background exists." if painted_artifact else "No player-facing painted background is available; frontend must keep a safe fallback.",
        },
        {
            "gate_id": "published_visual_logic_aligned",
            "status": "passed" if logic_aligned_visual else "warning",
            "summary": "The published background is generated from the same logical projection as the runtime overlay."
            if logic_aligned_visual
            else "Published background exists, but its source does not prove logic alignment; runtime overlay correction is required.",
        },
        {
            "gate_id": "no_ui_text_enemy_tower_in_painted_map",
            "status": "warning",
            "summary": "MVP records this as a required visual review gate; automated computer-vision enforcement is not yet enabled.",
        },
        {
            "gate_id": "alignment_requires_runtime_overlay",
            "status": "passed" if logic_aligned_visual else "warning",
            "summary": "Deterministic published background uses the runtime projection; subtle overlays are cosmetic rather than corrective."
            if logic_aligned_visual
            else "Pixel alignment is represented by checkpoints; subtle runtime overlays remain required until a stronger repaint/alignment checker lands.",
        },
    ]

    return {
        "schema_version": "map_compile_package.v0.2",
        "package_id": package_id or f"map_compile_{runtime_package.get('node_id', 'unknown')}_v0_2",
        "worldbook_id": str(runtime_package.get("worldbook_id", "")),
        "node_id": str(runtime_package.get("node_id", "")),
        "created_at": created_at or now_iso(),
        "source_refs": {
            "battle_config_path": battle_config_path,
            "map_runtime_package_path": map_runtime_package_path,
            "visual_reference_manifest_path": visual_reference_manifest_path,
            "logic_authority": "map_runtime_package",
        },
        "logical_map_layer": {
            "authority": "runtime_truth",
            "grid": runtime_package.get("grid", {}),
            "path_route_count": len(runtime_package.get("path_routes", [])),
            "build_slot_count": len(runtime_package.get("build_slots", [])),
            "objective_count": objective_count,
            "spawn_point_count": len(runtime_package.get("spawn_points", [])),
            "path_routes": runtime_package.get("path_routes", []),
            "build_slots": runtime_package.get("build_slots", []),
            "objectives": objectives,
            "spawn_points": runtime_package.get("spawn_points", []),
        },
        "control_layer": {
            "authority": "reference_only",
            "artifacts": control_artifacts,
            "model_instruction_boundary": [
                "Control images may guide composition but cannot define gameplay routes or build slots.",
                "Generated map backgrounds must contain no UI, no text, no enemies, no deployed towers, and no obvious board frame.",
                "Paths, tower bases, objectives, and threat entrances should be naturally embedded in the worldbook visual style.",
            ],
        },
        "painted_visual_layer": {
            "authority": str((painted_artifact or {}).get("authority") or "missing"),
            "status": "published" if painted_artifact else "missing",
            "artifact": painted_artifact,
            "visual_constraints": [
                "player-facing map only",
                "no tactical UI baked into the image",
                "no monsters or towers baked into the background",
                "path and tower bases readable but diegetic",
                "worldbook style must be visible",
            ],
        },
        "alignment_layer": {
            "authority": "runtime_overlay_alignment",
            "reference_size": reference_size,
            "projection": str((runtime_package.get("grid") or {}).get("projection") or "pseudo3d_oblique"),
            "coordinate_mapping": "map_runtime_cell_to_visual_plane",
            "max_pixel_error": 24 if logic_aligned_visual else 48,
            "overlay_correction_policy": "subtle_runtime_overlay",
            "alignment_status": "passed" if logic_aligned_visual else "needs_overlay_correction",
            "checkpoints": _alignment_checkpoints(runtime_package, reference_size),
        },
        "quality_gates": quality_gates,
        "export_refs": {
            "map_runtime_package_path": map_runtime_package_path,
            "frontend_default_visual_role": "battle_runtime_background" if painted_artifact else "painted_visual_layer",
        },
        "validation_report": {
            "gate_status": "warning" if any(gate.get("status") == "warning" for gate in quality_gates) else "passed",
            "runtime_truth_preserved": True,
            "player_visual_safe": bool(painted_artifact and logic_aligned_visual),
            "gates": quality_gates,
        },
    }


def _validate_visual_artifact(raw: Any, path: str, errors: list[str]) -> dict[str, Any]:
    artifact = _require_object(raw, path, errors)
    if not artifact:
        return {}
    role = _require_string(artifact.get("role"), f"{path}.role", errors)
    if role and role not in VISUAL_ROLES:
        errors.append(f"{path}.role={role!r} is not allowed")
    url = _require_string(artifact.get("url"), f"{path}.url", errors)
    if url and not url.startswith("/assets/map_visual_reference/"):
        errors.append(f"{path}.url must start with /assets/map_visual_reference/")
    _require_string(artifact.get("local_path"), f"{path}.local_path", errors)
    _require_int(artifact.get("width"), f"{path}.width", errors, minimum=1)
    _require_int(artifact.get("height"), f"{path}.height", errors, minimum=1)
    sha = _require_string(artifact.get("sha256"), f"{path}.sha256", errors)
    if sha and not SHA256_RE.match(sha):
        errors.append(f"{path}.sha256 must be a 64-char lowercase sha256")
    authority = _require_string(artifact.get("authority"), f"{path}.authority", errors)
    if role in CONTROL_ROLES and authority != "reference_only":
        errors.append(f"{path}.authority must be reference_only for control/reference layers")
    if role in PUBLISHED_ROLES and authority == "reference_only":
        errors.append(f"{path}.authority must not be reference_only for player-facing visual layers")
    return artifact


def _validate_quality_gates(raw: Any, path: str, errors: list[str]) -> list[dict[str, Any]]:
    gates = _require_array(raw, path, errors, minimum=1)
    result: list[dict[str, Any]] = []
    for index, item in enumerate(gates):
        gate_path = f"{path}[{index}]"
        gate = _require_object(item, gate_path, errors)
        if not gate:
            continue
        _require_string(gate.get("gate_id"), f"{gate_path}.gate_id", errors)
        status = _require_string(gate.get("status"), f"{gate_path}.status", errors)
        if status and status not in QUALITY_STATUSES:
            errors.append(f"{gate_path}.status={status!r} is not allowed")
        _require_string(gate.get("summary"), f"{gate_path}.summary", errors)
        result.append(gate)
    return result


def validate_package(package: dict[str, Any], schema: dict[str, Any] | None = None) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_with_jsonschema(package, schema))
    errors.extend(validate_pure_python(package))
    scan_forbidden_fields(package, "", errors)
    scan_external_urls(package, "", errors)
    return list(dict.fromkeys(errors))


def validate_with_jsonschema(package: dict[str, Any], schema: dict[str, Any] | None) -> list[str]:
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
        f"schema: {'.'.join(map(str, e.path)) or '<root>'}: {e.message}"
        for e in sorted(validator.iter_errors(package), key=str)
    ]


def validate_pure_python(package: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "package_id",
        "worldbook_id",
        "node_id",
        "created_at",
        "source_refs",
        "logical_map_layer",
        "control_layer",
        "painted_visual_layer",
        "alignment_layer",
        "quality_gates",
        "export_refs",
        "validation_report",
    }
    for key in required:
        if key not in package:
            errors.append(f"missing top-level key: {key}")
    if package.get("schema_version") != "map_compile_package.v0.2":
        errors.append("schema_version must be 'map_compile_package.v0.2'")
    for key in ("package_id", "worldbook_id", "node_id"):
        _require_string(package.get(key), key, errors)
    created_at = package.get("created_at")
    if not isinstance(created_at, str) or not DATETIME_RE.match(created_at):
        errors.append("created_at must be an ISO-8601 datetime string")

    source_refs = _require_object(package.get("source_refs"), "source_refs", errors)
    for key in ("battle_config_path", "map_runtime_package_path", "visual_reference_manifest_path"):
        _require_string(source_refs.get(key), f"source_refs.{key}", errors)
    if source_refs.get("logic_authority") != "map_runtime_package":
        errors.append("source_refs.logic_authority must be 'map_runtime_package'")

    logical = _require_object(package.get("logical_map_layer"), "logical_map_layer", errors)
    if logical:
        if logical.get("authority") != "runtime_truth":
            errors.append("logical_map_layer.authority must be 'runtime_truth'")
        routes = _require_array(logical.get("path_routes"), "logical_map_layer.path_routes", errors, minimum=1)
        slots = _require_array(logical.get("build_slots"), "logical_map_layer.build_slots", errors, minimum=1)
        spawns = _require_array(logical.get("spawn_points"), "logical_map_layer.spawn_points", errors, minimum=1)
        if _require_int(logical.get("path_route_count"), "logical_map_layer.path_route_count", errors, minimum=1) != len(routes):
            errors.append("logical_map_layer.path_route_count must match path_routes length")
        if _require_int(logical.get("build_slot_count"), "logical_map_layer.build_slot_count", errors, minimum=1) != len(slots):
            errors.append("logical_map_layer.build_slot_count must match build_slots length")
        if _require_int(logical.get("spawn_point_count"), "logical_map_layer.spawn_point_count", errors, minimum=1) != len(spawns):
            errors.append("logical_map_layer.spawn_point_count must match spawn_points length")

    control = _require_object(package.get("control_layer"), "control_layer", errors)
    if control:
        if control.get("authority") != "reference_only":
            errors.append("control_layer.authority must be 'reference_only'")
        artifacts = _require_array(control.get("artifacts"), "control_layer.artifacts", errors, minimum=1)
        for index, artifact in enumerate(artifacts):
            _validate_visual_artifact(artifact, f"control_layer.artifacts[{index}]", errors)
        _require_array(control.get("model_instruction_boundary"), "control_layer.model_instruction_boundary", errors, minimum=1)

    painted = _require_object(package.get("painted_visual_layer"), "painted_visual_layer", errors)
    if painted:
        status = painted.get("status")
        artifact = painted.get("artifact")
        if status == "published":
            _validate_visual_artifact(artifact, "painted_visual_layer.artifact", errors)
        elif artifact is not None:
            _validate_visual_artifact(artifact, "painted_visual_layer.artifact", errors)
        _require_array(painted.get("visual_constraints"), "painted_visual_layer.visual_constraints", errors, minimum=1)

    alignment = _require_object(package.get("alignment_layer"), "alignment_layer", errors)
    if alignment:
        checkpoints = _require_array(alignment.get("checkpoints"), "alignment_layer.checkpoints", errors, minimum=1)
        for index, checkpoint in enumerate(checkpoints):
            cp = _require_object(checkpoint, f"alignment_layer.checkpoints[{index}]", errors)
            _require_string(cp.get("checkpoint_id"), f"alignment_layer.checkpoints[{index}].checkpoint_id", errors)
            _require_object(cp.get("logic_position"), f"alignment_layer.checkpoints[{index}].logic_position", errors)
            _require_object(cp.get("expected_pixel"), f"alignment_layer.checkpoints[{index}].expected_pixel", errors)
        _require_int(alignment.get("max_pixel_error"), "alignment_layer.max_pixel_error", errors, minimum=0)

    quality = _validate_quality_gates(package.get("quality_gates"), "quality_gates", errors)
    gate_ids = {str(g.get("gate_id")) for g in quality}
    if "control_layers_not_player_default" not in gate_ids:
        errors.append("quality_gates must include control_layers_not_player_default")
    if "runtime_truth_source" not in gate_ids:
        errors.append("quality_gates must include runtime_truth_source")

    export_refs = _require_object(package.get("export_refs"), "export_refs", errors)
    _require_string(export_refs.get("map_runtime_package_path"), "export_refs.map_runtime_package_path", errors)
    role = _require_string(export_refs.get("frontend_default_visual_role"), "export_refs.frontend_default_visual_role", errors)
    if role and role not in PUBLISHED_ROLES:
        errors.append("export_refs.frontend_default_visual_role must be a player-facing role")

    report = _require_object(package.get("validation_report"), "validation_report", errors)
    if report:
        if report.get("runtime_truth_preserved") is not True:
            errors.append("validation_report.runtime_truth_preserved must be true")
        _validate_quality_gates(report.get("gates"), "validation_report.gates", errors)

    return errors


def checkpoint_distance(a: dict[str, int], b: dict[str, int]) -> float:
    return math.hypot(int(a.get("x", 0)) - int(b.get("x", 0)), int(a.get("y", 0)) - int(b.get("y", 0)))
