# Step 24 Security Q&A

## Q1: 为什么 `/runtime/agents/{id}/execute` 存在但 blocked？

这是企业安全平台的"draft API"策略——端点提前暴露以验证 auth/RBAC/gate/response schema，但执行逻辑故意不放行。在 checksum/signature/worker/policy/container/audit/kill-switch 全部就绪之前，放行执行是不可接受的。Step 24-H 将端点返回 status=blocked，is_execution_allowed=false。

## Q2: 为什么不直接执行第三方代码？

因为"门还没装好"——真实执行需要：(1) package 下载后的隔离存储，(2) checksum/signature/dependency 真实验证，(3) container/microVM 沙箱，(4) policy 到 worker config 的完整翻译，(5) secret/data/network 受控 broker，(6) 审计日志，(7) 全局 kill switch。这些在 Step 24-A 到 H 中设计并部分实现了基础层，但生产级执行环境需要 Step 25+。

## Q3: 为什么 subprocess 不安全？

Python subprocess 隔离不足——无法限制 syscall、网络访问、文件访问。攻击者代码可以通过 os.system()、subprocess.run()、ctypes、mmap 逃逸。Step 24-A 的沙箱比较表明确结论：subprocess 不能作为不可信第三方代码的强安全边界。真正隔离需要 container/microVM + seccomp + AppArmor + no-new-privileges。

## Q4: 为什么 policy config 不等于 execution permission？

Policy Translation 只是将 SandboxPolicy 的数据字段（13 字段）翻译为 WorkerPolicyConfig（5 个子 config）。config.enforceable=True 只表示"当前 worker 类型理论上可以强制这个策略"，不表示"可以执行"。执行需要 artifact ready + checksum verified + signature verified + worker available + kill switch off — 这些在 Step 24 均未全满足。

## Q5: 为什么 signature 当前 metadata-only？

真实签名验证需要：(1) package 文件在本地，(2) 对应公钥在信任链中，(3) 调用 minisign/cosign/gpg 等外部工具。Step 24-C 明确禁止调用外部工具——signature verifier 只验证算法的结构合法性和 trust-policy 检查（key_id 是否在信任列表中）。EXTERNAL_TOOL_RESERVED 模式返回 BLOCKED。这是故意设计的安全门禁。

## Q6: Checksum verification 到底验证了什么？

对受控 bytes 或受控 local fixture（必须在 allowed_root 内，不能是 symlink/目录，<50MB）计算 SHA256/SHA384/SHA512 并与 declared checksum 比对。没有 content_bytes 或 local_path → BLOCKED。不支持 MD5/SHA1。不下载 package_url。不访问网络。

## Q7: LocalDevSandboxPrototypeWorker 是不是已经能跑代码？

**不是。** LocalDevSandboxPrototypeWorker 只做 dry-run evaluation——检查 policy config snapshot 的 enforceable/network/secrets/filesystem/data_access 字段是否与 worker 能力兼容。它不读取任何 local path，不 open file，不 subprocess，不 container。stdout/stderr/exit_code 全部为 None。is_successful_execution() 始终 False。

## Q8: DisabledSandboxWorker 有什么意义？

它是 SandboxWorker Protocol 的 fail-closed 参考实现和默认安全锚点。Worker Registry 默认只注册 DisabledSandboxWorker——确保在显式启用任何 worker 之前，所有请求都被 block。它证明了接口设计正确，同时保证最小安全边界。

## Q9: RuntimeExecutionPlan 有什么意义？

它是"执行前置检查的持久化快照"。包含 20 preflight checks（marketplace agent → installation → permissions → binding → adapter → sandbox policy → artifact → verification → safety flags）。Plan 一旦创建就冻结了当时的系统状态快照。但 plan 本身不触发执行——is_dispatchable() 始终 False。

## Q10: 为什么 plan.is_dispatchable=false？

因为在 Step 24-D/E/F/G/H 阶段，worker 还没有真实执行能力。Dispatch 需要 worker available + policy enforced + artifact ready + verification passed + kill switch off。这些条件一个都没满足，所以 is_dispatchable() 返回 False 是正确的安全行为。

## Q11: 为什么 API Key 不能绕过 admin gate？

Admin gate（create plan/policy preview/worker preview）要求 JWT with admin/owner/org_admin/super_admin role。API Key 即使有 agent:execute scope 也不能访问 admin 端点。这是 Step 23-B 建立的硬边界——API Key 的 8 个 forbidden scopes 包含 admin:/developer:/submission:/platform:*。

## Q12: 为什么 install/publish/approve/binding enabled 不等于 executable？

这些是各自独立的状态变更：Install → TenantAgentInstallation record；Publish → Manifest → MarketplaceAgent mapping；Approve → AgentSubmission state transition；Binding enabled → RuntimeBinding status update。每个操作都不触发代码执行。这 4 个状态变更合起来也只是"允许执行的前置条件"中的一部分——还必须满足 artifact ready + verified + policy enforced + worker available + kill switch off。

## Q13: 为什么不自动启用 local dev dry-run？

因为任何自动启用都会降低安全门槛。create_default_sandbox_worker_registry(enable_local_dev_dry_run=False) 默认只注册 DisabledSandboxWorker。Local dev dry-run 只在测试中显式构造。main.py 不启用。不读环境变量。不读配置文件。

## Q14: Worker registry 为什么默认 disabled？

安全锚点原则——系统必须 fail-closed。默认 registry 只有一个 worker：DisabledSandboxWorker。没有 container、没有 subprocess、没有 WASM、没有 microVM。任何 worker type 的注册必须显式调用 register()。

## Q15: 怎么防 package_url 被下载？

代码层面：所有 Step 24 模块不 import requests/httpx/urllib.request。PackageArtifact 只存 URL 字符串。PackageArtifactDeclarationService 不发起 HTTP 请求。测试层面：Step 24-I import guard tests 验证所有 20 个模块不引入网络库。Process 层面：Step 24 没有 HTTP GET/HEAD 调用。

## Q16: 怎么防 SSRF？

多层防护：(1) PackageValidation 拒绝 localhost/private IP/169.254.169.254 的 URL。(2) ChecksumVerifier 不访问 package_url。(3) PolicyEnforcementTranslator 在 domain 层 block private IPs、localhost、metadata IP。(4) NetworkPolicyConfig 默认 DENY_ALL。(5) NetworkPolicyEnforcer 设计为 container-level iptables（未来实现）。

## Q17: 怎么防 secrets 泄露？

(1) 不注入环境变量。(2) SecretBroker 设计为限时临时凭证（未来实现）。(3) SecretPolicyConfig.raw_env_injection_allowed=False。(4) SandboxWorkerRequest 不存 raw input。(5) 所有 to_dict() 输出不含 raw_key/key_hash。(6) Metadata leakage guards 验证。

## Q18: 怎么防 raw input 泄露？

(1) RuntimeExecutionPlan 只存 input_payload_hash（SHA256 of sorted JSON），不存 raw input_payload。(2) SandboxWorkerRequest 只存 input_payload_hash。(3) Usage metadata 不包含 raw input。(4) Metadata leakage guards 验证。

## Q19: 怎么防 stdout/stderr 泄露？

(1) SandboxWorkerResult.stdout_text/stderr_text 默认 None。(2) 即使 LocalDevSandboxPrototypeWorker 也不填充 stdout/stderr。(3) 只有未来的真实 sandbox execution 才会产生 stdout/stderr，且必须经过 RuntimeResultSanitizer 脱敏。(4) Metadata leakage guards 验证。

## Q20: 怎么防 AgentRegistry 污染？

(1) Step 24 所有模块不 import AgentRegistry。(2) Developer Agent 永远不注册到 AgentRegistry——它走独立的 Sandbox Runtime path。(3) Security escape guard tests 验证所有 20 个模块的 import 安全。

## Q21: 怎么防 AgentRuntime trust boundary collapse？

(1) Developer agent 代码永远不在 PEOR loop（Plan→Execute→Observe→Reflect）中运行。(2) AgentRuntime 和 Developer Sandbox Execution 是两个完全隔离的执行路径。(3) Step 24 所有模块不 import AgentRuntime。

## Q22: Step 24-I 测试覆盖了什么？

168 项安全逃逸防护测试，分为 9 大类：
- A. Import Guards: 20 模块 × 3 检查（no subprocess/docker/requests/AgentRuntime）
- B. Method Name Guards: 16 项（no execute/run/dispatch methods）
- C. Execute Endpoint Guards: 14 项（always blocked）
- D. Worker/Registry Guards: 15 项（disabled by default）
- E. Package Supply-Chain: 13 项（no download, sha256+ only）
- F. Policy Enforcement: 12 项（fail-closed）
- G. Metadata Leakage: 10 项（no secrets in outputs）
- H. Startup Guards: 10 项（no worker/queue start）
- I. Documentation Guards: 10 项（no false claims）

## Q23: 当前最大 known issues 是什么？

- 没有真实 package 下载与隔离（quarantine 只是 metadata record）
- 没有真实 container/microVM 沙箱
- 没有真实 checksum verification（只能对 controlled bytes）
- 没有真实 cryptographic signature verification
- 没有 dependency/CVE scan
- 没有 data broker / secret broker
- 没有 network policy enforcement（at OS level）
- 没有 kill switch 实现
- 没有 worker queue / job dispatch
- execute endpoint 永远 blocked

以上全部是故意推迟到 Step 25+ 的设计决策，不是 Bug。

## Q24: Step 24-K 要做什么？

Step 24-K 是 Final Regression + Step 25 Gate。包括：
- 全量回归测试（预计 2000+ tests）
- Capability Gate: 24A-I 全部 capability 确认
- Security Gate: 所有 guard tests + escape tests
- Documentation Gate: 14 份 STEP24 文档完整性
- Startup Gate: main.py 零错误启动
- Step 25 Admission: 10 条件确认

## Q25: Step 25 以后才可能做什么？

- 真实 package download + quarantine directory
- 真实 container/microVM sandbox
- 真实 cryptographic signature verification（调用 gpg/minisign/cosign）
- 依赖扫描（safety/pip-audit）
- Data/Secret/Network Broker
- Kill switch 实现
- Worker queue + job dispatch
- Runtime execution result audit
- Developer-facing execute endpoint unblock
- Production sandbox infrastructure
