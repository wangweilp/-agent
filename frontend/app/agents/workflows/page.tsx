"use client";
/** Workflow Builder — 工作流管理 */

import { useEffect, useState } from "react";
import { listWorkflows, executeWorkflow, createWorkflow } from "@/services/agents";
import type { Workflow, WorkflowNode } from "@/types/agents";

export default function WorkflowBuilderPage() {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [executing, setExecuting] = useState<string | null>(null);
  const [selectedWf, setSelectedWf] = useState<Workflow | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const fetchWorkflows = async () => {
    setLoading(true);
    try {
      setWorkflows(await listWorkflows());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchWorkflows();
  }, []);

  const handleExecute = async (wfId: string) => {
    setExecuting(wfId);
    try {
      const result = await executeWorkflow(wfId);
      alert(
        `工作流执行${result.status === "completed" ? "成功" : "失败"}: ${result.status}\n耗时: ${result.duration_ms.toFixed(0)}ms`
      );
      fetchWorkflows();
    } catch (e: unknown) {
      alert(`执行失败: ${e instanceof Error ? e.message : "未知错误"}`);
    } finally {
      setExecuting(null);
    }
  };

  // 创建一个快速测试工作流
  const handleCreateQuick = async () => {
    try {
      await createWorkflow({
        name: `测试工作流 ${new Date().toLocaleTimeString()}`,
        description: "快速创建的测试工作流",
        nodes: [
          {
            node_id: "start",
            name: "开始",
            node_type: "start",
            agent_id: "",
            description: "",
            next_nodes: ["knowledge"],
            human_prompt: "",
            status: "",
            started_at: null,
            finished_at: null,
          },
          {
            node_id: "knowledge",
            name: "知识搜索",
            node_type: "agent",
            agent_id: "builtin-knowledge",
            description: "搜索相关知识",
            next_nodes: ["end"],
            human_prompt: "",
            status: "",
            started_at: null,
            finished_at: null,
          },
          {
            node_id: "end",
            name: "结束",
            node_type: "end",
            agent_id: "",
            description: "",
            next_nodes: [],
            human_prompt: "",
            status: "",
            started_at: null,
            finished_at: null,
          },
        ],
        start_node_id: "start",
        tags: ["test"],
      });
      await fetchWorkflows();
      setShowCreate(false);
    } catch (e: unknown) {
      alert(`创建失败: ${e instanceof Error ? e.message : "未知错误"}`);
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Workflow Builder</h1>
          <p className="text-gray-500 mt-1">Agent 工作流编排</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700"
        >
          + 新建工作流
        </button>
      </div>

      {error && <div className="p-4 rounded-lg bg-red-50 text-red-700 mb-6">{error}</div>}

      {showCreate && (
        <div className="mb-6 p-4 rounded-xl border border-indigo-200 bg-indigo-50">
          <p className="text-sm text-indigo-800 mb-2">快速创建测试工作流（知识搜索）</p>
          <div className="flex gap-2">
            <button
              onClick={handleCreateQuick}
              className="px-3 py-1.5 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700"
            >
              创建并测试
            </button>
            <button
              onClick={() => setShowCreate(false)}
              className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-900"
            >
              取消
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="text-center py-12 text-gray-500">加载中...</div>
      ) : workflows.length === 0 ? (
        <div className="text-center py-12 text-gray-400">暂无工作流，点击上方按钮创建</div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {workflows.map((wf) => (
            <div
              key={wf.workflow_id}
              className="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-md transition-shadow"
            >
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className="font-semibold text-gray-900">{wf.name}</h3>
                  <p className="text-sm text-gray-500">{wf.description || "无描述"}</p>
                </div>
                <span className="text-xs text-gray-400">v{wf.version}</span>
              </div>

              {/* Flow Visualization */}
              <div className="flex items-center gap-2 mb-4 overflow-x-auto py-2">
                {wf.nodes.map((node: WorkflowNode, idx: number) => (
                  <div key={node.node_id} className="flex items-center gap-2">
                    {idx > 0 && <span className="text-gray-300">→</span>}
                    <div
                      className={`px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap ${
                        node.node_type === "agent"
                          ? "bg-blue-50 text-blue-700 border border-blue-200"
                          : node.node_type === "human"
                          ? "bg-amber-50 text-amber-700 border border-amber-200"
                          : node.node_type === "start" || node.node_type === "end"
                          ? "bg-gray-50 text-gray-500 border border-gray-200"
                          : "bg-purple-50 text-purple-700 border border-purple-200"
                      }`}
                    >
                      {node.node_type === "agent" ? `🤖 ${node.name}` : node.name}
                    </div>
                  </div>
                ))}
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => setSelectedWf(wf)}
                  className="px-3 py-1.5 text-xs font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200"
                >
                  查看详情
                </button>
                <button
                  onClick={() => handleExecute(wf.workflow_id)}
                  disabled={executing === wf.workflow_id}
                  className="px-3 py-1.5 text-xs font-medium text-white bg-green-600 rounded-lg hover:bg-green-700 disabled:opacity-50"
                >
                  {executing === wf.workflow_id ? "执行中..." : "执行"}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Detail Modal */}
      {selectedWf && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg p-6 max-h-[80vh] overflow-y-auto">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-bold">{selectedWf.name}</h2>
              <button
                onClick={() => setSelectedWf(null)}
                className="p-1 text-gray-400 hover:text-gray-600"
              >
                ✕
              </button>
            </div>
            <p className="text-sm text-gray-500 mb-4">{selectedWf.description}</p>
            <div className="space-y-3">
              {selectedWf.nodes.map((n: WorkflowNode) => (
                <div key={n.node_id} className="border border-gray-200 rounded-lg p-3">
                  <div className="flex justify-between">
                    <span className="font-medium text-sm">{n.name}</span>
                    <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded">
                      {n.node_type}
                    </span>
                  </div>
                  {n.agent_id && (
                    <div className="text-xs text-gray-500 mt-1">Agent: {n.agent_id}</div>
                  )}
                  {n.next_nodes.length > 0 && (
                    <div className="text-xs text-gray-500 mt-1">
                      → {n.next_nodes.join(", ")}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
