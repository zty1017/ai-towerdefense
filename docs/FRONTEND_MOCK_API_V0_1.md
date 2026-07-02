# 前端 Mock API v0.1

本文档记录 MVP 前端 mock 接口。它服务于当前比赛演示链路：

```text
本地档案 / 世界实例配置
-> 预制开场
-> 大地图
-> 第一个危机节点
-> 现场试作
-> 战斗中样品送达
-> 战后结算 / 世界状态变化
-> 简单证据展示
```

## 边界

- 接口不调用 LLM。
- 接口不调用图片、视频或音频 provider。
- 接口不读取 `.env`。
- 前端看到的是统一后端 API，不需要直接读仓库 JSON 文件。
- 战斗运行时 mock 美术包是开发者预编译结果，不是玩家侧现场编译结果。
- 当前动效资源已经接入 `MediaAtlasManifest v0.1` 的 `spritesheet` 模式：种子图已经生成，processed PNG 已派生为确定性多帧 atlas frame sequence，并打包为实体 spritesheet PNG；真实图生视频关键帧后续再替换。
- 塔防战斗地图优先消费 `MapRuntimePackage v0.1`。`battle_config` 仍保留为旧兼容和调试输入，但前端不应从地图图片反推路径、塔位、碰撞或目标。

## 静态媒体

后端启动时会挂载：

```text
/assets/frontend_mock/processed
/assets/frontend_mock/generated
/assets/frontend_mock/atlas_frames
/assets/frontend_mock/atlas_sheets
/assets/frontend_runtime_mock/processed
/assets/frontend_runtime_mock/generated
/assets/frontend_runtime_mock/atlas_frames
/assets/frontend_runtime_mock/atlas_sheets
```

`processed` 是前端默认使用的透明 PNG。  
`generated` 是后续图生视频 / 动画卡管线的种子图来源。
`atlas_frames` 是当前多帧 atlas 的独立 PNG frame sequence。
`atlas_sheets` 是由 frame sequence 打包出的实体 spritesheet PNG，战斗运行时优先裁剪使用。

`frontend_runtime_mock` 覆盖战斗画面需要的敌人、保护目标、基础防御件、NPC 头像、地图 token 和程序化特效；它服务前端 mock 运行，不污染玩家侧叙事。

## 通用返回壳

新增接口统一返回：

```json
{
  "session_id": "...",
  "mode": "frontend_mock_fixture",
  "payload": {}
}
```

`mode` 表示当前走稳定 mock fixture，不代表实时生成。

## 接口清单

### 创建世界实例

```http
POST /api/sessions/{session_id}/world-instance
```

请求体可选：

```json
{
  "selected_options": {
    "creativity_mode": "stable",
    "player_origin": "lampwright_apprentice",
    "visual_style_id": "lantern_wasteland_pseudo3d"
  }
}
```

返回：

- `world_instance`
- `run_world_state`

并写入：

- `world_instance`
- `campaign_state`

### 获取前端总包

```http
GET /api/sessions/{session_id}/frontend-mock-pack
```

返回：

- `pack`: `examples/frontend_mock/frontend_mock_pack.v0.1.json`
- `ai_compile_core_artifacts`: `ContextPackage / FactEntry / CGOP / WorldStateDeltaTransaction` 字段级示例与引用
- `media_manifest`: processed 媒体清单
- `animation_seed_manifest`: 图生视频种子图清单
- `media_atlas_manifest`: 前端编译资产 atlas 清单，当前为 `spritesheet` 多帧 frame sequence + 实体 spritesheet
- `animation_pipeline_status`
- `runtime_art_kit`: 开发者预编译战斗运行时美术包
- `runtime_art_media_manifest`: processed 运行时美术媒体清单
- `runtime_art_animation_seed_manifest`: 图生视频种子图清单
- `runtime_art_atlas_manifest`: 战斗运行时美术 atlas 清单，当前为 `spritesheet` 多帧 frame sequence + 实体 spritesheet
- `runtime_art_pipeline_status`

`ai_compile_core_artifacts` 是 Studio / evidence 辅助数据，不是玩家默认界面文案。它用于证明前端 mock 包已经开始对齐统一 AI 编译对象模型；实际玩家流程仍读取 `pack`、runtime package、地图包和媒体清单。其中 `world_delta_transaction` 只解释世界状态提交语义，不替代 `WorldStateDelta.operations[]`。

### 获取开场

```http
GET /api/sessions/{session_id}/opening
```

返回预制开场内容。

### 获取动画种子

```http
GET /api/sessions/{session_id}/animation-seeds
```

返回 `frontend_animation_seed_manifest.v0.1.json`。当前状态：

```text
seed_images_ready_video_frames_not_generated
```

含义是：可以用种子图做前端临时 tween / shader / visual recipe 动效，但还没有真正的视频帧序列。

### 获取战斗运行时美术包

```http
GET /api/sessions/{session_id}/runtime-art-kit
```

返回：

- `runtime_art_kit`
- `runtime_art_media_manifest`
- `runtime_art_animation_seed_manifest`
- `runtime_art_atlas_manifest`
- `runtime_art_pipeline_status`

当前状态：

```text
developer_compiled_multiframe_atlas_ready_video_keyframes_not_generated
```

含义是：敌人、目标物、基础防御件和 NPC 头像已经有 processed PNG，并且 sprite 类资产已经进入多帧 atlas；地图 token 与攻击 / 命中 / 减速 / 死亡 / 漏怪反馈通过程序化 recipe 表示；真实图生视频关键帧和实体 atlas PNG 后续再补。

### 获取调度缓冲证据

```http
GET /api/sessions/{session_id}/generation-schedule
```

返回：

- `generation_schedule.refs`: 当前调度计划包与 dry-run 执行报告路径。
- `generation_schedule.buffer`: 面向 session 的紧凑调度缓冲摘要。
- `generation_schedule.plan`: `GenerationSchedulePlan v0.1` fixture。
- `generation_schedule.run_report`: `GenerationScheduleRunReport v0.1` fixture。

当前该接口只暴露 fixture-backed / review-only 调度事实，不会启动后台 worker，不会调用外部模型，不会修改世界状态。它用于证明以下事情已经进入后端 API 面：

- `sync_blocking` 内容在会话关键路径可立即复用。
- `background_prefetch`、`background`、`lazy` 内容只进入候选调度，不阻塞玩家体验。
- `fallback_static` 内容已经准备好，生成失败时可保持 MVP 主链路可玩。
- 预生成结果启用前必须重新经过对应 validator、semantic gate 或 media gate。

`generation_schedule.buffer` 当前包含：

- `status`
- `control_plane_mode`
- `latency_class_counts`
- `ready_reused_count`
- `fallback_selected_count`
- `scheduled_count`
- `provider_call_count`
- `world_mutation_count`
- `activation_requires_revalidation`
- `items`

其中 `provider_call_count` 和 `world_mutation_count` 在 MVP mock 模式下都必须为 `0`。这说明接口只是 session 可见的调度缓冲和演示证据，不是 live provider 执行器。

### 获取大地图

```http
GET /api/sessions/{session_id}/map
```

返回：

- `map`
- 当前 session 的 `run_world_state`

战后再次调用会看到更新后的世界状态。

### 获取节点简报

```http
GET /api/sessions/{session_id}/nodes/{node_id}/briefing
```

当前首战支持：

```text
gray_lantern_station
```

返回：

- 节点 briefing
- 当前材料
- 当前 NPC
- 建议玩家输入示例

### 获取战斗配置

```http
GET /api/sessions/{session_id}/battles/{node_id}/config
```

返回：

- battle config
- map runtime package
- bottom toolbar assets
- sample delivery asset
- media manifest
- animation seed manifest
- media atlas manifest
- runtime art kit
- runtime art media manifest
- runtime art atlas manifest

前端可用该接口构建战斗页面。

其中 `map_runtime_package` 是新的运行时地图真值入口，包含：

- `grid`
- `path_routes`
- `build_slots`
- `objectives`
- `spawn_points`
- `visual_layers`
- `runtime_hints`

前端应优先用它绘制拖拽部署、路径预览、目标标记和视觉底图引用；`battle_config.paths` 只是旧兼容字段。

### 研发接口内部元数据

研发提案与研发任务响应会额外带有 `compiler_metadata`。它服务 Studio / 演示证据 / 调试，不是玩家默认界面文案。

`compiler_metadata` 当前包含：

- `compiled_object`：可编译对象模型、候选类型、生命周期提示和运行时表面。
- `context_package`：世界书、节点、battle config、MapRuntimePackage 和玩家输入来源。
- `core_artifact_refs`：对应 `ContextPackage v0.1`、`FactEntry v0.1`、`CompiledGameObjectPackage v0.1`、`WorldStateDeltaTransaction v0.1` 示例或本次运行产物引用。
- `validation`：本地门禁、运行状态和 gate status。
- `runtime_refs`：runtime package、delivery payload 和 trace 数量。

边界：

- 玩家侧 UI 可以忽略该字段。
- 不包含 API key、secret、原始提示词、外部 provider 原始响应或完整 trace。
- 技术错误仍进入内部记录，玩家侧只显示世界内状态。
- 旧 `compiler_metadata.v0.1` 保留兼容；新字段只增加引用，不要求前端玩家 UI 展示。

### 获取地图运行包

```http
GET /api/sessions/{session_id}/battles/{node_id}/map-runtime-package
```

返回：

- `map_runtime_package`

当前 MVP 首战节点支持：

```text
gray_lantern_station
```

`MapRuntimePackage v0.1` 的边界：

- 路径、塔位、出生点和目标来自结构化逻辑数据。
- `visual_layers` 只引用本地 `/assets/map_visual_reference/...` 视觉参考层。
- 视觉参考层不是玩法真值，不决定碰撞、伤害、资源、部署或任务条件。
- 后续 AI 生成 painted map 时，也必须重新对齐到同一个 map runtime package。

### 获取 runtime package

```http
GET /api/sessions/{session_id}/battles/{node_id}/runtime-package
```

返回当前节点对应 reviewed runtime package，同时附带当前可用的样品展示资产、媒体清单和战斗运行时美术包。

若该节点已经生成 `MapRuntimePackage v0.1`，响应中也会附带 `map_runtime_package`，便于战斗运行时在同一个请求中拿到资产包与地图包。

### 提交战斗结果

```http
POST /api/sessions/{session_id}/battles/{node_id}/results
```

请求体：

```json
{
  "result": "victory",
  "protected_core_hp": 7,
  "optional_target_state": "damaged",
  "deployed_asset_ids": ["asset_mirror_lure_trap_001"],
  "leaked_enemy_count": 1,
  "notes": "front-end simulated battle result"
}
```

返回：

- settlement
- world delta
- 更新后的 run world state

并写入：

- `battle_results`
- `campaign_state`

### 获取最近结算

```http
GET /api/sessions/{session_id}/settlement/latest
```

返回最近一次战斗结算。若还未提交战斗结果，则 `settlement` 为 `null`。

### 获取演示证据

```http
GET /api/sessions/{session_id}/evidence
```

返回简单 Studio / 录屏证据 payload：

- 最新 proposal
- 最新 research job
- 最新 battle result
- AI 编译核心对象引用
- Generation Scheduler 调度缓冲摘要
- audit summary
- dossier summary

这不是正式后台页面，只是演示证明入口。
