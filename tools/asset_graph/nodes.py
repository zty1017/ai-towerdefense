"""Node implementations for the AssetGraph Kernel v0.1.

Most nodes in this module are deterministic / mock. Live-only nodes can call
external providers, but only when the workflow and node params explicitly
enable that path. Each node function takes:
- inputs: dict[input_name, ArtifactRef dict] (resolved refs pointing at files in run dir)
- params: dict (literal params from the workflow node)
- run_dir: Path (where this node should write its output artifact)
- content_pipeline_path: Path (so we can import existing validators)

And returns:
- dict with "output_refs": dict[output_name, ArtifactRef dict]
- on failure raises NodeError(message)
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
CONTENT_PIPELINE = ROOT / "tools" / "content_pipeline"
if str(CONTENT_PIPELINE) not in sys.path:
    sys.path.insert(0, str(CONTENT_PIPELINE))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import mock_compile_proposal  # noqa: E402
import simulate_asset_candidate  # noqa: E402
import validate_asset_candidate  # noqa: E402
import validate_proposal  # noqa: E402
import runtime_package as rp  # noqa: E402

WORLD_STATE_DIR = ROOT / "tools" / "world_state"
if str(WORLD_STATE_DIR) not in sys.path:
    sys.path.insert(0, str(WORLD_STATE_DIR))

import validate_run_world_state as v_rws  # noqa: E402
import validate_world_delta as v_wd  # noqa: E402
import apply_world_delta as a_wd  # noqa: E402

LLM_DIR = ROOT / "tools" / "llm"
if str(LLM_DIR) not in sys.path:
    sys.path.insert(0, str(LLM_DIR))

import adapter as llm_adapter  # noqa: E402
import asset_candidate_prompt  # noqa: E402
import world_delta_prompt  # noqa: E402

MEDIA_DIR = ROOT / "tools" / "media"
if str(MEDIA_DIR) not in sys.path:
    sys.path.insert(0, str(MEDIA_DIR))

import image_provider as img_provider  # noqa: E402
import asset_media_prompt  # noqa: E402


DEFAULT_REGISTRY_PATH = ROOT / "shared/module_registry/effect_blocks.v0.1.json"


class NodeError(Exception):
    """Raised when a node fails deterministically."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json(path: Path, data: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    path.write_text(payload + "\n", encoding="utf-8")
    return _sha256_bytes(payload.encode("utf-8"))


def _make_ref(
    artifact_id: str,
    kind: str,
    path: Path,
    run_dir: Path,
    *,
    media_layer: str | None = None,
    produced_by_node: str | None = None,
) -> dict[str, Any]:
    rel = path.relative_to(run_dir).as_posix() if path.is_relative_to(run_dir) else str(path)
    ref: dict[str, Any] = {
        "artifact_id": artifact_id,
        "kind": kind,
        "path": rel,
        "sha256": _sha256_file(path),
        "content_type": "application/json",
        "byte_size": path.stat().st_size,
        "produced_by_node": produced_by_node or "",
        "produced_at": _now_iso(),
    }
    if media_layer:
        ref["media_layer"] = media_layer
    return ref


def _load_artifact(inputs: dict[str, Any], name: str) -> dict[str, Any]:
    """Load JSON content from an input ArtifactRef."""
    ref = inputs.get(name)
    if ref is None:
        raise NodeError(f"missing required input artifact: {name}")
    if not isinstance(ref, dict) or "path" not in ref:
        raise NodeError(f"input {name!r} is not a valid ArtifactRef")
    p = Path(ref["path"])
    if not p.is_absolute():
        # Runner resolves refs against run_dir before calling nodes; this is a
        # safety fallback.
        raise NodeError(
            f"input {name!r} path {ref['path']!r} was not resolved to an absolute path"
        )
    if not p.exists():
        raise NodeError(f"input {name!r} file not found: {p}")
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        raise NodeError(f"input {name!r} is not valid JSON: {exc}") from exc


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------


def node_source_load_json(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    raw_path = params.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        raise NodeError("params.path is required")
    src = Path(raw_path)
    if not src.is_absolute():
        src = ROOT / src
    if not src.exists():
        raise NodeError(f"source file not found: {src}")
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise NodeError(f"source file is not valid JSON: {exc}") from exc

    out_path = run_dir / f"{node_id}__loaded.json"
    _write_json(out_path, data)
    ref = _make_ref(
        artifact_id=f"{node_id}__loaded",
        kind="json",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
    )
    return {"output_refs": {"default": ref}}


def node_proposal_validate(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    proposal = _load_artifact(inputs, "proposal")
    errs = validate_proposal.validate(proposal)
    result = {
        "status": "passed" if not errs else "failed",
        "errors": errs,
        "proposal_id": proposal.get("id"),
    }
    out_path = run_dir / f"{node_id}__proposal_validation.json"
    _write_json(out_path, result)
    ref = _make_ref(
        artifact_id=f"{node_id}__proposal_validation",
        kind="validation_result",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
    )
    if errs:
        raise NodeError(f"proposal validation failed: {errs}")
    return {"output_refs": {"default": ref}}


def node_asset_mock_compile_proposal(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    proposal = _load_artifact(inputs, "proposal")
    candidate = mock_compile_proposal.compile_candidate(
        proposal, provider="mock", model="mock_compiler_v0.1"
    )
    out_path = run_dir / f"{node_id}__compiled_asset.json"
    _write_json(out_path, candidate)
    ref = _make_ref(
        artifact_id=f"{node_id}__compiled_asset",
        kind="compiled_asset_candidate",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
    )
    return {"output_refs": {"default": ref}}


def node_asset_validate_candidate(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    candidate = _load_artifact(inputs, "candidate")
    # Optional registry input; default to the shared effect blocks registry.
    if "registry" in inputs and inputs["registry"] is not None:
        registry = _load_artifact(inputs, "registry")
    else:
        registry = json.loads(DEFAULT_REGISTRY_PATH.read_text(encoding="utf-8"))
    errs = validate_asset_candidate.validate(candidate, registry)
    result = {
        "status": "passed" if not errs else "failed",
        "errors": errs,
        "candidate_id": candidate.get("id"),
    }
    out_path = run_dir / f"{node_id}__candidate_validation.json"
    _write_json(out_path, result)
    ref = _make_ref(
        artifact_id=f"{node_id}__candidate_validation",
        kind="validation_result",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
    )
    if errs:
        raise NodeError(f"candidate validation failed: {errs}")
    return {"output_refs": {"default": ref}}


def node_asset_simulate_candidate(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    candidate = _load_artifact(inputs, "candidate")
    duration = float(
        params.get("duration_seconds", simulate_asset_candidate.DEFAULT_DURATION_SECONDS)
    )
    sim = simulate_asset_candidate.simulate(candidate, duration)
    out_path = run_dir / f"{node_id}__simulation_report.json"
    _write_json(out_path, sim)
    ref = _make_ref(
        artifact_id=f"{node_id}__simulation_report",
        kind="simulation_report",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
    )
    return {"output_refs": {"default": ref}}


def node_report_pipeline_summary(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "status": "passed",
        "stages": {},
    }
    for name in ("proposal_validation", "candidate_validation", "simulation"):
        ref = inputs.get(name)
        if ref is None:
            summary["stages"][name] = {"status": "skipped"}
            continue
        try:
            data = _load_artifact(inputs, name)
        except NodeError as exc:
            summary["stages"][name] = {"status": "failed", "error": str(exc)}
            summary["status"] = "partial"
            continue
        summary["stages"][name] = {
            "status": data.get("status", "passed"),
            "path": ref.get("path"),
        }
        if name == "simulation" and isinstance(data, dict):
            summary["balance_flags"] = data.get("balance_flags", [])
    out_path = run_dir / f"{node_id}__pipeline_summary.json"
    _write_json(out_path, summary)
    ref = _make_ref(
        artifact_id=f"{node_id}__pipeline_summary",
        kind="pipeline_summary",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
    )
    return {"output_refs": {"default": ref}}


def node_runtime_build_package_stub(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    """Build a real RuntimePackage v0.1 from upstream locked_manifest + battle_config.

    The node_type name is kept as ``runtime.build_package_stub`` for backwards
    compatibility with existing v0.1 workflows, but the implementation now
    delegates to the formal builder in ``runtime_package.build_runtime_package``
    and validates the result with the same safety rules used by the
    ``validate_runtime_package`` CLI. The output artifact is runtime_public
    safe: no provider/trace fields, no raw_media/processed_media, no
    source_layer, no external URLs, only /assets/ media refs.
    """
    manifest = _load_artifact(inputs, "locked_manifest")
    battle = _load_artifact(inputs, "battle_config")
    package_id = f"package_{manifest.get('session_id', 'session')}_{secrets.token_hex(4)}"
    package = rp.build_runtime_package(
        manifest,
        battle,
        package_id=package_id,
        created_at=_now_iso(),
    )
    # Validate before writing so a runtime_public post-check failure never
    # surfaces from a builder bug; raise NodeError with concrete paths instead.
    schema_path = ROOT / "shared/schemas/runtime_package.v0.1.schema.json"
    schema: dict[str, Any] | None = None
    if schema_path.exists():
        try:
            with schema_path.open("r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                schema = loaded
        except (OSError, json.JSONDecodeError):
            pass
    errors = rp.validate_package(package, schema)
    if errors:
        raise NodeError(
            f"runtime package validation failed: {'; '.join(errors)}"
        )
    out_path = run_dir / f"{node_id}__runtime_package.json"
    _write_json(out_path, package)
    ref = _make_ref(
        artifact_id=f"{node_id}__runtime_package",
        kind="runtime_package",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
    )
    return {"output_refs": {"default": ref}}


def node_research_build_delivery_payload_stub(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    manifest = _load_artifact(inputs, "locked_manifest")
    battle = _load_artifact(inputs, "battle_config")
    locked_assets = manifest.get("locked_assets", [])
    sample = next(
        (a for a in locked_assets if a.get("asset_kind") == "temporary_trap_sample"),
        None,
    )
    payload = {
        "payload_version": "research_delivery_payload_stub.v0.1",
        "session_id": manifest.get("session_id"),
        "node_id": battle.get("node_id"),
        "sample": {
            "stable_internal_id": sample.get("stable_internal_id") if sample else None,
            "display_name": sample.get("display", {}).get("name") if sample else None,
            "uses_per_battle": sample.get("battle_availability", {}).get("uses_per_battle") if sample else None,
            "requires_delivery": sample.get("battle_availability", {}).get("requires_delivery") if sample else None,
            "delivery_state": sample.get("battle_availability", {}).get("delivery_state") if sample else None,
            "delivery_delay_ms": battle.get("sample_asset", {}).get("delivery_delay_ms"),
        },
        # Player-facing delivery progress messages use world-in language only.
        "delivery_progress_messages": battle.get("sample_asset", {}).get(
            "delivery_progress_messages", []
        ),
    }
    out_path = run_dir / f"{node_id}__research_delivery_payload_stub.json"
    _write_json(out_path, payload)
    ref = _make_ref(
        artifact_id=f"{node_id}__research_delivery_payload_stub",
        kind="research_delivery_payload_stub",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
    )
    return {"output_refs": {"default": ref}}


def node_media_publish_stub_manifest(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    raw_meta = _load_artifact(inputs, "raw_media_metadata")
    # raw_media_metadata is a stub describing imported/raw media. We "process"
    # it deterministically by assigning local /assets/ paths and producing a
    # published_media manifest. No real image processing occurs.
    raw_items = raw_meta.get("raw_media_items", []) if isinstance(raw_meta, dict) else []
    published: list[dict[str, Any]] = []
    for item in raw_items:
        stable_id = item.get("stable_internal_id", "media_unknown")
        published.append({
            "stable_internal_id": stable_id,
            "media_layer": "published_media",
            "url": f"/assets/published/{stable_id}.webp",
            "width": item.get("width", 512),
            "height": item.get("height", 512),
            # source_layer and raw provenance are intentionally omitted from
            # the published_media manifest: raw -> published provenance lives
            # in the execution trace / internal logs only, not in runtime_public
            # artifacts.
            "fallback_used": item.get("fallback_used", True),
        })
    manifest = {
        "manifest_version": "published_media_manifest.v0.1",
        "published_media": published,
        # raw_media and processed_media layers are intentionally NOT exposed
        # here; only published_media may be runtime_public. No source_layer
        # fields leak to the runtime side.
    }
    out_path = run_dir / f"{node_id}__published_media_manifest.json"
    _write_json(out_path, manifest)
    ref = _make_ref(
        artifact_id=f"{node_id}__published_media_manifest",
        kind="published_media_manifest",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
        media_layer="published_media",
    )
    return {"output_refs": {"default": ref}}


# ---------------------------------------------------------------------------
# Narrative nodes (deterministic, world-in-language, no provider/trace terms)
# ---------------------------------------------------------------------------

# Narrative player-visible output must never leak technical terms. This set is
# stricter than the runner's FORBIDDEN_FIELDS: it also bans prompt/schema/
# traceback/simulation/trace/mock anywhere in the narrative artifact (as field
# names OR as substrings inside string values). Enforced before the artifact
# is written so a forbidden term never reaches the runtime_public layer.
NARRATIVE_FORBIDDEN_TERMS = frozenset(
    {
        "provider",
        "raw_prompt",
        "full_trace",
        "raw_json",
        "api_key",
        "secret",
        "schema",
        "traceback",
        "prompt",
        "mock",
        "simulation",
        "trace",
    }
)


def _scan_narrative_forbidden(value: Any, path: str, errors: list[str]) -> None:
    """Recursively reject narrative-forbidden terms in field names or strings."""
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if isinstance(key, str) and key.lower() in NARRATIVE_FORBIDDEN_TERMS:
                errors.append(
                    f"narrative output forbidden field {child_path!r} "
                    f"(term {key!r} is not player-visible-safe)"
                )
            _scan_narrative_forbidden(child, child_path, errors)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            _scan_narrative_forbidden(child, f"{path}[{i}]", errors)
    elif isinstance(value, str):
        lowered = value.lower()
        for term in NARRATIVE_FORBIDDEN_TERMS:
            if term in lowered:
                errors.append(
                    f"narrative output {path}={value!r} contains forbidden "
                    f"term {term!r}"
                )


def _enforce_narrative_safe(payload: dict[str, Any], node_id: str) -> None:
    """Raise NodeError if the narrative payload carries any forbidden term."""
    errors: list[str] = []
    _scan_narrative_forbidden(payload, "", errors)
    if errors:
        raise NodeError(
            f"narrative node {node_id!r} produced forbidden content: "
            + "; ".join(errors[:5])
        )


def _narrative_context(
    battle_result: dict[str, Any], session_context: dict[str, Any]
) -> dict[str, Any]:
    return {
        "worldbook_id": session_context.get(
            "worldbook_id", battle_result.get("worldbook_id", "long_night_lanterns")
        ),
        "node_id": session_context.get(
            "node_id", battle_result.get("node_id", "gray_lantern_station")
        ),
        "session_id": session_context.get(
            "session_id", battle_result.get("session_id", "session_lampwright_7f3a")
        ),
        "player_origin": session_context.get("player_origin", "lampwright"),
    }


def _narrative_outcome_phrases(battle_result: dict[str, Any]) -> dict[str, list[str]]:
    """Map battle_result flags to world-in-language phrases. Deterministic."""
    winner = battle_result.get("winner", "player")
    core_damaged = bool(battle_result.get("core_damaged", False))
    sample_triggered = bool(battle_result.get("sample_triggered", False))
    enemies_leaked = int(battle_result.get("enemies_leaked", 0) or 0)
    waves_survived = int(battle_result.get("waves_survived", 0) or 0)

    if winner == "player":
        summary_core = "驿站核心未受损。" if not core_damaged else "驿站核心虽有损耗，但仍在点亮。"
        summary_leak = "影潮无一漏过。" if enemies_leaked == 0 else f"仍有 {enemies_leaked} 股影潮漏过灯栏。"
        summary_wave = f"共守住 {waves_survived} 波影潮。" if waves_survived else "影潮被击退。"
        battle_summary = (
            "影潮涌至灰灯驿站，灯匠以灯火与折光绊索守御。"
            + summary_core
            + summary_leak
            + summary_wave
        )
        lampwright_line = (
            "折光绊索在战场上迟滞了影潮，但样品已经用尽，需要重新试作。"
            if sample_triggered
            else "这一战没有动用折光绊索，灯栏勉强支撑住了。"
        )
        world_reinforce = "灰灯驿站的灯栏经此一役得到加固，邻近路径的能见度略有提升。"
    else:
        battle_summary = (
            "影潮压过灰灯驿站，灯栏熄灭，驿站核心陷入黑暗。灯匠带着残留的灯火与记录撤离。"
        )
        lampwright_line = "驿站没能守住，但样品的实战表现已被记录，留待来日再战。"
        world_reinforce = "灰灯驿站暂时陷入沉寂，邻近路径的灯火黯淡，影潮活动有所增强。"

    sample_event = (
        "折光绊索的实战数据被灯匠归档，为后续正式研发留下线索。"
        if sample_triggered
        else "灯匠整理了这一战的守御记录，准备改进灯栏结构。"
    )

    return {
        "battle_summary": [battle_summary],
        "lampwright_line": [lampwright_line],
        "world_reinforce": [world_reinforce],
        "sample_event": [sample_event],
    }


def _apply_narrative_test_inject(
    payload: dict[str, Any], params: dict[str, Any]
) -> None:
    """Test-only hook: merge a single forbidden field into the payload so the
    narrative content guard can be exercised end-to-end via a workflow JSON.

    Never set in production workflows. The injected field is scanned by
    _enforce_narrative_safe immediately after, so the forbidden term never
    reaches the artifact file.
    """
    field = params.get("_test_inject_field")
    if not isinstance(field, str) or not field:
        return
    payload[field] = params.get("_test_inject_value")


def node_narrative_mock_npc_feedback(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    battle_result = _load_artifact(inputs, "battle_result")
    session_context = _load_artifact(inputs, "session_context")
    ctx = _narrative_context(battle_result, session_context)
    phrases = _narrative_outcome_phrases(battle_result)

    payload: dict[str, Any] = {
        "narrative_version": "narrative.v0.1",
        "focus": "npc_feedback",
        "worldbook_id": ctx["worldbook_id"],
        "node_id": ctx["node_id"],
        "session_id": ctx["session_id"],
        "player_origin": ctx["player_origin"],
        "npc_feedback": [
            {
                "npc_id": "engineer_001",
                "name": "灯匠",
                "text": phrases["lampwright_line"][0],
            }
        ],
        "battle_summary": phrases["battle_summary"][0],
        "world_events": [
            {
                "event_id": "npc_lampwright_acknowledge_hold",
                "kind": "npc_reaction",
                "text": "灯匠确认驿站核心的状况，并记录下这一战的实战表现。",
            }
        ],
    }
    _apply_narrative_test_inject(payload, params)
    _enforce_narrative_safe(payload, node_id)

    out_path = run_dir / f"{node_id}__narrative_npc_feedback.json"
    _write_json(out_path, payload)
    ref = _make_ref(
        artifact_id=f"{node_id}__narrative_npc_feedback",
        kind="narrative_artifact",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
    )
    return {"output_refs": {"default": ref}}


def node_narrative_mock_world_growth_event(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    battle_result = _load_artifact(inputs, "battle_result")
    session_context = _load_artifact(inputs, "session_context")
    ctx = _narrative_context(battle_result, session_context)
    phrases = _narrative_outcome_phrases(battle_result)

    payload: dict[str, Any] = {
        "narrative_version": "narrative.v0.1",
        "focus": "world_growth",
        "worldbook_id": ctx["worldbook_id"],
        "node_id": ctx["node_id"],
        "session_id": ctx["session_id"],
        "player_origin": ctx["player_origin"],
        "npc_feedback": [
            {
                "npc_id": "engineer_001",
                "name": "灯匠",
                "text": "影潮退去后，驿站的灯火比先前更稳了一些。",
            }
        ],
        "battle_summary": phrases["battle_summary"][0],
        "world_events": [
            {
                "event_id": "world_gray_lantern_reinforced",
                "kind": "world_state_change",
                "text": phrases["world_reinforce"][0],
            },
            {
                "event_id": "world_sample_data_archived",
                "kind": "world_state_change",
                "text": phrases["sample_event"][0],
            },
        ],
    }
    _apply_narrative_test_inject(payload, params)
    _enforce_narrative_safe(payload, node_id)

    out_path = run_dir / f"{node_id}__narrative_world_growth.json"
    _write_json(out_path, payload)
    ref = _make_ref(
        artifact_id=f"{node_id}__narrative_world_growth",
        kind="narrative_artifact",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
    )
    return {"output_refs": {"default": ref}}


# ---------------------------------------------------------------------------
# Media stub nodes (JSON metadata only, no real image processing)
# ---------------------------------------------------------------------------


def _media_stub_step(
    inputs: dict[str, Any],
    run_dir: Path,
    node_id: str,
    *,
    step_name: str,
    input_layer: str,
    output_layer: str,
    output_filename: str,
    output_kind: str,
) -> dict[str, Any]:
    """Generic media stub: read media_metadata, advance media_layer, strip
    source_layer, append a processing step marker. No real image processing."""
    meta = _load_artifact(inputs, "media_metadata")
    actual_layer = meta.get("media_layer") if isinstance(meta, dict) else None
    if actual_layer != input_layer:
        raise NodeError(
            f"{step_name} expected media_layer={input_layer!r}, "
            f"got {actual_layer!r}"
        )
    items_in = meta.get("items", []) if isinstance(meta, dict) else []
    items_out: list[dict[str, Any]] = []
    for item in items_in:
        if not isinstance(item, dict):
            continue
        # source_layer (raw->published provenance) must NOT leak to products;
        # it lives only in trace/internal.
        new_item = {k: v for k, v in item.items() if k != "source_layer"}
        new_item["media_layer"] = output_layer
        steps = list(new_item.get("processing_steps", []))
        steps.append(step_name)
        new_item["processing_steps"] = steps
        items_out.append(new_item)
    out_meta: dict[str, Any] = {
        "metadata_version": "media_metadata.v0.1",
        "media_layer": output_layer,
        "items": items_out,
    }
    out_path = run_dir / f"{node_id}__{output_filename}"
    _write_json(out_path, out_meta)
    ref = _make_ref(
        artifact_id=f"{node_id}__{output_kind}",
        kind=output_kind,
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
        media_layer=output_layer,
    )
    return {"output_refs": {"default": ref}}


def node_media_remove_background_stub(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    return _media_stub_step(
        inputs,
        run_dir,
        node_id,
        step_name="remove_background",
        input_layer="raw_media",
        output_layer="processed_media",
        output_filename="media_remove_background.json",
        output_kind="media_metadata",
    )


def node_media_crop_and_pad_stub(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    return _media_stub_step(
        inputs,
        run_dir,
        node_id,
        step_name="crop_and_pad",
        input_layer="processed_media",
        output_layer="processed_media",
        output_filename="media_crop_and_pad.json",
        output_kind="media_metadata",
    )


def node_media_normalize_canvas_stub(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    return _media_stub_step(
        inputs,
        run_dir,
        node_id,
        step_name="normalize_canvas",
        input_layer="processed_media",
        output_layer="processed_media",
        output_filename="media_normalize_canvas.json",
        output_kind="media_metadata",
    )


def node_media_assign_anchor_stub(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    return _media_stub_step(
        inputs,
        run_dir,
        node_id,
        step_name="assign_anchor",
        input_layer="processed_media",
        output_layer="processed_media",
        output_filename="media_assign_anchor.json",
        output_kind="media_metadata",
    )


def node_media_pack_sprite_sheet_stub(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    return _media_stub_step(
        inputs,
        run_dir,
        node_id,
        step_name="pack_sprite_sheet",
        input_layer="processed_media",
        output_layer="processed_media",
        output_filename="media_pack_sprite_sheet.json",
        output_kind="media_metadata",
    )


def node_media_build_atlas_json_stub(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    """Final publish step: processed_media -> published_media manifest with
    local /assets/ paths. No source_layer, no external URLs. runtime_public-safe."""
    meta = _load_artifact(inputs, "media_metadata")
    actual_layer = meta.get("media_layer") if isinstance(meta, dict) else None
    if actual_layer != "processed_media":
        raise NodeError(
            f"build_atlas_json expected media_layer='processed_media', "
            f"got {actual_layer!r}"
        )
    items_in = meta.get("items", []) if isinstance(meta, dict) else []
    published: list[dict[str, Any]] = []
    for item in items_in:
        if not isinstance(item, dict):
            continue
        stable_id = item.get("stable_internal_id", "media_unknown")
        published.append(
            {
                "stable_internal_id": stable_id,
                "media_layer": "published_media",
                "url": f"/assets/published/{stable_id}.webp",
                "width": item.get("width", 512),
                "height": item.get("height", 512),
                "fallback_used": item.get("fallback_used", True),
            }
        )
    manifest: dict[str, Any] = {
        "manifest_version": "published_media_manifest.v0.1",
        "media_layer": "published_media",
        "published_media": published,
        "atlas": {
            "image": "/assets/atlases/published.webp",
            "descriptor": "/assets/atlases/published.json",
        },
    }
    out_path = run_dir / f"{node_id}__published_media_manifest.json"
    _write_json(out_path, manifest)
    ref = _make_ref(
        artifact_id=f"{node_id}__published_media_manifest",
        kind="published_media_manifest",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
        media_layer="published_media",
    )
    return {"output_refs": {"default": ref}}


# ---------------------------------------------------------------------------
# World State Delta nodes (deterministic, no real LLM)
# ---------------------------------------------------------------------------


def _derive_delta_id(run_id: str, node_id: str, battle_result: dict[str, Any]) -> str:
    """Stable delta_id derived from run_id/node_id/battle_result — no random."""
    raw = f"{run_id}/{node_id}/{battle_result.get('winner', 'unknown')}/{battle_result.get('waves_survived', 0)}"
    return f"delta_{hashlib.sha256(raw.encode()).hexdigest()[:12]}"


def node_world_state_build_delta_from_narrative_stub(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    """Deterministic mock: build a WorldStateDelta from battle_result +
    session_context + narrative artifacts (npc_feedback, world_growth).

    The delta is assembled from input fields, validated with
    validate_world_delta, and written as a world_state_delta.v0.1 artifact.
    No real LLM is called. No provider/model/raw_prompt/trace terms leak into
    the output.
    """
    run_world_state = _load_artifact(inputs, "run_world_state")
    battle_result = _load_artifact(inputs, "battle_result")
    session_context = _load_artifact(inputs, "session_context")
    npc_feedback = _load_artifact(inputs, "npc_feedback") if inputs.get("npc_feedback") else None
    world_growth = _load_artifact(inputs, "world_growth") if inputs.get("world_growth") else None

    run_id = run_world_state.get("run_id", "run_unknown")
    worldbook_id = run_world_state.get("worldbook_id", "unknown")
    current_turn = run_world_state.get("progress", {}).get("turn", 1)
    winner = battle_result.get("winner", "player")
    core_damaged = bool(battle_result.get("core_damaged", False))
    enemies_leaked = int(battle_result.get("enemies_leaked", 0) or 0)
    waves_survived = int(battle_result.get("waves_survived", 0) or 0)
    sample_triggered = bool(battle_result.get("sample_triggered", False))
    node_id_battle = battle_result.get("node_id", session_context.get("node_id", "gray_lantern_station"))

    delta_id = _derive_delta_id(run_id, node_id, battle_result)
    created_turn = current_turn + 1

    # Build summary in world-in language
    if winner == "player":
        summary = "影潮被击退，驿站核心安全，灯匠记录下战斗数据。"
        if enemies_leaked > 0:
            summary = f"影潮被击退，但有 {enemies_leaked} 股漏过灯栏，驿站核心承受了压力。"
    else:
        summary = "影潮压过驿站，灯匠带着残余灯火撤离，长夜更浓了。"

    node_status = "secured" if winner == "player" else "contested"
    threat_level = 0 if winner == "player" else 2

    # Build operations
    operations: list[dict[str, Any]] = [
        {"op": "set_progress_phase", "phase": "post_first_defense"},
        {
            "op": "set_map_node_state",
            "node_id": node_id_battle,
            "patch": {
                "status": node_status,
                "threat_level": threat_level,
                "visibility": "visible",
                "available_actions": ["field_research", "rest", "talk_to_engineer"],
            },
        },
        {
            "op": "adjust_global_state",
            "field": "hope",
            "amount_delta": 0.08 if winner == "player" else -0.15,
        },
        {
            "op": "adjust_global_state",
            "field": "pressure",
            "amount_delta": -0.10 if winner == "player" else 0.20,
        },
        {
            "op": "update_npc_relationship",
            "npc_id": "engineer_001",
            "relationship_delta": {"trust": 0.08 if winner == "player" else -0.10},
        },
        {
            "op": "unlock_fact",
            "fact": {
                "fact_id": "engineer_lamp_calibration",
                "source": "first_battle",
                "visibility": "player_known",
                "summary": "工程师承认灯阵校准与玩家的现场判断一致。",
            },
        },
        {
            "op": "add_temporary_sample",
            "sample": {
                "sample_id": "sample_refraction_chard",
                "display_name": "焦黑的折射碎片",
                "source_delta_id": delta_id,
                "summary": "战后从灯座边缘拾得的碎片，表面有规则的灼烧纹路。",
            },
        },
        {
            "op": "append_event",
            "event": {
                "event_id": "first_battle_resolved",
                "turn": created_turn,
                "kind": "battle",
                "summary": "灰灯驿站首战告捷，夜雾暂退半步。" if winner == "player" else "灰灯驿站失守，夜雾涌入。",
            },
        },
        {
            "op": "set_flag",
            "flag": "tutorial_first_battle_completed",
            "value": True,
        },
    ]

    # Adjust resources: consume lamp_oil, gain iron_scrap
    operations.append({
        "op": "adjust_resource",
        "resource_id": "lamp_oil",
        "amount_delta": -3,
    })
    operations.append({
        "op": "adjust_resource",
        "resource_id": "iron_scrap",
        "amount_delta": 2,
    })

    delta: dict[str, Any] = {
        "schema_version": "world_state_delta.v0.1",
        "delta_id": delta_id,
        "run_id": run_id,
        "worldbook_id": worldbook_id,
        "source": "battle_result",
        "created_turn": created_turn,
        "summary": summary,
        "operations": operations,
    }

    # Validate delta before writing
    delta_errors: list[str] = []
    delta_errors.extend(v_wd.validate_with_jsonschema(delta))
    delta_errors.extend(v_wd.validate_world_delta(delta))
    seen: set[str] = set()
    deduped: list[str] = []
    for e in delta_errors:
        if e not in seen:
            seen.add(e)
            deduped.append(e)
    if deduped:
        raise NodeError(
            f"build_delta_from_narrative_stub produced invalid delta: "
            + "; ".join(deduped)
        )

    out_path = run_dir / f"{node_id}__world_state_delta.json"
    _write_json(out_path, delta)
    ref = _make_ref(
        artifact_id=f"{node_id}__world_state_delta",
        kind="world_state_delta",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
    )
    return {"output_refs": {"default": ref}}


def node_world_state_apply_delta(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    """Deterministic: apply a validated WorldStateDelta to a RunWorldState.

    Delegates to apply_world_delta.apply_delta and validates both input and
    output state. Raises NodeError on any failure so the workflow status
    becomes failed.
    """
    run_world_state = _load_artifact(inputs, "run_world_state")
    world_state_delta = _load_artifact(inputs, "world_state_delta")

    # Validate input state
    state_errors: list[str] = []
    state_errors.extend(v_rws.validate_with_jsonschema(run_world_state))
    state_errors.extend(v_rws.validate_run_world_state(run_world_state))
    seen: set[str] = set()
    deduped: list[str] = []
    for e in state_errors:
        if e not in seen:
            seen.add(e)
            deduped.append(e)
    if deduped:
        raise NodeError(
            f"apply_delta: input RunWorldState invalid: " + "; ".join(deduped)
        )

    # Validate input delta
    delta_errors: list[str] = []
    delta_errors.extend(v_wd.validate_with_jsonschema(world_state_delta))
    delta_errors.extend(v_wd.validate_world_delta(world_state_delta))
    seen2: set[str] = set()
    deduped2: list[str] = []
    for e in delta_errors:
        if e not in seen2:
            seen2.add(e)
            deduped2.append(e)
    if deduped2:
        raise NodeError(
            f"apply_delta: input WorldStateDelta invalid: " + "; ".join(deduped2)
        )

    # Check run_id / worldbook_id consistency
    if world_state_delta.get("run_id") != run_world_state.get("run_id"):
        raise NodeError(
            f"apply_delta: delta.run_id ({world_state_delta.get('run_id')!r}) "
            f"does not match state.run_id ({run_world_state.get('run_id')!r})"
        )
    if world_state_delta.get("worldbook_id") != run_world_state.get("worldbook_id"):
        raise NodeError(
            f"apply_delta: delta.worldbook_id ({world_state_delta.get('worldbook_id')!r}) "
            f"does not match state.worldbook_id ({run_world_state.get('worldbook_id')!r})"
        )

    # Apply
    next_state, apply_errors = a_wd.apply_delta(run_world_state, world_state_delta)
    if apply_errors:
        raise NodeError(
            f"apply_delta: errors while applying operations: " + "; ".join(apply_errors)
        )

    # Validate next state
    next_errors: list[str] = []
    next_errors.extend(v_rws.validate_with_jsonschema(next_state))
    next_errors.extend(v_rws.validate_run_world_state(next_state))
    seen3: set[str] = set()
    deduped3: list[str] = []
    for e in next_errors:
        if e not in seen3:
            seen3.add(e)
            deduped3.append(e)
    if deduped3:
        raise NodeError(
            f"apply_delta: next RunWorldState invalid after apply: "
            + "; ".join(deduped3)
        )

    out_path = run_dir / f"{node_id}__run_world_state.json"
    _write_json(out_path, next_state)
    ref = _make_ref(
        artifact_id=f"{node_id}__run_world_state",
        kind="run_world_state",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
    )
    return {"output_refs": {"default": ref}}


# ---------------------------------------------------------------------------
# Guarded LLM AssetCompile node (live only, calls provider)
# ---------------------------------------------------------------------------


def node_asset_compile_with_llm_guarded(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    """Call an LLM to generate a CompiledAssetCandidate, guarded by validation.

    This node only works in live mode with allow_live_provider_call=true.
    It calls the configured provider, extracts JSON, validates with
    validate_asset_candidate, and writes the validated candidate.
    Internal provenance may record provider/model, but raw prompts, raw
    provider responses, API keys, and secrets are never written to the output.
    """
    proposal = _load_artifact(inputs, "proposal")

    allow_live = params.get("allow_live_provider_call", False)
    if not allow_live:
        raise NodeError(
            "asset.compile_with_llm_guarded requires "
            "params.allow_live_provider_call=true to call a real LLM provider. "
            "Set it to true only when you explicitly intend to make a live API call."
        )

    provider_profile = str(params.get("provider_profile", "ark_deepseek_v4_flash"))
    max_tokens = int(params.get("max_tokens", 8192))
    request_timeout = int(params.get("request_timeout", 120))

    if provider_profile not in llm_adapter.PROFILES:
        raise NodeError(
            f"unknown provider_profile={provider_profile!r}; "
            f"known: {sorted(llm_adapter.PROFILES)}"
        )

    profile = llm_adapter.PROFILES[provider_profile]
    llm_adapter.load_dotenv(ROOT / ".env")

    # Optional registry input; default to the shared effect blocks registry.
    if "registry" in inputs and inputs["registry"] is not None:
        registry = _load_artifact(inputs, "registry")
    else:
        registry = json.loads(DEFAULT_REGISTRY_PATH.read_text(encoding="utf-8"))

    user_prompt = asset_candidate_prompt.build_user_prompt(proposal, registry)

    messages = [
        {"role": "system", "content": asset_candidate_prompt.SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    try:
        response_format = (
            {"type": "json_object"} if profile.supports_json_object else None
        )
        response = llm_adapter.chat_completion(
            profile,
            messages,
            max_tokens=max_tokens,
            timeout=request_timeout,
            response_format=response_format,
        )
    except Exception as exc:
        raise NodeError(f"LLM provider call failed: {exc}") from exc

    raw_text = llm_adapter.extract_content_from_response(response)
    candidate = llm_adapter.extract_json(raw_text)

    if candidate is None:
        raise NodeError(
            "failed to extract JSON from LLM provider response"
        )

    candidate = asset_candidate_prompt.normalize_candidate_provenance(
        candidate,
        proposal,
        provider=profile.name,
        model=profile.model,
    )

    # Validate candidate
    errs = validate_asset_candidate.validate(candidate, registry)
    if errs:
        raise NodeError(
            "LLM-produced CompiledAssetCandidate validation failed: "
            + "; ".join(errs)
        )

    out_path = run_dir / f"{node_id}__compiled_asset_candidate.json"
    _write_json(out_path, candidate)
    ref = _make_ref(
        artifact_id=f"{node_id}__compiled_asset_candidate",
        kind="compiled_asset_candidate",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
    )
    return {"output_refs": {"default": ref}}


# ---------------------------------------------------------------------------
# Guarded LLM WorldStateDelta node (live only, calls provider)
# ---------------------------------------------------------------------------


def node_world_state_build_delta_with_llm_guarded(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    """Call an LLM to generate a WorldStateDelta, guarded by validation.

    This node only works in live mode with allow_live_provider_call=true.
    It calls the configured provider, extracts JSON, validates with
    jsonschema + world delta rules, and writes the validated delta.
    The output artifact never contains provider/model/raw_prompt terms.
    """
    run_world_state = _load_artifact(inputs, "run_world_state")
    battle_result = _load_artifact(inputs, "battle_result")
    session_context = _load_artifact(inputs, "session_context")

    allow_live = params.get("allow_live_provider_call", False)
    if not allow_live:
        raise NodeError(
            "world_state.build_delta_with_llm_guarded requires "
            "params.allow_live_provider_call=true to call a real LLM provider. "
            "Set it to true only when you explicitly intend to make a live API call."
        )

    provider_profile = str(params.get("provider_profile", "ark_deepseek_v4_flash"))
    max_tokens = int(params.get("max_tokens", 4096))
    request_timeout = int(params.get("request_timeout", 90))

    if provider_profile not in llm_adapter.PROFILES:
        raise NodeError(
            f"unknown provider_profile={provider_profile!r}; "
            f"known: {sorted(llm_adapter.PROFILES)}"
        )

    profile = llm_adapter.PROFILES[provider_profile]
    llm_adapter.load_dotenv(ROOT / ".env")

    user_prompt = world_delta_prompt.build_user_prompt(
        run_world_state, battle_result, session_context
    )

    messages = [
        {"role": "system", "content": world_delta_prompt.SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    try:
        response_format = (
            {"type": "json_object"} if profile.supports_json_object else None
        )
        response = llm_adapter.chat_completion(
            profile,
            messages,
            max_tokens=max_tokens,
            timeout=request_timeout,
            response_format=response_format,
        )
    except Exception as exc:
        raise NodeError(f"LLM provider call failed: {exc}") from exc

    raw_text = llm_adapter.extract_content_from_response(response)
    delta = llm_adapter.extract_json(raw_text)

    if delta is None:
        raise NodeError(
            "failed to extract JSON from LLM provider response"
        )

    # Validate delta
    delta_errors: list[str] = []
    delta_errors.extend(v_wd.validate_with_jsonschema(delta))
    delta_errors.extend(v_wd.validate_world_delta(delta))
    seen: set[str] = set()
    deduped: list[str] = []
    for e in delta_errors:
        if e not in seen:
            seen.add(e)
            deduped.append(e)
    if deduped:
        raise NodeError(
            "LLM-produced WorldStateDelta validation failed: "
            + "; ".join(deduped)
        )

    out_path = run_dir / f"{node_id}__world_state_delta.json"
    _write_json(out_path, delta)
    ref = _make_ref(
        artifact_id=f"{node_id}__world_state_delta",
        kind="world_state_delta",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
    )
    return {"output_refs": {"default": ref}}


# ---------------------------------------------------------------------------
# Guarded Live Image Media Generation node (live only, calls provider)
# ---------------------------------------------------------------------------


def node_media_generate_asset_images_guarded(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    """Call an image provider to generate icon/tower_sprite images for a
    CompiledAssetCandidate, guarded by the allow_live_provider_call flag.

    This node only works in live mode with allow_live_provider_call=true.
    It generates images for each configured role, downloads them to the run
    output directory, and writes a raw_media_sequence.v0.1 metadata artifact.
    The output artifact kind is media_metadata with media_layer=raw_media.
    """
    candidate = _load_artifact(inputs, "candidate")
    registry = json.loads(DEFAULT_REGISTRY_PATH.read_text(encoding="utf-8"))
    errs = validate_asset_candidate.validate(candidate, registry)
    if errs:
        raise NodeError(
            "media.generate_asset_images_guarded received invalid candidate: "
            + "; ".join(errs)
        )

    allow_live = params.get("allow_live_provider_call", False)
    if not allow_live:
        raise NodeError(
            "media.generate_asset_images_guarded requires "
            "params.allow_live_provider_call=true to call a real image provider. "
            "Set it to true only when you explicitly intend to make a live API call."
        )

    image_profile = str(params.get("image_profile", "agnes_image_flash"))
    size = str(params.get("size", "1024x1024"))
    roles = params.get("roles", ["icon", "tower_sprite"])
    request_timeout = int(params.get("request_timeout", 180))

    if not isinstance(roles, list) or not roles:
        raise NodeError("params.roles must be a non-empty list of role strings")
    allowed_roles = {"icon", "tower_sprite"}
    unknown_roles = [role for role in roles if role not in allowed_roles]
    if unknown_roles:
        raise NodeError(f"unknown media role(s): {unknown_roles}")

    profile = img_provider.PROFILES.get(image_profile)
    if profile is None:
        raise NodeError(
            f"unknown image_profile={image_profile!r}; "
            f"known: {sorted(img_provider.PROFILES)}"
        )

    try:
        width, height = img_provider.parse_size(size)
    except ValueError as exc:
        raise NodeError(str(exc)) from exc

    img_provider.load_dotenv(ROOT / ".env")

    items: list[dict[str, Any]] = []
    for role in roles:
        if role == "icon":
            prompt = asset_media_prompt.build_icon_prompt(candidate)
        elif role == "tower_sprite":
            prompt = asset_media_prompt.build_tower_sprite_prompt(candidate)
        else:  # pragma: no cover - guarded above
            raise NodeError(f"unknown media role: {role!r}")

        prompt_summary = asset_media_prompt.build_prompt_summary(candidate, role)

        try:
            response = img_provider.generate_image(profile, prompt, size=size, timeout=request_timeout)
        except Exception as exc:
            raise NodeError(f"image generation failed for role={role!r}: {exc}") from exc

        try:
            image_url = img_provider.extract_image_url(response)
        except RuntimeError as exc:
            raise NodeError(
                f"failed to extract image URL for role={role!r}: {exc}"
            ) from exc

        stable_id = asset_media_prompt.stable_media_id(candidate, role)
        local_filename = f"{stable_id}.png"
        local_path = run_dir / local_filename
        try:
            img_provider.download_image(image_url, local_path, timeout=request_timeout)
        except Exception as exc:
            raise NodeError(
                f"failed to download image for role={role!r}: {exc}"
            ) from exc

        item = asset_media_prompt.build_raw_media_item(
            candidate,
            role,
            provider_profile=image_profile,
            model=profile.model,
            width=width,
            height=height,
            local_path=str(local_path),
            prompt_summary=prompt_summary,
        )
        items.append(item)

    if not items:
        raise NodeError("no media items were generated")

    sequence = asset_media_prompt.build_raw_media_sequence(candidate, items)
    out_path = run_dir / f"{node_id}__raw_media_sequence.json"
    _write_json(out_path, sequence)
    ref = _make_ref(
        artifact_id=f"{node_id}__raw_media_sequence",
        kind="media_metadata",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
        media_layer="raw_media",
    )
    return {"output_refs": {"default": ref}}


# Registry of node_type -> implementation function.
NODE_IMPLEMENTATIONS: dict[str, Any] = {
    "source.load_json": node_source_load_json,
    "proposal.validate": node_proposal_validate,
    "asset.mock_compile_proposal": node_asset_mock_compile_proposal,
    "asset.compile_with_llm_guarded": node_asset_compile_with_llm_guarded,
    "asset.validate_candidate": node_asset_validate_candidate,
    "asset.simulate_candidate": node_asset_simulate_candidate,
    "report.pipeline_summary": node_report_pipeline_summary,
    "runtime.build_package_stub": node_runtime_build_package_stub,
    "research.build_delivery_payload_stub": node_research_build_delivery_payload_stub,
    "media.publish_stub_manifest": node_media_publish_stub_manifest,
    "narrative.mock_npc_feedback": node_narrative_mock_npc_feedback,
    "narrative.mock_world_growth_event": node_narrative_mock_world_growth_event,
    "media.generate_asset_images_guarded": node_media_generate_asset_images_guarded,
    "media.remove_background_stub": node_media_remove_background_stub,
    "media.crop_and_pad_stub": node_media_crop_and_pad_stub,
    "media.normalize_canvas_stub": node_media_normalize_canvas_stub,
    "media.assign_anchor_stub": node_media_assign_anchor_stub,
    "media.pack_sprite_sheet_stub": node_media_pack_sprite_sheet_stub,
    "media.build_atlas_json_stub": node_media_build_atlas_json_stub,
    "world_state.build_delta_from_narrative_stub": node_world_state_build_delta_from_narrative_stub,
    "world_state.build_delta_with_llm_guarded": node_world_state_build_delta_with_llm_guarded,
    "world_state.apply_delta": node_world_state_apply_delta,
}
