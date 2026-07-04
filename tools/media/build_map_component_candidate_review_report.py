#!/usr/bin/env python3
"""Build a review report for MapComponent generation candidates.

Until real generated artifacts are imported, this report lists each deterministic
SVG baseline as a fixture candidate and blocks promotion. The baseline fixture
is useful evidence, but it is not a generated image/video result.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPORT_VERSION = "map_component_candidate_review_report.v0.1"
DEFAULT_REQUEST_PACK = ROOT / "examples/review_packs/map_component_generation_request_pack.v0.1.json"
DEFAULT_MANIFEST = ROOT / "game_data/media/map_components/map_component_media_manifest.v0.1.json"
DEFAULT_OUTPUT = ROOT / "examples/review_packs/map_component_candidate_review_report.v0.1.json"

USAGE_POLICY = [
    "review_gate_only",
    "not_runtime_semantic_source",
    "no_image_to_map_semantic_inference",
    "baseline_fixture_is_not_generated_candidate",
    "no_frontend_default_consumption",
    "no_provider_or_prompt_payload",
    "no_external_temporary_url",
]
NEXT_ACTIONS = [
    "import reviewed generation artifact",
    "run visual QA against baseline and StylePack role",
    "run cutout and normalization checks",
    "refresh MapStyleComponentBindingReport after accepted local artifacts exist",
    "run explicit promotion gate before any manifest replacement",
]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def build_candidate(request: dict[str, Any]) -> dict[str, Any]:
    component_id = str(request.get("component_id") or "unknown_component")
    return {
        "candidate_id": f"{component_id}.baseline_fixture_candidate",
        "request_id": request.get("request_id"),
        "component_id": component_id,
        "component_role": request.get("component_role"),
        "style_pack_id": request.get("style_pack_id"),
        "node_id": request.get("node_id"),
        "candidate_kind": "baseline_fixture_candidate",
        "review_status": "no_generated_candidate_yet",
        "promotion_recommendation": "do_not_promote",
        "promotion_allowed_now": False,
        "baseline_local_path": request.get("baseline_local_path"),
        "baseline_sha256": request.get("baseline_sha256"),
        "target_size": request.get("target_size"),
        "findings": [
            "Deterministic SVG baseline is present only as a fixture candidate.",
            "No generated image or video artifact has been imported for this component.",
            "Fixture SVG cannot replace itself as a generated candidate and cannot pass promotion.",
        ],
        "required_next_actions": NEXT_ACTIONS,
        "usage_policy": USAGE_POLICY,
    }


def build_report(
    request_pack_path: Path,
    manifest_path: Path,
    *,
    output_path: Path,
    created_at: str | None,
) -> dict[str, Any]:
    request_pack = as_obj(load_json(request_pack_path))
    candidates = [
        build_candidate(request)
        for request in as_list(request_pack.get("requests"))
        if isinstance(request, dict)
    ]
    status_counts = Counter(str(candidate.get("review_status")) for candidate in candidates)
    kind_counts = Counter(str(candidate.get("candidate_kind")) for candidate in candidates)
    generated_count = kind_counts.get("generated_candidate", 0)
    promotable_count = len(
        [
            candidate
            for candidate in candidates
            if candidate.get("promotion_allowed_now") is True
            and candidate.get("promotion_recommendation") == "eligible_for_promotion"
        ]
    )
    blocked_count = len(candidates) - promotable_count
    return {
        "schema_version": REPORT_VERSION,
        "report_id": "map_component_candidate_review_report_v0_1",
        "created_at": created_at or str(request_pack.get("created_at") or "2026-07-05T00:00:00Z"),
        "source_request_pack_path": rel(request_pack_path),
        "source_manifest_path": rel(manifest_path),
        "status": "blocked_from_promotion" if blocked_count else "passed",
        "usage_policy": USAGE_POLICY,
        "summary": {
            "candidate_count": len(candidates),
            "baseline_fixture_candidate_count": kind_counts.get("baseline_fixture_candidate", 0),
            "generated_candidate_count": generated_count,
            "promotable_count": promotable_count,
            "blocked_from_promotion_count": blocked_count,
            "no_generated_candidate_yet_count": status_counts.get("no_generated_candidate_yet", 0),
            "status_counts": dict(sorted(status_counts.items())),
            "candidate_kind_counts": dict(sorted(kind_counts.items())),
        },
        "candidates": candidates,
        "validation": {
            "validator": "tools/media/validate_map_component_candidate_review_report.py",
            "commands": [
                f"python3 tools/media/validate_map_component_candidate_review_report.py {rel(output_path)}"
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build MapComponentCandidateReviewReport v0.1.")
    parser.add_argument("--request-pack", default=str(DEFAULT_REQUEST_PACK))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--created-at", default=None)
    args = parser.parse_args()

    request_pack_path = resolve_path(args.request_pack)
    manifest_path = resolve_path(args.manifest)
    output_path = resolve_path(args.output)
    report = build_report(
        request_pack_path,
        manifest_path,
        output_path=output_path,
        created_at=args.created_at,
    )
    write_json(output_path, report)
    print(f"OK: wrote {output_path}")
    print(f"- status: {report['status']}")
    print(f"- candidate_count: {report['summary']['candidate_count']}")
    print(f"- generated_candidate_count: {report['summary']['generated_candidate_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
