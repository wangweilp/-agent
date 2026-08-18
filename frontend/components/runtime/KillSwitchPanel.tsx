"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Power, Ban, Activity, AlertTriangle, CheckCircle2, XCircle,
  Crosshair, Clock, Zap, ShieldAlert, Loader2,
} from "lucide-react";
import { cn, formatDate } from "@/lib/utils";
import type { RuntimeGovernanceSummary, SandboxV2KillRequest, SandboxV2KillRecord } from "@/types/runtime-admin";
import {
  listSandboxV2KillRequests,
  listSandboxV2KillRecords,
  listSandboxV2ActiveHandles,
  getSandboxV2KillReadiness,
  killSandboxV2Job,
  killSandboxV2ExecutionPlan,
  killSandboxV2ContainerPlan,
  requestSandboxV2HandleCancel,
} from "@/services/runtime-admin";
import { layout } from "@/styles/layout";

interface Props {
  governance?: RuntimeGovernanceSummary;
}

export function KillSwitchPanel({ governance }: Props) {
  const killModule = governance?.modules.kill_switch;
  const [killTarget, setKillTarget] = useState("");
  const [killType, setKillType] = useState<"job" | "execution-plan" | "container-plan">("job");

  const { data: killRequestsData } = useQuery({
    queryKey: ["sbv2-kill-requests"],
    queryFn: () => listSandboxV2KillRequests({ limit: 20 }),
    refetchInterval: 10000,
  });
  const { data: killRecordsData } = useQuery({
    queryKey: ["sbv2-kill-records"],
    queryFn: () => listSandboxV2KillRecords({ limit: 20 }),
    refetchInterval: 10000,
  });
  const { data: activeHandlesData } = useQuery({
    queryKey: ["sbv2-active-handles"],
    queryFn: () => listSandboxV2ActiveHandles({ limit: 20 }),
    refetchInterval: 5000,
  });
  const { data: readiness } = useQuery({
    queryKey: ["sbv2-kill-readiness"],
    queryFn: () => getSandboxV2KillReadiness(),
    refetchInterval: 30000,
  });

  const queryClient = useQueryClient();
  const invalidateKill = () => {
    queryClient.invalidateQueries({ queryKey: ["sbv2-kill-requests"] });
    queryClient.invalidateQueries({ queryKey: ["sbv2-kill-records"] });
    queryClient.invalidateQueries({ queryKey: ["sbv2-active-handles"] });
  };

  const killMutation = useMutation({
    mutationFn: async () => {
      if (!killTarget.trim()) return;
      if (killType === "job") return killSandboxV2Job(killTarget.trim());
      if (killType === "execution-plan") return killSandboxV2ExecutionPlan(killTarget.trim());
      return killSandboxV2ContainerPlan(killTarget.trim());
    },
    onSuccess: () => {
      setKillTarget("");
      invalidateKill();
    },
  });

  const cancelHandleMutation = useMutation({
    mutationFn: (handleId: string) => requestSandboxV2HandleCancel(handleId, "manual kill switch trigger"),
    onSuccess: invalidateKill,
  });

  const killRequests = killRequestsData?.kill_requests || [];
  const killRecords = killRecordsData?.kill_records || [];
  const activeHandles = activeHandlesData?.active_handles || [];

  return (
    <div className="space-y-4">
      {/* ── Kill readiness grid ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2">
        <ReadinessTile label="终止开关" ok={readiness?.kill_switch} />
        <ReadinessTile label="终止策略" ok={readiness?.kill_policy} />
        <ReadinessTile label="活跃句柄" ok={readiness?.active_execution_handles} />
        <ReadinessTile label="队列取消" ok={readiness?.queue_cancel} />
        <ReadinessTile label="工作进程检查点" ok={readiness?.worker_cancel_checkpoints} />
        <ReadinessTile label="提供方取消" ok={readiness?.provider_cancel_interface} />
      </div>

      {/* ── Kill trigger ── */}
      <div className="os-card p-4 scanline">
        <div className="flex items-center gap-2 mb-3">
          <div className="w-7 h-7 rounded bg-rose-400/10 flex items-center justify-center">
            <Power size={14} className="text-rose-700" />
          </div>
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-os-text-high">终止触发器</h3>
            <p className="text-2xs text-os-subtle">实时终止运行中的沙箱任务、执行计划或容器</p>
          </div>
          <span className="ml-auto inline-flex items-center gap-1 rounded-full bg-rose-400/10 px-2 py-0.5 font-mono text-2xs text-rose-700">
            <span className="w-1 h-1 rounded-full bg-rose-400 animate-status-breathe" /> 实时控制
          </span>
        </div>

        <div className="flex flex-col sm:flex-row gap-2">
          <select
            value={killType}
            onChange={(e) => setKillType(e.target.value as typeof killType)}
            className="h-9 rounded-md border border-os-border bg-os-elevated px-2 text-xs text-os-text-high outline-none focus:border-os-accent"
          >
            <option value="job">任务</option>
            <option value="execution-plan">执行计划</option>
            <option value="container-plan">容器计划</option>
          </select>
          <input
            value={killTarget}
            onChange={(e) => setKillTarget(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !killMutation.isPending && killMutation.mutate()}
            placeholder="输入目标 ID…"
            className="h-9 flex-1 rounded-md border border-os-border bg-os-elevated px-3 font-mono text-xs text-os-text-high outline-none placeholder:text-os-subtle focus:border-rose-400/50"
          />
          <button
            onClick={() => killMutation.mutate()}
            disabled={!killTarget.trim() || killMutation.isPending}
            className="flex h-9 items-center gap-1.5 rounded-md bg-rose-700 px-4 text-xs font-medium text-white transition-colors hover:bg-rose-800 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {killMutation.isPending ? <Loader2 size={12} className="animate-spin" /> : <Ban size={12} />}
            终止
          </button>
        </div>

        {killMutation.isError && (
          <p className="mt-2 flex items-center gap-1 text-2xs text-rose-700">
            <AlertTriangle size={10} /> {(killMutation.error as Error)?.message || "终止请求失败"}
          </p>
        )}
        {killMutation.isSuccess && (
          <p className="mt-2 flex items-center gap-1 text-2xs text-emerald-700">
            <CheckCircle2 size={10} /> 终止请求已发送
          </p>
        )}
      </div>

      {/* ── Active execution handles ── */}
      <div className="os-card">
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-os-border">
          <div className="flex items-center gap-2">
            <Crosshair size={13} className="text-amber-700" />
            <h3 className="text-xs font-semibold uppercase tracking-wider text-os-text-high">活跃执行句柄</h3>
            <span className="font-mono text-2xs text-os-subtle">{activeHandles.length}</span>
          </div>
          <span className={cn(
            "text-2xs px-2 py-0.5 rounded-full font-mono",
            activeHandles.length > 0 ? "bg-amber-400/10 text-amber-700" : "bg-emerald-400/10 text-emerald-700"
          )}>
            {activeHandles.length > 0 ? "执行中" : "空闲"}
          </span>
        </div>
        {activeHandles.length === 0 ? (
          <div className="px-4 py-8 text-center">
            <CheckCircle2 size={20} className="mx-auto mb-2 text-emerald-700" />
            <p className="text-xs text-os-subtle">无活跃执行句柄</p>
          </div>
        ) : (
          <div className="divide-y divide-os-border">
            {activeHandles.map((h) => (
              <div key={h.handle_id} className="px-4 py-2.5 flex items-center gap-3 hover:bg-os-elevated/40 transition-colors">
                <div className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-status-breathe shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-os-text-high truncate">{h.handle_id.slice(0, 20)}</span>
                    <span className="text-2xs text-os-subtle">{h.target_type}</span>
                  </div>
                  <div className="mt-0.5 flex items-center gap-3 text-2xs text-os-subtle">
                    <span className="font-mono">{h.provider}</span>
                    <span className="flex items-center gap-1"><Clock size={9} />{formatDate(h.started_at)}</span>
                    {h.timeout_at && <span className="text-amber-700">超时 {formatDate(h.timeout_at)}</span>}
                  </div>
                </div>
                {h.cancel_requested ? (
                  <span className="rounded bg-amber-400/10 px-2 py-0.5 text-2xs text-amber-700">等待取消</span>
                ) : (
                  <button
                    onClick={() => cancelHandleMutation.mutate(h.handle_id)}
                    disabled={cancelHandleMutation.isPending}
                    className="rounded bg-rose-400/10 px-2 py-1 text-2xs text-rose-700 transition-colors hover:bg-rose-400/20 disabled:opacity-50"
                  >
                    取消
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Kill requests + records ── */}
      <div className={layout.grid.twoLg}>
        <KillRequestList requests={killRequests} />
        <KillRecordList records={killRecords} />
      </div>

      {/* ── Governance metadata ── */}
      {killModule && (
        <div className="os-card p-4">
          <div className="flex items-center gap-2 mb-2">
            <ShieldAlert size={12} className="text-os-subtle" />
            <h4 className="text-2xs font-medium uppercase tracking-wider text-os-subtle">治理元数据</h4>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-2xs">
            <MetaItem label="状态" value={killModule.status} />
            <MetaItem label="模式" value={killModule.mode} />
            <MetaItem label="风险" value={killModule.risk_level} />
            <MetaItem label="是否启用" value={killModule.enabled ? "true" : "false"} />
          </div>
          {killModule.evidence.length > 0 && (
            <div className="mt-2 space-y-1">
              {killModule.evidence.slice(0, 3).map((e, i) => (
                <p key={i} className="text-2xs text-os-subtle flex items-start gap-1.5">
                  <CheckCircle2 size={10} className="mt-0.5 shrink-0 text-emerald-700" />
                  {e}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ReadinessTile({ label, ok }: { label: string; ok?: boolean }) {
  return (
    <div className={cn(
      "os-card p-2.5 flex flex-col gap-1",
      ok ? "border-emerald-400/20" : "border-os-border"
    )}>
      <div className="flex items-center justify-between">
        <span className="truncate text-2xs text-os-subtle">{label}</span>
        <div className={cn(
          "w-1.5 h-1.5 rounded-full",
          ok ? "bg-emerald-400" : "bg-os-muted"
        )} />
      </div>
      <span className={cn(
        "text-2xs font-mono",
        ok ? "text-emerald-700" : "text-os-subtle"
      )}>
        {ok ? "就绪" : "关闭"}
      </span>
    </div>
  );
}

function KillRequestList({ requests }: { requests: SandboxV2KillRequest[] }) {
  return (
    <div className="os-card">
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-os-border">
        <Zap size={12} className="text-amber-700" />
        <h3 className="text-xs font-semibold uppercase tracking-wider text-os-text-high">终止请求</h3>
        <span className="ml-auto font-mono text-2xs text-os-subtle">{requests.length}</span>
      </div>
      {requests.length === 0 ? (
        <p className="px-4 py-6 text-center text-2xs text-os-subtle">无终止请求记录</p>
      ) : (
        <div className="divide-y divide-os-border max-h-64 overflow-y-auto">
          {requests.map((r, i) => (
            <div key={i} className="px-4 py-2 text-2xs">
              <div className="flex items-center gap-2">
                <span className="font-mono text-os-text-high">{String(r.target_type || "-")}</span>
                <span className={cn(
                  "px-1.5 py-0.5 rounded text-2xs font-mono",
                  String(r.status) === "completed" ? "bg-emerald-400/10 text-emerald-700"
                    : String(r.status) === "pending" ? "bg-amber-400/10 text-amber-700"
                    : "bg-os-muted/10 text-os-subtle"
                )}>{String(r.status)}</span>
                {r.force && <span className="text-rose-700">强制</span>}
              </div>
              <p className="mt-0.5 truncate font-mono text-os-subtle">{String(r.target_id || r.job_id || "-")}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function KillRecordList({ records }: { records: SandboxV2KillRecord[] }) {
  return (
    <div className="os-card">
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-os-border">
        <Activity size={12} className="text-os-accent" />
        <h3 className="text-xs font-semibold uppercase tracking-wider text-os-text-high">终止记录</h3>
        <span className="ml-auto font-mono text-2xs text-os-subtle">{records.length}</span>
      </div>
      {records.length === 0 ? (
        <p className="px-4 py-6 text-center text-2xs text-os-subtle">无终止执行记录</p>
      ) : (
        <div className="divide-y divide-os-border max-h-64 overflow-y-auto">
          {records.map((r, i) => (
            <div key={i} className="px-4 py-2 text-2xs">
              <div className="flex items-center gap-2">
                <span className="font-mono text-os-text-high">{String(r.action_taken || "-")}</span>
                <span className={cn(
                  "px-1.5 py-0.5 rounded font-mono",
                  String(r.status_after) === "killed" || String(r.status_after) === "canceled"
                    ? "bg-emerald-400/10 text-emerald-700"
                    : "bg-rose-400/10 text-rose-700"
                )}>{String(r.status_after)}</span>
              </div>
              <p className="mt-0.5 truncate font-mono text-os-subtle">{String(r.target_id || "-")}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-os-border bg-os-elevated/40 px-2 py-1.5">
      <p className="text-os-subtle">{label}</p>
      <p className="text-os-text-high font-mono mt-0.5 truncate">{value}</p>
    </div>
  );
}
