import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "刚刚";
  if (mins < 60) return `${mins} 分钟前`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days} 天前`;
  return d.toLocaleDateString("zh-CN");
}

export function formatMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function formatNumber(n: number): string {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return n.toString();
}

export function importanceColor(score: number): string {
  if (score >= 8) return "text-emerald-400";
  if (score >= 6) return "text-amber-400";
  return "text-zinc-500";
}

export function importanceBg(score: number): string {
  if (score >= 8) return "bg-emerald-400/10";
  if (score >= 6) return "bg-amber-400/10";
  return "bg-zinc-500/10";
}

export function statusColor(status: string): string {
  switch (status) {
    case "success":
    case "healthy":
    case "idle":
      return "text-emerald-400";
    case "thinking":
    case "acting":
    case "running":
      return "text-indigo-400";
    case "reflecting":
      return "text-amber-400";
    case "failed":
    case "error":
      return "text-red-400";
    default:
      return "text-zinc-500";
  }
}
