"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Bot,
  CheckCircle2,
  Clock,
  Eye,
  GitBranch,
  Loader2,
  Play,
  Plus,
  RefreshCw,
  Search,
  UserRound,
  Workflow as WorkflowIcon,
  X,
} from "lucide-react";

import { createWorkflow, executeWorkflow, listWorkflows } from "@/services/agents";
import type { Workflow, WorkflowExecution, WorkflowNode } from "@/types/agents";
import { layout } from "@/styles/layout";

function nodeMeta(nodeType: WorkflowNode["node_type"]) {
  switch (nodeType) {
    case "agent":
      return {
        icon: Bot,
        label: "智能体",
        className: "border-blue-400/30 bg-blue-400/10 text-blue-200",
      };
    case "human":
      return {
        icon: UserRound,
        label: "人工",
        className: "border-amber-400/30 bg-amber-400/10 text-amber-200",
      };
    case "condition":
      return {
        icon: GitBranch,
        label: "条件",
        className: "border-purple-400/30 bg-purple-400/10 text-purple-200",
      };
    case "parallel":
      return {
        icon: GitBranch,
        label: "并行",
        className: "border-cyan-400/30 bg-cyan-400/10 text-cyan-200",
      };
    case "start":
      return {
        icon: Play,
        label: "开始",
        className: "border-emerald-400/30 bg-emerald-400/10 text-emerald-200",
      };
    case "end":
      return {
        icon: CheckCircle2,
        label: "结束",
        className: "border-os-border bg-os-elevated text-os-subtle",
      };
    default:
      return {
        icon: WorkflowIcon,
        label: nodeType,
        className: "border-os-border bg-os-elevated text-os-subtle",
      };
  }
}

function WorkflowStats({ workflows }: { workflows: Workflow[] }) {
  const stats = useMemo(() => {
    const nodes = workflows.flatMap((workflow) => workflow.nodes);
    return {
      total: workflows.length,
      nodes: nodes.length,
      agentNodes: nodes.filter((node) => node.node_type === "agent").length,
      humanNodes: nodes.filter((node) => node.node_type === "human").length,
    };
  }, [workflows]);

  return (
    <section className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {[
        { label: "工作流", value: stats.total, icon: WorkflowIcon },
        { label: "节点总数", value: stats.nodes, icon: GitBranch },
        { label: "智能体节点", value: stats.agentNodes, icon: Bot },
        { label: "人工节点", value: stats.humanNodes, icon: UserRound },
      ].map(({ label, value, icon: Icon }) => (
        <div key={label} className="os-card p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs text-os-muted">{label}</p>
              <p className="mt-2 text-2xl font-semibold text-os-text-high">{value}</p>
            </div>
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-os-elevated text-os-accent">
              <Icon size={18} />
            </div>
          </div>
        </div>
      ))}
    </section>
  );
}

function NodePill({ node }: { node: WorkflowNode }) {
  const meta = nodeMeta(node.node_type);
  const Icon = meta.icon;

  return (
    <div
      className={`flex min-w-32 max-w-48 items-center gap-2 rounded-md border px-3 py-2 ${meta.className}`}
      title={`${node.name} (${meta.label})`}
    >
      <Icon size={14} className="shrink-0" />
      <span className="truncate text-xs font-medium">{node.name}</span>
    </div>
  );
}

function WorkflowFlow({ workflow }: { workflow: Workflow }) {
  if (workflow.nodes.length === 0) {
    return <p className="text-xs text-os-muted">暂无节点</p>;
  }

  return (
    <div className="overflow-x-auto pb-1">
      <div className="flex min-w-max items-center gap-2">
        {workflow.nodes.map((node, index) => (
          <div key={node.node_id} className="flex items-center gap-2">
            {index > 0 && <span className="text-os-muted">→</span>}
            <NodePill node={node} />
          </div>
        ))}
      </div>
    </div>
  );
}

function ExecutionToast({ execution }: { execution: WorkflowExecution | null }) {
  if (!execution) return null;

  const success = execution.status === "completed";

  return (
    <div
      className={`mb-6 rounded-md border p-4 text-sm leading-6 ${
        success
          ? "border-emerald-400/20 bg-emerald-400/10 text-emerald-200"
          : "border-amber-400/20 bg-amber-400/10 text-amber-200"
      }`}
    >
      <div className="flex flex-wrap items-center gap-2">
        {success ? <CheckCircle2 size={16} /> : <Clock size={16} />}
        <span>执行状态：{execution.status}</span>
        <span>耗时：{execution.duration_ms.toFixed(0)}ms</span>
      </div>
    </div>
  );
}

export default function WorkflowBuilderPage() {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [executing, setExecuting] = useState<string | null>(null);
  const [selectedWorkflow, setSelectedWorkflow] = useState<Workflow | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [query, setQuery] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const [lastExecution, setLastExecution] = useState<WorkflowExecution | null>(null);

  const fetchWorkflows = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setWorkflows(await listWorkflows());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchWorkflows();
  }, [fetchWorkflows]);

  const allTags = useMemo(
    () => [...new Set(workflows.flatMap((workflow) => workflow.tags))].sort(),
    [workflows],
  );

  const filteredWorkflows = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();

    return workflows.filter((workflow) => {
      if (tagFilter && !workflow.tags.includes(tagFilter)) return false;
      if (!normalizedQuery) return true;

      const haystack = [
        workflow.name,
        workflow.description,
        workflow.workflow_id,
        ...workflow.tags,
        ...workflow.nodes.flatMap((node) => [node.name, node.node_type, node.agent_id]),
      ]
        .join(" ")
        .toLowerCase();

      return haystack.includes(normalizedQuery);
    });
  }, [query, tagFilter, workflows]);

  const handleExecute = async (workflowId: string) => {
    setExecuting(workflowId);
    setError(null);
    setLastExecution(null);

    try {
      const result = await executeWorkflow(workflowId);
      setLastExecution(result);
      await fetchWorkflows();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "执行失败");
    } finally {
      setExecuting(null);
    }
  };

  const handleCreateQuick = async () => {
    setError(null);

    try {
      await createWorkflow({
        name: `知识检索演示 ${new Date().toLocaleTimeString("zh-CN", { hour12: false })}`,
        description: "用于验证智能体编排可视化的演示工作流。",
        nodes: [
          {
            name: "开始",
            node_type: "start",
            description: "接收输入并启动流程",
            is_start: true,
          },
          {
            name: "知识检索",
            node_type: "agent",
            agent_id: "builtin-knowledge",
            description: "检索相关知识并生成摘要",
          },
          {
            name: "结束",
            node_type: "end",
            description: "汇总输出",
          },
        ],
        tags: ["demo", "knowledge"],
      });
      await fetchWorkflows();
      setShowCreate(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "创建失败");
    }
  };

  return (
    <main className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6">
      <header className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-os-border bg-os-surface px-3 py-1 text-xs text-os-subtle">
            <WorkflowIcon size={14} className="text-os-accent" />
            Agent 编排与流程观察
          </div>
          <h1 className="text-3xl font-semibold tracking-normal text-os-text-high">工作流编排</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-os-subtle">
            以节点图方式查看流程结构、筛选标签并触发执行，避免把后端 JSON 直接暴露给前端用户。
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setShowCreate((value) => !value)}
            className="inline-flex h-9 items-center justify-center gap-2 rounded-md bg-os-accent px-3 text-xs font-medium text-white transition-colors hover:bg-os-accent/90"
          >
            <Plus size={14} />
            创建演示工作流
          </button>
          <button
            type="button"
            onClick={() => void fetchWorkflows()}
            disabled={loading}
            className="inline-flex h-9 items-center justify-center gap-2 rounded-md border border-os-border bg-os-surface px-3 text-xs font-medium text-os-subtle transition-colors hover:text-os-text-high disabled:cursor-not-allowed disabled:opacity-60"
          >
            {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            刷新
          </button>
        </div>
      </header>

      <WorkflowStats workflows={workflows} />

      <section className="os-card mb-6 p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <label className="relative block flex-1">
            <Search
              size={15}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-os-muted"
            />
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索工作流、节点、智能体或 ID"
              className="h-10 w-full rounded-md border border-os-border bg-os-elevated pl-9 pr-3 text-sm text-os-text-high outline-none transition-colors placeholder:text-os-muted focus:border-os-accent"
            />
          </label>

          <select
            value={tagFilter}
            onChange={(event) => setTagFilter(event.target.value)}
            className="h-10 rounded-md border border-os-border bg-os-elevated px-3 text-sm text-os-text-high outline-none transition-colors focus:border-os-accent lg:w-56"
          >
            <option value="">所有标签</option>
            {allTags.map((tag) => (
              <option key={tag} value={tag}>
                {tag}
              </option>
            ))}
          </select>
        </div>
      </section>

      {showCreate && (
        <section className="os-card mb-6 border-os-accent/30 bg-os-accent/5 p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-sm font-semibold text-os-text-high">创建知识检索演示流程</h2>
              <p className="mt-1 text-xs leading-5 text-os-subtle">
                后端会生成节点 ID，前端只提交节点名称、类型和起始标记，保持编排创建边界清晰。
              </p>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => void handleCreateQuick()}
                className="inline-flex h-9 items-center justify-center gap-2 rounded-md bg-os-accent px-3 text-xs font-medium text-white transition-colors hover:bg-os-accent/90"
              >
                <Plus size={14} />
                创建
              </button>
              <button
                type="button"
                onClick={() => setShowCreate(false)}
                className="h-9 rounded-md bg-os-elevated px-3 text-xs font-medium text-os-subtle transition-colors hover:text-os-text-high"
              >
                取消
              </button>
            </div>
          </div>
        </section>
      )}

      {error && (
        <div className="mb-6 rounded-md border border-red-400/20 bg-red-400/10 p-4 text-sm leading-6 text-red-200">
          {error}
        </div>
      )}

      <ExecutionToast execution={lastExecution} />

      {loading ? (
        <section className={layout.grid.twoLg}>
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="os-card h-64 p-5">
              <div className="shimmer-bg h-5 w-44 rounded bg-os-elevated" />
              <div className="mt-4 h-20 rounded bg-os-elevated/70" />
              <div className="mt-5 flex gap-2">
                <div className="shimmer-bg h-8 w-20 rounded bg-os-elevated" />
                <div className="shimmer-bg h-8 w-20 rounded bg-os-elevated" />
              </div>
            </div>
          ))}
        </section>
      ) : filteredWorkflows.length > 0 ? (
        <section className={layout.grid.twoLg}>
          {filteredWorkflows.map((workflow) => (
            <article key={workflow.workflow_id} className="os-card os-card-hover p-5">
              <div className="mb-4 flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <Link
                    href={`/agents/workflows/${workflow.workflow_id}`}
                    className="break-words text-base font-semibold text-os-text-high hover:text-blue-400 transition-colors"
                  >
                    {workflow.name}
                  </Link>
                  <p className="mt-1 line-clamp-2 text-xs leading-5 text-os-subtle">
                    {workflow.description || "暂无描述"}
                  </p>
                </div>
                <span className="os-badge shrink-0 bg-os-elevated text-os-subtle">
                  v{workflow.version}
                </span>
              </div>

              <WorkflowFlow workflow={workflow} />

              <div className="mt-4 flex flex-wrap gap-1.5">
                {workflow.tags.length > 0 ? (
                  workflow.tags.map((tag) => (
                    <span key={tag} className="os-badge bg-os-elevated text-os-subtle">
                      {tag}
                    </span>
                  ))
                ) : (
                  <span className="text-xs text-os-muted">无标签</span>
                )}
              </div>

              <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-os-border pt-4">
                <div className="text-xs text-os-muted">
                  {workflow.nodes.length} 个节点 · 起点 {workflow.start_node_id || "未设置"}
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setSelectedWorkflow(workflow)}
                    className="inline-flex h-8 items-center justify-center gap-1.5 rounded-md bg-os-elevated px-3 text-xs font-medium text-os-subtle transition-colors hover:text-os-text-high"
                  >
                    <Eye size={13} />
                    详情
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleExecute(workflow.workflow_id)}
                    disabled={executing === workflow.workflow_id}
                    className="inline-flex h-8 items-center justify-center gap-1.5 rounded-md bg-emerald-500 px-3 text-xs font-medium text-white transition-colors hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {executing === workflow.workflow_id ? (
                      <Loader2 size={13} className="animate-spin" />
                    ) : (
                      <Play size={13} />
                    )}
                    {executing === workflow.workflow_id ? "执行中" : "执行"}
                  </button>
                </div>
              </div>
            </article>
          ))}
        </section>
      ) : (
        <section className="os-card flex min-h-56 flex-col items-center justify-center px-4 py-10 text-center">
          <WorkflowIcon size={28} className="text-os-muted" />
          <h2 className="mt-3 text-base font-semibold text-os-text-high">没有匹配的工作流</h2>
          <p className="mt-1 max-w-md text-sm leading-6 text-os-subtle">
            调整搜索条件，或创建一个演示工作流验证编排界面。
          </p>
        </section>
      )}

      {selectedWorkflow && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/20 px-4 py-6 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-labelledby="workflow-detail-title"
        >
          <div className="os-card flex max-h-[86vh] w-full max-w-2xl flex-col overflow-hidden">
            <div className="flex items-start justify-between gap-4 border-b border-os-border p-5">
              <div className="min-w-0">
                <p className="text-2xs font-medium uppercase tracking-wider text-os-muted">
                  Workflow Detail
                </p>
                <h2
                  id="workflow-detail-title"
                  className="mt-1 break-words text-base font-semibold text-os-text-high"
                >
                  {selectedWorkflow.name}
                </h2>
                <p className="mt-1 text-xs leading-5 text-os-subtle">
                  {selectedWorkflow.description || "暂无描述"}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSelectedWorkflow(null)}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-os-subtle transition-colors hover:bg-os-elevated hover:text-os-text-high"
                aria-label="关闭"
              >
                <X size={16} />
              </button>
            </div>

            <div className="space-y-3 overflow-y-auto p-5">
              {selectedWorkflow.nodes.map((node) => {
                const meta = nodeMeta(node.node_type);
                return (
                  <div key={node.node_id} className="rounded-md border border-os-border bg-os-base p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-sm font-medium text-os-text-high">{node.name}</span>
                      <span className={`rounded-full border px-2 py-0.5 text-2xs ${meta.className}`}>
                        {meta.label}
                      </span>
                    </div>
                    <div className="mt-2 space-y-1 text-xs leading-5 text-os-subtle">
                      <p>ID: {node.node_id}</p>
                      {node.agent_id && <p>智能体: {node.agent_id}</p>}
                      {node.description && <p>{node.description}</p>}
                      {node.next_nodes.length > 0 && <p>下一节点: {node.next_nodes.join(", ")}</p>}
                      {node.human_prompt && <p>人工提示: {node.human_prompt}</p>}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
