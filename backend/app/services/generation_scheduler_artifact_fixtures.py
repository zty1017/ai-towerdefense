"""Provider artifact fixture catalog used by the generation scheduler."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any


_FIXTURE_DIR = Path("examples/provider_artifact_staging")
_FIXTURE_PROFILES = {
    "default": {
        "aliases": {"", "default", "summary"},
        "provider_output_envelope": (
            _FIXTURE_DIR / "p1b_provider_artifact_staging.source_envelope.json"
        ),
        "provider_artifact_staging": (
            _FIXTURE_DIR / "p1b_provider_artifact_staging.example.json"
        ),
        "provider_artifact_promotion_report": (
            _FIXTURE_DIR / "p1b_provider_artifact_promotion_report.example.json"
        ),
    },
    "image_failure": {
        "aliases": {"image_failure", "image"},
        "provider_output_envelope": (
            _FIXTURE_DIR / "p1b_provider_image_artifact_staging.source_envelope.json"
        ),
        "provider_artifact_staging": (
            _FIXTURE_DIR / "p1b_provider_image_artifact_staging.example.json"
        ),
        "provider_artifact_promotion_report": (
            _FIXTURE_DIR
            / "p1b_provider_image_artifact_promotion_report.example.json"
        ),
    },
}


def normalize_provider_artifact_fixture_profile(
    profile: str | None,
    *,
    error_cls: type[Exception] = ValueError,
) -> str:
    """Return the canonical fixture profile name for a user/API alias."""

    if profile is None:
        return "default"
    requested = str(profile)
    for normalized, profile_config in _FIXTURE_PROFILES.items():
        aliases = profile_config["aliases"]
        if requested in aliases:
            return normalized
    raise error_cls(f"unknown provider artifact profile: {profile}")


def provider_artifact_fixture_paths(
    profile: str | None,
    *,
    repo_root: Path,
    error_cls: type[Exception] = ValueError,
) -> tuple[Path, Path, Path, str]:
    normalized_profile = normalize_provider_artifact_fixture_profile(
        profile,
        error_cls=error_cls,
    )
    profile_config = _FIXTURE_PROFILES[normalized_profile]
    return (
        repo_root / profile_config["provider_output_envelope"],
        repo_root / profile_config["provider_artifact_staging"],
        repo_root / profile_config["provider_artifact_promotion_report"],
        normalized_profile,
    )


def provider_artifact_fixture_metadata(
    profile: str | None,
    *,
    repo_root: Path,
    load_json: Callable[[Path], Any],
    rel_path: Callable[[Path], str],
    error_cls: type[Exception] = ValueError,
) -> dict[str, str]:
    envelope_path, _, _, normalized_profile = provider_artifact_fixture_paths(
        profile,
        repo_root=repo_root,
        error_cls=error_cls,
    )
    envelope = load_json(envelope_path)
    source = envelope.get("source", {}) if isinstance(envelope.get("source"), dict) else {}
    provider_call = (
        envelope.get("provider_call", {})
        if isinstance(envelope.get("provider_call"), dict)
        else {}
    )
    schedule_item_id = str(source.get("schedule_item_id") or "")
    authorization_ref = str(provider_call.get("authorization_ref") or "")
    if not schedule_item_id or not authorization_ref:
        raise error_cls(
            f"provider artifact fixture profile is missing source refs: {normalized_profile}"
        )
    return {
        "artifact_profile": normalized_profile,
        "schedule_item_id": schedule_item_id,
        "authorization_ref": authorization_ref,
        "provider_output_envelope": rel_path(envelope_path),
    }
