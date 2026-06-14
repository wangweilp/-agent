# Sandbox v2 Real OIDC / SAML Login Flow (Step 20)

## 1. Step 20 目标

在 Step 17 IAM/SSO 基础上增加真实 OIDC/SAML 登录闭环:
- OIDC Authorization Code Flow
- SAML SP-Initiated Flow
- State/Nonce/PKCE 防护
- SSO Session 管理

**所有真实登录能力默认关闭。**

## 2. OIDC Authorization Code Flow

- `SandboxV2OIDCFlowService` 管理完整 flow
- Authorization URL 生成（不含 client_secret）
- Callback 处理（GET + POST）
- State 一次性消费 + 过期检查
- Nonce 绑定与验证
- PKCE S256 支持
- Token exchange（默认关闭，需显式启用）
- id_token claims 验证（iss/aud/exp/iat/alg/nonce/email_verified）
- 签名验证返回 unavailable（需要 python-jose 等依赖）

## 3. SAML SP-Initiated Flow

- `SandboxV2SAMLFlowService` 管理完整 flow
- AuthnRequest 生成
- RelayState hash 存储
- ACS callback 处理
- XXE 防护（默认开启）
- SAMLResponse 大小限制（默认 128KB）
- 未签名 response/assertion 默认拒绝
- Claims 提取与 redaction

## 4. 安全原则

- 默认 fail-closed
- alg=none 拒绝
- issuer/audience 不匹配拒绝
- 过期 token 拒绝
- email_verified=false 拒绝
- 不存 token/secret/SAMLResponse
- State/nonce/verifier 只存 hash
- 所有 callback 写 audit

## 5. 运行脚本/测试

```bash
python scripts/check_sandbox_v2_real_sso.py
python -m pytest tests/test_open_platform/test_sandbox_v2_oidc_flow.py -q
python -m pytest tests/test_open_platform/red_team/test_sandbox_v2_red_team_real_sso.py -q
```

## 6. 当前限制

- 签名验证 unavailable（需要安全 JWT/SAML 库）
- 未做 SCIM
- 未做主系统 session 深度集成

## 7. 下一步

- Step 21: 真实 Prometheus/Grafana/OTel Collector 集成
- Step 22: 长期 Soak Test 与生产 SLO 门禁
