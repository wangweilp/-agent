# Step 25-C：Container/MicroVM Adapter Feasibility Spike

## 1. 本轮目标

对 10 种隔离技术做 paper-tier 可行性评估。**没有启动任何 container/microVM/docker/WASM。没有执行任何代码。**

## 2. Why This Is Not Container Implementation

- 没有启动 container
- 没有调用 docker CLI 或 SDK
- 没有启动 microVM (Firecracker/QEMU/gVisor/Kata)
- 没有启动 WASM runtime (wasmtime/wasmer)
- 没有执行第三方代码
- 没有下载 package
- execute endpoint 仍 blocked
- 所有 descriptor flags 仍是 False

## 3. Feasibility Domain Model

`src/open_platform/sandbox_adapter_feasibility.py`

| Enum | Values |
|------|--------|
| SandboxIsolationTechnology | 10 options: no_execution_baseline through managed_cloud_sandbox |
| FeasibilityStatus | not_assessed, assessed, candidate, rejected, reserved_for_prototype, blocked, fail_closed |
| FeasibilityDecision | accept_as_candidate, reject_for_untrusted_code, reserve_for_future_spike, block_until_hard_gates, fail_closed |
| IsolationStrength | none, low, medium, high, very_high, unknown |
| AdapterCapabilityProfile | 26 fields: technology, isolation_strength, production_fit, windows_dev_fit, 14 capability booleans, execution_enabled (always False), prototype_allowed, recommendation, known_risks, required_hard_gates |
| SandboxAdapterDescriptor | 16 fields: adapter_id, technology, adapter_status (BLOCKED default), 11 enabled flags (ALL False), capability_profile, safety_notes |
| SandboxAdapterFeasibilityAssessment | 22 fields: assessment_id, technology, status, decision, profile, descriptor, checks, 10 no_* safety flags (ALL True) |

**Key invariants**:
- `AdapterCapabilityProfile.execution_enabled` = **always False**
- `SandboxAdapterDescriptor.is_executable()` = **always False**
- `SandboxAdapterDescriptor.can_start_container()` = **always False**
- `SandboxAdapterDescriptor.can_start_microvm()` = **always False**
- `SandboxAdapterDescriptor.can_dispatch()` = **always False**
- `SandboxAdapterFeasibilityAssessment.is_approved_for_execution()` = **always False**

## 4. Isolation Options Assessment (10 technologies)

| # | Technology | Decision | Isolation | Production Fit | Execution | Key Risk |
|---|-----------|----------|-----------|---------------|-----------|----------|
| 1 | No Execution Baseline | ACCEPT_AS_CANDIDATE | VERY_HIGH | LIMITED | ❌ disabled | No execution capability |
| 2 | Disabled Worker | ACCEPT_AS_CANDIDATE | VERY_HIGH | LIMITED | ❌ disabled | No execution path |
| 3 | Local Dry-Run | ACCEPT_AS_CANDIDATE | VERY_HIGH | LIMITED | ❌ disabled | Dry-run only |
| 4 | **Subprocess** | **REJECT_FOR_UNTRUSTED_CODE** | LOW | NOT_FIT | ❌ disabled | os.system/ctypes escape, no seccomp on Windows |
| 5 | Container (Docker) | BLOCK_UNTIL_HARD_GATES | HIGH | GOOD | ❌ disabled | Escape if misconfigured, docker socket, host mount |
| 6 | Rootless Container | ACCEPT_AS_CANDIDATE | VERY_HIGH | GOOD | ❌ disabled | Needs Seccomp/AppArmor, still needs all hard gates |
| 7 | Remote Isolated Worker | RESERVE_FOR_FUTURE_SPIKE | MEDIUM | LIMITED | ❌ disabled | App-level only, network dependency |
| 8 | WASM Runtime | RESERVE_FOR_FUTURE_SPIKE | HIGH | LIMITED | ❌ disabled | Python not fully WASM-compatible |
| 9 | MicroVM (Firecracker) | RESERVE_FOR_FUTURE_SPIKE | VERY_HIGH | STRONG | ❌ disabled | Linux only, high complexity |
| 10 | Managed Cloud Sandbox | RESERVE_FOR_FUTURE_SPIKE | HIGH | GOOD | ❌ disabled | Vendor dependency, cost |

## 5. Subprocess Rejection Rationale

普通 subprocess **不是**不可信第三方代码的安全边界。原因：

- 共享宿主内核和用户态资源——无法内核级隔离
- Python 可通过 `os.system()`, `subprocess.run()`, `ctypes`, `mmap` 逃逸
- Windows 缺少 Linux seccomp/AppArmor/SELinux 等 syscall filter 机制
- 文件系统、网络、环境变量、凭据泄漏风险高
- 无法满足企业级租户隔离要求
- 无 cgroup/namespace 细粒度资源限制
- **结论**: 永久拒绝用于不可信第三方代码执行

## 6. Container Risk Summary

Container 比 subprocess 强很多，但配置错误风险高：

- Docker socket mount → **P0** risk (容器可控制宿主 Docker daemon)
- Privileged container → **P0** risk (近乎宿主 root 权限)
- Host path mount → **P0** risk (读写宿主文件系统)
- Namespace/cgroup/capabilities 配置错误 → 可能逃逸
- Windows Docker Desktop → 不是 Linux 容器，安全模型不同
- Container 不是自动安全——必须配合 15+ hard gates

## 7. Rootless Container Recommendation

Rootless container (Podman / rootless Docker) 作为 **MVP candidate**，但必须满足所有 hard gates：

- No privileged container flag
- No docker socket mount
- No host path mount
- Capability drop ALL
- Seccomp / AppArmor / SELinux profile
- Read-only rootfs
- Ephemeral workspace (tmpfs)
- Network default deny
- Resource limits enforced (cgroup v2)
- Audit log
- Kill switch
- Red-team escape tests

**Rootless container candidate ≠ execution approved。** 当前 execution_enabled=False。

## 8. MicroVM Recommendation

MicroVM (Firecracker) 提供最强隔离 (VERY_HIGH)，但：
- Linux only (no Windows)
- Higher startup overhead (~125ms+)
- Complex orchestration (firecracker-containerd)
- **Recommendation**: RESERVE_FOR_FUTURE_SPIKE — 适合生产 Linux 部署 (Step 25-I+)

## 9. WASM / Remote Worker / Managed Sandbox Notes

- **WASM**: 隔离强度高但 Python 生态兼容性有限 (Pyodide ≠ 所有 Python 包)
- **Remote Worker**: API 级别隔离而非内核级别，适合内部可信 agent
- **Managed Cloud Sandbox**: Vendor dependency + cost + data residency 考虑

## 10. Disabled Adapter Descriptor

所有 descriptor flags 当前仍是 **False**：

```
execution_enabled=False      worker_enabled=False
queue_enabled=False          dispatch_enabled=False
download_enabled=False       network_enabled=False
container_start_enabled=False  microvm_start_enabled=False
subprocess_enabled=False
```

## 11. Usage Metadata

4 new UsageResource enums:
- `SANDBOX_ADAPTER_FEASIBILITY_ASSESS`
- `SANDBOX_ADAPTER_FEASIBILITY_PROFILE`
- `SANDBOX_ADAPTER_FEASIBILITY_DESCRIPTOR`
- `SANDBOX_ADAPTER_FEASIBILITY_BLOCKED`

Metadata excludes: raw_key, key_hash, secrets, package contents, package_url, repository_url, raw input_payload, local_path, stdout, stderr, exit_code.

## 12. Non-Execution Guarantees

- ❌ 不下载 package / 不解压 package / 不执行 package_url / entrypoint
- ❌ 不联网 / 不读 secrets / 不读 local path / 不 open file
- ❌ 不启动 subprocess / container / microVM / WASM / docker
- ❌ 不创建 worker / queue / dispatch job
- ❌ execute draft endpoint 仍 blocked
- ❌ DisabledSandboxWorker 仍 blocked
- ❌ SandboxExecutionRecord.is_executable() 始终 false
- ❌ is_approved_for_execution() 始终 false

## 13. Known Issues

- No container implementation
- No rootless container proof
- No microVM implementation
- No WASM runtime
- No remote worker
- No worker queue
- No package download
- No execution success path
- No network/filesystem/secrets enforcement proof yet
- All intentional Step 25-D+ deferrals

## 14. Next Step

**Step 25-D：Package Download Quarantine Prototype with Explicit Admin Gate**

Not started. Do not begin Step 25-D.
