"""Task Queue Adapter — metadata-only, no real queue in Step 27.

Step 27: readiness assessment for task queue (Redis/RabbitMQ/Kafka).
No real queue. No real enqueue/dispatch. queue_active=False.
All is_enqueue_allowed()/is_dispatch_allowed() return False.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Protocol
from uuid import uuid4

from src.adapters.config import Settings


class TaskQueueStatus(StrEnum):
    NOT_STARTED = "not_started"
    CONFIGURED = "configured"
    CONNECTION_ACTIVE = "connection_active"
    QUEUE_ACTIVE = "queue_active"
    FAIL_CLOSED = "fail_closed"


class TaskPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class TaskQueueType(StrEnum):
    REDIS = "redis"
    RABBITMQ = "rabbitmq"
    KAFKA = "kafka"


@dataclass
class TaskDefinition:
    task_id: str = field(default_factory=lambda: f"tsk_{uuid4().hex[:16]}")
    task_name: str = ""
    queue_name: str = ""
    priority: str = TaskPriority.NORMAL
    payload_schema: dict[str, Any] = field(default_factory=dict)
    retry_count: int = 3
    timeout_seconds: int = 300
    enqueue_allowed: bool = False
    dispatch_allowed: bool = False
    execution_allowed: bool = False
    metadata_only: bool = True

    def is_enqueue_allowed(self) -> bool: return False
    def is_dispatch_allowed(self) -> bool: return False

    def to_dict(self):
        return {
            "task_id": self.task_id, "task_name": self.task_name,
            "queue_name": self.queue_name, "priority": self.priority,
            "retry_count": self.retry_count, "timeout_seconds": self.timeout_seconds,
            "enqueue_allowed": self.enqueue_allowed,
            "dispatch_allowed": self.dispatch_allowed,
            "execution_allowed": self.execution_allowed,
            "metadata_only": self.metadata_only,
        }


@dataclass
class TaskQueueReport:
    report_id: str = field(default_factory=lambda: f"tqrep_{uuid4().hex[:16]}")
    status: str = TaskQueueStatus.NOT_STARTED
    provider: str = TaskQueueType.REDIS
    connection_active: bool = False
    queue_active: bool = False
    enqueue_allowed: bool = False
    dispatch_allowed: bool = False
    execution_allowed: bool = False
    queues_defined: int = 0
    recommended_queues: list[str] = field(default_factory=list)
    task_definitions: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata_only: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_queue_active(self) -> bool: return False

    def to_dict(self):
        return {
            "report_id": self.report_id, "status": self.status,
            "provider": self.provider,
            "connection_active": self.connection_active,
            "queue_active": self.queue_active,
            "enqueue_allowed": self.enqueue_allowed,
            "dispatch_allowed": self.dispatch_allowed,
            "execution_allowed": self.execution_allowed,
            "queues_defined": self.queues_defined,
            "recommended_queues": self.recommended_queues,
            "task_definitions": self.task_definitions,
            "warnings": self.warnings,
            "metadata_only": self.metadata_only,
            "created_at": self.created_at.isoformat(),
        }


# Recommended task queue definitions
RECOMMENDED_QUEUES = {
    "memory_write": {
        "description": "Async memory write operations",
        "priority": "high", "retry": 5, "timeout": 60,
    },
    "import_process": {
        "description": "Import file processing (Notion/MD/PDF)",
        "priority": "normal", "retry": 3, "timeout": 300,
    },
    "sync_delta": {
        "description": "Incremental sync operations",
        "priority": "normal", "retry": 3, "timeout": 120,
    },
    "policy_audit": {
        "description": "Policy enforcement audit tasks",
        "priority": "low", "retry": 2, "timeout": 30,
    },
    "usage_aggregate": {
        "description": "Usage statistics aggregation",
        "priority": "low", "retry": 1, "timeout": 60,
    },
    "analytics_compute": {
        "description": "Analytics computation jobs",
        "priority": "low", "retry": 2, "timeout": 600,
    },
}


class TaskQueueAdapter:
    """Task queue readiness adapter. Metadata-only. No real queue."""

    def __init__(self, settings: Settings | None = None):
        self._settings = settings

    def assess_readiness(self) -> TaskQueueReport:
        tasks = [
            TaskDefinition(task_name=name, queue_name=name, priority=q["priority"],
                           retry_count=q["retry"], timeout_seconds=q["timeout"])
            for name, q in RECOMMENDED_QUEUES.items()
        ]
        return TaskQueueReport(
            status=TaskQueueStatus.CONFIGURED,
            connection_active=False, queue_active=False,
            enqueue_allowed=False, dispatch_allowed=False,
            execution_allowed=False,
            queues_defined=len(RECOMMENDED_QUEUES),
            recommended_queues=list(RECOMMENDED_QUEUES.keys()),
            task_definitions=[t.to_dict() for t in tasks],
            warnings=["No real queue backend connected",
                       "All enqueue/dispatch operations blocked",
                       "Celery/RQ/Kafka clients not imported"],
            metadata_only=True,
        )

    def get_queue_config(self) -> dict[str, dict]:
        return {k: dict(v) for k, v in RECOMMENDED_QUEUES.items()}

    def export_config(self) -> dict[str, Any]:
        return {
            "provider": "redis",
            "broker_url_template": "redis://localhost:6379/0",
            "connection_active": False,
            "enqueue_allowed": False,
            "dispatch_allowed": False,
            "queues": self.get_queue_config(),
            "metadata_only": True,
        }
