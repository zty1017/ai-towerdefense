#!/usr/bin/env python3
"""Dry-run a GenerationSchedulePlan v0.1 into a review-only run report."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ASSET_GRAPH_DIR = ROOT / "tools" / "asset_graph"
if str(ASSET_GRAPH_DIR) not in sys.path:
    sys.path.insert(0, str(ASSET_GRAPH_DIR))

from validation_common import load_json  # noqa: E402
from validate_generation_schedule_plan import validate_generation_schedule_plan  # noqa: E402
from validate_generation_schedule_run_report import validate_generation_schedule_run_report  # noqa: E402


DEFAULT_PLAN = ROOT / "examples/review_packs/mvp_generation_schedule_plan.v0.1.json"
DEFAULT_OUTPUT = ROOT / "examples/review_packs/mvp_generation_schedule_run_report.v0.1.json"


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def action_for_item(item: dict[str, Any], dependencies_satisfied: bool) -> tuple[str, str, list[str]]:
    latency = item.get("latency_class")
    source_status = item.get("status")
    provider_mode = as_obj(item.get("provider_policy")).get("mode")
    notes: list[str] = []

    if not dependencies_satisfied:
        return "blocked", "blocked", ["等待依赖调度项先完成或进入可用 fallback。"]

    if latency == "sync_blocking":
        if source_status in {"ready", "cached"}:
            return "reuse_ready", "passed", ["复用已审同步内容，不进行实时生成。"]
        return "select_fallback", "fallback", ["同步内容不可实时生成，选择已审 fallback。"]

    if latency == "fallback_static":
        return "select_fallback", "fallback", ["静态兜底路径已可用。"]

    if latency == "background_prefetch":
        if provider_mode != "no_live_provider":
            notes.append("需要人工或系统授权后才允许真实生成。")
        notes.append("预取结果启用前必须重新通过结构和语义门。")
        return "schedule_prefetch", "scheduled", notes

    if latency == "background":
        if provider_mode != "no_live_provider":
            notes.append("后台增强不阻塞玩家流程，真实调用需另行授权。")
        return "schedule_background", "scheduled", notes

    if latency == "lazy":
        return "schedule_lazy", "scheduled", ["低优先级修复，只在空闲窗口处理。"]

    return "blocked", "blocked", [f"未知 latency_class: {latency}"]


def run_plan(plan: dict[str, Any], plan_path: Path) -> dict[str, Any]:
    plan_errors = validate_generation_schedule_plan(plan)
    if plan_errors:
        raise ValueError("GenerationSchedulePlan invalid: " + "; ".join(plan_errors))

    completed: set[str] = set()
    run_items: list[dict[str, Any]] = []
    for item in sorted(as_list(plan.get("items")), key=lambda raw: -int(as_obj(raw).get("priority") or 0)):
        if not isinstance(item, dict):
            continue
        deps = [str(dep) for dep in as_list(item.get("dependencies"))]
        dependencies_satisfied = all(dep in completed for dep in deps)
        action, result_status, notes = action_for_item(item, dependencies_satisfied)
        provider_mode = as_obj(item.get("provider_policy")).get("mode")
        run_item = {
            "schedule_item_id": item.get("schedule_item_id"),
            "compile_request_id": item.get("compile_request_id"),
            "object_ref": item.get("object_ref"),
            "latency_class": item.get("latency_class"),
            "source_status": item.get("status"),
            "action": action,
            "result_status": result_status,
            "dependencies_satisfied": dependencies_satisfied,
            "provider_call_planned": False,
            "provider_review_required": provider_mode != "no_live_provider",
            "world_mutation_performed": False,
            "fallback_ref": item.get("fallback_ref"),
            "notes": notes,
        }
        run_items.append(run_item)
        if result_status in {"passed", "fallback", "scheduled"}:
            completed.add(str(item.get("schedule_item_id")))

    action_counts = Counter(str(item.get("action") or "") for item in run_items)
    status_counts = Counter(str(item.get("result_status") or "") for item in run_items)
    return {
        "schema_version": "generation_schedule_run_report.v0.1",
        "report_id": "mvp_generation_schedule_run_report_v0_1",
        "visibility": "review_only",
        "run_mode": "dry_run",
        "generated_at": "2026-07-02T00:00:00Z",
        "source_refs": {
            "generation_schedule_plan": rel(plan_path),
        },
        "execution_policy": {
            "reads_env": False,
            "calls_provider": False,
            "mutates_world_state": False,
            "writes_runtime_package": False,
            "activates_prefetch_results": False,
        },
        "summary": {
            "plan_id": plan.get("plan_id"),
            "item_count": len(run_items),
            "action_counts": dict(sorted(action_counts.items())),
            "status_counts": dict(sorted(status_counts.items())),
            "ready_reused_count": action_counts.get("reuse_ready", 0),
            "fallback_selected_count": action_counts.get("select_fallback", 0),
            "scheduled_count": sum(
                action_counts.get(action, 0)
                for action in ["schedule_prefetch", "schedule_background", "schedule_lazy"]
            ),
            "blocked_count": action_counts.get("blocked", 0),
            "provider_call_count": 0,
            "world_mutation_count": 0,
        },
        "items": run_items,
        "validation_commands": [
            {
                "purpose": "validate schedule run report",
                "command": "python3 tools/scheduler/validate_generation_schedule_run_report.py examples/review_packs/mvp_generation_schedule_run_report.v0.1.json",
            }
        ],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run a GenerationSchedulePlan v0.1.")
    parser.add_argument("--plan", default=str(DEFAULT_PLAN), help="Input GenerationSchedulePlan JSON.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output GenerationScheduleRunReport JSON.")
    parser.add_argument("--validate", action="store_true", help="Validate the report before writing.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    plan_path = Path(args.plan)
    try:
        plan = load_json(plan_path)
    except FileNotFoundError:
        print(f"missing generation schedule plan: {plan_path}")
        return 1
    report = run_plan(plan, plan_path)
    if args.validate:
        errors = validate_generation_schedule_run_report(report)
        if errors:
            print("INVALID generated GenerationScheduleRunReport")
            for error in errors:
                print(f"- {error}")
            return 1
    output = Path(args.output)
    write_json(output, report)
    print("OK dry-ran GenerationSchedulePlan")
    print(f"- output: {output}")
    print(f"- items: {report['summary']['item_count']}")
    print(f"- actions: {report['summary']['action_counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
