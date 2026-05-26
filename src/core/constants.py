"""Agent Memory 全局常量。"""

# ── 记忆类型 ──
MEMORY_TYPE_EPISODIC = "episodic"
MEMORY_TYPE_SEMANTIC = "semantic"
MEMORY_TYPE_PROCEDURAL = "procedural"

# ── 记忆类型中文标签 ──
MEMORY_TYPE_LABELS: dict[str, str] = {
    "episodic": "情景记忆",
    "semantic": "语义记忆",
    "procedural": "程序记忆",
    "reflect": "反思",
}

# ── 来源 ──
SOURCE_USER = "user"
SOURCE_AGENT = "agent"
SOURCE_REFLECT = "reflect"

# ── 工具调用状态 ──
TOOL_STATUS_PENDING = "pending"
TOOL_STATUS_RUNNING = "running"
TOOL_STATUS_SUCCESS = "success"
TOOL_STATUS_FAILED = "failed"

# ── 角色 ──
ROLE_SYSTEM = "system"
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
ROLE_TOOL = "tool"

# ── Agent 运行时配置 ──
MAX_LLM_RETRIES = 3
MIN_IMPORTANCE_FOR_STORAGE = 5  # importance >= 此值才真正写入长期记忆
MAX_CONTEXT_CHARS = 8000  # 记忆文本硬限制，防止 token 爆炸
MAX_SAME_TOOL_CALLS = 3  # 同一工具连续调用上限，防止死循环
