"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  Bot,
  Brain,
  CheckCircle2,
  Clock,
  Database,
  GitBranch,
  Loader2,
  Play,
  RefreshCw,
  UserRound,
  Wrench,
  XCircle,
} from "lucide-react";

import {
  getWorkflow,
  executeWorkflow,
  listExecutions,
} from "@/services/agents";
import type {
  Workflow,
  WorkflowExecution,
  WorkflowNode,
} from "@/types/agents";
import { layout } from "@/styles/layout";

const NODE_ICONS: Record<WorkflowNode["node_type"], typeof Bot> = {
  agent: Bot,
  human: UserRound,
  condition: GitBranch,
  parallel: GitBranch,
  tool: Wrench,
  memory: Database,
  knowledge_graph: Brain,
  start: Play,
  end: CheckCircle2,
};

const NODE_LABELS: Record<WorkflowNode["node_type"], string> = {
  agent: "智能体",
  human: "人工",
  condition: "条件",
  parallel: "并行",
  tool: "工具",
  memory: "记忆",
  knowledge_graph: "知识图谱",
  start: "开始",
  end: "结束",
};

const NODE_COLORS: Record<WorkflowNode["node_type"], string> = {
  agent: "border-blue-500 bg-blue-500/10 text-blue-400",
  human: "border-yellow-500 bg-yellow-500/10 text-yellow-400",
  condition: "border-purple-500 bg-purple-500/10 text-purple-400",
  parallel: "border-cyan-500 bg-cyan-500/10 text-cyan-400",
  tool: "border-orange-500 bg-orange-500/10 text-orange-400",
  memory: "border-green-500 bg-green-500/10 text-green-400",
  knowledge_graph: "border-pink-500 bg-pink-500/10 text-pink-400",
  start: "border-gray-500 bg-gray-500/10 text-os-subtle",
  end: "border-gray-500 bg-gray-500/10 text-os-subtle",
};

function NodeCard({ node }: { node: WorkflowNode }) {
  const Icon = NODE_ICONS[node.node_type] || Bot;
  const colorClass = NODE_COLORS[node.node_type] || "";
  const label = NODE_LABELS[node.node_type] || node.node_type;

  return (
    <div className={`p-4 rounded-xl border ${colorClass} bg-os-surface`}>
      <div className="flex items-center gap-2 mb-1">
        <Icon className="w-4 h-4" />
        <span className="text-xs uppercase tracking-wider opacity-70">{label}</span>
        {node.status && node.status !== "pending" && (
          <span
            className={`ml-auto text-xs px-2 py-0.5 rounded-full ${
              node.status === "completed"
                ? "bg-green-500/20 text-green-300"
                : node.status === "failed"
                  ? "bg-red-500/20 text-red-300"
                  : node.status === "running"
                    ? "bg-blue-500/20 text-blue-300"
                    : "bg-gray-500/20 text-os-text"
            }`}
          >
            {node.status}
          </span>
        )}
      </div>
      <p className="font-medium text-os-text-high">{node.name}</p>
      {node.description && (
        <p className="text-xs opacity-70 mt-1">{node.description}</p>
      )}
      {node.agent_id && (
        <p className="text-xs opacity-50 mt-1">智能体: {node.agent_id}</p>
      )}
      {node.next_nodes.length > 0 && (
        <p className="text-xs opacity-40 mt-2">
          → {node.next_nodes.length} 个下游节点
        </p>
      )}
    </div>
  );
}

function ExecutionCard({ execution }: { execution: WorkflowExecution }) {
  const statusColors: Record<string, string> = {
    draft: "bg-gray-500/20 text-os-text",
    running: "bg-blue-500/20 text-blue-300",
    paused: "bg-yellow-500/20 text-yellow-300",
    completed: "bg-green-500/20 text-green-300",
    failed: "bg-red-500/20 text-red-300",
    cancelled: "bg-gray-500/20 text-os-muted",
  };

  return (
    <Link
      href={`/agents/executions`}
      className="block p-4 rounded-lg bg-os-surface border border-os-border shadow-os-sm hover:border-os-accent/30 transition-colors"
    >
      <div className="flex items-center justify-between mb-2">
        <span
          className={`text-xs px-2 py-0.5 rounded-full ${statusColors[execution.status] || ""}`}
        >
          {execution.status}
        </span>
        <span className="text-xs text-os-muted">
          {execution.duration_ms > 0 ? `${execution.duration_ms.toFixed(0)}ms` : ""}
        </span>
      </div>
      <p className="text-sm text-os-subtle truncate">{execution.execution_id}</p>
      {execution.error && (
        <p className="text-xs text-red-400 mt-1 truncate">{execution.error}</p>
      )}
    </Link>
  );
}

export default function WorkflowDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [executions, setExecutions] = useState<WorkflowExecution[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [executing, setExecuting] = useState(false);

  const fetchData = useCallback(async () => {
    if (!id) return;
    try {
      setLoading(true);
      const [wf, execs] = await Promise.all([
        getWorkflow(id),
        listExecutions(id),
      ]);
      setWorkflow(wf);
      setExecutions(execs);
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleExecute = useCallback(async () => {
    if (!id) return;
    setExecuting(true);
    try {
      const result = await executeWorkflow(id);
      await fetchData();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "执行失败");
    } finally {
      setExecuting(false);
    }
  }, [id, fetchData]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="w-8 h-8 animate-spin text-blue-400" />
      </div>
    );
  }

  if (error || !workflow) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-16">
        <div className="p-4 rounded-lg bg-red-50 text-red-700">
          {error || "工作流不存在"}
        </div>
      </div>
    );
  }

  const nodes = workflow.nodes || [];

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      {/* 面包屑 */}
      <Link
        href="/agents/workflows"
        className="inline-flex items-center gap-1 text-sm text-os-subtle hover:text-os-accent mb-6 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        返回工作流列表
      </Link>

      {/* 头部 */}
      <div className="flex items-start justify-between mb-8">
        <div className="flex items-start gap-4">
          <div className="w-14 h-14 rounded-xl bg-purple-500/20 flex items-center justify-center flex-shrink-0">
            <GitBranch className="w-7 h-7 text-purple-400" />
          </div>
          <div>
            <h1 className="text-3xl font-bold text-os-text-high mb-1">
              {workflow.name}
            </h1>
            <p className="text-os-subtle max-w-lg">{workflow.description}</p>
            <div className="flex items-center gap-3 mt-3">
              <span className="text-xs px-2.5 py-1 rounded-full bg-os-elevated text-os-text border border-os-border">
                v{workflow.version}
              </span>
              <span className="text-xs px-2.5 py-1 rounded-full bg-os-elevated text-os-text border border-os-border">
                {nodes.length} 节点
              </span>
              {workflow.tags?.map((tag) => (
                <span
                  key={tag}
                  className="text-xs px-2 py-1 rounded-full bg-os-elevated text-os-subtle border border-os-border"
                >
                  {tag}
                </span>
              ))}
            </div>
          </div>
        </div>

        <button
          onClick={handleExecute}
          disabled={executing}
          className="px-5 py-2.5 rounded-lg bg-os-accent text-white font-medium hover:bg-os-accent/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
        >
          {executing ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              执行中...
            </>
          ) : (
            <>
              <Play className="w-4 h-4" />
              执行工作流
            </>
          )}
        </button>
      </div>

      {/* 节点流程可视化 */}
      <div className="mb-8">
        <h2 className="text-lg font-semibold text-os-text-high mb-4 flex items-center gap-2">
          <GitBranch className="w-5 h-5 text-purple-400" />
          工作流节点
        </h2>
        <div className={layout.grid.threeLgMd}>
          {nodes.map((node, i) => (
            <div key={node.node_id} className="relative">
              <NodeCard node={node} />
              {i < nodes.length - 1 && (
                <div className="hidden md:flex justify-center py-1">
                  <span className="text-os-muted text-lg">↓</span>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* 执行历史 */}
      <div className="mb-8">
        <div className="flex items-center gap-2 mb-4">
          <h2 className="text-lg font-semibold text-os-text-high">执行历史</h2>
          <button
            onClick={fetchData}
            className="p-1.5 rounded-lg hover:bg-os-elevated transition-colors"
          >
            <RefreshCw className="w-4 h-4 text-os-muted" />
          </button>
        </div>
        {executions.length === 0 ? (
          <p className="text-os-muted text-sm py-8 text-center">
            暂无执行记录
          </p>
        ) : (
          <div className={layout.grid.threeLgMd}>
            {executions.slice(-9).reverse().map((exec) => (
              <ExecutionCard key={exec.execution_id} execution={exec} />
            ))}
          </div>
        )}
      </div>

      {/* 原始数据 */}
      <details className="rounded-xl bg-os-surface border border-os-border shadow-os-sm p-6">
        <summary className="text-sm text-os-subtle cursor-pointer hover:text-os-text">
          工作流详情 (JSON)
        </summary>
        <pre className="mt-4 text-xs text-os-muted overflow-x-auto max-h-96">
          {JSON.stringify(workflow, null, 2)}
        </pre>
      </details>
    </div>
  );
}
