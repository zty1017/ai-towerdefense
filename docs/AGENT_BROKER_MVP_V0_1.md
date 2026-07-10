# 临时 Agent Worker

## 定位

这是比赛最后几天使用的一次性自动委派脚手架，不是长期 Agent 平台。

它只有两个正式入口：

- `agentctl.py`：把现有 `WorkerTaskPack v0.1` 复制到 `/tmp` 文件队列，查询结果。
- `agent_worker.py`：由用户在普通 WSL 终端或 tmux 中启动，领取任务并调用 CodeBuddy / Codex。

没有 systemd、数据库、HTTP、Unix socket、Web UI、自动重试、自动提交、自动合并、自动推送或自动删除 worktree。比赛后可以整体删除 `tools/agent_broker/` 和本文档。

## 路由

| 难度 | 执行器 |
|---|---|
| `low` / `medium_low` | CodeBuddy HY3，tmux 交互模式 |
| `medium_high` / `high` | CodeBuddy GLM-5.2，tmux 交互模式 |
| `extreme` | Codex headless |

可以用 `--executor codebuddy` 或 `--executor codex` 显式覆盖自动路由。

## 一次启动

当前 task worktree 尚未合并时，可以立即从这里启动：

```bash
tmux new-session -d \
  -s ai-td-agent-worker \
  -c /home/zty/projects/ai-compiled-towerdefense-worktrees/task-agent-broker-mvp \
  'python3 tools/agent_broker/agent_worker.py --loop --allow-external'
```

Broker 合入 `develop` 后，在普通 WSL 终端执行一次：

```bash
tmux new-session -d \
  -s ai-td-agent-worker \
  -c /home/zty/projects/ai-compiled-towerdefense-develop \
  'python3 tools/agent_broker/agent_worker.py --loop --allow-external'
```

检查 worker：

```bash
tmux has-session -t ai-td-agent-worker
```

此 tmux 进程由用户终端启动，不属于 Codex 沙箱的进程树。Codex 后续只写 `/tmp` 文件任务，不直接启动外部模型 CLI。

## 委派

先检查路由，不入队：

```bash
python3 tools/agent_broker/agentctl.py delegate \
  --task-pack examples/worker_task_packs/<task>.json \
  --difficulty medium_high \
  --dry-run
```

真实入队：

```bash
python3 tools/agent_broker/agentctl.py delegate \
  --task-pack examples/worker_task_packs/<task>.json \
  --difficulty medium_high \
  --authorize-external
```

等待并输出结果：

```bash
python3 tools/agent_broker/agentctl.py wait <dispatch_id> --timeout 3600
```

其他命令：

```bash
python3 tools/agent_broker/agentctl.py list
python3 tools/agent_broker/agentctl.py status <dispatch_id>
python3 tools/agent_broker/agentctl.py result <dispatch_id>
```

默认总线是 `/tmp/ai-td-agent-broker-$UID`。也可以让用户终端和 Codex 同时设置 `AI_TD_AGENT_BROKER_HOME` 覆盖。

## 交互确认

CodeBuddy 默认使用 `--permission-mode auto`。如果它等待确认，worker 超时结果会给出 tmux session 名；直接进入即可：

```bash
tmux attach -t <session_name>
```

确实需要完全放开隔离 worktree 权限时，在启动 worker 前设置：

```bash
export AI_TD_CODEBUDDY_PERMISSION_MODE=bypassPermissions
```

该设置只建议用于任务边界清晰、无密钥、可丢弃的 `task/*` worktree。

## Worker 行为

1. 校验 WorkerTaskPack。
2. 只接受 `base_branch=develop`、`branch=task/*`。
3. 若 worktree 不存在则创建；已存在时必须分支正确且启动前干净。
4. 启动外部 agent。
5. CodeBuddy 通过本地 `worker-complete` 命令报告结束；Codex 以进程退出码报告结束。
6. 若任务声明 `acceptance_profile`，worker 再运行一次标准 profile runner。
7. 检查所有改动是否位于 `allowed_paths`，并拒绝 `forbidden_paths`。
8. 写结构化结果，交给主会话审查。

worker 不会 commit、merge、push 或清理 worktree。主会话仍负责最终代码审查、测试、合并和发布判断。

## 本地验收

以下 smoke 不创建 worktree，也不调用外部 agent：

```bash
PYTHONPYCACHEPREFIX=/tmp/ai_td_agent_broker_pycache \
  python3 -m py_compile \
  tools/agent_broker/agentctl.py \
  tools/agent_broker/agent_worker.py \
  tools/agent_broker/check_agent_broker_smoke.py

python3 tools/agent_broker/check_agent_broker_smoke.py
git diff --check
```

## 明确不做

- 不处理多机、GPU、优先级或并发 worker。
- 不自动回答 CodeBuddy 的产品/架构问题。
- 不做失败后自动修复循环。
- 不替代 WorkerTaskPack、Git 治理或主会话验收。
- 不保证比赛后继续维护。
