# ProviderArtifactPromotionReport v0.1

本文定义 `ProviderArtifactStagingManifest` 之后的显式晋升报告。

它不是 runtime package，不是 WorldStateDeltaTransaction，也不是执行器。它只回答一个问题：某个 review-only provider artifact 是否可以进入后续 runtime package 构建、世界事务构建或 published media 更新。

当前 v0.1 的示例报告是阻断报告，因为 source staging 中的 `media_gate`、`semantic_gate` 和 `human_review` 仍未完成。

## 事实源

- Schema: `shared/schemas/provider_artifact_promotion_report.v0.1.schema.json`
- Validator: `tools/dev/validate_provider_artifact_promotion_report.py`
- Example: `examples/provider_artifact_staging/p1b_provider_artifact_promotion_report.example.json`
- Image failure example: `examples/provider_artifact_staging/p1b_provider_image_artifact_promotion_report.example.json`

## 在编译链路中的位置

```text
ProviderOutputEnvelope
  -> ProviderArtifactStagingManifest
  -> ProviderArtifactPromotionReport
  -> runtime package build or WorldStateDeltaTransaction build
```

## 允许表达

- source staging manifest 的本地引用。
- 被审查的 staged artifact 列表。
- source staging、local refs、media、semantic、human review、simulation 等门禁状态。
- promotion decision：阻断、拒绝，或批准进入后续构建阶段。
- promotion target 的本地 refs。

## 禁止表达

- API key、secret、token、`.env` 内容。
- prompt 正文。
- provider 响应正文。
- full trace 或 raw JSON。
- provider 临时 URL。
- 报告自身直接修改 runtime package 或世界状态。
- 在门禁未通过时声明可运行。

## 关键边界

`ProviderArtifactPromotionReport` 本身永远是 report-only：

```text
authority.report_only = true
authority.direct_runtime_mutation_allowed = false
authority.direct_world_mutation_allowed = false
```

即使未来报告给出 approved decision，也只是允许后续构建器生成 runtime package 或 WorldStateDeltaTransaction。真正写入 runtime / world state 的动作必须由对应构建器和独立 validator 完成。

图片候选可以给出更强的阻断决策。`p1b_provider_image_artifact_promotion_report.example.json` 使用 `blocked_validation_failed`，表达 source staging / local ref 已合法，但 media gate 与 semantic gate 已失败；这类报告必须保持 `promotion_targets.target_kind = none`，并把下一步收敛到控制图重生、paintover、media gate、semantic gate 和 human review。

## 验收命令

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_provider_artifact_promotion_report.v0.1.json
python3 tools/dev/validate_provider_artifact_promotion_report.py examples/provider_artifact_staging/p1b_provider_artifact_promotion_report.example.json
python3 tools/dev/validate_provider_artifact_promotion_report.py examples/provider_artifact_staging/p1b_provider_image_artifact_promotion_report.example.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_provider_artifact_promotion python3 -m py_compile tools/dev/validate_provider_artifact_promotion_report.py tools/demo/export_evidence.py
python3 -m json.tool shared/schemas/provider_artifact_promotion_report.v0.1.schema.json >/tmp/provider_artifact_promotion_report.schema.pretty.json
git diff --check
```

如果任务会接入演示证据，再运行：

```bash
python3 tools/demo/export_evidence.py --output-dir /tmp/provider_artifact_promotion_report_evidence
```
