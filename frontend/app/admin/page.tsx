"use client";

import { useCallback, useEffect, useState } from "react";
import { Activity, AlertTriangle, Brain, Building2, RefreshCw, Shield, TrendingUp, Users } from "lucide-react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import {
  EmptyState,
  InfoBanner,
  MetricCard,
  OsBadge,
  OsButton,
  OsCard,
  PageHeader,
  PageShell,
  SectionHeader,
  StatusBadge,
} from "@/components/ui/os";
import { ResponsiveChartContainer } from "@/components/ui/ResponsiveChartContainer";
import { cn, formatNumber } from "@/lib/utils";
import { apiFetch } from "@/services/api";
import { useAuthStore } from "@/stores/auth-store";
import type { AdminSummary, GrowthDataPoint } from "@/types";
import { layout } from "@/styles/layout";

type BadgeTone = "default" | "primary" | "success" | "warning" | "danger" | "info" | "muted";

interface RecentAuditEvent {
  id: string;
  action: string;
  user: string;
  org_id: string;
  timestamp: string;
  severity: string;
  detail: string;
}

function formatDate(iso: string): string {
  const date = new Date(iso);
  return date.toLocaleDateString("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function severityFromAction(action: string): string {
  const normalized = action.toLowerCase();
  if (/(delete|remove|revoke|disable|deny|fail|terminate)/.test(normalized)) return "high";
  if (/(update|change|create|assign|approve)/.test(normalized)) return "medium";
  return "info";
}

function severityTone(severity: string): BadgeTone {
  const normalized = severity.toLowerCase();
  if (normalized === "high" || normalized === "critical") return "danger";
  if (normalized === "medium" || normalized === "warning") return "warning";
  return "success";
}

function severityLabel(severity: string): string {
  const normalized = severity.toLowerCase();
  if (normalized === "critical") return "严重";
  if (normalized === "high") return "高";
  if (normalized === "medium" || normalized === "warning") return "中";
  if (normalized === "low") return "低";
  if (normalized === "info") return "信息";
  return severity;
}

export default function AdminDashboardPage() {
  const [summary, setSummary] = useState<AdminSummary | null>(null);
  const [auditEvents, setAuditEvents] = useState<RecentAuditEvent[]>([]);
  const [growthData, setGrowthData] = useState<GrowthDataPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const workspaceId = useAuthStore((state) => state.currentWorkspace?.id || "default");

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [summaryData, auditData, growth] = await Promise.all([
        apiFetch<AdminSummary>("/api/admin/summary"),
        apiFetch<
          Array<{
            id: string;
            action: string;
            user_id: string;
            workspace_id: string;
            resource_type: string;
            resource_id: string;
            detail: string;
            timestamp: string;
          }>
        >(`/api/audit?workspace_id=${encodeURIComponent(workspaceId)}&limit=10`),
        apiFetch<GrowthDataPoint[]>("/api/admin/growth?weeks=12"),
      ]);

      setSummary(summaryData);
      setAuditEvents(
        Array.isArray(auditData)
          ? auditData.map((event) => ({
              id: event.id,
              action: event.action,
              user: event.user_id,
              org_id: event.workspace_id || workspaceId,
              timestamp: event.timestamp,
              severity: severityFromAction(event.action),
              detail: event.detail || event.resource_type || "",
            }))
          : [],
      );
      setGrowthData(Array.isArray(growth) ? growth : []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "加载仪表盘数据失败");
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return (
    <PageShell>
      <PageHeader
        icon={Building2}
        title="企业仪表盘"
        subtitle="组织、用户、知识增长、审计事件与风险状态的企业级总览。"
        actions={
          <>
            <StatusBadge status={summary?.risk_events ? "warning" : "ready"}>
              {summary?.risk_events ? "存在风险事件" : "系统正常"}
            </StatusBadge>
            <OsButton type="button" variant="secondary" size="md" onClick={fetchData} disabled={loading}>
              <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
              刷新
            </OsButton>
          </>
        }
      />

      {error && (
        <InfoBanner variant="danger" icon={AlertTriangle}>
          {error}
        </InfoBanner>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <MetricCard
          icon={Building2}
          label="组织"
          value={loading ? "..." : formatNumber(summary?.total_orgs || 0)}
          detail="组织空间"
          accent="primary"
        />
        <MetricCard
          icon={Users}
          label="用户总数"
          value={loading ? "..." : formatNumber(summary?.total_users || 0)}
          detail="成员账户"
          accent="success"
        />
        <MetricCard
          icon={Brain}
          label="记忆"
          value={loading ? "..." : formatNumber(summary?.total_memories || 0)}
          detail="知识资产"
          accent="info"
        />
        <MetricCard
          icon={TrendingUp}
          label="增长"
          value={loading ? "..." : summary?.growth_rate_weekly != null ? `${summary.growth_rate_weekly}%` : "0%"}
          detail="周增长率"
          accent="success"
        />
        <MetricCard
          icon={Shield}
          label="审计"
          value={loading ? "..." : formatNumber(summary?.audit_events_30d || 0)}
          detail="30 天事件"
          accent="warning"
        />
        <MetricCard
          icon={AlertTriangle}
          label="风险事件"
          value={loading ? "..." : formatNumber(summary?.risk_events || 0)}
          detail="需要处置"
          accent={summary?.risk_events ? "danger" : "muted"}
        />
      </div>

      <div className={layout.grid.threeLg}>
        <OsCard className="lg:col-span-2" padding="md">
          <SectionHeader
            icon={TrendingUp}
            title="知识增长"
            subtitle="最近 12 周知识资产增长趋势，采用稳定图表容器防止空数据塌陷。"
            className="mb-4"
          />
          {loading ? (
            <div className="h-64 rounded-2xl bg-os-surface-muted animate-pulse" />
          ) : error && growthData.length === 0 ? (
            <p className="flex min-h-[256px] items-center justify-center text-sm text-os-subtle">增长数据暂不可用</p>
          ) : growthData.length === 0 ? (
            <EmptyState
              icon={TrendingUp}
              title="暂无增长数据"
              description="当后端返回增长序列后，这里会显示组织知识资产趋势。"
              className="min-h-[256px]"
            />
          ) : (
            <div className="h-64">
              <ResponsiveChartContainer height="100%" className="border-0 bg-transparent shadow-none">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={growthData} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                    <CartesianGrid stroke="#E6EAF2" strokeDasharray="3 4" vertical={false} />
                    <XAxis dataKey="week" tick={{ fill: "#64748B", fontSize: 12 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: "#64748B", fontSize: 12 }} axisLine={false} tickLine={false} />
                    <Tooltip
                      cursor={{ fill: "rgba(99,102,241,0.06)" }}
                      contentStyle={{
                        backgroundColor: "#FFFFFF",
                        border: "1px solid #E2E8F0",
                        borderRadius: "14px",
                        fontSize: "12px",
                        color: "#334155",
                        boxShadow: "0 12px 30px rgba(15, 23, 42, 0.10)",
                      }}
                      labelStyle={{ color: "#0F172A", fontWeight: 600 }}
                    />
                    <Bar dataKey="count" fill="#7C8CF8" radius={[5, 5, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </ResponsiveChartContainer>
            </div>
          )}
        </OsCard>

        <OsCard padding="md">
          <SectionHeader icon={Activity} title="风险摘要" subtitle="企业控制面状态摘要。" className="mb-4" />
          {loading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((item) => (
                <div key={item} className="h-12 rounded-xl bg-os-surface-muted animate-pulse" />
              ))}
            </div>
          ) : (
            <div className="space-y-2">
              <SummaryRow label="风险事件" value={summary?.risk_events ?? 0} danger={!!summary?.risk_events} />
              <SummaryRow label="审计事件（30 天）" value={summary?.audit_events_30d ?? 0} />
              <SummaryRow
                label="增长率"
                value={summary?.growth_rate_weekly != null ? `${summary.growth_rate_weekly}%` : "暂无"}
                danger={(summary?.growth_rate_weekly ?? 0) < 0}
              />
              <div className="flex items-center justify-between rounded-xl border border-os-border bg-os-surface-tinted px-3 py-2">
                <span className="text-sm text-os-text">系统状态</span>
                <StatusBadge status="ready">运行正常</StatusBadge>
              </div>
            </div>
          )}
        </OsCard>
      </div>

      <OsCard padding="md">
        <SectionHeader
          icon={Shield}
          title="最近审计事件"
          subtitle="最近审计事件，按操作风险自动映射状态色。"
          actions={<OsBadge variant="muted">{auditEvents.length} 条</OsBadge>}
          className="mb-4"
        />

        {loading ? (
          <div className="space-y-2">
            {[1, 2, 3, 4, 5].map((item) => (
              <div key={item} className="h-10 rounded-xl bg-os-surface-muted animate-pulse" />
            ))}
          </div>
        ) : error && auditEvents.length === 0 ? (
          <p className="flex min-h-[260px] items-center justify-center text-sm text-os-subtle">审计数据暂不可用</p>
        ) : auditEvents.length === 0 ? (
          <EmptyState
            icon={Shield}
            title="暂无审计事件"
            description="当组织内出现权限、配置或资源操作时，会在这里形成审计流水。"
            className="min-h-[260px]"
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[680px] text-sm">
              <thead>
                <tr className="border-b border-os-border text-xs text-os-subtle">
                  <th className="px-3 py-2 text-left font-semibold">操作</th>
                  <th className="px-3 py-2 text-left font-semibold">用户</th>
                  <th className="px-3 py-2 text-left font-semibold">组织</th>
                  <th className="px-3 py-2 text-left font-semibold">风险级别</th>
                  <th className="px-3 py-2 text-right font-semibold">时间</th>
                </tr>
              </thead>
              <tbody>
                {auditEvents.map((event) => (
                  <tr key={event.id} className="border-b border-os-border-subtle transition-colors hover:bg-os-surface-hover">
                    <td className="px-3 py-3 font-medium text-os-text-high">{event.action}</td>
                    <td className="px-3 py-3 text-os-text">{event.user}</td>
                    <td className="px-3 py-3 text-os-subtle">{event.org_id || "-"}</td>
                    <td className="px-3 py-3">
                      <OsBadge variant={severityTone(event.severity)}>{severityLabel(event.severity || "info")}</OsBadge>
                    </td>
                    <td className="px-3 py-3 text-right text-os-subtle">{formatDate(event.timestamp)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </OsCard>
    </PageShell>
  );
}

function SummaryRow({ label, value, danger = false }: { label: string; value: string | number; danger?: boolean }) {
  return (
    <div className="flex items-center justify-between rounded-xl border border-os-border bg-white px-3 py-2 shadow-os-card">
      <span className="text-sm text-os-text">{label}</span>
      <span className={cn("font-mono text-sm font-semibold", danger ? "text-os-danger" : "text-os-text-high")}>{value}</span>
    </div>
  );
}
