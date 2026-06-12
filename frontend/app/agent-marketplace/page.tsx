"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  Bot,
  Building2,
  Filter,
  Layers,
  Loader2,
  RefreshCw,
  Search,
  Shield,
  ShoppingBag,
  Sparkles,
  Tag,
} from "lucide-react";

import { MarketplaceAgentCard } from "@/components/agents/MarketplaceAgentCard";
import {
  installMarketplaceAgent,
  listMarketplaceAgents,
  getMarketplaceAnalyticsSummary,
  type MarketplaceApiError,
} from "@/services/marketplace";
import type { MarketplaceAgent, MarketplaceAnalyticsSummary } from "@/types/marketplace";

type InstalledFilter = "all" | "installed" | "not_installed";

const STATUS_BADGES = [
  { label: "Internal Marketplace", hint: "企业内部 Agent 分发中心" },
  { label: "Auth / RBAC Protected", hint: "租户级访问控制" },
  { label: "Tenant Installed", hint: "按工作区安装隔离" },
  { label: "Usage Metered", hint: "用量自动记录" },
];

function LoadingGrid() {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="os-card h-[280px] overflow-hidden p-4">
          <div className="shimmer-bg h-5 w-36 rounded bg-os-elevated" />
          <div className="mt-4 space-y-2">
            <div className="shimmer-bg h-3 w-full rounded bg-os-elevated" />
            <div className="shimmer-bg h-3 w-5/6 rounded bg-os-elevated" />
          </div>
          <div className="mt-4 flex gap-1.5">
            <div className="shimmer-bg h-5 w-14 rounded bg-os-elevated" />
            <div className="shimmer-bg h-5 w-12 rounded bg-os-elevated" />
          </div>
          <div className="mt-3 grid grid-cols-3 gap-2">
            <div className="shimmer-bg h-12 rounded bg-os-elevated" />
            <div className="shimmer-bg h-12 rounded bg-os-elevated" />
            <div className="shimmer-bg h-12 rounded bg-os-elevated" />
          </div>
          <div className="mt-auto flex gap-2 pt-4">
            <div className="shimmer-bg h-9 flex-1 rounded bg-os-elevated" />
            <div className="shimmer-bg h-9 flex-1 rounded bg-os-elevated" />
          </div>
        </div>
      ))}
    </div>
  );
}

export default function MarketplaceHomePage() {
  const router = useRouter();
  const [agents, setAgents] = useState<MarketplaceAgent[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [departments, setDepartments] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [category, setCategory] = useState("");
  const [department, setDepartment] = useState("");
  const [status, setStatus] = useState("");
  const [installedFilter, setInstalledFilter] = useState<InstalledFilter>("all");
  const [query, setQuery] = useState("");

  // Install state
  const [installing, setInstalling] = useState<Set<string>>(new Set());
  const [installedIds, setInstalledIds] = useState<Set<string>>(new Set());

  // Analytics
  const [analytics, setAnalytics] = useState<MarketplaceAnalyticsSummary | null>(null);

  const fetchAgents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const installedParam = installedFilter === "installed"
        ? true
        : installedFilter === "not_installed"
          ? false
          : undefined;

      const res = await listMarketplaceAgents({
        category: category || undefined,
        department: department || undefined,
        status: status || undefined,
        installed: installedParam,
      });
      setAgents(res.agents);
      setCategories(res.categories);
      setDepartments(res.departments);

      // Build installedIds from the enriched response (backend now includes is_installed)
      const ids = new Set<string>();
      for (const a of res.agents) {
        if (a.is_installed) ids.add(a.marketplace_agent_id);
      }
      setInstalledIds(ids);
    } catch (e: unknown) {
      const apiErr = e as MarketplaceApiError;
      setError(`[${apiErr.status || "ERR"}] ${apiErr.message || "加载失败"}`);
    } finally {
      setLoading(false);
    }
  }, [category, department, status, installedFilter]);

  useEffect(() => {
    void fetchAgents();
  }, [fetchAgents]);

  // Fetch analytics summary (best-effort, doesn't block main content)
  useEffect(() => {
    let cancelled = false;
    async function fetchAnalytics() {
      try {
        const data = await getMarketplaceAnalyticsSummary();
        if (!cancelled) setAnalytics(data);
      } catch {
        // Analytics are best-effort — don't block the page
      }
    }
    void fetchAnalytics();
    return () => { cancelled = true; };
  }, []);

  const handleInstall = async (marketplaceAgentId: string) => {
    setInstalling((prev) => new Set(prev).add(marketplaceAgentId));
    setError(null);
    try {
      await installMarketplaceAgent(marketplaceAgentId, {});
      setInstalledIds((prev) => new Set(prev).add(marketplaceAgentId));
    } catch (e: unknown) {
      const apiErr = e as MarketplaceApiError;
      if (apiErr.status === 409) {
        setInstalledIds((prev) => new Set(prev).add(marketplaceAgentId));
      } else {
        setError(`[${apiErr.status || "ERR"}] ${apiErr.message || "安装失败"}`);
      }
    } finally {
      setInstalling((prev) => {
        const next = new Set(prev);
        next.delete(marketplaceAgentId);
        return next;
      });
    }
  };

  const filteredAgents = useMemo(() => {
    if (!query.trim()) return agents;
    const q = query.trim().toLowerCase();
    return agents.filter(
      (a) =>
        a.display_name.toLowerCase().includes(q) ||
        a.name.toLowerCase().includes(q) ||
        a.description.toLowerCase().includes(q) ||
        a.capabilities.some((c) => c.toLowerCase().includes(q)),
    );
  }, [agents, query]);

  const stats = useMemo(() => {
    const total = agents.length;
    const withDept = agents.filter((a) => a.department).length;
    const freeCount = agents.filter((a) => a.pricing_model === "free").length;
    return { total, withDept, freeCount };
  }, [agents]);

  return (
    <main className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6">
      {/* Hero */}
      <header className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-os-border bg-os-surface px-3 py-1 text-xs text-os-subtle">
            <ShoppingBag size={14} className="text-os-accent" />
            企业内部 Agent 发现与安装中心
          </div>
          <h1 className="text-3xl font-semibold tracking-normal text-os-text-high">
            Agent Marketplace
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-os-subtle">
            发现、安装、配置和治理企业内部 Agent，让组织智能体从可运行走向可分发。
            <span className="mx-2 text-os-muted">|</span>
            <Link href="/agents" className="text-os-accent hover:underline">
              /agents
            </Link>
            {" "}用于执行 Agent，{" "}
            <span className="text-os-accent">/agent-marketplace</span>
            {" "}用于发现与安装 Agent。
          </p>

          {/* Status badges */}
          <div className="mt-4 flex flex-wrap gap-2">
            {STATUS_BADGES.map((b) => (
              <span
                key={b.label}
                className="inline-flex items-center gap-1.5 rounded-full border border-os-border/60 bg-os-elevated px-2.5 py-1 text-2xs text-os-subtle"
                title={b.hint}
              >
                {b.label}
              </span>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Link
            href="/agent-marketplace/installations"
            className="inline-flex h-9 items-center gap-2 rounded-md border border-os-border bg-os-surface px-3 text-xs font-medium text-os-subtle transition-colors hover:text-os-text-high"
          >
            <Layers size={14} />
            已安装
          </Link>
          <button
            type="button"
            onClick={() => void fetchAgents()}
            disabled={loading}
            className="inline-flex h-9 items-center justify-center gap-2 rounded-md border border-os-border bg-os-surface px-3 text-xs font-medium text-os-subtle transition-colors hover:text-os-text-high disabled:cursor-not-allowed disabled:opacity-60"
          >
            {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            刷新
          </button>
        </div>
      </header>

      {/* Stats */}
      <section className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="os-card p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs text-os-muted">可安装 Agent</p>
              <p className="mt-2 text-2xl font-semibold text-os-text-high">{stats.total}</p>
            </div>
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-os-elevated text-os-accent">
              <Bot size={18} />
            </div>
          </div>
          <p className="mt-3 text-xs text-os-subtle">内置 + 平台已审核 Agent</p>
        </div>
        <div className="os-card p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs text-os-muted">免费 Agent</p>
              <p className="mt-2 text-2xl font-semibold text-os-text-high">{stats.freeCount}</p>
            </div>
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-os-elevated text-emerald-400">
              <Sparkles size={18} />
            </div>
          </div>
          <p className="mt-3 text-xs text-os-subtle">零成本即可使用，无需付费</p>
        </div>
        <div className="os-card p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs text-os-muted">部门 Agent</p>
              <p className="mt-2 text-2xl font-semibold text-os-text-high">{stats.withDept}</p>
            </div>
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-os-elevated text-violet-400">
              <Building2 size={18} />
            </div>
          </div>
          <p className="mt-3 text-xs text-os-subtle">按部门定制的专属 Agent</p>
        </div>
      </section>

      {/* Analytics Summary */}
      {analytics && (
        <section className="mb-6 os-card p-4">
          <h3 className="mb-3 text-xs font-semibold text-os-subtle">
            Marketplace 使用概况
          </h3>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
            <div className="rounded-md bg-os-elevated/30 px-3 py-2 text-center">
              <p className="text-2xs text-os-muted">Agent 总数</p>
              <p className="mt-0.5 text-sm font-semibold text-os-text-high">
                {analytics.total_marketplace_agents}
              </p>
            </div>
            <div className="rounded-md bg-os-elevated/30 px-3 py-2 text-center">
              <p className="text-2xs text-os-muted">已安装</p>
              <p className="mt-0.5 text-sm font-semibold text-os-accent">
                {analytics.installed_agents}
              </p>
            </div>
            <div className="rounded-md bg-os-elevated/30 px-3 py-2 text-center">
              <p className="text-2xs text-os-muted">已启用</p>
              <p className="mt-0.5 text-sm font-semibold text-emerald-300">
                {analytics.enabled_installations}
              </p>
            </div>
            <div className="rounded-md bg-os-elevated/30 px-3 py-2 text-center">
              <p className="text-2xs text-os-muted">已停用</p>
              <p className="mt-0.5 text-sm font-semibold text-os-subtle">
                {analytics.disabled_installations}
              </p>
            </div>
            <div className="rounded-md bg-os-elevated/30 px-3 py-2 text-center">
              <p className="text-2xs text-os-muted">安装事件</p>
              <p className="mt-0.5 text-sm font-semibold text-os-text-high">
                {analytics.install_events}
              </p>
            </div>
            <div className="rounded-md bg-os-elevated/30 px-3 py-2 text-center">
              <p className="text-2xs text-os-muted">Agent 执行</p>
              <p className="mt-0.5 text-sm font-semibold text-os-text-high">
                {analytics.agent_runs}
              </p>
            </div>
          </div>
          <p className="mt-3 text-2xs text-os-muted">
            {analytics.billing_note}
          </p>
        </section>
      )}

      {/* Filter bar */}
      <section className="os-card mb-6 p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-1 flex-col gap-3 sm:flex-row sm:items-center">
            <label className="relative block flex-1">
              <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-os-muted" />
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="搜索名称、描述或能力"
                className="h-10 w-full rounded-md border border-os-border bg-os-elevated pl-9 pr-3 text-sm text-os-text-high outline-none transition-colors placeholder:text-os-muted focus:border-os-accent"
              />
            </label>

            <label className="relative block sm:w-44">
              <Tag size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-os-muted" />
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="h-10 w-full appearance-none rounded-md border border-os-border bg-os-elevated pl-9 pr-8 text-sm text-os-text-high outline-none transition-colors focus:border-os-accent"
              >
                <option value="">所有分类</option>
                {categories.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </label>

            <label className="relative block sm:w-44">
              <Building2 size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-os-muted" />
              <select
                value={department}
                onChange={(e) => setDepartment(e.target.value)}
                className="h-10 w-full appearance-none rounded-md border border-os-border bg-os-elevated pl-9 pr-8 text-sm text-os-text-high outline-none transition-colors focus:border-os-accent"
              >
                <option value="">所有部门</option>
                {departments.map((d) => (
                  <option key={d} value={d}>{d}</option>
                ))}
              </select>
            </label>

            <label className="relative block sm:w-36">
              <Shield size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-os-muted" />
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value)}
                className="h-10 w-full appearance-none rounded-md border border-os-border bg-os-elevated pl-9 pr-8 text-sm text-os-text-high outline-none transition-colors focus:border-os-accent"
              >
                <option value="">所有状态</option>
                <option value="active">Active</option>
                <option value="beta">Beta</option>
                <option value="deprecated">Deprecated</option>
              </select>
            </label>
          </div>

          <div className="inline-flex h-10 overflow-hidden rounded-md border border-os-border bg-os-elevated">
            {([
              { value: "all", label: "全部" },
              { value: "installed", label: "已安装" },
              { value: "not_installed", label: "未安装" },
            ] as const).map((item) => (
              <button
                key={item.value}
                type="button"
                onClick={() => setInstalledFilter(item.value)}
                className={`inline-flex min-w-20 items-center justify-center gap-1.5 px-3 text-xs font-medium transition-colors ${
                  installedFilter === item.value
                    ? "bg-os-accent text-white"
                    : "text-os-subtle hover:bg-os-surface hover:text-os-text-high"
                }`}
              >
                <Filter size={13} />
                {item.label}
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* Error */}
      {error && (
        <div className="mb-6 rounded-md border border-red-400/20 bg-red-400/10 p-4 text-sm leading-6 text-red-200">
          {error}
          <button
            type="button"
            onClick={() => void fetchAgents()}
            className="ml-3 text-xs text-red-300 underline hover:text-red-200"
          >
            重试
          </button>
        </div>
      )}

      {/* Content */}
      {loading ? (
        <LoadingGrid />
      ) : filteredAgents.length > 0 ? (
        <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {filteredAgents.map((agent) => (
            <MarketplaceAgentCard
              key={agent.marketplace_agent_id}
              agent={agent}
              installed={installedIds.has(agent.marketplace_agent_id)}
              busy={installing.has(agent.marketplace_agent_id)}
              onInstall={handleInstall}
              onDetail={(id) => router.push(`/agent-marketplace/${id}`)}
            />
          ))}
        </section>
      ) : (
        <section className="os-card flex min-h-56 flex-col items-center justify-center px-4 py-10 text-center">
          <ShoppingBag size={28} className="text-os-muted" />
          <h2 className="mt-3 text-base font-semibold text-os-text-high">没有匹配的 Agent</h2>
          <p className="mt-1 max-w-md text-sm leading-6 text-os-subtle">
            调整筛选条件或搜索词后再试。分类和部门过滤是精确匹配。
          </p>
          {error && (
            <p className="mt-2 text-xs text-red-300">{error}</p>
          )}
        </section>
      )}
    </main>
  );
}
