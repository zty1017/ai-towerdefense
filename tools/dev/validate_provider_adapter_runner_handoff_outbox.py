#!/usr/bin/env python3
"""Validate ProviderAdapterRunnerHandoffOutbox v0.1 artifacts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
ASSET_GRAPH_DIR = ROOT / "tools" / "asset_graph"
if str(ASSET_GRAPH_DIR) not in sys.path:
    sys.path.insert(0, str(ASSET_GRAPH_DIR))

from validation_common import load_json, validate_json_schema  # noqa: E402


SCHEMA_PATH = ROOT / "shared/schemas/provider_adapter_runner_handoff_outbox.v0.1.schema.json"
SCHEMA_VERSION = "provider_adapter_runner_handoff_outbox.v0.1"
HANDOFF_SCHEMA_VERSION = "provider_adapter_runner_handoff.v0.1"
FORBIDDEN_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "secret_key",
    "password",
    "auth_token",
    "access_token",
    "refresh_token",
    "raw_prompt",
    "full_prompt",
    "provider_response",
    "raw_response",
    "raw_json",
    "full_trace",
    "unreviewed_content",
)
FORBIDDEN_STRING_FRAGMENTS = (
    "api_key=",
    "apikey=",
    "bearer ",
    "sk-",
    "raw_prompt",
    "full_prompt",
    "provider_response",
    "raw_response",
    "raw json",
    "full trace",
)
ALLOWED_SAFETY_KEYS = {
    "provider_response_body_included",
}


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def references_dotenv_path(value: str) -> bool:
    return ".env" in Path(value).parts


def command_mode(command: list[Any]) -> str | None:
    try:
        mode_index = command.index("--mode")
    except ValueError:
        return None
    if mode_index + 1 >= len(command):
        return None
    mode = command[mode_index + 1]
    return mode if isinstance(mode, str) else None


def scan_forbidden(value: Any, errors: list[str], path: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            lowered = key.lower()
            if lowered not in ALLOWED_SAFETY_KEYS and any(
                fragment in lowered for fragment in FORBIDDEN_KEY_FRAGMENTS
            ):
                errors.append(f"forbidden key in handoff outbox: {child_path}")
            scan_forbidden(child, errors, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_forbidden(child, errors, f"{path}[{index}]")
    elif isinstance(value, str):
        lowered = value.lower()
        for fragment in FORBIDDEN_STRING_FRAGMENTS:
            if fragment in lowered:
                errors.append(f"forbidden string fragment {fragment!r} at {path}")


def check_outbox_safety(outbox: dict[str, Any], errors: list[str]) -> None:
    if outbox.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if outbox.get("handoff_mode") != "external_runner_required":
        errors.append("handoff_mode must be external_runner_required")
    if outbox.get("review_only") is not True:
        errors.append("review_only must be true")
    safety = as_obj(outbox.get("safety"))
    expected_false = (
        "api_reads_env",
        "api_calls_provider",
        "api_runs_provider_adapter",
        "api_stages_provider_artifacts",
        "api_promotes_provider_artifacts",
        "api_completes_queue_items",
        "api_writes_world_state",
        "api_activates_runtime",
        "prompt_body_included",
        "provider_response_body_included",
    )
    for key in expected_false:
        if safety.get(key) is not False:
            errors.append(f"safety.{key} must be false")
    if safety.get("live_templates_require_external_explicit_authorization") is not True:
        errors.append(
            "safety.live_templates_require_external_explicit_authorization must be true"
        )


def check_import_contract(outbox: dict[str, Any], errors: list[str]) -> None:
    contract = as_obj(outbox.get("import_contract"))
    if contract.get("method") != "POST":
        errors.append("import_contract.method must be POST")
    if contract.get("post_import_gate") != "provider_artifact_staging_or_promotion_review_required":
        errors.append("import_contract.post_import_gate is invalid")
    required = set(as_list(contract.get("required_body_fields")))
    for field in ("schedule_item_id", "authorization_ref", "receipt_path", "envelope_path"):
        if field not in required:
            errors.append(f"import_contract.required_body_fields must include {field}")


def check_handoff(outbox: dict[str, Any], handoff: dict[str, Any], index: int, errors: list[str]) -> None:
    prefix = f"runner_handoffs[{index}]"
    if handoff.get("schema_version") != HANDOFF_SCHEMA_VERSION:
        errors.append(f"{prefix}.schema_version must be {HANDOFF_SCHEMA_VERSION}")
    if handoff.get("handoff_mode") != "external_runner_required":
        errors.append(f"{prefix}.handoff_mode must be external_runner_required")
    if handoff.get("review_only") is not True:
        errors.append(f"{prefix}.review_only must be true")
    source = as_obj(handoff.get("source"))
    outbox_source = as_obj(outbox.get("source"))
    if source.get("session_id") != outbox_source.get("session_id"):
        errors.append(f"{prefix}.source.session_id must match outbox source")
    if source.get("run_id") != outbox_source.get("run_id"):
        errors.append(f"{prefix}.source.run_id must match outbox source")
    schedule_item_id = source.get("schedule_item_id")
    authorization_ref = source.get("authorization_ref")
    runner_inputs = as_obj(handoff.get("runner_inputs"))
    executor_request = as_obj(runner_inputs.get("executor_request"))
    executor_source = as_obj(executor_request.get("source"))
    authorization = as_obj(runner_inputs.get("provider_execution_authorization"))
    if executor_source.get("schedule_item_id") != schedule_item_id:
        errors.append(f"{prefix}.runner_inputs.executor_request.source.schedule_item_id must match source")
    if authorization.get("authorization_ref") != authorization_ref:
        errors.append(f"{prefix}.runner_inputs.provider_execution_authorization.authorization_ref must match source")
    suggested = as_obj(handoff.get("suggested_paths"))
    for key in (
        "executor_request_path",
        "authorization_path",
        "receipt_output_path",
        "envelope_output_path",
        "prompt_file_path",
    ):
        path = suggested.get(key)
        if not isinstance(path, str) or not path.startswith("/tmp/"):
            errors.append(f"{prefix}.suggested_paths.{key} must be a /tmp path")
        if isinstance(path, str) and references_dotenv_path(path):
            errors.append(f"{prefix}.suggested_paths.{key} must not reference .env")
    commands = as_obj(handoff.get("command_templates"))
    dry_run = as_list(commands.get("dry_run_fixture"))
    if "--live" in dry_run:
        errors.append(f"{prefix}.command_templates.dry_run_fixture must not include --live")
    video_boundary = as_list(commands.get("video_boundary"))
    if command_mode(video_boundary) != "video":
        errors.append(f"{prefix}.command_templates.video_boundary must include --mode video")
    if "--live" in video_boundary:
        errors.append(f"{prefix}.command_templates.video_boundary must not include --live")
    if "<authorized-dotenv-path>" in video_boundary:
        errors.append(
            f"{prefix}.command_templates.video_boundary must not require <authorized-dotenv-path>"
        )
    for name in ("live_llm_text", "live_image"):
        command = as_list(commands.get(name))
        if "--live" not in command:
            errors.append(f"{prefix}.command_templates.{name} must include --live")
        if "<authorized-dotenv-path>" not in command:
            errors.append(
                f"{prefix}.command_templates.{name} must require <authorized-dotenv-path>"
            )
    import_after = as_obj(handoff.get("import_after_runner"))
    body = as_obj(import_after.get("body"))
    if body.get("schedule_item_id") != schedule_item_id:
        errors.append(f"{prefix}.import_after_runner.body.schedule_item_id must match source")
    if body.get("authorization_ref") != authorization_ref:
        errors.append(f"{prefix}.import_after_runner.body.authorization_ref must match source")
    if body.get("receipt_path") != suggested.get("receipt_output_path"):
        errors.append(f"{prefix}.import_after_runner.body.receipt_path must match suggested path")
    if body.get("envelope_path") != suggested.get("envelope_output_path"):
        errors.append(f"{prefix}.import_after_runner.body.envelope_path must match suggested path")
    safety = as_obj(handoff.get("safety"))
    for key in (
        "api_reads_env",
        "api_calls_provider",
        "api_writes_world_state",
        "api_activates_runtime",
        "prompt_body_included",
        "provider_response_body_included",
    ):
        if safety.get(key) is not False:
            errors.append(f"{prefix}.safety.{key} must be false")
    if safety.get("live_templates_require_external_explicit_authorization") is not True:
        errors.append(
            f"{prefix}.safety.live_templates_require_external_explicit_authorization must be true"
        )


def validate_provider_adapter_runner_handoff_outbox(outbox: dict[str, Any]) -> list[str]:
    errors = validate_json_schema(outbox, SCHEMA_PATH)
    scan_forbidden(outbox, errors)
    check_outbox_safety(outbox, errors)
    check_import_contract(outbox, errors)
    handoffs = [item for item in as_list(outbox.get("runner_handoffs")) if isinstance(item, dict)]
    if outbox.get("runner_handoff_count") != len(handoffs):
        errors.append("runner_handoff_count must match runner_handoffs length")
    source = as_obj(outbox.get("source"))
    if source.get("dispatched_count", 0) < len(handoffs):
        errors.append("source.dispatched_count must be >= runner_handoff_count")
    seen_schedule_items: set[str] = set()
    for index, handoff in enumerate(handoffs):
        schedule_item_id = str(as_obj(handoff.get("source")).get("schedule_item_id") or "")
        if schedule_item_id in seen_schedule_items:
            errors.append(f"duplicate schedule_item_id in runner_handoffs: {schedule_item_id}")
        seen_schedule_items.add(schedule_item_id)
        check_handoff(outbox, handoff, index, errors)
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("outbox", type=Path)
    args = parser.parse_args()
    outbox = load_json(args.outbox)
    if not isinstance(outbox, dict):
        print("ProviderAdapterRunnerHandoffOutbox root must be an object", file=sys.stderr)
        return 1
    errors = validate_provider_adapter_runner_handoff_outbox(outbox)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"ProviderAdapterRunnerHandoffOutbox validation passed: {args.outbox}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
