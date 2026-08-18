"use client";
/** Execution History — 执行历史记录 */

import { useEffect, useState } from "react";
import { listExecutions, listWorkflows } from "@/services/agents";
import type { WorkflowExecution, Workflow } from "@/types/agents";

const STATUS_LABELS: Record<string, { label: string; className: string }> = {
  draft: { label: "草稿", className: "bg-gray-50 text-gray-600" },
  running: { label: "运行中", className: "bg-blue-50 text-blue-700" },
  paused: { label: "等待人工", className: "bg-amber-50 text-amber-700" },
  completed: { label: "已完成", className: "bg-green-50 text-green-700" },
  failed: { label: "失败", className: "bg-red-50 text-red-700" },
  cancelled: { label: "已取消", className: "bg-gray-50 text-gray-600" },
};

export default function ExecutionHistoryPage() {
  const [executions, setExecutions] = useState<WorkflowExecution[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterWfId, setFilterWfId] = useState("");
  const [selectedEx, setSelectedEx] = useState<WorkflowExecution | null>(null);

  const fetch = async () => {
    setLoading(true);
    try {
      const [exs, wfs] = await Promise.all([
        listExecutions(filterWfId || undefined),
        listWorkflows(),
      ]);
      setExecutions(exs.reverse());
      setWorkflows(wfs);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetch();
  }, [filterWfId]);

  const stats = {
    total: executions.length,
    completed: executions.filter((e) => e.status === "completed").length,
    failed: executions.filter((e) => e.status === "failed").length,
    avgDuration:
      executions.length > 0
        ? executions.reduce((s, e) => s + e.duration_ms, 0) / executions.length
        : 0,
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold text-gray-900 mb-1">执行历史</h1>
      <p className="text-gray-500 mb-8">工作流执行历史与追踪</p>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        {[
          { label: "总执行", value: stats.total },
          { label: "成功", value: stats.completed, color: "text-green-600" },
          { label: "失败", value: stats.failed, color: "text-red-600" },
          { label: "平均耗时", value: `${stats.avgDuration.toFixed(0)}ms` },
        ].map((s) => (
          <div key={s.label} className="bg-white rounded-xl border border-gray-200 p-4 text-center">
            <div className={`text-2xl font-bold ${s.color || "text-gray-900"}`}>{s.value}</div>
            <div className="text-sm text-gray-500">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="flex gap-3 mb-6">
        <select
          value={filterWfId}
          onChange={(e) => setFilterWfId(e.target.value)}
          className="px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white"
        >
          <option value="">所有工作流</option>
          {workflows.map((wf) => (
            <option key={wf.workflow_id} value={wf.workflow_id}>
              {wf.name}
            </option>
          ))}
        </select>
        <button
          onClick={fetch}
          className="px-4 py-2 text-sm font-medium text-gray-600 bg-white border border-gray-200 rounded-lg hover:bg-gray-50"
        >
          刷新
        </button>
      </div>

      {error && <div className="p-4 rounded-lg bg-red-50 text-red-700 mb-6">{error}</div>}

      {error ? null : loading ? (
        <div className="text-center py-12 text-gray-500">加载中...</div>
      ) : executions.length === 0 ? (
        <div className="text-center py-12 text-gray-600">暂无执行记录，请先执行工作流</div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50/50">
                <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  工作流
                </th>
                <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  状态
                </th>
                <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  节点完成
                </th>
                <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  耗时
                </th>
                <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  时间
                </th>
                <th className="px-5 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                  操作
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {executions.map((ex) => {
                const s = STATUS_LABELS[ex.status] || STATUS_LABELS.draft;
                const completedNodes = Object.values(ex.node_statuses).filter(
                  (s) => s === "completed"
                ).length;
                const totalNodes = Object.keys(ex.node_statuses).length;
                return (
                  <tr key={ex.execution_id} className="hover:bg-gray-50/50">
                    <td className="px-5 py-3">
                      <div className="text-sm font-medium text-gray-900">
                        {ex.workflow_name}
                      </div>
                      <div className="text-xs text-gray-400">{ex.execution_id.slice(0, 12)}...</div>
                    </td>
                    <td className="px-5 py-3">
                      <span
                        className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${s.className}`}
                      >
                        {s.label}
                      </span>
                      {ex.error && (
                        <div className="text-xs text-red-500 mt-1 max-w-[200px] truncate" title={ex.error}>
                          {ex.error}
                        </div>
                      )}
                    </td>
                    <td className="px-5 py-3 text-sm text-gray-600">
                      {totalNodes > 0 ? `${completedNodes}/${totalNodes}` : "-"}
                    </td>
                    <td className="px-5 py-3 text-sm text-gray-600">
                      {ex.duration_ms.toFixed(0)}ms
                    </td>
                    <td className="px-5 py-3 text-sm text-gray-500">
                      {ex.started_at ? new Date(ex.started_at).toLocaleString() : "-"}
                    </td>
                    <td className="px-5 py-3 text-right">
                      <button
                        onClick={() => setSelectedEx(ex)}
                        className="text-sm text-indigo-600 hover:text-indigo-800 font-medium"
                      >
                        详情
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          </div>
        </div>
      )}

      {/* Detail Modal */}
      {selectedEx && (
        <div className="fixed inset-0 bg-slate-950/20 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl shadow-os-lg w-full max-w-lg p-6 max-h-[80vh] overflow-y-auto">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-bold">执行详情</h2>
              <button
                onClick={() => setSelectedEx(null)}
                className="p-1 text-gray-400 hover:text-gray-600"
              >
                ✕
              </button>
            </div>
            <dl className="space-y-3 text-sm">
              <div className="flex items-start justify-between gap-4">
                <dt className="text-gray-500">执行 ID</dt>
                <dd className="min-w-0 break-all text-right font-mono text-gray-900">{selectedEx.execution_id}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">工作流</dt>
                <dd className="text-gray-900">{selectedEx.workflow_name}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">状态</dt>
                <dd>
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${(STATUS_LABELS[selectedEx.status] ?? STATUS_LABELS.draft).className}`}>
                    {STATUS_LABELS[selectedEx.status]?.label ?? selectedEx.status}
                  </span>
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">耗时</dt>
                <dd className="text-gray-900">{selectedEx.duration_ms.toFixed(0)}ms</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">开始时间</dt>
                <dd className="text-gray-900">
                  {selectedEx.started_at ? new Date(selectedEx.started_at).toLocaleString() : "-"}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">结束时间</dt>
                <dd className="text-gray-900">
                  {selectedEx.finished_at ? new Date(selectedEx.finished_at).toLocaleString() : "-"}
                </dd>
              </div>
            </dl>
            <div className="mt-4">
              <h3 className="text-sm font-medium text-gray-700 mb-2">节点状态</h3>
              <div className="space-y-2">
                {Object.entries(selectedEx.node_statuses).map(([nodeId, status]) => (
                  <div key={nodeId} className="flex justify-between text-sm border-b border-gray-100 pb-1">
                    <span className="text-gray-600 font-mono text-xs">{nodeId.slice(0, 12)}...</span>
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full ${
                        status === "completed"
                          ? "bg-green-50 text-green-700"
                          : status === "failed"
                          ? "bg-red-50 text-red-700"
                          : "bg-gray-50 text-gray-600"
                      }`}
                    >
                      {STATUS_LABELS[status]?.label ?? status}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
