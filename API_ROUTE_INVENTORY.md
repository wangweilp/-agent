# API Route Inventory

| Frontend call | FastAPI route | Connected | Rewrite | Fix |
| --- | --- | --- | --- | --- |
| `/imports` | `/imports` | Yes | Optional | Canonical import route. |
| `/import` | `/import` | Yes | Optional | Kept as legacy alias for old pages/scripts. |
| `/api/rbac/users` | `/api/rbac/users` | Yes, auth required | Yes | Next rewrite added for same-origin deployments. |
| `/api/rbac/roles` | `/api/rbac/roles` | Yes, auth required | Yes | Next rewrite added. |
| `/api/admin/config` | `/api/admin/config` | Yes, auth required | Yes | Returns backend and production backend config keys. |
| `/api/admin/production-backends` | `/api/admin/production-backends` | Yes, auth required | Yes | New production readiness health endpoint. |
| `/api/runtime/adapters` | `/admin/runtime/adapters` | Yes, auth required | `/api/runtime/:path*` | Runtime Admin defaults to same-origin proxy when `NEXT_PUBLIC_API_URL` is unset. |
| `/api/runtime/governance/summary` | `/admin/runtime/governance/summary` | Yes, auth required | `/api/runtime/:path*` | New read-only governance summary endpoint. |
| `/api/sandbox-policies` | `/admin/sandbox-policies` | Yes, auth required | `/api/sandbox-policies/:path*` | Runtime Admin sandbox policy calls can use same-origin proxy. |
| `/developers/me` | `/developers/me` | Yes, auth required | `/api/developer/:path*` | Rewrite added for same-origin compatibility. |
| `/agent-marketplace/categories` | `/agent-marketplace/categories` | Yes, auth may be required by middleware | `/api/marketplace/:path*` | Rewrite added for same-origin compatibility. |

Notes:

- `NEXT_PUBLIC_API_URL` can still force direct frontend-to-FastAPI calls when needed.
- Next rewrites are now present for `/api/rbac/...`, `/api/runtime/...`, `/api/sandbox-policies/...`, `/api/admin/...`, `/api/developer/...`, and `/api/marketplace/...`.
- Protected routes returning `401` or `403` are considered connected for smoke checks; `404` indicates route drift.
