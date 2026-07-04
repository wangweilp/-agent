"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Shield,
  Plus,
  X,
  RefreshCw,
  Edit3,
  Trash2,
  Database,
  Key,
  ToggleLeft,
  ToggleRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiFetch } from "@/services/api";

// ── Types ──

interface RetentionPolicy {
  id: string;
  name: string;
  description: string;
  resource_type: string;
  retention_period: string;
  archive_action: string;
  organization_id?: string;
  enabled: boolean;
}

interface AbacPolicy {
  id: string;
  name: string;
  effect: string;
  priority: number;
  conditions: Record<string, unknown>;
  enabled: boolean;
  description: string;
}

interface Role {
  id: string;
  name: string;
  permissions: string[];
  is_system: boolean;
}

// ── Constants ──

const DEFAULT_ROLES: { name: string; description: string; permissions: string[] }[] = [
  {
    name: "SuperAdmin",
    description: "Complete system access across all organizations.",
    permissions: [
      "org:create", "org:delete", "org:manage",
      "user:create", "user:delete", "user:manage",
      "role:assign", "policy:manage",
      "audit:view", "audit:export",
      "memory:all", "deployment:view",
    ],
  },
  {
    name: "OrgAdmin",
    description: "Manage a single organization and its users.",
    permissions: [
      "org:manage", "user:create", "user:manage",
      "role:assign", "audit:view",
      "memory:org_all",
    ],
  },
  {
    name: "DeptAdmin",
    description: "Manage department members and resources.",
    permissions: [
      "user:manage", "role:assign",
      "memory:dept_all",
    ],
  },
  {
    name: "Manager",
    description: "Manage team members and moderate content.",
    permissions: [
      "user:view", "memory:team_write",
      "audit:view",
    ],
  },
  {
    name: "Employee",
    description: "Standard user with read/write access to own content.",
    permissions: [
      "memory:read", "memory:write",
    ],
  },
  {
    name: "Guest",
    description: "Read-only access to shared resources.",
    permissions: [
      "memory:read",
    ],
  },
];

// ── Tab ──

type Tab = "retention" | "abac" | "roles";

// ── Page ──

export default function PolicyCenterPage() {
  const [tab, setTab] = useState<Tab>("retention");

  // Retention
  const [retPolicies, setRetPolicies] = useState<RetentionPolicy[]>([]);
  const [retLoading, setRetLoading] = useState(true);
  const [retError, setRetError] = useState<string | null>(null);

  // ABAC
  const [abacPolicies, setAbacPolicies] = useState<AbacPolicy[]>([]);
  const [abacLoading, setAbacLoading] = useState(true);
  const [abacError, setAbacError] = useState<string | null>(null);

  // Roles
  const [roles, setRoles] = useState<Role[]>([]);

  // Org ID (lazy init)
  const [orgId, setOrgId] = useState("");

  // Modals
  const [showRetModal, setShowRetModal] = useState(false);
  const [showAbacModal, setShowAbacModal] = useState(false);
  const [editingRet, setEditingRet] = useState<RetentionPolicy | null>(null);
  const [editingAbac, setEditingAbac] = useState<AbacPolicy | null>(null);

  // Retention form
  const [retForm, setRetForm] = useState({
    name: "",
    resource_type: "memory",
    retention_period: "1y",
    archive_action: "archive",
    description: "",
  });

  // ABAC form
  const [abacForm, setAbacForm] = useState({
    name: "",
    effect: "deny",
    priority: 100,
    description: "",
    conditionsJson: "{}",
  });

  // ── Fetch org ID ──

  useEffect(() => {
    apiFetch<Array<{ id: string }>>("/api/org")
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          setOrgId(data[0].id);
        }
      })
      .catch(() => {});
  }, []);

  // ── Fetch ──

  const fetchRetention = useCallback(async () => {
    setRetLoading(true);
    setRetError(null);
    try {
      const qs = orgId ? `?org_id=${orgId}` : "";
      const data = await apiFetch<RetentionPolicy[]>(`/api/compliance/policies${qs}`);
      setRetPolicies(Array.isArray(data) ? data : []);
    } catch (err: unknown) {
      setRetError(err instanceof Error ? err.message : "Failed to load retention policies");
    } finally {
      setRetLoading(false);
    }
  }, [orgId]);

  const fetchAbac = useCallback(async () => {
    setAbacLoading(true);
    setAbacError(null);
    try {
      const qs = orgId ? `?org_id=${orgId}` : "";
      const data = await apiFetch<AbacPolicy[]>(`/api/rbac/policies${qs}`);
      setAbacPolicies(Array.isArray(data) ? data : []);
    } catch (err: unknown) {
      setAbacError(err instanceof Error ? err.message : "Failed to load ABAC policies");
    } finally {
      setAbacLoading(false);
    }
  }, [orgId]);

  const fetchRoles = useCallback(async () => {
    try {
      const qs = orgId ? `?org_id=${orgId}` : "";
      const data = await apiFetch<Role[]>(`/api/rbac/roles${qs}`);
      setRoles(Array.isArray(data) ? data : []);
    } catch {
      setRoles([]);
    }
  }, [orgId]);

  useEffect(() => {
    fetchRetention();
    fetchAbac();
    fetchRoles();
  }, [fetchRetention, fetchAbac, fetchRoles]);

  // ── Retention CRUD ──

  const openCreateRet = () => {
    setEditingRet(null);
    setRetForm({ name: "", resource_type: "memory", retention_period: "1y", archive_action: "archive", description: "" });
    setShowRetModal(true);
  };

  const openEditRet = (p: RetentionPolicy) => {
    setEditingRet(p);
    setRetForm({
      name: p.name,
      resource_type: p.resource_type,
      retention_period: p.retention_period,
      archive_action: p.archive_action,
      description: p.description || "",
    });
    setShowRetModal(true);
  };

  const saveRetention = async () => {
    try {
      const body = { ...retForm, enabled: true, organization_id: orgId };
      if (editingRet) {
        await apiFetch(`/api/compliance/policies/${editingRet.id}`, {
          method: "PUT",
          body: JSON.stringify(body),
        });
      } else {
        await apiFetch("/api/compliance/policies", {
          method: "POST",
          body: JSON.stringify(body),
        });
      }
      setShowRetModal(false);
      await fetchRetention();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to save retention policy");
    }
  };

  const toggleRetention = async (p: RetentionPolicy) => {
    try {
      await apiFetch(`/api/compliance/policies/${p.id}`, {
        method: "PUT",
        body: JSON.stringify({ ...p, enabled: !p.enabled }),
      });
      await fetchRetention();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to toggle policy");
    }
  };

  const deleteRetention = async (id: string) => {
    if (!confirm("Delete this retention policy?")) return;
    try {
      await apiFetch(`/api/compliance/policies/${id}`, { method: "DELETE" });
      await fetchRetention();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to delete retention policy");
    }
  };

  // ── ABAC CRUD ──

  const openCreateAbac = () => {
    setEditingAbac(null);
    setAbacForm({ name: "", effect: "deny", priority: 100, description: "", conditionsJson: "{}" });
    setShowAbacModal(true);
  };

  const openEditAbac = (p: AbacPolicy) => {
    setEditingAbac(p);
    setAbacForm({
      name: p.name,
      effect: p.effect,
      priority: p.priority,
      description: p.description || "",
      conditionsJson: JSON.stringify(p.conditions, null, 2),
    });
    setShowAbacModal(true);
  };

  const saveAbac = async () => {
    try {
      let conditions = {};
      try { conditions = JSON.parse(abacForm.conditionsJson); } catch { alert("Invalid JSON in conditions"); return; }
      const body = { ...abacForm, conditions, enabled: true, organization_id: orgId };
      if (editingAbac) {
        await apiFetch(`/api/rbac/policies/${editingAbac.id}`, {
          method: "PUT",
          body: JSON.stringify(body),
        });
      } else {
        await apiFetch("/api/rbac/policies", {
          method: "POST",
          body: JSON.stringify(body),
        });
      }
      setShowAbacModal(false);
      await fetchAbac();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to save ABAC policy");
    }
  };

  const deleteAbac = async (id: string) => {
    if (!confirm("Delete this ABAC policy?")) return;
    try {
      await apiFetch(`/api/rbac/policies/${id}`, { method: "DELETE" });
      await fetchAbac();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to delete ABAC policy");
    }
  };

  // ── Render ──

  const tabs = [
    { key: "retention" as const, label: "Data Retention", icon: Database },
    { key: "abac" as const, label: "ABAC Policies", icon: Key },
    { key: "roles" as const, label: "Roles & Permissions", icon: Shield },
  ];

  return (
    <div className="p-6 space-y-4 max-w-[1440px] mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-os-text-high tracking-tight">策略中心</h1>
          <p className="text-xs text-os-subtle mt-0.5">管理数据留存、访问控制与角色权限</p>
        </div>
        <button
          onClick={() => { fetchRetention(); fetchAbac(); fetchRoles(); }}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-2xs text-os-subtle hover:text-os-text hover:bg-os-elevated transition-colors"
        >
          <RefreshCw size={12} />
          刷新
        </button>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 p-0.5 bg-os-surface border border-os-border rounded-lg w-fit">
        {tabs.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-2xs font-medium transition-colors",
              tab === key
                ? "bg-os-accent/10 text-os-accent"
                : "text-os-subtle hover:text-os-text"
            )}
          >
            <Icon size={12} />
            {label}
          </button>
        ))}
      </div>

      {/* Global error */}
      {(retError || abacError) && (
        <div className="os-card p-3 rounded-lg border border-red-400/20 bg-red-400/5 text-red-400 text-xs">
          {retError || abacError}
        </div>
      )}

      {/* ── Retention Tab ── */}
      {tab === "retention" && (
        <div className="space-y-4 animate-fade-in">
          <div className="flex items-center justify-between">
            <p className="text-xs text-os-muted">
              {retPolicies.length} polic{retPolicies.length !== 1 ? "ies" : "y"}
            </p>
            <button
              onClick={openCreateRet}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-2xs font-medium bg-os-accent text-white hover:bg-os-accent/90 transition-colors"
            >
              <Plus size={12} />
              New Retention Policy
            </button>
          </div>

          {retLoading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-12 bg-os-elevated rounded-lg animate-pulse" />
              ))}
            </div>
          ) : retPolicies.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-24 text-os-muted">
              <Database size={48} className="mb-4 opacity-30" />
              <p className="text-sm">No retention policies configured</p>
              <p className="text-2xs mt-1">Create a policy to manage data lifecycle</p>
            </div>
          ) : (
            <div className="os-card rounded-lg border border-os-border/30 bg-os-surface overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-os-muted border-b border-os-border/30 bg-os-elevated/30">
                      <th className="text-left py-2.5 px-3 font-medium">Name</th>
                      <th className="text-left py-2.5 px-3 font-medium">Resource</th>
                      <th className="text-left py-2.5 px-3 font-medium">Period</th>
                      <th className="text-left py-2.5 px-3 font-medium">Action</th>
                      <th className="text-center py-2.5 px-3 font-medium">Status</th>
                      <th className="text-right py-2.5 px-3 font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {retPolicies.map((p) => (
                      <tr key={p.id} className="border-b border-os-border/10 hover:bg-os-elevated/30 transition-colors">
                        <td className="py-2.5 px-3 text-os-text-high font-medium">
                          {p.name}
                          {p.description && (
                            <br />
                          )}
                          {p.description && (
                            <span className="text-2xs text-os-muted">{p.description}</span>
                          )}
                        </td>
                        <td className="py-2.5 px-3 text-os-text">{p.resource_type}</td>
                        <td className="py-2.5 px-3 text-os-text">{p.retention_period}</td>
                        <td className="py-2.5 px-3 text-os-text capitalize">{p.archive_action}</td>
                        <td className="py-2.5 px-3 text-center">
                          <button onClick={() => toggleRetention(p)} className="transition-colors">
                            {p.enabled ? (
                              <ToggleRight size={18} className="text-emerald-400" />
                            ) : (
                              <ToggleLeft size={18} className="text-os-muted" />
                            )}
                          </button>
                        </td>
                        <td className="py-2.5 px-3 text-right">
                          <div className="flex items-center justify-end gap-1">
                            <button onClick={() => openEditRet(p)} className="p-1 rounded text-os-subtle hover:text-os-text transition-colors">
                              <Edit3 size={12} />
                            </button>
                            <button onClick={() => deleteRetention(p.id)} className="p-1 rounded text-os-muted hover:text-red-400 transition-colors">
                              <Trash2 size={12} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── ABAC Tab ── */}
      {tab === "abac" && (
        <div className="space-y-4 animate-fade-in">
          <div className="flex items-center justify-between">
            <p className="text-xs text-os-muted">
              {abacPolicies.length} polic{abacPolicies.length !== 1 ? "ies" : "y"}
            </p>
            <button
              onClick={openCreateAbac}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-2xs font-medium bg-os-accent text-white hover:bg-os-accent/90 transition-colors"
            >
              <Plus size={12} />
              New ABAC Policy
            </button>
          </div>

          {abacLoading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-24 bg-os-elevated rounded-lg animate-pulse" />
              ))}
            </div>
          ) : abacPolicies.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-24 text-os-muted">
              <Key size={48} className="mb-4 opacity-30" />
              <p className="text-sm">No ABAC policies configured</p>
              <p className="text-2xs mt-1">Create attribute-based access control rules</p>
            </div>
          ) : (
            <div className="space-y-3">
              {abacPolicies.map((p) => (
                <div key={p.id} className="os-card p-4 rounded-lg border border-os-border/30 bg-os-surface hover:border-os-border/60 transition-colors">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold text-os-text-high">{p.name}</span>
                      <span
                        className={cn(
                          "px-1.5 py-0.5 rounded text-2xs font-bold uppercase",
                          p.effect === "deny"
                            ? "bg-red-400/10 text-red-400"
                            : "bg-emerald-400/10 text-emerald-400"
                        )}
                      >
                        {p.effect}
                      </span>
                      {!p.enabled && (
                        <span className="px-1.5 py-0.5 rounded text-2xs bg-os-elevated text-os-muted">Disabled</span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-2xs text-os-muted">Priority: {p.priority}</span>
                      <button onClick={() => openEditAbac(p)} className="p-1 rounded text-os-subtle hover:text-os-text transition-colors">
                        <Edit3 size={12} />
                      </button>
                      <button onClick={() => deleteAbac(p.id)} className="p-1 rounded text-os-muted hover:text-red-400 transition-colors">
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </div>
                  {p.description && (
                    <p className="text-2xs text-os-muted mb-2">{p.description}</p>
                  )}
                  <pre className="p-2 bg-os-elevated rounded text-2xs text-os-text overflow-x-auto border border-os-border/30">
                    {JSON.stringify(p.conditions, null, 2)}
                  </pre>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Roles & Permissions Tab ── */}
      {tab === "roles" && (
        <div className="space-y-6 animate-fade-in">
          {/* Built-in roles */}
          <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
            {DEFAULT_ROLES.map((role) => (
              <div key={role.name} className="os-card p-4 rounded-lg border border-os-border/30 bg-os-surface">
                <div className="flex items-center gap-2 mb-3">
                  <Shield size={14} className="text-os-accent" />
                  <h3 className="text-xs font-semibold text-os-text-high">{role.name}</h3>
                </div>
                <p className="text-2xs text-os-muted mb-3 leading-relaxed">{role.description}</p>
                <div>
                  <p className="text-2xs text-os-subtle uppercase tracking-wider mb-1.5">
                    Permissions ({role.permissions.length})
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {role.permissions.map((perm) => (
                      <span key={perm} className="px-1.5 py-0.5 rounded text-2xs bg-os-elevated text-os-text border border-os-border/30">
                        {perm}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Server-side roles if any */}
          {roles.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-xs font-semibold text-os-text-high">Custom Roles</h3>
              {roles.map((role) => (
                <div key={role.id} className="os-card p-4 rounded-lg border border-os-border/30 bg-os-surface">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Shield size={14} className="text-os-accent" />
                      <span className="text-xs font-semibold text-os-text-high">{role.name}</span>
                      {role.is_system && (
                        <span className="px-1.5 py-0.5 rounded text-2xs bg-os-accent/10 text-os-accent">System</span>
                      )}
                    </div>
                    <span className="text-2xs text-os-muted">{role.permissions.length} permissions</span>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {role.permissions.map((p) => (
                      <span key={p} className="px-1.5 py-0.5 rounded text-2xs bg-os-elevated text-os-text border border-os-border/30">
                        {p}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Permissions Matrix */}
          <div className="os-card rounded-lg border border-os-border/30 bg-os-surface overflow-hidden">
            <div className="p-4 border-b border-os-border/30">
              <h3 className="text-xs font-semibold text-os-text-high">Permissions Matrix</h3>
              <p className="text-2xs text-os-muted mt-0.5">Role-to-permission mapping overview</p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-os-muted border-b border-os-border/30 bg-os-elevated/30">
                    <th className="text-left py-2 px-3 font-medium sticky left-0 bg-os-elevated/30 z-10">Permission</th>
                    {DEFAULT_ROLES.map((r) => (
                      <th key={r.name} className="text-center py-2 px-3 font-medium whitespace-nowrap">{r.name}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(() => {
                    const allPerms = [...new Set(DEFAULT_ROLES.flatMap((r) => r.permissions))].sort();
                    return allPerms.map((perm) => (
                      <tr key={perm} className="border-b border-os-border/10 hover:bg-os-elevated/20 transition-colors">
                        <td className="py-1.5 px-3 text-os-text sticky left-0 bg-os-surface font-mono text-2xs">{perm}</td>
                        {DEFAULT_ROLES.map((role) => (
                          <td key={role.name} className="text-center py-1.5 px-3">
                            {role.permissions.includes(perm) ? (
                              <span className="inline-block w-2 h-2 rounded-full bg-emerald-400" />
                            ) : (
                              <span className="inline-block w-2 h-2 rounded-full bg-os-border/50" />
                            )}
                          </td>
                        ))}
                      </tr>
                    ));
                  })()}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ── Retention Modal ── */}
      {showRetModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-slate-950/20" onClick={() => setShowRetModal(false)} />
          <div className="relative bg-os-surface border border-os-border rounded-lg shadow-os-lg w-full max-w-sm mx-4 p-5 z-10 animate-fade-in">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-os-text-high">
                {editingRet ? "Edit" : "Create"} Retention Policy
              </h3>
              <button onClick={() => setShowRetModal(false)} className="text-os-muted hover:text-os-text transition-colors">
                <X size={16} />
              </button>
            </div>
            <div className="space-y-3">
              <input
                className="w-full h-9 px-3 bg-os-base border border-os-border rounded-md text-xs text-os-text-high placeholder:text-os-muted focus:outline-none focus:border-os-accent transition-colors"
                placeholder="Name"
                value={retForm.name}
                onChange={(e) => setRetForm({ ...retForm, name: e.target.value })}
              />
              <select
                className="w-full h-9 px-3 bg-os-base border border-os-border rounded-md text-xs text-os-text-high focus:outline-none focus:border-os-accent transition-colors"
                value={retForm.resource_type}
                onChange={(e) => setRetForm({ ...retForm, resource_type: e.target.value })}
              >
                <option value="memory">memory</option>
                <option value="audit_log">audit_log</option>
                <option value="notification">notification</option>
                <option value="import_job">import_job</option>
              </select>
              <select
                className="w-full h-9 px-3 bg-os-base border border-os-border rounded-md text-xs text-os-text-high focus:outline-none focus:border-os-accent transition-colors"
                value={retForm.retention_period}
                onChange={(e) => setRetForm({ ...retForm, retention_period: e.target.value })}
              >
                <option value="30d">30 days</option>
                <option value="90d">90 days</option>
                <option value="180d">180 days</option>
                <option value="1y">1 year</option>
                <option value="3y">3 years</option>
                <option value="7y">7 years</option>
                <option value="forever">Forever</option>
              </select>
              <select
                className="w-full h-9 px-3 bg-os-base border border-os-border rounded-md text-xs text-os-text-high focus:outline-none focus:border-os-accent transition-colors"
                value={retForm.archive_action}
                onChange={(e) => setRetForm({ ...retForm, archive_action: e.target.value })}
              >
                <option value="archive">Archive</option>
                <option value="delete">Delete</option>
                <option value="anonymize">Anonymize</option>
              </select>
              <textarea
                className="w-full px-3 py-2 bg-os-base border border-os-border rounded-md text-xs text-os-text-high placeholder:text-os-muted focus:outline-none focus:border-os-accent transition-colors resize-none"
                placeholder="Description (optional)"
                value={retForm.description}
                onChange={(e) => setRetForm({ ...retForm, description: e.target.value })}
                rows={2}
              />
              <div className="flex justify-end gap-2 pt-2">
                <button onClick={() => setShowRetModal(false)} className="px-3 py-1.5 rounded-md text-xs text-os-subtle hover:text-os-text transition-colors">
                  Cancel
                </button>
                <button
                  onClick={saveRetention}
                  disabled={!retForm.name.trim()}
                  className="px-3 py-1.5 rounded-md text-xs font-medium bg-os-accent text-white hover:bg-os-accent/90 transition-colors disabled:opacity-50"
                >
                  {editingRet ? "Update" : "Create"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── ABAC Modal ── */}
      {showAbacModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-slate-950/20" onClick={() => setShowAbacModal(false)} />
          <div className="relative bg-os-surface border border-os-border rounded-lg shadow-os-lg w-full max-w-sm mx-4 p-5 z-10 animate-fade-in">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-os-text-high">
                {editingAbac ? "Edit" : "Create"} ABAC Policy
              </h3>
              <button onClick={() => setShowAbacModal(false)} className="text-os-muted hover:text-os-text transition-colors">
                <X size={16} />
              </button>
            </div>
            <div className="space-y-3">
              <input
                className="w-full h-9 px-3 bg-os-base border border-os-border rounded-md text-xs text-os-text-high placeholder:text-os-muted focus:outline-none focus:border-os-accent transition-colors"
                placeholder="Name"
                value={abacForm.name}
                onChange={(e) => setAbacForm({ ...abacForm, name: e.target.value })}
              />
              <select
                className="w-full h-9 px-3 bg-os-base border border-os-border rounded-md text-xs text-os-text-high focus:outline-none focus:border-os-accent transition-colors"
                value={abacForm.effect}
                onChange={(e) => setAbacForm({ ...abacForm, effect: e.target.value })}
              >
                <option value="deny">Deny</option>
                <option value="allow">Allow</option>
              </select>
              <input
                className="w-full h-9 px-3 bg-os-base border border-os-border rounded-md text-xs text-os-text-high placeholder:text-os-muted focus:outline-none focus:border-os-accent transition-colors"
                type="number"
                placeholder="Priority (lower = higher)"
                value={abacForm.priority}
                onChange={(e) => setAbacForm({ ...abacForm, priority: parseInt(e.target.value) || 100 })}
              />
              <textarea
                className="w-full px-3 py-2 bg-os-base border border-os-border rounded-md text-xs text-os-text-high placeholder:text-os-muted focus:outline-none focus:border-os-accent transition-colors font-mono resize-none"
                placeholder='Conditions JSON, e.g. {"subject.org_id":{"eq":"org-1"}}'
                value={abacForm.conditionsJson}
                onChange={(e) => setAbacForm({ ...abacForm, conditionsJson: e.target.value })}
                rows={4}
              />
              <input
                className="w-full h-9 px-3 bg-os-base border border-os-border rounded-md text-xs text-os-text-high placeholder:text-os-muted focus:outline-none focus:border-os-accent transition-colors"
                placeholder="Description (optional)"
                value={abacForm.description}
                onChange={(e) => setAbacForm({ ...abacForm, description: e.target.value })}
              />
              <div className="flex justify-end gap-2 pt-2">
                <button onClick={() => setShowAbacModal(false)} className="px-3 py-1.5 rounded-md text-xs text-os-subtle hover:text-os-text transition-colors">
                  Cancel
                </button>
                <button
                  onClick={saveAbac}
                  disabled={!abacForm.name.trim()}
                  className="px-3 py-1.5 rounded-md text-xs font-medium bg-os-accent text-white hover:bg-os-accent/90 transition-colors disabled:opacity-50"
                >
                  {editingAbac ? "Update" : "Create"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
