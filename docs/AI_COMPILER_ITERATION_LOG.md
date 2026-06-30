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

## 4. 下一步建议

短期最值得继续做：

1. 给 `CompiledAssetCandidate` 增加更严格的 asset-type-specific schema。
2. 把 `simulation_focus` 纳入 Studio/证据导出。
3. 为 `support_item`、`temporary_mod`、`intel_asset` 各做一条 RuntimePackage / 前端消费示例。
4. 用这些新对象继续跑媒体生成，但按对象类型拆分媒体角色：`icon`、`battle_preview`、`ui_card`、`effect_preview`。
5. 增加“候选评分器”：综合 validation、simulation、世界书一致性、媒体可生成性，选出默认候选。
