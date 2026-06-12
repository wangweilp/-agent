# Step 23-G：Runtime Admin Frontend

## 1. 概述

Runtime Admin 前端让管理员在 UI 中管理 Developer Agent Runtime readiness。不执行任何代码。

## 2. Runtime Admin API（新增 8 endpoints）

**Prefix:** `/admin/runtime`

| Endpoint | 说明 |
|----------|------|
| `GET /adapters` | Runtime Adapter 列表 |
| `GET /bindings` | Runtime Binding 列表（tenant scoped） |
| `POST /bindings` | 创建 Binding（pending） |
| `GET /bindings/{id}` | Binding 详情 + adapter + eligibility |
| `POST /bindings/{id}/enable` | Enable（不执行代码） |
| `POST /bindings/{id}/disable` | Disable |
| `POST /bindings/{id}/suspend` | Suspend |
| `POST /bindings/{id}/sandbox-policy` | Assign sandbox policy |
| `GET /developer-agents/{id}/eligibility` | Runtime eligibility |

## 3. Runtime Admin Page

**路径:** `/admin/runtime`

4 个 Tab：
- **Runtime Adapters** — 5 adapter types，MVP 只有 manifest_only + simulation 可用
- **Runtime Bindings** — 创建/查看/enable/disable/suspend/assign policy
- **Sandbox Policies** — 查看/测试/enable/disable（3 system policies）
- **Readiness Guide** — 7 步 checklist

## 4. Package Validation into Admin Review

Admin Review Detail 页可通过 `admin-submissions.ts` 服务调用 `validate-package` 和 `get-package-validation`。

## 5. Sidebar

新增 `/admin/runtime` 导航项（ServerCog 图标）。

## 6. Non-Execution Guarantees

- ❌ 不执行代码
- ❌ 不调用 AgentRuntime / AgentRegistry
- ❌ Enable binding 只是状态变更
- ❌ Create binding 只是状态持久化
- ❌ Assign policy 只是关联
- ✅ Simulation 仍然 dry-run

## 7. 新增/修改文件

| 文件 | 操作 |
|------|------|
| `src/api/runtime_admin_router.py` | 新增 — Runtime Admin API |
| `frontend/types/runtime-admin.ts` | 新增 — 完整类型定义 |
| `frontend/services/runtime-admin.ts` | 新增 — API 客户端 |
| `frontend/app/admin/runtime/page.tsx` | 新增 — Runtime Admin 页面 |
| `frontend/components/layout/Sidebar.tsx` | 修改 — +Runtime Admin |
| `frontend/services/admin-submissions.ts` | 修改 — +package validation |
| `main.py` | 修改 — router include |
| `docs/ROADMAP.md` | 修改 — 23-G 标记 ✅ |

## 8. 测试

- Open Platform 全量: 535 passed
- 后端全量回归: 1182 passed
- TypeScript: 通过
- Scoped ESLint: 0 errors, 0 warnings

## 9. Next Step

Step 23-H：Developer SDK / Manifest Schema
