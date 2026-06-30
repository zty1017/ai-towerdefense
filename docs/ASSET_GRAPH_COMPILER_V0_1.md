# AssetGraph Compiler v0.1

Last updated: 2026-06-30

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

2026-06-30 的真实图像烟测确认：媒体 DAG 不能只包含 `generate_image`。
同一个防御塔候选在 Agnes / GLM / GLMFree 上都能生成图片，但原始产物可能包含背景、水印、
错误文件扩展名或不适合直接作为 sprite 的构图。因此媒体资产至少需要分层：

```text
RawGeneratedImage
  -> DetectFormat / NormalizeFormat
  -> WatermarkDetect
  -> VisualIdentitySpec
  -> QualityReport
  -> ConsistencyReport
  -> VisionReview
  -> PromptRepairPlan
  -> RegenerateFailedRoles
  -> MergeRepairedSequence
  -> Review / Select
  -> BackgroundRemoval
  -> CropAndPad
  -> NormalizeCanvas
  -> AssignAnchor
  -> SpriteSheetPack / AtlasJsonBuild
  -> PublishedMediaManifest
```

第一版实现可以先保留 stub 链路，但节点命名和 trace 边界应按真实后处理链路设计。
`icon`、`tower_sprite`、`battle_preview`、`animation_card` 应作为不同媒体角色处理，
不能用一个 prompt 同时承担“可抠图塔体”和“战斗展示图”。

2026-06-30 已新增视觉模型审查节点：`media.review_with_vision_guarded`。
它只允许在 `live` mode 下执行，且必须显式设置 `allow_live_provider_call: true`。
该节点读取本地 raw media 图片、VisualIdentitySpec、规则质量报告和规则一致性报告，
输出 `media_vision_review_report.v0.1`。它用于检查规则版无法确认的内容：

- 可读文字 / 伪文字 / 数字。
- 水印或模型标识。
- 多个媒体角色是否仍是同一个主体。
- 敌人、场景和构图是否符合世界书语义。
- 图片是否符合 `icon`、`ui_card`、`effect_preview` 等角色。

重要约束：`MediaConsistencyReport` 的高分只说明元数据、尺寸、provider / model 和 prompt 链路一致，
不能证明图片语义可用。`MediaVisionReviewReport.status = failed` 时，媒体不得进入 locked / runtime package。

2026-06-30 已新增确定性修复节点：`media.build_prompt_repair_plan` 和 `media.merge_repaired_sequence`。
前者把视觉审查失败原因转成 `media_prompt_repair_plan.v0.1`，后者把“复用通过角色 + 替换失败角色”
合并成新的完整 `raw_media_sequence`。

修复链路的关键经验：

- repair plan 可以保留完整诊断、失败原因和负面约束。
- 真正发送给图像 provider 的 prompt 必须短、正向、provider-safe。
- 详细负面词可能触发 provider 内容策略，不能把审查报告原文直接拼进图像 prompt。
- `roles: repair_failed` 只重生成 `target_roles`，并允许 target 为空时 no-op 通过。

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

## 11. 媒体后处理节点是 AssetGraph 一等节点（已确认）

媒体后处理不是临时补丁，而是 AssetGraph 的一等节点类别。

AI 生成图不能直接进入 runtime package。它必须经过显式的后处理与发布流程，才能成为前端可加载的已锁定媒体资产。

### 11.1 媒体三层结构

```text
raw_media
  AI 生成或外部导入的原始图片 / 视频 / 音频。
  不可被 runtime package 引用。
  不可暴露给玩家侧。

processed_media
  经过裁剪、抠底、归一化、锚点对齐等中间处理的媒体。
  仍不可被 runtime package 直接引用。
  可以被媒体子图内部节点之间传递。

published_media
  已打包、已签名（v0.2 起）、已分配本地 /assets/ 路径的发布态媒体。
  只有 published_media 可以出现在 runtime_public artifact 中。
  只有 published_media 可以被前端运行时加载。
```

### 11.2 MVP 内的轻量流程

MVP 不实现完整媒体后处理管线。MVP 内只做：

```text
validate
  -> normalize（轻量归一化，例如尺寸 / 命名 / 路径）
  -> vision_review（live，可选但强烈建议，用于关键素材）
  -> prompt_repair / regenerate_failed_roles / merge_repaired_sequence（按需）
  -> publish（分配 /assets/ 路径，写入 published_media manifest）
  -> fallback（如果上游缺失或失败，使用占位图标 / 统一 sprite）
```

对应已注册节点：`media.publish_stub_manifest`。

`media.publish_stub_manifest` 接受 raw_media_metadata（stub），产出一个 published_media manifest（stub）。它不调用真实图像处理，只用占位路径与 fallback 标记。

关键媒体的审查节点：

```text
media.build_visual_identity_spec
media.check_quality
media.check_consistency
media.review_with_vision_guarded
media.build_prompt_repair_plan
media.merge_repaired_sequence
```

其中 `media.review_with_vision_guarded` 会调用视觉模型；其他节点为确定性节点。它们默认不进入玩家运行时包，只作为编译证据和素材门禁。

### 11.3 MVP 后第一梯队节点

MVP 跑通后，按以下顺序补齐真实媒体后处理节点：

```text
remove_background      抠底 / 去背景
crop_and_pad           裁剪与留白
normalize_canvas       画布尺寸归一化
assign_anchor          锚点 / 站位点对齐
pack_sprite_sheet      打包 sprite sheet
build_atlas_json       生成 atlas 元数据 JSON
```

这些节点在 v0.2 进入 NodeRegistry，并接受 `processed_media` 作为输入、产出 `processed_media` 或 `published_media`。

### 11.4 媒体子图默认异步

媒体后处理子图默认异步执行，不阻塞 gameplay package 发布。

```text
gameplay package 构建
  -> 不等待媒体子图
  -> 媒体子图在后台推进
  -> 媒体 published 后，下一次 runtime package 构建再纳入

如果媒体子图未完成或失败：
  runtime package 使用 fallback 占位媒体
  不阻塞战斗加载
  失败信息进入内部 trace 与证据导出
```

这意味着：

- `runtime.build_package_stub` 不依赖 `media.publish_stub_manifest` 完成。
- 媒体缺失时使用 fallback 占位。
- 媒体子图的 trace 独立记录，可供证据导出读取。
