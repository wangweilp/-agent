"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Users,
  Search,
  Shield,
  ChevronDown,
  X,
  RefreshCw,
  UserCog,
  Building2,
  UserPlus,
  Key,
  AlertCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/services/api";
import type { RbacUser, RbacRole } from "@/types";
import { layout } from "@/styles/layout";

// ── Constants ──

const AVAILABLE_ROLES = [
  "SuperAdmin",
  "OrgAdmin",
  "DeptAdmin",
  "Manager",
  "Employee",
  "Guest",
];

const ROLE_DESCRIPTIONS: Record<string, string> = {
  SuperAdmin: "可访问并管理系统内全部组织",
  OrgAdmin: "可管理单个组织及其用户",
  DeptAdmin: "可管理部门及其成员",
  Manager: "可管理团队成员并审核内容",
  Employee: "拥有标准用户基础权限",
  Guest: "仅可读取共享资源",
};

// ── Page ──

export default function UserManagementPage() {
  const [users, setUsers] = useState<RbacUser[]>([]);
  const [roles, setRoles] = useState<RbacRole[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  // Filters
  const [search, setSearch] = useState("");
  const [orgFilter, setOrgFilter] = useState("");
  const [roleFilter, setRoleFilter] = useState("");

  // Role assignment modal
  const [selectedUser, setSelectedUser] = useState<RbacUser | null>(null);
  const [showRoleModal, setShowRoleModal] = useState(false);
  const [assigningRole, setAssigningRole] = useState("");

  // Permissions view
  const [showPermsFor, setShowPermsFor] = useState<string | null>(null);

  // Orgs for filter dropdown
  const [orgs, setOrgs] = useState<string[]>([]);

  const fetchUsers = useCallback(async () => {
    setError(null);
    try {
      const data = await api.rbac.users();
      const userList = Array.isArray(data) ? data : [];
      setUsers(userList);
      // Extract unique org names for filter
      const orgNames = [...new Set(
        userList.map((u) => u.org_name || u.org_id || "").filter(Boolean)
      )] as string[];
      setOrgs(orgNames);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "加载用户列表失败");
    }
  }, []);

  const fetchRoles = useCallback(async () => {
    try {
      const data = await api.rbac.roles();
      setRoles(Array.isArray(data) ? data : []);
    } catch {
      // Fallback to defaults if roles endpoint returns empty
      setRoles(AVAILABLE_ROLES.map((r) => ({ id: r, name: r, permissions: [] })));
    }
  }, []);

  useEffect(() => {
    async function load() {
      setLoading(true);
      await Promise.all([fetchUsers(), fetchRoles()]);
      setLoading(false);
    }
    load();
  }, [fetchUsers, fetchRoles]);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    await fetchUsers();
    setRefreshing(false);
  }, [fetchUsers]);

  // ── Filtering ──

  const filteredUsers = users.filter((u) => {
    if (search && !u.name?.toLowerCase().includes(search.toLowerCase()) && !u.email?.toLowerCase().includes(search.toLowerCase())) {
      return false;
    }
    if (orgFilter && (u.org_name || u.org_id || "") !== orgFilter) return false;
    if (roleFilter && !u.roles?.includes(roleFilter)) return false;
    return true;
  });

  // ── Stats ──

  const stats = {
    total: users.length,
    withRoles: users.filter((u) => (u.roles || []).length > 0).length,
    orgs: orgs.length,
    rolesAvailable: roles.length,
  };

  // ── Handlers ──

  const handleAssignRole = async () => {
    if (!selectedUser || !assigningRole) return;
    try {
      await api.rbac.assignRole({
        user_id: selectedUser.id,
        role_id: assigningRole,
        organization_id: selectedUser.org_id || "default",
      });
      setShowRoleModal(false);
      setAssigningRole("");
      await fetchUsers();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "分配角色失败");
    }
  };

  const handleRemoveRole = async (userId: string, role: string) => {
    if (!confirm(`确定从该用户移除角色“${role}”吗？`)) return;
    const user = users.find((u) => u.id === userId);
    if (!user) return;
    try {
      const newRoles = (user.roles || []).filter((r) => r !== role);
      // 通过 update user roles 方式
      await fetch(`/api/rbac/users/${userId}/roles`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ roles: newRoles }),
      });
      await fetchUsers();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "移除角色失败");
    }
  };

  const handleFetchPermissions = (userId: string) => {
    setShowPermsFor(showPermsFor === userId ? null : userId);
  };

  // ── Render ──

  return (
    <div className="p-6 space-y-5 max-w-[1440px] mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-os-text-high tracking-tight">
            用户管理
          </h1>
          <p className="text-xs text-os-subtle mt-0.5">
            {loading ? "加载中..." : `${stats.total} 位用户`}
          </p>
        </div>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-os-subtle hover:text-os-text hover:bg-os-elevated border border-transparent hover:border-os-border/50 transition-all disabled:opacity-50"
        >
          <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} />
          刷新
        </button>
      </div>

      {/* ── Stats Cards ── */}
      <div className={layout.grid.fourMd}>
        {[
          { icon: Users, label: "总用户", value: stats.total, accent: "indigo" as const },
          { icon: Shield, label: "已授权", value: stats.withRoles, accent: "emerald" as const },
          { icon: Building2, label: "组织", value: stats.orgs, accent: "violet" as const },
          { icon: Key, label: "可用角色", value: stats.rolesAvailable, accent: "amber" as const },
        ].map((s) => (
          <div
            key={s.label}
            className="os-card p-3.5 rounded-lg border border-os-border/30 bg-os-surface hover:border-os-border/60 transition-colors"
          >
            <div className="flex items-start justify-between">
              <p className="text-2xs text-os-subtle uppercase tracking-wider">{s.label}</p>
              <s.icon size={14} className={
                s.accent === "indigo" ? "text-indigo-400" :
                s.accent === "emerald" ? "text-emerald-400" :
                s.accent === "violet" ? "text-violet-400" : "text-amber-400"
              } />
            </div>
            <p className="text-lg font-mono font-semibold text-os-text-high mt-1">
              {loading ? "..." : s.value}
            </p>
          </div>
        ))}
      </div>

      {/* ── Filters ── */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-os-muted" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="按姓名或邮箱搜索..."
            className="w-full h-9 pl-9 pr-4 bg-os-surface border border-os-border rounded-lg text-xs text-os-text-high placeholder:text-os-subtle focus:outline-none focus:border-os-accent/50 focus:ring-1 focus:ring-os-accent/10 transition-all"
          />
        </div>
        <div className="relative">
          <select
            value={orgFilter}
            onChange={(e) => setOrgFilter(e.target.value)}
            className="h-9 pl-3 pr-8 bg-os-surface border border-os-border rounded-lg text-xs text-os-text-high focus:outline-none focus:border-os-accent/50 transition-all appearance-none cursor-pointer"
          >
            <option value="">所有组织</option>
            {orgs.map((o) => (
              <option key={o} value={o}>{o}</option>
            ))}
          </select>
          <ChevronDown size={12} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-os-muted pointer-events-none" />
        </div>
        <div className="relative">
          <select
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
            className="h-9 pl-3 pr-8 bg-os-surface border border-os-border rounded-lg text-xs text-os-text-high focus:outline-none focus:border-os-accent/50 transition-all appearance-none cursor-pointer"
          >
            <option value="">所有角色</option>
            {AVAILABLE_ROLES.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
          <ChevronDown size={12} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-os-muted pointer-events-none" />
        </div>
        {(search || orgFilter || roleFilter) && (
          <button
            onClick={() => { setSearch(""); setOrgFilter(""); setRoleFilter(""); }}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-2xs text-os-subtle hover:text-os-text bg-os-elevated/50 hover:bg-os-elevated transition-all border border-os-border/30"
          >
            <X size={12} />
            清除
          </button>
        )}
      </div>

      {/* ── Error ── */}
      {error && (
        <div className="flex items-start gap-3 rounded-lg border border-os-danger/20 bg-os-danger-soft p-3">
          <AlertCircle size={14} className="text-os-danger shrink-0 mt-0.5" />
          <div>
            <p className="text-xs text-os-danger font-medium">请求失败</p>
            <p className="mt-0.5 text-xs text-os-danger">{error}</p>
            <button
              onClick={handleRefresh}
              className="mt-1 text-2xs text-os-danger underline hover:text-os-danger-hover"
            >
              点击重试
            </button>
          </div>
        </div>
      )}

      {/* ── Loading ── */}
      {loading && !error && (
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-14 bg-os-surface rounded-lg animate-pulse border border-os-border/20 shimmer-bg" />
          ))}
        </div>
      )}

      {/* ── Empty ── */}
      {!loading && !error && filteredUsers.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 text-os-subtle">
          <div className="w-16 h-16 rounded-2xl bg-os-elevated border border-os-border/40 flex items-center justify-center mb-4">
            <Users size={28} className="opacity-40" />
          </div>
          <p className="text-sm text-os-text-high/80 font-medium">
            {users.length === 0 ? "暂无用户" : "无匹配结果"}
          </p>
          <p className="mt-1.5 max-w-xs text-center text-xs leading-5 text-os-subtle">
            {users.length === 0
              ? "系统尚未注册任何用户。启动服务时将根据 .env 配置自动创建管理员账号。"
              : "尝试调整搜索条件或筛选器。"}
          </p>
          {users.length === 0 && (
            <button
              onClick={handleRefresh}
              className="mt-4 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-os-accent bg-os-accent/5 border border-os-accent/10 hover:bg-os-accent/10 transition-colors"
            >
              <RefreshCw size={12} />
              重新加载
            </button>
          )}
        </div>
      )}

      {/* ── User Table ── */}
      {!loading && !error && filteredUsers.length > 0 && (
        <div className="os-card rounded-lg border border-os-border/30 bg-os-surface overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-os-border/30 bg-os-elevated/20 text-os-subtle">
                  <th className="text-left py-2.5 px-4 font-medium">姓名</th>
                  <th className="text-left py-2.5 px-4 font-medium">邮箱</th>
                  <th className="text-left py-2.5 px-4 font-medium hidden md:table-cell">组织</th>
                  <th className="text-left py-2.5 px-4 font-medium">角色</th>
                  <th className="text-left py-2.5 px-4 font-medium hidden lg:table-cell">部门</th>
                  <th className="text-right py-2.5 px-4 font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {filteredUsers.map((user) => (
                  <>
                    <tr key={user.id} className="border-b border-os-border/10 hover:bg-os-elevated/30 transition-colors">
                      <td className="py-2.5 px-4">
                        <div className="flex items-center gap-2.5">
                          <div className="w-7 h-7 rounded-lg bg-os-accent/10 flex items-center justify-center shrink-0">
                            <UserPlus size={13} className="text-os-accent/70" />
                          </div>
                          <span className="text-os-text-high font-medium">{user.name || "—"}</span>
                        </div>
                      </td>
                      <td className="py-2.5 px-4 text-os-text">{user.email}</td>
                      <td className="py-2.5 px-4 text-os-subtle hidden md:table-cell">
                        {user.org_name || user.org_id ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-2xs bg-os-elevated border border-os-border/30">
                            <Building2 size={10} />
                            {user.org_name || user.org_id}
                          </span>
                        ) : (
                          <span className="text-os-subtle">—</span>
                        )}
                      </td>
                      <td className="py-2.5 px-4">
                        <div className="flex flex-wrap gap-1">
                          {(user.roles || []).length === 0 ? (
                            <span className="text-2xs text-os-subtle">未分配</span>
                          ) : (
                            (user.roles || []).map((role) => (
                              <span
                                key={role}
                                className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-2xs bg-os-accent/10 text-os-accent border border-os-accent/10 cursor-default hover:border-os-accent/20 transition-colors group relative"
                              >
                                {role}
                                <button
                                  onClick={() => handleRemoveRole(user.id, role)}
                                  className="opacity-0 group-hover:opacity-100 transition-opacity p-0.5 rounded-sm hover:bg-red-400/10 text-os-accent hover:text-red-400"
                                >
                                  <X size={9} />
                                </button>
                              </span>
                            ))
                          )}
                        </div>
                      </td>
                      <td className="py-2.5 px-4 text-os-subtle hidden lg:table-cell">
                        {user.department || "—"}
                      </td>
                      <td className="py-2.5 px-4 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => handleFetchPermissions(user.id)}
                            className={cn(
                              "p-1.5 rounded-lg text-2xs transition-all border",
                              showPermsFor === user.id
                                ? "bg-os-accent/10 text-os-accent border-os-accent/15"
                                : "text-os-subtle hover:text-os-text hover:bg-os-elevated border-transparent"
                            )}
                            title="查看权限"
                          >
                            <Shield size={13} />
                          </button>
                          <button
                            onClick={() => {
                              setSelectedUser(user);
                              setAssigningRole("");
                              setShowRoleModal(true);
                            }}
                            className="p-1.5 rounded-lg text-2xs text-os-subtle hover:text-os-accent hover:bg-os-accent/5 border border-transparent hover:border-os-accent/10 transition-all"
                            title="分配角色"
                          >
                            <UserCog size={13} />
                          </button>
                        </div>
                      </td>
                    </tr>
                    {/* Permissions row */}
                    {showPermsFor === user.id && (
                      <tr key={`${user.id}-perms`} className="bg-os-elevated/10">
                        <td colSpan={6} className="py-3 px-6 animate-slide-up">
                          <div className="text-xs">
                            <p className="text-os-subtle mb-2 font-medium">权限：{user.name}</p>
                            {roles.length > 0 ? (
                              <div className="space-y-2">
                                {(user.roles || []).map((role) => {
                                  const roleDef = roles.find((r) => r.name === role || r.id === role);
                                  const perms = roleDef?.permissions;
                                  return (
                                    <div key={role} className="flex flex-col gap-1">
                                      <span className="text-2xs text-os-accent font-medium">{role}</span>
                                      {perms && perms.length > 0 ? (
                                        <div className="flex flex-wrap gap-1">
                                          {perms.map((p) => (
                                            <span key={p} className="px-1.5 py-0.5 rounded text-2xs bg-os-surface text-os-text border border-os-border/30">
                                              {p}
                                            </span>
                                          ))}
                                        </div>
                                      ) : (
                                        <span className="text-2xs text-os-subtle">
                                          {role} — 可在权限范围内查看、编辑和删除
                                        </span>
                                      )}
                                    </div>
                                  );
                                })}
                              </div>
                            ) : (
                              <span className="text-2xs text-os-subtle">未分配角色 — 无权限。</span>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Role Assignment Modal ── */}
      {showRoleModal && selectedUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-slate-950/20 backdrop-blur-sm" onClick={() => setShowRoleModal(false)} />
          <div className="relative bg-os-surface border border-os-border rounded-xl shadow-os-lg w-full max-w-md mx-4 p-5 z-10 animate-fade-in">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-os-text-high">
                分配角色 — {selectedUser.name}
              </h3>
              <button
                onClick={() => setShowRoleModal(false)}
                className="p-1 rounded-lg text-os-muted hover:text-os-text hover:bg-os-elevated transition-colors"
              >
                <X size={16} />
              </button>
            </div>
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-xs text-os-text mb-2">
                <span>当前角色：</span>
                {(selectedUser.roles || []).length === 0 ? (
                   <span className="text-os-subtle">无</span>
                ) : (
                  selectedUser.roles.map((r) => (
                    <span key={r} className="px-1.5 py-0.5 rounded text-2xs bg-os-accent/10 text-os-accent">{r}</span>
                  ))
                )}
              </div>
              <div>
                <label className="text-2xs text-os-subtle block mb-1">选择角色</label>
                <select
                  value={assigningRole}
                  onChange={(e) => setAssigningRole(e.target.value)}
                  className="w-full h-9 px-3 bg-os-base border border-os-border rounded-lg text-xs text-os-text-high focus:outline-none focus:border-os-accent/50 transition-all"
                >
                  <option value="">— 选择角色 —</option>
                  {AVAILABLE_ROLES.filter((r) => !(selectedUser.roles || []).includes(r)).map((r) => (
                    <option key={r} value={r}>{r}</option>
                  ))}
                </select>
                {assigningRole && (
                  <p className="mt-1.5 text-2xs leading-relaxed text-os-subtle">
                    {ROLE_DESCRIPTIONS[assigningRole]}
                  </p>
                )}
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  onClick={() => setShowRoleModal(false)}
                  className="px-3 py-1.5 rounded-lg text-xs text-os-subtle hover:text-os-text hover:bg-os-elevated transition-colors"
                >
                  取消
                </button>
                <button
                  onClick={handleAssignRole}
                  disabled={!assigningRole}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium bg-os-accent text-white hover:bg-os-accent/90 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  确认分配
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
