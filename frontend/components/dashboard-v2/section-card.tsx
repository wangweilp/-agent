"use client";

import { cn } from "@/lib/utils";

interface SectionCardProps {
  title: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  children: React.ReactNode;
}

// 标题卡容器 — 统一 os-card 风格，带标题栏与可选操作区。
export function SectionCard({
  title,
  icon,
  action,
  className,
  bodyClassName,
  children,
}: SectionCardProps) {
  return (
    <div className={cn("os-card p-6 rounded-xl h-full flex flex-col hover:border-os-accent/50 transition-colors", className)}>
      <div className="mb-5 flex flex-wrap items-center gap-2.5">
        {icon && <span className="text-os-accent">{icon}</span>}
        <h2 className="text-sm font-medium text-os-text-high uppercase tracking-wider">
          {title}
        </h2>
        {action && <div className="ml-auto shrink-0">{action}</div>}
      </div>
      <div className={cn("flex-1 min-w-0", bodyClassName)}>{children}</div>
    </div>
  );
}
