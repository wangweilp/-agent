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
    <div className={cn("os-card p-4 h-full flex flex-col", className)}>
      <div className="flex items-center gap-2 mb-3">
        {icon && <span className="text-os-accent">{icon}</span>}
        <h2 className="text-xs font-medium text-os-text-high uppercase tracking-wider">
          {title}
        </h2>
        {action && <div className="ml-auto">{action}</div>}
      </div>
      <div className={cn("flex-1 min-w-0", bodyClassName)}>{children}</div>
    </div>
  );
}
