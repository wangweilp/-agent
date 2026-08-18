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
  "当前运行时沙箱主要完成的是安全治理控制面、模拟运行、元数据校验、默认关闭和审计追踪能力，不等于已经完成生产级第三方代码执行沙箱。生产级执行环境需要后续接入 PostgreSQL/Redis/对象存储、真实任务队列、Rootless Container/MicroVM、只读工件物化和安全隔离验证。";

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

const RUNTIME_VALUE_LABELS: Record<string, string> = {
  metadata_only_control_plane: "仅元数据控制平面",
  "metadata-only / simulation": "仅元数据 / 模拟运行",
  metadata_only: "仅元数据",
  manifest_only: "仅清单",
  simulation_only: "仅模拟",
  simulation: "模拟运行",
  deny_by_default: "默认拒绝",
  "deny by default / fail closed": "默认拒绝 / 故障关闭",
  active: "运行中",
  inactive: "未运行",
  enabled: "已启用",
  disabled: "未启用",
  suspended: "已挂起",
  beta: "测试中",
  resolved: "已解决",
  investigating: "调查中",
  allowed: "允许",
  denied: "拒绝",
  allow: "允许",
  deny: "拒绝",
  blocked: "已拦截",
  passed: "已通过",
  ready: "就绪",
  not_ready: "未就绪",
  true: "是",
  false: "否",
  critical: "严重",
  high: "高",
  medium: "中",
  low: "低",
  system: "系统级",
};

const RUNTIME_FIELD_LABELS: Record<string, string> = {
  severity: "风险等级",
  status: "状态",
  title: "标题",
  related_runtime: "关联运行时",
  decision: "判定",
  deny_reason: "拒绝原因",
  read_only_policy: "只读策略",
  execution_status: "执行状态",
  mode: "模式",
  metadata_only: "仅元数据",
  name: "名称",
  evidence: "依据",
};

function runtimeValueLabel(value: string): string {
  return RUNTIME_VALUE_LABELS[value] || value;
}

function riskClass(risk: string) {
  if (risk === "critical") return "border-red-200 bg-red-50 text-red-700";
  if (risk === "high") return "border-amber-200 bg-amber-50 text-amber-800";
  if (risk === "medium") return "border-sky-200 bg-sky-50 text-sky-700";
  return "border-emerald-200 bg-emerald-50 text-emerald-700";
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
    ["运行时治理状态", governance?.runtime_governance_status || "metadata_only_control_plane"],
    ["当前运行模式", governance?.current_mode || "metadata-only / simulation"],
    ["生产沙箱", governance?.production_sandbox || "disabled"],
    ["默认安全策略", governance?.default_policy || "deny by default / fail closed"],
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
    if (!confirmAction("启用操作只允许 metadata/simulation 绑定，不代表真实执行代码。确认继续？")) return;
    try { await enableRuntimeBinding(id); await fetchAll(); }
    catch (e: unknown) { setError(`[${(e as RuntimeAdminApiError).status || "ERR"}] ${(e as Error).message}`); }
  }

  async function handleDisable(id: string) {
    if (!confirmAction("确认停用这个运行时绑定？")) return;
    try { await disableRuntimeBinding(id); await fetchAll(); }
    catch (e: unknown) { setError(`[${(e as RuntimeAdminApiError).status || "ERR"}] ${(e as Error).message}`); }
  }

  async function handleSuspend(id: string) {
    if (!confirmAction("确认挂起这个运行时绑定？")) return;
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
      ? "确认启用这个沙箱策略？它仍然不会启用真实代码执行。"
      : "确认停用这个沙箱策略？";
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
            <span key={label} className="inline-flex items-center gap-1.5 rounded-full border border-os-border bg-os-elevated px-2.5 py-1 text-2xs text-os-subtle">
              {label}
            </span>
          ))}
        </div>
      </header>

      <section className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {summaryTiles.map(([label, value]) => (
          <div key={label} className="os-card p-4">
            <p className="text-xs font-medium text-os-subtle">{label}</p>
            <p className="mt-2 break-words text-sm font-semibold text-os-text-high">
              {runtimeValueLabel(value)}
            </p>
          </div>
        ))}
      </section>

      {error && (
        <div className="mb-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
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
  "当前隔离层处于元数据（Metadata）模拟模式。MicroVM 与容器化底层需要依赖 PostgreSQL 与分布式队列集群，已列入下一阶段工程演进路线。";

function severityStyle(sev: string): string {
  if (sev === "critical") return "border-red-200 bg-red-50 text-red-700";
  if (sev === "high") return "border-amber-200 bg-amber-50 text-amber-800";
  if (sev === "medium") return "border-sky-200 bg-sky-50 text-sky-700";
  return "border-emerald-200 bg-emerald-50 text-emerald-700";
}

function statusStyle(status: string): string {
  if (status === "resolved") return "text-emerald-700";
  if (status === "investigating") return "text-amber-800";
  return "text-red-700";
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
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 shadow-sm sm:p-6">
        <div className="flex items-start gap-3 sm:gap-4">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-amber-200 bg-amber-100 text-amber-700 sm:h-11 sm:w-11">
            <AlertTriangle size={22} />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-amber-950">生产环境演进提示</h3>
            <p className="mt-1.5 text-sm leading-6 text-amber-900">{ROADMAP_BANNER_TEXT}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {["PostgreSQL 集群", "分布式任务队列", "Rootless Container", "MicroVM 隔离", "只读工件物化"].map((tag) => (
                <span key={tag} className="inline-flex max-w-full items-center gap-1 rounded-lg border border-amber-200 bg-white/70 px-2.5 py-1 text-xs font-medium text-amber-900">
                  {tag}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* ── Panel 1: Overview Status ── */}
      <div className="os-card relative rounded-xl p-6 overflow-hidden">
        <div className="absolute top-0 left-0 right-0 h-px bg-os-info" />
        <div className="flex items-start justify-between gap-4 mb-6 sm:items-center">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-os-border bg-os-elevated text-os-accent">
              <ShieldCheck size={20} />
            </div>
            <div>
              <h2 className="text-base font-semibold text-os-text-high">全局安全状态</h2>
              <p className="text-xs text-os-subtle">安全控制平面概览</p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <span className="relative flex h-2.5 w-2.5">
              <span className="absolute inline-flex h-full w-full rounded-full bg-os-success opacity-40 animate-status-breathe" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-os-success" />
            </span>
            <span className="text-xs font-medium text-emerald-700">
              {runtimeValueLabel(status?.status || "active")}
            </span>
          </div>
        </div>

        <div className="grid gap-6 md:grid-cols-3">
          {/* Mode */}
          <div className="relative overflow-hidden rounded-xl border border-os-border bg-os-surface-tinted p-5 sm:p-6">
            <div className="absolute top-0 left-0 right-0 h-px bg-os-info" />
            <div className="flex items-center gap-2 mb-3">
              <Zap size={14} className="text-os-info" />
              <span className="text-xs font-medium text-os-subtle">运行模式</span>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-xl font-bold text-os-info sm:text-2xl">{runtimeValueLabel(mode)}</span>
              <span className="text-xs text-os-subtle">模拟沙箱</span>
            </div>
            <p className="mt-2 text-xs leading-5 text-os-subtle">
              所有执行能力以元数据形式模拟，无真实进程/容器/网络操作
            </p>
          </div>

          {/* Default Policy */}
          <div className="rounded-xl border border-os-border bg-os-surface-tinted p-5 sm:p-6">
            <div className="flex items-center gap-2 mb-3">
              <ShieldX size={14} className="text-os-danger" />
              <span className="text-xs font-medium text-os-subtle">高危操作策略</span>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-xl font-bold text-os-danger sm:text-2xl">
                {defaultPolicy === "deny_by_default" ? "故障关闭" : runtimeValueLabel(defaultPolicy)}
              </span>
            </div>
            <p className="mt-2 text-xs leading-5 text-os-subtle">
              默认拒绝 · 未知风险一律拦截 · 仅元数据审计可通过
            </p>
          </div>

          {/* Production Sandbox */}
          <div className="rounded-xl border border-os-border bg-os-surface-tinted p-5 sm:p-6">
            <div className="flex items-center gap-2 mb-3">
              <LockKeyhole size={14} className="text-os-warning" />
              <span className="text-xs font-medium text-os-subtle">生产级沙箱</span>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-xl font-bold text-os-warning sm:text-2xl">
                {runtimeValueLabel(productionSandbox)}
              </span>
            </div>
            <p className="mt-2 text-xs leading-5 text-os-subtle">
              MicroVM / 容器隔离层未启用 · 等待基础设施就绪
            </p>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-2 text-xs">
          <span className="rounded-lg border border-os-border bg-os-elevated px-2.5 py-1 text-os-subtle">
            模式：{runtimeValueLabel(mode)}
          </span>
          <span className="rounded-lg border border-os-border bg-os-elevated px-2.5 py-1 text-os-subtle">
            默认策略：{runtimeValueLabel(defaultPolicy)}
          </span>
          <span className="rounded-lg border border-os-border bg-os-elevated px-2.5 py-1 text-os-subtle">
            生产沙箱：{runtimeValueLabel(productionSandbox)}
          </span>
          {status?.last_checked_at && (
            <span className="rounded-lg border border-os-border bg-os-elevated px-2.5 py-1 text-os-subtle">
              最近检查：{status.last_checked_at.slice(0, 19)}
            </span>
          )}
        </div>
      </div>

      {/* ── Panel 2: Kill Switch ── */}
      <div className="os-card rounded-xl p-6">
        <div className="mb-6 flex items-start justify-between gap-4 sm:items-center">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-os-danger/20 bg-os-danger-soft text-os-danger">
              <Siren size={20} />
            </div>
            <div>
              <h2 className="text-base font-semibold text-os-text-high">一键熔断开关</h2>
              <p className="text-xs text-os-subtle">紧急停止控制</p>
            </div>
          </div>
          <span className="shrink-0 rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-800">
            就绪 · 模拟模式
          </span>
        </div>

        <div className="flex flex-col items-center gap-5 rounded-xl border border-os-border bg-os-surface-tinted p-8">
          <button
            onClick={onKillSwitch}
            className="group relative flex h-32 w-32 items-center justify-center rounded-full border-2 border-os-danger/40 bg-os-danger-soft shadow-sm transition-all hover:border-os-danger hover:bg-red-100 active:scale-95 focus-visible:ring-2 focus-visible:ring-os-danger/25"
            title="紧急熔断（模拟）"
            aria-label="触发紧急熔断模拟"
          >
            <div className="absolute inset-3 rounded-full border border-os-danger/20" />
            <Power size={42} className="relative text-os-danger transition-colors group-hover:text-red-800" strokeWidth={2.5} />
          </button>
          <div className="text-center">
            <p className="text-sm font-semibold text-os-danger">紧急熔断</p>
            <p className="mt-1 text-xs text-os-subtle">点击触发模拟熔断 · 二次确认后执行</p>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="rounded-lg border border-os-border bg-os-surface-tinted p-3 text-center">
            <p className="text-xs text-os-subtle">拦截总数</p>
            <p className="mt-1 text-xl font-bold text-os-text-high">{incidents.length}</p>
          </div>
          <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-center">
            <p className="text-xs text-red-700">严重</p>
            <p className="mt-1 text-xl font-bold text-os-danger">{criticalCount}</p>
          </div>
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-center">
            <p className="text-xs text-amber-800">高</p>
            <p className="mt-1 text-xl font-bold text-os-warning">{highCount}</p>
          </div>
        </div>
      </div>

      {/* ── Panel 3: Incident Telemetry ── */}
      <div className="os-card rounded-xl p-6">
        <div className="mb-6 flex items-start justify-between gap-4 sm:items-center">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-os-border bg-os-elevated text-os-accent">
              <Activity size={20} />
            </div>
            <div>
              <h2 className="text-base font-semibold text-os-text-high">拦截遥测数据</h2>
              <p className="text-xs text-os-subtle">安全事件遥测 · 模拟数据流</p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-3 text-xs">
            <span className="text-os-subtle">已解决 <span className="font-mono font-bold text-emerald-700">{resolvedCount}</span>/{incidents.length}</span>
          </div>
        </div>

        {incidents.length === 0 ? (
          <div className="rounded-xl border border-os-border bg-os-surface-tinted">
            <EmptyState
              icon={ShieldCheck}
              message="暂无拦截记录"
              description="系统未记录到任何安全事件 · 控制面运行正常"
            />
          </div>
        ) : (
          <div className="w-full overflow-x-auto rounded-xl border border-os-border">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-os-border bg-os-surface-tinted">
                  <th className="px-4 py-3 font-medium text-os-subtle">时间</th>
                  <th className="px-4 py-3 font-medium text-os-subtle">智能体 ID</th>
                  <th className="px-4 py-3 font-medium text-os-subtle">事件类型</th>
                  <th className="px-4 py-3 font-medium text-os-subtle">描述</th>
                  <th className="px-4 py-3 font-medium text-os-subtle">风险等级</th>
                  <th className="px-4 py-3 font-medium text-os-subtle">拦截状态</th>
                </tr>
              </thead>
              <tbody>
                {incidents.map((inc) => {
                  const Icon = incidentTypeIcon(inc.incident_type);
                  const isCritical = inc.severity === "critical";
                  const rowClass = isCritical
                    ? "border-b border-os-border/70 border-l-2 border-l-os-danger bg-red-50/70 transition-colors hover:bg-red-50"
                    : "border-b border-os-border/70 transition-colors hover:bg-os-surface-hover";
                  return (
                    <tr key={inc.incident_id} className={rowClass}>
                      <td className="px-4 py-3.5 font-mono text-2xs text-os-subtle whitespace-nowrap">
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
                          {runtimeValueLabel(inc.severity)}
                        </span>
                      </td>
                      <td className="px-4 py-3.5">
                        <span className={`text-2xs font-medium ${statusStyle(inc.status)}`}>
                          {inc.status === "resolved" && <CheckCircle2 size={11} className="inline mr-1" />}
                          {inc.status === "investigating" && <AlertTriangle size={11} className="inline mr-1" />}
                          {runtimeValueLabel(inc.status)}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        <p className="mt-3 text-xs text-os-subtle">
          所有拦截记录均为模拟数据 · 仅元数据（metadata-only）· 无真实执行被阻止
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/20 backdrop-blur-sm px-4">
      <div className="w-full max-w-lg overflow-hidden rounded-xl border border-red-200 bg-os-base shadow-os-lg">
        {/* Header */}
        <div className="border-b border-red-200 bg-red-50 p-6">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-red-200 bg-white text-os-danger">
              <Siren size={22} />
            </div>
            <div>
              <h3 className="text-base font-semibold text-os-danger">紧急熔断确认</h3>
              <p className="text-xs text-red-700">请确认模拟熔断范围</p>
            </div>
          </div>
        </div>

        {/* Body */}
        <div className="p-6 space-y-4">
          {stage === "confirm" && (
            <>
              <div className="rounded-xl border border-red-200 bg-red-50 p-4">
                <p className="text-sm leading-6 text-red-800">
                  您即将触发 <span className="font-bold">模拟熔断</span>。此操作在当前模拟运行模式下不会影响任何真实进程，仅用于验证控制面的治理能力。
                </p>
              </div>
              <div className="space-y-2 text-xs text-os-subtle">
                <p className="flex items-center gap-2">
                  <CheckCircle2 size={12} className="text-os-success" />
                  将向所有活跃运行时绑定广播挂起（suspend）信号（模拟）
                </p>
                <p className="flex items-center gap-2">
                  <CheckCircle2 size={12} className="text-os-success" />
                  将标记 kill_switch.status = triggered_metadata_only
                </p>
                <p className="flex items-center gap-2">
                  <CheckCircle2 size={12} className="text-os-success" />
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
                  className="flex-1 rounded-xl border border-os-danger bg-os-danger px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-os-danger-hover focus-visible:ring-2 focus-visible:ring-os-danger/25"
                >
                  <Power size={14} className="inline mr-1.5" />
                  确认熔断
                </button>
              </div>
            </>
          )}

          {stage === "executing" && (
            <div className="flex flex-col items-center py-8">
              <div className="h-12 w-12 animate-spin rounded-full border-2 border-red-200 border-t-os-danger" />
              <p className="mt-4 text-sm text-os-text-high">正在广播熔断信号...</p>
              <p className="mt-1 text-xs text-os-subtle">向所有活跃运行时绑定发送挂起（suspend）指令（模拟）</p>
            </div>
          )}

          {stage === "done" && (
            <div className="flex flex-col items-center py-8">
              <div className="flex h-14 w-14 items-center justify-center rounded-full border border-emerald-200 bg-emerald-50 text-emerald-700">
                <CheckCircle2 size={28} />
              </div>
              <p className="mt-4 text-sm font-semibold text-emerald-700">熔断信号已广播</p>
              <p className="mt-1 text-xs text-os-subtle">所有运行时绑定已标记为 suspended_metadata_only</p>
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
            <button disabled title="只读元数据 API" className="inline-flex h-8 items-center gap-1 rounded border border-os-border bg-os-surface-muted px-2 text-2xs text-os-subtle disabled:cursor-not-allowed">
              <ShieldAlert size={12} />启用
            </button>
            <button disabled title="只读元数据 API" className="inline-flex h-8 items-center gap-1 rounded border border-os-border bg-os-surface-muted px-2 text-2xs text-os-subtle disabled:cursor-not-allowed">
              <Ban size={12} />停用
            </button>
            <button disabled title="汇总数据中的历史端点为只读" className="inline-flex h-8 items-center gap-1 rounded border border-os-border bg-os-surface-muted px-2 text-2xs text-os-subtle disabled:cursor-not-allowed">
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
              <div key={item} className="rounded border border-red-200 bg-red-50 px-2.5 py-2 text-2xs text-red-800">
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
          {runtimeValueLabel(panel.risk_level)}
        </span>
      </div>
      <div className="mt-3 flex flex-wrap gap-2 text-2xs">
        <Badge label={runtimeValueLabel(panel.status)} tone={panel.enabled ? "good" : "warn"} />
        <Badge label={runtimeValueLabel(panel.mode)} tone="neutral" />
        <Badge label={runtimeValueLabel(panel.enabled ? "enabled" : "disabled")} tone={panel.enabled ? "good" : "bad"} />
      </div>
      <div className="mt-3 space-y-1">
        {panel.evidence.slice(0, 3).map((item) => (
          <p key={item} className="flex gap-2 text-2xs leading-5 text-os-subtle">
            <CheckCircle2 size={12} className="mt-0.5 shrink-0 text-os-success" />
            <span>{item}</span>
          </p>
        ))}
      </div>
      <p className="mt-3 rounded border border-os-border bg-os-surface-tinted px-2.5 py-2 text-2xs leading-5 text-os-subtle">
        {panel.recommended_next_step}
      </p>
      {children}
    </article>
  );
}

function MiniTable({ rows, fields }: { rows: Record<string, unknown>[]; fields: string[] }) {
  if (!rows.length) return <p className="mt-3 text-2xs text-os-subtle">暂无记录</p>;
  return (
    <div className="mt-3 overflow-hidden rounded border border-os-border">
      {rows.slice(0, 4).map((row, index) => (
        <div key={index} className="grid gap-2 border-b border-os-border/70 px-2.5 py-2 text-2xs last:border-b-0 md:grid-cols-3">
          {fields.slice(0, 3).map((field) => (
            <div key={field} className="min-w-0">
              <p className="text-os-subtle">{RUNTIME_FIELD_LABELS[field] || field}</p>
              <p className="mt-0.5 truncate text-os-text-high" title={formatValue(row[field])}>
                {runtimeValueLabel(formatValue(row[field]))}
              </p>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

function Badge({ label, tone }: { label: string; tone: "good" | "warn" | "bad" | "neutral" }) {
  const cls = tone === "good" ? "border-emerald-200 bg-emerald-50 text-emerald-800"
    : tone === "warn" ? "border-amber-200 bg-amber-50 text-amber-900"
      : tone === "bad" ? "border-red-200 bg-red-50 text-red-700"
        : "border-os-border bg-os-surface-muted text-os-subtle";
  return <span className={`os-badge ${cls}`}>{label}</span>;
}

function AdaptersView({ adapters }: { adapters: RuntimeAdapter[] }) {
  return (
    <div className="space-y-2">
      <p className="mb-2 text-xs leading-5 text-os-subtle">
        当前元数据 / 模拟运行边界仅允许 manifest_only 与 simulation 模式。
      </p>
      {adapters.map((adapter) => (
        <div key={adapter.adapter_id} className="os-card p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <span className="text-sm font-semibold text-os-text-high">{adapter.name}</span>
              <span className="ml-2 font-mono text-2xs text-os-subtle">{adapter.adapter_type}</span>
              <span className={`ml-2 os-badge ${adapter.status === "active" ? "border-emerald-200 bg-emerald-50 text-emerald-800" : adapter.status === "beta" ? "border-amber-200 bg-amber-50 text-amber-900" : "border-os-border bg-os-surface-muted text-os-subtle"}`}>
                {runtimeValueLabel(adapter.status)}
              </span>
            </div>
            <div className="flex flex-wrap gap-2 text-2xs text-os-subtle">
              {adapter.supports_network && <span className="text-amber-800">network</span>}
              {adapter.supports_user_data_read && <span className="text-amber-800">data.read</span>}
              {adapter.supports_user_data_write && <span className="text-red-700">data.write</span>}
              {adapter.sandbox_required && <span className="text-amber-800">sandbox</span>}
              {!adapter.supports_network && !adapter.supports_user_data_read && !adapter.supports_user_data_write && !adapter.sandbox_required && <span className="text-emerald-700">无可用能力</span>}
              <span>{adapter.max_timeout_ms}ms</span>
              <span>{adapter.max_memory_mb}MB</span>
            </div>
          </div>
          <p className="mt-1 text-2xs text-os-subtle">{adapter.description}</p>
          {(adapter.adapter_type === "http_webhook" || adapter.adapter_type === "sandboxed_process" || adapter.adapter_type === "container") && (
            <p className="mt-1 flex items-center gap-1 text-2xs text-amber-800"><AlertTriangle size={10} /> 未来能力，当前未启用</p>
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
      <div className="mb-2 flex flex-col items-start gap-3 sm:flex-row sm:items-center">
        <p className="flex-1 text-xs leading-5 text-os-subtle">运行时绑定用于连接 Marketplace 开发者智能体与允许的元数据 / 模拟适配器；启用绑定不会执行代码。</p>
        <button onClick={onCreate} className="inline-flex h-8 shrink-0 items-center gap-1.5 whitespace-nowrap rounded bg-os-accent px-3 text-xs text-white hover:bg-os-accent/90 focus-visible:ring-2 focus-visible:ring-os-accent/25">
          <Plus size={12} />创建绑定
        </button>
      </div>
      {bindings.length === 0 ? <p className="py-8 text-center text-sm text-os-subtle">暂无运行时绑定</p> : bindings.map((binding) => (
        <div key={binding.binding_id} className="os-card p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <span className="font-mono text-xs text-os-text-high">{binding.binding_id.slice(0, 16)}</span>
              <span className={`ml-2 os-badge ${binding.runtime_status === "enabled" ? "border-emerald-200 bg-emerald-50 text-emerald-800" : binding.runtime_status === "disabled" ? "border-red-200 bg-red-50 text-red-700" : binding.runtime_status === "suspended" ? "border-amber-200 bg-amber-50 text-amber-900" : "border-os-border bg-os-surface-muted text-os-subtle"}`}>
                {runtimeValueLabel(binding.runtime_status)}
              </span>
              <span className="ml-2 font-mono text-2xs text-os-subtle">{binding.adapter_type}</span>
            </div>
            <div className="flex flex-wrap gap-1">
              {binding.runtime_status !== "enabled" && (
                <button onClick={() => onEnable(binding.binding_id)} className="rounded bg-emerald-50 px-2 py-0.5 text-2xs text-emerald-800 hover:bg-emerald-100">启用</button>
              )}
              {binding.runtime_status === "enabled" && (
                <>
                  <button onClick={() => onDisable(binding.binding_id)} className="rounded bg-red-50 px-2 py-0.5 text-2xs text-red-700 hover:bg-red-100">停用</button>
                  <button onClick={() => onSuspend(binding.binding_id)} className="rounded bg-amber-50 px-2 py-0.5 text-2xs text-amber-900 hover:bg-amber-100">挂起</button>
                </>
              )}
              <button onClick={() => onAssign(binding.binding_id)} className="rounded border border-os-border px-2 py-0.5 text-2xs text-os-subtle hover:text-os-text-high">分配策略</button>
            </div>
          </div>
          <div className="mt-1 flex flex-wrap gap-2 text-2xs text-os-subtle">
            <span>Marketplace：{binding.marketplace_agent_id.slice(0, 12)}</span>
            <span>开发者：{binding.developer_id.slice(0, 10)}</span>
            <span>租户：{binding.tenant_id}</span>
            {binding.sandbox_policy_id && <span className="text-os-memory-violet">策略：{binding.sandbox_policy_id}</span>}
          </div>
        </div>
      ))}
    </div>
  );
}

function PoliciesView({ policies, onTest, onStatusChange }: { policies: SandboxPolicy[]; onTest: (id: string) => void; onStatusChange: (id: string, next: "enable" | "disable") => void }) {
  return (
    <div className="space-y-2">
      <p className="mb-2 text-xs leading-5 text-os-subtle">沙箱策略用于定义模拟运行与未来运行时规划的边界；它们是策略模型，并非容器沙箱。</p>
      {policies.map((policy) => (
        <div key={policy.policy_id} className="os-card p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <span className="text-sm font-semibold text-os-text-high">{policy.name}</span>
              <span className="ml-2 os-badge border-violet-200 bg-violet-50 text-violet-800">{runtimeValueLabel(policy.sandbox_level)}</span>
              <span className={`ml-2 os-badge ${policy.scope === "system" ? "border-sky-200 bg-sky-50 text-sky-800" : "border-os-border bg-os-surface-muted text-os-subtle"}`}>{runtimeValueLabel(policy.scope)}</span>
            </div>
            <div className="flex gap-1">
              <button onClick={() => onTest(policy.policy_id)} className="rounded border border-os-border px-2 py-0.5 text-2xs text-os-subtle hover:text-os-text-high">测试</button>
              {policy.status === "active" ? (
                !policy.system_managed && <button onClick={() => onStatusChange(policy.policy_id, "disable")} className="rounded bg-red-50 px-2 py-0.5 text-2xs text-red-700 hover:bg-red-100">停用</button>
              ) : (
                <button onClick={() => onStatusChange(policy.policy_id, "enable")} className="rounded bg-emerald-50 px-2 py-0.5 text-2xs text-emerald-800 hover:bg-emerald-100">启用</button>
              )}
            </div>
          </div>
          <p className="mt-1 text-2xs text-os-subtle">{policy.description}</p>
          <div className="mt-1 flex flex-wrap gap-1.5 text-2xs">
            {policy.allow_network && <span className="text-amber-800">network</span>}
            {policy.allow_filesystem_read && <span className="text-amber-800">fs.read</span>}
            {policy.allow_filesystem_write && <span className="text-red-700">fs.write</span>}
            {policy.allow_secrets && <span className="text-red-700">secrets</span>}
            {!policy.allow_network && !policy.allow_filesystem_read && !policy.allow_filesystem_write && !policy.allow_secrets && <span className="text-emerald-700">无可用能力</span>}
            <span className="text-os-subtle">超时 {policy.max_timeout_ms}ms / 内存 {policy.max_memory_mb}MB</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function GuideView() {
  return (
    <div className="os-card p-4">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-os-text-high"><Activity size={14} className="text-os-accent" /> 运行时就绪清单</h3>
      <p className="mt-2 text-xs leading-5 text-os-subtle">开发者智能体要达到模拟运行就绪状态，必须满足以下条件；这些条件均不代表已具备真实第三方代码执行能力。</p>
      <div className="mt-4 grid gap-2 md:grid-cols-2">
        {[
          "开发者智能体已发布到 Marketplace",
          "租户已安装智能体并授予所需权限",
          "运行时绑定已创建，并保持 manifest_only 或 simulation 模式",
          "需要时已分配沙箱策略",
          "模拟运行返回确定性的试运行结果",
          "隔离能力实现前，生产沙箱门禁保持未启用",
        ].map((item, index) => (
          <div key={item} className="flex items-start gap-2">
            <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-os-border text-2xs text-os-subtle">{index + 1}</div>
            <p className="text-xs text-os-text-high">{item}</p>
          </div>
        ))}
      </div>
      <div className="mt-4 rounded border border-amber-200 bg-amber-50 p-3">
        <p className="flex items-start gap-2 text-xs leading-5 text-amber-900">
          <AlertTriangle size={13} className="mt-0.5 shrink-0 text-amber-700" />
          模拟运行不会下载软件包、发起外部网络调用、执行子进程、启动容器或 MicroVM，也不会读取真实企业数据。
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/20 px-4" onClick={onClose}>
      <div className="os-card w-full max-w-md p-4" onClick={(event) => event.stopPropagation()}>
        <h3 className="mb-3 text-sm font-semibold text-os-text-high">创建运行时绑定</h3>
        <div className="space-y-3">
          <label className="block text-2xs text-os-subtle">Marketplace 智能体 ID
            <input value={mkpId} onChange={(event) => setMkpId(event.target.value)} placeholder="mkp_..." className="mt-1 w-full rounded border border-os-border bg-os-elevated px-2 py-1.5 text-xs text-os-text-high outline-none focus:border-os-accent focus-visible:ring-2 focus-visible:ring-os-accent/20" />
          </label>
          <label className="block text-2xs text-os-subtle">适配器
            <select value={adapterId} onChange={(event) => setAdapterId(event.target.value)} className="mt-1 w-full rounded border border-os-border bg-os-elevated px-2 py-1.5 text-xs text-os-text-high outline-none focus:border-os-accent focus-visible:ring-2 focus-visible:ring-os-accent/20">
              {adapters.filter((adapter) => adapter.status === "active" || adapter.status === "beta").map((adapter) => (
                <option key={adapter.adapter_id} value={adapter.adapter_id}>{adapter.name} ({adapter.adapter_type})</option>
              ))}
            </select>
          </label>
          <label className="block text-2xs text-os-subtle">沙箱策略 ID
            <input value={policyId} onChange={(event) => setPolicyId(event.target.value)} placeholder="可选" className="mt-1 w-full rounded border border-os-border bg-os-elevated px-2 py-1.5 text-xs text-os-text-high outline-none placeholder:text-os-subtle focus:border-os-accent focus-visible:ring-2 focus-visible:ring-os-accent/20" />
          </label>
        </div>
        <p className="mt-3 flex items-start gap-1 rounded border border-amber-200 bg-amber-50 p-2.5 text-2xs leading-5 text-amber-900"><AlertTriangle size={10} className="mt-1 shrink-0 text-amber-700" /> 创建绑定不会执行代码、安装软件包或授予生产运行时访问权限。</p>
        <div className="mt-4 flex justify-end gap-2">
          <button onClick={onClose} className="rounded border border-os-border px-3 py-1.5 text-xs text-os-subtle hover:text-os-text-high">取消</button>
          <button onClick={() => onSubmit({ marketplace_agent_id: mkpId, adapter_id: adapterId, sandbox_policy_id: policyId || null })} disabled={!mkpId} className="rounded bg-os-accent px-3 py-1.5 text-xs text-white hover:bg-os-accent/90 disabled:cursor-not-allowed disabled:bg-os-surface-muted disabled:text-os-subtle">创建</button>
        </div>
      </div>
    </div>
  );
}

function AssignPolicyDialog({ policies, onClose, onAssign }: { policies: SandboxPolicy[]; onClose: () => void; onAssign: (pid: string) => void }) {
  const [selected, setSelected] = useState(policies[0]?.policy_id || "");
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/20 px-4" onClick={onClose}>
      <div className="os-card w-full max-w-md p-4" onClick={(event) => event.stopPropagation()}>
        <h3 className="mb-3 text-sm font-semibold text-os-text-high">分配沙箱策略</h3>
        <select value={selected} onChange={(event) => setSelected(event.target.value)} aria-label="选择沙箱策略" className="w-full rounded border border-os-border bg-os-elevated px-2 py-1.5 text-xs text-os-text-high outline-none focus:border-os-accent focus-visible:ring-2 focus-visible:ring-os-accent/20">
          {policies.filter((policy) => policy.status === "active").map((policy) => (
            <option key={policy.policy_id} value={policy.policy_id}>{policy.name} ({policy.sandbox_level})</option>
          ))}
        </select>
        <p className="mt-3 flex items-start gap-1 rounded border border-amber-200 bg-amber-50 p-2.5 text-2xs leading-5 text-amber-900"><AlertTriangle size={10} className="mt-1 shrink-0 text-amber-700" /> 分配策略不会启用执行能力，只会附加元数据治理规则。</p>
        <div className="mt-4 flex justify-end gap-2">
          <button onClick={onClose} className="rounded border border-os-border px-3 py-1.5 text-xs text-os-subtle hover:text-os-text-high">取消</button>
          <button onClick={() => onAssign(selected)} disabled={!selected} className="rounded bg-os-accent px-3 py-1.5 text-xs text-white hover:bg-os-accent/90 disabled:cursor-not-allowed disabled:bg-os-surface-muted disabled:text-os-subtle">分配</button>
        </div>
      </div>
    </div>
  );
}

function PolicyResultDialog({ policyId, result, onClose }: { policyId: string; result: SandboxPolicyTestResult; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/20 px-4" onClick={onClose}>
      <div className="os-card w-full max-w-md p-4" onClick={(event) => event.stopPropagation()}>
        <h3 className="mb-2 text-sm font-semibold text-os-text-high">策略测试结果：{policyId}</h3>
        <div className={`mb-2 flex items-center gap-2 rounded border px-2 py-1 text-xs ${result.allowed ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-red-200 bg-red-50 text-red-700"}`}>
          {result.allowed ? <CheckCircle2 size={13} /> : <XCircle size={13} />}
          判定：{runtimeValueLabel(result.decision)}（{result.allowed ? "允许" : "拒绝"}）
        </div>
        {result.violations.length > 0 && (
          <div className="mb-2">
            <p className="text-2xs font-medium text-red-700">违规项</p>
            {result.violations.map((violation) => <p key={violation} className="text-2xs text-red-700">{violation}</p>)}
          </div>
        )}
        {result.warnings.length > 0 && (
          <div className="mb-2">
            <p className="text-2xs font-medium text-amber-800">警告</p>
            {result.warnings.map((warning) => <p key={warning} className="text-2xs text-amber-800">{warning}</p>)}
          </div>
        )}
        <button onClick={onClose} className="rounded bg-os-elevated px-3 py-1.5 text-xs text-os-subtle hover:text-os-text-high">关闭</button>
      </div>
    </div>
  );
}
