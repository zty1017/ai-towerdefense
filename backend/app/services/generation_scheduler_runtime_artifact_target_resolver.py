"""Resolve scheduler object refs to review-only runtime artifact targets."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


_RUNTIME_PACKAGE_PATHS = {
    "mvp_demo": "examples/runtime_packages/mvp_demo.runtime_package.json",
    "mvp_old_signal_tower": (
        "examples/runtime_packages/mvp_old_signal_tower.runtime_package.json"
    ),
    "mvp_wick_store_pressure": (
        "examples/runtime_packages/mvp_wick_store_pressure.runtime_package.json"
    ),
    "provider_promotion_sample": (
        "examples/runtime_packages/provider_promotion_sample.runtime_package.json"
    ),
}
_MAP_RUNTIME_PACKAGE_PATHS = {
    "mvp_first_battle": (
        "examples/map_runtime_packages/mvp_first_battle.map_runtime_package.json"
    ),
    "mvp_old_signal_tower_pressure": (
        "examples/map_runtime_packages/"
        "mvp_old_signal_tower_pressure.map_runtime_package.json"
    ),
    "mvp_wick_store_pressure": (
        "examples/map_runtime_packages/"
        "mvp_wick_store_pressure.map_runtime_package.json"
    ),
}
_MAP_COMPILE_PACKAGE_PATHS = {
    "old_signal_tower_pressure": (
        "examples/map_compile_packages/"
        "mvp_old_signal_tower_pressure.map_compile_package.json"
    ),
    "mvp_old_signal_tower_pressure": (
        "examples/map_compile_packages/"
        "mvp_old_signal_tower_pressure.map_compile_package.json"
    ),
    "first_battle": "examples/map_compile_packages/mvp_first_battle.map_compile_package.json",
    "mvp_first_battle": (
        "examples/map_compile_packages/mvp_first_battle.map_compile_package.json"
    ),
    "wick_store_pressure": (
        "examples/map_compile_packages/mvp_wick_store_pressure.map_compile_package.json"
    ),
    "mvp_wick_store_pressure": (
        "examples/map_compile_packages/mvp_wick_store_pressure.map_compile_package.json"
    ),
}
_WORLD_DELTA_TRANSACTION_PATHS = {
    "act_1_stage_05_old_signal_tower_pressure": (
        "examples/world_delta_transactions/"
        "stage_05_old_signal_tower_pressure.world_delta_transaction.json"
    ),
    "stage_05_old_signal_tower_pressure": (
        "examples/world_delta_transactions/"
        "stage_05_old_signal_tower_pressure.world_delta_transaction.json"
    ),
    "first_battle_result": (
        "examples/world_delta_transactions/first_battle_result.world_delta_transaction.json"
    ),
}
_MEDIA_ATLAS_PATHS = {
    "frontend_runtime_art_atlas_v0_1": (
        "game_data/media/frontend_runtime_mock/"
        "frontend_runtime_art_atlas_manifest.v0.1.json"
    ),
    "frontend_mock": (
        "game_data/media/frontend_mock/frontend_media_atlas_manifest.v0.1.json"
    ),
}


def _repo_relative(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _load_json_object_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_artifact_ref(
    *,
    ref_kind: str,
    path: Path,
    fallback_id: str,
    repo_root: Path,
    status: str = "resolved_review_only",
) -> dict[str, Any]:
    payload = _load_json_object_if_exists(path)
    artifact_id = fallback_id
    schema_version = None
    node_id = None
    if payload is not None:
        schema_version = payload.get("schema_version")
        node_id = payload.get("node_id")
        for key in ("package_id", "transaction_id", "manifest_id", "report_id"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                artifact_id = value
                break
    return {
        "ref_kind": ref_kind,
        "artifact_id": artifact_id,
        "path": _repo_relative(path, repo_root),
        "schema_version": schema_version,
        "node_id": node_id,
        "sha256": _sha256_file(path) if payload is not None else None,
        "status": status if payload is not None else "missing_reference",
    }


def _split_object_ref(value: Any) -> tuple[str, str]:
    text = str(value or "")
    if ":" not in text:
        return "", text
    prefix, slug = text.split(":", 1)
    return prefix.strip(), slug.strip()


def resolve_runtime_artifact_targets(
    queue_item: dict[str, Any],
    *,
    repo_root: Path,
) -> dict[str, Any]:
    prefix, slug = _split_object_ref(queue_item.get("object_ref"))
    result: dict[str, Any] = {
        "runtime_package_refs": [],
        "map_runtime_package_refs": [],
        "world_delta_transaction_refs": [],
        "published_media_update_refs": [],
        "unresolved_targets": [],
    }

    def add_unresolved(reason: str) -> None:
        result["unresolved_targets"].append(
            {
                "object_ref": queue_item.get("object_ref"),
                "object_kind": queue_item.get("object_kind"),
                "reason": reason,
            }
        )

    if prefix == "runtime_package":
        raw_path = _RUNTIME_PACKAGE_PATHS.get(slug)
        if raw_path:
            result["runtime_package_refs"].append(
                _json_artifact_ref(
                    ref_kind="runtime_package",
                    path=repo_root / raw_path,
                    fallback_id=slug,
                    repo_root=repo_root,
                )
            )
        else:
            add_unresolved("unknown_runtime_package_ref")
        return result

    if prefix == "map_runtime_package":
        raw_path = _MAP_RUNTIME_PACKAGE_PATHS.get(slug)
        if raw_path:
            result["map_runtime_package_refs"].append(
                _json_artifact_ref(
                    ref_kind="map_runtime_package",
                    path=repo_root / raw_path,
                    fallback_id=slug,
                    repo_root=repo_root,
                )
            )
        else:
            add_unresolved("unknown_map_runtime_package_ref")
        return result

    if prefix == "map_compile_package":
        raw_path = _MAP_COMPILE_PACKAGE_PATHS.get(slug)
        if not raw_path:
            add_unresolved("unknown_map_compile_package_ref")
            return result
        compile_path = repo_root / raw_path
        result["published_media_update_refs"].append(
            _json_artifact_ref(
                ref_kind="map_compile_package",
                path=compile_path,
                fallback_id=slug,
                repo_root=repo_root,
            )
        )
        compile_payload = _load_json_object_if_exists(compile_path) or {}
        export_refs = compile_payload.get("export_refs")
        if isinstance(export_refs, dict):
            map_runtime_path = export_refs.get("map_runtime_package_path")
            if isinstance(map_runtime_path, str) and map_runtime_path:
                result["map_runtime_package_refs"].append(
                    _json_artifact_ref(
                        ref_kind="map_runtime_package",
                        path=repo_root / map_runtime_path,
                        fallback_id=slug,
                        repo_root=repo_root,
                    )
                )
        return result

    if prefix == "compilable_object_plan":
        raw_path = _WORLD_DELTA_TRANSACTION_PATHS.get(slug)
        if raw_path:
            result["world_delta_transaction_refs"].append(
                _json_artifact_ref(
                    ref_kind="world_state_delta_transaction",
                    path=repo_root / raw_path,
                    fallback_id=slug,
                    repo_root=repo_root,
                )
            )
        else:
            add_unresolved("unknown_compilable_object_plan_transaction_ref")
        return result

    if prefix == "media_atlas":
        raw_path = _MEDIA_ATLAS_PATHS.get(slug)
        if raw_path:
            result["published_media_update_refs"].append(
                _json_artifact_ref(
                    ref_kind="media_atlas_manifest",
                    path=repo_root / raw_path,
                    fallback_id=slug,
                    repo_root=repo_root,
                )
            )
        else:
            add_unresolved("unknown_media_atlas_ref")
        return result

    add_unresolved("unsupported_generation_object_ref")
    return result
