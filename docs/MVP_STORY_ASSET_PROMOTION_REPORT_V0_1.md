# MVP 阶段资产 Promotion 报告 v0.1

本文档说明 `examples/review_packs/mvp_story_asset_promotion_report.v0.1.json` 的用途和生成逻辑。它服务于内容审查，不接入前端，不构建正式 runtime package，不调用真实模型服务，不读取 `.env`。

## 目标

`mvp_story_asset_review_pack.v0.1.json` 已经把四个阶段的剧情、NPC、材料和可复用资产串成审查包。Promotion 报告在此基础上回答一个更具体的问题：

哪些资产可以先用 fallback 进入 MVP 演示，哪些只是候选，哪些必须先完成世界登记、真实媒体生成或数值复验。

## 离线流水线

生成命令：

```bash
python3 tools/content_pipeline/build_mvp_review_pack_promotion_report.py
```

流水线为：

```text
ReviewPack
  -> 遍历每个 stage.assets
  -> runtime package fixture 只做存在性与 asset id 检查
  -> compiled asset 进入 validate / simulate / score / promotion policy
  -> stage governance gate 叠加审查包语义
  -> 输出 promotion report JSON
```

其中 compiled asset 复用现有确定性工具：

- `validate_asset_candidate.py`
- `simulate_asset_candidate.py`
- `score_asset_candidate.py`
- `asset_promotion_policy.py`

最后的 `stage_governance_gate` 会继续拦截候选状态、高风险状态、未登记材料和未登记 NPC。也就是说，某个资产即使在玩法 policy 上可以 `fallback_ready`，只要它在审查包中是 `candidate_only` 或依赖未登记内容，就不会被标成默认可用。

## 状态含义

- `usable_runtime_fixture`：已有 runtime package 示例可用。它不是 compiled asset promotion，不代表 AI 编译资产已经正式晋升。
- `fallback_ready`：玩法核心通过离线校验，可用确定性占位外观和 visual recipe 支撑演示；真实图像、视频或动图仍需继续生成和入媒体清单。
- `candidate_only`：审查包仍把它定义为候选，不能进入默认 runtime。
- `candidate_only_needs_world_registration`：候选资产还依赖未登记 NPC 或材料。
- `candidate_only_high_risk`：高风险高收益研发候选，不能作为默认 MVP 战斗资产。
- `needs_world_registration`：资产本身不是 candidate-only，但 provenance 引用了未登记世界对象。
- `failed` / `missing_source`：基础校验、source 文件或 policy 输出存在阻断问题。

## 当前审查结论

第一战的 `sample_trap_7f3a / 折光绊索` 只能标为 `usable_runtime_fixture`。它用于证明战斗中途样品送达路径已经有示例包，但不伪装成已完成 promotion 的 compiled asset。

`signal_wick_decoy`、`wick_barrier_pylon`、`east_dark_echo_survey`、`ash_burst_lantern` 可以倾向 `fallback_ready`。它们适合先进入 MVP 演示的离线内容包：玩法核心可测，媒体可以用确定性 fallback 兜底，后续再补真实图片、视频帧、抠图和 runtime media manifest。

`shadow_tide_survey` 不能直接 runtime-ready。它依赖 `charcoal_map`、`signal_wick` 等未登记材料，并引用旧 NPC 或未登记 NPC。它应先进入世界登记或改写材料来源，再决定是否入包。

`overload_chain_mod` 不能进入默认 MVP 战斗。它是高风险临时改造，依赖未登记材料和电力上下文；应等高风险研发、供电系统、失败/回滚机制和更严格数值模拟存在后再开放。

## 审查用法

审查时优先看三个层次：

1. `summary`：快速判断整体可用数量、fallback 数量和候选/阻断数量。
2. `stages[].assets[]`：查看某阶段每个资产的 `promotion_state`、`blocking_reasons`、`required_next_actions`。
3. `asset_rollup`：查看同一个资产跨阶段复用时的统一状态。

如果一个资产是 `fallback_ready`，它仍然需要真实媒体生产工作，但不阻塞 MVP 演示链路。如果一个资产是 `candidate_only*` 或 `needs_world_registration`，应先解决世界对象登记、候选 NPC 晋升、材料来源改写或高风险机制缺口。
