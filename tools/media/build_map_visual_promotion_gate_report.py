#!/usr/bin/env python3
"""Build a deterministic promotion gate report for map visual candidates.

This gate does not judge visual beauty. It verifies a stricter contract:
review-only, rejected, blocked, or still-awaiting map candidates must not be
referenced by any player-facing published visual layer.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPORT_VERSION = "map_visual_promotion_gate_report.v0.1"
DEFAULT_MANIFEST = ROOT / "game_data/media/map_visual_reference/map_visual_reference_manifest.v0.1.json"
DEFAULT_PACKAGE_DIR = ROOT / "examples/map_runtime_packages"
DEFAULT_REVIEW_PACKS = [
    ROOT / "examples/review_packs/node_map_painted_candidate_review.v0.1.json",
    ROOT / "examples/review_packs/node_map_painted_candidate_review.v0.2.json",
    ROOT / "examples/review_packs/controlled_map_candidate_review.v0.1.json",
    ROOT / "examples/review_packs/controlled_map_text_fallback_candidate_review.v0.1.json",
    ROOT / "examples/review_packs/map_candidate_overlay_visual_review.v0.1.json",
    ROOT / "examples/review_packs/topology_constrained_map_overlay_visual_review.v0.1.json",
    ROOT / "examples/review_packs/map_layout_reconciliation_plan.v0.1.json",
    ROOT / "examples/review_packs/map_patch_overlay_review.v0.1.json",
]
DEFAULT_OUTPUT = ROOT / "examples/review_packs/map_visual_promotion_gate_report.v0.1.json"

BLOCKING_REVIEW_STATUSES = {
    "needs_regeneration",
    "awaiting_provider_or_paintover_output",
    "needs_layout_reconciliation",
    "needs_path_reprojection",
    "needs_prompt_iteration",
    "review_only_not_runtime_ready",
}
BLOCKING_RUNTIME_PROMOTIONS = {"blocked_until_explicit_review"}
BLOCKING_PROMOTION_RECOMMENDATIONS = {"do_not_promote"}


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


def norm_path(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return ""
    if value.startswith("/assets/map_visual_reference/"):
        return "game_data/media/map_visual_reference/" + value.rsplit(
            "/assets/map_visual_reference/",
            1,
        )[1]
    path = Path(value)
    if path.is_absolute():
        try:
            return path.resolve().relative_to(ROOT).as_posix()
        except ValueError:
            return path.as_posix()
    return path.as_posix()


def append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def candidate_paths_from_record(record: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for key in (
        "candidate_path",
        "normalized_path",
        "overlay_review_png_path",
        "patched_overlay_review_png_path",
        "source_normalized_path",
    ):
        append_unique(paths, norm_path(record.get(key)))
    return paths


def blocking_reasons(record: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    review_status = record.get("review_status")
    runtime_promotion = record.get("runtime_promotion")
    promotion_recommendation = record.get("promotion_recommendation")
    status = record.get("status")
    promotion_allowed_now = record.get("promotion_allowed_now")

    if review_status in BLOCKING_REVIEW_STATUSES:
        reasons.append(f"review_status:{review_status}")
    if runtime_promotion in BLOCKING_RUNTIME_PROMOTIONS:
        reasons.append(f"runtime_promotion:{runtime_promotion}")
    if promotion_recommendation in BLOCKING_PROMOTION_RECOMMENDATIONS:
        reasons.append(f"promotion_recommendation:{promotion_recommendation}")
    if status in BLOCKING_REVIEW_STATUSES:
        reasons.append(f"status:{status}")
    if promotion_allowed_now is False:
        reasons.append("promotion_allowed_now:false")
    if record.get("blocking_findings"):
        reasons.append("blocking_findings_present")
    return sorted(set(reasons))


def collect_blocked_candidates(review_pack_paths: list[Path]) -> list[dict[str, Any]]:
    blocked: dict[str, dict[str, Any]] = {}
    for path in review_pack_paths:
        report = load_json(path)
        records = []
        for key in ("candidates", "reviews", "recommendations", "artifacts"):
            records.extend(
                record for record in as_list(report.get(key)) if isinstance(record, dict)
            )
        for record in records:
            reasons = blocking_reasons(record)
            paths = candidate_paths_from_record(record)
            if not reasons or not paths:
                continue
            for candidate_path in paths:
                entry = blocked.setdefault(
                    candidate_path,
                    {
                        "candidate_path": candidate_path,
                        "node_ids": [],
                        "source_reports": [],
                        "blocking_reasons": [],
                    },
                )
                append_unique(entry["node_ids"], str(record.get("node_id") or "unknown"))
                append_unique(entry["source_reports"], rel(path))
                for reason in reasons:
                    append_unique(entry["blocking_reasons"], reason)
    return sorted(blocked.values(), key=lambda item: item["candidate_path"])


def is_published_player_layer(layer: dict[str, Any]) -> bool:
    return layer.get("authority") == "published_visual_layer" and layer.get(
        "player_visible_quality"
    ) == "passed"


def collect_published_layers(manifest_path: Path, package_dir: Path) -> list[dict[str, Any]]:
    layers: list[dict[str, Any]] = []
    manifest = load_json(manifest_path)
    for item in as_list(manifest.get("items")):
        if not isinstance(item, dict) or not is_published_player_layer(item):
            continue
        layers.append(
            {
                "source": rel(manifest_path),
                "node_id": "manifest",
                "role": item.get("role"),
                "local_path": norm_path(item.get("local_path")),
                "url": item.get("url"),
                "sha256": item.get("sha256"),
                "review_status": item.get("review_status"),
                "logic_alignment_status": item.get("logic_alignment_status"),
            }
        )
    for package_path in sorted(package_dir.glob("*.map_runtime_package.json")):
        package = load_json(package_path)
        for layer in as_list(package.get("visual_layers")):
            if not isinstance(layer, dict) or not is_published_player_layer(layer):
                continue
            layers.append(
                {
                    "source": rel(package_path),
                    "node_id": package.get("node_id"),
                    "role": layer.get("role"),
                    "local_path": norm_path(layer.get("local_path")),
                    "url": layer.get("url"),
                    "sha256": layer.get("sha256"),
                    "review_status": layer.get("review_status"),
                    "logic_alignment_status": layer.get("logic_alignment_status"),
                }
            )
    return layers


def build_report(
    *,
    manifest_path: Path,
    package_dir: Path,
    review_pack_paths: list[Path],
) -> dict[str, Any]:
    blocked_candidates = collect_blocked_candidates(review_pack_paths)
    published_layers = collect_published_layers(manifest_path, package_dir)
    blocked_by_path = {candidate["candidate_path"]: candidate for candidate in blocked_candidates}
    violations = []
    for layer in published_layers:
        local_path = layer.get("local_path")
        if local_path in blocked_by_path:
            violations.append(
                {
                    "violation_id": f"blocked_candidate_published_{len(violations) + 1:02d}",
                    "blocked_candidate": blocked_by_path[local_path],
                    "published_layer": layer,
                }
            )
    reason_counts = Counter()
    for candidate in blocked_candidates:
        reason_counts.update(as_list(candidate.get("blocking_reasons")))
    status = "failed" if violations else "passed"
    return {
        "schema_version": REPORT_VERSION,
        "report_id": "mvp_map_visual_promotion_gate",
        "status": status,
        "policy": [
            "Review-only, rejected, blocked, or still-awaiting map candidates cannot become player-facing published visual layers.",
            "MapRuntimePackage remains gameplay truth; painted maps are presentation layers that require explicit promotion.",
            "This deterministic gate does not replace human or vision-model visual quality review.",
        ],
        "inputs": {
            "manifest_path": rel(manifest_path),
            "package_dir": rel(package_dir),
            "review_pack_paths": [rel(path) for path in review_pack_paths],
        },
        "summary": {
            "blocked_candidate_count": len(blocked_candidates),
            "published_player_layer_count": len(published_layers),
            "violation_count": len(violations),
            "blocking_reason_counts": dict(sorted(reason_counts.items())),
        },
        "blocked_candidates": blocked_candidates,
        "published_player_layers": published_layers,
        "violations": violations,
        "next_required_gate": "explicit_map_visual_promotion_report",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build MapVisualPromotionGate report.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--package-dir", default=str(DEFAULT_PACKAGE_DIR))
    parser.add_argument(
        "--review-pack",
        action="append",
        default=None,
        help="Review pack JSON path. Can be repeated. Defaults to MVP map review packs.",
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    review_pack_paths = (
        [Path(path) for path in args.review_pack]
        if args.review_pack
        else DEFAULT_REVIEW_PACKS
    )
    report = build_report(
        manifest_path=Path(args.manifest),
        package_dir=Path(args.package_dir),
        review_pack_paths=review_pack_paths,
    )
    write_json(Path(args.output), report)
    summary = as_obj(report.get("summary"))
    print(f"map visual promotion gate: {report['status']}")
    print(f"- blocked candidates: {summary.get('blocked_candidate_count')}")
    print(f"- published player layers: {summary.get('published_player_layer_count')}")
    print(f"- violations: {summary.get('violation_count')}")
    print(f"- output: {args.output}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
