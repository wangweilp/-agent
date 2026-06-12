"use client";
import { useEffect, useState } from "react";
import { AlertTriangle, Copy, Eye, EyeOff, X } from "lucide-react";

export function ApiKeyReveal({ rawKey, onClose }: { rawKey: string; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    return () => { /* clear on unmount */ };
  }, []);

  async function handleCopy() {
    try { await navigator.clipboard.writeText(rawKey); setCopied(true); setTimeout(() => setCopied(false), 2000); }
    catch { /* clipboard not available */ }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
      <div className="w-full max-w-md rounded-lg border border-os-border bg-os-base shadow-2xl">
        <div className="flex items-center justify-between border-b border-os-border px-5 py-3">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-emerald-300">
            <AlertTriangle size={16} className="text-amber-400" />
            API Key 已创建
          </h2>
          <button onClick={onClose} className="rounded p-1 text-os-subtle hover:text-os-text-high"><X size={16} /></button>
        </div>
        <div className="px-5 py-4 space-y-3">
          <p className="text-xs leading-5 text-amber-300">
            ⚠ 请立即复制此密钥。关闭此窗口后将无法再次查看。
          </p>
          <div className="flex items-center gap-2 rounded-md border border-os-border bg-os-elevated p-3 font-mono text-xs text-os-text-high break-all">
            {visible ? rawKey : "•".repeat(Math.min(rawKey.length, 48))}
          </div>
          <div className="flex gap-2">
            <button onClick={handleCopy} className="inline-flex h-8 items-center gap-1.5 rounded-md bg-os-accent px-3 text-xs font-medium text-white hover:bg-os-accent/90">
              <Copy size={13} />{copied ? "已复制" : "复制"}
            </button>
            <button onClick={() => setVisible(!visible)} className="inline-flex h-8 items-center gap-1.5 rounded-md border border-os-border px-3 text-xs text-os-subtle hover:text-os-text-high">
              {visible ? <EyeOff size={13} /> : <Eye size={13} />}
              {visible ? "隐藏" : "显示"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
