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
- 前端媒体 manifest、animation seed、atlas 和 runtime art kit 的后端加载入口已拆分到 `backend/app/services/frontend_media_service.py`。
- 战斗配置和 reviewed runtime package 的后端加载入口已拆分到 `backend/app/services/battle_content_service.py`。
- MapRuntimePackage v0.1：首战节点已有路径、塔位、目标、出生点和本地视觉层引用。
- MapRuntimePackage 后端加载入口已拆分到 `backend/app/services/map_runtime_service.py`；`frontend_mock_service.py` 只在战斗配置和 runtime package 聚合响应中附带地图包。
- AI 编译核心对象示例、refs、Research Job 原生快照与 battle settlement 原生快照构造入口已拆分到 `backend/app/services/ai_core_artifact_service.py`。
- 前端已优先消费 MapRuntimePackage，旧 battle config 只作为兼容 fallback。
- 当前前端是 no-build MVP shell，不再以早期 React/Vite/Phaser 骨架任务为事实源。

当前缺口：

- 地图已经有 3 个 `MapRuntimePackage`、3 个 `MapCompilePackage v0.2`，并登记了带质量状态的视觉层；玩家侧只允许使用 `authority=published_visual_layer` 且 `player_visible_quality=passed` 的图，`agnes_02` 与 `battle_runtime_background.v0.2` 当前只作为失败/候选证据保留。后续缺口是更强的图像模型自动验图、像素级坐标回配和多节点差异化发布底图。
- `MapVisualQualityReport v0.1` 已接入 evidence，用于标记三节点复用同一玩家底图、发布底图需要 overlay correction、视觉审查证据偏弱等问题；当前状态为 `passed_with_warnings`，不阻断 MVP，但作为下一轮地图重生 / 差异化发布底图任务的输入。
- `NodeMapPaintedCandidateReview v0.2` 已接入 evidence，用于记录节点专属真实 Agnes 地图候选的审查结果；`clean_scene_v2` 当前三张候选均已清除主要箭头、单位和战斗特效问题，但仍需坐标对齐、战斗可读性复核和显式晋升。该报告证明地图生成管线已能迭代产出更干净的候选，也证明发布门禁不会把未对齐图误放给前端。
- `MapCandidateAlignmentReview v0.1` 已接入 evidence，用于把三张 `clean_scene_v2` 候选与 MapRuntimePackage 的路径、塔位、目标和出生点做结构前置审查；当前状态为 `ready_for_overlay_review_with_transform_required`，说明三张图都能进入 overlay review，但必须先做尺寸标准化，不能直接发布。
- `MapCandidateOverlayReview v0.1` 已接入 evidence，用于把三张 `clean_scene_v2` 候选标准化为 `1280x720` 并生成路径、塔位、出生点、目标的 SVG overlay 审查图；当前状态为 `overlay_artifacts_ready_review_required`，但仍是 review-only，不会自动进入前端 runtime，且 artifact ready 不等于视觉对齐已批准。
- `MapCandidateOverlayVisualReview v0.1` 已接入 evidence，用 raster overlay PNG 记录人工视觉复核结论；当前三张候选均 `do_not_promote`，主要问题是 runtime 路径/目标/塔位与视觉道路、核心物和建造点未完全一致。下一轮应优先做 runtime 坐标重投影或拓扑约束重生，而不是直接晋升。
- `MapLayoutReconciliationPlan v0.1` 已接入 evidence，把三张地图候选拆成 P0 后续动作：灰灯驿站混合重投影后复核，灯芯仓优先 runtime 路径重投影，旧信号塔优先拓扑约束重生或先做核心位置决策。该计划仍不修改 runtime 包，不晋升视觉层。
- `RuntimeMapPatchCandidates v0.1`、`MapPatchOverlayReview v0.1` 与 `TopologyConstrainedMapPromptPack v0.1` 已接入 evidence。前者为灰灯驿站、灯芯仓产出 review-only 坐标/路径/塔位补丁候选；中者把补丁应用到内存 MapRuntimePackage 快照并生成补丁后 overlay PNG/SVG 与 review-only runtime 快照，当前两张补丁后包结构校验通过但仍不能晋升；后者为旧信号塔产出拓扑约束重生 prompt，并为另外两张图保留 fallback prompt。三者都不自动修改 runtime，不发布视觉层。
- `TopologyConstrainedMapCandidateReview v0.1`、`TopologyConstrainedMapAlignmentReview v0.1`、`TopologyConstrainedMapOverlayReview v0.1` 与 `TopologyConstrainedMapOverlayVisualReview v0.1` 已接入 evidence。旧信号塔已通过 Agnes 生成一张真实拓扑约束候选并完成标准化、overlay 和视觉复核；当前可晋升数为 0，主要问题是塔体仍偏大、存在小人/杂物感噪声，后续应迭代 prompt 或做清理重生。
- `TopologyConstrainedMapPromptPack v0.2` 已把 visual review 失败原因转成 prompt repair，并调用 Agnes 生成 v2 候选；该候选被审查为 `review_only_not_runtime_ready`。这证明旧信号塔下一步不应继续盲目 prompt-only 生成。
- `MapTopologyControlSketchPack v0.1` 已把三张 MapRuntimePackage 确定性转成无文字、无 UI、无敌人、无塔的控制构图 PNG，以及带开发者标签的 SVG 审查图；该包只用于 compile-time reference / evidence，不进入玩家 runtime。下一步应基于控制图做受控图像重生、局部清理或视觉模型审查，再重新走 candidate / alignment / overlay / visual / promotion gates。
- `MapControlledRegenerationRequestPack v0.1` 已把控制构图 PNG、v0.2 prompt repair、负面约束、目标候选目录和 review gates 编译成三张地图的 reference-image request。下一步真实 provider 调用、人工 paintover 或局部清理应消费该 request pack，避免继续从散落 prompt 或截图临时拼输入。
- 战斗和大地图视觉仍需继续游戏化，不能停留在控制图、参考图、突兀棋盘或临时调试画布；默认玩家视图已加防线，战斗 HUD 已压低遮挡，并完成无浏览器环境下的静态视觉合约校验，但仍需要在有 Chromium / Playwright 的环境中补截图。
- `MediaAtlasManifest v0.1` 已以 `spritesheet` 多帧模式默认接入前端运行时；实体 atlas PNG 已生成并由前端战斗绘制优先裁剪使用，真实图生视频关键帧仍未生成。
- `ContextPackage v0.1`、`FactEntry v0.1`、`CompiledGameObjectPackage v0.1`、`WorldStateDeltaTransaction v0.1` 已有 schema、最小示例和统一 validator；Research Job proposal / job metadata、battle settlement evidence 与 frontend mock pack 已携带 ContextPackage、FactEntry、CGOP 原生快照，并保留 core artifact refs / world delta 兼容字段。WorldStateDeltaTransaction 已扩展为 stage01-stage07 事务链，后续缺口是把更广义的 review pack 和真实 provider 产物继续迁移到原生对象字段。
- Sprite cutout quality report 已接入 evidence，用于识别内部透明洞、主体碎裂、漂浮组件和边缘接触；当前仅生成 `needs_review` 排序，不阻断 MVP。
- Sprite cutout repair plan 已接入 evidence，用于把 `needs_review` 转成重抠图、重生成或人工复核任务。
- Sprite repair candidate pack 已接入 evidence，用于验证确定性修复候选；候选仍是 review-only，不替换正式 runtime。
- Sprite live regeneration candidate pack 已接入 evidence，用于对 runtime P1 问题素材调用真实图像 provider 生成 review-only 候选；候选仍不替换正式 runtime。
- Sprite regeneration promotion report 已接入 evidence，用于证明通过审查的 runtime P1 候选经过显式晋升后才替换 published runtime media，并已重建 atlas。
- GenerationSchedulePlan v0.1 与 GenerationScheduleRunReport v0.1 已接入 evidence 和后端 session mock API，并已支持 session 级 dry-run 运行记录持久化、item 级队列视图、claim / complete / fail / retry / fallback 状态流转、attempt 预算和 dry-run worker step；真实后台执行器、长期存档还未形成稳定实现。
- Campaign Router v0.1 已作为最薄运行时游标接入后端 mock API，并已被 no-build 前端消费：可返回当前节点、下一节点、前视窗口、已审资产 handle 和 scheduler 信号，前端进入当前节点时会通过 `prefetch-next` 触发一次 fixture-backed dry-run 预取步；它不调用 provider、不写世界状态、不创建新内容。
- 多节点战斗结算桥已接入后端 mock API：`gray_lantern_station` 与 `lamp_wick_store` 使用真实 `battle_result` transaction 推进运行态；`old_signal_tower` 使用 stage06 `research_job` after-state 作为 `fixture_bridge`，不得伪装成战斗结果。`tools/dev/validate_multinode_battle_settlement.py` 已接入 demo evidence。

## 3. 已完成的 P0 基线

以下任务已经合入 `develop`，后续 worker 不应重复实现；如需修改，应另开精确修补任务。

### P0-A 前端战斗画面与大地图视觉初版

状态：已完成。

已落地：

- 战斗主画面默认使用通过质量门的 `painted_visual_layer`；`battle_runtime_background` 必须同样通过质量门才可作为玩家 fallback，否则只能进入 debug/evidence。
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
- `ContextPackage / FactEntry / CGOP` 的字段级 schema 已作为 P1 前置事实源落地。

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

- 前端默认玩家视图只优先使用通过 `player_visible_quality=passed` 的 `painted_visual_layer` / `battle_runtime_background`。
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
- `game_data/media/frontend_mock/atlas_sheets/`
- `game_data/media/frontend_runtime_mock/atlas_frames/`
- `game_data/media/frontend_runtime_mock/atlas_sheets/`
- 前端 `mediaUrl()` 保持旧接口，战斗绘制优先按 battle elapsed time 从实体 spritesheet 裁剪当前帧。
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
- `shared/schemas/generation_schedule_run_report.v0.1.schema.json`
- `tools/scheduler/run_generation_schedule_plan.py`
- `tools/scheduler/validate_generation_schedule_run_report.py`
- `examples/review_packs/mvp_generation_schedule_run_report.v0.1.json`
- `docs/GENERATION_SCHEDULER_V0_1.md`
- `tools/demo/export_evidence.py` 已纳入 schedule plan 摘要和验证命令。

当前结论：

- 计划包包含 8 个调度项，覆盖 `sync_blocking`、`background_prefetch`、`background`、`lazy`、`fallback_static`。
- dry-run 报告把 8 个调度项分为 `reuse_ready: 3`、`select_fallback: 1`、`schedule_prefetch: 2`、`schedule_background: 1`、`schedule_lazy: 1`，provider 调用数和世界修改数均为 0。
- 同步项只读取已审 fixture / locked package / published manifest，不依赖实时 provider。
- 预取和后台项只声明候选生成计划，启用前必须重新通过对应 validator、semantic gate 或 media gate。
- 这不是后台执行器；后续仍需实现真正的队列、缓存、重试、状态持久化和 live campaign router。

### P1-B-1 Generation Scheduler session API 缓冲层

状态：已完成最小骨架。

已落地：

- `GET /api/sessions/{session_id}/generation-schedule`
- `backend/app/services/generation_scheduler_service.py` 已加载 `GenerationSchedulePlan v0.1` 与 `GenerationScheduleRunReport v0.1`，并维护 session dry-run 与队列状态。
- `generation_schedule.buffer` 提供 session 可见的紧凑摘要，包括 latency class、dry-run action、fallback、复验要求、provider 调用数和世界修改数。
- `/api/sessions/{session_id}/evidence` 已带 `generation_scheduler` 摘要，便于 Studio / 录屏证明调度器存在。
- `docs/FRONTEND_MOCK_API_V0_1.md` 已记录接口边界。

当前结论：

- 该接口仍是 fixture-backed / review-only，不启动后台 worker，不调用真实 provider，不修改世界状态。
- 它把“预生成缓冲”接到了后端 API 面，方便前端或演示读取；真实队列、缓存、重试、状态持久化和 provider 调度仍属后续 P1-B。

### P1-B-2 Generation Scheduler session dry-run 持久化

状态：已完成最小骨架。

已落地：

- `generation_schedule_runs` SQLite 表。
- `POST /api/sessions/{session_id}/generation-schedule/runs`
- `GET /api/sessions/{session_id}/generation-schedule/runs/latest`
- session reset 会清除对应调度运行记录。
- `/api/sessions/{session_id}/generation-schedule` 会返回最近一次持久化 dry-run。
- `/api/sessions/{session_id}/evidence` 会返回最近一次调度运行摘要。

当前结论：

- 该层仍不启动后台 worker，不调用 provider，不修改世界状态，不激活预取候选。
- 它把 Generation Scheduler 从离线 evidence 推进到后端状态层，为下一步真实队列、缓存、重试和 provider 调度留出落点。

### P1-B-3 Generation Scheduler item 级队列视图

状态：已完成最小骨架。

已落地：

- `generation_schedule_queue_items` SQLite 表。
- `GET /api/sessions/{session_id}/generation-schedule/queue`
- 每次 dry-run 会把 8 个 schedule items 派生为队列记录。
- `completed` 表示已审同步内容复用完成。
- `fallback_ready` 表示静态兜底可用。
- `queued` 表示预取、后台或懒加载候选等待后续 worker 处理。
- session reset 会清除对应队列项。
- `/api/sessions/{session_id}/evidence` 会返回最近一次队列摘要。

当前结论：

- 该队列仍不自动调用 provider，不领取真实任务，不修改世界状态。
- 它为后续后台 worker、缓存、重试、provider 调度和启用前复验提供最小可查询状态面。

### P1-B-4 Generation Scheduler 队列项状态流转

状态：已完成最小骨架。

已落地：

- `POST /api/sessions/{session_id}/generation-schedule/queue/{schedule_item_id}/claim`
- `POST /api/sessions/{session_id}/generation-schedule/queue/{schedule_item_id}/complete`
- `POST /api/sessions/{session_id}/generation-schedule/queue/{schedule_item_id}/fail`
- 队列 payload 会记录 transition log、worker_id、note 和时间戳。
- 非法状态流转返回 `409`，缺失队列项返回 `404`。

当前结论：

- 当前只支持本地 dry-run 队列状态流转，不调用 provider，不生成新内容，不写世界状态。
- 这为后续真实后台 worker 提供最小领取和回写接口。

### P1-B-5 Generation Scheduler dry-run worker step

状态：已完成最小骨架。

已落地：

- `POST /api/sessions/{session_id}/generation-schedule/workers/dry-run-step`
- 每次处理最近一次 run 中的一个 `queued` 项。
- 需要 provider 或人工复核的项进入 `waiting_review`。
- 不需要额外复核的项可进入 `completed`。
- 无可处理项时返回 `idle`。
- `waiting_review` 项允许后续通过 `complete` 或 `fail` 人工 / 系统复核收束。

当前结论：

- dry-run worker step 不调用 provider，不生成新内容，不写世界状态，不激活预取候选。
- 它只把后续后台 worker 的领取、处理、等待复核状态面跑通。

### P1-B-6 Generation Scheduler retry / fallback 守门

状态：已完成最小骨架。

已落地：

- 队列项从 `GenerationSchedulePlan.provider_policy.max_attempts` 继承 `max_attempts`。
- dry-run worker step 每处理一次 `queued` 项会递增 `attempt_count`。
- `POST /api/sessions/{session_id}/generation-schedule/queue/{schedule_item_id}/retry`
- `POST /api/sessions/{session_id}/generation-schedule/queue/{schedule_item_id}/fallback`
- `retry` 只允许 `failed -> queued`，且 `attempt_count < max_attempts`。
- `fallback` 允许 `failed|waiting_review -> fallback_ready`，且必须存在 `fallback_ref`。

当前结论：

- 该层仍不调用 provider，不生成新内容，不写世界状态。
- 它为后续真实 provider 调度建立最小 attempt 预算、重试上限和降级路径。

## 4. 当前 P0 任务

暂无。当前 P0 已全部关闭。

补充：`WorldStateDeltaTransaction v0.1` 已作为架构固化项落地到 schema、批量 validator、首战示例、stage01-stage07 事务链和 demo evidence；它包装现有 `WorldStateDelta v0.1`，不替换 delta schema，也不允许通用 `effects[]` 绕过 `operations[]` 白名单。

补充：Campaign Router 消费的三节点 MVP 主线已经能通过战斗结算接口连续推进。`lamp_wick_store` 使用 stage04 battle_result transaction；`old_signal_tower` 当前只有 research_job 来源的 after-state，因此以 `fixture_bridge` 暴露，并在返回值中保留 `fixture_baseline` 说明。

下一轮进入 P1 前，应先确认是否开始执行 `docs/MAIN_SYNC_PLAN_2026_07_02.md`。`main` 上 `docs/ASSET_GRAPH_COMPILER_V0_1.md` 用户草稿的有效媒体 guardrail 已合入 `develop`，但同步 `main` 前仍需保存草稿 diff 并确认是否晋级整个 `develop`。

## 5. P1 任务

### P1-A 视频帧 / spritesheet / atlas 增强

目标：

```text
在已接入 virtual atlas 的基础上，继续固化“图片 -> 图生视频 -> 关键帧 -> 后处理 -> spritesheet atlas -> runtime manifest”路线。
```

要点：

- `virtual_single_frame`、确定性 4 帧 frame sequence 与实体 spritesheet atlas 已完成；本任务后续继续推进真实图生视频关键帧。
- 首尾帧一致或 end frame 控制优先。
- 加入 LoopContinuityCheck。
- 后处理产物需支持透明 PNG、anchor、frame alignment、atlas json。
- 前端已优先消费实体 spritesheet atlas，静态 PNG 作为 fallback；后续需把当前确定性 frame PNG 来源升级为真实视频关键帧。

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
- Research Job proposal / job metadata、battle settlement evidence、frontend mock pack、多节点 battle settlement 与 stage01-stage07 WorldStateDeltaTransaction 链已开始携带或引用统一核心对象；下一步应把现有 review pack 和真实 provider 产物继续映射到同一套核心对象字段，而不是继续新增平行元数据口径。

### P1-D Map Visual Reference 生成管线升级

目标：

```text
把地图参考图升级为可选的开发者管线：逻辑地图 -> 控制图 / composition sketch -> 地图底图生成 -> 结构化路线与塔位回写。
```

要点：

- 图像模型只负责自然游戏地图渲染。
- 路线、塔位、目标以结构化数据为准。
- 需要支持世界书风格、地形、威胁状态和黑暗区域。
- 必须消费 `MapVisualQualityReport v0.1` 的 warnings，优先解决节点专属玩家底图、overlay correction 和视觉审查证据不足。
- 必须消费 `NodeMapPaintedCandidateReview v0.2` 的候选结论，下一步重点不是继续盲目生图，而是做坐标对齐、裁切/尺寸标准化、战斗可读性复核和显式晋升流程；候选图只能在显式晋升后进入 published visual layer。
- 必须消费 `MapCandidateAlignmentReview v0.1` 的对齐前置结论；下一步任务应生成 normalized candidate、overlay review 截图或结构化 overlay report，然后再决定是否晋升 published visual layer。
- 必须消费 `MapCandidateOverlayReview v0.1` 的 normalized PNG 与 SVG overlay；下一步应做人眼或视觉模型 overlay 复核，确认路径、塔位、目标与画面语义不冲突，再通过独立 promotion report 晋升。
- 必须消费 `MapCandidateOverlayVisualReview v0.1` 的拒绝晋升结论；下一步任务应生成 layout reconciliation plan，明确每个节点是重投影 runtime coordinates，还是重新生成符合现有 topology 的地图。
- 必须消费 `MapLayoutReconciliationPlan v0.1` 的节点级动作；下一步可拆为 `RuntimeMapPatchCandidate` 和 `TopologyConstrainedMapPromptPack` 两条任务，前者只产出 review-only runtime patch，后者只产出更严格的地图重生 prompt / control brief。
- 必须消费 `RuntimeMapPatchCandidates v0.1`、`TopologyConstrainedMapPromptPack v0.1/v0.2`、`MapTopologyControlSketchPack v0.1` 和 `MapControlledRegenerationRequestPack v0.1`。下一步候选任务：对 runtime patch candidate 重新生成 overlay PNG 复核；用 controlled regeneration request pack 调用支持参考图的真实图像 provider 或做局部清理，并重新走 candidate / alignment / overlay / visual review gates。
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

1. 确认是否执行 `docs/MAIN_SYNC_PLAN_2026_07_02.md`，并在执行前保护 `main` 工作区草稿。
2. WorldStateDelta / review pack 继续从 refs/evidence 对齐推进到原生产物字段；Research Job、battle settlement evidence 与 frontend mock pack 已完成第一层原生快照迁移。
3. 地图补丁后 overlay 人工/视觉模型复核，以及基于 MapControlledRegenerationRequestPack 的参考图受控重生 / 局部清理路线；只有通过 promotion gate 后才允许更新正式 MapRuntimePackage 或发布底图。
4. `P1-A` 真实视频关键帧增强。
5. `P1-B` Generation Scheduler 执行器 / live campaign router。

若需要并行，优先组合：

- `P1-A` 与 `P1-B` 可并行，但都应避免破坏当前 MVP 静态 fixture 路径。
- main 同步执行必须单独进行，不应与大规模 P1 实现任务混在同一 worktree。
- `P1-A` 视频帧 / atlas 增强应在地图质量防线之后推进，避免动画资产先接入了错误的地图展示框架。
