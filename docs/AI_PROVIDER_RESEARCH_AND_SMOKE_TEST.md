# AI Provider 调研与烟测基线

Last updated: 2026-06-30

## 1. 目标

本项目会同时使用多个模型 provider。它们不应直接散落在业务代码里，而应先沉淀为统一的 Provider Adapter、模型能力表和额度保护规则。

当前 `.env` 中约定的 key 名称：

```text
AGNES_API_KEY
ARK_API_KEY
DEEPSEEK_API_KEY
GLM_API_KEY
GLM_API_KEY_FREE
```

文档、日志、测试输出都不能打印 API key 的真实值。

## 2. 接入原则

1. 所有模型调用都通过统一网关进入，游戏逻辑不直接依赖某个 SDK。
2. 免费 key 和主账户 key 必须显式区分，不能失败后静默 fallback 到付费账户。
3. 默认测试只做 dry-run；真实联网调用必须显式启用。
4. 图像和视频调用即使当前免费，也要按“会消耗额度或受限流影响”的资源处理。
5. 结构化资产编译优先使用 JSON / Tool Call / Schema 校验组合，不能直接信任自然语言输出。
6. 方舟 Coding Plan 必须使用 Coding Plan 专用 Base URL，不能误用普通 `/api/v3`。

## 3. Provider 速览

| Provider | 环境变量 | 主要用途 | 推荐接入方式 | 关键风险 |
|---|---|---|---|---|
| Agnes | `AGNES_API_KEY` | 免费文本、图像、视频、多模态原型 | OpenAI-compatible + 视频异步接口 | 免费策略和 RPM 可能变化 |
| 火山方舟 Coding Plan | `ARK_API_KEY` | 编码模型、开发辅助、可能的内部编译评审 | OpenAI-compatible `/api/coding/v3` 或 Anthropic-compatible `/api/coding` | 用错 Base URL 会产生额外费用 |
| DeepSeek | `DEEPSEEK_API_KEY` | 低成本文本、结构化内容、推理/非推理切换 | OpenAI-compatible | 旧模型别名有明确下线日期 |
| 智谱 GLM | `GLM_API_KEY` | 高质量文本、多模态、图像/视频能力 | `zai-sdk` / HTTP v4 | 主账户生成额度有限 |
| 智谱 GLM Free | `GLM_API_KEY_FREE` | 免费模型隔离账户 | `zai-sdk` / HTTP v4 | 免费模型也可能限流或占用账户配额 |
| CodeBuddy / 混元图像 | CodeBuddy 本地配置 | 比赛合规、开发期图像候选、离线素材生成 | CodeBuddy `ImageGen` tool | 当前实测可调用但遇到限流，暂不作为默认运行时主通道 |

## 4. Agnes

官方信息：

- 官方站点：[agnes-ai.com](https://agnes-ai.com/)
- 文档索引：[wiki.agnes-ai.com/llms.txt](https://wiki.agnes-ai.com/llms.txt)
- 控制台：[platform.agnes-ai.com](https://platform.agnes-ai.com)
- Base URL：`https://apihub.agnes-ai.com/v1`
- 鉴权：`Authorization: Bearer <AGNES_API_KEY>`

模型与接口：

| 类型 | 模型 | 接口 |
|---|---|---|
| 文本 / 多模态理解 | `agnes-2.0-flash` | `POST /chat/completions` |
| 图像生成 | `agnes-image-2.0-flash` | `POST /images/generations` |
| 图像生成 | `agnes-image-2.1-flash` | `POST /images/generations` |
| 视频生成 | `agnes-video-v2.0` | `POST /videos` 创建任务 |

视频结果查询：

```text
GET https://apihub.agnes-ai.com/agnesapi?video_id=<VIDEO_ID>
```

Agnes 官方资料显示核心模型当前长期免费，覆盖文本、图像、视频、多模态，但免费用户存在 RPM 限制。当前公开参考值包括文本 `20 RPM`、视频 `1 RPM`。生产前必须以控制台 Usage / Billing 和 [Token Plan](https://wiki.agnes-ai.com/en/docs/tokenplan.md) 为准。

## 5. 火山方舟 Coding Plan

官方信息：

- 快速开始：[火山方舟 Coding Plan 快速开始](https://www.volcengine.com/docs/82379/1928261)
- OpenAI 兼容工具接入：[OpenAI 兼容工具接入页](https://www.volcengine.com/docs/82379/2188959)
- Base URL 与鉴权：[Base URL 及鉴权](https://www.volcengine.com/docs/82379/1298459)

Coding Plan 必须使用专用 Base URL：

```text
OpenAI-compatible:   https://ark.cn-beijing.volces.com/api/coding/v3
Anthropic-compatible: https://ark.cn-beijing.volces.com/api/coding
```

不要使用：

```text
https://ark.cn-beijing.volces.com/api/v3
```

该普通数据面不会消耗 Coding Plan 额度，而会产生额外费用。

当前文档列出的 Model Name：

```text
doubao-seed-2.0-code
doubao-seed-2.0-pro
doubao-seed-2.0-lite
doubao-seed-code
minimax-m2.7
minimax-m3
glm-5.2
glm-latest
deepseek-v4-flash
deepseek-v4-pro
kimi-k2.6
kimi-k2.7-code
ark-code-latest
```

`ark-code-latest` 适合由控制台管理/切换模型；`Auto` 不是可直接配置的 Model Name。

模型列表查询是管控面 API `ListArkCodingPlanModel`，需要 HMAC-SHA256 签名，不应拿推理 Bearer key 直接请求。参考：[ListArkCodingPlanModel](https://www.volcengine.com/docs/82379/2546386)。

建议定位：

- 优先作为开发期编码、审查、脚手架辅助 provider。
- 若未来放入游戏内运行时，需要先确认 Coding Plan 的产品边界和费用规则。

## 6. DeepSeek

官方信息：

- 文档首页：[DeepSeek API Docs](https://api-docs.deepseek.com/zh-cn/)
- Chat Completion：[Create Chat Completion](https://api-docs.deepseek.com/api/create-chat-completion)
- 模型列表：[List Models](https://api-docs.deepseek.com/api/list-models)
- 价格：[Pricing](https://api-docs.deepseek.com/quick_start/pricing)

Base URL：

```text
OpenAI-compatible:    https://api.deepseek.com
Anthropic-compatible: https://api.deepseek.com/anthropic
```

当前主要模型：

```text
deepseek-v4-flash
deepseek-v4-pro
```

`deepseek-chat` 和 `deepseek-reasoner` 仍兼容，但将于 2026-07-24 15:59 UTC，也就是北京时间 2026-07-24 23:59 弃用。当前它们分别路由到 `deepseek-v4-flash` 的非思考 / 思考模式。

结构化输出：

- JSON mode 使用 `response_format={"type":"json_object"}`。
- prompt 中仍应明确要求输出 JSON。
- API reference 未显示普通响应支持 OpenAI 风格 `json_schema`。
- 更严格的 Tool Calls `strict: true` 属于 beta，需要使用 `https://api.deepseek.com/beta`。

价格策略：

- `deepseek-v4-flash` 适合作为低成本默认文本模型。
- `deepseek-v4-pro` 适合复杂推理、评审、较高质量内容。
- Context caching 默认开启，可以读取 `usage.prompt_cache_hit_tokens` / `usage.prompt_cache_miss_tokens` 观察缓存效果。

## 7. 智谱 GLM / Z.AI

官方信息：

- 国内文档：[智谱开放平台文档](https://docs.bigmodel.cn/)
- 快速开始：[Quick Start](https://docs.bigmodel.cn/cn/guide/start/quick-start)
- Python SDK：[zai-sdk Python](https://docs.bigmodel.cn/cn/guide/develop/python/introduction)
- 模型概览：[Model Overview](https://docs.bigmodel.cn/cn/guide/start/model-overview)
- Z.AI Pricing：[Pricing](https://docs.z.ai/guides/overview/pricing)

本项目使用新包 `zai-sdk`，不使用旧 `zhipuai` 包。

安装：

```bash
pip install zai-sdk
```

国内平台推荐客户端：

```python
from zai import ZhipuAiClient
```

默认/推荐国内 API 地址：

```text
https://open.bigmodel.cn/api/paas/v4/
```

项目内 key 路由建议：

```text
GLM_API_KEY       -> 主账户，高质量模型或付费生成
GLM_API_KEY_FREE  -> 免费模型隔离账户
```

当前重点模型：

| 类型 | 模型示例 | 备注 |
|---|---|---|
| 文本旗舰 | `glm-5.2` | 推荐旗舰，适合高质量编译/评审 |
| 免费文本 | `glm-4.7-flash`、`glm-4.5-flash`、`glm-4-flash-250414` | 免费状态以控制台和价格页为准 |
| 视觉理解 | `glm-5v-turbo`、`glm-4.6v-flash` | 可用于素材审查、截图理解 |
| 图像生成 | `glm-image`、`cogview-4-250304`、`cogview-3-flash` | `cogview-3-flash` 属于免费候选 |
| 视频生成 | `cogvideox-3`、`cogvideox-flash` | 视频应异步处理 |

不要用后缀简单判断是否免费。例如 `glm-4.7-flashx` 是收费模型，不等同于 `glm-4.7-flash`。

2026-06-30 已用 `glm-5v-turbo` 完成真实素材视觉审查闭环。当前项目内 profile：

```text
glm_5v_turbo        -> GLM_API_KEY
glmfree_4_6v_flash  -> GLM_API_KEY_FREE
agnes_multimodal_flash -> AGNES_API_KEY
```

`media.review_with_vision_guarded` 会把本地生成图片以内联图片输入发送给视觉模型，
输出 `media_vision_review_report.v0.1`。该报告用于检查可读文字、水印、主体漂移、
世界观语义和媒体角色匹配度，不进入玩家运行时包。

## 8. 建议的项目内 Provider 架构

建议后端逐步形成如下结构：

```text
backend/app/ai_gateway/
  adapters/
    agnes.py
    ark.py
    deepseek.py
    glm.py
  model_catalog.py
  task_policy.py
  quota_guard.py
  structured_output.py
  audit_log.py
```

本章主要描述玩家游玩时的运行时 AI provider 设置。开发期间可以复用同一套 provider adapter，也可以允许人类使用网页聊天生成内容，把返回结果下载后放入固定目录，再由本地导入器纳入内容管线。

核心接口：

```text
ProviderAdapter
  - chat(request) -> ChatResult
  - structured_chat(request, schema) -> StructuredResult
  - generate_image(request) -> ImageJob
  - generate_video(request) -> VideoJob
  - poll_job(job_id) -> JobResult
```

策略层不应只按 provider 路由，而应按任务路由：

| 任务 | 初期建议 |
|---|---|
| 玩家自然语言解析 | Agnes / DeepSeek Flash / GLM Free 低成本模型 |
| 防御塔蓝图结构化编译 | DeepSeek JSON mode / GLM 旗舰 |
| 蓝图规则评审 | DeepSeek Pro / GLM 旗舰 / 方舟编码模型 |
| 内容草稿生成 | Agnes / DeepSeek Flash / GLM Free |
| 世界书一致性审查 | 方舟 Coding Plan 内的 `deepseek-v4-pro` / `glm-5.2` 优先，DeepSeek 官方 API fallback |
| 世界书内容生长 | 方舟 Coding Plan 内的 `deepseek-v4-pro` / `deepseek-v4-flash` / `glm-5.2` 优先，按成本与质量切换 |
| 弱主线 / 长剧情节点生成 | 方舟 Coding Plan 内的 1M 上下文模型优先，必要时拆分成多轮 reviewed 候选 |
| 图像 prompt 扩写 | Agnes / GLM Free |
| 关键图像生成 | Agnes Image 优先，智谱主账户 fallback，智谱免费模型二级 fallback |
| 批量图像草稿 | Agnes Image 优先，智谱免费模型 fallback，必要时才用智谱主账户 |
| CodeBuddy 图像候选 | CodeBuddy `ImageGen` + `hunyuan-image-v3.0` | 主要用于开发期、比赛合规记录和离线素材候选 |
| 视频原型 | MVP 不进入核心闭环；开场动画预制，后续离线生成与 reviewed / locked |
| 开发编码辅助 | 方舟 Coding Plan |

### 8.0a 图像生成真实烟测：防御塔候选媒体包

2026-06-30 已授权对 `examples/compiled_assets/light_slow_tower.compiled_asset.json`
派生的视觉 prompt 进行真实图像 provider 调用。测试目标不是选最终美术，而是验证：

1. `CompiledAssetCandidate` 可以派生 `icon` / `tower_sprite` 两类视觉 prompt。
2. 图像 provider adapter 可以真实生成并下载图片。
3. 生成图片可以写入 `raw_media_sequence.v0.1`。
4. `raw_media_sequence` 可以通过媒体处理 DAG 进入 `published_media_manifest.v0.1`。
5. 最终 runtime-public manifest 不泄漏 provider 临时 URL、prompt、provider_profile 或本地路径。

本轮真实调用结果：

| Provider profile | 模型 | 输出尺寸 | 状态 | 主要观察 |
|---|---|---:|---|---|
| `agnes_image_flash` | `agnes-image-2.1-flash` | 1024x1024 | 通过 | 画面质量高，无明显水印；`tower_sprite` 更像战斗预览，仍带场景背景 |
| `glmfree_cogview_3_flash` | `cogview-3-flash` | 1024x1024 | 通过 | 塔体干净度较好，但存在“AI生成”水印；实际下载内容为 JPEG |
| `glm_image` | `glm-image` | 1280x1280 | 通过 | 可生成，但主题贴合度弱于 Agnes；存在水印；实际下载内容为 JPEG |

本地烟测产物：

```text
/tmp/live_asset_media_agnes/raw_media_sequence.v0.1.json
/tmp/live_asset_media_glmfree/raw_media_sequence.v0.1.json
/tmp/live_asset_media_glm/raw_media_sequence.v0.1.json

/tmp/live_asset_media_agnes_processed/mvp_live_asset_media_agnes_process/build_atlas__published_media_manifest.json
/tmp/live_asset_media_glmfree_processed/mvp_live_asset_media_glmfree_process/build_atlas__published_media_manifest.json
/tmp/live_asset_media_glm_processed/mvp_live_asset_media_glm_process/build_atlas__published_media_manifest.json
```

关键结论：

- Agnes 当前更适合做 MVP 默认图像 provider。
- GLM / GLMFree 已验证可接入，适合 fallback 或对照候选，但需要水印检测与裁切。
- 图像 provider 不一定按请求返回 PNG；adapter 不能固定使用 `.png` 扩展名，应按响应头或 magic bytes 归一化。
- `tower_sprite` prompt 需要进一步收紧为“可抠图的干净塔体”，另设 `battle_preview` / `animation_card` 承载带背景的演示图。
- 当前媒体处理节点仍是 stub。进入前端实用前，至少需要实现格式归一化、背景去除、裁切留白、锚点分配和水印检测。

### 8.0 运行时设置与离线导入

运行时设置：

- 面向玩家游玩过程。
- 由后端 `ai_gateway` 根据任务类型、模型能力、限流和 fallback 策略自动选择 provider。
- 结果写入生成日志，并作为 `generated` 候选进入审查流程。
- 适合玩家意图解析、蓝图候选生成、少量关键图像生成、世界状态驱动的内容候选。

离线导入：

- 面向开发期、内容制作期、团队协作和人工实验。
- 允许使用 ChatGPT 网页、Agnes 网页、智谱控制台或其他网页聊天生成内容。
- 允许把返回的 JSON / Markdown / 图片 / 视频下载后放入约定目录。
- 导入器负责解析、校验、登记和移动状态；导入内容不能跳过 reviewed / locked。

建议目录：

```text
content/import_inbox/
  chat_exports/    # 网页聊天下载的 Markdown / JSON / TXT
  manifests/       # 描述一组素材来源、prompt、模型、用途的 manifest
  images/          # 下载后的图片素材
  videos/          # 下载后的视频素材
  rejected/        # 解析失败或被人工拒绝的导入内容
```

导入最小流程：

```text
网页聊天 / 控制台生成
  -> 下载 JSON / Markdown / 图片 / 视频
  -> 放入 content/import_inbox
  -> import tool 解析 manifest 或文件
  -> Schema / 文件类型 / 来源信息校验
  -> generated 记录
  -> reviewed
  -> locked
```

导入 manifest 至少应记录：

- 来源 provider 或网页工具
- 模型名
- prompt 摘要
- 生成日期
- 目标用途
- 关联世界书 / 节点 / NPC / 蓝图
- 原始文件路径
- 人工备注

manifest 草案：

```json
{
  "source": {
    "type": "web_chat",
    "provider": "chatgpt",
    "model": "unknown",
    "generated_at": "2026-06-28",
    "conversation_url": ""
  },
  "target": {
    "content_type": "worldbook_event",
    "worldbook_id": "long_night_lanterns",
    "node_id": "",
    "npc_id": "",
    "blueprint_id": ""
  },
  "files": [
    {
      "path": "content/import_inbox/chat_exports/example.md",
      "kind": "markdown",
      "role": "source_text"
    }
  ],
  "prompt_summary": "",
  "human_notes": "",
  "intended_lifecycle_state": "generated"
}
```

### 8.1 世界书与长上下文任务路由

世界书、弱主线、NPC 关系网、资源体系、事件池、材料与道具设定这类任务，输入往往包含：

- 基础世界书
- 已锁定内容注册表
- 当前节点和战斗结果
- NPC 记忆与阵营状态
- 可用模块库
- 禁用设定与风格约束
- 历史生成记录和审查意见

这类任务应优先使用长上下文模型，而不是为了省 token 过早压缩上下文。当前推荐顺序：

| 优先级 | 通道 | 模型 | 用途 |
|---:|---|---|---|
| 1 | 方舟 Coding Plan | `deepseek-v4-pro` | 世界书一致性审查、复杂设定冲突检查、高质量内容生长 |
| 2 | 方舟 Coding Plan | `glm-5.2` | 长上下文综合、中文叙事质量、设定润色与结构化整理 |
| 3 | 方舟 Coding Plan | `deepseek-v4-flash` | 大批量候选生成、较低成本预处理、草稿扩展 |
| 4 | 方舟 Coding Plan | `kimi-k2.6` | 世界书推理、叙事生长、复杂方案评审候选 |
| 5 | 方舟 Coding Plan | `kimi-k2.7-code` | 开发期编译器规则、Schema、DAG 节点、结构化资产转换候选 |
| 6 | DeepSeek 官方 API | `deepseek-v4-pro` | 方舟不可用、限流、套餐策略变化时的质量 fallback |
| 7 | DeepSeek 官方 API | `deepseek-v4-flash` | 方舟不可用时的低成本 fallback |

运行时策略：

1. 世界书长上下文任务默认走 `ARK_API_KEY` 和 `https://ark.cn-beijing.volces.com/api/coding/v3`。
2. 方舟返回限流、模型不可用、套餐策略变化、或明确不支持所需参数时，再切到 `DEEPSEEK_API_KEY`。
3. fallback 必须记录在 `AI_GENERATION_LOG`，包括原 provider、目标 provider、原因、模型名、输入摘要和输出摘要。
4. 对世界书内容生长，模型输出仍然只能进入 `generated` 状态，必须经过 reviewed / locked 流程。
5. 对需要严格 JSON 的任务，方舟某些模型可能不支持 `response_format=json_object`，应优先使用 prompt-only JSON + 本地 JSON parser + Schema 校验；如果失败，再切 DeepSeek 官方 JSON mode。
6. Kimi 系列在方舟 Coding Plan 中已验证文本和 JSON 输出可用；运行时 artifact 只允许读取 `message.content`，不得保存 `reasoning_content`。

### 8.2 图像生成任务路由

图像生成默认优先走 Agnes。当前 Agnes 图像接口已经实测可用，且适合作为 MVP 阶段的默认图像生成通道。CodeBuddy 配置中的 `textToImageModel: hunyuan-image-v3.0` 说明它也可以作为图像生成候选，但当前更适合开发期和比赛合规场景，不应在限流、权限和产物缓存都稳定前直接替代运行时默认链路。

图像任务建议分两类：

| 任务类型 | 路由顺序 | 说明 |
|---|---|---|
| 关键用户触发图像 | Agnes Image -> 智谱主账户 `glm-image` / `cogview-4` -> 智谱免费图像模型 | 用于可能进入 locked 内容、展示给玩家、路演截图或重要资产候选的图像 |
| 批量草稿 / prompt 试错 | Agnes Image -> 智谱免费图像模型 -> 智谱主账户 | 用于大量候选、风格探索、低风险素材草稿 |
| 比赛 / 开发期离线图像 | CodeBuddy `ImageGen` + `hunyuan-image-v3.0` -> Agnes Image -> 智谱免费图像模型 | 用于证明 CodeBuddy 参与、生成候选图标/立绘/背景草稿；结果仍需 reviewed / locked |
| 图像 prompt 扩写 | Agnes 文本 / GLM Free 文本 -> 方舟长上下文模型按需审查 | prompt 扩写本身不应直接消耗高价值图像生成次数 |

路由规则：

1. Agnes 作为默认图像 provider。
2. 智谱主账户的三百多次生成调用应留给关键资产、fallback 质量兜底和路演材料。
3. 智谱免费模型可作为二级 fallback，也可用于低价值批量草稿。
4. CodeBuddy / 混元图像作为候选通道，优先用于开发期离线素材、比赛合规记录、或 Agnes / GLM 都不合适时的人工触发。
5. fallback 必须记录原因，例如 Agnes 限流、接口失败、图像质量不可用、内容安全拒绝、结果 URL 失效、CodeBuddy ImageGen 限流。
6. 生成结果不能直接成为正式资产，应进入 `generated -> reviewed -> locked` 流程。
7. CodeBuddy ImageGen 当前建议由 `glm-5.1` 驱动，并用 `-y` 或权限配置允许工具执行；实测 `deepseek-v4-flash` 不稳定触发图像工具。

2026-06-30 媒体 repair loop 发现：Agnes 对某些过度负面的修复 prompt 会返回
`content_policy_violation`。因此 repair plan 可以保存完整诊断，但发送到图像 provider 的 prompt
必须压缩为更短、更正向、更安全的视觉描述，例如“镜片装置、灯光环、暗雾、无文字、无 logo”，
不要把视觉审查报告原文直接拼进图像 prompt。

`tools/media/image_provider.py` 已补充 HTTPError body 捕获，便于区分普通网络错误、参数错误和
provider 内容策略拒绝。

CodeBuddy ImageGen 非交互调用示例：

```bash
codebuddy -p -y --output-format json \
  --model glm-5.1 \
  --text-to-image-model hunyuan-image-v3.0 \
  --allowedTools ImageGen \
  --max-turns 8 \
  "请调用 ImageGen 工具生成一张简单的 2D 塔防炮塔图标，白色背景，512x512，medium quality。请把 output_dir 设置为 /tmp/codebuddy-image-test。不要生成 SVG 或代码。完成后只返回图片 URL 或文件路径。"
```

### 8.3 视频生成与过场动画策略

MVP 阶段不建议把视频生成放入核心可玩闭环。视频生成延迟、结果不确定性、素材缓存和审查成本都比图像高，容易拖慢塔防主循环。

MVP 建议：

| 场景 | 策略 |
|---|---|
| 开场动画 | 预制一段，可以由外部工具或视频模型离线生成后人工挑选 |
| 节点剧情 | 使用动画卡、2D 立绘、视差背景、轻量粒子、镜头推拉和文字演出 |
| 战后总结 | 使用静态图 + UI 动效 + 日志文本，不实时生成视频 |
| 特殊事件 | 先做动画卡模板，后续再考虑离线生成短视频 |

后续版本可以引入视频模型，但应作为离线内容管线：

```text
prompt / 参考图
  -> 视频任务提交
  -> 轮询结果
  -> 下载 / 缓存到项目侧存储
  -> 人工或 AI 审查
  -> locked 后进入游戏
```

图生视频、参考帧视频、素材再加工通常需要公网可访问图片 URL。本地路径不能直接传给远程 provider。开发期可以用临时公网 URL 调试，生产期应使用对象存储和短期签名 URL。

## 9. 烟测策略

仓库提供一个默认不联网的脚本：

```bash
python3 tools/provider_smoke_check.py --provider all --mode dry
```

脚本的 token 设置只是任务预算，不代表模型上下文长度或最大输出上限。现在许多模型已经支持很长上下文，部分模型的最大输出也远高于普通烟测需要。项目里应把三个概念分开：

```text
模型能力上限：provider / model catalog 记录，例如 context window、max output tokens。
任务输出预算：按意图解析、资产编译、评审、世界书生成等任务配置。
烟测预算：只用于确认接口、鉴权、结构化输出和异步任务流程可用。
```

脚本当前提供 `--budget` 预设，也可以用 `--max-tokens` 显式覆盖：

| 预设 | 输出预算 | 用途 |
|---|---:|---|
| `smoke` | 4096 | 默认烟测，不容易被 reasoning 截断 |
| `intent` | 4096 | 玩家意图解析 |
| `asset` | 8192 | 防御塔 / 道具蓝图编译 |
| `review` | 16384 | 蓝图评审、规则解释、平衡说明 |
| `world` | 32768 | 世界书内容生长、剧情节点生成 |
| `large` | 65536 | 长文档、批量内容、较长审查 |

如果某个模型明确支持更高输出，例如 128k 级别输出，直接使用：

```bash
python3 tools/provider_smoke_check.py --provider glm --mode structured --live --max-tokens 128000
```

建议初期任务级输出预算：

| 任务 | 建议输出预算 |
|---|---|
| 连通性 smoke test | 4096 |
| 玩家意图解析 | 4096 |
| 防御塔 / 道具蓝图编译 | 8192 |
| 蓝图评审 / 平衡解释 | 16384 |
| 世界书内容生长 | 32768+ |
| 剧情节点 / 事件批量生成 | 32768-128000，按模型能力和任务拆分决定 |

真实联网调用必须显式加 `--live`。建议顺序：

```bash
# 只确认环境变量和计划调用，不联网
python3 tools/provider_smoke_check.py --provider all --mode dry

# 只读模型列表，当前主要支持 DeepSeek
python3 tools/provider_smoke_check.py --provider deepseek --mode models --live

# 文本生成，每次只选一个 provider
python3 tools/provider_smoke_check.py --provider agnes --mode chat --live
python3 tools/provider_smoke_check.py --provider deepseek --mode chat --live
python3 tools/provider_smoke_check.py --provider ark --mode chat --live
python3 tools/provider_smoke_check.py --provider glm --mode chat --live
python3 tools/provider_smoke_check.py --provider glmfree --mode chat --live

# 贴近项目核心的结构化资产编译
python3 tools/provider_smoke_check.py --provider deepseek --mode structured --live
python3 tools/provider_smoke_check.py --provider glm --mode structured --live
```

图像和视频不建议放入自动 CI 烟测。它们更适合手动触发，并把任务 ID、结果 URL、耗时、控制台用量写入 `AI_GENERATION_LOG`。

```bash
python3 tools/provider_smoke_check.py --provider agnes --mode image --live
python3 tools/provider_smoke_check.py --provider glmfree --mode image --live
python3 tools/provider_smoke_check.py --provider agnes --mode video --live --request-timeout 240
python3 tools/provider_smoke_check.py --provider glmfree --mode video --live
python3 tools/provider_smoke_check.py --provider glmfree --mode job --live --job-id <TASK_ID>
```

## 10. 媒体资产 URL 策略

文本生图和文本生视频可以直接提交 prompt。图生视频、参考帧、素材再加工、视觉理解等流程通常需要图片 URL，不能直接传本地路径。

本项目建议：

1. 开发期优先使用对象存储或临时公网 URL，不把本地绝对路径传给 provider。
2. 生产期使用腾讯云 COS、Cloudflare R2、S3 兼容存储等对象存储，生成短期签名 URL。
3. 只有在 provider 明确支持 base64 / data URL 时，才直接传 base64；否则优先公网 URL。
4. Cloudflare Tunnel、ngrok、Tailscale Funnel 等只适合开发临时调试，不作为正式素材管线。
5. 所有生成结果应缓存到项目侧存储，不能只依赖 provider 返回的临时 URL。

## 11. 真实烟测记录

测试日期：2026-06-28

所有测试均未打印 API key。真实调用由 `--live` 显式触发。

### 11.1 文本连通性

| Provider | 模型 | 结果 | 备注 |
|---|---|---|---|
| Agnes | `agnes-2.0-flash` | 成功 | OpenAI-compatible chat 可用 |
| DeepSeek | `deepseek-v4-flash` | 成功 | usage 返回 cache hit/miss 信息 |
| DeepSeek | `deepseek-v4-pro` | 成功 | `/models` 返回 `deepseek-v4-flash` 和 `deepseek-v4-pro` |
| 火山方舟 Coding Plan | `doubao-seed-2.0-code` | 成功 | 返回 `reasoning_content`，输出预算不能设太低 |
| 智谱主账户 | `glm-5.2` | 成功 | 修正 key 后可用；`thinking.disabled` 后正文正常 |
| 智谱免费账户 | `glm-4.7-flash` | 成功 | 默认会消耗 reasoning tokens；建议文本烟测关闭 thinking |
| 方舟 Coding Plan | `deepseek-v4-pro` | 成功 | 作为方舟内长上下文候选模型可调用 |
| 方舟 Coding Plan | `deepseek-v4-flash` | 成功 | 作为方舟内低成本长上下文候选模型可调用 |
| 方舟 Coding Plan | `glm-5.2` | 成功 | 作为方舟内长上下文候选模型可调用，但会返回较多 reasoning tokens |

### 11.2 结构化资产编译

测试任务：把“用灯光减速敌人、但会消耗额外电力的防御塔”编译为 JSON 候选。

| Provider | 模型 | `response_format=json_object` | 结果 |
|---|---|---|---|
| Agnes | `agnes-2.0-flash` | 支持 | 成功返回合法 JSON |
| DeepSeek | `deepseek-v4-flash` | 支持 | 成功返回合法 JSON |
| 火山方舟 Coding Plan | `doubao-seed-2.0-code` | 不支持 | API 返回 `json_object is not supported by this model`；prompt-only JSON 可用 |
| 火山方舟 Coding Plan | `deepseek-v4-pro` | 不支持 | `response_format=json_object` 不支持；prompt-only JSON 可用 |
| 火山方舟 Coding Plan | `deepseek-v4-flash` | 不支持 | `response_format=json_object` 不支持；prompt-only JSON 可用 |
| 火山方舟 Coding Plan | `glm-5.2` | 支持 | 成功返回 JSON，但仍应经过本地 parser / Schema 校验 |
| 智谱主账户 | `glm-5.2` | 支持 | 成功返回合法 JSON |
| 智谱免费账户 | `glm-4.7-flash` | 未稳定验证 | 一次返回 429 模型繁忙，需稍后重试 |

### 11.3 图像与视频

| Provider | 模型 | 结果 | 备注 |
|---|---|---|---|
| Agnes | `agnes-image-2.1-flash` | 成功 | 不接受 `response_format` 参数；去掉后返回图片 URL |
| 智谱免费账户 | `cogview-3-flash` | 成功 | 返回带水印的临时图片 URL |
| 智谱主账户 | `glm-image` | 成功 | 返回带水印的临时图片 URL |
| 智谱免费账户 | `cogvideox-flash` | 成功 | 异步提交与查询均成功，返回 mp4 与封面临时 URL |
| 智谱主账户 | `cogvideox-3` | 成功 | 异步提交与查询均成功，返回 mp4 与封面临时 URL |
| Agnes | `agnes-video-v2.0` | 部分成功 | 提交成功，查询接口成功；最近一次查询状态为 `in_progress`，进度 30% |
| CodeBuddy ImageGen | `hunyuan-image-v3.0` | 可调用但被限流 | `glm-5.1` 能发现并调用 ImageGen；需 `-y` 或允许 `DeferExecuteTool`；最近一次返回 `Too many requests` |

## 12. Guarded LLM WorldStateDelta 实现说明

本轮实现新增了一条受控的 LLM 世界状态 delta 生成路径，位于 `tools/llm/`。

### 12.1 新增文件

- `tools/llm/__init__.py` — 空包初始化。
- `tools/llm/adapter.py` — 最小 LLM adapter，支持 OpenAI-compatible chat completions。
  - 7 个 provider profile：`ark_deepseek_v4_flash`、`ark_deepseek_v4_pro`、`ark_glm_5_2`、`ark_kimi_k2_6`、`ark_kimi_k2_7_code`、`deepseek_v4_flash`、`deepseek_v4_pro`。
  - `load_dotenv()` 从 `.env` 加载环境变量，日志只显示 env key 名称。
  - 方舟 `deepseek-v4-*` profile 默认不发送 `response_format=json_object`，改走 prompt-only JSON + 本地 JSON parser + Schema 校验；`ark_glm_5_2` 与 DeepSeek 官方 profile 可发送 JSON mode。
  - `extract_json()` 支持直接 JSON、markdown fenced JSON、文本中第一个 JSON object。
  - `chat_completion()` 使用 stdlib `urllib`，无额外依赖。
- `tools/llm/generate_world_delta.py` — CLI 工具。
  - 输入：`--run-world-state`、`--battle-result`、`--session-context`、`--output`。
  - 参数：`--provider-profile`、`--max-tokens`、`--request-timeout`、`--live`。
  - 没有 `--live` 时拒绝联网并返回非 0 退出码。
  - live 模式下调用 provider，提取 JSON，执行 `validate_with_jsonschema` + `validate_world_delta`。
  - 校验不通过则退出非 0，并将失败 artifact 写入 `/tmp/failed_delta_*.json`。
- `tools/llm/world_delta_prompt.py` — WorldStateDelta 共享提示词与输入压缩器，CLI 和 AssetGraph live 节点共用同一套顶层字段、operation 模板和禁止形态约束。

### 12.2 新增 AssetGraph 节点

- `tools/asset_graph/nodes.py` 新增 `node_world_state_build_delta_with_llm_guarded`。
  - node_type：`world_state.build_delta_with_llm_guarded`。
  - inputs：`run_world_state`、`battle_result`、`session_context`。
  - params：`allow_live_provider_call`（必须为 true）、`provider_profile`（默认 `ark_deepseek_v4_flash`）、`max_tokens`（默认 4096）、`request_timeout`（默认 90）。
  - `allow_live_provider_call` 不为 true 时抛出 NodeError，要求显式开启。
  - 调用 provider 后执行 JSON 提取 + 双重校验（jsonschema + 规则校验）。
  - 输出 artifact kind 为 `world_state_delta`，不含 provider/model/raw_prompt 字段。
- `shared/asset_graph/node_registry.v0.1.json` 注册该节点，`calls_provider: true`，`modes: ["live"]`。

### 12.3 新增示例 workflow

- `examples/workflows/mvp_live_world_delta_guarded.workflow.json`
  - mode 为 `live`。
  - 加载 demo state / battle result / session context。
  - 调用 `world_state.build_delta_with_llm_guarded`（`allow_live_provider_call: true`）。
  - 调用 `world_state.apply_delta` 应用 delta。
  - 文档强调该 workflow 会真实联网，由人工显式执行。

### 12.4 安全与隐私

- 本实现只在显式 live 路径读取 `.env` / 环境变量中的 API key，且不记录、不打印、不写入 artifact；日志只显示 env key 名称。
- 默认 CLI 路径不调用真实 provider；只有 `--live` 或 AssetGraph 中 `allow_live_provider_call=true` 的 live workflow 才允许联网。
- 输出 artifact 不包含 provider/model/raw_prompt/full_trace/raw_json/api_key/secret/unreviewed_content。

### 12.5 Guarded LLM 资产候选编译路径

本轮新增 `CompiledAssetCandidate` 的 live 编译路径：

- `tools/llm/asset_candidate_prompt.py` — 共享提示词与输入压缩器，明确候选顶层结构、生命周期、资产类型、effect registry 白名单、provenance 结构和禁止字段。
- `tools/llm/generate_asset_candidate.py` — CLI 工具。默认拒绝联网；显式 `--live` 后调用 provider，提取 JSON，并用 `validate_asset_candidate.validate()` 校验。
- `asset.compile_with_llm_guarded` — AssetGraph live 节点。必须设置 `allow_live_provider_call: true`，输出前必须通过 effect registry 校验。
- `examples/workflows/mvp_live_asset_compile_guarded.workflow.json` — live workflow：proposal -> proposal validation -> LLM compile -> candidate validation -> mock simulation -> summary。

首次真实烟测结果：

| 通道 | 模型 | 结果 | 说明 |
|---|---|---|---|
| 方舟 Coding Plan | `deepseek-v4-flash` | 成功 | 生成 `tower_blueprint`，effect 为 `slow` / `aura_buff` / `power_cost`，通过候选校验和 mock simulation |
| DeepSeek 官方 | `deepseek-v4-flash` | 成功 | 生成 `tower_blueprint`，effect 为 `slow` / `power_cost`，通过候选校验和 mock simulation |
| AssetGraph live workflow | 方舟 `deepseek-v4-flash` | 成功 | `source.load_json -> proposal.validate -> asset.compile_with_llm_guarded -> asset.validate_candidate -> asset.simulate_candidate -> report.pipeline_summary` 全部 passed |
| 方舟 Coding Plan | `kimi-k2.6` | 成功 | 文本 chat 可用；较低 `max_tokens` 时可能只返回 `reasoning_content` 并被截断，正常上限下返回 `message.content` |
| 方舟 Coding Plan | `kimi-k2.6` | 成功 | `response_format=json_object` 结构化输出可用，返回可解析 JSON |
| 方舟 Coding Plan | `kimi-k2.7-code` | 成功 | `response_format=json_object` 结构化输出可用，适合作为开发期/编译器规则候选模型 |
| AssetGraph live workflow | 方舟 `kimi-k2.6` | 成功 | `mvp_live_asset_compile_kimi_guarded.workflow.json` 全节点 passed；生成 `asset_luminous_slow_tower`，评分 `72.9`，建议进入 `generate_media` |

两个候选都被模拟器标记为 `pure_control_requires_damage_partner`，说明当前提案会产出“控场但不能独立击杀”的资产。这类缺陷可以进入玩家侧的世界内反馈，例如 NPC 评审、样品限制、需要搭配伤害塔等，而不是展示 provider/schema 等技术信息。

## 13. 待确认问题

1. Agnes 的 `GET /v1/models` 是否稳定可用。官方文档未明确承诺，不能作为生产依赖。
2. 方舟 Coding Plan 已验证可调用长上下文候选模型；仍需确认长期作为游戏运行时主通道时的套餐边界、并发限制、日志归因和费用策略。
3. 方舟 Coding Plan 暴露的 `kimi-k2.6` / `kimi-k2.7-code` 已验证文本与 JSON 调用，但是否支持图片输入仍未确认；视觉素材审查暂不依赖 Kimi。
4. 智谱免费模型在两个账户中的真实限流、每日额度和账单延迟。
5. 图像/视频生成结果的存储策略：本地缓存、对象存储、还是只保存远程 URL。
6. 资产编译的主结构化模型应以 DeepSeek JSON mode、GLM 旗舰，还是双模型交叉评审为第一版。
7. CodeBuddy ImageGen / `hunyuan-image-v3.0` 的真实限流、稳定 output_dir 行为和是否适合进入运行时 fallback。
