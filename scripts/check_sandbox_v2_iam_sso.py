#!/usr/bin/env python
"""Sandbox v2 IAM / SSO Check Script — Step 17.

Reads IAM/SSO settings from environment, checks readiness, runs mock claims preflight.
No external network. No metadata download. No token storage.

Usage:
    python scripts/check_sandbox_v2_iam_sso.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name, "").strip().lower()
    if val in ("true", "1", "yes"):
        return True
    if val in ("false", "0", "no"):
        return False
    return default


def _env_str(name: str, default: str) -> str:
    return os.getenv(name, "").strip() or default


def check_iam_sso() -> dict:
    """Run IAM/SSO readiness check. Returns JSON-serializable dict."""

    # Read settings
    iam_enabled = _env_bool("SANDBOX_V2_IAM_ENABLED", False)
    sso_enabled = _env_bool("SANDBOX_V2_SSO_ENABLED", False)
    oidc_enabled = _env_bool("SANDBOX_V2_OIDC_ENABLED", False)
    saml_enabled = _env_bool("SANDBOX_V2_SAML_ENABLED", False)
    discovery_enabled = _env_bool("SANDBOX_V2_OIDC_DISCOVERY_ENABLED", False)
    metadata_download_enabled = _env_bool("SANDBOX_V2_SAML_METADATA_DOWNLOAD_ENABLED", False)
    token_storage = False  # hardcoded — never stored

    blockers: list[str] = []
    warnings: list[str] = []

    # Mock provider check
    try:
        from src.open_platform.sandbox_v2.iam_provider import MockIAMProvider
        from src.open_platform.sandbox_v2.models import SandboxV2IAMProviderConfig
        provider = MockIAMProvider()
        mock_available = True

        # Run mock claims preflight
        config = SandboxV2IAMProviderConfig(
            enabled=True, issuer="https://mock-idp.example.com",
            allowed_domains=["example.com"],
        )
        result = provider.simulate_login(
            claims={
                "sub": "check-user-1",
                "iss": "https://mock-idp.example.com",
                "email": "user@example.com",
                "email_verified": True,
                "name": "Check User",
            },
            config=config,
        )
        claim_mapping_ready = result.get("allowed", False)
        role_scope_mapping_ready = claim_mapping_ready

    except Exception as e:
        mock_available = False
        claim_mapping_ready = False
        role_scope_mapping_ready = False
        warnings.append(f"Mock provider check failed: {e}")

    # Safety checks
    if discovery_enabled:
        blockers.append("OIDC discovery_enabled is true — must be false; no external network calls allowed")
    if metadata_download_enabled:
        blockers.append("SAML metadata_download_enabled is true — must be false; no external network calls allowed")
    if oidc_enabled and not iam_enabled:
        blockers.append("OIDC enabled but IAM is disabled")
    if saml_enabled and not iam_enabled:
        blockers.append("SAML enabled but IAM is disabled")
    if sso_enabled and not iam_enabled:
        blockers.append("SSO enabled but IAM is disabled")

    safe_mode = (
        not discovery_enabled
        and not metadata_download_enabled
        and not token_storage
        and mock_available
    )

    return {
        "iam_enabled": iam_enabled,
        "sso_enabled": sso_enabled,
        "oidc_enabled": oidc_enabled,
        "saml_enabled": saml_enabled,
        "mock_provider_available": mock_available,
        "real_oidc_login": False,
        "real_saml_login": False,
        "token_storage": token_storage,
        "claim_mapping_ready": claim_mapping_ready,
        "role_scope_mapping_ready": role_scope_mapping_ready,
        "blockers": blockers,
        "warnings": warnings,
        "safe_mode": safe_mode,
    }


def main():
    result = check_iam_sso()
    print(json.dumps(result, indent=2, ensure_ascii=False))

    has_blockers = len(result.get("blockers", [])) > 0
    if has_blockers:
        print("\n[BLOCKERS] found:")
        for b in result["blockers"]:
            print(f"  - {b}")

    warns = result.get("warnings", [])
    if warns:
        print("\n[Warnings]:")
        for w in warns:
            print(f"  - {w}")

    if result.get("safe_mode"):
        print("\n[OK] IAM safe mode active. All defaults are secure.")

    sys.exit(1 if has_blockers else 0)


if __name__ == "__main__":
    main()
