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
- `generation_schedule_runs` SQLite session table
- `generation_schedule_queue_items` SQLite session table
- `GET /api/sessions/{session_id}/generation-schedule`
- `POST /api/sessions/{session_id}/generation-schedule/runs`
- `GET /api/sessions/{session_id}/generation-schedule/runs/latest`
- `GET /api/sessions/{session_id}/generation-schedule/queue`

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

边界保持不变：

- 不读取 `.env`。
- 不调用 provider。
- 不创建新内容。
- 不写世界状态。
- 不激活预取候选。
- 只复用当前已审计划包和 dry-run 报告，生成 session 级调度运行证据。
