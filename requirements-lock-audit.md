# requirements-lock-audit.md

**生成时间:** 2026-06-21
**项目目录:** `D:\dma\day2`
**审计范围:** `requirements.txt` 全部 13 项声明依赖 vs 当前 Python 环境实际安装版本

---

## 总览

| 状态 | 数量 |
|------|------|
| 符合约束 | 9 |
| 超出上限 | 3 |
| 未安装 | 1 |
| **合计** | **13** |

---

## 逐项对比

| # | Package | Required | Installed | Status |
|---|---------|----------|-----------|--------|
| 1 | `openai` | `>=1.30,<2.0` | **2.37.0** | ❌ 超出 |
| 2 | `chromadb` | `>=0.5,<0.6` | **1.5.9** | ❌ 超出 |
| 3 | `bcrypt` | `>=4.0,<5.0` | **5.0.0** | ❌ 超出 |
| 4 | `sentence-transformers` | `>=3.0,<4.0` | **未安装** | ❌ 缺失 |
| 5 | `fastapi` | `>=0.115,<1.0` | 0.136.3 | ✅ |
| 6 | `uvicorn[standard]` | `>=0.23,<1.0` | 0.48.0 | ✅ |
| 7 | `sqlite-utils` | `>=3.0,<4.0` | 3.39 | ✅ |
| 8 | `python-dotenv` | `>=1.0,<2.0` | 1.2.2 | ✅ |
| 9 | `pydantic` | `>=2.7,<3.0` | 2.13.4 | ✅ |
| 10 | `httpx` | `>=0.25,<1.0` | 0.28.1 | ✅ |
| 11 | `pydantic-settings` | `>=2.0,<3.0` | 2.14.1 | ✅ |
| 12 | `python-multipart` | `>=0.0.9` | 0.0.29 | ✅ |
| 13 | `python-jose[cryptography]` | `>=3.3,<4.0` | 3.5.0 | ✅ |

---

## 超出版本约束的依赖（详细分析）

### 1. chromadb — CRITICAL

| 属性 | 值 |
|------|-----|
| **约束版本** | `>=0.5,<0.6` |
| **实际安装** | `1.5.9` |
| **跨度** | 0.5 → 1.5（跨越 1.0 主版本边界） |
| **风险等级** | 🔴 **CRITICAL** |

**代码使用点:**
```
src/adapters/vector_store.py:5   import chromadb
src/adapters/vector_store.py:6   from chromadb.api import ClientAPI
src/adapters/vector_store.py:36  chromadb.PersistentClient(path=...)
src/adapters/vector_store.py:39  client.get_or_create_collection(name=...)
src/adapters/vector_store.py:48  collection.upsert(ids=..., embeddings=..., metadatas=...)
src/adapters/vector_store.py:65  collection.query(query_embeddings=..., n_results=..., include=...)
```

**已知破坏性变更 (0.5.x → 1.x):**
- `ClientAPI` 类型在 chromadb 1.x 中可能已被移除或重命名
- `PersistentClient` 构造函数签名变更，`path` 参数可能改为 `Settings` 对象
- `get_or_create_collection` 的 metadata 参数行为变更
- 内部数据格式迁移（0.5.x 的持久化数据可能与 1.x 不兼容）

**当前表现:** 未知。`main.py` 在 `agent._embedding.warmup()` 崩溃，`ChromaDBAdapter` 尚未被实例化，此问题尚未暴露。**修复 embedding 缺失后此问题会立即暴露。**

**推荐:** 降级到 `chromadb>=0.5,<0.6`，或升级代码适配 chromadb 1.x API。

---

### 2. openai — HIGH

| 属性 | 值 |
|------|-----|
| **约束版本** | `>=1.30,<2.0` |
| **实际安装** | `2.37.0` |
| **跨度** | 1.x → 2.x（跨主版本） |
| **风险等级** | 🟠 **HIGH** |

**代码使用点:**
```
src/adapters/llm.py:5   from openai import APIError, APIConnectionError, OpenAI, RateLimitError
src/adapters/llm.py:25  OpenAI(api_key=..., base_url=..., timeout=...)
src/adapters/llm.py:40  client.chat.completions.create(model=..., messages=..., tools=..., ...)
src/adapters/llm.py:48  except RateLimitError
src/adapters/llm.py:50  except APIConnectionError
src/adapters/llm.py:52  except APIError
```

**已知破坏性变更 (1.x → 2.x):**
- `APIError` 异常类可能在 2.x 中被重构，继承体系变更
- `APIConnectionError` / `RateLimitError` 的模块路径可能变更
- `OpenAI()` 构造函数签名向后兼容，但某些参数行为可能不同
- `chat.completions.create()` 核心 API 基本兼容

**当前表现:** 未知。尚未触发 LLM 调用。导入 `main.py` 时 `from src.adapters.llm import DeepSeekAdapter` 会执行（在 embedding warmup 之前），但实际上 `llm.py` 的 `from openai import ...` 在模块级别执行。如果 openai 2.x 中这些异常类路径变更，导入就会失败，但当前实际报错是 embedding 缺失，说明至少 openai 导入是成功的（2.x 保留了向后兼容的导出路径）。

**推荐:** 降级到 `openai>=1.30,<2.0`，或验证 2.x 异常类兼容性后升级约束。

---

### 3. bcrypt — LOW

| 属性 | 值 |
|------|-----|
| **约束版本** | `>=4.0,<5.0` |
| **实际安装** | `5.0.0` |
| **跨度** | 4.x → 5.0（次主版本） |
| **风险等级** | 🟡 **LOW** |

**代码使用点:**
```
src/adapters/auth_store.py:299  import bcrypt
src/adapters/auth_store.py:300  bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
src/api/auth_router.py:12       import bcrypt
```

**已知变更 (4.x → 5.0):**
- 移除了对老旧 `2a` / `2x` / `2y` 前缀的支持
- 默认 salt 前缀从 `2b` 无变化
- `hashpw()` / `gensalt()` API 签名未变
- `checkpw()` 未变

**当前表现:** `import bcrypt` 在模块级别，导入成功即基本兼容。`hashpw`/`gensalt` 函数签名在 5.0 中未变。**实际风险极低。**

**推荐:** 升级约束到 `bcrypt>=4.0,<6.0` 即可。无需降级。

---

### 4. sentence-transformers — BLOCKER

| 属性 | 值 |
|------|-----|
| **约束版本** | `>=3.0,<4.0` |
| **实际安装** | **未安装** |
| **风险等级** | 🔴 **BLOCKER** |

**代码使用点:**
```
src/adapters/embedding.py:15  from sentence_transformers import SentenceTransformer  (TYPE_CHECKING)
src/adapters/embedding.py:65  from sentence_transformers import SentenceTransformer  (运行时)
src/adapters/embedding.py:75  SentenceTransformer(model_name, device=..., local_files_only=...)
main.py:152                  agent._embedding.warmup()  ← 启动阶段强制调用
```

**当前表现:** 启动直接崩溃，`ModuleNotFoundError: No module named 'sentence_transformers'`。

**传递依赖体积警告:** 安装 `sentence-transformers` 会带入 `torch`（~2GB），首次安装耗时较长。

**推荐:** 安装 `sentence-transformers>=3.0,<4.0`。

---

## 潜在兼容性风险矩阵

| 组件 | 启动阶段触发 | 运行时触发 | 崩溃概率 | 影响范围 |
|------|:----------:|:--------:|:------:|------|
| `sentence-transformers` | ✅ (warmup) | encode() | 100% | 启动阻塞 |
| `chromadb` | ✅ (init) | store/search | 高 | VectorStore 全部功能 |
| `openai` | ✅ (import) | chat() | 中 | LLM 全部调用 |
| `bcrypt` | ✅ (import) | hashpw | 低 | 认证/密码哈希 |

**注意:** `chromadb` 和 `openai` 的问题当前未暴露，仅因为 embedding 导入崩溃先发生。**修复 sentence-transformers 后，chromadb 的 import 将紧接着执行，如 API 不兼容会立刻暴露。**

---

## 推荐修复方案

### 方案 A: 严格对齐 requirements.txt（保守，推荐）

```bash
pip install "chromadb>=0.5,<0.6" "openai>=1.30,<2.0" "bcrypt>=4.0,<5.0" "sentence-transformers>=3.0,<4.0"
```

此命令会：
- 降级 chromadb 1.5.9 → 0.5.x
- 降级 openai 2.37.0 → 1.x
- 降级 bcrypt 5.0.0 → 4.x
- 安装 sentence-transformers 3.x

⚠ **降级 chromadb 可能破坏已有持久化数据**（1.5.9 格式不兼容 0.5.x）。

### 方案 B: 仅补装缺失 + 推迟版本对齐（风险自知）

```bash
pip install "sentence-transformers>=3.0,<4.0"
```

然后逐一验证 chromadb / openai 在启动后是否正常工作，再决定是否放宽约束。

---

## 行动建议

1. **立即:** 安装 `sentence-transformers`（解除启动阻塞）
2. **启动后立即检查:** chromadb `PersistentClient` / `ClientAPI` 导入是否成功
3. **随后检查:** openai 异常类导入是否正常
4. **最后:** 决定 `requirements.txt` 约束是否需要放宽，或降级到声明版本
