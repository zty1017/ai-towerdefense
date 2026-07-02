# Stage 05 计划落地样例 v0.1

本文档说明 `build_stage05_plan_realization.py` 的用途、边界和验收方式。

它不是正式第五关，也不会自动进入玩家 runtime。它是一个审查样例：把 `CompilableObjectPlan` 中规划的第五阶段对象，转成一组可以被现有校验器验证的草案产物。

## 背景判断

外部反馈中有一个关键判断可以吸收为本项目口径：游戏中的对象不是只有图像或文案，而是可以被描述、结构化、分解、校验、导出并在运行时执行的状态化结构。

因此 Stage 05 不是“补一段剧情”，而是一次小型闭环：

```text
CompilableObjectPlan
  -> NarrativeEventBundle
  -> WorldStateDelta
  -> next RunWorldState
  -> Proposal
  -> CompiledAssetCandidate
  -> review report
```

其中剧情、任务、随机事件、临时样本和防御塔候选都被视为可编译对象，只是输出形态和校验标准不同。

## Object Graph 与 Compile DAG

这个样例采用两层理解：

- `Object Graph`：描述对象之间的依赖关系，例如旧信号塔压力依赖当前地图节点、待触发随机事件、辉晶、北路斥候。
- `Compile DAG`：描述单个对象如何生成和验证，例如防御塔方案从 `Proposal` 进入 `CompiledAssetCandidate`，再过效果白名单校验。

不要把整个世界编成一张不可维护的大图。先明确对象依赖，再让每个对象进入自己的受控编译管线。

## 当前产物

默认命令会生成：

- `examples/narrative_bundles/stage_05_old_signal_tower_pressure.narrative_event_bundle.json`
- `examples/world_deltas/stage_05_old_signal_tower_pressure.world_delta.json`
- `examples/run_world_states/demo_after_stage_05_old_signal_tower.run_world_state.json`
- `examples/proposals/echo_prism_relay.proposal.json`
- `examples/compiled_assets/echo_prism_relay.compiled_asset.json`
- `examples/review_packs/mvp_stage05_plan_realization_report.v0.1.json`

构建并校验：

```bash
python3 tools/content_pipeline/build_stage05_plan_realization.py --validate
```

## 边界

构建器明确保证：

- 不读取 `.env`。
- 不调用外部模型或媒体服务。
- 不修改基础世界书。
- 不把 Stage 05 自动写入 `StageCandidatePack`。
- 不把输出声明为前端可直接加载的 runtime package。

当前输出是 review-only 草案。后续如果要晋升，需要进入阶段候选包、媒体 readiness、战斗模拟和人工审查。

顶层的 `core_artifact_alignment` 明确声明：

- `mvp_stage05_plan_realization_report.v0.1` 是 review-only 计划落地审查报告。
- 它本身不是 `ContextPackage`、`FactEntry`、`CGOP` 或 `WorldStateDeltaTransaction`。
- 它不能直接激活 runtime，也不能直接写世界状态。
- 后续核心对象迁移应针对它引用的 `NarrativeEventBundle`、`WorldStateDelta`、`WorldStateDeltaTransaction`、`CompiledAssetCandidate`、`StageCandidatePack` 或 runtime package。

## 受控演化规则

Stage 05 有两个重要约束：

1. 不直接引入未通过边界审查的新 NPC。
2. 不把候选材料当成正式库存资源。

所以本样例复用当前运行态已有的 `npc_road_scout`，并把“回光玻片”写成临时样本 `sample_resonant_glass_shard_trial`，而不是正式资源。

这对应项目治理原则：世界线和玩家线可以演化，但必须服务于玩法、进度和状态机，不允许自由改写基础世界书。

## 验收重点

验收时重点看：

- 叙事节点是否有玩法目的和状态变化，不只是文本。
- 世界状态变化是否通过结构校验、语义门和应用器。
- 新任务、样本、研发任务和随机事件是否能被运行态记录。
- 资产方案是否能转成合法 `CompiledAssetCandidate`。
- 玩家可见文本是否没有泄露底层技术词。

这个样例的价值不在于它是最终第五关，而在于它证明“叙事型对象”和“玩法资产对象”可以共用同一套受控编译思想。
