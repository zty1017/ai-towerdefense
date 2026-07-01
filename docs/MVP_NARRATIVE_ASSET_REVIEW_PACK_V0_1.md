# MVP 多阶段剧情与玩法对象审查包 v0.1

本文档用于审查《长夜灯火》世界书模板下的 MVP 多阶段内容包。它不接入前端，不调用真实模型服务，不读取 `.env`。本批内容的目标是证明：世界线、玩家线、NPC、材料、道具、防御塔和情报资产可以通过受控流水线组织成可验证的游戏内容，而不是自由续写文本。

## 产出文件

- `examples/narrative_bundles/stage_01_gray_lantern_first_defense.narrative_event_bundle.json`
- `examples/narrative_bundles/stage_02_dawn_review_supply_line.narrative_event_bundle.json`
- `examples/narrative_bundles/stage_03_northern_road_scouting.narrative_event_bundle.json`
- `examples/narrative_bundles/stage_04_wick_store_pressure_battle.narrative_event_bundle.json`
- `examples/review_packs/mvp_story_asset_review_pack.v0.1.json`
- `shared/schemas/mvp_story_asset_review_pack.v0.1.schema.json`
- `tools/content_pipeline/validate_mvp_story_asset_review_pack.py`

## 审查包校验器

`mvp_story_asset_review_pack.v0.1.json` 不是前端运行包，也不是最终世界状态；它是给人类审查的阶段化剧情与玩法对象索引。为了避免它退化成普通 JSON，本仓库提供专门校验器：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/content_pipeline/validate_mvp_story_asset_review_pack.py examples/review_packs/mvp_story_asset_review_pack.v0.1.json
```

校验器会检查：

- 顶层结构必须符合 `mvp_story_asset_review_pack.v0.1` schema。
- `generation_boundary.front_end_integration` 必须是 `not_included`，`base_worldbook_mutation` 必须是 `false`。
- 禁止携带 provider、model、raw prompt、trace、secret 等技术字段或原始调用内容；`schema` 只在玩家可见文本中作为技术词被拦截，结构字段不会被误伤。
- 每个阶段的 `bundle_file` 必须存在，并且会继续调用 `NarrativeEventBundle` 校验逻辑复验。
- 每个阶段的资产 `source_file` 和已确定的战斗 fixture 必须存在；显式 `needed` 占位表示待生产，不当作缺文件。
- canonical NPC 和材料必须能在当前世界书登记文件中找到；candidate-only NPC 和材料可以尚未登记，但必须在审查包边界中标注候选/审查状态与原因。
- 每个阶段至少覆盖世界线或玩家线之一，整包必须同时覆盖 `world_line` 和 `player_line`。
- `excluded_from_mvp_story_pack` 必须明确写出被排除对象和原因。

这道校验门的作用是确认审查包确实服务 MVP 内容交付：它汇总剧情阶段、NPC、材料、资产与玩法钩子，但不直接改写基础世界书，也不把未审查内容推进前端。

## 受控流水线

本批内容遵循当前 `NarrativeEventBundle v0.1` 体系：

```text
RunWorldState / BattleResult / SessionContext
  -> 阶段 brief
  -> NarrativeEventBundle
  -> Gameplay Purpose Gate
  -> WorldStateDelta review
  -> 串行提交到 RunWorldState
  -> 审查包汇总给人类确认
```

其中 `NarrativeEventBundle` 只提出剧情节点与变化意图，不直接改写基础世界书。每个剧情节点必须包含：

- `lane`：世界线、玩家线或交汇线索。
- `gameplay_purpose`：该节点服务什么玩法目的。
- `gameplay_hooks`：它连接到哪个地图、战斗、研发、资源或 NPC 玩法入口。
- `proposed_delta_summary`：若被接受，后续应提交哪些受控状态变化。

并行生成可以发生在候选层，例如 NPC 候选、地图事件候选、战后反馈候选可以同时准备。但正式落地必须经过审查和串行提交，避免两个候选同时改乱同一段世界状态。

## 总体边界

正式 canonical NPC：

- `npc_gray_lantern_keeper`：灰灯驿站守灯人。
- `npc_workshop_mentor`：临时工坊老师傅。

候选功能 NPC：

- `npc_wire_mender_003`：补线人，服务护线、材料折扣、现场评审。
- `npc_road_scout`：北路斥候，服务路径预测、弱点提示、侦测可信度。

正式 canonical 材料：

- `lamp_shard`
- `conductor_filament`
- `lantern_ash`
- `glow_crystal`

候选材料不得直接进入正式内容。例如 `charcoal_map`、`signal_wick`、`charged_copper_coil`、`cracked_insulator` 目前只允许作为候选资产依赖，不应写入正式 RunWorldState。

`engineer_001`、`scout_002` 属于旧 fixture 兼容引用，本审查包不把它们当 canonical NPC 使用。

## 阶段 1：灰灯驿站首防

Bundle：

- `examples/narrative_bundles/stage_01_gray_lantern_first_defense.narrative_event_bundle.json`

世界线：

- 东南影潮压近灰灯驿站。
- 灰灯驿站从地图危机变为第一战斗节点。
- 首战目标是保护驿站核心与信标天线。

玩家线：

- 玩家以守灯技师身份进入临时工坊。
- 本节点只允许一次现场试作。
- 样品不在开场发放，而是在战斗中途送达。

交汇线索：

- 折光绊索样品 `sample_trap_7f3a` 中途送达。
- 玩家构想转化为可部署临时陷阱，教学“构想 -> 试作 -> 战斗投放”。

NPC：

- `npc_gray_lantern_keeper`
- `npc_workshop_mentor`

材料：

- `lamp_shard`
- `conductor_filament`

资产：

- `sample_trap_7f3a`，来自 `examples/runtime_packages/mvp_demo.runtime_package.json`。

玩法目的：

- 教学地图节点选择。
- 教学现场试作限制。
- 教学样品中途送达。
- 用迟滞效果反制高速低耐久敌人。

## 阶段 2：黎明复盘与护线

Bundle：

- `examples/narrative_bundles/stage_02_dawn_review_supply_line.narrative_event_bundle.json`

世界线：

- 灰灯驿站守住，但 `supply_line_hub_to_gray` 受损。
- `lamp_wick_store` 的资源意义被提前强调。
- 影潮没有退去，只是改变压力方向。

玩家线：

- 老师傅复盘折光绊索：有效，但消耗过快。
- 引入 `lantern_ash` 作为稳定材料。
- 从一次性陷阱过渡到护线、修复、支援类资产。

交汇线索：

- 提示 `npc_wire_mender_003 / 补线人`。
- 只提交线索和任务入口，不直接让候选 NPC 成为常驻。

NPC：

- canonical：`npc_gray_lantern_keeper`、`npc_workshop_mentor`
- candidate：`npc_wire_mender_003`

材料：

- `lantern_ash`
- `lamp_shard`
- `conductor_filament`

资产：

- `asset_signal_wick_decoy`：信标灯芯诱饵，道具类，适合拖延前锋。
- `asset_wick_barrier_pylon`：灯芯护幕桩，防御塔类，适合护线和修复。

玩法目的：

- 把战斗结果变成世界状态压力。
- 把样品缺陷变成下一步研发需求。
- 引入功能 NPC 候选，但保持受控提交。

## 阶段 3：北路侦测与路径预测

Bundle：

- `examples/narrative_bundles/stage_03_northern_road_scouting.narrative_event_bundle.json`

世界线：

- 北方深暗出现回光，但不直接揭开黑暗区域。
- `northern_road_crossing` 从完全未知推进到边缘可侦测。
- `old_signal_tower` 成为后续压力来源或可选战斗节点。

玩家线：

- 玩家选择先侦察路径，而不是直接进入下一场硬守。
- 使用灯灰和导线制作短期情报札记。
- 情报资产只揭示路径和弱点，不直接造成伤害。

交汇线索：

- 提示 `npc_road_scout / 北路斥候`。
- 斥候作为功能 NPC 候选，可提升侦测可信度和路径预测能力。

NPC：

- canonical：`npc_gray_lantern_keeper`、`npc_workshop_mentor`
- candidate：`npc_road_scout`

材料：

- canonical：`lantern_ash`、`conductor_filament`
- candidate-only：`charcoal_map`、`signal_wick`

资产：

- `intel_dark_echo_survey_001`：东暗回声测记，可用 canonical 材料，适合作为本阶段默认情报资产。
- `intel_shadow_tide_survey`：影潮测绘札记，机制更完整，但依赖未登记材料和旧 NPC 引用，暂时只作为候选。

玩法目的：

- 引入非战斗准备选择。
- 让侦测影响下一场战斗布置。
- 防止隐藏区域无代价揭露。

## 阶段 4：第二节点压力战 / 灯芯仓防守

Bundle：

- `examples/narrative_bundles/stage_04_wick_store_pressure_battle.narrative_event_bundle.json`

世界线：

- 影潮绕开灰灯驿站，压向 `lamp_wick_store`。
- 灯芯仓从资源存储节点变为受威胁战斗节点。
- 玩家需要保护资源设施，而不是只守前哨核心。

玩家线：

- 组合使用诱饵、护幕和爆鸣塔。
- 让前几阶段产生的资产进入同一场防守。
- 高风险高收益改造只作为后续候选，不默认进入本战。

交汇线索：

- 守住灯芯仓后发现 `glow_crystal`。
- `glow_crystal` 是稀有奖励，不应开局泛滥。
- 补线人线索加深，但仍需后续登记或任务确认。

NPC：

- canonical：`npc_gray_lantern_keeper`、`npc_workshop_mentor`
- candidate：`npc_wire_mender_003`

材料：

- canonical：`lamp_shard`、`conductor_filament`、`lantern_ash`、`glow_crystal`
- candidate-only：`charged_copper_coil`、`cracked_insulator`

资产：

- `asset_signal_wick_decoy`：诱饵道具。
- `asset_wick_barrier_pylon`：护幕支援塔。
- `asset_ash_burst_lantern`：灯灰爆鸣塔，处理聚集敌人。
- `mod_overload_chain_arc_001`：过载连弧改造，高风险候选，不进入默认 MVP 战斗。

玩法目的：

- 从单一教学陷阱进入组合防线。
- 把资源节点保护变成清晰战斗目标。
- 把稀有材料作为守成奖励，引出下一阶段路线和正式研发。

## 已可用 fixture 与待生产内容

已可用或可改编 fixture：

- `game_data/demo/first_battle_config.json`
- `game_data/demo/first_crisis_node.json`
- `examples/runtime_packages/mvp_demo.runtime_package.json`
- `examples/compiled_assets/signal_wick_decoy.compiled_asset.json`
- `examples/compiled_assets/wick_barrier_pylon.compiled_asset.json`
- `examples/compiled_assets/east_dark_echo_survey.compiled_asset.json`
- `examples/compiled_assets/ash_burst_lantern.compiled_asset.json`

候选或待修正：

- `examples/compiled_assets/shadow_tide_survey.compiled_asset.json`：依赖未登记材料和旧 NPC 引用。
- `examples/compiled_assets/overload_chain_mod.compiled_asset.json`：高风险改造，依赖未登记材料和电力上下文。
- `npc_wire_mender_003`：需要后续 NPC 登记或任务确认。
- `npc_road_scout`：需要后续 NPC 登记或任务确认。
- `game_data/demo/second_battle_config.json`：尚未创建，应服务灯芯仓防守。
- 后续 `WorldStateDelta` 文件：本批 bundle 只提出变化意图，正式运行前应生成并审查每阶段 delta。

不纳入本 MVP 剧情包：

- `examples/intent_specs/alchemy_furnace_tower.*.json`：适合测试自由输入编译链路，但不适合当前灯火世界 MVP 正式内容。
- `examples/compiled_assets/mirror_lure_trap.compiled_asset.json`：材料未登记。
- `examples/compiled_assets/light_slow_tower.compiled_asset.json`：旧通用 fixture，可作平衡参考，不进入本批审查包。

## Commit Gate 拦截规则

正式落地前，Commit Gate 至少要拦截：

- 玩家可见文本出现 `AI`、`provider`、`schema`、`prompt`、`compiler`、`mock`、`simulation`、`trace` 等技术词。
- 任何直接改写基础世界书的行为。
- 未登记 NPC、材料、地图节点、敌人直接进入正式状态。
- 第一战突破“一次现场试作”和“样品中途送达”的硬约束。
- 无成本、无上限、无阶段限制、无放置限制的过强效果。
- 情报资产无代价揭露隐藏区域，或直接造成伤害。
- 只有氛围文字但没有玩法目的、玩法 hook 或受控变化摘要的剧情节点。
- 引用不存在 ID 的状态操作。

## 审查建议

这批内容可以作为 MVP 教学关加一段后续扩展的审查基础。建议先人工确认四阶段方向，再进入下一轮：

- 为阶段 2 到 4 生成实际 `WorldStateDelta` fixture。
- 为阶段 4 生成 `second_battle_config`。
- 选择是否把 `npc_wire_mender_003` 或 `npc_road_scout` 提升为 canonical NPC。
- 对 `asset_signal_wick_decoy`、`asset_wick_barrier_pylon`、`intel_dark_echo_survey_001`、`asset_ash_burst_lantern` 做资产晋升报告。
