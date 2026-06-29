#!/usr/bin/env python3
"""Run the local v0.1 mock compiler pipeline for one Proposal."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import mock_compile_proposal  # noqa: E402
import simulate_asset_candidate  # noqa: E402
import validate_asset_candidate  # noqa: E402
import validate_proposal  # noqa: E402


DEFAULT_REGISTRY = ROOT / "shared/module_registry/effect_blocks.v0.1.json"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value).strip("_") or "proposal"


def run_pipeline(proposal_path: Path, output_dir: Path, registry_path: Path) -> int:
    proposal = load_json(proposal_path)
    if not isinstance(proposal, dict):
        print("INVALID Proposal")
        print("- proposal root must be an object")
        return 1

    proposal_errors = validate_proposal.validate(proposal)
    if proposal_errors:
        print("INVALID Proposal")
        for error in proposal_errors:
            print(f"- {error}")
        return 1

    proposal_id = str(proposal.get("id", "proposal"))
    run_dir = output_dir / safe_id(proposal_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    candidate = mock_compile_proposal.compile_candidate(
        proposal,
        provider="mock",
        model="mock_compiler_v0.1",
    )
    candidate_path = run_dir / "compiled_asset.json"
    write_json(candidate_path, candidate)

    registry = load_json(registry_path)
    if not isinstance(registry, dict):
        print("INVALID registry")
        print("- registry root must be an object")
        return 1

    candidate_errors = validate_asset_candidate.validate(candidate, registry)
    if candidate_errors:
        report = {
            "status": "failed",
            "stage": "asset_validation",
            "proposal_path": str(proposal_path),
            "candidate_path": str(candidate_path),
            "errors": candidate_errors,
        }
        write_json(run_dir / "pipeline_report.json", report)
        print("INVALID CompiledAssetCandidate")
        for error in candidate_errors:
            print(f"- {error}")
        return 1

    simulation_report = simulate_asset_candidate.simulate(
        candidate,
        simulate_asset_candidate.DEFAULT_DURATION_SECONDS,
    )
    simulation_path = run_dir / "simulation_report.json"
    write_json(simulation_path, simulation_report)

    pipeline_report = {
        "status": "passed",
        "proposal_path": str(proposal_path),
        "candidate_path": str(candidate_path),
        "simulation_report_path": str(simulation_path),
        "candidate_id": candidate.get("id"),
        "balance_flags": simulation_report.get("balance_flags", []),
    }
    write_json(run_dir / "pipeline_report.json", pipeline_report)

    print("OK mock compiler pipeline")
    print(f"- proposal: {proposal_path}")
    print(f"- run_dir: {run_dir}")
    print(f"- candidate: {candidate_path}")
    print(f"- simulation_report: {simulation_path}")
    if simulation_report.get("balance_flags"):
        print(f"- balance_flags: {', '.join(simulation_report['balance_flags'])}")
    else:
        print("- balance_flags: none")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("proposal", help="Path to a Proposal JSON file.")
    parser.add_argument("--output-dir", default="/tmp/ai_compiled_td_mock_runs")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    args = parser.parse_args()

    return run_pipeline(
        proposal_path=Path(args.proposal),
        output_dir=Path(args.output_dir),
        registry_path=Path(args.registry),
    )


if __name__ == "__main__":
    raise SystemExit(main())

