# 分步提示词使用说明

## 为什么分步？

整个项目文档量很大（CLAUDE.md + 4 份设计文档 ≈ 2 万 token），一次性全喂给 Claude Code 会严重压缩有效工作上下文。

## 怎么用？

**每次开新的 Claude Code 对话，粘贴对应 step 文件内容即可。** 每个 step 自包含——所需的所有架构约束、代码示例、验收标准都写在里面，不需要前一步的完整上下文。

## 投喂顺序

| 步骤 | 文件 | 投喂内容 |
|------|------|---------|
| 第 1 步 | `step-1-init.md` | 粘贴全文 |
| 第 2 步 | `step-2-architecture.md` | 粘贴全文 |
| 第 3 步 | `step-3-infrastructure.md` | 粘贴全文 |
| 第 4 步 | `step-4-core-engines.md` | 粘贴全文 |
| 第 5 步 | `step-5-agents-api-dashboard.md` | 粘贴全文 |
| 第 6 步 | `step-6-final.md` | 粘贴全文 |

## 规则

- **严格按顺序**：步骤 3 依赖步骤 2 产出的文件，不可跳步
- **每个 step 一个对话**：不要在同一个对话里连续投喂两个 step（会累积上下文污染）
- **每步投喂前检查**：确认上一步的代码已 `git commit`
- **遇到问题就停**：不要埋头继续下一步，先修好当前步骤的问题

## 额外可投（非必须）

如果某一步需要更详细的规范参考，可以选择性追加投喂：
- `docs/ARCHITECTURE.md` — 当需要确认模块边界时
- `docs/DESIGN.md` — 当需要确认 Memory 字段或 Agent 循环细节时
- `CLAUDE.md` — 当 Claude 违反了架构隔离规则时（作为追加约束）

---
## Quick Start: Enterprise AI Agent Demo

```bash
# Start backend
python main.py

# Start frontend (in separate terminal)
cd frontend && npm run dev

# Initialize demo data
python scripts/seed_agent_demo.py --apply

# Open browser
# http://localhost:3000/agents/scenarios
```

See [Step 20-D Demo Script](docs/STEP20D_DEMO_SCRIPT.md) for full demo walkthrough.
