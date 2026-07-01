# 前端运行时 Mock 美术包 v0.1

本文档说明 `frontend_battle_mock_art_kit.v0.1` 的用途、边界和验收方式。

它是“开发者使用的 AI 编译管线产物”，不是玩家在游戏内现场研发时直接看到的编译结果。MVP 阶段前端不实时调用 LLM 或图片 provider，而是读取这批已生成、已后处理、已发布的素材来模拟完整战斗体验。

## 定位

```text
开发者编译输入
  -> 战斗运行时美术需求
  -> 图像 provider 生成白底母图
  -> PNG 后处理 / 抠白底 / 裁切 / 归一化 / anchor
  -> frontend_runtime_art_media_manifest
  -> 前端 battle mock 直接加载
```

玩家侧仍然只看到游戏内叙事、工坊试作、战斗送达和结算反馈。provider、prompt、schema、trace、API key 等技术细节不得进入玩家体验。

## 当前覆盖

第一版运行时 mock 美术包覆盖：

- 敌人：快速敌、残影敌、聚团敌。
- 保护目标：节点核心、信标、灯芯物资箱。
- 基础防御件：基础灯栏 / 阻挡物。
- NPC：战斗无线电 / 剧情对话用头像。
- 地图 token：路径、塔位、出生点、核心点、资源点、黑暗区域和威胁边界。
- 程序化特效：基础弹道、命中爆发、减速光环、死亡粒子、漏怪反馈。

其中敌人、目标、防御件和 NPC 会生成 PNG；地图 token 与程序化特效由前端按结构化 recipe 绘制。

## 文件

```text
examples/frontend_mock/frontend_battle_mock_art_kit.v0.1.json
game_data/media/frontend_runtime_mock/frontend_runtime_art_media_manifest.v0.1.json
game_data/media/frontend_runtime_mock/frontend_runtime_art_raw_media_manifest.v0.1.json
game_data/media/frontend_runtime_mock/frontend_runtime_art_animation_seed_manifest.v0.1.json
game_data/media/frontend_runtime_mock/generated/
game_data/media/frontend_runtime_mock/processed/
```

后端静态挂载：

```text
/assets/frontend_runtime_mock/generated
/assets/frontend_runtime_mock/processed
```

前端默认使用 `processed` PNG。`generated` PNG 是后续“图片 -> 视频 -> 关键帧 -> atlas”路线的种子。

## API 接入

可通过以下接口读取：

```http
GET /api/sessions/{session_id}/runtime-art-kit
GET /api/sessions/{session_id}/frontend-mock-pack
GET /api/sessions/{session_id}/battles/{node_id}/config
GET /api/sessions/{session_id}/battles/{node_id}/runtime-package
```

返回字段：

- `runtime_art_kit`
- `runtime_art_media_manifest`
- `runtime_art_animation_seed_manifest`
- `runtime_art_pipeline_status`

## 当前边界

- 不生成视频帧。
- 不生成 spritesheet / atlas。
- 不把攻击特效烘焙进主体图。
- 不把玩家侧中文名写入图像 prompt。
- 不在 manifest 中保存 provider、model、raw prompt、raw JSON 或临时 URL。

因此当前前端应使用：

- `processed` PNG 作为可摆放主体。
- `procedural_effects` 作为 Canvas / Phaser / Pixi 的轻量特效 recipe。
- `animation_seed_manifest` 作为后续图生视频或动图管线的输入，而不是默认战斗素材。

## 验收命令

生成前只校验 kit：

```bash
python3 tools/media/validate_frontend_runtime_art_pack.py --allow-missing-manifest
```

生成并后处理：

```bash
python3 tools/media/build_frontend_runtime_art_media_pack.py --live --force
python3 tools/media/postprocess_frontend_mock_media_pack.py \
  --manifest game_data/media/frontend_runtime_mock/frontend_runtime_art_media_manifest.v0.1.json \
  --raw-copy-manifest game_data/media/frontend_runtime_mock/frontend_runtime_art_raw_media_manifest.v0.1.json \
  --seed-manifest game_data/media/frontend_runtime_mock/frontend_runtime_art_animation_seed_manifest.v0.1.json \
  --output-dir game_data/media/frontend_runtime_mock/processed \
  --public-prefix /assets/frontend_runtime_mock/processed \
  --seed-public-prefix /assets/frontend_runtime_mock/generated
```

生成后完整校验：

```bash
python3 tools/media/validate_frontend_runtime_art_pack.py
python3 -m compileall backend
```
