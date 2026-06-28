"use client";

import { useState, useEffect, useMemo } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { FileText, CreditCard, RotateCcw, Download, Eye, AlertCircle, TrendingUp } from "lucide-react";
import { api } from "@/services/api";
import type { Invoice, Payment, Refund, BillingAccount } from "@/types";

// ── Tab definitions ──

const TABS = [
  { key: "invoices", label: "账单", icon: FileText },
  { key: "payments", label: "支付记录", icon: CreditCard },
  { key: "refunds", label: "退款记录", icon: RotateCcw },
] as const;

type TabKey = (typeof TABS)[number]["key"];

// ── Status & provider style maps ──

const INVOICE_STATUS: Record<string, string> = {
  paid: "bg-emerald-400/10 text-emerald-400 border-emerald-400/20",
  open: "bg-indigo-400/10 text-indigo-400 border-indigo-400/20",
  overdue: "bg-red-400/10 text-red-400 border-red-400/20",
  draft: "bg-os-muted/20 text-os-subtle border-os-border/50",
  void: "bg-os-muted/20 text-os-subtle border-os-border/50",
};

const INVOICE_STATUS_LABEL: Record<string, string> = {
  paid: "已支付",
  open: "待支付",
  overdue: "已逾期",
  draft: "草稿",
  void: "已作废",
};

const TX_STATUS: Record<string, string> = {
  succeeded: "bg-emerald-400/10 text-emerald-400 border-emerald-400/20",
  pending: "bg-amber-400/10 text-amber-400 border-amber-400/20",
  failed: "bg-red-400/10 text-red-400 border-red-400/20",
};

const TX_STATUS_LABEL: Record<string, string> = {
  succeeded: "成功",
  pending: "处理中",
  failed: "失败",
};

const PROVIDER_STYLE: Record<string, string> = {
  wechat: "bg-emerald-400/10 text-emerald-400 border-emerald-400/20",
  alipay: "bg-indigo-400/10 text-indigo-400 border-indigo-400/20",
  stripe: "bg-purple-400/10 text-purple-400 border-purple-400/20",
};

const PROVIDER_LABEL: Record<string, string> = {
  wechat: "微信支付",
  alipay: "支付宝",
  stripe: "Stripe",
};

// ── Format helpers ──

function fmtAmount(amount: number): string {
  return `¥${(amount / 100).toFixed(2)}`;
}

function fmtDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" });
}

function fmtFullDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ── Shared badge component ──

function StatusBadge({
  value,
  styleMap,
  labelMap,
}: {
  value: string;
  styleMap: Record<string, string>;
  labelMap: Record<string, string>;
}) {
  const cls = styleMap[value] ?? "bg-os-muted/20 text-os-subtle border-os-border/50";
  const label = labelMap[value] ?? value;
  return (
    <span className={`text-2xs px-2 py-0.5 rounded-full border font-medium whitespace-nowrap ${cls}`}>
      {label}
    </span>
  );
}

// ── Shared empty state ──

function EmptyState({ icon: Icon, message }: { icon: React.ElementType; message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-os-subtle gap-3">
      <Icon className="w-12 h-12 opacity-20" />
      <p className="text-sm">{message}</p>
    </div>
  );
}

// ── Shared loading spinner ──

function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="animate-spin w-8 h-8 border-2 border-os-accent border-t-transparent rounded-full" />
    </div>
  );
}

// ── Shared error state ──

function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
      <div className="w-12 h-12 rounded-full bg-red-400/10 flex items-center justify-center">
        <AlertCircle className="w-6 h-6 text-red-400" />
      </div>
      <p className="text-os-text text-sm">{message}</p>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// Neon Billing Chart — 发光的消费账单趋势图
// 使用 linearGradient 从 os-accent（顶部）渐变到透明（底部）
// 数据源：从现有 invoices 按日期聚合（无新增 API 调用）
// ═══════════════════════════════════════════════════════════════

interface SpendTrendPoint {
  date: string;
  spend: number; // 元
  label: string;
}

function deriveSpendTrend(invoices: Invoice[]): SpendTrendPoint[] {
  if (invoices.length === 0) return [];
  // 按日期聚合
  const byDate = new Map<string, number>();
  for (const inv of invoices) {
    const d = new Date(inv.created_at);
    const key = d.toISOString().slice(0, 10); // YYYY-MM-DD
    byDate.set(key, (byDate.get(key) ?? 0) + inv.amount / 100);
  }
  // 排序并生成连续序列
  const sorted = [...byDate.entries()].sort(([a], [b]) => a.localeCompare(b));
  return sorted.map(([date, spend]) => {
    const d = new Date(date);
    return {
      date,
      spend: Number(spend.toFixed(2)),
      label: `${d.getMonth() + 1}/${d.getDate()}`,
    };
  });
}

const BILLING_TOOLTIP_STYLE = {
  backgroundColor: "#111113",
  border: "1px solid #818CF8",
  borderRadius: "12px",
  fontSize: "12px",
  color: "#E4E4E7",
  boxShadow: "0 0 20px rgba(129,140,248,0.15)",
};

function NeonBillingChart({ trend }: { trend: SpendTrendPoint[] }) {
  if (trend.length === 0) {
    return (
      <div className="bg-os-surface border border-os-border rounded-xl p-4">
        <h3 className="mb-3 text-sm font-semibold text-os-text-high flex items-center gap-2">
          <TrendingUp className="h-4 w-4 text-os-accent" />
          消费趋势
        </h3>
        <div className="flex items-center justify-center h-[200px] text-xs text-os-subtle">
          暂无消费数据
        </div>
      </div>
    );
  }

  return (
    <div className="bg-os-surface border border-os-border rounded-xl p-4">
      <h3 className="mb-3 text-sm font-semibold text-os-text-high flex items-center gap-2">
        <TrendingUp className="h-4 w-4 text-os-accent" />
        消费趋势
        <span className="ml-auto text-2xs font-mono text-os-subtle">{trend.length} 期</span>
      </h3>
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart data={trend} margin={{ top: 6, right: 8, left: 8, bottom: 0 }}>
          <defs>
            {/* 霓虹渐变：os-accent 顶部 → 透明底部 */}
            <linearGradient id="neonSpendGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#818CF8" stopOpacity={0.6} />
              <stop offset="60%" stopColor="#818CF8" stopOpacity={0.15} />
              <stop offset="100%" stopColor="#818CF8" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="rgba(255,255,255,0.03)" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fill: "#52525B", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: "#52525B", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            width={48}
          />
          <Tooltip
            contentStyle={BILLING_TOOLTIP_STYLE}
            itemStyle={{ color: "#818CF8" }}
            formatter={(value: number) => [`¥${value.toFixed(2)}`, "消费"]}
          />
          <Area
            type="monotone"
            dataKey="spend"
            stroke="#818CF8"
            strokeWidth={2}
            fill="url(#neonSpendGradient)"
            dot={{ fill: "#818CF8", r: 2, strokeWidth: 0 }}
            activeDot={{ r: 4, fill: "#818CF8", stroke: "#111113", strokeWidth: 2 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// Tab: Invoices
// ═══════════════════════════════════════════════════════════════

function InvoicesTab({ invoices }: { invoices: Invoice[] }) {
  // 消费趋势派生（基于现有 invoices，无新增 API 调用）
  const spendTrend = useMemo(() => deriveSpendTrend(invoices), [invoices]);

  if (invoices.length === 0) {
    return <EmptyState icon={FileText} message="暂无账单" />;
  }

  const totalCount = invoices.length;
  const totalAmount = invoices.reduce((s, i) => s + i.amount, 0);
  const paidAmount = invoices.filter((i) => i.status === "paid").reduce((s, i) => s + i.amount, 0);

  return (
    <div className="space-y-4">
      {/* Summary row — Total Spend 带发光效果 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-os-surface border border-os-border rounded-xl p-4">
          <p className="text-xs text-os-subtle">总账单数</p>
          <p className="text-xl font-semibold text-os-text-high mt-1">{totalCount}</p>
        </div>
        {/* Total Spend — 微弱文本阴影发光 */}
        <div className="bg-os-surface border border-os-accent/30 rounded-xl p-4 shadow-[0_0_20px_rgba(129,140,248,0.08)]">
          <p className="text-xs text-os-subtle flex items-center gap-1">
            <TrendingUp className="h-3 w-3 text-os-accent" />
            总消费
          </p>
          <p className="text-xl font-semibold text-os-accent mt-1 font-mono tabular-nums drop-shadow-md">
            {fmtAmount(totalAmount)}
          </p>
        </div>
        <div className="bg-os-surface border border-os-border rounded-xl p-4">
          <p className="text-xs text-os-subtle">已支付</p>
          <p className="text-xl font-semibold text-emerald-400 mt-1">{fmtAmount(paidAmount)}</p>
        </div>
      </div>

      {/* Neon Billing Chart — 发光消费趋势图 */}
      <NeonBillingChart trend={spendTrend} />

      {/* Table */}
      <div className="bg-os-surface border border-os-border rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-os-border bg-os-elevated">
                <th className="text-left px-4 py-3 text-xs text-os-subtle font-medium">发票号</th>
                <th className="text-left px-4 py-3 text-xs text-os-subtle font-medium">金额</th>
                <th className="text-left px-4 py-3 text-xs text-os-subtle font-medium">状态</th>
                <th className="text-left px-4 py-3 text-xs text-os-subtle font-medium">描述</th>
                <th className="text-left px-4 py-3 text-xs text-os-subtle font-medium">日期</th>
                <th className="text-right px-4 py-3 text-xs text-os-subtle font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {invoices.map((inv) => (
                <tr
                  key={inv.id}
                  className="border-b border-os-border/40 hover:bg-os-elevated/40 transition-colors"
                >
                  <td className="px-4 py-3">
                    <span className="text-os-text-high font-mono text-xs">{inv.invoice_number}</span>
                  </td>
                  <td className="px-4 py-3 text-os-text font-medium">{fmtAmount(inv.amount)}</td>
                  <td className="px-4 py-3">
                    <StatusBadge value={inv.status} styleMap={INVOICE_STATUS} labelMap={INVOICE_STATUS_LABEL} />
                  </td>
                  <td className="px-4 py-3 text-os-text max-w-[240px] truncate" title={inv.description}>
                    {inv.description || "—"}
                  </td>
                  <td className="px-4 py-3 text-os-subtle text-xs whitespace-nowrap">{fmtDate(inv.created_at)}</td>
                  <td className="px-4 py-3 text-right">
                    <button
                      className="inline-flex items-center gap-1 text-xs text-os-accent hover:text-indigo-300 transition-colors"
                      title={`查看发票 ${inv.invoice_number} 详情`}
                    >
                      <Eye className="w-3.5 h-3.5" />
                      查看
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// Tab: Payments
// ═══════════════════════════════════════════════════════════════

function PaymentsTab({ payments }: { payments: Payment[] }) {
  if (payments.length === 0) {
    return <EmptyState icon={CreditCard} message="暂无支付记录" />;
  }

  return (
    <div className="bg-os-surface border border-os-border rounded-xl overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-os-border bg-os-elevated">
              <th className="text-left px-4 py-3 text-xs text-os-subtle font-medium">支付ID</th>
              <th className="text-left px-4 py-3 text-xs text-os-subtle font-medium">金额</th>
              <th className="text-left px-4 py-3 text-xs text-os-subtle font-medium">支付方式</th>
              <th className="text-left px-4 py-3 text-xs text-os-subtle font-medium">状态</th>
              <th className="text-left px-4 py-3 text-xs text-os-subtle font-medium">描述</th>
              <th className="text-left px-4 py-3 text-xs text-os-subtle font-medium">日期</th>
            </tr>
          </thead>
          <tbody>
            {payments.map((pmt) => (
              <tr
                key={pmt.id}
                className="border-b border-os-border/40 hover:bg-os-elevated/40 transition-colors"
              >
                <td className="px-4 py-3">
                  <span className="text-os-text-high font-mono text-xs">{pmt.id}</span>
                </td>
                <td className="px-4 py-3 text-os-text font-medium">{fmtAmount(pmt.amount)}</td>
                <td className="px-4 py-3">
                  <StatusBadge
                    value={pmt.provider}
                    styleMap={PROVIDER_STYLE}
                    labelMap={PROVIDER_LABEL}
                  />
                </td>
                <td className="px-4 py-3">
                  <StatusBadge value={pmt.status} styleMap={TX_STATUS} labelMap={TX_STATUS_LABEL} />
                </td>
                <td className="px-4 py-3 text-os-text max-w-[240px] truncate" title={pmt.description}>
                  {pmt.description || "—"}
                </td>
                <td className="px-4 py-3 text-os-subtle text-xs whitespace-nowrap">
                  {fmtDate(pmt.created_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// Tab: Refunds
// ═══════════════════════════════════════════════════════════════

function RefundsTab({ refunds }: { refunds: Refund[] }) {
  if (refunds.length === 0) {
    return <EmptyState icon={RotateCcw} message="暂无退款记录" />;
  }

  return (
    <div className="bg-os-surface border border-os-border rounded-xl overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-os-border bg-os-elevated">
              <th className="text-left px-4 py-3 text-xs text-os-subtle font-medium">退款ID</th>
              <th className="text-left px-4 py-3 text-xs text-os-subtle font-medium">支付ID</th>
              <th className="text-left px-4 py-3 text-xs text-os-subtle font-medium">金额</th>
              <th className="text-left px-4 py-3 text-xs text-os-subtle font-medium">状态</th>
              <th className="text-left px-4 py-3 text-xs text-os-subtle font-medium">原因</th>
              <th className="text-left px-4 py-3 text-xs text-os-subtle font-medium">日期</th>
            </tr>
          </thead>
          <tbody>
            {refunds.map((ref) => (
              <tr
                key={ref.id}
                className="border-b border-os-border/40 hover:bg-os-elevated/40 transition-colors"
              >
                <td className="px-4 py-3">
                  <span className="text-os-text-high font-mono text-xs">{ref.id}</span>
                </td>
                <td className="px-4 py-3">
                  <span className="text-os-text-high font-mono text-xs">{ref.payment_id}</span>
                </td>
                <td className="px-4 py-3 text-os-text font-medium">{fmtAmount(ref.amount)}</td>
                <td className="px-4 py-3">
                  <StatusBadge value={ref.status} styleMap={TX_STATUS} labelMap={TX_STATUS_LABEL} />
                </td>
                <td className="px-4 py-3 text-os-text max-w-[240px] truncate" title={ref.reason}>
                  {ref.reason || "—"}
                </td>
                <td className="px-4 py-3 text-os-subtle text-xs whitespace-nowrap">
                  {fmtDate(ref.created_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// Main Page Component
// ═══════════════════════════════════════════════════════════════

export default function BillingPage() {
  const [activeTab, setActiveTab] = useState<TabKey>("invoices");
  const [account, setAccount] = useState<BillingAccount | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [refunds, setRefunds] = useState<Refund[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchAll() {
      try {
        setLoading(true);
        setError(null);

        const [acct, inv, pmts, rfds] = await Promise.all([
          api.billing.getAccount(),
          api.billing.listInvoices(),
          api.billing.listPayments(),
          api.billing.listRefunds(),
        ]);

        if (cancelled) return;

        setAccount(acct);
        setInvoices(inv);
        setPayments(pmts);
        setRefunds(rfds);
      } catch (err: unknown) {
        if (cancelled) return;
        const msg = err instanceof Error ? err.message : "账单数据加载失败";
        setError(msg);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchAll();
    return () => {
      cancelled = true;
    };
  }, []);

  // ── Loading ──

  if (loading) return <LoadingSpinner />;

  // ── Error ──

  if (error) return <ErrorState message={error} />;

  // ── Render ──

  return (
    <div className="max-w-6xl mx-auto px-6 py-8 space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-semibold text-os-text-high">账单管理</h1>
        <p className="text-sm text-os-subtle mt-1">查看和管理您的账单、支付记录与退款</p>
      </div>

      {/* Account summary card */}
      {account && (
        <div className="bg-os-surface border border-os-border rounded-xl p-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 rounded-full bg-emerald-400/10 flex items-center justify-center shrink-0">
              <CreditCard className="w-5 h-5 text-emerald-400" />
            </div>
            <div>
              <p className="text-xs text-os-subtle">当前余额</p>
              <p className="text-2xl font-semibold text-os-text-high">
                {fmtAmount(account.balance)}
              </p>
            </div>
          </div>
          <div className="flex gap-6 text-sm">
            <div>
              <span className="text-os-subtle">货币 </span>
              <span className="text-os-text-high font-mono text-xs">
                {account.currency?.toUpperCase() ?? "CNY"}
              </span>
            </div>
            <div>
              <span className="text-os-subtle">账单邮箱 </span>
              <span className="text-os-text-high">{account.billing_email || "—"}</span>
            </div>
          </div>
        </div>
      )}

      {/* Tab bar */}
      <div className="flex border-b border-os-border">
        {TABS.map(({ key, label, icon: Icon }) => {
          const isActive = activeTab === key;
          return (
            <button
              key={key}
              type="button"
              onClick={() => setActiveTab(key)}
              className={`flex items-center gap-1.5 px-4 py-3 text-sm font-medium transition-colors border-b-2 -mb-px ${
                isActive
                  ? "border-os-accent text-os-text-high"
                  : "border-transparent text-os-subtle hover:text-os-text"
              }`}
            >
              <Icon className="w-4 h-4" />
              {label}
            </button>
          );
        })}
      </div>

      {/* Tab panels */}
      {activeTab === "invoices" && <InvoicesTab invoices={invoices} />}
      {activeTab === "payments" && <PaymentsTab payments={payments} />}
      {activeTab === "refunds" && <RefundsTab refunds={refunds} />}
    </div>
  );
}
