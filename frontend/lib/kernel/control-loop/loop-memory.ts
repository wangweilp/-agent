/**
 * 知维 OS Kernel Control Loop — 控制循环内存
 * Zhiwei OS Kernel Control Loop — Loop Memory
 *
 * 记录所有循环历史，用于：
 * - 趋势分析（drift 是否在收敛）
 * - 失败模式检测（infinite healing loop）
 * - 自适应调度决策
 * - 审计与回放
 */

import type { LoopCycle, ControlLoopHistory } from "@/lib/kernel/control-loop/types";

// ═══════════════════════════════════════════════════════════════
// LoopMemory — 循环内存
// ═══════════════════════════════════════════════════════════════

export class LoopMemory {
  private cycles: LoopCycle[] = [];
  private maxHistorySize: number;

  constructor(maxHistorySize: number = 1000) {
    this.maxHistorySize = maxHistorySize;
  }

  /**
   * 记录循环
   */
  record(cycle: LoopCycle): void {
    this.cycles.push(cycle);
    if (this.cycles.length > this.maxHistorySize) {
      this.cycles.shift();
    }
  }

  /**
   * 获取历史
   */
  getHistory(): ControlLoopHistory {
    const total = this.cycles.length;
    const successful = this.cycles.filter((c) => c.success).length;
    const failed = total - successful;
    const avgDuration = total > 0
      ? this.cycles.reduce((sum, c) => sum + c.total_duration_ms, 0) / total
      : 0;

    return {
      cycles: [...this.cycles],
      total_cycles: total,
      successful_cycles: successful,
      failed_cycles: failed,
      avg_cycle_duration_ms: avgDuration,
      last_cycle: this.cycles[this.cycles.length - 1] ?? null,
    };
  }

  /**
   * 获取最近 N 个循环
   */
  getRecentCycles(n: number): LoopCycle[] {
    return this.cycles.slice(-n);
  }

  /**
   * 获取指定 trace 的循环
   */
  getCyclesByTrace(trace_id: string): LoopCycle[] {
    return this.cycles.filter((c) => c.trace_id === trace_id);
  }

  /**
   * 获取失败的循环
   */
  getFailedCycles(): LoopCycle[] {
    return this.cycles.filter((c) => !c.success);
  }

  /**
   * 检测 infinite healing loop（连续 N 次循环都在 HEALING 模式）
   */
  detectInfiniteHealingLoop(threshold: number = 5): boolean {
    const recent = this.getRecentCycles(threshold);
    if (recent.length < threshold) return false;
    return recent.every((c) => c.state_delta.new_mode === "HEALING");
  }

  /**
   * 检测 enforcement oscillation（模式频繁切换）
   */
  detectEnforcementOscillation(windowSize: number = 10): boolean {
    const recent = this.getRecentCycles(windowSize);
    if (recent.length < windowSize) return false;

    let modeChanges = 0;
    for (let i = 1; i < recent.length; i++) {
      if (recent[i].state_delta.new_mode !== recent[i - 1].state_delta.new_mode) {
        modeChanges++;
      }
    }
    // 模式切换超过 50% 视为振荡
    return modeChanges > windowSize / 2;
  }

  /**
   * 计算 drift 趋势（正数=收敛，负数=恶化）
   */
  getDriftTrend(windowSize: number = 5): number {
    const recent = this.getRecentCycles(windowSize);
    if (recent.length < 2) return 0;

    const first = recent[0].drift_score_after;
    const last = recent[recent.length - 1].drift_score_after;
    return first - last; // 正数表示 drift 下降（收敛）
  }

  /**
   * 清空历史
   */
  clear(): void {
    this.cycles = [];
  }

  /**
   * 获取统计
   */
  getStats(): {
    total: number;
    avg_drift: number;
    avg_health: number;
    healing_count: number;
    locked_count: number;
  } {
    if (this.cycles.length === 0) {
      return { total: 0, avg_drift: 0, avg_health: 0, healing_count: 0, locked_count: 0 };
    }

    const avgDrift = this.cycles.reduce((s, c) => s + c.drift_score_after, 0) / this.cycles.length;
    const healingCount = this.cycles.filter((c) => c.state_delta.new_mode === "HEALING").length;
    const lockedCount = this.cycles.filter((c) => c.state_delta.new_mode === "LOCKED").length;

    return {
      total: this.cycles.length,
      avg_drift: avgDrift,
      avg_health: 100 - avgDrift,
      healing_count: healingCount,
      locked_count: lockedCount,
    };
  }
}

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export const loopMemory = new LoopMemory();
