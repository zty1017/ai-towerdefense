#!/usr/bin/env python3
"""Capture the API-mode frontend feature projection flow in Chromium."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from capture_frontend_flow_visual_smoke import (
    CDPClient,
    browser_candidates,
    capture_screenshot,
    choose_port,
    find_browser,
    js_click,
    js_wait_selector,
    launch_browser,
    wait_for_devtools_page,
    wait_for_http_json,
)
from capture_battle_drag_interaction_smoke import (
    dispatch_drag,
    interaction_passed,
    js_probe_snapshot,
    js_tool_center,
    wait_probe,
)


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "frontend_feature_projection_api_smoke_report.v0.1"


def start_backend(port: int, db_path: Path) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["APP_DB_PATH"] = str(db_path)
    env["PYTHONPATH"] = str(ROOT / "backend")
    env["AI_TD_LIVE_COMPILATION"] = "off"
    env["AI_TD_LIVE_MEDIA"] = "off"
    env["AI_TD_LIVE_WORLD_EVOLUTION"] = "off"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    wait_for_http_json(port, "/api/health", timeout=12)
    return process


def wait_for_condition(cdp: CDPClient, expression: str, timeout_ms: int = 9000) -> Any:
    result = cdp.eval(
        f"""
        (async () => {{
          const deadline = Date.now() + {int(timeout_ms)};
          while (Date.now() < deadline) {{
            const value = await ({expression});
            if (value) return {{ ok: true, value }};
            await new Promise((resolve) => setTimeout(resolve, 100));
          }}
          return {{ ok: false }};
        }})()
        """,
        timeout_ms=timeout_ms + 1000,
    )
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise RuntimeError(f"condition timed out: {expression}")
    return result.get("value")


def click_and_wait(cdp: CDPClient, click_selector: str, wait_selector: str) -> None:
    clicked = cdp.eval(js_click(click_selector))
    if not isinstance(clicked, dict) or clicked.get("ok") is not True:
        raise RuntimeError(f"click failed: {click_selector}: {clicked}")
    waited = cdp.eval(js_wait_selector(wait_selector, 12000), timeout_ms=13000)
    if not isinstance(waited, dict) or waited.get("ok") is not True:
        raise RuntimeError(f"selector timed out: {wait_selector}: {waited}")


def runtime_projection_expression(feature_id: str) -> str:
    return f"""
      (async () => {{
        const profile = JSON.parse(
          localStorage.getItem('ai_compiled_td_frontend_profile_v1') || '{{}}'
        );
        if (!profile.sessionId) return null;
        const response = await fetch(
          `/api/sessions/${{encodeURIComponent(profile.sessionId)}}/runtime/feature-snapshots?node_id=gray_lantern_station`
        );
        if (!response.ok) return null;
        const body = await response.json();
        const bundle = body.payload && body.payload.activated_runtime_bundle;
        return bundle && bundle.feature_snapshots && bundle.feature_snapshots[{json.dumps(feature_id)}];
      }})()
    """


def runtime_activation_expression() -> str:
    return """
      (async () => {
        const profile = JSON.parse(
          localStorage.getItem('ai_compiled_td_frontend_profile_v1') || '{}'
        );
        if (!profile.sessionId) return null;
        const sessionId = encodeURIComponent(profile.sessionId);
        const [activationResponse, runtimeResponse] = await Promise.all([
          fetch(`/api/sessions/${sessionId}/runtime/activations`),
          fetch(`/api/sessions/${sessionId}/runtime/feature-snapshots?node_id=gray_lantern_station`),
        ]);
        if (!activationResponse.ok || !runtimeResponse.ok) return null;
        const activationBody = await activationResponse.json();
        const runtimeBody = await runtimeResponse.json();
        const receipts = activationBody.activation_receipts || [];
        const receipt = receipts.find((item) => item.status === 'activated');
        const bundle = runtimeBody.payload && runtimeBody.payload.activated_runtime_bundle;
        const activationIds = bundle && bundle.runtime_selection
          ? bundle.runtime_selection.session_activation_ids || []
          : [];
        if (!receipt || !activationIds.includes(receipt.activation_id)) return null;
        const objectId = (receipt.runtime_effect.activated_object_ids || [])[0];
        const object = (((bundle || {}).capabilities || {}).battle_objects || [])
          .find((item) => item.object_id === objectId);
        if (!object || !object.media_refs || !object.source_runtime_ref) return null;
        return {
          activationId: receipt.activation_id,
          objectId,
          displayName: object.display_name,
          assetKind: object.asset_kind,
          toolId: object.tool_id || null,
          placementMode: object.behavior_abi && object.behavior_abi.placement
            ? object.behavior_abi.placement.mode
            : null,
          behaviorGate: receipt.validation.behavior_abi.status,
          mediaGate: receipt.validation.media.status,
        };
      })()
    """


def run_smoke(
    browser: str, output_dir: Path, timeout: int, intent_text: str
) -> dict[str, Any]:
    backend_port = choose_port()
    remote_port = choose_port()
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ai-td-feature-api-", dir="/tmp") as tmp:
        tmp_path = Path(tmp)
        backend = start_backend(backend_port, tmp_path / "feature_projection.db")
        browser_process = launch_browser(browser, remote_port, tmp_path / "browser")
        cdp: CDPClient | None = None
        try:
            tab = wait_for_devtools_page(remote_port, timeout=timeout)
            cdp = CDPClient(str(tab["webSocketDebuggerUrl"]))
            cdp.call("Page.enable")
            cdp.call("Runtime.enable")
            cdp.call(
                "Emulation.setDeviceMetricsOverride",
                {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False},
            )
            cdp.call(
                "Page.navigate",
                {
                    "url": (
                        f"http://127.0.0.1:{backend_port}"
                        "/frontend/index.html?flowVisualSmoke=1"
                    )
                },
            )
            waited = cdp.eval(js_wait_selector("[data-action='continue']", 12000), timeout_ms=13000)
            if not isinstance(waited, dict) or waited.get("ok") is not True:
                raise RuntimeError(f"frontend did not boot: {waited}")

            click_and_wait(cdp, "[data-action='continue']", "[data-action='begin-world']")
            click_and_wait(cdp, "[data-action='begin-world']", "[data-action='opening-skip']")
            click_and_wait(cdp, "[data-action='opening-skip']", "[data-action='enter-node']")
            click_and_wait(cdp, "[data-action='enter-node']", "[data-action='proposal-refresh']")

            intent_result = cdp.eval(
                f"""
                (() => {{
                  const input = document.querySelector('.workshop-input');
                  if (!input) return {{ ok: false }};
                  input.value = {json.dumps(intent_text, ensure_ascii=False)};
                  input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                  return {{ ok: true, value: input.value }};
                }})()
                """
            )
            if not isinstance(intent_result, dict) or intent_result.get("ok") is not True:
                raise RuntimeError("workshop intent input was unavailable")

            participant_visible = wait_for_condition(
                cdp,
                "document.querySelector('#app').innerText.includes('可参与当前节点的现场试作评审')",
            )
            cdp.eval(js_click("[data-action='proposal-refresh']"))
            workshop_snapshot = wait_for_condition(
                cdp,
                f"""
                (async () => {{
                  const snapshot = await {runtime_projection_expression('workshop')};
                  const proposal = snapshot && snapshot.contributions.find(
                    (item) => item.kind === 'proposal_hint'
                  );
                  const title = document.querySelector('.workshop-review.has-proposal h2');
                  return proposal && title && title.textContent.trim() === proposal.payload.title
                    ? {{ proposalId: proposal.contribution_id, title: proposal.payload.title }}
                    : null;
                }})()
                """,
                timeout_ms=12000,
            )
            workshop_shot = capture_screenshot(
                cdp,
                output_dir / "feature_projection_api_workshop.png",
            )

            click_and_wait(cdp, "[data-action='confirm-prototype']", "#battleCanvas")
            activation_snapshot = wait_for_condition(
                cdp,
                runtime_activation_expression(),
                timeout_ms=12000,
            )
            pause_result = cdp.eval(js_click("#pauseButton"))
            if not isinstance(pause_result, dict) or pause_result.get("ok") is not True:
                raise RuntimeError(f"battle pause failed before compiled tool drag: {pause_result}")
            time.sleep(0.1)

            drag_before = wait_probe(cdp, "sample", timeout_seconds=4)
            drag_source = cdp.eval(js_tool_center("sample"), timeout_ms=3000)
            drag_target = drag_before.get("deploymentPoint")
            if not isinstance(drag_source, dict) or drag_source.get("ok") is not True:
                raise RuntimeError(f"compiled sample card unavailable: {drag_source}")
            if not isinstance(drag_target, dict):
                raise RuntimeError(f"compiled sample has no deployment point: {drag_before}")
            dispatch_drag(cdp, drag_source, drag_target)
            time.sleep(0.45)
            drag_after = cdp.eval(js_probe_snapshot("sample"), timeout_ms=3000)
            if not isinstance(drag_after, dict) or not interaction_passed(
                drag_before, drag_after, "sample"
            ):
                raise RuntimeError(
                    f"compiled sample did not mutate battle state: before={drag_before}, after={drag_after}"
                )
            activation_shot = capture_screenshot(
                cdp,
                output_dir / "feature_projection_api_activated_sample.png",
            )
            resume_result = cdp.eval(js_click("#pauseButton"))
            if not isinstance(resume_result, dict) or resume_result.get("ok") is not True:
                raise RuntimeError(f"battle resume failed after compiled tool drag: {resume_result}")
            waited = cdp.eval(
                js_wait_selector("[data-action='return-map']", 20000),
                timeout_ms=21000,
            )
            if not isinstance(waited, dict) or waited.get("ok") is not True:
                raise RuntimeError(f"settlement did not appear: {waited}")
            settlement_snapshot = wait_for_condition(
                cdp,
                f"""
                (async () => {{
                  const snapshot = await {runtime_projection_expression('settlement')};
                  if (!snapshot) return null;
                  const slots = snapshot.contributions.map((item) => item.slot);
                  return slots.includes('result_summary') && slots.includes('world_delta')
                    ? {{ slots }}
                    : null;
                }})()
                """,
            )
            settlement_shot = capture_screenshot(
                cdp,
                output_dir / "feature_projection_api_settlement.png",
            )
            return {
                "status": "passed",
                "checks": {
                    "intent_text": intent_text,
                    "workshop_participant_projection_visible": participant_visible is True,
                    "workshop_proposal_projection": workshop_snapshot,
                    "runtime_activation_projection": activation_snapshot,
                    "compiled_tool_drag": {
                        "status": "passed",
                        "tool": "sample",
                        "before": drag_before,
                        "after": drag_after,
                    },
                    "settlement_projection": settlement_snapshot,
                },
                "screenshots": [workshop_shot, activation_shot, settlement_shot],
            }
        finally:
            if cdp:
                cdp.close()
            browser_process.terminate()
            backend.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):
                browser_process.wait(timeout=3)
            with contextlib.suppress(subprocess.TimeoutExpired):
                backend.wait(timeout=3)
            if browser_process.poll() is None:
                browser_process.kill()
            if backend.poll() is None:
                backend.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--browser-bin")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument(
        "--intent",
        default="我想做一个能拖慢影潮的临时装置。",
        help="Player intent entered in the workshop before proposal generation.",
    )
    args = parser.parse_args()
    browser = find_browser(args.browser_bin)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "browser_available": browser is not None,
        "browser_executable": browser,
        "browser_candidates": browser_candidates(args.browser_bin),
        "safety_summary": {
            "reads_env_file": False,
            "provider_call_count": 0,
            "runtime_activation_allowed": True,
            "runtime_activation_count": 1,
            "stores_provider_body": False,
            "world_mutation_count": 3,
        },
    }
    try:
        if not browser:
            raise RuntimeError("No Chromium-compatible browser executable found")
        report.update(run_smoke(browser, args.output_dir, args.timeout, args.intent))
    except Exception as exc:  # noqa: BLE001 - write a structured smoke failure.
        report.update(
            {
                "status": "failed",
                "checks": {},
                "screenshots": [],
                "failure": {"type": type(exc).__name__, "message": str(exc)},
            }
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.output_dir / "frontend_feature_projection_api_smoke_report.v0.1.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"{str(report['status']).upper()} feature projection API smoke: {report_path}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
