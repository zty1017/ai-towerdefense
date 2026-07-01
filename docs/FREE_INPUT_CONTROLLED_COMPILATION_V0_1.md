# 自由输入与受控编译 v0.1

Last updated: 2026-07-01

## 1. 核心原则

本项目允许玩家用自然语言自由表达想法，但不允许自然语言直接进入游戏执行层。

产品侧原则：

```text
玩家输入可以自由，底层执行必须受控。
```

工程侧原则：

```text
自然语言
  -> 隐藏中间表示
  -> 合法化 / 降维 / 补全
  -> 资产计划
  -> 玩法、表现、媒体分层编译
  -> 可校验 runtime package
```

这意味着 Compiler 的亮点不是“玩家一句话让 AI 直接画一张塔”，而是：

```text
玩家一句话
  -> AI 理解需求
  -> 编译成结构化设计规范
  -> 按规范生成、拼装、清洗素材
  -> 输出可运行游戏单位
```

## 2. 为什么不能自由执行

玩家可以说：

```text
我想要一个像炼丹炉一样的塔，会吸敌人过来，再喷紫火，杀怪后越来越强。
```

这句话可以作为创作输入，但不能直接交给图像模型或战斗引擎。

因为图像模型只会努力生成“看起来像”的图片，不会自动产出：

- 统一视角的干净塔本体
- 独立攻击特效
- 发射点、锚点、占地和碰撞框
- 可配置攻击逻辑
- 与现有模块兼容的 effect blocks
- 可被前端加载的 atlas / manifest
- 可被模拟器验证的数值结构

所以系统必须把“自由需求”映射到“有限可编译空间”。

## 3. 隐藏中间表示

玩家侧永远看到自然语言、研发提案、NPC 评审和世界内反馈。

系统内部新增以下隐藏层：

```text
PlayerUtterance
  玩家原始输入。

PlayerIntent
  LLM 解析后的语义意图，只描述玩家想要什么。

AssetDesignSpec
  隐藏 DSL / Schema，描述视觉、玩法、平衡、世界观需求。

LegalizedDesignSpec
  经合法化层处理后的规格，只包含当前版本可执行或可降级执行的内容。

AssetPlan
  面向 DAG 的产物计划，拆出 gameplay、presentation、media、runtime metadata。

Proposal
  玩家可见研发方案，不是可玩资产。

CompiledAssetCandidate
  结构化编译资产候选，通过校验后才可能进入战斗。
```

推荐主链路：

```text
PlayerUtterance
  -> PlayerIntent
  -> AssetDesignSpec
  -> LegalizedDesignSpec + LegalizationReport
  -> AssetPlan
  -> Proposal
  -> CompiledAssetCandidate
  -> Validate / Simulate / Score / Promotion
  -> MediaPlan / PublishedMedia
  -> RuntimePackage
```

`Proposal` 仍然是玩家可见的方案或提案，不是 AI 编译后的结果。它不应该替代隐藏 DSL，也不应该承载完整 runtime 数据。

## 4. AssetDesignSpec 草案

`AssetDesignSpec` 是隐藏 DSL，不进入玩家界面。

示例：

```json
{
  "schema_version": "asset_design_spec.v0.1",
  "asset_kind": "tower_blueprint",
  "theme": {
    "archetype": "alchemy_furnace",
    "world_tags": ["field_research", "night_fire"],
    "tone": "dangerous_but_useful"
  },
  "visual": {
    "view": "isometric_3_4",
    "style_id": "compiler_td_v1",
    "body_archetype": "furnace",
    "materials": ["dark_metal", "ceramic_core"],
    "core_element": "purple_fire",
    "body_layers": ["base", "furnace_body", "core_window", "ornament"],
    "vfx_layers": ["pull_ring", "flame_cone", "stack_glow"],
    "constraints": {
      "single_subject": true,
      "clean_background": true,
      "no_enemy_in_sprite": true,
      "no_attack_effect_on_body_sprite": true
    }
  },
  "gameplay": {
    "attack_pattern": "cone_damage_over_time",
    "control_effect": "pull_in",
    "growth_mechanic": "gain_stack_on_kill",
    "targeting": "dense_area",
    "intended_role": ["area_damage", "soft_control"]
  },
  "balance": {
    "risk_tier": "high",
    "cost_band": "expensive",
    "control_strength_cap": "medium",
    "growth_cap": "limited"
  },
  "world_fit": {
    "source_materials": ["unstable_core", "ash_residue"],
    "npc_disciplines": ["field_engineer", "occult_researcher"],
    "facility_requirement": "field_workbench"
  }
}
```

## 5. 合法化层

`LegalizeDesignSpec` 是自由输入和可执行系统之间的硬边界。

它至少负责：

- 冲突检测：例如同一资产同时要求极低成本、强控制、高伤害、无限成长。
- 降维映射：把未知机制映射到当前注册模块，或转成 `proposal_new_effect`。
- 缺字段补全：补齐视角、锚点、占地、攻击 socket、可用媒体角色。
- 平衡裁剪：按预算、关卡进度、材料、NPC、设施把数值压回合法区间。
- 世界观校验：把明显不符合世界书的表达改写成当前世界可接受的解释。
- 媒体约束：强制单主体、干净背景、角色拆分、无 provider 临时 URL。
- 失败回退：不能稳定编译时，输出降级方案或仅生成研发提案。

合法化不是“让 AI 少创造”，而是让 AI 的创造能落到游戏里。

## 6. 资产拆分

战斗类资产不能被视为一张图片。它必须被拆成 package manifest 中的多个产物。

防御塔至少应拆为：

```text
tower_body              干净塔本体 sprite 或帧序列
tower_icon              UI 图标
selection_ring          选择圈，可由前端程序化绘制
shadow                  阴影，可由前端或素材生成
projectile              投射物，可选
attack_vfx              攻击特效 recipe 或序列帧
impact_vfx              命中特效 recipe 或序列帧
unit_meta               锚点、占地、碰撞、socket、atlas frame
gameplay_config         effect blocks、targeting、cost、cooldown、range
presentation            名称、描述、世界内说明、NPC 评语
```

媒体产物必须遵循：

```text
raw_media -> processed_media -> published_media -> runtime package
```

只有 `published_media` 可以被前端运行时加载。

## 7. 三档自由度

MVP 默认采用第一档。

### 7.1 受控自由

玩家自然语言自由，但系统只能映射到已注册资产类型、effect blocks、视觉角色和媒体后处理流程。

这是默认 runtime_safe。

### 7.2 组合自由

允许在已有模块之间做更复杂组合，例如控制 + DOT + 成长，但必须经过预算和模拟。

这适合 runtime_experimental 或拥有相关 NPC / 材料 / 设施后解锁。

### 7.3 开放创造

允许 AI 提出新机制、新节点、新字段、新规则。

只允许 studio_mode 或明确提权的研发模式。运行时不能直接注册新执行逻辑。

## 8. 对玩家体验的要求

技术细节不进入玩家侧体验。

玩家看到的是：

- 自己提出构想
- 世界内角色理解和评审
- 材料、设施、NPC、风险与代价
- 研发等待或战斗中途送达
- 试作品的战斗表现
- 战后反馈和世界状态变化

玩家不应该看到：

- provider / model
- prompt / schema / JSON parse
- raw trace / stack trace
- API rate limit / token usage
- 不适合世界观的技术错误

技术日志可以进入 Studio 证据、录屏脚本或开发者 trace，但不能污染玩家沉浸感。

## 9. 与现有文档的关系

本文件不是替代 `AI_ASSET_COMPILER_V0_1.md`，而是补齐其中“自然语言到 Proposal / Candidate 之间”的隐藏编译层。

本文件也不是替代 `ASSET_GRAPH_COMPILER_V0_1.md`，而是为 AssetGraph 增加一组协议节点：

```text
intent.parse_player_utterance_guarded
asset.build_design_spec_guarded
asset.legalize_design_spec
asset.build_asset_plan
proposal.build_from_legalized_spec
```

这些节点先作为协议和 workflow 边界存在，后续再逐步实现真实执行器、schema、测试 fixture 和前端 runtime package 对接。

## 10. DAG 与 ReAct 的分工

项目采用混合模式：

```text
DAG 是可执行的编译管线。
LLM + ReAct 是规划器、调度器和修复器。
```

LLM / ReAct 不直接生成游戏对象，也不自由调用任意工具。它只负责：

- 理解玩家需求。
- 生成隐藏结构化规格。
- 选择对象级 DAG 模板。
- 填充节点参数。
- 根据校验报告做有限修复。

DAG 负责：

- 节点执行。
- 中间产物管理。
- 缓存和并行。
- 失败回滚。
- trace 和日志。
- 最终 runtime bundle 导出。

### 10.1 不从零生成任意 DAG

MVP 不允许 LLM 任意生成全新图。

第一阶段只允许选择对象级模板：

```text
TowerCompileGraph
SupportItemCompileGraph
TemporaryModCompileGraph
IntelAssetCompileGraph
SkillVFXCompileGraph
IconCompileGraph
MapModifierCompileGraph
```

第二阶段允许局部分支：

```text
projectile 攻击 -> projectile media branch
beam 攻击       -> beam visual recipe branch
aura 攻击       -> aura field branch
summon 机制     -> summon unit proposal branch
```

第三阶段才允许有限图变换：

```text
add_node
remove_node
replace_node
reroute_branch
increase_candidate_count
fallback_to_template
```

所有图变换都必须通过类型检查、预算检查和 runtime_public 安全检查。

### 10.2 ReAct 主要用于修复

常规路径不触发 ReAct：

```text
parse -> legalize -> compile -> validate -> export
```

只有出现明确失败原因时才触发修复，例如：

- 背景残留。
- 主体不完整。
- 塔本体混入攻击特效。
- 风格不一致。
- 玩法配置冲突。
- 平衡超限。
- 缺失锚点、发射点、占地或碰撞信息。

ReAct action set 必须有限：

```text
inspect_spec
inspect_artifact
inspect_validation_report
patch_spec
patch_prompt
rerun_node
increase_candidates
replace_with_template
split_asset_layer
fallback_to_preset
accept_with_warning
abort_compile
```

每次编译还必须有预算上限：

```text
最大候选数
最大修复轮数
最大 DAG 执行时间
最大 LLM 调用次数
最大图像 / 视频调用次数
失败后的强制 fallback
```

这保证比赛演示和玩家 runtime 不会因为开放式 agent loop 而无限重试。

### 10.3 校验报告驱动修复

ReAct 修复必须基于强类型 validator 的明确错误，而不是凭感觉重写。

示例：

```json
{
  "pass": false,
  "issues": [
    {
      "type": "vfx_contamination",
      "message": "tower body contains visible attack effect"
    },
    {
      "type": "background_residue",
      "message": "non-transparent background remains around bottom edge"
    }
  ]
}
```

对应修复动作应是：

```text
patch_prompt(body role: clean body only, no attack effect)
rerun_node(body image generation)
rerun_node(background removal)
rerun_node(body validator)
```

这样系统可以复现、调试和解释每次修复，而不是把失败掩盖成一次新的不可控生成。

## 11. Schema 与示例路径

v0.1 的协议 Schema 和示例 fixture 路径如下。

### 11.1 JSON Schema

```text
shared/schemas/player_utterance.v0.1.schema.json
shared/schemas/player_intent.v0.1.schema.json
shared/schemas/asset_design_spec.v0.1.schema.json
shared/schemas/legalized_design_spec.v0.1.schema.json
shared/schemas/legalization_report.v0.1.schema.json
shared/schemas/asset_plan.v0.1.schema.json
shared/schemas/compile_template_selection.v0.1.schema.json
shared/schemas/repair_action_plan.v0.1.schema.json
```

Schema 默认使用 `additionalProperties: false` 收紧结构。隐藏编译 artifact 不得包含
`provider`、`model`、`raw_prompt`、`full_trace`、`raw_json`、`api_key`、`secret`、
`unreviewed_content`。

### 11.2 示例 Fixture

```text
examples/player_inputs/alchemy_furnace_tower.player_utterance.json
examples/intent_specs/alchemy_furnace_tower.player_intent.json
examples/intent_specs/alchemy_furnace_tower.asset_design_spec.json
examples/intent_specs/alchemy_furnace_tower.legalized_design_spec.json
examples/intent_specs/alchemy_furnace_tower.legalization_report.json
examples/intent_specs/alchemy_furnace_tower.asset_plan.json
examples/intent_specs/alchemy_furnace_tower.compile_template_selection.json
examples/intent_specs/alchemy_furnace_tower.repair_action_plan.json
```

`asset_plan` 必须包含 gameplay、presentation、media_roles、runtime_metadata、fallback_plan。
`compile_template_selection.template_name` 只能引用已注册模板名，并且必须携带 budgets。
`repair_action_plan.actions[].action_type` 必须来自第 10.2 节定义的有限 action set。

### 11.3 校验脚本

```text
tools/asset_graph/validate_intent_compile_artifacts.py
tools/asset_graph/validate_compile_template_selection.py
tools/asset_graph/validate_repair_action_plan.py
```

`validate_intent_compile_artifacts.py` 支持传入一个或多个 JSON 文件，并依据 `schema_version`
自动选择对应 Schema。若本地没有 `jsonschema` 库，它会降级到基础字段检查。
