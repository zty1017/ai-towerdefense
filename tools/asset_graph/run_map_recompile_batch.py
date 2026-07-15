#!/usr/bin/env python3
"""Batch recompile closure for MVP map nodes.

Runs the latest map compilation closed loop across the three MVP battle nodes
(gray_lantern_station, lamp_wick_store, old_signal_tower) with safe defaults:

- Default dry/review-only: no provider calls, no player runtime mutation.
- ``--live``: calls providers for visual generation via the existing closed loop.
- ``--promote``: syncs validated outputs to canonical player runtime locations
  only when all structural/semantic/alignment/visual gates pass.

This CLI reuses the existing ``map_compilation_orchestrator`` and
``map_visual_closed_loop``. It does not introduce a parallel compiler, schema or
gate; it only batches the existing per-node compile, records a unified report,
and optionally promotes the validated artifacts into the canonical player-facing
``game_data/media/layered_maps/{node_id}/`` directory.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import map_compilation_orchestrator as orchestrator
except ModuleNotFoundError:  # pragma: no cover - package import path.
    from tools.asset_graph import map_compilation_orchestrator as orchestrator


ROOT = Path(__file__).resolve().parents[2]
LAYERED_MEDIA_ROOT = ROOT / "game_data" / "media" / "layered_maps"
CANONICAL_ROOT = LAYERED_MEDIA_ROOT
DEFAULT_OUTPUT_ROOT = LAYERED_MEDIA_ROOT / "_recompile_staging"
BATCH_INPUTS_DIRNAME = "_batch_inputs"

BATCH_REPORT_VERSION = "map_recompile_batch_report.v0.1"
COMPILATION_INPUT_VERSION = "map_compilation_input.v0.1"

# Reuse the same node -> battle/style mapping the backend services use.
NODE_INPUTS: dict[str, tuple[Path, Path]] = {
    "gray_lantern_station": (
        ROOT / "game_data/demo/first_battle_config.json",
        ROOT / "examples/map_style_packs/long_night_ruined_outpost.map_style_pack.json",
    ),
    "lamp_wick_store": (
        ROOT / "game_data/demo/wick_store_pressure_battle_config.json",
        ROOT / "examples/map_style_packs/long_night_lamp_wick_store.map_style_pack.json",
    ),
    "old_signal_tower": (
        ROOT / "game_data/demo/old_signal_tower_pressure_battle_config.json",
        ROOT / "examples/map_style_packs/long_night_old_signal_tower.map_style_pack.json",
    ),
}

DEFAULT_NODES = ["gray_lantern_station", "lamp_wick_store", "old_signal_tower"]

# Promote staging artifact directories that are scratch / per-attempt candidates
# and should not land in the canonical player-facing directory.
PROMOTE_IGNORE_DIRS = {"visual_candidates"}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _parse_nodes(raw: str) -> list[str]:
    nodes = [item.strip() for item in raw.split(",") if item.strip()]
    if not nodes:
        raise SystemExit("--nodes must contain at least one node id")
    unknown = [node for node in nodes if node not in NODE_INPUTS]
    if unknown:
        raise SystemExit(
            f"unknown node id(s): {', '.join(unknown)}; "
            f"supported: {', '.join(sorted(NODE_INPUTS))}"
        )
    return nodes


def build_compilation_input(
    node_id: str, battle_path: Path, style_path: Path
) -> dict[str, Any]:
    """Build a ``map_compilation_input.v0.1`` dict for one node.

    ``provider_handoff`` is enabled so the visual handoff pack (control sketches,
    layered request pack, prompt pack) is always produced for review.
    ``background_execution`` is disabled so the batch CLI stays the sole driver
    and no pending background job is left for the map visual worker to pick up.
    """
    return {
        "schema_version": COMPILATION_INPUT_VERSION,
        "input_id": f"map_recompile_batch_input_{node_id}_v0_1",
        "created_at": _now(),
        "battle_config_path": str(battle_path.resolve()),
        "map_style_pack_path": str(style_path.resolve()),
        "visual_generation": {
            "provider_handoff": True,
            "background_execution": False,
        },
    }


def _node_output_dir(output_root: Path, node_id: str) -> Path:
    return output_root / node_id


def _batch_inputs_dir(output_root: Path) -> Path:
    return output_root / BATCH_INPUTS_DIRNAME


def _validate_staging_root(output_root: Path) -> Path:
    resolved = output_root.resolve()
    try:
        relative = resolved.relative_to(LAYERED_MEDIA_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(
            f"output_root must stay under {LAYERED_MEDIA_ROOT.resolve()}"
        ) from exc
    if not relative.parts or not relative.parts[0].startswith("_"):
        raise ValueError(
            "output_root must use a private staging directory whose name starts with '_'"
        )
    return resolved


def check_gates(run_report: dict[str, Any], *, live: bool) -> dict[str, Any]:
    """Inspect a per-node run report and return gate statuses.

    Gates:

    - structural: orchestrator stages completed and schema validations passed.
    - semantic: ``semantic_visual_consistency_report`` status.
    - alignment: covered by the semantic consistency report's path/slot/objective
      alignment checks.
    - visual: closed-loop reviewed staging readiness (requires ``--live``).
    """
    quality = run_report.get("quality") or {}
    provider_exec = run_report.get("provider_execution") or {}
    stages = run_report.get("stages") or []
    structural_passed = (
        run_report.get("status") == "completed"
        and bool(stages)
        and all(stage.get("status") == "passed" for stage in stages)
    )
    semantic_status = str(quality.get("logic_visual_alignment") or "unknown")
    semantic_passed = semantic_status in {"passed", "passed_with_warnings"}
    alignment_status = semantic_status
    alignment_passed = semantic_passed

    if live:
        visual_status = (
            "passed"
            if provider_exec.get("automatic_reviewed_staging_ready") is True
            and provider_exec.get("candidate_generation_status")
            == "runtime_visuals_ready"
            else "failed"
        )
    else:
        visual_status = "skipped"
    visual_passed = visual_status == "passed"

    all_passed = structural_passed and semantic_passed and alignment_passed and visual_passed
    return {
        "structural": "passed" if structural_passed else "failed",
        "semantic": semantic_status,
        "alignment": alignment_status,
        "visual": visual_status,
        "all_passed": all_passed,
    }


def _staging_path_forms(staging_node_dir: Path) -> list[str]:
    """Return all path-prefix forms the orchestrator may have written."""
    forms = []
    resolved = staging_node_dir.resolve()
    forms.append(str(resolved))
    forms.append(resolved.as_posix())
    try:
        rel = resolved.relative_to(ROOT.resolve()).as_posix()
        forms.append(rel)
    except ValueError:
        pass
    # Deduplicate while preserving order.
    seen: set[str] = set()
    unique = []
    for form in forms:
        if form and form not in seen:
            seen.add(form)
            unique.append(form)
    return unique


def _rewrite_promoted_paths(
    canonical_node_dir: Path, staging_node_dir: Path, node_id: str
) -> int:
    """Fix path refs inside promoted JSON files to point at the canonical dir.

    The orchestrator writes ROOT-relative and absolute path refs that point at
    the staging directory. After copying into the canonical directory we must
    rewrite those prefixes so the player runtime resolves assets correctly.
    """
    staging_forms = _staging_path_forms(staging_node_dir)
    try:
        canonical_rel = canonical_node_dir.resolve().relative_to(
            ROOT.resolve()
        ).as_posix()
    except ValueError:
        canonical_rel = canonical_node_dir.resolve().as_posix()
    canonical_abs = canonical_node_dir.resolve().as_posix()
    staging_relative = staging_node_dir.resolve().relative_to(
        LAYERED_MEDIA_ROOT.resolve()
    ).as_posix()
    staging_url = f"/assets/layered_maps/{staging_relative}/"
    canonical_url = f"/assets/layered_maps/{node_id}/"

    rewritten = 0
    for json_path in canonical_node_dir.rglob("*.json"):
        original = json_path.read_text(encoding="utf-8")
        updated = original
        for staging_form in staging_forms:
            canonical_form = canonical_abs if staging_form == str(
                staging_node_dir.resolve()
            ) or staging_form == staging_node_dir.resolve().as_posix() else canonical_rel
            updated = updated.replace(staging_form, canonical_form)
        updated = updated.replace(staging_url, canonical_url)
        if updated != original:
            json_path.write_text(updated, encoding="utf-8")
            rewritten += 1
    return rewritten


def promote_node(
    node_id: str, staging_node_dir: Path, canonical_node_dir: Path
) -> dict[str, Any]:
    """Copy validated staging artifacts into the canonical player location.

    Uses a rename-based backup so the canonical directory is either fully
    promoted or fully restored on failure.
    """
    if staging_node_dir.resolve() == canonical_node_dir.resolve():
        return {
            "eligible": True,
            "applied": False,
            "canonical_dir": _rel(canonical_node_dir),
            "note": "staging_is_canonical_no_copy_needed",
        }

    backup_dir: Path | None = None
    if canonical_node_dir.exists():
        backup_dir = canonical_node_dir.with_name(f"{canonical_node_dir.name}.__promote_backup")
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
        canonical_node_dir.rename(backup_dir)
    try:
        canonical_node_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            staging_node_dir,
            canonical_node_dir,
            ignore=shutil.ignore_patterns(*PROMOTE_IGNORE_DIRS),
        )
        rewritten = _rewrite_promoted_paths(canonical_node_dir, staging_node_dir, node_id)
    except Exception:
        # Restore backup on any failure.
        if canonical_node_dir.exists():
            shutil.rmtree(canonical_node_dir)
        if backup_dir is not None and backup_dir.exists():
            backup_dir.rename(canonical_node_dir)
        raise
    if backup_dir is not None and backup_dir.exists():
        shutil.rmtree(backup_dir)
    return {
        "eligible": True,
        "applied": True,
        "canonical_dir": _rel(canonical_node_dir),
        "rewritten_json_files": rewritten,
        "excluded_dirs": sorted(PROMOTE_IGNORE_DIRS),
    }


def compile_node(
    node_id: str,
    *,
    output_root: Path,
    live: bool,
    dotenv_path: Path | None,
    max_attempts: int,
    max_workers: int,
) -> dict[str, Any]:
    """Run the orchestrator for a single node and return a per-node result."""
    battle_path, style_path = NODE_INPUTS[node_id]
    inputs_dir = _batch_inputs_dir(output_root)
    input_path = inputs_dir / f"{node_id}.map_compilation_input.json"
    input_value = build_compilation_input(node_id, battle_path, style_path)
    _write_json(input_path, input_value)
    output_dir = _node_output_dir(output_root, node_id)
    started = time.monotonic()
    try:
        run_report = orchestrator.compile_map(
            input_path,
            output_dir,
            force=True,
            live_visuals=live,
            dotenv_path=dotenv_path,
            visual_max_attempts=max_attempts,
            visual_max_workers=max_workers,
        )
    except Exception as exc:
        return {
            "node_id": node_id,
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
            "traceback_tail": traceback.format_exc().splitlines()[-1],
            "input_path": _rel(input_path),
            "output_dir": _rel(output_dir),
            "run_report_path": None,
            "gates": None,
            "promotion": {
                "eligible": False,
                "applied": False,
                "blocked_reasons": ["compile_failed"],
            },
            "provider_calls": 0,
            "vision_review_calls": 0,
            "duration_ms": int((time.monotonic() - started) * 1000),
        }
    run_report_path = output_dir / "map_compilation_run_report.v0.1.json"
    gates = check_gates(run_report, live=live)
    provider_exec = run_report.get("provider_execution") or {}
    return {
        "node_id": node_id,
        "status": "completed",
        "error": None,
        "input_path": _rel(input_path),
        "output_dir": _rel(output_dir),
        "run_report_path": _rel(run_report_path) if run_report_path.exists() else None,
        "gates": gates,
        "promotion": {
            "eligible": gates["all_passed"],
            "applied": False,
            "blocked_reasons": []
            if gates["all_passed"]
            else _blocked_reasons(gates, live),
        },
        "provider_calls": int(provider_exec.get("call_count") or 0),
        "vision_review_calls": int(provider_exec.get("vision_review_call_count") or 0),
        "duration_ms": int((time.monotonic() - started) * 1000),
    }


def _blocked_reasons(gates: dict[str, Any], live: bool) -> list[str]:
    reasons: list[str] = []
    if gates["structural"] != "passed":
        reasons.append("structural_gate_failed")
    if gates["semantic"] not in {"passed", "passed_with_warnings"}:
        reasons.append("semantic_gate_failed")
    if gates["alignment"] not in {"passed", "passed_with_warnings"}:
        reasons.append("alignment_gate_failed")
    if gates["visual"] != "passed":
        if live:
            reasons.append("visual_gate_failed")
        else:
            reasons.append("visual_gate_skipped_requires_live")
    return reasons


def run_batch(
    nodes: list[str],
    output_root: Path,
    *,
    dotenv_path: Path | None,
    live: bool,
    promote: bool,
    max_attempts: int,
    max_workers: int,
) -> dict[str, Any]:
    """Compile every node, optionally promote, and return a summary report."""
    output_root = _validate_staging_root(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    node_results: list[dict[str, Any]] = []
    for node_id in nodes:
        result = compile_node(
            node_id,
            output_root=output_root,
            live=live,
            dotenv_path=dotenv_path,
            max_attempts=max_attempts,
            max_workers=max_workers,
        )
        if promote and result["status"] == "completed" and result["gates"]["all_passed"]:
            staging_node_dir = _node_output_dir(output_root, node_id)
            canonical_node_dir = CANONICAL_ROOT / node_id
            try:
                promotion = promote_node(node_id, staging_node_dir, canonical_node_dir)
                promotion["blocked_reasons"] = []
            except Exception as exc:
                promotion = {
                    "eligible": True,
                    "applied": False,
                    "canonical_dir": _rel(CANONICAL_ROOT / node_id),
                    "blocked_reasons": [f"promotion_error:{type(exc).__name__}"],
                    "error": f"{type(exc).__name__}: {exc}",
                }
            result["promotion"] = promotion
        elif promote and result["status"] == "completed" and not result["gates"]["all_passed"]:
            existing = result["promotion"]
            existing["canonical_dir"] = _rel(CANONICAL_ROOT / node_id)
            existing.setdefault("blocked_reasons", _blocked_reasons(result["gates"], live))
        elif promote and result["status"] != "completed":
            existing = result["promotion"]
            existing["canonical_dir"] = _rel(CANONICAL_ROOT / node_id)
        node_results.append(result)

    summary = {
        "node_count": len(nodes),
        "completed_count": sum(1 for r in node_results if r["status"] == "completed"),
        "failed_count": sum(1 for r in node_results if r["status"] == "failed"),
        "promoted_count": sum(
            1 for r in node_results if r.get("promotion", {}).get("applied")
        ),
        "blocked_count": sum(
            1
            for r in node_results
            if r["status"] == "completed"
            and not r.get("promotion", {}).get("applied")
            and r.get("promotion", {}).get("blocked_reasons")
        ),
        "provider_call_count": sum(int(r.get("provider_calls") or 0) for r in node_results),
        "vision_review_call_count": sum(
            int(r.get("vision_review_calls") or 0) for r in node_results
        ),
    }
    if promote:
        summary["promotion_requested"] = True
    summary["overall_status"] = (
        "all_completed"
        if summary["completed_count"] == summary["node_count"]
        and summary["promoted_count"] == summary["node_count"]
        and promote
        else (
            "completed_with_blocked_promotions"
            if promote and summary["blocked_count"] > 0
            else (
                "all_completed_review_only"
                if summary["completed_count"] == summary["node_count"]
                else "partial_failure"
            )
        )
    )
    report = {
        "schema_version": BATCH_REPORT_VERSION,
        "run_id": f"mapbatch_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "created_at": _now(),
        "options": {
            "nodes": nodes,
            "output_root": _rel(output_root),
            "dotenv_provided": dotenv_path is not None,
            "live": live,
            "promote": promote,
            "max_attempts": max_attempts,
            "max_workers": max_workers,
        },
        "safety": {
            "default_dry_review_only": not live,
            "provider_called": live,
            "player_runtime_mutated": promote
            and summary["promoted_count"] > 0,
            "secrets_read_or_printed": False,
            "world_state_mutation": False,
        },
        "summary": summary,
        "nodes": node_results,
    }
    report_path = output_root / "map_recompile_batch_report.v0.1.json"
    _write_json(report_path, report)
    report["report_path"] = _rel(report_path)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batch recompile the MVP map nodes through the latest closed loop.",
    )
    parser.add_argument(
        "--nodes",
        default=",".join(DEFAULT_NODES),
        help="comma-separated node ids (default: all three MVP nodes)",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="staging root for per-node compile outputs (default: "
        "game_data/media/layered_maps/_recompile_staging)",
    )
    parser.add_argument(
        "--dotenv",
        type=Path,
        default=None,
        help="path to .env for provider credentials; required for --live",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="call providers for visual generation (default: dry/review-only)",
    )
    parser.add_argument(
        "--promote",
        action="store_true",
        help="sync validated outputs to canonical player runtime locations "
        "only when all gates pass",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=2,
        help="max visual generation attempts per role (default: 2)",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=3,
        help="max parallel workers per node visual closed loop (default: 3)",
    )
    args = parser.parse_args()

    nodes = _parse_nodes(args.nodes)
    if args.live and args.dotenv is None:
        raise SystemExit("--live requires --dotenv so the existing adapter can load credentials")
    if args.dotenv is not None and not args.dotenv.exists():
        raise SystemExit(f"--dotenv path does not exist: {args.dotenv}")
    if args.promote and not args.live:
        print(
            "warning: --promote without --live will be blocked because the visual gate "
            "cannot pass without provider output; use --live --promote together.",
            file=sys.stderr,
        )

    report = run_batch(
        nodes,
        args.output_root,
        dotenv_path=args.dotenv,
        live=args.live,
        promote=args.promote,
        max_attempts=args.max_attempts,
        max_workers=args.max_workers,
    )
    print(
        json.dumps(
            {
                "schema_version": report["schema_version"],
                "overall_status": report["summary"]["overall_status"],
                "summary": report["summary"],
                "report_path": report["report_path"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if report["summary"]["failed_count"] > 0:
        return 2
    if args.promote and report["summary"]["promoted_count"] != len(nodes):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
