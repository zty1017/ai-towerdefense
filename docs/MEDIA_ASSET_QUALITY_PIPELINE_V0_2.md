# 媒体资产质量管线 v0.2

本文档记录“AI 生成图片如何尽量无人工干预地变成游戏可用资产”的下一阶段方案。

核心判断：图片模型产出的图不能直接等同于游戏资产。必须经过生成约束、后处理、确定性门禁、视觉审查和修复循环，最后才进入 runtime package。

补充决策：Agnes 等图像 provider 稳定产出的白底图已经足够作为 MVP 母图。后续应固化“生成图片 -> 图生视频 -> 抽取关键帧 -> 批量抠图 -> atlas / animation state”的路线，而不是要求图片模型一次性产出完美动画资产。详见：

```text
docs/VIDEO_FRAME_ASSET_PIPELINE_V0_1.md
```

## 1. 外部方案调研结论

可参考的外部方向：

- `rembg`：成熟的 Python / CLI / HTTP / Docker 背景移除工具，支持单图、批处理、服务化、alpha matting，也支持不同模型。适合后续作为本地后处理增强节点。
  参考：https://github.com/danielgatis/rembg
- `SAM 2`：Meta 的图像 / 视频分割模型，适合复杂背景、角色/怪物/道具主体分割，以及后续多帧动画一致性分割。
  参考：https://github.com/facebookresearch/sam2
- `ComfyUI`：节点化图像生成/处理工作流。我们不一定需要 UI，但它证明“可复用图像 DAG + 可替换节点 + 可保存 workflow”是稳定方向。
  参考：https://github.com/Comfy-Org/ComfyUI
- Phaser texture / atlas：前端运行时更关心 texture、frame、atlas、key，而不是 provider 原图。媒体管线最终应该产出 `/assets` 引用、atlas JSON、anchor 和 frame。
  参考：https://docs.phaser.io/phaser/concepts/textures

对本项目的启发：

1. 不追求“一次生成最终图”。
2. 把图片生成拆成一组 AssetGraph 节点。
3. 把主体图和特效分离：主体图用于 sprite / icon，特效走 visual recipe 或独立透明层。
4. 用确定性门禁判断“能否加载和摆放”，用视觉模型判断“像不像、有没有文字水印、是否符合世界观”。
5. 失败后进入 repair loop，而不是要求人工逐张修。

## 2. 媒体角色分层

### 2.1 Cutout / Sprite 类

包括：

```text
icon
tower_sprite
unit_sprite
npc_sprite
monster_sprite
material_sprite
cutout_source
```

生成要求：

- 单一主体。
- 纯白 / 纯黑 / 纯灰 matte 背景，优先纯白。
- 无场景背景。
- 无文字、logo、水印。
- 无投影和地面阴影。
- 不把攻击特效、粒子、光环烘焙进主体图。
- 四周留空，便于裁切和 anchor。

目标产物：

```text
transparent PNG
square / normalized canvas
anchor
atlas frame
texture_key
published_media_manifest
runtime_readiness_report
```

### 2.2 Illustration / Preview 类

包括：

```text
ui_card
effect_preview
battle_preview
opening_card
event_card
```

这类图可以有背景和构图，不要求透明底，但必须：

- 无文字、logo、水印。
- 主体和同一资产保持一致。
- 世界观一致。
- 不混入现代士兵、枪械、现实 UI 等不该出现的元素。
- 只作为卡图 / 预览 / 叙事图，不直接当碰撞或部署 sprite。

### 2.3 Visual Recipe 类

攻击、命中、范围、连锁、光环、震动、浮字等不应优先烘焙进主体图。

MVP 已确认的类型：

```text
ring_pulse
beam
chain_arc
sprite_flash
particle_burst
aura_field
screen_shake
floating_text
```

主体 sprite 与 visual recipe 分离后，AI 生成图的一致性压力会显著降低。

## 3. 推荐管线

```text
CompiledAssetCandidate
  -> VisualIdentitySpec
  -> MediaPromptPlan
  -> GenerateRawMedia
  -> DeterministicQualityCheck
  -> VisionReview
  -> PromptRepairPlan
  -> RegenerateFailedRoles
  -> MergeRepairedMedia
  -> BackgroundRemoval
  -> CropAndPad
  -> NormalizeCanvas
  -> AssignAnchor
  -> PackSpriteSheet
  -> BuildAtlasManifest
  -> RuntimeReadinessCheck
  -> PromoteOrFallback
```

其中：

- `VisionReview` 负责语义、一致性、文字/水印等模型审查。
- `RuntimeReadinessCheck` 负责可加载、可摆放、透明底、anchor、atlas、hash 等硬条件。
- 只有两类报告都通过，媒体才可以被 promotion 到运行时默认素材。

## 4. 新增确定性门禁

新增节点：

```text
media.check_runtime_readiness
```

新增报告：

```text
shared/schemas/media_runtime_readiness_report.v0.1.schema.json
```

它检查：

- `published_media` 是否只使用 `/assets/generated/...`。
- 本地 published 文件是否存在。
- PNG 是否能读取。
- `sha256` 是否匹配。
- sprite 是否有透明背景。
- 主体 bbox 是否过小或过满。
- 主体是否贴到画布边缘。
- `tower_sprite` 是否为 `bottom_center` anchor。
- `texture_key` / `atlas_frame` 是否存在。
- atlas image / descriptor 是否存在。

这个节点不调用 LLM，不评价审美，只回答“前端能不能直接加载并放到战场上”。

当前前端 mock 与战斗 runtime art 还补充了一层 sprite cutout 几何审查：

```text
media.audit_sprite_cutout_quality
```

对应产物：

```text
examples/review_packs/frontend_sprite_cutout_quality_report.v0.1.json
examples/review_packs/frontend_runtime_sprite_cutout_quality_report.v0.1.json
```

它直接读取现有 `items[]` 风格的 media manifest，检查 sprite 透明底是否存在明显内部透明洞、主体碎裂、漂浮组件、边缘接触和 anchor/canvas 风险。该报告的 `needs_review` 不阻断 MVP；它用于排序后续重抠图、重生成、视频关键帧替换和人工复核任务。

质量报告之后会生成修复计划：

```text
media.build_sprite_cutout_repair_plan
```

对应产物：

```text
examples/review_packs/frontend_sprite_cutout_repair_plan.v0.1.json
examples/review_packs/frontend_runtime_sprite_cutout_repair_plan.v0.1.json
```

修复计划把 `needs_review` 项转成优先级、建议动作、重生成提示词约束和验收命令。它不直接修改素材，只作为后续后台重生 / 重抠图任务的输入。

修复计划之后可以生成审查候选：

```text
media.build_sprite_repair_candidates
```

对应产物：

```text
examples/review_packs/frontend_sprite_repair_candidates.v0.1.json
examples/review_packs/frontend_runtime_sprite_repair_candidates.v0.1.json
examples/review_packs/frontend_sprite_repair_candidate_quality_report.v0.1.json
examples/review_packs/frontend_runtime_sprite_repair_candidate_quality_report.v0.1.json
```

候选包只写入 `review_candidate_media`，不会替换 `processed` manifest、atlas 或前端默认资源。候选通过几何质量门后仍需人工/视觉审查，尤其是 `fill_interior_holes` 可能把本该中空的结构填实，只能作为“确定性修复是否可行”的证据。

## 5. 后续增强顺序

### 5.1 立即可做

- 已将 `icon` / `tower_sprite` prompt 收紧为 cutout 生成规则。
- 已新增 runtime readiness gate。
- live media workflow 发布后接入 readiness gate。

### 5.2 MVP 后第一梯队

- 接入 Pillow：
  - PNG/JPEG/WebP 统一读取。
  - 缩放重采样。
  - alpha 边缘 feather / defringe。
  - 调色和对比度归一。
- 接入 `rembg`：
  - 作为 `media.remove_background_rembg` 节点。
  - 优先处理复杂但仍可分割的主体图。
  - 批处理时复用 session。
- 增加 `sprite_source` / `cutout_source` 专用角色：
  - 与 `ui_card`、`battle_preview` 明确分离。
  - 生成图时默认纯色背景。
- 固化视频帧路线：
  - `animation_seed` 使用 raw generated image。
  - 图生视频产物必须下载为本地 raw video。
  - 抽帧后进入批量抠图、帧间对齐、atlas 打包。
  - 视频帧失败时回退到单帧 processed PNG + visual recipe。

### 5.3 第二梯队

- 接入 SAM 2 / 分割模型：
  - 复杂背景抠图。
  - 多帧主体一致分割。
  - 人物 / NPC / 怪物动画帧处理。
- 参考图链式生成：
  - 先生成 identity frame。
  - 后续关键帧使用 identity frame + prompt 引导。
  - 每一帧都经过 runtime readiness 和 vision consistency。
- 媒体候选排序：
  - 多 provider / 多 seed 生成多个候选。
  - 自动按 vision score + runtime readiness + file metrics 排序。
  - 默认选择最高分，失败角色进入 repair loop。

## 6. 自动 promotion 策略

建议状态机：

```text
raw_media
  -> processed_media
  -> published_media
  -> runtime_ready
  -> promoted
```

promotion 条件：

```text
runtime_readiness.status == passed
vision_review.status in ["passed", "needs_review"] 且 vision_score >= 80
media_consistency.status != failed
没有文字 / 水印 / provider 临时 URL / raw trace 泄漏
```

失败策略：

- `runtime_readiness.failed`：优先重跑后处理或改 prompt 生成 cutout 图。
- `vision_review.failed`：优先走 prompt repair + 重生成失败 role。
- `provider_error`：切 fallback provider。
- 多次失败：使用稳定 fallback sprite，不阻塞 gameplay package。

## 7. 玩家一次请求的硬性交付规则

玩家发起一次构想后，系统必须尽量交付一个可进入战斗的资产。这里的“一次性”不是指一次图片模型调用，而是指一次玩家请求内部可以运行多步编译、审查、修复和回退。

资产交付拆成两层：

```text
gameplay_core
  -> 数值、效果、部署规则、visual_recipe
  -> 必须可校验、可模拟、可 fallback

media_skin
  -> icon / sprite / card / atlas
  -> 通过 runtime_readiness 后 promotion
  -> 失败时不阻塞玩法，使用 fallback skin
```

新增交付策略节点：

```text
asset.evaluate_promotion_policy
```

新增报告：

```text
shared/schemas/asset_promotion_report.v0.1.schema.json
```

promotion 状态：

```text
runtime_ready
  gameplay_core 可用，生成媒体也通过 runtime readiness / review，可直接进入运行时包。

fallback_ready
  gameplay_core 可用，但生成媒体缺失、失败或需要修复；使用确定性 fallback skin，后台继续生成/修复媒体。

preview_only
  gameplay_core 需要审查，只能展示或等待人工 / agent 复核，不能直接进战斗。

failed
  gameplay_core 本身不可用，不能交付给玩家。
```

当前默认策略：

- candidate validation 失败：`failed`。
- 严重 simulation flag：`failed`。
- gameplay_core 通过但没有媒体：`fallback_ready`。
- runtime readiness 失败但 gameplay_core 通过：`fallback_ready`。
- runtime readiness 通过且语义审查没有失败：`runtime_ready`。

这条规则比“图片必须一次成功”更可靠。玩家看到的是一次研发完成；系统内部可以用 fallback skin 保证战斗不断流。

## 8. 对前端的承诺

前端只应该消费：

```text
published_media_manifest
runtime_package
/assets/generated/*.png
atlas json
texture_key
atlas_frame
anchor
visual_recipe
```

前端不应该关心：

```text
provider
model
prompt
raw_media
processed_media
repair_plan
vision trace
```

这样玩家侧永远看到的是游戏资产，不是 AI 工具链。
