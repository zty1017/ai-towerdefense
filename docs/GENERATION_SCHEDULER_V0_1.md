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

## GenerationExecutorRunRequest

`GenerationExecutorRunRequest v0.1` 是 live executor guard 之后、真实 provider adapter 之前的执行请求边界：

```text
shared/schemas/generation_executor_run_request.v0.1.schema.json
tools/dev/validate_generation_executor_run_request.py
examples/generation_executor_requests/p1b_generation_executor_run_request.example.json
POST /api/sessions/{session_id}/generation-schedule/workers/prepare-executor-request
```

它的职责不是调用 provider，也不是保存 provider 输出，而是把一个已经停在 `waiting_review`、且已经写入 `generation_live_executor_guard.v0.1` 的队列项，整理成真实执行器后续可消费的最小请求包。

请求包允许包含：

- run / schedule item / object ref / latency class / guard id。
- provider mode 与 provider profile 的脱敏执行意图。
- attempt budget、fallback ref 和必经 gates。
- `input_refs` / `context_refs` 形式的本地引用。
- output intent、artifact policy 和 activation policy。

请求包禁止包含：

- prompt 正文。
- provider 响应正文。
- secret、token、API key。
- 临时 provider URL 作为最终 refs。
- runtime-ready 声明。
- 世界状态写入或 runtime 激活行为。

后端入口会把请求包摘要登记到 `generation_artifact_ledger`，artifact kind 为：

```text
generation_executor_run_request
```

它保持：

```text
provider_call_count = 0
world_mutation_count = 0
activation_allowed_count = 0
authorization.granted = false
```

`dry-run-step`、`live-executor-guard` 和 `prepare-executor-request` 的请求体支持可选 `schedule_item_id`。提供该字段时，worker 只处理对应队列项；如果该项不处于当前 worker 所需状态，则返回 409。这让后台执行器可以按具体对象预取 / 生成，而不是只能按队列顺序处理第一个可用项。

因此真实 executor 的最小顺序更新为：

```text
live executor guard
  -> GenerationExecutorRunRequest
  -> ProviderExecutionAuthorization
  -> ProviderAdapterExecutionReceipt
  -> ProviderOutputEnvelope
  -> ProviderArtifactStagingManifest
  -> validator / media gate / semantic gate
  -> ProviderArtifactPromotionReport
  -> runtime package or WorldStateDeltaTransaction
```

## ProviderExecutionAuthorization

`ProviderExecutionAuthorization v0.1` 是 `GenerationExecutorRunRequest` 之后、真实 provider adapter 之前的显式授权记录：

```text
shared/schemas/provider_execution_authorization.v0.1.schema.json
tools/dev/validate_provider_execution_authorization.py
examples/provider_authorizations/p1b_provider_execution_authorization.example.json
POST /api/sessions/{session_id}/generation-schedule/workers/grant-provider-authorization
```

它只证明“某个已经过 guard、已经生成 executor request 的调度项，允许后续 provider adapter 执行一次受约束调用”。它本身仍然不调用 provider，不读取 `.env`，不保存 prompt / provider 正文，不写世界状态，不激活 runtime。

授权记录必须与 `GenerationExecutorRunRequest` 的同一 `run_id` / `schedule_item_id` 对齐，并生成 `authorization_ref`。后续 `ProviderOutputEnvelope.provider_call.authorization_ref` 必须能匹配该记录，否则 provider 输出、staging manifest 和 promotion report 不能登记到 `generation_artifact_ledger`。

授权范围冻结为：

```text
provider_adapter_execution_only
```

这意味着它只允许进入 provider adapter 边界；不等于 runtime 激活授权，不等于世界状态写入授权，也不等于晋升通过。

## ProviderAdapterExecutionReceipt

`ProviderAdapterExecutionReceipt v0.1` 是 `ProviderExecutionAuthorization` 之后、`ProviderOutputEnvelope` 之前的 provider adapter 边界回执：

```text
shared/schemas/provider_adapter_execution_receipt.v0.1.schema.json
tools/dev/validate_provider_adapter_execution_receipt.py
examples/provider_adapter_executions/p1b_provider_adapter_execution_receipt.example.json
POST /api/sessions/{session_id}/generation-schedule/workers/run-provider-adapter-fixture
```

它的职责是证明某个已授权的调度项已经进入 provider adapter 边界，并声明后续必须写入 `ProviderOutputEnvelope`。MVP 当前实现是 `fixture_backed_no_provider_call`：不读取 `.env`，不调用 provider，不保存 prompt / provider 正文，不写世界状态，不激活 runtime。

该回执必须与同一 `schedule_item_id` 和同一 `authorization_ref` 的 `ProviderExecutionAuthorization` 对齐。后续 live adapter 可以使用同一 schema 的 `live_redacted_provider_call` 模式，但仍只能保存脱敏摘要、digest 和本地 artifact refs；真实 provider 原始响应仍不得进入 evidence、ledger 或 runtime。

工具层已经提供 provider adapter runner：

```text
tools/provider_adapter/run_provider_adapter.py
examples/provider_adapter_runs/p1b_provider_adapter_runner.executor_request.json
examples/provider_adapter_runs/p1b_provider_adapter_runner.receipt.json
examples/provider_adapter_runs/p1b_provider_adapter_runner.envelope.json
```

runner 默认 `fixture` dry-run，不读取 `.env`，不调用 provider。显式 `--mode llm_text --live` 时才允许调用 `tools/llm/adapter.py` 中的 LLM profile，并且仍只写入 redacted summary artifact、`ProviderAdapterExecutionReceipt` 和 `ProviderOutputEnvelope`。图片 provider adapter 已在工具层以显式 `--mode image --live` 形式接入。`--mode video` 当前只是离线边界：它会生成 review-only receipt/envelope，`finish_reason=video_live_provider_not_implemented`，不创建视频候选；`--mode video --live` 必须快速失败，不读取 `.env`、不导入 provider、不写伪成功产物。

后端已提供 runner dry-run bridge：

```text
POST /api/sessions/{session_id}/generation-schedule/workers/run-provider-adapter-runner-fixture
```

该入口要求当前 session / latest run 已经存在匹配的 `GenerationExecutorRunRequest` 和 `ProviderExecutionAuthorization`，然后复用工具层 runner 的 dry-run artifact builder 生成 `ProviderAdapterExecutionReceipt` 与 `ProviderOutputEnvelope`，并把二者登记到 `generation_artifact_ledger`。它不会自动 staging、promotion、complete queue item、写世界状态或激活 runtime；队列仍停在 review / promotion 前。

后端也提供外部 runner handoff 导出：

```text
POST /api/sessions/{session_id}/generation-schedule/workers/export-provider-adapter-runner-handoff
```

该入口同样要求已有匹配的 `GenerationExecutorRunRequest` 与 `ProviderExecutionAuthorization`，但它不生成 receipt/envelope，也不写 ledger。它只从 ledger compact 还原经过 schema 校验的 executor request 与 authorization，返回建议写入 `/tmp` 的文件路径、`tools/provider_adapter/run_provider_adapter.py` 的 dry-run / live text / live image argv 模板，以及 runner 完成后应调用的 `import-provider-adapter-runner-output` 请求体。

因此该入口是正式后台执行器前的外部 worker 交接单，不是真 provider 调用入口。它不读取 `.env`，不调用 provider，不包含 prompt 正文，不包含 provider 响应正文，不 staging，不 promotion，不写世界状态，不激活 runtime。live 模板中的 `.env` 路径、prompt 文件和 artifact 输出仍必须由外部 worker 在显式授权下提供。

当前测试已覆盖 fixture roundtrip：从 handoff 的 `runner_inputs` 生成 dry-run receipt / envelope，本地写入 `/tmp`，再通过 `import-provider-adapter-runner-output` 回灌 ledger，最后由 `prefetch-cache` 读到 `review_only_envelope_ready`。这证明 handoff 与 import 两端已对齐，但仍不代表 live provider、staging、promotion 或 runtime activation 已自动化。

此外，`tools/dev/check_provider_runner_handoff_outbox_import_pipeline.py` 提供更严格的 outbox import pipeline smoke：它启动临时 SQLite 与本地 uvicorn，创建 scheduler run 后只为两个 queued provider-review 调度项执行 dry-run / live guard / executor request / provider authorization / handoff export，不运行后端 provider runner fixture；随后手动组装 `ProviderAdapterRunnerHandoffOutbox v0.1`，交给 `tools/dev/run_provider_adapter_runner_handoff_outbox.py` 的离线 `fixture` consumer 生成 receipt/envelope，再显式调用 `import-provider-adapter-runner-output` 导回临时后端 ledger。该 smoke 会先断言导入前 `prefetch-cache.review_only_envelope_ready_count == 0`，再断言导入后为 2，且 activation allowed、provider call、`.env` read、staging、promotion、queue complete、world mutation 都为 0。`tools/dev/validate_provider_runner_handoff_outbox_import_pipeline_report.py` 只读复核该报告的 handoff / consumer / import / prefetch 因果和安全边界，不重新启动后端。它只证明本地 consume -> import -> prefetch-cache 因果闭环，不提交报告到仓库，也不代表后端自动 live provider 执行器已经完成。

后端还提供 review-only dispatcher 薄编排入口：

```text
POST /api/sessions/{session_id}/generation-schedule/workers/run-review-only-dispatcher-step
```

该入口会在缺少 run 时创建一条 session 级 scheduler run，并选择调用方指定的 `schedule_item_id` 或下一个 `queued` 项，按固定顺序串接：

```text
dry-run-step
  -> live-executor-guard
  -> prepare-executor-request
  -> grant-provider-authorization
  -> run-provider-adapter-runner-fixture
```

它只把一个待生成项推进到 `ProviderAdapterExecutionReceipt` / `ProviderOutputEnvelope` review-only 边界，并登记到 `generation_artifact_ledger`。它不调用 provider，不读取 `.env`，不 staging，不 promotion，不 complete queue item，不写世界状态，也不激活 runtime；队列项仍停在 `waiting_review`。因此它是正式后台执行器前的 dispatcher 骨架，不是完整 executor chain，也不是内容晋升入口。

后端同时提供 bounded drain 入口，用于模拟后台 worker 的一个受限 tick：

```text
POST /api/sessions/{session_id}/generation-schedule/workers/run-review-only-dispatcher-drain
```

该入口只接受 `worker_id`、`note` 和 `max_items`，默认最多处理 4 个、单次上限 16 个。它会重复调用同一 review-only dispatcher step，直到达到预算或没有剩余 `queued` 且 `provider_review_required` 的项。返回的 `worker_step.stop_reason` 为 `budget_exhausted` 或 `no_eligible_items`，并携带 `remaining_eligible_count`，用于区分“本轮预算耗尽”和“队列已清空”。它拒绝 `schedule_item_id`、`authorization_ref`、`artifact_profile`、导入路径等定向 metadata，避免一次 drain 把同一个授权 ref 或产物路径错挂到多个调度项。

drain 的边界与单步 dispatcher 相同：只登记 executor request、provider authorization、adapter receipt 和 ProviderOutputEnvelope；不调用 provider，不读取 `.env`，不 staging，不 promotion，不 complete queue item，不写世界状态，不激活 runtime。它是正式后台执行器的调度壳和吞吐量控制面雏形，不是 live provider worker。

后端还提供更接近正式 daemon loop 的 review-only background executor tick：

```text
POST /api/sessions/{session_id}/generation-schedule/workers/run-review-only-background-executor-tick
```

该入口是 `run-review-only-dispatcher-drain` 的稳定外壳。它默认 `max_items = 2`，单次上限 8，适合由 Studio、脚本或未来后台循环按小预算触发；内部仍复用 drain，不复制 guard、authorization、runner 或 ledger 校验逻辑。

tick 返回 `worker_step.worker_mode = review_only_background_executor_tick`、底层 `dispatcher_worker_step`、`dispatcher_steps`、queue、worker cache、artifact ledger 和最新 `generation_prefetch_cache` 摘要。它明确声明以下安全边界：

- 不读取 `.env`。
- 不调用 provider。
- 不 staging，不 promotion。
- 不 complete queue item。
- 不写世界状态。
- 不激活 runtime。

因此它是正式后台执行器 / daemon loop 前的 API 形状和吞吐预算壳，不是 live provider worker，也不是内容发布入口。后续真正后台执行器可以把触发方式从手动 API 换成定时 / 事件驱动，但仍必须保留同一授权链、ProviderOutputEnvelope、staging / promotion gate、runtime package gate 和 WorldStateDeltaTransaction gate。

后端还提供 background handoff tick，用于把本轮 tick 产出的执行请求和授权批量导出给外部 runner：

```text
POST /api/sessions/{session_id}/generation-schedule/workers/run-review-only-background-handoff-tick
```

该入口先复用 `run-review-only-background-executor-tick`，再对本轮 `dispatcher_steps` 中的每个 `schedule_item_id / authorization_ref` 调用既有 `export-provider-adapter-runner-handoff`。返回的 `runner_handoffs[]` 包含：

- `runner_inputs.executor_request`
- `runner_inputs.provider_execution_authorization`
- `suggested_paths`
- `command_templates.dry_run_fixture`
- `command_templates.video_boundary`
- `command_templates.live_llm_text`
- `command_templates.live_image`
- `import_after_runner.body`

这相当于正式后台 provider worker 前的安全 outbox：后端 API 只导出脱敏 handoff，不运行 `tools/provider_adapter/run_provider_adapter.py`，不读取 `.env`，不调用 provider，不 staging，不 promotion，不 complete queue item，不写世界状态，不激活 runtime。外部 runner 执行后仍必须通过 `import-provider-adapter-runner-output` 回灌 receipt/envelope，并继续走 staging / promotion / activation gates。

当前 handoff tick 还会返回机器可校验的 outbox wrapper：

```text
provider_adapter_runner_handoff_outbox
shared/schemas/provider_adapter_runner_handoff_outbox.v0.1.schema.json
tools/dev/validate_provider_adapter_runner_handoff_outbox.py
```

`ProviderAdapterRunnerHandoffOutbox v0.1` 把本轮 `runner_handoffs[]` 固化为外部 runner 可消费的批量交接单。它只表达 review-only handoff、导入合同和安全边界，不是 provider 输出、staging manifest、promotion report、runtime package 或世界状态事务。outbox 可以包含 live text / live image 命令模板，但这些模板必须继续要求外部显式授权、显式 prompt file、显式 artifact output 和显式 `.env` 路径；video 只暴露 `command_templates.video_boundary`，命令形态为不带 `--live` 的 `--mode video` 离线边界，不要求 dotenv，也不代表真实图生视频 provider 已接入。

本地外部 runner 第一版入口：

```text
tools/dev/run_provider_adapter_runner_handoff_outbox.py
```

该工具读取一个 `ProviderAdapterRunnerHandoffOutbox v0.1` 文件，逐项写出脱敏 executor request / authorization，并运行 `tools/provider_adapter/run_provider_adapter.py` 的离线 `fixture` 或 `video` boundary，生成 `ProviderAdapterExecutionReceipt`、`ProviderOutputEnvelope` 和 `provider_adapter_runner_handoff_outbox_execution_report.v0.1`。它默认不读取 `.env`、不调用 provider、不导入后端、不 staging、不 promotion、不 complete queue item、不写世界状态、不激活 runtime。报告会保留 `import_after_runner` 请求体，但不会自动调用导入 API；外部 runner 输出进入后端 ledger 仍必须由显式导入步骤完成。

当前已有本地 HTTP smoke 证据：

```text
tools/dev/check_generation_scheduler_review_only_pipeline.py
tools/dev/validate_generation_scheduler_review_only_pipeline_smoke_report.py
examples/review_packs/generation_scheduler_review_only_pipeline_smoke_report.v0.1.json
```

该脚本使用临时 SQLite 和本地 uvicorn，先走 `run-review-only-background-handoff-tick`，再读取 queue / worker-cache / artifact-ledger / prefetch-cache / activation-gate，并额外验证 handoff tick 对 targeted metadata 与过大 `max_items` 的 409 阻断。随后它用 `run-fixture-executor-chain` 覆盖默认 promotion blocked 与 `image_failure` validation failed 两条负样本；再用临时 SQLite seed 制造一个仅限 smoke 的 `promotion_allowed` ledger entry，验证 `run-runtime-activation-readiness-chain` 能串起 runtime build request、runtime artifact build report 和 activation authorization 三步，并停在 `wait_for_runtime_activation_apply_gate`；最后确认 blocked default chain 不会写入 shared cache，且没有 approved promotion fixture 时 shared cache hit / reuse candidate 会保持空或 409。

独立 validator 只读取 smoke report，不重新启动后端；它复核 schema、step、checks、runtime readiness chain、apply gate 后续动作和 safety boundary。该 smoke 只能证明 review-only scheduler pipeline 能通过本地 HTTP 创建 session 级证据链、导出安全 handoff outbox、推进到 activation authorization 记录，并保持 provider / world / runtime 边界为 0。它不能声称 live provider 调用、真实 provider adapter 执行、staging/promotion 自动化、queue complete、runtime package apply、WorldStateDeltaTransaction apply、runtime activation、玩家侧发布或真实图生视频 provider 已完成。

后端还提供只读预取缓存视图：

```text
GET /api/sessions/{session_id}/generation-schedule/prefetch-cache
```

该视图不创建新的 run，也不推进任何 worker。它只读取最近一次 `generation_schedule_run` 的 `generation_schedule_queue_items` 与 `generation_artifact_ledger`，按 `schedule_item_id` 汇总 executor request、provider authorization、adapter receipt、ProviderOutputEnvelope、staging manifest 和 promotion report refs，并派生 `cache_status`。因此它是前端 / Studio 读取后台预取证据的视图，不是新的缓存表，也不是正式后台执行器。

后端还提供后台执行器就绪视图：

```text
GET /api/sessions/{session_id}/generation-schedule/daemon-readiness
```

该视图只读 `prefetch-cache`、`activation-gate` 与 `shared-prefetch-cache/hits`，把当前 session 是否具备安全手动 tick、是否有 queued provider-review 项、是否已有 review-only envelope、是否命中 shared cache，以及正式自动 daemon 为何仍被阻断整理成 `generation_daemon_readiness.v0.1`。它会给出 recommended next actions，但只指向已有受控入口，例如 `run-review-only-background-handoff-tick`、`record-shared-prefetch-cache-reuse-candidate` 或显式 artifact review import。它不创建 run、不推进 worker、不调用 provider、不读取 `.env`、不 staging、不 promotion、不 complete queue item、不写世界状态、不激活 runtime。

视图中的 `provider_call_count_by_this_request` 与 `world_mutation_count_by_this_request` 必须始终为 `0`。如果历史 ledger 中的 ProviderOutputEnvelope 记录过真实 provider 调用，只能进入 `recorded_provider_call_count`，不能证明本次 GET 调用了 provider。该视图也不能绕过 staging、promotion、runtime package、WorldStateDeltaTransaction 或 activation gate。

后端还提供只读激活门视图：

```text
GET /api/sessions/{session_id}/generation-schedule/activation-gate
```

该视图直接从 `prefetch-cache` 派生，不创建 run、不推进 dispatcher、不写 ledger、不 staging、不 promotion、不 complete queue item、不调用 provider、不写世界状态，也不激活 runtime。它的目的不是展示“已经可用了什么”，而是明确每个后台候选为什么仍不能进入玩家 runtime。

返回中的 `generation_activation_gate.summary` 至少包含：

- `item_count`
- `gate_status_counts`
- `blocked_count`
- `not_applicable_count`
- `runtime_ready_count`
- `activation_allowed_count`
- `promotion_allowed_count`
- `recorded_provider_call_count`
- `provider_call_count_by_this_request`
- `world_mutation_count_by_this_request`

其中 `provider_call_count_by_this_request`、`world_mutation_count_by_this_request`、`runtime_ready_count` 和 `activation_allowed_count` 在当前 read-model 中必须保持为 `0`。即使某个候选已有 `promotion_allowed_pending_activation`，也只能说明它可以进入后续 runtime package / WorldStateDeltaTransaction 构建与复验，不代表本接口允许激活。

典型状态：

| `activation_status` | 含义 |
|---|---|
| `blocked_runtime_package_or_world_delta_required` | promotion 已允许下一步构建，但仍缺 runtime package / WorldStateDeltaTransaction 和最终 activation gate。 |
| `blocked_promotion_report` | promotion report 明确阻断，需要修复失败门禁后重跑。 |
| `blocked_promotion_required` | staging 已有 review-only 候选，但还缺 promotion report。 |
| `blocked_staging_or_promotion_required` | ProviderOutputEnvelope 已入账，但还缺 staging / promotion。 |
| `blocked_provider_output_envelope_required` | 只有 receipt 或 waiting review，尚未形成 ProviderOutputEnvelope。 |
| `blocked_provider_adapter_required` | 只有 provider authorization，尚未执行 adapter。 |
| `blocked_provider_authorization_required` | 只有 executor request，尚未显式授权 provider adapter。 |
| `queued_or_not_ready` | 调度项还没有抵达可审查 artifact 边界。 |
| `not_applicable_locked_or_fallback_source` | 同步复用或 fallback 内容不是本生成候选 activation gate 的对象。 |

这让前端 / Studio / 演示脚本能清楚区分：

```text
后台有 review-only 候选证据
  != 已经可以进入玩家 runtime
```

后端还提供跨 session 的共享预取缓存索引：

```text
GET /api/sessions/{session_id}/generation-schedule/shared-prefetch-cache
GET /api/sessions/{session_id}/generation-schedule/shared-prefetch-cache/hits
POST /api/sessions/{session_id}/generation-schedule/workers/index-shared-prefetch-cache
POST /api/sessions/{session_id}/generation-schedule/workers/record-shared-prefetch-cache-reuse-candidate
```

它用于把当前 session 中已经 `promotion_allowed`、但仍被 runtime package / WorldStateDeltaTransaction / activation gate 阻断的候选，登记为后续 session 或后台 worker 可复用的索引记录。该索引不是玩家 runtime 内容池，也不是 published media，不会绕过 activation gate。

`index-shared-prefetch-cache` 只从 `generation_activation_gate` 派生记录，且只接受：

```text
promotion_allowed = true
activation_allowed = false
runtime_ready = false
activation_status = blocked_runtime_package_or_world_delta_required
```

记录状态固定为：

```text
promotion_allowed_pending_runtime_build
```

这表示候选只允许进入后续 runtime package build、WorldStateDeltaTransaction build 和启用前复验。它不表示候选已经 runtime-ready。

共享缓存索引的边界：

- 不保存 prompt 正文。
- 不保存 provider response 正文。
- 不调用 provider。
- 不写世界状态。
- 不 staging、不 promotion。
- 不 complete queue item。
- 不激活 runtime。
- 不随单个 session reset 自动清除，因为它是跨请求 / 跨 session 的脱敏索引，而不是 session-scoped 状态。

当前实现仍是最小索引层，还不包含正式 cache eviction、版本迁移、跨世界书兼容性检查或自动命中回填。后续正式后台执行器读取该索引时，仍必须重新检查 worldbook / run_world_version / ContextPackage hash / schema version / media gate / activation gate。

`shared-prefetch-cache/hits` 是当前 run 的只读命中视图。它读取当前 latest run 的 prefetch-cache item，再用 `object_kind + object_ref` 精确匹配全局 shared cache 记录，并返回每个调度项是否命中：

```text
shared_candidate_available_pending_runtime_build
no_shared_candidate
```

该视图不创建 run、不推进 worker、不调用 provider、不写世界状态、不激活 runtime。命中只说明“有可复用的脱敏候选摘要，可供后续构建器参考”，不代表可以跳过 runtime package build、WorldStateDeltaTransaction build、media / semantic gate 或 activation gate。

`record-shared-prefetch-cache-reuse-candidate` 会把当前 run 的一个 hit 写入 `generation_artifact_ledger`，artifact kind 为：

```text
shared_prefetch_cache_reuse_candidate
```

对应 `prefetch-cache` 状态为：

```text
shared_cache_reuse_pending_runtime_build
```

这个状态仍然是 review-only。它只说明当前 run 已经把跨 session 共享候选纳入统一 evidence chain；后续构建器仍必须补齐 runtime package / WorldStateDeltaTransaction build、校验、promotion/activation gate 和世界状态事务。该 worker 不调用 provider、不读取 `.env`、不写 shared cache、不 complete queue item、不写世界状态、不激活 runtime，并且同一 session / run / schedule item / cache key 会幂等更新同一条 ledger。

后端还提供 runtime 构建请求桥接入口：

```text
POST /api/sessions/{session_id}/generation-schedule/workers/prepare-runtime-build-request
```

该入口从当前 `prefetch-cache` 中选择一个已经 `promotion_allowed` 的 provider artifact 候选，或一个已经登记到当前 run 的 `shared_prefetch_cache_reuse_candidate`，并把它写入 `generation_artifact_ledger`，artifact kind 为：

```text
generation_runtime_build_request
```

对应 `prefetch-cache` 状态为：

```text
runtime_build_request_prepared
```

这个状态仍然不是 runtime package、不是 WorldStateDeltaTransaction、不是 published media，也不是玩家侧可加载资产。它只表示当前 run 已经准备好一份 review-only 构建请求，后续仍必须由 runtime package / WorldStateDeltaTransaction builder 消费、重新校验 media / semantic gate、显式 activation gate 才能进入玩家 runtime。

该 worker 的边界：

- 不调用 provider。
- 不读取 `.env`。
- 不保存 prompt 正文或 provider response 正文。
- 不构建 runtime package。
- 不构建 WorldStateDeltaTransaction。
- 不写世界状态。
- 不 complete queue item。
- 不激活 runtime。

`daemon-readiness` 会在存在 `promotion_allowed` 或共享复用候选时推荐 `prepare-runtime-build-request`；在请求已登记后，会继续推荐 `run-runtime-artifact-build-report`。

后端还提供 runtime artifact build report 入口：

```text
POST /api/sessions/{session_id}/generation-schedule/workers/run-runtime-artifact-build-report
```

该入口只消费已经登记到当前 run 的 `generation_runtime_build_request`，并把可解析的目标引用写成 `generation_runtime_artifact_build_report` ledger evidence。它支持第一版确定性 target resolution：

- `runtime_package:*`：解析到已有 `RuntimePackage v0.1` fixture。
- `map_runtime_package:*`：解析到已有 `MapRuntimePackage v0.1` fixture。
- `map_compile_package:*`：解析到 `MapCompilePackage v0.2` 与其 `export_refs.map_runtime_package_path`。
- `compilable_object_plan:*`：解析到已审查的 `WorldStateDeltaTransaction v0.1` fixture。
- `media_atlas:*`：解析到已有 media atlas manifest。

对应 `prefetch-cache` 状态为：

```text
runtime_artifact_build_report_ready
```

这个状态仍然不是玩家侧激活。它只表示后端已经为该调度项记录了 review-only 目标解析报告；后续仍必须通过 runtime artifact validation review、media / semantic gate 和 explicit activation gate。该 worker 不调用 provider、不读取 `.env`、不保存 prompt / provider 正文、不生成新 runtime package 文件、不提交 WorldStateDeltaTransaction、不 complete queue item、不写世界状态、不激活 runtime。

后端还提供 runtime activation authorization 记录入口：

```text
POST /api/sessions/{session_id}/generation-schedule/workers/record-runtime-activation-authorization
```

该入口只消费已经登记到当前 run 的 `generation_runtime_artifact_build_report`，并把开发者 / Studio / 受控脚本的显式激活决策写成 `generation_runtime_activation_authorization` ledger evidence。第一版支持的 `activation_decision` 为：

- `approved_for_manual_apply`
- `needs_more_review`
- `rejected`

默认决策是 `approved_for_manual_apply`，但它仍只是 review-only 授权记录，不会执行 runtime apply。对应 `prefetch-cache` 状态为：

```text
runtime_activation_authorization_recorded
```

这个状态仍然不是玩家侧激活，也不代表队列已完成。它只表示系统已经有一条显式授权记录；后续仍必须通过 `runtime_activation_apply_gate`、激活后证据复跑和必要的队列完成步骤。该 worker 不调用 provider、不读取 `.env`、不保存 prompt / provider 正文、不生成 runtime package 文件、不提交 WorldStateDeltaTransaction、不 complete queue item、不写世界状态、不激活 runtime。

为了减少演示脚本和本地开发时的手动步骤，后端还提供一个受控链式入口：

```text
POST /api/sessions/{session_id}/generation-schedule/workers/run-runtime-activation-readiness-chain
```

该入口只顺序复用已有三步 worker：

```text
prepare-runtime-build-request
-> run-runtime-artifact-build-report
-> record-runtime-activation-authorization
```

它不新增新的内容事实源，也不跳过任一步的前置条件。调用后会写入同样三类 ledger evidence：`generation_runtime_build_request`、`generation_runtime_artifact_build_report` 和 `generation_runtime_activation_authorization`。如果其中某步已存在，稳定 id 会使 ledger 幂等更新而不是新增重复记录。

该入口的边界与三步 worker 的组合一致：不调用 provider、不读取 `.env`、不保存 prompt / provider 正文、不生成 runtime package 文件、不提交 WorldStateDeltaTransaction、不 complete queue item、不写世界状态、不激活 runtime。它的目的只是减少本地受控推进成本；真正玩家 runtime apply 仍必须由后续单独的 apply gate 处理。

后端也允许导入外部 runner 已经生成好的本地 receipt/envelope：

```text
POST /api/sessions/{session_id}/generation-schedule/workers/import-provider-adapter-runner-output
```

调用方必须提供 `schedule_item_id`、`authorization_ref`、`receipt_path` 和 `envelope_path`。后端只接受仓库内或 `/tmp` 下的 JSON 文件，并会拒绝包含 `raw_prompt`、`provider_response`、`provider_body`、`secret`、`api_key` 等敏感键的导入内容。导入前必须已存在匹配的 executor request 与 provider authorization；导入时会重新校验 `ProviderAdapterExecutionReceipt`、`ProviderOutputEnvelope` 以及 receipt/envelope/source 与 ledger 授权链是否一致。导入本身不调用 provider，不 staging，不 promotion，不激活 runtime。

后端还允许导入外部工具已经生成并校验过的 staging / promotion review 文件：

```text
POST /api/sessions/{session_id}/generation-schedule/workers/import-provider-artifact-review-output
```

调用方必须提供 `schedule_item_id`、`staging_path` 和 `promotion_report_path`。后端只接受仓库内或 `/tmp` 下的本地 JSON 文件，并会拒绝 `.env`、prompt 正文、provider 正文、secret、API key 或 raw trace。导入前必须已经有同一 session / latest run / schedule item 下匹配 `source_envelope_id` 的 `ProviderOutputEnvelope` ledger entry；导入时会重新校验 `ProviderArtifactStagingManifest`、`ProviderArtifactPromotionReport`、promotion 指向的 staging 文件、staged artifact 引用和 source envelope 引用。导入本身不调用 provider，不写世界状态，不激活 runtime，也不把 promotion report 当作发布动作；它只是把外部审查产物安全登记进 `generation_artifact_ledger`。

当前工具层还提供显式 image live 边界：

```text
tools/provider_adapter/run_provider_adapter.py --mode image --live
```

该模式只能在显式授权、显式 `--live`、显式 prompt file 和显式 artifact output 同时存在时运行。它复用 `tools/media/image_provider.py` 的 image provider profile，下载 provider 返回的图片到本地 artifact path，并且只在 `ProviderAdapterExecutionReceipt` 与 `ProviderOutputEnvelope` 中保存 prompt digest、image digest、byte size、本地 artifact ref 和 redacted summary。它不得保存 prompt 正文、provider 原始响应、临时 URL 或 secret，也不得直接进入 staging、runtime package、published media 或世界状态。

因此 runner 当前能力边界是：

- `fixture`：默认 dry-run，不读 `.env`、不联网。
- `llm_text --live`：显式 live 文本候选，只写 redacted summary ref。
- `image --live`：显式 live 图片候选，只写本地 review-only image ref。
- `video`：离线 video adapter 边界，只写 review-only receipt/envelope，声明 live 图生视频尚未实现。
- `video --live`：明确阻断为 `video_live_provider_not_implemented`，不得调用 provider 或写成功产物。

图片 runner 的自动串接仍未实现，但当前已存在手工 evidence 闭环：image ProviderOutputEnvelope 可以进入 `ProviderArtifactStagingManifest`，再由 `ProviderArtifactPromotionReport` 显式阻断。该闭环目前用于证明低质量图片候选不会直接进入 runtime、published media 或世界状态。

真实视频 provider adapter、图片后处理、media gate 自动执行、staging / promotion 自动串接和后端自动后台执行器仍是后续任务。P1-A 图片 -> 视频 -> 关键帧 -> atlas 管线目前只获得 provider adapter runner 的安全边界，不等于真实图生视频 provider 已接入。

## ProviderOutputEnvelope

真实 provider 执行器的下一层落点是 `ProviderOutputEnvelope v0.1`：

```text
shared/schemas/provider_output_envelope.v0.1.schema.json
tools/dev/validate_provider_output_envelope.py
docs/PROVIDER_OUTPUT_ENVELOPE_V0_1.md
```

它定义“provider 调用之后允许保留什么”，而不是“如何调用 provider”。允许保存：

- 脱敏 request / result summary。
- source run、schedule item、object ref。
- 本地 artifact refs。
- schema / semantic / media / human review gate 状态。
- activation gate 阻断原因。

禁止保存：

- prompt 正文。
- provider 响应正文。
- secret、token、API key。
- full trace 或 raw JSON。
- review-only 直接 runtime-ready 的声明。

因此真实 executor 的最小顺序应是：

```text
live executor guard
  -> GenerationExecutorRunRequest
  -> ProviderExecutionAuthorization
  -> ProviderAdapterExecutionReceipt
  -> ProviderOutputEnvelope
  -> ProviderArtifactStagingManifest
  -> validator / media gate / semantic gate
  -> ProviderArtifactPromotionReport
  -> runtime package or WorldStateDeltaTransaction
```

`ProviderArtifactStagingManifest` 只登记从 envelope 输出 refs 转入本地审查暂存区的候选文件。它不是 runtime package，不写世界状态，也不能让 review-only artifact 被前端或战斗运行时直接消费。

后端 `stage-provider-artifacts` fixture worker 也必须先看到当前 session / latest run 已登记与 `ProviderOutputEnvelope.source.schedule_item_id` 相同的 `generation_executor_run_request`，已登记与 `ProviderOutputEnvelope.provider_call.authorization_ref` 相同的 `ProviderExecutionAuthorization`，并且已有同 `schedule_item_id` / `authorization_ref` 的 `ProviderAdapterExecutionReceipt`。如果缺少匹配请求包、匹配授权记录或匹配 adapter 回执，接口返回 409，避免 ProviderOutputEnvelope / staging / promotion report 绕过 dry-run worker、live executor guard、执行请求边界、显式授权边界和 adapter 边界，或挂到错误的调度项下。

`stage-provider-artifacts` 的默认 fixture profile 仍登记通用 `blocked_review_required` 示例。传入 `artifact_profile=image_failure` 时，它会登记 image ProviderOutputEnvelope、image ProviderArtifactStagingManifest 和 image ProviderArtifactPromotionReport，并要求调用方先用匹配的 image `authorization_ref` 完成授权和 adapter receipt。该 profile 用于 Studio / evidence 证明差图在后端 ledger 中也会收束为 `validation_failed` / `blocked_validation_failed`，不进入玩家 runtime。

后端还提供一个最小编排入口：

```text
POST /api/sessions/{session_id}/generation-schedule/workers/run-fixture-executor-chain
```

它会在缺少 run 时创建一条 session 级 scheduler run，然后按固定顺序串接 `dry-run-step -> live-executor-guard -> prepare-executor-request -> grant-provider-authorization -> run-provider-adapter-fixture -> stage-provider-artifacts`。该入口默认从所选 `artifact_profile` 的 ProviderOutputEnvelope fixture 反推 `schedule_item_id` 与 `authorization_ref`，避免把 provider artifact 挂到错误调度项下；如果调用方显式传入不匹配的 `schedule_item_id` 或 `authorization_ref`，接口返回 409。

该入口只是 review-only 的执行器壳，用于证明正式后台执行器的状态顺序、授权链、adapter 边界、staging 和 promotion 阻断可以被一次性编排。它仍不读取 `.env`、不调用 provider、不保存 prompt / provider 正文、不写世界状态、不激活 runtime。

`ProviderArtifactPromotionReport` 是 staging 之后的显式晋升/阻断报告。它可以允许后续构建器生成 runtime package 或 WorldStateDeltaTransaction，也可以阻断候选继续前进；但报告本身仍不修改 runtime、published media 或世界状态。

图片候选的当前示例使用更严格的失败路径：provider adapter 下载出的本地 PNG 可以被登记为 image candidate，但如果 media gate / semantic gate 判断其不符合地图质量、路径、塔位、目标或世界观约束，staging 与 promotion report 会以 `validation_failed` / `blocked_validation_failed` 收束，作为负样本 evidence，而不是可发布素材。

## Campaign Router 接入

当前后端已经提供最薄的战役路由层：

```http
GET /api/sessions/{session_id}/campaign-router
POST /api/sessions/{session_id}/campaign-router/prefetch-next
POST /api/sessions/{session_id}/campaign-router/prefetch-next-dispatcher-drain
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

`prefetch-next-dispatcher-drain` 保留旧入口，同时提供更强的 review-only 后台预取证据：它会调用 bounded dispatcher drain，默认 `max_items = 2`，把多个 queued provider-review 项推进到 receipt / envelope ledger 边界。下一节点只作为触发上下文，不作为 scheduler queue 的定向过滤器；drain 仍按 Generation Scheduler 的 eligible queue 顺序处理。

该入口拒绝 `schedule_item_id`、`authorization_ref`、`artifact_profile` 和本地导入路径，避免路由层把授权或 provider artifact 错挂到多个调度项。它仍不读取 `.env`，不调用 provider，不 staging，不 promotion，不 complete queue item，不写世界状态，不激活 runtime。

边界保持不变：

- 不读取 `.env`。
- 不调用 provider。
- 不创建新内容。
- 不写世界状态。
- 不激活预取候选。
- 只复用当前已审计划包和 dry-run 报告，生成 session 级调度运行证据。
