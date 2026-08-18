"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  Brain,
  Database,
  ShieldCheck,
  Loader2,
  ArrowRight,
  Check,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ── 引导步骤配置 ──

const TOTAL_STEPS = 3;

const BOOT_LOGS = [
  "> [OK] 认知内核模块已加载",
  "> [OK] 记忆保险库已分配",
  "> [OK] 安全控制面已建立",
  "> [OK] 执行约束层已就绪",
  "> AWAITING 用户配置...",
];

// ── 记忆保留策略卡片 ──

interface RetentionPolicy {
  id: string;
  label: string;
  desc: string;
  icon: typeof Database;
  retention: string;
  accent: string;
}

const RETENTION_POLICIES: RetentionPolicy[] = [
  {
    id: "compact",
    label: "精简模式",
    desc: "仅保留高重要性记忆，定期清理冗余",
    icon: Database,
    retention: "30 天 · 上限 1,000 条",
    accent: "text-blue-700",
  },
  {
    id: "balanced",
    label: "均衡模式",
    desc: "兼顾记忆深度与存储成本，推荐大多数用户",
    icon: Brain,
    retention: "90 天 · 上限 10,000 条",
    accent: "text-indigo-700",
  },
  {
    id: "archival",
    label: "归档模式",
    desc: "全量保留所有记忆，适合长期知识沉淀",
    icon: ShieldCheck,
    retention: "永久 · 上限 100,000 条",
    accent: "text-violet-700",
  },
];

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [orgName, setOrgName] = useState("");
  const [selectedPolicy, setSelectedPolicy] = useState<string>("balanced");
  const [booting, setBooting] = useState(false);
  const [bootProgress, setBootProgress] = useState(0);
  const [visibleLogs, setVisibleLogs] = useState<string[]>([]);

  // 终端启动日志打字机效果 (Step 3 进入时触发)
  useEffect(() => {
    if (step !== 2 || !booting) return;
    let i = 0;
    const timer = setInterval(() => {
      if (i < BOOT_LOGS.length) {
        setVisibleLogs((prev) => [...prev, BOOT_LOGS[i]]);
        i++;
      } else {
        clearInterval(timer);
      }
    }, 280);
    return () => clearInterval(timer);
  }, [step, booting]);

  // 启动进度条动画
  useEffect(() => {
    if (step !== 2 || !booting) return;
    setBootProgress(0);
    const timer = setInterval(() => {
      setBootProgress((p) => {
        if (p >= 100) {
          clearInterval(timer);
          return 100;
        }
        return p + 2;
      });
    }, 60);
    return () => clearInterval(timer);
  }, [step, booting]);

  const handleEnterOS = useCallback(() => {
    // localStorage 模拟"已完成引导"状态 (纯 UI 走查)
    try {
      localStorage.setItem("zhiwei_os_onboarded", "true");
      localStorage.setItem("zhiwei_os_org_name", orgName || "My Workspace");
      localStorage.setItem("zhiwei_os_retention_policy", selectedPolicy);
    } catch {
      // localStorage 不可用时静默降级
    }
    router.push("/home");
  }, [orgName, selectedPolicy, router]);

  const handleStep3Enter = useCallback(() => {
    setBooting(true);
  }, []);

  const canProceedStep0 = orgName.trim().length >= 2;

  return (
    <div className="relative min-h-screen overflow-hidden flex items-center justify-center p-4 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-white via-os-base to-os-base">
      {/* 网格背景层 */}
      <div className="absolute inset-0 bg-grid-subtle opacity-30 pointer-events-none" />

      {/* 装饰性光晕 */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[500px] h-[500px] rounded-full bg-os-accent/5 blur-3xl pointer-events-none" />

      <div className="relative w-full max-w-xl z-10">
        {/* Logo + 进度指示 */}
        <div className="mb-8 flex flex-col items-center">
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.3 }}
            className="w-12 h-12 rounded-xl bg-os-accent/15 flex items-center justify-center mb-4 ring-1 ring-os-accent/20 shadow-[0_0_20px_rgba(129,140,248,0.2)]"
          >
            <Zap size={22} className="text-os-accent" />
          </motion.div>
          <h1 className="text-xl font-semibold text-os-text-high tracking-tight">知维 OS</h1>
          <p className="text-sm text-os-subtle mt-1.5 font-mono">
            系统初始化向导
          </p>

          {/* 步骤进度指示器 */}
          <div className="mt-5 flex items-center gap-2">
            {Array.from({ length: TOTAL_STEPS }).map((_, i) => (
              <div
                key={i}
                className={cn(
                  "h-1 rounded-full transition-all duration-300",
                  i === step
                    ? "w-8 bg-os-accent shadow-[0_0_8px_rgba(129,140,248,0.6)]"
                    : i < step
                      ? "w-4 bg-os-accent/50"
                      : "w-4 bg-os-border",
                )}
              />
            ))}
          </div>
        </div>

        {/* ── 步骤卡片容器 ── */}
        <div className="backdrop-blur-2xl bg-os-surface/40 border border-os-border/50 shadow-os-lg rounded-2xl p-6 min-h-[360px] flex flex-col">
          <AnimatePresence mode="wait">
            {/* ── Step 1: Initializing Cognitive Core ── */}
            {step === 0 && (
              <motion.div
                key="step-0"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.2, ease: "easeOut" }}
                className="flex flex-col flex-1"
              >
                <div className="mb-5">
                  <div className="flex items-center gap-2 mb-1">
                    <Brain size={16} className="text-os-accent" />
                    <span className="font-mono text-2xs text-os-subtle uppercase tracking-wider">
                      步骤 01 / 03
                    </span>
                  </div>
                  <h2 className="text-lg font-semibold text-os-text-high">
                    初始化认知内核
                  </h2>
                  <p className="text-sm text-os-subtle mt-1">初始化认知内核 · 配置你的身份</p>
                </div>

                <div className="flex-1 space-y-4">
                  <div>
                    <label className="block text-xs text-os-subtle mb-1.5 font-mono">
                      组织 / 个人名称
                    </label>
                    <input
                      autoFocus
                      value={orgName}
                      onChange={(e) => setOrgName(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && canProceedStep0) setStep(1);
                      }}
                      placeholder="例如：知维实验室"
                      className="w-full h-11 px-3 rounded-lg bg-os-surface border border-os-border text-sm text-os-text-high placeholder:text-os-subtle focus:outline-none focus:border-os-accent/50 focus:ring-1 focus:ring-os-accent/20 transition-all"
                    />
                    <p className="mt-2 font-mono text-2xs text-os-subtle">
                      &gt; 此名称将作为你的认知工作区标识
                    </p>
                  </div>
                </div>

                <div className="mt-6 flex justify-end">
                  <button
                    onClick={() => setStep(1)}
                    disabled={!canProceedStep0}
                    className={cn(
                      "inline-flex h-10 items-center gap-2 rounded-lg px-5 text-sm font-medium transition-all",
                      canProceedStep0
                        ? "bg-os-accent text-white hover:bg-os-accent/90 shadow-os-glow"
                        : "cursor-not-allowed border border-os-border bg-os-surface-muted text-os-subtle",
                    )}
                  >
                    继续
                    <ArrowRight size={14} />
                  </button>
                </div>
              </motion.div>
            )}

            {/* ── Step 2: Provisioning Memory Vault ── */}
            {step === 1 && (
              <motion.div
                key="step-1"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.2, ease: "easeOut" }}
                className="flex flex-col flex-1"
              >
                <div className="mb-5">
                  <div className="flex items-center gap-2 mb-1">
                    <Database size={16} className="text-os-accent" />
                    <span className="font-mono text-2xs text-os-subtle uppercase tracking-wider">
                      步骤 02 / 03
                    </span>
                  </div>
                  <h2 className="text-lg font-semibold text-os-text-high">
                    配置记忆保险库
                  </h2>
                  <p className="text-sm text-os-subtle mt-1">分配记忆保险库 · 选择保留策略</p>
                </div>

                <div className="flex-1 space-y-2.5">
                  {RETENTION_POLICIES.map((policy) => {
                    const isSelected = selectedPolicy === policy.id;
                    const Icon = policy.icon;
                    return (
                      <button
                        key={policy.id}
                        type="button"
                        onClick={() => setSelectedPolicy(policy.id)}
                        className={cn(
                          "w-full flex items-start gap-3 rounded-xl border p-3.5 text-left transition-all duration-200",
                          isSelected
                            ? "border-os-accent/50 bg-os-accent/10 shadow-[0_0_15px_rgba(129,140,248,0.15)]"
                            : "border-os-border/50 bg-os-surface/30 hover:border-os-muted/50",
                        )}
                      >
                        <div className={cn(
                          "w-9 h-9 rounded-lg flex items-center justify-center border shrink-0",
                          isSelected
                            ? "bg-os-accent/15 border-os-accent/30"
                            : "bg-os-elevated border-os-border",
                        )}>
                          <Icon size={16} className={isSelected ? policy.accent : "text-os-muted"} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-sm font-medium text-os-text-high">{policy.label}</span>
                            {isSelected && (
                              <Check size={14} className="text-os-accent shrink-0" />
                            )}
                          </div>
                          <p className="mt-0.5 text-xs text-os-subtle">{policy.desc}</p>
                          <p className={cn("mt-1 font-mono text-2xs", isSelected ? policy.accent : "text-os-subtle")}>
                            {policy.retention}
                          </p>
                        </div>
                      </button>
                    );
                  })}
                </div>

                <div className="mt-6 flex justify-between">
                  <button
                    onClick={() => setStep(0)}
                    className="inline-flex h-10 items-center gap-2 rounded-lg border border-os-border px-4 text-sm font-medium text-os-subtle transition-colors hover:text-os-text-high"
                  >
                    返回
                  </button>
                  <button
                    onClick={() => setStep(2)}
                    className="inline-flex h-10 items-center gap-2 rounded-lg bg-os-accent px-5 text-sm font-medium text-white transition-colors hover:bg-os-accent/90 shadow-os-glow"
                  >
                    继续
                    <ArrowRight size={14} />
                  </button>
                </div>
              </motion.div>
            )}

            {/* ── Step 3: Establishing Security Plane ── */}
            {step === 2 && (
              <motion.div
                key="step-2"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.2, ease: "easeOut" }}
                className="flex flex-col flex-1"
              >
                <div className="mb-5">
                  <div className="flex items-center gap-2 mb-1">
                    <ShieldCheck size={16} className="text-os-accent" />
                    <span className="font-mono text-2xs text-os-subtle uppercase tracking-wider">
                      步骤 03 / 03
                    </span>
                  </div>
                  <h2 className="text-lg font-semibold text-os-text-high">
                    建立安全控制面
                  </h2>
                  <p className="text-sm text-os-subtle mt-1">建立安全隔离 · 启动认知内核</p>
                </div>

                <div className="flex-1 flex flex-col items-center justify-center">
                  {!booting ? (
                    // 启动前 — 展示启动按钮
                    <div className="text-center space-y-4">
                      <div className="w-16 h-16 mx-auto rounded-2xl bg-os-accent/10 border border-os-accent/30 flex items-center justify-center">
                        <ShieldCheck size={28} className="text-os-accent" />
                      </div>
                      <div>
                        <p className="text-sm text-os-text-high font-medium">准备就绪</p>
                        <p className="mt-1 text-xs text-os-subtle">
                          配置已确认，即将启动认知内核
                        </p>
                      </div>
                      <button
                        onClick={handleStep3Enter}
                        className="inline-flex h-11 items-center gap-2 rounded-lg bg-os-accent px-6 text-sm font-medium text-white transition-all hover:bg-os-accent/90 shadow-os-glow"
                      >
                        <Zap size={15} />
                        启动认知内核
                      </button>
                    </div>
                  ) : bootProgress < 100 ? (
                    // 启动中 — 流光加载动画 + 终端日志
                    <div className="w-full space-y-4">
                      {/* 流光进度条 */}
                      <div className="relative w-full h-2 bg-os-elevated rounded-full overflow-hidden">
                        <motion.div
                          className="relative h-full rounded-full bg-gradient-to-r from-os-accent to-cyan-400"
                          animate={{ width: `${bootProgress}%` }}
                          transition={{ duration: 0.06, ease: "linear" }}
                        >
                          <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/50 to-transparent animate-pulse" />
                        </motion.div>
                      </div>
                      <p className="text-center font-mono text-2xs text-os-subtle">
                        正在启动认知内核... {bootProgress}%
                      </p>

                      {/* 终端启动日志 */}
                      <div className="rounded-lg border border-os-border/60 bg-slate-50 p-3 h-32 overflow-y-auto font-mono text-2xs space-y-0.5">
                        {visibleLogs.map((log, i) => (
                          <motion.div
                            key={i}
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            transition={{ duration: 0.15 }}
                            className={cn(
                              "leading-4",
                              (log ?? "").includes("[OK]") && "text-emerald-700",
                              (log ?? "").includes("AWAITING") && "text-indigo-700",
                              !(log ?? "").includes("[OK]") && !(log ?? "").includes("AWAITING") && "text-os-subtle",
                            )}
                          >
                            {log ?? ""}
                          </motion.div>
                        ))}
                        {visibleLogs.length < BOOT_LOGS.length && (
                          <span className="inline-block w-1.5 h-3 bg-os-accent animate-pulse align-middle" />
                        )}
                      </div>
                    </div>
                  ) : (
                    // 启动完成 — 发光主按钮
                    <motion.div
                      initial={{ opacity: 0, scale: 0.95 }}
                      animate={{ opacity: 1, scale: 1 }}
                      transition={{ duration: 0.3 }}
                      className="text-center space-y-5"
                    >
                      <motion.div
                        initial={{ scale: 0.8 }}
                        animate={{ scale: 1 }}
                        className="w-20 h-20 mx-auto rounded-2xl bg-os-success/10 border border-os-success/40 flex items-center justify-center shadow-[0_0_30px_rgba(52,211,153,0.3)]"
                      >
                        <Check size={36} className="text-emerald-700" />
                      </motion.div>
                      <div>
                        <p className="text-base font-semibold text-os-text-high">
                          认知内核已就绪
                        </p>
                        <p className="mt-1 text-xs text-os-subtle">
                          认知内核已启动 · 欢迎进入知维 OS
                        </p>
                      </div>
                      <motion.button
                        onClick={handleEnterOS}
                        whileHover={{ scale: 1.02 }}
                        whileTap={{ scale: 0.98 }}
                        className={cn(
                          "inline-flex h-12 items-center gap-2 rounded-xl px-8 text-base font-semibold text-white",
                          "bg-os-accent hover:bg-os-accent/90",
                          "shadow-[0_0_30px_rgba(129,140,248,0.5)] hover:shadow-[0_0_40px_rgba(129,140,248,0.7)]",
                          "transition-shadow",
                        )}
                      >
                        <Zap size={18} />
                        进入知维 OS
                      </motion.button>
                    </motion.div>
                  )}
                </div>

                {!booting && (
                  <div className="mt-6 flex justify-start">
                    <button
                      onClick={() => setStep(1)}
                      className="inline-flex h-10 items-center gap-2 rounded-lg border border-os-border px-4 text-sm font-medium text-os-subtle transition-colors hover:text-os-text-high"
                    >
                      返回
                    </button>
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* 底部状态条 */}
        <div className="mt-4 flex items-center justify-between font-mono text-2xs text-os-subtle">
          <span className="inline-flex items-center gap-1.5">
            <Loader2 size={10} className={cn(!booting && "hidden", "animate-spin")} />
            zhiwei-os://onboarding
          </span>
          <span>步骤 {step + 1} / {TOTAL_STEPS}</span>
        </div>
      </div>
    </div>
  );
}
