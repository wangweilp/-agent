"""轻量事件系统 — 基于 logging 的结构化事件流。

所有 Memory 生命周期事件均通过此模块发出，后续可接入：
- Event Timeline 页面
- metrics 打点
- 外部 webhook/monitoring
"""
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

# ── 事件类型 ──
class EventType:
    MEMORY_CREATED = "memory.created"
    MEMORY_MERGED = "memory.merged"
    MEMORY_DELETED = "memory.deleted"
    MEMORY_ACCESSED = "memory.accessed"
    RECALL_EXECUTED = "recall.executed"
    REFLECTION_RUN = "reflection.run"
    REFLECTION_SKIPPED = "reflection.skipped"
    REFLECTION_INSIGHT = "reflection.insight"
    AGENT_START = "agent.start"
    AGENT_DONE = "agent.done"
    TOOL_CALL_START = "tool.call_start"
    TOOL_CALL_DONE = "tool.call_done"


@dataclass
class Event:
    id: str = field(default_factory=lambda: str(uuid4()))
    type: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    data: dict[str, Any] = field(default_factory=dict)


# ── 内存事件缓冲区（环形缓冲区，最近 500 条）─
_MAX_EVENTS = 500
_buffer: list[Event] = []
_lock = threading.Lock()


def emit(event_type: str, **data: Any) -> Event:
    """发出一个事件，同时写入 logger 和内存缓冲区。"""
    event = Event(type=event_type, data=data)
    
    # 写入 logger（结构化日志，可被 ELK/Loki 消费）
    logger.info(
        f"event:{event_type}",
        extra={"event": event_type, **data},
    )
    
    # 写入内存缓冲区（供 API 查询）
    with _lock:
        _buffer.append(event)
        if len(_buffer) > _MAX_EVENTS:
            del _buffer[:len(_buffer) - _MAX_EVENTS]
    
    return event


def recent(limit: int = 100) -> list[Event]:
    """获取最近 N 条事件。"""
    with _lock:
        return list(_buffer[-limit:])


def clear() -> None:
    """清空事件缓冲区。"""
    with _lock:
        _buffer.clear()