# MVP 审查交付入口 v0.1

本文档是当前 AI 编译系统的审查入口。它不表示正式前端已经接入，也不表示所有媒体资产已经达到最终品质；它用于证明当前 MVP 的 AI 编译流水线、内容产物和验证证据已经可以被集中审查。

## 一键审查

日常改动先跑快速质量门，确认静态合同、readiness 和前端关键入口没有被破坏：

```bash
python3 tools/dev/run_fast_quality_gate.py
```

若要运行后端测试或重新生成审查包，先检查完整测试环境：

```bash
python3 tools/dev/check_test_env.py
```

若报告缺少 `pytest`、`fastapi`、`httpx` 等依赖，先执行：

```bash
python3 -m pip install -r requirements.txt
```

运行：

```bash
python3 tools/content_pipeline/run_mvp_handoff_audit.py --validate
```

默认输出：

```text
examples/review_packs/mvp_handoff_audit_report.v0.1.json
```

独立校验：

```bash
python3 tools/content_pipeline/validate_mvp_handoff_audit_report.py examples/review_packs/mvp_handoff_audit_report.v0.1.json
```

录屏或评审前运行完整 evidence suite：

```bash
python3 tools/demo/run_demo_evidence_suite.py --output-root /tmp/ai_td_demo_evidence_suite
```

完整 suite 默认先执行 `tools/dev/check_generation_scheduler_review_only_pipeline.py` 和 `tools/dev/check_provider_runner_handoff_outbox_import_pipeline.py`，再执行浏览器玩家链路截图和统一 evidence 导出。scheduler smoke 与 outbox import smoke 都只产生本地 review-only 证据：provider 调用、世界修改和 runtime 激活计数都必须为 0；outbox import smoke 会额外证明导入前 prefetch-cache 没有 ready envelope、导入后出现 2 个 review-only envelope。它们不代表 live provider、真实图生视频、runtime package 构建或 WorldStateDeltaTransaction 写入已经完成。默认 `--scheduler-smoke-runner auto` 会优先使用仓库 `.venv/bin/python` 加快本地复跑；没有 `.venv` 时自动回退 `uv run`，suite report 会记录实际 runner。

当前环境没有浏览器时，必须显式使用降级参数并保留报告：

```bash
python3 tools/demo/run_demo_evidence_suite.py --allow-missing-browser --output-root /tmp/ai_td_demo_evidence_suite
```

## 审查顺序

建议按以下顺序看：

1. `examples/review_packs/mvp_handoff_audit_report.v0.1.json`
   - 看 `overall_status`、`command_results`、`coverage_checks` 和 `known_risks`。
2. `examples/review_packs/mvp_compiler_review_dossier.v0.1.json`
   - 看总流水线、source evidence、readiness summary 和验证命令。
3. `examples/review_packs/mvp_multistage_stage_candidate_pack.v0.1.json`
   - 逐阶段审查世界线、玩家线、任务、随机事件、资产候选和 runtime 引用。
4. `examples/frontend_mock/frontend_mock_pack.v0.1.json`
   - 审查前端并行开发可使用的玩家安全数据包。
5. `examples/runtime_packages/*.runtime_package.json`
   - 审查战斗运行时证据包。
6. `examples/map_runtime_packages/*.map_runtime_package.json`
   - 审查地图运行时包，确认路径、塔位、目标、出生点和视觉层引用。

## 当前证明范围

当前 handoff audit 证明：

- 多阶段内容链存在：Stage 05 / 06 / 07。
- 每个阶段都覆盖世界线和玩家线。
- 每个阶段至少有一个可玩资产候选。
- 可编译对象目录覆盖 100 个以上对象，包含实体、叙事、关卡、经济、成长、规则和表现层。
- 前端 mock 内容包包含 11 个可玩资产、3 个阶段摘要和 3 个 runtime package 摘要。
- 三个 runtime package 均可通过运行时包校验。
- 三个 map runtime package 均可通过地图运行时包校验。
- 当前前端已可消费首战 MapRuntimePackage；后续节点已有地图包，但完整战斗链路仍需继续打磨。

## 当前不证明范围

当前 handoff audit 不证明：

- 前端页面已经实现并正式消费这些数据。
- 所有资产都有最终可用的高质量媒体资源。
- 所有真实外部服务调用在任意环境下都稳定。
- Stage 06 / Stage 07 已经有战斗 runtime package。

## AI 编译流水线摘要

当前 MVP 的离线审查流水线是：

```text
对象计划
  -> 叙事包
  -> WorldStateDelta
  -> 语义门
  -> 下一运行态
  -> 资产提案
  -> 候选资产
  -> 校验 / 模拟 / 评分 / 晋级策略
  -> locked manifest / runtime package / frontend mock pack
  -> 总审查交付包
  -> handoff audit report
```

其中：

- 叙事包只表达意图，不直接修改运行态。
- WorldStateDelta 才能提交任务、随机事件、素材、NPC、地图节点和蓝图变化。
- 候选资产必须经过效果白名单、模拟、评分和晋级策略。
- 前端 mock pack 只抽取玩家安全数据。
- runtime package 只引用 locked manifest 和 battle config 中允许暴露的运行时内容。
