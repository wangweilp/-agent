"use client";
/** Agent Dashboard — Agent 运行数据看板 */

import { useEffect, useState } from "react";
import { getAgentStats, listExecutions } from "@/services/agents";
import type { AgentStats, WorkflowExecution } from "@/types/agents";

export default function AgentDashboardPage() {
  const [stats, setStats] = useState<AgentStats | null>(null);
  const [executions, setExecutions] = useState<WorkflowExecution[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetch = async () => {
      setLoading(true);
      try {
        const [s, e] = await Promise.all([getAgentStats(), listExecutions()]);
        setStats(s);
        setExecutions(e);
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "加载失败");
      } finally {
        setLoading(false);
      }
    };
    fetch();
  }, []);

  if (loading) return <div className="text-center py-12 text-gray-500">加载中...</div>;
  if (error) return <div className="p-4 rounded-lg bg-red-50 text-red-700">{error}</div>;
  if (!stats) return null;

  const recentExecs = executions.slice(-10).reverse();

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold text-gray-900 mb-1">Agent Dashboard</h1>
      <p className="text-gray-500 mb-8">Agent 运行状况全景</p>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {[
          { label: "Agent 总数", value: stats.total_agents, color: "text-indigo-600" },
          { label: "已启用", value: stats.enabled_agents, color: "text-green-600" },
          { label: "总调用次数", value: stats.total_usage, color: "text-blue-600" },
          {
            label: "总成功率",
            value: stats.total_usage > 0
              ? `${((stats.total_success / stats.total_usage) * 100).toFixed(0)}%`
              : "-",
            color: "text-emerald-600",
          },
        ].map((kpi) => (
          <div key={kpi.label} className="bg-white rounded-xl border border-gray-200 p-5">
            <div className={`text-3xl font-bold ${kpi.color}`}>{kpi.value}</div>
            <div className="text-sm text-gray-500 mt-1">{kpi.label}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Agent 列表 */}
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-100">
            <h2 className="font-semibold text-gray-900">Agent 列表</h2>
          </div>
          <div className="divide-y divide-gray-100">
            {stats.agents.map((a) => (
              <div key={a.agent_id} className="px-5 py-3 flex items-center justify-between">
                <div>
                  <div className="font-medium text-gray-900 text-sm">{a.name}</div>
                  <div className="text-xs text-gray-500">{a.agent_id}</div>
                </div>
                <div className="flex items-center gap-4 text-sm">
                  <span className="text-gray-600">{a.usage_count} 次</span>
                  <span className="text-green-600">{(a.success_rate * 100).toFixed(0)}%</span>
                  <span className="text-gray-400">
                    {a.avg_duration_ms > 0 ? `${a.avg_duration_ms.toFixed(0)}ms` : "-"}
                  </span>
                  <span
                    className={`px-2 py-0.5 rounded-full text-xs ${
                      a.enabled
                        ? "bg-green-50 text-green-700"
                        : "bg-gray-50 text-gray-500"
                    }`}
                  >
                    {a.enabled ? "启用" : "停用"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 最近执行 */}
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-100">
            <h2 className="font-semibold text-gray-900">最近执行</h2>
          </div>
          <div className="divide-y divide-gray-100">
            {recentExecs.length === 0 ? (
              <div className="px-5 py-8 text-center text-gray-400">暂无执行记录</div>
            ) : (
              recentExecs.map((ex) => (
                <div key={ex.execution_id} className="px-5 py-3">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-medium text-gray-900">
                      {ex.workflow_name}
                    </span>
                    <span
                      className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                        ex.status === "completed"
                          ? "bg-green-50 text-green-700"
                          : ex.status === "failed"
                          ? "bg-red-50 text-red-700"
                          : ex.status === "running"
                          ? "bg-blue-50 text-blue-700"
                          : "bg-gray-50 text-gray-600"
                      }`}
                    >
                      {ex.status}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-gray-500">
                    <span>{ex.execution_id.slice(0, 8)}...</span>
                    <span>{ex.duration_ms.toFixed(0)}ms</span>
                    {ex.started_at && (
                      <span>{new Date(ex.started_at).toLocaleString()}</span>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
