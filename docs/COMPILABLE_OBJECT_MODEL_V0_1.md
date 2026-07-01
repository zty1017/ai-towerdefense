# 可编译游戏对象模型 v0.1

本文档记录当前架构口径：项目不只是“AI 生成塔防素材”，而是一个面向游戏运行时的 AI 内容编译器。

## 定义

AI 可编译对象是指：

> 可以由玩家、系统、NPC 或开发者意图描述，经由结构化 Schema 表达，再通过 DAG 管线生成资产、逻辑、配置或状态变化，并通过校验后进入运行时或审查流程的游戏对象。

一个对象能否纳入编译体系，取决于它是否满足六个条件：

1. 可描述：能被自然语言或结构化字段表达。
2. 可结构化：能落到明确 Schema。
3. 可分解：能拆成资产、逻辑、配置、依赖和状态变化。
4. 可校验：能判断是否合法、平衡、可运行、可收束。
5. 可导出：能转换成 runtime package、RunWorldState、WorldStateDelta、locked manifest 或 review pack。
6. 可执行：能被战斗、地图、任务、研发、剧情或审查系统消费。

因此，可编译对象不一定是“物体”。防御塔、技能、素材、任务、随机事件、剧情节点、NPC 建议、地图节点、蓝图、科技树、编译报告都可以是可编译对象。

## 权限等级

不是任何对象都适合由玩家自由生成。当前采用五级权限：

| 等级 | 名称 | 玩家开放策略 | 说明 |
|---|---|---|---|
| L1 | 表现编译 | 可开放 | 名称、说明、图标、外观、特效、报告文本。 |
| L2 | 实体编译 | 受控开放 | 防御塔、道具、陷阱、样品、NPC、怪物等完整实体。 |
| L3 | 行为与局部叙事编译 | 强约束开放 | 技能、Buff、任务、随机事件、NPC 建议等状态机对象。 |
| L4 | 系统规则编译 | 系统辅助 | 地图、经济、进度、科技树、关卡规则、全局状态。 |
| L5 | 引擎与底层编译 | 开发者工具链 | 存档、寻路、渲染、底层代码、安全策略。MVP 不进入玩家侧编译。 |

MVP 玩家侧主要展示 L2 防御塔 / 道具 / 样品，以及少量 L3 局部行为。L4 由系统和审查流程生成，玩家可以影响但不应自由改写。

## 对象分层

当前目录使用以下层：

- `visual`：图像、图标、动画、特效、音效、表现文本。
- `entity`：防御塔、支援道具、临时样品、怪物、NPC、可交互物。
- `behavior`：技能、触发器、状态效果、临时改制、目标选择器。
- `rule`：世界 flag、羁绊、解锁规则、系统规则。
- `level`：地图节点、战斗节点、路径、波次、关卡环境。
- `narrative`：阶段剧情、任务、随机事件、事实、对话、分支。
- `progression`：研发任务、蓝图、科技节点、长期成长。
- `economy`：素材、资源、掉落、配方、建造成本。
- `adaptive`：玩家画像、难度调节、AI Director。
- `ui_explanation`：教程、复盘、编译报告、局势解释。
- `toolchain`：DAG 模板、Validator、测试套件、Prompt 模板。

## Object Graph 与 Compile DAG

不要把整个游戏编译成一张巨大 DAG。应拆成两层：

- `Object Graph`：对象之间的依赖关系，例如防御塔依赖技能、特效、素材、NPC 评审、蓝图。
- `Compile DAG`：单个对象如何从意图生成、合法化、校验、导出。

例如一个防御塔对象可以依赖：

```text
Tower
  -> Skill
  -> VFX
  -> Material
  -> RuntimeMediaManifest
  -> LockedManifest
```

而塔本身的编译 DAG 是：

```text
玩家构想
  -> Intent
  -> DesignSpec
  -> LegalizedSpec
  -> AssetPlan
  -> CompiledAssetCandidate
  -> Validate / Simulate / Score
  -> Media DAG
  -> Runtime Package
```

剧情、任务和随机事件也类似：

```text
世界状态 / 战斗结果 / 玩家行为
  -> NarrativeEventBundle
  -> WorldStateDelta
  -> Semantic Gate
  -> StageCandidatePack
  -> RunWorldState
```

## Runtime Contract

每个可编译对象都必须有运行时契约摘要：

- `load_surface`：它被哪里加载，例如 battle runtime、RunWorldState、StageCandidatePack。
- `state_effects`：它会影响哪些状态或玩法表面。
- `export_status`：runtime_ready、fallback_ready、candidate_only、review_only、not_exported。
- `rollback_policy`：如何回滚，例如 delta replay 或从 runtime package 移除。
- `player_visible`：玩家是否能看到。
- `risk_level`：低、中、高风险。

这个契约是项目区别于普通“AI 生内容”的关键：对象不是一段素材，而是可以被运行、审查和回滚的结构。

## 当前目录产物

当前实现：

- `shared/schemas/compilable_object_catalog.v0.1.schema.json`
- `shared/schemas/compilable_object_plan.v0.1.schema.json`
- `tools/content_pipeline/build_compilable_object_catalog.py`
- `tools/content_pipeline/build_compilable_object_plan.py`
- `tools/content_pipeline/validate_compilable_object_catalog.py`
- `tools/content_pipeline/validate_compilable_object_plan.py`
- `examples/review_packs/mvp_compilable_object_catalog.v0.1.json`
- `examples/review_packs/mvp_next_stage_compilable_object_plan.v0.1.json`

默认构建并校验：

```bash
python3 tools/content_pipeline/build_compilable_object_catalog.py --validate
```

当前目录从以下证据构建：

- `mvp_stage_candidate_pack.v0.1.json`
- `mvp_multistage_content_pack.v0.1.json`
- `mvp_multistage_stage_candidate_pack.v0.1.json`
- `mvp_story_asset_promotion_report.v0.1.json`
- `demo_after_stage_07_split_tide.run_world_state.json`

它不是前端数据，不读取 `.env`，不调用 provider，不修改基础世界书。

## 当前 MVP 结论

当前目录覆盖 104 个可编译对象，包含表现、实体、行为、经济、关卡、叙事、成长、规则八层。它已经吸收 Stage 05 / Stage 06 / Stage 07 的多阶段内容生产结果，因此能在一个统一 Object Graph 里审查旧四阶段纵切和后续三阶段候选链。

这说明当前系统已经不只是能审查“防御塔资产”，也能审查：

- 阶段剧情是否落到玩法对象。
- 地图节点、任务、随机事件是否进入运行态。
- 研发任务、蓝图、样品是否形成成长链。
- 素材和资源是否作为编译能力与约束存在。
- 哪些资产可以 runtime_ready / fallback_ready，哪些仍是 candidate_only。
- 多阶段新增的支援道具、临时改造、研发任务、临时样本、蓝图和地图节点是否与其来源阶段、依赖对象和晋级证据对应。

后续真实 LLM 生成新阶段或新资产时，应尽量提交同类目录证据，方便主代理和人工审查。

`CompilableObjectPlan v0.1` 是目录之后、真实生成之前的计划层。它会声明下一阶段需要生成哪些对象、依赖哪些现有对象、权限等级是什么、需要哪些验证门，以及失败时如何 fallback。这样 LLM 不应直接产出松散剧情，而应该先满足计划层的对象边界。
