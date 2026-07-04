# 地图编译设计采纳审查 v0.1

Last updated: 2026-07-03

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
| `CollisionMap` | 当前 validator 中的 path/build slot/objective 冲突检查 | 后续补显式 blocked areas，但不能从图片反推。 |
| `ResourceNodeMap` | 尚未进入 MapRuntimePackage | 后续作为 v0.2 或 encounter extension 引入。 |
| `HazardZoneMap` | 尚未进入 MapRuntimePackage | 后续作为 v0.2 或 environment modifier 引入。 |
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
  -> 再逐步扩展资源点、机关、碰撞、spline hints
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
