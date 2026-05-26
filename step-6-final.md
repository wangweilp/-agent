# 第 6 步：最终验证与收尾

## 6.1 架构合规检查
```bash
# 绝对不要在 core/ 中看到这些
rg -n "from (openai|chromadb|sqlite_utils|fastapi|sentence_transformers|src\.(adapters|api))" src/core/

# 绝对不要看到 JSON 字符串解析 tool call
rg -n "startswith.*tool" src/

# 绝对不要看到 SQLite LIKE 做语义搜索
rg -n "LIKE.*query" src/
```

## 6.2 功能验证
1. `python -m src.tools.cli` → 能启动对话
2. 输入「最近在读《系统之美》」→ Agent 调用 remember
3. 输入「之前那本书讲了什么？」→ Agent 调用 recall → 语义匹配
4. 验证记忆存入了 SQLite + ChromaDB

## 6.3 安全检查
- [ ] Tool Permission Layer 生效（危险工具需确认）
- [ ] System Prompt 含防护指令
- [ ] API Key 不在代码中

## 6.4 最终提交
```bash
git add -A
git commit -m "chore: v0.1 finalize with compliance checks"
git log --oneline
```
