# 任务队列

Last updated: 2026-07-03

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
- `ControlledMapCandidateGenerationRun v0.1` 已提供 `generate_controlled_map_candidates.py`。默认 reference-image handoff 模式会生成三张 review-only sidecar，不调用 provider、不伪造图片；text-fallback 模式只有显式 `--live` 才调用现有图像 provider，但最新真实调用已证明纯文本整图不适合作为地图发布候选路线。下一步应接支持参考图的 provider adapter、人工 paintover，或实现 `MapRuntimePackage` 驱动的分层程序化底图。
- `ControlledMapCandidateReview v0.1` 已把上述 sidecar 纳入 `build_node_map_candidate_review_pack.py`。当前三个受控候选都被审查为 `awaiting_provider_or_paintover_output`，整体 `review_only_not_runtime_ready`；这证明链路接上了，但在真实图片产出前不会进入 alignment 或晋升。
- `ControlledMapTextFallbackGenerationRun v0.1` 已完成一次真实 Agnes text-fallback 生成，三张图片均有 sidecar 和审查记录；`ControlledMapTextFallbackCandidateReview v0.1` 已全部判定为 `needs_regeneration`，整体 `review_only_not_runtime_ready`。结论是纯文本整图生成会把箭头、控制形状、未授权人物 / 塔位和错误路线烙进背景，不适合作为玩家 runtime 地图底图。后续地图任务应优先改为 reference-image / paintover / MapRuntimePackage 驱动的分层程序化底图。
- `MapVisualPromotionGateReport v0.1` 已接入 evidence，用确定性规则交叉检查 review-only / do_not_promote / needs_regeneration / awaiting provider 的地图候选是否被误挂到玩家侧 `published_visual_layer`。当前阻断候选 22 个、published 玩家图层 4 个、违规 0 个；这证明差图已被隔离为负样本证据，但不代表地图美术质量已完成。
- 前端战斗地图视觉底座已完成 P0-M 到 P1-D v0.4 改造：默认玩家战斗画面不再预加载或绘制失败整图候选，而是由 `MapRuntimePackage` 驱动 canvas 程序化绘制地形、平滑土路、路肩、车辙、部署基座、目标地标、入口雾潮、暗潮洼地、可玩地块边界、可部署台地、路线方向 cue、目标防御区和世界内废墟 / 补给 / 灯具地标；投影已按 runtime bounds 与 HUD safe area 做 contain fit，移动端不再只看到被裁切的局部路段；静态视觉合约已检查控制图隔离、失败图不得发布、棋盘 helper 不得回归、路径 / 塔位 / 目标 / 出生点仍来自结构化地图包。
- 已补浏览器视觉烟测入口 `tools/frontend/capture_battle_visual_smoke.py`：打开 `frontend/index.html?static=1&battleVisualSmoke=1`，采集桌面与移动视口截图并输出 JSON 证据。本轮已通过临时 Playwright Chromium 生成 `/tmp/p0m_browser_visual_smoke/battle_visual_smoke_desktop.png` 与 `/tmp/p0m_browser_visual_smoke/battle_visual_smoke_mobile.png`，并据截图修复移动端 HUD / 工具栏溢出。
- `MediaAtlasManifest v0.1` 已以 `spritesheet` 多帧模式默认接入前端运行时；实体 atlas PNG 已生成并由前端战斗绘制优先裁剪使用。`LoopContinuityReport v0.1` 已接入 frontend mock 与 runtime art 两套 atlas，当前动画均为 deterministic placeholder warning，真实图生视频关键帧仍未生成。
- `ContextPackage v0.1`、`FactEntry v0.1`、`CompiledGameObjectPackage v0.1`、`WorldStateDeltaTransaction v0.1` 已有 schema、最小示例和统一 validator；Research Job proposal / job metadata、battle settlement evidence 与 frontend mock pack 已携带 ContextPackage、FactEntry、CGOP 原生快照，并保留 core artifact refs / world delta 兼容字段。WorldStateDeltaTransaction 已扩展为 stage01-stage07 事务链。`CoreArtifactAlignmentReport v0.1` 已把更广义 review pack / provider artifact / 事务链的核心对象对齐状态纳入 evidence，当前为 `passed`，无 validator 失败、无剩余 P1 迁移任务；`mvp_compiler_review_dossier`、`mvp_stage_candidate_pack`、`mvp_multistage_stage_candidate_pack`、`mvp_multistage_content_pack`、`mvp_next_stage_compilable_object_plan`、`mvp_story_asset_review_pack`、`mvp_story_asset_promotion_report` 与 `mvp_stage05_plan_realization_report` 已显式声明为 `review_only_not_applicable`。
- Sprite cutout quality report 已接入 evidence，用于识别内部透明洞、主体碎裂、漂浮组件和边缘接触；当前仅生成 `needs_review` 排序，不阻断 MVP。
- Sprite cutout repair plan 已接入 evidence，用于把 `needs_review` 转成重抠图、重生成或人工复核任务。
- Sprite repair candidate pack 已接入 evidence，用于验证确定性修复候选；候选仍是 review-only，不替换正式 runtime。
- Sprite live regeneration candidate pack 已接入 evidence，用于对 runtime P1 问题素材调用真实图像 provider 生成 review-only 候选；候选仍不替换正式 runtime。
- Sprite regeneration promotion report 已接入 evidence，用于证明通过审查的 runtime P1 候选经过显式晋升后才替换 published runtime media，并已重建 atlas。
- GenerationSchedulePlan v0.1 与 GenerationScheduleRunReport v0.1 已接入 evidence 和后端 session mock API，并已支持 session 级 dry-run 运行记录持久化、item 级队列视图、claim / complete / fail / retry / fallback 状态流转、attempt 预算和 dry-run worker step；真实后台执行器、长期存档还未形成稳定实现。
- Campaign Router v0.1 已作为最薄运行时游标接入后端 mock API，并已被 no-build 前端消费：可返回当前节点、下一节点、前视窗口、已审资产 handle 和 scheduler 信号，前端进入当前节点时会通过 `prefetch-next` 触发一次 fixture-backed dry-run 预取步；另有 `prefetch-next-dispatcher-drain` 可显式触发 review-only dispatcher drain 预取 tick，用于 Studio / evidence 和后台执行器前置胶水。它们都不调用 provider、不写世界状态、不创建新内容。
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
- 已新增 `tools/frontend/capture_battle_visual_smoke.py` 作为可复跑浏览器烟测入口；本轮通过临时 Playwright Chromium 捕获桌面 / 移动截图，输出目录为 `/tmp/p0m_browser_visual_smoke`。

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

### P1-A-7 LoopContinuityReport 与视频帧门禁骨架

状态：已完成。

已落地：

- `shared/schemas/loop_continuity_report.v0.1.schema.json`
- `tools/media/build_loop_continuity_report.py`
- `tools/media/validate_loop_continuity_report.py`
- `tools/media/build_multiframe_atlas_manifest.py`：atlas item 已标注 `frame_source_kind` 与 `loop_continuity_ref`。
- `shared/schemas/media_atlas_manifest.v0.1.schema.json`：补充受限 `frame_source_kind` / `loop_continuity_ref` 字段。
- `examples/review_packs/frontend_loop_continuity_report.v0.1.json`
- `examples/review_packs/frontend_runtime_loop_continuity_report.v0.1.json`
- `tools/demo/export_evidence.py` 已纳入两份 loop continuity 摘要和验证命令。

当前结论：

- frontend mock：4 个动画序列已检查，`passed_with_warnings 4 / 4`，无 failed。
- runtime art：7 个动画序列已检查，`passed_with_warnings 7 / 7`，无 failed。
- warning 主要是 `deterministic_placeholder_not_real_video_keyframes` 和首尾帧 sha 不同；这说明现有帧序列适合 MVP 循环播放，但仍不是最终图生视频关键帧。
- 下一步真实图生视频帧接入必须复用该门禁：`video_keyframe_sequence` 进入 atlas 前必须重新跑 LoopContinuityReport、atlas contract 和前端视觉烟测。

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
- 这不是正式后台执行器；item 级队列、session dry-run 持久化、worker cache、retry / fallback 和 Campaign Router dry-run 胶水已经有最小骨架，后续仍需实现真实 provider 调度、跨请求持久化缓存、自动后台 executor 和正式 activation / promotion 执行。

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
- 它把“预生成缓冲”接到了后端 API 面，方便前端或演示读取；session 级队列、dry-run worker cache、retry / fallback 和 provider guard 已在后续 P1-B 子任务落地为骨架，真实 provider 调度、自动后台 executor、跨请求持久化缓存和正式激活仍属后续 P1-B。

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
- 它把 Generation Scheduler 从离线 evidence 推进到后端状态层；后续子任务已在 session 范围内补上 item 级队列、retry / fallback 和 dry-run worker cache，正式 provider 调度、自动后台 executor 和跨请求缓存仍未完成。

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

### P1-B-7 Generation Scheduler worker cache skeleton

状态：已完成最小骨架。

已落地：

- `generation_schedule_worker_cache` SQLite 表。
- `GET /api/sessions/{session_id}/generation-schedule/worker-cache`
- dry-run worker step 处理 `queued` 项后写入一条 review-only cache payload。
- cache summary 统计 item、status、object kind、provider call、world mutation、activation allowed 和 review required。
- session reset 会清除对应 worker cache 记录。
- `/api/sessions/{session_id}/generation-schedule/queue` 会返回 worker cache summary。
- `/api/sessions/{session_id}/generation-schedule/runs/latest` 与 `/api/sessions/{session_id}/evidence` 会返回最近 worker cache 摘要。

当前结论：

- 该层仍不调用 provider，不读取 `.env`，不保存 raw prompt 或 provider response，不生成新内容，不写世界状态。
- 该层只证明 dry-run worker 已经具备“处理队列项 -> 停在复核门 -> 禁止激活”的 session 级执行记录形态。
- 它不是正式后台生成缓存；后续真实 worker 必须继续补 provider 调用记录、产物 manifest、校验结果和显式 activation / promotion gate。

### P1-B-8 Generation Scheduler live executor guard

状态：已完成最小骨架。

已落地：

- `POST /api/sessions/{session_id}/generation-schedule/workers/live-executor-guard`
- 只处理最近一次 run 中的 `waiting_review` 队列项。
- 写入 `generation_live_executor_guard.v0.1` provider guard log 到 `provider_logs`。
- 更新 worker cache 的 `executor_guard` 和 `activation_gate.blocked_reason = explicit_provider_authorization_required`。
- `/api/sessions/{session_id}/evidence` 会返回最近 provider guard log 摘要。
- session reset 会清除 provider guard log。

当前结论：

- 该层仍不读取 `.env`，不调用 provider，不保存 raw prompt 或 provider response，不生成新内容，不写世界状态，不激活 review-only 产物。
- 它只把真实 provider 执行器前置的授权门、artifact manifest 门、校验门、人工/语义复核门和 activation / promotion gate 接入后端状态层。
- 下一步真实执行器必须基于该 guard 继续补显式授权、provider adapter、产物 manifest、validator 结果和 promotion report，不能直接把 provider 输出写入 runtime。

### P1-B-9 ProviderOutputEnvelope 安全产物信封

状态：已完成最小骨架。

已落地：

- `shared/schemas/provider_output_envelope.v0.1.schema.json`
- `examples/provider_output_envelopes/p1b_provider_output_envelope.example.json`
- `tools/dev/validate_provider_output_envelope.py`
- `docs/PROVIDER_OUTPUT_ENVELOPE_V0_1.md`
- `examples/worker_task_packs/p1b_provider_output_envelope.v0.1.json`

当前结论：

- 该层不调用真实 provider，只定义真实调用后允许保存的脱敏 envelope。
- Envelope 可以保存 provider profile、source refs、redacted request / result summary、本地 artifact refs、validation 状态和 activation gate。
- Envelope 禁止保存 prompt 正文、provider 响应正文、secret、token、full trace、raw JSON 或 runtime-ready 声明。
- 后续真实 executor 必须先生成并校验 ProviderOutputEnvelope，再进入 media / semantic gate 和 promotion report。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_provider_output_envelope.v0.1.json
python3 tools/dev/validate_provider_output_envelope.py examples/provider_output_envelopes/p1b_provider_output_envelope.example.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_provider_envelope python3 -m py_compile tools/dev/validate_provider_output_envelope.py
python3 -m json.tool shared/schemas/provider_output_envelope.v0.1.schema.json >/tmp/provider_output_envelope.schema.pretty.json
python3 tools/demo/export_evidence.py --output-dir /tmp/provider_output_envelope_evidence
git diff --check
```

### P1-B-10 ProviderArtifactStagingManifest 审查暂存清单

状态：已完成最小骨架。

已落地：

- `shared/schemas/provider_artifact_staging_manifest.v0.1.schema.json`
- `examples/provider_artifact_staging/p1b_provider_artifact_staging.example.json`
- `examples/provider_artifact_staging/p1b_provider_artifact_staging.source_envelope.json`
- `examples/provider_artifact_staging/artifacts/p1b_stage05_map_visual_candidate.summary.json`
- `tools/dev/validate_provider_artifact_staging_manifest.py`
- `docs/PROVIDER_ARTIFACT_STAGING_V0_1.md`
- `examples/worker_task_packs/p1b_provider_artifact_staging.v0.1.json`

当前结论：

- 该层不调用 provider，只登记 ProviderOutputEnvelope 之后的本地候选 artifact refs。
- staging manifest 必须保持 review-only、internal evidence、非玩家可见、非 runtime 激活、非世界状态修改。
- staged artifact 必须是本地路径，不能是 provider 临时 URL、data URI 或 runtime package。
- 后续真实 executor 必须先生成并校验 ProviderOutputEnvelope，再写 ProviderArtifactStagingManifest，然后进入 media / semantic / human review 和 promotion report。
- demo evidence exporter 已能展示 staging manifest、source envelope、暂存 artifact 数量、gate 状态和 promotion 阻断摘要。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_provider_artifact_staging.v0.1.json
python3 tools/dev/validate_provider_artifact_staging_manifest.py examples/provider_artifact_staging/p1b_provider_artifact_staging.example.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_provider_artifact_staging python3 -m py_compile tools/dev/validate_provider_artifact_staging_manifest.py
python3 -m json.tool shared/schemas/provider_artifact_staging_manifest.v0.1.schema.json >/tmp/provider_artifact_staging.schema.pretty.json
python3 tools/demo/export_evidence.py --output-dir /tmp/provider_artifact_staging_evidence
git diff --check
```

### P1-B-11 ProviderArtifactStaging demo evidence 接线

状态：已完成最小骨架。

已落地：

- `tools/demo/export_evidence.py` 已增加 ProviderArtifactStagingManifest 的 PATHS、source file 指纹、validation command、机器可读摘要、summary.md 摘要和 index.html 快速展示。
- `examples/worker_task_packs/p1b_provider_artifact_staging_evidence.v0.1.json`

当前结论：

- evidence 只展示 staging 摘要、计数、路径、gate 状态和 promotion 阻断。
- evidence 不输出 prompt 正文、provider 响应正文、secret、token、临时 URL 或 runtime-ready 声明。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_provider_artifact_staging_evidence.v0.1.json
python3 tools/dev/validate_provider_artifact_staging_manifest.py examples/provider_artifact_staging/p1b_provider_artifact_staging.example.json
python3 tools/demo/export_evidence.py --output-dir /tmp/provider_artifact_staging_evidence_connected
git diff --check
```

### P1-B-12 Provider artifact ledger 后端状态层

状态：已完成最小骨架。

已落地：

- `generation_artifact_ledger` SQLite 表，所有记录按 `session_id` 隔离，session reset 会清理。
- `GET /api/sessions/{session_id}/generation-schedule/artifact-ledger`
- `POST /api/sessions/{session_id}/generation-schedule/workers/stage-provider-artifacts`
- `backend/app/services/generation_scheduler_service.py` 中的 fixture-backed envelope / staging / promotion report 校验、摘要、upsert 和 evidence 聚合。
- `examples/worker_task_packs/p1b_provider_artifact_ledger_backend.v0.1.json`

当前结论：

- 该层只把已校验的 ProviderOutputEnvelope / ProviderArtifactStagingManifest / ProviderArtifactPromotionReport 摘要登记到 session 台账。
- worker API 自身不调用 provider、不读取 `.env`、不写世界状态、不激活 runtime。
- 台账会记录 source 中“已发生过的 provider 调用摘要”，但 `provider_call_count_by_this_request` 始终为 0，避免把台账写入伪装成真实执行器。
- `/api/sessions/{session_id}/evidence` 会返回 `generation_scheduler.latest_artifact_ledger`，供 Studio / evidence 页面使用。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_provider_artifact_ledger_backend.v0.1.json
python3 -m compileall backend
uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py backend/tests/test_sessions.py
python3 tools/demo/export_evidence.py --output-dir /tmp/provider_artifact_ledger_backend_evidence
git diff --check
```

### P1-B-13 ProviderArtifactPromotionReport 显式晋升报告

状态：已完成最小骨架。

已落地：

- `shared/schemas/provider_artifact_promotion_report.v0.1.schema.json`
- `examples/provider_artifact_staging/p1b_provider_artifact_promotion_report.example.json`
- `tools/dev/validate_provider_artifact_promotion_report.py`
- `docs/PROVIDER_ARTIFACT_PROMOTION_REPORT_V0_1.md`
- `examples/worker_task_packs/p1b_provider_artifact_promotion_report.v0.1.json`

当前结论：

- 该层只表达 staging 之后的显式晋升/阻断结论，不执行 provider、不读取 `.env`、不修改 runtime package、published media 或世界状态。
- 当前示例会因 `media_gate`、`semantic_gate`、`human_review` 仍为 `not_run` 而阻断晋升。
- 后续如果报告批准候选继续前进，也只是允许后续构建器生成 runtime package / WorldStateDeltaTransaction；真正写入仍必须由对应构建器和 validator 完成。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_provider_artifact_promotion_report.v0.1.json
python3 tools/dev/validate_provider_artifact_promotion_report.py examples/provider_artifact_staging/p1b_provider_artifact_promotion_report.example.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_provider_artifact_promotion python3 -m py_compile tools/dev/validate_provider_artifact_promotion_report.py tools/demo/export_evidence.py
python3 -m json.tool shared/schemas/provider_artifact_promotion_report.v0.1.schema.json >/tmp/provider_artifact_promotion_report.schema.pretty.json
python3 tools/demo/export_evidence.py --output-dir /tmp/provider_artifact_promotion_report_evidence
git diff --check
```

### P1-B-14 ProviderArtifactPromotionReport 后端 ledger 接线

状态：已完成最小骨架。

已落地：

- `POST /api/sessions/{session_id}/generation-schedule/workers/stage-provider-artifacts` 会额外校验并登记 `ProviderArtifactPromotionReport v0.1` 摘要。
- `GET /api/sessions/{session_id}/generation-schedule/artifact-ledger` 会返回三类记录：provider output envelope、provider artifact staging manifest、provider artifact promotion report。
- `backend/tests/test_frontend_mock_api.py` 已覆盖三类 ledger entry、promotion 阻断状态、reset 清理和 evidence 聚合。
- `examples/worker_task_packs/p1b_provider_artifact_promotion_ledger.v0.1.json`

当前结论：

- 当前 promotion report 是 `blocked_review_required`，因此 ledger 中 `promotion_allowed_count` 仍为 0。
- 该层只登记摘要，不调用 provider、不读取 `.env`、不写世界状态、不修改 runtime。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_provider_artifact_promotion_ledger.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_provider_artifact_promotion_ledger python3 -m compileall backend
uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py backend/tests/test_sessions.py
python3 tools/demo/export_evidence.py --output-dir /tmp/provider_artifact_promotion_ledger_evidence
git diff --check
```

### P1-B-15 GenerationExecutorRunRequest 执行请求包边界

状态：已完成最小骨架。

已落地：

- `shared/schemas/generation_executor_run_request.v0.1.schema.json`
- `examples/generation_executor_requests/p1b_generation_executor_run_request.example.json`
- `tools/dev/validate_generation_executor_run_request.py`
- `POST /api/sessions/{session_id}/generation-schedule/workers/prepare-executor-request`
- `backend/app/services/generation_scheduler_service.py` 中从 `waiting_review` 队列项和 live executor guard 生成执行请求包的逻辑。
- `generation_artifact_ledger` 现在可登记 `generation_executor_run_request` 摘要。
- `tools/demo/export_evidence.py` 已纳入 GenerationExecutorRunRequest 的 source file、validation command 和 evidence 摘要。
- `examples/worker_task_packs/p1b_generation_executor_request.v0.1.json`

当前结论：

- 该层位于 live executor guard 之后、真实 provider adapter 之前。
- 请求包只保存 source refs、input refs、context refs、attempt budget、provider mode/profile、授权门和必过 gates。
- 该层不调用 provider、不读取 `.env`、不保存 prompt 正文或 provider 响应正文、不写世界状态、不激活 runtime。
- 如果队列项尚未经过 live executor guard，后端会以 409 阻断 `prepare-executor-request`。
- 后续真实执行器必须消费该请求包，再在显式授权后生成 `ProviderOutputEnvelope`、`ProviderArtifactStagingManifest` 和 `ProviderArtifactPromotionReport`，不能直接把 provider 输出写入 runtime 或 WorldStateDelta。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_generation_executor_request.v0.1.json
python3 tools/dev/validate_generation_executor_run_request.py examples/generation_executor_requests/p1b_generation_executor_run_request.example.json
python3 -m json.tool shared/schemas/generation_executor_run_request.v0.1.schema.json
python3 -m py_compile tools/dev/validate_generation_executor_run_request.py tools/demo/export_evidence.py
python3 -m compileall backend
pytest backend/tests/test_frontend_mock_api.py backend/tests/test_sessions.py
python3 tools/demo/export_evidence.py --output-dir /tmp/generation_executor_request_evidence
git diff --check
```

### P1-B-16 ProviderArtifactStaging 依赖 executor request

状态：已完成最小骨架。

已落地：

- `POST /api/sessions/{session_id}/generation-schedule/workers/stage-provider-artifacts` 现在必须先看到 latest run 已登记 `generation_executor_run_request`。
- 若缺少 executor request，接口返回 409，不会登记 ProviderOutputEnvelope / ProviderArtifactStagingManifest / ProviderArtifactPromotionReport。
- `stage-provider-artifacts` 响应会返回 `worker_step.upstream_request_id` 和 `generation_executor_run_request` 摘要，供 evidence / Studio 串联。
- `backend/tests/test_frontend_mock_api.py` 已覆盖提前 stage 的 409，以及 dry-run worker -> live executor guard -> prepare executor request -> stage provider artifacts 的完整顺序。
- `examples/worker_task_packs/p1b_provider_staging_requires_executor_request.v0.1.json`

当前结论：

- Provider artifact ledger 不能再绕过 dry-run worker、live executor guard 和 GenerationExecutorRunRequest。
- 该层仍不调用 provider、不读取 `.env`、不保存 prompt 正文或 provider 响应正文、不写世界状态、不激活 runtime。
- 由于现有 provider fixture 仍是早期 stage05 样例，当前只要求 latest run 存在 executor request，不强制 fixture envelope 的 schedule item 与 executor request 完全相同；后续真实 provider adapter 接入时应把 source schedule item 精确绑定。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_provider_staging_requires_executor_request.v0.1.json
python3 -m compileall backend
pytest backend/tests/test_frontend_mock_api.py backend/tests/test_sessions.py
python3 tools/demo/export_evidence.py --output-dir /tmp/provider_staging_requires_executor_request_evidence
git diff --check
```

### P1-B-17 Provider fixture source 与 scheduler/executor request 对齐

状态：已完成最小骨架。

已落地：

- `GenerationScheduleQueueTransitionRequest` 增加可选 `schedule_item_id`。
- `dry-run-step`、`live-executor-guard` 和 `prepare-executor-request` 可定向处理指定队列项；若目标项状态不匹配则返回 409。
- provider artifact source envelope 已从早期 `schedule_map_visual_reference_old_signal_tower` 对齐到当前计划项 `sched_next_map_visual_prefetch`，object kind/ref 对齐为 `map_visual_prefetch` / `map_compile_package:old_signal_tower_pressure`。
- `stage-provider-artifacts` 现在要求 latest run 中存在同 `ProviderOutputEnvelope.source.schedule_item_id` 的 `generation_executor_run_request`，不再接受任意 executor request。
- 测试覆盖了错误调度项 request 不能 stage、正确调度项 request 可以 stage，以及 provider envelope source schedule item 对齐。
- `examples/worker_task_packs/p1b_provider_source_alignment.v0.1.json`

当前结论：

- Provider artifact staging 已从“session 内存在任意 executor request”收紧为“同 schedule item 的 executor request”。
- 这仍是 fixture-backed / review-only，不调用 provider、不读取 `.env`、不保存 prompt 正文或 provider 响应正文、不写世界状态、不激活 runtime。
- 后续真实 provider adapter 接入时，应继续把 ProviderOutputEnvelope.source.run_id / schedule_item_id / guard_id / executor request id 做强绑定，并把显式授权记录纳入同一链。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_provider_source_alignment.v0.1.json
python3 tools/dev/validate_provider_output_envelope.py examples/provider_artifact_staging/p1b_provider_artifact_staging.source_envelope.json
python3 tools/dev/validate_provider_artifact_staging_manifest.py examples/provider_artifact_staging/p1b_provider_artifact_staging.example.json
python3 tools/dev/validate_provider_artifact_promotion_report.py examples/provider_artifact_staging/p1b_provider_artifact_promotion_report.example.json
python3 -m compileall backend
pytest backend/tests/test_frontend_mock_api.py backend/tests/test_sessions.py
python3 tools/demo/export_evidence.py --output-dir /tmp/provider_source_alignment_evidence
git diff --check
```

### P1-B-18 ProviderExecutionAuthorization 显式授权记录

状态：已完成最小骨架。

已落地：

- `shared/schemas/provider_execution_authorization.v0.1.schema.json`
- `examples/provider_authorizations/p1b_provider_execution_authorization.example.json`
- `tools/dev/validate_provider_execution_authorization.py`
- `POST /api/sessions/{session_id}/generation-schedule/workers/grant-provider-authorization`
- `GenerationScheduleQueueTransitionRequest` 增加可选 `authorization_ref`。
- `stage-provider-artifacts` 现在要求 latest run 中存在同 `ProviderOutputEnvelope.source.schedule_item_id` 的 `generation_executor_run_request`，且存在同 `ProviderOutputEnvelope.provider_call.authorization_ref` 的 `provider_execution_authorization`。
- `stage-provider-artifacts` 响应会返回 `worker_step.authorization_ref`、`provider_execution_authorization` 摘要和带 `authorization_ref` 的 provider call 摘要。
- `generation_artifact_ledger` 现在可登记 `provider_execution_authorization` 摘要。
- `tools/demo/export_evidence.py` 已纳入 ProviderExecutionAuthorization 的 source file、validation command 和 evidence 摘要。
- `examples/worker_task_packs/p1b_provider_authorization_record.v0.1.json`

当前结论：

- ProviderExecutionAuthorization 位于 GenerationExecutorRunRequest 之后、真实 provider adapter 之前。
- 该层只记录 `provider_adapter_execution_only` 的显式授权，不调用 provider、不读取 `.env`、不保存 prompt 正文或 provider 响应正文、不写世界状态、不激活 runtime。
- ProviderOutputEnvelope / staging / promotion report 不能再只依赖 executor request；必须能追到同 schedule item 和同 authorization ref 的授权记录。
- 该层仍然不是 runtime activation gate，也不是 WorldStateDeltaTransaction 提交授权。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_provider_authorization_record.v0.1.json
python3 tools/dev/validate_provider_execution_authorization.py examples/provider_authorizations/p1b_provider_execution_authorization.example.json
python3 tools/dev/validate_provider_output_envelope.py examples/provider_artifact_staging/p1b_provider_artifact_staging.source_envelope.json
python3 -m json.tool shared/schemas/provider_execution_authorization.v0.1.schema.json
python3 -m py_compile tools/dev/validate_provider_execution_authorization.py tools/demo/export_evidence.py
python3 -m compileall backend
pytest backend/tests/test_frontend_mock_api.py backend/tests/test_sessions.py
python3 tools/demo/export_evidence.py --output-dir /tmp/provider_authorization_record_evidence
git diff --check
```

### P1-B-19 ProviderAdapterExecutionReceipt 执行边界回执

状态：已完成最小骨架。

已落地：

- `shared/schemas/provider_adapter_execution_receipt.v0.1.schema.json`
- `examples/provider_adapter_executions/p1b_provider_adapter_execution_receipt.example.json`
- `tools/dev/validate_provider_adapter_execution_receipt.py`
- `POST /api/sessions/{session_id}/generation-schedule/workers/run-provider-adapter-fixture`
- `stage-provider-artifacts` 现在要求 latest run 中存在同 `ProviderOutputEnvelope.source.schedule_item_id` 的 `generation_executor_run_request`，同 `ProviderOutputEnvelope.provider_call.authorization_ref` 的 `provider_execution_authorization`，以及同 schedule item / authorization ref 的 `provider_adapter_execution_receipt`。
- `stage-provider-artifacts` 响应会返回 `provider_adapter_execution_receipt` 摘要。
- `generation_artifact_ledger` 现在可登记 `provider_adapter_execution_receipt` 摘要。
- `tools/demo/export_evidence.py` 已纳入 ProviderAdapterExecutionReceipt 的 source file、validation command 和 evidence 摘要。
- `examples/worker_task_packs/p1b_provider_adapter_execution_boundary.v0.1.json`

当前结论：

- ProviderAdapterExecutionReceipt 位于 ProviderExecutionAuthorization 之后、ProviderOutputEnvelope 之前。
- 当前后端只实现 `fixture_backed_no_provider_call` 模式：不读取 `.env`、不调用 provider、不保存 prompt 正文或 provider 响应正文、不写世界状态、不激活 runtime。
- 后续真实 provider adapter 可使用同一 schema 的 `live_redacted_provider_call` 模式，但仍只能向 ProviderOutputEnvelope 输出脱敏摘要、digest 和本地 artifact refs。
- ProviderOutputEnvelope / staging / promotion report 不能再只依赖授权记录；必须能追到同 schedule item 和同 authorization ref 的 adapter receipt。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_provider_adapter_execution_boundary.v0.1.json
python3 tools/dev/validate_provider_adapter_execution_receipt.py examples/provider_adapter_executions/p1b_provider_adapter_execution_receipt.example.json
python3 tools/dev/validate_provider_output_envelope.py examples/provider_artifact_staging/p1b_provider_artifact_staging.source_envelope.json
python3 -m json.tool shared/schemas/provider_adapter_execution_receipt.v0.1.schema.json
python3 -m py_compile tools/dev/validate_provider_adapter_execution_receipt.py tools/demo/export_evidence.py
python3 -m compileall backend
pytest backend/tests/test_frontend_mock_api.py backend/tests/test_sessions.py
python3 tools/demo/export_evidence.py --output-dir /tmp/provider_adapter_execution_boundary_evidence
git diff --check
```

### P1-B-20 Provider adapter runner 脱敏执行工具

状态：已完成最小骨架。

已落地：

- `tools/provider_adapter/run_provider_adapter.py`
- `examples/provider_adapter_runs/p1b_provider_adapter_runner.executor_request.json`
- `examples/provider_adapter_runs/p1b_provider_adapter_runner.receipt.json`
- `examples/provider_adapter_runs/p1b_provider_adapter_runner.envelope.json`
- `examples/worker_task_packs/p1b_provider_adapter_runner.v0.1.json`
- `tools/demo/export_evidence.py` 已纳入 runner dry-run 命令、静态输出校验和 `provider_adapter_runner` evidence 摘要。

当前结论：

- Provider adapter runner 是工具层执行入口，不是后端自动后台执行器。
- 默认 `fixture` 模式是 deterministic dry-run：不读取 `.env`、不调用 provider、不创建候选 artifact，只输出可校验的 `ProviderAdapterExecutionReceipt` 和 `ProviderOutputEnvelope`。
- 显式 `--mode llm_text --live` 才允许调用 `tools/llm/adapter.py` 中的 LLM profile；live 输出仍只能保存 digest、计数和 redacted summary refs，不保存 prompt 正文或 provider 响应正文。
- 图片 provider adapter 已由 P1-B-21 单独推进；视频 provider adapter、媒体后处理自动串接和 media gate 仍应后续单独推进。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_provider_adapter_runner.v0.1.json
python3 tools/dev/validate_generation_executor_run_request.py examples/provider_adapter_runs/p1b_provider_adapter_runner.executor_request.json
python3 tools/provider_adapter/run_provider_adapter.py --executor-request examples/provider_adapter_runs/p1b_provider_adapter_runner.executor_request.json --authorization examples/provider_authorizations/p1b_provider_execution_authorization.example.json --receipt-output /tmp/p1b_provider_adapter_runner.receipt.json --envelope-output /tmp/p1b_provider_adapter_runner.envelope.json --created-at 2026-07-03T00:00:00Z
python3 tools/dev/validate_provider_adapter_execution_receipt.py examples/provider_adapter_runs/p1b_provider_adapter_runner.receipt.json
python3 tools/dev/validate_provider_output_envelope.py examples/provider_adapter_runs/p1b_provider_adapter_runner.envelope.json
python3 -m py_compile tools/provider_adapter/run_provider_adapter.py tools/demo/export_evidence.py
python3 tools/demo/export_evidence.py --output-dir /tmp/provider_adapter_runner_evidence
git diff --check
```

### P1-B-21 Provider adapter image runner 图片候选执行边界

状态：已完成最小骨架。

目标：

```text
在 ProviderExecutionAuthorization 之后，为 image provider 增加显式 live 工具层边界：调用图像 provider、下载成本地 review-only artifact ref，并只输出 ProviderAdapterExecutionReceipt / ProviderOutputEnvelope。
```

已落地：

- `tools/provider_adapter/run_provider_adapter.py`：新增 `--mode image --live`、`--image-profile`、`--size`；默认 fixture 行为保持不联网、不读取 `.env`。
- `examples/provider_adapter_runs/p1b_provider_adapter_image_runner.executor_request.json`
- `examples/provider_authorizations/p1b_provider_execution_authorization_image.example.json`
- `examples/provider_adapter_runs/p1b_provider_adapter_image_runner.receipt.json`
- `examples/provider_adapter_runs/p1b_provider_adapter_image_runner.envelope.json`
- `examples/worker_task_packs/p1b_provider_adapter_image_runner.v0.1.json`
- `tools/demo/export_evidence.py` 已纳入 image runner request / authorization / dry-run / receipt / envelope 校验和 `provider_adapter_image_runner` evidence 摘要。

当前结论：

- 默认 `fixture` dry-run 仍不读取 `.env`、不调用 provider、不创建候选 artifact。
- 显式 `--mode image --live` 才允许调用 `tools/media/image_provider.py` 中的 image profile。
- live image 只允许保存 prompt digest、image digest、byte size、本地 artifact ref 和 redacted summary；不得保存 prompt 正文、provider 原始响应、临时 URL 或 secret。
- image runner 产物仍是 review-only；后续必须进入 ProviderArtifactStagingManifest、media gate、semantic gate、human review 和 ProviderArtifactPromotionReport，不能直接进入 runtime package、published media 或世界状态。
- 视频 provider adapter、图生视频帧、后处理自动串接、media gate 自动执行和后端自动后台 executor 仍未完成。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_provider_adapter_image_runner.v0.1.json
python3 tools/dev/validate_generation_executor_run_request.py examples/provider_adapter_runs/p1b_provider_adapter_image_runner.executor_request.json
python3 tools/dev/validate_provider_execution_authorization.py examples/provider_authorizations/p1b_provider_execution_authorization_image.example.json
python3 tools/provider_adapter/run_provider_adapter.py --executor-request examples/provider_adapter_runs/p1b_provider_adapter_image_runner.executor_request.json --authorization examples/provider_authorizations/p1b_provider_execution_authorization_image.example.json --receipt-output /tmp/p1b_provider_adapter_image_runner.receipt.json --envelope-output /tmp/p1b_provider_adapter_image_runner.envelope.json --created-at 2026-07-03T00:00:00Z
python3 tools/dev/validate_provider_adapter_execution_receipt.py examples/provider_adapter_runs/p1b_provider_adapter_image_runner.receipt.json
python3 tools/dev/validate_provider_output_envelope.py examples/provider_adapter_runs/p1b_provider_adapter_image_runner.envelope.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_provider_image_runner python3 -m py_compile tools/provider_adapter/run_provider_adapter.py tools/demo/export_evidence.py tools/media/image_provider.py
python3 tools/demo/export_evidence.py --output-dir /tmp/provider_adapter_image_runner_evidence
git diff --check
```

### P1-B-22 Provider image artifact staging 失败闸门

状态：已完成最小闭环。

目标：

```text
把 image ProviderOutputEnvelope 接到 ProviderArtifactStagingManifest 与 ProviderArtifactPromotionReport，证明已经下载到本地的图片候选仍会因 media / semantic gate 失败而被阻断，不能直接进入 MapRuntimePackage、published media、runtime package 或世界状态。
```

已落地：

- `examples/provider_artifact_staging/p1b_provider_image_artifact_staging.source_envelope.json`
- `examples/provider_artifact_staging/p1b_provider_image_artifact_staging.example.json`
- `examples/provider_artifact_staging/p1b_provider_image_artifact_promotion_report.example.json`
- `examples/worker_task_packs/p1b_provider_image_artifact_staging.v0.1.json`
- `tools/demo/export_evidence.py` 已纳入 image staging / image promotion report 校验与 evidence 摘要。
- `docs/PROVIDER_ARTIFACT_STAGING_V0_1.md`、`docs/PROVIDER_ARTIFACT_PROMOTION_REPORT_V0_1.md`、`docs/GENERATION_SCHEDULER_V0_1.md`、`docs/CURRENT_ARCHITECTURE_INDEX.md` 已同步该失败门语义。

当前结论：

- source envelope 和 local PNG ref 可以合法保存为 review-only evidence。
- 该图片候选被明确标记为 `validation_failed` / `blocked_validation_failed`。
- 差图、控制图残留图、路径 / 塔位 / 目标语义不一致的生成图只能作为负样本和下一轮重生 / paintover 输入。
- 后续仍需要 MapRuntimePackage 驱动的控制图、reference-image provider、局部清理或人工 paintover，再重新走 media / semantic / human review / promotion gates。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_provider_image_artifact_staging.v0.1.json
python3 tools/dev/validate_provider_output_envelope.py examples/provider_artifact_staging/p1b_provider_image_artifact_staging.source_envelope.json
python3 tools/dev/validate_provider_artifact_staging_manifest.py examples/provider_artifact_staging/p1b_provider_image_artifact_staging.example.json
python3 tools/dev/validate_provider_artifact_promotion_report.py examples/provider_artifact_staging/p1b_provider_image_artifact_promotion_report.example.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_provider_image_staging python3 -m py_compile tools/demo/export_evidence.py
python3 tools/demo/export_evidence.py --output-dir /tmp/provider_image_artifact_staging_evidence
git diff --check
```

### P1-B-23 ProviderArtifactPromotionReport 失败决策校验加严

状态：已完成最小闭环。

目标：

```text
把 blocked_validation_failed 从文档约定升级为 validator 约束：只有至少一个 required gate 的 status=failed 时，ProviderArtifactPromotionReport 才能使用该决策。
```

已落地：

- `tools/dev/validate_provider_artifact_promotion_report.py`：新增 `blocked_validation_failed` 必须对应至少一个 failed required gate 的校验。
- `tools/dev/check_provider_artifact_promotion_report_negative_fixture.py`
- `examples/provider_artifact_staging/p1b_provider_artifact_promotion_report.invalid_blocked_validation_without_failed_gate.json`
- `examples/worker_task_packs/p1b_provider_artifact_promotion_validator_hardening.v0.1.json`
- `tools/demo/export_evidence.py` 已把负例检查纳入静态校验。
- `docs/PROVIDER_ARTIFACT_PROMOTION_REPORT_V0_1.md` 和 `docs/CURRENT_ARCHITECTURE_INDEX.md` 已同步该规则。

当前结论：

- `blocked_review_required` 用于“还没通过 / 还没审查”的阻断。
- `blocked_validation_failed` 用于“至少一个 required gate 已明确失败”的阻断。
- 这防止 report 在没有 failed gate 的情况下伪装成验证失败，也让 image candidate 负样本闭环成为可执行约束。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_provider_artifact_promotion_validator_hardening.v0.1.json
python3 tools/dev/validate_provider_artifact_promotion_report.py examples/provider_artifact_staging/p1b_provider_artifact_promotion_report.example.json
python3 tools/dev/validate_provider_artifact_promotion_report.py examples/provider_artifact_staging/p1b_provider_image_artifact_promotion_report.example.json
python3 tools/dev/check_provider_artifact_promotion_report_negative_fixture.py examples/provider_artifact_staging/p1b_provider_artifact_promotion_report.invalid_blocked_validation_without_failed_gate.json --expected-error "blocked_validation_failed requires at least one required gate failed"
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_promo_validator_hardening python3 -m py_compile tools/dev/validate_provider_artifact_promotion_report.py tools/dev/check_provider_artifact_promotion_report_negative_fixture.py tools/demo/export_evidence.py
python3 tools/demo/export_evidence.py --output-dir /tmp/provider_artifact_promotion_validator_hardening_evidence
git diff --check
```

### P1-B-24 Provider image artifact 失败门后端 ledger profile

状态：已完成最小闭环。

目标：

```text
扩展 fixture-backed stage-provider-artifacts worker，让它在默认行为不变的前提下支持 artifact_profile=image_failure，把 image ProviderOutputEnvelope / ProviderArtifactStagingManifest / ProviderArtifactPromotionReport 登记到同一 generation_artifact_ledger。
```

已落地：

- `backend/app/models.py`：`GenerationScheduleQueueTransitionRequest` 显式支持 `authorization_ref` 和 `artifact_profile`。
- `backend/app/services/generation_scheduler_service.py`：`stage_provider_artifacts_fixture` 支持 `default` 与 `image_failure` 两个 fixture profile。
- `backend/tests/test_frontend_mock_api.py`：覆盖 image failure profile、未知 profile 409、默认 profile 兼容。
- `examples/worker_task_packs/p1b_provider_image_artifact_ledger_profile.v0.1.json`
- `docs/CURRENT_ARCHITECTURE_INDEX.md` 和 `docs/GENERATION_SCHEDULER_V0_1.md` 已同步该后端 ledger profile。

当前结论：

- 默认 stage worker 仍登记通用 `blocked_review_required` 示例。
- `artifact_profile=image_failure` 会登记 `validation_failed` / `blocked_validation_failed` 图片候选负样本。
- image failure profile 仍然是 Studio / evidence 用后端状态层：不调用 provider、不读取 `.env`、不写世界状态、不发布媒体、不激活 runtime。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_provider_image_artifact_ledger_profile.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_provider_image_staging_ledger python3 -m compileall backend
uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py -q
git diff --check
```

### P1-B-25 Generation Scheduler fixture executor chain

状态：已完成最小骨架。

目标：

```text
新增 review-only 的 executor chain API，把现有 dry-run worker、live executor guard、executor request、provider authorization、fixture adapter receipt 和 provider artifact staging 串成一次可审计调用，为后续真实后台执行器提供稳定壳。
```

已落地：

- `POST /api/sessions/{session_id}/generation-schedule/workers/run-fixture-executor-chain`
- 缺少最新 scheduler run 时自动创建 session 级 run。
- 默认从所选 `artifact_profile` 的 ProviderOutputEnvelope fixture 反推 `schedule_item_id` 和 `authorization_ref`，避免 artifact ledger 挂到错误调度项下。
- 支持 `artifact_profile=default` 与 `artifact_profile=image_failure`。
- 显式传入不匹配的 `schedule_item_id` 或 `authorization_ref` 时返回 409。
- 返回 `executor_chain`、各阶段 `worker_step`、executor request、authorization、adapter receipt、staging、promotion report 与 ledger 汇总。

当前结论：

- 这只是正式后台执行器的 fixture-backed 编排壳，不是真 provider 调度器。
- 仍然不调用 provider、不读取 `.env`、不保存 prompt / provider 正文、不写世界状态、不激活 runtime。
- 后续真实 executor 可以替换 provider adapter 步骤，但必须保留同一授权链、产物信封、staging、promotion 与 activation gate。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_generation_executor_chain.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_generation_executor_chain python3 -m compileall backend
uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py -q
git diff --check
```

### P1-B-26 Provider adapter runner 后端 bridge

状态：已完成最小骨架。

目标：

```text
在后端 worker API 中复用工具层 provider adapter runner 的 dry-run artifact builder，把 runner 形态的 ProviderAdapterExecutionReceipt 与 ProviderOutputEnvelope 登记到 generation_artifact_ledger，为后续 live provider bridge 做安全落点。
```

已落地：

- `POST /api/sessions/{session_id}/generation-schedule/workers/run-provider-adapter-runner-fixture`
- 该入口要求已有匹配的 `GenerationExecutorRunRequest` 与 `ProviderExecutionAuthorization`。
- 后端从 ledger compact 还原 runner 校验所需的最小安全 payload，不保存 prompt / provider 正文。
- 复用 `tools/provider_adapter/run_provider_adapter.py` 的 dry-run artifact builder，生成并校验 runner 形态 receipt/envelope。
- receipt 与 envelope 均登记到 `generation_artifact_ledger`。

当前结论：

- 这是 runner bridge 的 dry-run 后端落账，不是真 live provider 调度。
- 不读取 `.env`、不调用 provider、不 staging、不 promotion、不 complete queue item、不写世界状态、不激活 runtime。
- 后续 live bridge 可以替换 runner 模式，但必须保留 executor request、authorization、redacted envelope、staging、promotion 和 activation gate。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_provider_adapter_runner_bridge.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_provider_adapter_runner_bridge python3 -m compileall backend
uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py -q
git diff --check
```

### P1-B-27 Provider adapter runner 输出导入

状态：已完成最小骨架。

目标：

```text
允许开发期 / 外部工具先生成本地 ProviderAdapterExecutionReceipt 与 ProviderOutputEnvelope 文件，再由后端 worker API 校验并导入 generation_artifact_ledger。
```

已落地：

- `POST /api/sessions/{session_id}/generation-schedule/workers/import-provider-adapter-runner-output`
- 请求体支持 `receipt_path` 与 `envelope_path`。
- 只接受仓库内或 `/tmp` 下的本地 JSON 文件，禁止 `.env`。
- 导入前检查敏感键：`raw_prompt`、`provider_response`、`provider_body`、`secret`、`api_key` 等。
- 导入前重新校验 `ProviderAdapterExecutionReceipt` 与 `ProviderOutputEnvelope`。
- 导入前要求已存在匹配的 `GenerationExecutorRunRequest` 与 `ProviderExecutionAuthorization`。
- 导入前检查 receipt/envelope/source 与 ledger 授权链一致。

当前结论：

- 这是外部 runner / 人工生成产物的后端验收入账路径，不是真 provider 调用入口。
- 导入本身不读取 `.env`、不调用 provider、不 staging、不 promotion、不 complete queue item、不写世界状态、不激活 runtime。
- 后续 live provider smoke 可以先由工具层 runner 生成本地 receipt/envelope，再通过该接口导入并继续走 staging / promotion gate。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_provider_adapter_runner_output_import.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_provider_adapter_output_import python3 -m compileall backend
uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py -q
git diff --check
```

### P1-B-28 Provider artifact review 输出导入

状态：已完成最小骨架。

目标：

```text
允许开发期 / 外部工具先生成本地 ProviderArtifactStagingManifest 与 ProviderArtifactPromotionReport 文件，再由后端 worker API 校验并导入 generation_artifact_ledger。
```

已落地：

- `POST /api/sessions/{session_id}/generation-schedule/workers/import-provider-artifact-review-output`
- 请求体支持 `staging_path` 与 `promotion_report_path`。
- 只接受仓库内或 `/tmp` 下的本地 JSON 文件，禁止 `.env`。
- 导入前检查敏感键：`raw_prompt`、`provider_response`、`provider_body`、`secret`、`api_key` 等。
- 导入前重新校验 `ProviderArtifactStagingManifest` 与 `ProviderArtifactPromotionReport`。
- 导入前要求同一 session / latest run / schedule item 已存在匹配 `source_envelope_id` 的 `ProviderOutputEnvelope` ledger entry。
- 导入前检查 promotion report 的 `source_staging_ref` 指向本次导入的 staging 文件。
- 导入前检查 promotion report 的 `source_staging_id` 与 staging `manifest_id` 一致。
- 导入前检查 `reviewed_artifacts[].staged_artifact_id` 均能在 staging `staged_artifacts[].artifact_id` 中找到。

当前结论：

- 这是外部 media gate / semantic gate / 人工审查产物的后端验收入账路径，不是真 provider 调用入口。
- 导入本身不读取 `.env`、不调用 provider、不发布素材、不 complete queue item、不写世界状态、不激活 runtime。
- 后续 live provider smoke 可以先由工具层 runner 生成本地 receipt/envelope，再由外部工具生成 staging/promotion review 文件，最后通过该接口导入并等待显式 promotion / runtime package / world transaction builder。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_provider_artifact_review_output_import.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_provider_artifact_review_output_import python3 -m compileall backend
uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py -q
git diff --check
```

### P1-B-29 Generation Scheduler review-only dispatcher step

状态：已完成最小骨架。

目标：

```text
新增 review-only dispatcher API，把一个 queued 调度项按既有 guard / request / authorization / runner fixture 链推进到 ProviderAdapterExecutionReceipt 与 ProviderOutputEnvelope ledger 边界，但不进入 staging、promotion、队列完成或 runtime 激活。
```

已落地：

- `POST /api/sessions/{session_id}/generation-schedule/workers/run-review-only-dispatcher-step`
- 缺少最新 scheduler run 时自动创建 session 级 run。
- 支持显式 `schedule_item_id`；未提供时处理下一个 `queued` 项。
- 固定复用 `dry-run-step -> live-executor-guard -> prepare-executor-request -> grant-provider-authorization -> run-provider-adapter-runner-fixture`。
- 返回统一 `worker_step`、各阶段 `steps`、queue item、worker cache、guard log、executor request、authorization、runner receipt、ProviderOutputEnvelope 和 ledger 摘要。
- 队列项保持 `waiting_review`，ledger 只包含 executor request、authorization、adapter receipt、ProviderOutputEnvelope 四类。

当前结论：

- 这是正式后台 dispatcher / executor 前的 review-only 编排壳，不是真 provider 调度器。
- 它不读取 `.env`、不调用 provider、不 staging、不 promotion、不 complete queue item、不写世界状态、不激活 runtime。
- 后续真实后台执行器可以替换 runner fixture 步骤，但必须保留同一授权链、redacted envelope、staging / promotion gate 和 activation gate。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_generation_scheduler_review_only_dispatcher.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_scheduler_dispatcher python3 -m compileall backend
uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py -q
git diff --check
```

### P1-B-30 Generation Scheduler review-only dispatcher drain

状态：已完成最小骨架。

目标：

```text
新增 bounded review-only dispatcher drain API，模拟后台 worker 的一个受限 tick：按预算连续处理多个 queued 且 provider_review_required 的调度项，并把它们推进到 ProviderAdapterExecutionReceipt / ProviderOutputEnvelope ledger 边界，但不进入 staging、promotion、队列完成或 runtime 激活。
```

已落地：

- `POST /api/sessions/{session_id}/generation-schedule/workers/run-review-only-dispatcher-drain`
- 请求体复用 `worker_id`、`note` 和 `max_items`；`max_items` 默认 4，单次上限 16。
- 拒绝 `schedule_item_id`、`authorization_ref`、`artifact_profile`、runner import path、staging / promotion path 等定向 metadata，避免一次 drain 错挂授权或产物路径。
- 内部复用 `run-review-only-dispatcher-step`，不复制 guard、authorization 或 runner 校验逻辑。
- 返回 `worker_step.stop_reason`：`budget_exhausted` 或 `no_eligible_items`，并返回 `remaining_eligible_count`。
- 返回 `dispatcher_steps`、queue、worker cache 和 artifact ledger 汇总。
- ledger 只包含 executor request、authorization、adapter receipt、ProviderOutputEnvelope 四类。

当前结论：

- 这是正式后台执行器前的吞吐量控制面雏形，不是真 provider worker。
- 它不读取 `.env`、不调用 provider、不 staging、不 promotion、不 complete queue item、不写世界状态、不激活 runtime。
- 如果第 N 个 item 失败，前 N-1 个 item 的 review-only ledger 写入会保留；该行为是 fail-fast partial progress，不是事务性批处理。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_generation_scheduler_review_only_dispatcher_drain.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_scheduler_dispatcher_drain python3 -m compileall backend
uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py -q
git diff --check
```

### P1-B-31 Campaign Router dispatcher prefetch

状态：已完成最小骨架。

目标：

```text
保留现有 Campaign Router `prefetch-next` dry-run 语义，同时新增显式 dispatcher drain 预取入口，让玩家进入当前节点时的后台预取证据可以推进到 ProviderAdapterExecutionReceipt / ProviderOutputEnvelope ledger 边界。
```

已落地：

- `POST /api/sessions/{session_id}/campaign-router/prefetch-next-dispatcher-drain`
- 旧 `POST /api/sessions/{session_id}/campaign-router/prefetch-next` 保持 dry-run worker step 语义不变。
- 新入口默认 `max_items = 2`，调用 `run_review_only_dispatcher_drain`。
- 返回 `prefetch_request`、`worker_step`、`dispatcher_steps`、queue、worker cache、artifact ledger 和更新后的 `campaign_router`。
- 拒绝 `schedule_item_id`、`authorization_ref`、`artifact_profile` 和本地导入路径；Campaign Router 的 next node 只是触发上下文，不是 scheduler queue 定向过滤器。

当前结论：

- 这是运行时路由到 review-only dispatcher drain 的胶水，不是真 provider 调度器。
- 它不读取 `.env`、不调用 provider、不 staging、不 promotion、不 complete queue item、不写世界状态、不激活 runtime。
- 前端现有 fire-and-forget 仍应使用旧 `prefetch-next`，新入口优先用于 Studio / evidence 或显式后台执行器实验。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_campaign_router_dispatcher_prefetch.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_campaign_router_dispatcher_prefetch python3 -m compileall backend
uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py -q
git diff --check
```

### P1-B-32 Generation Scheduler prefetch cache view

状态：已完成最小骨架。

目标：

```text
新增只读 prefetch cache API，从 latest generation schedule run 的 queue 与 generation_artifact_ledger 派生 schedule item 级预取状态视图，供前端 / Studio 读取后台预取证据，但不创建 run、不推进 dispatcher、不调用 provider、不写世界状态、不激活 runtime。
```

已落地：

- `GET /api/sessions/{session_id}/generation-schedule/prefetch-cache`
- 视图按 `schedule_item_id` 汇总 executor request、provider authorization、adapter receipt、ProviderOutputEnvelope、staging manifest 与 promotion report refs。
- `cache_status` 区分 `queued`、`review_only_envelope_ready`、`staged_review_only`、`promotion_blocked`、`promotion_allowed_pending_activation` 等状态。
- `provider_call_count_by_this_request` 与 `world_mutation_count_by_this_request` 固定为 0；历史 envelope 中记录过的 provider 调用只计入 `recorded_provider_call_count`。
- GET 前后不改变 `generation_schedule_runs`、`generation_schedule_queue_items`、`generation_schedule_worker_cache`、`generation_artifact_ledger`、`provider_logs` 或 `world_instance`。

当前结论：

- 这是从 queue / ledger 派生的读模型，不是新的缓存表，不是真后台执行器，也不是正式预生成产物缓存。
- 它不读取 `.env`、不调用 provider、不 staging、不 promotion、不 complete queue item、不写世界状态、不激活 runtime。
- 后续真实后台 executor 可以让该视图读到更多 reviewed refs，但仍必须经过 staging、promotion、runtime package、WorldStateDeltaTransaction 和 activation gate。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_generation_prefetch_cache_view.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_generation_prefetch_cache_view python3 -m compileall backend
uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py -q
git diff --check
```

### P1-B-33 Provider adapter runner handoff 导出

状态：已完成最小骨架。

目标：

```text
新增外部 provider adapter runner handoff 导出 API，让后端能从 latest run 的 ledger 中导出已校验的 GenerationExecutorRunRequest / ProviderExecutionAuthorization、建议 /tmp 路径、runner argv 模板和 import 回灌请求体；该 API 不直接调用 provider，也不写 ledger。
```

已落地：

- `POST /api/sessions/{session_id}/generation-schedule/workers/export-provider-adapter-runner-handoff`
- 要求同一 session / latest run / schedule item 下已有匹配的 `GenerationExecutorRunRequest` 与 `ProviderExecutionAuthorization`。
- 从 ledger compact 还原并重新校验 runner 所需的 executor request 与 authorization。
- 返回 dry-run、live text、live image 三类 `tools/provider_adapter/run_provider_adapter.py` argv 模板。
- 返回外部 runner 完成后调用 `import-provider-adapter-runner-output` 的请求体。
- 测试覆盖只读副作用：导出前后 generation schedule / worker cache / ledger / provider logs / world instance 行数不变。

当前结论：

- 这是正式后台执行器前的外部 worker 交接单，不是真 provider 调用入口。
- 它不读取 `.env`、不调用 provider、不包含 prompt 正文、不包含 provider 响应正文、不生成 receipt/envelope、不 staging、不 promotion、不写世界状态、不激活 runtime。
- live 模板中的 dotenv 路径、prompt 文件和 artifact 输出必须由外部 worker 在显式授权下提供；runner 输出仍必须通过 import API 回灌并继续走 staging / promotion gate。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_provider_runner_handoff_export.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_provider_runner_handoff_export python3 -m compileall backend
uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py -q
git diff --check
```

### P1-B-34 Provider adapter runner handoff roundtrip smoke

状态：已完成最小烟测。

目标：

```text
补一条 fixture roundtrip smoke，证明 export-provider-adapter-runner-handoff 返回的 runner_inputs 可以生成 dry-run ProviderAdapterExecutionReceipt / ProviderOutputEnvelope，本地文件可通过 import-provider-adapter-runner-output 回灌 ledger，并能被 prefetch-cache 读成 review_only_envelope_ready。
```

已落地：

- 新增 `test_provider_adapter_runner_handoff_roundtrip_import_updates_prefetch_cache`。
- 测试直接消费 handoff 的 `runner_inputs.executor_request` 与 `runner_inputs.provider_execution_authorization`。
- 使用 `tools/provider_adapter/run_provider_adapter.py` 的 dry-run builder 生成 receipt / envelope，并写入 pytest `/tmp`。
- 通过既有 `import-provider-adapter-runner-output` API 回灌 ledger。
- 最后通过 `GET /generation-schedule/prefetch-cache` 验证 `sched_next_map_visual_prefetch` 为 `review_only_envelope_ready`，且 staging / promotion / activation 仍为空或阻断。

当前结论：

- 这是 handoff 与 import 边界的 fixture smoke，不是真 provider 调用。
- 它不读取 `.env`、不调用 provider、不 staging、不 promotion、不 complete queue item、不写世界状态、不激活 runtime。
- OpenCode headless 在当前受控通道内尝试被安全策略拒绝为外部数据披露风险，因此使用 `local_codex_safe_fallback` 完成。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_provider_runner_handoff_roundtrip.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_provider_runner_handoff_roundtrip python3 -m compileall backend
uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py -q
git diff --check
```

### P1-B-35 Provider runner handoff evidence summary

状态：已完成最小证据接入。

目标：

```text
把 provider runner handoff export / dry-run runner / import / prefetch-cache roundtrip 的能力纳入 demo evidence，让 evidence.json、summary.md 和 index.html 都能展示 handoff 状态、roundtrip cache 状态、安全边界和对应任务包。
```

已落地：

- `tools/demo/export_evidence.py` 新增 `generation_scheduler.provider_runner_handoff` 摘要。
- `summary.md` 和 `index.html` 的 Generation Scheduler 区块展示 `fixture_roundtrip_covered`、`review_only_envelope_ready` 和 runtime activation 阻断状态。
- 摘要引用 P1-B-33 / P1-B-34 的任务包与验收命令，证明 handoff export 与 roundtrip smoke 已被覆盖。
- `examples/worker_task_packs/p1b_provider_runner_handoff_evidence.v0.1.json` 新增本轮证据接入任务包。

边界：

- 本任务不新增 provider 调用、不读取 `.env`、不写 ledger、不 staging、不 promotion、不写世界状态、不激活 runtime。
- 它只导出演示证据摘要，不代表后端自动后台执行器已经完成。
- OpenCode headless 在当前受控通道内尝试被安全策略拒绝为外部数据披露风险，因此使用 `local_codex_safe_fallback` 完成。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_provider_runner_handoff_evidence.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_provider_runner_handoff_evidence python3 -m py_compile tools/demo/export_evidence.py
python3 tools/demo/export_evidence.py --output-dir /tmp/provider_runner_handoff_evidence
rg -n "provider_runner_handoff|runner handoff|fixture_roundtrip_covered|review_only_envelope_ready" /tmp/provider_runner_handoff_evidence
git diff --check
```

### P1-B-36 Generation Scheduler background executor tick

状态：已完成最小骨架。

目标：

```text
新增 Generation Scheduler review-only background executor tick API，作为正式后台执行器 / daemon loop 前的稳定最小壳：默认按小预算复用现有 dispatcher drain，把 eligible queued provider-review 项推进到 ProviderAdapterExecutionReceipt / ProviderOutputEnvelope ledger 边界，同时保持零 live provider 调用、零 staging、零 promotion、零队列完成、零世界写入、零 runtime 激活。
```

已落地：

- `POST /api/sessions/{session_id}/generation-schedule/workers/run-review-only-background-executor-tick`
- 默认 `max_items = 2`，单次上限 8。
- 内部复用 `run_review_only_dispatcher_drain`，不复制 guard、authorization、runner 或 ledger 校验逻辑。
- 返回 `worker_step.worker_mode = review_only_background_executor_tick`、底层 `dispatcher_worker_step`、`dispatcher_steps`、queue、worker cache、artifact ledger 和 `generation_prefetch_cache`。
- `background_executor_tick.safety` 明确记录不读取 `.env`、不调用 provider、不 staging、不 promotion、不 complete queue item、不写世界状态、不激活 runtime。
- `tools/demo/export_evidence.py` 新增 `generation_scheduler.background_executor_tick` 摘要，并在 `summary.md` / `index.html` 展示 tick 状态、默认预算和安全边界。
- `examples/worker_task_packs/p1b_scheduler_background_executor_tick.v0.1.json` 记录本轮任务包与 OpenCode headless 在当前受控通道内被执行环境拒绝后的 `local_codex_safe_fallback`。

当前结论：

- 这是正式后台执行器 / daemon loop 前的 API 形状与吞吐预算壳，不是真 provider worker。
- 后续可以把触发方式从手动 API 换成定时 / 事件驱动，但仍必须保留 ProviderOutputEnvelope、staging / promotion gate、runtime package gate 和 WorldStateDeltaTransaction gate。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_scheduler_background_executor_tick.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_scheduler_background_tick python3 -m compileall backend
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_scheduler_background_tick_tools python3 -m py_compile tools/demo/export_evidence.py
uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py -q
python3 tools/demo/export_evidence.py --output-dir /tmp/scheduler_background_tick_evidence
rg -n "background_executor_tick|review_only_tick_api_ready|run-review-only-background-executor-tick" /tmp/scheduler_background_tick_evidence
git diff --check
```

### P1-B-37 Generation Scheduler background handoff tick

状态：已完成最小骨架。

目标：

```text
在现有 review-only background executor tick 基础上，新增 background handoff tick API：先按小预算推进 eligible queued provider-review 项到 ProviderAdapterExecutionReceipt / ProviderOutputEnvelope ledger 边界，再为本轮 dispatched 项批量导出 provider adapter runner handoff bundle，形成外部 runner 可消费的安全 outbox；不得调用 provider、不得读取 .env、不得运行 provider adapter、不得 staging/promotion、不得 complete queue item、不得写世界状态、不得激活 runtime。
```

已落地：

- `POST /api/sessions/{session_id}/generation-schedule/workers/run-review-only-background-handoff-tick`
- 默认 `max_items = 2`，单次上限 8。
- 内部复用 `run_review_only_background_executor_tick` 和 `export_provider_adapter_runner_handoff`。
- 返回 `runner_handoffs[]`，每项包含脱敏 executor request、provider authorization、建议 `/tmp` 路径、dry-run / live text / live image 命令模板和 import 回灌请求体。
- `background_handoff_tick.safety` 明确记录不读取 `.env`、不调用 provider、不运行 provider adapter、不 staging、不 promotion、不 complete queue item、不写世界状态、不激活 runtime。
- `tools/demo/export_evidence.py` 新增 `generation_scheduler.background_handoff_tick` 摘要，并在 `summary.md` / `index.html` 展示 handoff tick 状态、handoff 数和安全边界。
- `examples/worker_task_packs/p1b_scheduler_background_handoff_tick.v0.1.json` 记录本轮任务包与 OpenCode headless 在当前受控通道内被执行环境拒绝后的 `local_codex_safe_fallback`。

当前结论：

- 这是正式后台 provider worker 前的安全 outbox，不是真 provider worker。
- 外部 runner 执行后仍必须通过 `import-provider-adapter-runner-output` 回灌 receipt/envelope，并继续走 staging / promotion / activation gates。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_scheduler_background_handoff_tick.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_scheduler_background_handoff_tick python3 -m compileall backend
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_scheduler_background_handoff_tick_tools python3 -m py_compile tools/demo/export_evidence.py
uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py -q
python3 tools/demo/export_evidence.py --output-dir /tmp/scheduler_background_handoff_tick_evidence
rg -n "background_handoff_tick|review_only_handoff_tick_ready|run-review-only-background-handoff-tick" /tmp/scheduler_background_handoff_tick_evidence
git diff --check
```

### P1-C-1 CoreArtifactAlignmentReport 核心对象对齐审计

状态：已完成并清零当前迁移队列。

已落地：

- `shared/schemas/core_artifact_alignment_report.v0.1.schema.json`
- `tools/content_pipeline/build_core_artifact_alignment_report.py`
- `tools/content_pipeline/validate_core_artifact_alignment_report.py`
- `examples/review_packs/core_artifact_alignment_report.v0.1.json`
- `docs/CORE_ARTIFACT_ALIGNMENT_REPORT_V0_1.md`
- `examples/worker_task_packs/p1c_core_artifact_alignment_report.v0.1.json`
- `tools/demo/export_evidence.py` 已纳入报告摘要和 validation command。

当前结论：

- 该报告只做内部 evidence / 迁移审计，不调用 provider、不读取 `.env`、不激活 runtime、不写世界状态。
- 当前报告状态为 `passed`，无核心对象 validator 失败，`missing_core_alignment_count=0`，`migration_tasks=[]`。
- 前端 mock pack、核心示例和 stage01-stage07 WorldStateDeltaTransaction 链已处于 `native_snapshot_ready`。
- 初始 8 个早期叙事 / 阶段 / dossier review pack 已完成 P1-C-2 到 P1-C-9 的显式边界收敛：`mvp_compiler_review_dossier`、`mvp_stage_candidate_pack`、`mvp_multistage_stage_candidate_pack`、`mvp_multistage_content_pack`、`mvp_next_stage_compilable_object_plan`、`mvp_story_asset_review_pack`、`mvp_story_asset_promotion_report` 与 `mvp_stage05_plan_realization_report` 均已声明为 `review_only_not_applicable`。后续新增 review pack / provider artifact / runtime package 必须携带核心对象原生快照、core refs 或显式 not-applicable 边界，否则报告会重新回到 `needs_migration`。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1c_core_artifact_alignment_report.v0.1.json
python3 tools/content_pipeline/build_core_artifact_alignment_report.py --validate
python3 tools/content_pipeline/validate_core_artifact_alignment_report.py examples/review_packs/core_artifact_alignment_report.v0.1.json
python3 -m py_compile tools/content_pipeline/build_core_artifact_alignment_report.py tools/content_pipeline/validate_core_artifact_alignment_report.py tools/demo/export_evidence.py
python3 tools/demo/export_evidence.py --output-dir /tmp/core_artifact_alignment_report_evidence
git diff --check
```

### P1-C-2 MVP Compiler Review Dossier 核心对象对齐边界

状态：已完成最小骨架。

已落地：

- `shared/schemas/mvp_compiler_review_dossier.v0.1.schema.json` 增加 `core_artifact_alignment` 字段。
- `tools/content_pipeline/build_mvp_compiler_review_dossier.py` 会确定性输出该边界。
- `examples/review_packs/mvp_compiler_review_dossier.v0.1.json` 显式声明 `review_only_not_applicable`。
- `tools/content_pipeline/build_core_artifact_alignment_report.py` 会优先尊重显式 not-applicable 边界。
- `examples/review_packs/core_artifact_alignment_report.v0.1.json` 中待迁移目标从 8 个降为 7 个。
- `examples/worker_task_packs/p1c_dossier_core_alignment_boundary.v0.1.json`

当前结论：

- `mvp_compiler_review_dossier` 是总审查交付包，不是 runtime package、CGOP、ContextPackage、FactEntry 或 WorldStateDeltaTransaction。
- 后续核心对象迁移应针对它引用的阶段候选包、多阶段内容包或具体运行时产物，而不是把总审查包强行包装成核心对象。
- 本任务不调用 provider、不读取 `.env`、不激活 runtime、不写世界状态。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1c_dossier_core_alignment_boundary.v0.1.json
python3 tools/content_pipeline/build_mvp_compiler_review_dossier.py --validate
python3 tools/content_pipeline/build_core_artifact_alignment_report.py --validate
python3 tools/content_pipeline/validate_core_artifact_alignment_report.py examples/review_packs/core_artifact_alignment_report.v0.1.json
python3 -m py_compile tools/content_pipeline/build_mvp_compiler_review_dossier.py tools/content_pipeline/build_core_artifact_alignment_report.py tools/demo/export_evidence.py
python3 tools/demo/export_evidence.py --output-dir /tmp/dossier_core_alignment_evidence
git diff --check
```

### P1-C-3 StageCandidatePack 核心对象对齐边界

状态：已完成最小骨架。

已落地：

- `shared/schemas/stage_candidate_pack.v0.1.schema.json` 增加可选 `core_artifact_alignment` 字段。
- `tools/content_pipeline/build_stage_candidate_pack.py` 会为 `mvp_stage_candidate_pack` 确定性输出该边界。
- `examples/review_packs/mvp_stage_candidate_pack.v0.1.json` 显式声明 `review_only_not_applicable`。
- `examples/review_packs/core_artifact_alignment_report.v0.1.json` 中待迁移目标从 7 个降为 6 个。
- `examples/worker_task_packs/p1c_stage_candidate_core_alignment_boundary.v0.1.json`

当前结论：

- `StageCandidatePack` 是 review-only 阶段候选容器，不是 runtime package、CGOP、ContextPackage、FactEntry 或 WorldStateDeltaTransaction。
- 后续核心对象迁移应针对每个 stage candidate 引用的 WorldStateDelta / WorldStateDeltaTransaction / runtime package，而不是激活整个 review pack。

### P1-C-4 Multistage StageCandidatePack 核心对象对齐边界

状态：已完成。

产物：

- `examples/worker_task_packs/p1c_multistage_stage_candidate_core_alignment_boundary.v0.1.json`
- `tools/content_pipeline/build_multistage_content_pack.py`
- `examples/review_packs/mvp_multistage_stage_candidate_pack.v0.1.json`
- `examples/review_packs/core_artifact_alignment_report.v0.1.json`

决策：

- `mvp_multistage_stage_candidate_pack.v0.1` 是 review-only 多阶段候选容器。
- 它聚合 Stage 05/06/07 的候选摘要、WorldStateDelta 引用、资产晋升状态和 runtime package 引用，但本身不是 `ContextPackage`、`FactEntry`、`CGOP` 或 `WorldStateDeltaTransaction`。
- 它不能直接激活 runtime，也不能直接写世界状态。
- `examples/review_packs/core_artifact_alignment_report.v0.1.json` 中待迁移目标从 6 个降为 5 个。

后续：

- 剩余迁移目标包括 `mvp_multistage_content_pack`、`mvp_next_stage_compilable_object_plan`、`mvp_stage05_plan_realization_report`、`mvp_story_asset_promotion_report` 与 `mvp_story_asset_review_pack`。
- 本任务不调用 provider、不读取 `.env`、不激活 runtime、不写世界状态。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1c_multistage_stage_candidate_core_alignment_boundary.v0.1.json
python3 tools/content_pipeline/build_multistage_content_pack.py --validate
python3 tools/content_pipeline/validate_stage_candidate_pack.py examples/review_packs/mvp_multistage_stage_candidate_pack.v0.1.json
python3 tools/content_pipeline/build_mvp_compiler_review_dossier.py --validate
python3 tools/content_pipeline/build_core_artifact_alignment_report.py --validate
python3 tools/content_pipeline/validate_core_artifact_alignment_report.py examples/review_packs/core_artifact_alignment_report.v0.1.json
python3 -m py_compile tools/content_pipeline/build_multistage_content_pack.py tools/content_pipeline/build_mvp_compiler_review_dossier.py tools/content_pipeline/build_core_artifact_alignment_report.py tools/demo/export_evidence.py
python3 tools/demo/export_evidence.py --output-dir /tmp/multistage_stage_candidate_core_alignment_evidence
git diff --check
```

### P1-C-5 MultistageContentPack 核心对象对齐边界

状态：已完成。

产物：

- `examples/worker_task_packs/p1c_multistage_content_core_alignment_boundary.v0.1.json`
- `shared/schemas/multistage_content_pack.v0.1.schema.json`
- `tools/content_pipeline/build_multistage_content_pack.py`
- `examples/review_packs/mvp_multistage_content_pack.v0.1.json`
- `examples/review_packs/core_artifact_alignment_report.v0.1.json`

决策：

- `mvp_multistage_content_pack.v0.1` 是 review-only 多阶段内容生产审查包。
- 它串联 Stage 05/06/07 的叙事包、WorldStateDelta、compiled asset candidate 和阶段候选包引用，但本身不是 `ContextPackage`、`FactEntry`、`CGOP` 或 `WorldStateDeltaTransaction`。
- 它不能直接激活 runtime，也不能直接写世界状态。
- `examples/review_packs/core_artifact_alignment_report.v0.1.json` 中待迁移目标从 5 个降为 4 个。

后续：

- 剩余迁移目标包括 `mvp_next_stage_compilable_object_plan`、`mvp_stage05_plan_realization_report`、`mvp_story_asset_promotion_report` 与 `mvp_story_asset_review_pack`。
- 本任务不调用 provider、不读取 `.env`、不激活 runtime、不写世界状态。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1c_multistage_content_core_alignment_boundary.v0.1.json
python3 tools/content_pipeline/build_multistage_content_pack.py --validate
python3 tools/content_pipeline/validate_multistage_content_pack.py examples/review_packs/mvp_multistage_content_pack.v0.1.json
python3 tools/content_pipeline/build_mvp_compiler_review_dossier.py --validate
python3 tools/content_pipeline/build_core_artifact_alignment_report.py --validate
python3 tools/content_pipeline/validate_core_artifact_alignment_report.py examples/review_packs/core_artifact_alignment_report.v0.1.json
python3 -m py_compile tools/content_pipeline/build_multistage_content_pack.py tools/content_pipeline/validate_multistage_content_pack.py tools/content_pipeline/build_mvp_compiler_review_dossier.py tools/content_pipeline/build_core_artifact_alignment_report.py tools/demo/export_evidence.py
python3 tools/demo/export_evidence.py --output-dir /tmp/multistage_content_core_alignment_evidence
git diff --check
```

### P1-C-6 CompilableObjectPlan 核心对象对齐边界

状态：已完成。

产物：

- `examples/worker_task_packs/p1c_compilable_object_plan_core_alignment_boundary.v0.1.json`
- `shared/schemas/compilable_object_plan.v0.1.schema.json`
- `tools/content_pipeline/build_compilable_object_plan.py`
- `examples/review_packs/mvp_next_stage_compilable_object_plan.v0.1.json`
- `examples/review_packs/core_artifact_alignment_report.v0.1.json`

决策：

- `mvp_next_stage_compilable_object_plan.v0.1` 是 review-only 下一阶段编译计划。
- 它声明下一步要生成哪些对象、依赖什么证据和验证门，但本身不是 `ContextPackage`、`FactEntry`、`CGOP` 或 `WorldStateDeltaTransaction`。
- 它不能直接激活 runtime，也不能直接写世界状态。
- `examples/review_packs/core_artifact_alignment_report.v0.1.json` 中待迁移目标从 4 个降为 3 个。

后续：

- 剩余迁移目标包括 `mvp_stage05_plan_realization_report`、`mvp_story_asset_promotion_report` 与 `mvp_story_asset_review_pack`。
- 本任务不调用 provider、不读取 `.env`、不激活 runtime、不写世界状态。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1c_compilable_object_plan_core_alignment_boundary.v0.1.json
python3 tools/content_pipeline/build_compilable_object_plan.py --validate
python3 tools/content_pipeline/validate_compilable_object_plan.py examples/review_packs/mvp_next_stage_compilable_object_plan.v0.1.json
python3 tools/content_pipeline/build_mvp_compiler_review_dossier.py --validate
python3 tools/content_pipeline/build_core_artifact_alignment_report.py --validate
python3 tools/content_pipeline/validate_core_artifact_alignment_report.py examples/review_packs/core_artifact_alignment_report.v0.1.json
python3 -m py_compile tools/content_pipeline/build_compilable_object_plan.py tools/content_pipeline/validate_compilable_object_plan.py tools/content_pipeline/build_mvp_compiler_review_dossier.py tools/content_pipeline/build_core_artifact_alignment_report.py tools/demo/export_evidence.py
python3 tools/demo/export_evidence.py --output-dir /tmp/compilable_object_plan_core_alignment_evidence
git diff --check
```

### P1-C-7 StoryAssetReviewPack 核心对象对齐边界

状态：已完成。

产物：

- `examples/worker_task_packs/p1c_story_asset_review_core_alignment_boundary.v0.1.json`
- `shared/schemas/mvp_story_asset_review_pack.v0.1.schema.json`
- `examples/review_packs/mvp_story_asset_review_pack.v0.1.json`
- `examples/review_packs/core_artifact_alignment_report.v0.1.json`

决策：

- `mvp_story_asset_review_pack.v0.1` 是 review-only 多阶段剧情与玩法对象审查索引。
- 它汇总阶段剧情、NPC、材料、地图节点、战斗节点、研发 hook 和资产引用，但本身不是 `ContextPackage`、`FactEntry`、`CGOP` 或 `WorldStateDeltaTransaction`。
- 它不能直接激活 runtime，也不能直接写世界状态。
- `examples/review_packs/core_artifact_alignment_report.v0.1.json` 中待迁移目标从 3 个降为 2 个。

后续：

- 剩余迁移目标包括 `mvp_stage05_plan_realization_report` 与 `mvp_story_asset_promotion_report`。
- 本任务不调用 provider、不读取 `.env`、不激活 runtime、不写世界状态。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1c_story_asset_review_core_alignment_boundary.v0.1.json
python3 tools/content_pipeline/validate_mvp_story_asset_review_pack.py examples/review_packs/mvp_story_asset_review_pack.v0.1.json
python3 tools/narrative/validate_narrative_gameplay_contract.py examples/review_packs/mvp_story_asset_review_pack.v0.1.json
python3 tools/content_pipeline/build_mvp_compiler_review_dossier.py --validate
python3 tools/content_pipeline/build_core_artifact_alignment_report.py --validate
python3 tools/content_pipeline/validate_core_artifact_alignment_report.py examples/review_packs/core_artifact_alignment_report.v0.1.json
python3 -m py_compile tools/content_pipeline/validate_mvp_story_asset_review_pack.py tools/narrative/validate_narrative_gameplay_contract.py tools/content_pipeline/build_mvp_compiler_review_dossier.py tools/content_pipeline/build_core_artifact_alignment_report.py tools/demo/export_evidence.py
python3 tools/demo/export_evidence.py --output-dir /tmp/story_asset_review_core_alignment_evidence
git diff --check
```

### P1-C-8 StoryAssetPromotionReport 核心对象对齐边界

状态：已完成。

产物：

- `examples/worker_task_packs/p1c_story_asset_promotion_core_alignment_boundary.v0.1.json`
- `tools/content_pipeline/build_mvp_review_pack_promotion_report.py`
- `examples/review_packs/mvp_story_asset_promotion_report.v0.1.json`
- `examples/review_packs/core_artifact_alignment_report.v0.1.json`

决策：

- `mvp_story_asset_promotion_report.v0.1` 是 review-only 资产晋升决策报告。
- 它记录 fallback_ready、candidate_only、blocked 等晋升判断，但本身不是 `ContextPackage`、`FactEntry`、`CGOP` 或 `WorldStateDeltaTransaction`。
- 它不能直接激活 runtime，也不能直接写世界状态。
- `examples/review_packs/core_artifact_alignment_report.v0.1.json` 中待迁移目标从 2 个降为 1 个。

后续：

- 剩余迁移目标为 `mvp_stage05_plan_realization_report`。
- 本任务不调用 provider、不读取 `.env`、不激活 runtime、不写世界状态。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1c_story_asset_promotion_core_alignment_boundary.v0.1.json
python3 tools/content_pipeline/build_mvp_review_pack_promotion_report.py examples/review_packs/mvp_story_asset_review_pack.v0.1.json --output examples/review_packs/mvp_story_asset_promotion_report.v0.1.json
python3 tools/content_pipeline/build_mvp_compiler_review_dossier.py --validate
python3 tools/content_pipeline/build_core_artifact_alignment_report.py --validate
python3 tools/content_pipeline/validate_core_artifact_alignment_report.py examples/review_packs/core_artifact_alignment_report.v0.1.json
python3 -m py_compile tools/content_pipeline/build_mvp_review_pack_promotion_report.py tools/content_pipeline/build_mvp_compiler_review_dossier.py tools/content_pipeline/build_core_artifact_alignment_report.py tools/demo/export_evidence.py
python3 tools/demo/export_evidence.py --output-dir /tmp/story_asset_promotion_core_alignment_evidence
git diff --check
```

### P1-C-9 Stage05PlanRealizationReport 核心对象对齐边界

状态：已完成。

产物：

- `examples/worker_task_packs/p1c_stage05_realization_core_alignment_boundary.v0.1.json`
- `tools/content_pipeline/build_stage05_plan_realization.py`
- `examples/review_packs/mvp_stage05_plan_realization_report.v0.1.json`
- `examples/review_packs/core_artifact_alignment_report.v0.1.json`

决策：

- `mvp_stage05_plan_realization_report.v0.1` 是 review-only 计划落地审查报告。
- 它证明 plan 可以落地成 `NarrativeEventBundle`、`WorldStateDelta`、next `RunWorldState`、`Proposal` 和 `CompiledAssetCandidate`，但本身不是 `ContextPackage`、`FactEntry`、`CGOP` 或 `WorldStateDeltaTransaction`。
- 它不能直接激活 runtime，也不能直接写世界状态。
- `examples/review_packs/core_artifact_alignment_report.v0.1.json` 的 `missing_core_alignment_count` 已降为 0，`overall_status` 为 `passed`。

后续：

- 新增 review pack / provider artifact / runtime package 时，必须携带核心对象原生快照、core refs 或显式 not-applicable 边界，否则 CoreArtifactAlignmentReport 会重新回到 `needs_migration`。
- 本任务不调用 provider、不读取 `.env`、不激活 runtime、不写世界状态。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1c_stage05_realization_core_alignment_boundary.v0.1.json
python3 tools/content_pipeline/build_stage05_plan_realization.py --validate
python3 tools/content_pipeline/build_mvp_compiler_review_dossier.py --validate
python3 tools/content_pipeline/build_core_artifact_alignment_report.py --validate
python3 tools/content_pipeline/validate_core_artifact_alignment_report.py examples/review_packs/core_artifact_alignment_report.v0.1.json
python3 -m py_compile tools/content_pipeline/build_stage05_plan_realization.py tools/content_pipeline/build_mvp_compiler_review_dossier.py tools/content_pipeline/build_core_artifact_alignment_report.py tools/demo/export_evidence.py
python3 tools/demo/export_evidence.py --output-dir /tmp/stage05_realization_core_alignment_evidence
git diff --check
```

## 4. 当前 P0 任务

### P0-M 前端战斗地图视觉底座改造

状态：已完成。

目标：

- 不再把失败的整图候选作为默认玩家地图。
- 以前端可运行体验为优先，基于 `MapRuntimePackage` 绘制全屏自然战场底座：地形、道路、部署基座、核心目标、出生点和遮挡氛围分层渲染。
- 战斗底图必须像游戏画面，而不是控制图、参考图、棋盘、平行四边形或调试画布。
- 保留 `painted_visual_layer` 作为未来晋升入口；当发布底图不足时，程序化底图是玩家侧默认 fallback。

允许修改：

- `frontend/`
- `tools/frontend/`
- 必要的 `docs/FRONTEND_VISUAL_RUNTIME_AUDIT_V0_1.md`
- 必要的 evidence / validation 文档更新

验收：

```bash
node --check frontend/app.js
python3 tools/frontend/validate_battle_visual_contract.py
```

验收重点：

- 战斗画布占据浏览器中部主视觉，不能只是小块地图。
- 路径、塔位、目标和出生点仍来自 `MapRuntimePackage`，不能从图片里反推。
- 默认玩家视图不得显示 control sketch、reference board、箭头、网格标签或 provider 生成失败图。
- 拖拽部署路径保持可用，点击放置可作为 fallback。

已落地：

- `frontend/app.js`：默认战斗底座改为 `MapRuntimePackage` seed 驱动的程序化地形、土石路、部署基座、目标地基和入口雾潮；整张玩家地图图像不再进入默认 preload / drawBackdrop。
- `frontend/app.js` v0.2：新增平滑路口、路肩、车辙 / 木板细节、暗潮洼地、废墟 / 补给 / 灯具 / 信号残骸地标，让玩家默认战场更接近完整塔防关卡画面。
- `frontend/styles.css`：压低 HUD 遮挡，battle canvas 继续全屏铺底。
- `tools/frontend/validate_battle_visual_contract.py`：增加程序化底座、棋盘 helper 禁止、失败视觉层禁止发布、runtime package 结构、路肩、车辙、暗潮洼地和世界地标检查。
- `docs/FRONTEND_VISUAL_RUNTIME_AUDIT_V0_1.md` 与 `frontend/README.md`：同步玩家默认战斗底座事实源。

已验证：

```bash
node --check frontend/app.js
python3 tools/frontend/validate_battle_visual_contract.py
python3 tools/frontend/capture_battle_visual_smoke.py --allow-missing-browser --output-dir /tmp/p0m_browser_visual_smoke
python3 tools/frontend/capture_battle_visual_smoke.py --output-dir /tmp/p0m_browser_visual_smoke
python3 tools/frontend/capture_battle_visual_smoke.py --output-dir /tmp/frontend_procedural_map_polish_smoke
python3 tools/demo/export_evidence.py --output-dir /tmp/develop_p0m_visual_evidence
```

遗留风险：

- 当前截图只覆盖首战视觉烟测，不替代后续多节点地图、真实拖拽交互和完整录屏的人工验收。

补充：`WorldStateDeltaTransaction v0.1` 已作为架构固化项落地到 schema、批量 validator、首战示例、stage01-stage07 事务链和 demo evidence；它包装现有 `WorldStateDelta v0.1`，不替换 delta schema，也不允许通用 `effects[]` 绕过 `operations[]` 白名单。

补充：Campaign Router 消费的三节点 MVP 主线已经能通过战斗结算接口连续推进。`lamp_wick_store` 使用 stage04 battle_result transaction；`old_signal_tower` 当前只有 research_job 来源的 after-state，因此以 `fixture_bridge` 暴露，并在返回值中保留 `fixture_baseline` 说明。

下一轮可进入 P1。执行 `docs/MAIN_SYNC_PLAN_2026_07_02.md` 前仍需保护 `main` 上 `docs/ASSET_GRAPH_COMPILER_V0_1.md` 用户草稿，并确认是否晋级整个 `develop`。

## 5. P1 任务

### P1-A 视频帧 / spritesheet / atlas 增强

目标：

```text
在已接入 virtual atlas 的基础上，继续固化“图片 -> 图生视频 -> 关键帧 -> 后处理 -> spritesheet atlas -> runtime manifest”路线。
```

要点：

- `virtual_single_frame`、确定性 4 帧 frame sequence、实体 spritesheet atlas 与 LoopContinuityReport 已完成；本任务后续继续推进真实图生视频关键帧。
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
- Research Job proposal / job metadata、battle settlement evidence、frontend mock pack、多节点 battle settlement 与 stage01-stage07 WorldStateDeltaTransaction 链已开始携带或引用统一核心对象；当前已纳入 `CoreArtifactAlignmentReport` 的 review pack 已完成边界收敛。下一步新增可编译对象或真实 provider 产物时，必须继续映射到同一套核心对象字段或显式 not-applicable 边界，而不是新增平行元数据口径。

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
- 必须消费 `RuntimeMapPatchCandidates v0.1`、`TopologyConstrainedMapPromptPack v0.1/v0.2`、`MapTopologyControlSketchPack v0.1`、`MapControlledRegenerationRequestPack v0.1`、`ControlledMapCandidateGenerationRun v0.1`、`ControlledMapCandidateReview v0.1`、`ControlledMapTextFallbackGenerationRun v0.1` 和 `ControlledMapTextFallbackCandidateReview v0.1`。下一步候选任务：对 runtime patch candidate 重新生成 overlay PNG 复核；接入支持参考图的真实图像 provider，或优先完成 `P0-M` 的 MapRuntimePackage 驱动分层程序化底图。不要再把纯文本整图生成作为地图发布候选路线。
- 该任务在 `P0-G MapCompilePackage v0.2` 之后执行。

#### P1-D-01 MapVisualPromotionGateReport 地图视觉发布闸门

状态：已完成最小骨架。

已落地：

- `tools/media/build_map_visual_promotion_gate_report.py`
- `examples/review_packs/map_visual_promotion_gate_report.v0.1.json`
- `examples/worker_task_packs/p1d_map_visual_promotion_gate.v0.1.json`
- `tools/demo/export_evidence.py` 已纳入 `map_visual_promotion_gate` 静态校验和 evidence 摘要。

当前结论：

- 该闸门不评价地图是否漂亮，只检查已被 review 阻断、待重生、待 provider / paintover、`do_not_promote` 或 review-only 的地图候选是否被误发布给玩家侧。
- 当前报告阻断候选 22 个、published 玩家图层 4 个、违规 0 个。
- 这证明现有差图已被隔离在 review evidence / 负样本中；真正改善地图画面仍需后续 reference-image provider、paintover 或 MapRuntimePackage 驱动的分层程序化底图。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1d_map_visual_promotion_gate.v0.1.json
python3 tools/media/build_map_visual_promotion_gate_report.py --output examples/review_packs/map_visual_promotion_gate_report.v0.1.json
python3 -m py_compile tools/media/build_map_visual_promotion_gate_report.py tools/demo/export_evidence.py
python3 tools/demo/export_evidence.py --output-dir /tmp/map_visual_promotion_gate_evidence
python3 tools/frontend/validate_battle_visual_contract.py
git diff --check
```

#### P1-D-02 FrontendProceduralBattleBackdrop v0.3 分层底图 polish

状态：已完成最小修补。

目标：

```text
在不消费失败整图候选、不改写 MapRuntimePackage 事实源的前提下，把前端默认战斗底座继续打磨成更像真实塔防关卡的全屏画面。
```

已落地：

- `frontend/app.js`：新增节点调色、地貌深度带、道路边缘世界小物和部署基座接驳痕迹。
- `tools/frontend/validate_battle_visual_contract.py`：补充静态合约，要求保留道路边缘小物、基座接驳、节点调色 / 地貌深度层，并继续禁止默认整图候选、控制图、参考图、棋盘和虚线控制线。
- `docs/FRONTEND_VISUAL_RUNTIME_AUDIT_V0_1.md`：记录 v0.3 视觉审计结论和截图验收路径。
- `examples/worker_task_packs/p1d_frontend_procedural_backdrop_v3.v0.1.json`：新增本任务 worker handoff 包。

边界：

- 运行时事实仍只来自 `MapRuntimePackage.grid/path_routes/build_slots/objectives/spawn_points`。
- 路边小物、地貌深度带和接驳痕迹只是表现层，不改变寻路、放置合法性或目标耐久。
- 不调用 provider、不读取 `.env`、不修改地图 runtime package、不晋升任何 AI 地图候选。
- OpenCode headless 在当前受控通道内被安全策略拒绝为外部数据披露风险，本轮使用 `local_codex_safe_fallback` 完成。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1d_frontend_procedural_backdrop_v3.v0.1.json
node --check frontend/app.js
python3 tools/frontend/validate_battle_visual_contract.py
python3 tools/frontend/capture_battle_visual_smoke.py --allow-missing-browser --output-dir /tmp/map_procedural_backdrop_v3_after2
git diff --check
```

#### P1-D-03 FrontendProceduralBattleBackdrop v0.4 战场关卡读法

状态：已完成最小修补。

目标：

```text
在不消费失败整图候选、不改写 MapRuntimePackage 事实源的前提下，把默认战斗画面从“漂亮道路底图”继续推进到更像完整塔防关卡：安全区缩放、可玩地块边界、部署台地、路线方向、目标防御区和多路线移动一致性。
```

已落地：

- `frontend/app.js`：`computeBattleMetrics()` 改为按 `path_routes / build_slots / objectives / spawn_points` bounds 和 HUD safe area 做 contain fit，移动端不再只看到被裁切的局部路段。
- `frontend/app.js`：新增可玩地块边界、可部署台地、目标防御区和路线方向 cue，让入口、路线、放置点和核心关系更容易读。
- `frontend/app.js`：地图内 sprite 尺寸随投影缩放并带下限，避免移动端地图缩小时目标/敌人/防御件过大。
- `frontend/app.js`：敌人生成按 `spawn_points.route_id` / route 轮转绑定路线，多路线地图不再画两条路却只跑第一条。
- `tools/frontend/validate_battle_visual_contract.py`：补充 safe-area fit、关卡边界、路线方向 cue、部署台地、目标防御区和 route-bound enemy movement 的静态合约。
- `examples/worker_task_packs/p1d_frontend_battlefield_depth_v4.v0.1.json`：新增本轮 worker handoff 包。

边界：

- 本任务不调用 provider、不读取 `.env`、不修改地图 runtime package、不晋升任何 AI 地图候选。
- 可玩地块边界、台地、方向 cue 和防御区都是表现层；路径、塔位、目标、出生点和放置合法性仍只来自 `MapRuntimePackage`。
- OpenCode headless 在当前受控通道内被安全策略拒绝为外部数据披露风险，本轮使用 `local_codex_safe_fallback` 完成。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1d_frontend_battlefield_depth_v4.v0.1.json
node --check frontend/app.js
python3 tools/frontend/validate_battle_visual_contract.py
python3 tools/frontend/capture_battle_visual_smoke.py --output-dir /tmp/battlefield_depth_v4_scaled_smoke
git diff --check
```

### P1-E 手动 CodeBuddy / OpenCode 任务交付包

状态：已完成最小骨架。

目标：

```text
生成可粘贴给用户侧 CodeBuddy / OpenCode 主代理的任务包模板。
```

要点：

- 任务包包含允许修改范围、验收命令、禁止事项、汇报格式。
- 可被 IDE 侧代理读取完整仓库后执行。
- 不要求本 Codex 受控通道直接外发仓库上下文。
- 新增 `WorkerTaskPack v0.1` schema、validator、中文文档和示例任务包。
- 后续 worker 任务包应先通过 `tools/dev/validate_worker_task_pack.py` 校验，再交给 CodeBuddy / OpenCode / Codex headless / 人类 worker。

已落地：

- `shared/schemas/worker_task_pack.v0.1.schema.json`
- `docs/WORKER_TASK_PACK_V0_1.md`
- `examples/worker_task_packs/p1e_worker_task_pack_protocol.v0.1.json`
- `tools/dev/validate_worker_task_pack.py`

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1e_worker_task_pack_protocol.v0.1.json
python3 -m py_compile tools/dev/validate_worker_task_pack.py
python3 tools/demo/export_evidence.py --output-dir /tmp/worker_task_pack_evidence
git diff --check
```

### P1-F AI 编译架构事实源同步

状态：已完成最小修补。

目标：

```text
把 AI 编译系统总架构、当前架构索引、Generation Scheduler 文档和任务队列之间的事实源边界对齐，避免后续 worker 用概念文档绕过字段级 schema、semantic gate 或 tools。
```

已落地：

- `docs/AI_COMPILATION_SYSTEM_V0_1.md`：把概念层 latency 口径改为 `GenerationSchedulePlan v0.1` 的实际字段枚举映射，避免使用未落地调度枚举。
- `docs/CURRENT_ARCHITECTURE_INDEX.md`：补充 `WorldStateDelta v0.1` 本体的字段级事实源、结构 validator、semantic gate、applier、transaction schema 和 transaction validator 入口。
- `control/TASK_QUEUE.md`：修正旧状态描述，明确 item 级队列、session dry-run 持久化、worker cache、retry / fallback、provider guard 和 Campaign Router dry-run 胶水已落地；正式后台 executor、真实 provider 调度、跨请求缓存和 activation / promotion gate 仍未完成。
- `examples/worker_task_packs/p1f_architecture_fact_source_sync.v0.1.json`：新增架构事实源同步任务包。

边界：

- 本任务不修改 schema、工具脚本、后端、前端或媒体资源。
- 本任务不调用 provider、不读取 `.env`、不写世界状态、不激活 runtime。
- OpenCode headless 在当前受控通道内尝试被安全策略拒绝为外部数据披露风险，因此使用 `local_codex_safe_fallback` 在隔离 worktree 内完成。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1f_architecture_fact_source_sync.v0.1.json
python3 -c "from pathlib import Path; paths=[Path('docs/AI_COMPILATION_SYSTEM_V0_1.md'), Path('docs/CURRENT_ARCHITECTURE_INDEX.md'), Path('docs/GENERATION_SCHEDULER_V0_1.md'), Path('control/TASK_QUEUE.md')]; terms=('async'+'_visible','batch'+'_offline'); bad=[str(p) for p in paths if any(term in p.read_text(encoding='utf-8') for term in terms)]; raise SystemExit(('stale latency terms: '+', '.join(bad)) if bad else 0)"
rg -n "effects\\[\\]|operations\\[\\]|WorldStateDeltaTransaction|横切控制面|概念与边界事实源" docs/AI_COMPILATION_SYSTEM_V0_1.md docs/CURRENT_ARCHITECTURE_INDEX.md docs/GENERATION_SCHEDULER_V0_1.md control/TASK_QUEUE.md
git diff --check
```

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
2. 新增 WorldStateDelta / review pack / provider artifact 继续按 CoreArtifactAlignmentReport 口径进入原生产物字段、core refs 或显式 not-applicable 边界；当前已扫描范围的 migration task 已清零。
3. 地图补丁后 overlay 人工/视觉模型复核，以及基于 ControlledMapCandidateGenerationRun 的真实参考图 provider / paintover / 分层程序化底图路线；只有通过 promotion gate 后才允许更新正式 MapRuntimePackage 或发布底图。
4. 扩展地图补丁后的 overlay / 视觉模型复核，并在新增战斗节点后复跑 `tools/frontend/capture_battle_visual_smoke.py`。
5. `P1-A` 真实视频关键帧增强。
6. `P1-B` Generation Scheduler 正式后台执行器、真实 provider 调度、跨请求缓存和 activation / promotion gate；Campaign Router v0.1 dry-run 预取胶水已落地，不应重复实现。

若需要并行，优先组合：

- `P1-A` 与 `P1-B` 可并行，但都应避免破坏当前 MVP 静态 fixture 路径。
- main 同步执行必须单独进行，不应与大规模 P1 实现任务混在同一 worktree。
- `P1-A` 视频帧 / atlas 增强应在地图质量防线之后推进，避免动画资产先接入了错误的地图展示框架。
