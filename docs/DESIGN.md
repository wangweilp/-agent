# Design Document: 记忆进化型个人知识助手

## 1. 记忆系统设计

### 1.1 记忆分层模型

```
┌──────────────────────────────────────────┐
│           Working Memory（工作记忆）       │
│   当前对话上下文，最多 20 轮                │
│   实现：Python list[Message]               │
│   生命周期：单次会话                        │
├──────────────────────────────────────────┤
│           Semantic Memory（语义记忆）      │
│   向量化的长期记忆，支持语义检索             │
│   实现：ChromaDB                           │
│   生命周期：持久化                          │
├──────────────────────────────────────────┤
│           Episodic Memory（情节记忆）      │
│   原始笔记 + 时间戳 + 实体关联              │
│   实现：SQLite                             │
│   生命周期：持久化                          │
├──────────────────────────────────────────┤
│           Conceptual Memory（概念记忆）    │
│   实体关系图谱，抽象知识关联                 │
│   实现：SQLite（三表模拟图谱），未来 Neo4j   │
│   生命周期：持久化                          │
└──────────────────────────────────────────┘
```

### 1.2 记忆存储流程

```
用户输入
  │
  ▼
Agent 判断 → 调用 remember 工具
  │
  ├─→ 步骤1: 提取实体 (DeepSeek, few-shot)
  │   Input:  "今天读了《系统之美》，杠杆点那章很有意思"
  │   Output: {entities: ["系统之美","杠杆点","系统思维"],
  │            relation: [{s:"系统之美", p:"包含概念", o:"杠杆点"}]}
  │
  ├─→ 步骤2: 生成 embedding (本地 bge-small-zh)
  │
  ├─→ 步骤3: 写入 ChromaDB
  │   {id: uuid, embedding: [...], metadata: {timestamp, entities}}
  │
  └─→ 步骤4: 写入 SQLite
      {id: uuid, content: raw_text, timestamp, entities: json}
      {entity_name: "系统之美", type: "book"}
      {memory_id → entity_id 映射}
```

### 1.3 记忆检索流程（Hybrid Search）

```
用户问 "之前那本系统思维的书讲了什么？"
  │
  ▼
Agent 判断 → 调用 recall 工具
  │
  ├─→ 路径1: 语义搜索 (ChromaDB)
  │   生成 query embedding → top_k=5 相似文档
  │
  ├─→ 路径2: 关键词/实体匹配 (SQLite)
  │   解析出实体 "系统之美" → 查 entity→memory 映射 → 精确匹配
  │
  └─→ 合并: RRF (Reciprocal Rank Fusion)
       分数融合后 top_k=3 返回给 Agent
```

### 1.4 记忆压缩策略（v2.0）

当短期记忆超过 20 轮时：
1. 取最早 10 轮，调用 LLM 生成 1-2 句摘要
2. 摘要替换原文，标记为 `{role: "memory_summary", content: "..."}`
3. 腾出空间给新对话

---

## 2. Agent 核心循环

### 2.1 循环结构

```python
class AgentLoop:
    def run(self, user_input: str) -> str:
        self._add_user_message(user_input)

        for round in range(self.max_tool_rounds):  # 默认 5
            response = self._llm.generate(self._messages)

            if response.has_tool_call():
                tool_result = self._execute_tool(response.tool_call)
                self._add_tool_result(tool_result)
                continue  # 下一轮思考

            # 没有工具调用 → 最终回复
            return response.content

        raise MaxToolRoundsExceeded("Agent exceeded max tool rounds")
```

### 2.2 工具调用协议（JSON）

```json
{"tool": "remember", "args": {"content": "..."}}
{"tool": "recall", "args": {"query": "...", "entities": ["实体1"]}}
{"tool": "reflect", "args": {"topic": "...", "recent_n": 10}}
```

解析规则：
1. 扫描回复中第一个完整 JSON 对象
2. 校验 `tool` 字段在注册表中
3. 校验 `args` 符合工具的 pydantic schema
4. 若解析失败，不重试，直接当普通回复返回

### 2.3 System Prompt 设计

```
你是「记忆进化」个人知识助手。你拥有长期记忆，会逐渐了解用户的思维模式。

## 你的能力
- 存储用户分享的知识和想法
- 检索相关历史记忆来回答问题
- 主动发现用户知识体系中的隐藏联系

## 工具使用
你可以调用以下工具（输出 JSON，不要额外文字）：
- remember: 存储一条新记忆
- recall: 检索相关记忆
- reflect: 分析近期记忆，发现模式和矛盾

## 行为准则
1. 用户分享新知识时，主动调用 remember 存储
2. 用户提问时，先 recall 再回答
3. 回答要结合记忆，个性化而非通用
4. 发现联系时主动指出：「你 X 天前提到过...和你现在说的...可能有关联」
5. 不确定是否该存储时，宁存勿漏
6. 回复用中文，自然、简洁、有温度
```

---

## 3. RAG Pipeline 设计

### 3.1 整体流程

```
Query
  │
  ▼
Query Rewriting (可选，复杂问题时启用)
  改写用户原始问题，补充上下文
  │
  ▼
Hybrid Retrieval (ChromaDB + SQLite)
  │
  ▼
Reranking (RRF 融合 + 时间衰减)
  越新的记忆权重越高
  │
  ▼
Context Assembly
  将检索到的记忆拼接成上下文块
  │
  ▼
Grounded Generation (DeepSeek)
  基于检索到的记忆生成回答，要求标注来源
```

### 3.2 Reranking 算法

```python
def rrf_rerank(vector_results, sqlite_results, k=60):
    scores = {}
    for rank, doc in enumerate(vector_results):
        scores[doc.id] = scores.get(doc.id, 0) + 1 / (k + rank)
    for rank, doc in enumerate(sqlite_results):
        scores[doc.id] = scores.get(doc.id, 0) + 1 / (k + rank)
    # 时间衰减：每 7 天权重衰减 10%
    for doc in all_docs:
        days_ago = (now - doc.timestamp).days
        decay = 1.0 - 0.10 * (days_ago / 7)
        scores[doc.id] *= max(0.3, decay)  # 最低保留 30%
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
```

---

## 4. 周报生成设计

### 4.1 触发方式
- 手动：`python weekly_report.py`
- 自动：Windows 任务计划程序，每周日 20:00

### 4.2 数据源
```sql
-- 本周记忆
SELECT * FROM notes
WHERE timestamp >= date('now', 'weekday 0', '-7 days')
  AND timestamp < date('now', 'weekday 0')
ORDER BY timestamp ASC;

-- 本周活跃实体（按出现次数）
SELECT e.name, COUNT(*) as cnt
FROM entities e
JOIN memory_entities me ON e.id = me.entity_id
JOIN notes n ON me.memory_id = n.id
WHERE n.timestamp >= date('now', '-7 days')
GROUP BY e.id
ORDER BY cnt DESC
LIMIT 20;
```

### 4.3 Prompt 模板（不可变结构）
```markdown
## 角色
你是一个认知分析助手，擅长从个人的思维碎片中发现模式和联系。

## 输入
以下是用户本周记录的 {memory_count} 条想法：
{memory_list}

## 任务
基于以上数据，生成一份「认知周报」，用 Markdown 格式，包含以下五个固定板块：

### 1. 本周概览
- 记忆数量、最活跃日期
- 前 3 大主题域（用百分比标注）

### 2. 领域聚焦
每个领域 1-2 句核心洞察，引用具体记忆作为证据

### 3. 隐藏联系
跨领域的模式识别，指出用户可能没意识到的关联

### 4. 盲点提示
基于当前轨迹，指出可能被忽略的角度或对立观点

### 5. 下周建议
具体的下一步阅读/思考/行动建议

## 风格
温暖的分析师语调，不说教，像朋友聊天。
```

### 4.4 输出文件
- 文件路径：`data/reports/report_YYYYWW.md`
- 文件命名：`report_202621.md` 表示 2026 年第 21 周

---

## 5. 数据模型

### 5.1 核心类型定义

```python
@dataclass
class Memory:
    id: str
    content: str
    timestamp: datetime
    entities: list[str]

@dataclass
class Entity:
    id: str
    name: str
    entity_type: str  # "book", "person", "concept", "tool", "project"
    first_seen: datetime
    mention_count: int

@dataclass
class ToolCall:
    tool: str
    args: dict[str, Any]

@dataclass
class ToolResult:
    tool: str
    success: bool
    data: Any
    error: str | None

@dataclass
class AgentTurn:
    round: int
    thought: str      # LLM 的推理过程
    action: ToolCall | None
    observation: ToolResult | None
    final_response: str | None
```

### 5.2 SQLite 表结构

```sql
-- 原始笔记
CREATE TABLE notes (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    entities TEXT,  -- JSON array
    chroma_id TEXT  -- 关联向量库
);

-- 实体词典
CREATE TABLE entities (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    entity_type TEXT,
    first_seen TEXT,
    mention_count INTEGER DEFAULT 1
);

-- 记忆-实体关联
CREATE TABLE memory_entities (
    memory_id TEXT,
    entity_id TEXT,
    PRIMARY KEY (memory_id, entity_id),
    FOREIGN KEY (memory_id) REFERENCES notes(id),
    FOREIGN KEY (entity_id) REFERENCES entities(id)
);

-- 实体关系
CREATE TABLE relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_entity_id TEXT,
    target_entity_id TEXT,
    relation_type TEXT,
    weight REAL DEFAULT 1.0,
    FOREIGN KEY (source_entity_id) REFERENCES entities(id),
    FOREIGN KEY (target_entity_id) REFERENCES entities(id)
);
```

---

## 6. 错误处理策略

| 错误类型 | 处理方式 |
|---------|---------|
| DeepSeek API 不可用 | 返回友好提示，不崩溃；记录日志 |
| ChromaDB 写失败 | 回退到 SQLite-only 模式，下次重试 |
| SQLite 写失败 | 记录到日志文件，返回错误给 Agent |
| 工具调用 JSON 解析失败 | 当作普通回复，不做工具调用 |
| Agent 循环超限 | 返回当前最佳回复，不继续循环 |
| Embedding 生成失败 | 降级为纯关键词匹配 |

---

## 7. 安全与隐私

- API Key 只在 `.env`，永不提交
- 记忆数据纯本地存储
- 不向任何外部服务发送用户数据（除了 DeepSeek API 用于推理和实体抽取）
- 可选：将来支持本地 LLM 完全离线
