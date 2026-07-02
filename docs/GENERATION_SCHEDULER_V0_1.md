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
