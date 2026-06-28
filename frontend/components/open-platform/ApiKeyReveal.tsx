"use client";
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle, Copy, Eye, EyeOff, KeyRound, X } from "lucide-react";
import { toast } from "@/stores/ui-store";
import { cn } from "@/lib/utils";

export function ApiKeyReveal({ rawKey, onClose }: { rawKey: string; onClose: () => void }) {
  const [visible, setVisible] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(rawKey);
      toast.success("密钥已复制", "请妥善保管，此密钥仅显示一次");
    } catch {
      toast.warning("复制失败", "请手动选择密钥文本复制");
    }
  }

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.15 }}
        className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 backdrop-blur-sm px-4"
        onClick={(e) => {
          if (e.target === e.currentTarget) onClose();
        }}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.96, y: 8 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.96, y: 8 }}
          transition={{ duration: 0.2, ease: "easeOut" }}
          className="w-full max-w-md overflow-hidden rounded-2xl border border-os-border bg-os-base shadow-2xl"
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-os-border px-5 py-3.5">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-os-success">
              <KeyRound size={16} className="text-os-success" />
              API Key 已创建
            </h2>
            <button
              onClick={onClose}
              className="rounded p-1 text-os-subtle transition-colors hover:text-os-text-high"
            >
              <X size={16} />
            </button>
          </div>

          <div className="space-y-4 px-5 py-5">
            {/* Warning banner */}
            <div className="flex items-start gap-2 rounded-lg border border-amber-400/20 bg-amber-400/5 px-3 py-2.5">
              <AlertTriangle size={14} className="mt-0.5 shrink-0 text-amber-400" />
              <p className="text-xs leading-5 text-amber-300">
                请立即复制此密钥。关闭此窗口后将<strong className="font-semibold">无法再次查看</strong>。
              </p>
            </div>

            {/* Key display — blur by default, reveal on demand */}
            <div className="relative">
              <div
                className={cn(
                  "flex items-center gap-2 overflow-x-auto rounded-lg border border-os-border bg-os-elevated p-3 font-mono text-xs text-os-text-high break-all transition-all duration-300",
                  !visible && "blur-sm select-none",
                )}
              >
                {rawKey}
              </div>

              {/* Reveal toggle */}
              <button
                onClick={() => setVisible(!visible)}
                className="absolute right-2 top-1/2 -translate-y-1/2 inline-flex h-7 w-7 items-center justify-center rounded-md border border-os-border bg-os-surface text-os-subtle transition-colors hover:text-os-text-high"
                title={visible ? "隐藏" : "显示"}
              >
                {visible ? <EyeOff size={13} /> : <Eye size={13} />}
              </button>
            </div>

            {/* Actions */}
            <div className="flex gap-2 pt-1">
              <button
                onClick={handleCopy}
                className="inline-flex h-10 flex-1 items-center justify-center gap-1.5 rounded-lg bg-os-accent px-3 text-xs font-medium text-white transition-colors hover:bg-os-accent/90"
              >
                <Copy size={13} />
                复制密钥
              </button>
              <button
                onClick={() => setVisible(!visible)}
                className="inline-flex h-10 flex-1 items-center justify-center gap-1.5 rounded-lg border border-os-border bg-os-surface px-3 text-xs font-medium text-os-subtle transition-colors hover:text-os-text-high"
              >
                {visible ? <EyeOff size={13} /> : <Eye size={13} />}
                {visible ? "隐藏" : "显示"}
              </button>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
