"use client";

import { useState, useMemo } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  SlidersHorizontal, FlaskConical, Play, Loader2,
  CheckCircle2, XCircle, AlertTriangle, Shield, Globe,
  FileText, Lock, Clock, Cpu, Database, ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  listSandboxPolicies, testSandboxPolicy,
} from "@/services/runtime-admin";
import type {
  SandboxPolicy, SandboxPolicyTestRequest, SandboxPolicyTestResult,
} from "@/types/runtime-admin";

// ── 默认测试请求参数 ──
const DEFAULT_REQUEST: SandboxPolicyTestRequest = {
  sandbox_level: "restricted",
  requested_network: true,
  requested_domains: ["api.openai.com"],
  requested_filesystem_read: false,
  requested_filesystem_write: false,
  requested_secret_names: [],
  requested_timeout_ms: 30000,
  requested_memory_mb: 512,
  requested_data_access_scope: [],
};

const SANDBOX_LEVELS = ["no_execution", "simulation_only", "restricted", "isolated"];

const SCOPE_LABELS: Record<string, string> = {
  system: "系统级",
  tenant: "租户级",
};

export function SandboxSimulator() {
  const [selectedPolicyId, setSelectedPolicyId] = useState<string>("");
  const [req, setReq] = useState<SandboxPolicyTestRequest>(DEFAULT_REQUEST);
  const [domainsText, setDomainsText] = useState("api.openai.com");
  const [secretsText, setSecretsText] = useState("");
  const [scopeText, setScopeText] = useState("");

  // ── 策略列表 ──
  const { data: policiesData, isLoading: policiesLoading } = useQuery({
    queryKey: ["sandbox-policies-list"],
    queryFn: () => listSandboxPolicies(),
    refetchInterval: 60000,
  });

  const policies: SandboxPolicy[] = policiesData?.policies || [];

  // 自动选中第一个策略
  const effectivePolicyId = selectedPolicyId || policies[0]?.policy_id || "";
  const selectedPolicy = useMemo(
    () => policies.find((p) => p.policy_id === effectivePolicyId),
    [policies, effectivePolicyId],
  );

  // ── 测试执行 ──
  const testMutation = useMutation({
    mutationFn: async () => {
      if (!effectivePolicyId) return;
      // 解析逗号分隔的输入
      const domains = domainsText.split(",").map((s) => s.trim()).filter(Boolean);
      const secrets = secretsText.split(",").map((s) => s.trim()).filter(Boolean);
      const scope = scopeText.split(",").map((s) => s.trim()).filter(Boolean);
      const payload: SandboxPolicyTestRequest = {
        ...req,
        requested_domains: domains,
        requested_secret_names: secrets,
        requested_data_access_scope: scope,
      };
      return testSandboxPolicy(effectivePolicyId, payload);
    },
  });

  const result: SandboxPolicyTestResult | undefined = testMutation.data;
  const isAllowed = result?.allowed === true;

  const updateReq = (patch: Partial<SandboxPolicyTestRequest>) =>
    setReq((prev) => ({ ...prev, ...patch }));

  return (
    <div className="space-y-4 scanline">
      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FlaskConical size={14} className="text-rose-400" />
          <h2 className="text-sm font-semibold text-os-text-high">沙箱策略模拟器</h2>
          <span className="text-2xs text-os-muted">metadata-only simulation · no real execution</span>
        </div>
        <div className="text-2xs text-os-muted font-mono">
          {policies.length} policies · {policies.filter((p) => p.status === "active").length} active
        </div>
      </div>

      <div className="grid grid-cols-12 gap-4">
        {/* ── 左侧：策略选择 ── */}
        <div className="col-span-12 lg:col-span-4 space-y-3">
          <SectionLabel icon={<Shield size={11} />} text="策略选择" />
          <div className="rounded-md border border-os-border bg-os-surface/50 max-h-[480px] overflow-y-auto">
            {policiesLoading ? (
              <div className="p-4 text-center text-2xs text-os-muted flex items-center justify-center gap-2">
                <Loader2 size={12} className="animate-spin" /> 加载策略...
              </div>
            ) : policies.length === 0 ? (
              <div className="p-4 text-center text-2xs text-os-muted">暂无策略</div>
            ) : (
              <ul className="divide-y divide-os-border/50">
                {policies.map((p) => {
                  const isActive = effectivePolicyId === p.policy_id;
                  return (
                    <li key={p.policy_id}>
                      <button
                        onClick={() => setSelectedPolicyId(p.policy_id)}
                        className={cn(
                          "w-full text-left px-3 py-2.5 transition-colors",
                          isActive
                            ? "bg-rose-400/5 border-l-2 border-rose-400"
                            : "hover:bg-os-elevated/50 border-l-2 border-transparent",
                        )}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs font-medium text-os-text truncate">{p.name}</span>
                          <span className={cn(
                            "text-2xs px-1.5 py-0.5 rounded shrink-0",
                            p.status === "active"
                              ? "bg-emerald-400/10 text-emerald-400"
                              : "bg-zinc-500/10 text-zinc-500",
                          )}>
                            {p.status}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-2xs text-os-muted">{SCOPE_LABELS[p.scope] || p.scope}</span>
                          <span className="text-2xs text-os-muted">·</span>
                          <span className="text-2xs text-os-muted font-mono">{p.sandbox_level}</span>
                        </div>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          {/* 选中策略详情 */}
          {selectedPolicy && (
            <div className="rounded-md border border-os-border bg-os-surface/30 p-3 space-y-2">
              <div className="text-2xs font-medium text-os-subtle uppercase tracking-wider">策略约束</div>
              <div className="grid grid-cols-2 gap-2 text-2xs">
                <ConstraintItem label="网络" value={selectedPolicy.allow_network ? "允许" : "禁止"} ok={selectedPolicy.allow_network} />
                <ConstraintItem label="文件读" value={selectedPolicy.allow_filesystem_read ? "允许" : "禁止"} ok={selectedPolicy.allow_filesystem_read} />
                <ConstraintItem label="文件写" value={selectedPolicy.allow_filesystem_write ? "允许" : "禁止"} ok={selectedPolicy.allow_filesystem_write} />
                <ConstraintItem label="密钥" value={selectedPolicy.allow_secrets ? "允许" : "禁止"} ok={selectedPolicy.allow_secrets} />
                <ConstraintItem label="超时" value={`${selectedPolicy.max_timeout_ms}ms`} />
                <ConstraintItem label="内存" value={`${selectedPolicy.max_memory_mb}MB`} />
              </div>
              {selectedPolicy.allowed_domains.length > 0 && (
                <div className="pt-1">
                  <div className="text-2xs text-os-muted mb-1">允许域名</div>
                  <div className="flex flex-wrap gap-1">
                    {selectedPolicy.allowed_domains.map((d) => (
                      <span key={d} className="text-2xs px-1.5 py-0.5 rounded bg-emerald-400/10 text-emerald-400 font-mono">
                        {d}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── 中间：测试请求参数 ── */}
        <div className="col-span-12 lg:col-span-5 space-y-3">
          <SectionLabel icon={<SlidersHorizontal size={11} />} text="测试请求参数" />

          <div className="rounded-md border border-os-border bg-os-surface/50 p-3 space-y-3">
            {/* Sandbox Level */}
            <Field label="Sandbox Level" icon={<Shield size={11} />}>
              <select
                value={req.sandbox_level}
                onChange={(e) => updateReq({ sandbox_level: e.target.value })}
                className="w-full h-7 px-2 rounded bg-os-base border border-os-border text-xs text-os-text focus:outline-none focus:border-rose-400/50"
              >
                {SANDBOX_LEVELS.map((lv) => (
                  <option key={lv} value={lv}>{lv}</option>
                ))}
              </select>
            </Field>

            {/* Network */}
            <Field label="请求网络访问" icon={<Globe size={11} />}>
              <div className="flex items-center gap-3">
                <ToggleChip
                  active={req.requested_network}
                  onClick={() => updateReq({ requested_network: !req.requested_network })}
                  label={req.requested_network ? "允许" : "拒绝"}
                />
                <input
                  type="text"
                  value={domainsText}
                  onChange={(e) => setDomainsText(e.target.value)}
                  placeholder="逗号分隔域名，如 api.openai.com, github.com"
                  className="flex-1 h-7 px-2 rounded bg-os-base border border-os-border text-xs text-os-text font-mono focus:outline-none focus:border-rose-400/50"
                />
              </div>
            </Field>

            {/* Filesystem */}
            <Field label="文件系统" icon={<FileText size={11} />}>
              <div className="flex items-center gap-3">
                <ToggleChip
                  active={req.requested_filesystem_read}
                  onClick={() => updateReq({ requested_filesystem_read: !req.requested_filesystem_read })}
                  label={`读 ${req.requested_filesystem_read ? "ON" : "OFF"}`}
                />
                <ToggleChip
                  active={req.requested_filesystem_write}
                  onClick={() => updateReq({ requested_filesystem_write: !req.requested_filesystem_write })}
                  label={`写 ${req.requested_filesystem_write ? "ON" : "OFF"}`}
                />
              </div>
            </Field>

            {/* Secrets */}
            <Field label="请求密钥" icon={<Lock size={11} />}>
              <input
                type="text"
                value={secretsText}
                onChange={(e) => setSecretsText(e.target.value)}
                placeholder="逗号分隔密钥名，如 OPENAI_API_KEY, DB_PASSWORD"
                className="w-full h-7 px-2 rounded bg-os-base border border-os-border text-xs text-os-text font-mono focus:outline-none focus:border-rose-400/50"
              />
            </Field>

            {/* Resource Limits */}
            <div className="grid grid-cols-2 gap-3">
              <Field label="超时 (ms)" icon={<Clock size={11} />}>
                <input
                  type="number"
                  value={req.requested_timeout_ms}
                  onChange={(e) => updateReq({ requested_timeout_ms: Number(e.target.value) })}
                  className="w-full h-7 px-2 rounded bg-os-base border border-os-border text-xs text-os-text font-mono focus:outline-none focus:border-rose-400/50"
                />
              </Field>
              <Field label="内存 (MB)" icon={<Cpu size={11} />}>
                <input
                  type="number"
                  value={req.requested_memory_mb}
                  onChange={(e) => updateReq({ requested_memory_mb: Number(e.target.value) })}
                  className="w-full h-7 px-2 rounded bg-os-base border border-os-border text-xs text-os-text font-mono focus:outline-none focus:border-rose-400/50"
                />
              </Field>
            </div>

            {/* Data Access Scope */}
            <Field label="数据访问范围" icon={<Database size={11} />}>
              <input
                type="text"
                value={scopeText}
                onChange={(e) => setScopeText(e.target.value)}
                placeholder="逗号分隔，如 memory:read, memory:write"
                className="w-full h-7 px-2 rounded bg-os-base border border-os-border text-xs text-os-text font-mono focus:outline-none focus:border-rose-400/50"
              />
            </Field>

            {/* Execute */}
            <button
              onClick={() => testMutation.mutate()}
              disabled={!effectivePolicyId || testMutation.isPending}
              className={cn(
                "w-full h-9 rounded-md flex items-center justify-center gap-2 text-xs font-medium transition-all",
                !effectivePolicyId || testMutation.isPending
                  ? "bg-os-elevated text-os-muted cursor-not-allowed"
                  : "bg-rose-500/10 text-rose-300 border border-rose-400/30 hover:bg-rose-500/20 hover:border-rose-400/50",
              )}
            >
              {testMutation.isPending ? (
                <><Loader2 size={13} className="animate-spin" /> 执行模拟...</>
              ) : (
                <><Play size={13} /> 执行策略模拟</>
              )}
            </button>

            {testMutation.isError && (
              <div className="text-2xs text-rose-400 flex items-center gap-1.5">
                <AlertTriangle size={11} />
                {(testMutation.error as Error)?.message || "模拟执行失败"}
              </div>
            )}
          </div>
        </div>

        {/* ── 右侧：决策结果 ── */}
        <div className="col-span-12 lg:col-span-3 space-y-3">
          <SectionLabel icon={<ChevronRight size={11} />} text="决策结果" />

          {!result ? (
            <div className="rounded-md border border-dashed border-os-border bg-os-surface/20 p-6 text-center">
              <FlaskConical size={20} className="mx-auto text-os-muted mb-2" />
              <p className="text-2xs text-os-muted">尚未执行模拟</p>
              <p className="text-2xs text-os-muted mt-1">配置参数后点击执行</p>
            </div>
          ) : (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-3"
            >
              {/* 决策卡片 */}
              <div className={cn(
                "rounded-md border p-3",
                isAllowed
                  ? "border-emerald-400/30 bg-emerald-400/[0.03]"
                  : "border-rose-400/30 bg-rose-400/[0.03]",
              )}>
                <div className="flex items-center gap-2">
                  {isAllowed ? (
                    <CheckCircle2 size={16} className="text-emerald-400" />
                  ) : (
                    <XCircle size={16} className="text-rose-400" />
                  )}
                  <span className={cn(
                    "text-sm font-semibold",
                    isAllowed ? "text-emerald-300" : "text-rose-300",
                  )}>
                    {result.decision}
                  </span>
                </div>
                <div className="mt-1 text-2xs text-os-muted font-mono">
                  allowed = {String(result.allowed)}
                </div>
              </div>

              {/* Violations */}
              {result.violations.length > 0 && (
                <div className="rounded-md border border-rose-400/20 bg-rose-400/[0.02] p-3">
                  <div className="text-2xs font-medium text-rose-300 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                    <XCircle size={11} /> 违规 ({result.violations.length})
                  </div>
                  <ul className="space-y-1">
                    {result.violations.map((v, i) => (
                      <li key={i} className="text-2xs text-rose-200/80 font-mono leading-relaxed">
                        · {v}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Warnings */}
              {result.warnings.length > 0 && (
                <div className="rounded-md border border-amber-400/20 bg-amber-400/[0.02] p-3">
                  <div className="text-2xs font-medium text-amber-300 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                    <AlertTriangle size={11} /> 警告 ({result.warnings.length})
                  </div>
                  <ul className="space-y-1">
                    {result.warnings.map((w, i) => (
                      <li key={i} className="text-2xs text-amber-200/80 font-mono leading-relaxed">
                        · {w}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Evaluated Rules */}
              {result.evaluated_rules.length > 0 && (
                <div className="rounded-md border border-os-border bg-os-surface/30 p-3">
                  <div className="text-2xs font-medium text-os-subtle uppercase tracking-wider mb-2">
                    评估规则 ({result.evaluated_rules.length})
                  </div>
                  <ul className="space-y-1">
                    {result.evaluated_rules.map((r, i) => (
                      <li key={i} className="text-2xs text-os-muted font-mono leading-relaxed">
                        · {r}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Metadata */}
              {result.metadata && Object.keys(result.metadata).length > 0 && (
                <div className="rounded-md border border-os-border bg-os-surface/30 p-3">
                  <div className="text-2xs font-medium text-os-subtle uppercase tracking-wider mb-2">元数据</div>
                  <pre className="text-2xs text-os-muted font-mono whitespace-pre-wrap break-all leading-relaxed">
                    {JSON.stringify(result.metadata, null, 2)}
                  </pre>
                </div>
              )}
            </motion.div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── 子组件 ──

function SectionLabel({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <div className="flex items-center gap-1.5 text-2xs font-medium text-os-subtle uppercase tracking-wider">
      <span className="text-rose-400/70">{icon}</span>
      {text}
    </div>
  );
}

function Field({
  label, icon, children,
}: {
  label: string; icon: React.ReactNode; children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label className="flex items-center gap-1.5 text-2xs text-os-subtle">
        <span className="text-os-muted">{icon}</span>
        {label}
      </label>
      {children}
    </div>
  );
}

function ToggleChip({
  active, onClick, label,
}: {
  active: boolean; onClick: () => void; label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "px-2 py-1 rounded text-2xs font-mono transition-colors shrink-0",
        active
          ? "bg-rose-400/10 text-rose-300 border border-rose-400/30"
          : "bg-os-elevated text-os-muted border border-os-border",
      )}
    >
      {label}
    </button>
  );
}

function ConstraintItem({
  label, value, ok,
}: {
  label: string; value: string; ok?: boolean;
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-os-muted">{label}</span>
      <span className={cn(
        "font-mono",
        ok === undefined ? "text-os-subtle" : ok ? "text-emerald-400" : "text-rose-400",
      )}>
        {value}
      </span>
    </div>
  );
}
