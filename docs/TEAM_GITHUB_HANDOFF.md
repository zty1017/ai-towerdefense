# 队友 GitHub 协作入口

本文档面向比赛最后阶段的并行探索。当前项目时间很短，目标是让队友快速验证独立方向，由主控统一决定是否采纳，不在主线上直接试错。

## 分支事实源

- `main`：稳定展示与阶段冻结分支。
- `develop`：当前实现与集成事实源，所有探索应从这里开始。
- `task/*`：边界明确、预期可合入的实现任务。
- `experiment/*`：视觉、玩法、模型或管线探索，不承诺合入。

队友不得直接向 `main` 或 `develop` 提交。探索结果通过 Draft PR 指向 `develop`，由主控审查、挑选和合并。

## 获取与启动

```bash
git clone git@github.com:zty1017/ai-towerdefense.git
cd ai-towerdefense
git switch develop

python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
.venv/bin/uvicorn app.main:app --app-dir backend --reload --port 8001
```

浏览器访问：

```text
http://127.0.0.1:8001/frontend/index.html
```

没有 provider key 时仍可使用 reviewed fallback 体验主流程。真实 `.env` 只保存在本机，不提交、不粘贴到 Issue 或 PR。

## 开始探索

```bash
git switch develop
git pull --ff-only origin develop
git switch -c experiment/<主题>-<姓名或代号>
```

一个分支只做一个主题，例如：

```text
experiment/workshop-interaction-alice
experiment/map-visual-style-bob
experiment/random-event-flow-charlie
```

提交前至少运行：

```bash
.venv/bin/python tools/dev/run_fast_quality_gate.py
.venv/bin/python -m pytest backend/tests
git diff --check
```

涉及前端交互或视觉时，还需附桌面和移动端截图；涉及 AI 编译时，还需说明真实 provider 调用次数、fallback 行为、产物路径和未通过的 gate。

## PR 交付内容

Draft PR 必须包含：

1. 探索目标与结论。
2. 修改文件和边界。
3. 验收命令与结果。
4. 截图、录屏或结构化报告。
5. 新依赖、provider 调用与费用情况。
6. 已知问题以及建议采纳的最小部分。

不要提交原始 provider 响应、`.env`、密钥、大批未筛选候选图、视频中间帧、临时数据库或 `/tmp` 产物。需要交付大文件时先在 PR 中说明，由主控决定存储方式。

## 合并边界

- API URL、共享 schema、数据库模型、Runtime Activation 和 Generation Scheduler 核心协议属于冻结区，探索分支不得自行修改。
- AI 编译产物只能通过现有校验、语义门、媒体门和激活门进入玩家运行时。
- 视觉探索可以提交 reviewed 小样与复现脚本，但不能直接替换默认运行资产。
- 主控可以只采纳 PR 中的部分提交或思路；探索分支不自行合并。
