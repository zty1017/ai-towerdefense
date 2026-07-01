# 多阶段内容生产包 v0.1

本文档说明 `build_multistage_content_pack.py` 的用途、边界和验收方式。

它不接入前端，不生成战斗 runtime package，也不会把候选资产自动晋升为默认可玩内容。它的目标是把当前 AI 编译系统从“单阶段样例”推进到“多阶段内容生产链”：连续生产 Stage 05 / Stage 06 / Stage 07 的世界线、玩家线、任务、随机事件、临时样本、研发任务和资产候选，交给项目负责人审查。

## 产物

默认命令：

```bash
python3 tools/content_pipeline/build_multistage_content_pack.py --validate
```

会生成以下审查入口：

- `examples/review_packs/mvp_multistage_content_pack.v0.1.json`
- `examples/review_packs/mvp_multistage_stage_candidate_pack.v0.1.json`
- `shared/schemas/multistage_content_pack.v0.1.schema.json`
- `tools/content_pipeline/validate_multistage_content_pack.py`

其中第一份是详细内容包，包含流水线逻辑、阶段摘要、资产类型统计、资产政策证据和验证结果。第二份是符合现有 `StageCandidatePack v0.1` 的标准阶段候选包，便于沿用现有审查格式。

同时会生成每阶段的具体产物：

- Stage 05：旧信号塔回光压力，生成回光棱镜中继塔候选。
- Stage 06：旧塔回声测标，生成支援道具候选。
- Stage 07：东侧分潮遏制，生成高风险临时改造候选。

## 当前三阶段内容链

### Stage 05：旧信号塔回光压力

输入来自 Stage 04 后运行态：旧信号塔已侦察、回光压力事件 pending、辉晶已发现、北路斥候在场。

输出包括：

- `task_stabilize_old_signal_tower`
- `sample_resonant_glass_shard_trial`
- `research_echo_prism_relay_trial`
- `asset_echo_prism_relay`

资产类型是 `tower_blueprint`，效果块是 `slow` 与 `aura_buff`。

### Stage 06：旧塔回声测标

承接 Stage 05 的试作完成，把旧信号塔从受压状态推进到暂稳状态，并把回流记录成支援道具。

输出包括：

- `task_map_signal_backwash`
- `sample_signal_echo_marker_trial`
- `research_signal_echo_marker_trial`
- `asset_signal_echo_marker`

资产类型是 `support_item`，效果块是 `scout_reveal` 与 `countermeasure_hint`。

### Stage 07：东侧分潮遏制

承接 Stage 06 的回声测标，打开东侧暗脊压力节点，并生成一个高风险短时改造候选。

输出包括：

- `east_dark_ridge`
- `task_contain_split_tide`
- `sample_charged_copper_coil_trial`
- `research_overload_chain_breaker_trial`
- `asset_overload_chain_breaker`

资产类型是 `temporary_mod`，效果块是 `charge_burst` 与 `risk_modifier`。

## 流水线逻辑

多阶段内容生产遵循串行状态链：

```text
Stage 04 RunWorldState
  -> Stage 05 NarrativeEventBundle
  -> Stage 05 WorldStateDelta
  -> Stage 05 next RunWorldState
  -> Stage 05 Proposal / CompiledAssetCandidate
  -> Stage 06 NarrativeEventBundle
  -> Stage 06 WorldStateDelta
  -> Stage 06 next RunWorldState
  -> Stage 06 Proposal / CompiledAssetCandidate
  -> Stage 07 NarrativeEventBundle
  -> Stage 07 WorldStateDelta
  -> Stage 07 next RunWorldState
  -> Stage 07 Proposal / CompiledAssetCandidate
  -> MultistageContentPack
  -> Multistage StageCandidatePack
```

每个阶段都必须过：

- `validate_narrative_bundle.py`
- `validate_world_delta.py`
- `validate_world_delta_semantics.py`
- `apply_world_delta.py`
- `validate_run_world_state.py`
- `validate_proposal.py`
- `validate_asset_candidate.py`
- `simulate_asset_candidate.py`，生成确定性粗粒度玩法模拟摘要
- `score_asset_candidate.py`，生成资产候选评分和媒体需求建议
- `asset_promotion_policy.py`，判断候选是 `fallback_ready`、`preview_only`、`runtime_ready` 还是 `failed`
- `validate_multistage_content_pack.py` 的完整回放门：从 `summary.initial_state_file` 串行应用每阶段 `WorldStateDelta`，最终状态必须等于 `summary.final_state_file`
- `validate_multistage_content_pack.py`
- `validate_stage_candidate_pack.py`，用于标准阶段候选包

`MultistageContentPack.stage_summaries[].asset_policy_evidence` 会保存每阶段资产的证据摘要：

- `validation`：效果白名单和基础运行契约是否通过。
- `simulation`：估算输出、工具性、漏怪、能耗和风险旗标。
- `score`：总分、分项分数、媒体角色需求和晋级建议。
- `promotion`：晋级状态、是否可 fallback 运行、是否仍缺 runtime media，以及后续动作。

当前多阶段样例的三个资产都应停在 `fallback_ready`：玩法核心可作为候选审查，但媒体和 runtime package 尚未正式晋升，因此不能自动进入默认战斗主路径。

单独校验详细内容包：

```bash
python3 tools/content_pipeline/validate_multistage_content_pack.py examples/review_packs/mvp_multistage_content_pack.v0.1.json
```

## 边界

构建器明确保证：

- 不读取 `.env`。
- 不调用外部模型或媒体服务。
- 不修改基础世界书。
- 不接入前端。
- 不把候选内容自动晋升到默认战斗 runtime。
- 不覆盖原有四阶段 MVP `mvp_stage_candidate_pack.v0.1.json`。

当前 `mvp_multistage_stage_candidate_pack.v0.1.json` 的推荐结论是 `needs_human_review`。这是有意设计：内容和结构已经可审查，但资产还需要平衡、媒体 readiness 和 runtime package 晋升。

## 审查重点

审查这套产物时，建议重点看：

1. 世界线是否服务玩法进度，而不是自由扩写世界书。
2. 玩家线是否产生可完成任务、可验证奖励和清晰风险。
3. 每个阶段是否至少生成一个可运行或可审查的玩法对象。
4. 候选材料是否通过临时样本进入运行态，而不是绕过资源治理。
5. NPC 引用是否只使用当前运行态、canonical 或 review pack 明确允许的候选。
6. 资产候选是否只使用效果白名单，不生成任意代码。
7. 资产候选是否带有验证、模拟、评分和晋级策略证据。
8. 标准阶段候选包是否足以支撑人工审查和后续晋升决策。

这份内容包的价值在于证明：同一套 AI 编译系统不仅能生成防御塔，还能连续生成剧情阶段、任务、随机事件、材料样本、支援道具和临时改造，并且每一步都可校验、可回滚、可审查。
