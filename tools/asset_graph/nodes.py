"""Node implementations for the AssetGraph Kernel v0.1.

All nodes in this module are deterministic / mock. None call a real LLM or
provider. Each node function takes:
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

import mock_compile_proposal  # noqa: E402
import simulate_asset_candidate  # noqa: E402
import validate_asset_candidate  # noqa: E402
import validate_proposal  # noqa: E402


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
    manifest = _load_artifact(inputs, "locked_manifest")
    battle = _load_artifact(inputs, "battle_config")
    # Build a minimal runtime package stub. No raw_media, no provider URLs.
    locked_assets = manifest.get("locked_assets", [])
    package = {
        "package_version": "runtime_package_stub.v0.1",
        "worldbook_id": manifest.get("worldbook_id"),
        "session_id": manifest.get("session_id"),
        "node_id": battle.get("node_id"),
        "battle_display_name": battle.get("display_name"),
        "sample_assets": [
            {
                "stable_internal_id": a.get("stable_internal_id"),
                "display_name": a.get("display", {}).get("name"),
                "uses_per_battle": a.get("battle_availability", {}).get("uses_per_battle"),
                "requires_delivery": a.get("battle_availability", {}).get("requires_delivery"),
                "delivery_state": a.get("battle_availability", {}).get("delivery_state"),
            }
            for a in locked_assets
        ],
        # No raw_media, no processed_media, no provider URLs.
        "media_refs": [],
    }
    out_path = run_dir / f"{node_id}__runtime_package_stub.json"
    _write_json(out_path, package)
    ref = _make_ref(
        artifact_id=f"{node_id}__runtime_package_stub",
        kind="runtime_package_stub",
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
            "source_layer": "raw_media",
            "fallback_used": item.get("fallback_used", True),
        })
    manifest = {
        "manifest_version": "published_media_manifest.v0.1",
        "published_media": published,
        # raw_media and processed_media layers are intentionally NOT exposed
        # here; only published_media may be runtime_public.
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


# Registry of node_type -> implementation function.
NODE_IMPLEMENTATIONS: dict[str, Any] = {
    "source.load_json": node_source_load_json,
    "proposal.validate": node_proposal_validate,
    "asset.mock_compile_proposal": node_asset_mock_compile_proposal,
    "asset.validate_candidate": node_asset_validate_candidate,
    "asset.simulate_candidate": node_asset_simulate_candidate,
    "report.pipeline_summary": node_report_pipeline_summary,
    "runtime.build_package_stub": node_runtime_build_package_stub,
    "research.build_delivery_payload_stub": node_research_build_delivery_payload_stub,
    "media.publish_stub_manifest": node_media_publish_stub_manifest,
}
