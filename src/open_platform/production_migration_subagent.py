"""Production Migration Sub-Agent — metadata-only migration readiness assessment.

Step 27: Assess production readiness for PostgreSQL, Redis, Object Storage,
Task Queue, Import Hub, and Sync Hub. No real connections. No execution.

all execution_allowed / runtime_enabled / fixture_execution_allowed = False.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from src.adapters.postgres_adapter import PostgresAdapter, PostgresMigrationReport
from src.adapters.redis_cache import RedisCacheAdapter, RedisCacheReport
from src.adapters.object_storage_adapter import ObjectStorageAdapter, ObjectStorageReport
from src.adapters.task_queue_adapter import TaskQueueAdapter, TaskQueueReport
from src.open_platform.import_hub import ImportHub, ImportHubReport
from src.open_platform.sync_hub import SyncHub, SyncHubReport


@dataclass
class ProductionMigrationReport:
    report_id: str = field(default_factory=lambda: f"prdmig_{uuid4().hex[:16]}")
    status: str = "not_started"
    overall_ready: bool = False
    postgres: dict[str, Any] = field(default_factory=dict)
    redis: dict[str, Any] = field(default_factory=dict)
    object_storage: dict[str, Any] = field(default_factory=dict)
    task_queue: dict[str, Any] = field(default_factory=dict)
    import_hub: dict[str, Any] = field(default_factory=dict)
    sync_hub: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    all_connections_blocked: bool = True
    all_execution_blocked: bool = True
    all_runtime_disabled: bool = True
    execution_allowed: bool = False
    runtime_enabled: bool = False
    fixture_execution_allowed: bool = False
    metadata_only: bool = True
    ready_for_step27_demo: bool = True
    ready_for_production: bool = False
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "report_id": self.report_id, "status": self.status,
            "overall_ready": self.overall_ready,
            "postgres": self.postgres, "redis": self.redis,
            "object_storage": self.object_storage, "task_queue": self.task_queue,
            "import_hub": self.import_hub, "sync_hub": self.sync_hub,
            "summary": self.summary,
            "all_connections_blocked": self.all_connections_blocked,
            "all_execution_blocked": self.all_execution_blocked,
            "all_runtime_disabled": self.all_runtime_disabled,
            "execution_allowed": self.execution_allowed,
            "runtime_enabled": self.runtime_enabled,
            "fixture_execution_allowed": self.fixture_execution_allowed,
            "metadata_only": self.metadata_only,
            "ready_for_step27_demo": self.ready_for_step27_demo,
            "ready_for_production": self.ready_for_production,
            "generated_at": self.generated_at.isoformat(),
        }


class ProductionMigrationSubAgent:
    """Assess production readiness across all infrastructure. Metadata-only."""

    def __init__(self, metadata_only: bool = True, execution_allowed: bool = False,
                 runtime_enabled: bool = False):
        if execution_allowed or runtime_enabled:
            raise ValueError("execution_allowed and runtime_enabled must be False")
        self.metadata_only = True
        self.execution_allowed = False
        self.runtime_enabled = False

    def run_migration_assessment(self) -> ProductionMigrationReport:
        """Assess all 6 infrastructure components. No real connections."""
        pg = PostgresAdapter().assess_readiness()
        rd = RedisCacheAdapter().assess_readiness()
        os_obj = ObjectStorageAdapter().assess_readiness()
        tq = TaskQueueAdapter().assess_readiness()
        imp = ImportHub().assess_readiness()
        sync = SyncHub().assess_readiness()

        all_blocked = (
            not pg.connection_active
            and not rd.connection_active
            and not os_obj.connection_active
            and not tq.connection_active
            and not imp.import_active
            and not sync.sync_active
        )

        all_no_exec = (
            not pg.execution_allowed
            and not rd.execution_allowed
            and not os_obj.execution_allowed
            and not tq.execution_allowed
            and not imp.execution_allowed
            and not sync.execution_allowed
        )

        summary = {
            "total_components": 6,
            "components_assessed": 6,
            "connections_active": 0,
            "connections_blocked": 6,
            "components_configuration_ready": 6,
            "migration_ready": False,
            "demo_ready": True,
            "production_ready": False,
        }

        return ProductionMigrationReport(
            status="assessed",
            overall_ready=False,
            postgres=pg.to_dict(), redis=rd.to_dict(),
            object_storage=os_obj.to_dict(), task_queue=tq.to_dict(),
            import_hub=imp.to_dict(), sync_hub=sync.to_dict(),
            summary=summary,
            all_connections_blocked=all_blocked,
            all_execution_blocked=all_no_exec,
            all_runtime_disabled=True,
            execution_allowed=False, runtime_enabled=False,
            metadata_only=True,
            ready_for_step27_demo=True,
            ready_for_production=False,
        )

    def generate_usage_and_memory_test_data(self) -> dict[str, Any]:
        """Generate test data for usage and memory. No real DB write."""
        return {
            "test_users": [
                {"user_id": "u_test_1", "email": "demo@cognitive-os.local", "role": "admin"},
                {"user_id": "u_test_2", "email": "dev@cognitive-os.local", "role": "developer"},
                {"user_id": "u_test_3", "email": "viewer@cognitive-os.local", "role": "viewer"},
            ],
            "test_workspaces": [
                {"workspace_id": "ws_default", "name": "Default", "tenant_id": "t_demo"},
                {"workspace_id": "ws_team", "name": "Team Brain", "tenant_id": "t_demo"},
            ],
            "test_memories": [
                {"content": "Cognitive OS production migration assessed.", "memory_type": "note"},
                {"content": "Step 27 is metadata-only readiness assessment.", "memory_type": "note"},
                {"content": "PostgreSQL, Redis, S3, Task Queue configured.", "memory_type": "note"},
            ],
            "test_usage": [
                {"resource": "llm_call", "quantity": 150, "cost_cents": 75},
                {"resource": "search", "quantity": 45, "cost_cents": 0},
                {"resource": "memory", "quantity": 320, "cost_cents": 0},
            ],
            "metadata_only": True, "execution_allowed": False,
        }
