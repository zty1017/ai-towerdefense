#!/usr/bin/env python3
"""Capture browser screenshots for the MVP frontend player flow.

The tool uses only the Python standard library and a Chromium-compatible
browser. It drives the no-build frontend through Chrome DevTools Protocol,
captures the player-facing screens, and writes a structured evidence report.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import http.client
import http.server
import json
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VIEWPORTS = {
    "desktop": (1440, 900),
    "mobile": (390, 844),
}
BROWSER_CANDIDATES = (
    "chromium",
    "chromium-browser",
    "google-chrome",
    "google-chrome-stable",
    "microsoft-edge",
    "brave-browser",
)
PLAYWRIGHT_BROWSER_GLOBS = (
    "/tmp/pw-browsers/chromium-*/chrome-linux64/chrome",
    "/tmp/pw-browsers/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell",
)
PLAYWRIGHT_BROWSER_CACHE_PATTERNS = (
    "chromium-*/chrome-linux64/chrome",
    "chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell",
)
WSL_WINDOWS_BROWSER_PATHS = (
    "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe",
    "/mnt/c/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "/mnt/c/Program Files/Microsoft/Edge/Application/msedge.exe",
    "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    "/mnt/c/Program Files/BraveSoftware/Brave-Browser/Application/brave.exe",
    "/mnt/c/Program Files (x86)/BraveSoftware/Brave-Browser/Application/brave.exe",
)
FLOW_STEPS = (
    {
        "step_id": "profile",
        "label": "本地档案入口",
        "wait_selector": "main.screen [data-action='continue']",
    },
    {
        "step_id": "world_config",
        "label": "本局档案配置",
        "click_selector": "[data-action='continue']",
        "wait_selector": "[data-action='begin-world']",
    },
    {
        "step_id": "opening",
        "label": "开场叙事",
        "click_selector": "[data-action='begin-world']",
        "wait_selector": "[data-action='opening-skip']",
    },
    {
        "step_id": "map",
        "label": "大地图态势",
        "click_selector": "[data-action='opening-skip']",
        "wait_selector": "[data-action='enter-node']",
    },
    {
        "step_id": "workshop",
        "label": "现场试作工坊",
        "click_selector": "[data-action='enter-node']",
        "wait_selector": "[data-action='confirm-prototype']",
    },
    {
        "step_id": "battle",
        "label": "塔防战斗",
        "click_selector": "[data-action='confirm-prototype']",
        "wait_selector": "#battleCanvas",
        "post_wait_ms": 450,
    },
    {
        "step_id": "settlement",
        "label": "战后结算",
        "wait_selector": "[data-action='return-map']",
        "wait_timeout_ms": 12000,
    },
)


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


class DevToolsProtocolError(RuntimeError):
    pass


class WebSocketClient:
    def __init__(self, url: str, timeout: float = 15.0):
        parsed = urlparse(url)
        if parsed.scheme != "ws":
            raise ValueError(f"Only ws:// URLs are supported: {url}")
        self.host = parsed.hostname or "127.0.0.1"
        self.port = parsed.port or 80
        self.path = parsed.path
        if parsed.query:
            self.path += f"?{parsed.query}"
        self.timeout = timeout
        self.sock = socket.create_connection((self.host, self.port), timeout=timeout)
        self.sock.settimeout(timeout)
        self._handshake()

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self.sock.close()

    def _handshake(self) -> None:
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        self.sock.sendall(request.encode("ascii"))
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self.sock.recv(4096)
            if not chunk:
                break
            response += chunk
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise DevToolsProtocolError(
                f"WebSocket handshake failed: {response[:200]!r}"
            )

    def send_json(self, value: dict[str, Any]) -> None:
        payload = json.dumps(value, separators=(",", ":")).encode("utf-8")
        mask = os.urandom(4)
        header = bytearray([0x81])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack(">H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack(">Q", length))
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)

    def receive_json(self) -> dict[str, Any]:
        while True:
            frame = self._receive_frame()
            opcode = frame["opcode"]
            payload = frame["payload"]
            if opcode == 0x1:
                return json.loads(payload.decode("utf-8"))
            if opcode == 0x8:
                raise DevToolsProtocolError("WebSocket closed by browser")
            if opcode == 0x9:
                self._send_control(0xA, payload)

    def _send_control(self, opcode: int, payload: bytes) -> None:
        if len(payload) > 125:
            payload = payload[:125]
        mask = os.urandom(4)
        header = bytes([0x80 | opcode, 0x80 | len(payload)])
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(header + mask + masked)

    def _receive_exact(self, size: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < size:
            chunk = self.sock.recv(size - len(chunks))
            if not chunk:
                raise DevToolsProtocolError("Unexpected EOF from WebSocket")
            chunks.extend(chunk)
        return bytes(chunks)

    def _receive_frame(self) -> dict[str, Any]:
        first, second = self._receive_exact(2)
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        length = second & 0x7F
        if length == 126:
            length = struct.unpack(">H", self._receive_exact(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", self._receive_exact(8))[0]
        mask = self._receive_exact(4) if masked else b""
        payload = self._receive_exact(length) if length else b""
        if masked:
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        return {"opcode": opcode, "payload": payload}


class CDPClient:
    def __init__(self, websocket_url: str):
        self.ws = WebSocketClient(websocket_url)
        self.next_id = 1

    def close(self) -> None:
        self.ws.close()

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        message_id = self.next_id
        self.next_id += 1
        self.ws.send_json({"id": message_id, "method": method, "params": params or {}})
        while True:
            message = self.ws.receive_json()
            if message.get("id") != message_id:
                continue
            if "error" in message:
                raise DevToolsProtocolError(
                    f"{method} failed: {json.dumps(message['error'], ensure_ascii=False)}"
                )
            return message.get("result", {})

    def eval(self, expression: str, timeout_ms: int = 5000) -> Any:
        result = self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": True,
                "returnByValue": True,
                "timeout": timeout_ms,
            },
        )
        if as_obj(result.get("exceptionDetails")):
            raise DevToolsProtocolError(json.dumps(result["exceptionDetails"]))
        return as_obj(result.get("result")).get("value")


def as_obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG file")
    return struct.unpack(">II", header[16:24])


def choose_port() -> int:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_static_server() -> tuple[http.server.ThreadingHTTPServer, int]:
    port = choose_port()
    handler = lambda *args, **kwargs: QuietHandler(*args, directory=str(ROOT), **kwargs)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def browser_candidates(override: str | None) -> list[dict[str, str | None]]:
    names = [override] if override else list(BROWSER_CANDIDATES)
    candidates = [
        {"name": name, "path": shutil.which(name) if name else None}
        for name in names
        if name
    ]
    if override and not candidates[0]["path"] and Path(override).exists():
        candidates[0]["path"] = override
    if not override:
        for pattern in PLAYWRIGHT_BROWSER_GLOBS:
            for path in sorted(Path("/").glob(pattern.lstrip("/"))):
                if path.is_file():
                    candidates.append({"name": str(path), "path": str(path)})
        for root in (Path.home() / ".cache/ms-playwright",):
            for pattern in PLAYWRIGHT_BROWSER_CACHE_PATTERNS:
                for path in sorted(root.glob(pattern)):
                    if path.is_file():
                        candidates.append({"name": str(path), "path": str(path)})
        for path in WSL_WINDOWS_BROWSER_PATHS:
            try:
                is_file = Path(path).is_file()
            except OSError:
                is_file = False
            if is_file:
                candidates.append({"name": f"wsl-windows:{Path(path).name}", "path": path})
    seen = set()
    unique = []
    for candidate in candidates:
        key = (candidate["name"], candidate["path"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def find_browser(override: str | None) -> str | None:
    if override and Path(override).exists():
        return override
    for candidate in browser_candidates(override):
        path = candidate["path"]
        if path:
            return path
    return None


def is_windows_browser(browser: str) -> bool:
    normalized = browser.lower().replace("\\", "/")
    return normalized.endswith(".exe") or normalized.startswith("/mnt/c/")


def path_for_browser_arg(path: Path, browser: str) -> str:
    if not is_windows_browser(browser):
        return str(path)
    try:
        result = subprocess.run(
            ["wslpath", "-w", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return str(path)
    converted = result.stdout.strip()
    return converted or str(path)


def wait_for_http_json(port: int, path: str, timeout: float = 10.0) -> Any:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
            conn.request("GET", path)
            response = conn.getresponse()
            body = response.read()
            conn.close()
            if response.status == 200:
                return json.loads(body.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - report last browser startup error.
            last_error = exc
        time.sleep(0.1)
    raise DevToolsProtocolError(f"Browser DevTools endpoint unavailable: {last_error}")


def wait_for_devtools_page(port: int, timeout: float = 10.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    last_payload: Any = None
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            last_payload = wait_for_http_json(
                port,
                "/json/list",
                timeout=min(1.0, max(0.1, deadline - time.time())),
            )
        except Exception as exc:  # noqa: BLE001 - keep waiting for the browser page target.
            last_error = exc
            time.sleep(0.1)
            continue
        if isinstance(last_payload, list):
            for tab in last_payload:
                if isinstance(tab, dict) and tab.get("webSocketDebuggerUrl"):
                    return tab
        time.sleep(0.1)
    raise DevToolsProtocolError(f"No DevTools page target found: {last_payload or last_error}")


def launch_browser(browser: str, remote_port: int, user_data_dir: Path) -> subprocess.Popen[str]:
    cmd = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-dev-shm-usage",
        "--disable-extensions",
        "--no-sandbox",
        f"--remote-debugging-port={remote_port}",
        f"--user-data-dir={path_for_browser_arg(user_data_dir, browser)}",
        "about:blank",
    ]
    return subprocess.Popen(  # noqa: S603 - browser path is selected from local candidates.
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def js_wait_selector(selector: str, timeout_ms: int) -> str:
    return f"""
      (async () => {{
        const selector = {json.dumps(selector)};
        const deadline = Date.now() + {int(timeout_ms)};
        while (Date.now() < deadline) {{
          const el = document.querySelector(selector);
          if (el && !el.disabled) {{
            return {{
              ok: true,
              selector,
              title: (document.querySelector('h1') || document.querySelector('h2') || {{}}).textContent || '',
              text: (document.querySelector('#app') || document.body).innerText.slice(0, 600),
              canvasCount: document.querySelectorAll('canvas').length,
              buttonCount: document.querySelectorAll('button').length
            }};
          }}
          await new Promise((resolve) => setTimeout(resolve, 100));
        }}
        return {{
          ok: false,
          selector,
          title: (document.querySelector('h1') || document.querySelector('h2') || {{}}).textContent || '',
          text: (document.querySelector('#app') || document.body).innerText.slice(0, 600),
          canvasCount: document.querySelectorAll('canvas').length,
          buttonCount: document.querySelectorAll('button').length
        }};
      }})()
    """


def js_click(selector: str) -> str:
    return f"""
      (() => {{
        const selector = {json.dumps(selector)};
        const el = document.querySelector(selector);
        if (!el) return {{ ok: false, selector, error: 'selector not found' }};
        if (el.disabled) return {{ ok: false, selector, error: 'element disabled' }};
        el.click();
        return {{ ok: true, selector }};
      }})()
    """


def js_dom_snapshot() -> str:
    return """
      (() => {
        const root = document.querySelector('#app') || document.body;
        const canvas = document.querySelector('canvas');
        let canvasPixels = null;
        if (canvas) {
          const ctx = canvas.getContext('2d');
          const width = canvas.width || 0;
          const height = canvas.height || 0;
          const samples = [];
          if (ctx && width && height) {
            const points = [
              [0.2, 0.2],
              [0.5, 0.5],
              [0.8, 0.35],
              [0.35, 0.72],
              [0.68, 0.78]
            ];
            for (const [x, y] of points) {
              const px = Math.max(0, Math.min(width - 1, Math.floor(width * x)));
              const py = Math.max(0, Math.min(height - 1, Math.floor(height * y)));
              samples.push(Array.from(ctx.getImageData(px, py, 1, 1).data));
            }
          }
          canvasPixels = { width, height, samples };
        }
        return {
          title: (document.querySelector('h1') || document.querySelector('h2') || {}).textContent || '',
          text: root.innerText.slice(0, 800),
          canvasCount: document.querySelectorAll('canvas').length,
          buttonCount: document.querySelectorAll('button').length,
          imageCount: document.querySelectorAll('img').length,
          canvasPixels
        };
      })()
    """


def capture_screenshot(cdp: CDPClient, path: Path) -> dict[str, Any]:
    result = cdp.call(
        "Page.captureScreenshot",
        {"format": "png", "fromSurface": True, "captureBeyondViewport": False},
    )
    data = result.get("data")
    if not isinstance(data, str):
        raise DevToolsProtocolError("Page.captureScreenshot did not return image data")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(base64.b64decode(data))
    width, height = png_dimensions(path)
    return {
        "path": str(path),
        "width": width,
        "height": height,
        "file_size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def run_flow_for_viewport(
    browser: str,
    static_port: int,
    output_dir: Path,
    viewport_id: str,
    width: int,
    height: int,
    timeout: int,
) -> dict[str, Any]:
    remote_port = choose_port()
    with tempfile.TemporaryDirectory(prefix=f"ai-td-{viewport_id}-", dir="/tmp") as tmp:
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
            url = (
                f"http://127.0.0.1:{static_port}"
                "/frontend/index.html?static=1&flowVisualSmoke=1"
            )
            cdp.call("Page.navigate", {"url": url})
            wait_result = cdp.eval(js_wait_selector("main", 9000), timeout_ms=10000)
            if not as_obj(wait_result).get("ok"):
                raise DevToolsProtocolError(f"App did not boot: {wait_result}")

            screenshots: list[dict[str, Any]] = []
            failures: list[dict[str, Any]] = []
            for step in FLOW_STEPS:
                step_id = str(step["step_id"])
                if step.get("click_selector"):
                    click_result = cdp.eval(js_click(str(step["click_selector"])))
                    if not as_obj(click_result).get("ok"):
                        raise DevToolsProtocolError(
                            f"Click failed for {step_id}: {click_result}"
                        )
                wait_selector = str(step["wait_selector"])
                wait_timeout_ms = int(step.get("wait_timeout_ms") or 7000)
                wait_result = cdp.eval(
                    js_wait_selector(wait_selector, wait_timeout_ms),
                    timeout_ms=wait_timeout_ms + 1000,
                )
                if not as_obj(wait_result).get("ok"):
                    failures.append(
                        {
                            "viewport_id": viewport_id,
                            "step_id": step_id,
                            "reason": "wait_selector_timeout",
                            "wait_selector": wait_selector,
                            "snapshot": wait_result,
                        }
                    )
                    break
                post_wait_ms = int(step.get("post_wait_ms") or 250)
                if post_wait_ms:
                    time.sleep(post_wait_ms / 1000)
                screenshot_path = output_dir / f"frontend_flow_{viewport_id}_{step_id}.png"
                screenshot = capture_screenshot(cdp, screenshot_path)
                snapshot = cdp.eval(js_dom_snapshot())
                screenshots.append(
                    {
                        "viewport_id": viewport_id,
                        "step_id": step_id,
                        "label": step.get("label"),
                        "wait_selector": wait_selector,
                        "dom": snapshot,
                        **screenshot,
                    }
                )
            status = "captured" if len(screenshots) == len(FLOW_STEPS) and not failures else "failed"
            return {
                "viewport_id": viewport_id,
                "requested_width": width,
                "requested_height": height,
                "status": status,
                "screenshot_count": len(screenshots),
                "screenshots": screenshots,
                "failures": failures,
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
) -> dict[str, Any]:
    return {
        "schema_version": "frontend_flow_visual_smoke_report.v0.1",
        "task_id": "P1-D-18-browser-flow-visual-smoke",
        "status": "browser_unavailable",
        "browser_available": browser is not None,
        "browser_executable": browser,
        "browser_candidates": candidates,
        "output_dir": str(output_dir),
        "viewport_count": 0,
        "step_ids": [str(step["step_id"]) for step in FLOW_STEPS],
        "viewport_results": [],
        "screenshots": [],
        "failures": failures,
        "smoke_mode": {
            "query": "static=1&flowVisualSmoke=1",
            "purpose": "Browser-only visual flow smoke; battle is accelerated for screenshots.",
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
    viewport_results: list[dict[str, Any]],
) -> dict[str, Any]:
    screenshots = [
        screenshot
        for viewport in viewport_results
        for screenshot in viewport.get("screenshots", [])
    ]
    failures = [
        failure
        for viewport in viewport_results
        for failure in viewport.get("failures", [])
    ]
    status = "captured" if viewport_results and all(
        item.get("status") == "captured" for item in viewport_results
    ) else "failed"
    return {
        "schema_version": "frontend_flow_visual_smoke_report.v0.1",
        "task_id": "P1-D-18-browser-flow-visual-smoke",
        "status": status,
        "browser_available": True,
        "browser_executable": browser,
        "browser_candidates": candidates,
        "output_dir": str(output_dir),
        "viewport_count": len(viewport_results),
        "step_ids": [str(step["step_id"]) for step in FLOW_STEPS],
        "expected_screenshot_count": len(viewport_results) * len(FLOW_STEPS),
        "captured_screenshot_count": len(screenshots),
        "viewport_results": viewport_results,
        "screenshots": [
            {
                "viewport_id": item.get("viewport_id"),
                "step_id": item.get("step_id"),
                "label": item.get("label"),
                "path": item.get("path"),
                "width": item.get("width"),
                "height": item.get("height"),
                "file_size_bytes": item.get("file_size_bytes"),
                "sha256": item.get("sha256"),
                "title": as_obj(item.get("dom")).get("title"),
                "canvas_count": as_obj(item.get("dom")).get("canvasCount"),
                "button_count": as_obj(item.get("dom")).get("buttonCount"),
                "image_count": as_obj(item.get("dom")).get("imageCount"),
            }
            for item in screenshots
        ],
        "failures": failures,
        "smoke_mode": {
            "query": "static=1&flowVisualSmoke=1",
            "purpose": "Browser-only visual flow smoke; battle is accelerated for screenshots.",
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
    report_path = output_dir / "frontend_flow_visual_smoke_report.v0.1.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report_path


def parse_viewports(raw: list[str] | None) -> dict[str, tuple[int, int]]:
    if not raw:
        return dict(DEFAULT_VIEWPORTS)
    parsed: dict[str, tuple[int, int]] = {}
    for item in raw:
        try:
            viewport_id, size = item.split("=", 1)
            width_text, height_text = size.lower().split("x", 1)
            parsed[viewport_id] = (int(width_text), int(height_text))
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"Invalid viewport format {item!r}; expected id=WIDTHxHEIGHT"
            ) from exc
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--browser-bin", help="Path or command name for a Chromium-compatible browser.")
    parser.add_argument("--allow-missing-browser", action="store_true")
    parser.add_argument("--timeout", type=int, default=30)
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
    candidates = browser_candidates(args.browser_bin)
    browser = find_browser(args.browser_bin)
    if not browser:
        report = build_unavailable_report(
            output_dir,
            None,
            candidates,
            [{"error": "No Chromium-compatible browser executable found."}],
        )
        report_path = write_report(output_dir, report)
        print(f"BROWSER_UNAVAILABLE frontend flow visual smoke: {report_path}")
        return 0 if args.allow_missing_browser else 2

    server, static_port = start_static_server()
    try:
        viewport_results = [
            run_flow_for_viewport(
                browser,
                static_port,
                output_dir,
                viewport_id,
                width,
                height,
                args.timeout,
            )
            for viewport_id, (width, height) in parse_viewports(args.viewport).items()
        ]
    except Exception as exc:  # noqa: BLE001 - emit structured failure report.
        report = build_unavailable_report(
            output_dir,
            browser,
            candidates,
            [{"error": type(exc).__name__, "message": str(exc)}],
        )
        report["status"] = "failed"
        report_path = write_report(output_dir, report)
        print(f"FAILED frontend flow visual smoke: {report_path}")
        return 1
    finally:
        server.shutdown()
        server.server_close()

    report = build_report(output_dir, browser, candidates, viewport_results)
    report_path = write_report(output_dir, report)
    print(f"{report['status'].upper()} frontend flow visual smoke: {report_path}")
    for item in report.get("screenshots", []):
        print(f"- {item['viewport_id']} {item['step_id']}: {item['path']}")
    return 0 if report["status"] == "captured" else 1


if __name__ == "__main__":
    raise SystemExit(main())
