"""Research job service: bridges the player-facing research API and the
AssetGraph Kernel v0.1 deterministic workflow runner.

This module is intentionally MVP-shaped:
- ``create_proposal`` synthesizes a world-in-language proposal deterministically
  from the player's ``intent_text`` and ``node_id``. No real LLM is called.
- ``confirm_proposal`` runs two AssetGraph workflows synchronously, lowers the
  proposal into one of the allowlisted playable object kinds, and stores the
  resulting artifact paths on a research job row. The job ends in ``completed``
  (or ``failed``) immediately.
- ``get_job`` reads the row back.

All workflow output is written under ``/tmp/ai_compiled_td_backend_runs`` so
nothing leaks into the repo. Player-facing strings avoid the forbidden
technical vocabulary listed in the worldbook and the task spec.
"""
from __future__ import annotations

import json
import hashlib
import secrets
import sys
from pathlib import Path
from typing import Any

from ..db import db_cursor, now_iso
from . import ai_core_artifact_service, battle_content_service, map_runtime_service

# Repo root (backend/app/services -> backend/app -> backend -> repo root).
_REPO_ROOT = Path(__file__).resolve().parents[3]
_ASSET_GRAPH_DIR = _REPO_ROOT / "tools" / "asset_graph"
_REGISTRY_PATH = _REPO_ROOT / "shared" / "asset_graph" / "node_registry.v0.1.json"
_WORKFLOW_DIR = _REPO_ROOT / "examples" / "workflows"

_MOCK_COMPILE_WORKFLOW = _WORKFLOW_DIR / "mvp_mock_asset_compile.workflow.json"
_TRAP_DELIVERY_WORKFLOW = _WORKFLOW_DIR / "mvp_temporary_trap_delivery.workflow.json"

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
            "worldbook_id": "long_night_lanterns",
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


def _compiled_runtime_identity(intent_text: str, candidate_kind: str) -> dict[str, Any]:
    intent = intent_text or ""
    if candidate_kind == "tower_blueprint":
        slowing = any(keyword in intent for keyword in ("拖慢", "减速", "迟滞", "slow"))
        return {
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
    if candidate_kind == "support_item":
        return {
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
    return {
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
) -> None:
    """Bind deterministic workflow output to this proposal's compiled object.

    The workflow remains the producer of the artifact envelope. This final
    deterministic lowering step only selects allowlisted runtime fields; the
    activation service still owns schema, behavior, media, and promotion gates.
    """
    identity = _compiled_runtime_identity(intent_text, candidate_kind)
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
        try:
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
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return {
                "trace_paths": trace_paths,
                "runtime_package_path": None,
                "delivery_payload_path": None,
                "ok": False,
                "error": f"runtime lowering failed: {exc}",
            }

    return {
        "trace_paths": trace_paths,
        "runtime_package_path": runtime_package_path,
        "delivery_payload_path": delivery_payload_path,
        "ok": True,
        "error": None,
    }


# ---------------------------------------------------------------------------
# Public service entrypoints
# ---------------------------------------------------------------------------


def create_proposal(session_id: str, intent_text: str, node_id: str) -> dict[str, Any]:
    """Create a research proposal row and return its public representation."""
    fields = _synthesize_proposal_fields(intent_text, node_id)
    proposal_id = secrets.token_urlsafe(16)
    compiler_metadata = _compiler_metadata_for_proposal(
        session_id=session_id,
        proposal_id=proposal_id,
        node_id=node_id,
        intent_text=intent_text,
        display_name=fields["display_name"],
        proposal_summary=fields["summary"],
    )
    ts = now_iso()
    payload = json.dumps(
        {
            "intent_text": intent_text,
            "node_id": node_id,
            "compiler_metadata": compiler_metadata,
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
    data.pop("payload", None)
    return data


def confirm_proposal(session_id: str, proposal_id: str) -> dict[str, Any]:
    """Confirm a proposal: create a job and run both workflows synchronously."""
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
        # Verify proposal exists, belongs to this session, and is not confirmed.
        cur.execute(
            "SELECT proposal_id, node_id, intent_text, display_name, summary, "
            "status, payload FROM research_proposals "
            "WHERE proposal_id = ? AND session_id = ?",
            (proposal_id, session_id),
        )
        prow = cur.fetchone()
        if prow is None:
            return {"error": "proposal_not_found"}
        proposal_payload = _proposal_payload(prow)
        proposal_metadata = as_dict(proposal_payload.get("compiler_metadata"))
        if not proposal_metadata:
            proposal_metadata = _compiler_metadata_for_proposal(
                session_id=session_id,
                proposal_id=proposal_id,
                node_id=str(proposal_payload.get("node_id") or "gray_lantern_station"),
                intent_text=str(proposal_payload.get("intent_text") or ""),
                display_name="临时光幕方案",
                proposal_summary="以灯光构筑的临时防线，为节点争取喘息。",
            )
        # Insert the job row in "running" state before executing workflows so
        # that even a crash leaves an auditable record.
        cur.execute(
            "INSERT INTO research_jobs "
            "(job_id, session_id, proposal_id, status, player_state_message, "
            " runtime_package_path, delivery_payload_path, trace_paths, payload, "
            " created_at, updated_at, completed_at) "
            "VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, NULL)",
            (
                job_id,
                session_id,
                proposal_id,
                "running",
                "现场试作正在封装，请稍候。",
                "[]",
                "{}",
                ts,
                ts,
            ),
        )
        cur.execute(
            "UPDATE research_proposals SET status = ?, updated_at = ? "
            "WHERE proposal_id = ?",
            ("confirmed", now_iso(), proposal_id),
        )

    # Run the workflows outside the cursor block (no DB lock held during IO).
    result = _run_two_workflows(
        session_id,
        job_id,
        {
            "proposal_id": prow["proposal_id"],
            "node_id": prow["node_id"],
            "intent_text": prow["intent_text"],
            "display_name": prow["display_name"],
            "summary": prow["summary"],
            "compiler_metadata": proposal_metadata,
        },
    )
    completed_at = now_iso()
    if result["ok"] and result["runtime_package_path"] and result["delivery_payload_path"]:
        status = "completed"
        player_msg = _sanitize_player_text(
            f"试作封装完成，临时防线已送达{_node_display(_proposal_node_id(session_id, proposal_id))}。"
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
            "payload = ?, updated_at = ?, completed_at = ? WHERE job_id = ?",
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
