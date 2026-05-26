# Architecture: 记忆进化型个人知识助手

## 1. 设计哲学

> 每一层都有边界，每一个模块都有职责，每一次调用都是可预期的。

本项目定位：**Cognitive OS / AI Second Brain**，而非又一个聊天机器人。

采用 **六边形架构（Ports & Adapters）**：领域核心不依赖任何外部实现，所有外部能力通过适配器注入。

---

## 2. 目录结构与职责边界

```
D:\代码\day2\
├── src/
│   ├── core/              # 领域层 — 纯逻辑，零外部依赖
│   │   ├── types.py       # 所有数据类型定义
│   │   ├── memory.py      # 记忆抽象协议（MemoryStore, VectorStore, LLMProvider）
│   │   ├── agent.py       # Agent 核心循环 + System Prompt
│   │   ├── context.py     # Context Builder（动态组装上下文）
│   │   ├── consolidation.py # 记忆巩固（自动重组知识）
│   │   ├── knowledge.py   # 知识图谱逻辑（实体→关系）
│   │   └── report.py      # 周报/洞察生成逻辑
│   │
│   ├── adapters/          # 适配器层 — 封装所有外部 I/O
│   │   ├── llm.py         # DeepSeek adapter（chat + embedding + tool calling）
│   │   ├── embedding.py   # 本地 embedding（bge-small-zh-v1.5）
│   │   ├── vector_store.py# ChromaDB adapter
│   │   ├── sqlite_store.py# SQLite adapter（结构化存储）
│   │   └── config.py      # 配置加载（pydantic Settings）
│   │
│   ├── api/               # 接口层 — FastAPI
│   │   ├── routes.py      # /chat 端点 + SSE 流式
│   │   ├── schemas.py     # Pydantic 请求/响应模型
│   │   └── middleware.py  # 日志、错误处理
│   │
│   └── tools/             # 工具层 — Agent 可调用的工具
│       ├── remember.py    # 记忆存储（+重要性评分）
│       ├── recall.py      # 语义检索（+RRF 重排序）
│       ├── reflect.py     # 反思工具
│       ├── consolidate.py # 记忆巩固触发
│       └── registry.py    # 工具注册表 + 权限分级
│
├── tests/                 # 镜像 src/ 结构
├── docs/                  # 设计文档
├── config/.env.template
├── data/                  # 运行时数据
├── CLAUDE.md              # 开发规则（最高优先级）
├── main.py                # 依赖注入入口
└── requirements.txt
```

---

## 3. 模块依赖图

```
                    ┌──────────────┐
                    │   main.py    │
                    │ (依赖注入)    │
                    └──┬───────┬───┘
                       │       │
          ┌────────────▼─┐  ┌──▼──────────┐
          │    api/       │  │   tools/     │
          │  FastAPI      │  │ 注册表+权限   │
          └──────┬────────┘  └──┬───────────┘
                 │              │
          ┌──────▼──────────────▼───┐
          │         core/           │
          │  ┌───────────────────┐  │
          │  │    agent.py       │  │ ← 真 Tool Calling + Reflective 循环
          │  │ Think→Act→Reflect │  │
          │  └─┬──────┬──────┬──┘  │
          │    │      │      │     │
          │  ┌─▼──┐ ┌─▼──┐ ┌─▼───┐ │
          │  │ctx │ │mem │ │cons │ │ ← 纯领域模型
          │  │bldr│ │    │ │olida│ │
          │  └────┘ └────┘ └─────┘ │
          └─────────┬──────────────┘
                    │ 协议(Protocol/ABC)
          ┌─────────▼──────────────┐
          │      adapters/          │
          │ ┌────┬────┬────┬─────┐ │
          │ │LLM │Emb │Vec │SQL  │ │ ← 所有 I/O
          │ └────┴────┴────┴─────┘ │
          └────────────────────────┘
```

**核心规则**：
- `core/` 不导入 `adapters/`、`api/`。只定义 Protocol 签名。
- `adapters/` 实现 core 定义的协议。
- `tools/` 是纯函数，通过协议访问数据。
- `api/` 只做请求解析和响应格式化。
- `main.py` 负责依赖注入。

---

## 4. 数据流（Cognitive Architecture）

```
用户输入
  │
  ▼
api/routes.py
  │
  ▼
core/context.py ← Context Builder
  │  ├─ System Prompt (core/agent.py)
  │  ├─ 最近 6 轮对话
  │  ├─ 检索到的长期记忆 (via adapters/)
  │  └─ 当前用户输入
  │
  ▼
core/agent.py ← Agent 核心循环 (5 轮上限)
  │
  ├─→ Think: LLM 推理 (via True Tool Calling API)
  │   tools=[{remember}, {recall}, {reflect}]
  │
  ├─→ Act: 执行工具调用
  │   ├─ remember → embedding + ChromaDB + SQLite 双写
  │   └─ recall   → 语义搜索 + RRF 重排序
  │
  ├─→ Reflect: 自我检查
  │   └─ 检查是否遗漏记忆、存在矛盾、可建立新连接
  │
  └─→ Respond: 最终回复 (SSE 流式)
```

---

## 5. 关键设计决策

| 决策 | v0.1 方案 | 理由 |
|------|----------|------|
| Tool Calling | **OpenAI Tool Calling API** | 结构化 schema，防 prompt injection，DeepSeek 兼容 |
| Embedding | **本地 bge-small-zh-v1.5** | 免费、离线、中文 SOTA，不做 SQLite LIKE 伪搜索 |
| Context 组装 | **Context Builder** | Agent 上下文 ≠ 全部历史，防 token 爆炸 |
| 记忆存储 | **双写（ChromaDB + SQLite）** | 向量搜索 + 结构化精确查询 |
| 记忆模型 | **丰富字段（含 importance, memory_type）** | 支持记忆衰减、分级、巩固 |
| Agent 循环 | **Reflective（Think→Act→Reflect）** | 非单步 Agent，有自我检查 |
| RAG | **Embedding 召回 → RRF 重排序 → LLM 压缩** | 非 top_k 直接返回 |
| 工具安全 | **SAFE / DANGEROUS 分级** | 危险操作需人工确认 |

---

## 6. 分层测试策略

| 层级 | 测试类型 | 覆盖目标 |
|------|---------|---------|
| `core/` | 单元测试 | 95%+ 覆盖纯逻辑 |
| `tools/` | 单元测试 | 每个工具的输入输出 |
| `adapters/` | 集成测试 | Mock 外部 API，验证适配器行为 |
| `api/` | E2E 测试 | 完整请求-响应链路 |
