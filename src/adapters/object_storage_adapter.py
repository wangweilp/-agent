"""Object Storage Adapter — metadata-only, no real S3/MinIO connection in Step 27.

Step 27: readiness assessment for object storage.
No real connection. storage_active=False.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from src.adapters.config import Settings


class ObjectStorageStatus(StrEnum):
    NOT_STARTED = "not_started"
    CONFIGURED = "configured"
    CONNECTION_ACTIVE = "connection_active"
    STORAGE_ACTIVE = "storage_active"
    FAIL_CLOSED = "fail_closed"


@dataclass
class ObjectStorageReport:
    report_id: str = field(default_factory=lambda: f"osrep_{uuid4().hex[:16]}")
    status: str = ObjectStorageStatus.NOT_STARTED
    connection_active: bool = False
    storage_active: bool = False
    provider: str = "minio"
    bucket: str = "cognitive-os"
    buckets_defined: int = 0
    recommended_buckets: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    execution_allowed: bool = False
    runtime_enabled: bool = False
    metadata_only: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_connected(self) -> bool: return False
    def is_storage_active(self) -> bool: return False

    def to_dict(self):
        return {
            "report_id": self.report_id, "status": self.status,
            "connection_active": self.connection_active,
            "storage_active": self.storage_active,
            "provider": self.provider, "bucket": self.bucket,
            "buckets_defined": self.buckets_defined,
            "recommended_buckets": self.recommended_buckets,
            "warnings": self.warnings,
            "execution_allowed": self.execution_allowed,
            "runtime_enabled": self.runtime_enabled,
            "metadata_only": self.metadata_only,
            "created_at": self.created_at.isoformat(),
        }


RECOMMENDED_BUCKETS = {
    "memory-attachments": "User memory file attachments",
    "import-files": "Imported markdown/PDF files",
    "agent-artifacts": "Agent execution artifacts (future)",
    "analytics-exports": "Analytics report exports",
    "backups": "Database backup snapshots",
}


class ObjectStorageAdapter:
    """Object storage readiness adapter. Metadata-only. No real S3/MinIO."""

    def __init__(self, settings: Settings | None = None):
        self._settings = settings

    def assess_readiness(self) -> ObjectStorageReport:
        return ObjectStorageReport(
            status=ObjectStorageStatus.CONFIGURED,
            connection_active=False, storage_active=False,
            provider="minio", bucket="cognitive-os",
            buckets_defined=len(RECOMMENDED_BUCKETS),
            recommended_buckets=list(RECOMMENDED_BUCKETS.keys()),
            warnings=["No real S3/MinIO connection established",
                       "Storage is metadata-configured only",
                       "boto3/minio-py not imported"],
            execution_allowed=False, runtime_enabled=False, metadata_only=True,
        )

    def get_bucket_config(self) -> dict[str, str]:
        return dict(RECOMMENDED_BUCKETS)

    def export_config(self) -> dict[str, Any]:
        return {
            "provider": "minio",
            "endpoint": "http://localhost:9000",
            "access_key": "***",
            "secret_key": "***",
            "bucket": "cognitive-os",
            "connection_active": False,
            "buckets": self.get_bucket_config(),
            "metadata_only": True,
        }
