# AI 编译器迭代日志

Last updated: 2026-06-30

## 1. 本轮目标

本轮目标是用更多真实 LLM 调用测试 AI 编译器，而不是只验证单一防御塔。

测试对象覆盖：

| 对象类型 | 提案 | 目标 |
|---|---|---|
| `support_item` | `mirror_lure_trap.proposal.json` | 一次性支援/陷阱道具 |
| `temporary_mod` | `overload_chain_mod.proposal.json` | 高风险临时改造 |
| `intel_asset` | `shadow_tide_survey.proposal.json` | 战前/战中情报资产 |

## 2. 真实 LLM 迭代

### Round 1：方舟 DeepSeek Flash，旧 prompt

三类对象均生成成功并通过校验，但暴露了两个问题：

- 非塔类资产经常缺少 `base_stats` 和 `type_specific`。
- 旧 mock simulation 把所有对象都按“塔的 DPS / 漏怪数”评估，导致情报资产被误判为低效。

### Round 2：方舟 DeepSeek Flash，改进 prompt

改进后 prompt 明确要求不同 `asset_type` 填写不同结构：

- `support_item`: `deploy_cost`、`cooldown`、`use_count`、`cast_range`
- `temporary_mod`: `activation_cost`、`duration_seconds`、`cooldown`
- `intel_asset`: `action_cost`、`valid_turns`、`confidence`

结果明显改善：三类对象都开始生成对应的结构字段。

新暴露的问题：

- 支援道具候选把 `id` 写成了 `proposal_...`，会污染资产缓存和媒体命名。
- 临时改造可能只生成 `pierce_or_chain`，没有直接伤害；这在玩法上可能是“增强现有塔”，不应简单判无效。

### Round 3：方舟 GLM 5.2，改进 prompt + ID guardrail

三类对象均通过新 guardrail，并固化为示例：

```text
examples/compiled_assets/mirror_lure_trap.compiled_asset.json
examples/compiled_assets/overload_chain_mod.compiled_asset.json
examples/compiled_assets/shadow_tide_survey.compiled_asset.json
```

观察：

- GLM 5.2 输出的 `base_stats` / `type_specific` 更稳定。
- `temporary_mod` 更倾向生成完整风险/代价结构。
- `intel_asset` 的情报效果更丰富，能组合 `path_prediction`、`weakness_tag`、`countermeasure_hint`、`risk_modifier`。

## 3. 已落地的编译器改进

### 3.1 Prompt guardrail

`tools/llm/asset_candidate_prompt.py` 增加：

- `id` 不能复用 `proposal.id`。
- `id` 不能以 `proposal_` 开头。
- 不同 `asset_type` 的结构字段建议。

### 3.2 Validator guardrail

`tools/content_pipeline/validate_asset_candidate.py` 增加：

- 拒绝 `id` 以 `proposal_` 开头。
- 拒绝 `id == provenance.proposal_id`。

### 3.3 Asset-type-aware simulation

`tools/content_pipeline/simulate_asset_candidate.py` 升级到 `mock_sim_v0.2`：

- 新增 `asset_type`
- 新增 `simulation_focus`
- 新增 `utility_score`
- 情报资产不再因“没有直接伤害”被自动判低效。
- 临时改造可按“增强现有塔”的方式估算代理 DPS。
- `action_cost` 会按行动点稀缺性换算为模拟成本。

### 3.4 DAG 证据输出

新增三条 live compile workflow：

```text
examples/workflows/mvp_live_support_item_compile_guarded.workflow.json
examples/workflows/mvp_live_temporary_mod_compile_guarded.workflow.json
examples/workflows/mvp_live_intel_asset_compile_guarded.workflow.json
```

`report.pipeline_summary` 现在会额外汇总：

- `asset_type`
- `simulation_focus`
- `utility_score`
- `cost_efficiency`
- `estimated_dps`

这样 Studio/证据导出可以直接比较候选，而不必深入打开每个 simulation report。

## 4. 候选评分器与媒体角色迭代

### 4.1 CandidateScore v0.1

本轮新增 `candidate_score.v0.1`：

```text
tools/content_pipeline/score_asset_candidate.py
shared/schemas/candidate_score.v0.1.schema.json
```

评分维度：

| 维度 | 权重 | 含义 |
|---|---:|---|
| validation | 0.20 | 结构校验是否通过 |
| gameplay_fit | 0.20 | 是否符合 asset_type 应有字段和效果 |
| simulation | 0.20 | utility / DPS / cost efficiency / balance flags |
| world_fit | 0.15 | 是否有世界书、NPC、材料上下文，玩家文案是否无技术词 |
| media_readiness | 0.15 | 是否覆盖该 asset_type 所需媒体角色 |
| risk_control | 0.10 | 运行模式与风险是否匹配 |

推荐结果：

```text
reject
revise
generate_media
needs_review
promote_candidate
```

`asset.score_candidate` 已加入 AssetGraph，编译类 workflow 现在会输出 `score__candidate_score.json`，
`report.pipeline_summary` 会带上 `total_score` 和 `recommendation`。

真实工作流烟测：

```text
examples/workflows/mvp_live_support_item_compile_guarded.workflow.json
/tmp/live_support_compile_score_glm_check/mvp_live_support_item_compile_guarded/score__candidate_score.json
```

结果：`total_score=77.6`，`recommendation=generate_media`。说明结构和玩法已经可用，
但缺媒体时仍会被引导进入媒体生成阶段。

### 4.2 媒体角色自动选择

图像生成从固定 `icon/tower_sprite` 扩展为：

```text
icon
tower_sprite
ui_card
effect_preview
battle_preview
```

`roles: "auto"` 会按 asset_type 选择：

| asset_type | 默认媒体角色 |
|---|---|
| `tower_blueprint` | `icon`、`tower_sprite`、`battle_preview` |
| `support_item` | `icon`、`ui_card`、`effect_preview` |
| `temporary_mod` | `icon`、`ui_card`、`effect_preview` |
| `intel_asset` | `icon`、`ui_card`、`effect_preview` |

新增 workflow：

```text
examples/workflows/mvp_live_asset_media_auto_guarded.workflow.json
```

### 4.3 真实 Agnes 媒体烟测：折光诱饵陷阱

对 `examples/compiled_assets/mirror_lure_trap.compiled_asset.json` 使用 Agnes 真实生成：

```text
/tmp/live_asset_media_auto_support_agnes/mvp_live_asset_media_auto_guarded/generate_images__raw_media_sequence.json
/tmp/live_asset_media_auto_support_agnes/mvp_live_asset_media_auto_guarded/build_atlas__published_media_manifest.json
```

生成角色：

```text
icon
ui_card
effect_preview
```

结果观察：

- `icon` 语义准确，碎镜、灯芯灰和诱饵光源都清晰。
- `ui_card` 视觉表现强，但模型生成了中文伪文案，违反 `no text`，已进一步收紧 prompt。
- `effect_preview` 能表达诱饵吸引效果，但敌人偏人类士兵，已要求使用影潮生物或抽象敌影。
- published manifest 已保留 `media_role`，方便前端区分图标、卡图和预览图。
- runtime-public manifest 未泄漏 provider 临时 URL、prompt_summary 或 local_path。

评分变化：

| 状态 | total_score | recommendation |
|---|---:|---|
| 无媒体 | 71.2 | `generate_media` |
| 覆盖 `icon/ui_card/effect_preview` | 80.9 | `promote_candidate` |

## 5. 素材一致性与质量检查

本轮新增三类媒体审查产物：

```text
VisualIdentitySpec v0.1
MediaQualityReport v0.1
MediaConsistencyReport v0.1
```

对应实现：

```text
tools/media/media_review.py
shared/schemas/visual_identity_spec.v0.1.schema.json
shared/schemas/media_quality_report.v0.1.schema.json
shared/schemas/media_consistency_report.v0.1.schema.json
```

新增 AssetGraph 节点：

```text
media.build_visual_identity_spec
media.check_quality
media.check_consistency
```

新增工作流：

```text
examples/workflows/mvp_media_consistency_check.workflow.json
```

`mvp_live_asset_media_auto_guarded.workflow.json` 也已接入这三个旁路节点：生成图像后会同时产出
visual identity、quality report、consistency report，再继续进入 raw -> processed -> published 的媒体链路。

### 5.1 VisualIdentitySpec

`VisualIdentitySpec` 是每个资产的小型视觉设定稿。它从 `CompiledAssetCandidate` 中抽取：

- subject name
- asset_type
- identity tokens
- silhouette
- materials
- palette
- light effects
- required motifs
- forbidden elements
- role directives

它的作用是防止 `icon`、`ui_card`、`effect_preview` 各画各的。

### 5.2 MediaQualityReport

当前规则版会检查：

- 需要的媒体角色是否齐全。
- `media_role` 是否合法。
- 宽高是否存在且有效。
- 有 `local_path` 时读取文件头，检查 PNG/JPEG/WEBP/GIF 与扩展名是否一致。
- 标记 `ui_card` 需要 OCR 文本检测。
- 标记 `effect_preview` / `battle_preview` 需要水印与世界观语义复核。
- 标记 `tower_sprite` 需要背景和锚点复核。

它不会假装能完全理解图片内容。文字、水印和“敌人是否像影潮生物”仍需要视觉模型或人工复核。

### 5.3 MediaConsistencyReport

当前规则版会检查：

- 角色覆盖是否完整。
- 多张图是否来自同一 provider / model，避免风格漂移。
- 尺寸是否一致。
- `stable_internal_id` 是否以候选资产 ID 为前缀。
- `prompt_summary` 是否与视觉身份有基本链接。
- 质量报告是否要求进一步复核。

对真实 Agnes 生成的折光诱饵陷阱 raw media 进行检查：

```text
/tmp/real_mirror_quality.json
/tmp/real_mirror_consistency.json
```

结果：

```text
MediaQualityReport.status = needs_review
MediaConsistencyReport.status = needs_review
MediaConsistencyReport.consistency_score = 97.5
```

解释：角色覆盖、provider/model、尺寸和身份链接都一致；但 `ui_card` 仍需要 OCR 文本检测，
`effect_preview` 仍需要世界观语义复核。

## 6. Kimi 接入与真实资产编译闭环

本轮把方舟 Coding Plan 中的 Kimi 纳入统一 LLM adapter：

```text
ark_kimi_k2_6      -> kimi-k2.6
ark_kimi_k2_7_code -> kimi-k2.7-code
```

真实 smoke 结论：

- `kimi-k2.6` 普通 chat 可调用。
- `kimi-k2.6` 支持 `response_format=json_object` 结构化输出。
- `kimi-k2.7-code` 支持 `response_format=json_object` 结构化输出，更适合作为开发期编译器规则、Schema、DAG 节点和结构化资产转换候选。
- `kimi-k2.6` 会返回 `reasoning_content`；管线只能读取 `message.content`，不能把推理内容写入玩家侧产物。

新增 Kimi live workflow：

```text
examples/workflows/mvp_live_asset_compile_kimi_guarded.workflow.json
```

真实 AssetGraph 闭环结果：

```text
/tmp/live_asset_compile_kimi_check/mvp_live_asset_compile_kimi_guarded/
```

节点全部通过：

```text
source.load_json
proposal.validate
asset.compile_with_llm_guarded
asset.validate_candidate
asset.simulate_candidate
asset.score_candidate
report.pipeline_summary
```

Kimi 生成候选：

```text
id: asset_luminous_slow_tower
name: 光幕迟滞塔
asset_type: tower_blueprint
score: 72.9
recommendation: generate_media
balance_flag: pure_control_requires_damage_partner
```

质量判断：候选结构合法，世界观贴合度和玩法匹配度较好；但它仍是纯控场塔，不能独立击杀敌人，
因此应在玩家侧表现为“需要搭配伤害来源”的样品限制，而不是技术错误。

## 7. 视觉模型审查节点

本轮新增 `media.review_with_vision_guarded`，用于把本地生成图片、VisualIdentitySpec、
规则质量报告和规则一致性报告交给视觉模型审查。

新增文件：

```text
tools/media/vision_review.py
shared/schemas/media_vision_review_report.v0.1.schema.json
```

新增 / 更新节点与工作流：

```text
media.review_with_vision_guarded
examples/workflows/mvp_live_asset_media_auto_guarded.workflow.json
```

节点约束：

- 只在 `live` mode 可用。
- 必须设置 `allow_live_provider_call: true`。
- 默认视觉 profile 为 `glm_5v_turbo`，同时预留 `glmfree_4_6v_flash` 和 `agnes_multimodal_flash`。
- 输出 `media_vision_review_report.v0.1`，不保存 raw prompt、raw provider response 或 API key。

真实审查对象：

```text
/tmp/live_asset_media_auto_support_agnes/mvp_live_asset_media_auto_guarded/generate_images__raw_media_sequence.json
```

规则版审查结果：

```text
MediaQualityReport.status = needs_review
MediaConsistencyReport.status = needs_review
MediaConsistencyReport.consistency_score = 97.5
```

视觉模型审查结果：

```text
/tmp/real_mirror_vision_review_glm_5v.json
/tmp/live_media_vision_review_node_check/mvp_media_vision_review_existing/vision_review__media_vision_review_report.json
```

核心结论：

```text
MediaVisionReviewReport.status = failed
MediaVisionReviewReport.vision_score = 25.0
recommended_action = regenerate_media
```

视觉模型抓到了规则版无法确认的问题：

- `ui_card` 出现生成式伪文字 / 可读文字。
- `effect_preview` 中敌人被生成成现代人类士兵，不符合“影潮 / 抽象敌意轮廓”。
- `icon`、`ui_card`、`effect_preview` 的主体发生严重漂移：碎片、祭坛、鱼钩状晶体不是同一个小型陷阱。

决策：`MediaConsistencyReport` 分数高只能说明元数据和 prompt 链路一致，不能证明素材可用。
视觉审查失败时，候选不得进入 locked / runtime package，应回到 prompt 修订或重新生成媒体。

## 8. 媒体 Prompt Repair 与修复闭环

本轮新增确定性修复节点，把视觉审查失败原因转成下一轮图像生成可用的修复计划。

新增文件：

```text
tools/media/prompt_repair.py
shared/schemas/media_prompt_repair_plan.v0.1.schema.json
examples/asset_graph/mirror_lure_trap.media_vision_review.sample.json
```

新增 / 更新节点与工作流：

```text
media.build_prompt_repair_plan
media.merge_repaired_sequence
examples/workflows/mvp_media_prompt_repair.workflow.json
examples/workflows/mvp_live_asset_media_repair_guarded.workflow.json
```

`MediaPromptRepairPlan` 会输出：

- `target_roles`：需要重生成的媒体角色。
- `reuse_roles`：可以复用的媒体角色。
- `global_negative_constraints`：审查诊断用的全局负面约束。
- `role_repairs`：每个角色的失败原因、正向补充、构图约束和参考策略。
- `prompt_suffix_by_role`：可接回图像生成节点的修复 prompt 片段。

真实修复闭环：

```text
/tmp/live_media_repair_retry_safe_check_2/mvp_media_repair_retry_existing/
```

流程：

```text
原始 raw media
  -> vision_review failed / 65.0
  -> build_prompt_repair_plan
  -> regenerate_failed_roles(effect_preview)
  -> merge_repaired_sequence(icon + ui_card 复用，effect_preview 替换)
  -> vision_review_after_repair passed / 88.0
```

二次审查结果：

```text
MediaVisionReviewReport.status = passed
vision_score = 88.0
recommended_action = promote
```

修复后的 `effect_preview` 已移除现代人类士兵、文字和水印问题，主体也与镜片诱饵更一致。
剩余警告是画面缺少被影响目标，表现力可以继续增强，但已经不再阻塞 promotion。

重要实现经验：

- 详细失败原因可以保存在 repair plan 中。
- 直接发给图像 provider 的 prompt 必须更短、更正向、更安全。
- 负面词越多，越容易触发 provider content policy。Agnes 对一版 repair prompt 返回过：

```text
content_policy_violation
```

- 因此当前实现把 `provider-safe repair prompt` 与 `diagnostic repair plan` 分离：计划可以详细，
  生成 prompt 只描述“镜片装置、灯光环、暗雾、无文字、无 logo”等安全视觉目标。

## 9. PNG v0.1 像素级后处理管线

本轮把原先只改 JSON 的媒体后处理 stub，升级为可运行的 PNG v0.1 处理管线。

新增文件：

```text
tools/media/png_pipeline.py
```

能力范围：

- 纯 Python 读取 / 写入 8-bit、非隔行 RGB/RGBA PNG。
- 根据四角颜色估算 matte 背景，去除纯色 / 近纯色背景并写入 alpha。
- 根据 alpha bbox 裁切主体并留白。
- 方形画布归一，支持 bottom-center 对齐。
- 按媒体角色写入 anchor；sprite 默认 `bottom_center`，UI / preview 默认 `center`。
- 横向打包 PNG atlas，并生成 atlas JSON frames。
- 发布真实 `published_media_manifest`，包含 `/assets/generated/...` URL、sha256、anchor、atlas frame。

仍沿用旧节点名以兼容已有 workflow：

```text
media.remove_background_stub
media.crop_and_pad_stub
media.normalize_canvas_stub
media.assign_anchor_stub
media.pack_sprite_sheet_stub
media.build_atlas_json_stub
```

真实 deterministic smoke：

```text
/tmp/png_pipeline_run/tmp_png_processing_check/
```

验证内容：

- 输入：64x64 白底红色主体 PNG。
- `remove_background` 后：3489 个像素 alpha=0，607 个像素 alpha=255。
- `crop_and_pad` / `normalize_canvas` 后：输出 38x38。
- `assign_anchor`：`bottom_center`，pixel anchor `(19.0, 38.0)`。
- `build_atlas`：生成真实 `published/asset_test_sprite_icon.png`、`published/build_atlas__atlas.png`、`published/build_atlas__atlas.json`。
- published manifest 含真实 sha256 和 atlas frame。

当前限制：

- 不支持 JPEG/WebP 读取和转换。
- 不支持复杂背景抠图。
- 不做缩放重采样，只做裁切和补边。
- 不处理多帧动画的逐帧对齐。

因此现在已经可以自动产出“受控 PNG sprite_source / cutout_source”的前端可加载素材；
但 AI 自由生成的复杂场景图仍应作为 `ui_card` / `effect_preview`，不能直接当 runtime sprite。

## 10. AssetGraph + 有界 ReAct AgentNode 决策

本轮确认：AI 编译器不应走“纯自由 agent”，也不应被限制为“所有智能都必须是纯 DAG 节点”。

最终架构决策：

```text
外层 WorkflowGraph / AssetGraph
  -> 继续保持 DAG
  -> 负责缓存、校验、回放、失败恢复和证据 trace

内层 AgentNode
  -> 封装有界 ReAct 循环
  -> 可查询工具、观察结果、修复候选、选择下一步
  -> 只能输出结构化 artifact
```

新增 schema：

```text
shared/schemas/agent_node_contract.v0.1.schema.json
```

新增示例：

```text
examples/asset_graph/asset_compile_react_agent_node.contract.json
```

关键约束：

- 图级 workflow 仍然禁止循环。
- ReAct 只能在单个 AgentNode 内部运行。
- AgentNode 必须声明 max steps、max tool calls、max seconds、stop conditions。
- AgentNode 必须声明工具白名单和禁止动作。
- AgentNode 不能直接写 `runtime_public` artifact。
- AgentNode 输出必须经过 schema validation / simulation / score / review。
- trace 可以服务 Studio 和演示证据，但必须脱敏，不进入玩家侧。

第一批适用位置：

1. `asset_compile_react_node`：玩家构想 + 世界状态 + 玩法约束 -> `CompiledAssetCandidate`。
2. `media_repair_react_node`：视觉审查失败 -> 修复计划 / 重生成策略。
3. `world_delta_react_node`：战斗结果 -> 服务玩法进度的世界增量。

这意味着当前的 `asset.compile_with_llm_guarded` 和 `media.build_prompt_repair_plan`
可以作为准 AgentNode 的前身，后续逐步升级，不需要推翻现有 AssetGraph。

## 11. 媒体资产 runtime-ready 门禁

本轮继续优化图片资产质量，重点不是“更好看”，而是“几乎无人工干预地变成游戏可用素材”。

外部调研吸收：

- `rembg` 适合作为后续背景移除增强节点。
- `SAM 2` 适合后续复杂主体分割和多帧一致性处理。
- `ComfyUI` 的启发是节点化图像生成 / 后处理工作流，不一定需要 UI。
- Phaser 运行时更需要 texture、atlas、frame、anchor，而不是 provider 原图。

新增文档：

```text
docs/MEDIA_ASSET_QUALITY_PIPELINE_V0_2.md
```

新增代码：

```text
tools/media/runtime_readiness.py
tools/media/tests/test_runtime_readiness.py
shared/schemas/media_runtime_readiness_report.v0.1.schema.json
```

新增 AssetGraph 节点：

```text
media.check_runtime_readiness
```

它检查：

- published PNG 文件是否存在并可读。
- `/assets/generated/...` runtime 引用是否存在。
- sha256 是否匹配。
- sprite 是否有透明背景。
- 主体 bbox 是否过小或过满。
- 主体是否贴边。
- `tower_sprite` 是否使用 `bottom_center` anchor。
- `texture_key` / `atlas_frame` 是否存在。
- atlas image / descriptor 是否存在。

同时收紧了 `icon` / `tower_sprite` 的图像生成 prompt：

- 单一主体。
- 纯白 matte 背景。
- 无场景、无投影、无特效烘焙。
- 无文字、logo、水印。
- 特效后续走 visual recipe 或独立透明层。

已接入 runtime readiness gate 的 live workflow：

```text
examples/workflows/mvp_live_asset_media_guarded.workflow.json
examples/workflows/mvp_live_asset_media_auto_guarded.workflow.json
examples/workflows/mvp_live_asset_media_repair_guarded.workflow.json
```

关键结论：

- 语义一致性靠 vision review。
- 游戏可用性靠 runtime readiness。
- 两者都过，才能 promotion。
- 任一失败，进入 repair / regenerate / fallback。

## 12. 下一步建议

短期最值得继续做：

1. 给 `CompiledAssetCandidate` 增加更严格的 asset-type-specific schema。
2. 为 `support_item`、`temporary_mod`、`intel_asset` 各做一条 RuntimePackage / 前端消费示例。
3. 增加 `sprite_source` / `cutout_source` 专用媒体角色和 prompt。
4. 为媒体 repair loop 增加最多 N 次重试 / provider fallback 策略。
5. 增加候选排序 workflow：同一 proposal 多 provider 生成多个候选，统一评分后选择默认候选。
6. 把 score / media role / published media manifest / consistency report / vision review / repair plan 接到前端研发台和战斗 UI mock。
