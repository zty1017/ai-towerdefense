# Compiler 黑客松提交清单

截止时间：2026-07-15

## 必交材料

| 序号 | 材料 | 约束 | 当前状态 | 文件或待填内容 |
| --- | --- | --- | --- | --- |
| 01 | 作品标题 | 文本 | 已准备 | `Compiler：AI 驱动的塔防游戏内容编译器` |
| 02 | 作品描述 | 背景、玩法、亮点 | 已准备 | `submission/FORM_COPY.md` |
| 03 | 作品海报 | 16:9，单图不超过 5MB | 已生成并检查 | `submission/generated/compiler_project_poster_16x9.jpg` |
| 11 | 项目源代码 | 单个 ZIP，不超过 512MB | 已生成并验证（152MB） | `Compiler-source.zip` |
| 12 | 作品网页链接 | 公网可访问，浏览器可玩 | 已部署并通过 Chromium 验收 | `http://1.15.67.144/frontend/index.html` |
| 13 | 游戏 Demo 视频 | MP4，3-5 分钟，不超过 500MB | 已检查：3分11秒，16MB | `Compiler-game-demo.mp4` |
| 14 | 作品介绍 PPT | PDF 或 PPTX，不超过 50MB | 已生成并检查 | `submission/generated/Compiler-Project-Deck.pptx` 与 PDF |
| 17 | AI 使用说明 | 不超过 300 字 | 已准备 | `submission/FORM_COPY.md` |
| 18 | 社交媒体发布链接 | 带 `#CodeBuddy`、`#TencentCloudHackathon` | 文案已准备，链接待发布 | `submission/FORM_COPY.md` |

## 提交前硬检查

1. 用无痕窗口从公网地址完成一次完整主流程。当前已自动录制主世界与三个扩展世界，并完成战略地图检查。
2. 视频时长在 3-5 分钟，格式 MP4，文件小于 500MB。
3. 海报为 16:9 且小于 5MB。
4. PPTX/PDF 均小于 50MB，中文字体无缺失。
5. 源码 ZIP 排除 `.git`、`.venv`、缓存、数据库、`.env` 和 API key。
6. AI 使用说明不超过 300 个汉字，不夸大实时图片或地图生成范围。
7. 社媒正文包含 `#CodeBuddy` 与 `#TencentCloudHackathon`。
