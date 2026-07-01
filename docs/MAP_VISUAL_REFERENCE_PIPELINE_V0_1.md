# 地图视觉参考流水线 v0.1

## 定位

地图也是可编译对象，但第一版不让图片反过来决定玩法逻辑。

当前流水线以 `game_data/demo/initial_map.json` 与 `game_data/demo/first_battle_config.json` 为权威输入，生成三类 PNG：

- `strategic_control_sketch`：战略大地图控制草图，表达主城、节点、补给线、黑暗区域和威胁边界。
- `battle_control_sketch`：战斗地图控制草图，表达路径、可部署槽位、核心、防守目标和出生方向。
- `battle_reference_board`：玩家侧可预览的整屏战斗场景参考图。它必须像地图场景，而不是可见的逻辑棋盘；路径、核心和落点应嵌入地形中，也可作为后续图像模型的参考输入。

这些 PNG 不是最终规则数据。前端仍然以战斗配置中的网格、路径、目标、敌人、塔位规则作为运行时真相。

## 运行

```bash
python3 tools/media/build_map_visual_reference_pack.py
```

默认输出到：

```text
game_data/media/map_visual_reference/
```

并生成：

```text
game_data/media/map_visual_reference/map_visual_reference_manifest.v0.1.json
```

## 前端使用方式

前端读取 `map_visual_reference_manifest.v0.1.json`，将 `battle_reference_board` 作为战斗画布的视觉参考底层。玩家侧不显示完整逻辑网格，只在其上实时绘制：

- 路径高光
- 核心和防守目标
- 敌人与防御塔
- 拖拽部署预览
- 特效与生命值

因此，即使后续替换为真实图像模型生成的地图背景，也不需要改战斗逻辑。

## 后续升级方向

下一阶段可以把 `battle_control_sketch`、世界书视觉风格、节点剧情状态、材料/建筑语义一起交给图像模型，生成更完整的地图底图。生成后仍应执行对齐检查：

- 路径轮廓是否与逻辑路径一致
- 核心和防守目标是否落在预期位置
- 可部署区域是否没有被视觉元素误导
- 黑暗区域和敌潮入口是否保留清晰辨识
- 玩家侧是否避免出现突兀的完整平行四边形棋盘
