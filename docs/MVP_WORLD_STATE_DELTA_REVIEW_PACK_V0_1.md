# MVP 多阶段 WorldStateDelta 审查包 v0.1

本文档说明阶段 2 到阶段 4 的世界状态推进包。它们不接入前端，不调用真实模型服务，不读取 `.env`，只把已经审查过的 `NarrativeEventBundle` 和玩法对象边界落成可验证、可连续应用的 `WorldStateDelta`。

## 产出文件

- `examples/world_deltas/stage_02_dawn_review_supply_line.world_delta.json`
- `examples/world_deltas/stage_03_northern_road_scouting.world_delta.json`
- `examples/world_deltas/stage_04_wick_store_pressure_battle.world_delta.json`
- `examples/run_world_states/demo_after_stage_04_wick_store.run_world_state.json`

前置状态使用：

- `examples/run_world_states/demo_initial.run_world_state.json`
- `examples/world_deltas/repaired_first_battle_semantic_pass.world_delta.json`

## 生产流水线

当前流水线为：

```text
MVP Story Asset Review Pack
  -> NarrativeEventBundle stage 2/3/4
  -> 人类确认的玩法目的与对象边界
  -> WorldStateDelta fixture
  -> validate_world_delta.py
  -> validate_world_delta_semantics.py
  -> apply_world_delta.py
  -> demo_after_stage_04_wick_store.run_world_state.json
```

这里的 `WorldStateDelta fixture` 仍然是受控编译产物，不是自由续写。每个 delta 只允许使用 schema 白名单 op；任何基础世界书改写、任意 JSON patch、脚本、provider 调用都不允许出现在 delta 中。

## 受控引入能力

为了让世界线能推进到新节点、功能 NPC 和可执行玩法对象，本轮扩展运行态 op。

地图 / NPC 引入：

- `introduce_map_node`：把地图节点加入当前单局 `RunWorldState.map_nodes`。
- `introduce_npc`：把 canonical 或显式候选 NPC 加入当前单局 `RunWorldState.npcs`。

玩法对象引入：

- `upsert_task` / `set_task_status`：生成或推进任务。
- `schedule_random_event` / `set_random_event_status`：安排或结算随机事件、压力事件、传闻事件。
- `upsert_research_job`：把任务、样品或战后结果转成研发任务。
- `unlock_blueprint`：把稳定结果登记为当前单局可用蓝图。

这些 op 只影响当前 run state，不修改基础世界书。`WorldStateDeltaSemanticGate` 会继续检查：

- 新 NPC 不能是 `legacy_fixture_ref`。
- 新 NPC 必须来自 canonical NPC 或审查包 candidate NPC 边界。
- 新 NPC 的 `location_node_id` 必须已存在，或在同一个 delta 中先被 `introduce_map_node` 引入。
- 关系更新只能作用于当前 run state 中已经存在的 NPC。
- 任务引用的节点与 NPC 必须存在，或在同一个 delta 中先被引入。
- 随机事件引用的节点和关联任务必须存在，或在同一个 delta 中先被写入。
- 研发任务引用的任务或样品必须存在，或在同一个 delta 中先被写入。

## 阶段摘要

阶段 2：`stage_02_dawn_review_supply_line`

- 引入 `supply_line_hub_to_gray` 与 `lamp_wick_store`。
- 引入候选功能 NPC `npc_wire_mender_003`。
- 将首战样品缺陷转成护线、诱饵、护幕方向。
- 生成补给线抢修任务、灯芯仓防守任务、灯芯仓压力事件和信标灯芯诱饵试作研发任务。
- 增加 `lantern_ash`、`lamp_shard`、`conductor_filament` 作为后续研发材料。

阶段 3：`stage_03_northern_road_scouting`

- 将 `northern_road_crossing` 调整为已侦测。
- 将 `old_signal_tower` 从隐藏风险推进到已侦测压力点。
- 引入候选功能 NPC `npc_road_scout`。
- 产出临时情报样品 `intel_dark_echo_survey_001`。
- 完成北路侦察任务，激活灯芯仓压力事件，并安排旧信号塔压力事件。

阶段 4：`stage_04_wick_store_pressure_battle`

- 将 `lamp_wick_store` 与 `supply_line_hub_to_gray` 标记为守住。
- 让 `npc_wire_mender_003` 关系提升，证明阶段 2 引入的功能 NPC 可以在后续战斗中被使用。
- 消耗 `lantern_ash`，获得稀有材料 `glow_crystal`。
- 产出临时样品 `asset_ash_burst_lantern_trial`，对应灯灰爆鸣塔后续正式蓝图整理。
- 完成灯芯仓防守和补给线抢修任务，解决灯芯仓压力事件，解锁 `asset_ash_burst_lantern` 蓝图。

## 验收命令

结构校验：

```bash
python3 tools/world_state/validate_world_delta.py examples/world_deltas/stage_02_dawn_review_supply_line.world_delta.json
python3 tools/world_state/validate_world_delta.py examples/world_deltas/stage_03_northern_road_scouting.world_delta.json
python3 tools/world_state/validate_world_delta.py examples/world_deltas/stage_04_wick_store_pressure_battle.world_delta.json
```

连续语义校验与应用顺序：

```bash
python3 tools/world_state/apply_world_delta.py examples/run_world_states/demo_initial.run_world_state.json examples/world_deltas/repaired_first_battle_semantic_pass.world_delta.json /tmp/run_demo_stage_01_repaired.run_world_state.json
python3 tools/world_state/validate_world_delta_semantics.py examples/world_deltas/stage_02_dawn_review_supply_line.world_delta.json --run-state /tmp/run_demo_stage_01_repaired.run_world_state.json
python3 tools/world_state/apply_world_delta.py /tmp/run_demo_stage_01_repaired.run_world_state.json examples/world_deltas/stage_02_dawn_review_supply_line.world_delta.json /tmp/run_demo_stage_02_supply_line.run_world_state.json
python3 tools/world_state/validate_world_delta_semantics.py examples/world_deltas/stage_03_northern_road_scouting.world_delta.json --run-state /tmp/run_demo_stage_02_supply_line.run_world_state.json
python3 tools/world_state/apply_world_delta.py /tmp/run_demo_stage_02_supply_line.run_world_state.json examples/world_deltas/stage_03_northern_road_scouting.world_delta.json /tmp/run_demo_stage_03_scouting.run_world_state.json
python3 tools/world_state/validate_world_delta_semantics.py examples/world_deltas/stage_04_wick_store_pressure_battle.world_delta.json --run-state /tmp/run_demo_stage_03_scouting.run_world_state.json
python3 tools/world_state/apply_world_delta.py /tmp/run_demo_stage_03_scouting.run_world_state.json examples/world_deltas/stage_04_wick_store_pressure_battle.world_delta.json /tmp/run_demo_stage_04_wick_store.run_world_state.json
```

最终快照包含 4 个任务、2 个随机事件、3 个临时样品和 1 个已知蓝图。

最终快照：

```bash
python3 tools/world_state/validate_run_world_state.py examples/run_world_states/demo_after_stage_04_wick_store.run_world_state.json
```

## 审查注意

当前 `demo_initial.run_world_state.json` 仍保留早期兼容 NPC：`engineer_001` 与 `scout_002`。本轮没有继续引用或强化它们；semantic gate 会阻止新的 delta 更新这些旧 NPC。后续应单独做一次 run state fixture 迁移，把初始状态切到 canonical NPC 与候选 NPC 体系。
