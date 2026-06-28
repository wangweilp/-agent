"use client";

import { useState, useEffect, useCallback } from "react";
import { RefreshCw, BarChart3 } from "lucide-react";
import { api } from "@/services/api";
import MetricsOverview from "@/components/analytics/MetricsOverview";
import {
  UsageTrendChart,
  ImportChannelChart,
  RetentionChart,
} from "@/components/analytics/UsageTrendChart";
import type {
  AnalyticsMetrics,
  MemoryTrend,
  ResourceUsageTrend,
  ImportChannelBreakdown,
  RetentionCohort,
  RealtimeMetrics,
} from "@/types";
import { layout } from "@/styles/layout";

export default function AnalyticsPage() {
  const [metrics, setMetrics] = useState<AnalyticsMetrics | null>(null);
  const [memoryTrend, setMemoryTrend] = useState<MemoryTrend | null>(null);
  const [llmUsage, setLlmUsage] = useState<ResourceUsageTrend | null>(null);
  const [embeddingUsage, setEmbeddingUsage] = useState<ResourceUsageTrend | null>(null);
  const [importChannels, setImportChannels] = useState<ImportChannelBreakdown | null>(null);
  const [retention, setRetention] = useState<RetentionCohort | null>(null);
  const [realtime, setRealtime] = useState<RealtimeMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState(30);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [
        m,
        mt,
        llm,
        emb,
        ic,
        rt,
        rl,
      ] = await Promise.all([
        api.analytics.getMetrics(),
        api.analytics.getMemoryTrend({ days: timeRange }),
        api.analytics.getResourceUsage({ resource: "llm_call", days: timeRange }),
        api.analytics.getResourceUsage({ resource: "embedding", days: timeRange }),
        api.analytics.getImportChannels(timeRange),
        api.analytics.getRetention(6),
        api.analytics.getRealtime(),
      ]);
      setMetrics(m);
      setMemoryTrend(mt);
      setLlmUsage(llm);
      setEmbeddingUsage(emb);
      setImportChannels(ic);
      setRetention(rt);
      setRealtime(rl);
    } catch (err) {
      console.error("Failed to fetch analytics:", err);
    } finally {
      setLoading(false);
    }
  }, [timeRange]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Growth & Analytics Center</h1>
          <p className="text-sm text-muted-foreground">
            运营数据分析与决策看板
            {realtime && (
              <span className="ml-3">
                今日: {realtime.today_events} 事件 | {realtime.active_users_today} 活跃用户 | ¥
                {(realtime.today_cost_cents / 100).toFixed(2)} 成本
              </span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            className="rounded-lg border px-3 py-1.5 text-sm bg-background"
            value={timeRange}
            onChange={(e) => setTimeRange(Number(e.target.value))}
          >
            <option value={7}>最近 7 天</option>
            <option value={30}>最近 30 天</option>
            <option value={90}>最近 90 天</option>
            <option value={365}>最近 1 年</option>
          </select>
          <button
            onClick={fetchAll}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm hover:bg-accent disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            刷新
          </button>
        </div>
      </div>

      {/* Metrics Cards */}
      {metrics && (
        <MetricsOverview
          mrr={metrics.mrr_cents}
          arr={metrics.arr_cents}
          conversionRate={metrics.conversion_rate}
          retentionRate={metrics.retention_rate}
          activeTenants={metrics.active_tenants}
          totalTenants={metrics.total_tenants}
          payingTenants={metrics.paying_tenants}
          churnRate={metrics.churn_rate}
        />
      )}

      {/* Charts */}
      <div className={layout.grid.twoLgWide}>
        {memoryTrend && (
          <UsageTrendChart
            data={memoryTrend.trend}
            title="记忆使用趋势"
            dataKey="count"
            type="area"
          />
        )}
        {llmUsage && (
          <UsageTrendChart
            data={llmUsage.trend}
            title="LLM 调用趋势"
            dataKey="count"
            type="area"
          />
        )}
      </div>

      <div className={layout.grid.twoLgWide}>
        {embeddingUsage && (
          <UsageTrendChart
            data={embeddingUsage.trend}
            title="Embedding 调用趋势"
            dataKey="count"
            type="bar"
          />
        )}
        {importChannels && (
          <ImportChannelChart
            channels={importChannels.channels}
            title="导入渠道分析"
          />
        )}
      </div>

      <div className={layout.grid.twoLgWide}>
        {retention && (
          <RetentionChart
            cohort={retention.cohort}
            title="留存队列分析"
          />
        )}
        {/* Real-time status panel */}
        {realtime && (
          <div className="rounded-xl border bg-card p-4 shadow-sm">
            <h3 className="mb-3 text-sm font-semibold text-muted-foreground">实时运行状态</h3>
            <div className="space-y-3">
              {Object.entries(realtime.hourly_breakdown).length > 0 && (
                <div>
                  <p className="text-xs text-muted-foreground mb-1">每小时事件分布</p>
                  <div className="flex h-16 items-end gap-1">
                    {Object.entries(realtime.hourly_breakdown).map(([hour, count]) => (
                      <div
                        key={hour}
                        className="flex-1 rounded-t bg-blue-500/70"
                        style={{
                          height: `${Math.max(4, (count / Math.max(realtime.max_hourly_events, 1)) * 100)}%`,
                        }}
                        title={`${hour}:00 — ${count} 事件`}
                      />
                    ))}
                  </div>
                </div>
              )}
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div className="rounded-lg bg-accent/50 p-2">
                  <span className="text-xs text-muted-foreground">最高小时事件</span>
                  <p className="font-bold">{realtime.max_hourly_events}</p>
                </div>
                <div className="rounded-lg bg-accent/50 p-2">
                  <span className="text-xs text-muted-foreground">今日活跃用户</span>
                  <p className="font-bold">{realtime.active_users_today}</p>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Quick Links */}
      <div className="flex gap-3">
        <a
          href="/analytics/alerts"
          className="rounded-lg border bg-accent/30 px-4 py-2 text-sm font-medium hover:bg-accent/50 transition-colors"
        >
          ⚠️ 告警管理
        </a>
        <a
          href="/analytics/reports"
          className="rounded-lg border bg-accent/30 px-4 py-2 text-sm font-medium hover:bg-accent/50 transition-colors"
        >
          <BarChart3 className="inline h-3.5 w-3.5 mr-1" />
          报告中心
        </a>
      </div>
    </div>
  );
}
