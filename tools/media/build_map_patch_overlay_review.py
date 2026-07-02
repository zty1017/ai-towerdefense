#!/usr/bin/env python3
"""Build review-only overlays from runtime map patch candidates.

This tool applies RuntimeMapPatchCandidates to in-memory copies of
MapRuntimePackage files, then renders fresh overlay artifacts on top of the
existing normalized candidate backgrounds. It never updates the source
MapRuntimePackage files and never promotes visual layers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MEDIA_DIR = Path(__file__).resolve().parent
ASSET_GRAPH_DIR = ROOT / "tools/asset_graph"
for directory in (MEDIA_DIR, ASSET_GRAPH_DIR):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import build_map_candidate_overlay_review as overlay  # noqa: E402
import build_runtime_map_patch_candidates as patch_candidates  # noqa: E402
import map_runtime_package as mrp  # noqa: E402


REPORT_VERSION = "map_patch_overlay_review.v0.1"
DEFAULT_PATCH_CANDIDATES = ROOT / "examples/review_packs/runtime_map_patch_candidates.v0.1.json"
DEFAULT_SOURCE_OVERLAY_REVIEW = ROOT / "examples/review_packs/map_candidate_overlay_review.v0.1.json"
DEFAULT_OUTPUT_DIR = ROOT / "game_data/media/map_visual_reference/node_candidates_v2_patched_overlay"
DEFAULT_REPORT = ROOT / "examples/review_packs/map_patch_overlay_review.v0.1.json"
DEFAULT_SCHEMA = ROOT / "shared/schemas/map_runtime_package.v0.1.schema.json"
TARGET_WIDTH = 1280
TARGET_HEIGHT = 720


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def resolve_repo_path(value: Any) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def sha256_json(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def overlay_artifact_index(source_overlay_review: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for artifact in as_list(source_overlay_review.get("artifacts")):
        if isinstance(artifact, dict) and isinstance(artifact.get("node_id"), str):
            index[artifact["node_id"]] = artifact
    return index


def load_runtime_schema(schema_path: Path) -> dict[str, Any] | None:
    if not schema_path.exists():
        return None
    loaded = load_json(schema_path)
    return loaded if isinstance(loaded, dict) else None


def target_from_package(package: dict[str, Any], target_id: str) -> dict[str, Any] | None:
    objectives = as_obj(package.get("objectives"))
    core = objectives.get("core_target")
    if isinstance(core, dict) and core.get("target_id") == target_id:
        return core
    for target in as_list(objectives.get("optional_targets")):
        if isinstance(target, dict) and target.get("target_id") == target_id:
            return target
    return None


def collect_operation_deltas(
    before: dict[str, Any],
    after: dict[str, Any],
    operations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    before_routes = {
        route.get("route_id"): route
        for route in as_list(before.get("path_routes"))
        if isinstance(route, dict)
    }
    after_routes = {
        route.get("route_id"): route
        for route in as_list(after.get("path_routes"))
        if isinstance(route, dict)
    }
    before_spawns = {
        spawn.get("spawn_id"): spawn
        for spawn in as_list(before.get("spawn_points"))
        if isinstance(spawn, dict)
    }
    after_spawns = {
        spawn.get("spawn_id"): spawn
        for spawn in as_list(after.get("spawn_points"))
        if isinstance(spawn, dict)
    }
    before_slots = {
        slot.get("slot_id"): slot
        for slot in as_list(before.get("build_slots"))
        if isinstance(slot, dict)
    }
    after_slots = {
        slot.get("slot_id"): slot
        for slot in as_list(after.get("build_slots"))
        if isinstance(slot, dict)
    }
    deltas: list[dict[str, Any]] = []
    for operation in operations:
        kind = operation.get("op")
        if kind == "replace_path_waypoints":
            route_id = str(operation.get("route_id"))
            before_route = as_obj(before_routes.get(route_id))
            after_route = as_obj(after_routes.get(route_id))
            deltas.append(
                {
                    "op": kind,
                    "route_id": route_id,
                    "before_waypoints": as_list(before_route.get("waypoints")),
                    "after_waypoints": as_list(after_route.get("waypoints")),
                }
            )
        elif kind == "move_objective":
            target_id = str(operation.get("target_id"))
            before_target = target_from_package(before, target_id) or {}
            after_target = target_from_package(after, target_id) or {}
            deltas.append(
                {
                    "op": kind,
                    "target_id": target_id,
                    "before_position": before_target.get("position"),
                    "after_position": after_target.get("position"),
                }
            )
        elif kind == "move_spawn_point":
            spawn_id = str(operation.get("spawn_id"))
            deltas.append(
                {
                    "op": kind,
                    "spawn_id": spawn_id,
                    "before_position": as_obj(before_spawns.get(spawn_id)).get("position"),
                    "after_position": as_obj(after_spawns.get(spawn_id)).get("position"),
                }
            )
        elif kind == "move_build_slot":
            slot_id = str(operation.get("slot_id"))
            deltas.append(
                {
                    "op": kind,
                    "slot_id": slot_id,
                    "before_position": as_obj(before_slots.get(slot_id)).get("position"),
                    "after_position": as_obj(after_slots.get(slot_id)).get("position"),
                }
            )
        else:
            deltas.append({"op": kind, "status": "unknown_operation_not_applied"})
    return deltas


def load_normalized_rows(artifact: dict[str, Any]) -> tuple[Path, int, int, int, list[bytearray]]:
    normalized_path = resolve_repo_path(artifact.get("normalized_path"))
    if normalized_path is None or not normalized_path.exists():
        raise FileNotFoundError("source normalized map candidate image is missing")
    width, height, color_type, rows = overlay.read_png(normalized_path)
    return normalized_path, width, height, color_type, rows


def build_patch_artifact(
    candidate: dict[str, Any],
    source_artifacts: dict[str, dict[str, Any]],
    output_dir: Path,
    schema: dict[str, Any] | None,
    target_width: int,
    target_height: int,
) -> dict[str, Any]:
    node_id = str(candidate.get("node_id") or "unknown_node")
    if candidate.get("status") != "review_candidate":
        return {
            "node_id": node_id,
            "status": "skipped",
            "reason": candidate.get("reason") or "not a review_candidate patch",
            "promotion_allowed_now": False,
            "review_required": True,
        }

    package_path = resolve_repo_path(candidate.get("source_runtime_package"))
    source_artifact = source_artifacts.get(node_id)
    if package_path is None or not package_path.exists():
        return {
            "node_id": node_id,
            "status": "blocked",
            "issues": ["source_runtime_package_missing"],
            "promotion_allowed_now": False,
            "review_required": True,
        }
    if source_artifact is None:
        return {
            "node_id": node_id,
            "status": "blocked",
            "issues": ["source_overlay_artifact_missing"],
            "promotion_allowed_now": False,
            "review_required": True,
        }

    runtime_package = load_json(package_path)
    operations = [operation for operation in as_list(candidate.get("patch_operations")) if isinstance(operation, dict)]
    patched_package = patch_candidates.apply_patch_candidate(runtime_package, operations)
    validation_errors = mrp.validate_package(patched_package, schema)

    try:
        normalized_path, width, height, color_type, rows = load_normalized_rows(source_artifact)
    except (FileNotFoundError, ValueError) as exc:
        return {
            "node_id": node_id,
            "status": "blocked",
            "issues": [str(exc)],
            "promotion_allowed_now": False,
            "review_required": True,
        }

    if width != target_width or height != target_height:
        return {
            "node_id": node_id,
            "status": "blocked",
            "issues": [f"normalized_image_size_mismatch:{width}x{height}"],
            "promotion_allowed_now": False,
            "review_required": True,
        }

    patched_package_path = output_dir / f"{node_id}.patched_runtime_review.json"
    overlay_path = output_dir / f"{node_id}.patched_overlay_review.svg"
    overlay_png_path = output_dir / f"{node_id}.patched_overlay_review.png"
    write_json(patched_package_path, patched_package)
    overlay.build_overlay_svg(overlay_path, normalized_path, patched_package, target_width, target_height)
    overlay.build_overlay_png(overlay_png_path, rows, patched_package, target_width, target_height)

    validation_status = "passed" if not validation_errors else "failed"
    status = "patched_overlay_artifact_ready" if validation_status == "passed" else "patched_overlay_artifact_ready_validation_failed"
    return {
        "node_id": node_id,
        "status": status,
        "source_runtime_package": rel(package_path),
        "source_normalized_path": rel(normalized_path),
        "patched_runtime_review_path": rel(patched_package_path),
        "patched_overlay_review_path": rel(overlay_path),
        "patched_overlay_review_png_path": rel(overlay_png_path),
        "patched_runtime_sha256": sha256_json(patched_package),
        "patched_overlay_sha256": overlay.sha256_file(overlay_path),
        "patched_overlay_png_sha256": overlay.sha256_file(overlay_png_path),
        "patch_strategy": candidate.get("patch_strategy"),
        "risk_level": candidate.get("risk_level"),
        "patch_operation_count": len(operations),
        "patch_operation_deltas": collect_operation_deltas(runtime_package, patched_package, operations),
        "before_summary": {
            "route_bounds": patch_candidates.route_bounds(runtime_package),
            "path_route_count": len(as_list(runtime_package.get("path_routes"))),
        },
        "after_summary": {
            "route_bounds": patch_candidates.route_bounds(patched_package),
            "path_route_count": len(as_list(patched_package.get("path_routes"))),
        },
        "validation": {
            "status": validation_status,
            "error_count": len(validation_errors),
            "errors": validation_errors,
        },
        "promotion_allowed_now": False,
        "review_required": True,
        "acceptance_gates": [
            "patched_runtime_schema_passed",
            "patched_overlay_artifact_ready",
            "runtime_paths_follow_visible_roads",
            "objectives_land_on_unique_visible_landmarks",
            "build_slots_land_on_visible_empty_pads",
            "battle_simulation_still_valid",
            "explicit_promotion_report_updates_MapRuntimePackage",
        ],
        "review_notes": [
            "This artifact applies patch candidates to an in-memory runtime package only.",
            "The source MapRuntimePackage file is not changed by this tool.",
            "Patched overlay readiness does not approve visual readability or runtime promotion.",
        ],
    }


def build_report(
    patch_candidates_path: Path,
    source_overlay_review_path: Path,
    output_dir: Path,
    schema_path: Path,
    target_width: int,
    target_height: int,
) -> dict[str, Any]:
    patch_report = load_json(patch_candidates_path)
    source_overlay_review = load_json(source_overlay_review_path)
    source_artifacts = overlay_artifact_index(source_overlay_review)
    schema = load_runtime_schema(schema_path)
    artifacts = [
        build_patch_artifact(candidate, source_artifacts, output_dir, schema, target_width, target_height)
        for candidate in as_list(patch_report.get("candidates"))
        if isinstance(candidate, dict)
    ]
    status_counts = Counter(str(artifact.get("status")) for artifact in artifacts)
    blocked_count = status_counts.get("blocked", 0)
    ready_count = status_counts.get("patched_overlay_artifact_ready", 0)
    validation_failed_count = status_counts.get("patched_overlay_artifact_ready_validation_failed", 0)
    return {
        "schema_version": REPORT_VERSION,
        "report_id": "mvp_map_patch_overlay_review",
        "runtime_map_patch_candidates_path": rel(patch_candidates_path),
        "source_overlay_review_path": rel(source_overlay_review_path),
        "output_dir": rel(output_dir),
        "status": "blocked" if blocked_count else "patched_overlay_artifacts_ready_review_required",
        "summary": {
            "candidate_count": len(artifacts),
            "patched_overlay_artifact_ready_count": ready_count,
            "validation_failed_count": validation_failed_count,
            "skipped_count": status_counts.get("skipped", 0),
            "blocked_count": blocked_count,
            "promotion_allowed_now_count": 0,
            "status_counts": dict(sorted(status_counts.items())),
            "target_size": {"width": target_width, "height": target_height},
        },
        "artifacts": artifacts,
        "policy": [
            "Patched runtime JSON files are review snapshots, not promoted MapRuntimePackage files.",
            "The frontend runtime must not consume these artifacts unless a later promotion report explicitly updates published runtime packages or visual layers.",
            "This report only proves that patch candidates can be visualized against the existing normalized background.",
        ],
    }


def parse_target_size(value: str) -> tuple[int, int]:
    try:
        width_s, height_s = value.lower().split("x", 1)
        return int(width_s), int(height_s)
    except ValueError as exc:
        raise SystemExit(f"invalid --target-size {value!r}; expected WIDTHxHEIGHT") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Build patched map overlay review artifacts.")
    parser.add_argument("--patch-candidates", default=str(DEFAULT_PATCH_CANDIDATES))
    parser.add_argument("--source-overlay-review", default=str(DEFAULT_SOURCE_OVERLAY_REVIEW))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--output", "--report", dest="report", default=str(DEFAULT_REPORT))
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    parser.add_argument("--target-size", default=f"{TARGET_WIDTH}x{TARGET_HEIGHT}")
    args = parser.parse_args()

    patch_candidates_path = Path(args.patch_candidates)
    if not patch_candidates_path.is_absolute():
        patch_candidates_path = ROOT / patch_candidates_path
    source_overlay_review_path = Path(args.source_overlay_review)
    if not source_overlay_review_path.is_absolute():
        source_overlay_review_path = ROOT / source_overlay_review_path
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    schema_path = Path(args.schema)
    if not schema_path.is_absolute():
        schema_path = ROOT / schema_path
    target_width, target_height = parse_target_size(args.target_size)

    report = build_report(
        patch_candidates_path,
        source_overlay_review_path,
        output_dir,
        schema_path,
        target_width,
        target_height,
    )
    write_json(report_path, report)
    print(f"Wrote {report_path}")
    print(f"- status: {report['status']}")
    print(f"- patched overlays: {report['summary']['patched_overlay_artifact_ready_count']}")
    print(f"- validation failed: {report['summary']['validation_failed_count']}")
    return 0 if report["summary"]["candidate_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
