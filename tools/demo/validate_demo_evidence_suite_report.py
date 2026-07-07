#!/usr/bin/env python3
"""Validate the compact report written by run_demo_evidence_suite.py."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


EXPECTED_SCHEMA_VERSION = "demo_evidence_suite_report.v0.1"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("suite report root must be an object")
    return data


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def command_names(report: dict[str, Any]) -> set[str]:
    return {
        str(item.get("name"))
        for item in as_list(report.get("commands"))
        if isinstance(item, dict)
    }


def validate_status(
    report: dict[str, Any],
    *,
    allow_browser_unavailable: bool,
    require_browser_captured: bool,
    failures: list[str],
) -> None:
    status = report.get("status")
    allowed_statuses = {"passed"}
    if allow_browser_unavailable:
        allowed_statuses.add("browser_unavailable_allowed")
    require(status in allowed_statuses, f"unexpected suite status: {status}", failures)
    if require_browser_captured:
        require(status == "passed", "browser capture required but suite did not pass", failures)
        frontend = as_obj(report.get("frontend_flow_visual_smoke"))
        require(frontend.get("status") == "captured", "frontend flow not captured", failures)
        require(
            int_value(frontend.get("captured_screenshot_count")) == 14,
            "captured screenshot count is not 14",
            failures,
        )
        require(
            int_value(frontend.get("expected_screenshot_count")) == 14,
            "expected screenshot count is not 14",
            failures,
        )
        multinode = as_obj(report.get("frontend_multinode_visual_smoke"))
        require(
            multinode.get("status") == "captured",
            "frontend multinode visual smoke not captured",
            failures,
        )
        require(
            int_value(multinode.get("captured_screenshot_count")) == 6,
            "multinode captured screenshot count is not 6",
            failures,
        )
        require(
            int_value(multinode.get("expected_screenshot_count")) == 6,
            "multinode expected screenshot count is not 6",
            failures,
        )
        battle_drag = as_obj(report.get("frontend_battle_drag_interaction_smoke"))
        require(
            battle_drag.get("status") == "captured",
            "frontend battle drag interaction smoke not captured",
            failures,
        )
        require(
            int_value(battle_drag.get("passed_interaction_count")) == 2,
            "battle drag passed interaction count is not 2",
            failures,
        )
        require(
            int_value(battle_drag.get("expected_interaction_count")) == 2,
            "battle drag expected interaction count is not 2",
            failures,
        )
    report_failures = as_list(report.get("failures"))
    require(not report_failures, f"suite failures not empty: {report_failures}", failures)


def validate_outputs(report: dict[str, Any], failures: list[str]) -> None:
    outputs = as_obj(report.get("outputs"))
    safety = as_obj(report.get("safety_summary"))
    optional_when_skipped = {
        "generation_scheduler_pipeline_smoke_report": bool(
            safety.get("scheduler_pipeline_smoke_skipped")
        ),
        "provider_runner_handoff_outbox_import_smoke_report": bool(
            safety.get("outbox_import_smoke_skipped")
        ),
    }
    require(bool(outputs), "outputs missing", failures)
    for name, output in outputs.items():
        output_obj = as_obj(output)
        if optional_when_skipped.get(name) and output_obj.get("exists") is False:
            continue
        require(output_obj.get("exists") is True, f"output missing: {name}", failures)


def validate_demo_evidence(report: dict[str, Any], failures: list[str]) -> None:
    evidence = as_obj(report.get("demo_evidence"))
    require(
        evidence.get("export_validation_status") == "passed",
        f"demo evidence export status is {evidence.get('export_validation_status')}",
        failures,
    )


def validate_safety(report: dict[str, Any], failures: list[str]) -> None:
    safety = as_obj(report.get("safety_summary"))
    require(
        int_value(safety.get("provider_call_count_during_suite")) == 0,
        "provider call count during suite is not 0",
        failures,
    )
    require(
        int_value(safety.get("world_mutation_count_during_suite")) == 0,
        "world mutation count during suite is not 0",
        failures,
    )
    require(
        int_value(safety.get("runtime_activation_count_during_suite")) == 0,
        "runtime activation count during suite is not 0",
        failures,
    )
    require(safety.get("reads_env_file") is False, "suite reads .env", failures)
    require(safety.get("stores_provider_body") is False, "suite stores provider body", failures)


def validate_browser_preflight(
    report: dict[str, Any],
    *,
    require_browser_captured: bool,
    allow_browser_unavailable: bool,
    failures: list[str],
) -> None:
    preflight = as_obj(report.get("browser_smoke_environment"))
    status = preflight.get("status")
    allowed = {"available"}
    if allow_browser_unavailable:
        allowed.add("browser_unavailable")
    require(status in allowed, f"browser preflight status is {status}", failures)
    if require_browser_captured:
        require(status == "available", "browser preflight did not find a browser", failures)
    safety = as_obj(preflight.get("safety_summary"))
    if safety:
        require(safety.get("reads_env_file") is False, "browser preflight reads .env", failures)
        require(
            int_value(safety.get("provider_call_count")) == 0,
            "browser preflight provider call count is not 0",
            failures,
        )
        require(
            safety.get("launches_browser") is False,
            "browser preflight should not launch a browser",
            failures,
        )
        require(safety.get("opens_socket") is False, "browser preflight opens a socket", failures)


def validate_browser_battle_drag(
    report: dict[str, Any],
    *,
    require_browser_captured: bool,
    allow_browser_unavailable: bool,
    failures: list[str],
) -> None:
    battle_drag = as_obj(report.get("frontend_battle_drag_interaction_smoke"))
    status = battle_drag.get("status")
    allowed = {"captured"}
    if allow_browser_unavailable:
        allowed.add("browser_unavailable")
    require(status in allowed, f"battle drag smoke status is {status}", failures)
    if require_browser_captured:
        require(status == "captured", "battle drag smoke was not captured", failures)
    if status == "captured":
        require(
            int_value(battle_drag.get("passed_interaction_count")) == 2,
            "battle drag passed interaction count is not 2",
            failures,
        )
        require(
            int_value(battle_drag.get("expected_interaction_count")) == 2,
            "battle drag expected interaction count is not 2",
            failures,
        )
    safety = as_obj(battle_drag.get("safety_summary"))
    if safety:
        require(safety.get("reads_env_file") is False, "battle drag smoke reads .env", failures)
        require(
            int_value(safety.get("provider_call_count")) == 0,
            "battle drag smoke provider call count is not 0",
            failures,
        )
        require(
            safety.get("runtime_activation_allowed") is False,
            "battle drag smoke activates runtime",
            failures,
        )


def validate_scheduler(
    report: dict[str, Any],
    *,
    required: bool,
    runner_mode: str | None,
    failures: list[str],
) -> None:
    safety = as_obj(report.get("safety_summary"))
    scheduler = as_obj(report.get("generation_scheduler_review_only_pipeline_smoke"))
    names = command_names(report)
    if required:
        require(
            safety.get("scheduler_pipeline_smoke_skipped") is False,
            "scheduler pipeline smoke was skipped",
            failures,
        )
        require(
            "generation_scheduler_review_only_pipeline_smoke" in names,
            "scheduler pipeline smoke command missing",
            failures,
        )
        require(scheduler.get("status") == "passed", "scheduler smoke not passed", failures)
        require(
            int_value(scheduler.get("external_provider_call_count")) == 0,
            "scheduler provider call count is not 0",
            failures,
        )
        require(
            int_value(scheduler.get("runtime_activation_allowed_count")) == 0,
            "scheduler runtime activation allowed count is not 0",
            failures,
        )
        require(
            scheduler.get("runtime_readiness_chain_status")
            == "completed_review_only",
            "scheduler runtime readiness chain is not completed_review_only",
            failures,
        )
        require(
            int_value(scheduler.get("runtime_readiness_chain_step_count")) == 3,
            "scheduler runtime readiness chain step count is not 3",
            failures,
        )
        require(
            int_value(
                scheduler.get("runtime_readiness_chain_activation_allowed_count")
            )
            == 0,
            "scheduler runtime readiness chain activation allowed count is not 0",
            failures,
        )
        post_actions = {
            str(action)
            for action in as_list(
                scheduler.get("runtime_readiness_chain_post_actions")
            )
        }
        require(
            "wait_for_runtime_activation_apply_gate" in post_actions,
            "scheduler runtime readiness chain apply gate action missing",
            failures,
        )
    if runner_mode:
        runner = as_obj(report.get("scheduler_pipeline_smoke_runner"))
        require(
            runner.get("mode") == runner_mode,
            f"scheduler runner mode is {runner.get('mode')}, expected {runner_mode}",
            failures,
        )


def validate_outbox(
    report: dict[str, Any],
    *,
    required: bool,
    runner_mode: str | None,
    failures: list[str],
) -> None:
    safety = as_obj(report.get("safety_summary"))
    outbox = as_obj(report.get("provider_runner_handoff_outbox_import_smoke"))
    names = command_names(report)
    if required:
        require(
            safety.get("outbox_import_smoke_skipped") is False,
            "outbox import smoke was skipped",
            failures,
        )
        require(
            "provider_runner_handoff_outbox_import_smoke" in names,
            "outbox import smoke command missing",
            failures,
        )
        require(outbox.get("status") == "passed", "outbox import smoke not passed", failures)
        require(int_value(outbox.get("imported_count")) == 2, "outbox imported count is not 2", failures)
        require(
            int_value(outbox.get("pre_import_review_only_envelope_ready_count")) == 0,
            "outbox pre-import ready count is not 0",
            failures,
        )
        require(
            int_value(outbox.get("prefetch_review_only_envelope_ready_count")) == 2,
            "outbox prefetch ready count is not 2",
            failures,
        )
        for field in (
            "external_provider_call_count",
            "consumer_reads_env_count",
            "staging_count",
            "promotion_count",
            "queue_complete_count",
            "world_mutation_count",
            "runtime_activation_allowed_count",
        ):
            require(int_value(outbox.get(field)) == 0, f"outbox {field} is not 0", failures)
    if runner_mode:
        runner = as_obj(report.get("outbox_import_smoke_runner"))
        require(
            runner.get("mode") == runner_mode,
            f"outbox runner mode is {runner.get('mode')}, expected {runner_mode}",
            failures,
        )


def validate_report(report: dict[str, Any], args: argparse.Namespace) -> list[str]:
    failures: list[str] = []
    require(
        report.get("schema_version") == EXPECTED_SCHEMA_VERSION,
        f"schema_version is {report.get('schema_version')}",
        failures,
    )
    validate_status(
        report,
        allow_browser_unavailable=args.allow_browser_unavailable,
        require_browser_captured=args.require_browser_captured,
        failures=failures,
    )
    validate_outputs(report, failures)
    validate_demo_evidence(report, failures)
    validate_safety(report, failures)
    validate_browser_preflight(
        report,
        require_browser_captured=args.require_browser_captured,
        allow_browser_unavailable=args.allow_browser_unavailable,
        failures=failures,
    )
    validate_browser_battle_drag(
        report,
        require_browser_captured=args.require_browser_captured,
        allow_browser_unavailable=args.allow_browser_unavailable,
        failures=failures,
    )
    validate_scheduler(
        report,
        required=args.require_scheduler_pipeline_smoke,
        runner_mode=args.require_scheduler_runner_mode,
        failures=failures,
    )
    validate_outbox(
        report,
        required=args.require_outbox_import_smoke,
        runner_mode=args.require_outbox_runner_mode,
        failures=failures,
    )
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument(
        "--allow-browser-unavailable",
        action="store_true",
        help="Accept browser_unavailable_allowed suite status.",
    )
    parser.add_argument(
        "--require-browser-captured",
        action="store_true",
        help="Require fully captured frontend browser reports: 14 flow screenshots, 6 multinode screenshots, and 2 drag interactions.",
    )
    parser.add_argument(
        "--require-scheduler-pipeline-smoke",
        action="store_true",
        help="Require scheduler pipeline smoke summary and safety counts.",
    )
    parser.add_argument(
        "--require-outbox-import-smoke",
        action="store_true",
        help="Require provider runner outbox import smoke summary and safety counts.",
    )
    parser.add_argument(
        "--require-scheduler-runner-mode",
        help="Require scheduler_pipeline_smoke_runner.mode to match this value.",
    )
    parser.add_argument(
        "--require-outbox-runner-mode",
        help="Require outbox_import_smoke_runner.mode to match this value.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = load_json(args.report)
        failures = validate_report(report, args)
    except Exception as exc:  # noqa: BLE001 - CLI should report concise failures.
        print(f"INVALID demo evidence suite report: {exc}", file=sys.stderr)
        return 1
    if failures:
        print("INVALID demo evidence suite report")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"valid demo evidence suite report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
