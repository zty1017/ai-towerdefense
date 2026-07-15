# Compiler 腾讯云部署说明

比赛公开实例：`http://1.15.67.144/frontend/index.html`

当前部署使用 Docker 中的 Python 3.12 与 Uvicorn，监听公网 80 端口。代码、依赖、SQLite 数据和运行时媒体分别挂载，容器设置为自动重启。公开实例关闭真实 Provider，避免匿名访问消耗 API 配额；玩家研发仍会走相同 Schema、模拟、晋升和激活协议，并在 Provider 不可用时使用已审查兜底内容。

## 更新

从 `develop` 工作区增量同步运行文件后重启容器：

```bash
rsync -az --delete -e ssh ./ tencent:/home/ubuntu/compiler/
ssh tencent 'sudo docker restart compiler-demo'
```

实际发布时应继续排除 `.git`、`.venv`、`.env`、缓存、测试数据库和历史探索候选。

## 验收

```bash
curl http://1.15.67.144/api/health
curl http://1.15.67.144/api/world-catalog
```

浏览器必须继续验证档案、世界配置、开场、大地图、工坊、战斗和结算，不以健康检查代替玩家流程验收。
