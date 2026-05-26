# 第 1 步：项目初始化与 Git 管理

> ⚠️ 先用 `git status` 和 `git log --oneline` 检查当前状态。

## 任务：创建项目骨架

### 1.1 目录结构
```
D:\代码\day2\
├── src/core/           # 领域层 — 纯逻辑，零外部依赖
├── src/adapters/       # 适配器层 — 封装外部 I/O
├── src/api/            # 接口层 — FastAPI
├── src/tools/          # 工具层 — Agent 可调用工具
├── tests/test_core/
├── tests/test_adapters/
├── tests/test_tools/
├── docs/               # 已有设计文档
├── config/
├── data/
├── CLAUDE.md           # 已有，每次对话前必读
├── main.py             # 依赖注入入口（空文件）
└── .gitignore
```

### 1.2 创建文件
- `requirements.txt`（openai, chromadb, sentence-transformers, fastapi, uvicorn, sqlite-utils, python-dotenv, pydantic, pydantic-settings, httpx）
- `config/.env.template`（DEEPSEEK_API_KEY, CHROMA_PERSIST_DIR, SQLITE_DB_PATH）
- 所有 `__init__.py`（空文件即可）

### 1.3 Git
```bash
git checkout develop
git add -A
git commit -m "chore: initialize v0.1 project skeleton"
```

### 1.4 验证
- `python -c "import openai; print('ok')"` — 确认依赖安装
- `git log --oneline` — 确认提交记录
