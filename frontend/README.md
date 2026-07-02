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

前端会优先创建匿名 session，并调用 `/api/sessions/{session_id}/...` 下的前端 mock API、研发提案 API 和战斗结果 API。媒体资源走后端挂载的 `/assets/frontend_mock/...` 与 `/assets/frontend_runtime_mock/...`，包含 `processed`、`generated`、`atlas_frames` 和 `atlas_sheets`。

API 模式下，前端会读取 `/api/sessions/{session_id}/campaign-router` 决定当前节点、下一节点和前视窗口；进入当前节点时会静默调用 `/api/sessions/{session_id}/campaign-router/prefetch-next` 触发一次 fixture-backed dry-run 预取。静态模式仍固定使用灰灯驿站首战作为可玩兜底。

战斗地图运行时优先消费后端返回的 `map_runtime_package`，用其中的路径、塔位、目标、出生点和视觉层引用来驱动画面；旧 `battle_config` 只作为兼容数据。

玩家默认战斗视图使用 MapRuntimePackage 驱动的程序化大画面底座：canvas 会按包内路径、塔位、目标和出生点绘制地形、土路、部署基座、目标地标与入口雾潮。`battle_control_sketch` 和 `battle_reference_board` 不得作为默认玩家底图；失败的整图候选只保留为审查证据，不进入默认战斗画面。

媒体加载优先读取 atlas manifest：

```text
game_data/media/frontend_mock/frontend_media_atlas_manifest.v0.1.json
game_data/media/frontend_runtime_mock/frontend_runtime_art_atlas_manifest.v0.1.json
```

当前 atlas 是 `spritesheet` 模式，sprite 类动画入口包含确定性的多帧 PNG frame sequence，并打包为实体 spritesheet PNG；静态角色仍是一帧。战斗绘制优先裁剪 spritesheet，找不到 atlas 时会回退到旧的 media manifest。后续真实图生视频关键帧可以沿用同一接口替换 frames 来源。

视觉合约可在无浏览器环境中先跑：

```bash
python3 tools/frontend/validate_battle_visual_contract.py
python3 tools/frontend/validate_campaign_router_frontend_contract.py
```

这些检查不会替代真实截图，但会阻止控制图进入玩家默认体验、失败整图被发布、程序化底座入口缺失、战斗画布被压成小面板，以及 API 模式退回固定首战节点。

控制图和参考图只允许作为调试 / evidence 辅助素材。需要临时查看时，在 URL 上追加：

```text
?mapVisualDebug=1
```

或：

```text
?evidence=1
```

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

静态模式会把 manifest 中的 `/assets/frontend_runtime_mock/...`、`/assets/frontend_mock/...` 和 `/assets/map_visual_reference/...` 映射到仓库内的 `game_data/media/...` 路径，包含多帧 atlas 的 `atlas_frames` 与 `atlas_sheets` 子目录。

## 验证命令

```bash
node --check frontend/app.js
python3 -m json.tool examples/frontend_mock/frontend_mock_pack.v0.1.json >/tmp/frontend_mock_pack.check
python3 -m json.tool examples/frontend_mock/frontend_battle_mock_art_kit.v0.1.json >/tmp/frontend_runtime_kit.check
python3 -m json.tool game_data/media/frontend_runtime_mock/frontend_runtime_art_media_manifest.v0.1.json >/tmp/frontend_runtime_media.check
python3 tools/media/validate_media_atlas_manifest.py game_data/media/frontend_runtime_mock/frontend_runtime_art_atlas_manifest.v0.1.json
python3 tools/media/validate_multiframe_atlas_contract.py game_data/media/frontend_runtime_mock/frontend_runtime_art_atlas_manifest.v0.1.json
```
