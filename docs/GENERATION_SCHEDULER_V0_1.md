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

runner 默认 `fixture` dry-run，不读取 `.env`，不调用 provider。显式 `--mode llm_text --live` 时才允许调用 `tools/llm/adapter.py` 中的 LLM profile，并且仍只写入 redacted summary artifact、`ProviderAdapterExecutionReceipt` 和 `ProviderOutputEnvelope`。图片 provider adapter 已在工具层以显式 `--mode image --live` 形式接入；视频、媒体后处理和 media gate 不属于 runner 当前自动能力。

后端已提供 runner dry-run bridge：

```text
POST /api/sessions/{session_id}/generation-schedule/workers/run-provider-adapter-runner-fixture
```

该入口要求当前 session / latest run 已经存在匹配的 `GenerationExecutorRunRequest` 和 `ProviderExecutionAuthorization`，然后复用工具层 runner 的 dry-run artifact builder 生成 `ProviderAdapterExecutionReceipt` 与 `ProviderOutputEnvelope`，并把二者登记到 `generation_artifact_ledger`。它不会自动 staging、promotion、complete queue item、写世界状态或激活 runtime；队列仍停在 review / promotion 前。

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

图片 runner 的自动串接仍未实现，但当前已存在手工 evidence 闭环：image ProviderOutputEnvelope 可以进入 `ProviderArtifactStagingManifest`，再由 `ProviderArtifactPromotionReport` 显式阻断。该闭环目前用于证明低质量图片候选不会直接进入 runtime、published media 或世界状态。

视频 adapter、图片后处理、media gate 自动执行、staging / promotion 自动串接和后端自动后台执行器仍是后续任务。

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
