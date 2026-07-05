# 当前架构文档索引

Last updated: 2026-07-05

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
- `ProviderAdapterRunnerHandoffOutbox v0.1` 是外部 runner 批量交接单，不是 provider 输出、staging manifest、promotion report、runtime package 或世界状态事务。
- worker 不得从旧 task worktree、早期主聊天摘要或 `main` 的滞后文档推导当前字段事实；派发实现任务时以 `develop` 上的本索引、`AI_COMPILATION_SYSTEM_V0_1.md`、schema、tools 和专题文档为准。

## 0. 冻结快照

本索引当前冻结以下使用方式：

```text
CURRENT_ARCHITECTURE_INDEX.md
  -> 找入口、读顺序、事实源优先级

AI_COMPILATION_SYSTEM_V0_1.md
  -> 概念、边界、权限、生命周期

shared/schemas/ + tools/ + 专题文档
  -> 字段、枚举、op 白名单、validator、builder、命令
```

概念层可以提出下一轮 schema 修订，但不能让实现跳过已有 gate。字段级冲突时先按 schema / tools 执行，再单独开任务更新概念文档或迁移旧产物。

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
- `docs/MAP_COMPILATION_DESIGN_V0_1.md`
  - 外部地图编译方案的审查采纳文档：采纳 logic-first、StylePack、程序化渲染、权限分层、地图元素语义强度分级和 validator-gated export；不照搬完整 LevelBundle，也不让 AI 整图成为运行时地图事实源。2026-07-05 已补充外部 v0.3 执行建议复审：后续地图任务应增强现有 `MapRuntimePackage v0.2 preview -> ProceduralMapRenderPlan -> SemanticVisualConsistencyReport -> evidence / activation gate` 链路，而不是新建一组与 `MapRuntimePackage` 竞争的运行时事实源。
- `shared/schemas/map_style_pack.v0.1.schema.json`、`shared/schemas/procedural_map_render_plan.v0.1.schema.json`、`shared/schemas/semantic_visual_consistency_report.v0.1.schema.json`
  - 地图编译最小链路字段事实源：StylePack 只管表现层，RenderPlan 把 MapRuntimePackage + StylePack 编成分层绘制操作，SemanticVisualConsistencyReport 证明路径、塔位、目标、出生点和 debug/player 边界一致。
- `shared/schemas/map_style_component_binding_report.v0.1.schema.json`、`tools/asset_graph/build_map_style_component_binding_report.py`、`tools/asset_graph/validate_map_style_component_binding_report.py`、`examples/review_packs/map_style_component_binding_report.v0.1.json`
  - MapStylePack component media binding 审查门：只解析 `material.component_ref` 与 `visual_ref.kind == reviewed_component_ref` 的显式 reviewed media/atlas 引用，统计 resolved / missing / procedural fallback / coverage gap，并拒绝 provider/raw prompt/secret/unreviewed 字段和外部临时 URL。该报告只进入 evidence，不改变 MapRuntimePackage 事实源，也不允许从图片或 atlas 反推路线、塔位、目标、出生点、资源、机关或碰撞语义。
- `shared/schemas/map_component_media_manifest.v0.1.schema.json`、`tools/media/build_map_component_media_pack.py`、`tools/media/validate_map_component_media_pack.py`、`game_data/media/map_components/map_component_media_manifest.v0.1.json`
  - MapComponentMediaManifest v0.1 是 MapStylePack 表现层组件媒体事实：记录 reviewed local SVG refs、sha256、尺寸、component role、style_pack_id / node_id 和 usage policy，并通过 `/assets/map_components/...` 的只读静态挂载保持 URL 可解析。它不调用 provider、不读取 `.env`、不保存 provider/model/raw prompt/full trace/raw JSON/secret/unreviewed content 或外部临时 URL，也不是地图语义事实源；路径、塔位、目标、出生点、资源、机关、阻挡和碰撞仍只能来自 `MapRuntimePackage` / `MapRuntimePackage v0.2 preview`。
- `shared/schemas/map_component_media_manifest.v0.2.schema.json`、`tools/media/build_map_component_media_manifest_v02.py`、`tools/media/validate_map_component_media_pack_v02.py`、`game_data/media/map_components/map_component_media_manifest.v0.2.json`
  - MapComponentMediaManifest v0.2 是旁路 preview artifact，不替换正式 v0.1 manifest，也不改变前端默认消费。当前 builder 从 v0.1 迁移 36 个 deterministic SVG baseline，保留 stable id、sha、StylePack / node / source binding，并新增 `media_kind` / `file_type` / atlas 引用结构和 summary 中的 `media_kind_counts`、`single_image_count`、`atlas_animation_count`，为后续 PNG / WebP / atlas animation 留门。独立 validator 继续拒绝 provider / prompt / raw trace / secret / 外部 URL，校验本地 `/assets/map_components/...` URL、sha、SVG 安全规则、PNG/WebP 文件头和 atlas animation 引用存在性；统一 demo evidence 只把它作为 `map_component_media_v02_preview` 摘要和静态校验项纳入。
- `shared/schemas/map_component_generation_request_pack.v0.1.schema.json`、`tools/media/build_map_component_generation_request_pack.py`、`tools/media/validate_map_component_generation_request_pack.py`、`examples/review_packs/map_component_generation_request_pack.v0.1.json`
  - MapComponentGenerationRequestPack v0.1 是 MapComponentMediaManifest 之后的 review-only 生成请求摘要层：从当前 36 个 deterministic SVG baseline 派生 component_id、component_role、style_pack_id、node_id、baseline local ref、target size、prompt_profile_id、negative constraints、required gates 和 usage policy。它只保存 redacted prompt summary / structured prompt tokens，不调用 provider、不读取 `.env`、不保存 provider/model/raw prompt/full trace/raw JSON/secret/unreviewed content 或外部临时 URL，也不修改 manifest / StylePack / RenderPlan / runtime map truth。
- `shared/schemas/map_component_artifact_staging_manifest.v0.1.schema.json`、`tools/media/build_map_component_artifact_staging_manifest.py`、`tools/media/import_map_component_artifacts.py`、`tools/media/validate_map_component_artifact_staging_manifest.py`、`examples/review_packs/map_component_artifact_staging_manifest.v0.1.json`、`examples/review_packs/map_component_artifact_import_plan.v0.1.json`
  - MapComponentArtifactStagingManifest v0.1 是 generation request pack 之后、candidate review 之前的 review-only 本地 artifact 导入边界：从 36 个 request 派生 36 个 staging slot，声明外部 provider 或人工生成的本地 `png/svg/webp` 如何进入候选池。当前默认 manifest 没有真实本地候选，因此所有 slot 均为 `awaiting_local_artifact` / `not_imported`，`imported_count=0`、`awaiting_count=36`；candidate path 必须为空，未来非空时只能指向仓库内 `game_data/media/map_components/candidates/` 或 `/tmp/...` 本地文件并校验存在、sha256 和扩展名。`tools/media/import_map_component_artifacts.py` 可按 import plan 生成 alternate staging manifest 供 candidate review / visual quality / promotion gate 消费，但不会直接激活 runtime，也不写正式 MapComponentMediaManifest。该层不代表 review passed，不调用 provider、不保存 provider/model/raw prompt/full trace/raw JSON/secret/unreviewed content 或外部 URL，也明确不写 manifest、不改 StylePack / RenderPlan / frontend default / runtime map truth。
- `shared/schemas/map_component_candidate_review_report.v0.1.schema.json`、`tools/media/build_map_component_candidate_review_report.py`、`tools/media/approve_map_component_candidate_review.py`、`tools/media/validate_map_component_candidate_review_report.py`、`examples/review_packs/map_component_candidate_review_report.v0.1.json`
  - MapComponentCandidateReviewReport v0.1 是 artifact staging 之后的候选审查层，顶层记录 `source_artifact_staging_manifest_path` 并读取 staging slot 作为 generated candidate 的唯一入口。当前 artifact staging 的 `imported_count=0`，因此 36 个 deterministic SVG baseline 仍只被登记为 `baseline_fixture_candidate` / `no_generated_candidate_yet`，`generated_candidate_count=0`，报告状态为 `blocked_from_promotion`；未来只有 `imported` + `staged_for_review` 且本地路径 / sha 与 staging 匹配的 slot 才能进入报告为 blocked generated candidate。默认 builder 不会自动批准 generated candidate；`approve_map_component_candidate_review.py` 只能按 approval plan 从 imported alternate candidate review 派生带 `approval_record` 的 alternate report，使指定 generated candidate 进入 `passed` / `eligible_for_promotion` / `promotion_allowed_now=true`，但 baseline fixture 仍永远不可 promotion，且该工具不写正式 report、manifest 或 runtime。
- `shared/schemas/map_component_visual_quality_report.v0.1.schema.json`、`tools/media/build_map_component_visual_quality_report.py`、`tools/media/approve_map_component_visual_quality.py`、`tools/media/validate_map_component_visual_quality_report.py`、`examples/review_packs/map_component_visual_quality_report.v0.1.json`
  - MapComponentVisualQualityReport v0.1 是 candidate review 之后、promotion gate 之前的 generated candidate 本地视觉质量 / cutout normalization gate。builder 默认读取 `examples/review_packs/map_component_candidate_review_report.v0.1.json`，只审查 `candidate_kind == generated_candidate` 的条目，记录本地文件存在性、sha256、size、检测到的 PNG / SVG / WebP 类型，以及 PNG alpha / subject bbox / edge contact、SVG root / script / remote reference、WebP unsupported decode 等 review-only 结果。当前没有 generated candidate，因此 `generated_candidate_count=0`、`checked_candidate_count=0`、`passed_count=0`、状态为 `awaiting_generated_candidates`，validator 通过但不伪造通过；36 个 baseline SVG 不进入该 report。默认 builder 对无文件级 issue 的 generated item 仍只给 `needs_review`；`approve_map_component_visual_quality.py` 可按 approval plan 派生 alternate visual-approved report，使指定 item 进入 `passed`，但仍保持 `promotion_allowed_now=false`、`runtime_ready=false`、runtime / promotion effect 全 false，不写 MapComponentMediaManifest、不改 StylePack、不改 RenderPlan、不改 frontend default、不改 runtime map truth。
- `shared/schemas/map_component_promotion_gate_report.v0.1.schema.json`、`tools/media/build_map_component_promotion_gate_report.py`、`tools/media/validate_map_component_promotion_gate_report.py`、`examples/review_packs/map_component_promotion_gate_report.v0.1.json`
  - MapComponentPromotionGateReport v0.1 是 visual quality / cutout normalization gate 之后的显式晋升门。builder 默认读取 `examples/review_packs/map_component_visual_quality_report.v0.1.json`，顶层记录 `source_visual_quality_report_path`，并在每个 generated candidate decision 中写入 visual quality report 状态、匹配 item 状态、是否已检查、是否必需和阻断原因；baseline fixture 不要求 visual item。当前 generated candidates 为 0，visual quality report 状态为 `awaiting_generated_candidates`，`promotion_allowed_count=0`，`baseline_preserved_count=36`，并声明没有写入新的 MapComponentMediaManifest、StylePack、RenderPlan、frontend default 或 runtime map truth；alternate 链路可以用 imported staging + candidate approval + visual approval 证明 `promotion_allowed_count > 0`，但 promotion gate 本身仍只写 report，runtime_effect 全 false，manifest replacement / runtime activation 必须由后续单独发布机制处理。
- `shared/schemas/map_component_manifest_patch_plan.v0.1.schema.json`、`tools/media/build_map_component_manifest_patch_plan.py`、`tools/media/validate_map_component_manifest_patch_plan.py`、`examples/review_packs/map_component_manifest_patch_plan.v0.1.json`
  - MapComponentManifestPatchPlan v0.1 是 promotion gate 之后、任何正式 apply 之前的 review-only manifest patch proposal 层。它只读取 `MapComponentPromotionGateReport` 中 `allowed` 的 generated candidate decision，并回查 candidate review、visual quality 和当前 `MapComponentMediaManifest`，把可替换目标、候选 sha / local path、schema 兼容状态、建议 processed path / public URL 和后续人工 apply 动作写成 proposal。默认正式链路 `promotion_allowed_count=0`，因此 plan 为 `no_allowed_candidates`、`patch_count=0`；alternate approved SVG 链路可以得到 `ready_for_developer_apply` patch proposal，但该层仍不复制 candidate、不创建 processed 文件、不写正式 manifest、不改 StylePack / RenderPlan / frontend default / runtime map truth。当前 `MapComponentMediaManifest v0.1` 只允许 processed SVG，PNG/WebP candidate 必须标记为 `blocked_manifest_schema_incompatible`，不得成为 ready patch。
- `shared/schemas/map_component_manifest_apply_report.v0.1.schema.json`、`tools/media/apply_map_component_manifest_patch_plan.py`、`tools/media/validate_map_component_manifest_apply_report.py`、`examples/review_packs/map_component_manifest_apply_approval_plan.v0.1.json`、`examples/review_packs/map_component_manifest_apply_report.v0.1.json`
  - MapComponentManifestApplyReport v0.1 是 patch plan 之后的 developer-approved SVG replacement build/report 层。它读取 patch plan + 显式 approval plan，只接受 `ready_for_developer_apply` 且 `replacement_source.file_type == svg` 的 patch，复核候选本地文件存在、sha 匹配、proposed processed path / public URL 与当前 manifest item 对应；可在调用方显式传 `--output-manifest` 时写 replacement manifest artifact，但默认不覆盖正式 `game_data/media/map_components/map_component_media_manifest.v0.1.json`。实际复制 candidate 到 processed 目标还需要额外显式 `--copy-files`。默认 approval plan 为空，因此默认 report 为 `no_approved_patches`、`applied_patch_count=0`，并明确 `style_pack_modified=false`、`render_plan_modified=false`、`frontend_default_modified=false`、`runtime_map_truth_modified=false`、`candidate_file_copied=false`。
- `shared/schemas/map_component_manifest_patch_plan.v0.2.schema.json`、`tools/media/build_map_component_manifest_patch_plan_v02.py`、`tools/media/validate_map_component_manifest_patch_plan_v02.py`、`examples/review_packs/map_component_manifest_patch_plan.v0.2.json`
  - MapComponentManifestPatchPlan v0.2 是 v0.2 preview manifest 的旁路 patch proposal 层，不替换 v0.1 plan，也不让前端默认消费 v0.2。它默认读取 `game_data/media/map_components/map_component_media_manifest.v0.2.json`，允许通过 candidate review、visual quality 和 promotion gate 的 `svg/png/webp` 单图 generated candidate 成为 `ready_for_developer_apply`，并把 replacement 会改变的 `media_kind/file_type/local_path/url/sha/width/height/source_kind` 写入 `proposed_manifest_item`；`atlas_animation` 仍阻断为 apply 暂不支持。默认正式链路仍为 `no_allowed_candidates` / `patch_count=0`。
- `shared/schemas/map_component_manifest_apply_report.v0.2.schema.json`、`tools/media/apply_map_component_manifest_patch_plan_v02.py`、`tools/media/validate_map_component_manifest_apply_report_v02.py`、`examples/review_packs/map_component_manifest_apply_report.v0.2.json`
  - MapComponentManifestApplyReport v0.2 是 v0.2 patch plan 之后的 developer-approved 单图 replacement report 层。它只接受 `ready_for_developer_apply` 的 `svg/png/webp` patch，复核候选文件存在、sha、扩展名和 SVG/PNG/WebP 文件规则；默认不复制文件、不写正式 v0.2 manifest，approval 为空时即使传 output manifest 也不会生成 replacement artifact。有 approval 时必须传 `--output-manifest`，且只有 replacement manifest 能通过正式 v0.2 validator 时才写出；否则记录 blocked report，保持 StylePack / RenderPlan / frontend / runtime 全 false。
- `frontend/app.js` 与 `tools/frontend/validate_battle_visual_contract.py`
  - 前端玩家战斗画面已经消费 `map_render_plan_bundle` / `MapStylePack` 的表现层颜色，并读取 `ProceduralMapRenderPlan` 的道路宽度、路肩宽度和部署基座 footprint 等表现层几何参数；`MapRuntimePackage` 仍是路径、塔位、目标、出生点和碰撞事实源。
- `tools/asset_graph/render_procedural_map_preview.py`、`tools/asset_graph/validate_procedural_map_preview_report.py`、`examples/map_render_previews/`、`tools/demo/export_evidence.py`
  - 地图 RenderPlan 的离线审查预览入口：用 RuntimePackage 提供语义坐标、StylePack 提供颜色、RenderPlan 提供表现层几何参数，输出 review-only SVG 和 report；统一 demo evidence 会动态纳入 `*.procedural_map_preview_report.json` 并展示 `procedural_map_previews` 摘要；不得作为 published visual layer 或玩家 runtime 背景。
- `shared/schemas/map_runtime_package.v0.2.schema.json`、`tools/asset_graph/map_runtime_package_v02.py`、`examples/map_runtime_packages_v02/`
  - MapRuntimePackage v0.2 强语义 preview：在不替换当前 v0.1 正式 runtime 包的前提下，旁路表达资源点、机关区、防守锚点和阻挡区；统一 demo evidence 会纳入 `map_runtime_packages_v02` 摘要，但前端/后端默认路径仍使用 v0.1。
- `examples/map_render_plans_v02/`、`examples/semantic_visual_consistency_reports_v02/`、`examples/map_render_previews_v02/`
  - MapRuntimePackage v0.2 强语义的 RenderPlan / SVG preview 旁路证据：资源点、机关区、防守锚点和阻挡区来自 `MapRuntimePackage v0.2 preview`，StylePack 只提供 procedural prefab / palette；统一 demo evidence 会纳入 `procedural_map_previews_v02`，但这些 SVG 仍是 review-only，不是玩家 runtime 或 published visual layer。
- `backend/app/services/map_runtime_service.py`、`backend/app/services/map_render_plan_service.py`、`backend/app/api/frontend_mock.py`
  - 后端已暴露 review-only `/api/sessions/{session_id}/battles/{node_id}/map-v02-preview`：聚合 `MapRuntimePackage v0.2 preview`、v0.2 RenderPlan bundle、语义一致性报告、preview report 和 SVG ref。该接口只用于审查 / Studio / 录屏证据，`runtime_activation_allowed=false`，不改变默认 `/map-runtime-package` 的 v0.1 玩家运行时路径。
- `tools/dev/check_map_v02_preview_api.py`、`examples/review_packs/map_v02_preview_api_smoke_report.v0.1.json`
  - 后端 v0.2 地图预览 API 的 TestClient smoke 证据：创建匿名 session，逐节点请求 `/map-v02-preview`，确认 v0.2 强语义可读、默认 `/map-runtime-package` 仍保持 v0.1、unknown node 返回 404，且 provider 调用、`.env` 读取、玩家默认 runtime 修改均为 0。
- `tools/media/build_map_runtime_promotion_readiness_report.py`、`tools/media/validate_map_runtime_promotion_readiness_report.py`、`examples/review_packs/map_runtime_promotion_readiness_report.v0.1.json`
  - 地图 runtime 晋升准备度读模型：聚合默认 `MapRuntimePackage v0.1`、`MapRuntimePackage v0.2 preview`、v0.2 RenderPlan、SemanticVisualConsistencyReport、MapCompilePackage 和地图视觉发布闸门，逐节点说明 v0.2 强语义已经形成 promotion candidate，但仍被显式 activation gate 与 review-only/拒绝候选隔离要求阻断。该报告不调用 provider、不读取 `.env`、不写世界状态、不替换玩家默认地图。
- `tools/media/build_map_runtime_activation_gate_report.py`、`tools/media/validate_map_runtime_activation_gate_report.py`、`examples/review_packs/map_runtime_activation_gate_report.v0.1.json`
  - 地图 runtime 激活授权记录层：默认 `MapRuntimeActivationAuthorizationReport v0.1` 为 `pending_developer_approval`，三张节点都有授权记录但均未批准，且 runtime/backend/frontend/world/provider 修改数均为 0。它是 activation gate 的输入之一，不是激活命令。
  - 地图 runtime 显式激活门：读取 readiness、v0.2 preview API smoke、视觉发布闸门、激活授权记录和 v0.1/v0.2 地图包，逐节点给出 activation decision。当前三张节点均为 `blocked`，允许数为 0，阻断原因为显式开发者激活授权未批准、review-only/拒绝候选隔离、API/frontend 合同更新和激活后证据复跑。该报告是 gate/evidence，不修改默认 runtime、后端接口或前端行为。
- `tools/asset_graph/map_path_geometry.py`、`tools/asset_graph/build_map_path_geometry_report.py`、`tools/asset_graph/validate_map_path_geometry_report.py`、`shared/schemas/map_path_geometry_report.v0.1.schema.json`、`examples/review_packs/map_path_geometry_report.v0.1.json`
  - P1-MAP-F/G 的路径几何与塔位放置支撑：只从 `MapRuntimePackage v0.1 / v0.2 preview` 的 `path_routes.waypoints` 派生 sampled centerline、route length、turn hints、road band envelope 和塔位距离统计。该 helper/report 不读取 `.env`、不调用 provider、不从图片 / SVG / preview / AI candidate 反推地图语义，也不替换玩家默认 runtime 包；builder 已在自动派生 `build_slots` 时使用连续 road-band footprint 距离避让，旧信号塔历史重叠 fixture 已重建，当前 `MapPathGeometryReport` 为 `passed` 且 warning 为 0。
- `tools/dev/check_mvp_primary_api_flow.py`、`examples/review_packs/mvp_primary_api_flow_smoke_report.v0.1.json`
  - MVP 玩家主流程 API smoke 证据：启动本地 `uvicorn` 临时服务和临时 SQLite，走通匿名 session、世界实例、开场、mock pack、大地图、campaign router、预取、节点 briefing、研发 proposal/job、战斗配置、runtime package、MapRuntimePackage、RenderPlan、v0.2 地图预览、战斗结果、latest settlement 和 session evidence；该报告纳入统一 demo evidence，证明主路径可通过真实本地 HTTP 调用完成。
- `tools/frontend/capture_frontend_flow_visual_smoke.py`、`tools/frontend/validate_frontend_flow_visual_smoke_report.py`
  - 浏览器玩家链路截图门禁：用真实 Chromium 与 no-build 静态前端，从本地档案入口、开局配置、开场叙事、大地图、现场试作、塔防战斗走到战后结算，输出桌面 / 移动 14 张截图和结构化 smoke report。该工具不调用 provider、不读取 `.env`、不写世界状态；`flowVisualSmoke` query 只用于截图时加速战斗，不改变正常玩家入口。
- `tools/demo/run_demo_evidence_suite.py`
  - MVP 录屏 / 评审前一键证据套件：串联浏览器玩家链路截图、截图 report 校验和 `export_evidence.py --frontend-flow-smoke-report`，输出本地 suite report；默认要求真实 Chromium 可用，显式 `--allow-missing-browser` 才允许降级，不调用 provider、不读取 `.env`、不提交截图到仓库。
- `tools/demo/build_mvp_demo_readiness_report.py`、`examples/review_packs/mvp_demo_readiness_report.v0.1.json`
  - MVP 演示 readiness 总报告：从主流程 API、v0.2 地图预览 API、核心对象对齐、地图视觉发布安全、运行时 sprite 几何质量、循环动画连续性、视频 provider 离线边界和失败地图候选隔离等已审 evidence 推导 `ready_for_mvp_demo_with_known_limitations`；该报告不调用 provider、不读取 `.env`、不生成新内容，只作为录屏 / 评审 / 合并前的顶层验收摘要。`provider_video_boundary` 是非必需 warning gate，只证明 video adapter dry boundary、receipt/envelope 和 scheduler handoff 模板可见且不调用 provider，不代表 live video provider 或真实图生视频关键帧已经进入玩家 runtime。

### AI 编译器与 AssetGraph

- `docs/AI_COMPILATION_SYSTEM_V0_1.md`
  - 当前 AI 编译总架构边界事实源。定义 Context Engine、Object Compiler、World Transaction System、Generation Scheduler，以及 CGOP、ContextPackage、FactEntry、WorldStateDelta / WorldStateDeltaTransaction、GenerationExecutorRunRequest 映射的 v0.1 边界。具体字段仍以 schema 和 semantic gate 为准。
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
  - ProviderOutputEnvelope 之后的本地候选 artifact 暂存层：只登记 review-only local refs、校验状态和 promotion gate，不声明 runtime-ready；图片候选失败示例已覆盖 local PNG 合法但 media / semantic gate 失败的阻断路径。
- `docs/PROVIDER_ARTIFACT_PROMOTION_REPORT_V0_1.md`
  - ProviderArtifactStagingManifest 之后的显式晋升/阻断报告：决定候选是否可进入 runtime package build、WorldStateDeltaTransaction build 或 published media 更新；图片候选失败示例使用 `blocked_validation_failed`，确保差图只能作为负样本 evidence。
- `docs/CORE_ARTIFACT_ALIGNMENT_REPORT_V0_1.md`
  - AI 编译核心对象对齐审计报告：扫描前端 mock pack、review pack、provider staging/promotion 示例和事务链，说明哪些已经携带 ContextPackage / FactEntry / CGOP / WorldStateDeltaTransaction 原生字段或 refs，哪些仍需迁移。
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
- `shared/schemas/generation_executor_run_request.v0.1.schema.json`
  - GenerationExecutorRunRequest 字段级事实源：live executor guard 之后、provider adapter 之前的 review-only 执行请求包，只保存 source refs、预算、授权门和必过 gates，不调用 provider、不保存 prompt / provider 正文、不写世界状态。
- `shared/schemas/provider_execution_authorization.v0.1.schema.json`
  - ProviderExecutionAuthorization 字段级事实源：GenerationExecutorRunRequest 之后、provider adapter 之前的显式授权记录，只授权 provider adapter 执行边界，不读取 `.env`、不调用 provider、不保存 prompt / provider 正文、不写世界状态、不激活 runtime。
- `shared/schemas/provider_adapter_execution_receipt.v0.1.schema.json`
  - ProviderAdapterExecutionReceipt 字段级事实源：ProviderExecutionAuthorization 之后、ProviderOutputEnvelope 之前的 provider adapter 边界回执。fixture 模式不读取 `.env`、不调用 provider；live 模式也只能保存脱敏摘要、digest 和本地 refs，不写世界状态、不激活 runtime。
- `tools/provider_adapter/run_provider_adapter.py`
  - Provider adapter runner 工具层事实源：默认 fixture dry-run，不读取 `.env`、不调用 provider；显式 `--mode llm_text --live` 才允许调用 LLM adapter，显式 `--mode image --live` 才允许调用 image provider 并下载为本地 review-only image ref；`--mode video` 目前只是离线 video 边界，输出 review-only receipt/envelope 并以 `finish_reason=video_live_provider_not_implemented` 表达真实图生视频尚未接入，`--mode video --live` 必须快速失败。Generation Scheduler 的 runner handoff / outbox 只暴露不带 `--live`、不要求 dotenv 的 `command_templates.video_boundary`，不提供 live video 模板。live text/image 模式都只能输出 ProviderAdapterExecutionReceipt、ProviderOutputEnvelope 和本地 refs / digest / redacted summary，不保存 prompt 正文、provider 响应正文、临时 URL 或 secret。
- `shared/schemas/provider_adapter_runner_handoff_outbox.v0.1.schema.json`
  - ProviderAdapterRunnerHandoffOutbox 字段级事实源：把 background handoff tick 的 `runner_handoffs[]` 固化为外部 runner 可消费的 review-only 批量交接单；它不是 provider 输出、staging manifest、promotion report、runtime package 或世界状态事务。其 `command_templates.video_boundary` 只能是 `--mode video` dry boundary，不能带 `--live` 或 `<authorized-dotenv-path>`。
- `tools/dev/validate_provider_adapter_runner_handoff_outbox.py`
  - ProviderAdapterRunnerHandoffOutbox 语义校验入口：拒绝 secret、prompt 正文、provider response、raw JSON / trace 等敏感内容，并检查 handoff source、授权 ref、建议 `/tmp` 路径、live 模板显式授权和 import 回灌合同。
- `shared/schemas/provider_artifact_staging_manifest.v0.1.schema.json`
  - ProviderArtifactStagingManifest 字段级事实源：把 ProviderOutputEnvelope 中的本地 refs 转入 review-only staging，仍不写世界状态、不激活 runtime、不绕过 media / semantic / human review / promotion gate。
- `shared/schemas/provider_artifact_promotion_report.v0.1.schema.json`
  - ProviderArtifactPromotionReport 字段级事实源：只表达显式晋升/阻断结论，不直接修改 runtime package、published media 或世界状态。
- `tools/dev/validate_provider_artifact_promotion_report.py`
  - ProviderArtifactPromotionReport 可执行语义事实源：批准类决策要求 required gates 全部通过；`blocked_review_required` 要求至少一个 required gate 未通过；`blocked_validation_failed` 要求至少一个 required gate 已失败。
- `shared/schemas/core_artifact_alignment_report.v0.1.schema.json`
  - CoreArtifactAlignmentReport 字段级事实源：只做内部 evidence / 迁移审计，不激活 review-only 产物、不写世界状态、不替代任何 runtime package 或事务构建器。

### 剧情、任务与世界状态

- `docs/CONTROLLED_NARRATIVE_WORLD_COMPILER_V0_1.md`
  - 剧情 / 世界生长如何受控服务玩法。
- `docs/NARRATIVE_GAMEPLAY_CONTRACT_V0_1.md`
  - 叙事节点和玩法输出之间的合同。
- `shared/schemas/world_state_delta.v0.1.schema.json`
  - WorldStateDelta 字段级事实源：所有可提交世界状态变化必须落到当前 `operations[]` 白名单，不能使用通用 `effects[]`、自然语言 summary 或 raw JSON patch 绕过。
- `tools/world_state/validate_world_delta.py`
  - WorldStateDelta 结构校验入口：schema、op 白名单、禁止字段和玩家可见文本基础检查。
- `docs/WORLD_STATE_DELTA_SEMANTIC_GATE_V0_1.md`
  - WorldStateDelta 语义门。
- `tools/world_state/validate_world_delta_semantics.py`
  - WorldStateDelta 语义校验入口：基于当前 RunWorldState、registry 和审查包边界确认引用、NPC、任务、随机事件、样品、研究等变化能否进入运行态。
- `tools/world_state/apply_world_delta.py`
  - WorldStateDelta 应用入口：只有结构校验和语义校验通过后的 delta 才能写入 `RunWorldState`。
- `shared/schemas/world_state_delta_transaction.v0.1.schema.json`
  - WorldStateDeltaTransaction 字段级事实源：包装现有 `WorldStateDelta v0.1` 的事务语义，不替换 delta schema，不新增可执行 effect DSL。
- `tools/world_state/validate_world_delta_transaction.py`
  - WorldStateDeltaTransaction 校验入口：检查事务外壳、delta 引用、preconditions、operation mapping、conflict policy、rollback policy 和 status。
- `docs/MVP_WORLD_STATE_DELTA_REVIEW_PACK_V0_1.md`
  - MVP 世界状态变化审查包。

### 媒体素材

- `docs/MEDIA_ASSET_QUALITY_PIPELINE_V0_2.md`
  - 图片生成、后处理、审查、修复和运行时就绪门禁。
- `docs/VIDEO_FRAME_ASSET_PIPELINE_V0_1.md`
  - 图片种子 -> 图生视频 -> 关键帧 -> 循环连续性检查 -> 批量后处理 -> atlas 的路线。
- `shared/schemas/frame_sequence.v0.1.schema.json` 与 `tools/media/validate_frame_sequence.py`
  - FrameSequence v0.1 字段级事实源和语义门：结构由 schema 固化；validator 拒绝 remote URL、provider / raw prompt / secret 等敏感键，检查 fixture review-only 标记，并验证 runtime sprite import 所需的 loop、fps、帧数、唯一 frame_index、本地 PNG 尺寸 / sha / 统一画布和 `/assets/` URL 合同。
- `shared/schemas/raw_video_sequence.v0.1.schema.json`、`tools/media/validate_raw_video_sequence.py` 与 `tools/media/extract_video_keyframes.py`
  - RawVideoSequence v0.1 字段级事实源和抽帧入口：只允许本地 raw video / review-only fixture metadata，不保存 provider 临时 URL、公网 URL、raw response、prompt、secret 或未审 payload；validator 拒绝 remote URL 与 provider / model / raw prompt / raw JSON / full trace / secret / unreviewed content 等敏感键，验证本地 video_ref sha、extraction fps / max_frames / loop；extractor 在 fixture 模式下只从 review-only `fixture_frames[]` 生成 `frame_sequence.v0.1`，真实视频模式必须依赖本地 `ffmpeg`，缺失时明确失败而不伪造帧。

当前状态：

```text
processed PNG 已可用于前端 mock。
animation seed 已可用于后续图生视频。
frontend_runtime_mock 已作为战斗运行时美术包入口，覆盖敌人、目标物、基础防御件、NPC 头像、地图 token 和程序化特效。
MapRuntimePackage v0.1 已作为三张 MVP 战斗节点运行时地图包入口，包含路径、塔位、目标、出生点和带质量状态的本地视觉层引用。
循环动画策略已确认：优先首尾同图 / end frame 控制，否则通过 seamless loop prompt 与 LoopContinuityCheck 修复。
MediaAtlasManifest v0.1 已作为 spritesheet 多帧入口接入前端、后端 mock API 和 demo evidence；实体 atlas PNG 已由确定性 frame sequence 打包生成，并已标注 `frame_source_kind` / `loop_continuity_ref`。
FrameSequence v0.1 已建立正式 schema 与 validator：`shared/schemas/frame_sequence.v0.1.schema.json` 负责字段结构，`tools/media/validate_frame_sequence.py` 负责本地路径、PNG/sha、fixture 标记、禁止 provider / remote URL payload 和 runtime sprite import 合同；`tools/media/import_video_keyframe_sequence.py` 复用同一 validator 后才允许写出候选 atlas。
RawVideoSequence v0.1 已建立正式 schema、validator 与 fixture 抽帧工具：`shared/schemas/raw_video_sequence.v0.1.schema.json` 负责字段结构，`tools/media/validate_raw_video_sequence.py` 负责 local-only、敏感键、fixture review-only、video_ref sha 和 extraction plan 语义门；`tools/media/extract_video_keyframes.py` 可把 review-only fixture_frames 转成 `frame_sequence.v0.1`，并为未来真实本地视频保留 ffmpeg 解码路径。当前验收只证明 fixture -> frame_sequence -> atlas import 链路，不声明真实 provider 视频已经完成。
LoopContinuityReport v0.1 已接入 frontend mock 与 runtime art 两套 atlas：当前所有动画机械连续性通过，但均标记为 deterministic placeholder warning，说明它们可用于 MVP 循环播放，却还不是最终真实图生视频关键帧。
真实图生视频关键帧仍未生成。
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
ControlledMapCandidateArtifactImportReport v0.1 已提供受控地图候选的本地 PNG 导入边界：`tools/media/import_controlled_map_candidate_artifacts.py` 只接受仓库内或 `/tmp` 下的本地 PNG，默认示例为 `awaiting_local_artifacts` 且不复制图片；显式 `--copy-files` 时才把人工 paintover 或外部 reference-image provider 下载后的 PNG 复制到 `node_candidates_controlled_v1` 候选槽并刷新 review-only sidecar。`tools/media/validate_controlled_map_candidate_artifact_import_report.py` 会复核路径边界、PNG sha、provider 调用数、runtime / MapRuntimePackage / published visual layer 修改数均为 0。该层不调用 provider、不读取 `.env`、不发布 runtime，只为下一步 candidate review 提供安全入口。
ControlledMapCandidateReview v0.1 已把上述 handoff sidecar 接入 `tools/media/build_node_map_candidate_review_pack.py`，当前审查状态为 `review_only_not_runtime_ready`，三个候选均 `awaiting_provider_or_paintover_output`。这证明受控候选已经进入统一候选审查门，但在真实 provider 或人工 paintover 产出图片前不会进入 alignment / runtime promotion。
ControlledMapTextFallbackGenerationRun v0.1 已用真实 Agnes 调用产出三张受控 text-fallback 地图候选，并记录 provider 调用数、图片路径和 sidecar；审查结果为 `review_only_not_runtime_ready`，三张均 `needs_regeneration`。失败原因包括箭头 / 控制形状 / 棋盘边框被烙进背景、未授权人物或塔位被模型自行添加、视觉路线与 MapRuntimePackage 拓扑不一致。该结果冻结为负样本证据：地图不应继续依赖纯文本整图生成，下一轮应走 reference-image provider、人工 paintover，或由 MapRuntimePackage 驱动的分层程序化底图。
MapVisualPromotionGateReport v0.1 已接入 demo evidence，用确定性规则交叉检查 review-only、`do_not_promote`、`needs_regeneration`、`awaiting_provider_or_paintover_output` 或补丁 review-only 的地图候选是否被误挂到玩家侧 `published_visual_layer`。当前阻断候选 22 个、published 玩家图层 4 个、违规 0 个；这证明差图已被隔离为 review/负样本证据，但不代表地图美术质量已完成。
MapPublishedVisualLayerAlignment v0.1 已把确定性逻辑对齐的 `battle_runtime_background.v0.2` 晋升为玩家可用 `published_visual_layer` fallback，旧 `painted_visual_layer` 保留为 `candidate_visual_layer` / `superseded_requires_overlay_correction` 证据。当前 map visual quality 不再报告 overlay correction blocker，只保留共享底图和非节点专属图层 warning。
MapRuntimePromotionReadinessReport v0.1 已接入 demo evidence，逐节点聚合 v0.1 默认 runtime、v0.2 preview、RenderPlan、语义一致性报告、MapCompilePackage 和视觉发布闸门。当前三张节点均为 `promotion_candidate_activation_required`：v0.2 强语义、RenderPlan 与语义一致性已满足候选条件，但 activation allowed 仍为 0，且还保留 review-only/拒绝候选隔离 blocker。因此它是 runtime 晋升读模型，不是激活命令。
MapRuntimeActivationAuthorizationReport v0.1 已接入 demo evidence，作为 v0.2 地图 runtime 激活前的显式开发者授权记录层。当前默认报告状态为 `pending_developer_approval`，三张节点均 `pending`，`activation_authorized_for_gate_count=0`，且 provider / runtime / backend / frontend / world 修改数均为 0；它只证明授权记录层存在，不会自动激活 v0.2。
MapRuntimeActivationGateReport v0.1 已接入 demo evidence，逐节点消费 readiness、授权记录与 preview API 证据并给出显式 activation decision。当前三张节点均为 `blocked`，允许激活数为 0；阻断项包括显式开发者激活授权未批准、review-only/拒绝候选隔离、API/frontend 合同更新和激活后证据复跑。因此 v0.2 强语义当前被正式登记为“候选但不可激活”，默认玩家 runtime 继续保持 v0.1。
FrontendProceduralBattleBackdrop v0.5 已完成一轮战场自然嵌入增强：默认玩家战斗画面不再绘制失败整图候选，而是由 `MapRuntimePackage` 的 grid、path_routes、build_slots、objectives 和 spawn_points 驱动 canvas 程序化绘制自然地形、场外地貌背板、可玩区碎边、道路地形融合、平滑土路、路肩、车辙、部署基座、塔位接地线、目标地基、入口雾潮、暗潮洼地、可玩地块边界、可部署台地、路线方向 cue、目标防御区和世界内废墟 / 补给 / 灯具地标。投影已按 runtime bounds 与 HUD safe area 做 contain fit，移动端不再用 cover 裁掉入口到核心的关卡链路；敌人生成也会按 `spawn_points.route_id` / route 轮转绑定多路线。静态合约会阻止控制图 / 参考图 / 棋盘 helper / 失败整图发布进入默认玩家视图，并要求保留 safe-area fit、场外背板、关卡碎边、道路地形融合、路线方向 cue、部署台地、塔位接地线、目标防御区、路肩、车辙、暗潮洼地与战场地标层；仍需持续截图或录屏做像素验收。
GenerationSchedulePlan v0.1 已作为 Generation Scheduler 的 review-only 计划包入口，覆盖 sync_blocking、background_prefetch、background、lazy、fallback_static 五类调度，并接入 demo evidence 与后端 session mock API；GenerationScheduleRunReport v0.1 已可离线 dry-run 调度计划并证明 provider 调用数和世界修改数为 0；`generation_schedule_queue_items` 已能提供 item 级队列视图、claim / complete / fail / retry / fallback 状态流转、attempt 预算和 dry-run worker step；`generation_schedule_worker_cache` 已提供 review-only worker step 执行痕迹；`generation_live_executor_guard.v0.1` provider guard log 已能记录真实 provider 执行前的显式授权阻断、artifact manifest 门、校验门和 activation gate；`GenerationExecutorRunRequest v0.1` 已定义 guard 之后、provider adapter 之前的脱敏执行请求包，并可登记到 `generation_artifact_ledger`；`ProviderExecutionAuthorization v0.1` 已定义 executor request 之后、provider adapter 之前的显式授权记录，并可登记到 `generation_artifact_ledger`；`ProviderAdapterExecutionReceipt v0.1` 已定义 authorization 之后、ProviderOutputEnvelope 之前的 provider adapter 边界回执，并可登记到 `generation_artifact_ledger`；`tools/provider_adapter/run_provider_adapter.py` 已能默认 dry-run 生成 ProviderAdapterExecutionReceipt / ProviderOutputEnvelope，显式 live LLM text 生成 redacted summary refs，显式 live image 生成本地 review-only image refs；`export-provider-adapter-runner-handoff` 已能从 latest run ledger 导出外部 runner 所需的脱敏 request / authorization、建议 `/tmp` 路径、runner argv 模板和 import 回灌请求体，且 fixture roundtrip 已证明 handoff runner_inputs 可生成 receipt/envelope、通过 import API 回灌 ledger，并在 prefetch-cache 中显示为 `review_only_envelope_ready`；`run-review-only-dispatcher-step` 已能在缺少 run 时创建 session 级 run，并把一个 queued 项按 dry-run worker、live guard、executor request、provider authorization、runner fixture 顺序推进到 receipt/envelope ledger 边界；`run-review-only-dispatcher-drain` 已能按 `max_items` 连续 drain 多个 queued provider-review 项，并返回 `stop_reason` 与 `remaining_eligible_count`；`run-review-only-background-executor-tick` 已作为更接近正式 daemon loop 的小预算 API 壳接入，默认处理 2 个、单次上限 8 个，并返回 prefetch cache 摘要；`run-review-only-background-handoff-tick` 已把同一 tick 的 dispatched 项批量导出为 `ProviderAdapterRunnerHandoffOutbox v0.1`；这些 dispatcher / tick / handoff tick / outbox 入口都不 staging、不 promotion、不 complete queue item、不激活 runtime；`ProviderOutputEnvelope v0.1` 已定义真实 provider 调用后允许保存的脱敏摘要和 artifact refs；`ProviderArtifactStagingManifest v0.1` 已定义这些本地 refs 进入 review-only 暂存区的清单和 promotion gate，并接入 demo evidence 摘要；`ProviderArtifactPromotionReport v0.1` 已定义 staging 之后的显式晋升/阻断报告，当前既有通用 review-required 示例，也有 image candidate 因 media / semantic gate 失败而 `blocked_validation_failed` 的负样本示例；`generation_artifact_ledger` 后端状态层已能把已校验的 executor request / authorization / adapter receipt / envelope / staging / promotion report 摘要登记到匿名 session SQLite 台账并暴露 GET / worker API，也已支持从仓库或 `/tmp` 导入外部 runner 输出的 receipt/envelope，以及在匹配 ProviderOutputEnvelope 已入账后导入 staging/promotion review 文件；`GET /api/sessions/{session_id}/generation-schedule/prefetch-cache` 已提供从 latest run 队列和 ledger 派生的只读预取缓存视图，按 schedule item 暴露 refs、cache_status、activation gate 和 promotion gate 摘要；这些层都不保存 prompt / provider 正文、不写世界状态、不激活候选。真实 live provider 后台执行器、视频 adapter、媒体后处理自动串接和跨请求持久化预生成产物仍未实现。
ContextPackage v0.1、FactEntry v0.1、CompiledGameObjectPackage v0.1 已有 schema、最小示例和统一 validator；Research Job proposal / job metadata、battle settlement evidence 与 frontend mock pack 已携带 ContextPackage、FactEntry、CGOP 原生快照，并保留 core artifact refs / world delta 兼容字段。CoreArtifactAlignmentReport v0.1 已把前端 mock pack、核心示例、事务链、provider staging/promotion 示例和 review pack 的核心对象对齐状态纳入 evidence；当前整体为 `passed`，无 validator 失败、无剩余 migration task。`mvp_compiler_review_dossier`、`mvp_stage_candidate_pack`、`mvp_multistage_stage_candidate_pack`、`mvp_multistage_content_pack`、`mvp_next_stage_compilable_object_plan`、`mvp_story_asset_review_pack`、`mvp_story_asset_promotion_report` 与 `mvp_stage05_plan_realization_report` 已明确为 `review_only_not_applicable`。
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
- 前端默认战斗底座：`frontend/app.js` 当前用 `drawProceduralTerrain()`、`drawPlayableFieldBoundary()`、`drawPath()`、`drawRouteFlowCues()`、`drawBuildableTerraces()`、`drawDeploymentBase()`、`drawObjectiveDefensiveZone()`、`drawTargetFoundation()` 和 `drawSpawnRift()` 从 `MapRuntimePackage` 稳定生成玩家默认战场画面；`MapStylePack` 提供表现色，`ProceduralMapRenderPlan` 提供道路宽度、路肩宽度和部署基座 footprint 等表现层几何参数，但路线、塔位、目标、出生点仍只来自 `MapRuntimePackage`；`computeBattleMetrics()` 已按 runtime bounds 与 HUD safe area 做 contain fit，多路线敌人会绑定 runtime route / spawn id；整张 map image 只保留为 future published layer / debug evidence 语义，不进入默认 preload 或 `drawBackdrop()`。`tools/frontend/validate_battle_visual_contract.py` 已把这一点纳入静态合约。
- 地图编译设计采纳：`docs/MAP_COMPILATION_DESIGN_V0_1.md` 已审查外部 AI 方案并项目化采纳其核心判断：AI 负责风格和组件，程序负责结构和对齐，Validator 负责可信。后续地图任务应优先推进 `MapStylePack`、`ProceduralMapRenderPlan` 和 `SemanticVisualConsistencyReport`，而不是继续 prompt-only 整图生成或从图片反推路线/塔位。
- 地图编译最小实现链路：`MapStylePack v0.1`、`ProceduralMapRenderPlan v0.1` 与 `SemanticVisualConsistencyReport v0.1` 已有 schema、validator、builder 和 `mvp_first_battle` 示例。`tools/asset_graph/build_procedural_map_render_plan.py` 会从 `examples/map_runtime_packages/mvp_first_battle.map_runtime_package.json` 与 `examples/map_style_packs/long_night_ruined_outpost.map_style_pack.json` 生成 `examples/map_render_plans/mvp_first_battle.procedural_map_render_plan.json` 和 `examples/semantic_visual_consistency_reports/mvp_first_battle.semantic_visual_consistency_report.json`。当前报告检查 route road band、build slot platform、objective marker、spawn marker、debug/reference 不进入 player default，以及 StylePack 可读性边界。
- MapStylePack component binding 审查门：`map_style_component_binding_report.v0.1` 已纳入统一 demo evidence，解析显式 `media:<stable_internal_id>` / `atlas:<animation_id>` 引用并记录 procedural fallback。当前三份 StylePack 已绑定 `MapComponentMediaManifest v0.1` 的 36 个 reviewed local SVG 组件，报告为 `passed`，resolved `36`、fallback `0`；这些组件仍只是表现层 evidence，不是 runtime semantic source。`tools/frontend/validate_map_component_frontend_contract.py` 会额外检查 `/assets/map_components` 静态挂载存在且前端默认不加载 / 不绘制这些组件。
- Map component AI 生成候选、晋升门与 manifest patch/apply evidence：统一 demo evidence 现在纳入 `MapComponentGenerationRequestPack -> MapComponentArtifactStagingManifest -> MapComponentCandidateReviewReport -> MapComponentVisualQualityReport -> MapComponentPromotionGateReport -> MapComponentManifestPatchPlan -> MapComponentManifestApplyReport`。当前 request pack 覆盖 36 个 baseline component；artifact staging 派生 36 个本地导入 slot，明确 `imported_count=0`、`awaiting_count=36`，且 staging 不等于 review passed；candidate review 记录并读取 artifact staging manifest，当前因无 imported slot 仍保持 `generated_candidate_count=0`、只存在 baseline fixture candidate；visual quality / cutout gate 只读取 generated candidate，当前 `generated_candidate_count=0`、`checked_candidate_count=0`、`passed_count=0`、状态为 `awaiting_generated_candidates`；promotion gate 显式读取 visual quality report 并把该状态写入顶层 summary 与 decision 证据，当前仍为 `promotion_allowed_count=0`、`baseline_preserved_count=36`；manifest patch plan 因此为 `no_allowed_candidates`、`patch_count=0`；manifest apply report 使用默认空 approval plan，保持 `no_approved_patches`、`applied_patch_count=0`、`manifest_replacement_written=false`、`candidate_file_copied=false`。本地 import 工具可以用最小 import plan 生成 alternate staging manifest 证明 1 个 generated candidate 会进入后续 gates；candidate / visual approval tools 可继续派生 alternate approved reports，并让 promotion gate 出现 `promotion_allowed_count > 0`，manifest patch plan 可为 SVG candidate 形成 `ready_for_developer_apply` proposal，apply 工具再按 developer approval plan 输出 replacement manifest/report；但默认 demo evidence 仍读取正式 0 imported / 0 promoted / 0 patch / 0 applied reports，且不会读取 approved alternate。这条链路只为未来真实图像/视频组件生成提供 request -> local artifact staging -> candidate review -> visual quality / cutout normalization -> promotion -> manifest patch proposal -> explicit apply report 结构，不改变玩家默认前端、MapRuntimePackage、StylePack、RenderPlan 或现有 MapComponentMediaManifest。
- 地图 RenderPlan 后端只读接入：`backend/app/services/map_render_plan_service.py` 已把 `gray_lantern_station`、`lamp_wick_store` 和 `old_signal_tower` 三个 MVP 战斗节点映射到 `MapStylePack`、`ProceduralMapRenderPlan` 和 `SemanticVisualConsistencyReport` bundle；`/api/sessions/{session_id}/battles/{node_id}/config` 与 `/runtime-package` 会返回 `map_render_plan_bundle`，`/map-render-plan` 提供单独读取入口。三节点报告当前均为 `passed`，debug/reference layer 均未进入 player default。
- 地图 RenderPlan 离线预览：`tools/asset_graph/render_procedural_map_preview.py` 已可为三张 MVP 地图生成 review-only SVG；`tools/asset_graph/validate_procedural_map_preview_report.py` 会检查 SVG digest、runtime 语义来源、StylePack 颜色来源、RenderPlan 表现几何来源和 usage policy。当前三张预览 report 均为 `preview_ready_review_only`，并已通过 `tools/demo/export_evidence.py` 纳入 demo evidence 的 `assets_and_media.map_visual_reference.procedural_map_previews` 摘要；这证明 RenderPlan 已是可执行表现计划，而不是只存在于 JSON 中。
- MapRuntimePackage v0.2 强语义 preview：`shared/schemas/map_runtime_package.v0.2.schema.json`、`tools/asset_graph/map_runtime_package_v02.py`、`tools/asset_graph/build_map_runtime_package_v02.py` 与 `tools/asset_graph/validate_map_runtime_package_v02.py` 已建立旁路扩展链路；三张 `examples/map_runtime_packages_v02/*.map_runtime_package_v02.json` 均包含资源点、机关区、防守锚点和阻挡区，并已纳入 demo evidence 的 `map_runtime_packages_v02` 摘要。该 preview 不改变 `backend/app/services/map_runtime_service.py` 的 v0.1 默认加载路径，也不发布任何视觉层。
- GenerationSchedulePlan v0.1 / GenerationScheduleRunReport v0.1：已有 review-only 计划包、dry-run 执行报告、schema、builder、validator、evidence 摘要、`GET /api/sessions/{session_id}/generation-schedule` session API、`generation_schedule_runs` 持久化 dry-run 运行记录，以及 `generation_schedule_queue_items` item 级队列视图、状态流转、attempt 预算、retry / fallback 和 dry-run worker step，用于声明并离线验证同步、预取、后台、懒加载和静态 fallback 内容。
- Generation Scheduler 后端状态层：`backend/app/services/generation_scheduler_service.py` 是当前 session 缓冲、dry-run run、队列状态流转、attempt 预算、retry / fallback、dry-run worker step、review-only worker cache 和 live executor guard 的实现入口；`frontend_mock_service.py` 只聚合玩家侧 fixture 与 evidence。
- GenerationExecutorRunRequest v0.1：`shared/schemas/generation_executor_run_request.v0.1.schema.json`、`tools/dev/validate_generation_executor_run_request.py`、`examples/generation_executor_requests/` 与 `POST /api/sessions/{session_id}/generation-schedule/workers/prepare-executor-request` 已作为 live executor guard 之后的执行请求包边界。它只准备 refs、预算、授权门和必过 gates，不调用 provider、不保存 prompt / provider 正文、不写世界状态、不激活 runtime。
- ProviderExecutionAuthorization v0.1：`shared/schemas/provider_execution_authorization.v0.1.schema.json`、`tools/dev/validate_provider_execution_authorization.py`、`examples/provider_authorizations/` 与 `POST /api/sessions/{session_id}/generation-schedule/workers/grant-provider-authorization` 已作为 GenerationExecutorRunRequest 之后、provider adapter 之前的显式授权记录边界。它只授权 `provider_adapter_execution_only`，不调用 provider、不保存 prompt / provider 正文、不写世界状态、不激活 runtime。
- ProviderAdapterExecutionReceipt v0.1：`shared/schemas/provider_adapter_execution_receipt.v0.1.schema.json`、`tools/dev/validate_provider_adapter_execution_receipt.py`、`examples/provider_adapter_executions/` 与 `POST /api/sessions/{session_id}/generation-schedule/workers/run-provider-adapter-fixture` 已作为 ProviderExecutionAuthorization 之后、ProviderOutputEnvelope 之前的 provider adapter 边界回执。当前 fixture 模式不调用 provider、不读取 `.env`、不保存 prompt / provider 正文、不写世界状态、不激活 runtime。
- Provider adapter runner v0.1：`tools/provider_adapter/run_provider_adapter.py`、`examples/provider_adapter_runs/` 与 `provider_adapter_runner` / `provider_adapter_image_runner` evidence 摘要已作为工具层执行入口。默认 `fixture` dry-run 只生成 receipt/envelope，不读 `.env`、不联网；显式 `--mode llm_text --live` 才允许调用 LLM adapter，并且只保存 digest、计数和 redacted summary refs；显式 `--mode image --live` 才允许调用 image provider，下载成本地 review-only image artifact，并且只保存 digest、本地 ref 和脱敏摘要；`--mode video` 当前只生成 review-only video 边界 receipt/envelope，`--mode video --live` 阻断为 `video_live_provider_not_implemented`。
- Generation activation gate read-model：`GET /api/sessions/{session_id}/generation-schedule/activation-gate` 已从 latest run 的 prefetch-cache 派生只读激活门视图，按调度项解释候选为什么仍被 runtime package / WorldStateDeltaTransaction / staging / promotion / provider envelope / authorization 等门阻断；该接口不创建 run、不推进 worker、不写 ledger、不调用 provider、不写世界状态、不激活 runtime。
- Generation shared prefetch cache index：`generation_shared_prefetch_cache` SQLite 表、`GET /api/sessions/{session_id}/generation-schedule/shared-prefetch-cache`、`GET /api/sessions/{session_id}/generation-schedule/shared-prefetch-cache/hits`、`POST /api/sessions/{session_id}/generation-schedule/workers/index-shared-prefetch-cache` 与 `POST /api/sessions/{session_id}/generation-schedule/workers/record-shared-prefetch-cache-reuse-candidate` 已作为跨 session 脱敏预取索引入口。它只登记 `promotion_allowed` 但仍等待 runtime package / WorldStateDeltaTransaction 和 activation gate 的候选，状态为 `promotion_allowed_pending_runtime_build`；hit 视图只用 `object_kind + object_ref` 对当前 latest run 做只读匹配，不随单个 session reset 清除，也不代表 runtime-ready。reuse candidate worker 只把命中写成当前 run 的 `shared_prefetch_cache_reuse_candidate` ledger evidence，并在 prefetch-cache 中标记 `shared_cache_reuse_pending_runtime_build`；它不调用 provider、不写世界状态、不激活 runtime。
- Generation artifact ledger 后端状态层：`generation_artifact_ledger` SQLite 表、`GET /api/sessions/{session_id}/generation-schedule/artifact-ledger`、`POST /api/sessions/{session_id}/generation-schedule/workers/prepare-executor-request`、`POST /api/sessions/{session_id}/generation-schedule/workers/grant-provider-authorization`、`POST /api/sessions/{session_id}/generation-schedule/workers/run-provider-adapter-fixture` 与 `POST /api/sessions/{session_id}/generation-schedule/workers/stage-provider-artifacts` 已能登记 fixture-backed GenerationExecutorRunRequest / ProviderExecutionAuthorization / ProviderAdapterExecutionReceipt / ProviderOutputEnvelope / ProviderArtifactStagingManifest / ProviderArtifactPromotionReport 摘要。`dry-run-step`、`live-executor-guard` 和 `prepare-executor-request` 支持可选 `schedule_item_id` 定向处理；`stage-provider-artifacts` 必须先看到 latest run 已有同 `ProviderOutputEnvelope.source.schedule_item_id` 的 `generation_executor_run_request`，已有同 `ProviderOutputEnvelope.provider_call.authorization_ref` 的 `provider_execution_authorization`，且已有同 schedule item / authorization ref 的 `provider_adapter_execution_receipt`，否则返回 409，避免 provider artifact ledger 绕过 live executor guard、执行请求边界、显式授权边界、adapter 边界或挂到错误调度项下。该 worker 已支持 `artifact_profile=default` 和 `artifact_profile=image_failure` 两个 fixture profile；后者会把图片候选失败门登记到同一后端 ledger，状态仍是 review-only / promotion blocked。`POST /api/sessions/{session_id}/generation-schedule/workers/run-fixture-executor-chain` 已作为最小执行器壳，把 dry-run、guard、executor request、授权、fixture adapter receipt 与 staging 串成一次请求，并从 fixture envelope 反推 schedule item / authorization ref 以防错挂。`POST /api/sessions/{session_id}/generation-schedule/workers/run-provider-adapter-runner-fixture` 已开始复用工具层 provider adapter runner 的 dry-run artifact builder，把 runner 形态的 receipt/envelope 安全落入 ledger。`POST /api/sessions/{session_id}/generation-schedule/workers/export-provider-adapter-runner-handoff` 已能只读导出外部 runner handoff 包：脱敏 request / authorization、建议 `/tmp` 路径、dry-run / live argv 模板和 import 请求体；该入口不生成 receipt/envelope、不写 ledger、不调用 provider。`POST /api/sessions/{session_id}/generation-schedule/workers/run-review-only-dispatcher-step` 已把一个 queued 且需要 provider review 的调度项编排到 runner receipt/envelope ledger 边界；`POST /api/sessions/{session_id}/generation-schedule/workers/run-review-only-dispatcher-drain` 已按 `max_items` 连续编排多个 eligible 项，并显式返回 `budget_exhausted` / `no_eligible_items` 停止原因；`POST /api/sessions/{session_id}/generation-schedule/workers/run-review-only-background-executor-tick` 已把 drain 包装成更接近后台 daemon loop 的小预算 tick，并返回 prefetch cache 摘要；`POST /api/sessions/{session_id}/generation-schedule/workers/run-review-only-background-handoff-tick` 已把本轮 dispatched 项批量导出为 `ProviderAdapterRunnerHandoffOutbox v0.1`，并由 outbox schema / validator 固化批量交接单合同。它们都不 staging、不 promotion、不 complete queue item、不激活 runtime。`POST /api/sessions/{session_id}/generation-schedule/workers/import-provider-adapter-runner-output` 已允许导入仓库内或 `/tmp` 下的 runner receipt/envelope 文件，并在重新校验 schema、敏感键和 ledger 授权链后登记。`POST /api/sessions/{session_id}/generation-schedule/workers/import-provider-artifact-review-output` 已允许导入仓库内或 `/tmp` 下的 ProviderArtifactStagingManifest / ProviderArtifactPromotionReport 文件，并要求对应 ProviderOutputEnvelope 已在同一 session/run/schedule item 的 ledger 中存在；导入时会重新校验 schema、敏感键、source staging ref、source envelope id 和 reviewed artifact refs。它们都是 Studio / evidence 用内部台账，不调用 provider、不读取 `.env`、不写世界状态、不激活 runtime。
- Provider runner handoff evidence：`tools/demo/export_evidence.py` 已在 `generation_scheduler.provider_runner_handoff`、`generation_scheduler.background_executor_tick` 与 `generation_scheduler.background_handoff_tick` 中导出 handoff export / dry-run runner / import / prefetch-cache roundtrip、后台 tick、外部 runner outbox 和 video dry boundary 模板摘要，并在 `summary.md` 与 `index.html` 展示 `fixture_roundtrip_covered`、`review_only_envelope_ready`、`review_only_tick_api_ready`、`review_only_handoff_tick_ready` 与 `video_dry_boundary_template_visible`。这只是演示证据摘要，不代表后端自动 live provider 执行器或 live video provider 已完成。
- ProviderOutputEnvelope v0.1：`shared/schemas/provider_output_envelope.v0.1.schema.json`、`tools/dev/validate_provider_output_envelope.py`、`docs/PROVIDER_OUTPUT_ENVELOPE_V0_1.md` 和 `examples/provider_output_envelopes/` 已作为真实 provider 输出安全信封入口。后续真实 executor 只能保存 redacted summary、本地 artifact refs、validation 状态和 activation gate，不能保存 prompt 正文、provider 响应正文或 runtime-ready 声明。
- ProviderArtifactStagingManifest v0.1：`shared/schemas/provider_artifact_staging_manifest.v0.1.schema.json`、`tools/dev/validate_provider_artifact_staging_manifest.py`、`docs/PROVIDER_ARTIFACT_STAGING_V0_1.md` 和 `examples/provider_artifact_staging/` 已作为 ProviderOutputEnvelope 后的本地候选 artifact 暂存入口。它只登记 review-only local refs、gate 状态和 promotion 阻断，不能替代 runtime package、WorldStateDeltaTransaction、media gate 或人工 review。
- ProviderArtifactPromotionReport v0.1：`shared/schemas/provider_artifact_promotion_report.v0.1.schema.json`、`tools/dev/validate_provider_artifact_promotion_report.py`、`docs/PROVIDER_ARTIFACT_PROMOTION_REPORT_V0_1.md` 和 `examples/provider_artifact_staging/p1b_provider_artifact_promotion_report.example.json` 已作为 staging 之后的显式晋升/阻断入口。报告本身不修改 runtime、published media 或世界状态。
- WorkerTaskPack v0.1：`shared/schemas/worker_task_pack.v0.1.schema.json`、`tools/dev/validate_worker_task_pack.py`、`docs/WORKER_TASK_PACK_V0_1.md` 和 `examples/worker_task_packs/` 已作为 worker 委派任务包入口。后续 CodeBuddy / OpenCode / Codex headless / 人类 worker 的任务应先声明必读事实源、允许路径、禁止路径、安全规则、provider policy、验收命令和汇报字段。
- Campaign Router v0.1：`backend/app/services/campaign_router_service.py` 是当前最薄运行时游标入口；它根据 `RunWorldState.progress.phase` 返回当前节点、下一节点、前视窗口、已审资产 handle 和 scheduler 信号，并可触发一次 fixture-backed dry-run 预取步，或显式触发一次 review-only dispatcher drain 预取 tick。no-build 前端已在 API 模式消费该 route，静态模式保留灰灯驿站首战兜底；dispatcher drain 入口暂作为 Studio / evidence 和后台执行器前置胶水，不自动替换前端旧 dry-run 调用。
- 多节点战斗结算桥：`backend/app/services/frontend_mock_service.py` 当前支持 `gray_lantern_station`、`lamp_wick_store`、`old_signal_tower` 三个路由节点的战斗结果提交。前两个节点使用 `battle_result` transaction；`old_signal_tower` 使用 stage06 `research_job` after-state 作为 `fixture_bridge`，并在 API 返回中显式标注来源，避免把研究任务基线误当战斗结果。
- AI 编译核心对象 schema：ContextPackage v0.1、FactEntry v0.1、CompiledGameObjectPackage v0.1 已有 schema、示例和统一 validator；`backend/app/services/ai_core_artifact_service.py` 是当前后端 refs / 示例加载入口，也是 Research Job proposal / job metadata 与 battle settlement evidence 原生快照构造入口。
- CoreArtifactAlignmentReport v0.1：`shared/schemas/core_artifact_alignment_report.v0.1.schema.json`、`tools/content_pipeline/build_core_artifact_alignment_report.py`、`tools/content_pipeline/validate_core_artifact_alignment_report.py` 和 `examples/review_packs/core_artifact_alignment_report.v0.1.json` 已作为核心对象迁移审计入口。它只报告 native / refs-only / missing / not-applicable / validation-failed 状态，不调用 provider、不读取 `.env`、不激活 runtime、不写世界状态；`mvp_compiler_review_dossier` 已通过自身 `core_artifact_alignment` 字段声明为总审查包，`mvp_stage_candidate_pack` 与 `mvp_multistage_stage_candidate_pack` 已声明为 review-only 阶段候选容器，`mvp_multistage_content_pack` 已声明为 review-only 多阶段内容生产审查包，`mvp_next_stage_compilable_object_plan` 已声明为 review-only 下一阶段编译计划，`mvp_story_asset_review_pack` 已声明为 review-only 剧情资产审查索引，`mvp_story_asset_promotion_report` 已声明为 review-only 资产晋升决策报告，`mvp_stage05_plan_realization_report` 已声明为 review-only 计划落地审查报告，八者都不应强行迁移成核心对象。
- WorldStateDeltaTransaction v0.1：已有 schema、首战 committed 示例、stage01-stage07 事务链、批量 validator 和 deterministic builder；它包装可通过语义门的 `WorldStateDelta`，并接入 demo evidence。
- AssetGraph workflow、节点注册表、runtime package 构建与校验。
- 多阶段叙事 / 世界状态 / 资产候选审查包。
- MVP handoff audit 一键验证。
- 演示证据导出脚本：可生成 `summary.md / evidence.json / index.html`。
- Runtime sprite live regeneration 候选：已为信标、基础灯栏与驿站核心生成 review-only PNG，并接入 cutout quality report 与 demo evidence。
- Runtime sprite 显式晋升：已把通过审查的信标、基础灯栏与驿站核心候选晋升到 published runtime media，重建 runtime atlas，并接入 promotion report。
- 前端 MVP 页面：已有本地可运行 mock 体验入口，已补桌面 / 移动浏览器截图烟测；后续仍需多节点和交互录屏验收。

当前尚未完成：

- 真实图生视频帧序列，以及用真实关键帧替换当前确定性 frame sequence 的默认接入；LoopContinuityReport 已经先行提供替换前后的循环连续性门禁。
- 新增 WorldStateDelta / review pack / provider artifact 与 ContextPackage、FactEntry、CGOP 字段的持续对齐；Research Job、battle settlement evidence、多节点 battle settlement、frontend mock pack 和 stage01-stage07 WorldStateDeltaTransaction 链已完成第一层原生快照 / 事务迁移。CoreArtifactAlignmentReport 当前已清零，未来新增产物若缺核心对象快照、core refs 或显式 not-applicable 边界，会重新进入迁移队列。
- 正式 Generation Scheduler 后台执行器、真实 provider 调度、跨请求持久化预生成产物和 runtime activation；当前 Campaign Router 已能显式触发 review-only dispatcher drain 预取证据，prefetch cache 也只能读取 latest run 的 queue / ledger 派生视图，仍不是真实后台执行器或正式产物缓存。
- 多世界书选择与长期存档系统。
- 多页面 / 多节点自动化浏览器视觉回归；当前只有首战桌面 / 移动截图烟测。

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
