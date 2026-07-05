"""Pure builders for Generation Scheduler provider runner handoffs.

These helpers intentionally avoid database access, provider calls, environment
reads, and runtime activation. The scheduler service owns state transitions;
this module only builds review-only handoff payloads.
"""

from __future__ import annotations

from typing import Any


def safe_runner_handoff_slug(*parts: str) -> str:
    raw = "_".join(part for part in parts if part)
    slug = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in raw)
    return slug[:120] or "provider_runner_handoff"


def build_runner_handoff_paths(slug: str) -> dict[str, str]:
    return {
        "executor_request_path": f"/tmp/{slug}.executor_request.json",
        "authorization_path": f"/tmp/{slug}.authorization.json",
        "receipt_output_path": f"/tmp/{slug}.receipt.json",
        "envelope_output_path": f"/tmp/{slug}.envelope.json",
        "llm_summary_artifact_path": f"/tmp/{slug}.redacted_text_summary.json",
        "image_artifact_path": f"/tmp/{slug}.image_candidate.png",
        "prompt_file_path": f"/tmp/{slug}.prompt.txt",
    }


def provider_runner_outbox_safety() -> dict[str, bool]:
    return {
        "api_reads_env": False,
        "api_calls_provider": False,
        "api_runs_provider_adapter": False,
        "api_stages_provider_artifacts": False,
        "api_promotes_provider_artifacts": False,
        "api_completes_queue_items": False,
        "api_writes_world_state": False,
        "api_activates_runtime": False,
        "prompt_body_included": False,
        "provider_response_body_included": False,
        "live_templates_require_external_explicit_authorization": True,
    }


def build_provider_adapter_runner_handoff(
    *,
    session_id: str,
    run_id: str,
    schedule_item_id: str,
    authorization_ref: str,
    executor_request_id: Any,
    executor_request: dict[str, Any],
    authorization: dict[str, Any],
    provider_profile: str,
    created_at: str,
    note: Any = None,
) -> dict[str, Any]:
    slug = safe_runner_handoff_slug(schedule_item_id, authorization_ref)
    paths = build_runner_handoff_paths(slug)
    base_args = [
        "python3",
        "tools/provider_adapter/run_provider_adapter.py",
        "--executor-request",
        paths["executor_request_path"],
        "--authorization",
        paths["authorization_path"],
        "--receipt-output",
        paths["receipt_output_path"],
        "--envelope-output",
        paths["envelope_output_path"],
        "--created-at",
        created_at,
    ]
    if note:
        base_args.extend(["--note", str(note)])
    dry_run_args = [*base_args, "--mode", "fixture"]
    video_boundary_args = [*base_args, "--mode", "video"]
    live_llm_args = [
        *base_args,
        "--mode",
        "llm_text",
        "--live",
        "--llm-profile",
        provider_profile if provider_profile != "unknown" else "<llm-profile>",
        "--prompt-file",
        paths["prompt_file_path"],
        "--artifact-output",
        paths["llm_summary_artifact_path"],
        "--max-tokens",
        "4096",
        "--load-dotenv",
        "<authorized-dotenv-path>",
    ]
    live_image_args = [
        *base_args,
        "--mode",
        "image",
        "--live",
        "--image-profile",
        provider_profile if provider_profile != "unknown" else "<image-profile>",
        "--prompt-file",
        paths["prompt_file_path"],
        "--artifact-output",
        paths["image_artifact_path"],
        "--size",
        "1024x1024",
        "--load-dotenv",
        "<authorized-dotenv-path>",
    ]
    return {
        "schema_version": "provider_adapter_runner_handoff.v0.1",
        "created_at": created_at,
        "handoff_mode": "external_runner_required",
        "review_only": True,
        "source": {
            "session_id": session_id,
            "run_id": run_id,
            "schedule_item_id": schedule_item_id,
            "authorization_ref": authorization_ref,
            "executor_request_id": executor_request_id,
            "provider_profile": provider_profile,
        },
        "runner_inputs": {
            "executor_request": executor_request,
            "provider_execution_authorization": authorization,
        },
        "suggested_paths": paths,
        "command_templates": {
            "dry_run_fixture": dry_run_args,
            "video_boundary": video_boundary_args,
            "live_llm_text": live_llm_args,
            "live_image": live_image_args,
        },
        "import_after_runner": {
            "endpoint": (
                f"/api/sessions/{session_id}/generation-schedule/workers/"
                "import-provider-adapter-runner-output"
            ),
            "method": "POST",
            "body": {
                "worker_id": "provider-runner-output-import",
                "schedule_item_id": schedule_item_id,
                "authorization_ref": authorization_ref,
                "receipt_path": paths["receipt_output_path"],
                "envelope_path": paths["envelope_output_path"],
            },
        },
        "safety": {
            "api_reads_env": False,
            "api_calls_provider": False,
            "api_writes_world_state": False,
            "api_activates_runtime": False,
            "prompt_body_included": False,
            "provider_response_body_included": False,
            "live_templates_require_external_explicit_authorization": True,
        },
    }


def build_provider_adapter_runner_handoff_outbox(
    *,
    session_id: str,
    run_id: str,
    worker_id: str,
    max_items: int,
    dispatched_count: int,
    stop_reason: Any,
    runner_handoffs: list[dict[str, Any]],
    created_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": "provider_adapter_runner_handoff_outbox.v0.1",
        "outbox_id": safe_runner_handoff_slug(
            "provider_adapter_runner_handoff_outbox",
            run_id or "no_run",
            worker_id,
        ),
        "created_at": created_at,
        "handoff_mode": "external_runner_required",
        "review_only": True,
        "source": {
            "session_id": session_id,
            "run_id": run_id,
            "worker_mode": "review_only_background_handoff_tick",
            "max_items": max_items,
            "dispatched_count": dispatched_count,
            "stop_reason": stop_reason,
        },
        "safety": provider_runner_outbox_safety(),
        "runner_handoff_count": len(runner_handoffs),
        "runner_handoffs": runner_handoffs,
        "import_contract": {
            "endpoint": (
                "/api/sessions/{session_id}/generation-schedule/workers/"
                "import-provider-adapter-runner-output"
            ),
            "method": "POST",
            "required_body_fields": [
                "schedule_item_id",
                "authorization_ref",
                "receipt_path",
                "envelope_path",
            ],
            "post_import_gate": "provider_artifact_staging_or_promotion_review_required",
        },
    }
