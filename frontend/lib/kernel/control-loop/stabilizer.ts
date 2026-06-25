/**
 * 知维 OS Self-Stabilization System — 自稳定系统
 * Zhiwei OS Self-Stabilization System
 *
 * 能力：
 * stabilizeSystem(trace_id)
 *
 * 行为：
 * 1. detect instability（检测不稳定）
 * 2. reduce enforcement pressure（降低执行压力）
 * 3. increase snapshot dependency（增加快照依赖）
 * 4. trigger healing if needed（必要时触发修复）
 *
 * 不稳定检测维度：
 * - drift_score 持续高
 * - 连续多次 HEALING 模式
 * - enforcement oscillation（模式振荡）
 * - event backlog explosion（事件积压）
 */

import { loopMemory } from "@/lib/kernel/control-loop/loop-memory";
import { autoRecoveryEngine } from "@/lib/self-healing/recovery-engine";
import { consistencyAutoHealer } from "@/lib/self-healing/auto-healer";
import { persistencePipeline } from "@/lib/persistence/pipeline";
import { causalKernel } from "@/lib/event-bus/causal-kernel";
import type {
  StabilityAssessment,
  StabilizationResult,
  ControlMode,
} from "@/lib/kernel/control-loop/types";

// ═══════════════════════════════════════════════════════════════
// Stabilizer — 自稳定器
// ═══════════════════════════════════════════════════════════════

export class Stabilizer {
  /**
   * 评估稳定性
   */
  assessStability(
    driftScore: number,
    healthScore: number,
    currentMode: ControlMode,
  ): StabilityAssessment {
    const reasons: string[] = [];
    let pressureAdjustment = 0;
    let snapshotDependency = 0;
    let needsHealing = false;

    // 1. drift 持续高
    if (driftScore > 50) {
      reasons.push(`High drift score: ${driftScore}`);
      pressureAdjustment = -20; // 降低压力
      snapshotDependency = 0.7; // 增加快照依赖
      needsHealing = true;
    } else if (driftScore > 20) {
      reasons.push(`Elevated drift score: ${driftScore}`);
      pressureAdjustment = -10;
      snapshotDependency = 0.4;
    }

    // 2. 检测 infinite healing loop
    if (loopMemory.detectInfiniteHealingLoop(5)) {
      reasons.push("Infinite healing loop detected (5+ consecutive HEALING cycles)");
      pressureAdjustment = -30;
      needsHealing = false; // 停止 healing，避免无限循环
    }

    // 3. 检测 enforcement oscillation
    if (loopMemory.detectEnforcementOscillation(10)) {
      reasons.push("Enforcement oscillation detected (frequent mode changes)");
      pressureAdjustment = -15;
    }

    // 4. 健康分数过低
    if (healthScore < 30) {
      reasons.push(`Critical health score: ${healthScore}`);
      needsHealing = true;
      pressureAdjustment = -25;
    }

    // 5. 当前在 HEALING 模式
    if (currentMode === "HEALING") {
      reasons.push("System in HEALING mode");
      snapshotDependency = Math.max(snapshotDependency, 0.6);
    }

    // 6. 当前在 LOCKED 模式
    if (currentMode === "LOCKED") {
      reasons.push("System LOCKED - critical state");
      pressureAdjustment = -50;
      needsHealing = true;
    }

    const stable = reasons.length === 0;

    return {
      stable,
      instability_reasons: reasons,
      pressure_adjustment: pressureAdjustment,
      snapshot_dependency: snapshotDependency,
      needs_healing: needsHealing,
      assessed_at: new Date().toISOString(),
    };
  }

  /**
   * 稳定化系统 — 主入口
   *
   * @param trace_id      要稳定的 trace
   * @param currentMode   当前模式
   * @param driftScore    当前 drift
   * @param healthScore   当前 health
   * @param enforcementPressure  当前 enforcement 压力
   */
  async stabilizeSystem(
    trace_id: string,
    currentMode: ControlMode,
    driftScore: number,
    healthScore: number,
    enforcementPressure: number,
  ): Promise<StabilizationResult> {
    const startTime = Date.now();
    const actions: string[] = [];
    let modeAfter = currentMode;

    // 1. 评估稳定性
    const assessment = this.assessStability(driftScore, healthScore, currentMode);

    if (assessment.stable) {
      return {
        trace_id,
        mode_before: currentMode,
        mode_after: currentMode,
        actions: ["System stable, no stabilization needed"],
        stabilized: true,
        duration_ms: Date.now() - startTime,
      };
    }

    // 2. reduce enforcement pressure
    if (assessment.pressure_adjustment !== 0) {
      const newPressure = Math.max(0, enforcementPressure + assessment.pressure_adjustment);
      actions.push(`Reduced enforcement pressure: ${enforcementPressure} → ${newPressure}`);
    }

    // 3. increase snapshot dependency（创建新 snapshot 作为恢复基点）
    if (assessment.snapshot_dependency > 0.5) {
      const events = causalKernel.replay(trace_id);
      if (events.length > 0) {
        const { applyEvent } = await import("@/lib/replay/state-reducer");
        const { createInitialState } = await import("@/lib/replay/types");
        let state = createInitialState();
        for (const event of events) {
          state = applyEvent(state, event);
        }
        await persistencePipeline.createSnapshot(trace_id, state, "restore_base");
        actions.push(`Created restore_base snapshot (dependency: ${assessment.snapshot_dependency})`);
      }
    }

    // 4. trigger healing if needed
    if (assessment.needs_healing && !loopMemory.detectInfiniteHealingLoop(5)) {
      modeAfter = "HEALING";
      const healResult = await consistencyAutoHealer.heal(trace_id);
      actions.push(`Triggered healing: ${healResult.final_status} (${healResult.total_attempts} attempts)`);

      if (healResult.final_status === "consistent") {
        modeAfter = "NORMAL";
        actions.push("Healing successful, returning to NORMAL mode");
      } else if (healResult.final_status === "escalated") {
        modeAfter = "LOCKED";
        actions.push("Healing escalated, entering LOCKED mode");
      }
    }

    // 5. 模式调整
    if (modeAfter === currentMode && driftScore > 50) {
      modeAfter = "DEGRADED";
      actions.push("Switched to DEGRADED mode due to high drift");
    }

    const stabilized = modeAfter !== "LOCKED";

    return {
      trace_id,
      mode_before: currentMode,
      mode_after: modeAfter,
      actions,
      stabilized,
      duration_ms: Date.now() - startTime,
    };
  }
}

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export const stabilizer = new Stabilizer();
