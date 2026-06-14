"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Loader2, Plus, RefreshCw, Trash2 } from "lucide-react";
import { ApiKeyReveal } from "@/components/open-platform/ApiKeyReveal";
import { StatusBadge } from "@/components/open-platform/StatusBadge";
import { createDeveloperApiKey, listDeveloperApiKeys, revokeDeveloperApiKey, type DeveloperApiError } from "@/services/developer";
import type { DeveloperApiKey } from "@/types/open-platform";

export default function ApiKeysPage() {
  const [keys, setKeys] = useState<DeveloperApiKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [includeRevoked, setIncludeRevoked] = useState(false);
  const [newName, setNewName] = useState("");
  const [scopesText, setScopesText] = useState("agent:read");
  const [creating, setCreating] = useState(false);
  const [revealKey, setRevealKey] = useState<string | null>(null);
  const [revoking, setRevoking] = useState<Set<string>>(new Set());

  const fetch = useCallback(async () => {
    setLoading(true); setError(null);
    try { const r = await listDeveloperApiKeys(includeRevoked); setKeys(r.api_keys); } catch (e: unknown) { const ae = e as DeveloperApiError; setError(`[${ae.status}] ${ae.message}`); }
    finally { setLoading(false); }
  }, [includeRevoked]);

  useEffect(() => { void fetch(); }, [fetch]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault(); setError(null);
    const scopes = scopesText.split(",").map(s => s.trim()).filter(Boolean);
    if (!scopes.length) { setError("scopes 不能为空"); return; }
    setCreating(true);
    try {
      const r = await createDeveloperApiKey({ name: newName, scopes });
      setRevealKey(r.raw_key);
      setNewName(""); setScopesText("agent:read");
      await fetch();
    } catch (e: unknown) { const ae = e as DeveloperApiError; setError(`[${ae.status}] ${ae.message}`); }
    finally { setCreating(false); }
  }

  async function handleRevoke(id: string) {
    setRevoking(prev => new Set(prev).add(id));
    try { await revokeDeveloperApiKey(id); await fetch(); }
    catch (e: unknown) { const ae = e as DeveloperApiError; setError(`[${ae.status}] ${ae.message}`); }
    finally { setRevoking(prev => { const n = new Set(prev); n.delete(id); return n; }); }
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <Link href="/developer" className="mb-4 inline-flex items-center gap-1.5 text-xs text-os-subtle hover:text-os-text-high"><ArrowLeft size={14}/>开发者控制台</Link>
      <div className="mb-6 flex items-end justify-between">
        <div><h1 className="text-2xl font-semibold text-os-text-high">API Keys</h1><p className="text-sm text-os-subtle">管理开发者 API Key</p></div>
        <button onClick={() => void fetch()} disabled={loading} className="inline-flex h-9 items-center gap-2 rounded-md border border-os-border px-3 text-xs text-os-subtle hover:text-os-text-high disabled:opacity-60"><RefreshCw size={14}/>刷新</button>
      </div>

      {error && <div className="mb-4 rounded-md border border-red-400/20 bg-red-400/10 p-3 text-sm text-red-200">{error}</div>}

      {/* Create form */}
      <form onSubmit={handleCreate} className="os-card mb-4 p-4 space-y-3">
        <h3 className="text-sm font-semibold text-os-text-high flex items-center gap-2"><Plus size={14} className="text-os-accent"/> 创建 API Key</h3>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-2xs font-medium text-os-subtle">Name</label>
            <input value={newName} onChange={e => setNewName(e.target.value)} placeholder="Production Key" className="h-9 w-full rounded-md border border-os-border bg-os-elevated px-3 text-sm text-os-text-high outline-none placeholder:text-os-muted focus:border-os-accent"/>
          </div>
          <div>
            <label className="mb-1 block text-2xs font-medium text-os-subtle">Scopes (逗号分隔)</label>
            <input value={scopesText} onChange={e => setScopesText(e.target.value)} placeholder="agent:read, agent:submit" className="h-9 w-full rounded-md border border-os-border bg-os-elevated px-3 text-sm text-os-text-high outline-none placeholder:text-os-muted focus:border-os-accent"/>
          </div>
        </div>
        <button type="submit" disabled={creating || !newName}
          className="inline-flex h-9 items-center gap-2 rounded-md bg-os-accent px-4 text-xs font-medium text-white hover:bg-os-accent/90 disabled:opacity-50 disabled:cursor-not-allowed">
          {creating ? <Loader2 size={14} className="animate-spin"/> : "创建 API Key"}
        </button>
      </form>

      {/* List */}
      <div className="mb-3 flex items-center justify-between">
        <span className="text-xs text-os-subtle">{keys.length} keys</span>
        <label className="flex items-center gap-2 text-xs text-os-subtle">
          <input type="checkbox" checked={includeRevoked} onChange={e => setIncludeRevoked(e.target.checked)} className="rounded" />
          包含已撤销
        </label>
      </div>

      {loading ? <div className="space-y-2">{[1,2].map(i=><div key={i} className="os-card p-4"><div className="shimmer-bg h-4 w-32 rounded bg-os-elevated"/></div>)}</div>
        : keys.length === 0 ? <div className="os-card flex min-h-32 items-center justify-center p-4"><p className="text-sm text-os-subtle">暂无 API Key</p></div>
        : keys.map(k => (
          <div key={k.api_key_id} className="os-card mb-2 p-3">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-os-text-high">{k.name}</span>
                  <StatusBadge status={k.status} />
                </div>
                <p className="mt-0.5 font-mono text-2xs text-os-muted">{k.key_prefix}...</p>
                <div className="mt-1 flex flex-wrap gap-1">
                  {k.scopes.map(s => <span key={s} className="rounded bg-os-elevated px-1.5 py-0.5 text-2xs text-os-subtle">{s}</span>)}
                </div>
              </div>
              {k.status === "active" && (
                <button onClick={() => handleRevoke(k.api_key_id)} disabled={revoking.has(k.api_key_id)}
                  className="inline-flex h-8 items-center gap-1 rounded border border-os-border px-2 text-xs text-os-subtle hover:border-red-400/30 hover:text-red-300 disabled:opacity-50">
                  <Trash2 size={12}/> Revoke
                </button>
              )}
            </div>
          </div>
        ))}

      {revealKey && <ApiKeyReveal rawKey={revealKey} onClose={() => setRevealKey(null)} />}
    </main>
  );
}
