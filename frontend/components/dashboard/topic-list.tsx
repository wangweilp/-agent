"use client";

import { motion } from "framer-motion";
import { Tag } from "lucide-react";
import { Skeleton } from "@/components/animations/skeleton";
import { EmptyState, RankRow } from "@/components/ui/os";
import type { TopicItem } from "@/types";

interface TopicListProps {
  topics?: TopicItem[];
  isLoading: boolean;
}

export function TopicList({ topics, isLoading }: TopicListProps) {
  if (isLoading) return <Skeleton className="h-64 rounded-2xl" />;

  if (!topics || topics.length === 0) {
    return (
      <EmptyState
        icon={Tag}
        title="暂无主题数据"
        description="当记忆被写入并提取主题后，这里会显示最活跃的知识线索。"
        className="min-h-[240px]"
      />
    );
  }

  const maxMention = topics[0]?.mention_count || 1;

  return (
    <div className="space-y-1.5">
      {topics.map((topic, i) => (
        <motion.div
          key={topic.name}
          initial={{ opacity: 0, x: -6 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: Math.min(i * 0.03, 0.18), duration: 0.16 }}
        >
          <RankRow
            rank={i + 1}
            label={topic.name}
            value={`${topic.mention_count} / ${topic.memory_count} 条`}
            percent={Math.round((topic.mention_count / maxMention) * 100)}
          />
        </motion.div>
      ))}
    </div>
  );
}
