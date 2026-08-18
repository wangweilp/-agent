"use client";
import { AlertTriangle, Lock, FileText, Shield, Wifi } from "lucide-react";
import type { SecurityProfile } from "@/types/open-platform";

export function SecurityProfilePanel({ sp }: { sp: SecurityProfile | null }) {
  if (!sp) return <div className="rounded-md border border-red-400/20 bg-red-400/10 p-3 text-xs text-red-700"><AlertTriangle size={13} className="inline mr-1"/> 缺少安全配置</div>;

  const risks: string[] = [];
  if (sp.sandbox_level !== "no_execution") risks.push(`沙箱级别：${sp.sandbox_level}（不是 no_execution）`);
  if (sp.requires_network) risks.push("需要网络访问");
  if (sp.reads_user_data) risks.push("读取用户数据");
  if (sp.writes_user_data) risks.push("写入用户数据");

  return (
    <div className="os-card p-4">
      <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-os-text-high"><Shield size={14} className="text-os-accent"/> 安全配置</h3>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 text-xs">
        <div className="rounded-md bg-os-elevated/30 px-2 py-2 text-center">
          <p className="flex items-center justify-center gap-1 text-2xs text-os-subtle"><Wifi size={10}/> 网络</p>
          <span className={sp.requires_network ? "text-amber-800 font-semibold" : "text-emerald-700 font-semibold"}>{sp.requires_network ? "是" : "否"}</span>
        </div>
        <div className="rounded-md bg-os-elevated/30 px-2 py-2 text-center">
          <p className="flex items-center justify-center gap-1 text-2xs text-os-subtle"><FileText size={10}/> 读取数据</p>
          <span className={sp.reads_user_data ? "text-amber-800 font-semibold" : "text-emerald-700 font-semibold"}>{sp.reads_user_data ? "是" : "否"}</span>
        </div>
        <div className="rounded-md bg-os-elevated/30 px-2 py-2 text-center">
          <p className="flex items-center justify-center gap-1 text-2xs text-os-subtle"><FileText size={10}/> 写入数据</p>
          <span className={sp.writes_user_data ? "text-amber-800 font-semibold" : "text-emerald-700 font-semibold"}>{sp.writes_user_data ? "是" : "否"}</span>
        </div>
        <div className="rounded-md bg-os-elevated/30 px-2 py-2 text-center">
          <p className="flex items-center justify-center gap-1 text-2xs text-os-subtle"><Lock size={10}/> 沙箱</p>
          <span className={`${sp.sandbox_level === "no_execution" ? "text-emerald-700" : "text-red-700"} break-all font-semibold`}>{sp.sandbox_level}</span>
        </div>
      </div>
      {sp.allowed_domains.length > 0 && <div className="mt-2 break-all text-2xs text-os-subtle">允许域名：{sp.allowed_domains.join(", ")}</div>}
      {sp.data_access_scope.length > 0 && <div className="mt-1 break-all text-2xs text-os-subtle">访问范围：{sp.data_access_scope.join(", ")}</div>}
      {sp.risk_notes && <div className="mt-1 break-words text-2xs text-amber-800">风险说明：{sp.risk_notes}</div>}
      {risks.length > 0 && (
        <div className="mt-3 rounded-md border border-amber-400/20 bg-amber-400/5 p-3">
          <p className="flex items-center gap-1 text-xs font-medium text-amber-800"><AlertTriangle size={12}/> 风险标记</p>
          <ul className="mt-1 space-y-0.5">{risks.map((r, i) => <li key={i} className="text-2xs text-amber-800">• {r}</li>)}</ul>
        </div>
      )}
    </div>
  );
}
