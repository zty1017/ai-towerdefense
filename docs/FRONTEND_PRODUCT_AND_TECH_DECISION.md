# 前端产品形态与技术决策

Last updated: 2026-06-29

## 1. 决策状态

本文记录前端产品形态、游戏表现和技术栈决策。

决策方式：

- 每次只讨论并确认一个问题。
- 未确认的问题只保留为待讨论，不提前固化。
- 所有前端文档使用中文。

## 1.1 命名与世界内文本原则

本文讨论中出现的游戏内名词，例如机构、道具、防御塔、NPC、身份、节点、材料和事件名称，除非明确标记为 locked 内容，否则都只是占位语义锚点。

最终玩家侧文本不应由开发者长期写死。

它应由以下因素共同生成或选择：

- 世界书。
- 玩家游玩情况。
- 当前节点和战斗上下文。
- NPC、设施、材料和科技状态。
- 游戏底层规则限制。
- 内容生命周期状态。

内部可以使用稳定技术标识：

```text
research_entry
formal_research_institute
temporary_trap_sample
node_battle_hotspot
```

玩家侧显示名应是世界内名称，并经过 reviewed / locked 流程后进入正式内容。

示例：

```text
内部功能位：
formal_research_institute

世界书生成或选择的显示名：
余灯工造院 / 守灯铸造所 / 灯塔研修院
```

开发文档可以使用临时名称辅助讨论，但实现时要把“稳定内部 ID”和“世界内显示名”分离。

## 1.2 模板与单局实例原则

项目需要通用默认模板，但玩家单局看到的内容应该是世界观与游玩过程演化后的实例。

三层结构：

```text
系统级通用模板
  -> 世界书适配模板
  -> 单局运行实例
```

### 系统级通用模板

由开发者提供稳定结构，负责约束玩法和前端加载。

示例：

- `temporary_trap_sample`
- `tower_blueprint`
- `support_item`
- `npc_support_skill`
- `battle_node`
- `research_facility`
- `locked_manifest_asset`

系统级模板定义：

- 需要哪些字段。
- 允许哪些 effect_blocks。
- 能进入哪些 UI surface。
- 生命周期如何变化。
- 如何被 Phaser / game-core 运行时解释。

### 世界书适配模板

世界书把通用模板翻译成世界内表达。

同一个 `temporary_trap_sample` 在不同世界书中可以表现为：

```text
长夜灯火：
折光绊索 / 灯芯绊线 / 灰灯陷索

赛博朋克：
频闪绊雷 / 神经扰频器

奇幻：
符文缚环 / 月银缠索
```

世界书适配模板决定：

- 命名风格。
- 材料名。
- 机构名。
- NPC 评语口吻。
- 图像 prompt 风格。
- 动画卡风格。

### 单局运行实例

每个 session 中，根据玩家输入、当前节点、投入材料、战斗结果生成具体实例。

示例字段：

```text
stable_internal_id: sample_trap_7f3a
template_id: temporary_trap_sample
worldbook_id: long_night_lanterns
session_instance_id: session_xxx
display_name: 本局生成并 locked 的世界内名称
materials_used: 本局实际投入材料
revealed_defects: 本局战后暴露缺陷
```

`locked manifest` 应记录这个资产来自哪个通用模板、哪个世界书适配、哪个单局实例，而不是把所有内容当作一次性自由生成。

## 2. 已确认：首次体验第一幕

首次体验第一幕不是常规大地图页，而是一段完整的新档案进入流程。

MVP 第一幕流程：

```text
本地档案入口
  -> 世界实例配置
  -> 预制开场文字 / 动画卡 / 开屏过场
  -> 大地图页面
  -> 引导玩家点击第一个战役点
  -> 第一次 AI 编译小道具 / 陷阱
  -> 第一场短战斗
```

### 2.1 本地档案入口

MVP 不做复杂用户注册登录。

入口形态：

```text
继续当前体验
开始新档案
重置演示
设置
```

这里可以看起来像登录页，但实际只管理匿名体验会话、本地档案和演示入口。

普通玩家入口不展示 Studio 模式。演示证据通过脚本导出，不作为默认前端页面。

公开部署可以只暴露一个体验链接，但不能使用全局共享存档。

多评委体验策略：

```text
评委打开同一个链接
  -> 前端检测 localStorage / cookie
  -> 没有 session_id 就向后端创建匿名体验会话
  -> 后端返回 session_id
  -> 之后所有世界状态、AI 编译记录、战斗结果按 session_id 隔离
```

后端状态表应带 `session_id`：

- `world_instance`
- `campaign_state`
- `asset_compile_runs`
- `battle_results`
- `provider_logs`
- `studio_logs`

MVP 不需要手机号、邮箱、密码、验证码、第三方登录或复杂用户中心。

为了比赛稳定性，应支持：

```text
普通体验：真实 AI / fallback / 缓存
演示稳定模式：优先使用预生成结果，可选真实调用
```

### 2.2 世界实例配置

这一页类似游戏捏脸，但捏的不是角色外观，而是本次世界实例。

它应该像开局仪式，而不是后台设置表单。

MVP 页面结构：

```text
左侧：世界书模板卡
中间：世界预览 / 画风预览
右侧：开局参数
底部：开始生成世界 / 使用推荐配置
```

MVP 可展示：

- 世界书模板：`long_night_lanterns` / 《长夜灯火》
- 画风：默认推荐画风
- AI 创造性：稳健 / 实验性
- 开局身份：守灯技师 / 流亡工程师 / 见习调度员

MVP 可以只真正启用一个世界书模板和一个推荐画风，其他选项可作为未解锁或演示占位。

这些选择不是普通皮肤设置，而是会写入 `world_instance_config`。

示例：

```text
worldbook_template_id: long_night_lanterns
visual_style_id: lantern_wasteland_pseudo3d
creativity_mode: stable
player_origin: lampwright_apprentice
```

这些字段会影响：

- NPC 称呼玩家的方式。
- 开局资源。
- AI 生成提案时的设定约束。
- 图像 prompt 风格。
- 开场文字。
- 第一个战役点说明。

### 2.2.1 正式研发机构与现场应急研发

研发体系分为两层：

```text
现场应急研发
  当前战役节点前 / 战中使用
  产物偏向小道具、陷阱、临时改造
  快、风险高、生命周期短

正式研发机构
  主城 / 中枢设施中使用
  产物偏向防御塔蓝图、技术、材料工艺、稳定化资产
  慢、消耗高、可长期解锁
```

在系统内部，正式研发机构是通用功能位：

```text
formal_research_institute
```

玩家侧名称由世界书、主城设施和 NPC 上下文决定。例如《长夜灯火》中可以由世界书生成：

- 余灯工造院
- 守灯铸造所
- 灯塔研修院
- 中枢工坊

这对应资产生命周期：

```text
ephemeral
  节点现场临时资产

session_blueprint
  本次战役可复用资产

stabilized_blueprint
  正式研发稳定化后的长期蓝图
```

MVP 第一战只实现节点现场应急研发，但机制和数据结构应预留正式研发机构。

正式研发机构不应在现场应急研发页常驻说明，避免系统解释打断玩家体验。

它只在合适时机自然出现：

- 战后 NPC 评价。
- 某个试作效果很好时。
- 玩家第一次打开正式研发机构时。
- 系统解锁“登记蓝图”功能时。

### 2.3 预制开场

开场不追求实时生成。

MVP 开场目标：

- 建立世界氛围。
- 交代第一场危机。
- 引出大地图。
- 引出第一次 AI 编译。

推荐形式：

```text
总时长：30-60 秒
形式：黑屏白字 + 动画卡 + 轻量镜头推拉 + 音效 / 环境声
可跳过
可回看
```

MVP 使用：

- 黑屏白字的短文字段落
- 预制动画卡
- 预制开屏过场动画
- 2D 立绘、视差背景、轻量粒子、镜头推拉

开场分段：

```text
1. 黑屏白字：世界背景
   长夜没有结束，灯塔一座接一座熄灭。

2. 动画卡 1：远景
   暗色大地图 / 灯火稀疏 / 影潮边缘逼近

3. 动画卡 2：危机
   第一个战役点被标红，NPC 发来急报

4. 动画卡 3：玩家介入
   你被唤醒为守灯技师，需要用有限材料临时改造防线
```

开场最后落到：

```text
大地图页
当前节点：灰灯驿站
状态：高速影潮接近
建议：寻找临时阻滞手段
```

视频生成可以用于开发期离线生产开场素材，但生成结果必须经过 reviewed / locked 后进入游戏。

### 2.4 大地图页面

大地图不是固定节点菜单，而是动态战略态势图。

它表现的是：

- 主城 / 中枢。
- 前哨 / 据点。
- 战斗热点。
- 战略设施 / 资源存储节点。
- 路线 / 补给线。
- 黑暗未知区。
- 移动威胁区。
- 地图悬浮事件。
- NPC / 小队标记。

资源节点不应简单理解为野外矿点。

更准确的资源相关对象：

- 灯芯仓。
- 备用电站。
- 晶体库。
- 废料堆场。
- 观测设施。
- 临时工坊。

资源开采点可以出现在战斗节点内部，作为战斗保护目标。例如战斗中保护采晶机、供电塔或临时输送装置。

重要节点未来都可以被攻打，包括主城。MVP 中主城先作为中枢，不开放主城防御战。

未知区域初始由黑暗遮盖。玩家通过情报、探索、战后事件和 AI 生长逐步揭示地图。

剧情和任务不一定是固定地图节点，可以是地图上的悬浮 NPC 头像、任务图标、求援信号、异常裂缝或战斗警报。

MVP 页面职责：

```text
1. 展示当前世界状态
2. 展示主城、可见据点、路线和当前危机
3. 标出黑暗、威胁边缘和战斗热点
4. 展示资源设施 / 存储设施 / NPC 状态摘要
5. 引导玩家进入第一个战役点
6. 为后续多线防守和节点调度预留接口
```

MVP 第一张地图可以包含：

```text
可见区域：
- 余灯中枢（主城）
- 灰灯驿站（当前战斗热点）
- 临时工坊（设施）
- 灯芯仓（资源存储设施）
- 一条从主城到灰灯驿站的补给线

黑暗区域：
- 大部分地图被黑暗遮盖
- 右下角有影潮移动边缘

悬浮事件：
- NPC 求援图标
- 当前任务标记
- 战斗警报图标
```

### 2.5 第一次 AI 编译对象

第一场战斗不急于编译完整防御塔。

第一次 AI 编译推荐对象：

```text
小道具 / 一次性陷阱 / 临时装置
```

原因：

- 教学成本低。
- 实现风险小。
- 战斗验证快。
- 玩家能更自然地理解“想法 -> 提案 -> 编译 -> 可用资产”。

示例：

```text
玩家输入：
我想做一个能拖慢影潮的临时装置。

系统提案：
折光绊索

类型：
一次性陷阱 / 小道具

效果：
经过的敌人短暂减速。

代价：
消耗少量灯芯碎片。
```

第二个战役点再升级到完整防御塔编译：

```text
折光绊索效果不错。
NPC 建议把它稳定化为塔式装置。
玩家输入：我想造一座能持续用灯光拖慢敌人的防御塔。
```

## 3. 已确认：前端技术栈 v0.1

MVP 前端技术栈：

```text
React + Vite + TypeScript：前端应用外壳
Phaser 3：塔防战斗画布
Zustand：本地 UI / 战斗快照状态
TanStack Query：后端数据请求
FastAPI + SQLite：AI 编译器、日志、资产状态后端
纯 TypeScript game/core：确定性战斗规则核心
locked manifest：前端只加载已校验资产
```

边界：

- React 负责工坊、卡牌、页面流转和玩家侧反馈。
- Phaser 负责战斗表现、地图、精灵、粒子、镜头和命中反馈。
- 纯 TypeScript `game/core` 负责确定性数值、效果执行、波次和战斗状态推进。
- AI 生成的内容不能直接变成可运行前端逻辑。
- 前端只加载 reviewed / locked 后的 manifest 和资产。

## 4. 待讨论问题

后续按顺序逐个确认：

1. MVP Scope 与任务拆分。

## 5. 已确认：演示证据与 debug 范围

玩家模式必须保持正常游戏体验。

玩家模式不展示：

- provider
- token
- schema
- trace
- JSON
- 错误栈
- mock simulation 技术细节

玩家感知 AI 驱动的方式是：

- 世界会回应玩家想法。
- 研发会生成新资产。
- 战斗结果会反哺世界状态。
- NPC 和事件会根据上下文生长。

MVP 不做复杂 Studio 前端页面，也不要求在游戏内展示 debug 后台。

录制演示视频或评委追问时，用脚本从后端日志、运行记录和生成工件中抽取证据，生成静态报告。

建议形态：

```text
python tools/demo/export_evidence.py --session-id <SESSION_ID> --run-id <RUN_ID>
  -> demo_exports/<RUN_ID>/summary.md
  -> demo_exports/<RUN_ID>/evidence.json
  -> demo_exports/<RUN_ID>/index.html
```

证据报告可展示：

- AI 编译运行 ID
- 用户输入摘要
- `worldbook_id`
- provider / model
- 提案摘要
- schema 校验结果
- mock simulation 摘要
- 生成资产 ID
- fallback / error 状态
- 关键时间戳

AssetGraph trace 在 MVP 证据报告中使用文本列表即可：

```text
1. parse_player_intent: success
2. generate_proposal: success
3. compile_candidate: success
4. validate_schema: success
5. run_mock_simulation: warning
6. export_locked_manifest: success
```

证据报告不进入玩家主体验，也不要求做成长期维护的可视后台。

导出脚本必须避免泄漏：

- API key。
- 完整敏感 prompt。
- 原始 provider 错误栈中的凭据。
- 本地绝对路径中不必要的隐私信息。
- 未 reviewed / locked 的玩家侧内容。

## 6. 已确认：塔防战斗页布局

塔防战斗页采用全屏战斗场景 + 贴边 HUD。

核心布局：

```text
左上圆形战略缩略图      顶部状态 / 资源 / 暂停 / 倍速

左侧任务事件栏        中央斜视角主战场        右侧战术面板
- 本场目标            塔 / 陷阱 / 敌人 / NPC  - 选中对象详情
- 临时事件            路径 / 部署格 / 特效     - 敌潮预告
- 环境影响                                      - NPC 建议

剧情触发时：覆盖式剧情聚焦层

底部：陷阱 / 道具 / 防御塔 / NPC 支援技能横向热栏
```

### 6.1 左上圆形战略缩略图

左上角放圆形战略缩略地图。

作用：

- 缩略显示大地图。
- 当前战斗节点用重点色和战斗图标标注。
- 点击后可打开大地图页面或大地图浮层。
- 战斗中默认不允许随意切换节点，只允许查看态势。
- 后续为多线防守、节点调度和战场切换预留接口。

### 6.2 中央主战场

中央是最大视觉区域。

表现方式：

- 逻辑层为 2D 网格 / 路径。
- 表现层为斜视角 / 等距伪 3D。
- 使用 y-depth sorting、椭圆阴影、光环、粒子、遮挡和视差制造空间感。
- Phaser 负责表现，纯 TypeScript `game/core` 负责确定性战斗规则。

### 6.3 左侧任务事件栏

左侧不放资产栏。

左侧展示：

- 本场目标
- 敌潮预警
- 临时事件
- 环境影响
- 战斗约束

它是世界内信息，不是 debug 面板。

### 6.4 顶部状态控制条

顶部保持克制，只放高频状态：

- 当前节点名
- 波次
- 核心耐久
- 电力
- 资源
- 暂停
- 倍速

### 6.5 底部横向资产热栏

底部放陷阱、道具、防御塔、NPC 支援技能。

每个格子展示：

- 图标
- 资源消耗
- 冷却
- 剩余次数
- 可用 / 不可用状态

资源或冷却满足时点亮，不满足时置灰。

MVP 第一场可以只开放小道具 / 一次性陷阱。

### 6.6 右侧动态战术面板

右侧用于保持视觉平衡，同时承载上下文战术信息。

默认状态：

- 下一波敌潮
- 敌人弱点
- 环境异常
- NPC 简短建议

选中对象后切换：

- 选中防御塔：范围、伤害、效果、升级 / 改造入口。
- 选中陷阱：触发范围、剩余次数、回收 / 强化。
- 选中 NPC：状态、支援技能、冷却、剧情提示。
- 选中敌人：类型、抗性、弱点、当前异常状态。

### 6.7 参战 NPC 与技能

参战 NPC 是否拥有技能仍待具体玩法确认，但布局预留接口。

可能交互：

- 点击战斗画面中的 NPC，头顶出现技能图标。
- 点击 NPC 后弹出类似防御塔升级 / 改造的小面板。
- 底部热栏也可以提供 NPC 支援技能格。

MVP 可以先弱实现为“NPC 支援技能按钮 + 目标选择”。

### 6.8 剧情触发层

剧情触发时进入覆盖式剧情聚焦态，而不是跳出战斗场景。

层级：

```text
底层：战斗仍在原场景中
中层：原 HUD 压暗、部分隐藏或退后
顶层：角色立绘 + 底部对话框 + 可选选择按钮
```

原战斗画面作为压暗背景。

剧情状态分三类：

```text
普通战斗态
  中央战场 + 左右面板 + 顶部状态 + 底部热栏

轻提示态
  不暂停战斗
  小头像 / 短 toast / 右侧 NPC 建议

剧情聚焦态
  暂停或慢放战斗
  背景战场压暗、模糊或降饱和
  角色立绘进入画面主体
  底部展开对话框
  可出现 1-2 个选择按钮
```

普通 NPC 提醒不应频繁进入剧情聚焦态。关键节点才使用，例如首次触发陷阱、敌潮异变、NPC 支援解锁、战后前置剧情。

## 7. 已确认：现场应急研发页

现场应急研发页是通用功能位，不是固定世界观名称。

系统内部可以称为：

```text
research_entry
proposal_entry
intent_workshop_page
```

玩家侧名称由世界书、当前节点、设施和 NPC 上下文决定。

例如《长夜灯火》中可以显示为：

- 灰灯驿站应急改造间
- 铸灯台
- 守灯研修间
- 临时图纸台

其他世界书应使用对应世界观名称，不应出现 AI、prompt、schema、provider、compiler 等技术词。

### 7.1 页面职责

现场应急研发页只负责把玩家构想转成可确认的研发提案。

它不直接展示已编译游戏资产。

流程：

```text
玩家表达构想
  -> 生成研发提案
  -> 玩家查看 / 补充 / 确认提案
  -> 确认后进入试作 / 编译过程
  -> 编译后才生成 CompiledAssetCandidate
```

MVP 只做文本构想输入，后续预留语音输入。

语音后续流程：

```text
语音输入
  -> ASR 转文本
  -> 玩家确认 / 编辑
  -> 进入同一条提案与编译管线
```

语音输入不能绕过文本确认、提案确认和 Schema 校验。

### 7.2 页面布局

推荐布局：

```text
顶部：
当前节点 / 危机名 / 世界内设施名

左侧：当前危机与现场限制
- 敌潮特征
- 地形 / 保护目标
- 可用材料
- 当前限制

中间：玩家构想输入
- 向设施说明你的构想
- 文本输入框
- 后续预留语音按钮

右侧：参与者与条件
- NPC 在场状态
- 设施状态
- 材料 / 技术
- 可解锁更多提案的条件

下方：试作方案卡
- 方案预估
- 建议投入 / 可投入材料
- 已知约束
- 研发不确定性
- NPC 初步判断
- 操作按钮
```

默认只生成 1 个试作方案。

更多方案需要 NPC、材料、技术、设施、玩家补充构想或高风险研发条件触发。

### 7.3 试作方案卡字段

玩家看到的是试作方案卡，不是 Proposal。

MVP 字段：

- 方案名称。
- 一句话描述。
- 预期作用。
- 建议投入 / 可投入材料。
- 已知约束。
- 不确定性 / 研发风险。
- NPC 初步判断。
- 操作按钮。

材料不是 AI 给出的固定清单。

玩家可以：

- 添加材料。
- 替换材料。
- 减少材料。
- 询问 NPC 建议。

材料可能影响：

- 成功率 / 稳定性。
- 持续时间。
- 使用次数。
- 触发范围。
- 副作用概率。
- 后续可稳定化潜力。

已知约束只展示提案阶段能明确判断的内容，例如：

- 一次性装置。
- 需要部署在路径边缘。
- 需要手动触发。
- 会占用一个临时装置槽。

不确定性 / 研发风险使用预估表达，例如：

- 可能对重甲敌人效果不稳定。
- 可能需要现场调试。
- 可能消耗额外电力。
- 模拟后才能确认持续时间。

### 7.4 信息分阶段披露

数值和缺陷按阶段逐步显现。

```text
提案阶段：
  给预估。

AI 编译后：
  形成明确试作参数和已识别缺陷。

实战后：
  暴露隐藏缺陷、验证偏差和改良线索。
```

提案阶段玩家看到的是模糊的世界内语言：

```text
预期：短暂减速
消耗：少量灯芯材料
风险：对高速敌潮可能不稳定
```

试作 / AI 编译后可以形成明确试作参数：

```text
部署次数：2
触发范围：小
减速强度：中
持续时间：短
材料消耗：灯芯碎片 x2
已识别缺陷：对无影类敌人效果衰减
```

玩家侧不一定显示底层精确数值，可以显示成世界内属性条或等级：

```text
减速：中
持续：短
稳定性：偏低
```

演示证据报告才显示精确 JSON 数值。

实战后可能揭示：

```text
实际触发慢半拍
雨雾环境中效果下降
敌人适应后第二波减速变弱
NPC 发现可以改良为持续光幕
```

这些发现可以进入正式研发机构、战后结算或世界书事件。

### 7.5 确认试作后的研发任务

玩家确认试作后，不应立刻跳到后台式“编译结果页”。

它应表现为世界内研发任务。

流程：

```text
确认试作
  -> 创建研发任务
  -> 进入研发倒计时
  -> 玩家可以等待，或先进入战斗
  -> 研发完成后获得样品 / 试作品
  -> 样品进入底部热栏或节点补给
```

MVP 支持两种节奏：

```text
短等待：
  玩家留在应急改造间，看 10-20 秒试作进度，然后获得样品。

后台研发：
  玩家先进入战斗，样品在第 1 波或第 2 波中途完成，作为战场补给送达。
```

MVP 第一战推荐后台研发。

示例体验：

```text
玩家确认“折光绊索”试作
  -> 灰灯驿站战斗开始
  -> 前 30 秒玩家只能用基础手段拖延
  -> NPC 提示“样品还在封装”
  -> 倒计时结束
  -> 底部热栏点亮“折光绊索 x2”
  -> 玩家部署，看到减速效果
```

玩家侧文案不出现“AI 编译中”。

可用文案：

- 现场试作中。
- 材料校准中。
- 样品封装中。
- 正在送达战场。

完成后玩家看到：

```text
样品完成：折光绊索
可部署次数：2
稳定性：偏低
已识别风险：强雾中效果可能衰减
```

底层状态机：

```text
proposal_confirmed
  -> research_job_created
  -> research_in_progress
  -> sample_ready / delayed / unstable / failed
  -> sample_delivered
  -> battle_used
  -> after_action_report
```

## 8. 已确认：locked manifest v0.1 字段范围

`locked manifest` 是前端运行时能安全读取的已锁定资产索引。

它不是：

- 编译日志。
- AI 原始输出。
- provider 调用记录。
- 完整 AssetGraph trace。
- 未审查内容容器。

### 8.1 顶层结构

v0.1 顶层结构：

```json
{
  "schema_version": "locked_manifest.v0.1",
  "manifest_id": "manifest_session_xxx_001",
  "session_id": "session_xxx",
  "worldbook_id": "long_night_lanterns",
  "content_set": "mvp_demo",
  "created_at": "2026-06-29T00:00:00Z",
  "locked_assets": []
}
```

### 8.2 单个 locked asset

每个资产至少包含：

```text
1. 身份与来源
2. 显示信息
3. 玩法引用
4. 媒体引用
5. 表现 recipe
6. 可用性
```

示例：

```json
{
  "stable_internal_id": "sample_trap_7f3a",
  "asset_kind": "temporary_trap_sample",
  "template_id": "temporary_trap_sample",
  "worldbook_id": "long_night_lanterns",
  "session_instance_id": "session_xxx",
  "lifecycle_state": "ephemeral",
  "display": {
    "name": "本局 locked 的世界内名称",
    "summary": "玩家侧一句话说明",
    "tags": ["陷阱", "减速", "试作品"]
  },
  "gameplay_ref": {
    "kind": "compiled_asset_candidate",
    "path": "game_data/compiled_assets/sample_trap_7f3a.json",
    "sha256": "..."
  },
  "media_refs": {
    "icon": {
      "url": "/assets/icons/sample_trap_7f3a.webp",
      "width": 512,
      "height": 512,
      "sha256": "..."
    },
    "sprite": {
      "texture_key": "sample_trap_7f3a",
      "atlas": "/assets/atlases/traps.json",
      "image": "/assets/atlases/traps.webp"
    }
  },
  "visual_recipes": [
    {
      "trigger": "on_activate",
      "kind": "ring_pulse",
      "color": "#9edcff",
      "duration_ms": 900
    }
  ],
  "battle_availability": {
    "surfaces": ["battle_hotbar"],
    "uses_per_battle": 2,
    "requires_delivery": true,
    "delivery_state": "research_in_progress"
  }
}
```

### 8.3 字段边界

确认规则：

- `display.name` 是 locked 后的玩家侧名，不是运行时临时再生成。
- `gameplay_ref` 指向已校验玩法定义，manifest 不内嵌完整 gameplay。
- `media_refs` 只引用已缓存 / 已锁定素材，不引用 provider 临时 URL。
- `visual_recipes` 是声明式表现，不允许任意 JS、CSS、shader 或脚本。
- `battle_availability` 控制前端能不能把资产放入热栏、节点补给或其他 UI surface。
- manifest 应记录 `template_id`、`worldbook_id` 和 `session_instance_id`，以体现通用模板、世界书适配和单局实例三层来源。

不得出现：

- `provider`
- `model`
- `raw_prompt`
- `full_trace`
- `raw_json`
- `api_key`
- `secret`
- `unreviewed_content`

证据导出脚本可以从日志和 trace 文件中读取技术细节，但玩家运行时 manifest 不能携带这些字段。

### 8.4 visual_recipes v0.1

`visual_recipes` 第一版只允许有限模板，不做复杂特效系统。

允许类型：

```text
ring_pulse        地面环形脉冲
beam              光束 / 射线
chain_arc         连锁弧线 / 跳转特效
sprite_flash      精灵闪烁 / 染色
particle_burst    粒子爆发
aura_field        持续范围光环
screen_shake      轻量镜头震动
floating_text     短文字反馈
```

这些类型通过调色板 token 和少量参数变化扩展表现，而不是为每个资产生成全新动画逻辑。

建议参数：

```text
palette_token
color
secondary_color
intensity
radius
duration_ms
particle_density
blend_mode
```

参数边界：

```text
intensity: low / medium / high
particle_density: low / medium / high
blend_mode: normal / additive / multiply
duration_ms: 需要上下限
radius: 可以固定，也可以从 gameplay effect 读取
```

颜色策略：

```text
冷蓝：减速 / 冻结 / 稳定场
暖金：灯火 / 治疗 / 护盾
红橙：爆裂 / 过载 / 燃烧
紫黑：腐蚀 / 影潮 / 诅咒
绿色：修复 / 生长 / 毒素
白色：净化 / 眩光 / 暴露
```

颜色不能完全自由生成。

推荐结构：

```json
{
  "kind": "aura_field",
  "palette_token": "light.control.cold",
  "color": "#9edcff",
  "secondary_color": "#ffffff",
  "intensity": "medium",
  "radius_from_effect": "slow.radius",
  "duration_ms": 1200
}
```

`palette_token` 是语义稳定字段，由世界书和运行时约束选择。

`color` 是 locked 后解析出的具体颜色值。

`chain_arc` 只负责表现，不负责真实连锁逻辑。

真实连锁逻辑必须来自 gameplay effect_blocks，例如：

- `pierce_or_chain`
- `mark_vulnerability`
- `aura_buff`

示例：

```json
{
  "trigger": "on_chain",
  "kind": "chain_arc",
  "palette_token": "light.control.cold",
  "color": "#9edcff",
  "max_links_from_effect": "pierce_or_chain.max_targets",
  "arc_style": "curved",
  "duration_ms": 280,
  "intensity": "medium"
}
```

`arc_style` v0.1 可选：

```text
straight
curved
jagged
```

## 9. 已确认：MVP 前端页面链路

第一版 MVP 固定为教学关式演示 demo。

它用于验证核心闭环，不代表完整最终愿景。

MVP 主链路：

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

流程说明：

```text
本地档案入口：
  创建匿名 session 或继续当前 session。

世界实例配置：
  选择世界书、画风、AI 创造性、开局身份。
  MVP 大部分使用默认推荐。

预制开场：
  30-60 秒黑屏白字 + 动画卡，可跳过。

大地图 / 战略态势图：
  看到主城、黑暗区域、当前危机点、路线、悬浮任务。

战役节点 Briefing：
  点击危机节点后，先看敌潮特征、保护目标、可用材料和 NPC 在场情况。

现场应急研发页：
  玩家表达构想，生成 1 个试作方案卡，确认试作。

战斗加载 / 研发任务创建：
  创建研发倒计时，MVP 第一战推荐后台研发。

塔防战斗页：
  前 30 秒拖延，样品中途送达，底部热栏点亮，玩家部署样品。

战后结算 / 世界生长：
  战报、节点状态变化、样品表现、NPC 反馈、世界事件生长。

返回大地图：
  大地图状态更新，下一节点或正式研发线索出现。
```

MVP 范围说明：

- 第一版更像教学关，不覆盖完整策略层。
- 世界书自动演化只在短流程中做关键体现，不追求完整长期模拟。
- 暂不实现复杂多线防守、完整正式研发机构、完整技术树、多世界书切换、复杂经营系统。
- 后续时间允许时，在这条闭环上扩展世界书自动演化、多节点、多资产、正式研发、更多策略层。

## 10. 已确认：第一场战斗与第一个 AI 编译资产

第一场战斗目标：

```text
让玩家在危机中提出一个临时应对想法，并在战斗中看到它变成可用样品。
```

第一场结构：

```text
场景：
  第一个战役节点受到高速敌潮冲击。

问题：
  敌人移动快，基础防御很难留住它们。

玩家构想：
  我想做一个能拖慢影潮的临时装置。

试作方案：
  一个一次性 / 少量使用的减速陷阱样品。

战斗体验：
  样品在战斗中途送达，玩家部署后明显拖慢敌人，完成教学闭环。

战后反馈：
  样品有效但不稳定，获得正式研发线索。
```

演示段落：

```text
1. 大地图
   当前危机节点高亮，影潮逼近。

2. 节点 Briefing
   目标：守住节点核心，并保护一个小型资源 / 设施目标。
   敌人：高速影潮，低耐久但移动快。
   资源：有限材料，可做一次现场试作。

3. 现场应急研发
   玩家输入：我想做一个能拖慢影潮的临时装置。

4. 试作方案卡
   显示 1 个方案。
   名称由世界书生成。
   预期：敌人经过时短暂减速。
   材料：玩家投入少量灯芯 / 导线类材料。
   风险：效果可能不稳定。
   操作：确认试作。

5. 进入战斗
   前 30 秒没有样品，只能用基础手段拖延。
   显示世界内研发状态，例如“样品封装中”。

6. 样品送达
   底部热栏点亮样品 x2。
   玩家在路径转角部署。
   敌人经过后触发减速，出现 ring_pulse / aura_field / sprite_flash。

7. 战斗结束
   节点守住，但资源设施受损或有少量泄漏。

8. 战后结算
   显示节点状态变化、样品实战表现、暴露缺陷、NPC 反馈、正式研发线索，并返回大地图。
```

第一个 AI 编译资产：

```text
asset_kind: temporary_trap_sample
template_id: temporary_trap_sample
lifecycle_state: ephemeral
battle_availability: battle_hotbar
uses_per_battle: 2
```

推荐 `visual_recipes`：

```text
ring_pulse
aura_field
sprite_flash
```

底层 gameplay：

```text
触发：敌人经过陷阱格
效果：范围内敌人减速
持续：短
次数：2
风险：在特殊环境 / 敌人类型下效果下降
```

玩家侧显示：

```text
减速：中
持续：短
稳定性：偏低
次数：2
```

战后生长：

```text
如果样品触发成功：
  NPC 认为光幕干扰确实有效，解锁后续正式研发方向。

如果样品触发较差：
  NPC 发现影潮对某种频率适应很快，解锁改良材料 / 频率调校线索。
```
