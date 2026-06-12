# Step 23-F：Package Validation Pipeline

## 1. 概述

静态 Package Metadata 验证流水线，辅助 Admin Review 判断提交的 Agent 包是否具备基本安全元数据、URL 合规性和供应链风险提示。

**不下载，不解压，不执行，不联网。**

## 2. Static Checks (19 codes)

| Code | 说明 |
|------|------|
| URL_PRESENT | package_url 是否存在 |
| URL_FORMAT_VALID | URL 格式校验 |
| HTTPS_REQUIRED | 仅允许 HTTPS |
| DOMAIN_ALLOWED | 域名在 allowlist 中 |
| DOMAIN_BLOCKED | 域名在 blocklist 中 |
| CHECKSUM_DECLARED | sha256/sha384/sha512 |
| SIGNATURE_DECLARED | minisign/cosign/gpg |
| PACKAGE_NAME_MATCH | 与 manifest.name 一致 |
| PACKAGE_VERSION_MATCH | 与 manifest.version 一致 |
| RUNTIME_TYPE_SUPPORTED | 仅 manifest_only |
| DEPENDENCIES_DECLARED | 依赖声明 |
| LICENSE_DECLARED | 许可证声明 |
| SECURITY_CONTACT_DECLARED | 安全联系 |
| SANDBOX/NETWORK/USER_DATA | 安全披露 |
| PACKAGE_NOT_DOWNLOADED | 静态验证 marker |
| PACKAGE_NOT_EXECUTED | 静态验证 marker |

## 3. URL Policy

- 仅 HTTPS
- 禁止 localhost / 127.0.0.1 / 0.0.0.0 / ::1 / metadata.google.internal / 169.254.169.254
- 禁止 private IP / loopback / link-local / multicast / unspecified
- 不做 DNS 解析，不发 HTTP 请求

## 4. API Endpoints

**POST /admin/agent-submissions/{id}/validate-package**
**GET /admin/agent-submissions/{id}/package-validation**

权限：admin/owner/super_admin only（JWT only）。

## 5. Non-Execution Guarantees

- ❌ 不下载 / 不解压 / 不执行 package_url
- ❌ 不联网 / 不读文件 / 不读 secrets
- ❌ 不调用 AgentRuntime / AgentRegistry
- ❌ 不修改 submission status
- ❌ 不 create review record / 不 approve / 不 publish

## 6. 测试

- Package Validation 专项：58 tests
- Open Platform 全量：518 passed（460 + 58）
- 后端全量回归：1165 passed（1107 + 58）

## 7. 新增/修改文件

| 文件 | 操作 |
|------|------|
| `src/open_platform/package_validation.py` | 新增 |
| `src/adapters/package_validation_store.py` | 新增 |
| `src/open_platform/package_validation_service.py` | 新增 |
| `src/api/admin_submission_router.py` | 修改（+2 endpoints） |
| `src/core/usage.py` | 修改（+1 UsageResource） |
| `main.py` | 修改（store + service bootstrap） |
| `tests/test_open_platform/test_package_validation.py` | 新增 |
| `docs/ROADMAP.md` | 修改 |

## 8. Next Step

Step 23-G：Runtime Admin Frontend
