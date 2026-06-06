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
} from "lucide-react";
import { cn } from "@/lib/utils";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

// ── Types ──

interface UserRecord {
  id: string;
  name: string;
  email: string;
  roles: string[];
  department?: string;
  org_id?: string;
  org_name?: string;
  created_at?: string;
}

interface Role {
  id: string;
  name: string;
  permissions: string[];
}

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
  SuperAdmin: "Full system access across all organizations",
  OrgAdmin: "Manage a single organization and its users",
  DeptAdmin: "Manage a department and its members",
  Manager: "Manage team members and moderate content",
  Employee: "Standard user with basic access",
  Guest: "Read-only access to shared resources",
};

// ── API helper ──

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers as Record<string, string> || {}) },
  });
  if (!res.ok) {
    const body = await res.text();
    let msg = `API ${res.status}`;
    try {
      const j = JSON.parse(body);
      if (j.detail) msg = j.detail;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return res.json();
}

// ── Page ──

export default function UserManagementPage() {
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [search, setSearch] = useState("");
  const [orgFilter, setOrgFilter] = useState("");
  const [roleFilter, setRoleFilter] = useState("");

  // Role assignment modal
  const [selectedUser, setSelectedUser] = useState<UserRecord | null>(null);
  const [showRoleModal, setShowRoleModal] = useState(false);
  const [assigningRole, setAssigningRole] = useState("");

  // Permissions view
  const [showPermsFor, setShowPermsFor] = useState<string | null>(null);

  // Orgs for filter dropdown
  const [orgs, setOrgs] = useState<string[]>([]);

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<UserRecord[]>("/api/rbac/users");
      const userList = Array.isArray(data) ? data : [];
      setUsers(userList);
      // Extract unique org names for filter
      const orgNames = [...new Set(userList.map((u) => u.org_name || u.org_id || "").filter(Boolean))];
      setOrgs(orgNames);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load users");
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchRoles = useCallback(async () => {
    try {
      const data = await apiFetch<Role[]>("/api/rbac/roles");
      setRoles(Array.isArray(data) ? data : []);
    } catch {
      // roles endpoint may not exist, fall back to defaults
      setRoles(AVAILABLE_ROLES.map((r) => ({ id: r, name: r, permissions: [] })));
    }
  }, []);

  useEffect(() => {
    fetchUsers();
    fetchRoles();
  }, [fetchUsers, fetchRoles]);

  // ── Filtering ──

  const filteredUsers = users.filter((u) => {
    if (search && !u.name?.toLowerCase().includes(search.toLowerCase()) && !u.email?.toLowerCase().includes(search.toLowerCase())) {
      return false;
    }
    if (orgFilter && (u.org_name || u.org_id || "") !== orgFilter) return false;
    if (roleFilter && !u.roles?.includes(roleFilter)) return false;
    return true;
  });

  // ── Handlers ──

  const handleAssignRole = async () => {
    if (!selectedUser || !assigningRole) return;
    try {
      const newRoles = [...new Set([...(selectedUser.roles || []), assigningRole])];
      await apiFetch(`/api/rbac/users/${selectedUser.id}/roles`, {
        method: "PUT",
        body: JSON.stringify({ roles: newRoles }),
      });
      setShowRoleModal(false);
      setAssigningRole("");
      await fetchUsers();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to assign role");
    }
  };

  const handleRemoveRole = async (userId: string, role: string) => {
    if (!confirm(`Remove role "${role}" from this user?`)) return;
    const user = users.find((u) => u.id === userId);
    if (!user) return;
    try {
      const newRoles = (user.roles || []).filter((r) => r !== role);
      await apiFetch(`/api/rbac/users/${userId}/roles`, {
        method: "PUT",
        body: JSON.stringify({ roles: newRoles }),
      });
      await fetchUsers();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to remove role");
    }
  };

  const handleFetchPermissions = async (userId: string) => {
    if (showPermsFor === userId) {
      setShowPermsFor(null);
      return;
    }
    setShowPermsFor(userId);
  };

  // ── Render ──

  return (
    <div className="p-6 space-y-4 max-w-[1440px] mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-os-text-high tracking-tight">
            User Management
          </h1>
          <p className="text-xs text-os-subtle mt-0.5">
            {users.length} user{users.length !== 1 ? "s" : ""} registered
          </p>
        </div>
        <button
          onClick={fetchUsers}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-2xs text-os-subtle hover:text-os-text hover:bg-os-elevated transition-colors"
        >
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-os-muted" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name or email..."
            className="w-full h-9 pl-9 pr-4 bg-os-surface border border-os-border rounded-md text-xs text-os-text-high placeholder:text-os-muted focus:outline-none focus:border-os-accent transition-colors"
          />
        </div>
        <select
          value={orgFilter}
          onChange={(e) => setOrgFilter(e.target.value)}
          className="h-9 px-3 bg-os-surface border border-os-border rounded-md text-xs text-os-text-high focus:outline-none focus:border-os-accent transition-colors appearance-none cursor-pointer"
        >
          <option value="">All Organizations</option>
          {orgs.map((o) => (
            <option key={o} value={o}>{o}</option>
          ))}
        </select>
        <select
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value)}
          className="h-9 px-3 bg-os-surface border border-os-border rounded-md text-xs text-os-text-high focus:outline-none focus:border-os-accent transition-colors appearance-none cursor-pointer"
        >
          <option value="">All Roles</option>
          {AVAILABLE_ROLES.map((r) => (
            <option key={r} value={r}>{r}</option>
          ))}
        </select>
        {(search || orgFilter || roleFilter) && (
          <button
            onClick={() => { setSearch(""); setOrgFilter(""); setRoleFilter(""); }}
            className="flex items-center gap-1 px-2 py-1 rounded text-2xs text-os-muted hover:text-os-text transition-colors"
          >
            <X size={12} />
            Clear
          </button>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="os-card p-3 rounded-lg border border-red-400/20 bg-red-400/5 text-red-400 text-xs">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-14 bg-os-elevated rounded-lg animate-pulse" />
          ))}
        </div>
      )}

      {/* Empty */}
      {!loading && filteredUsers.length === 0 && (
        <div className="flex flex-col items-center justify-center py-24 text-os-muted">
          <Users size={48} className="mb-4 opacity-30" />
          <p className="text-sm">No users found</p>
          <p className="text-2xs mt-1">
            {search || orgFilter || roleFilter ? "Try adjusting your filters" : "No users registered yet"}
          </p>
        </div>
      )}

      {/* User Table */}
      {!loading && filteredUsers.length > 0 && (
        <div className="os-card rounded-lg border border-os-border/30 bg-os-surface overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-os-muted border-b border-os-border/30 bg-os-elevated/30">
                  <th className="text-left py-2.5 px-3 font-medium">Name</th>
                  <th className="text-left py-2.5 px-3 font-medium">Email</th>
                  <th className="text-left py-2.5 px-3 font-medium hidden md:table-cell">Organization</th>
                  <th className="text-left py-2.5 px-3 font-medium">Roles</th>
                  <th className="text-left py-2.5 px-3 font-medium hidden lg:table-cell">Department</th>
                  <th className="text-right py-2.5 px-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredUsers.map((user) => (
                  <>
                    <tr key={user.id} className="border-b border-os-border/10 hover:bg-os-elevated/30 transition-colors">
                      <td className="py-2.5 px-3 text-os-text-high font-medium">{user.name}</td>
                      <td className="py-2.5 px-3 text-os-text">{user.email}</td>
                      <td className="py-2.5 px-3 text-os-subtle hidden md:table-cell">
                        {user.org_name || user.org_id || "-"}
                      </td>
                      <td className="py-2.5 px-3">
                        <div className="flex flex-wrap gap-1">
                          {(user.roles || []).length === 0 ? (
                            <span className="text-2xs text-os-muted">No roles</span>
                          ) : (
                            (user.roles || []).map((role) => (
                              <span
                                key={role}
                                className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-2xs bg-os-accent/10 text-os-accent cursor-pointer hover:bg-os-accent/20 transition-colors group relative"
                              >
                                {role}
                                <button
                                  onClick={() => handleRemoveRole(user.id, role)}
                                  className="opacity-0 group-hover:opacity-100 transition-opacity"
                                >
                                  <X size={10} />
                                </button>
                              </span>
                            ))
                          )}
                        </div>
                      </td>
                      <td className="py-2.5 px-3 text-os-subtle hidden lg:table-cell">
                        {user.department || "-"}
                      </td>
                      <td className="py-2.5 px-3 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => handleFetchPermissions(user.id)}
                            className={cn(
                              "p-1.5 rounded text-2xs transition-colors",
                              showPermsFor === user.id
                                ? "bg-os-accent/10 text-os-accent"
                                : "text-os-subtle hover:text-os-text hover:bg-os-elevated"
                            )}
                            title="View Permissions"
                          >
                            <Shield size={13} />
                          </button>
                          <button
                            onClick={() => {
                              setSelectedUser(user);
                              setAssigningRole("");
                              setShowRoleModal(true);
                            }}
                            className="p-1.5 rounded text-2xs text-os-subtle hover:text-os-text hover:bg-os-elevated transition-colors"
                            title="Assign Role"
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
                            <p className="text-os-subtle mb-2 font-medium">Permissions for {user.name}:</p>
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
                                        <span className="text-2xs text-os-muted">
                                          {role} — View / Edit / Delete access in scope
                                        </span>
                                      )}
                                    </div>
                                  );
                                })}
                              </div>
                            ) : (
                              <span className="text-2xs text-os-muted">No roles assigned — no permissions.</span>
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

      {/* Role Assignment Modal */}
      {showRoleModal && selectedUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/60" onClick={() => setShowRoleModal(false)} />
          <div className="relative bg-os-surface border border-os-border rounded-lg shadow-os-lg w-full max-w-md mx-4 p-5 z-10 animate-fade-in">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-os-text-high">
                Assign Role — {selectedUser.name}
              </h3>
              <button onClick={() => setShowRoleModal(false)} className="text-os-muted hover:text-os-text transition-colors">
                <X size={16} />
              </button>
            </div>
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-xs text-os-text mb-2">
                <span>Current roles:</span>
                {(selectedUser.roles || []).length === 0 ? (
                  <span className="text-os-muted">None</span>
                ) : (
                  selectedUser.roles.map((r) => (
                    <span key={r} className="px-1.5 py-0.5 rounded text-2xs bg-os-accent/10 text-os-accent">{r}</span>
                  ))
                )}
              </div>
              <div>
                <label className="text-2xs text-os-subtle block mb-1">Select Role</label>
                <select
                  value={assigningRole}
                  onChange={(e) => setAssigningRole(e.target.value)}
                  className="w-full h-9 px-3 bg-os-base border border-os-border rounded-md text-xs text-os-text-high focus:outline-none focus:border-os-accent transition-colors"
                >
                  <option value="">— Choose a role —</option>
                  {AVAILABLE_ROLES.filter((r) => !(selectedUser.roles || []).includes(r)).map((r) => (
                    <option key={r} value={r}>{r}</option>
                  ))}
                </select>
                {assigningRole && (
                  <p className="text-2xs text-os-muted mt-1.5">
                    {ROLE_DESCRIPTIONS[assigningRole]}
                  </p>
                )}
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button onClick={() => setShowRoleModal(false)} className="px-3 py-1.5 rounded-md text-xs text-os-subtle hover:text-os-text transition-colors">
                  Cancel
                </button>
                <button
                  onClick={handleAssignRole}
                  disabled={!assigningRole}
                  className="px-3 py-1.5 rounded-md text-xs font-medium bg-os-accent text-white hover:bg-os-accent/90 transition-colors disabled:opacity-50"
                >
                  Assign
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
