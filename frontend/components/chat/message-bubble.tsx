"use client";

import { motion } from "framer-motion";
import { Brain, User } from "lucide-react";
import { cn, formatDate } from "@/lib/utils";
import type { Message } from "@/types";

export function MessageBubble({
  message,
  streaming,
}: {
  message: Message;
  streaming?: boolean;
}) {
  const isUser = message.role === "user";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn("flex gap-3", isUser && "flex-row-reverse")}
    >
      {/* Avatar */}
      <div
        className={cn(
          "w-7 h-7 rounded-lg flex items-center justify-center shrink-0",
          isUser ? "bg-os-accent/10" : "bg-os-elevated border border-os-border",
        )}
      >
        {isUser ? (
          <User size={14} className="text-os-accent" />
        ) : (
          <Brain size={14} className="text-os-subtle" />
        )}
      </div>

      {/* Content */}
      <div className={cn("max-w-[80%]", isUser && "items-end")}>
        <div
          className={cn(
            "rounded-xl px-4 py-2.5 text-sm leading-relaxed",
            isUser
              ? "bg-os-accent/10 text-os-text-high border border-os-accent/10"
              : "bg-os-elevated text-os-text-high border border-os-border",
          )}
        >
          <p className="whitespace-pre-wrap break-words">{message.content}</p>
          {streaming && (
            <span className="inline-block w-1.5 h-4 bg-os-accent ml-0.5 animate-pulse align-text-bottom" />
          )}
        </div>
        {message.timestamp && (
          <p className="text-2xs text-os-muted mt-1 px-1">{formatDate(message.timestamp)}</p>
        )}
      </div>
    </motion.div>
  );
}
