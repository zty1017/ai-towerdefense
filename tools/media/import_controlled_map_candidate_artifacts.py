#!/usr/bin/env python3
"""Import local controlled map candidate PNG artifacts for review.

This importer consumes MapControlledRegenerationRequestPack plus a local import
plan. By default it only reports that artifacts are awaited. With --copy-files
it copies validated local PNGs into the existing controlled candidate slots and
refreshes their sidecars. It never calls providers, reads .env, publishes a
runtime layer, or mutates MapRuntimePackage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPORT_VERSION = "controlled_map_candidate_artifact_import_report.v0.1"
PLAN_VERSION = "controlled_map_candidate_artifact_import_plan.v0.1"
REQUEST_PACK_ID = "mvp_map_controlled_regeneration_request_pack"
DEFAULT_REQUEST_PACK = ROOT / "examples/review_packs/map_controlled_regeneration_request_pack.v0.1.json"
DEFAULT_PLAN = ROOT / "examples/review_packs/controlled_map_candidate_artifact_import_plan.v0.1.json"
DEFAULT_OUTPUT = ROOT / "examples/review_packs/controlled_map_candidate_artifact_import_report.v0.1.json"
DEFAULT_TARGET_DIR = ROOT / "game_data/media/map_visual_reference/node_candidates_controlled_v1"
ALLOWED_TMP_DIR = Path("/tmp")
ALLOWED_SOURCE_KINDS = {"reference_image_provider", "manual_paintover", "local_review_fixture"}
PLAN_ROOT_KEYS = {"schema_version", "plan_id", "status", "approvals", "imports", "policy", "notes"}
PLAN_ITEM_KEYS = {"node_id", "source_png_path", "approved_by", "source_kind", "notes"}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def rel(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


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


def png_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        with path.open("rb") as handle:
            header = handle.read(24)
    except OSError:
        return None
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", header[16:24])


def target_path_for(node_id: str, target_dir: Path) -> Path:
    return target_dir / f"{node_id}.controlled_reference_candidate.png"


def request_by_node(pack: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(request.get("node_id")): request
        for request in as_list(pack.get("requests"))
        if isinstance(request, dict) and request.get("node_id")
    }


def validate_plan(plan: Any) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    if not isinstance(plan, dict):
        return [], ["import plan root must be an object"]
    for key in sorted(set(plan) - PLAN_ROOT_KEYS):
        errors.append(f"import plan root contains unsupported field: {key}")
    if plan.get("schema_version") != PLAN_VERSION:
        errors.append(f"schema_version must be {PLAN_VERSION}")
    approvals = plan.get("approvals", [])
    if not isinstance(approvals, list):
        errors.append("approvals must be an array")
    imports = plan.get("imports", [])
    if not isinstance(imports, list):
        errors.append("imports must be an array")
        return [], errors
    entries: list[dict[str, Any]] = []
    for index, item in enumerate(imports):
        if not isinstance(item, dict):
            errors.append(f"imports[{index}] must be an object")
            continue
        for key in sorted(set(item) - PLAN_ITEM_KEYS):
            errors.append(f"imports[{index}] contains unsupported field: {key}")
        if not isinstance(item.get("node_id"), str) or not item.get("node_id", "").strip():
            errors.append(f"imports[{index}].node_id must be a non-empty string")
        if not isinstance(item.get("source_png_path"), str) or not item.get("source_png_path", "").strip():
            errors.append(f"imports[{index}].source_png_path must be a non-empty string")
        source_kind = item.get("source_kind", "manual_paintover")
        if source_kind not in ALLOWED_SOURCE_KINDS:
            errors.append(f"imports[{index}].source_kind must be one of {sorted(ALLOWED_SOURCE_KINDS)}")
        entries.append(item)
    return entries, errors


def validate_source_png(path_value: str, index: int) -> tuple[Path | None, dict[str, Any], list[str]]:
    errors: list[str] = []
    path = resolve_path(path_value)
    allowed_repo_path = is_relative_to(path, ROOT)
    allowed_tmp_path = path.is_absolute() and is_relative_to(path, ALLOWED_TMP_DIR)
    if not allowed_repo_path and not allowed_tmp_path:
        errors.append(f"imports[{index}].source_png_path must be under repository root or /tmp")
    if path.suffix.lower() != ".png":
        errors.append(f"imports[{index}].source_png_path must end with .png")
    if not path.exists():
        errors.append(f"imports[{index}].source_png_path does not exist: {path_value}")
        return None, {}, errors
    if not path.is_file():
        errors.append(f"imports[{index}].source_png_path must be a file: {path_value}")
        return None, {}, errors
    dims = png_dimensions(path)
    if dims is None:
        errors.append(f"imports[{index}].source_png_path is not a readable PNG: {path_value}")
        return None, {}, errors
    refs = {
        "source_png_path": rel(path),
        "source_png_sha256": sha256_file(path),
        "source_png_size_bytes": path.stat().st_size,
        "source_png_dimensions": {"width": dims[0], "height": dims[1]},
    }
    return path, refs, errors


def refresh_sidecar(
    *,
    sidecar_path: Path,
    target_png_path: Path,
    request_pack_path: Path,
    request: dict[str, Any],
    source_refs: dict[str, Any],
    item: dict[str, Any],
) -> dict[str, Any]:
    sidecar = load_json(sidecar_path) if sidecar_path.exists() else {}
    control = as_obj(request.get("control_sketch"))
    target_dims = png_dimensions(target_png_path)
    sidecar.update(
        {
            "schema_version": "controlled_map_candidate.v0.1",
            "candidate_id": f"{request.get('node_id')}.reference_image.controlled_map_candidate",
            "candidate_path": rel(target_png_path),
            "sidecar_kind": "controlled_map_candidate",
            "request_pack_path": rel(request_pack_path),
            "request_id": request.get("request_id"),
            "node_id": request.get("node_id"),
            "runtime_package_path": request.get("runtime_package_path"),
            "source_prompt_pack": request.get("source_prompt_pack"),
            "source_control_sketch_pack": request.get("source_control_sketch_pack"),
            "control_sketch_png_path": control.get("png_path"),
            "control_sketch_png_sha256": control.get("png_sha256"),
            "provider_mode": "reference-image",
            "provider_called_this_run": False,
            "generation_status": "local_artifact_imported_pending_candidate_review",
            "review_status": "candidate_needs_candidate_review_first",
            "promotion_allowed_now": False,
            "promotion_policy": "must pass candidate, alignment, overlay, visual, and explicit promotion gates before runtime use",
            "required_review_gates": as_list(request.get("required_review_gates")),
            "target_candidate": as_obj(request.get("target_candidate")),
            "provider_reference_contract": as_obj(request.get("provider_reference_contract")),
            "safe_to_send": "topology_prompt_and_control_image_only_no_secret_no_raw_trace",
            "image_exists": True,
            "image_size_bytes": target_png_path.stat().st_size,
            "image_sha256": sha256_file(target_png_path),
            "size": f"{target_dims[0]}x{target_dims[1]}" if target_dims else sidecar.get("size"),
            "local_artifact_import": {
                "source_kind": item.get("source_kind", "manual_paintover"),
                "approved_by": item.get("approved_by"),
                "notes": item.get("notes"),
                "source_png_path": source_refs.get("source_png_path"),
                "source_png_sha256": source_refs.get("source_png_sha256"),
            },
        }
    )
    write_json(sidecar_path, sidecar)
    return sidecar


def build_awaiting_item(request: dict[str, Any], target_dir: Path) -> dict[str, Any]:
    node_id = str(request.get("node_id"))
    target_png = target_path_for(node_id, target_dir)
    return {
        "node_id": node_id,
        "request_id": request.get("request_id"),
        "status": "awaiting_local_artifact",
        "source_kind": None,
        "source_png_path": None,
        "source_png_sha256": None,
        "target_candidate_path": rel(target_png),
        "target_sidecar_path": rel(target_png.with_suffix(target_png.suffix + ".candidate.json")),
        "copied": False,
        "provider_called_this_run": False,
        "promotion_allowed_now": False,
        "notes": "no import item supplied",
    }


def build_report(
    *,
    request_pack_path: Path,
    plan_path: Path,
    target_dir: Path,
    copy_files: bool,
    items: list[dict[str, Any]],
    errors: list[str],
) -> dict[str, Any]:
    status_counts = Counter(str(item.get("status")) for item in items)
    imported_count = status_counts.get("imported_pending_candidate_review", 0)
    awaiting_count = status_counts.get("awaiting_local_artifact", 0)
    invalid_count = status_counts.get("invalid_import_plan_item", 0) + len(errors)
    status = (
        "invalid_import_plan"
        if errors
        else (
            "imported_pending_candidate_review"
            if imported_count and not awaiting_count
            else ("partially_imported_pending_candidate_review" if imported_count else "awaiting_local_artifacts")
        )
    )
    return {
        "schema_version": REPORT_VERSION,
        "report_id": "mvp_controlled_map_candidate_artifact_import_v0_1",
        "status": status,
        "request_pack_path": rel(request_pack_path),
        "import_plan_path": rel(plan_path),
        "target_dir": rel(target_dir),
        "copy_files": copy_files,
        "summary": {
            "request_count": len(items),
            "awaiting_count": awaiting_count,
            "imported_count": imported_count,
            "invalid_count": invalid_count,
            "provider_call_count": 0,
            "runtime_mutation_count": 0,
            "published_visual_layer_write_count": 0,
            "map_runtime_package_write_count": 0,
            "status_counts": dict(sorted(status_counts.items())),
        },
        "safety_summary": {
            "provider_called": False,
            "reads_env": False,
            "runtime_published": False,
            "map_runtime_package_modified": False,
            "published_visual_layer_written": False,
            "runtime_package_activation_changed": False,
            "copies_files_only_when_copy_files_true": True,
            "source_paths_limited_to_repo_or_tmp": True,
        },
        "items": items,
        "errors": errors,
        "policy": [
            "This report imports local PNG artifacts into review-only controlled map candidate slots only.",
            "The importer does not call providers, read .env, publish runtime artifacts, modify MapRuntimePackage, or write a published visual layer.",
            "Imported candidates remain blocked from runtime promotion until candidate, alignment, overlay, visual, and explicit promotion gates pass.",
        ],
        "validation": {
            "commands": [
                "python3 tools/media/validate_controlled_map_candidate_artifact_import_report.py "
                + rel(DEFAULT_OUTPUT)
            ]
        },
    }


def run_import(
    *,
    request_pack_path: Path,
    plan_path: Path,
    target_dir: Path,
    output_path: Path,
    copy_files: bool,
) -> dict[str, Any]:
    request_pack = load_json(request_pack_path)
    plan = load_json(plan_path)
    errors: list[str] = []
    if not isinstance(request_pack, dict) or request_pack.get("pack_id") != REQUEST_PACK_ID:
        errors.append(f"request pack must be {REQUEST_PACK_ID}")
        requests = {}
    else:
        requests = request_by_node(request_pack)
    imports, plan_errors = validate_plan(plan)
    errors.extend(plan_errors)
    import_by_node: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(imports):
        node_id = str(item.get("node_id") or "")
        if node_id in import_by_node:
            errors.append(f"imports[{index}].node_id duplicates another import item: {node_id}")
        import_by_node[node_id] = item

    report_items: list[dict[str, Any]] = []
    for request in requests.values():
        node_id = str(request.get("node_id"))
        item = import_by_node.get(node_id)
        if item is None or errors:
            report_items.append(build_awaiting_item(request, target_dir))
            continue
        index = imports.index(item)
        source_path, source_refs, source_errors = validate_source_png(str(item.get("source_png_path")), index)
        target_png = target_path_for(node_id, target_dir)
        sidecar_path = target_png.with_suffix(target_png.suffix + ".candidate.json")
        item_errors = list(source_errors)
        if not sidecar_path.exists():
            item_errors.append(f"target sidecar does not exist: {rel(sidecar_path)}")
        if item_errors:
            report_items.append(
                {
                    **build_awaiting_item(request, target_dir),
                    "status": "invalid_import_plan_item",
                    "source_kind": item.get("source_kind", "manual_paintover"),
                    "source_png_path": str(item.get("source_png_path")),
                    "errors": item_errors,
                    "notes": item.get("notes"),
                }
            )
            continue
        if copy_files and source_path is not None:
            target_png.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, target_png)
            target_refs = {
                "target_png_path": rel(target_png),
                "target_png_sha256": sha256_file(target_png),
                "target_png_size_bytes": target_png.stat().st_size,
                "target_png_dimensions": source_refs["source_png_dimensions"],
            }
            refresh_sidecar(
                sidecar_path=sidecar_path,
                target_png_path=target_png,
                request_pack_path=request_pack_path,
                request=request,
                source_refs=source_refs,
                item=item,
            )
            status = "imported_pending_candidate_review"
            copied = True
        else:
            target_refs = {
                "target_png_path": rel(target_png),
                "target_png_sha256": None,
                "target_png_size_bytes": 0,
                "target_png_dimensions": None,
            }
            status = "validated_not_copied"
            copied = False
        report_items.append(
            {
                "node_id": node_id,
                "request_id": request.get("request_id"),
                "status": status,
                "source_kind": item.get("source_kind", "manual_paintover"),
                "approved_by": item.get("approved_by"),
                "notes": item.get("notes"),
                **source_refs,
                "target_candidate_path": target_refs["target_png_path"],
                "target_candidate_sha256": target_refs["target_png_sha256"],
                "target_candidate_size_bytes": target_refs["target_png_size_bytes"],
                "target_candidate_dimensions": target_refs["target_png_dimensions"],
                "target_sidecar_path": rel(sidecar_path),
                "copied": copied,
                "provider_called_this_run": False,
                "promotion_allowed_now": False,
                "generation_status": (
                    "local_artifact_imported_pending_candidate_review" if copied else "local_artifact_validated_not_copied"
                ),
                "review_status": (
                    "candidate_needs_candidate_review_first" if copied else "not_copied_needs_copy_files"
                ),
            }
        )

    unknown_nodes = sorted(set(import_by_node) - set(requests))
    for node_id in unknown_nodes:
        errors.append(f"import item references unknown node_id: {node_id}")

    report = build_report(
        request_pack_path=request_pack_path,
        plan_path=plan_path,
        target_dir=target_dir,
        copy_files=copy_files,
        items=report_items,
        errors=errors,
    )
    report["validation"]["commands"] = [
        f"python3 tools/media/validate_controlled_map_candidate_artifact_import_report.py {rel(output_path)}"
    ]
    write_json(output_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Import controlled map candidate local PNG artifacts.")
    parser.add_argument("--request-pack", default=str(DEFAULT_REQUEST_PACK))
    parser.add_argument("--plan", default=str(DEFAULT_PLAN))
    parser.add_argument("--target-dir", default=str(DEFAULT_TARGET_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--copy-files", action="store_true")
    args = parser.parse_args()

    request_pack_path = resolve_path(args.request_pack)
    plan_path = resolve_path(args.plan)
    target_dir = resolve_path(args.target_dir)
    output_path = resolve_path(args.output)
    report = run_import(
        request_pack_path=request_pack_path,
        plan_path=plan_path,
        target_dir=target_dir,
        output_path=output_path,
        copy_files=args.copy_files,
    )
    print(f"Wrote {output_path}")
    print(f"- status: {report['status']}")
    print(f"- imported: {report['summary']['imported_count']}")
    print(f"- awaiting: {report['summary']['awaiting_count']}")
    return 0 if not report.get("errors") else 1


if __name__ == "__main__":
    raise SystemExit(main())
