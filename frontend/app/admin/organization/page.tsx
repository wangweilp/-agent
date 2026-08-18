"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Building2,
  Plus,
  ChevronDown,
  ChevronRight,
  Trash2,
  Layers,
  Users,
  UserPlus,
  X,
  RefreshCw,
  Search,
} from "lucide-react";
import { OsButton } from "@/components/ui/os";
import { apiFetch } from "@/services/api";

// ── Types ──

interface Organization {
  id: string;
  name: string;
  industry: string;
  business_units: BusinessUnit[];
  created_at?: string;
}

interface BusinessUnit {
  id: string;
  name: string;
  org_id: string;
  departments: Department[];
}

interface Department {
  id: string;
  name: string;
  bu_id: string;
  members: Member[];
}

interface Member {
  user_id: string;
  name: string;
  email: string;
  position: string;
}

// ── Helpers ──


// ── Modal Component ──

interface OrganizationSummary {
  id: string;
  name: string;
  industry: string;
  created_at?: string;
}

interface OrgTreeNode {
  id: string;
  name: string;
  node_type: string;
  member_count: number;
  children: OrgTreeNode[];
}

function toOrganization(summary: OrganizationSummary, tree: OrgTreeNode | null): Organization {
  return {
    id: summary.id,
    name: summary.name,
    industry: summary.industry,
    created_at: summary.created_at,
    business_units: (tree?.children || []).map((bu) => ({
      id: bu.id,
      name: bu.name,
      org_id: summary.id,
      departments: (bu.children || []).map((dept) => ({
        id: dept.id,
        name: dept.name,
        bu_id: bu.id,
        members: [],
      })),
    })),
  };
}

function Modal({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: React.ReactNode }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-slate-950/20" onClick={onClose} />
      <div className="relative bg-os-surface border border-os-border rounded-lg shadow-os-lg w-full max-w-md mx-4 p-5 z-10 animate-fade-in">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-os-text-high">{title}</h3>
          <button
            type="button"
            onClick={onClose}
            className="rounded text-os-subtle transition-colors hover:text-os-text focus-visible:ring-2 focus-visible:ring-os-accent/25"
            aria-label="关闭弹窗"
            title="关闭"
          >
            <X size={16} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

// ── Page Component ──

export default function OrganizationPage() {
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedOrg, setExpandedOrg] = useState<string | null>(null);
  const [expandedBU, setExpandedBU] = useState<string | null>(null);

  // Create org modal
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newOrgName, setNewOrgName] = useState("");
  const [newOrgIndustry, setNewOrgIndustry] = useState("");
  const [creating, setCreating] = useState(false);

  // Create BU modal
  const [showCreateBUModal, setShowCreateBUModal] = useState(false);
  const [newBUName, setNewBUName] = useState("");
  const [targetOrgId, setTargetOrgId] = useState<string | null>(null);
  const [creatingBU, setCreatingBU] = useState(false);

  // Create Dept modal
  const [showCreateDeptModal, setShowCreateDeptModal] = useState(false);
  const [newDeptName, setNewDeptName] = useState("");
  const [targetBUId, setTargetBUId] = useState<string | null>(null);
  const [creatingDept, setCreatingDept] = useState(false);

  // Assign member modal
  const [showAssignModal, setShowAssignModal] = useState(false);
  const [assignUserId, setAssignUserId] = useState("");
  const [assignName, setAssignName] = useState("");
  const [assignEmail, setAssignEmail] = useState("");
  const [assignPosition, setAssignPosition] = useState("");
  const [targetDeptId, setTargetDeptId] = useState<string | null>(null);
  const [assigning, setAssigning] = useState(false);

  // Search
  const [search, setSearch] = useState("");

  const fetchOrgs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<OrganizationSummary[]>("/api/org");
      const summaries = Array.isArray(data) ? data : [];
      const orgsWithTrees = await Promise.all(
        summaries.map(async (summary) => {
          const tree = await apiFetch<OrgTreeNode>(`/api/org/${summary.id}/tree`);
          return toOrganization(summary, tree);
        })
      );
      setOrgs(orgsWithTrees);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "加载组织失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchOrgs();
  }, [fetchOrgs]);

  const hasSearch = search.length > 0;
  const filteredOrgs = hasSearch
    ? orgs.filter((o) => o.name.toLowerCase().includes(search.toLowerCase()))
    : orgs;

  // ── Handlers ──

  const handleCreateOrg = async () => {
    if (!newOrgName.trim()) return;
    setCreating(true);
    try {
      await apiFetch("/api/org", {
        method: "POST",
        body: JSON.stringify({ name: newOrgName.trim(), industry: newOrgIndustry.trim() }),
      });
      setNewOrgName("");
      setNewOrgIndustry("");
      setShowCreateModal(false);
      await fetchOrgs();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "创建组织失败");
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteOrg = async (orgId: string) => {
    if (!confirm("确定删除此组织及其全部数据吗？此操作无法撤销。")) return;
    try {
      await apiFetch(`/api/org/${orgId}`, { method: "DELETE" });
      await fetchOrgs();
      if (expandedOrg === orgId) setExpandedOrg(null);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "删除组织失败");
    }
  };

  const handleCreateBU = async () => {
    if (!newBUName.trim() || !targetOrgId) return;
    setCreatingBU(true);
    try {
      await apiFetch(`/api/org/${targetOrgId}/business-units`, {
        method: "POST",
        body: JSON.stringify({ name: newBUName.trim() }),
      });
      setNewBUName("");
      setShowCreateBUModal(false);
      await fetchOrgs();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "创建业务单元失败");
    } finally {
      setCreatingBU(false);
    }
  };

  const handleDeleteBU = async (orgId: string, buId: string) => {
    if (!confirm("确定删除此业务单元及其全部部门吗？")) return;
    try {
      await apiFetch(`/api/org/${orgId}/business-units/${buId}`, { method: "DELETE" });
      await fetchOrgs();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "删除业务单元失败");
    }
  };

  const handleCreateDept = async () => {
    if (!newDeptName.trim() || !targetBUId || !targetOrgId) return;
    setCreatingDept(true);
    try {
      await apiFetch(`/api/org/${targetOrgId}/departments`, {
        method: "POST",
        body: JSON.stringify({ name: newDeptName.trim(), business_unit_id: targetBUId }),
      });
      setNewDeptName("");
      setShowCreateDeptModal(false);
      await fetchOrgs();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "创建部门失败");
    } finally {
      setCreatingDept(false);
    }
  };

  const handleDeleteDept = async (orgId: string, deptId: string) => {
    if (!confirm("确定删除此部门并移除全部成员分配吗？")) return;
    try {
      await apiFetch(`/api/org/${orgId}/departments/${deptId}`, { method: "DELETE" });
      await fetchOrgs();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "删除部门失败");
    }
  };

  const handleAssignMember = async () => {
    if (!assignUserId.trim() || !targetDeptId || !targetOrgId) return;
    setAssigning(true);
    try {
      await apiFetch(`/api/org/${targetOrgId}/positions`, {
        method: "POST",
        body: JSON.stringify({
          user_id: assignUserId.trim(),
          department_id: targetDeptId,
          title: assignPosition.trim() || "Member",
          is_manager: false,
        }),
      });
      setAssignUserId("");
      setAssignName("");
      setAssignEmail("");
      setAssignPosition("");
      setShowAssignModal(false);
      await fetchOrgs();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "分配成员失败");
    } finally {
      setAssigning(false);
    }
  };

  const handleRemoveMember = async (deptId: string, userId: string) => {
    if (!confirm("确定从此部门移除该成员吗？")) return;
    try {
      await apiFetch(`/api/org/dept/${deptId}/members/${userId}`, { method: "DELETE" });
      await fetchOrgs();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "移除成员失败");
    }
  };

  // ── Render ──

  return (
    <div className="mx-auto max-w-[1440px] space-y-4 p-4 md:p-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 sm:items-center">
        <div>
          <h1 className="text-lg font-semibold text-os-text-high tracking-tight">
            组织中心
          </h1>
          <p className="text-xs text-os-subtle mt-0.5">
            {orgs.length} 个组织
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <OsButton
            type="button"
            variant="ghost"
            size="icon"
            onClick={fetchOrgs}
            disabled={loading}
            className="text-os-subtle disabled:bg-transparent disabled:text-os-subtle"
            aria-label="刷新组织列表"
            title="刷新"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </OsButton>
          <OsButton
            type="button"
            variant="primary"
            size="md"
            onClick={() => setShowCreateModal(true)}
            className="text-xs"
          >
            <Plus size={14} />
            新建组织
          </OsButton>
        </div>
      </div>

      {/* Search */}
      <div className="relative">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-os-muted" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="搜索组织..."
          aria-label="搜索组织"
          className="h-9 w-full max-w-sm rounded-md border border-os-border bg-os-surface pl-9 pr-4 text-xs text-os-text-high transition-colors placeholder:text-os-subtle focus:border-os-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-os-accent/20"
        />
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-os-danger/20 bg-os-danger-soft p-3 text-xs text-os-danger">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-20 bg-os-elevated rounded-lg animate-pulse" />
          ))}
        </div>
      )}

      {/* Empty */}
      {!loading && !error && filteredOrgs.length === 0 && (
        <div className="flex min-h-[320px] flex-col items-center justify-center px-4 py-12 text-center">
          <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-os-surface-muted text-os-subtle">
            <Building2 size={30} aria-hidden="true" />
          </div>
          <div className="max-w-sm">
            <h2 className="text-sm font-semibold text-os-text-high">
              {hasSearch ? "未找到匹配的组织" : "暂无组织"}
            </h2>
            <p className="mt-2 text-sm leading-6 text-os-subtle">
              {hasSearch
                ? "请尝试调整搜索关键词"
                : "创建您的第一个组织，开始配置团队与智能体资源"}
            </p>
          </div>
          {hasSearch ? (
            <OsButton
              type="button"
              variant="secondary"
              size="md"
              onClick={() => setSearch("")}
              className="mt-5 text-xs"
            >
              清除搜索
            </OsButton>
          ) : (
            <OsButton
              type="button"
              variant="primary"
              size="md"
              onClick={() => setShowCreateModal(true)}
              className="mt-5 text-xs"
            >
              <Plus size={14} />
              新建组织
            </OsButton>
          )}
        </div>
      )}

      {/* Org List */}
      <div className="space-y-3">
        {filteredOrgs.map((org) => (
          <div key={org.id} className="os-card overflow-hidden rounded-lg border border-os-border bg-os-surface">
            {/* Org Header */}
            <div
              className="flex items-center justify-between gap-3 p-4 cursor-pointer hover:bg-os-elevated/30 transition-colors"
              onClick={() => setExpandedOrg(expandedOrg === org.id ? null : org.id)}
            >
              <div className="flex min-w-0 flex-1 items-center gap-3">
                {expandedOrg === org.id ? <ChevronDown size={16} className="shrink-0 text-os-subtle" /> : <ChevronRight size={16} className="shrink-0 text-os-subtle" />}
                <Building2 size={16} className="shrink-0 text-os-accent" />
                <div className="min-w-0">
                  <p className="break-words text-sm font-medium text-os-text-high">{org.name}</p>
                  <p className="mt-0.5 break-words text-xs leading-5 text-os-subtle">
                    {org.industry || "未设置行业"} &middot; {org.business_units?.length || 0} 个业务单元
                  </p>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-1" onClick={(e) => e.stopPropagation()}>
                <button
                  type="button"
                  onClick={() => {
                    setTargetOrgId(org.id);
                    setShowCreateBUModal(true);
                  }}
                  className="p-1.5 rounded text-2xs text-os-subtle hover:text-os-text hover:bg-os-elevated transition-colors"
                  title="添加业务单元"
                >
                  <Plus size={14} />
                </button>
                <button
                  type="button"
                  onClick={() => handleDeleteOrg(org.id)}
                  className="p-1.5 rounded text-2xs text-os-subtle hover:text-os-danger hover:bg-os-danger-soft transition-colors"
                  title="删除组织"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>

            {/* Org Body — Expand */}
            {expandedOrg === org.id && (
              <div className="border-t border-os-border/60 bg-os-base/50">
                {org.business_units && org.business_units.length > 0 ? (
                  <div className="divide-y divide-os-border/60">
                    {org.business_units.map((bu) => (
                      <div key={bu.id} className="animate-slide-up">
                        {/* BU Header */}
                        <div
                          className="flex items-center justify-between gap-3 px-4 py-3 cursor-pointer hover:bg-os-elevated/20 transition-colors sm:px-6"
                          onClick={() => setExpandedBU(expandedBU === bu.id ? null : bu.id)}
                        >
                          <div className="flex min-w-0 flex-1 items-center gap-2.5">
                            {expandedBU === bu.id ? <ChevronDown size={14} className="shrink-0 text-os-subtle" /> : <ChevronRight size={14} className="shrink-0 text-os-subtle" />}
                            <Layers size={14} className="shrink-0 text-indigo-600" />
                            <span className="min-w-0 flex-1 break-words text-xs font-medium text-os-text-high">{bu.name}</span>
                            <span className="shrink-0 whitespace-nowrap text-xs text-os-subtle">
                              {bu.departments?.length || 0} 个部门
                            </span>
                          </div>
                          <div className="flex shrink-0 items-center gap-1" onClick={(e) => e.stopPropagation()}>
                            <button
                              type="button"
                              onClick={() => {
                                setTargetOrgId(org.id);
                                setTargetBUId(bu.id);
                                setShowCreateDeptModal(true);
                              }}
                              className="p-1 rounded text-2xs text-os-subtle hover:text-os-text hover:bg-os-elevated transition-colors"
                              title="添加部门"
                            >
                              <Plus size={13} />
                            </button>
                            <button
                              type="button"
                              onClick={() => handleDeleteBU(org.id, bu.id)}
                              className="p-1 rounded text-2xs text-os-subtle hover:text-os-danger hover:bg-os-danger-soft transition-colors"
                              title="删除业务单元"
                            >
                              <Trash2 size={13} />
                            </button>
                          </div>
                        </div>

                        {/* BU Body — Departments */}
                        {expandedBU === bu.id && (
                          <div className="border-t border-os-border/60">
                            {bu.departments && bu.departments.length > 0 ? (
                              bu.departments.map((dept) => (
                                <div key={dept.id} className="border-b border-os-border/50 px-4 py-3 last:border-0 hover:bg-os-elevated/20 transition-colors sm:px-8">
                                  <div className="mb-2 flex items-start justify-between gap-3 sm:items-center">
                                    <div className="flex min-w-0 flex-1 items-center gap-2">
                                      <Users size={13} className="shrink-0 text-emerald-600" />
                                      <span className="min-w-0 flex-1 break-words text-xs text-os-text-high">{dept.name}</span>
                                      <span className="shrink-0 whitespace-nowrap text-xs text-os-subtle">
                                        {dept.members?.length || 0} 名成员
                                      </span>
                                    </div>
                                    <div className="flex shrink-0 items-center gap-1">
                                      <button
                                        type="button"
                                        onClick={() => {
                                          setTargetOrgId(org.id);
                                          setTargetDeptId(dept.id);
                                          setShowAssignModal(true);
                                        }}
                                        className="p-1 rounded text-2xs text-os-subtle hover:text-os-text hover:bg-os-elevated transition-colors"
                                        title="分配成员"
                                      >
                                        <UserPlus size={13} />
                                      </button>
                                      <button
                                        type="button"
                                        onClick={() => handleDeleteDept(org.id, dept.id)}
                                        className="p-1 rounded text-2xs text-os-subtle hover:text-os-danger hover:bg-os-danger-soft transition-colors"
                                        title="删除部门"
                                      >
                                        <Trash2 size={13} />
                                      </button>
                                    </div>
                                  </div>

                                  {/* Members */}
                                  {dept.members && dept.members.length > 0 && (
                                    <div className="space-y-1 mt-2">
                                      {dept.members.map((m) => (
                                        <div key={m.user_id} className="flex flex-col items-start gap-2 border-l-2 border-os-border/60 py-2 pl-4 text-xs sm:ml-2 sm:flex-row sm:items-center sm:justify-between sm:pl-6">
                                          <div className="min-w-0 max-w-full">
                                            <span className="block break-words text-os-text sm:inline">{m.name}</span>
                                            <span className="mt-0.5 block break-all text-os-subtle sm:ml-2 sm:mt-0 sm:inline">{m.email}</span>
                                          </div>
                                          <div className="flex max-w-full flex-wrap items-center gap-2">
                                            <span className="max-w-full break-words rounded bg-os-elevated px-1.5 py-0.5 text-2xs text-os-subtle">
                                              {m.position || "成员"}
                                            </span>
                                            <button
                                              type="button"
                                              onClick={() => handleRemoveMember(dept.id, m.user_id)}
                                              className="shrink-0 rounded text-os-subtle transition-colors hover:bg-os-danger-soft hover:text-os-danger focus-visible:ring-2 focus-visible:ring-os-accent/25"
                                              aria-label={`从部门移除 ${m.name || "该成员"}`}
                                              title="移除成员"
                                            >
                                              <X size={12} />
                                            </button>
                                          </div>
                                        </div>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              ))
                            ) : (
                              <div className="px-4 py-6 text-center text-xs text-os-subtle sm:px-8">
                                暂无部门，请添加部门以组织成员。
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="p-6 text-center text-xs text-os-subtle">
                    暂无业务单元，请添加业务单元以完善组织结构。
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* ── Modals ── */}

      {/* Create Org Modal */}
      <Modal open={showCreateModal} onClose={() => setShowCreateModal(false)} title="创建组织">
        <div className="space-y-3">
          <div>
            <label className="text-2xs text-os-subtle block mb-1">组织名称</label>
            <input
              value={newOrgName}
              onChange={(e) => setNewOrgName(e.target.value)}
              placeholder="例如：知维科技"
              className="h-9 w-full rounded-md border border-os-border bg-os-base px-3 text-xs text-os-text-high transition-colors placeholder:text-os-subtle focus:border-os-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-os-accent/20"
            />
          </div>
          <div>
            <label className="text-2xs text-os-subtle block mb-1">所属行业</label>
            <input
              value={newOrgIndustry}
              onChange={(e) => setNewOrgIndustry(e.target.value)}
              placeholder="例如：科技"
              className="h-9 w-full rounded-md border border-os-border bg-os-base px-3 text-xs text-os-text-high transition-colors placeholder:text-os-subtle focus:border-os-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-os-accent/20"
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={() => setShowCreateModal(false)} className="px-3 py-1.5 rounded-md text-xs text-os-subtle hover:text-os-text transition-colors">
              取消
            </button>
            <button
              type="button"
              onClick={handleCreateOrg}
              disabled={creating || !newOrgName.trim()}
              className="rounded-md bg-os-accent px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-os-accent/90 disabled:cursor-not-allowed disabled:bg-os-surface-muted disabled:text-os-subtle"
            >
              {creating ? "创建中..." : "创建"}
            </button>
          </div>
        </div>
      </Modal>

      {/* Create BU Modal */}
      <Modal open={showCreateBUModal} onClose={() => setShowCreateBUModal(false)} title="添加业务单元">
        <div className="space-y-3">
          <div>
            <label className="text-2xs text-os-subtle block mb-1">业务单元名称</label>
            <input
              value={newBUName}
              onChange={(e) => setNewBUName(e.target.value)}
              placeholder="例如：研发中心"
              className="h-9 w-full rounded-md border border-os-border bg-os-base px-3 text-xs text-os-text-high transition-colors placeholder:text-os-subtle focus:border-os-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-os-accent/20"
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={() => setShowCreateBUModal(false)} className="px-3 py-1.5 rounded-md text-xs text-os-subtle hover:text-os-text transition-colors">
              取消
            </button>
            <button
              type="button"
              onClick={handleCreateBU}
              disabled={creatingBU || !newBUName.trim()}
              className="rounded-md bg-os-accent px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-os-accent/90 disabled:cursor-not-allowed disabled:bg-os-surface-muted disabled:text-os-subtle"
            >
              {creatingBU ? "添加中..." : "添加业务单元"}
            </button>
          </div>
        </div>
      </Modal>

      {/* Create Dept Modal */}
      <Modal open={showCreateDeptModal} onClose={() => setShowCreateDeptModal(false)} title="添加部门">
        <div className="space-y-3">
          <div>
            <label className="text-2xs text-os-subtle block mb-1">部门名称</label>
            <input
              value={newDeptName}
              onChange={(e) => setNewDeptName(e.target.value)}
              placeholder="例如：前端团队"
              className="h-9 w-full rounded-md border border-os-border bg-os-base px-3 text-xs text-os-text-high transition-colors placeholder:text-os-subtle focus:border-os-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-os-accent/20"
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={() => setShowCreateDeptModal(false)} className="px-3 py-1.5 rounded-md text-xs text-os-subtle hover:text-os-text transition-colors">
              取消
            </button>
            <button
              type="button"
              onClick={handleCreateDept}
              disabled={creatingDept || !newDeptName.trim()}
              className="rounded-md bg-os-accent px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-os-accent/90 disabled:cursor-not-allowed disabled:bg-os-surface-muted disabled:text-os-subtle"
            >
              {creatingDept ? "添加中..." : "添加部门"}
            </button>
          </div>
        </div>
      </Modal>

      {/* Assign Member Modal */}
      <Modal open={showAssignModal} onClose={() => setShowAssignModal(false)} title="分配成员">
        <div className="space-y-3">
          <div>
            <label className="text-2xs text-os-subtle block mb-1">用户 ID</label>
            <input
              value={assignUserId}
              onChange={(e) => setAssignUserId(e.target.value)}
              placeholder="例如：user-123"
              className="h-9 w-full rounded-md border border-os-border bg-os-base px-3 text-xs text-os-text-high transition-colors placeholder:text-os-subtle focus:border-os-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-os-accent/20"
            />
          </div>
          <div>
            <label className="text-2xs text-os-subtle block mb-1">姓名</label>
            <input
              value={assignName}
              onChange={(e) => setAssignName(e.target.value)}
              placeholder="例如：张伟"
              className="h-9 w-full rounded-md border border-os-border bg-os-base px-3 text-xs text-os-text-high transition-colors placeholder:text-os-subtle focus:border-os-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-os-accent/20"
            />
          </div>
          <div>
            <label className="text-2xs text-os-subtle block mb-1">邮箱</label>
            <input
              value={assignEmail}
              onChange={(e) => setAssignEmail(e.target.value)}
              placeholder="例如：zhang@example.com"
              className="h-9 w-full rounded-md border border-os-border bg-os-base px-3 text-xs text-os-text-high transition-colors placeholder:text-os-subtle focus:border-os-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-os-accent/20"
            />
          </div>
          <div>
            <label className="text-2xs text-os-subtle block mb-1">职位</label>
            <input
              value={assignPosition}
              onChange={(e) => setAssignPosition(e.target.value)}
              placeholder="例如：高级工程师"
              className="h-9 w-full rounded-md border border-os-border bg-os-base px-3 text-xs text-os-text-high transition-colors placeholder:text-os-subtle focus:border-os-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-os-accent/20"
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={() => setShowAssignModal(false)} className="px-3 py-1.5 rounded-md text-xs text-os-subtle hover:text-os-text transition-colors">
              取消
            </button>
            <button
              type="button"
              onClick={handleAssignMember}
              disabled={assigning || !assignUserId.trim()}
              className="rounded-md bg-os-accent px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-os-accent/90 disabled:cursor-not-allowed disabled:bg-os-surface-muted disabled:text-os-subtle"
            >
              {assigning ? "分配中..." : "分配"}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
