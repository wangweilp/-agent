# 第 3 步：适配器层 — DeepSeek + Embedding + ChromaDB + SQLite

> ⚠️ 严格按顺序：先 llm.py → embedding.py → vector_store.py → sqlite_store.py。每完成一个跑测试再进下一个。

## 3.1 `src/adapters/llm.py` — DeepSeek Adapter
- 实现 `LLMProvider` 协议
- `chat()` 支持 `tools` 和 `tool_choice` 参数
- 不在此处定义 tool 列表（tool 列表在 core/agent.py）

```python
class DeepSeekAdapter:
    def chat(self, messages, tools=None, tool_choice=None, stream=False, **kwargs):
        return self._client.chat.completions.create(
            model=self._model, messages=messages,
            tools=tools, tool_choice=tool_choice,
            stream=stream, temperature=kwargs.get("temperature", 0.7)
        )
```

## 3.2 `src/adapters/embedding.py` — 本地 Embedding
- 使用 `sentence-transformers`，模型 `BAAI/bge-small-zh-v1.5`
- 实现 `LLMProvider.get_embedding()`（或独立方法）
- 延迟加载（Lazy init），节省启动时间

```python
class LocalEmbeddingProvider:
    def __init__(self, model_name: str):
        self._model = None; self._model_name = model_name
    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)
        return self._model
    def encode(self, text: str) -> list[float]:
        return self.model.encode(text, normalize_embeddings=True).tolist()
```

## 3.3 `src/adapters/vector_store.py` — ChromaDB Adapter
- 实现 `VectorStore` 协议
- `store(doc_id, embedding, metadata)` → 存入 ChromaDB
- `search(embedding, k)` → 返回 `[{doc_id, metadata, distance}]`

## 3.4 `src/adapters/sqlite_store.py` — SQLite Adapter
- 实现 `MemoryStore` 协议
- 初始化时创建完整表结构（notes + entities + memory_entities + relations）
- `store(memory)` → 插入 notes 表 + upsert entities
- `search_semantic(query, top_k)` → **先调 embedding，再调 ChromaDB**
- `search_by_entity(entity_name)` → SQL 精确查询
- `get_recent(limit)` → 按 timestamp DESC

## 3.5 提交
```bash
git add src/adapters/llm.py src/adapters/embedding.py src/adapters/vector_store.py src/adapters/sqlite_store.py
git commit -m "feat(adapters): implement DeepSeek, embedding, ChromaDB, and SQLite adapters"
```
