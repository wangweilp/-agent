"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ExternalLink, RefreshCw, Shield } from "lucide-react";
import { StatusBadge } from "@/components/open-platform/StatusBadge";
import { ReviewActionDialog } from "@/components/open-platform/ReviewActionDialog";
import { listAdminSubmissions, approveAdminSubmission, rejectAdminSubmission, requestChangesAdminSubmission, type AdminReviewApiError } from "@/services/admin-submissions";
import type { AgentSubmission } from "@/types/open-platform";

const SANDBOX_LEVEL_LABELS: Record<string, string> = {
  no_execution: "禁止执行",
  restricted: "受限执行",
  isolated: "隔离执行",
};

export default function AdminReviewQueuePage() {
  const [subs, setSubs] = useState<AgentSubmission[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusF, setStatusF] = useState("");
  const [devF, setDevF] = useState("");
  const [saving, setSaving] = useState(false);
  const [dialog, setDialog] = useState<{ type: "approve"|"reject"|"request_changes"; id: string } | null>(null);

  const fetch = useCallback(async () => {
    setLoading(true); setError(null);
    try { const r = await listAdminSubmissions({ status: statusF || undefined, developer_id: devF || undefined }); setSubs(r.submissions); }
    catch (e: unknown) { const ae = e as AdminReviewApiError; setError(`[${ae.status}] ${ae.message}`); }
    finally { setLoading(false); }
  }, [statusF, devF]);

  useEffect(() => { void fetch(); }, [fetch]);

  async function handleAction(id: string, notes: string, checklist: Record<string, unknown>) {
    setSaving(true); setError(null);
    try {
      if (dialog?.type === "approve") await approveAdminSubmission(id, { notes, checklist });
      else if (dialog?.type === "reject") await rejectAdminSubmission(id, { notes, checklist });
      else if (dialog?.type) await requestChangesAdminSubmission(id, { notes, checklist });
      setDialog(null); await fetch();
    } catch (e: unknown) { const ae = e as AdminReviewApiError; setError(`[${ae.status}] ${ae.message}`); }
    finally { setSaving(false); }
  }

  return (
    <main className="mx-auto max-w-6xl px-4 py-8">
      <header className="mb-6">
        <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-os-border bg-os-surface px-3 py-1 text-xs text-os-subtle">
          <Shield size={14} className="text-os-accent"/> 仅管理员
        </div>
        <h1 className="text-3xl font-semibold text-os-text-high">智能体提交审核</h1>
        <p className="mt-2 max-w-xl text-sm text-os-subtle">审核开发者提交的智能体 Manifest，确保权限、安全声明和企业数据边界符合要求。</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {["仅管理员", "需要审核", "禁止自动发布", "禁止远程代码执行"].map(b => (
            <span key={b} className="inline-flex items-center gap-1.5 rounded-full border border-os-border/60 bg-os-elevated px-2.5 py-1 text-2xs text-os-subtle">{b}</span>
          ))}
        </div>
      </header>

      {error && <div className="mb-4 rounded-md border border-os-danger/20 bg-os-danger-soft p-3 text-sm text-os-danger">{error}</div>}

      {/* Filters */}
      <div className="os-card mb-4 flex flex-wrap items-center gap-3 p-3">
        <div className="flex flex-wrap gap-1.5">
          {["", "submitted", "in_review", "approved", "rejected", "published", "withdrawn"].map(s => (
            <button key={s} onClick={() => setStatusF(s)}
              className={`rounded px-2 py-0.5 text-xs transition-colors ${statusF === s ? "bg-os-accent text-white" : "bg-os-elevated text-os-subtle hover:text-os-text-high"}`}>
              {(() => { const m: Record<string,string>={"":"全部","submitted":"已提交","in_review":"审核中","approved":"已通过","rejected":"已拒绝","published":"已发布","withdrawn":"已撤回"}; return m[s]; })()}
            </button>
          ))}
        </div>
        <input value={devF} onChange={e => setDevF(e.target.value)} placeholder="按开发者 ID 筛选..."
          className="h-8 rounded border border-os-border bg-os-elevated px-2 text-xs text-os-text-high outline-none placeholder:text-os-subtle focus:border-os-accent sm:w-48" />
        <button onClick={() => void fetch()} disabled={loading} className="inline-flex h-8 items-center gap-1.5 rounded border border-os-border px-2.5 text-xs text-os-subtle hover:text-os-text-high disabled:opacity-60">
          <RefreshCw size={12}/>刷新
        </button>
      </div>

      {/* List */}
      {loading ? <div className="space-y-2">{[1,2,3].map(i=><div key={i} className="os-card p-4"><div className="shimmer-bg h-4 w-48 rounded bg-os-elevated"/><div className="mt-2 flex gap-2"><div className="shimmer-bg h-3 w-24 rounded bg-os-elevated"/><div className="shimmer-bg h-3 w-16 rounded bg-os-elevated"/></div></div>)}</div>
        : error && subs.length === 0 ? null
        : subs.length === 0 ? <div className="os-card flex min-h-32 items-center justify-center p-4"><p className="text-sm text-os-subtle">暂无待审核提交</p></div>
        : subs.map(s => {
          const canReview = s.status === "submitted" || s.status === "in_review";
          const sp = s.agent_manifest?.security_profile;
          return (
            <div key={s.submission_id} className="os-card mb-2 p-3">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <Link href={`/admin/agent-submissions/${s.submission_id}`} className="min-w-0 break-words text-sm font-semibold text-os-text-high hover:text-os-accent">
                      {s.agent_manifest?.display_name || s.agent_manifest?.name || "未命名"}
                    </Link>
                    <StatusBadge status={s.status} />
                    {sp && sp.sandbox_level !== "no_execution" && <span className="flex items-center gap-0.5 text-2xs text-os-danger"><AlertTriangle size={10}/>{SANDBOX_LEVEL_LABELS[sp.sandbox_level] || sp.sandbox_level}</span>}
                  </div>
                  <div className="mt-1 flex flex-wrap gap-1.5 text-2xs text-os-subtle">
                    <span>v{s.agent_manifest?.version || "-"}</span>
                    <span>•</span>
                    <span className="font-mono">{s.developer_id.slice(0,8)}</span>
                    {s.submitted_at && <span>• {new Date(s.submitted_at).toLocaleDateString("zh-CN")}</span>}
                    {s.package_url && <span className="text-os-warning">• 含软件包 URL</span>}
                    <span>• {(s.agent_manifest?.required_permissions?.length || 0)} 项权限</span>
                    <span>• {(s.agent_manifest?.capabilities?.length || 0)} 项能力</span>
                  </div>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  <Link href={`/admin/agent-submissions/${s.submission_id}`} className="inline-flex h-7 items-center gap-1 rounded border border-os-border px-2 text-xs text-os-subtle hover:text-os-text-high">
                    <ExternalLink size={11}/>详情
                  </Link>
                  {canReview && (
                    <>
                      <button onClick={() => setDialog({ type: "approve", id: s.submission_id })}
                        className="inline-flex h-7 items-center gap-1 rounded bg-os-success-soft px-2 text-xs text-os-success hover:bg-os-success/15">通过</button>
                      <button onClick={() => setDialog({ type: "reject", id: s.submission_id })}
                        className="inline-flex h-7 items-center gap-1 rounded bg-os-danger-soft px-2 text-xs text-os-danger hover:bg-os-danger/15">拒绝</button>
                      <button onClick={() => setDialog({ type: "request_changes", id: s.submission_id })}
                        className="inline-flex h-7 items-center gap-1 rounded bg-os-warning-soft px-2 text-xs text-os-warning hover:bg-os-warning/15">请求修改</button>
                    </>
                  )}
                </div>
              </div>
            </div>
          );
        })}

      {dialog && (
        <ReviewActionDialog open={true} action={dialog.type} submissionId={dialog.id} saving={saving} error={error}
          onClose={() => setDialog(null)} onSubmit={(notes, checklist) => handleAction(dialog.id, notes, checklist)} />
      )}

      {/* Boundary Notice */}
      <section className="os-card mt-4 p-4">
        <p className="text-2xs text-os-subtle">通过仅表示审核通过；发布到智能体市场仍需后续发布流程。本页面不会直接创建市场智能体，不执行远程代码，也不产生真实支付。</p>
      </section>
    </main>
  );
}
