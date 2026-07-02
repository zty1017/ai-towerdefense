# 前端 MVP 运行说明

这是第一版无构建单页演示，入口是 `frontend/index.html`。不需要 `npm install`，不依赖 CDN。

## 后端 API 模式

从仓库根目录启动后端：

```bash
uvicorn app.main:app --app-dir backend --reload
```

然后访问：

```text
http://127.0.0.1:8000/frontend/index.html
```

前端会优先创建匿名 session，并调用 `/api/sessions/{session_id}/...` 下的前端 mock API、研发提案 API 和战斗结果 API。媒体资源走后端挂载的 `/assets/frontend_mock/...` 与 `/assets/frontend_runtime_mock/...`。

战斗地图运行时优先消费后端返回的 `map_runtime_package`，用其中的路径、塔位、目标、出生点和视觉层引用来驱动画面；旧 `battle_config` 只作为兼容数据。视觉层优先使用 `battle_runtime_background`，控制草图和 reference board 只作为开发期 fallback。

如果你希望用独立静态服务打开前端，也可以在 URL 上指定后端：

```text
http://127.0.0.1:5174/frontend/index.html?apiBase=http://127.0.0.1:8000
```

## 静态 fallback 模式

从仓库根目录启动静态服务：

```bash
python3 -m http.server 5174
```

然后访问：

```text
http://127.0.0.1:5174/frontend/index.html
```

如果后端不可用，前端会读取仓库内静态 JSON：

- `examples/frontend_mock/frontend_mock_pack.v0.1.json`
- `examples/frontend_mock/frontend_battle_mock_art_kit.v0.1.json`
- `game_data/media/frontend_mock/frontend_media_manifest.v0.1.json`
- `game_data/media/frontend_runtime_mock/frontend_runtime_art_media_manifest.v0.1.json`
- `examples/map_runtime_packages/mvp_first_battle.map_runtime_package.json`
- `game_data/demo/*.json`
- `content/worldbooks/long_night_lanterns/*.json`

静态模式会把 manifest 中的 `/assets/frontend_runtime_mock/...`、`/assets/frontend_mock/...` 和 `/assets/map_visual_reference/...` 映射到仓库内的 `game_data/media/...` 路径。

## 验证命令

```bash
node --check frontend/app.js
python3 -m json.tool examples/frontend_mock/frontend_mock_pack.v0.1.json >/tmp/frontend_mock_pack.check
python3 -m json.tool examples/frontend_mock/frontend_battle_mock_art_kit.v0.1.json >/tmp/frontend_runtime_kit.check
python3 -m json.tool game_data/media/frontend_runtime_mock/frontend_runtime_art_media_manifest.v0.1.json >/tmp/frontend_runtime_media.check
```
