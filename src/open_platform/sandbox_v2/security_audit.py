"""Sandbox v2 Security Audit Service — Step 14 审计服务。

Append-only audit events with hash chain.
Evidence bundle export with redaction.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from src.open_platform.sandbox_v2.models import (
    SandboxV2AuditEvent, SandboxV2AuditEventType, SandboxV2AuditSeverity,
    SandboxV2EvidenceBundle,
)

logger = logging.getLogger(__name__)

_SENSITIVE_KEYS = frozenset({
    "password", "secret", "token", "key", "credential",
    "dsn", "access_key", "secret_key", "api_key",
    "SANDBOX_V2_POSTGRES_DSN", "SANDBOX_V2_REDIS_URL",
    "SANDBOX_V2_MINIO_ACCESS_KEY", "SANDBOX_V2_MINIO_SECRET_KEY",
    "SANDBOX_V2_S3_ACCESS_KEY", "SANDBOX_V2_S3_SECRET_KEY",
})


class SandboxV2SecurityAuditService:
    """Sandbox v2 安全审计服务。"""

    def __init__(self, store: Any = None):
        self._store = store

    # ── Audit Events ──

    def create_audit_event(
        self, *,
        event_type: str = SandboxV2AuditEventType.ACCESS_ALLOWED,
        severity: str = SandboxV2AuditSeverity.INFO,
        principal_id: str = "", principal_type: str = "",
        organization_id: str = "", workspace_id: str = "",
        resource_type: str = "", resource_id: str = "",
        action: str = "", decision: str = "", reason: str = "",
        request_id: str = "", metadata: dict[str, Any] | None = None,
    ) -> SandboxV2AuditEvent:
        """创建审计事件。append-only。"""
        metadata_clean = self.redact_sensitive_metadata(metadata or {})

        previous_hash = ""
        if self._store:
            try:
                latest = self._store.get_latest_security_audit_event(
                    organization_id=organization_id, workspace_id=workspace_id,
                )
                if latest and hasattr(latest, 'event_hash'):
                    previous_hash = latest.event_hash
            except Exception:
                pass

        event = SandboxV2AuditEvent(
            event_type=event_type, severity=severity,
            principal_id=principal_id, principal_type=principal_type,
            organization_id=organization_id, workspace_id=workspace_id,
            resource_type=resource_type, resource_id=resource_id,
            action=action, decision=decision, reason=reason,
            request_id=request_id, previous_hash=previous_hash,
            metadata=metadata_clean,
        )
        event.event_hash = self.compute_event_hash(event)
        event.created_at = datetime.now(timezone.utc)

        if self._store:
            try:
                self._store.create_security_audit_event(event)
            except Exception as e:
                logger.warning(f"Failed to persist audit event: {e}")

        return event

    def compute_event_hash(self, event: SandboxV2AuditEvent) -> str:
        """计算审计事件哈希。"""
        data = {
            "audit_event_id": event.audit_event_id,
            "event_type": event.event_type,
            "severity": event.severity,
            "principal_id": event.principal_id,
            "principal_type": event.principal_type,
            "organization_id": event.organization_id,
            "workspace_id": event.workspace_id,
            "resource_type": event.resource_type,
            "resource_id": event.resource_id,
            "action": event.action,
            "decision": event.decision,
            "reason": event.reason,
            "request_id": event.request_id,
            "previous_hash": event.previous_hash,
            "created_at": _normalize_ts(event.created_at),
        }
        payload = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode()).hexdigest()

    def get_latest_audit_event(self, organization_id: str = "", workspace_id: str = "") -> SandboxV2AuditEvent | None:
        if self._store:
            try:
                return self._store.get_latest_security_audit_event(organization_id, workspace_id)
            except Exception:
                pass
        return None

    def verify_audit_chain(self, organization_id: str = "", workspace_id: str = "", limit: int = 100) -> dict[str, Any]:
        """校验审计哈希链。"""
        events: list[Any] = []
        if self._store:
            try:
                events = self._store.list_security_audit_events(
                    organization_id=organization_id, workspace_id=workspace_id, limit=limit,
                )
            except Exception:
                return {"valid": False, "reason": "Failed to load audit events", "tampered": [], "events_checked": 0}

        if not events:
            return {"valid": True, "reason": "No audit events to verify", "tampered": [], "events_checked": 0}

        # Events are returned in DESC order (newest first). Reverse for chain verification.
        events_asc = list(reversed(events))
        tampered: list[str] = []
        for i, event in enumerate(events_asc):
            if i == 0:
                continue
            prev = events_asc[i - 1]
            expected_prev = getattr(event, 'previous_hash', '')
            actual_prev = getattr(prev, 'event_hash', '')
            if expected_prev != actual_prev:
                tampered.append(getattr(event, 'audit_event_id', f'index-{i}'))

            # Verify current event hash
            computed = self.compute_event_hash(event)
            actual = getattr(event, 'event_hash', '')
            if computed != actual:
                tampered.append(f"hash-mismatch:{getattr(event, 'audit_event_id', f'index-{i}')}")

        return {
            "valid": len(tampered) == 0,
            "reason": "Audit chain verified" if not tampered else f"Found {len(tampered)} tampered events",
            "tampered": tampered,
            "events_checked": len(events),
        }

    def list_audit_events(self, organization_id: str = "", workspace_id: str = "",
                          event_type: str | None = None, severity: str | None = None,
                          limit: int = 50) -> list[Any]:
        if self._store:
            try:
                return self._store.list_security_audit_events(
                    organization_id=organization_id, workspace_id=workspace_id,
                    event_type=event_type, severity=severity, limit=limit,
                )
            except Exception:
                pass
        return []

    # ── Evidence Bundles ──

    def create_evidence_bundle(
        self, *,
        organization_id: str = "", workspace_id: str = "",
        created_by: str = "", title: str = "", description: str = "",
        resource_refs: list[dict[str, str]] | None = None,
        audit_event_ids: list[str] | None = None,
        job_ids: list[str] | None = None,
        artifact_ids: list[str] | None = None,
        package_request_ids: list[str] | None = None,
        network_request_ids: list[str] | None = None,
        kill_request_ids: list[str] | None = None,
    ) -> SandboxV2EvidenceBundle:
        """创建 evidence bundle。资源必须同 org/workspace。"""
        bundle = SandboxV2EvidenceBundle(
            organization_id=organization_id, workspace_id=workspace_id,
            created_by=created_by, title=title, description=description,
            resource_refs=resource_refs or [],
            audit_event_ids=audit_event_ids or [],
            job_ids=job_ids or [], artifact_ids=artifact_ids or [],
            package_request_ids=package_request_ids or [],
            network_request_ids=network_request_ids or [],
            kill_request_ids=kill_request_ids or [],
            redacted=True,
        )
        bundle.bundle_hash = _compute_bundle_hash(bundle)

        if self._store:
            try:
                self._store.create_evidence_bundle(bundle)
            except Exception as e:
                logger.warning(f"Failed to persist evidence bundle: {e}")

        return bundle

    def get_evidence_bundle(self, evidence_bundle_id: str) -> SandboxV2EvidenceBundle | None:
        if self._store:
            try:
                return self._store.get_evidence_bundle(evidence_bundle_id)
            except Exception:
                pass
        return None

    def list_evidence_bundles(self, organization_id: str = "", workspace_id: str = "",
                               limit: int = 50) -> list[Any]:
        if self._store:
            try:
                return self._store.list_evidence_bundles(
                    organization_id=organization_id, workspace_id=workspace_id, limit=limit,
                )
            except Exception:
                pass
        return []

    def export_evidence_bundle_json(self, evidence_bundle_id: str) -> dict[str, Any]:
        """导出 evidence bundle JSON。redacted=true。"""
        bundle = self.get_evidence_bundle(evidence_bundle_id)
        if bundle is None:
            return {"error": "Evidence bundle not found"}
        d = bundle.to_dict() if hasattr(bundle, 'to_dict') else {}
        d["redacted"] = True
        # Redact any sensitive metadata
        if "metadata" in d:
            d["metadata"] = self.redact_sensitive_metadata(d["metadata"])
        return d

    @staticmethod
    def redact_sensitive_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
        """移除敏感 metadata。"""
        result: dict[str, Any] = {}
        for k, v in metadata.items():
            k_lower = k.lower()
            is_sensitive = any(s in k_lower for s in _SENSITIVE_KEYS)
            if is_sensitive:
                result[k] = "[REDACTED]"
            elif isinstance(v, dict):
                result[k] = SandboxV2SecurityAuditService.redact_sensitive_metadata(v)
            elif isinstance(v, str) and len(v) > 200:
                # 截断过长文本
                for sk in _SENSITIVE_KEYS:
                    if sk in v.lower():
                        result[k] = "[REDACTED]"
                        break
                else:
                    result[k] = v
            else:
                result[k] = v
        return result


def _normalize_ts(ts: Any) -> str:
    """Normalize timestamp to consistent ISO format."""
    if hasattr(ts, 'isoformat'):
        return ts.strftime("%Y-%m-%dT%H:%M:%S.000000+00:00")
    return str(ts)


def _compute_bundle_hash(bundle: SandboxV2EvidenceBundle) -> str:
    data = {
        "evidence_bundle_id": bundle.evidence_bundle_id,
        "organization_id": bundle.organization_id,
        "workspace_id": bundle.workspace_id,
        "created_by": bundle.created_by,
        "title": bundle.title,
        "resource_refs": bundle.resource_refs,
        "audit_event_ids": bundle.audit_event_ids,
        "created_at": bundle.created_at.isoformat() if hasattr(bundle.created_at, 'isoformat') else str(bundle.created_at),
    }
    payload = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()
