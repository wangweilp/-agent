"use client";

import { useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2, Settings, X } from "lucide-react";
import type { TenantAgentInstallation, MarketplaceConfigRequest } from "@/types/marketplace";

interface AgentConfigDialogProps {
  open: boolean;
  installation: TenantAgentInstallation;
  saving?: boolean;
  error?: string | null;
  onClose: () => void;
  onSave: (payload: MarketplaceConfigRequest) => void;
}

export function AgentConfigDialog({
  open,
  installation,
  saving = false,
  error = null,
  onClose,
  onSave,
}: AgentConfigDialogProps) {
  const [configText, setConfigText] = useState(() =>
    JSON.stringify(installation.config, null, 2),
  );
  const [permissionsText, setPermissionsText] = useState(() =>
    JSON.stringify(installation.permissions_granted, null, 2),
  );
  const [usageLimitText, setUsageLimitText] = useState(() =>
    JSON.stringify(installation.usage_limit_override, null, 2),
  );
  const [versionPinned, setVersionPinned] = useState(
    installation.version_pinned || "",
  );
  const [jsonError, setJsonError] = useState<string | null>(null);

  if (!open) return null;

  function safeParse(text: string, label: string): Record<string, unknown> | null {
    if (!text.trim()) return {};
    try {
      const parsed = JSON.parse(text);
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        setJsonError(`${label} 必须是有效的 JSON 对象`);
        return null;
      }
      return parsed as Record<string, unknown>;
    } catch {
      setJsonError(`${label} JSON 格式错误`);
      return null;
    }
  }

  function safeParseArray(text: string, label: string): string[] | null {
    if (!text.trim()) return [];
    try {
      const parsed = JSON.parse(text);
      if (!Array.isArray(parsed)) {
        setJsonError(`${label} 必须是 JSON 数组`);
        return null;
      }
      return parsed as string[];
    } catch {
      setJsonError(`${label} JSON 格式错误`);
      return null;
    }
  }

  function handleSave() {
    setJsonError(null);
    const config = safeParse(configText, "配置");
    if (config === null) return;
    const permissions = safeParseArray(permissionsText, "授权权限");
    if (permissions === null) return;
    const usageLimits = safeParse(usageLimitText, "用量限制");
    if (usageLimits === null) return;

    onSave({
      config: Object.keys(config).length > 0 ? config : undefined,
      permissions_granted: permissions.length > 0 ? permissions : undefined,
      usage_limit_override: usageLimits && Object.keys(usageLimits).length > 0 ? usageLimits : undefined,
      version_pinned: versionPinned || null,
    });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
      <div className="w-full max-w-lg rounded-lg border border-os-border bg-os-base shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-os-border px-5 py-3">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-os-text-high">
            <Settings size={16} className="text-os-accent" />
            编辑安装配置
          </h2>
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="rounded p-1 text-os-subtle hover:bg-os-elevated hover:text-os-text-high disabled:opacity-50"
          >
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="max-h-[70vh] overflow-y-auto px-5 py-4 space-y-4">
          {/* Installation ID hint */}
          <p className="rounded bg-os-elevated px-3 py-2 font-mono text-2xs text-os-muted">
            {installation.installation_id}
          </p>

          {/* Config JSON */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-os-subtle">
              配置 (JSON 对象)
            </label>
            <textarea
              rows={5}
              value={configText}
              onChange={(e) => setConfigText(e.target.value)}
              spellCheck={false}
              className="w-full rounded-md border border-os-border bg-os-elevated px-3 py-2 font-mono text-xs text-os-text-high outline-none placeholder:text-os-muted focus:border-os-accent"
              placeholder='{"key": "value"}'
            />
          </div>

          {/* Permissions Granted */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-os-subtle">
              已授权权限 (JSON 数组)
            </label>
            <textarea
              rows={4}
              value={permissionsText}
              onChange={(e) => setPermissionsText(e.target.value)}
              spellCheck={false}
              className="w-full rounded-md border border-os-border bg-os-elevated px-3 py-2 font-mono text-xs text-os-text-high outline-none placeholder:text-os-muted focus:border-os-accent"
              placeholder='["agent:execute", "memory:read"]'
            />
          </div>

          {/* Usage Limit Override */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-os-subtle">
              用量限制覆盖 (JSON 对象)
            </label>
            <textarea
              rows={4}
              value={usageLimitText}
              onChange={(e) => setUsageLimitText(e.target.value)}
              spellCheck={false}
              className="w-full rounded-md border border-os-border bg-os-elevated px-3 py-2 font-mono text-xs text-os-text-high outline-none placeholder:text-os-muted focus:border-os-accent"
              placeholder='{"max_calls": 1000}'
            />
          </div>

          {/* Version Pinned */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-os-subtle">
              锁定版本 (留空 = 跟随最新)
            </label>
            <input
              type="text"
              value={versionPinned}
              onChange={(e) => setVersionPinned(e.target.value)}
              className="h-10 w-full rounded-md border border-os-border bg-os-elevated px-3 text-sm text-os-text-high outline-none placeholder:text-os-muted focus:border-os-accent"
              placeholder="例如: 1.2.0"
            />
          </div>

          {/* JSON error */}
          {jsonError && (
            <div className="flex items-center gap-2 rounded-md border border-red-400/20 bg-red-400/10 px-3 py-2 text-xs text-red-300">
              <AlertTriangle size={13} />
              {jsonError}
            </div>
          )}

          {/* API error */}
          {error && (
            <div className="flex items-center gap-2 rounded-md border border-red-400/20 bg-red-400/10 px-3 py-2 text-xs text-red-200">
              <AlertTriangle size={13} />
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 border-t border-os-border px-5 py-3">
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="inline-flex h-9 items-center rounded-md border border-os-border px-3 text-xs font-medium text-os-subtle hover:text-os-text-high disabled:opacity-50"
          >
            取消
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="inline-flex h-9 items-center gap-2 rounded-md bg-os-accent px-4 text-xs font-medium text-white transition-colors hover:bg-os-accent/90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <CheckCircle2 size={14} />
            )}
            {saving ? "保存中..." : "保存"}
          </button>
        </div>
      </div>
    </div>
  );
}
