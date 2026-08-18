"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  Calendar,
  Clock,
  Copy,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  Plus,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { ApiKeyReveal } from "@/components/open-platform/ApiKeyReveal";
import { StatusBadge } from "@/components/open-platform/StatusBadge";
import { DangerConfirmDialog } from "@/components/os/danger-confirm-dialog";
import {
  createDeveloperApiKey,
  listDeveloperApiKeys,
  revokeDeveloperApiKey,
  type DeveloperApiError,
} from "@/services/developer";
import { toast } from "@/stores/ui-store";
import { cn } from "@/lib/utils";
import type { DeveloperApiKey } from "@/types/open-platform";

// ── 模拟配额数据（API 未返回用量，前端安全模拟） ──
const MOCK_QUOTAS = [
  { label: "API 请求", usage: 14052, quota: 50000, period: "本月" },
  { label: "Agent 运行", usage: 892, quota: 2000, period: "本月" },
  { label: "Token 消耗", usage: 1280000, quota: 5000000, period: "本月" },
];

function formatNumber(n: number): string {
  return n.toLocaleString("en-US");
}

function formatRelativeTime(iso: string | null): string {
  if (!iso) return "从未使用";
  const d = new Date(iso);
  const now = Date.now();
  const diff = now - d.getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} 天前`;
  return d.toLocaleDateString("zh-CN");
}

function QuotaBar({ usage, quota }: { usage: number; quota: number }) {
  const ratio = Math.min(usage / quota, 1);
  const pct = (ratio * 100).toFixed(1);
  const color = ratio >= 0.9 ? "bg-os-danger" : ratio >= 0.75 ? "bg-os-warning" : "bg-os-accent";
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-os-border/50">
      <div
        className={cn("h-full rounded-full transition-all duration-500", color)}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

export default function ApiKeysPage() {
  const [keys, setKeys] = useState<DeveloperApiKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [includeRevoked, setIncludeRevoked] = useState(false);
  const [newName, setNewName] = useState("");
  const [scopesText, setScopesText] = useState("agent:read");
  const [creating, setCreating] = useState(false);
  const [revealKey, setRevealKey] = useState<string | null>(null);
  const [revoking, setRevoking] = useState<Set<string>>(new Set());
  // 任务 A: 每个密钥的 reveal 状态（hover/click 解除 blur）
  const [revealedIds, setRevealedIds] = useState<Set<string>>(new Set());
  // 任务 C: Danger Zone
  const [showRevokeAll, setShowRevokeAll] = useState(false);
  const [revokingAll, setRevokingAll] = useState(false);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await listDeveloperApiKeys(includeRevoked);
      setKeys(r.api_keys);
    } catch (e: unknown) {
      const ae = e as DeveloperApiError;
      setError(`[${ae.status}] ${ae.message}`);
    } finally {
      setLoading(false);
    }
  }, [includeRevoked]);

  useEffect(() => {
    void fetch();
  }, [fetch]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const scopes = scopesText.split(",").map((s) => s.trim()).filter(Boolean);
    if (!scopes.length) {
      setError("权限范围（scopes）不能为空");
      return;
    }
    setCreating(true);
    try {
      const r = await createDeveloperApiKey({ name: newName, scopes });
      setRevealKey(r.raw_key);
      setNewName("");
      setScopesText("agent:read");
      await fetch();
      toast.success("API Key 已创建", "请立即复制保存");
    } catch (e: unknown) {
      const ae = e as DeveloperApiError;
      setError(`[${ae.status}] ${ae.message}`);
    } finally {
      setCreating(false);
    }
  }

  async function handleRevoke(id: string) {
    setRevoking((prev) => new Set(prev).add(id));
    try {
      await revokeDeveloperApiKey(id);
      await fetch();
      toast.success("密钥已撤销");
    } catch (e: unknown) {
      const ae = e as DeveloperApiError;
      setError(`[${ae.status}] ${ae.message}`);
      toast.danger("撤销失败", ae.message);
    } finally {
      setRevoking((prev) => {
        const n = new Set(prev);
        n.delete(id);
        return n;
      });
    }
  }

  // 任务 C: 批量撤销所有活跃密钥（复用现有 revokeDeveloperApiKey）
  async function handleRevokeAll() {
    const activeKeys = keys.filter((k) => k.status === "active");
    if (!activeKeys.length) {
      setShowRevokeAll(false);
      return;
    }
    setRevokingAll(true);
    let successCount = 0;
    let failCount = 0;
    for (const k of activeKeys) {
      try {
        await revokeDeveloperApiKey(k.api_key_id);
        successCount++;
      } catch {
        failCount++;
      }
    }
    await fetch();
    setRevokingAll(false);
    setShowRevokeAll(false);
    if (failCount === 0) {
      toast.success(`已撤销 ${successCount} 个密钥`);
    } else {
      toast.warning(`撤销完成`, `成功 ${successCount}，失败 ${failCount}`);
    }
  }

  function toggleReveal(id: string) {
    setRevealedIds((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  }

  async function copyKeyPrefix(prefix: string) {
    try {
      await navigator.clipboard.writeText(prefix);
      toast.success("密钥前缀已复制");
    } catch {
      toast.warning("复制失败", "请手动选择文本复制");
    }
  }

  const activeCount = keys.filter((k) => k.status === "active").length;

  return (
    <main className="mx-auto max-w-4xl px-4 py-8">
      <Link
        href="/developer"
        className="mb-4 inline-flex items-center gap-1.5 text-xs text-os-subtle transition-colors hover:text-os-text-high"
      >
        <ArrowLeft size={14} />
        开发者控制台
      </Link>

      {/* Header */}
      <div className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-os-text-high">API Key</h1>
          <p className="text-sm text-os-subtle">管理开发者 API Key · 密钥保险库</p>
        </div>
        <button
          onClick={() => void fetch()}
          disabled={loading}
          className="inline-flex h-9 items-center gap-2 rounded-lg border border-os-border bg-os-surface px-3 text-xs text-os-subtle transition-colors hover:text-os-text-high disabled:opacity-60"
        >
          {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          刷新
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-os-danger/20 bg-os-danger-soft p-3 text-sm text-os-danger">
          {error}
        </div>
      )}

      {/* ── 任务 B: Vercel 风格配额卡片 ── */}
      <section className="mb-6 rounded-2xl border border-os-border/50 bg-os-surface/40 p-5 backdrop-blur-md">
        <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-os-text-high">
          <Activity size={15} className="text-os-accent" />
          用量与配额
        </h3>
        <div className="space-y-4">
          {MOCK_QUOTAS.map((q) => {
            const ratio = q.usage / q.quota;
            const isWarning = ratio >= 0.75 && ratio < 0.9;
            const isDanger = ratio >= 0.9;
            return (
              <div key={q.label}>
                <div className="mb-1.5 flex items-center justify-between">
                  <span className="text-xs text-os-subtle">
                    {q.label}
                    <span className="ml-2 text-2xs text-os-subtle">{q.period}</span>
                  </span>
                  <span className="font-mono text-xs">
                    <span
                      className={cn(
                        "font-semibold",
                        isDanger ? "text-os-danger" : isWarning ? "text-os-warning" : "text-os-text-high",
                      )}
                    >
                      {formatNumber(q.usage)}
                    </span>
                    <span className="text-os-subtle"> / {formatNumber(q.quota)}</span>
                  </span>
                </div>
                <QuotaBar usage={q.usage} quota={q.quota} />
              </div>
            );
          })}
        </div>
        <p className="mt-3 text-xs leading-5 text-os-subtle">配额基于当前套餐，超限将自动限流。数据为模拟值。</p>
      </section>

      {/* ── 任务 A: 创建表单 ── */}
      <form
        onSubmit={handleCreate}
        className="mb-6 space-y-3 rounded-2xl border border-os-border/50 bg-os-surface/40 p-5 backdrop-blur-md"
      >
        <h3 className="flex items-center gap-2 text-sm font-semibold text-os-text-high">
          <Plus size={14} className="text-os-accent" />
          创建 API Key
        </h3>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-2xs font-medium text-os-subtle">名称</label>
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="生产环境密钥"
              className="h-9 w-full rounded-lg border border-os-border bg-os-elevated px-3 text-sm text-os-text-high outline-none transition-colors placeholder:text-os-subtle focus:border-os-accent"
            />
          </div>
          <div>
            <label className="mb-1 block text-2xs font-medium text-os-subtle">权限范围（Scopes，逗号分隔）</label>
            <input
              value={scopesText}
              onChange={(e) => setScopesText(e.target.value)}
              placeholder="agent:read, agent:submit"
              className="h-9 w-full rounded-lg border border-os-border bg-os-elevated px-3 text-sm text-os-text-high outline-none transition-colors placeholder:text-os-subtle focus:border-os-accent"
            />
          </div>
        </div>
        <button
          type="submit"
          disabled={creating || !newName}
          className="inline-flex h-9 items-center gap-2 rounded-lg bg-os-accent px-4 text-xs font-medium text-white transition-colors hover:bg-os-accent/90 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {creating ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
          创建 API Key
        </button>
      </form>

      {/* ── 任务 A: 密钥保险库列表 ── */}
      <div className="mb-3 flex items-center justify-between">
        <span className="text-xs text-os-subtle">
          {keys.length} 个密钥 · <span className="text-os-success">{activeCount} 个活跃</span>
        </span>
        <label className="flex items-center gap-2 text-xs text-os-subtle">
          <input
            type="checkbox"
            checked={includeRevoked}
            onChange={(e) => setIncludeRevoked(e.target.checked)}
            className="rounded"
          />
          包含已撤销
        </label>
      </div>

      {loading ? (
        <div className="space-y-2">
          {[1, 2].map((i) => (
            <div
              key={i}
              className="rounded-2xl border border-os-border/50 bg-os-surface/40 p-4 backdrop-blur-md"
            >
              <div className="shimmer-bg h-4 w-32 rounded bg-os-elevated" />
              <div className="mt-3 shimmer-bg h-3 w-48 rounded bg-os-elevated" />
            </div>
          ))}
        </div>
      ) : error && keys.length === 0 ? null : keys.length === 0 ? (
        <div className="flex min-h-32 items-center justify-center rounded-2xl border border-os-border/50 bg-os-surface/40 p-4 backdrop-blur-md">
          <p className="text-sm text-os-subtle">暂无 API Key</p>
        </div>
      ) : (
        <div className="space-y-2">
          {keys.map((k) => {
            const revealed = revealedIds.has(k.api_key_id);
            return (
              <div
                key={k.api_key_id}
                className="group rounded-2xl border border-os-border/50 bg-os-surface/40 p-4 backdrop-blur-md transition-all duration-200 hover:border-os-accent/30"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    {/* Name + status */}
                    <div className="flex items-center gap-2">
                      <KeyRound size={14} className="shrink-0 text-os-accent" />
                      <span className="min-w-0 flex-1 break-words text-sm font-semibold text-os-text-high">{k.name}</span>
                      <StatusBadge status={k.status} />
                    </div>

                    {/* 任务 A: 毛玻璃模糊密钥前缀 */}
                    <div className="mt-2 flex items-center gap-2">
                      <code
                        className={cn(
                          "rounded-md border border-os-border bg-os-elevated px-2 py-1 font-mono text-2xs text-os-text-high transition-all duration-300",
                          !revealed && "blur-sm select-none",
                        )}
                      >
                        {k.key_prefix}••••••••••••••••••••
                      </code>
                      {k.status === "active" && (
                        <button
                          onClick={() => toggleReveal(k.api_key_id)}
                          className="inline-flex h-6 w-6 items-center justify-center rounded-md border border-os-border bg-os-surface text-os-subtle transition-colors hover:text-os-text-high"
                          title={revealed ? "隐藏" : "显示"}
                        >
                          {revealed ? <EyeOff size={11} /> : <Eye size={11} />}
                        </button>
                      )}
                      <button
                        onClick={() => void copyKeyPrefix(k.key_prefix)}
                        className="inline-flex h-6 w-6 items-center justify-center rounded-md border border-os-border bg-os-surface text-os-subtle transition-colors hover:text-os-text-high"
                        title="复制前缀"
                      >
                        <Copy size={11} />
                      </button>
                    </div>

                    {/* Scopes */}
                    <div className="mt-2 flex flex-wrap gap-1">
                      {k.scopes.map((s) => (
                        <span
                          key={s}
                          className="rounded bg-os-elevated px-1.5 py-0.5 text-2xs text-os-subtle"
                        >
                          {s}
                        </span>
                      ))}
                    </div>

                    {/* Meta — created / last used */}
                    <div className="mt-2 flex flex-wrap items-center gap-4 text-2xs text-os-subtle">
                      <span className="inline-flex items-center gap-1" title={k.created_at}>
                        <Calendar size={10} />
                        {formatRelativeTime(k.created_at)}
                      </span>
                      <span className="inline-flex items-center gap-1" title={k.last_used_at || ""}>
                        <Clock size={10} />
                        {formatRelativeTime(k.last_used_at)}
                      </span>
                    </div>
                  </div>

                  {/* Revoke action */}
                  {k.status === "active" && (
                    <button
                      onClick={() => handleRevoke(k.api_key_id)}
                      disabled={revoking.has(k.api_key_id)}
                        className="inline-flex h-8 shrink-0 items-center gap-1 rounded-lg border border-os-border px-2 text-xs text-os-subtle transition-colors hover:border-os-danger/30 hover:text-os-danger disabled:opacity-50"
                    >
                      {revoking.has(k.api_key_id) ? (
                        <Loader2 size={12} className="animate-spin" />
                      ) : (
                        <Trash2 size={12} />
                      )}
                      撤销
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ── 任务 C: Danger Zone ── */}
      <section className="mt-8 rounded-2xl border border-os-danger/40 bg-os-danger/5 p-6">
        <div className="mb-4 flex items-center gap-2">
          <AlertTriangle size={16} className="text-os-danger" />
          <h2 className="text-sm font-semibold text-os-danger">危险操作</h2>
        </div>
        <p className="mb-4 text-xs text-os-subtle">
          以下操作不可逆。执行前请确认你理解其后果。
        </p>

        <div className="flex flex-col items-start justify-between gap-4 rounded-lg border border-os-border/50 bg-os-surface/30 p-4 sm:flex-row sm:items-center">
          <div className="min-w-0">
            <h3 className="text-sm font-medium text-os-text-high">撤销全部活跃密钥</h3>
            <p className="mt-1 text-xs text-os-subtle">
              立即撤销当前所有 <span className="font-mono text-os-danger">{activeCount}</span> 个活跃 API Key。所有使用这些密钥的集成将立即停止工作。
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowRevokeAll(true)}
            disabled={activeCount === 0}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-os-danger px-3 text-xs font-medium text-os-danger transition-colors hover:bg-os-danger/10 disabled:cursor-not-allowed disabled:border-os-border disabled:text-os-subtle sm:shrink-0"
          >
            <Trash2 size={13} />
            撤销全部
          </button>
        </div>
      </section>

      {/* Create reveal modal */}
      {revealKey && <ApiKeyReveal rawKey={revealKey} onClose={() => setRevealKey(null)} />}

      {/* Danger confirm modal — Revoke All */}
      <DangerConfirmDialog
        open={showRevokeAll}
        title="撤销全部活跃密钥"
        description={`此操作将立即撤销 ${activeCount} 个活跃的 API Key。所有依赖这些密钥的第三方集成、脚本和服务将立即无法访问 知维 OS API。此操作不可撤销。`}
        confirmWord="REVOKE ALL"
        confirmWordLabel="请输入下方确认词以撤销全部密钥"
        actionLabel="撤销全部密钥"
        onConfirm={handleRevokeAll}
        onClose={() => !revokingAll && setShowRevokeAll(false)}
        loading={revokingAll}
      />
    </main>
  );
}
