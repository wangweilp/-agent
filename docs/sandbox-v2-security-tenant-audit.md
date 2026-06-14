# Sandbox v2 — Security, Tenant Isolation & Audit

**版本**: Step 14  
**最后更新**: 2026-06-13

---

## 一、Step 14 目标

为 Sandbox v2 增加权限、多租户隔离和审计强化：
- Security Context
- RBAC / Scope 权限引擎
- Organization / Workspace 边界隔离
- Audit hash chain (append-only)
- Evidence bundle (redacted export)
- Runtime Admin security dashboard

---

## 二、Security Context

| 字段 | 说明 |
|------|------|
| `principal_id` | 身份标识 |
| `principal_type` | user / api_key / service_account / worker / admin / system / anonymous |
| `roles` | 角色列表 (owner, admin, developer, operator, auditor, viewer, worker, service) |
| `scopes` | API key scope 白名单 |
| `organization_id` | 所属组织 |
| `workspace_id` | 所属工作区 |

---

## 三、Role / Scope 权限矩阵

| 角色 | create | read | list | update | delete | execute | cancel | kill | review | approve | admin |
|------|--------|------|------|--------|--------|---------|--------|------|--------|---------|-------|
| owner | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| admin | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| developer | ✓ | ✓ | ✓ | — | — | — | — | — | — | — | — |
| operator | — | ✓ | ✓ | — | — | ✓ | ✓ | ✓ | — | — | — |
| auditor | — | ✓ | ✓ | — | — | — | — | — | — | — | — |
| viewer | — | ✓ | ✓ | — | — | — | — | — | — | — | — |
| worker | — | ✓ | — | ✓ | — | ✓ | — | — | — | — | — |

API key scope: `admin:*` (full), `sandbox:*` (read/list/create/cancel), `sandbox:{type}:read` (read only)

---

## 四、Organization / Workspace 隔离

- 资源必须绑定 `organization_id` 和 `workspace_id`
- Cross organization → 拒绝
- Cross workspace → 拒绝
- System principal → 允许（必须写审计记录）
- Admin 仅限同 organization

---

## 五、Audit Hash Chain

- 每条 audit event 包含 `previous_hash` → `event_hash`
- SHA256 基于稳定 JSON payload
- `verify_audit_chain()` 检查链完整性
- Tamper detection：hash 不匹配或 previous_hash 断链
- Append-only：已创建事件不可修改

---

## 六、Evidence Bundle

- 打包同 organization/workspace 的 audit events + resource refs
- `redacted=true`（敏感字段自动脱敏）
- `bundle_hash` 可验证
- 跨租户资源不能打包

---

## 七、敏感信息脱敏

自动脱敏的 key 前缀：
- password, secret, token, key, credential, dsn
- SANDBOX_V2_POSTGRES_DSN, SANDBOX_V2_REDIS_URL
- SANDBOX_V2_MINIO_ACCESS_KEY, SANDBOX_V2_MINIO_SECRET_KEY

---

## 八、Runtime Admin 使用

Dashboard → Security & Audit 分区：
1. **Security Readiness** — 查看安全能力状态
2. **Access Decision Tester** — 测试权限
3. **Audit Events** — 浏览和筛选审计事件
4. **Evidence Bundles** — 查看和导出证据包

---

## 九、当前限制

| 限制 | 说明 |
|------|------|
| 外部 IAM | 未接入 |
| SSO | 未接入 |
| Legacy endpoint | enforcement incremental |
| 生产级策略管理 UI | 未实现 |
| 跨服务审计聚合 | 未实现 |
| 数据脱敏 | 仅 metadata 级别 |
