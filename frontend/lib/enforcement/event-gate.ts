/**
 * 知维 OS Event Gate System — 事件门控系统
 * Zhiwei OS Event Gate System
 *
 * 核心能力：
 * validateEvent(event) → GateResult (ALLOW / BLOCK / MODIFY / QUARANTINE)
 *
 * 门控维度：
 * 1. rule-based gating         — 基于规则匹配
 * 2. authority-aware gating    — 权威层级感知（L1 > L2 > L3 > L4）
 * 3. severity-based blocking   — 基于严重级别阻断
 *
 * 决策优先级：
 * - 高优先级规则先评估
 * - 首个非 ALLOW 决策胜出（短路评估）
 * - 无规则匹配时默认 ALLOW
 */

import type { SystemEvent, EventSource, EventSeverity, EventType } from "@/types/event-bus";
import type { GateResult, GateDecision, GateRule, GateCondition } from "@/lib/enforcement/types";
import { policyEngine } from "@/lib/enforcement/policy-engine";

// ═══════════════════════════════════════════════════════════════
// EventGateSystem — 事件门控系统
// ═══════════════════════════════════════════════════════════════

export class EventGateSystem {
  /**
   * 验证事件 — 门控主入口
   *
   * @param event 待验证的事件
   * @returns 门控决策结果
   */
  validateEvent(event: SystemEvent): GateResult {
    const rules = policyEngine.getActiveRules();
    const evaluatedAt = new Date().toISOString();

    // 按优先级降序评估规则（短路：首个非 ALLOW 决策胜出）
    for (const rule of rules) {
      if (this.matchCondition(event, rule.condition)) {
        const decision = rule.decision;

        // 如果是 MODIFY，生成修改后的事件
        let modifiedEvent: SystemEvent | undefined;
        if (decision === "MODIFY") {
          modifiedEvent = this.applyModification(event, rule);
        }

        return {
          decision,
          rule_id: rule.rule_id,
          policy_id: this.findPolicyIdForRule(rule.rule_id),
          reason: rule.description,
          modified_event: modifiedEvent,
          authority_level: this.resolveAuthorityLevel(event),
          severity: event.severity,
          evaluated_at: evaluatedAt,
        };
      }
    }

    // 无规则匹配 → 默认 ALLOW
    return {
      decision: "ALLOW",
      rule_id: "default.allow",
      policy_id: "default",
      reason: "No matching rule, default allow",
      authority_level: this.resolveAuthorityLevel(event),
      severity: event.severity,
      evaluated_at: evaluatedAt,
    };
  }

  /**
   * 批量验证事件
   */
  validateBatch(events: SystemEvent[]): GateResult[] {
    return events.map((e) => this.validateEvent(e));
  }

  /**
   * 检查事件是否会被阻断（便捷方法）
   */
  isBlocked(event: SystemEvent): boolean {
    return this.validateEvent(event).decision === "BLOCK";
  }

  /**
   * 检查事件是否会被修改（便捷方法）
   */
  isModified(event: SystemEvent): boolean {
    return this.validateEvent(event).decision === "MODIFY";
  }

  // ─────────────────────────────────────────────────────────────
  // 内部方法
  // ─────────────────────────────────────────────────────────────

  /**
   * 匹配条件 — 检查事件是否满足门控条件
   */
  private matchCondition(event: SystemEvent, condition: GateCondition): boolean {
    // source 匹配
    if (condition.source) {
      const sources = Array.isArray(condition.source) ? condition.source : [condition.source];
      if (!sources.includes(event.source)) return false;
    }

    // type 匹配
    if (condition.type) {
      const types = Array.isArray(condition.type) ? condition.type : [condition.type];
      if (!types.includes(event.type)) return false;
    }

    // severity 匹配
    if (condition.severity) {
      const severities = Array.isArray(condition.severity) ? condition.severity : [condition.severity];
      if (!severities.includes(event.severity)) return false;
    }

    // trace_id 匹配
    if (condition.trace_id && event.trace_id !== condition.trace_id) {
      return false;
    }

    // 自定义谓词
    if (condition.predicate && !condition.predicate(event)) {
      return false;
    }

    return true;
  }

  /**
   * 应用修改 — 根据规则修改事件
   *
   * 当前支持的修改：
   * - severity 降级（critical → warn）
   * - 可扩展：payload 修改、metadata 注入等
   */
  private applyModification(event: SystemEvent, rule: GateRule): SystemEvent {
    // 默认修改：severity 降级
    if (event.severity === "critical") {
      return {
        ...event,
        severity: "warn" as EventSeverity,
        // 添加修改元数据
        causal: {
          ...event.causal,
          cause_metadata: {
            ...event.causal.cause_metadata,
            modified_by: rule.rule_id,
            original_severity: "critical",
            modified_at: new Date().toISOString(),
          },
        },
      };
    }

    // 默认不修改
    return event;
  }

  /**
   * 解析权威层级 — 根据 event.origin 决定
   */
  private resolveAuthorityLevel(event: SystemEvent): "L1" | "L2" | "L3" | "L4" {
    // backend 事件 = L1（最高权威）
    if (event.origin === "backend") return "L1";
    // simulated 事件 = L3（运行时缓存级别）
    return "L3";
  }

  /**
   * 查找规则所属的策略 ID
   */
  private findPolicyIdForRule(rule_id: string): string {
    for (const policy of policyEngine.getActivePolicies()) {
      if (policy.rules.some((r) => r.rule_id === rule_id)) {
        return policy.policy_id;
      }
    }
    return "unknown";
  }
}

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export const eventGateSystem = new EventGateSystem();
