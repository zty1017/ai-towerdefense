# 任务队列

Last updated: 2026-06-29

## 1. 使用规则

本文是主会话生成给 CodeBuddy / OpenCode / Codex worker / 人类队友的任务来源。

优先级：

```text
P0：MVP 必须完成
P1：时间允许
P2：暂不做
```

执行规则：

- 每个任务优先在独立 `task/*` 分支或 worktree 中完成。
- CodeBuddy 可以使用自身子代理，但必须遵守任务包的允许修改范围。
- worker 不得修改 `.env`。
- worker 不得直接合并到 `main` 或 `develop`。
- worker 完成后必须汇报修改文件、测试命令、结果和风险。
- 主会话负责最终审查、合并和发布判断。

## 2. 推荐分支 / worktree

```text
develop
task/backend-session-and-runs
task/backend-research-job
task/frontend-shell
task/frontend-battle-runtime
task/content-demo-fixtures
task/locked-manifest
task/demo-evidence-export
docs/mvp-control-docs
```

## 3. P0 任务

### P0-001 后端基础与匿名 session

任务类型：实现

推荐执行：CodeBuddy

允许 CodeBuddy 子代理：是

目标：

```text
建立 FastAPI + SQLite 后端骨架，实现匿名 session 创建、读取、重置。
```

允许修改：

- `backend/`
- `pyproject.toml`
- `requirements.txt`
- `README.md`
- `control/TASK_QUEUE.md`

禁止修改：

- `.env`
- `docs/PROJECT_ARCHITECTURE_AND_GOVERNANCE.md`
- `docs/AI_ASSET_COMPILER_V0_1.md`
- `docs/ASSET_GRAPH_COMPILER_V0_1.md`

接口建议：

```text
POST /api/sessions
GET /api/sessions/{session_id}
POST /api/sessions/{session_id}/reset
```

验收命令：

```bash
python3 -m compileall backend
pytest backend/tests
```

完成标准：

- SQLite 表带 `session_id`。
- 不做真实登录。
- 不读取或打印 `.env`。

### P0-002 内容 fixture 与世界实例配置

任务类型：实现 / 内容

推荐执行：CodeBuddy + 内容队友

允许 CodeBuddy 子代理：是

目标：

```text
创建 MVP 默认世界实例 fixture，包括世界书模板、开局配置、第一张大地图、第一危机节点、初始材料和 NPC 占位。
```

允许修改：

- `content/`
- `game_data/`
- `shared/`
- `examples/`

验收命令：

```bash
python3 -m json.tool content/worldbooks/long_night_lanterns/world_instance_config.json
python3 -m json.tool game_data/demo/initial_map.json
```

完成标准：

- 使用稳定内部 ID。
- 玩家侧名称可作为 locked 示例，但不得假定未来写死。
- 不出现 provider / prompt / schema 技术词。

### P0-003 locked manifest v0.1 schema 与校验器

任务类型：实现

推荐执行：CodeBuddy

允许 CodeBuddy 子代理：是

参考材料：

- `/tmp/ai-compiled-td-research/locked_manifest_v0_1.md`
- `/tmp/ai-compiled-td-research/locked_manifest_prototype/`
- `docs/FRONTEND_PRODUCT_AND_TECH_DECISION.md`

目标：

```text
实现 locked manifest v0.1 的 JSON Schema、示例和校验脚本。
```

允许修改：

- `shared/schemas/`
- `examples/locked_manifests/`
- `tools/content_pipeline/`

验收命令：

```bash
python3 tools/content_pipeline/validate_locked_manifest.py examples/locked_manifests/mvp_light_snare.locked_manifest.json
python3 -m py_compile tools/content_pipeline/validate_locked_manifest.py
```

完成标准：

- 递归拒绝 `provider`、`model`、`raw_prompt`、`full_trace`、`raw_json`、`api_key`、`secret`。
- manifest 不内嵌完整 gameplay。
- media refs 不使用 provider 临时 URL。

### P0-004 研发任务状态机

任务类型：实现

推荐执行：CodeBuddy

允许 CodeBuddy 子代理：是

参考材料：

- `/tmp/ai-compiled-td-research/research_job_state_machine/`
- `docs/FRONTEND_PRODUCT_AND_TECH_DECISION.md`

目标：

```text
实现确认试作后的研发任务状态机：创建任务、倒计时、样品完成、战斗中送达、使用后进入战后观察。
```

允许修改：

- `backend/`
- `shared/`
- `tools/`
- `examples/`

验收命令：

```bash
pytest backend/tests
python3 -m compileall backend tools
```

完成标准：

- 支持 happy path。
- 支持 delayed / failed / unstable 状态枚举。
- 玩家侧事件流不出现 AI/provider/schema/prompt。
- 内部事件流可供证据导出读取。

### P0-005 Mock AI 编译管线 API

任务类型：实现

推荐执行：CodeBuddy

允许 CodeBuddy 子代理：是

目标：

```text
基于现有 content_pipeline，提供后端 API：玩家构想 -> 试作方案 -> 确认试作 -> compiled candidate / sample。
```

允许修改：

- `backend/`
- `tools/content_pipeline/`
- `shared/schemas/`
- `examples/`

接口建议：

```text
POST /api/sessions/{session_id}/research/proposals
POST /api/sessions/{session_id}/research/proposals/{proposal_id}/confirm
GET /api/sessions/{session_id}/research/jobs/{job_id}
```

验收命令：

```bash
python3 tools/content_pipeline/run_mock_pipeline.py examples/proposals/light_slow_field.proposal.json --output-dir /tmp/ai_compiled_td_mock_runs
pytest backend/tests
```

完成标准：

- P0 可用 mock / fixture，不强制真实 provider。
- 结构化输出必须经过本地校验。
- 技术错误进入内部日志，玩家侧只显示世界内状态。

### P0-006 前端应用骨架

任务类型：实现

推荐执行：CodeBuddy

允许 CodeBuddy 子代理：是

目标：

```text
创建 React + Vite + TypeScript 前端骨架，包含页面路由和基础布局。
```

允许修改：

- `frontend/`
- `package.json`
- `pnpm-lock.yaml`
- `README.md`

技术：

```text
React
Vite
TypeScript
react-router
Zustand
TanStack Query
```

页面：

- 本地档案入口。
- 世界实例配置。
- 预制开场。
- 大地图。
- 节点 Briefing。
- 现场应急研发。
- 塔防战斗。
- 战后结算。

验收命令：

```bash
npm install
npm run build
npm run lint
```

完成标准：

- 可启动本地前端。
- 页面路由完整。
- 不做登录。
- 不显示 Studio/debug 页面。

### P0-007 Phaser 战斗运行时原型

任务类型：实现

推荐执行：CodeBuddy

允许 CodeBuddy 子代理：是

目标：

```text
实现 Phaser 3 战斗页原型：斜视角伪 3D 地图、敌人路径、样品热栏、减速陷阱、基础 HUD。
```

允许修改：

- `frontend/src/game/`
- `frontend/src/pages/Battle*`
- `frontend/src/components/battle/`
- `frontend/public/assets/`

验收命令：

```bash
npm run build
```

完成标准：

- 中央战场可见。
- 敌人沿路径移动。
- 研发倒计时后底部热栏点亮样品。
- 玩家可部署样品。
- 样品触发后敌人明显减速。
- 有 `ring_pulse` / `aura_field` / `sprite_flash` 至少一种表现。

### P0-008 前端玩家主链路集成

任务类型：实现 / 集成

推荐执行：CodeBuddy

允许 CodeBuddy 子代理：是

目标：

```text
把本地档案入口、世界配置、开场、大地图、briefing、现场研发、战斗、战后结算串成完整可走流程。
```

允许修改：

- `frontend/`
- `backend/`
- `game_data/`
- `content/`

验收命令：

```bash
npm run build
pytest backend/tests
```

完成标准：

- 新 session 能走完整链路。
- 结算后返回大地图且状态变化。
- 玩家侧不出现 AI/provider/schema/prompt/raw JSON 等词。

### P0-009 战后结算与世界生长

任务类型：实现 / 内容

推荐执行：CodeBuddy + 内容队友

允许 CodeBuddy 子代理：是

参考材料：

- `/tmp/ai-compiled-td-research/settlement_world_growth.md`

目标：

```text
实现战后结算页和后端结果记录：节点状态变化、资源变化、样品观察、NPC 反馈、下一步研发线索。
```

允许修改：

- `frontend/`
- `backend/`
- `content/`
- `game_data/`

验收命令：

```bash
npm run build
pytest backend/tests
```

完成标准：

- 胜利和失败都能产生结果。
- 样品表现写入内部记录。
- 玩家侧用世界内语言表达。
- 后续正式研发线索被记录但不强制实现正式研发页。

### P0-010 演示证据导出脚本

任务类型：实现

推荐执行：CodeBuddy

允许 CodeBuddy 子代理：否

参考材料：

- `/tmp/ai-compiled-td-research/demo_evidence_exporter/`

目标：

```text
实现从 session / run 记录导出 summary.md、evidence.json、index.html 的脚本。
```

允许修改：

- `tools/demo/`
- `backend/`
- `control/`

验收命令：

```bash
python3 tools/demo/export_evidence.py --help
python3 tools/demo/export_evidence.py --fixture examples/demo/run_bundle.json --out /tmp/ai_compiled_td_evidence
```

完成标准：

- 导出 Markdown、JSON、HTML。
- 不泄露 API key。
- 不输出完整敏感 prompt。
- 不输出 provider 原始错误栈。

## 4. P1 任务

### P1-001 真实 provider 接入

目标：

```text
把 mock 方案生成替换为可配置 provider，保留演示稳定模式。
```

优先模型：

- 方舟 Coding Plan 长上下文模型。
- DeepSeek 官方 fallback。
- GLM fallback。

### P1-002 离线图像生成与缓存

目标：

```text
用 Agnes / GLM / CodeBuddy Hunyuan 生成候选图标或动画卡，下载并缓存为 reviewed / locked 素材。
```

### P1-003 正式研发机构轻量入口

目标：

```text
战后出现正式研发机构入口，只展示样品可登记为后续蓝图线索，不实现完整技术树。
```

### P1-004 第二战役节点

目标：

```text
增加一个节点，用第一场样品反馈推动第二次研发。
```

## 5. P2 不做任务

这些任务禁止进入 MVP：

- 登录注册。
- 多人联机。
- 真 3D。
- 实时视频生成。
- 完整技术树。
- 复杂经营系统。
- 可视化 AssetGraph 编辑器。
- 运行时动态注册新 node / effect。

## 6. 首批推荐派工顺序

建议顺序：

```text
1. P0-003 locked manifest schema 与校验器
2. P0-001 后端 session
3. P0-002 内容 fixture
4. P0-004 研发任务状态机
5. P0-005 Mock AI 编译管线 API
6. P0-006 前端应用骨架
7. P0-007 Phaser 战斗运行时
8. P0-008 主链路集成
9. P0-009 战后结算
10. P0-010 演示证据导出
```

并行建议：

```text
P0-003、P0-001、P0-002 可以并行。
P0-006 可以与后端并行。
P0-007 等前端骨架完成后开始。
P0-010 可以在后端 run 记录结构确定后开始。
```

## 7. 下一批 P0 任务（AssetGraph Kernel 之后）

以下任务在 AssetGraph Kernel v0.1（task/assetgraph-kernel）落地后推进。已完成的 P0-001/P0-002/P0-003 不再改写。

### P0-011 AssetGraph Kernel

任务类型：实现

推荐执行：CodeBuddy

目标：

```text
建立可跑通的 AssetGraph Kernel v0.1，能用 DAG 执行现有 mock 编译管线，
产生 artifact 与 execution trace。
```

允许修改：

- `docs/ASSET_GRAPH_COMPILER_V0_1.md`
- `control/TASK_QUEUE.md`
- `shared/schemas/`
- `shared/asset_graph/`
- `examples/workflows/`
- `examples/asset_graph/`
- `tools/asset_graph/`
- `tools/content_pipeline/`（仅必要可复用函数适配，不破坏现有 CLI）

禁止修改：

- `.env`
- `backend/`
- `frontend/`
- `content/`
- `game_data/`
- 已有 provider 配置与密钥

验收命令：

```bash
python3 tools/asset_graph/validate_workflow.py examples/workflows/mvp_mock_asset_compile.workflow.json
python3 tools/asset_graph/run_workflow.py examples/workflows/mvp_mock_asset_compile.workflow.json --output-dir /tmp/ai_td_assetgraph_runs/mock_asset_compile
python3 tools/asset_graph/run_workflow.py examples/workflows/mvp_temporary_trap_delivery.workflow.json --output-dir /tmp/ai_td_assetgraph_runs/trap_delivery
python3 tools/asset_graph/run_workflow.py examples/workflows/mvp_media_stub_publish.workflow.json --output-dir /tmp/ai_td_assetgraph_runs/media_stub
python3 -m compileall tools/asset_graph tools/content_pipeline
python3 tools/content_pipeline/run_mock_pipeline.py examples/proposals/light_slow_field.proposal.json --output-dir /tmp/ai_compiled_td_mock_runs
```

完成标准：

- DAG 拓扑排序执行，无循环。
- 节点间传 ArtifactRef，不在边上塞大对象。
- 每个节点写 artifact 到 output_dir，trace 记录 status/start/end/input refs/output refs/errors。
- 只实现 deterministic/mock 节点，不调用真实 LLM/provider。
- runtime_public artifact 不得引用 raw_media 或 provider 临时 URL。
- 不允许 provider/model/raw_prompt/full_trace/raw_json/api_key/secret/unreviewed_content 出现在 runtime_public artifact。
- 现有 content_pipeline CLI 仍然可用。

### P0-012 RuntimePackage v0.1 schema/builder

任务类型：实现

目标：

```text
基于 AssetGraph 的 runtime.build_package_stub 节点产出，定义
RuntimePackage v0.1 schema 与正式 builder，作为前端运行时加载的已锁定
资产包。RuntimePackage 必须只引用 published_media，不得引用 raw_media /
processed_media 或 provider 临时 URL。
```

允许修改：

- `shared/schemas/`
- `tools/asset_graph/`
- `examples/`

验收命令（建议）：

```bash
python3 tools/asset_graph/validate_runtime_package.py examples/runtime_packages/mvp_demo.runtime_package.json
python3 -m py_compile tools/asset_graph/validate_runtime_package.py
```

### P0-013 ResearchJob API 接入 AssetGraph

任务类型：实现 / 集成

目标：

```text
把后端 ResearchJob 状态机接入 AssetGraph Kernel。玩家确认试作后，
后端创建 ResearchJob 并触发 mvp_mock_asset_compile workflow；
研发倒计时结束后，runtime.build_package_stub / research.build_delivery_payload_stub
节点产出的 artifact 写回 session 状态。
```

允许修改：

- `backend/`
- `tools/asset_graph/`
- `shared/`

完成标准：

- ResearchJob 状态机驱动 workflow 执行。
- 玩家侧不出现 AI/provider/schema/prompt。
- 内部 trace 可供证据导出读取。

### P0-014 DAG templates 扩展：defense / narrative / media

任务类型：实现 / 内容

目标：

```text
在 AssetGraph Kernel 上扩展三类 DAG 模板：
- defense：防御塔蓝图编译流程（提案 -> 编译 -> 校验 -> 模拟 -> runtime package）。
- narrative：NPC 反馈 / 战后结算 / 世界生长事件生成流程。
- media：raw_media -> processed_media -> published_media 完整媒体发布子图，
  体现 MVP 后第一梯队节点（remove_background、crop_and_pad、normalize_canvas、
  assign_anchor、pack_sprite_sheet、build_atlas_json）的占位与边界。
```

允许修改：

- `examples/workflows/`
- `examples/asset_graph/`
- `shared/asset_graph/`
- `tools/asset_graph/`（仅必要时新增节点实现）

