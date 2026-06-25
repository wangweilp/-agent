"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search, Loader2, Brain, Target, Clock, TrendingUp, Zap,
  Database, ChevronRight, Hash, Cpu,
} from "lucide-react";
import { cn, formatDate, importanceColor } from "@/lib/utils";
import { api } from "@/services/api";
import type { RetrieveHit } from "@/types";

export function VectorInspector() {
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(10);
  const [submittedQuery, setSubmittedQuery] = useState("");

  // 检索执行
  const { data: hits, isLoading, isFetching } = useQuery({
    queryKey: ["memory-console-retrieve", submittedQuery, topK],
    queryFn: () => api.debug.retrieve({ q: submittedQuery, top_k: topK }),
    enabled: submittedQuery.length > 0,
    refetchInterval: false,
  });

  const results: RetrieveHit[] = hits || [];

  const handleSearch = () => {
    if (query.trim()) {
      setSubmittedQuery(query.trim());
    }
  };

  return (
    <div className="space-y-4">
      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Search size={14} className="text-violet-400" />
          <h2 className="text-sm font-semibold text-os-text-high">向量检索探针</h2>
          <span className="text-2xs text-os-muted">query → embedding → result ranking</span>
        </div>
      </div>

      {/* ── 检索输入 ── */}
      <div className="rounded-md border border-os-border bg-os-surface/30 p-4 space-y-3">
        <div className="flex items-center gap-2">
          <div className="flex-1 flex items-center gap-2 h-9 px-3 rounded-md border border-os-border bg-os-base focus-within:border-violet-400/50 transition-colors">
            <Search size={13} className="text-os-muted" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              placeholder="输入查询文本，探针将展示 RRF 融合排序的完整评分链路..."
              className="flex-1 bg-transparent text-xs text-os-text placeholder:text-os-muted focus:outline-none"
            />
          </div>
          <div className="flex items-center gap-1.5">
            <label className="text-2xs text-os-muted">top_k</label>
            <input
              type="number"
              value={topK}
              onChange={(e) => setTopK(Math.max(1, Math.min(50, Number(e.target.value))))}
              className="w-16 h-9 px-2 rounded-md border border-os-border bg-os-base text-xs text-os-text font-mono focus:outline-none focus:border-violet-400/50"
            />
          </div>
          <button
            onClick={handleSearch}
            disabled={!query.trim() || isFetching}
            className={cn(
              "h-9 px-4 rounded-md flex items-center gap-1.5 text-xs font-medium transition-all",
              !query.trim() || isFetching
                ? "bg-os-elevated text-os-muted cursor-not-allowed"
                : "bg-violet-500/10 text-violet-300 border border-violet-400/30 hover:bg-violet-500/20 hover:border-violet-400/50",
            )}
          >
            {isFetching ? (
              <><Loader2 size={13} className="animate-spin" /> 检索中...</>
            ) : (
              <><Target size={13} /> 执行检索</>
            )}
          </button>
        </div>

        {/* 检索状态 */}
        {submittedQuery && (
          <div className="flex items-center gap-2 text-2xs text-os-muted">
            <Hash size={10} />
            <span className="font-mono">query: "{submittedQuery}"</span>
            <span>·</span>
            <span>{results.length} hits</span>
            <span>·</span>
            <span>top_k: {topK}</span>
          </div>
        )}
      </div>

      {/* ── 检索结果 ── */}
      {!submittedQuery ? (
        <div className="rounded-md border border-dashed border-os-border bg-os-surface/20 p-8 text-center">
          <Search size={24} className="mx-auto text-os-muted mb-2" />
          <p className="text-xs text-os-subtle">输入查询以探针检索</p>
          <p className="text-2xs text-os-muted mt-1">将展示 RRF 融合排序的完整评分链路</p>
        </div>
      ) : isLoading ? (
        <div className="rounded-md border border-os-border bg-os-surface/30 p-8 text-center">
          <Loader2 size={20} className="mx-auto text-violet-400 animate-spin mb-2" />
          <p className="text-2xs text-os-muted">正在生成 embedding 并检索...</p>
        </div>
      ) : results.length === 0 ? (
        <div className="rounded-md border border-os-border bg-os-surface/30 p-8 text-center">
          <Database size={20} className="mx-auto text-os-muted mb-2" />
          <p className="text-2xs text-os-muted">无检索结果</p>
        </div>
      ) : (
        <div className="space-y-3">
          {/* ── 评分链路说明 ── */}
          <div className="rounded-md border border-violet-400/20 bg-violet-400/[0.02] p-3">
            <div className="flex items-center gap-2 mb-2">
              <Cpu size={11} className="text-violet-400" />
              <span className="text-2xs font-medium text-violet-300 uppercase tracking-wider">RRF 评分链路</span>
            </div>
            <div className="flex items-center gap-1.5 text-2xs text-os-subtle flex-wrap">
              <ScoreFactor label="rrf_score" icon={<Hash size={9} />} color="violet" hint="融合分数" />
              <ChevronRight size={10} className="text-os-muted" />
              <ScoreFactor label="time_factor" icon={<Clock size={9} />} color="cyan" hint="时间衰减" />
              <ChevronRight size={10} className="text-os-muted" />
              <ScoreFactor label="importance_factor" icon={<TrendingUp size={9} />} color="emerald" hint="重要度权重" />
              <ChevronRight size={10} className="text-os-muted" />
              <ScoreFactor label="access_bonus" icon={<Zap size={9} />} color="amber" hint="访问加成" />
              <ChevronRight size={10} className="text-os-muted" />
              <ScoreFactor label="final_score" icon={<Target size={9} />} color="rose" hint="最终排序" />
            </div>
          </div>

          {/* ── 结果列表 ── */}
          <div className="space-y-2">
            <AnimatePresence mode="popLayout">
              {results.map((hit, idx) => (
                <motion.div
                  key={hit.memory_id}
                  layout
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{ delay: Math.min(idx * 0.03, 0.3) }}
                  className="rounded-md border border-os-border bg-os-surface/30 overflow-hidden"
                >
                  {/* 排名条 */}
                  <div className="flex">
                    <div className={cn(
                      "shrink-0 w-10 flex flex-col items-center justify-center border-r border-os-border/50",
                      idx === 0 ? "bg-violet-400/10" : "bg-os-elevated/30",
                    )}>
                      <span className={cn(
                        "text-sm font-bold tabular-nums",
                        idx === 0 ? "text-violet-400" : "text-os-muted",
                      )}>
                        #{idx + 1}
                      </span>
                    </div>

                    {/* 内容区 */}
                    <div className="flex-1 p-3 min-w-0">
                      {/* 内容 */}
                      <div className="flex items-start gap-2 mb-2">
                        <Brain size={11} className="text-os-muted mt-0.5 shrink-0" />
                        <p className="text-xs text-os-text leading-relaxed flex-1">
                          {hit.content}
                        </p>
                      </div>

                      {/* 元数据 */}
                      <div className="flex items-center gap-2 text-2xs text-os-muted mb-2 flex-wrap">
                        <span className="font-mono text-os-subtle">{hit.memory_id.slice(0, 8)}</span>
                        <span>·</span>
                        <span className="px-1 py-0.5 rounded bg-os-elevated">{hit.source}</span>
                        <span>·</span>
                        <span className={cn("font-mono", importanceColor(hit.importance))}>
                          imp: {hit.importance}
                        </span>
                        <span>·</span>
                        <span>{formatDate(hit.timestamp)}</span>
                      </div>

                      {/* 评分链路可视化 */}
                      <ScoreBreakdown hit={hit} />
                    </div>

                    {/* 最终分数 */}
                    <div className="shrink-0 w-20 flex flex-col items-center justify-center border-l border-os-border/50 bg-os-base/50">
                      <span className="text-2xs text-os-muted">final</span>
                      <span className={cn(
                        "text-base font-bold tabular-nums",
                        idx === 0 ? "text-violet-400" : "text-os-text-high",
                      )}>
                        {hit.final_score.toFixed(4)}
                      </span>
                    </div>
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </div>
      )}
    </div>
  );
}

// ── 评分因子标签 ──

function ScoreFactor({
  label, icon, color, hint,
}: {
  label: string;
  icon: React.ReactNode;
  color: "violet" | "cyan" | "emerald" | "amber" | "rose";
  hint: string;
}) {
  const colorMap = {
    violet: "bg-violet-400/10 text-violet-400 border-violet-400/20",
    cyan: "bg-cyan-400/10 text-cyan-400 border-cyan-400/20",
    emerald: "bg-emerald-400/10 text-emerald-400 border-emerald-400/20",
    amber: "bg-amber-400/10 text-amber-400 border-amber-400/20",
    rose: "bg-rose-400/10 text-rose-400 border-rose-400/20",
  };
  return (
    <span className={cn("flex items-center gap-1 px-1.5 py-0.5 rounded border font-mono", colorMap[color])} title={hint}>
      {icon}
      {label}
    </span>
  );
}

// ── 评分链路可视化 ──

function ScoreBreakdown({ hit }: { hit: RetrieveHit }) {
  const factors = [
    { label: "rrf", value: hit.rrf_score, color: "bg-violet-400", max: 1 },
    { label: "time", value: hit.time_factor, color: "bg-cyan-400", max: 1 },
    { label: "imp", value: hit.importance_factor, color: "bg-emerald-400", max: 1 },
    { label: "access", value: hit.access_bonus, color: "bg-amber-400", max: 1 },
  ];

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1">
        {factors.map((f) => {
          const pct = Math.min(100, (f.value / f.max) * 100);
          return (
            <div key={f.label} className="flex-1 group relative">
              <div className="h-1 rounded-full bg-os-elevated overflow-hidden">
                <div
                  className={cn("h-full rounded-full", f.color)}
                  style={{ width: `${pct}%` }}
                />
              </div>
              <div className="absolute -top-4 left-0 right-0 text-center opacity-0 group-hover:opacity-100 transition-opacity">
                <span className="text-2xs text-os-muted font-mono">
                  {f.label}: {f.value.toFixed(3)}
                </span>
              </div>
            </div>
          );
        })}
      </div>
      <div className="flex items-center justify-between text-2xs text-os-muted font-mono">
        <span>rrf: {hit.rrf_score.toFixed(3)}</span>
        <span>time: {hit.time_factor.toFixed(3)}</span>
        <span>imp: {hit.importance_factor.toFixed(3)}</span>
        <span>access: {hit.access_bonus.toFixed(3)}</span>
      </div>
    </div>
  );
}
