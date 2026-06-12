"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowDownToLine,
  Bot,
  FileText,
  Layers,
  Loader2,
  Power,
  PowerOff,
  Settings,
  Shield,
  Star,
  Trash2,
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

function LoadingDetail() {
  return (
    <main className="mx-auto w-full max-w-4xl px-4 py-8 sm:px-6">
      <div className="shimmer-bg mb-4 h-5 w-32 rounded bg-os-elevated" />
      <div className="os-card p-6">
        <div className="shimmer-bg h-6 w-48 rounded bg-os-elevated" />
        <div className="mt-4 space-y-2">
          <div className="shimmer-bg h-3 w-full rounded bg-os-elevated" />
          <div className="shimmer-bg h-3 w-3/4 rounded bg-os-elevated" />
        </div>
        <div className="mt-6 flex gap-2">
          <div className="shimmer-bg h-6 w-16 rounded bg-os-elevated" />
          <div className="shimmer-bg h-6 w-12 rounded bg-os-elevated" />
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
      setError(`[${apiErr.status || "ERR"}] ${apiErr.message || "加载失败"}`);
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
        setError(`[${apiErr.status || "ERR"}] ${apiErr.message || "安装失败"}`);
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
      setError(`[${apiErr.status || "ERR"}] ${apiErr.message || "操作失败"}`);
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
      setError(`[${apiErr.status || "ERR"}] ${apiErr.message || "卸载失败"}`);
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
      setError(`[${apiErr.status || "ERR"}] ${apiErr.message || "配置保存失败"}`);
    } finally {
      setSavingConfig(false);
    }
  };

  if (loading) return <LoadingDetail />;
  if (!agent) {
    return (
      <main className="mx-auto w-full max-w-4xl px-4 py-8 sm:px-6">
        <div className="os-card flex min-h-64 flex-col items-center justify-center gap-3 text-center">
          <Bot size={32} className="text-os-muted" />
          <h2 className="text-base font-semibold text-os-text-high">Agent 不存在</h2>
          <p className="text-sm text-os-subtle">请检查 Marketplace Agent ID 是否正确。</p>
          <Link
            href="/agent-marketplace"
            className="inline-flex items-center gap-2 rounded-md border border-os-border px-3 py-1.5 text-xs text-os-subtle hover:text-os-text-high"
          >
            <ArrowLeft size={14} />
            返回 Marketplace
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-4xl px-4 py-8 sm:px-6">
      {/* Back link */}
      <Link
        href="/agent-marketplace"
        className="mb-4 inline-flex items-center gap-1.5 text-xs text-os-subtle hover:text-os-text-high"
      >
        <ArrowLeft size={14} />
        返回 Marketplace
      </Link>

      {error && (
        <div className="mb-4 rounded-md border border-red-400/20 bg-red-400/10 p-3 text-sm text-red-200">
          {error}
        </div>
      )}

      {/* Agent Info */}
      <section className="os-card p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="flex min-w-0 items-start gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg border border-os-accent/30 bg-os-accent/15 text-os-accent">
              <Bot size={22} />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-os-text-high">{agent.display_name}</h1>
              <p className="mt-1 text-sm text-os-subtle">{agent.description}</p>
              <div className="mt-3 flex flex-wrap gap-1.5">
                <span className="os-badge bg-os-elevated text-os-subtle">{agent.category}</span>
                {agent.department && (
                  <span className="os-badge bg-os-elevated text-os-subtle">{agent.department}</span>
                )}
                <AgentPricingBadge model={agent.pricing_model} />
                <span className="os-badge bg-os-elevated text-os-subtle">v{agent.version}</span>
                <span className="os-badge bg-os-elevated text-os-subtle">{agent.publisher_name}</span>
              </div>
            </div>
          </div>

          <span
            className={`os-badge shrink-0 ${
              agent.status === "active"
                ? "bg-emerald-400/10 text-emerald-300"
                : agent.status === "beta"
                  ? "bg-amber-400/10 text-amber-300"
                  : "bg-zinc-500/10 text-os-muted"
            }`}
          >
            {agent.status}
          </span>
        </div>

        {agent.long_description && (
          <div className="mt-6 rounded-md border border-os-border bg-os-elevated/30 p-4">
            <h3 className="flex items-center gap-2 text-xs font-semibold text-os-subtle">
              <FileText size={13} />
              详细介绍
            </h3>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-os-text-high">
              {agent.long_description}
            </p>
          </div>
        )}

        {/* Stats */}
        <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Metric label="安装次数" value={String(agent.install_count)} />
          <Metric label="评分" value={agent.rating.toFixed(1)} icon={<Star size={13} className="text-amber-400" />} />
          <Metric label="能力数量" value={String(agent.capabilities.length)} />
          <Metric label="权限需求" value={String(agent.required_permissions.length)} icon={<Shield size={13} className="text-os-accent" />} />
        </div>
      </section>

      {/* Capabilities */}
      <section className="os-card mt-4 p-4">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-os-text-high">
          <Layers size={16} className="text-os-accent" />
          能力
        </h3>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {agent.capabilities.map((cap) => (
            <span key={cap} className="rounded bg-os-elevated px-2.5 py-1 text-xs text-os-text-high">
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
                <span key={wf} className="rounded bg-violet-400/10 px-2.5 py-1 text-xs text-violet-300">
                  {wf}
                </span>
              ))}
            </div>
          </>
        )}
      </section>

      {/* Permissions */}
      <div className="mt-4">
        <AgentPermissionPanel
          required={permissions?.required || agent.required_permissions}
          granted={permissions?.granted || []}
          missing={permissions?.missing || agent.required_permissions}
        />
      </div>

      {/* Usage (MVP) */}
      {isInstalled && <div className="mt-4"><AgentUsageSummary usage={usage} /></div>}

      {/* Installation Status */}
      <section className="os-card mt-4 p-4">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-os-text-high">
          <ArrowDownToLine size={16} className="text-os-accent" />
          安装状态
        </h3>

        {isInstalled && installation ? (
          <div className="mt-4 space-y-3">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <InfoItem label="安装 ID" value={installation.installation_id} mono />
              <InfoItem label="状态" value={installation.status} />
              <InfoItem
                label="启用"
                value={installation.enabled ? "是" : "否"}
                color={installation.enabled ? "text-emerald-300" : "text-red-300"}
              />
              <InfoItem label="锁定版本" value={installation.version_pinned || "跟随最新"} />
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-2">
              <InfoItem label="安装人" value={installation.installed_by} />
              <InfoItem label="安装时间" value={installation.installed_at ? new Date(installation.installed_at).toLocaleString("zh-CN") : "-"} />
            </div>

            {/* Config */}
            {Object.keys(installation.config).length > 0 && (
              <details className="mt-2">
                <summary className="cursor-pointer text-xs font-medium text-os-subtle hover:text-os-text-high">
                  配置 ({Object.keys(installation.config).length} 项)
                </summary>
                <pre className="mt-2 overflow-auto rounded bg-os-elevated p-3 text-2xs text-os-subtle">
                  {JSON.stringify(installation.config, null, 2)}
                </pre>
              </details>
            )}

            {/* Granted permissions */}
            {installation.permissions_granted.length > 0 && (
              <div>
                <p className="text-xs font-medium text-os-subtle">已授权权限</p>
                <div className="mt-1 flex flex-wrap gap-1">
                  {installation.permissions_granted.map((p) => (
                    <span key={p} className="rounded bg-emerald-400/10 px-2 py-0.5 text-2xs text-emerald-300">
                      {p}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Actions */}
            <div className="flex flex-wrap gap-2 pt-2">
              <button
                type="button"
                onClick={handleToggle}
                disabled={toggling}
                className={`inline-flex h-9 items-center gap-2 rounded-md px-3 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                  installation.enabled
                    ? "bg-red-400/10 text-red-300 hover:bg-red-400/15"
                    : "bg-emerald-400/10 text-emerald-300 hover:bg-emerald-400/15"
                }`}
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
                className="inline-flex h-9 items-center gap-2 rounded-md border border-os-border px-3 text-xs font-medium text-os-subtle transition-colors hover:border-os-accent/40 hover:text-os-text-high"
              >
                <Settings size={14} />
                配置
              </button>

              <Link
                href={`/agent-marketplace/installations`}
                className="inline-flex h-9 items-center gap-2 rounded-md border border-os-border px-3 text-xs font-medium text-os-subtle transition-colors hover:text-os-text-high"
              >
                <Layers size={14} />
                管理安装
              </Link>

              {showConfirmUninstall ? (
                <div className="inline-flex items-center gap-2 rounded-md border border-red-400/20 bg-red-400/5 px-3 py-2">
                  <span className="text-xs text-red-300">确认卸载？</span>
                  <button
                    type="button"
                    onClick={handleUninstall}
                    disabled={uninstalling}
                    className="rounded bg-red-400/20 px-2 py-0.5 text-xs text-red-200 hover:bg-red-400/30 disabled:opacity-50"
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
                  className="inline-flex h-9 items-center gap-2 rounded-md border border-os-border px-3 text-xs font-medium text-os-subtle transition-colors hover:border-red-400/30 hover:text-red-300"
                >
                  <Trash2 size={14} />
                  卸载
                </button>
              )}
            </div>
          </div>
        ) : (
          <div className="mt-4">
            <p className="text-sm text-os-subtle">此 Agent 尚未安装到当前工作区。</p>
            <button
              type="button"
              onClick={handleInstall}
              disabled={installing}
              className="mt-3 inline-flex h-9 items-center gap-2 rounded-md bg-os-accent px-4 text-xs font-medium text-white transition-colors hover:bg-os-accent/90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {installing ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <ArrowDownToLine size={14} />
              )}
              {installing ? "安装中..." : "安装 Agent"}
            </button>
          </div>
        )}
      </section>

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

function Metric({
  label,
  value,
  icon,
}: {
  label: string;
  value: string;
  icon?: React.ReactNode;
}) {
  return (
    <div className="rounded-md border border-os-border bg-os-elevated/30 px-3 py-2 text-center">
      <p className="text-2xs text-os-muted">{label}</p>
      <p className="mt-1 flex items-center justify-center gap-1 text-sm font-semibold text-os-text-high">
        {icon}
        {value}
      </p>
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
      <p className="text-2xs text-os-muted">{label}</p>
      <p className={`mt-0.5 ${mono ? "font-mono" : ""} text-xs ${color || "text-os-text-high"}`}>
        {value}
      </p>
    </div>
  );
}
