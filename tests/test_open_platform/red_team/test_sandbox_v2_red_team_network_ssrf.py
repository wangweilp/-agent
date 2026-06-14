"""Red-Team Network SSRF / Egress Tests — 网络出站攻击测试。

验证：localhost/内网/metadata/危险scheme/IP欺骗/域名绕过均被拒绝。
不真实发起网络请求，不做 DNS 查询。
"""

import pytest
from src.open_platform.sandbox_v2.models import (
    SandboxNetworkEgressRequest, SandboxNetworkPolicyConfig,
)
from src.open_platform.sandbox_v2.network_policy import evaluate_egress_policy


def _cfg(**kw):
    return SandboxNetworkPolicyConfig(allow_network=True, allowed_domains=kw.get("allowed_domains", ["api.example.com"]),
                                      denied_domains=kw.get("denied_domains", []), **{k: v for k, v in kw.items() if k not in ("allowed_domains", "denied_domains")})

def _req(url, **kw):
    return SandboxNetworkEgressRequest(url=url, **kw)


class TestSSRFInternal:
    """内网 SSRF 攻击必须拒绝。"""
    def check(self, url): return not evaluate_egress_policy(_req(url), _cfg()).allowed

    def test_localhost(self): assert self.check("http://localhost")
    def test_loopback(self): assert self.check("http://127.0.0.1")
    def test_zero(self): assert self.check("http://0.0.0.0")
    def test_ipv6_loopback(self): assert self.check("http://[::1]")
    def test_metadata_aws(self): assert self.check("http://169.254.169.254")
    def test_metadata_gcp(self): assert self.check("http://metadata.google.internal")
    def test_private_10(self): assert self.check("http://10.0.0.1")
    def test_private_172(self): assert self.check("http://172.16.0.1")
    def test_private_192(self): assert self.check("http://192.168.1.1")
    def test_ipv6_private(self): assert self.check("http://[fc00::1]")
    def test_ipv6_link_local(self): assert self.check("http://[fe80::1]")


class TestDangerousSchemes:
    """危险 scheme 必须拒绝。"""
    def check(self, url): return not evaluate_egress_policy(_req(url), _cfg()).allowed

    def test_file(self): assert self.check("file:///etc/passwd")
    def test_ftp(self): assert self.check("ftp://example.com/file")
    def test_gopher(self): assert self.check("gopher://example.com")
    def test_dict(self): assert self.check("dict://example.com")


class TestPortAbuse:
    """非标准端口拒绝。"""
    def test_ssh_port(self): assert not evaluate_egress_policy(_req("http://example.com:22"), _cfg(allowed_domains=["example.com"])).allowed
    def test_docker_port(self): assert not evaluate_egress_policy(_req("http://example.com:2375"), _cfg(allowed_domains=["example.com"])).allowed


class TestHostnameAbuse:
    """hostname 欺诈拒绝。"""
    def test_userinfo_at(self):
        d = evaluate_egress_policy(_req("http://example.com@127.0.0.1"), _cfg())
        assert not d.allowed

    def test_wildcard_bypass(self):
        d = evaluate_egress_policy(_req("https://badexample.com"), _cfg(allowed_domains=["*.example.com"]))
        assert not d.allowed

    def test_denied_overrides(self):
        d = evaluate_egress_policy(_req("https://evil.com"), _cfg(allowed_domains=["*.com"], denied_domains=["evil.com"]))
        assert not d.allowed


class TestResolvedIPBypass:
    """resolved_ips 包含 private IP 时必须拒绝，即使 hostname 在 allowlist。"""
    def test_private_ip_overrides_hostname(self):
        d = evaluate_egress_policy(_req("https://api.example.com", resolved_ips=["10.0.0.1"]), _cfg())
        assert not d.allowed
        assert "private_ip_blocked" in d.matched_rules


class TestPolicyDenyAll:
    """allow_network=false 时全部拒绝。"""
    def test_deny_all(self):
        cfg = SandboxNetworkPolicyConfig(allow_network=False)
        d = evaluate_egress_policy(_req("https://safe.com"), cfg)
        assert not d.allowed


class TestFailClosed:
    def test_none_request(self):
        d = evaluate_egress_policy(None)  # type: ignore
        assert not d.allowed
        assert d.fail_closed is True
