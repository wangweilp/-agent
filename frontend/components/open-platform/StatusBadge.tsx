"use client";
import { CheckCircle2, XCircle, Clock, AlertTriangle, Ban } from "lucide-react";

const STATUS_CONFIG: Record<string, { icon: typeof CheckCircle2; color: string; label: string }> = {
  draft: { icon: Clock, color: "bg-zinc-400/10 text-zinc-300", label: "Draft" },
  submitted: { icon: Clock, color: "bg-blue-400/10 text-blue-300", label: "Submitted" },
  in_review: { icon: Clock, color: "bg-amber-400/10 text-amber-300", label: "In Review" },
  approved: { icon: CheckCircle2, color: "bg-emerald-400/10 text-emerald-300", label: "Approved" },
  rejected: { icon: XCircle, color: "bg-red-400/10 text-red-300", label: "Rejected" },
  published: { icon: CheckCircle2, color: "bg-violet-400/10 text-violet-300", label: "Published" },
  withdrawn: { icon: Ban, color: "bg-zinc-500/10 text-os-muted", label: "Withdrawn" },
  active: { icon: CheckCircle2, color: "bg-emerald-400/10 text-emerald-300", label: "Active" },
  suspended: { icon: AlertTriangle, color: "bg-red-400/10 text-red-300", label: "Suspended" },
  pending: { icon: Clock, color: "bg-amber-400/10 text-amber-300", label: "Pending" },
  rejected_dev: { icon: XCircle, color: "bg-red-400/10 text-red-300", label: "Rejected" },
  revoked: { icon: Ban, color: "bg-zinc-500/10 text-os-muted", label: "Revoked" },
  expired: { icon: Clock, color: "bg-amber-400/10 text-amber-300", label: "Expired" },
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
