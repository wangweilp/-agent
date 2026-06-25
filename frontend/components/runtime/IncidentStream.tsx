"use client";

import { motion } from "framer-motion";
import {
  AlertOctagon, ShieldAlert, ShieldCheck, Activity,
  Bug, Lock, Zap, Clock,
} from "lucide-react";
import { cn, formatDate } from "@/lib/utils";
import type { RuntimeGovernanceSummary } from "@/types/runtime-admin";

interface Props {
  governance?: RuntimeGovernanceSummary;
}

interface IncidentItem {
  severity?: string;
  title?: string;
  name?: string;
  description?: string;
  status?: string;
  related_runtime?: string;
  created_at?: string;
  metadata_only?: boolean;
  [key: string]: unknown;
}

const SEVERITY_STYLE: Record<string, { color: string; bg: string; border: string }> = {
  critical: { color: "text-rose-300", bg: "bg-rose-400/10", border: "border-rose-400/25" },
  high: { color: "text-amber-300", bg: "bg-amber-400/10", border: "border-amber-400/25" },
  medium: { color: "text-sky-300", bg: "bg-sky-400/10", border: "border-sky-400/25" },
  low: { color: "text-emerald-300", bg: "bg-emerald-400/10", border: "border-emerald-400/25" },
};

export function IncidentStream({ governance }: Props) {
  const incidentModule = governance?.modules.incident_store;
  const incidents = (incidentModule?.incidents || []) as IncidentItem[];

  // Severity counts
  const counts = incidents.reduce<Record<string, number>>((acc, inc) => {
    const sev = String(inc.severity || "low").toLowerCase();
    acc[sev] = (acc[sev] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-4">
      {/* ── Summary tiles ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <SummaryTile
          label="Total Incidents"
          value={incidents.length}
          icon={AlertOctagon}
          accent="text-os-accent"
        />
        <SummaryTile
          label="Critical"
          value={counts.critical || 0}
          icon={ShieldAlert}
          accent="text-rose-400"
        />
        <SummaryTile
          label="High"
          value={counts.high || 0}
          icon={Bug}
          accent="text-amber-400"
        />
        <SummaryTile
          label="Resolved"
          value={incidents.filter((i) => String(i.status).toLowerCase() === "closed" || String(i.status).toLowerCase() === "resolved").length}
          icon={ShieldCheck}
          accent="text-emerald-400"
        />
      </div>

      {/* ── Incident stream ── */}
      <div className="os-card">
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-os-border">
          <div className="flex items-center gap-2">
            <Activity size={13} className="text-rose-400" />
            <h3 className="text-xs font-semibold text-os-text-high uppercase tracking-wider">Incident Stream</h3>
            <span className="text-2xs text-os-muted font-mono">{incidents.length}</span>
          </div>
          <span className="text-2xs text-os-muted font-mono">
            {incidentModule?.mode || "metadata-only"}
          </span>
        </div>

        {incidents.length === 0 ? (
          <div className="px-4 py-12 text-center">
            <ShieldCheck size={24} className="mx-auto text-emerald-400/40 mb-2" />
            <p className="text-xs text-os-muted">无安全事件</p>
            <p className="text-2xs text-os-muted mt-1">系统运行正常</p>
          </div>
        ) : (
          <div className="divide-y divide-os-border max-h-[480px] overflow-y-auto">
            {incidents.map((inc, i) => {
              const severity = String(inc.severity || "low").toLowerCase();
              const style = SEVERITY_STYLE[severity] || SEVERITY_STYLE.low;
              const status = String(inc.status || "open");
              const isOpen = status.toLowerCase() === "open" || status.toLowerCase() === "active";
              return (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.03 }}
                  className="px-4 py-3 hover:bg-os-elevated/40 transition-colors"
                >
                  <div className="flex items-start gap-3">
                    {/* Severity indicator */}
                    <div className={cn(
                      "w-1 self-stretch rounded-full shrink-0",
                      style.bg.replace("/10", "/60")
                    )} />

                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className={cn("text-2xs font-mono px-1.5 py-0.5 rounded", style.bg, style.color)}>
                          {severity.toUpperCase()}
                        </span>
                        <span className="text-xs font-medium text-os-text-high truncate">
                          {String(inc.title || inc.name || "Untitled Incident")}
                        </span>
                        <span className={cn(
                          "text-2xs px-1.5 py-0.5 rounded font-mono ml-auto shrink-0",
                          isOpen ? "bg-amber-400/10 text-amber-300" : "bg-emerald-400/10 text-emerald-300"
                        )}>
                          {status}
                        </span>
                      </div>

                      {inc.description && (
                        <p className="text-2xs text-os-subtle mb-1.5 line-clamp-2">
                          {String(inc.description)}
                        </p>
                      )}

                      <div className="flex items-center gap-3 text-2xs text-os-muted">
                        {inc.related_runtime && (
                          <span className="flex items-center gap-1">
                            <Zap size={9} />
                            <span className="font-mono truncate max-w-[120px]">{String(inc.related_runtime)}</span>
                          </span>
                        )}
                        {inc.created_at && (
                          <span className="flex items-center gap-1">
                            <Clock size={9} />
                            {formatDate(String(inc.created_at))}
                          </span>
                        )}
                        {inc.metadata_only && (
                          <span className="flex items-center gap-1 text-amber-300/70">
                            <Lock size={9} />
                            metadata
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </motion.div>
              );
            })}
          </div>
        )}
      </div>

      {/* ── Incident store governance ── */}
      {incidentModule && (
        <div className="os-card p-4">
          <div className="flex items-center gap-2 mb-3">
            <ShieldAlert size={12} className="text-os-muted" />
            <h4 className="text-2xs font-medium text-os-muted uppercase tracking-wider">Incident Store Governance</h4>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-2xs mb-3">
            <MetaItem label="Status" value={incidentModule.status} />
            <MetaItem label="Mode" value={incidentModule.mode} />
            <MetaItem label="Risk" value={incidentModule.risk_level} />
            <MetaItem label="Enabled" value={incidentModule.enabled ? "true" : "false"} />
          </div>
          <div className="rounded border border-os-border bg-os-elevated/40 px-3 py-2">
            <p className="text-2xs text-os-subtle leading-5">{incidentModule.recommended_next_step}</p>
          </div>
        </div>
      )}
    </div>
  );
}

function SummaryTile({
  label, value, icon: Icon, accent,
}: {
  label: string;
  value: number;
  icon: typeof AlertOctagon;
  accent: string;
}) {
  return (
    <div className="os-card p-3 flex items-center gap-2.5">
      <div className={cn("w-8 h-8 rounded-md bg-os-elevated flex items-center justify-center", accent)}>
        <Icon size={14} />
      </div>
      <div>
        <p className="text-2xs text-os-muted">{label}</p>
        <p className="text-lg font-semibold text-os-text-high font-mono">{value}</p>
      </div>
    </div>
  );
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-os-border bg-os-elevated/40 px-2 py-1.5">
      <p className="text-os-muted">{label}</p>
      <p className="text-os-text-high font-mono mt-0.5 truncate">{value}</p>
    </div>
  );
}
