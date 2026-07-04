#!/usr/bin/env python3
"""Audit map visual quality assumptions for MVP battle maps.

This is a deterministic evidence check, not a vision model. It catches the
specific failure mode we saw during frontend review: a technically loadable map
layer being treated as player-ready even when it is shared across multiple
nodes, depends on overlay correction, or has only weak/manual visual evidence.
"""

from __future__ import annotations

import argparse
import json
import struct
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPORT_VERSION = "map_visual_quality_report.v0.1"
DEFAULT_MANIFEST = ROOT / "game_data/media/map_visual_reference/map_visual_reference_manifest.v0.1.json"
DEFAULT_PACKAGE_DIR = ROOT / "examples/map_runtime_packages"
DEFAULT_OUTPUT = ROOT / "examples/review_packs/map_visual_quality_report.v0.1.json"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def resolve_local_path(value: Any) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def png_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        with path.open("rb") as handle:
            header = handle.read(24)
    except FileNotFoundError:
        return None
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", header[16:24])


def is_player_ready(layer: dict[str, Any]) -> bool:
    return (
        layer.get("authority") == "published_visual_layer"
        and layer.get("player_visible_quality") == "passed"
    )


def layer_key(layer: dict[str, Any]) -> str:
    return str(layer.get("sha256") or layer.get("local_path") or layer.get("url") or "unknown")


def audit_layer_file(layer: dict[str, Any]) -> tuple[list[str], list[str]]:
    issues: list[str] = []
    warnings: list[str] = []
    path = resolve_local_path(layer.get("local_path"))
    if path is None:
        issues.append("missing_local_path")
        return issues, warnings
    if not path.exists():
        issues.append("local_path_not_found")
        return issues, warnings
    dims = png_dimensions(path)
    if dims is None:
        issues.append("not_a_png")
        return issues, warnings
    width, height = dims
    if width != layer.get("width") or height != layer.get("height"):
        issues.append("manifest_dimensions_mismatch")
    ratio = width / height if height else 0
    if ratio < 1.55 or ratio > 1.95:
        warnings.append("unusual_battle_map_aspect_ratio")
    return issues, warnings


def audit_runtime_package(path: Path) -> dict[str, Any]:
    package = load_json(path)
    node_id = package.get("node_id")
    layers = [layer for layer in as_list(package.get("visual_layers")) if isinstance(layer, dict)]
    player_layers = [layer for layer in layers if is_player_ready(layer)]
    issues: list[str] = []
    warnings: list[str] = []

    if not player_layers:
        issues.append("missing_player_ready_visual_layer")

    for layer in player_layers:
        file_issues, file_warnings = audit_layer_file(layer)
        issues.extend(file_issues)
        warnings.extend(file_warnings)
        if layer.get("logic_alignment_status") != "passed":
            warnings.append("player_layer_needs_overlay_correction")
        deterministic_runtime_background = (
            layer.get("role") == "battle_runtime_background"
            and layer.get("logic_alignment_status") == "passed"
        )
        if (
            not deterministic_runtime_background
            and layer.get("source_kind") in {None, "", "human_reviewed_painted_visual_runtime_overlay"}
        ):
            warnings.append("player_layer_review_is_manual_or_weakly_described")

    for role in ("battle_control_sketch", "battle_reference_board"):
        for layer in layers:
            if layer.get("role") == role and layer.get("authority") != "reference_only":
                issues.append(f"{role}_is_not_reference_only")

    return {
        "package_path": rel(path),
        "package_id": package.get("package_id"),
        "node_id": node_id,
        "player_ready_layer_count": len(player_layers),
        "player_ready_layers": [
            {
                "role": layer.get("role"),
                "local_path": layer.get("local_path"),
                "sha256": layer.get("sha256"),
                "source_kind": layer.get("source_kind"),
                "review_status": layer.get("review_status"),
                "logic_alignment_status": layer.get("logic_alignment_status"),
            }
            for layer in player_layers
        ],
        "issues": sorted(set(issues)),
        "warnings": sorted(set(warnings)),
        "status": "failed" if issues else ("passed_with_warnings" if warnings else "passed"),
    }


def build_report(manifest_path: Path, package_dir: Path) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    packages = [audit_runtime_package(path) for path in sorted(package_dir.glob("*.map_runtime_package.json"))]
    issues: list[str] = []
    warnings: list[str] = []

    items = [item for item in as_list(manifest.get("items")) if isinstance(item, dict)]
    manifest_player_layers = [item for item in items if is_player_ready(item)]
    if not manifest_player_layers:
        issues.append("manifest_missing_player_ready_visual_layer")
    for item in manifest_player_layers:
        file_issues, file_warnings = audit_layer_file(item)
        issues.extend(f"manifest_{issue}" for issue in file_issues)
        warnings.extend(f"manifest_{warning}" for warning in file_warnings)
        if item.get("logic_alignment_status") != "passed":
            warnings.append("manifest_player_layer_needs_overlay_correction")

    by_layer: dict[str, list[str]] = defaultdict(list)
    for package in packages:
        for layer in as_list(package.get("player_ready_layers")):
            if isinstance(layer, dict):
                by_layer[layer_key(layer)].append(str(package.get("node_id")))

    shared_groups = [
        {
            "layer_key": key,
            "node_ids": sorted(set(nodes)),
            "node_count": len(set(nodes)),
        }
        for key, nodes in sorted(by_layer.items())
        if len(set(nodes)) > 1
    ]
    if shared_groups:
        warnings.append("shared_player_visual_layer_across_nodes")
    if len(packages) > 1 and len(by_layer) < len(packages):
        warnings.append("node_specific_player_visual_layers_missing")

    package_status_counts = Counter(str(package.get("status")) for package in packages)
    issue_counts = Counter()
    warning_counts = Counter(warnings)
    for package in packages:
        issue_counts.update(as_list(package.get("issues")))
        warning_counts.update(as_list(package.get("warnings")))
    issue_counts.update(issues)

    status = "failed" if issue_counts else ("passed_with_warnings" if warning_counts else "passed")
    return {
        "schema_version": REPORT_VERSION,
        "report_id": "mvp_map_visual_quality_report",
        "manifest_path": rel(manifest_path),
        "package_dir": rel(package_dir),
        "status": status,
        "summary": {
            "map_package_count": len(packages),
            "node_ids": [package.get("node_id") for package in packages],
            "manifest_player_ready_layer_count": len(manifest_player_layers),
            "shared_player_visual_layer_group_count": len(shared_groups),
            "package_status_counts": dict(sorted(package_status_counts.items())),
            "issue_counts": dict(sorted(issue_counts.items())),
            "warning_counts": dict(sorted(warning_counts.items())),
        },
        "shared_player_visual_layer_groups": shared_groups,
        "packages": packages,
        "notes": [
            "This audit is deterministic and does not replace human or vision-model map review.",
            "Warnings are evidence for follow-up work; only missing/load-invalid player layers are hard failures.",
            "Runtime truth remains MapRuntimePackage paths, build slots, objectives, and spawn points.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit MVP map visual quality assumptions.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--package-dir", default=str(DEFAULT_PACKAGE_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as a non-zero exit for manual visual hardening runs.",
    )
    args = parser.parse_args()

    report = build_report(Path(args.manifest), Path(args.package_dir))
    write_json(Path(args.output), report)
    print(f"map visual quality: {report['status']}")
    summary = as_obj(report.get("summary"))
    print(f"- map packages: {summary.get('map_package_count')}")
    print(f"- shared player visual layer groups: {summary.get('shared_player_visual_layer_group_count')}")
    print(f"- warnings: {summary.get('warning_counts')}")
    print(f"- output: {args.output}")
    if report["status"] == "failed":
        return 1
    if args.strict and report["status"] == "passed_with_warnings":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
