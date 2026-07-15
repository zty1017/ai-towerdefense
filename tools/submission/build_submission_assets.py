#!/usr/bin/env python3
"""Build the final poster and project deck from real product screenshots."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt


ROOT = Path(__file__).resolve().parents[2]
SCREENSHOT_ROOT = ROOT / "submission/assets/screenshots"
DEFAULT_OUTPUT = ROOT / "submission/generated"
FONT_PATH = Path.home() / ".local/share/fonts/NotoSansCJKsc-Regular.otf"

BG = RGBColor(8, 13, 12)
PANEL = RGBColor(18, 25, 20)
INK = RGBColor(243, 239, 222)
MUTED = RGBColor(177, 183, 169)
GOLD = RGBColor(221, 164, 64)
TEAL = RGBColor(68, 177, 163)
RED = RGBColor(204, 95, 79)


def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_PATH), size)


def cover_crop(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    target_w, target_h = size
    ratio = max(target_w / image.width, target_h / image.height)
    resized = image.resize((round(image.width * ratio), round(image.height * ratio)))
    left = (resized.width - target_w) // 2
    top = (resized.height - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def draw_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, size: int, fill: str, spacing: int = 8) -> None:
    draw.multiline_text(xy, text, font=font(size), fill=fill, spacing=spacing)


def build_poster(output: Path) -> Path:
    canvas = cover_crop(Image.open(SCREENSHOT_ROOT / "main_battle.png").convert("RGB"), (1920, 1080))
    canvas = ImageEnhance.Contrast(canvas).enhance(1.08)
    canvas = ImageEnhance.Color(canvas).enhance(0.88)
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    pixels = overlay.load()
    for x in range(1920):
        alpha = int(220 * max(0.0, 1.0 - x / 1320)) + 28
        for y in range(1080):
            pixels[x, y] = (4, 8, 7, min(alpha, 235))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((108, 94, 318, 142), radius=10, fill=(24, 42, 34, 235), outline=(68, 177, 163, 220), width=2)
    draw_text(draw, (132, 102), "AI 原生塔防", 27, "#a9e8d8")
    draw_text(draw, (102, 184), "Compiler", 128, "#fff8df")
    draw_text(draw, (108, 350), "把玩家想法\n编译成真正可玩的世界", 54, "#f4e9c8", 14)
    draw_text(draw, (112, 514), "自然语言构想  →  结构化候选  →  模拟与晋升  →  战斗执行", 26, "#ced8cb")

    chips = [("防御塔", GOLD), ("陷阱", TEAL), ("支援道具", RED), ("多世界生长", RGBColor(140, 125, 216))]
    x = 112
    for label, color in chips:
        width = 54 + len(label) * 31
        draw.rounded_rectangle((x, 604, x + width, 658), radius=10, fill=(10, 16, 14, 220), outline=tuple(color), width=2)
        draw_text(draw, (x + 24, 613), label, 25, "#f6f1df")
        x += width + 18

    draw.rounded_rectangle((112, 790, 1010, 968), radius=12, fill=(8, 13, 12, 222), outline=(196, 152, 70, 150), width=2)
    draw_text(draw, (146, 824), "一个完整主线 · 三个真实编译世界 · 三类运行时对象", 28, "#e7c478")
    draw_text(draw, (146, 875), "Schema 校验  /  确定性模拟  /  Promotion Gate  /  Session 隔离", 24, "#c5cec2")
    draw_text(draw, (146, 918), "玩家负责想象，Compiler 负责让想象在规则内运行。", 25, "#fff8df")
    draw_text(draw, (1630, 1016), "TEAM COMPILER", 23, "#dcb66b")
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output, quality=91, optimize=True, progressive=True)
    return output


def set_slide_bg(slide, color: RGBColor = BG) -> None:
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def add_text(slide, text: str, x: float, y: float, w: float, h: float, size: int, color: RGBColor = INK, bold: bool = False, align=PP_ALIGN.LEFT):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.clear()
    frame.margin_left = 0
    frame.margin_right = 0
    frame.margin_top = 0
    frame.margin_bottom = 0
    frame.vertical_anchor = MSO_ANCHOR.TOP
    paragraph = frame.paragraphs[0]
    paragraph.text = text
    paragraph.alignment = align
    run = paragraph.runs[0]
    run.font.name = "Noto Sans CJK SC"
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    return box


def add_title(slide, eyebrow: str, title: str, subtitle: str = "") -> None:
    add_text(slide, eyebrow, 0.7, 0.42, 5.5, 0.3, 11, GOLD, True)
    add_text(slide, title, 0.7, 0.76, 11.9, 0.72, 30, INK, True)
    if subtitle:
        add_text(slide, subtitle, 0.72, 1.48, 11.6, 0.48, 14, MUTED)


def add_picture_cover(slide, path: Path, x: float, y: float, w: float, h: float) -> None:
    with Image.open(path) as image:
        image_ratio = image.width / image.height
    box_ratio = w / h
    picture = slide.shapes.add_picture(str(path), Inches(x), Inches(y), Inches(w), Inches(h))
    if image_ratio > box_ratio:
        visible = box_ratio / image_ratio
        crop = (1 - visible) / 2
        picture.crop_left = crop
        picture.crop_right = crop
    else:
        visible = image_ratio / box_ratio
        crop = (1 - visible) / 2
        picture.crop_top = crop
        picture.crop_bottom = crop


def add_card(slide, x: float, y: float, w: float, h: float, title: str, body: str, accent: RGBColor = GOLD) -> None:
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid(); shape.fill.fore_color.rgb = PANEL
    shape.line.color.rgb = accent; shape.line.transparency = 38
    add_text(slide, title, x + 0.25, y + 0.22, w - 0.5, 0.38, 16, INK, True)
    add_text(slide, body, x + 0.25, y + 0.72, w - 0.5, h - 0.88, 11, MUTED)


def add_footer(slide, index: int) -> None:
    add_text(slide, "Compiler · Tencent Cloud Hackathon", 0.72, 7.18, 5.5, 0.18, 8, MUTED)
    add_text(slide, f"{index:02d}", 12.1, 7.16, 0.5, 0.2, 8, GOLD, True, PP_ALIGN.RIGHT)


def build_deck(output: Path, poster: Path) -> Path:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]

    slide = prs.slides.add_slide(blank); set_slide_bg(slide)
    add_picture_cover(slide, poster, 0, 0, 13.333, 7.5)

    slide = prs.slides.add_slide(blank); set_slide_bg(slide); add_title(slide, "01 · 项目命题", "自由想象，需要一个可执行的桥梁", "我们把 AI 辅助编程的“自然语言 → 结构化产物 → 可运行结果”带入塔防游戏。")
    add_card(slide, 0.7, 2.15, 3.8, 3.9, "玩家想要什么", "像沙盒一样自由提出构想；\n每次游玩产生独特内容；\nAI 深入世界、剧情与玩法，而不是停留在聊天层。", TEAL)
    add_card(slide, 4.75, 2.15, 3.8, 3.9, "塔防需要什么", "行为可预测；\n数值可平衡；\n部署、射程、伤害和结算必须真实执行；\n失败不能破坏整局体验。", GOLD)
    add_card(slide, 8.8, 2.15, 3.8, 3.9, "Compiler 的答案", "玩家输入可以自由，底层执行必须受控。\nLLM 负责理解与提案，编译管线负责校验、模拟、晋升、激活和回滚。", RED)
    add_footer(slide, 2)

    slide = prs.slides.add_slide(blank); set_slide_bg(slide); add_title(slide, "02 · 玩家体验", "从世界书到战场中的新能力", "玩家只看见符合世界观的工坊、研发与样品交付，技术细节留在证据层。")
    add_picture_cover(slide, SCREENSHOT_ROOT / "main_map.png", 0.7, 2.0, 4.05, 4.55)
    add_picture_cover(slide, SCREENSHOT_ROOT / "main_workshop.png", 4.95, 2.0, 3.45, 4.55)
    add_picture_cover(slide, SCREENSHOT_ROOT / "main_battle.png", 8.6, 2.0, 4.05, 4.55)
    add_text(slide, "战略地图", 0.9, 6.62, 2.4, 0.3, 12, GOLD, True)
    add_text(slide, "自然语言构想", 5.15, 6.62, 2.4, 0.3, 12, TEAL, True)
    add_text(slide, "样品实战", 8.8, 6.62, 2.4, 0.3, 12, RED, True)
    add_footer(slide, 3)

    slide = prs.slides.add_slide(blank); set_slide_bg(slide); add_title(slide, "03 · AI 编译器", "DAG 负责执行，受限 React 负责修复", "任何模型输出都不能直接写入世界状态，也不能向前端注入任意代码。")
    steps = [("Context", "世界书 / 节点 / 材料 / 敌情"), ("Candidate", "LLM 结构化候选"), ("Validate", "Schema / 语义 / ABI"), ("Simulate", "确定性战斗模拟"), ("Promote", "评分与晋升报告"), ("Activate", "Session 激活回执")]
    for i, (name, body) in enumerate(steps):
        x = 0.65 + i * 2.08
        add_card(slide, x, 2.35, 1.78, 2.2, name, body, [TEAL, GOLD, RED][i % 3])
        if i < len(steps) - 1:
            add_text(slide, "→", x + 1.82, 3.13, 0.28, 0.4, 18, MUTED, True, PP_ALIGN.CENTER)
    add_text(slide, "失败只触发局部修复与有限重试；超时或媒体失败时使用审核兜底，不中断玩法。", 1.1, 5.35, 11.1, 0.65, 16, INK, True, PP_ALIGN.CENTER)
    add_footer(slide, 4)

    slide = prs.slides.add_slide(blank); set_slide_bg(slide); add_title(slide, "04 · 真实运行闭环", "三类对象，三次 Provider 调用，三次运行时变更", "2026-07-15 最终烟测：43.32 秒完成候选生成、校验、模拟、晋升、激活与行为验证。")
    add_card(slide, 0.75, 2.15, 3.85, 3.65, "光幕跳跃塔 · 17.94s", "防御塔\n伤害 + 最多三个目标连锁\n模型生成名称、费用、射程与目标数\n战斗行为由 battle_behavior_abi.v0.1 执行", TEAL)
    add_card(slide, 4.75, 2.15, 3.85, 3.65, "折光绊索 · 12.87s", "触发陷阱\n一次范围伤害 + 持续减速场\n模拟验证触发窗口与作用半径\n部署后按生命周期自动失效", GOLD)
    add_card(slide, 8.75, 2.15, 3.85, 3.65, "折光迟滞脉冲 · 11.58s", "支援道具\n自由落点范围伤害 + 迟滞\n冷却、费用和范围进入运行时投影\n媒体失败不影响行为晋升", RED)
    add_text(slide, "3 / 3 Provider calls · 3 PromotionReports · 3 ActivationReceipts · 3 gameplay mutations", 1.2, 6.25, 10.9, 0.4, 15, GOLD, True, PP_ALIGN.CENTER)
    add_footer(slide, 5)

    slide = prs.slides.add_slide(blank); set_slide_bg(slide); add_title(slide, "05 · 安全与可治理性", "让 AI 创造，但不让 AI 越权", "开发者拥有最高权限；玩家运行时只能消费白名单能力和已激活资源。")
    items = [("结构安全", "Schema、稳定 ID、禁止敏感字段与任意代码"), ("玩法安全", "效果注册表、数值 clamp、确定性模拟与预算"), ("状态安全", "匿名 session 隔离、事务化 world delta、回执与 rollback"), ("媒体安全", "本地哈希、审查门、临时 URL 不进入运行包"), ("体验安全", "Provider / rate limit 不暴露给玩家，失败走世界内降级"), ("证据安全", "只保存脱敏候选、摘要、哈希与必要 provenance")]
    for i, (title, body) in enumerate(items):
        add_card(slide, 0.75 + (i % 3) * 4.08, 2.05 + (i // 3) * 2.2, 3.75, 1.75, title, body, [TEAL, GOLD, RED][i % 3])
    add_footer(slide, 6)

    slide = prs.slides.add_slide(blank); set_slide_bg(slide); add_title(slide, "06 · 地图编译", "逻辑事实与视觉表现分离", "路线、塔位、出生点和目标来自 MapRuntimePackage；视觉层不能反向决定玩法。")
    add_card(slide, 0.75, 2.05, 3.65, 4.35, "LogicMapIR", "冻结拓扑\n路径样条与分叉\n部署槽位与合法区域\n目标、出生点、危险区\n所有坐标可测试", TEAL)
    add_card(slide, 4.85, 2.05, 3.65, 4.35, "VisualMaterialPack", "低语义地表材质\n道路与边缘材质\n塔位、目标与装饰组件\nAI 候选 + 多模态审查\n不从整图反推逻辑", GOLD)
    add_card(slide, 8.95, 2.05, 3.65, 4.35, "MapVisualRuntimePackage", "确定性合成与对齐\n世界观色调与接触阴影\n运行时高亮独立叠加\n自动审查 + 人工终审\n失败保留可玩 fallback", RED)
    add_footer(slide, 7)

    slide = prs.slides.add_slide(blank); set_slide_bg(slide); add_title(slide, "07 · 同一套 Compiler，多个世界", "《长夜灯火》只是 MVP 模板", "仙侠、西幻、科幻拥有独立世界书、身份、开场、战略地图、首关与研发上下文。")
    world_maps = [
        ("xianxia_map.png", "云海断峰关 · 仙侠", "灵脉为路，符阵为城", TEAL),
        ("western_map.png", "石风边境领 · 西幻", "沼泽荒原上的最后堡垒", GOLD),
        ("scifi_map.png", "星锚轨道站 · 科幻", "轨道设施的模块化防线", RED),
    ]
    for index, (image, title, subtitle, accent) in enumerate(world_maps):
        x = 0.7 + index * 4.18
        add_picture_cover(slide, SCREENSHOT_ROOT / image, x, 2.0, 3.78, 3.95)
        add_text(slide, title, x + 0.12, 6.08, 3.54, 0.35, 14, accent, True, PP_ALIGN.CENTER)
        add_text(slide, subtitle, x + 0.12, 6.48, 3.54, 0.3, 10, MUTED, False, PP_ALIGN.CENTER)
    add_footer(slide, 8)

    slide = prs.slides.add_slide(blank); set_slide_bg(slide); add_title(slide, "08 · 工程实现与 AI 协作", "浏览器可玩、可测试、可审计", "比赛开发过程同样使用多 Agent，但最终代码、运行包和发布证据由统一质量门验收。")
    add_card(slide, 0.75, 2.05, 3.7, 3.9, "运行架构", "FastAPI + SQLite\n原生 ES Modules + Canvas 2D\n匿名 session，无复杂登录\n后台 research worker 可恢复\n单链接浏览器体验", TEAL)
    add_card(slide, 4.82, 2.05, 3.7, 3.9, "AI 工具", "CodeBuddy：实现、重构、代码审查\nCodex/OpenCode：架构、编排、集成验收\nDeepSeek/GLM：结构化内容候选\nAgnes：视觉候选\n多模态模型：视觉审查", GOLD)
    add_card(slide, 8.89, 2.05, 3.7, 3.9, "自动验收", "55 项前端运行时模块测试\n105 项相关后端测试\n桌面/移动 Chromium 流程\n拖拽部署与战斗行为 smoke\nScheduler 28 步证据链", RED)
    add_footer(slide, 9)

    slide = prs.slides.add_slide(blank); set_slide_bg(slide); add_title(slide, "09 · 当前成果与下一步", "从教学关 Demo 到 AI 编译游戏内容系统", "黑客松版本优先证明“自由构想可以安全成为玩法”，而不是堆叠固定关卡数量。")
    add_card(slide, 0.75, 2.05, 5.7, 4.45, "已经真实闭环", "• 塔、陷阱、支援道具：文本候选 → 战斗执行\n• 真实 Provider 三对象演示与激活回执\n• 世界实例编译与三种题材首战\n• 地图逻辑/视觉分层编译工具链\n• 完整主线、音频、部署范围与战后状态", TEAL)
    add_card(slide, 6.85, 2.05, 5.7, 4.45, "比赛后优先方向", "• 把剧情、任务、随机事件接入同一事务化编译协议\n• 扩展召唤、护盾、修复与资源联动 ABI\n• 提升视觉材质审查和自动发布通过率\n• 后台预生成、缓存与跨节点调度\n• 让世界演化始终服务玩法和进度", GOLD)
    add_footer(slide, 10)

    slide = prs.slides.add_slide(blank); set_slide_bg(slide)
    add_text(slide, "Compiler", 0.8, 1.25, 6.5, 1.0, 46, INK, True)
    add_text(slide, "玩家负责想象，\n我们让想象在规则内运行。", 0.82, 2.45, 7.2, 1.7, 30, GOLD, True)
    add_text(slide, "AI-native tower defense · Runtime asset compilation · Playable world growth", 0.85, 4.7, 8.6, 0.5, 14, MUTED)
    add_picture_cover(slide, SCREENSHOT_ROOT / "main_battle.png", 8.55, 0.75, 4.15, 5.95)
    add_text(slide, "TEAM COMPILER", 0.85, 6.35, 3.0, 0.35, 13, TEAL, True)
    add_footer(slide, 11)

    output.parent.mkdir(parents=True, exist_ok=True)
    prs.save(output)
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    poster = build_poster(args.output_dir / "compiler_project_poster_16x9.jpg")
    deck = build_deck(args.output_dir / "Compiler-Project-Deck.pptx", poster)
    print(poster)
    print(deck)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
