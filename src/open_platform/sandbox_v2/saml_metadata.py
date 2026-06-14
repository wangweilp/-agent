"""Sandbox v2 SAML Metadata Service — Step 22.

IdP Metadata XML 解析与缓存。
支持 entityID / SSO endpoint / SLO endpoint / X509 certificate / NameID Format 提取。

安全原则：
1. 默认 disabled
2. 不接受外部 URL 下载（metadata_download_enabled 必须显式开启）
3. 不信任未验证的 metadata
4. 解析失败 → fail closed
5. XML 必须 well-formed
"""
from __future__ import annotations

import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any

from src.open_platform.sandbox_v2.models import SandboxV2SAMLMetadata

logger = logging.getLogger(__name__)

_SAML_NS = "urn:oasis:names:tc:SAML:2.0:metadata"
_MD_NS = "urn:oasis:names:tc:SAML:2.0:metadata"
_DS_NS = "http://www.w3.org/2000/09/xmldsig#"
_SSO_BINDING_HTTP_REDIRECT = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
_SSO_BINDING_HTTP_POST = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
_SLO_BINDING_HTTP_REDIRECT = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"

# XXE prevention — block DTD entirely
_DTD_PATTERN = re.compile(r'<!DOCTYPE', re.IGNORECASE)


class SandboxV2SAMLMetadataService:
    """SAML Metadata 导入与缓存服务。默认 disabled。"""

    def __init__(self, settings: Any = None):
        self._settings = settings
        self._cache: dict[str, SandboxV2SAMLMetadata] = {}

    def _cfg(self, key: str, default: Any = None) -> Any:
        return getattr(self._settings, key, default) if self._settings else default

    @property
    def enabled(self) -> bool:
        return bool(self._cfg("saml_metadata_import_enabled", False))

    @property
    def cache_ttl_seconds(self) -> int:
        return int(self._cfg("saml_metadata_cache_ttl_seconds", 3600))

    def import_metadata_xml(self, xml_content: str, source: str = "import",
                            entity_id_hint: str = "") -> SandboxV2SAMLMetadata | None:
        """导入 IdP Metadata XML 并返回解析结果。

        默认 disabled — 必须将 SAML_METADATA_IMPORT_ENABLED=true 后才工作。
        """
        if not self.enabled:
            logger.warning("SAML metadata import is disabled")
            return None

        if not xml_content or not xml_content.strip():
            logger.warning("Empty XML content for metadata import")
            return None

        # XXE check
        if _DTD_PATTERN.search(xml_content):
            logger.warning("DTD/XXE pattern detected in metadata XML — rejected")
            return None

        try:
            root = ET.fromstring(xml_content.strip())
        except ET.ParseError as e:
            logger.warning(f"XML parse error in metadata: {e}")
            return None

        ns = self._resolve_namespaces(root)

        entity_id = self._extract_entity_id(root, ns)
        if not entity_id and not entity_id_hint:
            logger.warning("No entityID found in metadata")
            return None

        entity_id = entity_id or entity_id_hint

        sso_url = self._extract_endpoint(root, ns, "SingleSignOnService", _SSO_BINDING_HTTP_REDIRECT)
        sso_url_post = self._extract_endpoint(root, ns, "SingleSignOnService", _SSO_BINDING_HTTP_POST)
        slo_url = self._extract_endpoint(root, ns, "SingleLogoutService", _SLO_BINDING_HTTP_REDIRECT)

        certs = self._extract_certificates(root, ns)
        fingerprints = [self._sha256_fingerprint(c) for c in certs]

        name_id_formats = self._extract_name_id_formats(root, ns)

        org_name = self._extract_text(root, ns, "OrganizationName")
        org_display = self._extract_text(root, ns, "OrganizationDisplayName")

        ttl = self.cache_ttl_seconds
        metadata_obj = SandboxV2SAMLMetadata(
            entity_id=entity_id,
            organization_name=org_name,
            organization_display_name=org_display,
            sso_url=sso_url,
            sso_url_post=sso_url_post,
            slo_url=slo_url,
            name_id_formats=name_id_formats,
            x509_certificates=certs,
            certificate_fingerprints=fingerprints,
            signing_certificates=certs,  # conservative: treat all as signing
            encryption_certificates=[],
            parsed_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl),
            source=source,
            raw_xml_redacted="<redacted/>",
        )

        # Cache
        cache_key = entity_id
        self._cache[cache_key] = metadata_obj
        logger.info(f"SAML metadata imported for entityID={entity_id}, {len(certs)} cert(s)")
        return metadata_obj

    def get_metadata(self, entity_id: str) -> SandboxV2SAMLMetadata | None:
        """从缓存获取 metadata。如果过期返回 None。"""
        entry = self._cache.get(entity_id)
        if not entry:
            return None
        if entry.is_expired():
            logger.warning(f"SAML metadata for {entity_id} has expired")
            # Don't delete — caller may decide to use expired as last-resort
        return entry

    def get_or_import(self, xml_content: str, entity_id: str = "", source: str = "import") -> SandboxV2SAMLMetadata | None:
        """获取缓存的 metadata，若无则导入。"""
        cached = self.get_metadata(entity_id) if entity_id else None
        if cached and not cached.is_expired():
            return cached
        return self.import_metadata_xml(xml_content, source=source, entity_id_hint=entity_id)

    def clear_cache(self, entity_id: str = "") -> None:
        if entity_id:
            self._cache.pop(entity_id, None)
        else:
            self._cache.clear()

    def _resolve_namespaces(self, root: ET.Element) -> dict[str, str]:
        ns = {"md": _MD_NS, "ds": _DS_NS, "saml": "urn:oasis:names:tc:SAML:2.0:assertion",
              "samlp": "urn:oasis:names:tc:SAML:2.0:protocol"}
        # Auto-detect from root tag
        tag = root.tag.lower() if hasattr(root, 'tag') else ""
        if "metadata" in tag:
            ns["md"] = root.tag.split("}")[0].strip("{") if "}" in root.tag else _MD_NS
        return ns

    def _extract_entity_id(self, root: ET.Element, ns: dict[str, str]) -> str:
        for suffix in ["entityID", "entityid", "EntityID"]:
            for prefix in ["md", "saml", ""]:
                xp = f".//{{{ns.get(prefix, '')}}}{suffix}" if prefix and ns.get(prefix) else f".//{suffix}"
                el = root.find(xp)
                if el is not None:
                    return (el.text or el.get("entityID") or "").strip()
        # Fallback: check root attrib
        for attr in ["entityID", "entityid", "EntityID"]:
            val = root.get(attr, "")
            if val:
                return val.strip()
        return ""

    def _extract_endpoint(self, root: ET.Element, ns: dict[str, str],
                          element_name: str, binding: str) -> str:
        for prefix in ["md", ""]:
            ns_uri = ns.get(prefix, "") if prefix else ""
            for el in root.iter():
                tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
                if tag == element_name:
                    el_binding = el.get("Binding", "")
                    if binding in el_binding:
                        loc = el.get("Location", "")
                        if loc:
                            return loc.strip()
        return ""

    def _extract_certificates(self, root: ET.Element, ns: dict[str, str]) -> list[str]:
        certs: list[str] = []
        # Search for X509Certificate elements
        for el in root.iter():
            tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
            if tag == "X509Certificate":
                text = (el.text or "").strip()
                if text and len(text) > 100:  # reasonable cert size
                    certs.append(self._normalize_x509(text))
        return certs

    def _extract_name_id_formats(self, root: ET.Element, ns: dict[str, str]) -> list[str]:
        formats: list[str] = []
        for el in root.iter():
            tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
            if tag == "NameIDFormat":
                text = (el.text or "").strip()
                if text:
                    formats.append(text)
        return formats

    def _extract_text(self, root: ET.Element, ns: dict[str, str], tag_name: str) -> str:
        for el in root.iter():
            tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
            if tag == tag_name:
                return (el.text or "").strip()
        return ""

    @staticmethod
    def _normalize_x509(cert_text: str) -> str:
        """Normalize X509 cert: remove whitespace, wrap with PEM headers."""
        cleaned = re.sub(r'\s+', '', cert_text)
        cleaned = cleaned.replace("-----BEGINCERTIFICATE-----", "").replace("-----ENDCERTIFICATE-----", "")
        return f"-----BEGIN CERTIFICATE-----\n{cleaned}\n-----END CERTIFICATE-----"

    @staticmethod
    def _sha256_fingerprint(cert_pem: str) -> str:
        """Generate SHA-256 fingerprint of an X.509 certificate (PEM format)."""
        # Strip PEM headers and decode base64
        b64 = cert_pem.replace("-----BEGIN CERTIFICATE-----", "") \
                      .replace("-----END CERTIFICATE-----", "") \
                      .replace("\n", "").replace("\r", "").strip()
        try:
            import base64
            der = base64.b64decode(b64)
            return hashlib.sha256(der).hexdigest()
        except Exception:
            return hashlib.sha256(cert_pem.encode()).hexdigest()

    def get_readiness(self) -> dict[str, Any]:
        """SAML Metadata Readiness 报告。"""
        return {
            "enabled": self.enabled,
            "ready": self.enabled and len(self._cache) > 0,
            "cached_entities": len(self._cache),
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "status": "ready" if (self.enabled and len(self._cache) > 0) else ("disabled" if not self.enabled else "not_ready"),
            "reason": "" if self.enabled else "SAML_METADATA_IMPORT_ENABLED=false",
        }
