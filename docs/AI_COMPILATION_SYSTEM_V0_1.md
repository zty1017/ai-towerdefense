# AI 编译系统总架构 v0.1

Last updated: 2026-07-02

本文是项目级 AI 编译系统的概念与边界事实源。若早期文档中关于“AI 资产编译器”“世界书”“剧情编译”“地图编译”“媒体生成”的描述与本文冲突，以本文的分层、权限和生命周期边界为准。

本文不替代具体 schema、semantic gate 或工具脚本。字段级事实源仍以 `shared/schemas/`、`tools/` 和对应专题文档为准；本文只规定这些对象为什么存在、彼此如何分工、哪些东西不能绕过校验进入运行时。

本项目不是单纯让 LLM 生成文本、图片或 JSON，而是把玩家、系统、开发者或发布层的意图，在世界状态、玩法规则、运行时契约、调度约束和校验器共同限制下，转化为可运行、可验证、可回滚的游戏对象与世界状态变化。

## 0. 事实源层级

当前文档层级按以下顺序使用：

```text
docs/CURRENT_ARCHITECTURE_INDEX.md
  -> 导航、阅读顺序、当前有效文档入口

docs/AI_COMPILATION_SYSTEM_V0_1.md
  -> AI 编译系统的概念、边界、权限、生命周期事实源

shared/schemas/ + tools/ + 专题文档
  -> 字段级、白名单、校验器、运行命令事实源
```

如果本文中的概念名称与现有 schema 字段不完全一致，以具体 schema 和校验器为准；本文应在下一轮修订中补齐映射，而不是要求实现层直接改名。

### 0.1 执行冻结规则

后续 worker、子代理和人工实现应按以下规则使用本文：

- 本文可以定义概念、边界、生命周期和权限，但不能单独发明运行时字段。任何要被代码读取的字段，都必须落到 `shared/schemas/`、`tools/` 或对应专题文档。
- 字段级冲突时，以当前 schema、校验器和构建脚本为准；概念文档只能触发后续 schema 修订，不能让实现绕过现有工具。
- `Generation Scheduler` 是横切控制面，不拥有内容真值，也不替代 schema gate、semantic gate、simulation gate、media gate 或人工审查。
- `WorldStateDeltaTransaction` 是当前 `WorldStateDelta v0.1` 的事务语义外壳。除非 `world_state_delta.v0.1.schema.json` 或后续 schema 明确允许，不得把事务字段直接塞进现有 delta 顶层。
- 所有世界状态变化必须落到当前 `operations[]` 白名单，不能通过通用 `effects[]`、自然语言 summary、raw JSON patch 或 provider trace 进入 `RunWorldState`。
- `generated`、`reviewed`、`locked`、`published`、`active`、`certified` 等状态名称可以在不同对象线中使用，但必须能映射回本文第 6 节的生命周期，而不是各管线自行解释。
- `main` 与早期文档可以保留讨论痕迹；真正派发实现任务时，默认以 `develop` 的本索引、本文、schema 和 tools 为事实源。

## 1. 总定义

AI 编译系统由四个协作层组成：

```text
Generation Scheduler (control plane)
  -> CompileRequest / queue / cache / fallback
     -> Context Engine
     -> Object Compiler
     -> World Transaction System
     -> Runtime / RunWorldState
```

更精确地说：

```text
Generation Scheduler
  surrounds:
    CompileRequest
      -> ContextPackage
      -> CandidateGeneration
      -> ObjectNormalization
      -> Validation / Simulation
      -> CGOP 或 WorldStateDelta v0.1 / Transaction wrapper
      -> Lock / Commit / Fallback
      -> Runtime / RunWorldState
```

统一口径：

> Context is advisory. CGOP is installable. Transaction is authoritative. Scheduler is latency-aware.

中文口径：

> 上下文只是建议，对象包是可安装产物，事务才是权威世界状态，调度器负责让生成在正确时间完成。

## 2. 四层职责

### 2.1 Context Engine

职责：

```text
assemble, rank, redact context
```

Context Engine 决定本次 AI 编译应看到什么，但它不是事实源，也不提交世界变化。

输入可以包括：

- `WorldBookTemplate`：世界书模板、风格、规则边界。
- `RunWorldState`：当前单局世界状态。
- `FactEntry`：世界事实、记忆摘要、NPC 关系、区域状态、系统观测。
- 最近战斗结果、玩家输入、节点上下文、NPC 状态、研发状态。
- 开发者约束、系统约束、运行时策略、玩家可见文本风格。

输出是 `ContextPackage`，而不是直接输出游戏对象。

### 2.2 Object Compiler

职责：

```text
compile, normalize, validate, package objects
```

Object Compiler 把候选内容规范化、校验、打包为不可变的 `CGOP`。

可编译对象包括但不限于：

- 塔、陷阱、道具、技能、Buff / Debuff、流派、研究方向。
- NPC、剧情事件、任务、对话片段、章节推进。
- 遭遇组合、敌潮、环境 modifier、奖励倾向、随机事件。
- 地图运行包、关卡包、路径、塔位、碰撞、波次库、敌人池、Boss 机制。
- 图像、视频帧、sprite、atlas、特效 recipe、音效、UI 图标。

Object Compiler 不直接修改 `RunWorldState`。如果对象需要改变世界，必须产出或关联当前 `WorldStateDelta v0.1`，并按 `WorldStateDeltaTransaction` 的事务语义交给 World Transaction System 提交。

### 2.3 World Transaction System

职责：

```text
authorize, validate, commit, rollback world deltas
```

World Transaction System 是唯一能修改 `RunWorldState` 的入口。

世界书不是死设定。MVP 的《长夜灯火》只是启动模板；正式架构中，系统应根据玩家行为、战斗结果、研发输出、随机事件和剧情节点持续演化单局世界状态。

世界变化必须表示为事务，而不是普通文本：

```text
WorldStateDelta v0.1 / Transaction wrapper
  -> authorize
  -> validate
  -> commit
  -> rollback / reject
```

### 2.4 Generation Scheduler

职责：

```text
schedule, parallelize, prefetch, cache, fallback
```

Generation Scheduler 是横切控制面，不是编译流水线的末端步骤。它不决定事实，也不决定对象是否有效；它决定何时生成、如何并发、如何缓存、如何降级，避免 AI 编译卡死实时游玩。

它负责：

- 选择生成时机。
- 管理并发和 provider 预算。
- 预取玩家可能很快用到的内容。
- 复用兼容缓存。
- 在失败时切换到已锁定 fallback。
- 隐藏 provider / rate limit / schema error 等技术错误。
- 让耗时内容在玩家到达前预生成，并在真正启用前重新过校验门。

## 3. 核心原则

### 3.1 Runtime-first

最终结果必须能被游戏运行。自然语言、图片、视频、概念图都不是终点。

### 3.2 Logic-first

玩法对象先有逻辑，再有表现。地图、塔、敌人、波次、任务条件、碰撞、奖励尤其如此。

### 3.3 World-aware

所有对象必须符合世界书模板、当前 `RunWorldState`、节点状态和玩法阶段。

### 3.4 World-evolving

部分对象会通过受控 `WorldStateDelta v0.1` / `WorldStateDeltaTransaction` 改变单局世界状态。世界演化必须服务玩法，不是自由续写。

### 3.5 Role-aware

玩家、系统、开发者、发布层有不同编译权限。开发者有最高创作权限，但正式运行仍由发布层和验证门控制。

### 3.6 Validator-gated

AI 输出默认是候选。进入运行时或世界状态前，必须通过机器可读校验。

### 3.7 Locked-only runtime

运行时只加载 `locked`、`certified`、`published` 或 `active` 的内容。不得直接加载 raw LLM 输出、prompt、provider trace 或未验证 JSON。

### 3.8 Presentation is not Truth

图片、视频、文本、特效只负责表现。碰撞、路径、伤害、阵营、任务条件、资源变化必须来自结构化 gameplay / world 字段。

### 3.9 DAG + ReAct

稳定流程用 DAG；失败修复、质量审查、提示词修复、分支决策使用有界 ReAct。DAG + ReAct 属于编译期辅助，不应变成浏览器运行时任意执行框架。

### 3.10 Latency-aware

AI 编译必须是调度感知的。实时运行只消费已锁定或可降级的结果；耗时生成应后台化、预取化、缓存化，并在进入世界事实前重新校验。

## 4. 权限模型

### 4.1 权限层

```text
PlayerCompiler
  玩家编译解法。

SystemCompiler
  系统编译遭遇与世界演化候选。

DeveloperCompiler
  开发者编译世界、规则、关卡、对象、校验器。

Publisher / Admin
  发布、锁定、认证、回滚、废弃。
```

### 4.2 权限动作

权限不只是“能不能生成”，而应拆成：

```text
can_propose
can_compile
can_validate
can_lock
can_publish
can_activate
can_mutate_world
```

示例边界：

- 玩家可以提出和编译塔、陷阱、技能、道具、研究方向、临时样品。
- 玩家不能直接编译地图、波次压力、奖励掉落、敌人出生点、经济规则。
- 系统可以根据玩家表现和世界状态组织遭遇，但不应自由生成未认证地图。
- 开发者可以编译几乎所有对象，但产物默认进入 `draft` / `candidate` / `reviewed`，不自动进入 runtime。
- 发布层决定正式发布、认证、回滚和废弃。

## 5. 最小对象模型

MVP 先保留四个核心对象，避免过早做大型知识系统：

```text
ContextPackage
CGOP
WorldStateDeltaTransaction
FactEntry
```

后续 v0.2 再把 `FactEntry` 拆成 `WorldBookEntry`、`MemoryEntry`、`RuntimeFact` 等更细对象。

### 5.1 ContextPackage

`ContextPackage` 是一次 AI 编译前的上下文装配结果。

最小字段：

```json
{
  "context_package_id": "ctx_...",
  "run_id": "run_...",
  "worldbook_id": "long_night_lanterns",
  "run_world_version": "turn_003_hash_...",
  "purpose": "asset_compile|encounter_compile|world_delta|narrative|media",
  "scope": "region.gray_lantern_station",
  "blocks": [
    {
      "block_id": "block_...",
      "block_kind": "worldbook|runtime_fact|memory|policy|player_input|developer_instruction|recent_event",
      "source_ref": "...",
      "trust_level": "developer|system|ai_inferred|player_claim",
      "visibility": "player_visible|ai_visible|system_private|spoiler",
      "priority": 100,
      "token_budget": 256,
      "trim_policy": "keep_full|trim_middle|summarize|drop_if_over_budget",
      "content_hash": "sha256:..."
    }
  ],
  "policy_refs": [],
  "source_refs": [],
  "token_budget": {},
  "insertion_plan": [],
  "redaction_report": {},
  "created_at": "...",
  "hash": "sha256:..."
}
```

规则：

- Context Engine 可以召回、排序、裁剪、脱敏上下文。
- ContextPackage 不能覆盖 system / developer / runtime policy。
- 玩家输入、世界书、AI 生成内容必须标记来源和权限级别。
- 每个 `blocks[]` 条目必须能追溯来源、可见性、信任等级和裁剪策略；否则不能作为高优先级上下文进入编译。
- 上下文可以影响 LLM 输出，但不能直接改变游戏事实。

### 5.2 CGOP

`CompiledGameObjectPackage`，可编译游戏对象包。它是冻结后的可安装对象包，不是世界数据库、记忆系统或事务日志。

最小字段：

```json
{
  "package_id": "pkg_...",
  "object_type": "tower|trap|item|npc|quest|encounter|map|media|world_object",
  "schema_version": "cgop.v0.1",
  "content_version": "0.1.0",
  "artifact_hash": "sha256:...",
  "worldbook_id": "long_night_lanterns",
  "run_world_version": "turn_003_hash_...",
  "lifecycle_state": "draft|compiled|validated|reviewed|locked|published|active",

  "authority": {},

  "source_intent": {},
  "context_package_id": "ctx_...",
  "source_refs": [],
  "policy_refs": [],
  "execution_trace_ref": "trace_...",
  "world_context": {},

  "semantic_spec": {},
  "gameplay_spec": {},
  "runtime_contract": {},
  "media_presentation": {},

  "dependencies": [],
  "conflicts": [],
  "required_capabilities": [],
  "runtime_budget": {},

  "validation_report": {
    "gate_status": "passed|failed|warning|skipped",
    "runtime_loadable": false,
    "gates": []
  },
  "lineage": {}
}
```

CGOP 可以包含：

- 对象定义。
- 运行时 manifest。
- 依赖、能力、冲突声明。
- 资产引用。
- validation report。
- 版本、hash、编译来源摘要。

CGOP 不应包含：

- 完整世界书。
- 长期记忆全集。
- 当前世界事实全集。
- 世界事务日志。
- 可变实例状态。
- 玩家隐私数据。
- AI 推理过程全文。

### 5.3 WorldStateDeltaTransaction

世界状态变化事务。它是 `RunWorldState` 写入行为的事务外壳和解释模型，不替代当前已经落地的 `WorldStateDelta v0.1`。

v0.1 兼容策略：

```text
WorldStateDeltaTransaction
  wraps / interprets:
    WorldStateDelta v0.1
      -> validate_world_delta.py
      -> validate_world_delta_semantics.py
      -> apply_world_delta.py
      -> RunWorldState
```

也就是说，当前 MVP 的可执行事实源仍是 `shared/schemas/world_state_delta.v0.1.schema.json`、`docs/WORLD_STATE_DELTA_SEMANTIC_GATE_V0_1.md` 和 `tools/world_state/`。本文中的事务字段用于说明未来需要的并发、幂等、回滚和冲突控制，不允许用通用 `effects[]` 绕过现有 `operations[]` 白名单。

最小字段：

```json
{
  "transaction_id": "tx_...",
  "actor": "player|system|developer|publisher",
  "source": "battle_result|research_job|narrative_event|system",
  "base_world_version": "world_v...",
  "idempotency_key": "...",
  "scope": {},
  "source_refs": {},
  "preconditions": [],
  "operation_effects_mapping": [],
  "world_state_delta_ref": {},
  "conflict_policy": {},
  "rollback_policy": {},
  "expires_at": null,
  "validation_report": {},
  "status": "candidate|validated|committed|rejected|rolled_back"
}
```

当前落地文件：

- `shared/schemas/world_state_delta_transaction.v0.1.schema.json`
- `tools/world_state/validate_world_delta_transaction.py`
- `examples/world_delta_transactions/first_battle_result.world_delta_transaction.json`

与现有 `WorldStateDelta v0.1` 的映射：

| 事务概念 | 当前 MVP 落地字段 / 事实源 |
| --- | --- |
| `transaction_id` | 事务外壳自己的 ID；不替代 `delta_id` |
| `actor` | 由 `source`、调用方权限和 job metadata 推导 |
| `base_world_version` | 当前 `RunWorldState` 的 turn / hash / snapshot metadata |
| `scope` | `run_id`、`worldbook_id`、操作引用对象共同决定 |
| `operation_effects_mapping[]` | 逐项映射 `WorldStateDelta.operations[]` 的 index / op / target_ref / effect_kind；不是可执行 effect DSL |
| `preconditions` | v0.1 主要由 schema、semantic gate 和当前 run state registry 表达 |
| `validation_report` | `validate_world_delta.py` 与 `validate_world_delta_semantics.py` 的报告 |
| `commit` | `apply_world_delta.py` 成功执行 |

规则：

- 事务必须基于明确 `base_world_version`。
- 事务必须可幂等，或声明为什么不能幂等。
- 多 AI、多系统 tick、多玩家操作并行时，必须通过 `conflict_keys` 和 `idempotency_key` 控制重复提交和冲突。
- 预生成事务只能是候选；玩家真正到达相关节点时，必须基于最新世界状态重新校验。
- v0.1 不新增任意 `effects` 执行器，也不允许顶层 `effects[]`。所有世界变化仍必须写成当前 `WorldStateDelta v0.1` 允许的 `operations[]`，事务外壳只能解释和校验这些 operation 的提交语义。
- 如旧文档提到更少或不同的 op 集合，以当前 schema 与 `WorldStateDeltaSemanticGate` 为准；旧说法只保留为历史背景。

### 5.4 FactEntry

MVP 先用 `FactEntry` 统一承载世界书条目、系统观测、AI 记忆摘要、NPC 关系事实、区域状态事实。

最小字段：

```json
{
  "fact_id": "fact_...",
  "fact_kind": "worldbook|memory|runtime_fact|npc_state|region_state|quest_state",
  "scope": "run|region|node|npc|quest|global",
  "subject": "...",
  "predicate": "...",
  "content": "...",
  "source": "developer|system_observation|ai_inferred|player_claim|battle_result",
  "confidence": "canonical|observed|inferred|rumor|player_claim",
  "visibility": "player_visible|ai_visible|system_private|spoiler",
  "activation_rules": {},
  "expires_at": null,
  "created_at": "...",
  "source_tx_id": null
}
```

规则：

- `developer` / `system_observation` / `battle_result` 的可信度高于 `ai_inferred` 和 `player_claim`。
- 剧透、系统私有事实、AI 可见事实、玩家可见事实必须分开。
- FactEntry 可以被 Context Engine 使用，但只有 World Transaction System 可以把候选事实提交为世界事实。

## 6. 生命周期

CGOP 主生命周期：

```text
draft
  -> compiled
  -> validated
  -> reviewed
  -> locked
  -> published
  -> active
  -> deprecated / revoked / quarantined / rolled_back
```

含义：

- `draft`：草稿或未完整生成。
- `compiled`：已生成结构化候选。
- `validated`：通过当前校验器。
- `reviewed`：通过人工、确定性规则或指定审查包的发布前审查；仍不等于运行时可加载。
- `locked`：不可变封存，带 hash。
- `published`：进入可被运行时选择的内容池。
- `active`：当前 session / run 已启用。
- `deprecated`：不再推荐新用，但可兼容旧存档。
- `revoked`：发现问题，禁止新加载。
- `quarantined`：隔离调查，保留回放和存档修复空间。
- `rolled_back`：发布层回退到旧版本。

`locked` 后不得原地修改。任何变化都必须生成新的 `content_version` 和 `artifact_hash`。

不同对象线的状态名称可以不同，但必须能映射到统一生命周期：

| 对象线 | 典型状态 | 映射说明 |
| --- | --- | --- |
| AI 文本 / 内容候选 | `generated` -> `reviewed` -> `locked` | 早期“生成后审查再锁定”的口径继续有效。 |
| CGOP | `draft` -> `compiled` -> `validated` -> `reviewed` -> `locked` -> `published` -> `active` | 游戏对象包主生命周期。 |
| locked manifest / runtime package | `reviewed` -> `locked` -> `published` -> `active` | runtime 只读已锁定或已发布内容。 |
| 媒体资产 | `raw_media` -> `processed_media` -> `reviewed` -> `published_media` | 图片、视频帧、atlas 先后处理，再进入发布媒体池。 |
| 地图 / 关卡模板 | `candidate_map` -> `validated` -> `certified` -> `published` / `active` | `certified` 表示地图逻辑、塔位、路径、预算、视觉包均已通过设计与机器校验，可进入认证模板池。 |

`certified` 只用于需要被重复调度或作为 fallback 的高风险模板，例如地图、关卡、遭遇组合和重资产内容。普通玩家临时样品不必进入 `certified`，通过 `validated` / `reviewed` / `locked` 即可进入受限 runtime。

当前 v0.1 对应关系：

- `ContextPackage v0.1`、`FactEntry v0.1`、`CompiledGameObjectPackage v0.1` 已有字段级 schema 草案和统一 validator；它们冻结 v0.1 边界，但不要求旧包一次性全部迁移。
- `CGOP` 是可安装对象包的概念事实源；字段级落地文件是 `compiled_game_object_package.v0.1.schema.json`。
- `locked_manifest.v0.1`、`runtime_package.v0.1`、`frontend_mock_pack.v0.1` 和各类 review pack 是当前已落地的包形态。
- `MediaAtlasManifest v0.1` 承接已发布媒体，当前已经包含确定性 frame sequence 与实体 `atlas_sheets`；真实图生视频关键帧后续只替换 frames 来源，不改变运行时只读 published media 的原则。
- `MapCompilePackage v0.2` 记录地图编译证据，`MapRuntimePackage v0.1` 是前端战斗地图运行时事实源；地图是否可复用进入模板池，应由 `certified` 语义表达。

## 7. 包与实例分离

CGOP 是蓝图，不是运行时实例。

示例：

```text
一个 Tower CGOP
  -> 可以实例化为 battle_instance_001
  -> 也可以实例化为 battle_instance_002
```

运行时实例状态包括：

- 位置。
- 等级。
- 当前生命值。
- 冷却。
- Buff / Debuff。
- 归属阵营。
- 临时状态。
- 战斗内统计。

这些应进入 `RuntimeObjectInstance` 或 save state，不能回写 CGOP。

## 8. 验证报告

`validation_report` 必须机器可读，不能只有自然语言。

最小字段：

```json
{
  "gate_status": "passed|failed|warning|skipped",
  "runtime_loadable": true,
  "gates": [
    {
      "gate_id": "schema",
      "status": "passed|failed|warning|skipped",
      "validator_version": "...",
      "summary": "...",
      "failed_rules": [],
      "warnings": []
    }
  ],
  "validator_versions": {},
  "approved_scopes": [],
  "failed_rules": [],
  "warnings": [],
  "player_safe_explanation": "",
  "reviewer_notes": ""
}
```

基础验证门：

- schema 校验。
- 权限校验。
- 依赖和能力校验。
- 世界状态引用校验。
- 玩法预算校验。
- 运行时预算校验。
- 媒体资源校验。
- 玩家可见文本校验。
- 安全和隐私校验。

LLM 可以参与审查和建议修复，但最终 gate 应尽量由确定性 Schema、规则、模拟器、视觉检查或人工审核决定。

## 9. Runtime 约束与预算

运行时不得执行 AI 生成的任意代码。运行时只消费：

- locked 数据。
- 受控 DSL。
- 白名单模块。
- 已发布媒体 manifest。
- 通过校验的 runtime contract。

每个可运行包必须声明预算：

```json
{
  "max_instances": 8,
  "max_triggers_per_second": 10,
  "texture_budget_kb": 1024,
  "particle_budget": 80,
  "audio_budget_kb": 0,
  "cpu_budget_hint": "low|medium|high",
  "browser_tier": "mvp"
}
```

超预算对象不能进入 MVP runtime。

## 10. Generation Scheduler

### 10.1 Latency Class

冻结以下延迟等级：

```text
sync_blocking
async_visible
background_prefetch
batch_offline
fallback_static
```

说明：

- `sync_blocking`：必须立刻可用，否则玩家无法继续。应只读取 locked / cached / fallback。
- `async_visible`：玩家知道它在生成，可以等待或做别的事。例如现场试作倒计时。
- `background_prefetch`：玩家尚未到达，但系统预测可能会用，提前生成。
- `batch_offline`：开发期或闲时生成，例如地图模板、美术包、视频帧、认证关卡池。
- `fallback_static`：实时生成失败时使用的已锁定兜底内容。

### 10.2 CompileRequest 调度字段

```json
{
  "request_id": "req_...",
  "purpose": "encounter_prefetch",
  "latency_class": "background_prefetch",
  "deadline_ms": 30000,
  "priority": 40,
  "player_visible": false,
  "fallback_package_id": "pkg_...",
  "cache_policy": "reuse_if_world_version_compatible",
  "parallelism_hint": 3
}
```

### 10.3 CompileJob 最小字段

```json
{
  "job_id": "job_...",
  "request_id": "req_...",
  "status": "queued|running|succeeded|failed|cancelled|expired",
  "latency_class": "background_prefetch",
  "cache_key": "...",
  "result_ref": null,
  "fallback_ref": "pkg_...",
  "player_visible": false,
  "created_at": "...",
  "finished_at": null
}
```

### 10.4 缓存 key

缓存不应只按 prompt，而应至少考虑：

```text
worldbook_template_hash
run_world_version
context_package_hash
compile_request_hash
object_type
provider_profile
schema_version
```

可跨存档复用的内容：

- 基础地图模板。
- 通用敌人素材。
- 通用特效。
- UI 图标。
- 开发者认证内容。

不可直接跨存档复用的内容：

- 当前 NPC 对当前玩家的反馈。
- 根据当前世界状态生成的剧情。
- 玩家输入编译出的专属塔。
- 当前节点的 WorldStateDelta。

### 10.5 降级链

```text
live_generated
  -> cached_compatible
  -> certified_template
  -> deterministic_local
  -> mock/static fallback
```

玩家侧不应看到 provider、rate limit、schema error。玩家看到的是世界内解释，例如：

```text
样品封装失败，工坊改用旧式灯栏方案。
信标受扰，本次只收到残缺情报。
调度员先给出保守方案。
```

## 11. 上下文引擎与世界书系统的关系

SillyTavern、NovelAI、AI Dungeon 这类系统成熟之处在于 Context Engineering：通过世界书、角色卡、记忆、Author Note、Story Card 等机制决定本次 prompt 中放入哪些内容。

本项目吸收这些机制，但必须补上游戏事实层：

```text
酒馆 / AI 小说系统：
  chat history + lorebook retrieval + memory summary
    -> prompt
    -> model continuation

本项目：
  WorldBookTemplate + RunWorldState + PlayerAction + BattleResult
    -> ContextPackage
    -> candidate
    -> CGOP 或 WorldStateDelta v0.1 / Transaction wrapper
    -> validation
    -> locked / committed
```

因此：

- 世界书条目可以进入 ContextPackage。
- 世界书条目不能直接改变 `RunWorldState`。
- AI 生成的新 lore 先是候选 FactEntry。
- 只有通过当前 `WorldStateDelta v0.1` 流水线提交，并被 `WorldStateDeltaTransaction` 语义约束解释的事实，才是游戏事实。

## 12. 地图、剧情、媒体的特殊边界

### 12.1 地图

地图必须 logic-first：

```text
EncounterSpec
  -> PathGraph
  -> PlacementMap
  -> CollisionMap
  -> MapRuntimePackage
  -> Visual Map
```

不要从 AI 生成图片反推怪物路线、塔位和碰撞。图片是表现层，不是真值来源。

### 12.2 剧情

剧情不是自由续写。可落地剧情必须服务玩法，并通过当前 `WorldStateDelta v0.1` 流水线提交；`WorldStateDeltaTransaction` 是它的事务语义外壳：

```text
NarrativeEventBundle
  -> Gameplay Purpose Gate
  -> WorldStateDelta v0.1 / WorldStateDeltaTransaction wrapper
  -> RunWorldState
```

### 12.3 媒体

媒体资产可以由 AI 生成，但必须进入：

```text
generated
  -> processed
  -> reviewed
  -> locked / published
  -> MediaAtlasManifest / atlas_sheets
  -> runtime package
```

媒体表现不能决定碰撞、伤害、路线、资源和任务条件。

当前 MVP 允许用确定性多帧 frame sequence 先占位循环动画，并打包为实体 spritesheet；这只是媒体表现层的已发布资源形态。后续接入图片 -> 视频 -> 关键帧链路时，必须重新经过后处理、审查、atlas 打包和 runtime 引用校验。

## 13. MVP 实现边界

MVP 不实现完整知识图谱、通用事务 DSL 或大型地图生成器。

MVP 应实现或固化：

```text
ContextPackage v0.1
FactEntry v0.1
CGOP v0.1
WorldStateDelta v0.1 + transaction metadata / mapping
GenerationSchedulePlan / GenerationScheduleRunReport 最小字段
MapRuntimePackage v0.1
MediaAtlasManifest v0.1 + entity spritesheet atlas
```

最小闭环：

```text
玩家进入工坊
  -> ContextPackage
  -> 编译一个临时样品 CGOP
  -> 校验通过
  -> 战斗中 async_visible 倒计时送达
  -> 战后生成 WorldStateDelta v0.1，并以 WorldStateDeltaTransaction 语义提交
  -> 提交 RunWorldState
  -> 返回大地图时看到世界状态变化
```

地图和视频等重资产：

- 开发期 `batch_offline`。
- 或章节开始时 `background_prefetch`。
- 不在战斗点击瞬间阻塞生成。

## 14. v0.2+ 扩展

可以后置：

- `WorldBookEntry`、`MemoryEntry`、`RuntimeFact` 从 `FactEntry` 中拆分。
- 完整知识图谱。
- 长周期势力 / 资源 / 威胁生态模拟。
- 自动数值调优器和大规模蒙特卡洛测试。
- 复杂地图模块拼接和搜索式地图生成。
- 玩家自定义 DSL 编辑器。
- 灰度发布 / A-B 发布 / 赛季迁移。
- 完整素材版权工作流和多语言本地化。
- 可视化 provenance / ReAct 调试器。

## 15. 明确非目标

v0.1 不做：

- 玩家直接生成战斗地图、怪物路线、波次压力和奖励掉落。
- 从 AI 地图图片中全自动反推运行时事实。
- runtime 执行 AI 生成代码。
- 未经验证的对象进入正式运行。
- 预生成内容直接改变世界。
- Context Engine 直接写 `RunWorldState`。
- Object Compiler 直接提交世界变化。
- CGOP 携带完整世界书、长期记忆全集或玩家隐私数据。

## 16. 后续实现顺序

建议顺序：

1. 为现有 `WorldStateDelta v0.1` 补事务 metadata / 映射说明；不要替换现有 delta schema。
2. Research Job 与 battle settlement evidence 已先行携带 `ContextPackage v0.1`、`FactEntry v0.1`、`CompiledGameObjectPackage v0.1` 原生快照；下一步继续把 WorldStateDelta / frontend mock 包 / review pack 对齐到这些核心字段与 `WorldStateDeltaTransaction v0.1`，并统一机器可读 validation report。
3. 实现 live campaign router 与 Generation Scheduler 后台执行器，让预生成、缓存和 fallback 真正进入游玩流程。
4. 把当前确定性 frame sequence 替换为真实图生视频关键帧，并继续走已落地的实体 spritesheet atlas。
5. 推进 AI 生成 painted map 的受控图像管线，但仍以 `MapRuntimePackage` 的路径、塔位、碰撞和目标为运行时事实源。

这份文档冻结的是架构边界，不要求所有对象一次性实现。后续所有具体管线都应说明自己属于哪一层、产出哪个对象、能否改变世界事实、如何被调度和校验。
