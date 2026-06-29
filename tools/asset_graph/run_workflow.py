#!/usr/bin/env python3
"""Run a WorkflowGraph v0.1 DAG deterministically.

Topologically sorts the DAG, executes each node in order, threads ArtifactRefs
between nodes, writes per-node artifacts to output_dir, and emits an
ExecutionTrace. Only deterministic/mock node implementations are used; no real
LLM or provider is called.

Usage:
    python3 tools/asset_graph/run_workflow.py <workflow.json> --output-dir <dir>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import sys
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import nodes as node_mod  # noqa: E402
from validate_workflow import (  # noqa: E402
    DEFAULT_REGISTRY,
    validate_workflow,
)

FORBIDDEN_FIELDS = frozenset(
    {
        "provider",
        "model",
        "raw_prompt",
        "full_trace",
        "raw_json",
        "api_key",
        "secret",
        "unreviewed_content",
    }
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    path.write_text(payload + "\n", encoding="utf-8")


def _topo_sort(
    node_ids: list[str], edges: list[dict[str, Any]]
) -> list[str] | None:
    """Kahn's algorithm. Returns None if a cycle exists."""
    indeg: dict[str, int] = {n: 0 for n in node_ids}
    adj: dict[str, list[str]] = {n: [] for n in node_ids}
    for e in edges:
        src = e.get("source")
        dst = e.get("target")
        if src in indeg and dst in indeg:
            adj[src].append(dst)
            indeg[dst] += 1
    q: deque[str] = deque([n for n in node_ids if indeg[n] == 0])
    order: list[str] = []
    while q:
        n = q.popleft()
        order.append(n)
        for m in adj[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                q.append(m)
    if len(order) != len(node_ids):
        return None
    return order


def _resolve_ref(
    raw: Any, run_dir: Path, produced_paths: dict[str, Path]
) -> Any:
    """Resolve an input declaration into a concrete ArtifactRef dict.

    Supported declarations:
    - A literal ArtifactRef dict with an absolute "path" -> returned as-is.
    - A string artifact_id produced by an upstream node -> looked up in
      produced_paths and wrapped into a ref.
    - A literal dict {"__literal__": true, ...} -> wrapped as a synthetic ref
      written to run_dir so downstream nodes can read it as JSON.
    """
    if raw is None:
        return None
    if isinstance(raw, dict):
        if "path" in raw and Path(raw["path"]).is_absolute():
            return raw
        if raw.get("__literal__"):
            artifact_id = raw.get("artifact_id", f"literal_{secrets.token_hex(4)}")
            out_path = run_dir / "literals" / f"{artifact_id}.json"
            _write_json(out_path, raw.get("data"))
            return {
                "artifact_id": artifact_id,
                "kind": raw.get("kind", "json"),
                "path": str(out_path),
            }
        # Otherwise treat as a literal object to be written.
        artifact_id = raw.get("artifact_id", f"literal_{secrets.token_hex(4)}")
        out_path = run_dir / "literals" / f"{artifact_id}.json"
        _write_json(out_path, raw)
        return {
            "artifact_id": artifact_id,
            "kind": "json",
            "path": str(out_path),
        }
    if isinstance(raw, str) and raw in produced_paths:
        p = produced_paths[raw]
        return {
            "artifact_id": raw,
            "kind": "json",
            "path": str(p),
        }
    # Bare string literal (e.g., a path or scalar) -> return as-is; node must
    # handle it.
    return raw


def _scan_runtime_public_forbidden(value: Any, path: str, errors: list[str]) -> None:
    """Recursively scan a runtime_public artifact for forbidden fields/URLs."""
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key in FORBIDDEN_FIELDS:
                errors.append(
                    f"runtime_public artifact forbidden field '{child_path}'"
                )
            _scan_runtime_public_forbidden(child, child_path, errors)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            _scan_runtime_public_forbidden(child, f"{path}[{i}]", errors)
    elif isinstance(value, str):
        lowered = value.lower()
        if "http://" in lowered or "https://" in lowered or "://" in lowered:
            errors.append(
                f"runtime_public artifact {path}={value!r} must not contain a URL"
            )


def run_workflow(
    workflow: dict[str, Any], registry: dict[str, Any], output_dir: Path
) -> dict[str, Any]:
    trace_id = f"trace_{secrets.token_hex(8)}"
    workflow_id = workflow.get("workflow_id", "workflow")
    mode = workflow.get("mode", "deterministic")
    started_at = _now_iso()

    # Validate before executing.
    val_errors = validate_workflow(workflow, registry)
    if val_errors:
        return {
            "schema_version": "execution_trace.v0.1",
            "trace_id": trace_id,
            "workflow_id": workflow_id,
            "mode": mode,
            "started_at": started_at,
            "ended_at": _now_iso(),
            "status": "failed",
            "error": "workflow validation failed: " + "; ".join(val_errors),
            "node_runs": [],
        }

    nodes_list = workflow.get("nodes", [])
    edges = workflow.get("edges", [])
    node_by_id: dict[str, dict[str, Any]] = {n["id"]: n for n in nodes_list}
    order = _topo_sort(list(node_by_id.keys()), edges)
    if order is None:
        return {
            "schema_version": "execution_trace.v0.1",
            "trace_id": trace_id,
            "workflow_id": workflow_id,
            "mode": mode,
            "started_at": started_at,
            "ended_at": _now_iso(),
            "status": "failed",
            "error": "workflow graph contains a cycle",
            "node_runs": [],
        }

    run_dir = output_dir / workflow_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Track produced artifact paths by artifact_id (we use node_id__<kind> as
    # the artifact_id convention; edges map source node -> target node default).
    produced_paths: dict[str, Path] = {}
    # Track each node's output_refs by node_id for edge threading.
    node_output_refs: dict[str, dict[str, Any]] = {}

    node_runs: list[dict[str, Any]] = []
    overall_status = "passed"

    for node_id in order:
        node = node_by_id[node_id]
        node_type = node.get("node_type", "")
        node_start = _now_iso()

        # Resolve inputs from incoming edges.
        resolved_inputs: dict[str, Any] = {}
        for e in edges:
            if e.get("target") != node_id:
                continue
            src = e.get("source")
            target_input = e.get("target_input", "default")
            source_output = e.get("source_output", "default")
            src_refs = node_output_refs.get(src, {})
            ref = src_refs.get(source_output)
            if ref is None:
                continue
            # Resolve relative path to absolute against run_dir so downstream
            # nodes can load the artifact by absolute path.
            if isinstance(ref, dict) and "path" in ref:
                ref = dict(ref)
                p = Path(ref["path"])
                if not p.is_absolute():
                    ref["path"] = str(run_dir / p)
            resolved_inputs[target_input] = ref

        # Also resolve any literal inputs declared on the node itself.
        for name, raw in (node.get("inputs") or {}).items():
            if name not in resolved_inputs:
                resolved_inputs[name] = _resolve_ref(raw, run_dir, produced_paths)

        params = node.get("params") or {}
        impl = node_mod.NODE_IMPLEMENTATIONS.get(node_type)
        node_run: dict[str, Any] = {
            "node_id": node_id,
            "node_type": node_type,
            "status": "skipped",
            "started_at": node_start,
            "ended_at": node_start,
            "input_refs": [
                v for v in resolved_inputs.values() if isinstance(v, dict) and "path" in v
            ],
            "output_refs": [],
            "errors": [],
            "fallback_used": False,
        }

        if impl is None:
            node_run["status"] = "failed"
            node_run["errors"].append(
                f"no implementation registered for node_type={node_type!r}"
            )
            node_run["ended_at"] = _now_iso()
            node_runs.append(node_run)
            overall_status = "failed"
            break

        try:
            result = impl(resolved_inputs, params, run_dir, node_id)
            out_refs = result.get("output_refs", {})
            node_output_refs[node_id] = out_refs
            for ref in out_refs.values():
                if isinstance(ref, dict) and "path" in ref:
                    abs_path = (
                        Path(ref["path"])
                        if Path(ref["path"]).is_absolute()
                        else run_dir / ref["path"]
                    )
                    produced_paths[ref.get("artifact_id", node_id)] = abs_path
            node_run["output_refs"] = list(out_refs.values())
            node_run["status"] = "passed"

            # runtime_public post-check: scan the produced artifact file for
            # forbidden fields and provider URLs.
            if node.get("runtime_public") is True:
                for ref in out_refs.values():
                    if not isinstance(ref, dict) or "path" not in ref:
                        continue
                    abs_path = (
                        Path(ref["path"])
                        if Path(ref["path"]).is_absolute()
                        else run_dir / ref["path"]
                    )
                    if not abs_path.exists():
                        continue
                    try:
                        artifact_data = _load_json(abs_path)
                    except json.JSONDecodeError:
                        continue
                    pub_errors: list[str] = []
                    _scan_runtime_public_forbidden(
                        artifact_data, str(abs_path), pub_errors
                    )
                    if pub_errors:
                        node_run["status"] = "failed"
                        node_run["errors"].extend(pub_errors)
                        overall_status = "failed"
        except node_mod.NodeError as exc:
            node_run["status"] = "failed"
            node_run["errors"].append(str(exc))
            node_run["ended_at"] = _now_iso()
            node_runs.append(node_run)
            overall_status = "failed"
            break
        except Exception as exc:  # pragma: no cover - defensive
            node_run["status"] = "failed"
            node_run["errors"].append(f"unexpected error: {type(exc).__name__}: {exc}")
            node_run["ended_at"] = _now_iso()
            node_runs.append(node_run)
            overall_status = "failed"
            break

        node_run["ended_at"] = _now_iso()
        node_runs.append(node_run)

    trace = {
        "schema_version": "execution_trace.v0.1",
        "trace_id": trace_id,
        "workflow_id": workflow_id,
        "mode": mode,
        "started_at": started_at,
        "ended_at": _now_iso(),
        "status": overall_status,
        "node_runs": node_runs,
    }
    if overall_status != "passed":
        trace["error"] = f"workflow {workflow_id} did not pass"

    trace_path = run_dir / "execution_trace.json"
    _write_json(trace_path, trace)
    return trace


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a WorkflowGraph v0.1 DAG deterministically."
    )
    parser.add_argument("workflow", help="Path to a workflow JSON file.")
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where run artifacts and execution_trace.json are written.",
    )
    parser.add_argument(
        "--registry",
        default=str(DEFAULT_REGISTRY),
        help="Path to node_registry.v0.1.json.",
    )
    args = parser.parse_args()

    workflow_path = Path(args.workflow)
    output_dir = Path(args.output_dir)
    registry_path = Path(args.registry)

    try:
        workflow = _load_json(workflow_path)
    except FileNotFoundError:
        print(f"workflow file not found: {workflow_path}")
        return 1
    except json.JSONDecodeError as exc:
        print(f"workflow is not valid JSON: {exc}")
        return 1

    try:
        registry = _load_json(registry_path)
    except FileNotFoundError:
        print(f"registry file not found: {registry_path}")
        return 1

    trace = run_workflow(workflow, registry, output_dir)
    trace_path = output_dir / workflow.get("workflow_id", "workflow") / "execution_trace.json"
    print(f"trace: {trace_path}")
    print(f"status: {trace.get('status')}")
    for nr in trace.get("node_runs", []):
        marker = "OK" if nr.get("status") == "passed" else "FAIL"
        print(f"  [{marker}] {nr.get('node_id')} ({nr.get('node_type')})")
        for err in nr.get("errors", []):
            print(f"        - {err}")
    return 0 if trace.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
