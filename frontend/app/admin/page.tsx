"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Building2,
  Users,
  Brain,
  TrendingUp,
  Shield,
  AlertTriangle,
  Activity,
  RefreshCw,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { cn, formatNumber } from "@/lib/utils";
import { apiFetch } from "@/services/api";
import { useAuthStore } from "@/stores/auth-store";
import type { AdminSummary, GrowthDataPoint } from "@/types";

// ── Types ──

interface RecentAuditEvent {
  id: string;
  action: string;
  user: string;
  org_id: string;
  timestamp: string;
  severity: string;
  detail: string;
}

// ── Helpers ──

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function severityColor(s: string): string {
  switch (s?.toLowerCase()) {
    case "high":
    case "critical":
      return "text-red-400";
    case "medium":
    case "warning":
      return "text-amber-400";
    default:
      return "text-emerald-400";
  }
}

function severityFromAction(action: string): string {
  const a = action.toLowerCase();
  if (/(delete|remove|revoke|disable|deny|fail|terminate)/.test(a)) return "high";
  if (/(update|change|create|assign|approve)/.test(a)) return "medium";
  return "info";
}

// ── Card Component ──

function StatCard({
  icon: Icon,
  label,
  value,
  accent = "indigo",
  loading = false,
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  accent?: "indigo" | "emerald" | "amber" | "violet" | "red" | "cyan";
  loading?: boolean;
}) {
  const accentMap = {
    indigo: "bg-indigo-400/10 text-indigo-400 border-indigo-400/20",
    emerald: "bg-emerald-400/10 text-emerald-400 border-emerald-400/20",
    amber: "bg-amber-400/10 text-amber-400 border-amber-400/20",
    violet: "bg-violet-400/10 text-violet-400 border-violet-400/20",
    red: "bg-red-400/10 text-red-400 border-red-400/20",
    cyan: "bg-cyan-400/10 text-cyan-400 border-cyan-400/20",
  };

  return (
    <div className="os-card p-4 rounded-lg border border-os-border/30 bg-os-surface hover:border-os-border/60 transition-colors">
      <div className="flex items-start justify-between">
        <div className="space-y-1">
          <p className="text-2xs text-os-muted uppercase tracking-wider">{label}</p>
          {loading ? (
            <div className="h-7 w-16 bg-os-elevated rounded animate-pulse" />
          ) : (
            <p className="text-lg font-mono font-semibold text-os-text-high">
              {typeof value === "number" ? formatNumber(value) : value}
            </p>
          )}
        </div>
        <div className={cn("w-8 h-8 rounded-lg flex items-center justify-center border", accentMap[accent])}>
          <Icon size={16} />
        </div>
      </div>
    </div>
  );
}

// ── Page ──

export default function AdminDashboardPage() {
  const [summary, setSummary] = useState<AdminSummary | null>(null);
  const [auditEvents, setAuditEvents] = useState<RecentAuditEvent[]>([]);
  const [growthData, setGrowthData] = useState<GrowthDataPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const workspaceId = useAuthStore((s) => s.currentWorkspace?.id || "default");

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [summaryData, auditData, growthData] = await Promise.all([
        apiFetch<AdminSummary>("/api/admin/summary"),
        apiFetch<Array<{
          id: string;
          action: string;
          user_id: string;
          workspace_id: string;
          resource_type: string;
          resource_id: string;
          detail: string;
          timestamp: string;
        }>>(`/api/audit?workspace_id=${encodeURIComponent(workspaceId)}&limit=10`),
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
      setGrowthData(Array.isArray(growthData) ? growthData : []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard data");
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return (
    <div className="p-6 space-y-5 max-w-[1440px] mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-os-text-high tracking-tight">
            Enterprise Dashboard
          </h1>
          <p className="text-xs text-os-subtle mt-0.5">
            Overview of all organizations, users, and system health
          </p>
        </div>
        <button
          onClick={fetchData}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-2xs text-os-subtle hover:text-os-text hover:bg-os-elevated transition-colors disabled:opacity-50"
        >
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="os-card p-3 rounded-lg border border-red-400/20 bg-red-400/5 text-red-400 text-xs">
          {error}
        </div>
      )}

      {/* Stat Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <StatCard icon={Building2} label="Organizations" value={summary?.total_orgs ?? (loading ? "..." : 0)} accent="indigo" loading={loading} />
        <StatCard icon={Users} label="Total Users" value={summary?.total_users ?? (loading ? "..." : 0)} accent="emerald" loading={loading} />
        <StatCard icon={Brain} label="Memories" value={summary?.total_memories ?? (loading ? "..." : 0)} accent="violet" loading={loading} />
        <StatCard icon={TrendingUp} label="Growth (Weekly)" value={summary?.growth_rate_weekly != null ? `${summary.growth_rate_weekly}%` : "..."} accent="cyan" loading={loading} />
        <StatCard icon={Shield} label="Audit (30d)" value={summary?.audit_events_30d ?? (loading ? "..." : 0)} accent="amber" loading={loading} />
        <StatCard icon={AlertTriangle} label="Risk Events" value={summary?.risk_events ?? (loading ? "..." : 0)} accent={summary?.risk_events ? "red" : "emerald"} loading={loading} />
      </div>

      {/* Charts + Recent Audit */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Growth Chart (2/3) */}
        <div className="lg:col-span-2 os-card p-4 rounded-lg border border-os-border/30 bg-os-surface">
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp size={14} className="text-os-accent" />
            <h2 className="text-xs font-medium text-os-text-high uppercase tracking-wider">
              Knowledge Growth (12 weeks)
            </h2>
          </div>
          {loading ? (
            <div className="h-64 flex items-center justify-center">
              <div className="animate-spin w-5 h-5 border-2 border-os-accent border-t-transparent rounded-full" />
            </div>
          ) : growthData.length === 0 ? (
            <div className="h-64 flex items-center justify-center text-os-muted text-xs">
              No growth data available
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={256}>
              <BarChart data={growthData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272A" />
                <XAxis dataKey="week" tick={{ fill: "#52525B", fontSize: 10 }} axisLine={{ stroke: "#27272A" }} />
                <YAxis tick={{ fill: "#52525B", fontSize: 10 }} axisLine={{ stroke: "#27272A" }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#18181B",
                    border: "1px solid #27272A",
                    borderRadius: "8px",
                    fontSize: "12px",
                    color: "#E4E4E7",
                  }}
                />
                <Bar dataKey="count" fill="#818CF8" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Risk Summary (1/3) */}
        <div className="os-card p-4 rounded-lg border border-os-border/30 bg-os-surface">
          <div className="flex items-center gap-2 mb-4">
            <Activity size={14} className="text-os-accent" />
            <h2 className="text-xs font-medium text-os-text-high uppercase tracking-wider">
              Risk Summary
            </h2>
          </div>
          {loading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-10 bg-os-elevated rounded animate-pulse" />
              ))}
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center justify-between py-2 border-b border-os-border/30">
                <span className="text-xs text-os-text">Risk Events</span>
                <span className={cn("text-sm font-mono font-semibold", summary?.risk_events ? "text-red-400" : "text-emerald-400")}>
                  {summary?.risk_events ?? 0}
                </span>
              </div>
              <div className="flex items-center justify-between py-2 border-b border-os-border/30">
                <span className="text-xs text-os-text">Audit Events (30d)</span>
                <span className="text-sm font-mono font-semibold text-os-text-high">
                  {summary?.audit_events_30d ?? 0}
                </span>
              </div>
              <div className="flex items-center justify-between py-2 border-b border-os-border/30">
                <span className="text-xs text-os-text">Growth Rate</span>
                <span className={cn("text-sm font-mono font-semibold", (summary?.growth_rate_weekly ?? 0) > 0 ? "text-emerald-400" : "text-red-400")}>
                  {summary?.growth_rate_weekly != null ? `${summary.growth_rate_weekly}%` : "N/A"}
                </span>
              </div>
              <div className="flex items-center justify-between py-2">
                <span className="text-xs text-os-text">System Status</span>
                <span className="flex items-center gap-1.5 text-xs text-emerald-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-status-breathe" />
                  Operational
                </span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Recent Audit Events */}
      <div className="os-card p-4 rounded-lg border border-os-border/30 bg-os-surface">
        <div className="flex items-center gap-2 mb-4">
          <Shield size={14} className="text-os-accent" />
          <h2 className="text-xs font-medium text-os-text-high uppercase tracking-wider">
            Recent Audit Events
          </h2>
          <span className="text-2xs text-os-muted ml-auto">
            {auditEvents.length} entries
          </span>
        </div>

        {loading ? (
          <div className="space-y-2">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="h-8 bg-os-elevated rounded animate-pulse" />
            ))}
          </div>
        ) : auditEvents.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-os-muted">
            <Shield size={32} className="mb-2 opacity-30" />
            <p className="text-xs">No recent audit events</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-os-muted border-b border-os-border/30">
                  <th className="text-left py-2 px-2 font-medium">Action</th>
                  <th className="text-left py-2 px-2 font-medium">User</th>
                  <th className="text-left py-2 px-2 font-medium hidden md:table-cell">Org</th>
                  <th className="text-left py-2 px-2 font-medium">Severity</th>
                  <th className="text-right py-2 px-2 font-medium hidden sm:table-cell">Time</th>
                </tr>
              </thead>
              <tbody>
                {auditEvents.map((event) => (
                  <tr key={event.id} className="border-b border-os-border/10 hover:bg-os-elevated/50 transition-colors">
                    <td className="py-2 px-2 text-os-text-high font-medium">{event.action}</td>
                    <td className="py-2 px-2 text-os-text">{event.user}</td>
                    <td className="py-2 px-2 text-os-subtle hidden md:table-cell">{event.org_id || "-"}</td>
                    <td className={cn("py-2 px-2", severityColor(event.severity))}>
                      {event.severity || "info"}
                    </td>
                    <td className="py-2 px-2 text-os-muted text-right hidden sm:table-cell">
                      {formatDate(event.timestamp)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
