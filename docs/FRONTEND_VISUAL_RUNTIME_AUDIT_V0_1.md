# 前端视觉运行态审计 v0.1

Last updated: 2026-07-06

本文记录 P0-M 前端战斗地图视觉底座改造结果。目标是让默认玩家战斗视图不依赖失败整图候选，而是由 `MapRuntimePackage` 的路径、塔位、目标和出生点驱动 canvas 程序化战场底座。

## 1. 审计结论

当前结论：

- 默认战斗画面不再预加载或绘制整张玩家地图图像；`drawBackdrop()` 固定从 `drawProceduralTerrain()` 开始绘制，再叠加受 debug 参数保护的辅助 overlay 与边缘雾暗。
- `MapRuntimePackage` 仍是运行时事实源：`grid` 负责投影，`path_routes` 负责道路，`build_slots` 负责部署基座，`objectives` 负责目标地标，`spawn_points` 负责出生点氛围。
- 程序化底座使用 `package_id` / `node_id` 派生稳定 seed，同一节点会得到稳定地形纹理、地表斑块、环境碎片和边缘雾。
- 路径已改为平滑土石路、路肩、碎石边缘、车辙和少量木板细节，不再使用发光虚线或控制线；塔位已改为石质部署基座；出生点已改为雾潮裂口，不再画箭头。
- v0.2 增加暗潮洼地和世界内废墟 / 补给 / 灯具 / 信号残骸地标，用于打破单调地表，让默认战斗画面更接近完整塔防关卡而不是调试底座。
- v0.3 增加节点调色、地貌深度带、道路边缘小物和部署基座接驳痕迹；塔位仍来自 `build_slots`，道路仍来自 `path_routes`，这些表现层细节不新增运行时逻辑事实。
- v0.4 增加 HUD safe-area contain fit、可玩地块边界、可部署台地、路线方向 cue 和目标防御区；移动端不再以 cover 方式裁掉入口到核心的关卡链路，多路线地图的敌人也会按 `spawn_points.route_id` 绑定路线。
- 旧 `drawGrid()` / `drawDiamond()` 棋盘绘制入口已移除，静态合约会阻止它们重新出现。
- 静态视觉合约现在可以输出 `battle_visual_contract_report.v0.1` 结构化报告，并已纳入 MVP demo readiness 的 `battle_visual_contract` 必需 gate。
- `battle_control_sketch` 与 `battle_reference_board` 仍只允许在 debug / evidence 参数下作为低透明辅助 overlay，不进入默认玩家体验。
- 侧栏和提示层进一步降低遮挡：左右侧栏宽度收紧到 190px / 198px，背景透明度降低，canvas 继续全屏铺满 battle stage。

## 2. 已验证命令

```bash
node --check frontend/app.js
python3 tools/frontend/validate_battle_visual_contract.py
python3 tools/frontend/validate_battle_visual_contract.py --report-output examples/review_packs/battle_visual_contract_report.v0.1.json --generated-at 2026-07-06T00:00:00+00:00
python3 tools/frontend/capture_battle_visual_smoke.py --allow-missing-browser --output-dir /tmp/p0m_browser_visual_smoke
python3 tools/frontend/capture_battle_visual_smoke.py --output-dir /tmp/p0m_browser_visual_smoke
python3 tools/frontend/capture_battle_visual_smoke.py --output-dir /tmp/frontend_procedural_map_polish_smoke
python3 tools/frontend/capture_battle_visual_smoke.py --allow-missing-browser --output-dir /tmp/map_procedural_backdrop_v3_after2
python3 tools/frontend/capture_battle_visual_smoke.py --output-dir /tmp/battlefield_depth_v4_scaled_smoke
```

结果：通过。

静态视觉合约输出：

```text
OK battle visual contract
- map runtime packages: 3
- default battle backdrop: MapRuntimePackage-driven procedural terrain
```

本机浏览器烟测输出：

```text
CAPTURED battle visual smoke: /tmp/p0m_browser_visual_smoke/battle_visual_smoke_report.v0.1.json
- desktop: /tmp/p0m_browser_visual_smoke/battle_visual_smoke_desktop.png
- mobile: /tmp/p0m_browser_visual_smoke/battle_visual_smoke_mobile.png
```

截图由临时下载到 `/tmp/pw-browsers` 的 Playwright Chromium 生成，不写入项目依赖；脚本会自动发现该临时浏览器。桌面视口为 1440x900，移动视口为 390x844。

## 3. 静态合约覆盖

`tools/frontend/validate_battle_visual_contract.py` 当前检查：

- 默认 preload 不得请求整张玩家地图图像。
- `drawBackdrop()` 必须调用程序化地形，并且不能调用 `playerBattleMapVisualUrl()`。
- 路径绘制必须包含世界内路肩、纹理、车辙或木板细节，且不得使用 dashed control line。
- 路径绘制必须包含道路边缘世界小物，部署基座必须通过接驳痕迹融入运行时道路。
- 程序化地形必须保留节点调色、地貌深度带、暗潮洼地和世界内地标层。
- 战斗投影必须基于 runtime bounds 与 HUD safe area 做适配，不能只用 viewport cover 策略裁掉关卡。
- 默认玩家画面必须保留可玩地块边界、路线方向 cue、可部署台地和目标防御区。
- 敌人生成和移动必须绑定 runtime route / spawn id，多路线地图不能只跑第一条路径。
- 部署点必须走 world-space deployment base。
- 出生点必须走 ambient entry effect，不得回退箭头。
- `drawGrid()` / `drawDiamond()` 不得保留。
- 失败视觉层不能以 `published_visual_layer` 权限进入 manifest 或 runtime package。
- 每个 `MapRuntimePackage` 必须具备 grid、path_routes、build_slots、core objective 和 spawn_points。
- 每个 `MapRuntimePackage v0.2 preview` 必须携带 resource_nodes、hazard_zones、defense_anchors、blocked_areas，且默认前端不得请求 review-only v0.2 endpoint。

结构化报告输出：

```bash
python3 tools/frontend/validate_battle_visual_contract.py --report-output examples/review_packs/battle_visual_contract_report.v0.1.json --generated-at 2026-07-06T00:00:00+00:00
```

当前报告状态为 `passed`，app / CSS / 地图层错误数均为 0。该报告只记录静态合同与本地文件覆盖，不调用 provider、不读取 `.env`、不写世界状态、不修改 runtime package；真实截图和人工观感仍由浏览器 smoke 与录屏验收补充。

## 4. 浏览器验收

已新增可复跑脚本：

```bash
python3 tools/frontend/capture_battle_visual_smoke.py --output-dir /tmp/p0m_browser_visual_smoke
```

脚本会启动本地静态服务，打开 `frontend/index.html?static=1&battleVisualSmoke=1`，并采集桌面与移动视口截图。`battleVisualSmoke=1` 只用于验收深链，默认玩家流程不使用。

本轮截图确认：

- 默认战斗首屏是全屏战场，不再是小块平行四边形调试地图。
- 程序化地形、平滑土路、路肩、车辙、塔位石基、目标地标、出生点雾潮、暗潮洼地和世界内地标在桌面与移动视口下都可见。
- v0.3 的路边小物和接驳痕迹只增强场景可信度，不改变点击/拖拽命中、路径寻路或放置合法性。
- v0.4 的 safe-area fit 让移动端可以看到完整入口、路线、核心和底部工具条之间的关系；桌面端则把关卡稳定放在左右面板之间。
- 路线方向 cue 和部署台地提高了一眼读法，但不改变敌人寻路、部署合法性或 MapRuntimePackage。
- 移动端顶部状态已允许换行，底部工具栏已取消桌面居中 transform，三张工具卡完整可见。
- debug / evidence 参数之外不会显示控制图、参考图、失败 text-fallback 地图、棋盘或箭头。

残余限制：本轮是首战烟测截图，不替代后续对多节点地图、真实拖拽交互和完整录屏的人工验收。
