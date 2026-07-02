# 当前架构文档索引

Last updated: 2026-07-02

本文档是当前项目设计、决策、架构与验收材料的入口。

若其他早期文档与本文档冲突，以本文档列出的当前事实源为准。

事实源层级：

- 本索引用于导航、阅读顺序和优先级路由。
- `docs/AI_COMPILATION_SYSTEM_V0_1.md` 用于 AI 编译系统的概念、边界、权限和生命周期事实源。
- 具体字段、op 白名单、semantic gate、运行命令和校验行为，以 `shared/schemas/`、`tools/` 和对应专题文档为字段级事实源。

## 1. 当前事实源

当前事实源是 `develop` 分支的最新集成结果。`main` 只在稳定同步后作为发布 / 决策基线使用。

截至本索引更新时间，当前有效主线是：

```text
通用 AI 驱动塔防系统
  -> 玩家自然语言 / 世界书 / 战斗上下文
  -> 受控 AI 编译
  -> AssetGraph DAG / 有界 ReAct 节点
  -> Schema / 白名单 / 预算 / 语义门 / 媒体门禁
  -> 可玩资产、任务、事件、剧情节点、世界状态变化
  -> 前端 mock API 先用 reviewed fixture 跑完整 MVP 演示链路
```

《长夜灯火》只是 MVP 世界书模板，不是项目本体名称。

## 2. 先读顺序

新代理、新队友或评审应按以下顺序阅读：

1. `README.md`
   - 项目运行入口、后端 API、验证命令。
2. `docs/CURRENT_ARCHITECTURE_INDEX.md`
   - 当前文档导航和有效性说明。
3. `docs/PROJECT_ARCHITECTURE_AND_GOVERNANCE.md`
   - 产品定位、架构分层、协作治理基线。
4. `docs/AI_COMPILATION_SYSTEM_V0_1.md`
   - AI 编译系统总架构：Context Engine、Object Compiler、World Transaction System，以及作为横切控制面的 Generation Scheduler。
5. `docs/DEMO_VERTICAL_SLICE.md`
   - MVP 演示主路径。
6. `docs/FRONTEND_MOCK_API_V0_1.md`
   - 当前前端应接入的 mock API。
7. `docs/FRONTEND_RUNTIME_MOCK_ART_KIT_V0_1.md`
   - 前端战斗运行时 mock 美术包：敌人、目标物、基础防御件、NPC 头像、地图 token 和程序化特效。
8. `docs/MVP_REVIEW_HANDOFF_V0_1.md`
   - 当前审查交付入口。

## 3. 当前有效设计文档

### 产品与前端

- `docs/DEMO_VERTICAL_SLICE.md`
  - MVP 录屏和玩家体验主路径。
- `docs/FRONTEND_PRODUCT_AND_TECH_DECISION.md`
  - 前端产品形态和技术决策。
- `docs/FRONTEND_MOCK_API_V0_1.md`
  - 后端暴露给前端的稳定 mock API。
- `docs/FRONTEND_MOCK_PACK_V0_1.md`
  - 前端 mock 内容包说明。
- `docs/FRONTEND_RUNTIME_MOCK_ART_KIT_V0_1.md`
  - 开发者预编译的战斗运行时 mock 美术包说明。

### AI 编译器与 AssetGraph

- `docs/AI_COMPILATION_SYSTEM_V0_1.md`
  - 当前 AI 编译总架构边界事实源。定义 Context Engine、Object Compiler、World Transaction System、Generation Scheduler，以及 CGOP、ContextPackage、FactEntry、WorldStateDelta / WorldStateDeltaTransaction 映射的 v0.1 边界。具体字段仍以 schema 和 semantic gate 为准。
- `docs/AI_ASSET_COMPILER_V0_1.md`
  - AI 资产编译器基础定位。
- `docs/ASSET_GRAPH_COMPILER_V0_1.md`
  - 当前 AssetGraph / DAG / 有界 ReAct / 媒体节点主设计。
- `docs/FREE_INPUT_CONTROLLED_COMPILATION_V0_1.md`
  - 自由输入如何进入受控编译。
- `docs/COMPILABLE_OBJECT_MODEL_V0_1.md`
  - 游戏中哪些对象可被 AI 编译。
- `docs/COMPILABLE_OBJECT_PLAN_V0_1.md`
  - 下一阶段可编译对象规划。
- `docs/GAMEPLAY_OBJECT_COMPILER_V0_1.md`
  - 玩法对象编译边界。

### 剧情、任务与世界状态

- `docs/CONTROLLED_NARRATIVE_WORLD_COMPILER_V0_1.md`
  - 剧情 / 世界生长如何受控服务玩法。
- `docs/NARRATIVE_GAMEPLAY_CONTRACT_V0_1.md`
  - 叙事节点和玩法输出之间的合同。
- `docs/WORLD_STATE_DELTA_SEMANTIC_GATE_V0_1.md`
  - WorldStateDelta 语义门。
- `docs/MVP_WORLD_STATE_DELTA_REVIEW_PACK_V0_1.md`
  - MVP 世界状态变化审查包。

### 媒体素材

- `docs/MEDIA_ASSET_QUALITY_PIPELINE_V0_2.md`
  - 图片生成、后处理、审查、修复和运行时就绪门禁。
- `docs/VIDEO_FRAME_ASSET_PIPELINE_V0_1.md`
  - 图片种子 -> 图生视频 -> 关键帧 -> 循环连续性检查 -> 批量后处理 -> atlas 的路线。

当前状态：

```text
processed PNG 已可用于前端 mock。
animation seed 已可用于后续图生视频。
frontend_runtime_mock 已作为战斗运行时美术包入口，覆盖敌人、目标物、基础防御件、NPC 头像、地图 token 和程序化特效。
循环动画策略已确认：优先首尾同图 / end frame 控制，否则通过 seamless loop prompt 与 LoopContinuityCheck 修复。
视频帧 / spritesheet / atlas 还未作为默认前端资产生成。
```

### 审查与交付

- `docs/MVP_REVIEW_HANDOFF_V0_1.md`
  - 一键审查入口。
- `docs/MVP_COMPILER_REVIEW_DOSSIER_V0_1.md`
  - 总审查交付包说明。
- `docs/MULTISTAGE_CONTENT_PACK_V0_1.md`
  - 多阶段内容包。
- `docs/STAGE_CANDIDATE_PACK_V0_1.md`
  - 阶段候选包。
- `docs/MVP_NARRATIVE_ASSET_REVIEW_PACK_V0_1.md`
  - 叙事资产审查包。
- `docs/MVP_STORY_ASSET_PROMOTION_REPORT_V0_1.md`
  - 剧情资产晋级报告。

### Provider 与真实调用

- `docs/AI_PROVIDER_RESEARCH_AND_SMOKE_TEST.md`
  - 方舟、DeepSeek、GLM、Agnes 等 provider 调研和烟测记录。
- `docs/LIVE_LLM_WORLD_DELTA_SMOKE_TEST_V0_1.md`
  - 真实 LLM 世界状态变化烟测。
- `docs/AI_COMPILER_ITERATION_LOG.md`
  - AI 编译器多轮迭代记录。

## 4. 当前实现事实

当前已实现或已落地的事实：

- FastAPI + SQLite 后端。
- 匿名 session，不做真实注册登录。
- Research proposal / job API。
- Frontend mock API。
- 前端 mock 内容包：11 个可玩资产、3 个阶段摘要、3 个 runtime package 摘要。
- Agnes 生成的 22 张当前资产图片。
- processed 透明 PNG 媒体包。
- animation seed manifest。
- 前端运行时 mock 美术包：敌人、目标物、基础防御件、NPC 头像、地图 token、程序化特效与独立媒体 manifest。
- AssetGraph workflow、节点注册表、runtime package 构建与校验。
- 多阶段叙事 / 世界状态 / 资产候选审查包。
- MVP handoff audit 一键验证。

当前尚未完成：

- 正式前端页面。
- 视频帧序列、spritesheet 和 atlas 默认接入。
- 证据导出为 `summary.md / evidence.json / index.html` 的独立脚本。
- 正式 live campaign router。
- 多世界书选择与长期存档系统。

## 5. 历史文档处理规则

早期文档不直接删除，因为它们包含决策来源和演化过程。但使用时必须区分：

- `当前有效`：可以作为实现依据。
- `实现参考`：方向有效，但字段或流程可能已被更新。
- `审查证据`：用于证明某次流水线产物，不一定是运行时接口。
- `历史记录`：只说明当时讨论背景，不作为实现依据。

若旧文档中出现以下说法，应以当前索引和最新对应文档为准：

- “候选默认 3 个”：当前玩家侧默认 1 个方案，更多候选由 NPC、材料、技术或提示条件解锁。
- “前端直接读 JSON”：当前前端优先走后端 mock API。
- “图片直接作为游戏资产”：当前图片必须进入媒体后处理和 published manifest；视频帧路线另见 `VIDEO_FRAME_ASSET_PIPELINE_V0_1.md`。
- “长夜灯火是项目名”：当前项目本体是通用 AI 编译塔防系统，`long_night_lanterns` 是 MVP 世界书。

## 6. 协作分支规则

- `main`：稳定决策 / 发布基线，只在阶段性冻结窗口从 `develop` 受控同步。
- `develop`：当前集成事实源。
- `task/*` worktree：CodeBuddy / OpenCode / Codex headless 等代理执行任务。

主聊天可以讨论和决策；具体实现应优先进入 `develop` 派生的 task worktree，验收后合回 `develop`。稳定后再统一同步到 `main`。

`main` 允许短期落后于讨论和 `develop`，但这种落后应是受控滞后。同步前必须先检查 `main` 是否存在未识别的用户改动，并确认本次同步范围；不得为了追平文档而覆盖用户草稿。
