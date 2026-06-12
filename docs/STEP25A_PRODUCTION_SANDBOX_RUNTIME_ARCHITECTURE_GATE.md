# Step 25-A Production Sandbox Runtime Architecture Gate + Isolation Strategy

## 1. Purpose

Step 25-A 是生产级 sandbox runtime 的架构门禁和隔离策略设计，**不是实现阶段**。

- Step 25-A 不执行第三方代码
- Step 25-A 不启动 container/microVM
- Step 25-A 不下载 package
- Step 25-A 不修改 `/runtime/agents/{id}/execute` 的 blocked 语义
- Step 25-A 只决定后续怎么安全地逐步进入生产级隔离

## 2. Step 24 Baseline

### 已完成能力 (24-A to 24-K)

| Capability | Status | Execution Boundary |
|------------|--------|--------------------|
| Threat model (34 threats) + execution principles (20) | ✅ | Design only |
| PackageArtifact metadata store + quarantine + audit | ✅ | No download |
| Checksum verifier (sha256+) + Signature verifier (metadata) | ✅ | Controlled input only |
| RuntimeExecutionPlan (20 preflight checks) + Planner | ✅ | Not dispatchable |
| SandboxWorker interface + DisabledStub (fail-closed) | ✅ | Always blocked |
| Policy→WorkerConfig translator (5 sub-configs) | ✅ | Config ≠ permission |
| LocalDevSandbox prototype (dry-run only) | ✅ | Not real execution |
| Runtime execution API (plan endpoints + draft blocked) | ✅ | Execute always blocked |
| 168 security escape guard tests (9 categories) | ✅ | No escape path |
| Demo script + 25 Q&A + architecture summary | ✅ | Docs only |
| Final regression gate (1997 tests, 0 failures) | ✅ | Verification only |

### 明确没有完成的能力

- ❌ No production sandbox
- ❌ No external code execution
- ❌ No package download / unzip
- ❌ No container / microVM
- ❌ No worker queue / job dispatch
- ❌ No real cryptographic signature verification
- ❌ No dependency / CVE scan
- ❌ No data broker / secret broker / network enforcer
- ❌ No kill switch implementation

### 当前仍然 blocked 的执行边界

- `/runtime/agents/{id}/execute` — always returns blocked
- `is_execution_allowed()` — always returns False
- `is_successful_execution()` — always returns False
- `is_dispatchable()` — always returns False
- `is_real_execution()` — always returns False
- DisabledSandboxWorker — default, always BLOCKED
- LocalDevSandboxPrototypeWorker — dry-run only, disabled by default
- Worker Registry — only DisabledSandboxWorker registered

## 3. Production Sandbox Problem Statement

在允许 production sandbox 执行第三方代码之前，必须回答以下 17 个问题：

| # | Question | Answer Strategy |
|---|----------|-----------------|
| 1 | 不可信代码来自哪里？ | Submission.package_url → quarantine download (25-D) |
| 2 | 谁允许下载？ | Admin explicit gate, not auto (25-D) |
| 3 | 谁验证包？ | Checksum actual vs declared + signature crypto (25-C/E) |
| 4 | 谁批准执行？ | Admin approval + plan verification + policy enforcement |
| 5 | 谁决定 worker 类型？ | Sandbox policy sandbox_level → adapter selection |
| 6 | 代码在哪运行？ | Isolated container/microVM, not FastAPI process |
| 7 | 代码能访问什么数据？ | Default none; DataAccessBroker if scope allows |
| 8 | 代码能不能联网？ | Default deny; allowlist + NetworkPolicyEnforcer |
| 9 | 代码能不能访问文件？ | Ephemeral workspace only; no host mount |
| 10 | 代码能不能拿 secrets？ | Default deny; scoped broker only, short-lived tokens |
| 11 | 超时怎么 kill？ | Worker SIGTERM → grace → SIGKILL |
| 12 | 资源超限怎么处理？ | cgroup/container limits enforced at OS level |
| 13 | 输出怎么 sanitize？ | Truncate + redact secrets + strip tenant IDs |
| 14 | 审计怎么记录？ | Append-only RuntimeAuditLogStore |
| 15 | 租户怎么隔离？ | Per-tenant worker namespace; no cross-tenant access |
| 16 | 全局 kill switch 怎么生效？ | agent/tenant/global levels; worker polls every 5s |
| 17 | 出现逃逸迹象怎么 fail closed？ | Kill switch auto-activates; incident logged; tenant suspended |

## 4. Threat Model Update (30 new threats)

### P0 — Critical (15 threats)

| # | Threat | Impact | Existing Step 24 Protection | Missing Protection | Required Isolation Control |
|---|--------|--------|---------------------------|-------------------|---------------------------|
| T1 | Container escape via kernel exploit | Host root access | No container exists | No container security | Seccomp + AppArmor + no-new-privileges + read-only rootfs |
| T2 | Docker socket mount escape | Container breakout to host | No docker socket exists | No docker mount block | Explicit deny `/var/run/docker.sock` in container config |
| T3 | Privileged container escape | Full host access | No container exists | No privileged flag block | `--privileged=false` enforced; capability drop ALL |
| T4 | Host path mount data exfiltration | Read host filesystem | No container exists | No mount validation | Only tmpfs/ephemeral mounts; no host path binding |
| T5 | Namespace escape (PID/net/ipc) | Cross-container access | No container exists | No namespace isolation | Separate user/PID/net/IPC/mount namespaces per execution |
| T6 | Network egress data exfiltration via DNS | Bypass HTTP block via DNS tunneling | No network in dry-run | No DNS egress control | Container-level DNS filtering + allowlist only |
| T7 | SSRF via metadata service (169.254.169.254) | Cloud credential theft | Static URL validation | No runtime network block | iptables/nftables block metadata IP at container level |
| T8 | Secrets exfiltration via environment variables | Leak API tokens, JWT keys | No secrets in requests | No env injection block | Never pass secrets as env vars; broker only |
| T9 | Cross-tenant data leakage via shared volume | Tenant-A reads Tenant-B data | No shared volumes | No volume isolation | Per-tenant tmpfs; no shared volumes |
| T10 | Artifact tampering after verification | Execute modified code after checksum pass | No download/execute | No TOCTOU protection | Content-addressable storage; verify at execution time |
| T11 | Symlink traversal in extracted archive | Read arbitrary host files | No extraction | No extraction guard | `realpath()` check + no symlink outside workspace |
| T12 | Path traversal in extracted archive (zip slip) | Write to arbitrary host paths | No extraction | No zip-slip guard | Reject entries with `../` in path |
| T13 | Kill switch bypass via worker cache | Worker continues after kill activated | No kill switch | No worker poll mechanism | Worker checks kill switch before each I/O operation |
| T14 | Audit log tampering by execution code | Delete/modify execution audit trail | No audit store | No append-only storage | Append-only; checksum chain; separate DB |
| T15 | AgentRegistry pollution via namespace collision | Registration with forged agent_id | Architectural separation | No runtime enforcement | AgentRegistry permanently closed to external agents |

### P1 — High (10 threats)

| # | Threat | Impact | Required Isolation Control |
|---|--------|--------|---------------------------|
| T16 | Memory exhaustion (OOM) via large allocation | Worker crash, host slowdown | cgroup v2 memory.max; OOM killer |
| T17 | Disk exhaustion via large output | Ephemeral workspace full | tmpfs with size limit; output truncation |
| T18 | CPU exhaustion via infinite loop | Starve other tenants | CPU quota via cgroup; hard timeout |
| T19 | Dependency confusion (internal package name) | Install malicious internal-named package | Dependency namespace validation; allowlist |
| T20 | Malicious dependency install (backdoor) | Runtime code execution with elevated context | Static dependency scan before execution |
| T21 | Archive bomb (zip of 1TB from 1KB) | Disk exhaustion during extraction | Max uncompressed size check before extraction |
| T22 | Queue poisoning (inject fake job) | Execute unauthorized code | Queue auth; job signature verification |
| T23 | Job replay (re-run old execution request) | Repeat execution without re-approval | Job nonce/expiry; one-time execution tokens |
| T24 | Worker impersonation (fake worker claiming execution) | False execution records | Worker identity verification; mTLS between queue and worker |
| T25 | Policy translator bypass (downgrade attack) | Execute with weaker policy than assigned | Policy version pinning; execution refs policy version |

### P2 — Medium (5 threats)

| # | Threat | Impact | Required Isolation Control |
|---|--------|--------|---------------------------|
| T26 | Side-channel timing attack | Infer other tenant data via execution time | Coarse-grained timing; random jitter |
| T27 | Worker log injection | Fake audit entries via stdout | Structured JSON logging; no free-form parsing |
| T28 | Metadata service DNS rebinding | Bypass IP block via DNS | DNS resolve + IP re-check at connect time |
| T29 | Shared kernel attack surface | Cross-tenant kernel exploit | MicroVM when isolation requirement demands it |
| T30 | Supply-chain: build tool compromise | Malicious code injected during pip install | Pinned dependency versions + lockfile verification |

## 5. Isolation Options Comparison

| Option | Isolation Strength | Windows Dev Fit | Production Fit | Complexity | Risk | 25 Recommendation |
|--------|-------------------|-----------------|---------------|------------|------|-------------------|
| No Execution Baseline | ★★★★★ | ✅ Full | No execution | Zero | No execution capability | Maintain as fallback |
| Disabled Worker | ★★★★★ | ✅ Full | Fail-closed gate | Zero | No execution path | Keep as default |
| Local Dry-run Prototype | ★★★★★ | ✅ Full | Preview only | Low | No real execution | Already done (24-G) |
| Sandboxed Subprocess | ★★☆☆☆ | ⚠️ No seccomp | **Not safe** | Low | Escape via os.system/ctypes | **REJECT for untrusted code** |
| Container Runtime (Docker) | ★★★★☆ | ⚠️ Docker Desktop | MVP viable | Medium | Config errors can escape | **Recommended MVP** |
| Rootless Container Runtime | ★★★★★ | ⚠️ Podman/WSL2 | Production viable | Medium-High | Podman≠Docker on Windows | **Recommended Production** |
| Remote Isolated Worker Service | ★★★☆☆ | ✅ | API-level isolation | Medium | Not kernel-level isolation | Internal trusted agents only |
| WASM Runtime | ★★★★☆ | ✅ wasmtime | Limited ecosystem | High | Python not fully supported | Future direction |
| MicroVM Runtime (Firecracker) | ★★★★★ | ❌ Linux only | Maximum isolation | High | Not on Windows | Production (Linux servers) |
| Managed Cloud Sandbox | ★★★★★ | ✅ API-based | Ops simplicity | Low-Medium | Vendor dependency | Future option |

### Key Conclusion

**普通 subprocess 永远不能作为不可信第三方代码的安全边界。**

Step 25 推荐渐进路线：
1. **25-B**: Sandbox Execution Store + Audit Model (基础设施)
2. **25-C**: Container/MicroVM Feasibility Spike (技术验证)
3. **25-D**: Package Download Quarantine (显式 admin gate)
4. **25-E**: Archive Extraction Guard (防 zip-slip/path-traversal)
5. **25-F**: Worker Queue Design, Disabled by Default
6. **25-G**: Network/Filesystem/Secrets Enforcement Proof
7. **25-H**: Limited Trusted Fixture Execution (仅受控 fixture，非第三方代码)
8. **25-I**: Red-Team Escape Tests

## 6. Recommended Production Architecture

以下 20 个组件为 Step 25 完整蓝图。Step 25-A 只设计，不实现。

| Component | Purpose | Must Exist Before Execution? | Step 24 Status | Fail-Closed When Missing |
|-----------|---------|------------------------------|----------------|--------------------------|
| SandboxExecutionStore | Persist execution request/result/status | Yes | Not started | Cannot execute |
| SandboxExecutionAuditLogStore | Append-only immutable audit log | Yes | Not started | Cannot execute |
| SandboxJobQueue | Queue jobs for dispatch, disabled default | Yes | Not started | Cannot execute |
| WorkerLeaseStore | Worker acquires lease before execution | Yes | Not started | Cannot execute |
| WorkerHeartbeatStore | Worker sends heartbeat during execution | Yes | Not started | Cannot execute |
| ContainerSandboxAdapter | Docker/Podman container isolation adapter | Conditional | Not started | Falls back to disabled |
| MicroVMSandboxAdapter | Firecracker microVM adapter | No (future) | Not started | Falls back to container |
| WASMSandboxAdapter | wasmtime/wasmer adapter | No (future) | Not started | Falls back to container |
| PackageDownloadQuarantineService | Download + quarantine directory | Yes | Not started | Cannot download |
| ArtifactExtractionGuard | Zip-slip/symlink/path traversal check | Yes | Not started | Cannot extract |
| FilesystemPolicyEnforcer | Enforce read/write paths, no host mount | Yes | Not started | Deny all FS access |
| NetworkPolicyEnforcer | Enforce egress rules at container level | Yes | Not started | Deny all network |
| SecretBroker | Scoped, short-lived credentials | Conditional | Not started (24 designed) | Deny all secrets |
| DataAccessBroker | Controlled data access for code | Conditional | Not started (24 designed) | Deny all data access |
| OutputSanitizer | Truncate, redact, strip tenant IDs | Yes | Not started | Redact all output |
| KillSwitchService | agent/tenant/global kill switch | Yes | Not started | Cannot execute |
| RuntimeIncidentStore | Track security incidents | No (post-MVP) | Not started | Log to audit |
| RuntimeRedTeamTestSuite | Escape attempt tests | Yes (pre-execution) | Not started | Cannot execute |
| PolicyEnforcementTranslator | Policy→Worker config (exists in 24-F) | Yes | ✅ Done | Fail closed |
| RuntimeExecutionPlanner | Preflight checks (exists in 24-D) | Yes | ✅ Done | Fail closed |

## 7. Execution Lifecycle Design (Future, Not Implemented)

```
1. Admin requests execution plan (24-D: exists, not dispatchable)
2. Plan must pass all preflight checks
3. Artifact must be declared (24-B: exists)
4. Package download requires explicit admin gate (25-D)
5. Downloaded artifact → quarantine directory (25-D)
6. Checksum verification AFTER download (25-C)
7. Cryptographic signature verification (25-C)
8. Archive extraction with zip-slip/symlink/path traversal guard (25-E)
9. Dependency/CVE scan (25-C)
10. Policy → WorkerConfig translation (24-F: exists)
11. Worker queue job creation (disabled by default) (25-F)
12. Worker lease acquisition (25-F)
13. Sandbox start: container/microVM with policy limits (25-C/G)
14. Runtime heartbeat periodic check (25-F)
15. Kill switch poll every 5s (25-G)
16. Output capture: stdout/stderr pipe (25-G)
17. Output sanitizer: truncate, redact, strip (25-G)
18. Audit log: start/stop/result/timeout/kill (25-B)
19. Result persisted to SandboxExecutionStore (25-B)
20. Tenant-safe sanitized response returned (25-B)
```

**Step 25-A 只是生命周期设计，不是实现。Steps 1-3 在 24 已有，Steps 4+ 需要 25-B to 25-H。**

## 8. Hard Gates Before Any Real Execution

任何真实执行（包括 trusted fixture）必须满足以下 20 个 hard gates:

1. ✅ Explicit admin execution approval (not auto)
2. ⏸ Package downloaded into quarantine (25-D)
3. ⏸ Checksum verified against declared value (25-C)
4. ⏸ Real cryptographic signature verification OR explicit admin override (25-C)
5. ⏸ Dependency/CVE scan decision recorded (25-C)
6. ⏸ Archive extraction guard passed: no zip-slip/symlink/path-traversal (25-E)
7. ⏸ SandboxPolicy enforceable by current worker type (24-F exists)
8. ⏸ NetworkPolicyEnforcer: egress default deny, allowlist only (25-G)
9. ⏸ SecretBroker: default deny, no raw env injection (25-G)
10. ⏸ FilesystemPolicyEnforcer: no host path mount, ephemeral workspace only (25-G)
11. ⏸ No docker socket mount in container (25-C/G)
12. ⏸ No privileged container flag (25-C/G)
13. ⏸ Worker queue disabled by default until admin explicitly enables (25-F)
14. ⏸ KillSwitchService exists and tested (25-G)
15. ⏸ RuntimeAuditLogStore: append-only, checksum chain (25-B)
16. ⏸ Tenant isolation verified by test (25-I)
17. ⏸ OutputSanitizer tested with secret patterns (25-G)
18. ⏸ Red-team escape tests passed (25-I)
19. ⏸ `/runtime/agents/{id}/execute` still blocked until gate explicitly opens
20. ⏸ Step 25 final gate (25-K) passed

## 9. Data / Network / Secrets / Filesystem Strategy

### Data Access
- Developer code cannot access DB directly → deny by default
- Developer code cannot access vector store directly → deny by default
- Developer code cannot access memory store directly → deny by default
- All data access through DataAccessBroker → scoped, audited
- DataAccessPolicyConfig.mode=DENY_ALL until broker implemented

### Network
- Default deny egress at container/OS level
- Allowlist only (SandboxPolicy.allowed_domains)
- Block: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.169.254, 127.0.0.0/8, ::1
- DNS egress considered as network access
- No raw sockets / no ICMP tunnels

### Secrets
- Default deny — no secrets injected
- If policy allows: scoped broker only, short-lived tokens (TTL ≤ execution timeout)
- Never environment variables
- Audit every secret access
- Auto-revoke after execution completes or times out

### Filesystem
- Ephemeral workspace only (tmpfs)
- No host path mount
- No docker socket mount
- Read-only package mount after extraction guard
- Symlink escape blocked (realpath check)
- Path traversal blocked (reject `../`)
- Output quota enforced (max_output_bytes)
- Workspace deleted immediately after execution

## 10. Step 25 Implementation Plan

| Step | Name | Status | Goal | Forbidden |
|------|------|--------|------|-----------|
| 25-A | Architecture Gate + Isolation Strategy | ✅ | Design doc, threat model | Implement execution |
| 25-B | Sandbox Execution Store + Audit Model | ⏸ | Store/store/audit tables | Package download/execution |
| 25-C | Container/MicroVM Feasibility Spike | ⏸ | Tech validation, not production | Execute third-party code |
| 25-D | Package Download Quarantine | ⏸ | Download with admin gate | Auto-download; execute |
| 25-E | Archive Extraction Guard | ⏸ | Zip-slip/symlink/traversal guard | Execute extracted code |
| 25-F | Worker Queue Design, Disabled | ⏸ | Queue model, disabled by default | Dispatch jobs |
| 25-G | Network/FS/Secrets Enforcement Proof | ⏸ | Enforcement test with safe fixture | Execute untrusted code |
| 25-H | Limited Trusted Fixture Execution | ⏸ | Controlled fixture only | Third-party code |
| 25-I | Red-Team Escape Tests | ⏸ | Escape attempt tests | Production execution |
| 25-J | Demo + Documentation | ⏸ | End-to-end demo | Claim production ready |
| 25-K | Final Regression Gate | ⏸ | Full regression pass | New capability |

## 11. Step 25-B Admission Criteria

Step 25-B is **Sandbox Execution Store + Audit Model** only.

Admission requires:
- ✅ Step 25-A doc completed
- ✅ No execution implemented in 25-A
- ✅ ROADMAP updated
- ✅ Step 24 blocked behavior unchanged
- ✅ Execute endpoint still blocked
- ✅ No worker queue
- ✅ No package download
- ✅ No subprocess/container started

**Step 25-B is limited to data model + SQLite store + audit event model. No execution. No download. No worker.**

## 12. Known Issues

- No production sandbox
- No real worker queue / job dispatch
- No package download / unzip / extraction
- No real cryptographic signature verification
- No dependency/CVE scan
- No container/microVM adapter implementation
- No data/secret/network broker implementation
- No kill switch implementation
- No runtime execution success path
- Windows Docker Desktop ≠ Linux container parity
- Podman on Windows requires WSL2

## 13. Final Positioning

**Step 25-A moves the project from "runtime safety preparation" (Step 24) into "production sandbox design" (Step 25), but does NOT enable code execution.**

All execution entrypoints remain fail-closed. All Step 24 safety guarantees remain intact.
