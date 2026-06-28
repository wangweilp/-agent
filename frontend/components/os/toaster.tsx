"use client";

import { motion, AnimatePresence } from "framer-motion";
import { X, CheckCircle2, AlertTriangle, AlertCircle, Info } from "lucide-react";
import { useUIStore, type ToastType } from "@/stores/ui-store";
import { cn } from "@/lib/utils";

// ── 状态指示条与图标映射 ──

const toastConfig: Record<ToastType, {
  bar: string;
  icon: typeof CheckCircle2;
  iconColor: string;
}> = {
  success: { bar: "bg-emerald-400", icon: CheckCircle2, iconColor: "text-emerald-400" },
  warning: { bar: "bg-amber-400", icon: AlertTriangle, iconColor: "text-amber-400" },
  danger: { bar: "bg-red-400", icon: AlertCircle, iconColor: "text-red-400" },
  info: { bar: "bg-os-accent", icon: Info, iconColor: "text-os-accent" },
};

// ── Toaster ──

export function Toaster() {
  const { toasts, dismissToast } = useUIStore();

  return (
    <div className="fixed bottom-6 right-6 z-[200] flex flex-col gap-2 w-80 pointer-events-none">
      <AnimatePresence>
        {toasts.map((t) => {
          const config = toastConfig[t.type];
          const Icon = config.icon;
          return (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, x: 20, scale: 0.96 }}
              animate={{ opacity: 1, x: 0, scale: 1 }}
              exit={{ opacity: 0, x: 20, scale: 0.96 }}
              transition={{ duration: 0.2, ease: "easeOut" }}
              className="pointer-events-auto relative flex items-start gap-3 pl-3 pr-3 py-3 rounded-xl border border-os-border/50 bg-os-surface/95 backdrop-blur-xl shadow-os-lg overflow-hidden"
            >
              {/* 左侧状态指示条 */}
              <div className={cn("absolute left-0 top-0 bottom-0 w-1", config.bar)} />

              {/* 状态图标 */}
              <Icon size={16} className={cn("shrink-0 mt-0.5", config.iconColor)} />

              {/* 内容 */}
              <div className="flex-1 min-w-0">
                <p className="text-sm text-os-text-high font-medium">{t.message}</p>
                {t.description && (
                  <p className="text-xs text-os-muted mt-0.5">{t.description}</p>
                )}
              </div>

              {/* 关闭按钮 */}
              <button
                onClick={() => dismissToast(t.id)}
                className="shrink-0 text-os-muted hover:text-os-text-high transition-colors"
              >
                <X size={14} />
              </button>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
