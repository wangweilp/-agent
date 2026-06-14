# Sandbox v2 Step 20 Report — 真实 OIDC / SAML 登录闭环

**日期:** 2026-06-14
**状态:** Complete

## 新增文件

| # | 文件 | 说明 |
|---|------|------|
| 1 | `src/open_platform/sandbox_v2/oidc_flow.py` | OIDC Authorization Code Flow 服务 |
| 2 | `src/open_platform/sandbox_v2/saml_flow.py` | SAML SP-Initiated Flow 服务 |
| 3 | `tests/test_open_platform/test_sandbox_v2_oidc_flow.py` | OIDC flow 测试 (14) |
| 4 | `tests/test_open_platform/test_sandbox_v2_saml_flow.py` | SAML flow 测试 (9) |
| 5 | `tests/test_open_platform/test_sandbox_v2_real_sso_service.py` | SSO service 测试 (5) |
| 6 | `tests/test_open_platform/test_sandbox_v2_real_sso_api.py` | SSO API 测试 (10) |
| 7 | `tests/test_open_platform/test_sandbox_v2_sso_session.py` | Session 测试 (5) |
| 8 | `tests/test_open_platform/red_team/test_sandbox_v2_red_team_real_sso.py` | Red-Team (17) |
| 9 | `scripts/check_sandbox_v2_real_sso.py` | Real SSO check script |
| 10 | `docs/sandbox-v2-real-sso-flow.md` | 文档 |

## 修改文件 (8 个)

`config.py`, `models.py`, `store.py`, `sqlite_sandbox_v2_store.py`, `service.py`, `sandbox_v2.py`, `iam.py`, `.env.sandbox-v2.example`

## 新增 API (10 个)

| 方法 | 路径 |
|------|------|
| GET  | `/iam/sso/readiness` |
| POST | `/iam/oidc/authorize` |
| GET  | `/iam/oidc/callback` |
| POST | `/iam/oidc/callback` |
| POST | `/iam/saml/authn-request` |
| POST | `/iam/saml/acs` |
| GET  | `/iam/sso/sessions` |
| POST | `/iam/sso/sessions/{id}/revoke` |
| GET  | `/iam/oidc/callback-results` |
| GET  | `/iam/saml/acs-results` |

## OIDC Flow Readiness

```
real_oidc_login_enabled: false | oidc_authorization_code_flow: true
state_nonce_pkce: true         | token_exchange_enabled: false
signature_validation: false    | claim_validation: true
token_storage: false           | sso_safe_mode: true
```

## SAML Flow Readiness

```
real_saml_login_enabled: false | saml_xxe_protection: true
sp_initiated_flow: true        | unsigned_assertion_blocked: true
signature_validation: false    | token_storage: false
```

## State/Nonce/PKCE 结果

- state: 32-byte random, SHA256 hash stored, one-time consumption enforced
- nonce: 24-byte random, SHA256 hash stored
- PKCE: S256 challenge, code_verifier SHA256 hashed
- None stored in plaintext

## Token Storage

**token_storage: false** — 所有 token (access/id/refresh) 一律不存，appear in no logs/audit/responses

## SSO Session 结果

- Session 创建不含 token
- Roles/scopes 来源 mapping decision
- Revoke 支持
- 默认 sso_session_enabled=false

## Red-Team Real SSO 结果

**17 passed** — 覆盖: state replay, alg=none, issuer spoof, expired, email unverified, XXE, oversize, unsigned, token not in session, fail-closed, disabled-default

## 测试结果

| 类别 | 结果 |
|------|------|
| Step 20 核心测试 (oidc + saml + service + api + session) | **48 passed** |
| Red-Team Real SSO | **17 passed** |
| 已有 IAM/Security 测试 | **33 passed** |

## 当前仍缺什么

| 项目 | 计划 |
|------|------|
| 真实 IdP 生产验证 | Future |
| 完整 JWT/JWKS 签名验证依赖 | Future |
| 完整 SAML 签名验证依赖 | Future |
| SCIM | Future |
| 主系统 session 深度集成 | Future |

## 下一步建议

1. **Step 21:** 真实 Prometheus/Grafana/OTel Collector 集成
2. **Step 22:** 长期 Soak Test 与生产 SLO 门禁
3. **Step 23:** 安全运行时 UX 与审计体验完善
