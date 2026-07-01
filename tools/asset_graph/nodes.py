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
import shutil
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
import score_asset_candidate  # noqa: E402
import simulate_asset_candidate  # noqa: E402
import validate_asset_candidate  # noqa: E402
import validate_proposal  # noqa: E402
import asset_promotion_policy  # noqa: E402
import runtime_package as rp  # noqa: E402

WORLD_STATE_DIR = ROOT / "tools" / "world_state"
if str(WORLD_STATE_DIR) not in sys.path:
    sys.path.insert(0, str(WORLD_STATE_DIR))

import validate_run_world_state as v_rws  # noqa: E402
import validate_world_delta as v_wd  # noqa: E402
import validate_world_delta_semantics as v_wds  # noqa: E402
import apply_world_delta as a_wd  # noqa: E402

NARRATIVE_DIR = ROOT / "tools" / "narrative"
if str(NARRATIVE_DIR) not in sys.path:
    sys.path.insert(0, str(NARRATIVE_DIR))

import validate_narrative_bundle as v_nb  # noqa: E402

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
import media_review  # noqa: E402
import vision_review  # noqa: E402
import prompt_repair  # noqa: E402
import png_pipeline  # noqa: E402
import runtime_readiness  # noqa: E402


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
    for name in ("proposal_validation", "candidate_validation", "simulation", "candidate_score", "asset_promotion"):
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
            summary["simulation_focus"] = data.get("simulation_focus")
            summary["asset_type"] = data.get("asset_type")
            summary["utility_score"] = data.get("utility_score")
            summary["cost_efficiency"] = data.get("cost_efficiency")
            summary["estimated_dps"] = data.get("estimated_dps")
        if name == "candidate_score" and isinstance(data, dict):
            summary["total_score"] = data.get("total_score")
            summary["recommendation"] = data.get("recommendation")
            summary["score_reasons"] = data.get("reasons", [])
        if name == "asset_promotion" and isinstance(data, dict):
            summary["promotion_state"] = data.get("promotion_state")
            summary["playable"] = data.get("playable")
            summary["uses_fallback_media"] = data.get("uses_fallback_media")
            summary["promotion_actions"] = data.get("required_next_actions", [])
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


def node_asset_score_candidate(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    """Score a candidate using deterministic guardrails.

    Inputs are optional except candidate: validation/simulation/media_metadata
    improve the score fidelity, but the node can still produce a report while
    clearly marking missing dimensions.
    """
    candidate = _load_artifact(inputs, "candidate")
    validation = _load_artifact(inputs, "validation") if inputs.get("validation") else None
    simulation = _load_artifact(inputs, "simulation") if inputs.get("simulation") else None
    media_metadata = (
        _load_artifact(inputs, "media_metadata")
        if inputs.get("media_metadata")
        else None
    )
    report = score_asset_candidate.score_candidate(
        candidate,
        validation=validation,
        simulation=simulation,
        media_metadata=media_metadata,
    )
    out_path = run_dir / f"{node_id}__candidate_score.json"
    _write_json(out_path, report)
    ref = _make_ref(
        artifact_id=f"{node_id}__candidate_score",
        kind="candidate_score",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
    )
    return {"output_refs": {"default": ref}}


def node_asset_evaluate_promotion_policy(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    """Decide whether a compiled asset is deliverable to the player runtime."""
    candidate = _load_artifact(inputs, "candidate")
    validation = _load_artifact(inputs, "validation") if inputs.get("validation") else None
    simulation = _load_artifact(inputs, "simulation") if inputs.get("simulation") else None
    candidate_score = _load_artifact(inputs, "candidate_score") if inputs.get("candidate_score") else None
    runtime_readiness = (
        _load_artifact(inputs, "runtime_readiness")
        if inputs.get("runtime_readiness")
        else None
    )
    vision_review = (
        _load_artifact(inputs, "vision_review")
        if inputs.get("vision_review")
        else None
    )
    consistency_report = (
        _load_artifact(inputs, "consistency_report")
        if inputs.get("consistency_report")
        else None
    )
    report = asset_promotion_policy.evaluate_promotion(
        candidate,
        validation=validation,
        simulation=simulation,
        candidate_score=candidate_score,
        runtime_readiness=runtime_readiness,
        vision_review=vision_review,
        consistency_report=consistency_report,
    )
    out_path = run_dir / f"{node_id}__asset_promotion_report.json"
    _write_json(out_path, report)
    ref = _make_ref(
        artifact_id=f"{node_id}__asset_promotion_report",
        kind="asset_promotion_report",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
    )
    if report.get("promotion_state") == "failed" and params.get("fail_on_reject", True):
        raise NodeError(f"asset promotion failed: {report.get('blockers', [])}")
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
    # Legacy JSON-only publisher kept for old workflows that do not yet provide
    # local PNG files. New media workflows should use the PNG processing chain
    # ending in media.build_atlas_json_stub.
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


def _derive_bundle_id(run_id: str, node_id: str, battle_result: dict[str, Any]) -> str:
    raw = (
        f"{run_id}/{node_id}/{battle_result.get('node_id', 'unknown')}/"
        f"{battle_result.get('winner', 'unknown')}/{battle_result.get('waves_survived', 0)}"
    )
    return f"bundle_{hashlib.sha256(raw.encode()).hexdigest()[:12]}"


def _validate_controlled_narrative_bundle(bundle: dict[str, Any], node_id: str) -> None:
    errors = v_nb.validate_narrative_bundle(bundle)
    if errors:
        raise NodeError(
            f"controlled narrative bundle produced by {node_id!r} is invalid: "
            + "; ".join(errors[:8])
        )


def node_narrative_build_controlled_world_player_bundle(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    """Build a staged NarrativeEventBundle from battle/world context.

    This is a deterministic v0.1 builder used to prove the controlled shape:
    world_line + player_line share the same bundle and every node carries
    gameplay_purpose, gameplay_hooks, and proposed WorldStateDelta intent.
    It does not call a real LLM.
    """
    run_world_state = _load_artifact(inputs, "run_world_state")
    battle_result = _load_artifact(inputs, "battle_result")
    session_context = _load_artifact(inputs, "session_context")
    ctx = _narrative_context(battle_result, session_context)
    phrases = _narrative_outcome_phrases(battle_result)

    run_id = run_world_state.get("run_id", "run_unknown")
    worldbook_id = run_world_state.get("worldbook_id", ctx["worldbook_id"])
    current_turn = run_world_state.get("progress", {}).get("turn", 1)
    current_phase = run_world_state.get("progress", {}).get("phase", "first_defense")
    created_turn = current_turn + 1
    node_id_battle = battle_result.get("node_id", ctx["node_id"])
    sample_perf = battle_result.get("sample_performance", {})
    sample_name = sample_perf.get("display_name", "折光绊索")
    sample_ref = sample_perf.get("stable_internal_id", "sample_trap_7f3a")

    bundle_id = _derive_bundle_id(run_id, node_id, battle_result)
    proposed_delta_ref = f"delta_from_{bundle_id}"

    if battle_result.get("winner", "player") == "player":
        world_block = "夜雾退到路口之外，灰灯驿站的灯栏在风里重新排成一线。"
        route_block = "北侧旧路露出断续的光点，像是有人在更远处回应。"
    else:
        world_block = "灰灯驿站的灯栏被夜雾压低，只剩核心旁还有一圈余光。"
        route_block = "北侧旧路的光点变得混乱，像是在催促下一次救援。"

    sample_text = (
        f"{sample_name}能拖住影潮，但线圈烧得太快。"
        "下一件试作品需要更稳的引光材料。"
        if battle_result.get("sample_triggered", False)
        else "这一战主要依靠旧灯栏撑住。下一件试作品需要补上迟滞手段。"
    )

    bundle: dict[str, Any] = {
        "schema_version": "narrative_event_bundle.v0.1",
        "bundle_id": bundle_id,
        "run_id": run_id,
        "worldbook_id": worldbook_id,
        "source": "battle_result",
        "created_turn": created_turn,
        "stage": "act_1_gray_lantern_after_first_defense",
        "lane": "shared",
        "commit_policy": {
            "candidate_generation": "parallel_allowed",
            "commit_gate": "world_state_delta_required",
            "commit_order": "serial_by_created_turn",
        },
        "worldbook_base_mutation_allowed": False,
        "nodes": [
            {
                "node_id": "world_line_gray_lantern_recovered",
                "stage": "act_1_gray_lantern_after_first_defense",
                "phase": "post_first_defense",
                "lane": "world_line",
                "scope": "map",
                "trigger": {
                    "kind": "battle_result",
                    "ref": node_id_battle,
                    "summary": "灰灯驿站首战结束，灯栏仍在燃烧。",
                },
                "prerequisites": [f"phase_{current_phase}"],
                "visibility": "player_visible",
                "presentation": {
                    "scene_type": "map_event",
                    "title": "驿站灯栏回稳",
                    "blocks": [{"text": world_block}, {"text": route_block}],
                },
                "gameplay_purpose": [
                    "modify_map_node_state",
                    "advance_main_pressure",
                    "open_resource_route",
                ],
                "gameplay_hooks": [
                    {
                        "hook": "modify_map_node_state",
                        "target_ref": node_id_battle,
                        "summary": "把灰灯驿站推进到可整备状态。",
                    },
                    {
                        "hook": "open_resource_route",
                        "target_ref": "northern_road_crossing",
                        "summary": "让玩家下一步可侦察北侧路口。",
                    },
                ],
                "npc_refs": ["engineer_001", "scout_002"],
                "npc_introductions": [],
                "proposed_world_delta_ref": proposed_delta_ref,
                "proposed_delta_summary": {
                    "expected_operations": [
                        "set_map_node_state",
                        "adjust_global_state",
                        "append_event",
                    ],
                    "summary": "提交地图节点状态、希望与压力变化，并记录世界线事件。",
                },
            },
            {
                "node_id": "player_line_battle_feedback_workshop_need",
                "stage": "act_1_gray_lantern_after_first_defense",
                "phase": "post_first_defense",
                "lane": "player_line",
                "scope": "workshop",
                "trigger": {
                    "kind": "battle_result",
                    "ref": sample_ref,
                    "summary": f"{sample_name}在首战中留下可分析的战场痕迹。",
                },
                "prerequisites": [f"battle_{node_id_battle}_resolved"],
                "visibility": "player_visible",
                "presentation": {
                    "scene_type": "dialogue",
                    "title": "战后评审",
                    "blocks": [
                        {
                            "speaker_id": "engineer_001",
                            "speaker_name": "灯匠",
                            "text": sample_text,
                        },
                        {
                            "text": "战场边缘留下几片焦黑的折射碎片，仍能折出细小的白光。",
                        },
                    ],
                },
                "gameplay_purpose": [
                    "explain_battle_result",
                    "create_research_need",
                    "offer_workshop_hook",
                    "introduce_material",
                ],
                "gameplay_hooks": [
                    {
                        "hook": "explain_battle_result",
                        "target_ref": sample_ref,
                        "summary": "解释试作品有效但需要改进。",
                    },
                    {
                        "hook": "offer_workshop_hook",
                        "target_ref": "field_research",
                        "summary": "引导玩家回到现场研发，尝试改进下一件样品。",
                    },
                    {
                        "hook": "introduce_material",
                        "target_ref": "sample_refraction_chard",
                        "summary": "把战场遗留物转成可被研发流程引用的临时样品。",
                    },
                ],
                "npc_refs": ["engineer_001"],
                "npc_introductions": [],
                "proposed_world_delta_ref": proposed_delta_ref,
                "proposed_delta_summary": {
                    "expected_operations": [
                        "add_temporary_sample",
                        "unlock_fact",
                        "update_npc_relationship",
                        "append_event",
                    ],
                    "summary": "提交临时样品、研发线索、NPC 信任变化与玩家线事件。",
                },
            },
            {
                "node_id": "shared_line_functional_npc_candidate",
                "stage": "act_1_gray_lantern_after_first_defense",
                "phase": "post_first_defense",
                "lane": "shared",
                "scope": "npc",
                "trigger": {
                    "kind": "world_tick",
                    "ref": "northern_road_crossing",
                    "summary": "北侧路口的光点在首战后变得稳定。",
                },
                "prerequisites": [f"{node_id_battle}_secured_or_contested"],
                "visibility": "hinted",
                "presentation": {
                    "scene_type": "map_event",
                    "title": "北路回光",
                    "blocks": [
                        {
                            "text": "侦察员在北侧路口看到一盏小灯，对方熟悉废旧线缆和临时支架。",
                        }
                    ],
                },
                "gameplay_purpose": [
                    "introduce_functional_npc",
                    "create_quest_hook",
                    "offer_workshop_hook",
                ],
                "gameplay_hooks": [
                    {
                        "hook": "introduce_functional_npc",
                        "target_ref": "npc_wire_mender_003",
                        "summary": "引入可影响现场研发的功能 NPC 候选。",
                    },
                    {
                        "hook": "create_quest_hook",
                        "target_ref": "quest_follow_northern_light",
                        "summary": "为后续路口侦察或救援任务留下入口。",
                    },
                ],
                "npc_refs": ["scout_002"],
                "npc_introductions": [
                    {
                        "npc_id": "npc_wire_mender_003",
                        "npc_kind": "functional",
                        "display_name": "补线人",
                        "narrative_roles": ["road_contact", "survivor"],
                        "gameplay_roles": ["research_review", "material_discount"],
                        "introduction_status": "candidate_only",
                    }
                ],
                "proposed_world_delta_ref": proposed_delta_ref,
                "proposed_delta_summary": {
                    "expected_operations": ["unlock_fact", "append_event", "set_flag"],
                    "summary": "只提交候选 NPC 的线索和任务入口，不直接把新 NPC 写入当前状态。",
                },
            },
        ],
    }

    _apply_narrative_test_inject(bundle, params)
    _enforce_narrative_safe(bundle, node_id)
    _validate_controlled_narrative_bundle(bundle, node_id)

    out_path = run_dir / f"{node_id}__narrative_event_bundle.json"
    _write_json(out_path, bundle)
    ref = _make_ref(
        artifact_id=f"{node_id}__narrative_event_bundle",
        kind="narrative_event_bundle",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
    )
    return {"output_refs": {"default": ref}}


# ---------------------------------------------------------------------------
# Media processing nodes
# ---------------------------------------------------------------------------


def _media_metadata(layer: str, items: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "metadata_version": "media_metadata.v0.1",
        "media_layer": layer,
        "items": items,
    }
    meta.update(extra)
    return meta


def _processed_media_item(
    item: dict[str, Any],
    local_path: Path,
    image: png_pipeline.PngImage,
    *,
    step_name: str,
) -> dict[str, Any]:
    new_item = {k: v for k, v in item.items() if k != "source_layer"}
    new_item["media_layer"] = "processed_media"
    new_item["local_path"] = str(local_path)
    new_item["width"] = image.width
    new_item["height"] = image.height
    new_item["detected_format"] = "png"
    steps = list(new_item.get("processing_steps", []))
    steps.append(step_name)
    new_item["processing_steps"] = steps
    return new_item


def _default_anchor_for_role(role: str) -> dict[str, Any]:
    if role in {"tower_sprite", "unit_sprite", "npc_sprite", "monster_sprite", "subject_sprite", "cutout_source"}:
        return {"preset": "bottom_center", "x": 0.5, "y": 1.0}
    return {"preset": "center", "x": 0.5, "y": 0.5}


def node_media_remove_background_stub(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    meta = _load_artifact(inputs, "media_metadata")
    if meta.get("media_layer") != "raw_media":
        raise NodeError("remove_background expected media_layer='raw_media'")
    threshold = int(params.get("threshold", 28))
    items_out: list[dict[str, Any]] = []
    for item in meta.get("items", []):
        if not isinstance(item, dict):
            continue
        local_path = item.get("local_path")
        if not isinstance(local_path, str) or not local_path:
            raise NodeError(f"media item {item.get('stable_internal_id')} has no local_path")
        src_path = Path(local_path)
        if not src_path.exists():
            raise NodeError(f"media file not found: {src_path}")
        try:
            image = png_pipeline.read_png(src_path)
            processed = png_pipeline.remove_matte_background(image, threshold=threshold)
        except ValueError as exc:
            raise NodeError(f"remove_background supports PNG only: {src_path}: {exc}") from exc
        stable_id = str(item.get("stable_internal_id", "media_unknown"))
        out_path = run_dir / f"{node_id}__{stable_id}.png"
        png_pipeline.write_png(out_path, processed)
        new_item = _processed_media_item(item, out_path, processed, step_name="remove_background")
        new_item["background_removed"] = True
        new_item["background_threshold"] = threshold
        items_out.append(new_item)
    out_meta = _media_metadata("processed_media", items_out)
    out_path = run_dir / f"{node_id}__media_remove_background.json"
    _write_json(out_path, out_meta)
    ref = _make_ref(
        artifact_id=f"{node_id}__media_metadata",
        kind="media_metadata",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
        media_layer="processed_media",
    )
    return {"output_refs": {"default": ref}}


def node_media_build_visual_identity_spec(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    candidate = _load_artifact(inputs, "candidate")
    spec = media_review.build_visual_identity_spec(candidate)
    out_path = run_dir / f"{node_id}__visual_identity_spec.json"
    _write_json(out_path, spec)
    ref = _make_ref(
        artifact_id=f"{node_id}__visual_identity_spec",
        kind="visual_identity_spec",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
    )
    return {"output_refs": {"default": ref}}


def node_media_check_quality(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    candidate = _load_artifact(inputs, "candidate")
    media_metadata = _load_artifact(inputs, "media_metadata")
    report = media_review.assess_media_quality(candidate, media_metadata)
    out_path = run_dir / f"{node_id}__media_quality_report.json"
    _write_json(out_path, report)
    ref = _make_ref(
        artifact_id=f"{node_id}__media_quality_report",
        kind="media_quality_report",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
    )
    return {"output_refs": {"default": ref}}


def node_media_check_consistency(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    candidate = _load_artifact(inputs, "candidate")
    media_metadata = _load_artifact(inputs, "media_metadata")
    visual_identity = _load_artifact(inputs, "visual_identity")
    quality_report = (
        _load_artifact(inputs, "quality_report")
        if inputs.get("quality_report")
        else None
    )
    report = media_review.assess_media_consistency(
        candidate,
        media_metadata,
        visual_identity,
        quality_report=quality_report,
    )
    out_path = run_dir / f"{node_id}__media_consistency_report.json"
    _write_json(out_path, report)
    ref = _make_ref(
        artifact_id=f"{node_id}__media_consistency_report",
        kind="media_consistency_report",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
    )
    return {"output_refs": {"default": ref}}


def node_media_review_with_vision_guarded(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    """Call a vision model to review local raw media images.

    This node is live-only and requires allow_live_provider_call=true. It sends
    local generated image files plus compact identity context to a multimodal
    model, then stores only a normalized MediaVisionReviewReport.
    """
    allow_live = params.get("allow_live_provider_call", False)
    if not allow_live:
        raise NodeError(
            "media.review_with_vision_guarded requires "
            "params.allow_live_provider_call=true to call a real vision provider."
        )

    candidate = _load_artifact(inputs, "candidate")
    media_metadata = _load_artifact(inputs, "media_metadata")
    visual_identity = _load_artifact(inputs, "visual_identity")
    quality_report = (
        _load_artifact(inputs, "quality_report")
        if inputs.get("quality_report")
        else None
    )
    consistency_report = (
        _load_artifact(inputs, "consistency_report")
        if inputs.get("consistency_report")
        else None
    )

    profile_name = str(params.get("vision_profile", "glm_5v_turbo"))
    max_images = int(params.get("max_images", 4))
    max_tokens = int(params.get("max_tokens", 4096))
    request_timeout = int(params.get("request_timeout", 180))

    vision_review.load_dotenv(ROOT / ".env")
    try:
        report = vision_review.review_media_with_vision(
            candidate,
            media_metadata,
            visual_identity,
            quality_report=quality_report if isinstance(quality_report, dict) else None,
            consistency_report=consistency_report if isinstance(consistency_report, dict) else None,
            profile_name=profile_name,
            max_images=max_images,
            max_tokens=max_tokens,
            timeout=request_timeout,
        )
    except Exception as exc:
        raise NodeError(f"vision media review failed: {exc}") from exc

    out_path = run_dir / f"{node_id}__media_vision_review_report.json"
    _write_json(out_path, report)
    ref = _make_ref(
        artifact_id=f"{node_id}__media_vision_review_report",
        kind="media_vision_review_report",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
    )
    return {"output_refs": {"default": ref}}


def node_media_build_prompt_repair_plan(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    """Build a deterministic prompt repair plan from review reports."""
    candidate = _load_artifact(inputs, "candidate")
    visual_identity = _load_artifact(inputs, "visual_identity")
    quality_report = (
        _load_artifact(inputs, "quality_report")
        if inputs.get("quality_report")
        else None
    )
    consistency_report = (
        _load_artifact(inputs, "consistency_report")
        if inputs.get("consistency_report")
        else None
    )
    vision_review_report = (
        _load_artifact(inputs, "vision_review_report")
        if inputs.get("vision_review_report")
        else None
    )
    plan = prompt_repair.build_prompt_repair_plan(
        candidate,
        visual_identity,
        quality_report=quality_report if isinstance(quality_report, dict) else None,
        consistency_report=consistency_report if isinstance(consistency_report, dict) else None,
        vision_review_report=vision_review_report if isinstance(vision_review_report, dict) else None,
    )
    out_path = run_dir / f"{node_id}__media_prompt_repair_plan.json"
    _write_json(out_path, plan)
    ref = _make_ref(
        artifact_id=f"{node_id}__media_prompt_repair_plan",
        kind="media_prompt_repair_plan",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
    )
    return {"output_refs": {"default": ref}}


def node_media_merge_repaired_sequence(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    """Merge original raw media with regenerated repair media by role."""
    original = _load_artifact(inputs, "original_media_metadata")
    repair = _load_artifact(inputs, "repair_media_metadata")
    repair_plan = _load_artifact(inputs, "repair_plan")
    if original.get("media_layer") != "raw_media":
        raise NodeError("original_media_metadata must have media_layer='raw_media'")
    if repair.get("media_layer") != "raw_media":
        raise NodeError("repair_media_metadata must have media_layer='raw_media'")
    target_roles = set(asset_media_prompt.target_roles_from_repair_plan(repair_plan))
    if not target_roles:
        merged_items: list[dict[str, Any]] = []
        for item in original.get("items", []):
            if not isinstance(item, dict):
                continue
            new_item = dict(item)
            steps = list(new_item.get("processing_steps", []))
            steps.append("repair_noop_reused")
            new_item["processing_steps"] = steps
            merged_items.append(new_item)
        merged = {
            "metadata_version": "raw_media_sequence.v0.1",
            "media_layer": "raw_media",
            "items": merged_items,
            "repair_merge": {
                "target_roles": [],
                "reused_roles": sorted(
                    {
                        str(item.get("media_role"))
                        for item in merged_items
                        if item.get("media_role")
                    }
                ),
                "replaced_roles": [],
                "source_plan": repair_plan.get("plan_version"),
            },
        }
        out_path = run_dir / f"{node_id}__raw_media_sequence.json"
        _write_json(out_path, merged)
        ref = _make_ref(
            artifact_id=f"{node_id}__raw_media_sequence",
            kind="media_metadata",
            path=out_path,
            run_dir=run_dir,
            produced_by_node=node_id,
            media_layer="raw_media",
        )
        return {"output_refs": {"default": ref}}

    repair_items_by_role: dict[str, dict[str, Any]] = {}
    for item in repair.get("items", []):
        if not isinstance(item, dict):
            continue
        role = str(item.get("media_role", ""))
        if role in target_roles:
            new_item = dict(item)
            steps = list(new_item.get("processing_steps", []))
            steps.append("repair_regenerated")
            new_item["processing_steps"] = steps
            repair_items_by_role[role] = new_item

    missing_repairs = sorted(target_roles - set(repair_items_by_role))
    if missing_repairs:
        raise NodeError(f"repair media missing target role(s): {missing_repairs}")

    merged_items: list[dict[str, Any]] = []
    kept_roles: set[str] = set()
    replaced_roles: set[str] = set()
    for item in original.get("items", []):
        if not isinstance(item, dict):
            continue
        role = str(item.get("media_role", ""))
        if role in target_roles:
            merged_items.append(repair_items_by_role[role])
            replaced_roles.add(role)
        else:
            new_item = dict(item)
            steps = list(new_item.get("processing_steps", []))
            steps.append("repair_reused")
            new_item["processing_steps"] = steps
            merged_items.append(new_item)
            kept_roles.add(role)

    for role in sorted(target_roles - replaced_roles):
        merged_items.append(repair_items_by_role[role])
        replaced_roles.add(role)

    merged = {
        "metadata_version": "raw_media_sequence.v0.1",
        "media_layer": "raw_media",
        "items": merged_items,
        "repair_merge": {
            "target_roles": sorted(target_roles),
            "reused_roles": sorted(kept_roles),
            "replaced_roles": sorted(replaced_roles),
            "source_plan": repair_plan.get("plan_version"),
        },
    }
    out_path = run_dir / f"{node_id}__raw_media_sequence.json"
    _write_json(out_path, merged)
    ref = _make_ref(
        artifact_id=f"{node_id}__raw_media_sequence",
        kind="media_metadata",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
        media_layer="raw_media",
    )
    return {"output_refs": {"default": ref}}


def node_media_crop_and_pad_stub(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    meta = _load_artifact(inputs, "media_metadata")
    if meta.get("media_layer") != "processed_media":
        raise NodeError("crop_and_pad expected media_layer='processed_media'")
    padding = int(params.get("padding", 24))
    alpha_threshold = int(params.get("alpha_threshold", 8))
    items_out: list[dict[str, Any]] = []
    for item in meta.get("items", []):
        if not isinstance(item, dict):
            continue
        src_path = Path(str(item.get("local_path", "")))
        if not src_path.exists():
            raise NodeError(f"media file not found: {src_path}")
        image = png_pipeline.read_png(src_path)
        cropped = png_pipeline.crop_and_pad(
            image,
            padding=padding,
            alpha_threshold=alpha_threshold,
        )
        stable_id = str(item.get("stable_internal_id", "media_unknown"))
        out_path = run_dir / f"{node_id}__{stable_id}.png"
        png_pipeline.write_png(out_path, cropped)
        new_item = _processed_media_item(item, out_path, cropped, step_name="crop_and_pad")
        new_item["crop_padding"] = padding
        items_out.append(new_item)
    out_meta = _media_metadata("processed_media", items_out)
    out_path = run_dir / f"{node_id}__media_crop_and_pad.json"
    _write_json(out_path, out_meta)
    ref = _make_ref(
        artifact_id=f"{node_id}__media_metadata",
        kind="media_metadata",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
        media_layer="processed_media",
    )
    return {"output_refs": {"default": ref}}


def node_media_normalize_canvas_stub(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    meta = _load_artifact(inputs, "media_metadata")
    if meta.get("media_layer") != "processed_media":
        raise NodeError("normalize_canvas expected media_layer='processed_media'")
    square = bool(params.get("square", True))
    min_size = int(params.get("min_size", 1))
    bottom_padding = int(params.get("bottom_padding", 0))
    items_out: list[dict[str, Any]] = []
    for item in meta.get("items", []):
        if not isinstance(item, dict):
            continue
        src_path = Path(str(item.get("local_path", "")))
        if not src_path.exists():
            raise NodeError(f"media file not found: {src_path}")
        image = png_pipeline.read_png(src_path)
        role = str(item.get("media_role", "unknown"))
        anchor = item.get("anchor") if isinstance(item.get("anchor"), dict) else _default_anchor_for_role(role)
        align = "bottom_center" if anchor.get("preset") == "bottom_center" else "center"
        normalized = png_pipeline.normalize_canvas(
            image,
            square=square,
            min_size=min_size,
            align=align,
            bottom_padding=bottom_padding,
        )
        stable_id = str(item.get("stable_internal_id", "media_unknown"))
        out_path = run_dir / f"{node_id}__{stable_id}.png"
        png_pipeline.write_png(out_path, normalized)
        new_item = _processed_media_item(item, out_path, normalized, step_name="normalize_canvas")
        new_item["canvas_normalized"] = {"square": square, "min_size": min_size, "align": align}
        items_out.append(new_item)
    out_meta = _media_metadata("processed_media", items_out)
    out_path = run_dir / f"{node_id}__media_normalize_canvas.json"
    _write_json(out_path, out_meta)
    ref = _make_ref(
        artifact_id=f"{node_id}__media_metadata",
        kind="media_metadata",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
        media_layer="processed_media",
    )
    return {"output_refs": {"default": ref}}


def node_media_assign_anchor_stub(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    meta = _load_artifact(inputs, "media_metadata")
    if meta.get("media_layer") != "processed_media":
        raise NodeError("assign_anchor expected media_layer='processed_media'")
    items_out: list[dict[str, Any]] = []
    for item in meta.get("items", []):
        if not isinstance(item, dict):
            continue
        role = str(item.get("media_role", "unknown"))
        anchor = _default_anchor_for_role(role)
        width = int(item.get("width", 1))
        height = int(item.get("height", 1))
        anchor["pixel_x"] = round(anchor["x"] * width, 3)
        anchor["pixel_y"] = round(anchor["y"] * height, 3)
        new_item = dict(item)
        new_item["anchor"] = anchor
        steps = list(new_item.get("processing_steps", []))
        steps.append("assign_anchor")
        new_item["processing_steps"] = steps
        items_out.append(new_item)
    out_meta = _media_metadata("processed_media", items_out)
    out_path = run_dir / f"{node_id}__media_assign_anchor.json"
    _write_json(out_path, out_meta)
    ref = _make_ref(
        artifact_id=f"{node_id}__media_metadata",
        kind="media_metadata",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
        media_layer="processed_media",
    )
    return {"output_refs": {"default": ref}}


def node_media_pack_sprite_sheet_stub(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    meta = _load_artifact(inputs, "media_metadata")
    if meta.get("media_layer") != "processed_media":
        raise NodeError("pack_sprite_sheet expected media_layer='processed_media'")
    pack_items: list[tuple[str, Path, dict[str, Any]]] = []
    for item in meta.get("items", []):
        if not isinstance(item, dict):
            continue
        stable_id = str(item.get("stable_internal_id", "media_unknown"))
        local_path = Path(str(item.get("local_path", "")))
        if not local_path.exists():
            raise NodeError(f"media file not found: {local_path}")
        pack_items.append((stable_id, local_path, item))
    atlas, descriptor = png_pipeline.pack_horizontal(pack_items)
    atlas_path = run_dir / f"{node_id}__atlas.png"
    descriptor_path = run_dir / f"{node_id}__atlas.json"
    png_pipeline.write_png(atlas_path, atlas)
    png_pipeline.write_json(descriptor_path, descriptor)
    items_out: list[dict[str, Any]] = []
    for item in meta.get("items", []):
        if not isinstance(item, dict):
            continue
        stable_id = str(item.get("stable_internal_id", "media_unknown"))
        new_item = dict(item)
        new_item["texture_key"] = f"{node_id}__atlas"
        new_item["atlas_local_path"] = str(atlas_path)
        new_item["atlas_json_local_path"] = str(descriptor_path)
        if stable_id in descriptor["frames"]:
            new_item["atlas_frame"] = descriptor["frames"][stable_id]["frame"]
        steps = list(new_item.get("processing_steps", []))
        steps.append("pack_sprite_sheet")
        new_item["processing_steps"] = steps
        items_out.append(new_item)
    out_meta = _media_metadata(
        "processed_media",
        items_out,
        atlas={
            "texture_key": f"{node_id}__atlas",
            "image_local_path": str(atlas_path),
            "descriptor_local_path": str(descriptor_path),
            "width": atlas.width,
            "height": atlas.height,
        },
    )
    out_path = run_dir / f"{node_id}__media_pack_sprite_sheet.json"
    _write_json(out_path, out_meta)
    ref = _make_ref(
        artifact_id=f"{node_id}__media_metadata",
        kind="media_metadata",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
        media_layer="processed_media",
    )
    return {"output_refs": {"default": ref}}


def node_media_build_atlas_json_stub(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    """Final publish step: processed_media -> published_media manifest.

    Copies processed PNGs plus atlas files into a local published directory and
    writes runtime-safe /assets/ URLs with hashes. No provider/raw fields leak.
    """
    meta = _load_artifact(inputs, "media_metadata")
    actual_layer = meta.get("media_layer") if isinstance(meta, dict) else None
    if actual_layer != "processed_media":
        raise NodeError(
            f"build_atlas_json expected media_layer='processed_media', "
            f"got {actual_layer!r}"
        )
    items_in = meta.get("items", []) if isinstance(meta, dict) else []
    published_dir = run_dir / "published"
    published_dir.mkdir(parents=True, exist_ok=True)

    atlas_info = meta.get("atlas") if isinstance(meta.get("atlas"), dict) else {}
    atlas_image_src = Path(str(atlas_info.get("image_local_path", ""))) if atlas_info else None
    atlas_json_src = Path(str(atlas_info.get("descriptor_local_path", ""))) if atlas_info else None
    if not atlas_image_src or not atlas_image_src.exists() or not atlas_json_src or not atlas_json_src.exists():
        pack_items: list[tuple[str, Path, dict[str, Any]]] = []
        for item in items_in:
            if not isinstance(item, dict):
                continue
            stable_id = str(item.get("stable_internal_id", "media_unknown"))
            local_path = Path(str(item.get("local_path", "")))
            if not local_path.exists():
                raise NodeError(f"media file not found: {local_path}")
            pack_items.append((stable_id, local_path, item))
        atlas_image, descriptor = png_pipeline.pack_horizontal(pack_items)
        atlas_image_src = run_dir / f"{node_id}__atlas.png"
        atlas_json_src = run_dir / f"{node_id}__atlas.json"
        png_pipeline.write_png(atlas_image_src, atlas_image)
        png_pipeline.write_json(atlas_json_src, descriptor)

    atlas_image_name = f"{node_id}__atlas.png"
    atlas_json_name = f"{node_id}__atlas.json"
    atlas_image_dst = published_dir / atlas_image_name
    atlas_json_dst = published_dir / atlas_json_name
    shutil.copyfile(atlas_image_src, atlas_image_dst)
    shutil.copyfile(atlas_json_src, atlas_json_dst)

    published: list[dict[str, Any]] = []
    for item in items_in:
        if not isinstance(item, dict):
            continue
        stable_id = str(item.get("stable_internal_id", "media_unknown"))
        local_path = Path(str(item.get("local_path", "")))
        if not local_path.exists():
            raise NodeError(f"media file not found: {local_path}")
        file_name = f"{stable_id}.png"
        file_dst = published_dir / file_name
        shutil.copyfile(local_path, file_dst)
        published.append(
            {
                "stable_internal_id": stable_id,
                "media_role": item.get("media_role", "unknown"),
                "media_layer": "published_media",
                "url": f"/assets/generated/{file_name}",
                "file": f"published/{file_name}",
                "width": item.get("width", 512),
                "height": item.get("height", 512),
                "fallback_used": item.get("fallback_used", True),
                "sha256": _sha256_file(file_dst),
                "anchor": item.get("anchor"),
                "texture_key": item.get("texture_key", f"{node_id}__atlas"),
                "atlas_frame": item.get("atlas_frame"),
            }
        )
    manifest: dict[str, Any] = {
        "manifest_version": "published_media_manifest.v0.1",
        "media_layer": "published_media",
        "published_media": published,
        "atlas": {
            "texture_key": atlas_info.get("texture_key", f"{node_id}__atlas") if isinstance(atlas_info, dict) else f"{node_id}__atlas",
            "image": f"/assets/generated/{atlas_image_name}",
            "descriptor": f"/assets/generated/{atlas_json_name}",
            "image_file": f"published/{atlas_image_name}",
            "descriptor_file": f"published/{atlas_json_name}",
            "image_sha256": _sha256_file(atlas_image_dst),
            "descriptor_sha256": _sha256_file(atlas_json_dst),
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


def node_media_check_runtime_readiness(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    """Check that published media is directly loadable by the game runtime."""
    manifest = _load_artifact(inputs, "published_media")
    ref = inputs.get("published_media")
    if not isinstance(ref, dict) or "path" not in ref:
        raise NodeError("published_media input must be an ArtifactRef")
    manifest_path = Path(str(ref["path"]))
    artifact_dir = manifest_path.parent
    report = runtime_readiness.assess_runtime_readiness(
        manifest,
        artifact_dir=artifact_dir,
        alpha_threshold=int(params.get("alpha_threshold", 8)),
        min_size=int(params.get("min_size", 16)),
        max_size=int(params.get("max_size", 1024)),
        min_subject_coverage=float(params.get("min_subject_coverage", 0.05)),
        max_subject_coverage=float(params.get("max_subject_coverage", 0.92)),
    )
    out_path = run_dir / f"{node_id}__media_runtime_readiness_report.json"
    _write_json(out_path, report)
    out_ref = _make_ref(
        artifact_id=f"{node_id}__media_runtime_readiness_report",
        kind="media_runtime_readiness_report",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
    )
    if report.get("status") == "failed":
        failed_items = [
            item.get("stable_internal_id")
            for item in report.get("items", [])
            if isinstance(item, dict) and item.get("status") == "failed"
        ]
        raise NodeError(
            "media runtime readiness failed"
            + (f": {failed_items}" if failed_items else "")
        )
    return {"output_refs": {"default": out_ref}}


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
    narrative_bundle = (
        _load_artifact(inputs, "narrative_bundle")
        if inputs.get("narrative_bundle")
        else None
    )
    if isinstance(narrative_bundle, dict):
        _validate_controlled_narrative_bundle(narrative_bundle, node_id)

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
    if isinstance(narrative_bundle, dict):
        summary = "战后记录已整理，世界局势与玩家行动后果将按顺序落地。"

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

    if isinstance(narrative_bundle, dict):
        for bundle_node in narrative_bundle.get("nodes", []):
            if not isinstance(bundle_node, dict):
                continue
            bundle_node_id = bundle_node.get("node_id", "narrative_node")
            title = bundle_node.get("presentation", {}).get("title", "战后事件")
            lane = bundle_node.get("lane", "shared")
            lane_label = {
                "world_line": "世界局势",
                "player_line": "玩家行动",
                "shared": "交汇线索",
            }.get(lane, "交汇线索")
            scope = bundle_node.get("scope", "world")
            event_kind = "story"
            if scope == "npc":
                event_kind = "npc"
            elif scope == "workshop":
                event_kind = "research"
            elif scope in {"world", "map"}:
                event_kind = "world"
            operations.append(
                {
                    "op": "append_event",
                        "event": {
                            "event_id": f"{bundle_node_id}_accepted",
                            "turn": created_turn,
                            "kind": event_kind,
                            "summary": f"{title}已进入{lane_label}推进序列。",
                        },
                    }
                )
            for npc in bundle_node.get("npc_introductions", []):
                if not isinstance(npc, dict):
                    continue
                npc_id = npc.get("npc_id", "npc_candidate")
                display_name = npc.get("display_name", "新来者")
                operations.append(
                    {
                        "op": "unlock_fact",
                        "fact": {
                            "fact_id": f"{npc_id}_hinted",
                            "source": "narrative_event",
                            "visibility": "hinted",
                            "summary": f"{display_name}的线索已出现，后续可通过任务确认其去向。",
                        },
                    }
                )
                operations.append(
                    {
                        "op": "set_flag",
                        "flag": f"{npc_id}_candidate_seen",
                        "value": True,
                    }
                )

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


def node_world_state_validate_delta_semantics(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    """Deterministic semantic gate before applying a WorldStateDelta.

    This node sits between any delta producer, including live LLM nodes, and
    world_state.apply_delta. It writes a validation report for traceability and
    forwards a copied delta only when semantic checks pass.
    """
    run_world_state = _load_artifact(inputs, "run_world_state")
    world_state_delta = _load_artifact(inputs, "world_state_delta")

    review_pack_raw = params.get(
        "review_pack",
        "examples/review_packs/mvp_story_asset_review_pack.v0.1.json",
    )
    if not isinstance(review_pack_raw, str) or not review_pack_raw:
        raise NodeError("validate_delta_semantics: params.review_pack must be a non-empty string")
    review_pack_path = Path(review_pack_raw)
    if not review_pack_path.is_absolute():
        review_pack_path = ROOT / review_pack_path

    state_errors: list[str] = []
    state_errors.extend(v_rws.validate_with_jsonschema(run_world_state))
    state_errors.extend(v_rws.validate_run_world_state(run_world_state))
    state_errors = list(dict.fromkeys(state_errors))

    delta_errors: list[str] = []
    delta_errors.extend(v_wd.validate_with_jsonschema(world_state_delta))
    delta_errors.extend(v_wd.validate_world_delta(world_state_delta))
    delta_errors = list(dict.fromkeys(delta_errors))

    semantic_errors: list[str] = []
    registry_counts: dict[str, int] = {}
    if not state_errors and not delta_errors:
        registry = v_wds.build_reference_registry(run_world_state, review_pack_path)
        semantic_errors = v_wds.validate_world_delta_semantics(
            world_state_delta, run_world_state, registry
        )
        registry_counts = {
            "run_map_nodes": len(registry.run_map_node_ids),
            "allowed_resources": len(registry.allowed_resource_ids),
            "allowed_npcs": len(registry.allowed_npc_ids),
        }

    errors = [*state_errors, *delta_errors, *semantic_errors]
    report = {
        "semantic_gate_version": "world_state_delta_semantic_gate.v0.1",
        "status": "passed" if not errors else "failed",
        "delta_id": world_state_delta.get("delta_id"),
        "run_id": world_state_delta.get("run_id"),
        "worldbook_id": world_state_delta.get("worldbook_id"),
        "review_pack": str(review_pack_path.relative_to(ROOT))
        if review_pack_path.is_relative_to(ROOT)
        else str(review_pack_path),
        "structure_errors": {
            "run_state": state_errors,
            "world_state_delta": delta_errors,
        },
        "semantic_errors": semantic_errors,
        "registry_counts": registry_counts,
    }
    report_path = run_dir / f"{node_id}__world_delta_semantic_gate_report.json"
    _write_json(report_path, report)
    report_ref = _make_ref(
        artifact_id=f"{node_id}__world_delta_semantic_gate_report",
        kind="semantic_validation_report",
        path=report_path,
        run_dir=run_dir,
        produced_by_node=node_id,
    )

    if errors and params.get("fail_on_error", True):
        raise NodeError(
            "world_state semantic gate failed: " + "; ".join(errors)
        )

    out_path = run_dir / f"{node_id}__world_state_delta.semantic_validated.json"
    _write_json(out_path, world_state_delta)
    delta_ref = _make_ref(
        artifact_id=f"{node_id}__world_state_delta_semantic_validated",
        kind="world_state_delta",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
    )
    delta_alias_ref = dict(delta_ref)
    delta_alias_ref["artifact_id"] = f"{node_id}__world_state_delta"
    return {
        "output_refs": {
            "default": delta_ref,
            "world_state_delta": delta_alias_ref,
            "validation_report": report_ref,
        }
    }


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
    max_tokens = int(params.get("max_tokens", 8192))
    request_timeout = int(params.get("request_timeout", 90))
    review_pack_path_raw = str(
        params.get(
            "review_pack_path",
            "examples/review_packs/mvp_story_asset_review_pack.v0.1.json",
        )
    )

    if provider_profile not in llm_adapter.PROFILES:
        raise NodeError(
            f"unknown provider_profile={provider_profile!r}; "
            f"known: {sorted(llm_adapter.PROFILES)}"
        )

    profile = llm_adapter.PROFILES[provider_profile]
    llm_adapter.load_dotenv(ROOT / ".env")

    review_pack_path = Path(review_pack_path_raw)
    if not review_pack_path.is_absolute():
        review_pack_path = ROOT / review_pack_path
    review_pack: dict[str, Any] | None = None
    if review_pack_path.is_file():
        try:
            loaded_review_pack = json.loads(review_pack_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise NodeError(f"review_pack_path is not valid JSON: {exc}") from exc
        if isinstance(loaded_review_pack, dict):
            review_pack = loaded_review_pack

    user_prompt = world_delta_prompt.build_user_prompt(
        run_world_state, battle_result, session_context, review_pack
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
    roles = params.get("roles", "auto")
    request_timeout = int(params.get("request_timeout", 180))
    repair_plan = (
        _load_artifact(inputs, "repair_plan")
        if inputs.get("repair_plan")
        else None
    )

    if roles == "auto":
        roles = asset_media_prompt.default_media_roles(candidate)
    elif roles == "repair_failed":
        if not isinstance(repair_plan, dict):
            raise NodeError("roles='repair_failed' requires input repair_plan")
        roles = asset_media_prompt.target_roles_from_repair_plan(repair_plan)
        if not roles:
            sequence = {
                "metadata_version": "raw_media_sequence.v0.1",
                "media_layer": "raw_media",
                "items": [],
                "repair_noop": {
                    "reason": "repair_plan has no target_roles",
                    "source_plan": repair_plan.get("plan_version"),
                },
            }
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
    if not isinstance(roles, list) or not roles:
        raise NodeError("params.roles must be 'auto' or a non-empty list of role strings")
    allowed_roles = asset_media_prompt.MEDIA_ROLES
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
        try:
            prompt = asset_media_prompt.build_prompt_for_role(
                candidate,
                role,
                repair_plan=repair_plan if isinstance(repair_plan, dict) else None,
            )
        except ValueError as exc:  # pragma: no cover - guarded above
            raise NodeError(str(exc)) from exc

        prompt_summary = asset_media_prompt.build_prompt_summary(candidate, role)
        if isinstance(repair_plan, dict) and asset_media_prompt.repair_suffix_for_role(repair_plan, role):
            prompt_summary = f"{prompt_summary}; repair_plan=applied"

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


# ---------------------------------------------------------------------------
# Free-input controlled compilation nodes
# ---------------------------------------------------------------------------

KNOWN_ATTACK_PATTERNS = frozenset(
    {
        "single_target",
        "cone_damage",
        "cone_damage_over_time",
        "area_burst",
        "beam",
        "chain",
        "aura",
        "projectile",
        "melee",
        "summon",
    }
)
KNOWN_CONTROL_EFFECTS = frozenset(
    {"pull_in", "push_back", "slow", "stun", "root", "fear", "taunt"}
)
KNOWN_GROWTH_MECHANICS = frozenset(
    {"gain_stack_on_kill", "gain_stack_on_hit", "charge_over_time", "absorb_enemy_stat"}
)
KNOWN_TARGETING = frozenset(
    {"nearest", "dense_area", "lowest_health", "highest_threat", "random", "last_on_path"}
)
ARCHETYPE_DISPLAY_NAMES = {
    "alchemy_furnace": "炼丹炉",
    "field_device": "野战装置",
}


def _effect_blocks_from_gameplay(gameplay: dict[str, Any]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    attack = gameplay.get("attack_pattern")
    control = gameplay.get("control_effect")
    growth = gameplay.get("growth_mechanic")

    if attack == "cone_damage_over_time":
        blocks.append(
            {
                "type": "damage_over_time",
                "params": {
                    "damage_per_tick": 15,
                    "tick_interval": 1.0,
                    "duration": 3.0,
                    "element": "purple_fire",
                },
            }
        )
    elif attack in {"cone_damage", "area_burst", "beam"}:
        blocks.append({"type": "area_damage", "params": {"damage": 30}})
    elif attack == "chain":
        blocks.append({"type": "pierce_or_chain", "params": {"jumps": 3}})
    elif attack == "summon":
        blocks.append({"type": "summon_unit", "params": {"duration": 8.0}})
    else:
        blocks.append({"type": "damage", "params": {"damage": 20}})

    if control == "pull_in":
        blocks.append(
            {
                "type": "aura_buff",
                "params": {"radius": 120, "effect": "pull_in", "strength": "medium"},
            }
        )
    elif control == "slow":
        blocks.append(
            {"type": "slow", "params": {"slow_ratio": 0.3, "duration": 2.0}}
        )

    if growth in {"gain_stack_on_kill", "gain_stack_on_hit", "charge_over_time"}:
        blocks.append(
            {
                "type": "charge_burst",
                "params": {
                    "stacks_on_kill": growth == "gain_stack_on_kill",
                    "max_stacks": 10,
                    "damage_bonus_per_stack": 0.05,
                },
            }
        )
    return blocks


def node_asset_legalize_design_spec(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    design_spec = _load_artifact(inputs, "design_spec")
    mode = params.get("legalization_mode", "runtime_safe")
    if mode not in {"runtime_safe", "runtime_experimental", "studio_mode"}:
        raise NodeError(f"unsupported legalization_mode: {mode!r}")

    theme = dict(design_spec.get("theme", {}))
    visual = dict(design_spec.get("visual", {}))
    gameplay = dict(design_spec.get("gameplay", {}))
    balance = dict(design_spec.get("balance", {}))
    world_fit = dict(design_spec.get("world_fit", {}))

    issues: list[dict[str, Any]] = []
    fixes: list[dict[str, Any]] = []
    unmapped: list[str] = []
    degraded_fields: list[str] = []
    proposal_new_effects: list[str] = []

    constraints = dict(visual.get("constraints", {}))
    media_defaults = {
        "single_subject": True,
        "clean_background": True,
        "no_enemy_in_sprite": True,
        "no_attack_effect_on_body_sprite": True,
    }
    for key, value in media_defaults.items():
        if key not in constraints:
            constraints[key] = value
            fixes.append(
                {
                    "action": "media_constraint_enforcement",
                    "description": f"Applied media constraint {key}.",
                    "field_path": f"visual.constraints.{key}",
                }
            )
    visual["constraints"] = constraints

    attack = gameplay.get("attack_pattern")
    if attack not in KNOWN_ATTACK_PATTERNS:
        unmapped.append(str(attack))
        gameplay["attack_pattern"] = "area_burst"
        degraded_fields.append("gameplay.attack_pattern")
        issues.append(
            {
                "type": "unknown_mechanism",
                "severity": "warning",
                "message": "Unknown attack pattern was mapped to area burst.",
                "field_path": "gameplay.attack_pattern",
                "original_value": attack,
                "resolved_value": "area_burst",
            }
        )

    control = gameplay.get("control_effect")
    if control and control not in KNOWN_CONTROL_EFFECTS:
        unmapped.append(str(control))
        proposal_new_effects.append(str(control))
        degraded_fields.append("gameplay.control_effect")
        gameplay.pop("control_effect", None)
        issues.append(
            {
                "type": "fallback_mapping",
                "severity": "warning",
                "message": "Unknown control effect was kept as a proposal-only idea.",
                "field_path": "gameplay.control_effect",
                "original_value": control,
                "resolved_value": None,
            }
        )

    growth = gameplay.get("growth_mechanic")
    if growth and growth not in KNOWN_GROWTH_MECHANICS:
        unmapped.append(str(growth))
        proposal_new_effects.append(str(growth))
        degraded_fields.append("gameplay.growth_mechanic")
        gameplay.pop("growth_mechanic", None)

    targeting = gameplay.get("targeting")
    if targeting not in KNOWN_TARGETING:
        gameplay["targeting"] = "nearest"
        fixes.append(
            {
                "action": "fallback_mapping",
                "description": "Unknown targeting was mapped to nearest.",
                "field_path": "gameplay.targeting",
            }
        )

    if (
        "area_damage" in gameplay.get("intended_role", [])
        and "soft_control" in gameplay.get("intended_role", [])
        and balance.get("cost_band") == "cheap"
        and balance.get("growth_cap") == "unlimited"
    ):
        balance["cost_band"] = "medium"
        balance["growth_cap"] = "limited"
        balance["budget_clamped"] = True
        issues.append(
            {
                "type": "budget_clamp",
                "severity": "warning",
                "message": "High damage, control, cheap cost, and unlimited growth exceeded runtime_safe budget.",
                "field_path": "balance",
                "original_value": "cheap/unlimited",
                "resolved_value": "medium/limited",
            }
        )
        fixes.append(
            {
                "action": "budget_clamp",
                "description": "Raised cost band and capped growth for runtime safety.",
                "field_path": "balance",
            }
        )

    if mode == "runtime_safe" and balance.get("growth_cap") == "unlimited":
        balance["growth_cap"] = "limited"
        balance["budget_clamped"] = True
        issues.append(
            {
                "type": "budget_clamp",
                "severity": "warning",
                "message": "Unlimited growth is capped in runtime_safe mode.",
                "field_path": "balance.growth_cap",
                "original_value": "unlimited",
                "resolved_value": "limited",
            }
        )
        fixes.append(
            {
                "action": "budget_clamp",
                "description": "Capped growth from unlimited to limited.",
                "field_path": "balance.growth_cap",
            }
        )

    if not gameplay.get("effect_blocks"):
        gameplay["effect_blocks"] = _effect_blocks_from_gameplay(gameplay)
        fixes.append(
            {
                "action": "field_completion",
                "description": "Populated effect blocks from legalized gameplay fields.",
                "field_path": "gameplay.effect_blocks",
            }
        )

    legalized = {
        "schema_version": "legalized_design_spec.v0.1",
        "asset_kind": design_spec.get("asset_kind", "tower_blueprint"),
        "legalization_mode": mode,
        "theme": theme,
        "visual": visual,
        "gameplay": gameplay,
        "balance": balance,
        "world_fit": world_fit,
        "media_constraints": constraints,
        "fallback_mapping": {
            "unmapped_mechanics": unmapped,
            "degraded_fields": degraded_fields,
            "proposal_new_effects": proposal_new_effects,
        },
    }
    report = {
        "schema_version": "legalization_report.v0.1",
        "legalization_mode": mode,
        "passed": not any(i.get("severity") == "error" for i in issues),
        "issues": issues,
        "applied_fixes": fixes,
        "fallback_summary": {
            "unmapped_mechanics": unmapped,
            "degraded_to_proposal": bool(proposal_new_effects),
            "stable_enough_for_compile": not proposal_new_effects,
        },
    }

    legalized_path = run_dir / f"{node_id}__legalized_design_spec.json"
    _write_json(legalized_path, legalized)
    legalized_ref = _make_ref(
        artifact_id=f"{node_id}__legalized_design_spec",
        kind="legalized_design_spec",
        path=legalized_path,
        run_dir=run_dir,
        produced_by_node=node_id,
    )
    report_path = run_dir / f"{node_id}__legalization_report.json"
    _write_json(report_path, report)
    report_ref = _make_ref(
        artifact_id=f"{node_id}__legalization_report",
        kind="legalization_report",
        path=report_path,
        run_dir=run_dir,
        produced_by_node=node_id,
    )
    return {"output_refs": {"default": legalized_ref, "report": report_ref}}


def node_asset_build_asset_plan(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    legalized = _load_artifact(inputs, "legalized_design_spec")
    gameplay = legalized.get("gameplay", {})
    visual = legalized.get("visual", {})
    theme = legalized.get("theme", {})
    balance = legalized.get("balance", {})

    cost_band = balance.get("cost_band", "medium")
    build_cost = {"cheap": 90, "medium": 150, "expensive": 220}.get(
        cost_band, 150
    )
    archetype = theme.get("archetype", "field_device")
    element = visual.get("core_element", "compiled_light")

    asset_plan = {
        "schema_version": "asset_plan.v0.1",
        "asset_kind": legalized.get("asset_kind", "tower_blueprint"),
        "gameplay": {
            "effect_blocks": gameplay.get("effect_blocks", []),
            "targeting": gameplay.get("targeting", "nearest"),
            "range": 150,
            "cooldown": 2.5 if cost_band == "expensive" else 1.8,
            "build_cost": build_cost,
            "growth_mechanic": gameplay.get("growth_mechanic", "none"),
        },
        "presentation": {
            "name": "炼丹炉" if archetype == "alchemy_furnace" else archetype,
            "short_description": "将玩家构想整理成可试作的防御设施。",
            "detailed_description": "该方案会先生成稳定的战斗规则，随后准备塔体、图标与特效素材。",
            "visual_style_ref": visual.get("style_id", "compiler_td_v1"),
        },
        "media_roles": {
            "tower_body": {
                "role": "tower_body",
                "required": True,
                "prompt_hint": f"isometric {archetype}, {element}, clean background, single subject",
                "fallback_strategy": "placeholder_sprite",
            },
            "tower_icon": {
                "role": "tower_icon",
                "required": True,
                "prompt_hint": f"2D game icon, {archetype}, clean silhouette",
                "fallback_strategy": "placeholder_sprite",
            },
            "attack_vfx": {
                "role": "attack_vfx",
                "required": True,
                "prompt_hint": f"{element} attack effect, transparent background",
                "fallback_strategy": "visual_recipe",
            },
            "impact_vfx": {
                "role": "impact_vfx",
                "required": False,
                "prompt_hint": f"{element} impact burst",
                "fallback_strategy": "visual_recipe",
            },
            "projectile": {
                "role": "projectile",
                "required": False,
                "prompt_hint": f"{element} projectile",
                "fallback_strategy": "visual_recipe",
            },
            "selection_ring": {
                "role": "selection_ring",
                "required": False,
                "prompt_hint": "",
                "fallback_strategy": "deterministic_shape",
            },
            "shadow": {
                "role": "shadow",
                "required": False,
                "prompt_hint": "",
                "fallback_strategy": "deterministic_shape",
            },
        },
        "runtime_metadata": {
            "anchor_point": "bottom_center",
            "footprint": {"width": 1, "height": 1},
            "collision_box": {"width": 0.8, "height": 0.8},
            "attack_socket": {"x": 0, "y": 0.5},
        },
        "fallback_plan": {
            "media_fallback_strategy": "placeholder_sprite",
            "gameplay_fallback_strategy": "skip_unregistered_effects",
            "can_degrade_to_proposal": False,
        },
    }

    out_path = run_dir / f"{node_id}__asset_plan.json"
    _write_json(out_path, asset_plan)
    ref = _make_ref(
        artifact_id=f"{node_id}__asset_plan",
        kind="asset_plan",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
    )
    return {"output_refs": {"default": ref}}


def node_proposal_build_from_legalized_spec(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    legalized = _load_artifact(inputs, "legalized_design_spec")
    asset_plan = _load_artifact(inputs, "asset_plan")
    run_world_state = None
    if inputs.get("run_world_state") is not None:
        try:
            run_world_state = _load_artifact(inputs, "run_world_state")
        except NodeError:
            run_world_state = None

    gameplay = legalized.get("gameplay", {})
    theme = legalized.get("theme", {})
    balance = legalized.get("balance", {})
    world_fit = legalized.get("world_fit", {})
    presentation = asset_plan.get("presentation", {})
    roles = gameplay.get("intended_role", [])
    archetype = theme.get("archetype", "field_device")
    archetype_display = ARCHETYPE_DISPLAY_NAMES.get(archetype, archetype.replace("_", " "))

    expected: list[str] = []
    if "area_damage" in roles or "single_target_damage" in roles:
        expected.append("damage")
    if "soft_control" in roles or "hard_control" in roles:
        expected.append("control")
    if not expected:
        expected.append("damage")

    title = presentation.get("name") or archetype
    cost = {"cheap": "low", "medium": "medium", "expensive": "high"}.get(
        balance.get("cost_band", "medium"), "medium"
    )
    worldbook_id = "long_night_lanterns"
    if isinstance(run_world_state, dict):
        worldbook_id = run_world_state.get("worldbook_id", worldbook_id)

    proposal = {
        "id": f"proposal_{archetype}_001",
        "mode": legalized.get("legalization_mode", "runtime_safe"),
        "title": title,
        "summary": f"把{archetype_display}构想整理为一件可试作的防御方案。",
        "intended_asset_type": legalized.get("asset_kind", "tower_blueprint"),
        "expected_effect": expected,
        "risk_level": balance.get("risk_tier", "medium"),
        "estimated_cost": cost,
        "required_inputs": {
            "npc_ids": [],
            "materials": world_fit.get("source_materials", []),
            "facility": world_fit.get("facility_requirement", "field_workbench"),
            "knowledge_tags": theme.get("world_tags", []),
        },
        "known_tradeoffs": [
            "试作品会先保证战斗规则可用，外观素材可稍后稳定化",
            "成长类效果会受到上限约束",
        ],
        "player_prompt": f"我想试作一个以{archetype_display}为原型的防御设施。",
        "worldbook_id": worldbook_id,
    }
    _enforce_narrative_safe(proposal, node_id)

    out_path = run_dir / f"{node_id}__proposal.json"
    _write_json(out_path, proposal)
    ref = _make_ref(
        artifact_id=f"{node_id}__proposal",
        kind="proposal",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
    )
    return {"output_refs": {"default": ref}}


def node_graph_validate_planned_workflow(
    inputs: dict[str, Any],
    params: dict[str, Any],
    run_dir: Path,
    node_id: str,
) -> dict[str, Any]:
    from validate_workflow import DEFAULT_REGISTRY, validate_workflow

    workflow_graph = _load_artifact(inputs, "workflow_graph")
    registry = json.loads(DEFAULT_REGISTRY.read_text(encoding="utf-8"))
    errors = validate_workflow(workflow_graph, registry)
    report = {
        "schema_version": "workflow_validation_report.v0.1",
        "workflow_id": workflow_graph.get("workflow_id", "unknown"),
        "status": "passed" if not errors else "failed",
        "issues": [{"type": "workflow_validation", "message": e} for e in errors],
    }
    out_path = run_dir / f"{node_id}__workflow_validation_report.json"
    _write_json(out_path, report)
    ref = _make_ref(
        artifact_id=f"{node_id}__workflow_validation_report",
        kind="workflow_validation_report",
        path=out_path,
        run_dir=run_dir,
        produced_by_node=node_id,
    )
    if errors:
        raise NodeError("workflow validation failed: " + "; ".join(errors))
    return {"output_refs": {"default": ref}}


# Registry of node_type -> implementation function.
NODE_IMPLEMENTATIONS: dict[str, Any] = {
    "source.load_json": node_source_load_json,
    "proposal.validate": node_proposal_validate,
    "asset.mock_compile_proposal": node_asset_mock_compile_proposal,
    "asset.compile_with_llm_guarded": node_asset_compile_with_llm_guarded,
    "asset.validate_candidate": node_asset_validate_candidate,
    "asset.simulate_candidate": node_asset_simulate_candidate,
    "asset.score_candidate": node_asset_score_candidate,
    "asset.evaluate_promotion_policy": node_asset_evaluate_promotion_policy,
    "report.pipeline_summary": node_report_pipeline_summary,
    "runtime.build_package_stub": node_runtime_build_package_stub,
    "research.build_delivery_payload_stub": node_research_build_delivery_payload_stub,
    "media.publish_stub_manifest": node_media_publish_stub_manifest,
    "narrative.mock_npc_feedback": node_narrative_mock_npc_feedback,
    "narrative.mock_world_growth_event": node_narrative_mock_world_growth_event,
    "narrative.build_controlled_world_player_bundle": node_narrative_build_controlled_world_player_bundle,
    "media.generate_asset_images_guarded": node_media_generate_asset_images_guarded,
    "media.build_visual_identity_spec": node_media_build_visual_identity_spec,
    "media.check_quality": node_media_check_quality,
    "media.check_consistency": node_media_check_consistency,
    "media.review_with_vision_guarded": node_media_review_with_vision_guarded,
    "media.build_prompt_repair_plan": node_media_build_prompt_repair_plan,
    "media.merge_repaired_sequence": node_media_merge_repaired_sequence,
    "media.remove_background_stub": node_media_remove_background_stub,
    "media.crop_and_pad_stub": node_media_crop_and_pad_stub,
    "media.normalize_canvas_stub": node_media_normalize_canvas_stub,
    "media.assign_anchor_stub": node_media_assign_anchor_stub,
    "media.pack_sprite_sheet_stub": node_media_pack_sprite_sheet_stub,
    "media.build_atlas_json_stub": node_media_build_atlas_json_stub,
    "media.check_runtime_readiness": node_media_check_runtime_readiness,
    "world_state.build_delta_from_narrative_stub": node_world_state_build_delta_from_narrative_stub,
    "world_state.build_delta_with_llm_guarded": node_world_state_build_delta_with_llm_guarded,
    "world_state.validate_delta_semantics": node_world_state_validate_delta_semantics,
    "world_state.apply_delta": node_world_state_apply_delta,
    "asset.legalize_design_spec": node_asset_legalize_design_spec,
    "asset.build_asset_plan": node_asset_build_asset_plan,
    "proposal.build_from_legalized_spec": node_proposal_build_from_legalized_spec,
    "graph.validate_planned_workflow": node_graph_validate_planned_workflow,
}
