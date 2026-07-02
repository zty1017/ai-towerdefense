# ProviderOutputEnvelope v0.1

本文定义真实 provider 调用之后，或者 provider 调用被 guard 阻断时，项目允许保存的最小安全信封。

它不是 provider 原始响应，不是 prompt 记录，不是 runtime package，也不是 world state。它只保存脱敏摘要、artifact refs、校验状态和 activation gate。

## 事实源

- Schema: `shared/schemas/provider_output_envelope.v0.1.schema.json`
- Validator: `tools/dev/validate_provider_output_envelope.py`
- Example: `examples/provider_output_envelopes/p1b_provider_output_envelope.example.json`

## 在编译链路中的位置

```text
Generation Scheduler live executor guard
  -> explicit authorization
  -> provider adapter call
  -> ProviderOutputEnvelope
  -> schema / semantic / media gate
  -> review-only artifact manifest
  -> promotion report
  -> runtime / world transaction
```

当前 v0.1 只定义 envelope 和 validator，不调用真实 provider。

## 允许保存

- provider profile / mode 等非敏感执行摘要。
- source run / schedule item / object ref。
- redacted request summary。
- redacted result summary。
- 本地 artifact refs。
- validator / semantic gate / media gate / human review 状态。
- activation gate 阻断原因。

## 禁止保存

- API key、secret、token、`.env` 内容。
- prompt 正文。
- provider 响应正文。
- provider trace、full trace、raw JSON。
- 未审查内容的 runtime-ready 声明。
- provider 返回的临时 URL 作为可发布资源。

真实 provider 产物如果是图片、视频或音频，必须先下载或转存为本地 artifact ref，再进入 media gate。临时 URL 不能被 runtime 直接消费。

## Activation Gate

`ProviderOutputEnvelope v0.1` 永远不能直接激活内容：

```text
authority.review_only = true
authority.runtime_activation_allowed = false
authority.world_mutation_allowed = false
activation_gate.activation_allowed = false
```

即使 provider 调用成功，后续也必须经过：

- schema or media validation
- semantic gate or gameplay simulation
- manual / visual review
- promotion report
- runtime package 或 WorldStateDeltaTransaction

## 验收命令

```bash
python3 tools/dev/validate_provider_output_envelope.py examples/provider_output_envelopes/p1b_provider_output_envelope.example.json
PYTHONPYCACHEPREFIX=/tmp/ai_td_pycache_provider_envelope python3 -m py_compile tools/dev/validate_provider_output_envelope.py
python3 -m json.tool shared/schemas/provider_output_envelope.v0.1.schema.json >/tmp/provider_output_envelope.schema.pretty.json
git diff --check
```

如果任务会接入演示证据，再运行：

```bash
python3 tools/demo/export_evidence.py --output-dir /tmp/provider_output_envelope_evidence
```
