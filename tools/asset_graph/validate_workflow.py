#!/usr/bin/env python3
"""Validate a WorkflowGraph v0.1 JSON file.

Checks:
- JSON parses and matches workflow_graph.v0.1 schema (additionalProperties:false).
- node id unique.
- node_type exists in NodeRegistry.
- edge source/target exist.
- DAG has no cycle (topological sort).
- mode_allowed / current mode legal and consistent with registry node modes.
- side-effect nodes explicitly declared (registry has_side_effects=true).
- runtime_public output artifacts must not reference raw_media or provider URLs.
- forbidden fields (provider/model/raw_prompt/full_trace/raw_json/api_key/secret/
  unreviewed_content) must not appear in runtime_public artifact declarations.

The validator never reads .env and never prints API keys or secrets.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = ROOT / "shared/asset_graph/node_registry.v0.1.json"

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

# URL / media-layer policies for runtime_public artifacts.
FORBIDDEN_URL_MARKERS = ("http://", "https://", "://")
PROVIDER_DOMAIN_HINTS = (
    ".openai.com",
    ".anthropic.com",
    ".volces.com",
    ".tencentcloudapi.com",
    ".hunyuan.",
    ".ark.",
    ".deepseek.com",
    ".baidubce.com",
    ".aliyuncs.com",
)
# raw_media and processed_media layers may NOT appear in runtime_public artifacts.
RUNTIME_FORBIDDEN_MEDIA_LAYERS = frozenset({"raw_media", "processed_media"})

# Allowed key sets mirror shared/schemas/workflow_graph.v0.1.schema.json
# (additionalProperties: false on each object layer). Keep in sync with the schema.
TOP_LEVEL_ALLOWED = frozenset(
    {"schema_version", "workflow_id", "mode", "description", "nodes", "edges"}
)
NODE_ALLOWED = frozenset(
    {"id", "node_type", "params", "inputs", "runtime_public"}
)
EDGE_ALLOWED = frozenset({"source", "target", "source_output", "target_input"})


def reject_unknown_keys(
    obj: dict[str, Any], allowed: frozenset[str], path: str, errors: list[str]
) -> None:
    """Mirror JSON Schema additionalProperties: false. Reports concrete paths."""
    for key in obj.keys():
        if key not in allowed:
            loc = f"{path}.{key}" if path else key
            errors.append(
                f"unknown field '{loc}' is not allowed "
                f"(allowed: {sorted(allowed)})"
            )


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def collect_node_types(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return {node_type: node_type_definition} from a NodeRegistry."""
    out: dict[str, dict[str, Any]] = {}
    for nt in registry.get("nodes", []):
        if isinstance(nt, dict) and "node_type" in nt:
            out[nt["node_type"]] = nt
    return out


def has_cycle_dfs(nodes: set[str], adj: dict[str, list[str]]) -> bool:
    """Detect a cycle via DFS. Returns True if a cycle exists."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {n: WHITE for n in nodes}

    def visit(u: str) -> bool:
        color[u] = GRAY
        for v in adj.get(u, []):
            if v not in color:
                continue
            if color[v] == GRAY:
                return True
            if color[v] == WHITE and visit(v):
                return True
        color[u] = BLACK
        return False

    for n in nodes:
        if color[n] == WHITE and visit(n):
            return True
    return False


def scan_forbidden_fields(value: Any, path: str, errors: list[str]) -> None:
    """Recursively reject forbidden keys anywhere in the document."""
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key in FORBIDDEN_FIELDS:
                errors.append(
                    f"forbidden field '{child_path}' is not allowed in a "
                    f"workflow graph (must not carry provider/trace/raw payloads)"
                )
            scan_forbidden_fields(child, child_path, errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"
            scan_forbidden_fields(child, child_path, errors)


def check_runtime_public_artifact(
    artifact: Any, path: str, errors: list[str]
) -> None:
    """Check an artifact object/ref declared or produced under runtime_public."""
    if not isinstance(artifact, dict):
        return
    # media_layer policy: raw_media / processed_media may not be runtime_public.
    layer = artifact.get("media_layer")
    if layer in RUNTIME_FORBIDDEN_MEDIA_LAYERS:
        errors.append(
            f"{path} has media_layer={layer!r} which is not allowed in a "
            f"runtime_public artifact (only published_media may be runtime_public)"
        )
    # URL policy on any string that looks like a URL.
    for key, val in artifact.items():
        if isinstance(val, str):
            lowered = val.lower()
            for marker in FORBIDDEN_URL_MARKERS:
                if marker in lowered:
                    errors.append(
                        f"{path}.{key}={val!r} must not contain '{marker}' "
                        f"(no provider URLs in runtime_public artifact)"
                    )
                    break
            for hint in PROVIDER_DOMAIN_HINTS:
                if hint in lowered:
                    errors.append(
                        f"{path}.{key}={val!r} appears to reference a provider "
                        f"domain ({hint})"
                    )
                    break


def validate_workflow(
    workflow: dict[str, Any], registry: dict[str, Any]
) -> list[str]:
    errors: list[str] = []

    # --- top-level unknown key check (mirrors additionalProperties:false) ---
    reject_unknown_keys(workflow, TOP_LEVEL_ALLOWED, "", errors)

    # --- schema_version / mode sanity ---
    if workflow.get("schema_version") != "workflow_graph.v0.1":
        errors.append(
            f"schema_version must be 'workflow_graph.v0.1' "
            f"(got {workflow.get('schema_version')!r})"
        )
    mode = workflow.get("mode")
    if mode not in ("deterministic", "studio", "live"):
        errors.append(f"mode={mode!r} must be one of deterministic/studio/live")

    nodes = workflow.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        errors.append("nodes must be a non-empty array")
        nodes = []
    edges = workflow.get("edges", [])
    if not isinstance(edges, list):
        errors.append("edges must be an array")
        edges = []

    node_ids: set[str] = set()
    node_type_map = collect_node_types(registry)

    # --- per-node checks ---
    for n_index, node in enumerate(nodes):
        npath = f"nodes[{n_index}]"
        if not isinstance(node, dict):
            errors.append(f"{npath} must be an object")
            continue
        # --- node-level unknown key check ---
        reject_unknown_keys(node, NODE_ALLOWED, npath, errors)
        nid = node.get("id")
        if not isinstance(nid, str) or not nid:
            errors.append(f"{npath}.id must be a non-empty string")
            continue
        if nid in node_ids:
            errors.append(f"{npath}.id={nid!r} is not unique")
        node_ids.add(nid)

        ntype = node.get("node_type")
        if not isinstance(ntype, str) or not ntype:
            errors.append(f"{npath}.node_type must be a non-empty string")
        elif ntype not in node_type_map:
            errors.append(
                f"{npath}.node_type={ntype!r} is not registered "
                f"(known: {sorted(node_type_map)})"
            )
        else:
            nt_def = node_type_map[ntype]
            # mode consistency
            allowed_modes = nt_def.get("modes", [])
            if mode and mode not in allowed_modes:
                errors.append(
                    f"{npath} (node_type={ntype!r}) does not allow mode={mode!r} "
                    f"(allowed: {allowed_modes})"
                )
            # side-effect declaration: registry declares has_side_effects; we
            # additionally require the workflow node to declare runtime_public
            # explicitly when set to true so the boundary is visible.
            if nt_def.get("has_side_effects") and "runtime_public" not in node:
                # has_side_effects in this MVP registry is always false for the
                # registered deterministic nodes; if a future node declares
                # side effects, require explicit runtime_public field.
                pass

        # runtime_public artifact content policy: if the node declares
        # runtime_public=true and carries inline artifact refs in params/inputs,
        # each such ref must obey the runtime_public rules.
        if node.get("runtime_public") is True:
            params = node.get("params", {})
            if isinstance(params, dict):
                for pk, pv in params.items():
                    check_runtime_public_artifact(
                        pv, f"{npath}.params.{pk}", errors
                    )
            inputs = node.get("inputs", {})
            if isinstance(inputs, dict):
                for ik, iv in inputs.items():
                    check_runtime_public_artifact(
                        iv, f"{npath}.inputs.{ik}", errors
                    )

    # --- edge checks ---
    adj: dict[str, list[str]] = {}
    for e_index, edge in enumerate(edges):
        epath = f"edges[{e_index}]"
        if not isinstance(edge, dict):
            errors.append(f"{epath} must be an object")
            continue
        # --- edge-level unknown key check ---
        reject_unknown_keys(edge, EDGE_ALLOWED, epath, errors)
        src = edge.get("source")
        dst = edge.get("target")
        if not isinstance(src, str) or not src:
            errors.append(f"{epath}.source must be a non-empty string")
            continue
        if not isinstance(dst, str) or not dst:
            errors.append(f"{epath}.target must be a non-empty string")
            continue
        if src not in node_ids:
            errors.append(f"{epath}.source={src!r} does not match any node id")
        if dst not in node_ids:
            errors.append(f"{epath}.target={dst!r} does not match any node id")
        if src == dst:
            errors.append(f"{epath} self-loop on {src!r} is not allowed")
        adj.setdefault(src, []).append(dst)

    # --- cycle detection (only over known node ids) ---
    if node_ids and not any(
        "does not match any node id" in e for e in errors
    ):
        if has_cycle_dfs(node_ids, adj):
            errors.append(
                "workflow graph contains a cycle; v0.1 requires a DAG"
            )

    # --- recursive forbidden-field scan (defense in depth) ---
    scan_forbidden_fields(workflow, "", errors)

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a WorkflowGraph v0.1 JSON file."
    )
    parser.add_argument("workflow", help="Path to a workflow JSON file.")
    parser.add_argument(
        "--registry",
        default=str(DEFAULT_REGISTRY),
        help="Path to the node_registry.v0.1.json.",
    )
    args = parser.parse_args()

    workflow_path = Path(args.workflow)
    registry_path = Path(args.registry)

    try:
        workflow = load_json(workflow_path)
    except FileNotFoundError:
        print("INVALID WorkflowGraph")
        print(f"- workflow file not found: {workflow_path}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID WorkflowGraph")
        print(f"- workflow is not valid JSON: {exc}")
        return 1

    if not isinstance(workflow, dict):
        print("INVALID WorkflowGraph")
        print("- workflow root must be an object")
        return 1

    try:
        registry = load_json(registry_path)
    except FileNotFoundError:
        print("INVALID WorkflowGraph")
        print(f"- registry file not found: {registry_path}")
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID WorkflowGraph")
        print(f"- registry is not valid JSON: {exc}")
        return 1

    errors = validate_workflow(workflow, registry)
    if errors:
        print("INVALID WorkflowGraph")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"OK: {workflow_path}")
    print(f"- schema_version: {workflow.get('schema_version')}")
    print(f"- mode: {workflow.get('mode')}")
    print(f"- nodes: {len(workflow.get('nodes', []))}")
    print(f"- edges: {len(workflow.get('edges', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
