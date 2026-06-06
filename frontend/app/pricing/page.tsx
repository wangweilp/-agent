"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Check,
  X,
  Zap,
  Users,
  Database,
  Search,
  TrendingUp,
  Shield,
  ChevronDown,
  Sparkles,
  HelpCircle,
} from "lucide-react";
import { api } from "@/services/api";
import type { PlanPreview, PlanLimit } from "@/types";
import { cn } from "@/lib/utils";

// ── 常量 ──

const FEATURE_DEFS: {
  key: Exclude<keyof PlanLimit, "tier">;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  format: (v: number | boolean) => string;
}[] = [
  { key: "memory_count", label: "记忆条数", icon: Database, format: (v) => formatNumeric(v) },
  { key: "search_count", label: "每日搜索", icon: Search, format: (v) => formatNumeric(v) },
  { key: "storage_mb", label: "存储空间", icon: Database, format: (v) => formatStorage(v) },
  { key: "import_per_day", label: "每日导入", icon: TrendingUp, format: (v) => formatNumeric(v) },
  { key: "sync_connectors", label: "同步连接器", icon: Users, format: (v) => formatNumeric(v) },
  { key: "knowledge_graph", label: "知识图谱", icon: TrendingUp, format: (v) => formatBool(v) },
  { key: "ai_coach", label: "AI Coach", icon: Zap, format: (v) => formatBool(v) },
  { key: "team_members", label: "团队成员", icon: Users, format: (v) => formatNumeric(v) },
  { key: "api_access", label: "API 访问", icon: Shield, format: (v) => formatBool(v) },
  { key: "priority_support", label: "优先支持", icon: Shield, format: (v) => formatBool(v) },
  { key: "llm_calls_per_day", label: "LLM 调用/日", icon: Zap, format: (v) => formatNumeric(v) },
  { key: "embedding_calls_per_day", label: "Embedding/日", icon: TrendingUp, format: (v) => formatNumeric(v) },
];

const ACCENT_MAP: Record<string, { border: string; bg: string; badge: string; glow: string }> = {
  free: {
    border: "border-os-border",
    bg: "",
    badge: "bg-os-muted/50 text-os-text",
    glow: "",
  },
  personal: {
    border: "border-blue-500/30",
    bg: "bg-blue-500/[0.04]",
    badge: "bg-blue-500/15 text-blue-400",
    glow: "shadow-[0_0_30px_rgba(59,130,246,0.06)]",
  },
  professional: {
    border: "border-purple-500/30",
    bg: "bg-purple-500/[0.04]",
    badge: "bg-purple-500/15 text-purple-400",
    glow: "shadow-[0_0_30px_rgba(168,85,247,0.06)]",
  },
  team: {
    border: "border-green-500/30",
    bg: "bg-green-500/[0.04]",
    badge: "bg-green-500/15 text-green-400",
    glow: "shadow-[0_0_30px_rgba(34,197,94,0.06)]",
  },
  enterprise: {
    border: "border-amber-500/30",
    bg: "bg-amber-500/[0.04]",
    badge: "bg-amber-500/15 text-amber-400",
    glow: "shadow-[0_0_30px_rgba(251,191,36,0.06)]",
  },
};

const FAQ_ITEMS = [
  {
    q: "如何切换套餐？",
    a: "在账户设置中选择升级即可立即生效。升级时按比例折算剩余时间费用，降级在下个计费周期生效。",
  },
  {
    q: "Free 套餐有什么限制？",
    a: "Free 套餐提供基础的记忆存储和搜索功能，适合个人试用。记忆条数、搜索次数和存储空间均有上限。",
  },
  {
    q: "年付能省多少？",
    a: "年付方案比月付节省约 17%，相当于每年免费使用 2 个月。",
  },
  {
    q: "是否支持发票？",
    a: "支持。所有付费套餐均可开具增值税电子发票，在账单页面自助申请。",
  },
  {
    q: "数据安全如何保障？",
    a: "所有数据加密存储，传输使用 TLS 1.3。企业版支持私有化部署和自定义加密密钥。",
  },
  {
    q: "可以随时取消吗？",
    a: "可以。取消后当前计费周期结束前仍可继续使用，不会立即中断服务。",
  },
];

// ── 格式化 ──

const UNLIMITED = 999999;

function formatNumeric(v: number | boolean): string {
  if (typeof v === "boolean") return v ? "是" : "否";
  if (v >= UNLIMITED) return "无限";
  return v.toLocaleString();
}

function formatStorage(v: number | boolean): string {
  if (typeof v === "boolean") return v ? "是" : "否";
  if (v >= UNLIMITED) return "无限";
  if (v >= 1024) {
    const gb = v / 1024;
    return gb % 1 === 0 ? `${gb} GB` : `${gb.toFixed(1)} GB`;
  }
  return `${v} MB`;
}

function formatBool(v: number | boolean): string {
  return v ? "支持" : "不支持";
}

function isTruthy(v: number | boolean): boolean {
  if (typeof v === "boolean") return v;
  return v > 0;
}

function computeSavings(monthly: number, yearly: number): number {
  return monthly * 12 - yearly;
}

function computeSavingsPercent(monthly: number, yearly: number): number {
  return Math.round((1 - yearly / (monthly * 12)) * 100);
}

// ── 子组件 ──

function ToggleSwitch({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-8 w-14 shrink-0 cursor-pointer items-center rounded-full transition-colors duration-200",
        checked ? "bg-os-accent" : "bg-os-muted"
      )}
    >
      <span
        className={cn(
          "inline-block h-5 w-5 rounded-full bg-white shadow-sm transition-transform duration-200",
          checked ? "translate-x-7" : "translate-x-1.5"
        )}
      />
    </button>
  );
}

function FeatureRow({
  label,
  value,
  icon: Icon,
  isLast,
}: {
  label: string;
  value: string;
  icon: React.ComponentType<{ className?: string }>;
  isLast?: boolean;
}) {
  const positive = value === "支持" || value === "无限";
  const negative = value === "不支持";
  return (
    <div
      className={cn(
        "flex items-center gap-3 py-2.5 text-sm",
        !isLast && "border-b border-os-border/50"
      )}
    >
      <Icon className="h-4 w-4 shrink-0 text-os-muted" />
      <span className="flex-1 text-os-text">{label}</span>
      <span className="flex items-center gap-1.5 text-right font-medium tabular-nums">
        {positive ? (
          <Check className="h-4 w-4 text-emerald-400" />
        ) : negative ? (
          <X className="h-4 w-4 text-os-muted" />
        ) : null}
        <span
          className={cn(
            positive && "text-emerald-400",
            negative && "text-os-muted",
            !positive && !negative && "text-os-text-high"
          )}
        >
          {value}
        </span>
      </span>
    </div>
  );
}

function PlanCard({
  plan,
  billingCycle,
  highlight,
}: {
  plan: PlanPreview;
  billingCycle: "monthly" | "yearly";
  highlight: boolean;
}) {
  const tierKey = plan.tier.toLowerCase();
  const accent = ACCENT_MAP[tierKey] ?? ACCENT_MAP.free;
  const isYearly = billingCycle === "yearly";
  const price = isYearly ? plan.yearly_price : plan.monthly_price;
  const savings = isYearly ? computeSavings(plan.monthly_price, plan.yearly_price) : 0;
  const savingsPct = isYearly ? computeSavingsPercent(plan.monthly_price, plan.yearly_price) : 0;
  const periodLabel = isYearly ? "/年" : "/月";

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={cn(
        "relative flex flex-col rounded-xl border p-6 transition-all duration-300",
        "bg-os-surface",
        highlight ? "ring-1 ring-os-accent/30 shadow-os-lg" : "shadow-os-sm",
        accent.border,
        accent.bg,
        accent.glow,
        "hover:border-os-muted hover:shadow-os-md"
      )}
    >
      {/* 当前套餐标记 */}
      {highlight && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2">
          <span className="inline-flex items-center gap-1 rounded-full bg-os-accent px-3 py-0.5 text-2xs font-semibold text-white shadow-os-sm">
            <Sparkles className="h-3 w-3" />
            当前套餐
          </span>
        </div>
      )}

      {/* 套餐名称和描述 */}
      <div className="mb-5">
        <div className="flex items-center gap-2">
          <h3 className="text-lg font-semibold text-os-text-high">{plan.tier}</h3>
          {tierKey !== "free" && (
            <span className={cn("rounded-full px-2 py-0.5 text-2xs font-medium", accent.badge)}>
              {tierKey === "enterprise" ? "旗舰" : tierKey === "team" ? "协作" : "推荐"}
            </span>
          )}
        </div>
        <p className="mt-1 text-xs text-os-muted">
          {tierKey === "free"
            ? "免费开始体验"
            : tierKey === "personal"
              ? "个人深度使用"
              : tierKey === "professional"
                ? "专业用户首选"
                : tierKey === "team"
                  ? "团队协作版本"
                  : "企业级部署"}
        </p>
      </div>

      {/* 价格 */}
      <div className="mb-5">
        <div className="flex items-baseline gap-1">
          <span className="text-3xl font-bold text-os-text-high">{"¥"}{price.toLocaleString()}</span>
          <span className="text-sm text-os-muted">{periodLabel}</span>
        </div>
        {isYearly && savings > 0 && (
          <p className="mt-1 text-xs text-emerald-400">
            节省 {"¥"}{savings.toLocaleString()}（{savingsPct}%）
          </p>
        )}
        {!isYearly && tierKey !== "free" && (
          <p className="mt-1 text-xs text-os-muted">
            或 {"¥"}{plan.yearly_price.toLocaleString()}/年
          </p>
        )}
      </div>

      {/* CTA 按钮 */}
      <button
        disabled={highlight}
        className={cn(
          "mb-6 w-full rounded-lg px-4 py-2.5 text-sm font-semibold transition-all duration-200",
          highlight
            ? "cursor-default bg-os-muted/30 text-os-muted"
            : tierKey === "enterprise"
              ? "bg-amber-500/15 text-amber-400 hover:bg-amber-500/25 border border-amber-500/30"
              : "bg-os-accent text-white hover:bg-os-accent/85 shadow-os-sm"
        )}
      >
        {highlight ? "当前套餐" : tierKey === "free" ? "免费开始" : "升级"}
      </button>

      {/* 特性列表 */}
      <div className="flex flex-col gap-0">
        {FEATURE_DEFS.map((def, i) => (
          <FeatureRow
            key={def.key}
            label={def.label}
            value={def.format(plan.limits[def.key])}
            icon={def.icon}
            isLast={i === FEATURE_DEFS.length - 1}
          />
        ))}
      </div>
    </motion.div>
  );
}

function FaqAccordion({
  question,
  answer,
}: {
  question: string;
  answer: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="border-b border-os-border/50 last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between gap-4 py-4 text-left text-sm font-medium text-os-text-high hover:text-os-text transition-colors"
      >
        <span className="flex items-center gap-2">
          <HelpCircle className="h-4 w-4 shrink-0 text-os-muted" />
          {question}
        </span>
        <ChevronDown
          className={cn(
            "h-4 w-4 shrink-0 text-os-muted transition-transform duration-200",
            open && "rotate-180"
          )}
        />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <p className="pb-4 text-sm leading-relaxed text-os-muted">{answer}</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
      {Array.from({ length: 5 }).map((_, i) => (
        <div
          key={i}
          className="animate-pulse rounded-xl border border-os-border bg-os-surface p-6"
        >
          <div className="mb-4 h-5 w-20 rounded bg-os-muted/40" />
          <div className="mb-2 h-8 w-24 rounded bg-os-muted/40" />
          <div className="mb-6 h-4 w-16 rounded bg-os-muted/40" />
          <div className="mb-6 h-10 w-full rounded-lg bg-os-muted/40" />
          {Array.from({ length: 12 }).map((_, j) => (
            <div key={j} className="mb-2.5 flex items-center gap-3">
              <div className="h-4 w-4 shrink-0 rounded bg-os-muted/40" />
              <div className="h-3 flex-1 rounded bg-os-muted/30" />
              <div className="h-3 w-10 rounded bg-os-muted/30" />
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

// ── 主页面 ──

export default function PricingPage() {
  const [plans, setPlans] = useState<PlanPreview[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [billingCycle, setBillingCycle] = useState<"monthly" | "yearly">("monthly");

  const fetchPlans = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.subscription.listPlans();
      setPlans(data);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "加载套餐失败";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPlans();
  }, [fetchPlans]);

  const currentTier = plans.find((p) => p.current)?.tier ?? null;

  return (
    <div className="min-h-screen">
      {/* ── Hero ── */}
      <section className="relative overflow-hidden border-b border-os-border">
        {/* 背景装饰 */}
        <div className="pointer-events-none absolute inset-0 bg-os-grid bg-os-grid opacity-30" />
        <div className="pointer-events-none absolute left-1/2 top-0 h-[400px] w-[800px] -translate-x-1/2 bg-gradient-to-b from-os-accent/[0.04] via-transparent to-transparent" />

        <div className="relative mx-auto max-w-7xl px-6 pb-16 pt-20 text-center sm:pt-24 sm:pb-20">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
          >
            <h1 className="text-3xl font-bold tracking-tight text-os-text-high sm:text-4xl lg:text-5xl">
              选择适合你的套餐
            </h1>
            <p className="mx-auto mt-4 max-w-2xl text-sm text-os-muted sm:text-base">
              从个人探索到企业部署，灵活的定价满足不同规模需求。
              所有套餐均可随时升级或取消。
            </p>
          </motion.div>

          {/* 计费周期切换 */}
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.1 }}
            className="mt-10 flex items-center justify-center gap-3"
          >
            <span
              className={cn(
                "text-sm font-medium transition-colors",
                billingCycle === "monthly" ? "text-os-text-high" : "text-os-muted"
              )}
            >
              月付
            </span>
            <ToggleSwitch
              checked={billingCycle === "yearly"}
              onChange={(v) => setBillingCycle(v ? "yearly" : "monthly")}
            />
            <span
              className={cn(
                "text-sm font-medium transition-colors",
                billingCycle === "yearly" ? "text-os-text-high" : "text-os-muted"
              )}
            >
              年付
            </span>
            {billingCycle === "yearly" && (
              <span className="ml-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-2xs font-semibold text-emerald-400">
                省 ~17%
              </span>
            )}
          </motion.div>
        </div>
      </section>

      {/* ── 套餐卡片 ── */}
      <section className="mx-auto max-w-7xl px-6 py-16 sm:py-20">
        {loading ? (
          <LoadingSkeleton />
        ) : error ? (
          <div className="flex flex-col items-center gap-4 py-20 text-center">
            <div className="rounded-full bg-red-500/10 p-3">
              <X className="h-6 w-6 text-red-400" />
            </div>
            <p className="text-sm text-os-muted">{error}</p>
            <button
              type="button"
              onClick={fetchPlans}
              className="rounded-lg bg-os-muted/30 px-4 py-2 text-sm font-medium text-os-text-high transition-colors hover:bg-os-muted/50"
            >
              重试
            </button>
          </div>
        ) : plans.length === 0 ? (
          <div className="py-20 text-center text-sm text-os-muted">暂无可用套餐</div>
        ) : (
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
            <AnimatePresence mode="wait">
              {plans.map((plan) => (
                <PlanCard
                  key={plan.tier}
                  plan={plan}
                  billingCycle={billingCycle}
                  highlight={plan.current}
                />
              ))}
            </AnimatePresence>
          </div>
        )}
      </section>

      {/* ── FAQ ── */}
      <section className="border-t border-os-border">
        <div className="mx-auto max-w-3xl px-6 py-16 sm:py-20">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.4 }}
            className="mb-10 text-center"
          >
            <h2 className="text-2xl font-bold text-os-text-high sm:text-3xl">常见问题</h2>
            <p className="mt-3 text-sm text-os-muted">关于套餐和计费的常见疑问</p>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.4, delay: 0.1 }}
            className="rounded-xl border border-os-border bg-os-surface px-6"
          >
            {FAQ_ITEMS.map((item) => (
              <FaqAccordion key={item.q} question={item.q} answer={item.a} />
            ))}
          </motion.div>
        </div>
      </section>
    </div>
  );
}
