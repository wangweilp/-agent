"""Sandbox v2 SAML Replay Protection Service — Step 22.

AssertionID 一次性消费。重复 Assertion 必须拒绝。

接口：
- ReplayStore (abstract)
- MemoryReplayStore (default)
- SQLiteReplayStore (future)

安全原则：
1. 默认 disabled
2. AssertionID 只能使用一次
3. 重复 Assertion → 拒绝
4. 过期条目自动清除
"""
from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any

from src.open_platform.sandbox_v2.models import SandboxV2SAMLReplayEntry

logger = logging.getLogger(__name__)


class SandboxV2SAMLReplayStore(ABC):
    """SAML Replay Store 抽象接口。"""

    @abstractmethod
    def consume(self, assertion_id: str, issuer: str = "", tenant_id: str = "",
                ttl_seconds: int = 3600) -> tuple[bool, str]:
        """尝试消费 assertion_id。返回 (consumed, reason)。

        consumed=True 表示首次使用，已记录。
        consumed=False 表示已存在（重复）。
        """
        ...

    @abstractmethod
    def is_consumed(self, assertion_id: str) -> bool:
        """检查 assertion_id 是否已被消费。"""
        ...

    @abstractmethod
    def clear_expired(self) -> int:
        """清除过期条目。返回清除数量。"""
        ...

    @abstractmethod
    def size(self) -> int:
        """当前存储条目数。"""
        ...


class SandboxV2MemoryReplayStore(SandboxV2SAMLReplayStore):
    """基于内存的 Replay Store。默认实现。"""

    def __init__(self):
        self._store: dict[str, SandboxV2SAMLReplayEntry] = {}
        self._lock = threading.Lock()

    def consume(self, assertion_id: str, issuer: str = "", tenant_id: str = "",
                ttl_seconds: int = 3600) -> tuple[bool, str]:
        if not assertion_id:
            return False, "Empty assertion_id"

        now = datetime.now(timezone.utc)
        with self._lock:
            # Check if already consumed
            existing = self._store.get(assertion_id)
            if existing and existing.expires_at > now:
                return False, f"Assertion {assertion_id[:20]}... has already been consumed (replay detected)"

            # First consumption
            entry = SandboxV2SAMLReplayEntry(
                assertion_id=assertion_id,
                issuer=issuer,
                consumed_at=now,
                expires_at=now + timedelta(seconds=ttl_seconds),
                tenant_id=tenant_id,
            )
            self._store[assertion_id] = entry
            return True, f"Assertion {assertion_id[:20]}... accepted (first use)"

    def is_consumed(self, assertion_id: str) -> bool:
        if not assertion_id:
            return False
        now = datetime.now(timezone.utc)
        entry = self._store.get(assertion_id)
        if not entry:
            return False
        if entry.expires_at <= now:
            return False  # expired → not consumed for practical purposes
        return True

    def clear_expired(self) -> int:
        now = datetime.now(timezone.utc)
        removed = 0
        with self._lock:
            expired = [k for k, v in self._store.items() if v.expires_at <= now]
            for k in expired:
                del self._store[k]
                removed += 1
        return removed

    def size(self) -> int:
        return len(self._store)


class SandboxV2SAMLReplayService:
    """SAML Replay Protection Service。默认 disabled。"""

    def __init__(self, settings: Any = None, store: SandboxV2SAMLReplayStore | None = None):
        self._settings = settings
        self._store = store or SandboxV2MemoryReplayStore()

    def _cfg(self, key: str, default: Any = None) -> Any:
        return getattr(self._settings, key, default) if self._settings else default

    @property
    def enabled(self) -> bool:
        return bool(self._cfg("saml_assertion_replay_protection_enabled", False))

    @property
    def ttl_seconds(self) -> int:
        return int(self._cfg("saml_replay_store_ttl_seconds", 3600))

    def check_and_consume(self, assertion_id: str, issuer: str = "",
                          tenant_id: str = "") -> tuple[bool, str]:
        """检查并消费 assertion_id。首次使用 → 成功；重复 → 拒绝。"""
        if not self.enabled:
            return True, "Replay protection disabled — assertion accepted without replay check"

        if not assertion_id:
            return False, "Empty assertion_id — rejected"

        # Clear expired entries periodically
        self._store.clear_expired()

        consumed, reason = self._store.consume(
            assertion_id, issuer=issuer, tenant_id=tenant_id,
            ttl_seconds=self.ttl_seconds,
        )
        if not consumed:
            logger.warning(f"SAML replay detected: {reason}")
        return consumed, reason

    def is_consumed(self, assertion_id: str) -> bool:
        return self._store.is_consumed(assertion_id)

    def clear_expired(self) -> int:
        return self._store.clear_expired()

    def store_size(self) -> int:
        return self._store.size()

    def get_readiness(self) -> dict[str, Any]:
        """Replay Protection Readiness。"""
        return {
            "enabled": self.enabled,
            "ready": self.enabled,
            "store_type": type(self._store).__name__,
            "store_size": self._store.size(),
            "ttl_seconds": self.ttl_seconds,
            "status": "ready" if self.enabled else "disabled",
            "reason": "" if self.enabled else "SAML_ASSERTION_REPLAY_PROTECTION_ENABLED=false",
        }
