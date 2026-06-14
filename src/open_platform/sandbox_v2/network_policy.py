"""Sandbox v2 Network Egress Policy Engine — 网络访问前置策略。

安全策略（必须遵守）：
1. 默认 deny
2. fail closed
3. 只允许 http/https scheme
4. 禁止 localhost / loopback / link-local / metadata
5. 禁止所有私有网段
6. 端口默认只允许 80/443
7. 所有域名默认拒绝（除非 allowed_domains）
8. denied_domains 优先于 allowed_domains
9. 不做真实 DNS 查询
10. 不真实发起网络请求

全部为纯函数，便于测试。
"""

from __future__ import annotations

import ipaddress
import logging
import re
from typing import Any
from urllib.parse import urlparse

from src.open_platform.sandbox_v2.models import (
    SandboxV2RiskLevel,
    SandboxV2NetworkEgressAction,
    SandboxV2NetworkEgressStatus,
    SandboxNetworkEgressRequest,
    SandboxNetworkEgressPolicyDecision,
    SandboxNetworkPolicyConfig,
    BLOCKED_NETWORK_SCHEMES,
    ALLOWED_NETWORK_SCHEMES,
    DEFAULT_ALLOWED_PORTS,
    PRIVATE_NETWORKS_V4,
)

logger = logging.getLogger(__name__)

# 循环回环和保留主机名
_BLOCKED_HOSTNAMES: frozenset[str] = frozenset({
    "localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]",
    "0:0:0:0:0:0:0:1", "0000:0000:0000:0000:0000:0000:0000:0001",
})
_BLOCKED_IP_BYTES = (
    b"\x7f",          # 127.0.0.0/8
    b"\x00\x00\x00",  # 0.0.0.0/8
    b"\xa9\xfe",      # 169.254.0.0/16
)
# Special IPs
_METADATA_IPS: frozenset[str] = frozenset({
    "169.254.169.254", "100.100.100.200",
})
_METADATA_HOSTS: frozenset[str] = frozenset({
    "metadata.google.internal", "169.254.169.254",
})


def evaluate_egress_policy(
    request: SandboxNetworkEgressRequest,
    config: SandboxNetworkPolicyConfig | None = None,
) -> SandboxNetworkEgressPolicyDecision:
    """评估网络出站请求策略。不发起任何真实网络请求。"""
    try:
        return _eval_impl(request, config or SandboxNetworkPolicyConfig())
    except Exception:
        logger.exception("egress_policy_evaluation_failed")
        return SandboxNetworkEgressPolicyDecision(
            allowed=False, action=SandboxV2NetworkEgressAction.DENY,
            reason="Network egress policy evaluation raised an exception — fail closed.",
            risk_level=SandboxV2RiskLevel.CRITICAL, matched_rules=["exception_fail_closed"],
            fail_closed=True,
        )


def _eval_impl(
    r: SandboxNetworkEgressRequest,
    cfg: SandboxNetworkPolicyConfig,
) -> SandboxNetworkEgressPolicyDecision:
    matched: list[str] = []

    # Rule 0: allow_network check
    if not cfg.allow_network:
        return SandboxNetworkEgressPolicyDecision(
            reason="Network access is disabled by policy (allow_network=false).",
            risk_level=SandboxV2RiskLevel.LOW, matched_rules=["policy_deny_network"],
        )
    matched.append("policy_network_allowed")

    # Rule 1: url must exist
    if not r.url or not r.url.strip():
        return SandboxNetworkEgressPolicyDecision(
            reason="URL is missing — fail closed.",
            risk_level=SandboxV2RiskLevel.HIGH, matched_rules=["url_missing"],
            fail_closed=True,
        )

    # Rule 2: parse URL
    try:
        parsed = urlparse(r.url)
    except Exception:
        return SandboxNetworkEgressPolicyDecision(
            reason=f"URL parse failed for '{r.url}' — fail closed.",
            risk_level=SandboxV2RiskLevel.HIGH, matched_rules=["url_parse_failed"],
            fail_closed=True,
        )
    matched.append("url_parsed")

    # Rule 3: scheme check
    scheme = (r.scheme or parsed.scheme or "").lower()
    if not scheme:
        return SandboxNetworkEgressPolicyDecision(
            reason="URL has no scheme — fail closed.",
            risk_level=SandboxV2RiskLevel.HIGH, matched_rules=["scheme_missing"],
            fail_closed=True,
        )
    if scheme in BLOCKED_NETWORK_SCHEMES:
        return SandboxNetworkEgressPolicyDecision(
            reason=f"Scheme '{scheme}' is blocked for all requests.",
            risk_level=SandboxV2RiskLevel.CRITICAL, matched_rules=[*matched, "scheme_blocked"],
            fail_closed=True,
        )
    if scheme not in ALLOWED_NETWORK_SCHEMES:
        return SandboxNetworkEgressPolicyDecision(
            reason=f"Scheme '{scheme}' is not in the allowed list (http, https).",
            risk_level=SandboxV2RiskLevel.HIGH, matched_rules=[*matched, "scheme_not_allowed"],
            fail_closed=True,
        )
    scheme_allowed = True
    matched.append("scheme_allowed")

    # Rule 4: hostname / host check
    host = (r.hostname or parsed.hostname or "").strip().lower()
    if not host:
        return SandboxNetworkEgressPolicyDecision(
            reason="URL has no hostname — fail closed.",
            risk_level=SandboxV2RiskLevel.HIGH, matched_rules=[*matched, "host_missing"],
            fail_closed=True,
        )

    # Check blocked hostnames
    if host in _BLOCKED_HOSTNAMES:
        return SandboxNetworkEgressPolicyDecision(
            reason=f"Hostname '{host}' is blocked (loopback/special address).",
            risk_level=SandboxV2RiskLevel.CRITICAL,
            matched_rules=[*matched, "loopback_blocked"],
            fail_closed=True,
        )

    # Check metadata service hostnames
    if cfg.block_metadata_service and host in _METADATA_HOSTS:
        return SandboxNetworkEgressPolicyDecision(
            reason=f"Metadata service hostname '{host}' is blocked.",
            risk_level=SandboxV2RiskLevel.CRITICAL,
            matched_rules=[*matched, "metadata_host_blocked"],
            metadata_service_blocked=True, fail_closed=True,
        )

    # Rule 5: port check (prefer parsed port from URL over dataclass default)
    port = parsed.port or r.port or (443 if scheme == "https" else 80)
    allowed_ports = set(cfg.allowed_ports) if cfg.allowed_ports else DEFAULT_ALLOWED_PORTS
    denied_ports = set(cfg.denied_ports)

    if port in denied_ports:
        return SandboxNetworkEgressPolicyDecision(
            reason=f"Port {port} is explicitly denied.",
            risk_level=SandboxV2RiskLevel.CRITICAL,
            matched_rules=[*matched, "port_denied"], fail_closed=True,
        )
    if port not in allowed_ports:
        return SandboxNetworkEgressPolicyDecision(
            reason=f"Port {port} is not in allowed ports {sorted(allowed_ports)}.",
            risk_level=SandboxV2RiskLevel.MEDIUM,
            matched_rules=[*matched, "port_not_allowed"], fail_closed=True,
        )
    port_allowed = True
    matched.append("port_allowed")

    # Rule 6: IP / resolved_ips check
    ip_allowed = True
    resolved_ips = r.resolved_ips or []

    for ip_str in resolved_ips:
        if cfg.block_metadata_service and ip_str in _METADATA_IPS:
            return SandboxNetworkEgressPolicyDecision(
                reason=f"IP '{ip_str}' is a metadata service address — blocked.",
                risk_level=SandboxV2RiskLevel.CRITICAL,
                matched_rules=[*matched, "metadata_ip_blocked"],
                metadata_service_blocked=True, fail_closed=True,
            )
        if _is_private_ip(ip_str):
            return SandboxNetworkEgressPolicyDecision(
                reason=f"IP '{ip_str}' is in a private/reserved range — blocked.",
                risk_level=SandboxV2RiskLevel.CRITICAL,
                matched_rules=[*matched, "private_ip_blocked"],
                private_network_blocked=True, fail_closed=True,
            )
        if _is_loopback_ip(ip_str):
            return SandboxNetworkEgressPolicyDecision(
                reason=f"IP '{ip_str}' is a loopback address — blocked.",
                risk_level=SandboxV2RiskLevel.CRITICAL,
                matched_rules=[*matched, "loopback_ip_blocked"],
                fail_closed=True,
            )

    # If hostname looks like an IP, check it too
    if _looks_like_ip(host):
        if _is_private_ip(host) or _is_loopback_ip(host):
            return SandboxNetworkEgressPolicyDecision(
                reason=f"Hostname '{host}' is a blocked IP address.",
                risk_level=SandboxV2RiskLevel.CRITICAL,
                matched_rules=[*matched, "blocked_ip_as_host"],
                fail_closed=True,
            )

    matched.append("ip_check_passed")

    # Rule 7: DNS preflight
    dns_allowed = not cfg.require_dns_preflight or bool(resolved_ips)
    if not dns_allowed:
        if not cfg.require_dns_preflight:
            dns_allowed = True

    # Rule 8: Domain allowlist/denylist
    host_allowed = False
    if _looks_like_ip(host):
        # IP as hostname - only allowed if not blocked by IP rules above
        host_allowed = ip_allowed
    elif cfg.allowed_domains:
        host_allowed = _matches_domain_list(host, cfg.allowed_domains)
    else:
        host_allowed = False  # empty allowlist → deny all

    # denylist overrides
    if cfg.denied_domains and _matches_domain_list(host, cfg.denied_domains):
        host_allowed = False
        matched.append("domain_denied")

    if not host_allowed:
        return SandboxNetworkEgressPolicyDecision(
            reason=f"Domain '{host}' is not in the allowed domain list.",
            risk_level=SandboxV2RiskLevel.MEDIUM,
            matched_rules=[*matched, "domain_not_allowed"],
            scheme_allowed=scheme_allowed, port_allowed=port_allowed,
            ip_allowed=ip_allowed, dns_resolution_allowed=dns_allowed,
            fail_closed=True,
        )

    matched.append("domain_allowed")

    # All passed
    return SandboxNetworkEgressPolicyDecision(
        allowed=True,
        action=SandboxV2NetworkEgressAction.ALLOW_PREFLIGHT_ONLY,
        reason="Network egress preflight passed. No real network access was performed.",
        risk_level=SandboxV2RiskLevel.LOW,
        scheme_allowed=scheme_allowed, host_allowed=host_allowed,
        ip_allowed=ip_allowed, port_allowed=port_allowed,
        dns_resolution_allowed=dns_allowed,
        metadata_service_blocked=cfg.block_metadata_service,
        private_network_blocked=cfg.block_private_networks,
        matched_rules=matched, fail_closed=False,
    )


# ═══════════ IP Helpers ═══════════

def _is_private_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        return ip.is_private or ip.is_reserved or ip.is_multicast or ip.is_unspecified or ip.is_link_local
    except ValueError:
        return False


def _is_loopback_ip(ip_str: str) -> bool:
    try:
        return ipaddress.ip_address(ip_str).is_loopback
    except ValueError:
        return False


def _looks_like_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


# ═══════════ Domain Matching ═══════════

def _matches_domain_list(host: str, patterns: list[str]) -> bool:
    """检查 host 是否匹配 domain pattern 列表。

    Wildcard: *.example.com 匹配 a.example.com 但不匹配 badexample.com 或 example.com 自身。
    Exact: example.com 只匹配 example.com。
    """
    for pattern in patterns:
        pattern = pattern.lower().strip()
        if not pattern:
            continue
        if pattern.startswith("*."):
            suffix = pattern[2:]  # e.g., "example.com"
            if _is_subdomain(host, suffix):
                return True
        elif pattern == host:
            return True
    return False


def _is_subdomain(host: str, domain: str) -> bool:
    """host 是否是 domain 的子域名（不包括 domain 自身）。

    e.g. a.example.com 是 example.com 的子域名。
    badexample.com 不是 example.com 的子域名。
    """
    if host == domain:
        return False
    if host.endswith("." + domain):
        prefix = host[:-len(domain) - 1]
        return "." in prefix or bool(prefix)
    return False
