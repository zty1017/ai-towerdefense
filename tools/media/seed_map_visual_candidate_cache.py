#!/usr/bin/env python3
"""Import previously passed map candidates into the current reviewed cache."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import generate_layered_map_visual_candidates as candidate_generator
import image_provider
import map_visual_candidate_cache
import map_visual_closed_loop
import vision_review


def _candidate_path(report_path: Path, raw_path: str) -> Path | None:
    direct = Path(raw_path)
    if direct.is_file():
        return direct
    parts = direct.parts
    if "visual_candidates" in parts:
        tail = parts[parts.index("visual_candidates") + 1 :]
        relocated = report_path.parent.joinpath(*tail)
        if relocated.is_file():
            return relocated
    fallback = report_path.parent / direct.name
    return fallback if fallback.is_file() else None


def seed_report(
    request_pack_path: Path,
    report_path: Path,
    cache: map_visual_candidate_cache.CandidateCache,
    image_profile: image_provider.ImageProfile,
    vision_profile: vision_review.VisionProfile,
    minimum_score: float,
) -> dict[str, Any]:
    pack = candidate_generator.load_json(request_pack_path)
    report = candidate_generator.load_json(report_path)
    requests = {
        str(item.get("request_id")): item
        for item in pack.get("requests", [])
        if isinstance(item, dict)
    }
    imported = []
    rejected = []
    for result in report.get("results", []):
        if not isinstance(result, dict) or result.get("status") != "passed":
            continue
        request_id = str(result.get("request_id") or "")
        request = requests.get(request_id)
        attempts = [item for item in result.get("attempts", []) if isinstance(item, dict)]
        passed_attempts = [
            item
            for item in attempts
            if isinstance(item.get("review"), dict)
            and item["review"].get("status") == "passed"
        ]
        if request is None or not passed_attempts:
            rejected.append({"request_id": request_id, "reason": "missing_request_or_passed_review"})
            continue
        attempt = passed_attempts[-1]
        path = _candidate_path(report_path, str(attempt.get("candidate_path") or ""))
        if path is None:
            rejected.append({"request_id": request_id, "reason": "candidate_not_found"})
            continue
        if map_visual_candidate_cache.sha256_file(path) != str(attempt.get("candidate_sha256") or ""):
            rejected.append({"request_id": request_id, "reason": "candidate_sha256_mismatch"})
            continue
        role = str(request.get("role") or "")
        review = attempt["review"]
        required = map_visual_closed_loop.required_review_checks(role)
        checks = review.get("checks") if isinstance(review.get("checks"), dict) else {}
        score = float(review.get("score") or 0)
        contract = request.get("output_contract")
        contract = contract if isinstance(contract, dict) else {}
        ratio_text = str(contract.get("ratio") or "")
        ratio = None
        if ":" in ratio_text:
            left, right = ratio_text.split(":", 1)
            ratio = int(left) / int(right)
        deterministic, metrics = map_visual_closed_loop.deterministic_issues(path, role, ratio)
        failed = [*deterministic, *[name for name in required if checks.get(name) is not True]]
        if failed or score < minimum_score:
            rejected.append({"request_id": request_id, "reason": "current_policy_failed", "failed_checks": failed})
            continue
        normalized_review = dict(review)
        normalized_review.update(
            {"status": "passed", "failed_checks": [], "deterministic_metrics": metrics}
        )
        request_fp, policy_fp = map_visual_closed_loop.cache_fingerprints(
            pack, request, image_profile, vision_profile, minimum_score
        )
        stored = cache.store(
            request_fingerprint_value=request_fp,
            review_policy_fingerprint_value=policy_fp,
            candidate_path=path,
            review=normalized_review,
            source_prompt_sha256=str(attempt.get("prompt_sha256") or ""),
            provenance={
                "node_id": pack.get("node_id"),
                "worldbook_id": pack.get("worldbook_id"),
                "request_id": request_id,
                "role": role,
                "imported_from_report_sha256": map_visual_candidate_cache.sha256_file(report_path),
            },
        )
        imported.append({"request_id": request_id, "role": role, **stored})
    return {
        "report_path": str(report_path.resolve()),
        "imported": imported,
        "rejected": rejected,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request-pack", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path, action="append")
    parser.add_argument("--cache-dir", type=Path, default=map_visual_closed_loop.resolve_cache_dir())
    parser.add_argument("--image-profile", default="agnes_image_flash", choices=sorted(image_provider.PROFILES))
    parser.add_argument("--vision-profile", default="agnes_multimodal_flash", choices=sorted(vision_review.PROFILES))
    parser.add_argument("--minimum-score", type=float, default=map_visual_closed_loop.DEFAULT_MIN_VISION_SCORE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cache = map_visual_candidate_cache.CandidateCache(args.cache_dir)
    results = [
        seed_report(
            args.request_pack,
            report,
            cache,
            image_provider.PROFILES[args.image_profile],
            vision_review.PROFILES[args.vision_profile],
            args.minimum_score,
        )
        for report in args.report
    ]
    summary = {
        "cache_dir": str(args.cache_dir.expanduser().resolve()),
        "imported_count": sum(len(item["imported"]) for item in results),
        "rejected_count": sum(len(item["rejected"]) for item in results),
        "results": results,
    }
    if args.output:
        candidate_generator.write_json(args.output, summary)
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["imported_count"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
