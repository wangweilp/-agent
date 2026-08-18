"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  Activity,
  ArrowLeft,
  BarChart3,
  Bot,
  Brain,
  CheckCircle2,
  Clock,
  History,
  Loader2,
  Play,
  RefreshCw,
  Settings,
  XCircle,
  Zap,
} from "lucide-react";

import { getAgent, runAgent, enableAgent, disableAgent } from "@/services/agents";
import type { AgentDetail, AgentRunResponse } from "@/types/agents";

const AGENT_STATUS_LABELS: Record<string, string> = {
  idle: "空闲",
  running: "运行中",
  done: "已完成",
  error: "错误",
  disabled: "已停用",
};

export default function AgentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [agent, setAgent] = useState<AgentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runResult, setRunResult] = useState<AgentRunResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [query, setQuery] = useState("");

  const fetchAgent = useCallback(async () => {
    if (!id) return;
    try {
      setLoading(true);
      const data = await getAgent(id);
      setAgent(data);
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchAgent();
  }, [fetchAgent]);

  const handleRun = useCallback(async () => {
    if (!id) return;
    setRunning(true);
    setRunResult(null);
    try {
      const result = await runAgent({
        agent_id: id,
        title: query || "人工触发",
        description: query || "从智能体 Detail 页面手动触发",
      });
      setRunResult(result);
    } catch (e: unknown) {
      setRunResult({
        task_id: "",
        agent_id: id,
        agent_name: agent?.name || "",
        success: false,
        output: "",
        error: e instanceof Error ? e.message : "执行失败",
        plan: [],
        observations: [],
        reflections: [],
        tool_calls_count: 0,
        memory_calls_count: 0,
        kg_calls_count: 0,
        duration_ms: 0,
      });
    } finally {
      setRunning(false);
    }
  }, [id, query, agent?.name]);

  const handleToggle = useCallback(async () => {
    if (!id || !agent) return;
    try {
      if (agent.enabled) {
        await disableAgent(id);
      } else {
        await enableAgent(id);
      }
      setAgent((prev) => (prev ? { ...prev, enabled: !prev.enabled } : prev));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "操作失败");
    }
  }, [id, agent]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="w-8 h-8 animate-spin text-blue-700" />
      </div>
    );
  }

  if (error || !agent) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-16">
        <div className="p-4 rounded-lg bg-red-50 text-red-700">
          {error || "智能体不存在"}
        </div>
      </div>
    );
  }

  const successRate = agent.success_rate ?? 1;
  const metrics = agent.metrics || {};
  const agentStatusLabel = agent.status
    ? AGENT_STATUS_LABELS[agent.status] ?? agent.status
    : AGENT_STATUS_LABELS.idle;

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      {/* 面包屑 */}
      <Link
        href="/agents"
        className="inline-flex items-center gap-1 text-sm text-os-subtle hover:text-os-accent mb-6 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        返回智能体中心
      </Link>

      {/* Agent 头部 */}
      <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-4">
          <div className="w-14 h-14 rounded-xl bg-blue-500/20 flex items-center justify-center flex-shrink-0">
            <Bot className="w-7 h-7 text-blue-700" />
          </div>
          <div>
            <h1 className="text-3xl font-bold text-os-text-high mb-1">{agent.name}</h1>
            <p className="text-os-subtle max-w-lg">{agent.description}</p>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <span className="text-xs px-2.5 py-1 rounded-full bg-os-elevated text-os-text border border-os-border">
                v{agent.version}
              </span>
              <span
                className={`text-xs px-2.5 py-1 rounded-full border ${
                  agent.enabled
                    ? "border-green-200 bg-green-50 text-green-700"
                    : "bg-os-elevated text-os-subtle border-os-border"
                }`}
              >
                {agent.enabled ? "已启用" : "已停用"}
              </span>
              {agent.tags?.map((tag) => (
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

        <div className="flex items-center gap-2">
          <button
            onClick={handleToggle}
            className={`px-4 py-2 rounded-lg text-sm font-medium border transition-colors ${
              agent.enabled
                ? "border-red-200 text-red-700 hover:bg-red-50"
                : "border-green-200 text-green-700 hover:bg-green-50"
            }`}
          >
            {agent.enabled ? "停用" : "启用"}
          </button>
        </div>
      </div>

      {/* 指标卡片 */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
        {[
          {
            icon: Activity,
            label: "调用次数",
            value: agent.usage_count ?? 0,
            color: "text-blue-700",
          },
          {
            icon: CheckCircle2,
            label: "成功率",
            value: `${(successRate * 100).toFixed(1)}%`,
            color: successRate > 0.9 ? "text-green-700" : "text-amber-700",
          },
          {
            icon: Clock,
            label: "平均耗时",
            value: agent.avg_duration_ms > 0
              ? `${agent.avg_duration_ms.toFixed(0)}ms`
              : "暂无数据",
            color: "text-violet-700",
          },
          {
            icon: Brain,
            label: "知识利用率",
            value: agent.avg_duration_ms > 0 ? "了解详情" : "暂无数据",
            color: "text-cyan-700",
          },
          {
            icon: Zap,
            label: "状态",
            value: agentStatusLabel,
            color: agent.status === "done" ? "text-green-700" : "text-os-subtle",
          },
        ].map(({ icon: Icon, label, value, color }) => (
          <div
            key={label}
            className="p-4 rounded-xl bg-os-surface border border-os-border"
          >
            <div className="mb-2 flex items-center gap-2 text-xs text-os-subtle">
              <Icon className="w-3.5 h-3.5" />
              {label}
            </div>
            <div className={`text-xl font-bold ${color}`}>{value}</div>
          </div>
        ))}
      </div>

      {/* 执行测试 */}
      <div className="rounded-xl bg-os-surface border border-os-border shadow-os-sm p-6 mb-8">
        <h2 className="text-lg font-semibold text-os-text-high mb-4 flex items-center gap-2">
          <Play className="w-5 h-5 text-blue-700" />
          手动执行
        </h2>
        <div className="flex flex-col gap-3 sm:flex-row">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="输入查询或任务描述..."
            className="flex-1 px-4 py-2.5 rounded-lg bg-os-elevated border border-os-border text-os-text-high placeholder:text-os-subtle focus:outline-none focus:border-os-accent transition-colors"
          />
          <button
            onClick={handleRun}
            disabled={running || !agent.enabled}
            className="px-6 py-2.5 rounded-lg bg-os-accent text-white font-medium hover:bg-os-accent/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
          >
            {running ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                执行中...
              </>
            ) : (
              <>
                <Play className="w-4 h-4" />
                执行
              </>
            )}
          </button>
        </div>

        {runResult && (
          <div className="mt-6 p-4 rounded-lg bg-os-elevated border border-os-border">
            <div className="flex items-center gap-2 mb-3">
              {runResult.success ? (
                <CheckCircle2 className="w-5 h-5 text-green-700" />
              ) : (
                <XCircle className="w-5 h-5 text-red-700" />
              )}
              <span
                className={`font-medium ${runResult.success ? "text-green-700" : "text-red-700"}`}
              >
                {runResult.success ? "执行成功" : "执行失败"}
              </span>
              <span className="text-sm text-os-subtle">
                {runResult.duration_ms > 0
                  ? `耗时 ${runResult.duration_ms.toFixed(0)}ms`
                  : ""}
              </span>
            </div>

            {runResult.error && (
              <div className="mb-3 text-sm text-red-700">{runResult.error}</div>
            )}

            {runResult.plan.length > 0 && (
              <details className="mb-3">
                <summary className="text-sm text-os-subtle cursor-pointer hover:text-os-text">
                  执行计划 ({runResult.plan.length} 步)
                </summary>
                <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm text-os-subtle">
                  {runResult.plan.map((step, i) => (
                    <li key={i}>{step}</li>
                  ))}
                </ol>
              </details>
            )}

            {runResult.output && (
              <div className="mt-2">
                <p className="mb-1 text-xs text-os-subtle">输出</p>
                <pre className="text-sm text-os-text whitespace-pre-wrap bg-os-surface rounded-lg p-3 max-h-64 overflow-y-auto">
                  {runResult.output}
                </pre>
              </div>
            )}

            <div className="mt-3 flex flex-wrap gap-4 text-xs text-os-subtle">
              <span>🔧 工具调用：{runResult.tool_calls_count}</span>
              <span>🧠 记忆调用：{runResult.memory_calls_count}</span>
              <span>🕸️ 图谱调用：{runResult.kg_calls_count}</span>
            </div>
          </div>
        )}
      </div>

      {/* Agent 配置 */}
      <div className="rounded-xl bg-os-surface border border-os-border shadow-os-sm p-6">
        <h2 className="text-lg font-semibold text-os-text-high mb-4 flex items-center gap-2">
          <Settings className="w-5 h-5 text-os-subtle" />
          配置信息
        </h2>
        {agent.config && Object.keys(agent.config).length > 0 ? (
          <pre className="text-sm text-os-text bg-os-surface rounded-lg p-4 overflow-x-auto">
            {JSON.stringify(agent.config, null, 2)}
          </pre>
        ) : (
          <p className="text-sm text-os-subtle">暂无可配置项</p>
        )}
      </div>
    </div>
  );
}
