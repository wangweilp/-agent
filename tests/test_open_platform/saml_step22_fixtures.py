"""Step 22 SAML test fixtures — SAML assertion/response generators.

Reusable helpers for both Security Tests (11) and Red-Team Tests (9).
"""
from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any


def _xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Step22Settings:
    """Minimal settings fixture for Step 22 SAML tests."""
    real_saml_login_enabled = False
    saml_metadata_import_enabled = False
    saml_signature_validation_enabled = False
    saml_certificate_validation_enabled = False
    saml_certificate_pinning_enabled = False
    saml_assertion_replay_protection_enabled = False
    saml_identity_mapping_enabled = False
    saml_metadata_cache_ttl_seconds = 3600
    saml_replay_store_ttl_seconds = 3600
    saml_clock_skew_seconds = 60
    saml_max_response_bytes = 131072
    saml_require_signed_response = True
    saml_require_signed_assertion = True
    saml_allow_unsigned_dev_assertion = False
    saml_disable_xxe = True
    saml_allow_stub_signature_engine = False


# ── Certificate Fixtures ──

def generate_test_certificate() -> tuple[str, str]:
    """Generate a test X.509 certificate. Returns (pem, sha256_fingerprint)."""
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-idp.example.com")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    pem = cert.public_bytes(serialization.Encoding.PEM).decode("ascii")
    der = cert.public_bytes(serialization.Encoding.DER)
    fp = hashlib.sha256(der).hexdigest()
    return pem, fp


# ── SAML XML Generators ──

def build_valid_assertion_xml(
    issuer: str = "https://idp.example.com",
    audience: str = "sandbox-v2",
    recipient: str = "http://localhost:8000/api/runtime/sandbox-v2/iam/saml/acs",
    destination: str = "http://localhost:8000/api/runtime/sandbox-v2/iam/saml/acs",
    name_id: str = "user@example.com",
    in_response_to: str = "",
    not_before_offset_minutes: int = -5,
    not_on_or_after_offset_minutes: int = 5,
    assertion_id: str = "",
    session_index: str = "",
    include_signature: bool = True,
    cert_pem: str = "",
) -> str:
    """Build a valid SAML Assertion XML."""
    now = datetime.now(timezone.utc)
    nb = (now + timedelta(minutes=not_before_offset_minutes)).isoformat()
    noa = (now + timedelta(minutes=not_on_or_after_offset_minutes)).isoformat()
    aid = assertion_id or f"_assertion_{secrets.token_hex(12)}"
    sid = session_index or f"_session_{secrets.token_hex(12)}"

    sig_block = ""
    if include_signature:
        sig_block = f"""
  <ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
    <ds:SignedInfo>
      <ds:CanonicalizationMethod Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"/>
      <ds:SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/>
      <ds:Reference URI="#{aid}">
        <ds:Transforms>
          <ds:Transform Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"/>
          <ds:Transform Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"/>
        </ds:Transforms>
        <ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
        <ds:DigestValue>dGVzdGRpZ2VzdHZhbHVlZm9yYXNzZXJ0aW9uc2lnbmF0dXJl</ds:DigestValue>
      </ds:Reference>
    </ds:SignedInfo>
    <ds:SignatureValue>dGVzdHNpZ25hdHVyZXZhbHVlZm9yYXNzZXJ0aW9u</ds:SignatureValue>
  </ds:Signature>"""

    assertion = f"""<?xml version="1.0" encoding="UTF-8"?>
<saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
                xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
                ID="{aid}"
                Version="2.0"
                IssueInstant="{now.isoformat()}">
  <saml:Issuer>{_xml_escape(issuer)}</saml:Issuer>
  {sig_block if include_signature else ""}
  <saml:Subject>
    <saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress">{_xml_escape(name_id)}</saml:NameID>
    <saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
      <saml:SubjectConfirmationData Recipient="{_xml_escape(recipient)}"
        NotOnOrAfter="{noa}"
        InResponseTo="{_xml_escape(in_response_to)}"/>
    </saml:SubjectConfirmation>
  </saml:Subject>
  <saml:Conditions NotBefore="{nb}" NotOnOrAfter="{noa}">
    <saml:AudienceRestriction>
      <saml:Audience>{_xml_escape(audience)}</saml:Audience>
    </saml:AudienceRestriction>
  </saml:Conditions>
  <saml:AuthnStatement AuthnInstant="{now.isoformat()}" SessionIndex="{sid}">
    <saml:AuthnContext>
      <saml:AuthnContextClassRef>urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport</saml:AuthnContextClassRef>
    </saml:AuthnContext>
  </saml:AuthnStatement>
  <saml:AttributeStatement>
    <saml:Attribute Name="email">
      <saml:AttributeValue>{_xml_escape(name_id)}</saml:AttributeValue>
    </saml:Attribute>
  </saml:AttributeStatement>
</saml:Assertion>"""
    return assertion


def build_valid_response_xml(
    issuer: str = "https://idp.example.com",
    audience: str = "sandbox-v2",
    recipient: str = "http://localhost:8000/api/runtime/sandbox-v2/iam/saml/acs",
    destination: str = "http://localhost:8000/api/runtime/sandbox-v2/iam/saml/acs",
    name_id: str = "user@example.com",
    in_response_to: str = "",
    assertion_id: str = "",
) -> str:
    """Build a valid SAML Response XML with an embedded Assertion."""
    now = datetime.now(timezone.utc)
    response_id = f"_response_{secrets.token_hex(12)}"
    aid = assertion_id or f"_assertion_{secrets.token_hex(12)}"

    assertion = build_valid_assertion_xml(
        issuer=issuer, audience=audience, recipient=recipient,
        destination=destination, name_id=name_id,
        in_response_to=in_response_to, assertion_id=aid,
    )

    response = f"""<?xml version="1.0" encoding="UTF-8"?>
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
                xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
                ID="{response_id}"
                Version="2.0"
                IssueInstant="{now.isoformat()}"
                Destination="{_xml_escape(destination)}"
                InResponseTo="{_xml_escape(in_response_to)}">
  <saml:Issuer>{_xml_escape(issuer)}</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>
  {assertion.replace('<?xml version="1.0" encoding="UTF-8"?>', '')}
</samlp:Response>"""
    return response


def build_idp_metadata_xml(
    entity_id: str = "https://idp.example.com",
    sso_url: str = "https://idp.example.com/sso",
    cert_pem: str = "",
) -> str:
    """Build IdP metadata XML."""
    now = datetime.now(timezone.utc)
    cert_b64 = ""
    if cert_pem:
        cert_b64 = cert_pem.replace("-----BEGIN CERTIFICATE-----", "") \
                           .replace("-----END CERTIFICATE-----", "") \
                           .replace("\n", "").replace("\r", "").strip()

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
                     entityID="{_xml_escape(entity_id)}">
  <md:IDPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
                       WantAuthnRequestsSigned="false">
    <md:KeyDescriptor use="signing">
      <ds:KeyInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
        <ds:X509Data>
          <ds:X509Certificate>{cert_b64}</ds:X509Certificate>
        </ds:X509Data>
      </ds:KeyInfo>
    </md:KeyDescriptor>
    <md:SingleSignOnService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
                            Location="{_xml_escape(sso_url)}"/>
    <md:SingleSignOnService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
                            Location="{_xml_escape(sso_url)}"/>
    <md:NameIDFormat>urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress</md:NameIDFormat>
    <md:NameIDFormat>urn:oasis:names:tc:SAML:2.0:nameid-format:persistent</md:NameIDFormat>
  </md:IDPSSODescriptor>
  <md:Organization>
    <md:OrganizationName xml:lang="en">Test IdP</md:OrganizationName>
    <md:OrganizationDisplayName xml:lang="en">Test Identity Provider</md:OrganizationDisplayName>
  </md:Organization>
</md:EntityDescriptor>"""
