# 视频帧资产管线 v0.1

本文档固化“生成图片 -> 生成视频 -> 抽取关键帧 -> 批量抠图 -> 组装成游戏资产”的路线。

核心判断：Agnes 生成的白底图片已经足够作为 MVP 母图。它不一定要一次性成为完美战斗 sprite；更合理的做法是把它作为 `animation_seed`，后续生成短视频、截帧，再经过确定性后处理和门禁，变成可被前端加载的动画资产。

## 1. 资产分层

### 1.1 raw generated image

AI 图像 provider 生成的原图。

用途：

- 作为视觉审查对象。
- 作为图生视频种子。
- 作为失败排查证据。

限制：

- 不直接进入 runtime package。
- 不直接作为前端战斗默认 sprite。
- 允许带有较强表现力，例如环光、符文感、粒子感，但不能有怪物、复杂场景、文字、水印。

当前示例：

```text
game_data/media/frontend_mock/generated/
game_data/media/frontend_mock/frontend_raw_media_manifest.v0.1.json
```

### 1.2 animation seed

从 raw generated image 中挑出的图生视频种子。

用途：

- 图生视频。
- 研发完成演出。
- 动画卡。
- 后续抽帧生成 sprite 动画。

限制：

- 可以比 runtime sprite 更“戏剧化”。
- 可以保留环光、能量感、主体装饰。
- 仍然不能有 provider 临时 URL、密钥、原始 prompt 或 trace。

当前示例：

```text
game_data/media/frontend_mock/frontend_animation_seed_manifest.v0.1.json
```

### 1.3 processed cutout

经过后处理的透明 PNG。

用途：

- 前端 UI 图标。
- 战斗中可摆放的塔 / 道具 sprite。
- 后续 atlas / animation frame 的输入。

处理内容：

```text
edge matte removal
  -> near-white island cleanup（仅默认用于 tower_sprite）
  -> small component cleanup
  -> crop and pad
  -> normalize canvas
  -> assign anchor
```

当前示例：

```text
game_data/media/frontend_mock/processed/
game_data/media/frontend_mock/frontend_media_manifest.v0.1.json
```

### 1.4 runtime published media

真正进入 runtime package 的发布态资产。

要求：

- 本地 `/assets/...` 路径。
- sha256。
- width / height。
- anchor。
- atlas frame。
- runtime_readiness 通过。

MVP 前端 mock 当前先直接使用 `frontend_media_manifest.v0.1.json` 中的 processed PNG。后续正式 runtime package 应继续走 atlas 打包和 readiness gate。

当前已补充 `MediaAtlasManifest v0.1` 作为 P1-A 的最小可运行切片：

```text
game_data/media/frontend_mock/frontend_media_atlas_manifest.v0.1.json
game_data/media/frontend_runtime_mock/frontend_runtime_art_atlas_manifest.v0.1.json
```

这两份 manifest 当前已经进入 `spritesheet` 模式：sprite 类角色由已发布 processed PNG 派生出确定性的 4 帧循环 frame sequence，并打包为实体 spritesheet PNG；静态角色仍保持 1 帧。它还不是最终图生视频关键帧成果，但已经让前端、后端 mock API、demo evidence 和 validator 都按多帧 atlas 合同工作。

后续接入图生视频和关键帧时，应在同一合同上扩展：

- `frames` 从当前 4 帧临时循环扩展为 8-16 帧真实关键帧。
- `spritesheet` 继续由真实关键帧重打包为 atlas PNG。
- `playback.fps` 和 `loop` 按动画状态设置。
- 单张 PNG fallback 仍保留，避免视频链路失败影响 MVP。

## 2. 标准路线

```text
CompiledAssetCandidate
  -> VisualIdentitySpec
  -> GenerateRawImage
  -> RawImageReview
  -> SelectAnimationSeed
  -> GenerateVideoFromImage
  -> ExtractVideoKeyframes
  -> SelectKeyframes
  -> LoopContinuityCheck
  -> PostprocessFrameSequence
  -> AlignFrames
  -> PackSpriteSheet
  -> BuildAtlasJson
  -> RuntimeReadinessCheck
  -> RuntimePackage
```

MVP 可以拆成两条并行线：

```text
短期可展示:
  GenerateRawImage
    -> PostprocessSingleImage
    -> FrontendMockMediaManifest
    -> DeterministicFrameSequence
    -> MediaAtlasManifest(spritesheet-compatible frames)

动画资产路线:
  GenerateRawImage
    -> AnimationSeedManifest
    -> GenerateVideoFromImage
    -> ExtractKeyframes
    -> BatchPostprocessFrames
    -> Atlas / AnimationState
```

## 3. 新注册节点

### 3.1 `media.generate_video_from_image_guarded`

调用图生视频 provider。

输入：

- `image_seed_media`
- 可选 `end_frame_media`
- 可选 `candidate`

输出：

- `raw_video_sequence.v0.1`

约束：

- 只允许 `live` mode。
- 必须显式设置 `allow_live_provider_call: true`。
- 如果 provider 要求公网图片 URL，必须先把本地 seed 图发布到临时可访问地址，且该地址不得进入 runtime public artifact。
- provider 返回的视频必须下载到本地 artifact store。
- 面向循环动画时，prompt 必须要求 `seamless loop`、`return to the original pose`、`no camera cut`、`no scene transition`、`stable centered subject`。
- 如果 provider 支持首尾帧控制，应优先把同一张 `image_seed_media` 同时作为首帧和尾帧，或显式传入经过审核的 `end_frame_media`。
- 如果 provider 只支持单图生视频，则 prompt 必须强调最后一帧回到首帧姿态；后续由 `LoopContinuityCheck` 判定是否可循环。

### 3.2 `media.extract_video_keyframes`

从本地视频抽取 PNG 帧。

输入：

- `raw_video_sequence.v0.1`

输出：

- `frame_sequence.v0.1`

建议参数：

```text
fps: 8 或 12
max_frames: 16
prefer_keyframes: true
reject_blurry_frames: true
```

实现可选：

- `ffmpeg`
- 浏览器 Media API
- Python 视频库

MVP 优先使用 `ffmpeg` CLI，因为它稳定、可复现、易调试。

### 3.3 `media.select_keyframes`

从抽出的帧中选出更适合游戏的短序列。

规则：

- 去掉首尾黑帧。
- 去掉过度模糊帧。
- 保留动作相位差明显的帧。
- 保持最多 8-16 帧。
- 同一动画状态内保持主体尺寸接近。

输出仍是 `frame_sequence.v0.1`。

### 3.4 `media.loop_continuity_check`

检查抽帧结果是否适合循环播放。

输入：

- `frame_sequence.v0.1`
- `image_seed_media`

输出：

- `loop_continuity_report.v0.1`

检查项：

- 首帧与末帧主体 bbox 差异不能过大。
- 首帧与末帧 anchor 差异不能过大。
- 首帧与末帧平均颜色 / alpha 覆盖差异不能过大。
- 不能出现明显镜头切换、主体消失、背景突变。
- 对塔、道具、NPC idle 动画，默认要求 `loopable = true`。

失败处理：

```text
轻微失败:
  丢弃末尾突变帧
  或反向追加短序列 ping-pong
  或首尾 crossfade 生成补间帧

严重失败:
  进入 prompt repair
  重生成视频
  或退回单帧 processed PNG + visual recipe 动效
```

MVP 后实现可以先用确定性像素指标；后续再接视觉模型判断“是否肉眼跳帧”。

### 3.5 `media.postprocess_frame_sequence`

批量处理帧序列。

步骤：

```text
edge matte removal
near-white island cleanup
small component cleanup
crop and pad
normalize canvas
frame alignment
assign anchor
```

关键点：

- 对 `tower_sprite` / `unit_sprite` / `monster_sprite`，锚点默认 `bottom_center`。
- 对 `icon` / `ui_card`，锚点默认 `center`。
- 视频帧必须使用同一画布尺寸。
- 不能每帧独立裁切后让主体跳动；需要以全序列 union bbox 或统一 anchor 对齐。

## 4. 抠图策略

当前纯 Python PNG 管线已经支持：

- 边缘连通白底移除。
- 内部近白孤岛清理。
- 小碎片清理。
- 裁切、补边、画布归一。
- 透明像素 RGB 清零。

重要经验：

1. 不能全局删除所有近白像素。玻璃、金属高光、灯焰和纸张会被误删。
2. 先做 edge flood-fill，再做有限的 near-white island cleanup。
3. `near-white island cleanup` 默认只应强用于 `tower_sprite` 这类战斗 sprite。
4. `icon` / `ui_card` 更保守，避免把展示图打穿。
5. 后续接 `rembg` 或 SAM 2 时，也必须保留这个确定性后处理作为门禁前的清理步骤。

## 5. 帧序列 manifest 草案

`frame_sequence.v0.1` 建议结构：

```json
{
  "metadata_version": "frame_sequence.v0.1",
  "media_layer": "raw_media",
  "source_video_id": "video_asset_xxx",
  "asset_id": "asset_xxx",
  "animation_state": "idle_or_activation",
  "frames": [
    {
      "stable_internal_id": "asset_xxx_activation_frame_000",
      "frame_index": 0,
      "timestamp_ms": 0,
      "media_role": "tower_sprite",
      "local_path": "runs/.../frame_000.png",
      "width": 1024,
      "height": 1024,
      "sha256": "..."
    }
  ],
  "summary": {
    "frame_count": 8,
    "fps": 8,
    "duration_ms": 1000
  }
}
```

处理后可提升为：

```text
processed frame_sequence
  -> atlas.png
  -> atlas.json
  -> animation_states
  -> published_media_manifest
```

## 6. 前端使用方式

前端不关心 provider，也不读取 raw prompt。

前端需要的是：

```text
texture_key
atlas image
atlas json
animation state name
frame list
frame rate
anchor
effects / visual_recipes
```

示例运行时结构：

```json
{
  "texture_key": "asset_wick_barrier_pylon_activation",
  "image": "/assets/generated/asset_wick_barrier_pylon_activation.png",
  "atlas": "/assets/generated/asset_wick_barrier_pylon_activation.json",
  "animation_states": {
    "activation": {
      "frames": ["frame_000", "frame_001", "frame_002", "frame_003"],
      "fps": 8,
      "loop": false
    }
  },
  "anchor": { "preset": "bottom_center", "x": 0.5, "y": 1.0 }
}
```

## 7. MVP 决策

MVP 演示阶段采用以下策略：

1. 前端默认使用 processed 单帧 PNG，保证 UI 和战斗可展示。
2. raw generated image 保留为 animation seed。
3. 视频生成和抽帧作为下一条可演示增强链路，不阻塞当前 MVP。
4. 若视频链路失败，回退到单帧 PNG + 前端 visual recipe。
5. 图生视频产物不直接进战斗，必须先抽帧、抠图、对齐、打包和 readiness 检查。

这条路线允许我们把 Agnes 的表现力转化为优势：原图可以带有氛围和能量感，用来生成动画；运行时仍通过 processed / atlas / effect recipe 保持可控。
