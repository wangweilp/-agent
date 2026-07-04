import { cva } from "class-variance-authority";

export const cardStyles = cva(
  "border bg-os-surface text-os-text shadow-os-card transition-[border-color,box-shadow,background-color,transform] duration-200",
  {
    variants: {
      variant: {
        default: "rounded-2xl border-os-border",
        elevated: "rounded-2xl border-os-border-subtle shadow-os-elevated",
        tinted: "rounded-2xl border-os-border bg-os-surface-tinted",
        danger: "rounded-2xl border-os-danger/20 bg-os-danger-soft",
        inspector: "rounded-2xl border-os-border-subtle bg-white shadow-os-card",
      },
      interactive: {
        true: "hover:-translate-y-0.5 hover:border-os-primary/25 hover:shadow-os-elevated",
        false: "",
      },
      padding: {
        none: "",
        sm: "p-3",
        md: "p-4 md:p-5",
        lg: "p-5 md:p-6",
      },
    },
    defaultVariants: {
      variant: "default",
      interactive: false,
      padding: "md",
    },
  },
);

export const buttonStyles = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-xl text-sm font-medium outline-none transition-[background-color,border-color,color,box-shadow,transform] duration-150 focus-visible:ring-2 focus-visible:ring-os-primary/25 disabled:cursor-not-allowed disabled:border-os-border-subtle disabled:bg-os-surface-muted disabled:text-os-muted",
  {
    variants: {
      variant: {
        primary: "border border-os-primary bg-os-primary text-white shadow-os-brand hover:bg-os-primary-hover",
        secondary: "border border-os-border bg-white text-os-text-high shadow-os-card hover:bg-os-surface-hover",
        soft: "border border-os-primary/15 bg-os-primary-soft text-os-primary hover:border-os-primary/25 hover:bg-os-primary-soft",
        ghost: "border border-transparent bg-transparent text-os-subtle hover:bg-os-surface-hover hover:text-os-text-high",
        danger: "border border-os-danger bg-os-danger text-white shadow-none hover:bg-os-danger-hover",
        dangerSoft: "border border-os-danger/20 bg-os-danger-soft text-os-danger hover:bg-os-danger-soft",
      },
      size: {
        sm: "h-8 px-3 text-xs",
        md: "h-9 px-3.5 text-sm",
        lg: "h-10 px-4 text-sm",
        iconSm: "h-8 w-8 p-0",
        icon: "h-9 w-9 p-0",
      },
    },
    defaultVariants: {
      variant: "secondary",
      size: "md",
    },
  },
);

export const badgeStyles = cva(
  "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-medium leading-5",
  {
    variants: {
      variant: {
        default: "border-os-border bg-white text-os-subtle",
        primary: "border-os-primary/20 bg-os-primary-soft text-os-primary",
        success: "border-os-success/20 bg-os-success-soft text-os-success",
        warning: "border-os-warning/20 bg-os-warning-soft text-os-warning",
        danger: "border-os-danger/20 bg-os-danger-soft text-os-danger",
        info: "border-os-info/20 bg-os-info-soft text-os-info",
        muted: "border-os-border-subtle bg-os-surface-muted text-os-muted",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export const tabStyles = cva(
  "relative inline-flex h-9 items-center justify-center gap-2 whitespace-nowrap rounded-xl px-3 text-sm font-medium outline-none transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-os-primary/25",
  {
    variants: {
      active: {
        true: "bg-white text-os-text-high shadow-os-card ring-1 ring-os-border",
        false: "text-os-subtle hover:bg-white/70 hover:text-os-text-high",
      },
    },
    defaultVariants: {
      active: false,
    },
  },
);

export const inputStyles =
  "h-9 rounded-xl border border-os-border bg-white px-3 text-sm text-os-text-high outline-none transition-[border-color,box-shadow,background-color] duration-150 placeholder:text-os-muted focus:border-os-primary/35 focus:ring-2 focus:ring-os-primary/15 disabled:cursor-not-allowed disabled:bg-os-surface-muted disabled:text-os-muted";

export const emptyStateStyles =
  "flex min-h-[220px] flex-col items-center justify-center rounded-2xl border border-dashed border-os-border bg-os-surface-tinted px-6 py-10 text-center";

export const toolbarStyles =
  "flex min-h-10 flex-wrap items-center gap-2 rounded-2xl border border-os-border bg-white px-3 py-2 shadow-os-card";
