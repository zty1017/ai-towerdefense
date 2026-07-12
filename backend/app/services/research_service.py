"""Research job service: bridges the player-facing research API and the
AssetGraph Kernel v0.1 deterministic workflow runner.

This module is intentionally MVP-shaped:
- ``create_proposal`` synthesizes a world-in-language proposal deterministically
  from the player's ``intent_text`` and ``node_id``. No real LLM is called.
- ``confirm_proposal`` idempotently enqueues one durable job per proposal.
- the research worker atomically claims queued jobs, runs the two AssetGraph
  workflows, and stores the resulting artifact paths.
- ``get_job`` reads the row back.

All workflow output is written under ``/tmp/ai_compiled_td_backend_runs`` so
nothing leaks into the repo. Player-facing strings avoid the forbidden
technical vocabulary listed in the worldbook and the task spec.
"""
from __future__ import annotations

import json
import hashlib
import os
import secrets
import sys
from pathlib import Path
from typing import Any

from ..db import db_cursor, now_iso
from . import (
    ai_core_artifact_service,
    battle_content_service,
    live_asset_compile_service,
    map_runtime_service,
    research_runtime_media_service,
    world_catalog_service,
)

# Repo root (backend/app/services -> backend/app -> backend -> repo root).
_REPO_ROOT = Path(__file__).resolve().parents[3]
_ASSET_GRAPH_DIR = _REPO_ROOT / "tools" / "asset_graph"
_CONTENT_PIPELINE_DIR = _REPO_ROOT / "tools" / "content_pipeline"
_REGISTRY_PATH = _REPO_ROOT / "shared" / "asset_graph" / "node_registry.v0.1.json"
_WORKFLOW_DIR = _REPO_ROOT / "examples" / "workflows"

_MOCK_COMPILE_WORKFLOW = _WORKFLOW_DIR / "mvp_mock_asset_compile.workflow.json"
_TRAP_DELIVERY_WORKFLOW = _WORKFLOW_DIR / "mvp_temporary_trap_delivery.workflow.json"

# Filename for the deterministic simulation report of the real provider-backed
# live candidate. Distinct from any mock workflow simulation trace so the
# promotion gate cannot mistake fixture evidence for live-candidate evidence.
_LIVE_CANDIDATE_SIMULATION_REPORT_NAME = "live_candidate_simulation_report.v0.1.json"

# All run artifacts land here, never inside the repo.
_RUNS_ROOT = Path("/tmp/ai_compiled_td_backend_runs")

# World-in-language node display names (subset of worldbook node_mapping).
_NODE_DISPLAY = {
    "gray_lantern_station": "灰灯驿站",
    "residual_lantern_hub": "余灯中枢",
    "temporary_workshop": "临时工坊",
    "lamp_wick_store": "灯芯仓",
}

# Terms that must never appear in player-facing text. Union of the task spec
# forbidden list and the worldbook forbidden_terms_in_player_text.
_FORBIDDEN_PLAYER_TERMS = (
    "provider",
    "raw_prompt",
    "full_trace",
    "raw_json",
    "api_key",
    "secret",
    "schema",
    "traceback",
    "AI",
    "prompt",
    "compiler",
    "token",
    "trace",
    "mock",
    "simulation",
)


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_registry() -> dict[str, Any]:
    return _load_json(_REGISTRY_PATH)


def _load_workflow(path: Path) -> dict[str, Any]:
    return _load_json(path)


def _import_run_workflow():
    """Import the AssetGraph run_workflow entrypoint on demand.

    Adding tools/asset_graph to sys.path lets us call run_workflow directly
    rather than shelling out, so we get the trace dict in-process.
    """
    asset_graph_str = str(_ASSET_GRAPH_DIR)
    if asset_graph_str not in sys.path:
        sys.path.insert(0, asset_graph_str)
    import run_workflow as rw  # noqa: WPS433 (deliberate lazy import)

    return rw


def _import_simulate_asset_candidate():
    """Import tools/content_pipeline/simulate_asset_candidate.py on demand.

    Used to run the deterministic headless simulation against the real
    provider-backed live candidate before the promotion report is written.
    """
    content_pipeline_str = str(_CONTENT_PIPELINE_DIR)
    if content_pipeline_str not in sys.path:
        sys.path.insert(0, content_pipeline_str)
    import simulate_asset_candidate  # noqa: WPS433 (deliberate lazy import)

    return simulate_asset_candidate


def _sanitize_player_text(text: str) -> str:
    """Defensive scrub: strip any forbidden technical term from player text.

    The deterministic proposal strings below never contain these terms, but we
    keep this guard so a future content source cannot leak them.
    """
    cleaned = text
    for term in _FORBIDDEN_PLAYER_TERMS:
        cleaned = cleaned.replace(term, "")
    return cleaned


def _node_display(node_id: str) -> str:
    return _NODE_DISPLAY.get(node_id, node_id)


def _synthesize_proposal_fields(intent_text: str, node_id: str) -> dict[str, str]:
    """Produce world-in-language display_name/summary/risk_note from intent.

    The mapping is keyword-based and deterministic; it gives the player a
    flavorful description without calling any external service.
    """
    intent = intent_text or ""
    if any(kw in intent for kw in ("拖慢", "减速", "迟滞", "slow", "迟")):
        display_name = "折光迟滞方案"
        summary = "用灯光编织的临时减速场，可让经过的影潮短暂迟滞。"
        risk_note = "持续消耗电力，对高速影潮收益更明显。"
    elif any(kw in intent for kw in ("陷阱", "绊", "trap", "索")):
        display_name = "折光绊索方案"
        summary = "灯光编织的临时绊线，能让经过的影潮短暂迟滞。"
        risk_note = "一次性试作品，使用后需重新布置。"
    elif any(kw in intent for kw in ("伤害", "攻击", "打击", "damage", "攻")):
        display_name = "聚光刺击方案"
        summary = "聚焦灯光形成瞬时刺击，对单体影潮造成伤害。"
        risk_note = "射程有限，对密集影潮收益较低。"
    elif any(kw in intent for kw in ("支援", "技能", "脉冲", "support")):
        display_name = "守灯支援方案"
        summary = "引燃储备灯芯形成短时脉冲，为一片战场提供应急支援。"
        risk_note = "储备只能支撑一次释放，需要把握时机。"
    else:
        display_name = "临时光幕方案"
        summary = "以灯光构筑的临时防线，为节点争取喘息。"
        risk_note = "试作品稳定性有限，需现场确认。"

    return {
        "display_name": _sanitize_player_text(display_name),
        "summary": _sanitize_player_text(summary),
        "risk_note": _sanitize_player_text(risk_note),
        "player_state_message": _sanitize_player_text(
            "现场试作方案已就绪，等待确认。"
        ),
    }


def _candidate_kind_from_intent(intent_text: str) -> str:
    intent = intent_text or ""
    if any(kw in intent for kw in ("陷阱", "绊", "trap", "索")):
        return "temporary_trap_sample"
    if any(kw in intent for kw in ("塔", "炮", "攻击", "伤害", "damage", "攻")):
        return "tower_blueprint"
    if any(kw in intent for kw in ("支援", "技能", "脉冲", "support")):
        return "support_item"
    return "temporary_trap_sample"


def _compiler_metadata_for_proposal(
    *,
    session_id: str,
    proposal_id: str,
    node_id: str,
    intent_text: str,
    display_name: str,
    proposal_summary: str,
    worldbook_id: str,
) -> dict[str, Any]:
    candidate_kind = _candidate_kind_from_intent(intent_text)
    battle_config_ref = battle_content_service.battle_config_ref(node_id)
    map_runtime_package_ref = map_runtime_service.map_runtime_package_ref(node_id)
    core_artifacts = ai_core_artifact_service.research_proposal_core_artifacts(
        session_id=session_id,
        proposal_id=proposal_id,
        node_id=node_id,
        intent_summary="玩家提出了一个现场试作构想。",
        candidate_kind=candidate_kind,
        display_name=display_name,
        proposal_summary=proposal_summary,
        battle_config_ref=battle_config_ref,
        map_runtime_package_ref=map_runtime_package_ref,
        created_at=now_iso(),
    )
    return {
        "schema_version": "compiler_metadata.v0.1",
        "visibility": "internal_evidence",
        "stage": "proposal",
        "compiled_object": {
            "object_model": "CGOP",
            "candidate_kind": candidate_kind,
            "lifecycle_hint": "ephemeral_sample"
            if candidate_kind == "temporary_trap_sample"
            else "session_blueprint",
            "proposal_id": proposal_id,
            "runtime_surfaces": ["battle_toolbar", "battle_delivery"],
        },
        "context_package": {
            "worldbook_id": worldbook_id,
            "node_id": node_id,
            "battle_config_ref": battle_config_ref,
            "map_runtime_package_ref": map_runtime_package_ref,
            "intent_source": "player_free_text",
        },
        "core_artifact_refs": core_artifacts["refs"],
        "core_artifacts": core_artifacts,
        "validation": {
            "player_text_safety": "scrubbed",
            "local_gates": [
                "intent_classification",
                "proposal_synthesis",
                "forbidden_player_terms_guard",
            ],
        },
        "runtime_refs": {},
    }


def _compiler_metadata_for_job(
    *,
    proposal_metadata: dict[str, Any],
    status: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    metadata = json.loads(json.dumps(proposal_metadata, ensure_ascii=False))
    metadata["stage"] = "compiled_sample"
    metadata["job_status"] = status
    metadata["validation"] = {
        **as_dict(metadata.get("validation")),
        "local_gates": [
            "intent_classification",
            "proposal_synthesis",
            "assetgraph_mock_compile_workflow",
            "assetgraph_delivery_workflow",
            "runtime_package_artifact",
            "delivery_payload_artifact",
        ],
        "gate_status": "passed" if status == "completed" else "failed",
    }
    metadata["runtime_refs"] = {
        "runtime_package_path": result.get("runtime_package_path"),
        "delivery_payload_path": result.get("delivery_payload_path"),
        "promotion_report_path": result.get("promotion_report_path"),
        "reviewed_media_fallback_allowed": bool(result.get("promotion_report_path"))
        and not result.get("promotion_blocked"),
        "compiled_media_status": result.get("media_status") or "not_applicable",
        "compiled_media_evidence_path": result.get("media_evidence_path"),
        "trace_count": len(result.get("trace_paths") or []),
    }
    metadata["core_artifacts"] = ai_core_artifact_service.research_job_core_artifacts(
        proposal_core_artifacts=as_dict(metadata.get("core_artifacts")),
        status=status,
        runtime_package_path=result.get("runtime_package_path"),
        delivery_payload_path=result.get("delivery_payload_path"),
        trace_paths=[str(path) for path in (result.get("trace_paths") or [])],
        completed_at=now_iso(),
    )
    metadata["core_artifact_refs"] = {
        **as_dict(metadata.get("core_artifact_refs")),
        "runtime_package_path": result.get("runtime_package_path"),
        "delivery_payload_path": result.get("delivery_payload_path"),
    }
    if status != "completed":
        metadata["failure"] = {
            "class": "compiler_pipeline_failure",
            "player_safe_message": "现场试作未能稳定封装，请稍后重试。",
        }
    return metadata


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _proposal_payload(row: Any) -> dict[str, Any]:
    if not row or not row["payload"]:
        return {}
    try:
        parsed = json.loads(row["payload"])
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _find_artifact_path(
    trace: dict[str, Any], run_dir: Path, node_id: str
) -> Path | None:
    """Return the absolute path of the first output artifact of ``node_id``.

    ``run_workflow`` writes output_refs with paths relative to ``run_dir``; we
    resolve them back to absolute paths here.
    """
    for nr in trace.get("node_runs", []):
        if nr.get("node_id") != node_id:
            continue
        for ref in nr.get("output_refs", []) or []:
            if isinstance(ref, dict) and "path" in ref:
                p = Path(ref["path"])
                if not p.is_absolute():
                    p = run_dir / p
                return p
    return None


def _compiled_runtime_identity(
    intent_text: str, candidate_kind: str, candidate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    intent = intent_text or ""
    if candidate_kind == "tower_blueprint":
        slowing = any(keyword in intent for keyword in ("拖慢", "减速", "迟滞", "slow"))
        identity = {
            "name": "迟光灯塔" if slowing else "聚光刺塔",
            "tags": ["防御塔", "迟滞" if slowing else "打击", "试作蓝图"],
            "lifecycle_state": "session_blueprint",
            "uses_per_battle": 3,
            "visual_recipes": [
                {
                    "trigger": "on_attack",
                    "kind": "chain_arc",
                    "palette_token": "light.control.warm",
                    "color": "#f4c45f",
                    "secondary_color": "#9edcff",
                    "intensity": "medium",
                    "duration_ms": 360,
                    "max_links_from_effect": "damage.max_links",
                    "arc_style": "jagged",
                    "blend_mode": "additive",
                }
            ],
        }
    elif candidate_kind == "support_item":
        identity = {
            "name": "守灯脉冲",
            "tags": ["支援", "范围", "一次性"],
            "lifecycle_state": "ephemeral",
            "uses_per_battle": 1,
            "visual_recipes": [
                {
                    "trigger": "on_activate",
                    "kind": "ring_pulse",
                    "palette_token": "light.control.warm",
                    "color": "#f4c45f",
                    "secondary_color": "#ffffff",
                    "intensity": "high",
                    "radius": 128,
                    "duration_ms": 720,
                    "blend_mode": "additive",
                },
                {
                    "trigger": "on_active",
                    "kind": "aura_field",
                    "palette_token": "light.control.warm",
                    "color": "#f4c45f",
                    "secondary_color": "#9edcff",
                    "intensity": "medium",
                    "radius": 120,
                    "duration_ms": 1200,
                    "particle_density": "low",
                    "blend_mode": "additive",
                },
            ],
        }
    else:
        identity = {
            "name": "折光绊索",
            "tags": ["陷阱", "减速", "试作品"],
            "lifecycle_state": "ephemeral",
            "uses_per_battle": 2,
            "visual_recipes": [
                {
                    "trigger": "on_activate",
                    "kind": "ring_pulse",
                    "palette_token": "light.control.cold",
                    "color": "#9edcff",
                    "secondary_color": "#ffffff",
                    "intensity": "medium",
                    "radius": 96,
                    "duration_ms": 900,
                    "blend_mode": "additive",
                },
                {
                    "trigger": "on_active",
                    "kind": "aura_field",
                    "palette_token": "light.control.cold",
                    "color": "#9edcff",
                    "secondary_color": "#cfeeff",
                    "intensity": "medium",
                    "radius": 96,
                    "duration_ms": 1200,
                    "particle_density": "low",
                    "blend_mode": "additive",
                },
            ],
        }
    if candidate:
        presentation = as_dict(candidate.get("presentation"))
        gameplay = as_dict(candidate.get("gameplay"))
        stats = as_dict(gameplay.get("base_stats"))
        identity["name"] = _sanitize_player_text(str(presentation.get("name") or identity["name"]))[:48]
        tags = presentation.get("visual_tags")
        if isinstance(tags, list) and tags:
            identity["tags"] = [_sanitize_player_text(str(item))[:24] for item in tags[:4]]
        uses = stats.get("use_count", stats.get("charges"))
        if isinstance(uses, (int, float)):
            identity["uses_per_battle"] = max(1, min(5, int(uses)))
        identity["lifecycle_state"] = str(candidate.get("lifecycle") or identity["lifecycle_state"])
    return identity


def _personalize_compiled_artifacts(
    *,
    runtime_package_path: Path,
    delivery_payload_path: Path,
    session_id: str,
    proposal_id: str,
    node_id: str,
    intent_text: str,
    proposal_summary: str,
    candidate_kind: str,
    compiled_candidate: dict[str, Any] | None = None,
    candidate_path: Path | None = None,
    compiled_media_refs: dict[str, Any] | None = None,
) -> None:
    """Bind deterministic workflow output to this proposal's compiled object.

    The workflow remains the producer of the artifact envelope. This final
    deterministic lowering step only selects allowlisted runtime fields; the
    activation service still owns schema, behavior, media, and promotion gates.
    """
    identity = _compiled_runtime_identity(intent_text, candidate_kind, compiled_candidate)
    suffix = hashlib.sha256(proposal_id.encode("utf-8")).hexdigest()[:10]
    object_id = f"compiled_{candidate_kind}_{suffix}"

    package = _load_json(runtime_package_path)
    assets = package.get("assets") if isinstance(package.get("assets"), list) else []
    if not assets or not isinstance(assets[0], dict):
        raise ValueError("compiled runtime package has no primary asset")
    asset = assets[0]
    package["package_id"] = f"package_{suffix}"
    package["session_id"] = session_id
    package["node_id"] = node_id
    package["source_refs"]["locked_manifest_id"] = f"manifest_{suffix}"
    asset["stable_internal_id"] = object_id
    asset["asset_kind"] = candidate_kind
    asset["lifecycle_state"] = identity["lifecycle_state"]
    asset["display"] = {
        "name": identity["name"],
        "summary": _sanitize_player_text(proposal_summary),
        "tags": identity["tags"],
    }
    asset["visual_recipes"] = identity["visual_recipes"]
    if compiled_media_refs is not None:
        asset["media_refs"] = compiled_media_refs
    if candidate_path is not None:
        asset["gameplay_ref"] = {
            "kind": "compiled_asset_candidate",
            "path": str(candidate_path),
            "sha256": hashlib.sha256(candidate_path.read_bytes()).hexdigest(),
        }
    asset["battle_availability"] = {
        "surfaces": ["battle_hotbar"],
        "uses_per_battle": identity["uses_per_battle"],
        "requires_delivery": True,
        "delivery_state": "research_in_progress",
    }
    runtime_package_path.write_text(
        json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    delivery = _load_json(delivery_payload_path)
    delivery["session_id"] = session_id
    delivery["node_id"] = node_id
    delivery["sample"] = {
        "stable_internal_id": object_id,
        "display_name": identity["name"],
        "uses_per_battle": identity["uses_per_battle"],
        "requires_delivery": True,
        "delivery_state": "research_in_progress",
        "delivery_delay_ms": 30000,
    }
    delivery_payload_path.write_text(
        json.dumps(delivery, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _run_two_workflows(
    session_id: str, job_id: str, proposal: dict[str, Any]
) -> dict[str, Any]:
    """Run both MVP workflows under the job's run directory.

    Returns a dict with keys: trace_paths, runtime_package_path,
    delivery_payload_path, ok (bool), error (str|None).
    """
    rw = _import_run_workflow()
    registry = _load_registry()
    job_dir = _RUNS_ROOT / session_id / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    trace_paths: list[str] = []
    runtime_package_path: str | None = None
    delivery_payload_path: str | None = None
    error: str | None = None

    # Workflow 1: mock asset compile (proof the AI compile pipeline runs).
    wf_mock = _load_workflow(_MOCK_COMPILE_WORKFLOW)
    mock_out = job_dir / "mock_compile"
    trace_mock = rw.run_workflow(wf_mock, registry, mock_out)
    mock_trace_path = mock_out / wf_mock["workflow_id"] / "execution_trace.json"
    if mock_trace_path.exists():
        trace_paths.append(str(mock_trace_path))
    if trace_mock.get("status") != "passed":
        error = f"mock_compile workflow did not pass: {trace_mock.get('error', '')}"
        return {
            "trace_paths": trace_paths,
            "runtime_package_path": None,
            "delivery_payload_path": None,
            "ok": False,
            "error": error,
        }

    # Workflow 2: trap delivery (produces runtime_package + delivery payload).
    wf_trap = _load_workflow(_TRAP_DELIVERY_WORKFLOW)
    trap_out = job_dir / "trap_delivery"
    trace_trap = rw.run_workflow(wf_trap, registry, trap_out)
    trap_run_dir = trap_out / wf_trap["workflow_id"]
    trap_trace_path = trap_run_dir / "execution_trace.json"
    if trap_trace_path.exists():
        trace_paths.append(str(trap_trace_path))
    if trace_trap.get("status") != "passed":
        error = f"trap_delivery workflow did not pass: {trace_trap.get('error', '')}"
        return {
            "trace_paths": trace_paths,
            "runtime_package_path": None,
            "delivery_payload_path": None,
            "ok": False,
            "error": error,
        }

    rp_path = _find_artifact_path(trace_trap, trap_run_dir, "build_runtime_package")
    dp_path = _find_artifact_path(
        trace_trap, trap_run_dir, "build_delivery_payload"
    )
    if rp_path is not None and rp_path.exists():
        runtime_package_path = str(rp_path)
    if dp_path is not None and dp_path.exists():
        delivery_payload_path = str(dp_path)

    if runtime_package_path and delivery_payload_path:
        metadata = as_dict(proposal.get("compiler_metadata"))
        compiled_object = as_dict(metadata.get("compiled_object"))
        compiled_candidate = as_dict(proposal.get("compiled_candidate"))
        candidate_path = None
        if compiled_candidate:
            candidate_path = live_asset_compile_service.write_candidate(
                compiled_candidate, Path(runtime_package_path).parent
            )
        try:
            generation = as_dict(metadata.get("generation"))
            provider_backed = (
                generation.get("provider_call_performed") is True
                and candidate_path is not None
            )
            media_result: dict[str, Any] = {
                "status": "not_applicable",
                "media_refs": None,
                "evidence_path": None,
                "published_ref": None,
            }
            if provider_backed:
                media_result = research_runtime_media_service.compile_runtime_media(
                    candidate=compiled_candidate,
                    asset_kind=str(
                        compiled_object.get("candidate_kind")
                        or "temporary_trap_sample"
                    ),
                    session_id=session_id,
                    job_id=job_id,
                    job_dir=job_dir,
                )
            _personalize_compiled_artifacts(
                runtime_package_path=Path(runtime_package_path),
                delivery_payload_path=Path(delivery_payload_path),
                session_id=session_id,
                proposal_id=str(proposal.get("proposal_id") or "proposal"),
                node_id=str(proposal.get("node_id") or "gray_lantern_station"),
                intent_text=str(proposal.get("intent_text") or ""),
                proposal_summary=str(proposal.get("summary") or "临时试作品。"),
                candidate_kind=str(
                    compiled_object.get("candidate_kind") or "temporary_trap_sample"
                ),
                compiled_candidate=compiled_candidate or None,
                candidate_path=candidate_path,
                compiled_media_refs=(
                    as_dict(media_result.get("media_refs"))
                    if provider_backed
                    else None
                ),
            )
            promotion_report_path = None
            promotion_blocked = False
            if provider_backed:
                simulator = _import_simulate_asset_candidate()
                simulation_report = simulator.simulate(
                    compiled_candidate, simulator.DEFAULT_DURATION_SECONDS
                )
                simulation_report_path = job_dir / _LIVE_CANDIDATE_SIMULATION_REPORT_NAME
                simulation_report_path.write_text(
                    json.dumps(simulation_report, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                promotion_result = live_asset_compile_service.write_promotion_report(
                    package_path=Path(runtime_package_path),
                    candidate_path=candidate_path,
                    job_dir=job_dir,
                    created_at=now_iso(),
                    profile=str(generation.get("profile") or "unknown_profile"),
                    model=str(generation.get("model") or "unknown_model"),
                    simulation_report=simulation_report,
                    simulation_report_path=simulation_report_path,
                    media_result=media_result,
                )
                promotion_report_path = promotion_result["path"]
                promotion_blocked = not promotion_result["promotion_allowed"]
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return {
                "trace_paths": trace_paths,
                "runtime_package_path": None,
                "delivery_payload_path": None,
                "ok": False,
                "error": f"runtime lowering failed: {exc}",
            }
    else:
        promotion_report_path = None
        promotion_blocked = False

    error: str | None = None
    if promotion_blocked:
        error = "live_candidate_simulation_blocked"

    return {
        "trace_paths": trace_paths,
        "runtime_package_path": runtime_package_path,
        "delivery_payload_path": delivery_payload_path,
        "promotion_report_path": str(promotion_report_path) if promotion_report_path else None,
        "promotion_blocked": promotion_blocked,
        "media_status": media_result.get("status") if runtime_package_path and delivery_payload_path else "not_applicable",
        "media_evidence_path": media_result.get("evidence_path") if runtime_package_path and delivery_payload_path else None,
        "ok": True,
        "error": error,
    }


# ---------------------------------------------------------------------------
# Public service entrypoints
# ---------------------------------------------------------------------------


def create_proposal(session_id: str, intent_text: str, node_id: str) -> dict[str, Any]:
    """Create a research proposal row and return its public representation."""
    proposal_id = secrets.token_urlsafe(16)
    fields = _synthesize_proposal_fields(intent_text, node_id)
    world_bundle = world_catalog_service.session_bundle(session_id)
    worldbook = as_dict(world_bundle.get("worldbook"))
    worldbook_id = str(worldbook.get("worldbook_id") or "long_night_lanterns")
    if worldbook_id != "long_night_lanterns":
        fields = {
            "display_name": "现场试作方案",
            "summary": _sanitize_player_text(f"围绕“{intent_text[:72]}”形成的本局临时装置。"),
            "risk_note": "试作品的完整代价需要在实战中继续确认。",
            "player_state_message": "现场试作方案已就绪，等待确认。",
        }
    world_context = {
        "display_name": worldbook.get("display_name"),
        "summary": worldbook.get("summary"),
        "tone_and_taboos": worldbook.get("tone_and_taboos"),
        "resource_mapping": worldbook.get("resource_mapping"),
        "enemy_mapping": worldbook.get("enemy_mapping"),
        "asset_naming_rules": worldbook.get("asset_naming_rules"),
        "visual_rules": worldbook.get("visual_rules"),
    }
    candidate_kind = _candidate_kind_from_intent(intent_text)
    live_result = live_asset_compile_service.compile_candidate(
        proposal_id=proposal_id,
        intent_text=intent_text,
        worldbook_id=worldbook_id,
        candidate_kind=candidate_kind,
        display_name=fields["display_name"],
        summary=fields["summary"],
        world_context=world_context,
    )
    compiled_candidate = as_dict(live_result.get("candidate"))
    if compiled_candidate:
        fields.update(
            {
                key: _sanitize_player_text(value)
                for key, value in live_asset_compile_service.player_fields(compiled_candidate).items()
            }
        )
    compiler_metadata = _compiler_metadata_for_proposal(
        session_id=session_id,
        proposal_id=proposal_id,
        node_id=node_id,
        intent_text=intent_text,
        display_name=fields["display_name"],
        proposal_summary=fields["summary"],
        worldbook_id=worldbook_id,
    )
    provenance = as_dict(live_result.get("provenance"))
    compiler_metadata["generation"] = provenance or {
        "mode": "deterministic_fallback",
        "provider_call_performed": False,
        "fallback_reason": str(live_result.get("reason") or "not_requested"),
        "raw_prompt_stored": False,
        "raw_response_stored": False,
    }
    ts = now_iso()
    payload = json.dumps(
        {
            "intent_text": intent_text,
            "node_id": node_id,
            "compiler_metadata": compiler_metadata,
            "compiled_candidate": compiled_candidate or None,
        },
        ensure_ascii=False,
    )
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO research_proposals "
            "(proposal_id, session_id, node_id, intent_text, display_name, summary, "
            " risk_note, player_state_message, status, payload, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                proposal_id,
                session_id,
                node_id,
                intent_text,
                fields["display_name"],
                fields["summary"],
                fields["risk_note"],
                fields["player_state_message"],
                "proposed",
                payload,
                ts,
                ts,
            ),
        )
        cur.execute(
            "SELECT proposal_id, session_id, node_id, display_name, summary, "
            "risk_note, player_state_message, payload FROM research_proposals "
            "WHERE proposal_id = ?",
            (proposal_id,),
        )
        row = cur.fetchone()
    assert row is not None
    data = dict(row)
    payload_obj = _proposal_payload(row)
    data["compiler_metadata"] = as_dict(payload_obj.get("compiler_metadata"))
    data["compiled_candidate"] = as_dict(payload_obj.get("compiled_candidate")) or None
    data.pop("payload", None)
    return data


def confirm_proposal(session_id: str, proposal_id: str) -> dict[str, Any]:
    """Idempotently enqueue one durable compilation job for a proposal."""
    ts = now_iso()
    job_id = secrets.token_urlsafe(16)
    with db_cursor() as cur:
        # Verify session exists.
        cur.execute(
            "SELECT session_id FROM sessions WHERE session_id = ?",
            (session_id,),
        )
        if cur.fetchone() is None:
            return {"error": "session_not_found"}
        # Verify the proposal exists and belongs to this session.
        cur.execute(
            "SELECT proposal_id, node_id, intent_text, display_name, summary, "
            "status, payload FROM research_proposals "
            "WHERE proposal_id = ? AND session_id = ?",
            (proposal_id, session_id),
        )
        prow = cur.fetchone()
        if prow is None:
            return {"error": "proposal_not_found"}
        # The unique proposal index makes repeated or concurrent confirms return
        # the original job instead of scheduling duplicate work.
        cur.execute(
            "INSERT OR IGNORE INTO research_jobs "
            "(job_id, session_id, proposal_id, status, player_state_message, "
            " runtime_package_path, delivery_payload_path, trace_paths, payload, "
            " created_at, updated_at, completed_at) "
            "VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, NULL)",
            (
                job_id,
                session_id,
                proposal_id,
                "queued",
                "现场试作已登记，工坊很快开始准备。",
                "[]",
                "{}",
                ts,
                ts,
            ),
        )
        inserted = cur.rowcount == 1
        cur.execute(
            "UPDATE research_proposals SET status = ?, updated_at = ? "
            "WHERE proposal_id = ? AND session_id = ?",
            ("confirmed", now_iso(), proposal_id, session_id),
        )
        cur.execute(
            "SELECT job_id FROM research_jobs WHERE proposal_id = ? AND session_id = ?",
            (proposal_id, session_id),
        )
        job_row = cur.fetchone()
    assert job_row is not None
    job_id = str(job_row["job_id"])

    # Explicit compatibility mode keeps older focused tests deterministic. It
    # is never selected implicitly in production.
    if research_worker_mode() == "inline":
        claimed = claim_job(job_id)
        if claimed is not None:
            run_claimed_job(claimed)
    elif inserted:
        # Return the enqueue acknowledgement itself. This guarantees the first
        # confirm cannot race an unusually fast worker and appear synchronous.
        return {
            "job_id": job_id,
            "session_id": session_id,
            "proposal_id": proposal_id,
            "status": "queued",
            "player_state_message": "现场试作已登记，工坊很快开始准备。",
            "runtime_package_path": None,
            "delivery_payload_path": None,
            "trace_paths": [],
            "compiler_metadata": {},
            "created_at": ts,
            "updated_at": ts,
            "completed_at": None,
        }
    job = get_job(session_id, job_id)
    assert job is not None
    return job


def research_worker_mode() -> str:
    """Return the explicit worker mode; background is the production default."""
    value = os.environ.get("AI_TD_RESEARCH_WORKER_MODE", "background")
    return value.strip().lower()


def recover_running_jobs() -> int:
    """Return interrupted jobs to the durable queue during process startup."""
    ts = now_iso()
    with db_cursor() as cur:
        cur.execute(
            "UPDATE research_jobs SET status = 'queued', player_state_message = ?, "
            "updated_at = ?, completed_at = NULL WHERE status = 'running'",
            ("工坊已重新接续这份试作，请稍候。", ts),
        )
        return cur.rowcount


def claim_next_job() -> dict[str, Any] | None:
    """Atomically claim the oldest queued job across competing processes."""
    ts = now_iso()
    with db_cursor() as cur:
        cur.execute(
            "UPDATE research_jobs SET status = 'running', player_state_message = ?, "
            "updated_at = ? WHERE job_id = ("
            "SELECT job_id FROM research_jobs WHERE status = 'queued' "
            "ORDER BY created_at, job_id LIMIT 1"
            ") AND status = 'queued' RETURNING job_id, session_id, proposal_id, status",
            ("工坊正在准备这份试作，请稍候。", ts),
        )
        row = cur.fetchone()
    return dict(row) if row is not None else None


def claim_job(job_id: str) -> dict[str, Any] | None:
    """Atomically claim a specific queued job for explicit inline execution."""
    with db_cursor() as cur:
        cur.execute(
            "UPDATE research_jobs SET status = 'running', player_state_message = ?, "
            "updated_at = ? WHERE job_id = ? AND status = 'queued' "
            "RETURNING job_id, session_id, proposal_id, status",
            ("工坊正在准备这份试作，请稍候。", now_iso(), job_id),
        )
        row = cur.fetchone()
    return dict(row) if row is not None else None


def requeue_interrupted_job(job_id: str) -> None:
    """Best-effort recovery when the worker fails outside workflow handling."""
    with db_cursor() as cur:
        cur.execute(
            "UPDATE research_jobs SET status = 'queued', player_state_message = ?, "
            "updated_at = ?, completed_at = NULL "
            "WHERE job_id = ? AND status = 'running'",
            ("工坊暂时停顿，正在重新接续这份试作。", now_iso(), job_id),
        )


def _claimed_proposal(claimed: dict[str, Any]) -> dict[str, Any] | None:
    with db_cursor() as cur:
        cur.execute(
            "SELECT proposal_id, node_id, intent_text, display_name, summary, payload "
            "FROM research_proposals WHERE proposal_id = ? AND session_id = ?",
            (claimed["proposal_id"], claimed["session_id"]),
        )
        row = cur.fetchone()
    if row is None:
        return None
    proposal_payload = _proposal_payload(row)
    proposal_metadata = as_dict(proposal_payload.get("compiler_metadata"))
    if not proposal_metadata:
        proposal_metadata = _compiler_metadata_for_proposal(
            session_id=str(claimed["session_id"]),
            proposal_id=str(row["proposal_id"]),
            node_id=str(row["node_id"] or "gray_lantern_station"),
            intent_text=str(row["intent_text"] or ""),
            display_name=str(row["display_name"] or "临时光幕方案"),
            proposal_summary=str(row["summary"] or "以灯光构筑的临时防线。"),
            worldbook_id="long_night_lanterns",
        )
    return {
        "proposal_id": row["proposal_id"],
        "node_id": row["node_id"],
        "intent_text": row["intent_text"],
        "display_name": row["display_name"],
        "summary": row["summary"],
        "compiler_metadata": proposal_metadata,
        "compiled_candidate": as_dict(proposal_payload.get("compiled_candidate")),
    }


def run_claimed_job(claimed: dict[str, Any]) -> dict[str, Any] | None:
    """Execute and finalize a job previously moved to ``running`` by claim."""
    session_id = str(claimed["session_id"])
    job_id = str(claimed["job_id"])
    proposal_id = str(claimed["proposal_id"])
    proposal = _claimed_proposal(claimed)
    if proposal is None:
        result = {
            "ok": False,
            "error": "proposal missing while processing claimed job",
            "trace_paths": [],
            "runtime_package_path": None,
            "delivery_payload_path": None,
        }
        proposal_metadata: dict[str, Any] = {}
    else:
        proposal_metadata = as_dict(proposal.get("compiler_metadata"))
        try:
            result = _run_two_workflows(session_id, job_id, proposal)
        except Exception as exc:  # keep the durable worker alive after one bad job
            result = {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "trace_paths": [],
                "runtime_package_path": None,
                "delivery_payload_path": None,
            }

    completed_at = now_iso()
    if (
        result["ok"]
        and result["runtime_package_path"]
        and result["delivery_payload_path"]
        and not result.get("promotion_blocked")
    ):
        status = "completed"
        player_msg = _sanitize_player_text(
            f"试作准备完成，临时防线已送达{_node_display(_proposal_node_id(session_id, proposal_id))}。"
        )
        compiler_metadata = _compiler_metadata_for_job(
            proposal_metadata=proposal_metadata,
            status=status,
            result=result,
        )
        payload = json.dumps(
            {
                "trace_paths": result["trace_paths"],
                "compiler_metadata": compiler_metadata,
            },
            ensure_ascii=False,
        )
    else:
        status = "failed"
        player_msg = _sanitize_player_text("现场试作未能稳定封装，请稍后重试。")
        compiler_metadata = _compiler_metadata_for_job(
            proposal_metadata=proposal_metadata,
            status=status,
            result=result,
        )
        payload = json.dumps(
            {
                "error": result.get("error") or "unknown failure",
                "trace_paths": result["trace_paths"],
                "compiler_metadata": compiler_metadata,
            },
            ensure_ascii=False,
        )

    trace_paths_json = json.dumps(result["trace_paths"], ensure_ascii=False)
    with db_cursor() as cur:
        cur.execute(
            "UPDATE research_jobs SET status = ?, player_state_message = ?, "
            "runtime_package_path = ?, delivery_payload_path = ?, trace_paths = ?, "
            "payload = ?, updated_at = ?, completed_at = ? "
            "WHERE job_id = ? AND status = 'running'",
            (
                status,
                player_msg,
                result["runtime_package_path"],
                result["delivery_payload_path"],
                trace_paths_json,
                payload,
                now_iso(),
                completed_at,
                job_id,
            ),
        )

    return get_job(session_id, job_id)


def _proposal_node_id(session_id: str, proposal_id: str) -> str:
    """Fetch the node_id for a proposal (used to phrase the success message)."""
    with db_cursor() as cur:
        cur.execute(
            "SELECT node_id FROM research_proposals "
            "WHERE proposal_id = ? AND session_id = ?",
            (proposal_id, session_id),
        )
        row = cur.fetchone()
    return row["node_id"] if row else ""


def get_job(session_id: str, job_id: str) -> dict[str, Any] | None:
    """Return the public representation of a research job, or None."""
    with db_cursor() as cur:
        cur.execute(
            "SELECT job_id, session_id, proposal_id, status, player_state_message, "
            "runtime_package_path, delivery_payload_path, trace_paths, payload, "
            "created_at, updated_at, completed_at FROM research_jobs "
            "WHERE job_id = ? AND session_id = ?",
            (job_id, session_id),
        )
        row = cur.fetchone()
    if row is None:
        return None
    trace_paths: list[str] = []
    raw_traces = row.get("trace_paths")
    if raw_traces:
        try:
            parsed = json.loads(raw_traces)
            if isinstance(parsed, list):
                trace_paths = [str(p) for p in parsed]
        except json.JSONDecodeError:
            trace_paths = []
    payload = {}
    if row.get("payload"):
        try:
            parsed_payload = json.loads(row["payload"])
            if isinstance(parsed_payload, dict):
                payload = parsed_payload
        except json.JSONDecodeError:
            payload = {}
    return {
        "job_id": row["job_id"],
        "session_id": row["session_id"],
        "proposal_id": row["proposal_id"],
        "status": row["status"],
        "player_state_message": row["player_state_message"],
        "runtime_package_path": row["runtime_package_path"],
        "delivery_payload_path": row["delivery_payload_path"],
        "trace_paths": trace_paths,
        "compiler_metadata": as_dict(payload.get("compiler_metadata")),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "completed_at": row["completed_at"],
    }
