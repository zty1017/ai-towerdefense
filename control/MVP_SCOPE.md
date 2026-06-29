# MVP 范围冻结

Last updated: 2026-06-29

## 1. 定位

第一版 MVP 是教学关式演示 demo。

目标不是做完整游戏，而是证明一条强闭环：

```text
玩家进入世界
  -> 看到第一个危机节点
  -> 用世界内语言提出应急构想
  -> 系统生成试作方案
  -> 确认后进入研发倒计时
  -> 战斗中样品送达
  -> 玩家部署样品改变战局
  -> 战后世界状态、NPC 反馈和研发线索发生变化
```

## 2. 队伍与项目名

比赛队伍名：

```text
Compiler
```

项目定位：

```text
通用 AI 驱动塔防资产编译系统
```

MVP 世界书：

```text
long_night_lanterns / 《长夜灯火》
```

《长夜灯火》只是演示世界书模板，不是项目本体名称。

## 3. P0 必须完成

### 3.1 玩家主链路

P0 主链路固定为：

```text
1. 本地档案入口
2. 世界实例配置
3. 预制开场
4. 大地图 / 战略态势图
5. 战役节点 Briefing
6. 现场应急研发页
7. 战斗加载 / 研发任务创建
8. 塔防战斗页
9. 战后结算 / 世界生长
10. 返回大地图
```

### 3.2 体验链接与匿名 session

公开部署只暴露一个体验链接。

每个评委 / 玩家访问时自动创建匿名 session。

要求：

- 不做真实注册登录。
- 不做邮箱、手机号、验证码、第三方登录。
- 后端状态按 `session_id` 隔离。
- 支持重置演示。

### 3.3 世界实例配置

P0 只启用：

- 一个世界书模板：`long_night_lanterns`
- 一个推荐视觉风格
- 少量开局身份选项
- AI 创造性模式：稳健 / 实验性

选择结果写入 `world_instance_config`。

### 3.4 预制开场

开场不实时生成。

P0 使用：

- 30-60 秒可跳过开场。
- 黑屏白字。
- 2-3 张动画卡。
- 轻量镜头推拉 / 粒子 / 环境声。

### 3.5 大地图 / 战略态势图

P0 大地图是动态战略态势图，不是固定节点菜单。

必须表现：

- 主城 / 中枢。
- 当前危机战斗热点。
- 战略设施 / 资源存储节点。
- 补给线。
- 黑暗未知区。
- 移动威胁边缘。
- 地图悬浮任务 / NPC / 警报图标。

P0 不做复杂多线防守调度，只预留接口。

### 3.6 现场应急研发

P0 只做现场应急研发，不做完整正式研发机构。

玩家侧不出现：

- AI
- prompt
- schema
- provider
- compiler
- raw JSON

玩家看到的是世界内表达。

现场研发流程：

```text
玩家表达构想
  -> 生成 1 个试作方案
  -> 玩家可调整材料 / 补充构想
  -> 玩家确认试作
  -> 创建研发任务
```

默认只给 1 个方案。更多方案需要 NPC、材料、技术、设施或高风险条件触发，P0 不实现复杂多候选系统。

### 3.7 第一个 AI 编译资产

P0 第一个资产类型：

```text
temporary_trap_sample
```

它是临时减速陷阱样品。

要求：

- 生命周期为 `ephemeral`。
- 进入战斗底部热栏。
- 使用次数为 2。
- 在战斗中途送达。
- 触发后对敌人产生短时减速。
- 战后产生缺陷观察和正式研发线索。

### 3.8 研发任务与战斗中途送达

确认试作后不立刻给结果。

P0 使用后台研发：

```text
确认试作
  -> 进入战斗
  -> 前 30 秒样品仍在封装
  -> 样品完成并送达
  -> 热栏点亮
  -> 玩家部署
```

玩家侧文案使用：

- 现场试作中。
- 材料校准中。
- 样品封装中。
- 正在送达战场。

### 3.9 塔防战斗页

P0 战斗页布局：

- 左上圆形战略缩略图。
- 顶部状态 / 资源 / 暂停 / 倍速。
- 左侧任务事件栏。
- 中央斜视角伪 3D 主战场。
- 右侧动态战术面板。
- 底部资产热栏。
- 剧情触发时覆盖式剧情聚焦层。

战斗逻辑：

- 2D 网格 / 路径。
- 斜视角或等距伪 3D 表现。
- 一条简单敌人路径。
- 高速低耐久敌潮。
- 一个核心保护目标。
- 一个可选资源 / 设施保护目标。
- 基础拖延手段。
- 临时减速陷阱样品。

### 3.10 战后结算 / 世界生长

P0 战后页必须展示：

- 战报摘要。
- 节点状态变化。
- 资源 / 设施损伤或回收。
- 样品实战表现。
- 新暴露缺陷。
- NPC 反馈。
- 下一步正式研发线索。
- 返回大地图后的态势变化。

胜利和失败都推进世界，不做纯 Game Over。

### 3.11 locked manifest v0.1

P0 manifest 是前端安全读取的 locked 资产索引。

必须包含：

- `schema_version`
- `manifest_id`
- `session_id`
- `worldbook_id`
- `content_set`
- `locked_assets`

单个资产必须包含：

- `stable_internal_id`
- `asset_kind`
- `template_id`
- `worldbook_id`
- `session_instance_id`
- `lifecycle_state`
- `display`
- `gameplay_ref`
- `media_refs`
- `visual_recipes`
- `battle_availability`

不得包含：

- provider
- model
- raw_prompt
- full_trace
- raw_json
- api_key
- secret
- unreviewed_content

### 3.12 visual_recipes v0.1

P0 只允许：

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

通过调色板 token 和少量参数扩展表现，不允许任意脚本、CSS、shader。

### 3.13 演示证据导出

P0 不做 Studio 前端页面。

需要脚本导出演示证据：

```text
summary.md
evidence.json
index.html
```

证据导出可以展示技术细节，但必须避免泄露：

- API key。
- 完整敏感 prompt。
- provider 原始错误栈。
- 本地隐私路径。
- 未 reviewed / locked 的玩家侧内容。

## 4. P1 时间允许

P1 是在 P0 跑通后的扩展。

- 真实 provider 接入替代 mock 生成，但保留演示稳定模式。
- CodeBuddy / Hunyuan 图像生成进入离线素材候选。
- 多种开局身份实际影响开场和 NPC 称呼。
- 额外一个战役节点。
- 正式研发机构的入口和轻量稳定化流程。
- 简单 Tiled 地图导入或地图编辑 fixture。
- 更多动画卡和 NPC 立绘。
- 战斗 telemetry 与 mock simulation 差异报告。
- PWA / 缓存优化。

## 5. P2 明确不做

P2 不进入第一版 MVP。

- 真实注册登录系统。
- 多人联机。
- 完整 4X / 文明式系统。
- 完整红警式基地经营。
- 完整技术树。
- 复杂多线实时防守调度。
- 多世界书正式切换。
- 实时视频生成。
- 真 3D 战斗。
- 可视化 AssetGraph 编辑器。
- 运行时动态注册新 effect / node。
- 玩家侧 Studio 后台。

## 6. 技术栈

P0 技术栈：

```text
React + Vite + TypeScript
Phaser 3
Zustand
TanStack Query
FastAPI
SQLite
Python 内容管线
```

游戏运行时边界：

- `game/core` 负责确定性战斗逻辑。
- `game/phaser` 负责表现。
- React 负责页面和 HUD。
- 后端负责 session、研发任务、日志、asset compile run、证据导出。

## 7. 验收标准

P0 验收必须满足：

1. 新浏览器打开同一个链接会创建独立匿名 session。
2. 玩家能完整走完主链路。
3. 第一场战斗中样品能在倒计时后送达。
4. 玩家能部署临时减速陷阱并看到明显效果。
5. 战后页面能展示样品表现、节点变化和下一步线索。
6. 返回大地图后地图状态发生变化。
7. 运行时玩家侧不出现 AI/provider/schema/prompt/raw JSON 等出戏词。
8. `locked manifest` 不包含禁止字段。
9. 演示证据脚本能导出 `summary.md`、`evidence.json`、`index.html`。
10. `.env` 不进入 Git，不被任何脚本打印。

## 8. 降级策略

如果时间不足：

- 真实 AI 调用降级为预生成 fixture。
- 图像素材降级为占位图标和统一 sprite。
- 开场动画降级为黑屏白字 + 静态动画卡。
- 战斗地图降级为固定单路径。
- 世界生长降级为固定但按 session 写入的事件结果。
- 证据导出降级为 Markdown + JSON，不做 HTML。

降级不能破坏主闭环。
