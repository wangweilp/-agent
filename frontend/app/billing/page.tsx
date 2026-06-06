"use client";

import { useState, useEffect } from "react";
import { FileText, CreditCard, RotateCcw, Download, Eye, AlertCircle } from "lucide-react";
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
// Tab: Invoices
// ═══════════════════════════════════════════════════════════════

function InvoicesTab({ invoices }: { invoices: Invoice[] }) {
  if (invoices.length === 0) {
    return <EmptyState icon={FileText} message="暂无账单" />;
  }

  const totalCount = invoices.length;
  const totalAmount = invoices.reduce((s, i) => s + i.amount, 0);
  const paidAmount = invoices.filter((i) => i.status === "paid").reduce((s, i) => s + i.amount, 0);

  return (
    <div className="space-y-4">
      {/* Summary row */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-os-surface border border-os-border rounded-xl p-4">
          <p className="text-xs text-os-subtle">总账单数</p>
          <p className="text-xl font-semibold text-os-text-high mt-1">{totalCount}</p>
        </div>
        <div className="bg-os-surface border border-os-border rounded-xl p-4">
          <p className="text-xs text-os-subtle">总金额</p>
          <p className="text-xl font-semibold text-os-text-high mt-1">{fmtAmount(totalAmount)}</p>
        </div>
        <div className="bg-os-surface border border-os-border rounded-xl p-4">
          <p className="text-xs text-os-subtle">已支付</p>
          <p className="text-xl font-semibold text-emerald-400 mt-1">{fmtAmount(paidAmount)}</p>
        </div>
      </div>

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
