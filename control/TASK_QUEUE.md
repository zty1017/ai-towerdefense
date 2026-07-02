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
- 媒体后处理 mock assets、processed PNG、animation seed manifest、spritesheet 兼容多帧 atlas manifest。
- 前端运行时 mock 美术包：敌人、目标物、基础防御件、NPC 头像、地图 token、程序化特效。
- MapRuntimePackage v0.1：首战节点已有路径、塔位、目标、出生点和本地视觉层引用。
- 前端已优先消费 MapRuntimePackage，旧 battle config 只作为兼容 fallback。
- 当前前端是 no-build MVP shell，不再以早期 React/Vite/Phaser 骨架任务为事实源。

当前缺口：

- 地图已经有 3 个 `MapRuntimePackage`、3 个 `MapCompilePackage v0.2`，并登记了玩家侧 `painted_visual_layer` 与逻辑对齐 fallback `battle_runtime_background`；后续缺口是更强的图像模型自动验图、像素级坐标回配和多节点差异化发布底图。
- 战斗和大地图视觉仍需继续游戏化，不能停留在控制图、参考图、突兀棋盘或临时调试画布；默认玩家视图已加防线，战斗 HUD 已压低遮挡，并完成无浏览器环境下的静态视觉合约校验，但仍需要在有 Chromium / Playwright 的环境中补截图。
- `MediaAtlasManifest v0.1` 已以 `spritesheet` 兼容多帧模式默认接入前端运行时；真实图生视频关键帧与实体 atlas PNG 仍未生成。
- Sprite cutout quality report 已接入 evidence，用于识别内部透明洞、主体碎裂、漂浮组件和边缘接触；当前仅生成 `needs_review` 排序，不阻断 MVP。
- Sprite cutout repair plan 已接入 evidence，用于把 `needs_review` 转成重抠图、重生成或人工复核任务。
- Sprite repair candidate pack 已接入 evidence，用于验证确定性修复候选；候选仍是 review-only，不替换正式 runtime。
- Sprite live regeneration candidate pack 已接入 evidence，用于对 runtime P1 问题素材调用真实图像 provider 生成 review-only 候选；候选仍不替换正式 runtime。
- Sprite regeneration promotion report 已接入 evidence，用于证明通过审查的 runtime P1 候选经过显式晋升后才替换 published runtime media，并已重建 atlas。
- GenerationSchedulePlan v0.1 已接入 evidence，用于声明 sync_blocking、background_prefetch、background、lazy 和 fallback_static 内容；真实后台执行器、live campaign router、长期存档还未形成稳定实现。

## 3. 已完成的 P0 基线

以下任务已经合入 `develop`，后续 worker 不应重复实现；如需修改，应另开精确修补任务。

### P0-A 前端战斗画面与大地图视觉初版

状态：已完成。

已落地：

- 战斗主画面默认使用 `painted_visual_layer` 作为玩家可见发布底图；`battle_runtime_background` 只作为逻辑对齐 fallback。
- `battle_control_sketch` 与 `battle_reference_board` 被降级为控制 / 参考层，不应进入默认玩家体验。
- 前端根据 `MapRuntimePackage` 叠加路径、塔位、目标、出生点和拖拽部署预览。
- `tools/frontend/validate_battle_visual_contract.py` 已用于无浏览器环境的静态视觉合约校验。

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

### P0-K MapCompilePackage 覆盖更多战斗节点

状态：已完成。

已落地：

- `examples/map_compile_packages/mvp_wick_store_pressure.map_compile_package.json`
- `examples/map_compile_packages/mvp_old_signal_tower_pressure.map_compile_package.json`
- 三个 MVP 战斗节点均有地图编译证据包，demo evidence 会自动收集三份。

### P0-L 前端视觉运行态截图验收

状态：已完成替代验收。

已落地：

- `docs/FRONTEND_VISUAL_RUNTIME_AUDIT_V0_1.md`
- 已验证前端语法、默认玩家底图代码路径、发布底图资源、首战 `MapRuntimePackage` 视觉层 authority、本地 HTTP 静态读取。
- 当前环境缺 Chromium / Playwright，因此未生成真实截图；该缺口已记录为后续人工或具备浏览器环境的验证项。

### P0-I main 文档受控同步准备

状态：已完成。

已落地：

- `docs/MAIN_SYNC_PLAN_2026_07_02.md`
- 明确 `main` 当前存在用户草稿 `docs/ASSET_GRAPH_COMPILER_V0_1.md`，不得直接覆盖。
- 给出 develop 晋级 main 前的验证清单、同步策略、禁止操作和人工确认项。

### P1-A-0 MediaAtlasManifest virtual atlas 接入

状态：已完成。

已落地：

- `shared/schemas/media_atlas_manifest.v0.1.schema.json`
- `tools/media/build_media_atlas_manifest.py`
- `tools/media/validate_media_atlas_manifest.py`
- `game_data/media/frontend_mock/frontend_media_atlas_manifest.v0.1.json`
- `game_data/media/frontend_runtime_mock/frontend_runtime_art_atlas_manifest.v0.1.json`
- 前端优先通过 atlas 第一帧查找媒体，缺失时回退旧 media manifest。
- 后端 mock API 和 demo evidence 已返回 / 展示 atlas manifest。

### P1-A-1 MediaAtlasManifest 多帧 frame sequence 接入

状态：已完成。

已落地：

- `tools/media/build_multiframe_atlas_manifest.py`
- `tools/media/validate_multiframe_atlas_contract.py`
- `game_data/media/frontend_mock/atlas_frames/`
- `game_data/media/frontend_runtime_mock/atlas_frames/`
- 前端 `mediaUrl()` 保持旧接口，但会按 battle elapsed time 从 atlas frames 中选择当前帧。
- sprite 类角色生成 4 帧循环，静态图标 / 头像 / UI 卡保持 1 帧。

### P1-A-2 Sprite cutout quality gate

状态：已完成。

已落地：

- `tools/media/audit_sprite_cutout_quality.py`
- `examples/review_packs/frontend_sprite_cutout_quality_report.v0.1.json`
- `examples/review_packs/frontend_runtime_sprite_cutout_quality_report.v0.1.json`
- `tools/demo/export_evidence.py` 已纳入两份 cutout quality 摘要和验证命令。

当前结论：

- frontend mock sprite：`needs_review`，2 / 4 个需复核。
- runtime battle sprite：`passed`，7 / 7 个通过。
- 无硬失败；frontend mock 报告仍用于后续重生素材、重抠图和真实视频关键帧替换排序，runtime 当前已达到 MVP 几何质量门。

### P1-A-3 Sprite cutout repair plan

状态：已完成。

已落地：

- `tools/media/build_sprite_cutout_repair_plan.py`
- `examples/review_packs/frontend_sprite_cutout_repair_plan.v0.1.json`
- `examples/review_packs/frontend_runtime_sprite_cutout_repair_plan.v0.1.json`
- `tools/demo/export_evidence.py` 已纳入两份 repair plan 摘要和验证命令。

当前结论：

- frontend mock repair plan：2 个任务，优先级分布 `P1: 1, P2: 1`。
- runtime repair plan：0 个任务，已随 runtime sprite 晋升与复核清空。
- 这些任务是下一轮素材重生 / 重抠图 / 视频关键帧替换的输入，不直接改动玩家侧资产。

### P1-A-4 Sprite repair candidates

状态：已完成。

已落地：

- `tools/media/build_sprite_repair_candidates.py`
- `examples/review_packs/frontend_sprite_repair_candidates.v0.1.json`
- `examples/review_packs/frontend_runtime_sprite_repair_candidates.v0.1.json`
- `examples/review_packs/frontend_sprite_repair_candidate_quality_report.v0.1.json`
- `examples/review_packs/frontend_runtime_sprite_repair_candidate_quality_report.v0.1.json`
- `tools/demo/export_evidence.py` 已纳入候选包摘要和验证命令。

当前结论：

- frontend repair candidates：2 个候选，几何质量门 `passed`，未晋升 runtime。
- runtime repair candidates：0 个候选；旧的 `fill_interior_holes` 驿站核心候选已删除，runtime 改走真实重生成与显式晋升。
- 抽查显示 `fill_interior_holes` 会把部分开放结构填实，因此这类确定性候选只能作为审查证据；后续应优先走真实重生成 / 更强分割 / 人工确认。

### P1-A-5 Runtime sprite live regeneration candidates

状态：已完成。

已落地：

- `tools/media/generate_sprite_regeneration_candidates.py`
- `examples/review_packs/frontend_runtime_sprite_regeneration_candidates.v0.1.json`
- `examples/review_packs/frontend_runtime_sprite_regeneration_candidate_quality_report.v0.1.json`
- `game_data/media/sprite_regeneration_candidates/frontend_runtime_mock/raw/`
- `game_data/media/sprite_regeneration_candidates/frontend_runtime_mock/processed/`
- `tools/demo/export_evidence.py` 已纳入 live regeneration 候选摘要和离线验证命令。

当前结论：

- 使用 Agnes 真实生成 runtime 信标、基础灯栏与驿站核心候选，各 1 个，几何质量门 `passed`。
- 基础灯栏经过多轮提示词收紧，从围栏 enclosure 收敛为单段便携路障；这说明重生成 DAG 需要支持单素材迭代、复用 raw 后处理和人工/视觉复核。
- 驿站核心经过 provider 对比和提示词收紧后选择 Agnes 候选；一次 GLM free 尝试返回非 PNG / 带水印图像，后续 provider adapter 需要补格式转换与水印门禁。
- 候选包仍是 `review_candidate_media`，不会自动替换正式 runtime 素材；晋升需要下一步人工/视觉审查和显式 promotion。

### P1-A-6 Runtime sprite regeneration promotion

状态：已完成。

已落地：

- `tools/media/promote_sprite_regeneration_candidates.py`
- `examples/review_packs/frontend_runtime_sprite_regeneration_promotion_report.v0.1.json`
- `game_data/media/frontend_runtime_mock/frontend_runtime_art_media_manifest.v0.1.json`
- `game_data/media/frontend_runtime_mock/frontend_runtime_art_atlas_manifest.v0.1.json`
- `game_data/media/frontend_runtime_mock/atlas_frames/`
- `examples/review_packs/frontend_runtime_sprite_cutout_quality_report.v0.1.json`
- `examples/review_packs/frontend_runtime_sprite_cutout_repair_plan.v0.1.json`
- `tools/demo/export_evidence.py` 已纳入 promotion report 摘要和 dry-run 验证命令。

当前结论：

- 信标、基础灯栏与驿站核心候选已显式晋升到 published runtime media，并重建 runtime atlas。
- runtime sprite cutout quality 从 `needs_review 3 / 7` 推进到 `passed 7 / 7`。
- runtime sprite repair plan 已清空；后续新增问题仍走同一套重生成和 promotion 流程。
- 晋升工具默认 dry-run，必须显式 `--apply` 才能替换 runtime PNG 和 manifest。

### P1-B-0 Generation Scheduler review-only 计划包

状态：已完成最小骨架。

已落地：

- `shared/schemas/generation_schedule_plan.v0.1.schema.json`
- `tools/scheduler/build_generation_schedule_plan.py`
- `tools/scheduler/validate_generation_schedule_plan.py`
- `examples/review_packs/mvp_generation_schedule_plan.v0.1.json`
- `docs/GENERATION_SCHEDULER_V0_1.md`
- `tools/demo/export_evidence.py` 已纳入 schedule plan 摘要和验证命令。

当前结论：

- 计划包包含 8 个调度项，覆盖 `sync_blocking`、`background_prefetch`、`background`、`lazy`、`fallback_static`。
- 同步项只读取已审 fixture / locked package / published manifest，不依赖实时 provider。
- 预取和后台项只声明候选生成计划，启用前必须重新通过对应 validator、semantic gate 或 media gate。
- 这不是后台执行器；后续仍需实现真正的队列、缓存、重试、状态持久化和 live campaign router。

## 4. 当前 P0 任务

暂无。当前 P0 已全部关闭。

下一轮进入 P1 前，应先确认是否开始执行 `docs/MAIN_SYNC_PLAN_2026_07_02.md`，尤其是 `main` 上 `docs/ASSET_GRAPH_COMPILER_V0_1.md` 用户草稿的合并策略。

## 5. P1 任务

### P1-A 视频帧 / spritesheet / atlas 增强

目标：

```text
在已接入 virtual atlas 的基础上，继续固化“图片 -> 图生视频 -> 关键帧 -> 后处理 -> spritesheet atlas -> runtime manifest”路线。
```

要点：

- `virtual_single_frame` 与确定性 4 帧 frame sequence 已完成；本任务后续继续推进真实图生视频关键帧。
- 首尾帧一致或 end frame 控制优先。
- 加入 LoopContinuityCheck。
- 后处理产物需支持透明 PNG、anchor、frame alignment、atlas json。
- 前端已优先消费 atlas，静态 PNG 作为 fallback；后续需把当前独立 frame PNG 升级为真实视频关键帧和实体 spritesheet。

### P1-B 世界演化预生成与调度

目标：

```text
建立类似视频缓冲的后台预生成机制，让剧情、任务、地图、资产在玩家到达前被异步准备。
```

要点：

- `GenerationSchedulePlan v0.1` 的 review-only 计划包已完成，后续应基于它实现执行器而不是重新定义调度字段。
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

1. 确认是否执行 `docs/MAIN_SYNC_PLAN_2026_07_02.md`。
2. `P1-A` 真实视频帧 / 实体 spritesheet atlas 增强。
3. `P1-B` Generation Scheduler 执行器 / live campaign router。

若需要并行，优先组合：

- `P1-A` 与 `P1-B` 可并行，但都应避免破坏当前 MVP 静态 fixture 路径。
- main 同步执行必须单独进行，不应与大规模 P1 实现任务混在同一 worktree。
- `P1-A` 视频帧 / atlas 增强应在地图质量防线之后推进，避免动画资产先接入了错误的地图展示框架。
