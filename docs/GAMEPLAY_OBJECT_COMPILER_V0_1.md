# 玩法对象编译器 v0.1

本文档记录当前结论：剧情编译不只是根据世界书生成剧情文本，而是把世界线推进与玩家游玩线推进一起编译成可执行的玩法对象。

## 核心判断

世界书提供风格、规则、角色关系和可解释边界，但它本身不应该自由演化。AI 编译器要做的是：在世界书和底层玩法约束之间，生成能被游戏系统消费的对象。

因此，剧情编译应至少产出两层结果：

- 叙事层：事件摘要、已知事实、NPC 反应、阶段推进文本。
- 玩法层：任务、随机事件、地图压力、研发任务、临时样品、蓝图解锁、资源变化、NPC 状态变化。

玩家看到的是自然的游戏体验：任务出现、传闻发生、NPC 给出反馈、研发完成、地图节点变化。内部才保留结构化对象与审查链路。

## 双线推进

世界线推进负责回答：这个世界发生了什么。

典型产物包括：

- 地图节点显露、受威胁、失守或稳定。
- NPC 进入当前单局，离开、忙碌或改变关系。
- 资源压力、传闻、危机预告和世界状态变化。
- 玩家已知事实和世界日志。

玩家线推进负责回答：玩家现在能做什么。

典型产物包括：

- 主线 / 支线 / 侦察 / 防御 / 资源 / 研发任务。
- 随机事件或压力事件进入 pending / available / resolved。
- 研发任务开始、完成或失败。
- 临时样品进入背包或工坊。
- 蓝图解锁，进入后续可部署资产或正式研发链。

这两条线可以异步并行。例如世界线先安排 `random_event`，玩家线后续通过任务、战斗或研发把它解决。

## 当前运行态对象

`RunWorldState v0.1` 新增可选对象：

- `tasks[]`：可执行任务对象，包含 `task_id`、`kind`、`status`、`title`、`summary`，可挂接 `node_id`、`npc_id`、`objective_refs`、`reward_refs`。
- `random_events[]`：待触发或已出现的世界压力对象，包含 `random_event_id`、`event_type`、`status`、`summary`，可挂接 `node_id`、`trigger_turn`、`related_task_id`。
- `research.active_jobs[]` 增强：支持 `source_task_id`、`source_sample_id`、`expected_turns`，使研发能从任务或样品派生。
- `research.known_blueprints[]`：通过 `unlock_blueprint` 进入正式可用候选。

## 当前 Delta op

`WorldStateDelta v0.1` 的 op 白名单扩展到 17 种，其中玩法对象相关 op 为：

- `upsert_task`
- `set_task_status`
- `schedule_random_event`
- `set_random_event_status`
- `upsert_research_job`
- `unlock_blueprint`

这些 op 只修改当前单局 `RunWorldState`，不修改基础世界书。

## 语义门约束

`WorldStateDeltaSemanticGate v0.1` 会检查：

- 任务挂接的地图节点必须已经存在，或在同一个 delta 中先被引入。
- 任务挂接的 NPC 必须在当前运行态中存在，且不能是旧 fixture 引用。
- 随机事件挂接的节点必须存在。
- 随机事件关联的任务必须存在，或在同一个 delta 中先被写入。
- 研发任务如果引用任务或样品，对应对象必须存在，或在同一个 delta 中先被写入。
- 玩家可见文本不得泄漏 provider、schema、prompt、trace 等技术词。

`NarrativeGameplayContract v0.1` 继续做跨文件检查：

- 每个 `NarrativeEventBundle` 节点必须引用实际存在的 `WorldStateDelta`。
- 每个 `gameplay_hook` 必须由对应 delta op 类型支撑。
- delta 引入的任务、随机事件、研发任务、蓝图、样品、NPC、地图节点等对象必须最终落到 `RunWorldState`。
- 这道门专门防止剧情编译退化成“好看的文本 + 假玩法 hook”。

## MVP 样例链

当前四阶段样例已经把剧情推进落成玩法对象：

- 阶段 1：结算灰灯驿站首战，登记折光绊索样品，写入首战完成状态。
- 阶段 2：生成补给线抢修任务、灯芯仓防守任务、灯芯仓压力事件、信标灯芯诱饵试作研发任务。
- 阶段 3：生成北路侦察任务，激活灯芯仓压力事件，安排旧信号塔压力事件，完成东暗回声测记研发。
- 阶段 4：结算灯芯仓防守，解决压力事件，整理灯灰爆鸣塔蓝图，并解锁 `asset_ash_burst_lantern`。

最终状态 `examples/run_world_states/demo_after_stage_04_wick_store.run_world_state.json` 已包含 4 个任务、2 个随机事件、3 个临时样品和 1 个已知蓝图。

## 后续方向

下一步可以继续扩展：

- 为任务和随机事件增加权重、过期条件、触发条件和失败后果。
- 增加任务链 / 事件链的图结构，便于前端呈现大地图节点和日志。
- 让真实 LLM 先产出候选 GameplayObjectPlan，再经 deterministic legalize 转成 Delta op。
- 让前端只消费 `RunWorldState` 和 locked manifest，不暴露 AI 编译细节。

## 与可编译对象目录的关系

`CompilableObjectCatalog v0.1` 是本文件的上层索引：它不只登记任务和随机事件，也把资产、地图节点、NPC、素材、研发任务、蓝图、事实和 flag 统一登记为可编译对象。

这能回答两个审查问题：

- 当前 MVP 到底有哪些对象已经进入运行态或审查态。
- 每个对象属于哪个权限等级，能否被玩家影响，是否需要人工复核，是否已经可以进入 runtime。

相关文档：

```text
docs/COMPILABLE_OBJECT_MODEL_V0_1.md
```
