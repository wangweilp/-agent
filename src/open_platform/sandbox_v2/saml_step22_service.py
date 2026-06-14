"""Sandbox v2 SAML Step 22 Coordinator — Production-Grade SAML Validation Orchestrator.

聚合 Step 22 的各个子服务，对外暴露单一 ``SandboxV2SAMLStep22Service``：

- Metadata Import
- XML Signature Validation
- Certificate Validation + Pinning
- Assertion Field Validation
- Replay Protection
- Identity Mapping

提供 ``get_saml_validation_readiness()`` — Runtime Admin 直接消费。
与 ``oidc_step21_service.py`` 模式保持一致。
"""
from __future__ import annotations

import logging
from typing import Any

from src.open_platform.sandbox_v2.saml_metadata import SandboxV2SAMLMetadataService
from src.open_platform.sandbox_v2.saml_signature_validation import SandboxV2SAMLSignatureService
from src.open_platform.sandbox_v2.saml_certificate import SandboxV2SAMLCertificateService
from src.open_platform.sandbox_v2.saml_assertion_validation import SandboxV2SAMLAssertionValidationService
from src.open_platform.sandbox_v2.saml_replay import SandboxV2SAMLReplayService
from src.open_platform.sandbox_v2.saml_identity import SandboxV2SAMLIdentityMappingService

logger = logging.getLogger(__name__)


def _status_of(*, enabled: bool, ready: bool) -> str:
    """enabled / disabled / ready / not_ready mapping per Step 22 spec."""
    if enabled and ready:
        return "ready"
    if enabled and not ready:
        return "not_ready"
    return "disabled"


class SandboxV2SAMLStep22Service:
    """Step 22 orchestrator. Default deny, all sub-services disabled by default."""

    def __init__(
        self,
        settings: Any = None,
        store: Any = None,
        iam_service: Any = None,
        audit_service: Any = None,
    ) -> None:
        self._settings = settings
        self._store = store
        self._iam = iam_service
        self._audit = audit_service

        self.metadata = SandboxV2SAMLMetadataService(settings=settings)
        self.signature = SandboxV2SAMLSignatureService(settings=settings)
        self.certificate = SandboxV2SAMLCertificateService(settings=settings)
        self.assertion_validator = SandboxV2SAMLAssertionValidationService(settings=settings)
        self.replay = SandboxV2SAMLReplayService(settings=settings)
        self.identity = SandboxV2SAMLIdentityMappingService(
            settings=settings, iam_service=iam_service, store=store,
        )

    def _cfg(self, key: str, default: Any = None) -> Any:
        return getattr(self._settings, key, default) if self._settings else default

    # ── Validate Assertion (full pipeline) ──

    def validate_saml_assertion(self, assertion_xml: str = "",
                                saml_response_xml: str = "",
                                expected_issuer: str = "",
                                expected_audience: str = "",
                                expected_recipient: str = "",
                                expected_destination: str = "",
                                in_response_to_id: str = "",
                                expected_cert_fingerprint: str = "",
                                organization_id: str = "",
                                workspace_id: str = "") -> dict[str, Any]:
        """Full SAML assertion validation pipeline.

        Steps:
        1. Signature validation
        2. Certificate validation
        3. Assertion field validation
        4. Replay protection
        5. Identity mapping

        Any failure → fail closed → rejected.
        """
        xml_to_validate = assertion_xml or saml_response_xml
        if not xml_to_validate:
            return {
                "valid": False, "reason": "No assertion or response XML provided",
                "fail_closed": True,
            }

        # 1. Signature Validation
        sig_result = self.signature.validate_response_signature(
            xml_to_validate,
            expected_entity_id=expected_issuer,
        )

        # 2. Certificate Validation
        cert_result = None
        if self.certificate.certificate_validation_enabled:
            # Extract cert from metadata if available
            cert_pems: list[str] = []
            if expected_issuer:
                md = self.metadata.get_metadata(expected_issuer)
                if md:
                    cert_pems = md.x509_certificates

            if cert_pems:
                cert_result = self.certificate.validate_certificate(
                    cert_pems[0],
                    expected_fingerprint=expected_cert_fingerprint,
                    entity_id=expected_issuer,
                )
            else:
                cert_result = self.certificate.validate_certificate(
                    "", expected_fingerprint=expected_cert_fingerprint,
                    entity_id=expected_issuer,
                )

        # 3. Assertion Field Validation — route to correct method
        if assertion_xml and not saml_response_xml:
            # Direct assertion XML — validate it directly
            assertion_result = self.assertion_validator.validate_assertion(
                assertion_xml,
                expected_issuer=expected_issuer,
                expected_audience=expected_audience,
                expected_recipient=expected_recipient,
                expected_destination=expected_destination,
                in_response_to_id=in_response_to_id,
            )
        else:
            # Full SAML Response XML — extract and validate embedded assertion
            assertion_result = self.assertion_validator.validate_response(
                saml_response_xml or assertion_xml,
                expected_issuer=expected_issuer,
                expected_audience=expected_audience,
                expected_recipient=expected_recipient,
                expected_destination=expected_destination,
                in_response_to_id=in_response_to_id,
            )

        # 4. Replay Protection
        assertion_id = assertion_result.assertion_id
        replay_ok, replay_reason = self.replay.check_and_consume(
            assertion_id, issuer=expected_issuer, tenant_id=organization_id,
        )
        assertion_result.replay_protection_pass = replay_ok

        # 5. Signature + Certificate pass into assertion result
        assertion_result.signature_valid = sig_result.get("valid", False)
        assertion_result.certificate_valid = cert_result.is_trusted if cert_result else False

        # 6. Determine overall
        overall = (
            (sig_result.get("valid", True) or not self.signature.enabled)
            and (cert_result is None or cert_result.is_trusted or not self.certificate.certificate_validation_enabled)
            and assertion_result.overall_valid
            and replay_ok
        )

        assertion_result.overall_valid = overall
        if not overall:
            reasons: list[str] = []
            if not sig_result.get("valid", True) and self.signature.enabled:
                reasons.append(f"signature: {sig_result.get('reason', 'invalid')}")
            if cert_result and not cert_result.is_trusted and self.certificate.certificate_validation_enabled:
                reasons.append(f"certificate: {cert_result.reason}")
            if not assertion_result.overall_valid:
                reasons.append(f"assertion: {assertion_result.reason}")
            if not replay_ok:
                reasons.append(f"replay: {replay_reason}")
            assertion_result.reason = "; ".join(reasons)
            assertion_result.validation_status = "rejected"

        # 7. Identity Mapping
        identity_result = None
        if overall and self.identity.enabled:
            claims = self.identity.extract_claims_from_validation(assertion_result)
            identity_result = self.identity.map_assertion_to_identity(
                claims,
                organization_id=organization_id,
                workspace_id=workspace_id,
            )

        return {
            "valid": overall,
            "fail_closed": True,
            "signature": sig_result,
            "certificate": cert_result.to_dict() if cert_result else None,
            "assertion": assertion_result.to_dict(),
            "replay_protection": {
                "enabled": self.replay.enabled,
                "passed": replay_ok,
                "reason": replay_reason,
            },
            "identity_mapping": identity_result.to_dict() if identity_result else {
                "allowed": False, "reason": "Identity mapping skipped (validation not passed or disabled)",
            },
        }

    # ── Metadata Import ──

    def import_metadata(self, xml_content: str, source: str = "import",
                        entity_id: str = "") -> dict[str, Any]:
        """Import IdP metadata XML."""
        md = self.metadata.import_metadata_xml(xml_content, source=source, entity_id_hint=entity_id)
        if md:
            return {"status": "imported", "metadata": md.to_dict()}
        return {"status": "rejected", "reason": "Metadata import failed or is disabled"}

    def get_metadata(self, entity_id: str) -> dict[str, Any]:
        """Get cached metadata for an entityID."""
        md = self.metadata.get_metadata(entity_id)
        if md:
            return {"status": "found", "metadata": md.to_dict()}
        return {"status": "not_found", "reason": f"No metadata for entityID={entity_id}"}

    # ── Certificate Management ──

    def pin_certificate(self, fingerprint: str, entity_id: str = "") -> dict[str, Any]:
        ok = self.certificate.pin_certificate(fingerprint, entity_id)
        return {"pinned": ok, "fingerprint": fingerprint, "entity_id": entity_id}

    def list_pinned_certificates(self) -> dict[str, Any]:
        return {"pins": self.certificate.list_pins()}

    # ── Replay Store Management ──

    def get_replay_store_info(self) -> dict[str, Any]:
        return {
            "store_type": type(self.replay._store).__name__,
            "size": self.replay.store_size(),
            "enabled": self.replay.enabled,
        }

    def clear_replay_store(self) -> dict[str, Any]:
        count = self.replay.clear_expired()
        return {"cleared": count, "remaining": self.replay.store_size()}

    # ── Readiness ──

    def get_saml_validation_readiness(self) -> dict[str, Any]:
        """SAML Validation Readiness — Runtime Admin 直接消费。

        所有子能力默认 disabled。每项包含 enabled / ready / status / reason。
        """
        md_r = self.metadata.get_readiness()
        sig_r = self.signature.get_readiness()
        cert_r = self.certificate.get_readiness()
        assertion_r = self.assertion_validator.get_readiness()
        replay_r = self.replay.get_readiness()
        identity_r = self.identity.get_readiness()

        return {
            "step": "step22_saml_production_validation",
            "available": True,
            "fail_closed": True,
            "metadata_import": {
                "enabled": md_r["enabled"],
                "ready": md_r["ready"],
                "status": md_r["status"],
                "reason": md_r["reason"],
                "cached_entities": md_r.get("cached_entities", 0),
            },
            "signature_validation": {
                "enabled": sig_r["enabled"],
                "ready": sig_r["ready"],
                "status": sig_r["status"],
                "reason": sig_r["reason"],
                "signature_engine": sig_r["signature_engine"],
                "engine_available": sig_r["engine_available"],
            },
            "certificate_validation": {
                "enabled": cert_r["enabled"],
                "ready": cert_r["ready"],
                "status": cert_r["status"],
                "reason": cert_r["reason"],
                "pinned_certs": cert_r.get("pinned_certs", 0),
            },
            "certificate_pinning": {
                "enabled": cert_r["pinning_enabled"],
                "ready": cert_r["pinning_enabled"] and cert_r.get("pinned_certs", 0) > 0,
                "status": _status_of(enabled=cert_r["pinning_enabled"],
                                     ready=cert_r["pinning_enabled"] and cert_r.get("pinned_certs", 0) > 0),
                "reason": "" if cert_r["pinning_enabled"] else "SAML_CERTIFICATE_PINNING_ENABLED=false",
            },
            "replay_protection": {
                "enabled": replay_r["enabled"],
                "ready": replay_r["ready"],
                "status": replay_r["status"],
                "reason": replay_r["reason"],
                "store_type": replay_r.get("store_type", "MemoryReplayStore"),
                "store_size": replay_r.get("store_size", 0),
            },
            "identity_mapping": {
                "enabled": identity_r["enabled"],
                "ready": identity_r["ready"],
                "status": identity_r["status"],
                "reason": identity_r["reason"],
                "mapper_type": identity_r.get("mapper_type", ""),
            },
        }
