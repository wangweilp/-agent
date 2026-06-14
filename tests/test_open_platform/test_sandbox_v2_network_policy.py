"""Test Sandbox v2 Network Policy — 网络出站策略测试。"""
import pytest
from src.open_platform.sandbox_v2.models import (
    SandboxNetworkEgressRequest, SandboxNetworkPolicyConfig,
)
from src.open_platform.sandbox_v2.network_policy import (
    evaluate_egress_policy, _matches_domain_list, _is_subdomain,
    _is_private_ip, _is_loopback_ip, _looks_like_ip,
)


class TestDefaultDeny:
    def test_default_deny_no_url(self):
        req = SandboxNetworkEgressRequest(url="")
        d = evaluate_egress_policy(req)
        assert d.allowed is False

    def test_http_url_accepted_when_domain_allowed(self):
        cfg = SandboxNetworkPolicyConfig(allow_network=True, allowed_domains=["api.example.com"])
        req = SandboxNetworkEgressRequest(url="https://api.example.com/test")
        d = evaluate_egress_policy(req, cfg)
        assert d.allowed is True
        assert d.action == "allow_preflight_only"

    def test_allow_network_false_blocks_all(self):
        cfg = SandboxNetworkPolicyConfig(allow_network=False, allowed_domains=["example.com"])
        req = SandboxNetworkEgressRequest(url="https://example.com")
        d = evaluate_egress_policy(req, cfg)
        assert d.allowed is False
        assert "policy_deny_network" in d.matched_rules


class TestBlockedSchemes:
    def test_http_allowed(self):
        cfg = SandboxNetworkPolicyConfig(allow_network=True, allowed_domains=["ex.com"])
        d = evaluate_egress_policy(SandboxNetworkEgressRequest(url="http://ex.com"), cfg)
        assert d.allowed is True

    def test_file_blocked(self):
        cfg = SandboxNetworkPolicyConfig(allow_network=True)
        d = evaluate_egress_policy(SandboxNetworkEgressRequest(url="file:///etc/passwd"), cfg)
        assert d.allowed is False; assert "scheme_blocked" in d.matched_rules

    def test_ftp_blocked(self):
        cfg = SandboxNetworkPolicyConfig(allow_network=True)
        d = evaluate_egress_policy(SandboxNetworkEgressRequest(url="ftp://evil.com"), cfg)
        assert d.allowed is False


class TestBlockedHostnames:
    def _check(self, host, cfg=None):
        cfg = cfg or SandboxNetworkPolicyConfig(allow_network=True, allowed_domains=["example.com"])
        return evaluate_egress_policy(SandboxNetworkEgressRequest(url=f"https://{host}/test"), cfg)

    def test_localhost_denied(self): assert not self._check("localhost").allowed
    def test_loopback_denied(self): assert not self._check("127.0.0.1").allowed
    def test_ipv6_loopback_denied(self): assert not self._check("[::1]").allowed
    def test_metadata_ip_denied(self): assert not self._check("169.254.169.254").allowed


class TestPrivateIPs:
    def test_10_network_denied(self): assert _is_private_ip("10.0.0.1")
    def test_172_16_denied(self): assert _is_private_ip("172.16.0.1")
    def test_192_168_denied(self): assert _is_private_ip("192.168.1.1")
    def test_8_8_8_8_allowed(self): assert not _is_private_ip("8.8.8.8")
    def test_fc00_denied(self): assert _is_private_ip("fc00::1")
    def test_fe80_denied(self): assert _is_private_ip("fe80::1")
    def test_loopback_v4(self): assert _is_loopback_ip("127.0.0.1")
    def test_loopback_v6(self): assert _is_loopback_ip("::1")


class TestPortCheck:
    def _check_port(self, port, cfg=None):
        cfg = cfg or SandboxNetworkPolicyConfig(allow_network=True, allowed_domains=["ex.com"])
        return evaluate_egress_policy(SandboxNetworkEgressRequest(url="https://ex.com", port=port), cfg)

    def test_443_allowed(self): assert self._check_port(443).allowed
    def test_80_allowed(self): assert self._check_port(80).allowed
    def test_8080_denied_by_default(self): assert not self._check_port(8080).allowed


class TestDomainMatching:
    def test_wildcard_matches_subdomain(self):
        assert _matches_domain_list("sub.example.com", ["*.example.com"])

    def test_wildcard_not_match_exact(self):
        assert not _matches_domain_list("example.com", ["*.example.com"])

    def test_wildcard_not_match_bad(self):
        assert not _matches_domain_list("badexample.com", ["*.example.com"])

    def test_exact_match(self):
        assert _matches_domain_list("example.com", ["example.com"])

    def test_denied_overrides_allowed(self):
        # denylist has priority
        assert _matches_domain_list("evil.com", ["*.com"])  # allowed wildcard
        # but denylist check handled by policy engine order
        cfg = SandboxNetworkPolicyConfig(allow_network=True, allowed_domains=["*.com"], denied_domains=["evil.com"])
        d = evaluate_egress_policy(SandboxNetworkEgressRequest(url="https://evil.com"), cfg)
        assert not d.allowed


class TestResolvedIPs:
    def test_private_resolved_ips_blocked(self):
        cfg = SandboxNetworkPolicyConfig(allow_network=True, allowed_domains=["example.com"])
        req = SandboxNetworkEgressRequest(url="https://example.com", resolved_ips=["10.0.0.1"])
        d = evaluate_egress_policy(req, cfg)
        assert not d.allowed; assert "private_ip_blocked" in d.matched_rules

    def test_public_resolved_ips_ok(self):
        cfg = SandboxNetworkPolicyConfig(allow_network=True, allowed_domains=["example.com"])
        req = SandboxNetworkEgressRequest(url="https://example.com", resolved_ips=["8.8.8.8"])
        d = evaluate_egress_policy(req, cfg)
        assert d.allowed


class TestFailClosed:
    def test_exception_fail_closed(self):
        d = evaluate_egress_policy(None)  # type: ignore
        assert d.allowed is False
        assert d.fail_closed is True


class TestIsSubdomain:
    def test_sub_ok(self): assert _is_subdomain("a.example.com", "example.com")
    def test_exact_not_sub(self): assert not _is_subdomain("example.com", "example.com")
    def test_bad_not_sub(self): assert not _is_subdomain("badexample.com", "example.com")

class TestLooksLikeIP:
    def test_v4(self): assert _looks_like_ip("1.2.3.4")
    def test_v6(self): assert _looks_like_ip("::1")
    def test_hostname(self): assert not _looks_like_ip("example.com")
