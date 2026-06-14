"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Activity,
  AlertTriangle,
  Ban,
  CheckCircle2,
  ClipboardList,
  FileWarning,
  FlaskConical,
  LockKeyhole,
  PackageX,
  Plus,
  Power,
  RefreshCw,
  ServerCog,
  ShieldAlert,
  ShieldCheck,
  XCircle,
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
  listRuntimeAdapters,
  listRuntimeBindings,
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
  SandboxPolicy,
  SandboxPolicyTestResult,
} from "@/types/runtime-admin";

import SandboxV2Dashboard from "@/components/open-platform/SandboxV2Dashboard";

type TabKey = "governance" | "adapters" | "bindings" | "policies" | "guide" | "sandbox-v2";

const boundaryFallback =
  "当前 Runtime/Sandbox 主要完成的是安全治理控制面、模拟运行、元数据校验、默认关闭和审计追踪能力，不等于已经完成生产级第三方代码执行沙箱。生产级执行环境需要后续接入 PostgreSQL/Redis/对象存储、真实任务队列、Rootless Container/MicroVM、只读工件物化和安全隔离验证。";

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
  const [tab, setTab] = useState<TabKey>("governance");
  const [adapters, setAdapters] = useState<RuntimeAdapter[]>([]);
  const [bindings, setBindings] = useState<DeveloperAgentRuntimeBinding[]>([]);
  const [policies, setPolicies] = useState<SandboxPolicy[]>([]);
  const [governance, setGovernance] = useState<RuntimeGovernanceSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [showCreateBind, setShowCreateBind] = useState(false);
  const [assignDialog, setAssignDialog] = useState<{ bindingId: string } | null>(null);
  const [policyDialog, setPolicyDialog] = useState<{ policyId: string } | null>(null);
  const [testResult, setTestResult] = useState<SandboxPolicyTestResult | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [a, b, p, g] = await Promise.all([
        listRuntimeAdapters(),
        listRuntimeBindings(),
        listSandboxPolicies(),
        getRuntimeGovernanceSummary(),
      ]);
      setAdapters(a.adapters);
      setBindings(b.bindings);
      setPolicies(p.policies);
      setGovernance(g);
    } catch (e: unknown) {
      setError(`[${(e as RuntimeAdminApiError).status || "ERR"}] ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void fetchAll(); }, [fetchAll]);

  const summaryTiles = useMemo(() => [
    ["Runtime Governance Status", governance?.runtime_governance_status || "metadata_only_control_plane"],
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
    if (!confirmAction("确认停用这个 Runtime Binding？")) return;
    try { await disableRuntimeBinding(id); await fetchAll(); }
    catch (e: unknown) { setError(`[${(e as RuntimeAdminApiError).status || "ERR"}] ${(e as Error).message}`); }
  }

  async function handleSuspend(id: string) {
    if (!confirmAction("确认挂起这个 Runtime Binding？")) return;
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

      <section className="mb-5 grid gap-3 md:grid-cols-4">
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
    </main>
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
      {bindings.length === 0 ? <p className="py-8 text-center text-sm text-os-subtle">暂无 Runtime Binding</p> : bindings.map((binding) => (
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
      <h3 className="flex items-center gap-2 text-sm font-semibold text-os-text-high"><Activity size={14} className="text-os-accent" /> Runtime Readiness Checklist</h3>
      <p className="mt-2 text-xs text-os-subtle">For a developer agent to be simulation-ready, the following conditions must be met. None imply real third-party code execution.</p>
      <div className="mt-4 grid gap-2 md:grid-cols-2">
        {[
          "Developer Agent published to Marketplace",
          "Tenant installed agent with required permissions granted",
          "Runtime binding exists and stays on manifest_only or simulation",
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
        <h3 className="mb-3 text-sm font-semibold text-os-text-high">Create Runtime Binding</h3>
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
