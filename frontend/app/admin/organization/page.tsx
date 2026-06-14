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
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative bg-os-surface border border-os-border rounded-lg shadow-os-lg w-full max-w-md mx-4 p-5 z-10 animate-fade-in">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-os-text-high">{title}</h3>
          <button onClick={onClose} className="text-os-muted hover:text-os-text transition-colors">
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
      setError(err instanceof Error ? err.message : "Failed to load organizations");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchOrgs();
  }, [fetchOrgs]);

  const filteredOrgs = search
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
      alert(err instanceof Error ? err.message : "Failed to create organization");
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteOrg = async (orgId: string) => {
    if (!confirm("Delete this organization and all its data? This cannot be undone.")) return;
    try {
      await apiFetch(`/api/org/${orgId}`, { method: "DELETE" });
      await fetchOrgs();
      if (expandedOrg === orgId) setExpandedOrg(null);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to delete organization");
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
      alert(err instanceof Error ? err.message : "Failed to create business unit");
    } finally {
      setCreatingBU(false);
    }
  };

  const handleDeleteBU = async (orgId: string, buId: string) => {
    if (!confirm("Delete this business unit and all its departments?")) return;
    try {
      await apiFetch(`/api/org/${orgId}/business-units/${buId}`, { method: "DELETE" });
      await fetchOrgs();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to delete business unit");
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
      alert(err instanceof Error ? err.message : "Failed to create department");
    } finally {
      setCreatingDept(false);
    }
  };

  const handleDeleteDept = async (orgId: string, deptId: string) => {
    if (!confirm("Delete this department and remove all member assignments?")) return;
    try {
      await apiFetch(`/api/org/${orgId}/departments/${deptId}`, { method: "DELETE" });
      await fetchOrgs();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to delete department");
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
      alert(err instanceof Error ? err.message : "Failed to assign member");
    } finally {
      setAssigning(false);
    }
  };

  const handleRemoveMember = async (deptId: string, userId: string) => {
    if (!confirm("Remove this member from the department?")) return;
    try {
      await apiFetch(`/api/org/dept/${deptId}/members/${userId}`, { method: "DELETE" });
      await fetchOrgs();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to remove member");
    }
  };

  // ── Render ──

  return (
    <div className="p-6 space-y-4 max-w-[1440px] mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-os-text-high tracking-tight">
            组织中心
          </h1>
          <p className="text-xs text-os-subtle mt-0.5">
            {orgs.length} organization{orgs.length !== 1 ? "s" : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={fetchOrgs}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-2xs text-os-subtle hover:text-os-text hover:bg-os-elevated transition-colors"
          >
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-2xs font-medium bg-os-accent text-white hover:bg-os-accent/90 transition-colors"
          >
            <Plus size={12} />
            New Organization
          </button>
        </div>
      </div>

      {/* Search */}
      <div className="relative">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-os-muted" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search organizations..."
          className="w-full max-w-sm h-9 pl-9 pr-4 bg-os-surface border border-os-border rounded-md text-xs text-os-text-high placeholder:text-os-muted focus:outline-none focus:border-os-accent transition-colors"
        />
      </div>

      {/* Error */}
      {error && (
        <div className="os-card p-3 rounded-lg border border-red-400/20 bg-red-400/5 text-red-400 text-xs">
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
      {!loading && filteredOrgs.length === 0 && (
        <div className="flex flex-col items-center justify-center py-24 text-os-muted">
          <Building2 size={48} className="mb-4 opacity-30" />
          <p className="text-sm">No organizations found</p>
          <p className="text-2xs mt-1">
            {search ? "Try adjusting your search" : "Create your first organization to get started"}
          </p>
        </div>
      )}

      {/* Org List */}
      <div className="space-y-3">
        {filteredOrgs.map((org) => (
          <div key={org.id} className="os-card rounded-lg border border-os-border/30 bg-os-surface overflow-hidden">
            {/* Org Header */}
            <div
              className="flex items-center justify-between p-4 cursor-pointer hover:bg-os-elevated/30 transition-colors"
              onClick={() => setExpandedOrg(expandedOrg === org.id ? null : org.id)}
            >
              <div className="flex items-center gap-3">
                {expandedOrg === org.id ? <ChevronDown size={16} className="text-os-subtle" /> : <ChevronRight size={16} className="text-os-subtle" />}
                <Building2 size={16} className="text-os-accent" />
                <div>
                  <p className="text-sm font-medium text-os-text-high">{org.name}</p>
                  <p className="text-2xs text-os-muted">{org.industry || "No industry"} &middot; {org.business_units?.length || 0} BU{org.business_units?.length !== 1 ? "s" : ""}</p>
                </div>
              </div>
              <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                <button
                  onClick={() => {
                    setTargetOrgId(org.id);
                    setShowCreateBUModal(true);
                  }}
                  className="p-1.5 rounded text-2xs text-os-subtle hover:text-os-text hover:bg-os-elevated transition-colors"
                  title="Add Business Unit"
                >
                  <Plus size={14} />
                </button>
                <button
                  onClick={() => handleDeleteOrg(org.id)}
                  className="p-1.5 rounded text-2xs text-os-muted hover:text-red-400 hover:bg-red-400/10 transition-colors"
                  title="Delete Organization"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>

            {/* Org Body — Expand */}
            {expandedOrg === org.id && (
              <div className="border-t border-os-border/30 bg-os-base/50">
                {org.business_units && org.business_units.length > 0 ? (
                  <div className="divide-y divide-os-border/20">
                    {org.business_units.map((bu) => (
                      <div key={bu.id} className="animate-slide-up">
                        {/* BU Header */}
                        <div
                          className="flex items-center justify-between px-6 py-3 cursor-pointer hover:bg-os-elevated/20 transition-colors"
                          onClick={() => setExpandedBU(expandedBU === bu.id ? null : bu.id)}
                        >
                          <div className="flex items-center gap-2.5">
                            {expandedBU === bu.id ? <ChevronDown size={14} className="text-os-subtle" /> : <ChevronRight size={14} className="text-os-subtle" />}
                            <Layers size={14} className="text-indigo-400" />
                            <span className="text-xs font-medium text-os-text-high">{bu.name}</span>
                            <span className="text-2xs text-os-muted">
                              {bu.departments?.length || 0} dept{bu.departments?.length !== 1 ? "s" : ""}
                            </span>
                          </div>
                          <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                            <button
                              onClick={() => {
                                setTargetOrgId(org.id);
                                setTargetBUId(bu.id);
                                setShowCreateDeptModal(true);
                              }}
                              className="p-1 rounded text-2xs text-os-subtle hover:text-os-text hover:bg-os-elevated transition-colors"
                              title="Add Department"
                            >
                              <Plus size={13} />
                            </button>
                            <button
                              onClick={() => handleDeleteBU(org.id, bu.id)}
                              className="p-1 rounded text-2xs text-os-muted hover:text-red-400 hover:bg-red-400/10 transition-colors"
                              title="Delete Business Unit"
                            >
                              <Trash2 size={13} />
                            </button>
                          </div>
                        </div>

                        {/* BU Body — Departments */}
                        {expandedBU === bu.id && (
                          <div className="border-t border-os-border/20">
                            {bu.departments && bu.departments.length > 0 ? (
                              bu.departments.map((dept) => (
                                <div key={dept.id} className="px-8 py-3 border-b border-os-border/10 last:border-0 hover:bg-os-elevated/20 transition-colors">
                                  <div className="flex items-center justify-between mb-2">
                                    <div className="flex items-center gap-2">
                                      <Users size={13} className="text-emerald-400" />
                                      <span className="text-xs text-os-text-high">{dept.name}</span>
                                      <span className="text-2xs text-os-muted">
                                        {dept.members?.length || 0} member{dept.members?.length !== 1 ? "s" : ""}
                                      </span>
                                    </div>
                                    <div className="flex items-center gap-1">
                                      <button
                                        onClick={() => {
                                          setTargetOrgId(org.id);
                                          setTargetDeptId(dept.id);
                                          setShowAssignModal(true);
                                        }}
                                        className="p-1 rounded text-2xs text-os-subtle hover:text-os-text hover:bg-os-elevated transition-colors"
                                        title="Assign Member"
                                      >
                                        <UserPlus size={13} />
                                      </button>
                                      <button
                                        onClick={() => handleDeleteDept(org.id, dept.id)}
                                        className="p-1 rounded text-2xs text-os-muted hover:text-red-400 hover:bg-red-400/10 transition-colors"
                                        title="Delete Department"
                                      >
                                        <Trash2 size={13} />
                                      </button>
                                    </div>
                                  </div>

                                  {/* Members */}
                                  {dept.members && dept.members.length > 0 && (
                                    <div className="space-y-1 mt-2">
                                      {dept.members.map((m) => (
                                        <div key={m.user_id} className="flex items-center justify-between pl-6 py-1 text-xs border-l-2 border-os-border/30 ml-2">
                                          <div>
                                            <span className="text-os-text">{m.name}</span>
                                            <span className="text-os-muted ml-2">{m.email}</span>
                                          </div>
                                          <div className="flex items-center gap-2">
                                            <span className="text-2xs text-os-subtle bg-os-elevated px-1.5 py-0.5 rounded">
                                              {m.position || "Member"}
                                            </span>
                                            <button
                                              onClick={() => handleRemoveMember(dept.id, m.user_id)}
                                              className="text-os-muted hover:text-red-400 transition-colors"
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
                              <div className="px-8 py-6 text-center text-2xs text-os-muted">
                                No departments yet. Add one to organize members.
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="p-6 text-center text-xs text-os-muted">
                    No business units yet. Add a BU to structure this organization.
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* ── Modals ── */}

      {/* Create Org Modal */}
      <Modal open={showCreateModal} onClose={() => setShowCreateModal(false)} title="Create Organization">
        <div className="space-y-3">
          <div>
            <label className="text-2xs text-os-subtle block mb-1">Name</label>
            <input
              value={newOrgName}
              onChange={(e) => setNewOrgName(e.target.value)}
              placeholder="e.g. Acme Corp"
              className="w-full h-9 px-3 bg-os-base border border-os-border rounded-md text-xs text-os-text-high placeholder:text-os-muted focus:outline-none focus:border-os-accent transition-colors"
            />
          </div>
          <div>
            <label className="text-2xs text-os-subtle block mb-1">Industry</label>
            <input
              value={newOrgIndustry}
              onChange={(e) => setNewOrgIndustry(e.target.value)}
              placeholder="e.g. Technology"
              className="w-full h-9 px-3 bg-os-base border border-os-border rounded-md text-xs text-os-text-high placeholder:text-os-muted focus:outline-none focus:border-os-accent transition-colors"
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button onClick={() => setShowCreateModal(false)} className="px-3 py-1.5 rounded-md text-xs text-os-subtle hover:text-os-text transition-colors">
              Cancel
            </button>
            <button
              onClick={handleCreateOrg}
              disabled={creating || !newOrgName.trim()}
              className="px-3 py-1.5 rounded-md text-xs font-medium bg-os-accent text-white hover:bg-os-accent/90 transition-colors disabled:opacity-50"
            >
              {creating ? "Creating..." : "Create"}
            </button>
          </div>
        </div>
      </Modal>

      {/* Create BU Modal */}
      <Modal open={showCreateBUModal} onClose={() => setShowCreateBUModal(false)} title="Add Business Unit">
        <div className="space-y-3">
          <div>
            <label className="text-2xs text-os-subtle block mb-1">Business Unit Name</label>
            <input
              value={newBUName}
              onChange={(e) => setNewBUName(e.target.value)}
              placeholder="e.g. Engineering"
              className="w-full h-9 px-3 bg-os-base border border-os-border rounded-md text-xs text-os-text-high placeholder:text-os-muted focus:outline-none focus:border-os-accent transition-colors"
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button onClick={() => setShowCreateBUModal(false)} className="px-3 py-1.5 rounded-md text-xs text-os-subtle hover:text-os-text transition-colors">
              Cancel
            </button>
            <button
              onClick={handleCreateBU}
              disabled={creatingBU || !newBUName.trim()}
              className="px-3 py-1.5 rounded-md text-xs font-medium bg-os-accent text-white hover:bg-os-accent/90 transition-colors disabled:opacity-50"
            >
              {creatingBU ? "Adding..." : "Add BU"}
            </button>
          </div>
        </div>
      </Modal>

      {/* Create Dept Modal */}
      <Modal open={showCreateDeptModal} onClose={() => setShowCreateDeptModal(false)} title="Add Department">
        <div className="space-y-3">
          <div>
            <label className="text-2xs text-os-subtle block mb-1">Department Name</label>
            <input
              value={newDeptName}
              onChange={(e) => setNewDeptName(e.target.value)}
              placeholder="e.g. Frontend Team"
              className="w-full h-9 px-3 bg-os-base border border-os-border rounded-md text-xs text-os-text-high placeholder:text-os-muted focus:outline-none focus:border-os-accent transition-colors"
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button onClick={() => setShowCreateDeptModal(false)} className="px-3 py-1.5 rounded-md text-xs text-os-subtle hover:text-os-text transition-colors">
              Cancel
            </button>
            <button
              onClick={handleCreateDept}
              disabled={creatingDept || !newDeptName.trim()}
              className="px-3 py-1.5 rounded-md text-xs font-medium bg-os-accent text-white hover:bg-os-accent/90 transition-colors disabled:opacity-50"
            >
              {creatingDept ? "Adding..." : "Add Department"}
            </button>
          </div>
        </div>
      </Modal>

      {/* Assign Member Modal */}
      <Modal open={showAssignModal} onClose={() => setShowAssignModal(false)} title="Assign Member">
        <div className="space-y-3">
          <div>
            <label className="text-2xs text-os-subtle block mb-1">User ID</label>
            <input
              value={assignUserId}
              onChange={(e) => setAssignUserId(e.target.value)}
              placeholder="e.g. user-123"
              className="w-full h-9 px-3 bg-os-base border border-os-border rounded-md text-xs text-os-text-high placeholder:text-os-muted focus:outline-none focus:border-os-accent transition-colors"
            />
          </div>
          <div>
            <label className="text-2xs text-os-subtle block mb-1">Name</label>
            <input
              value={assignName}
              onChange={(e) => setAssignName(e.target.value)}
              placeholder="e.g. Zhang Wei"
              className="w-full h-9 px-3 bg-os-base border border-os-border rounded-md text-xs text-os-text-high placeholder:text-os-muted focus:outline-none focus:border-os-accent transition-colors"
            />
          </div>
          <div>
            <label className="text-2xs text-os-subtle block mb-1">Email</label>
            <input
              value={assignEmail}
              onChange={(e) => setAssignEmail(e.target.value)}
              placeholder="e.g. zhang@example.com"
              className="w-full h-9 px-3 bg-os-base border border-os-border rounded-md text-xs text-os-text-high placeholder:text-os-muted focus:outline-none focus:border-os-accent transition-colors"
            />
          </div>
          <div>
            <label className="text-2xs text-os-subtle block mb-1">Position</label>
            <input
              value={assignPosition}
              onChange={(e) => setAssignPosition(e.target.value)}
              placeholder="e.g. Senior Engineer"
              className="w-full h-9 px-3 bg-os-base border border-os-border rounded-md text-xs text-os-text-high placeholder:text-os-muted focus:outline-none focus:border-os-accent transition-colors"
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button onClick={() => setShowAssignModal(false)} className="px-3 py-1.5 rounded-md text-xs text-os-subtle hover:text-os-text transition-colors">
              Cancel
            </button>
            <button
              onClick={handleAssignMember}
              disabled={assigning || !assignUserId.trim()}
              className="px-3 py-1.5 rounded-md text-xs font-medium bg-os-accent text-white hover:bg-os-accent/90 transition-colors disabled:opacity-50"
            >
              {assigning ? "Assigning..." : "Assign"}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
