# 受控剧情 / 世界线推进编译 v0.1

本文记录 MVP 阶段的剧情编译骨架。目标不是让 AI 自由续写长篇剧情，而是把剧情、NPC、任务、地图变化和研发机会编译成可验证、可提交、服务玩法的结构化节点。

## 1. 核心原则

世界演化不是自由写作，而是服务玩法循环的受控内容编译。

AI 或 deterministic builder 可以生成候选剧情节点，但不能直接修改基础世界书，也不能直接写运行状态。所有可落地变化必须先表达为 `NarrativeEventBundle`，再由 `WorldStateDelta` 串行提交到 `RunWorldState`。

```text
RunWorldState + BattleResult + SessionContext
  -> NarrativeEventBundle
  -> Narrative validator
  -> Gameplay Purpose Gate
  -> WorldStateDelta
  -> WorldStateDelta validator
  -> apply_delta
  -> Next RunWorldState
```

## 2. 世界线与玩家线

剧情推进分两条线，但底层共享同一套状态与 delta 机制：

- `world_line`：地图、威胁、主线压力、路线开放、世界状态变化。
- `player_line`：战后反馈、研发机会、玩家选择的后果、NPC 对玩家行为的回应。
- `shared`：两条线交汇的位置，例如功能 NPC 候选、任务入口、重要资源线索。

这三类节点都写在同一个 `NarrativeEventBundle` 中，避免拆成两套互相不知道的剧情系统。

## 3. 并行候选与串行提交

后续 AI 版本可以并行生成：

- NPC 候选；
- 地图事件候选；
- 战后反馈候选；
- 研发机会候选；
- 下一战役入口候选。

但正式落地必须经过串行 commit gate：

```text
candidate pool
  -> schema validation
  -> gameplay purpose gate
  -> world fit check
  -> state conflict check
  -> WorldStateDelta
  -> apply_delta
```

当前 v0.1 已在 `commit_policy` 中固定：

```json
{
  "candidate_generation": "parallel_allowed",
  "commit_gate": "world_state_delta_required",
  "commit_order": "serial_by_created_turn"
}
```

## 4. Gameplay Purpose Gate

每个可提交剧情节点必须至少有一个 `gameplay_purpose` 和一个 `gameplay_hook`。没有玩法作用的文本只能作为临时氛围候选，不能进入正式运行状态。

v0.1 白名单包括：

- `unlock_battle_node`
- `introduce_functional_npc`
- `introduce_generic_npc`
- `introduce_material`
- `create_research_need`
- `modify_map_node_state`
- `offer_workshop_hook`
- `advance_main_pressure`
- `explain_battle_result`
- `trigger_random_event`
- `teach_mechanic`
- `reward_player_choice`
- `increase_threat`
- `open_resource_route`
- `create_quest_hook`

## 5. 与 WorldStateDelta 的关系

`NarrativeEventBundle` 只说明剧情节点想如何影响游戏：

- 解释战斗结果；
- 引入功能 NPC 候选；
- 开放地图路线；
- 生成研发需求；
- 引入临时材料或样品；
- 记录世界线事件。

它不直接改 `RunWorldState`。真正写入仍由 `WorldStateDelta` 完成，并且只能使用现有 9 类受控操作：

- `append_event`
- `set_map_node_state`
- `adjust_resource`
- `set_flag`
- `unlock_fact`
- `update_npc_relationship`
- `add_temporary_sample`
- `set_progress_phase`
- `adjust_global_state`

因此，即使后续由真实 LLM 生成剧情包，也必须经过同一套 delta 门禁。

## 6. 当前示例闭环

新增 workflow：

```text
examples/workflows/mvp_controlled_narrative_world_progression.workflow.json
```

它会生成：

- 世界线节点：灰灯驿站首战后，地图状态推进、北侧路口开放侦察入口。
- 玩家线节点：解释折光绊索有效但消耗过快，引出下一次现场研发。
- 交汇节点：引入“补线人”作为功能 NPC 候选，但不直接写入当前 NPC 列表，只提交线索和任务入口。

对应示例：

```text
examples/narrative_bundles/first_battle_controlled.narrative_event_bundle.json
```

执行后会产出：

- `narrative_event_bundle`
- `world_state_delta`
- 下一份 `run_world_state`

这证明剧情编译已经从“文案生成”进入“阶段化、节点化、玩法绑定、受控提交”的 MVP 骨架。
