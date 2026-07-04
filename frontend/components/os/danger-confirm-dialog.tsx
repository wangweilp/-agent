"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle, Loader2, X } from "lucide-react";
import { cn } from "@/lib/utils";

interface DangerConfirmDialogProps {
  open: boolean;
  title: string;
  description: string;
  /** 用户必须手动输入的确认词（如 "DELETE" 或工作区名称） */
  confirmWord: string;
  confirmWordLabel?: string;
  actionLabel: string;
  onConfirm: () => void | Promise<void>;
  onClose: () => void;
  loading?: boolean;
}

export function DangerConfirmDialog({
  open,
  title,
  description,
  confirmWord,
  confirmWordLabel,
  actionLabel,
  onConfirm,
  onClose,
  loading = false,
}: DangerConfirmDialogProps) {
  const [input, setInput] = useState("");

  // 打开时重置输入
  useEffect(() => {
    if (open) setInput("");
  }, [open]);

  // Esc 关闭
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !loading) onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, loading, onClose]);

  const isMatch = input.trim() === confirmWord;

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/20 backdrop-blur-sm px-4"
          onClick={(e) => {
            if (e.target === e.currentTarget && !loading) onClose();
          }}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 8 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="w-full max-w-md overflow-hidden rounded-2xl border border-os-danger/40 bg-os-base shadow-os-lg"
          >
            {/* Header — danger accent */}
            <div className="flex items-center justify-between border-b border-os-danger/20 bg-os-danger/5 px-5 py-3.5">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-os-danger">
                <AlertTriangle size={16} />
                {title}
              </h2>
              <button
                onClick={onClose}
                disabled={loading}
                className="rounded p-1 text-os-subtle transition-colors hover:text-os-text-high disabled:opacity-50"
              >
                <X size={16} />
              </button>
            </div>

            {/* Body */}
            <div className="space-y-4 px-5 py-5">
              <p className="text-xs leading-6 text-os-subtle">{description}</p>

              {/* Confirm word hint */}
              <div className="rounded-lg border border-os-danger/20 bg-os-danger/5 px-3 py-2.5">
                <p className="text-2xs text-os-muted">
                  {confirmWordLabel || "请输入确认词以继续"}
                </p>
                <p className="mt-1 font-mono text-sm font-semibold text-os-danger">
                  {confirmWord}
                </p>
              </div>

              {/* Input */}
              <div>
                <input
                  autoFocus
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder={confirmWord}
                  disabled={loading}
                  className={cn(
                    "h-10 w-full rounded-lg border bg-os-surface px-3 font-mono text-sm text-os-text-high outline-none transition-colors placeholder:text-os-muted",
                    isMatch
                      ? "border-os-danger/50 focus:border-os-danger"
                      : "border-os-border focus:border-os-danger/40",
                  )}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && isMatch && !loading) {
                      void onConfirm();
                    }
                  }}
                />
              </div>

              {/* Actions */}
              <div className="flex gap-2 pt-1">
                <button
                  type="button"
                  onClick={onClose}
                  disabled={loading}
                  className="inline-flex h-10 flex-1 items-center justify-center gap-1.5 rounded-lg border border-os-border bg-os-surface px-3 text-xs font-medium text-os-subtle transition-colors hover:text-os-text-high disabled:opacity-50"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={() => void onConfirm()}
                  disabled={!isMatch || loading}
                  className={cn(
                    "inline-flex h-10 flex-1 items-center justify-center gap-1.5 rounded-lg border px-3 text-xs font-medium transition-all duration-200",
                    isMatch && !loading
                      ? "border-os-danger bg-os-danger/10 text-os-danger hover:bg-os-danger/20"
                      : "border-os-border bg-os-surface text-os-muted cursor-not-allowed",
                  )}
                >
                  {loading ? (
                    <Loader2 size={13} className="animate-spin" />
                  ) : (
                    <AlertTriangle size={13} />
                  )}
                  {loading ? "执行中..." : actionLabel}
                </button>
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
