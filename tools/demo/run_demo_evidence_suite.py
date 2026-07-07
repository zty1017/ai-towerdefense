#!/usr/bin/env python3
"""Run the repeatable MVP demo evidence suite.

This orchestrator intentionally delegates to existing tools:

1. preflight-check the local browser smoke environment;
2. smoke-check the Generation Scheduler review-only pipeline over local HTTP;
3. smoke-check provider runner outbox consume -> import -> prefetch-cache;
4. capture the browser player-flow visual smoke report;
5. capture the browser multinode battle visual smoke report;
6. capture the browser battle drag interaction smoke report;
7. validate those reports;
8. export the redacted demo evidence bundle with the browser flow report attached;
9. write a compact suite report for recording and judge Q&A.

It does not call providers, read .env, mutate world state, or activate runtime
artifacts. It only produces local review/evidence files under the output root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.dev.command_runner import now_iso, run_command


DEFAULT_OUTPUT_ROOT = Path("/tmp/ai_td_demo_evidence_suite")
REPORT_NAME = "demo_evidence_suite_report.v0.1.json"
BROWSER_PREFLIGHT_REPORT_NAME = "browser_smoke_environment_report.v0.1.json"
FRONTEND_REPORT_NAME = "frontend_flow_visual_smoke_report.v0.1.json"
FRONTEND_MULTINODE_REPORT_NAME = "frontend_multinode_visual_smoke_report.v0.1.json"
FRONTEND_BATTLE_DRAG_REPORT_NAME = "battle_drag_interaction_smoke_report.v0.1.json"
SCHEDULER_PIPELINE_REPORT_NAME = "generation_scheduler_review_only_pipeline_smoke_report.v0.1.json"
OUTBOX_IMPORT_REPORT_NAME = "provider_runner_handoff_outbox_import_pipeline_report.v0.1.json"
MAX_OUTPUT_TAIL = 1800
SCHEDULER_SMOKE_RUNNERS = ("auto", "uv", "venv", "current-python")


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
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


def build_capture_command(args: argparse.Namespace, frontend_output: Path) -> list[str]:
    command = [
        sys.executable,
        "tools/frontend/capture_frontend_flow_visual_smoke.py",
        "--output-dir",
        str(frontend_output),
        "--timeout",
        str(args.browser_timeout),
    ]
    if args.browser_bin:
        command.extend(["--browser-bin", str(args.browser_bin)])
    if args.allow_missing_browser:
        command.append("--allow-missing-browser")
    return command


def build_browser_preflight_command(
    args: argparse.Namespace,
    preflight_output: Path,
) -> list[str]:
    command = [
        sys.executable,
        "tools/frontend/check_browser_smoke_environment.py",
        "--output",
        str(preflight_output),
    ]
    if args.browser_bin:
        command.extend(["--browser-bin", str(args.browser_bin)])
    if args.allow_missing_browser:
        command.append("--allow-missing-browser")
    return command


def build_multinode_capture_command(
    args: argparse.Namespace,
    multinode_output: Path,
) -> list[str]:
    command = [
        sys.executable,
        "tools/frontend/capture_frontend_multinode_visual_smoke.py",
        "--output-dir",
        str(multinode_output),
        "--timeout",
        str(args.browser_timeout),
    ]
    if args.browser_bin:
        command.extend(["--browser-bin", str(args.browser_bin)])
    if args.allow_missing_browser:
        command.append("--allow-missing-browser")
    return command


def build_battle_drag_capture_command(
    args: argparse.Namespace,
    battle_drag_output: Path,
) -> list[str]:
    command = [
        sys.executable,
        "tools/frontend/capture_battle_drag_interaction_smoke.py",
        "--output-dir",
        str(battle_drag_output),
        "--timeout",
        str(args.browser_timeout),
    ]
    if args.browser_bin:
        command.extend(["--browser-bin", str(args.browser_bin)])
    if args.allow_missing_browser:
        command.append("--allow-missing-browser")
    return command


def build_python_scheduler_pipeline_smoke_command(
    python_path: Path,
    scheduler_report_path: Path,
) -> list[str]:
    return [
        str(python_path),
        "tools/dev/check_generation_scheduler_review_only_pipeline.py",
        "--output",
        str(scheduler_report_path),
    ]


def build_scheduler_pipeline_smoke_validate_command(
    scheduler_report_path: Path,
) -> list[str]:
    return [
        sys.executable,
        "tools/dev/validate_generation_scheduler_review_only_pipeline_smoke_report.py",
        str(scheduler_report_path),
    ]


def build_python_outbox_import_smoke_command(
    python_path: Path,
    outbox_import_report_path: Path,
) -> list[str]:
    return [
        str(python_path),
        "tools/dev/check_provider_runner_handoff_outbox_import_pipeline.py",
        "--output",
        str(outbox_import_report_path),
    ]


def build_uv_scheduler_pipeline_smoke_command(
    scheduler_report_path: Path,
) -> list[str]:
    return [
        "uv",
        "run",
        "--extra",
        "dev",
        "python",
        "tools/dev/check_generation_scheduler_review_only_pipeline.py",
        "--output",
        str(scheduler_report_path),
    ]


def build_uv_outbox_import_smoke_command(
    outbox_import_report_path: Path,
) -> list[str]:
    return [
        "uv",
        "run",
        "--extra",
        "dev",
        "python",
        "tools/dev/check_provider_runner_handoff_outbox_import_pipeline.py",
        "--output",
        str(outbox_import_report_path),
    ]


def shared_worktree_venv_python() -> Path | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return None
    common_dir_text = result.stdout.strip()
    if not common_dir_text:
        return None
    common_dir = Path(common_dir_text)
    if not common_dir.is_absolute():
        common_dir = (ROOT / common_dir).resolve()
    candidate = common_dir.parent / ".venv" / "bin" / "python"
    return candidate if candidate.exists() else None


def resolve_scheduler_pipeline_smoke_runner(
    args: argparse.Namespace,
) -> tuple[str, Path | None]:
    if args.scheduler_python:
        return ("explicit-python", args.scheduler_python.expanduser())
    if args.scheduler_smoke_runner == "uv":
        return ("uv", None)
    if args.scheduler_smoke_runner == "current-python":
        return ("current-python", Path(sys.executable))

    venv_python = ROOT / ".venv" / "bin" / "python"
    if args.scheduler_smoke_runner == "venv":
        return ("venv", venv_python)
    if venv_python.exists():
        return ("venv", venv_python)
    shared_python = shared_worktree_venv_python()
    if shared_python:
        return ("shared-venv", shared_python)
    return ("uv", None)


def build_scheduler_pipeline_smoke_invocation(
    args: argparse.Namespace,
    scheduler_report_path: Path,
    output_root: Path,
) -> tuple[list[str], dict[str, str], dict[str, Any]]:
    runner, python_path = resolve_scheduler_pipeline_smoke_runner(args)
    if python_path is not None:
        command = build_python_scheduler_pipeline_smoke_command(
            python_path,
            scheduler_report_path,
        )
        return (
            command,
            {},
            {
                "mode": runner,
                "uses_uv": False,
                "python_path": str(python_path),
            },
        )

    command = build_uv_scheduler_pipeline_smoke_command(scheduler_report_path)
    env = {
        "UV_CACHE_DIR": str(output_root / "uv-cache-generation-pipeline-smoke"),
        "UV_PROJECT_ENVIRONMENT": str(
            output_root / "uv-venv-generation-pipeline-smoke"
        ),
    }
    return (
        command,
        env,
        {
            "mode": runner,
            "uses_uv": True,
            "uv_cache_dir": env["UV_CACHE_DIR"],
            "uv_project_environment": env["UV_PROJECT_ENVIRONMENT"],
        },
    )


def build_outbox_import_smoke_invocation(
    args: argparse.Namespace,
    outbox_import_report_path: Path,
    output_root: Path,
) -> tuple[list[str], dict[str, str], dict[str, Any]]:
    runner, python_path = resolve_scheduler_pipeline_smoke_runner(args)
    if python_path is not None:
        command = build_python_outbox_import_smoke_command(
            python_path,
            outbox_import_report_path,
        )
        return (
            command,
            {},
            {
                "mode": runner,
                "uses_uv": False,
                "python_path": str(python_path),
            },
        )

    command = build_uv_outbox_import_smoke_command(outbox_import_report_path)
    env = {
        "UV_CACHE_DIR": str(output_root / "uv-cache-outbox-import-smoke"),
        "UV_PROJECT_ENVIRONMENT": str(output_root / "uv-venv-outbox-import-smoke"),
    }
    return (
        command,
        env,
        {
            "mode": runner,
            "uses_uv": True,
            "uv_cache_dir": env["UV_CACHE_DIR"],
            "uv_project_environment": env["UV_PROJECT_ENVIRONMENT"],
        },
    )


def build_validate_command(
    report_path: Path,
    allow_unavailable: bool,
) -> list[str]:
    command = [
        sys.executable,
        "tools/frontend/validate_frontend_flow_visual_smoke_report.py",
        str(report_path),
    ]
    if allow_unavailable:
        command.append("--allow-unavailable")
    return command


def build_multinode_validate_command(
    report_path: Path,
    allow_unavailable: bool,
) -> list[str]:
    command = [
        sys.executable,
        "tools/frontend/validate_frontend_multinode_visual_smoke_report.py",
        str(report_path),
    ]
    if allow_unavailable:
        command.append("--allow-unavailable")
    return command


def build_battle_drag_validate_command(
    report_path: Path,
    allow_unavailable: bool,
) -> list[str]:
    command = [
        sys.executable,
        "tools/frontend/validate_battle_drag_interaction_smoke_report.py",
        str(report_path),
    ]
    if allow_unavailable:
        command.append("--allow-unavailable")
    return command


def build_export_command(evidence_output: Path, report_path: Path) -> list[str]:
    return [
        sys.executable,
        "tools/demo/export_evidence.py",
        "--output-dir",
        str(evidence_output),
        "--frontend-flow-smoke-report",
        str(report_path),
    ]


def browser_flow_summary(report: dict[str, Any] | None) -> dict[str, Any]:
    if report is None:
        return {
            "status": "missing",
            "captured_screenshot_count": 0,
            "expected_screenshot_count": 0,
            "viewport_count": 0,
            "failure_count": 0,
            "safety_summary": {},
        }
    screenshots = as_list(report.get("screenshots"))
    return {
        "schema_version": report.get("schema_version"),
        "status": report.get("status"),
        "browser_available": report.get("browser_available"),
        "viewport_count": report.get("viewport_count"),
        "captured_screenshot_count": report.get("captured_screenshot_count"),
        "expected_screenshot_count": report.get("expected_screenshot_count"),
        "step_ids": as_list(report.get("step_ids")),
        "screenshot_matrix": [
            f"{item.get('viewport_id')}:{item.get('step_id')}"
            for item in screenshots
            if isinstance(item, dict)
        ],
        "failure_count": len(as_list(report.get("failures"))),
        "safety_summary": as_obj(report.get("safety_summary")),
    }


def browser_multinode_summary(report: dict[str, Any] | None) -> dict[str, Any]:
    if report is None:
        return {
            "status": "missing",
            "captured_screenshot_count": 0,
            "expected_screenshot_count": 0,
            "node_count": 0,
            "viewport_count": 0,
            "failure_count": 0,
            "safety_summary": {},
        }
    screenshots = as_list(report.get("screenshots"))
    return {
        "schema_version": report.get("schema_version"),
        "status": report.get("status"),
        "browser_available": report.get("browser_available"),
        "node_count": len(as_list(report.get("node_ids"))),
        "viewport_count": len(as_list(report.get("viewport_ids"))),
        "captured_screenshot_count": report.get("captured_screenshot_count"),
        "expected_screenshot_count": report.get("expected_screenshot_count"),
        "screenshot_matrix": [
            f"{item.get('node_id')}:{item.get('viewport_id')}"
            for item in screenshots
            if isinstance(item, dict)
        ],
        "failure_count": len(as_list(report.get("failures"))),
        "safety_summary": as_obj(report.get("safety_summary")),
    }


def browser_battle_drag_summary(report: dict[str, Any] | None) -> dict[str, Any]:
    if report is None:
        return {
            "status": "missing",
            "passed_interaction_count": 0,
            "expected_interaction_count": 0,
            "captured_screenshot_count": 0,
            "viewport_count": 0,
            "failure_count": 0,
            "safety_summary": {},
        }
    interactions = as_list(report.get("interactions"))
    return {
        "schema_version": report.get("schema_version"),
        "status": report.get("status"),
        "browser_available": report.get("browser_available"),
        "node_id": report.get("node_id"),
        "tool": report.get("tool"),
        "viewport_count": len(as_list(report.get("viewport_ids"))),
        "passed_interaction_count": report.get("passed_interaction_count"),
        "expected_interaction_count": report.get("expected_interaction_count"),
        "captured_screenshot_count": report.get("captured_screenshot_count"),
        "interaction_matrix": [
            f"{item.get('viewport_id')}:{item.get('status')}"
            for item in interactions
            if isinstance(item, dict)
        ],
        "failure_count": len(as_list(report.get("failures"))),
        "safety_summary": as_obj(report.get("safety_summary")),
    }


def browser_preflight_summary(report: dict[str, Any] | None) -> dict[str, Any]:
    if report is None:
        return {
            "status": "missing",
            "browser_available": False,
            "candidate_count": 0,
            "candidate_path_count": 0,
            "safety_summary": {},
        }
    return {
        "schema_version": report.get("schema_version"),
        "status": report.get("status"),
        "browser_available": report.get("browser_available"),
        "browser_executable": report.get("browser_executable"),
        "candidate_count": report.get("candidate_count"),
        "candidate_path_count": report.get("candidate_path_count"),
        "safety_summary": as_obj(report.get("safety_summary")),
    }


def evidence_summary(evidence: dict[str, Any] | None) -> dict[str, Any]:
    if evidence is None:
        return {
            "export_validation_status": "missing",
            "readiness_status": "missing",
            "frontend_flow_status": "missing",
        }
    validation = as_obj(evidence.get("validation_summary"))
    export_validation = as_obj(validation.get("current_export_validation"))
    readiness = as_obj(evidence.get("mvp_demo_readiness"))
    frontend_flow = as_obj(
        as_obj(evidence.get("browser_visual_evidence")).get("frontend_flow")
    )
    return {
        "export_validation_status": export_validation.get("status"),
        "readiness_status": readiness.get("overall_status"),
        "frontend_flow_status": frontend_flow.get("status"),
        "frontend_flow_captured_screenshot_count": frontend_flow.get(
            "captured_screenshot_count"
        ),
        "frontend_flow_expected_screenshot_count": frontend_flow.get(
            "expected_screenshot_count"
        ),
        "frontend_flow_failure_count": frontend_flow.get("failure_count"),
    }


def scheduler_pipeline_summary(report: dict[str, Any] | None) -> dict[str, Any]:
    if report is None:
        return {
            "status": "missing",
            "step_count": 0,
            "passed_step_count": 0,
            "runtime_readiness_chain_status": "missing",
            "runtime_readiness_chain_step_count": 0,
            "runtime_readiness_chain_activation_allowed_count": None,
            "runtime_readiness_chain_post_actions": [],
            "external_provider_call_count": None,
            "runtime_activation_allowed_count": None,
        }
    summary = as_obj(report.get("summary"))
    safety = as_obj(report.get("safety_summary"))
    return {
        "schema_version": report.get("schema_version"),
        "status": report.get("status"),
        "step_count": report.get("step_count"),
        "passed_step_count": report.get("passed_step_count"),
        "background_handoff_status": summary.get("background_handoff_status"),
        "background_handoff_runner_handoff_count": summary.get(
            "background_handoff_runner_handoff_count"
        ),
        "background_handoff_outbox_schema_version": summary.get(
            "background_handoff_outbox_schema_version"
        ),
        "image_chain_staging_status": summary.get("image_chain_staging_status"),
        "runtime_readiness_chain_status": summary.get(
            "runtime_readiness_chain_status"
        ),
        "runtime_readiness_chain_step_count": summary.get(
            "runtime_readiness_chain_step_count"
        ),
        "runtime_readiness_chain_schedule_item_id": summary.get(
            "runtime_readiness_chain_schedule_item_id"
        ),
        "runtime_readiness_chain_post_actions": as_list(
            summary.get("runtime_readiness_chain_post_actions")
        ),
        "runtime_readiness_chain_activation_allowed_count": summary.get(
            "runtime_readiness_chain_activation_allowed_count"
        ),
        "runtime_readiness_chain_ledger_kind_counts": summary.get(
            "runtime_readiness_chain_ledger_kind_counts"
        ),
        "positive_shared_cache_reuse_path": summary.get(
            "positive_shared_cache_reuse_path"
        ),
        "external_provider_call_count": safety.get("external_provider_call_count"),
        "world_mutation_count": safety.get("world_mutation_count"),
        "runtime_activation_allowed_count": safety.get(
            "runtime_activation_allowed_count"
        ),
        "runtime_package_write_count": safety.get("runtime_package_write_count"),
        "world_delta_transaction_write_count": safety.get(
            "world_delta_transaction_write_count"
        ),
    }


def outbox_import_summary(report: dict[str, Any] | None) -> dict[str, Any]:
    if report is None:
        return {
            "status": "missing",
            "step_count": 0,
            "passed_step_count": 0,
            "external_provider_call_count": None,
            "runtime_activation_allowed_count": None,
        }
    summary = as_obj(report.get("summary"))
    safety = as_obj(report.get("safety_summary"))
    return {
        "schema_version": report.get("schema_version"),
        "status": report.get("status"),
        "step_count": report.get("step_count"),
        "passed_step_count": report.get("passed_step_count"),
        "runner_handoff_count": summary.get("runner_handoff_count"),
        "consumer_executed_count": summary.get("consumer_executed_count"),
        "imported_count": summary.get("imported_count"),
        "pre_import_review_only_envelope_ready_count": summary.get(
            "pre_import_review_only_envelope_ready_count"
        ),
        "prefetch_review_only_envelope_ready_count": summary.get(
            "prefetch_review_only_envelope_ready_count"
        ),
        "activation_allowed_count": summary.get("activation_allowed_count"),
        "external_provider_call_count": safety.get("external_provider_call_count"),
        "consumer_reads_env_count": safety.get("consumer_reads_env_count"),
        "staging_count": safety.get("staging_count"),
        "promotion_count": safety.get("promotion_count"),
        "queue_complete_count": safety.get("queue_complete_count"),
        "world_mutation_count": safety.get("world_mutation_count"),
        "runtime_activation_allowed_count": safety.get(
            "runtime_activation_allowed_count"
        ),
    }


def derive_suite_status(
    commands: list[dict[str, Any]],
    browser_preflight_report: dict[str, Any] | None,
    frontend_report: dict[str, Any] | None,
    frontend_multinode_report: dict[str, Any] | None,
    frontend_battle_drag_report: dict[str, Any] | None,
    evidence: dict[str, Any] | None,
    scheduler_pipeline_report: dict[str, Any] | None,
    outbox_import_report: dict[str, Any] | None,
    allow_missing_browser: bool,
    skip_scheduler_pipeline_smoke: bool,
    skip_outbox_import_smoke: bool,
) -> tuple[str, list[str]]:
    failures: list[str] = [
        f"command_failed:{item['name']}"
        for item in commands
        if item.get("status") != "passed"
    ]
    preflight_status = (browser_preflight_report or {}).get("status")
    frontend_status = (frontend_report or {}).get("status")
    multinode_status = (frontend_multinode_report or {}).get("status")
    battle_drag_status = (frontend_battle_drag_report or {}).get("status")
    evidence_status = evidence_summary(evidence).get("export_validation_status")
    scheduler_summary = scheduler_pipeline_summary(scheduler_pipeline_report)
    outbox_summary = outbox_import_summary(outbox_import_report)

    if preflight_status == "browser_unavailable" and not allow_missing_browser:
        failures.append("browser_preflight_unavailable")
    elif preflight_status not in {"available", "browser_unavailable"}:
        failures.append(f"browser_preflight_status:{preflight_status or 'missing'}")

    if skip_scheduler_pipeline_smoke:
        pass
    elif scheduler_summary.get("status") != "passed":
        failures.append(
            f"scheduler_pipeline_smoke_status:{scheduler_summary.get('status')}"
        )
    if (
        not skip_scheduler_pipeline_smoke
        and int(scheduler_summary.get("external_provider_call_count") or 0) != 0
    ):
        failures.append("scheduler_pipeline_provider_call_count_not_0")
    if (
        not skip_scheduler_pipeline_smoke
        and int(scheduler_summary.get("runtime_activation_allowed_count") or 0) != 0
    ):
        failures.append("scheduler_pipeline_runtime_activation_not_0")
    if (
        not skip_scheduler_pipeline_smoke
        and scheduler_summary.get("runtime_readiness_chain_status")
        != "completed_review_only"
    ):
        failures.append(
            "scheduler_pipeline_runtime_readiness_chain_not_completed"
        )
    if (
        not skip_scheduler_pipeline_smoke
        and int(scheduler_summary.get("runtime_readiness_chain_step_count") or 0) != 3
    ):
        failures.append("scheduler_pipeline_runtime_readiness_step_count_not_3")
    if (
        not skip_scheduler_pipeline_smoke
        and int(
            scheduler_summary.get(
                "runtime_readiness_chain_activation_allowed_count"
            )
            or 0
        )
        != 0
    ):
        failures.append("scheduler_pipeline_runtime_readiness_activation_not_0")
    if not skip_scheduler_pipeline_smoke:
        readiness_actions = set(
            str(action)
            for action in as_list(
                scheduler_summary.get("runtime_readiness_chain_post_actions")
            )
        )
        if "wait_for_runtime_activation_apply_gate" not in readiness_actions:
            failures.append("scheduler_pipeline_runtime_readiness_apply_gate_missing")

    if skip_outbox_import_smoke:
        pass
    elif outbox_summary.get("status") != "passed":
        failures.append(f"outbox_import_smoke_status:{outbox_summary.get('status')}")
    if (
        not skip_outbox_import_smoke
        and int(outbox_summary.get("external_provider_call_count") or 0) != 0
    ):
        failures.append("outbox_import_provider_call_count_not_0")
    if (
        not skip_outbox_import_smoke
        and int(outbox_summary.get("consumer_reads_env_count") or 0) != 0
    ):
        failures.append("outbox_import_env_read_count_not_0")
    if (
        not skip_outbox_import_smoke
        and int(outbox_summary.get("staging_count") or 0) != 0
    ):
        failures.append("outbox_import_staging_count_not_0")
    if (
        not skip_outbox_import_smoke
        and int(outbox_summary.get("promotion_count") or 0) != 0
    ):
        failures.append("outbox_import_promotion_count_not_0")
    if (
        not skip_outbox_import_smoke
        and int(outbox_summary.get("queue_complete_count") or 0) != 0
    ):
        failures.append("outbox_import_queue_complete_count_not_0")
    if (
        not skip_outbox_import_smoke
        and int(outbox_summary.get("world_mutation_count") or 0) != 0
    ):
        failures.append("outbox_import_world_mutation_count_not_0")
    if (
        not skip_outbox_import_smoke
        and int(outbox_summary.get("runtime_activation_allowed_count") or 0) != 0
    ):
        failures.append("outbox_import_runtime_activation_not_0")
    if (
        not skip_outbox_import_smoke
        and (
            outbox_summary.get("pre_import_review_only_envelope_ready_count") is None
            or int(outbox_summary.get("pre_import_review_only_envelope_ready_count"))
            != 0
        )
    ):
        failures.append("outbox_import_pre_import_ready_count_not_0")
    if (
        not skip_outbox_import_smoke
        and int(outbox_summary.get("imported_count") or 0) != 2
    ):
        failures.append("outbox_import_imported_count_not_2")
    if (
        not skip_outbox_import_smoke
        and int(outbox_summary.get("prefetch_review_only_envelope_ready_count") or 0)
        != 2
    ):
        failures.append("outbox_import_prefetch_ready_count_not_2")

    if frontend_status == "captured":
        captured = int((frontend_report or {}).get("captured_screenshot_count") or 0)
        expected = int((frontend_report or {}).get("expected_screenshot_count") or 0)
        if captured != 14 or expected != 14:
            failures.append("frontend_flow_screenshot_count_not_14")
    elif frontend_status == "browser_unavailable" and allow_missing_browser:
        pass
    else:
        failures.append(f"frontend_flow_status:{frontend_status or 'missing'}")

    if multinode_status == "captured":
        captured = int((frontend_multinode_report or {}).get("captured_screenshot_count") or 0)
        expected = int((frontend_multinode_report or {}).get("expected_screenshot_count") or 0)
        if captured != 6 or expected != 6:
            failures.append("frontend_multinode_screenshot_count_not_6")
    elif multinode_status == "browser_unavailable" and allow_missing_browser:
        pass
    else:
        failures.append(f"frontend_multinode_status:{multinode_status or 'missing'}")

    if battle_drag_status == "captured":
        passed = int((frontend_battle_drag_report or {}).get("passed_interaction_count") or 0)
        expected = int((frontend_battle_drag_report or {}).get("expected_interaction_count") or 0)
        if passed != 2 or expected != 2:
            failures.append("frontend_battle_drag_interaction_count_not_2")
    elif battle_drag_status == "browser_unavailable" and allow_missing_browser:
        pass
    else:
        failures.append(f"frontend_battle_drag_status:{battle_drag_status or 'missing'}")

    if (
        allow_missing_browser
        and (
            frontend_status == "browser_unavailable"
            or multinode_status == "browser_unavailable"
            or battle_drag_status == "browser_unavailable"
        )
    ):
        if evidence_status != "passed":
            failures.append("evidence_export_not_passed")
        return ("browser_unavailable_allowed" if not failures else "failed", failures)

    if evidence_status != "passed":
        failures.append(f"evidence_export_status:{evidence_status}")

    return ("passed" if not failures else "failed", failures)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="输出根目录，默认 /tmp/ai_td_demo_evidence_suite。",
    )
    parser.add_argument(
        "--browser-timeout",
        type=int,
        default=45,
        help="传给浏览器截图脚本的单步浏览器超时秒数。",
    )
    parser.add_argument(
        "--command-timeout",
        type=int,
        default=180,
        help="每个子命令的最大运行秒数。",
    )
    parser.add_argument(
        "--browser-bin",
        type=Path,
        help="可选：Chromium 兼容浏览器路径。",
    )
    parser.add_argument(
        "--allow-missing-browser",
        action="store_true",
        help="允许没有本地浏览器时生成 browser_unavailable 证据；默认会失败。",
    )
    parser.add_argument(
        "--skip-scheduler-pipeline-smoke",
        action="store_true",
        help="跳过 Generation Scheduler review-only pipeline smoke；仅用于快速调试，不建议录屏前使用。",
    )
    parser.add_argument(
        "--skip-outbox-import-smoke",
        action="store_true",
        help="跳过 provider runner outbox consume/import smoke；仅用于快速调试，不建议录屏前使用。",
    )
    parser.add_argument(
        "--scheduler-smoke-runner",
        choices=SCHEDULER_SMOKE_RUNNERS,
        default="auto",
        help=(
            "scheduler smoke 执行器。auto 会优先使用当前或共享 worktree 的 .venv/bin/python，"
            "都不存在时回退 uv run。"
        ),
    )
    parser.add_argument(
        "--scheduler-python",
        type=Path,
        help="显式指定 scheduler smoke 使用的 Python；设置后优先于 --scheduler-smoke-runner。",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    output_root = args.output_root.expanduser()
    browser_preflight_path = output_root / "browser" / BROWSER_PREFLIGHT_REPORT_NAME
    scheduler_report_path = output_root / "generation_scheduler" / SCHEDULER_PIPELINE_REPORT_NAME
    outbox_import_report_path = output_root / "generation_scheduler" / OUTBOX_IMPORT_REPORT_NAME
    frontend_output = output_root / "frontend_flow_visual_smoke"
    frontend_report_path = frontend_output / FRONTEND_REPORT_NAME
    frontend_multinode_output = output_root / "frontend_multinode_visual_smoke"
    frontend_multinode_report_path = frontend_multinode_output / FRONTEND_MULTINODE_REPORT_NAME
    frontend_battle_drag_output = output_root / "frontend_battle_drag_interaction_smoke"
    frontend_battle_drag_report_path = frontend_battle_drag_output / FRONTEND_BATTLE_DRAG_REPORT_NAME
    evidence_output = output_root / "demo_evidence"
    suite_report_path = output_root / REPORT_NAME
    output_root.mkdir(parents=True, exist_ok=True)

    commands: list[dict[str, Any]] = []
    browser_preflight_report: dict[str, Any] | None = None
    scheduler_pipeline_report: dict[str, Any] | None = None
    scheduler_pipeline_runner: dict[str, Any] = {
        "mode": "skipped",
        "uses_uv": False,
    }
    outbox_import_report: dict[str, Any] | None = None
    outbox_import_runner: dict[str, Any] = {
        "mode": "skipped",
        "uses_uv": False,
    }
    frontend_report: dict[str, Any] | None = None
    frontend_multinode_report: dict[str, Any] | None = None
    frontend_battle_drag_report: dict[str, Any] | None = None
    evidence: dict[str, Any] | None = None

    uv_lock_path = ROOT / "uv.lock"
    uv_lock_existed_before = uv_lock_path.exists()

    preflight_command = build_browser_preflight_command(args, browser_preflight_path)
    commands.append(
        run_command(
            "browser_smoke_environment_preflight",
            preflight_command,
            root=ROOT,
            timeout_seconds=20,
            output_tail_limit=MAX_OUTPUT_TAIL,
        )
    )
    if browser_preflight_path.exists():
        browser_preflight_report = load_json(browser_preflight_path)
    if (
        (browser_preflight_report or {}).get("status") == "browser_unavailable"
        and not args.allow_missing_browser
    ):
        report = {
            "schema_version": "demo_evidence_suite_report.v0.1",
            "suite_id": "mvp_demo_evidence_suite",
            "status": "failed",
            "generated_at": now_iso(),
            "output_root": str(output_root),
            "commands": commands,
            "outputs": {
                "browser_preflight_report": file_ref(
                    browser_preflight_path,
                    "browser_smoke_environment_report",
                ),
                "suite_report": {
                    "path": str(suite_report_path),
                    "role": "demo_evidence_suite_report",
                    "exists": True,
                },
            },
            "browser_smoke_environment": browser_preflight_summary(
                browser_preflight_report
            ),
            "scheduler_pipeline_smoke_runner": scheduler_pipeline_runner,
            "outbox_import_smoke_runner": outbox_import_runner,
            "generation_scheduler_review_only_pipeline_smoke": scheduler_pipeline_summary(
                scheduler_pipeline_report
            ),
            "provider_runner_handoff_outbox_import_smoke": outbox_import_summary(
                outbox_import_report
            ),
            "frontend_flow_visual_smoke": browser_flow_summary(frontend_report),
            "frontend_multinode_visual_smoke": browser_multinode_summary(
                frontend_multinode_report
            ),
            "frontend_battle_drag_interaction_smoke": browser_battle_drag_summary(
                frontend_battle_drag_report
            ),
            "demo_evidence": evidence_summary(evidence),
            "failures": [
                "browser_preflight_unavailable",
                "rerun_with_allow_missing_browser_for_non_release_evidence",
            ],
            "safety_summary": {
                "reads_env_file": False,
                "provider_call_count_during_suite": 0,
                "world_mutation_count_during_suite": 0,
                "runtime_activation_count_during_suite": 0,
                "stores_provider_body": False,
                "uses_localhost_browser_only": True,
                "scheduler_pipeline_smoke_skipped": bool(
                    args.skip_scheduler_pipeline_smoke
                ),
                "outbox_import_smoke_skipped": bool(args.skip_outbox_import_smoke),
            },
        }
        write_json(suite_report_path, report)
        print(f"demo evidence suite failed: {suite_report_path}")
        print(f"- browser preflight report: {browser_preflight_path}")
        print("- browser missing; rerun with --allow-missing-browser for non-release evidence")
        return 1

    if not args.skip_scheduler_pipeline_smoke:
        scheduler_command, scheduler_env, scheduler_pipeline_runner = (
            build_scheduler_pipeline_smoke_invocation(
                args,
                scheduler_report_path,
                output_root,
            )
        )
        commands.append(
            run_command(
                "generation_scheduler_review_only_pipeline_smoke",
                scheduler_command,
                root=ROOT,
                timeout_seconds=args.command_timeout,
                output_tail_limit=MAX_OUTPUT_TAIL,
                env=scheduler_env,
            )
        )
        if (
            scheduler_pipeline_runner.get("uses_uv") is True
            and not uv_lock_existed_before
            and uv_lock_path.exists()
        ):
            uv_lock_path.unlink()
        if scheduler_report_path.exists():
            scheduler_pipeline_report = load_json(scheduler_report_path)
        commands.append(
            run_command(
                "generation_scheduler_review_only_pipeline_smoke_report_validator",
                build_scheduler_pipeline_smoke_validate_command(scheduler_report_path),
                root=ROOT,
                timeout_seconds=20,
                output_tail_limit=MAX_OUTPUT_TAIL,
            )
        )

    if not args.skip_outbox_import_smoke:
        outbox_command, outbox_env, outbox_import_runner = (
            build_outbox_import_smoke_invocation(
                args,
                outbox_import_report_path,
                output_root,
            )
        )
        commands.append(
            run_command(
                "provider_runner_handoff_outbox_import_smoke",
                outbox_command,
                root=ROOT,
                timeout_seconds=args.command_timeout,
                output_tail_limit=MAX_OUTPUT_TAIL,
                env=outbox_env,
            )
        )
        if (
            outbox_import_runner.get("uses_uv") is True
            and not uv_lock_existed_before
            and uv_lock_path.exists()
        ):
            uv_lock_path.unlink()
        if outbox_import_report_path.exists():
            outbox_import_report = load_json(outbox_import_report_path)

    capture_command = build_capture_command(args, frontend_output)
    commands.append(
        run_command(
            "frontend_flow_visual_smoke_capture",
            capture_command,
            root=ROOT,
            timeout_seconds=args.command_timeout,
            output_tail_limit=MAX_OUTPUT_TAIL,
        )
    )

    if frontend_report_path.exists():
        frontend_report = load_json(frontend_report_path)

    multinode_capture_command = build_multinode_capture_command(
        args,
        frontend_multinode_output,
    )
    commands.append(
        run_command(
            "frontend_multinode_visual_smoke_capture",
            multinode_capture_command,
            root=ROOT,
            timeout_seconds=args.command_timeout,
            output_tail_limit=MAX_OUTPUT_TAIL,
        )
    )
    if frontend_multinode_report_path.exists():
        frontend_multinode_report = load_json(frontend_multinode_report_path)

    battle_drag_capture_command = build_battle_drag_capture_command(
        args,
        frontend_battle_drag_output,
    )
    commands.append(
        run_command(
            "frontend_battle_drag_interaction_smoke_capture",
            battle_drag_capture_command,
            root=ROOT,
            timeout_seconds=args.command_timeout,
            output_tail_limit=MAX_OUTPUT_TAIL,
        )
    )
    if frontend_battle_drag_report_path.exists():
        frontend_battle_drag_report = load_json(frontend_battle_drag_report_path)

    if frontend_report_path.exists():
        validate_command = build_validate_command(
            frontend_report_path,
            args.allow_missing_browser,
        )
        commands.append(
            run_command(
                "frontend_flow_visual_smoke_validate",
                validate_command,
                root=ROOT,
                timeout_seconds=args.command_timeout,
                output_tail_limit=MAX_OUTPUT_TAIL,
            )
        )

    if frontend_multinode_report_path.exists():
        multinode_validate_command = build_multinode_validate_command(
            frontend_multinode_report_path,
            args.allow_missing_browser,
        )
        commands.append(
            run_command(
                "frontend_multinode_visual_smoke_validate",
                multinode_validate_command,
                root=ROOT,
                timeout_seconds=args.command_timeout,
                output_tail_limit=MAX_OUTPUT_TAIL,
            )
        )

    if frontend_battle_drag_report_path.exists():
        battle_drag_validate_command = build_battle_drag_validate_command(
            frontend_battle_drag_report_path,
            args.allow_missing_browser,
        )
        commands.append(
            run_command(
                "frontend_battle_drag_interaction_smoke_validate",
                battle_drag_validate_command,
                root=ROOT,
                timeout_seconds=args.command_timeout,
                output_tail_limit=MAX_OUTPUT_TAIL,
            )
        )

    if frontend_report_path.exists():
        export_command = build_export_command(evidence_output, frontend_report_path)
        commands.append(
            run_command(
                "demo_evidence_export",
                export_command,
                root=ROOT,
                timeout_seconds=args.command_timeout,
                output_tail_limit=MAX_OUTPUT_TAIL,
            )
        )
        evidence_path = evidence_output / "evidence.json"
        if evidence_path.exists():
            evidence = load_json(evidence_path)

    status, failures = derive_suite_status(
        commands,
        browser_preflight_report,
        frontend_report,
        frontend_multinode_report,
        frontend_battle_drag_report,
        evidence,
        scheduler_pipeline_report,
        outbox_import_report,
        args.allow_missing_browser,
        args.skip_scheduler_pipeline_smoke,
        args.skip_outbox_import_smoke,
    )
    report = {
        "schema_version": "demo_evidence_suite_report.v0.1",
        "suite_id": "mvp_demo_evidence_suite",
        "status": status,
        "generated_at": now_iso(),
        "output_root": str(output_root),
        "commands": commands,
        "outputs": {
            "browser_preflight_report": file_ref(
                browser_preflight_path,
                "browser_smoke_environment_report",
            ),
            "frontend_flow_report": file_ref(
                frontend_report_path,
                "frontend_flow_visual_smoke_report",
            ),
            "frontend_multinode_report": file_ref(
                frontend_multinode_report_path,
                "frontend_multinode_visual_smoke_report",
            ),
            "frontend_battle_drag_report": file_ref(
                frontend_battle_drag_report_path,
                "battle_drag_interaction_smoke_report",
            ),
            "generation_scheduler_pipeline_smoke_report": file_ref(
                scheduler_report_path,
                "generation_scheduler_review_only_pipeline_smoke_report",
            ),
            "provider_runner_handoff_outbox_import_smoke_report": file_ref(
                outbox_import_report_path,
                "provider_runner_handoff_outbox_import_pipeline_report",
            ),
            "demo_evidence_json": file_ref(
                evidence_output / "evidence.json",
                "demo_evidence_json",
            ),
            "demo_summary_markdown": file_ref(
                evidence_output / "summary.md",
                "demo_summary_markdown",
            ),
            "demo_index_html": file_ref(
                evidence_output / "index.html",
                "demo_index_html",
            ),
            "suite_report": {
                "path": str(suite_report_path),
                "role": "demo_evidence_suite_report",
                "exists": True,
            },
        },
        "scheduler_pipeline_smoke_runner": scheduler_pipeline_runner,
        "outbox_import_smoke_runner": outbox_import_runner,
        "browser_smoke_environment": browser_preflight_summary(
            browser_preflight_report
        ),
        "generation_scheduler_review_only_pipeline_smoke": scheduler_pipeline_summary(
            scheduler_pipeline_report
        ),
        "provider_runner_handoff_outbox_import_smoke": outbox_import_summary(
            outbox_import_report
        ),
        "frontend_flow_visual_smoke": browser_flow_summary(frontend_report),
        "frontend_multinode_visual_smoke": browser_multinode_summary(
            frontend_multinode_report
        ),
        "frontend_battle_drag_interaction_smoke": browser_battle_drag_summary(
            frontend_battle_drag_report
        ),
        "demo_evidence": evidence_summary(evidence),
        "failures": failures,
        "safety_summary": {
            "reads_env_file": False,
            "provider_call_count_during_suite": 0,
            "world_mutation_count_during_suite": 0,
            "runtime_activation_count_during_suite": 0,
            "stores_provider_body": False,
            "uses_localhost_browser_only": True,
            "scheduler_pipeline_smoke_skipped": bool(
                args.skip_scheduler_pipeline_smoke
            ),
            "outbox_import_smoke_skipped": bool(args.skip_outbox_import_smoke),
        },
    }
    write_json(suite_report_path, report)
    print(f"demo evidence suite {status}: {suite_report_path}")
    print(f"- browser preflight report: {browser_preflight_path}")
    print(f"- frontend report: {frontend_report_path}")
    print(f"- frontend multinode report: {frontend_multinode_report_path}")
    print(f"- frontend battle drag report: {frontend_battle_drag_report_path}")
    print(f"- evidence bundle: {evidence_output}")
    return 0 if status == "passed" or status == "browser_unavailable_allowed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
