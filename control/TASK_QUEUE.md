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

- 地图已经有 `MapRuntimePackage`、首战 `MapCompilePackage v0.2` 和玩家侧 `battle_runtime_background`，但后续战斗节点还缺对应的地图编译包覆盖。
- 战斗和大地图视觉仍需继续游戏化，不能停留在控制图、参考图、突兀棋盘或临时调试画布；默认玩家视图已加防线，但还需要浏览器截图或人工视觉验收。
- 视频帧、spritesheet、atlas 尚未默认接入前端运行时。
- live campaign router、预生成调度、长期存档还未形成稳定实现。

## 3. 已完成的 P0 基线

以下任务已经合入 `develop`，后续 worker 不应重复实现；如需修改，应另开精确修补任务。

### P0-A 前端战斗画面与大地图视觉初版

状态：已完成。

已落地：

- 战斗主画面默认使用 `battle_runtime_background` 作为玩家可见发布底图。
- `battle_control_sketch` 与 `battle_reference_board` 被降级为控制 / 参考层，不应进入默认玩家体验。
- 前端根据 `MapRuntimePackage` 叠加路径、塔位、目标、出生点和拖拽部署预览。

### P0-B 演示证据导出脚本

状态：已完成。

已落地：

- `tools/demo/export_evidence.py`
- 可导出 `summary.md`、`evidence.json`、`index.html`。
- 覆盖 frontend mock pack、runtime package、全部 map runtime package、media manifest、审查包和验证命令。

### P0-C 继续补齐 MapRuntimePackage 节点覆盖

状态：已完成。

已落地：

- `mvp_first_battle`
- `lamp_wick_store`
- `old_signal_tower`

### P0-D 研发 / 编译接口与 CGOP 元数据对齐

状态：已完成。

已落地：

- Research proposal / job 返回内部 `compiler_metadata`。
- 玩家侧仍使用世界内研发 / 试作 / 样品语言。
- 内部证据可表达 compiled object、context package、validation、runtime refs 和失败分类。

### P0-E 测试依赖与本地验证环境整理

状态：已完成。

已落地：

- `tools/dev/check_test_env.py`
- README 与 handoff 文档区分无依赖检查和完整测试检查。

### P0-F 前端 API / 静态 fallback 适配层整理

状态：已完成。

已落地：

- 前端加载逻辑集中到数据适配层。
- API 优先，静态 fixture 作为本地 fallback。
- `MapRuntimePackage` 是战斗地图运行时事实源。

### P0-G MapCompilePackage v0.2

状态：已完成。

已落地：

- `shared/schemas/map_compile_package.v0.2.schema.json`
- `tools/asset_graph/map_compile_package.py`
- `tools/asset_graph/build_map_compile_package.py`
- `tools/asset_graph/validate_map_compile_package.py`
- `examples/map_compile_packages/mvp_first_battle.map_compile_package.json`
- 地图编译包明确区分逻辑层、控制层、玩家可见渲染层、坐标回配、质量门和最终 `MapRuntimePackage` 导出引用。

### P0-H 前端地图表现质量防线

状态：已完成。

已落地：

- 前端默认玩家视图只优先使用 `painted_visual_layer` / `battle_runtime_background`。
- `battle_control_sketch` 与 `battle_reference_board` 只允许在 debug / evidence 模式作为辅助素材。
- 发布底图缺失时使用程序化大画面背景承托结构化叠层，不再自动回退到控制图或参考图。
- 拖拽部署保留，点击放置保留为 fallback。

### P0-J MapCompilePackage 证据导出接入

状态：已完成。

已落地：

- `tools/demo/export_evidence.py` 会收集 `examples/map_compile_packages/*.map_compile_package.json`。
- 演示证据包会展示地图编译包数量、发布图状态、对齐状态、质量门和玩法真相保留状态。
- 导出校验命令纳入 `tools/asset_graph/validate_map_compile_package.py`。

## 4. 当前 P0 任务

### P0-I main 文档受控同步准备

任务类型：治理 / 同步计划

建议分支：

```text
task/main-sync-plan
```

目标：

```text
生成一份从 develop 同步到 main 前的中文清单，明确哪些文档/实现应同步，哪些用户草稿不能覆盖。
```

允许修改：

- `docs/`
- `control/`

禁止修改：

- `main` 工作区。
- `.env`
- 用户未提交草稿。

关键要求：

- 只在 `develop` 派生的 task worktree 中准备同步清单。
- 不直接合并到 `main`。
- 明确 `main` 当前存在用户草稿 `docs/ASSET_GRAPH_COMPILER_V0_1.md` 时的处理策略。
- 清单应服务下一次人工 / 主代理同步窗口。

验收命令：

```bash
git diff --check
```

### P0-K MapCompilePackage 覆盖更多战斗节点

任务类型：实现 / 内容管线

建议分支：

```text
task/map-compile-package-more-nodes
```

目标：

```text
为 `lamp_wick_store` 与 `old_signal_tower` 生成 MapCompilePackage，使三张 MVP 战斗地图都有编译证据包。
```

允许修改：

- `examples/map_compile_packages/`
- `tools/asset_graph/`
- `tools/demo/`
- `docs/MAP_VISUAL_REFERENCE_PIPELINE_V0_1.md`

关键要求：

- 不复制首战 JSON 后只改 ID；应从对应 `MapRuntimePackage` 派生逻辑层。
- 对应节点没有发布底图时可以标记 `painted_visual_layer.status = missing` 或 `warning`，但必须保留 runtime truth。
- evidence exporter 应继续覆盖全部 map compile packages。

验收命令：

```bash
python3 tools/asset_graph/validate_map_compile_package.py examples/map_compile_packages/mvp_first_battle.map_compile_package.json
python3 tools/demo/export_evidence.py --output-dir /tmp/ai_td_demo_evidence
```

### P0-L 前端视觉运行态截图验收

任务类型：验证 / 前端体验

```text
task/frontend-visual-screenshot-audit
```

目标：

```text
启动本地前端或后端服务，获取战斗页截图，确认默认玩家视图没有控制图 / 参考图 / 棋盘图污染。
```

允许修改：

- `docs/`
- `artifacts/` 或 `/tmp` 输出截图

关键要求：

- 能启动服务则用浏览器截图。
- 如果当前环境缺 Chromium / Playwright，必须记录替代验证和缺口。
- 不为了截图引入大型前端构建链。

验收命令：

```bash
git diff --check
```

## 5. P1 任务

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

### P1-B 世界演化预生成与调度

目标：

```text
建立类似视频缓冲的后台预生成机制，让剧情、任务、地图、资产在玩家到达前被异步准备。
```

要点：

- 区分 blocking、prefetch、background、lazy。
- 引入预算、失败重试、降级 fixture。
- 世界演化必须服务玩法和进度，不自由失控生长。

### P1-C 更多可编译对象覆盖

目标：

```text
继续扩展 NPC、任务、随机事件、剧情节点、材料、怪物、地图、设施等可编译对象。
```

要点：

- 所有对象先进入统一 CGOP / package manifest 模型。
- 不允许直接自由写 runtime。
- 每类对象定义最小可玩字段和审查门禁。

### P1-D Map Visual Reference 生成管线升级

目标：

```text
把地图参考图升级为可选的开发者管线：逻辑地图 -> 控制图 / composition sketch -> 地图底图生成 -> 结构化路线与塔位回写。
```

要点：

- 图像模型只负责自然游戏地图渲染。
- 路线、塔位、目标以结构化数据为准。
- 需要支持世界书风格、地形、威胁状态和黑暗区域。
- 该任务在 `P0-G MapCompilePackage v0.2` 之后执行。

### P1-E 手动 CodeBuddy / OpenCode 任务交付包

目标：

```text
生成可粘贴给用户侧 CodeBuddy / OpenCode 主代理的任务包模板。
```

要点：

- 任务包包含允许修改范围、验收命令、禁止事项、汇报格式。
- 可被 IDE 侧代理读取完整仓库后执行。
- 不要求本 Codex 受控通道直接外发仓库上下文。

## 6. P2 暂不做

本阶段明确不做：

- 复杂注册登录、多用户权限、联机同步。
- 真 3D 战斗画面。
- 玩家运行时任意代码执行。
- 游戏内可视化 DAG 编辑器。
- 游玩中实时生成长视频作为关键路径。
- 完整长期存档和跨局世界继承。
- 复杂后台管理系统。

## 7. 推荐执行顺序

建议当前批次按以下顺序推进：

1. `P0-K` MapCompilePackage 覆盖更多战斗节点。
2. `P0-L` 前端视觉运行态截图验收。
3. `P0-I` main 文档受控同步准备。

若需要并行，优先组合：

- `P0-K` 与 `P0-I` 可并行。
- `P0-L` 依赖当前前端视觉防线，但不依赖 `P0-K`。
- `P1-A` 视频帧 / atlas 默认接入应在地图质量防线之后推进，避免动画资产先接入了错误的地图展示框架。
