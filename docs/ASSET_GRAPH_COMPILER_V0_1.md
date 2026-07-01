# AssetGraph Compiler v0.1

Last updated: 2026-07-01

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

v0.1 的外层 WorkflowGraph 只要求 DAG，不支持图级循环。

后续如果需要 agent loop，应封装为单个 AgentNode 的内部实现，并显式声明最大迭代次数、工具权限、停止条件、失败回退和 trace 脱敏策略。也就是说，外层仍是可验证 DAG，内层可以是有界 ReAct。

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

### 4.1 自由输入到受控编译图

2026-07-01 确认：玩家自然语言不能直接进入 Proposal、图像生成或战斗执行层。

AssetGraph 需要把自由输入先转成隐藏中间表示，再由确定性合法化层裁剪到当前版本可执行的设计空间。

协议图：

```text
PlayerUtterance
  -> intent.parse_player_utterance_guarded
  -> asset.build_design_spec_guarded
  -> asset.legalize_design_spec
  -> asset.build_asset_plan
  -> proposal.build_from_legalized_spec
  -> proposal.validate
```

其中：

- `intent.parse_player_utterance_guarded` 和 `asset.build_design_spec_guarded` 可以调用 LLM，但只能输出隐藏结构化产物。
- `asset.legalize_design_spec` 必须是确定性硬门禁，负责冲突检测、降维映射、字段补全、预算裁剪和 fallback。
- `asset.build_asset_plan` 把一个资产拆成 gameplay、presentation、media、runtime metadata 等子产物。
- `proposal.build_from_legalized_spec` 生成玩家可见研发方案，但不携带 provider、prompt、trace 或 runtime 完整规则。

详细产品和工程边界见：

```text
docs/FREE_INPUT_CONTROLLED_COMPILATION_V0_1.md
```

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

### 6.3 LLM + ReAct 控制 DAG，而不是替代 DAG

确认原则：

```text
DAG 是编译运行时。
LLM + ReAct 是规划器、调度器和修复器。
```

危险路径：

```text
玩家需求 -> LLM 一边想一边随意调用工具 -> 凑出素材
```

该路径不可复现、难调试、成本不可控，也不适合比赛 Demo 和玩家 runtime。

推荐路径：

```text
玩家需求
  -> Intent Parser
  -> DesignSpec
  -> Legalizer
  -> 选择对象级 DAG 模板
  -> DAG Executor
  -> Validators
  -> 有限 ReAct Repair Agent
  -> Runtime Bundle
```

MVP 只允许 LLM 从已注册对象级模板中选择：

```text
TowerCompileGraph
SupportItemCompileGraph
TemporaryModCompileGraph
IntelAssetCompileGraph
SkillVFXCompileGraph
IconCompileGraph
MapModifierCompileGraph
```

对象级模板可以包含局部分支，但分支条件必须来自 `LegalizedDesignSpec` 或 `AssetPlan`，不能来自 LLM 运行时即兴判断。

ReAct Repair Agent 只在 validator 返回失败或警告时触发，且只能使用有限 action set：

```text
inspect_spec
inspect_artifact
inspect_validation_report
patch_spec
patch_prompt
rerun_node
increase_candidates
replace_with_template
split_asset_layer
fallback_to_preset
accept_with_warning
abort_compile
```

图级约束：

- 外层仍然是 DAG。
- ReAct 只能封装在单个 AgentNode 或修复子图内。
- 必须声明最大迭代次数、最大 provider 调用、最大执行时间和 fallback。
- 修复动作必须产生结构化 patch / rerun plan，不能直接改 runtime package。
- 修复后的图或参数必须再次通过 workflow 校验。

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
- 图级循环 agent graph
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

MVP 内先实现 PNG v0.1 媒体后处理管线。它不等于完整美术生产管线，但已经能把受控 PNG
素材转成前端可加载的 published media。

```text
validate
  -> remove_background（纯色 / 近纯色 matte 背景抠透明）
  -> crop_and_pad（按 alpha bbox 裁切并留白）
  -> normalize_canvas（方形补边 / bottom-center 对齐）
  -> assign_anchor（sprite 默认 bottom_center，UI 图默认 center）
  -> pack_sprite_sheet（横向 PNG atlas + JSON frames）
  -> vision_review（live，可选但强烈建议，用于关键素材）
  -> prompt_repair / regenerate_failed_roles / merge_repaired_sequence（按需）
  -> publish（分配 /assets/ 路径，写入 published_media manifest）
  -> runtime_readiness（检查透明度、anchor、atlas、hash、/assets 引用）
  -> fallback（如果上游缺失或失败，使用占位图标 / 统一 sprite）
```

PNG v0.1 的已注册节点仍沿用旧名，避免打断已有 workflow：

```text
media.remove_background_stub
media.crop_and_pad_stub
media.normalize_canvas_stub
media.assign_anchor_stub
media.pack_sprite_sheet_stub
media.build_atlas_json_stub
```

这些节点现在会写真实 PNG / atlas JSON / published manifest。当前限制：

- 只支持 8-bit、非隔行 RGB/RGBA PNG。
- 适合纯白、纯黑、纯灰或近纯色背景的 `sprite_source` / `cutout_source`。
- 不支持 JPEG/WebP 转 PNG；这需要 Pillow 或浏览器侧工具补齐。
- 不支持复杂背景自动抠图；这需要 rembg、视觉分割模型或人工处理。
- 不负责生成攻击特效；特效应优先走 visual recipe 或单独透明特效层。

关键媒体的审查节点：

```text
media.build_visual_identity_spec
media.check_quality
media.check_consistency
media.review_with_vision_guarded
media.build_prompt_repair_plan
media.merge_repaired_sequence
media.check_runtime_readiness
```

其中 `media.review_with_vision_guarded` 会调用视觉模型；其他节点为确定性节点。它们默认不进入玩家运行时包，只作为编译证据和素材门禁。

`media.check_runtime_readiness` 是发布后硬门禁：它不判断审美，只检查 published PNG、`/assets/generated/...`、sha256、透明度、主体 bbox、anchor、texture key 和 atlas frame。它回答的是“前端是否可以直接加载并摆放这个素材”。

### 11.3 图片到视频帧序列路线（已固化）

Agnes 等图像 provider 生成的白底图可以作为母图，不必强行要求它一次性成为最终 sprite。
当前路线固化为：

```text
raw generated image
  -> animation seed
  -> image-to-video
  -> extract keyframes
  -> select keyframes
  -> batch matte removal / cutout
  -> frame alignment
  -> sprite sheet / atlas
  -> animation_states
  -> runtime_readiness
```

对应协议节点：

```text
media.generate_video_from_image_guarded
media.extract_video_keyframes
media.select_keyframes
media.postprocess_frame_sequence
```

这条路线的完整决策见：

```text
docs/VIDEO_FRAME_ASSET_PIPELINE_V0_1.md
```

约束：

- 图生视频调用只能在 `live` mode 下执行，并需要 `allow_live_provider_call: true`。
- provider 如果要求公网图片 URL，该 URL 只能作为 provider 输入和内部 trace 证据，不得进入 runtime_public。
- 视频产物必须先下载到本地 artifact store，再抽帧。
- 抽帧结果仍属于 `raw_media`，不能直接给前端。
- 只有经过批量抠图、帧间对齐、atlas 打包和 runtime readiness 的 published media 才能进入 runtime package。

### 11.4 MVP 后第一梯队节点

MVP 跑通后，按以下顺序补齐更强媒体后处理节点：

```text
remove_background      抠底 / 去背景
crop_and_pad           裁剪与留白
normalize_canvas       画布尺寸归一化
assign_anchor          锚点 / 站位点对齐
pack_sprite_sheet      打包 sprite sheet
build_atlas_json       生成 atlas 元数据 JSON
```

PNG v0.1 已覆盖其中最基础的路径；v0.2 需要把节点名从 `_stub` 迁移到正式名，并补齐 JPEG/WebP、缩放重采样、复杂背景抠图和多帧动画。

### 11.5 媒体子图默认异步

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

## 12. AgentNode 与有界 ReAct（已确认）

现代 agent 系统常见的形态不是“纯自由 agent”，也不是“纯 DAG”，而是：

```text
外层 WorkflowGraph / AssetGraph
  -> 负责确定性编排、缓存、并发、校验、回放、失败恢复

内层 AgentNode
  -> 在单个节点内部执行有界 ReAct 循环
  -> 查询工具 / 观察结果 / 修复候选 / 选择下一步
  -> 只输出结构化 artifact
```

因此本项目采用混合模式：

```text
AssetGraph = 可验证图编排
AgentNode = 有预算、有工具白名单、有输出 schema 的局部 ReAct
Compiler Runtime = 图执行器 + checkpoint + trace + artifact store
```

关键原则：

1. 外层 `WorkflowGraph` 继续保持 DAG，便于验证、缓存和回放。
2. ReAct 循环只能存在于 `AgentNode` 内部，不能跨节点自由跳转。
3. `AgentNode` 不能直接写 `runtime_public` artifact。
4. `AgentNode` 的输出必须进入后续 schema 校验、simulation、评分或审查节点。
5. 玩家侧永远不展示 provider、schema、prompt、raw trace、工具日志等技术词。
6. Studio / 演示证据可以读取脱敏后的 trace，用于证明 AI 编译管线真实运行。

### 12.1 AgentNodeContract

新增机器可读合约：

```text
shared/schemas/agent_node_contract.v0.1.schema.json
```

它规定：

- `agent_kind`：资产编译、媒体修复、世界演化、候选选择、工具开发等。
- `runtime_modes`：只允许 `studio` / `live`，不进入 deterministic mock 路径。
- `loop_policy`：`bounded_react`、最大 step、最大工具调用、最大耗时、停止条件。
- `provider_policy`：是否允许真实 provider 调用、主 provider、fallback provider、输出预算。
- `tool_policy`：工具白名单和禁止动作。
- `input_artifacts`：可读取的结构化输入。
- `output_artifact`：唯一结构化输出及其 schema，且 `runtime_public=false`。
- `failure_policy`：预算耗尽、schema 失败、工具失败时如何回退。
- `trace_policy`：记录哪些步骤、哪些字段必须脱敏、trace 不进入玩家侧。

示例：

```text
examples/asset_graph/asset_compile_react_agent_node.contract.json
```

### 12.2 第一批适用位置

MVP 后优先把 AgentNode 用在两个位置：

```text
asset_compile_react_node
  -> 玩家构想 + 世界状态 + 玩法约束
  -> 查询材料 / NPC / 技术 / runtime 能力
  -> 产出 CompiledAssetCandidate
  -> 后接 validate / simulate / score

media_repair_react_node
  -> 读取 media quality / consistency / vision review
  -> 决定复用哪些图、重生成哪些图、如何改 provider-safe prompt
  -> 产出 MediaPromptRepairPlan 或 repaired raw_media sequence
  -> 后接 media processing / vision review
```

后续再扩展到：

- `world_delta_react_node`：根据战斗结果和进度生成服务玩法的世界增量。
- `candidate_selection_react_node`：多 provider / 多候选统一比较，选择默认候选。
- `tool_development_agent_node`：开发者模式下尝试生成新节点或新 workflow，但必须走测试、审查和注册流程。

### 12.3 与纯 DAG 的关系

外层仍然是：

```text
proposal
  -> agent.asset_compile_react
  -> validate_candidate
  -> simulate_candidate
  -> score_candidate
  -> media_generate
  -> media_postprocess
  -> evaluate_promotion_policy
  -> lock_manifest
  -> runtime_package
```

其中 `agent.asset_compile_react` 内部可以循环：

```text
think
  -> query_world_state
  -> query_runtime_capabilities
  -> draft_candidate
  -> validate_candidate
  -> repair_candidate
  -> stop
```

但这个循环只出现在节点内部 trace 中。对外部 workflow 来说，它仍然是一个普通节点：输入 artifact，输出 artifact，失败或成功。

### 12.4 MVP 实现顺序

短期不需要立刻实现完整 agent runtime。建议顺序：

1. 先维护 `AgentNodeContract` schema 和示例。
2. 给现有 `asset.compile_with_llm_guarded` 增加“准 AgentNode”输入压缩和多轮修复接口。
3. 把媒体 repair 现在的 deterministic plan 升级为可选 `media_repair_react_node`。
4. 执行器层增加 agent step trace，但默认只写脱敏摘要。
5. 再考虑真正支持 checkpoint、resume、human-in-the-loop。

## 13. Asset Promotion Policy（已确认）

玩家一次构想必须尽量得到可战斗资产。因此资产交付不能依赖单次图片生成成功。

新增节点：

```text
asset.evaluate_promotion_policy
```

新增报告：

```text
shared/schemas/asset_promotion_report.v0.1.schema.json
```

它把资产交付拆成两层：

```text
gameplay_core
  -> validation / simulation / score
  -> 决定是否有可玩的数值、效果、部署规则和 visual_recipe

media_skin
  -> runtime_readiness / vision_review / consistency
  -> 决定是否使用 AI 生成媒体，还是回退到确定性 fallback skin
```

输出状态：

```text
runtime_ready   gameplay_core 与 media_skin 都可用
fallback_ready  gameplay_core 可用，media_skin 缺失或失败，使用 fallback skin
preview_only    需要审查，暂不进入战斗
failed          gameplay_core 不可用，不能交付给玩家
```

硬规则：

- `failed` 只应该由 gameplay_core 阻断触发，例如 candidate validation 失败或严重 simulation flag。
- 图片生成、抠图、atlas、vision review 失败不能直接阻断玩家流程；只要 gameplay_core 可用，就应进入 `fallback_ready`。
- `fallback_ready` 必须带 `fallback_media_strategy`，前端或 runtime package builder 可以使用 deterministic shape sprite、模板 icon 和 visual recipe。
- 媒体管线可在后台继续 repair / regenerate，成功后再升级到 `runtime_ready`。
