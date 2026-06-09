"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Send,
  Sparkles,
  Brain,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Search,
  Wrench,
  Lightbulb,
  FileText,
  BarChart3,
  MessageSquare,
  Zap,
  Globe,
  PenTool,
  Cpu,
} from "lucide-react";
import { useChatStore } from "@/stores/chat-store";
import { useAgentStore } from "@/stores/agent-store";
import { api } from "@/services/api";
import { PageTransition } from "@/components/animations/page-transition";
import { MessageBubble } from "@/components/chat/message-bubble";
import { ToolCallCard } from "@/components/chat/tool-call-card";
import { SessionSidebar } from "@/components/chat/session-sidebar";
import { ActivityPanel } from "@/components/chat/activity-panel";
import { ImageUploadButton } from "@/components/chat/image-upload-button";
import type { ToolCall } from "@/types";

// ── 快捷指令 ──
const quickActions = [
  { icon: Search, label: "搜索记忆", prompt: "帮我搜索关于 AI 的记忆" },
  { icon: FileText, label: "总结最近", prompt: "总结我最近的记忆和反思" },
  { icon: Lightbulb, label: "深度反思", prompt: "基于最近的记忆，帮我做一次深度反思" },
  { icon: BarChart3, label: "知识分析", prompt: "分析我的知识图谱中的关键主题" },
  { icon: PenTool, label: "创意写作", prompt: "基于我的知识库，帮我写一篇关于 Agent 记忆系统的文章" },
  { icon: Globe, label: "知识问答", prompt: "根据我的记忆，我最近关注哪些话题？" },
];

// ── 能力标签 ──
const capabilities = [
  { icon: Brain, label: "长期记忆", desc: "持久化存储与检索" },
  { icon: Lightbulb, label: "主动反思", desc: "自动发现洞察" },
  { icon: Wrench, label: "工具调用", desc: "搜索/计算/分析" },
  { icon: Zap, label: "实时流式", desc: "逐字输出响应" },
];

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
  const [agentPhase, setAgentPhase] = useState<"idle" | "retrieving" | "thinking" | "acting" | "reflecting">("idle");
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, streamingText]);

  const sendMessage = useCallback((text: string) => {
    if (!text.trim() || streaming) return;
    addMessage({ role: "user", content: text });
    setInput("");
    setStreaming(true);
    setThinking(true);
    setAgentPhase("retrieving");
    setStatus("thinking");

    let firstTokenReceived = false;

    abortRef.current = api.chatStream(
      { content: text },
      (token) => {
        if (!firstTokenReceived) {
          firstTokenReceived = true;
          setAgentPhase("thinking");
        }
        if (token.includes("⚡")) { setAgentPhase("acting"); setStatus("acting"); }
        else if (token.includes("✓")) { setAgentPhase("thinking"); }
        else if (token.includes("🔄")) { setAgentPhase("reflecting"); setStatus("reflecting"); }
        else { setAgentPhase("thinking"); }
        appendStreamToken(token);
        setThinking(false);
      },
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
        setAgentPhase("acting");
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
        setAgentPhase("idle");
        setStatus("idle");
      },
      (err) => {
        addMessage({ role: "assistant", content: `错误: ${err}` });
        setStreaming(false);
        setThinking(false);
        setAgentPhase("idle");
        setStatus("idle");
      },
    );
  }, [input, streaming]);

  const handleSend = useCallback(() => {
    sendMessage(input);
  }, [input, sendMessage]);

  const handleQuickAction = useCallback((prompt: string) => {
    sendMessage(prompt);
  }, [sendMessage]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const isEmpty = messages.length === 0 && !streaming;

  return (
    <PageTransition>
      <div className="flex h-[calc(100vh-3rem)] bg-grid-subtle">
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
        <div className="flex-1 flex flex-col min-w-0 relative">
          {/* 顶部渐变光晕 */}
          <div className="absolute inset-0 pointer-events-none bg-glow-top opacity-60" />

          {/* Chat header */}
          <div className="relative flex items-center gap-3 h-10 px-4 border-b border-os-border shrink-0 bg-os-base/60 backdrop-blur-sm">
            <button
              onClick={() => setShowSidebar(!showSidebar)}
              className="text-os-subtle hover:text-os-text transition-colors"
            >
              {showSidebar ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
            </button>
            <Sparkles size={14} className="text-os-accent" />
            <span className="text-xs text-os-text-high font-medium">对话</span>
            {agentPhase !== "idle" && (
              <div className="flex items-center gap-1.5 ml-2">
                <Loader2 size={11} className="text-os-accent animate-spin" />
                <span className="text-2xs text-os-accent">
                  {agentPhase === "retrieving" && "检索记忆中..."}
                  {agentPhase === "thinking" && "思考中..."}
                  {agentPhase === "acting" && "执行工具中..."}
                  {agentPhase === "reflecting" && "反思中..."}
                </span>
              </div>
            )}
            <div className="flex-1" />
            <div className="flex items-center gap-1.5">
              <Cpu size={11} className="text-emerald-400/60" />
              <span className="text-2xs text-os-muted">Agent OS v0.1</span>
            </div>
            <button
              onClick={() => setShowActivity(!showActivity)}
              className="text-os-subtle hover:text-os-text transition-colors ml-1"
            >
              {showActivity ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
            </button>
          </div>

          {/* Messages Area */}
          <div className="flex-1 overflow-y-auto relative">
            <div className="max-w-3xl mx-auto py-6 px-4 space-y-4">
              {/* ── 空状态：欢迎卡片 ── */}
              {isEmpty && (
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="py-8 space-y-8"
                >
                  {/* Hero 区域 */}
                  <div className="text-center space-y-3">
                    <div className="relative inline-flex">
                      <div className="w-16 h-16 rounded-2xl bg-os-accent-grad border border-os-accent/15 flex items-center justify-center shadow-os-glow">
                        <Brain size={30} className="text-os-accent" />
                      </div>
                      <div className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-emerald-400/20 border border-emerald-400/30 flex items-center justify-center">
                        <div className="w-2 h-2 rounded-full bg-emerald-400 animate-status-breathe" />
                      </div>
                    </div>
                    <h2 className="text-lg font-semibold text-os-text-high tracking-tight">Agent Memory OS</h2>
                    <p className="text-xs text-os-subtle max-w-sm mx-auto leading-relaxed">
                      具备长期记忆与自我反思能力的 AI 认知工作台<br />
                      每一次对话都会被记住，Agent 会主动发现洞察
                    </p>
                  </div>

                  {/* 能力卡片 */}
                  <div className="grid grid-cols-4 gap-2">
                    {capabilities.map((cap) => (
                      <div
                        key={cap.label}
                        className="os-panel p-3 text-center space-y-1.5 hover:border-os-accent/20 transition-all duration-300 group cursor-default"
                      >
                        <cap.icon size={16} className="text-os-accent/60 group-hover:text-os-accent mx-auto transition-colors" />
                        <p className="text-2xs text-os-text-high font-medium">{cap.label}</p>
                        <p className="text-2xs text-os-muted hidden sm:block">{cap.desc}</p>
                      </div>
                    ))}
                  </div>

                  {/* 快捷指令 */}
                  <div className="space-y-2">
                    <p className="text-2xs text-os-muted text-center uppercase tracking-wider">快捷指令</p>
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5">
                      {quickActions.map((action) => (
                        <button
                          key={action.label}
                          onClick={() => handleQuickAction(action.prompt)}
                          className="flex items-center gap-2 px-3 py-2 rounded-lg bg-os-surface/60 border border-os-border/50 hover:border-os-accent/20 hover:bg-os-elevated/80 transition-all duration-200 group text-left"
                        >
                          <action.icon size={13} className="text-os-subtle group-hover:text-os-accent shrink-0 transition-colors" />
                          <span className="text-2xs text-os-text group-hover:text-os-text-high transition-colors truncate">{action.label}</span>
                        </button>
                      ))}
                    </div>
                  </div>
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

          {/* Input Area */}
          <div className="relative border-t border-os-border/60 shrink-0 bg-os-base/80 backdrop-blur-md">
            {/* 光晕装饰 */}
            <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-os-accent/15 to-transparent" />

            <div className="max-w-3xl mx-auto p-4">
              <div className="os-panel-elevated rounded-xl p-1.5 flex items-end gap-2 shadow-os-glow">
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
                  rows={1}
                  className="flex-1 bg-transparent resize-none text-sm text-os-text-high placeholder-os-muted py-2 px-2.5 outline-none max-h-32"
                />
                <ImageUploadButton
                  disabled={streaming}
                  onUploaded={(summary) => setInput((prev) => (prev ? `${prev}\n${summary}` : summary))}
                />
                <button
                  onClick={handleSend}
                  disabled={!input.trim() || streaming}
                  className="shrink-0 w-9 h-9 rounded-lg bg-os-accent/15 text-os-accent hover:bg-os-accent/25 hover:shadow-os-glow disabled:opacity-25 disabled:cursor-not-allowed disabled:hover:shadow-none transition-all flex items-center justify-center"
                >
                  {streaming ? (
                    <Loader2 size={15} className="animate-spin" />
                  ) : (
                    <Send size={15} />
                  )}
                </button>
              </div>
              <p className="text-2xs text-os-muted/60 text-center mt-2 select-none">
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
              <ActivityPanel agentPhase={agentPhase} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </PageTransition>
  );
}
