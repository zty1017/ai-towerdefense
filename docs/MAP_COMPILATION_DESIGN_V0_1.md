# 地图编译设计采纳审查 v0.1

Last updated: 2026-07-05

本文用于审查并项目化采纳外部 AI 给出的地图编译方案。该外部方案的核心建议是：

```text
不要再走 AI 整图生成 / 重绘 -> 反推路线和塔位。
应走逻辑层先行 + StylePack 统一视觉 + 程序化渲染 / 拼装。
```

审查结论：方向采纳，结构改写。

该方案与本项目当前证据一致：多轮 Agnes / text-fallback / topology-constrained 地图整图候选已经证明，图像模型会重构路径、塔位、目标和装饰布局；即使参考图和 overlay 能帮助审查，也不能让整图成为运行时事实源。因此，正式地图编译应从“AI 画一张地图”转为“结构化地图事实 + AI 生成风格和组件 + 程序确定性渲染”。

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

| 外部概念 | 本项目当前映射 | 采纳方式 |
|---|---|---|
| `PathGraph` / `SplinePath` | `MapRuntimePackage.path_routes` | v0.1 仍用结构化 waypoints；后续 v0.2 可增加 sampled spline / road band。 |
| `PlacementMap` | `MapRuntimePackage.build_slots` | 保留为运行时塔位事实源；后续补距离道路、转角、瓶颈标签。 |
| `SpawnPoints` / `BasePoints` | `spawn_points` / `objectives.core_target` | 已存在，继续作为事实源。 |
| `CollisionMap` | `MapRuntimePackage v0.2 preview.blocked_areas` 与当前 validator 冲突检查 | 已旁路表达显式阻挡区，但仍不能从图片反推。 |
| `ResourceNodeMap` | `MapRuntimePackage v0.2 preview.resource_nodes` | 已作为 v0.2 preview 引入，前端默认 runtime 暂不切换。 |
| `HazardZoneMap` | `MapRuntimePackage v0.2 preview.hazard_zones` | 已作为 v0.2 preview 引入，后续再接环境 modifier / 战斗结算。 |
| `DecorationZoneMap` | 当前前端程序化地标 / 边缘装饰 | 后续由 renderer/StylePack 管，不成为玩法事实。 |

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
  -> reviewed component atlas
  -> procedural renderer consumes reviewed components
```

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
