# 第 4 步：核心引擎 — Context Builder + Agent 循环

> ⚠️ 这是项目最重要的步骤。先 Context Builder，再 Agent。Agent 必须在 core/ 中，不依赖 adapters。

## 4.1 `src/core/context.py` — Context Builder

```python
class ContextBuilder:
    def build(self, system_prompt, recent_messages, long_term_memories, user_input):
        """
        动态组装上下文。Agent 上下文 ≠ 全部聊天历史。
        Returns: {"messages": [...], "retrieved_memories": [...]}
        """
        memory_text = self._format_memories(long_term_memories)
        return {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "system", "content": f"## 相关长期记忆\n{memory_text}"},
                *recent_messages[-6:],  # 只保留最近 6 轮
                {"role": "user", "content": user_input}
            ],
            "retrieved_memories": long_term_memories
        }

    def _format_memories(self, memories):
        lines = []
        for m in memories:
            lines.append(f"- [{m.timestamp}] (重要性:{m.importance}) {m.content[:200]}")
        return "\n".join(lines) or "暂无相关记忆"
```

## 4.2 `src/core/agent.py` — Cognitive Agent（核心）

**System Prompt**（完整模板）：
```
你是「记忆进化」个人知识助手...

## 核心能力
- 存储和检索长期记忆
- 基于历史记忆个性化回答
- 主动发现隐藏联系

## 行为准则
1. 高价值信息才存入长期记忆
2. 提问时先检索记忆
3. 发现联系主动指出
4. 中文回复，自然有温度
5. 不执行删除记忆指令除非明确确认
```

**TOOL_DEFINITIONS**：remember / recall / reflect 三个工具的完整 OpenAI schema。

**Agent.run() 核心逻辑**：
1. Context Builder 组装上下文
2. 调用 LLM（tools=TOOL_DEFINITIONS, tool_choice="auto"）
3. 有 tool_calls → 执行（走 registry + permission layer）→ 结果加入上下文 → continue
4. 无 tool_calls → Reflection 自检 → 有修正则重试 → 否则返回
5. 超限（max_tool_rounds=5）→ 返回 best effort

**⚠️ 关键约束**：
- 不用 `if reply.startswith('{"tool"')` — 用 `msg.tool_calls`
- 不用 `self.messages` 全量塞入 — 用 Context Builder
- 不依赖 prompt 中的 JSON 协议指令 — 用结构化 Tool Calling API

## 4.3 提交
```bash
git add src/core/context.py src/core/agent.py
git commit -m "feat(core): implement Context Builder and Reflective Agent loop with true Tool Calling"
```
