from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass
class Memory:
    content: str
    summary: str | None
    source: str  # "user" | "agent" | "reflect"
    timestamp: datetime
    id: str = field(default_factory=lambda: str(uuid4()))
    importance: int = 5  # 1-10
    entities: list[str] = field(default_factory=list)
    relations: list[dict] = field(default_factory=list)  # [{s:"", p:"", o:""}]
    memory_type: str = "episodic"
    access_count: int = 0
    last_accessed: datetime | None = None
    status: str = "active"  # "active" | "archived" | "merged" | "deleted"
    archived_at: datetime | None = None


@dataclass
class Entity:
    id: str
    name: str
    entity_type: str = ""
    first_seen: datetime | None = None
    mention_count: int = 1


@dataclass
class ToolCall:
    tool_name: str
    arguments: dict
    call_id: str = ""
    status: str = "pending"  # pending | running | success | failed
    started_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass
class ToolResult:
    tool_name: str
    success: bool
    content: str = ""  # 工具返回的主要内容
    error: str | None = None  # 内部错误信息，仅用于日志
    user_message: str = ""  # 用户可见信息，默认取 content
    metadata: dict = field(default_factory=dict)  # {"memory_count": 3, "importance": 7, ...}

    def __post_init__(self) -> None:
        if not self.user_message:
            self.user_message = self.content

    @property
    def data(self) -> str:
        """向后兼容别名。"""
        return self.content


@dataclass
class SearchResult:
    doc_id: str
    score: float
    metadata: dict


@dataclass
class Message:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str
    timestamp: datetime | None = None
    metadata: dict = field(default_factory=dict)
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] | None = None
