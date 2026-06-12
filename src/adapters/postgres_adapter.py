"""PostgreSQL Adapter — metadata-only readiness, no real connection in Step 27.

Step 27: readiness assessment for production migration.
No real SQLite→PG migration yet. connection_active=False.
All is_connected()/is_migration_ready() return False.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from src.adapters.config import Settings


class PostgresMigrationStatus(StrEnum):
    NOT_STARTED = "not_started"
    SCHEMA_DEFINED = "schema_defined"
    MIGRATION_PLANNED = "migration_planned"
    MIGRATION_READY = "migration_ready"
    CONNECTION_ACTIVE = "connection_active"
    MIGRATION_COMPLETE = "migration_complete"
    FAIL_CLOSED = "fail_closed"


@dataclass
class PostgresMigrationReport:
    report_id: str = field(default_factory=lambda: f"pgmig_{uuid4().hex[:16]}")
    status: str = PostgresMigrationStatus.NOT_STARTED
    connection_active: bool = False
    migration_ready: bool = False
    schema_validated: bool = False
    tables_defined: int = 0
    tables_migrated: int = 0
    existing_sqlite_tables: list[str] = field(default_factory=list)
    target_pg_tables: list[str] = field(default_factory=list)
    migration_commands: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    execution_allowed: bool = False
    runtime_enabled: bool = False
    metadata_only: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_connected(self) -> bool: return False
    def is_migration_ready(self) -> bool: return False

    def to_dict(self):
        return {
            "report_id": self.report_id, "status": self.status,
            "connection_active": self.connection_active,
            "migration_ready": self.migration_ready,
            "schema_validated": self.schema_validated,
            "tables_defined": self.tables_defined,
            "tables_migrated": self.tables_migrated,
            "existing_sqlite_tables": self.existing_sqlite_tables,
            "target_pg_tables": self.target_pg_tables,
            "errors": self.errors, "warnings": self.warnings,
            "execution_allowed": self.execution_allowed,
            "runtime_enabled": self.runtime_enabled,
            "metadata_only": self.metadata_only,
            "created_at": self.created_at.isoformat(),
        }


# Target PostgreSQL schema definitions (for migration planning only)
PG_TARGET_SCHEMA = {
    "users": """
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL DEFAULT '', password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user', tenant_id TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """,
    "workspaces": """
        CREATE TABLE IF NOT EXISTS workspaces (
            workspace_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
            name TEXT NOT NULL DEFAULT '', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """,
    "memberships": """
        CREATE TABLE IF NOT EXISTS memberships (
            membership_id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
            workspace_id TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'member',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """,
    "memories": """
        CREATE TABLE IF NOT EXISTS memories (
            memory_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
            user_id TEXT, content TEXT NOT NULL DEFAULT '',
            memory_type TEXT NOT NULL DEFAULT 'note', importance REAL DEFAULT 0.5,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """,
    "usage_events": """
        CREATE TABLE IF NOT EXISTS usage_events (
            event_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
            user_id TEXT, resource TEXT NOT NULL,
            quantity INTEGER DEFAULT 1, cost_cents INTEGER DEFAULT 0,
            timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """,
    "runtime_kill_switch_policies": """
        CREATE TABLE IF NOT EXISTS runtime_kill_switch_policies (
            policy_id TEXT PRIMARY KEY, tenant_id TEXT,
            scope TEXT NOT NULL DEFAULT 'global_runtime',
            enabled_metadata_only INTEGER DEFAULT 1,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """,
    "runtime_incidents": """
        CREATE TABLE IF NOT EXISTS runtime_incidents (
            incident_id TEXT PRIMARY KEY, tenant_id TEXT,
            incident_type TEXT NOT NULL DEFAULT '',
            severity TEXT NOT NULL DEFAULT 'medium',
            status TEXT NOT NULL DEFAULT 'open',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """,
}


class PostgresAdapter:
    """PostgreSQL migration readiness adapter. Metadata-only. No real PG connection."""

    def __init__(self, settings: Settings | None = None):
        self._settings = settings
        self._connected = False
        self._migration_ready = False

    def assess_readiness(self) -> PostgresMigrationReport:
        """Assess PG migration readiness. No real connection."""
        report = PostgresMigrationReport(
            status=PostgresMigrationStatus.MIGRATION_PLANNED,
            connection_active=False,
            migration_ready=False,
            schema_validated=True,
            tables_defined=len(PG_TARGET_SCHEMA),
            target_pg_tables=list(PG_TARGET_SCHEMA.keys()),
            existing_sqlite_tables=[
                "users", "workspaces", "memberships", "memories",
                "usage_events", "runtime_kill_switch_policies",
                "runtime_incidents", "runtime_safety_audit_events",
                "package_download_worker_policies", "runtime_capabilities",
                "policy_decisions"
            ],
            warnings=["No real PostgreSQL connection established",
                       "Migration is metadata-planned only",
                       "Alembic migration scripts not yet generated"],
            execution_allowed=False, runtime_enabled=False, metadata_only=True,
        )
        return report

    def generate_migration_plan(self) -> dict[str, Any]:
        """Generate migration plan commands. No real execution."""
        return {
            "target": "PostgreSQL 16+",
            "orm": "SQLAlchemy 2.0 + Alembic",
            "tables": list(PG_TARGET_SCHEMA.keys()),
            "migration_order": [
                "1. Create PG database and user",
                "2. Run Alembic init and autogenerate",
                "3. Create all tables via CREATE TABLE IF NOT EXISTS",
                "4. Verify schema parity with SQLite",
                "5. Run data migration scripts (SQLite → PG)",
                "6. Verify data integrity",
                "7. Update connection config",
                "8. Run full test suite against PG",
                "9. Switch application to PG",
                "10. Keep SQLite as backup",
            ],
            "connection_string_template": "postgresql://user:pass@host:5432/cognitive_os",
            "alembic_commands": [
                "alembic init alembic",
                "alembic revision --autogenerate -m 'initial_schema'",
                "alembic upgrade head",
            ],
            "metadata_only": True,
            "execution_allowed": False,
        }

    def export_schema_snapshot(self) -> dict[str, str]:
        """Export PG schema for documentation. No real migration."""
        return {k: v.strip() for k, v in PG_TARGET_SCHEMA.items()}
