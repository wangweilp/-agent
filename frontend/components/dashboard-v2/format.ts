// Dashboard V2 格式化工具 — 纯函数，便于单元测试。

// 分 → 元（保留 2 位小数），如 12345 → "¥123.45"
export function formatCents(cents: number): string {
  if (!Number.isFinite(cents)) return "¥0.00";
  return `¥${(cents / 100).toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

// 百分比，如 87.5 → "87.5%"；null/NaN → "—"
export function formatPercent(pct: number | null | undefined): string {
  if (pct === null || pct === undefined || !Number.isFinite(pct)) return "—";
  return `${pct.toFixed(1)}%`;
}

// 毫秒延迟，如 320 → "320ms"；1500 → "1.5s"
export function formatLatency(ms: number): string {
  if (!Number.isFinite(ms)) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

// 净增长带符号，如 12 → "+12"；-5 → "-5"；0 → "0"
export function formatDelta(n: number): string {
  if (!Number.isFinite(n)) return "0";
  if (n > 0) return `+${n}`;
  return `${n}`;
}

// 紧凑数字，如 1500 → "1.5K"，1200000 → "1.2M"
export function formatCompact(n: number): string {
  if (!Number.isFinite(n)) return "0";
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

// 烧录率（日成本 → 月成本估算），单位：分
export function estimateMonthlyCostCents(dailyCostCents: number): number {
  if (!Number.isFinite(dailyCostCents) || dailyCostCents < 0) return 0;
  return Math.round(dailyCostCents * 30);
}
