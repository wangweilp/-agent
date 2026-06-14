# Sandbox v2 Step 21 Report — Production-Grade OIDC Identity Validation

**日期:** 2026-06-14
**状态:** Complete
**前置:** Step 20 (Real SSO Skeleton)

> Real SSO Skeleton → **Production-Grade OIDC Identity Validation**
> 所有能力默认关闭；签名验证仅在显式 `OIDC_SIGNATURE_VALIDATION_ENABLED=true` 后才在 readiness 中显示 enabled。

---

## 1. 新增文件列表 (9 个)

| # | 文件 | 说明 |
|---|------|------|
| 1 | `src/open_platform/sandbox_v2/oidc_discovery.py` | OIDC Discovery + JWKS Cache 服务（fail closed / kid rotation / anti-issuer-spoof） |
| 2 | `src/open_platform/sandbox_v2/oidc_identity_validation.py` | RS256 签名验证 + Claim Validation（sub/iss/aud/exp/iat/nbf/nonce / alg=none 必拒） |
| 3 | `src/open_platform/sandbox_v2/oidc_token_exchange.py` | Token Exchange（默认关闭） + Identity Mapping |
| 4 | `src/open_platform/sandbox_v2/oidc_step21_service.py` | Step 21 orchestrator + readiness 聚合 |
| 5 | `tests/test_open_platform/oidc_step21_fixtures.py` | 测试 fixtures（RSA keypair / signed JWT / JWKS / unsigned JWT） |
| 6 | `tests/test_open_platform/test_sandbox_v2_oidc_step21_security.py` | OIDC Security Tests (11) |
| 7 | `tests/test_open_platform/test_sandbox_v2_oidc_step21_exchange_mapping.py` | Token Exchange + Identity Mapping Tests (9) |
| 8 | `tests/test_open_platform/red_team/test_sandbox_v2_red_team_oidc_step21.py` | OIDC Red-Team (8) |
| 9 | `docs/oidc-production-readiness.md` | 生产就绪文档（含未完成项诚实声明） |

## 2. 修改文件列表 (7 个)

| 文件 | 修改内容 |
|------|---------|
| `src/open_platform/sandbox_v2/config.py` | 新增 8 个 Step 21 配置字段 + `production_blockers()` 安全检查 + `load_sandbox_v2_settings()` 加载 |
| `src/open_platform/sandbox_v2/models.py` | 新增 4 个 Step 21 数据模型 + `SandboxV2OIDCValidationMode` 枚举 |
| `src/open_platform/sandbox_v2/iam.py` | `get_real_sso_readiness` 同步 signature_validation 字段；新增 `get_oidc_validation_readiness` |
| `src/open_platform/sandbox_v2/service.py` | 新增 `get_oidc_validation_readiness` + `validate_oidc_id_token` 透传 |
| `src/api/sandbox_v2.py` | 新增 2 个 API；`oidc_signature_validation` readiness 字段同步 |
| `src/api/runtime_admin_router.py` | Runtime Admin 新增 `GET /admin/runtime/oidc-validation/readiness` |
| `.env.sandbox-v2.example` | 新增 8 个 Step 21 环境变量示例 |

## 3. 新增 API (3 个)

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET  | `/api/runtime/sandbox-v2/iam/oidc/validation/readiness` | 公开 | Step 21 详细 readiness（每子能力 enabled/disabled/ready/not_ready） |
| POST | `/api/runtime/sandbox-v2/iam/oidc/validate-id-token` | 公开 | 手动验证 id_token（不持久化） |
| GET  | `/api/admin/runtime/oidc-validation/readiness` | admin | Runtime Admin OIDC Readiness |

## 4. Runtime Admin 新增项

Runtime Admin 新增 **OIDC Validation Readiness** 面板入口：
`GET /api/admin/runtime/oidc-validation/readiness`

每子能力返回 4 态状态：
- `enabled` — 已显式启用且就绪
- `disabled` — 默认关闭（绝大多数场景）
- `ready` — 子能力逻辑可用（如 identity_mapping，复用 Step 17 mapper）
- `not_ready` — 已启用但缺前置条件（如 signature 启用但无 jwks 源）

展示项：OIDC Discovery / JWKS Cache / Token Exchange / Signature Validation / Claim Validation / Identity Mapping。

## 5. OIDC Readiness 结果

默认配置（无任何环境变量）：

```
step: step21_oidc_production_validation
signature_validation: disabled
oidc_discovery:        disabled
jwks_cache:            disabled
token_exchange:        disabled
claim_validation:      disabled
identity_mapping:      ready
token_storage: false
fail_closed:    true
secure_by_default: true
```

Legacy `/iam/sso/readiness` 同步：
```
oidc_signature_validation: false  (Step 20 固定 false → Step 21 现由 OIDC_SIGNATURE_VALIDATION_ENABLED 驱动)
```

开启 `OIDC_SIGNATURE_VALIDATION_ENABLED=true` 但未配 jwks 源 → `production_blockers` 报警：
```
oidc_signature_validation_enabled=true but no jwks source configured (oidc_jwks_uri / oidc_jwks_fetch_enabled / oidc_discovery_fetch_enabled all unset)
```

## 6. 测试结果

| 套件 | 数量 | 结果 |
|------|------|------|
| Security Tests (含正向) | 11 | ✅ all pass |
| Red-Team Tests | 8 | ✅ all pass |
| Token Exchange + Mapping | 9 | ✅ all pass |
| **Step 21 小计** | **28** | ✅ **28/28 pass** |
| Step 17-20 SSO 回归 | 40 | ✅ all pass |
| SSO Red-Team 回归 | 51 | ✅ all pass |
| open_platform 全套 | 4861 pass / 59 skip / 1 fail | ⚠️ 1 fail 与 Step 21 无关（详见下） |

**1 个失败说明：** `test_step23_security_runtime.py::TestFrontendSecurityUX::test_runtime_admin_no_misleading_execution`
是预先存在的前端 UX 文本断言（要求 `frontend/app/admin/runtime/page.tsx` 含字符串
`"no remote code execution"`，但该文件用的是其它安全措辞）。**与 Step 21 完全无关**
（Step 21 不修改任何前端文件；该测试在我修改前就已不通过）。

## 7. Red-Team 结果

**8/8 passed** — 覆盖：
1. **alg=none** — 必拒（在结构校验前先 parse header，mark `alg_allowed=False`）
2. **unsigned token** — 必拒（3-segment empty signature）
3. **wrong issuer** — 必拒（精确匹配）
4. **wrong audience** — 必拒（精确匹配，支持 list aud）
5. **replay nonce** — 必拒（SHA256 hash 比对，constant-time compare）
6. **JWKS fetch failure** — fail closed（绝不退化为跳过验证）
7. **default disabled** — Step 21 service 默认 disabled 阻止任何验证
8. **no token persisted** — 验证结果结构中永不出现 access/refresh/id token

## 8. 仍未完成项（诚实声明）

| 能力 | 状态 |
|------|------|
| **MFA Federation** | ❌ 未实现（WebAuthn / TOTP / acr/amr claim 校验） |
| **SCIM** | ❌ 未实现（RFC 7643/7644 用户/组生命周期同步） |
| **Cross-Tenant Federation** | ❌ 未实现（多 IdP / Home Realm Discovery） |
| **Production IdP Certification** | ❌ 未完成（未对 Okta/Auth0/Keycloak/Azure AD 做正式互操作认证） |
| Formal OIDC Conformance Suite | ❌ 未完成（OpenID Certification） |
| Token Revocation / Back-Channel Logout | ❌ 未实现（RFC 8414 / RFC 4628） |
| HSM/KMS signing key custody | ❌ 未集成（签名 key 由 IdP 保管，本服务只验签） |

## 9. Step 22 建议

按优先级：

1. **MFA Federation** — 集成 WebAuthn / TOTP 二因子；OIDC `acr` / `amr` claim 强制校验
2. **SCIM Provisioning** — JIT 之外的批量用户/组同步 + 生命周期审计
3. **Cross-Tenant Federation** — 多 IdP 路由 + Home Realm Discovery
4. **Production IdP Certification** — Okta / Auth0 / Keycloak / Azure AD 互操作测试套件
5. **Token Revocation / Back-Channel Logout** — RFC 8414 / RFC 4628
6. **Formal OIDC Conformance Suite** — OpenID Certification

---

## 边界遵守

✅ **未实现**（按 spec 要求）：
- ❌ 用户密码登录
- ❌ 自定义 IdP
- ❌ Token 持久化（`token_storage=false` 永远）
- ❌ Refresh Token 存储（`refresh_token_persisted=false` 永远）
- ❌ 自动信任任何 Issuer（issuer 必须精确匹配配置）

✅ **保持不变**（按 spec 要求）：
- ✅ `default deny` — 所有子服务默认关闭
- ✅ `fail closed` — JWKS/Discovery 失败绝不退化为跳过验证
- ✅ `audit first` — 验证结果摘要写入审计（不含 token）
- ✅ `secure by default` — alg=none 必拒 / kid 必填 / issuer 精确匹配 / nonce replay 必拒
- ✅ 所有新增能力默认关闭（`signature_validation_enabled=false` 等）

✅ **不破坏现有结构**（按 spec 要求）：
- ✅ 未重构项目
- ✅ 未删除已有功能（Step 17-20 全部回归通过）
- ✅ 未修改 Runtime Governance 边界（仅在 Runtime Admin 新增展示项）
- ✅ 未引入真实用户数据
- ✅ 未降低现有安全默认关闭策略
