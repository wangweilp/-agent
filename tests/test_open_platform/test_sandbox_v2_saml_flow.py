"""SAML Flow tests (Step 20)."""
from __future__ import annotations
import sys; from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pytest
from src.open_platform.sandbox_v2.saml_flow import SandboxV2SAMLFlowService
from src.open_platform.sandbox_v2.models import SandboxV2SSOFlowStatus
from src.adapters.sqlite_sandbox_v2_store import SQLiteSandboxV2Store
from src.adapters.config import Settings


class DummySettings:
    real_oidc_login_enabled = False
    real_saml_login_enabled = False
    saml_acs_url = "http://localhost:8000/acs"
    saml_slo_url = ""
    saml_require_signed_assertion = True
    saml_require_signed_response = True
    saml_allow_unsigned_dev_assertion = False
    saml_disable_xxe = True
    saml_max_response_bytes = 131072
    sso_session_enabled = False
    sso_session_ttl_seconds = 3600
    sso_state_ttl_seconds = 300


class TestSAMLDefaults:
    def test_default_disabled(self):
        svc = SandboxV2SAMLFlowService(settings=DummySettings())
        assert not svc.enabled

    def test_authn_request_disabled(self):
        svc = SandboxV2SAMLFlowService(settings=DummySettings())
        r = svc.create_authn_request(None)
        assert r["status"] == "disabled"

    def test_acs_disabled(self):
        svc = SandboxV2SAMLFlowService(settings=DummySettings())
        r = svc.handle_acs(saml_response="<xml></xml>", relay_state="x")
        assert r["status"] == SandboxV2SSOFlowStatus.DISABLED


class TestSAMLSecurity:
    def test_oversize_response_rejected(self):
        s = DummySettings(); s.real_saml_login_enabled = True
        svc = SandboxV2SAMLFlowService(settings=s)
        big = "x" * 200000
        r = svc.handle_acs(saml_response=big, relay_state="x")
        assert r["status"] == "rejected"

    def test_xxe_payload_rejected(self):
        s = DummySettings(); s.real_saml_login_enabled = True
        svc = SandboxV2SAMLFlowService(settings=s)
        xxe = '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><foo>&xxe;</foo>'
        r = svc.handle_acs(saml_response=xxe, relay_state="x")
        assert r["status"] == "rejected"

    def test_unsigned_response_rejected(self):
        s = DummySettings(); s.real_saml_login_enabled = True
        s.saml_require_signed_response = True
        s.saml_allow_unsigned_dev_assertion = False
        store = SQLiteSandboxV2Store(Settings(), db_path=":memory:")
        relay = "test-relay-state-value"
        import hashlib
        relay_hash = hashlib.sha256(relay.encode()).hexdigest()
        from src.open_platform.sandbox_v2.models import SandboxV2SSOState
        from datetime import datetime, timedelta, timezone
        state = SandboxV2SSOState(state_hash=relay_hash, status="created",
                                  expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
        store.create_sso_state(state)
        svc = SandboxV2SAMLFlowService(store=store, settings=s)
        r = svc.handle_acs(saml_response="<Response></Response>", relay_state=relay)
        assert r["status"] == "rejected"

    def test_missing_relay_state(self):
        s = DummySettings(); s.real_saml_login_enabled = True
        svc = SandboxV2SAMLFlowService(settings=s)
        r = svc.handle_acs(saml_response="<Response/>", relay_state="")
        assert r["status"] == "rejected"


class TestSAMLReadiness:
    def test_readiness(self):
        svc = SandboxV2SAMLFlowService(settings=DummySettings())
        r = svc.get_saml_readiness()
        assert not r["real_saml_login_enabled"]
        assert r["saml_xxe_protection"]
