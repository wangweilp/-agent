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
  if (!sub) return <main className="mx-auto max-w-3xl px-4 py-8"><div className="os-card flex min-h-32 items-center justify-center p-4"><p className="text-sm text-os-text-high">Submission 不存在</p></div></main>;

  const isDraft = sub.status === "draft";
  const canWithdraw = sub.status === "submitted" || sub.status === "in_review";

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <Link href="/developer/agents" className="mb-4 inline-flex items-center gap-1.5 text-xs text-os-subtle hover:text-os-text-high"><ArrowLeft size={14}/>Submissions</Link>

      {error && <div className="mb-4 rounded-md border border-red-400/20 bg-red-400/10 p-3 text-sm text-red-200">{error}</div>}

      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-os-text-high">{sub.agent_manifest?.display_name || "(untitled)"}</h1>
          <span className="font-mono text-2xs text-os-muted">{sub.submission_id}</span>
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
                {saving ? <Loader2 size={12} className="animate-spin"/> : "Save Draft"}
              </button>
              <button onClick={handleValidate} disabled={validating} className="inline-flex h-8 items-center gap-1.5 rounded border border-os-border px-3 text-xs text-os-subtle hover:text-os-text-high disabled:opacity-50">
                {validating ? <Loader2 size={12} className="animate-spin"/> : "Validate"}
              </button>
              <button onClick={handleSubmit} disabled={submitting} className="inline-flex h-8 items-center gap-1.5 rounded bg-os-accent px-3 text-xs font-medium text-white hover:bg-os-accent/90 disabled:opacity-50">
                {submitting ? <Loader2 size={12} className="animate-spin"/> : "Submit for Review"}
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
              className="inline-flex h-8 items-center gap-1.5 rounded border border-os-border px-3 text-xs text-os-subtle hover:border-red-400/30 hover:text-red-300 disabled:opacity-50">
              {withdrawing ? <Loader2 size={12} className="animate-spin"/> : "Withdraw"}
            </button>
          </div>
        )}
      </section>

      {/* Validation */}
      {validation && (
        <section className="os-card mb-4 p-4">
          <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-os-text-high">
            {validation.valid ? <CheckCircle2 size={14} className="text-emerald-400"/> : <XCircle size={14} className="text-red-400"/>}
            Manifest Validation
          </h3>
          {validation.errors.length > 0 && <div className="space-y-1"><p className="text-xs text-red-300">Errors:</p>{validation.errors.map((e,i)=><p key={i} className="text-2xs text-red-200">• {e}</p>)}</div>}
          {validation.warnings.length > 0 && <div className="mt-2 space-y-1"><p className="text-xs text-amber-300">Warnings:</p>{validation.warnings.map((w,i)=><p key={i} className="text-2xs text-amber-200">• {w}</p>)}</div>}
          {validation.valid && validation.errors.length === 0 && validation.warnings.length === 0 && <p className="text-xs text-emerald-300">All checks passed</p>}
        </section>
      )}

      {/* Info */}
      <section className="os-card mb-4 p-4">
        <h3 className="mb-3 text-sm font-semibold text-os-text-high">Details</h3>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 text-xs">
          <Info label="Developer ID" value={sub.developer_id} mono />
          <Info label="Source" value={sub.source_type} />
          <Info label="Package URL" value={sub.package_url || "-"} />
          <Info label="Mkp 智能体 ID" value={sub.marketplace_agent_id || "-"} mono />
          <Info label="Submitted" value={sub.submitted_at ? new Date(sub.submitted_at).toLocaleString("zh-CN") : "-"} />
          <Info label="Reviewed" value={sub.reviewed_at ? new Date(sub.reviewed_at).toLocaleString("zh-CN") : "-"} />
          <Info label="Reviewed By" value={sub.reviewed_by || "-"} />
          <Info label="Published" value={sub.published_at ? new Date(sub.published_at).toLocaleString("zh-CN") : "-"} />
        </div>
      </section>

      {/* Review Notes */}
      {(sub.review_notes || sub.status === "approved" || sub.status === "rejected") && (
        <section className="os-card mb-4 p-4">
          <h3 className="mb-2 text-sm font-semibold text-os-text-high">Review</h3>
          {sub.status === "approved" && <p className="text-xs text-emerald-300">✓ Approved — 等待 Marketplace Publish Integration (Step 22-H)</p>}
          {sub.status === "rejected" && sub.review_notes && <p className="text-xs text-red-300">✗ Rejected — {sub.review_notes}</p>}
          {sub.status === "published" && sub.marketplace_agent_id && (
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-xs text-violet-300">Published to Marketplace</p>
              <Link href={`/agent-marketplace/${sub.marketplace_agent_id}`} className="text-xs text-os-accent hover:underline font-mono">{sub.marketplace_agent_id}</Link>
            </div>
          )}
          {sub.status === "published" && !sub.marketplace_agent_id && <p className="text-xs text-violet-300">Published to Marketplace</p>}
        </section>
      )}

      {/* Boundary */}
      <section className="os-card p-4">
        <p className="text-2xs text-os-subtle">Approved ≠ Published. Step 22-H handles Marketplace Publish Integration. No remote code execution. No real payment.</p>
      </section>
    </main>
  );
}

function Info({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return <div><p className="text-2xs text-os-muted">{label}</p><p className={`mt-0.5 ${mono ? "font-mono" : ""} text-xs text-os-text-high truncate`}>{value}</p></div>;
}
