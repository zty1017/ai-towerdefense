#!/usr/bin/env python3
"""Capture browser screenshots for the P0-M battle visual smoke test.

The repository must not fake screenshot evidence. If no browser executable is
available, this tool writes a structured unavailable report and exits with a
non-zero status unless --allow-missing-browser is set.
"""

from __future__ import annotations

import argparse
import contextlib
import http.server
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from report_io import write_json


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


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A003 - inherited name
        return


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
    if not override:
        for pattern in PLAYWRIGHT_BROWSER_GLOBS:
            for path in sorted(Path("/").glob(pattern.lstrip("/"))):
                if path.is_file():
                    candidates.append({"name": str(path), "path": str(path)})
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
    for candidate in browser_candidates(override):
        path = candidate["path"]
        if path:
            return path
    return None


def screenshot_with_chromium(
    browser: str,
    url: str,
    output_path: Path,
    width: int,
    height: int,
    timeout: int,
) -> dict[str, Any]:
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
        f"--window-size={width},{height}",
        "--virtual-time-budget=7000",
        f"--screenshot={output_path}",
        url,
    ]
    started = time.time()
    result = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    elapsed_ms = round((time.time() - started) * 1000)
    stderr_tail = result.stderr[-1200:] if result.stderr else ""
    stdout_tail = result.stdout[-1200:] if result.stdout else ""
    if result.returncode != 0:
        return {
            "status": "failed",
            "returncode": result.returncode,
            "elapsed_ms": elapsed_ms,
            "stdout_tail": stdout_tail,
            "stderr_tail": stderr_tail,
        }
    if not output_path.exists():
        return {
            "status": "failed",
            "returncode": result.returncode,
            "elapsed_ms": elapsed_ms,
            "stdout_tail": stdout_tail,
            "stderr_tail": stderr_tail,
            "error": "screenshot file was not created",
        }
    actual_width, actual_height = png_dimensions(output_path)
    return {
        "status": "captured",
        "returncode": result.returncode,
        "elapsed_ms": elapsed_ms,
        "width": actual_width,
        "height": actual_height,
        "file_size_bytes": output_path.stat().st_size,
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
    }


def build_report(
    status: str,
    output_dir: Path,
    browser: str | None,
    candidates: list[dict[str, str | None]],
    screenshots: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    url_path: str,
) -> dict[str, Any]:
    return {
        "schema_version": "battle_visual_smoke_report.v0.1",
        "task_id": "P0-M-browser-visual-smoke",
        "status": status,
        "browser_available": browser is not None,
        "browser_executable": browser,
        "browser_candidates": candidates,
        "url_path": url_path,
        "output_dir": str(output_dir),
        "screenshots": screenshots,
        "failures": failures,
        "rerun_commands": [
            "python3 tools/frontend/capture_battle_visual_smoke.py --output-dir /tmp/p0m_browser_visual_smoke",
            "python3 tools/frontend/capture_battle_visual_smoke.py --allow-missing-browser --output-dir /tmp/p0m_browser_visual_smoke",
        ],
        "notes": [
            "The smoke URL forces static data and deep-links to the battle screen.",
            "The battle rendering code path is the same MapRuntimePackage-driven player battle canvas.",
            "Screenshots are only valid when produced by a real browser executable.",
        ],
    }


def write_report(output_dir: Path, report: dict[str, Any]) -> Path:
    report_path = output_dir / "battle_visual_smoke_report.v0.1.json"
    write_json(report_path, report, sort_keys=False)
    return report_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--browser-bin", help="Path or command name for a Chromium-compatible browser.")
    parser.add_argument("--allow-missing-browser", action="store_true")
    parser.add_argument("--timeout", type=int, default=30)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    url_path = "/frontend/index.html?static=1&battleVisualSmoke=1"
    candidates = browser_candidates(args.browser_bin)
    browser = find_browser(args.browser_bin)
    if not browser:
        report = build_report(
            "browser_unavailable",
            output_dir,
            None,
            candidates,
            [],
            [{"error": "No Chromium-compatible browser executable found."}],
            url_path,
        )
        report_path = write_report(output_dir, report)
        print(f"BROWSER_UNAVAILABLE battle visual smoke: {report_path}")
        return 0 if args.allow_missing_browser else 2

    server, port = start_static_server()
    screenshots: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    try:
        url = f"http://127.0.0.1:{port}{url_path}"
        for viewport_id, (width, height) in DEFAULT_VIEWPORTS.items():
            output_path = output_dir / f"battle_visual_smoke_{viewport_id}.png"
            result = screenshot_with_chromium(
                browser,
                url,
                output_path,
                width,
                height,
                args.timeout,
            )
            record = {
                "viewport_id": viewport_id,
                "requested_width": width,
                "requested_height": height,
                "path": str(output_path),
                **result,
            }
            if result["status"] == "captured":
                screenshots.append(record)
            else:
                failures.append(record)
    finally:
        server.shutdown()
        server.server_close()

    status = "captured" if screenshots and not failures else "failed"
    report = build_report(status, output_dir, browser, candidates, screenshots, failures, url_path)
    report_path = write_report(output_dir, report)
    print(f"{status.upper()} battle visual smoke: {report_path}")
    for screenshot in screenshots:
        print(f"- {screenshot['viewport_id']}: {screenshot['path']}")
    return 0 if status == "captured" else 1


if __name__ == "__main__":
    raise SystemExit(main())
