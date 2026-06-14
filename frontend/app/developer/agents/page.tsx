"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ExternalLink, Loader2, Plus, RefreshCw } from "lucide-react";
import { StatusBadge } from "@/components/open-platform/StatusBadge";
import { listDeveloperSubmissions, withdrawDeveloperSubmission, type DeveloperApiError } from "@/services/developer";
import type { AgentSubmission } from "@/types/open-platform";

export default function DeveloperAgentsPage() {
  const [subs, setSubs] = useState<AgentSubmission[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [withdrawing, setWithdrawing] = useState<Set<string>>(new Set());

  const fetch = useCallback(async () => {
    setLoading(true); setError(null);
    try { const r = await listDeveloperSubmissions({ status: statusFilter || undefined, include_withdrawn: true }); setSubs(r.submissions); }
    catch (e: unknown) { const ae = e as DeveloperApiError; setError(`[${ae.status}] ${ae.message}`); }
    finally { setLoading(false); }
  }, [statusFilter]);

  useEffect(() => { void fetch(); }, [fetch]);

  async function handleWithdraw(id: string) {
    setWithdrawing(prev => new Set(prev).add(id));
    try { await withdrawDeveloperSubmission(id); await fetch(); }
    catch (e: unknown) { const ae = e as DeveloperApiError; setError(`[${ae.status}] ${ae.message}`); }
    finally { setWithdrawing(prev => { const n = new Set(prev); n.delete(id); return n; }); }
  }

  return (
    <main className="mx-auto max-w-4xl px-4 py-8">
      <Link href="/developer" className="mb-4 inline-flex items-center gap-1.5 text-xs text-os-subtle hover:text-os-text-high"><ArrowLeft size={14}/>开发者控制台</Link>
      <div className="mb-6 flex items-end justify-between">
        <div><h1 className="text-2xl font-semibold text-os-text-high">智能体提交</h1><p className="text-sm text-os-subtle">{subs.length} 个提交</p></div>
        <div className="flex items-center gap-2">
          <Link href="/developer/agents/new" className="inline-flex h-9 items-center gap-2 rounded-md bg-os-accent px-3 text-xs font-medium text-white hover:bg-os-accent/90"><Plus size={14}/>新建</Link>
          <button onClick={() => void fetch()} disabled={loading} className="inline-flex h-9 items-center gap-2 rounded-md border border-os-border px-3 text-xs text-os-subtle hover:text-os-text-high disabled:opacity-60"><RefreshCw size={14}/>刷新</button>
        </div>
      </div>

      {error && <div className="mb-4 rounded-md border border-red-400/20 bg-red-400/10 p-3 text-sm text-red-200">{error}</div>}

      {/* Status filter */}
      <div className="mb-3 flex flex-wrap gap-1.5">
        {["", "draft", "submitted", "in_review", "approved", "rejected", "published", "withdrawn"].map(s => (
          <button key={s} onClick={() => setStatusFilter(s)}
            className={`rounded px-2 py-0.5 text-xs transition-colors ${statusFilter === s ? "bg-os-accent text-white" : "bg-os-elevated text-os-subtle hover:text-os-text-high"}`}>
            {s || "All"}
          </button>
        ))}
      </div>

      {loading ? <div className="space-y-2">{[1,2,3].map(i=><div key={i} className="os-card p-4"><div className="shimmer-bg h-4 w-40 rounded bg-os-elevated"/></div>)}</div>
        : subs.length === 0 ? <div className="os-card flex min-h-32 items-center justify-center p-4"><p className="text-sm text-os-subtle">暂无 Agent Submission</p></div>
        : subs.map(s => (
          <div key={s.submission_id} className="os-card os-card-hover mb-2 p-3">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <Link href={`/developer/agents/${s.submission_id}`} className="text-sm font-semibold text-os-text-high hover:text-os-accent truncate">
                    {s.agent_manifest?.display_name || s.agent_manifest?.name || "(untitled)"}
                  </Link>
                  <StatusBadge status={s.status} />
                </div>
                <div className="mt-1 flex flex-wrap gap-1.5 text-2xs text-os-subtle">
                  <span>v{s.agent_manifest?.version || "-"}</span>
                  <span>•</span>
                  <span>{s.agent_manifest?.name || s.submission_id.slice(0,8)}</span>
                  {s.review_notes && <span className="text-amber-300 max-w-[200px] truncate">• {s.review_notes}</span>}
                </div>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <Link href={`/developer/agents/${s.submission_id}`} className="inline-flex h-7 items-center gap-1 rounded border border-os-border px-2 text-xs text-os-subtle hover:text-os-text-high"><ExternalLink size={11}/>详情</Link>
                {(s.status === "submitted" || s.status === "in_review") && (
                  <button onClick={() => handleWithdraw(s.submission_id)} disabled={withdrawing.has(s.submission_id)}
                    className="inline-flex h-7 items-center gap-1 rounded border border-os-border px-2 text-xs text-os-subtle hover:border-red-400/30 hover:text-red-300 disabled:opacity-50">
                    {withdrawing.has(s.submission_id) ? <Loader2 size={11} className="animate-spin"/> : "撤回"}
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}
    </main>
  );
}
