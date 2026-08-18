"use client";

import { useState, useRef } from "react";
import { motion } from "framer-motion";
import { Mic, Upload, Loader2, CheckCircle2, XCircle } from "lucide-react";
import { api } from "@/services/api";
import { cn } from "@/lib/utils";

interface AudioUploadButtonProps {
  onUploadComplete?: (result: { file_id: string; filename: string; summary: string }) => void;
}

export function AudioUploadButton({ onUploadComplete }: AudioUploadButtonProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [results, setResults] = useState<Array<{ filename: string; summary: string; ok: boolean }>>([]);

  const handleSelect = () => inputRef.current?.click();

  const handleFiles = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;

    setUploading(true);
    setResults([]);

    try {
      const result = await api.audio.upload(files);
      const items = result.items.map((item) => ({
        filename: item.filename,
        summary: item.analysis.summary || "分析完成",
        ok: true,
      }));
      setResults(items);

      // 回调
      if (onUploadComplete && result.items.length > 0) {
        const first = result.items[0];
        onUploadComplete({
          file_id: first.file_id,
          filename: first.filename,
          summary: first.analysis.summary || "",
        });
      }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (err: any) {
      setResults([{ filename: "上传失败", summary: err.message || "未知错误", ok: false }]);
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  return (
    <div className="relative">
      <input
        ref={inputRef}
        type="file"
        accept="audio/*"
        multiple
        className="hidden"
        onChange={handleFiles}
      />

      <button
        type="button"
        onClick={handleSelect}
        disabled={uploading}
        className={cn(
          "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs transition-all",
          "text-os-subtle hover:text-os-text hover:bg-os-elevated",
          "disabled:opacity-50"
        )}
        title="上传音频"
        aria-label="上传音频"
      >
        {uploading ? (
          <Loader2 size={14} className="animate-spin text-os-accent" />
        ) : (
          <Mic size={14} />
        )}
        <span className="hidden sm:inline">音频</span>
      </button>

      {/* Results toast */}
      {results.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          className="absolute top-full mt-2 right-0 w-72 space-y-1 z-50"
        >
          {results.map((r, i) => (
            <div
              key={i}
              className={cn(
                "os-card p-2.5 flex items-start gap-2 text-2xs",
                r.ok ? "border-emerald-400/30" : "border-red-400/30"
              )}
            >
              {r.ok ? (
                <CheckCircle2 size={13} className="text-emerald-700 shrink-0 mt-0.5" />
              ) : (
                <XCircle size={13} className="text-red-700 shrink-0 mt-0.5" />
              )}
              <div className="min-w-0">
                <p className="text-os-text-high truncate font-medium">{r.filename}</p>
                <p className="text-os-subtle line-clamp-2">{r.summary}</p>
              </div>
            </div>
          ))}
        </motion.div>
      )}
    </div>
  );
}
