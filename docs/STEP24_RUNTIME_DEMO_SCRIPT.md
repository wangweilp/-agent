# Step 24 Runtime Safety Demo Script

## 1. Demo Positioning

Step 24 **不是"已经开始执行第三方代码"**——是从安全准备态进入真实执行态前，必须完成的架构、门禁、计划、隔离、验证、dry-run、API gate。

当前系统 **故意 blocked-by-default**。这是企业级安全平台必须走的路线：先把门禁和审计做完，再逐步开放执行能力。

## 2. Demo Storyline — 8 Scenes

### Scene 1: Package Artifact Declaration

展示 package artifact metadata 登记 + quarantine + audit event。

```python
# 从 submission manifest 声明 artifact（不下载）
from src.open_platform.package_artifact import PackageArtifact, ArtifactStatus
artifact = PackageArtifact(submission_id="sub_demo", developer_id="dev1", tenant_id="t1",
    package_url="https://example.com/pkg.zip",
    checksum_algorithm="sha256", checksum_value="abc123...")
# artifact_status=DECLARED, quarantine_status=NOT_QUARANTINED
```

**说明**: 不下载 package_url。不读取本地文件。不解压。不执行。

### Scene 2: Checksum / Signature Verification

```python
# Checksum: 只对 controlled bytes 计算 hash
from src.open_platform.checksum_verifier import verify_checksum, ChecksumVerificationRequest
data = b"test package content"
r = verify_checksum(ChecksumVerificationRequest(artifact_id="a1", algorithm="sha256",
    expected_checksum=hashlib.sha256(data).hexdigest(), content_bytes=data))
# r.matched = True

# Signature: metadata-only，不做真实 cryptographic verification
from src.open_platform.signature_verifier import verify_signature, SignatureVerificationRequest
sr = verify_signature(SignatureVerificationRequest(artifact_id="a1",
    signature_algorithm="cosign", signature_value="b64sig", signing_key_id="k1"))
# sr.signature_verified = False (metadata-only in Step 24-C)
```

**说明**: sha256/sha384/sha512 支持。MD5/SHA1 被拒。无 content_bytes/path → BLOCKED。不调用 gpg/cosign/minisign。

### Scene 3: Runtime Execution Plan

```python
# Create plan — 20 preflight checks
plan = planner.create_plan("mkp_xxx", "tenant_1", "actor_admin", execution_mode="sandbox_reserved")
# plan.plan_status = PLANNED or BLOCKED
# plan.is_dispatchable() = False (always)
# plan.dispatch_status = RESERVED_FOR_STEP24E
```

**说明**: plan 创建了但不意味着可以 dispatch。is_dispatchable()=False。dispatch_status 不进入 running/completed。

### Scene 4: Disabled Worker Interface

```python
from src.open_platform.sandbox_worker_stub import DisabledSandboxWorker
worker = DisabledSandboxWorker()
# worker.get_worker_type() = "disabled_stub"
# worker.get_availability() = "disabled"
result = worker.evaluate_request(request)
# result.status = BLOCKED, decision = BLOCKED_DISABLED
# result.is_successful_execution() = False
```

**说明**: 有接口但没有执行能力。无 execute/run/dispatch 方法。

### Scene 5: Policy Enforcement Translator

```python
from src.open_platform.policy_enforcement_translator import SandboxPolicyEnforcementTranslator
t = SandboxPolicyEnforcementTranslator()
result = t.translate_policy(no_execution_policy)
# result.status = PASSED/PASSED_WITH_WARNINGS
# result.config: WorkerPolicyConfig (network=DENY_ALL, secrets=DENY_ALL...)
# isolated → BLOCKED/FAIL_CLOSED
# secrets without broker → BLOCKED
```

**说明**: policy → config 只是翻译层。config 不等于 execution permission。fail-closed 全程开启。

### Scene 6: Local Dev Sandbox Prototype

```python
from src.open_platform.local_dev_sandbox_worker import LocalDevSandboxPrototypeWorker
from src.open_platform.local_dev_sandbox import LocalDevSandboxConfig
cfg = LocalDevSandboxConfig.dry_run_for_tests()  # enabled=True, dry_run_only=True
worker = LocalDevSandboxPrototypeWorker(config=cfg)
result = worker.evaluate_request(request_with_good_policy_config)
# result.status = RESERVED/SKIPPED
# result.is_successful_execution() = False (always)
# result.stdout_text = None, result.stderr_text = None
```

**说明**: local dev prototype 只做 dry-run。不 subprocess/container。disabled by default。

### Scene 7: Runtime Execution API Draft

```bash
# Admin plan endpoint
POST /admin/runtime/execution-plans  → plan created (no execution)
GET  /admin/runtime/execution-plans  → list plans
POST /admin/runtime/execution-plans/{id}/policy-preview → policy config preview
POST /admin/runtime/execution-plans/{id}/worker-preview  → DisabledSandboxWorker blocked

# Execute draft endpoint — ALWAYS BLOCKED
POST /runtime/agents/{id}/execute → {"status": "blocked", ...}
```

**说明**: API 门面存在。Execute endpoint 永远返回 blocked。

### Scene 8: Security Escape Guard Tests

```bash
python -m pytest tests/test_open_platform/test_step24_security_escape_guards.py -v
# 168 passed — import/method/endpoint/worker/supply-chain/policy/metadata/startup/docs guards
```

**说明**: 系统性安全测试覆盖全链路。零 bypass。

## 3. Demo Commands

```powershell
# Security guard tests
python -m pytest tests/test_open_platform/test_step24_security_escape_guards.py -v

# Full Open Platform tests
python -m pytest tests/test_open_platform/ -q

# Full backend regression
python -m pytest tests/test_security.py tests/test_agents/ tests/test_saas/ tests/test_open_platform/ -q

# Startup verification
python main.py
# Must see: runtime_execution_api_registered
# Must NOT see: runtime_worker_started, execution_enabled

# Docs check
Get-ChildItem docs -Filter "STEP24*.md"
Get-Content docs\ROADMAP.md | Select-String "24-"
```

## 4. Demo Narration（3-5 min 中文讲稿）

各位好。我来演示 Step 24 Runtime Safety Layer 的当前状态。

**第一步，我们看一下 Package Artifact 的声明过程。** 当 Developer 提交了一个包含 package_url 的 manifest 后，系统会创建一个 artifact metadata 记录（artifact status=DECLARED），并自动生成 quarantine record 和 audit event。注意——整个过程没有下载 package，没有解压，没有执行。这只是元数据注册。

**第二步，校验。** Checksum verifier 支持 sha256/sha384/sha512 对受控 bytes 或 local fixture 计算 hash——但必须满足 allowed_root 安全约束。Signature verifier 当前是 metadata-only 层，不做真实 cryptographic verification。不调用 gpg/cosign/minisign。MD5/SHA1 被直接拒绝。

**第三步，Execution Plan。** 管理员创建 Runtime Execution Plan，系统执行 20 项 preflight 检查——marketplace agent 存在性、installation 状态、permissions、runtime binding、adapter、sandbox policy、artifact、verification。Plan 创建成功——但 is_dispatchable() 始终返回 False。Plan 状态是 PLANNED 或 BLOCKED，绝不进入 running/completed。

**第四步，Worker。** 我们有 SandboxWorker 接口——DisabledSandboxWorker 是默认实现。它永远返回 BLOCKED_DISABLED。没有 execute/run/dispatch 方法。Local Dev Prototype 是 dry-run only——只验证 policy config 兼容性，不执行。

**第五步，Policy。** Policy Enforcement Translator 将 SandboxPolicy 翻译为 WorkerPolicyConfig（网络/filesystem/secrets/resource/data 五个子 config）。isolated 策略 fail-closed。Secrets without broker？Blocked。Host mount？Never allowed。Raw env injection？Never allowed。

**第六步，API。** Admin execution plan API 已注册——create/list/detail/cancel/expire/policy-preview/worker-preview——全部 admin-only。关键是 `/runtime/agents/{id}/execute` 端点存在但永远 blocked。返回 status=blocked，is_execution_allowed=false。

**最后，Security Guards。** 168 项安全逃逸防护测试覆盖了 20 个 Step 24 模块的 import 安全、method name 安全、API 边界、worker 边界、package 供应链安全、policy 安全、metadata 泄露防护、startup 安全和文档安全。

**当前全量回归：1967 个测试全部通过。系统启动零错误。**

关键信息：Step 24 不是执行阶段——它是安全准备阶段。所有执行入口都被 fail-closed 保护。这正是企业级平台在允许第三方代码执行之前必须做的工作。

## 5. What We Can Claim

- 完成安全执行架构审计
- 完成 artifact/quarantine metadata store
- 完成 checksum verifier (controlled input only)
- 完成 signature verifier (metadata-only)
- 完成 execution plan model/store/planner
- 完成 disabled worker interface
- 完成 policy-to-config translator (fail-closed)
- 完成 dry-run-only local prototype
- 完成 admin-gated API draft
- 完成 168 项 security escape guard tests
- execute endpoint currently blocked by design
- DisabledSandboxWorker is default

## 6. What We Cannot Claim

- ❌ production sandbox completed
- ❌ external code execution completed
- ❌ container isolation completed
- ❌ subprocess sandbox safe
- ❌ package download completed / package unzip completed
- ❌ real cryptographic signature verification completed
- ❌ dependency/CVE scan completed
- ❌ worker queue completed / runtime job dispatch completed
- ❌ AgentRuntime developer execution completed
- ❌ `/runtime/agents/{id}/execute` returns success

## 7. Demo Risk Notes

这不是产品缺陷，而是安全路线。企业级平台必须先建立门禁和审计体系，再逐步开放不可信代码执行能力。Step 24 做的是"把门装好"，Step 25+ 才"开门"。
