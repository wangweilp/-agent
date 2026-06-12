"""Runtime Capability Service — metadata registry, no runtime, no execution."""
from __future__ import annotations
import logging
from .runtime_capability import *

logger = logging.getLogger(__name__)


class RuntimeCapabilityService:
    def __init__(self, store=None, usage_store=None):
        self._store = store; self._usage_store = usage_store

    def list_capabilities(self, *, category="", status=""):
        if self._store is None: raise ValueError("store not available")
        return self._store.list_capabilities(category=category, status=status)

    def get_capability(self, capability_id):
        if self._store is None: raise ValueError("store not available")
        c = self._store.get_capability(capability_id)
        if c is None: raise RuntimeCapabilityNotFoundError(f"Not found: {capability_id}")
        return c

    def update_capability(self, capability_id, status=None, reason=None, metadata=None):
        if self._store is None: raise ValueError("store not available")
        c = self._store.get_capability(capability_id)
        if c is None: raise RuntimeCapabilityNotFoundError(f"Not found: {capability_id}")
        if status is not None: c.status = status
        if reason is not None: c.reason = reason
        if metadata is not None: c.metadata = {**c.metadata, **metadata}
        updated = self._store.update_capability(c)
        self._try_usage(updated, "update")
        return updated

    def export_matrix(self):
        if self._store is None: raise ValueError("store not available")
        return self._store.export_matrix()

    def seed_defaults(self):
        if self._store is None: raise ValueError("store not available")
        if hasattr(self._store, "seed_default_capabilities"):
            self._store.seed_default_capabilities()
            self._try_usage(None, "seed")

    def _try_usage(self, cap, action):
        if self._usage_store is None: return
        try:
            from src.core.usage import UsageEvent, UsageResource, UsageUnit
            resource = UsageResource.RUNTIME_CAPABILITY_ACCESS
            tid = cap.tenant_id if (cap and hasattr(cap, "tenant_id")) else ""
            self._usage_store.record_event(UsageEvent(
                tenant_id=tid or "", user_id="system", workspace_id=tid or "",
                resource=resource, quantity=1, unit=UsageUnit.COUNT,
                metadata={"action": action, "metadata_only": True,
                          "execution_allowed": False, "runtime_enabled": False}))
        except Exception: logger.warning("rtcap_usage_failed", exc_info=True)
