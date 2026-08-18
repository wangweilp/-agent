"use client";

import { cn } from "@/lib/utils";

const typeOptions = [
  { value: "", label: "全部类型" },
  { value: "episodic", label: "情景" },
  { value: "semantic", label: "语义" },
  { value: "procedural", label: "程序" },
  { value: "reflect", label: "反思" },
];

const statusOptions = [
  { value: "", label: "全部状态" },
  { value: "active", label: "活跃" },
  { value: "archived", label: "已归档" },
  { value: "merged", label: "已合并" },
];

interface FilterBarProps {
  type: string;
  status: string;
  dateFrom: string;
  dateTo: string;
  onTypeChange: (v: string) => void;
  onStatusChange: (v: string) => void;
  onDateFromChange: (v: string) => void;
  onDateToChange: (v: string) => void;
  onClear: () => void;
  hasFilters: boolean;
}

export function MemoryFilterBar({
  type, status, dateFrom, dateTo,
  onTypeChange, onStatusChange,
  onDateFromChange, onDateToChange,
  onClear, hasFilters,
}: FilterBarProps) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {/* Type filter */}
      <div className="flex items-center gap-0.5">
        {typeOptions.map((opt) => (
          <button
            key={opt.value}
            onClick={() => onTypeChange(opt.value)}
            className={cn(
              "px-2.5 py-1 rounded text-2xs transition-colors",
              type === opt.value
                ? "bg-os-accent/20 text-os-accent font-medium"
                : "text-os-subtle hover:text-os-text hover:bg-os-surface"
            )}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {/* Divider */}
      <span className="w-px h-4 bg-os-border mx-1" />

      {/* Status filter */}
      <div className="flex items-center gap-0.5">
        {statusOptions.map((opt) => (
          <button
            key={opt.value}
            onClick={() => onStatusChange(opt.value)}
            className={cn(
              "px-2.5 py-1 rounded text-2xs transition-colors",
              status === opt.value
                ? "bg-os-accent/20 text-os-accent font-medium"
                : "text-os-subtle hover:text-os-text hover:bg-os-surface"
            )}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {/* Date filters */}
      <span className="w-px h-4 bg-os-border mx-1" />
      <div className="flex items-center gap-1.5">
        <input
          type="date"
          value={dateFrom}
          onChange={(e) => onDateFromChange(e.target.value)}
          className="w-32 h-6 px-2 rounded bg-os-surface border border-os-border text-2xs text-os-text-high focus:outline-none focus:border-os-accent"
          title="起始日期"
        />
        <span className="text-2xs text-os-subtle">至</span>
        <input
          type="date"
          value={dateTo}
          onChange={(e) => onDateToChange(e.target.value)}
          className="w-32 h-6 px-2 rounded bg-os-surface border border-os-border text-2xs text-os-text-high focus:outline-none focus:border-os-accent"
          title="结束日期"
        />
      </div>

      {/* Clear */}
      {hasFilters && (
        <button
          onClick={onClear}
          className="text-2xs text-os-subtle hover:text-os-text px-2 py-1 rounded hover:bg-os-surface transition-colors"
        >
          清除筛选
        </button>
      )}
    </div>
  );
}
