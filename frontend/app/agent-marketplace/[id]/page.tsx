"use client";

import { useCallback, useEffect, useState, type ComponentPropsWithoutRef } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import {
  ArrowLeft,
  ArrowDownToLine,
  Bot,
  Building2,
  CheckCircle2,
  FileText,
  Layers,
  Loader2,
  Power,
  PowerOff,
  Settings,
  Shield,
  Star,
  Trash2,
  User,
  Workflow,
} from "lucide-react";

import { AgentConfigDialog } from "@/components/agents/AgentConfigDialog";
import { AgentPermissionPanel } from "@/components/agents/AgentPermissionPanel";
import { AgentPricingBadge } from "@/components/agents/AgentPricingBadge";
import { AgentUsageSummary } from "@/components/agents/AgentUsageSummary";
import {
  disableMarketplaceInstallation,
  enableMarketplaceInstallation,
  getMarketplaceAgent,
  getMarketplaceAgentPermissions,
  getMarketplaceInstallationUsage,
  installMarketplaceAgent,
  uninstallMarketplaceInstallation,
  updateMarketplaceInstallationConfig,
  type MarketplaceApiError,
} from "@/services/marketplace";
import type {
  MarketplaceAgent,
  MarketplaceConfigRequest,
  MarketplacePermissionsResponse,
  MarketplaceUsageResponse,
  TenantAgentInstallation,
} from "@/types/marketplace";
import { cn } from "@/lib/utils";

const AGENT_STATUS_LABELS: Record<string, string> = {
  active: "运行中",
  beta: "测试版",
  deprecated: "已弃用",
  disabled: "已停用",
  error: "异常",
};

const PUBLISHER_TYPE_LABELS: Record<string, string> = {
  internal: "内部发布",
  organization: "组织",
  developer: "开发者",
  official: "官方",
  community: "社区",
};

// ── 权限 Pill 元数据映射 ──
function permissionMeta(permission: string): { icon: string; label: string } {
  const p = permission.toLowerCase();
  if (p.includes("web") || p.includes("network") || p.includes("internet") || p.includes("http") || p.includes("online")) {
    return { icon: "🌐", label: "允许联网" };
  }
  if (p.includes("memory") || p.includes("storage") || p.includes("persist")) {
    return { icon: "💾", label: "读写记忆" };
  }
  if (p.includes("tool") || p.includes("function") || p.includes("action")) {
    return { icon: "🔧", label: "工具调用" };
  }
  if (p.includes("knowledge") || p.includes("search") || p.includes("retriev")) {
    return { icon: "📚", label: "知识检索" };
  }
  if (p.includes("file") || p.includes("document") || p.includes("upload")) {
    return { icon: "📁", label: "文件访问" };
  }
  if (p.includes("code") || p.includes("exec") || p.includes("sandbox") || p.includes("runtime")) {
    return { icon: "⚙️", label: "代码执行" };
  }
  if (p.includes("email") || p.includes("mail") || p.includes("message")) {
    return { icon: "✉️", label: "消息发送" };
  }
  if (p.includes("data") || p.includes("database") || p.includes("db")) {
    return { icon: "🗄️", label: "数据访问" };
  }
  return { icon: "🔐", label: permission };
}

// ── 按分类提取径向渐变起始色 ──
function categoryGradient(category: string): string {
  const map: Record<string, string> = {
    automation: "from-blue-500/20",
    assistant: "from-cyan-500/20",
    knowledge: "from-emerald-500/20",
    training: "from-violet-500/20",
    sales: "from-amber-500/20",
    support: "from-rose-500/20",
    engineering: "from-indigo-500/20",
    hr: "from-pink-500/20",
    analytics: "from-orange-500/20",
  };
  return map[category] || "from-os-accent/20";
}

// ── Markdown 组件映射（readme 风格） ──
const readmeComponents: ComponentPropsWithoutRef<typeof ReactMarkdown>["components"] = {
  code({ className, children, ...props }) {
    const match = /language-(\w+)/.exec(className || "");
    const value = String(children).replace(/\n$/, "");
    const isBlock = !!match || value.includes("\n");
    if (isBlock) {
      return (
        <pre className="my-3 overflow-auto rounded-lg border border-os-border bg-os-base p-3 text-2xs font-mono">
          <code>{value}</code>
        </pre>
      );
    }
    return (
      <code className="rounded bg-os-elevated px-1.5 py-0.5 text-2xs font-mono text-os-accent" {...props}>
        {children}
      </code>
    );
  },
  p({ children }) {
    return <p className="leading-6 mb-3 last:mb-0 text-sm text-os-text">{children}</p>;
  },
  ul({ children }) {
    return <ul className="list-disc list-inside mb-3 space-y-1 last:mb-0 text-sm text-os-text">{children}</ul>;
  },
  ol({ children }) {
    return <ol className="list-decimal list-inside mb-3 space-y-1 last:mb-0 text-sm text-os-text">{children}</ol>;
  },
  li({ children }) {
    return <li className="leading-6 text-sm text-os-text">{children}</li>;
  },
  blockquote({ children }) {
    return (
      <blockquote className="border-l-2 border-os-accent/40 pl-3 text-os-subtle italic my-3 text-sm">
        {children}
      </blockquote>
    );
  },
  h1({ children }) {
    return <h1 className="text-lg font-semibold mb-2 mt-4 first:mt-0 text-os-text-high">{children}</h1>;
  },
  h2({ children }) {
    return <h2 className="text-base font-semibold mb-2 mt-4 first:mt-0 text-os-text-high">{children}</h2>;
  },
  h3({ children }) {
    return <h3 className="text-sm font-semibold mb-1.5 mt-3 first:mt-0 text-os-text-high">{children}</h3>;
  },
  a({ href, children }) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-os-accent hover:underline"
      >
        {children}
      </a>
    );
  },
  hr() {
    return <hr className="border-os-border/50 my-4" />;
  },
  table({ children }) {
    return (
      <div className="overflow-x-auto my-3">
        <table className="w-full text-xs border-collapse">{children}</table>
      </div>
    );
  },
};

function LoadingDetail() {
  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6">
      <div className="shimmer-bg mb-4 h-5 w-32 rounded bg-os-elevated" />
      <div className="h-44 rounded-2xl border border-os-border/50 bg-os-surface/40 p-6 backdrop-blur-md">
        <div className="flex items-start gap-4">
          <div className="shimmer-bg h-14 w-14 rounded-2xl bg-os-elevated" />
          <div className="flex-1 space-y-2">
            <div className="shimmer-bg h-6 w-48 rounded bg-os-elevated" />
            <div className="shimmer-bg h-3 w-full rounded bg-os-elevated" />
            <div className="shimmer-bg h-3 w-3/4 rounded bg-os-elevated" />
          </div>
        </div>
      </div>
    </main>
  );
}

export default function MarketplaceAgentDetailPage() {
  const params = useParams();
  const id = params.id as string;

  const [agent, setAgent] = useState<MarketplaceAgent | null>(null);
  const [installation, setInstallation] = useState<TenantAgentInstallation | null>(null);
  const [isInstalled, setIsInstalled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Sub-resources
  const [permissions, setPermissions] = useState<MarketplacePermissionsResponse | null>(null);
  const [usage, setUsage] = useState<MarketplaceUsageResponse | null>(null);

  // Action states
  const [installing, setInstalling] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [uninstalling, setUninstalling] = useState(false);
  const [savingConfig, setSavingConfig] = useState(false);
  const [showConfirmUninstall, setShowConfirmUninstall] = useState(false);
  const [showConfigDialog, setShowConfigDialog] = useState(false);

  const fetchAgent = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getMarketplaceAgent(id);
      setAgent(data.agent);
      setIsInstalled(data.is_installed);
      setInstallation(data.installation);

      // Fetch sub-resources if installed
      if (data.is_installed && data.installation) {
        try {
          const p = await getMarketplaceAgentPermissions(id);
          setPermissions(p);
        } catch { /* quiet */ }
        try {
          const u = await getMarketplaceInstallationUsage(data.installation.installation_id);
          setUsage(u);
        } catch { /* quiet */ }
      }
    } catch (e: unknown) {
      const apiErr = e as MarketplaceApiError;
      setError(`[${apiErr.status || "错误"}] ${apiErr.message || "加载失败"}`);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void fetchAgent();
  }, [fetchAgent]);

  const handleInstall = async () => {
    setInstalling(true);
    setError(null);
    try {
      const res = await installMarketplaceAgent(id, {});
      setIsInstalled(true);
      setInstallation(res.installation);
      // Fetch permissions
      try {
        const p = await getMarketplaceAgentPermissions(id);
        setPermissions(p);
      } catch { /* quiet */ }
    } catch (e: unknown) {
      const apiErr = e as MarketplaceApiError;
      if (apiErr.status === 409) {
        setIsInstalled(true);
        void fetchAgent();
      } else {
        setError(`[${apiErr.status || "错误"}] ${apiErr.message || "安装失败"}`);
      }
    } finally {
      setInstalling(false);
    }
  };

  const handleToggle = async () => {
    if (!installation) return;
    setToggling(true);
    setError(null);
    try {
      if (installation.enabled) {
        const res = await disableMarketplaceInstallation(installation.installation_id);
        setInstallation(res.installation);
      } else {
        const res = await enableMarketplaceInstallation(installation.installation_id);
        setInstallation(res.installation);
      }
    } catch (e: unknown) {
      const apiErr = e as MarketplaceApiError;
      setError(`[${apiErr.status || "错误"}] ${apiErr.message || "操作失败"}`);
    } finally {
      setToggling(false);
    }
  };

  const handleUninstall = async () => {
    if (!installation) return;
    setUninstalling(true);
    setError(null);
    try {
      await uninstallMarketplaceInstallation(installation.installation_id);
      setIsInstalled(false);
      setInstallation(null);
    } catch (e: unknown) {
      const apiErr = e as MarketplaceApiError;
      setError(`[${apiErr.status || "错误"}] ${apiErr.message || "卸载失败"}`);
    } finally {
      setUninstalling(false);
      setShowConfirmUninstall(false);
    }
  };

  const handleSaveConfig = async (payload: MarketplaceConfigRequest) => {
    if (!installation) return;
    setSavingConfig(true);
    setError(null);
    try {
      const res = await updateMarketplaceInstallationConfig(
        installation.installation_id,
        payload,
      );
      setInstallation(res.installation);
      setShowConfigDialog(false);
    } catch (e: unknown) {
      const apiErr = e as MarketplaceApiError;
      setError(`[${apiErr.status || "错误"}] ${apiErr.message || "配置保存失败"}`);
    } finally {
      setSavingConfig(false);
    }
  };

  if (loading) return <LoadingDetail />;
  if (!agent) {
    return (
      <main className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6">
        <div className="flex min-h-64 flex-col items-center justify-center gap-3 rounded-2xl border border-os-border/50 bg-os-surface/40 p-6 text-center backdrop-blur-md">
          <Bot size={32} className="text-os-muted" />
          <h2 className="text-base font-semibold text-os-text-high">
            {error ? "智能体加载失败" : "智能体不存在"}
          </h2>
          <p className={cn("max-w-lg break-words text-sm", error ? "text-os-danger" : "text-os-subtle")}>
            {error || "请检查智能体市场中的智能体 ID 是否正确。"}
          </p>
          <Link
            href="/agent-marketplace"
            className="inline-flex items-center gap-2 rounded-lg border border-os-border px-3 py-1.5 text-xs text-os-subtle transition-colors hover:text-os-text-high"
          >
            <ArrowLeft size={14} />
            返回智能体市场
          </Link>
        </div>
      </main>
    );
  }

  const readme = agent.long_description || agent.description || "暂无详细介绍。";
  const requiredPerms = permissions?.required || agent.required_permissions;

  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6">
      {/* Back link */}
      <Link
        href="/agent-marketplace"
        className="mb-4 inline-flex items-center gap-1.5 text-xs text-os-subtle transition-colors hover:text-os-text-high"
      >
        <ArrowLeft size={14} />
        返回智能体市场
      </Link>

      {error && (
        <div className="mb-4 rounded-lg border border-os-danger/20 bg-os-danger-soft p-3 text-sm text-os-danger">
          {error}
        </div>
      )}

      {/* ── Hero Banner ── */}
      <section
        className={cn(
          "relative overflow-hidden rounded-2xl border border-os-border/50 p-6 mb-6",
          "bg-gradient-to-br to-os-surface/40 backdrop-blur-md",
          categoryGradient(agent.category),
        )}
      >
        {/* Blurred grid background */}
        <div className="absolute inset-0 bg-grid-subtle opacity-30 pointer-events-none" />
        {/* Radial glow */}
        <div className="absolute -top-20 -right-20 w-72 h-72 rounded-full bg-os-accent/8 blur-3xl pointer-events-none" />

        <div className="relative flex items-start justify-between gap-4">
          <div className="flex min-w-0 items-start gap-4">
            <div className="relative flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border border-os-accent/30 bg-os-accent/15 text-os-accent">
              <Bot size={26} />
              <div className="pointer-events-none absolute inset-0 rounded-2xl bg-os-accent/15 blur-lg -z-10" />
            </div>
            <div className="min-w-0">
              <h1 className="text-2xl font-semibold tracking-tight text-os-text-high">
                {agent.display_name}
              </h1>
              <p className="mt-1.5 max-w-2xl text-sm leading-6 text-os-subtle">
                {agent.description}
              </p>
              <div className="mt-3 flex flex-wrap gap-1.5">
                <span className="os-badge bg-os-elevated/80 text-os-subtle">{agent.category}</span>
                {agent.department && (
                  <span className="os-badge bg-os-elevated/80 text-os-subtle">{agent.department}</span>
                )}
                <AgentPricingBadge model={agent.pricing_model} />
                <span className="os-badge bg-os-elevated/80 text-os-subtle">v{agent.version}</span>
              </div>
            </div>
          </div>

          <span
            className={cn(
              "os-badge shrink-0",
              agent.status === "active"
                ? "bg-os-success-soft text-os-success"
                : agent.status === "beta"
                  ? "bg-os-warning-soft text-os-warning"
                  : "bg-os-elevated text-os-subtle",
            )}
          >
            {AGENT_STATUS_LABELS[agent.status] || agent.status}
          </span>
        </div>
      </section>

      {/* ── Two-column layout: readme + sticky sidebar ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left column (2/3) — Readme + Capabilities + Installation management */}
        <div className="lg:col-span-2 space-y-4">
          {/* Readme (Markdown) */}
          <section className="rounded-2xl border border-os-border/50 bg-os-surface/40 p-6 backdrop-blur-md">
            <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-os-text-high">
              <FileText size={15} className="text-os-accent" />
              详细介绍
            </h3>
            <ReactMarkdown components={readmeComponents}>{readme}</ReactMarkdown>
          </section>

          {/* Capabilities */}
          <section className="rounded-2xl border border-os-border/50 bg-os-surface/40 p-6 backdrop-blur-md">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-os-text-high">
              <Layers size={15} className="text-os-accent" />
              能力矩阵
            </h3>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {agent.capabilities.map((cap) => (
                <span
                  key={cap}
                  className="rounded-lg border border-os-border bg-os-elevated/60 px-2.5 py-1 text-xs text-os-text-high"
                >
                  {cap}
                </span>
              ))}
            </div>

            {agent.supported_workflows.length > 0 && (
              <>
                <h4 className="mt-4 flex items-center gap-2 text-xs font-semibold text-os-subtle">
                  <Workflow size={13} />
                  支持的工作流
                </h4>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {agent.supported_workflows.map((wf) => (
                    <span
                      key={wf}
                      className="rounded-lg bg-os-accent-soft px-2.5 py-1 text-xs text-os-accent"
                    >
                      {wf}
                    </span>
                  ))}
                </div>
              </>
            )}
          </section>

          {/* Permissions detail (AgentPermissionPanel) */}
          <AgentPermissionPanel
            required={permissions?.required || agent.required_permissions}
            granted={permissions?.granted || []}
            missing={permissions?.missing || agent.required_permissions}
          />

          {/* Usage (if installed) */}
          {isInstalled && <AgentUsageSummary usage={usage} />}

          {/* Installation management (if installed) */}
          {isInstalled && installation && (
            <section className="rounded-2xl border border-os-border/50 bg-os-surface/40 p-6 backdrop-blur-md">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-os-text-high">
                <Settings size={15} className="text-os-accent" />
                安装管理
              </h3>

              <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                <InfoItem label="安装 ID" value={installation.installation_id} mono />
                <InfoItem
                  label="状态"
                  value={AGENT_STATUS_LABELS[installation.status] || installation.status}
                />
                <InfoItem
                  label="启用"
                  value={installation.enabled ? "是" : "否"}
                  color={installation.enabled ? "text-os-success" : "text-os-danger"}
                />
                <InfoItem label="锁定版本" value={installation.version_pinned || "跟随最新"} />
              </div>
              <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-2">
                <InfoItem label="安装人" value={installation.installed_by} />
                <InfoItem
                  label="安装时间"
                  value={
                    installation.installed_at
                      ? new Date(installation.installed_at).toLocaleString("zh-CN")
                      : "-"
                  }
                />
              </div>

              {/* Config */}
              {Object.keys(installation.config).length > 0 && (
                <details className="mt-3">
                  <summary className="cursor-pointer text-xs font-medium text-os-subtle hover:text-os-text-high">
                    配置 ({Object.keys(installation.config).length} 项)
                  </summary>
                  <pre className="mt-2 overflow-auto rounded-lg bg-os-elevated p-3 text-2xs text-os-subtle">
                    {JSON.stringify(installation.config, null, 2)}
                  </pre>
                </details>
              )}

              {/* Granted permissions */}
              {installation.permissions_granted.length > 0 && (
                <div className="mt-3">
                  <p className="text-xs font-medium text-os-subtle">已授权权限</p>
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {installation.permissions_granted.map((p) => (
                      <span
                        key={p}
                        className="rounded bg-os-success-soft px-2 py-0.5 text-2xs text-os-success"
                      >
                        {p}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Actions */}
              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={handleToggle}
                  disabled={toggling}
                  className={cn(
                    "inline-flex h-9 items-center gap-2 rounded-lg px-3 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
                    installation.enabled
                      ? "bg-os-danger-soft text-os-danger hover:bg-os-danger/15"
                      : "bg-os-success-soft text-os-success hover:bg-os-success/15",
                  )}
                >
                  {toggling ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : installation.enabled ? (
                    <PowerOff size={14} />
                  ) : (
                    <Power size={14} />
                  )}
                  {installation.enabled ? "停用" : "启用"}
                </button>

                <button
                  type="button"
                  onClick={() => setShowConfigDialog(true)}
                  className="inline-flex h-9 items-center gap-2 rounded-lg border border-os-border px-3 text-xs font-medium text-os-subtle transition-colors hover:border-os-accent/40 hover:text-os-text-high"
                >
                  <Settings size={14} />
                  配置
                </button>

                <Link
                  href="/agent-marketplace/installations"
                  className="inline-flex h-9 items-center gap-2 rounded-lg border border-os-border px-3 text-xs font-medium text-os-subtle transition-colors hover:text-os-text-high"
                >
                  <Layers size={14} />
                  管理安装
                </Link>

                {showConfirmUninstall ? (
                  <div className="inline-flex items-center gap-2 rounded-lg border border-os-danger/20 bg-os-danger-soft px-3 py-2">
                    <span className="text-xs text-os-danger">确认卸载？</span>
                    <button
                      type="button"
                      onClick={handleUninstall}
                      disabled={uninstalling}
                      className="rounded bg-os-danger px-2 py-0.5 text-xs text-white hover:bg-os-danger/90 disabled:opacity-50"
                    >
                      {uninstalling ? "卸载中..." : "确认"}
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowConfirmUninstall(false)}
                      className="rounded bg-os-elevated px-2 py-0.5 text-xs text-os-subtle hover:text-os-text-high"
                    >
                      取消
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => setShowConfirmUninstall(true)}
                    className="inline-flex h-9 items-center gap-2 rounded-lg border border-os-border px-3 text-xs font-medium text-os-subtle transition-colors hover:border-os-danger/30 hover:text-os-danger"
                  >
                    <Trash2 size={14} />
                    卸载
                  </button>
                )}
              </div>
            </section>
          )}
        </div>

        {/* Right column (1/3) — Sticky sidebar */}
        <div className="lg:col-span-1">
          <div className="sticky top-24 space-y-4">
            {/* Install button card */}
            <section className="rounded-2xl border border-os-border/50 bg-os-surface/40 p-5 backdrop-blur-md">
              {isInstalled && installation ? (
                <div className="space-y-3">
                  <div className="flex items-center gap-2 text-os-success">
                    <CheckCircle2 size={16} />
                    <span className="text-sm font-semibold">已安装</span>
                  </div>
                  <p className="text-2xs text-os-subtle">
                    状态：{installation.enabled ? "运行中" : "已停用"}
                  </p>
                  <Link
                    href="/agent-marketplace/installations"
                    className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg border border-os-success/30 bg-os-success/10 px-3 text-xs font-medium text-os-success transition-colors hover:bg-os-success/15"
                  >
                    <Layers size={14} />
                    管理安装
                  </Link>
                </div>
              ) : (
                <div className="space-y-3">
                  <button
                    type="button"
                    onClick={handleInstall}
                    disabled={installing}
                    className={cn(
                      "inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg px-4 text-sm font-medium transition-all duration-200",
                      installing
                        ? "border border-os-accent text-os-accent bg-transparent cursor-wait"
                        : "bg-os-elevated text-os-text hover:bg-os-accent/20 hover:text-os-accent shadow-os-glow",
                    )}
                  >
                    {installing ? (
                      <Loader2 size={15} className="animate-spin" />
                    ) : (
                      <ArrowDownToLine size={15} />
                    )}
                    {installing ? "注入内核中..." : "注入内核"}
                  </button>
                  <p className="text-center text-2xs text-os-subtle">
                    安装到当前工作区，立即开始使用
                  </p>
                </div>
              )}
            </section>

            {/* Quick stats */}
            <section className="rounded-2xl border border-os-border/50 bg-os-surface/40 p-5 backdrop-blur-md">
              <h4 className="text-2xs font-semibold tracking-wider text-os-subtle">概览</h4>
              <div className="mt-3 space-y-2.5">
                <StatRow
                  icon={<ArrowDownToLine size={13} />}
                  label="安装次数"
                  value={String(agent.install_count)}
                />
                <StatRow
                  icon={<Star size={13} className="text-amber-400" />}
                  label="评分"
                  value={agent.rating.toFixed(1)}
                />
                <StatRow
                  icon={<Layers size={13} className="text-os-accent" />}
                  label="能力数"
                  value={String(agent.capabilities.length)}
                />
                <StatRow
                  icon={<Shield size={13} className="text-os-accent" />}
                  label="权限需求"
                  value={String(agent.required_permissions.length)}
                />
              </div>
            </section>

            {/* Permissions pills with icons */}
            {requiredPerms.length > 0 && (
              <section className="rounded-2xl border border-os-border/50 bg-os-surface/40 p-5 backdrop-blur-md">
                <h4 className="flex items-center gap-1.5 text-2xs font-semibold tracking-wider text-os-subtle">
                  <Shield size={12} />
                  权限要求
                </h4>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {requiredPerms.map((perm) => {
                    const meta = permissionMeta(perm);
                    return (
                      <span
                        key={perm}
                        className="inline-flex items-center gap-1 rounded-lg border border-os-border bg-os-elevated/60 px-2 py-1 text-2xs text-os-text"
                        title={perm}
                      >
                        <span className="text-xs">{meta.icon}</span>
                        {meta.label}
                      </span>
                    );
                  })}
                </div>
              </section>
            )}

            {/* Author / Version metadata */}
            <section className="rounded-2xl border border-os-border/50 bg-os-surface/40 p-5 backdrop-blur-md">
              <h4 className="text-2xs font-semibold tracking-wider text-os-subtle">元数据</h4>
              <div className="mt-3 space-y-2.5">
                <MetaRow
                  icon={<User size={13} />}
                  label="作者"
                  value={agent.publisher_name}
                />
                <MetaRow
                  icon={<Building2 size={13} />}
                  label="类型"
                  value={PUBLISHER_TYPE_LABELS[agent.publisher_type] || agent.publisher_type}
                />
                <MetaRow
                  icon={<Layers size={13} />}
                  label="版本"
                  value={`v${agent.version}`}
                />
                {agent.department && (
                  <MetaRow
                    icon={<Building2 size={13} />}
                    label="部门"
                    value={agent.department}
                  />
                )}
              </div>
            </section>
          </div>
        </div>
      </div>

      {/* Config Dialog */}
      {installation && (
        <AgentConfigDialog
          open={showConfigDialog}
          installation={installation}
          saving={savingConfig}
          error={error}
          onClose={() => setShowConfigDialog(false)}
          onSave={handleSaveConfig}
        />
      )}
    </main>
  );
}

function StatRow({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="inline-flex items-center gap-2 text-xs text-os-subtle">
        {icon}
        {label}
      </span>
      <span className="text-xs font-semibold text-os-text-high">{value}</span>
    </div>
  );
}

function MetaRow({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="inline-flex shrink-0 items-center gap-2 text-xs text-os-subtle">
        {icon}
        {label}
      </span>
      <span className="min-w-0 break-words text-right text-xs font-medium text-os-text-high">{value}</span>
    </div>
  );
}

function InfoItem({
  label,
  value,
  mono,
  color,
}: {
  label: string;
  value: string;
  mono?: boolean;
  color?: string;
}) {
  return (
    <div>
      <p className="text-2xs text-os-subtle">{label}</p>
      <p className={`mt-0.5 break-all ${mono ? "font-mono" : ""} text-xs ${color || "text-os-text-high"}`}>
        {value}
      </p>
    </div>
  );
}
