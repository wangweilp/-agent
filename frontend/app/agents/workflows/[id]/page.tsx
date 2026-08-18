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
  agent: "border-blue-200 bg-blue-50 text-blue-700",
  human: "border-yellow-200 bg-yellow-50 text-yellow-800",
  condition: "border-purple-200 bg-purple-50 text-purple-700",
  parallel: "border-cyan-200 bg-cyan-50 text-cyan-700",
  tool: "border-orange-200 bg-orange-50 text-orange-700",
  memory: "border-green-200 bg-green-50 text-green-700",
  knowledge_graph: "border-pink-200 bg-pink-50 text-pink-700",
  start: "border-gray-200 bg-gray-50 text-gray-700",
  end: "border-gray-200 bg-gray-50 text-gray-700",
};

const STATUS_LABELS: Record<string, string> = {
  pending: "等待中",
  draft: "草稿",
  running: "运行中",
  paused: "等待人工",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

function NodeCard({ node }: { node: WorkflowNode }) {
  const Icon = NODE_ICONS[node.node_type] || Bot;
  const colorClass = NODE_COLORS[node.node_type] || "";
  const label = NODE_LABELS[node.node_type] || node.node_type;

  return (
    <div className={`rounded-xl border p-4 ${colorClass}`}>
      <div className="flex items-center gap-2 mb-1">
        <Icon className="w-4 h-4" />
        <span className="text-xs uppercase tracking-wider">{label}</span>
        {node.status && node.status !== "pending" && (
          <span
            className={`ml-auto text-xs px-2 py-0.5 rounded-full ${
              node.status === "completed"
                ? "bg-green-50 text-green-700"
                : node.status === "failed"
                  ? "bg-red-50 text-red-700"
                  : node.status === "running"
                    ? "bg-blue-50 text-blue-700"
                    : "bg-gray-50 text-gray-700"
            }`}
          >
            {STATUS_LABELS[node.status] ?? node.status}
          </span>
        )}
      </div>
      <p className="font-medium text-os-text-high">{node.name}</p>
      {node.description && (
        <p className="mt-1 text-xs text-os-subtle">{node.description}</p>
      )}
      {node.agent_id && (
        <p className="mt-1 text-xs text-os-subtle">智能体：{node.agent_id}</p>
      )}
      {node.next_nodes.length > 0 && (
        <p className="mt-2 text-xs text-os-subtle">
          → {node.next_nodes.length} 个下游节点
        </p>
      )}
    </div>
  );
}

function ExecutionCard({ execution }: { execution: WorkflowExecution }) {
  const statusColors: Record<string, string> = {
    draft: "bg-gray-50 text-gray-700",
    running: "bg-blue-50 text-blue-700",
    paused: "bg-yellow-50 text-yellow-800",
    completed: "bg-green-50 text-green-700",
    failed: "bg-red-50 text-red-700",
    cancelled: "bg-gray-50 text-gray-700",
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
          {STATUS_LABELS[execution.status] ?? execution.status}
        </span>
        <span className="text-xs text-os-subtle">
          {execution.duration_ms > 0 ? `${execution.duration_ms.toFixed(0)}ms` : ""}
        </span>
      </div>
      <p className="text-sm text-os-subtle truncate">{execution.execution_id}</p>
      {execution.error && (
        <p className="mt-1 truncate text-xs text-red-700">{execution.error}</p>
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
      await executeWorkflow(id);
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
        <Loader2 className="w-8 h-8 animate-spin text-blue-700" />
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
      <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-4">
          <div className="w-14 h-14 rounded-xl bg-purple-500/20 flex items-center justify-center flex-shrink-0">
            <GitBranch className="w-7 h-7 text-purple-700" />
          </div>
          <div>
            <h1 className="text-3xl font-bold text-os-text-high mb-1">
              {workflow.name}
            </h1>
            <p className="text-os-subtle max-w-lg">{workflow.description}</p>
            <div className="mt-3 flex flex-wrap items-center gap-3">
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
          <GitBranch className="w-5 h-5 text-purple-700" />
          工作流节点
        </h2>
        <div className={layout.grid.threeLgMd}>
          {nodes.length === 0 ? (
            <p className="py-8 text-sm text-os-subtle">暂无工作流节点</p>
          ) : nodes.map((node, i) => (
            <div key={node.node_id} className="relative">
              <NodeCard node={node} />
              {i < nodes.length - 1 && (
                <div className="hidden md:flex justify-center py-1">
                  <span className="text-lg text-os-subtle">↓</span>
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
          <p className="py-8 text-center text-sm text-os-subtle">
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
          工作流详情（JSON）
        </summary>
        <pre className="mt-4 max-h-96 overflow-x-auto text-xs text-os-text">
          {JSON.stringify(workflow, null, 2)}
        </pre>
      </details>
    </div>
  );
}
