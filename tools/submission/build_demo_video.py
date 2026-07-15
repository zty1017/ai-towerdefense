#!/usr/bin/env python3
"""将实机录屏、跨世界片段与项目视觉合成为 3-5 分钟演示视频。"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FFMPEG = (
    ROOT
    / ".venv/lib/python3.12/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2"
)
FALLBACK_FFMPEG = (
    Path.home()
    / "projects/ai-compiled-towerdefense/.venv/lib/python3.12/site-packages/"
    "imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2"
)
def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def video_filter(*, speed: float = 1.0, fade_out: float, title: str = "", subtitle: str = "") -> str:
    filters = [
        f"setpts=PTS/{speed}",
        "scale=1600:900:force_original_aspect_ratio=decrease",
        "pad=1600:900:(ow-iw)/2:(oh-ih)/2:color=black",
        "fps=30",
        "fade=t=in:st=0:d=0.45",
        f"fade=t=out:st={fade_out}:d=0.55",
    ]
    return ",".join(filters)


def transcode_clip(ffmpeg: Path, source: Path, output: Path, *, start: float, duration: float, speed: float, title: str = "", subtitle: str = "") -> None:
    final_duration = duration / speed
    run(
        [
            str(ffmpeg), "-y", "-ss", str(start), "-t", str(duration), "-i", str(source),
            "-an", "-vf", video_filter(speed=speed, fade_out=max(0.1, final_duration - 0.55), title=title, subtitle=subtitle),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output),
        ],
    )


def image_clip(ffmpeg: Path, source: Path, output: Path, duration: float) -> None:
    run(
        [
            str(ffmpeg), "-y", "-loop", "1", "-t", str(duration), "-i", str(source),
            "-an", "-vf", (
                "scale=1600:900:force_original_aspect_ratio=decrease,"
                "pad=1600:900:(ow-iw)/2:(oh-ih)/2:color=black,fps=30,"
                f"fade=t=in:st=0:d=0.5,fade=t=out:st={duration - .6}:d=0.6"
            ),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", str(output),
        ],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--main-flow", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ffmpeg", type=Path)
    args = parser.parse_args()
    ffmpeg = args.ffmpeg or (DEFAULT_FFMPEG if DEFAULT_FFMPEG.exists() else FALLBACK_FFMPEG)
    work = args.release_dir / ".video-build"
    work.mkdir(parents=True, exist_ok=True)
    poster = args.release_dir / "compiler_project_poster_16x9.jpg"
    architecture = args.release_dir / "compiler_architecture_slide.png"
    multiworld = args.release_dir / "compiler_multiworld_slide.png"
    clips = [work / f"clip-{index:02d}.mp4" for index in range(8)]

    image_clip(ffmpeg, poster, clips[0], 8)
    transcode_clip(ffmpeg, args.main_flow, clips[1], start=0, duration=82, speed=1.0, title="长夜灯火 · 完整玩法闭环", subtitle="构想 → 研发 → 激活 → 首战")
    worlds = [
        ("Compiler-xianxia.webm", 40, 11, "仙侠 · 云海断峰关", "灵脉为路，符阵为城"),
        ("Compiler-western.webm", 40, 13, "西幻 · 石风边境领", "荒原沼泽中的最后堡垒"),
        ("Compiler-scifi.webm", 39, 14, "科幻 · 星锚轨道站", "轨道设施上的模块化防线"),
    ]
    for index, (name, start, duration, title, subtitle) in enumerate(worlds, start=2):
        transcode_clip(
            ffmpeg,
            args.release_dir / name,
            clips[index],
            start=start,
            duration=duration,
            speed=1.0,
            title=title,
            subtitle=subtitle,
        )
    image_clip(ffmpeg, multiworld, clips[5], 25)
    image_clip(ffmpeg, architecture, clips[6], 28)
    image_clip(ffmpeg, poster, clips[7], 10)

    concat_list = work / "clips.txt"
    concat_list.write_text("".join(f"file '{clip}'\n" for clip in clips), encoding="utf-8")
    silent = work / "compiler-demo-silent.mp4"
    run([str(ffmpeg), "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(silent)])

    asian = ROOT / "frontend/assets/audio/music/asianoriental2.ogg"
    orien = ROOT / "frontend/assets/audio/music/orien.ogg"
    run(
        [
            str(ffmpeg), "-y", "-i", str(silent), "-i", str(asian), "-i", str(orien),
            "-filter_complex",
            "[1:a]atrim=0:90,asetpts=PTS-STARTPTS,volume=.17[a1];"
            "[2:a]atrim=0:130,asetpts=PTS-STARTPTS,volume=.18[a2];"
            "[a1][a2]acrossfade=d=3:c1=tri:c2=tri[a]",
            "-map", "0:v:0", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
            "-shortest", "-movflags", "+faststart", str(args.output),
        ],
    )
    print({"output": str(args.output), "bytes": args.output.stat().st_size})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
