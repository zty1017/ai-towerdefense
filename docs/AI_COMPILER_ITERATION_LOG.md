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

## 6. 下一步建议

短期最值得继续做：

1. 给 `CompiledAssetCandidate` 增加更严格的 asset-type-specific schema。
2. 为 `support_item`、`temporary_mod`、`intel_asset` 各做一条 RuntimePackage / 前端消费示例。
3. 接入视觉模型审查节点，真正检查文字、水印、敌人形态和风格一致性。
4. 增加候选排序 workflow：同一 proposal 多 provider 生成多个候选，统一评分后选择默认候选。
5. 把 score / media role / published media manifest / consistency report 接到前端研发台和战斗 UI mock。
