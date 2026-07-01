# WorldStateDelta 语义校验门 v0.1

本文档定义 `WorldStateDeltaSemanticGate v0.1` 的原型边界。它不调用真实 LLM、图像或视频服务，不读取 `.env`，只在本地读取 `WorldStateDelta`、当前 `RunWorldState` 和可用的世界书 / 审查包登记信息。

## 流水线位置

正式世界状态提交流水线应为：

1. 真实 LLM 或 deterministic 节点提出 `WorldStateDelta`。
2. `tools/world_state/validate_world_delta.py` 做结构校验：schema、字段、op 白名单、禁止字段、玩家可见文本基础禁词。
3. `tools/world_state/validate_world_delta_semantics.py` 做语义校验：引用边界、最小状态语义、样品归属、文本技术词泄漏。
4. `tools/world_state/apply_world_delta.py` 才允许把 delta 应用到当前 run state。

真实 LLM 可以提出变化，但正式提交前必须同时通过结构校验与语义校验。结构合法不等于可以进入玩法状态。

## v0.1 检查项

CLI：

```bash
python3 tools/world_state/validate_world_delta_semantics.py <delta.json> \
  --run-state examples/run_world_states/demo_initial.run_world_state.json
```

AssetGraph 节点：

```text
world_state.validate_delta_semantics
```

节点输入：

- `run_world_state`：当前运行态。
- `world_state_delta`：结构校验后的变化包。

节点输出：

- `default` / `world_state_delta`：通过语义门后转交给 `world_state.apply_delta` 的 delta。
- `validation_report`：语义门审查报告，保留在 execution trace 的产物目录中。

当前实现先复用 `validate_world_delta.py` 的完整结构校验；结构不合法时直接失败，不继续做语义判断。

语义检查包括：

- `delta.run_id` 与 `delta.worldbook_id` 必须匹配当前 run state。
- `set_map_node_state.node_id` 必须存在于当前 `run_state.map_nodes`。
- `adjust_resource.resource_id` 必须是当前 run state 资源，或可从世界书 / 审查包登记中识别的资源 ID；若资源不在当前 run state 中，不允许负数消耗。
- `update_npc_relationship.npc_id` 必须已经存在于当前 `run_state.npcs`，并且不能被审查包标记为 `legacy_fixture_ref`。世界书 canonical NPC 或显式候选 NPC 可以作为合法引用边界，但若尚未进入当前 run state，不能直接更新关系。
- `add_temporary_sample.sample.sample_id` 必须非空，且 `source_delta_id` 必须等于当前 `delta_id`。
- `set_progress_phase.phase` 必须非空。
- 当 `source == "battle_result"` 时，不允许把以 `_started` 结尾的 flag 设置为 `true`；战后应写入 `_completed` 或其他完成态。
- 只扫描玩家 / 世界可见文本值，不扫描结构字段名本身。扫描范围包括 delta summary、event summary、fact summary、sample display name 与 sample summary；文本不得泄漏 `provider`、`schema`、`prompt`、`raw_json`、`api_key`、`trace` 等技术词。

## Registry 策略

v0.1 采用“能稳定读取则登记，否则以 run state 为准”的保守策略：

- 地图节点以当前 `RunWorldState.map_nodes` 为准。
- runtime 资源以当前 `RunWorldState.resources` 为准，同时补充世界书 `resource_mapping`、`materials.json` 和审查包材料边界；但正式消耗仍要求资源已经在当前 run state 中。
- NPC 登记会读取当前 run state、世界书 canonical NPC 和审查包 candidate NPC；但 `update_npc_relationship` 这类会被 applier 立即执行的操作仍要求 NPC 已经存在于当前 run state。审查包 `compatibility_refs` 中标记为 `legacy_fixture_ref` 的旧 fixture ID 会从允许集合中移除。

这个策略解释了为什么 `engineer_001` 即便仍出现在旧 demo run state 中，也会被 semantic gate 拦截：它已在 MVP 审查包中被标记为旧兼容引用，不应由真实 LLM 自动写入正式世界状态。

## 样例

真实 LongCat 首战 delta 结构合法，但语义应失败：

```bash
python3 tools/world_state/validate_world_delta.py examples/world_deltas/live_longcat_first_battle.world_delta.json
python3 tools/world_state/validate_world_delta_semantics.py examples/world_deltas/live_longcat_first_battle.world_delta.json --run-state examples/run_world_states/demo_initial.run_world_state.json
```

预期语义问题至少包括：

- `update_npc_relationship.npc_id="engineer_001"` 是旧 fixture NPC 引用。
- `source="battle_result"` 后设置 `tutorial_first_battle_started=true`，应改为类似 `tutorial_first_battle_completed=true`。

修复后的最小 passing 示例：

```bash
python3 tools/world_state/validate_world_delta_semantics.py examples/world_deltas/repaired_first_battle_semantic_pass.world_delta.json --run-state examples/run_world_states/demo_initial.run_world_state.json
```

DAG passing 示例：

```bash
python3 tools/asset_graph/run_workflow.py examples/workflows/mvp_world_delta_semantic_gate_demo.workflow.json --output-dir /tmp/world_delta_semantic_gate_demo
```

真实 LLM world delta workflow 已在 `mvp_live_world_delta_guarded.workflow.json` 中接入该 gate：

```text
build_delta_with_llm_guarded -> validate_delta_semantics -> apply_delta
```

这意味着真实 provider 产出的 delta 即使通过结构校验，也必须先通过语义门，才会进入运行态 apply。

## 后续扩展

v0.1 只做最小语义门。后续可加入更细的玩法目的校验，例如：每个 delta 是否明确服务地图解锁、研发推进、资源压力、NPC 关系、样品登记或阶段推进；以及更完整的世界书 registry schema，避免从审查包和世界书正文中临时提取边界。
