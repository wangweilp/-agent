"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Activity,
  AlertOctagon,
  AlertTriangle,
  Ban,
  CheckCircle2,
  ClipboardList,
  FileWarning,
  FlaskConical,
  Gauge,
  LockKeyhole,
  Network,
  OctagonAlert,
  PackageX,
  Plus,
  Power,
  RefreshCw,
  ServerCog,
  ShieldAlert,
  ShieldCheck,
  ShieldX,
  Siren,
  XCircle,
  Zap,
  type LucideIcon,
} from "lucide-react";
import {
  assignRuntimeBindingSandboxPolicy,
  createRuntimeBinding,
  disableRuntimeBinding,
  disableSandboxPolicy,
  enableRuntimeBinding,
  enableSandboxPolicy,
  getRuntimeGovernanceSummary,
  getRuntimeStatus,
  listRuntimeAdapters,
  listRuntimeBindings,
  listRuntimeIncidents,
  listSandboxPolicies,
  suspendRuntimeBinding,
  testSandboxPolicy,
  type RuntimeAdminApiError,
} from "@/services/runtime-admin";
import type {
  DeveloperAgentRuntimeBinding,
  RuntimeAdapter,
  RuntimeGovernancePanel,
  RuntimeGovernanceSummary,
  RuntimeControlPlaneStatus,
  RuntimeIncident,
  SandboxPolicy,
  SandboxPolicyTestResult,
} from "@/types/runtime-admin";

import SandboxV2Dashboard from "@/components/open-platform/SandboxV2Dashboard";
import { EmptyState } from "@/components/dashboard-v2/query-state";
import { toast } from "@/stores/ui-store";

type TabKey = "security" | "governance" | "adapters" | "bindings" | "policies" | "guide" | "sandbox-v2";

const boundaryFallback =
  "当前运行时/Sandbox 主要完成的是安全治理控制面、模拟运行、元数据校验、默认关闭和审计追踪能力，不等于已经完成生产级第三方代码执行沙箱。生产级执行环境需要后续接入 PostgreSQL/Redis/对象存储、真实任务队列、Rootless Container/MicroVM、只读工件物化和安全隔离验证。";

function confirmAction(message: string): boolean {
  if (typeof window === "undefined") return false;
  return window.confirm(message);
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "string" || typeof value === "number") return String(value);
  return JSON.stringify(value);
}

function riskClass(risk: string) {
  if (risk === "critical") return "border-red-400/25 bg-red-400/10 text-red-200";
  if (risk === "high") return "border-amber-400/25 bg-amber-400/10 text-amber-200";
  if (risk === "medium") return "border-sky-400/25 bg-sky-400/10 text-sky-200";
  return "border-emerald-400/25 bg-emerald-400/10 text-emerald-200";
}

export default function RuntimeAdminPage() {
  const [tab, setTab] = useState<TabKey>("security");
  const [adapters, setAdapters] = useState<RuntimeAdapter[]>([]);
  const [bindings, setBindings] = useState<DeveloperAgentRuntimeBinding[]>([]);
  const [policies, setPolicies] = useState<SandboxPolicy[]>([]);
  const [governance, setGovernance] = useState<RuntimeGovernanceSummary | null>(null);
  const [cpStatus, setCpStatus] = useState<RuntimeControlPlaneStatus | null>(null);
  const [incidents, setIncidents] = useState<RuntimeIncident[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [showCreateBind, setShowCreateBind] = useState(false);
  const [assignDialog, setAssignDialog] = useState<{ bindingId: string } | null>(null);
  const [policyDialog, setPolicyDialog] = useState<{ policyId: string } | null>(null);
  const [testResult, setTestResult] = useState<SandboxPolicyTestResult | null>(null);
  const [showKillSwitch, setShowKillSwitch] = useState(false);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [a, b, p, g, s, inc] = await Promise.all([
        listRuntimeAdapters(),
        listRuntimeBindings(),
        listSandboxPolicies(),
        getRuntimeGovernanceSummary(),
        getRuntimeStatus(),
        listRuntimeIncidents(),
      ]);
      setAdapters(a.adapters);
      setBindings(b.bindings);
      setPolicies(p.policies);
      setGovernance(g);
      setCpStatus(s);
      setIncidents(inc.incidents);
    } catch (e: unknown) {
      setError(`[${(e as RuntimeAdminApiError).status || "ERR"}] ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void fetchAll(); }, [fetchAll]);

  const summaryTiles = useMemo(() => [
    ["运行时治理 Status", governance?.runtime_governance_status || "metadata_only_control_plane"],
    ["Current Mode", governance?.current_mode || "metadata-only / simulation"],
    ["Production Sandbox", governance?.production_sandbox || "disabled"],
    ["Default Policy", governance?.default_policy || "deny by default / fail closed"],
  ], [governance]);

  async function handleCreateBind(data: { marketplace_agent_id: string; adapter_id: string; sandbox_policy_id?: string | null }) {
    setError(null);
    try {
      await createRuntimeBinding(data);
      setShowCreateBind(false);
      await fetchAll();
    } catch (e: unknown) {
      setError(`[${(e as RuntimeAdminApiError).status || "ERR"}] ${(e as Error).message}`);
    }
  }

  async function handleEnable(id: string) {
    if (!confirmAction("Enable 只允许 metadata/simulation 绑定，不代表真实执行代码。确认继续？")) return;
    try { await enableRuntimeBinding(id); await fetchAll(); }
    catch (e: unknown) { setError(`[${(e as RuntimeAdminApiError).status || "ERR"}] ${(e as Error).message}`); }
  }

  async function handleDisable(id: string) {
    if (!confirmAction("确认停用这个运行时 Binding？")) return;
    try { await disableRuntimeBinding(id); await fetchAll(); }
    catch (e: unknown) { setError(`[${(e as RuntimeAdminApiError).status || "ERR"}] ${(e as Error).message}`); }
  }

  async function handleSuspend(id: string) {
    if (!confirmAction("确认挂起这个运行时 Binding？")) return;
    try { await suspendRuntimeBinding(id); await fetchAll(); }
    catch (e: unknown) { setError(`[${(e as RuntimeAdminApiError).status || "ERR"}] ${(e as Error).message}`); }
  }

  async function handleAssign(bindingId: string, policyId: string) {
    try {
      await assignRuntimeBindingSandboxPolicy(bindingId, policyId);
      setAssignDialog(null);
      await fetchAll();
    } catch (e: unknown) {
      setError(`[${(e as RuntimeAdminApiError).status || "ERR"}] ${(e as Error).message}`);
    }
  }

  async function handleTestPolicy(policyId: string) {
    try {
      const r = await testSandboxPolicy(policyId, {
        sandbox_level: "simulation_only",
        requested_network: true,
        requested_domains: [],
        requested_filesystem_read: false,
        requested_filesystem_write: false,
        requested_secret_names: [],
        requested_timeout_ms: 0,
        requested_memory_mb: 0,
        requested_data_access_scope: [],
      });
      setTestResult(r);
      setPolicyDialog({ policyId });
    } catch (e: unknown) {
      setError(`[${(e as RuntimeAdminApiError).status || "ERR"}] ${(e as Error).message}`);
    }
  }

  async function handlePolicyStatus(policyId: string, next: "enable" | "disable") {
    const message = next === "enable"
      ? "确认启用这个 Sandbox Policy？它仍然不会启用真实代码执行。"
      : "确认停用这个 Sandbox Policy？";
    if (!confirmAction(message)) return;
    try {
      if (next === "enable") await enableSandboxPolicy(policyId);
      else await disableSandboxPolicy(policyId);
      await fetchAll();
    } catch (e: unknown) {
      setError(`[${(e as RuntimeAdminApiError).status || "ERR"}] ${(e as Error).message}`);
    }
  }

  if (loading) {
    return (
      <main className="mx-auto max-w-7xl px-4 py-8">
        <div className="os-card p-6">
          <div className="shimmer-bg h-6 w-56 rounded bg-os-elevated" />
          <div className="mt-4 space-y-2">
            <div className="shimmer-bg h-3 w-full rounded bg-os-elevated" />
            <div className="shimmer-bg h-3 w-2/3 rounded bg-os-elevated" />
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-7xl px-4 py-8">
      <header className="mb-6">
        <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-os-border bg-os-surface px-3 py-1 text-xs text-os-subtle">
          <ServerCog size={14} className="text-os-accent" /> 运行时管理
        </div>
        <h1 className="text-3xl font-semibold text-os-text-high">运行时安全治理</h1>
        <p className="mt-2 max-w-4xl text-sm leading-6 text-os-subtle">
          {governance?.boundary_statement || boundaryFallback}
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {["禁止远程代码执行", "仅元数据", "模拟运行", "默认拒绝", "故障关闭"].map((label) => (
            <span key={label} className="inline-flex items-center gap-1.5 rounded-full border border-os-border/60 bg-os-elevated px-2.5 py-1 text-2xs text-os-subtle">
              {label}
            </span>
          ))}
        </div>
      </header>

      <section className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        {summaryTiles.map(([label, value]) => (
          <div key={label} className="os-card p-4">
            <p className="text-2xs uppercase tracking-normal text-os-muted">{label}</p>
            <p className="mt-2 text-sm font-semibold text-os-text-high">{value}</p>
          </div>
        ))}
      </section>

      {error && (
        <div className="mb-4 rounded-md border border-red-400/20 bg-red-400/10 p-3 text-sm text-red-200">
          {error}
        </div>
      )}

      <div className="mb-4 flex flex-wrap gap-1">
        {[
          ["security", "安全控制面"],
          ["governance", "治理面板"],
          ["adapters", "运行时适配器"],
          ["bindings", "运行时绑定"],
          ["policies", "沙箱策略"],
          ["sandbox-v2", "沙箱 v2"],
          ["guide", "就绪指南"],
        ].map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key as TabKey)}
            className={`rounded px-3 py-1.5 text-xs transition-colors ${tab === key ? "bg-os-accent text-white" : "bg-os-elevated text-os-subtle hover:text-os-text-high"}`}
          >
            {label}
          </button>
        ))}
        <button onClick={() => void fetchAll()} className="ml-auto inline-flex h-8 items-center gap-1.5 rounded border border-os-border px-2.5 text-xs text-os-subtle hover:text-os-text-high">
          <RefreshCw size={12} />刷新
        </button>
      </div>

      {tab === "security" && (
        <SecurityDashboard
          status={cpStatus}
          incidents={incidents}
          onKillSwitch={() => setShowKillSwitch(true)}
        />
      )}
      {tab === "governance" && governance && <GovernanceView governance={governance} />}
      {tab === "adapters" && <AdaptersView adapters={adapters} />}
      {tab === "bindings" && (
        <BindingsView
          bindings={bindings}
          onCreate={() => setShowCreateBind(true)}
          onEnable={handleEnable}
          onDisable={handleDisable}
          onSuspend={handleSuspend}
          onAssign={(bindingId) => setAssignDialog({ bindingId })}
        />
      )}
      {tab === "policies" && (
        <PoliciesView
          policies={policies}
          onTest={handleTestPolicy}
          onStatusChange={handlePolicyStatus}
        />
      )}
      {tab === "sandbox-v2" && <SandboxV2Dashboard />}
      {tab === "guide" && <GuideView />}

      {showCreateBind && (
        <CreateBindingDialog
          adapters={adapters}
          onClose={() => setShowCreateBind(false)}
          onSubmit={handleCreateBind}
        />
      )}

      {assignDialog && (
        <AssignPolicyDialog
          policies={policies}
          onClose={() => setAssignDialog(null)}
          onAssign={(pid: string) => handleAssign(assignDialog.bindingId, pid)}
        />
      )}

      {policyDialog && testResult && (
        <PolicyResultDialog
          policyId={policyDialog.policyId}
          result={testResult}
          onClose={() => { setPolicyDialog(null); setTestResult(null); }}
        />
      )}

      {showKillSwitch && (
        <KillSwitchConfirmModal
          onClose={() => setShowKillSwitch(false)}
        />
      )}
    </main>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Phase 4 — Security Control Plane Dashboard
// ═══════════════════════════════════════════════════════════════════════════

const ROADMAP_BANNER_TEXT =
  "当前隔离层处于 Metadata 模拟模式。微虚拟机 (microVM) 与容器化底层需要依赖 PostgreSQL 与分布式队列集群，已列入下一阶段工程演进路线。";

function severityStyle(sev: string): string {
  if (sev === "critical") return "border-red-500/40 bg-red-500/15 text-red-300";
  if (sev === "high") return "border-amber-400/40 bg-amber-400/10 text-amber-300";
  if (sev === "medium") return "border-sky-400/40 bg-sky-400/10 text-sky-300";
  return "border-emerald-400/40 bg-emerald-400/10 text-emerald-300";
}

function statusStyle(status: string): string {
  if (status === "resolved") return "text-emerald-400";
  if (status === "investigating") return "text-amber-400";
  return "text-red-400";
}

function incidentTypeIcon(type: string): LucideIcon {
  if (type.includes("filesystem")) return FileWarning;
  if (type.includes("network")) return Network;
  if (type.includes("secrets")) return LockKeyhole;
  if (type.includes("subprocess") || type.includes("process")) return OctagonAlert;
  if (type.includes("resource")) return Gauge;
  return AlertTriangle;
}

function SecurityDashboard({
  status,
  incidents,
  onKillSwitch,
}: {
  status: RuntimeControlPlaneStatus | null;
  incidents: RuntimeIncident[];
  onKillSwitch: () => void;
}) {
  const mode = status?.mode || "simulation";
  const defaultPolicy = status?.default_policy || "deny_by_default";
  const productionSandbox = status?.production_sandbox || "disabled";

  const criticalCount = incidents.filter((i) => i.severity === "critical").length;
  const highCount = incidents.filter((i) => i.severity === "high").length;
  const resolvedCount = incidents.filter((i) => i.status === "resolved").length;

  return (
    <div className="space-y-6">
      {/* ── Panel 4: Roadmap Warning Banner (top) ── */}
      <div className="rounded-xl border border-amber-400/30 bg-gradient-to-r from-amber-400/10 via-amber-400/5 to-transparent p-6">
        <div className="flex items-start gap-4">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-amber-400/40 bg-amber-400/15 text-amber-400">
            <AlertTriangle size={22} />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-amber-200">生产环境演进提示</h3>
            <p className="mt-1.5 text-sm leading-6 text-amber-100/80">{ROADMAP_BANNER_TEXT}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {["PostgreSQL 集群", "分布式任务队列", "Rootless Container", "MicroVM 隔离", "只读工件物化"].map((tag) => (
                <span key={tag} className="inline-flex items-center gap-1 rounded-lg border border-amber-400/20 bg-amber-400/5 px-2.5 py-1 text-2xs text-amber-200/70">
                  {tag}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* ── Panel 1: Overview Status ── */}
      <div className="os-card relative rounded-xl p-6 overflow-hidden">
        {/* 顶部青色激活亮线 — 模拟监控面板扫描条 */}
        <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-cyan-400 to-transparent shadow-[0_0_8px_rgba(34,211,238,0.8)]" />
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-os-border bg-os-elevated text-os-accent">
              <ShieldCheck size={20} />
            </div>
            <div>
              <h2 className="text-base font-semibold text-os-text-high">全局安全状态</h2>
              <p className="text-2xs text-os-muted">Security Control Plane Overview</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {/* 系统存活指示点 — 顺滑呼吸灯动画 */}
            <span className="relative flex h-2.5 w-2.5">
              <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-40 animate-status-breathe" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.8)]" />
            </span>
            <span className="text-xs text-emerald-400 font-medium">{status?.status || "active"}</span>
          </div>
        </div>

        <div className="grid gap-6 md:grid-cols-3">
          {/* Mode — 激活监控面板，顶部青色发光亮线 */}
          <div className="relative rounded-xl border border-os-border/60 border-t-cyan-400/40 bg-os-elevated/40 p-6 overflow-hidden">
            {/* 顶部青色 1px 亮线 + 发光阴影，假装被激活的监控面板 */}
            <div className="absolute top-0 left-0 right-0 h-px bg-cyan-400 shadow-[0_0_8px_rgba(34,211,238,0.9),0_0_4px_rgba(34,211,238,0.6)]" />
            <div className="flex items-center gap-2 mb-3">
              <Zap size={14} className="text-os-accent-cyan" />
              <span className="text-2xs uppercase tracking-wider text-os-muted">运行模式</span>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-bold text-os-accent-cyan">Simulation</span>
              <span className="text-xs text-os-muted">模拟沙箱</span>
            </div>
            <p className="mt-2 text-2xs leading-5 text-os-subtle">
              所有执行能力以元数据形式模拟，无真实进程/容器/网络操作
            </p>
          </div>

          {/* Default Policy */}
          <div className="rounded-xl border border-os-border/60 bg-os-elevated/40 p-6">
            <div className="flex items-center gap-2 mb-3">
              <ShieldX size={14} className="text-red-400" />
              <span className="text-2xs uppercase tracking-wider text-os-muted">高危操作策略</span>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-bold text-red-400">Fail Closed</span>
            </div>
            <p className="mt-2 text-2xs leading-5 text-os-subtle">
              默认拒绝 · 未知风险一律拦截 · 仅元数据审计可通过
            </p>
          </div>

          {/* Production Sandbox */}
          <div className="rounded-xl border border-os-border/60 bg-os-elevated/40 p-6">
            <div className="flex items-center gap-2 mb-3">
              <LockKeyhole size={14} className="text-amber-400" />
              <span className="text-2xs uppercase tracking-wider text-os-muted">生产级沙箱</span>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-bold text-amber-400">Disabled</span>
            </div>
            <p className="mt-2 text-2xs leading-5 text-os-subtle">
              microVM / 容器隔离层未启用 · 等待基础设施就绪
            </p>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-2 text-2xs">
          <span className="rounded-lg border border-os-border bg-os-elevated px-2.5 py-1 text-os-subtle">mode: {mode}</span>
          <span className="rounded-lg border border-os-border bg-os-elevated px-2.5 py-1 text-os-subtle">default_policy: {defaultPolicy}</span>
          <span className="rounded-lg border border-os-border bg-os-elevated px-2.5 py-1 text-os-subtle">production_sandbox: {productionSandbox}</span>
          {status?.last_checked_at && (
            <span className="rounded-lg border border-os-border bg-os-elevated px-2.5 py-1 text-os-muted">
              last_check: {status.last_checked_at.slice(0, 19)}
            </span>
          )}
        </div>
      </div>

      {/* ── Panel 2: Kill Switch ── */}
      <div className="os-card rounded-xl p-6">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-red-500/30 bg-red-500/10 text-red-400">
              <Siren size={20} />
            </div>
            <div>
              <h2 className="text-base font-semibold text-os-text-high">一键熔断开关</h2>
              <p className="text-2xs text-os-muted">Kill Switch · Emergency Halt</p>
            </div>
          </div>
          <span className="rounded-lg border border-emerald-400/30 bg-emerald-400/10 px-2.5 py-1 text-2xs text-emerald-300">
            就绪 · 模拟模式
          </span>
        </div>

        <div className="flex flex-col items-center gap-5 rounded-xl border border-os-border/60 bg-gradient-to-b from-red-500/5 to-transparent p-8">
          <button
            onClick={onKillSwitch}
            className="group relative flex h-32 w-32 items-center justify-center rounded-full border-2 border-red-500/50 bg-red-500/10 shadow-[0_0_30px_rgba(239,68,68,0.6)] transition-all hover:border-red-500 hover:bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] hover:from-red-500 hover:to-red-700 hover:shadow-[0_0_60px_rgba(239,68,68,0.8)] active:scale-95"
            title="紧急熔断（模拟）"
          >
            {/* 外层持续呼吸警告光环 — 双层脉冲营造危险物理按钮质感 */}
            <div className="absolute inset-0 rounded-full border border-red-500/30 animate-pulse" style={{ animationDuration: "2.5s" }} />
            <div className="absolute inset-2 rounded-full border border-red-500/40 animate-ping" style={{ animationDuration: "3s" }} />
            <div className="absolute inset-4 rounded-full bg-red-500/5 animate-pulse" style={{ animationDuration: "2s" }} />
            <Power size={42} className="relative text-red-400 group-hover:text-red-200 transition-colors drop-shadow-[0_0_8px_rgba(239,68,68,0.8)]" strokeWidth={2.5} />
          </button>
          <div className="text-center">
            <p className="text-sm font-semibold text-red-300">EMERGENCY HALT</p>
            <p className="mt-1 text-2xs text-os-muted">点击触发模拟熔断 · 二次确认后执行</p>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="rounded-lg border border-os-border/50 bg-os-elevated/30 p-3 text-center">
            <p className="text-2xs text-os-muted">拦截总数</p>
            <p className="mt-1 text-xl font-bold text-os-text-high">{incidents.length}</p>
          </div>
          <div className="rounded-lg border border-red-400/20 bg-red-400/5 p-3 text-center">
            <p className="text-2xs text-os-muted">Critical</p>
            <p className="mt-1 text-xl font-bold text-red-400">{criticalCount}</p>
          </div>
          <div className="rounded-lg border border-amber-400/20 bg-amber-400/5 p-3 text-center">
            <p className="text-2xs text-os-muted">High</p>
            <p className="mt-1 text-xl font-bold text-amber-400">{highCount}</p>
          </div>
        </div>
      </div>

      {/* ── Panel 3: Incident Telemetry ── */}
      <div className="os-card rounded-xl p-6">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-os-border bg-os-elevated text-os-accent">
              <Activity size={20} />
            </div>
            <div>
              <h2 className="text-base font-semibold text-os-text-high">拦截遥测数据</h2>
              <p className="text-2xs text-os-muted">Incident Telemetry · Simulation Stream</p>
            </div>
          </div>
          <div className="flex items-center gap-3 text-2xs">
            <span className="text-os-muted">已解决 <span className="text-emerald-400 font-mono font-bold">{resolvedCount}</span>/{incidents.length}</span>
          </div>
        </div>

        {incidents.length === 0 ? (
          <div className="rounded-xl border border-os-border/50 bg-os-elevated/20">
            <EmptyState
              icon={ShieldCheck}
              message="暂无拦截记录"
              description="系统未记录到任何安全事件 · 控制面运行正常"
            />
          </div>
        ) : (
          <div className="w-full overflow-x-auto rounded-xl border border-os-border/40">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-os-border bg-os-elevated/50">
                  <th className="px-4 py-3 font-medium text-os-muted">时间</th>
                  <th className="px-4 py-3 font-medium text-os-muted">智能体 ID</th>
                  <th className="px-4 py-3 font-medium text-os-muted">事件类型</th>
                  <th className="px-4 py-3 font-medium text-os-muted">描述</th>
                  <th className="px-4 py-3 font-medium text-os-muted">风险等级</th>
                  <th className="px-4 py-3 font-medium text-os-muted">拦截状态</th>
                </tr>
              </thead>
              <tbody>
                {incidents.map((inc) => {
                  const Icon = incidentTypeIcon(inc.incident_type);
                  // Critical 行：微弱红色呼吸背景 + 2px 发光左边框，让高危事件异常刺眼
                  const isCritical = inc.severity === "critical";
                  const rowClass = isCritical
                    ? "border-b border-os-border/30 border-l-2 border-l-red-500 shadow-[0_0_10px_rgba(239,68,68,0.4)] bg-red-900/10 animate-pulse hover:bg-red-900/20 transition-colors"
                    : "border-b border-os-border/30 hover:bg-os-elevated/30 transition-colors";
                  return (
                    <tr key={inc.incident_id} className={rowClass} style={isCritical ? { animationDuration: "3s" } : undefined}>
                      <td className="px-4 py-3.5 font-mono text-2xs text-os-muted whitespace-nowrap">
                        {inc.timestamp.slice(0, 19).replace("T", " ")}
                      </td>
                      <td className="px-4 py-3.5">
                        <span className="font-mono text-2xs text-os-text">{inc.agent_id}</span>
                      </td>
                      <td className="px-4 py-3.5">
                        <div className="flex items-center gap-2">
                          <Icon size={13} className="text-os-subtle shrink-0" />
                          <span className="text-2xs text-os-subtle">{inc.incident_type}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3.5 max-w-xs">
                        <p className="text-2xs leading-5 text-os-text truncate" title={inc.description}>
                          {inc.title}
                        </p>
                      </td>
                      <td className="px-4 py-3.5">
                        <span className={`inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-2xs font-medium ${severityStyle(inc.severity)}`}>
                          {inc.severity === "critical" && <AlertOctagon size={10} />}
                          {inc.severity === "high" && <AlertTriangle size={10} />}
                          {inc.severity}
                        </span>
                      </td>
                      <td className="px-4 py-3.5">
                        <span className={`text-2xs font-medium ${statusStyle(inc.status)}`}>
                          {inc.status === "resolved" && <CheckCircle2 size={11} className="inline mr-1" />}
                          {inc.status === "investigating" && <AlertTriangle size={11} className="inline mr-1" />}
                          {inc.status}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        <p className="mt-3 text-2xs text-os-muted">
          所有拦截记录均为模拟数据 · metadata-only · 无真实执行被阻止
        </p>
      </div>
    </div>
  );
}

// ── Kill Switch Confirmation Modal ──

function KillSwitchConfirmModal({ onClose }: { onClose: () => void }) {
  const [stage, setStage] = useState<"confirm" | "executing" | "done">("confirm");

  const handleConfirm = () => {
    setStage("executing");
    // 模拟熔断执行延迟
    setTimeout(() => {
      setStage("done");
      toast.danger("熔断信号已广播", "所有智能体执行已暂停（模拟模式）");
    }, 1800);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm px-4">
      <div className="w-full max-w-lg rounded-xl border border-red-500/30 bg-os-base shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="border-b border-os-border bg-gradient-to-r from-red-500/15 to-transparent p-6">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-red-500/40 bg-red-500/15 text-red-400">
              <Siren size={22} />
            </div>
            <div>
              <h3 className="text-base font-semibold text-red-300">紧急熔断确认</h3>
              <p className="text-2xs text-os-muted">Emergency Kill Switch Confirmation</p>
            </div>
          </div>
        </div>

        {/* Body */}
        <div className="p-6 space-y-4">
          {stage === "confirm" && (
            <>
              <div className="rounded-xl border border-red-400/20 bg-red-400/5 p-4">
                <p className="text-sm leading-6 text-red-100">
                  您即将触发 <span className="font-bold">模拟熔断</span>。此操作在当前 Simulation 模式下不会影响任何真实进程，仅用于验证控制面的治理能力。
                </p>
              </div>
              <div className="space-y-2 text-2xs text-os-muted">
                <p className="flex items-center gap-2">
                  <CheckCircle2 size={12} className="text-emerald-400" />
                  将向所有活跃 binding 广播 suspend 信号（模拟）
                </p>
                <p className="flex items-center gap-2">
                  <CheckCircle2 size={12} className="text-emerald-400" />
                  将标记 kill_switch.status = triggered_metadata_only
                </p>
                <p className="flex items-center gap-2">
                  <CheckCircle2 size={12} className="text-emerald-400" />
                  不会终止任何真实容器或进程（production_sandbox=disabled）
                </p>
              </div>
              <div className="flex gap-3 pt-2">
                <button
                  onClick={onClose}
                  className="flex-1 rounded-xl border border-os-border bg-os-elevated px-4 py-2.5 text-sm text-os-text-high hover:bg-os-surface transition-colors"
                >
                  取消
                </button>
                <button
                  onClick={handleConfirm}
                  className="flex-1 rounded-xl border border-red-500/50 bg-red-500/20 px-4 py-2.5 text-sm font-semibold text-red-300 hover:bg-red-500/30 transition-colors"
                >
                  <Power size={14} className="inline mr-1.5" />
                  确认熔断
                </button>
              </div>
            </>
          )}

          {stage === "executing" && (
            <div className="flex flex-col items-center py-8">
              <div className="h-12 w-12 animate-spin rounded-full border-2 border-red-500/30 border-t-red-400" />
              <p className="mt-4 text-sm text-os-text-high">正在广播熔断信号...</p>
              <p className="mt-1 text-2xs text-os-muted">向所有活跃 binding 发送 suspend 指令（模拟）</p>
            </div>
          )}

          {stage === "done" && (
            <div className="flex flex-col items-center py-8">
              <div className="flex h-14 w-14 items-center justify-center rounded-full border border-emerald-400/40 bg-emerald-400/10 text-emerald-400">
                <CheckCircle2 size={28} />
              </div>
              <p className="mt-4 text-sm font-semibold text-emerald-300">熔断信号已广播</p>
              <p className="mt-1 text-2xs text-os-muted">所有 binding 已标记为 suspended_metadata_only</p>
              <button
                onClick={onClose}
                className="mt-6 rounded-xl border border-os-border bg-os-elevated px-6 py-2 text-sm text-os-text-high hover:bg-os-surface transition-colors"
              >
                关闭
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function GovernanceView({ governance }: { governance: RuntimeGovernanceSummary }) {
  const m = governance.modules;
  return (
    <div className="space-y-4">
      <div className="grid gap-3 lg:grid-cols-3">
        <GovernancePanel icon={Power} panel={m.kill_switch}>
          <div className="mt-3 flex flex-wrap gap-2">
            <button disabled title="Read-only metadata API" className="inline-flex h-8 items-center gap-1 rounded border border-os-border px-2 text-2xs text-os-muted opacity-60">
              <ShieldAlert size={12} />启用
            </button>
            <button disabled title="Read-only metadata API" className="inline-flex h-8 items-center gap-1 rounded border border-os-border px-2 text-2xs text-os-muted opacity-60">
              <Ban size={12} />停用
            </button>
            <button disabled title="History endpoint is read-only in the summary payload" className="inline-flex h-8 items-center gap-1 rounded border border-os-border px-2 text-2xs text-os-muted opacity-60">
              <ClipboardList size={12} />历史
            </button>
          </div>
        </GovernancePanel>
        <GovernancePanel icon={ShieldCheck} panel={m.incident_store}>
          <MiniTable rows={m.incident_store.incidents || []} fields={["severity", "status", "title", "related_runtime"]} />
        </GovernancePanel>
        <GovernancePanel icon={PackageX} panel={m.package_download_worker_gate}>
          <MiniTable rows={m.package_download_worker_gate.recent_denials || []} fields={["status", "decision", "deny_reason"]} />
        </GovernancePanel>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <GovernancePanel icon={FileWarning} panel={m.artifact_materialization_gate}>
          <MiniTable rows={m.artifact_materialization_gate.blocked_records || []} fields={["status", "decision", "read_only_policy"]} />
        </GovernancePanel>
        <GovernancePanel icon={Activity} panel={m.sandbox_execution_record}>
          <MiniTable rows={m.sandbox_execution_record.records || []} fields={["execution_status", "decision", "mode", "metadata_only"]} />
        </GovernancePanel>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <GovernancePanel icon={FlaskConical} panel={m.red_team_result}>
          <MiniTable rows={m.red_team_result.results || []} fields={["name", "status", "evidence"]} />
        </GovernancePanel>
        <GovernancePanel icon={LockKeyhole} panel={m.production_sandbox_gate}>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {(m.production_sandbox_gate.unmet_conditions || []).map((item) => (
              <div key={item} className="rounded border border-red-400/15 bg-red-400/5 px-2.5 py-2 text-2xs text-red-100">
                {item}
              </div>
            ))}
          </div>
        </GovernancePanel>
      </div>
    </div>
  );
}

function GovernancePanel({ icon: Icon, panel, children }: { icon: LucideIcon; panel: RuntimeGovernancePanel; children?: ReactNode }) {
  return (
    <article className="os-card p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded border border-os-border bg-os-elevated text-os-accent">
            <Icon size={17} />
          </div>
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-os-text-high">{panel.title}</h3>
            <p className="mt-1 text-2xs leading-5 text-os-subtle">{panel.reason}</p>
          </div>
        </div>
        <span className={`shrink-0 rounded border px-2 py-1 text-2xs ${riskClass(panel.risk_level)}`}>
          {panel.risk_level}
        </span>
      </div>
      <div className="mt-3 flex flex-wrap gap-2 text-2xs">
        <Badge label={panel.status} tone={panel.enabled ? "good" : "warn"} />
        <Badge label={panel.mode} tone="neutral" />
        <Badge label={panel.enabled ? "enabled" : "disabled"} tone={panel.enabled ? "good" : "bad"} />
      </div>
      <div className="mt-3 space-y-1">
        {panel.evidence.slice(0, 3).map((item) => (
          <p key={item} className="flex gap-2 text-2xs leading-5 text-os-subtle">
            <CheckCircle2 size={12} className="mt-0.5 shrink-0 text-emerald-300" />
            <span>{item}</span>
          </p>
        ))}
      </div>
      <p className="mt-3 rounded border border-os-border/70 bg-os-elevated/60 px-2.5 py-2 text-2xs leading-5 text-os-muted">
        {panel.recommended_next_step}
      </p>
      {children}
    </article>
  );
}

function MiniTable({ rows, fields }: { rows: Record<string, unknown>[]; fields: string[] }) {
  if (!rows.length) return <p className="mt-3 text-2xs text-os-muted">暂无记录</p>;
  return (
    <div className="mt-3 overflow-hidden rounded border border-os-border">
      {rows.slice(0, 4).map((row, index) => (
        <div key={index} className="grid gap-2 border-b border-os-border/70 px-2.5 py-2 text-2xs last:border-b-0 md:grid-cols-3">
          {fields.slice(0, 3).map((field) => (
            <div key={field} className="min-w-0">
              <p className="text-os-muted">{field}</p>
              <p className="mt-0.5 truncate text-os-text-high" title={formatValue(row[field])}>{formatValue(row[field])}</p>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

function Badge({ label, tone }: { label: string; tone: "good" | "warn" | "bad" | "neutral" }) {
  const cls = tone === "good" ? "bg-emerald-400/10 text-emerald-300"
    : tone === "warn" ? "bg-amber-400/10 text-amber-300"
      : tone === "bad" ? "bg-red-400/10 text-red-300"
        : "bg-zinc-500/10 text-os-subtle";
  return <span className={`os-badge ${cls}`}>{label}</span>;
}

function AdaptersView({ adapters }: { adapters: RuntimeAdapter[] }) {
  return (
    <div className="space-y-2">
      <p className="mb-2 text-xs text-os-muted">Only manifest_only and simulation are allowed for the current metadata/simulation runtime boundary.</p>
      {adapters.map((adapter) => (
        <div key={adapter.adapter_id} className="os-card p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <span className="text-sm font-semibold text-os-text-high">{adapter.name}</span>
              <span className="ml-2 font-mono text-2xs text-os-muted">{adapter.adapter_type}</span>
              <span className={`ml-2 os-badge ${adapter.status === "active" ? "bg-emerald-400/10 text-emerald-300" : adapter.status === "beta" ? "bg-amber-400/10 text-amber-300" : "bg-zinc-500/10 text-os-muted"}`}>{adapter.status}</span>
            </div>
            <div className="flex flex-wrap gap-2 text-2xs text-os-subtle">
              {adapter.supports_network && <span className="text-amber-300">network</span>}
              {adapter.supports_user_data_read && <span className="text-amber-300">data.read</span>}
              {adapter.supports_user_data_write && <span className="text-red-300">data.write</span>}
              {adapter.sandbox_required && <span className="text-amber-300">sandbox</span>}
              {!adapter.supports_network && !adapter.supports_user_data_read && !adapter.supports_user_data_write && !adapter.sandbox_required && <span className="text-emerald-300">no capabilities</span>}
              <span>{adapter.max_timeout_ms}ms</span>
              <span>{adapter.max_memory_mb}MB</span>
            </div>
          </div>
          <p className="mt-1 text-2xs text-os-subtle">{adapter.description}</p>
          {(adapter.adapter_type === "http_webhook" || adapter.adapter_type === "sandboxed_process" || adapter.adapter_type === "container") && (
            <p className="mt-1 flex items-center gap-1 text-2xs text-amber-300"><AlertTriangle size={10} /> Disabled future capability</p>
          )}
        </div>
      ))}
    </div>
  );
}

function BindingsView({
  bindings,
  onCreate,
  onEnable,
  onDisable,
  onSuspend,
  onAssign,
}: {
  bindings: DeveloperAgentRuntimeBinding[];
  onCreate: () => void;
  onEnable: (id: string) => void;
  onDisable: (id: string) => void;
  onSuspend: (id: string) => void;
  onAssign: (id: string) => void;
}) {
  return (
    <div className="space-y-2">
      <div className="mb-2 flex items-center gap-2">
        <p className="flex-1 text-xs text-os-muted">Bindings connect Marketplace developer agents to allowed metadata/simulation adapters. Enabling a binding does not execute code.</p>
        <button onClick={onCreate} className="inline-flex h-8 items-center gap-1.5 rounded bg-os-accent px-3 text-xs text-white hover:bg-os-accent/90">
          <Plus size={12} />Create Binding
        </button>
      </div>
      {bindings.length === 0 ? <p className="py-8 text-center text-sm text-os-subtle">暂无运行时 Binding</p> : bindings.map((binding) => (
        <div key={binding.binding_id} className="os-card p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <span className="font-mono text-xs text-os-text-high">{binding.binding_id.slice(0, 16)}</span>
              <span className={`ml-2 os-badge ${binding.runtime_status === "enabled" ? "bg-emerald-400/10 text-emerald-300" : binding.runtime_status === "disabled" ? "bg-red-400/10 text-red-300" : binding.runtime_status === "suspended" ? "bg-amber-400/10 text-amber-300" : "bg-zinc-500/10 text-os-muted"}`}>{binding.runtime_status}</span>
              <span className="ml-2 font-mono text-2xs text-os-muted">{binding.adapter_type}</span>
            </div>
            <div className="flex gap-1">
              {binding.runtime_status !== "enabled" && (
                <button onClick={() => onEnable(binding.binding_id)} className="rounded bg-emerald-400/10 px-2 py-0.5 text-2xs text-emerald-300 hover:bg-emerald-400/15">Enable</button>
              )}
              {binding.runtime_status === "enabled" && (
                <>
                  <button onClick={() => onDisable(binding.binding_id)} className="rounded bg-red-400/10 px-2 py-0.5 text-2xs text-red-300 hover:bg-red-400/15">Disable</button>
                  <button onClick={() => onSuspend(binding.binding_id)} className="rounded bg-amber-400/10 px-2 py-0.5 text-2xs text-amber-300 hover:bg-amber-400/15">Suspend</button>
                </>
              )}
              <button onClick={() => onAssign(binding.binding_id)} className="rounded border border-os-border px-2 py-0.5 text-2xs text-os-subtle hover:text-os-text-high">Policy</button>
            </div>
          </div>
          <div className="mt-1 flex flex-wrap gap-2 text-2xs text-os-subtle">
            <span>mkp: {binding.marketplace_agent_id.slice(0, 12)}</span>
            <span>dev: {binding.developer_id.slice(0, 10)}</span>
            <span>tenant: {binding.tenant_id}</span>
            {binding.sandbox_policy_id && <span className="text-violet-300">policy: {binding.sandbox_policy_id}</span>}
          </div>
        </div>
      ))}
    </div>
  );
}

function PoliciesView({ policies, onTest, onStatusChange }: { policies: SandboxPolicy[]; onTest: (id: string) => void; onStatusChange: (id: string, next: "enable" | "disable") => void }) {
  return (
    <div className="space-y-2">
      <p className="mb-2 text-xs text-os-muted">Sandbox Policies define boundaries for simulation and future runtime planning. They are policy models, not container sandboxes.</p>
      {policies.map((policy) => (
        <div key={policy.policy_id} className="os-card p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <span className="text-sm font-semibold text-os-text-high">{policy.name}</span>
              <span className="ml-2 os-badge bg-violet-400/10 text-violet-300">{policy.sandbox_level}</span>
              <span className={`ml-2 os-badge ${policy.scope === "system" ? "bg-blue-400/10 text-blue-300" : "bg-zinc-500/10 text-os-muted"}`}>{policy.scope}</span>
            </div>
            <div className="flex gap-1">
              <button onClick={() => onTest(policy.policy_id)} className="rounded border border-os-border px-2 py-0.5 text-2xs text-os-subtle hover:text-os-text-high">Test</button>
              {policy.status === "active" ? (
                !policy.system_managed && <button onClick={() => onStatusChange(policy.policy_id, "disable")} className="rounded bg-red-400/10 px-2 py-0.5 text-2xs text-red-300 hover:bg-red-400/15">Disable</button>
              ) : (
                <button onClick={() => onStatusChange(policy.policy_id, "enable")} className="rounded bg-emerald-400/10 px-2 py-0.5 text-2xs text-emerald-300 hover:bg-emerald-400/15">Enable</button>
              )}
            </div>
          </div>
          <p className="mt-1 text-2xs text-os-subtle">{policy.description}</p>
          <div className="mt-1 flex flex-wrap gap-1.5 text-2xs">
            {policy.allow_network && <span className="text-amber-300">network</span>}
            {policy.allow_filesystem_read && <span className="text-amber-300">fs.read</span>}
            {policy.allow_filesystem_write && <span className="text-red-300">fs.write</span>}
            {policy.allow_secrets && <span className="text-red-300">secrets</span>}
            {!policy.allow_network && !policy.allow_filesystem_read && !policy.allow_filesystem_write && !policy.allow_secrets && <span className="text-emerald-300">no capabilities</span>}
            <span className="text-os-muted">timeout {policy.max_timeout_ms}ms / memory {policy.max_memory_mb}MB</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function GuideView() {
  return (
    <div className="os-card p-4">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-os-text-high"><Activity size={14} className="text-os-accent" /> 运行时 Readiness Checklist</h3>
      <p className="mt-2 text-xs text-os-subtle">For a developer agent to be simulation-ready, the following conditions must be met. None imply real third-party code execution.</p>
      <div className="mt-4 grid gap-2 md:grid-cols-2">
        {[
          "Developer 智能体 published to Marketplace",
          "Tenant installed agent with required permissions granted",
          "运行时 binding exists and stays on manifest_only or simulation",
          "Sandbox policy assigned when required",
          "Simulation returns deterministic dry-run result",
          "Production Sandbox Gate remains disabled until isolation is implemented",
        ].map((item, index) => (
          <div key={item} className="flex items-start gap-2">
            <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-os-border text-2xs text-os-subtle">{index + 1}</div>
            <p className="text-xs text-os-text-high">{item}</p>
          </div>
        ))}
      </div>
      <div className="mt-4 rounded border border-amber-400/20 bg-amber-400/5 p-3">
        <p className="flex items-start gap-2 text-xs leading-5 text-amber-200">
          <AlertTriangle size={13} className="mt-0.5 shrink-0" />
          Simulation does not download packages, make external network calls, execute subprocesses, start containers, start MicroVMs, or read real enterprise data.
        </p>
      </div>
    </div>
  );
}

function CreateBindingDialog({ adapters, onClose, onSubmit }: { adapters: RuntimeAdapter[]; onClose: () => void; onSubmit: (d: { marketplace_agent_id: string; adapter_id: string; sandbox_policy_id?: string | null }) => void }) {
  const [mkpId, setMkpId] = useState("");
  const [adapterId, setAdapterId] = useState("rtadp_simulation");
  const [policyId, setPolicyId] = useState("");
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4" onClick={onClose}>
      <div className="os-card w-full max-w-md p-4" onClick={(event) => event.stopPropagation()}>
        <h3 className="mb-3 text-sm font-semibold text-os-text-high">Create 运行时 Binding</h3>
        <div className="space-y-3">
          <label className="block text-2xs text-os-muted">Marketplace Agent ID
            <input value={mkpId} onChange={(event) => setMkpId(event.target.value)} placeholder="mkp_..." className="mt-1 w-full rounded border border-os-border bg-os-elevated px-2 py-1.5 text-xs text-os-text-high outline-none focus:border-os-accent" />
          </label>
          <label className="block text-2xs text-os-muted">Adapter
            <select value={adapterId} onChange={(event) => setAdapterId(event.target.value)} className="mt-1 w-full rounded border border-os-border bg-os-elevated px-2 py-1.5 text-xs text-os-text-high outline-none focus:border-os-accent">
              {adapters.filter((adapter) => adapter.status === "active" || adapter.status === "beta").map((adapter) => (
                <option key={adapter.adapter_id} value={adapter.adapter_id}>{adapter.name} ({adapter.adapter_type})</option>
              ))}
            </select>
          </label>
          <label className="block text-2xs text-os-muted">Sandbox Policy ID
            <input value={policyId} onChange={(event) => setPolicyId(event.target.value)} placeholder="optional" className="mt-1 w-full rounded border border-os-border bg-os-elevated px-2 py-1.5 text-xs text-os-text-high outline-none focus:border-os-accent" />
          </label>
        </div>
        <p className="mt-3 flex items-start gap-1 text-2xs leading-5 text-amber-300"><AlertTriangle size={10} className="mt-1 shrink-0" /> Creating a binding does not execute code, install packages, or grant production runtime access.</p>
        <div className="mt-4 flex justify-end gap-2">
          <button onClick={onClose} className="rounded border border-os-border px-3 py-1.5 text-xs text-os-subtle hover:text-os-text-high">取消</button>
          <button onClick={() => onSubmit({ marketplace_agent_id: mkpId, adapter_id: adapterId, sandbox_policy_id: policyId || null })} disabled={!mkpId} className="rounded bg-os-accent px-3 py-1.5 text-xs text-white hover:bg-os-accent/90 disabled:opacity-50">创建</button>
        </div>
      </div>
    </div>
  );
}

function AssignPolicyDialog({ policies, onClose, onAssign }: { policies: SandboxPolicy[]; onClose: () => void; onAssign: (pid: string) => void }) {
  const [selected, setSelected] = useState(policies[0]?.policy_id || "");
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4" onClick={onClose}>
      <div className="os-card w-full max-w-md p-4" onClick={(event) => event.stopPropagation()}>
        <h3 className="mb-3 text-sm font-semibold text-os-text-high">Assign Sandbox Policy</h3>
        <select value={selected} onChange={(event) => setSelected(event.target.value)} className="w-full rounded border border-os-border bg-os-elevated px-2 py-1.5 text-xs text-os-text-high outline-none focus:border-os-accent">
          {policies.filter((policy) => policy.status === "active").map((policy) => (
            <option key={policy.policy_id} value={policy.policy_id}>{policy.name} ({policy.sandbox_level})</option>
          ))}
        </select>
        <p className="mt-3 flex items-start gap-1 text-2xs leading-5 text-amber-300"><AlertTriangle size={10} className="mt-1 shrink-0" /> Assigning a policy does not enable execution. It only attaches metadata governance.</p>
        <div className="mt-4 flex justify-end gap-2">
          <button onClick={onClose} className="rounded border border-os-border px-3 py-1.5 text-xs text-os-subtle hover:text-os-text-high">取消</button>
          <button onClick={() => onAssign(selected)} disabled={!selected} className="rounded bg-os-accent px-3 py-1.5 text-xs text-white hover:bg-os-accent/90 disabled:opacity-50">Assign</button>
        </div>
      </div>
    </div>
  );
}

function PolicyResultDialog({ policyId, result, onClose }: { policyId: string; result: SandboxPolicyTestResult; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4" onClick={onClose}>
      <div className="os-card w-full max-w-md p-4" onClick={(event) => event.stopPropagation()}>
        <h3 className="mb-2 text-sm font-semibold text-os-text-high">Policy Test Result: {policyId}</h3>
        <div className={`mb-2 flex items-center gap-2 rounded px-2 py-1 text-xs ${result.allowed ? "bg-emerald-400/10 text-emerald-300" : "bg-red-400/10 text-red-300"}`}>
          {result.allowed ? <CheckCircle2 size={13} /> : <XCircle size={13} />}
          Decision: {result.decision} ({result.allowed ? "Allowed" : "Denied"})
        </div>
        {result.violations.length > 0 && (
          <div className="mb-2">
            <p className="text-2xs font-medium text-red-300">Violations</p>
            {result.violations.map((violation) => <p key={violation} className="text-2xs text-red-200">{violation}</p>)}
          </div>
        )}
        {result.warnings.length > 0 && (
          <div className="mb-2">
            <p className="text-2xs font-medium text-amber-300">Warnings</p>
            {result.warnings.map((warning) => <p key={warning} className="text-2xs text-amber-200">{warning}</p>)}
          </div>
        )}
        <button onClick={onClose} className="rounded bg-os-elevated px-3 py-1.5 text-xs text-os-subtle hover:text-os-text-high">关闭</button>
      </div>
    </div>
  );
}
