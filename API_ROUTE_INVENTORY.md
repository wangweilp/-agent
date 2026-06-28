# Zhiwei OS — API Route Inventory

> Phase 3 deliverable: Frontend-to-Backend communication pipe alignment.
> Generated: 2026-06-26 | Baseline: v1.0

## 1. Next.js Rewrite Proxy Rules (next.config.js)

| # | Frontend Source Path | Backend Destination | Rewrite Type | Notes |
|---|---|---|---|---|
| 1 | `/api/rbac/:path*` | `${API_TARGET}/api/rbac/:path*` | Direct passthrough | Same prefix on both sides |
| 2 | `/api/runtime/:path*` | `${API_TARGET}/admin/runtime/:path*` | Prefix transform | `/api` → `/admin` (control plane) |
| 3 | `/api/sandbox-policies/:path*` | `${API_TARGET}/admin/sandbox-policies/:path*` | Prefix transform | `/api` → `/admin` (control plane) |
| 4 | `/api/admin/:path*` | `${API_TARGET}/api/admin/:path*` | Direct passthrough | Same prefix on both sides |
| 5 | `/api/developer/:path*` | `${API_TARGET}/developers/:path*` | Singular → plural | `/api/developer` → `/developers` |
| 6 | `/api/marketplace/:path*` | `${API_TARGET}/agent-marketplace/:path*` | Rename | `/api/marketplace` → `/agent-marketplace` |
| 7 | `/api/imports/:path*` | `${API_TARGET}/imports/:path*` | Prefix strip | Primary plural route |
| 8 | `/api/import/:path*` | `${API_TARGET}/imports/:path*` | Alias → plural | Legacy singular alias to plural backend (Phase 3 fix) |

## 2. Service Layer API Inventory

### 2.1 Core API Service (`services/api.ts`)

Uses centralized `API_BASE_URL` constant (exported) with `NEXT_PUBLIC_API_URL` env fallback. All requests go through unified `request()` / `apiFetch()` helpers with auth header injection. The exported `API_BASE_URL` is the single source of truth — display-only consumers (e.g. `admin/deployment/page.tsx` anchor hrefs) import it rather than re-declaring a hardcoded fallback.

| Frontend Caller | Frontend Request Path | Proxy Rewrite Rule | Backend FastAPI Target | Status |
|---|---|---|---|---|
| `services/api.ts` → `api.chat()` | `/chat` | (none — direct) | `/chat` | OK |
| `services/api.ts` → `api.chatStream()` | `/chat/stream` | (none — direct) | `/chat/stream` | OK |
| `services/api.ts` → `api.health()` | `/health` | (none — direct) | `/health` | OK |
| `services/api.ts` → `api.memory.*` | `/memory`, `/memory/:id`, `/memory/search`, `/memory/merge` | (none — direct) | `/memory/*` | OK |
| `services/api.ts` → `api.reflection.list()` | `/reflection` | (none — direct) | `/reflection` | OK |
| `services/api.ts` → `api.tools.*` | `/tools`, `/tools/:name` | (none — direct) | `/tools/*` | OK |
| `services/api.ts` → `api.upload()` | `/upload` | (none — direct) | `/upload` | OK |
| `services/api.ts` → `api.dashboard.*` | `/dashboard/*` | (none — direct) | `/dashboard/*` | OK |
| `services/api.ts` → `api.timeline.*` | `/timeline/*` | (none — direct) | `/timeline/*` | OK |
| `services/api.ts` → `api.graph.*` | `/graph`, `/graph/entity/:name`, `/graph/subgraph` | (none — direct) | `/graph/*` | OK |
| `services/api.ts` → `api.audio.*` | `/audio/*` | (none — direct) | `/audio/*` | OK |
| `services/api.ts` → `api.video.*` | `/video/*` | (none — direct) | `/video/*` | OK |
| `services/api.ts` → `api.auth.*` | `/auth/*` | (none — direct) | `/auth/*` | OK |
| `services/api.ts` → `api.workspace.*` | `/workspace/:id/*`, `/notifications/*` | (none — direct) | `/workspace/*`, `/notifications/*` | OK |
| `services/api.ts` → `api.imports.*` | `/imports`, `/imports/:id`, `/imports/:id/retry` | (none — direct) | `/imports/*` | OK — plural standardized |
| `services/api.ts` → `api.sync.*` | `/sync/*` | (none — direct) | `/sync/*` | OK |
| `services/api.ts` → `api.billing.*` | `/billing/*` | (none — direct) | `/billing/*` | OK |
| `services/api.ts` → `api.subscription.*` | `/subscription/*` | (none — direct) | `/subscription/*` | OK |
| `services/api.ts` → `api.usage.*` | `/usage/*` | (none — direct) | `/usage/*` | OK |
| `services/api.ts` → `api.tenant.*` | `/tenants/*` | (none — direct) | `/tenants/*` | OK |
| `services/api.ts` → `api.growth.*` | `/growth/*` | (none — direct) | `/growth/*` | OK |
| `services/api.ts` → `api.analytics.*` | `/analytics/*` | (none — direct) | `/analytics/*` | OK |
| `services/api.ts` → `api.alerts.*` | `/alerts/*` | (none — direct) | `/alerts/*` | OK |
| `services/api.ts` → `api.reports.*` | `/reports/*` | (none — direct) | `/reports/*` | OK |
| `services/api.ts` → `api.rbac.*` | `/api/rbac/*` | Rule #1 | `/api/rbac/*` | OK — proxied |
| `services/api.ts` → `api.admin.*` | `/api/admin/*` | Rule #4 | `/api/admin/*` | OK — proxied |
| `services/api.ts` → `api.debug.retrieve()` | `/debug/retrieve` | (none — direct) | `/debug/retrieve` | OK — refactored in Phase 3 |
| `services/api.ts` → `api.dashboardV2.*` | `/dashboard/v2/*` | (none — direct) | `/dashboard/v2/*` | OK |

### 2.2 Developer API Service (`services/developer.ts`)

Uses centralized `API_BASE` → `DEV_API_BASE = ${API_BASE}/developers`.

| Frontend Caller | Frontend Request Path | Proxy Rewrite Rule | Backend FastAPI Target | Status |
|---|---|---|---|---|
| `services/developer.ts` → `registerDeveloper()` | `${API_BASE}/developers/register` | Rule #5 (if proxied) | `/developers/register` | OK |
| `services/developer.ts` → `getDeveloperMe()` | `${API_BASE}/developers/me` | Rule #5 (if proxied) | `/developers/me` | OK |
| `services/developer.ts` → `createDeveloperApiKey()` | `${API_BASE}/developers/api-keys` | Rule #5 (if proxied) | `/developers/api-keys` | OK |
| `services/developer.ts` → `createDeveloperSubmission()` | `${API_BASE}/developers/agents` | Rule #5 (if proxied) | `/developers/agents` | OK |
| `services/developer.ts` → `submitDeveloperSubmission()` | `${API_BASE}/developers/agents/:id/submit` | Rule #5 (if proxied) | `/developers/agents/:id/submit` | OK |

### 2.3 Marketplace API Service (`services/marketplace.ts`)

Uses centralized `API_BASE` → `MKP_API_BASE = ${API_BASE}/agent-marketplace`.

| Frontend Caller | Frontend Request Path | Proxy Rewrite Rule | Backend FastAPI Target | Status |
|---|---|---|---|---|
| `services/marketplace.ts` → `listMarketplaceAgents()` | `${API_BASE}/agent-marketplace` | Rule #6 (if proxied) | `/agent-marketplace` | OK |
| `services/marketplace.ts` → `installMarketplaceAgent()` | `${API_BASE}/agent-marketplace/:id/install` | Rule #6 (if proxied) | `/agent-marketplace/:id/install` | OK |
| `services/marketplace.ts` → `getMarketplaceAnalyticsSummary()` | `${API_BASE}/agent-marketplace/analytics/summary` | Rule #6 (if proxied) | `/agent-marketplace/analytics/summary` | OK |

### 2.4 Agents API Service (`services/agents.ts`)

Uses centralized `API_BASE` → `AGENT_API_BASE = ${API_BASE}/agents`.

| Frontend Caller | Frontend Request Path | Proxy Rewrite Rule | Backend FastAPI Target | Status |
|---|---|---|---|---|
| `services/agents.ts` → `listAgents()` | `${API_BASE}/agents` | (none — direct) | `/agents` | OK |
| `services/agents.ts` → `runAgent()` | `${API_BASE}/agents/run` | (none — direct) | `/agents/run` | OK |
| `services/agents.ts` → `listWorkflows()` | `${API_BASE}/agents/workflows` | (none — direct) | `/agents/workflows` | OK |
| `services/agents.ts` → `runMeetingToTraining()` | `${API_BASE}/agents/scenarios/meeting-to-training/run` | (none — direct) | `/agents/scenarios/meeting-to-training/run` | OK |

### 2.5 Admin Submissions API Service (`services/admin-submissions.ts`)

Uses centralized `API_BASE` → `AR_API_BASE = ${API_BASE}/admin/agent-submissions`.

| Frontend Caller | Frontend Request Path | Proxy Rewrite Rule | Backend FastAPI Target | Status |
|---|---|---|---|---|
| `services/admin-submissions.ts` → `listAdminSubmissions()` | `${API_BASE}/admin/agent-submissions` | (none — direct) | `/admin/agent-submissions` | OK |
| `services/admin-submissions.ts` → `approveAdminSubmission()` | `${API_BASE}/admin/agent-submissions/:id/approve` | (none — direct) | `/admin/agent-submissions/:id/approve` | OK |

### 2.6 Runtime Admin API Service (`services/runtime-admin.ts`)

Implements ideal pattern: `API_BASE ? absolute : relative` — falls back to proxy-relative paths when env var unset.

| Frontend Caller | Frontend Request Path | Proxy Rewrite Rule | Backend FastAPI Target | Status |
|---|---|---|---|---|
| `services/runtime-admin.ts` → `listRuntimeAdapters()` | `/api/runtime/adapters` (relative) | Rule #2 | `/admin/runtime/adapters` | OK — proxy-native |
| `services/runtime-admin.ts` → `listSandboxPolicies()` | `/api/sandbox-policies` (relative) | Rule #3 | `/admin/sandbox-policies` | OK — proxy-native |
| `services/runtime-admin.ts` → `submitSandboxV2Job()` | `/api/runtime/sandbox-v2/jobs` (relative) | Rule #2 | `/admin/runtime/sandbox-v2/jobs` | OK — proxy-native |

## 3. Refactored Rogue Fetch Calls (Phase 3 Fixes)

| File | Before | After | Status |
|---|---|---|---|
| `components/chat/image-upload-button.tsx` | Inline `fetch(\`${process.env.NEXT_PUBLIC_API_URL \|\| "http://127.0.0.1:8000"}/upload\`)` | `api.upload([file])` via `services/api.ts` | FIXED |
| `app/debug/page.tsx` (MemoryExplorer) | Inline `fetch(\`${...}/memory?q=...\`)` | `api.memory.list({ q, limit: 50 })` | FIXED |
| `app/debug/page.tsx` (RetrieveTester) | Inline `fetch(\`${...}/debug/retrieve?q=...\`)` | `apiFetch(\`/debug/retrieve?q=...\`)` | FIXED |
| `app/debug/page.tsx` (EventTimeline) | Inline `fetch(\`${...}/debug/events?limit=100\`)` | `apiFetch(\`/debug/events?limit=100\`)` | FIXED |
| `app/admin/deployment/page.tsx` | `const BASE = process.env.NEXT_PUBLIC_API_URL \|\| "http://127.0.0.1:8000"` + `fetch(\`${BASE}/health\`)` | `apiFetch<BackendHealth>("/health")` for fetch; `const BASE = API_BASE_URL` (imported) for display-only anchor hrefs | FIXED |

## 4. Backend Router Verification

| Backend Router File | Route Prefix | Plural Form | Notes |
|---|---|---|---|
| `src/api/import_router.py` | `/imports` | Yes | Primary route — `POST /imports`, `GET /imports`, `GET /imports/:id`, `POST /imports/:id/retry`, `DELETE /imports/:id` |
| `src/api/sync_router.py` | `/sync` | N/A | Sync hub routes |
| `src/api/growth_analytics_router.py` | `/growth` | N/A | Growth analytics |

**No singular `/import` route exists on the backend.** The Next.js rewrite Rule #8 (`/api/import/:path*` → `/imports/:path*`) serves as a strict alias to prevent 404s from any legacy hardcoded scripts.

## 5. Simulation-Mode Security Boundary

All Runtime and Sandbox API endpoints (`/api/runtime/*`, `/api/sandbox-policies/*`, `/api/runtime/sandbox-v2/*`) are **metadata-only, simulation-driven, and disabled-by-default**. The proxy rules route to the backend's control-plane routers, which enforce the Security Control Plane gate before any actual virtualization. No runtime execution path is exposed through the proxy.
