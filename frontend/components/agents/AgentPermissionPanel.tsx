"use client";

import { AlertTriangle, CheckCircle2, Shield, ShieldAlert, ShieldCheck, XCircle } from "lucide-react";

interface AgentPermissionPanelProps {
  required: string[];
  granted: string[];
  missing: string[];
  loading?: boolean;
}

function permissionLabel(perm: string): string {
  if (perm.startsWith("agent:")) return `智能体 — ${perm.replace("agent:", "")}`;
  if (perm.startsWith("memory:")) return `记忆 — ${perm.replace("memory:", "")}`;
  if (perm.startsWith("kg:")) return `Knowledge Graph — ${perm.replace("kg:", "")}`;
  return perm;
}

export function AgentPermissionPanel({
  required,
  granted,
  missing,
  loading = false,
}: AgentPermissionPanelProps) {
  if (loading) {
    return (
      <div className="os-card p-4">
        <div className="shimmer-bg h-4 w-28 rounded bg-os-elevated" />
        <div className="mt-3 space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="shimmer-bg h-8 w-full rounded bg-os-elevated" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="os-card p-4">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-os-text-high">
        <Shield size={16} className="text-os-accent" />
        权限需求
      </h3>

      <div className="mt-4 grid gap-2 sm:grid-cols-3">
        {/* Required */}
        <div className="rounded-md border border-os-border bg-os-elevated/30 p-3">
          <p className="flex items-center gap-1.5 text-xs font-medium text-os-subtle">
            <ShieldAlert size={13} className="text-amber-400" />
            需要 ({required.length})
          </p>
          <ul className="mt-2 space-y-1">
            {required.map((perm) => (
              <li key={perm} className="flex items-start gap-1.5 text-xs text-os-text-high">
                <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400" />
                {permissionLabel(perm)}
              </li>
            ))}
          </ul>
        </div>

        {/* Granted */}
        <div className="rounded-md border border-emerald-400/20 bg-emerald-400/5 p-3">
          <p className="flex items-center gap-1.5 text-xs font-medium text-emerald-300">
            <ShieldCheck size={13} />
            已授权 ({granted.length})
          </p>
          <ul className="mt-2 space-y-1">
            {granted.length > 0 ? (
              granted.map((perm) => (
                <li key={perm} className="flex items-start gap-1.5 text-xs text-emerald-200">
                  <CheckCircle2 size={12} className="mt-0.5 shrink-0" />
                  {permissionLabel(perm)}
                </li>
              ))
            ) : (
              <li className="text-xs text-os-muted">-</li>
            )}
          </ul>
        </div>

        {/* Missing */}
        <div className="rounded-md border border-red-400/10 bg-red-400/5 p-3">
          <p className="flex items-center gap-1.5 text-xs font-medium text-red-300">
            <XCircle size={13} />
            缺失 ({missing.length})
          </p>
          <ul className="mt-2 space-y-1">
            {missing.length > 0 ? (
              missing.map((perm) => (
                <li key={perm} className="flex items-start gap-1.5 text-xs text-red-200">
                  <AlertTriangle size={12} className="mt-0.5 shrink-0" />
                  {permissionLabel(perm)}
                </li>
              ))
            ) : (
              <li className="flex items-center gap-1 text-xs text-emerald-300">
                <CheckCircle2 size={12} />
                所有权限已授予
              </li>
            )}
          </ul>
        </div>
      </div>
    </div>
  );
}
