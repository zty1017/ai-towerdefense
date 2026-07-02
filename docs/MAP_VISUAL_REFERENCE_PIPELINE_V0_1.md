# 地图视觉参考流水线 v0.1

## 定位

地图也是可编译对象，但第一版不让图片反过来决定玩法逻辑。

当前流水线以 `game_data/demo/initial_map.json` 与 `game_data/demo/first_battle_config.json` 为权威输入，生成或登记五类 PNG：

- `strategic_control_sketch`：战略大地图控制草图，表达主城、节点、补给线、黑暗区域和威胁边界。
- `battle_control_sketch`：战斗地图控制草图，表达路径、可部署槽位、核心、防守目标和出生方向。
- `battle_reference_board`：编译参考图，用于给图像模型或审查流程说明路线和塔位关系。它不应直接作为玩家侧最终底图。
- `painted_visual_layer`：玩家侧优先使用的发布级美术底图。MVP 当前使用 Agnes 真实图像生成候选，经人工审查确认无 UI、文字、敌人、已部署塔和角色后登记为发布层。
- `battle_runtime_background`：逻辑对齐的确定性发布 fallback。它使用与前端一致的伪 3D 投影生成，保证路径、塔位、目标和出生点可对齐，但视觉质量不应被宣传为最终美术水准。

这些 PNG 不是最终规则数据。前端仍然以战斗配置和 `MapRuntimePackage` 中的网格、路径、目标、敌人、塔位规则作为运行时真相。

当前已补充 `MapRuntimePackage v0.1`，作为战斗地图运行时真相的更稳定入口。它从 battle config 派生：

- `grid`
- `path_routes`
- `build_slots`
- `objectives`
- `spawn_points`
- `visual_layers`

因此后续前端应优先读取 map runtime package，而不是直接消费 battle config。battle config 仍是开发期和兼容层输入。

## MapCompilePackage v0.2

`MapCompilePackage v0.2` 是“地图作为可编译对象”的编译侧证据包。它不替代 `MapRuntimePackage`，也不应该被前端当成战斗运行时事实源。

二者边界如下：

| 包 | 作用 | 是否给前端运行时直接消费 |
|---|---|---|
| `MapCompilePackage v0.2` | 记录地图编译过程：逻辑层、控制层、玩家可见渲染层、坐标回配、质量门。 | 否，主要用于编译审查、证据导出和后续地图生成管线。 |
| `MapRuntimePackage v0.1` | 提供战斗运行时事实：路径、塔位、目标、出生点、视觉层引用。 | 是，前端优先消费。 |

`MapCompilePackage` 当前包含：

- `logical_map_layer`：从 `MapRuntimePackage` 复制的运行时真相，包括路径、塔位、目标、出生点和网格。
- `control_layer`：控制图、参考图、composition sketch 等，只能作为图像模型和审查流程的参考。
- `painted_visual_layer`：玩家可见发布底图，MVP 默认优先使用。它仍不是玩法真相，战斗路线和塔位必须由 `MapRuntimePackage` 叠层驱动。
- `alignment_layer`：逻辑坐标到视觉平面的回配检查点、误差阈值和叠层修正策略。
- `quality_gates`：视觉质量门，明确禁止 UI、文字、敌人、已部署防御塔、棋盘感和突兀边框进入玩家底图。
- `export_refs`：指回最终前端应加载的 `MapRuntimePackage`。

第一版示例：

```bash
python3 tools/asset_graph/build_map_compile_package.py
python3 tools/asset_graph/validate_map_compile_package.py examples/map_compile_packages/mvp_first_battle.map_compile_package.json
python3 -m json.tool examples/map_compile_packages/mvp_first_battle.map_compile_package.json
```

当前质量门中，`no_ui_text_enemy_tower_in_painted_map` 仍为 `warning`，原因是 MVP 还没有接入真正的视觉模型自动验图。`alignment_requires_runtime_overlay` 在存在逻辑对齐 fallback 或人工审查发布图时可通过，但正式版仍需要自动化像素回配或视觉模型审查。

## 运行

```bash
python3 tools/media/build_map_visual_reference_pack.py
python3 tools/asset_graph/build_map_runtime_package.py --output examples/map_runtime_packages/mvp_first_battle.map_runtime_package.json
python3 tools/asset_graph/validate_map_runtime_package.py examples/map_runtime_packages/mvp_first_battle.map_runtime_package.json
```

如果需要重新生成玩家侧美术候选，必须显式允许真实图像 provider 调用：

```bash
python3 tools/media/generate_map_painted_background.py \
  --live \
  --dotenv /home/zty/projects/ai-compiled-towerdefense/.env \
  --image-profile agnes_image_flash \
  --size 1280x720 \
  --output game_data/media/map_visual_reference/mvp_battle_painted_candidate_agnes_02.png
```

该脚本只下载候选图和 sidecar，不自动发布。候选必须经过审查后才能被 `build_map_visual_reference_pack.py` 登记为 `painted_visual_layer`。

默认输出到：

```text
game_data/media/map_visual_reference/
```

并生成：

```text
game_data/media/map_visual_reference/map_visual_reference_manifest.v0.1.json
examples/map_runtime_packages/mvp_first_battle.map_runtime_package.json
```

## 前端使用方式

前端通过后端接口读取 `map_runtime_package`，并从其中的 `visual_layers` 选择玩家侧战斗画布底层。默认选择顺序是：

```text
painted_visual_layer
  -> battle_runtime_background
  -> 程序化大画面背景
```

默认玩家视图不得回退到 `battle_reference_board` 或 `battle_control_sketch`。若发布底图缺失，前端必须保持中部全屏 / 大画面表达，用程序化背景承托结构化玩法叠层，而不是把控制图、参考图、棋盘图或孤立几何块暴露给玩家。

控制图和参考图只允许在 debug / evidence 模式中显示，例如通过 `?mapVisualDebug=1` 或 `?evidence=1` 临时开启。玩家侧不显示完整逻辑网格，只在底图上实时绘制：

- 路径高光
- 核心和防守目标
- 敌人与防御塔
- 拖拽部署预览
- 特效与生命值

因此，即使后续替换为真实图像模型生成的地图背景，也不需要改战斗逻辑。

关键边界：

- 图片永远不是玩法真相。怪物路线、塔位、目标、出生点以 MapRuntimePackage 的结构化数据为准。
- 控制图和参考图不进入玩家默认体验，也不作为发布底图缺失时的默认 fallback。
- 发布底图可以由 AI 生成，但必须进入 manifest，标记为 `published_visual_layer`，并经过本地路径、hash、尺寸、schema 校验和人工或自动视觉审查。
- 若底图与结构化路线不完全对齐，MVP 可以用轻量叠层修正；正式版需要增加对齐审查或回写步骤。
- `MapCompilePackage` 可以引用控制图和发布底图，但最终导出的玩家战斗数据仍应是 `MapRuntimePackage`。

## 后续升级方向

下一阶段可以把 `battle_control_sketch`、世界书视觉风格、节点剧情状态、材料/建筑语义一起交给图像模型，生成更完整的地图底图。生成后仍应执行对齐检查：

- 路径轮廓是否与逻辑路径一致
- 核心和防守目标是否落在预期位置
- 可部署区域是否没有被视觉元素误导
- 黑暗区域和敌潮入口是否保留清晰辨识
- 玩家侧是否避免出现突兀的完整平行四边形棋盘
