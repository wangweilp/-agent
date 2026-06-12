"use client";
import { AlertTriangle, Lock, FileText, Shield, Wifi } from "lucide-react";
import type { SecurityProfile } from "@/types/open-platform";

export function SecurityProfilePanel({ sp }: { sp: SecurityProfile | null }) {
  if (!sp) return <div className="rounded-md border border-red-400/20 bg-red-400/10 p-3 text-xs text-red-300"><AlertTriangle size={13} className="inline mr-1"/> Security profile is missing</div>;

  const risks: string[] = [];
  if (sp.sandbox_level !== "no_execution") risks.push(`Sandbox level: ${sp.sandbox_level} (not no_execution)`);
  if (sp.requires_network) risks.push("Requires network access");
  if (sp.reads_user_data) risks.push("Reads user data");
  if (sp.writes_user_data) risks.push("Writes user data");

  return (
    <div className="os-card p-4">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-os-text-high mb-3"><Shield size={14} className="text-os-accent"/> Security Profile</h3>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 text-xs">
        <div className="rounded-md bg-os-elevated/30 px-2 py-2 text-center">
          <p className="text-2xs text-os-muted flex items-center justify-center gap-1"><Wifi size={10}/> Network</p>
          <span className={sp.requires_network ? "text-amber-300 font-semibold" : "text-emerald-300 font-semibold"}>{sp.requires_network ? "Yes" : "No"}</span>
        </div>
        <div className="rounded-md bg-os-elevated/30 px-2 py-2 text-center">
          <p className="text-2xs text-os-muted flex items-center justify-center gap-1"><FileText size={10}/> Reads Data</p>
          <span className={sp.reads_user_data ? "text-amber-300 font-semibold" : "text-emerald-300 font-semibold"}>{sp.reads_user_data ? "Yes" : "No"}</span>
        </div>
        <div className="rounded-md bg-os-elevated/30 px-2 py-2 text-center">
          <p className="text-2xs text-os-muted flex items-center justify-center gap-1"><FileText size={10}/> Writes Data</p>
          <span className={sp.writes_user_data ? "text-amber-300 font-semibold" : "text-emerald-300 font-semibold"}>{sp.writes_user_data ? "Yes" : "No"}</span>
        </div>
        <div className="rounded-md bg-os-elevated/30 px-2 py-2 text-center">
          <p className="text-2xs text-os-muted flex items-center justify-center gap-1"><Lock size={10}/> Sandbox</p>
          <span className={sp.sandbox_level === "no_execution" ? "text-emerald-300 font-semibold" : "text-red-300 font-semibold"}>{sp.sandbox_level}</span>
        </div>
      </div>
      {sp.allowed_domains.length > 0 && <div className="mt-2 text-2xs text-os-subtle">Domains: {sp.allowed_domains.join(", ")}</div>}
      {sp.data_access_scope.length > 0 && <div className="mt-1 text-2xs text-os-subtle">Access scope: {sp.data_access_scope.join(", ")}</div>}
      {sp.risk_notes && <div className="mt-1 text-2xs text-amber-300">Risk notes: {sp.risk_notes}</div>}
      {risks.length > 0 && (
        <div className="mt-3 rounded-md border border-amber-400/20 bg-amber-400/5 p-3">
          <p className="text-xs font-medium text-amber-300 flex items-center gap-1"><AlertTriangle size={12}/> Risk Flags</p>
          <ul className="mt-1 space-y-0.5">{risks.map((r, i) => <li key={i} className="text-2xs text-amber-200">• {r}</li>)}</ul>
        </div>
      )}
    </div>
  );
}
