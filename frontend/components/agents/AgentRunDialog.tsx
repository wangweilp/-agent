"use client";

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  Loader2,
  Play,
  Sparkles,
  X,
} from "lucide-react";

import { runAgent } from "@/services/agents";
import type { AgentRunRequest, AgentRunResponse, AgentSummary } from "@/types/agents";

interface AgentRunDialogProps {
  agent: AgentSummary | null;
  open: boolean;
  onClose: () => void;
}

function ResultList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;

  return (
    <div>
      <h4 className="mb-2 text-xs font-medium text-os-muted">{title}</h4>
      <ol className="space-y-1.5 text-xs leading-5 text-os-subtle">
        {items.map((item, index) => (
          <li key={`${title}-${index}`} className="rounded-md bg-os-elevated px-3 py-2">
            {item}
          </li>
        ))}
      </ol>
    </div>
  );
}

export function AgentRunDialog({ agent, open, onClose }: AgentRunDialogProps) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AgentRunResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !agent) return;

    setTitle(`测试 ${agent.name}`);
    setDescription("");
    setResult(null);
    setError(null);
  }, [agent, open]);

  if (!open || !agent) return null;

  const handleRun = async () => {
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const req: AgentRunRequest = {
        agent_id: agent.agent_id,
        title: title.trim() || `测试 ${agent.name}`,
        description: description.trim(),
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
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4 py-6 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="agent-run-title"
    >
      <div className="os-card flex max-h-[88vh] w-full max-w-2xl flex-col overflow-hidden">
        <div className="flex items-start justify-between gap-4 border-b border-os-border p-5">
          <div className="min-w-0">
            <p className="text-2xs font-medium uppercase tracking-wider text-os-muted">
              Agent 运行测试
            </p>
            <h2
              id="agent-run-title"
              className="mt-1 break-words text-base font-semibold text-os-text-high"
            >
              {agent.name}
            </h2>
            <p className="mt-1 line-clamp-2 text-xs leading-5 text-os-subtle">
              {agent.description || "暂无描述"}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-os-subtle transition-colors hover:bg-os-elevated hover:text-os-text-high"
            aria-label="关闭"
          >
            <X size={16} />
          </button>
        </div>

        <div className="space-y-4 overflow-y-auto p-5">
          <div className="grid gap-3">
            <label className="grid gap-1.5">
              <span className="text-xs font-medium text-os-text-high">任务标题</span>
              <input
                type="text"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder={`测试 ${agent.name}`}
                className="h-10 rounded-md border border-os-border bg-os-elevated px-3 text-sm text-os-text-high outline-none transition-colors placeholder:text-os-muted focus:border-os-accent"
              />
            </label>

            <label className="grid gap-1.5">
              <span className="text-xs font-medium text-os-text-high">任务描述</span>
              <textarea
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="描述希望这个 Agent 处理的任务、输入或约束"
                rows={3}
                className="resize-none rounded-md border border-os-border bg-os-elevated px-3 py-2 text-sm leading-6 text-os-text-high outline-none transition-colors placeholder:text-os-muted focus:border-os-accent"
              />
            </label>
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={handleRun}
              disabled={loading}
              className="inline-flex h-9 items-center justify-center gap-2 rounded-md bg-os-accent px-4 text-xs font-medium text-white transition-colors hover:bg-os-accent/90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
              {loading ? "执行中" : "执行"}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="h-9 rounded-md bg-os-elevated px-4 text-xs font-medium text-os-subtle transition-colors hover:text-os-text-high"
            >
              取消
            </button>
          </div>

          {error && (
            <div className="flex items-start gap-2 rounded-md border border-red-400/20 bg-red-400/10 p-3 text-xs leading-5 text-red-200">
              <AlertTriangle size={15} className="mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {loading && !result && (
            <div className="rounded-lg border border-os-border bg-os-base p-4">
              <div className="flex items-center gap-2 text-sm text-os-text-high">
                <CircleDashed size={16} className="animate-spin text-os-accent" />
                正在调用后端 Agent 执行器
              </div>
              <div className="mt-3 h-2 overflow-hidden rounded-full bg-os-elevated">
                <div className="h-full w-1/2 animate-pulse rounded-full bg-os-accent" />
              </div>
            </div>
          )}

          {result && (
            <section className="space-y-4 rounded-lg border border-os-border bg-os-base p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={`os-badge ${
                    result.success
                      ? "bg-emerald-400/10 text-emerald-300"
                      : "bg-red-400/10 text-red-300"
                  }`}
                >
                  <CheckCircle2 size={12} />
                  {result.success ? "成功" : "失败"}
                </span>
                <span className="os-badge bg-os-elevated text-os-subtle">
                  耗时 {result.duration_ms.toFixed(0)}ms
                </span>
                <span className="os-badge bg-os-elevated text-os-subtle">
                  工具 {result.tool_calls_count}
                </span>
                <span className="os-badge bg-os-elevated text-os-subtle">
                  记忆 {result.memory_calls_count}
                </span>
                <span className="os-badge bg-os-elevated text-os-subtle">
                  KG {result.kg_calls_count}
                </span>
              </div>

              {result.error && <p className="text-xs leading-5 text-red-300">{result.error}</p>}

              <div>
                <h4 className="mb-2 flex items-center gap-1.5 text-xs font-medium text-os-muted">
                  <Sparkles size={13} />
                  输出
                </h4>
                <div className="max-h-56 overflow-y-auto whitespace-pre-wrap rounded-md bg-os-elevated p-3 text-sm leading-6 text-os-text-high">
                  {result.output || "无输出"}
                </div>
              </div>

              <ResultList title="执行计划" items={result.plan} />
              <ResultList title="观察记录" items={result.observations} />
              <ResultList title="反思" items={result.reflections} />
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
