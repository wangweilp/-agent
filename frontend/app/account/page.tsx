"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  Crown,
  BarChart3,
  Users,
  Ticket,
  Building2,
  Copy,
  Check,
  Gift,
  Loader2,
  AlertCircle,
  Send,
  XCircle,
} from "lucide-react";
import { api } from "@/services/api";
import { cn } from "@/lib/utils";
import type {
  Subscription,
  UsageStats,
  Referral,
  ReferralStats,
  Coupon,
  Tenant,
  Invite,
} from "@/types";

// ── Label/color config maps ──

const tierConfig: Record<string, { label: string; className: string }> = {
  FREE:         { label: "免费版", className: "border-zinc-500/20 bg-zinc-500/10 text-zinc-400" },
  PERSONAL:     { label: "个人版", className: "border-blue-500/20 bg-blue-500/10 text-blue-400" },
  PROFESSIONAL: { label: "专业版", className: "border-purple-500/20 bg-purple-500/10 text-purple-400" },
  TEAM:         { label: "团队版", className: "border-emerald-500/20 bg-emerald-500/10 text-emerald-400" },
  ENTERPRISE:   { label: "企业版", className: "border-amber-500/20 bg-amber-500/10 text-amber-400" },
};

tierConfig.free = tierConfig.FREE;
tierConfig.personal = tierConfig.PERSONAL;
tierConfig.professional = tierConfig.PROFESSIONAL;
tierConfig.team = tierConfig.TEAM;
tierConfig.enterprise = tierConfig.ENTERPRISE;

const statusConfig: Record<string, { label: string; className: string }> = {
  active:   { label: "活跃",   className: "bg-emerald-500/15 text-emerald-400" },
  trial:    { label: "试用中", className: "bg-amber-500/15 text-amber-400" },
  past_due: { label: "已逾期", className: "bg-red-500/15 text-red-400" },
  canceled: { label: "已取消", className: "bg-zinc-500/15 text-zinc-400" },
};

const billingCycleLabel: Record<string, string> = {
  monthly: "月度",
  yearly:  "年度",
};

const resourceLabels: Record<string, string> = {
  memory_count:     "记忆数量",
  search_count:     "搜索次数",
  llm_calls:        "LLM 调用",
  embedding_calls:  "向量调用",
  storage_mb:       "存储 (MB)",
  import_count:     "导入次数",
  sync_count:       "同步次数",
};

const resourcePalette = [
  "bg-indigo-500",
  "bg-blue-500",
  "bg-violet-500",
  "bg-cyan-500",
  "bg-emerald-500",
  "bg-amber-500",
  "bg-rose-500",
];

// ── Section header ──

function SectionHeader({ icon: Icon, title }: { icon: React.ElementType; title: string }) {
  return (
    <div className="flex items-center gap-2.5 mb-5">
      <Icon size={16} className="text-os-muted" />
      <h2 className="text-sm font-semibold text-os-text-high">{title}</h2>
    </div>
  );
}

// ── Main page ──

export default function AccountPage() {
  const router = useRouter();

  // ── Section 1: Subscription ──
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [subLoading, setSubLoading] = useState(true);
  const [subError, setSubError] = useState("");

  // ── Section 2: Usage ──
  const [usage, setUsage] = useState<UsageStats | null>(null);
  const [usageLoading, setUsageLoading] = useState(true);

  // ── Section 3: Referral & Invite ──
  const [referrals, setReferrals] = useState<Referral[]>([]);
  const [referralStats, setReferralStats] = useState<ReferralStats | null>(null);
  const [refLoading, setRefLoading] = useState(true);
  const [invites, setInvites] = useState<Invite[]>([]);

  // Invite form
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteSending, setInviteSending] = useState(false);
  const [inviteError, setInviteError] = useState("");
  const [inviteSuccess, setInviteSuccess] = useState(false);

  // ── Section 4: Coupons ──
  const [couponCode, setCouponCode] = useState("");
  const [couponRedeeming, setCouponRedeeming] = useState(false);
  const [couponError, setCouponError] = useState("");
  const [couponSuccess, setCouponSuccess] = useState("");
  const [coupons, setCoupons] = useState<Coupon[]>([]);
  const [couponsLoading, setCouponsLoading] = useState(true);

  // ── Section 5: Tenant ──
  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [memberCount, setMemberCount] = useState<number | null>(null);
  const [tenantLoading, setTenantLoading] = useState(true);

  // Cancel confirmation
  const [cancelConfirm, setCancelConfirm] = useState(false);
  const [canceling, setCanceling] = useState(false);

  // Copy feedback
  const [copiedCode, setCopiedCode] = useState<string | null>(null);

  // Referral creation loading
  const [creatingReferral, setCreatingReferral] = useState(false);

  // ── Fetch all data on mount ──

  useEffect(() => {
    // Subscription
    api.subscription
      .get()
      .then(setSubscription)
      .catch((e: Error) => setSubError(e.message))
      .finally(() => setSubLoading(false));

    // Usage (current month)
    const now = new Date();
    api.usage
      .getStats({ year: now.getFullYear(), month: now.getMonth() + 1 })
      .then(setUsage)
      .catch(() => {})
      .finally(() => setUsageLoading(false));

    // Referrals
    api.growth
      .listReferrals()
      .then(setReferrals)
      .catch(() => {})
      .finally(() => setRefLoading(false));

    api.growth.getReferralStats().then(setReferralStats).catch(() => {});

    // Invites
    api.growth.listInvites().then(setInvites).catch(() => {});

    // Coupons
    api.growth
      .listCoupons()
      .then(setCoupons)
      .catch(() => {})
      .finally(() => setCouponsLoading(false));

    // Tenant
    api.tenant
      .getCurrent()
      .then(setTenant)
      .catch(() => {})
      .finally(() => setTenantLoading(false));

    api.tenant
      .listMembers()
      .then((members) => setMemberCount(members.length))
      .catch(() => {});
  }, []);

  // ── Actions ──

  const handleCancelSubscription = useCallback(async () => {
    if (canceling) return;
    setCanceling(true);
    try {
      await api.subscription.cancel();
      const updated = await api.subscription.get();
      setSubscription(updated);
      setCancelConfirm(false);
    } catch {
      // keep current UI state on error
    } finally {
      setCanceling(false);
    }
  }, [canceling]);

  const handleCreateReferral = useCallback(async () => {
    setCreatingReferral(true);
    try {
      const ref = await api.growth.createReferral();
      setReferrals((prev) => [ref, ...prev]);
      const stats = await api.growth.getReferralStats();
      setReferralStats(stats);
    } catch {
      // ignore
    } finally {
      setCreatingReferral(false);
    }
  }, []);

  const handleSendInvite = useCallback(async () => {
    if (!inviteEmail.trim() || inviteSending) return;
    setInviteSending(true);
    setInviteError("");
    setInviteSuccess(false);
    try {
      const inv = await api.growth.createInvite({ invitee_email: inviteEmail.trim() });
      setInvites((prev) => [inv, ...prev]);
      setInviteEmail("");
      setInviteSuccess(true);
      setTimeout(() => setInviteSuccess(false), 3000);
    } catch (e: unknown) {
      setInviteError(e instanceof Error ? e.message : "发送失败");
    } finally {
      setInviteSending(false);
    }
  }, [inviteEmail, inviteSending]);

  const handleRedeemCoupon = useCallback(async () => {
    if (!couponCode.trim() || couponRedeeming) return;
    setCouponRedeeming(true);
    setCouponError("");
    setCouponSuccess("");
    try {
      const redeemed = await api.growth.redeemCoupon({ code: couponCode.trim() });
      setCouponSuccess(`兑换成功！优惠 ¥${(redeemed.discount_cents / 100).toFixed(2)}`);
      setCouponCode("");
      const list = await api.growth.listCoupons();
      setCoupons(list);
    } catch (e: unknown) {
      setCouponError(e instanceof Error ? e.message : "兑换失败");
    } finally {
      setCouponRedeeming(false);
    }
  }, [couponCode, couponRedeeming]);

  const handleCopyReferral = useCallback(async (code: string) => {
    try {
      await navigator.clipboard.writeText(code);
      setCopiedCode(code);
      setTimeout(() => setCopiedCode(null), 2000);
    } catch {
      // clipboard unavailable
    }
  }, []);

  // ── Derived values ──

  const tier = subscription?.plan_tier ?? "FREE";
  const tierMeta = tierConfig[tier] ?? tierConfig.FREE;
  const status = subscription?.status ?? "active";
  const statusMeta = statusConfig[status] ?? statusConfig.active;
  const daysRemaining = subscription?.days_remaining ?? null;
  const activeReferral = referrals.find((r) => r.status === "active");

  // ── Render ──

  return (
    <div className="p-6 space-y-5 max-w-[800px] mx-auto">
      <h1 className="text-lg font-semibold text-os-text-high tracking-tight">账户设置</h1>

      {/* ════════════════════════════════════════════════
          Section 1 — 当前套餐
          ════════════════════════════════════════════════ */}
      <div className="os-card p-6">
        <SectionHeader icon={Crown} title="当前套餐" />

        {subLoading ? (
          <div className="flex items-center gap-2 text-sm text-os-muted py-4">
            <Loader2 size={14} className="animate-spin" />
            加载中...
          </div>
        ) : subError ? (
          <div className="flex items-center gap-2 text-sm text-os-danger py-4">
            <AlertCircle size={14} />
            {subError}
          </div>
        ) : subscription ? (
          <div className="space-y-4">
            {/* Tier + status badges */}
            <div className="flex items-center gap-3 flex-wrap">
              <span className={cn("os-badge border", tierMeta.className)}>
                {tierMeta.label}
              </span>
              <span className={cn("os-badge", statusMeta.className)}>
                {statusMeta.label}
              </span>
              {daysRemaining !== null && daysRemaining > 0 && (
                <span className="text-xs text-os-subtle">
                  {status === "trial" ? "试用剩余 " : "剩余 "}
                  <span className="text-os-text-high font-medium">{daysRemaining}</span> 天
                </span>
              )}
            </div>

            {/* Billing cycle */}
            {subscription.billing_cycle && (
              <div>
                <span className="text-xs text-os-muted">计费周期</span>
                <p className="text-sm text-os-text-high mt-0.5">
                  {billingCycleLabel[subscription.billing_cycle] ?? subscription.billing_cycle}
                </p>
              </div>
            )}

            {/* Period dates */}
            {subscription.current_period_start && (
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <span className="text-xs text-os-muted">周期开始</span>
                  <p className="text-sm text-os-text-high mt-0.5">
                    {new Date(subscription.current_period_start).toLocaleDateString("zh-CN")}
                  </p>
                </div>
                {subscription.current_period_end && (
                  <div>
                    <span className="text-xs text-os-muted">周期结束</span>
                    <p className="text-sm text-os-text-high mt-0.5">
                      {new Date(subscription.current_period_end).toLocaleDateString("zh-CN")}
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* Auto-renew */}
            {subscription.auto_renew !== undefined && (
              <div>
                <span className="text-xs text-os-muted">自动续费</span>
                <p className="text-sm text-os-text-high mt-0.5">
                  {subscription.auto_renew ? "已开启" : "未开启"}
                </p>
              </div>
            )}

            {/* Coupon applied */}
            {subscription.coupon_code && (
              <div>
                <span className="text-xs text-os-muted">已使用优惠券</span>
                <p className="text-sm font-mono text-os-text-high mt-0.5">{subscription.coupon_code}</p>
              </div>
            )}

            {/* Actions */}
            <div className="flex items-center gap-3 pt-2">
              <button
                onClick={() => router.push("/pricing")}
                className="px-4 py-1.5 rounded text-xs font-medium bg-os-accent text-white hover:bg-os-accent/90 transition-colors"
              >
                更换套餐
              </button>

              {subscription.status !== "canceled" && (
                <>
                  {!cancelConfirm ? (
                    <button
                      onClick={() => setCancelConfirm(true)}
                      className="px-4 py-1.5 rounded text-xs font-medium border border-os-danger/30 text-os-danger hover:bg-os-danger/10 transition-colors"
                    >
                      取消订阅
                    </button>
                  ) : (
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-os-subtle">确认取消？</span>
                      <button
                        onClick={handleCancelSubscription}
                        disabled={canceling}
                        className="px-3 py-1 rounded text-xs font-medium bg-os-danger text-white hover:bg-os-danger/90 disabled:opacity-50 transition-colors"
                      >
                        {canceling ? "取消中..." : "确认"}
                      </button>
                      <button
                        onClick={() => setCancelConfirm(false)}
                        className="px-3 py-1 rounded text-xs text-os-muted hover:text-os-text transition-colors"
                      >
                        返回
                      </button>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        ) : (
          <p className="text-sm text-os-muted py-4">暂无订阅信息</p>
        )}
      </div>

      {/* ════════════════════════════════════════════════
          Section 2 — 用量统计
          ════════════════════════════════════════════════ */}
      <div className="os-card p-6">
        <SectionHeader icon={BarChart3} title="用量统计" />

        {usageLoading ? (
          <div className="flex items-center gap-2 text-sm text-os-muted py-4">
            <Loader2 size={14} className="animate-spin" />
            加载中...
          </div>
        ) : usage ? (
          <div className="space-y-4">
            {/* Period label */}
            <div className="text-xs text-os-muted">
              {new Date(usage.period_start).toLocaleDateString("zh-CN")}
              {" — "}
              {new Date(usage.period_end).toLocaleDateString("zh-CN")}
            </div>

            {/* Resource usage bars */}
            {Object.keys(usage.by_resource).length > 0 ? (
              <div className="space-y-3">
                {Object.entries(usage.by_resource).map(([resource, count], i) => {
                  const cost = usage.by_resource_cost[resource] ?? 0;
                  const maxCount = Math.max(...Object.values(usage.by_resource), 1);
                  const pct = Math.max((count / maxCount) * 100, 2);
                  const color = resourcePalette[i % resourcePalette.length];
                  return (
                    <div key={resource}>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs text-os-subtle">
                          {resourceLabels[resource] ?? resource}
                        </span>
                        <span className="text-xs text-os-text-high font-mono tabular-nums">
                          {count.toLocaleString()} 次
                          {cost > 0 && (
                            <span className="text-os-muted ml-1.5">
                              ¥{(cost / 100).toFixed(2)}
                            </span>
                          )}
                        </span>
                      </div>
                      <div className="h-1.5 bg-os-elevated rounded-full overflow-hidden">
                        <div
                          className={cn("h-full rounded-full transition-all duration-500", color)}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-sm text-os-muted">本月暂无用量记录</p>
            )}

            {/* Summary row */}
            <div className="grid grid-cols-2 gap-4 pt-3 border-t border-os-border">
              <div>
                <span className="text-xs text-os-muted">总调用量</span>
                <p className="text-lg font-semibold text-os-text-high mt-0.5 tabular-nums">
                  {usage.total_events.toLocaleString()}
                </p>
              </div>
              <div>
                <span className="text-xs text-os-muted">预估费用</span>
                <p className="text-lg font-semibold text-os-text-high mt-0.5 tabular-nums">
                  ¥{(usage.total_cost_cents / 100).toFixed(2)}
                </p>
              </div>
            </div>
          </div>
        ) : (
          <p className="text-sm text-os-muted py-4">暂无用量数据</p>
        )}
      </div>

      {/* ════════════════════════════════════════════════
          Section 3 — 邀请好友
          ════════════════════════════════════════════════ */}
      <div className="os-card p-6">
        <SectionHeader icon={Users} title="邀请好友" />

        <div className="space-y-5">
          {/* Referral code */}
          <div>
            <span className="text-xs text-os-muted">邀请码</span>
            {refLoading ? (
              <div className="flex items-center gap-2 mt-1 text-sm text-os-muted">
                <Loader2 size={14} className="animate-spin" />
                加载中...
              </div>
            ) : activeReferral ? (
              <div className="flex items-center gap-2 mt-1.5">
                <code className="text-sm font-mono text-os-text-high bg-os-elevated px-3 py-1.5 rounded border border-os-border select-all">
                  {activeReferral.referral_code}
                </code>
                <button
                  onClick={() => handleCopyReferral(activeReferral.referral_code)}
                  className="p-1.5 rounded text-os-muted hover:text-os-text hover:bg-os-elevated transition-colors shrink-0"
                  title="复制邀请码"
                >
                  {copiedCode === activeReferral.referral_code ? (
                    <Check size={14} className="text-emerald-400" />
                  ) : (
                    <Copy size={14} />
                  )}
                </button>
              </div>
            ) : (
              <div className="mt-1.5">
                <button
                  onClick={handleCreateReferral}
                  disabled={creatingReferral}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium bg-os-accent text-white hover:bg-os-accent/90 disabled:opacity-40 transition-colors"
                >
                  {creatingReferral ? (
                    <Loader2 size={13} className="animate-spin" />
                  ) : (
                    <Gift size={13} />
                  )}
                  生成邀请码
                </button>
              </div>
            )}
          </div>

          {/* Referral stats */}
          {referralStats && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div className="bg-os-elevated rounded-lg p-3 text-center">
                <p className="text-lg font-semibold text-os-text-high tabular-nums">
                  {referralStats.total_referrals}
                </p>
                <span className="text-2xs text-os-muted">总邀请</span>
              </div>
              <div className="bg-os-elevated rounded-lg p-3 text-center">
                <p className="text-lg font-semibold text-os-text-high tabular-nums">
                  {referralStats.completed_referrals}
                </p>
                <span className="text-2xs text-os-muted">已完成</span>
              </div>
              <div className="bg-os-elevated rounded-lg p-3 text-center">
                <p className="text-lg font-semibold text-os-text-high tabular-nums">
                  ¥{(referralStats.total_rewards_cents / 100).toFixed(2)}
                </p>
                <span className="text-2xs text-os-muted">奖励金额</span>
              </div>
            </div>
          )}

          {/* Send invite form */}
          <div className="border-t border-os-border pt-4">
            <span className="text-xs text-os-muted">邀请好友加入</span>
            <div className="flex items-center gap-2 mt-1.5">
              <input
                type="email"
                value={inviteEmail}
                onChange={(e) => {
                  setInviteEmail(e.target.value);
                  setInviteError("");
                  setInviteSuccess(false);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleSendInvite();
                }}
                placeholder="输入好友邮箱"
                className="flex-1 h-9 px-3 rounded bg-os-surface border border-os-border text-sm text-os-text-high placeholder:text-os-muted focus:outline-none focus:border-os-accent transition-colors"
              />
              <button
                onClick={handleSendInvite}
                disabled={inviteSending || !inviteEmail.trim()}
                className="inline-flex items-center gap-1.5 px-4 h-9 rounded text-xs font-medium bg-os-accent text-white hover:bg-os-accent/90 disabled:opacity-40 transition-colors shrink-0"
              >
                {inviteSending ? (
                  <Loader2 size={13} className="animate-spin" />
                ) : (
                  <Send size={13} />
                )}
                发送
              </button>
            </div>
            {inviteError && (
              <p className="text-2xs text-os-danger mt-1.5 flex items-center gap-1">
                <XCircle size={11} />
                {inviteError}
              </p>
            )}
            {inviteSuccess && (
              <p className="text-2xs text-emerald-400 mt-1.5 flex items-center gap-1">
                <Check size={11} />
                邀请已发送
              </p>
            )}
          </div>

          {/* Sent invites history */}
          {invites.length > 0 && (
            <div className="border-t border-os-border pt-4">
              <span className="text-xs text-os-muted">
                已发送邀请 ({invites.length})
              </span>
              <div className="mt-2 space-y-1.5 max-h-48 overflow-y-auto">
                {invites.map((inv) => (
                  <div
                    key={inv.id}
                    className="flex items-center justify-between bg-os-elevated rounded px-3 py-2"
                  >
                    <div className="min-w-0">
                      <span className="text-xs text-os-text-high truncate block">
                        {inv.invitee_email}
                      </span>
                      {inv.expires_at && (
                        <span className="text-2xs text-os-muted">
                          有效期至 {new Date(inv.expires_at).toLocaleDateString("zh-CN")}
                        </span>
                      )}
                    </div>
                    <span
                      className={cn(
                        "text-2xs px-1.5 py-0.5 rounded-full shrink-0 ml-2",
                        inv.status === "accepted"
                          ? "bg-emerald-500/15 text-emerald-400"
                          : inv.status === "expired"
                            ? "bg-zinc-500/15 text-zinc-400"
                            : "bg-amber-500/15 text-amber-400",
                      )}
                    >
                      {inv.status === "accepted"
                        ? "已接受"
                        : inv.status === "expired"
                          ? "已过期"
                          : "待接受"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ════════════════════════════════════════════════
          Section 4 — 优惠券
          ════════════════════════════════════════════════ */}
      <div className="os-card p-6">
        <SectionHeader icon={Ticket} title="优惠券" />

        <div className="space-y-4">
          {/* Redeem input */}
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={couponCode}
              onChange={(e) => {
                setCouponCode(e.target.value);
                setCouponError("");
                setCouponSuccess("");
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleRedeemCoupon();
              }}
              placeholder="输入优惠券代码"
              className="flex-1 h-9 px-3 rounded bg-os-surface border border-os-border text-sm text-os-text-high placeholder:text-os-muted focus:outline-none focus:border-os-accent transition-colors"
            />
            <button
              onClick={handleRedeemCoupon}
              disabled={couponRedeeming || !couponCode.trim()}
              className="inline-flex items-center gap-1.5 px-4 h-9 rounded text-xs font-medium bg-os-accent text-white hover:bg-os-accent/90 disabled:opacity-40 transition-colors shrink-0"
            >
              {couponRedeeming ? (
                <Loader2 size={13} className="animate-spin" />
              ) : (
                <Gift size={13} />
              )}
              兑换
            </button>
          </div>

          {couponError && (
            <p className="text-2xs text-os-danger flex items-center gap-1">
              <XCircle size={11} />
              {couponError}
            </p>
          )}
          {couponSuccess && (
            <p className="text-2xs text-emerald-400 flex items-center gap-1">
              <Check size={11} />
              {couponSuccess}
            </p>
          )}

          {/* Active coupons list */}
          <div className="border-t border-os-border pt-4">
            <span className="text-xs text-os-muted">
              已持有优惠券 ({coupons.filter((c) => c.status === "active").length})
            </span>

            {couponsLoading ? (
              <div className="flex items-center gap-2 mt-2 text-sm text-os-muted">
                <Loader2 size={14} className="animate-spin" />
                加载中...
              </div>
            ) : coupons.length === 0 ? (
              <p className="text-sm text-os-muted mt-2">暂无优惠券</p>
            ) : (
              <div className="mt-2 space-y-1.5 max-h-56 overflow-y-auto">
                {coupons.map((c) => (
                  <div
                    key={c.id}
                    className={cn(
                      "flex items-center justify-between rounded px-3 py-2.5 border",
                      c.status === "active"
                        ? "bg-emerald-500/5 border-emerald-500/15"
                        : "bg-os-elevated border-os-border opacity-60",
                    )}
                  >
                    <div className="min-w-0">
                      <span className="text-sm font-mono font-medium text-os-text-high">
                        {c.code}
                      </span>
                      <span className="text-2xs text-os-muted ml-2">
                        {c.coupon_type === "percentage"
                          ? `${c.value}% 折扣`
                          : `¥${c.value} 减免`}
                        {c.usage_limit > 0 &&
                          ` · 已用 ${c.usage_count}/${c.usage_limit}`}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 shrink-0 ml-2">
                      {c.valid_until && (
                        <span className="text-2xs text-os-muted hidden sm:inline">
                          有效期至 {new Date(c.valid_until).toLocaleDateString("zh-CN")}
                        </span>
                      )}
                      <span
                        className={cn(
                          "text-2xs px-1.5 py-0.5 rounded-full",
                          c.status === "active"
                            ? "bg-emerald-500/15 text-emerald-400"
                            : c.status === "used"
                              ? "bg-blue-500/15 text-blue-400"
                              : "bg-zinc-500/15 text-zinc-400",
                        )}
                      >
                        {c.status === "active"
                          ? "可用"
                          : c.status === "used"
                            ? "已使用"
                            : "已过期"}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ════════════════════════════════════════════════
          Section 5 — 租户信息
          ════════════════════════════════════════════════ */}
      <div className="os-card p-6">
        <SectionHeader icon={Building2} title="租户信息" />

        {tenantLoading ? (
          <div className="flex items-center gap-2 text-sm text-os-muted py-4">
            <Loader2 size={14} className="animate-spin" />
            加载中...
          </div>
        ) : tenant ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <span className="text-xs text-os-muted">名称</span>
                <p className="text-sm text-os-text-high mt-0.5">{tenant.name || "-"}</p>
              </div>
              <div>
                <span className="text-xs text-os-muted">邮箱</span>
                <p className="text-sm text-os-text-high mt-0.5">{tenant.email || "-"}</p>
              </div>
              <div>
                <span className="text-xs text-os-muted">标识符</span>
                <p className="text-sm font-mono text-os-text-high mt-0.5">
                  {tenant.slug || "-"}
                </p>
              </div>
              <div>
                <span className="text-xs text-os-muted">状态</span>
                <p className="text-sm mt-0.5">
                  <span
                    className={cn(
                      "os-badge",
                      tenant.status === "active"
                        ? "bg-emerald-500/15 text-emerald-400"
                        : tenant.status === "trial"
                          ? "bg-amber-500/15 text-amber-400"
                          : "bg-zinc-500/15 text-zinc-400",
                    )}
                  >
                    {tenant.status === "active"
                      ? "活跃"
                      : tenant.status === "trial"
                        ? "试用"
                        : tenant.status}
                  </span>
                </p>
              </div>
              <div>
                <span className="text-xs text-os-muted">成员数量</span>
                <p className="text-lg font-semibold text-os-text-high mt-0.5 tabular-nums">
                  {memberCount !== null ? memberCount : "-"}
                </p>
              </div>
              <div>
                <span className="text-xs text-os-muted">规模</span>
                <p className="text-sm text-os-text-high mt-0.5">
                  {tenant.org_size || "-"}
                </p>
              </div>
              <div>
                <span className="text-xs text-os-muted">行业</span>
                <p className="text-sm text-os-text-high mt-0.5">
                  {tenant.industry || "-"}
                </p>
              </div>
              <div>
                <span className="text-xs text-os-muted">网站</span>
                <p className="text-sm mt-0.5 truncate">
                  {tenant.website ? (
                    <a
                      href={tenant.website}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-os-accent hover:underline"
                    >
                      {tenant.website}
                    </a>
                  ) : (
                    "-"
                  )}
                </p>
              </div>
            </div>
          </div>
        ) : (
          <p className="text-sm text-os-muted py-4">暂无租户信息</p>
        )}
      </div>
    </div>
  );
}
