import type { ElementType, ReactNode } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { AlertCircle, ArrowUpRight, Circle, Inbox } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  badgeStyles,
  buttonStyles,
  cardStyles,
  emptyStateStyles,
  inputStyles,
  tabStyles,
  toolbarStyles,
} from "@/styles/components";
import { spacing, typeScale } from "@/styles/tokens";

type DivProps = React.HTMLAttributes<HTMLDivElement>;
type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement>;

export function PageShell({ className, children, ...props }: DivProps) {
  return (
    <div className={cn(spacing.pageMax, spacing.pageShell, spacing.sectionGap, className)} {...props}>
      {children}
    </div>
  );
}

export function PageHeader({
  icon: Icon,
  title,
  subtitle,
  actions,
  eyebrow,
  className,
}: {
  icon?: ElementType;
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  eyebrow?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-3 md:flex-row md:items-start md:justify-between", className)}>
      <div className="min-w-0">
        {eyebrow && <div className="mb-2">{eyebrow}</div>}
        <div className="flex min-w-0 items-center gap-3">
          {Icon && (
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-os-border bg-white shadow-os-card">
              <Icon size={18} className="text-os-primary" />
            </span>
          )}
          <div className="min-w-0">
            <h1 className={cn(typeScale.pageTitle, "truncate")}>{title}</h1>
            {subtitle && <p className={cn(typeScale.pageSubtitle, "mt-1 max-w-3xl")}>{subtitle}</p>}
          </div>
        </div>
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function SectionHeader({
  title,
  subtitle,
  actions,
  icon: Icon,
  className,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  icon?: ElementType;
  className?: string;
}) {
  return (
    <div className={cn("flex items-start justify-between gap-3", className)}>
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          {Icon && <Icon size={15} className="text-os-primary" />}
          <h2 className={typeScale.sectionTitle}>{title}</h2>
        </div>
        {subtitle && <p className="mt-1 text-xs leading-5 text-os-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function OsCard({
  className,
  variant,
  interactive,
  padding,
  ...props
}: DivProps & VariantProps<typeof cardStyles>) {
  return <div className={cn(cardStyles({ variant, interactive, padding }), className)} {...props} />;
}

export function OsButton({
  className,
  variant,
  size,
  ...props
}: ButtonProps & VariantProps<typeof buttonStyles>) {
  return <button className={cn(buttonStyles({ variant, size }), className)} {...props} />;
}

export function OsBadge({
  className,
  variant,
  children,
}: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeStyles>) {
  return <span className={cn(badgeStyles({ variant }), className)}>{children}</span>;
}

export function StatusBadge({
  status,
  children,
}: {
  status?: "ready" | "active" | "success" | "warning" | "danger" | "info" | "muted";
  children: ReactNode;
}) {
  const variant =
    status === "ready" || status === "success" || status === "active"
      ? "success"
      : status === "warning"
        ? "warning"
        : status === "danger"
          ? "danger"
          : status === "info"
            ? "info"
            : "muted";
  return (
    <OsBadge variant={variant}>
      <Circle size={7} className="fill-current" />
      {children}
    </OsBadge>
  );
}

export function MetricCard({
  label,
  value,
  icon: Icon,
  trend,
  detail,
  accent = "primary",
  className,
}: {
  label: ReactNode;
  value: ReactNode;
  icon?: ElementType;
  trend?: ReactNode;
  detail?: ReactNode;
  accent?: "primary" | "success" | "warning" | "danger" | "info" | "muted";
  className?: string;
}) {
  const accentMap = {
    primary: "text-os-primary bg-os-primary-soft border-os-primary/15",
    success: "text-os-success bg-os-success-soft border-os-success/15",
    warning: "text-os-warning bg-os-warning-soft border-os-warning/15",
    danger: "text-os-danger bg-os-danger-soft border-os-danger/15",
    info: "text-os-info bg-os-info-soft border-os-info/15",
    muted: "text-os-subtle bg-os-surface-muted border-os-border-subtle",
  };
  return (
    <OsCard className={cn("min-h-[116px]", className)} padding="md">
      <div className="flex items-start justify-between gap-3">
        <div className={typeScale.cardLabel}>{label}</div>
        {Icon && (
          <div className={cn("flex h-8 w-8 items-center justify-center rounded-xl border", accentMap[accent])}>
            <Icon size={15} />
          </div>
        )}
      </div>
      <div className="mt-5 flex items-end justify-between gap-3">
        <div>
          <div className={typeScale.metricValue}>{value}</div>
          {detail && <div className="mt-2 text-xs leading-5 text-os-muted">{detail}</div>}
        </div>
        {trend && <div className="text-xs font-medium text-os-subtle">{trend}</div>}
      </div>
    </OsCard>
  );
}

export function Toolbar({ className, ...props }: DivProps) {
  return <div className={cn(toolbarStyles, className)} {...props} />;
}

export function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,
  className,
}: {
  icon?: ElementType;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn(emptyStateStyles, className)}>
      <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-2xl border border-os-border bg-white text-os-primary shadow-os-card">
        <Icon size={18} />
      </div>
      <p className="text-sm font-semibold text-os-text-high">{title}</p>
      {description && <p className="mt-1 max-w-md text-sm leading-6 text-os-muted">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function InfoBanner({
  variant = "info",
  title,
  children,
  icon: Icon = AlertCircle,
  className,
}: {
  variant?: "info" | "warning" | "danger" | "success";
  title?: ReactNode;
  children: ReactNode;
  icon?: ElementType;
  className?: string;
}) {
  const classes = {
    info: "border-os-info/18 bg-os-info-soft text-os-info",
    warning: "border-os-warning/20 bg-os-warning-soft text-os-warning",
    danger: "border-os-danger/20 bg-os-danger-soft text-os-danger",
    success: "border-os-success/20 bg-os-success-soft text-os-success",
  };
  return (
    <div className={cn("flex items-start gap-3 rounded-2xl border px-4 py-3", classes[variant], className)}>
      <Icon size={16} className="mt-0.5 shrink-0" />
      <div className="min-w-0">
        {title && <p className="text-sm font-semibold">{title}</p>}
        <div className="text-sm leading-6 text-os-text">{children}</div>
      </div>
    </div>
  );
}

export function ProgressBar({
  value,
  tone = "primary",
  className,
}: {
  value: number;
  tone?: "primary" | "success" | "warning" | "danger" | "info";
  className?: string;
}) {
  const toneClass = {
    primary: "bg-os-primary",
    success: "bg-os-success",
    warning: "bg-os-warning",
    danger: "bg-os-danger",
    info: "bg-os-info",
  };
  return (
    <div className={cn("h-2 overflow-hidden rounded-full bg-os-surface-muted", className)}>
      <div
        className={cn("h-full rounded-full transition-[width] duration-200", toneClass[tone])}
        style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
      />
    </div>
  );
}

export const chipStyles = cva(
  "inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium transition-colors duration-150",
  {
    variants: {
      active: {
        true: "border-os-primary/20 bg-os-primary-soft text-os-primary",
        false: "border-os-border bg-white text-os-subtle hover:bg-os-surface-hover hover:text-os-text-high",
      },
    },
    defaultVariants: {
      active: false,
    },
  },
);

export function OsInput({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(inputStyles, className)} {...props} />;
}

export function RankRow({
  rank,
  label,
  value,
  percent,
  onClick,
}: {
  rank: number;
  label: ReactNode;
  value?: ReactNode;
  percent?: number;
  onClick?: () => void;
}) {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag
      onClick={onClick}
      className={cn(
        "group flex w-full items-center gap-3 rounded-xl px-2.5 py-2 text-left transition-colors duration-150",
        onClick && "hover:bg-os-surface-hover",
      )}
    >
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-os-surface-muted font-mono text-xs text-os-subtle">
        {rank}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium text-os-text-high">{label}</span>
        {typeof percent === "number" && <ProgressBar value={percent} className="mt-1 h-1" />}
      </span>
      {value && <span className="font-mono text-xs text-os-muted">{value}</span>}
      {onClick && <ArrowUpRight size={13} className="text-os-muted group-hover:text-os-primary" />}
    </Tag>
  );
}
