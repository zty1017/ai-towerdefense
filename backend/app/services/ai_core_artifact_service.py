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


def _core_artifact_refs_with_world_delta(
    world_delta_ref: str, transaction_ref: str | None = None
) -> dict[str, str]:
    return {
        **core_artifact_refs(),
        **({"world_delta_transaction": transaction_ref} if transaction_ref else {}),
        "world_delta": world_delta_ref,
    }


def battle_settlement_core_artifacts(
    *,
    node_id: str,
    world_delta_ref: str,
    world_delta: dict[str, Any],
    transaction: dict[str, Any],
    created_at: str,
    transaction_ref: str | None = None,
) -> dict[str, Any]:
    """Build native core artifact snapshots for battle settlement evidence."""

    transaction_id = str(transaction.get("transaction_id") or "battle_settlement")
    delta_id = str(world_delta.get("delta_id") or "world_delta")
    context_package_id = f"ctx_settlement_{transaction_id}"
    fact_id = f"fact_settlement_{delta_id}"
    node_scope = f"node.{node_id}"

    context = _clone_context_package()
    context.update(
        {
            "context_package_id": context_package_id,
            "purpose": "world_delta",
            "scope": node_scope,
            "run_id": str(transaction.get("run_id") or context.get("run_id")),
            "run_world_version": str(
                transaction.get("base_world_version")
                or context.get("run_world_version")
            ),
            "created_at": created_at,
        }
    )
    for block in context.get("blocks", []):
        if not isinstance(block, dict):
            continue
        if block.get("block_id") == "current_battle_node":
            block["source_ref"] = world_delta_ref
            block["summary"] = (
                f"{node_id} 的战斗结果已被整理为受控 WorldStateDelta，"
                "等待事务语义提交。"
            )
        if block.get("block_id") == "player_workshop_intent":
            block["source_ref"] = world_delta_ref
            block["summary"] = "战后结算只消费已验证的世界状态变化，不读取原始运行日志。"
    context["source_refs"] = [
        _artifact_ref("world_delta", "fixture", world_delta_ref),
        _artifact_ref(
            "world_delta_transaction",
            "fixture",
            transaction_ref or core_artifact_refs()["world_delta_transaction"],
        ),
    ]

    fact = _clone_fact_entry()
    fact.update(
        {
            "fact_id": fact_id,
            "subject": node_id,
            "predicate": "battle_result_committed",
            "content": (
                f"{node_id} 的战斗结果已通过 WorldStateDeltaTransaction "
                f"{transaction_id} 提交，后续剧情和研发应以提交后的世界状态为准。"
            ),
            "source": "world_state_delta",
            "confidence": "observed",
            "commit_state": "committed",
            "created_at": created_at,
            "source_tx_id": transaction_id,
        }
    )
    fact["submission_policy"] = {
        "can_mutate_run_world_state": False,
        "commit_requires_world_state_delta": True,
        "allowed_context_use": "committed_world_fact",
    }
    fact["activation_rules"] = {
        "active_when": [f"world_delta:{delta_id}:committed"],
        "deactivate_when": [],
    }

    cgop = _clone_cgop()
    cgop.update(
        {
            "package_id": f"cgop_settlement_{delta_id}",
            "content_version": "battle-settlement.0.1",
            "lifecycle_state": "reviewed",
            "source_intent": {
                "intent_ref": f"world_delta:{delta_id}",
                "summary": "战后结算把样品表现和节点变化封装为可审查世界状态提交证据。",
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
            "unmapped_effects",
            "raw_patch_apply",
        ],
    }
    cgop["runtime_contract"] = {
        "runtime_loadable": False,
        "load_surface": "review_only",
        "manifest_refs": [],
        "world_delta_refs": [
            _artifact_ref("world_delta", "world_delta", world_delta_ref),
        ],
        "state_instance_policy": "review_only",
    }
    cgop["validation_report"] = {
        "gate_status": "passed",
        "runtime_loadable": False,
        "gates": [
            {
                "gate_id": "world_delta_transaction",
                "status": "passed",
                "summary": "Settlement references a validated WorldStateDeltaTransaction wrapper.",
            },
            {
                "gate_id": "operations_whitelist",
                "status": "passed",
                "summary": "World changes remain in WorldStateDelta.operations[].",
            },
        ],
        "approved_scopes": ["battle_settlement_evidence"],
        "failed_rules": [],
        "warnings": [],
    }
    cgop["lineage"] = {
        "compiled_at": created_at,
        "compiler_version": "ai_compile_core.v0.1",
        "parent_package_ids": ["cgop_mvp_light_snare_sample"],
    }

    return {
        "status": "native_settlement_committed",
        "refs": _core_artifact_refs_with_world_delta(world_delta_ref, transaction_ref),
        "context_package": context,
        "fact_entry": fact,
        "compiled_game_object_package": cgop,
        "world_delta": copy.deepcopy(world_delta),
        "world_delta_transaction": copy.deepcopy(transaction),
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
