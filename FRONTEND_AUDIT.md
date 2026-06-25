# Frontend Audit — Dashboard V2 落地分析

> 基于 `D:\dma\day2\frontend` 仓库真实结构，非猜测。

## 1. 当前前端架构

| 维度 | 实际技术 |
| --- | --- |
| 框架 | Next.js 15 (App Router) + React 19 |
| 语言 | TypeScript 5.6 |
| 路由 | App Router 文件式路由 (`app/<segment>/page.tsx`) |
| 数据层 | TanStack React Query v5 (`@tanstack/react-query`) — 在 `app/providers.tsx` 注入 `QueryClientProvider` |
| 状态管理 | Zustand v5 (`stores/auth-store.ts` 等) |
| 图表库 | Recharts 2.13（**唯一**图表库，禁止新增） |
| 样式 | Tailwind CSS 3.4 + 自定义 `os-*` 设计 token（暗色主题，`<html className="dark">`） |
| 动画 | Framer Motion 11 |
| 图标 | lucide-react |
| API Client | `services/api.ts` 集中式 `request<T>()` + `api` 对象；导出 `apiFetch<T>()` |
| 路径别名 | `@/*` → `./*`（`tsconfig.json`） |
| 测试 | **无**（package.json 无 test 脚本，无 jest/vitest 配置）— 本阶段需新增 |

### 设计 Token（`tailwind.config.ts` + `globals.css`）

- 颜色：`os-base #09090B` / `os-surface #111113` / `os-elevated #18181B` / `os-border #27272A` / `os-text #A1A1AA` / `os-text-high #E4E4E7` / `os-accent #818CF8` / `os-success #34D399` / `os-warning #FBBF24` / `os-danger #F87171`
- 组件类：`.os-card` / `.os-card-hover` / `.os-panel` / `.os-badge` / `.text-gradient`
- 字号：`text-2xs` (0.625rem)
- 圆角：`rounded-os` (0.625rem)

### 现有路由结构（`app/`）

```
app/
  layout.tsx          # RootLayout → Providers → AppLayout(Sidebar+Header+main)
  providers.tsx       # QueryClientProvider (retry:1, staleTime:5000)
  page.tsx
  dashboard/           # 记忆仪表盘（Memory 中心）
  analytics/           # 运营分析（含 alerts/、reports/ 子页）
  agents/              # 智能体中心
  ...
```

### 数据获取模式

主仪表盘 `app/dashboard/page.tsx` 使用 `useQuery({ queryKey, queryFn: () => api.xxx(), refetchInterval })`。
`app/analytics/page.tsx` 使用 `useState + useEffect + Promise.all`（非 Query）。
**Dashboard V2 统一采用 React Query**（与主仪表盘一致，符合 Phase 12 缓存策略要求）。

## 2. 可复用组件

### 通用 / 动画
| 组件 | 路径 | 用途 |
| --- | --- | --- |
| `PageTransition` | `components/animations/page-transition.tsx` | 页面进入动画 |
| `StaggerItem` | 同上 | 子元素错峰入场 |
| `Skeleton` / `CardSkeleton` | `components/animations/skeleton.tsx` | 加载骨架（`shimmer-bg`） |

### Dashboard 通用
| 组件 | 路径 | 用途 |
| --- | --- | --- |
| `StatusCard` | `components/dashboard/status-card.tsx` | KPI 卡（icon+label+value+change），accent: indigo/emerald/amber/violet |
| `MemoryChart` | `components/dashboard/memory-chart.tsx` | 堆叠柱状图（Recharts），含 loading/empty 处理 |

### Analytics 图表（Recharts 封装）
| 组件 | 路径 | 用途 |
| --- | --- | --- |
| `UsageTrendChart` | `components/analytics/UsageTrendChart.tsx` | Area/Bar 趋势图 |
| `ImportChannelChart` | 同上 | Pie 饼图 |
| `RetentionChart` | 同上 | 留存 Bar 图 |
| `MetricsOverview` | `components/analytics/MetricsOverview.tsx` | SaaS 指标卡墙（内部 `MetricCard`） |

### Alert 相关
- `app/analytics/alerts/page.tsx`：已有完整告警规则/事件管理页，使用 `api.alerts.listRules()` / `api.alerts.listEvents()`，含 severity 样式映射、确认/删除/测试逻辑。
- 类型 `AlertRule` / `AlertEvent` 已定义于 `types/index.ts`。

### API Client（`services/api.ts`）
- `request<T>(path, init)`：统一 fetch 封装（auth header、401 跳转、错误转 `ApiError`）
- `apiFetch<T>(path, init)`：导出的通用方法
- `api` 对象：按域分组的命名空间（`api.dashboard.*`、`api.analytics.*`、`api.alerts.*` 等）
- **Dashboard V2 落地方式**：在 `api` 对象新增 `dashboardV2` 命名空间，复用 `request<T>()`，禁止另造 fetch。

## 3. Dashboard V2 推荐落地方案

### 后端契约（已确认，`src/api/dashboard_v2_router.py` + `main.py:336`）

| 端点 | 响应模型 | 关键字段 |
| --- | --- | --- |
| `GET /dashboard/v2/overview` | `OverviewResponse` | mrr/arr/arpu_cents, gross_margin_pct, dau/wau/mau, retention_d1/d7, agent_success_rate, p95_latency_ms, token_cost_today_cents, total_memories, memory_hit_rate, net_growth_today |
| `GET /dashboard/v2/growth?days=` | `GrowthResponse` | dau_series, wau_series, mau_series, retention_cohort[], funnel[], activation_rate |
| `GET /dashboard/v2/agent-performance?days=` | `AgentPerformanceResponse` | call_volume_series, success_rate, failure_rate, latency{p50,p95,p99}_ms, token_usage_series, token_cost_cents |
| `GET /dashboard/v2/memory-health?days=` | `MemoryHealthResponse` | growth_series, hit_rate, total/active/net_growth, type_distribution[] |

> **无** `/dashboard/v2/cost-analytics` 与 `/dashboard/v2/alerts` 端点。
> - Cost Analytics 复用 `agent-performance` 的 `token_usage_series` + `token_cost_cents`（底层 `analytics_token_usage_daily`）。
> - Alerts 复用现有 `api.alerts.listRules/listEvents`。

### 目录结构（遵循现有规范）

```
frontend/
  app/dashboard-v2/
    page.tsx                      # 主入口：6 Tab 客户端切换
  components/dashboard-v2/
    query-state.tsx               # 统一 Loading/Empty/Error/Retry
    series-chart.tsx              # MetricPoint[] 时间序列图（Area/Line）
    kpi-card.tsx                  # KPI 卡（复用 StatusCard 风格）
    section-card.tsx              # 标题卡容器
    tab-overview.tsx              # Overview — KPI 墙
    tab-growth.tsx                # Growth — DAU/WAU/MAU + 队列 + 漏斗
    tab-agent-performance.tsx     # Agent Performance
    tab-memory-health.tsx         # Memory Health
    tab-cost-analytics.tsx        # Cost Analytics（含 Forecast/Budget 预留区）
    tab-alerts.tsx                # Alerts（复用 api.alerts）
  types/dashboard-v2.ts           # Dashboard V2 类型
  services/api.ts                # 新增 api.dashboardV2 命名空间（复用 request<T>）
```

### 复用清单

- **直接复用**：`StatusCard`、`CardSkeleton`、`PageTransition`、`StaggerItem`、Recharts、`os-*` token、`cn/formatNumber/formatMs`（`lib/utils.ts`）
- **新增**：`api.dashboardV2.*`、Dashboard V2 类型、6 个 Tab 组件、4 个共享组件、主页面
- **导航**：在 `components/layout/Sidebar.tsx` 的 `navItems` 增加 `/dashboard-v2`

### 缓存策略（Phase 12，复用 React Query）

| Tab | staleTime |
| --- | --- |
| Overview | 60s |
| Growth | 5min |
| Agent Performance | 5min |
| Memory Health | 5min |
| Alerts | 1min |
| Cost Analytics | 5min（复用 agent-performance 数据） |

### 状态处理（Phase 11）

所有 Tab 组件通过统一 `QueryState` 处理 Loading（`CardSkeleton`）/ Empty / Error（含 Retry），禁止只写 Happy Path。
