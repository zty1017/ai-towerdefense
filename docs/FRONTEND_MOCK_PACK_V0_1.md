# 前端 Mock 内容包 v0.1

本文档说明 `FrontendMockPack v0.1` 的用途、边界和验收方式。

这不是正式前端接入，也不是玩家生产环境数据。它是给前端、后端和评审并行使用的玩家安全内容包：把世界书基础信息、开局地图、NPC、材料、剧情入口、多阶段阶段摘要、runtime package 引用和可玩资产统一放进一个 JSON 文件。

默认构建命令：

```bash
python3 tools/content_pipeline/build_frontend_mock_pack.py
```

默认输出：

```text
examples/frontend_mock/frontend_mock_pack.v0.1.json
```

## 当前内容

当前 mock pack 包含：

- 11 个可玩资产：防御塔、支援道具、临时改造和情报资产。
- 3 个多阶段阶段摘要：旧信号塔回光压力、旧塔回声测标、东侧分潮遏制。
- 3 个 runtime package 摘要：第一战、灯芯仓压力战、旧信号塔压力战。
- 世界书基础信息、开局地图、第一危机节点、NPC、材料和开场剧情。
- effect catalog、visual recipes、fallback media token 和已生成媒体引用。

## 边界

构建器明确保证：

- 不读取 `.env`。
- 不调用外部模型或媒体服务。
- 不包含 provider、model、raw prompt、raw JSON、full trace、api key 或 secret。
- 不把 review-only 内容伪装成正式 campaign router。
- 不要求前端已经实现正式加载逻辑。

## 和审查包的关系

`frontend_mock_pack.v0.1.json` 是从当前编译产物和审查包中抽取出的玩家安全子集。它引用：

- `mvp_multistage_content_pack.v0.1.json`
- `mvp_multistage_stage_candidate_pack.v0.1.json`
- `mvp_demo.runtime_package.json`
- `mvp_wick_store_pressure.runtime_package.json`
- `mvp_old_signal_tower.runtime_package.json`

前端可以先使用这个包开发页面和交互，但正式运行时仍应以后端 API、locked manifest 和 runtime package 为准。

## 验收命令

```bash
python3 tools/content_pipeline/build_frontend_mock_pack.py
python3 tools/content_pipeline/validate_frontend_mock_pack.py examples/frontend_mock/frontend_mock_pack.v0.1.json
```

校验器会检查：

- 所有前端 mock 资产都可部署或可用 fallback 渲染。
- 必须覆盖防御塔、支援道具、临时改造和情报资产。
- visual recipes 只引用 effect catalog 中的特效 primitive。
- stage outline 引用的资产必须存在于 `assets`。
- stage outline 引用的 runtime package 必须存在于 `runtime_packages`。
- 不允许出现 provider、model、raw prompt、full trace、api key 等技术或敏感字段。
