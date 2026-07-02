# 任务队列

Last updated: 2026-07-02

本文是交付给 CodeBuddy / OpenCode / Codex worker / 人类队友的当前任务来源。

若本文与早期任务文档冲突，以本文为准。字段级事实源仍以 `shared/schemas/`、`tools/`、`examples/` 和对应专题文档为准。

## 1. 使用规则

优先级：

```text
P0：MVP 当前闭环必须完成
P1：时间允许时推进
P2：本阶段明确不做
```

协作规则：

- `main` 是稳定决策 / 发布基线，只在阶段性冻结窗口从 `develop` 受控同步。
- `develop` 是当前集成事实源。
- 具体实现优先在从 `develop` 派生的 `task/*` worktree 中完成。
- worker 不得直接合并到 `main` 或 `develop`。
- worker 不得修改 `.env`，不得打印 API key、secret、token。
- worker 完成后必须汇报修改文件、验证命令、结果、风险和未解决问题。
- 玩家侧页面、接口文案、演示文本不得出现 provider、prompt、schema、raw trace、API key 等技术词。
- 内部证据、校验日志和演示导出可以保留技术信息，但必须过滤 secret 和原始未审内容。

外部 agent 调用说明：

- CodeBuddy / OpenCode / Codex headless 可以在用户授权的 IDE / CLI 环境中作为 worker 使用。
- 本 Codex 受控执行通道已验证 `opencode run` 的无项目上下文调用可用。
- 本 Codex 受控执行通道不能依赖“把仓库或项目上下文直接发送给外部模型”的调用方式；这会被环境策略拦截为外部数据披露风险。
- 因此，在本通道内需要使用外部 agent 时，应优先使用不包含仓库内容的公开任务指令；需要仓库上下文的任务由用户侧 CodeBuddy/OpenCode 工作区或本地 task worktree 执行。

## 2. 当前已完成基线

当前有效基线位于 `develop`。

已落地内容：

- FastAPI + SQLite 后端。
- 匿名 session，不做真实注册登录。
- Research proposal / job API。
- Frontend mock API。
- 内容 fixture 与 MVP 世界实例。
- locked manifest / runtime package 基础合同与校验。
- AssetGraph DAG / 有界 ReAct / 节点注册 / runtime package 构建与校验。
- 真实 LLM 世界状态变化烟测与语义门。
- 媒体后处理 mock assets、processed PNG、animation seed manifest。
- 前端运行时 mock 美术包：敌人、目标物、基础防御件、NPC 头像、地图 token、程序化特效。
- MapRuntimePackage v0.1：首战节点已有路径、塔位、目标、出生点和本地视觉层引用。
- 前端已优先消费 MapRuntimePackage，旧 battle config 只作为兼容 fallback。
- 当前前端是 no-build MVP shell，不再以早期 React/Vite/Phaser 骨架任务为事实源。

当前缺口：

- 战斗和大地图视觉仍需明显游戏化，不能停留在调试图形或突兀棋盘感。
- 证据导出脚本仍未独立成 `summary.md / evidence.json / index.html`。
- 多个战斗节点还缺 MapRuntimePackage。
- 视频帧、spritesheet、atlas 尚未默认接入前端运行时。
- live campaign router、预生成调度、长期存档还未形成稳定实现。

## 3. P0 任务

### P0-A 前端战斗画面与大地图视觉打磨

任务类型：实现 / 视觉

建议分支：

```text
task/frontend-visual-polish
```

目标：

```text
让 MVP 前端第一眼更像完整塔防游戏画面，而不是调试面板或孤立几何图。
```

允许修改：

- `frontend/`
- `game_data/media/`
- `examples/map_runtime_packages/`
- `docs/FRONTEND_RUNTIME_MOCK_ART_KIT_V0_1.md`

关键要求：

- 战斗主画面占据页面视觉中心，地图应是自然地形画面上的路径 / 塔位 / 目标叠层。
- 不再使用突兀的平行四边形板块作为主地图表达。
- 支持拖拽防御件到可放置塔位，保留点击放置 fallback。
- 塔位、路径、目标、出生点必须来自 MapRuntimePackage。
- UI 可以有调试辅助开关，但默认玩家视图应沉浸式。
- 大地图需要包含主城、战斗节点、资源 / 存储节点、未知黑暗区域、剧情 / NPC 标记。

验收命令：

```bash
node --check frontend/app.js
python3 tools/asset_graph/validate_map_runtime_package.py examples/map_runtime_packages/mvp_first_battle.map_runtime_package.json
```

验收要点：

- 首屏视觉能支撑录屏演示。
- 中部战斗区域不显得像临时调试画布。
- 拖拽放置不会破坏现有 MapRuntimePackage 逻辑。

### P0-B 演示证据导出脚本

任务类型：实现 / 演示工程

建议分支：

```text
task/demo-evidence-export
```

目标：

```text
从当前 fixture、runtime package、编译日志和审查报告中导出可录屏展示的证据包。
```

允许修改：

- `tools/demo/`
- `docs/`
- `examples/`
- `backend/tests/`

产物建议：

```text
artifacts/demo_evidence/summary.md
artifacts/demo_evidence/evidence.json
artifacts/demo_evidence/index.html
```

关键要求：

- 不导出 API key、secret、raw prompt、provider 原始响应。
- 能展示 AI 编译链路存在：输入上下文、DAG 节点、校验结果、runtime package、前端可用资产。
- 作为 Studio 证据替代物，不强制做复杂前端 Studio 页面。

验收命令：

```bash
python3 tools/demo/export_evidence.py --output-dir /tmp/ai_td_demo_evidence
python3 -m json.tool /tmp/ai_td_demo_evidence/evidence.json
```

### P0-C 继续补齐 MapRuntimePackage 节点覆盖

任务类型：实现 / 内容管线

建议分支：

```text
task/map-runtime-package-more-nodes
```

目标：

```text
为 MVP 大地图上的后续战斗节点生成 MapRuntimePackage，使前端可按统一合同加载地图运行时信息。
```

允许修改：

- `examples/map_runtime_packages/`
- `tools/asset_graph/`
- `backend/`
- `backend/tests/`
- `docs/MAP_VISUAL_REFERENCE_PIPELINE_V0_1.md`

节点目标：

- `mvp_first_battle`
- `lamp_wick_store`
- `old_signal_tower`

关键要求：

- 每个可战斗节点返回非空 MapRuntimePackage。
- path routes、build slots、objectives、spawn points 均需结构化。
- visual_layers 只能引用本地发布资产或受控静态路径。
- 校验器继续递归拒绝 provider、raw_prompt、secret、unreviewed_content。

验收命令：

```bash
python3 tools/asset_graph/validate_map_runtime_package.py examples/map_runtime_packages/mvp_first_battle.map_runtime_package.json
python3 -m compileall tools/asset_graph backend
```

### P0-D 研发 / 编译接口与 CGOP 元数据对齐

任务类型：实现 / 架构对齐

建议分支：

```text
task/research-cgop-runtime-alignment
```

目标：

```text
让 research proposal / job / sample 输出更接近 AI 可编译游戏对象统一模型，并能引用 MapRuntimePackage、ContextPackage、WorldStateDeltaTransaction 等当前概念。
```

允许修改：

- `backend/`
- `shared/`
- `tools/asset_graph/`
- `examples/`
- `docs/FRONTEND_MOCK_API_V0_1.md`

关键要求：

- 玩家侧仍是世界内研发 / 试作 / 样品语言。
- 内部对象需要能表达 compiled object 类型、上下文来源、约束、校验状态和 runtime package 引用。
- 编译失败要区分世界内失败、校验失败、provider / 调度失败、实现错误。
- 技术错误不得直接污染玩家体验。

验收命令：

```bash
python3 -m compileall backend tools
```

若测试依赖已可用，再运行：

```bash
pytest backend/tests
```

### P0-E 测试依赖与本地验证环境整理

任务类型：工程治理

建议分支：

```text
task/test-env-hardening
```

目标：

```text
让当前后端测试、工具测试和前端语法检查能被新 worker 稳定复现。
```

允许修改：

- `requirements.txt`
- `pyproject.toml`
- `README.md`
- `docs/MVP_REVIEW_HANDOFF_V0_1.md`
- `backend/tests/`
- `tools/`

关键要求：

- 明确 FastAPI、pytest 等测试依赖安装方式。
- 不强制 worker 修改全局 Python 环境。
- README 中区分“无依赖可运行检查”和“完整测试检查”。

验收命令：

```bash
python3 -m compileall backend tools
node --check frontend/app.js
```

完整环境下再运行：

```bash
pytest backend/tests
```

### P0-F 前端 API / 静态 fallback 适配层整理

任务类型：实现 / 简化

建议分支：

```text
task/frontend-data-adapter
```

目标：

```text
把前端加载后端 API、静态 fixture、MapRuntimePackage fallback 的逻辑集中，减少散落兼容代码。
```

允许修改：

- `frontend/`
- `docs/FRONTEND_MOCK_API_V0_1.md`

关键要求：

- 优先后端 mock API。
- 静态文件只作为本地无后端演示 fallback。
- MapRuntimePackage 是战斗地图运行时事实源。
- 不引入构建步骤，除非另开技术栈迁移任务。

验收命令：

```bash
node --check frontend/app.js
```

## 4. P1 任务

### P1-A 视频帧 / spritesheet / atlas 默认接入

目标：

```text
固化“图片 -> 图生视频 -> 关键帧 -> 后处理 -> atlas -> runtime manifest”路线。
```

要点：

- 首尾帧一致或 end frame 控制优先。
- 加入 LoopContinuityCheck。
- 后处理产物需支持透明 PNG、anchor、frame alignment、atlas json。
- 前端优先消费 atlas，静态 PNG 作为 fallback。

### P1-B Map Visual Reference 生成管线

目标：

```text
实现逻辑地图 -> 控制图 / composition sketch -> 地图底图生成 -> 结构化路线与塔位回写的开发者管线。
```

要点：

- 图像模型只负责自然游戏地图渲染。
- 路线、塔位、目标以结构化数据为准。
- 需要支持世界书风格、地形、威胁状态和黑暗区域。

### P1-C 世界演化预生成与调度

目标：

```text
建立类似视频缓冲的后台预生成机制，让剧情、任务、地图、资产在玩家到达前被异步准备。
```

要点：

- 区分 blocking、prefetch、background、lazy。
- 引入预算、失败重试、降级 fixture。
- 世界演化必须服务玩法和进度，不自由失控生长。

### P1-D 更多可编译对象覆盖

目标：

```text
继续扩展 NPC、任务、随机事件、剧情节点、材料、怪物、地图、设施等可编译对象。
```

要点：

- 所有对象先进入统一 CGOP / package manifest 模型。
- 不允许直接自由写 runtime。
- 每类对象定义最小可玩字段和审查门禁。

### P1-E 手动 CodeBuddy / OpenCode 任务交付包

目标：

```text
生成可粘贴给用户侧 CodeBuddy / OpenCode 主代理的任务包模板。
```

要点：

- 任务包包含允许修改范围、验收命令、禁止事项、汇报格式。
- 可被 IDE 侧代理读取完整仓库后执行。
- 不要求本 Codex 受控通道直接外发仓库上下文。

## 5. P2 暂不做

本阶段明确不做：

- 复杂注册登录、多用户权限、联机同步。
- 真 3D 战斗画面。
- 玩家运行时任意代码执行。
- 游戏内可视化 DAG 编辑器。
- 游玩中实时生成长视频作为关键路径。
- 完整长期存档和跨局世界继承。
- 复杂后台管理系统。

## 6. 推荐执行顺序

建议当前批次按以下顺序推进：

1. `P0-A` 前端战斗画面与大地图视觉打磨。
2. `P0-B` 演示证据导出脚本。
3. `P0-C` 补齐更多节点 MapRuntimePackage。
4. `P0-D` 研发 / 编译接口与 CGOP 元数据对齐。
5. `P0-E` 测试依赖与本地验证环境整理。
6. `P0-F` 前端 API / 静态 fallback 适配层整理。

若需要并行，优先组合：

- `P0-A` 与 `P0-B` 可并行。
- `P0-C` 与 `P0-D` 可并行，但合并时先合 `P0-C`，再让 `P0-D` 引用新的地图包事实。
- `P0-E` 可独立并行，但不得大规模重构业务代码。

