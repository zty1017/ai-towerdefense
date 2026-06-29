# AI 编译塔防：架构与治理基线

Last updated: 2026-06-29

比赛队伍名：`Compiler`

## 1. 产品定位

本项目是一个通用的 AI 驱动塔防系统，不是单一世界观游戏。

项目核心是一套面向塔防的 AI 资产与内容编译系统：

```text
玩家意图 / 世界书种子 / 战斗上下文
  -> AI 语义理解
  -> 结构化蓝图或内容候选
  -> Schema、模块、预算、玩法兼容性校验
  -> 可玩游戏资产或 reviewed 内容
```

MVP 世界书是《长夜灯火》（`long_night_lanterns`）。它是用于验证系统的演示战役，不是项目本体名称。

所有正式项目文档应使用中文。代码标识、目录名、API 名、Schema 字段名可以保留英文。

## 2. 核心支柱

1. 塔防是主要可玩循环。
2. AI 资产编译是核心创新。
3. 世界书不是换皮，而是语义、视觉、资源、NPC、敌人、玩法权重和模块池约束层。
4. AI 输出默认是候选内容，不能直接成为正式数据。
5. 运行期 AI 不得发明未注册的可执行规则。
6. MVP 先验证一条强闭环，再扩展多世界书和更复杂系统。

## 3. 系统分层

### 3.1 塔防运行时

负责真实游戏规则：

- 敌人路径
- 固定塔位
- 主核心耐久
- 资源点耐久
- 波次系统
- 基础塔
- 兵营与单位
- 支援道具
- 临时改制
- 蓝图塔升级
- 胜利、失败、软失败与战斗指标

这一层必须保持确定性、可测试、可复现。

视觉呈现应优先采用 2D 或伪 3D。项目需要浏览器部署和路演展示，不应在 MVP 阶段做完整 3D 战斗场景。伪 3D 可以通过等距视角、层次阴影、粒子、轻量动画和 2.5D UI 来实现。

MVP 的视频内容不进入实时生成闭环。开场动画可以预制；节点剧情、战后总结和特殊事件优先使用动画卡、2D 立绘、视差背景、轻量粒子、镜头推拉和文字演出。视频生成模型后续可以作为离线内容生产工具，生成结果必须经过 reviewed / locked 流程后再进入游戏。

### 3.2 AI 资产编译器

把玩家的战术意图转化为可玩资产。

输入包括：

- 玩家自然语言需求
- 当前节点
- 已知敌人压力
- 资源与材料
- 参与 NPC
- 世界书
- 模块库
- 预算规则
- 塔防参考模式

输出包括：

- 防御塔蓝图
- 兵营或单位蓝图
- 临时改制道具
- 支援道具
- 机关 / 陷阱
- 稳定化蓝图记录

必须经过：

- Schema 校验
- 模块白名单校验
- 预算校验
- 玩法兼容性校验
- 世界书一致性检查
- fallback 可用性检查

### 3.3 内容生长管线

根据世界书生成候选内容，并进入审查流程。

候选内容可以包括：

- 弱主线节点
- 节点卡
- NPC 档案
- 敌人包装
- 资源与材料
- 随机事件
- 战前简报
- 战后日志
- 蓝图命名与说明
- 美术 prompt 候选

候选来源可以包括：

- 游戏运行时内置 AI provider 调用
- 开发期脚本或批处理生成
- 人类在网页聊天中生成后下载的 JSON / Markdown / 图片 / 视频
- 团队成员手写或整理的外部素材

外部导入内容必须进入固定 inbox，由导入器解析和登记，不能直接写入 locked game data。

生命周期：

```text
generated -> reviewed -> locked -> game_data
```

只有 locked 内容可以被正式游戏读取。

### 3.4 世界书层

世界书把通用玩法语法映射到具体世界。

世界书应定义：

- 语气与禁用内容
- 阶段映射
- 资源映射
- 节点映射
- 敌人映射
- NPC 原型
- 资产命名与视觉规则
- 玩法倾向
- 模块偏好
- 事件风格

世界书可以影响玩法权重和可用的已注册模块，但不能绕过底层塔防语法。

### 3.5 策略与叙事层

这一层给塔防结果提供长期意义，但 MVP 阶段不能变成完整 4X 或复杂经营游戏。

MVP 范围内负责：

- 节点地图
- 主城 / 大本营
- 资源点
- 受威胁 / 失守 / 可夺回状态
- NPC 记忆
- 资源后果
- 蓝图谱系
- 战后状态变化

## 4. MVP 主循环

MVP 应证明这条闭环：

```text
节点受威胁
  -> 情报 / 节点卡说明问题
  -> 玩家进入工坊 / 研发界面
  -> 玩家提出战术需求
  -> mock compiler 返回 3 个合法候选
  -> 玩家选择蓝图
  -> 进入塔防战斗
  -> 基础塔升级为蓝图塔
  -> 蓝图明显改变战局
  -> 战后更新资源点、NPC 记忆和蓝图谱系
```

推荐 MVP 世界书：

```text
长夜灯火
Preparation -> 白天修缮
Battle -> 入夜防守
Resolution -> 黎明巡记录
```

## 5. 仓库骨架

```text
.
  README.md
  AGENTS.md
  package.json

  control/
    PROJECT_BRIEF.md
    MVP_SCOPE.md
    DECISIONS.md
    TASK_QUEUE.md
    QUALITY_GATES.md
    WORKTREE_BOARD.md
    INTEGRATION_LOG.md
    TEAM_BOARD.md
    AI_GENERATION_LOG.md
    AI_REVIEW_LOG.md
    QA_RUN_LOG.md
    PROMPT_REGISTRY.md
    CONTENT_REGISTRY.md
    PLAYTEST_NOTES.md

  docs/
    00_BRAINSTORM_SYNTHESIS.md
    01_COMPLETE_GAME_DESIGN.md
    02_MVP_SPEC.md
    03_UX_FLOW.md
    04_BATTLE_DESIGN.md
    05_AI_ASSET_COMPILER.md
    06_WORLD_BOOK_AND_CONTENT_PIPELINE.md
    07_TECH_ARCHITECTURE.md
    08_DATA_SCHEMA_DRAFT.md
    09_LOCAL_AI_HANDOFF.md
    10_EVALUATION_AND_QA_PLAN.md
    11_AI_EVALUATOR_DESIGN.md
    12_PROMPTOPS_AND_PROMPT_EVALUATION.md
    13_PARALLEL_WORKTREE_DEVELOPMENT.md
    14_TEAM_COLLABORATION.md
    AI_ASSET_COMPILER_V0_1.md
    ASSET_GRAPH_COMPILER_V0_1.md
    AGENT_COLLABORATION_AND_GIT_GOVERNANCE.md

  frontend/
    src/
      app/
      game/
      scenes/
      systems/
      ui/
      state/
      data/mock/

  backend/
    app/
      api/
      compiler/
      schemas/
      services/
      prompts/
    tests/

  shared/
    schemas/
    module_registry/
    budget_rules/

  tools/
    content_pipeline/
    eval/
    prompt_lab/

  content/
    import_inbox/
      chat_exports/
      manifests/
      images/
      videos/
      rejected/
    generated/
    reviewed/
    locked_exports/

  game_data/
    worldbooks/
    nodes/
    npcs/
    enemies/
    maps/
    blueprints/
    modules/

  references/
    td_case_studies/
    td_patterns/

  local/
    repos/
    worktrees/
    runs/
    staging/
    logs/
    machine_control/

  artifacts/
    screenshots/
    videos/
    demo_logs/
```

## 6. 技术架构

前端：

- React + Vite + TypeScript 负责应用界面
- Phaser 3 负责塔防战斗运行时
- Zustand 或同类轻量状态库
- locked game data 加载器
- 蓝图卡渲染
- 节点地图与战后结算 UI

后端：

- Python + FastAPI
- Pydantic v2 作为 Schema 权威
- SQLite 作为轻量持久化层
- 先实现 mock compiler
- 后续接入真实 LLM compiler
- repair / fallback 管线
- AI 生成日志
- 可选 AI Reviewer 接口

共享层：

- JSON Schema 导出给前端
- 模块库
- 预算规则
- 玩法兼容性规则

数据存储策略：

- 初期可以使用 JSON + Markdown 承载文档、mock 数据、候选内容和人工审查记录。
- 随着系统进入蓝图编译、运行日志、NPC 记忆、PromptOps、AI Reviewer 与 playtest 记录阶段，应引入 SQLite。
- MVP 不需要复杂用户注册登录系统；如需区分本地试玩记录，可以使用本地 profile、run id 或 demo session id。

SQLite 适合承载：

- game runs
- blueprint candidates
- selected / stabilized blueprints
- AI generation logs
- AI review reports
- content lifecycle state
- NPC memory snapshots
- playtest records
- prompt eval results

正式 locked 游戏数据仍应可导出为 JSON，方便前端加载、版本管理和人工审查。

## 7. 项目治理

### 7.1 事实源

`control/` 是项目事实源。

重要设计变更必须记录到：

- `DECISIONS.md`
- `TASK_QUEUE.md`
- `MVP_SCOPE.md`
- `QUALITY_GATES.md`

### 7.2 保护文件

以下文件只有在人类明确确认后才能直接修改：

- `control/MVP_SCOPE.md`
- `control/DECISIONS.md`

以下内容应先提交 proposal：

- `control/QUALITY_GATES.md`
- `control/PROMPT_REGISTRY.md`
- `control/AI_DEV_GOVERNANCE_LITE.md`
- `shared/schemas/`
- `shared/module_registry/`
- `shared/budget_rules/`
- locked 游戏数据

### 7.3 AI 输出生命周期

AI 输出默认不是正式内容。

```text
generated: AI 原始候选
reviewed: 已经过规则 / 人类 / AI Reviewer 初审
locked: 可被正式游戏读取
```

### 7.4 任务纪律

每个可执行任务必须包含：

- task id
- goal
- context docs
- allowed files
- not allowed files
- acceptance criteria
- validation commands
- stop condition

worker 一次只执行一个 ready 任务。

### 7.5 质量门

Gate 0：项目能启动。

Gate 1：最小塔防可玩。

Gate 2：蓝图闭环可用。

Gate 3：内容生命周期可用。

Gate 4：真实 AI 与 fallback 稳定。

Gate 5：Demo 路径可重复。

## 8. 团队协作

### 8.1 你：项目与技术主控

负责：

- 产品方向
- MVP 范围
- 架构决策
- 核心 Schema / 模块库 / 编译器审查
- branch 与 worktree 集成
- 部署
- 最终 Demo 判断

不应投入过多时间在：

- 反复润色文案
- 美术候选初筛
- 手工试 prompt
- 第一轮试玩记录
- PPT 初稿排版

### 8.2 计算机专业队友

定位：初级技术执行、QA、数据与工具协助。

适合任务：

- 按 README 跑环境并记录报错
- 整理 mock JSON 数据
- 实现简单静态 UI 组件
- 写简单校验脚本
- 维护 fixture 数据
- 复现 bug
- 测试战斗场景
- 维护简单文档

初期不建议负责：

- 编译器核心架构
- Schema 和模块库最终设计
- 部署密钥
- 复杂战斗引擎逻辑
- 合并和集成决策

### 8.3 文科类队友

定位：世界书、内容、可读性、美术审查、试玩、路演表达。

适合任务：

- 审查世界书气质
- 压缩节点 UI 文案
- 评价 NPC 是否清晰
- 给蓝图命名打分
- 审查美术候选
- 做第一玩家试玩
- 准备 Demo 脚本
- 协助 PPT 和路演叙事

不建议负责：

- 代码修改
- Schema 编辑
- Prompt approval
- locked 内容升级
- 数值平衡最终判断

## 9. Worktree 策略

分支模型：

```text
main: 稳定 Demo
develop: 集成开发
task/<task-id>-<slug>: 单任务分支
```

早期阶段：

- P0-001 和 P0-002 低并行
- 避免并行修改 Schema、compiler、budget rules

Schema v0.1 后：

- 允许 2-4 个 active worktree
- 可拆分 UI、内容管线、参考库、QA/eval
- 高耦合系统串行集成

## 10. 近期下一步

1. 用通用系统定位创建修正版项目骨架。
2. 导入或重写 handoff 文档，让《长夜灯火》成为 MVP 世界书，而不是项目本体。
3. 完成 Gate 0：
   - 前端占位可启动
   - 后端 health check 可启动
   - README 写明启动方式
   - 验证命令可运行
4. 进入 Schema / Module Registry / Budget Rules v0.1。
