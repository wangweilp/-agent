"use client";

import { motion } from "framer-motion";
import {
  Download, Package, FileWarning, ShieldCheck, ShieldAlert,
  CheckCircle2, XCircle, AlertTriangle, Lock,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { RuntimeGovernanceSummary } from "@/types/runtime-admin";
import { layout } from "@/styles/layout";

interface Props {
  governance?: RuntimeGovernanceSummary;
}

type GateKey = "package_download_worker_gate" | "artifact_materialization_gate" | "sandbox_execution_record";

const GATES: { key: GateKey; label: string; icon: typeof Download; accent: string }[] = [
  { key: "package_download_worker_gate", label: "下载闸门", icon: Download, accent: "text-sky-700" },
  { key: "artifact_materialization_gate", label: "制品闸门", icon: FileWarning, accent: "text-violet-700" },
  { key: "sandbox_execution_record", label: "软件包闸门", icon: Package, accent: "text-amber-700" },
];

export function GateMatrix({ governance }: Props) {
  const modules = governance?.modules;

  return (
    <div className="space-y-4">
      {/* ── Gate status overview ── */}
      <div className={layout.grid.threeMd}>
        {GATES.map((gate, i) => {
          const panel = modules?.[gate.key];
          const records = (panel?.[gate.key === "package_download_worker_gate" ? "recent_denials" :
                            gate.key === "artifact_materialization_gate" ? "blocked_records" : "records"] || []) as Record<string, unknown>[];
          return (
            <motion.div
              key={gate.key}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              className={cn(
                "os-card p-4 scanline",
                panel?.enabled ? "border-emerald-400/15" : "border-os-border"
              )}
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-2">
                  <div className={cn(
                    "w-8 h-8 rounded-md flex items-center justify-center",
                    panel?.enabled ? "bg-emerald-400/10" : "bg-os-elevated"
                  )}>
                    <gate.icon size={15} className={panel?.enabled ? "text-emerald-700" : gate.accent} />
                  </div>
                  <div>
                    <h3 className="text-xs font-semibold text-os-text-high">{gate.label}</h3>
                    <p className="text-2xs text-os-subtle">{panel?.mode || "disabled"}</p>
                  </div>
                </div>
                <GateStatusBadge enabled={panel?.enabled} status={panel?.status} />
              </div>

              {/* Status bar */}
              <div className="flex items-center gap-1 mb-3">
                <div className="flex-1 h-1 rounded-full bg-os-elevated overflow-hidden">
                  <div
                    className={cn(
                      "h-full rounded-full transition-all",
                      panel?.enabled ? "bg-emerald-400" : "bg-os-muted"
                    )}
                    style={{ width: panel?.enabled ? "100%" : "0%" }}
                  />
                </div>
                <span className={cn(
                  "text-2xs font-mono",
                  panel?.enabled ? "text-emerald-700" : "text-os-subtle"
                )}>
                  {panel?.enabled ? "运行中" : "已关闭"}
                </span>
              </div>

              {/* Record count */}
              <div className="grid grid-cols-2 gap-2 text-2xs">
                <div className="rounded bg-os-elevated/40 px-2 py-1.5">
                  <p className="text-os-subtle">记录</p>
                  <p className="text-os-text-high font-mono mt-0.5">{records.length}</p>
                </div>
                <div className="rounded bg-os-elevated/40 px-2 py-1.5">
                  <p className="text-os-subtle">风险</p>
                  <p className={cn(
                    "font-mono mt-0.5",
                    panel?.risk_level === "critical" ? "text-rose-700"
                    : panel?.risk_level === "high" ? "text-amber-700"
                    : panel?.risk_level === "medium" ? "text-sky-700"
                    : "text-emerald-700"
                  )}>{panel?.risk_level || "unknown"}</p>
                </div>
              </div>

              {/* Evidence */}
              {panel?.evidence && panel.evidence.length > 0 && (
                <div className="mt-3 space-y-1">
                  {panel.evidence.slice(0, 2).map((e, j) => (
                    <p key={j} className="text-2xs text-os-subtle flex items-start gap-1.5">
                      <CheckCircle2 size={10} className="mt-0.5 shrink-0 text-emerald-700" />
                      <span className="line-clamp-2">{e}</span>
                    </p>
                  ))}
                </div>
              )}
            </motion.div>
          );
        })}
      </div>

      {/* ── Detailed gate records ── */}
      <div className={layout.grid.threeLg}>
        {GATES.map((gate) => {
          const panel = modules?.[gate.key];
          const records = (panel?.[gate.key === "package_download_worker_gate" ? "recent_denials" :
                            gate.key === "artifact_materialization_gate" ? "blocked_records" : "records"] || []) as Record<string, unknown>[];
          return (
            <GateRecordList
              key={gate.key}
              title={gate.label}
              icon={gate.icon}
              records={records}
              reason={panel?.reason}
            />
          );
        })}
      </div>

      {/* ── Production sandbox gate ── */}
      <ProductionGatePanel panel={modules?.production_sandbox_gate} />
    </div>
  );
}

function GateStatusBadge({ enabled, status }: { enabled?: boolean; status?: string }) {
  if (enabled) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-400/10 px-2 py-0.5 font-mono text-2xs text-emerald-700">
        <span className="w-1 h-1 rounded-full bg-emerald-400 animate-status-breathe" />
        运行中
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-amber-400/10 px-2 py-0.5 font-mono text-2xs text-amber-700">
      <Lock size={9} />
      {status || "已禁用"}
    </span>
  );
}

function GateRecordList({
  title, icon: Icon, records, reason,
}: {
  title: string;
  icon: typeof Download;
  records: Record<string, unknown>[];
  reason?: string;
}) {
  return (
    <div className="os-card flex flex-col">
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-os-border">
        <Icon size={12} className="text-os-accent" />
        <h3 className="text-xs font-semibold text-os-text-high uppercase tracking-wider">{title}</h3>
        <span className="ml-auto font-mono text-2xs text-os-subtle">{records.length}</span>
      </div>
      {records.length === 0 ? (
        <div className="px-4 py-6 text-center">
          <ShieldCheck size={18} className="mx-auto mb-1.5 text-emerald-700" />
          <p className="text-2xs text-os-subtle">无拦截记录</p>
        </div>
      ) : (
        <div className="divide-y divide-os-border max-h-72 overflow-y-auto">
          {records.slice(0, 8).map((r, i) => {
            const decision = String(r.decision || r.status || "-");
            const isDenied = decision.includes("deny") || decision.includes("block") || decision.includes("reject");
            return (
              <div key={i} className="px-4 py-2 text-2xs">
                <div className="flex items-center gap-2">
                  {isDenied ? (
                    <XCircle size={10} className="shrink-0 text-rose-700" />
                  ) : (
                    <AlertTriangle size={10} className="shrink-0 text-amber-700" />
                  )}
                  <span className="font-mono text-os-text-high">{decision}</span>
                </div>
                <p className="mt-0.5 truncate font-mono text-os-subtle">
                  {String(r.deny_reason || r.read_only_policy || r.reason || r.metadata_only || "-")}
                </p>
              </div>
            );
          })}
        </div>
      )}
      {reason && (
        <p className="px-4 py-2 text-2xs text-os-subtle border-t border-os-border bg-os-elevated/20">
          {reason}
        </p>
      )}
    </div>
  );
}

function ProductionGatePanel({ panel }: { panel?: RuntimeGovernanceSummary["modules"]["production_sandbox_gate"] }) {
  if (!panel) return null;
  const unmet = panel.unmet_conditions || [];
  const roadmap = panel.roadmap || [];

  return (
    <div className="os-card p-4">
      <div className="flex items-center gap-2 mb-3">
        <div className="w-8 h-8 rounded-md bg-rose-400/10 flex items-center justify-center">
          <ShieldAlert size={15} className="text-rose-700" />
        </div>
        <div>
          <h3 className="text-xs font-semibold text-os-text-high">生产沙箱闸门</h3>
          <p className="text-2xs text-os-subtle">{panel.status} · {panel.mode}</p>
        </div>
        <span className="ml-auto inline-flex items-center gap-1 rounded-full bg-rose-400/10 px-2 py-0.5 font-mono text-2xs text-rose-700">
          <Lock size={9} /> 已阻断
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <p className="mb-2 text-2xs font-medium uppercase tracking-wider text-rose-700">未满足条件</p>
          <div className="space-y-1.5">
            {unmet.map((c, i) => (
              <div key={i} className="flex items-start gap-2 rounded border border-rose-400/15 bg-rose-400/[0.03] px-2.5 py-1.5">
                <XCircle size={11} className="mt-0.5 shrink-0 text-rose-700" />
                <span className="text-2xs text-rose-700">{c}</span>
              </div>
            ))}
          </div>
        </div>
        <div>
          <p className="mb-2 text-2xs font-medium uppercase tracking-wider text-os-primary-hover">路线图</p>
          <div className="space-y-1.5">
            {roadmap.map((r, i) => (
              <div key={i} className="flex items-start gap-2 rounded border border-os-border bg-os-elevated/30 px-2.5 py-1.5">
                <span className="shrink-0 font-mono text-2xs text-os-subtle">{String(i + 1).padStart(2, "0")}</span>
                <span className="text-2xs text-os-subtle">{r}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
