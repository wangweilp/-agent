"use client";

import { useState } from "react";
import type { AgentSummary, AgentRunRequest, AgentRunResponse } from "@/types/agents";
import { runAgent } from "@/services/agents";

interface AgentRunDialogProps {
  agent: AgentSummary | null;
  open: boolean;
  onClose: () => void;
}

export function AgentRunDialog({ agent, open, onClose }: AgentRunDialogProps) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AgentRunResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!open || !agent) return null;

  const handleRun = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const req: AgentRunRequest = {
        agent_id: agent.agent_id,
        title: title || `测试 ${agent.name}`,
        description,
        priority: "medium",
      };
      const res = await runAgent(req);
      setResult(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "执行失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[85vh] overflow-y-auto p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold text-gray-900">测试运行: {agent.name}</h2>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100"
          >
            ✕
          </button>
        </div>

        {/* Input */}
        <div className="space-y-3 mb-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">任务标题</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={`测试 ${agent.name}`}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">任务描述</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="描述任务需求"
              rows={3}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none resize-none"
            />
          </div>
        </div>

        {/* Actions */}
        <div className="flex gap-2 mb-4">
          <button
            onClick={handleRun}
            disabled={loading}
            className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            {loading ? "执行中..." : "执行"}
          </button>
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200"
          >
            取消
          </button>
        </div>

        {/* Error */}
        {error && (
          <div className="p-3 rounded-lg bg-red-50 text-red-700 text-sm mb-4">{error}</div>
        )}

        {/* Result */}
        {result && (
          <div className="border border-gray-200 rounded-xl p-4 space-y-3">
            <div className="flex items-center gap-2">
              <span
                className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                  result.success
                    ? "bg-green-50 text-green-700"
                    : "bg-red-50 text-red-700"
                }`}
              >
                {result.success ? "成功" : "失败"}
              </span>
              <span className="text-sm text-gray-500">
                耗时 {result.duration_ms.toFixed(0)}ms
              </span>
              <span className="text-sm text-gray-500">
                工具 {result.tool_calls_count} | 记忆 {result.memory_calls_count} | KG {result.kg_calls_count}
              </span>
            </div>
            {result.error && (
              <p className="text-sm text-red-600">{result.error}</p>
            )}
            <div>
              <h4 className="text-sm font-medium text-gray-700 mb-1">输出</h4>
              <pre className="text-sm text-gray-800 whitespace-pre-wrap bg-gray-50 rounded-lg p-3 max-h-64 overflow-y-auto">
                {result.output || "(空)"}
              </pre>
            </div>
            {result.plan.length > 0 && (
              <div>
                <h4 className="text-sm font-medium text-gray-700 mb-1">执行计划</h4>
                <ol className="list-decimal list-inside text-sm text-gray-600">
                  {result.plan.map((step, i) => (
                    <li key={i}>{step}</li>
                  ))}
                </ol>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
