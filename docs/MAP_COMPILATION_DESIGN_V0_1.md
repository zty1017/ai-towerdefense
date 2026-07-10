# 地图编译设计采纳审查 v0.1

Last updated: 2026-07-06

本文用于审查并项目化采纳外部 AI 给出的地图编译方案。该外部方案的核心建议是：

```text
不要再走 AI 整图生成 / 重绘 -> 反推路线和塔位。
应走逻辑层先行 + StylePack 统一视觉 + 程序化渲染 / 拼装。
```

审查结论：方向采纳，结构改写。

## 当前实现状态（2026-07-11）

地图编译必须拆开说明，不能只用“已完成”概括：

- 逻辑地图编译已接通：三张 MVP 战斗地图都有独立 `MapRuntimePackage`，路径、塔位、目标和出生点是结构化运行时事实。
- 世界书风格与分层组装已接通：每个节点都有独立 `MapStylePack`、`ProceduralMapRenderPlan` 和 `LayeredMapVisualPackage`，前端消费节点专属分层合成图。
- 编译证据绑定已修正：每个 `MapCompilePackage` 直接绑定对应节点的 `LayeredMapVisualPackage`，不再让三份编译包共用同一张通用背景。
- AI 媒体目前属于“已审本地导入”，不是“编译器运行内生成”：现有地形、道路和背景中包含 `local_ai_exploration_*` 资产，但历史生成过程没有完整进入 provider envelope、staging、review、promotion 和 activation 记录。
- 因此 `ai_media_generation_provenance` 当前必须是 `warning`。只有真实 provider 执行记录和产物晋升证据随同一次地图编译运行进入包内，才可以改为 `passed`。

当前准确口径是：

```text
结构化地图编译 + 世界书风格编译 + 分层运行包编译：已完成 MVP 闭环
AI 媒体自动生成并在同一次 DAG 中晋升：尚未完全接通
```

这不影响玩家使用已发布地图，但演示时不能把历史人工触发、人工挑选的 AI 地图素材描述成实时自动生成。

该方案与本项目当前证据一致：多轮 Agnes / text-fallback / topology-constrained 地图整图候选已经证明，图像模型会重构路径、塔位、目标和装饰布局；即使参考图和 overlay 能帮助审查，也不能让整图成为运行时事实源。因此，正式地图编译应从“AI 画一张地图”转为“结构化地图事实 + AI 生成风格和组件 + 程序确定性渲染”。

## 0. 2026-07-06 外部 v0.3 附件复审结论

本次附件可以作为地图编译方向的参考，但不应直接另存为 `MAP_COMPILATION_DESIGN.md` 后交给 worker 照做。原因是附件中的 `PathGraph`、`PlacementMap`、`LevelBundle` 等概念是通用建模语言；本项目已经有 `MapRuntimePackage`、`MapCompilePackage`、`MapStylePack`、`ProceduralMapRenderPlan`、`SemanticVisualConsistencyReport`、activation gate 和 evidence 导出链路。直接新增并列事实源会制造两套运行时地图真相。

采纳矩阵如下：

| 外部建议 | 本项目结论 | 落点 |
|---|---|---|
| 地图不是一张图，而是语义对象 + 视觉资产 + 规则约束 + 渲染结果 | 采纳 | 用 `MapRuntimePackage` 管强语义，`MapStylePack` / component manifest 管表现，RenderPlan / preview / report 管渲染证据。 |
| AI 不直接生成最终可运行整图 | 采纳并强化 | 整图候选只可作为概念图、封面、style reference、negative evidence 或人工 paintover 输入；不得成为默认玩家战场路线。 |
| 路线由程序控制形状，风格由 StylePack 控制表现 | 采纳 | 近期从 `path_routes.waypoints` 派生 sampled centerline / road band；后续再补 spline hints。 |
| 一次性建立 `PathGraph`、`SplinePath`、`PlacementMap`、`LevelBundle` 等新 schema | 不照搬 | 先增强现有 `MapRuntimePackage v0.2 preview -> RenderPlan -> SemanticVisualConsistencyReport -> activation gate` 链路。 |
| 玩家编译解法，开发者编译关卡，系统编译遭遇 | 采纳 | 普通玩家不直接改地图拓扑；地图模板、组件、关卡池由开发者 / 系统侧在门禁下编译。 |
| 输出 `preview.png` / `LevelBundle` | 改写采纳 | 预览图是 review-only evidence；未来如需完整关卡包，应由现有包聚合导出，不替换当前字段事实源。 |

因此，后续 worker 任务应从“改进当前可执行地图链路”出发，而不是从外部文档复制一套新目录：

```text
MapRuntimePackage v0.1 / v0.2 preview
  -> path geometry helper / road band
  -> placement and strong semantic validators
  -> MapStylePack component slots
  -> ProceduralMapRenderPlan
  -> SemanticVisualConsistencyReport
  -> review-only preview / screenshot / evidence
  -> explicit promotion / activation gate
  -> developer-approved runtime selector
```

## 1. 采纳原则

### 1.1 采纳：逻辑地图先行

本项目已存在的事实源继续保留：

```text
MapRuntimePackage v0.1
  -> 路径、塔位、目标、出生点、运行时提示、视觉层引用

MapCompilePackage v0.2
  -> 地图编译证据、控制图、候选图、对齐审查、质量门、导出引用
```

外部方案中的 `PathGraph`、`PlacementMap`、`CollisionMap`、`ResourceNodeMap`、`HazardZoneMap` 等概念，不应立即拆成一堆新 schema；第一步应映射到现有包：

`MapTemplateCatalog v0.1` 是更薄的一层开发者侧候选种子目录。它只记录可读的路径模板候选，例如 S 形单路、双路汇合、长折线、短线高压和中央环绕，用 normalized control points / suggested road width / slot strategy / semantic hook 摘要帮助开发者生成后续候选 `MapRuntimePackage` 或 review evidence。它不是 `PathGraph`、`PlacementMap` 或 `LevelBundle`，也不是玩家默认 runtime；模板不能从图片反推路径、塔位、资源、机关、防守或阻挡逻辑。任何模板被采用后，仍必须重新生成结构化 `MapRuntimePackage`，并经过现有 validator、RenderPlan、SemanticVisualConsistencyReport、evidence 和 activation gate。

当前字段级入口：

- `shared/schemas/map_template_catalog.v0.1.schema.json`
- `tools/asset_graph/build_map_template_catalog.py`
- `tools/asset_graph/validate_map_template_catalog.py`
- `examples/map_template_catalogs/mvp_map_template_catalog.v0.1.json`

`MapDecorationZonePolicy v0.1` 是对 `DecorationZoneMap` 思路的最小工程化采纳。它不新建与 `MapRuntimePackage` 竞争的地图事实源，而是从现有 `MapRuntimePackage v0.1 / v0.2 preview` 与 `path_routes.waypoints` 几何派生强语义保护区、弱语义可附着区、纯装饰区和氛围层约束，供 renderer / StylePack / 后续组件化地图使用。它的职责是告诉程序化渲染器“哪里不能放装饰、哪里可以低风险放装饰、氛围层不能遮挡什么”，不能反向修改路径、塔位、目标、出生点、资源、机关、防守锚点或阻挡区。

当前字段级入口：

- `shared/schemas/map_decoration_zone_policy.v0.1.schema.json`
- `tools/asset_graph/build_map_decoration_zone_policy.py`
- `tools/asset_graph/validate_map_decoration_zone_policy.py`
- `examples/map_decoration_zone_policies/mvp_map_decoration_zone_policy.v0.1.json`

| 外部概念 | 本项目当前映射 | 采纳方式 |
|---|---|---|
| `PathGraph` / `SplinePath` | `MapRuntimePackage.path_routes` | v0.1 仍用结构化 waypoints；后续 v0.2 可增加 sampled spline / road band。 |
| `PlacementMap` | `MapRuntimePackage.build_slots` | 保留为运行时塔位事实源；后续补距离道路、转角、瓶颈标签。 |
| `SpawnPoints` / `BasePoints` | `spawn_points` / `objectives.core_target` | 已存在，继续作为事实源。 |
| `CollisionMap` | `MapRuntimePackage v0.2 preview.blocked_areas` 与当前 validator 冲突检查 | 已旁路表达显式阻挡区，但仍不能从图片反推。 |
| `ResourceNodeMap` | `MapRuntimePackage v0.2 preview.resource_nodes` | 已作为 v0.2 preview 引入，前端默认 runtime 暂不切换。 |
| `HazardZoneMap` | `MapRuntimePackage v0.2 preview.hazard_zones` | 已作为 v0.2 preview 引入，后续再接环境 modifier / 战斗结算。 |
| `DecorationZoneMap` | `MapDecorationZonePolicy v0.1` + 当前前端程序化地标 / 边缘装饰 | 作为 review-only renderer helper 采纳；不成为玩法事实，不从图片反推。 |

### 1.2 采纳：AI 负责风格和组件，不负责运行时语义

AI 可以生成：

- 地表纹理、道路材质、道路边缘材质。
- 塔位平台、资源点、机关、障碍、非阻挡装饰等 sprite / prefab。
- 雾、光照、天气、远景、概念图和 StylePack 参考。
- 用于开发者审查的 mood board / style sheet。

AI 不允许决定：

- 怪物最终路径。
- 塔位最终坐标。
- 资源点、机关、防守点、碰撞区的最终语义。
- 哪些图片可以进入玩家 runtime。

任何 AI 产物都必须进入 provider envelope / staging / promotion / media gate / runtime package 或 MapCompilePackage 审查链，不能直接被前端默认加载。

### 1.3 采纳：StylePack，但先作为编译期约束

外部文档提出的 `StylePack` 是值得采纳的关键概念。它解决的是：程序化地图容易像调试图，整图生成又不可信。

本项目第一版 StylePack 应包含：

```text
style_pack_id
worldbook_id
node_theme_tags
palette
lighting
terrain_materials
road_materials
road_edge_rules
build_slot_platforms
objective_prefabs
spawn_prefabs
resource_prefabs
hazard_prefabs
blocking_props
non_blocking_props
decorative_props
atmosphere_layers
postprocess
readability_rules
```

StylePack 不是运行时事实源。它只影响表现层，并且必须服务 `MapRuntimePackage` 的结构化事实。

`MapStylePack` 可以携带显式组件媒体引用，但这些引用必须经过单独的 component binding 审查门：

```text
MapStylePack material.component_ref / prefab visual_ref
  -> MapComponentMediaManifest
  -> MapStyleComponentBindingReport
  -> reviewed media / atlas ref 解析证据
  -> ProceduralMapRenderPlan 表现层元数据
```

`MapComponentMediaManifest v0.1` 只登记 reviewed local component media：local refs、sha256、width/height、component_role、style_pack_id / node_id 和 usage policy。它可以让 `/assets/map_components/...` 的表现层组件 URL 在后端只读静态挂载中可解析，但不表示前端默认会消费这些组件，也不允许组件反向决定任何地图语义。

`MapComponentMediaManifest v0.2` 是旁路 / preview manifest，不替换正式 v0.1 manifest，也不改变默认前端消费。当前 v0.2 从 v0.1 deterministic SVG baseline 迁移，仍保持 36 个 stable component id、sha、StylePack / node / source binding 不变；新增 `media_kind`、`file_type`、`media_kind_counts`、`single_image_count`、`atlas_animation_count` 等字段，以便后续承接 PNG、WebP 和 atlas animation 引用。v0.2 继续声明 `not_runtime_semantic_source`、`no_image_to_map_semantic_inference`、`no_frontend_default_consumption`、`no_provider_or_prompt_payload` 和 `no_external_temporary_url`，并由独立 validator 校验本地路径、sha、文件头、SVG 安全规则和 atlas 引用存在性。

当前真实 AI 组件生成尚未接入 provider。为了让后续图像 / 视频组件候选有可审查入口，组件媒体链路先扩展为 review-only 门禁结构：

```text
MapComponentMediaManifest deterministic SVG baseline
  -> MapComponentGenerationRequestPack
  -> MapComponentArtifactStagingManifest
  -> MapComponentCandidateReviewReport
  -> MapComponentVisualQualityReport
  -> MapComponentPromotionGateReport
  -> MapComponentManifestPatchPlan
  -> MapComponentManifestApplyReport / optional replacement manifest artifact

MapComponentMediaManifest v0.2 preview
  -> MapComponentManifestPatchPlan v0.2
  -> MapComponentManifestApplyReport v0.2 / optional replacement manifest artifact
```

`MapComponentGenerationRequestPack v0.1` 只从现有 manifest 派生每个组件的生成请求摘要：component_id、component_role、style_pack_id、node_id、baseline_local_path、target_size、prompt_profile_id、negative constraints、required gates 和 usage policy。它可以包含 redacted prompt summary / structured prompt tokens，但不得保存 provider/model/raw prompt/full trace/raw JSON/secret/unreviewed content 或外部临时 URL。

`MapComponentArtifactStagingManifest v0.1` 是 request pack 之后、candidate review 之前的 review-only 本地 artifact 导入边界。它把 36 个 request 派生为 36 个 staging slot，声明外部 provider 或人工生成的本地 `png/svg/webp` 候选如何进入候选池；当前没有真实候选，因此所有 slot 都是 `awaiting_local_artifact` / `not_imported`，`imported_count=0`、`awaiting_count=36`。非空 candidate path 只能来自仓库内 `game_data/media/map_components/candidates/` 或 `/tmp/...` 本地文件，并必须通过存在性、sha256 和扩展名校验。staging 只说明“可进入后续审查的导入边界”，不代表 review passed，也不写 manifest、不改 StylePack / RenderPlan / frontend default / runtime map truth。

`MapComponentCandidateReviewReport v0.1` 是本地 artifact staging 之后的审查层。报告顶层记录 `source_artifact_staging_manifest_path`，并且 generated candidate 只能来自 artifact staging 中 `imported` + `staged_for_review`、本地 path / sha 匹配的 slot。当前 artifact staging 没有真实生成候选，`imported_count=0`，因此 36 个 baseline SVG 仍只能作为 `baseline_fixture_candidate` / `no_generated_candidate_yet` 负责任地占位，`generated_candidate_count=0`，不能伪装成 AI 生成结果。默认 builder 会阻断晋升，并要求后续导入本地生成 artifact、visual QA、cutout / normalization 和 binding refresh；只有 `tools/media/approve_map_component_candidate_review.py` 在读取显式 approval plan 时，才能从 imported alternate report 派生带 `approval_record` 的 alternate candidate-approved report，使指定 generated candidate 进入 `passed` / `eligible_for_promotion` / `promotion_allowed_now=true`。baseline fixture 永远不能 approval / promotion，该 approval 工具也不写正式 report、manifest 或 runtime。

`MapComponentVisualQualityReport v0.1` 是 candidate review 之后、promotion gate 之前的本地文件质量 / cutout normalization gate。它默认读取 `MapComponentCandidateReviewReport`，只对 `candidate_kind == generated_candidate` 的条目执行本地检查；baseline SVG fixture 不进入该 report，也不能被当作 generated candidate。当前默认没有 generated candidate，因此 report 为 `awaiting_generated_candidates`，`generated_candidate_count=0`、`checked_candidate_count=0`、`passed_count=0`，validator 仍通过，表示结构化等待/阻断状态而不是伪造通过。未来 generated candidate 进入该层时，报告会复核 candidate review 提供的 local path / sha，记录文件类型、sha、size；PNG 会检查尺寸、alpha visible ratio、subject bbox、edge contact 和 cutout review 状态；SVG 会检查 `<svg`、script 和远程引用；WebP 在无本地 decode 依赖时只能标记为 `needs_review_unsupported_decode`。默认 builder 对无文件级 issue 的 generated item 仍只进入 `needs_review`；只有 `tools/media/approve_map_component_visual_quality.py` 在读取显式 approval plan 时，才能从 alternate visual report 派生带 `approval_record` 的 visual-approved report，使指定 item 进入 `passed`。该层即使 passed 也保持 `promotion_allowed_now=false`、`runtime_ready=false`、runtime / promotion effect 全 false，仍必须等待显式 promotion gate。

`MapComponentPromotionGateReport v0.1` 是显式晋升门。它默认读取 `MapComponentVisualQualityReport v0.1`，顶层记录 `source_visual_quality_report_path`，并在每个 decision 中写入 visual quality report 状态、匹配 item 状态、是否已检查、是否必需和阻断原因；baseline fixture 不要求 visual item。当前 visual quality report 为 `awaiting_generated_candidates`，`promotion_allowed_count=0`、`baseline_preserved_count=36`，且不写新的 manifest、不改 StylePack、不改 RenderPlan、不改前端默认消费、不改 runtime map truth。alternate 链路可以从 imported staging 继续派生 candidate-approved / visual-approved reports，使 promotion gate 对指定 generated candidate 给出 `allowed` 并让 `promotion_allowed_count > 0`；但 promotion gate 仍只写 report，runtime_effect 全 false，不执行 manifest replacement 或 runtime activation。未来 generated candidate 的 promotion 条件必须同时满足 candidate review 自身允许、visual report 中存在匹配 item、该 item 为 `passed`，并且 runtime readiness 仍由更后续发布机制决定；v0.1 不把 visual `runtime_ready` 放宽为晋升条件。

`MapComponentManifestPatchPlan v0.1` 是 promotion gate 之后、正式 apply 之前的 review-only 计划层。它只把 `MapComponentPromotionGateReport` 中 `allowed` 的 generated candidate decision 映射成 manifest patch proposal，并回查 candidate review、visual quality 和当前 `MapComponentMediaManifest`：默认正式链路没有 allowed candidate，因此输出 `no_allowed_candidates`、`patch_count=0`；approved alternate SVG 链路可以得到 `ready_for_developer_apply` proposal，指向当前 processed SVG 的同名替换目标和 `/assets/map_components/processed/...svg` public URL，但仍不复制文件、不创建 processed 产物、不写正式 manifest、不改 StylePack / RenderPlan / frontend default / runtime map truth。由于 `MapComponentMediaManifest v0.1` 只接受 processed SVG，PNG/WebP generated candidate 即使通过前置 gate，也必须在 patch plan 中标记为 `blocked_manifest_schema_incompatible`，等待 manifest schema 扩展或新版本发布。

`MapComponentManifestApplyReport v0.1` 是 patch plan 之后的 developer-approved replacement build 证据层。它读取 patch plan 和显式 approval plan，只接受 `patch_status == ready_for_developer_apply` 且 `replacement_source.file_type == svg` 的 patch，复核 candidate local path 存在、sha 匹配、proposed processed path / public URL 与当前 manifest item 一致，然后可按调用方传入的 `--output-manifest` 写出 replacement manifest artifact。默认正式 approval plan 为空，因此 report 为 `no_approved_patches`、`applied_patch_count=0`，不会复制 candidate、不会改正式 `MapComponentMediaManifest`；只有额外显式 `--copy-files` 才会把候选 SVG 复制到 processed 目标。无论是否写 replacement artifact，该层都明确 `style_pack_modified=false`、`render_plan_modified=false`、`frontend_default_modified=false`、`runtime_map_truth_modified=false`，并记录 source/output manifest path 与 before/after sha。

`MapComponentManifestPatchPlan v0.2` / `MapComponentManifestApplyReport v0.2` 是 v0.2 preview manifest 的旁路链路，不替换 v0.1 patch/apply，也不让前端默认消费 v0.2。v0.2 patch plan 默认读取 `game_data/media/map_components/map_component_media_manifest.v0.2.json`，让通过前置 gate 的 `svg/png/webp` 单图 generated candidate 可以表达为 `ready_for_developer_apply`，并把 replacement 会改变的 `media_kind/file_type/local_path/url/sha/width/height/source_kind` 写入 proposal；`atlas_animation` 当前只记录为 apply 暂不支持。v0.2 apply 只在显式 approval 后复核候选本地文件、sha、扩展名和 SVG/PNG/WebP 文件规则；若不能保证 replacement manifest 通过正式 v0.2 validator，就只输出 blocked report，不写坏 manifest、不复制正式 processed 文件、不改 StylePack / RenderPlan / frontend default / runtime map truth。默认正式 examples 仍保持 `no_allowed_candidates` / `patch_count=0` 和 `no_approved_patches` / `applied_patch_count=0`。

该报告只证明“这个 StylePack 声称使用的组件媒体是否存在、是否已审、是否仍回退到程序化表现”。Manifest 与报告都不是 runtime semantic source，不得替代 `MapRuntimePackage` 的路径、塔位、目标、出生点、资源、机关、阻挡或碰撞事实，也不得从图片、atlas 或 prefab 外观反向推导地图语义。外部临时 URL、provider/model/raw prompt/full trace/raw JSON/secret/unreviewed content 等字段不能成为通过项。

### 1.4 采纳：程序化分层渲染

当前前端已走向正确方向：`drawProceduralTerrain()`、`drawPath()`、`drawBuildableTerraces()`、`drawDeploymentBase()`、`drawObjectiveDefensiveZone()` 等函数已经从 `MapRuntimePackage` 派生玩家默认战场，而不是绘制失败整图候选。

下一步应把这套前端实现上升为正式编译管线：

```text
MapRuntimePackage
  -> MapStylePack
  -> ProceduralMapRenderPlan
  -> preview.png / runtime canvas layers
  -> SemanticVisualConsistencyReport
```

当前实现已经补上最小 runtime selector：默认授权记录 pending 时，后端玩家默认路径仍返回 `MapRuntimePackage v0.1`；当本地显式开发者授权报告批准某个 v0.2 目标且 target 匹配时，`/map-runtime-package`、`/config`、`/runtime-package` 和 `/map-render-plan` 会在同一选择摘要下切到 `MapRuntimePackage v0.2` 与匹配的 v0.2 RenderPlan bundle。该 selector 不是绕过 gate 的快捷开关，它只消费本地授权记录和已审结构化包，不读取 `.env`、不调用 provider、不使用 review-only 整图候选作为运行时真相。

渲染层建议固定为：

```text
terrain_base
road_band
road_edge
build_slot_platform
objective_foundation
spawn_atmosphere
resource_or_hazard
blocking_prop
non_blocking_decoration
fog_light_weather
runtime_interaction_overlay
```

强语义元素必须由结构化 anchor 渲染。弱语义和装饰元素可以有随机性，但必须受 allowed / forbidden zone 约束。

### 1.5 采纳：地图编译权限分层

外部文档把权限边界说得很清楚，这一点应正式纳入本项目地图编译口径：

```text
玩家编译解法。
系统编译遭遇。
开发者编译关卡。
发布层决定什么能进正式 runtime。
```

对应到地图：

| 权限层 | 可以做什么 | 不可以做什么 |
|---|---|---|
| 玩家侧 | 通过塔、道具、陷阱、研究方向影响某个节点的解法 | 直接自定义路径、塔位、资源点、碰撞或关卡拓扑 |
| 系统侧 | 根据世界状态、战斗结果和进度生成遭遇、奖励、环境 modifier、后续节点候选 | 绕过地图 validator 修改已发布运行时事实 |
| 开发者侧 | 使用 AI 辅助生成地图模板、StylePack、组件、候选关卡和审查证据 | 让未审 AI 图片直接成为玩家默认地图 |
| 发布层 | 把已验证地图包、表现层和证据包晋升为可运行内容 | 把 review-only、negative evidence 或 provider 临时产物晋升 |

因此，MVP 和后续版本都应保持这个口径：普通玩家不直接编译战斗地图，玩家编译的是战术解法和世界内研发结果；地图作为关卡 / 系统内容，由开发者或系统侧在严格门禁下编译。

### 1.6 采纳：地图元素按语义强度分级

外部文档的 A-D 分级适合转化成 worker 约束。当前不新增独立 schema，但后续地图任务必须按下表理解各元素的权威来源：

| 级别 | 例子 | 权威来源 | 渲染策略 |
|---|---|---|---|
| A 强语义 | 路径、出生点、目标、塔位、资源点、机关区、防守锚点、阻挡区 | `MapRuntimePackage` / v0.2 preview | 必须由结构化坐标、anchor 或 zone 派生，不能从图片反推 |
| B 弱语义 | 路边护栏、塔位周边碎石、资源点附属物、机关旁提示物 | `MapRuntimePackage` anchor + `MapStylePack` prefab | 可随机，但必须受 allowed / forbidden zone 约束 |
| C 装饰 | 远景、墙裂、地面污渍、非阻挡杂物 | `MapStylePack` / renderer seed | 可更自由，但不能像道路、塔位、资源或阻挡物 |
| D 氛围 | 雾、雨雪、火花、光照、天气粒子 | `MapStylePack.atmosphere_layers` | 只能增强气质，不能遮挡路径、塔位、目标和操作提示 |

这条分级比“是否由 AI 生成”更重要。AI 可以参与 B/C/D 的组件生成，也可以为 A 类提供表现素材，但 A 类位置和玩法语义必须始终来自结构化地图事实。

## 2. 不照搬的部分

### 2.1 不新增完整 LevelBundle 体系

外部方案提出 `LevelBundle` 包含 encounter、wave、enemy、reward、environment rules 等大量内容。该概念方向正确，但当前不应替代已有包体系。

本项目当前边界是：

```text
MapRuntimePackage = 战斗地图运行时事实
RuntimePackage = 可玩对象 / 战斗上下文运行时包
WorldStateDeltaTransaction = 世界状态变化事实
Generation Scheduler ledger = 后台生成与审查证据链
```

因此，`LevelBundle` 暂时只作为未来聚合概念，不作为 v0.1 字段事实源。若后续需要完整关卡包，应由现有包组合生成，而不是推翻当前 schema。

### 2.2 不立刻拆分十几个新 schema

外部方案建议一次定义 `PathGraph`、`SplinePath`、`PlacementMap`、`ResourceNodeMap`、`DefenseAnchorMap`、`HazardZoneMap`、`CollisionMap`、`DecorationZoneMap`、`StylePack`、`LevelBundle` 等 schema。

本项目不应一次性铺这么宽。更稳妥的顺序是：

1. `MapStylePack v0.1`
2. `ProceduralMapRenderPlan v0.1`
3. `SemanticVisualConsistencyReport v0.1`
4. `MapRuntimePackage v0.2` 扩展资源点 / 机关 / 碰撞 / spline hints
5. 需要时再引入完整 LevelBundle 聚合层

### 2.3 不把 spline 作为立即强制重构

Spline 思路正确。怪物中心线和道路视觉同源，是解决“路径视觉与怪物移动不一致”的好办法。

但当前 `MapRuntimePackage.path_routes` 是离散 waypoints / grid 结构，前端已经能稳定消费。近期不应大规模重构为纯 spline；更好的第一步是：

```text
path_routes.waypoints
  -> sampled centerline
  -> road band / road shoulder / direction cue
```

后续 `MapRuntimePackage v0.2` 可以增加 spline hints，但必须保持对当前 waypoints 的兼容。

### 2.4 不把 AI 整图完全废弃

AI 整图不能作为运行时地图，但仍可用于：

- 概念图。
- 风格参考。
- 封面 / 章节卡。
- StylePack 提炼参考。
- 负样本审查和 prompt repair 证据。

当前已生成的失败地图候选仍有价值：它们证明了为什么 promotion gate 必须阻断整图进入玩家 runtime。

## 3. 对当前项目的影响

### 3.1 地图编译主线改写

后续地图任务不再以“继续调 prompt 生成完整地图”为默认方向。

新的主线是：

```text
MapRuntimePackage
  -> StylePack / component assets
  -> MapComponentMediaManifest
  -> MapComponentGenerationRequestPack
  -> MapComponentArtifactStagingManifest
  -> MapComponentCandidateReviewReport
  -> MapComponentVisualQualityReport
  -> MapComponentPromotionGateReport
  -> MapComponentManifestPatchPlan
  -> MapComponentManifestApplyReport
  -> deterministic procedural render
  -> semantic visual consistency check
  -> published visual layer or runtime canvas style update
```

AI 介入点是：

```text
worldbook + node state + visual identity
  -> StylePack proposal
  -> component prompt pack
  -> component image/video generation
  -> media postprocess
  -> MapComponentGenerationRequestPack
  -> MapComponentArtifactStagingManifest
  -> MapComponentCandidateReviewReport
  -> MapComponentVisualQualityReport
  -> MapComponentPromotionGateReport
  -> MapComponentManifestPatchPlan
  -> MapComponentManifestApplyReport / reviewed component manifest artifact
  -> MapStyleComponentBindingReport
  -> procedural renderer consumes reviewed components
```

在该链路中，`MapStyleComponentBindingReport` 只是审查和 evidence gate。Procedural renderer 可以读取其解析过的表现层引用，但路线、塔位、目标、资源、机关和阻挡区域仍只能来自 `MapRuntimePackage` / `MapRuntimePackage v0.2 preview` 的结构化字段。

`MapComponentMediaManifest` 同样只是表现层组件媒体事实：它证明本地组件文件、尺寸、sha 和 style/node 归属，不证明地图玩法事实。当前 deterministic SVG baseline 会先进入 generation request pack，再进入 artifact staging 的 36 个 awaiting slot；candidate review 会读取该 staging manifest，但因为 `imported_count=0`，仍只保留 baseline fixture evidence；visual quality report 因无 generated candidate 保持 `awaiting_generated_candidates`，promotion gate 会显式读取该 visual report 并继续阻断晋升，manifest patch plan 则保持 `no_allowed_candidates` / `patch_count=0`，默认 manifest apply report 也保持 `no_approved_patches` / `applied_patch_count=0`。approval tools 只能基于 alternate imported reports 派生 candidate-approved / visual-approved alternate evidence，让 promotion gate 证明受控链路可出现 `promotion_allowed_count > 0`，并让 patch plan 为 SVG candidate 形成 review-only `ready_for_developer_apply` proposal；developer approval plan 再决定是否生成 replacement manifest artifact。默认 demo / 正式 examples 仍保持 0 imported / 0 promoted / 0 patch / 0 applied，且 apply report 不复制文件、不改正式 manifest、不改 StylePack / RenderPlan / frontend default / runtime map truth。即使 manifest URL 可解析，前端默认 runtime 是否消费这些组件也必须由后续明确发布 / 前端合同任务决定。

### 3.2 前端视觉路线确认

当前 `FrontendProceduralBattleBackdrop v0.4` 方向正确，应继续打磨，而不是回退到整图贴图。

短期前端任务应优先：

- 把道路、塔位、目标、出生点、装饰和氛围进一步组件化。
- 让节点差异来自 StylePack / seed / map package，而不是整图背景。
- 保持全屏战场和 HUD safe area fit。
- 保持拖拽部署和 runtime route 绑定。

### 3.3 地图 AI 管线调整

当前 `generate_controlled_map_candidates.py` 的 text-fallback 结果已证明“纯文本整图生成”不可靠。后续可以保留该工具作为负样本 / 概念图入口，但不应继续把它当成发布底图路线。

后续更有价值的是：

- 生成 StylePack JSON 候选。
- 生成道路/塔位/目标/资源/机关组件。
- 生成地表 tile / decal / prop atlas。
- 用视觉模型审查 preview 是否像游戏地图、是否误导玩家。

### 3.4 Validator 职责拆分

外部文档列出的 validator 名称可以采纳为任务拆分语言，但当前字段事实仍以已有工具为准：

| 外部 validator | 本项目当前落点 | 后续用途 |
|---|---|---|
| ReachabilityValidator | `validate_map_runtime_package.py` / `map_runtime_package_v02.py` 的路线和目标检查 | 后续加入多路线长度、断路、卡死风险和通路压力指标 |
| PlacementValidator | `build_slots` 与 collision / road overlap 检查 | 后续加入道路距离、塔位间距、转角收益和占位 footprint 检查 |
| ResourceValidator | v0.2 `resource_nodes` 与 semantic visual report | 后续接奖励经济、保护目标和交互半径 |
| HazardValidator | v0.2 `hazard_zones` 与 semantic visual report | 后续接触发频率、必败风险和视觉范围一致性 |
| CollisionValidator | v0.2 `blocked_areas` 与前端静态视觉合约 | 后续接 blocking prop / collision 同步检查 |
| SemanticVisualConsistencyValidator | `validate_semantic_visual_consistency_report.py` | 继续作为强语义可视化覆盖和 debug/player 边界门禁 |
| StyleConsistencyValidator | `validate_map_style_pack.py` + 后续视觉模型审查 | 后续检查同一 StylePack 下道路、平台、资源和氛围是否统一 |

这意味着 validator 不是一个单独大脚本，而是贯穿 `MapRuntimePackage`、`MapStylePack`、`ProceduralMapRenderPlan`、preview report、前端视觉合约和 promotion gate 的多层门禁。

## 4. 推荐执行顺序

### P1-MAP-A：冻结本文档并更新事实源索引

目标：

```text
确认地图编译不再以 AI 整图生成为主线。
把 StylePack + 程序化渲染作为后续地图路线。
```

### P1-MAP-B：MapStylePack v0.1

产物：

```text
shared/schemas/map_style_pack.v0.1.schema.json
tools/asset_graph/validate_map_style_pack.py
examples/map_style_packs/long_night_ruined_outpost.map_style_pack.json
```

边界：

- 不调用 provider。
- 不生成图片。
- 不改前端。
- 只定义表现层风格合同。

### P1-MAP-C：ProceduralMapRenderPlan v0.1

产物：

```text
shared/schemas/procedural_map_render_plan.v0.1.schema.json
tools/asset_graph/build_procedural_map_render_plan.py
examples/map_render_plans/*.json
```

目标：

```text
把 MapRuntimePackage + MapStylePack 编译成分层渲染计划。
```

该计划可供前端 canvas 或离线 preview renderer 消费。

### P1-MAP-D：SemanticVisualConsistencyReport v0.1

先做确定性检查：

- 每条 route 都有 road band。
- 每个 build_slot 都有 platform layer。
- 非 build slot 不生成 platform。
- objective / spawn 有对应 visual marker。
- 装饰不覆盖强语义元素。
- debug/control/reference 图没有进入 player default layer。

后续再接入视觉模型或截图审查。

### P1-MAP-E：组件级 AI 生成与后处理

用 AI 生成：

- road texture / edge decal。
- platform sprite。
- objective / spawn marker。
- resource / hazard / prop。
- fog / lighting overlay。

这些组件进入 media staging / promotion / atlas，不直接决定地图语义。

## 5. 硬约束

后续地图编译相关 worker 必须遵守：

```text
1. MapRuntimePackage 是运行时地图事实源。
2. MapCompilePackage 是编译证据源，不是前端运行时事实源。
3. 图片、概念图、整图候选、control sketch、reference board 不能反向决定路径、塔位、资源点、机关或碰撞。
4. AI 整图不能直接成为玩家默认战斗地图。
5. StylePack 只控制表现层，不控制 gameplay truth。
6. 程序化渲染必须从结构化 map package 派生强语义元素。
7. 进入玩家默认视图的视觉层必须通过 quality gate、semantic visual gate 和 promotion gate。
8. 失败整图候选必须作为 review-only / negative evidence 保留，不能静默删除或误发布。
9. 玩家侧不能直接编译战斗地图拓扑；玩家输入只能影响战术解法、研发对象或受控世界状态。
10. 地图元素必须按强语义、弱语义、装饰和氛围分级处理；强语义位置不得由视觉图像反推。
```

## 6. 审查结论

外部设计文档最有价值的判断是：

```text
AI 负责风格和组件，程序负责结构和对齐，Validator 负责可信。
```

本项目采纳这个判断，但不照搬其完整 schema 和 LevelBundle 拆分。当前最稳的工程路线是：

```text
保留 MapRuntimePackage / MapCompilePackage
  -> 新增 MapStylePack
  -> 新增 ProceduralMapRenderPlan
  -> 新增 SemanticVisualConsistencyReport
  -> v0.2 preview 已扩展资源点、机关、防守锚点和阻挡区
  -> 后续再评估 spline hints / LevelBundle 聚合
```

这条路线能吸收 AI 创造力，同时避免地图运行时语义被图像模型污染。

## 7. v0.1 实现落点

截至 2026-07-04，本文的 P1-MAP-B/C/D 已落地第一条最小链路：

```text
MapRuntimePackage
  + MapStylePack
  -> ProceduralMapRenderPlan
  -> SemanticVisualConsistencyReport
```

已新增：

- `shared/schemas/map_style_pack.v0.1.schema.json`
- `shared/schemas/procedural_map_render_plan.v0.1.schema.json`
- `shared/schemas/semantic_visual_consistency_report.v0.1.schema.json`
- `tools/asset_graph/build_procedural_map_render_plan.py`
- `tools/asset_graph/validate_map_style_pack.py`
- `tools/asset_graph/validate_procedural_map_render_plan.py`
- `tools/asset_graph/validate_semantic_visual_consistency_report.py`

当前实现仍不生成图片、不调用 provider，也不让整图候选替换前端默认战场。前端已经开始消费这条分层合同：路径、塔位、目标和出生点来自 `MapRuntimePackage`；材质、平台、氛围和可读性约束来自 `MapStylePack`；道路宽度、路肩宽度和部署基座 footprint 等表现层几何参数来自 `ProceduralMapRenderPlan`；`SemanticVisualConsistencyReport` 负责阻断 debug/reference 层进入玩家默认视图。

同时已新增离线 SVG 预览入口：`tools/asset_graph/render_procedural_map_preview.py` 会用同一组输入生成 review-only 预览图和 `procedural_map_preview_report.v0.1`。该预览只证明 RenderPlan 可执行和可审查，不是 published visual layer，也不是玩家 runtime 背景。

## 8. v0.2 强语义 preview 落点

截至 2026-07-04，地图运行包已经新增旁路 v0.2 preview：

```text
MapRuntimePackage v0.1
  -> MapRuntimePackage v0.2 preview
  -> resource_nodes / hazard_zones / defense_anchors / blocked_areas
```

已新增：

- `shared/schemas/map_runtime_package.v0.2.schema.json`
- `tools/asset_graph/map_runtime_package_v02.py`
- `tools/asset_graph/build_map_runtime_package_v02.py`
- `tools/asset_graph/validate_map_runtime_package_v02.py`
- `examples/map_runtime_packages_v02/*.map_runtime_package_v02.json`

v0.2 preview 解决的是：地图中“可被保护或采集的资源点”“影响路线或局部战斗节奏的机关区”“推荐防守锚点”“不可建造 / 不可装饰阻挡区”不再只依赖视觉暗示，而成为结构化玩法语义。

该 preview 仍不替换现有前端 / 后端默认 v0.1 地图包。当前玩家侧正式路径继续消费 `examples/map_runtime_packages/*.map_runtime_package.json`；v0.2 包放在 `examples/map_runtime_packages_v02/`，用于下一阶段 renderer、前端和世界状态编译逐步接入。

硬边界：

- 图片、StylePack 和 RenderPlan 只能表现 v0.2 的资源点、机关区、防守锚点和阻挡区，不能反向决定它们。
- v0.2 preview 不能自动发布视觉层，不能自动替换 `MapRuntimePackage v0.1`。
- 只有当前端、后端服务和 semantic visual gate 明确升级后，v0.2 才能进入玩家默认 runtime。

## 9. v0.2 RenderPlan 语义预览落点

截至 2026-07-04，`MapRuntimePackage v0.2 preview` 的强语义已经接入旁路 RenderPlan / preview evidence：

```text
MapRuntimePackage v0.2 preview
  + MapStylePack
  -> ProceduralMapRenderPlan v0.1
  -> SemanticVisualConsistencyReport v0.1
  -> ProceduralMapPreviewReport v0.1 / review-only SVG
```

已新增：

- `examples/map_render_plans_v02/*.procedural_map_render_plan.json`
- `examples/semantic_visual_consistency_reports_v02/*.semantic_visual_consistency_report.json`
- `examples/map_render_previews_v02/*.procedural_map_preview.svg`
- `examples/map_render_previews_v02/*.procedural_map_preview_report.json`

`ProceduralMapRenderPlan v0.1` 现在允许以下 v0.2 强语义 operation：

```text
resource_node
hazard_zone
defense_anchor
blocked_area
```

对应层仍是已有表现层：

```text
resource_or_hazard
blocking_prop
```

这不是正式 runtime 升级。当前输出只用于审查和证据：

- `resource_nodes`、`hazard_zones`、`defense_anchors`、`blocked_areas` 必须来自 `MapRuntimePackage v0.2 preview`。
- `MapStylePack` 只提供 procedural prefab / palette，不决定语义位置。
- `render_procedural_map_preview.py` 只输出 review-only SVG；不得作为 published visual layer 或玩家 runtime 背景。
- `tools/demo/export_evidence.py` 会把 `examples/map_render_previews_v02/*.procedural_map_preview_report.json` 汇总到 `procedural_map_previews_v02`，用于评审证明强地图语义可被 deterministic renderer 消费。

## 10. 外部 v0.3 执行建议复审

2026-07-05 复审的外部 v0.3 文档进一步强调：

```text
logic-first
semantic-first
spline-based path
stylepack-driven rendering
validator-gated export
```

该方向继续采纳，但执行方式必须按本项目现有事实源改写。

### 10.1 继续采纳的部分

- 路线和道路视觉必须同源。当前可先由 `path_routes.waypoints` 采样生成 centerline / road band；后续再补 spline hints，而不是立即重构掉 waypoints。
- 塔位、资源点、机关区、防守锚点和阻挡区必须来自结构化地图包；图片和 preview 只能表现这些事实，不能反向识别或覆盖这些事实。
- StylePack 应成为地图视觉一致性的主要入口：道路、路肩、平台、资源点、机关、阻挡物、装饰和氛围都应从 StylePack / component atlas 中取表现素材。
- Validator 名称可以作为任务语言保留：Reachability、Placement、Resource、Hazard、Collision、SemanticVisualConsistency、StyleConsistency。但字段事实仍以现有 schema 和 tools 为准。
- 推荐路径模板可以作为开发者侧生成种子保留，例如单路 S 曲线、双路汇合、长折线路、短压迫路、中央环路；这些是 map template candidate，不是玩家自由输入。

### 10.2 不直接采纳的部分

外部 v0.3 中的以下建议不能直接派发给 worker：

- 不新建独立 `PathGraph.schema.json`、`SplinePath.schema.json`、`PlacementMap.schema.json`、`ResourceNodeMap.schema.json`、`HazardZoneMap.schema.json`、`CollisionMap.schema.json`、`DecorationZoneMap.schema.json` 和 `LevelBundle.schema.json` 作为并列事实源。
- 不把 `PathGraph / PlacementMap / ResourceNodeMap / HazardZoneMap` 作为新运行时合同替换 `MapRuntimePackage`。
- 不把 `LevelBundle` 作为当前 v0.1 / v0.2 的强制产物；它最多是未来聚合层，应由现有包组合导出。
- 不把 spline 作为近期强制迁移目标。近期应先在现有 waypoints 上派生 smooth centerline、road band 和塔位距离检查。
- 不把 preview.png / SVG / AI map candidate 视为 published visual layer。它们仍是 review-only evidence，必须经过 promotion gate。

### 10.3 下一步地图任务应这样拆

后续地图相关 worker 应优先补现有链路，而不是从零铺新体系：

```text
MapRuntimePackage v0.1 / v0.2 preview
  -> path sampling / road band geometry
  -> slot distance and footprint validation
  -> StylePack component slots
  -> ProceduralMapRenderPlan
  -> SemanticVisualConsistencyReport
  -> review-only preview / evidence
  -> explicit activation gate
```

建议任务顺序：

1. `P1-MAP-F path geometry helper`
   - 在不改 schema 的前提下，从现有 `path_routes.waypoints` 派生 sampled centerline、route length、turn tags、road band envelope。
   - 供 RenderPlan、塔位评分和 validator 使用。
2. `P1-MAP-G placement validation upgrade`
   - 检查 build slot 与 road band、blocked areas、resource nodes、objective、spawn 的距离和重叠。
   - 给塔位补 near_turn / near_choke / good_for_aoe 这类审查标签，但不改变 runtime 发布路径。
3. `P1-MAP-H map component style slots`
   - 扩展 StylePack 的 component 引用粒度，让道路边缘、平台、资源点、机关、阻挡物和氛围可以接 reviewed media atlas。
   - AI 生成的是 component candidate，不是整图 runtime。
4. `P1-MAP-I procedural battle backdrop polish`
   - 前端继续使用 `MapRuntimePackage` 的强语义与 `map_render_plan_bundle` 的表现层参数，打磨全屏战场、自然道路、塔位平台和地形边界。
   - 不允许默认回退到 battle control sketch、reference board 或失败整图候选。

### 10.4 Worker 派发硬约束补充

地图任务包必须附带以下补充约束：

```text
1. 不新增与 MapRuntimePackage 并列竞争的运行时地图事实源。
2. 不从图片、SVG、preview 或 AI candidate 中反推路线、塔位、资源点、机关、碰撞。
3. 新增 helper / validator 可以读取现有 map package，但不得静默修改 default runtime package。
4. 所有 preview / generated media 默认 review-only，进入玩家默认视图必须有 promotion / activation evidence。
5. 玩家侧仍不直接编译战斗地图拓扑；地图模板和关卡池属于开发者侧或系统侧受控编译。
```

### 10.5 P1-MAP-F/G 最小实现落点

截至 2026-07-05，P1-MAP-F/G 已落地第一条最小可验证闭环：

```text
MapRuntimePackage v0.1 / v0.2 preview
  -> path_routes.waypoints
  -> deterministic path geometry helper
  -> builder-side road band avoidance
  -> placement validator / review-only MapPathGeometryReport
```

已新增：

- `tools/asset_graph/map_path_geometry.py`
- `tools/asset_graph/build_map_path_geometry_report.py`
- `tools/asset_graph/validate_map_path_geometry_report.py`
- `shared/schemas/map_path_geometry_report.v0.1.schema.json`
- `examples/review_packs/map_path_geometry_report.v0.1.json`

该实现只从现有 `MapRuntimePackage` 的 `path_routes.waypoints` 派生 sampled centerline、route length、turn angle / near_turn hints、road band envelope 和塔位到 road band 的距离统计。它是 builder / validator / evidence 的支撑模块，不是新的运行时地图事实源，不从表现层反推地图语义，也不替换 v0.1 玩家默认 runtime 包。

当前 placement 升级采用源头避让加非破坏性审查策略：

- v0.1 / v0.2 builder 在自动派生 `build_slots` 时，使用从 `path_routes.waypoints` 派生的连续 footprint-to-road-band 距离过滤候选，避免只避开离散 path cells。
- v0.1 / v0.2 validator 会输出 `placement_geometry_warnings`，但不会因派生 road band warning 改变已有 valid fixture 的 exit code。
- 旧信号塔压力地图的历史塔位重叠 fixture 已由 builder 源头修复并重建 v0.1 / v0.2 runtime、RenderPlan、semantic report 和 review-only preview；`MapPathGeometryReport` 当前为 `passed` 且 warning 为 0。
- v0.2 的 resource / blocked / objective / spawn 与塔位、road band 的冲突同样通过 helper 进入 warning/report；后续如果模板和示例完成迁移，可再把明确重叠升级为硬失败。

硬边界保持不变：不得从图片、SVG、preview 或 AI candidate 反推路线、塔位、资源点、机关或碰撞；StylePack / RenderPlan 仍只表现结构化地图事实。

### 10.6 v0.2 激活前合同计划落点

截至 2026-07-05，地图 runtime v0.2 已补齐激活前合同计划层：

```text
MapRuntimePackage v0.2 preview
  -> promotion readiness
  -> developer authorization record
  -> opt-in dry-run contract
  -> activation gate
  -> activation contract plan
```

已新增：

- `tools/media/build_map_runtime_v02_activation_contract_plan.py`
- `tools/media/validate_map_runtime_v02_activation_contract_plan.py`
- `examples/review_packs/map_runtime_v02_activation_contract_plan.v0.1.json`

该层的职责不是激活 v0.2，而是把 activation gate 中仍阻断的显式授权、候选隔离和激活后 evidence 复跑，展开为可机器校验的计划；同时记录后端 selector 与前端消费合同是否已具备预接入条件：

- 后端必须把 v0.2 选择限制在 developer-approved selector 之后，不能因为 v0.2 preview 存在就自动替换 `/map-runtime-package`。当前 selector 已预接入为 `pre_activation_ready`：默认 pending 授权仍保持 v0.1，临时 approved 授权夹具可证明 v0.2 包与对应 RenderPlan bundle 会一致被选中。
- 前端必须只从 activated default runtime 消费资源点、机关区、防守锚点和阻挡区；review-only preview / opt-in endpoint 仍不能成为玩家默认依赖。当前前端强语义消费和默认 fetch 隔离已预接入为 `pre_activation_ready`，但激活后仍必须复跑前端静态合同与浏览器证据。
- 激活后必须重新跑 v0.2 preview API、MVP 主流程 API、前端静态视觉合同、浏览器玩家链路和 demo evidence suite。

当前计划报告保持：

```text
contract_plan_status = not_applied
activation_allowed_count = 0
activation_apply_now_count = 0
frontend_contract_status = pre_activation_ready
backend_selector_contract_status = pre_activation_ready
backend_not_applied_change_count = 0
default_runtime_mutation_performed = false
backend_api_contract_mutation_performed = false
frontend_contract_mutation_performed = false
```

这说明 v0.2 强语义已经是“可读候选”，后端 selector 和前端消费也已预接入，但它还不是“默认玩家 runtime”。后续真正激活时，仍必须另开独立任务，提交显式开发者授权，并以该计划为 checklist 复跑后端、前端和证据链。

### 10.7 v0.2 强语义几何一致性 report 落点

截至 2026-07-05，`MapRuntimePackage v0.2 preview` 已补齐 review-only 强语义几何证据：

```text
MapRuntimePackage v0.2 preview
  -> resource_nodes / hazard_zones / defense_anchors / blocked_areas
  -> deterministic path geometry helper
  -> MapRuntimeV02SemanticGeometryReport
  -> demo evidence summary
```

已新增：

- `shared/schemas/map_runtime_v02_semantic_geometry_report.v0.1.schema.json`
- `tools/asset_graph/build_map_runtime_v02_semantic_geometry_report.py`
- `tools/asset_graph/validate_map_runtime_v02_semantic_geometry_report.py`
- `examples/review_packs/map_runtime_v02_semantic_geometry_report.v0.1.json`

该报告只读取 `examples/map_runtime_packages_v02/*.json`，先按 `map_runtime_package.v0.2` 校验输入，再复用 `map_path_geometry.py` 的连续路线 / road band 距离逻辑检查强语义几何：

- `resource_nodes`：检查 footprint 是否在 grid 内，是否与 path road band、build slot、objective、spawn 或 blocked area 冲突；`interactable=true` 时记录 `interactable_area_status`。
- `hazard_zones`：检查 anchor route id、`path_t_range` 和 `affected_area`；`road_band` 会记录绑定 route 与 t span。
- `defense_anchors`：检查 related route id、grid 内位置和到相关 route 的最近距离。
- `blocked_areas`：检查 cells 是否在 grid 内，是否与 path / build / resource / objective / spawn 冲突。

报告状态为 `passed` / `passed_with_warnings` / `blocked`，并在 summary 中记录 warning / error counts。当前正式 report 为 `passed_with_warnings`：旧信号塔 v0.2 preview 的 `resource_old_signal_tower_primary` 贴近派生 road band，但没有 blocking resource / 阻挡区 / 塔位 / 目标 / 出生点硬冲突。该 warning 只作为 review evidence，不修改 v0.2 runtime package，也不影响默认 v0.1 玩家 runtime。

安全边界保持显式字段：`runtime_effect=false`、`provider_call_count=0`、`default_runtime_mutation=false`，并声明不读 `.env`、不调用 provider、不读图片、不从 SVG / preview / AI candidate 反推语义。它不是新的 `PathGraph`、`CollisionMap`、`ResourceNodeMap` 或 `LevelBundle` 事实源，只是对现有 `MapRuntimePackage v0.2 preview` 的结构化证据层。

`tools/demo/build_mvp_demo_readiness_report.py` 已把该报告作为 `map_runtime_v02_semantic_geometry` 必需 gate 纳入 MVP demo readiness：当前 gate 为 `passed_with_warnings`，只证明 v0.2 preview 的强语义几何候选足够进入演示证据链，不代表 v0.2 已成为玩家默认 runtime。默认 runtime 切换仍必须经过 activation authorization、activation gate、developer-approved selector 约束、前端合同和激活后 evidence 复跑。
