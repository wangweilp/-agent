export const surface = {
  app: "bg-os-page",
  panel: "bg-os-panel",
  card: "bg-os-surface",
  elevated: "bg-os-elevated",
  tinted: "bg-os-surface-tinted",
  hover: "hover:bg-os-surface-hover",
} as const;

export const border = {
  default: "border-os-border",
  subtle: "border-os-border-subtle",
  strong: "border-os-border-strong",
  active: "border-os-primary/25",
  danger: "border-os-danger/25",
} as const;

export const radius = {
  card: "rounded-2xl",
  panel: "rounded-2xl",
  control: "rounded-xl",
  badge: "rounded-full",
} as const;

export const shadow = {
  card: "shadow-os-card",
  elevated: "shadow-os-elevated",
  floating: "shadow-os-floating",
  none: "shadow-none",
} as const;

export const typeScale = {
  pageTitle: "text-2xl font-semibold leading-tight tracking-normal text-os-text-high md:text-[1.75rem]",
  pageSubtitle: "text-sm leading-6 text-os-muted",
  sectionTitle: "text-sm font-semibold tracking-normal text-os-text-high",
  cardLabel: "text-[11px] font-medium uppercase tracking-[0.08em] text-os-muted",
  metricValue: "font-mono text-2xl font-semibold leading-none tracking-normal text-os-text-high",
  monoCaption: "font-mono text-[11px] leading-4 text-os-muted",
} as const;

export const spacing = {
  pageShell: "px-4 py-4 md:px-6 md:py-6 lg:px-8",
  pageMax: "mx-auto w-full max-w-[1440px]",
  sectionGap: "space-y-5 md:space-y-6",
  cardPadding: "p-4 md:p-5",
  toolbarHeight: "min-h-10",
  navItemHeight: "h-9",
} as const;

export const semantic = {
  primary: {
    text: "text-os-primary",
    bg: "bg-os-primary",
    soft: "bg-os-primary-soft",
    border: "border-os-primary/25",
    ring: "focus-visible:ring-os-primary/25",
  },
  success: {
    text: "text-os-success",
    bg: "bg-os-success",
    soft: "bg-os-success-soft",
    border: "border-os-success/25",
  },
  warning: {
    text: "text-os-warning",
    bg: "bg-os-warning",
    soft: "bg-os-warning-soft",
    border: "border-os-warning/25",
  },
  danger: {
    text: "text-os-danger",
    bg: "bg-os-danger",
    soft: "bg-os-danger-soft",
    border: "border-os-danger/25",
  },
  info: {
    text: "text-os-info",
    bg: "bg-os-info",
    soft: "bg-os-info-soft",
    border: "border-os-info/25",
  },
  muted: {
    text: "text-os-muted",
    bg: "bg-os-surface-muted",
    border: "border-os-border",
  },
} as const;

export const chart = {
  panelHeight: "h-[300px] md:h-[340px]",
  compactHeight: "h-[220px] md:h-[260px]",
  gridStroke: "rgba(17, 24, 39, 0.07)",
  axisStroke: "rgba(71, 85, 105, 0.58)",
  tooltip:
    "rounded-xl border border-os-border bg-white/95 px-3 py-2 text-xs shadow-os-floating backdrop-blur",
} as const;
