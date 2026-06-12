# Step 23-I：Security + Runtime Tests

## 1. 覆盖范围

| 域 | 测试数 | 关键验证 |
|---|--------|---------|
| API Key Boundary | 17 | Admin/Runtime/Policy 访问禁止, scope enforcement, raw_key/key_hash 不泄露 |
| Tenant Isolation | 6 | 跨 tenant 404, super_admin 跨 tenant, developer 隔离 |
| Runtime Binding / Eligibility | 17 | publish/install 不自动 binding, enable/disable/suspend, eligibility codes |
| Simulation Runtime | 8 | developer-only, no builtin, requires install/permissions/binding, safety flags |
| Sandbox Policy | 8 | no_execution/simulation_only is_execution_allowed=False, system_managed 不可删除, test 只做静态评估 |
| Package Validation | 4 | admin-only, localhost block, no_download/no_execution flags, no raw_key in result |
| Manifest SDK / Schema | 7 | 不创建 submission, blocks unsafe runtime/network, schema MVP-only, examples safe |
| Usage / Logging Safety | 5 | metadata 不含 raw_key/key_hash, LogRecord reserved key 修复, frontend types 安全 |
| Frontend Security UX | 7 | UI 不含 "Run external code"/"Execute package", 服务不含 publish/execute |

## 2. 测试

| 测试套件 | 数量 | 结果 |
|----------|------|------|
| Step23 Security/Runtime 专项 | 77 | passed |
| Open Platform 全量 | 678 | passed |
| 后端全量回归 | 1325 | passed |

## 3. Minimal Fixes

No code changes required. Tests only.

## 4. Non-Execution Guarantees

所有测试验证以下边界均未突破：
- 不下载 package / 不解压 / 不执行
- 不联网 / 不做 CVE scan
- 不调用 AgentRuntime / AgentRegistry
- 不自动 approve / publish / enable runtime
- API Key 不能 access admin routes
- raw_key/key_hash 不泄露

## 5. 文件清单

| 文件 | 操作 |
|------|------|
| `tests/test_open_platform/test_step23_security_runtime.py` | 新增 (77 tests) |
| `docs/STEP23I_SECURITY_RUNTIME_TESTS.md` | 新增 |
| `docs/ROADMAP.md` | 修改 (23-I ✅) |

## 6. Next Step

Step 23-J：Demo + Documentation
