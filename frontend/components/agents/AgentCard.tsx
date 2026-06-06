"use client";

import type { AgentSummary } from "@/types/agents";

interface AgentCardProps {
  agent: AgentSummary;
  onRun?: (agentId: string) => void;
  onToggle?: (agentId: string, enabled: boolean) => void;
  onClick?: (agentId: string) => void;
}

export function AgentCard({ agent, onRun, onToggle, onClick }: AgentCardProps) {
  return (
    <div
      className="group rounded-xl border border-gray-200 bg-white p-5 shadow-sm transition-all hover:shadow-md hover:border-indigo-200 cursor-pointer"
      onClick={() => onClick?.(agent.agent_id)}
    >
      <div className="flex items-start justify-between mb-3">
        <div>
          <h3 className="font-semibold text-gray-900 text-lg">{agent.name}</h3>
          <p className="text-sm text-gray-500 mt-0.5">{agent.description}</p>
        </div>
        <span
          className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
            agent.enabled
              ? "bg-green-50 text-green-700 ring-1 ring-green-600/20"
              : "bg-gray-50 text-gray-500 ring-1 ring-gray-500/20"
          }`}
        >
          {agent.enabled ? "启用" : "停用"}
        </span>
      </div>

      <div className="flex flex-wrap gap-1.5 mb-4">
        {agent.tags.map((tag) => (
          <span
            key={tag}
            className="inline-flex items-center px-2 py-0.5 rounded text-xs bg-indigo-50 text-indigo-600"
          >
            {tag}
          </span>
        ))}
        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs bg-gray-100 text-gray-500">
          v{agent.version}
        </span>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-3 gap-3 pt-3 border-t border-gray-100">
        <div className="text-center">
          <div className="text-lg font-bold text-gray-900">{agent.usage_count}</div>
          <div className="text-xs text-gray-500">调用次数</div>
        </div>
        <div className="text-center">
          <div className="text-lg font-bold text-green-600">
            {(agent.success_rate * 100).toFixed(0)}%
          </div>
          <div className="text-xs text-gray-500">成功率</div>
        </div>
        <div className="text-center">
          <div className="text-lg font-bold text-gray-900">
            {agent.avg_duration_ms > 0 ? `${agent.avg_duration_ms.toFixed(0)}ms` : "-"}
          </div>
          <div className="text-xs text-gray-500">耗时</div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-2 mt-3 pt-3 border-t border-gray-100 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          className="flex-1 px-3 py-1.5 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition-colors"
          onClick={(e) => {
            e.stopPropagation();
            onRun?.(agent.agent_id);
          }}
        >
          测试运行
        </button>
        <button
          className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${
            agent.enabled
              ? "text-red-600 bg-red-50 hover:bg-red-100"
              : "text-green-600 bg-green-50 hover:bg-green-100"
          }`}
          onClick={(e) => {
            e.stopPropagation();
            onToggle?.(agent.agent_id, !agent.enabled);
          }}
        >
          {agent.enabled ? "停用" : "启用"}
        </button>
      </div>
    </div>
  );
}
