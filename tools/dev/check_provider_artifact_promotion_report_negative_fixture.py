#!/usr/bin/env python3
"""Check that an invalid ProviderArtifactPromotionReport fixture is rejected."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ASSET_GRAPH_DIR = ROOT / "tools" / "asset_graph"
DEV_DIR = ROOT / "tools" / "dev"
for path in (ASSET_GRAPH_DIR, DEV_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from validation_common import load_json  # noqa: E402
from validate_provider_artifact_promotion_report import (  # noqa: E402
    validate_provider_artifact_promotion_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--expected-error", required=True)
    args = parser.parse_args()

    report = load_json(args.fixture)
    if not isinstance(report, dict):
        print("ProviderArtifactPromotionReport fixture root must be an object", file=sys.stderr)
        return 1

    errors = validate_provider_artifact_promotion_report(report)
    if args.expected_error not in errors:
        print("expected validation error was not found", file=sys.stderr)
        print(f"expected: {args.expected_error}", file=sys.stderr)
        print("actual errors:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"negative fixture rejected as expected: {args.fixture}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
