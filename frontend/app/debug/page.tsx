"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Search, Brain, Layers, Clock, AlertCircle, Zap,
  Activity, Eye, Hash, BarChart3, ChevronRight,
} from "lucide-react";
import { api, apiFetch } from "@/services/api";
import { PageTransition } from "@/components/animations/page-transition";
import { cn, formatDate } from "@/lib/utils";

// ── Types ──

interface MemoryItem {
  id: string;
  content: string;
  summary: string | null;
  source: string;
  timestamp: string;
  importance: number;
  entities: string[];
  memory_type: string;
  access_count: number;
  embedding_status: "vectorized" | "missing";
}

interface RetrieveHit {
  memory_id: string;
  content: string;
  source: string;
  importance: number;
  rrf_score: number;
  time_factor: number;
  importance_factor: number;
  access_bonus: number;
  final_score: number;
  timestamp: string;
}

interface EventEntry {
  id: string;
  type: string;
  timestamp: string;
  data: Record<string, unknown>;
}

// ── Labels ──

const eventLabels: Record<string, { label: string; color: string }> = {
  "memory.created": { label: "记忆创建", color: "bg-os-success-soft text-os-success border-os-success/20" },
  "memory.merged": { label: "记忆合并", color: "bg-os-warning-soft text-os-warning border-os-warning/20" },
  "memory.accessed": { label: "记忆访问", color: "bg-os-info-soft text-os-info border-os-info/20" },
  "recall.executed": { label: "检索执行", color: "bg-os-primary-soft text-os-primary border-os-primary/20" },
  "reflection.run": { label: "反思运行", color: "bg-os-primary-soft text-os-primary border-os-primary/20" },
  "reflection.insight": { label: "反思洞察", color: "bg-os-primary-soft text-os-primary border-os-primary/20" },
  "reflection.skipped": { label: "反思跳过", color: "bg-os-danger-soft text-os-danger border-os-danger/20" },
  "agent.start": { label: "智能体启动", color: "bg-os-info-soft text-os-info border-os-info/20" },
  "agent.done": { label: "智能体完成", color: "bg-os-info-soft text-os-info border-os-info/20" },
  "tool.call_start": { label: "工具调用", color: "bg-os-surface-muted text-os-subtle border-os-border" },
  "tool.call_done": { label: "工具完成", color: "bg-os-surface-muted text-os-subtle border-os-border" },
};

const sourceLabel: Record<string, string> = { user: "用户", agent: "智能体", reflect: "反思" };

const typeLabel: Record<string, string> = {
  episodic: "情景", semantic: "语义", procedural: "程序", reflect: "反思",
};

// ── Tabs ──

type Tab = "memory" | "retrieve" | "events";
const tabs: { key: Tab; label: string; icon: React.ReactNode }[] = [
  { key: "memory", label: "记忆浏览器", icon: <Brain size={14} /> },
  { key: "retrieve", label: "检索分析", icon: <Search size={14} /> },
  { key: "events", label: "事件时间线", icon: <Activity size={14} /> },
];

// ── Components ──

function MemoryExplorer() {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");

  const { data: raw, isLoading, isError } = useQuery({
    queryKey: ["debug-memory", query],
    queryFn: () => api.memory.list({ q: query, limit: 50 }),
    refetchInterval: 15000,
  });

  // 防御：确保 memories 始终是数组（API 可能返回对象/null/undefined）
  // Memory.embedding_status is a broader string locally; cast to MemoryItem[]
  // whose literal union ("vectorized" | "missing") drives the UI badges below.
  const memories: MemoryItem[] = Array.isArray(raw) ? (raw as MemoryItem[]) : [];

  // 按 memory_type 过滤
  const filtered = memories.filter((m) =>
    filter === "all" ? true : m.memory_type === filter
  );

  // 统计（memories 已保证是数组，filter 调用安全）
  const stats = {
    total: memories.length,
    vectorized: memories.filter((m) => m.embedding_status === "vectorized").length,
    missing: memories.filter((m) => m.embedding_status === "missing").length,
  };

  return (
    <div className="flex flex-col gap-4">
      {/* Stats bar */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        {[
          { label: "总记忆", value: stats.total, icon: <Brain size={12} /> },
          { label: "已向量化", value: stats.vectorized, icon: <Zap size={12} />, good: true },
          { label: "向量缺失", value: stats.missing, icon: <AlertCircle size={12} />, good: false },
          { label: "类型", value: [...new Set(memories.map((m) => typeLabel[m.memory_type] || m.memory_type))].length, icon: <Layers size={12} /> },
        ].map((s, i) => (
          <div key={i} className="os-card p-3 flex items-center gap-2.5">
            <span className="text-os-muted">{s.icon}</span>
            <div>
              <p className="text-2xs text-os-subtle">{s.label}</p>
              <p className={cn("text-sm font-mono font-medium", s.good === true ? "text-os-success" : s.good === false ? "text-os-danger" : "text-os-text-high")}>{s.value}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="flex items-center gap-2">
        <div className="os-card flex-1 flex items-center gap-2 px-3 py-2">
          <Search size={14} className="text-os-muted" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索记忆内容或实体..."
            className="flex-1 bg-transparent text-sm text-os-text-high outline-none placeholder:text-os-subtle"
          />
        </div>
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="os-card px-3 py-2 text-sm text-os-subtle bg-transparent outline-none"
        >
          <option value="all">全部类型</option>
          <option value="episodic">情景记忆</option>
          <option value="semantic">语义记忆</option>
          <option value="reflect">反思洞察</option>
        </select>
      </div>

      {/* Memory list */}
      {isLoading ? (
        <p className="text-sm text-os-subtle py-8 text-center">加载中...</p>
      ) : isError ? (
        <p className="text-sm text-os-danger py-8 text-center">记忆数据加载失败，请稍后重试</p>
      ) : filtered.length === 0 ? (
        <p className="text-sm text-os-subtle py-8 text-center">暂无记忆数据</p>
      ) : (
        <div className="flex flex-col gap-2">
          {filtered.map((m: MemoryItem) => (
            <motion.div
              key={m.id}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="os-card p-3 flex flex-col gap-2"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className={cn("px-1.5 py-0.5 rounded text-2xs font-medium",
                    m.source === "user" && "bg-os-primary-soft text-os-primary",
                    m.source === "reflect" && "bg-os-warning-soft text-os-warning",
                    m.source === "agent" && "bg-os-success-soft text-os-success",
                  )}>{sourceLabel[m.source] || m.source}</span>
                  <span className="text-2xs text-os-subtle">{typeLabel[m.memory_type] || m.memory_type}</span>
                  <span className={cn("text-2xs font-mono",
                    m.importance >= 7 ? "text-os-warning" : "text-os-subtle"
                  )}>权重 {m.importance}</span>
                </div>
                <div className="flex items-center gap-2">
                  {m.embedding_status === "vectorized" ? (
                    <span className="flex items-center gap-1 text-2xs text-os-success"><Zap size={10} />已向量化</span>
                  ) : (
                    <span className="flex items-center gap-1 text-2xs text-os-danger"><AlertCircle size={10} />向量缺失</span>
                  )}
                  <span className="text-2xs text-os-subtle flex items-center gap-1"><Eye size={10} />{m.access_count}</span>
                </div>
              </div>
              <p className="text-sm text-os-text-high leading-relaxed line-clamp-2">
                {m.summary || m.content}
              </p>
              <div className="flex items-center gap-2 text-2xs text-os-subtle">
                <Clock size={10} /> {formatDate(m.timestamp)}
                {m.entities.length > 0 && (
                  <span className="flex items-center gap-1">
                    <Hash size={10} /> {m.entities.slice(0, 3).join(", ")}
                    {m.entities.length > 3 && ` +${m.entities.length - 3}`}
                  </span>
                )}
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}

function RetrievalInspector() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<RetrieveHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [topK, setTopK] = useState(5);

  const handleSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setSearchError("");
    try {
      const data = await apiFetch<RetrieveHit[]>(
        `/debug/retrieve?q=${encodeURIComponent(query)}&top_k=${topK}`
      );
      setResults(data);
    } catch {
      setResults([]);
      setSearchError("检索请求失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  };

  const maxScore = results.length > 0 ? Math.max(...results.map((r) => r.final_score)) : 1;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <div className="os-card flex-1 flex items-center gap-2 px-3 py-2">
          <Search size={14} className="text-os-muted" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            placeholder="输入查询以测试检索管线..."
            className="flex-1 bg-transparent text-sm text-os-text-high outline-none placeholder:text-os-subtle"
          />
        </div>
        <select
          value={topK}
          onChange={(e) => setTopK(Number(e.target.value))}
          className="os-card px-3 py-2 text-sm text-os-subtle bg-transparent outline-none"
        >
          {[3, 5, 10, 20].map((k) => (
            <option key={k} value={k}>前 {k} 条</option>
          ))}
        </select>
        <button
          onClick={handleSearch}
          className="os-card px-4 py-2 text-sm text-os-text-high font-medium hover:bg-os-elevated transition-colors"
        >
          {loading ? "搜索中..." : "查询"}
        </button>
      </div>

      {searchError ? (
        <p className="text-sm text-os-danger py-8 text-center">{searchError}</p>
      ) : results.length === 0 ? (
        <p className="text-sm text-os-subtle py-8 text-center">
          输入查询并点击 &ldquo;查询&rdquo; 来查看检索管线的分步评分
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          {results.map((hit, i) => (
            <motion.div
              key={hit.memory_id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              className="os-card p-3 flex flex-col gap-2"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-os-subtle">#{i + 1}</span>
                  <span className={cn("px-1.5 py-0.5 rounded text-2xs font-medium",
                    hit.source === "user" && "bg-os-primary-soft text-os-primary",
                    hit.source === "reflect" && "bg-os-warning-soft text-os-warning",
                  )}>{sourceLabel[hit.source] || hit.source}</span>
                </div>
                <span className="text-sm font-mono font-bold text-os-text-high">
                  {hit.final_score.toFixed(4)}
                </span>
              </div>

              <p className="text-sm text-os-text-high line-clamp-2">{hit.content}</p>

              {/* Score breakdown bar */}
              <div className="flex items-center gap-1.5">
                <BarChart3 size={11} className="text-os-muted" />
                <div className="flex-1 flex gap-1 h-5">
                  {[
                    { label: "RRF", value: hit.rrf_score, max: 0.15, color: "bg-purple-400/60" },
                    { label: "时间", value: hit.time_factor, max: 1, color: "bg-blue-400/60" },
                    { label: "重要性", value: hit.importance_factor, max: 1, color: "bg-amber-400/60" },
                    { label: "访问", value: hit.access_bonus, max: 0.3, color: "bg-emerald-400/60" },
                  ].map((seg) => (
                    <div key={seg.label} className="flex-1 flex flex-col justify-end">
                      <div className="flex-1 rounded-sm" style={{
                        width: `${Math.min((seg.value / seg.max) * 100, 100)}%`,
                        minHeight: "100%",
                      }}>
                        <div className={`h-full rounded-sm ${seg.color}`} />
                      </div>
                      <span className="text-2xs text-os-subtle mt-0.5">{seg.label}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex items-center gap-4 text-2xs text-os-subtle">
                <span className="flex items-center gap-1"><Clock size={9} />{formatDate(hit.timestamp)}</span>
                <span>重要性 {hit.importance}/10</span>
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}

function EventTimeline() {
  const { data: events = [], isLoading, isError, refetch } = useQuery({
    queryKey: ["debug-events"],
    queryFn: () => apiFetch<EventEntry[]>(`/debug/events?limit=100`),
    refetchInterval: 10000,
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <span className="text-sm text-os-subtle">
          最近 {events.length} 条系统事件
        </span>
        <button onClick={() => refetch()} className="os-card px-3 py-1.5 text-xs text-os-subtle hover:text-os-text-high transition-colors">
          刷新
        </button>
      </div>

      {isLoading ? (
        <p className="text-sm text-os-subtle py-8 text-center">正在加载系统事件...</p>
      ) : isError ? (
        <p className="text-sm text-os-danger py-8 text-center">系统事件加载失败，请稍后重试</p>
      ) : events.length === 0 ? (
        <p className="text-sm text-os-subtle py-8 text-center">
          暂无事件。尝试与智能体对话或在记忆浏览器中操作以生成事件。
        </p>
      ) : (
        <div className="relative">
          {/* Timeline line */}
          <div className="absolute left-3 top-0 bottom-0 w-px bg-os-border" />

          <div className="flex flex-col gap-1">
            {events.map((e: EventEntry, i: number) => {
              const info = eventLabels[e.type] || { label: e.type, color: "bg-os-surface-muted text-os-subtle border-os-border" };
              return (
                <motion.div
                  key={e.id}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.02 }}
                  className="ml-8 relative"
                >
                  {/* Dot on timeline */}
                  <div className="absolute -left-5 top-2 w-2 h-2 rounded-full bg-os-border border-2 border-os-base" />
                  <div className={cn("os-card p-2 text-xs flex items-center gap-2", info.color, "border")}>
                    <span className="text-2xs font-mono text-os-subtle min-w-[60px]">
                      {e.timestamp.slice(11, 19)}
                    </span>
                    <span className="font-medium">{info.label}</span>
                    {e.data && Object.keys(e.data).length > 0 && (
                      <span className="text-2xs text-os-subtle truncate max-w-[200px]">
                        {Object.entries(e.data).map(([k, v]) => `${k}=${v}`).join(", ")}
                      </span>
                    )}
                  </div>
                </motion.div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Page ──

export default function DebugConsolePage() {
  const [activeTab, setActiveTab] = useState<Tab>("memory");

  return (
    <PageTransition>
      <div className="max-w-5xl mx-auto px-6 py-8 flex flex-col gap-6">
        <div>
          <h1 className="text-lg font-semibold text-os-text-high">调试控制台</h1>
          <p className="text-sm text-os-subtle mt-1">记忆生命周期可观测与诊断</p>
        </div>

        {/* Tabs */}
        <div className="flex items-center gap-1 os-card p-1 rounded-lg">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors",
                activeTab === tab.key
                  ? "bg-os-elevated text-os-text-high shadow-sm"
                  : "text-os-subtle hover:text-os-text"
              )}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        {activeTab === "memory" && <MemoryExplorer />}
        {activeTab === "retrieve" && <RetrievalInspector />}
        {activeTab === "events" && <EventTimeline />}
      </div>
    </PageTransition>
  );
}
