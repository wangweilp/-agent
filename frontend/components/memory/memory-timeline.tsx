"use client";

import { motion } from "framer-motion";
import { Brain, Lightbulb, BookOpen } from "lucide-react";
import { cn, formatDate, importanceColor } from "@/lib/utils";
import type { Memory } from "@/types";

const typeIcon: Record<string, React.ElementType> = {
  episodic: BookOpen,
  semantic: Brain,
  reflect: Lightbulb,
};

export function MemoryTimeline({ memories }: { memories: Memory[] }) {
  const sorted = [...memories].sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
  );

  if (sorted.length === 0) return null;

  return (
    <div className="relative pl-6">
      {/* Timeline line */}
      <div className="absolute left-[11px] top-2 bottom-2 w-px bg-os-border" />

      <div className="space-y-4">
        {sorted.map((m, i) => {
          const Icon = typeIcon[m.memory_type] || BookOpen;
          return (
            <motion.div
              key={m.id}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: i * 0.03 }}
              className="relative"
            >
              {/* Dot */}
              <div className={cn(
                "absolute -left-[22px] top-1.5 w-2.5 h-2.5 rounded-full border-2 border-os-base",
                importanceColor(m.importance).replace("text-", "bg-"),
              )} />

              {/* Content */}
              <div className="os-card p-4 ml-2 os-card-hover">
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <Icon size={13} className="text-os-subtle" />
                  <span className="text-xs font-medium text-os-text-high">
                    {m.memory_type === "reflect" ? "反思洞察" : m.memory_type === "semantic" ? "语义记忆" : "情景记忆"}
                  </span>
                  <span className="text-2xs text-os-subtle">{formatDate(m.timestamp)}</span>
                </div>
                <p className="break-words text-sm leading-relaxed text-os-text [overflow-wrap:anywhere]">
                  {m.summary || m.content.slice(0, 200)}
                </p>
                {m.entities.length > 0 && (
                  <div className="flex items-center gap-1 mt-2 flex-wrap">
                    {m.entities.map((e) => (
                      <span key={e} className="max-w-full break-all rounded bg-os-elevated px-1.5 py-0.5 text-2xs text-os-subtle">
                        {e}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
