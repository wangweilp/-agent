"use client";

import { Activity, BarChart3, Calendar, Download, Infinity, TrendingUp } from "lucide-react";
import type { MarketplaceUsageResponse } from "@/types/marketplace";

interface AgentUsageSummaryProps {
  usage: MarketplaceUsageResponse | null;
  loading?: boolean;
}

export function AgentUsageSummary({ usage, loading = false }: AgentUsageSummaryProps) {
  if (loading) {
    return (
      <div className="os-card p-4">
        <div className="shimmer-bg h-4 w-24 rounded bg-os-elevated" />
        <div className="mt-3 grid grid-cols-4 gap-3">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="shimmer-bg h-16 rounded bg-os-elevated" />
          ))}
        </div>
      </div>
    );
  }

  if (!usage) {
    return (
      <div className="os-card p-4">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-os-text-high">
          <Activity size={16} className="text-os-accent" />
          用量概览
        </h3>
        <p className="mt-2 text-xs text-os-subtle">暂无用量数据。安装并启用 Agent 后，用量会自动汇总。</p>
      </div>
    );
  }

  return (
    <div className="os-card p-4">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-os-text-high">
        <Activity size={16} className="text-os-accent" />
        用量概览
      </h3>

      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <div className="rounded-md border border-os-border bg-os-elevated/30 px-2 py-3 text-center">
          <p className="flex items-center justify-center gap-1 text-2xs text-os-muted">
            <BarChart3 size={10} />
            总调用
          </p>
          <p className="mt-1 text-sm font-semibold text-os-text-high">{usage.total_calls.toLocaleString()}</p>
        </div>

        <div className="rounded-md border border-os-border bg-os-elevated/30 px-2 py-3 text-center">
          <p className="flex items-center justify-center gap-1 text-2xs text-os-muted">
            <TrendingUp size={10} />
            30天调用
          </p>
          <p className="mt-1 text-sm font-semibold text-os-accent">{usage.period_calls.toLocaleString()}</p>
        </div>

        <div className="rounded-md border border-os-border bg-os-elevated/30 px-2 py-3 text-center">
          <p className="flex items-center justify-center gap-1 text-2xs text-os-muted">
            <Download size={10} />
            安装
          </p>
          <p className="mt-1 text-sm font-semibold text-os-text-high">{usage.install_events.toLocaleString()}</p>
        </div>

        <div className="rounded-md border border-os-border bg-os-elevated/30 px-2 py-3 text-center">
          <p className="flex items-center justify-center gap-1 text-2xs text-os-muted">
            <Calendar size={10} />
            最后使用
          </p>
          <p className="mt-1 text-sm font-semibold text-os-text-high">
            {usage.last_used_at
              ? new Date(usage.last_used_at).toLocaleDateString("zh-CN")
              : "-"}
          </p>
        </div>

        <div className="rounded-md border border-os-border bg-os-elevated/30 px-2 py-3 text-center">
          <p className="text-2xs text-os-muted">限额</p>
          <p className="mt-1 text-sm font-semibold text-os-text-high">
            {usage.limit !== null ? usage.limit.toLocaleString() : <Infinity size={14} className="inline text-os-subtle" />}
          </p>
        </div>

        <div className="rounded-md border border-os-border bg-os-elevated/30 px-2 py-3 text-center">
          <p className="text-2xs text-os-muted">剩余</p>
          <p
            className={`mt-1 text-sm font-semibold ${
              usage.remaining === null
                ? "text-os-text-high"
                : usage.remaining > 0
                  ? "text-emerald-300"
                  : "text-red-300"
            }`}
          >
            {usage.remaining !== null ? usage.remaining.toLocaleString() : <Infinity size={14} className="inline text-os-subtle" />}
          </p>
        </div>
      </div>
      <p className="mt-3 text-2xs text-os-muted">
        {usage.billing_note || "※ MVP Usage — 非真实计费数据。"}
      </p>
    </div>
  );
}
