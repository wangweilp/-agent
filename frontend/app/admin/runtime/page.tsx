"use client";
import { useCallback, useEffect, useState } from "react";
import { Activity, AlertTriangle, Plus, RefreshCw, ServerCog } from "lucide-react";
import {
  listRuntimeAdapters, listRuntimeBindings, createRuntimeBinding, enableRuntimeBinding,
  disableRuntimeBinding, suspendRuntimeBinding, assignRuntimeBindingSandboxPolicy,
  listSandboxPolicies, testSandboxPolicy, enableSandboxPolicy, disableSandboxPolicy,
  type RuntimeAdminApiError,
} from "@/services/runtime-admin";
import type { RuntimeAdapter, DeveloperAgentRuntimeBinding, SandboxPolicy, SandboxPolicyTestResult } from "@/types/runtime-admin";

export default function RuntimeAdminPage() {
  const [tab, setTab] = useState<"adapters"|"bindings"|"policies"|"guide">("adapters");
  const [adapters, setAdapters] = useState<RuntimeAdapter[]>([]);
  const [bindings, setBindings] = useState<DeveloperAgentRuntimeBinding[]>([]);
  const [policies, setPolicies] = useState<SandboxPolicy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [showCreateBind, setShowCreateBind] = useState(false);
  const [assignDialog, setAssignDialog] = useState<{ bindingId: string } | null>(null);
  const [policyDialog, setPolicyDialog] = useState<{ policyId: string } | null>(null);
  const [testResult, setTestResult] = useState<SandboxPolicyTestResult | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [a, b, p] = await Promise.all([
        listRuntimeAdapters(), listRuntimeBindings(), listSandboxPolicies(),
      ]);
      setAdapters(a.adapters); setBindings(b.bindings); setPolicies(p.policies);
    } catch (e: unknown) { setError(`[${(e as RuntimeAdminApiError).status || "ERR"}] ${(e as Error).message}`); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { void fetchAll(); }, [fetchAll]);

  async function handleCreateBind(data: { marketplace_agent_id: string; adapter_id: string; sandbox_policy_id?: string | null }) {
    setError(null);
    try { await createRuntimeBinding(data); setShowCreateBind(false); await fetchAll(); }
    catch (e: unknown) { setError(`[${(e as RuntimeAdminApiError).status || "ERR"}] ${(e as Error).message}`); }
  }

  async function handleEnable(id: string) {
    try { await enableRuntimeBinding(id); await fetchAll(); }
    catch (e: unknown) { setError(`[${(e as RuntimeAdminApiError).status || "ERR"}] ${(e as Error).message}`); }
  }

  async function handleDisable(id: string) {
    try { await disableRuntimeBinding(id); await fetchAll(); }
    catch (e: unknown) { setError(`[${(e as RuntimeAdminApiError).status || "ERR"}] ${(e as Error).message}`); }
  }

  async function handleAssign(bindingId: string, policyId: string) {
    try { await assignRuntimeBindingSandboxPolicy(bindingId, policyId); setAssignDialog(null); await fetchAll(); }
    catch (e: unknown) { setError(`[${(e as RuntimeAdminApiError).status || "ERR"}] ${(e as Error).message}`); }
  }

  async function handleTestPolicy(policyId: string) {
    try { const r = await testSandboxPolicy(policyId, { sandbox_level: "simulation_only", requested_network: true, requested_domains: [], requested_filesystem_read: false, requested_filesystem_write: false, requested_secret_names: [], requested_timeout_ms: 0, requested_memory_mb: 0, requested_data_access_scope: [] }); setTestResult(r); setPolicyDialog({ policyId }); }
    catch (e: unknown) { setError(`[${(e as RuntimeAdminApiError).status || "ERR"}] ${(e as Error).message}`); }
  }

  if (loading) return <main className="mx-auto max-w-6xl px-4 py-8"><div className="os-card p-6"><div className="shimmer-bg h-6 w-48 rounded bg-os-elevated"/><div className="mt-4 space-y-2"><div className="shimmer-bg h-3 w-full rounded bg-os-elevated"/></div></div></main>;

  return (
    <main className="mx-auto max-w-6xl px-4 py-8">
      <header className="mb-6">
        <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-os-border bg-os-surface px-3 py-1 text-xs text-os-subtle">
          <ServerCog size={14} className="text-os-accent"/> Runtime Readiness — Admin Only
        </div>
        <h1 className="text-3xl font-semibold text-os-text-high">Runtime Admin</h1>
        <p className="mt-2 max-w-xl text-sm text-os-subtle">Manage developer agent runtime readiness. Simulation only. No remote code execution.</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {["No Remote Code Execution", "Simulation Only", "Admin Only", "Tenant Isolated"].map(b => (
            <span key={b} className="inline-flex items-center gap-1.5 rounded-full border border-os-border/60 bg-os-elevated px-2.5 py-1 text-2xs text-os-subtle">{b}</span>
          ))}
        </div>
      </header>

      {error && <div className="mb-4 rounded-md border border-red-400/20 bg-red-400/10 p-3 text-sm text-red-200">{error}</div>}

      {/* Tabs */}
      <div className="mb-4 flex gap-1">
        {[["adapters","Runtime Adapters"],["bindings","Runtime Bindings"],["policies","Sandbox Policies"],["guide","Readiness Guide"]].map(([k,v]) => (
          <button key={k} onClick={() => setTab(k as typeof tab)}
            className={`rounded px-3 py-1.5 text-xs transition-colors ${tab === k ? "bg-os-accent text-white" : "bg-os-elevated text-os-subtle hover:text-os-text-high"}`}>
            {v}
          </button>
        ))}
        <button onClick={() => void fetchAll()} className="ml-auto inline-flex h-8 items-center gap-1.5 rounded border border-os-border px-2.5 text-xs text-os-subtle hover:text-os-text-high">
          <RefreshCw size={12}/>刷新
        </button>
      </div>

      {/* Adapters */}
      {tab === "adapters" && (
        <div className="space-y-2">
          <p className="text-xs text-os-muted mb-2">Runtime Adapters define how developer agents interact with the system. Only manifest_only and simulation are enabled in MVP.</p>
          {adapters.map(a => (
            <div key={a.adapter_id} className="os-card p-3">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-sm font-semibold text-os-text-high">{a.name}</span>
                  <span className="ml-2 font-mono text-2xs text-os-muted">{a.adapter_type}</span>
                  <span className={`ml-2 os-badge ${a.status === "active" ? "bg-emerald-400/10 text-emerald-300" : a.status === "beta" ? "bg-amber-400/10 text-amber-300" : "bg-zinc-500/10 text-os-muted"}`}>{a.status}</span>
                </div>
                <div className="flex gap-3 text-2xs text-os-subtle">
                  {a.supports_network && <span className="text-amber-300">🌐 network</span>}
                  {a.supports_user_data_read && <span className="text-amber-300">📖 data.read</span>}
                  {a.supports_user_data_write && <span className="text-red-300">📝 data.write</span>}
                  {a.sandbox_required && <span className="text-amber-300">🔒 sandbox</span>}
                  {!a.supports_network && !a.supports_user_data_read && !a.supports_user_data_write && !a.sandbox_required &&
                    <span className="text-emerald-300">✓ no capabilities</span>}
                  <span>⏱ {a.max_timeout_ms}ms</span>
                  <span>💾 {a.max_memory_mb}MB</span>
                </div>
              </div>
              <p className="mt-1 text-2xs text-os-subtle">{a.description}</p>
              {(a.adapter_type === "http_webhook" || a.adapter_type === "sandboxed_process" || a.adapter_type === "container") && (
                <p className="mt-1 text-2xs text-amber-300 flex items-center gap-1"><AlertTriangle size={10}/> Disabled — future capability (Step 24+)</p>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Bindings */}
      {tab === "bindings" && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 mb-2">
            <p className="text-xs text-os-muted flex-1">Runtime Bindings connect Marketplace developer agents to Runtime Adapters. Enabling a binding does NOT execute code.</p>
            <button onClick={() => setShowCreateBind(true)} className="inline-flex h-8 items-center gap-1.5 rounded bg-os-accent px-3 text-xs text-white hover:bg-os-accent/90"><Plus size={12}/>Create Binding</button>
          </div>
          {bindings.length === 0 ? <p className="text-sm text-os-subtle py-8 text-center">暂无 Runtime Binding</p> : bindings.map(b => (
            <div key={b.binding_id} className="os-card p-3">
              <div className="flex items-center justify-between">
                <div>
                  <span className="font-mono text-xs text-os-text-high">{b.binding_id.slice(0,16)}</span>
                  <span className={`ml-2 os-badge ${b.runtime_status === "enabled" ? "bg-emerald-400/10 text-emerald-300" : b.runtime_status === "disabled" ? "bg-red-400/10 text-red-300" : b.runtime_status === "suspended" ? "bg-amber-400/10 text-amber-300" : "bg-zinc-500/10 text-os-muted"}`}>{b.runtime_status}</span>
                  <span className="ml-2 font-mono text-2xs text-os-muted">{b.adapter_type}</span>
                </div>
                <div className="flex gap-1">
                  {b.runtime_status !== "enabled" && (
                    <button onClick={() => handleEnable(b.binding_id)} className="rounded bg-emerald-400/10 px-2 py-0.5 text-2xs text-emerald-300 hover:bg-emerald-400/15">Enable</button>
                  )}
                  {b.runtime_status === "enabled" && (
                    <>
                      <button onClick={() => handleDisable(b.binding_id)} className="rounded bg-red-400/10 px-2 py-0.5 text-2xs text-red-300 hover:bg-red-400/15">Disable</button>
                      <button onClick={() => { suspendRuntimeBinding(b.binding_id); setTimeout(fetchAll, 300); }} className="rounded bg-amber-400/10 px-2 py-0.5 text-2xs text-amber-300 hover:bg-amber-400/15">Suspend</button>
                    </>
                  )}
                  <button onClick={() => setAssignDialog({ bindingId: b.binding_id })} className="rounded border border-os-border px-2 py-0.5 text-2xs text-os-subtle hover:text-os-text-high">Policy</button>
                </div>
              </div>
              <div className="mt-1 flex flex-wrap gap-2 text-2xs text-os-subtle">
                <span>mkp: {b.marketplace_agent_id.slice(0,12)}</span>
                <span>• dev: {b.developer_id.slice(0,10)}</span>
                <span>• tenant: {b.tenant_id}</span>
                {b.sandbox_policy_id && <span className="text-violet-300">• policy: {b.sandbox_policy_id}</span>}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Policies */}
      {tab === "policies" && (
        <div className="space-y-2">
          <p className="text-xs text-os-muted mb-2">Sandbox Policies define security boundaries. They are policy models — not container sandboxes. No code execution is enabled by assigning a policy.</p>
          {policies.map(p => (
            <div key={p.policy_id} className="os-card p-3">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-sm font-semibold text-os-text-high">{p.name}</span>
                  <span className="ml-2 os-badge bg-violet-400/10 text-violet-300">{p.sandbox_level}</span>
                  <span className={`ml-2 os-badge ${p.scope === "system" ? "bg-blue-400/10 text-blue-300" : "bg-zinc-500/10 text-os-muted"}`}>{p.scope}</span>
                  {p.system_managed && <span className="ml-2 text-2xs text-os-muted">🔒 system managed</span>}
                </div>
                <div className="flex gap-1">
                  <button onClick={() => handleTestPolicy(p.policy_id)} className="rounded border border-os-border px-2 py-0.5 text-2xs text-os-subtle hover:text-os-text-high">Test</button>
                  {p.status === "active" ? (
                    !p.system_managed && <button onClick={() => { disableSandboxPolicy(p.policy_id); setTimeout(fetchAll, 300); }} className="rounded bg-red-400/10 px-2 py-0.5 text-2xs text-red-300 hover:bg-red-400/15">Disable</button>
                  ) : (
                    <button onClick={() => { enableSandboxPolicy(p.policy_id); setTimeout(fetchAll, 300); }} className="rounded bg-emerald-400/10 px-2 py-0.5 text-2xs text-emerald-300 hover:bg-emerald-400/15">Enable</button>
                  )}
                </div>
              </div>
              <p className="mt-1 text-2xs text-os-subtle">{p.description}</p>
              <div className="mt-1 flex flex-wrap gap-1.5 text-2xs">
                {p.allow_network && <span className="text-amber-300">🌐 net</span>}
                {p.allow_filesystem_read && <span className="text-amber-300">📖 fs.read</span>}
                {p.allow_filesystem_write && <span className="text-red-300">📝 fs.write</span>}
                {p.allow_secrets && <span className="text-red-300">🔑 secrets</span>}
                {!p.allow_network && !p.allow_filesystem_read && !p.allow_filesystem_write && !p.allow_secrets &&
                  <span className="text-emerald-300">✓ no capabilities</span>}
                <span className="text-os-muted">| ⏱{p.max_timeout_ms}ms 💾{p.max_memory_mb}MB</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Guide */}
      {tab === "guide" && (
        <div className="os-card p-4 space-y-3">
          <h3 className="text-sm font-semibold text-os-text-high flex items-center gap-2"><Activity size={14} className="text-os-accent"/> Runtime Readiness Checklist</h3>
          <p className="text-xs text-os-subtle">For a developer agent to be simulation-ready, the following conditions must be met. None imply real code execution.</p>
          {["Developer Agent published to Marketplace", "Tenant installed agent with required permissions granted", "Runtime binding exists (created by admin)", "Binding is enabled (simulation adapter, e.g. simulation)", "Sandbox policy assigned (if required by adapter)", "API Key has agent:simulate or agent:execute:simulation scope (for API-triggered simulation)", "Simulation returns deterministic dry-run result — no external code executed"].map((item, i) => (
            <div key={i} className="flex items-start gap-2">
              <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-os-border text-2xs text-os-subtle">{i + 1}</div>
              <p className="text-xs text-os-text-high">{item}</p>
            </div>
          ))}
          <div className="mt-3 rounded border border-amber-400/20 bg-amber-400/5 p-3">
            <p className="text-xs text-amber-300 flex items-center gap-1"><AlertTriangle size={12}/> <strong>Important:</strong> Simulation does NOT execute external code. No package_url is downloaded or executed. No network calls are made. No real enterprise data is accessed. This is a safe dry-run validation of the install → permissions → binding → policy chain.</p>
          </div>
        </div>
      )}

      {/* Create Binding Dialog */}
      {showCreateBind && <CreateBindingDialog adapters={adapters} onClose={() => setShowCreateBind(false)} onSubmit={handleCreateBind}/>}

      {/* Assign Policy Dialog */}
      {assignDialog && <AssignPolicyDialog policies={policies} onClose={() => setAssignDialog(null)} onAssign={(pid: string) => handleAssign(assignDialog.bindingId, pid)}/>}

      {/* Policy Test Dialog */}
      {policyDialog && testResult && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => { setPolicyDialog(null); setTestResult(null); }}>
          <div className="os-card w-full max-w-md p-4" onClick={e => e.stopPropagation()}>
            <h3 className="text-sm font-semibold text-os-text-high mb-2">Policy Test Result: {policyDialog.policyId}</h3>
            <div className={`mb-2 rounded px-2 py-1 text-xs ${testResult.allowed ? "bg-emerald-400/10 text-emerald-300" : "bg-red-400/10 text-red-300"}`}>
              Decision: {testResult.decision} ({testResult.allowed ? "Allowed" : "Denied"})
            </div>
            {testResult.violations.length > 0 && (
              <div className="mb-2"><p className="text-2xs text-red-300 font-medium">Violations:</p>
                {testResult.violations.map((v: string, i: number) => <p key={i} className="text-2xs text-red-200">• {v}</p>)}
              </div>
            )}
            {testResult.warnings.length > 0 && (
              <div className="mb-2"><p className="text-2xs text-amber-300 font-medium">Warnings:</p>
                {testResult.warnings.map((w: string, i: number) => <p key={i} className="text-2xs text-amber-200">• {w}</p>)}
              </div>
            )}
            <button onClick={() => { setPolicyDialog(null); setTestResult(null); }} className="rounded bg-os-elevated px-3 py-1.5 text-xs text-os-subtle hover:text-os-text-high">关闭</button>
          </div>
        </div>
      )}
    </main>
  );
}

function CreateBindingDialog({ adapters, onClose, onSubmit }: { adapters: RuntimeAdapter[]; onClose: () => void; onSubmit: (d: { marketplace_agent_id: string; adapter_id: string; sandbox_policy_id?: string | null }) => void }) {
  const [mkpId, setMkpId] = useState(""); const [adapterId, setAdapterId] = useState("rtadp_simulation"); const [policyId, setPolicyId] = useState("");
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="os-card w-full max-w-md p-4" onClick={e => e.stopPropagation()}>
        <h3 className="text-sm font-semibold text-os-text-high mb-3">Create Runtime Binding</h3>
        <div className="space-y-3">
          <div><label className="text-2xs text-os-muted">Marketplace Agent ID</label><input value={mkpId} onChange={e => setMkpId(e.target.value)} placeholder="mkp_..." className="mt-0.5 w-full rounded border border-os-border bg-os-elevated px-2 py-1.5 text-xs text-os-text-high outline-none focus:border-os-accent"/></div>
          <div><label className="text-2xs text-os-muted">Adapter</label>
            <select value={adapterId} onChange={e => setAdapterId(e.target.value)} className="mt-0.5 w-full rounded border border-os-border bg-os-elevated px-2 py-1.5 text-xs text-os-text-high outline-none focus:border-os-accent">
              {adapters.filter(a => a.status === "active" || a.status === "beta").map(a => <option key={a.adapter_id} value={a.adapter_id}>{a.name} ({a.adapter_type})</option>)}
            </select>
          </div>
          <div><label className="text-2xs text-os-muted">Sandbox Policy ID (optional)</label><input value={policyId} onChange={e => setPolicyId(e.target.value)} placeholder="sbxpol_..." className="mt-0.5 w-full rounded border border-os-border bg-os-elevated px-2 py-1.5 text-xs text-os-text-high outline-none focus:border-os-accent"/></div>
        </div>
        <p className="mt-3 text-2xs text-amber-300 flex items-center gap-1"><AlertTriangle size={10}/> Creating a binding does NOT execute code, install the agent, publish the agent, or grant data access. Pending binding requires manual enablement.</p>
        <div className="mt-4 flex gap-2 justify-end">
          <button onClick={onClose} className="rounded border border-os-border px-3 py-1.5 text-xs text-os-subtle hover:text-os-text-high">取消</button>
          <button onClick={() => onSubmit({ marketplace_agent_id: mkpId, adapter_id: adapterId, sandbox_policy_id: policyId || null })} disabled={!mkpId}
            className="rounded bg-os-accent px-3 py-1.5 text-xs text-white hover:bg-os-accent/90 disabled:opacity-50">创建</button>
        </div>
      </div>
    </div>
  );
}

function AssignPolicyDialog({ policies, onClose, onAssign }: { policies: SandboxPolicy[]; onClose: () => void; onAssign: (pid: string) => void }) {
  const [sel, setSel] = useState(policies[0]?.policy_id || "");
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="os-card w-full max-w-md p-4" onClick={e => e.stopPropagation()}>
        <h3 className="text-sm font-semibold text-os-text-high mb-3">Assign Sandbox Policy</h3>
        <select value={sel} onChange={e => setSel(e.target.value)} className="w-full rounded border border-os-border bg-os-elevated px-2 py-1.5 text-xs text-os-text-high outline-none focus:border-os-accent">
          {policies.filter(p => p.status === "active").map(p => <option key={p.policy_id} value={p.policy_id}>{p.name} ({p.sandbox_level})</option>)}
        </select>
        <p className="mt-3 text-2xs text-amber-300 flex items-center gap-1"><AlertTriangle size={10}/> Assigning a policy does NOT enable execution. SandboxPolicy is a policy model, not a container sandbox. Binding remains in its current state.</p>
        <div className="mt-4 flex gap-2 justify-end">
          <button onClick={onClose} className="rounded border border-os-border px-3 py-1.5 text-xs text-os-subtle hover:text-os-text-high">取消</button>
          <button onClick={() => onAssign(sel)} className="rounded bg-os-accent px-3 py-1.5 text-xs text-white hover:bg-os-accent/90">Assign</button>
        </div>
      </div>
    </div>
  );
}
