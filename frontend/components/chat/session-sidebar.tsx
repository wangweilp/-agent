"use client";

import { useSessionStore } from "@/stores/session-store";
import { MessageSquare, Plus, Trash2 } from "lucide-react";
import { cn, formatDate } from "@/lib/utils";

export function SessionSidebar() {
  const { sessions, activeId, setActive, addSession, removeSession } = useSessionStore();

  return (
    <div className="h-full flex flex-col bg-os-base">
      <div className="flex items-center justify-between px-4 h-10 border-b border-os-border">
        <span className="text-xs font-medium text-os-text-high">会话</span>
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
          className="w-6 h-6 rounded flex items-center justify-center text-os-subtle hover:text-os-text hover:bg-os-elevated transition-all"
        >
          <Plus size={14} />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
        {sessions.length === 0 && (
          <p className="text-2xs text-os-muted text-center py-6">暂无会话，点击 + 创建</p>
        )}
        {sessions.map((s) => (
          <div
            key={s.id}
            role="button"
            tabIndex={0}
            onClick={() => setActive(s.id)}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setActive(s.id); } }}
            className={cn(
              "w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-left transition-all group cursor-pointer",
              s.id === activeId
                ? "bg-os-accent/10 text-os-accent"
                : "text-os-text hover:bg-os-elevated",
            )}
          >
            <MessageSquare size={13} className="shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-xs truncate">{s.title}</p>
              <p className="text-2xs text-os-muted">{formatDate(s.updated_at)}</p>
            </div>
            <button
              onClick={(e) => { e.stopPropagation(); removeSession(s.id); }}
              className="opacity-0 group-hover:opacity-100 text-os-subtle hover:text-red-400 transition-all"
              aria-label="删除会话"
            >
              <Trash2 size={12} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
