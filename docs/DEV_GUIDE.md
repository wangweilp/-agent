# Development Guide: 记忆进化型个人知识助手

## 1. Git 分支策略

### 分支模型
```
master / main     ← 生产就绪代码，只接受 develop 和 hotfix 合并
  └── develop     ← 开发主分支，所有功能从这里切出
       ├── feature/xxx    ← 新功能开发
       ├── fix/xxx        ← Bug 修复
       └── refactor/xxx   ← 重构（不改行为）
```

### 分支命名
- 新功能：`feature/<feature-name>` 例：`feature/tool-registry`
- Bug 修复：`fix/<issue-desc>` 例：`fix/memory-duplicate-key`
- 重构：`refactor/<scope>` 例：`refactor/adapter-interface`

### 提交规范
采用 **Conventional Commits**：
```
<type>(<scope>): <subject>

[optional body]
```

**Type 限定**：
| Type | 用途 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `refactor` | 重构，不改行为 |
| `docs` | 文档变更 |
| `test` | 测试变更 |
| `chore` | 杂项（依赖更新、构建脚本） |
| `style` | 格式（空格、分号，不影响逻辑） |
| `perf` | 性能优化 |

**Scope 限定**：必须是以下之一，保持精确
- `core` — 领域层
- `adapters` — 适配器层
- `api` — 接口层
- `tools` — 工具层
- `docs` — 文档
- `config` — 配置
- `tests` — 测试

**示例**：
```
feat(core): add memory search with vector + keyword hybrid
fix(adapters): handle empty ChromaDB response gracefully
refactor(tools): extract ToolRegistry as standalone module
docs: add architecture decision records
```

**规则**：
- subject 用英文，祈使语气，首字母小写
- 不加句号
- 72 字符以内

---

## 2. 代码风格

### Python
- 严格遵循 **PEP 8**
- 使用 **type hints** 所有公共接口
- 行宽上限 100 字符
- 类名 `PascalCase`，函数/变量 `snake_case`，常量 `UPPER_SNAKE`

### 文档字符串
用 Google 风格 docstring：
```python
def add_memory(content: str, entities: list[str] | None = None) -> Memory:
    """Store a new memory entry and index it for retrieval.

    Args:
        content: The raw text content to store.
        entities: Optional list of named entities extracted from content.

    Returns:
        The persisted Memory object with generated ID and timestamp.

    Raises:
        MemoryStoreError: If storage to either vector DB or SQLite fails.
    """
```

### 导入顺序
1. 标准库
2. 第三方库
3. 项目内部（绝对导入，从 `src.` 开始）
```python
import json
from datetime import datetime
from typing import Protocol, Optional

import chromadb
from fastapi import FastAPI

from src.core.types import Memory, Entity
from src.adapters.llm import DeepSeekAdapter
```

### 抽象与协议
- `core/` 中定义 `Protocol` 或 `ABC`，不在 core 中出现任何 `import chromadb` 或 `from openai import`
- 适配器实现协议，通过 `main.py` 注入

```python
# src/core/memory.py — 协议定义
from typing import Protocol, runtime_checkable

@runtime_checkable
class VectorStore(Protocol):
    def store(self, content: str, embedding: list[float], metadata: dict) -> str: ...
    def search(self, embedding: list[float], k: int) -> list[dict]: ...
    def delete(self, doc_id: str) -> None: ...

# src/adapters/vector_store.py — 适配器实现
class ChromaVectorStore:
    def __init__(self, persist_dir: str):
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._client.get_or_create_collection("memories")

    def store(self, content: str, embedding: list[float], metadata: dict) -> str:
        ...
```

---

## 3. 测试规范

### 文件命名
- 测试文件放在 `tests/`，路径镜像 `src/`
- 文件命名：`test_<模块名>.py`
- 例：`tests/test_core/test_memory.py` 测试 `src/core/memory.py`

### 测试函数
- 命名：`test_<what>_<condition>_<expected>`
- 例：`test_search_returns_empty_list_when_no_match`

### 运行
```bash
python -m pytest tests/ -v
```

### 覆盖率基线
| 阶段 | 目标 |
|------|------|
| 开发中 | `core/` 95%+，`tools/` 90%+ |
| CI | 总覆盖率 ≥ 80% |
| 发布前 | 总覆盖率 ≥ 85% |

---

## 4. 开发工作流

### 日常操作
```bash
# 1. 开新功能
git checkout develop
git pull
git checkout -b feature/my-feature

# 2. 开发 → 测试 → 提交
# (写代码，写测试，跑测试)
git add -A
git commit -m "feat(core): add hybrid memory search"

# 3. 合回 develop
git checkout develop
git pull
git merge feature/my-feature
git push

# 4. 删除特性分支
git branch -d feature/my-feature
```

### 环境
```bash
# 创建虚拟环境
python -m venv venv

# 激活
# Windows:
.\venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 复制配置文件
cp config/.env.template .env
# 编辑 .env，填入真实 API Key
```

### 启动
```bash
# 开发模式
uvicorn main:app --reload

# 直接跑 Agent（终端交互）
python -m src.tools.cli
```

---

## 5. 代码审查检查清单

提交 PR 前自查：

- [ ] `core/` 没有导入 `adapters/`、`api/`、第三方库
- [ ] 所有公共函数有 type hints
- [ ] 新功能有对应测试
- [ ] 提交信息符合 Conventional Commits
- [ ] 没有 print 残留，用 logging
- [ ] 敏感信息（API Key）不在代码中，走 `.env`
- [ ] 不破坏已有测试

---

## 6. 设计决策记录 (ADR)

当遇到需要权衡的技术决策时，在 `docs/adr/` 下创建 ADR：

```markdown
# ADR-001: 选择 ChromaDB 而非 FAISS 作为向量存储

## 背景
需要一个本地零配置的向量数据库。

## 决策
选择 ChromaDB。

## 理由
- pip install 零配置，FAISS 在 Windows 上需要额外编译
- 内置元数据过滤，不需要额外维护 SQLite 索引
- 社区活跃，文档友好

## 后果
- ChromaDB 在大规模场景下性能不如 FAISS，但本项目数据量不构成瓶颈
- 如果未来需要切换到 FAISS/Milvus，只需实现新的 VectorStore 适配器
```

每次创建 ADR 时用递增编号，并在 `docs/adr/README.md` 维护索引。

---

## 7. 禁止事项

- 🚫 **禁止循环导入**：`core` → `adapters` → `core` 绝不出现
- 🚫 **禁止在 core 中硬编码配置**：所有配置通过依赖注入
- 🚫 **禁止 print 调试**：用 `logging` 模块
- 🚫 **禁止直接操作全局状态**：Agent 和 Memory 实例通过依赖注入传递
- 🚫 **禁止无测试的 feature 合并到 develop**
- 🚫 **禁止跳过 PR 直接 push master**
