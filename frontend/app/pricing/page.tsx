"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
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
  Crown,
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

// ── 3 阶套餐映射 ──
// 将后端任意套餐映射为顶级 SaaS 三阶卡片（Hobby / Pro / Enterprise）
type TierKind = "hobby" | "pro" | "enterprise";

interface TierMeta {
  kind: TierKind;
  display: string;
  tagline: string;
  cta: string;
  badge?: string;
}

const TIER_META: Record<TierKind, TierMeta> = {
  hobby: {
    kind: "hobby",
    display: "Hobby",
    tagline: "免费开始体验个人知识管理",
    cta: "免费开始",
  },
  pro: {
    kind: "pro",
    display: "Pro",
    tagline: "专业用户首选，解锁全部能力",
    cta: "升级到 Pro",
    badge: "MOST POPULAR",
  },
  enterprise: {
    kind: "enterprise",
    display: "Enterprise",
    tagline: "团队协作与企业级部署",
    cta: "联系销售",
  },
};

// 3 阶展示规则：每个 tier 显示哪些 features（true=支持/勾选，false=不支持/X）
// 与原数据无关，构造极致对比的顶级 SaaS 视觉差异
const TIER_FEATURE_MATRIX: Record<TierKind, Array<{ key: keyof PlanLimit; included: boolean; value?: string }>> = {
  hobby: [
    { key: "memory_count", included: true, value: "500 条" },
    { key: "search_count", included: true, value: "50 / 日" },
    { key: "storage_mb", included: true, value: "100 MB" },
    { key: "import_per_day", included: true, value: "10 / 日" },
    { key: "sync_connectors", included: true, value: "2 个" },
    { key: "knowledge_graph", included: false },
    { key: "ai_coach", included: false },
    { key: "team_members", included: false },
    { key: "api_access", included: false },
    { key: "priority_support", included: false },
    { key: "llm_calls_per_day", included: true, value: "100 / 日" },
    { key: "embedding_calls_per_day", included: true, value: "1K / 日" },
  ],
  pro: [
    { key: "memory_count", included: true, value: "无限" },
    { key: "search_count", included: true, value: "无限" },
    { key: "storage_mb", included: true, value: "10 GB" },
    { key: "import_per_day", included: true, value: "无限" },
    { key: "sync_connectors", included: true, value: "无限" },
    { key: "knowledge_graph", included: true },
    { key: "ai_coach", included: true },
    { key: "team_members", included: true, value: "3 人" },
    { key: "api_access", included: true },
    { key: "priority_support", included: false },
    { key: "llm_calls_per_day", included: true, value: "10K / 日" },
    { key: "embedding_calls_per_day", included: true, value: "100K / 日" },
  ],
  enterprise: [
    { key: "memory_count", included: true, value: "无限" },
    { key: "search_count", included: true, value: "无限" },
    { key: "storage_mb", included: true, value: "1 TB" },
    { key: "import_per_day", included: true, value: "无限" },
    { key: "sync_connectors", included: true, value: "无限" },
    { key: "knowledge_graph", included: true },
    { key: "ai_coach", included: true },
    { key: "team_members", included: true, value: "无限" },
    { key: "api_access", included: true },
    { key: "priority_support", included: true },
    { key: "llm_calls_per_day", included: true, value: "无限" },
    { key: "embedding_calls_per_day", included: true, value: "无限" },
  ],
};

const FAQ_ITEMS = [
  {
    q: "如何切换套餐？",
    a: "在账户设置中选择升级即可立即生效。升级时按比例折算剩余时间费用，降级在下个计费周期生效。",
  },
  {
    q: "Hobby 套餐有什么限制？",
    a: "Hobby 套餐提供基础的记忆存储和搜索功能，适合个人试用。记忆条数、搜索次数和存储空间均有上限。",
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

function computeSavings(monthly: number, yearly: number): number {
  return monthly * 12 - yearly;
}

function computeSavingsPercent(monthly: number, yearly: number): number {
  if (monthly <= 0) return 0;
  return Math.round((1 - yearly / (monthly * 12)) * 100);
}

function formatPrice(cents: number): string {
  const yuan = cents / 100;
  return yuan.toLocaleString("zh-CN", {
    minimumFractionDigits: 0,
    maximumFractionDigits: yuan % 1 === 0 ? 0 : 2,
  });
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

// ── 3 阶套餐展示卡片 ──
// 顶级 SaaS 卡片：极客光晕 + MOST POPULAR 徽章 + 巨大价格数字 + 青色 Check / 灰色 X 划线

function TierCard({
  kind,
  plan,
  billingCycle,
  isCurrent,
}: {
  kind: TierKind;
  plan: PlanPreview | null;
  billingCycle: "monthly" | "yearly";
  isCurrent: boolean;
}) {
  const meta = TIER_META[kind];
  const isPro = kind === "pro";
  const isYearly = billingCycle === "yearly";

  // 价格计算：优先使用后端真实价格；若后端无对应 tier，则使用默认价目
  const fallbackPriceCents: Record<TierKind, { monthly: number; yearly: number }> = {
    hobby: { monthly: 0, yearly: 0 },
    pro: { monthly: 4900, yearly: 49000 },
    enterprise: { monthly: 19900, yearly: 199000 },
  };

  const monthlyCents = plan ? plan.monthly_price : fallbackPriceCents[kind].monthly;
  const yearlyCents = plan ? plan.yearly_price : fallbackPriceCents[kind].yearly;
  const priceCents = isYearly ? yearlyCents : monthlyCents;
  const savings = isYearly ? computeSavings(monthlyCents, yearlyCents) : 0;
  const savingsPct = isYearly ? computeSavingsPercent(monthlyCents, yearlyCents) : 0;
  const periodLabel = isYearly ? "/年" : "/month";
  const features = TIER_FEATURE_MATRIX[kind];

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={cn(
        "relative flex flex-col rounded-xl border p-6 transition-all duration-300",
        "bg-os-surface",
        // Pro 卡片：知维 OS 专属极客光晕
        isPro
          ? "border-os-accent shadow-[0_0_30px_rgba(129,140,248,0.15)] ring-1 ring-os-accent/30"
          : "border-os-border shadow-os-sm",
        "hover:border-os-muted hover:shadow-os-md",
        // Pro 卡片在中间略大
        isPro && "lg:scale-[1.04] lg:-my-2 z-10"
      )}
    >
      {/* MOST POPULAR 徽章（仅 Pro） */}
      {isPro && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2 z-20">
          <span className="inline-flex items-center gap-1 rounded-full bg-os-accent px-3 py-1 text-2xs font-bold tracking-wider text-[#000000] shadow-os-sm">
            <Sparkles className="h-3 w-3" />
            {meta.badge}
          </span>
        </div>
      )}

      {/* 当前套餐标记 */}
      {isCurrent && !isPro && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2">
          <span className="inline-flex items-center gap-1 rounded-full bg-os-muted px-3 py-0.5 text-2xs font-semibold text-os-text-high shadow-os-sm">
            当前套餐
          </span>
        </div>
      )}

      {/* 套餐名称和描述 */}
      <div className="mb-5">
        <div className="flex items-center gap-2">
          {kind === "enterprise" && <Crown className="h-4 w-4 text-amber-400" />}
          <h3 className="text-lg font-semibold text-os-text-high">{meta.display}</h3>
          {isPro && (
            <span className="rounded-full bg-os-accent/15 px-2 py-0.5 text-2xs font-medium text-os-accent">
              推荐
            </span>
          )}
        </div>
        <p className="mt-1 text-xs text-os-muted">{meta.tagline}</p>
      </div>

      {/* 价格 — 巨大且极具冲击力 */}
      <div className="mb-5">
        <div className="flex items-baseline gap-1.5">
          <span className="text-2xl font-semibold text-os-muted">¥</span>
          <span className="text-5xl font-mono font-bold tracking-tight text-os-text-high tabular-nums">
            {formatPrice(priceCents)}
          </span>
          <span className="text-xs text-os-muted font-mono">{periodLabel}</span>
        </div>
        {isYearly && savings > 0 && (
          <p className="mt-2 text-xs text-emerald-400 font-mono">
            节省 ¥{formatPrice(savings)}（{savingsPct}%）
          </p>
        )}
        {!isYearly && kind !== "hobby" && (
          <p className="mt-2 text-xs text-os-muted font-mono">
            或 ¥{formatPrice(yearlyCents)}/年
          </p>
        )}
      </div>

      {/* CTA 按钮 */}
      <button
        disabled={isCurrent}
        className={cn(
          "mb-6 w-full rounded-lg px-4 py-2.5 text-sm font-semibold transition-all duration-200",
          isCurrent
            ? "cursor-default bg-os-muted/30 text-os-muted"
            : isPro
              ? "bg-os-accent text-white hover:bg-os-accent/85 shadow-[0_0_20px_rgba(129,140,248,0.3)]"
              : kind === "enterprise"
                ? "bg-amber-500/15 text-amber-400 hover:bg-amber-500/25 border border-amber-500/30"
                : "bg-os-elevated text-os-text-high hover:bg-os-muted/30 border border-os-border"
        )}
      >
        {isCurrent ? "当前套餐" : meta.cta}
      </button>

      {/* 特性列表 — 青色 Check / 灰色 X 划线 */}
      <div className="flex flex-col gap-0">
        {features.map((f, i) => {
          const def = FEATURE_DEFS.find((d) => d.key === f.key);
          if (!def) return null;
          const valueLabel = f.included
            ? (f.value ?? "支持")
            : "不支持";
          const positive = f.included;
          const negative = !f.included;
          return (
            <div
              key={f.key}
              className={cn(
                "flex items-center gap-3 py-2.5 text-sm",
                i !== features.length - 1 && "border-b border-os-border/50"
              )}
            >
              {positive ? (
                <Check className="h-4 w-4 shrink-0 text-cyan-400" />
              ) : (
                <X className="h-4 w-4 shrink-0 text-os-border" />
              )}
              <span
                className={cn(
                  "flex-1",
                  negative ? "text-os-border line-through" : "text-os-text"
                )}
              >
                {def.label}
              </span>
              <span
                className={cn(
                  "flex items-center gap-1.5 text-right font-medium tabular-nums font-mono text-xs",
                  positive && f.value && valueLabel !== "支持" && "text-cyan-400",
                  positive && (!f.value || valueLabel === "支持") && "text-os-text-high",
                  negative && "text-os-border line-through"
                )}
              >
                {valueLabel}
              </span>
            </div>
          );
        })}
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
    <div className="grid grid-cols-1 gap-6 md:grid-cols-3 lg:gap-8 max-w-5xl mx-auto">
      {Array.from({ length: 3 }).map((_, i) => (
        <div
          key={i}
          className={cn(
            "animate-pulse rounded-xl border border-os-border bg-os-surface p-6",
            i === 1 && "lg:scale-[1.04] ring-1 ring-os-accent/20"
          )}
        >
          <div className="mb-4 h-5 w-20 rounded bg-os-muted/40" />
          <div className="mb-2 h-12 w-28 rounded bg-os-muted/40" />
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

  // 将后端任意套餐映射为 3 阶展示
  // 优先匹配：free→hobby, professional→pro, enterprise→enterprise
  // 若无匹配，按价格区间兜底
  const tierPlans = useMemo(() => {
    const findTier = (kind: TierKind): PlanPreview | null => {
      const tierKey = kind === "hobby" ? "free" : kind === "pro" ? "professional" : "enterprise";
      // 精确匹配 tier 名称
      const exact = plans.find((p) => p.tier.toLowerCase() === tierKey);
      if (exact) return exact;
      // 兜底：按价格区间
      const sorted = [...plans].sort((a, b) => a.monthly_price - b.monthly_price);
      if (kind === "hobby") return sorted[0] ?? null;
      if (kind === "enterprise") return sorted[sorted.length - 1] ?? null;
      // pro 取中位数
      return sorted[Math.floor(sorted.length / 2)] ?? sorted[0] ?? null;
    };
    return {
      hobby: findTier("hobby"),
      pro: findTier("pro"),
      enterprise: findTier("enterprise"),
    };
  }, [plans]);

  const currentTierKind: TierKind | null = useMemo(() => {
    const current = plans.find((p) => p.current);
    if (!current) return null;
    const tierKey = current.tier.toLowerCase();
    if (tierKey === "free") return "hobby";
    if (tierKey === "professional") return "pro";
    if (tierKey === "enterprise") return "enterprise";
    // 按价格区间兜底
    if (current.monthly_price === 0) return "hobby";
    if (current.monthly_price >= 10000) return "enterprise";
    return "pro";
  }, [plans]);

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

      {/* ── 3 阶套餐卡片 ── */}
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
        ) : (
          <div className="grid grid-cols-1 gap-6 md:grid-cols-3 lg:gap-8 max-w-5xl mx-auto items-stretch">
            <AnimatePresence mode="wait">
              <TierCard
                key="hobby"
                kind="hobby"
                plan={tierPlans.hobby}
                billingCycle={billingCycle}
                isCurrent={currentTierKind === "hobby"}
              />
              <TierCard
                key="pro"
                kind="pro"
                plan={tierPlans.pro}
                billingCycle={billingCycle}
                isCurrent={currentTierKind === "pro"}
              />
              <TierCard
                key="enterprise"
                kind="enterprise"
                plan={tierPlans.enterprise}
                billingCycle={billingCycle}
                isCurrent={currentTierKind === "enterprise"}
              />
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
