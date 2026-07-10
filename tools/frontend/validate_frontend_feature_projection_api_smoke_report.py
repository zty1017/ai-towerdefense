#!/usr/bin/env python3
"""Validate FrontendFeatureProjectionApiSmokeReport v0.1."""

from __future__ import annotations

import argparse
from pathlib import Path

from report_io import load_json_object


SCHEMA_VERSION = "frontend_feature_projection_api_smoke_report.v0.1"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate(report: dict) -> None:
    require(report.get("schema_version") == SCHEMA_VERSION, "schema_version mismatch")
    require(report.get("status") == "passed", "smoke status must be passed")
    require(report.get("browser_available") is True, "browser must be available")
    safety = report.get("safety_summary") or {}
    require(safety.get("reads_env_file") is False, "smoke must not read .env")
    require(int(safety.get("provider_call_count") or 0) == 0, "smoke must not call providers")
    require(safety.get("runtime_activation_allowed") is True, "smoke must exercise runtime activation")
    require(int(safety.get("runtime_activation_count") or 0) == 1, "unexpected runtime activation count")
    require(int(safety.get("world_mutation_count") or 0) == 3, "unexpected world mutation count")
    checks = report.get("checks") or {}
    require(
        checks.get("workshop_participant_projection_visible") is True,
        "workshop participant projection was not visible",
    )
    proposal = checks.get("workshop_proposal_projection") or {}
    require(bool(proposal.get("proposalId")), "workshop proposal contribution missing")
    require(bool(proposal.get("title")), "workshop proposal title missing")
    activation = checks.get("runtime_activation_projection") or {}
    require(bool(activation.get("activationId")), "runtime activation receipt missing")
    require(bool(activation.get("objectId")), "activated battle object missing")
    require(bool(activation.get("displayName")), "activated battle object name missing")
    require(
        activation.get("behaviorGate") in {"passed", "degraded"},
        "behavior ABI gate did not pass",
    )
    require(
        activation.get("mediaGate") in {"passed", "degraded"},
        "media gate did not pass",
    )
    settlement = checks.get("settlement_projection") or {}
    require(
        set(settlement.get("slots") or []) >= {"result_summary", "world_delta"},
        "settlement projection slots missing",
    )
    screenshots = report.get("screenshots") or []
    require(len(screenshots) == 3, "expected three screenshots")
    for item in screenshots:
        path = Path(str(item.get("path") or ""))
        require(path.exists(), f"screenshot missing: {path}")
        require(path.suffix.lower() == ".png", f"screenshot must be PNG: {path}")
        require(int(item.get("file_size_bytes") or 0) > 5000, f"screenshot too small: {path}")
        require(bool(item.get("sha256")), f"screenshot hash missing: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        validate(load_json_object(args.report, label="report root"))
    except Exception as exc:  # noqa: BLE001 - concise CLI failure.
        print(f"feature projection API smoke validation failed: {exc}")
        return 1
    print(f"feature projection API smoke validation passed: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
