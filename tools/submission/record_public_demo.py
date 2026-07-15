#!/usr/bin/env python3
"""录制 Compiler 公网主流程，产出无剪辑 WebM 素材。"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright


DEFAULT_BROWSER = Path.home() / ".cache/ms-playwright/chromium-1228/chrome-linux64/chrome"


def pause(page: Page, seconds: float) -> None:
    page.wait_for_timeout(round(seconds * 1000))


def click_when_ready(page: Page, selector: str, timeout: int = 20_000) -> None:
    target = page.locator(selector)
    target.wait_for(state="visible", timeout=timeout)
    target.click()


def drag_first_tool(page: Page) -> bool:
    tool = page.locator(".toolbar-card[data-tool]").first
    try:
        tool.wait_for(state="visible", timeout=4_000)
    except Exception:
        return False
    tool_id = tool.get_attribute("data-tool") or "basic"
    target = page.evaluate(
        """(tool) => window.__AI_TD_BATTLE_SMOKE__?.deploymentPoint?.(tool) || null""",
        tool_id,
    )
    source = tool.bounding_box()
    if not source or not target:
        return False
    start_x = source["x"] + source["width"] / 2
    start_y = source["y"] + source["height"] / 2
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(float(target["client_x"]), float(target["client_y"]), steps=18)
    pause(page, 1.5)
    page.mouse.up()
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://1.15.67.144/frontend/index.html")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--browser", type=Path, default=DEFAULT_BROWSER)
    parser.add_argument("--world-id", default="")
    parser.add_argument("--short-world-clip", action="store_true")
    parser.add_argument("--map-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    video_dir = args.output.parent / ".raw-video"
    video_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=str(args.browser),
            headless=True,
            args=["--no-proxy-server", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(
            viewport={"width": 1600, "height": 900},
            record_video_dir=str(video_dir),
            record_video_size={"width": 1600, "height": 900},
        )
        page = context.new_page()
        video = page.video
        url = f"{args.url}?flowVisualSmoke=1"
        page.goto(url, wait_until="domcontentloaded", timeout=45_000)

        page.locator("[data-action='continue']").wait_for(state="visible", timeout=45_000)
        pause(page, 7)
        click_when_ready(page, "[data-action='continue']")
        page.locator("[data-action='begin-world']").wait_for(timeout=20_000)
        if args.world_id:
            world = page.locator(
                f"[data-action='select-world'][data-value='{args.world_id}']",
            )
            world.wait_for(state="visible", timeout=30_000)
            world.click()
            pause(page, 5)
        pause(page, 6 if args.short_world_clip else 15)

        click_when_ready(page, "[data-action='begin-world']")
        page.locator("[data-action='opening-next']").wait_for(timeout=20_000)
        if args.short_world_clip:
            pause(page, 5)
            click_when_ready(page, "[data-action='opening-skip']")
        else:
            for _ in range(3):
                pause(page, 5)
                click_when_ready(page, "[data-action='opening-next']")
            pause(page, 5)
            if page.locator("[data-action='opening-skip']").count():
                click_when_ready(page, "[data-action='opening-skip']")

        page.locator("[data-action='enter-node']").wait_for(timeout=20_000)
        pause(page, 8 if args.short_world_clip else 12)
        click_when_ready(page, "[data-action='map-zoom-in']")
        pause(page, 3)
        click_when_ready(page, "[data-action='map-camera-reset']")
        pause(page, 4)
        if args.map_only:
            if video is None:
                raise RuntimeError("Playwright 未创建录屏文件")
            page.close()
            video.save_as(str(args.output))
            context.close()
            browser.close()
            print({"status": "recorded", "output": str(args.output), "bytes": args.output.stat().st_size})
            return 0
        click_when_ready(page, "[data-action='enter-node']")

        confirm = page.locator("[data-action='confirm-prototype']")
        try:
            confirm.wait_for(state="visible", timeout=3_000)
        except Exception:
            click_when_ready(page, "[data-action='proposal-refresh']", timeout=30_000)
            confirm.wait_for(state="visible", timeout=45_000)
        pause(page, 10 if args.short_world_clip else 13)
        confirm.click()
        page.locator("#battleCanvas").wait_for(timeout=35_000)
        pause(page, 10 if args.short_world_clip else 8)
        if not args.short_world_clip:
            drag_first_tool(page)
            pause(page, 8)
            speed = page.locator("[data-action='cycle-speed']")
            if speed.count():
                speed.click()
                speed.click()
            pause(page, 38)

            settlement = page.locator("[data-action='return-map']")
            try:
                settlement.wait_for(timeout=45_000)
                pause(page, 15)
            except Exception:
                pause(page, 5)

        if video is None:
            raise RuntimeError("Playwright 未创建录屏文件")
        page.close()
        video.save_as(str(args.output))
        context.close()
        browser.close()

    print({"status": "recorded", "output": str(args.output), "bytes": args.output.stat().st_size})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
