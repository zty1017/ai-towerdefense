# 运行时激活桥 v0.1

## 1. 定位

运行时激活桥负责把已经完成编译、校验和晋升审查的游戏对象，以会话级补丁形式装入玩家运行时。它不是新的 AI 编译器，也不替代既有 `RuntimePackage`、`LockedManifest`、`FrontendFeatureSnapshot` 或 `FrontendSurfaceContribution`。

当前契约分工如下：

- `RuntimePackage v0.1`：编译结果的运行时安全包。
- `BattleObjectCapability v0.1`：浏览器可解释执行的战斗对象能力子集。
- `RuntimeActivationReceipt v0.1`：最终 apply gate 的审计回执。
- `FrontendFeatureSnapshot / FrontendSurfaceContribution v0.1`：已激活内容投影到玩家界面的声明式贡献。
- `ActivatedRuntimeBundle`：基础运行包与当前会话有效补丁合并后的前端只读快照。

## 2. 核心原则

1. 生成完成不等于激活。
2. Provider 输出必须先经过 staging、promotion report、运行包构建和最终激活门。
3. 前端只解释白名单 ABI，不执行 AI 生成代码。
4. blocked 回执不得修改玩家运行时。
5. 激活按 `session_id + source_kind + source_id` 幂等。
6. 每次激活只写一个会话级运行补丁，不修改世界状态。
7. 回滚只撤销对应补丁，基础运行包和其他会话补丁不受影响。

## 3. 当前闭环

### 3.1 研发任务路径

```text
玩家确认试作
  -> ResearchJob 完成两个确定性 AssetGraph 工作流
  -> 产出 RuntimePackage 与 ExecutionTrace
  -> 战斗中的样品送达事件调用 apply gate
  -> 校验包结构、安全扫描、证据、Behavior ABI 与 published media
  -> 写入 runtime_activations
  -> 合并为 ActivatedRuntimeBundle
  -> 前端热更新工具栏、部署行为与媒体引用
```

MVP 的确定性研发工作流允许使用经过审查的安全 ABI 与 published media 兜底，但回执必须把对应门标记为 `degraded`。该兜底只服务当前可信工作流，不向真实 Provider 产物开放。

真实 Provider 路径必须携带 `ProviderArtifactPromotionReport v0.1`，并满足：

- `promotion_allowed=true`；
- promotion target 包含 runtime package；
- runtime package 本地路径和 sha256 与报告一致；
- 所有 `required_before_promotion=true` 的门均为 `passed`；
- gameplay 与 media 引用是本地、已发布且哈希匹配的产物。

### 3.2 Generation Scheduler 路径

Scheduler 的三步 readiness chain 仍然只写审阅证据：

```text
ProviderArtifactPromotionReport
  -> GenerationRuntimeBuildRequest
  -> GenerationRuntimeArtifactBuildReport
  -> GenerationRuntimeActivationAuthorization
```

它不会隐式激活任何内容。开发者明确调用 apply worker 后，系统才会逐跳验证：

- session、run、schedule item 是否始终一致；
- authorization -> build report -> build request -> promotion report 的 ledger id、source id 与类型是否一致；
- PromotionReport 与 build report 是否指向同一个本地 runtime package 路径和 `sha256`；
- 目标是否恰好为一个战斗 `RuntimePackage`，且没有夹带地图、世界事务、媒体发布或未解析目标；
- developer decision 是否为 `approved_for_manual_apply`；
- Provider 的 source、local ref、media、semantic、human review 与 simulation gate 是否通过；
- runtime package 的 session、schema、安全扫描、Behavior ABI 与 published media 是否在 apply 时再次通过。

全部通过后才写入 `runtime_activations` 和 `generation_runtime_activation_receipt` ledger，并投影为 `runtime_activated`。授权后修改目标引用、哈希或文件内容都会被拒绝。

## 4. 数据与 API

SQLite 表 `runtime_activations` 保存：

- 激活 ID、会话、来源、状态；
- `RuntimeActivationReceipt`；
- 声明式 `runtime_patch.battle_objects`；
- 创建、更新与回滚时间。

当前 API：

- `POST /api/sessions/{session_id}/research/jobs/{job_id}/activate`
- `GET /api/sessions/{session_id}/runtime/activations`
- `POST /api/sessions/{session_id}/runtime/activations/{activation_id}/rollback`
- `POST /api/sessions/{session_id}/generation-schedule/workers/apply-runtime-activation`

会话 reset 会清除该会话的激活记录。任何 API 都不能跨会话读取、激活或回滚补丁。

## 5. BattleObjectCapability 边界

v0.1 只允许：

- 对象类型：防御塔、临时陷阱、支援道具、场地装置；
- 放置模式：塔位、道路邻接、自由点、道路区域、范围点；
- 效果块：伤害、减速、光环、显形；
- 固定 UI surface 与 simulation hook 白名单；
- `/assets/` 下的 published media 引用。

它不允许脚本、组件代码、任意表达式、Provider 临时 URL、密钥、原始提示词或原始响应正文。

## 6. 当前限制

- 当前研发 API 仍是确定性 MVP 工作流；Scheduler 已有脱敏、可重复的 Provider PromotionReport 正向闭环样例，但不代表后台 live provider daemon 已完成。
- Scheduler v0.1 apply 只接受恰好一个战斗 `RuntimePackage`；地图、世界事务与媒体发布必须走各自专用 apply gate。
- Scheduler apply 不自动 complete queue item，避免把“运行时已生效”与“后台任务生命周期完成”混成一个事务。
- 激活只覆盖战斗对象；剧情、任务、随机事件和世界状态变化仍应分别走 FeatureSnapshot 与 WorldStateDeltaTransaction。
