"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Loader2 } from "lucide-react";
import { createDeveloperSubmission, type DeveloperApiError } from "@/services/developer";

const DEFAULT_MANIFEST = JSON.stringify({
  name: "my-agent",
  display_name: "My Agent",
  description: "Describe what this agent does.",
  version: "1.0.0",
  capabilities: ["knowledge_search"],
  required_permissions: ["agent:execute"],
  supported_workflows: [],
  runtime_type: "manifest_only",
  entrypoint: null,
  config_schema: {},
  usage_limits: {},
  security_profile: {
    requires_network: false,
    reads_user_data: false,
    writes_user_data: false,
    sandbox_level: "no_execution",
    allowed_domains: [],
    data_access_scope: [],
    risk_notes: null,
  },
  metadata: {},
}, null, 2);

export default function NewSubmissionPage() {
  const router = useRouter();
  const [manifestText, setManifestText] = useState(DEFAULT_MANIFEST);
  const [packageUrl, setPackageUrl] = useState("");
  const [metaText, setMetaText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault(); setError(null);

    // Parse manifest JSON
    let agentManifest: Record<string, unknown>;
    try { agentManifest = JSON.parse(manifestText); } catch { setError("Manifest JSON 格式错误"); return; }

    // Parse metadata JSON
    let metadata: Record<string, unknown> = {};
    if (metaText.trim()) { try { metadata = JSON.parse(metaText); } catch { setError("Metadata JSON 格式错误"); return; } }

    setSubmitting(true);
    try {
      const r = await createDeveloperSubmission({ agent_manifest: agentManifest, package_url: packageUrl || null, source_type: "manifest", metadata });
      router.push(`/developer/agents/${r.submission.submission_id}`);
    } catch (e: unknown) {
      const ae = e as DeveloperApiError;
      const detail = ae.detail as Record<string, unknown> | null;
      if (detail && typeof detail === "object" && "message" in detail) {
        setError(`[${ae.status}] ${detail.message}`);
        if ("errors" in detail && Array.isArray(detail.errors) && (detail.errors as string[]).length > 0) {
          setError(prev => `${prev}\n${(detail.errors as string[]).map((e: string) => `• ${e}`).join("\n")}`);
        }
      } else { setError(`[${ae.status}] ${ae.message}`); }
    }
    finally { setSubmitting(false); }
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <Link href="/developer/agents" className="mb-4 inline-flex items-center gap-1.5 text-xs text-os-subtle hover:text-os-text-high"><ArrowLeft size={14}/>Submissions</Link>
      <h1 className="text-2xl font-semibold text-os-text-high mb-6">New Agent Submission</h1>

      {error && <div className="mb-4 rounded-md border border-red-400/20 bg-red-400/10 p-3 text-sm text-red-200 whitespace-pre-wrap">{error}</div>}

      <form onSubmit={handleCreate} className="space-y-4">
        <div>
          <label className="mb-1 block text-xs font-medium text-os-subtle">Agent Manifest (JSON)</label>
          <textarea rows={20} value={manifestText} onChange={e => setManifestText(e.target.value)} spellCheck={false}
            className="w-full rounded-md border border-os-border bg-os-elevated px-3 py-2 font-mono text-xs text-os-text-high outline-none placeholder:text-os-muted focus:border-os-accent" />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-os-subtle">Package URL (optional, stored only, not executed)</label>
          <input value={packageUrl} onChange={e => setPackageUrl(e.target.value)} placeholder="https://..."
            className="h-10 w-full rounded-md border border-os-border bg-os-elevated px-3 text-sm text-os-text-high outline-none placeholder:text-os-muted focus:border-os-accent" />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-os-subtle">Metadata (JSON, optional)</label>
          <textarea rows={3} value={metaText} onChange={e => setMetaText(e.target.value)} spellCheck={false}
            className="w-full rounded-md border border-os-border bg-os-elevated px-3 py-2 font-mono text-xs text-os-text-high outline-none placeholder:text-os-muted focus:border-os-accent" placeholder='{"env": "prod"}' />
        </div>
        <button type="submit" disabled={submitting}
          className="inline-flex h-9 items-center gap-2 rounded-md bg-os-accent px-4 text-xs font-medium text-white hover:bg-os-accent/90 disabled:cursor-not-allowed disabled:opacity-50">
          {submitting ? <Loader2 size={14} className="animate-spin"/> : "Create Draft"}
        </button>
      </form>
    </main>
  );
}
