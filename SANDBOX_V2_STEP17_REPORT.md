# Sandbox v2 Step 17 Report — IAM / SSO 集成基础

**日期:** 2026-06-13
**状态:** Complete

## 新增文件

| 文件 | 说明 |
|------|------|
| `src/open_platform/sandbox_v2/iam_mapping.py` | IAM Claim Mapper — 声明映射、角色映射、租户校验 |
| `src/open_platform/sandbox_v2/iam_provider.py` | IAM Provider Protocol + Disabled/Mock/OIDC/SAML Skeletons |
| `src/open_platform/sandbox_v2/iam.py` | IAM Service — 集成服务层 |
| `tests/test_open_platform/test_sandbox_v2_iam_mapping.py` | Claim Mapper 测试 (22 tests) |
| `tests/test_open_platform/test_sandbox_v2_iam_provider.py` | Provider 测试 (17 tests) |
| `tests/test_open_platform/test_sandbox_v2_iam_service.py` | Service 测试 (10 tests) |
| `tests/test_open_platform/test_sandbox_v2_iam_api.py` | API 测试 (15 tests) |
| `tests/test_open_platform/test_sandbox_v2_iam_store.py` | Store 测试 (10 tests) |
| `tests/test_open_platform/red_team/test_sandbox_v2_red_team_iam_sso.py` | Red-Team 测试 (26 tests) |
| `tests/test_open_platform/integration_iam/test_sandbox_v2_oidc_sso_integration.py` | 集成测试 (6 tests, default skip) |
| `scripts/check_sandbox_v2_iam_sso.py` | IAM/SSO 检查脚本 |
| `docs/sandbox-v2-iam-sso.md` | IAM/SSO 文档 |

## 修改文件

| 文件 | 修改内容 |
|------|----------|
| `src/open_platform/sandbox_v2/config.py` | 新增 14 个 IAM/SSO 配置项 |
| `src/open_platform/sandbox_v2/models.py` | 新增 5 个枚举 + 6 个数据模型 + 2 个审计事件类型 + 5 个资源类型 |
| `src/open_platform/sandbox_v2/store.py` | 新增 13 个 IAM Store 接口方法 |
| `src/adapters/sqlite_sandbox_v2_store.py` | 新增 5 张 IAM 表 + 13 个方法实现 + row converters |
| `src/open_platform/sandbox_v2/service.py` | 新增 IAM service 聚合方法 |
| `src/api/sandbox_v2.py` | 新增 10 个 IAM API 端点 + IAM readiness 字段 |
| `.env.sandbox-v2.example` | 新增 IAM/SSO 环境变量模板 |
| `docs/sql/sandbox_v2_postgres_schema.sql` | 新增 5 张 IAM 表 |
| `frontend/types/runtime-admin.ts` | 新增 7 个 IAM TypeScript 类型 |
| `frontend/services/runtime-admin.ts` | 新增 10 个 IAM API client 方法 |

## 新增 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/runtime/sandbox-v2/iam/readiness` | IAM/SSO readiness |
| POST | `/api/runtime/sandbox-v2/iam/provider-configs` | 创建 provider config |
| GET | `/api/runtime/sandbox-v2/iam/provider-configs` | 列出 provider configs |
| GET | `/api/runtime/sandbox-v2/iam/provider-configs/{id}` | 获取 provider config |
| POST | `/api/runtime/sandbox-v2/iam/role-mappings` | 创建 role mapping |
| GET | `/api/runtime/sandbox-v2/iam/role-mappings` | 列出 role mappings |
| POST | `/api/runtime/sandbox-v2/iam/simulate-login` | 模拟 SSO 登录 |
| GET | `/api/runtime/sandbox-v2/iam/external-identities` | 列出 external identities |
| GET | `/api/runtime/sandbox-v2/iam/mapping-decisions` | 列出 mapping decisions |
| GET | `/api/runtime/sandbox-v2/iam/sso-simulations` | 列出 SSO simulation results |

## IAM / SSO Readiness

```json
{
  "iam_provider_config": true,
  "sso_config_model": true,
  "oidc_provider_skeleton": true,
  "saml_provider_skeleton": true,
  "mock_iam_provider": true,
  "claim_mapping": true,
  "role_scope_mapping": true,
  "jit_provisioning": false,
  "external_iam_enabled": false,
  "sso_enabled": false,
  "real_oidc_login": false,
  "real_saml_login": false,
  "token_storage": false,
  "token_introspection": false,
  "iam_safe_mode": true
}
```

## Mock Claims Mapping 结果

```
iam_enabled: false
sso_enabled: false
mock_provider_available: true
claim_mapping_ready: true
role_scope_mapping_ready: true
safe_mode: true
blockers: []
warnings: []
```

## 安全验证

| 验证项 | 状态 |
|--------|------|
| IAM 默认 disabled | ✅ |
| SSO 默认 disabled | ✅ |
| OIDC discovery 默认 disabled | ✅ |
| SAML metadata download 默认 disabled | ✅ |
| Token 不存储 | ✅ |
| Client secret 不泄露 | ✅ |
| Cross-tenant mapping 拒绝 | ✅ |
| Email 未验证拒绝 | ✅ |
| Email domain 白名单拒绝 | ✅ |
| Unknown group 不给高权限 | ✅ |
| Fake admin group 拒绝 | ✅ |
| Default role 不能是 admin/owner | ✅ |
| Malformed body 不返回 500 | ✅ |
| SAMLResponse 不解析 | ✅ |
| Audit hash chain 可验证 | ✅ |

## 测试结果

### IAM 单元测试
```
74 passed in 2.72s
```

### Red-Team IAM/SSO 测试
```
26 passed in 0.44s
```

### 集成测试 (默认 skip)
```
6 skipped in 0.08s
```

### 已有测试 (Step 1-16)
```
- Access Policy: 46 passed
- Security Audit: (included above)
- Tenant Isolation: (included above)
- Models: 87 passed
- Service: 26 passed
- Policy Engine: (included above)
```

### 前端 Build
```
npm run build: SUCCESS
```

## 当前仍缺什么

| 项目 | 计划 |
|------|------|
| 真实 OIDC code flow | Step 20 |
| 真实 SAML ACS | Step 20 |
| SCIM | Future |
| 完整会话管理 | Future |
| 外部 IdP 生产验证 | Step 20 |

## 下一步建议

1. **Step 18:** Prometheus / Grafana / OpenTelemetry 集成
2. **Step 19:** 真实生产压测与 SLO
3. **Step 20:** 真实 OIDC/SAML 登录闭环
