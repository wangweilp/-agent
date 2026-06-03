"use client";

import { motion } from "framer-motion";
import { Lightbulb, Calendar } from "lucide-react";
import { Skeleton } from "@/components/animations/skeleton";
import { formatDate } from "@/lib/utils";
import type { RecentReflectionItem } from "@/types";

interface RecentReflectionsProps {
  reflections?: RecentReflectionItem[];
  isLoading: boolean;
}

export function RecentReflections({ reflections, isLoading }: RecentReflectionsProps) {
  if (isLoading) return <Skeleton className="h-64" />;
  if (!reflections || reflections.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-2xs text-os-muted">
        <Lightbulb size={20} className="mb-2 opacity-40" />
        暂无反思记录
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {reflections.map((ref, i) => (
        <motion.div
          key={ref.id}
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.06 }}
          className="os-card p-3 group transition-colors"
        >
          <div className="flex items-start gap-2.5">
            <div className="w-7 h-7 rounded-lg bg-amber-400/10 flex items-center justify-center shrink-0 mt-0.5">
              <Lightbulb size={13} className="text-amber-400" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-os-text-high truncate">
                {ref.topic}
              </p>
              <p className="text-2xs text-os-subtle mt-1 line-clamp-3 leading-relaxed">
                {ref.finding}
              </p>
              <div className="flex items-center gap-2 mt-2">
                <span className="text-2xs text-os-muted flex items-center gap-1">
                  <Calendar size={10} />
                  {formatDate(ref.timestamp)}
                </span>
                {ref.entities.length > 0 && (
                  <span className="text-2xs text-os-muted truncate">
                    {ref.entities.slice(0, 2).join(", ")}
                  </span>
                )}
              </div>
            </div>
          </div>
        </motion.div>
      ))}
    </div>
  );
}
