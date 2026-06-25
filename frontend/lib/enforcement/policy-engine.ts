/**
 * 知维 OS Policy Engine — 策略引擎
 * Zhiwei OS Policy Engine
 *
 * 三大策略域：
 * 1. kill_switch        — 紧急阻断策略（最高优先级）
 * 2. memory_write       — Memory 写入策略（认知面控制）
 * 3. governance_override — Governance 覆盖策略（治理面控制）
 *
 * 能力：
 * - dynamic policy update   — 动态更新策略
 * - policy versioning       — 策略版本管理
 * - policy priority resolution — 策略优先级解决（同域内高优先级胜出）
 */

import type {
  PolicyDomain,
  RuntimePolicy,
  PolicyUpdateRequest,
  PolicyUpdateResult,
  GateRule,
} from "@/lib/enforcement/types";

// ═══════════════════════════════════════════════════════════════
// 默认策略 — 三大策略域的内置策略
// ═══════════════════════════════════════════════════════════════

/**
 * Kill Switch 策略 — 紧急阻断
 * 当 kill_switch.triggered 事件发生时，阻断所有同 trace 的后续事件
 */
function createDefaultKillSwitchPolicy(): RuntimePolicy {
  return {
    policy_id: "policy.kill_switch.default",
    domain: "kill_switch",
    name: "Default Kill Switch Policy",
    description: "阻断 kill switch 触发后的所有同 trace 事件",
    version: 1,
    priority: 1000, // 最高优先级
    status: "active",
    rules: [
      {
        rule_id: "rule.kill_switch.block_after_trigger",
        name: "Block After Kill Switch Triggered",
        description: "kill_switch.triggered 后阻断同 trace 的 agent.action 事件",
        condition: {
          type: ["agent.action.started", "agent.action.completed"],
        },
        decision: "BLOCK",
        priority: 1000,
        enabled: true,
      },
      {
        rule_id: "rule.kill_switch.block_high_risk_tools",
        name: "Block High Risk Tools After Kill",
        description: "kill_switch 触发后阻断高风险工具调用",
        condition: {
          type: "agent.tool.called",
          predicate: (event) => {
            const payload = event.payload as { risk_level?: string };
            return payload?.risk_level === "high";
          },
        },
        decision: "BLOCK",
        priority: 999,
        enabled: true,
      },
    ],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
}

/**
 * Memory Write 策略 — 认知面控制
 * 阻断低重要性的 LTM 写入，防止记忆膨胀
 */
function createDefaultMemoryWritePolicy(): RuntimePolicy {
  return {
    policy_id: "policy.memory_write.default",
    domain: "memory_write",
    name: "Default Memory Write Policy",
    description: "控制 memory 写入，阻断低重要性 LTM 写入",
    version: 1,
    priority: 500,
    status: "active",
    rules: [
      {
        rule_id: "rule.memory_write.block_low_importance_ltm",
        name: "Block Low Importance LTM Write",
        description: "阻断 importance < 0.3 的 LTM 写入",
        condition: {
          type: "memory.write.ltm",
          predicate: (event) => {
            const payload = event.payload as { importance?: number };
            return (payload?.importance ?? 1) < 0.3;
          },
        },
        decision: "BLOCK",
        priority: 500,
        enabled: true,
      },
      {
        rule_id: "rule.memory_write.downgrade_critical_stm",
        name: "Downgrade Critical STM to Warn",
        description: "将 critical 级别的 STM 写入降级为 warn",
        condition: {
          type: "memory.write.stm",
          severity: "critical",
        },
        decision: "MODIFY",
        priority: 400,
        enabled: true,
      },
    ],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
}

/**
 * Governance Override 策略 — 治理面控制
 * 当 governance.execution.blocked 事件发生时，阻断后续相关执行
 */
function createDefaultGovernanceOverridePolicy(): RuntimePolicy {
  return {
    policy_id: "policy.governance_override.default",
    domain: "governance_override",
    name: "Default Governance Override Policy",
    description: "governance 阻断后强制阻断相关执行",
    version: 1,
    priority: 800,
    status: "active",
    rules: [
      {
        rule_id: "rule.governance.block_policy_violation_followup",
        name: "Block After Policy Violation",
        description: "policy.violation 后阻断同 trace 的 agent.tool.called",
        condition: {
          type: "agent.tool.called",
        },
        decision: "BLOCK",
        priority: 800,
        enabled: true,
      },
      {
        rule_id: "rule.governance.quarantine_incident_critical",
        name: "Quarantine Critical Incidents",
        description: "隔离 critical 级别的 incident.created 事件待审核",
        condition: {
          type: "governance.incident.created",
          severity: "critical",
        },
        decision: "QUARANTINE",
        priority: 700,
        enabled: true,
      },
    ],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
}

// ═══════════════════════════════════════════════════════════════
// PolicyEngine — 策略引擎
// ═══════════════════════════════════════════════════════════════

type PolicyListener = (policy: RuntimePolicy) => void;

export class PolicyEngine {
  /** 策略存储 — policy_id → policy */
  private policies: Map<string, RuntimePolicy> = new Map();
  /** 域索引 — domain → policy_id[] */
  private domainIndex: Map<PolicyDomain, string[]> = new Map();
  /** 监听器 */
  private listeners: Set<PolicyListener> = new Set();

  constructor() {
    // 注册默认策略
    this.registerPolicy(createDefaultKillSwitchPolicy());
    this.registerPolicy(createDefaultMemoryWritePolicy());
    this.registerPolicy(createDefaultGovernanceOverridePolicy());
  }

  /**
   * 注册策略
   */
  registerPolicy(policy: RuntimePolicy): void {
    this.policies.set(policy.policy_id, policy);

    // 更新域索引
    const domainPolicies = this.domainIndex.get(policy.domain) || [];
    if (!domainPolicies.includes(policy.policy_id)) {
      domainPolicies.push(policy.policy_id);
      this.domainIndex.set(policy.domain, domainPolicies);
    }

    this.notifyListeners(policy);
  }

  /**
   * 获取策略
   */
  getPolicy(policy_id: string): RuntimePolicy | null {
    return this.policies.get(policy_id) ?? null;
  }

  /**
   * 获取指定域的所有策略（按优先级降序）
   */
  getPoliciesByDomain(domain: PolicyDomain): RuntimePolicy[] {
    const ids = this.domainIndex.get(domain) || [];
    return ids
      .map((id) => this.policies.get(id))
      .filter((p): p is RuntimePolicy => p !== undefined && p !== null && p.status === "active")
      .sort((a, b) => b.priority - a.priority);
  }

  /**
   * 获取所有活跃策略
   */
  getActivePolicies(): RuntimePolicy[] {
    return Array.from(this.policies.values())
      .filter((p) => p.status === "active")
      .sort((a, b) => b.priority - a.priority);
  }

  /**
   * 获取所有活跃规则（跨策略，按优先级降序）
   */
  getActiveRules(): GateRule[] {
    const rules: GateRule[] = [];
    for (const policy of this.getActivePolicies()) {
      for (const rule of policy.rules) {
        if (rule.enabled) {
          rules.push(rule);
        }
      }
    }
    return rules.sort((a, b) => b.priority - a.priority);
  }

  /**
   * 动态更新策略
   */
  updatePolicy(request: PolicyUpdateRequest): PolicyUpdateResult {
    const existing = this.policies.get(request.policy_id);
    if (!existing) {
      return {
        success: false,
        policy: null,
        previous_version: 0,
        new_version: 0,
        error: `Policy ${request.policy_id} not found`,
      };
    }

    const previousVersion = existing.version;
    const updated: RuntimePolicy = {
      ...existing,
      ...request.patch,
      updated_at: new Date().toISOString(),
      version: request.bump_version ? existing.version + 1 : existing.version,
    };

    this.policies.set(request.policy_id, updated);
    this.notifyListeners(updated);

    return {
      success: true,
      policy: updated,
      previous_version: previousVersion,
      new_version: updated.version,
      error: null,
    };
  }

  /**
   * 启用/禁用策略
   */
  togglePolicy(policy_id: string, enabled: boolean): PolicyUpdateResult {
    return this.updatePolicy({
      policy_id,
      patch: { status: enabled ? "active" : "disabled" },
      bump_version: true,
    });
  }

  /**
   * 删除策略
   */
  deletePolicy(policy_id: string): boolean {
    const policy = this.policies.get(policy_id);
    if (!policy) return false;

    this.policies.delete(policy_id);
    const domainPolicies = this.domainIndex.get(policy.domain) || [];
    const idx = domainPolicies.indexOf(policy_id);
    if (idx >= 0) domainPolicies.splice(idx, 1);
    return true;
  }

  /**
   * 策略优先级解决 — 同域内高优先级胜出
   * 返回该域内优先级最高的策略
   */
  resolvePriority(domain: PolicyDomain): RuntimePolicy | null {
    const policies = this.getPoliciesByDomain(domain);
    return policies.length > 0 ? policies[0] : null;
  }

  /**
   * 订阅策略变更
   */
  subscribe(listener: PolicyListener): () => void {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  }

  /**
   * 获取统计
   */
  getStats(): {
    total_policies: number;
    active_policies: number;
    active_rules: number;
    by_domain: Record<PolicyDomain, number>;
  } {
    const byDomain: Record<PolicyDomain, number> = {
      kill_switch: 0,
      memory_write: 0,
      governance_override: 0,
    };
    let activeRules = 0;

    for (const policy of this.policies.values()) {
      if (policy.status === "active") {
        byDomain[policy.domain]++;
        activeRules += policy.rules.filter((r) => r.enabled).length;
      }
    }

    return {
      total_policies: this.policies.size,
      active_policies: this.getActivePolicies().length,
      active_rules: activeRules,
      by_domain: byDomain,
    };
  }

  private notifyListeners(policy: RuntimePolicy): void {
    for (const listener of this.listeners) {
      try {
        listener(policy);
      } catch (err) {
        console.error("[PolicyEngine] listener error:", err);
      }
    }
  }
}

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export const policyEngine = new PolicyEngine();
