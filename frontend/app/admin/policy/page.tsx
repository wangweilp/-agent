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
    description: "拥有跨组织的完整系统访问权限。",
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
    description: "管理单个组织及其用户。",
    permissions: [
      "org:manage", "user:create", "user:manage",
      "role:assign", "audit:view",
      "memory:org_all",
    ],
  },
  {
    name: "DeptAdmin",
    description: "管理部门成员与资源。",
    permissions: [
      "user:manage", "role:assign",
      "memory:dept_all",
    ],
  },
  {
    name: "Manager",
    description: "管理团队成员并审核内容。",
    permissions: [
      "user:view", "memory:team_write",
      "audit:view",
    ],
  },
  {
    name: "Employee",
    description: "可读写本人内容的标准用户。",
    permissions: [
      "memory:read", "memory:write",
    ],
  },
  {
    name: "Guest",
    description: "仅可读取共享资源。",
    permissions: [
      "memory:read",
    ],
  },
];

const ROLE_LABELS: Record<string, string> = {
  SuperAdmin: "超级管理员",
  OrgAdmin: "组织管理员",
  DeptAdmin: "部门管理员",
  Manager: "经理",
  Employee: "员工",
  Guest: "访客",
};

const RESOURCE_LABELS: Record<string, string> = {
  memory: "记忆",
  audit_log: "审计日志",
  notification: "通知",
  import_job: "导入任务",
};

const RETENTION_PERIOD_LABELS: Record<string, string> = {
  "30d": "30 天",
  "90d": "90 天",
  "180d": "180 天",
  "1y": "1 年",
  "3y": "3 年",
  "7y": "7 年",
  forever: "永久保留",
};

const ARCHIVE_ACTION_LABELS: Record<string, string> = {
  archive: "归档",
  delete: "删除",
  anonymize: "匿名化",
};

const EFFECT_LABELS: Record<string, string> = {
  deny: "拒绝",
  allow: "允许",
};

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
      setRetError(err instanceof Error ? err.message : "数据留存策略加载失败");
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
      setAbacError(err instanceof Error ? err.message : "ABAC 策略加载失败");
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
      alert(err instanceof Error ? err.message : "数据留存策略保存失败");
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
      alert(err instanceof Error ? err.message : "策略状态更新失败");
    }
  };

  const deleteRetention = async (id: string) => {
    if (!confirm("确认删除这条数据留存策略？")) return;
    try {
      await apiFetch(`/api/compliance/policies/${id}`, { method: "DELETE" });
      await fetchRetention();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "数据留存策略删除失败");
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
      try { conditions = JSON.parse(abacForm.conditionsJson); } catch { alert("条件中的 JSON 无效"); return; }
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
      alert(err instanceof Error ? err.message : "ABAC 策略保存失败");
    }
  };

  const deleteAbac = async (id: string) => {
    if (!confirm("确认删除这条 ABAC 策略？")) return;
    try {
      await apiFetch(`/api/rbac/policies/${id}`, { method: "DELETE" });
      await fetchAbac();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "ABAC 策略删除失败");
    }
  };

  // ── Render ──

  const tabs = [
    { key: "retention" as const, label: "数据留存", icon: Database },
    { key: "abac" as const, label: "ABAC 策略", icon: Key },
    { key: "roles" as const, label: "角色与权限", icon: Shield },
  ];
  const activeError = tab === "retention" ? retError : tab === "abac" ? abacError : null;

  return (
    <div className="p-6 space-y-4 max-w-[1440px] mx-auto">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
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
      <div className="overflow-x-auto">
        <div className="flex min-w-max items-center gap-1 rounded-lg border border-os-border bg-os-surface p-0.5">
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
      </div>

      {/* Global error */}
      {activeError && (
        <div className="os-card rounded-lg border border-os-danger/20 bg-os-danger-soft p-3 text-xs text-os-danger">
          {activeError}
        </div>
      )}

      {/* ── Retention Tab ── */}
      {tab === "retention" && (
        <div className="space-y-4 animate-fade-in">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs text-os-subtle">
              {retPolicies.length} 条策略
            </p>
            <button
              onClick={openCreateRet}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-2xs font-medium bg-os-accent text-white hover:bg-os-accent/90 transition-colors"
            >
              <Plus size={12} />
              新建数据留存策略
            </button>
          </div>

          {retLoading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-12 bg-os-elevated rounded-lg animate-pulse" />
              ))}
            </div>
          ) : retError && retPolicies.length === 0 ? null : retPolicies.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-24 text-os-subtle">
              <Database size={48} className="mb-4 opacity-30" />
              <p className="text-sm">尚未配置数据留存策略</p>
              <p className="text-2xs mt-1">创建策略以管理数据生命周期</p>
            </div>
          ) : (
            <div className="os-card rounded-lg border border-os-border/30 bg-os-surface overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-os-subtle border-b border-os-border/30 bg-os-elevated/30">
                      <th className="text-left py-2.5 px-3 font-medium">名称</th>
                      <th className="text-left py-2.5 px-3 font-medium">资源</th>
                      <th className="text-left py-2.5 px-3 font-medium">留存周期</th>
                      <th className="text-left py-2.5 px-3 font-medium">到期操作</th>
                      <th className="text-center py-2.5 px-3 font-medium">状态</th>
                      <th className="text-right py-2.5 px-3 font-medium">操作</th>
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
                            <span className="text-2xs text-os-subtle">{p.description}</span>
                          )}
                        </td>
                        <td className="py-2.5 px-3 text-os-text">{RESOURCE_LABELS[p.resource_type] || p.resource_type}</td>
                        <td className="py-2.5 px-3 text-os-text">{RETENTION_PERIOD_LABELS[p.retention_period] || p.retention_period}</td>
                        <td className="py-2.5 px-3 text-os-text">{ARCHIVE_ACTION_LABELS[p.archive_action] || p.archive_action}</td>
                        <td className="py-2.5 px-3 text-center">
                          <button onClick={() => toggleRetention(p)} className="transition-colors">
                            {p.enabled ? (
                              <ToggleRight size={18} className="text-os-success" />
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
                            <button onClick={() => deleteRetention(p.id)} className="p-1 rounded text-os-muted hover:text-os-danger transition-colors">
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
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs text-os-subtle">
              {abacPolicies.length} 条策略
            </p>
            <button
              onClick={openCreateAbac}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-2xs font-medium bg-os-accent text-white hover:bg-os-accent/90 transition-colors"
            >
              <Plus size={12} />
              新建 ABAC 策略
            </button>
          </div>

          {abacLoading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-24 bg-os-elevated rounded-lg animate-pulse" />
              ))}
            </div>
          ) : abacError && abacPolicies.length === 0 ? null : abacPolicies.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-24 text-os-subtle">
              <Key size={48} className="mb-4 opacity-30" />
              <p className="text-sm">尚未配置 ABAC 策略</p>
              <p className="text-2xs mt-1">创建基于属性的访问控制规则</p>
            </div>
          ) : (
            <div className="space-y-3">
              {abacPolicies.map((p) => (
                <div key={p.id} className="os-card p-4 rounded-lg border border-os-border/30 bg-os-surface hover:border-os-border/60 transition-colors">
                  <div className="mb-2 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex min-w-0 flex-wrap items-center gap-2">
                      <span className="break-words text-xs font-semibold text-os-text-high">{p.name}</span>
                      <span
                        className={cn(
                          "px-1.5 py-0.5 rounded text-2xs font-bold uppercase",
                          p.effect === "deny"
                            ? "bg-os-danger-soft text-os-danger"
                            : "bg-os-success-soft text-os-success"
                        )}
                      >
                        {EFFECT_LABELS[p.effect] || p.effect}
                      </span>
                      {!p.enabled && (
                        <span className="px-1.5 py-0.5 rounded text-2xs bg-os-elevated text-os-subtle">已停用</span>
                      )}
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <span className="text-2xs text-os-subtle">优先级：{p.priority}</span>
                      <button onClick={() => openEditAbac(p)} className="p-1 rounded text-os-subtle hover:text-os-text transition-colors">
                        <Edit3 size={12} />
                      </button>
                      <button onClick={() => deleteAbac(p.id)} className="p-1 rounded text-os-muted hover:text-os-danger transition-colors">
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </div>
                  {p.description && (
                    <p className="text-2xs text-os-subtle mb-2">{p.description}</p>
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
                  <h3 className="text-xs font-semibold text-os-text-high">{ROLE_LABELS[role.name] || role.name}</h3>
                </div>
                <p className="text-2xs text-os-subtle mb-3 leading-relaxed">{role.description}</p>
                <div>
                  <p className="text-2xs text-os-subtle tracking-wider mb-1.5">
                    权限（{role.permissions.length}）
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
              <h3 className="text-xs font-semibold text-os-text-high">自定义角色</h3>
              {roles.map((role) => (
                <div key={role.id} className="os-card p-4 rounded-lg border border-os-border/30 bg-os-surface">
                  <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                    <div className="flex min-w-0 flex-wrap items-center gap-2">
                      <Shield size={14} className="text-os-accent" />
                      <span className="text-xs font-semibold text-os-text-high">{role.name}</span>
                      {role.is_system && (
                        <span className="px-1.5 py-0.5 rounded text-2xs bg-os-accent/10 text-os-accent">系统角色</span>
                      )}
                    </div>
                    <span className="text-2xs text-os-subtle">{role.permissions.length} 项权限</span>
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
              <h3 className="text-xs font-semibold text-os-text-high">权限矩阵</h3>
              <p className="text-2xs text-os-subtle mt-0.5">角色与权限的对应关系</p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-os-subtle border-b border-os-border/30 bg-os-elevated/30">
                    <th className="text-left py-2 px-3 font-medium sticky left-0 bg-os-elevated/30 z-10">权限</th>
                    {DEFAULT_ROLES.map((r) => (
                      <th key={r.name} className="text-center py-2 px-3 font-medium whitespace-nowrap">{ROLE_LABELS[r.name] || r.name}</th>
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
                              <span className="inline-block w-2 h-2 rounded-full bg-os-success" />
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
                {editingRet ? "编辑数据留存策略" : "新建数据留存策略"}
              </h3>
              <button onClick={() => setShowRetModal(false)} className="text-os-muted hover:text-os-text transition-colors">
                <X size={16} />
              </button>
            </div>
            <div className="space-y-3">
              <input
                className="w-full h-9 px-3 bg-os-base border border-os-border rounded-md text-xs text-os-text-high placeholder:text-os-subtle focus:outline-none focus:border-os-accent transition-colors"
                placeholder="名称"
                value={retForm.name}
                onChange={(e) => setRetForm({ ...retForm, name: e.target.value })}
              />
              <select
                className="w-full h-9 px-3 bg-os-base border border-os-border rounded-md text-xs text-os-text-high focus:outline-none focus:border-os-accent transition-colors"
                value={retForm.resource_type}
                onChange={(e) => setRetForm({ ...retForm, resource_type: e.target.value })}
              >
                <option value="memory">记忆</option>
                <option value="audit_log">审计日志</option>
                <option value="notification">通知</option>
                <option value="import_job">导入任务</option>
              </select>
              <select
                className="w-full h-9 px-3 bg-os-base border border-os-border rounded-md text-xs text-os-text-high focus:outline-none focus:border-os-accent transition-colors"
                value={retForm.retention_period}
                onChange={(e) => setRetForm({ ...retForm, retention_period: e.target.value })}
              >
                <option value="30d">30 天</option>
                <option value="90d">90 天</option>
                <option value="180d">180 天</option>
                <option value="1y">1 年</option>
                <option value="3y">3 年</option>
                <option value="7y">7 年</option>
                <option value="forever">永久保留</option>
              </select>
              <select
                className="w-full h-9 px-3 bg-os-base border border-os-border rounded-md text-xs text-os-text-high focus:outline-none focus:border-os-accent transition-colors"
                value={retForm.archive_action}
                onChange={(e) => setRetForm({ ...retForm, archive_action: e.target.value })}
              >
                <option value="archive">归档</option>
                <option value="delete">删除</option>
                <option value="anonymize">匿名化</option>
              </select>
              <textarea
                className="w-full px-3 py-2 bg-os-base border border-os-border rounded-md text-xs text-os-text-high placeholder:text-os-subtle focus:outline-none focus:border-os-accent transition-colors resize-none"
                placeholder="描述（可选）"
                value={retForm.description}
                onChange={(e) => setRetForm({ ...retForm, description: e.target.value })}
                rows={2}
              />
              <div className="flex justify-end gap-2 pt-2">
                <button onClick={() => setShowRetModal(false)} className="px-3 py-1.5 rounded-md text-xs text-os-subtle hover:text-os-text transition-colors">
                  取消
                </button>
                <button
                  onClick={saveRetention}
                  disabled={!retForm.name.trim()}
                  className="px-3 py-1.5 rounded-md text-xs font-medium bg-os-accent text-white hover:bg-os-accent/90 transition-colors disabled:opacity-50"
                >
                  {editingRet ? "更新" : "创建"}
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
                {editingAbac ? "编辑 ABAC 策略" : "新建 ABAC 策略"}
              </h3>
              <button onClick={() => setShowAbacModal(false)} className="text-os-muted hover:text-os-text transition-colors">
                <X size={16} />
              </button>
            </div>
            <div className="space-y-3">
              <input
                className="w-full h-9 px-3 bg-os-base border border-os-border rounded-md text-xs text-os-text-high placeholder:text-os-subtle focus:outline-none focus:border-os-accent transition-colors"
                placeholder="名称"
                value={abacForm.name}
                onChange={(e) => setAbacForm({ ...abacForm, name: e.target.value })}
              />
              <select
                className="w-full h-9 px-3 bg-os-base border border-os-border rounded-md text-xs text-os-text-high focus:outline-none focus:border-os-accent transition-colors"
                value={abacForm.effect}
                onChange={(e) => setAbacForm({ ...abacForm, effect: e.target.value })}
              >
                <option value="deny">拒绝</option>
                <option value="allow">允许</option>
              </select>
              <input
                className="w-full h-9 px-3 bg-os-base border border-os-border rounded-md text-xs text-os-text-high placeholder:text-os-subtle focus:outline-none focus:border-os-accent transition-colors"
                type="number"
                placeholder="优先级（数值越小，优先级越高）"
                value={abacForm.priority}
                onChange={(e) => setAbacForm({ ...abacForm, priority: parseInt(e.target.value) || 100 })}
              />
              <textarea
                className="w-full px-3 py-2 bg-os-base border border-os-border rounded-md text-xs text-os-text-high placeholder:text-os-subtle focus:outline-none focus:border-os-accent transition-colors font-mono resize-none"
                placeholder='条件 JSON，例如 {"subject.org_id":{"eq":"org-1"}}'
                value={abacForm.conditionsJson}
                onChange={(e) => setAbacForm({ ...abacForm, conditionsJson: e.target.value })}
                rows={4}
              />
              <input
                className="w-full h-9 px-3 bg-os-base border border-os-border rounded-md text-xs text-os-text-high placeholder:text-os-subtle focus:outline-none focus:border-os-accent transition-colors"
                placeholder="描述（可选）"
                value={abacForm.description}
                onChange={(e) => setAbacForm({ ...abacForm, description: e.target.value })}
              />
              <div className="flex justify-end gap-2 pt-2">
                <button onClick={() => setShowAbacModal(false)} className="px-3 py-1.5 rounded-md text-xs text-os-subtle hover:text-os-text transition-colors">
                  取消
                </button>
                <button
                  onClick={saveAbac}
                  disabled={!abacForm.name.trim()}
                  className="px-3 py-1.5 rounded-md text-xs font-medium bg-os-accent text-white hover:bg-os-accent/90 transition-colors disabled:opacity-50"
                >
                  {editingAbac ? "更新" : "创建"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
