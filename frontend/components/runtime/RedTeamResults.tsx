"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  FlaskConical, ShieldCheck, ShieldX, AlertTriangle,
  CheckCircle2, XCircle, Activity, Lock,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { RuntimeGovernanceSummary } from "@/types/runtime-admin";
import { getSandboxV2Readiness } from "@/services/runtime-admin";
import { layout } from "@/styles/layout";

interface Props {
  governance?: RuntimeGovernanceSummary;
}

interface RedTeamResultItem {
  name?: string;
  status?: string;
  evidence?: string;
  [key: string]: unknown;
}

const RED_TEAM_CATEGORIES = [
  { key: "artifact_escape_tests", label: "Artifact Escape", desc: "工件逃逸测试" },
  { key: "network_ssrf_tests", label: "Network SSRF", desc: "网络 SSRF 防护" },
  { key: "package_supply_chain_tests", label: "Package Supply Chain", desc: "包供应链安全" },
  { key: "kill_switch_abuse_tests", label: "Kill Switch Abuse", desc: "Kill 开关滥用" },
  { key: "container_escape_tests", label: "Container Escape", desc: "容器逃逸" },
  { key: "policy_fail_closed_tests", label: "Policy Fail-Closed", desc: "策略故障关闭" },
  { key: "api_abuse_tests", label: "API Abuse", desc: "API 滥用" },
  { key: "worker_queue_abuse_tests", label: "Worker/Queue Abuse", desc: "Worker 队列滥用" },
] as const;

export function RedTeamResults({ governance }: Props) {
  const redTeamModule = governance?.modules.red_team_result;
  const results = (redTeamModule?.results || []) as RedTeamResultItem[];

  const { data: readiness } = useQuery({
    queryKey: ["sbv2-readiness-redteam"],
    queryFn: () => getSandboxV2Readiness(),
    refetchInterval: 60000,
  });

  const passedCount = results.filter((r) => String(r.status).toLowerCase() === "passed").length;
  const pendingCount = results.filter((r) => String(r.status).toLowerCase() === "pending").length;
  const failedCount = results.filter((r) => String(r.status).toLowerCase() === "failed").length;

  return (
    <div className="space-y-4">
      {/* ── Summary ── */}
      <div className={layout.grid.fourMd}>
        <SummaryTile
          label="Total Tests"
          value={results.length}
          icon={FlaskConical}
          accent="text-os-accent"
        />
        <SummaryTile
          label="Passed"
          value={passedCount}
          icon={CheckCircle2}
          accent="text-emerald-400"
        />
        <SummaryTile
          label="Pending"
          value={pendingCount}
          icon={AlertTriangle}
          accent="text-amber-400"
        />
        <SummaryTile
          label="Failed"
          value={failedCount}
          icon={XCircle}
          accent="text-rose-400"
        />
      </div>

      {/* ── Test results ── */}
      <div className="os-card">
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-os-border">
          <div className="flex items-center gap-2">
            <FlaskConical size={13} className="text-violet-400" />
            <h3 className="text-xs font-semibold text-os-text-high uppercase tracking-wider">Red-Team Test Results</h3>
          </div>
          <span className={cn(
            "text-2xs px-2 py-0.5 rounded-full font-mono",
            failedCount > 0 ? "bg-rose-400/10 text-rose-300"
            : pendingCount > 0 ? "bg-amber-400/10 text-amber-300"
            : "bg-emerald-400/10 text-emerald-300"
          )}>
            {failedCount > 0 ? "FAILURES DETECTED" : pendingCount > 0 ? "PARTIAL" : "ALL PASSED"}
          </span>
        </div>
        <div className="divide-y divide-os-border">
          {results.map((r, i) => {
            const status = String(r.status).toLowerCase();
            return (
              <motion.div
                key={i}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: i * 0.05 }}
                className="px-4 py-3 flex items-start gap-3"
              >
                <div className={cn(
                  "w-7 h-7 rounded-md flex items-center justify-center shrink-0",
                  status === "passed" ? "bg-emerald-400/10"
                  : status === "pending" ? "bg-amber-400/10"
                  : "bg-rose-400/10"
                )}>
                  {status === "passed" ? <ShieldCheck size={14} className="text-emerald-400" />
                  : status === "pending" ? <AlertTriangle size={14} className="text-amber-400" />
                  : <ShieldX size={14} className="text-rose-400" />}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-os-text-high">{String(r.name || "Unknown Test")}</span>
                    <span className={cn(
                      "text-2xs px-1.5 py-0.5 rounded font-mono ml-auto",
                      status === "passed" ? "bg-emerald-400/10 text-emerald-300"
                      : status === "pending" ? "bg-amber-400/10 text-amber-300"
                      : "bg-rose-400/10 text-rose-300"
                    )}>
                      {String(r.status).toUpperCase()}
                    </span>
                  </div>
                  {r.evidence && (
                    <p className="text-2xs text-os-subtle mt-1 leading-5">{String(r.evidence)}</p>
                  )}
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>

      {/* ── Readiness flags ── */}
      {readiness && (
        <div className="os-card">
          <div className="flex items-center gap-2 px-4 py-2.5 border-b border-os-border">
            <Activity size={12} className="text-os-accent" />
            <h3 className="text-xs font-semibold text-os-text-high uppercase tracking-wider">Readiness Coverage</h3>
            <span className="text-2xs text-os-muted font-mono ml-auto">
              {RED_TEAM_CATEGORIES.filter((c) => readiness[c.key as keyof typeof readiness] === true).length}/{RED_TEAM_CATEGORIES.length}
            </span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2 p-3">
            {RED_TEAM_CATEGORIES.map((cat) => {
              const ok = readiness[cat.key as keyof typeof readiness] === true;
              return (
                <div
                  key={cat.key}
                  className={cn(
                    "flex items-center gap-2.5 rounded border px-3 py-2",
                    ok ? "border-emerald-400/15 bg-emerald-400/[0.03]" : "border-os-border bg-os-elevated/30"
                  )}
                >
                  <div className={cn(
                    "w-1.5 h-1.5 rounded-full shrink-0",
                    ok ? "bg-emerald-400" : "bg-os-muted"
                  )} />
                  <div className="flex-1 min-w-0">
                    <p className="text-2xs font-medium text-os-text-high">{cat.label}</p>
                    <p className="text-2xs text-os-muted">{cat.desc}</p>
                  </div>
                  <span className={cn(
                    "text-2xs font-mono",
                    ok ? "text-emerald-300" : "text-os-muted"
                  )}>
                    {ok ? "READY" : "OFF"}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Boundary ── */}
      {redTeamModule && (
        <div className="os-card p-4">
          <div className="flex items-center gap-2 mb-2">
            <Lock size={12} className="text-amber-400" />
            <h4 className="text-2xs font-medium text-os-muted uppercase tracking-wider">Red-Team Boundary</h4>
          </div>
          <p className="text-2xs text-os-subtle leading-5">{redTeamModule.reason}</p>
          <div className="mt-2 rounded border border-amber-400/15 bg-amber-400/[0.03] px-3 py-2">
            <p className="text-2xs text-amber-200/80 leading-5">{redTeamModule.recommended_next_step}</p>
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
  icon: typeof FlaskConical;
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
