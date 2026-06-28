"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Activity,
  Bot,
  Filter,
  Loader2,
  RefreshCw,
  Search,
  ShieldCheck,
  Tags,
  TrendingUp,
} from "lucide-react";

import { AgentCard } from "@/components/agents/AgentCard";
import { AgentRunDialog } from "@/components/agents/AgentRunDialog";
import { disableAgent, enableAgent, listAgents } from "@/services/agents";
import type { AgentSummary } from "@/types/agents";

type AgentFilter = "all" | "enabled" | "disabled";

const FILTERS: Array<{ value: AgentFilter; label: string }> = [
  { value: "all", label: "全部" },
  { value: "enabled", label: "已启用" },
  { value: "disabled", label: "已停用" },
];

function StatCard({
  icon: Icon,
  label,
  value,
  hint,
}: {
  icon: typeof Bot;
  label: string;
  value: string | number;
  hint: string;
}) {
  return (
    <div className="os-card p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs text-os-muted">{label}</p>
          <p className="mt-2 text-2xl font-semibold text-os-text-high">{value}</p>
        </div>
        <div className="flex h-10 w-10 items-center justify-center rounded-md bg-os-elevated text-os-accent">
          <Icon size={18} />
        </div>
      </div>
      <p className="mt-3 text-xs text-os-subtle">{hint}</p>
    </div>
  );
}

function LoadingGrid() {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: 6 }).map((_, index) => (
        <div key={index} className="os-card h-56 overflow-hidden p-5">
          <div className="shimmer-bg h-5 w-36 rounded bg-os-elevated" />
          <div className="mt-4 space-y-2">
            <div className="shimmer-bg h-3 w-full rounded bg-os-elevated" />
            <div className="shimmer-bg h-3 w-5/6 rounded bg-os-elevated" />
            <div className="shimmer-bg h-3 w-3/5 rounded bg-os-elevated" />
          </div>
          <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-2">
            <div className="shimmer-bg h-14 rounded bg-os-elevated" />
            <div className="shimmer-bg h-14 rounded bg-os-elevated" />
            <div className="shimmer-bg h-14 rounded bg-os-elevated" />
          </div>
        </div>
      ))}
    </div>
  );
}

export default function InternalAgentCenterPage() {
  const router = useRouter();
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<AgentFilter>("all");
  const [tagFilter, setTagFilter] = useState("");
  const [query, setQuery] = useState("");
  const [selectedAgent, setSelectedAgent] = useState<AgentSummary | null>(null);
  const [runDialogOpen, setRunDialogOpen] = useState(false);
  const [toggling, setToggling] = useState<Set<string>>(new Set());

  const fetchAgents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listAgents(tagFilter || undefined, filter === "enabled");
      setAgents(res.agents);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [filter, tagFilter]);

  useEffect(() => {
    void fetchAgents();
  }, [fetchAgents]);

  const allTags = useMemo(
    () => [...new Set(agents.flatMap((agent) => agent.tags))].sort(),
    [agents],
  );

  const filteredAgents = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();

    return agents.filter((agent) => {
      if (filter === "enabled" && !agent.enabled) return false;
      if (filter === "disabled" && agent.enabled) return false;

      if (!normalizedQuery) return true;
      const haystack = [agent.name, agent.description, agent.agent_id, ...agent.tags]
        .join(" ")
        .toLowerCase();
      return haystack.includes(normalizedQuery);
    });
  }, [agents, filter, query]);

  const stats = useMemo(() => {
    const enabled = agents.filter((agent) => agent.enabled).length;
    const totalUsage = agents.reduce((sum, agent) => sum + agent.usage_count, 0);
    const avgSuccessRate =
      agents.length > 0
        ? agents.reduce((sum, agent) => sum + agent.success_rate, 0) / agents.length
        : 0;

    return {
      total: agents.length,
      enabled,
      disabled: agents.length - enabled,
      totalUsage,
      avgSuccessRate,
    };
  }, [agents]);

  const handleToggle = async (agentId: string, enable: boolean) => {
    setToggling((prev) => new Set(prev).add(agentId));
    setError(null);

    try {
      if (enable) await enableAgent(agentId);
      else await disableAgent(agentId);
      await fetchAgents();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "操作失败");
    } finally {
      setToggling((prev) => {
        const next = new Set(prev);
        next.delete(agentId);
        return next;
      });
    }
  };

  const openRunDialog = (agentId: string) => {
    const agent = agents.find((item) => item.agent_id === agentId) || null;
    setSelectedAgent(agent);
    setRunDialogOpen(Boolean(agent));
  };

  return (
    <main className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6">
      <header className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-os-border bg-os-surface px-3 py-1 text-xs text-os-subtle">
            <Bot size={14} className="text-os-accent" />
            企业内部 Agent 能力目录
          </div>
          <h1 className="text-3xl font-semibold tracking-normal text-os-text-high">内部智能体中心</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-os-subtle">
            企业内部 Agent 管理中心。以卡片方式浏览、筛选和执行 Agent，所有数据通过后端 Agent API 获取。
          </p>
        </div>

        <button
          type="button"
          onClick={() => void fetchAgents()}
          disabled={loading}
          className="inline-flex h-9 items-center justify-center gap-2 rounded-md border border-os-border bg-os-surface px-3 text-xs font-medium text-os-subtle transition-colors hover:text-os-text-high disabled:cursor-not-allowed disabled:opacity-60"
        >
          {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          刷新
        </button>
      </header>

      <section className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard icon={Bot} label="智能体总数" value={stats.total} hint="当前可被编排或试运行的能力" />
        <StatCard
          icon={ShieldCheck}
          label="已启用"
          value={stats.enabled}
          hint={`${stats.disabled} 个处于停用状态`}
        />
        <StatCard icon={Activity} label="总调用" value={stats.totalUsage} hint="来自后端统计的累计调用量" />
        <StatCard
          icon={TrendingUp}
          label="平均成功率"
          value={`${(stats.avgSuccessRate * 100).toFixed(0)}%`}
          hint="按当前列表智能体计算"
        />
      </section>

      <section className="os-card mb-6 p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-1 flex-col gap-3 sm:flex-row sm:items-center">
            <label className="relative block flex-1">
              <Search
                size={15}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-os-muted"
              />
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜索名称、描述、标签或 ID"
                className="h-10 w-full rounded-md border border-os-border bg-os-elevated pl-9 pr-3 text-sm text-os-text-high outline-none transition-colors placeholder:text-os-muted focus:border-os-accent"
              />
            </label>

            <label className="relative block sm:w-56">
              <Tags
                size={15}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-os-muted"
              />
              <select
                value={tagFilter}
                onChange={(event) => setTagFilter(event.target.value)}
                className="h-10 w-full appearance-none rounded-md border border-os-border bg-os-elevated pl-9 pr-8 text-sm text-os-text-high outline-none transition-colors focus:border-os-accent"
              >
                <option value="">所有标签</option>
                {allTags.map((tag) => (
                  <option key={tag} value={tag}>
                    {tag}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="inline-flex h-10 overflow-hidden rounded-md border border-os-border bg-os-elevated">
            {FILTERS.map((item) => (
              <button
                key={item.value}
                type="button"
                onClick={() => setFilter(item.value)}
                className={`inline-flex min-w-20 items-center justify-center gap-1.5 px-3 text-xs font-medium transition-colors ${
                  filter === item.value
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

      {error && (
        <div className="mb-6 rounded-md border border-red-400/20 bg-red-400/10 p-4 text-sm leading-6 text-red-200">
          {error}
        </div>
      )}

      {loading ? (
        <LoadingGrid />
      ) : filteredAgents.length > 0 ? (
        <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {filteredAgents.map((agent) => (
            <AgentCard
              key={agent.agent_id}
              agent={agent}
              busy={toggling.has(agent.agent_id)}
              onRun={openRunDialog}
              onToggle={handleToggle}
              onClick={(id) => router.push(`/agents/${id}`)}
            />
          ))}
        </section>
      ) : (
        <section className="os-card flex min-h-56 flex-col items-center justify-center px-4 py-10 text-center">
          <Bot size={28} className="text-os-muted" />
          <h2 className="mt-3 text-base font-semibold text-os-text-high">没有匹配的智能体</h2>
          <p className="mt-1 max-w-md text-sm leading-6 text-os-subtle">
            调整搜索词、状态或标签筛选后再试。
          </p>
        </section>
      )}

      <AgentRunDialog
        agent={selectedAgent}
        open={runDialogOpen}
        onClose={() => {
          setRunDialogOpen(false);
          void fetchAgents();
        }}
      />
    </main>
  );
}
