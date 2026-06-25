/**
 * 知维 OS Adaptive Loop Scheduler — 自适应循环调度器
 * Zhiwei OS Adaptive Loop Scheduler
 *
 * 核心算法：
 * - drift ↑ → loop faster（间隔减小）
 * - health ↑ → loop slower（间隔增大）
 * - 自适应强度（adaptivity）控制响应速度
 *
 * 调度公式：
 *   interval = base_interval * (1 - adaptivity * drift_factor)
 *   drift_factor = min(drift_score / 100, 1)
 *
 * 约束：
 *   min_interval_ms <= interval <= max_interval_ms
 */

import type { LoopSchedulerConfig } from "@/lib/kernel/control-loop/types";
import { DEFAULT_SCHEDULER_CONFIG } from "@/lib/kernel/control-loop/types";
import type { ControlState } from "@/lib/kernel/control-loop/types";

// ═══════════════════════════════════════════════════════════════
// AdaptiveLoopScheduler — 自适应调度器
// ═══════════════════════════════════════════════════════════════

export class AdaptiveLoopScheduler {
  private config: LoopSchedulerConfig;
  private timer: ReturnType<typeof setInterval> | null = null;
  private callback: (() => Promise<void>) | null = null;

  constructor(config: Partial<LoopSchedulerConfig> = {}) {
    this.config = { ...DEFAULT_SCHEDULER_CONFIG, ...config };
  }

  /**
   * 配置调度器
   */
  configure(config: Partial<LoopSchedulerConfig>): void {
    this.config = { ...this.config, ...config };
  }

  /**
   * 计算下一个间隔 — 自适应核心算法
   *
   * @param driftScore   当前 drift_score（0-100）
   * @param healthScore  当前 health_score（0-100）
   * @returns 下一个间隔（ms）
   */
  computeNextInterval(driftScore: number, healthScore: number): number {
    const { base_interval_ms, min_interval_ms, max_interval_ms, adaptivity } = this.config;

    // drift 因子：drift 越高，间隔越小
    const driftFactor = Math.min(driftScore / 100, 1);

    // health 因子：health 越高，间隔越大
    const healthFactor = Math.min(healthScore / 100, 1);

    // 综合调整：drift 加速 + health 减速
    const acceleration = adaptivity * driftFactor;        // 0 ~ adaptivity
    const deceleration = adaptivity * healthFactor * 0.5;  // 0 ~ adaptivity/2

    // 净加速因子
    const netAdjustment = acceleration - deceleration;

    // 计算间隔
    let interval = base_interval_ms * (1 - netAdjustment);

    // 应用约束
    interval = Math.max(min_interval_ms, Math.min(max_interval_ms, interval));

    return Math.round(interval);
  }

  /**
   * 启动调度器
   *
   * @param callback  每次循环执行的回调
   * @param initialState  初始控制状态
   */
  start(callback: () => Promise<void>, initialState: ControlState): void {
    if (this.timer) {
      console.warn("[AdaptiveScheduler] already running");
      return;
    }

    this.callback = callback;
    const initialInterval = this.computeNextInterval(
      initialState.drift_score,
      initialState.health_score,
    );

    this.scheduleNext(initialInterval);
  }

  /**
   * 停止调度器
   */
  stop(): void {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
    this.callback = null;
  }

  /**
   * 重新调度（根据当前状态调整间隔）
   */
  reschedule(currentState: ControlState): void {
    if (!this.callback) return;

    const newInterval = this.computeNextInterval(
      currentState.drift_score,
      currentState.health_score,
    );

    // 仅在间隔变化超过 20% 时重新调度
    if (Math.abs(newInterval - currentState.current_interval_ms) / currentState.current_interval_ms > 0.2) {
      if (this.timer) {
        clearInterval(this.timer);
      }
      this.scheduleNext(newInterval);
    }
  }

  /**
   * 是否运行中
   */
  isRunning(): boolean {
    return this.timer !== null;
  }

  /**
   * 获取配置
   */
  getConfig(): LoopSchedulerConfig {
    return { ...this.config };
  }

  // ─────────────────────────────────────────────────────────────
  // 内部方法
  // ─────────────────────────────────────────────────────────────

  private scheduleNext(intervalMs: number): void {
    if (!this.callback) return;

    this.timer = setInterval(async () => {
      if (this.callback) {
        try {
          await this.callback();
        } catch (err) {
          console.error("[AdaptiveScheduler] loop callback error:", err);
        }
      }
    }, intervalMs);
  }
}

// ═══════════════════════════════════════════════════════════════
// 单例导出
// ═══════════════════════════════════════════════════════════════

export const adaptiveScheduler = new AdaptiveLoopScheduler();
