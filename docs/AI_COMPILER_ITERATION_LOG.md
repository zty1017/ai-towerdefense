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

## 5. 下一步建议

短期最值得继续做：

1. 给 `CompiledAssetCandidate` 增加更严格的 asset-type-specific schema。
2. 为 `support_item`、`temporary_mod`、`intel_asset` 各做一条 RuntimePackage / 前端消费示例。
3. 增加媒体质量检测节点：文字/水印检测、格式识别、透明背景/裁切检查。
4. 增加候选排序 workflow：同一 proposal 多 provider 生成多个候选，统一评分后选择默认候选。
5. 把 score / media role / published media manifest 接到前端研发台和战斗 UI mock。
