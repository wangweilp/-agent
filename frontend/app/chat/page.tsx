"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Send,
  Sparkles,
  Brain,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { useChatStore } from "@/stores/chat-store";
import { useAgentStore } from "@/stores/agent-store";
import { api } from "@/services/api";
import { PageTransition } from "@/components/animations/page-transition";
import { MessageBubble } from "@/components/chat/message-bubble";
import { ToolCallCard } from "@/components/chat/tool-call-card";
import { SessionSidebar } from "@/components/chat/session-sidebar";
import { ActivityPanel } from "@/components/chat/activity-panel";
import type { ToolCall } from "@/types";

export default function ChatPage() {
  const {
    messages, streaming, streamingText, toolCalls, isThinking,
    addMessage, setStreaming, appendStreamToken, flushStream,
    addToolCall, updateToolCall, setThinking,
  } = useChatStore();

  const setStatus = useAgentStore((s) => s.setStatus);
  const [input, setInput] = useState("");
  const [showSidebar, setShowSidebar] = useState(true);
  const [showActivity, setShowActivity] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, streamingText]);

  const handleSend = useCallback(() => {
    const text = input.trim();
    if (!text || streaming) return;
    addMessage({ role: "user", content: text });
    setInput("");
    setStreaming(true);
    setThinking(true);
    setStatus("thinking");

    abortRef.current = api.chatStream(
      { content: text },
      (token) => { appendStreamToken(token); setThinking(false); },
      (data: unknown) => {
        const d = data as Record<string, unknown>;
        const tc: ToolCall = {
          tool_name: (d.tool_name as string) || "unknown",
          arguments: (d.arguments as Record<string, unknown>) || {},
          call_id: (d.call_id as string) || crypto.randomUUID(),
          status: "running",
          started_at: new Date().toISOString(),
          finished_at: null,
        };
        addToolCall(tc);
        setStatus("acting");
      },
      (data: unknown) => {
        const d = data as Record<string, unknown>;
        updateToolCall((d.call_id as string) || "", { status: "success", finished_at: new Date().toISOString() });
      },
      () => {
        flushStream("assistant");
        setStreaming(false);
        setThinking(false);
        setStatus("idle");
      },
      (err) => {
        addMessage({ role: "assistant", content: `错误: ${err}` });
        setStreaming(false);
        setThinking(false);
        setStatus("idle");
      },
    );
  }, [input, streaming]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  return (
    <PageTransition>
      <div className="flex h-[calc(100vh-3rem)]">
        {/* Session Sidebar */}
        <AnimatePresence>
          {showSidebar && (
            <motion.div
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: 260, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              className="border-r border-os-border overflow-hidden shrink-0"
            >
              <SessionSidebar />
            </motion.div>
          )}
        </AnimatePresence>

        {/* Main Chat */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Chat header */}
          <div className="flex items-center gap-3 h-10 px-4 border-b border-os-border shrink-0">
            <button
              onClick={() => setShowSidebar(!showSidebar)}
              className="text-os-subtle hover:text-os-text transition-colors"
            >
              {showSidebar ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
            </button>
            <Sparkles size={14} className="text-os-accent" />
            <span className="text-xs text-os-text-high font-medium">对话</span>
            {isThinking && (
              <span className="text-2xs text-os-accent animate-pulse">Agent 思考中...</span>
            )}
            <button
              onClick={() => setShowActivity(!showActivity)}
              className="ml-auto text-os-subtle hover:text-os-text transition-colors"
            >
              {showActivity ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
            </button>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto">
            <div className="max-w-3xl mx-auto py-6 px-4 space-y-4">
              {messages.length === 0 && !streaming && (
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="text-center py-20"
                >
                  <div className="w-12 h-12 rounded-2xl bg-os-accent/10 flex items-center justify-center mx-auto mb-4">
                    <Brain size={24} className="text-os-accent" />
                  </div>
                  <p className="text-os-text-high text-sm font-medium">Agent Memory OS</p>
                  <p className="text-os-subtle text-xs mt-1">开始对话，Agent 会记住重要信息并主动反思</p>
                </motion.div>
              )}

              <AnimatePresence>
                {messages.map((msg, i) => (
                  <MessageBubble key={i} message={msg} />
                ))}
              </AnimatePresence>

              {/* Streaming text */}
              {streamingText && (
                <MessageBubble
                  message={{ role: "assistant", content: streamingText }}
                  streaming
                />
              )}

              {/* Tool calls in progress */}
              {toolCalls.map((tc) => (
                <ToolCallCard key={tc.call_id} toolCall={tc} />
              ))}

              <div ref={bottomRef} />
            </div>
          </div>

          {/* Input */}
          <div className="border-t border-os-border p-4 shrink-0">
            <div className="max-w-3xl mx-auto">
              <div className="glass-elevated rounded-xl p-1.5 flex items-end gap-2">
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
                  rows={1}
                  className="flex-1 bg-transparent resize-none text-sm text-os-text-high placeholder-os-muted py-2 px-2 outline-none max-h-32"
                />
                <button
                  onClick={handleSend}
                  disabled={!input.trim() || streaming}
                  className="shrink-0 w-9 h-9 rounded-lg bg-os-accent/15 text-os-accent hover:bg-os-accent/25 disabled:opacity-30 disabled:cursor-not-allowed transition-all flex items-center justify-center"
                >
                  <Send size={16} />
                </button>
              </div>
              <p className="text-2xs text-os-muted text-center mt-2">
                Agent Memory OS — 具备长期记忆与自我反思能力
              </p>
            </div>
          </div>
        </div>

        {/* Activity Panel */}
        <AnimatePresence>
          {showActivity && (
            <motion.div
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: 300, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              className="border-l border-os-border overflow-hidden shrink-0"
            >
              <ActivityPanel />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </PageTransition>
  );
}
