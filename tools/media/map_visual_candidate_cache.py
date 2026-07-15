#!/usr/bin/env python3
"""Content-addressed cache for reviewed layered-map visual candidates."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
from pathlib import Path
from typing import Any


CACHE_ENTRY_VERSION = "map_visual_candidate_cache_entry.v0.1"
_WRITE_LOCK = threading.Lock()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def request_fingerprint(
    pack: dict[str, Any],
    request: dict[str, Any],
    *,
    image_profile_name: str,
    image_model: str,
) -> str:
    """Fingerprint the semantic generation contract, not a repaired prompt pass."""
    references = {}
    for name in ("generation_reference", "style_reference", "control_reference"):
        value = request.get(name)
        if isinstance(value, dict):
            if name == "control_reference" and value.get("semantic_authority") is False:
                continue
            references[name] = {
                "usage": value.get("usage"),
                "sha256": value.get("sha256"),
            }
    payload = {
        "node_id": pack.get("node_id"),
        "worldbook_id": pack.get("worldbook_id"),
        "request_id": request.get("request_id"),
        "role": request.get("role"),
        "prompt_profile": request.get("prompt_profile"),
        "prompt_sections": request.get("prompt_sections"),
        "negative_constraints": request.get("negative_constraints"),
        "generation_mode": request.get("generation_mode"),
        "output_contract": request.get("output_contract"),
        "references": references,
        "required_gates": request.get("required_gates"),
        "image_profile": image_profile_name,
        "image_model": image_model,
    }
    return _sha256_text(_canonical_json(payload))


def review_policy_fingerprint(
    *,
    role: str,
    required_checks: list[str],
    minimum_score: float,
    reviewer_profile_name: str,
    reviewer_model: str,
    policy_revision: str = "v1",
) -> str:
    payload = {
        "role": role,
        "required_checks": required_checks,
        "minimum_score": round(float(minimum_score), 6),
        "reviewer_profile": reviewer_profile_name,
        "reviewer_model": reviewer_model,
        "raw_response_stored": False,
    }
    if policy_revision != "v1":
        payload["policy_revision"] = policy_revision
    return _sha256_text(_canonical_json(payload))


class CandidateCache:
    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()

    def _entry_dir(self, fingerprint: str) -> Path:
        return self.root / fingerprint[:2] / fingerprint

    def restore(
        self,
        *,
        request_fingerprint_value: str,
        review_policy_fingerprint_value: str,
        output_path: Path,
    ) -> dict[str, Any] | None:
        entry_dir = self._entry_dir(request_fingerprint_value)
        metadata_path = entry_dir / "entry.json"
        source_path = entry_dir / "candidate.png"
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        if not isinstance(metadata, dict):
            return None
        if metadata.get("schema_version") != CACHE_ENTRY_VERSION:
            return None
        if metadata.get("request_fingerprint") != request_fingerprint_value:
            return None
        if metadata.get("review_policy_fingerprint") != review_policy_fingerprint_value:
            return None
        if not source_path.is_file():
            return None
        expected_sha = str(metadata.get("candidate_sha256") or "")
        if not expected_sha or sha256_file(source_path) != expected_sha:
            return None
        review = metadata.get("review")
        if not isinstance(review, dict) or review.get("status") != "passed":
            return None
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, output_path)
        return {
            "candidate_path": str(output_path.resolve()),
            "candidate_sha256": expected_sha,
            "review": review,
            "source_prompt_sha256": metadata.get("source_prompt_sha256"),
            "cache_entry_path": str(metadata_path.resolve()),
        }

    def restore_compatible(
        self,
        *,
        review_policy_fingerprint_value: str,
        base_prompt_sha256: str,
        source_prompt_sha256: str,
        provenance_match: dict[str, Any],
        required_checks: list[str],
        minimum_score: float,
        output_path: Path,
        required_policy_revision: str | None = None,
    ) -> dict[str, Any] | None:
        """Recover a passed entry after repair passes or cache-key evolution."""

        for metadata_path in sorted(self.root.glob("*/*/entry.json")):
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                continue
            if not isinstance(metadata, dict):
                continue
            if metadata.get("schema_version") != CACHE_ENTRY_VERSION:
                continue
            stored_base_prompt = metadata.get("base_prompt_sha256")
            stored_source_prompt = metadata.get("source_prompt_sha256")
            prompt_contract_matches = stored_base_prompt == base_prompt_sha256 or (
                stored_base_prompt is None
                and stored_source_prompt in {base_prompt_sha256, source_prompt_sha256}
            )
            legacy_policy_matches = (
                stored_base_prompt is None
                and metadata.get("review_policy_fingerprint")
                == review_policy_fingerprint_value
            )
            if not prompt_contract_matches and not legacy_policy_matches:
                continue
            provenance = metadata.get("provenance")
            if not isinstance(provenance, dict) or any(
                provenance.get(key) != value for key, value in provenance_match.items()
            ):
                continue
            if (
                required_policy_revision is not None
                and provenance.get("review_policy_revision")
                != required_policy_revision
            ):
                continue
            review = metadata.get("review")
            if not isinstance(review, dict) or review.get("status") != "passed":
                continue
            checks = review.get("checks")
            if not isinstance(checks, dict) or any(
                checks.get(check) is not True for check in required_checks
            ):
                continue
            try:
                score = float(review.get("score") or 0)
            except (TypeError, ValueError):
                continue
            if score < minimum_score:
                continue
            source_path = metadata_path.parent / "candidate.png"
            expected_sha = str(metadata.get("candidate_sha256") or "")
            if not source_path.is_file() or not expected_sha:
                continue
            if sha256_file(source_path) != expected_sha:
                continue
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, output_path)
            return {
                "candidate_path": str(output_path.resolve()),
                "candidate_sha256": expected_sha,
                "review": review,
                "source_prompt_sha256": metadata.get("source_prompt_sha256"),
                "base_prompt_sha256": stored_base_prompt,
                "cache_entry_path": str(metadata_path.resolve()),
                "match_mode": (
                    "compatible_base_prompt_and_current_checks"
                    if prompt_contract_matches
                    else "legacy_policy_provenance_and_current_checks"
                ),
            }
        return None

    def store(
        self,
        *,
        request_fingerprint_value: str,
        review_policy_fingerprint_value: str,
        candidate_path: Path,
        review: dict[str, Any],
        base_prompt_sha256: str,
        source_prompt_sha256: str,
        provenance: dict[str, Any],
    ) -> dict[str, Any]:
        if review.get("status") != "passed" or review.get("failed_checks"):
            raise ValueError("only fully passed candidates may enter the cache")
        candidate_sha = sha256_file(candidate_path)
        entry_dir = self._entry_dir(request_fingerprint_value)
        metadata = {
            "schema_version": CACHE_ENTRY_VERSION,
            "request_fingerprint": request_fingerprint_value,
            "review_policy_fingerprint": review_policy_fingerprint_value,
            "candidate_sha256": candidate_sha,
            "base_prompt_sha256": base_prompt_sha256,
            "source_prompt_sha256": source_prompt_sha256,
            "review": review,
            "provenance": provenance,
            "safety": {
                "stores_api_key": False,
                "stores_raw_provider_body": False,
                "stores_raw_prompt": False,
            },
        }
        with _WRITE_LOCK:
            entry_dir.mkdir(parents=True, exist_ok=True)
            token = f"{os.getpid()}.{threading.get_ident()}"
            image_tmp = entry_dir / f"candidate.png.{token}.tmp"
            metadata_tmp = entry_dir / f"entry.json.{token}.tmp"
            shutil.copy2(candidate_path, image_tmp)
            metadata_tmp.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(image_tmp, entry_dir / "candidate.png")
            os.replace(metadata_tmp, entry_dir / "entry.json")
        return {
            "cache_entry_path": str((entry_dir / "entry.json").resolve()),
            "candidate_sha256": candidate_sha,
        }
