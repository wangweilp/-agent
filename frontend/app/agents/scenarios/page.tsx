"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ArrowRight,
  Beaker,
  Bot,
  Brain,
  Building2,
  CheckCircle2,
  Clock,
  Copy,
  Database,
  FileText,
  GitBranch,
  Layers,
  Loader2,
  Play,
  RefreshCw,
  Search,
  Shield,
  Sparkles,
  Workflow,
  XCircle,
  Zap,
} from "lucide-react";

import {
  listScenarios,
  runMeetingToTraining,
  runDepartmentAssistant,
} from "@/services/agents";
import type {
  ScenarioDefinition,
  ScenarioRunResponse,
  MeetingToTrainingResult,
  DepartmentAssistantResult,
} from "@/types/agents";

// ═══════════════════════════════════════════
// Demo Data
// ═══════════════════════════════════════════

const DEMO_MEETINGS = [
  {
    label: "项目复盘会议",
    meeting_title: "知维 OS v2.0 项目复盘会议",
    meeting_notes:
      "参会人：张总(项目负责人)、李工(研发组长)、王经理(产品经理)、赵运营(运营)\n\n会议内容：\n1. 项目进度回顾：v2.0 已完成 AI Coach、Knowledge Graph、Memory Search Center 等核心模块，决定下周启动内部测试。\n2. 技术方案讨论：李工汇报后端已采用六边形架构，API 响应时间降到 50ms 以下。企业 AI Agent 平台已完成 Runtime 和 Registry。\n3. 下一步计划：张总确定比赛演示方案、李工负责性能优化、王经理梳理演示场景、赵运营准备企业案例数据。\n4. 风险点：比赛日期临近需要集中打磨演示效果。",
  },
  {
    label: "新人培训会议",
    meeting_title: "新人入职培训 — Enterprise AI Agent 平台",
    meeting_notes:
      "参会人：刘HR、新员工小陈、新员工小林、导师李工\n\n会议内容：\n1. 平台认知：刘HR介绍知维 OS (Zhiwei OS) 核心模块：Memory、Knowledge Graph、AI Coach、Enterprise AI Agent。\n2. 技术架构：导师李工讲解六边形架构、PEOR Agent 循环、WorkflowEngine 9种节点类型。\n3. 新人7天学习计划：第1-2天熟悉代码、第3-4天深入Memory/KG、第5天理解Agent Runtime、第6天实践业务场景、第7天写自己的Agent并测试。",
  },
];

const DEMO_QUESTIONS = [
  { department: "engineering", label: "研发部 — 技术风险评估", question: "当前 Enterprise AI Agent 平台的技术风险有哪些？下一步应如何排期？" },
  { department: "product", label: "产品部 — 差异化价值", question: "如何用最简单的话让企业客户理解 知维 OS 的差异化价值？" },
  { department: "sales", label: "销售部 — 付费说服力", question: "客户问「企业为什么要为内部知识管理付费」时，应该如何回答？" },
  { department: "hr", label: "HR — 新人学习计划", question: "请为新入职的 AI 工程师生成一份 7 天学习计划。" },
  { department: "support", label: "客服部 — 知识图谱价值", question: "客户问「知识图谱对企业有什么实际用处」时，应该如何回答？" },
];

// ═══════════════════════════════════════════
// Components
// ═══════════════════════════════════════════

function CapabilityCards() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-8">
      {[
        { icon: Workflow, label: "工作流（Workflow）编排", desc: "智能体串联执行" },
        { icon: Database, label: "记忆 / KG", desc: "知识库 + 图谱调用" },
        { icon: Layers, label: "追踪与指标（Trace / Metrics）", desc: "每一步可审计" },
      ].map(({ icon: Icon, label, desc }) => (
        <div key={label} className="rounded-lg border border-os-border bg-os-surface shadow-os-sm p-3 text-center">
          <Icon size={18} className="mx-auto mb-1 text-blue-700" />
          <p className="text-xs font-medium text-os-text">{label}</p>
          <p className="text-2xs text-os-subtle">{desc}</p>
        </div>
      ))}
    </div>
  );
}

function DemoStatusBar() {
  return (
    <div className="mb-6 flex flex-wrap items-center gap-2 text-xs text-os-subtle">
      <span className="flex items-center gap-1 rounded bg-green-50 px-2 py-1 text-green-700">
        <CheckCircle2 size={11} /> 演示就绪
      </span>
      <span className="px-2 py-1 rounded bg-os-elevated text-os-subtle">2 业务场景</span>
      <span className="flex items-center gap-1 px-2 py-1 rounded bg-os-elevated text-os-subtle">
        <GitBranch size={11} /> 工作流执行（WorkflowExecution）
      </span>
      <span className="flex items-center gap-1 px-2 py-1 rounded bg-os-elevated text-os-subtle">
        <Shield size={11} /> 鉴权 / RBAC
      </span>
    </div>
  );
}

function ScenarioCard({
  scenario,
  onRun,
  onDemoInput,
  demoOptions,
  busy,
}: {
  scenario: ScenarioDefinition;
  onRun: () => void;
  onDemoInput?: (index: number) => void;
  demoOptions?: Array<{ label: string }>;
  busy: boolean;
}) {
  const isM2T = scenario.scenario_id === "meeting-to-training";

  return (
    <article className="os-card flex flex-col p-5">
      {/* Header */}
      <div className="flex items-start gap-3 mb-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-blue-200 bg-blue-50 text-blue-700">
          {isM2T ? <FileText size={20} /> : <Building2 size={20} />}
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold text-os-text-high">
            {isM2T ? "会议纪要自动沉淀与培训生成" : "部门知识助手"}
          </h3>
          <p className="mt-1 text-xs text-os-subtle line-clamp-2">{scenario.description}</p>
          <div className="flex items-center gap-2 mt-2">
            <span className="text-xs px-2 py-0.5 rounded-full bg-os-elevated text-os-subtle border border-os-border">
              {scenario.category === "automation" ? "自动化" : "助手"}
            </span>
            <span className="rounded-full bg-blue-50 px-2 py-0.5 text-xs text-blue-700">
              工作流
            </span>
            <span className="rounded-full bg-green-50 px-2 py-0.5 text-xs text-green-700">
              追踪
            </span>
          </div>
        </div>
      </div>

      {/* Flow visualization */}
      <div className="mb-4 flex items-center gap-1 overflow-x-auto pb-1 text-2xs text-os-subtle">
        {isM2T ? (
          <>会议纪要 <ArrowRight size={10} /> 会议智能体 <ArrowRight size={10} /> 知识智能体 <ArrowRight size={10} /> KG <ArrowRight size={10} /> 培训智能体 <ArrowRight size={10} /> 工作流执行（WorkflowExecution）</>
        ) : (
          <>部门问题 <ArrowRight size={10} /> 部门智能体 <ArrowRight size={10} /> 记忆 <ArrowRight size={10} /> KG <ArrowRight size={10} /> 建议 <ArrowRight size={10} /> 执行</>
        )}
      </div>

      {/* Demo sample picker */}
      {demoOptions && demoOptions.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1">
          {demoOptions.map((opt, i) => (
            <button
              key={i}
              onClick={() => onDemoInput?.(i)}
              className="rounded border border-amber-200 bg-amber-50 px-2 py-1 text-2xs text-amber-800 transition-colors hover:bg-amber-100"
            >
              <Sparkles size={9} className="inline mr-0.5" />
              {opt.label}
            </button>
          ))}
        </div>
      )}

      {/* Action */}
      <button
        onClick={onRun}
        disabled={busy}
        className="mt-auto inline-flex h-9 w-full items-center justify-center gap-2 rounded-md bg-os-accent px-4 text-xs font-medium text-white transition-colors hover:bg-os-accent/90 disabled:opacity-50"
      >
        {busy ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
        {busy ? "执行中..." : "运行场景"}
      </button>
    </article>
  );
}

function MetricsBar({
  duration_ms,
  memory_refs,
  knowledge_refs,
  fallback_mode,
  steps_count,
}: {
  duration_ms?: number;
  memory_refs?: unknown[];
  knowledge_refs?: unknown[];
  fallback_mode?: boolean;
  steps_count?: number;
}) {
  return (
    <div className="flex flex-wrap gap-2 mb-2">
      {typeof duration_ms === "number" && (
        <span className="text-xs px-2 py-1 rounded bg-os-elevated text-os-text flex items-center gap-1">
          <Clock size={11} /> {duration_ms.toFixed(0)}ms
        </span>
      )}
      {typeof steps_count === "number" && steps_count > 0 && (
        <span className="text-xs px-2 py-1 rounded bg-os-elevated text-os-text flex items-center gap-1">
          <GitBranch size={11} /> {steps_count} 步骤
        </span>
      )}
      <span className="text-xs px-2 py-1 rounded bg-os-elevated text-os-text flex items-center gap-1">
        <Database size={11} /> 记忆 {Array.isArray(memory_refs) ? (memory_refs as unknown[]).length : 0}
      </span>
      <span className="text-xs px-2 py-1 rounded bg-os-elevated text-os-text flex items-center gap-1">
        <Brain size={11} /> 图谱 {Array.isArray(knowledge_refs) ? (knowledge_refs as unknown[]).length : 0}
      </span>
      {fallback_mode && (
        <span className="flex items-center gap-1 rounded bg-amber-50 px-2 py-1 text-xs text-amber-800">
          <Zap size={11} /> 确定性引擎
        </span>
      )}
    </div>
  );
}

function ExecutionTimeline({
  steps,
}: {
  steps?: Record<string, unknown>[];
}) {
  if (!steps || steps.length === 0) {
    return (
      <div className="mt-2 border-l border-os-border pl-4 text-xs text-os-subtle">
        等待执行...
      </div>
    );
  }

  return (
    <details className="mt-3" open>
      <summary className="text-xs text-os-subtle cursor-pointer hover:text-os-text flex items-center gap-1">
        <GitBranch size={12} />
        工作流执行步骤 · {steps.length} 个节点
      </summary>
      <div className="mt-2 pl-4 border-l border-os-border space-y-1">
        {steps.map((item: Record<string, unknown>, i: number) => (
          <div key={i} className="relative pl-5 pb-2">
            <div
              className={`absolute left-0 top-1 w-2 h-2 rounded-full ${
                item.status === "completed" ? "bg-green-600"
                  : item.status === "failed" ? "bg-red-600"
                  : "bg-gray-500"
              }`}
            />
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs text-os-text font-medium">
                {String(item.node_name || `节点 ${i}`)}
              </span>
              <span className="rounded bg-os-elevated px-1.5 py-0.5 text-2xs text-os-subtle">
                {String(item.node_type || "")}
              </span>
              {item.duration_ms != null && (
                <span className="text-2xs text-os-subtle">
                  {Number(item.duration_ms).toFixed(0)}ms
                </span>
              )}
            </div>
            {item.output_summary != null && (
              <p className="mt-0.5 line-clamp-1 text-2xs text-os-subtle">{String(item.output_summary)}</p>
            )}
            {item.error != null && (
              <span className="mt-0.5 block text-2xs text-red-700">{String(item.error)}</span>
            )}
          </div>
        ))}
      </div>
    </details>
  );
}

function ResultCard({
  result,
  scenarioId,
  resp,
}: {
  result: Record<string, unknown>;
  scenarioId: string;
  resp?: ScenarioRunResponse;
}) {
  const isM2T = scenarioId === "meeting-to-training";
  const m2tResult = result as unknown as MeetingToTrainingResult;
  const daResult = result as unknown as DepartmentAssistantResult;
  const steps = (result.execution_steps as Record<string, unknown>[]) || [];
  const trace = resp?.trace || (result.execution_trace as Record<string, unknown>[]) || [];
  const wfExecId = result.workflow_execution_id as string | null;
  const fallback = Boolean(
    (result as Record<string, unknown>).fallback_mode ??
      (result as Record<string, unknown>).llm_available === false
  );

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).catch(() => {});
  };

  return (
    <div className="p-4 rounded-xl bg-os-surface border border-os-border shadow-os-sm space-y-3">
      {/* Status + IDs */}
      <div className="flex items-center gap-2 flex-wrap">
        {result.success ? (
          <CheckCircle2 className="w-5 h-5 text-green-700" />
        ) : (
          <XCircle className="w-5 h-5 text-red-700" />
        )}
        <span className={result.success ? "text-green-700 font-medium text-sm" : "text-red-700 font-medium text-sm"}>
          {result.success ? "工作流执行成功" : "执行失败"}
        </span>
        {result.error != null && (
          <span className="ml-auto max-w-[200px] truncate text-xs text-red-700">{String(result.error)}</span>
        )}
      </div>

      {/* WF Execution ID */}
      {wfExecId && (
        <div className="flex items-center gap-2 rounded bg-os-elevated px-2 py-1 text-xs text-os-subtle">
          <GitBranch size={11} className="text-os-muted" />
          <code className="text-os-subtle font-mono text-2xs truncate flex-1">{wfExecId}</code>
          <button
            onClick={() => copyToClipboard(wfExecId)}
            className="text-os-muted hover:text-os-subtle transition-colors"
            title="复制"
          >
            <Copy size={11} />
          </button>
          <span className="text-2xs text-os-subtle">
            {fallback ? "确定性引擎 · 可追溯" : "工作流引擎（WorkflowEngine）· 可追溯"}
          </span>
        </div>
      )}

      {/* Metrics */}
      <MetricsBar
        duration_ms={typeof result.duration_ms === "number" ? (result.duration_ms as number) : undefined}
        memory_refs={result.memory_refs as unknown[]}
        knowledge_refs={result.knowledge_refs as unknown[]}
        fallback_mode={fallback}
        steps_count={steps.length}
      />

      {/* Fallback notice */}
      {fallback && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
          <Zap size={12} className="mt-0.5 shrink-0" />
          <span>当前使用确定性规则引擎（LLM 离线回退模式，fallback）。结果可复现、可审计，但深度推理能力受限。</span>
        </div>
      )}

      {/* Execution Timeline — 演示重点 */}
      <ExecutionTimeline steps={steps} />

      {/* M2T business results */}
      {isM2T && m2tResult && (
        <div className="space-y-2 text-sm border-t border-os-border pt-3">
          {m2tResult.summary && (
            <details open>
              <summary className="text-os-subtle cursor-pointer hover:text-os-text text-xs font-medium">会议摘要</summary>
              <p className="mt-1 text-os-text whitespace-pre-wrap text-xs max-h-40 overflow-y-auto leading-relaxed">{m2tResult.summary}</p>
            </details>
          )}
          {m2tResult.decisions?.length > 0 && (
            <details>
              <summary className="text-os-subtle cursor-pointer hover:text-os-text text-xs font-medium">
                决策要点 ({m2tResult.decisions.length})
              </summary>
              <ul className="mt-1 list-disc pl-5 text-os-text text-xs space-y-0.5">
                {m2tResult.decisions.map((d, i) => <li key={i}>{d}</li>)}
              </ul>
            </details>
          )}
          {m2tResult.action_items?.length > 0 && (
            <details open>
              <summary className="text-os-subtle cursor-pointer hover:text-os-text text-xs font-medium">
                行动项 ({m2tResult.action_items.length})
              </summary>
              <ul className="mt-1 list-disc pl-5 text-os-text text-xs space-y-0.5">
                {m2tResult.action_items.map((a, i) => <li key={i}>{a}</li>)}
              </ul>
            </details>
          )}
          {m2tResult.knowledge_entries?.length > 0 && (
            <details>
              <summary className="text-os-subtle cursor-pointer hover:text-os-text text-xs font-medium">
                知识条目 ({m2tResult.knowledge_entries.length})
              </summary>
              <ul className="mt-1 list-disc pl-5 text-os-text text-xs space-y-0.5">
                {m2tResult.knowledge_entries.map((k, i) => <li key={i}>{k.content}</li>)}
              </ul>
            </details>
          )}
          {m2tResult.training_outline?.length > 0 && (
            <details>
              <summary className="text-os-subtle cursor-pointer hover:text-os-text text-xs font-medium">
                培训大纲 ({m2tResult.training_outline.length})
              </summary>
              <ol className="mt-1 list-decimal pl-5 text-os-text text-xs space-y-0.5">
                {m2tResult.training_outline.map((t, i) => <li key={i}>{t}</li>)}
              </ol>
            </details>
          )}
          {m2tResult.training_qa?.length > 0 && (
            <details>
              <summary className="text-os-subtle cursor-pointer hover:text-os-text text-xs font-medium">
                练习QA ({m2tResult.training_qa.length})
              </summary>
              <ul className="mt-1 list-disc pl-5 text-os-text text-xs space-y-0.5">
                {m2tResult.training_qa.map((q, i) => <li key={i}>{q}</li>)}
              </ul>
            </details>
          )}
          {m2tResult.entity_suggestions?.length > 0 && (
            <details>
              <summary className="text-os-subtle cursor-pointer hover:text-os-text text-xs font-medium">
                实体建议 ({m2tResult.entity_suggestions.length})
              </summary>
              <div className="mt-1 flex flex-wrap gap-1">
                {m2tResult.entity_suggestions.map((e, i) => (
                  <span key={i} className="text-2xs px-2 py-0.5 rounded bg-os-elevated text-os-subtle border border-os-border">
                    {e.name} <span className="text-os-subtle">[{e.entity_type}]</span>
                  </span>
                ))}
              </div>
            </details>
          )}
        </div>
      )}

      {/* DA business results */}
      {!isM2T && daResult && (
        <div className="space-y-2 text-sm border-t border-os-border pt-3">
          {daResult.answer && (
            <details open>
              <summary className="text-os-subtle cursor-pointer hover:text-os-text text-xs font-medium">分析结果</summary>
              <p className="mt-1 text-os-text whitespace-pre-wrap text-xs max-h-48 overflow-y-auto leading-relaxed">{daResult.answer}</p>
            </details>
          )}
          {daResult.reasoning_summary && (
            <details>
              <summary className="text-os-subtle cursor-pointer hover:text-os-text text-xs font-medium">推理依据</summary>
              <p className="mt-1 text-os-text text-xs">{daResult.reasoning_summary}</p>
            </details>
          )}
          {daResult.recommended_actions?.length > 0 && (
            <details open>
              <summary className="text-os-subtle cursor-pointer hover:text-os-text text-xs font-medium">
                建议行动 ({daResult.recommended_actions.length})
              </summary>
              <ul className="mt-1 list-disc pl-5 text-os-text text-xs space-y-0.5">
                {daResult.recommended_actions.map((a, i) => <li key={i}>{a}</li>)}
              </ul>
            </details>
          )}
          {typeof daResult.confidence === "number" && (
            <div className="flex items-center gap-3 text-xs flex-wrap">
              <span className="text-os-subtle">
                置信度: <span className="text-os-text-high font-medium">{(daResult.confidence * 100).toFixed(0)}%</span>
              </span>
              {daResult.confidence_reason && (
                <span className="text-os-subtle">({daResult.confidence_reason})</span>
              )}
            </div>
          )}
          {(typeof daResult.related_memory_count === "number" || typeof daResult.related_entity_count === "number") && (
            <div className="text-xs text-os-subtle">
              关联记忆 {daResult.related_memory_count ?? 0} 条 | 关联实体 {daResult.related_entity_count ?? 0} 个
            </div>
          )}
          {daResult.limitations?.length > 0 && (
            <details>
              <summary className="cursor-pointer text-xs text-os-subtle hover:text-os-text-high">局限性</summary>
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs text-os-subtle">
                {daResult.limitations.map((l, i) => <li key={i}>{l}</li>)}
              </ul>
            </details>
          )}
        </div>
      )}

      {/* Agent Trace */}
      {trace.length > 0 && (
        <details className="border-t border-os-border pt-3">
          <summary className="flex cursor-pointer items-center gap-1 text-xs text-os-subtle hover:text-os-text-high">
            <Layers size={12} />
            智能体追踪（Agent Trace）· {trace.length} 条 PEOR 记录
          </summary>
          <div className="mt-2 space-y-1 max-h-48 overflow-y-auto">
            {trace.map((t, i) => (
              <div key={i} className="border-l border-os-border pl-4 text-xs text-os-subtle">
                <span className="text-os-subtle">[{String(t.phase || t.node_type || "步骤")}]</span>{" "}
                {String(t.detail || t.node_name || t.output_summary || "").slice(0, 120)}
                {t.duration_ms != null && <span className="ml-2 text-os-subtle">{Number(t.duration_ms).toFixed(0)}ms</span>}
              </div>
            ))}
          </div>
        </details>
      )}

      {/* Empty trace */}
      {trace.length === 0 && steps.length === 0 && !result.success && (
        <div className="py-2 text-center text-xs text-os-subtle">
          无执行记录
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════
// Page
// ═══════════════════════════════════════════

export default function ScenariosPage() {
  const [scenarios, setScenarios] = useState<ScenarioDefinition[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [executing, setExecuting] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, { result: Record<string, unknown>; resp?: ScenarioRunResponse }>>({});
  const [m2tInput, setM2tInput] = useState({ meeting_title: "", meeting_notes: "", participants: "" });
  const [daInput, setDaInput] = useState({ department: "", question: "", context: "" });

  const fetchScenarios = useCallback(async () => {
    try {
      setLoading(true);
      setScenarios(await listScenarios());
      setError(null);
    } catch (e: unknown) {
      if (e instanceof Error && e.message?.includes("401")) {
        setError("请先登录以访问内部智能体中心。所有 API 端点需要有效 JWT Token。");
      } else if (e instanceof Error && e.message?.includes("403")) {
        setError("权限不足。当前账号没有执行该操作的权限，请联系管理员。");
      } else {
        setError(e instanceof Error ? e.message : "加载场景失败，请确认后端已启动");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchScenarios();
  }, [fetchScenarios]);

  const handleRun = useCallback(async (scenarioId: string) => {
    setExecuting(scenarioId);
    setResults((prev) => ({ ...prev, [scenarioId]: { result: {} as Record<string, unknown> } }));
    try {
      let resp: ScenarioRunResponse;
      if (scenarioId === "meeting-to-training") {
        resp = await runMeetingToTraining({
          meeting_title: m2tInput.meeting_title || "测试会议",
          meeting_notes: m2tInput.meeting_notes || "讨论项目进展。",
          participants: m2tInput.participants ? m2tInput.participants.split(",").map((s) => s.trim()).filter(Boolean) : [],
        });
      } else {
        const deptMap: Record<string, string> = { engineering: "研发部", product: "产品部", operations: "运营部", sales: "销售部", hr: "人力资源部", support: "客服部" };
        resp = await runDepartmentAssistant({
          department: deptMap[daInput.department] || daInput.department || "研发部",
          question: daInput.question || "当前项目的主要风险有哪些？",
          context: daInput.context || "",
        });
      }
      setResults((prev) => ({ ...prev, [scenarioId]: { result: resp.result, resp } }));
    } catch (e: unknown) {
      setResults((prev) => ({
        ...prev,
        [scenarioId]: { result: { success: false, error: e instanceof Error ? e.message : "执行失败" } },
      }));
    } finally {
      setExecuting(null);
    }
  }, [m2tInput, daInput]);

  // Demo input handlers
  const handleDemoM2T = useCallback((index: number) => {
    const d = DEMO_MEETINGS[index] || DEMO_MEETINGS[0];
    setM2tInput({ meeting_title: d.meeting_title, meeting_notes: d.meeting_notes, participants: "" });
  }, []);

  const handleDemoDA = useCallback((index: number | string) => {
    if (typeof index === "string") {
      // Legacy single-demo call
      setDaInput({ department: "engineering", question: DEMO_QUESTIONS[0].question, context: "" });
      return;
    }
    const d = DEMO_QUESTIONS[index] || DEMO_QUESTIONS[0];
    setDaInput({ department: d.department, question: d.question, context: "" });
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="w-8 h-8 animate-spin text-blue-700" />
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-2">
          <div>
            <h1 className="text-3xl font-bold text-os-text-high mb-1">业务场景</h1>
            <p className="text-os-subtle text-sm max-w-xl">
              用企业级 AI 智能体（Agent）将会议、知识、部门问题转化为可追踪、可审计的组织行动。
            </p>
          </div>
          <button onClick={() => void fetchScenarios()} className="p-2 rounded-lg hover:bg-os-elevated transition-colors">
            <RefreshCw className="w-5 h-5 text-os-subtle" />
          </button>
        </div>
        <p className="text-xs text-os-subtle">
          内部智能体中心 · 每一次智能体（Agent）执行都有工作流执行（WorkflowExecution）记录 · 追踪、指标与步骤（Trace / Metrics / Steps）让组织智能体可解释、可审计
        </p>
      </div>

      {/* Capability cards */}
      <CapabilityCards />

      {/* Demo status */}
      <DemoStatusBar />

      {/* Error */}
      {error && (
        <div className="mb-6 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          <XCircle size={16} className="mt-0.5 shrink-0" /> {error}
        </div>
      )}

      {/* Scenario cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        {scenarios.map((s) => (
          <div key={s.scenario_id}>
            <ScenarioCard
              scenario={s}
              onRun={() => handleRun(s.scenario_id)}
              onDemoInput={s.scenario_id === "meeting-to-training" ? handleDemoM2T : handleDemoDA}
              demoOptions={s.scenario_id === "meeting-to-training"
                ? DEMO_MEETINGS.map((d) => ({ label: d.label }))
                : DEMO_QUESTIONS.map((d) => ({ label: d.label }))}
              busy={executing === s.scenario_id}
            />
            <div className="mt-4 space-y-2">
              {s.scenario_id === "meeting-to-training" && (
                <>
                  <input type="text" placeholder="会议标题" value={m2tInput.meeting_title}
                    onChange={(e) => setM2tInput((p) => ({ ...p, meeting_title: e.target.value }))}
                    className="w-full px-3 py-2 rounded-lg bg-os-elevated border border-os-border text-os-text-high text-sm placeholder:text-os-subtle focus:outline-none focus:border-os-accent transition-colors" />
                  <textarea placeholder="会议记录内容…粘贴后运行即可" rows={4} value={m2tInput.meeting_notes}
                    onChange={(e) => setM2tInput((p) => ({ ...p, meeting_notes: e.target.value }))}
                    className="w-full px-3 py-2 rounded-lg bg-os-elevated border border-os-border text-os-text-high text-sm placeholder:text-os-subtle focus:outline-none focus:border-os-accent resize-none transition-colors" />
                </>
              )}
              {s.scenario_id === "department-assistant" && (
                <>
                  <select value={daInput.department}
                    onChange={(e) => setDaInput((p) => ({ ...p, department: e.target.value }))}
                    className="w-full px-3 py-2 rounded-lg bg-os-elevated border border-os-border text-os-text-high text-sm focus:outline-none focus:border-os-accent transition-colors">
                    <option value="">选择部门…部门智能体默认遵守知识边界</option>
                    <option value="engineering">研发部</option>
                    <option value="product">产品部</option>
                    <option value="operations">运营部</option>
                    <option value="sales">销售部</option>
                    <option value="hr">人力资源部</option>
                    <option value="support">客服部</option>
                  </select>
                  <input type="text" placeholder="输入业务问题…" value={daInput.question}
                    onChange={(e) => setDaInput((p) => ({ ...p, question: e.target.value }))}
                    className="w-full px-3 py-2 rounded-lg bg-os-elevated border border-os-border text-os-text-high text-sm placeholder:text-os-subtle focus:outline-none focus:border-os-accent transition-colors" />
                </>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Results */}
      {Object.keys(results).length > 0 && (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold text-os-text-high flex items-center gap-2">
            <Layers size={18} className="text-blue-700" />
            执行结果
            <span className="text-xs font-normal text-os-subtle">
              · 从知识沉淀到行动执行
            </span>
          </h2>
          {Object.entries(results).map(([sceneId, { result, resp }]) => (
            <ResultCard key={sceneId} result={result} scenarioId={sceneId} resp={resp} />
          ))}
        </div>
      )}

      {/* Empty state */}
      {scenarios.length === 0 && !loading && !error && (
        <div className="py-12 text-center">
          <Beaker className="mx-auto mb-4 h-12 w-12 text-slate-500" />
          <p className="text-os-text-high">暂无可用业务场景</p>
          <p className="mt-1 text-xs text-os-subtle">当前尚未配置可用业务场景，请配置后刷新重试。</p>
        </div>
      )}
    </div>
  );
}
