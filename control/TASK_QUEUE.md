# 任务队列

Last updated: 2026-07-07

本文是交付给本地 worker、自动化执行器和人工审查环节的当前任务来源。

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
- `ControlledMapCandidateArtifactImportReport v0.1` 已补本地 PNG 导入边界：默认示例为三张候选 `awaiting_local_artifacts`，不复制图片；后续人工 paintover 或 reference-image provider runner 下载本地 PNG 后，必须通过该 import plan / validator / `--copy-files` 显式进入 `node_candidates_controlled_v1` 候选槽，并保持 review-only、promotion blocked。
- `ControlledMapCandidateReview v0.1` 已把上述 sidecar 纳入 `build_node_map_candidate_review_pack.py`。当前三个受控候选都被审查为 `awaiting_provider_or_paintover_output`，整体 `review_only_not_runtime_ready`；这证明链路接上了，但在真实图片产出前不会进入 alignment 或晋升。
- `ControlledMapTextFallbackGenerationRun v0.1` 已完成一次真实 Agnes text-fallback 生成，三张图片均有 sidecar 和审查记录；`ControlledMapTextFallbackCandidateReview v0.1` 已全部判定为 `needs_regeneration`，整体 `review_only_not_runtime_ready`。结论是纯文本整图生成会把箭头、控制形状、未授权人物 / 塔位和错误路线烙进背景，不适合作为玩家 runtime 地图底图。后续地图任务应优先改为 reference-image / paintover / MapRuntimePackage 驱动的分层程序化底图。
- `MapVisualPromotionGateReport v0.1` 已接入 evidence，用确定性规则交叉检查 review-only / do_not_promote / needs_regeneration / awaiting provider 的地图候选是否被误挂到玩家侧 `published_visual_layer`。当前阻断候选 22 个、published 玩家图层 4 个、违规 0 个；这证明差图已被隔离为负样本证据，但不代表地图美术质量已完成。
- 前端战斗地图视觉底座已完成 P0-M 到 P1-D v0.5 改造：默认玩家战斗画面不再预加载或绘制失败整图候选，而是由 `MapRuntimePackage` 驱动 canvas 程序化绘制地形、场外地貌背板、可玩区碎边、道路地形融合、平滑土路、路肩、车辙、部署基座、塔位接地线、目标地标、入口雾潮、暗潮洼地、可玩地块边界、可部署台地、路线方向 cue、目标防御区和世界内废墟 / 补给 / 灯具地标；投影已按 runtime bounds 与 HUD safe area 做 contain fit，移动端不再只看到被裁切的局部路段；静态视觉合约已检查控制图隔离、失败图不得发布、棋盘 helper 不得回归、路径 / 塔位 / 目标 / 出生点仍来自结构化地图包。
- 前端战斗地图已经消费 `map_render_plan_bundle` / `MapStylePack` 的表现层颜色，并读取 `ProceduralMapRenderPlan` 的道路宽度、路肩宽度和部署基座 footprint 等表现层几何参数；`MapRuntimePackage` 仍是路径、塔位、目标、出生点和碰撞事实源。
- 地图 RenderPlan 已有离线 SVG 预览入口和 report 校验，三张 MVP 地图均可生成 `preview_ready_review_only` 的审查预览；该预览证明 RenderPlan 可执行，但不作为玩家 runtime 或 published visual layer。
- MapRuntimePackage v0.2 的强语义 preview 已接入 RenderPlan 旁路预览：`examples/map_render_plans_v02/`、`examples/semantic_visual_consistency_reports_v02/` 和 `examples/map_render_previews_v02/` 会用结构化资源点、机关区、防守锚点和阻挡区生成 review-only evidence；统一 demo evidence 会展示 `procedural_map_previews_v02`，但前端/后端默认 runtime 仍使用 v0.1。
- 后端已提供 review-only v0.2 地图预览接口：`GET /api/sessions/{session_id}/battles/{node_id}/map-v02-preview` 会聚合 `MapRuntimePackage v0.2 preview`、v0.2 RenderPlan bundle、语义一致性报告、preview report 和 SVG ref；该接口仅供审查 / Studio / 录屏证据使用，不替换默认 `/map-runtime-package` 的 v0.1 玩家运行时包。
- 后端 v0.2 地图预览 API 已有 TestClient smoke 证据：`tools/dev/check_map_v02_preview_api.py` 会创建匿名 session 并请求三张节点的 `/map-v02-preview`，生成 `examples/review_packs/map_v02_preview_api_smoke_report.v0.1.json`；统一 demo evidence 会展示该接口 smoke 摘要。
- MapRuntimePackage v0.2 强语义几何一致性 report 已接入 review-only evidence：新增 `map_runtime_v02_semantic_geometry_report.v0.1` schema / builder / validator，默认读取 `examples/map_runtime_packages_v02/*.json`，只复用 `map_path_geometry.py` 的连续路线 / road band 距离逻辑检查资源点、机关区、防守锚点和阻挡区相对 grid、路线、塔位、目标、出生点、资源与阻挡的几何关系；当前报告状态为 `passed_with_warnings`，旧信号塔资源点贴近派生 road band，但没有 blocking resource / 阻挡区 / 塔位 / 目标 / 出生点硬冲突。该报告不修改 runtime package，不调用 provider，不读 `.env` / 图片 / preview，`runtime_effect=false`、`provider_call_count=0`、`default_runtime_mutation=false`，并已纳入 `tools/demo/export_evidence.py` 验证摘要。
- MapPublishedVisualLayerAlignment v0.1 已把确定性逻辑对齐的 `battle_runtime_background.v0.2` 晋升为玩家可用 `published_visual_layer` fallback，旧 `painted_visual_layer` 保留为 `candidate_visual_layer` / `superseded_requires_overlay_correction` 证据。当前 map visual quality 不再报告 overlay correction blocker，只保留共享底图和非节点专属图层 warning。
- MapRuntimePromotionReadinessReport v0.1 已作为地图 runtime 晋升读模型接入 demo evidence：三张节点均为 `promotion_candidate_activation_required`，说明 v0.2 强语义、RenderPlan 和语义一致性已经具备候选条件，但 activation allowed 仍为 0，且 review-only/拒绝候选隔离仍是 blocker。后续若要切换玩家默认地图语义，必须另开独立 activation / API / 前端 / 截图验收任务，不能直接从 readiness report 修改 runtime。
- MapRuntimeActivationAuthorizationReport v0.1 已作为地图 runtime 激活授权记录层接入 demo evidence：默认状态 `pending_developer_approval`，三张节点均有记录但未批准，且 provider / runtime / backend / frontend / world 修改数均为 0。它不是激活命令，只是 activation gate 的输入。
- MapRuntimeV02OptInContractSmokeReport v0.1 已作为地图 runtime v0.2 opt-in dry-run 合同证据接入 demo evidence：默认 API 仍 pending 且不返回完整 v0.2 包，临时 approved 授权夹具会在 service 层证明 v0.2 候选包可读，并证明 developer-approved selector 会一致选择 v0.2；默认 `/config`、`/runtime-package`、`/map-runtime-package` 仍保持 v0.1 且 v0.2 字段泄漏为 0。
- MapRuntimeActivationGateReport v0.1 已作为地图 runtime 显式激活门接入 demo evidence：三张节点当前 activation decision 均为 `blocked`，允许数为 0；前端 v0.2 强语义消费合同和后端 developer-approved selector 合同已标记为 `pre_activation_ready`，但阻断项仍包括显式开发者激活授权未批准、review-only/拒绝候选隔离和激活后证据复跑。它证明 v0.2 强语义是候选而非默认运行时，后续任务不得绕过该 gate 直接修改 `examples/map_runtime_packages/`、后端默认接口或前端默认地图。
- MapRuntimeV02ActivationContractPlan v0.1 已作为地图 runtime v0.2 激活前合同计划层接入 demo evidence：它读取 activation gate、authorization、opt-in smoke、promotion readiness、v0.2 API smoke、前端消费合同和后端 selector 合同，列出正式激活前的预接入状态和复跑证据命令；当前 `contract_plan_status=not_applied`、`activation_allowed_count=0`、`activation_apply_now_count=0`，后端 selector 3 项为 `pre_activation_ready`、后端未完成数为 0，前端 2 项为 `pre_activation_ready`、1 项为 `post_activation_evidence_required`，且默认 runtime / backend API / frontend 合同修改均为 false。
- MapDecorationZonePolicy v0.1 已把外部地图编译方案中的 DecorationZoneMap 思路压缩为 review-only renderer helper：默认读取三张 `MapRuntimePackage v0.1` 与三张 `MapRuntimePackage v0.2 preview`，从结构化路径、塔位、目标、出生点、资源点、机关、防守锚点和阻挡区派生强语义保护区、弱语义附着区、纯装饰区和氛围层遮挡约束。该策略不调用 provider、不读取 `.env`、不从图片 / SVG / preview 反推逻辑、不修改 runtime 包，也不绕过 v0.2 activation gate。
- MapDecorationZonePolicy v0.1 已纳入统一 demo evidence：`tools/demo/export_evidence.py` 会把策略摘要写入 `assets_and_media.map_visual_reference.map_decoration_zone_policy`，在 `summary.md` / `index.html` 中展示地图数、强语义保护区、可装饰区和安全边界，并在 full validation 中运行独立 validator；`tools/dev/run_fast_quality_gate.py` 也会快速校验该策略。该接入只提高演示可见性，不新增 MVP readiness 必需 gate。
- RenderPlan 离线预览已只读消费 MapDecorationZonePolicy：`render_procedural_map_preview.py` 默认读取策略并在 review-only SVG 中生成 `decoration-policy-layer`，report 记录 consumed / map_id / zone counts / drawn item count / runtime boundary；`validate_procedural_map_preview_report.py` 会校验策略文件、SVG 层存在和 `runtime_fact_source=false` / `may_modify_map_runtime_package=false` / `provider_call_count=0`。该层只提高离线审查画面自然度，不修改玩家 runtime、后端接口、MapRuntimePackage 或 readiness gate。
- 前端战斗画面已补 MapRuntimePackage v0.2 强语义消费能力：当被激活的默认地图运行包携带 `resource_nodes`、`hazard_zones`、`defense_anchors`、`blocked_areas` 时，玩家战场会从结构化 runtime 字段绘制资源点、沿路线绑定的机关区、防守锚点和阻挡物；默认前端仍不得请求 `map-v02-preview` 或 `map-v02-opt-in-dry-run`，当前正式 runtime 仍保持 v0.1。
- MVP 玩家主流程 API 已有本地 HTTP smoke 证据：`tools/dev/check_mvp_primary_api_flow.py` 会启动临时 `uvicorn` 和临时 SQLite，走通匿名 session、世界实例、开场、大地图、campaign router、研发 proposal/job、战斗配置、runtime package、地图包、战斗结算和 session evidence，生成 `examples/review_packs/mvp_primary_api_flow_smoke_report.v0.1.json`；统一 demo evidence 会展示该主流程 smoke 摘要。
- MVP 演示 readiness 已有顶层聚合报告：`tools/demo/build_mvp_demo_readiness_report.py` 会读取已审 evidence，生成 `examples/review_packs/mvp_demo_readiness_report.v0.1.json`；`tools/demo/validate_mvp_demo_readiness_report.py` 会独立复算 gate 顺序、必需 gate 数、阻断 / warning / expected block、source file 数、安全计数和整体状态，并已接入 `tools/demo/export_evidence.py` 静态验证。当前结论为 `ready_for_mvp_demo_with_known_limitations`：主流程、v0.2 地图预览 API、v0.2 强语义几何审查、v0.2 激活合同门、核心对象对齐、地图视觉发布安全、前端战斗视觉合同、运行时 sprite 几何质量、Generation Scheduler review-only 调度、视频 provider 离线边界和失败地图候选隔离均纳入门禁/证据；地图美术质量、v0.2 默认 runtime 激活、真实图生视频关键帧和实时 provider 调度仍作为已知限制保留。`map_runtime_v02_semantic_geometry` 是 MVP 必需 warning gate，证明 v0.2 preview 的资源点、机关区、防守锚点和阻挡区已通过结构化几何审查；`battle_visual_contract` 是 MVP 必需 gate，证明默认战斗画面仍是全屏 MapRuntimePackage 驱动的程序化战场，不回退控制图、失败整图、棋盘或虚线调试画面；`generation_scheduler_review_only` 是 MVP 必需 gate，证明同步内容、后台预取、后台增强、懒加载和静态兜底都已有 review-only 调度计划和 dry-run 运行证据；`frontend_flow_visual_smoke_harness` 默认以 `harness_only` 模式证明浏览器截图工具可用，录屏前通过 `--frontend-flow-smoke-report` 可升级为消费真实 14 张截图的 `actual_report` 模式；`map_runtime_activation_contract` 和 `provider_video_boundary` 都是非必需 warning gate，前者证明前端已预接入但 runtime 仍未激活，后者证明 dry boundary / receipt / envelope / handoff 模板可见且不调用 provider。
- 已补浏览器视觉烟测入口 `tools/frontend/capture_battle_visual_smoke.py`：打开 `frontend/index.html?static=1&battleVisualSmoke=1`，采集桌面与移动视口截图并输出 JSON 证据。本轮已通过临时 Playwright Chromium 生成 `/tmp/p0m_browser_visual_smoke/battle_visual_smoke_desktop.png` 与 `/tmp/p0m_browser_visual_smoke/battle_visual_smoke_mobile.png`，并据截图修复移动端 HUD / 工具栏溢出。
- 已补浏览器玩家主链路截图门禁 `tools/frontend/capture_frontend_flow_visual_smoke.py` 与 `tools/frontend/validate_frontend_flow_visual_smoke_report.py`：使用真实 Chromium 通过 no-build 前端从本地档案入口、开局配置、开场叙事、大地图、现场试作、塔防战斗走到战后结算，覆盖 desktop/mobile 共 14 张截图。当前 develop 已验证 `/tmp/frontend_flow_visual_smoke_develop/frontend_flow_visual_smoke_report.v0.1.json` 为 `captured`，battle 截图包含 canvas，settlement 截图到达结算页；该工具不调用 provider、不读取 `.env`、不写世界状态。
- 已补演示前一键证据套件 `tools/demo/run_demo_evidence_suite.py`：串联浏览器玩家链路截图、截图 report 校验和统一 demo evidence 导出，输出 `/tmp/.../demo_evidence_suite_report.v0.1.json`；默认要求真实 Chromium 可用，显式 `--allow-missing-browser` 才允许降级；不调用 provider、不读取 `.env`、不写世界状态、不提交截图到仓库。
- 已补日常开发快速质量门 `tools/dev/run_fast_quality_gate.py`：串联 Python 编译、前端语法检查、战斗视觉合同、campaign router 前端合同、map component 前端合同、MVP readiness build 和 readiness validator，默认输出 `/tmp/ai_td_fast_quality_gate_report.v0.1.json`。它不跑浏览器、不调用 provider、不读取 `.env`、不写世界状态、不激活 runtime，用于比完整 evidence export 更快地发现常见破坏；录屏 / 评审前仍以完整 evidence 套件为准。
- 已补 WorkerTaskPack acceptance profile runner `tools/dev/run_worker_acceptance_profile.py`：先校验任务包，再按 `acceptance_profile.default_profile` 或显式 `--profile` 安全执行命令，支持 profile 列表、dry-run、fail-fast、timeout 和 JSON report。该 runner 不使用 shell，遇到管道、非受限重定向、分号连接、逻辑连接或命令替换语法会记录 unsupported 并拒绝执行；最终 token 形式的 `> /tmp/file` 或 `>/tmp/file` 会由 runner 捕获 stdout 后写入仓库外 `/tmp` 文件；没有 `acceptance_profile` 的旧包仍需手动运行 `acceptance_commands`。
- 已补 WorkerTaskPack acceptance profile 迁移审计 `tools/dev/audit_worker_acceptance_profiles.py`：只读扫描 `examples/worker_task_packs/*.json`，复用任务包 validator 和 profile runner 命令解析规则，输出已有 profile、无 profile 旧包、完整 evidence 顶层命令、fast gate、summary-only、迁移候选和 shell-only/manual-review 命令清单；该审计不执行被扫描任务包的验收命令，不修改旧包，并强制 `--output` 写到仓库外 `/tmp` 路径。
- 已用 `tools/dev/migrate_worker_acceptance_profiles.py --write` 批量迁移 80 个 runner-compatible 旧 WorkerTaskPack；当前审计剩余 16 个无 profile / manual-review 包，均因 heredoc、多命令脚本或其他 runner-incompatible 命令需要人工处理。
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

### P1-A-8 Provider adapter video runner 边界

状态：已完成边界接入，真实 live 图生视频 provider 未接入。

目标：

```text
让 tools/provider_adapter/run_provider_adapter.py 接受 --mode video，为 P1-A 图片 -> 视频 -> 关键帧 -> atlas 管线生成可验证的 review-only 上游 receipt/envelope；默认不调用 provider，不读取 .env，不联网，不写世界状态，不激活 runtime。
```

产物：

- `tools/provider_adapter/run_provider_adapter.py`：新增 `--mode video` 离线边界；`--mode video --live` 快速失败为 `video_live_provider_not_implemented`，不写成功产物。
- `examples/provider_adapter_runs/p1a_provider_adapter_video_runner.executor_request.json`
- `examples/provider_authorizations/p1a_provider_execution_authorization_video.example.json`
- `examples/provider_adapter_runs/p1a_provider_adapter_video_runner.receipt.json`
- `examples/provider_adapter_runs/p1a_provider_adapter_video_runner.envelope.json`
- `examples/worker_task_packs/p1a_provider_video_adapter_boundary.v0.1.json`
- `tools/demo/export_evidence.py`：统一 evidence 新增 `provider_adapter_video_runner` 摘要和离线验证命令。

当前结论：

- video runner 只是 provider adapter 边界和 dry-run receipt/envelope，不等于真实图生视频 provider 已接入。
- receipt 复用既有 `fixture_output_ready_for_envelope` 状态，未实现原因写入 `finish_reason=video_live_provider_not_implemented` 与 envelope 摘要。
- 默认 video 模式不创建 raw video、frame sequence、atlas 或 staging / promotion 产物。
- 后续真实 live video 必须先安全下载为本地 video ref，再进入 RawVideoSequence、抽帧、FrameSequence、LoopContinuityReport、media gate、human review 和 promotion gate。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1a_provider_video_adapter_boundary.v0.1.json
python3 tools/dev/validate_generation_executor_run_request.py examples/provider_adapter_runs/p1a_provider_adapter_video_runner.executor_request.json
python3 tools/dev/validate_provider_execution_authorization.py examples/provider_authorizations/p1a_provider_execution_authorization_video.example.json
python3 tools/provider_adapter/run_provider_adapter.py --mode video --executor-request examples/provider_adapter_runs/p1a_provider_adapter_video_runner.executor_request.json --authorization examples/provider_authorizations/p1a_provider_execution_authorization_video.example.json --receipt-output /tmp/p1a_provider_adapter_video_runner.receipt.json --envelope-output /tmp/p1a_provider_adapter_video_runner.envelope.json --created-at 2026-07-05T00:00:00Z
python3 tools/dev/validate_provider_adapter_execution_receipt.py examples/provider_adapter_runs/p1a_provider_adapter_video_runner.receipt.json
python3 tools/dev/validate_provider_output_envelope.py examples/provider_adapter_runs/p1a_provider_adapter_video_runner.envelope.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_provider_video_runner python3 -m py_compile tools/provider_adapter/run_provider_adapter.py tools/demo/export_evidence.py
python3 tools/demo/export_evidence.py --output-dir /tmp/provider_video_adapter_boundary_evidence
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

### P1-B-38 Provider adapter runner handoff outbox

状态：已完成最小骨架。

目标：

```text
把 background handoff tick 返回的 runner_handoffs 固化为可验证的 ProviderAdapterRunnerHandoffOutbox v0.1：新增 schema、validator、后端 outbox wrapper、测试和 evidence 摘要，使外部 runner / worker 可以消费一个机器可校验的批量交接单；不得调用 provider、不得读取 .env、不得运行 provider adapter、不得 staging/promotion、不得 complete queue item、不得写世界状态、不得激活 runtime。
```

已落地：

- `shared/schemas/provider_adapter_runner_handoff_outbox.v0.1.schema.json`
- `tools/dev/validate_provider_adapter_runner_handoff_outbox.py`
- `POST /api/sessions/{session_id}/generation-schedule/workers/run-review-only-background-handoff-tick` 返回 `provider_adapter_runner_handoff_outbox`。
- outbox 记录 `source`、`safety`、`runner_handoff_count`、`runner_handoffs[]` 和 `import_contract`。
- validator 会递归拒绝 secret、API key、prompt 正文、provider response、raw JSON / trace、unreviewed content 等敏感内容，并检查 handoff source、授权 ref、建议 `/tmp` 路径、live 模板显式授权和 import 回灌合同。
- `tools/demo/export_evidence.py` 新增 outbox schema / validator / task pack 摘要，并在 `summary.md` / `index.html` 展示 `provider_adapter_runner_handoff_outbox_v0_1_ready`。
- `examples/worker_task_packs/p1b_provider_runner_handoff_outbox.v0.1.json` 记录本轮任务包与 OpenCode headless 在当前受控通道内被执行环境拒绝后的 `local_codex_safe_fallback`。

当前结论：

- outbox 是外部 runner 的批量交接单，不是 provider 输出、staging manifest、promotion report、runtime package 或世界状态事务。
- live 模板可以存在，但必须继续要求外部显式授权、显式 prompt file、显式 artifact output 和显式 `.env` 路径。
- 外部 runner 执行后仍必须通过 `import-provider-adapter-runner-output` 回灌 receipt/envelope，并继续走 staging / promotion / activation gates。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_provider_runner_handoff_outbox.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_provider_runner_handoff_outbox python3 -m compileall backend
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_provider_runner_handoff_outbox_tools python3 -m py_compile tools/dev/validate_provider_adapter_runner_handoff_outbox.py tools/demo/export_evidence.py
uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py -q
python3 tools/demo/export_evidence.py --output-dir /tmp/provider_runner_handoff_outbox_evidence
rg -n "provider_adapter_runner_handoff_outbox|provider_adapter_runner_handoff_outbox_v0_1_ready|validate_provider_adapter_runner_handoff_outbox" /tmp/provider_runner_handoff_outbox_evidence
git diff --check
```

### P1-B-59 Provider adapter runner handoff outbox consumer

状态：已完成本地 dry boundary consumer。

目标：

```text
让外部 runner / worker 可以消费 ProviderAdapterRunnerHandoffOutbox v0.1 文件，批量执行 provider adapter runner 的离线 fixture / video boundary，并输出 receipt/envelope 与执行报告；仍不导入后端、不 staging/promotion、不激活 runtime。
```

已落地：

- `tools/dev/run_provider_adapter_runner_handoff_outbox.py`：新增 outbox consumer CLI。
- 默认 `--adapter-mode fixture`；可显式 `--adapter-mode video` 验证 video dry boundary。
- 工具会校验 outbox、写出每个 handoff 的 executor request / authorization、调用 `tools/provider_adapter/run_provider_adapter.py`、校验 receipt/envelope，并生成 `provider_adapter_runner_handoff_outbox_execution_report.v0.1.json`。
- report 记录每个 handoff 的 receipt/envelope 文件引用、import_after_runner body、安全计数和未执行导入说明。
- `tools/demo/export_evidence.py`：provider runner handoff 摘要新增 `outbox_consumer_status=local_dry_boundary_consumer_ready` 和 consumer tool / task pack 引用。
- `docs/GENERATION_SCHEDULER_V0_1.md`、`docs/CURRENT_ARCHITECTURE_INDEX.md`：同步 outbox consumer 边界。
- `examples/worker_task_packs/p1b_provider_runner_handoff_outbox_consumer.v0.1.json`：新增本轮 worker task pack。

边界：

- v0.1 consumer 只支持离线 `fixture` / `video` boundary，不接入 live text/image provider。
- 不读取 `.env`、不调用 provider、不把结果导入后端、不 staging、不 promotion、不 complete queue item、不写世界状态、不激活 runtime。
- report 中的 `import_after_runner` 只是后续显式导入合同，不由该工具自动执行。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_provider_runner_handoff_outbox_consumer.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_provider_runner_outbox_consumer python3 -m py_compile tools/dev/run_provider_adapter_runner_handoff_outbox.py tools/demo/export_evidence.py
python3 tools/dev/validate_provider_adapter_runner_handoff_outbox.py /tmp/provider_runner_handoff_outbox_consumer_fixture.v0.1.json
python3 tools/dev/run_provider_adapter_runner_handoff_outbox.py /tmp/provider_runner_handoff_outbox_consumer_fixture.v0.1.json --output-dir /tmp/provider_runner_handoff_outbox_consumer_fixture_run --generated-at 2026-07-07T00:00:00+00:00
python3 tools/dev/run_provider_adapter_runner_handoff_outbox.py /tmp/provider_runner_handoff_outbox_consumer_fixture.v0.1.json --adapter-mode video --output-dir /tmp/provider_runner_handoff_outbox_consumer_video_run --generated-at 2026-07-07T00:00:00+00:00
python3 tools/demo/export_evidence.py --validation-profile summary-only --output-dir /tmp/provider_runner_handoff_outbox_consumer_evidence
rg -n "outbox consumer|local_dry_boundary_consumer_ready|run_provider_adapter_runner_handoff_outbox" /tmp/provider_runner_handoff_outbox_consumer_evidence
git diff --check
```

### P1-B-60 Provider adapter runner handoff outbox import pipeline smoke

状态：已完成严格本地 smoke。

目标：

```text
证明 ProviderAdapterRunnerHandoffOutbox v0.1 不只是能被本地 consumer 消费，也能在不预先运行后端 runner fixture 的情况下，经外部 consumer 生成 receipt/envelope 后显式导回临时后端 ledger，并让 prefetch-cache 出现 review-only envelope；同时保持 provider call、.env read、staging、promotion、queue complete、world mutation 和 runtime activation 全部为 0。
```

已落地：

- `tools/dev/check_provider_runner_handoff_outbox_import_pipeline.py`：新增严格 smoke 脚本。
- 脚本启动临时 SQLite / uvicorn，创建 scheduler run，并对 `sched_next_map_visual_prefetch`、`sched_video_frame_background_compile` 分别执行 dry-run、live guard、executor request、provider authorization 和 handoff export。
- 脚本手动组装 `ProviderAdapterRunnerHandoffOutbox v0.1`，调用 `tools/dev/run_provider_adapter_runner_handoff_outbox.py` 的离线 fixture consumer，再调用 `import-provider-adapter-runner-output` 导入临时后端。
- smoke 断言导入前 `review_only_envelope_ready_count=0`，导入后为 2，且 `activation_allowed_count=0`。
- `tools/dev/run_provider_adapter_runner_handoff_outbox.py` 修正 provider call 安全计数字段，读取 `ProviderOutputEnvelope.provider_call.performed`。
- `tools/demo/export_evidence.py`：provider runner handoff 摘要新增 `outbox_import_pipeline_status=local_consume_import_prefetch_smoke_ready`、tool / task pack 引用和 summary/html 展示。
- `docs/GENERATION_SCHEDULER_V0_1.md`、`docs/CURRENT_ARCHITECTURE_INDEX.md`：同步该 smoke 的边界和事实源入口。
- `examples/worker_task_packs/p1b_provider_runner_handoff_outbox_import_smoke.v0.1.json`：新增本轮 worker task pack。

边界：

- 只使用本地 fixture provider adapter boundary，不调用 live provider。
- 不读取 `.env`、不保存 prompt/provider 原文、不 staging、不 promotion、不 complete queue item、不写世界状态、不激活 runtime。
- 生成的 smoke report 写入 `/tmp`，不提交到仓库。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_provider_runner_handoff_outbox_import_smoke.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_provider_runner_outbox_import_smoke python3 -m py_compile tools/dev/check_provider_runner_handoff_outbox_import_pipeline.py tools/dev/run_provider_adapter_runner_handoff_outbox.py tools/demo/export_evidence.py
python3 tools/dev/check_provider_runner_handoff_outbox_import_pipeline.py --output /tmp/provider_runner_handoff_outbox_import_pipeline_report.v0.1.json --generated-at 2026-07-07T00:00:00+00:00
python3 tools/demo/export_evidence.py --validation-profile summary-only --output-dir /tmp/provider_runner_handoff_outbox_import_smoke_evidence
rg -n "consume_import|outbox import|check_provider_runner_handoff_outbox_import_pipeline|local_consume_import_prefetch_smoke_ready" /tmp/provider_runner_handoff_outbox_import_smoke_evidence
git diff --check
```

### P1-B-39 Architecture fact source freeze

状态：已完成文档治理。

目标：

```text
冻结 AI 编译系统 v0.1 的事实源层级和生命周期映射：CURRENT_ARCHITECTURE_INDEX 只做导航与事实源路由，AI_COMPILATION_SYSTEM 只做概念 / 边界 / 权限 / 生命周期事实源，字段、op 白名单、semantic gate、builder、validator 和运行命令以 shared/schemas、tools 和专题文档为准；补齐 ProviderAdapterRunnerHandoffOutbox、ProviderOutputEnvelope、staging、promotion、runtime package、媒体、地图 certified 与 CGOP 生命周期关系；不得改实现代码、不得调用 provider、不得读取 .env。
```

已落地：

- `docs/AI_COMPILATION_SYSTEM_V0_1.md` 新增 `v0.1 冻结断言`，明确索引、概念文档、schema/tools、Scheduler、WorldStateDeltaTransaction、ProviderAdapterRunnerHandoffOutbox、MapRuntimePackage、媒体与 runtime 的边界。
- `docs/AI_COMPILATION_SYSTEM_V0_1.md` 生命周期映射补齐 ProviderOutputEnvelope、ProviderArtifactStagingManifest、ProviderArtifactPromotionReport 与 ProviderAdapterRunnerHandoffOutbox。
- `docs/CURRENT_ARCHITECTURE_INDEX.md` 新增冻结快照，明确当前 worker 应使用的事实源层级，并禁止从旧 task worktree、早期聊天摘要或滞后 main 文档推导字段事实。
- `examples/worker_task_packs/p1b_architecture_fact_source_freeze.v0.1.json` 记录本轮文档治理任务包，以及 OpenCode headless 在当前受控通道内被执行环境拒绝后的 `local_codex_safe_fallback`。

当前结论：

- 这是事实源治理，不是 schema 迁移，也不是实现重构。
- 概念层可以触发后续 schema 修订，但不能让实现绕过当前 gate。
- `ProviderAdapterRunnerHandoffOutbox` 只能作为外部 runner 交接单，不得被任何 worker 解释为 provider 输出、runtime artifact 或世界事务。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_architecture_fact_source_freeze.v0.1.json
rg -n "v0.1 冻结断言|ProviderAdapterRunnerHandoffOutbox|CURRENT_ARCHITECTURE_INDEX.md|shared/schemas/ \\+ tools/ \\+ 专题文档" docs/AI_COMPILATION_SYSTEM_V0_1.md docs/CURRENT_ARCHITECTURE_INDEX.md
rg -n "Architecture fact source freeze|p1b_architecture_fact_source_freeze" control/TASK_QUEUE.md examples/worker_task_packs/p1b_architecture_fact_source_freeze.v0.1.json
git diff --check
```

### P1-B-40 Refactor scheduler handoff builders

状态：已完成小范围重构。

目标：

```text
把 Generation Scheduler 中 provider adapter runner handoff 和 ProviderAdapterRunnerHandoffOutbox 的纯 payload 构造逻辑从 generation_scheduler_service.py 抽到独立 builder 模块；保持 API 返回兼容，不改变 queue / ledger / DB 状态流转，不调用 provider，不读取 .env，不 staging，不 promotion，不写世界状态，不激活 runtime。
```

已落地：

- 新增 `backend/app/services/generation_scheduler_handoff_builders.py`。
- `generation_scheduler_service.py` 继续负责 latest run、ledger 查询、schema 校验和 API 编排；handoff payload、runner 命令模板、outbox safety 与 import contract 改由纯 builder 构造。
- `backend/tests/test_frontend_mock_api.py` 新增 builder 安全合同测试，并保留原 handoff / outbox API 兼容测试。
- `examples/worker_task_packs/p1b_refactor_scheduler_handoff_builders.v0.1.json` 记录本轮任务包与 OpenCode headless 在当前受控通道内被执行环境拒绝后的 `local_codex_safe_fallback`。

当前结论：

- 这是行为保持型重构，目标是减少 `generation_scheduler_service.py` 继续膨胀。
- 新 builder 是纯构造模块，不拥有调度状态、不读 DB、不调用 provider、不保存 prompt / provider response。
- 后续可按同一方式继续拆分 scheduler service 的 ledger import、queue transition 和 prefetch cache view。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_refactor_scheduler_handoff_builders.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_refactor_handoff python3 -m compileall backend
uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py -q
rg -n "generation_scheduler_handoff_builders|build_provider_adapter_runner_handoff_outbox|provider_runner_outbox_safety" backend/app/services backend/tests/test_frontend_mock_api.py
git diff --check
```

### P1-B-41 Refactor scheduler import safety

状态：已完成小范围重构。

目标：

```text
把 provider runner / artifact review import 的本地路径限制、.env 路径拒绝、敏感 key 扫描和安全 JSON 加载从 generation_scheduler_service.py 抽到独立模块；保持 API 错误和返回兼容，不改变 DB / ledger / queue 行为，不调用 provider，不读取 .env，不 staging，不 promotion，不写世界状态，不激活 runtime。
```

已落地：

- 新增 `backend/app/services/generation_scheduler_import_safety.py`。
- `generation_scheduler_service.py` 保留 `_resolve_import_path`、`_load_runner_import_json`、`_display_import_path` 兼容薄包装，并把实际安全规则交给 import safety 模块。
- `backend/tests/test_frontend_mock_api.py` 增加 `.envelope.json` 后缀允许、真实 `.env` 路径拒绝的回归测试。
- `examples/worker_task_packs/p1b_refactor_scheduler_import_safety.v0.1.json` 记录本轮任务包与 OpenCode headless 在当前受控通道内被执行环境拒绝后的 `local_codex_safe_fallback`。

当前结论：

- 这是行为保持型重构，目标是让导入安全规则从调度状态机中分离出来。
- 新模块只处理本地路径和 JSON 内容安全，不读 DB、不读 `.env`、不调用 provider、不写 ledger。
- `.envelope.json` 文件名不会被误判为 `.env` 路径；真正包含 `.env` 路径段的导入仍会被拒绝。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_refactor_scheduler_import_safety.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_refactor_import_safety python3 -m compileall backend
uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py -q
rg -n "generation_scheduler_import_safety|resolve_import_path|load_safe_import_json|display_import_path" backend/app/services backend/tests/test_frontend_mock_api.py
git diff --check
```

### P1-B-42 Refactor provider artifact fixture catalog

状态：已完成小范围重构。

目标：

```text
把 provider artifact fixture profile、fixture 文件路径和 metadata 读取逻辑从 generation_scheduler_service.py 抽到独立 catalog 模块；保持 API 行为兼容，不改变 queue / ledger / DB 状态流转，不调用 provider，不读取 .env，不 staging，不 promotion，不写世界状态，不激活 runtime。
```

已落地：

- 新增 `backend/app/services/generation_scheduler_artifact_fixtures.py`。
- `generation_scheduler_service.py` 保留 `_provider_artifact_fixture_paths`、`_provider_artifact_fixture_metadata` 兼容薄包装，并把 profile alias、fixture 路径和 source refs 读取交给 catalog 模块。
- `backend/tests/test_frontend_mock_api.py` 增加 default / image_failure profile catalog 直接测试，并保留现有 API 兼容测试。
- `examples/worker_task_packs/p1b_refactor_provider_artifact_fixtures.v0.1.json` 记录本轮任务包与 OpenCode headless 在当前受控通道内被执行环境拒绝后的 `local_codex_safe_fallback`。

当前结论：

- 这是行为保持型重构，目标是让 fixture profile 目录从调度状态机中分离出来。
- 新模块只处理 repo 内 fixture catalog、路径解析和 envelope source refs 提取，不读 DB、不读 `.env`、不调用 provider、不写 ledger。
- 后续增加新的 provider artifact fixture 时，应先更新 catalog 和直接单测，再接 API 端到端流程。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_refactor_provider_artifact_fixtures.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_refactor_artifact_fixtures python3 -m compileall backend
uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py -q
rg -n "generation_scheduler_artifact_fixtures|provider_artifact_fixture_paths|provider_artifact_fixture_metadata" backend/app/services backend/tests/test_frontend_mock_api.py
git diff --check
```

### P1-B-43 Refactor scheduler run and queue builders

状态：已完成小范围重构。

目标：

```text
把 Generation Scheduler 中 generation schedule buffer、run payload、queue item payload、queue summary、worker cache summary、provider guard log summary、safe id / cache id 等纯 payload 构造与摘要函数抽到独立模块；保持 API 行为兼容，不改变 queue / ledger / DB 状态流转，不调用 provider，不读取 .env，不 staging，不 promotion，不写世界状态，不激活 runtime。
```

已落地：

- 新增 `backend/app/services/generation_scheduler_run_queue_builders.py`。
- `generation_scheduler_service.py` 继续负责 fixture 加载、DB、queue transition、ledger 和 API 编排；纯 run / queue / cache / guard summary builder 改由独立模块提供。
- `backend/tests/test_frontend_mock_api.py` 增加 run / queue builder 与 worker cache builder 安全合同测试，并保留原 API 兼容测试。
- `examples/worker_task_packs/p1b_refactor_scheduler_run_queue_builders.v0.1.json` 记录本轮任务包与 OpenCode headless 在当前受控通道内被执行环境拒绝后的 `local_codex_safe_fallback`。

当前结论：

- 这是行为保持型重构，目标是让 scheduler service 继续从巨型状态机文件收缩为编排层。
- 新模块只处理纯 dict 构造和摘要，不读 fixture、不读 DB、不读 `.env`、不调用 provider、不写 ledger。
- 后续可继续拆分 provider request / authorization / receipt payload builders，或 artifact ledger 读写层。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_refactor_scheduler_run_queue_builders.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_refactor_run_queue_builders python3 -m compileall backend
uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py -q
rg -n "generation_scheduler_run_queue_builders|build_generation_schedule_buffer|build_worker_cache_payload|compact_generation_queue|safe_id_fragment" backend/app/services backend/tests/test_frontend_mock_api.py
git diff --check
```

### P1-B-44 Refactor artifact ledger builders

状态：已完成小范围重构。

目标：

```text
把 Generation Scheduler 中 ProviderOutputEnvelope compact、ProviderArtifactStaging compact、ProviderArtifactPromotionReport compact、artifact ledger entry payload、artifact ledger summary 和 compact ledger view 等纯 dict 构造/摘要函数抽到独立模块；保持 API 行为兼容，不改变 queue / ledger / DB 状态流转，不调用 provider，不读取 .env，不 staging，不 promotion，不写世界状态，不激活 runtime。
```

已落地：

- 新增 `backend/app/services/generation_scheduler_artifact_ledger_builders.py`。
- `generation_scheduler_service.py` 继续负责 DB、ledger 查询 / upsert、queue 状态和 API 编排；provider artifact compact 与 ledger entry / summary builder 改由独立模块提供。
- `backend/tests/test_frontend_mock_api.py` 增加 provider artifact compact 与 ledger summary 安全合同测试，并保留原 API 兼容测试。
- `examples/worker_task_packs/p1b_refactor_artifact_ledger_builders.v0.1.json` 记录本轮任务包与 OpenCode headless 在当前受控通道内被执行环境拒绝后的 `local_codex_safe_fallback`。

当前结论：

- 这是行为保持型重构，目标是把 artifact ledger 的无副作用摘要逻辑从 scheduler service 中分离。
- 新模块只处理纯 dict compact、ledger entry payload 和 summary，不读 fixture、不读 DB、不读 `.env`、不调用 provider、不写 ledger。
- 后续可继续拆分 provider request / authorization / receipt payload builders，或 artifact ledger repository 读写层。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_refactor_artifact_ledger_builders.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_refactor_artifact_ledger_builders python3 -m compileall backend
uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py -q
rg -n "generation_scheduler_artifact_ledger_builders|compact_provider_output_envelope|compact_provider_artifact_staging|compact_provider_artifact_promotion_report|build_artifact_ledger_payload|compact_generation_artifact_ledger" backend/app/services backend/tests/test_frontend_mock_api.py
git diff --check
```

### P1-B-45 Refactor provider execution builders

状态：已完成小范围重构。

目标：

```text
把 Generation Scheduler 中 provider guard id、executor request id、authorization ref、adapter receipt id、live executor guard payload、executor request payload / compact、provider authorization payload / compact、runner rehydrate、adapter receipt payload / compact 等纯构造函数抽到独立模块；保持 API 行为兼容，不改变 queue / ledger / DB 状态流转，不调用 provider，不读取 .env，不 staging，不 promotion，不写世界状态，不激活 runtime。
```

已落地：

- 新增 `backend/app/services/generation_scheduler_provider_execution_builders.py`。
- `generation_scheduler_service.py` 继续负责 repo ref 注入、DB、ledger、queue 状态和 API 编排；provider execution 边界对象构造改由独立模块提供。
- `backend/tests/test_frontend_mock_api.py` 增加 guard / executor request / authorization / receipt / runner rehydrate 安全合同测试，并保留原 API 兼容测试。
- `generation_scheduler_service.py` 的 run id 生成从 `secrets.token_urlsafe` 改为 `secrets.token_hex`，避免随机出现 `sk-` 片段被 secret-fragment gate 误判。
- `examples/worker_task_packs/p1b_refactor_provider_execution_builders.v0.1.json` 记录本轮任务包与 OpenCode headless 在当前受控通道内被执行环境拒绝后的 `local_codex_safe_fallback`。

当前结论：

- 这是行为保持型重构，目标是把 provider execution 边界的无副作用构造逻辑从 scheduler service 中分离。
- 新模块只处理纯 dict payload / compact / rehydrate，不读 fixture、不读 DB、不读 `.env`、不调用 provider、不写 ledger。
- 后续可继续拆分 artifact ledger repository 读写层，或转向 MapRuntimePackage / 前端 mock 体验闭环。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_refactor_provider_execution_builders.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_refactor_provider_execution_builders python3 -m compileall backend
uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py -q
rg -n "generation_scheduler_provider_execution_builders|build_live_executor_guard_payload|build_generation_executor_run_request_payload|build_provider_execution_authorization_payload|build_provider_adapter_execution_receipt_payload|rehydrate_generation_executor_request_for_runner|rehydrate_provider_authorization_for_runner" backend/app/services backend/tests/test_frontend_mock_api.py
git diff --check
```

### P1-B-46 Refactor artifact ledger repository

状态：已完成小范围重构。

目标：

```text
把 Generation Scheduler 中 generation_artifact_ledger 的 upsert、load、latest executor request / provider authorization / provider adapter receipt / provider output envelope 查询函数抽到独立 repository 模块；保持 API 行为兼容，不改变 queue / ledger payload / DB schema，不调用 provider，不读取 .env，不 staging，不 promotion，不写世界状态，不激活 runtime。
```

已落地：

- 新增 `backend/app/services/generation_scheduler_artifact_ledger_repository.py`。
- `generation_scheduler_service.py` 继续负责业务编排、payload 构造、validation 和 API 返回；ledger SQLite 读写与 latest 查询改由 repository 模块提供。
- `backend/tests/test_frontend_mock_api.py` 增加 repository upsert / run filter / latest provider chain 查询测试，并保留原 API 兼容测试。
- `backend/app/api/sessions.py` 的 session id 生成从 URL-safe token 改为 hex token，避免随机出现 `sk-` 片段被 generation executor request 的 secret-fragment gate 误判。
- `examples/worker_task_packs/p1b_refactor_artifact_ledger_repository.v0.1.json` 记录本轮任务包与 OpenCode headless 在当前受控通道内被执行环境拒绝后的 `local_codex_safe_fallback`。

当前结论：

- 这是行为保持型重构，目标是把 artifact ledger 的 SQLite 访问细节从 scheduler service 中分离。
- 新模块只处理 `generation_artifact_ledger` 表读写和 latest 查询，不读 `.env`、不调用 provider、不构造 provider payload、不写世界状态。
- 后续可继续拆分 queue repository / worker cache repository，或转向 MapRuntimePackage / 前端 mock 体验闭环。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_refactor_artifact_ledger_repository.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_refactor_artifact_ledger_repository python3 -m compileall backend
uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py backend/tests/test_sessions.py -q
rg -n "generation_scheduler_artifact_ledger_repository|upsert_generation_artifact_ledger|load_generation_artifact_ledger_items|latest_generation_executor_request_ledger_entry|latest_provider_authorization_ledger_entry|latest_provider_adapter_execution_ledger_entry|latest_provider_output_envelope_ledger_entry|token_hex" backend/app backend/tests
git diff --check
```

### P1-B-47 Refactor scheduler run queue repository

状态：已完成小范围重构。

目标：

```text
把 Generation Scheduler 中 generation_schedule_runs 与 generation_schedule_queue_items 的 SQLite 插入、读取、按状态查找和更新函数抽到独立 repository 模块；保持 API 行为兼容，不改变 queue payload、worker cache、provider guard、ledger、DB schema，不调用 provider，不读取 .env，不 staging，不 promotion，不写世界状态，不激活 runtime。
```

已落地：

- 新增 `backend/app/services/generation_scheduler_run_queue_repository.py`。
- `generation_scheduler_service.py` 继续负责状态转移规则、attempt / retry / fallback 预算、业务异常和 API 编排；run / queue 两张表的 SQLite 访问改由 repository 模块提供。
- `backend/tests/test_frontend_mock_api.py` 增加 repository run / queue insert、load latest、run filter、按状态取下一项、定向 row lookup 和 update 测试，并保留原 API 兼容测试。
- `examples/worker_task_packs/p1b_refactor_scheduler_run_queue_repository.v0.1.json` 记录本轮任务包与 OpenCode headless 在当前受控通道内被执行环境拒绝后的 `local_codex_safe_fallback`。

当前结论：

- 这是行为保持型重构，目标是把 scheduler run / queue 的 SQLite 访问细节从 scheduler service 中分离。
- 新模块只处理 `generation_schedule_runs` 与 `generation_schedule_queue_items` 表读写，不读 `.env`、不调用 provider、不构造 provider payload、不写世界状态。
- 后续可继续拆分 worker cache repository / provider guard log repository，或转向正式后台 executor 与 MapRuntimePackage / 前端体验闭环。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_refactor_scheduler_run_queue_repository.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_refactor_scheduler_run_queue_repository python3 -m compileall backend
uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py backend/tests/test_sessions.py -q
rg -n "generation_scheduler_run_queue_repository|insert_generation_schedule_run|insert_generation_queue_items|load_latest_generation_schedule_run|load_generation_queue_items|load_generation_queue_item_row|load_next_generation_item_row_by_status|update_generation_queue_item" backend/app backend/tests
git diff --check
```

### P1-B-48 Refactor scheduler worker state repository

状态：已完成小范围重构。

目标：

```text
把 Generation Scheduler 中 generation_schedule_worker_cache 与 provider_logs 的 SQLite upsert、load、insert 和 guard log 过滤函数抽到独立 repository 模块；保持 API 行为兼容，不改变 run / queue / ledger payload、DB schema，不调用 provider，不读取 .env，不 staging，不 promotion，不写世界状态，不激活 runtime。
```

已落地：

- 新增 `backend/app/services/generation_scheduler_worker_state_repository.py`。
- `generation_scheduler_service.py` 继续负责 worker cache payload 构造、live executor guard payload 构造、状态转移和 API 编排；worker cache 与 provider guard log 的 SQLite 读写改由 repository 模块提供。
- `backend/tests/test_frontend_mock_api.py` 增加 worker cache upsert / run filter / created_at 保留，以及 provider guard log schema / run filter 测试，并保留原 API 兼容测试。
- `examples/worker_task_packs/p1b_refactor_scheduler_worker_state_repository.v0.1.json` 记录本轮任务包与 OpenCode headless 在当前受控通道内被执行环境拒绝后的 `local_codex_safe_fallback`。

当前结论：

- 这是行为保持型重构，目标是把 worker cache 与 provider guard log 的 SQLite 访问细节从 scheduler service 中分离。
- 新模块只处理 `generation_schedule_worker_cache` 与 `provider_logs` 两张表读写和过滤，不读 `.env`、不调用 provider、不构造 provider payload、不写世界状态。
- 后续可继续拆分 provider review import / staging import repository，或转向正式后台 executor 与 MapRuntimePackage / 前端体验闭环。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_refactor_scheduler_worker_state_repository.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_refactor_scheduler_worker_state_repository python3 -m compileall backend
uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py backend/tests/test_sessions.py -q
rg -n "generation_scheduler_worker_state_repository|upsert_worker_cache_payload|load_worker_cache_items|insert_provider_guard_log|load_provider_guard_logs" backend/app backend/tests
git diff --check
```

### P1-B-49 Refactor provider artifact review helpers

状态：已完成小范围重构。

目标：

```text
把 Generation Scheduler 中 ProviderArtifactStagingManifest 与 ProviderArtifactPromotionReport 之间的纯 review contract 校验、staging / reviewed artifact 引用匹配和 promotion_allowed 判断抽到独立 helper 模块；保持 API 行为兼容，不改变 ledger payload、DB schema、fixture 路径、安全门或 runtime activation 边界。
```

已落地：

- 新增 `backend/app/services/generation_scheduler_provider_artifact_review_helpers.py`。
- `generation_scheduler_service.py` 继续负责路径解析、schema validator 调用、latest run / ledger 查询、ledger upsert 和 API 编排；staging / promotion report 的跨文件 contract 判断改由 helper 模块提供。
- `backend/tests/test_frontend_mock_api.py` 增加 helper 级合同测试，覆盖正常引用、`promotion_allowed` 判断和未 staged 的 reviewed artifact 阻断。
- `examples/worker_task_packs/p1b_refactor_provider_artifact_review_helpers.v0.1.json` 记录本轮任务包与 OpenCode headless 在当前受控通道内被执行环境拒绝后的 `local_codex_safe_fallback`。

当前结论：

- 这是行为保持型重构，目标是把 provider artifact review 的纯判断从 scheduler service 中分离。
- 新模块只处理 staging / promotion report 的跨文件 review contract，不读 fixture、不读 `.env`、不调用 provider、不写 ledger、不写世界状态、不激活 runtime。
- 后续可继续拆分 provider artifact review import / staging import 编排，或转向正式后台 executor、真实 provider 调度与 activation / promotion gate。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_refactor_provider_artifact_review_helpers.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_refactor_provider_artifact_review_helpers python3 -m compileall backend
uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py backend/tests/test_sessions.py -q
rg -n "generation_scheduler_provider_artifact_review_helpers|validate_provider_artifact_review_contract|provider_artifact_promotion_allowed|missing_reviewed_staged_artifact_ids" backend/app backend/tests
git diff --check
```

### P1-B-50 Refactor prefetch cache read-model builders

状态：已完成小范围重构。

目标：

```text
把 Generation Scheduler 中 GET prefetch-cache 的只读视图构造逻辑抽到独立 builder 模块；保持 API 行为兼容，不改变 queue / ledger 读写、DB schema、provider 调用边界、staging / promotion / activation gate 或世界状态边界。
```

已落地：

- 新增 `backend/app/services/generation_scheduler_prefetch_cache_builders.py`。
- `generation_scheduler_service.py` 继续负责 latest run、queue items 和 artifact ledger items 的读取；preload / prefetch cache 的 refs 汇总、`cache_status` 推导、activation / promotion gate 摘要和 summary 计数改由 builder 模块提供。
- `backend/tests/test_frontend_mock_api.py` 增加 builder 级读模型测试，覆盖 queue / ledger refs 汇总、`promotion_allowed_pending_activation`、queued fallback 状态、provider 调用历史计数和只读安全计数。
- `examples/worker_task_packs/p1b_refactor_prefetch_cache_builders.v0.1.json` 记录本轮任务包与 OpenCode headless 在当前受控通道内被执行环境拒绝后的 `local_codex_safe_fallback`。

当前结论：

- 这是行为保持型重构，目标是把前端 / Studio 读取的 prefetch cache 派生视图从 scheduler service 中分离。
- 新模块只从 queue items 与 artifact ledger items 派生只读 payload，不读 `.env`、不调用 provider、不写 DB、不写 ledger、不写世界状态、不激活 runtime。
- 后续真实后台 executor、跨请求缓存或 activation gate 接入时，应优先扩展该读模型 builder，而不是继续扩张 scheduler service。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_refactor_prefetch_cache_builders.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_refactor_prefetch_cache_builders python3 -m compileall backend
uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py backend/tests/test_sessions.py -q
rg -n "generation_scheduler_prefetch_cache_builders|build_generation_prefetch_cache_payload|prefetch_cache_status|ledger_entry_ref" backend/app backend/tests
git diff --check
```

### P1-B-51 Refactor provider adapter runner import helpers

状态：已完成小范围重构。

目标：

```text
把 Generation Scheduler 中 import-provider-adapter-runner-output 的纯 receipt / envelope / ledger authorization chain alignment 检查抽到独立 helper 模块；保持 API 行为兼容，不改变 runner output validator、ledger payload、DB schema、provider 调用边界、staging / promotion / activation gate 或世界状态边界。
```

已落地：

- 新增 `backend/app/services/generation_scheduler_provider_adapter_import_helpers.py`。
- `generation_scheduler_service.py` 继续负责路径解析、runner output validator、latest run / ledger 查询、ledger upsert 和 API 编排；receipt / envelope / executor request / authorization 的 alignment checks 改由 helper 模块提供。
- `backend/tests/test_frontend_mock_api.py` 增加 helper 级合同测试，覆盖全部 alignment 通过和失败名称回报。
- `examples/worker_task_packs/p1b_refactor_provider_adapter_runner_import_helpers.v0.1.json` 记录本轮任务包与 OpenCode headless 在当前受控通道内被执行环境拒绝后的 `local_codex_safe_fallback`。

当前结论：

- 这是行为保持型重构，目标是把外部 runner 回灌的授权链对齐规则从 scheduler service 中分离。
- 新模块只检查 receipt / envelope / ledger authorization chain alignment，不读 `.env`、不调用 provider、不写 DB、不写 ledger、不写世界状态、不激活 runtime。
- 后续 live provider runner、视频 adapter 或多 provider import 扩展时，应复用该 helper，而不是继续扩张 scheduler service。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_refactor_provider_adapter_runner_import_helpers.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_refactor_provider_adapter_runner_import_helpers python3 -m compileall backend
uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py backend/tests/test_sessions.py -q
rg -n "generation_scheduler_provider_adapter_import_helpers|validate_provider_adapter_runner_import_contract|provider_adapter_runner_import_alignment_checks" backend/app backend/tests
git diff --check
```

### P1-B-52 Refactor scheduler dispatcher controls

状态：已完成小范围重构。

目标：

```text
把 Generation Scheduler 中 review-only dispatcher drain / background tick 的 max_items 解析、targeted metadata 拒绝和 dispatcher step metadata 构造等纯控制面规则抽到独立 helper 模块；保持 API 行为兼容，不改变 dispatcher 编排、queue / ledger 读写、DB schema、provider 调用边界、staging / promotion / activation gate 或世界状态边界。
```

已落地：

- 新增 `backend/app/services/generation_scheduler_dispatcher_controls.py`。
- `generation_scheduler_service.py` 继续负责 dispatcher drain、background executor tick 和 background handoff tick 的实际编排；`max_items` 解析、targeted metadata 拒绝和 dispatcher step metadata 构造改由 helper 模块提供。
- `backend/tests/test_frontend_mock_api.py` 增加 helper 级合同测试，覆盖默认 / 字符串 `max_items`、越界错误、targeted metadata 列表、拒绝错误文案和 step metadata 输出。
- `examples/worker_task_packs/p1b_refactor_scheduler_dispatcher_controls.v0.1.json` 记录本轮任务包与 OpenCode headless 在当前受控通道内被执行环境拒绝后的 `local_codex_safe_fallback`。

当前结论：

- 这是行为保持型重构，目标是把 dispatcher / tick 的控制面规则从 scheduler service 中分离。
- 新模块只处理控制面规则，不读 `.env`、不调用 provider、不写 DB、不写 ledger、不写世界状态、不激活 runtime。
- 后续正式后台 executor、daemon loop 或多 worker 调度接入时，应复用该 helper，而不是继续扩张 scheduler service。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_refactor_scheduler_dispatcher_controls.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_refactor_scheduler_dispatcher_controls python3 -m compileall backend
uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py backend/tests/test_sessions.py -q
rg -n "generation_scheduler_dispatcher_controls|requested_max_items|reject_targeted_metadata|dispatcher_step_metadata|targeted_metadata_keys" backend/app backend/tests
git diff --check
```

### P1-B-53 Provider video handoff template

状态：已完成最小骨架。

目标：

```text
把 Generation Scheduler 的 provider adapter runner handoff/outbox 扩展到 video runner 模板，让外部 runner 能看到 tools/provider_adapter/run_provider_adapter.py --mode video 的离线边界命令；后端 handoff/API 不运行 provider adapter，不接入真实 live video provider，不读取 .env，不调用外部 provider，不 staging/promotion，不写世界状态，不激活 runtime。证据脚本中的离线 dry-run 校验只能停在 review-only receipt/envelope 边界。
```

已落地：

- `backend/app/services/generation_scheduler_handoff_builders.py` 在 `command_templates` 中新增 `video_boundary`。
- `command_templates.video_boundary` 只包含不带 `--live` 的 `--mode video` dry boundary，不要求 `<authorized-dotenv-path>`。
- `tools/dev/validate_provider_adapter_runner_handoff_outbox.py` 会校验 video 模板存在、包含 `--mode video`，且不包含 `--live` 或 `<authorized-dotenv-path>`。
- `backend/tests/test_frontend_mock_api.py` 覆盖 handoff export 与 background handoff tick 中的 video 模板可见性。
- `tools/demo/export_evidence.py` 在 provider runner handoff / background handoff tick 摘要中展示 `video_dry_boundary_template_visible`。
- `examples/worker_task_packs/p1b_provider_video_handoff_template.v0.1.json` 记录本轮任务包。

当前结论：

- video handoff 只是外部 runner 可见的离线边界模板，不是 live video provider 接入。
- 现有 `live_llm_text` / `live_image` 模板仍保持显式 `--live` 与 `<authorized-dotenv-path>` 授权合同。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_provider_video_handoff_template.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_provider_video_handoff_template python3 -m compileall backend
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_provider_video_handoff_template_tools python3 -m py_compile tools/dev/validate_provider_adapter_runner_handoff_outbox.py tools/demo/export_evidence.py
uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py -q -k "provider_adapter_runner_handoff or background_handoff_tick or provider_runner_handoff_outbox"
python3 tools/demo/export_evidence.py --output-dir /tmp/provider_video_handoff_template_evidence
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
- provider adapter runner 已有 `--mode video` 离线边界和 live 阻断，用于服务后续真实图生视频接入前的 request / authorization / receipt / envelope 验收。
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

#### P1-D-04 MapCompilationDesign 地图编译设计采纳审查

状态：已完成设计审查与项目化采纳。

目标：

```text
审查外部 AI 提出的地图编译方案，采纳其 logic-first / StylePack / 程序化渲染方向，但不照搬完整 LevelBundle 或一组全新 schema。
```

已落地：

- `docs/MAP_COMPILATION_DESIGN_V0_1.md`：新增审查采纳文档，明确 AI 不再负责整张运行时地图，AI 只负责风格、组件和参考，程序负责结构和对齐，Validator 负责可信。
- `docs/MAP_COMPILATION_DESIGN_V0_1.md` 2026-07-04 加固：补充地图编译权限分层、强语义 / 弱语义 / 装饰 / 氛围分级，以及 Reachability / Placement / Resource / Hazard / Collision / SemanticVisual / StyleConsistency validator 在本项目中的映射。
- `docs/CURRENT_ARCHITECTURE_INDEX.md`：把该文档加入当前有效设计文档和实现事实。
- `examples/worker_task_packs/p1d_map_compilation_design_review.v0.1.json`：新增本轮 worker handoff 包。

采纳结论：

- 保留 `MapRuntimePackage` 作为运行时地图事实源。
- 保留 `MapCompilePackage` 作为编译证据源。
- 后续新增 `MapStylePack`、`ProceduralMapRenderPlan`、`SemanticVisualConsistencyReport`，而不是继续 prompt-only 整图生成。
- `LevelBundle` 暂时只作为未来聚合概念，不替代现有 schema。
- Spline 思路采纳为 v0.2 方向，但短期保持 `path_routes.waypoints` 兼容。
- 玩家不直接编译地图拓扑；玩家编译解法，系统编译遭遇，开发者编译关卡，发布层控制 runtime 激活。

边界：

- 本任务不改代码、不调用 provider、不读取 `.env`。
- 外部文档仅作为参考，不作为字段级事实源。
- Codex headless 在当前受控通道内被安全策略拒绝为外部数据披露风险，本轮使用 `local_codex_safe_fallback` 完成。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1d_map_compilation_design_review.v0.1.json
python3 -m py_compile tools/dev/validate_worker_task_pack.py
rg -n "MAP_COMPILATION_DESIGN|MapStylePack|ProceduralMapRenderPlan|SemanticVisualConsistencyReport|AI 负责风格和组件" docs control examples/worker_task_packs
git diff --check
```

#### P1-D-04B MapDecorationZonePolicy v0.1 装饰区约束层

状态：已完成第一版实现。

目标：

```text
把外部方案中的 DecorationZoneMap 思路落成最小 review-only 策略：从现有 MapRuntimePackage 派生强语义保护区、弱语义附着区、纯装饰区和氛围遮挡规则，供后续 renderer / StylePack / 地图组件化使用。
```

已落地：

- `shared/schemas/map_decoration_zone_policy.v0.1.schema.json`
- `tools/asset_graph/build_map_decoration_zone_policy.py`
- `tools/asset_graph/validate_map_decoration_zone_policy.py`
- `examples/map_decoration_zone_policies/mvp_map_decoration_zone_policy.v0.1.json`
- `examples/worker_task_packs/p1map_decoration_zone_policy.v0.1.json`

边界：

- `MapRuntimePackage v0.1 / v0.2 preview` 仍是强语义事实源。
- 本策略只派生装饰和弱语义约束，不修改 runtime 包、不调用 provider、不读取 `.env`、不从图片 / SVG / preview 反推逻辑。
- 它不是玩家默认 runtime，不绕过 v0.2 activation gate。

验收：

```bash
python3 tools/asset_graph/build_map_decoration_zone_policy.py --validate
python3 tools/asset_graph/validate_map_decoration_zone_policy.py examples/map_decoration_zone_policies/mvp_map_decoration_zone_policy.v0.1.json
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1map_decoration_zone_policy.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_map_decoration_zone_policy python3 -m py_compile tools/asset_graph/build_map_decoration_zone_policy.py tools/asset_graph/validate_map_decoration_zone_policy.py
python3 tools/dev/run_worker_acceptance_profile.py examples/worker_task_packs/p1map_decoration_zone_policy.v0.1.json --profile daily_fast --output /tmp/map_decoration_zone_policy_runner.json
python3 tools/dev/run_fast_quality_gate.py --output /tmp/map_decoration_zone_policy_fast_gate.json
git diff --check
```

#### P1-D-05 MapStylePack / ProceduralMapRenderPlan / SemanticVisualConsistencyReport 最小链路

状态：已完成第一版实现。

目标：

```text
把地图编译从“AI 整图候选”推进到 MapRuntimePackage + MapStylePack -> ProceduralMapRenderPlan -> SemanticVisualConsistencyReport 的可验证最小链路。
```

已落地：

- `shared/schemas/map_style_pack.v0.1.schema.json`：StylePack 字段事实源，只允许表现层风格、材质、prefab、氛围和可读性规则。
- `shared/schemas/procedural_map_render_plan.v0.1.schema.json`：分层程序化渲染计划，强语义 layer 必须来自 MapRuntimePackage。
- `shared/schemas/semantic_visual_consistency_report.v0.1.schema.json`：语义视觉一致性报告，记录 route / slot / objective / spawn / debug-player 边界检查。
- `tools/asset_graph/procedural_map_render_plan.py`：核心 builder / validator helper。
- `tools/asset_graph/build_procedural_map_render_plan.py`：从 runtime package + style pack 生成 render plan 和 consistency report。
- `tools/asset_graph/validate_map_style_pack.py`
- `tools/asset_graph/validate_procedural_map_render_plan.py`
- `tools/asset_graph/validate_semantic_visual_consistency_report.py`
- `examples/map_style_packs/long_night_ruined_outpost.map_style_pack.json`
- `examples/map_render_plans/mvp_first_battle.procedural_map_render_plan.json`
- `examples/semantic_visual_consistency_reports/mvp_first_battle.semantic_visual_consistency_report.json`
- `examples/worker_task_packs/p1d_map_style_render_plan.v0.1.json`

边界：

- 本任务不调用 provider、不读取 `.env`、不生成图片。
- StylePack 不允许决定路线、塔位、目标、出生点或碰撞事实。
- RenderPlan 的 player default 层不得包含 debug/reference layer。
- Codex headless 已尝试委派，但当前执行环境拒绝外部 coding model 披露工作区数据，本轮使用 `local_codex_safe_fallback` 在隔离 task worktree 完成。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1d_map_style_render_plan.v0.1.json
python3 tools/asset_graph/validate_map_style_pack.py examples/map_style_packs/long_night_ruined_outpost.map_style_pack.json
python3 tools/asset_graph/build_procedural_map_render_plan.py --runtime-package examples/map_runtime_packages/mvp_first_battle.map_runtime_package.json --style-pack examples/map_style_packs/long_night_ruined_outpost.map_style_pack.json --output examples/map_render_plans/mvp_first_battle.procedural_map_render_plan.json --report-output examples/semantic_visual_consistency_reports/mvp_first_battle.semantic_visual_consistency_report.json --created-at 2026-07-04T00:00:00Z
python3 tools/asset_graph/validate_procedural_map_render_plan.py examples/map_render_plans/mvp_first_battle.procedural_map_render_plan.json
python3 tools/asset_graph/validate_semantic_visual_consistency_report.py examples/semantic_visual_consistency_reports/mvp_first_battle.semantic_visual_consistency_report.json --render-plan examples/map_render_plans/mvp_first_battle.procedural_map_render_plan.json --runtime-package examples/map_runtime_packages/mvp_first_battle.map_runtime_package.json
PYTHONPYCACHEPREFIX=/tmp/ai-td-pycache-map-style-render-plan python3 -m py_compile tools/asset_graph/procedural_map_render_plan.py tools/asset_graph/build_procedural_map_render_plan.py tools/asset_graph/validate_map_style_pack.py tools/asset_graph/validate_procedural_map_render_plan.py tools/asset_graph/validate_semantic_visual_consistency_report.py
git diff --check
```

#### P1-D-06 MapRenderPlan 后端与前端 mock 数据层只读接入

状态：已完成第一版接入。

目标：

```text
让前端 mock API 和静态前端数据层能拿到 MapStylePack / ProceduralMapRenderPlan / SemanticVisualConsistencyReport bundle，为后续前端真正消费分层地图渲染计划做接口准备。
```

已落地：

- `backend/app/services/map_render_plan_service.py`：新增 node -> render plan bundle 的 fixture-backed 只读服务。
- `backend/app/services/frontend_mock_service.py`：`get_battle_config()` 与 `get_runtime_package()` 可选返回 `map_render_plan_bundle`。
- `backend/app/api/frontend_mock.py`：新增 `/api/sessions/{session_id}/battles/{node_id}/map-render-plan` endpoint。
- `frontend/app.js`：API 模式和静态模式都能保存 `state.data.mapRenderPlanBundle`，但暂不改变战斗画面渲染。
- `backend/tests/test_frontend_mock_api.py`：补充首战 bundle 和非首战 404 的测试断言。
- `examples/worker_task_packs/p1d_map_render_plan_api.v0.1.json`：新增本轮任务包。

边界：

- 本任务不调用 provider、不读取 `.env`、不改变前端战斗绘制函数。
- 当前只有 `gray_lantern_station` 有 RenderPlan bundle；其他节点返回 `null`，单独 endpoint 返回 404。
- 完整 pytest 在当前受控环境中未能执行：系统 Python 无 pytest / FastAPI，`uv run` 需要访问用户缓存目录但升级权限被平台额度限制拒绝。已用服务层 smoke、`py_compile`、`node --check` 与 `git diff --check` 覆盖本轮核心风险。

验收：

```bash
PYTHONPYCACHEPREFIX=/tmp/ai-td-pycache-map-render-plan-api PYTHONPATH=/tmp/ai-td-task-map-render-plan-api/backend python3 - <<'PY'
from app.services import frontend_mock_service, map_render_plan_service
bundle = map_render_plan_service.load_map_render_plan_bundle('gray_lantern_station')
assert bundle['procedural_map_render_plan']['schema_version'] == 'procedural_map_render_plan.v0.1'
assert bundle['semantic_visual_consistency_report']['status'] == 'passed'
assert 'debug_control_overlay' not in bundle['procedural_map_render_plan']['player_default_layer_ids']
payload = frontend_mock_service.get_battle_config('smoke_session', 'gray_lantern_station')
assert payload['map_render_plan_bundle']['node_id'] == 'gray_lantern_station'
assert frontend_mock_service.get_battle_config('smoke_session', 'lamp_wick_store')['map_render_plan_bundle'] is None
try:
    map_render_plan_service.load_map_render_plan_bundle('lamp_wick_store')
except map_render_plan_service.MapRenderPlanNotFoundError:
    pass
else:
    raise AssertionError('expected MapRenderPlanNotFoundError')
PY
PYTHONPYCACHEPREFIX=/tmp/ai-td-pycache-map-render-plan-api python3 -m py_compile backend/app/services/map_render_plan_service.py backend/app/services/frontend_mock_service.py backend/app/api/frontend_mock.py backend/tests/test_frontend_mock_api.py
node --check frontend/app.js
git diff --check
```

#### P1-D-07 MVP 三节点 MapRenderPlan bundle 补齐

状态：已完成第一版实现。

目标：

```text
让 gray_lantern_station、lamp_wick_store、old_signal_tower 三个 MVP 战斗节点都具备 MapStylePack / ProceduralMapRenderPlan / SemanticVisualConsistencyReport bundle，而不是只有首战节点可走地图编译最小链路。
```

已落地：

- `examples/map_style_packs/long_night_lamp_wick_store.map_style_pack.json`
- `examples/map_style_packs/long_night_old_signal_tower.map_style_pack.json`
- `examples/map_render_plans/mvp_wick_store_pressure.procedural_map_render_plan.json`
- `examples/map_render_plans/mvp_old_signal_tower_pressure.procedural_map_render_plan.json`
- `examples/semantic_visual_consistency_reports/mvp_wick_store_pressure.semantic_visual_consistency_report.json`
- `examples/semantic_visual_consistency_reports/mvp_old_signal_tower_pressure.semantic_visual_consistency_report.json`
- `backend/app/services/map_render_plan_service.py`：映射扩展为三节点。
- `backend/tests/test_frontend_mock_api.py`：三节点均要求暴露 render plan bundle，单独 `/map-render-plan` endpoint 均应返回 `passed` report。
- `examples/worker_task_packs/p1d_map_render_plan_all_nodes.v0.1.json`

边界：

- 本任务不调用 provider、不读取 `.env`、不生成图片。
- 新 StylePack 仍只描述表现层，不允许决定路线、塔位、目标或出生点。
- RenderPlan 由已有 builder 从 MapRuntimePackage + StylePack 生成；SemanticVisualConsistencyReport 必须为 `passed`。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1d_map_render_plan_all_nodes.v0.1.json
python3 tools/asset_graph/validate_map_style_pack.py examples/map_style_packs/long_night_lamp_wick_store.map_style_pack.json
python3 tools/asset_graph/validate_map_style_pack.py examples/map_style_packs/long_night_old_signal_tower.map_style_pack.json
python3 tools/asset_graph/build_procedural_map_render_plan.py --runtime-package examples/map_runtime_packages/mvp_wick_store_pressure.map_runtime_package.json --style-pack examples/map_style_packs/long_night_lamp_wick_store.map_style_pack.json --output examples/map_render_plans/mvp_wick_store_pressure.procedural_map_render_plan.json --report-output examples/semantic_visual_consistency_reports/mvp_wick_store_pressure.semantic_visual_consistency_report.json --created-at 2026-07-04T00:00:00Z
python3 tools/asset_graph/build_procedural_map_render_plan.py --runtime-package examples/map_runtime_packages/mvp_old_signal_tower_pressure.map_runtime_package.json --style-pack examples/map_style_packs/long_night_old_signal_tower.map_style_pack.json --output examples/map_render_plans/mvp_old_signal_tower_pressure.procedural_map_render_plan.json --report-output examples/semantic_visual_consistency_reports/mvp_old_signal_tower_pressure.semantic_visual_consistency_report.json --created-at 2026-07-04T00:00:00Z
python3 tools/asset_graph/validate_procedural_map_render_plan.py examples/map_render_plans/mvp_wick_store_pressure.procedural_map_render_plan.json
python3 tools/asset_graph/validate_procedural_map_render_plan.py examples/map_render_plans/mvp_old_signal_tower_pressure.procedural_map_render_plan.json
python3 tools/asset_graph/validate_semantic_visual_consistency_report.py examples/semantic_visual_consistency_reports/mvp_wick_store_pressure.semantic_visual_consistency_report.json --render-plan examples/map_render_plans/mvp_wick_store_pressure.procedural_map_render_plan.json --runtime-package examples/map_runtime_packages/mvp_wick_store_pressure.map_runtime_package.json
python3 tools/asset_graph/validate_semantic_visual_consistency_report.py examples/semantic_visual_consistency_reports/mvp_old_signal_tower_pressure.semantic_visual_consistency_report.json --render-plan examples/map_render_plans/mvp_old_signal_tower_pressure.procedural_map_render_plan.json --runtime-package examples/map_runtime_packages/mvp_old_signal_tower_pressure.map_runtime_package.json
PYTHONPYCACHEPREFIX=/tmp/ai-td-pycache-map-render-plan-all-nodes PYTHONPATH=/tmp/ai-td-task-map-render-plan-all-nodes/backend python3 - <<'PY'
from app.services import frontend_mock_service, map_render_plan_service
expected = {
    'gray_lantern_station': 'render_plan_gray_lantern_station_v0_1',
    'lamp_wick_store': 'render_plan_lamp_wick_store_v0_1',
    'old_signal_tower': 'render_plan_old_signal_tower_v0_1',
}
assert map_render_plan_service.available_map_render_plan_node_ids() == sorted(expected)
for node_id, plan_id in expected.items():
    bundle = map_render_plan_service.load_map_render_plan_bundle(node_id)
    assert bundle['procedural_map_render_plan']['plan_id'] == plan_id
    assert bundle['semantic_visual_consistency_report']['status'] == 'passed'
    assert 'debug_control_overlay' not in bundle['procedural_map_render_plan']['player_default_layer_ids']
    payload = frontend_mock_service.get_battle_config('smoke_session', node_id)
    assert payload['map_render_plan_bundle']['procedural_map_render_plan']['plan_id'] == plan_id
PY
PYTHONPYCACHEPREFIX=/tmp/ai-td-pycache-map-render-plan-all-nodes python3 -m py_compile backend/app/services/map_render_plan_service.py backend/tests/test_frontend_mock_api.py
git diff --check
```

#### P1-D-08 前端消费 MapRenderPlan / StylePack 表现层

状态：已完成第一版实现。

目标：

```text
让前端战斗画面在保持 MapRuntimePackage 为运行时语义事实源的前提下，消费 map_render_plan_bundle / MapStylePack 的表现层信息，驱动道路、塔基、目标和出生点的玩家可见样式。
```

已落地：

- `frontend/app.js`：新增 `mapRenderPlanBundle()`、`mapStylePack()`、`mapStylePalette()`、`colorFromStyle()`、`rgbaFromStyle()`、`mapRenderPlanHasLayer()`。
- `frontend/app.js`：`battleNodeVisualProfile()` 会在 `map_style_pack.v0.1` 可用时用 StylePack 调整地形、道路、部署基座、目标和出生点表现色。
- `frontend/app.js`：道路、路肩、碎石、车辙、方向 cue、部署基座、目标地基和出生点氛围读取 StylePack 派生颜色，缺失时保留原本节点 fallback。
- `tools/frontend/validate_battle_visual_contract.py`：补充 MapRenderPlan / StylePack 前端消费契约，确保玩家默认画面仍不使用控制图或失败整图。
- `frontend/README.md`：说明 `MapStylePack` 只管表现层，`MapRuntimePackage` 仍管运行时语义。
- `examples/worker_task_packs/p1d_frontend_consume_map_render_plan.v0.1.json`

边界：

- 本任务不调用 provider、不读取 `.env`、不生成图片、不修改 schema。
- StylePack 不允许决定路线、塔位、目标、出生点或碰撞事实。
- ProceduralMapRenderPlan 只作为前端分层绘制就绪证据，不替代 MapRuntimePackage。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1d_frontend_consume_map_render_plan.v0.1.json
node --check frontend/app.js
PYTHONPYCACHEPREFIX=/tmp/ai-td-pycache-frontend-consume-map-render-plan python3 tools/frontend/validate_battle_visual_contract.py
git diff --check
```

#### P1-D-09 前端消费 RenderPlan 层几何参数

状态：已完成第一版实现。

目标：

```text
让前端战斗画面不只读取 MapStylePack 颜色，也读取 ProceduralMapRenderPlan 的非语义表现层几何参数，例如 road_band.width_cells、road_edge.shoulder_width_cells 和 build_slot_platform.footprint。
```

已落地：

- `frontend/app.js`：新增 `mapRenderPlan()`、`mapRenderPlanLayer()`、`mapRenderPlanOperation()`、`renderGeometryNumber()` 等 RenderPlan adapter。
- `frontend/app.js`：道路宽度读取 `road_band.geometry.width_cells`，路肩厚度读取 `road_edge.geometry.shoulder_width_cells`。
- `frontend/app.js`：部署台地和部署底座读取 `build_slot_platform.geometry.footprint.width_cells / height_cells`。
- `tools/frontend/validate_battle_visual_contract.py`：补充 RenderPlan geometry 前端消费契约，避免后续只保留 StylePack 调色。
- `frontend/README.md`、`docs/CURRENT_ARCHITECTURE_INDEX.md`、`docs/MAP_COMPILATION_DESIGN_V0_1.md`：同步说明 RenderPlan 已进入玩家侧表现层，但不拥有玩法语义。
- `examples/worker_task_packs/p1d_frontend_render_plan_layer_params.v0.1.json`

边界：

- 本任务不调用 provider、不读取 `.env`、不生成图片、不修改 schema。
- RenderPlan 不提供路线、塔位、目标或出生点事实；这些事实仍只来自 `MapRuntimePackage`。
- 前端只读取表现层 geometry，不从 RenderPlan 的重复 waypoints / position 反推 runtime 语义。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1d_frontend_render_plan_layer_params.v0.1.json
node --check frontend/app.js
PYTHONPYCACHEPREFIX=/tmp/ai-td-pycache-frontend-render-plan-layer-params python3 tools/frontend/validate_battle_visual_contract.py
git diff --check
```

#### P1-D-10 RenderPlan 离线 SVG 预览

状态：已完成第一版实现。

目标：

```text
让 ProceduralMapRenderPlan 不只被前端运行时消费，也能在无浏览器、无 provider 的环境中生成 review-only SVG 预览和可校验 report，证明它是可执行表现计划。
```

已落地：

- `tools/asset_graph/render_procedural_map_preview.py`：输入 MapRuntimePackage、MapStylePack、ProceduralMapRenderPlan，输出伪 3D SVG 预览和 `procedural_map_preview_report.v0.1`。
- `tools/asset_graph/validate_procedural_map_preview_report.py`：校验 SVG 文件存在、sha256 匹配、usage policy、semantic source policy 和基本渲染统计。
- `examples/map_render_previews/mvp_first_battle.procedural_map_preview.svg`
- `examples/map_render_previews/mvp_wick_store_pressure.procedural_map_preview.svg`
- `examples/map_render_previews/mvp_old_signal_tower_pressure.procedural_map_preview.svg`
- 三份对应 `*.procedural_map_preview_report.json`。

边界：

- 本任务不调用 provider、不读取 `.env`、不生成位图、不修改前端/后端/schema。
- 预览 SVG 是 review-only evidence，不是玩家 runtime 背景，不进入 media manifest。
- 路线、塔位、目标、出生点坐标仍来自 `MapRuntimePackage`；RenderPlan 只提供 road width、shoulder width 和 slot footprint 等表现几何参数。

验收：

```bash
python3 tools/asset_graph/render_procedural_map_preview.py --output examples/map_render_previews/mvp_first_battle.procedural_map_preview.svg --report-output examples/map_render_previews/mvp_first_battle.procedural_map_preview_report.json
python3 tools/asset_graph/render_procedural_map_preview.py --runtime-package examples/map_runtime_packages/mvp_wick_store_pressure.map_runtime_package.json --style-pack examples/map_style_packs/long_night_lamp_wick_store.map_style_pack.json --render-plan examples/map_render_plans/mvp_wick_store_pressure.procedural_map_render_plan.json --output examples/map_render_previews/mvp_wick_store_pressure.procedural_map_preview.svg --report-output examples/map_render_previews/mvp_wick_store_pressure.procedural_map_preview_report.json
python3 tools/asset_graph/render_procedural_map_preview.py --runtime-package examples/map_runtime_packages/mvp_old_signal_tower_pressure.map_runtime_package.json --style-pack examples/map_style_packs/long_night_old_signal_tower.map_style_pack.json --render-plan examples/map_render_plans/mvp_old_signal_tower_pressure.procedural_map_render_plan.json --output examples/map_render_previews/mvp_old_signal_tower_pressure.procedural_map_preview.svg --report-output examples/map_render_previews/mvp_old_signal_tower_pressure.procedural_map_preview_report.json
python3 tools/asset_graph/validate_procedural_map_preview_report.py examples/map_render_previews/mvp_first_battle.procedural_map_preview_report.json
python3 tools/asset_graph/validate_procedural_map_preview_report.py examples/map_render_previews/mvp_wick_store_pressure.procedural_map_preview_report.json
python3 tools/asset_graph/validate_procedural_map_preview_report.py examples/map_render_previews/mvp_old_signal_tower_pressure.procedural_map_preview_report.json
PYTHONPYCACHEPREFIX=/tmp/ai-td-pycache-render-plan-preview python3 -m py_compile tools/asset_graph/render_procedural_map_preview.py tools/asset_graph/validate_procedural_map_preview_report.py
git diff --check
```

#### P1-D-11 RenderPlan 离线预览接入 demo evidence

状态：已完成第一版实现。

目标：

```text
让 `examples/map_render_previews/*.procedural_map_preview_report.json` 被统一 demo evidence 自动纳入，使评审/录屏能直接看到 MapRuntimePackage + MapStylePack + ProceduralMapRenderPlan 的 review-only SVG 预览证据。
```

已落地：

- `tools/demo/export_evidence.py`：新增动态发现 `examples/map_render_previews/*.procedural_map_preview_report.json`，并把预览 report 纳入 validation commands、source files、`assets_and_media.map_visual_reference.procedural_map_previews`、`summary.md` 和 `index.html`。
- `examples/worker_task_packs/p1d_render_preview_evidence_export.v0.1.json`：记录本任务的 worktree、边界、验收命令和 `local_codex_safe_fallback` 原因。
- `docs/CURRENT_ARCHITECTURE_INDEX.md`：补充 demo evidence 已展示 RenderPlan 离线预览事实。

边界：

- 本任务不调用 provider、不读取 `.env`、不修改前端/后端/schema。
- 预览 report 只作为 review-only evidence，不修改 `MapRuntimePackage`、不晋升 published visual layer、不改变玩家 runtime 背景。
- 新增地图节点后，只要补充 `*.procedural_map_preview_report.json`，统一 evidence 会动态纳入。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1d_render_preview_evidence_export.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai-td-pycache-render-preview-evidence python3 -m py_compile tools/demo/export_evidence.py
python3 tools/demo/export_evidence.py --output-dir /tmp/render_preview_evidence_export
python3 - <<'PY'
import json
from pathlib import Path
root = Path('/tmp/render_preview_evidence_export')
evidence = json.loads((root / 'evidence.json').read_text(encoding='utf-8'))
previews = evidence['assets_and_media']['map_visual_reference']['procedural_map_previews']
assert previews['report_count'] == 3
assert previews['ready_count'] == 3
assert previews['runtime_activation_policy'] == 'review_only_not_player_runtime'
summary = (root / 'summary.md').read_text(encoding='utf-8')
assert '地图 RenderPlan 离线预览' in summary
PY
git diff --check
```

#### P1-D-12 MapRuntimePackage v0.2 强语义 preview

状态：已完成第一版旁路实现。

目标：

```text
在不替换现有前端/后端默认 v0.1 地图包的前提下，建立 MapRuntimePackage v0.2 preview：把资源点、机关区、防守锚点和阻挡区变成结构化运行时语义对象，避免继续依赖图片或整图生成反推这些玩法信息。
```

已落地：

- `shared/schemas/map_runtime_package.v0.2.schema.json`：定义 v0.2 顶层合同和四类新增强语义对象。
- `tools/asset_graph/map_runtime_package_v02.py`：复用 v0.1 builder，追加 `resource_nodes`、`hazard_zones`、`defense_anchors`、`blocked_areas`，并做 Python 语义校验。
- `tools/asset_graph/build_map_runtime_package_v02.py` / `validate_map_runtime_package_v02.py`：提供离线构建和校验入口。
- `examples/map_runtime_packages_v02/*.map_runtime_package_v02.json`：三张 MVP 战斗节点的 v0.2 preview 包。
- `tools/demo/export_evidence.py`：新增 `map_runtime_packages_v02` evidence 摘要、source files 和 validation commands；summary / index 会展示资源点、机关区、防守锚点和阻挡区计数。
- `examples/worker_task_packs/p1d_map_runtime_semantics_v02.v0.1.json`：记录本轮边界和验收命令。

边界：

- v0.2 preview 不进入 `backend/app/services/map_runtime_service.py` 的默认节点映射。
- v0.2 示例放在 `examples/map_runtime_packages_v02/`，不混入 `examples/map_runtime_packages/` 的 v0.1 正式 runtime 包扫描。
- 本任务不调用 provider、不读取 `.env`、不改前端、不改后端、不发布任何地图视觉层。
- 资源点、机关区、防守锚点和阻挡区是结构化玩法语义；图像/StylePack/RenderPlan 只能表现这些语义，不能反向决定它们。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1d_map_runtime_semantics_v02.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai-td-pycache-map-runtime-v02 python3 -m py_compile tools/asset_graph/map_runtime_package_v02.py tools/asset_graph/build_map_runtime_package_v02.py tools/asset_graph/validate_map_runtime_package_v02.py tools/demo/export_evidence.py
python3 tools/asset_graph/validate_map_runtime_package_v02.py examples/map_runtime_packages_v02/mvp_first_battle.map_runtime_package_v02.json
python3 tools/asset_graph/validate_map_runtime_package_v02.py examples/map_runtime_packages_v02/mvp_wick_store_pressure.map_runtime_package_v02.json
python3 tools/asset_graph/validate_map_runtime_package_v02.py examples/map_runtime_packages_v02/mvp_old_signal_tower_pressure.map_runtime_package_v02.json
python3 tools/demo/export_evidence.py --output-dir /tmp/map_runtime_v02_evidence
python3 - <<'PY'
import json
from pathlib import Path
evidence = json.loads(Path('/tmp/map_runtime_v02_evidence/evidence.json').read_text(encoding='utf-8'))
v02 = evidence['map_runtime_packages_v02']
assert v02['package_count'] == 3
assert v02['total_resource_node_count'] == 3
assert v02['total_hazard_zone_count'] == 3
assert v02['total_defense_anchor_count'] == 3
assert v02['total_blocked_area_count'] == 3
PY
git diff --check
```

#### P1-D-13 RenderPlan v0.2 强语义预览

状态：已完成第一版旁路实现。

目标：

```text
让 ProceduralMapRenderPlan 和离线 SVG 预览消费 MapRuntimePackage v0.2 preview 的资源点、机关区、防守锚点和阻挡区，同时保持该链路为 review-only 旁路，不替换前端/后端默认 v0.1 runtime。
```

已落地：

- `shared/schemas/procedural_map_render_plan.v0.1.schema.json`：补充 `resource_node`、`hazard_zone`、`defense_anchor`、`blocked_area` semantic kind，以及 `draw_zone`、`draw_blocked_cells`、`draw_anchor_marker` operation。
- `tools/asset_graph/procedural_map_render_plan.py`：从 v0.2 runtime 包生成 `resource_or_hazard` 与 `blocking_prop` layer，并在 `SemanticVisualConsistencyReport` 中检查四类强语义覆盖。
- `tools/asset_graph/build_procedural_map_render_plan.py`：自动识别 `map_runtime_package.v0.2`，调用 v0.2 validator。
- `tools/asset_graph/render_procedural_map_preview.py`：离线 SVG 预览可以绘制资源点、机关区、防守锚点和阻挡区，并在 report 中记录语义计数。
- `examples/map_style_packs/*.map_style_pack.json`：补齐最小 resource / hazard / blocking procedural prefab。
- `examples/map_render_plans_v02/`、`examples/semantic_visual_consistency_reports_v02/`、`examples/map_render_previews_v02/`：三张 MVP 地图的 v0.2 review-only 旁路证据。
- `tools/demo/export_evidence.py`：新增 `procedural_map_previews_v02` evidence 摘要、source files 和 validation commands。
- `examples/worker_task_packs/p1d_render_plan_v02_semantics.v0.1.json`：记录本轮边界和验收命令。

边界：

- 本任务不调用 provider、不读取 `.env`、不改前端/后端。
- v0.2 preview SVG 只作为 review-only evidence，不作为玩家 runtime 或 published visual layer。
- 资源点、机关区、防守锚点和阻挡区必须来自 `MapRuntimePackage v0.2 preview`，不能从图像反推。
- `MapStylePack` 只提供表现层 prefab / palette，不控制 gameplay truth。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1d_render_plan_v02_semantics.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai-td-pycache-render-plan-v02-semantics python3 -m py_compile tools/asset_graph/procedural_map_render_plan.py tools/asset_graph/build_procedural_map_render_plan.py tools/asset_graph/render_procedural_map_preview.py tools/asset_graph/validate_procedural_map_preview_report.py tools/demo/export_evidence.py
python3 tools/asset_graph/validate_procedural_map_render_plan.py examples/map_render_plans_v02/mvp_first_battle.procedural_map_render_plan.json
python3 tools/asset_graph/validate_semantic_visual_consistency_report.py examples/semantic_visual_consistency_reports_v02/mvp_first_battle.semantic_visual_consistency_report.json --render-plan examples/map_render_plans_v02/mvp_first_battle.procedural_map_render_plan.json --runtime-package examples/map_runtime_packages_v02/mvp_first_battle.map_runtime_package_v02.json
python3 tools/asset_graph/validate_procedural_map_preview_report.py examples/map_render_previews_v02/mvp_first_battle.procedural_map_preview_report.json
python3 tools/demo/export_evidence.py --output-dir /tmp/render_plan_v02_semantics_evidence
python3 - <<'PY'
import json
from pathlib import Path
evidence = json.loads(Path('/tmp/render_plan_v02_semantics_evidence/evidence.json').read_text(encoding='utf-8'))
summary = evidence['assets_and_media']['map_visual_reference']['procedural_map_previews_v02']
assert summary['report_count'] == 3
assert summary['ready_count'] == 3
for sample in summary['preview_samples']:
    render = sample['render_summary']
    assert render['resource_node_count'] == 1
    assert render['hazard_zone_count'] == 1
    assert render['defense_anchor_count'] == 1
    assert render['blocked_area_count'] == 1
PY
git diff --check
```

#### P1-D-14 MapRuntimePackage v0.2 审查接口

状态：已完成第一版后端旁路实现。

目标：

```text
给前端 / Studio / 演示脚本一个统一入口读取 MapRuntimePackage v0.2 preview 与 v0.2 RenderPlan 证据，同时明确禁止它替换玩家默认 v0.1 地图运行时。
```

已落地：

- `backend/app/services/map_runtime_service.py`：登记三张 MVP 节点的 `MapRuntimePackage v0.2 preview`，提供 v0.2 加载入口。
- `backend/app/services/map_render_plan_service.py`：登记三张 MVP 节点的 v0.2 RenderPlan bundle、语义一致性报告、preview report 和 SVG ref。
- `backend/app/api/frontend_mock.py`：新增 `GET /api/sessions/{session_id}/battles/{node_id}/map-v02-preview`，返回 review-only payload。
- `backend/tests/test_frontend_mock_api.py`：覆盖三张节点的 v0.2 预览接口、unknown node 404，以及默认 `/map-runtime-package` 仍返回 v0.1。
- `docs/FRONTEND_MOCK_API_V0_1.md`、`docs/CURRENT_ARCHITECTURE_INDEX.md`：补充接口边界。
- `examples/worker_task_packs/p1d_map_v02_preview_api.v0.1.json`：记录本轮任务边界和验收命令。

边界：

- 本任务不调用 provider、不读取 `.env`、不改前端玩家默认地图渲染。
- `map-v02-preview` 只供审查 / Studio / 录屏证据使用。
- `runtime_activation_allowed` 必须保持 `false`。
- 默认 `/map-runtime-package` 仍返回 `MapRuntimePackage v0.1`。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1d_map_v02_preview_api.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai-td-pycache-map-v02-preview-api python3 -m py_compile backend/app/api/frontend_mock.py backend/app/services/map_runtime_service.py backend/app/services/map_render_plan_service.py
UV_CACHE_DIR=/tmp/ai-td-uv-cache-map-v02-preview-api uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py -k "map_v02_preview or all_battle_nodes_expose_map_runtime_and_render_plan_packages"
python3 tools/demo/export_evidence.py --output-dir /tmp/map_v02_preview_api_evidence
git diff --check
```

#### P1-D-15 MapRuntimePackage v0.2 API evidence

状态：已完成第一版 TestClient smoke 证据。

目标：

```text
把 review-only MapRuntimePackage v0.2 预览接口纳入可重复演示证据：不只证明静态 JSON 和 RenderPlan 存在，还证明后端 API 能在匿名 session 下读取三张节点的 v0.2 强语义预览，并且默认玩家地图 runtime 仍保持 v0.1。
```

已落地：

- `tools/dev/check_map_v02_preview_api.py`：使用 FastAPI TestClient 创建临时 SQLite session，逐节点请求 `/map-v02-preview` 和默认 `/map-runtime-package`。
- `examples/review_packs/map_v02_preview_api_smoke_report.v0.1.json`：固化本轮通过报告，记录三节点语义计数、默认 v0.1 保留、unknown node 404 和安全摘要。
- `tools/demo/export_evidence.py`：读取 smoke report，新增 `backend_api_evidence.map_v02_preview`，并在 `summary.md` / `index.html` 展示 API smoke 摘要。
- `docs/CURRENT_ARCHITECTURE_INDEX.md`：补充该 evidence 事实源。
- `examples/worker_task_packs/p1d_map_v02_api_evidence.v0.1.json`：记录本轮边界和验收命令。

边界：

- 本任务不调用 provider、不读取 `.env`、不改前端玩家默认地图渲染。
- smoke 工具只使用临时 SQLite 和 TestClient，不写长期 session 数据。
- `map-v02-preview` 仍是 review-only；默认 `/map-runtime-package` 必须保持 `MapRuntimePackage v0.1`。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1d_map_v02_api_evidence.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai-td-pycache-map-v02-api-evidence python3 -m py_compile tools/dev/check_map_v02_preview_api.py tools/demo/export_evidence.py
UV_CACHE_DIR=/tmp/ai-td-uv-cache-map-v02-api-evidence UV_PROJECT_ENVIRONMENT=/tmp/ai-td-uv-venv-map-v02-api-evidence uv run --extra dev python tools/dev/check_map_v02_preview_api.py --output /tmp/map_v02_preview_api_smoke_report.json --generated-at 2026-07-04T00:00:00+00:00
python3 tools/demo/export_evidence.py --output-dir /tmp/map_v02_api_evidence
python3 - <<'PY'
import json
from pathlib import Path
evidence = json.loads(Path('/tmp/map_v02_api_evidence/evidence.json').read_text(encoding='utf-8'))
api = evidence['backend_api_evidence']['map_v02_preview']
assert api['status'] == 'passed'
assert api['node_count'] == 3
assert api['default_runtime_v01_preserved_count'] == 3
assert api['safety']['provider_call_count'] == 0
assert api['runtime_activation_allowed'] is False
PY
git diff --check
```

#### P1-D-16 MVP 主流程 API smoke evidence

状态：已完成第一版本地 HTTP smoke 证据。

目标：

```text
把玩家 MVP 主路径纳入可重复演示证据：通过本地 HTTP 调用走通匿名 session、世界实例、开场、大地图、campaign router、研发 proposal/job、战斗配置、runtime package、地图包、战斗结算和 session evidence，证明后端 mock API 足以支撑当前演示闭环。
```

已落地：

- `tools/dev/check_mvp_primary_api_flow.py`：启动临时 `uvicorn` 服务和临时 SQLite，使用真实 localhost HTTP 请求跑主流程。
- `examples/review_packs/mvp_primary_api_flow_smoke_report.v0.1.json`：固化本轮通过报告，记录 21 个 endpoint step、主节点、研发 job、地图包、结算和安全摘要。
- `tools/demo/export_evidence.py`：读取 smoke report，新增 `backend_api_evidence.mvp_primary_flow`，并在 `summary.md` / `index.html` 展示主流程 smoke 摘要。
- `docs/CURRENT_ARCHITECTURE_INDEX.md`：补充该 evidence 事实源。
- `examples/worker_task_packs/p1d_mvp_primary_api_flow_evidence.v0.1.json`：记录本轮边界和验收命令。

边界：

- 本任务不调用 provider、不读取 `.env`、不改前端玩家默认地图渲染。
- smoke 工具只绑定 `127.0.0.1` 临时端口，使用临时 SQLite，不写长期 session 数据。
- 报告不保存玩家输入正文、玩家长文本、provider 原始输出或 trace 文件路径，只保存计数、状态和脱敏 endpoint 模板。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1d_mvp_primary_api_flow_evidence.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai-td-pycache-mvp-api-flow python3 -m py_compile tools/dev/check_mvp_primary_api_flow.py tools/demo/export_evidence.py
UV_CACHE_DIR=/tmp/ai-td-uv-cache-map-v02-api-evidence-develop UV_PROJECT_ENVIRONMENT=/tmp/ai-td-uv-venv-map-v02-api-evidence-develop uv run --extra dev python tools/dev/check_mvp_primary_api_flow.py --output /tmp/mvp_primary_api_flow_smoke_report.json --generated-at 2026-07-04T00:00:00+00:00
python3 tools/demo/export_evidence.py --output-dir /tmp/mvp_primary_api_flow_evidence
python3 - <<'PY'
import json
from pathlib import Path
evidence = json.loads(Path('/tmp/mvp_primary_api_flow_evidence/evidence.json').read_text(encoding='utf-8'))
flow = evidence['backend_api_evidence']['mvp_primary_flow']
assert flow['status'] == 'passed'
assert flow['passed_step_count'] == flow['step_count'] == 21
assert flow['research']['job_status'] == 'completed'
assert flow['safety']['provider_call_count'] == 0
assert flow['safety']['runtime_activation_mutation_count'] == 0
PY
git diff --check
```

### P1-D-18 MVP demo readiness video boundary evidence

状态：已完成最小对齐。

目标：

```text
把 provider video adapter dry boundary 与 Generation Scheduler video handoff template 纳入 MVP demo readiness 顶层报告，证明视频链路已有受控离线边界，同时明确真实 live video provider 和真实图生视频关键帧仍未进入玩家 runtime。
```

已落地：

- `tools/demo/build_mvp_demo_readiness_report.py`：新增 `provider_video_boundary` 非必需 warning gate。
- `examples/review_packs/mvp_demo_readiness_report.v0.1.json`：重新生成 readiness 报告，保留 `ready_for_mvp_demo_with_known_limitations`，并把 warning gate 数更新为 3。
- `provider_video_boundary` 检查 video receipt / envelope / adapter task pack / handoff task pack，确认 `provider_call_performed=false`、`finish_reason=video_live_provider_not_implemented`、`activation_allowed=false`。
- `docs/CURRENT_ARCHITECTURE_INDEX.md`：同步 readiness 总报告事实源。
- `examples/worker_task_packs/p1d_demo_readiness_video_boundary.v0.1.json`：记录本轮任务包。

边界：

- 该 gate 不接入真实 live video provider，不触发 provider 调用，不读取 `.env`，不生成新媒体。
- 该 gate 不是 MVP 必需门禁；它只把“视频链路已有离线边界”放进演示总报告，避免 readiness 停留在旧状态。
- 真实图生视频关键帧仍需后续接入 RawVideoSequence / FrameSequence / atlas / LoopContinuityReport 门禁。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1d_demo_readiness_video_boundary.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai-td-pycache-demo-readiness-video-boundary python3 -m py_compile tools/demo/build_mvp_demo_readiness_report.py tools/demo/export_evidence.py
python3 tools/demo/build_mvp_demo_readiness_report.py --output /tmp/mvp_demo_readiness_video_boundary_report.json --generated-at 2026-07-05T00:00:00+00:00
python3 tools/demo/build_mvp_demo_readiness_report.py --output examples/review_packs/mvp_demo_readiness_report.v0.1.json --generated-at 2026-07-05T00:00:00+00:00
python3 tools/demo/export_evidence.py --output-dir /tmp/mvp_demo_readiness_video_boundary_evidence
python3 - <<'PY'
import json
from pathlib import Path
report = json.loads(Path('/tmp/mvp_demo_readiness_video_boundary_report.json').read_text(encoding='utf-8'))
assert report['overall_status'] == 'ready_for_mvp_demo_with_known_limitations'
assert report['summary']['blocking_gate_count'] == 0
gates = {gate['gate_id']: gate for gate in report['gates']}
assert gates['provider_video_boundary']['status'] == 'passed_with_warnings'
assert gates['provider_video_boundary']['required_for_mvp_demo'] is False
assert gates['provider_video_boundary']['metrics']['provider_call_performed'] is False
evidence = json.loads(Path('/tmp/mvp_demo_readiness_video_boundary_evidence/evidence.json').read_text(encoding='utf-8'))
readiness_gates = {gate['gate_id']: gate for gate in evidence['mvp_demo_readiness']['gates']}
assert readiness_gates['provider_video_boundary']['status'] == 'passed_with_warnings'
assert evidence['mvp_demo_readiness']['summary']['provider_call_count_by_report'] == 0
PY
git diff --check
```

### P1-D-19 Controlled map candidate artifact import

状态：已完成最小导入边界。

目标：

```text
建立受控地图候选本地 PNG 导入边界：外部 reference-image provider 或人工 paintover 先产出本地 PNG，再通过 import plan / validator / 显式 --copy-files 进入 node_candidates_controlled_v1 候选槽；默认示例不复制图片，只记录 awaiting_local_artifacts。
```

已落地：

- `tools/media/import_controlled_map_candidate_artifacts.py`：读取 `MapControlledRegenerationRequestPack` 与 import plan，默认输出 awaiting report；显式 `--copy-files` 时复制本地 PNG 并刷新 review-only sidecar。
- `tools/media/validate_controlled_map_candidate_artifact_import_report.py`：校验 report、路径边界、PNG sha、provider 调用数和 runtime / published visual layer 修改数。
- `tools/media/build_node_map_candidate_review_pack.py`：识别 `local_artifact_imported_pending_candidate_review` sidecar，并把它标记为 `candidate_review_ready`，仍阻断 runtime promotion。
- `tools/demo/export_evidence.py`：纳入统一 demo evidence 的地图受控候选本地 PNG 导入摘要和静态校验命令。
- `examples/review_packs/controlled_map_candidate_artifact_import_plan.v0.1.json`：默认空 plan，不导入真实图片。
- `examples/review_packs/controlled_map_candidate_artifact_import_report.v0.1.json`：默认报告状态为 `awaiting_local_artifacts`，三张节点等待本地 PNG。
- `examples/worker_task_packs/p1d_controlled_map_candidate_artifact_import.v0.1.json`：记录任务边界。

边界：

- 本任务不调用 provider，不读取 `.env`，不新增真实 PNG，不改 `MapRuntimePackage`，不写 published visual layer，不激活 runtime。
- 真实导入只接受仓库内或 `/tmp` 下本地 PNG，不接受远程 URL。
- 导入后的候选仍必须重新走 candidate / alignment / overlay / visual / explicit promotion gates。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1d_controlled_map_candidate_artifact_import.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai-td-pycache-controlled-map-import python3 -m py_compile tools/media/import_controlled_map_candidate_artifacts.py tools/media/validate_controlled_map_candidate_artifact_import_report.py tools/media/build_node_map_candidate_review_pack.py tools/demo/export_evidence.py
python3 tools/media/import_controlled_map_candidate_artifacts.py --plan examples/review_packs/controlled_map_candidate_artifact_import_plan.v0.1.json --output /tmp/controlled_map_candidate_artifact_import_report.json
python3 tools/media/validate_controlled_map_candidate_artifact_import_report.py /tmp/controlled_map_candidate_artifact_import_report.json
python3 tools/media/import_controlled_map_candidate_artifacts.py --plan examples/review_packs/controlled_map_candidate_artifact_import_plan.v0.1.json --output examples/review_packs/controlled_map_candidate_artifact_import_report.v0.1.json
python3 tools/media/validate_controlled_map_candidate_artifact_import_report.py examples/review_packs/controlled_map_candidate_artifact_import_report.v0.1.json
python3 tools/demo/export_evidence.py --output-dir /tmp/controlled_map_candidate_import_evidence
git diff --check
```

### P1-D-20 Map runtime activation authorization record

状态：已完成最小授权记录层。

目标：

```text
在不激活 MapRuntimePackage v0.2、不修改默认玩家 runtime、不改后端/前端默认行为的前提下，补齐显式开发者激活授权记录层，并让 MapRuntimeActivationGateReport 消费该记录。
```

已落地：

- `tools/media/build_map_runtime_activation_authorization_report.py`：从 readiness 与 activation gate 生成只读授权报告；默认三节点为 `pending_developer_approval`。
- `tools/media/validate_map_runtime_activation_authorization_report.py`：校验授权报告不能伪装成激活，且 provider / runtime / backend / frontend / world 修改数为 0。
- `tools/media/build_map_runtime_activation_gate_report.py`：读取授权报告；当前 blocker 从 `explicit_developer_activation_approval_missing` 收敛为 `explicit_developer_activation_not_approved`。
- `tools/demo/export_evidence.py`：纳入授权报告静态校验与 evidence 摘要。
- `examples/review_packs/map_runtime_activation_authorization_report.v0.1.json`：默认授权记录报告。

边界：

- 本任务不批准 v0.2 激活，不修改 `examples/map_runtime_packages/`，不修改后端默认 `/map-runtime-package`，不修改前端默认战斗地图消费。
- 即使未来授权为 approved，也只解除“开发者授权”这一项；当前后端 selector 与前端消费预接入由 P1-D-32 / P1-D-33 证明，但仍必须保持 review-only/拒绝候选隔离并复跑激活后证据。

验收：

```bash
python3 tools/media/build_map_runtime_activation_authorization_report.py --output examples/review_packs/map_runtime_activation_authorization_report.v0.1.json
python3 tools/media/validate_map_runtime_activation_authorization_report.py examples/review_packs/map_runtime_activation_authorization_report.v0.1.json
python3 tools/media/build_map_runtime_activation_gate_report.py --output examples/review_packs/map_runtime_activation_gate_report.v0.1.json
python3 tools/media/validate_map_runtime_activation_gate_report.py examples/review_packs/map_runtime_activation_gate_report.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai-td-pycache-map-runtime-auth python3 -m py_compile tools/media/build_map_runtime_activation_authorization_report.py tools/media/validate_map_runtime_activation_authorization_report.py tools/media/build_map_runtime_activation_gate_report.py tools/demo/export_evidence.py
python3 tools/demo/export_evidence.py --output-dir /tmp/map_runtime_activation_authorization_evidence
git diff --check
```

### P1-D-21 Map runtime v0.2 opt-in dry-run contract

状态：已完成最小 opt-in 合同证据。

目标：

```text
在默认玩家 runtime 仍保持 MapRuntimePackage v0.1 的前提下，补一个 review-only v0.2 opt-in dry-run 合同，证明显式授权后 v0.2 候选包可以被安全读取，但不会自动激活 runtime。
```

已落地：

- `backend/app/services/map_runtime_service.py`：新增 `get_map_runtime_v02_opt_in_contract()`，默认读取授权报告；只有授权为 `approved_for_gate_review` 且目标匹配时才返回完整 v0.2 候选包。
- `backend/app/api/frontend_mock.py`：新增 `GET /api/sessions/{session_id}/battles/{node_id}/map-v02-opt-in-dry-run`，默认仍 pending / review-only / runtime_activation_allowed=false。
- `tools/dev/check_map_runtime_v02_opt_in_contract.py`：用本地 uvicorn HTTP 检查默认 API pending，并用临时 approved 授权夹具检查 service-level v0.2 候选可读。
- `tools/dev/validate_map_runtime_v02_opt_in_contract_report.py`：校验 opt-in smoke 报告。
- `tools/frontend/validate_battle_visual_contract.py`：阻止默认前端拉取 `map-v02-preview` 或 `map-v02-opt-in-dry-run`。
- `tools/demo/export_evidence.py`：纳入 opt-in 合同 smoke 摘要。

边界：

- 不修改 `examples/map_runtime_packages/`，不把默认 `/map-runtime-package` 指向 v0.2。
- 不让前端默认消费 v0.2 preview 或 opt-in dry-run endpoint。
- 不把临时 approved 授权夹具提交为默认授权状态；它只存在于 smoke 的 `/tmp` 临时目录。
- 不调用 provider，不读取 `.env`，不写世界状态，不激活 runtime。

验收：

```bash
/home/zty/projects/ai-compiled-towerdefense/.venv/bin/python tools/dev/check_map_runtime_v02_opt_in_contract.py --output examples/review_packs/map_runtime_v02_opt_in_contract_smoke_report.v0.1.json --generated-at 2026-07-05T00:00:00+00:00
python3 tools/dev/validate_map_runtime_v02_opt_in_contract_report.py examples/review_packs/map_runtime_v02_opt_in_contract_smoke_report.v0.1.json
python3 tools/frontend/validate_battle_visual_contract.py
PYTHONPYCACHEPREFIX=/tmp/ai-td-pycache-v02-opt-in-final python3 -m py_compile backend/app/services/map_runtime_service.py backend/app/api/frontend_mock.py tools/dev/check_map_runtime_v02_opt_in_contract.py tools/dev/validate_map_runtime_v02_opt_in_contract_report.py tools/frontend/validate_battle_visual_contract.py tools/demo/export_evidence.py
python3 tools/demo/export_evidence.py --output-dir /tmp/map_runtime_v02_opt_in_contract_evidence
git diff --check
```

### P1-D-22 Map runtime v0.2 activation contract plan

状态：已完成最小激活前合同计划证据。

目标：

```text
在不激活 MapRuntimePackage v0.2、不修改默认玩家 runtime、不改后端/前端默认行为的前提下，把 activation gate 中“合同预接入状态和激活后证据复跑”的阻断项展开成可审查、可校验的计划层；当前后端 selector 预接入由 P1-D-32 / P1-D-33 补齐。
```

已落地：

- `tools/media/build_map_runtime_v02_activation_contract_plan.py`：读取 activation gate、activation authorization、opt-in smoke、promotion readiness 和 v0.2 API smoke，生成计划报告。
- `tools/media/validate_map_runtime_v02_activation_contract_plan.py`：校验计划层必须保持 `plan_only` / `read_model_only`，且 activation allowed、apply-now、runtime/backend/frontend/world/provider 修改均为 0 / false。
- `examples/review_packs/map_runtime_v02_activation_contract_plan.v0.1.json`：三节点均记录 v0.1 -> v0.2 目标候选、当前 gate blocker、默认 API v0.1 保留、approved fixture v0.2 语义可读、前端强语义消费 `pre_activation_ready`，以及未应用的后端/evidence 合同计划；当前后端 selector 已由 P1-D-32 / P1-D-33 标记为 `pre_activation_ready`。
- `tools/demo/export_evidence.py`：纳入该计划摘要、校验项、Markdown/HTML 展示，并在导出时断言计划不得激活或修改默认 runtime / backend / frontend 合同。

边界：

- 这不是激活任务，不写 `examples/map_runtime_packages/`，不让默认 `/map-runtime-package` 指向 v0.2。
- 不让默认前端读取 `map-v02-preview` 或 `map-v02-opt-in-dry-run`。
- 不新增与 `MapRuntimePackage` 竞争的 `LevelBundle` / `PathGraph` / `PlacementMap` 并列运行时事实源。
- 不从图片、SVG、preview 或 AI candidate 中反推路线、塔位、资源点、机关、阻挡或碰撞。
- 不调用 provider，不读取 `.env`，不写世界状态。

验收：

```bash
python3 tools/media/build_map_runtime_v02_activation_contract_plan.py
python3 tools/media/validate_map_runtime_v02_activation_contract_plan.py examples/review_packs/map_runtime_v02_activation_contract_plan.v0.1.json
python3 -m py_compile tools/media/build_map_runtime_v02_activation_contract_plan.py tools/media/validate_map_runtime_v02_activation_contract_plan.py tools/demo/export_evidence.py
python3 tools/demo/export_evidence.py --output-dir /tmp/map_runtime_v02_activation_contract_plan_evidence
git diff --check
```

### P1-D-23 Frontend v0.2 map strong semantics consumption

状态：已完成最小前端消费合同。

目标：

```text
在不激活 MapRuntimePackage v0.2、不修改后端默认 runtime、不让玩家前端读取 review-only endpoint 的前提下，让战斗画面具备消费 v0.2 强语义字段的能力。后续一旦默认 runtime 显式切到携带强语义字段的包，前端无需再重写绘制入口。
```

已落地：

- `frontend/app.js`：新增 `mapResourceNodes()`、`mapHazardZones()`、`mapDefenseAnchors()`、`mapBlockedAreas()`，统一从 `mapRuntimePackage()` 读取可选强语义字段。
- `frontend/app.js`：新增 `routePointAtT()` 与 `routeSamplesBetween()`，让机关区按 `anchor_route_id` + `path_t_range` 绑定 runtime route，而不是从图片或预览图反推。
- `frontend/app.js`：新增 `drawMapRuntimeStrongSemantics()`，在道路层之后、部署提示和实体之前绘制阻挡区、机关区、资源点和防守锚点。
- `tools/frontend/validate_battle_visual_contract.py`：静态合约新增 v0.2 强语义消费检查，并确认默认前端仍不请求 `map-v02-preview` / `map-v02-opt-in-dry-run`。

边界：

- 不改变 `backend/app/services/map_runtime_service.py` 的 v0.1 默认加载路径。
- 不把 `examples/map_runtime_packages_v02/` 发布为默认玩家 runtime。
- 不从图片、SVG、preview、AI candidate 或 review-only endpoint 反推资源点、机关区、防守锚点、阻挡或碰撞。
- 不调用 provider，不读取 `.env`，不写世界状态。

验收：

```bash
python3 tools/frontend/validate_battle_visual_contract.py
python3 -c "import py_compile; py_compile.compile('tools/frontend/validate_battle_visual_contract.py', cfile='/tmp/validate_battle_visual_contract.pyc', doraise=True)"
node --check frontend/app.js
python3 tools/demo/export_evidence.py --output-dir /tmp/frontend_v02_map_semantics_evidence_develop
git diff --check
```

### P1-D-24 MVP demo readiness activation contract gate

状态：已完成顶层 readiness 同步。

目标：

```text
让 MVP demo readiness 顶层报告反映当时的 v0.2 地图激活状态；当前口径已由 P1-D-32 / P1-D-33 继续更新为：前端强语义消费与后端 selector 均已预接入，但默认 runtime 仍保持 v0.1，正式激活仍需要开发者授权和激活后证据复跑。
```

已落地：

- `tools/demo/build_mvp_demo_readiness_report.py`：新增 `map_runtime_activation_contract` 非必需 warning gate，读取 `MapRuntimeActivationGateReport` 与 `MapRuntimeV02ActivationContractPlan`。
- `examples/review_packs/mvp_demo_readiness_report.v0.1.json`：重新生成，`overall_status` 仍为 `ready_for_mvp_demo_with_known_limitations`，required gate 不增加，warning gate 记录 v0.2 activation 合同状态。
- `docs/CURRENT_ARCHITECTURE_INDEX.md` 与本任务队列：同步 readiness 报告的新证据边界。

边界：

- 不激活 `MapRuntimePackage v0.2`。
- 不修改后端默认 `/map-runtime-package`。
- 不调用 provider，不读取 `.env`，不写世界状态。

验收：

```bash
python3 tools/demo/build_mvp_demo_readiness_report.py --output examples/review_packs/mvp_demo_readiness_report.v0.1.json --generated-at 2026-07-05T00:00:00+00:00
python3 -c "import json; r=json.load(open('examples/review_packs/mvp_demo_readiness_report.v0.1.json')); g={x['gate_id']:x for x in r['gates']}; assert r['overall_status']=='ready_for_mvp_demo_with_known_limitations'; assert g['map_runtime_activation_contract']['status']=='passed_with_warnings'; assert g['map_runtime_activation_contract']['metrics']['activation_allowed_count']==0"
python3 tools/demo/export_evidence.py --output-dir /tmp/mvp_readiness_activation_contract_evidence
git diff --check
```

### P1-D-25 MVP demo readiness map v0.2 semantic geometry gate

状态：已完成顶层 readiness 同步。

目标：

```text
让 MVP demo readiness 顶层报告把 MapRuntimePackage v0.2 强语义几何一致性作为必需 gate，而不是只停留在独立 review evidence。
```

已落地：

- `tools/demo/build_mvp_demo_readiness_report.py`：新增 `map_runtime_v02_semantic_geometry` 必需 gate，读取 `MapRuntimeV02SemanticGeometryReport`。
- `examples/review_packs/mvp_demo_readiness_report.v0.1.json`：重新生成，`overall_status` 仍为 `ready_for_mvp_demo_with_known_limitations`；required gate 从 7 增加到 8，新增 gate 当前为 `passed_with_warnings`。
- `docs/CURRENT_ARCHITECTURE_INDEX.md`、`docs/MAP_COMPILATION_DESIGN_V0_1.md` 与本任务队列：同步 readiness 报告的新证据边界。

边界：

- 只读取 `examples/review_packs/map_runtime_v02_semantic_geometry_report.v0.1.json`。
- 不激活 `MapRuntimePackage v0.2`，不修改后端默认 `/map-runtime-package`，不修改前端默认 fetch 路径。
- 不调用 provider，不读取 `.env`，不写世界状态，不从图片 / SVG / preview / AI candidate 反推地图语义。

验收：

```bash
python3 tools/demo/build_mvp_demo_readiness_report.py --output examples/review_packs/mvp_demo_readiness_report.v0.1.json --generated-at 2026-07-05T00:00:00+00:00
python3 -c "import json; r=json.load(open('examples/review_packs/mvp_demo_readiness_report.v0.1.json')); g={x['gate_id']:x for x in r['gates']}; assert r['overall_status']=='ready_for_mvp_demo_with_known_limitations'; assert g['map_runtime_v02_semantic_geometry']['required_for_mvp_demo'] is True; assert g['map_runtime_v02_semantic_geometry']['status']=='passed_with_warnings'; assert g['map_runtime_v02_semantic_geometry']['metrics']['error_count']==0; assert g['map_runtime_v02_semantic_geometry']['metrics']['provider_call_count']==0"
python3 tools/demo/export_evidence.py --output-dir /tmp/mvp_readiness_map_v02_semantic_geometry_evidence
git diff --check
```

### P1-D-26 MVP demo readiness battle visual contract gate

状态：已完成顶层 readiness 同步。

目标：

```text
让 MVP demo readiness 顶层报告把前端战斗视觉合同作为必需 gate，避免默认战斗画面回退到控制图、失败整图、棋盘、虚线调试线或小面板式地图。
```

已落地：

- `tools/frontend/validate_battle_visual_contract.py`：保留原 CLI 文本输出，并新增 `--report-output` 结构化报告输出。
- `examples/review_packs/battle_visual_contract_report.v0.1.json`：固化当前通过报告，记录 app / CSS / 地图层错误数、三张 v0.1 地图包和三张 v0.2 preview 包覆盖。
- `tools/demo/build_mvp_demo_readiness_report.py`：新增 `battle_visual_contract` MVP 必需 gate，读取上述报告。
- `tools/demo/export_evidence.py`：统一 demo evidence 静态校验会复跑 `validate_battle_visual_contract.py --report-output /tmp/...`。
- `examples/review_packs/mvp_demo_readiness_report.v0.1.json`：重新生成，`overall_status` 仍为 `ready_for_mvp_demo_with_known_limitations`；required gate 从 8 增加到 9，新增 gate 当前为 `passed`。

边界：

- 该 gate 是静态视觉合同，不替代真实浏览器截图和人工观感验收。
- 不调用 provider，不读取 `.env`，不写世界状态，不修改 runtime package。
- 不激活 `MapRuntimePackage v0.2`，不允许默认前端请求 review-only v0.2 preview / opt-in endpoint。

验收：

```bash
python3 tools/frontend/validate_battle_visual_contract.py --report-output examples/review_packs/battle_visual_contract_report.v0.1.json --generated-at 2026-07-06T00:00:00+00:00
python3 tools/demo/build_mvp_demo_readiness_report.py --output examples/review_packs/mvp_demo_readiness_report.v0.1.json --generated-at 2026-07-06T00:00:00+00:00
python3 -c "import json; r=json.load(open('examples/review_packs/mvp_demo_readiness_report.v0.1.json')); g={x['gate_id']:x for x in r['gates']}; assert r['overall_status']=='ready_for_mvp_demo_with_known_limitations'; assert g['battle_visual_contract']['required_for_mvp_demo'] is True; assert g['battle_visual_contract']['status']=='passed'; assert g['battle_visual_contract']['metrics']['error_count']==0"
python3 tools/demo/export_evidence.py --output-dir /tmp/mvp_readiness_battle_visual_contract_evidence
git diff --check
```

### P1-D-27 MVP demo readiness frontend flow actual smoke

状态：已完成最小接线。

目标：

```text
让 MVP demo readiness 在录屏 / 评审前可以消费真实浏览器玩家链路截图报告，而不是只证明截图 harness 存在。
```

已落地：

- `tools/demo/build_mvp_demo_readiness_report.py`：新增 `--frontend-flow-smoke-report` 参数；传入真实 `frontend_flow_visual_smoke_report.v0.1.json` 后，`frontend_flow_visual_smoke_harness` gate 会以 `actual_report` 模式校验 captured / 14 screenshots / desktop+mobile / 7 steps / safety summary。
- 默认不传该参数时，repo 固化 readiness 仍保持 `harness_only` 模式，适合无浏览器环境离线重建。
- `tools/demo/export_evidence.py`：当收到 `--frontend-flow-smoke-report` 时，会动态构建带 actual flow smoke gate 的 readiness 摘要，而不是只读取仓库内静态 readiness 文件。
- `tools/demo/run_demo_evidence_suite.py` 已经会把截图报告传给 `export_evidence.py`，因此演示套件输出会展示 actual screenshot gate。

边界：

- 不提交截图 PNG 或 `/tmp` 报告到仓库。
- 不调用 provider，不读取 `.env`，不写世界状态，不激活 runtime。
- actual report 只在本地 evidence bundle / demo suite 输出中体现；仓库 fixture 继续保留可复现的 harness-only readiness。

验收：

```bash
python3 tools/demo/build_mvp_demo_readiness_report.py --output /tmp/mvp_readiness_harness_only.json --generated-at 2026-07-06T00:00:00+00:00
python3 tools/frontend/capture_frontend_flow_visual_smoke.py --output-dir /tmp/frontend_flow_visual_smoke_actual --timeout 45
python3 tools/frontend/validate_frontend_flow_visual_smoke_report.py /tmp/frontend_flow_visual_smoke_actual/frontend_flow_visual_smoke_report.v0.1.json
python3 tools/demo/build_mvp_demo_readiness_report.py --output /tmp/mvp_readiness_actual_flow.json --generated-at 2026-07-06T00:00:00+00:00 --frontend-flow-smoke-report /tmp/frontend_flow_visual_smoke_actual/frontend_flow_visual_smoke_report.v0.1.json
python3 tools/demo/export_evidence.py --output-dir /tmp/mvp_evidence_actual_flow --frontend-flow-smoke-report /tmp/frontend_flow_visual_smoke_actual/frontend_flow_visual_smoke_report.v0.1.json
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

### P1-E-2 WorkerTaskPack acceptance command profiles

状态：已完成小范围协议扩展。

目标：

```text
给 WorkerTaskPack v0.1 增加可选验收命令 profile 机制，让日常小改可默认运行快速质量门和 summary-only evidence，同时保留最终评审 / 录屏 / release gate 的完整 evidence 或 demo suite 命令。
```

已落地：

- `shared/schemas/worker_task_pack.v0.1.schema.json`：新增可选 `acceptance_profile`，包含 `default_profile` 和 `profiles`。
- `tools/dev/validate_worker_task_pack.py`：在 profile 存在时校验默认 profile 指向、profile 字段、命令禁用片段复用，以及 `daily_fast` 不得包含默认完整 `tools/demo/export_evidence.py --output-dir`。
- `docs/WORKER_TASK_PACK_V0_1.md`、`docs/CURRENT_ARCHITECTURE_INDEX.md`：说明 `daily_fast`、`full_evidence`、`release_gate` 的推荐语义和边界。
- `examples/worker_task_packs/p1e_worker_acceptance_command_profiles.v0.1.json`：新增示例任务包，默认 `daily_fast`，最终评审使用 `full_evidence`，录屏 / release candidate 使用 `release_gate`。

边界：

- `acceptance_commands` 仍保持必填和兼容；旧任务包不需要新增 profile。
- profile 是验收分层，不是降低质量；`daily_fast` 只用于日常快速反馈，合并前 / 最终评审 / 录屏前仍需按风险运行完整 evidence 或 demo suite。
- 本任务不修改 `backend/`、`frontend/`、`examples/review_packs/`、`game_data/`、`.env` 或默认 runtime/package 文件。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1e_worker_acceptance_command_profiles.v0.1.json
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1e_worker_task_pack_protocol.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_worker_acceptance_profiles python3 -m py_compile tools/dev/validate_worker_task_pack.py
python3 tools/dev/run_fast_quality_gate.py --output /tmp/worker_acceptance_profiles_fast_gate.json
python3 tools/demo/export_evidence.py --validation-profile summary-only --output-dir /tmp/worker_acceptance_profiles_summary_only_evidence
git diff --check
```

### P1-E-3 WorkerTaskPack acceptance profile runner

状态：已完成本地 runner。

目标：

```text
按 WorkerTaskPack 的 acceptance_profile 安全执行验收命令，输出结构化报告，并避免旧任务包或 shell-only 命令被误执行。
```

已落地：

- `tools/dev/run_worker_acceptance_profile.py`：新增 profile runner，复用 `validate_worker_task_pack.py` 的 `validate()`，支持 `--profile`、`--list-profiles`、`--dry-run`、`--output`、`--fail-fast` 和 `--timeout`。
- `tools/dev/run_fast_quality_gate.py`：把 runner 纳入自身 `py_compile`。
- `docs/WORKER_TASK_PACK_V0_1.md`、`docs/CURRENT_ARCHITECTURE_INDEX.md`：补 runner 用法和安全边界。
- `examples/worker_task_packs/p1e_worker_acceptance_command_profiles.v0.1.json`：顶层 `acceptance_commands` 补实际 `daily_fast` runner 命令。

边界：

- runner 不使用 shell；只用 `shlex.split` 解析 argv，并支持前置环境变量 token。
- 管道、非受限重定向、逻辑连接、反引号和 `$(` 命令替换会被拒绝为 `unsupported_command_syntax`，不会执行。
- 没有 `acceptance_profile` 的旧包直接失败，提示手动运行 `acceptance_commands`。
- 本任务不修改 `backend/`、`frontend/`、`examples/review_packs/`、`game_data/`、`.env` 或默认 runtime/package 文件。

验收：

```bash
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_worker_acceptance_runner python3 -m py_compile tools/dev/run_worker_acceptance_profile.py tools/dev/validate_worker_task_pack.py
python3 tools/dev/run_worker_acceptance_profile.py examples/worker_task_packs/p1e_worker_acceptance_command_profiles.v0.1.json --list-profiles
python3 tools/dev/run_worker_acceptance_profile.py examples/worker_task_packs/p1e_worker_acceptance_command_profiles.v0.1.json --dry-run --output /tmp/worker_acceptance_runner_dry_run.json
python3 tools/dev/run_worker_acceptance_profile.py examples/worker_task_packs/p1e_worker_acceptance_command_profiles.v0.1.json --profile daily_fast --output /tmp/worker_acceptance_runner_daily_fast.json
python3 tools/dev/run_fast_quality_gate.py --output /tmp/worker_acceptance_runner_fast_gate.json
git diff --check
```

### P1-E-4 WorkerTaskPack acceptance profile migration audit

状态：已完成只读审计工具。

目标：

```text
审计现有 WorkerTaskPack 是否已经迁移到 acceptance_profile，指出哪些旧包适合迁移、哪些命令需要人工处理，并保证审计过程不执行旧包验收命令、不修改旧包。
```

已落地：

- `tools/dev/audit_worker_acceptance_profiles.py`：新增只读审计 CLI，默认扫描 `examples/worker_task_packs`，默认输出 `/tmp/worker_acceptance_profile_audit_report.v0.1.json`，复用 `validate_worker_task_pack.validate()` 和 `run_worker_acceptance_profile.parse_command()`。
- `tools/dev/run_worker_acceptance_profile.py`：补充拒绝分号连接命令，避免 `python3 a.py;python3 b.py` 这类 shell-only 写法被误判为 runner 兼容。
- `tools/dev/run_fast_quality_gate.py`：把审计脚本纳入自身 `py_compile`。
- `docs/WORKER_TASK_PACK_V0_1.md`、`docs/CURRENT_ARCHITECTURE_INDEX.md`：补审计用法、输出 schema、sample lists 和只读边界。
- `examples/worker_task_packs/p1e_worker_acceptance_profile_audit.v0.1.json`：新增示例任务包，说明审计只生成报告和迁移建议，不修改旧任务包。

边界：

- 审计不执行任何被扫描任务包里的 `acceptance_commands` 或 `acceptance_profile` 命令。
- 复杂 shell 命令、here-doc、管道、非受限重定向、分号连接、逻辑连接和命令替换只会进入 manual review 清单，不会让整次 audit 失败。
- 迁移候选定义为无 `acceptance_profile` 且 validator 通过的旧包；若顶层含完整 `tools/demo/export_evidence.py --output-dir`，建议拆成 `daily_fast` 的快速 / summary-only profile 与 `full_evidence` 的完整证据 profile。
- 本任务不修改 `backend/`、`frontend/`、`examples/review_packs/`、`game_data/`、`.env` 或默认 runtime/package 文件。

验收：

```bash
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_worker_acceptance_audit python3 -m py_compile tools/dev/audit_worker_acceptance_profiles.py tools/dev/run_worker_acceptance_profile.py tools/dev/validate_worker_task_pack.py
python3 tools/dev/audit_worker_acceptance_profiles.py --output /tmp/worker_acceptance_profile_audit_report.json --max-samples 8
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1e_worker_acceptance_profile_audit.v0.1.json
python3 tools/dev/run_worker_acceptance_profile.py examples/worker_task_packs/p1e_worker_acceptance_profile_audit.v0.1.json --profile daily_fast --output /tmp/worker_acceptance_profile_audit_runner.json
python3 tools/dev/run_fast_quality_gate.py --output /tmp/worker_acceptance_profile_audit_fast_gate.json
git diff --check
```

### P1-E-5 WorkerTaskPack acceptance profile migrator

状态：已完成安全迁移工具与首个样例迁移。

目标：

```text
在只读审计之后补一个安全迁移器：默认只输出报告，只有显式 --write 才给 runner-compatible 的 WorkerTaskPack 写入 acceptance_profile，并跳过 shell-only 命令包。
```

已落地：

- `tools/dev/migrate_worker_acceptance_profiles.py`：新增迁移器 CLI，默认 report-only，输出 `/tmp/worker_acceptance_profile_migration_report.v0.1.json`。
- `tools/dev/check_worker_acceptance_profile_migrator.py`：新增临时目录 smoke，验证 eligible 包会迁移，shell-only 包会跳过，且不执行验收命令、不调用 provider。
- `examples/worker_task_packs/p1d_map_v02_preview_api.v0.1.json`：作为首个 runner-compatible 样例，新增 `daily_fast` / `full_evidence` profile；原 `acceptance_commands` 保留。
- `examples/worker_task_packs/p1e_worker_acceptance_profile_migrator.v0.1.json`：新增本轮任务包。

边界：

- 迁移器默认不修改仓库；必须显式 `--write` 才会写入。
- 只迁移 validator 通过且顶层 `acceptance_commands` 全部可由 profile runner 解析的旧任务包。
- 含 heredoc、分号、管道、非受限重定向、逻辑连接或命令替换的包只进入 skip / manual review，不自动改写。
- 本任务不修改 `backend/`、`frontend/`、`examples/review_packs/`、`game_data/`、`.env` 或 runtime package。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1e_worker_acceptance_profile_migrator.v0.1.json
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1d_map_v02_preview_api.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_worker_profile_migrator python3 -m py_compile tools/dev/migrate_worker_acceptance_profiles.py tools/dev/check_worker_acceptance_profile_migrator.py tools/dev/audit_worker_acceptance_profiles.py tools/dev/run_worker_acceptance_profile.py
python3 tools/dev/check_worker_acceptance_profile_migrator.py --output /tmp/worker_profile_migrator_smoke.json
python3 tools/dev/migrate_worker_acceptance_profiles.py --task-pack examples/worker_task_packs/p1b_campaign_router_dispatcher_prefetch.v0.1.json --output /tmp/worker_profile_migrator_campaign_router_dry.json
python3 tools/dev/run_worker_acceptance_profile.py examples/worker_task_packs/p1d_map_v02_preview_api.v0.1.json --profile daily_fast --dry-run --output /tmp/map_v02_preview_api_profile_dry_run.json
python3 tools/dev/run_fast_quality_gate.py --output /tmp/worker_profile_migrator_fast_gate.json
git diff --check
```

### P1-E-6 Demo suite task pack acceptance profiles

状态：已完成高频 demo suite 包 profile 迁移。

目标：

```text
把 demo evidence suite 相关任务包里的 shell-only 报告断言收束成标准 validator，并补 acceptance_profile，让 profile runner 能直接运行高频 demo / quality gate 验收。
```

已落地：

- `tools/demo/validate_demo_evidence_suite_report.py`：新增 suite report validator，只检查报告状态、浏览器降级边界、scheduler/outbox 摘要、安全计数和输出文件存在性，不重新实现 suite 子流程。
- `p1d_demo_evidence_suite_runner.v0.1.json`、`p1d_demo_suite_scheduler_pipeline_smoke.v0.1.json`、`p1d_demo_suite_scheduler_runner_selection.v0.1.json`、`p1d_demo_suite_outbox_import_smoke.v0.1.json`：将 heredoc / `python3 -c` 断言替换为 validator 命令，并补 `daily_fast` profile；一键 suite runner 额外保留 `release_gate` profile 要求真实浏览器 captured。
- `examples/worker_task_packs/p1e_worker_acceptance_suite_profiles.v0.1.json`：新增本轮任务包。

边界：

- `daily_fast` 允许 `--allow-missing-browser`，用于日常无浏览器环境；录屏 / release candidate 应运行 `release_gate` 或显式不允许浏览器降级。
- validator 不调用 provider、不读取 `.env`、不写世界状态、不激活 runtime，也不替代 `run_demo_evidence_suite.py`。
- 本任务不修改 `backend/`、`frontend/`、`game_data/`、`examples/review_packs/` 或 runtime package。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1e_worker_acceptance_suite_profiles.v0.1.json
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1d_demo_evidence_suite_runner.v0.1.json
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1d_demo_suite_scheduler_pipeline_smoke.v0.1.json
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1d_demo_suite_scheduler_runner_selection.v0.1.json
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1d_demo_suite_outbox_import_smoke.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_suite_profiles python3 -m py_compile tools/demo/validate_demo_evidence_suite_report.py tools/demo/run_demo_evidence_suite.py tools/dev/run_worker_acceptance_profile.py tools/dev/audit_worker_acceptance_profiles.py
python3 tools/demo/run_demo_evidence_suite.py --allow-missing-browser --output-root /tmp/ai_td_suite_profile_check --command-timeout 180
python3 tools/demo/validate_demo_evidence_suite_report.py /tmp/ai_td_suite_profile_check/demo_evidence_suite_report.v0.1.json --allow-browser-unavailable --require-scheduler-pipeline-smoke --require-outbox-import-smoke
python3 tools/dev/run_worker_acceptance_profile.py examples/worker_task_packs/p1d_demo_suite_scheduler_pipeline_smoke.v0.1.json --profile daily_fast --dry-run --output /tmp/p1d_scheduler_pipeline_profile_dry.json
python3 tools/dev/run_worker_acceptance_profile.py examples/worker_task_packs/p1d_demo_suite_outbox_import_smoke.v0.1.json --profile daily_fast --dry-run --output /tmp/p1d_outbox_import_profile_dry.json
python3 tools/dev/audit_worker_acceptance_profiles.py --output /tmp/worker_acceptance_profile_audit_after_suite_profiles.json --max-samples 20
python3 tools/dev/run_fast_quality_gate.py --output /tmp/suite_profiles_fast_gate.json
git diff --check
```

### P1-E-7 WorkerTaskPack runner regex pipe arguments

状态：已完成 profile runner / audit 解析修正。

目标：

```text
让 acceptance profile runner 允许 `rg "a|b"` 这类安全正则参数，同时继续拒绝真正的 shell 管道、非受限重定向、heredoc、分号连接和命令替换。
```

已落地：

- `tools/dev/run_worker_acceptance_profile.py`：`parse_command()` 不再把参数内部的 `|` 一律视为 shell-only；只拒绝独立管道 token `|` / `|&`，并继续拒绝 `<`、非受限 `>`、`;`、反引号和 `$(`。
- `tools/dev/audit_worker_acceptance_profiles.py`：移除 raw string 级别的 `|` 预筛，统一以 runner parser 的结果作为兼容性判断。
- `examples/worker_task_packs/p1e_worker_acceptance_pipe_args.v0.1.json`：新增本轮任务包。

效果：

- 审计 manual review 数从 45 降到 21。
- 24 条 `rg "pattern_a|pattern_b"` 任务命令变成 runner-compatible 迁移候选。
- 真正的 `cmd | cmd2`、heredoc、非受限重定向和分号连接仍会被拒绝。

边界：

- 本任务不执行被审计任务包的验收命令。
- 本任务不修改任何历史任务包、不调用 provider、不读取 `.env`、不改 runtime / backend / frontend。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1e_worker_acceptance_pipe_args.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_pipe_args python3 -m py_compile tools/dev/run_worker_acceptance_profile.py tools/dev/audit_worker_acceptance_profiles.py tools/dev/check_worker_acceptance_profile_pipe_args.py
python3 tools/dev/check_worker_acceptance_profile_pipe_args.py --output /tmp/worker_acceptance_profile_pipe_args_smoke.json
python3 tools/dev/audit_worker_acceptance_profiles.py --output /tmp/worker_acceptance_profile_pipe_args_audit.json --max-samples 20
python3 tools/dev/run_fast_quality_gate.py --output /tmp/worker_acceptance_pipe_args_fast_gate.json
git diff --check
```

### P1-E-8 WorkerTaskPack runner Python -c semicolon arguments

状态：已完成 profile runner / audit 解析修正。

目标：

```text
让 acceptance profile runner 允许 `python3 -c "import json; print(...)"` 这类安全代码参数，同时继续拒绝真正的 shell 分号连接、非受限重定向、管道、逻辑连接和命令替换。
```

已落地：

- `tools/dev/run_worker_acceptance_profile.py`：`parse_command()` 只在 `python* -c` 的最后一个代码 argv 中允许 `;`，并继续拒绝 `cmd1; cmd2`、非 final argv 分号、非受限重定向、独立管道 token、逻辑连接、反引号和 `$(`。
- `tools/dev/check_worker_acceptance_profile_python_c.py`：新增 parser smoke，覆盖安全 `python -c` 代码参数和三个拒绝样例。
- `examples/worker_task_packs/p1e_worker_acceptance_python_c_semicolon.v0.1.json`：新增本轮任务包。

效果：

- 审计 manual review 数从 21 降到 19。
- 2 条 `python3 -c` 临时断言变成 runner-compatible 迁移候选。
- heredoc、非受限重定向和真实 shell 连接仍留在人工处理清单。

边界：

- 本任务不执行被审计任务包的验收命令。
- 本任务不修改任何历史任务包、不调用 provider、不读取 `.env`、不改 runtime / backend / frontend。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1e_worker_acceptance_python_c_semicolon.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_python_c_semicolon python3 -m py_compile tools/dev/run_worker_acceptance_profile.py tools/dev/audit_worker_acceptance_profiles.py tools/dev/check_worker_acceptance_profile_python_c.py
python3 tools/dev/check_worker_acceptance_profile_python_c.py --output /tmp/worker_acceptance_profile_python_c_smoke.json
python3 tools/dev/audit_worker_acceptance_profiles.py --output /tmp/worker_acceptance_profile_python_c_audit.json --max-samples 80
python3 tools/dev/run_fast_quality_gate.py --output /tmp/worker_acceptance_python_c_semicolon_fast_gate.json
git diff --check
```

### P1-E-9 WorkerTaskPack runner safe stdout redirect

状态：已完成 profile runner / audit 解析修正。

目标：

```text
让 acceptance profile runner 支持 `python3 -m json.tool schema.json >/tmp/out.json` 这类安全 stdout 重定向，同时继续拒绝 stdin、stderr、append、非 /tmp、非 final 重定向和真实 shell 连接。
```

已落地：

- `tools/dev/run_worker_acceptance_profile.py`：`parse_command()` 支持最终 token 形式的 `> /tmp/file` 或 `>/tmp/file`，目标必须是仓库外 `/tmp` 下文件；其他重定向仍拒绝。
- `tools/dev/command_runner.py`：新增可选 `stdout_path`，由 runner 捕获 stdout 后写入目标文件，命令仍不经过 shell。
- `tools/dev/check_worker_acceptance_profile_stdout_redirect.py`：新增 parser + execution smoke，覆盖 compact / spaced stdout redirect、实际写文件和拒绝样例。
- 更新 pipe / Python `-c` smoke 的拒绝样例，避免把安全 `/tmp` stdout redirect 继续当成必须失败。
- `examples/worker_task_packs/p1e_worker_acceptance_stdout_redirect.v0.1.json`：新增本轮任务包。

效果：

- 审计 manual review 数从 19 降到 16。
- 3 条 `python3 -m json.tool ... >/tmp/...` 旧验收命令变成 runner-compatible 迁移候选。
- heredoc、多命令脚本、stdin/stderr/append/非 final 重定向仍留在人工处理清单。

边界：

- 本任务不执行被审计任务包的验收命令。
- 本任务不修改任何历史任务包、不调用 provider、不读取 `.env`、不改 runtime / backend / frontend。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1e_worker_acceptance_stdout_redirect.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_stdout_redirect python3 -m py_compile tools/dev/command_runner.py tools/dev/run_worker_acceptance_profile.py tools/dev/audit_worker_acceptance_profiles.py tools/dev/check_worker_acceptance_profile_stdout_redirect.py tools/dev/check_worker_acceptance_profile_pipe_args.py tools/dev/check_worker_acceptance_profile_python_c.py
python3 tools/dev/check_worker_acceptance_profile_stdout_redirect.py --output /tmp/worker_acceptance_profile_stdout_redirect_smoke.json
python3 tools/dev/check_worker_acceptance_profile_pipe_args.py --output /tmp/worker_acceptance_profile_pipe_args_after_stdout_redirect_smoke.json
python3 tools/dev/check_worker_acceptance_profile_python_c.py --output /tmp/worker_acceptance_profile_python_c_after_stdout_redirect_smoke.json
python3 tools/dev/audit_worker_acceptance_profiles.py --output /tmp/worker_acceptance_profile_stdout_redirect_audit.json --max-samples 120
python3 tools/dev/run_fast_quality_gate.py --output /tmp/worker_acceptance_stdout_redirect_fast_gate.json
git diff --check
```

### P1-E-10 WorkerTaskPack acceptance profile bulk migration

状态：已完成机械迁移。

目标：

```text
使用既有迁移器给所有 runner-compatible 的旧 WorkerTaskPack 批量补 acceptance_profile，减少日常验收手动步骤；保留 shell-only / heredoc 包为人工处理。
```

已落地：

- 运行 `tools/dev/migrate_worker_acceptance_profiles.py --write`，迁移 80 个旧任务包。
- 新增 `examples/worker_task_packs/p1e_worker_acceptance_bulk_migration.v0.1.json` 记录本轮机械迁移任务。
- 不修改工具脚本、后端、前端、runtime、schema 或 review evidence。

效果：

- 审计从 `110 packs: 14 with profile, 96 without profile, 96 migration candidates, 16 manual review required` 变为 `111 packs: 95 with profile, 16 without profile, 16 migration candidates, 16 manual review required`。
- 迁移器再次 dry-run 显示 `would_migrate_count=0`，说明没有剩余 runner-compatible 旧包可自动迁移。
- 剩余 16 个包保留人工处理，主要是 heredoc、多命令脚本或其他 runner-incompatible 命令。

边界：

- 本任务不执行被迁移任务包的验收命令。
- 本任务不调用 provider、不读取 `.env`、不改 runtime / backend / frontend。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1e_worker_acceptance_bulk_migration.v0.1.json
python3 tools/dev/migrate_worker_acceptance_profiles.py --output /tmp/worker_acceptance_profile_bulk_migration_after_dry.json
python3 tools/dev/audit_worker_acceptance_profiles.py --output /tmp/worker_acceptance_profile_bulk_migration_audit.json --max-samples 120
python3 tools/dev/run_fast_quality_gate.py --output /tmp/worker_acceptance_bulk_migration_fast_gate.json
python3 tools/demo/export_evidence.py --output-dir /tmp/worker_acceptance_bulk_migration_full_evidence
git diff --check
```

### P1-E-11 WorkerTaskPack media negative checks without heredoc

状态：已完成媒体负例任务包迁移。

目标：

```text
把媒体帧序列、原始视频序列和视频关键帧 atlas 导入任务包里的 heredoc / inline JSON 负例断言替换为标准工具命令，使这些任务包可以纳入 acceptance_profile runner。
```

已落地：

- 新增 `tools/dev/expect_command_failure.py`，用于运行预期失败命令，并可断言仓库外 `/tmp` 输出文件没有被写出。
- 新增 `tools/media/validate_video_keyframe_import_result.py`，用于校验视频关键帧 atlas 导入结果与 LoopContinuityReport 一致。
- 更新并迁移以下 3 个任务包到 `acceptance_profile`：
  - `examples/worker_task_packs/p1a_frame_sequence_schema_validator.v0.1.json`
  - `examples/worker_task_packs/p1a_raw_video_sequence_extraction.v0.1.json`
  - `examples/worker_task_packs/p1a_video_keyframe_atlas_import.v0.1.json`
- 新增 `examples/worker_task_packs/p1e_worker_acceptance_media_negative_checks.v0.1.json` 记录本轮验收任务。

效果：

- 迁移 3 个原本需要人工审查的媒体任务包。
- 审计从 `111 packs: 95 with profile, 16 without profile, 16 migration candidates, 16 manual review required` 先变为 `111 packs: 98 with profile, 13 without profile, 13 migration candidates, 13 manual review required`。
- 新增本任务包后，预期审计为 `112 packs: 99 with profile, 13 without profile, 13 migration candidates, 13 manual review required`。

边界：

- 本任务不调用 provider、不读取 `.env`、不修改 schema、runtime package、前端或后端。
- 本任务只验证负例失败和候选输出缺失，不把 review-only 视频帧素材激活为玩家 runtime。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1e_worker_acceptance_media_negative_checks.v0.1.json
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1a_frame_sequence_schema_validator.v0.1.json
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1a_raw_video_sequence_extraction.v0.1.json
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1a_video_keyframe_atlas_import.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_media_negative_checks python3 -m py_compile tools/dev/expect_command_failure.py tools/media/validate_video_keyframe_import_result.py
python3 tools/dev/audit_worker_acceptance_profiles.py --output /tmp/media_negative_checks_audit_after_migrate.json --max-samples 200
python3 tools/dev/migrate_worker_acceptance_profiles.py --output /tmp/media_negative_checks_after_dry.json
python3 tools/dev/run_fast_quality_gate.py --output /tmp/media_negative_checks_fast_gate.json
python3 tools/demo/export_evidence.py --output-dir /tmp/media_negative_checks_full_evidence
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

### P1-B Generation Scheduler activation gate read-model

状态：已完成最小后端读模型。

目标：

```text
把 latest run 的 prefetch-cache 进一步派生成只读 activation gate 视图，明确 review-only 候选为何仍不能进入玩家 runtime。
```

已落地：

- `backend/app/services/generation_scheduler_activation_gate_builders.py`：新增纯 builder，从 `generation_prefetch_cache` 派生 `generation_activation_gate`。
- `backend/app/services/generation_scheduler_service.py`：新增 `get_generation_activation_gate()`，复用现有 prefetch cache read-model，不新增 DB 写入。
- `backend/app/api/frontend_mock.py`：新增 `GET /api/sessions/{session_id}/generation-schedule/activation-gate`。
- `backend/tests/test_frontend_mock_api.py`：覆盖 builder、无 run 空视图、dispatcher drain 后 envelope 阻断、fixture executor chain 后 promotion 阻断，以及只读性。
- `docs/GENERATION_SCHEDULER_V0_1.md`、`docs/FRONTEND_MOCK_API_V0_1.md`、`docs/CURRENT_ARCHITECTURE_INDEX.md`：补充 activation gate read-model 边界。
- `examples/worker_task_packs/p1b_generation_activation_gate_view.v0.1.json`：新增本轮 worker task pack。

边界：

- 本接口不创建 run、不推进 worker、不写 ledger、不 staging、不 promotion、不 complete queue item。
- 本接口不读取 `.env`、不调用 provider、不写世界状态、不激活 runtime。
- 即使某个候选出现 `promotion_allowed_pending_activation`，也只能进入后续 runtime package / WorldStateDeltaTransaction 构建与复验；当前 read-model 仍返回 `activation_allowed_count = 0`。
- OpenCode headless 在当前受控通道内仍被执行环境拒绝为外部数据披露风险，本轮使用 `local_codex_safe_fallback`。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_generation_activation_gate_view.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_generation_activation_gate_view python3 -m compileall backend
uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py backend/tests/test_sessions.py -q
rg -n "activation-gate|generation_activation_gate|build_generation_activation_gate_payload" backend/app backend/tests docs control/TASK_QUEUE.md
git diff --check
```

### P1-B Generation Scheduler shared prefetch cache index

状态：已完成最小后端索引层。

目标：

```text
把 promotion 已允许、但仍等待 runtime package / WorldStateDeltaTransaction / activation gate 的候选，登记进跨 session 可复用的脱敏 shared prefetch cache index。
```

已落地：

- `backend/app/db.py`：新增 `generation_shared_prefetch_cache` 全局 SQLite 表和索引。该表不随单个 session reset 级联清除。
- `backend/app/services/generation_scheduler_shared_prefetch_cache_builders.py`：新增 builder，只从 activation gate 中筛选 `promotion_allowed = true` 且 `activation_allowed = false` / `runtime_ready = false` 的候选。
- `backend/app/services/generation_scheduler_shared_prefetch_cache_repository.py`：新增 upsert / load repository。
- `backend/app/services/generation_scheduler_service.py`：新增 `get_generation_shared_prefetch_cache()` 与 `index_generation_shared_prefetch_cache()`。
- `backend/app/api/frontend_mock.py`：新增 `GET /generation-schedule/shared-prefetch-cache` 与 `POST /generation-schedule/workers/index-shared-prefetch-cache`。
- `backend/tests/test_frontend_mock_api.py` 与 `backend/tests/test_sessions.py`：覆盖 builder、repository、API、跨 session 可读、session reset 不清除 shared cache，以及 blocked 候选不会被索引。
- `docs/GENERATION_SCHEDULER_V0_1.md`、`docs/FRONTEND_MOCK_API_V0_1.md`、`docs/CURRENT_ARCHITECTURE_INDEX.md`：补充共享预取索引边界。
- `examples/worker_task_packs/p1b_generation_shared_prefetch_cache.v0.1.json`：新增本轮 worker task pack。

边界：

- shared cache index 只保存脱敏摘要和 refs presence，不保存 prompt 正文或 provider response。
- 它不调用 provider、不 staging、不 promotion、不 complete queue item、不写世界状态、不激活 runtime。
- `promotion_allowed_pending_runtime_build` 只表示可进入后续 runtime package / WorldStateDeltaTransaction 构建与复验，不表示 runtime-ready。
- OpenCode headless 在当前受控通道内仍被执行环境拒绝为外部数据披露风险，本轮使用 `local_codex_safe_fallback`。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_generation_shared_prefetch_cache.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_generation_shared_prefetch_cache python3 -m compileall backend
uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py backend/tests/test_sessions.py -q
rg -n "shared-prefetch-cache|generation_shared_prefetch_cache|build_shared_prefetch_cache_records" backend/app backend/tests docs control/TASK_QUEUE.md
git diff --check
```

### P1-B Generation Scheduler shared prefetch cache hits

状态：已完成最小只读命中视图。

目标：

```text
让当前 session/latest run 能发现哪些调度项命中了跨 session shared prefetch cache index，同时继续保持命中不等于 runtime-ready。
```

已落地：

- `backend/app/services/generation_scheduler_shared_prefetch_cache_hit_builders.py`：新增只读 hit read-model builder，用 `object_kind + object_ref` 精确匹配当前 prefetch item 与 shared cache record。
- `backend/app/services/generation_scheduler_service.py`：新增 `get_generation_shared_prefetch_cache_hits()`。
- `backend/app/api/frontend_mock.py`：新增 `GET /generation-schedule/shared-prefetch-cache/hits`。
- `backend/tests/test_frontend_mock_api.py`：覆盖 builder、缺失 session、无 run 空结果、跨 session 命中、只读性和 runtime/activation 阻断。
- `docs/GENERATION_SCHEDULER_V0_1.md`、`docs/FRONTEND_MOCK_API_V0_1.md`、`docs/CURRENT_ARCHITECTURE_INDEX.md`：补充 hit read-model 边界。
- `examples/worker_task_packs/p1b_generation_shared_cache_hits.v0.1.json`：新增本轮 worker task pack。

边界：

- hits 视图不创建 run、不推进 worker、不写 shared cache、不调用 provider、不写世界状态、不激活 runtime。
- 命中状态 `shared_candidate_available_pending_runtime_build` 只表示当前调度项有可复用脱敏候选摘要，后续仍必须过 runtime package / WorldStateDeltaTransaction build、media / semantic gate 和 activation gate。
- OpenCode headless 在当前受控通道内仍被执行环境拒绝为外部数据披露风险，本轮使用 `local_codex_safe_fallback`。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_generation_shared_cache_hits.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_generation_shared_cache_hits python3 -m compileall backend
uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py backend/tests/test_sessions.py -q
rg -n "shared-prefetch-cache/hits|generation_shared_prefetch_cache_hits|build_shared_prefetch_cache_hit_payload" backend/app backend/tests docs control/TASK_QUEUE.md
git diff --check
```

### P1-B Generation Scheduler shared cache reuse candidate ledger

状态：已完成最小 review-only ledger 桥接层。

目标：

```text
把当前 run 的 shared cache hit 显式记录为 generation_artifact_ledger 里的复用候选，使后续 runtime package / WorldStateDeltaTransaction builder 能消费统一 evidence chain。
```

已落地：

- `backend/app/services/generation_scheduler_shared_cache_reuse_builders.py`：新增 shared cache reuse candidate builder 与 compact 摘要。
- `backend/app/services/generation_scheduler_prefetch_cache_builders.py`：新增 `shared_prefetch_cache_reuse_candidate` ref kind 与 `shared_cache_reuse_pending_runtime_build` 状态。
- `backend/app/services/generation_scheduler_service.py`：新增 `record_shared_prefetch_cache_reuse_candidate()`，从当前 hit view 选择一个命中并幂等写入 ledger。
- `backend/app/api/frontend_mock.py`：新增 `POST /generation-schedule/workers/record-shared-prefetch-cache-reuse-candidate`。
- `backend/tests/test_frontend_mock_api.py`：覆盖 builder、缺失 session / 无 run / 无 hit、写入 review-only ledger、prefetch-cache refs、幂等和安全计数。
- `docs/GENERATION_SCHEDULER_V0_1.md`、`docs/FRONTEND_MOCK_API_V0_1.md`、`docs/CURRENT_ARCHITECTURE_INDEX.md`：补充 reuse candidate 边界。
- `examples/worker_task_packs/p1b_generation_shared_cache_reuse_candidate.v0.1.json`：新增本轮 worker task pack。

边界：

- reuse candidate 不是 runtime package、不是 WorldStateDeltaTransaction、不是 provider 输出，也不是 published media。
- 该 worker 不调用 provider、不读取 `.env`、不写 shared cache、不 complete queue item、不写世界状态、不激活 runtime。
- `shared_cache_reuse_pending_runtime_build` 只表示当前 run 已把跨 session 候选挂入 evidence chain，后续仍必须过 runtime package / WorldStateDeltaTransaction build、media / semantic gate 和 activation gate。
- OpenCode headless 在当前受控通道内仍被执行环境拒绝为外部数据披露风险，本轮使用 `local_codex_safe_fallback`。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_generation_shared_cache_reuse_candidate.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_generation_shared_cache_reuse_candidate python3 -m compileall backend
uv run --extra dev python -m pytest backend/tests/test_frontend_mock_api.py backend/tests/test_sessions.py -q
rg -n "record-shared-prefetch-cache-reuse-candidate|shared_prefetch_cache_reuse_candidate|shared_cache_reuse_pending_runtime_build" backend/app backend/tests docs control/TASK_QUEUE.md
git diff --check
```

### P1-B Generation Scheduler review-only pipeline smoke

状态：已完成本地 HTTP 闭环 smoke。

目标：

```text
把已有 review-only scheduler worker 入口串成一份可重复 smoke 证据，减少演示和开发时手动调用多个 endpoint 的成本，同时保持 provider / world / runtime 边界不被放宽。
```

已落地：

- `tools/dev/check_generation_scheduler_review_only_pipeline.py`：启动临时 uvicorn 与临时 SQLite，使用真实 localhost HTTP 跑调度闭环 smoke。
- `examples/review_packs/generation_scheduler_review_only_pipeline_smoke_report.v0.1.json`：固定示例报告，当前 `status=passed`，23 个 HTTP 步骤通过。
- `tools/demo/export_evidence.py`：新增 `generation_scheduler.review_only_pipeline_smoke` 摘要，并在 summary.md 展示 handoff outbox、步骤数和安全计数。
- `docs/GENERATION_SCHEDULER_V0_1.md`、`docs/FRONTEND_MOCK_API_V0_1.md`、`docs/CURRENT_ARCHITECTURE_INDEX.md`：同步脚本定位与边界。
- `examples/worker_task_packs/p1b_generation_scheduler_review_only_pipeline_smoke.v0.1.json`：新增本轮 worker task pack。

覆盖：

- 主路径：`run-review-only-background-handoff-tick -> queue / worker-cache / artifact-ledger / prefetch-cache / activation-gate`。
- 负向边界：handoff tick 拒绝 targeted metadata 与过大 `max_items`。
- 负样本：默认 fixture executor chain 保持 promotion blocked；`image_failure` 保持 validation failed / blocked validation failed。
- shared cache：blocked default chain 不会被索引；没有 approved promotion fixture 时，shared cache hit 为空，reuse candidate 返回 409。

边界：

- 不调用 provider、不读取 `.env`、不运行真实 provider adapter、不 staging 自动化、不 promotion 自动化、不 complete queue item、不写世界状态、不激活 runtime。
- 不声明 live provider、真实图生视频、runtime package builder、WorldStateDeltaTransaction builder 或玩家侧发布已经完成。
- `positive_shared_cache_reuse_path=not_exercised_no_approved_promotion_fixture` 是刻意保留的诚实限制；正向 promotion_allowed 索引仍由后端单元测试覆盖。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_generation_scheduler_review_only_pipeline_smoke.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_generation_scheduler_review_only_pipeline_smoke python3 -m py_compile tools/dev/check_generation_scheduler_review_only_pipeline.py tools/demo/export_evidence.py tools/dev/run_fast_quality_gate.py
UV_CACHE_DIR=/tmp/ai-td-uv-cache-generation-pipeline-smoke UV_PROJECT_ENVIRONMENT=/tmp/ai-td-uv-venv-generation-pipeline-smoke uv run --extra dev python tools/dev/check_generation_scheduler_review_only_pipeline.py --output /tmp/generation_scheduler_review_only_pipeline_smoke_report.v0.1.json --generated-at 2026-07-07T00:00:00+00:00
rm -f uv.lock
python3 -m json.tool examples/review_packs/generation_scheduler_review_only_pipeline_smoke_report.v0.1.json
python3 tools/demo/export_evidence.py --validation-profile summary-only --output-dir /tmp/generation_scheduler_review_only_pipeline_smoke_evidence
git diff --check
```

### P1-B Generation Scheduler MVP readiness gate

状态：已完成顶层 readiness 同步。

目标：

```text
让 MVP demo readiness 顶层报告显式证明 Generation Scheduler 的 review-only 计划和 dry-run 运行报告存在，而不是只在 evidence 详情中间接展示调度能力。
```

已落地：

- `tools/demo/build_mvp_demo_readiness_report.py`：新增 `generation_scheduler_review_only` MVP 必需 gate，读取 `mvp_generation_schedule_plan.v0.1.json` 和 `mvp_generation_schedule_run_report.v0.1.json`。
- `examples/review_packs/mvp_demo_readiness_report.v0.1.json`：重新生成，`overall_status` 仍为 `ready_for_mvp_demo_with_known_limitations`；required gate 从 9 增加到 10，新增 gate 当前为 `passed`。
- `docs/CURRENT_ARCHITECTURE_INDEX.md` 与本任务队列：同步 readiness 报告的新证据边界。

边界：

- 该 gate 只证明 review-only 调度计划和 dry-run 运行报告可用。
- 不调用 provider，不读取 `.env`，不写世界状态，不写 runtime package，不激活预取结果。
- 不声明真实后台 provider executor 已完成；真实执行仍必须经过 guard、authorization、adapter receipt / envelope、staging、promotion 和 activation gate。

验收：

```bash
python3 tools/scheduler/validate_generation_schedule_plan.py examples/review_packs/mvp_generation_schedule_plan.v0.1.json
python3 tools/scheduler/validate_generation_schedule_run_report.py examples/review_packs/mvp_generation_schedule_run_report.v0.1.json
python3 tools/demo/build_mvp_demo_readiness_report.py --output examples/review_packs/mvp_demo_readiness_report.v0.1.json --generated-at 2026-07-06T00:00:00+00:00
python3 -c "import json; r=json.load(open('examples/review_packs/mvp_demo_readiness_report.v0.1.json')); g={x['gate_id']:x for x in r['gates']}; assert r['overall_status']=='ready_for_mvp_demo_with_known_limitations'; assert g['generation_scheduler_review_only']['required_for_mvp_demo'] is True; assert g['generation_scheduler_review_only']['status']=='passed'; assert g['generation_scheduler_review_only']['metrics']['provider_call_count']==0; assert g['generation_scheduler_review_only']['metrics']['world_mutation_count']==0"
python3 tools/demo/export_evidence.py --output-dir /tmp/generation_scheduler_readiness_evidence
git diff --check
```

### P1-D-28 MVP demo readiness report validator

状态：已完成顶层 readiness 自校验加固。

目标：

```text
让 MVP demo readiness 报告不只由 builder 生成，还能被独立 validator 复算关键计数、状态和安全边界，避免顶层演示结论漂移。
```

已落地：

- `tools/demo/validate_mvp_demo_readiness_report.py`：新增独立 CLI，校验 schema / report id、14 个固定 gate 顺序、必需 gate 计数、warning / expected block、source file 数、整体状态、安全摘要、已知限制、推荐动作和 evidence ref 存在性。
- `tools/demo/export_evidence.py`：静态验证列表新增 `mvp_demo_readiness_report_validator`，导出 evidence 时会校验仓库内 readiness fixture。
- `control/TASK_QUEUE.md`、`docs/CURRENT_ARCHITECTURE_INDEX.md`：同步 readiness builder + validator 的事实源边界。

边界：

- 只读取 readiness JSON 与其声明的本地 evidence refs。
- 不调用 provider，不读取 `.env`，不写世界状态，不写 runtime package，不生成内容。
- validator 不替代各单项 evidence validator；它只验证顶层 readiness 报告的结构、计数、状态和安全不变量。

验收：

```bash
python3 tools/demo/validate_mvp_demo_readiness_report.py examples/review_packs/mvp_demo_readiness_report.v0.1.json
python3 tools/demo/build_mvp_demo_readiness_report.py --output /tmp/mvp_demo_readiness_validator_rebuild.json --generated-at 2026-07-06T00:00:00+00:00
python3 tools/demo/validate_mvp_demo_readiness_report.py /tmp/mvp_demo_readiness_validator_rebuild.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_mvp_demo_readiness_validator python3 -m py_compile tools/demo/build_mvp_demo_readiness_report.py tools/demo/validate_mvp_demo_readiness_report.py tools/demo/export_evidence.py
python3 tools/demo/export_evidence.py --output-dir /tmp/mvp_demo_readiness_validator_evidence
git diff --check
```

### P1-D-29 Daily fast quality gate

状态：已完成日常开发验收入口简化。

目标：

```text
在不放宽质量门禁的前提下，把日常开发最常用的无浏览器 / 无 provider 检查收束成一个快速入口，减少每次小改动都跑完整 evidence export 的等待。
```

已落地：

- `tools/dev/run_fast_quality_gate.py`：新增快速质量门 CLI，默认输出 `/tmp/ai_td_fast_quality_gate_report.v0.1.json`。
- `README.md`：Tests 段新增日常开发优先命令。
- `docs/CURRENT_ARCHITECTURE_INDEX.md`、`control/TASK_QUEUE.md`：同步该入口的定位和边界。

默认检查：

- `py_compile` 核心 demo / frontend validator / fast gate 脚本，缓存写入 `/tmp`。
- `node --check frontend/app.js`。
- `tools/frontend/validate_battle_visual_contract.py --report-output /tmp/...`。
- `tools/frontend/validate_campaign_router_frontend_contract.py`。
- `tools/frontend/validate_map_component_frontend_contract.py`。
- `tools/demo/build_mvp_demo_readiness_report.py --output /tmp/...`。
- `tools/demo/validate_mvp_demo_readiness_report.py` 校验仓库 fixture 和临时重建 report。

边界：

- 不调用 provider，不读取 `.env`，不跑浏览器，不写世界状态，不写 runtime package，不激活 runtime。
- 不替代完整 `tools/demo/export_evidence.py` 或 `tools/demo/run_demo_evidence_suite.py`；只作为日常开发快速反馈。

验收：

```bash
python3 tools/dev/run_fast_quality_gate.py --output /tmp/ai_td_fast_quality_gate_report.v0.1.json
python3 -m json.tool /tmp/ai_td_fast_quality_gate_report.v0.1.json >/tmp/ai_td_fast_quality_gate_report.pretty.json
python3 tools/demo/export_evidence.py --output-dir /tmp/fast_quality_gate_evidence_check
git diff --check
```

### P1-D-30 Shared local command runner

状态：已完成本地 QA / evidence 命令执行去重。

目标：

```text
把快速质量门和 demo evidence suite 中重复的 subprocess 执行、输出截断、时间戳记录逻辑收束为一个共享 helper，减少后续新增验收脚本时复制粘贴。
```

已落地：

- `tools/dev/command_runner.py`：新增共享命令执行 helper，提供 `now_iso()`、输出截断、命令文本化和 timeout-safe `run_command()`。
- `tools/dev/run_fast_quality_gate.py`：复用共享 runner，并把 `command_runner.py` 纳入自身 `py_compile`。
- `tools/demo/run_demo_evidence_suite.py`：复用共享 runner，保持原 suite report 字段兼容。
- `tools/demo/export_evidence.py`：静态验证命令执行复用共享 runner，保持 validation summary 字段兼容。

边界：

- 只抽取本地命令运行工具函数，不改变 fast gate / demo suite 的业务判断。
- 不调用 provider，不读取 `.env`，不写世界状态，不激活 runtime。
- 不改变浏览器缺失时的 `--allow-missing-browser` 语义。

验收：

```bash
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_export_runner_refactor python3 -m py_compile tools/dev/command_runner.py tools/dev/run_fast_quality_gate.py tools/demo/run_demo_evidence_suite.py tools/demo/export_evidence.py
python3 tools/dev/run_fast_quality_gate.py --output /tmp/ai_td_fast_quality_gate_export_runner_report.v0.1.json
python3 tools/demo/export_evidence.py --output-dir /tmp/export_runner_refactor_evidence_check
python3 tools/demo/run_demo_evidence_suite.py --allow-missing-browser --output-root /tmp/ai_td_demo_suite_export_runner_check --command-timeout 120
git diff --check
```

### P1-D-30a Export evidence validation profile

状态：已完成 demo evidence 导出快速预览 profile。

目标：

```text
给 export_evidence.py 增加显式 validation profile，让日常开发可快速导出 summary / HTML，同时保持默认正式 evidence 导出质量不变。
```

已落地：

- `tools/demo/export_evidence.py`：新增 `--validation-profile {full,summary-only}`，默认 `full` 保持完整 validation commands 和返回码规则；`summary-only` 不运行 validation commands，仍构建 `evidence.json`、`summary.md` 和 `index.html`。
- `summary-only` 的 `validation_summary.current_export_validation` 显式记录 `status=skipped`、profile、`command_count=0`、`results=[]` 和跳过原因；console / summary / HTML 均展示 skipped，不把快速预览误称为 passed。
- `README.md`、`docs/CURRENT_ARCHITECTURE_INDEX.md`、`control/TASK_QUEUE.md`：说明 `summary-only` 只用于本地快速查看；最终评审、录屏或合并前仍使用默认 `full` 导出或完整 demo evidence suite。

边界：

- 不放宽默认质量门；未传参的 `python3 tools/demo/export_evidence.py --output-dir ...` 仍跑完整 validation，只有 `passed` 返回 0。
- 不修改 backend、frontend、examples/review_packs、game_data、`.env` 或默认 runtime/package 文件。

验收：

```bash
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_evidence_validation_profile python3 -m py_compile tools/demo/export_evidence.py
python3 tools/demo/export_evidence.py --output-dir /tmp/ai_td_evidence_validation_profile_full
python3 tools/demo/export_evidence.py --validation-profile summary-only --output-dir /tmp/ai_td_evidence_validation_profile_summary_only
python3 -c "import json; from pathlib import Path; v=json.loads(Path('/tmp/ai_td_evidence_validation_profile_summary_only/evidence.json').read_text())['validation_summary']['current_export_validation']; assert v['status']=='skipped' and v['profile']=='summary-only' and v['command_count']==0 and v['results']==[]"
```

### P1-D-31 README and review handoff command simplification

状态：已完成开发 / 审查入口文档收束。

目标：

```text
去掉 README 中旧的极简环境手动命令长列表，把日常开发、后端测试、录屏评审三类入口明确分层，减少 worker 和队友复制过时命令。
```

已落地：

- `README.md`：Tests 段改为三层入口：日常 fast gate、后端 pytest、录屏 / 评审 evidence suite 或只导出 evidence bundle。
- `docs/MVP_REVIEW_HANDOFF_V0_1.md`：一键审查前置 fast gate，并补充浏览器可用 / 浏览器缺失两种 demo evidence suite 命令。

边界：

- 只改文档入口，不改变任何 validator、builder、backend、frontend 行为。
- fast gate 仍不替代完整 evidence suite；浏览器缺失必须显式 `--allow-missing-browser` 并保留报告。

验收：

```bash
python3 tools/dev/run_fast_quality_gate.py --output /tmp/readme_simplified_fast_gate_report.v0.1.json
git diff --check
```

### P1-D-32 Map runtime v0.2 activation selector

状态：已完成受控 selector 与测试夹具证明。

目标：

```text
在不改变默认 pending 授权行为的前提下，补齐 developer-approved selector：当显式开发者授权报告批准并匹配目标 v0.2 包时，后端默认地图运行时表面可以一致选择 MapRuntimePackage v0.2 与匹配 RenderPlan bundle。
```

已落地：

- `backend/app/services/map_runtime_service.py`：新增 `map_runtime_activation_selection()`、`load_selected_map_runtime_package()` 和响应中的 `runtime_selection`。
- `backend/app/services/map_render_plan_service.py`：新增按 runtime schema 选择 RenderPlan bundle 的入口；v0.2 被批准为默认 runtime 时，返回激活后的 v0.2 bundle 元数据。
- `backend/app/services/frontend_mock_service.py` 与 `backend/app/api/frontend_mock.py`：`/map-runtime-package`、`/map-render-plan`、`/config`、`/runtime-package` 聚合响应使用同一个 selector，避免地图包与表现计划版本漂移。
- `backend/tests/test_frontend_mock_api.py`：新增临时 approved 授权夹具测试，证明三张节点在授权匹配时可一致切到 v0.2，默认 pending 测试仍保持 v0.1。
- `tools/dev/check_map_runtime_v02_opt_in_contract.py` 与 validator：opt-in smoke 继续证明 endpoint review-only，同时新增 approved selector 选择 v0.2 的 service-level 证据。

边界：

- 默认仓库授权报告仍为 `pending_developer_approval`，因此正常玩家 API 仍选择 v0.1。
- selector 只消费本地授权报告和已审结构化包，不读取 `.env`、不调用 provider、不读取 review-only / 失败整图候选。
- 该任务不把 activation gate 改成 allowed；正式默认切换仍需要显式授权文件、后端/前端证据复跑和 demo evidence 更新。

验收：

```bash
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_map_runtime_v02_activation_selector python3 -m py_compile backend/app/services/map_runtime_service.py backend/app/services/map_render_plan_service.py backend/app/services/frontend_mock_service.py backend/app/api/frontend_mock.py backend/tests/test_frontend_mock_api.py tools/dev/check_map_runtime_v02_opt_in_contract.py tools/dev/validate_map_runtime_v02_opt_in_contract_report.py
/home/zty/projects/ai-compiled-towerdefense/.venv/bin/python -m pytest backend/tests/test_frontend_mock_api.py -k "map_v02 or map_runtime_and_render_plan or approved_map_v02_activation_selector" -q
/home/zty/projects/ai-compiled-towerdefense/.venv/bin/python tools/dev/check_map_runtime_v02_opt_in_contract.py --output examples/review_packs/map_runtime_v02_opt_in_contract_smoke_report.v0.1.json --generated-at 2026-07-06T00:00:00+00:00
python3 tools/dev/validate_map_runtime_v02_opt_in_contract_report.py examples/review_packs/map_runtime_v02_opt_in_contract_smoke_report.v0.1.json
python3 tools/dev/run_fast_quality_gate.py --output /tmp/map_runtime_v02_activation_selector_fast_gate.json
git diff --check
```

### P1-D-33 Map runtime activation gate selector sync

状态：已完成 gate / plan / readiness 口径同步。

目标：

```text
在 P1-D-32 补齐 developer-approved selector 之后，同步 MapRuntimeActivationGateReport、MapRuntimeV02ActivationContractPlan、MVP demo readiness 与主文档，确保旧的后端 API 合同 blocker 不再被当作未完成项，同时仍保持默认 pending 授权下 runtime v0.1。
```

已落地：

- `tools/media/build_map_runtime_activation_gate_report.py` 与 validator：把后端 selector 合同纳入 gate summary；当 selector 为 `pre_activation_ready` 时，旧 `api_frontend_contract_update_required` blocker 不得再出现。
- `tools/media/build_map_runtime_v02_activation_contract_plan.py` 与 validator：新增 `backend_tracked_step_count`、`backend_not_applied_change_count`、`backend_selector_contract_status`，把后端 selector 步骤标为已预接入但不执行激活。
- `tools/demo/build_mvp_demo_readiness_report.py` 与 `tools/demo/export_evidence.py`：演示证据展示“后端 selector 已预接入、正式激活仍需开发者授权和激活后复跑”。
- `docs/CURRENT_ARCHITECTURE_INDEX.md`、`docs/MAP_COMPILATION_DESIGN_V0_1.md` 与本任务队列：同步当前事实源。

边界：

- 不激活 `MapRuntimePackage v0.2`。
- 不修改默认 pending 授权报告。
- 不调用 provider，不读取 `.env`，不写世界状态。

验收：

```bash
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_map_activation_gate_sync python3 -m py_compile tools/media/build_map_runtime_activation_gate_report.py tools/media/validate_map_runtime_activation_gate_report.py tools/media/build_map_runtime_v02_activation_contract_plan.py tools/media/validate_map_runtime_v02_activation_contract_plan.py tools/demo/build_mvp_demo_readiness_report.py tools/demo/validate_mvp_demo_readiness_report.py tools/demo/export_evidence.py
python3 tools/media/validate_map_runtime_activation_gate_report.py examples/review_packs/map_runtime_activation_gate_report.v0.1.json
python3 tools/media/validate_map_runtime_v02_activation_contract_plan.py examples/review_packs/map_runtime_v02_activation_contract_plan.v0.1.json
python3 tools/demo/validate_mvp_demo_readiness_report.py examples/review_packs/mvp_demo_readiness_report.v0.1.json
python3 tools/dev/run_fast_quality_gate.py --output /tmp/map_runtime_activation_gate_selector_sync_fast_gate.json
python3 tools/demo/export_evidence.py --output-dir /tmp/map_runtime_activation_gate_selector_sync_evidence
git diff --check
```

### P1-D-34 Demo evidence suite scheduler pipeline smoke

状态：已完成一键套件前置调度 smoke。

目标：

```text
让评审 / 录屏前的一键 demo evidence suite 默认先跑 Generation Scheduler review-only pipeline smoke，再跑浏览器玩家链路截图、截图报告校验和 evidence 导出，避免调度闭环证据被手动遗漏。
```

已落地：

- `tools/demo/run_demo_evidence_suite.py`：新增套件第 1 步 `generation_scheduler_review_only_pipeline_smoke`，调用 `tools/dev/check_generation_scheduler_review_only_pipeline.py` 并把报告写到 output root 下的 `generation_scheduler/`。
- suite report 新增 `generation_scheduler_pipeline_smoke_report` 文件引用、`generation_scheduler_review_only_pipeline_smoke` 摘要和 `scheduler_pipeline_smoke_skipped` 安全标记。
- suite 状态会检查 scheduler smoke 必须 `passed`，且 `external_provider_call_count` 与 `runtime_activation_allowed_count` 必须为 0。
- `README.md`、`docs/MVP_REVIEW_HANDOFF_V0_1.md`、`docs/CURRENT_ARCHITECTURE_INDEX.md`：同步说明完整 suite 默认包含 scheduler pipeline smoke。
- `examples/worker_task_packs/p1d_demo_suite_scheduler_pipeline_smoke.v0.1.json`：新增本轮 worker task pack。

边界：

- 不调用 provider、不读取 `.env`、不运行真实 provider adapter、不写世界状态、不构建 runtime package、不激活 review-only 结果。
- 该 suite 仍只是本地 evidence 编排；它证明 scheduler review-only pipeline、handoff outbox、prefetch-cache 和 activation gate 边界可重复，不代表 live provider、真实图生视频、WorldStateDeltaTransaction 写入或玩家侧发布已完成。
- `--skip-scheduler-pipeline-smoke` 只用于快速调试，不建议录屏 / 评审前使用。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1d_demo_suite_scheduler_pipeline_smoke.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_demo_suite_scheduler_pipeline_smoke python3 -m py_compile tools/demo/run_demo_evidence_suite.py
python3 tools/demo/run_demo_evidence_suite.py --allow-missing-browser --output-root /tmp/ai_td_demo_suite_scheduler_pipeline_check --command-timeout 180
python3 -c "import json; from pathlib import Path; report=json.loads(Path('/tmp/ai_td_demo_suite_scheduler_pipeline_check/demo_evidence_suite_report.v0.1.json').read_text(encoding='utf-8')); scheduler=report['generation_scheduler_review_only_pipeline_smoke']; command_names=[item['name'] for item in report['commands']]; assert scheduler['status']=='passed'; assert scheduler['external_provider_call_count']==0; assert scheduler['runtime_activation_allowed_count']==0; assert report['safety_summary']['scheduler_pipeline_smoke_skipped'] is False; assert 'generation_scheduler_review_only_pipeline_smoke' in command_names"
git diff --check
```

### P1-D-35 Demo evidence suite scheduler runner selection

状态：已完成一键套件执行器选择优化。

目标：

```text
减少录屏 / 评审前反复运行 demo evidence suite 的等待时间：scheduler pipeline smoke 默认优先复用仓库本地 .venv/bin/python；没有 .venv 的干净 worktree / CI 继续使用 uv run 回退。
```

已落地：

- `tools/demo/run_demo_evidence_suite.py`：新增 `--scheduler-smoke-runner {auto,uv,venv,current-python}` 与 `--scheduler-python`。
- 默认 `auto` 在 `.venv/bin/python` 存在时使用本地 venv；不存在时保持原来的 `uv run --extra dev` 隔离执行。
- suite report 新增 `scheduler_pipeline_smoke_runner`，记录实际 runner、是否使用 uv，以及相关本地路径 / uv cache 路径。
- `README.md`、`docs/MVP_REVIEW_HANDOFF_V0_1.md`、`docs/CURRENT_ARCHITECTURE_INDEX.md`：同步执行器选择说明。
- `examples/worker_task_packs/p1d_demo_suite_scheduler_runner_selection.v0.1.json`：新增本轮 worker task pack。

边界：

- 不改变 scheduler smoke 覆盖范围和通过条件；仍要求 provider 调用、世界修改和 runtime activation 计数为 0。
- 不读取 `.env`、不调用 provider、不写世界状态、不构建 runtime package、不激活 review-only 结果。
- `--scheduler-python` 只用于显式本地调试 / 验收；没有显式指定时，干净环境仍可通过 uv 回退复现。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1d_demo_suite_scheduler_runner_selection.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_demo_suite_scheduler_runner_selection python3 -m py_compile tools/demo/run_demo_evidence_suite.py
python3 tools/demo/run_demo_evidence_suite.py --help
python3 -c "from pathlib import Path; from tools.demo.run_demo_evidence_suite import build_scheduler_pipeline_smoke_invocation, parse_args; args=parse_args(['--scheduler-smoke-runner','uv']); command, env, runner=build_scheduler_pipeline_smoke_invocation(args, Path('/tmp/report.json'), Path('/tmp/out')); assert command[:4]==['uv','run','--extra','dev']; assert runner['mode']=='uv' and runner['uses_uv'] is True and 'UV_CACHE_DIR' in env; args=parse_args(['--scheduler-python','/tmp/python']); command, env, runner=build_scheduler_pipeline_smoke_invocation(args, Path('/tmp/report.json'), Path('/tmp/out')); assert command[0]=='/tmp/python' and runner['mode']=='explicit-python' and runner['uses_uv'] is False and env=={}"
python3 tools/demo/run_demo_evidence_suite.py --scheduler-smoke-runner uv --allow-missing-browser --output-root /tmp/ai_td_demo_suite_scheduler_runner_selection_check --command-timeout 180
python3 -c "import json; from pathlib import Path; report=json.loads(Path('/tmp/ai_td_demo_suite_scheduler_runner_selection_check/demo_evidence_suite_report.v0.1.json').read_text(encoding='utf-8')); runner=report['scheduler_pipeline_smoke_runner']; scheduler=report['generation_scheduler_review_only_pipeline_smoke']; assert runner['mode']=='uv' and runner['uses_uv'] is True; assert scheduler['status']=='passed'; assert scheduler['external_provider_call_count']==0; assert scheduler['runtime_activation_allowed_count']==0"
git diff --check
```

### P1-D-36 Demo evidence suite outbox import smoke

状态：已完成一键套件集成。

目标：

```text
把已经独立通过的 provider runner outbox consume -> import -> prefetch-cache 严格 smoke 纳入默认 demo evidence suite，避免录屏 / 评审前只跑 scheduler pipeline smoke 而遗漏外部 runner 回灌链路。
```

已落地：

- `tools/demo/run_demo_evidence_suite.py`：新增默认步骤 `provider_runner_handoff_outbox_import_smoke`，在浏览器玩家链路截图前运行。
- suite report 新增 `provider_runner_handoff_outbox_import_smoke_report` 文件引用、`outbox_import_smoke_runner` 和 `provider_runner_handoff_outbox_import_smoke` 摘要。
- suite 状态会检查 outbox import smoke 必须 `passed`，且 provider call、env read、staging、promotion、queue complete、world mutation、runtime activation 都为 0。
- suite 状态还会检查导入前 `review_only_envelope_ready_count=0`、导入后 `prefetch_review_only_envelope_ready_count=2`、`imported_count=2`。
- 新增 `--skip-outbox-import-smoke` 快速调试开关；录屏 / 评审前不建议使用。
- `README.md`、`docs/MVP_REVIEW_HANDOFF_V0_1.md`、`docs/CURRENT_ARCHITECTURE_INDEX.md`：同步说明完整 suite 默认包含 outbox import smoke。
- `examples/worker_task_packs/p1d_demo_suite_outbox_import_smoke.v0.1.json`：新增本轮 worker task pack。

边界：

- 不调用 provider、不读取 `.env`、不 staging、不 promotion、不 complete queue item、不写世界状态、不激活 runtime。
- 该 suite 仍只是本地 evidence 编排；它证明外部 runner 回灌链路可重复，不代表 live provider、真实图生视频或 runtime package 构建已完成。

验收：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1d_demo_suite_outbox_import_smoke.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_demo_suite_outbox_import_smoke python3 -m py_compile tools/demo/run_demo_evidence_suite.py
python3 tools/demo/run_demo_evidence_suite.py --allow-missing-browser --output-root /tmp/ai_td_demo_suite_outbox_import_check --command-timeout 180
python3 -c "import json; from pathlib import Path; report=json.loads(Path('/tmp/ai_td_demo_suite_outbox_import_check/demo_evidence_suite_report.v0.1.json').read_text(encoding='utf-8')); outbox=report['provider_runner_handoff_outbox_import_smoke']; command_names=[item['name'] for item in report['commands']]; assert outbox['status']=='passed'; assert outbox['imported_count']==2; assert outbox['pre_import_review_only_envelope_ready_count']==0; assert outbox['prefetch_review_only_envelope_ready_count']==2; assert outbox['external_provider_call_count']==0; assert outbox['runtime_activation_allowed_count']==0; assert report['safety_summary']['outbox_import_smoke_skipped'] is False; assert 'provider_runner_handoff_outbox_import_smoke' in command_names"
git diff --check
```

### P1-MAP-34 MapTemplateCatalog v0.1

状态：已完成最薄开发者侧候选目录。

目标：

```text
新增 MapTemplateCatalog v0.1，用于记录开发者 / 系统侧地图路径模板候选，帮助后续生成候选 MapRuntimePackage 或 review evidence，但不成为玩家默认 runtime，也不与 MapRuntimePackage 竞争运行时事实源。
```

已落地：

- `shared/schemas/map_template_catalog.v0.1.schema.json`
- `tools/asset_graph/build_map_template_catalog.py`
- `tools/asset_graph/validate_map_template_catalog.py`
- `examples/map_template_catalogs/mvp_map_template_catalog.v0.1.json`
- `examples/worker_task_packs/p1map_map_template_catalog.v0.1.json`

边界：

- catalog 只保存 stable template id、中文可读说明、topology kind、推荐节点用途、grid constraints、normalized route blueprint、slot strategy、semantic hook 摘要和 usage policy。
- catalog 不保存 provider/model/raw prompt/full trace/raw JSON/api key/secret/unreviewed content。
- catalog 不修改 `examples/map_runtime_packages/`、`examples/map_runtime_packages_v02/`、RenderPlan、后端默认接口或前端默认消费。
- 任何模板被采用后，仍必须重新生成结构化 `MapRuntimePackage` 并经过现有 validator、RenderPlan、SemanticVisualConsistencyReport、evidence 和 activation gate。

验收：

```bash
python3 tools/asset_graph/build_map_template_catalog.py --validate
python3 tools/asset_graph/validate_map_template_catalog.py examples/map_template_catalogs/mvp_map_template_catalog.v0.1.json
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1map_map_template_catalog.v0.1.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_map_template_catalog python3 -m py_compile tools/asset_graph/build_map_template_catalog.py tools/asset_graph/validate_map_template_catalog.py
python3 tools/dev/run_worker_acceptance_profile.py examples/worker_task_packs/p1map_map_template_catalog.v0.1.json --profile daily_fast --output /tmp/map_template_catalog_runner.json
python3 tools/dev/run_fast_quality_gate.py --output /tmp/map_template_catalog_fast_gate.json
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
3. 地图 runtime v0.2 若要正式成为玩家默认路径，应先准备显式 approved 授权文件，再复跑 API smoke、前端视觉合同、浏览器玩家链路和 demo evidence；不得从 review-only preview endpoint 间接激活。
4. 地图补丁后 overlay 人工/视觉模型复核，以及基于 ControlledMapCandidateGenerationRun 的真实参考图 provider / paintover / 分层程序化底图路线；只有通过 promotion gate 后才允许更新发布底图。
5. 扩展地图补丁后的 overlay / 视觉模型复核，并在新增战斗节点后复跑 `tools/frontend/capture_battle_visual_smoke.py`。
6. `P1-A` 真实视频关键帧增强。
7. `P1-B` Generation Scheduler 正式后台执行器、真实 provider 调度、跨请求缓存和 activation / promotion gate；Campaign Router v0.1 dry-run 预取胶水已落地，不应重复实现。

若需要并行，优先组合：

- `P1-A` 与 `P1-B` 可并行，但都应避免破坏当前 MVP 静态 fixture 路径。
- main 同步执行必须单独进行，不应与大规模 P1 实现任务混在同一 worktree。
- `P1-A` 视频帧 / atlas 增强应在地图质量防线之后推进，避免动画资产先接入了错误的地图展示框架。
