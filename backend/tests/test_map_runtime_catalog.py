"""Fail-closed contracts for Map Runtime Catalog discovery."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services import map_runtime_catalog, map_runtime_service


def _write(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _package(root: Path, node_id: str, version: str = "v0.1") -> tuple[Path, str, str]:
    schema = f"map_runtime_package.{version}"
    package_id = f"map_pkg_{node_id}_{version.replace('.', '_')}"
    directory = "map_runtime_packages_v02" if version == "v0.2" else "map_runtime_packages"
    path = root / "examples" / directory / f"{node_id}.json"
    _write(path, {"schema_version": schema, "package_id": package_id, "node_id": node_id})
    return path, schema, package_id


def _catalog(root: Path, entries: list[dict]) -> Path:
    return _write(
        root / "examples/map_runtime_catalogs/test.json",
        {
            "schema_version": "map_runtime_catalog.v0.1",
            "catalog_id": "test_catalog",
            "generated_at": "2026-07-12T00:00:00Z",
            "source_policy": {},
            "summary": {},
            "entries": entries,
        },
    )


def _entry(root: Path, node_id: str, version: str = "v0.1") -> dict:
    path, schema, package_id = _package(root, node_id, version)
    return {
        "node_id": node_id,
        "authorization_status": "pending",
        "quality_status": "reviewed",
        "packages": {
            schema: {
                "package_id": package_id,
                "path": path.relative_to(root).as_posix(),
                "release_status": (
                    "published_for_gate_review" if version == "v0.2" else "published"
                ),
            }
        },
    }


def test_default_catalog_preserves_current_mvp_nodes():
    assert map_runtime_service.available_map_runtime_node_ids() == [
        "gray_lantern_station", "lamp_wick_store", "old_signal_tower"
    ]
    catalog = map_runtime_catalog.load_catalog(map_runtime_catalog.default_catalog_path())
    assert len(catalog["entries"]) == 3


def test_catalog_schema_and_runtime_validator_share_authorization_policy(tmp_path: Path):
    entry = _entry(tmp_path, "bad_authority_node")
    entry["authorization_status"] = "silently_trusted"
    with pytest.raises(map_runtime_catalog.MapRuntimeCatalogError, match="schema failed"):
        map_runtime_catalog.load_catalog(_catalog(tmp_path, [entry]), tmp_path)


def test_catalog_builds_package_index(tmp_path: Path):
    entry = _entry(tmp_path, "new_compiled_node")
    catalog_path = _catalog(tmp_path, [entry])
    v01, v02 = map_runtime_catalog.build_package_index([catalog_path], tmp_path)
    assert v01["new_compiled_node"].is_file()
    assert v02 == {}


def test_catalog_rejects_path_escape(tmp_path: Path):
    entry = _entry(tmp_path, "escaped_node")
    entry["packages"]["map_runtime_package.v0.1"]["path"] = "../outside.json"
    with pytest.raises(map_runtime_catalog.MapRuntimeCatalogError, match="escapes repository"):
        map_runtime_catalog.load_catalog(_catalog(tmp_path, [entry]), tmp_path)


def test_catalog_rejects_package_identity_mismatch(tmp_path: Path):
    entry = _entry(tmp_path, "identity_node")
    entry["packages"]["map_runtime_package.v0.1"]["package_id"] = "wrong"
    with pytest.raises(map_runtime_catalog.MapRuntimeCatalogError, match="package_id mismatch"):
        map_runtime_catalog.load_catalog(_catalog(tmp_path, [entry]), tmp_path)


def test_catalog_rejects_unpublished_v02(tmp_path: Path):
    entry = _entry(tmp_path, "candidate_node")
    v02_entry = _entry(tmp_path, "candidate_node", "v0.2")
    entry["packages"].update(v02_entry["packages"])
    entry["packages"]["map_runtime_package.v0.2"]["release_status"] = "candidate"
    with pytest.raises(
        map_runtime_catalog.MapRuntimeCatalogError,
        match="schema failed|not published",
    ):
        map_runtime_catalog.load_catalog(_catalog(tmp_path, [entry]), tmp_path)


def test_catalog_rejects_duplicate_nodes_across_catalogs(tmp_path: Path):
    first = _catalog(tmp_path, [_entry(tmp_path, "duplicate_node")])
    second = _write(
        tmp_path / "examples/map_runtime_catalogs/second.json",
        json.loads(first.read_text(encoding="utf-8")),
    )
    with pytest.raises(map_runtime_catalog.MapRuntimeCatalogError, match="registered by both"):
        map_runtime_catalog.build_package_index([first, second], tmp_path)


def test_generated_world_catalog_discovery_is_recursive(tmp_path: Path):
    generated = _write(
        tmp_path / "content/generated_worlds/world_a/maps/world_a.map_runtime_catalog.json",
        {},
    )
    assert generated.resolve() in map_runtime_catalog.discover_catalog_paths(tmp_path)
