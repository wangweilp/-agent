"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import {
  Building2, Plus, Users, Crown, Shield, User, Eye,
  ChevronRight, Loader2, AlertCircle,
} from "lucide-react";
import { api } from "@/services/api";
import { useAuthStore } from "@/stores/auth-store";
import { PageTransition, StaggerItem } from "@/components/animations/page-transition";
import { CardSkeleton } from "@/components/animations/skeleton";
import { cn } from "@/lib/utils";
import type { Workspace, WorkspaceRole } from "@/types";

const roleMeta: Record<WorkspaceRole, { icon: typeof User; label: string; color: string }> = {
  owner:  { icon: Crown,  label: "拥有者", color: "text-amber-400 bg-amber-400/10" },
  admin:  { icon: Shield, label: "管理员", color: "text-indigo-400 bg-indigo-400/10" },
  member: { icon: User,   label: "成员",   color: "text-emerald-400 bg-emerald-400/10" },
  viewer: { icon: Eye,    label: "访客",   color: "text-zinc-400 bg-zinc-400/10" },
};

export default function WorkspacePage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { currentWorkspace, setCurrentWorkspace, token } = useAuthStore();
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [createError, setCreateError] = useState("");

  // Fetch workspace list via /auth/me which returns workspaces with role info
  const { data: meData, isLoading } = useQuery({
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
    // Navigate to dashboard or stay - for now just stay on workspace page
    router.push("/dashboard");
  };

  if (!token) {
    return (
      <PageTransition>
        <div className="flex flex-col items-center justify-center py-32 text-os-muted">
          <Building2 size={48} className="mb-4 opacity-30" />
          <p className="text-sm">请先登录</p>
          <p className="text-2xs mt-1">登录后可管理工作区</p>
        </div>
      </PageTransition>
    );
  }

  return (
    <PageTransition>
      <div className="p-6 space-y-5 max-w-[900px] mx-auto">
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
              className="w-full h-9 px-3 rounded-md bg-os-surface border border-os-border text-sm text-os-text-high placeholder:text-os-muted focus:outline-none focus:border-os-accent transition-colors"
            />
            {createError && (
              <p className="text-xs text-red-400">{createError}</p>
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
        ) : workspaces.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 text-os-muted">
            <Building2 size={48} className="mb-4 opacity-30" />
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
                          <span className="text-2xs text-os-muted flex items-center gap-0.5">
                            <Users size={10} />
                            {ws.members} 成员
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Settings & Arrow */}
                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          router.push(`/workspace/settings?id=${ws.id}`);
                        }}
                        className="p-1.5 rounded-md text-os-muted hover:text-os-text hover:bg-os-elevated transition-colors"
                        title="设置"
                      >
                        <Shield size={14} />
                      </button>
                      <ChevronRight size={16} className="text-os-muted" />
                    </div>
                  </button>
                </StaggerItem>
              );
            })}
          </div>
        )}
      </div>
    </PageTransition>
  );
}
