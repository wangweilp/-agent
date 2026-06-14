# Sandbox v2 IAM / SSO Integration (Step 17)

## 1. Step 17 目标

为 Sandbox v2 增加外部 IAM / SSO 集成基础，包括：
- OIDC / SAML 配置模型
- 身份声明映射（Claim Mapping）
- 外部用户到 Security Context 的转换
- 角色与 Scope 映射
- JIT 用户/主体绑定
- 租户边界校验
- SSO 审计事件
- Runtime Admin 展示
- 默认 skip 的集成测试和文档

**本步骤不要求接入真实企业 IdP，不要求真实登录流程上线，不替换现有登录系统。**

## 2. IAM / SSO 当前能力

| 能力 | 状态 |
|------|------|
| IAM Provider Config 模型 | ✅ Ready |
| OIDC Provider Skeleton | ✅ Ready |
| SAML Provider Skeleton | ✅ Ready |
| Mock IAM Provider | ✅ Ready |
| Claim Mapping | ✅ Ready |
| Role / Scope Mapping | ✅ Ready |
| Tenant Boundary Check | ✅ Ready |
| Security Audit (hash chain) | ✅ Ready |
| Runtime Admin Dashboard | ✅ Ready |
| Red-Team IAM/SSO Tests | ✅ 26 tests |
| Integration Tests | ✅ Default skip |
| Real OIDC Login | ❌ Not yet |
| Real SAML Login | ❌ Not yet |
| Token Storage | ❌ Never |
| SCIM | ❌ Not yet |

## 3. 为什么默认 disabled

- IAM_ENABLED=false: 未配置外部 IdP 时不干扰现有登录
- SSO_ENABLED=false: 真实 OIDC/SAML 登录未实现
- OIDC_DISCOVERY_ENABLED=false: 禁止外网 discovery 调用
- SAML_METADATA_DOWNLOAD_ENABLED=false: 禁止外网 metadata 下载
- Token 一律不存储

**所有开关默认 fail-closed。**

## 4. OIDC Skeleton 说明

`OIDCProviderSkeleton`:
- 只做配置校验 (issuer, client_id)
- 不访问 discovery URL
- 不下载 JWKS
- 不验证真实 token
- discovery_enabled=false → 返回 preflight_only
- 用户传 token → 拒绝并提示

## 5. SAML Skeleton 说明

`SAMLProviderSkeleton`:
- 只做 metadata path 校验
- 不下载 metadata URL
- 不解析真实 SAML Response
- metadata_download_enabled=false → 不联网
- 用户传 SAMLResponse → 拒绝并提示

## 6. Mock Provider 用途

`MockIAMProvider`:
- 仅用于测试和本地模拟
- 接收安全 fixture claims
- 不访问外网
- 不验证真实签名
- 不接受 token
- 验证 claim mapping、role mapping、tenant boundary、audit

## 7. Claim Mapping 规则

1. 缺 subject → 拒绝
2. 缺 issuer → 拒绝
3. email 未验证且 require_verified_email=true → 拒绝
4. email domain 不在 allowed_domains → 拒绝
5. tenant claim 与 organization/workspace 不匹配 → 拒绝
6. unknown group → 不给高权限
7. default_role 不能是 owner/admin
8. raw claims 必须 redacted
9. 不存 token
10. 不泄露 secret

## 8. Role / Scope Mapping 规则

- external_group → sandbox_role
- external_claim → sandbox_role
- 支持映射到 scopes（如 read, write, cancel, kill）
- 所有映射可审计
- 未映射的 group 默认 fallback 到 default_role（仅限 viewer/auditor/developer/operator）

## 9. JIT Provisioning

- 默认 false
- 开启时也只创建/绑定 sandbox principal 记录
- 不创建真实系统用户

## 10. 不存 token / 不回显 secret 的原则

- client_secret: 仅存储 secret_ref，不回显明文
- access_token/id_token/refresh_token: 一律拒绝，不存储
- SAMLResponse: 一律拒绝，不解析
- Claims 中的 token keys: redacted
- API response: client_id masked (前4+后4字符)
- Audit: 不包含任何 secret/token

## 11. 运行脚本

```bash
python scripts/check_sandbox_v2_iam_sso.py
```

## 12. 运行测试

```bash
# IAM 单元测试
python -m pytest tests/test_open_platform/test_sandbox_v2_iam_*.py -q

# Red-Team IAM/SSO 测试
python -m pytest tests/test_open_platform/red_team/test_sandbox_v2_red_team_iam_sso.py -q

# 集成测试 (默认 skip)
python -m pytest tests/test_open_platform/integration_iam -q
```

## 13. 当前限制

- 未实现真实 OIDC code flow
- 未实现真实 SAML ACS
- 未接外部 IdP
- 未接 SCIM
- 未实现完整会话管理

## 14. 下一步建议

- Step 18: Prometheus / Grafana / OpenTelemetry 集成
- Step 19: 真实生产压测与 SLO
- Step 20: 真实 OIDC/SAML 登录闭环
