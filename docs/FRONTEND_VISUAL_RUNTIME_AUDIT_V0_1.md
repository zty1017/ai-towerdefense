# 前端视觉运行态审计 v0.1

Last updated: 2026-07-02

本文记录 P0-L 前端视觉运行态验收结果。目标是确认默认玩家战斗视图不会把控制图、参考图、棋盘图或孤立几何块作为正式地图画面。

## 1. 审计结论

当前结论：

- 默认玩家视图的地图底图选择顺序已固定为 `painted_visual_layer -> battle_runtime_background -> 程序化大画面背景`。
- `battle_control_sketch` 与 `battle_reference_board` 只允许在 debug / evidence 模式作为辅助 fallback，不进入默认玩家体验。
- 首战 `MapRuntimePackage` 中 `painted_visual_layer` 和 `battle_runtime_background` 均标记为 `published_visual_layer`；前者是玩家默认美术底图，后者是逻辑对齐 fallback。
- 战斗 UI 已压缩为低遮挡 HUD：画布全屏铺底，顶部 HUD 更薄，左右侧栏更窄，底部工具条降低高度，避免把主战场变成后台面板。
- 前端静态入口、前端脚本、首战 `painted_visual_layer` PNG、首战 `MapRuntimePackage` 均可通过本地 HTTP 服务读取。
- 已补充无浏览器环境下的静态视觉合约校验脚本，用于防止控制图泄漏、玩家底图优先级倒置、战斗画布塌缩和侧栏过宽。
- 本轮未生成真实浏览器截图，因为当前执行环境没有 Chromium / Chrome，也没有 Playwright。

这意味着：代码和资源层面的默认路径已经防止低质量控制图污染玩家视图；但真正的像素级截图验收仍需要在安装浏览器的环境中补做。

## 2. 已验证命令

### 2.1 前端语法与 diff 检查

```bash
node --check frontend/app.js
python3 tools/frontend/validate_battle_visual_contract.py
git diff --check
```

结果：通过。

### 2.2 浏览器能力探测

```bash
python3 -c "import shutil, importlib.util; print('chromium', bool(shutil.which('chromium') or shutil.which('chromium-browser') or shutil.which('google-chrome') or shutil.which('google-chrome-stable'))); print('playwright', bool(importlib.util.find_spec('playwright')))"
```

结果：

```text
chromium False
playwright False
```

### 2.3 静态资源 HTTP 读取

运行时需要清除代理变量，否则 localhost 请求会被代理转发。

```bash
python3 -m http.server 8765
```

然后读取：

```text
http://127.0.0.1:8765/frontend/index.html
http://127.0.0.1:8765/frontend/app.js
http://127.0.0.1:8765/game_data/media/map_visual_reference/mvp_battle_painted_candidate_agnes_02.png
http://127.0.0.1:8765/examples/map_runtime_packages/mvp_first_battle.map_runtime_package.json
```

结果：

```text
200 http://127.0.0.1:8765/frontend/index.html
200 http://127.0.0.1:8765/frontend/app.js
200 http://127.0.0.1:8765/game_data/media/map_visual_reference/mvp_battle_painted_candidate_agnes_02.png
200 http://127.0.0.1:8765/examples/map_runtime_packages/mvp_first_battle.map_runtime_package.json
```

### 2.4 首战视觉层权威性

```bash
python3 -c 'import json; p=json.load(open("examples/map_runtime_packages/mvp_first_battle.map_runtime_package.json", encoding="utf-8")); print([l["role"]+":"+l.get("authority","") for l in p["visual_layers"]])'
```

结果：

```text
[
  "strategic_control_sketch:reference_only",
  "battle_control_sketch:reference_only",
  "battle_reference_board:reference_only",
  "painted_visual_layer:published_visual_layer",
  "battle_runtime_background:published_visual_layer"
]
```

## 3. 代码路径证据

关键函数位于 `frontend/app.js`：

- `playerBattleMapVisualUrl()`：默认只返回 `painted_visual_layer` 或 `battle_runtime_background`。
- `debugBattleMapVisualUrls()`：只有 `?mapVisualDebug=1`、`?debugMapVisuals=1` 或 `?evidence=1` 时才返回 `battle_reference_board` / `battle_control_sketch`。
- `drawBackdrop()`：优先绘制玩家发布底图；发布底图缺失时使用程序化背景，只有 debug/evidence 模式才允许调试图 fallback。
- `tools/frontend/validate_battle_visual_contract.py`：检查玩家地图层优先级、debug 图隔离、PNG 尺寸、runtime package 视觉层、全屏 battle canvas 和 HUD 宽度约束。

## 4. 未完成项

仍需在具备浏览器的环境中补做：

```bash
npx playwright screenshot http://127.0.0.1:8765/frontend/index.html /tmp/ai_td_frontend_battle.png
```

或使用本机 Chrome / Chromium 手动录屏确认：

- 战斗地图占据页面中部视觉重心。
- 默认玩家视图不出现 `battle_control_sketch` / `battle_reference_board`。
- 路径、塔位、目标、出生点来自结构化叠层。
- 拖拽部署视觉没有破坏地图主体。

## 5. 当前风险

当前风险不是“控制图会默认进入玩家视图”，这条已被代码防线挡住。当前风险是：

- 由于缺少浏览器截图，本轮无法证明最终像素构图足够好看。
- 后续如果替换 `painted_visual_layer` 或 `battle_runtime_background`，仍需要重新跑本审计。
- `painted_visual_layer` 当前已进入 `MapRuntimePackage v0.1`，但仍需要在有浏览器环境时补做截图或录屏验收。
