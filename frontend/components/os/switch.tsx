"use client";

import { cn } from "@/lib/utils";

// ── Switch 开关组件 ──
// 开启：bg-os-accent + 发光阴影；关闭：bg-os-muted

interface SwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  "aria-label"?: string;
}

export function Switch({ checked, onChange, disabled, ...props }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full transition-all duration-200 outline-none",
        "focus-visible:ring-2 focus-visible:ring-os-accent/40 focus-visible:ring-offset-2 focus-visible:ring-offset-os-surface",
        disabled && "cursor-not-allowed opacity-50",
        checked
          ? "bg-os-accent shadow-[0_0_10px_rgba(129,140,248,0.4)]"
          : "bg-os-muted",
      )}
      {...props}
    >
      <span
        className={cn(
          "inline-block h-4 w-4 transform rounded-full bg-white shadow-sm transition-transform duration-200",
          checked ? "translate-x-6" : "translate-x-1",
        )}
      />
    </button>
  );
}
