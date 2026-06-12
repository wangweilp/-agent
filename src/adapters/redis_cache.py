"""Redis Cache Adapter — metadata-only, no real Redis connection in Step 27.

Step 27: readiness assessment for Redis caching.
No real Redis connection. cache_active=False.
All get/set operations return placeholder values.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from src.adapters.config import Settings


class RedisCacheStatus(StrEnum):
    NOT_STARTED = "not_started"
    CONFIGURED = "configured"
    CONNECTION_ACTIVE = "connection_active"
    CACHE_ACTIVE = "cache_active"
    FAIL_CLOSED = "fail_closed"


@dataclass
class RedisCacheReport:
    report_id: str = field(default_factory=lambda: f"rdrep_{uuid4().hex[:16]}")
    status: str = RedisCacheStatus.NOT_STARTED
    connection_active: bool = False
    cache_active: bool = False
    keys_defined: int = 0
    ttl_default_seconds: int = 3600
    cache_prefix: str = "cognitive_os:"
    recommended_keys: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    execution_allowed: bool = False
    runtime_enabled: bool = False
    metadata_only: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_connected(self) -> bool: return False
    def is_cache_active(self) -> bool: return False

    def to_dict(self):
        return {
            "report_id": self.report_id, "status": self.status,
            "connection_active": self.connection_active,
            "cache_active": self.cache_active,
            "keys_defined": self.keys_defined,
            "ttl_default_seconds": self.ttl_default_seconds,
            "cache_prefix": self.cache_prefix,
            "recommended_keys": self.recommended_keys,
            "warnings": self.warnings,
            "execution_allowed": self.execution_allowed,
            "runtime_enabled": self.runtime_enabled,
            "metadata_only": self.metadata_only,
            "created_at": self.created_at.isoformat(),
        }


# Recommended cache key patterns (for documentation only)
REDIS_CACHE_KEYS = {
    "memory": {
        "pattern": "cognitive_os:memory:{memory_id}",
        "ttl": 3600,
        "description": "Single memory entry cache",
    },
    "memory_list": {
        "pattern": "cognitive_os:memory:list:{tenant_id}:{user_id}",
        "ttl": 300,
        "description": "Memory list for a user",
    },
    "timeline": {
        "pattern": "cognitive_os:timeline:{tenant_id}",
        "ttl": 600,
        "description": "Timeline cache for a tenant",
    },
    "usage_stats": {
        "pattern": "cognitive_os:usage:{tenant_id}:{month}",
        "ttl": 1800,
        "description": "Usage statistics for a tenant-month",
    },
    "analytics_summary": {
        "pattern": "cognitive_os:analytics:summary",
        "ttl": 900,
        "description": "Platform analytics summary",
    },
    "policy_decision": {
        "pattern": "cognitive_os:policy:{decision_id}",
        "ttl": 600,
        "description": "Cached policy decision result",
    },
}


class RedisCacheAdapter:
    """Redis cache readiness adapter. Metadata-only. No real Redis connection."""

    def __init__(self, settings: Settings | None = None):
        self._settings = settings
        self._connected = False
        self._cache_active = False
        self._store: dict[str, str] = {}  # local placeholder only

    def assess_readiness(self) -> RedisCacheReport:
        return RedisCacheReport(
            status=RedisCacheStatus.CONFIGURED,
            connection_active=False,
            cache_active=False,
            keys_defined=len(REDIS_CACHE_KEYS),
            recommended_keys=list(REDIS_CACHE_KEYS.keys()),
            warnings=["No real Redis connection established",
                       "Cache is metadata-configured only",
                       "redis-py not imported"],
            execution_allowed=False, runtime_enabled=False, metadata_only=True,
        )

    def get_cache_key_patterns(self) -> dict[str, dict]:
        return {k: dict(v) for k, v in REDIS_CACHE_KEYS.items()}

    def export_config(self) -> dict[str, Any]:
        return {
            "host": "localhost", "port": 6379, "db": 0,
            "connection_active": False,
            "prefix": "cognitive_os:",
            "default_ttl": 3600,
            "key_patterns": self.get_cache_key_patterns(),
            "metadata_only": True,
        }
