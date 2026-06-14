# OIDC Production Readiness — Step 21

**日期:** 2026-06-14
**状态:** Production-Grade Identity Validation (signature + claims) — 默认关闭
**前置:** Step 20 (Real SSO Skeleton)

> ⚠️ **诚实的能力边界声明** — 本文档不夸大能力。所有列在
> 「未完成」的项目都尚未实现，**不应在生产配置中启用**。

---

## 一句话总结

Step 21 把 OIDC 从 **Real SSO Skeleton** 升级到 **Production-Grade OIDC Identity Validation**
—— JWKS 发现、kid 解析、RS256 签名验证、claim 全套校验、身份映射全部上线；
**所有能力默认关闭**；签名验证仅在显式
`OIDC_SIGNATURE_VALIDATION_ENABLED=true` 后才在 readiness 中显示 `enabled`。

---

## ✅ 当前已完成 (Production-Grade Identity Validation)

| 能力 | 默认 | 描述 |
|------|------|------|
| **Discovery** | disabled | 拉取并缓存 `/.well-known/openid-configuration`；anti-issuer-spoof；缓存 TTL |
| **JWKS Cache** | disabled | kid rotation 支持；失败 cooldown + 重试；fail closed |
| **Signature Validation** | disabled | RS256 验签 (via python-jose)；alg whitelist；kid 必填；alg=none 必拒 |
| **Claim Validation** | disabled (随 signature) | sub / iss / aud / exp / iat / nbf / nonce 全套校验；clock skew |
| **Identity Mapping** | ready | claims → local user → roles → scopes → SSO session (复用 Step 17 mapper) |

### 安全不变量 (invariants)

- `token_storage = false` — **永不存储** access_token / refresh_token / id_token 原文
- `default deny` — 任何子服务默认关闭
- `fail closed` — JWKS/Discovery 拉取失败**绝不退化为跳过验证**
- `audit first` — 验证结果摘要写入审计 (id_token_validation 摘要, 不含 token)
- `secure by default` — alg=none 必拒；kid 必填；issuer 精确匹配；audience 精确匹配；nonce replay 必拒
- `python-jose` + `cryptography` 用于 RS256 验签

### 配置开关 (默认全部 false)

```bash
# 总开关 — 开启后 readiness 才显示 signature_validation=true
SANDBOX_V2_OIDC_SIGNATURE_VALIDATION_ENABLED=false

# 子能力
SANDBOX_V2_OIDC_TOKEN_EXCHANGE_ENABLED=false
SANDBOX_V2_OIDC_JWKS_FETCH_ENABLED=false
SANDBOX_V2_OIDC_DISCOVERY_FETCH_ENABLED=false

# 安全参数
SANDBOX_V2_OIDC_ALLOWED_ALGS=RS256      # 白名单；绝不包含 none
SANDBOX_V2_OIDC_REQUIRE_KID=true         # 防 alg/key 混淆
SANDBOX_V2_OIDC_JWKS_CACHE_TTL_SECONDS=3600
SANDBOX_V2_OIDC_JWKS_REFRESH_RETRIES=2
SANDBOX_V2_OIDC_JWKS_REFRESH_COOLDOWN_SECONDS=30
SANDBOX_V2_OIDC_DISCOVERY_CACHE_TTL_SECONDS=3600
SANDBOX_V2_OIDC_CLOCK_SKEW_SECONDS=60
```

### Readiness 字段映射

| 配置 | legacy `/iam/sso/readiness` | Step 21 `/iam/oidc/validation/readiness` |
|------|----------------------------|------------------------------------------|
| signature_validation_enabled | `oidc_signature_validation: true` | `signature_validation.status: ready` |
| (disabled) | `oidc_signature_validation: false` | `signature_validation.status: disabled` |

Step 21 Runtime Admin 端点返回每子能力的 `enabled / disabled / ready / not_ready` 状态：

```json
{
  "step": "step21_oidc_production_validation",
  "signature_validation": {"enabled": false, "status": "disabled"},
  "oidc_discovery":        {"enabled": false, "status": "disabled"},
  "jwks_cache":            {"enabled": false, "status": "disabled"},
  "token_exchange":        {"enabled": false, "status": "disabled"},
  "claim_validation":      {"enabled": false, "status": "disabled"},
  "identity_mapping":      {"enabled": true,  "status": "ready"},
  "token_storage": false,
  "fail_closed": true,
  "secure_by_default": true
}
```

---

## ❌ 当前未完成 (NOT Production-Ready)

以下能力**尚未实现**，**不应**在生产配置中启用：

| 能力 | 状态 | 说明 |
|------|------|------|
| **MFA Federation** | ❌ 未实现 | 未集成 WebAuthn / TOTP / PUSH；不能用于强因子联邦 |
| **SCIM** | ❌ 未实现 | 用户/组生命周期同步 (RFC 7643/7644) 未实现 |
| **Cross-Tenant Federation** | ❌ 未实现 | 多 IdP / 多租户联邦编排未实现 |
| **Production IdP Certification** | ❌ 未完成 | 尚未对 Okta/Auth0/Keycloak/Azure AD 做正式互操作认证 |

### 网络出口限制

- 真实 Discovery / JWKS / Token Exchange 的网络出口通过依赖注入
  (`HttpFetcherProtocol` / `TokenEndpointClientProtocol`)
- 默认**无注入器** → fail closed
- 必须由部署方审计后注入可信 fetcher

### 安全审计缺口

- 暂未做 formal penetration test (仅 Step 21 自带 Red-Team 28 项)
- 暂未做 formal OIDC Conformance 测试 (RFC / OpenID Certification)
- 暂未集成 HSM/KMS for signing key custody (离线签名 key 由 IdP 保管，本服务只验签)

---

## API 端点 (Step 21 新增)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/api/runtime/sandbox-v2/iam/oidc/validation/readiness` | Step 21 详细 readiness |
| POST | `/api/runtime/sandbox-v2/iam/oidc/validate-id-token` | 手动验证 id_token (不持久化) |
| GET  | `/api/admin/runtime/oidc-validation/readiness` | Runtime Admin OIDC Readiness (admin-only) |

---

## 测试结果 (Step 21)

- **Security Tests:** 11/11 passed (含正向用例)
  - invalid issuer / invalid audience / expired / future nbf / nonce mismatch /
    unknown kid / JWKS rotation / invalid signature / missing claims /
    disabled mode / positive case
- **Red-Team Tests:** 8/8 passed
  - alg=none / unsigned token / wrong issuer / wrong audience /
    replay nonce / JWKS fail closed / default-disabled blocks / no-token-persisted
- **Token Exchange + Mapping Tests:** 9/9 passed

---

## Step 22 建议 (Recommended Next Step)

按优先级：

1. **MFA Federation** — 集成 WebAuthn / TOTP 二因子；OIDC `acr` / `amr` claim 校验
2. **SCIM Provisioning** — JIT 之外的批量用户/组同步；生命周期审计
3. **Cross-Tenant Federation** — 多 IdP 路由；Home Realm Discovery
4. **Production IdP Certification** — Okta / Auth0 / Keycloak / Azure AD 互操作测试套件
5. **Token Revocation / Back-Channel Logout** — RFC 8414 / RFC 4628 集成
6. **Formal OIDC Conformance Suite** — OpenID Certification 流程

---

## 边界 (Out of Scope — 永不实现)

- ❌ 用户密码登录 (本系统是 IdP 消费方，不是密码 IdP)
- ❌ 自定义 IdP (不做自建身份提供者)
- ❌ Token 持久化 (`token_storage=false` 永远)
- ❌ Refresh Token 存储 (`refresh_token_persisted=false` 永远)
- ❌ 自动信任任何 Issuer (issuer 必须精确匹配配置)

---

## 文件清单

### 新增文件

| # | 文件 | 说明 |
|---|------|------|
| 1 | `src/open_platform/sandbox_v2/oidc_discovery.py` | Discovery + JWKS Cache 服务 |
| 2 | `src/open_platform/sandbox_v2/oidc_identity_validation.py` | RS256 + Claim Validation |
| 3 | `src/open_platform/sandbox_v2/oidc_token_exchange.py` | Token Exchange + Identity Mapping |
| 4 | `src/open_platform/sandbox_v2/oidc_step21_service.py` | Step 21 orchestrator |
| 5 | `tests/test_open_platform/oidc_step21_fixtures.py` | 测试 fixtures (RSA/JWT/JWKS) |
| 6 | `tests/test_open_platform/test_sandbox_v2_oidc_step21_security.py` | Security Tests (11) |
| 7 | `tests/test_open_platform/test_sandbox_v2_oidc_step21_exchange_mapping.py` | Exchange+Mapping (9) |
| 8 | `tests/test_open_platform/red_team/test_sandbox_v2_red_team_oidc_step21.py` | Red-Team (8) |
| 9 | `docs/oidc-production-readiness.md` | 本文档 |

### 修改文件

- `src/open_platform/sandbox_v2/config.py` — 新增 8 个 Step 21 配置 + production_blockers
- `src/open_platform/sandbox_v2/models.py` — 新增 Step 21 数据模型
- `src/open_platform/sandbox_v2/iam.py` — readiness 同步 + `get_oidc_validation_readiness`
- `src/open_platform/sandbox_v2/service.py` — `get_oidc_validation_readiness` + `validate_oidc_id_token`
- `src/api/sandbox_v2.py` — 2 个新 API + readiness 字段同步
- `src/api/runtime_admin_router.py` — Runtime Admin 新增 Step 21 readiness 端点
- `.env.sandbox-v2.example` — 新增 8 个 Step 21 环境变量示例
