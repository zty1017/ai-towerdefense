#!/usr/bin/env python3
"""Capture and verify strategic-map zoom, drag, bounds, and reset behavior."""

from __future__ import annotations

import argparse
import contextlib
import json
import tempfile
import time
from pathlib import Path
from typing import Any

from capture_frontend_flow_visual_smoke import (
    CDPClient,
    DevToolsProtocolError,
    as_obj,
    browser_candidates,
    capture_screenshot,
    choose_port,
    find_browser,
    js_click,
    js_wait_selector,
    launch_browser,
    parse_viewports,
    start_static_server,
    wait_for_devtools_page,
)


SCHEMA_VERSION = "strategic_map_interaction_smoke_report.v0.1"
MAP_STEPS = (
    ("[data-action='continue']", "[data-action='begin-world']"),
    ("[data-action='begin-world']", "[data-action='opening-skip']"),
    ("[data-action='opening-skip']", "[data-map-camera-svg]"),
)


def js_map_snapshot() -> str:
    return """
      (() => {
        const map = document.querySelector('.strategic-map');
        const svg = document.querySelector('[data-map-camera-svg]');
        const readout = document.querySelector('[data-map-camera-readout]');
        if (!map || !svg || !readout) return { ok: false };
        const rect = map.getBoundingClientRect();
        const viewBox = (svg.getAttribute('viewBox') || '')
          .trim()
          .split(/\s+/)
          .map(Number);
        return {
          ok: viewBox.length === 4 && viewBox.every(Number.isFinite),
          viewBox,
          zoomText: readout.textContent.trim(),
          rect: {
            left: rect.left,
            top: rect.top,
            width: rect.width,
            height: rect.height,
          },
          dragging: map.classList.contains('is-dragging'),
        };
      })()
    """


def view_box(snapshot: dict[str, Any]) -> list[float]:
    raw = snapshot.get("viewBox")
    if not isinstance(raw, list) or len(raw) != 4:
        return []
    try:
        return [float(value) for value in raw]
    except (TypeError, ValueError):
        return []


def view_box_changed(before: dict[str, Any], after: dict[str, Any], *, axes: range) -> bool:
    left = view_box(before)
    right = view_box(after)
    return bool(left and right) and any(abs(left[index] - right[index]) > 0.1 for index in axes)


def view_box_matches(before: dict[str, Any], after: dict[str, Any]) -> bool:
    left = view_box(before)
    right = view_box(after)
    return bool(left and right) and all(abs(a - b) <= 0.05 for a, b in zip(left, right))


def screenshot_record(cdp: CDPClient, output_dir: Path, viewport_id: str, phase: str) -> dict[str, Any]:
    path = output_dir / f"strategic_map_{viewport_id}_{phase}.png"
    return {"viewport_id": viewport_id, "phase": phase, **capture_screenshot(cdp, path)}


def run_for_viewport(
    browser: str,
    static_port: int,
    output_dir: Path,
    viewport_id: str,
    width: int,
    height: int,
    timeout: int,
) -> dict[str, Any]:
    remote_port = choose_port()
    with tempfile.TemporaryDirectory(prefix=f"ai-td-map-{viewport_id}-", dir="/tmp") as tmp:
        proc = launch_browser(browser, remote_port, Path(tmp))
        cdp: CDPClient | None = None
        try:
            tab = wait_for_devtools_page(remote_port, timeout=timeout)
            cdp = CDPClient(str(tab.get("webSocketDebuggerUrl")))
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
            cdp.call(
                "Page.navigate",
                {
                    "url": (
                        f"http://127.0.0.1:{static_port}"
                        "/frontend/index.html?static=1&flowVisualSmoke=1"
                    )
                },
            )
            boot = cdp.eval(js_wait_selector("[data-action='continue']", 9000), timeout_ms=10000)
            if not as_obj(boot).get("ok"):
                raise DevToolsProtocolError(f"frontend did not boot: {boot}")
            for click_selector, wait_selector in MAP_STEPS:
                clicked = cdp.eval(js_click(click_selector))
                if not as_obj(clicked).get("ok"):
                    raise DevToolsProtocolError(f"failed to click {click_selector}: {clicked}")
                waited = cdp.eval(js_wait_selector(wait_selector, 7000), timeout_ms=8000)
                if not as_obj(waited).get("ok"):
                    raise DevToolsProtocolError(f"failed to reach {wait_selector}: {waited}")
            time.sleep(0.4)

            initial = as_obj(cdp.eval(js_map_snapshot()))
            screenshots = [screenshot_record(cdp, output_dir, viewport_id, "initial")]
            for _ in range(2):
                clicked = cdp.eval(js_click("[data-action='map-zoom-in']"))
                if not as_obj(clicked).get("ok"):
                    raise DevToolsProtocolError(f"zoom button failed: {clicked}")
                time.sleep(0.12)
            zoomed = as_obj(cdp.eval(js_map_snapshot()))

            rect = as_obj(zoomed.get("rect"))
            start_x = float(rect.get("left") or 0) + float(rect.get("width") or 0) * 0.57
            start_y = float(rect.get("top") or 0) + float(rect.get("height") or 0) * 0.54
            end_x = start_x - min(150.0, float(rect.get("width") or 0) * 0.16)
            end_y = start_y - min(70.0, float(rect.get("height") or 0) * 0.10)
            cdp.call(
                "Input.dispatchMouseEvent",
                {"type": "mousePressed", "x": start_x, "y": start_y, "button": "left", "buttons": 1, "clickCount": 1},
            )
            for step in range(1, 7):
                ratio = step / 6
                cdp.call(
                    "Input.dispatchMouseEvent",
                    {
                        "type": "mouseMoved",
                        "x": start_x + (end_x - start_x) * ratio,
                        "y": start_y + (end_y - start_y) * ratio,
                        "button": "left",
                        "buttons": 1,
                    },
                )
            cdp.call(
                "Input.dispatchMouseEvent",
                {"type": "mouseReleased", "x": end_x, "y": end_y, "button": "left", "buttons": 0, "clickCount": 1},
            )
            time.sleep(0.18)
            dragged = as_obj(cdp.eval(js_map_snapshot()))
            screenshots.append(screenshot_record(cdp, output_dir, viewport_id, "dragged"))

            reset_click = cdp.eval(js_click("[data-action='map-camera-reset']"))
            if not as_obj(reset_click).get("ok"):
                raise DevToolsProtocolError(f"reset button failed: {reset_click}")
            time.sleep(0.15)
            reset = as_obj(cdp.eval(js_map_snapshot()))
            screenshots.append(screenshot_record(cdp, output_dir, viewport_id, "reset"))

            checks = {
                "initial_snapshot_valid": initial.get("ok") is True,
                "zoom_reduces_view_box": view_box_changed(initial, zoomed, axes=range(2, 4))
                and view_box(zoomed)[2] < view_box(initial)[2],
                "drag_changes_camera_center": view_box_changed(zoomed, dragged, axes=range(0, 2)),
                "drag_class_released": dragged.get("dragging") is False,
                "reset_restores_auto_camera": view_box_matches(initial, reset),
            }
            return {
                "viewport_id": viewport_id,
                "requested_width": width,
                "requested_height": height,
                "status": "passed" if all(checks.values()) else "failed",
                "checks": checks,
                "initial": initial,
                "zoomed": zoomed,
                "dragged": dragged,
                "reset": reset,
                "drag": {
                    "start": {"x": start_x, "y": start_y},
                    "end": {"x": end_x, "y": end_y},
                },
                "screenshots": screenshots,
            }
        finally:
            if cdp:
                cdp.close()
            proc.terminate()
            with contextlib.suppress(Exception):
                proc.wait(timeout=3)
            if proc.poll() is None:
                proc.kill()


def build_report(
    output_dir: Path,
    browser: str | None,
    candidates: list[dict[str, str | None]],
    interactions: list[dict[str, Any]],
    failures: list[dict[str, Any]],
) -> dict[str, Any]:
    screenshots = [item for interaction in interactions for item in interaction.get("screenshots", [])]
    passed = sum(interaction.get("status") == "passed" for interaction in interactions)
    if browser is None:
        status = "browser_unavailable"
    else:
        status = "captured" if interactions and passed == len(interactions) and not failures else "failed"
    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": "P3.9-strategic-map-controller-browser-smoke",
        "status": status,
        "browser_available": browser is not None,
        "browser_executable": browser,
        "browser_candidates": candidates,
        "output_dir": str(output_dir),
        "viewport_ids": [item.get("viewport_id") for item in interactions],
        "expected_interaction_count": len(interactions),
        "passed_interaction_count": passed,
        "captured_screenshot_count": len(screenshots),
        "interactions": interactions,
        "screenshots": screenshots,
        "failures": failures,
        "smoke_mode": {
            "query": "static=1&flowVisualSmoke=1",
            "purpose": "Verify strategic-map camera interaction without backend or provider calls.",
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
    path = output_dir / "strategic_map_interaction_smoke_report.v0.1.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--browser-bin")
    parser.add_argument("--allow-missing-browser", action="store_true")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--viewport", action="append", help="Viewport as id=WIDTHxHEIGHT.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    candidates = browser_candidates(args.browser_bin)
    browser = find_browser(args.browser_bin)
    if not browser:
        report = build_report(
            args.output_dir,
            None,
            candidates,
            [],
            [{"error": "No Chromium-compatible browser executable found."}],
        )
        report_path = write_report(args.output_dir, report)
        print(f"BROWSER_UNAVAILABLE strategic map interaction smoke: {report_path}")
        return 0 if args.allow_missing_browser else 2

    server, static_port = start_static_server()
    interactions: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    try:
        for viewport_id, (width, height) in parse_viewports(args.viewport).items():
            try:
                interactions.append(
                    run_for_viewport(
                        browser,
                        static_port,
                        args.output_dir,
                        viewport_id,
                        width,
                        height,
                        args.timeout,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - preserve structured browser evidence.
                failures.append({"viewport_id": viewport_id, "error": type(exc).__name__, "message": str(exc)})
    finally:
        server.shutdown()
        server.server_close()

    report = build_report(args.output_dir, browser, candidates, interactions, failures)
    report_path = write_report(args.output_dir, report)
    print(f"{report['status'].upper()} strategic map interaction smoke: {report_path}")
    for item in report["screenshots"]:
        print(f"- {item['viewport_id']} {item['phase']}: {item['path']}")
    return 0 if report["status"] == "captured" else 1


if __name__ == "__main__":
    raise SystemExit(main())
