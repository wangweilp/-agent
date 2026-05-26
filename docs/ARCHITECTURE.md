# Architecture: 记忆进化型个人知识助手

## 1. 设计哲学

> 每一层都有边界，每一个模块都有职责，每一次调用都是可预期的。

本项目采用 **六边形架构（Ports & Adapters）** 的简化版：领域核心不依赖任何外部实现，所有外部能力通过适配器注入。

## 2. 目录结构与职责边界

```
knowledge-agent/
├── src/
│   ├── core/          # 【领域层】纯逻辑，零外部依赖
│   │   ├── __init__.py
│   │   ├── memory.py        # 记忆抽象：存储/检索/管理记忆
│   │   ├── agent.py         # Agent 核心循环：Think → Act → Observe
│   │   ├── knowledge.py     # 知识实体模型 + 关系图谱
│   │   ├── report.py        # 周报生成逻辑（纯 prompt 组装）
│   │   └── types.py         # 共享数据类型（Memory, Entity, ToolCall...）
│   │
│   ├── adapters/      # 【适配器层】所有外部系统在这里封装
│   │   ├── __init__.py
│   │   ├── llm.py           # DeepSeek 适配器（chat + embedding）
│   │   ├── vector_store.py  # ChromaDB 适配器
│   │   ├── sqlite_store.py  # SQLite 适配器（结构化存储）
│   │   └── config.py        # 配置加载（.env → pydantic Settings）
│   │
│   ├── api/           # 【接口层】对外暴露的通信协议
│   │   ├── __init__.py
│   │   ├── routes.py        # FastAPI 路由
│   │   ├── schemas.py       # 请求/响应 Pydantic 模型
│   │   └── middleware.py    # 日志、错误处理
│   │
│   └── tools/         # 【工具层】Agent 可调用的工具函数（独立可测试）
│       ├── __init__.py
│       ├── recall.py        # 记忆检索工具
│       ├── remember.py      # 记忆存储工具
│       ├── reflect.py       # 反思/关联发现工具
│       └── registry.py      # 工具注册表
│
├── tests/             # 测试目录（镜像 src/ 结构）
│   ├── test_core/
│   ├── test_adapters/
│   └── test_tools/
│
├── docs/              # 文档
│   ├── ARCHITECTURE.md
│   ├── DESIGN.md
│   ├── ROADMAP.md
│   └── DEV_GUIDE.md
│
├── config/            # 配置文件模板
│   └── .env.template
│
├── data/              # 运行时数据（不提交 git）
├── main.py            # 启动入口（组装所有依赖）
├── requirements.txt
└── .gitignore
```

## 3. 模块依赖图

```
┌─────────────────────────────────────────────────┐
│                   main.py                       │
│          (依赖注入：组装整个系统)                  │
└─────────────────────────────────────────────────┘
         │                │
    ┌────▼────┐      ┌───▼────┐
    │  api/   │      │ tools/ │
    │ FastAPI │◄─────│ 工具注册│
    └────┬────┘      └───┬────┘
         │               │
    ┌────▼───────────────▼────┐
    │         core/            │
    │  ┌────────────────────┐  │
    │  │      agent.py      │  │  ◄── 核心循环
    │  │  Think→Act→Observe │  │
    │  └───┬──────────┬─────┘  │
    │      │          │        │
    │  ┌───▼──┐  ┌───▼─────┐  │
    │  │memory│  │knowledge│  │  ◄── 纯领域模型
    │  └───┬──┘  └─────────┘  │
    └──────┼──────────────────┘
           │ 依赖协议(Protocol/ABC)
    ┌──────▼──────────────────┐
    │       adapters/          │
    │  ┌─────┬─────┬────────┐  │
    │  │ LLM │Vectr│ SQLite │  │  ◄── 所有 I/O 在这里
    │  └─────┴─────┴────────┘  │
    └──────────────────────────┘
```

**核心规则**：
- `core/` 不导入 `adapters/`、`api/`。只定义 Protocol/ABC 签名。
- `adapters/` 实现 `core/` 定义的协议。
- `tools/` 是纯函数，依赖 `core/` 的类型，通过协议访问 `adapters/`。
- `api/` 只做请求解析和响应格式化，调用 `core/`。
- `main.py` 负责把所有东西组装起来（依赖注入）。

## 4. 数据流

```
用户输入
  │
  ▼
api/routes.py ──→ core/agent.py
                      │
         ┌────────────┼────────────┐
         ▼            ▼            ▼
      Think        Act         Observe
      (LLM)      (Tools)      (Update)
         │            │            │
         │      ┌─────┴─────┐      │
         │      ▼           ▼      │
         │  remember     recall    │
         │  →SQLite     →ChromaDB  │
         │  →ChromaDB              │
         └─────────────────────────┘
                      │
                      ▼
              最终回复 (streaming SSE)
```

## 5. 关键设计决策

| 决策 | 理由 | 约束 |
|------|------|------|
| 双层记忆（向量+结构化） | 语义搜索 + 精确查询不可互相替代 | ChromaDB 只存向量，SQLite 存原始文本和元数据 |
| Agent 循环上限 5 轮 | 防止 Agent 死循环，控制成本和延迟 | 在 config 中可配置 |
| 短对话记忆窗口 20 条 | 平衡上下文相关性和 token 成本 | 超过时自动摘要压缩 |
| 工具调用用 JSON 解析 | 零依赖，足够控制 Agent 行为 | 后续可升级为 function calling |
| CLI 入口优先于 Web UI | 快速验证，不分散架构精力 | dev 阶段用终端，prod 再挂 FastAPI |

## 6. 分层测试策略

| 层级 | 测试类型 | 覆盖目标 |
|------|---------|---------|
| `core/` | 单元测试 | 100% 覆盖纯逻辑 |
| `tools/` | 单元测试 | 每个工具的输入输出 |
| `adapters/` | 集成测试 | Mock 外部 API，验证适配器行为 |
| `api/` | E2E 测试 | 完整请求-响应链路 |
