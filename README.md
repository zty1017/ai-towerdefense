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
| GET | `/api/sessions/{session_id}/map` | Read strategic map and session world state |
| GET | `/api/sessions/{session_id}/nodes/{node_id}/briefing` | Read node briefing |
| GET | `/api/sessions/{session_id}/battles/{node_id}/config` | Read battle config and toolbar assets |
| GET | `/api/sessions/{session_id}/battles/{node_id}/runtime-package` | Read reviewed runtime package |
| POST | `/api/sessions/{session_id}/battles/{node_id}/results` | Submit mock battle result and apply world delta |
| GET | `/api/sessions/{session_id}/settlement/latest` | Read latest settlement |
| GET | `/api/sessions/{session_id}/evidence` | Read simple demo evidence payload |

静态媒体挂载：

```text
/assets/frontend_mock/processed
/assets/frontend_mock/generated
```

当前 `processed` PNG 可用于前端 mock；`generated` PNG 是后续图生视频 / 动画帧管线的 seed。

## Tests

```bash
pytest backend/tests
```

测试使用 `tmp_path` 把 `APP_DB_PATH` 指向临时 SQLite 文件，不会触碰主数据库。

在缺少依赖的极简环境中，至少运行：

```bash
python3 -m compileall backend
python3 tools/content_pipeline/run_mvp_handoff_audit.py --validate
python3 tools/content_pipeline/validate_frontend_mock_pack.py examples/frontend_mock/frontend_mock_pack.v0.1.json
python3 tools/media/validate_frontend_mock_media_pack.py game_data/media/frontend_mock/frontend_media_manifest.v0.1.json
```
