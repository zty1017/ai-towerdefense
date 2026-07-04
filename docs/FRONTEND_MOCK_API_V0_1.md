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
- 后端的媒体 manifest、animation seed、atlas 和 runtime art kit 加载由 `backend/app/services/frontend_media_service.py` 维护。
- 后端的战斗配置和 reviewed runtime package 加载由 `backend/app/services/battle_content_service.py` 维护。
- 塔防战斗地图优先消费 `MapRuntimePackage v0.1`。`battle_config` 仍保留为旧兼容和调试输入，但前端不应从地图图片反推路径、塔位、碰撞或目标。
- 后端的地图运行时包加载由 `backend/app/services/map_runtime_service.py` 维护；`frontend_mock_service.py` 只在战斗配置和 runtime package 聚合响应中附带该包。

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

`ai_compile_core_artifacts` 和 `pack.core_artifacts` 都是 Studio / evidence 辅助数据，不是玩家默认界面文案。它们用于证明前端 mock 包已经开始对齐统一 AI 编译对象模型；实际玩家流程仍读取 `pack.assets`、runtime package、地图包和媒体清单。其中 `world_delta_transaction` 只解释世界状态提交语义，不替代 `WorldStateDelta.operations[]`。后端加载入口是 `backend/app/services/ai_core_artifact_service.py`。Research proposal / job metadata 也通过同一服务生成 ContextPackage、FactEntry、CGOP 原生快照，并继续保留 `core_artifact_refs` 兼容字段。

### 获取开场

```http
GET /api/sessions/{session_id}/opening
```

返回预制开场内容。

### 获取动画种子

```http
GET /api/sessions/{session_id}/animation-seeds
```

返回 `frontend_animation_seed_manifest.v0.1.json`。当前单独动画种子接口状态：

```text
seed_images_ready_video_frames_not_generated
```

含义是：可以用种子图做前端临时 tween / shader / visual recipe 动效，但还没有真正的视频帧序列。

前端总包和战斗配置会同时聚合 `media_atlas_manifest`，因此其中的 `animation_pipeline_status` 为：

```text
multiframe_atlas_ready_video_keyframes_not_generated
```

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

含义是：敌人、目标物、基础防御件和 NPC 头像已经有 processed PNG，并且 sprite 类资产已经进入多帧 atlas；地图 token 与攻击 / 命中 / 减速 / 死亡 / 漏怪反馈通过程序化 recipe 表示；真实图生视频关键帧后续再替换，当前实体 spritesheet PNG 由已发布 processed PNG 确定性派生。

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

响应还会带：

- `latest_generation_schedule_run`: 当前 session 最近一次持久化 dry-run 运行记录；如果尚未执行，则为 `null`。

### 获取战役路由游标

```http
GET /api/sessions/{session_id}/campaign-router
```

返回当前 session 的薄战役游标：

- `campaign_router.current`: 当前应展示 / 游玩的节点。
- `campaign_router.next`: 前视一步节点。
- `campaign_router.lookahead`: 前视窗口，MVP 固定为最多 2 个节点。
- `campaign_router.route`: 当前已审 MVP 路线表。
- `campaign_router.scheduler_signal`: 最近一次调度 dry-run 与队列摘要。
- `campaign_router.boundary`: 明确该接口不调用 provider、不写世界状态。

该接口只仲裁“当前节点 -> 下一节点”和可用资产入口，不生成内容、不提交世界状态。节点内容仍以 battle config、runtime package、MapRuntimePackage 和 `WorldStateDeltaTransaction` 为事实源。

当前 MVP 路线支持：

- `gray_lantern_station`
- `lamp_wick_store`
- `old_signal_tower`

### 请求下一节点预取

```http
POST /api/sessions/{session_id}/campaign-router/prefetch-next
```

该接口会：

- 若当前 session 尚无 scheduler dry-run，则创建一条 fixture-backed dry-run 运行记录。
- 处理一个 queued 调度项，模拟后台预取 worker 的最小闭环。
- 返回 `prefetch_request`、`worker_step`、`generation_schedule_queue` 和更新后的 `campaign_router`。

它仍然不会调用外部模型，不会读取 `.env`，不会创建新内容，也不会写入世界状态。MVP 中它用于证明玩家进入当前节点时，系统已经可以把下一节点的预生成 / fallback 检查挂到同一条运行时链路上。

### 请求下一节点 dispatcher 预取

```http
POST /api/sessions/{session_id}/campaign-router/prefetch-next-dispatcher-drain
```

该接口保留 Campaign Router 的“当前节点 -> 下一节点”语义，但把调度动作升级为 review-only dispatcher drain。默认 `max_items = 2`，用于模拟玩家进入当前节点时，后台预取 tick 可以连续推进多个 queued provider-review 项到 `ProviderAdapterExecutionReceipt` / `ProviderOutputEnvelope` ledger 边界。

请求体可选：

```json
{
  "worker_id": "router-dispatcher-prefetch",
  "note": "lookahead dispatcher prefetch",
  "max_items": 2
}
```

返回：

- `prefetch_request`: 目标下一节点、预取模式、预算、处理数量、停止原因和安全计数。
- `worker_step`: 底层 dispatcher drain 的汇总。
- `dispatcher_steps`: 每个被处理调度项的 receipt / envelope 摘要。
- `generation_schedule_queue`
- `generation_schedule_worker_cache`
- `generation_artifact_ledger`
- 更新后的 `campaign_router`

该接口不按节点定向过滤 scheduler queue；下一节点只是触发上下文，drain 仍按 Generation Scheduler 的 eligible queue 顺序处理。因此它拒绝 `schedule_item_id`、`authorization_ref`、`artifact_profile` 和本地导入路径。它仍然不会调用外部模型，不读取 `.env`，不 staging，不 promotion，不 complete queue item，不写世界状态，不激活 runtime。

### 获取预取缓存视图

```http
GET /api/sessions/{session_id}/generation-schedule/prefetch-cache
```

该接口只读取最近一次 `generation_schedule_run` 的队列项和 `generation_artifact_ledger`，按 `schedule_item_id` 汇总当前预取链路走到哪一步。它不创建 run，不推进 dispatcher，不 staging，不 promotion，不 complete queue item，不调用 provider，不写世界状态，也不激活 runtime。

返回：

- `generation_schedule_run`：最近一次 run 摘要；如果尚未创建 run，则为 `null`。
- `generation_prefetch_cache.summary`：item 数、cache status 计数、历史 ledger 中记录过的 provider 调用数，以及本次 GET 的 provider / world mutation / activation / promotion 安全计数。
- `generation_prefetch_cache.items`：每个调度项的 `queue_status`、`cache_status`、executor request / authorization / receipt / envelope / staging / promotion refs、activation gate 与 promotion gate 摘要。

`provider_call_count_by_this_request` 与 `world_mutation_count_by_this_request` 必须始终为 `0`。如果历史 `ProviderOutputEnvelope` 记录了真实 provider 调用摘要，只能计入 `recorded_provider_call_count`，不能把只读查询伪装成执行器。

### 获取激活门视图

```http
GET /api/sessions/{session_id}/generation-schedule/activation-gate
```

该接口只读 `prefetch-cache` 的派生结果，用于 Studio、演示脚本或调试面板解释后台候选为什么还不能进入玩家 runtime。它不创建 run，不推进 worker，不 staging，不 promotion，不 complete queue item，不调用 provider，不写世界状态，也不激活 runtime。

返回：

- `generation_schedule_run`：最近一次 run 摘要；如果尚未创建 run，则为 `null`。
- `generation_activation_gate.summary`：item 数、activation status 计数、阻断数、非适用数、promotion allowed 数，以及本次 GET 的 provider / world mutation / activation 安全计数。
- `generation_activation_gate.items`：每个调度项的 `cache_status`、`activation_status`、`blocked_reason`、`required_next_gates`、promotion / activation 安全布尔值和 `refs_present`。
- `generation_activation_gate.safety`：明确该接口不读取 `.env`、不调用 provider、不晋升产物、不写世界状态、不激活 runtime。

前端玩家侧不应把该接口作为可玩内容来源；它只是证明：

```text
有预取候选证据
  != 可以加载到玩家 runtime
```

### 获取共享预取缓存索引

```http
GET /api/sessions/{session_id}/generation-schedule/shared-prefetch-cache
```

返回跨 session 的 `generation_shared_prefetch_cache` 索引。这个索引只包含已通过 promotion、但仍等待 runtime package / WorldStateDeltaTransaction 构建与激活前复验的候选摘要。

它不是玩家 runtime 内容接口。前端玩家侧不应直接加载其中的记录；Studio 或演示脚本可以用它说明“后台预生成结果已经被脱敏索引，可供后续构建器复用”。

### 获取当前 run 的共享缓存命中

```http
GET /api/sessions/{session_id}/generation-schedule/shared-prefetch-cache/hits
```

该接口只读当前 session 最新 run 的 `prefetch-cache` 和全局 `generation_shared_prefetch_cache`，用 `object_kind + object_ref` 精确匹配 shared cache 记录。

返回：

- `generation_shared_prefetch_cache_hits.summary`
- `generation_shared_prefetch_cache_hits.items`

`hit_status` 当前只有：

```text
shared_candidate_available_pending_runtime_build
no_shared_candidate
```

命中仍不代表 runtime-ready。它只是告诉 Studio / 演示脚本：当前调度项有一个跨 session 可复用的脱敏候选摘要，后续仍必须进入 runtime package / WorldStateDeltaTransaction 构建、校验和 activation gate。

边界：

- 不创建 run。
- 不推进 worker。
- 不调用 provider。
- 不写世界状态。
- 不激活 runtime。

### 记录共享缓存复用候选

```http
POST /api/sessions/{session_id}/generation-schedule/workers/record-shared-prefetch-cache-reuse-candidate
```

该接口把当前 run 的一个 shared cache hit 记录为 `generation_artifact_ledger` 中的 `shared_prefetch_cache_reuse_candidate`。它不是 runtime package，也不是 WorldStateDeltaTransaction；它只是把跨 session 命中挂入当前 run 的统一 evidence chain，供后续构建器读取。

请求体可选：

```json
{
  "worker_id": "studio-reuse-recorder",
  "schedule_item_id": "sched_next_map_visual_prefetch"
}
```

未提供 `schedule_item_id` 时，后端选择当前 hit 视图中的第一个命中项。返回包含：

- `worker_step`
- `shared_prefetch_cache_reuse_candidate`
- `generation_prefetch_cache`
- `generation_artifact_ledger`

写入后，对应 prefetch item 的 `cache_status` 会变为：

```text
shared_cache_reuse_pending_runtime_build
```

该状态只表示“当前 run 已有一个可审查复用候选”，仍必须补齐 runtime package / WorldStateDeltaTransaction build、校验和 activation gate。

边界：

- 不调用 provider。
- 不读取 `.env`。
- 不保存 prompt 或 provider response。
- 不写 shared cache。
- 不 complete queue item。
- 不写世界状态。
- 不激活 runtime。

### 索引当前 session 的共享预取候选

```http
POST /api/sessions/{session_id}/generation-schedule/workers/index-shared-prefetch-cache
```

该接口从当前 session 的 `activation-gate` 派生 eligible 候选并写入全局共享索引。它只接受：

```text
promotion_allowed = true
activation_allowed = false
runtime_ready = false
activation_status = blocked_runtime_package_or_world_delta_required
```

返回：

- `shared_prefetch_cache_index.indexed_count`
- `generation_shared_prefetch_cache.summary`
- `generation_shared_prefetch_cache.records`

边界：

- 不调用 provider。
- 不读取 `.env`。
- 不保存 prompt 或 provider response。
- 不 staging、不 promotion。
- 不 complete queue item。
- 不写世界状态。
- 不激活 runtime。

### 导出外部 runner handoff

```http
POST /api/sessions/{session_id}/generation-schedule/workers/export-provider-adapter-runner-handoff
```

该接口用于 Studio / 开发期 worker，不属于玩家默认流程。调用方必须提供 `schedule_item_id` 和 `authorization_ref`，且同一 session / latest run 中必须已经存在匹配的 `GenerationExecutorRunRequest` 与 `ProviderExecutionAuthorization`。

它返回：

- `provider_adapter_runner_handoff.runner_inputs.executor_request`
- `provider_adapter_runner_handoff.runner_inputs.provider_execution_authorization`
- 建议写入 `/tmp` 的 request / authorization / receipt / envelope / artifact / prompt 路径
- `tools/provider_adapter/run_provider_adapter.py` 的 dry-run、live text、live image argv 模板
- runner 完成后调用 `import-provider-adapter-runner-output` 的请求体

该接口只导出 handoff，不创建 receipt/envelope，不调用 provider，不读取 `.env`，不写 ledger，不写世界状态，不激活 runtime。live 模板中的 prompt 文件、artifact 输出和 dotenv 路径必须由外部 worker 在显式授权下提供。

MVP 当前已有 fixture roundtrip smoke：调用方可以消费 handoff 的 `runner_inputs`，用 provider adapter runner 的 dry-run builder 生成本地 receipt / envelope，再调用 `import-provider-adapter-runner-output` 回灌 ledger。回灌后 `prefetch-cache` 会把对应调度项显示为 `review_only_envelope_ready`，但 staging、promotion 和 runtime activation 仍需要后续显式步骤。

### 提交战斗结果

```http
POST /api/sessions/{session_id}/battles/{node_id}/results
```

当前支持的 `node_id` 与结算来源：

- `gray_lantern_station`：使用首战 `battle_result` transaction，推进到 `post_first_defense`。
- `lamp_wick_store`：使用 stage04 `battle_result` transaction，推进到 `post_wick_store_defense`。
- `old_signal_tower`：使用 stage06 `research_job` after-state 作为 `fixture_bridge` 基线，推进到 `signal_resonance_trial`；该节点不会伪装成 `battle_result`。

返回的 `settlement` 会带：

- `settlement_mode`: `transaction` 或 `fixture_bridge`。
- `world_delta`: 原生战斗结算有值；`fixture_bridge` 为 `null`。
- `world_delta_transaction`: 对应的事务外壳或基线 transaction。
- `fixture_baseline`: 仅 `fixture_bridge` 使用，说明来源不是战斗结果。
- `run_world_state`: 写回后的当前运行态。

该接口仍然只消费已审 fixture，不调用 provider，不读取 `.env`。前端应根据 `settlement_mode` 判断证据来源，不能把 `fixture_bridge` 当作玩家战斗实时编译产物。

### 创建调度 dry-run 运行记录

```http
POST /api/sessions/{session_id}/generation-schedule/runs
```

创建并持久化一条 fixture-backed dry-run 运行记录，写入 `generation_schedule_runs` 表。

返回：

- `generation_schedule_run.run_id`
- `generation_schedule_run.status`
- `generation_schedule_run.scheduler_mode`
- `generation_schedule_run.generation_schedule.buffer`
- `generation_schedule_run.execution_policy`
- `generation_schedule_run.source_report_summary`
- `generation_schedule_queue.summary`
- `generation_schedule_queue.items`

当前状态：

```text
fixture_backed_dry_run
```

边界：

- 不启动后台 worker。
- 不调用外部模型。
- 不读取 `.env`。
- 不修改世界状态。
- 不激活预生成候选。
- 只把当前调度计划和 dry-run 报告固化为 session 级运行证据。

### 获取最近调度 dry-run 运行记录

```http
GET /api/sessions/{session_id}/generation-schedule/runs/latest
```

返回最近一次持久化 `generation_schedule_run` 以及从该 run 派生的队列项。若当前 session 尚未创建调度运行记录，则返回：

```json
{
  "generation_schedule_run": null,
  "generation_schedule_queue": {
    "summary": {
      "item_count": 0
    },
    "items": []
  }
}
```

### 获取最近调度队列项

```http
GET /api/sessions/{session_id}/generation-schedule/queue
```

返回最近一次调度 dry-run 派生出的 item 级队列视图：

- `generation_schedule_run`: 最近一次运行的紧凑摘要。
- `generation_schedule_queue.summary`: 队列状态计数。
- `generation_schedule_queue.items`: 每个调度项的队列记录。

队列状态当前只包含：

- `completed`: 已审同步内容已经复用。
- `fallback_ready`: 静态兜底已可用。
- `queued`: 预取、后台或懒加载项已进入候选队列。
- `blocked`: dry-run 未能分类的异常项。

该接口为后续真实 worker 领取任务预留形态；MVP mock 模式不会真正执行 `queued` 项，也不会调用外部模型。

### 调度队列项状态流转

```http
POST /api/sessions/{session_id}/generation-schedule/queue/{schedule_item_id}/claim
POST /api/sessions/{session_id}/generation-schedule/queue/{schedule_item_id}/complete
POST /api/sessions/{session_id}/generation-schedule/queue/{schedule_item_id}/fail
POST /api/sessions/{session_id}/generation-schedule/queue/{schedule_item_id}/retry
POST /api/sessions/{session_id}/generation-schedule/queue/{schedule_item_id}/fallback
```

请求体可选：

```json
{
  "worker_id": "local-mock-worker",
  "note": "short internal note"
}
```

状态规则：

- `claim`: 只允许 `queued -> claimed`。
- `complete`: 允许 `queued|claimed|waiting_review -> completed`。
- `fail`: 允许 `queued|claimed|waiting_review -> failed`。
- `retry`: 只允许 `failed -> queued`，且 `attempt_count < max_attempts`。
- `fallback`: 允许 `failed|waiting_review -> fallback_ready`，且必须存在 `fallback_ref`。
- `completed`、`fallback_ready`、`failed`、`blocked` 不能再被 claim。

返回：

- `generation_schedule_queue_item`: 被更新的队列项。
- `generation_schedule_queue`: 更新后的最近队列摘要。

非法状态流转返回 `409`。未知队列项返回 `404`。

这些接口只更新本地 dry-run 队列状态，仍不会调用外部模型、不会写世界状态、不会激活预生成候选。它们的作用是给后续真实后台 worker 预留最小领取和回写接口。

队列项会携带从 `GenerationSchedulePlan.provider_policy` 派生的预算字段：

- `max_attempts`
- `attempt_count`
- `attempt_budget_exhausted`
- `fallback_ref`

dry-run worker 每处理一次 `queued` 项会递增 `attempt_count`。当 `attempt_count >= max_attempts` 时，`retry` 会返回 `409`，此时只能由人工 / 系统选择 `fallback` 或保持失败状态。

### 调度 dry-run worker step

```http
POST /api/sessions/{session_id}/generation-schedule/workers/dry-run-step
```

请求体可选：

```json
{
  "worker_id": "local-dry-worker",
  "note": "single dry-run step"
}
```

每次只处理最近一次调度 run 中的一个 `queued` 项：

- 如果该项需要 provider / review，则标记为 `waiting_review`。
- 如果该项不需要额外审查，则标记为 `completed`。
- 如果没有 `queued` 项，则返回 `worker_step.status = idle`。

返回：

- `worker_step`
- `generation_schedule_queue_item`
- 更新后的 `generation_schedule_queue`
- `generation_schedule_worker_cache`

当前所有 MVP 预取 / 后台 / 懒加载项都要求启用前复验，因此 dry worker step 会把这些项停在 `waiting_review`。它不会调用外部模型、不会写世界状态、不会激活预生成候选。

每次 dry worker step 处理队列项时，会写入一条 review-only worker cache 记录。该记录只证明“本地 dry worker 已处理这个调度项，并停在复核/激活门前”，不代表真实 provider 已执行，也不代表资产已经可以进入运行时。

### 获取调度 worker cache

```http
GET /api/sessions/{session_id}/generation-schedule/worker-cache
```

返回最近一次调度 run 的 worker cache 视图：

- `generation_schedule_run`: 最近一次运行的紧凑摘要。
- `generation_schedule_worker_cache.summary`: cache 计数、对象类型计数、provider 调用计数、世界修改计数、激活计数、复核计数。
- `generation_schedule_worker_cache.items`: 每个被 dry worker step 处理过的调度项的 review-only cache payload。

当前 worker cache payload 明确包含以下安全边界：

- `provider_call_performed: false`
- `world_mutation_performed: false`
- `activation_allowed_now: false`
- `artifact_placeholder.status: review_only_placeholder`
- `activation_gate.revalidate_before_activation`
- `safe_content_policy.reads_env: false`
- `safe_content_policy.calls_provider: false`
- `safe_content_policy.writes_world_state: false`
- `safe_content_policy.stores_raw_prompt: false`
- `safe_content_policy.stores_provider_response: false`

这张表不是正式生成缓存，不存 raw prompt，不存 provider response，不持有可直接发布的 runtime package。它的作用是给后续真实 worker / provider 调度器预留 session 级执行记录形态，同时让 Studio / evidence 能证明调度器已经具备“处理、等待复核、阻断激活”的最小闭环。

### 调度 live executor guard

```http
POST /api/sessions/{session_id}/generation-schedule/workers/live-executor-guard
```

请求体可选：

```json
{
  "worker_id": "local-live-guard",
  "note": "guard before provider"
}
```

该接口只处理最近一次调度 run 中已经处于 `waiting_review` 的队列项。它不会执行 provider，而是返回并持久化一条 provider guard log：

- `live_executor_guard.status`: `blocked_pending_explicit_authorization`
- `authorization.required`: `true`
- `authorization.granted`: `false`
- `provider_call_performed`: `false`
- `world_mutation_performed`: `false`
- `activation_allowed_now`: `false`
- `raw_prompt_stored`: `false`
- `provider_response_stored`: `false`
- `provider_guard_logs.summary`

同时，`generation_schedule_worker_cache.items[].executor_guard` 会记录该 guard，`activation_gate.blocked_reason` 会变为 `explicit_provider_authorization_required`。

这仍然不是正式后台执行器。它只证明真实 provider 调用前的授权门、产物 manifest 门、校验门和晋升门已经有后端状态落点。没有 `waiting_review` 项时，接口返回 `worker_step.status = idle`。

### 调度 review-only dispatcher

```http
POST /api/sessions/{session_id}/generation-schedule/workers/run-review-only-dispatcher-step
POST /api/sessions/{session_id}/generation-schedule/workers/run-review-only-dispatcher-drain
POST /api/sessions/{session_id}/generation-schedule/workers/run-review-only-background-executor-tick
POST /api/sessions/{session_id}/generation-schedule/workers/run-review-only-background-handoff-tick
```

`run-review-only-dispatcher-step` 会把一个 `queued` 且需要 provider review 的调度项推进到 `ProviderAdapterExecutionReceipt` / `ProviderOutputEnvelope` ledger 边界。`run-review-only-dispatcher-drain` 会按 `max_items` 重复执行这个动作，默认最多 4 个，单次上限 16 个。

`run-review-only-background-executor-tick` 是更接近后台 daemon 的稳定外壳：默认 `max_items = 2`，单次上限 8，内部仍复用 dispatcher drain，并额外返回 `background_executor_tick.safety` 与 `generation_prefetch_cache.summary`，方便 Studio / 脚本展示“后台预取 tick 已推进到 review-only envelope 边界”。

`run-review-only-background-handoff-tick` 在同一 tick 之后为本轮 dispatched 项导出 `runner_handoffs[]`，并返回 `provider_adapter_runner_handoff_outbox`。这些 handoff 是外部 runner outbox，包含脱敏 executor request、provider authorization、建议 `/tmp` 路径、dry-run / live text / live image 命令模板和 import 回灌请求体；接口本身不会运行 provider adapter。`provider_adapter_runner_handoff_outbox` 由 `shared/schemas/provider_adapter_runner_handoff_outbox.v0.1.schema.json` 和 `tools/dev/validate_provider_adapter_runner_handoff_outbox.py` 校验，只证明可安全交给外部 runner，不代表 provider 输出、staging、promotion 或 runtime activation 已完成。

drain 请求体只使用：

```json
{
  "worker_id": "local-dispatcher-drain",
  "note": "bounded review-only background tick",
  "max_items": 4
}
```

返回中的 `worker_step.stop_reason` 为 `budget_exhausted` 或 `no_eligible_items`，`remaining_eligible_count` 表示仍处于 `queued` 且需要 provider review 的剩余项数量。

这些入口都是 Studio / evidence 用内部接口，不是玩家默认体验，也不是真实 provider worker。它们不会调用 provider，不读取 `.env`，不 staging，不 promotion，不 complete queue item，不写世界状态，不激活 runtime。

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
lamp_wick_store
old_signal_tower
```

`MapRuntimePackage v0.1` 的边界：

- 路径、塔位、出生点和目标来自结构化逻辑数据。
- `visual_layers` 只引用本地 `/assets/map_visual_reference/...` 视觉参考层。
- 视觉参考层不是玩法真值，不决定碰撞、伤害、资源、部署或任务条件。
- 后续 AI 生成 painted map 时，也必须重新对齐到同一个 map runtime package。

### 获取 v0.2 地图审查预览包

```http
GET /api/sessions/{session_id}/battles/{node_id}/map-v02-preview
```

返回：

- `preview_mode`：固定为 `review_only_map_v02`。
- `review_only`：固定为 `true`。
- `runtime_activation_allowed`：固定为 `false`。
- `source_refs`：v0.2 runtime package、RenderPlan、语义一致性报告、预览报告和 SVG 预览引用。
- `map_runtime_package_v02`：包含资源点、机关区、防守锚点和阻挡区的 `MapRuntimePackage v0.2 preview`。
- `map_render_plan_bundle_v02`：对应 `MapStylePack`、`ProceduralMapRenderPlan`、语义一致性报告和预览报告。
- `preview_report_v02`：离线 SVG preview 的审查报告。
- `preview_svg_ref`：review-only SVG 预览文件引用。
- `safety`：声明本接口不读取 `.env`、不调用 provider、不修改玩家默认 runtime。

边界：

- 该接口只服务开发审查、Studio 证据和演示录屏，不是玩家默认战斗地图接口。
- 默认玩家战斗仍使用 `/map-runtime-package` 返回的 `MapRuntimePackage v0.1`。
- v0.2 包和 SVG 预览不得被当作 `published_visual_layer`，也不得绕过地图视觉晋升门禁。
- 返回的 `mode` 仍是 `frontend_mock_fixture`，便于前端 mock 客户端复用现有响应包装；review-only 语义在 payload 内表达。

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
- `settlement.core_artifacts`：战后结算对应的 ContextPackage、FactEntry、CGOP、WorldStateDelta、WorldStateDeltaTransaction 原生证据快照；旧 `world_delta`、`world_delta_transaction`、`core_artifact_refs` 仍保留用于兼容。

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
- Generation Scheduler 最近一次持久化 dry-run 运行摘要
- Generation Scheduler 最近一次 item 级队列摘要
- audit summary
- dossier summary

这不是正式后台页面，只是演示证明入口。
