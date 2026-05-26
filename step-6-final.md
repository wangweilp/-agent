# 第 6 步：最终验证与收尾

## 6.1 完整测试
```bash
python -m pytest tests/ -v --tb=short --cov=src --cov-report=term-missing
```
确保所有测试通过。

## 6.2 架构合规检查
```bash
# 检查 core 层是否有违规导入
rg -n "from openai|from chromadb|from sqlite_utils|from fastapi|from src\.adapters|from src\.api" src/core/

# 检查是否有 print 残留
rg -n "print\(" src/ --glob '!cli.py'
```

## 6.3 功能验证
1. 启动 CLI：`python -m src.tools.cli`
2. 输入一条知识："最近在读《系统之美》"
3. 验证 Agent 调用了 remember
4. 提问："之前那本书讲了什么？"
5. 验证 Agent 调用了 recall 并回答

## 6.4 最终提交
```bash
git add -A
git commit -m "chore: finalize v0.1 with full test coverage and compliance checks"
git log --oneline
```

## 6.5 CLAUDE.md 自检
确认 `CLAUDE.md` 中的所有规则在本轮开发中都被遵守了。
