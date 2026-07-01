# 可编译对象计划 v0.1

本文档说明 `CompilableObjectPlan v0.1` 的用途、边界和验收方式。

它不是最终剧情，不是 runtime package，也不是玩家侧数据。它是下一轮 AI 编译前的审查施工图：在 LLM 或 worker 生成内容之前，先声明“这一阶段应该生成哪些对象、为什么生成、依赖什么、权限等级是什么、需要哪些验证门、失败时如何降级”。

## 为什么需要它

目前系统已经有：

- `CompilableObjectCatalog`：登记当前已经存在或已审查的可编译对象。
- `StageCandidatePack`：把每个阶段的剧情、状态变化、玩法对象和资产引用合成候选单元。
- `WorldStateDelta`：实际修改单局运行态。
- `CompiledAssetCandidate`：实际承载塔、道具、临时改制、情报资产等。

但如果让 LLM 直接从当前运行态跳到 `WorldStateDelta` 或资产候选，仍然容易出现两个问题：

1. 它可能只写一段故事，缺少可执行对象。
2. 它可能生成过多或越权对象，例如直接给最终奖励、改写主线、注册高风险规则。

`CompilableObjectPlan` 在中间增加一道计划层，让“下一步要生成什么”先被结构化审查。

## 当前产物

- `shared/schemas/compilable_object_plan.v0.1.schema.json`
- `tools/content_pipeline/build_compilable_object_plan.py`
- `tools/content_pipeline/validate_compilable_object_plan.py`
- `examples/review_packs/mvp_next_stage_compilable_object_plan.v0.1.json`

默认构建并校验：

```bash
python3 tools/content_pipeline/build_compilable_object_plan.py --validate
```

单独校验：

```bash
python3 tools/content_pipeline/validate_compilable_object_plan.py examples/review_packs/mvp_next_stage_compilable_object_plan.v0.1.json
```

计划落地样例：

```bash
python3 tools/content_pipeline/build_stage05_plan_realization.py --validate
```

该样例不会把 Stage 05 自动晋升为正式阶段候选，只证明计划可以转成可审查的 `NarrativeEventBundle`、`WorldStateDelta`、下一运行态快照、资产提案和候选资产。详见 `docs/STAGE05_PLAN_REALIZATION_V0_1.md`。

## 边界

构建器明确保证：

- 不接入前端。
- 不读取 `.env`。
- 不调用外部模型或媒体服务。
- 不修改基础世界书。
- 不导出 runtime package。
- 只生成 review-only 计划。

计划允许后续 LLM 填充，但必须在审查通过后执行。

## 当前 Stage 05 计划

当前样例计划目标是：

```text
act_1_stage_05_old_signal_tower_pressure
旧信号塔回光压力
```

它基于当前运行态里的证据：

- `map_node:old_signal_tower`
- `random_event:random_event_old_signal_tower_pressure`
- `fact:old_signal_tower_pressure_hint`
- `material:glow_crystal`
- `npc:npc_road_scout`

计划请求 6 个对象：

1. 第五阶段候选：把旧信号塔压力事件升级为可审查阶段。
2. 玩家任务：稳定旧信号塔。
3. 候选材料：回光玻片，用于后续折射 / 回声类编译。
4. 候选功能 NPC：信号塔相关的路线解释和研发评审角色。
5. 防御塔候选：回光棱镜中继塔。
6. 编译报告：用世界内语言解释为什么某些结果只能候选或 fallback。

这些请求不会直接进入运行态。它们只是下一轮 LLM / DAG 生成的受控输入。

## 审查重点

审查这份计划时，重点不是文案好不好，而是：

- 是否确实承接了当前运行态证据。
- 是否产生了任务、事件、材料、NPC、资产等具体对象。
- 是否没有越权生成 L5 引擎或终局规则。
- 是否把候选 NPC / 候选材料保留在 review 状态。
- 是否为资产媒体、模拟、语义门和人工审查预留了正确 gate。
- 是否有合理 fallback，不会因为 LLM 或媒体失败破坏玩家流程。

## 在流水线中的位置

推荐后续流水线：

```text
CompilableObjectCatalog
  -> CompilableObjectPlan
  -> LLM 或离线 builder 填充 NarrativeEventBundle / Proposal / ObjectSpec
  -> deterministic legalize
  -> WorldStateDelta / CompiledAssetCandidate
  -> Validator / Simulation / Promotion
  -> StageCandidatePack
  -> Review Dossier
```

这让 AI 创作自由度被保留在“可计划、可校验、可回滚”的范围内。
