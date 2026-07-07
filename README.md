# AI-Compiled Tower Defense — Compiler MVP

通用 AI 驱动塔防 / 游戏内容编译 MVP。

本项目不是单一《长夜灯火》游戏。《长夜灯火》只是 MVP 世界书模板，用来验证：

```text
玩家想法 / 世界书 / 战斗上下文
  -> 受控 AI 编译
  -> 可玩资产、剧情节点、任务、随机事件和世界状态变化
  -> 浏览器前端可演示的塔防体验
```

当前后端是 FastAPI + SQLite。它提供匿名 session、研发提案 / job、前端 mock API、fixture-backed MVP 游玩链路和审查证据入口。不做真实注册登录，不收集 PII。

## 文档入口

先读：

```text
docs/CURRENT_ARCHITECTURE_INDEX.md
```

这个文件标明哪些设计文档是当前有效事实源，哪些只是审查证据或历史记录。

## Layout

```
docs/
  CURRENT_ARCHITECTURE_INDEX.md
  FRONTEND_MOCK_API_V0_1.md
  ASSET_GRAPH_COMPILER_V0_1.md
  MEDIA_ASSET_QUALITY_PIPELINE_V0_2.md
  VIDEO_FRAME_ASSET_PIPELINE_V0_1.md
  FRONTEND_RUNTIME_MOCK_ART_KIT_V0_1.md

backend/
  app/
    main.py
    config.py        # env-based config, never reads .env
    db.py            # sqlite3 connection + schema init
    models.py
    api/
      health.py
      sessions.py
      research.py
      frontend_mock.py
    services/
      research_service.py
      frontend_mock_service.py
  tests/
    conftest.py
    test_sessions.py
    test_research_jobs.py
    test_frontend_mock_api.py

examples/
  frontend_mock/
  runtime_packages/
  review_packs/
  workflows/

game_data/
  demo/
  media/frontend_mock/
  media/frontend_runtime_mock/

tools/
  asset_graph/
  content_pipeline/
  media/
  world_state/
```

## Configuration

所有运行配置都通过环境变量读取，并带有安全默认值。后端不会读取 `.env`。

| 变量 | 默认值 | 用途 |
| ------------- | ----------------------------- | -------------------------------- |
| `APP_DB_PATH` | `backend/data/app.db`         | SQLite database file path        |
| `APP_TITLE`   | `AI-Compiled Tower Defense…`  | FastAPI app title                |
| `APP_VERSION` | `0.1.0`                       | FastAPI app version              |

## Running

```bash
pip install -r requirements.txt
uvicorn app.main:app --app-dir backend --reload
```

服务启动时会自动创建 SQLite schema。

## API

### 基础

| Method | Path | 说明 |
| ------ | ---- | ----------- |
| GET | `/api/health` | Health check |
| POST | `/api/sessions` | Create an anonymous session |
| GET | `/api/sessions/{session_id}` | Read a session |
| POST | `/api/sessions/{session_id}/reset` | Reset per-session demo data |

### 研发 / 编译

| Method | Path | 说明 |
| ------ | ---- | ----------- |
| POST | `/api/sessions/{session_id}/research/proposals` | Create a fixture-backed research proposal |
| POST | `/api/sessions/{session_id}/research/proposals/{proposal_id}/confirm` | Confirm proposal and run deterministic workflows |
| GET | `/api/sessions/{session_id}/research/jobs/{job_id}` | Read research job |

### 前端 Mock

这些接口不调用 LLM、不调用图片 provider、不读取 `.env`。它们只读取已审查 fixture、mock pack 和媒体 manifest，让前端先跑完整 MVP 链路。

| Method | Path | 说明 |
| ------ | ---- | ----------- |
| POST | `/api/sessions/{session_id}/world-instance` | Create fixture-backed world instance |
| GET | `/api/sessions/{session_id}/frontend-mock-pack` | Read player-safe frontend mock pack |
| GET | `/api/sessions/{session_id}/opening` | Read prebuilt opening |
| GET | `/api/sessions/{session_id}/animation-seeds` | Read image-to-video seed manifest |
| GET | `/api/sessions/{session_id}/runtime-art-kit` | Read developer-compiled battle runtime art |
| GET | `/api/sessions/{session_id}/generation-schedule` | Read fixture-backed scheduler buffer |
| POST | `/api/sessions/{session_id}/generation-schedule/runs` | Persist a scheduler dry-run record |
| GET | `/api/sessions/{session_id}/generation-schedule/runs/latest` | Read latest scheduler dry-run record |
| GET | `/api/sessions/{session_id}/generation-schedule/queue` | Read latest scheduler queue items |
| POST | `/api/sessions/{session_id}/generation-schedule/queue/{schedule_item_id}/claim` | Claim a queued scheduler item |
| POST | `/api/sessions/{session_id}/generation-schedule/queue/{schedule_item_id}/complete` | Complete a queued or claimed scheduler item |
| POST | `/api/sessions/{session_id}/generation-schedule/queue/{schedule_item_id}/fail` | Fail a queued or claimed scheduler item |
| POST | `/api/sessions/{session_id}/generation-schedule/queue/{schedule_item_id}/retry` | Requeue a failed scheduler item within budget |
| POST | `/api/sessions/{session_id}/generation-schedule/queue/{schedule_item_id}/fallback` | Select static fallback for a failed/review-blocked item |
| POST | `/api/sessions/{session_id}/generation-schedule/workers/dry-run-step` | Process one queued scheduler item without providers |
| POST | `/api/sessions/{session_id}/generation-schedule/workers/live-executor-guard` | Record a blocked live-provider intent without providers |
| GET | `/api/sessions/{session_id}/map` | Read strategic map and session world state |
| GET | `/api/sessions/{session_id}/nodes/{node_id}/briefing` | Read node briefing |
| GET | `/api/sessions/{session_id}/battles/{node_id}/config` | Read battle config and toolbar assets |
| GET | `/api/sessions/{session_id}/battles/{node_id}/runtime-package` | Read reviewed runtime package |
| GET | `/api/sessions/{session_id}/battles/{node_id}/map-runtime-package` | Read runtime-safe map package |
| POST | `/api/sessions/{session_id}/battles/{node_id}/results` | Submit mock battle result and apply world delta |
| GET | `/api/sessions/{session_id}/settlement/latest` | Read latest settlement |
| GET | `/api/sessions/{session_id}/evidence` | Read simple demo evidence payload |

静态媒体挂载：

```text
/assets/frontend_mock/processed
/assets/frontend_mock/generated
/assets/frontend_runtime_mock/processed
/assets/frontend_runtime_mock/generated
```

当前 `processed` PNG 可用于前端 mock；`generated` PNG 是后续图生视频 / 动画帧管线的 seed。`frontend_runtime_mock` 是开发者预编译的战斗运行时美术包，覆盖敌人、目标物、基础防御件、NPC 头像、地图 token 和程序化特效。

## Tests

日常开发优先跑快速质量门。它串起无浏览器、无 provider、无 `.env` 的关键静态 / 结构检查，用来在几秒级发现常见破坏。

```bash
python3 tools/dev/run_fast_quality_gate.py
```

合并前建议跑本地 pre-merge quality gate。它在 fast gate 之外追加 WorkerTaskPack 全量 profile dry-run、profile 审计、迁移 dry-run 和 `git diff --check`，仍然不跑浏览器、不调用 provider、不读取 `.env`。

```bash
python3 tools/dev/run_premerge_quality_gate.py
```

需要改后端服务或数据库行为时，先检查当前环境是否已经具备完整测试依赖：

```bash
python3 tools/dev/check_test_env.py
```

如果缺依赖，使用项目声明的依赖文件安装：

```bash
python3 -m pip install -r requirements.txt
```

完整测试：

```bash
python3 -m pytest backend/tests
```

测试使用 `tmp_path` 把 `APP_DB_PATH` 指向临时 SQLite 文件，不会触碰主数据库。

录屏、评审或合并前跑完整 evidence。具备浏览器时直接运行：

```bash
python3 tools/demo/run_demo_evidence_suite.py --output-root /tmp/ai_td_demo_evidence_suite
```

该套件会先做 browser smoke environment preflight；没有可用 Chromium 且未显式允许降级时会早停。通过预检后，suite 会运行 Generation Scheduler review-only pipeline smoke 和 provider runner outbox consume/import smoke，再采集浏览器玩家主链路截图、多节点战斗截图，并导出 full evidence。scheduler smoke 会启动临时本地后端和临时 SQLite，验证 background handoff outbox、prefetch-cache、activation-gate 与 shared cache 空命中边界；outbox import smoke 会验证外部 runner outbox 经本地 consumer 生成 receipt/envelope 后能显式导回临时后端，并让 prefetch-cache 从 0 个 review-only envelope 变为 2 个。两者都不调用 provider、不读取 `.env`、不写世界状态、不激活 runtime。默认 `--scheduler-smoke-runner auto` 会优先复用当前 worktree 或主工作区的 `.venv/bin/python`，没有可用 `.venv` 时回退 `uv run`；实际 runner、浏览器预检结果、14 张玩家主链路截图摘要和 6 张多节点战斗截图摘要都会写入 suite report。

当前环境没有浏览器时，可以显式记录降级证据：

```bash
python3 tools/demo/run_demo_evidence_suite.py --allow-missing-browser --output-root /tmp/ai_td_demo_evidence_suite
```

只需要导出已审查 evidence bundle 时运行：

```bash
python3 tools/demo/export_evidence.py --output-dir /tmp/ai_td_demo_evidence
```

该命令默认使用 `--validation-profile full`，会运行完整 validation commands；只有本次导出校验 `passed` 才返回 0。日常开发如果只想快速查看 `summary.md` / `index.html`，可以显式跳过 validation commands：

```bash
python3 tools/demo/export_evidence.py --validation-profile summary-only --output-dir /tmp/ai_td_demo_evidence_preview
```

`summary-only` 会在 `validation_summary.current_export_validation` 中标记 `status=skipped`，只用于本地预览；最终评审、录屏或合并前仍使用默认 `full` 导出，或运行完整 demo evidence suite。
