"use client";

import { motion } from "framer-motion";
import { Hash, Tag } from "lucide-react";
import { Skeleton } from "@/components/animations/skeleton";
import type { TopicItem } from "@/types";

interface TopicListProps {
  topics?: TopicItem[];
  isLoading: boolean;
}

export function TopicList({ topics, isLoading }: TopicListProps) {
  if (isLoading) return <Skeleton className="h-64" />;
  if (!topics || topics.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-2xs text-os-muted">
        <Tag size={20} className="mb-2 opacity-40" />
        暂无主题数据
      </div>
    );
  }

  const maxMention = topics[0]?.mention_count || 1;

  return (
    <div className="space-y-2">
      {topics.map((topic, i) => (
        <motion.div
          key={topic.name}
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: i * 0.04 }}
          className="flex items-center gap-3 py-2 px-3 rounded-lg hover:bg-os-surface-hover transition-colors group"
        >
          {/* Rank */}
          <span className={`
            w-5 h-5 rounded text-2xs font-mono flex items-center justify-center shrink-0
            ${i === 0 ? "bg-amber-400/20 text-amber-400" :
              i === 1 ? "bg-zinc-400/20 text-zinc-400" :
              i === 2 ? "bg-amber-700/20 text-amber-700" :
              "bg-os-surface text-os-muted"}
          `}>
            {i + 1}
          </span>

          {/* Name */}
          <div className="flex-1 min-w-0">
            <p className="text-xs text-os-text-high truncate">{topic.name}</p>
            {/* Mention bar */}
            <div className="mt-1 h-0.5 w-full bg-os-surface rounded-full overflow-hidden">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${Math.round((topic.mention_count / maxMention) * 100)}%` }}
                transition={{ duration: 0.6, delay: 0.2 + i * 0.04 }}
                className="h-full bg-indigo-400/60 rounded-full"
              />
            </div>
          </div>

          {/* Stats */}
          <div className="flex items-center gap-2 text-2xs shrink-0">
            <span className="text-os-subtle flex items-center gap-0.5">
              <Hash size={10} />
              {topic.mention_count}
            </span>
            <span className="text-os-muted">{topic.memory_count} 条</span>
          </div>
        </motion.div>
      ))}
    </div>
  );
}
