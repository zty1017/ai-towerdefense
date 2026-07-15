# Compiler 黑客松最终演示手册

最后更新：2026-07-15

## 1. 冻结范围

从本手册生效起停止新增世界、地图、对象类型和大规模重构。只允许修复阻断启动、录制、真实编译、部署、结算或证据展示的问题。

演示口径：

- 玩家构想、结构化候选、数值、效果、模拟、晋升、激活和战斗行为实时编译。
- 玩家研发图片在主录制中使用 reviewed fallback，避免视觉 Provider 延迟破坏节奏。
- 主演示地图是人工终审通过的预编译运行包；地图分层编译作为开发期工具链和技术报告证据展示。
- 《长夜灯火》是 MVP 世界书模板，不是项目唯一世界。

## 2. 录制前检查

在 `develop` 工作区执行：

```bash
/home/zty/projects/ai-compiled-towerdefense/.venv/bin/python \
  tools/demo/run_live_compiler_showcase.py \
  --output /tmp/live_compiler_showcase.v0.1.json \
  --dotenv /home/zty/projects/ai-compiled-towerdefense/.env \
  --profile ark_deepseek_v4_flash \
  --media-mode off \
  --max-attempts 2 \
  --allow-provider

/home/zty/projects/ai-compiled-towerdefense/.venv/bin/python \
  tools/demo/validate_live_compiler_showcase_report.py \
  /tmp/live_compiler_showcase.v0.1.json
```

通过标准：塔、陷阱、支援道具 `3/3`，三个 Provider 调用、三个 PromotionReport、三个运行时变更全部通过。该检查在录制前完成，不在录屏中等待三次调用。

最终浏览器证据基线：

```text
/tmp/ai_td_demo_evidence_suite_release_passed/
```

该基线已通过真实 Chromium、14 张主流程截图、6 张多节点战斗截图、2 次拖拽部署、Scheduler 28 步、outbox 导入和 full evidence。

## 3. 启动参数

```bash
cd /home/zty/projects/ai-compiled-towerdefense-develop

AI_TD_ENV_FILE=/home/zty/projects/ai-compiled-towerdefense/.env \
AI_TD_LIVE_COMPILATION=live \
AI_TD_LIVE_MEDIA=off \
AI_TD_LIVE_WORLD_EVOLUTION=auto \
AI_TD_RESEARCH_WORKER_MODE=background \
/home/zty/projects/ai-compiled-towerdefense/.venv/bin/uvicorn \
  app.main:app --app-dir backend --host 0.0.0.0 --port 8001
```

浏览器打开：

```text
http://127.0.0.1:8001/frontend/index.html
```

使用新的无痕窗口创建干净 session。先点击一次页面解锁浏览器音频，确认右上角不是静音状态。

## 4. 五分钟镜头

| 时间 | 画面与操作 | 旁白重点 |
| --- | --- | --- |
| 0:00-0:25 | 本地档案、世界配置、开场卡 | 一个体验链接为评委创建隔离世界实例；《长夜灯火》只是首个模板。 |
| 0:25-0:55 | 可缩放大地图，点击灰灯驿站 | 地图节点、资源和危机由结构化世界状态驱动，不是静态关卡菜单。 |
| 0:55-1:45 | 工坊输入“用铜镜和导光纹做一座命中后向附近两个敌人跳跃的防御塔” | 玩家只描述目标；系统结合世界书、材料、节点和 ABI 生成唯一可试作方案。 |
| 1:45-3:30 | 确认试作并进入战斗；拖放基础塔；等待样品送达；悬停显示范围；部署新塔 | 研发在后台完成。新名称、费用、射程、连锁目标数和战斗行为来自激活包，不是前端写死。部署成功后选择自动取消。 |
| 3:30-4:15 | 完成战斗并进入结算 | 样品表现、NPC 反馈和世界变化回写 session，为后续节点和研发提供上下文。 |
| 4:15-5:00 | 打开脱敏报告或 evidence HTML | 展示 DAG、PromotionReport、RuntimePackage、激活回执和三对象真实 smoke；强调模型输出不能直接执行。 |

证据入口：

```text
examples/review_packs/live_compiler_showcase_report.v0.1.json
/tmp/ai_td_demo_evidence_suite_release_passed/demo_evidence/index.html
docs/HACKATHON_TECHNICAL_REPORT_DRAFT.md
```

## 5. 录制降级策略

- 文本 Provider 超时：不要在玩家画面展示技术错误。保留上一条完整录制，切到已验证的 3/3 脱敏报告说明真实调用结果。
- 样品图片仍为通用图标：这是主录制预设，不是故障。旁白说明媒体与行为独立晋升，行为实时、媒体使用审核兜底。
- 战斗节奏过慢：使用 `4x`，样品出现后恢复正常速度展示范围和连锁效果。
- 音频未播放：先点击页面解锁媒体；仍失败时使用程序化 Web Audio fallback，不临时改代码。
- 新队友改动：先单独分支验收，不在录制前直接覆盖当前 `develop` 基线。

## 6. 最终提交口径

可宣称：三类玩法对象已完成真实 Provider 到战斗执行闭环；前端、多节点战斗、拖拽部署、音频和完整证据套件已通过自动验收。

不可宣称：所有地图、剧情、世界和图片都在玩家游玩时实时生成；当前这些子系统分别处于开发期编译、受控生长或 reviewed fallback 阶段。
