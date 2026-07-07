# WorkerTaskPack v0.1

本文定义交付给 CodeBuddy、OpenCode、Codex headless 或人类 worker 的任务包格式。

它的目的不是替代具体 schema、semantic gate、media gate、工具脚本或专题文档，而是在 worker 开始读仓库、改文件、调用 provider 或提交结果前，先冻结任务边界。

## 使用场景

当主会话需要把任务交给本地 worker、自动化执行器或人工审查环节时，应先生成一个 `WorkerTaskPack v0.1`：

```text
主会话决策任务
  -> 生成 WorkerTaskPack
  -> validator 校验边界
  -> worker 在 task/* worktree 执行
  -> worker 汇报 diff / 验收 / 风险
  -> 主会话审查并合回 develop
```

`main` 仍是稳定决策 / 发布基线；`develop` 是当前集成事实源；普通 worker 不直接合并 `main` 或 `develop`。

## 字段级事实源

- Schema: `shared/schemas/worker_task_pack.v0.1.schema.json`
- Validator: `tools/dev/validate_worker_task_pack.py`
- 示例: `examples/worker_task_packs/p1e_worker_task_pack_protocol.v0.1.json`
- 验收 profile 示例: `examples/worker_task_packs/p1e_worker_acceptance_command_profiles.v0.1.json`
- 审计公共 helper: `tools/dev/audit_common.py`
- 验收 profile 迁移审计: `tools/dev/audit_worker_acceptance_profiles.py`
- release gate 降级审计: `tools/dev/audit_release_gate_profiles.py`

## 必读事实源

任务包的 `required_reading` 至少应包含：

- `docs/CURRENT_ARCHITECTURE_INDEX.md`
- `docs/AI_COMPILATION_SYSTEM_V0_1.md`
- `control/TASK_QUEUE.md`

根据任务类型继续追加专题文档。例如地图任务追加 `docs/MAP_VISUAL_REFERENCE_PIPELINE_V0_1.md`，调度任务追加 `docs/GENERATION_SCHEDULER_V0_1.md`，前端任务追加 `docs/FRONTEND_MOCK_API_V0_1.md` 与 `docs/FRONTEND_VISUAL_RUNTIME_AUDIT_V0_1.md`。

## 最小字段

```json
{
  "schema_version": "worker_task_pack.v0.1",
  "task_id": "P1-example",
  "title": "任务标题",
  "task_type": "implementation",
  "handoff_mode": "codebuddy_ide",
  "base_branch": "develop",
  "branch": "task/example",
  "worktree": "/tmp/example-worktree",
  "objective": "一句话说明真实目标。",
  "required_reading": [
    "docs/CURRENT_ARCHITECTURE_INDEX.md",
    "docs/AI_COMPILATION_SYSTEM_V0_1.md",
    "control/TASK_QUEUE.md"
  ],
  "allowed_paths": ["docs/"],
  "forbidden_paths": [".env"],
  "acceptance_commands": ["git diff --check"],
  "reporting_requirements": [
    "modified_files",
    "acceptance_results",
    "protected_files_touched",
    "unresolved_risks"
  ],
  "safety_rules": {
    "may_read_env": false,
    "may_print_secrets": false,
    "may_store_raw_prompt": false,
    "may_store_provider_response": false,
    "may_bypass_schema_or_semantic_gates": false,
    "may_direct_merge_main_or_develop": false,
    "may_activate_review_only_artifacts": false,
    "must_preserve_player_immersion": true,
    "must_report_protected_files_touched": true
  },
  "provider_policy": {
    "provider_calls_allowed": false,
    "requires_explicit_user_authorization": true,
    "allowed_profiles": [],
    "max_calls": 0,
    "raw_response_storage": "forbidden"
  }
}
```

## 安全规则

WorkerTaskPack 必须显式表达以下边界：

- worker 不读 `.env`，不打印 API key、secret、token。
- worker 不保存 raw prompt 或 provider response。
- worker 不绕过 schema、semantic gate、simulation gate、media gate 或人工 review。
- worker 不直接合并 `main` 或 `develop`。
- worker 不把 `review_only` 产物当作 runtime ready。
- 玩家侧文案继续保持沉浸式，不暴露 provider、prompt、schema、raw trace 等技术词。

真实 provider 调用不是一概禁止，但必须在 `provider_policy` 中显式开启，并写明授权、允许 profiles 和最大调用次数。即使允许真实调用，也不能保存 raw response，产物仍必须进入对应 manifest、validator 和 promotion gate。

## 验收命令 profile

`acceptance_commands` 保持必填，用于兼容旧任务包和只理解平铺命令的 worker。新任务包可以额外提供可选的 `acceptance_profile`，把日常快速反馈、最终 evidence 和录屏 / release gate 分层表达：

```json
{
  "acceptance_commands": ["python3 tools/dev/run_fast_quality_gate.py --output /tmp/fast.json"],
  "acceptance_profile": {
    "default_profile": "daily_fast",
    "profiles": {
      "daily_fast": {
        "description": "日常小改的快速反馈。",
        "commands": [
          "python3 tools/dev/run_fast_quality_gate.py --output /tmp/fast.json",
          "python3 tools/demo/export_evidence.py --validation-profile summary-only --output-dir /tmp/summary_evidence",
          "git diff --check"
        ],
        "required_for": ["daily_small_changes"]
      },
      "full_evidence": {
        "description": "最终评审前完整 evidence。",
        "commands": [
          "python3 tools/demo/export_evidence.py --output-dir /tmp/full_evidence",
          "git diff --check"
        ],
        "required_for": ["final_review"]
      },
      "release_gate": {
        "description": "录屏或发布候选验收。",
        "commands": [
          "python3 tools/demo/run_demo_evidence_suite.py --output-root /tmp/demo_suite",
          "git diff --check"
        ],
        "required_for": ["recording", "release_candidate_review"]
      }
    }
  }
}
```

规则：

- `default_profile` 必须存在于 `profiles`。
- 推荐 profile id 为 `daily_fast`、`full_evidence`、`release_gate`；也可以按任务需要增加其他简单 id。
- 每个 profile 使用 `description`、`commands`、`required_for` 三个字段，不嵌套更复杂的策略结构。
- profile 内的命令和顶层 `acceptance_commands` 一样，都会被 validator 检查 forbidden command fragment。
- `daily_fast` 不得包含默认完整 `tools/demo/export_evidence.py --output-dir`；它可以使用 `tools/dev/run_fast_quality_gate.py`，也可以使用 `tools/demo/export_evidence.py --validation-profile summary-only --output-dir ...`。
- `full_evidence` 和 `release_gate` 用于最终评审、录屏或发布候选，可以包含默认完整 `export_evidence.py` 或 `run_demo_evidence_suite.py`。
- `release_gate` 不得包含 `--allow-missing-browser`、`--allow-browser-unavailable` 或 `--validation-profile summary-only`；如果运行 `run_demo_evidence_suite.py`，必须配套 `validate_demo_evidence_suite_report.py --require-browser-captured`。
- 通用 `release_gate` 不应硬编码 `--require-scheduler-runner-mode` 或 `--require-outbox-runner-mode`；runner mode 专项选择任务包可以作为例外，普通发布门应允许 suite 的 `auto` runner 选择可用环境。

profile 是验收分层，不是降低质量。日常小改可以默认跑 `daily_fast` 加速反馈，但合并前、最终评审前或录屏前仍应按任务风险运行 `full_evidence` 或 `release_gate`。

### Profile runner

`tools/dev/run_worker_acceptance_profile.py` 是本地执行 `acceptance_profile` 的标准入口：

```bash
python3 tools/dev/run_worker_acceptance_profile.py examples/worker_task_packs/p1e_worker_acceptance_command_profiles.v0.1.json --list-profiles
python3 tools/dev/run_worker_acceptance_profile.py examples/worker_task_packs/p1e_worker_acceptance_command_profiles.v0.1.json --dry-run --output /tmp/worker_acceptance_profile_dry_run.json
python3 tools/dev/run_worker_acceptance_profile.py examples/worker_task_packs/p1e_worker_acceptance_command_profiles.v0.1.json --profile daily_fast --output /tmp/worker_acceptance_profile_daily_fast.json
```

规则：

- runner 会先复用 `tools/dev/validate_worker_task_pack.py` 的 `validate()` 逻辑；任务包校验失败时不会执行 profile 命令。
- 不传 `--profile` 时使用 `acceptance_profile.default_profile`；`--list-profiles` 只列出 profile 并退出 0，不执行命令。
- `--dry-run` 只解析和列出将运行的命令，报告状态为 `dry_run`。
- runner 不使用 shell。命令字符串通过 `shlex.split` 转成 argv，支持 `PYTHONPYCACHEPREFIX=/tmp/x python3 ...` 这类前置环境变量 token。
- 前置环境变量 token 会进入子进程环境，而不只是 dry-run 报告字段；`tools/dev/check_worker_acceptance_profile_env_assignments.py` 会验证 `KEY=value python3 ...` 与受限 stdout redirect 可以组合使用。
- runner 会拒绝独立管道、`<`、任意非受限重定向、`;` shell 连接、`&&`、`||`、反引号和 `$(` 等 shell-only 语法；遇到不支持语法时该命令记为 `failed/unsupported_command_syntax`，不会执行。
- runner 只支持一种受限 stdout 重定向：最终 token 为 `> /tmp/file` 或 `>/tmp/file`。该路径必须是仓库外 `/tmp` 下的文件，runner 会捕获 stdout 后自行写文件，命令仍不经过 shell。
- 参数内部的 `|` 可作为普通 argv 内容，例如 `rg "a|b"`；`;` 只允许出现在 `python* -c` 的最后一个代码 argv 内。
- 输出报告默认写入 `/tmp/worker_acceptance_profile_run_report.v0.1.json`，schema 为 `worker_acceptance_profile_run_report.v0.1`。
- 没有 `acceptance_profile` 的旧任务包会直接失败并提示手动运行 `acceptance_commands`，避免把旧平铺命令误读成 profile。

### Profile batch runner

`tools/dev/run_worker_acceptance_batch.py` 是批量执行或 dry-run 多个 WorkerTaskPack `acceptance_profile` 的本地入口。它复用单包 profile runner 的任务包校验、profile 解析和命令执行规则，用于全量 dry-run、按前缀抽样或对一组明确任务包跑同一 profile。

```bash
python3 tools/dev/run_worker_acceptance_batch.py --task-pack examples/worker_task_packs/p1e_worker_acceptance_profile_audit.v0.1.json --profile daily_fast --dry-run --output /tmp/worker_acceptance_batch_dry_run.json
python3 tools/dev/run_worker_acceptance_batch.py --all --profile daily_fast --dry-run --output /tmp/worker_acceptance_batch_all_dry.json
python3 tools/dev/validate_worker_acceptance_batch_report.py /tmp/worker_acceptance_batch_all_dry.json --expect-status dry_run --expect-failed-count 0 --min-pack-count 100
```

规则：

- runner 默认拒绝隐式选择所有任务包；必须显式传入 `--all`、`--task-pack`、`--task-id-prefix` 或 `--path-contains`。
- `--all --dry-run` 适合在迁移、审计和合并前快速确认所有任务包 profile 可解析；日常真实执行应使用显式 `--task-pack` 或筛选条件缩小范围。
- `--profile` 会对所有选中的任务包使用同一个 profile；不传时使用每个任务包自己的 `acceptance_profile.default_profile`。
- `--fail-fast` 会在首个失败包后停止，但报告仍记录 selected 与 executed 的差异。
- 输出报告默认写入 `/tmp/worker_acceptance_batch_run_report.v0.1.json`，schema 为 `worker_acceptance_batch_run_report.v0.1`，可由 `tools/dev/validate_worker_acceptance_batch_report.py` 校验。
- batch runner 只负责本地验收编排，不调用 provider、不读取 `.env`，也不替代完整 evidence、demo suite 或最终人工审查。

### Profile migration audit

`tools/dev/audit_common.py` 提供只读审计工具共享的 `/tmp` 输出路径保护、仓库相对路径显示、JSON 报告写入和命令字符串归一化 helper。它不是全仓通用工具层；新增本地审计脚本时可以复用它，普通内容生成、媒体处理或 runtime builder 不需要为了统一风格而迁移。

`tools/dev/audit_worker_acceptance_profiles.py` 是只读迁移审计入口，用于分析现有 `examples/worker_task_packs/*.json` 是否已经迁移到 `acceptance_profile`，并指出哪些旧包适合迁移、哪些命令需要人工处理：

```bash
python3 tools/dev/audit_worker_acceptance_profiles.py
python3 tools/dev/audit_worker_acceptance_profiles.py --task-pack-dir examples/worker_task_packs --output /tmp/worker_acceptance_profile_audit_report.json --max-samples 8
```

规则：

- 审计会扫描 `--task-pack-dir` 下的 `*.json`，默认目录为 `examples/worker_task_packs`。
- 审计复用 `tools/dev/validate_worker_task_pack.py` 的 `validate()`，但不会执行任何被扫描任务包里的 `acceptance_commands` 或 `acceptance_profile` 命令。
- 审计复用 `tools/dev/run_worker_acceptance_profile.py` 的 `parse_command()` 判断 runner 兼容性；here-doc、管道、非受限重定向、分号连接、逻辑连接、命令替换等 shell-only 命令只会被标记为需要人工处理，不会让整次 audit 失败。
- 报告默认写入 `/tmp/worker_acceptance_profile_audit_report.v0.1.json`，schema 为 `worker_acceptance_profile_audit_report.v0.1`。
- 报告包含 summary、逐包 top-level/profile 命令分类、runner 兼容性计数、迁移建议，以及 `without_profile_samples`、`full_export_samples`、`manual_review_samples`、`migration_candidate_samples`。
- 无 `acceptance_profile` 且 validator 通过的旧包会被标记为 migration candidate；若顶层含完整 `tools/demo/export_evidence.py --output-dir`，建议拆成 `daily_fast` 的快速/summary-only profile 和 `full_evidence` 的完整证据 profile。
- 该工具只审计和写仓库外 `/tmp` 报告；`--output` 指向仓库内路径或其他非 `/tmp` 路径时会失败，不修改旧任务包，不替代人工迁移、最终 evidence、demo suite 或合并前审查。

### Release gate profile audit

`tools/dev/audit_release_gate_profiles.py` 是只读发布门配置审计入口，用于扫描已声明 `acceptance_profile.profiles.release_gate` 的任务包，避免录屏 / 发布候选验收命令混入日常快速反馈的降级开关：

```bash
python3 tools/dev/audit_release_gate_profiles.py
python3 tools/dev/audit_release_gate_profiles.py --task-pack-dir examples/worker_task_packs --output /tmp/release_gate_profile_audit_report.json --max-samples 20
```

规则：

- 审计只扫描 WorkerTaskPack JSON，不执行任何被扫描任务包里的 `release_gate`、`daily_fast` 或 `acceptance_commands`。
- 没有 `release_gate` 的任务包不会失败；工具只检查已经声明 release gate 的任务包是否保持发布级证据要求。
- `release_gate` 中出现 `--allow-missing-browser`、`--allow-browser-unavailable` 或 `--validation-profile summary-only` 会失败。
- `release_gate` 中运行 `run_demo_evidence_suite.py` 时，应同时运行 `validate_demo_evidence_suite_report.py`，并至少包含 `--require-browser-captured`；当前默认还要求 scheduler pipeline smoke 与 outbox import smoke 证据被 validator 看见。
- 通用 `release_gate` 中出现 scheduler / outbox runner mode 锁定会失败；只有 runner 选择专项任务包允许用该类断言验证 suite 的 runner mode 报告。
- 报告默认写入 `/tmp/release_gate_profile_audit_report.v0.1.json`，schema 为 `release_gate_profile_audit_report.v0.1`；`--output` 指向仓库内路径或其他非 `/tmp` 路径时会失败。

## 验收

生成任务包后至少运行：

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1e_worker_task_pack_protocol.v0.1.json
python3 -m py_compile tools/dev/validate_worker_task_pack.py
git diff --check
```

若任务包会触及演示证据，还应运行：

```bash
python3 tools/demo/export_evidence.py --output-dir /tmp/worker_task_pack_evidence
```

## 汇报格式

worker 完成后必须回报：

- 修改文件。
- 关键设计。
- 验收命令与结果。
- 是否触碰禁止路径或保护文件。
- 是否新增依赖。
- 是否使用子代理。
- 未解决风险。

主会话负责最终审查、补跑验收、处理冲突、合回 `develop`，以及决定何时同步到 `main`。
