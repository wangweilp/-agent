import { layout } from "@/styles/layout";

/**
 * Dashboard 路由级加载占位。
 *
 * Next.js App Router 在 CSR 路由跳转时，如果没有 loading.tsx，
 * 会等到页面组件完全准备好才渲染，期间用户看到空白。
 * 有了 loading.tsx，跳转瞬间即显示骨架屏，避免"什么也没显示"的感知。
 */
export default function DashboardLoading() {
  return (
    <div className="p-6 space-y-5 max-w-[1440px] mx-auto">
      {/* Page header skeleton */}
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <div className="h-5 w-32 rounded bg-os-elevated animate-pulse" />
          <div className="h-3 w-40 rounded bg-os-elevated/60 animate-pulse" />
        </div>
        <div className="h-3 w-20 rounded bg-os-elevated/60 animate-pulse" />
      </div>

      {/* SaaS Metrics row skeleton */}
      <div className={layout.grid.fiveLg}>
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="os-card p-4 space-y-2">
            <div className="h-3 w-16 rounded bg-os-elevated animate-pulse" />
            <div className="h-6 w-24 rounded bg-os-elevated/70 animate-pulse" />
          </div>
        ))}
      </div>

      {/* Stats cards skeleton */}
      <div className={layout.grid.five}>
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="os-card p-6 rounded-xl flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <div className="h-4 w-20 rounded bg-os-border/50 animate-pulse" />
              <div className="h-8 w-8 rounded-lg bg-os-border/50 animate-pulse" />
            </div>
            <div className="h-8 w-32 rounded bg-os-border/50 animate-pulse" />
            <div className="h-4 w-24 rounded bg-os-border/30 animate-pulse" />
          </div>
        ))}
      </div>

      {/* Main content area skeleton */}
      <div className={layout.grid.threeLg}>
        <div className="lg:col-span-2 os-card p-4 h-64">
          <div className="h-3 w-32 rounded bg-os-elevated animate-pulse mb-4" />
          <div className="h-48 w-full rounded bg-os-elevated/40 animate-pulse" />
        </div>
        <div className="os-card p-4 h-64">
          <div className="h-3 w-24 rounded bg-os-elevated animate-pulse mb-4" />
          <div className="space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-4 w-full rounded bg-os-elevated/40 animate-pulse" />
            ))}
          </div>
        </div>
      </div>

      {/* Bottom row skeleton */}
      <div className={layout.grid.twoLg}>
        {Array.from({ length: 2 }).map((_, i) => (
          <div key={i} className="os-card p-4 h-48">
            <div className="h-3 w-28 rounded bg-os-elevated animate-pulse mb-4" />
            <div className="space-y-2">
              {Array.from({ length: 5 }).map((_, j) => (
                <div key={j} className="h-4 w-full rounded bg-os-elevated/40 animate-pulse" />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
