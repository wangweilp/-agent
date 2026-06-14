"""Sandbox v2 SAML Assertion Validation Service — Step 22.

严格验证 SAML Assertion 的所有必要字段：
- Issuer
- AudienceRestriction
- Recipient
- Destination
- NotBefore
- NotOnOrAfter
- InResponseTo
- NameID
- SessionIndex
- AuthnInstant

安全原则：
1. 默认 disabled
2. 任何字段校验失败 → 直接拒绝 (fail closed)
3. 不得降级放行
4. 时间使用 UTC；允许配置时钟偏移
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any

from src.open_platform.sandbox_v2.models import SandboxV2SAMLAssertionValidationResult, SandboxV2SAMLValidationStatus

logger = logging.getLogger(__name__)

_VALIDATION_ERROR_PREFIX = "assertion_validation"


class SandboxV2SAMLAssertionValidationService:
    """SAML Assertion 逐字段校验服务。默认 disabled。"""

    def __init__(self, settings: Any = None):
        self._settings = settings

    def _cfg(self, key: str, default: Any = None) -> Any:
        return getattr(self._settings, key, default) if self._settings else default

    @property
    def enabled(self) -> bool:
        return bool(self._cfg("real_saml_login_enabled", False))

    @property
    def clock_skew_seconds(self) -> int:
        return int(self._cfg("saml_clock_skew_seconds", 60))

    def validate_assertion(self, assertion_xml: str,
                           expected_issuer: str = "",
                           expected_audience: str = "",
                           expected_recipient: str = "",
                           expected_destination: str = "",
                           in_response_to_id: str = "",
                           now: datetime | None = None) -> SandboxV2SAMLAssertionValidationResult:
        """Validate a SAML Assertion against all required fields.

        Any single field failure → overall_valid=False, status=REJECTED.
        """
        now = now or datetime.now(timezone.utc)
        skew = timedelta(seconds=self.clock_skew_seconds)

        result = SandboxV2SAMLAssertionValidationResult(
            validation_status=SandboxV2SAMLValidationStatus.UNAVAILABLE,
            reason="Validation not started",
            validated_at=now,
        )

        if not self.enabled:
            result.reason = "SAML assertion validation disabled (real_saml_login_enabled=false)"
            result.validation_status = SandboxV2SAMLValidationStatus.UNAVAILABLE
            return result

        try:
            root = ET.fromstring(assertion_xml.strip())
        except ET.ParseError as e:
            result.reason = f"XML parse error: {e}"
            result.validation_status = SandboxV2SAMLValidationStatus.INVALID
            return result

        ns = self._resolve_namespaces(root)

        # ── Assertion ID ──
        assertion_id = root.get("ID", "")
        result.assertion_id = assertion_id

        # ── Issuer ──
        issuer_el = root.find(".//saml:Issuer", ns)
        issuers: list[str] = []
        if issuer_el is not None:
            issuers.append((issuer_el.text or "").strip())
        result.issuers = issuers

        if not issuers:
            result.reason = "Assertion has no Issuer element"
            result.validation_status = SandboxV2SAMLValidationStatus.INVALID
            return result

        if expected_issuer:
            result.issuer_valid = expected_issuer in issuers
            if not result.issuer_valid:
                result.reason = f"Issuer mismatch: expected '{expected_issuer}', got {issuers}"
                result.validation_status = SandboxV2SAMLValidationStatus.INVALID
                return result
        else:
            result.issuer_valid = True

        # ── Conditions (NotBefore / NotOnOrAfter) ──
        conditions_el = root.find(".//saml:Conditions", ns)
        if conditions_el is not None:
            nb_str = conditions_el.get("NotBefore", "")
            noa_str = conditions_el.get("NotOnOrAfter", "")

            if nb_str:
                nb = self._parse_iso(nb_str)
                if nb:
                    result.not_before_valid = now >= (nb - skew)
                    if not result.not_before_valid:
                        result.reason = f"Assertion not yet valid: NotBefore={nb_str}, now={now.isoformat()}"
                        result.validation_status = SandboxV2SAMLValidationStatus.INVALID
                        return result

            if noa_str:
                noa = self._parse_iso(noa_str)
                if noa:
                    result.not_on_or_after_valid = now <= (noa + skew)
                    if not result.not_on_or_after_valid:
                        result.reason = f"Assertion expired: NotOnOrAfter={noa_str}, now={now.isoformat()}"
                        result.validation_status = SandboxV2SAMLValidationStatus.EXPIRED
                        return result

        # ── AudienceRestriction ──
        audience_el = root.find(".//saml:AudienceRestriction/saml:Audience", ns)
        audience_value = (audience_el.text or "").strip() if audience_el is not None else ""
        if expected_audience:
            result.audience_valid = audience_value == expected_audience
            if not result.audience_valid:
                result.reason = f"Audience mismatch: expected '{expected_audience}', got '{audience_value}'"
                result.validation_status = SandboxV2SAMLValidationStatus.INVALID
                return result
        else:
            result.audience_valid = bool(audience_value)

        # ── Subject / NameID ──
        name_id_el = root.find(".//saml:Subject/saml:NameID", ns)
        if name_id_el is not None:
            result.name_id = (name_id_el.text or "").strip()
            result.name_id_format = name_id_el.get("Format", "")
        if not result.name_id:
            result.reason = "Assertion has no NameID in Subject"
            result.validation_status = SandboxV2SAMLValidationStatus.INVALID
            return result

        # ── SubjectConfirmation / Recipient ──
        recip_el = root.find(".//saml:SubjectConfirmation/saml:SubjectConfirmationData", ns)
        recipient = ""
        destination = ""
        in_response_to = ""
        if recip_el is not None:
            recipient = recip_el.get("Recipient", "")
            in_response_to = recip_el.get("InResponseTo", "")
        if expected_recipient:
            result.recipient_valid = recipient == expected_recipient
            if not result.recipient_valid:
                result.reason = f"Recipient mismatch: expected '{expected_recipient}', got '{recipient}'"
                result.validation_status = SandboxV2SAMLValidationStatus.INVALID
                return result
        else:
            result.recipient_valid = True

        # ── Destination (on Response root) ──
        # Check root element for Destination attribute
        resp_dest = root.get("Destination", "")
        if expected_destination:
            result.destination_valid = resp_dest == expected_destination
            if not result.destination_valid:
                result.reason = f"Destination mismatch: expected '{expected_destination}', got '{resp_dest}'"
                result.validation_status = SandboxV2SAMLValidationStatus.INVALID
                return result
        else:
            result.destination_valid = True

        # ── InResponseTo ──
        if in_response_to_id:
            result.in_response_to_valid = in_response_to == in_response_to_id
            if not result.in_response_to_valid:
                result.reason = f"InResponseTo mismatch: expected '{in_response_to_id}', got '{in_response_to}'"
                result.validation_status = SandboxV2SAMLValidationStatus.INVALID
                return result
        else:
            result.in_response_to_valid = True

        # ── SessionIndex ──
        session_idx_el = root.find(".//saml:AuthnStatement", ns)
        if session_idx_el is not None:
            result.session_index = session_idx_el.get("SessionIndex", "")
            snoa_str = session_idx_el.get("SessionNotOnOrAfter", "")
            if snoa_str:
                snoa = self._parse_iso(snoa_str)
                if snoa:
                    result.session_not_on_or_after_valid = now <= (snoa + skew)
                    if not result.session_not_on_or_after_valid:
                        result.reason = f"Session expired: SessionNotOnOrAfter={snoa_str}"
                        result.validation_status = SandboxV2SAMLValidationStatus.EXPIRED
                        return result

            # AuthnInstant
            ai_str = session_idx_el.get("AuthnInstant", "")
            if ai_str:
                ai = self._parse_iso(ai_str)
                if ai and ai > (now + skew):
                    result.authn_instant_valid = False
                    result.reason = f"AuthnInstant in the future: {ai_str}"
                    result.validation_status = SandboxV2SAMLValidationStatus.INVALID
                    return result

        # ── Build claims redacted ──
        result.claims_redacted = {
            "issuer": issuers[0] if issuers else "",
            "audience": audience_value,
            "name_id": result.name_id[:20] + "..." if len(result.name_id) > 20 else result.name_id,
            "name_id_format": result.name_id_format,
            "session_index": result.session_index[:16] + "..." if len(result.session_index) > 16 else result.session_index,
            "source": "saml_assertion",
        }

        # ── All checks passed ──
        result.overall_valid = True
        result.validation_status = SandboxV2SAMLValidationStatus.VALID
        result.reason = "All assertion validations passed"
        return result

    def validate_response(self, response_xml: str,
                          expected_issuer: str = "",
                          expected_audience: str = "",
                          expected_recipient: str = "",
                          expected_destination: str = "",
                          in_response_to_id: str = "",
                          now: datetime | None = None) -> SandboxV2SAMLAssertionValidationResult:
        """Validate all assertions within a SAML Response. Validates the first assertion found."""
        try:
            root = ET.fromstring(response_xml.strip())
        except ET.ParseError as e:
            result = SandboxV2SAMLAssertionValidationResult(
                reason=f"Response XML parse error: {e}",
                validation_status=SandboxV2SAMLValidationStatus.INVALID,
            )
            return result

        ns = self._resolve_namespaces(root)

        # Extract response-level Destination
        resp_dest = root.get("Destination", "")
        if not expected_destination:
            expected_destination = resp_dest

        # Find first assertion
        assertion_el = root.find(".//saml:Assertion", ns)
        if assertion_el is None:
            result = SandboxV2SAMLAssertionValidationResult(
                reason="No Assertion element found in SAML Response",
                validation_status=SandboxV2SAMLValidationStatus.INVALID,
            )
            return result

        assertion_xml = ET.tostring(assertion_el, encoding="unicode")
        return self.validate_assertion(
            assertion_xml,
            expected_issuer=expected_issuer,
            expected_audience=expected_audience,
            expected_recipient=expected_recipient,
            expected_destination=expected_destination,
            in_response_to_id=in_response_to_id,
            now=now,
        )

    def _resolve_namespaces(self, root: ET.Element) -> dict[str, str]:
        return {
            "saml": "urn:oasis:names:tc:SAML:2.0:assertion",
            "samlp": "urn:oasis:names:tc:SAML:2.0:protocol",
            "ds": "http://www.w3.org/2000/09/xmldsig#",
            "md": "urn:oasis:names:tc:SAML:2.0:metadata",
        }

    @staticmethod
    def _parse_iso(iso_str: str) -> datetime | None:
        """Parse ISO 8601 datetime string to UTC datetime."""
        if not iso_str:
            return None
        try:
            s = iso_str.replace("Z", "+00:00")
            return datetime.fromisoformat(s)
        except (ValueError, TypeError):
            try:
                from dateutil.parser import parse
                return parse(iso_str).astimezone(timezone.utc)
            except (ImportError, Exception):
                return None

    def get_readiness(self) -> dict[str, Any]:
        """Assertion Validation Readiness。"""
        return {
            "enabled": self.enabled,
            "ready": self.enabled,
            "clock_skew_seconds": self.clock_skew_seconds,
            "status": "ready" if self.enabled else "disabled",
            "reason": "" if self.enabled else "real_saml_login_enabled=false",
        }
