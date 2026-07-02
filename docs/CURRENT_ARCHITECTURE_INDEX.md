# 当前架构文档索引

Last updated: 2026-07-02

本文档是当前项目设计、决策、架构与验收材料的入口。

若其他早期文档与本文档冲突，以本文档列出的当前事实源为准。

事实源层级：

- 本索引用于导航、阅读顺序和优先级路由。
- `docs/AI_COMPILATION_SYSTEM_V0_1.md` 用于 AI 编译系统的概念、边界、权限和生命周期事实源。
- 具体字段、op 白名单、semantic gate、运行命令和校验行为，以 `shared/schemas/`、`tools/` 和对应专题文档为字段级事实源。

实现规则：

- 本索引不替代具体规范，只负责告诉 worker 应该读哪份规范。
- 概念文档不替代 schema、semantic gate 或工具脚本；如果概念名与字段名冲突，先按字段级事实源实现，再回补文档映射。
- `WorldStateDeltaTransaction v0.1` 是现有 `WorldStateDelta v0.1` 的事务外壳，不替换当前 delta schema；字段级事实源是 `shared/schemas/world_state_delta_transaction.v0.1.schema.json` 和 `tools/world_state/validate_world_delta_transaction.py`。
- `Generation Scheduler` 是跨管线调度控制面，不是内容校验器，也不是流水线末端产物。
- 任何世界状态变化都必须经过当前 `operations[]` 白名单、结构校验和语义校验；不得用通用 `effects[]` 绕过。

## 1. 当前事实源

当前事实源是 `develop` 分支的最新集成结果。`main` 只在稳定同步后作为发布 / 决策基线使用。

截至本索引更新时间，当前有效主线是：

```text
通用 AI 驱动塔防系统
  -> 玩家自然语言 / 世界书 / 战斗上下文
  -> 受控 AI 编译
  -> AssetGraph DAG / 有界 ReAct 节点
  -> Schema / 白名单 / 预算 / 语义门 / 媒体门禁
  -> 可玩资产、任务、事件、剧情节点、世界状态变化
  -> 前端 mock API 先用 reviewed fixture 跑完整 MVP 演示链路
```

《长夜灯火》只是 MVP 世界书模板，不是项目本体名称。

## 2. 先读顺序

新代理、新队友或评审应按以下顺序阅读：

1. `README.md`
   - 项目运行入口、后端 API、验证命令。
2. `docs/CURRENT_ARCHITECTURE_INDEX.md`
   - 当前文档导航和有效性说明。
3. `docs/PROJECT_ARCHITECTURE_AND_GOVERNANCE.md`
   - 产品定位、架构分层、协作治理基线。
4. `docs/AI_COMPILATION_SYSTEM_V0_1.md`
   - AI 编译系统总架构：Context Engine、Object Compiler、World Transaction System，以及作为横切控制面的 Generation Scheduler。
5. `docs/GENERATION_SCHEDULER_V0_1.md`
   - Generation Scheduler 的字段级计划包、延迟等级、fallback 和预生成边界。
6. `docs/DEMO_VERTICAL_SLICE.md`
   - MVP 演示主路径。
7. `docs/FRONTEND_MOCK_API_V0_1.md`
   - 当前前端应接入的 mock API。
8. `docs/FRONTEND_RUNTIME_MOCK_ART_KIT_V0_1.md`
   - 前端战斗运行时 mock 美术包：敌人、目标物、基础防御件、NPC 头像、地图 token 和程序化特效。
9. `docs/WORKER_TASK_PACK_V0_1.md`
   - CodeBuddy / OpenCode / Codex headless / 人类 worker 的可验证任务包格式。
10. `docs/MVP_REVIEW_HANDOFF_V0_1.md`
   - 当前审查交付入口。

## 3. 当前有效设计文档

### 产品与前端

- `docs/DEMO_VERTICAL_SLICE.md`
  - MVP 录屏和玩家体验主路径。
- `docs/FRONTEND_PRODUCT_AND_TECH_DECISION.md`
  - 前端产品形态和技术决策。
- `docs/FRONTEND_MOCK_API_V0_1.md`
  - 后端暴露给前端的稳定 mock API。
- `docs/FRONTEND_MOCK_PACK_V0_1.md`
  - 前端 mock 内容包说明。
- `docs/FRONTEND_RUNTIME_MOCK_ART_KIT_V0_1.md`
  - 开发者预编译的战斗运行时 mock 美术包说明。
- `docs/FRONTEND_VISUAL_RUNTIME_AUDIT_V0_1.md`
  - 前端战斗视觉运行态审计，记录 P0-M 程序化战场底座、防控制图 / 失败整图回退、静态视觉合约和截图环境缺口。

### AI 编译器与 AssetGraph

- `docs/AI_COMPILATION_SYSTEM_V0_1.md`
  - 当前 AI 编译总架构边界事实源。定义 Context Engine、Object Compiler、World Transaction System、Generation Scheduler，以及 CGOP、ContextPackage、FactEntry、WorldStateDelta / WorldStateDeltaTransaction 映射的 v0.1 边界。具体字段仍以 schema 和 semantic gate 为准。
- `docs/AI_ASSET_COMPILER_V0_1.md`
  - AI 资产编译器基础定位。
- `docs/ASSET_GRAPH_COMPILER_V0_1.md`
  - 当前 AssetGraph / DAG / 有界 ReAct / 媒体节点主设计。
- `docs/FREE_INPUT_CONTROLLED_COMPILATION_V0_1.md`
  - 自由输入如何进入受控编译。
- `docs/COMPILABLE_OBJECT_MODEL_V0_1.md`
  - 游戏中哪些对象可被 AI 编译。
- `docs/COMPILABLE_OBJECT_PLAN_V0_1.md`
  - 下一阶段可编译对象规划。
- `docs/GENERATION_SCHEDULER_V0_1.md`
  - 预生成调度计划包、延迟等级、fallback 与启用前复验边界。
- `docs/PROVIDER_OUTPUT_ENVELOPE_V0_1.md`
  - 真实 provider 调用后允许保存的脱敏安全信封：摘要、artifact refs、校验状态和 activation gate。
- `docs/PROVIDER_ARTIFACT_STAGING_V0_1.md`
  - ProviderOutputEnvelope 之后的本地候选 artifact 暂存层：只登记 review-only local refs、校验状态和 promotion gate，不声明 runtime-ready。
- `docs/GAMEPLAY_OBJECT_COMPILER_V0_1.md`
  - 玩法对象编译边界。
- `shared/schemas/context_package.v0.1.schema.json`
  - ContextPackage 字段级事实源：只做上下文装配和脱敏，不写世界状态。
- `shared/schemas/fact_entry.v0.1.schema.json`
  - FactEntry 字段级事实源：候选事实必须经 WorldStateDelta 提交后才是游戏事实。
- `shared/schemas/compiled_game_object_package.v0.1.schema.json`
  - CGOP 字段级事实源：可安装对象包，不携带完整世界书、长期记忆或可变实例状态。
- `shared/schemas/provider_output_envelope.v0.1.schema.json`
  - ProviderOutputEnvelope 字段级事实源：只保存脱敏 provider 调用摘要、本地 artifact refs、校验状态和 activation gate，不保存 prompt 正文、provider 响应正文、secret 或 runtime-ready 声明。
- `shared/schemas/provider_artifact_staging_manifest.v0.1.schema.json`
  - ProviderArtifactStagingManifest 字段级事实源：把 ProviderOutputEnvelope 中的本地 refs 转入 review-only staging，仍不写世界状态、不激活 runtime、不绕过 media / semantic / human review / promotion gate。

### 剧情、任务与世界状态

- `docs/CONTROLLED_NARRATIVE_WORLD_COMPILER_V0_1.md`
  - 剧情 / 世界生长如何受控服务玩法。
- `docs/NARRATIVE_GAMEPLAY_CONTRACT_V0_1.md`
  - 叙事节点和玩法输出之间的合同。
- `docs/WORLD_STATE_DELTA_SEMANTIC_GATE_V0_1.md`
  - WorldStateDelta 语义门。
- `docs/MVP_WORLD_STATE_DELTA_REVIEW_PACK_V0_1.md`
  - MVP 世界状态变化审查包。

### 媒体素材

- `docs/MEDIA_ASSET_QUALITY_PIPELINE_V0_2.md`
  - 图片生成、后处理、审查、修复和运行时就绪门禁。
- `docs/VIDEO_FRAME_ASSET_PIPELINE_V0_1.md`
  - 图片种子 -> 图生视频 -> 关键帧 -> 循环连续性检查 -> 批量后处理 -> atlas 的路线。

当前状态：

```text
processed PNG 已可用于前端 mock。
animation seed 已可用于后续图生视频。
frontend_runtime_mock 已作为战斗运行时美术包入口，覆盖敌人、目标物、基础防御件、NPC 头像、地图 token 和程序化特效。
MapRuntimePackage v0.1 已作为三张 MVP 战斗节点运行时地图包入口，包含路径、塔位、目标、出生点和带质量状态的本地视觉层引用。
循环动画策略已确认：优先首尾同图 / end frame 控制，否则通过 seamless loop prompt 与 LoopContinuityCheck 修复。
MediaAtlasManifest v0.1 已作为 spritesheet 多帧入口接入前端、后端 mock API 和 demo evidence；实体 atlas PNG 已由确定性 frame sequence 打包生成，真实图生视频关键帧仍未生成。
Sprite cutout quality report 已接入 demo evidence，用于标记内部透明洞、主体碎裂和边缘接触等需复核素材；当前报告只排序修复工作，不阻断玩家侧 MVP。
Sprite cutout repair plan 已从质量报告派生，列出需要重抠图、重生成或人工复核的素材任务，作为下一轮素材重生的输入。
Sprite repair candidate pack 已可从 repair plan 生成 review-only PNG，并再次经过 cutout quality audit；候选不会自动替换正式 runtime 素材。
Sprite live regeneration candidate pack 已可针对 runtime 素材调用 Agnes 生成 review-only 候选，并支持单素材迭代、复用 raw 后处理和最大主体保留；当前候选覆盖信标、基础灯栏与驿站核心，候选仍不自动替换正式 runtime 素材。
Sprite regeneration promotion report 已记录 runtime 候选的显式晋升；信标、基础灯栏与驿站核心已替换 runtime processed PNG 并重建 atlas，runtime sprite cutout quality 已达到 `passed 7 / 7`，repair plan 已清空。
MapVisualQualityReport v0.1 已接入 demo evidence，用于标记共享玩家底图、overlay correction 和视觉审查证据不足；当前结果是 `passed_with_warnings`，说明 MVP 可演示但仍需要多节点差异化发布底图。
NodeMapPaintedCandidateReview v0.2 已接入 demo evidence，用于记录三张节点专属 Agnes 地图候选的人工审查结论；当前 `clean_scene_v2` 结果为 `review_only_alignment_required`，说明候选图已经清除了上一轮主要的箭头、单位和战斗特效问题，但仍必须经过坐标对齐、可读性复核和显式晋升，不能自动更新 MapRuntimePackage 或玩家侧发布底图。
MapCandidateAlignmentReview v0.1 已接入 demo evidence，用于把 `clean_scene_v2` 候选图与 MapRuntimePackage 的路径、塔位、目标和出生点做结构对齐前置审查；当前结果为 `ready_for_overlay_review_with_transform_required`，说明三张图都具备进入 overlay review 的结构前提，但必须先从 Agnes 返回尺寸标准化到请求尺寸，再显式晋升。
MapCandidateOverlayReview v0.1 已接入 demo evidence，用纯 Python 把三张 `clean_scene_v2` 候选标准化为 `1280x720`，并生成带路径、塔位、出生点和目标叠层的 SVG 审查图；当前结果为 `overlay_artifacts_ready_review_required`。这些 PNG/SVG 仍是 review-only，不会被前端 runtime 默认消费，且 artifact ready 不等于视觉对齐已批准。
MapCandidateOverlayVisualReview v0.1 已接入 demo evidence，用 raster overlay PNG 做人工视觉复核；当前结果为 `needs_layout_reconciliation`，三张候选均 `do_not_promote`。主要问题是 runtime 路线、核心目标和塔位与画面中的道路、目标物、建造点还未完全一致。下一步应做 runtime 坐标/路径重投影，或用更强拓扑约束重生地图。
MapLayoutReconciliationPlan v0.1 已接入 demo evidence，把 overlay 视觉复核转成三类 P0 后续动作：灰灯驿站采用 `hybrid_reproject_then_review`，灯芯仓采用 `runtime_path_reprojection`，旧信号塔优先 `topology_constrained_regeneration_preferred`。该计划不修改 runtime 包，也不晋升视觉层，只作为下一轮布局修订任务输入。
RuntimeMapPatchCandidates v0.1 已接入 demo evidence，为灰灯驿站和灯芯仓产出 review-only 坐标/路径/塔位补丁候选，旧信号塔因拓扑冲突跳过补丁并转入拓扑约束重生。
MapPatchOverlayReview v0.1 已接入 demo evidence，会把 runtime 补丁候选应用到内存 MapRuntimePackage 快照，生成补丁后 overlay PNG/SVG 与 review-only runtime 快照；当前灰灯驿站和灯芯仓的补丁后 MapRuntimePackage 校验通过，但仍需视觉复核和显式 promotion report，不能自动替换正式 MapRuntimePackage 或发布底图。
TopologyConstrainedMapPromptPack v0.1 已接入 demo evidence，包含旧信号塔主重生 prompt，以及灰灯驿站、灯芯仓的 fallback prompt。它不直接修改 MapRuntimePackage 或发布视觉层。
TopologyConstrainedMapCandidateReview v0.1、TopologyConstrainedMapAlignmentReview v0.1、TopologyConstrainedMapOverlayReview v0.1 与 TopologyConstrainedMapOverlayVisualReview v0.1 已接入 demo evidence，记录旧信号塔基于真实 Agnes 调用生成的一张拓扑约束候选。该候选比上一轮更接近右入左出的路径拓扑并有更清楚的建造空地，但仍存在塔体过大和小人/杂物感噪声，当前 `do_not_promote`，只能作为下一轮 prompt 修复输入。
TopologyConstrainedMapPromptPack v0.2 已把上述失败原因转成确定性 prompt repair；但 Agnes v2 仍生成多塔/人物感噪声，被记录为 `review_only_not_runtime_ready`。这说明下一轮不应继续盲目 prompt-only 抽图，而应引入控制图、参考构图、局部清理或视觉模型审查。
MapTopologyControlSketchPack v0.1 已接入 demo evidence，会从现有 MapRuntimePackage 确定性生成无文字、无 UI、无敌人、无塔的 `1280x720` topology control PNG，以及带开发者标签的 SVG 审查图。该包是 compile-time reference / evidence，不是玩家可见地图层；下一步应把它作为图像 provider 参考图、人工 paintover 输入或局部清理输入，再重新走 candidate / alignment / overlay / visual / promotion gates。
MapControlledRegenerationRequestPack v0.1 已把三张 topology control sketch、v0.2 prompt repair、负面约束、目标候选目录和后续 gate 编译成统一的 reference-image request。它不调用 provider、不发布图层；下一步真实图像生成或人工 paintover 应消费该 request pack，而不是从散落 prompt 或截图临时拼输入。
ControlledMapCandidateGenerationRun v0.1 已提供 `tools/media/generate_controlled_map_candidates.py` 入口，默认 `reference-image` handoff 模式会从 request pack 生成三张 review-only sidecar，不调用 provider、不伪造图片；`text-fallback` 模式可在显式 `--live` 时走当前 OpenAI-compatible 图像接口，但产物仍必须重新过 review/alignment/overlay/visual/promotion gates。
ControlledMapCandidateReview v0.1 已把上述 handoff sidecar 接入 `tools/media/build_node_map_candidate_review_pack.py`，当前审查状态为 `review_only_not_runtime_ready`，三个候选均 `awaiting_provider_or_paintover_output`。这证明受控候选已经进入统一候选审查门，但在真实 provider 或人工 paintover 产出图片前不会进入 alignment / runtime promotion。
ControlledMapTextFallbackGenerationRun v0.1 已用真实 Agnes 调用产出三张受控 text-fallback 地图候选，并记录 provider 调用数、图片路径和 sidecar；审查结果为 `review_only_not_runtime_ready`，三张均 `needs_regeneration`。失败原因包括箭头 / 控制形状 / 棋盘边框被烙进背景、未授权人物或塔位被模型自行添加、视觉路线与 MapRuntimePackage 拓扑不一致。该结果冻结为负样本证据：地图不应继续依赖纯文本整图生成，下一轮应走 reference-image provider、人工 paintover，或由 MapRuntimePackage 驱动的分层程序化底图。
FrontendProceduralBattleBackdrop v0.1 已完成 P0-M：默认玩家战斗画面不再绘制失败整图候选，而是由 `MapRuntimePackage` 的 grid、path_routes、build_slots、objectives 和 spawn_points 驱动 canvas 程序化绘制自然地形、土石路、部署基座、目标地基和入口雾潮。静态合约会阻止控制图 / 参考图 / 棋盘 helper / 失败整图发布进入默认玩家视图；仍需浏览器截图或录屏做最终像素验收。
GenerationSchedulePlan v0.1 已作为 Generation Scheduler 的 review-only 计划包入口，覆盖 sync_blocking、background_prefetch、background、lazy、fallback_static 五类调度，并接入 demo evidence 与后端 session mock API；GenerationScheduleRunReport v0.1 已可离线 dry-run 调度计划并证明 provider 调用数和世界修改数为 0；`generation_schedule_queue_items` 已能提供 item 级队列视图、claim / complete / fail / retry / fallback 状态流转、attempt 预算和 dry-run worker step；`generation_schedule_worker_cache` 已提供 review-only worker step 执行痕迹；`generation_live_executor_guard.v0.1` provider guard log 已能记录真实 provider 执行前的显式授权阻断、artifact manifest 门、校验门和 activation gate；`ProviderOutputEnvelope v0.1` 已定义真实 provider 调用后允许保存的脱敏摘要和 artifact refs；`ProviderArtifactStagingManifest v0.1` 已定义这些本地 refs 进入 review-only 暂存区的清单和 promotion gate，并接入 demo evidence 摘要；两者都不保存 raw prompt / provider response、不写世界状态、不激活候选，真实后台执行器仍未实现。
ContextPackage v0.1、FactEntry v0.1、CompiledGameObjectPackage v0.1 已有 schema、最小示例和统一 validator；Research Job proposal / job metadata、battle settlement evidence 与 frontend mock pack 已携带 ContextPackage、FactEntry、CGOP 原生快照，并保留 core artifact refs / world delta 兼容字段。
```

### 审查与交付

- `docs/MVP_REVIEW_HANDOFF_V0_1.md`
  - 一键审查入口。
- `docs/WORKER_TASK_PACK_V0_1.md`
  - WorkerTaskPack v0.1 任务包协议，约束 worker 的必读事实源、允许修改范围、安全规则、验收命令和汇报格式。
- `docs/MVP_COMPILER_REVIEW_DOSSIER_V0_1.md`
  - 总审查交付包说明。
- `docs/MULTISTAGE_CONTENT_PACK_V0_1.md`
  - 多阶段内容包。
- `docs/STAGE_CANDIDATE_PACK_V0_1.md`
  - 阶段候选包。
- `docs/MVP_NARRATIVE_ASSET_REVIEW_PACK_V0_1.md`
  - 叙事资产审查包。
- `docs/MVP_STORY_ASSET_PROMOTION_REPORT_V0_1.md`
  - 剧情资产晋级报告。

### Provider 与真实调用

- `docs/AI_PROVIDER_RESEARCH_AND_SMOKE_TEST.md`
  - 方舟、DeepSeek、GLM、Agnes 等 provider 调研和烟测记录。
- `docs/LIVE_LLM_WORLD_DELTA_SMOKE_TEST_V0_1.md`
  - 真实 LLM 世界状态变化烟测。
- `docs/AI_COMPILER_ITERATION_LOG.md`
  - AI 编译器多轮迭代记录。

## 4. 当前实现事实

当前已实现或已落地的事实：

- FastAPI + SQLite 后端。
- 匿名 session，不做真实注册登录。
- Research proposal / job API。
- Frontend mock API。
- 前端 mock 内容包：11 个可玩资产、3 个阶段摘要、3 个 runtime package 摘要。
- 战斗配置与 reviewed runtime package：三张 MVP 战斗节点均由 `backend/app/services/battle_content_service.py` 作为后端加载入口。
- Agnes 生成的 22 张当前资产图片。
- processed 透明 PNG 媒体包。
- animation seed manifest。
- 前端运行时 mock 美术包：敌人、目标物、基础防御件、NPC 头像、地图 token、程序化特效与独立媒体 manifest；`backend/app/services/frontend_media_service.py` 是当前后端加载入口。
- MapRuntimePackage v0.1：三张 MVP 战斗节点已有结构化运行时地图包，包含路径、塔位、目标、出生点和本地视觉层引用；`backend/app/services/map_runtime_service.py` 是当前后端加载入口。
- MapCompilePackage v0.2：三个 MVP 战斗节点已有地图编译证据包，区分逻辑层、控制层、玩家可见渲染层、坐标回配和质量门。
- 地图视觉层：玩家默认只消费 `authority=published_visual_layer` 且 `player_visible_quality=passed` 的图层；`agnes_02` 与 `battle_runtime_background.v0.2` 已降为失败/候选证据，控制图和参考图只用于 debug / evidence。
- 地图视觉质量审计：`tools/media/audit_map_visual_quality.py` 与 `examples/review_packs/map_visual_quality_report.v0.1.json` 已记录当前三节点共享同一玩家底图、发布底图需 overlay correction、审查证据偏弱；该报告是 P1-D 地图重生和差异化底图任务的输入。
- 节点专属地图候选生成与审查：`tools/media/generate_node_map_painted_candidates.py` 可基于战斗配置生成 review-only 地图候选或只刷新 sidecar，并支持 `clean_scene_v2` prompt profile；`tools/media/build_node_map_candidate_review_pack.py` 与 `examples/review_packs/node_map_painted_candidate_review.v0.2.json` 记录当前三张真实 Agnes 候选的质量结论。候选不会自动发布，当前三张进入 alignment review，而不是直接晋升 runtime。
- 地图候选对齐审查：`tools/media/build_map_candidate_alignment_review.py` 与 `examples/review_packs/map_candidate_alignment_review.v0.1.json` 已证明三张 `clean_scene_v2` 候选均能对应到 runtime package 的路径、塔位、目标与出生点，并记录 Agnes 实际返回 `1312x736`、请求尺寸 `1280x720` 的差异。下一步应做尺寸标准化、overlay 截图和显式晋升，而不是继续盲目生成。
- 地图候选标准化与 overlay 审查：`tools/media/build_map_candidate_overlay_review.py`、`examples/review_packs/map_candidate_overlay_review.v0.1.json` 和 `game_data/media/map_visual_reference/node_candidates_v2_normalized/` 已生成三张 `1280x720` normalized PNG 与对应 SVG overlay。下一步应进行人工或视觉模型 overlay 复核，并只通过显式 promotion report 更新 published visual layer。
- 地图候选视觉复核：`tools/media/build_map_candidate_overlay_visual_review.py` 与 `examples/review_packs/map_candidate_overlay_visual_review.v0.1.json` 已记录 raster overlay 人工复核结论。当前可晋升数为 0，说明这批图适合作为地图编译管线证据和布局修订输入，但不适合作为前端默认战斗底图。
- 地图布局修订计划：`tools/media/build_map_layout_reconciliation_plan.py` 与 `examples/review_packs/map_layout_reconciliation_plan.v0.1.json` 已把每个节点拆成可执行后续动作、验收门和 fallback。下一轮应基于该计划产出 runtime patch candidate 或 topology-constrained regeneration prompt，而不是继续泛化生成地图。
- 地图补丁、补丁后 overlay、拓扑重生、控制图、受控重生请求、候选 dry-run 与候选审查：`tools/media/build_runtime_map_patch_candidates.py`、`tools/media/build_map_patch_overlay_review.py`、`tools/media/build_topology_constrained_map_prompt_pack.py`、`tools/media/generate_topology_constrained_map_candidates.py`、`tools/media/build_map_topology_control_sketch_pack.py`、`tools/media/build_map_controlled_regeneration_request_pack.py`、`tools/media/generate_controlled_map_candidates.py`、`tools/media/build_node_map_candidate_review_pack.py` 与对应 `examples/review_packs/*.json` 已把布局修订计划拆成 review-only runtime 补丁、补丁后 overlay 复核、旧信号塔拓扑约束重生证据、三节点 topology control sketch、三节点 reference-image request、三节点 handoff sidecar 和受控候选审查。text-fallback live 已形成负样本，下一步应接入支持参考图的 provider、人工 paintover，或实现 MapRuntimePackage 驱动的分层程序化底图，再重新走 review/alignment/overlay/visual gate。
- 地图 text-fallback 真实生成负样本：`examples/review_packs/controlled_map_text_fallback_generation_run.v0.1.json` 记录了三次真实 Agnes 图像调用，`examples/review_packs/controlled_map_text_fallback_candidate_review.v0.1.json` 把三张候选全部阻断为 `needs_regeneration`。该负样本不进入 alignment / overlay / frontend runtime，是下一步地图编译改造的决策依据。
- 前端默认战斗底座：`frontend/app.js` 当前用 `drawProceduralTerrain()`、`drawPath()`、`drawDeploymentBase()`、`drawTargetFoundation()` 和 `drawSpawnRift()` 从 `MapRuntimePackage` 稳定生成玩家默认战场画面；整张 map image 只保留为 future published layer / debug evidence 语义，不进入默认 preload 或 `drawBackdrop()`。`tools/frontend/validate_battle_visual_contract.py` 已把这一点纳入静态合约。
- GenerationSchedulePlan v0.1 / GenerationScheduleRunReport v0.1：已有 review-only 计划包、dry-run 执行报告、schema、builder、validator、evidence 摘要、`GET /api/sessions/{session_id}/generation-schedule` session API、`generation_schedule_runs` 持久化 dry-run 运行记录，以及 `generation_schedule_queue_items` item 级队列视图、状态流转、attempt 预算、retry / fallback 和 dry-run worker step，用于声明并离线验证同步、预取、后台、懒加载和静态 fallback 内容。
- Generation Scheduler 后端状态层：`backend/app/services/generation_scheduler_service.py` 是当前 session 缓冲、dry-run run、队列状态流转、attempt 预算、retry / fallback、dry-run worker step、review-only worker cache 和 live executor guard 的实现入口；`frontend_mock_service.py` 只聚合玩家侧 fixture 与 evidence。
- ProviderOutputEnvelope v0.1：`shared/schemas/provider_output_envelope.v0.1.schema.json`、`tools/dev/validate_provider_output_envelope.py`、`docs/PROVIDER_OUTPUT_ENVELOPE_V0_1.md` 和 `examples/provider_output_envelopes/` 已作为真实 provider 输出安全信封入口。后续真实 executor 只能保存 redacted summary、本地 artifact refs、validation 状态和 activation gate，不能保存 prompt 正文、provider 响应正文或 runtime-ready 声明。
- ProviderArtifactStagingManifest v0.1：`shared/schemas/provider_artifact_staging_manifest.v0.1.schema.json`、`tools/dev/validate_provider_artifact_staging_manifest.py`、`docs/PROVIDER_ARTIFACT_STAGING_V0_1.md` 和 `examples/provider_artifact_staging/` 已作为 ProviderOutputEnvelope 后的本地候选 artifact 暂存入口。它只登记 review-only local refs、gate 状态和 promotion 阻断，不能替代 runtime package、WorldStateDeltaTransaction、media gate 或人工 review。
- WorkerTaskPack v0.1：`shared/schemas/worker_task_pack.v0.1.schema.json`、`tools/dev/validate_worker_task_pack.py`、`docs/WORKER_TASK_PACK_V0_1.md` 和 `examples/worker_task_packs/` 已作为 worker 委派任务包入口。后续 CodeBuddy / OpenCode / Codex headless / 人类 worker 的任务应先声明必读事实源、允许路径、禁止路径、安全规则、provider policy、验收命令和汇报字段。
- Campaign Router v0.1：`backend/app/services/campaign_router_service.py` 是当前最薄运行时游标入口；它根据 `RunWorldState.progress.phase` 返回当前节点、下一节点、前视窗口、已审资产 handle 和 scheduler 信号，并可触发一次 fixture-backed dry-run 预取步。no-build 前端已在 API 模式消费该 route，静态模式保留灰灯驿站首战兜底。
- 多节点战斗结算桥：`backend/app/services/frontend_mock_service.py` 当前支持 `gray_lantern_station`、`lamp_wick_store`、`old_signal_tower` 三个路由节点的战斗结果提交。前两个节点使用 `battle_result` transaction；`old_signal_tower` 使用 stage06 `research_job` after-state 作为 `fixture_bridge`，并在 API 返回中显式标注来源，避免把研究任务基线误当战斗结果。
- AI 编译核心对象 schema：ContextPackage v0.1、FactEntry v0.1、CompiledGameObjectPackage v0.1 已有 schema、示例和统一 validator；`backend/app/services/ai_core_artifact_service.py` 是当前后端 refs / 示例加载入口，也是 Research Job proposal / job metadata 与 battle settlement evidence 原生快照构造入口。
- WorldStateDeltaTransaction v0.1：已有 schema、首战 committed 示例、stage01-stage07 事务链、批量 validator 和 deterministic builder；它包装可通过语义门的 `WorldStateDelta`，并接入 demo evidence。
- AssetGraph workflow、节点注册表、runtime package 构建与校验。
- 多阶段叙事 / 世界状态 / 资产候选审查包。
- MVP handoff audit 一键验证。
- 演示证据导出脚本：可生成 `summary.md / evidence.json / index.html`。
- Runtime sprite live regeneration 候选：已为信标、基础灯栏与驿站核心生成 review-only PNG，并接入 cutout quality report 与 demo evidence。
- Runtime sprite 显式晋升：已把通过审查的信标、基础灯栏与驿站核心候选晋升到 published runtime media，重建 runtime atlas，并接入 promotion report。
- 前端 MVP 页面：已有本地可运行 mock 体验入口，仍需浏览器环境补截图和视觉验收。

当前尚未完成：

- 真实图生视频帧序列，以及用真实关键帧替换当前确定性 frame sequence 的默认接入。
- WorldStateDelta / review pack 与 ContextPackage、FactEntry、CGOP 字段的全面迁移；Research Job、battle settlement evidence、多节点 battle settlement、frontend mock pack 和 stage01-stage07 WorldStateDeltaTransaction 链已完成第一层原生快照 / 事务迁移，但其他运行时产物仍未全部改为原生核心对象。
- 正式 Generation Scheduler 后台执行器、真实 provider 调度、跨请求缓存和持久化预生成产物；当前 Campaign Router 只触发 dry-run 预取，不是真实后台执行器。
- 多世界书选择与长期存档系统。
- 自动化浏览器截图 / Playwright 视觉回归。

## 5. 历史文档处理规则

早期文档不直接删除，因为它们包含决策来源和演化过程。但使用时必须区分：

- `当前有效`：可以作为实现依据。
- `实现参考`：方向有效，但字段或流程可能已被更新。
- `审查证据`：用于证明某次流水线产物，不一定是运行时接口。
- `历史记录`：只说明当时讨论背景，不作为实现依据。

若旧文档中出现以下说法，应以当前索引和最新对应文档为准：

- “候选默认 3 个”：当前玩家侧默认 1 个方案，更多候选由 NPC、材料、技术或提示条件解锁。
- “前端直接读 JSON”：当前前端优先走后端 mock API。
- “图片直接作为游戏资产”：当前图片必须进入媒体后处理和 published manifest；视频帧路线另见 `VIDEO_FRAME_ASSET_PIPELINE_V0_1.md`。
- “长夜灯火是项目名”：当前项目本体是通用 AI 编译塔防系统，`long_night_lanterns` 是 MVP 世界书。

## 6. 协作分支规则

- `main`：稳定决策 / 发布基线，只在阶段性冻结窗口从 `develop` 受控同步。
- `develop`：当前集成事实源。
- `task/*` worktree：CodeBuddy / OpenCode / Codex headless 等代理执行任务。

主聊天可以讨论和决策；具体实现应优先进入 `develop` 派生的 task worktree，验收后合回 `develop`。稳定后再统一同步到 `main`。

`main` 允许短期落后于讨论和 `develop`，但这种落后应是受控滞后。同步前必须先检查 `main` 是否存在未识别的用户改动，并确认本次同步范围；不得为了追平文档而覆盖用户草稿。

当前 main 同步准备清单见：

- `docs/MAIN_SYNC_PLAN_2026_07_02.md`
