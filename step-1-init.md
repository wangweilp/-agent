# 第 1 步：项目初始化与 Git 管理

请按以下要求创建项目骨架，并用 git 管理。

## 目录结构
```
D:\代码\day2\
├── src/
│   ├── core/          # 领域层 — 纯逻辑，零外部依赖
│   ├── adapters/      # 适配器层 — 封装所有外部 I/O
│   ├── api/           # 接口层 — FastAPI 路由
│   └── tools/         # 工具层 — Agent 可调用的工具函数
├── tests/
│   ├── test_core/
│   ├── test_adapters/
│   └── test_tools/
├── docs/              # 设计文档，后面步骤会填充
├── config/            # .env.template
├── data/              # 运行时数据（gitignore）
├── main.py            # 启动入口（依赖注入）
├── requirements.txt
├── CLAUDE.md          # 项目专属开发规则（后面步骤会写）
└── .gitignore
```

## 要求
1. 创建所有空目录和 `__init__.py`
2. 创建 `.gitignore`（忽略 venv、__pycache__、.env、*.db、chroma_db、data/）
3. 创建 `requirements.txt`（openai、chromadb、fastapi、uvicorn、sqlite-utils、python-dotenv、pydantic、httpx）
4. 创建 `config/.env.template`（DEEPSEEK_API_KEY、DEEPSEEK_BASE_URL、CHROMA_PERSIST_DIR、SQLITE_DB_PATH 等）
5. `git init` 并完成首次提交
6. 创建 develop 分支

**提交信息格式**：`chore: initialize project skeleton`
