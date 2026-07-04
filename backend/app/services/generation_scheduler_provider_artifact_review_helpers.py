"""Pure ProviderArtifactStaging / PromotionReport contract helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def provider_artifact_promotion_allowed(promotion: dict[str, Any]) -> bool:
    """Return whether a promotion report explicitly allows promotion."""

    decision = promotion.get("decision", {})
    return isinstance(decision, dict) and decision.get("promotion_allowed") is True


def staged_artifact_ids(staging: dict[str, Any]) -> set[Any]:
    return {
        artifact.get("artifact_id")
        for artifact in staging.get("staged_artifacts", [])
        if isinstance(artifact, dict)
    }


def reviewed_staged_artifact_ids(promotion: dict[str, Any]) -> set[Any]:
    return {
        artifact.get("staged_artifact_id")
        for artifact in promotion.get("reviewed_artifacts", [])
        if isinstance(artifact, dict)
    }


def missing_reviewed_staged_artifact_ids(
    staging: dict[str, Any],
    promotion: dict[str, Any],
) -> list[str]:
    missing = reviewed_staged_artifact_ids(promotion) - staged_artifact_ids(staging)
    return sorted(str(item) for item in missing)


def validate_provider_artifact_review_contract(
    staging: dict[str, Any],
    promotion: dict[str, Any],
    *,
    staging_path: Path | None = None,
    source_staging_path: Path | None = None,
    error_cls: type[Exception] = ValueError,
) -> dict[str, Any]:
    """Validate cross-file review contract after each file passes its schema gate."""

    if (
        staging_path is not None
        and source_staging_path is not None
        and source_staging_path != staging_path
    ):
        raise error_cls("promotion_report.source_staging_ref must reference staging_path")

    if str(promotion.get("source_staging_id") or "") != str(
        staging.get("manifest_id") or ""
    ):
        raise error_cls("promotion_report.source_staging_id must match staging manifest_id")

    missing_review_refs = missing_reviewed_staged_artifact_ids(staging, promotion)
    if missing_review_refs:
        raise error_cls(
            "promotion reviewed_artifacts must reference staged_artifacts: "
            + ", ".join(missing_review_refs)
        )

    return {
        "staging_manifest_id": str(staging.get("manifest_id") or ""),
        "promotion_report_id": str(promotion.get("report_id") or ""),
        "source_staging_id": str(promotion.get("source_staging_id") or ""),
        "staged_artifact_ids": sorted(str(item) for item in staged_artifact_ids(staging)),
        "reviewed_staged_artifact_ids": sorted(
            str(item) for item in reviewed_staged_artifact_ids(promotion)
        ),
        "promotion_allowed": provider_artifact_promotion_allowed(promotion),
    }
