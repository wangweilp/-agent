"""Step 22 — SAML Validation Security Tests (11 scenarios).

覆盖:
 1. invalid issuer
 2. invalid audience
 3. invalid recipient
 4. expired assertion
 5. future not_before
 6. replay assertion
 7. unknown certificate
 8. wrong fingerprint
 9. invalid signature
10. missing required fields
11. disabled validation mode
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from datetime import datetime, timedelta, timezone

from src.open_platform.sandbox_v2.saml_step22_service import SandboxV2SAMLStep22Service
from src.open_platform.sandbox_v2.saml_metadata import SandboxV2SAMLMetadataService
from src.open_platform.sandbox_v2.saml_certificate import SandboxV2SAMLCertificateService
from src.open_platform.sandbox_v2.saml_assertion_validation import SandboxV2SAMLAssertionValidationService
from src.open_platform.sandbox_v2.saml_replay import SandboxV2SAMLReplayService, SandboxV2MemoryReplayStore
from src.open_platform.sandbox_v2.saml_signature_validation import SandboxV2SAMLSignatureService
from src.open_platform.sandbox_v2.saml_identity import SandboxV2SAMLIdentityMappingService
from tests.test_open_platform.saml_step22_fixtures import (
    Step22Settings,
    generate_test_certificate,
    build_valid_assertion_xml,
    build_valid_response_xml,
    build_idp_metadata_xml,
)


class _Step22EnabledSettings(Step22Settings):
    """Settings with SAML validation enabled."""
    real_saml_login_enabled = True
    saml_metadata_import_enabled = True
    saml_signature_validation_enabled = True
    saml_certificate_validation_enabled = True
    saml_certificate_pinning_enabled = False
    saml_assertion_replay_protection_enabled = True
    saml_identity_mapping_enabled = False
    saml_allow_stub_signature_engine = True


ISSUER = "https://idp.example.com"
AUDIENCE = "sandbox-v2"
RECIPIENT = "http://localhost:8000/api/runtime/sandbox-v2/iam/saml/acs"
DESTINATION = "http://localhost:8000/api/runtime/sandbox-v2/iam/saml/acs"


def _make_services():
    settings = _Step22EnabledSettings()
    return SandboxV2SAMLStep22Service(settings=settings)


# ═══════════════════════════════════════════
# 1. Invalid Issuer
# ═══════════════════════════════════════════

class TestInvalidIssuer:
    def test_invalid_issuer_rejected(self):
        svc = _make_services()
        assertion = build_valid_assertion_xml(issuer="https://real-idp.example.com")
        result = svc.validate_saml_assertion(
            assertion_xml=assertion,
            expected_issuer="https://fake-idp.example.com",
            expected_audience=AUDIENCE,
            expected_recipient=RECIPIENT,
        )
        assert result["valid"] is False
        assert "issuer" in result.get("assertion", {}).get("reason", "").lower() or \
               result.get("assertion", {}).get("issuer_valid") is False

    def test_matching_issuer_accepted(self):
        svc = _make_services()
        assertion = build_valid_assertion_xml(issuer=ISSUER)
        result = svc.validate_saml_assertion(
            assertion_xml=assertion,
            expected_issuer=ISSUER,
            expected_audience=AUDIENCE,
            expected_recipient=RECIPIENT,
        )
        assert result["assertion"]["issuer_valid"] is True


# ═══════════════════════════════════════════
# 2. Invalid Audience
# ═══════════════════════════════════════════

class TestInvalidAudience:
    def test_invalid_audience_rejected(self):
        svc = _make_services()
        assertion = build_valid_assertion_xml(audience="correct-audience")
        result = svc.validate_saml_assertion(
            assertion_xml=assertion,
            expected_issuer=ISSUER,
            expected_audience="wrong-audience",
            expected_recipient=RECIPIENT,
        )
        assert result["valid"] is False
        assert result["assertion"]["audience_valid"] is False


# ═══════════════════════════════════════════
# 3. Invalid Recipient
# ═══════════════════════════════════════════

class TestInvalidRecipient:
    def test_invalid_recipient_rejected(self):
        svc = _make_services()
        assertion = build_valid_assertion_xml(recipient="https://correct/acs")
        result = svc.validate_saml_assertion(
            assertion_xml=assertion,
            expected_issuer=ISSUER,
            expected_audience=AUDIENCE,
            expected_recipient="https://wrong/acs",
        )
        assert result["valid"] is False
        assert result["assertion"]["recipient_valid"] is False


# ═══════════════════════════════════════════
# 4. Expired Assertion
# ═══════════════════════════════════════════

class TestExpiredAssertion:
    def test_expired_assertion_rejected(self):
        svc = _make_services()
        # NotOnOrAfter is in the past
        assertion = build_valid_assertion_xml(
            not_on_or_after_offset_minutes=-10, not_before_offset_minutes=-15,
        )
        result = svc.validate_saml_assertion(
            assertion_xml=assertion,
            expected_issuer=ISSUER,
            expected_audience=AUDIENCE,
            expected_recipient=RECIPIENT,
        )
        assert result["valid"] is False
        assert not result["assertion"]["not_on_or_after_valid"]


# ═══════════════════════════════════════════
# 5. Future NotBefore
# ═══════════════════════════════════════════

class TestFutureNotBefore:
    def test_future_not_before_rejected(self):
        svc = _make_services()
        # NotBefore is in the future
        assertion = build_valid_assertion_xml(
            not_before_offset_minutes=30, not_on_or_after_offset_minutes=60,
        )
        result = svc.validate_saml_assertion(
            assertion_xml=assertion,
            expected_issuer=ISSUER,
            expected_audience=AUDIENCE,
            expected_recipient=RECIPIENT,
        )
        assert result["valid"] is False
        assert not result["assertion"]["not_before_valid"]


# ═══════════════════════════════════════════
# 6. Replay Assertion
# ═══════════════════════════════════════════

class TestReplayAssertion:
    def test_replay_assertion_rejected(self):
        svc = _make_services()
        assertion = build_valid_assertion_xml(assertion_id="_replay_test_1")
        # First use — should pass
        r1 = svc.validate_saml_assertion(
            assertion_xml=assertion,
            expected_issuer=ISSUER,
            expected_audience=AUDIENCE,
            expected_recipient=RECIPIENT,
        )
        assert r1.get("replay_protection", {}).get("passed") is True

        # Second use — should fail (replay)
        r2 = svc.validate_saml_assertion(
            assertion_xml=assertion,
            expected_issuer=ISSUER,
            expected_audience=AUDIENCE,
            expected_recipient=RECIPIENT,
        )
        assert r2.get("replay_protection", {}).get("passed") is False
        assert r2["valid"] is False


# ═══════════════════════════════════════════
# 7. Unknown Certificate
# ═══════════════════════════════════════════

class TestUnknownCertificate:
    def test_unknown_certificate_rejected(self):
        svc = _make_services()
        # Enable pinning
        svc.certificate._settings.saml_certificate_pinning_enabled = True
        cert_pem, fp = generate_test_certificate()
        # Don't pin this cert — it should be rejected
        result = svc.certificate.validate_certificate(cert_pem, entity_id=ISSUER)
        assert result.is_trusted is False
        assert "not found in pinning store" in result.reason.lower()


# ═══════════════════════════════════════════
# 8. Wrong Fingerprint
# ═══════════════════════════════════════════

class TestWrongFingerprint:
    def test_wrong_fingerprint_rejected(self):
        svc = _make_services()
        cert_pem, correct_fp = generate_test_certificate()
        wrong_fp = "0" * 64  # intentionally wrong
        result = svc.certificate.validate_certificate(
            cert_pem, expected_fingerprint=wrong_fp, entity_id=ISSUER,
        )
        assert result.is_trusted is False


# ═══════════════════════════════════════════
# 9. Invalid Signature
# ═══════════════════════════════════════════

class TestInvalidSignature:
    def test_unsigned_assertion_detected(self):
        settings = _Step22EnabledSettings()
        sig = SandboxV2SAMLSignatureService(settings=settings)
        assertion = build_valid_assertion_xml(include_signature=False)
        result = sig.validate_response_signature(assertion)
        assert result["valid"] is False
        assert "no xml signature element" in result.get("reason", "").lower() or \
               not result.get("details", {}).get("has_signature_element", True)

    def test_signed_assertion_stub_accepts_structure(self):
        settings = _Step22EnabledSettings()
        settings.saml_allow_stub_signature_engine = True
        sig = SandboxV2SAMLSignatureService(settings=settings)
        assertion = build_valid_assertion_xml(include_signature=True)
        result = sig.validate_response_signature(assertion)
        # Stub validates structure, not crypto
        assert result["engine"] == "stub"


# ═══════════════════════════════════════════
# 10. Missing Required Fields
# ═══════════════════════════════════════════

class TestMissingRequiredFields:
    def test_missing_name_id_rejected(self):
        # Test the assertion validator directly — bypass signature to isolate NameID check
        settings = _Step22EnabledSettings()
        validator = SandboxV2SAMLAssertionValidationService(settings=settings)
        assertion = build_valid_assertion_xml(name_id="", include_signature=False)
        result = validator.validate_assertion(
            assertion,
            expected_issuer=ISSUER,
            expected_audience=AUDIENCE,
        )
        assert result.overall_valid is False
        assert "nameid" in result.reason.lower()

    def test_missing_issuer_rejected(self):
        svc = _make_services()
        assertion = build_valid_assertion_xml(issuer="")
        result = svc.validate_saml_assertion(
            assertion_xml=assertion,
            expected_issuer=ISSUER,
            expected_audience=AUDIENCE,
        )
        assert result["valid"] is False


# ═══════════════════════════════════════════
# 11. Disabled Validation Mode
# ═══════════════════════════════════════════

class TestDisabledValidationMode:
    def test_disabled_validation_returns_unavailable(self):
        settings = Step22Settings()  # all disabled
        sig = SandboxV2SAMLSignatureService(settings=settings)
        result = sig.validate_response_signature("<Response/>")
        assert result["valid"] is False
        assert "disabled" in result.get("reason", "").lower()

    def test_disabled_metadata_import_returns_none(self):
        settings = Step22Settings()
        md_svc = SandboxV2SAMLMetadataService(settings=settings)
        result = md_svc.import_metadata_xml("<xml/>")
        assert result is None

    def test_disabled_replay_allows_all(self):
        settings = Step22Settings()
        replay = SandboxV2SAMLReplayService(settings=settings)
        ok, reason = replay.check_and_consume("_any_id_")
        assert ok is True  # replay protection disabled → all accepted

    def test_disabled_cert_validation_returns_untrusted(self):
        settings = Step22Settings()
        cert_svc = SandboxV2SAMLCertificateService(settings=settings)
        result = cert_svc.validate_certificate("fake-cert")
        assert result.is_trusted is False
        assert "disabled" in result.reason.lower()


# ═══════════════════════════════════════════
# Readiness
# ═══════════════════════════════════════════

class TestSAMLReadiness:
    def test_all_disabled_readiness(self):
        settings = Step22Settings()
        svc = SandboxV2SAMLStep22Service(settings=settings)
        r = svc.get_saml_validation_readiness()
        assert r["fail_closed"] is True
        assert r["metadata_import"]["enabled"] is False
        assert r["signature_validation"]["enabled"] is False
        assert r["certificate_validation"]["enabled"] is False
        assert r["replay_protection"]["enabled"] is False
        assert r["identity_mapping"]["enabled"] is False

    def test_enabled_some_readiness(self):
        settings = _Step22EnabledSettings()
        svc = SandboxV2SAMLStep22Service(settings=settings)
        r = svc.get_saml_validation_readiness()
        assert r["fail_closed"] is True
        assert r["metadata_import"]["enabled"] is True
        assert r["signature_validation"]["enabled"] is True
        assert r["certificate_validation"]["enabled"] is True
        assert r["replay_protection"]["enabled"] is True
