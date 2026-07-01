# MVP 编译器审查交付包 v0.1

本文档说明 `MVP Compiler Review Dossier v0.1` 的用途、内容边界和验收方式。

这份交付包不是前端 runtime 包，也不是玩家侧数据。它是给项目负责人和评审者审查 AI 编译系统逻辑用的证据索引：把多阶段剧情、玩法对象、防御塔 / 道具 / 情报资产、材料、NPC、运行态变化和验证命令汇总到一个 JSON 文件。

## 产出文件

- `examples/review_packs/mvp_compiler_review_dossier.v0.1.json`
- `shared/schemas/mvp_compiler_review_dossier.v0.1.schema.json`
- `tools/content_pipeline/build_mvp_compiler_review_dossier.py`
- `tools/world_state/replay_mvp_delta_chain.py`
- `game_data/demo/wick_store_pressure_battle_config.json`
- `examples/locked_manifests/mvp_wick_store_pressure.locked_manifest.json`
- `examples/runtime_packages/mvp_wick_store_pressure.runtime_package.json`

默认构建命令：

```bash
python3 tools/content_pipeline/build_mvp_compiler_review_dossier.py --validate
```

## 边界

交付包明确标记：

- `visibility: review_only`
- 不接入前端。
- 构建器不读取 `.env`。
- 构建器不调用任何 provider。
- 构建器不修改基础世界书。
- runtime package 只做引用，不内嵌为玩家加载包。

注意：交付包会引用 live workflow 和 provider 调用相关文档，但它本身不执行 live workflow，也不保存原始 provider payload。

## 汇总内容

交付包包含：

- `pipeline_overview`：从剧情节点、WorldStateDelta、资产编译、媒体管线到审查交付包的流水线说明。
- `stage_reviews`：四个 MVP 阶段的世界线 / 玩家线覆盖、玩法目的、玩法 hook、Delta op 统计、关联资产、NPC、材料、地图节点。
- `content_inventory`：唯一资产、NPC、材料、地图节点、任务、随机事件、研发任务、蓝图。
- `runtime_package_summaries`：第一战和灯芯仓压力战 runtime package 的资产、战斗上下文和可部署状态摘要。灯芯仓压力战包含信标灯芯诱饵、灯芯护幕桩、灯灰爆鸣塔三件资产。
- `runtime_state_summary`：最终运行态的进度、全局状态和对象数量。
- `readiness_summary`：当前是否足以支撑 MVP 审查。
- `source_evidence`：被汇总的关键文件与 sha256。
- `validation_commands`：建议复验命令。
- `known_risks`：仍需处理的风险。

## 当前审查结论

当前交付包证明的范围：

- 已有四阶段剧情演示链。
- 每个阶段都能关联 `NarrativeEventBundle` 和受控 `WorldStateDelta`。
- 世界线和玩家线都不是纯文本，而是能落到任务、随机事件、研发任务、资源、NPC、地图节点和蓝图。
- 当前资产清单包含运行时样品、塔、防御支援道具、情报资产和高风险候选改造。
- 灯芯仓压力战已有 runtime package 证据，能验证第二战地图、路径、保护目标和三件默认可用资产。
- 默认 MVP 可以按 `runtime_fixture` + `fallback_ready` 资产组织审查；候选 / 受阻资产不应默认进入战斗。

当前仍不证明：

- 前端已经接入这些数据。
- 所有媒体资产都已具备最终 runtime readiness。
- 所有 live provider workflow 都可以在任意环境稳定运行。
- 基础世界书已经完成 canonical NPC / material 的长期治理。

## 验收命令

构建并校验交付包：

```bash
python3 tools/content_pipeline/build_mvp_compiler_review_dossier.py --validate
```

校验故事资产审查包：

```bash
python3 tools/content_pipeline/validate_mvp_story_asset_review_pack.py examples/review_packs/mvp_story_asset_review_pack.v0.1.json
```

校验最终运行态：

```bash
python3 tools/world_state/validate_run_world_state.py examples/run_world_states/demo_after_stage_04_wick_store.run_world_state.json
```

校验灯芯仓压力战 locked manifest 和 runtime package：

```bash
python3 tools/content_pipeline/validate_locked_manifest.py examples/locked_manifests/mvp_wick_store_pressure.locked_manifest.json
python3 tools/asset_graph/validate_runtime_package.py examples/runtime_packages/mvp_wick_store_pressure.runtime_package.json
```

校验 WorldStateDelta 语义门示例：

```bash
python3 tools/asset_graph/run_workflow.py examples/workflows/mvp_world_delta_semantic_gate_demo.workflow.json --output-dir /tmp/mvp_world_delta_semantic_gate_demo
```

重放完整世界状态链并对比最终快照：

```bash
python3 tools/world_state/replay_mvp_delta_chain.py --compare-final examples/run_world_states/demo_after_stage_04_wick_store.run_world_state.json
```

校验所有 workflow：

```bash
for f in examples/workflows/*.json; do
  python3 tools/asset_graph/validate_workflow.py "$f" || exit 1
done
```

## 审查建议

优先审查三个问题：

1. `pipeline_overview` 的流水线逻辑是否符合项目定位：自然语言 / 世界书 / 玩家行为 -> 受控结构化对象 -> 可玩资产。
2. `stage_reviews` 里的每一阶段是否真的服务玩法，而不是只写剧情。
3. `known_risks` 是否覆盖了 MVP 前必须处理的风险，尤其是媒体 readiness 和旧 fixture NPC 迁移。
