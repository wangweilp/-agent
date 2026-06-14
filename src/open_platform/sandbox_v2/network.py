"""Sandbox v2 Network Egress Service — 网络访问预检服务。

提供网络访问前置策略与审计控制面。
不真实发起网络请求。不做真实 DNS 查询。

安全约束：
- 默认禁止所有外网访问
- 不做真实 HTTP 请求
- 不做真实 DNS resolution
- 只做策略预检
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.open_platform.sandbox_v2.models import (
    SandboxV2RiskLevel,
    SandboxV2NetworkEgressAction,
    SandboxV2NetworkEgressStatus,
    SandboxNetworkEgressRequest,
    SandboxNetworkEgressPolicyDecision,
    SandboxNetworkEgressAuditRecord,
    SandboxNetworkPolicyConfig,
)
from src.open_platform.sandbox_v2.network_policy import evaluate_egress_policy

logger = logging.getLogger(__name__)


class SandboxNetworkEgressService:
    """网络出站预检服务 — 只做策略检查，不访问网络。"""

    def __init__(self, store: Any = None, policy_config: SandboxNetworkPolicyConfig | None = None):
        self._store = store
        self._config = policy_config or SandboxNetworkPolicyConfig()

    def create_egress_request(self, **kw) -> dict:
        """创建网络出站请求并评估策略。"""
        request = SandboxNetworkEgressRequest(
            job_id=kw.get("job_id", ""),
            organization_id=kw.get("organization_id", ""),
            workspace_id=kw.get("workspace_id", ""),
            requested_by=kw.get("requested_by", ""),
            url=kw.get("url", ""),
            scheme=kw.get("scheme", ""),
            hostname=kw.get("hostname", ""),
            port=kw.get("port", 443),
            resolved_ips=kw.get("resolved_ips", []),
            method=kw.get("method", "GET"),
            purpose=kw.get("purpose", ""),
            metadata=kw.get("metadata", {}),
        )

        decision = evaluate_egress_policy(request, self._config)
        request.status = SandboxV2NetworkEgressStatus.ALLOWED_PREFLIGHT if decision.allowed else SandboxV2NetworkEgressStatus.REJECTED
        request.risk_level = decision.risk_level
        request.reason = decision.reason

        # Persist
        if self._store:
            self._store.create_network_egress_request(request)

        # Audit
        if self._store:
            self._store.create_network_egress_audit_record(SandboxNetworkEgressAuditRecord(
                egress_request_id=request.egress_request_id,
                job_id=request.job_id, organization_id=request.organization_id,
                workspace_id=request.workspace_id, url=request.url,
                hostname=request.hostname, resolved_ips=request.resolved_ips,
                decision=decision.action, reason=decision.reason,
                risk_level=decision.risk_level, created_at=datetime.now(timezone.utc),
                metadata={"preflight_only": True, "no_real_network": True},
            ))

        return {"egress_request": request.to_dict(), "decision": decision.to_dict()}

    def evaluate_egress_policy(self, **kw) -> dict:
        """即时策略预检，不持久化。"""
        request = SandboxNetworkEgressRequest(
            url=kw.get("url", ""), scheme=kw.get("scheme", ""),
            hostname=kw.get("hostname", ""), port=kw.get("port", 443),
            resolved_ips=kw.get("resolved_ips", []), purpose=kw.get("purpose", ""),
        )
        decision = evaluate_egress_policy(request, self._config)
        return {"allowed": decision.allowed, "action": decision.action,
                "reason": decision.reason, "risk_level": decision.risk_level,
                "matched_rules": decision.matched_rules,
                "preflight_only": True, "no_real_network": True,
                "decision": decision.to_dict()}

    def list_egress_requests(self, job_id: str | None = None, organization_id: str | None = None, workspace_id: str | None = None, status: str | None = None, limit: int = 50) -> list[dict]:
        if not self._store: return []
        return [r.to_dict() for r in self._store.list_network_egress_requests(job_id=job_id, organization_id=organization_id, workspace_id=workspace_id, status=status, limit=limit)]

    def get_egress_request(self, egress_request_id: str) -> dict | None:
        if not self._store: return None
        r = self._store.get_network_egress_request(egress_request_id)
        return r.to_dict() if r else None

    def list_audit_records(self, egress_request_id: str | None = None, job_id: str | None = None, limit: int = 50) -> list[dict]:
        if not self._store: return []
        return [a.to_dict() for a in self._store.list_network_egress_audit_records(egress_request_id=egress_request_id, job_id=job_id, limit=limit)]

    def get_readiness(self) -> dict:
        return {
            "network_egress_policy": True,
            "network_preflight": True,
            "external_network_access": False,
            "egress_proxy": False,
            "dns_runtime_resolution": False,
            "private_network_blocking": self._config.block_private_networks,
            "metadata_service_blocking": self._config.block_metadata_service,
            "localhost_blocking": self._config.block_loopback,
            "allowed_domain_policy": True,
            "ip_denylist_policy": True,
            "runtime_network_namespace": False,
            "iptables_enforcement": False,
            "current_mode": "preflight_only",
            "no_real_network": True,
        }
