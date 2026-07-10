#!/usr/bin/env python3
"""Capture battle screenshots for every MVP frontend battle node.

This browser smoke is intentionally narrower than the full player flow smoke:
it opens the no-build frontend directly in battle smoke mode for each current
MVP node and captures desktop/mobile screenshots. It does not call providers,
read .env, mutate world state, or activate review-only runtime artifacts.
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
from typing import Any
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


SCHEMA_VERSION = "frontend_multinode_visual_smoke_report.v0.1"
TASK_ID = "P1-D-37-frontend-multinode-visual-smoke"
DEFAULT_NODES = (
    "gray_lantern_station",
    "lamp_wick_store",
    "old_signal_tower",
)
NODE_LABELS = {
    "gray_lantern_station": "灰灯驿站",
    "lamp_wick_store": "灯芯仓",
    "old_signal_tower": "旧信号塔",
}


def js_battle_snapshot() -> str:
    return r"""
(() => {
  const canvas = document.querySelector("#battleCanvas");
  const nodeTitle = Array.from(document.querySelectorAll(".top-stat strong"))
    .map((item) => item.innerText || "")
    .find(Boolean) || "";
  return {
    title: document.title,
    bodyText: (document.body && document.body.innerText || "").slice(0, 1600),
    nodeTitle,
    canvasCount: document.querySelectorAll("canvas").length,
    buttonCount: document.querySelectorAll("button").length,
    imageCount: document.querySelectorAll("img").length,
    battleCanvasClientWidth: canvas ? Math.round(canvas.getBoundingClientRect().width) : 0,
    battleCanvasClientHeight: canvas ? Math.round(canvas.getBoundingClientRect().height) : 0,
    battleCanvasBitmapWidth: canvas ? canvas.width : 0,
    battleCanvasBitmapHeight: canvas ? canvas.height : 0
  };
})()
"""


def smoke_url(static_port: int, node_id: str) -> str:
    query = urlencode(
        {
            "static": "1",
            "battleVisualSmoke": "1",
            "nodeId": node_id,
        }
    )
    return f"http://127.0.0.1:{static_port}/frontend/index.html?{query}"


def run_node_viewport_capture(
    browser: str,
    static_port: int,
    output_dir: Path,
    node_id: str,
    viewport_id: str,
    width: int,
    height: int,
    timeout: int,
) -> dict[str, Any]:
    remote_port = choose_port()
    browser_label = f"ai-td-multinode-{node_id}-{viewport_id}"
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
            cdp.call("Page.navigate", {"url": smoke_url(static_port, node_id)})
            wait_result = cdp.eval(js_wait_selector("#battleCanvas", 9000), timeout_ms=10000)
            if not as_obj(wait_result).get("ok"):
                raise DevToolsProtocolError(f"Battle canvas did not mount: {wait_result}")
            time.sleep(0.45)
            screenshot_path = output_dir / f"frontend_multinode_{node_id}_{viewport_id}.png"
            screenshot = capture_screenshot(cdp, screenshot_path)
            dom = cdp.eval(js_battle_snapshot())
            return {
                "node_id": node_id,
                "expected_label": NODE_LABELS.get(node_id, ""),
                "viewport_id": viewport_id,
                "requested_width": width,
                "requested_height": height,
                "status": "captured",
                "url": smoke_url(static_port, node_id),
                "dom": dom,
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


def build_unavailable_report(
    output_dir: Path,
    browser: str | None,
    candidates: list[dict[str, str | None]],
    failures: list[dict[str, Any]],
    node_ids: list[str],
    viewport_ids: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "status": "browser_unavailable",
        "browser_available": browser is not None,
        "browser_executable": browser,
        "browser_candidates": candidates,
        "output_dir": str(output_dir),
        "node_ids": node_ids,
        "viewport_ids": viewport_ids,
        "expected_screenshot_count": len(node_ids) * len(viewport_ids),
        "captured_screenshot_count": 0,
        "screenshots": [],
        "failures": failures,
        "smoke_mode": {
            "query": "static=1&battleVisualSmoke=1&nodeId=<node_id>",
            "purpose": "Browser-only visual battle smoke across MVP nodes.",
            "player_runtime_mutation": False,
        },
        "safety_summary": {
            "reads_env_file": False,
            "provider_call_count": 0,
            "world_mutation_count": 0,
            "runtime_activation_allowed": False,
            "stores_provider_body": False,
        },
    }


def build_report(
    output_dir: Path,
    browser: str,
    candidates: list[dict[str, str | None]],
    screenshots: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    node_ids: list[str],
    viewport_ids: list[str],
) -> dict[str, Any]:
    expected = len(node_ids) * len(viewport_ids)
    status = "captured" if len(screenshots) == expected and not failures else "failed"
    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "status": status,
        "browser_available": True,
        "browser_executable": browser,
        "browser_candidates": candidates,
        "output_dir": str(output_dir),
        "node_ids": node_ids,
        "viewport_ids": viewport_ids,
        "expected_screenshot_count": expected,
        "captured_screenshot_count": len(screenshots),
        "screenshots": [
            {
                "node_id": item.get("node_id"),
                "expected_label": item.get("expected_label"),
                "viewport_id": item.get("viewport_id"),
                "path": item.get("path"),
                "width": item.get("width"),
                "height": item.get("height"),
                "file_size_bytes": item.get("file_size_bytes"),
                "sha256": item.get("sha256"),
                "url": item.get("url"),
                "title": as_obj(item.get("dom")).get("title"),
                "node_title": as_obj(item.get("dom")).get("nodeTitle"),
                "canvas_count": as_obj(item.get("dom")).get("canvasCount"),
                "button_count": as_obj(item.get("dom")).get("buttonCount"),
                "image_count": as_obj(item.get("dom")).get("imageCount"),
                "battle_canvas_client_width": as_obj(item.get("dom")).get(
                    "battleCanvasClientWidth"
                ),
                "battle_canvas_client_height": as_obj(item.get("dom")).get(
                    "battleCanvasClientHeight"
                ),
                "battle_canvas_bitmap_width": as_obj(item.get("dom")).get(
                    "battleCanvasBitmapWidth"
                ),
                "battle_canvas_bitmap_height": as_obj(item.get("dom")).get(
                    "battleCanvasBitmapHeight"
                ),
            }
            for item in screenshots
        ],
        "failures": failures,
        "smoke_mode": {
            "query": "static=1&battleVisualSmoke=1&nodeId=<node_id>",
            "purpose": "Browser-only visual battle smoke across MVP nodes.",
            "player_runtime_mutation": False,
        },
        "safety_summary": {
            "reads_env_file": False,
            "provider_call_count": 0,
            "world_mutation_count": 0,
            "runtime_activation_allowed": False,
            "stores_provider_body": False,
        },
    }


def write_report(output_dir: Path, report: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "frontend_multinode_visual_smoke_report.v0.1.json"
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
    parser.add_argument(
        "--node-id",
        action="append",
        choices=DEFAULT_NODES,
        help="Battle node to capture. Defaults to all current MVP nodes.",
    )
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
    node_ids = list(args.node_id or DEFAULT_NODES)
    viewports = parse_viewports(args.viewport)
    candidates = browser_candidates(args.browser_bin)
    browser = find_browser(args.browser_bin)
    viewport_ids = list(viewports.keys())
    if not browser:
        report = build_unavailable_report(
            output_dir,
            None,
            candidates,
            [{"error": "No Chromium-compatible browser executable found."}],
            node_ids,
            viewport_ids,
        )
        report_path = write_report(output_dir, report)
        print(f"BROWSER_UNAVAILABLE frontend multinode visual smoke: {report_path}")
        return 0 if args.allow_missing_browser else 2

    server, static_port = start_static_server()
    screenshots: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    try:
        for node_id in node_ids:
            for viewport_id, (width, height) in viewports.items():
                try:
                    screenshots.append(
                        run_node_viewport_capture(
                            browser,
                            static_port,
                            output_dir,
                            node_id,
                            viewport_id,
                            width,
                            height,
                            args.timeout,
                        )
                    )
                except Exception as exc:  # noqa: BLE001 - collect matrix failures.
                    failures.append(
                        {
                            "node_id": node_id,
                            "viewport_id": viewport_id,
                            "error": type(exc).__name__,
                            "message": str(exc),
                        }
                    )
    finally:
        server.shutdown()
        server.server_close()

    report = build_report(output_dir, browser, candidates, screenshots, failures, node_ids, viewport_ids)
    report_path = write_report(output_dir, report)
    print(f"{report['status'].upper()} frontend multinode visual smoke: {report_path}")
    for item in report.get("screenshots", []):
        print(f"- {item['node_id']} {item['viewport_id']}: {item['path']}")
    return 0 if report["status"] == "captured" else 1


if __name__ == "__main__":
    raise SystemExit(main())
