# AI 编译系统实现与接入审计（2026-07-12）

## 1. 审计结论

当前系统不是“只有概念和 mock”，但也还不是所有内容都由同一条 AI 编译链实时生成。

已经形成真实玩家闭环的是：

`玩家构想 -> 文本模型结构化候选 -> 白名单校验 -> 真实候选模拟 -> 晋升报告 -> RuntimePackage -> 显式激活 -> ActivatedRuntimeBundle -> 前端工具栏与战斗行为`

地图、世界、剧情和 Generation Scheduler 处于不同成熟度，不能统一宣称“已实时接入”。比赛演示应明确区分：

- **玩家实时编译**：研发对象的结构、数值、效果和行为。
- **开发期 AI 编译**：地图视觉与世界实例，可真实调用 Provider，但运行时通常消费预编译并审核过的包。
- **确定性受控生长**：当前剧情、结算变化、战役路由和随机事件的大部分实现。
- **架构证据原型**：Generation Scheduler 的大量接口与 ledger，目前主要是 fixture/review-only。

## 2. 接入矩阵

| 对象/子系统 | 真实生成 | 校验与晋升 | 运行时消费 | 当前判断 |
| --- | --- | --- | --- | --- |
| 玩家研发塔/陷阱/支援 | 已接真实文本 Provider | 已接候选校验、真实候选模拟、PromotionReport、激活门禁 | 已进入前端 hotbar 与战斗模拟 | **真实闭环** |
| 研发对象行为 ABI | 由候选降低生成 | 白名单、数值裁剪、schema、包哈希复验 | 伤害、范围伤害、减速、范围支援可执行 | **真实闭环，能力集有限** |
| 研发对象图片/动画 | 候选只生成视觉提示 | 当前使用 reviewed fallback media | 前端能显示，但不是本次实时生成图 | **半闭环** |
| 战斗地图逻辑 | MapRuntimePackage/路径/塔位编译器已实现 | 结构、语义和对齐门禁已实现 | 三个 MVP 节点消费预编译包 | **开发期编译** |
| 地图视觉 | Agnes 生图、视觉审查、修复重试已实现 | reviewed staging、组件 fallback、候选缓存已实现 | 默认消费预编译审核包 | **开发期真实闭环，非玩家实时** |
| 世界实例 | World Compiler 支持真实 Provider 和地图编译 | 有候选 schema 与 manifest | Catalog 可加载已编译世界 | **工具链已接，当前无已生成世界实例** |
| 世界书/剧情/事件 | 多数节点为确定性模板和状态投影 | 有文本安全与世界变化结构门禁 | 能进入开场、对话、结算和地图进度 | **受控原型** |
| Generation Scheduler | Provider 边界、授权、ledger、apply gate 齐全 | 大量 review-only/fixture 证据 | 可演示调度状态，非默认真实生成器 | **架构原型** |
| 前端 FeatureSnapshot | 不负责生成 | 只消费 ActivatedRuntimeBundle | 战斗对象已动态投影；地图节点主要来自静态目录和进度解锁 | **部分动态** |

## 3. 已验证的真实闭环

本轮使用 `ark_deepseek_v4_flash` 真实生成“灯灰爆鸣塔”，Provider 返回：

- 候选 ID：`asset_lantern_ash_burst_tower`
- 类型：`tower_blueprint`
- 效果：范围伤害 `80`
- 原始范围：`80` 像素式单位，经 ABI 降低为约 `1.67` 格
- 原始射程：`160`，经 ABI 降低为约 `3.33` 格

真实候选随后通过独立模拟：估算 DPS `88`，无漏失，存在 `high_cost_efficiency` 复核警告但无阻断项。PromotionReport 的 `simulation_gate.report_ref` 指向该候选自己的 `live_candidate_simulation_report.v0.1.json`，不再借用固定 mock workflow 的模拟。

激活后，RuntimeActivationReceipt 为 `activated`；ActivatedRuntimeBundle 和 FeatureSnapshot 中出现同一个 `compiled_tower_blueprint_*` object ID，前端战斗行为可读取 `damage.radius_cells` 执行范围伤害。媒体门禁诚实标记为 `degraded`，因为仍使用审核过的塔图 fallback。

## 4. 本轮已修复

### P0：优质地图候选跨运行丢失

新增内容寻址缓存。缓存键绑定请求语义、参考图哈希、输出契约、生成 profile 和审查策略指纹；恢复时复验图片哈希和当前确定性门禁。缓存不保存 API key、原始 Provider body 或完整提示词。

旧报告可通过迁移工具重新校验后入库。真实 v2 证据已恢复 3 个通过候选；地形恢复烟测为 `provider_call_count=0`、`vision_review_call_count=0`。

### P0：真实候选使用了错误的模拟证据

Provider 候选现在必须先运行自身的确定性模拟。严重 flag 或“无伤害且效用过低”会生成 blocked PromotionReport，并让研发 job 失败；固定 mock DAG trace 不能替代真实候选模拟。

### P0：运行时 schema 门禁 fail-open

`jsonschema` 已加入部署依赖。依赖、validator class 或 schema 文件不可用时，运行时激活必须阻断；不能再把“无法校验”当成“零错误”。

### P1：地图 worker 状态命名误导

地图视觉成功状态从 `runtime_activated` 改为 `visual_package_applied`。它表示节点视觉包已写入地图编译产物，不表示写入会话 `runtime_activations`。

## 5. 仍存在的问题

### P0/P1：玩家实时编译尚未生成专属视觉

文本候选已决定名称、类型和行为，但 icon/sprite 仍使用 reviewed fallback。下一步应在研发倒计时期间异步生成视觉候选；超时或审查失败继续使用 fallback，不阻断玩法。

### P1：玩家研发并未完全走统一 AssetGraph

真实 LLM 调用发生在 `live_asset_compile_service`；确认阶段再运行两个确定性 workflow，并对产物做降低。行为结果已经统一，但编排、trace 和模拟仍有两套入口。MVP 后应把真实候选生成与模拟封装成正式 DAG 节点，删除“固定 mock compile 作为真实编译证明”的语义。

### P1：同步 Provider 调用影响交互延迟

创建提案会在 HTTP 请求内等待文本模型，最长可达配置超时。比赛版本可接受短暂等待，但正式方案应返回研发 job，后台执行，并由前端轮询或事件流更新。

### P1：Provider fallback 可观测性不足

文本 Provider 或候选校验失败会退回确定性方案；内部 metadata 有失败类型，但缺少统一 ops 日志和指标。玩家侧不应看到 Provider 错误，Studio/演示证据必须能区分 live 与 fallback。

### P1：地图服务仍绑定三个预编译节点

地图编译器能够生成运行包，但 `map_runtime_service` 和 `map_render_plan_service` 仍以固定节点路径表为主。新地图要进入常规战役，需要 manifest/catalog 驱动的发现机制，而不是继续追加 Python 常量。

### P1：世界与剧情演化未形成玩家实时闭环

World Compiler 支持真实 Provider，但当前 `content/generated_worlds` 没有可用世界实例。剧情、NPC 反馈、世界变化和随机事件大多为确定性节点；它们服务玩法且可控，但不能宣称为实时 AI 生长。

### P2：Generation Scheduler 规模大于当前实际价值

Scheduler 已有授权、ledger、缓存、handoff 和 apply gate，但默认仍是 fixture/review-only。比赛剩余时间内不应继续横向扩展；只保留演示真实编译异步化所需的最短路径。

## 6. 剩余开发顺序

1. 给玩家研发补“异步视觉生成 + 超时 fallback”，并在前端显示本次候选的专属图标或明确的封装中状态。
2. 把地图运行包服务改为 manifest/catalog 发现，先支持当前三个节点和一个新编译节点。
3. 用真实 Provider 编译一个额外世界实例，完整验收 Catalog、开场、大地图、首关和研发对象。
4. 只选一条剧情生长链接入真实 LLM：战后世界事件或下一节点任务，不同时铺开全部叙事对象。
5. 最后做浏览器完整流程、视觉、性能和失败 fallback 验收。
