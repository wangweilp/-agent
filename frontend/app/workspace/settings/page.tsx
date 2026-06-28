"use client";

import { useState, useMemo, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Users, UserPlus, Crown, Shield, Eye, User, Trash2,
  Loader2, AlertCircle, Check, X, ArrowLeft, Settings,
  Activity, ClipboardList, AlertTriangle,
} from "lucide-react";
import { api } from "@/services/api";
import { useAuthStore } from "@/stores/auth-store";
import { PageTransition, StaggerItem } from "@/components/animations/page-transition";
import { Skeleton } from "@/components/animations/skeleton";
import { DangerConfirmDialog } from "@/components/os/danger-confirm-dialog";
import { toast } from "@/stores/ui-store";
import { cn, formatDate } from "@/lib/utils";
import type { WorkspaceMember, WorkspaceRole, ActivityEvent } from "@/types";

const roleMeta: Record<WorkspaceRole, { icon: typeof User; label: string; color: string }> = {
  owner:  { icon: Crown,  label: "拥有者", color: "text-amber-400 bg-amber-400/10" },
  admin:  { icon: Shield, label: "管理员", color: "text-indigo-400 bg-indigo-400/10" },
  member: { icon: User,   label: "成员",   color: "text-emerald-400 bg-emerald-400/10" },
  viewer: { icon: Eye,    label: "访客",   color: "text-zinc-400 bg-zinc-400/10" },
};

const roleOptionLabel: Record<string, string> = {
  viewer: "访客 - 仅查看",
  member: "成员 - 可编辑",
  admin: "管理员 - 可管理",
  owner: "拥有者 - 完全控制",
};

function SettingsContent() {
  const searchParams = useSearchParams();
  const wsId = searchParams.get("id") || "";
  const queryClient = useQueryClient();
  const { currentWorkspace, user } = useAuthStore();

  // Fetch members
  const {
    data: members,
    isLoading: membersLoading,
    error: membersError,
  } = useQuery({
    queryKey: ["workspace-members", wsId],
    queryFn: () => api.workspace.listMembers(wsId),
    enabled: !!wsId,
  });

  // Fetch activity log
  const { data: activityLog } = useQuery({
    queryKey: ["workspace-activity", wsId],
    queryFn: () => api.workspace.activityLog(wsId, 20),
    enabled: !!wsId,
  });

  // Current user's role in this workspace
  const myRole: WorkspaceRole = useMemo(() => {
    if (!members || !user) return "viewer";
    const me = members.find((m) => m.user_id === user.id);
    return (me?.role || "viewer") as WorkspaceRole;
  }, [members, user]);

  const canManage = myRole === "owner" || myRole === "admin";

  // Add member
  const [addEmail, setAddEmail] = useState("");
  const [addRole, setAddRole] = useState("member");
  const [addError, setAddError] = useState("");
  const [showAdd, setShowAdd] = useState(false);

  const addMutation = useMutation({
    mutationFn: () => api.workspace.addMember(wsId, addEmail, addRole),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspace-members", wsId] });
      setAddEmail("");
      setAddRole("member");
      setShowAdd(false);
      setAddError("");
    },
    onError: (err: Error) => setAddError(err.message),
  });

  // Update role
  const [editingRole, setEditingRole] = useState<string | null>(null);

  const roleMutation = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: string }) =>
      api.workspace.updateRole(wsId, userId, role),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspace-members", wsId] });
      setEditingRole(null);
    },
  });

  // Remove member
  const removeMutation = useMutation({
    mutationFn: (userId: string) => api.workspace.removeMember(wsId, userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspace-members", wsId] });
    },
  });

  // ── 任务 C: Danger Zone — 批量移除非 owner 成员 ──
  const [showRemoveAll, setShowRemoveAll] = useState(false);
  const [removingAll, setRemovingAll] = useState(false);

  const removableMembers = useMemo(() => {
    if (!members) return [];
    return members.filter((m) => m.role !== "owner");
  }, [members]);

  async function handleRemoveAllMembers() {
    if (!removableMembers.length) {
      setShowRemoveAll(false);
      return;
    }
    setRemovingAll(true);
    let successCount = 0;
    let failCount = 0;
    for (const m of removableMembers) {
      try {
        await api.workspace.removeMember(wsId, m.user_id);
        successCount++;
      } catch {
        failCount++;
      }
    }
    queryClient.invalidateQueries({ queryKey: ["workspace-members", wsId] });
    setRemovingAll(false);
    setShowRemoveAll(false);
    if (failCount === 0) {
      toast.success(`已移除 ${successCount} 个成员`);
    } else {
      toast.warning("批量移除完成", `成功 ${successCount}，失败 ${failCount}`);
    }
  }

  // Activity event type label
  const eventTypeLabel: Record<string, string> = {
    member_added: "添加成员",
    member_removed: "移除成员",
    member_role_changed: "角色变更",
    memory_merged: "记忆合并",
    action_created: "创建任务",
    action_completed: "完成任务",
  };

  if (!wsId) {
    return (
      <PageTransition>
        <div className="flex flex-col items-center justify-center py-32 text-os-muted">
          <AlertCircle size={48} className="mb-4 opacity-30" />
          <p className="text-sm">未指定工作区</p>
          <p className="text-2xs mt-1">请从工作区列表进入设置</p>
        </div>
      </PageTransition>
    );
  }

  return (
    <PageTransition>
      <div className="p-6 space-y-5 max-w-[900px] mx-auto">
        {/* Back link */}
        <a
          href="/workspace"
          className="inline-flex items-center gap-1.5 text-xs text-os-subtle hover:text-os-text transition-colors"
        >
          <ArrowLeft size={13} />
          返回工作区列表
        </a>

        {/* Header */}
        <div>
          <h1 className="text-lg font-semibold text-os-text-high tracking-tight">
            {currentWorkspace?.name || "工作区设置"}
          </h1>
          <p className="text-xs text-os-subtle mt-0.5">
            成员管理 · 活动日志
          </p>
        </div>

        {/* Tab bar */}
        <div className="flex items-center gap-1">
          <span className="text-xs font-medium text-os-accent px-2.5 py-1 rounded bg-os-accent/10 flex items-center gap-1">
            <Users size={13} /> 成员
          </span>
          <span className="text-xs text-os-subtle px-2.5 py-1 rounded hover:bg-os-surface transition-colors flex items-center gap-1 cursor-pointer">
            <Activity size={13} /> 活动
          </span>
        </div>

        {/* Members Section */}
        <div className="space-y-4">
          {/* Section header */}
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-os-text-high flex items-center gap-2">
              <Users size={15} className="text-os-accent" />
              成员
              {members && (
                <span className="text-xs font-normal text-os-muted">({members.length})</span>
              )}
            </h2>
            {canManage && (
              <button
                onClick={() => setShowAdd(!showAdd)}
                className="flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium text-os-accent hover:bg-os-accent/10 transition-colors"
              >
                <UserPlus size={13} />
                添加成员
              </button>
            )}
          </div>

          {/* Add member form */}
          {showAdd && canManage && (
            <div className="os-card p-3 space-y-3">
              <div className="flex items-center gap-2">
                <input
                  autoFocus
                  value={addEmail}
                  onChange={(e) => { setAddEmail(e.target.value); setAddError(""); }}
                  onKeyDown={(e) => e.key === "Enter" && addEmail.trim() && addMutation.mutate()}
                  placeholder="输入成员邮箱"
                  className="flex-1 h-8 px-2.5 rounded bg-os-surface border border-os-border text-xs text-os-text-high placeholder:text-os-muted focus:outline-none focus:border-os-accent"
                />
                <select
                  value={addRole}
                  onChange={(e) => setAddRole(e.target.value)}
                  className="h-8 px-2 rounded bg-os-surface border border-os-border text-xs text-os-text-high focus:outline-none focus:border-os-accent"
                >
                  <option value="admin">管理员</option>
                  <option value="member">成员</option>
                  <option value="viewer">访客</option>
                </select>
                <button
                  onClick={() => addMutation.mutate()}
                  disabled={addMutation.isPending || !addEmail.trim()}
                  className="flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium bg-os-accent text-white hover:bg-os-accent/90 disabled:opacity-40 transition-colors"
                >
                  {addMutation.isPending ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
                  添加
                </button>
                <button
                  onClick={() => { setShowAdd(false); setAddEmail(""); setAddError(""); }}
                  className="p-1 rounded text-os-muted hover:text-os-text transition-colors"
                >
                  <X size={14} />
                </button>
              </div>
              {addError && <p className="text-2xs text-red-400">{addError}</p>}
            </div>
          )}

          {/* Members list */}
          {membersLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="os-card p-3">
                  <Skeleton className="h-10 w-full" />
                </div>
              ))}
            </div>
          ) : membersError ? (
            <div className="os-card p-4 text-center text-sm text-red-400">
              加载成员失败
            </div>
          ) : !members || members.length === 0 ? (
            <div className="os-card p-8 text-center text-sm text-os-muted">
              暂无成员
            </div>
          ) : (
            <div className="space-y-1">
              {members.map((member, i) => {
                const meta = roleMeta[member.role] || roleMeta.member;
                const isMe = member.user_id === user?.id;
                const isOwner = member.role === "owner";
                const canEdit = canManage && !isOwner;

                return (
                  <StaggerItem key={member.user_id} delay={i * 0.04}>
                    <div className="os-card p-3 flex items-center gap-3 group">
                      {/* Avatar */}
                      <div className="w-8 h-8 rounded-full bg-os-elevated flex items-center justify-center shrink-0">
                        {member.avatar_url ? (
                          <img src={member.avatar_url} className="w-8 h-8 rounded-full object-cover" alt="" />
                        ) : (
                          <span className="text-xs text-os-subtle font-medium">
                            {(member.name || member.email).charAt(0).toUpperCase()}
                          </span>
                        )}
                      </div>

                      {/* Info */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className="text-xs font-medium text-os-text-high truncate">
                            {member.name || member.email}
                          </span>
                          {isMe && (
                            <span className="text-2xs text-os-accent bg-os-accent/10 px-1 py-0.5 rounded shrink-0">你</span>
                          )}
                        </div>
                        <span className="text-2xs text-os-muted truncate block">{member.email}</span>
                      </div>

                      {/* Role */}
                      <div className="flex items-center gap-1 shrink-0">
                        {/* Role badge or selector */}
                        {editingRole === member.user_id && canEdit ? (
                          <div className="flex items-center gap-1">
                            <select
                              defaultValue={member.role}
                              onChange={(e) => {
                                roleMutation.mutate({ userId: member.user_id, role: e.target.value });
                              }}
                              className="h-6 px-1.5 rounded bg-os-surface border border-os-border text-2xs text-os-text-high focus:outline-none focus:border-os-accent"
                            >
                              <option value="admin">管理员</option>
                              <option value="member">成员</option>
                              <option value="viewer">访客</option>
                            </select>
                            <button
                              onClick={() => setEditingRole(null)}
                              className="p-0.5 rounded text-os-muted hover:text-os-text"
                            >
                              <X size={12} />
                            </button>
                          </div>
                        ) : (
                          <span className={cn("text-2xs px-1.5 py-0.5 rounded-full flex items-center gap-0.5", meta.color)}>
                            <meta.icon size={10} />
                            {meta.label}
                          </span>
                        )}

                        {/* Actions */}
                        {canEdit && editingRole !== member.user_id && (
                          <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                            <button
                              onClick={() => setEditingRole(member.user_id)}
                              className="p-1 rounded text-os-muted hover:text-os-text hover:bg-os-elevated"
                              title="更改角色"
                            >
                              <Shield size={12} />
                            </button>
                            <button
                              onClick={() => {
                                if (confirm(`确定移除成员 ${member.name || member.email}?`)) {
                                  removeMutation.mutate(member.user_id);
                                }
                              }}
                              disabled={removeMutation.isPending}
                              className="p-1 rounded text-os-muted hover:text-red-400 hover:bg-red-400/10"
                              title="移除成员"
                            >
                              {removeMutation.isPending ? (
                                <Loader2 size={12} className="animate-spin" />
                              ) : (
                                <Trash2 size={12} />
                              )}
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  </StaggerItem>
                );
              })}
            </div>
          )}
        </div>

        {/* Activity Log Section */}
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-os-text-high flex items-center gap-2">
            <Activity size={15} className="text-os-accent" />
            最近活动
          </h2>
          {!activityLog || activityLog.length === 0 ? (
            <div className="os-card p-6 text-center text-sm text-os-muted">
              暂无活动记录
            </div>
          ) : (
            <div className="space-y-1">
              {activityLog.map((ev, i) => (
                <div key={ev.id || i} className="os-card p-3 flex items-center gap-3">
                  <div className="w-7 h-7 rounded-lg bg-os-elevated flex items-center justify-center shrink-0">
                    <ClipboardList size={13} className="text-os-subtle" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <span className="text-xs text-os-text">{ev.message}</span>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-2xs text-os-muted">{ev.user_name}</span>
                      <span className="text-2xs text-os-muted">
                        {ev.timestamp ? formatDate(ev.timestamp) : ""}
                      </span>
                    </div>
                  </div>
                  {ev.event_type && (
                    <span className="text-2xs text-os-muted bg-os-surface px-1.5 py-0.5 rounded shrink-0">
                      {eventTypeLabel[ev.event_type] || ev.event_type}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ── 任务 C: Danger Zone ── */}
        {canManage && (
          <div className="space-y-3">
            <div className="rounded-2xl border border-os-danger/40 bg-os-danger/5 p-6">
              <div className="mb-4 flex items-center gap-2">
                <AlertTriangle size={16} className="text-os-danger" />
                <h2 className="text-sm font-semibold text-os-danger">Danger Zone</h2>
              </div>
              <p className="mb-4 text-xs text-os-subtle">
                以下操作不可逆。执行前请确认你理解其后果。
              </p>

              <div className="flex items-center justify-between gap-4 rounded-lg border border-os-border/50 bg-os-surface/30 p-4">
                <div className="min-w-0">
                  <h3 className="text-sm font-medium text-os-text-high">移除全部非拥有者成员</h3>
                  <p className="mt-1 text-xs text-os-subtle">
                    立即从工作区移除当前所有 <span className="font-mono text-os-danger">{removableMembers.length}</span> 个非拥有者成员。被移除的成员将立即失去访问权限。
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setShowRemoveAll(true)}
                  disabled={removableMembers.length === 0}
                  className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-lg border border-os-danger px-3 text-xs font-medium text-os-danger transition-colors hover:bg-os-danger/10 disabled:cursor-not-allowed disabled:border-os-border disabled:text-os-muted"
                >
                  <Trash2 size={13} />
                  移除全部
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Danger confirm modal — Remove All Members */}
      <DangerConfirmDialog
        open={showRemoveAll}
        title="移除全部非拥有者成员"
        description={`此操作将从工作区 "${currentWorkspace?.name || wsId}" 移除 ${removableMembers.length} 个非拥有者成员。被移除的成员将立即失去对该工作区的所有访问权限。此操作不可撤销。`}
        confirmWord="REMOVE ALL"
        confirmWordLabel="请输入下方确认词以移除全部成员"
        actionLabel="移除全部成员"
        onConfirm={handleRemoveAllMembers}
        onClose={() => !removingAll && setShowRemoveAll(false)}
        loading={removingAll}
      />
    </PageTransition>
  );
}

export default function WorkspaceSettingsPage() {
  return (
    <Suspense fallback={
      <div className="p-6 space-y-5 max-w-[900px] mx-auto">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-64 w-full" />
      </div>
    }>
      <SettingsContent />
    </Suspense>
  );
}
