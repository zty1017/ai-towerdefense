# Stage Candidate Pack v0.1

本文档说明 `StageCandidatePack v0.1` 的用途、边界和验收方式。

它不是玩家侧数据，也不是前端 runtime package。它是给项目负责人、代码代理和评审者使用的阶段候选审查单元：把一个阶段的剧情节点、世界状态变化、玩法对象输出、资产输出、战斗 runtime 引用和验证门放在同一个 JSON 包里。

## 为什么需要它

当前项目的“剧情编译”不应该只生成剧情文本。每个阶段都应该服务玩法，并且能落到受控对象：

- 世界线推进：地图节点、NPC、资源、世界事实、阵营压力。
- 玩家线推进：任务、随机事件、研发机会、临时样品、蓝图。
- 战斗准备：可用资产、战斗节点、runtime package 引用。
- 审查边界：哪些内容已可用，哪些只是候选，哪些仍需人工复核。

`StageCandidatePack` 的作用是把这些内容绑定起来，避免后续真实 LLM 只提交一段好看的故事，却没有提交可验证的玩法增量。

## 产出文件

- `examples/review_packs/mvp_stage_candidate_pack.v0.1.json`
- `shared/schemas/stage_candidate_pack.v0.1.schema.json`
- `tools/content_pipeline/build_stage_candidate_pack.py`
- `tools/content_pipeline/validate_stage_candidate_pack.py`

默认构建命令：

```bash
python3 tools/content_pipeline/build_stage_candidate_pack.py --validate
```

单独校验命令：

```bash
python3 tools/content_pipeline/validate_stage_candidate_pack.py examples/review_packs/mvp_stage_candidate_pack.v0.1.json
```

## 数据边界

`StageCandidatePack` 明确标记：

- `visibility: review_only`
- 不接入前端。
- 构建器不读取 `.env`。
- 构建器不调用 provider。
- 不修改基础世界书。
- runtime package 只做引用，不内嵌完整玩家加载包。

包内禁止保存 provider、model、raw prompt、full trace、raw JSON、API key、secret、未审查原始内容等技术细节。玩家侧体验不应该看到这些信息。

## 主要结构

每个 `stage_candidates[]` 包含：

- `source_files`：剧情 bundle、WorldStateDelta、可选 battle config。
- `lane_coverage`：世界线、玩家线或共享线覆盖情况；战斗、研发等更细分类由玩法对象输出和验证门体现。
- `narrative_summary`：剧情节点数量、玩法目的和 hook。
- `delta_summary`：WorldStateDelta op 数量与类型统计。
- `gameplay_outputs`：地图节点、NPC、资源、事实、flag、任务、随机事件、研发任务、样品和蓝图。
- `asset_outputs`：本阶段相关资产的 promotion 状态和后续动作。
- `runtime_package_refs`：该阶段已存在的战斗 runtime package 引用。
- `validation_gates`：剧情 bundle、WorldStateDelta、剧情玩法契约、资产晋升、runtime package 引用等门禁。
- `next_actions`：下一步需要人工或代理处理的动作。

## 当前 MVP 结论

当前 MVP 包含四个 reviewed fixture 阶段：

1. 灰灯驿站首防。
2. 黎明复盘与补给线。
3. 北路侦测。
4. 灯芯仓压力战。

阶段 1 和阶段 4 已有关联 runtime package。阶段 2 和阶段 3 主要服务复盘、侦测、任务、随机事件和研发线，不要求直接生成战斗 runtime package。

当前 readiness 不是“自动上线”，而是 `needs_human_review`：因为仍有候选资产或高风险改造需要人工确认后才能默认进入战斗。

## 后续用法

后续真实 LLM 生成 Stage 05 或更远阶段时，不应只输出自然语言故事。推荐流程是：

1. 生成候选 `NarrativeEventBundle`。
2. 生成候选 `WorldStateDelta`。
3. 通过结构校验和语义门。
4. 汇总任务、随机事件、NPC、资源、研发机会和资产需求。
5. 形成 `StageCandidatePack`。
6. 人工或高权限代理审查后，才允许进入 runtime package 或正式 run state。

这让“世界书生长”始终服务玩法和游戏进度，而不是自由扩写设定。
