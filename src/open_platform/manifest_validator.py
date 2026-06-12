"""Manifest Validator — shared backend validator for developer agent manifests.

Used by:
- Developer API validate endpoint
- SDK validator (via copy or shared import)
- Admin Review manifest inspection

Rules aligned with:
- src/open_platform/submission.py: AgentManifest.validate()
- src/open_platform/package_validation_service.py: checks
- schemas/cognitive-agent.schema.json

Safety: no network, no package download, no code execution.
"""

from __future__ import annotations

import re as _re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

_MANIFEST_NAME_RE = _re.compile(r"^[a-z0-9_-]+$")
_SEMVER_RE = _re.compile(r"^\d+\.\d+\.\d+(-[a-zA-Z0-9_.]+)?(\+[a-zA-Z0-9_.]+)?$")
_ALLOWED_CHECKSUM_ALGOS = {"sha256", "sha384", "sha512"}
_ALLOWED_SIGNATURE_ALGOS = {"minisign", "cosign", "gpg"}

MVP_ALLOWED_RUNTIME_TYPES = {"manifest_only"}
MVP_ALLOWED_SANDBOX_LEVELS = {"no_execution", "simulation_only"}


@dataclass
class ValidationIssue:
    code: str = ""
    severity: str = "info"  # info | warning | error | blocker
    message: str = ""
    path: str = ""  # json path, e.g. "security_profile.requires_network"
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

    # ── required fields ──
    for field in ("name", "display_name", "description", "version", "capabilities", "required_permissions", "runtime_type", "security_profile"):
        if field not in manifest:
            _add(f"missing_{field}", "blocker", f"Required field '{field}' is missing.", field)

    # ── name ──
    name = manifest.get("name", "")
    if not isinstance(name, str) or not name:
        _add("name_required", "error", "name is required and must be a non-empty string.", "name")
    elif not _MANIFEST_NAME_RE.match(str(name)):
        _add("name_pattern", "error", f"name '{name}' must match pattern ^[a-z0-9_-]+$", "name")

    # ── display_name ──
    dn = manifest.get("display_name", "")
    if not isinstance(dn, str) or not dn:
        _add("display_name_required", "error", "display_name is required.", "display_name")

    # ── description ──
    desc = manifest.get("description", "")
    if not isinstance(desc, str) or not desc:
        _add("description_required", "error", "description is required.", "description")

    # ── version ──
    ver = manifest.get("version", "")
    if not isinstance(ver, str) or not ver:
        _add("version_required", "error", "version is required.", "version")
    elif not _SEMVER_RE.match(str(ver)):
        _add("version_semver", "warning", f"version '{ver}' is not semver.", "version")

    # ── capabilities ──
    caps = manifest.get("capabilities", [])
    if not isinstance(caps, list) or len(caps) == 0:
        _add("capabilities_required", "error", "capabilities must be a non-empty array.", "capabilities")

    # ── required_permissions ──
    perms = manifest.get("required_permissions", [])
    if not isinstance(perms, list) or len(perms) == 0:
        _add("permissions_required", "error", "required_permissions must be a non-empty array.", "required_permissions")

    # ── runtime_type ──
    rt = manifest.get("runtime_type", "")
    if not isinstance(rt, str) or not rt:
        _add("runtime_type_required", "error", "runtime_type is required.", "runtime_type")
    elif strict and rt not in MVP_ALLOWED_RUNTIME_TYPES:
        _add("runtime_type_unsupported", "blocker",
             f"runtime_type='{rt}' is not supported in MVP. Only 'manifest_only' is allowed.", "runtime_type")

    # ── entrypoint ──
    ep = manifest.get("entrypoint")
    if ep is not None and str(ep).strip():
        _add("entrypoint_reserved", "warning",
             "entrypoint is reserved and will NOT be executed in Step 23 runtime.", "entrypoint")

    # ── config_schema ──
    cs = manifest.get("config_schema", {})
    if not isinstance(cs, dict):
        _add("config_schema_type", "error", "config_schema must be an object.", "config_schema")

    # ── usage_limits ──
    ul = manifest.get("usage_limits", {})
    if not isinstance(ul, dict):
        _add("usage_limits_type", "error", "usage_limits must be an object.", "usage_limits")

    # ── security_profile ──
    sp = manifest.get("security_profile")
    if not isinstance(sp, dict):
        _add("security_profile_required", "blocker", "security_profile is required and must be an object.", "security_profile")
    else:
        sl = sp.get("sandbox_level", "")
        if not isinstance(sl, str) or not sl:
            _add("sandbox_level_required", "error", "security_profile.sandbox_level is required.", "security_profile.sandbox_level")
        elif strict and sl not in MVP_ALLOWED_SANDBOX_LEVELS:
            _add("sandbox_level_unsupported", "blocker",
                 f"sandbox_level='{sl}' is not allowed in MVP. Only no_execution and simulation_only.", "security_profile.sandbox_level")

        if sp.get("requires_network"):
            _add("network_forbidden", "error",
                 "requires_network=true is not allowed in MVP.", "security_profile.requires_network")

        if sp.get("writes_user_data"):
            _add("write_forbidden", "error",
                 "writes_user_data=true is not allowed in MVP.", "security_profile.writes_user_data")

        if sp.get("reads_user_data"):
            _add("reads_user_data_warning", "warning",
                 "reads_user_data=true — user data access requested. Reviewer must verify.", "security_profile.reads_user_data")

        if sp.get("requires_secrets"):
            _add("secrets_forbidden", "error",
                 "requires_secrets=true is not allowed in MVP.", "security_profile.requires_secrets")

    # ── metadata ──
    meta = manifest.get("metadata", {})
    if not isinstance(meta, dict):
        _add("metadata_type", "error", "metadata must be an object.", "metadata")
    else:
        _validate_package_url(meta, result, _add, strict)
        _validate_repository_url(meta, result, _add, strict)
        _validate_checksum(meta, result, _add)
        _validate_signature(meta, result, _add)
        _validate_dependencies(meta, result, _add)
        _validate_license(meta, result, _add)

    return result


def _validate_package_url(meta: dict, result: ManifestValidationResult, _add, strict: bool):
    pu = meta.get("package_url", "")
    if not pu: return
    if not isinstance(pu, str): return
    _validate_url(pu, "metadata.package_url", result, _add, strict)


def _validate_repository_url(meta: dict, result: ManifestValidationResult, _add, strict: bool):
    ru = meta.get("repository_url", "")
    if not ru: return
    if not isinstance(ru, str): return
    _validate_url(ru, "metadata.repository_url", result, _add, strict)


def _validate_url(url: str, path: str, result: ManifestValidationResult, _add, strict: bool):
    blocked = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "metadata.google.internal", "169.254.169.254"}
    try:
        p = urlparse(url)
        if p.scheme not in ("https",):
            _add("url_https_only", "error" if strict else "warning",
                 f"[{path}] Only HTTPS allowed, got '{p.scheme}'.", path)
            return
        host = (p.hostname or "").lower()
        if host in blocked:
            _add("url_blocked", "blocker", f"[{path}] Domain '{host}' is blocked.", path)
            return
        if _is_private_ip(host):
            _add("url_private_ip", "blocker", f"[{path}] Private IP not allowed: {host}", path)
            return
    except Exception:
        _add("url_invalid", "error", f"[{path}] Invalid URL format.", path)


def _validate_checksum(meta: dict, result: ManifestValidationResult, _add):
    algo = meta.get("package_checksum_algorithm", "")
    if algo and algo not in _ALLOWED_CHECKSUM_ALGOS:
        _add("checksum_algo_invalid", "error",
             f"package_checksum_algorithm '{algo}' not in {sorted(_ALLOWED_CHECKSUM_ALGOS)}", "metadata.package_checksum_algorithm")
    cs = meta.get("package_checksum", "")
    if not cs and meta.get("package_url"):
        _add("checksum_missing", "warning",
             "package_url present but package_checksum not declared.", "metadata.package_checksum")


def _validate_signature(meta: dict, result: ManifestValidationResult, _add):
    algo = meta.get("package_signature_algorithm", "")
    if algo and algo not in _ALLOWED_SIGNATURE_ALGOS:
        _add("signature_algo_invalid", "error",
             f"package_signature_algorithm '{algo}' not in {sorted(_ALLOWED_SIGNATURE_ALGOS)}", "metadata.package_signature_algorithm")
    sig = meta.get("package_signature", "")
    if not sig and meta.get("package_url"):
        _add("signature_missing", "warning",
             "package_url present but package_signature not declared.", "metadata.package_signature")


def _validate_dependencies(meta: dict, result: ManifestValidationResult, _add):
    deps = meta.get("dependencies")
    if deps is None: return
    if not isinstance(deps, list):
        _add("deps_not_list", "error", "metadata.dependencies must be a list.", "metadata.dependencies")
        return
    empty = [d for d in deps if isinstance(d, str) and not d.strip()]
    if empty:
        _add("deps_empty", "error", f"Dependencies contain {len(empty)} empty entries.", "metadata.dependencies")


def _validate_license(meta: dict, result: ManifestValidationResult, _add):
    lic = meta.get("license", "")
    if not lic:
        _add("license_missing", "warning", "No license declared in metadata.", "metadata.license")


def _is_private_ip(host: str) -> bool:
    import ipaddress
    try:
        a = ipaddress.ip_address(host)
        return a.is_private or a.is_loopback or a.is_link_local or a.is_multicast or a.is_unspecified
    except ValueError:
        return False
