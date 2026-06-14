"""Step 22 — SAML Red-Team Tests (9 attack scenarios).

攻击场景验证 — 全部必须拒绝:
 1. unsigned assertion
 2. unsigned response
 3. fake issuer
 4. fake audience
 5. metadata spoof
 6. replay assertion
 7. expired assertion
 8. forged certificate
 9. wrong fingerprint

All must fail closed.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from datetime import datetime, timedelta, timezone

from src.open_platform.sandbox_v2.saml_step22_service import SandboxV2SAMLStep22Service
from src.open_platform.sandbox_v2.saml_signature_validation import SandboxV2SAMLSignatureService
from src.open_platform.sandbox_v2.saml_assertion_validation import SandboxV2SAMLAssertionValidationService
from src.open_platform.sandbox_v2.saml_certificate import SandboxV2SAMLCertificateService
from src.open_platform.sandbox_v2.saml_metadata import SandboxV2SAMLMetadataService
from src.open_platform.sandbox_v2.saml_replay import SandboxV2SAMLReplayService, SandboxV2MemoryReplayStore
from tests.test_open_platform.saml_step22_fixtures import (
    Step22Settings,
    generate_test_certificate,
    build_valid_assertion_xml,
    build_valid_response_xml,
    build_idp_metadata_xml,
)


class _RedTeamSettings(Step22Settings):
    """Settings with all SAML validation enabled for red-team."""
    real_saml_login_enabled = True
    saml_metadata_import_enabled = True
    saml_signature_validation_enabled = True
    saml_certificate_validation_enabled = True
    saml_certificate_pinning_enabled = True
    saml_assertion_replay_protection_enabled = True
    saml_identity_mapping_enabled = True
    saml_allow_stub_signature_engine = True


ISSUER = "https://idp.example.com"
AUDIENCE = "sandbox-v2"
RECIPIENT = "http://localhost:8000/api/runtime/sandbox-v2/iam/saml/acs"


def _make_svc():
    settings = _RedTeamSettings()
    return SandboxV2SAMLStep22Service(settings=settings)


# ═══════════════════════════════════════════
# Red-Team 1: Unsigned Assertion
# ═══════════════════════════════════════════

class TestRedTeamUnsignedAssertion:
    def test_unsigned_assertion_rejected(self):
        """Unsigned assertion MUST be rejected."""
        svc = _make_svc()
        assertion = build_valid_assertion_xml(include_signature=False)
        result = svc.validate_saml_assertion(
            assertion_xml=assertion,
            expected_issuer=ISSUER,
            expected_audience=AUDIENCE,
            expected_recipient=RECIPIENT,
        )
        # Without signature element, stub engine rejects
        assert result["valid"] is False, f"Unsigned assertion should be rejected, got: {result}"


# ═══════════════════════════════════════════
# Red-Team 2: Unsigned Response
# ═══════════════════════════════════════════

class TestRedTeamUnsignedResponse:
    def test_unsigned_response_rejected(self):
        """Unsigned SAML Response MUST be rejected (no Signature)."""
        settings = _RedTeamSettings()
        sig = SandboxV2SAMLSignatureService(settings=settings)
        # Build response without signature — the response itself must be signed
        unsigned = """<?xml version="1.0"?>
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    Destination="http://localhost/acs" ID="_resp1" Version="2.0"
    IssueInstant="2024-01-01T00:00:00Z">
  <saml:Issuer xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">https://idp.example.com</saml:Issuer>
  <samlp:Status><samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/></samlp:Status>
</samlp:Response>"""
        result = sig.validate_response_signature(unsigned)
        assert result["valid"] is False, f"Unsigned response should be rejected: {result}"


# ═══════════════════════════════════════════
# Red-Team 3: Fake Issuer
# ═══════════════════════════════════════════

class TestRedTeamFakeIssuer:
    def test_fake_issuer_rejected(self):
        """Assertion from a fake/unknown issuer MUST be rejected."""
        svc = _make_svc()
        assertion = build_valid_assertion_xml(issuer="https://evil-idp.phishing.com")
        result = svc.validate_saml_assertion(
            assertion_xml=assertion,
            expected_issuer=ISSUER,  # real IdP
            expected_audience=AUDIENCE,
            expected_recipient=RECIPIENT,
        )
        assert result["valid"] is False, f"Fake issuer should be rejected: {result}"
        assert result["assertion"]["issuer_valid"] is False

    def test_issuer_spoof_with_similar_name_rejected(self):
        """Issuer spoofing with a visually similar domain MUST be rejected."""
        svc = _make_svc()
        # Use a similar-looking issuer
        assertion = build_valid_assertion_xml(issuer="https://idp.examp1e.com")  # '1' instead of 'l'
        result = svc.validate_saml_assertion(
            assertion_xml=assertion,
            expected_issuer=ISSUER,
            expected_audience=AUDIENCE,
            expected_recipient=RECIPIENT,
        )
        assert result["valid"] is False


# ═══════════════════════════════════════════
# Red-Team 4: Fake Audience
# ═══════════════════════════════════════════

class TestRedTeamFakeAudience:
    def test_fake_audience_rejected(self):
        """Assertion targeting a different SP MUST be rejected."""
        svc = _make_svc()
        assertion = build_valid_assertion_xml(audience="other-sp-client")
        result = svc.validate_saml_assertion(
            assertion_xml=assertion,
            expected_issuer=ISSUER,
            expected_audience=AUDIENCE,  # our SP
            expected_recipient=RECIPIENT,
        )
        assert result["valid"] is False, f"Fake audience should be rejected: {result}"
        assert result["assertion"]["audience_valid"] is False


# ═══════════════════════════════════════════
# Red-Team 5: Metadata Spoof
# ═══════════════════════════════════════════

class TestRedTeamMetadataSpoof:
    def test_metadata_spoof_detected(self):
        """Metadata from a different entityID should not affect validation of another."""
        settings = _RedTeamSettings()
        md_svc = SandboxV2SAMLMetadataService(settings=settings)

        # Import real metadata
        real_xml = build_idp_metadata_xml(entity_id=ISSUER)
        real_md = md_svc.import_metadata_xml(real_xml, source="import")
        assert real_md is not None

        # A spoofed metadata with different entityID should be stored separately
        spoof_xml = build_idp_metadata_xml(entity_id="https://evil-idp.example.com")
        spoof_md = md_svc.import_metadata_xml(spoof_xml, source="import")
        assert spoof_md is not None

        # Getting metadata for real entityID should NOT return spoofed metadata
        fetched = md_svc.get_metadata(ISSUER)
        assert fetched is not None
        assert fetched.entity_id == ISSUER
        assert fetched.entity_id != "https://evil-idp.example.com"

    def test_cross_entity_cert_isolation(self):
        """Certificate from one entityID should not validate for another entityID."""
        settings = _RedTeamSettings()
        md_svc = SandboxV2SAMLMetadataService(settings=settings)

        cert_pem, _ = generate_test_certificate()
        # Real IdP metadata with its cert
        real_md_xml = build_idp_metadata_xml(entity_id=ISSUER, cert_pem=cert_pem)
        md_svc.import_metadata_xml(real_md_xml, source="import")

        # Different entityID with a different cert
        evil_cert_pem, _ = generate_test_certificate()
        evil_md_xml = build_idp_metadata_xml(entity_id="https://evil.example.com", cert_pem=evil_cert_pem)
        md_svc.import_metadata_xml(evil_md_xml, source="import")

        # Real entityID should have its cert, not the evil one
        real_md = md_svc.get_metadata(ISSUER)
        evil_md = md_svc.get_metadata("https://evil.example.com")
        assert real_md is not None and evil_md is not None
        # The certificates should be different
        assert real_md.certificate_fingerprints != evil_md.certificate_fingerprints


# ═══════════════════════════════════════════
# Red-Team 6: Replay Assertion
# ═══════════════════════════════════════════

class TestRedTeamReplayAssertion:
    def test_replay_assertion_rejected(self):
        """Replayed assertion MUST be rejected (one-time use)."""
        svc = _make_svc()
        assertion = build_valid_assertion_xml(assertion_id="_rt_replay_test")

        # First consumption — allowed
        r1 = svc.validate_saml_assertion(
            assertion_xml=assertion,
            expected_issuer=ISSUER,
            expected_audience=AUDIENCE,
            expected_recipient=RECIPIENT,
        )
        assert r1.get("replay_protection", {}).get("passed") is True

        # Second consumption — MUST be rejected
        r2 = svc.validate_saml_assertion(
            assertion_xml=assertion,
            expected_issuer=ISSUER,
            expected_audience=AUDIENCE,
            expected_recipient=RECIPIENT,
        )
        assert r2.get("replay_protection", {}).get("passed") is False
        assert r2["valid"] is False, f"Replay assertion must be rejected: {r2}"

    def test_replay_different_assertion_accepted(self):
        """Different assertion IDs should each be accepted once."""
        svc = _make_svc()
        a1 = build_valid_assertion_xml(assertion_id="_rt_replay_a")
        a2 = build_valid_assertion_xml(assertion_id="_rt_replay_b")

        r1 = svc.validate_saml_assertion(
            assertion_xml=a1, expected_issuer=ISSUER,
            expected_audience=AUDIENCE, expected_recipient=RECIPIENT,
        )
        r2 = svc.validate_saml_assertion(
            assertion_xml=a2, expected_issuer=ISSUER,
            expected_audience=AUDIENCE, expected_recipient=RECIPIENT,
        )
        assert r1.get("replay_protection", {}).get("passed") is True
        assert r2.get("replay_protection", {}).get("passed") is True


# ═══════════════════════════════════════════
# Red-Team 7: Expired Assertion
# ═══════════════════════════════════════════

class TestRedTeamExpiredAssertion:
    def test_expired_assertion_rejected(self):
        """An assertion past its NotOnOrAfter MUST be rejected even with valid signature."""
        svc = _make_svc()
        # NotOnOrAfter is 60 minutes in the past
        assertion = build_valid_assertion_xml(
            not_on_or_after_offset_minutes=-60,
            not_before_offset_minutes=-90,
        )
        result = svc.validate_saml_assertion(
            assertion_xml=assertion,
            expected_issuer=ISSUER,
            expected_audience=AUDIENCE,
            expected_recipient=RECIPIENT,
        )
        assert result["valid"] is False, f"Expired assertion should be rejected: {result}"
        assert not result["assertion"]["not_on_or_after_valid"]

    def test_barely_expired_assertion_rejected(self):
        """Assertion expired by 1 second MUST still be rejected (no leniency)."""
        settings = _RedTeamSettings()
        settings.saml_clock_skew_seconds = 0  # zero tolerance
        validator = SandboxV2SAMLAssertionValidationService(settings=settings)
        assertion = build_valid_assertion_xml(not_on_or_after_offset_minutes=-1)
        result = validator.validate_assertion(
            assertion, expected_issuer=ISSUER,
            expected_audience=AUDIENCE, expected_recipient=RECIPIENT,
        )
        # With zero skew, even 1 second expired → invalid
        assert result.overall_valid is False or not result.not_on_or_after_valid


# ═══════════════════════════════════════════
# Red-Team 8: Forged Certificate
# ═══════════════════════════════════════════

class TestRedTeamForgedCertificate:
    def test_forged_certificate_rejected(self):
        """A certificate that is not pinned MUST be rejected."""
        settings = _RedTeamSettings()
        cert_svc = SandboxV2SAMLCertificateService(settings=settings)

        cert_pem, fp = generate_test_certificate()
        # Do not pin this cert — it should be rejected
        result = cert_svc.validate_certificate(cert_pem, entity_id=ISSUER)
        assert result.is_trusted is False, f"Unpinned certificate should be rejected: {result}"

    def test_wrong_cert_for_entity_rejected(self):
        """Cross-entity cert: cert not in pinning store must be rejected even if entity-id matches."""
        settings = _RedTeamSettings()
        cert_svc = SandboxV2SAMLCertificateService(settings=settings)

        cert_a, fp_a = generate_test_certificate()
        cert_b, fp_b = generate_test_certificate()

        # Only pin cert_b to entity-b. cert_a is NOT pinned at all.
        cert_svc.pin_certificate(fp_b, entity_id="entity-b")

        # Validate unpinned cert_a against expected_fingerprint=fp_b (entity-b's cert)
        # cert_a's actual fingerprint (fp_a) does NOT match expected (fp_b) AND is NOT pinned
        result = cert_svc.validate_certificate(cert_a, expected_fingerprint=fp_b, entity_id="entity-b")
        assert result.is_trusted is False, f"Unpinned cert with mismatched expected fingerprint should be rejected: {result}"


# ═══════════════════════════════════════════
# Red-Team 9: Wrong Fingerprint
# ═══════════════════════════════════════════

class TestRedTeamWrongFingerprint:
    def test_wrong_fingerprint_rejected(self):
        """Certificate with mismatched fingerprint MUST be rejected."""
        settings = _RedTeamSettings()
        cert_svc = SandboxV2SAMLCertificateService(settings=settings)

        cert_pem, real_fp = generate_test_certificate()
        wrong_fp = "deadbeef" * 8  # intentionally wrong

        result = cert_svc.validate_certificate(
            cert_pem, expected_fingerprint=wrong_fp, entity_id=ISSUER,
        )
        assert result.is_trusted is False, f"Wrong fingerprint should be rejected: {result}"
        # With pinning enabled and wrong fingerprint, cert is rejected as unknown
        assert not result.is_trusted

    def test_zero_length_fingerprint_rejected(self):
        """Empty fingerprint should be rejected."""
        settings = _RedTeamSettings()
        cert_svc = SandboxV2SAMLCertificateService(settings=settings)
        cert_pem, _ = generate_test_certificate()
        result = cert_svc.validate_certificate(cert_pem, expected_fingerprint="", entity_id=ISSUER)
        # With pinning enabled and no fingerprint match, should reject
        assert result.is_trusted is False


# ═══════════════════════════════════════════
# Fail-Closed Verification
# ═══════════════════════════════════════════

class TestRedTeamFailClosed:
    def test_all_disabled_fail_closed(self):
        """With everything disabled, the service must fail closed."""
        settings = Step22Settings()
        svc = SandboxV2SAMLStep22Service(settings=settings)
        r = svc.get_saml_validation_readiness()
        assert r["fail_closed"] is True
        # All sub-services disabled
        for key in ["metadata_import", "signature_validation",
                     "certificate_validation", "replay_protection", "identity_mapping"]:
            assert r[key]["enabled"] is False, f"{key} should be disabled by default"
            assert r[key]["status"] == "disabled", f"{key} should show disabled"
