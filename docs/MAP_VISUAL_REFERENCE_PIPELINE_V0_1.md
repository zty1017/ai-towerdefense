# 地图视觉参考流水线 v0.1

## 定位

地图也是可编译对象，但第一版不让图片反过来决定玩法逻辑。

当前流水线以 `game_data/demo/initial_map.json` 与 `game_data/demo/first_battle_config.json` 为权威输入，生成四类 PNG：

- `strategic_control_sketch`：战略大地图控制草图，表达主城、节点、补给线、黑暗区域和威胁边界。
- `battle_control_sketch`：战斗地图控制草图，表达路径、可部署槽位、核心、防守目标和出生方向。
- `battle_reference_board`：编译参考图，用于给图像模型或审查流程说明路线和塔位关系。它不应直接作为玩家侧最终底图。
- `battle_runtime_background`：玩家侧战斗画布的发布底图。它必须像完整塔防游戏地图，而不是控制图、棋盘、UI 面板或调试图；路径、塔基、核心和防守目标应自然嵌入地形中。

这些 PNG 不是最终规则数据。前端仍然以战斗配置中的网格、路径、目标、敌人、塔位规则作为运行时真相。

当前已补充 `MapRuntimePackage v0.1`，作为战斗地图运行时真相的更稳定入口。它从 battle config 派生：

- `grid`
- `path_routes`
- `build_slots`
- `objectives`
- `spawn_points`
- `visual_layers`

因此后续前端应优先读取 map runtime package，而不是直接消费 battle config。battle config 仍是开发期和兼容层输入。

## 运行

```bash
python3 tools/media/build_map_visual_reference_pack.py
python3 tools/asset_graph/build_map_runtime_package.py --output examples/map_runtime_packages/mvp_first_battle.map_runtime_package.json
python3 tools/asset_graph/validate_map_runtime_package.py examples/map_runtime_packages/mvp_first_battle.map_runtime_package.json
```

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

前端通过后端接口读取 `map_runtime_package`，并从其中的 `visual_layers` 优先选择 `battle_runtime_background` 作为战斗画布底层。若该发布底图缺失，才允许临时回退到 `battle_reference_board`。玩家侧不显示完整逻辑网格，只在其上实时绘制：

- 路径高光
- 核心和防守目标
- 敌人与防御塔
- 拖拽部署预览
- 特效与生命值

因此，即使后续替换为真实图像模型生成的地图背景，也不需要改战斗逻辑。

关键边界：

- 图片永远不是玩法真相。怪物路线、塔位、目标、出生点以 MapRuntimePackage 的结构化数据为准。
- 控制图不进入玩家默认体验。
- 发布底图可以由 AI 生成，但必须进入 manifest，标记为 `published_visual_layer`，并经过本地路径、hash、尺寸和 schema 校验。
- 若底图与结构化路线不完全对齐，MVP 可以用轻量叠层修正；正式版需要增加对齐审查或回写步骤。

## 后续升级方向

下一阶段可以把 `battle_control_sketch`、世界书视觉风格、节点剧情状态、材料/建筑语义一起交给图像模型，生成更完整的地图底图。生成后仍应执行对齐检查：

- 路径轮廓是否与逻辑路径一致
- 核心和防守目标是否落在预期位置
- 可部署区域是否没有被视觉元素误导
- 黑暗区域和敌潮入口是否保留清晰辨识
- 玩家侧是否避免出现突兀的完整平行四边形棋盘
