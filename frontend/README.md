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

API 模式下，前端会读取 `/api/sessions/{session_id}/campaign-router` 决定当前节点、下一节点和前视窗口；进入当前节点时会静默调用 `/api/sessions/{session_id}/campaign-router/prefetch-next` 触发一次 fixture-backed dry-run 预取。静态模式使用同一套节点资源组织三关 MVP 短流程：灰灯驿站、灯芯仓、旧信号塔，战后通过本地 RunWorldState 快照推进地图、任务、NPC 和随机事件。

战斗地图运行时优先消费后端返回的 `map_runtime_package`，用其中的路径、塔位、目标、出生点和视觉层引用来驱动画面；旧 `battle_config` 只作为兼容数据。

如果后端返回 `map_render_plan_bundle`，前端会读取其中的 `MapStylePack` 调整地形、道路、部署基座、目标和出生点的玩家侧表现色，也会读取 `ProceduralMapRenderPlan` 中的表现层几何参数，例如道路宽度、路肩宽度和部署基座 footprint。路线、塔位、目标、出生点等玩法语义仍以 `MapRuntimePackage` 为准，前端不得从 RenderPlan 或图片反推这些事实。

玩家默认战斗视图优先读取 `LayeredMapVisualPackage v0.1` 的 `composited` 玩家层作为大画面底图。三个 MVP 战斗节点的静态包位于 `game_data/media/layered_maps/{node_id}/layered_map_visual_package.v0.1.json`，其中每个 SVG layer 都带 local path、URL、sha256 和质量状态；当前可见层拆成 `terrain_base / terrain_detail / road_shadow / road_edge / road_surface / build_slots / objectives / spawn / semantic_props / non_blocking_decorations / lighting / fog_weather / color_grade / composited`。`media_assets` 记录 8 类 PNG 纹理或 overlay tile，并可记录本地审查通过的 `reviewed_painted_backdrop` 整图底图。发布给前端的 SVG 会内嵌这些本地媒体，manifest 仍记录本地 PNG 文件用于审查和追踪。整图底图不得烘焙玩家可见道路、塔位圆盘、部署平台或可交互槽位；默认玩家画面也不得叠加 `battle_control_sketch` / `battle_reference_board` 这类 debug/reference 图。它只负责表现层，路线、塔位、目标、出生点和碰撞仍以 `MapRuntimePackage` 为准。当前没有分层包或分层包未通过质量状态时，前端才回退到 MapRuntimePackage 驱动的程序化战场底座。前端还会读取 `MapComponentMediaManifest v0.1`，把 reviewed 本地组件作为表现层贴片；这些组件不得成为路线、塔位、目标或碰撞事实源。失败的整图候选只保留为审查证据，不进入默认战斗画面。

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

这些检查不会替代真实截图，但会阻止控制图进入玩家默认体验、失败整图被发布、玩家底图入口缺失、战斗画布被压成小面板、RenderPlan 表现参数接线丢失，以及 API 模式退回固定首战节点。

前端运行时契约冻结在 `frontend/runtime_contract_manifest.v0.1.json`，最小激活示例在 `examples/frontend_runtime/activated_runtime_bundle.mvp.v0.1.json`。它们用于约束公开深链、关键 selector、battle smoke hook、RuntimeBundle / RuntimeSnapshot / FeatureSnapshot 命名和玩家侧 runtime-safe 边界；可用下面命令复验：

现有前后端 schema 按职责分层，不互相替代：

- `runtime_package / map_runtime_package / narrative_event_bundle / run_world_state / proposal` 是 AI 编译与玩法领域事实源。
- `FrontendMockPayloadResponse` 等 Pydantic 模型是 HTTP 传输外壳；`frontend_mock_pack` 是固定演示内容包。
- `frontend_feature_snapshot / frontend_surface_contribution` 只描述已激活领域对象如何投影到既有页面白名单槽位。它通过 `source_refs` 追溯上游对象，只携带必要展示字段，不复制完整领域对象，也不能携带任意 HTML、脚本、样式、事件处理器或新页面路由。

API 模式可通过 `GET /api/sessions/{session_id}/runtime/feature-snapshots?node_id=...` 刷新投影。研发提案、RunWorldState 中的任务/NPC/随机事件、剧情事件日志和战斗结算都沿这条通道进入工坊、战略图、剧情对话与结算页面；战斗对象的可执行玩法仍由独立的受控 `behavior_abi` 投影负责。

`frontend/runtime/` 存放从 `app.js` 拆出的运行时模块。`feature-gates.js` 是 AI 编译产物进入玩家界面的统一门禁：只接受已激活、运行时安全检查通过、未隔离且对应 FeatureSnapshot 可用的 bundle；声明式 surface contribution 只能进入白名单槽位，不能携带 HTML、JS、CSS 或自定义组件代码。`app-flow-orchestrator.js` 只允许编译 surface 映射到已注册的 map/workshop/battle/settlement/opening 页面，未知 surface 不能创建新路由。`strategic-map-projection.js` 将 Map 空间结构、RunWorldState 任务/事件/NPC 和已激活 contribution 合并为稳定 snapshot，`strategic-map-feature-controller.js` 只负责呈现该 snapshot；`strategic-map-controller.js` 独立负责缩放、拖拽和边界。`onboarding-feature-controller.js`、`workshop-feature-controller.js` 和 `settlement-feature-controller.js` 分别负责建档/开场、现场试作与战后结算。`root-event-router.js` 统一安装根节点和窗口级事件。战斗侧由 `battle-map-adapter.js` 解释 MapRuntimePackage，`runtime-projection-adapter.js` 投影已过门禁的战斗对象 ABI，六个 renderer 只负责表现，`battle-rules.js` 与 `battle-simulation.js` 负责受控玩法。入口仍由 `app.js` 编排，前端不会发布或激活候选产物。

```bash
python3 tools/frontend/validate_frontend_runtime_contract_manifest.py frontend/runtime_contract_manifest.v0.1.json
python3 tools/frontend/validate_activated_runtime_bundle_fixture.py examples/frontend_runtime/activated_runtime_bundle.mvp.v0.1.json
python3 tools/frontend/validate_frontend_feature_snapshots.py examples/frontend_runtime/activated_runtime_bundle.mvp.v0.1.json
```

浏览器视觉 / 交互烟测在具备 Chromium 兼容浏览器的环境中运行。推荐用项目虚拟环境安装 Playwright 与 Linux Chromium：

```bash
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -m playwright install chromium
```

先做浏览器环境预检：

```bash
.venv/bin/python tools/frontend/check_browser_smoke_environment.py --output /tmp/browser_smoke_environment.json
```

战斗页截图烟测：

```bash
.venv/bin/python tools/frontend/capture_battle_visual_smoke.py --output-dir /tmp/p0m_browser_visual_smoke
```

它会启动本地静态服务，打开 `frontend/index.html?static=1&battleVisualSmoke=1&battleVisualHold=1`，采集桌面和移动视口截图，并写出 `battle_visual_smoke_report.v0.1.json`。`battleVisualSmoke=1` / `battleVisualHold=1` 只是验收深链，正常玩家流程不会使用；`static=1` 用于让烟测不依赖后端服务。

战斗剧情模态层烟测（`capture_battle_dialogue_modal_smoke.py` 与 `battle_dialogue_modal_smoke_report.v0.1.json`）为 planned 项，不在当前前端 runtime 模块化包内交付；其深链 `battleDialogueSmoke=1` 已作为公开契约冻结，待脚本落地后再纳入烟测流程。

战斗拖拽部署烟测可指定任意已投影工具，确认资源、部署记录和战场实体都发生变化。默认验证基础灯栏，第二条命令验证由 ActivatedRuntimeBundle 注入的第四个动态塔：

```bash
.venv/bin/python tools/frontend/capture_battle_drag_interaction_smoke.py --output-dir /tmp/battle_drag_interaction_smoke
.venv/bin/python tools/frontend/capture_battle_drag_interaction_smoke.py --tool asset_light_slow_tower_001 --output-dir /tmp/battle_dynamic_tool_drag_smoke
.venv/bin/python tools/frontend/validate_battle_drag_interaction_smoke_report.py --expected-tool asset_light_slow_tower_001 /tmp/battle_dynamic_tool_drag_smoke/battle_drag_interaction_smoke_report.v0.1.json
```

玩家主链路截图烟测会自动点击档案、开局配置、开场、大地图、工坊、战斗和结算：

```bash
.venv/bin/python tools/frontend/capture_frontend_flow_visual_smoke.py --output-dir /tmp/frontend_flow_visual_smoke
```

战略地图交互烟测会在桌面和移动视口执行放大、拖拽和复位，校验相机 `viewBox` 的真实变化并保存截图证据：

```bash
.venv/bin/python tools/frontend/capture_strategic_map_interaction_smoke.py --output-dir /tmp/strategic_map_interaction_smoke
.venv/bin/python tools/frontend/validate_strategic_map_interaction_smoke_report.py /tmp/strategic_map_interaction_smoke/strategic_map_interaction_smoke_report.v0.1.json
```

前后端动态投影烟测会使用临时 SQLite 启动真实 API，自动生成工坊提案、进入战斗并检查结算投影；它会写演示 session 状态，但不调用 provider、不读取 `.env`、不激活候选运行包：

```bash
.venv/bin/python tools/frontend/capture_frontend_feature_projection_api_smoke.py --output-dir /tmp/frontend_feature_projection_api_smoke
.venv/bin/python tools/frontend/validate_frontend_feature_projection_api_smoke_report.py /tmp/frontend_feature_projection_api_smoke/frontend_feature_projection_api_smoke_report.v0.1.json
```

如果当前机器没有浏览器，可先记录环境探测结果：

```bash
.venv/bin/python tools/frontend/capture_battle_visual_smoke.py --allow-missing-browser --output-dir /tmp/p0m_browser_visual_smoke
```

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
- `game_data/media/map_components/map_component_media_manifest.v0.1.json`
- `examples/map_runtime_packages/mvp_first_battle.map_runtime_package.json`
- `examples/map_style_packs/long_night_ruined_outpost.map_style_pack.json`
- `examples/map_render_plans/mvp_first_battle.procedural_map_render_plan.json`
- `examples/semantic_visual_consistency_reports/mvp_first_battle.semantic_visual_consistency_report.json`
- `game_data/demo/*.json`
- `content/worldbooks/long_night_lanterns/*.json`

静态模式会把 manifest 中的 `/assets/frontend_runtime_mock/...`、`/assets/frontend_mock/...`、`/assets/map_visual_reference/...` 和 `/assets/map_components/...` 映射到仓库内的 `game_data/media/...` 路径，包含多帧 atlas 的 `atlas_frames` 与 `atlas_sheets` 子目录。

## 验证命令

```bash
node --check frontend/app.js
python3 -m json.tool examples/frontend_mock/frontend_mock_pack.v0.1.json >/tmp/frontend_mock_pack.check
python3 -m json.tool examples/frontend_mock/frontend_battle_mock_art_kit.v0.1.json >/tmp/frontend_runtime_kit.check
python3 -m json.tool game_data/media/frontend_runtime_mock/frontend_runtime_art_media_manifest.v0.1.json >/tmp/frontend_runtime_media.check
python3 tools/media/validate_media_atlas_manifest.py game_data/media/frontend_runtime_mock/frontend_runtime_art_atlas_manifest.v0.1.json
python3 tools/media/validate_multiframe_atlas_contract.py game_data/media/frontend_runtime_mock/frontend_runtime_art_atlas_manifest.v0.1.json
```
