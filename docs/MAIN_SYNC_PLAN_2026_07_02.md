# main 受控同步计划 2026-07-02

本文只是一份同步清单，不执行合并，不修改 `main` 工作区。

## 1. 当前状态

当前分支状态：

- `main`：`b893f76 docs: record worktree collaboration setup`
- `develop`：`e6ce5d4 docs: close map compile queue items`
- `main` 工作区存在未提交用户草稿：`docs/ASSET_GRAPH_COMPILER_V0_1.md`

重要结论：

> 现在不应直接把 `develop` 快进或覆盖到 `main`，因为 `main` 上存在用户未提交草稿，并且 `develop` 也修改了同名文档。

## 2. develop 相对 main 的同步范围

`develop` 相对 `main` 已经不只是文档分支，而是完整 MVP 集成线。主要新增范围：

- 后端：FastAPI、SQLite、匿名 session、frontend mock API、research proposal / job API。
- 前端：无构建 MVP shell、玩家流程、战斗画面、拖拽部署、API/static fallback 数据适配。
- 内容：MVP 世界书 fixture、开局配置、大地图、战斗配置、NPC、材料。
- 编译器：AssetGraph、DAG workflow、runtime package、locked manifest、MapRuntimePackage、MapCompilePackage。
- 媒体：前端 mock 图片、runtime art、地图视觉参考、发布底图、processed PNG manifest。
- 叙事 / 世界状态：WorldStateDelta、RunWorldState、多阶段 narrative bundle、stage candidate、review pack。
- 证据：demo evidence exporter、handoff audit、compiler dossier、视觉运行态审计。
- 治理：任务队列、协作规则、当前架构索引。

这意味着下一次同步不是“挑几份文档更新”，而更像把 `develop` 晋级为新的稳定主线。

## 3. 绝对不能覆盖的内容

同步前必须保护：

```text
main: docs/ASSET_GRAPH_COMPILER_V0_1.md
```

原因：

- 这是 `main` 工作区里的用户未提交改动。
- `develop` 也包含同名文件的大量更新。
- 直接切分支、reset、checkout 或覆盖会丢失用户草稿。

推荐处理方式：

1. 先在 `main` 读取用户草稿并保存 diff 摘要。
2. 在单独临时文件或分支中三方合并：
   - `main` 原始版本
   - `main` 用户草稿
   - `develop` 最新版本
3. 由主代理 / 用户确认合并后的 `docs/ASSET_GRAPH_COMPILER_V0_1.md`。
4. 再执行 main 同步。

## 4. 推荐同步策略

推荐采用“保护草稿后晋级 develop”的策略：

```text
Step 1: 在 main 上确认未提交草稿内容
Step 2: 生成 docs/ASSET_GRAPH_COMPILER_V0_1.md 的人工合并版本
Step 3: 确认 develop 当前验证全部通过
Step 4: 将 main 更新到 develop
Step 5: 应用人工合并后的 ASSET_GRAPH 文档
Step 6: 运行 smoke validation
Step 7: 再考虑推送远程
```

不推荐：

- 不推荐 `git reset --hard develop`。
- 不推荐在有用户草稿时 `git checkout develop -- docs/ASSET_GRAPH_COMPILER_V0_1.md`。
- 不推荐把 `main` 的用户草稿丢给 worker 自行猜测合并。

## 5. 同步前验证清单

在 `develop` 上至少运行：

```bash
node --check frontend/app.js
python3 -m compileall backend tools
python3 tools/asset_graph/validate_map_runtime_package.py examples/map_runtime_packages/mvp_first_battle.map_runtime_package.json
python3 tools/asset_graph/validate_map_runtime_package.py examples/map_runtime_packages/mvp_wick_store_pressure.map_runtime_package.json
python3 tools/asset_graph/validate_map_runtime_package.py examples/map_runtime_packages/mvp_old_signal_tower_pressure.map_runtime_package.json
python3 tools/asset_graph/validate_map_compile_package.py examples/map_compile_packages/mvp_first_battle.map_compile_package.json
python3 tools/asset_graph/validate_map_compile_package.py examples/map_compile_packages/mvp_wick_store_pressure.map_compile_package.json
python3 tools/asset_graph/validate_map_compile_package.py examples/map_compile_packages/mvp_old_signal_tower_pressure.map_compile_package.json
python3 tools/demo/export_evidence.py --output-dir /tmp/ai_td_demo_evidence_main_sync
python3 -m json.tool /tmp/ai_td_demo_evidence_main_sync/evidence.json
```

完整后端测试需要依赖：

```bash
python3 -m pip install -r requirements.txt
python3 -m pytest backend/tests
```

当前环境缺少 `fastapi`、`pydantic`、`pytest`、`httpx`、`uvicorn` 时，完整后端测试不能作为同步前硬门，但必须记录。

## 6. 同步后 smoke 清单

同步到 `main` 后至少检查：

```bash
git status --short --branch
node --check frontend/app.js
python3 -m compileall backend tools
python3 tools/demo/export_evidence.py --output-dir /tmp/ai_td_demo_evidence_main_after_sync
```

若本机有浏览器，还应补做：

```bash
python3 -m http.server 8765
npx playwright screenshot http://127.0.0.1:8765/frontend/index.html /tmp/ai_td_frontend_after_main_sync.png
```

## 7. 需要人工确认的问题

同步前需要人工或主代理确认：

1. `main` 上的 `docs/ASSET_GRAPH_COMPILER_V0_1.md` 草稿是否要完整保留、部分合入，还是另存为历史草稿。
2. 是否把 `develop` 当前全部内容晋级为 `main`，还是只同步文档和 MVP 运行所需子集。
3. 是否现在推送远程 `git@github.com:zty1017/ai-towerdefense.git`。此前用户要求“先不要提交远程”，因此默认不 push。

## 8. 当前建议

当前建议是：

- 暂不直接同步 `main`。
- 先由主代理读取并合并 `docs/ASSET_GRAPH_COMPILER_V0_1.md` 的用户草稿。
- 确认后再把 `develop` 晋级为 `main`。
- 晋级后立即运行 evidence export，确保地图编译包、前端视觉防线和最新任务队列都在 `main` 可见。
