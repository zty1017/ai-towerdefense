# WorkerTaskPack v0.1

本文定义交付给 CodeBuddy、OpenCode、Codex headless 或人类 worker 的任务包格式。

它的目的不是替代具体 schema、semantic gate、media gate、工具脚本或专题文档，而是在 worker 开始读仓库、改文件、调用 provider 或提交结果前，先冻结任务边界。

## 使用场景

当主会话需要把任务委派给外部或并行 worker 时，应先生成一个 `WorkerTaskPack v0.1`：

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
