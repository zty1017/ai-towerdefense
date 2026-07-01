# 真实 LLM 世界状态 Delta 烟测 v0.1

本文档记录一次真实模型服务闭环烟测。它用于审查“世界线 / 玩家线推进是否能从真实 LLM 输出进入本地受控结构”，不作为玩家侧文案，不接入前端，也不保存原始 provider 响应。

## 调用边界

- 调用日期：2026-07-01
- Provider profile：`longcat_2_0`
- 真实服务调用：是
- 输入来源：本地 demo 世界状态、战斗结果和世界书上下文
- `.env`：仅由本地 wrapper 加载环境变量；未打印、未提交、未写入任何 key
- 未保存内容：原始 prompt、原始 provider response、provider trace、API key
- 保存内容：通过本地 schema 校验的 `WorldStateDelta`

## 产物

- `examples/world_deltas/live_longcat_first_battle.world_delta.json`

该文件来自 `/tmp/live_world_delta_longcat_2_0.json`，复制进仓库前已经通过本地 `WorldStateDelta` 校验。它的作用是保留一份可审查的真实闭环样例，证明真实 LLM 输出可以被约束成世界状态变更包，而不是直接自由续写世界书。

## 验收命令

```bash
python3 tools/world_state/validate_world_delta.py examples/world_deltas/live_longcat_first_battle.world_delta.json
python3 tools/world_state/apply_world_delta.py examples/run_world_states/demo_initial.run_world_state.json examples/world_deltas/live_longcat_first_battle.world_delta.json /tmp/live_world_delta_longcat_2_0.next_run_world_state.json
```

烟测结果：

- `WorldStateDelta` schema 校验通过。
- delta 可应用到 `demo_initial.run_world_state.json`。
- 应用后阶段推进到 `post_first_defense`。
- 应用后事件数为 2，已解锁 fact 数为 2，临时样品数为 1。

## Delta 摘要

- `delta_id`：`delta_run_demo_001_gray_lantern_station_2_battle_result`
- `run_id`：`run_demo_001`
- `worldbook_id`：`long_night_lanterns`
- 操作数：10
- 核心结果：灰灯驿站首波防守成功，折光绊索样品被记录，地图节点进入 `secured`，进度推进到 `post_first_defense`。

主要操作包括：

- 追加首战成功事件。
- 将 `gray_lantern_station` 标记为 `secured`。
- 消耗 `lamp_oil`。
- 解锁 `sample_trap_tested_in_battle`。
- 添加临时样品 `sample_trap_7f3a`。
- 调整全局 `hope` 与 `pressure`。

## 审查结论

这次真实调用说明：当前 LLM -> 结构化 JSON -> schema 校验 -> apply world delta 的底层闭环可以跑通。

但它也暴露出 schema 之外的语义问题：

- 产物引用了旧 NPC `engineer_001`。当前 MVP 内容包的 canonical NPC 是 `npc_gray_lantern_keeper` 与 `npc_workshop_mentor`；旧 fixture ID 不应被真实 LLM 自动写入正式世界状态。
- 产物设置了 `tutorial_first_battle_started = true`。首战已经结束，更合理的 flag 应该是 `tutorial_first_battle_completed` 或同类完成态。
- 当前 `validate_world_delta.py` 能保证结构合法，但还不能完全保证引用 ID、flag 状态机和阶段语义正确。

## 后续 Gate

已新增 `WorldStateDeltaSemanticGate v0.1` 原型，详见 `docs/WORLD_STATE_DELTA_SEMANTIC_GATE_V0_1.md`。该 gate 位于 `validate_world_delta.py` 之后、`apply_world_delta.py` 之前，用于把本次真实 LLM 烟测暴露出的结构外问题沉淀为本地校验规则。当前它既有 CLI，也已作为 `world_state.validate_delta_semantics` 节点接入 `mvp_live_world_delta_guarded.workflow.json`。

后续已把 live WorldStateDelta 提示词升级到完整 17 种 op，并注入 review pack 边界，要求真实 LLM 不仅写世界事件，还要把阶段推进落到任务、随机事件、研发任务、样品、蓝图、资源、NPC 或地图节点等玩法对象/状态上。`tools/llm/generate_world_delta.py` 默认也会执行语义门，只有显式 `--skip-semantic-gate` 才跳过。

核心校验包括：

- 校验 `npc_id`、`resource_id`、`node_id`、`sample_id` 是否来自当前 run world state、世界书 registry 或显式候选白名单。
- 校验 flag 命名和状态流转，例如 `started`、`completed`、`failed` 不应互相混用。
- 校验战斗结果类 delta 不得把旧兼容 fixture ID 写入正式状态。
- 扫描玩家 / 世界可见文本值，避免泄漏 provider、schema、prompt、raw_json、api_key、trace 等技术词。

这道 gate 的原则是：真实模型可以提出变化，但正式提交前必须经过结构校验与语义校验两层。
