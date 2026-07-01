# 剧情 / 玩法联合编译契约 v0.1

本文档记录当前结论：剧情编译不是单独“根据世界书写剧情”，而是把世界剧情线、玩家游玩线和玩法对象一起编译。

世界书提供风格、禁区、角色关系和解释边界；游戏底层框架提供地图、战斗、资源、任务、研发和资产约束。AI 只能在这两者之间生成受控内容，不能自由续写基础世界书，也不能只产出没有玩法落点的氛围文本。

## 三层产物

一次剧情推进至少经过三层：

1. `NarrativeEventBundle`
   - 表达阶段、世界线 / 玩家线、触发条件、展示文本。
   - 每个节点必须声明 `gameplay_purpose` 和 `gameplay_hooks`。
   - 每个节点必须引用将要提交的 `WorldStateDelta`。

2. `WorldStateDelta`
   - 把剧情意图转成可执行 op。
   - 可以引入或推进地图节点、NPC、资源、任务、随机事件、研究任务、样品和蓝图。
   - 不允许修改基础世界书。

3. `RunWorldState`
   - 应用 delta 后的单局状态。
   - 它是前端、战斗和后续 AI 编译的真实上下文。
   - 任务、随机事件、研究任务等对象必须在这里可追踪。

## 硬性规则

- 剧情节点不能只写对白或旁白，必须有玩法目的。
- 剧情节点的 `gameplay_hooks` 必须能在对应 delta 中找到支持它的 op 类型。
- 任务、随机事件、研究任务、蓝图、样品、NPC、地图节点等新对象必须最终落到 `RunWorldState`。
- 世界线推进可以异步生成压力、传闻、资源问题和 NPC 线索，但必须服务于后续玩法。
- 玩家线推进可以生成研发需求、样品反馈、任务奖励和战斗复盘，但必须能影响后续可玩资产或决策。
- 基础世界书不在运行时被直接改写；单局变化写入 `RunWorldState` 或审查过的派生资产。

## 软性告警

有些 `target_ref` 是抽象设计 token，例如“组合防守”“风险取舍”“下一夜路线选择”。MVP 阶段允许它们先作为告警存在，但后续应该逐步 ID 化成任务、事件、节点、资产、材料或系统标志。

## 校验器

跨文件契约校验命令：

```bash
python3 tools/narrative/validate_narrative_gameplay_contract.py examples/review_packs/mvp_story_asset_review_pack.v0.1.json
```

该命令会检查：

- 审查包中的每个阶段 bundle 都能通过 `NarrativeEventBundle` 校验。
- 每个 narrative node 引用的 `WorldStateDelta` 文件存在。
- 每个玩法 hook 都有对应的 delta op 类型支撑。
- 被 delta 引入的玩法对象最终出现在 `demo_after_stage_04_wick_store.run_world_state.json`。
- 四阶段链路不是纯剧情文本，而是持续产生地图、资源、NPC、任务、随机事件、研究任务、样品和蓝图。

真实 LLM 生成入口也应遵守同一契约：

```bash
python3 tools/llm/generate_world_delta.py \
  --run-world-state examples/run_world_states/demo_initial.run_world_state.json \
  --battle-result examples/asset_graph/battle_result.sample.json \
  --session-context examples/asset_graph/session_context.sample.json \
  --review-pack examples/review_packs/mvp_story_asset_review_pack.v0.1.json \
  --output /tmp/live_world_delta.json \
  --apply-output /tmp/live_next_run_world_state.json \
  --provider-profile ark_deepseek_v4_flash \
  --live
```

该 CLI 没有 `--live` 时不会加载 `.env` 或调用 provider；live 模式下会先做结构校验，再默认执行 `validate_world_delta_semantics.py`。

默认情况下，抽象 `target_ref` 只作为 warning 输出，不阻断 MVP 审查。需要更严格时可使用：

```bash
python3 tools/narrative/validate_narrative_gameplay_contract.py \
  examples/review_packs/mvp_story_asset_review_pack.v0.1.json \
  --warnings-as-errors
```

## 当前 MVP 解释

当前四阶段样例应被理解为：

- Stage 01：首战教学与样品送达，产出战后样品和首战完成状态。
- Stage 02：清晨复盘与补给线压力，产出资源节点、功能 NPC、任务、随机事件和诱饵研发。
- Stage 03：北路侦察，产出情报资产、侦察任务、旧信标塔压力事件和研究任务。
- Stage 04：灯芯仓压力防守，结算资源节点防守、解锁灯灰爆鸣塔蓝图，并留下后续路线选择。

这说明剧情编译和玩法编译不是两条分离流水线，而是同一条受控世界推进流水线的两个视角。
