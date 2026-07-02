"""Fixture-backed AI compilation core artifact service.

This service owns the MVP references for ContextPackage, FactEntry, CGOP, and
WorldStateDeltaTransaction examples. These artifacts are evidence and schema
boundary fixtures, not player-facing text.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[3]

_CONTEXT_PACKAGE_EXAMPLE = (
    _REPO_ROOT / "examples/review_packs/mvp_first_battle.context_package.json"
)
_FACT_ENTRY_EXAMPLE = (
    _REPO_ROOT / "examples/review_packs/mvp_gray_lantern.fact_entry.json"
)
_CGOP_EXAMPLE = (
    _REPO_ROOT / "examples/review_packs/mvp_light_snare.compiled_game_object_package.json"
)
_WORLD_DELTA_TRANSACTION_EXAMPLE = (
    _REPO_ROOT
    / "examples/world_delta_transactions/first_battle_result.world_delta_transaction.json"
)


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _rel(path: Path) -> str:
    return path.relative_to(_REPO_ROOT).as_posix()


def _artifact_ref(ref_id: str, ref_kind: str, path: str) -> dict[str, str]:
    return {
        "ref_id": ref_id,
        "ref_kind": ref_kind,
        "path": path,
    }


def _object_type_for_candidate(candidate_kind: str) -> str:
    if candidate_kind == "tower_blueprint":
        return "tower"
    if candidate_kind == "support_item":
        return "item"
    return "trap"


def _clone_context_package() -> dict[str, Any]:
    return copy.deepcopy(_load_json(_CONTEXT_PACKAGE_EXAMPLE))


def _clone_fact_entry() -> dict[str, Any]:
    return copy.deepcopy(_load_json(_FACT_ENTRY_EXAMPLE))


def _clone_cgop() -> dict[str, Any]:
    return copy.deepcopy(_load_json(_CGOP_EXAMPLE))


def core_artifact_refs() -> dict[str, str]:
    return {
        "context_package": _rel(_CONTEXT_PACKAGE_EXAMPLE),
        "fact_entry": _rel(_FACT_ENTRY_EXAMPLE),
        "compiled_game_object_package": _rel(_CGOP_EXAMPLE),
        "world_delta_transaction": _rel(_WORLD_DELTA_TRANSACTION_EXAMPLE),
    }


def load_world_delta_transaction() -> dict[str, Any]:
    return _load_json(_WORLD_DELTA_TRANSACTION_EXAMPLE)


def core_artifact_payload() -> dict[str, Any]:
    return {
        "status": "field_boundary_examples_ready",
        "refs": core_artifact_refs(),
        "context_package": _load_json(_CONTEXT_PACKAGE_EXAMPLE),
        "fact_entry": _load_json(_FACT_ENTRY_EXAMPLE),
        "compiled_game_object_package": _load_json(_CGOP_EXAMPLE),
        "world_delta_transaction": load_world_delta_transaction(),
    }


def research_proposal_core_artifacts(
    *,
    session_id: str,
    proposal_id: str,
    node_id: str,
    intent_summary: str,
    candidate_kind: str,
    display_name: str,
    proposal_summary: str,
    battle_config_ref: str | None,
    map_runtime_package_ref: str | None,
    created_at: str,
) -> dict[str, Any]:
    """Build native core artifact snapshots for a research proposal.

    These snapshots are stored inside internal compiler metadata so workers can
    consume the v0.1 object model directly. They remain advisory / review-only:
    no object here mutates RunWorldState or becomes runtime-loadable by itself.
    """

    context_package_id = f"ctx_research_{proposal_id}"
    fact_id = f"fact_research_{proposal_id}_node_pressure"
    package_id = f"cgop_research_{proposal_id}_candidate"
    node_scope = f"node.{node_id}"

    context = _clone_context_package()
    context.update(
        {
            "context_package_id": context_package_id,
            "run_id": f"session_{session_id}",
            "scope": node_scope,
            "created_at": created_at,
        }
    )
    for block in context.get("blocks", []):
        if not isinstance(block, dict):
            continue
        if block.get("block_id") == "current_battle_node" and map_runtime_package_ref:
            block["source_ref"] = map_runtime_package_ref
            block["summary"] = (
                f"{node_id} 的路径、塔位、保护目标与出生点来自当前 "
                "MapRuntimePackage。"
            )
        if block.get("block_id") == "player_workshop_intent":
            block["source_ref"] = f"research_proposal:{proposal_id}"
            block["summary"] = intent_summary or "玩家提出了一个现场试作构想。"
    source_refs = [
        _artifact_ref(
            "map_runtime_package",
            "map_package",
            map_runtime_package_ref
            or "examples/map_runtime_packages/mvp_first_battle.map_runtime_package.json",
        ),
        _artifact_ref(
            "battle_config",
            "fixture",
            battle_config_ref or "game_data/demo/first_battle_config.json",
        ),
    ]
    context["source_refs"] = source_refs

    fact = _clone_fact_entry()
    fact.update(
        {
            "fact_id": fact_id,
            "subject": node_id,
            "predicate": "has_research_proposal_candidate",
            "content": (
                f"{node_id} 收到一个现场试作构想：{proposal_summary} "
                "该事实仍是候选，只能作为后续编译上下文。"
            ),
            "source": "player_claim",
            "confidence": "player_claim",
            "created_at": created_at,
            "source_tx_id": None,
        }
    )
    fact["activation_rules"] = {
        "active_when": [f"research_proposal:{proposal_id}:created"],
        "deactivate_when": [f"research_proposal:{proposal_id}:discarded"],
    }

    cgop = _clone_cgop()
    cgop.update(
        {
            "package_id": package_id,
            "object_type": _object_type_for_candidate(candidate_kind),
            "content_version": "research-proposal.0.1",
            "lifecycle_state": "compiled",
            "source_intent": {
                "intent_ref": f"research_proposal:{proposal_id}",
                "summary": intent_summary or proposal_summary,
            },
            "context_package_id": context_package_id,
            "execution_trace_ref": None,
        }
    )
    cgop["world_context"] = {
        "scope": node_scope,
        "required_fact_ids": [fact_id],
        "forbidden_world_mutations": [
            "base_worldbook_rewrite",
            "direct_resource_change",
            "unreviewed_npc_creation",
        ],
    }
    cgop["semantic_spec"] = {
        "player_visible_name_hint": display_name,
        "world_fit": proposal_summary,
    }
    cgop["gameplay_spec"] = {
        "role": candidate_kind,
        "allowed_effects": ["slow", "short_stun"]
        if candidate_kind == "temporary_trap_sample"
        else [],
        "deployment_limit": 2 if candidate_kind == "temporary_trap_sample" else 1,
    }
    cgop["runtime_contract"] = {
        "runtime_loadable": False,
        "load_surface": "review_only",
        "manifest_refs": [],
        "world_delta_refs": [],
        "state_instance_policy": "blueprint_only",
    }
    cgop["dependencies"] = [f"map_runtime_package:{node_id}"]
    cgop["validation_report"] = {
        "gate_status": "warning",
        "runtime_loadable": False,
        "gates": [
            {
                "gate_id": "proposal_native_snapshot",
                "status": "passed",
                "summary": "Research proposal metadata now carries native core artifact snapshots.",
            },
            {
                "gate_id": "runtime_activation",
                "status": "warning",
                "summary": "The proposal is not runtime-loadable until downstream workflow output is reviewed.",
            },
        ],
        "approved_scopes": ["research_job_metadata"],
        "failed_rules": [],
        "warnings": ["proposal_not_locked"],
    }
    cgop["lineage"] = {
        "compiled_at": created_at,
        "compiler_version": "ai_compile_core.v0.1",
        "parent_package_ids": [],
    }

    return {
        "status": "native_snapshots_ready",
        "refs": core_artifact_refs(),
        "context_package": context,
        "fact_entry": fact,
        "compiled_game_object_package": cgop,
    }


def research_job_core_artifacts(
    *,
    proposal_core_artifacts: dict[str, Any],
    status: str,
    runtime_package_path: str | None,
    delivery_payload_path: str | None,
    trace_paths: list[str],
    completed_at: str,
) -> dict[str, Any]:
    """Return a job-stage copy of proposal core artifacts."""

    artifacts = copy.deepcopy(proposal_core_artifacts)
    artifacts["status"] = (
        "native_snapshots_compiled" if status == "completed" else "native_snapshots_failed"
    )
    cgop = artifacts.get("compiled_game_object_package")
    if isinstance(cgop, dict):
        cgop["lifecycle_state"] = "reviewed" if status == "completed" else "quarantined"
        cgop["execution_trace_ref"] = trace_paths[0] if trace_paths else None
        cgop["runtime_contract"] = {
            "runtime_loadable": False,
            "load_surface": "review_only",
            "manifest_refs": [
                _artifact_ref("runtime_package", "runtime_package", runtime_package_path)
            ]
            if runtime_package_path
            else [],
            "world_delta_refs": [],
            "state_instance_policy": "blueprint_only",
        }
        cgop["validation_report"] = {
            "gate_status": "passed" if status == "completed" else "failed",
            "runtime_loadable": False,
            "gates": [
                {
                    "gate_id": "assetgraph_workflow",
                    "status": "passed" if status == "completed" else "failed",
                    "summary": (
                        "AssetGraph workflows produced runtime and delivery artifacts."
                        if status == "completed"
                        else "AssetGraph workflows did not produce all required artifacts."
                    ),
                },
                {
                    "gate_id": "runtime_activation",
                    "status": "warning",
                    "summary": "Job output remains review-only until explicitly activated.",
                },
            ],
            "approved_scopes": ["research_job_metadata", "review_evidence"],
            "failed_rules": [] if status == "completed" else ["workflow_output_missing"],
            "warnings": ["runtime_activation_requires_review"],
        }
        cgop["lineage"] = {
            **(cgop.get("lineage") if isinstance(cgop.get("lineage"), dict) else {}),
            "compiled_at": completed_at,
        }
    if delivery_payload_path:
        artifacts["delivery_payload_ref"] = delivery_payload_path
    return artifacts
