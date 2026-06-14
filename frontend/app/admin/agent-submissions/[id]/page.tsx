"use client";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { AlertTriangle, ArrowLeft, CheckCircle2, Clock, ExternalLink, Loader2, Shield, XCircle } from "lucide-react";
import { StatusBadge } from "@/components/open-platform/StatusBadge";
import { SecurityProfilePanel } from "@/components/open-platform/SecurityProfilePanel";
import { ReviewActionDialog } from "@/components/open-platform/ReviewActionDialog";
import {
  getAdminSubmission, listAdminSubmissionReviews, startAdminSubmissionReview,
  approveAdminSubmission, rejectAdminSubmission, requestChangesAdminSubmission,
  publishAdminSubmission, type AdminReviewApiError,
} from "@/services/admin-submissions";
import type { AgentSubmission, AgentReviewRecord, DeveloperAccount, ManifestValidationResult } from "@/types/open-platform";

export default function AdminReviewDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [sub, setSub] = useState<AgentSubmission | null>(null);
  const [dev, setDev] = useState<DeveloperAccount | null>(null);
  const [validation, setValidation] = useState<ManifestValidationResult | null>(null);
  const [reviews, setReviews] = useState<AgentReviewRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [showPublishConfirm, setShowPublishConfirm] = useState(false);
  const [dialog, setDialog] = useState<{ type: "approve"|"reject"|"request_changes" } | null>(null);

  const fetch = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const d = await getAdminSubmission(id);
      setSub(d.submission); setDev(d.developer); setValidation(d.validation);
      try { const rv = await listAdminSubmissionReviews(id); setReviews(rv.reviews); } catch { /* */ }
    } catch (e: unknown) { const ae = e as AdminReviewApiError; setError(`[${ae.status}] ${ae.message}`); }
    finally { setLoading(false); }
  }, [id]);

  useEffect(() => { void fetch(); }, [fetch]);

  async function handleStartReview() {
    setSaving(true); setError(null);
    try { await startAdminSubmissionReview(id); await fetch(); } catch (e: unknown) { const ae = e as AdminReviewApiError; setError(`[${ae.status}] ${ae.message}`); }
    finally { setSaving(false); }
  }

  async function handleAction(notes: string, checklist: Record<string, unknown>) {
    if (!dialog) return;
    setSaving(true); setError(null);
    try {
      if (dialog.type === "approve") await approveAdminSubmission(id, { notes, checklist });
      else if (dialog.type === "reject") await rejectAdminSubmission(id, { notes, checklist });
      else await requestChangesAdminSubmission(id, { notes, checklist });
      setDialog(null); await fetch();
    } catch (e: unknown) { const ae = e as AdminReviewApiError; setError(`[${ae.status}] ${ae.message}`); }
    finally { setSaving(false); }
  }

  async function handlePublish() {
    setPublishing(true); setError(null);
    try {
      const result = await publishAdminSubmission(id);
      setSub(result.submission);
      setShowPublishConfirm(false);
    } catch (e: unknown) { const ae = e as AdminReviewApiError; setError(`[${ae.status}] ${ae.message}`); }
    finally { setPublishing(false); }
  }

  if (loading) return <main className="mx-auto max-w-4xl px-4 py-8"><div className="os-card p-6"><div className="shimmer-bg h-6 w-48 rounded bg-os-elevated"/><div className="mt-4 space-y-2"><div className="shimmer-bg h-3 w-full rounded bg-os-elevated"/><div className="shimmer-bg h-3 w-3/4 rounded bg-os-elevated"/></div></div></main>;
  if (!sub) return <main className="mx-auto max-w-4xl px-4 py-8"><div className="os-card flex min-h-32 items-center justify-center p-4"><p className="text-sm text-os-text-high">Submission 不存在</p></div></main>;

  const sp = sub.agent_manifest?.security_profile || null;
  const canReview = sub.status === "submitted" || sub.status === "in_review";
  const hasWarnings = validation && validation.warnings.length > 0;
  const hasErrors = validation && !validation.valid;
  const canApprove = canReview && !hasErrors && !hasWarnings;

  return (
    <main className="mx-auto max-w-4xl px-4 py-8">
      <Link href="/admin/agent-submissions" className="mb-4 inline-flex items-center gap-1.5 text-xs text-os-subtle hover:text-os-text-high"><ArrowLeft size={14}/>审核队列</Link>

      {error && <div className="mb-4 rounded-md border border-red-400/20 bg-red-400/10 p-3 text-sm text-red-200">{error}</div>}

      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-os-text-high">{sub.agent_manifest?.display_name || "(untitled)"}</h1>
          <span className="font-mono text-2xs text-os-muted">{sub.submission_id}</span>
        </div>
        <StatusBadge status={sub.status} />
      </div>

      {/* Info Grid */}
      <section className="os-card mb-4 p-4">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 text-xs">
          <Info label="Developer ID" value={sub.developer_id} mono/>
          <Info label="Tenant" value={sub.tenant_id} mono/>
          <Info label="Source" value={sub.source_type}/>
          <Info label="Package URL" value={sub.package_url || "-"}/>
          <Info label="Mkp Agent ID" value={sub.marketplace_agent_id || "-"} mono/>
          <Info label="提交时间" value={sub.submitted_at ? new Date(sub.submitted_at).toLocaleString("zh-CN") : "-"}/>
          <Info label="审核时间" value={sub.reviewed_at ? new Date(sub.reviewed_at).toLocaleString("zh-CN") : "-"}/>
          <Info label="审核人" value={sub.reviewed_by || "-"}/>
        </div>
      </section>

      {/* Developer Profile */}
      {dev && (
        <section className="os-card mb-4 p-4">
          <h3 className="mb-3 text-sm font-semibold text-os-text-high flex items-center gap-2"><ExternalLink size={14}/> 开发者信息</h3>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 text-xs">
            <Info label="Display Name" value={dev.display_name}/>
            <Info label="Organization" value={dev.organization_name || "-"}/>
            <Info label="Contact" value={dev.contact_email}/>
            <div><p className="text-2xs text-os-muted">Status</p><StatusBadge status={dev.status}/></div>
          </div>
          <p className="mt-1 font-mono text-2xs text-os-muted">{dev.developer_id}{dev.verified ? " ✓ Verified" : ""}</p>
        </section>
      )}

      {/* Security Profile */}
      <div className="mb-4"><SecurityProfilePanel sp={sp}/></div>

      {/* Validation */}
      {validation && (
        <section className="os-card mb-4 p-4">
          <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-os-text-high">
            {ValidationIcon(validation)} Manifest 校验
          </h3>
          {hasErrors && <div className="rounded border border-red-400/20 bg-red-400/5 p-2 mb-2">
            <p className="text-xs text-red-300 font-medium">错误 — 无法通过审核：</p>
            {validation.errors.map((e,i)=><p key={i} className="text-2xs text-red-200">• {e}</p>)}
          </div>}
          {hasWarnings && <div className="rounded border border-amber-400/20 bg-amber-400/5 p-2">
            <p className="text-xs text-amber-300 font-medium">警告 — 需在审核通过前解决：</p>
            {validation.warnings.map((w,i)=><p key={i} className="text-2xs text-amber-200">• {w}</p>)}
          </div>}
          {!hasErrors && !hasWarnings && <p className="text-xs text-emerald-300">所有检查通过</p>}
        </section>
      )}

      {/* Review Actions */}
      <section className="os-card mb-4 p-4">
        <h3 className="mb-3 text-sm font-semibold text-os-text-high flex items-center gap-2"><Shield size={14} className="text-os-accent"/> 审核操作</h3>
        <div className="flex flex-wrap gap-2">
          {sub.status === "submitted" && (
            <button onClick={handleStartReview} disabled={saving}
              className="inline-flex h-8 items-center gap-1.5 rounded border border-os-border px-3 text-xs text-os-subtle hover:text-os-text-high disabled:opacity-50">
              {saving ? <Loader2 size={12} className="animate-spin"/> : "开始审核"}
            </button>
          )}
          {canReview && (
            <>
              {canApprove ? (
                <button onClick={() => setDialog({ type: "approve" })}
                  className="inline-flex h-8 items-center gap-1.5 rounded bg-emerald-400/10 px-3 text-xs text-emerald-300 hover:bg-emerald-400/15">通过</button>
              ) : (
                <button disabled className="inline-flex h-8 items-center gap-1.5 rounded bg-zinc-500/10 px-3 text-xs text-os-muted cursor-not-allowed" title={hasErrors ? "Manifest 无效" : "安全警告未解决"}>
                  通过（不可用）
                </button>
              )}
              <button onClick={() => setDialog({ type: "reject" })}
                className="inline-flex h-8 items-center gap-1.5 rounded bg-red-400/10 px-3 text-xs text-red-300 hover:bg-red-400/15">拒绝</button>
              <button onClick={() => setDialog({ type: "request_changes" })}
                className="inline-flex h-8 items-center gap-1.5 rounded bg-amber-400/10 px-3 text-xs text-amber-300 hover:bg-amber-400/15">请求修改</button>
            </>
          )}
          {sub.status === "approved" && !sub.marketplace_agent_id && (
            <div>
              <p className="text-xs text-emerald-300 flex items-center gap-1 mb-2"><CheckCircle2 size={12}/> 已通过 — 可以发布</p>
              {showPublishConfirm ? (
                <div className="inline-flex flex-wrap items-center gap-2 rounded border border-amber-400/20 bg-amber-400/5 px-3 py-2">
                  <span className="text-xs text-amber-300">此操作将创建市场智能体条目。不会执行 package_url、不为任何租户安装、也不启用支付。</span>
                  <button onClick={handlePublish} disabled={publishing} className="rounded bg-os-accent px-2 py-0.5 text-xs text-white hover:bg-os-accent/90 disabled:opacity-50">
                    {publishing ? <Loader2 size={12} className="animate-spin"/> : "确认发布"}
                  </button>
                  <button onClick={() => setShowPublishConfirm(false)} className="rounded px-2 py-0.5 text-xs text-os-subtle hover:text-os-text-high">取消</button>
                </div>
              ) : (
                <button onClick={() => setShowPublishConfirm(true)}
                  className="inline-flex h-8 items-center gap-1.5 rounded bg-violet-400/10 px-3 text-xs text-violet-300 hover:bg-violet-400/15">
                  发布到智能体市场
                </button>
              )}
            </div>
          )}
          {sub.status === "published" && sub.marketplace_agent_id && (
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-xs text-violet-300 flex items-center gap-1"><CheckCircle2 size={12}/> 已发布</p>
              <Link href={`/agent-marketplace/${sub.marketplace_agent_id}`} className="text-xs text-os-accent hover:underline font-mono">{sub.marketplace_agent_id}</Link>
            </div>
          )}
          {sub.status === "rejected" && sub.review_notes && (
            <p className="text-xs text-red-300 flex items-center gap-1"><XCircle size={12}/> 已拒绝：{sub.review_notes.slice(0, 200)}</p>
          )}
        </div>
      </section>

      {/* Manifest */}
      <section className="os-card mb-4 p-4">
        <h3 className="mb-2 text-sm font-semibold text-os-text-high">智能体清单</h3>
        {sub.agent_manifest && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 text-xs mb-3">
            <Info label="Name" value={sub.agent_manifest.name}/>
            <Info label="Version" value={sub.agent_manifest.version}/>
            <Info label="Runtime" value={sub.agent_manifest.runtime_type}/>
            <Info label="Entrypoint" value={sub.agent_manifest.entrypoint || "-"}/>
          </div>
        )}
        {sub.agent_manifest?.capabilities && sub.agent_manifest.capabilities.length > 0 && (
          <div className="mb-2"><p className="text-2xs text-os-muted mb-1">Capabilities</p>
            <div className="flex flex-wrap gap-1">{sub.agent_manifest.capabilities.map((c,i)=><span key={i} className="rounded bg-os-elevated px-2 py-0.5 text-2xs text-os-text-high">{c}</span>)}</div>
          </div>
        )}
        {sub.agent_manifest?.required_permissions && sub.agent_manifest.required_permissions.length > 0 && (
          <div className="mb-2"><p className="text-2xs text-os-muted mb-1">Required Permissions</p>
            <div className="flex flex-wrap gap-1">{sub.agent_manifest.required_permissions.map((p,i)=><span key={i} className="rounded bg-amber-400/10 px-2 py-0.5 text-2xs text-amber-300">{p}</span>)}</div>
          </div>
        )}
        <details className="mt-2">
          <summary className="cursor-pointer text-xs text-os-subtle hover:text-os-text-high">Full Manifest JSON</summary>
          <pre className="mt-2 overflow-auto rounded bg-os-elevated p-3 font-mono text-2xs text-os-subtle max-h-96">{JSON.stringify(sub.agent_manifest, null, 2)}</pre>
        </details>
      </section>

      {/* Review Records */}
      <section className="os-card mb-4 p-4">
        <h3 className="mb-3 text-sm font-semibold text-os-text-high flex items-center gap-2"><Clock size={14} className="text-os-accent"/> 审核记录 ({reviews.length})</h3>
        {reviews.length === 0 ? <p className="text-xs text-os-subtle">暂无审核记录</p> : reviews.map(r => (
          <div key={r.review_id} className="mb-2 rounded border border-os-border bg-os-elevated/30 p-3">
            <div className="flex items-center gap-2">
              <span className={`os-badge ${r.decision === "approve" ? "bg-emerald-400/10 text-emerald-300" : r.decision === "reject" ? "bg-red-400/10 text-red-300" : "bg-amber-400/10 text-amber-300"}`}>{r.decision}</span>
              <span className="text-xs text-os-subtle">by {r.reviewer_id}</span>
              <span className="text-2xs text-os-muted">{new Date(r.created_at).toLocaleString("zh-CN")}</span>
            </div>
            {r.notes && <p className="mt-1 text-xs text-os-text-high">{r.notes}</p>}
            {Object.keys(r.checklist).length > 0 && <details className="mt-1"><summary className="cursor-pointer text-2xs text-os-subtle">Checklist</summary><pre className="mt-1 text-2xs text-os-subtle">{JSON.stringify(r.checklist, null, 2)}</pre></details>}
          </div>
        ))}
      </section>

      {/* Publish Boundary */}
      <section className="os-card p-4">
        <p className="text-2xs text-os-subtle">审核通过不代表发布。市场发布将在后续发布流程中实现。本审核页面不能创建市场智能体。不执行远程代码，不产生真实支付，无收入分成。</p>
      </section>

      {dialog && (
        <ReviewActionDialog open={true} action={dialog.type} submissionId={id} saving={saving} error={error}
          onClose={() => setDialog(null)} onSubmit={handleAction} />
      )}
    </main>
  );
}

function Info({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return <div><p className="text-2xs text-os-muted">{label}</p><p className={`mt-0.5 ${mono ? "font-mono" : ""} text-xs text-os-text-high truncate`}>{value}</p></div>;
}

function ValidationIcon(v: ManifestValidationResult) {
  if (!v.valid) return <XCircle size={14} className="text-red-400"/>;
  if (v.warnings.length > 0) return <AlertTriangle size={14} className="text-amber-400"/>;
  return <CheckCircle2 size={14} className="text-emerald-400"/>;
}
