# AssetGraph Compiler v0.1

Last updated: 2026-06-29

## 1. 定位

AssetGraph Compiler 是 AI 资产编译器的底层工作流系统。

它借鉴 ComfyUI / Node-RED 的节点图思想，但目标不是做一个可视化 UI 画布，而是建立一套：

```text
可复用节点
  + 机器可读 workflow graph
  + AI 可自主编排
  + 可复现 execution trace
  + 可测试 / 可 debug 的游戏资产编译管线
```

玩家侧不需要看到节点图。玩家看到的是：

```text
输入想法 -> 研发方案 -> 编译结果 -> 进入战斗
```

开发者 / studio_mode 看到的是：

```text
用了哪些节点
每个节点输入输出是什么
哪个 provider 被调用
哪里校验失败
哪里 fallback
模拟报告是什么
```

## 2. 为什么需要节点图

如果 AI 编译器只是一个大函数，失败时很难判断问题来自：

- prompt
- provider
- JSON 解析
- Schema
- effect 白名单
- 预算规则
- 世界书一致性
- 数值模拟
- 图像生成
- 文件缓存
- 人工导入

节点图可以把这些步骤拆开。

好处：

1. 每个节点可单测。
2. 整张图可集成测试。
3. 每次执行可生成 trace。
4. 失败能定位到具体节点。
5. 节点输出可以缓存和复用。
6. AI 可以只改编排，不直接改底层代码。
7. 后续 AI 写新节点时，可以走提案、测试、注册流程。

## 3. 核心概念

### 3.1 NodeRegistry

节点注册表。

记录系统有哪些节点、输入输出 schema、允许模式、是否调用 provider、是否有副作用、实现位置和版本。

### 3.2 WorkflowGraph

工作流图。

由节点和边组成。边定义数据如何从一个节点流向另一个节点。

v0.1 只要求 DAG，不支持循环。后续如果需要 agent loop，要显式声明最大迭代次数和停止条件。

### 3.3 WorkflowNode

图中的节点实例。

同一个 `node_type` 可以在一张图里出现多次，但每个实例有自己的 `id` 和参数。

### 3.4 ExecutionTrace

执行记录。

记录每个节点：

- 输入摘要
- 输出摘要
- 开始 / 结束时间
- 状态
- 错误
- provider 调用
- fallback
- 产物路径

## 4. v0.1 第一条固定图

当前 mock pipeline 可以表达为：

```text
ProposalJson
  -> ValidateProposal
  -> MockCompileProposal
  -> ValidateAssetCandidate
  -> SimulateAssetCandidate
  -> PipelineReport
```

对应现有脚本：

| 节点 | 脚本 |
|---|---|
| `validate_proposal` | `tools/content_pipeline/validate_proposal.py` |
| `mock_compile_proposal` | `tools/content_pipeline/mock_compile_proposal.py` |
| `validate_asset_candidate` | `tools/content_pipeline/validate_asset_candidate.py` |
| `simulate_asset_candidate` | `tools/content_pipeline/simulate_asset_candidate.py` |
| `run_mock_pipeline` | `tools/content_pipeline/run_mock_pipeline.py` |

## 5. 节点分类

### 5.1 纯函数节点

不调用外部 provider，不产生不可逆副作用。

示例：

- `validate_proposal`
- `validate_asset_candidate`
- `budget_check`
- `effect_whitelist_check`
- `mock_simulation`
- `risk_score`

优先做成纯函数节点，因为它们最好测试。

### 5.2 LLM 节点

调用文本模型。

示例：

- `generate_proposal`
- `compile_gameplay`
- `generate_presentation`
- `worldbook_consistency_check`
- `schema_repair`
- `npc_review`

必须记录：

- provider
- model
- prompt 摘要
- token usage
- fallback 记录
- 原始输出路径
- 结构化解析结果

### 5.3 媒体节点

生成或处理图片、视频、音频等外部资产。

示例：

- `expand_image_prompt`
- `generate_image`
- `generate_video`
- `poll_media_job`
- `cache_media`
- `create_media_manifest`

必须记录：

- 输入 prompt
- provider / model
- 任务 ID
- 临时 URL
- 本地缓存路径
- reviewed / locked 状态

### 5.4 人类 / 审查节点

需要人工或 AI Reviewer 判断。

示例：

- `human_review`
- `ai_review`
- `lock_content`
- `reject_content`

MVP 可以先把这些作为状态节点，不做复杂 UI。

## 6. AI 自主编排

AI 自主编排分两层。

### 6.1 编排已有节点

这是优先实现方向。

AI 根据任务目标选择已有节点、填参数、连边。

示例：

```text
“生成一个高风险电力塔”
  -> generate_proposal
  -> risk_score
  -> compile_gameplay
  -> validate_asset_candidate
  -> simulate_asset_candidate
  -> generate_presentation
```

AI 可以生成 `WorkflowGraph` JSON，但执行前必须通过图校验。

### 6.2 提出或编写新节点

只允许在 `studio_mode`。

流程：

```text
AI 提出新节点
  -> node_proposal
  -> input_schema / output_schema 草案
  -> 测试样例
  -> 实现草案
  -> 人类 / AI Reviewer 审查
  -> 测试通过
  -> registered_node
  -> 可被 workflow graph 使用
```

玩家运行时不能直接注册新节点。

## 7. Graph 校验

WorkflowGraph 执行前必须检查：

- node id 唯一
- node_type 都存在于 NodeRegistry
- 边的 source / target 存在
- 没有循环
- 必需输入都有来源或默认值
- 输出 schema 与下游输入 schema 兼容
- 当前 mode 允许使用这些节点
- LLM / 媒体节点有 provider 策略
- 有副作用节点必须显式声明

## 8. Debug 与测试价值

节点图直接服务于测试和 debug。

### 8.1 节点单测

每个节点可以用 fixture 输入测试。

示例：

```text
validate_asset_candidate(valid_asset) -> passed
validate_asset_candidate(unknown_effect) -> failed
simulate_asset_candidate(pure_control_tower) -> balance_flags includes pure_control_requires_damage_partner
```

### 8.2 图集成测试

整张图用固定输入跑。

示例：

```text
light_slow_field.proposal.json
  -> mock graph
  -> compiled_asset.json
  -> simulation_report.json
  -> pipeline_report.json
```

### 8.3 Trace 回放

失败时可以从 trace 重新执行某个节点，而不是重新跑整条管线。

示例：

```text
node mock_compile_proposal passed
node validate_asset_candidate failed: unknown effect "time_freeze"
```

系统可以把失败内容交给 repair 节点修复。

## 9. v0.1 不做

- 可视化节点编辑器
- 用户拖拽连线
- 运行时动态注册新节点
- 循环 agent graph
- 分布式执行
- 并行调度优化
- 复杂权限系统

## 10. v0.2 建议

下一步可以落地：

- `shared/schemas/asset_graph.v0.1.schema.json`
- `shared/node_registry/nodes.v0.1.json`
- `examples/workflows/mock_asset_compile.workflow.json`
- `tools/content_pipeline/run_workflow.py`
- `tools/content_pipeline/validate_workflow.py`

这样现有脚本就可以从“顺序脚本”升级成“执行 graph JSON”。

