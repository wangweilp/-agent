"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Shield,
  Search,
  Download,
  RefreshCw,
  Filter,
  X,
  Calendar,
  Clock,
  AlertTriangle,
  CheckCircle2,
  Info,
  Activity,
} from "lucide-react";
import { cn } from "@/lib/utils";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

// ── Types ──

interface AuditEvent {
  id: string;
  action: string;
  user: string;
  user_id?: string;
  org_id?: string;
  resource?: string;
  timestamp: string;
  severity: string;
  detail?: string;
  ip_address?: string;
}

interface AuditSummary {
  last_24h: number;
  last_7d: number;
  last_30d: number;
  by_severity: Record<string, number>;
  by_action: Record<string, number>;
}

// ── API helper ──

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers as Record<string, string> || {}) },
  });
  if (!res.ok) {
    const body = await res.text();
    let msg = `API ${res.status}`;
    try {
      const j = JSON.parse(body);
      if (j.detail) msg = j.detail;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return res.json();
}

// ── Helpers ──

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function severityBadgeStyle(severity: string): string {
  switch (severity?.toLowerCase()) {
    case "critical":
      return "bg-red-400/10 text-red-400 border-red-400/20";
    case "high":
      return "bg-red-400/10 text-red-400 border-red-400/20";
    case "medium":
    case "warning":
      return "bg-amber-400/10 text-amber-400 border-amber-400/20";
    case "low":
    case "info":
      return "bg-emerald-400/10 text-emerald-400 border-emerald-400/20";
    default:
      return "bg-os-elevated text-os-subtle border-os-border/30";
  }
}

function severityIcon(severity: string) {
  switch (severity?.toLowerCase()) {
    case "critical":
    case "high":
      return <AlertTriangle size={12} />;
    case "medium":
    case "warning":
      return <Activity size={12} />;
    case "low":
    case "info":
      return <Info size={12} />;
    default:
      return <Info size={12} />;
  }
}

// ── Page ──

export default function AuditCenterPage() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [summary, setSummary] = useState<AuditSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [actionFilter, setActionFilter] = useState("");
  const [userFilter, setUserFilter] = useState("");
  const [severityFilter, setSeverityFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [showFilters, setShowFilters] = useState(false);

  const fetchEvents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (actionFilter) params.set("action", actionFilter);
      if (userFilter) params.set("user", userFilter);
      if (severityFilter) params.set("severity", severityFilter);
      if (dateFrom) params.set("date_from", dateFrom);
      if (dateTo) params.set("date_to", dateTo);
      params.set("limit", "100");

      const qs = params.toString();
      const data = await apiFetch<AuditEvent[]>(`/api/audit/events${qs ? `?${qs}` : ""}`);
      setEvents(Array.isArray(data) ? data : []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load audit events");
    } finally {
      setLoading(false);
    }
  }, [actionFilter, userFilter, severityFilter, dateFrom, dateTo]);

  const fetchSummary = useCallback(async () => {
    setSummaryLoading(true);
    try {
      const data = await apiFetch<AuditSummary>("/api/audit/summary");
      setSummary(data);
    } catch {
      // summary may not be available
      setSummary(null);
    } finally {
      setSummaryLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchEvents();
    fetchSummary();
  }, [fetchEvents, fetchSummary]);

  const hasFilters = !!(actionFilter || userFilter || severityFilter || dateFrom || dateTo);

  const clearFilters = () => {
    setActionFilter("");
    setUserFilter("");
    setSeverityFilter("");
    setDateFrom("");
    setDateTo("");
  };

  const handleExport = () => {
    const blob = new Blob([JSON.stringify(events, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `audit-export-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // ── Render ──

  return (
    <div className="p-6 space-y-4 max-w-[1440px] mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-os-text-high tracking-tight">
            Audit Center
          </h1>
          <p className="text-xs text-os-subtle mt-0.5">
            Security and compliance audit trail
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleExport}
            disabled={events.length === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-2xs text-os-subtle hover:text-os-text hover:bg-os-elevated transition-colors disabled:opacity-50"
          >
            <Download size={12} />
            Export JSON
          </button>
          <button
            onClick={fetchEvents}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-2xs text-os-subtle hover:text-os-text hover:bg-os-elevated transition-colors"
          >
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="os-card p-3 rounded-lg border border-os-border/30 bg-os-surface">
          <div className="flex items-center gap-2 mb-1">
            <Clock size={12} className="text-os-accent" />
            <span className="text-2xs text-os-muted uppercase tracking-wider">Last 24h</span>
          </div>
          {summaryLoading ? (
            <div className="h-6 w-8 bg-os-elevated rounded animate-pulse mt-1" />
          ) : (
            <p className="text-lg font-mono font-semibold text-os-text-high">
              {summary?.last_24h ?? "-"}
            </p>
          )}
        </div>
        <div className="os-card p-3 rounded-lg border border-os-border/30 bg-os-surface">
          <div className="flex items-center gap-2 mb-1">
            <Calendar size={12} className="text-os-accent" />
            <span className="text-2xs text-os-muted uppercase tracking-wider">Last 7 Days</span>
          </div>
          {summaryLoading ? (
            <div className="h-6 w-8 bg-os-elevated rounded animate-pulse mt-1" />
          ) : (
            <p className="text-lg font-mono font-semibold text-os-text-high">
              {summary?.last_7d ?? "-"}
            </p>
          )}
        </div>
        <div className="os-card p-3 rounded-lg border border-os-border/30 bg-os-surface">
          <div className="flex items-center gap-2 mb-1">
            <Calendar size={12} className="text-os-accent" />
            <span className="text-2xs text-os-muted uppercase tracking-wider">Last 30 Days</span>
          </div>
          {summaryLoading ? (
            <div className="h-6 w-8 bg-os-elevated rounded animate-pulse mt-1" />
          ) : (
            <p className="text-lg font-mono font-semibold text-os-text-high">
              {summary?.last_30d ?? "-"}
            </p>
          )}
        </div>
        <div className="os-card p-3 rounded-lg border border-os-border/30 bg-os-surface">
          <div className="flex items-center gap-2 mb-1">
            <AlertTriangle size={12} className="text-os-accent" />
            <span className="text-2xs text-os-muted uppercase tracking-wider">Critical/High</span>
          </div>
          {summaryLoading ? (
            <div className="h-6 w-8 bg-os-elevated rounded animate-pulse mt-1" />
          ) : (
            <p className="text-lg font-mono font-semibold text-red-400">
              {(summary?.by_severity?.critical || 0) + (summary?.by_severity?.high || 0) || "-"}
            </p>
          )}
        </div>
      </div>

      {/* Filter toggle + controls */}
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => setShowFilters(!showFilters)}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-2xs transition-colors",
            showFilters
              ? "bg-os-accent/10 text-os-accent"
              : "text-os-subtle hover:text-os-text hover:bg-os-elevated"
          )}
        >
          <Filter size={12} />
          Filters
          {hasFilters && (
            <span className="w-1.5 h-1.5 rounded-full bg-os-accent" />
          )}
        </button>
        <div className="text-2xs text-os-muted">
          {events.length} event{events.length !== 1 ? "s" : ""} found
        </div>
        {hasFilters && (
          <button
            onClick={clearFilters}
            className="flex items-center gap-1 px-2 py-1 rounded text-2xs text-os-muted hover:text-os-text transition-colors"
          >
            <X size={12} />
            Clear filters
          </button>
        )}
      </div>

      {/* Filter panel */}
      {showFilters && (
        <div className="os-card p-4 rounded-lg border border-os-border/30 bg-os-surface grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 animate-slide-up">
          <div>
            <label className="text-2xs text-os-subtle block mb-1">Action</label>
            <input
              value={actionFilter}
              onChange={(e) => setActionFilter(e.target.value)}
              placeholder="e.g. login, delete"
              className="w-full h-9 px-3 bg-os-base border border-os-border rounded-md text-xs text-os-text-high placeholder:text-os-muted focus:outline-none focus:border-os-accent transition-colors"
            />
          </div>
          <div>
            <label className="text-2xs text-os-subtle block mb-1">User</label>
            <input
              value={userFilter}
              onChange={(e) => setUserFilter(e.target.value)}
              placeholder="e.g. user@example.com"
              className="w-full h-9 px-3 bg-os-base border border-os-border rounded-md text-xs text-os-text-high placeholder:text-os-muted focus:outline-none focus:border-os-accent transition-colors"
            />
          </div>
          <div>
            <label className="text-2xs text-os-subtle block mb-1">Severity</label>
            <select
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value)}
              className="w-full h-9 px-3 bg-os-base border border-os-border rounded-md text-xs text-os-text-high focus:outline-none focus:border-os-accent transition-colors"
            >
              <option value="">All</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
              <option value="info">Info</option>
            </select>
          </div>
          <div className="flex gap-2">
            <div className="flex-1">
              <label className="text-2xs text-os-subtle block mb-1">From</label>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="w-full h-9 px-3 bg-os-base border border-os-border rounded-md text-xs text-os-text-high focus:outline-none focus:border-os-accent transition-colors"
              />
            </div>
            <div className="flex-1">
              <label className="text-2xs text-os-subtle block mb-1">To</label>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="w-full h-9 px-3 bg-os-base border border-os-border rounded-md text-xs text-os-text-high focus:outline-none focus:border-os-accent transition-colors"
              />
            </div>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="os-card p-3 rounded-lg border border-red-400/20 bg-red-400/5 text-red-400 text-xs">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="space-y-2">
          {[1, 2, 3, 4, 5, 6, 7, 8].map((i) => (
            <div key={i} className="h-10 bg-os-elevated rounded-lg animate-pulse" />
          ))}
        </div>
      )}

      {/* Empty */}
      {!loading && events.length === 0 && (
        <div className="flex flex-col items-center justify-center py-24 text-os-muted">
          <Shield size={48} className="mb-4 opacity-30" />
          <p className="text-sm">No audit events found</p>
          <p className="text-2xs mt-1">
            {hasFilters ? "Try adjusting your filters" : "Events will appear here as users interact with the system"}
          </p>
        </div>
      )}

      {/* Events Table */}
      {!loading && events.length > 0 && (
        <div className="os-card rounded-lg border border-os-border/30 bg-os-surface overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-os-muted border-b border-os-border/30 bg-os-elevated/30">
                  <th className="text-left py-2.5 px-3 font-medium">Timestamp</th>
                  <th className="text-left py-2.5 px-3 font-medium">Action</th>
                  <th className="text-left py-2.5 px-3 font-medium">User</th>
                  <th className="text-left py-2.5 px-3 font-medium hidden md:table-cell">Resource</th>
                  <th className="text-left py-2.5 px-3 font-medium">Severity</th>
                  <th className="text-left py-2.5 px-3 font-medium hidden lg:table-cell">Detail</th>
                </tr>
              </thead>
              <tbody>
                {events.map((event) => (
                  <tr key={event.id} className="border-b border-os-border/10 hover:bg-os-elevated/30 transition-colors">
                    <td className="py-2.5 px-3 text-os-subtle font-mono whitespace-nowrap">
                      {formatDateTime(event.timestamp)}
                    </td>
                    <td className="py-2.5 px-3 text-os-text-high font-medium">
                      {event.action}
                    </td>
                    <td className="py-2.5 px-3 text-os-text">
                      {event.user || event.user_id || "-"}
                    </td>
                    <td className="py-2.5 px-3 text-os-subtle hidden md:table-cell">
                      {event.resource || event.org_id || "-"}
                    </td>
                    <td className="py-2.5 px-3">
                      <span
                        className={cn(
                          "inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-2xs",
                          severityBadgeStyle(event.severity)
                        )}
                      >
                        {severityIcon(event.severity)}
                        {event.severity || "info"}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-os-muted hidden lg:table-cell max-w-[200px] truncate">
                      {event.detail || "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
