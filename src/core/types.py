from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Memory:
    id: str
    content: str
    summary: str | None
    source: str  # "user" | "agent" | "reflect"
    timestamp: datetime
    importance: int = 5  # 1-10
    entities: list[str] = field(default_factory=list)
    relations: list[dict] = field(default_factory=list)  # [{s:"", p:"", o:""}]
    memory_type: str = "episodic"
    access_count: int = 0
    last_accessed: datetime | None = None


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
    data: str = ""
    error: str | None = None


@dataclass
class Message:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] | None = None
