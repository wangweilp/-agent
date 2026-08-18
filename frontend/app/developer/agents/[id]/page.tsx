"use client";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, CheckCircle2, Loader2, XCircle } from "lucide-react";
import { StatusBadge } from "@/components/open-platform/StatusBadge";
import {
  getDeveloperSubmission, updateDeveloperSubmission, validateDeveloperSubmission,
  submitDeveloperSubmission, withdrawDeveloperSubmission, type DeveloperApiError,
} from "@/services/developer";
import type { AgentSubmission, ManifestValidationResult } from "@/types/open-platform";

export default function SubmissionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [sub, setSub] = useState<AgentSubmission | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [manifestText, setManifestText] = useState("");
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [withdrawing, setWithdrawing] = useState(false);
  const [validation, setValidation] = useState<ManifestValidationResult | null>(null);
  const [validating, setValidating] = useState(false);

  const fetch = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const r = await getDeveloperSubmission(id);
      setSub(r.submission);
      if (r.submission.agent_manifest) setManifestText(JSON.stringify(r.submission.agent_manifest, null, 2));
    } catch (e: unknown) { const ae = e as DeveloperApiError; setError(`[${ae.status}] ${ae.message}`); }
    finally { setLoading(false); }
  }, [id]);

  useEffect(() => { void fetch(); }, [fetch]);

  async function handleSave() {
    let m: Record<string, unknown>;
    try { m = JSON.parse(manifestText); } catch { setError("Manifest JSON 格式错误"); return; }
    setSaving(true); setError(null);
    try { const r = await updateDeveloperSubmission(id, { agent_manifest: m }); setSub(r.submission); }
    catch (e: unknown) { const ae = e as DeveloperApiError; setError(`[${ae.status}] ${ae.message}`); }
    finally { setSaving(false); }
  }

  async function handleValidate() {
    setValidating(true); setError(null);
    try { const r = await validateDeveloperSubmission(id); setValidation(r); }
    catch (e: unknown) { const ae = e as DeveloperApiError; setError(`[${ae.status}] ${ae.message}`); }
    finally { setValidating(false); }
  }

  async function handleSubmit() {
    setSubmitting(true); setError(null);
    try { const r = await submitDeveloperSubmission(id); setSub(r.submission); }
    catch (e: unknown) { const ae = e as DeveloperApiError; setError(`[${ae.status}] ${ae.message}`); }
    finally { setSubmitting(false); }
  }

  async function handleWithdraw() {
    setWithdrawing(true); setError(null);
    try { const r = await withdrawDeveloperSubmission(id); setSub(r.submission); }
    catch (e: unknown) { const ae = e as DeveloperApiError; setError(`[${ae.status}] ${ae.message}`); }
    finally { setWithdrawing(false); }
  }

  if (loading) return <main className="mx-auto max-w-3xl px-4 py-8"><div className="os-card p-6"><div className="shimmer-bg h-6 w-48 rounded bg-os-elevated"/><div className="mt-4 space-y-2"><div className="shimmer-bg h-3 w-full rounded bg-os-elevated"/><div className="shimmer-bg h-3 w-3/4 rounded bg-os-elevated"/></div></div></main>;
  if (!sub) return <main className="mx-auto max-w-3xl px-4 py-8"><div className="os-card flex min-h-32 items-center justify-center p-4"><p className={error ? "text-sm text-os-danger" : "text-sm text-os-text-high"}>{error || "智能体提交不存在"}</p></div></main>;

  const isDraft = sub.status === "draft";
  const canWithdraw = sub.status === "submitted" || sub.status === "in_review";

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <Link href="/developer/agents" className="mb-4 inline-flex items-center gap-1.5 text-xs text-os-subtle hover:text-os-text-high"><ArrowLeft size={14}/>智能体提交</Link>

      {error && <div className="mb-4 rounded-md border border-os-danger/20 bg-os-danger-soft p-3 text-sm text-os-danger">{error}</div>}

      {/* Header */}
      <div className="mb-4 flex items-start justify-between gap-3 sm:items-center">
        <div className="min-w-0">
          <h1 className="break-words text-xl font-semibold text-os-text-high">{sub.agent_manifest?.display_name || "未命名"}</h1>
          <span className="break-all font-mono text-2xs text-os-subtle">{sub.submission_id}</span>
        </div>
        <StatusBadge status={sub.status} />
      </div>

      {/* Manifest editor / viewer */}
      <section className="os-card mb-4 p-4">
        <h3 className="mb-3 text-sm font-semibold text-os-text-high">智能体 Manifest</h3>
        {isDraft ? (
          <>
            <textarea rows={18} value={manifestText} onChange={e => setManifestText(e.target.value)} spellCheck={false}
              className="w-full rounded-md border border-os-border bg-os-elevated px-3 py-2 font-mono text-xs text-os-text-high outline-none focus:border-os-accent" />
            <div className="mt-3 flex flex-wrap gap-2">
              <button onClick={handleSave} disabled={saving} className="inline-flex h-8 items-center gap-1.5 rounded border border-os-border px-3 text-xs text-os-subtle hover:text-os-text-high disabled:opacity-50">
                {saving ? <Loader2 size={12} className="animate-spin"/> : "保存草稿"}
              </button>
              <button onClick={handleValidate} disabled={validating} className="inline-flex h-8 items-center gap-1.5 rounded border border-os-border px-3 text-xs text-os-subtle hover:text-os-text-high disabled:opacity-50">
                {validating ? <Loader2 size={12} className="animate-spin"/> : "校验"}
              </button>
              <button onClick={handleSubmit} disabled={submitting} className="inline-flex h-8 items-center gap-1.5 rounded bg-os-accent px-3 text-xs font-medium text-white hover:bg-os-accent/90 disabled:opacity-50">
                {submitting ? <Loader2 size={12} className="animate-spin"/> : "提交审核"}
              </button>
            </div>
          </>
        ) : (
          <pre className="max-h-64 overflow-auto rounded bg-os-elevated p-3 font-mono text-2xs text-os-subtle">
            {JSON.stringify(sub.agent_manifest, null, 2)}
          </pre>
        )}

        {canWithdraw && (
          <div className="mt-3">
            <button onClick={handleWithdraw} disabled={withdrawing}
              className="inline-flex h-8 items-center gap-1.5 rounded border border-os-border px-3 text-xs text-os-subtle hover:border-os-danger/30 hover:text-os-danger disabled:opacity-50">
              {withdrawing ? <Loader2 size={12} className="animate-spin"/> : "撤回"}
            </button>
          </div>
        )}
      </section>

      {/* Validation */}
      {validation && (
        <section className="os-card mb-4 p-4">
          <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-os-text-high">
            {validation.valid ? <CheckCircle2 size={14} className="text-os-success"/> : <XCircle size={14} className="text-os-danger"/>}
            Manifest 校验
          </h3>
          {validation.errors.length > 0 && <div className="space-y-1"><p className="text-xs font-medium text-os-danger">错误：</p>{validation.errors.map((e,i)=><p key={i} className="text-xs text-os-danger">• {e}</p>)}</div>}
          {validation.warnings.length > 0 && <div className="mt-2 space-y-1"><p className="text-xs font-medium text-os-warning">警告：</p>{validation.warnings.map((w,i)=><p key={i} className="text-xs text-os-warning">• {w}</p>)}</div>}
          {validation.valid && validation.errors.length === 0 && validation.warnings.length === 0 && <p className="text-xs text-os-success">全部检查已通过</p>}
        </section>
      )}

      {/* Info */}
      <section className="os-card mb-4 p-4">
        <h3 className="mb-3 text-sm font-semibold text-os-text-high">详细信息</h3>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 text-xs">
          <Info label="开发者 ID" value={sub.developer_id} mono />
          <Info label="来源" value={sub.source_type} />
          <Info label="Package URL" value={sub.package_url || "-"} />
          <Info label="市场智能体 ID" value={sub.marketplace_agent_id || "-"} mono />
          <Info label="提交时间" value={sub.submitted_at ? new Date(sub.submitted_at).toLocaleString("zh-CN") : "-"} />
          <Info label="审核时间" value={sub.reviewed_at ? new Date(sub.reviewed_at).toLocaleString("zh-CN") : "-"} />
          <Info label="审核人" value={sub.reviewed_by || "-"} />
          <Info label="发布时间" value={sub.published_at ? new Date(sub.published_at).toLocaleString("zh-CN") : "-"} />
        </div>
      </section>

      {/* Review Notes */}
      {(sub.review_notes || sub.status === "approved" || sub.status === "rejected") && (
        <section className="os-card mb-4 p-4">
          <h3 className="mb-2 text-sm font-semibold text-os-text-high">审核结果</h3>
          {sub.status === "approved" && <p className="text-xs text-os-success">✓ 已通过 — 等待智能体市场发布集成（步骤 22-H）</p>}
          {sub.status === "rejected" && sub.review_notes && <p className="text-xs text-os-danger">✗ 已驳回 — {sub.review_notes}</p>}
          {sub.status === "published" && sub.marketplace_agent_id && (
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-xs text-os-accent">已发布至智能体市场</p>
              <Link href={`/agent-marketplace/${sub.marketplace_agent_id}`} className="text-xs text-os-accent hover:underline font-mono">{sub.marketplace_agent_id}</Link>
            </div>
          )}
          {sub.status === "published" && !sub.marketplace_agent_id && <p className="text-xs text-os-accent">已发布至智能体市场</p>}
        </section>
      )}

      {/* Boundary */}
      <section className="os-card p-4">
        <p className="text-xs leading-5 text-os-subtle">审核通过不等于已发布。智能体市场发布集成由步骤 22-H 处理；不会执行远程代码，也不涉及真实支付。</p>
      </section>
    </main>
  );
}

function Info({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return <div className="min-w-0"><p className="text-2xs text-os-subtle">{label}</p><p className={`mt-0.5 break-words ${mono ? "break-all font-mono" : ""} text-xs text-os-text-high`}>{value}</p></div>;
}
