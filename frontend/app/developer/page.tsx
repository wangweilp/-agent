"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, CheckCircle2, Clock, Code2, Key, Layers, Plus, Shield, Sparkles, XCircle } from "lucide-react";
import { StatusBadge } from "@/components/open-platform/StatusBadge";
import { getDeveloperMe, listDeveloperApiKeys, listDeveloperSubmissions, type DeveloperApiError } from "@/services/developer";
import type { DeveloperAccount } from "@/types/open-platform";

export default function DeveloperConsolePage() {
  const [dev, setDev] = useState<DeveloperAccount | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [keyCount, setKeyCount] = useState(0);
  const [stats, setStats] = useState({ total: 0, draft: 0, submitted: 0, approved: 0, rejected: 0 });

  useEffect(() => { let c = false;
    async function load() {
      try {
        const me = await getDeveloperMe();
        if (!c) setDev(me.developer);
        try { const keys = await listDeveloperApiKeys(true); if (!c) setKeyCount(keys.total); } catch { /* */ }
        try { const subs = await listDeveloperSubmissions({ include_withdrawn: true });
          if (!c) { const items = subs.submissions; setStats({ total: items.length, draft: items.filter(s=>s.status==="draft").length, submitted: items.filter(s=>s.status==="submitted"||s.status==="in_review").length, approved: items.filter(s=>s.status==="approved").length, rejected: items.filter(s=>s.status==="rejected").length }); }
        } catch { /* */ }
      } catch (e: unknown) {
        const apiErr = e as DeveloperApiError;
        if (apiErr.status === 404) { if (!c) setDev(null); } else { if (!c) setError(`[${apiErr.status}] ${apiErr.message}`); }
      } finally { if (!c) setLoading(false); }
    }
    void load(); return () => { c = true; };
  }, []);

  if (loading) return <main className="mx-auto max-w-4xl px-4 py-8"><div className="os-card p-6"><div className="shimmer-bg h-6 w-48 rounded bg-os-elevated"/><div className="mt-4 space-y-2"><div className="shimmer-bg h-3 w-full rounded bg-os-elevated"/><div className="shimmer-bg h-3 w-3/4 rounded bg-os-elevated"/></div></div></main>;

  // Not registered
  if (!dev) return (
    <main className="mx-auto max-w-4xl px-4 py-8">
      <header className="mb-6">
        <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-os-border bg-os-surface px-3 py-1 text-xs text-os-subtle">
          <Code2 size={14} className="text-os-accent" /> Open Platform
        </div>
        <h1 className="text-3xl font-semibold text-os-text-high">开发者控制台</h1>
        <p className="mt-2 text-sm text-os-subtle max-w-xl">构建、提交和跟踪 Cognitive OS Agent，从 Manifest 草稿进入审核流程。</p>
      </header>
      <section className="os-card flex min-h-48 flex-col items-center justify-center gap-3 text-center p-6">
        <Code2 size={28} className="text-os-muted" />
        <h2 className="text-base font-semibold text-os-text-high">尚未注册开发者账号</h2>
        <p className="text-sm text-os-subtle max-w-sm">注册开发者账号后即可创建 API Key、提交 Agent Manifest 并进入审核流程。</p>
        <Link href="/developer/register" className="inline-flex h-9 items-center gap-2 rounded-md bg-os-accent px-4 text-xs font-medium text-white hover:bg-os-accent/90">
          <Plus size={14} /> 注册开发者账号
        </Link>
      </section>
    </main>
  );

  return (
    <main className="mx-auto max-w-4xl px-4 py-8">
      {/* Hero */}
      <header className="mb-6">
        <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-os-border bg-os-surface px-3 py-1 text-xs text-os-subtle">
          <Code2 size={14} className="text-os-accent" /> Open Platform
        </div>
        <h1 className="text-3xl font-semibold text-os-text-high">开发者控制台</h1>
        <p className="mt-2 text-sm text-os-subtle max-w-xl">构建、提交和跟踪 Cognitive OS Agent，从 Manifest 草稿进入审核流程。</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {["开放平台", "Manifest 优先", "需要审核", "禁止远程代码执行"].map(b => (
            <span key={b} className="inline-flex items-center gap-1.5 rounded-full border border-os-border/60 bg-os-elevated px-2.5 py-1 text-2xs text-os-subtle">{b}</span>
          ))}
        </div>
      </header>

      {error && <div className="mb-4 rounded-md border border-red-400/20 bg-red-400/10 p-3 text-sm text-red-200">{error}</div>}

      {/* Dev Profile Card */}
      <section className="os-card mb-4 p-4">
        <h3 className="text-sm font-semibold text-os-text-high">Developer Profile</h3>
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Info label="Display Name" value={dev.display_name} />
          <Info label="Organization" value={dev.organization_name || "-"} />
          <Info label="Contact" value={dev.contact_email} />
          <div><p className="text-2xs text-os-muted">Status</p><StatusBadge status={dev.status} /></div>
        </div>
        <p className="mt-2 font-mono text-2xs text-os-muted">{dev.developer_id}</p>
      </section>

      {/* Stats */}
      <section className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-6">
        <Stat icon={Key} label="API Keys" value={String(keyCount)} />
        <Stat icon={Layers} label="Submissions" value={String(stats.total)} />
        <Stat icon={Sparkles} label="Drafts" value={String(stats.draft)} />
        <Stat icon={Clock} label="In Review" value={String(stats.submitted)} />
        <Stat icon={CheckCircle2} label="Approved" value={String(stats.approved)} />
        <Stat icon={XCircle} label="Rejected" value={String(stats.rejected)} />
      </section>

      {/* Quick Links */}
      <section className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Link href="/developer/api-keys" className="os-card os-card-hover flex items-center gap-4 p-4">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-os-accent/15 text-os-accent"><Key size={18} /></div>
          <div className="flex-1 min-w-0"><p className="text-sm font-semibold text-os-text-high">API Keys</p><p className="text-xs text-os-subtle">管理 API Key</p></div>
          <ArrowRight size={14} className="shrink-0 text-os-muted" />
        </Link>
        <Link href="/developer/agents" className="os-card os-card-hover flex items-center gap-4 p-4">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-violet-400/15 text-violet-400"><Layers size={18} /></div>
          <div className="flex-1 min-w-0"><p className="text-sm font-semibold text-os-text-high">Agent Submissions</p><p className="text-xs text-os-subtle">查看和管理提交</p></div>
          <ArrowRight size={14} className="shrink-0 text-os-muted" />
        </Link>
        <Link href="/developer/agents/new" className="os-card os-card-hover flex items-center gap-4 p-4">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-emerald-400/15 text-emerald-400"><Plus size={18} /></div>
          <div className="flex-1 min-w-0"><p className="text-sm font-semibold text-os-text-high">New Submission</p><p className="text-xs text-os-subtle">提交新 Agent</p></div>
          <ArrowRight size={14} className="shrink-0 text-os-muted" />
        </Link>
      </section>

      {/* Boundary Notice */}
      <section className="os-card mt-4 p-4">
        <h3 className="flex items-center gap-2 text-xs font-semibold text-os-subtle"><Shield size={13} className="text-os-accent"/> Open Platform 边界说明</h3>
        <ul className="mt-2 space-y-1 text-2xs text-os-subtle">
          <li>• 开发者控制台用于创建和提交 Agent Manifest</li>
          <li>• 智能体审核由管理员通过审核面板完成</li>
          <li>• 审核通过不等于自动上架智能体市场</li>
          <li>• 后续发布流程中完成市场对接</li>
          <li>• 当前不支持真实支付 / 收入分成 / 远程代码执行</li>
        </ul>
      </section>
    </main>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return <div><p className="text-2xs text-os-muted">{label}</p><p className="mt-0.5 text-xs text-os-text-high truncate">{value}</p></div>;
}

function Stat({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: string }) {
  return <div className="rounded-md border border-os-border bg-os-elevated/30 px-3 py-2 text-center">
    <div className="mb-1 flex items-center justify-center"><Icon size={14} /></div>
    <p className="text-2xs text-os-muted">{label}</p>
    <p className="mt-1 text-lg font-semibold text-os-text-high">{value}</p>
  </div>;
}
