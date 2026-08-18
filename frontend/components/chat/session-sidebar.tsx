"use client";

import { useSessionStore } from "@/stores/session-store";
import { MessageSquare, Plus, Trash2, MessagesSquare } from "lucide-react";
import { cn, formatDate } from "@/lib/utils";

export function SessionSidebar() {
  const { sessions, activeId, setActive, addSession, removeSession } = useSessionStore();

  return (
    <div className="h-full flex flex-col bg-os-base/90 backdrop-blur-sm">
      <div className="flex items-center justify-between px-4 h-10 border-b border-os-border shrink-0">
        <div className="flex items-center gap-2">
          <MessagesSquare size={13} className="text-os-accent/70" />
          <span className="text-xs font-medium text-os-text-high">会话</span>
        </div>
        <button
          onClick={() =>
            addSession({
              id: crypto.randomUUID(),
              title: "新对话",
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
              message_count: 0,
            })
          }
          className="w-6 h-6 rounded-md flex items-center justify-center text-os-subtle hover:text-os-accent hover:bg-os-accent/10 transition-all"
          title="新建会话"
          aria-label="新建会话"
        >
          <Plus size={14} />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
        {sessions.length === 0 && (
          <div className="text-center py-10 space-y-3">
            <div className="w-10 h-10 rounded-xl bg-os-elevated border border-os-border/50 flex items-center justify-center mx-auto">
              <MessageSquare size={18} className="text-os-subtle" />
            </div>
            <div>
              <p className="text-xs text-os-text-high/80 font-medium">暂无会话</p>
              <p className="text-2xs text-os-subtle mt-0.5">点击右上角 + 开始新对话</p>
            </div>
          </div>
        )}
        {sessions.map((s) => (
          <div
            key={s.id}
            role="button"
            tabIndex={0}
            onClick={() => setActive(s.id)}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setActive(s.id); } }}
            className={cn(
              "w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-left transition-all group cursor-pointer",
              s.id === activeId
                ? "bg-os-accent/10 text-os-accent border border-os-accent/10"
                : "text-os-text hover:bg-os-elevated/80 border border-transparent",
            )}
          >
            <div className={cn(
              "w-7 h-7 rounded-lg flex items-center justify-center shrink-0",
              s.id === activeId ? "bg-os-accent/10" : "bg-os-elevated",
            )}>
              <MessageSquare size={13} className={s.id === activeId ? "text-os-accent" : "text-os-subtle"} />
            </div>
            <div className="flex-1 min-w-0">
              <p className={cn("text-xs truncate", s.id === activeId ? "text-os-accent" : "text-os-text-high")}>{s.title}</p>
              <p className="text-2xs text-os-subtle">{formatDate(s.updated_at)}</p>
            </div>
            <button
              onClick={(e) => { e.stopPropagation(); removeSession(s.id); }}
              className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100 p-1 rounded text-os-subtle hover:text-red-700 hover:bg-red-400/10 transition-all"
              aria-label="删除会话"
            >
              <Trash2 size={12} />
            </button>
          </div>
        ))}
      </div>

      {/* 底部提示 */}
      <div className="border-t border-os-border/50 px-4 py-2">
        <p className="text-2xs text-os-subtle text-center">
          {sessions.length > 0 ? `${sessions.length} 个会话` : "开始你的第一段对话"}
        </p>
      </div>
    </div>
  );
}
