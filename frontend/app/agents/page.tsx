"use client";
/** Agent Marketplace — 内部 Agent 市场 */

import { useEffect, useState } from "react";
import { AgentCard } from "@/components/agents/AgentCard";
import { AgentRunDialog } from "@/components/agents/AgentRunDialog";
import { listAgents, enableAgent, disableAgent } from "@/services/agents";
import type { AgentSummary } from "@/types/agents";

export default function AgentMarketplacePage() {
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "enabled" | "disabled">("all");
  const [tagFilter, setTagFilter] = useState("");
  const [selectedAgent, setSelectedAgent] = useState<AgentSummary | null>(null);
  const [runDialogOpen, setRunDialogOpen] = useState(false);
  const [toggling, setToggling] = useState<Set<string>>(new Set());

  const fetchAgents = async () => {
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
  };

  useEffect(() => {
    fetchAgents();
  }, [filter, tagFilter]);

  const allTags = [...new Set(agents.flatMap((a) => a.tags))].sort();

  const filteredAgents = agents.filter((a) => {
    if (filter === "enabled") return a.enabled;
    if (filter === "disabled") return !a.enabled;
    return true;
  });

  const handleToggle = async (agentId: string, enable: boolean) => {
    setToggling((prev) => new Set(prev).add(agentId));
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

  const stats = {
    total: agents.length,
    enabled: agents.filter((a) => a.enabled).length,
    totalUsage: agents.reduce((s, a) => s + a.usage_count, 0),
    avgSuccessRate:
      agents.length > 0
        ? agents.reduce((s, a) => s + a.success_rate, 0) / agents.length
        : 0,
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Agent Marketplace</h1>
        <p className="text-gray-500 mt-1">企业内部 AI Agent 市场 — 让知识变成行动力</p>
      </div>

      {/* Stats Bar */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        {[
          { label: "Agent 总数", value: stats.total },
          { label: "已启用", value: stats.enabled },
          { label: "总调用", value: stats.totalUsage },
          { label: "平均成功率", value: `${(stats.avgSuccessRate * 100).toFixed(0)}%` },
        ].map((s) => (
          <div key={s.label} className="bg-white rounded-xl border border-gray-200 p-4 text-center">
            <div className="text-2xl font-bold text-gray-900">{s.value}</div>
            <div className="text-sm text-gray-500">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="flex gap-3 mb-6 flex-wrap">
        <div className="flex rounded-lg border border-gray-200 overflow-hidden">
          {(["all", "enabled", "disabled"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-4 py-2 text-sm font-medium transition-colors ${
                filter === f
                  ? "bg-indigo-600 text-white"
                  : "bg-white text-gray-600 hover:bg-gray-50"
              }`}
            >
              {f === "all" ? "全部" : f === "enabled" ? "已启用" : "已停用"}
            </button>
          ))}
        </div>

        <select
          value={tagFilter}
          onChange={(e) => setTagFilter(e.target.value)}
          className="px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white"
        >
          <option value="">所有标签</option>
          {allTags.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>

        <button
          onClick={fetchAgents}
          className="px-4 py-2 text-sm font-medium text-gray-600 bg-white border border-gray-200 rounded-lg hover:bg-gray-50"
        >
          刷新
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="p-4 rounded-lg bg-red-50 text-red-700 mb-6">{error}</div>
      )}

      {/* Loading */}
      {loading && (
        <div className="text-center py-12 text-gray-500">加载中...</div>
      )}

      {/* Agent Grid */}
      {!loading && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredAgents.map((agent) => (
            <AgentCard
              key={agent.agent_id}
              agent={agent}
              onRun={(id) => {
                const a = agents.find((x) => x.agent_id === id) || null;
                setSelectedAgent(a);
                setRunDialogOpen(true);
              }}
              onToggle={handleToggle}
            />
          ))}
        </div>
      )}

      {!loading && filteredAgents.length === 0 && (
        <div className="text-center py-12 text-gray-400">暂无 Agent</div>
      )}

      {/* Run Dialog */}
      <AgentRunDialog
        agent={selectedAgent}
        open={runDialogOpen}
        onClose={() => {
          setRunDialogOpen(false);
          fetchAgents();
        }}
      />
    </div>
  );
}
