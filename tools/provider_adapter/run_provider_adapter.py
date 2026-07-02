#!/usr/bin/env python3
"""Run a guarded provider adapter and emit redacted review-only artifacts.

Default mode is deterministic dry-run and does not call providers or read `.env`.
Live mode is intentionally explicit and still writes only a
ProviderAdapterExecutionReceipt plus a redacted ProviderOutputEnvelope.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
TOOLS_DEV_DIR = ROOT / "tools" / "dev"
LLM_DIR = ROOT / "tools" / "llm"
if str(TOOLS_DEV_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DEV_DIR))
if str(LLM_DIR) not in sys.path:
    sys.path.insert(0, str(LLM_DIR))

from validate_generation_executor_run_request import (  # noqa: E402
    validate_generation_executor_run_request,
)
from validate_provider_adapter_execution_receipt import (  # noqa: E402
    validate_provider_adapter_execution_receipt,
)
from validate_provider_execution_authorization import (  # noqa: E402
    validate_provider_execution_authorization,
)
from validate_provider_output_envelope import validate_provider_output_envelope  # noqa: E402


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} root must be an object")
    return data


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repo_rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def validate_or_raise(kind: str, errors: list[str]) -> None:
    if errors:
        raise ValueError(f"{kind} validation failed: " + "; ".join(errors))


def require_input_alignment(
    request: dict[str, Any],
    authorization: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], str]:
    validate_or_raise(
        "GenerationExecutorRunRequest",
        validate_generation_executor_run_request(request),
    )
    validate_or_raise(
        "ProviderExecutionAuthorization",
        validate_provider_execution_authorization(authorization),
    )
    request_source = as_obj(request.get("source"))
    auth_source = as_obj(authorization.get("source"))
    request_id = str(request.get("request_id") or "")
    auth_ref = str(authorization.get("authorization_ref") or "")
    checks = {
        "executor_request_id": auth_source.get("executor_request_id") == request_id,
        "schedule_item_id": auth_source.get("schedule_item_id")
        == request_source.get("schedule_item_id"),
        "object_kind": auth_source.get("object_kind") == request_source.get("object_kind"),
        "object_ref": auth_source.get("object_ref") == request_source.get("object_ref"),
        "guard_id": auth_source.get("guard_id") == request_source.get("guard_id"),
    }
    failed = [key for key, passed in checks.items() if not passed]
    if failed:
        raise ValueError("executor request and authorization mismatch: " + ", ".join(failed))
    if not auth_ref:
        raise ValueError("authorization_ref is required")
    return request_source, auth_source, auth_ref


def result_kind_from_request(request: dict[str, Any]) -> str:
    requested = as_obj(request.get("requested_output"))
    result_kind = requested.get("result_kind")
    if isinstance(result_kind, str) and result_kind:
        return result_kind
    return "mixed_candidate"


def artifact_ref(path: Path, *, artifact_id: str, kind: str) -> dict[str, Any]:
    return {
        "artifact_id": artifact_id,
        "kind": kind,
        "path": repo_rel(path),
        "sha256": sha256_file(path),
        "byte_size": path.stat().st_size,
        "content_type": "application/json",
        "media_layer": "processed_media",
    }


def compact_input_refs(request: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for ref in as_list(request.get("input_refs")) + as_list(request.get("context_refs")):
        if not isinstance(ref, dict):
            continue
        path = ref.get("path")
        kind = ref.get("kind")
        artifact_id = ref.get("artifact_id") or ref.get("ref_id")
        if not isinstance(path, str) or not path:
            continue
        refs.append(
            {
                "artifact_id": str(artifact_id or Path(path).stem),
                "kind": str(kind or "context_ref"),
                "path": path,
            }
        )
    return refs


def build_receipt(
    *,
    request_source: dict[str, Any],
    auth_source: dict[str, Any],
    authorization_ref: str,
    status: str,
    mode: str,
    performed: bool,
    created_at: str,
    worker_id: str,
    note: str | None,
    request_digest: str | None,
    result_digest: str | None,
    finish_reason: str | None,
    redacted_summary: str,
) -> dict[str, Any]:
    schedule_item_id = str(auth_source.get("schedule_item_id") or "")
    safe_item_id = "".join(
        ch if ch.isalnum() or ch in {"_", "-"} else "_"
        for ch in schedule_item_id
    )
    return {
        "schema_version": "provider_adapter_execution_receipt.v0.1",
        "execution_receipt_id": f"padapter_{safe_item_id}_runner_001",
        "created_at": created_at,
        "source": {
            "session_id": auth_source.get("session_id"),
            "run_id": auth_source.get("run_id"),
            "schedule_item_id": schedule_item_id,
            "object_kind": auth_source.get("object_kind"),
            "object_ref": auth_source.get("object_ref"),
            "executor_request_id": auth_source.get("executor_request_id"),
            "authorization_ref": authorization_ref,
            "guard_id": auth_source.get("guard_id"),
            "provider_mode": auth_source.get("provider_mode"),
            "provider_profile": auth_source.get("provider_profile"),
            "worker_id": worker_id,
            "note": note,
        },
        "authority": {
            "visibility": "internal_evidence",
            "review_only": True,
            "provider_adapter_boundary_entered": True,
            "runtime_activation_allowed": False,
            "world_mutation_allowed": False,
            "player_visible": False,
        },
        "execution": {
            "status": status,
            "mode": mode,
            "authorization_ref": authorization_ref,
            "provider_call_performed_by_receipt_builder": performed,
            "requires_provider_output_envelope": True,
            "request_digest": request_digest,
            "result_digest": result_digest,
            "finish_reason": finish_reason,
            "redacted_summary": redacted_summary,
        },
        "output_contract": {
            "must_write_provider_output_envelope": True,
            "allowed_result_storage": "provider_output_envelope_redacted_only",
            "temporary_url_policy": "download_then_local_ref_only",
            "required_next_gates": [
                "provider_output_envelope",
                "local_artifact_staging_manifest",
                "schema_or_media_validation",
                "semantic_gate",
                "human_review",
                "promotion_report",
            ],
        },
        "retention_policy": {
            "prompt_body_storage": "forbidden",
            "provider_body_storage": "forbidden",
            "secret_storage": "forbidden",
            "temporary_url_policy": "download_then_local_ref_only",
            "executor_result_storage": "provider_output_envelope_redacted_only",
        },
        "adapter_safety": {
            "reads_env": performed,
            "calls_provider": performed,
            "stores_prompt_body": False,
            "stores_provider_body": False,
            "writes_world_state": False,
            "activates_runtime": False,
        },
    }


def gate(status: str, notes: list[str]) -> dict[str, Any]:
    return {
        "status": status,
        "required_before_activation": True,
        "report_ref": None,
        "notes": notes,
    }


def build_envelope(
    *,
    request: dict[str, Any],
    request_source: dict[str, Any],
    auth_source: dict[str, Any],
    authorization_ref: str,
    created_at: str,
    provider_call_status: str,
    provider_performed: bool,
    authorization_granted: bool,
    result_status: str,
    result_summary: str,
    result_kind: str,
    result_digest: str | None,
    finish_reason: str | None,
    output_refs: list[dict[str, Any]],
    request_digest: str | None,
) -> dict[str, Any]:
    artifacts_ready = bool(output_refs)
    return {
        "schema_version": "provider_output_envelope.v0.1",
        "envelope_id": f"pout_{authorization_ref}_runner_001",
        "created_at": created_at,
        "source": {
            "run_id": auth_source.get("run_id"),
            "schedule_item_id": auth_source.get("schedule_item_id"),
            "object_kind": auth_source.get("object_kind"),
            "object_ref": auth_source.get("object_ref"),
            "provider_profile": auth_source.get("provider_profile"),
            "provider_mode": auth_source.get("provider_mode"),
            "worker_id": "provider_adapter_runner",
            "guard_id": auth_source.get("guard_id"),
        },
        "authority": {
            "visibility": "internal_evidence",
            "review_only": True,
            "runtime_activation_allowed": False,
            "world_mutation_allowed": False,
            "player_visible": False,
        },
        "provider_call": {
            "status": provider_call_status,
            "performed": provider_performed,
            "authorization_required": True,
            "authorization_granted": authorization_granted,
            "authorization_ref": authorization_ref if provider_performed else None,
            "attempt_count": as_obj(request.get("execution_budget")).get("attempt_count", 0),
            "max_attempts": as_obj(request.get("execution_budget")).get("max_attempts", 0),
        },
        "retention_policy": {
            "prompt_body_storage": "forbidden",
            "provider_body_storage": "forbidden",
            "secret_storage": "forbidden",
            "temporary_url_policy": "download_then_local_ref_only",
        },
        "redacted_request_summary": {
            "intent_class": as_obj(request.get("requested_output")).get(
                "intent_class",
                "provider_adapter_runner",
            ),
            "input_refs": compact_input_refs(request),
            "policy_notes": [
                "Only local refs, digests, and redacted summaries are retained.",
                "Prompt bodies and provider response bodies are forbidden.",
            ],
            "request_digest": request_digest,
        },
        "redacted_result_summary": {
            "result_kind": result_kind,
            "status": result_status,
            "summary": result_summary,
            "result_digest": result_digest,
            "finish_reason": finish_reason,
        },
        "artifact_manifest": {
            "status": "review_only_artifacts_ready"
            if artifacts_ready
            else "not_created",
            "output_refs": output_refs,
            "review_only": True,
            "notes": [
                "Artifacts remain internal evidence and require staging, validation, review, and promotion."
            ]
            if artifacts_ready
            else ["No provider call or artifact was created in dry-run mode."],
        },
        "validation": {
            "schema_gate": gate(
                "not_run" if artifacts_ready else "not_run",
                ["Schema validation waits for staging and downstream validators."],
            ),
            "semantic_gate": gate(
                "not_run",
                ["Semantic review is required before promotion."],
            ),
            "media_gate": gate(
                "not_run",
                ["Media review is required before promotion."],
            ),
            "human_review": gate(
                "not_run",
                ["Human or visual review is required before promotion."],
            ),
        },
        "activation_gate": {
            "activation_allowed": False,
            "blocked_reason": "promotion_required"
            if artifacts_ready
            else "provider_call_not_performed",
            "required_next_gates": [
                "artifact_staging_manifest",
                "media_gate",
                "semantic_gate",
                "human_review",
                "promotion_report",
            ],
        },
    }


def build_dry_run_artifacts(
    request: dict[str, Any],
    authorization: dict[str, Any],
    *,
    created_at: str,
    note: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    request_source, auth_source, auth_ref = require_input_alignment(request, authorization)
    receipt = build_receipt(
        request_source=request_source,
        auth_source=auth_source,
        authorization_ref=auth_ref,
        status="fixture_output_ready_for_envelope",
        mode="fixture_backed_no_provider_call",
        performed=False,
        created_at=created_at,
        worker_id="provider_adapter_runner",
        note=note,
        request_digest=None,
        result_digest=None,
        finish_reason="dry_run",
        redacted_summary=(
            "Dry-run provider adapter boundary recorded. No provider call was performed."
        ),
    )
    envelope = build_envelope(
        request=request,
        request_source=request_source,
        auth_source=auth_source,
        authorization_ref=auth_ref,
        created_at=created_at,
        provider_call_status="not_performed_guarded",
        provider_performed=False,
        authorization_granted=False,
        result_status="blocked_before_provider_call",
        result_summary="Dry-run mode blocked the provider call and produced no candidate artifact.",
        result_kind="none",
        result_digest=None,
        finish_reason=None,
        output_refs=[],
        request_digest=None,
    )
    return receipt, envelope


def run_live_llm(
    request: dict[str, Any],
    authorization: dict[str, Any],
    *,
    profile_name: str,
    prompt_path: Path,
    artifact_output: Path,
    created_at: str,
    max_tokens: int,
    timeout: int,
    load_dotenv_path: Path | None,
    note: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    from adapter import (  # noqa: WPS433
        PROFILES,
        chat_completion,
        extract_content_from_response,
        load_dotenv,
    )

    request_source, auth_source, auth_ref = require_input_alignment(request, authorization)
    if profile_name not in PROFILES:
        raise ValueError(f"unknown llm profile: {profile_name}")
    if load_dotenv_path is not None:
        load_dotenv(load_dotenv_path)
    prompt = prompt_path.read_text(encoding="utf-8")
    request_digest = sha256_text(prompt)
    messages = [
        {
            "role": "system",
            "content": (
                "You are a game asset compiler adapter. Return concise structured content. "
                "The caller will store only redacted summaries and digests."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    response = chat_completion(
        PROFILES[profile_name],
        messages,
        max_tokens=max_tokens,
        timeout=timeout,
    )
    content = extract_content_from_response(response)
    result_digest = sha256_text(content)
    summary = {
        "schema_version": "provider_adapter_redacted_text_summary.v0.1",
        "created_at": created_at,
        "provider_profile": profile_name,
        "result_kind": result_kind_from_request(request),
        "content_sha256": result_digest,
        "content_char_count": len(content),
        "finish_reason": as_list(response.get("choices"))[0].get("finish_reason")
        if as_list(response.get("choices")) and isinstance(as_list(response.get("choices"))[0], dict)
        else None,
        "retention_policy": {
            "prompt_body_storage": "forbidden",
            "provider_body_storage": "forbidden",
            "secret_storage": "forbidden",
        },
    }
    write_json(artifact_output, summary)
    output_ref = artifact_ref(
        artifact_output,
        artifact_id=f"redacted_text_summary_{auth_ref}",
        kind="json_candidate",
    )
    receipt = build_receipt(
        request_source=request_source,
        auth_source=auth_source,
        authorization_ref=auth_ref,
        status="performed_redacted_live",
        mode="live_redacted_provider_call",
        performed=True,
        created_at=created_at,
        worker_id="provider_adapter_runner",
        note=note,
        request_digest=request_digest,
        result_digest=result_digest,
        finish_reason=summary["finish_reason"] or "completed",
        redacted_summary=(
            "Live LLM provider call completed; only digest, counts, and local summary refs were retained."
        ),
    )
    envelope = build_envelope(
        request=request,
        request_source=request_source,
        auth_source=auth_source,
        authorization_ref=auth_ref,
        created_at=created_at,
        provider_call_status="performed_redacted",
        provider_performed=True,
        authorization_granted=True,
        result_status="candidate_ready_for_validation",
        result_summary="Live LLM provider call completed and produced a redacted local summary artifact.",
        result_kind=result_kind_from_request(request),
        result_digest=result_digest,
        finish_reason=summary["finish_reason"] or "completed",
        output_refs=[output_ref],
        request_digest=request_digest,
    )
    return receipt, envelope


def validate_outputs(receipt: dict[str, Any], envelope: dict[str, Any]) -> None:
    validate_or_raise(
        "ProviderAdapterExecutionReceipt",
        validate_provider_adapter_execution_receipt(receipt),
    )
    validate_or_raise(
        "ProviderOutputEnvelope",
        validate_provider_output_envelope(envelope),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executor-request", required=True, type=Path)
    parser.add_argument("--authorization", required=True, type=Path)
    parser.add_argument("--receipt-output", required=True, type=Path)
    parser.add_argument("--envelope-output", required=True, type=Path)
    parser.add_argument("--artifact-output", type=Path)
    parser.add_argument("--created-at", default=None)
    parser.add_argument("--note", default=None)
    parser.add_argument(
        "--mode",
        choices=("fixture", "llm_text"),
        default="fixture",
        help="fixture is offline dry-run; llm_text requires --live.",
    )
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--llm-profile", default="ark_deepseek_v4_flash")
    parser.add_argument("--prompt-file", type=Path)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument(
        "--load-dotenv",
        type=Path,
        default=None,
        help="Explicit dotenv path for live mode only.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    request = load_json(args.executor_request)
    authorization = load_json(args.authorization)
    created_at = args.created_at or now_iso()
    if args.mode == "fixture":
        if args.live:
            raise ValueError("--live is not meaningful with --mode fixture")
        receipt, envelope = build_dry_run_artifacts(
            request,
            authorization,
            created_at=created_at,
            note=args.note,
        )
    else:
        if not args.live:
            raise ValueError("--mode llm_text requires explicit --live")
        if args.prompt_file is None:
            raise ValueError("--prompt-file is required for --mode llm_text")
        if args.artifact_output is None:
            raise ValueError("--artifact-output is required for --mode llm_text")
        receipt, envelope = run_live_llm(
            request,
            authorization,
            profile_name=args.llm_profile,
            prompt_path=args.prompt_file,
            artifact_output=args.artifact_output,
            created_at=created_at,
            max_tokens=args.max_tokens,
            timeout=args.timeout,
            load_dotenv_path=args.load_dotenv,
            note=args.note,
        )
    validate_outputs(receipt, envelope)
    write_json(args.receipt_output, receipt)
    write_json(args.envelope_output, envelope)
    print(
        json.dumps(
            {
                "status": "passed",
                "mode": args.mode,
                "live": args.live,
                "receipt_output": str(args.receipt_output),
                "envelope_output": str(args.envelope_output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
