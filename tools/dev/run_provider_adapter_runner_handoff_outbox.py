#!/usr/bin/env python3
"""Consume a ProviderAdapterRunnerHandoffOutbox with the local provider runner.

Default execution is fixture dry-run only: it writes each handoff's sanitized
executor request and authorization to a local output directory, runs
tools/provider_adapter/run_provider_adapter.py, and emits a compact execution
report. It does not import outputs back into the backend, stage artifacts,
promote artifacts, write world state, activate runtime, read .env, or call
providers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
TOOLS_DEV_DIR = ROOT / "tools" / "dev"
if str(TOOLS_DEV_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DEV_DIR))

from validate_provider_adapter_execution_receipt import (  # noqa: E402
    validate_provider_adapter_execution_receipt,
)
from validate_provider_adapter_runner_handoff_outbox import (  # noqa: E402
    validate_provider_adapter_runner_handoff_outbox,
)
from validate_provider_output_envelope import (  # noqa: E402
    validate_provider_output_envelope,
)


DEFAULT_OUTPUT_DIR = Path("/tmp/ai_td_provider_runner_handoff_outbox")
REPORT_NAME = "provider_adapter_runner_handoff_outbox_execution_report.v0.1.json"
MAX_OUTPUT_TAIL = 1600


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} root must be an object")
    return data


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_ref(path: Path, role: str) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(path),
            "role": role,
            "exists": False,
        }
    return {
        "path": str(path),
        "role": role,
        "exists": True,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def short_tail(value: str, limit: int = MAX_OUTPUT_TAIL) -> str:
    normalized = value.replace(str(ROOT), "$REPO_ROOT").strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[-limit:]


def safe_slug(*parts: str) -> str:
    raw = "_".join(part for part in parts if part)
    slug = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in raw)
    return slug[:120] or "provider_runner_handoff"


def validate_or_raise(label: str, errors: list[str]) -> None:
    if errors:
        raise ValueError(f"{label} validation failed: " + "; ".join(errors))


def command_for_handoff(
    *,
    args: argparse.Namespace,
    executor_request_path: Path,
    authorization_path: Path,
    receipt_path: Path,
    envelope_path: Path,
    created_at: str,
    note: str,
) -> list[str]:
    command = [
        str(args.python),
        "tools/provider_adapter/run_provider_adapter.py",
        "--executor-request",
        str(executor_request_path),
        "--authorization",
        str(authorization_path),
        "--receipt-output",
        str(receipt_path),
        "--envelope-output",
        str(envelope_path),
        "--created-at",
        created_at,
        "--note",
        note,
        "--mode",
        args.adapter_mode,
    ]
    return command


def run_command(command: list[str], timeout_seconds: int) -> dict[str, Any]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        return {
            "command": " ".join(command),
            "return_code": completed.returncode,
            "status": "passed" if completed.returncode == 0 else "failed",
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "stdout_tail": short_tail(completed.stdout),
            "stderr_tail": short_tail(completed.stderr),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": " ".join(command),
            "return_code": 124,
            "status": "failed",
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "stdout_tail": short_tail(exc.stdout or ""),
            "stderr_tail": short_tail((exc.stderr or "") + "\ncommand timed out"),
        }


def receipt_summary(receipt: dict[str, Any] | None) -> dict[str, Any]:
    if not receipt:
        return {"status": "missing"}
    execution = as_obj(receipt.get("execution"))
    safety = as_obj(receipt.get("adapter_safety"))
    source = as_obj(receipt.get("source"))
    return {
        "status": execution.get("status"),
        "mode": execution.get("mode"),
        "finish_reason": execution.get("finish_reason"),
        "schedule_item_id": source.get("schedule_item_id"),
        "authorization_ref": source.get("authorization_ref"),
        "calls_provider": safety.get("calls_provider"),
        "reads_env": safety.get("reads_env"),
        "writes_world_state": safety.get("writes_world_state"),
        "activates_runtime": safety.get("activates_runtime"),
    }


def envelope_summary(envelope: dict[str, Any] | None) -> dict[str, Any]:
    if not envelope:
        return {"status": "missing"}
    provider_call = as_obj(envelope.get("provider_call"))
    result = as_obj(envelope.get("result"))
    validation = as_obj(envelope.get("validation_summary"))
    authority = as_obj(envelope.get("authority"))
    return {
        "envelope_id": envelope.get("envelope_id"),
        "provider_call_performed": provider_call.get("provider_call_performed"),
        "finish_reason": provider_call.get("finish_reason"),
        "result_kind": result.get("result_kind"),
        "artifact_ref_count": len(as_list(result.get("artifact_refs"))),
        "validation_status": validation.get("status"),
        "runtime_activation_allowed": authority.get("runtime_activation_allowed"),
        "world_mutation_allowed": authority.get("world_mutation_allowed"),
    }


def execute_handoff(
    *,
    args: argparse.Namespace,
    handoff: dict[str, Any],
    index: int,
    output_dir: Path,
    created_at: str,
) -> dict[str, Any]:
    source = as_obj(handoff.get("source"))
    schedule_item_id = str(source.get("schedule_item_id") or f"handoff_{index}")
    authorization_ref = str(source.get("authorization_ref") or f"auth_{index}")
    slug = safe_slug(f"{index:02d}", schedule_item_id, authorization_ref)
    runner_inputs = as_obj(handoff.get("runner_inputs"))
    executor_request = as_obj(runner_inputs.get("executor_request"))
    authorization = as_obj(runner_inputs.get("provider_execution_authorization"))

    input_dir = output_dir / "runner_inputs"
    artifact_dir = output_dir / "runner_outputs"
    executor_request_path = input_dir / f"{slug}.executor_request.json"
    authorization_path = input_dir / f"{slug}.authorization.json"
    receipt_path = artifact_dir / f"{slug}.receipt.json"
    envelope_path = artifact_dir / f"{slug}.envelope.json"
    write_json(executor_request_path, executor_request)
    write_json(authorization_path, authorization)

    command = command_for_handoff(
        args=args,
        executor_request_path=executor_request_path,
        authorization_path=authorization_path,
        receipt_path=receipt_path,
        envelope_path=envelope_path,
        created_at=created_at,
        note=f"outbox consumer dry boundary for {schedule_item_id}",
    )
    command_result = run_command(command, args.command_timeout)

    receipt: dict[str, Any] | None = None
    envelope: dict[str, Any] | None = None
    validation_errors: list[str] = []
    if receipt_path.exists():
        receipt = load_json(receipt_path)
        validation_errors.extend(
            f"receipt:{error}"
            for error in validate_provider_adapter_execution_receipt(receipt)
        )
    else:
        validation_errors.append("receipt:missing")
    if envelope_path.exists():
        envelope = load_json(envelope_path)
        validation_errors.extend(
            f"envelope:{error}" for error in validate_provider_output_envelope(envelope)
        )
    else:
        validation_errors.append("envelope:missing")

    import_body = dict(as_obj(as_obj(handoff.get("import_after_runner")).get("body")))
    import_body.update(
        {
            "schedule_item_id": schedule_item_id,
            "authorization_ref": authorization_ref,
            "receipt_path": str(receipt_path),
            "envelope_path": str(envelope_path),
        }
    )
    status = (
        "passed"
        if command_result.get("status") == "passed" and not validation_errors
        else "failed"
    )
    return {
        "index": index,
        "status": status,
        "schedule_item_id": schedule_item_id,
        "authorization_ref": authorization_ref,
        "adapter_mode": args.adapter_mode,
        "live": False,
        "command_result": command_result,
        "input_refs": {
            "executor_request": file_ref(executor_request_path, "executor_request"),
            "authorization": file_ref(authorization_path, "provider_authorization"),
        },
        "output_refs": {
            "receipt": file_ref(receipt_path, "provider_adapter_execution_receipt"),
            "envelope": file_ref(envelope_path, "provider_output_envelope"),
        },
        "receipt_summary": receipt_summary(receipt),
        "envelope_summary": envelope_summary(envelope),
        "validation_errors": validation_errors,
        "import_after_runner": {
            "not_performed_by_this_tool": True,
            "method": "POST",
            "endpoint": as_obj(handoff.get("import_after_runner")).get("endpoint"),
            "body": import_body,
            "post_import_gate": "provider_artifact_staging_or_promotion_review_required",
        },
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    outbox = load_json(args.outbox)
    validate_or_raise(
        "ProviderAdapterRunnerHandoffOutbox",
        validate_provider_adapter_runner_handoff_outbox(outbox),
    )
    output_dir = args.output_dir.expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    created_at = args.generated_at or now_iso()
    handoffs = [
        item for item in as_list(outbox.get("runner_handoffs")) if isinstance(item, dict)
    ]
    if args.limit is not None:
        handoffs = handoffs[: args.limit]
    executions = [
        execute_handoff(
            args=args,
            handoff=handoff,
            index=index,
            output_dir=output_dir,
            created_at=created_at,
        )
        for index, handoff in enumerate(handoffs)
    ]
    failed = [item for item in executions if item.get("status") != "passed"]
    provider_call_count = sum(
        1
        for item in executions
        if as_obj(item.get("receipt_summary")).get("calls_provider") is True
        or as_obj(item.get("envelope_summary")).get("provider_call_performed") is True
    )
    reads_env_count = sum(
        1
        for item in executions
        if as_obj(item.get("receipt_summary")).get("reads_env") is True
    )
    runtime_activation_allowed_count = sum(
        1
        for item in executions
        if as_obj(item.get("envelope_summary")).get("runtime_activation_allowed") is True
        or as_obj(item.get("receipt_summary")).get("activates_runtime") is True
    )
    world_mutation_allowed_count = sum(
        1
        for item in executions
        if as_obj(item.get("envelope_summary")).get("world_mutation_allowed") is True
        or as_obj(item.get("receipt_summary")).get("writes_world_state") is True
    )
    return {
        "schema_version": "provider_adapter_runner_handoff_outbox_execution_report.v0.1",
        "status": "passed" if not failed else "failed",
        "generated_at": created_at,
        "source_outbox": file_ref(args.outbox, "provider_adapter_runner_handoff_outbox"),
        "adapter_mode": args.adapter_mode,
        "live": False,
        "runner_handoff_count": len(handoffs),
        "executed_count": len(executions),
        "passed_count": len(executions) - len(failed),
        "failed_count": len(failed),
        "executions": executions,
        "safety_summary": {
            "reads_env_count": reads_env_count,
            "provider_call_count": provider_call_count,
            "imports_to_backend_count": 0,
            "staging_count": 0,
            "promotion_count": 0,
            "queue_complete_count": 0,
            "world_mutation_allowed_count": world_mutation_allowed_count,
            "runtime_activation_allowed_count": runtime_activation_allowed_count,
            "stores_prompt_body": False,
            "stores_provider_response_body": False,
        },
        "limitations": [
            "This tool consumes an outbox and runs local provider adapter dry boundaries only.",
            "It does not import outputs back into the backend; use import_after_runner after review.",
            "It does not stage, promote, complete queue items, write world state, or activate runtime.",
            "Live llm_text/image execution remains outside this v0.1 consumer.",
        ],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("outbox", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--report-output",
        type=Path,
        help=f"默认写到 output dir 下的 {REPORT_NAME}。",
    )
    parser.add_argument(
        "--adapter-mode",
        choices=("fixture", "video"),
        default="fixture",
        help="v0.1 consumer 只执行离线 fixture 或 video boundary。",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--command-timeout", type=int, default=90)
    parser.add_argument("--generated-at", default=None)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    report = build_report(args)
    report_output = args.report_output or args.output_dir / REPORT_NAME
    write_json(report_output, report)
    print(f"provider runner outbox consumer {report['status']}: {report_output}")
    print(
        "- executed "
        f"{report['passed_count']} / {report['executed_count']} handoffs "
        f"with mode {report['adapter_mode']}"
    )
    safety = as_obj(report.get("safety_summary"))
    print(
        "- provider calls: "
        f"{safety.get('provider_call_count')}, runtime activation: "
        f"{safety.get('runtime_activation_allowed_count')}"
    )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
