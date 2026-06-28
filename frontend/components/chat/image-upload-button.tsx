"use client";

import { useRef, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Image as ImageIcon, Upload, X, Check, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "@/stores/ui-store";
import { api } from "@/services/api";

interface UploadItem {
  file: File;
  preview: string;
  status: "pending" | "uploading" | "done" | "error";
  taskCount?: number;
  summary?: string;
  error?: string;
}

interface Props {
  onUploaded: (summary: string) => void;
  disabled?: boolean;
}

export function ImageUploadButton({ onUploaded, disabled }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [items, setItems] = useState<UploadItem[]>([]);
  const [isDragging, setIsDragging] = useState(false);

  const handleFiles = useCallback(async (files: FileList) => {
    const fileArray = Array.from(files).filter((f) => f.type.startsWith("image/"));
    if (fileArray.length === 0) return;

    const newItems: UploadItem[] = fileArray.map((file) => ({
      file,
      preview: "",
      status: "pending" as const,
    }));

    // 生成预览
    for (let i = 0; i < fileArray.length; i++) {
      const reader = new FileReader();
      const idx = i;
      reader.onload = () => {
        setItems((prev) => {
          const updated = [...prev];
          if (updated[idx]) updated[idx] = { ...updated[idx], preview: reader.result as string };
          return updated;
        });
      };
      reader.readAsDataURL(fileArray[i]);
    }

    setItems(newItems);

    // 逐个上传
    const summaries: string[] = [];
    for (let i = 0; i < fileArray.length; i++) {
      setItems((prev) => {
        const updated = [...prev];
        if (updated[i]) updated[i] = { ...updated[i], status: "uploading" };
        return updated;
      });

      try {
        const data = await api.upload([fileArray[i]]) as {
          items?: Array<{ task_count?: number; analysis?: { summary?: string } }>;
        };
        const item = data.items?.[0];
        const taskCount = item?.task_count ?? 0;
        const summary = item?.analysis?.summary || "";

        summaries.push(`[图片: ${fileArray[i].name}]\n${summary}`);

        setItems((prev) => {
          const updated = [...prev];
          if (updated[i]) {
            updated[i] = {
              ...updated[i],
              status: "done",
              taskCount,
              summary,
            };
          }
          return updated;
        });
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      } catch (e: any) {
        setItems((prev) => {
          const updated = [...prev];
          if (updated[i]) {
            updated[i] = { ...updated[i], status: "error", error: e.message };
          }
          return updated;
        });
      }
    }

    // 全部完成 → 注入聊天
    if (summaries.length > 0) {
      onUploaded(summaries.join("\n"));
      toast.success("图片上传完成", `${summaries.length} 张图片已解析并注入对话`);
    }
  }, [onUploaded]);

  const dismiss = (idx: number) => {
    setItems((prev) => prev.filter((_, i) => i !== idx));
    if (inputRef.current) inputRef.current.value = "";
  };

  const uploading = items.some((it) => it.status === "uploading");

  return (
    <div
      className="relative flex items-center gap-1"
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled && !uploading) setIsDragging(true);
      }}
      onDragLeave={(e) => {
        e.preventDefault();
        setIsDragging(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        setIsDragging(false);
        if (!disabled && !uploading && e.dataTransfer.files.length > 0) {
          handleFiles(e.dataTransfer.files);
        }
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept="image/png,image/jpeg,image/gif,image/webp"
        multiple
        onChange={(e) => {
          if (e.target.files && e.target.files.length > 0) handleFiles(e.target.files);
        }}
        className="hidden"
      />

      <button
        onClick={() => inputRef.current?.click()}
        disabled={disabled || uploading}
        className={cn(
          "shrink-0 w-9 h-9 rounded-lg transition-all flex items-center justify-center relative",
          isDragging
            ? "border-2 border-dashed border-os-accent/50 bg-os-accent/5 text-os-accent scale-110"
            : "text-os-subtle hover:text-os-accent hover:bg-os-surface-hover disabled:opacity-30 disabled:cursor-not-allowed",
        )}
        title="上传图片（支持多选 / 拖拽）"
      >
        {uploading ? (
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ repeat: Infinity, duration: 1, ease: "linear" }}
          >
            <Upload size={15} />
          </motion.div>
        ) : isDragging ? (
          <motion.div
            animate={{ y: [0, -3, 0] }}
            transition={{ repeat: Infinity, duration: 1.2, ease: "easeInOut" }}
          >
            <Upload size={15} />
          </motion.div>
        ) : (
          <ImageIcon size={15} />
        )}
      </button>

      {/* 上传状态条 */}
      <AnimatePresence>
        {items.length > 0 && (
          <motion.div
            initial={{ opacity: 0, width: 0 }}
            animate={{ opacity: 1, width: "auto" }}
            exit={{ opacity: 0, width: 0 }}
            className="flex items-center gap-1.5 overflow-hidden"
          >
            {items.map((it, i) => (
              <div
                key={i}
                className="relative w-8 h-8 rounded overflow-hidden shrink-0 border border-os-border"
                title={it.status === "done" ? `已解析·${it.taskCount ?? 0} 条记忆` : it.status === "error" ? it.error : "上传中"}
              >
                {it.preview ? (
                  <img src={it.preview} alt="" className="w-full h-full object-cover" />
                ) : (
                  <div className="w-full h-full bg-os-surface-hover flex items-center justify-center">
                    <Upload size={10} className="text-os-muted animate-pulse" />
                  </div>
                )}
                {/* 状态角标 */}
                <div className="absolute -top-1 -right-1">
                  {it.status === "done" && <Check size={10} className="text-emerald-400 bg-os-surface rounded-full" />}
                  {it.status === "uploading" && (
                    <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 0.8, ease: "linear" }}>
                      <Upload size={10} className="text-os-accent" />
                    </motion.div>
                  )}
                  {it.status === "error" && <AlertTriangle size={10} className="text-red-400" />}
                </div>
              </div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
