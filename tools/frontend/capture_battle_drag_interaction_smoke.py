#!/usr/bin/env python3
"""Capture a browser smoke report for battle drag deployment.

The smoke opens the no-build frontend in battle smoke mode and performs the
player-facing gesture: drag a requested tool card onto a valid battlefield
slot and release. It writes a structured report plus after-drag screenshots.
No providers, .env files, world mutations, or runtime activation are involved.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.frontend.capture_frontend_flow_visual_smoke import (  # noqa: E402
    CDPClient,
    DevToolsProtocolError,
    as_obj,
    browser_candidates,
    capture_screenshot,
    choose_port,
    find_browser,
    js_wait_selector,
    launch_browser,
    parse_viewports,
    start_static_server,
    wait_for_devtools_page,
)


SCHEMA_VERSION = "battle_drag_interaction_smoke_report.v0.1"
TASK_ID = "P1-D-41-battle-drag-browser-smoke"
DEFAULT_NODE_ID = "gray_lantern_station"
REPORT_NAME = "battle_drag_interaction_smoke_report.v0.1.json"


def smoke_url(static_port: int, node_id: str) -> str:
    query = urlencode(
        {
            "static": "1",
            "battleVisualSmoke": "1",
            "nodeId": node_id,
        }
    )
    return f"http://127.0.0.1:{static_port}/frontend/index.html?{query}"


def js_tool_center(tool: str) -> str:
    return f"""
(() => {{
  const tool = {json.dumps(tool)};
  const el = document.querySelector(`.toolbar-card[data-tool="${{tool}}"]`);
  if (!el) return {{ ok: false, error: "tool card not found", tool }};
  el.scrollIntoView({{ block: "nearest", inline: "nearest" }});
  const rect = el.getBoundingClientRect();
  return {{
    ok: true,
    tool,
    client_x: Math.round(rect.left + rect.width / 2),
    client_y: Math.round(rect.top + rect.height / 2),
    width: Math.round(rect.width),
    height: Math.round(rect.height),
    className: el.className
  }};
}})()
"""


def js_probe_snapshot(tool: str) -> str:
    return f"""
(() => {{
  const probe = window.__AI_TD_BATTLE_SMOKE__;
  if (!probe || typeof probe.snapshot !== "function") {{
    return {{ ok: false, error: "battle smoke probe missing" }};
  }}
  const snapshot = probe.snapshot();
  snapshot.requestedTool = {json.dumps(tool)};
  if (!snapshot.deploymentPoint && typeof probe.deploymentPoint === "function") {{
    snapshot.deploymentPoint = probe.deploymentPoint({json.dumps(tool)});
  }}
  return snapshot;
}})()
"""


def wait_probe(cdp: CDPClient, tool: str, timeout_seconds: float) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last: Any = None
    while time.time() < deadline:
        last = cdp.eval(js_probe_snapshot(tool), timeout_ms=3000)
        snapshot = as_obj(last)
        if snapshot.get("ok") and as_obj(snapshot.get("deploymentPoint")):
            return snapshot
        time.sleep(0.1)
    raise DevToolsProtocolError(f"Battle smoke probe not ready: {last}")


def dispatch_drag(
    cdp: CDPClient,
    start: dict[str, Any],
    end: dict[str, Any],
    before_release: Callable[[], None] | None = None,
) -> None:
    start_x = float(start["client_x"])
    start_y = float(start["client_y"])
    end_x = float(end["client_x"])
    end_y = float(end["client_y"])
    cdp.call(
        "Input.dispatchMouseEvent",
        {
            "type": "mouseMoved",
            "x": start_x,
            "y": start_y,
            "button": "none",
            "pointerType": "mouse",
        },
    )
    cdp.call(
        "Input.dispatchMouseEvent",
        {
            "type": "mousePressed",
            "x": start_x,
            "y": start_y,
            "button": "left",
            "buttons": 1,
            "clickCount": 1,
            "pointerType": "mouse",
        },
    )
    for step in range(1, 10):
        ratio = step / 9
        cdp.call(
            "Input.dispatchMouseEvent",
            {
                "type": "mouseMoved",
                "x": start_x + (end_x - start_x) * ratio,
                "y": start_y + (end_y - start_y) * ratio,
                "button": "left",
                "buttons": 1,
                "pointerType": "mouse",
            },
        )
        time.sleep(0.025)
    if before_release:
        before_release()
    cdp.call(
        "Input.dispatchMouseEvent",
        {
            "type": "mouseReleased",
            "x": end_x,
            "y": end_y,
            "button": "left",
            "buttons": 0,
            "clickCount": 1,
            "pointerType": "mouse",
        },
    )


def int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def interaction_passed(before: dict[str, Any], after: dict[str, Any], tool: str) -> bool:
    entity_count_before = sum(
        int_value(before.get(field)) for field in ("defensesCount", "trapsCount", "effectsCount")
    )
    entity_count_after = sum(
        int_value(after.get(field)) for field in ("defensesCount", "trapsCount", "effectsCount")
    )
    resource_spent = (
        int_value(after.get("resources")) < int_value(before.get("resources"))
        or int_value(after.get("power")) < int_value(before.get("power"))
    )
    deployed = int_value(after.get("deployedAssetCount")) > int_value(before.get("deployedAssetCount"))
    default_use_spent = tool != "basic" or int_value(after.get("basicUses")) < int_value(before.get("basicUses"))
    return entity_count_after > entity_count_before and resource_spent and deployed and default_use_spent


def run_drag_for_viewport(
    browser: str,
    static_port: int,
    output_dir: Path,
    node_id: str,
    viewport_id: str,
    width: int,
    height: int,
    timeout: int,
    tool: str,
) -> dict[str, Any]:
    remote_port = choose_port()
    browser_label = f"ai-td-drag-{node_id}-{viewport_id}"
    with tempfile.TemporaryDirectory(prefix=f"{browser_label}-", dir="/tmp") as tmp:
        proc = launch_browser(browser, remote_port, Path(tmp))
        cdp: CDPClient | None = None
        try:
            tab = wait_for_devtools_page(remote_port, timeout=timeout)
            websocket_url = tab.get("webSocketDebuggerUrl")
            cdp = CDPClient(websocket_url)
            cdp.call("Page.enable")
            cdp.call("Runtime.enable")
            cdp.call(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": width,
                    "height": height,
                    "deviceScaleFactor": 1,
                    "mobile": viewport_id == "mobile",
                },
            )
            url = smoke_url(static_port, node_id)
            cdp.call("Page.navigate", {"url": url})
            selector = f'.toolbar-card[data-tool="{tool}"]'
            wait_result = cdp.eval(js_wait_selector(selector, 9000), timeout_ms=10000)
            if not as_obj(wait_result).get("ok"):
                raise DevToolsProtocolError(f"Battle toolbar did not mount: {wait_result}")
            time.sleep(0.4)
            before = wait_probe(cdp, tool, timeout_seconds=5)
            source = as_obj(cdp.eval(js_tool_center(tool), timeout_ms=3000))
            if not source.get("ok"):
                raise DevToolsProtocolError(f"Tool card unavailable: {source}")
            target = as_obj(before.get("deploymentPoint"))
            if not target:
                raise DevToolsProtocolError(f"No deployment point returned: {before}")
            safe_tool = "".join(char if char.isalnum() or char in "_-" else "_" for char in tool)
            preview: dict[str, Any] = {}

            def capture_preview() -> None:
                time.sleep(0.18)
                preview["snapshot"] = as_obj(cdp.eval(js_probe_snapshot(tool), timeout_ms=3000))
                preview_path = output_dir / f"battle_drag_preview_{node_id}_{safe_tool}_{viewport_id}.png"
                preview.update(capture_screenshot(cdp, preview_path))

            dispatch_drag(cdp, source, target, before_release=capture_preview)
            time.sleep(0.45)
            after = as_obj(cdp.eval(js_probe_snapshot(tool), timeout_ms=3000))
            screenshot_path = output_dir / f"battle_drag_interaction_{node_id}_{safe_tool}_{viewport_id}.png"
            screenshot = capture_screenshot(cdp, screenshot_path)
            passed = interaction_passed(before, after, tool)
            return {
                "node_id": node_id,
                "viewport_id": viewport_id,
                "requested_width": width,
                "requested_height": height,
                "tool": tool,
                "status": "passed" if passed else "failed",
                "url": url,
                "source": source,
                "target": target,
                "before": before,
                "preview": preview,
                "after": after,
                **screenshot,
            }
        finally:
            if cdp:
                cdp.close()
            proc.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=3)
            if proc.poll() is None:
                proc.kill()


def safety_summary() -> dict[str, Any]:
    return {
        "reads_env_file": False,
        "provider_call_count": 0,
        "world_mutation_count": 0,
        "runtime_activation_allowed": False,
        "stores_provider_body": False,
    }


def build_unavailable_report(
    output_dir: Path,
    browser: str | None,
    candidates: list[dict[str, str | None]],
    failures: list[dict[str, Any]],
    node_id: str,
    viewport_ids: list[str],
    tool: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "status": "browser_unavailable",
        "browser_available": browser is not None,
        "browser_executable": browser,
        "browser_candidates": candidates,
        "output_dir": str(output_dir),
        "node_id": node_id,
        "tool": tool,
        "viewport_ids": viewport_ids,
        "expected_interaction_count": len(viewport_ids),
        "passed_interaction_count": 0,
        "captured_screenshot_count": 0,
        "interactions": [],
        "failures": failures,
        "smoke_mode": {
            "query": "static=1&battleVisualSmoke=1&nodeId=<node_id>",
            "primary_interaction": "drag_tool_card_to_battle_cell",
            "player_runtime_mutation": False,
        },
        "safety_summary": safety_summary(),
    }


def build_report(
    output_dir: Path,
    browser: str,
    candidates: list[dict[str, str | None]],
    interactions: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    node_id: str,
    viewport_ids: list[str],
    tool: str,
) -> dict[str, Any]:
    expected = len(viewport_ids)
    passed = [item for item in interactions if item.get("status") == "passed"]
    status = "captured" if len(passed) == expected and not failures else "failed"
    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "status": status,
        "browser_available": True,
        "browser_executable": browser,
        "browser_candidates": candidates,
        "output_dir": str(output_dir),
        "node_id": node_id,
        "tool": tool,
        "viewport_ids": viewport_ids,
        "expected_interaction_count": expected,
        "passed_interaction_count": len(passed),
        "captured_screenshot_count": len(interactions),
        "interactions": interactions,
        "failures": failures,
        "smoke_mode": {
            "query": "static=1&battleVisualSmoke=1&nodeId=<node_id>",
            "primary_interaction": "drag_tool_card_to_battle_cell",
            "player_runtime_mutation": False,
        },
        "safety_summary": safety_summary(),
    }


def write_report(output_dir: Path, report: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / REPORT_NAME
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--browser-bin", help="Path or command name for a Chromium-compatible browser.")
    parser.add_argument("--allow-missing-browser", action="store_true")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--node-id", default=DEFAULT_NODE_ID)
    parser.add_argument("--tool", default="basic", help="Projected battle toolbar tool id to drag.")
    parser.add_argument(
        "--viewport",
        action="append",
        help="Viewport to capture, e.g. desktop=1440x900. Defaults to desktop and mobile.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    viewports = parse_viewports(args.viewport)
    viewport_ids = list(viewports.keys())
    candidates = browser_candidates(args.browser_bin)
    browser = find_browser(args.browser_bin)
    if not browser:
        report = build_unavailable_report(
            output_dir,
            None,
            candidates,
            [{"error": "No Chromium-compatible browser executable found."}],
            args.node_id,
            viewport_ids,
            args.tool,
        )
        report_path = write_report(output_dir, report)
        print(f"BROWSER_UNAVAILABLE battle drag interaction smoke: {report_path}")
        return 0 if args.allow_missing_browser else 2

    server, static_port = start_static_server()
    interactions: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    try:
        for viewport_id, (width, height) in viewports.items():
            try:
                interactions.append(
                    run_drag_for_viewport(
                        browser,
                        static_port,
                        output_dir,
                        args.node_id,
                        viewport_id,
                        width,
                        height,
                        args.timeout,
                        args.tool,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - collect viewport failures.
                failures.append(
                    {
                        "node_id": args.node_id,
                        "viewport_id": viewport_id,
                        "error": type(exc).__name__,
                        "message": str(exc),
                    }
                )
    finally:
        server.shutdown()
        server.server_close()

    report = build_report(output_dir, browser, candidates, interactions, failures, args.node_id, viewport_ids, args.tool)
    report_path = write_report(output_dir, report)
    print(f"{report['status'].upper()} battle drag interaction smoke: {report_path}")
    for item in report.get("interactions", []):
        print(f"- {item['viewport_id']} {item['status']}: {item.get('path')}")
    return 0 if report["status"] == "captured" else 1


if __name__ == "__main__":
    raise SystemExit(main())
