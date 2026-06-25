"use client";

import { AlertCircle, RefreshCw, Inbox } from "lucide-react";
import { CardSkeleton } from "@/components/animations/skeleton";
import { cn } from "@/lib/utils";

// ── Empty ──

export function EmptyState({
  message = "暂无数据",
  className,
}: {
  message?: string;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center h-48 gap-2 text-os-muted", className)}>
      <Inbox size={20} className="text-os-subtle" />
      <p className="text-2xs">{message}</p>
    </div>
  );
}

// ── Error + Retry ──

export function ErrorState({
  message = "加载失败",
  onRetry,
}: {
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center h-48 gap-3 text-os-muted">
      <AlertCircle size={20} className="text-os-danger" />
      <p className="text-2xs">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="flex items-center gap-1.5 rounded-md border border-os-border px-2.5 py-1 text-2xs text-os-text hover:bg-os-elevated transition-colors"
        >
          <RefreshCw size={11} />
          重试
        </button>
      )}
    </div>
  );
}

// ── 统一状态分发 ──

interface QueryStateProps {
  isLoading: boolean;
  isError: boolean;
  isEmpty?: boolean;
  errorText?: string;
  emptyText?: string;
  onRetry?: () => void;
  skeleton?: React.ReactNode;
  children: React.ReactNode;
}

export function QueryState({
  isLoading,
  isError,
  isEmpty = false,
  errorText,
  emptyText,
  onRetry,
  skeleton,
  children,
}: QueryStateProps) {
  if (isLoading) {
    return <>{skeleton ?? <CardSkeleton />}</>;
  }
  if (isError) {
    return <ErrorState message={errorText} onRetry={onRetry} />;
  }
  if (isEmpty) {
    return <EmptyState message={emptyText} />;
  }
  return <>{children}</>;
}
