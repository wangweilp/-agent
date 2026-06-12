# Step 24-A：Real Sandbox Runtime Architecture Audit + Execution Boundary Design

## 1. 本阶段目标

Step 24-A **只做真实沙箱运行时架构审计与执行边界设计**，不实现真实执行。

产出：威胁模型（34 threats）、执行边界原则（20 条）、沙箱技术比较（7 方案）、推荐目标架构（15 组件）、数据流设计、数据模型/API 草案、policy enforcement 设计、分阶段实施路线（24-B 到 24-K）。

**不写一行执行代码。不下载/解压/执行 package。不联网。不创建 worker。**

---

## 2. Step 23 基线能力

### 2.1 已具备能力总结

- **API Key Auth** — X-Cognitive-API-Key middleware, 12 scopes, 8 forbidden scopes, admin routes denied
- **Manifest SDK/Schema** — JSON Schema v1, Python validation library, manifest-only entrypoint
- **Package Validation** — 10-step static pipeline, no download/unzip/execution/network
- **Sandbox Policy** — 3 builtin system-managed policies, 13-field model, static rule evaluation, is_execution_allowed()
- **Runtime Binding** — PENDING→ENABLED→DISABLED→SUSPENDED, MVP gate, sandbox policy assignment, eligibility engine (8 codes)
- **Simulation Runtime** — 9-step deterministic dry-run, no package/network/data access
- **Runtime Admin** — API + Frontend: adapters/bindings/policies/guide
- **Security Tests** — 77 Step23 + 678 Open Platform + 1338 backend regression, all passed

### 2.2 当前 RuntimeAdapter 类型和状态

| adapter_type | adapter_id | status | sandbox_required | MVP allowed | 实际能力 |
|---|---|---|---|---|---|
| manifest_only | rtadp_manifest_only | active | No | Yes | 纯数据映射，不执行 |
| simulation | rtadp_simulation | beta | No | Yes | 9-step dry-run |
| http_webhook | rtadp_http_webhook | disabled | Yes | No | 预留 |
| sandboxed_process | rtadp_sandboxed_process | disabled | Yes | No | 预留 |
| container | rtadp_container | disabled | Yes | No | 预留 |

### 2.3 当前 RuntimeBinding 状态机

PENDING → ENABLED ⇄ DISABLED; ENABLED → SUSPENDED (resume → ENABLED)

- enable: 检查 adapter active + MVP allowed + sandbox_policy
- enable 不执行代码 — SQLite UPDATE 操作
- binding 不创建 worker — 纯数据操作

### 2.4 当前 SandboxPolicy 能表达什么

13 字段沙箱边界：sandbox_level / allow_network / allowed_domains / allow_filesystem_read / allow_filesystem_write / allowed_paths / allow_secrets / allowed_secret_names / max_timeout_ms / max_memory_mb / max_cpu_percent / max_output_bytes / max_requests_per_minute

静态规则评估（test_policy），is_execution_allowed(): no_execution→False, simulation_only→False

**不包括**：容器配置、cgroup/seccomp profile、capability drop、user namespace、read-only rootfs

### 2.5 当前 PackageValidation 能验证什么

URL format / checksum declared / signature declared / manifest consistency / dependencies declared / runtime sandbox block

**不验证**：真实 checksum 哈希、签名有效性、依赖 CVE scan、package 内容安全

### 2.6 当前 SimulationRuntime 做到什么

9-step sequential dry-run: marketplace agent→publisher type→metadata→installation→permissions→binding→adapter→scope→simulated response

Deterministic mock output, 不调用 AgentRuntime, 不注册 AgentRegistry, 不下载/执行 package

### 2.7 当前 AgentRuntime / AgentRegistry 是否适合承载 developer agent

**不适合，且当前明确禁止。**

- AgentRegistry: in-memory Python class instances, PEOR loop, shared process space
- Developer Agent: untrusted third-party code, Manifest + package_url, 不是 Python 类
- **结论**：Developer Agent 永远不注册到 AgentRegistry，走独立 Sandbox Runtime path

### 2.8 当前缺少哪些真实 sandbox 前置能力

| 缺失能力 | 严重性 |
|---------|--------|
| Package Artifact Store | P0 |
| Package Quarantine | P0 |
| Checksum Verification (SHA256 actual vs declared) | P0 |
| Signature Verification (minisign/cosign/GPG) | P0 |
| Dependency Scanner (静态 CVE/恶意依赖) | P1 |
| Sandbox Worker Interface (disabled stub) | P0 |
| Container/MicroVM Sandbox Infrastructure | P0 |
| Policy Enforcement Translator | P0 |
| Data Access Broker | P0 |
| Secret Broker | P0 |
| Network Policy Enforcer | P0 |
| Runtime Audit Log | P0 |
| Kill Switch (agent/tenant/global) | P0 |
| Runtime Result Sanitizer | P1 |

### 2.9 Step 24-A 最小文档改动范围

- 新增: `docs/STEP24A_REAL_SANDBOX_RUNTIME_ARCHITECTURE_AUDIT.md`
- 修改: `docs/ROADMAP.md`（新增 Step 24 区域）

### 2.10 本阶段禁止实现的内容

不实现任何 sandbox runtime 代码、不启动 subprocess/container、不下载/解压/执行 package、不执行 entrypoint、不联网、不读取 secrets、不调用 AgentRuntime 执行 developer agent、不注册 developer agent 到 AgentRegistry、不创建 worker/执行队列/真实 execution API、不修改 enable binding 语义、不让 sandbox policy 变成执行开关、不进入 Step 24-B 开发。

---

## 3. 真实 Sandbox Runtime 的核心问题（13 问）

| Q | 问题 | 答案 |
|---|------|------|
| 1 | 代码从哪来？ | Submission.package_url → artifact store |
| 2 | 谁允许下载？ | Admin with artifact:download scope |
| 3 | 谁验证？ | ChecksumVerifier + SignatureVerifier + DependencyScanner |
| 4 | 谁批准执行？ | Review→Publish→Install→Binding→Policy→Enforcer(fail closed) |
| 5 | 谁决定可运行？ | EligibilityResult + PolicyEnforcer.can_enforce() |
| 6 | 在哪运行？ | 隔离 worker（不在 FastAPI 进程，不在 PEOR loop） |
| 7 | 能访问什么？ | Default none；DataAccessBroker 受控 |
| 8 | 是否联网？ | Default deny；policy allow_network + allowed_domains |
| 9 | 文件/secrets？ | Default deny；broker 受控提供 |
| 10 | 超时 kill？ | Worker SIGTERM → grace 5s → SIGKILL |
| 11 | 审计？ | RuntimeAuditLogStore append-only + checksum chain |
| 12 | 多租户隔离？ | Worker namespace per tenant；ephemeral workspace per execution |
| 13 | Kill switch？ | agent/tenant/global 三级；worker poll every 5s |

---

## 4. Threat Model (34 threats)

### 威胁分类

| 类别 | 数量 | 最高级别 |
|------|------|---------|
| RCE/Escape | 5 | P0 |
| Data Leak/Exfil | 4 | P0 |
| Supply Chain | 4 | P0 |
| AuthN/AuthZ Bypass | 4 | P0 |
| Resource Exhaustion/DoS | 4 | P1 |
| Audit/Compliance | 3 | P1 |
| Confusion/Replay | 3 | P1 |
| Info Disclosure | 2 | P2 |

### P0 — Critical (15 threats)

| # | Threat | Impact | Current Step23 Protection | Missing Protection | Step24 Mitigation |
|---|--------|--------|--------------------------|-------------------|-------------------|
| T1 | **RCE Escape: subprocess breakout** | Attacker gains host shell access | No execution allowed | No execution sandbox | Container/microVM; no shell; cap drop; seccomp; read-only rootfs |
| T2 | **Host filesystem read** | Read /etc/passwd, .env, secrets, source code | No execution allowed | No filesystem isolation | Ephemeral workspace only; no host mount; seccomp block open/openat |
| T3 | **Secrets exfiltration via env/fs** | Leak DATABASE_URL, JWT_SECRET, API keys | No execution; secrets never injected | No SecretBroker | Secrets only via broker; never env vars; time-limited credentials |
| T4 | **Cross-tenant data exfiltration** | Agent for tenant-A reads tenant-B data | Tenant isolation in API layer | No execution-level isolation | Worker-per-tenant namespace; DB tenant-scoped views |
| T5 | **SSRF via network-allowlisted adapter** | Access internal services, metadata, localhost | Network denied (simulation only) | No network enforcement | Deny 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.169.254, localhost |
| T6 | **Package URL redirect attack** | Malicious package from lookalike domain | Static URL validation (HTTPS, domain) | No TLS pinning; no redirect check | Follow redirects with domain re-check; block >3 hops |
| T7 | **Package malicious dependency** | Backdoor/ransomware in dependency | Dependency declared check (format only) | No CVE scan | DependencyScanner (static CVE + malware sig DB); quarantine first |
| T8 | **Review bypass: direct runtime enable** | Attacker enables binding without review | Enable requires admin + MVP allowed | No review gate on enable | Enable must verify submission approved+published |
| T9 | **Runtime binding bypass** | Direct execution without binding check | Binding check in eligibility engine | No execution API | Execution API verifies binding at call time |
| T10 | **Sandbox policy bypass** | Weak policy allows execution escape | Policy validation (static rules) | No enforcement parity | PolicyEnforcer fail closed; restricted/isolated require container |
| T11 | **API Key privilege escalation** | Forged scopes access admin routes | API Key admin route deny | No runtime admin scope | Double-check auth source at every layer |
| T12 | **AgentRegistry pollution** | Developer agent gains process-level access | No developer agent registration | Not architectural separation | Registry permanently closed to external agents |
| T13 | **AgentRuntime trust boundary collapse** | Developer code runs in PEOR loop | No developer agent in PEOR | PEOR has no sandbox | Developer agents never run in AgentRuntime; separate worker |
| T14 | **Container escape: privileged flag** | --privileged container with host mount | No container exists | No container security policy | No privileged; no docker socket; no CAP_SYS_ADMIN |
| T15 | **Execution result data leak** | Output contains other tenant secrets/data | No execution | No output sanitization | RuntimeResultSanitizer: truncate, redact, strip tenant IDs |

### P1 — High (14 threats)

| # | Threat | Impact | Step24 Mitigation |
|---|--------|--------|-------------------|
| T16 | Timeout bypass: infinite loop | DoS | Worker SIGKILL + audit |
| T17 | Memory exhaustion: OOM | Host crash | cgroup v2 memory.max |
| T18 | Disk exhaustion: large output | Worker crash | tmpfs size limit; output truncation |
| T19 | Rate limit bypass | 10,000×/min DoS | Per-tenant rate limiter at execution API |
| T20 | Audit log tampering | Delete/modify execution records | Append-only; checksum chain |
| T21 | Kill switch bypass | Execution continues after kill | Worker checks every 5s + pre-I/O |
| T22 | Package artifact tampering | Replace after checksum, before exec | Content-addressable storage; verify at execution time |
| T23 | Policy downgrade attack | Downgrade restricted→simulation_only | Policy version history; execution refs policy version |
| T24 | Worker process reuse | Previous state leaks to next | Fresh worker per execution; no carryover |
| T25 | Side-channel: timing | Infer other tenant data | Coarse-grained timing; jitter |
| T26 | Dependency confusion | Internal package name hijack | Blocklist internal names; allowlist registry |
| T27 | Malicious manifest metadata | XSS/HTML in admin UI | Sanitize before storage; UI double-sanitize |
| T28 | Simulation replay as real evidence | Replay simulation output | Audit log distinguishes simulation vs real (PID/container ID) |
| T29 | Package quarantine bypass | Skip scan via direct artifact create | All artifacts: quarantine→scan→promote pipeline |

### P2 — Medium (5 threats)

| # | Threat | Impact | Step24 Mitigation |
|---|--------|--------|-------------------|
| T30 | Package metadata info disclosure | Internal paths/IPs leaked | Sanitize error messages |
| T31 | Execution queue starvation | Low-priority never runs | Fair scheduling; max depth; priority aging |
| T32 | Worker log injection | Fake log lines | Structured JSON logging; execution_id tagged |
| T33 | Policy confusion: cross-scope | Tenant policy vs system policy | System > tenant precedence; documented |
| T34 | Unverified checksum algorithm | MD5 passes format check | Only sha256/sha384/sha512; reject deprecated |

---

## 5. 执行边界原则（20 条硬约束）

### Trust Boundaries
1. Review approved ≠ executable
2. Published ≠ executable
3. Installed ≠ executable
4. Runtime binding enabled ≠ unrestricted execution
5. Sandbox policy assigned ≠ execution permission alone

### Code Safety
6. Package validated ≠ package safe
7. Signature metadata ≠ signature verified

### Authentication & Authorization
8. API Key ≠ admin authority
9. Developer ≠ runtime operator

### Network & Data & Filesystem
10. Network egress default deny
11. Secrets default deny (never env vars)
12. Filesystem default deny (ephemeral workspace only)
13. No docker socket mount
14. No privileged container
15. Kill switch overrides everything

### Process & Isolation
16. One execution, one worker, one workspace
17. No state carryover between executions
18. Output size limit enforced
19. Timeout is mandatory
20. Fail closed — any check failure = deny execution

---

## 6. Sandbox 技术方案比较

| 方案 | 安全强度 | 实现复杂度 | Windows 本地适配 | 适合 MVP | 风险 |
|------|---------|-----------|-----------------|---------|------|
| **No Execution** (当前) | ★★★★★ | 零 | ✅ 全平台 | 是 | 无执行能力 |
| **Simulation Runtime** | ★★★★★ | 低 | ✅ 全平台 | 是 | 无法验证真实行为 |
| **Sandboxed Subprocess** | ★★☆☆☆ | 中 | ⚠️ 部分（无 seccomp） | **否** | Python 进程隔离不足；os.system() 可逃逸；无 syscall filter |
| **Container Runtime (Docker)** | ★★★★☆ | 中-高 | ⚠️ 需 Docker Desktop | 有条件 | 配置错误可逃逸；Windows 容器≠Linux容器 |
| **Isolated Worker Service** | ★★★☆☆ | 中 | ✅ | 是 (MVP) | 应用层隔离，不防恶意代码；适合同组织可信 agent |
| **WASM Runtime** | ★★★★☆ | 高 | ✅ (wasmtime/wasmer) | 未来 | 生态有限；不支持通用 Python 库；需编译 target |
| **MicroVM (Firecracker)** | ★★★★★ | 高 | ❌ Linux only | 否 | 最强隔离但仅 Linux；启动开销大 |

### 结论

**普通 subprocess 不能作为不可信第三方代码的强安全边界。** Python subprocess 无法限制 syscall、网络访问、文件访问。攻击者可通过 os.system() / subprocess.run() / ctypes / mmap 逃逸。

Step 24 推荐两层实现：
1. **MVP (24-B 到 24-H)**: Isolated Worker Service abstraction — 建 artifact/quarantine/checksum/signature/worker interface/policy enforcement 基础设施，worker 默认 disabled-by-default stub
2. **Production (24-I+)**: Container Runtime — 不可信代码时切换到 Docker/Podman container worker，启用 seccomp/AppArmor/no-new-privileges/read-only rootfs

**WASM Runtime** 作为未来方向（Pyodide 等），当前不支持通用 Python package。

---

## 7. 推荐目标架构（15 组件，仅设计）

1. **PackageArtifactStore** — artifact 生命周期管理（download→quarantine→verify→promote→executable）
2. **PackageQuarantineStore** — 隔离状态（quarantined→scanning→scanned→promoted/rejected）
3. **SignatureVerifier** — minisign/cosign/GPG 验证（调用已有工具，不实现算法）
4. **ChecksumVerifier** — SHA256 actual vs declared
5. **DependencyScanner interface** — 静态 CVE + 恶意依赖（初版 stub: not_implemented）
6. **SandboxPolicyEnforcer** — policy → worker config 翻译器；can_enforce() fail closed
7. **RuntimeExecutionPlanner** — 验证前置条件 → ExecutionPlan
8. **SandboxWorker** — 隔离执行 accept ExecutionPlan（初版 stub: not_implemented）
9. **RuntimeExecutionStore** — execution request/result 持久化
10. **RuntimeAuditLogStore** — append-only + checksum chain
11. **DataAccessBroker** — 受控数据访问桥梁（初版 stub: all denied）
12. **SecretBroker** — 限时临时凭证（初版 stub: no secrets）
13. **NetworkPolicyEnforcer** — worker 层网络过滤（container: iptables; subprocess: unsafe）
14. **KillSwitch** — agent/tenant/global 三级；worker poll every 5s
15. **RuntimeResultSanitizer** — 截断/脱敏/去 tenant ID

---

## 8. 数据流设计（17 步，仅设计）

```
1. Developer creates Submission (manifest + package_url)
2. Admin reviews → approves → publishes to Marketplace
3. Admin creates RuntimeBinding + assigns SandboxPolicy + enables
4. Tenant installs Developer Agent from Marketplace
5. Admin: POST /admin/runtime/artifacts/{id}/prepare → Download to quarantine
6. PackageArtifactStore: status=quarantined
7. ChecksumVerifier: SHA256 actual vs declared → mismatch → BLOCK
8. SignatureVerifier: minisign/cosign/GPG → invalid → BLOCK
9. DependencyScanner: static CVE + malware check → critical → BLOCK
10. Quarantine → promote to verified storage
11. POST /admin/runtime/executions/plan → verify all preconditions
12. RuntimeExecutionPlanner: build ExecutionPlan (fail closed if any check fails)
13. KillSwitch check: agent/tenant/global
14. SandboxWorker.execute(plan): ephemeral workspace, timeout, policy enforcement
15. RuntimeResultSanitizer: truncate, redact, strip
16. RuntimeExecutionStore.save() + RuntimeAuditLogStore.record()
17. Return sanitized result to caller
```

**所有标注 "Step 24-A 只设计" 的步骤均不在此阶段实现。**

---

## 9. 数据模型草案（仅设计）

### 9.1 PackageArtifact (draft)
- artifact_id (pk), submission_id (FK), package_url, downloaded_at, artifact_path (quarantine), checksum_sha256, declared_checksum, checksum_verified, file_size_bytes, quarantine_status, signature_verified, dependency_scan_status, promoted_at

### 9.2 RuntimeExecutionRequest (draft)
- execution_id (pk), marketplace_agent_id, binding_id, artifact_id, tenant_id, plan_json, status (planned/queued/running/completed/failed/timeout/killed), worker_id, started_at, completed_at, exit_code, timeout_occurred, kill_switch_triggered, output_truncated

### 9.3 RuntimeExecutionResult (draft)
- execution_id, status, exit_code, stdout (sanitized), stderr (sanitized), output_bytes, output_truncated, duration_ms, timeout_occurred, kill_switch_triggered, worker_id, worker_type, policy_decisions, data_access_denied, network_access_denied

### 9.4 RuntimeAuditEvent (draft)
- event_id (pk, append-only), event_type, execution_id, tenant_id, marketplace_agent_id, artifact_id, actor_id, timestamp, detail_json, previous_event_id, checksum (SHA256 chain)

### 9.5 RuntimeKillSwitch (draft)
- switch_id (pk), level (agent/tenant/global), target_id, activated, activated_at, activated_by, reason, deactivated_at, deactivated_by

---

## 10. API 草案（仅设计）

- `POST /admin/runtime/artifacts/{submission_id}/prepare` — 下载到 quarantine (admin)
- `GET /admin/runtime/artifacts/{artifact_id}` — artifact 详情
- `POST /admin/runtime/artifacts/{artifact_id}/verify-checksum` — SHA256 比对
- `POST /admin/runtime/artifacts/{artifact_id}/verify-signature` — 签名验证
- `POST /admin/runtime/artifacts/{artifact_id}/scan-dependencies` — 触发依赖扫描
- `POST /admin/runtime/artifacts/{artifact_id}/promote` — 提升到 verified
- `POST /admin/runtime/executions/plan` — 生成执行计划（**不执行**）
- `POST /admin/runtime/executions/{execution_id}/execute` — 执行
- `GET /admin/runtime/executions/{execution_id}` — 执行记录
- `POST /admin/runtime/kill-switch` — 激活 kill switch (super_admin)
- `GET /admin/runtime/kill-switch` — 列出所有 kill switches
- `DELETE /admin/runtime/kill-switch/{switch_id}` — 停用 kill switch

**`POST /runtime/agents/{id}/execute` — 当前不能实现。** 需完整 artifact pipeline + sandbox worker + policy enforcer。这是 Step 24-H 之后的能力。

---

## 11. Policy Enforcement 设计

### 11.1 SandboxPolicy → WorkerConfig 翻译

- sandbox_level=no_execution → worker refuses (fail closed)
- sandbox_level=simulation_only → SimulationRuntime (existing)
- sandbox_level=restricted → SandboxWorker with caps + no network
- sandbox_level=isolated → ContainerWorker with full isolation
- allow_network + allowed_domains → NetworkPolicyEnforcer: iptables whitelist + DNS filter
- allow_filesystem → Container: volume mounts (read-only/tmpfs)
- max_timeout_ms → Worker SIGTERM at timeout, SIGKILL at timeout+5000ms
- max_memory_mb → Container --memory limit / cgroup v2 memory.max
- max_output_bytes → stdout/stderr pipe limit; truncation flag

### 11.2 Fail Closed 策略

PolicyEnforcer.can_enforce(policy) 检查：
- Worker type 是否支持此 sandbox_level？
- Worker type 是否支持网络过滤？
- Worker type 是否支持 filesystem 限制？
- Worker type 是否支持 memory/CPU limits？

任何不支持 → can_enforce=False → ExecutionPlanner 拒绝执行。

---

## 12. Data Access / Network / Secrets / Filesystem 设计

### Data Access Broker
- Developer code 永远不能直接访问: SQLite, ChromaDB, Memory Store, Workspace 文件, secrets
- 通过受控 IPC (stdin/stdout JSON-RPC pipe) 向 broker 发送请求
- Broker 检查: data_access_scope, tenant_id, limit
- 初版 stub: all data requests return `{"denied": true, "reason": "not yet implemented"}`

### Network
- Default: DENY ALL egress
- Block: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.169.254, 127.0.0.0/8, ::1
- Allow: only if policy allow_network + domain in allowed_domains
- Enforced at container/OS level, not Python level

### Secrets
- Default: NO secrets available
- Injection: broker RPC (never env vars)
- Credential: time-limited temporary (TTL ≤ execution timeout)
- Post-execution: auto revoke

### Filesystem
- Default: empty ephemeral workspace (tmpfs)
- No host path mount
- Read access: only if policy allow + path in allowed_paths
- Write path: tmpfs subdirectory, deleted after execution
- Output size: capped at max_output_bytes
- Cleanup: workspace deleted immediately after execution

---

## 13. Observability / Audit / Kill Switch

### Execution Audit Log 事件类型
- execution_started: {execution_id, agent_id, tenant_id, binding_id, artifact_id, worker_type, policy_id, timestamp}
- policy_decision: {execution_id, policy_id, decision, rule_details}
- execution_completed: {execution_id, exit_code, duration_ms, output_bytes, output_truncated, timeout_occurred}
- execution_timeout: {execution_id, timeout_ms, kill_signal}
- execution_killed: {execution_id, kill_switch_id, kill_switch_level}
- artifact_verified: {artifact_id, checksum_match, signature_valid, scan_status}

### Kill Switch Architecture
- agent-level: stop all executions for marketplace_agent_id
- tenant-level: stop all executions for tenant_id
- global: stop ALL executions (super_admin only)
- Worker poll every 5s + before each I/O operation

---

## 14. Step 24 分阶段计划

| Step | Name | Goal | Status |
|------|------|------|--------|
| 24-A | Architecture Audit + Execution Boundary Design | 完整蓝图 + 34 威胁 + 20 边界 + 15 组件 | ✅ |
| 24-B | Package Artifact & Quarantine Domain Model + Store | Artifact/Quarantine 数据模型+store，**不下载** | ⏸ |
| 24-C | Checksum / Signature Verification Pipeline | SHA256 + minisign/cosign/GPG 验证组件 | ⏸ |
| 24-D | Runtime Execution Plan Model + Store | ExecutionPlanner + ExecutionPlan + store | ⏸ |
| 24-E | Sandbox Worker Interface + Disabled-by-default Stub | Worker protocol + stub (not_implemented) | ⏸ |
| 24-F | Policy Enforcement Translator | Policy → WorkerConfig; fail closed | ⏸ |
| 24-G | Local Development Sandbox Prototype | Subprocess worker prototype (受限) | ⏸ |
| 24-H | Runtime Execution API Draft + Admin Gate | Artifact + Execution + Kill Switch API | ⏸ |
| 24-I | Security Tests + Escape Guard Tests | P0 威胁测试; breakout/SSRF/data leak | ⏸ |
| 24-J | Demo + Documentation | End-to-end demo + 文档 | ⏸ |
| 24-K | Final Regression + Step 25 Gate | 全量回归 + Step 25 准入 | ⏸ |

### Per-Step Forbidden
- 24-B: 不下载/不执行; 24-C: 不联网/不在主进程执行; 24-D: 不启动 worker; 24-E: 不真实执行; 24-F: 不执行代码; 24-G: 不网络/secrets/production; 24-H: 不开放 dev execute 端点; 24-I: 不在生产测; 24-J: 不跳过安全; 24-K: 不新功能

---

## 15. Step 24-B 准入条件

进入 Step 24-B（Package Artifact & Quarantine Domain Model + Store）的唯一条件：

1. ✅ Step 24-A 完成（本文档 + ROADMAP 更新）
2. ✅ 34 威胁模型已识别（P0×15, P1×14, P2×5）
3. ✅ 20 执行边界原则已定义
4. ✅ 沙箱技术比较完成，结论明确
5. ✅ 推荐目标架构已设计
6. ✅ 数据流完整链路已定义
7. ✅ Step 24 分阶段计划已制定
8. ⏸ Step 24-B 不包含任何 package 下载/执行

**Step 24-B 只允许进入 Package Artifact & Quarantine Domain Model + Store。不允许直接进入 execution。**

---

## 16. Known Issues

- No real package download yet (24-B)
- No artifact quarantine store yet (24-B)
- No checksum verification yet (24-C)
- No signature verification yet (24-C)
- No dependency scan yet (24-C+)
- No container sandbox yet (24-G+)
- No worker isolation yet (24-E+)
- No data broker yet (24-F+)
- No secret broker yet (24-F+)
- No policy enforcement runtime translator yet (24-F)
- No real external code execution yet (24-G+)
- No developer-facing execution API (24-H+)
- Subprocess is NOT a strong security boundary for untrusted code
- Windows adaptation ≠ Linux container security capabilities
- WASM Runtime does not support general Python packages

---

## 17. Non-Execution Guarantees

Step 24-A explicitly does NOT:
- ❌ Download any package
- ❌ Unzip any package
- ❌ Execute package_url
- ❌ Execute entrypoint
- ❌ Make network calls
- ❌ Read secrets
- ❌ Read real enterprise data
- ❌ Call AgentRuntime to execute developer agent
- ❌ Register developer agent to AgentRegistry
- ❌ Create new worker processes
- ❌ Start containers
- ❌ Implement runtime execution API
- ❌ Claim sandbox completed
- ❌ Claim external code execution completed
- ❌ Write any implementation code beyond documentation
