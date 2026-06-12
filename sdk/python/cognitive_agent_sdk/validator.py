"""Manifest Validator — static validation for developer agent manifests.

Rules aligned with src/open_platform/manifest_validator.py and schemas/cognitive-agent.schema.json.
Safety: no network, no package download, no code execution.
"""

from __future__ import annotations

import json
import re as _re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_MANIFEST_NAME_RE = _re.compile(r"^[a-z0-9_-]+$")
_SEMVER_RE = _re.compile(r"^\d+\.\d+\.\d+(-[a-zA-Z0-9_.]+)?(\+[a-zA-Z0-9_.]+)?$")
_ALLOWED_CHECKSUM_ALGOS = {"sha256", "sha384", "sha512"}
_ALLOWED_SIGNATURE_ALGOS = {"minisign", "cosign", "gpg"}
MVP_ALLOWED_RUNTIME_TYPES = {"manifest_only"}
MVP_ALLOWED_SANDBOX_LEVELS = {"no_execution", "simulation_only"}


@dataclass
class ValidationIssue:
    code: str = ""
    severity: str = "info"
    message: str = ""
    path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "severity": self.severity,
                "message": self.message, "path": self.path, "metadata": self.metadata}


@dataclass
class ManifestValidationResult:
    valid: bool = True
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]
    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]
    @property
    def blockers(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "blocker"]
    @property
    def has_warnings(self) -> bool: return len(self.warnings) > 0
    @property
    def has_errors(self) -> bool: return len(self.errors) > 0
    @property
    def has_blockers(self) -> bool: return len(self.blockers) > 0

    def summary_counts(self) -> dict[str, int]:
        return {"total": len(self.issues), "warnings": len(self.warnings),
                "errors": len(self.errors), "blockers": len(self.blockers)}

    def to_dict(self) -> dict[str, Any]:
        return {"valid": self.valid,
                "issues": [i.to_dict() for i in self.issues],
                "summary": self.summary_counts(),
                "non_execution_guarantees": [
                    "No package URL was downloaded.",
                    "No package URL was executed.",
                    "No network calls were made.",
                    "No external code was executed.",
                    "This is a static validation only.",
                ]}


def load_manifest_file(path: str | Path) -> dict[str, Any]:
    with open(str(path), "r", encoding="utf-8") as f:
        return json.load(f)


def validate_manifest_file(path: str | Path, strict: bool = True) -> ManifestValidationResult:
    data = load_manifest_file(path)
    return validate_manifest_dict(data, strict)


def validate_manifest_dict(manifest: dict[str, Any], strict: bool = True) -> ManifestValidationResult:
    result = ManifestValidationResult()

    def _add(code: str, severity: str, message: str, path: str = "", meta: dict | None = None):
        issue = ValidationIssue(code=code, severity=severity, message=message, path=path, metadata=meta or {})
        result.issues.append(issue)
        if severity in ("error", "blocker"):
            result.valid = False

    if not isinstance(manifest, dict):
        _add("invalid_type", "blocker", "Manifest must be a JSON object.", "")
        return result

    for field in ("name", "display_name", "description", "version", "capabilities", "required_permissions", "runtime_type", "security_profile"):
        if field not in manifest:
            _add(f"missing_{field}", "blocker", f"Required field '{field}' is missing.", field)

    name = manifest.get("name", "")
    if not isinstance(name, str) or not name:
        _add("name_required", "error", "name required.", "name")
    elif not _MANIFEST_NAME_RE.match(str(name)):
        _add("name_pattern", "error", f"name '{name}' invalid pattern (^[a-z0-9_-]+$)", "name")

    dn = manifest.get("display_name", "")
    if not isinstance(dn, str) or not dn:
        _add("display_name_required", "error", "display_name required.", "display_name")

    desc = manifest.get("description", "")
    if not isinstance(desc, str) or not desc:
        _add("description_required", "error", "description required.", "description")

    ver = manifest.get("version", "")
    if not isinstance(ver, str) or not ver:
        _add("version_required", "error", "version required.", "version")
    elif not _SEMVER_RE.match(str(ver)):
        _add("version_semver", "warning", f"version '{ver}' is not semver.", "version")

    caps = manifest.get("capabilities", [])
    if not isinstance(caps, list) or len(caps) == 0:
        _add("capabilities_required", "error", "capabilities must be non-empty array.", "capabilities")

    perms = manifest.get("required_permissions", [])
    if not isinstance(perms, list) or len(perms) == 0:
        _add("permissions_required", "error", "required_permissions must be non-empty array.", "required_permissions")

    rt = manifest.get("runtime_type", "")
    if not isinstance(rt, str) or not rt:
        _add("runtime_type_required", "error", "runtime_type required.", "runtime_type")
    elif strict and rt not in MVP_ALLOWED_RUNTIME_TYPES:
        _add("runtime_type_unsupported", "blocker",
             f"runtime_type='{rt}' not allowed in MVP (only manifest_only).", "runtime_type")

    ep = manifest.get("entrypoint")
    if ep is not None and str(ep).strip():
        _add("entrypoint_reserved", "warning",
             "entrypoint will NOT be executed in Step 23.", "entrypoint")

    cs = manifest.get("config_schema", {})
    if not isinstance(cs, dict):
        _add("config_schema_type", "error", "config_schema must be object.", "config_schema")

    ul = manifest.get("usage_limits", {})
    if not isinstance(ul, dict):
        _add("usage_limits_type", "error", "usage_limits must be object.", "usage_limits")

    sp = manifest.get("security_profile")
    if not isinstance(sp, dict):
        _add("security_profile_required", "blocker", "security_profile required.", "security_profile")
    else:
        sl = sp.get("sandbox_level", "")
        if not isinstance(sl, str) or not sl:
            _add("sandbox_level_required", "error", "sandbox_level required.", "security_profile.sandbox_level")
        elif strict and sl not in MVP_ALLOWED_SANDBOX_LEVELS:
            _add("sandbox_level_unsupported", "blocker",
                 f"sandbox_level='{sl}' not allowed in MVP.", "security_profile.sandbox_level")
        if sp.get("requires_network"):
            _add("network_forbidden", "error", "requires_network=true not allowed.", "security_profile.requires_network")
        if sp.get("writes_user_data"):
            _add("write_forbidden", "error", "writes_user_data=true not allowed.", "security_profile.writes_user_data")
        if sp.get("reads_user_data"):
            _add("reads_user_data_warning", "warning", "reads_user_data=true — reviewer must verify.", "security_profile.reads_user_data")
        if sp.get("requires_secrets"):
            _add("secrets_forbidden", "error", "requires_secrets=true not allowed.", "security_profile.requires_secrets")

    meta = manifest.get("metadata", {})
    if not isinstance(meta, dict):
        _add("metadata_type", "error", "metadata must be object.", "metadata")
    else:
        _validate_url_static(meta, result, _add)

    return result


def _validate_url_static(meta: dict, result: ManifestValidationResult, _add):
    from urllib.parse import urlparse
    blocked = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "metadata.google.internal", "169.254.169.254"}
    for key, path in [("package_url", "metadata.package_url"), ("repository_url", "metadata.repository_url")]:
        url = meta.get(key, "")
        if not url or not isinstance(url, str): continue
        try:
            p = urlparse(url)
            if p.scheme != "https":
                _add("url_https_only", "error", f"[{key}] Only HTTPS allowed.", path)
                continue
            host = (p.hostname or "").lower()
            if host in blocked:
                _add("url_blocked", "blocker", f"[{key}] Domain '{host}' blocked.", path)
                continue
            import ipaddress
            try:
                a = ipaddress.ip_address(host)
                if a.is_private or a.is_loopback or a.is_link_local or a.is_multicast or a.is_unspecified:
                    _add("url_private_ip", "blocker", f"[{key}] Private IP not allowed.", path)
            except ValueError:
                pass
        except Exception:
            _add("url_invalid", "error", f"[{key}] Invalid URL format.", path)

    algo = meta.get("package_checksum_algorithm", "")
    if algo and algo not in _ALLOWED_CHECKSUM_ALGOS:
        _add("checksum_algo_invalid", "error", f"checksum algorithm '{algo}' not allowed.", "metadata.package_checksum_algorithm")
    if not meta.get("package_checksum") and meta.get("package_url"):
        _add("checksum_missing", "warning", "package_url present but no checksum.", "metadata.package_checksum")

    sig_algo = meta.get("package_signature_algorithm", "")
    if sig_algo and sig_algo not in _ALLOWED_SIGNATURE_ALGOS:
        _add("sig_algo_invalid", "error", f"signature algorithm '{sig_algo}' invalid.", "metadata.package_signature_algorithm")
    if not meta.get("package_signature") and meta.get("package_url"):
        _add("sig_missing", "warning", "package_url present but no signature.", "metadata.package_signature")

    deps = meta.get("dependencies")
    if deps is not None:
        if not isinstance(deps, list):
            _add("deps_not_list", "error", "dependencies must be list.", "metadata.dependencies")
        else:
            empty = [d for d in deps if isinstance(d, str) and not d.strip()]
            if empty:
                _add("deps_empty", "error", f"Dependencies has {len(empty)} empty entries.", "metadata.dependencies")

    if not meta.get("license"):
        _add("license_missing", "warning", "No license declared.", "metadata.license")
