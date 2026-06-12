# Step 23-B：API Key Auth Middleware + Scope Enforcement

## 1. 概述

Step 23-B 让 API Key 从"只存储不用"升级为"可用于受控 Developer API 调用"。API Key 认证通过 `X-Cognitive-API-Key` header 完成，不与现有 JWT `Authorization: Bearer` 冲突。

## 2. Header

```
X-Cognitive-API-Key: cos_dev_<prefix>_<secret>
```

推荐使用此自定义 header 而非 `Authorization: Bearer` 格式，原因：
- 不与 JWT Bearer 冲突
- 语义明确——这是 API Key 不是 JWT
- 可同时发送 JWT 和 API Key（浏览器场景）
- FastAPI 解析简单

## 3. DeveloperApiPrincipal

```python
@dataclass
class DeveloperApiPrincipal:
    developer_id: str
    user_id: str
    tenant_id: str
    api_key_id: str
    key_prefix: str
    scopes: list[str]
    auth_type: str = "developer_api_key"
```

**关键约束**：
- 不包含 `role`（不是 WorkspaceRole）
- 不包含 `is_super_admin`（永远 False）
- 不包含 `email`
- 不包含 `raw_key` 或 `key_hash`
- `to_dict()` 不泄露敏感信息

## 4. Allowed Scopes

| Scope | 用途 |
|-------|------|
| `developer:read` | 读取 developer profile |
| `developer:write` | 更新 developer profile |
| `api_keys:read` | 列出 API Keys |
| `api_keys:write` | 创建/撤销 API Keys |
| `submissions:read` | 读取 submissions |
| `submissions:write` | 创建/编辑/撤回 submissions |
| `submissions:submit` | 提交审核 |
| `marketplace:read` | 浏览 Marketplace |
| `agent:simulate` | 触发仿真 |
| `agent:execute:simulation` | 仿真执行 |
| `usage:read` | 查看用量 |

**Legacy aliases**（已弃用，向后兼容）:
- `agent:read` → `submissions:read`
- `agent:write` → `submissions:write`
- `agent:submit` → `submissions:submit`

## 5. Forbidden Scopes

以下 scopes 在 API Key 创建时被硬拒绝：

- `admin:review`
- `admin:publish`
- `tenant:admin`
- `workspace:admin`
- `org:admin`
- `billing:write`
- `revenue:write`
- `system:super_admin`
- `runtime:unsafe_execute`
- `agent:execute:unsafe`

## 6. JWT-only Endpoints

以下端点保留 JWT-only，不接受 API Key：

| 端点 | 原因 |
|------|------|
| `POST /developers/register` | 账号创建需 JWT |
| `PATCH /developers/me` | Profile 修改需 JWT |
| `POST /developers/me/verify-request` | 验证请求需 JWT |
| `POST /developers/api-keys` | 创建 API Key 需 JWT |
| `DELETE /developers/api-keys/{id}` | 撤销 API Key 需 JWT |

## 7. API-Key-Enabled Endpoints

以下端点支持 JWT 或 API Key：

| 端点 | Required Scope |
|------|---------------|
| `GET /developers/me` | `developer:read` |
| `GET /developers/api-keys` | `api_keys:read` |
| `POST /developers/agents` | `submissions:write` |
| `GET /developers/agents` | `submissions:read` |
| `GET /developers/agents/{id}` | `submissions:read` |
| `PATCH /developers/agents/{id}` | `submissions:write` |
| `POST /developers/agents/{id}/validate` | `submissions:read` |
| `POST /developers/agents/{id}/submit` | `submissions:submit` |
| `POST /developers/agents/{id}/withdraw` | `submissions:write` |

## 8. Admin / Publish Denial

- API Key **永远不可**访问 Admin Review API（`/admin/agent-submissions`）
- Admin router 仍使用 `require_auth`（JWT only）
- `require_auth` 对无 JWT 的 API Key 请求返回 401
- API Key **永远不可**publish

## 9. Scope Enforcement

- API Key 创建时 scope 白名单校验（validate_api_key_scopes）
- Endpoint 层面检查 required scope
- 缺少 scope → 403 `{"message": "Insufficient API key scope", "required_scopes": [...]}`
- 禁止 wildcard（`*`、`admin:*`）
- Scope 去重 + 排序 + legacy alias resolution

## 10. Usage Metadata Safety

- 每次 API Key 认证记录 `DEVELOPER_API_KEY_AUTH` usage event
- metadata 包含：developer_id, api_key_id, key_prefix, auth_type, endpoint, method
- **不包含**：raw_key, key_hash, request body
- Usage 写入失败仅 warning，不影响主流程

## 11. Security Guarantees

- ✅ API Key 不能调用 Admin Review API
- ✅ API Key 不能 publish
- ✅ API Key 不能创建或撤销 API Key
- ✅ API Key 不能绕过 tenant isolation
- ✅ API Key 不能拥有 admin/super_admin role
- ✅ API Key 不能执行 Runtime
- ✅ raw_key/key_hash 不泄露
- ✅ scopes 必须显式 enforcement
- ✅ wildcard 禁止

## 12. 测试

- 新增 `tests/test_open_platform/test_api_key_auth.py` — 44 tests
- Open Platform 全量：290 passed（246 + 44）
- 后端全量回归：937 passed（893 + 44）
- 零回归

## 13. Known Issues

| # | 问题 | 说明 |
|---|------|------|
| 1 | API Key rate limit 未实现 | 调用频率无限制 |
| 2 | Marketplace:read 暂未启用 | Marketplace API 本阶段不接入 API Key |
| 3 | API Key 不能调用 agent 仿真 | Simulation Runtime 尚未实现（Step 23-D） |

## 14. 新增/修改文件

| 文件 | 操作 |
|------|------|
| `src/open_platform/developer.py` | 修改 — 新增 scope constants + validation helpers |
| `src/open_platform/api_auth.py` | 新增 — DeveloperApiPrincipal |
| `src/core/usage.py` | 修改 — 新增 DEVELOPER_API_KEY_AUTH |
| `src/api/developer_api_auth.py` | 新增 — API Key auth dependency |
| `src/api/developer_router.py` | 修改 — 双认证模式 |
| `tests/test_open_platform/test_api_key_auth.py` | 新增 — 44 tests |
| `tests/test_open_platform/test_developer_api.py` | 修改 — get_token_payload override |
| `tests/test_open_platform/test_open_platform_security.py` | 修改 — get_token_payload override |
| `docs/STEP23B_API_KEY_AUTH.md` | 新增 — 本文档 |

## 15. Next Step

Step 23-C：Runtime Adapter Domain Model + Store
