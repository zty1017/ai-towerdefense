# CoreArtifactAlignmentReport v0.1

Last updated: 2026-07-02

本文档说明 `CoreArtifactAlignmentReport v0.1` 的用途和边界。

它是内部 evidence / 迁移审计报告，不是玩家侧数据，不是 runtime package，不是 WorldStateDeltaTransaction，也不是 promotion gate。它只回答一个问题：

```text
当前 reviewed 产物是否已经对齐 ContextPackage / FactEntry / CGOP / WorldStateDeltaTransaction 这些 AI 编译核心对象？
```

## 1. 为什么需要它

当前项目已经有：

- `ContextPackage v0.1`
- `FactEntry v0.1`
- `CompiledGameObjectPackage v0.1`
- `WorldStateDeltaTransaction v0.1`

前端 mock pack、Research Job、战斗结算和事务链已经开始携带这些对象或引用。但大量早期 review pack、地图审查包、媒体审查包和 provider 暂存产物仍然是专项 evidence。它们不一定都需要变成核心对象，但后续 worker 不能再靠口头判断“哪些该迁移、哪些不该迁移”。

`CoreArtifactAlignmentReport` 把这个判断变成机器可读清单。

## 2. 报告状态

每个 `target_report` 有一个 `alignment_state`：

- `native_snapshot_ready`：已经携带原生核心对象快照，并通过对应 validator。
- `refs_only`：只携带核心对象引用，还缺原生摘要或统一 validation report。
- `missing_core_alignment`：该 review pack 可能会进入后续 runtime / world 编译链路，但目前没有核心对象或 refs。
- `review_only_not_applicable`：专项审查证据，当前不应该强行迁移成核心对象。
- `validation_failed`：已有核心对象或事务，但 validator 未通过。

报告的 `overall_status` 可以是：

- `passed`
- `needs_migration`
- `failed`

`needs_migration` 不表示 MVP 阻断。它表示存在明确的下一批 P1 迁移任务。

## 2.1 显式不适用边界

某些 review pack 本身只是证据索引或审查交付包，不应该被强行包装成核心对象。此时应在对应产物中加入显式边界，例如：

```json
{
  "core_artifact_alignment": {
    "alignment_state": "review_only_not_applicable",
    "reason": "该文件是总审查交付包，不是 runtime package 或世界事务。",
    "expected_core_artifacts": [],
    "present_core_artifacts": [],
    "runtime_activation_allowed": false,
    "world_mutation_allowed": false,
    "next_action": "后续迁移应针对它引用的具体内容包或运行时产物。"
  }
}
```

`mvp_compiler_review_dossier.v0.1`、`mvp_stage_candidate_pack.v0.1`、`mvp_multistage_stage_candidate_pack.v0.1` 和 `mvp_multistage_content_pack.v0.1` 已采用该方式。这样做不是跳过校验，而是把“不应迁移”的架构判断显式化，避免后续 worker 把总览证据包、阶段候选容器或多阶段内容审查包误改成 CGOP 或 WorldStateDeltaTransaction。对于这些 review-only 容器，后续核心对象迁移应落到单个阶段引用的 WorldStateDelta、WorldStateDeltaTransaction、runtime package、compiled asset candidate，或具体 story asset review / promotion pack。

## 3. 安全边界

该报告必须保持：

```text
reads_env=false
calls_external_service=false
stores_prompt_body=false
stores_provider_body=false
runtime_mutation_count=0
world_mutation_count=0
```

它不能：

- 激活 review-only 产物。
- 更新 runtime package。
- 写入 RunWorldState。
- 把 ProviderArtifactPromotionReport 当作可运行对象。
- 用通用 effects 绕过 WorldStateDelta.operations[]。

## 4. 当前落地

字段级事实源：

- `shared/schemas/core_artifact_alignment_report.v0.1.schema.json`

构建与校验：

```bash
python3 tools/content_pipeline/build_core_artifact_alignment_report.py --validate
python3 tools/content_pipeline/validate_core_artifact_alignment_report.py examples/review_packs/core_artifact_alignment_report.v0.1.json
```

输出：

- `examples/review_packs/core_artifact_alignment_report.v0.1.json`

演示证据：

- `tools/demo/export_evidence.py` 会把报告摘要纳入 `summary.md` 与 `evidence.json`。

## 5. 后续使用

后续 worker 迁移 review pack 时，应先看本报告的 `migration_tasks`，再选择其中一个目标补：

- `core_artifact_refs`
- 原生 `core_artifacts` 快照
- 或明确的 `review_only_not_applicable` 边界

不要在没有运行时需求的情况下，把地图视觉审查、媒体质量审查等专项报告强行塞进 CGOP 或 WorldStateDeltaTransaction。
