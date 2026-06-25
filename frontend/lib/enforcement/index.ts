/**
 * 知维 OS Runtime Enforcement Kernel — 统一门面
 * Zhiwei OS Runtime Enforcement Kernel — Unified Facade
 *
 * v4 核心入口：
 * 整合 Event Gate + Enforcement Pipeline + Policy Engine + Enforcement Loop
 *
 * 架构层级：
 * ┌─────────────────────────────────────────┐
 * │  EnforcementFacade（本文件）           │  ← 统一入口
 * ├─────────────────────────────────────────┤
 * │  EnforcementLoop                        │  ← 闭环执行
 * │  EnforcementPipeline                    │  ← 流水线
 * │  EventGateSystem                        │  ← 事件门控
 * │  PolicyEngine                           │  ← 策略引擎
 * ├─────────────────────────────────────────┤
 * │  CausalKernel / Authority Layer（不修改）│  ← 数据层
 * └─────────────────────────────────────────┘
 *
 * 使用方式：
 *   import { enforcementFacade } from "@/lib/enforcement";
 *   const record = enforcementFacade.enforce(event);
 *   if (record.final_decision === "BLOCK") { ... }
 */

import { enforcementLoop } from "@/lib/enforcement/loop";
import { enforcementPipeline } from "@/lib/enforcement/pipeline";
import { eventGateSystem } from "@/lib/enforcement/event-gate";
import { policyEngine } from "@/lib/enforcement/policy-engine";
import type { SystemEvent } from "@/types/event-bus";
import type {
  EnforcementLoopRecord,
  EnforcementKernelState,
  EnforcementResult,
  GateResult,
  RuntimePolicy,
  PolicyDomain,
  PolicyUpdateRequest,
  PolicyUpdateResult,
} from "@/lib/enforcement/types";

// ═══════════════════════════════════════════════════════════════
// EnforcementFacade — 统一强制执行门面
// ═══════════════════════════════════════════════════════════════

export class EnforcementFacade {
  /**
   * 执行强制闭环 — 主入口
   * event → validate → enforce → apply → validate → reconcile
   */
  enforce(event: SystemEvent): EnforcementLoopRecord {
    return enforcementLoop.enforce(event);
  }

  /**
   * 批量执行
   */
  enforceBatch(events: SystemEvent[]): EnforcementLoopRecord[] {
    return enforcementLoop.enforceBatch(events);
  }

  /**
   * 预检查 — 不实际执行，仅检查是否会被允许
   */
  preCheck(event: SystemEvent): { would_allow: boolean; decision: GateResult["decision"]; reason: string } {
    return enforcementLoop.preCheck(event);
  }

  /**
   * 验证事件（门控评估）
   */
  validateEvent(event: SystemEvent): GateResult {
    return eventGateSystem.validateEvent(event);
  }

  /**
   * 执行流水线（不含闭环）
   */
  executePipeline(event: SystemEvent): EnforcementResult {
    return enforcementPipeline.execute(event);
  }

  // ── 策略管理 ──

  /**
   * 获取所有活跃策略
   */
  getPolicies(): RuntimePolicy[] {
    return policyEngine.getActivePolicies();
  }

  /**
   * 获取指定域的策略
   */
  getPoliciesByDomain(domain: PolicyDomain): RuntimePolicy[] {
    return policyEngine.getPoliciesByDomain(domain);
  }

  /**
   * 更新策略
   */
  updatePolicy(request: PolicyUpdateRequest): PolicyUpdateResult {
    return policyEngine.updatePolicy(request);
  }

  /**
   * 启用/禁用策略
   */
  togglePolicy(policy_id: string, enabled: boolean): PolicyUpdateResult {
    return policyEngine.togglePolicy(policy_id, enabled);
  }

  /**
   * 注册新策略
   */
  registerPolicy(policy: RuntimePolicy): void {
    policyEngine.registerPolicy(policy);
  }

  // ── 状态与历史 ──

  /**
   * 获取内核状态
   */
  getState(): EnforcementKernelState {
    return enforcementLoop.getState();
  }

  /**
   * 获取执行历史
   */
  getHistory(limit?: number): EnforcementLoopRecord[] {
    return enforcementLoop.getHistory(limit);
  }

  /**
   * 获取被阻断的事件历史
   */
  getBlockedHistory(limit?: number): EnforcementLoopRecord[] {
    return enforcementLoop.getBlockedHistory(limit);
  }

  /**
   * 启用/禁用内核
   */
  setEnabled(enabled: boolean): void {
    enforcementLoop.setEnabled(enabled);
  }

  /**
   * 订阅闭环执行
   */
  subscribe(listener: (record: EnforcementLoopRecord) => void): () => void {
    return enforcementLoop.subscribe(listener);
  }
}

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export const enforcementFacade = new EnforcementFacade();

// 重新导出子模块，方便统一引用
export { enforcementLoop } from "@/lib/enforcement/loop";
export { enforcementPipeline } from "@/lib/enforcement/pipeline";
export { eventGateSystem } from "@/lib/enforcement/event-gate";
export { policyEngine } from "@/lib/enforcement/policy-engine";
