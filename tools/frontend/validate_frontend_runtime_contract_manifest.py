#!/usr/bin/env python3
"""Validate FrontendRuntimeContractManifest v0.1 files."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from report_io import load_json_object


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "frontend_runtime_contract_manifest.v0.1"
REQUIRED_DEEP_LINK_IDS = {
    "default_player_entry",
    "static_battle_visual_smoke",
    "static_battle_dialogue_smoke",
}
REQUIRED_QUERY_FLAGS = {
    "static",
    "staticMode",
    "apiBase",
    "nodeId",
    "node",
    "flowVisualSmoke",
    "battleVisualSmoke",
    "battleVisualHold",
    "battleDialogueSmoke",
    "mapVisualDebug",
    "evidence",
}
REQUIRED_SELECTORS = {
    "#app",
    "#battleCanvas",
    ".battle-shell",
    ".battle-stage",
    ".battle-tools",
    ".toolbar-card[data-tool]",
    ".dialogue-overlay",
}
REQUIRED_DATA_ACTIONS = {
    "select-map-node",
    "enter-node",
    "select-tool",
    "close-dialogue",
    "toggle-pause",
    "cycle-speed",
    "return-map",
    "restart-battle",
}
REQUIRED_DATA_TOOLS = {"basic", "sample", "support"}
REQUIRED_HOOKS = {
    "window.__AI_TD_BATTLE_SMOKE__.snapshot",
    "window.__AI_TD_BATTLE_SMOKE__.deploymentPoint",
}
REQUIRED_RUNTIME_TYPES = {"RuntimeBundle", "RuntimeSnapshot", "FeatureSnapshot"}
REQUIRED_RUNTIME_TYPES.update(
    {"ActivatedRuntimeBundle", "BattleObjectCapability", "RuntimeActivationReceipt"}
)
REQUIRED_RUNTIME_LAYERS = {
    "ActivatedRuntimeBundle",
    "RuntimeSnapshot",
    "FeatureSnapshot",
    "BattleObjectCapability",
    "RuntimeActivationReceipt",
}
REQUIRED_MIGRATION_TARGETS = {
    "runtime_bundle_loader",
    "battle_map_adapter",
    "onboarding_feature_controller",
    "workshop_feature_controller",
    "settlement_feature_controller",
    "root_event_router",
    "feature_gate_registry",
    "smoke_contract_harness",
}
REQUIRED_FORBIDDEN_TERMS = {
    "provider",
    "model",
    "raw_prompt",
    "full_trace",
    "raw_json",
    "api_key",
    "secret",
    ".env",
}
FORBIDDEN_EXEMPT_PATHS = {("runtime_safe_policy", "forbidden_terms")}
SOURCE_CONTRACT_FILES = (
    ROOT / "frontend" / "index.html",
    ROOT / "frontend" / "app.js",
    ROOT / "frontend" / "styles.css",
)
RUNTIME_MODULE_DIR = ROOT / "frontend" / "runtime"
RUNTIME_SCHEMA_CONTRACTS = {
    ROOT / "shared/schemas/battle_object_capability.v0.1.schema.json": (
        "battle_object_capability.v0.1"
    ),
    ROOT / "shared/schemas/runtime_activation_receipt.v0.1.schema.json": (
        "runtime_activation_receipt.v0.1"
    ),
}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def path_text(path: tuple[str, ...]) -> str:
    return "$" + "".join(f".{part}" for part in path)


def is_exempt_path(path: tuple[str, ...]) -> bool:
    return any(path[: len(exempt)] == exempt for exempt in FORBIDDEN_EXEMPT_PATHS)


def normalized_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def scan_forbidden_terms(
    value: Any,
    terms: set[str],
    path: tuple[str, ...] = (),
) -> list[str]:
    if is_exempt_path(path):
        return []
    hits: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            key_lower = key_text.lower()
            key_normalized = normalized_token(key_text)
            for term in terms:
                if term in key_lower or normalized_token(term) in key_normalized:
                    hits.append(f"{path_text(path + (key_text,))} key contains {term!r}")
            hits.extend(scan_forbidden_terms(child, terms, path + (key_text,)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            hits.extend(scan_forbidden_terms(child, terms, path + (str(index),)))
    elif isinstance(value, str):
        lower = value.lower()
        normalized = normalized_token(value)
        for term in terms:
            if term in lower or normalized_token(term) in normalized:
                hits.append(f"{path_text(path)} contains {term!r}")
    return hits


def source_text() -> str:
    chunks: list[str] = []
    runtime_module_files = sorted(RUNTIME_MODULE_DIR.glob("*.js")) if RUNTIME_MODULE_DIR.exists() else []
    for path in (*SOURCE_CONTRACT_FILES, *runtime_module_files):
        if path.exists():
            chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def validate_source_contract(
    *,
    source: str,
    deep_links: list[dict[str, Any]],
    query_flags: set[str],
    selectors: set[str],
    data_actions: set[str],
    data_tools: set[str],
    hooks: set[str],
    failures: list[str],
) -> None:
    for item in deep_links:
        path = str(item.get("path") or "")
        if not path:
            failures.append("declared deep link missing path")
            continue
        parsed = urlparse(path)
        query_keys = set(parse_qs(parsed.query).keys())
        query_present = all(key in source for key in query_keys)
        entry_file_exists = parsed.path == "/frontend/index.html" and (ROOT / "frontend" / "index.html").exists()
        require(
            entry_file_exists and query_present,
            f"declared deep link is not backed by frontend runtime entry/query handling: {path}",
            failures,
        )
    for flag in sorted(query_flags):
        require(
            flag in source,
            f"declared query flag is not present in frontend runtime source: {flag}",
            failures,
        )
    for selector in sorted(selectors):
        if selector.startswith("#"):
            ident = selector[1:]
            present = (
                selector in source
                or f'id="{ident}"' in source
                or f"id='{ident}'" in source
                or f"getElementById(\"{ident}\")" in source
                or f"getElementById('{ident}')" in source
            )
        elif selector.startswith("."):
            class_name = selector[1:].split("[", 1)[0]
            present = selector in source or class_name in source
        elif selector.startswith("["):
            attr_name = selector.strip("[]").split("=", 1)[0]
            present = selector in source or attr_name in source
        else:
            present = selector in source
        require(present, f"declared selector is not present in frontend source: {selector}", failures)
    for action in sorted(data_actions):
        require(
            f'data-action="{action}"' in source or f"data-action='{action}'" in source,
            f"declared data-action is not present in frontend source: {action}",
            failures,
        )
    for tool in sorted(data_tools):
        require(
            f'data-tool="{tool}"' in source
            or f"data-tool='{tool}'" in source
            or (
                ('data-tool="${tool.id}"' in source or 'data-tool="${safeText(tool.id)}"' in source)
                and (f'id: "{tool}"' in source or f"id: '{tool}'" in source)
            ),
            f"declared data-tool is not present in frontend source: {tool}",
            failures,
        )
    for hook in sorted(hooks):
        hook_without_window = hook.replace("window.", "")
        hook_parts = hook_without_window.split(".")
        hook_base = hook_parts[0]
        hook_leaf = hook_parts[-1]
        require(
            hook in source
            or (hook_base in source and f"{hook_leaf}:" in source)
            or (hook_base in source and f"{hook_leaf} =" in source),
            f"declared window smoke hook is not present in frontend source: {hook}",
            failures,
        )


def validate(manifest: dict[str, Any]) -> None:
    failures: list[str] = []
    for schema_path, version in RUNTIME_SCHEMA_CONTRACTS.items():
        require(schema_path.is_file(), f"runtime schema missing: {schema_path}", failures)
        if not schema_path.is_file():
            continue
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        require(
            as_obj(as_obj(schema).get("properties")).get("schema_version", {}).get("const")
            == version,
            f"runtime schema version mismatch: {schema_path.name}",
            failures,
        )
        require(
            schema.get("additionalProperties") is False,
            f"runtime schema root must reject extra properties: {schema_path.name}",
            failures,
        )
    require(manifest.get("schema_version") == SCHEMA_VERSION, "schema_version mismatch", failures)
    for field in (
        "manifest_id",
        "public_runtime_entrypoints",
        "selectors_contract",
        "window_smoke_hooks",
        "runtime_type_names",
        "runtime_contract_names",
        "runtime_contract_layers",
        "frontend_runtime_authority",
        "modular_migration_targets",
        "runtime_safe_policy",
    ):
        require(field in manifest, f"missing top-level field: {field}", failures)

    entrypoints = as_obj(manifest.get("public_runtime_entrypoints"))
    deep_links = [item for item in as_list(entrypoints.get("deep_links")) if isinstance(item, dict)]
    deep_link_ids = {
        str(item.get("id"))
        for item in deep_links
    }
    require(
        REQUIRED_DEEP_LINK_IDS <= deep_link_ids,
        f"missing deep links: {sorted(REQUIRED_DEEP_LINK_IDS - deep_link_ids)}",
        failures,
    )
    query_flags = {
        str(item.get("name"))
        for item in as_list(entrypoints.get("query_flags"))
        if isinstance(item, dict)
    }
    require(
        REQUIRED_QUERY_FLAGS <= query_flags,
        f"missing query flags: {sorted(REQUIRED_QUERY_FLAGS - query_flags)}",
        failures,
    )

    selectors = as_obj(manifest.get("selectors_contract"))
    root_selectors = set(map(str, as_list(selectors.get("root_selectors"))))
    smoke_selectors = set(map(str, as_list(selectors.get("smoke_required_selectors"))))
    require(
        REQUIRED_SELECTORS <= (root_selectors | smoke_selectors),
        f"missing selectors: {sorted(REQUIRED_SELECTORS - (root_selectors | smoke_selectors))}",
        failures,
    )
    data_actions = set(map(str, as_list(selectors.get("data_actions"))))
    require(
        REQUIRED_DATA_ACTIONS <= data_actions,
        f"missing data-actions: {sorted(REQUIRED_DATA_ACTIONS - data_actions)}",
        failures,
    )
    data_tools = set(map(str, as_list(selectors.get("data_tools"))))
    require(
        REQUIRED_DATA_TOOLS <= data_tools,
        f"missing data-tools: {sorted(REQUIRED_DATA_TOOLS - data_tools)}",
        failures,
    )

    hooks = {
        str(item.get("name"))
        for item in as_list(manifest.get("window_smoke_hooks"))
        if isinstance(item, dict)
    }
    require(
        REQUIRED_HOOKS <= hooks,
        f"missing window smoke hooks: {sorted(REQUIRED_HOOKS - hooks)}",
        failures,
    )

    runtime_types = set(map(str, as_list(manifest.get("runtime_type_names"))))
    require(
        REQUIRED_RUNTIME_TYPES <= runtime_types,
        f"missing runtime type names: {sorted(REQUIRED_RUNTIME_TYPES - runtime_types)}",
        failures,
    )
    contract_names = set(as_obj(manifest.get("runtime_contract_names")).keys())
    require(
        REQUIRED_RUNTIME_TYPES <= contract_names,
        f"missing runtime contract names: {sorted(REQUIRED_RUNTIME_TYPES - contract_names)}",
        failures,
    )
    layers = as_obj(manifest.get("runtime_contract_layers"))
    require(
        REQUIRED_RUNTIME_LAYERS <= set(layers.keys()),
        f"missing runtime contract layers: {sorted(REQUIRED_RUNTIME_LAYERS - set(layers.keys()))}",
        failures,
    )
    authority = as_obj(manifest.get("frontend_runtime_authority"))
    require(
        authority.get("activation_authority") == "backend_or_published_artifact",
        "frontend_runtime_authority.activation_authority must stay backend_or_published_artifact",
        failures,
    )
    require(
        authority.get("frontend_role") == "consume_only",
        "frontend_runtime_authority.frontend_role must stay consume_only",
        failures,
    )
    target_ids = {
        str(item.get("id"))
        for item in as_list(manifest.get("modular_migration_targets"))
        if isinstance(item, dict)
    }
    require(
        REQUIRED_MIGRATION_TARGETS <= target_ids,
        f"missing migration targets: {sorted(REQUIRED_MIGRATION_TARGETS - target_ids)}",
        failures,
    )

    policy = as_obj(manifest.get("runtime_safe_policy"))
    forbidden_terms = {str(term).lower() for term in as_list(policy.get("forbidden_terms"))}
    require(
        REQUIRED_FORBIDDEN_TERMS <= forbidden_terms,
        f"missing runtime-safe forbidden terms: {sorted(REQUIRED_FORBIDDEN_TERMS - forbidden_terms)}",
        failures,
    )
    scanner_terms = forbidden_terms or REQUIRED_FORBIDDEN_TERMS
    forbidden_hits = scan_forbidden_terms(manifest, scanner_terms)
    require(
        not forbidden_hits,
        "forbidden runtime terms outside policy declaration: " + "; ".join(forbidden_hits[:12]),
        failures,
    )
    validate_source_contract(
        source=source_text(),
        deep_links=deep_links,
        query_flags=query_flags,
        selectors=REQUIRED_SELECTORS,
        data_actions=data_actions,
        data_tools=data_tools,
        hooks=hooks,
        failures=failures,
    )

    if failures:
        raise ValueError("\n- ".join(["manifest validation failed", *failures]))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        validate(load_json_object(args.manifest, label="manifest root"))
    except Exception as exc:  # noqa: BLE001 - CLI validator should stay concise.
        print(f"frontend runtime contract manifest validation failed: {exc}", file=sys.stderr)
        return 1
    print(f"frontend runtime contract manifest validation passed: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
