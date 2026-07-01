# AI 资产编译器 v0.1

Last updated: 2026-07-01

## 1. 目标

AI 资产编译器负责把玩家或开发者的自然语言想法，转化为游戏中可审查、可校验、可模拟、可运行的资产候选。

本项目的核心类比是：

```text
AI 辅助编程：
自然语言 -> 编码工具 -> 代码 -> 测试 -> 可运行软件

本项目：
自然语言 -> AI 结构化理解 -> 研发提案 -> AI 编译 -> 玩法校验 / 模拟 -> 可玩游戏资产
```

v0.1 的目标不是让 AI 任意改写游戏，而是建立一条稳定闭环：

```text
玩家想法
  -> PlayerIntent / AssetDesignSpec 隐藏中间表示
  -> LegalizedDesignSpec 合法化规格
  -> AssetPlan 资产计划
  -> Proposal 研发提案
  -> CompiledAssetCandidate 编译资产候选
  -> Schema / 模块 / 预算 / 世界书 / 模拟校验
  -> RuntimeAssetInstance 战斗实例
  -> 战后记录 / 稳定化 / 蓝图谱系
```

核心原则见 `docs/FREE_INPUT_CONTROLLED_COMPILATION_V0_1.md`：

```text
玩家输入可以自由，底层执行必须受控。
```

## 2. 范围

MVP 不只编译防御塔，也纳入支援道具、临时改制、情报资产，以及开发期素材。

运行时资产类型：

- `tower_blueprint`：防御塔蓝图
- `support_item`：支援道具
- `temporary_mod`：临时改制 / 战斗内插件
- `intel_asset`：情报 / 侦察 / 弱点揭示资产

开发期素材类型：

- `image_prompt`：图像 prompt
- `icon_asset`：图标素材候选
- `animation_card`：动画卡 / 过场卡候选
- `worldbook_fragment`：世界书片段
- `event_draft`：事件草稿
- `npc_fragment`：NPC 设定片段
- `material_fragment`：材料或资源设定片段

运行时资产和开发期素材共用底层管线，但可见权限不同。

## 3. 模式

### 3.1 runtime_safe

玩家常规游玩模式。

特点：

- 只能使用已注册模块。
- 只能在允许参数区间内调参。
- 必须通过预算、Schema、玩法兼容性和世界书一致性校验。
- 技术失败不扣玩家关键资源。
- 不向玩家暴露 provider、API、JSON parse、Schema stack trace 等技术细节。

### 3.2 runtime_experimental

玩家高风险研发模式。

特点：

- 允许提出边界组合或新机制雏形。
- 未注册机制不能直接进入战斗，只能转为 `proposal_new_effect`。
- 需要材料、NPC、设施、情报或剧情条件支持。
- 采用确定性风险评分，而不是 MVP 阶段真随机。
- 可能产生不稳定成功、降级成功、部分失败、材料损失、NPC 反应或知识增益。

### 3.3 studio_mode

开发者 / 内容制作模式。

特点：

- 可以看到 provider、模型、prompt、原始 JSON、校验错误、生成日志和导入导出信息。
- 允许 AI 提出新模块、新字段、新资产类型、新规则建议。
- 可以生成素材 manifest、世界书草稿、图像 prompt、动画卡、测试样例。
- 不能直接绕过 `generated -> reviewed -> locked`。

## 4. Proposal 与编译资产

必须区分两个层次。

在它们之前，还有一组玩家不可见的中间层：

- `PlayerIntent`：玩家话语的语义理解。
- `AssetDesignSpec`：隐藏 DSL / Schema，描述视觉、玩法、平衡、世界观需求。
- `LegalizedDesignSpec`：经过合法化、降维、补全和预算裁剪后的规格。
- `AssetPlan`：把玩法、表现、媒体、runtime metadata 拆成可执行 DAG 产物计划。

这些中间层不进入玩家界面，也不进入 runtime package。它们用于约束 AI，不让自由输入直接变成无约束执行。

### 4.1 Proposal

`Proposal` 是研发方案，不是可玩资产。

示例：

```text
用灯光形成减速场，但需要持续供电。适合对抗高速敌人，但会增加电力压力。
```

它的作用是：

- 表达研发方向
- 暴露风险和成本预估
- 让 NPC、材料、设施和玩家补充提示词影响方案
- 作为后续编译的约束输入

默认只生成 1 个 Proposal。更多 Proposal 由条件触发：

- 相关 NPC 参与
- 特殊材料加入
- 技术 / 设施支持
- 玩家要求“再想一个方向”
- `runtime_experimental` 高风险研发

Proposal 操作：

- `choose`：选择方案进入编译
- `revise`：追加提示词修改方案
- `ask_npc`：让 NPC 评审或提出替代思路
- `use_material`：投入材料改变方向
- `risk_upgrade`：转为高风险研发
- `discard`：放弃

### 4.2 CompiledAssetCandidate

`CompiledAssetCandidate` 是结构化编译结果，必须经过校验后才可能进入战斗。

操作：

- `accept_for_battle`：接受进入本场战斗
- `test_simulation`：运行无头 mock simulation
- `repair`：根据校验失败原因修复
- `stabilize`：消耗资源稳定化
- `discard`：放弃

## 5. Proposal Schema 草案

```json
{
  "id": "proposal_light_slow_field_001",
  "mode": "runtime_safe",
  "title": "光幕迟滞方案",
  "summary": "使用持续灯光形成减速场，压制高速敌人，但需要稳定供电。",
  "intended_asset_type": "tower_blueprint",
  "expected_effect": ["control", "support"],
  "risk_level": "medium",
  "estimated_cost": "medium",
  "required_inputs": {
    "npc_ids": ["engineer_001"],
    "materials": ["focusing_lens"],
    "facility": "workshop_level_1",
    "knowledge_tags": ["basic_power_grid"]
  },
  "known_tradeoffs": [
    "无直接伤害",
    "持续消耗电力",
    "对高速敌人收益更高"
  ],
  "player_prompt": "我想要一座用灯光减速敌人、但会消耗额外电力的防御塔。",
  "worldbook_id": "long_night_lanterns"
}
```

## 6. 编译产物三层结构

`CompiledAssetCandidate` 拆成三层：

```text
CompiledAssetCandidate
  gameplay
  presentation
  provenance
```

### 6.1 gameplay

游戏运行时真正读取的结构化规则。

必须严格校验，不能包含任意自然语言机制。

结构：

```text
gameplay = asset_type + shared effect_blocks + type_specific fields
```

### 6.2 presentation

展示、文案和美术信息。

可以由 AI 更自由地生成，但不能影响运行时规则。

包括：

- 名称
- 简短描述
- 详细说明
- 图标 prompt
- 动画卡 prompt
- 视觉标签
- 音效提示
- UI 稀有度 / 风格

### 6.3 provenance

来源和治理信息。

包括：

- 来源 Proposal
- mode
- provider / model
- prompt 摘要
- NPC / 材料 / 设施参与
- 世界书
- 校验结果
- 模拟报告
- fallback 记录
- 人工审查备注

## 7. CompiledAssetCandidate Schema 草案

```json
{
  "id": "asset_light_slow_tower_001",
  "lifecycle": "ephemeral",
  "gameplay": {
    "asset_type": "tower_blueprint",
    "base_stats": {
      "build_cost": 160,
      "range": 140,
      "cooldown": 1.0,
      "targeting": "nearest"
    },
    "effect_blocks": [
      {
        "type": "slow",
        "slow_ratio": 0.35,
        "duration": 1.8,
        "stacking": "refresh"
      },
      {
        "type": "aura_buff",
        "radius": 110,
        "target": "enemy",
        "effect_ref": "slow"
      },
      {
        "type": "power_cost",
        "power_per_second": 4,
        "shutdown_behavior": "disable_effects"
      }
    ],
    "constraints": {
      "requires_power_grid": true,
      "max_instances": 2,
      "allowed_phases": ["battle"]
    },
    "type_specific": {
      "tower_slot": "standard",
      "upgrade_from": "basic_light_tower"
    }
  },
  "presentation": {
    "name": "聚光迟滞塔",
    "short_description": "用稳定灯幕拖慢敌人，但会持续消耗电力。",
    "icon_prompt": "2D game icon, brass lantern turret, blue-white light beam, clean silhouette",
    "animation_card_prompt": "A 2D pseudo-isometric lantern turret casting a slow pulsing light field on a dark path"
  },
  "provenance": {
    "proposal_id": "proposal_light_slow_field_001",
    "mode": "runtime_safe",
    "worldbook_id": "long_night_lanterns",
    "provider": "ark",
    "model": "deepseek-v4-pro",
    "npc_ids": ["engineer_001"],
    "material_ids": ["focusing_lens"],
    "validation_status": "pending",
    "simulation_report_id": null
  }
}
```

## 8. 生命周期

AI 编译资产有三层生命周期。

### 8.1 ephemeral

一次性资产。

适合：

- 支援道具
- 临时改制
- 战斗内实验品
- 未稳定高风险产物

### 8.2 session_blueprint

本局可复用资产。

适合：

- 本次 run 研发出的防御塔
- 本次战役可持续使用的支援道具
- 已经通过数值校验但尚未稳定化的蓝图

### 8.3 stabilized_blueprint

长期稳定资产。

进入条件可以包括：

- 消耗资源稳定化
- NPC 协助
- 通过测试
- 完成剧情条件
- 人工 / AI Reviewer 审查

稳定后进入：

- 蓝图谱系
- 图鉴
- locked 游戏数据
- 长期可用库

## 9. effect_blocks 白名单

v0.1 使用严格白名单。

```text
damage
area_damage
slow
damage_over_time
pierce_or_chain
summon_unit
shield
repair
power_cost
charge_burst
mark_vulnerability
trap_tile_effect
aura_buff
scout_reveal
weakness_tag
path_prediction
threat_forecast
countermeasure_hint
risk_modifier
```

规则：

- `runtime_safe` 中未知 effect 直接校验失败，进入 repair。
- `runtime_experimental` 中未知 effect 转为 `proposal_new_effect`，不能直接进入战斗。
- `studio_mode` 中未知 effect 可以进入新模块提案流程。

## 10. 白名单不是终点

v0.1 的白名单是自举安全边界，不是长期创造力上限。

当前阶段必须限制 AI 直接运行新机制，因为：

- 运行时尚未实现任意机制解释器。
- 数值模拟需要确定性。
- 战斗表现需要前端支持。
- 未注册机制无法测试和调平。

但长期目标可以是 AI-friendly 的资产编译管线：

```text
AI 提出新机制
  -> 生成新模块提案
  -> 生成 Schema 草案
  -> 生成预算规则草案
  -> 生成 mock simulation 测试样例
  -> 生成前端表现建议
  -> 人类 / AI Reviewer 审查
  -> 实现任务
  -> 测试通过
  -> registered_module
  -> 可被 runtime 使用
```

也就是说，AI 未来可以帮助扩展白名单本身，但不能在玩家运行时绕过注册流程。

建议阶段：

| 阶段 | 能力 | 安全边界 |
|---|---|---|
| v0.1 | 固定白名单 + 参数编译 | AI 只能组合已注册模块 |
| v0.2 | studio_mode 新模块提案 | AI 可提出新 effect，但不能运行 |
| v0.3 | AI 生成 Schema / 测试 / 预算草案 | 必须人工或 AI Reviewer 审查 |
| v0.4 | AI 辅助实现模块代码 | 必须测试、沙盒、代码审查 |
| v1.x | 半自动模块扩展管线 | 仍需注册、版本化和回滚机制 |

## 11. 风险评分

MVP 的 `runtime_experimental` 使用确定性风险评分，不先做真随机。

```text
risk_score =
  proposal_risk
  + material_instability
  + mechanism_novelty
  + power_overload
  - npc_support
  - facility_level
  - known_blueprint_similarity
```

结果区间：

| risk_score | 结果 |
|---:|---|
| 0-20 | `clean_success` |
| 21-40 | `downgraded_success` |
| 41-65 | `unstable_success` |
| 66-85 | `partial_failure` |
| 86+ | `hard_failure` |

风险结算只适用于设定内研发风险，不适用于真实系统错误。

## 12. 失败分类

### 12.1 技术失败

真实系统、API 或管线问题。

示例：

- provider timeout
- provider rate limited
- provider auth error
- invalid JSON
- schema validation failed
- repair exhausted
- asset download failed
- backend exception

玩家层表达应低违和：

- “编译器暂时过载，请稍后重试。”
- “工坊链路不稳定，这次推演未能完成。”
- “方案没有损坏，材料未被消耗。”

系统层记录真实诊断：

```text
provider_rate_limited
provider: glmfree
http_status: 429
model: glm-4.7-flash
fallback_attempted: true
```

技术失败不扣玩家关键资源。

### 12.2 规则失败

条件不满足导致不能提交。

示例：

- 材料不足
- 设施等级不够
- NPC 不愿意参与
- 当前节点缺少情报
- 技术前置缺失

这是确定性阻止，不需要随机率。

### 12.3 研发风险失败

玩家选择 `runtime_experimental` 后的设定内结果。

示例：

- 不稳定材料反应
- 过载副作用
- NPC 信任下降
- 只获得知识增益，没有生成资产
- 降级成功

## 13. 资源扣除提交点

资源不应在技术调用前就被永久扣除。

建议流程：

```text
玩家输入想法
  -> 生成 Proposal：通常不扣关键资源
  -> 选择 Proposal：可以预占材料
  -> 技术编译成功：仍不立刻扣除
  -> 玩家确认正式投入 / 实验
  -> 扣除材料、NPC 时间、设施次数或研发机会
  -> runtime_experimental 风险评分结算
```

规则：

- 普通 Proposal 免费或消耗轻量行动机会。
- NPC 评审可消耗 NPC 时间 / 好感 / 当天行动机会。
- 使用材料引导方向先预占，正式投入后扣除。
- 技术失败不扣关键资源。
- 设定内高风险研发在正式投入后可能损失资源。

## 14. 无头 mock simulation

MVP 先做无头数值模拟，不做复杂 UI 测试。

输入：

- `CompiledAssetCandidate`
- 固定敌人样本：普通、快速、重甲
- 固定路径
- 固定模拟时间
- 固定资源 / 电力预算

输出：

- `estimated_dps`
- `slow_uptime`
- `enemies_leaked`
- `power_peak`
- `cost_efficiency`
- `balance_flags`

作用：

- 检测过强 / 过弱
- 检测能耗是否有意义
- 检测控场覆盖是否过高
- 为自动修复提供依据
- 生成 `simulation_report`

UI 验收放在垂直切片完成后做，不作为编译器第一步。

## 15. v0.1 最小闭环

```text
玩家输入想法
  -> 生成 1 个 Proposal
  -> 玩家 choose / revise / ask_npc / use_material
  -> 编译为 CompiledAssetCandidate
  -> Schema 校验
  -> effect_blocks 白名单校验
  -> 预算校验
  -> 世界书一致性检查
  -> 无头 mock simulation
  -> repair / downgrade / accept_for_battle
  -> RuntimeAssetInstance
  -> 战后记录
  -> 可选 stabilize
```

## 16. MVP 暂不做

- 真随机研发失败率
- AI 直接改写运行时代码
- 玩家运行时注册新 effect
- 完整图形化调参器
- 复杂 UI 自动测试
- 视频生成进入实时战斗闭环
- 多人账户系统

## 17. 当前落地文件

v0.1 已经落地为：

```text
shared/schemas/proposal.v0.1.schema.json
shared/schemas/asset_compiler.v0.1.schema.json
shared/schemas/simulation_report.v0.1.schema.json
shared/module_registry/effect_blocks.v0.1.json
examples/proposals/light_slow_field.proposal.json
examples/compiled_assets/light_slow_tower.compiled_asset.json
tools/content_pipeline/validate_proposal.py
tools/content_pipeline/mock_compile_proposal.py
tools/content_pipeline/validate_asset_candidate.py
tools/content_pipeline/simulate_asset_candidate.py
tools/content_pipeline/run_mock_pipeline.py
```

本地校验：

```bash
python3 tools/content_pipeline/validate_proposal.py examples/proposals/light_slow_field.proposal.json
python3 tools/content_pipeline/validate_asset_candidate.py examples/compiled_assets/light_slow_tower.compiled_asset.json
```

本地 mock 编译链路：

```bash
python3 tools/content_pipeline/mock_compile_proposal.py \
  examples/proposals/light_slow_field.proposal.json \
  --output /tmp/light_slow_from_proposal.compiled_asset.json

python3 tools/content_pipeline/validate_asset_candidate.py \
  /tmp/light_slow_from_proposal.compiled_asset.json
```

一键 mock pipeline：

```bash
python3 tools/content_pipeline/run_mock_pipeline.py \
  examples/proposals/light_slow_field.proposal.json \
  --output-dir /tmp/ai_compiled_td_mock_runs
```

该命令会输出：

```text
compiled_asset.json
simulation_report.json
pipeline_report.json
```

当前校验脚本不依赖第三方库。它不是完整 JSON Schema validator，而是优先检查 AI 输出最容易失控的部分：

- Proposal 必填字段
- Proposal 的 mode / intended_asset_type / risk_level / estimated_cost
- 顶层结构
- 生命周期
- mode
- asset_type
- presentation 必填字段
- effect_blocks 白名单
- effect 必填字段
- effect 数值区间
- effect 与 asset_type 是否兼容
