"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import {
  Building2, Plus, Users, Crown, Shield, User, Eye,
  ChevronRight, Loader2, AlertCircle, Zap, Send, X,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "@/services/api";
import { useAuthStore } from "@/stores/auth-store";
import { PageTransition, StaggerItem } from "@/components/animations/page-transition";
import { CardSkeleton } from "@/components/animations/skeleton";
import { cn } from "@/lib/utils";
import { kernelApi, kernelSafe, type RouteResponse } from "@/lib/core-client";
import type { Workspace, WorkspaceRole } from "@/types";

const roleMeta: Record<WorkspaceRole, { icon: typeof User; label: string; color: string }> = {
  owner:  { icon: Crown,  label: "拥有者", color: "text-os-warning bg-os-warning-soft" },
  admin:  { icon: Shield, label: "管理员", color: "text-os-primary bg-os-primary-soft" },
  member: { icon: User,   label: "成员",   color: "text-os-success bg-os-success-soft" },
  viewer: { icon: Eye,    label: "访客",   color: "text-os-subtle bg-os-surface-muted" },
};

export default function WorkspacePage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { currentWorkspace, setCurrentWorkspace, token } = useAuthStore();
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [createError, setCreateError] = useState("");

  // ── Kernel Ping 面板状态 ──
  const [kernelOpen, setKernelOpen] = useState(false);
  const [kernelInput, setKernelInput] = useState("");
  const [kernelResult, setKernelResult] = useState<RouteResponse | null>(null);
  const [kernelLoading, setKernelLoading] = useState(false);
  const [kernelError, setKernelError] = useState("");

  const handleKernelPing = async () => {
    if (!kernelInput.trim()) return;
    setKernelLoading(true);
    setKernelError("");
    setKernelResult(null);
    const result = await kernelSafe(
      kernelApi.routeIntent(kernelInput.trim()),
      "意图路由请求失败",
    );
    if (result) {
      setKernelResult(result);
    } else {
      setKernelError("后端无响应，请确认 uvicorn 已启动在 localhost:8000");
    }
    setKernelLoading(false);
  };

  // Fetch workspace list via /auth/me which returns workspaces with role info
  const { data: meData, isLoading, isError } = useQuery({
    queryKey: ["auth-me"],
    queryFn: () => api.auth.me(),
    enabled: !!token,
  });

  const workspaces: Workspace[] = meData?.workspaces || [];

  // Create workspace mutation
  const createMutation = useMutation({
    mutationFn: (name: string) => api.auth.createWorkspace(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["auth-me"] });
      setShowCreate(false);
      setNewName("");
      setCreateError("");
    },
    onError: (err: Error) => {
      setCreateError(err.message);
    },
  });

  const handleCreate = () => {
    if (!newName.trim()) {
      setCreateError("请输入工作区名称");
      return;
    }
    createMutation.mutate(newName.trim());
  };

  const handleSwitch = (ws: Workspace) => {
    setCurrentWorkspace(ws);
    // 切换工作区后回到工作台门面首页
    router.push("/home");
  };

  if (!token) {
    return (
      <PageTransition>
        <div className="flex flex-col items-center justify-center py-32 text-os-subtle">
          <Building2 size={48} className="mb-4 text-os-muted" />
          <p className="text-sm">请先登录</p>
          <p className="text-2xs mt-1">登录后可管理工作区</p>
        </div>
      </PageTransition>
    );
  }

  return (
    <PageTransition>
      <div className="p-4 md:p-6 space-y-5 max-w-[900px] mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-os-text-high tracking-tight">工作区</h1>
            <p className="text-xs text-os-subtle mt-0.5">
              {isLoading ? "加载中..." : `${workspaces.length} 个工作区`}
            </p>
          </div>
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium bg-os-accent text-white hover:bg-os-accent/90 transition-colors"
          >
            <Plus size={14} />
            创建工作区
          </button>
        </div>

        {/* Create Dialog */}
        {showCreate && (
          <div className="os-card p-4 space-y-3">
            <h2 className="text-sm font-semibold text-os-text-high">创建工作区</h2>
            <input
              autoFocus
              value={newName}
              onChange={(e) => { setNewName(e.target.value); setCreateError(""); }}
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              placeholder="工作区名称"
              className="w-full h-9 px-3 rounded-md bg-os-surface border border-os-border text-sm text-os-text-high placeholder:text-os-subtle focus:outline-none focus:border-os-accent transition-colors"
            />
            {createError && (
              <p className="text-xs text-os-danger">{createError}</p>
            )}
            <div className="flex items-center gap-2 justify-end">
              <button
                onClick={() => { setShowCreate(false); setNewName(""); setCreateError(""); }}
                className="px-3 py-1.5 rounded text-xs text-os-subtle hover:text-os-text hover:bg-os-surface transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleCreate}
                disabled={createMutation.isPending || !newName.trim()}
                className="px-3 py-1.5 rounded text-xs font-medium bg-os-accent text-white hover:bg-os-accent/90 disabled:opacity-40 transition-colors flex items-center gap-1"
              >
                {createMutation.isPending && <Loader2 size={12} className="animate-spin" />}
                创建
              </button>
            </div>
          </div>
        )}

        {/* Workspace List */}
        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="os-card p-4">
                <CardSkeleton />
              </div>
            ))}
          </div>
        ) : isError ? (
          <div className="flex flex-col items-center justify-center py-24 text-os-danger">
            <AlertCircle size={48} className="mb-4" />
            <p className="text-sm">工作区加载失败</p>
            <p className="text-2xs mt-1 text-os-subtle">请检查网络连接后刷新页面</p>
          </div>
        ) : workspaces.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 text-os-subtle">
            <Building2 size={48} className="mb-4 text-os-muted" />
            <p className="text-sm">暂无工作区</p>
            <p className="text-2xs mt-1">创建一个工作区开始协作</p>
          </div>
        ) : (
          <div className="space-y-2">
            {workspaces.map((ws, i) => {
              const role = (ws.role || "member") as WorkspaceRole;
              const meta = roleMeta[role] || roleMeta.member;
              const isActive = currentWorkspace?.id === ws.id;

              return (
                <StaggerItem key={ws.id} delay={i * 0.05}>
                  <button
                    onClick={() => handleSwitch(ws)}
                    className={cn(
                      "os-card os-card-hover w-full p-4 flex items-center gap-4 text-left transition-all cursor-pointer",
                      isActive && "ring-1 ring-os-accent/40 bg-os-accent/5"
                    )}
                  >
                    {/* Icon */}
                    <div className="w-10 h-10 rounded-xl bg-os-elevated flex items-center justify-center shrink-0">
                      <Building2 size={18} className={isActive ? "text-os-accent" : "text-os-subtle"} />
                    </div>

                    {/* Info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-os-text-high truncate">
                          {ws.name}
                        </span>
                        {isActive && (
                          <span className="text-2xs px-1.5 py-0.5 rounded-full bg-os-accent/10 text-os-accent font-medium shrink-0">
                            当前
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 mt-1">
                        <span className={cn("text-2xs px-1.5 py-0.5 rounded-full flex items-center gap-0.5", meta.color)}>
                          <meta.icon size={10} />
                          {meta.label}
                        </span>
                        {ws.members !== undefined && (
                          <span className="text-2xs text-os-subtle flex items-center gap-0.5">
                            <Users size={10} />
                            {ws.members} 成员
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Settings & Arrow */}
                    <div className="flex items-center gap-2 shrink-0">
                      <div
                        role="button"
                        tabIndex={0}
                        onClick={(e) => {
                          e.stopPropagation();
                          router.push(`/workspace/settings?id=${ws.id}`);
                        }}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            e.stopPropagation();
                            router.push(`/workspace/settings?id=${ws.id}`);
                          }
                        }}
                        className="p-1.5 rounded-md text-os-muted hover:text-os-text hover:bg-os-elevated transition-colors cursor-pointer"
                        title="设置"
                      >
                        <Shield size={14} />
                      </div>
                      <ChevronRight size={16} className="text-os-muted" />
                    </div>
                  </button>
                </StaggerItem>
              );
            })}
          </div>
        )}
      </div>

      {/* ── Kernel Ping 浮动面板（右下角） ── */}
      <div className="fixed bottom-4 right-4 z-[150] flex flex-col items-end gap-3">
        <AnimatePresence>
          {kernelOpen && (
            <motion.div
              key="kernel-panel"
              initial={{ opacity: 0, y: 12, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 12, scale: 0.95 }}
              transition={{ duration: 0.2, ease: "easeOut" }}
              className="w-[90vw] md:w-80 rounded-xl border border-os-border/50 bg-os-surface/95 backdrop-blur-xl shadow-os-lg overflow-hidden"
            >
              {/* Header */}
              <div className="flex items-center justify-between px-4 py-3 border-b border-os-border/30">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                  <span className="text-xs font-semibold text-os-text-high tracking-wide">
                    内核连通测试
                  </span>
                </div>
                <button
                  onClick={() => {
                    setKernelOpen(false);
                    setKernelResult(null);
                    setKernelError("");
                  }}
                  className="text-os-muted hover:text-os-text-high transition-colors"
                >
                  <X size={14} />
                </button>
              </div>

              {/* Body */}
              <div className="p-4 space-y-3">
                <div className="flex items-center gap-2">
                  <input
                    value={kernelInput}
                    onChange={(e) => {
                      setKernelInput(e.target.value);
                      setKernelError("");
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleKernelPing();
                    }}
                    placeholder="输入文本测试意图路由..."
                    className="flex-1 h-9 px-3 rounded-md bg-os-surface border border-os-border text-sm text-os-text-high placeholder:text-os-subtle focus:outline-none focus:border-os-accent transition-colors"
                  />
                  <button
                    onClick={handleKernelPing}
                    disabled={kernelLoading || !kernelInput.trim()}
                    className="shrink-0 w-9 h-9 flex items-center justify-center rounded-md bg-os-accent text-white hover:bg-os-accent/90 disabled:opacity-40 transition-colors"
                  >
                    {kernelLoading ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <Send size={14} />
                    )}
                  </button>
                </div>

                {/* Error */}
                {kernelError && (
                  <div className="flex items-start gap-2 p-2.5 rounded-md bg-os-danger-soft border border-os-danger/20">
                    <AlertCircle size={14} className="text-os-danger shrink-0 mt-0.5" />
                    <p className="text-xs text-os-danger">{kernelError}</p>
                  </div>
                )}

                {/* Result */}
                {kernelResult && (
                  <div className="p-3 rounded-md bg-os-accent/5 border border-os-accent/20 space-y-2">
                    <div className="flex items-center gap-2">
                      <span className="text-2xs text-os-subtle">意图</span>
                      <span className={cn(
                        "text-xs font-mono font-semibold px-1.5 py-0.5 rounded",
                        kernelResult.intent === "CODE_EXECUTION"
                          ? "bg-os-warning-soft text-os-warning"
                          : "bg-os-primary-soft text-os-primary",
                      )}>
                        {kernelResult.intent}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-2xs text-os-subtle">置信度</span>
                      <span className="text-xs font-mono text-os-text-high">
                        {(kernelResult.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-2xs text-os-subtle">原始输入</span>
                      <span className="text-xs text-os-subtle truncate max-w-[180px]">
                        {kernelResult.raw_query}
                      </span>
                    </div>
                  </div>
                )}

                {/* Empty hint */}
                {!kernelResult && !kernelError && !kernelLoading && (
                  <p className="text-2xs text-os-subtle text-center">
                    输入关键词如 &quot;搜索记忆&quot; 或 &quot;执行代码&quot; 测试路由
                  </p>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Toggle button */}
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={() => setKernelOpen((v) => !v)}
          className={cn(
            "w-11 h-11 rounded-full flex items-center justify-center shadow-lg transition-colors",
            kernelOpen
              ? "bg-os-accent text-white"
              : "bg-os-surface/90 border border-os-border/50 text-os-subtle hover:text-os-accent",
          )}
          title="内核连通测试面板"
        >
          <Zap size={18} />
        </motion.button>
      </div>
    </PageTransition>
  );
}
