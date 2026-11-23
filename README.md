# 知维 OS · Zhiwei OS

知维 OS 是一个带长期记忆的 AI 工作台。你可以在对话后检索保存的记忆，在知识图谱中查看关联，也可以让多个 Agent 按工作流协作。例如，「会议纪要转培训」场景将一份纪要依次交给会议、知识和培训 Agent，并记录每一步的执行结果。

![知维 OS 工作台首页](zhiwei-os-video/public/ui/home.png)

## 从哪里开始

| 想做什么 | 打开哪个页面 |
| --- | --- |
| 与助手对话，再查看保存的记忆 | `/chat`、`/memory` |
| 查看知识之间的关联 | `/graph` |
| 体验会议纪要转培训，查看工作流执行记录 | `/agents/scenarios`、`/agents/executions` |
| 浏览和安装 Agent | `/agent-marketplace` |
| 查看数据源同步任务 | `/sync` |

## 本地运行

以下命令使用 Windows PowerShell。准备 Python 3.11、Node.js 20 或 22 和 npm，然后克隆仓库。使用 GitHub 的 **Code → Download ZIP** 也可以，解压后在包含 `main.py` 的目录打开终端。

```powershell
git clone https://github.com/wangweilp/-agent.git zhiwei-os
cd zhiwei-os
```

**1. 配置后端。** 首次运行时创建虚拟环境，将配置模板复制为项目根目录的 `.env`。

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item config/.env.template .env
New-Item -ItemType Directory -Force data | Out-Null
```

在 `.env` 中填写自己的 `DEEPSEEK_API_KEY` 以使用模型对话。默认配置使用 SQLite 保存结构化数据，使用 ChromaDB 保存向量。首次加载默认中文向量模型 `BAAI/bge-small-zh-v1.5` 可能需要联网下载。

**2. 启动 API。** 在项目根目录运行以下命令，然后打开 [API 文档](http://127.0.0.1:8000/docs)。

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

**3. 启动工作台。** 在项目根目录打开第二个终端。

```powershell
cd frontend
npm ci
npm run dev
```

打开 [本地工作台](http://localhost:3000)。要体验多 Agent 协作，进入[业务场景](http://localhost:3000/agents/scenarios)，按[企业 Agent 演示指南](docs/STEP20D_DEMO_SCRIPT.md)运行示例。

## 开发与验证

后端入口是 `main.py`。`src/core/` 定义核心类型和协议，`src/adapters/` 对接模型与存储，`src/api/` 提供 HTTP 接口。`src/sync/` 实现同步任务的调度、执行与恢复。前端位于 `frontend/`，使用 Next.js、React 和 TypeScript。

在项目根目录运行同步任务的回归测试，覆盖工作进程中断后的恢复、取消任务、并发重复执行和跨租户隔离。

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_sync/test_p1_lifecycle.py tests/test_sync/test_cross_tenant_isolation.py
```

完整后端测试使用 `python -m pytest`（先激活虚拟环境）。前端测试在 `frontend/` 下运行 `npm test`，类型检查使用 `npm run typecheck`。

## 项目文档

- [架构设计](docs/ARCHITECTURE.md)
- [Agent 市场演示](docs/STEP21_MARKETPLACE_DEMO_SCRIPT.md)
- [开发者开放平台演示](docs/STEP22_OPEN_PLATFORM_DEMO_SCRIPT.md)
- [开发过程、分阶段说明与运行记录](DEVELOPMENT_NOTES.md)
