"use client";
import { useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft, Loader2, Brain, Globe, Wrench, Database,
  Code2, Eye, type LucideIcon,
} from "lucide-react";
import { createDeveloperSubmission, type DeveloperApiError } from "@/services/developer";
import { Switch } from "@/components/os/switch";
import { cn } from "@/lib/utils";

// ── 能力定义 ──

interface Capability {
  key: string;
  label: string;
  description: string;
  icon: LucideIcon;
}

const CAPABILITIES: Capability[] = [
  { key: "knowledge_search", label: "记忆检索", description: "允许智能体访问长期记忆与知识图谱", icon: Brain },
  { key: "web_search", label: "联网搜索", description: "允许智能体通过互联网获取实时信息", icon: Globe },
  { key: "tool_use", label: "工具调用", description: "允许智能体挂载并执行外部工具", icon: Wrench },
  { key: "memory_write", label: "记忆写入", description: "允许智能体将新知识写入记忆系统", icon: Database },
];

// ── 默认 Manifest ──

const DEFAULT_MANIFEST = {
  name: "my-agent",
  display_name: "My 智能体",
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
};

export default function NewSubmissionPage() {
  const router = useRouter();

  // 结构化配置字段
  const [agentName, setAgentName] = useState(DEFAULT_MANIFEST.name);
  const [displayName, setDisplayName] = useState(DEFAULT_MANIFEST.display_name);
  const [description, setDescription] = useState(DEFAULT_MANIFEST.description);
  const [version, setVersion] = useState(DEFAULT_MANIFEST.version);
  const [systemPrompt, setSystemPrompt] = useState("");
  const [capabilities, setCapabilities] = useState<string[]>(DEFAULT_MANIFEST.capabilities);
  const [packageUrl, setPackageUrl] = useState("");
  const [metaText, setMetaText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 动态生成 manifest（保持与原 handleCreate 兼容）
  const manifestText = useMemo(() => {
    const manifest = {
      ...DEFAULT_MANIFEST,
      name: agentName,
      display_name: displayName,
      description,
      version,
      capabilities,
      security_profile: {
        ...DEFAULT_MANIFEST.security_profile,
        requires_network: capabilities.includes("web_search"),
        reads_user_data: capabilities.includes("knowledge_search"),
        writes_user_data: capabilities.includes("memory_write"),
      },
      metadata: {
        ...DEFAULT_MANIFEST.metadata,
        ...(systemPrompt ? { system_prompt: systemPrompt } : {}),
      },
    };
    return JSON.stringify(manifest, null, 2);
  }, [agentName, displayName, description, version, capabilities, systemPrompt]);

  // 能力开关切换
  const toggleCapability = (key: string) => {
    setCapabilities((prev) =>
      prev.includes(key) ? prev.filter((c) => c !== key) : [...prev, key],
    );
  };

  // 保持原有提交逻辑不变
  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    let agentManifest: Record<string, unknown>;
    try {
      agentManifest = JSON.parse(manifestText);
    } catch {
      setError("Manifest JSON 格式错误");
      return;
    }

    let metadata: Record<string, unknown> = {};
    if (metaText.trim()) {
      try {
        metadata = JSON.parse(metaText);
      } catch {
        setError("Metadata JSON 格式错误");
        return;
      }
    }

    setSubmitting(true);
    try {
      const r = await createDeveloperSubmission({
        agent_manifest: agentManifest,
        package_url: packageUrl || null,
        source_type: "manifest",
        metadata,
      });
      router.push(`/developer/agents/${r.submission.submission_id}`);
    } catch (e: unknown) {
      const ae = e as DeveloperApiError;
      const detail = ae.detail as Record<string, unknown> | null;
      if (detail && typeof detail === "object" && "message" in detail) {
        setError(`[${ae.status}] ${detail.message}`);
        if ("errors" in detail && Array.isArray(detail.errors) && (detail.errors as string[]).length > 0) {
          setError((prev) => `${prev}\n${(detail.errors as string[]).map((e: string) => `• ${e}`).join("\n")}`);
        }
      } else {
        setError(`[${ae.status}] ${ae.message}`);
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto max-w-7xl px-4 py-8">
      <Link href="/developer/agents" className="mb-4 inline-flex items-center gap-1.5 text-xs text-os-subtle hover:text-os-text-high">
        <ArrowLeft size={14} />Submissions
      </Link>
      <div className="flex items-center gap-3 mb-6">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-os-border bg-os-elevated">
          <Code2 size={18} className="text-os-accent" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold text-os-text-high">Agent Studio</h1>
          <p className="text-xs text-os-subtle">智能体集成开发环境 · IDE-grade Authoring</p>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-xl border border-red-400/20 bg-red-400/10 p-3 text-sm text-red-200 whitespace-pre-wrap">
          {error}
        </div>
      )}

      <form onSubmit={handleCreate}>
        {/* ── 分屏 IDE 布局 ── */}
        <div className="flex flex-col md:flex-row gap-4 md:gap-6">
          {/* 左侧：配置区（60%） */}
          <div className="flex-1 md:w-3/5 space-y-5">
            {/* 基础信息卡片 */}
            <section className="os-card p-6 rounded-xl space-y-4">
              <h2 className="text-sm font-semibold text-os-text-high flex items-center gap-2">
                <span className="w-1 h-4 rounded-full bg-os-accent" />
                基础信息
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="mb-1 block text-xs font-medium text-os-subtle">智能体标识 (name)</label>
                  <input
                    value={agentName}
                    onChange={(e) => setAgentName(e.target.value)}
                    placeholder="my-agent"
                    className="h-10 w-full rounded-lg border border-os-border bg-os-elevated px-3 text-sm text-os-text-high outline-none placeholder:text-os-muted focus:border-os-accent"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-os-subtle">显示名称</label>
                  <input
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    placeholder="My 智能体"
                    className="h-10 w-full rounded-lg border border-os-border bg-os-elevated px-3 text-sm text-os-text-high outline-none placeholder:text-os-muted focus:border-os-accent"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-os-subtle">版本号</label>
                  <input
                    value={version}
                    onChange={(e) => setVersion(e.target.value)}
                    placeholder="1.0.0"
                    className="h-10 w-full rounded-lg border border-os-border bg-os-elevated px-3 text-sm text-os-text-high outline-none placeholder:text-os-muted focus:border-os-accent"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-os-subtle">Package URL (optional)</label>
                  <input
                    value={packageUrl}
                    onChange={(e) => setPackageUrl(e.target.value)}
                    placeholder="https://..."
                    className="h-10 w-full rounded-lg border border-os-border bg-os-elevated px-3 text-sm text-os-text-high outline-none placeholder:text-os-muted focus:border-os-accent"
                  />
                </div>
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-os-subtle">描述</label>
                <input
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Describe what this agent does."
                  className="h-10 w-full rounded-lg border border-os-border bg-os-elevated px-3 text-sm text-os-text-high outline-none placeholder:text-os-muted focus:border-os-accent"
                />
              </div>
            </section>

            {/* 系统提示词编辑器（极客风） */}
            <section className="os-card p-6 rounded-xl space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-os-text-high flex items-center gap-2">
                  <span className="w-1 h-4 rounded-full bg-os-accent" />
                  系统提示词 (System Prompt)
                </h2>
                <span className="text-xs text-os-subtle font-mono">
                  {systemPrompt.length} chars · 支持 <code className="text-os-accent">{"{{var}}"}</code>
                </span>
              </div>
              <div className="relative rounded-xl border border-os-border bg-slate-50 overflow-hidden focus-within:ring-1 focus-within:ring-os-accent focus-within:border-os-accent transition-all">
                {/* 编辑器顶部栏 */}
                <div className="flex items-center justify-between px-3 py-1.5 border-b border-os-border/50 bg-os-elevated/40">
                  <div className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full bg-red-400/60" />
                    <span className="w-2.5 h-2.5 rounded-full bg-amber-400/60" />
                    <span className="w-2.5 h-2.5 rounded-full bg-emerald-400/60" />
                    <span className="ml-2 text-2xs text-os-muted font-mono">system_prompt.md</span>
                  </div>
                  <span className="text-2xs text-os-subtle font-mono">UTF-8 · LF</span>
                </div>
                <textarea
                  value={systemPrompt}
                  onChange={(e) => setSystemPrompt(e.target.value)}
                  spellCheck={false}
                  rows={10}
                  placeholder="你是一个专业的智能体。请根据用户输入，调用相应工具完成任务...&#10;&#10;支持变量: {{user_name}} {{context}} {{memory}}"
                  className="w-full bg-transparent px-4 py-3 font-mono text-sm leading-relaxed text-os-text-high outline-none placeholder:text-os-muted resize-none"
                />
              </div>
            </section>

            {/* 能力矩阵开关 */}
            <section className="os-card p-6 rounded-xl space-y-3">
              <h2 className="text-sm font-semibold text-os-text-high flex items-center gap-2">
                <span className="w-1 h-4 rounded-full bg-os-accent" />
                能力矩阵 (Capability Matrix)
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {CAPABILITIES.map((cap) => {
                  const Icon = cap.icon;
                  const enabled = capabilities.includes(cap.key);
                  return (
                    <div
                      key={cap.key}
                      className={cn(
                        "p-4 border rounded-xl flex items-center justify-between transition-colors",
                        enabled
                          ? "border-os-accent/30 bg-os-accent/5"
                          : "border-os-border",
                      )}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div
                          className={cn(
                            "w-9 h-9 rounded-lg flex items-center justify-center shrink-0",
                            enabled ? "bg-os-accent/15 text-os-accent" : "bg-os-elevated text-os-subtle",
                          )}
                        >
                          <Icon size={16} />
                        </div>
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-os-text-high">{cap.label}</p>
                          <p className="text-2xs text-os-muted truncate">{cap.description}</p>
                        </div>
                      </div>
                      <Switch
                        checked={enabled}
                        onChange={() => toggleCapability(cap.key)}
                        aria-label={cap.label}
                      />
                    </div>
                  );
                })}
              </div>
            </section>

            {/* Metadata */}
            <section className="os-card p-6 rounded-xl space-y-3">
              <h2 className="text-sm font-semibold text-os-text-high flex items-center gap-2">
                <span className="w-1 h-4 rounded-full bg-os-accent" />
                Metadata (JSON, optional)
              </h2>
              <textarea
                rows={3}
                value={metaText}
                onChange={(e) => setMetaText(e.target.value)}
                spellCheck={false}
                className="w-full rounded-lg border border-os-border bg-os-elevated px-3 py-2 font-mono text-xs text-os-text-high outline-none placeholder:text-os-muted focus:border-os-accent"
                placeholder='{"env": "prod"}'
              />
            </section>
          </div>

          {/* 右侧：实时预览/调试区（40%） */}
          <div className="md:w-2/5 flex flex-col">
            <div className="os-card rounded-xl border-l border-os-border bg-os-base flex flex-col md:h-full md:sticky md:top-4">
              {/* 预览区 Header */}
              <div className="flex items-center justify-between px-4 py-3 border-b border-os-border">
                <div className="flex items-center gap-2">
                  <Eye size={14} className="text-os-accent" />
                  <span className="text-sm font-medium text-os-text-high">Manifest Preview</span>
                </div>
                <span className="text-2xs text-os-subtle font-mono">auto-generated</span>
              </div>

              {/* JSON 预览 */}
              <div className="flex-1 overflow-auto p-4">
                <pre className="text-2xs font-mono text-os-text leading-relaxed whitespace-pre-wrap">
                  {manifestText}
                </pre>
              </div>

              {/* 底部状态栏 */}
              <div className="flex items-center justify-between px-4 py-2 border-t border-os-border bg-os-elevated/30">
                <span className="text-2xs text-os-muted">
                  {capabilities.length} capabilities · {systemPrompt.length} prompt chars
                </span>
                <span className="text-2xs text-emerald-400 font-mono">● valid JSON</span>
              </div>
            </div>

            {/* 提交按钮 */}
            <button
              type="submit"
              disabled={submitting}
              className="mt-4 inline-flex h-10 items-center justify-center gap-2 rounded-xl bg-os-accent px-6 text-sm font-medium text-white hover:bg-os-accent/90 disabled:cursor-not-allowed disabled:opacity-50 transition-all hover:shadow-[0_0_15px_rgba(129,140,248,0.3)]"
            >
              {submitting ? (
                <>
                  <Loader2 size={15} className="animate-spin" />
                  提交中...
                </>
              ) : (
                "Create Draft"
              )}
            </button>
          </div>
        </div>
      </form>
    </main>
  );
}
