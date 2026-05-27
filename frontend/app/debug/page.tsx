"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Search, Brain, Layers, Clock, AlertCircle, Zap,
  Activity, Eye, Hash, BarChart3, ChevronRight,
} from "lucide-react";
import { api } from "@/services/api";
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
  "memory.created": { label: "记忆创建", color: "bg-emerald-400/10 text-emerald-400 border-emerald-400/20" },
  "memory.merged": { label: "记忆合并", color: "bg-amber-400/10 text-amber-400 border-amber-400/20" },
  "memory.accessed": { label: "记忆访问", color: "bg-blue-400/10 text-blue-400 border-blue-400/20" },
  "recall.executed": { label: "检索执行", color: "bg-purple-400/10 text-purple-400 border-purple-400/20" },
  "reflection.run": { label: "反思运行", color: "bg-indigo-400/10 text-indigo-400 border-indigo-400/20" },
  "reflection.insight": { label: "反思洞察", color: "bg-indigo-400/10 text-indigo-400 border-indigo-400/20" },
  "reflection.skipped": { label: "反思跳过", color: "bg-rose-400/10 text-rose-400 border-rose-400/20" },
  "agent.start": { label: "Agent 启动", color: "bg-cyan-400/10 text-cyan-400 border-cyan-400/20" },
  "agent.done": { label: "Agent 完成", color: "bg-cyan-400/10 text-cyan-400 border-cyan-400/20" },
  "tool.call_start": { label: "工具调用", color: "bg-slate-400/10 text-slate-400 border-slate-400/20" },
  "tool.call_done": { label: "工具完成", color: "bg-slate-400/10 text-slate-400 border-slate-400/20" },
};

const sourceLabel: Record<string, string> = { user: "用户", agent: "Agent", reflect: "反思" };

const typeLabel: Record<string, string> = {
  episodic: "情景", semantic: "语义", procedural: "程序", reflect: "反思",
};

// ── Tabs ──

type Tab = "memory" | "retrieve" | "events";
const tabs: { key: Tab; label: string; icon: React.ReactNode }[] = [
  { key: "memory", label: "Memory Explorer", icon: <Brain size={14} /> },
  { key: "retrieve", label: "Retrieval Inspector", icon: <Search size={14} /> },
  { key: "events", label: "Event Timeline", icon: <Activity size={14} /> },
];

// ── Components ──

function MemoryExplorer() {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");

  const { data: memories = [], isLoading } = useQuery({
    queryKey: ["debug-memory", query],
    queryFn: () =>
      fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"}/memory?q=${encodeURIComponent(query)}&limit=50`
      ).then((r) => r.json()),
    refetchInterval: 15000,
  });

  const filtered = (memories || []).filter((m: MemoryItem) =>
    filter === "all" ? true : m.memory_type === filter
  );

  const stats = {
    total: memories.length,
    vectorized: memories.filter((m: MemoryItem) => m.embedding_status === "vectorized").length,
    missing: memories.filter((m: MemoryItem) => m.embedding_status === "missing").length,
  };

  return (
    <div className="flex flex-col gap-4">
      {/* Stats bar */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: "总记忆", value: stats.total, icon: <Brain size={12} /> },
          { label: "已向量化", value: stats.vectorized, icon: <Zap size={12} />, good: true },
          { label: "向量缺失", value: stats.missing, icon: <AlertCircle size={12} />, good: false },
          { label: "类型", value: [...new Set((memories || []).map((m: MemoryItem) => typeLabel[m.memory_type] || m.memory_type))].length, icon: <Layers size={12} /> },
        ].map((s, i) => (
          <div key={i} className="os-card p-3 flex items-center gap-2.5">
            <span className="text-os-muted">{s.icon}</span>
            <div>
              <p className="text-2xs text-os-muted">{s.label}</p>
              <p className={cn("text-sm font-mono font-medium", s.good === true ? "text-emerald-400" : s.good === false ? "text-rose-400" : "text-os-text-high")}>{s.value}</p>
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
            className="flex-1 bg-transparent text-sm text-os-text-high outline-none placeholder:text-os-muted"
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
        <p className="text-sm text-os-muted py-8 text-center">加载中...</p>
      ) : filtered.length === 0 ? (
        <p className="text-sm text-os-muted py-8 text-center">暂无记忆数据</p>
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
                    m.source === "user" && "bg-indigo-400/10 text-indigo-400",
                    m.source === "reflect" && "bg-amber-400/10 text-amber-400",
                    m.source === "agent" && "bg-emerald-400/10 text-emerald-400",
                  )}>{sourceLabel[m.source] || m.source}</span>
                  <span className="text-2xs text-os-muted">{typeLabel[m.memory_type] || m.memory_type}</span>
                  <span className={cn("text-2xs font-mono",
                    m.importance >= 7 ? "text-amber-400" : m.importance >= 5 ? "text-os-subtle" : "text-os-muted"
                  )}>权重 {m.importance}</span>
                </div>
                <div className="flex items-center gap-2">
                  {m.embedding_status === "vectorized" ? (
                    <span className="flex items-center gap-1 text-2xs text-emerald-400"><Zap size={10} />已向量化</span>
                  ) : (
                    <span className="flex items-center gap-1 text-2xs text-rose-400"><AlertCircle size={10} />向量缺失</span>
                  )}
                  <span className="text-2xs text-os-muted flex items-center gap-1"><Eye size={10} />{m.access_count}</span>
                </div>
              </div>
              <p className="text-sm text-os-text-high leading-relaxed line-clamp-2">
                {m.summary || m.content}
              </p>
              <div className="flex items-center gap-2 text-2xs text-os-muted">
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
  const [topK, setTopK] = useState(5);

  const handleSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"}/debug/retrieve?q=${encodeURIComponent(query)}&top_k=${topK}`
      );
      const data = await res.json();
      setResults(data);
    } catch { /* ignore */ }
    setLoading(false);
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
            className="flex-1 bg-transparent text-sm text-os-text-high outline-none placeholder:text-os-muted"
          />
        </div>
        <select
          value={topK}
          onChange={(e) => setTopK(Number(e.target.value))}
          className="os-card px-3 py-2 text-sm text-os-subtle bg-transparent outline-none"
        >
          {[3, 5, 10, 20].map((k) => (
            <option key={k} value={k}>Top {k}</option>
          ))}
        </select>
        <button
          onClick={handleSearch}
          className="os-card px-4 py-2 text-sm text-os-text-high font-medium hover:bg-os-elevated transition-colors"
        >
          {loading ? "搜索中..." : "查询"}
        </button>
      </div>

      {results.length === 0 ? (
        <p className="text-sm text-os-muted py-8 text-center">
          输入查询并点击"查询"来查看检索管线的分步评分
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
                  <span className="font-mono text-xs text-os-muted">#{i + 1}</span>
                  <span className={cn("px-1.5 py-0.5 rounded text-2xs font-medium",
                    hit.source === "user" && "bg-indigo-400/10 text-indigo-400",
                    hit.source === "reflect" && "bg-amber-400/10 text-amber-400",
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
                      <span className="text-2xs text-os-muted mt-0.5">{seg.label}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex items-center gap-4 text-2xs text-os-muted">
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
  const { data: events = [], isLoading, refetch } = useQuery({
    queryKey: ["debug-events"],
    queryFn: () =>
      fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"}/debug/events?limit=100`
      ).then((r) => r.json()),
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

      {events.length === 0 ? (
        <p className="text-sm text-os-muted py-8 text-center">
          暂无事件。尝试与 Agent 对话或在 Memory Explorer 中操作以生成事件。
        </p>
      ) : (
        <div className="relative">
          {/* Timeline line */}
          <div className="absolute left-3 top-0 bottom-0 w-px bg-os-border" />

          <div className="flex flex-col gap-1">
            {events.map((e: EventEntry, i: number) => {
              const info = eventLabels[e.type] || { label: e.type, color: "bg-slate-400/10 text-slate-400 border-slate-400/20" };
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
                    <span className="text-2xs font-mono text-os-muted min-w-[60px]">
                      {e.timestamp.slice(11, 19)}
                    </span>
                    <span className="font-medium">{info.label}</span>
                    {e.data && Object.keys(e.data).length > 0 && (
                      <span className="text-2xs text-os-muted truncate max-w-[200px]">
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
          <h1 className="text-lg font-semibold text-os-text-high">Debug Console</h1>
          <p className="text-sm text-os-muted mt-1">Memory lifecycle observability & inspector</p>
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
                  : "text-os-muted hover:text-os-subtle"
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