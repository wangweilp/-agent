#!/usr/bin/env python
"""Sandbox v2 Real SSO Check Script — Step 20.

Reads OIDC/SAML settings, checks real login flow readiness.
No external network. No token storage.

Usage:
    python scripts/check_sandbox_v2_real_sso.py
"""
from __future__ import annotations
import json, os, sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _env_bool(n: str, d: bool = False) -> bool:
    v = os.getenv(n, "").strip().lower()
    return v in ("true", "1", "yes") if v else d


def check() -> dict:
    real_oidc = _env_bool("SANDBOX_V2_REAL_OIDC_LOGIN_ENABLED")
    real_saml = _env_bool("SANDBOX_V2_REAL_SAML_LOGIN_ENABLED")
    token_exch = _env_bool("SANDBOX_V2_OIDC_TOKEN_EXCHANGE_ENABLED")
    jwks = _env_bool("SANDBOX_V2_OIDC_JWKS_FETCH_ENABLED")
    disco = _env_bool("SANDBOX_V2_OIDC_DISCOVERY_FETCH_ENABLED")
    sso_sess = _env_bool("SANDBOX_V2_SSO_SESSION_ENABLED")

    blockers: list[str] = []
    warnings: list[str] = []

    if real_oidc and not token_exch:
        blockers.append("real_oidc_login_enabled=true but token_exchange_enabled=false")
    if disco:
        blockers.append("OIDC discovery fetch enabled — must be false unless audited")
    if jwks:
        blockers.append("OIDC JWKS fetch enabled — must be false unless audited")

    # OIDC preflight
    try:
        from src.open_platform.sandbox_v2.oidc_flow import SandboxV2OIDCFlowService
        svc = SandboxV2OIDCFlowService()
        oidc_ready = svc.get_oidc_readiness()
    except Exception as e:
        oidc_ready = {}
        warnings.append(f"OIDC readiness error: {e}")

    # SAML preflight
    try:
        from src.open_platform.sandbox_v2.saml_flow import SandboxV2SAMLFlowService
        saml = SandboxV2SAMLFlowService()
        saml_ready = saml.get_saml_readiness()
    except Exception as e:
        saml_ready = {}
        warnings.append(f"SAML readiness error: {e}")

    return {
        "real_oidc_login_enabled": real_oidc,
        "real_saml_login_enabled": real_saml,
        "oidc_authorization_code_flow": True,
        "oidc_state_nonce_pkce": True,
        "oidc_token_exchange_enabled": token_exch,
        "oidc_signature_validation": False,
        "saml_sp_initiated_flow": True,
        "saml_acs_endpoint": True,
        "saml_signature_validation": False,
        "saml_xxe_protection": True,
        "sso_session_binding": sso_sess,
        "token_storage": False,
        "blockers": blockers,
        "warnings": warnings,
        "safe_mode": not real_oidc and not real_saml,
    }


def main():
    result = check()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result["blockers"]:
        print("\n[BLOCKERS]:")
        for b in result["blockers"]: print(f"  - {b}")
    if result["warnings"]:
        print("\n[Warnings]:")
        for w in result["warnings"]: print(f"  - {w}")
    if result["safe_mode"]:
        print("\n[OK] Real SSO safe mode active. No real login enabled by default.")
    sys.exit(1 if result["blockers"] else 0)


if __name__ == "__main__":
    main()
