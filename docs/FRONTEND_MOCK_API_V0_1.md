# 前端 Mock API v0.1

本文档记录 MVP 前端 mock 接口。它服务于当前比赛演示链路：

```text
本地档案 / 世界实例配置
-> 预制开场
-> 大地图
-> 第一个危机节点
-> 现场试作
-> 战斗中样品送达
-> 战后结算 / 世界状态变化
-> 简单证据展示
```

## 边界

- 接口不调用 LLM。
- 接口不调用图片、视频或音频 provider。
- 接口不读取 `.env`。
- 前端看到的是统一后端 API，不需要直接读仓库 JSON 文件。
- 当前动效资源处于 `animation seed` 阶段：种子图已经生成，视频帧 / spritesheet / atlas 后续再补。

## 静态媒体

后端启动时会挂载：

```text
/assets/frontend_mock/processed
/assets/frontend_mock/generated
```

`processed` 是前端默认使用的透明 PNG。  
`generated` 是后续图生视频 / 动画卡管线的种子图来源。

## 通用返回壳

新增接口统一返回：

```json
{
  "session_id": "...",
  "mode": "frontend_mock_fixture",
  "payload": {}
}
```

`mode` 表示当前走稳定 mock fixture，不代表实时生成。

## 接口清单

### 创建世界实例

```http
POST /api/sessions/{session_id}/world-instance
```

请求体可选：

```json
{
  "selected_options": {
    "creativity_mode": "stable",
    "player_origin": "lampwright_apprentice",
    "visual_style_id": "lantern_wasteland_pseudo3d"
  }
}
```

返回：

- `world_instance`
- `run_world_state`

并写入：

- `world_instance`
- `campaign_state`

### 获取前端总包

```http
GET /api/sessions/{session_id}/frontend-mock-pack
```

返回：

- `pack`: `examples/frontend_mock/frontend_mock_pack.v0.1.json`
- `media_manifest`: processed 媒体清单
- `animation_seed_manifest`: 图生视频种子图清单
- `animation_pipeline_status`

### 获取开场

```http
GET /api/sessions/{session_id}/opening
```

返回预制开场内容。

### 获取动画种子

```http
GET /api/sessions/{session_id}/animation-seeds
```

返回 `frontend_animation_seed_manifest.v0.1.json`。当前状态：

```text
seed_images_ready_video_frames_not_generated
```

含义是：可以用种子图做前端临时 tween / shader / visual recipe 动效，但还没有真正的视频帧序列。

### 获取大地图

```http
GET /api/sessions/{session_id}/map
```

返回：

- `map`
- 当前 session 的 `run_world_state`

战后再次调用会看到更新后的世界状态。

### 获取节点简报

```http
GET /api/sessions/{session_id}/nodes/{node_id}/briefing
```

当前首战支持：

```text
gray_lantern_station
```

返回：

- 节点 briefing
- 当前材料
- 当前 NPC
- 建议玩家输入示例

### 获取战斗配置

```http
GET /api/sessions/{session_id}/battles/{node_id}/config
```

返回：

- battle config
- bottom toolbar assets
- sample delivery asset
- media manifest
- animation seed manifest

前端可用该接口构建战斗页面。

### 获取 runtime package

```http
GET /api/sessions/{session_id}/battles/{node_id}/runtime-package
```

返回当前节点对应 reviewed runtime package，同时附带当前可用的样品展示资产和媒体清单。

### 提交战斗结果

```http
POST /api/sessions/{session_id}/battles/{node_id}/results
```

请求体：

```json
{
  "result": "victory",
  "protected_core_hp": 7,
  "optional_target_state": "damaged",
  "deployed_asset_ids": ["asset_mirror_lure_trap_001"],
  "leaked_enemy_count": 1,
  "notes": "front-end simulated battle result"
}
```

返回：

- settlement
- world delta
- 更新后的 run world state

并写入：

- `battle_results`
- `campaign_state`

### 获取最近结算

```http
GET /api/sessions/{session_id}/settlement/latest
```

返回最近一次战斗结算。若还未提交战斗结果，则 `settlement` 为 `null`。

### 获取演示证据

```http
GET /api/sessions/{session_id}/evidence
```

返回简单 Studio / 录屏证据 payload：

- 最新 proposal
- 最新 research job
- 最新 battle result
- audit summary
- dossier summary

这不是正式后台页面，只是演示证明入口。
