"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Clock,
  ExternalLink,
  Layers,
  Loader2,
  Power,
  PowerOff,
  RefreshCw,
  Settings,
  Trash2,
  XCircle,
} from "lucide-react";

import { AgentConfigDialog } from "@/components/agents/AgentConfigDialog";
import {
  disableMarketplaceInstallation,
  enableMarketplaceInstallation,
  listMarketplaceInstallations,
  uninstallMarketplaceInstallation,
  updateMarketplaceInstallationConfig,
  type MarketplaceApiError,
} from "@/services/marketplace";
import type { MarketplaceConfigRequest, TenantAgentInstallation } from "@/types/marketplace";

function statusBadge(status: string, enabled: boolean) {
  if (enabled && status === "active") {
    return (
      <span className="os-badge bg-emerald-400/10 text-emerald-300">
        <CheckCircle2 size={11} />
        运行中
      </span>
    );
  }
  if (status === "disabled") {
    return (
      <span className="os-badge bg-zinc-500/10 text-os-muted">
        <XCircle size={11} />
        已停用
      </span>
    );
  }
  if (status === "error") {
    return (
      <span className="os-badge bg-red-400/10 text-red-300">
        <AlertTriangle size={11} />
        异常
      </span>
    );
  }
  return <span className="os-badge bg-zinc-500/10 text-os-muted">{status}</span>;
}

export default function InstallationsPage() {
  const [installations, setInstallations] = useState<TenantAgentInstallation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Action states
  const [toggling, setToggling] = useState<Set<string>>(new Set());
  const [uninstalling, setUninstalling] = useState<Set<string>>(new Set());
  const [savingConfig, setSavingConfig] = useState<string | null>(null);
  const [confirmUninstall, setConfirmUninstall] = useState<string | null>(null);
  const [configDialogInst, setConfigDialogInst] = useState<TenantAgentInstallation | null>(null);

  const fetchInstallations = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listMarketplaceInstallations({ include_disabled: true });
      setInstallations(res.installations);
    } catch (e: unknown) {
      const apiErr = e as MarketplaceApiError;
      setError(`[${apiErr.status || "ERR"}] ${apiErr.message || "加载失败"}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchInstallations();
  }, [fetchInstallations]);

  const handleToggle = async (inst: TenantAgentInstallation) => {
    setToggling((prev) => new Set(prev).add(inst.installation_id));
    setError(null);
    try {
      if (inst.enabled) {
        const res = await disableMarketplaceInstallation(inst.installation_id);
        updateOne(res.installation);
      } else {
        const res = await enableMarketplaceInstallation(inst.installation_id);
        updateOne(res.installation);
      }
    } catch (e: unknown) {
      const apiErr = e as MarketplaceApiError;
      setError(`[${apiErr.status || "ERR"}] ${apiErr.message || "操作失败"}`);
    } finally {
      setToggling((prev) => {
        const next = new Set(prev);
        next.delete(inst.installation_id);
        return next;
      });
    }
  };

  const handleUninstall = async (inst: TenantAgentInstallation) => {
    setUninstalling((prev) => new Set(prev).add(inst.installation_id));
    setError(null);
    try {
      await uninstallMarketplaceInstallation(inst.installation_id);
      setInstallations((prev) => prev.filter((i) => i.installation_id !== inst.installation_id));
    } catch (e: unknown) {
      const apiErr = e as MarketplaceApiError;
      setError(`[${apiErr.status || "ERR"}] ${apiErr.message || "卸载失败"}`);
    } finally {
      setUninstalling((prev) => {
        const next = new Set(prev);
        next.delete(inst.installation_id);
        return next;
      });
      setConfirmUninstall(null);
    }
  };

  const handleSaveConfig = async (payload: MarketplaceConfigRequest) => {
    if (!configDialogInst) return;
    setSavingConfig(configDialogInst.installation_id);
    setError(null);
    try {
      const res = await updateMarketplaceInstallationConfig(
        configDialogInst.installation_id,
        payload,
      );
      updateOne(res.installation);
      setConfigDialogInst(null);
    } catch (e: unknown) {
      const apiErr = e as MarketplaceApiError;
      setError(`[${apiErr.status || "ERR"}] ${apiErr.message || "配置保存失败"}`);
    } finally {
      setSavingConfig(null);
    }
  };

  const updateOne = (updated: TenantAgentInstallation) => {
    setInstallations((prev) =>
      prev.map((i) => (i.installation_id === updated.installation_id ? updated : i)),
    );
  };

  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6">
      {/* Header */}
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <Link
            href="/agent-marketplace"
            className="mb-2 inline-flex items-center gap-1.5 text-xs text-os-subtle hover:text-os-text-high"
          >
            <ArrowLeft size={14} />
            返回 Marketplace
          </Link>
          <h1 className="text-3xl font-semibold tracking-normal text-os-text-high">
            已安装 Agent
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-os-subtle">
            管理当前工作区已安装的 Agent。启用、停用、更新配置或卸载。
          </p>
        </div>

        <button
          type="button"
          onClick={() => void fetchInstallations()}
          disabled={loading}
          className="inline-flex h-9 items-center justify-center gap-2 rounded-md border border-os-border bg-os-surface px-3 text-xs font-medium text-os-subtle transition-colors hover:text-os-text-high disabled:cursor-not-allowed disabled:opacity-60"
        >
          {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          刷新
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 rounded-md border border-red-400/20 bg-red-400/10 p-3 text-sm text-red-200">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="os-card p-4">
              <div className="shimmer-bg h-5 w-40 rounded bg-os-elevated" />
              <div className="mt-2 flex gap-4">
                <div className="shimmer-bg h-4 w-24 rounded bg-os-elevated" />
                <div className="shimmer-bg h-4 w-20 rounded bg-os-elevated" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Empty */}
      {!loading && installations.length === 0 && !error && (
        <section className="os-card flex min-h-48 flex-col items-center justify-center gap-3 px-4 py-10 text-center">
          <Layers size={28} className="text-os-muted" />
          <h2 className="text-base font-semibold text-os-text-high">暂无已安装 Agent</h2>
          <p className="text-sm text-os-subtle">
            前往{" "}
            <Link href="/agent-marketplace" className="text-os-accent hover:underline">
              智能体市场
            </Link>
            {" "}浏览并安装 Agent。
          </p>
        </section>
      )}

      {/* Installation list */}
      {!loading &&
        installations.map((inst) => {
          const isToggling = toggling.has(inst.installation_id);
          const isUninstalling = uninstalling.has(inst.installation_id);

          return (
            <section key={inst.installation_id} className="os-card mb-3 p-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <Link
                      href={`/agent-marketplace/${inst.marketplace_agent_id}`}
                      className="text-sm font-semibold text-os-text-high hover:text-os-accent"
                    >
                      {inst.agent_id}
                    </Link>
                    {statusBadge(inst.status, inst.enabled)}
                  </div>
                  <p className="mt-1 font-mono text-2xs text-os-muted">
                    {inst.installation_id}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1.5 text-2xs text-os-subtle">
                    <span className="flex items-center gap-1">
                      <Clock size={11} />
                      {inst.installed_at ? new Date(inst.installed_at).toLocaleString("zh-CN") : "-"}
                    </span>
                    {inst.version_pinned && (
                      <span className="rounded bg-amber-400/10 px-1.5 py-0.5 text-amber-300">
                        锁定: {inst.version_pinned}
                      </span>
                    )}
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  {/* Toggle */}
                  <button
                    type="button"
                    onClick={() => handleToggle(inst)}
                    disabled={isToggling}
                    className={`inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                      inst.enabled
                        ? "bg-red-400/10 text-red-300 hover:bg-red-400/15"
                        : "bg-emerald-400/10 text-emerald-300 hover:bg-emerald-400/15"
                    }`}
                  >
                    {isToggling ? (
                      <Loader2 size={12} className="animate-spin" />
                    ) : inst.enabled ? (
                      <PowerOff size={12} />
                    ) : (
                      <Power size={12} />
                    )}
                    {inst.enabled ? "停用" : "启用"}
                  </button>

                  {/* Config */}
                  <button
                    type="button"
                    onClick={() => setConfigDialogInst(inst)}
                    className="inline-flex h-8 items-center gap-1.5 rounded-md border border-os-border px-2.5 text-xs font-medium text-os-subtle transition-colors hover:border-os-accent/40 hover:text-os-text-high"
                  >
                    <Settings size={12} />
                    配置
                  </button>

                  {/* Detail */}
                  <Link
                    href={`/agent-marketplace/${inst.marketplace_agent_id}`}
                    className="inline-flex h-8 items-center gap-1.5 rounded-md border border-os-border px-2.5 text-xs font-medium text-os-subtle transition-colors hover:text-os-text-high"
                  >
                    <ExternalLink size={12} />
                    详情
                  </Link>

                  {/* Uninstall */}
                  {confirmUninstall === inst.installation_id ? (
                    <div className="inline-flex items-center gap-1.5 rounded-md border border-red-400/20 bg-red-400/5 px-2 py-1">
                      <span className="text-xs text-red-300">确认卸载？</span>
                      <button
                        type="button"
                        onClick={() => handleUninstall(inst)}
                        disabled={isUninstalling}
                        className="rounded bg-red-400/20 px-2 py-0.5 text-xs text-red-200 hover:bg-red-400/30 disabled:opacity-50"
                      >
                        {isUninstalling ? "..." : "确认"}
                      </button>
                      <button
                        type="button"
                        onClick={() => setConfirmUninstall(null)}
                        className="rounded px-2 py-0.5 text-xs text-os-subtle hover:text-os-text-high"
                      >
                        取消
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setConfirmUninstall(inst.installation_id)}
                      className="inline-flex h-8 items-center gap-1.5 rounded-md border border-os-border px-2.5 text-xs font-medium text-os-subtle transition-colors hover:border-red-400/30 hover:text-red-300"
                    >
                      <Trash2 size={12} />
                      卸载
                    </button>
                  )}
                </div>
              </div>

              {/* Config/perms summary */}
              <div className="mt-3 flex flex-wrap gap-4 text-xs text-os-subtle">
                {Object.keys(inst.config).length > 0 && (
                  <details>
                    <summary className="cursor-pointer hover:text-os-text-high">
                      配置 ({Object.keys(inst.config).length} 项)
                    </summary>
                  </details>
                )}
                {inst.permissions_granted.length > 0 && (
                  <span>
                    已授权 {inst.permissions_granted.length} 项权限
                  </span>
                )}
              </div>
            </section>
          );
        })}

      {/* Config Dialog */}
      {configDialogInst && (
        <AgentConfigDialog
          open={true}
          installation={configDialogInst}
          saving={savingConfig === configDialogInst.installation_id}
          error={error}
          onClose={() => setConfigDialogInst(null)}
          onSave={handleSaveConfig}
        />
      )}
    </main>
  );
}
