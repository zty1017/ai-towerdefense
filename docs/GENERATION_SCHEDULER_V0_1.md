# Generation Scheduler v0.1

本文档说明 `GenerationSchedulePlan v0.1` 的用途、边界和验收方式。

`Generation Scheduler` 是 AI 编译系统的横切控制面。它不决定内容是否正确，不替代 schema、semantic gate、simulation gate、media gate 或人工审查；它只决定：

- 什么内容必须同步可用。
- 什么内容可以在玩家到达前预取。
- 什么内容适合后台慢慢生成。
- 什么内容只能懒加载修复。
- 失败时使用哪个已审 fallback。

## 当前产物

- `shared/schemas/generation_schedule_plan.v0.1.schema.json`
- `tools/scheduler/build_generation_schedule_plan.py`
- `tools/scheduler/validate_generation_schedule_plan.py`
- `examples/review_packs/mvp_generation_schedule_plan.v0.1.json`
- `shared/schemas/generation_schedule_run_report.v0.1.schema.json`
- `tools/scheduler/run_generation_schedule_plan.py`
- `tools/scheduler/validate_generation_schedule_run_report.py`
- `examples/review_packs/mvp_generation_schedule_run_report.v0.1.json`
- `backend/app/services/generation_scheduler_service.py`
- `generation_schedule_runs` SQLite session table
- `generation_schedule_queue_items` SQLite session table
- `GET /api/sessions/{session_id}/generation-schedule`
- `POST /api/sessions/{session_id}/generation-schedule/runs`
- `GET /api/sessions/{session_id}/generation-schedule/runs/latest`
- `GET /api/sessions/{session_id}/generation-schedule/queue`
- `POST /api/sessions/{session_id}/generation-schedule/queue/{schedule_item_id}/claim`
- `POST /api/sessions/{session_id}/generation-schedule/queue/{schedule_item_id}/complete`
- `POST /api/sessions/{session_id}/generation-schedule/queue/{schedule_item_id}/fail`
- `POST /api/sessions/{session_id}/generation-schedule/queue/{schedule_item_id}/retry`
- `POST /api/sessions/{session_id}/generation-schedule/queue/{schedule_item_id}/fallback`
- `POST /api/sessions/{session_id}/generation-schedule/workers/dry-run-step`

默认构建并校验：

```bash
python3 tools/scheduler/build_generation_schedule_plan.py --validate
```

单独校验：

```bash
python3 tools/scheduler/validate_generation_schedule_plan.py examples/review_packs/mvp_generation_schedule_plan.v0.1.json
```

离线 dry-run 并校验执行报告：

```bash
python3 tools/scheduler/run_generation_schedule_plan.py --validate
python3 tools/scheduler/validate_generation_schedule_run_report.py examples/review_packs/mvp_generation_schedule_run_report.v0.1.json
```

## 边界

当前构建器明确保证：

- 不读取 `.env`。
- 不调用 LLM、图像或视频服务。
- 不启动后台任务。
- 不修改 `RunWorldState`。
- 不导出新的 runtime package。
- 只生成 review-only 调度计划。
- dry-run 执行报告只模拟复用、fallback 和排队动作，不实际执行生成。

## 延迟等级

`GenerationSchedulePlan` 使用五类调度：

| 等级 | 含义 |
|---|---|
| `sync_blocking` | 玩家继续流程前必须可用，只能读取 locked / cached / fallback 内容。 |
| `background_prefetch` | 玩家可能很快遇到，提前准备候选；启用前必须重新校验。 |
| `background` | 体验增强型生成，例如真实视频帧，不阻塞当前玩法。 |
| `lazy` | 低优先级修复或补美术，只有空闲时处理。 |
| `fallback_static` | 实时或后台生成失败时使用的已审静态兜底。 |

## 关键规则

- `sync_blocking` 不允许依赖实时 provider 调用。
- `background_prefetch`、`background`、`lazy` 不允许直接提交世界状态。
- 任何会改变世界的结果必须重新进入 `WorldStateDelta` 结构校验和 semantic gate。
- 预生成结果只能是候选或 review-only，不能因为提前生成就自动进入运行态。
- 玩家侧错误只显示世界内解释，不暴露 provider、prompt、schema、rate limit 或 raw trace。

## 当前 MVP 计划

当前计划包包含 8 个调度项：

- 会话主链路、首战地图包、战斗运行时美术包和静态兜底为同步或 fallback 项。
- Stage 05 世界线 / 玩家线推进作为后台预取项。
- 旧信号塔后续地图底图作为后台预取项。
- 图生视频关键帧和实体 atlas 作为后台增强项。
- 非 runtime 的前端 mock sprite 修复作为懒加载项。

这让系统可以像视频缓冲一样提前准备内容，但真正进入玩家流程前仍受结构化校验和审查门控制。

当前 dry-run 报告会把这些调度项分成：

- `reuse_ready`：已审同步内容直接复用。
- `select_fallback`：静态兜底路径可用。
- `schedule_prefetch`：进入预取队列，但不激活。
- `schedule_background`：进入后台增强队列。
- `schedule_lazy`：进入低优先级修复队列。

报告中的 `provider_call_count` 和 `world_mutation_count` 必须保持为 0。真实执行器只能在后续任务中基于同一计划包实现，且需要继续保留 review、fallback 和启用前复验边界。

## 后端 session 缓冲层

当前后端已经把 review-only 计划包接入 session API：

```text
GET /api/sessions/{session_id}/generation-schedule
```

该接口返回当前调度计划、dry-run 报告、紧凑 buffer 摘要，以及当前 session 最近一次持久化调度运行记录。

当前后端也支持创建一条 session-scoped dry-run 运行记录：

```text
POST /api/sessions/{session_id}/generation-schedule/runs
GET /api/sessions/{session_id}/generation-schedule/runs/latest
```

这些记录写入 `generation_schedule_runs` 表，并在 session reset 时清除。它们证明调度器已经从离线 evidence 进入后端状态层，但仍不是正式后台执行器。

当前后端实现由 `backend/app/services/generation_scheduler_service.py` 维护。`frontend_mock_service.py` 只负责玩家侧 fixture 内容和 evidence 聚合，不再承载 scheduler 队列、状态流转或 retry / fallback 逻辑。

每条 dry-run 运行还会派生 item 级队列记录：

```text
generation_schedule_queue_items
```

当前状态映射：

| dry-run 结果 | 队列状态 | 含义 |
|---|---|---|
| `passed` | `completed` | 已审同步内容已经复用。 |
| `fallback` | `fallback_ready` | 静态兜底路径已可用。 |
| `scheduled` | `queued` | 预取 / 后台 / 懒加载项进入候选队列。 |
| 其他 | `blocked` | dry-run 未能分类，需要人工或系统修复。 |

队列项可通过以下接口读取：

```text
GET /api/sessions/{session_id}/generation-schedule/queue
```

它为后续真正 worker 领取任务预留形态，但当前不会自动执行 `queued` 项。

## 队列状态流转

当前 API 支持最小 worker 状态流转：

```text
queued -> claimed
queued -> completed
claimed -> completed
waiting_review -> completed
queued -> failed
claimed -> failed
waiting_review -> failed
failed -> queued
failed -> fallback_ready
waiting_review -> fallback_ready
```

对应接口：

```text
POST /api/sessions/{session_id}/generation-schedule/queue/{schedule_item_id}/claim
POST /api/sessions/{session_id}/generation-schedule/queue/{schedule_item_id}/complete
POST /api/sessions/{session_id}/generation-schedule/queue/{schedule_item_id}/fail
```

这些接口只改本地队列状态和 item payload 中的 transition log，不触发 provider、不提交世界状态、不激活候选。非法状态流转返回 `409`，例如对已经 `completed` 的同步复用项再次 `claim`。

## Retry / Fallback Budget

队列项会从 `GenerationSchedulePlan.items[].provider_policy` 继承：

```text
max_attempts
provider_policy.mode
provider_policy.profile
fallback_ref
```

dry-run worker 每处理一次 `queued` 项会把 `attempt_count` 加 1。失败后：

- 若 `attempt_count < max_attempts`，可以 `retry` 回到 `queued`。
- 若 `attempt_count >= max_attempts`，`retry` 返回 `409`。
- 若存在 `fallback_ref`，可通过 `fallback` 进入 `fallback_ready`。

MVP 中这些动作仍只改变本地状态，不触发真实生成。它们用于证明未来接入 provider 前已经有预算、重试和降级边界。

## Dry-run Worker Step

当前 API 还支持一个最小 worker step：

```text
POST /api/sessions/{session_id}/generation-schedule/workers/dry-run-step
```

它每次只处理最近一次 run 中的一个 `queued` 项。处理规则：

- 不调用 provider。
- 不写世界状态。
- 不创建新 runtime package。
- 不激活预取候选。
- 如果 item 需要 provider 或人工复核，则进入 `waiting_review`。
- 如果 item 不需要额外复核，则进入 `completed`。
- 没有可处理项时返回 `idle`。

这一步的目的不是完成真实生成，而是把后续 worker 的领取 / 处理 / 等待复核状态面跑通。

## Worker Cache Skeleton

dry-run worker step 处理队列项时，会把该队列项的处理结果写入 session-scoped worker cache：

```text
generation_schedule_worker_cache
GET /api/sessions/{session_id}/generation-schedule/worker-cache
```

这不是正式产物缓存，也不是 provider response 存储。它只记录 review-only worker step 的可审计状态：

- 处理的是哪个 `run_id` / `schedule_item_id`。
- 对应对象类型、对象引用和 latency class。
- 使用的 `worker_id`、`attempt_count` 和当前 `status`。
- 是否需要复核。
- 是否调用 provider。
- 是否写世界状态。
- 是否允许立即激活。
- 被哪个 activation gate 阻断。

当前 MVP 中，这些安全字段必须保持：

```text
provider_call_performed = false
world_mutation_performed = false
activation_allowed_now = false
artifact_placeholder.status = review_only_placeholder
safe_content_policy.calls_provider = false
safe_content_policy.writes_world_state = false
safe_content_policy.stores_raw_prompt = false
safe_content_policy.stores_provider_response = false
```

因此 worker cache 只能作为后端状态层和 Studio / evidence 证据使用，不能作为玩家侧内容事实源，不能绕过 CGOP、WorldStateDelta、semantic gate、media gate 或人工 review。后续真实后台执行器可以复用这张表的形态，但必须新增独立的 provider 调用记录、产物 manifest、校验结果和显式 activation / promotion gate。

## Live Executor Guard Skeleton

当前后端还提供真实后台执行器前的最小守门入口：

```text
POST /api/sessions/{session_id}/generation-schedule/workers/live-executor-guard
```

它只处理最近一次 run 中已经停在 `waiting_review` 的队列项，并写入一条 `generation_live_executor_guard.v0.1` provider guard log。该 log 证明系统已经识别到“这里未来可能需要真实 provider 执行”，但仍然显式阻断：

```text
provider_call_performed = false
world_mutation_performed = false
activation_allowed_now = false
raw_prompt_stored = false
provider_response_stored = false
authorization.required = true
authorization.granted = false
```

该入口会把 worker cache 的 `activation_gate.blocked_reason` 更新为：

```text
explicit_provider_authorization_required
```

并记录后续真实执行器必须补齐的 gates：

- explicit user authorization
- provider adapter execution
- artifact manifest write
- schema or media validation
- manual or semantic review
- activation or promotion gate

这一步仍不读取 `.env`，不调用 provider，不写世界状态，不创建 runtime package，不激活 review-only 产物。它只是把“真实 provider 执行前必须有授权、产物 manifest、校验和晋升门”的形态接到 session 状态层和 evidence 中。

## Campaign Router 接入

当前后端已经提供最薄的战役路由层：

```http
GET /api/sessions/{session_id}/campaign-router
POST /api/sessions/{session_id}/campaign-router/prefetch-next
```

`CampaignRouter` 不替代 Generation Scheduler，也不替代 `WorldStateDeltaTransaction`。它只根据当前 `RunWorldState.progress.phase`、已审战斗节点表和已审 runtime/map package 判断：

- 当前节点。
- 下一节点。
- 前视窗口。
- 下一节点资产是否已有 reviewed package。
- 是否需要触发 scheduler dry-run 预取。

`prefetch-next` 会在没有 session dry-run 时创建一条 `generation_schedule_run`，然后执行一个 dry-run worker step。它仍然保持以下边界：

- 不读取 `.env`。
- 不调用 provider。
- 不创建新内容。
- 不写世界状态。
- 不激活预取候选。

这一步的意义是把“玩家进入当前节点时，系统提前检查下一节点资产 / fallback”的运行时胶水接上，而不是把 Scheduler 升级成正式后台执行器。

边界保持不变：

- 不读取 `.env`。
- 不调用 provider。
- 不创建新内容。
- 不写世界状态。
- 不激活预取候选。
- 只复用当前已审计划包和 dry-run 报告，生成 session 级调度运行证据。
