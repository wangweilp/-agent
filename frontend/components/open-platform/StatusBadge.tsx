"use client";
import { CheckCircle2, XCircle, Clock, AlertTriangle, Ban } from "lucide-react";

const STATUS_CONFIG: Record<string, { icon: typeof CheckCircle2; color: string; label: string }> = {
  draft: { icon: Clock, color: "bg-zinc-400/10 text-zinc-300", label: "草稿" },
  submitted: { icon: Clock, color: "bg-blue-400/10 text-blue-300", label: "已提交" },
  in_review: { icon: Clock, color: "bg-amber-400/10 text-amber-300", label: "审核中" },
  approved: { icon: CheckCircle2, color: "bg-emerald-400/10 text-emerald-300", label: "已通过" },
  rejected: { icon: XCircle, color: "bg-red-400/10 text-red-300", label: "已拒绝" },
  published: { icon: CheckCircle2, color: "bg-violet-400/10 text-violet-300", label: "已发布" },
  withdrawn: { icon: Ban, color: "bg-zinc-500/10 text-os-muted", label: "已撤回" },
  active: { icon: CheckCircle2, color: "bg-emerald-400/10 text-emerald-300", label: "活跃" },
  suspended: { icon: AlertTriangle, color: "bg-red-400/10 text-red-300", label: "已暂停" },
  pending: { icon: Clock, color: "bg-amber-400/10 text-amber-300", label: "待处理" },
  rejected_dev: { icon: XCircle, color: "bg-red-400/10 text-red-300", label: "已拒绝" },
  revoked: { icon: Ban, color: "bg-zinc-500/10 text-os-muted", label: "已撤销" },
  expired: { icon: Clock, color: "bg-amber-400/10 text-amber-300", label: "已过期" },
};

export function StatusBadge({ status }: { status: string }) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.draft;
  const Icon = config.icon;
  return (
    <span className={`os-badge inline-flex items-center gap-1 ${config.color}`}>
      <Icon size={11} />
      {config.label}
    </span>
  );
}
