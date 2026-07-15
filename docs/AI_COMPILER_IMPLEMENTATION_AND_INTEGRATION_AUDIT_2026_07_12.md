# AI 编译系统实现与接入审计（更新至 2026-07-15）

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
| 研发对象行为 ABI | 由候选 lowering 生成 | 白名单、数值裁剪、schema、包哈希复验 | 单体/范围/连锁伤害、触发陷阱、持续减速、落点支援可执行 | **真实闭环，能力集有限** |
| 研发对象图片/动画 | Agnes 生成对象本体并可基于首图修复 | 白底硬门禁、多模态审查、透明化、哈希发布；失败使用 reviewed fallback | 专属 icon/sprite 可随 ActivatedRuntimeBundle 进入战斗 | **真实图片闭环；动画待接** |
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

激活后，RuntimeActivationReceipt 为 `activated`；ActivatedRuntimeBundle 和 FeatureSnapshot 中出现同一个 `compiled_tower_blueprint_*` object ID，前端战斗行为可读取 `damage.radius_cells` 执行范围伤害。

后续真实闭环又生成并激活“折光观测塔”：首图带有烙死的战斗特效，自动审查拒绝后以首图为参考执行去特效修复，第二张通过审查、透明化和发布哈希复验。最终 `behavior_abi` 与 `media` 两个激活门均为 `passed`。现场 confirm 耗时约 107 秒，因此前端后台研发请求上限提高到 180 秒；超时、审查失败或后处理失败仍只降级媒体，不阻断已通过玩法模拟的对象。

2026-07-15 又执行了统一三对象真实烟测。方舟 `deepseek-v4-flash` 在一次报告中分别生成并激活连锁塔“光幕跳跃塔”、伤害减速陷阱“折光绊索”和伤害减速支援“折光迟滞脉冲”，总耗时 43.32 秒，三次 Provider 调用、三次 PromotionReport 和三次运行时变更全部通过。报告不保存原始提示词、原始响应、session/job 标识或密钥，已固化为 `examples/review_packs/live_compiler_showcase_report.v0.1.json`。

## 4. 本轮已修复

### P0：优质地图候选跨运行丢失

新增内容寻址缓存。缓存键绑定请求语义、参考图哈希、输出契约、生成 profile 和审查策略指纹；恢复时复验图片哈希和当前确定性门禁。缓存不保存 API key、原始 Provider body 或完整提示词。

旧报告可通过迁移工具重新校验后入库。真实 v2 证据已恢复 3 个通过候选；地形恢复烟测为 `provider_call_count=0`、`vision_review_call_count=0`。

### P0：真实候选使用了错误的模拟证据

Provider 候选现在必须先运行自身的确定性模拟。严重 flag 或“无伤害且效用过低”会生成 blocked PromotionReport，并让研发 job 失败；固定 mock DAG trace 不能替代真实候选模拟。

### P0：运行时 schema 门禁 fail-open

`jsonschema` 已加入部署依赖。依赖、validator class 或 schema 文件不可用时，运行时激活必须阻断；不能再把“无法校验”当成“零错误”。

### P0：提案效果与前端实战行为不一致

真实调用曾生成“文字说明包含范围伤害，但陷阱运行时只执行减速”的候选。当前对象类型提示会约束模型优先产出 ABI 可执行的效果组合；陷阱状态保留伤害与半径，并在首次触发时执行一次范围伤害，再进入持续减速阶段。模块测试和三对象真实烟测均覆盖该行为。

### P1：地图 worker 状态命名误导

地图视觉成功状态从 `runtime_activated` 改为 `visual_package_applied`。它表示节点视觉包已写入地图编译产物，不表示写入会话 `runtime_activations`。

## 5. 仍存在的问题

### 已修复：真实候选复用固定 mock compile 证据

真实 LLM 调用仍由 `live_asset_compile_service` 负责受控 Provider 边界，但 Provider 候选进入确认阶段后，已改走 `runtime_safe_candidate_validation` DAG：`load_candidate -> validate_candidate -> simulate -> score -> promotion -> summary`。固定 mock compile 只保留为无 Provider 候选时的确定性 fallback，不再作为真实候选的编译证明。RuntimePackage 的通用壳与 lowering 仍是后续可继续统一的边界。

### P1：Provider 调用仍占用单次 HTTP 请求

创建提案和确认研发仍分别在 HTTP 请求内等待文本、图片和视觉审查。前端会先进入战斗并保留后台 Promise，比赛版本可用；正式方案仍应把 confirm 改为立即返回 running job，由后台 worker 执行，并由前端轮询或事件流更新。

### P1：Provider fallback 运行期可观测性仍不足

文本 Provider 或候选校验失败会退回确定性方案；内部 metadata 有失败类型。新增的统一演示报告能明确区分 live、fallback、门禁结果与运行时变更，但常驻服务仍缺少统一 ops 日志和聚合指标。玩家侧不应看到 Provider 错误。

### P1：地图服务仍绑定三个预编译节点

地图编译器能够生成运行包，但 `map_runtime_service` 和 `map_render_plan_service` 仍以固定节点路径表为主。新地图要进入常规战役，需要 manifest/catalog 驱动的发现机制，而不是继续追加 Python 常量。

### P1：世界与剧情演化未形成玩家实时闭环

World Compiler 支持真实 Provider，但当前 `content/generated_worlds` 没有可用世界实例。剧情、NPC 反馈、世界变化和随机事件大多为确定性节点；它们服务玩法且可控，但不能宣称为实时 AI 生长。

### P2：Generation Scheduler 规模大于当前实际价值

Scheduler 已有授权、ledger、缓存、handoff 和 apply gate，但默认仍是 fixture/review-only。比赛剩余时间内不应继续横向扩展；只保留演示真实编译异步化所需的最短路径。

## 6. 剩余开发顺序

1. 冻结核心协议和大规模重构，完成浏览器完整流程、视觉、性能和失败 fallback 验收。
2. 用统一三对象报告和玩家侧工坊流程录制“真实编译并参与战斗”的双重证据。
3. 只修复会阻断演示的地图、音频、状态和交互问题，不再扩展第四类运行时对象。
4. 比赛后再把地图运行包改为 manifest/catalog 发现，并扩展真实世界实例和剧情生长链。
