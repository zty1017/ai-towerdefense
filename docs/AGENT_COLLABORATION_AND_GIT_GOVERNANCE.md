# AI 协作与 Git 治理

Last updated: 2026-07-13

## 1. 基本原则

主会话是项目大脑，不是施工日志。

主代理负责：

- 架构与产品方向
- 任务拆分
- 子代理 / CodeBuddy / 人类队友委派
- Git 分支与 worktree 管理
- 集成审查
- 合并冲突处理
- 验收与发布判断
- 事实源文档维护

实现工作应尽量交给：

- CodeBuddy
- OpenCode headless
- 子代理 / Codex worker
- 人类队友
- 独立 worktree 中的 worker

主代理可以审查和做小范围修补，但不应长期陷入底层实现细节。

比赛协作工具优先级：

```text
CodeBuddy 优先
  -> OpenCode headless 作为自动化候选
  -> Codex 用于高难度任务、架构兜底、集成审查和 Git 合并
```

主代理默认不直接承担普通实现任务，除非任务很小、需要快速修补，或其他工具无法完成。

### 当前冲刺覆盖规则

以下规则覆盖本文后部较早的模型清单和调用建议：

- CodeBuddy 当前只使用免费 `hy3`；每个边界清晰任务先尝试一次，遇到 `429` 或不可用立即回退，不等待额度恢复。
- OpenCode 当前允许：`opencode/big-pickle`、`opencode/deepseek-v4-flash-free`、`opencode/hy3-free`、`opencode/mimo-v2.5-free`、`zhipuai-coding-plan/glm-5.2`、`deepseek/deepseek-v4-flash`、`deepseek/deepseek-v4-pro`。
- 中低难度任务优先 CodeBuddy `hy3`，不可用时使用 OpenCode 免费模型；中高难度任务使用 `zhipuai-coding-plan/glm-5.2` 或 DeepSeek；极难、跨模块和高风险任务允许 Codex headless 在隔离 worktree 中执行。
- 所有实现 worker 都在从 `develop` 派生的 `task/*` 或 `experiment/*` worktree 中工作；`main` 只做稳定展示与阶段冻结。
- 外部 agent 可以读取和修改隔离 task worktree，但不得读取或修改 `.env`，不得提交密钥、原始 provider 响应或未审查候选资产。
- 当前 OpenCode CLI 以工作目录作为项目目录，最小调用形式为 `cd <worktree> && opencode run -m <model> "<task>"`；不要依赖旧文档中的 `--dir`、`--format` 或过期 `volcengine-plan/*` 示例。
- 队友 GitHub 并行探索遵循 `docs/TEAM_GITHUB_HANDOFF.md`，统一从 `develop` 派生并向 `develop` 提交 Draft PR。

## 2. 角色分工

### 2.1 主代理

主代理是：

```text
架构负责人 + 任务调度者 + 集成负责人 + Git 合并守门人
```

职责：

- 维护项目核心概念一致性。
- 把宏观目标拆成可执行任务。
- 明确每个任务的写入范围、禁止修改范围和验收命令。
- 决定任务交给子代理、CodeBuddy 还是人类队友。
- 审查 worker 输出。
- 运行集成验收。
- 处理 Git 合并、冲突和回滚策略。
- 更新 `DECISIONS`、任务队列、集成日志和关键架构文档。

### 2.2 子代理

子代理负责单一明确任务。

要求：

- 只修改授权写入范围内的文件。
- 不回滚他人改动。
- 完成后汇报改动文件、验收命令、测试结果和风险。
- 遇到架构冲突时停止并汇报，不自行改写核心方向。

### 2.3 CodeBuddy

由于比赛可能要求尽可能使用 CodeBuddy，CodeBuddy 应作为第一优先实现通道。

当前决策：

- 已确认本机 `codebuddy` CLI 可用，版本 `2.113.0`。
- 已确认 `codebuddy -p/--print` 可用于非交互调用。
- 已确认 `--output-format json` 可输出机器可读执行结果。
- 已确认 `--model` 可指定模型。
- 已确认存在 `--serve` HTTP 服务模式、`--acp` Agent Client Protocol 模式、`--bg` 后台模式、`--worktree` 工作树模式。
- 已确认本地配置存在 `textToImageModel: hunyuan-image-v3.0`，且 CodeBuddy 具备 `ImageGen` / `ImageEdit` 工具。
- 已确认 `glm-5.1` 能通过 ToolSearch 找到并尝试调用 `ImageGen`；最近一次真实调用被服务端限流，返回 `Too many requests`。
- 不因为使用 CodeBuddy 而放弃主代理的架构审查和 Git 合并守门职责。

当前建议：

- CodeBuddy CLI 作为第一优先自动化实现通道。
- 对简单任务可用 `--tools ""` 禁用工具，只拿模型回复。
- 对实现任务应明确 `--permission-mode`、`--tools`、写入范围和验收命令。
- `--json-schema` 参数存在，但实测 `deepseek-v4-flash` 可能把 StructuredOutput tool call 当文本输出；因此结构化结果仍必须经过本地 parser / Schema 校验。
- 图像生成建议使用 `glm-5.1` 驱动 `ImageGen`，并通过 `-y` 或权限配置允许工具执行；实测 `deepseek-v4-flash` 不稳定触发图像工具。
- `hunyuan-image-v3.0` 可进入开发期图像候选池，但在限流、权限、输出路径和缓存策略稳定前，不作为玩家运行时默认图像通道。

最小非交互调用示例：

```bash
codebuddy -p \
  --output-format json \
  --tools "" \
  --model deepseek-v4-flash \
  "请只输出 OK。"
```

结构化输出不应只信 `--json-schema`，应继续走项目本地校验：

```text
CodeBuddy 输出
  -> parse / extract JSON
  -> validate_proposal.py 或 validate_asset_candidate.py
  -> simulate_asset_candidate.py
```

CodeBuddy 适合：

- 局部代码实现
- 前端组件草稿
- 后端 API 草稿
- 测试用例
- 文档初稿
- 重构建议
- bug 修复建议
- 开发期离线图像候选生成
- 比赛合规所需的 AI 工具使用证据
- 由用户手动转交后的多子代理任务调度

CodeBuddy 当前 CLI help 标注的 supported model：

```text
glm-5.1
glm-5.0
glm-5.0-turbo
glm-5v-turbo
glm-4.7
minimax-m3-play
minimax-m2.7
minimax-m2.5
kimi-k2.6
kimi-k2.5
hy3-preview-agent
deepseek-v4-pro
deepseek-v4-flash
deepseek-v3-2-volc
```

本地产品配置中还能看到其他候选模型，例如 `glm-4.6`、`glm-4.6v`、`deepseek-v4-pro-exclusive`、`kimi-k2-thinking` 等；但任务委派默认以 CLI help 的 supported list 为准，避免使用未确认可调用的隐藏模型。

CodeBuddy ImageGen 非交互调用示例：

```bash
codebuddy -p -y --output-format json \
  --model glm-5.1 \
  --text-to-image-model hunyuan-image-v3.0 \
  --allowedTools ImageGen \
  --max-turns 8 \
  "请调用 ImageGen 工具生成一张简单的 2D 塔防炮塔图标，白色背景，512x512，medium quality。请把 output_dir 设置为 /tmp/codebuddy-image-test。不要生成 SVG 或代码。完成后只返回图片 URL 或文件路径。"
```

CodeBuddy 不应单独决定：

- 项目核心架构
- 编译器 IR 设计
- 数据生命周期
- Git 主线合并
- provider 费用策略
- 安全 / secret 处理

### 2.3.1 CodeBuddy 子代理调度边界

CodeBuddy 可以作为主要执行调度器。

用户可以把主代理生成的任务包手动转交给 CodeBuddy，并允许 CodeBuddy 使用其自身的子代理模式进行实现。

但 CodeBuddy 子代理仍必须遵守主项目边界：

- 只能修改任务包明确授权的文件或目录。
- 不得修改 `.env`、密钥、凭据或本地 provider 配置。
- 不得自行改写核心架构决策。
- 不得绕过 schema、测试和验收命令。
- 不得直接合并到 `main`。
- 不得把实验性原型直接混入正式实现。
- 遇到架构冲突、依赖新增、数据模型变更或保护文件修改需求时，必须停止并回报。

主会话职责不因 CodeBuddy 子代理调度而变化：

- 主会话负责关键架构和产品决策。
- 主会话负责任务边界和验收标准。
- 主会话负责最终审查、测试、合并和发布判断。
- 主会话负责维护事实源文档。

### 2.4 OpenCode headless

OpenCode headless 是第二优先实现通道，适合可自动化、边界清晰、可在 worktree 中执行的任务。

当前决策：

- 已确认本机 `opencode` CLI 可用，版本 `1.17.11`。
- 已确认 `opencode run` 可用于非交互调用。
- 已确认 `--model` 支持 `provider/model` 格式。
- 已确认 `--format json` 可输出 JSON 事件流。
- 已确认 `--dir` 可指定任务工作目录。
- 已确认 `--dangerously-skip-permissions` 可用于自动批准工具调用；只应在隔离 worktree 或 `/tmp` 探针中使用。
- 已确认 `opencode serve` 可启动 headless server。
- 已确认 `opencode acp` 可启动 ACP server。
- 已确认 `opencode models` 可查询 provider / model 列表。
- 已用 `volcengine-plan/deepseek-v4-flash` 完成最小文本调用。
- 已用 `/tmp/opencode-headless-probe` 完成安全写文件 smoke test。

已知限制：

- headless 模式只允许调用指定模型。
- OpenCode headless 中优先使用 `volcengine-plan/*`。
- 其他免费或官方 API 模型作为候选 / fallback。
- 在当前 Codex 受控执行通道内，`opencode run --dir <private-project-worktree>` 会被平台视为可能向外部模型披露私有仓库上下文，即使用户允许也可能被拒绝。不得通过复制仓库、改目录、压缩上下文等方式绕过。
- 因此，本通道内 OpenCode 只适合无项目上下文的公开任务建议、模型能力探针或用户明确在自己 IDE/CLI 环境中执行的 worker。需要读取私有仓库并修改代码时，优先使用本地 task worktree、CodeBuddy IDE 主代理或 Codex worker。

允许模型白名单：

```text
opencode/big-pickle
opencode/deepseek-v4-flash-free
opencode/mimo-v2.5-free
deepseek/deepseek-v4-flash
deepseek/deepseek-v4-pro
volcengine-plan/deepseek-v4-flash
volcengine-plan/deepseek-v4-pro
volcengine-plan/glm-5.2
volcengine-plan/kimi-k2.6
zhipuai-coding-plan/glm-5.2
```

OpenCode 模型建议：

| 任务类型 | 优先模型 |
|---|---|
| 普通脚本 / 小工具 / 测试 | `volcengine-plan/deepseek-v4-flash` 优先；fallback `opencode/deepseek-v4-flash-free`、`opencode/mimo-v2.5-free` |
| 中等实现任务 | `volcengine-plan/deepseek-v4-pro` 或 `volcengine-plan/deepseek-v4-flash` 优先；fallback `deepseek/deepseek-v4-pro`、`deepseek/deepseek-v4-flash` |
| 关键编译器 / 后端 / 复杂重构 | `volcengine-plan/deepseek-v4-pro`、`volcengine-plan/glm-5.2` |
| 大上下文审查 / 复杂中文文档 | `volcengine-plan/glm-5.2` 优先；fallback `zhipuai-coding-plan/glm-5.2` |
| Kimi 适合的代码/推理任务 | `volcengine-plan/kimi-k2.6` |
| 需要降级或候选时 | `opencode/big-pickle`、`deepseek/*`、免费模型作为候选 |

最小非交互调用示例：

```bash
opencode run \
  --dir /home/zty/projects/ai-compiled-towerdefense \
  --model volcengine-plan/deepseek-v4-flash \
  --format json \
  "请只输出 OK。不要解释，不要调用工具。"
```

隔离目录写文件 smoke test 示例：

```bash
opencode run \
  --dir /tmp/opencode-headless-probe \
  --model volcengine-plan/deepseek-v4-flash \
  --format json \
  --dangerously-skip-permissions \
  "请创建文件 /tmp/opencode-headless-probe/result.txt，内容只写 OK。完成后只回复 DONE。"
```

OpenCode 不应单独决定：

- 架构方向
- Git 合并
- 保护文件修改
- secret / provider 配置
- 重大依赖引入

### 2.5 Codex

Codex 在本项目中的定位不是普通实现优先工具，而是：

- 高难度任务兜底
- 架构推演
- 子代理调度
- 任务切片
- 代码审查
- 集成测试
- Git 合并和冲突处理
- 与用户进行设计决策讨论

Codex 可以在必要时直接实现，但应优先保留主会话的架构连续性。

当前决策：

- 已确认本机 `codex` CLI 可用，版本 `codex-cli 0.142.0`。
- 已确认 `codex exec` 可用于非交互调用。
- 已确认 `codex review` 可用于非交互代码审查。
- 已确认 `codex mcp-server` 可启动 MCP server。
- 已确认 `--cd` 可指定工作目录。
- 已确认 `--sandbox read-only/workspace-write` 可控制执行沙盒。
- 已确认 `--ephemeral` 可避免持久化 session 文件。
- 已确认 `--json` 可输出 JSONL 事件流。
- 已确认 `--output-last-message` 可把最终回复写入文件。
- 已确认 `--output-schema` 可约束最终响应结构。
- 已用 `codex exec` 完成最小文本调用。
- 已用 `/tmp/codex-headless-probe` 完成安全写文件 smoke test。

注意：

- 当前 `codex exec` 子命令没有 `--ask-for-approval` 参数；不要照搬交互 CLI 的参数。
- 对 worker 任务应显式设置 `--sandbox`，普通审查用 `read-only`，受控实现用 `workspace-write`。
- 对非 Git 目录探针需要 `--skip-git-repo-check`；真实项目任务应尽量在 Git worktree 中执行。

最小非交互调用示例：

```bash
codex exec \
  --cd /home/zty/projects/ai-compiled-towerdefense \
  --skip-git-repo-check \
  --sandbox read-only \
  --ephemeral \
  --json \
  --output-last-message /tmp/codex-headless-ok.txt \
  "请只输出 OK。不要解释，不要运行命令。"
```

隔离目录写文件 smoke test 示例：

```bash
codex exec \
  --cd /tmp/codex-headless-probe \
  --skip-git-repo-check \
  --sandbox workspace-write \
  --ephemeral \
  --json \
  --output-last-message /tmp/codex-headless-probe/last.txt \
  "请创建文件 /tmp/codex-headless-probe/result.txt，内容只写 OK。完成后只回复 DONE。"
```

### 2.6 人类队友

技术队友适合：

- 前端 UI 切片
- 简单后端接口
- 测试
- 数据整理
- Playtest 问题记录

内容队友适合：

- 世界书内容
- NPC
- 节点事件
- 材料 / 道具命名
- 文案润色
- 美术结果筛选
- 演示脚本

主创 / 用户负责：

- 产品方向
- 玩法取舍
- 比赛策略
- 演示优先级
- 最终审查

## 3. CodeBuddy 使用策略

### 3.1 能力分级

#### A 级：可自动化 headless / CLI / API

条件：

- 有官方文档或本地可验证命令。
- 可以指定仓库路径、任务文本和输出位置。
- 可以在隔离 worktree 中运行。
- 可以返回结构化结果或 patch。

策略：

- 主代理生成任务包。
- 在独立 worktree 中调用 CodeBuddy。
- CodeBuddy 输出 patch / diff / 报告。
- 主代理审查、测试、合并。

#### B 级：IDE / CLI 手动执行

条件：

- CodeBuddy 能在 IDE 或终端交互执行任务。
- 但无法被主代理稳定 headless 调用。

策略：

- 主代理生成 CodeBuddy handoff prompt。
- 用户或队友把 prompt 粘贴到 CodeBuddy。
- CodeBuddy 在指定分支 / worktree 中工作。
- 完成后把 diff、文件列表、测试结果交回主代理。

#### C 级：网页聊天 / 外部生成

条件：

- 只能通过网页或聊天生成内容。
- 不能直接修改仓库。

策略：

- 输出放入 `content/import_inbox/` 或作为 patch 文本交回。
- 主代理或工具解析和审查。
- 不能直接进入 `locked` 或主线。

### 3.2 CodeBuddy 任务包模板

当前可验证任务包格式以 `docs/WORKER_TASK_PACK_V0_1.md`、`shared/schemas/worker_task_pack.v0.1.schema.json` 和 `tools/dev/validate_worker_task_pack.py` 为准。下面的文本模板只保留为人工粘贴时的可读结构；正式交付给 worker 前，应优先生成并校验 `WorkerTaskPack v0.1` JSON。

```text
任务目标：

任务类型：
- 实现 / 修复 / 测试 / 文档 / 原型

背景文档：
- docs/...

工作分支 / worktree：

允许修改：
- path/to/file

禁止修改：
- docs/PROJECT_ARCHITECTURE_AND_GOVERNANCE.md
- .env
- control/DECISIONS.md

允许 CodeBuddy 子代理：
- 是 / 否

如果允许子代理：
- 子代理必须继承本任务的允许修改 / 禁止修改范围。
- 子代理之间必须避免修改同一文件。
- 最终必须由 CodeBuddy 主任务汇总为一个结果报告。

实现要求：

验收命令：

完成后请汇报：
- 修改文件
- 关键设计
- 验收结果
- 未解决风险
- 是否使用了 CodeBuddy 子代理
- 子代理分工摘要
- 是否需要主代理集成处理
```

### 3.2.1 手动转交流程

用户手动把任务交给 CodeBuddy 时，建议流程：

```text
主会话生成任务包
  -> 用户粘贴给 CodeBuddy
  -> CodeBuddy 在指定 worktree / 分支执行
  -> CodeBuddy 可内部拆分子代理
  -> CodeBuddy 汇总改动、测试和风险
  -> 用户把结果交回主会话
  -> 主会话审查 diff、运行验收、决定是否合并
```

CodeBuddy 返回结果至少应包含：

- 分支 / worktree。
- 修改文件列表。
- 关键实现说明。
- 运行过的命令。
- 测试结果。
- 未解决风险。
- 是否新增依赖。
- 是否触碰保护文件。
- 是否有需要主会话确认的设计变化。

### 3.3 CodeBuddy 使用记录

如果比赛需要证明使用 CodeBuddy，应维护使用记录。

建议记录：

- 日期
- 任务名
- 使用方式：headless / CLI / IDE / 网页 / OpenCode / Codex
- 输入 prompt 摘要
- 输出摘要
- 修改文件
- 验收命令
- 是否合并
- 截图或日志路径

## 4. OpenCode 使用策略

### 4.1 任务包模板

```text
任务目标：

推荐模型：

工作分支 / worktree：

允许修改：
- path/to/file

禁止修改：
- .env
- docs/PROJECT_ARCHITECTURE_AND_GOVERNANCE.md
- docs/AI_ASSET_COMPILER_V0_1.md
- docs/ASSET_GRAPH_COMPILER_V0_1.md

参考文档：
- docs/...

实现要求：

验收命令：

完成后请汇报：
- 修改文件
- 关键设计
- 验收结果
- 未解决风险
- 是否需要主代理集成处理
```

### 4.2 分配规则

优先级：

1. 比赛明确需要 CodeBuddy 的任务，优先 CodeBuddy。
2. CodeBuddy 不方便自动执行、但任务边界清楚时，用 OpenCode headless。
3. OpenCode headless 默认优先使用 `volcengine-plan/*`。
4. 其他 OpenCode 模型作为候选、降级或 fallback。
5. Codex 负责高难度兜底和最终集成审查。

## 5. 分支与 worktree

当前仓库状态：

- 当前目录已初始化为 Git 仓库。
- 主分支为 `main`。
- 仓库级 `user.name` 为 `zty`。
- 仓库级 `user.email` 为 `25451354054@stu.wzu.edu.cn`。
- `.env` 已被 `.gitignore` 忽略，不能纳入提交。
- 当前 `main` worktree 位于 `/home/zty/projects/ai-compiled-towerdefense`，作为 Codex 主会话的架构决策、任务、验收和合并基线。
- 当前 `develop` worktree 位于 `/home/zty/projects/ai-compiled-towerdefense-develop`，作为 CodeBuddy IDE 主代理工作区。

推荐分支：

```text
main              稳定展示分支
develop           集成分支
task/*            任务分支
experiment/*      高风险探索分支
```

推荐 worktree：

```text
local/worktrees/
  task-assetgraph-runtime/
  task-backend-api/
  task-studio-ui/
  task-phaser-battle/
  task-content-pipeline/
```

规则：

- 任务分支不能直接进入 `main`。
- 子代理和 CodeBuddy 优先在 `task/*` 或独立 worktree 中工作。
- 主代理负责把结果整合到 `develop`。
- `main` 不作为实时施工事实源；它只在阶段性冻结窗口从 `develop` 受控同步。
- 演示前或阶段冻结后，从 `develop` 合并或挑选到 `main`。
- 高风险实验放入 `experiment/*`。
- CodeBuddy IDE 可以打开 `develop` worktree 作为主交互目录。
- CodeBuddy 主代理可以在 `develop` 阅读上下文、拆分任务和汇总结果，但普通实现改动应交给 `task/*` worktree 中的子代理 / worker 完成。

### 5.1 main 同步窗口

`develop` 是快速集成事实源，允许承载最新架构、设计、实现和审查结果。`main` 是稳定决策 / 展示基线，只有在一组关键决策已经阶段性冻结、验收通过，并且需要给评审、队友或发布环境提供稳定入口时才同步。

同步 `main` 前必须先做以下检查：

- 确认 `develop` 已通过本轮必需验收。
- 确认 `main` 当前工作区没有未识别的用户改动。
- 如果 `main` 有手动改动，先判断它是用户草稿、待合并决策，还是应由 `develop` 版本覆盖；不得直接回滚。
- 列出本次要同步的文档、代码和资产范围。
- 对 `CURRENT_ARCHITECTURE_INDEX.md`、README、关键治理文档做一次事实源一致性检查。
- 同步完成后记录 commit 摘要和剩余差异。

`main` 落后于讨论或 `develop` 是允许的，但这种落后必须是“受控滞后”。如果 `main` 中的旧说法会误导新代理、CodeBuddy、OpenCode、队友或评委，应安排一次同步窗口，而不是继续让旧说法长期存在。

### 5.2 分支命名

建议格式：

```text
task/<area>-<short-name>
experiment/<area>-<short-name>
docs/<topic>
fix/<short-name>
```

示例：

```text
task/frontend-battle-shell
task/backend-research-job
task/content-locked-manifest
experiment/candidate-ir
docs/mvp-scope
```

### 5.3 worktree 边界

每个 worker / CodeBuddy 任务优先使用独立 worktree。

一个 worktree 对应一个任务包。

规则：

- 不在同一个 worktree 中并行跑多个互相无关任务。
- 不让多个 worker 同时修改同一文件。
- 不在 worker worktree 中改 `.env`。
- 不在 worker worktree 中做主线合并。
- 不在 worker worktree 中直接处理跨任务冲突。
- worker 完成后必须提供 diff 摘要、测试结果和风险说明。

### 5.4 正式任务与探索任务

正式任务：

```text
task/*
  目标明确
  写入范围明确
  有验收命令
  可以进入 develop
```

探索任务：

```text
experiment/*
  验证想法
  可以失败
  不直接进入 develop
  需要主会话审查后挑选迁移
```

纯研究原型优先放 `/tmp/ai-compiled-td-research/`，不进入 Git。

只有当主会话确认其价值后，才转成正式任务迁入仓库。

### 5.5 回收与集成

worker 完成后，主会话需要做：

1. 查看 `git status` 和 diff。
2. 检查是否越界修改保护文件。
3. 运行任务指定验收命令。
4. 检查是否泄露 secret、provider key、原始 prompt 或不该进入玩家侧的 trace。
5. 判断是否需要更新文档。
6. 决定合并、要求返工、拆分提交或废弃。

## 6. 合并规则

合并前必须满足：

- 任务目标已完成或明确降级。
- 通过任务指定验收命令。
- 没有未经解释的失败测试。
- 没有 secret 泄露。
- 没有未经授权修改保护文件。
- 关键设计变更已更新文档。

合并后必须记录：

- 合并来源
- 任务摘要
- 测试结果
- 已知风险
- 后续任务

## 7. 保护文件

以下文件只有主代理或人类明确授权后才能修改：

- `.env`
- `control/DECISIONS.md`
- `control/MVP_SCOPE.md`
- `docs/PROJECT_ARCHITECTURE_AND_GOVERNANCE.md`
- `docs/AI_ASSET_COMPILER_V0_1.md`
- `docs/ASSET_GRAPH_COMPILER_V0_1.md`

worker 可以阅读这些文件，但不能随意改写核心概念。

## 8. 任务委派优先级

优先级建议：

1. 比赛要求必须使用 CodeBuddy 的任务，优先尝试 CodeBuddy。
2. CodeBuddy 不适合自动化时，边界清晰任务优先 OpenCode headless。
3. 可并行、边界清晰的复杂实现任务，可用子代理 / worktree。
4. 高难度、跨模块、架构敏感任务由 Codex 兜底或审查。
5. 架构和产品决策留在主会话。
6. 高风险实验先用 `experiment/*`。

## 9. 下一步

已确认：

- CodeBuddy CLI 可做非交互调用。
- OpenCode headless 可做非交互调用和隔离目录写文件。
- Codex `exec` 可做非交互调用和隔离目录写文件。

下一步需要确认：

- 当前本地仓库是否需要绑定比赛指定远程仓库。
- CodeBuddy / OpenCode / Codex 在独立 Git worktree 中并行执行任务的标准流程。
- 每个 worker 的 stdout / JSONL / session id 如何归档到 `control/` 或 `logs/`，作为比赛和审查证据。
- worker 输出如何统一回收为 diff、测试结果和风险报告。
- 哪些任务必须强制 `read-only`，哪些任务可以给 `workspace-write` 或自动许可。
- CodeBuddy `--serve`、OpenCode `serve`、ACP / MCP 模式是否值得用于后续自动调度；MVP 阶段优先使用 CLI headless。
