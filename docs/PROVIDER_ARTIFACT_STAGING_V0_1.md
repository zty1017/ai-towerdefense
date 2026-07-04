# ProviderArtifactStaging v0.1

本文定义 `ProviderOutputEnvelope` 之后、正式 media / semantic / promotion gate 之前的本地候选产物暂存层。

它不是 provider 原始输出，不是 runtime package，不是 WorldStateDelta，也不是前端可直接消费的素材入口。它只负责把已经转成本地文件的候选 artifact 登记为 review-only evidence，并说明下一步还需要哪些门禁。

## 事实源

- Schema: `shared/schemas/provider_artifact_staging_manifest.v0.1.schema.json`
- Validator: `tools/dev/validate_provider_artifact_staging_manifest.py`
- Example: `examples/provider_artifact_staging/p1b_provider_artifact_staging.example.json`
- Source envelope example: `examples/provider_artifact_staging/p1b_provider_artifact_staging.source_envelope.json`
- Image failure example: `examples/provider_artifact_staging/p1b_provider_image_artifact_staging.example.json`
- Image source envelope example: `examples/provider_artifact_staging/p1b_provider_image_artifact_staging.source_envelope.json`

## 在编译链路中的位置

```text
Generation Scheduler live executor guard
  -> explicit authorization
  -> provider adapter call
  -> ProviderOutputEnvelope
  -> ProviderArtifactStagingManifest
  -> media gate / semantic gate / human review
  -> promotion report
  -> runtime package or WorldStateDeltaTransaction
```

`ProviderOutputEnvelope` 定义 provider 调用后允许保留什么；`ProviderArtifactStagingManifest` 定义这些本地 refs 如何进入审查暂存区。

## 允许保存

- source envelope 的本地引用和 envelope id。
- 本地候选 artifact refs。
- artifact 的 kind、content type、role、review status。
- source envelope gate、local ref gate、schema gate、media gate、semantic gate、human review 的状态。
- promotion gate 的阻断原因和下一步门禁。

## 禁止保存

- API key、secret、token、`.env` 内容。
- prompt 正文。
- provider 响应正文。
- full trace 或 raw JSON。
- provider 临时 URL。
- runtime-ready 声明。
- 玩家可见或运行时可激活语义。

所有暂存 artifact 必须是本地路径。图片、视频、音频等媒体候选如果来自 provider 临时 URL，必须先下载或转存为本地文件，再进入 staging。临时 URL 不能进入 runtime，也不能作为可发布资源。

## Promotion Gate

`ProviderArtifactStagingManifest v0.1` 永远不能直接激活内容：

```text
authority.review_only = true
authority.runtime_activation_allowed = false
authority.world_mutation_allowed = false
promotion_gate.promotion_allowed = false
```

后续至少需要：

- media gate 或 schema gate
- semantic gate 或 gameplay simulation
- human / visual review
- promotion report
- runtime package 或 WorldStateDeltaTransaction

## 与媒体管线的关系

对于图片、视频、atlas、地图视觉层等媒体候选，staging 只解决“本地文件登记和审查入口”的问题。它不负责抠图、裁剪、关键帧抽取、atlas 打包、地图拓扑对齐或视觉晋升。

这些后续步骤应继续由 `MEDIA_ASSET_QUALITY_PIPELINE_V0_2.md`、`VIDEO_FRAME_ASSET_PIPELINE_V0_1.md`、`MapRuntimePackage` / `MapCompilePackage` 以及对应 validator / review pack 处理。

图片候选即使已经通过 provider adapter 下载成本地 PNG，也不能因此进入玩家 runtime。`p1b_provider_image_artifact_staging.example.json` 专门作为负样本闭环：source envelope 和 local ref 合法，但 media / semantic gate 失败，因此 `staging_status = validation_failed`，`promotion_gate.blocked_reason = validation_failed`。

该模式用于防止低质量地图图、带控制图残留的生成图、与路径 / 塔位 / 目标语义不一致的生成图被误当作可发布素材。它们可以保留为 review-only evidence 和 prompt-repair 约束 / paintover 输入，但不能更新 `MapRuntimePackage`、published visual layer、runtime package 或世界状态。

## 验收命令

```bash
python3 tools/dev/validate_worker_task_pack.py examples/worker_task_packs/p1b_provider_artifact_staging.v0.1.json
python3 tools/dev/validate_provider_artifact_staging_manifest.py examples/provider_artifact_staging/p1b_provider_artifact_staging.example.json
python3 tools/dev/validate_provider_artifact_staging_manifest.py examples/provider_artifact_staging/p1b_provider_image_artifact_staging.example.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_provider_artifact_staging python3 -m py_compile tools/dev/validate_provider_artifact_staging_manifest.py
python3 -m json.tool shared/schemas/provider_artifact_staging_manifest.v0.1.schema.json >/tmp/provider_artifact_staging.schema.pretty.json
git diff --check
```

如果任务会接入演示证据，再运行：

```bash
python3 tools/demo/export_evidence.py --output-dir /tmp/provider_artifact_staging_evidence
```
