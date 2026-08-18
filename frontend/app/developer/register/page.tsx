"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Loader2 } from "lucide-react";
import { getDeveloperMe, registerDeveloper, type DeveloperApiError } from "@/services/developer";

export default function RegisterPage() {
  const router = useRouter();
  const [existing, setExisting] = useState(false);
  const [loadingCheck, setLoadingCheck] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [displayName, setDisplayName] = useState("");
  const [orgName, setOrgName] = useState("");
  const [website, setWebsite] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [metaText, setMetaText] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let c = false;
    getDeveloperMe().then(r => { if (!c) { setExisting(!!r.developer); } }).catch(() => {}).finally(() => { if (!c) setLoadingCheck(false); });
    return () => { c = true; };
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault(); setError(null);
    let metadata: Record<string, unknown> = {};
    if (metaText.trim()) {
      try { metadata = JSON.parse(metaText); } catch { setError("metadata JSON 格式错误"); return; }
    }
    setSubmitting(true);
    try {
      await registerDeveloper({ display_name: displayName, organization_name: orgName || null, website: website || null, contact_email: contactEmail, metadata });
      router.push("/developer");
    } catch (e: unknown) { const ae = e as DeveloperApiError; setError(`[${ae.status}] ${ae.message}`); }
    finally { setSubmitting(false); }
  }

  if (loadingCheck) return <main className="mx-auto max-w-lg px-4 py-8"><div className="os-card p-6"><div className="shimmer-bg h-5 w-32 rounded bg-os-elevated"/></div></main>;

  if (existing) return (
    <main className="mx-auto max-w-lg px-4 py-8">
      <div className="os-card flex flex-col items-center gap-3 p-6 text-center">
        <p className="text-sm text-os-text-high">你已经注册了开发者账号。</p>
        <Link href="/developer" className="inline-flex h-9 items-center gap-2 rounded-md bg-os-accent px-4 text-xs font-medium text-white hover:bg-os-accent/90">前往开发者控制台</Link>
      </div>
    </main>
  );

  return (
    <main className="mx-auto max-w-lg px-4 py-8">
      <Link href="/developer" className="mb-4 inline-flex items-center gap-1.5 text-xs text-os-subtle hover:text-os-text-high"><ArrowLeft size={14}/>返回</Link>
      <h1 className="text-2xl font-semibold text-os-text-high mb-6">注册开发者账号</h1>

      {error && <div className="mb-4 rounded-md border border-os-danger/20 bg-os-danger-soft p-3 text-sm text-os-danger">{error}</div>}

      <form onSubmit={handleSubmit} className="os-card p-4 space-y-4">
        <Field label="显示名称 *" value={displayName} onChange={setDisplayName} placeholder="你的开发者展示名" />
        <Field label="组织名称" value={orgName} onChange={setOrgName} placeholder="可选" />
        <Field label="网站" value={website} onChange={setWebsite} placeholder="https://..." />
        <Field label="联系邮箱 *" value={contactEmail} onChange={setContactEmail} placeholder="dev@example.com" type="email" />
        <div>
          <label className="mb-1 block text-xs font-medium text-os-subtle">元数据（JSON，可选）</label>
          <textarea rows={3} value={metaText} onChange={e => setMetaText(e.target.value)} spellCheck={false}
            className="w-full rounded-md border border-os-border bg-os-elevated px-3 py-2 font-mono text-xs text-os-text-high outline-none placeholder:text-os-subtle focus:border-os-accent"
            placeholder='{"plan": "free"}' />
        </div>
        <button type="submit" disabled={submitting || !displayName || !contactEmail}
          className="inline-flex h-9 w-full items-center justify-center gap-2 rounded-md bg-os-accent text-xs font-medium text-white hover:bg-os-accent/90 disabled:cursor-not-allowed disabled:opacity-50">
          {submitting ? <Loader2 size={14} className="animate-spin"/> : "注册"}
        </button>
      </form>
    </main>
  );
}

function Field({ label, value, onChange, placeholder, type = "text" }: { label: string; value: string; onChange: (v: string) => void; placeholder: string; type?: string }) {
  return <div>
    <label className="mb-1 block text-xs font-medium text-os-subtle">{label}</label>
    <input type={type} value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
      className="h-10 w-full rounded-md border border-os-border bg-os-elevated px-3 text-sm text-os-text-high outline-none placeholder:text-os-subtle focus:border-os-accent" />
  </div>;
}
