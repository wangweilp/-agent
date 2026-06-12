# Step 25 Runtime Safety Demo Script

## 1. Demo Positioning

Step 25 is a **production sandbox roadmap and safety-gated runtime preparation layer**. It is **not** a production sandbox. It does **not** execute third-party code.

What Step 25 demonstrates:
- Safety-gated execution record pipeline (audit-only)
- Container/microVM feasibility assessment (paper-tier only)
- Admin-gated download request with source validation (no actual download)
- Read-only extraction guard (no unzip)
- Disabled-by-default worker queue records (no real queue)
- Network/filesystem/secrets enforcement proof (metadata-only)
- Trusted fixture execution (built-in deterministic fixtures only, no third-party code)
- Red-team escape guard tests (163 tests, no critical escape path found)

## 2. Demo Storyline (9 Scenes)

### Scene 1: Execution Record (Audit-Only)
```python
from src.open_platform.sandbox_execution import SandboxExecutionRecord
r = SandboxExecutionRecord(plan_id="p", marketplace_agent_id="m", tenant_id="t", developer_id="d")
assert not r.is_executable()  # Always False — no execution path exists
```
**Key point**: Execution record is metadata only. No queue, no dispatch, no worker.

### Scene 2: Container/MicroVM Feasibility
```python
from src.open_platform.sandbox_adapter_feasibility_service import SandboxAdapterFeasibilityService
svc = SandboxAdapterFeasibilityService()
results = svc.assess_all_default_options()  # 10 technologies
for r in results:
    assert not r.profile.execution_enabled  # All disabled
# Subprocess: REJECTED. Rootless container: CANDIDATE (not approved). MicroVM: RESERVED.
```
**Key point**: 10 technologies assessed. Subprocess rejected. No container started.

### Scene 3: Package Download Admin Gate
```python
from src.open_platform.package_download_quarantine import build_package_source_metadata
# HTTPS → admin review. HTTP/file/git/localhost/private IP → blocked.
src = build_package_source_metadata("https://example.com/pkg.zip")  # not blocked
assert not src.is_blocked_source
src_bad = build_package_source_metadata("http://insecure.com/pkg.zip")  # blocked
assert src_bad.is_blocked_source
```
**Key point**: Admin approval = future download reserved. No actual download.

### Scene 4: Read-only Extraction Guard
```python
from src.open_platform.artifact_extraction_guard import build_archive_entry_metadata
e = build_archive_entry_metadata("a/b/file.py", "file", 100)
assert not e.is_blocked
e_bad = build_archive_entry_metadata("../etc/passwd")  # traversal → blocked
assert e_bad.is_blocked
```
**Key point**: No archive read. No extraction. No file write. Path traversal/symlink/device blocked.

### Scene 5: Disabled Worker Queue
```python
from src.open_platform.sandbox_worker_queue import SandboxWorkerQueueRecord
r = SandboxWorkerQueueRecord(tenant_id="t")
assert not r.is_dispatch_allowed()  # Always False
assert not r.is_queue_enabled()     # Always False
```
**Key point**: Queue record exists. Real queue does not. No enqueue/dispatch/worker.

### Scene 6: Enforcement Proof
```python
from src.open_platform.sandbox_enforcement_proof_service import SandboxEnforcementProofService
svc = SandboxEnforcementProofService(store=store)
r = svc.create_proof_request("t1")
res = svc.evaluate_proof(r.request_id)
assert not res.is_enforcement_active()  # Metadata-only proof
```
**Key point**: Network DENY_ALL. No host mount. No docker socket. No raw env secret injection. Proof not enforcement.

### Scene 7: Trusted Fixture Execution
```python
from src.open_platform.trusted_fixture_registry import TrustedFixtureRegistry
from src.open_platform.trusted_fixture_execution import TrustedFixtureExecutionResult
reg = TrustedFixtureRegistry()
o = reg.run_trusted_fixture("tfix_noop_builtin", {})
assert o["ok"]  # Trusted fixture executed
r = TrustedFixtureExecutionResult(request_id="r", fixture_id="f", tenant_id="t")
r.trusted_fixture_executed = True
assert not r.third_party_code_executed  # Always False
assert not r.package_executed           # Always False
```
**Key point**: 5 built-in fixtures. No eval/exec/import. Not third-party code execution.

### Scene 8: Red-Team Escape Tests
```bash
python -m pytest tests/test_open_platform/test_step25_red_team_escape_guards.py -v
# 163 passed — 11 guard categories
```
**Key point**: Dangerous import/method/enum guards. Metadata leakage. Execute endpoint blocked. No critical escape path.

### Scene 9: Claim Boundary
**Can claim**: Execution record pipeline, feasibility assessment, admin gate, extraction guard, queue records, enforcement proof, trusted fixture, red-team tests, 2709 regression tests passed.

**Cannot claim**: Production sandbox, third-party execution, package execution, container/microVM runtime, real queue/worker/enforcement.

## 3. Demo Commands

```powershell
# All Step 25 tests
python -m pytest tests/test_open_platform/test_step25_red_team_escape_guards.py -v
python -m pytest tests/test_open_platform/test_trusted_fixture_execution.py -q
python -m pytest tests/test_open_platform/test_sandbox_enforcement_proof.py -q
python -m pytest tests/test_open_platform/test_sandbox_worker_queue.py -q
python -m pytest tests/test_open_platform/test_artifact_extraction_guard.py -q
python -m pytest tests/test_open_platform/test_package_download_quarantine.py -q
python -m pytest tests/test_open_platform/test_sandbox_adapter_feasibility.py -q
python -m pytest tests/test_open_platform/test_sandbox_execution_store.py -q

# Full regression
python -m pytest tests/test_open_platform/ -q
python -m pytest tests/test_security.py tests/test_agents/ tests/test_saas/ tests/test_open_platform/ -q

# Startup
python main.py
# Must see: runtime_execution_api_registered, no runtime_worker_started

# Docs check
Get-ChildItem docs -Filter "STEP25*.md"
```

## 4. Demo Narration (3-5 min 中文稿)

各位好。我来演示 Step 25 Runtime Safety Demo。

Step 25 不是一个跑代码的演示，而是一个安全治理能力的演示。

**第一步：Sandbox Execution Record。** 我们建立了一个完整的执行记录数据模型，支持 audit-only 创建、状态变更、审计事件追踪。但关键特点是——is_executable() 始终返回 False。没有 queue，没有 dispatch，没有 worker。这是"知道能不能做，但先不做"的安全起点。

**第二步：Container/MicroVM 可行性评估。** 我们评估了 10 种隔离技术。Subprocess 被明确拒绝——因为普通 subprocess 不能作为不可信第三方代码的安全边界。Rootless container 是候选方案，但 execution_enabled=False。MicroVM 保留到未来。零 Docker 调用，零容器启动。

**第三步：Package Download Admin Gate。** 所有 package URL 都经过字符串级校验——HTTPS 进入 admin review，HTTP/file/git/localhost/private IP/metadata IP 全部 blocked。Admin 可以 approve，但 approve 只表示 "future download reserved"。is_downloadable() 始终 False。

**第四步：Read-only Extraction Guard。** Zip-slip、路径穿越、符号链接、硬链接、设备节点、FIFO、Socket——全部 blocked。Script 扩展名和可执行权限 flag 为 WARNING。不 import zipfile/tarfile/shutil。不解压，不写文件。

**第五步：Worker Queue。** 有 queue record，没有 real queue。enqueue_allowed=False，dispatch_allowed=False，worker_start_allowed=False。Queue gate result 始终 is_passed_for_queue=False。

**第六步：Enforcement Proof。** Network DENY_ALL，Filesystem DENY_ALL，Secrets DENY_ALL。Metadata-only proof——不改 iptables，不挂载文件系统，不读 secrets，不读 os.environ。

**第七步：Trusted Fixture。** 5 个平台内置确定性无副作用 fixture——noop、echo metadata、policy proof summary、queue gate summary、static health check。Trusted fixture executed=True 是允许的，但 third_party_code_executed=False，package_executed=False，entrypoint_executed=False。不 eval，不 exec，不动态 import。

**第八步：Red-Team Escape Tests。** 163 个红队逃逸测试，覆盖 11 个守卫类别——dangerous import、dangerous call、dangerous enum state、dangerous method、boundary behavior、trusted fixture escape、metadata leakage、execute endpoint、no-action store/service、docs honesty、startup guard。全过，零逃逸路径。

**最后总结。** 我们已经建立了从执行记录、可行性评估、下载审批、解压守卫、队列禁用、强制证明、夹具执行到红队测试的完整安全门控链路。但以下内容明确不能声称：production sandbox completed、third-party code execution completed、container/microVM runtime、real queue/worker。Step 25-K 做 final regression gate，在这之后才能进入真正的 sandbox 执行阶段。

核心信息：我们不是在证明"能做"，而是在证明"知道怎么安全地做"。

## 5. What We Can Claim (15 items)

1. Sandbox execution record with audit-only state machine
2. Container/microVM feasibility assessment (10 technologies)
3. Package download admin gate with source URL validation
4. Metadata-only quarantine reservation (no file write)
5. Read-only extraction guard (no archive read, no extraction)
6. Disabled worker queue records (no real queue)
7. Network/filesystem/secrets enforcement proof (metadata-only)
8. Trusted fixture execution (5 built-in deterministic fixtures only)
9. Red-team escape guard tests (163 tests, 11 categories)
10. Execute endpoint blocked for third-party/package execution
11. Metadata leakage guards (all to_dict() outputs verified)
12. Dangerous import/method/enum guards (15 modules)
13. Documentation honesty guards
14. 2709 cross-suite regression tests passed
15. No critical escape path found

## 6. What We Cannot Claim (20 items)

1. Production sandbox completed
2. Third-party code execution completed
3. Package execution completed
4. Entrypoint execution completed
5. Container runtime implemented
6. MicroVM runtime implemented
7. Docker integration implemented
8. Package download implemented
9. Archive extraction implemented
10. Worker queue running
11. Job dispatch implemented
12. Real worker started
13. Network enforcement applied
14. Filesystem enforcement applied
15. Secrets broker implemented
16. OS-level isolation proved
17. Dependency/CVE scan implemented
18. Real cryptographic signature verification implemented
19. Execute endpoint returns package success
20. Trusted fixture equals external code execution

## 7. Demo Risk Notes

- Step 25 is safety-gated runtime preparation, not a production sandbox
- Any real third-party execution must wait for an independent gate after Step 25-K
- Trusted fixture only proves pipeline closure, not arbitrary code execution capability
