/**
 * 知维 OS Self-Healing Engine — 统一门面
 * Zhiwei OS Self-Healing Engine — Unified Facade
 *
 * v5 核心入口：
 * 整合 CrashDetector + AutoRecoveryEngine + ConsistencyAutoHealer + SnapshotCompactor
 */

export { selfHealingKernel, SelfHealingKernel } from "@/lib/self-healing/kernel";
export { crashDetector, CrashDetector } from "@/lib/self-healing/crash-detector";
export { autoRecoveryEngine, AutoRecoveryEngine } from "@/lib/self-healing/recovery-engine";
export { consistencyAutoHealer, ConsistencyAutoHealer } from "@/lib/self-healing/auto-healer";
export { snapshotCompactor, SnapshotCompactor } from "@/lib/self-healing/snapshot-compactor";

export type {
  CrashReport,
  CrashType,
  CrashSeverity,
  CrashEvidence,
  RecoveryStrategy,
  RecoveryResult,
  HealStatus,
  HealAttempt,
  HealResult,
  CompactionStrategy,
  CompactionAction,
  CompactionResult,
  SelfHealingKernelState,
  FullRecoveryResult,
  CrashSimulationConfig,
} from "@/lib/self-healing/types";
