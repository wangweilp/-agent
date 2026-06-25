/**
 * 知维 OS Kernel Control Loop — 统一门面
 * Zhiwei OS Kernel Control Loop — Unified Facade
 *
 * v6 核心入口：
 * 唯一的 runtime kernel — OSControlLoop
 *
 * 架构：
 * ┌─────────────────────────────────────────┐
 * │  OSControlLoop（唯一 runtime kernel）   │
 * │  ┌─────────────────────────────────┐    │
 * │  │  OBSERVE → DECIDE → ENFORCE    │    │
 * │  │  → RECONCILE → HEAL → COMPACT  │    │
 * │  │  → REPLAY_VERIFY → OBSERVE     │    │
 * │  └─────────────────────────────────┘    │
 * ├─────────────────────────────────────────┤
 * │  AdaptiveLoopScheduler                  │
 * │  Stabilizer                             │
 * │  LoopMemory                             │
 * └─────────────────────────────────────────┘
 */

export { osControlLoop, OSControlLoop } from "@/lib/kernel/control-loop/control-loop";
export { adaptiveScheduler, AdaptiveLoopScheduler } from "@/lib/kernel/control-loop/scheduler";
export { stabilizer, Stabilizer } from "@/lib/kernel/control-loop/stabilizer";
export { loopMemory, LoopMemory } from "@/lib/kernel/control-loop/loop-memory";

export type {
  ControlMode,
  ControlState,
  LoopStage,
  ObserveResult,
  DecisionResult,
  EnforcementStageResult,
  ReconcileResult,
  HealingStageResult,
  CompactionStageResult,
  ReplayVerifyResult,
  StateDelta,
  LoopCycle,
  ControlLoopHistory,
  LoopSchedulerConfig,
  StabilityAssessment,
  StabilizationResult,
} from "@/lib/kernel/control-loop/types";
