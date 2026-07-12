"""Strict catalog discovery for reviewed MapRuntimePackage artifacts."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable


_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCHEMA_PATH = _REPO_ROOT / "shared/schemas/map_runtime_catalog.v0.1.schema.json"
CATALOG_SCHEMA_VERSION = "map_runtime_catalog.v0.1"
_V01 = "map_runtime_package.v0.1"
_V02 = "map_runtime_package.v0.2"
_ALLOWED_PACKAGE_DIRS = (
    Path("examples/map_runtime_packages"),
    Path("examples/map_runtime_packages_v02"),
    Path("content/generated_worlds"),
)
_ENTRY_KEYS = {"node_id", "authorization_status", "quality_status", "packages"}
_PACKAGE_REF_KEYS = {"package_id", "path", "release_status"}
_CATALOG_KEYS = {
    "schema_version", "catalog_id", "generated_at", "source_policy", "summary", "entries"
}


class MapRuntimeCatalogError(ValueError):
    """Raised when a catalog cannot be trusted as a runtime registry."""


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MapRuntimeCatalogError(f"{label} is unreadable: {path}") from exc
    if not isinstance(value, dict):
        raise MapRuntimeCatalogError(f"{label} root must be an object: {path}")
    return value


def _validate_schema(catalog: dict[str, Any]) -> None:
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:
        raise MapRuntimeCatalogError("catalog schema validation is unavailable") from exc
    schema = _load_object(_SCHEMA_PATH, "map runtime catalog schema")
    errors = sorted(
        Draft202012Validator(schema).iter_errors(catalog),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        raise MapRuntimeCatalogError(f"catalog schema failed: {errors[0].message}")


def _resolve_package_path(repo_root: Path, raw_path: str) -> Path:
    root = repo_root.resolve()
    candidate = Path(raw_path)
    resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()
    if not resolved.is_relative_to(root):
        raise MapRuntimeCatalogError(f"package path escapes repository: {raw_path}")
    if not any(
        resolved.is_relative_to((root / allowed).resolve())
        for allowed in _ALLOWED_PACKAGE_DIRS
    ):
        raise MapRuntimeCatalogError(f"package path is outside allowed roots: {raw_path}")
    if not resolved.is_file():
        raise MapRuntimeCatalogError(f"package file is missing: {raw_path}")
    return resolved


def _validate_package_ref(
    *, repo_root: Path, node_id: str, schema_version: str, value: Any,
) -> Path:
    if schema_version not in {_V01, _V02}:
        raise MapRuntimeCatalogError(
            f"catalog node {node_id!r} declares unsupported package schema {schema_version!r}"
        )
    if not isinstance(value, dict) or set(value) != _PACKAGE_REF_KEYS:
        raise MapRuntimeCatalogError(
            f"catalog node {node_id!r} package ref has invalid fields"
        )
    package_id = value.get("package_id")
    raw_path = value.get("path")
    release_status = value.get("release_status")
    if not isinstance(package_id, str) or not package_id:
        raise MapRuntimeCatalogError(f"catalog node {node_id!r} has no package_id")
    if not isinstance(raw_path, str) or not raw_path:
        raise MapRuntimeCatalogError(f"catalog node {node_id!r} has no package path")
    allowed_statuses = {"published"} if schema_version == _V01 else {"published_for_gate_review"}
    if release_status not in allowed_statuses:
        raise MapRuntimeCatalogError(
            f"catalog node {node_id!r} package is not published: {release_status!r}"
        )
    path = _resolve_package_path(repo_root, raw_path)
    package = _load_object(path, "map runtime package")
    expected = {
        "schema_version": schema_version,
        "package_id": package_id,
        "node_id": node_id,
    }
    for field, expected_value in expected.items():
        if package.get(field) != expected_value:
            raise MapRuntimeCatalogError(
                f"catalog node {node_id!r} {field} mismatch: "
                f"expected {expected_value!r}, found {package.get(field)!r}"
            )
    return path


def load_catalog(catalog_path: Path, repo_root: Path | None = None) -> dict[str, Any]:
    """Load and validate one catalog and every referenced package."""
    root = (repo_root or _REPO_ROOT).resolve()
    catalog = _load_object(catalog_path, "map runtime catalog")
    _validate_schema(catalog)
    if set(catalog) != _CATALOG_KEYS:
        raise MapRuntimeCatalogError("map runtime catalog has invalid top-level fields")
    if catalog.get("schema_version") != CATALOG_SCHEMA_VERSION:
        raise MapRuntimeCatalogError("unsupported map runtime catalog schema_version")
    entries = catalog.get("entries")
    if not isinstance(entries, list) or not entries:
        raise MapRuntimeCatalogError("map runtime catalog entries must be a non-empty list")
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != _ENTRY_KEYS:
            raise MapRuntimeCatalogError("catalog entry has invalid fields")
        node_id = entry.get("node_id")
        if not isinstance(node_id, str) or not node_id:
            raise MapRuntimeCatalogError("catalog entry node_id must be a non-empty string")
        if node_id in seen:
            raise MapRuntimeCatalogError(f"duplicate node_id in catalog: {node_id}")
        seen.add(node_id)
        if entry.get("quality_status") not in {"reviewed", "published"}:
            raise MapRuntimeCatalogError(f"catalog node {node_id!r} is not reviewed")
        if entry.get("authorization_status") not in {"pending", "approved"}:
            raise MapRuntimeCatalogError(
                f"catalog node {node_id!r} has invalid authorization status"
            )
        packages = entry.get("packages")
        if not isinstance(packages, dict) or _V01 not in packages:
            raise MapRuntimeCatalogError(f"catalog node {node_id!r} has no v0.1 package")
        for schema_version, package_ref in packages.items():
            _validate_package_ref(
                repo_root=root,
                node_id=node_id,
                schema_version=str(schema_version),
                value=package_ref,
            )
    return catalog


def default_catalog_path(repo_root: Path | None = None) -> Path:
    return (repo_root or _REPO_ROOT) / "examples/map_runtime_catalogs/mvp_map_runtime_catalog.v0.1.json"


def discover_catalog_paths(repo_root: Path | None = None) -> list[Path]:
    """Discover the built-in registry, generated-world registries, and one override."""
    root = (repo_root or _REPO_ROOT).resolve()
    paths: list[Path] = []
    default = default_catalog_path(root)
    if default.is_file():
        paths.append(default)
    generated_root = root / "content/generated_worlds"
    if generated_root.is_dir():
        paths.extend(sorted(generated_root.rglob("*.map_runtime_catalog.json")))
    configured = os.environ.get("AI_TD_MAP_RUNTIME_CATALOG")
    if configured:
        configured_path = Path(configured).expanduser()
        paths.append(
            configured_path if configured_path.is_absolute() else root / configured_path
        )
    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            deduped.append(resolved)
    return deduped


def build_package_index(
    catalog_paths: Iterable[Path], repo_root: Path | None = None,
) -> tuple[dict[str, Path], dict[str, Path]]:
    """Build immutable node indexes, rejecting cross-catalog shadowing."""
    root = (repo_root or _REPO_ROOT).resolve()
    v01: dict[str, Path] = {}
    v02: dict[str, Path] = {}
    owners: dict[str, Path] = {}
    for catalog_path in catalog_paths:
        catalog = load_catalog(catalog_path, root)
        for entry in catalog["entries"]:
            node_id = entry["node_id"]
            if node_id in owners:
                raise MapRuntimeCatalogError(
                    f"node {node_id!r} is registered by both {owners[node_id]} and {catalog_path}"
                )
            owners[node_id] = catalog_path
            for schema_version, package_ref in entry["packages"].items():
                path = _resolve_package_path(root, package_ref["path"])
                if schema_version == _V01:
                    v01[node_id] = path
                elif schema_version == _V02:
                    v02[node_id] = path
    return v01, v02
