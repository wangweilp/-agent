# SANDBOX V2 STEP 6A REPORT — Isolation Provider 抽象、能力探测与安全执行契约

**实施日期**: 2026-06-13
**项目**: 黔智脑 Cognitive OS (`D:\dma\day2`)
**步骤**: Sandbox v2 Step 6A — Isolation Provider 抽象、能力探测与 Trusted Fixture 执行契约

---

## 一、本次新增文件

| # | 文件 | 用途 |
|---|------|------|
| 1 | `src/open_platform/sandbox_v2/isolation_capabilities.py` | SandboxIsolationCapabilityProbe — 平台能力探测（detect_platform, check_docker/podman/firecracker/gvisor/kata/namespace/cgroup/seccomp/lsm） |
| 2 | `src/open_platform/sandbox_v2/isolation_policy.py` | Isolation Policy Engine — 14 条安全规则（provider 预留、future 拒绝、resource limits、network/filesystem/package/artifact 约束） |
| 3 | `src/open_platform/sandbox_v2/execution_provider.py` | ExecutionProvider Protocol + DisabledExecutionProvider + TrustedFixtureExecutionProvider + 注册表 |
| 4 | `tests/test_open_platform/test_sandbox_v2_isolation_capabilities.py` | 能力探测测试（8 项） |
| 5 | `tests/test_open_platform/test_sandbox_v2_isolation_policy.py` | 隔离策略测试（18 项） |
| 6 | `tests/test_open_platform/test_sandbox_v2_execution_provider.py` | Provider 测试（13 项） |
| 7 | `tests/test_open_platform/test_sandbox_v2_isolation_service.py` | Service 测试（7 项） |
| 8 | `tests/test_open_platform/test_sandbox_v2_isolation_api.py` | API 测试（13 项） |

**共新增 8 个文件。**

---

## 二、本次修改文件

| # | 文件 | 变更内容 |
|---|------|----------|
| 1 | `src/open_platform/sandbox_v2/models.py` | +1 数据类枚举 + 4 数据类 + 2 常量（IsolationProvider, ExecutionPlanStatus, IsolationCapability, ExecutionPlan, IsolationDecision, TrustedFixtureExecutionResult） |
| 2 | `src/open_platform/sandbox_v2/store.py` | +7 protocol 方法（isolation_capability/execution_plan CRUD） |
| 3 | `src/adapters/sqlite_sandbox_v2_store.py` | +2 个 SQL 表 + 7 个 CRUD 方法 + 2 个 row mapper |
| 4 | `src/open_platform/sandbox_v2/service.py` | 构造函数 +execution_providers 参数；+9 个 isolation 方法 |
| 5 | `src/open_platform/sandbox_v2/worker.py` | 对非 simulation/metadata_only mode 尝试 trusted fixture 路由 |
| 6 | `src/api/sandbox_v2.py` | +1 Pydantic schema + 7 个端点 + readiness +10 字段 |
| 7 | `main.py` | create_default_provider_registry 注入 service |
| 8 | `frontend/types/runtime-admin.ts` | +5 个 TypeScript 接口 |
| 9 | `frontend/services/runtime-admin.ts` | +7 个 API client 方法 |

**共修改 9 个文件。**

---

## 三、新增 API 列表

| 方法 | 路径 | 功能 | 新增于 |
|------|------|------|--------|
| `GET` | `/api/runtime/sandbox-v2/isolation/capabilities` | 收集/返回当前隔离能力探测结果 | Step 6A |
| `GET` | `/api/runtime/sandbox-v2/isolation/readiness` | 返回隔离执行 readiness | Step 6A |
| `POST` | `/api/runtime/sandbox-v2/isolation/execution-plans` | 创建 execution plan | Step 6A |
| `GET` | `/api/runtime/sandbox-v2/isolation/execution-plans` | 列出 execution plans | Step 6A |
| `GET` | `/api/runtime/sandbox-v2/isolation/execution-plans/{id}` | 查看 execution plan | Step 6A |
| `POST` | `/api/runtime/sandbox-v2/isolation/execution-plans/{id}/run-trusted-fixture` | 运行内置 trusted fixture | Step 6A |
| `POST` | `/api/runtime/sandbox-v2/isolation/execution-plans/{id}/cancel` | 取消 execution plan | Step 6A |

Step 1/2/3/4/5 的 37 个端点全部向后兼容。

---

## 四、当前环境能力探测结果

| 能力 | 状态 | 说明 |
|------|------|------|
| 平台 | Windows | 当前运行环境 |
| isolation_capability_probe | ✅ True | 探测接口已实现 |
| execution_provider_abstraction | ✅ True | Provider 协议 + 实现 |
| trusted_fixture_provider | ✅ True | 6 个内置 fixture 可执行 |
| docker_execution | ❌ False | 当前环境 docker 不可用 / disabled |
| podman_execution | ❌ False | 当前环境 podman 不可用 / disabled |
| microvm_execution | ❌ False | 当前环境 firecracker 不可用 / disabled |
| untrusted_code_execution | ❌ False | 不支持 |
| local_process_execution | ❌ False | 不支持 |
| seccomp_enforcement | ❌ False | Windows 不可用 |
| cgroup_enforcement | ❌ False | Windows 不可用 |
| runtime_network_namespace | ❌ False | Windows 不可用 |
| runtime_filesystem_namespace | ❌ False | Windows 不可用 |

---

## 五、Isolation Provider 当前完成能力

### 5.1 Provider 抽象 ✅

| 能力 | 状态 | 说明 |
|------|------|------|
| ExecutionProvider Protocol | ✅ | 5 个方法：get_provider_name, get_capabilities, validate_execution_plan, execute_trusted_fixture, cancel_execution, cleanup |
| DisabledExecutionProvider | ✅ | 永远拒绝真实执行 |
| TrustedFixtureExecutionProvider | ✅ | 6 个 fixture（echo_hello, env_dump, cpu_info, memory_check, filesystem_check, network_check_fail） |
| Provider Registry | ✅ | 默认注册 disabled + trusted_fixture |

### 5.2 能力探测 ✅

| 能力 | 状态 | 说明 |
|------|------|------|
| shutil.which 检测 | ✅ | docker/podman/firecracker/runsc/kata-runtime |
| Linux namespace 检测 | ✅ | /proc/self/ns/user，Windows 返回 unavailable |
| cgroup 检测 | ✅ | /sys/fs/cgroup |
| seccomp 检测 | ✅ | /proc/self/status Seccomp |
| LSM 检测 | ✅ | AppArmor/SELinux |

### 5.3 Isolation Policy ✅

| 能力 | 状态 | 说明 |
|------|------|------|
| 默认 deny | ✅ | 空 provider 拒绝 |
| future 类型 provider 拒绝 | ✅ | docker_rootless_future 等 5 种全部 reject |
| local_process_disabled 拒绝 | ✅ | 不允许本地进程执行 |
| future_container mode 拒绝 | ✅ | job mode 检查 |
| resource limits 必需 | ✅ | 缺 → reject |
| allow_network=true 拒绝 | ✅ | 不允许真实网络 |
| filesystem write 拒绝 | ✅ | 不允许任意写 |
| package install 拒绝 | ✅ | 不允许包安装 |
| artifact 只读 | ✅ | artifact 必须只读 |

### 5.4 Trusted Fixture 执行 ✅

| 能力 | 状态 | 说明 |
|------|------|------|
| echo_hello | ✅ | 返回问候 fixture 文本 |
| env_dump | ✅ | 返回模拟环境变量 |
| cpu_info | ✅ | 返回模拟 CPU 信息 |
| memory_check | ✅ | 返回模拟内存状态 |
| filesystem_check | ✅ | 返回模拟文件系统状态 |
| network_check_fail | ✅ | 正确返回网络不可用（exit_code=6） |
| 拒绝用户 command | ✅ | rm -rf / 等被拒绝 |
| 不调用 subprocess | ✅ | 无 subprocess 模块 |
| 不访问网络 | ✅ | 无 urllib/requests 模块 |
| 生成 execution record | ✅ | 每次执行生成 record |
| 生成 stdout/stderr artifact | ✅ | 只读 artifact |

---

## 六、当前限制（诚实声明）

| 能力 | 状态 | 原因 |
|------|------|------|
| 真实容器执行 | ❌ | docker/podman 二进制在 Windows 可能不存在 |
| 真实 MicroVM 执行 | ❌ | firecracker 不在 Windows 上可用 |
| 真实进程执行 | ❌ | 不调用 subprocess |
| 执行用户代码 | ❌ | 只允许 trusted fixture |
| runtime 网络 namespace | ❌ | Windows 不可用 |
| runtime 文件系统隔离 | ❌ | Windows 不可用 |
| seccomp 强制执行 | ❌ | Windows 不可用 |
| cgroup 资源限制 | ❌ | Windows 不可用 |

---

## 七、测试结果

### 新增测试
```
test_sandbox_v2_isolation_capabilities.py   8 passed
test_sandbox_v2_isolation_policy.py        18 passed
test_sandbox_v2_execution_provider.py      13 passed
test_sandbox_v2_isolation_service.py        7 passed
test_sandbox_v2_isolation_api.py           13 passed
```

### 全部 sandbox v2 测试 (Step 1-6A)
```
330 passed in 13.29s
```

### 全部 test_open_platform
```
3896 passed in 89.14s
```

零回归。

---

## 八、测试覆盖清单

1. ✅ Windows 环境 Linux namespace readiness false
2. ✅ docker/podman/firecracker 不存在时 check 不报错（返回 has_xxx=False）
3. ✅ capability probe 不导入 subprocess
4. ✅ capability probe 不导入 urllib/requests（不访问网络）
5. ✅ isolation policy 默认 deny
6. ✅ docker_rootless_future 被拒绝
7. ✅ podman_rootless_future 被拒绝
8. ✅ gvisor_future 被拒绝
9. ✅ kata_future 被拒绝
10. ✅ firecracker_future 被拒绝
11. ✅ microvm_future 被拒绝
12. ✅ local_process_disabled 被拒绝
13. ✅ trusted_fixture 通过 policy
14. ✅ simulation 通过 policy
15. ✅ 缺少 resource limits 时拒绝
16. ✅ allow_network=true 时拒绝
17. ✅ filesystem 任意写时拒绝
18. ✅ package install 允许时拒绝
19. ✅ future_container mode 拒绝
20. ✅ future_microvm mode 拒绝
21. ✅ DisabledExecutionProvider 永远拒绝执行
22. ✅ TrustedFixtureExecutionProvider 不接受用户 command（rm -rf /）
23. ✅ TrustedFixtureExecutionProvider 不导入 subprocess
24. ✅ TrustedFixtureExecutionProvider 不导入 urllib/requests
25. ✅ 6 个 fixture 全部正确执行
26. ✅ echo_hello 返回 hello 文本
27. ✅ network_check_fail 返回 exit_code=6
28. ✅ run_trusted_fixture 生成 execution record
29. ✅ run_trusted_fixture 生成 stdout/stderr artifact
30. ✅ execution plan 写入 SQLite
31. ✅ execution plan 可查询
32. ✅ cancel execution plan 返回 "No real process was killed"
33. ✅ isolation readiness 字段正确
34. ✅ API capabilities 不返回 500
35. ✅ API run-trusted-fixture 不执行用户代码
36. ✅ 旧 Step 1-5 测试仍通过（330 total）

---

## 九、下一步建议

**建议进入 Step 6B：Rootless Container / Podman / Docker 最小隔离执行 PoC**

前置条件：Linux 服务器或 VM

具体任务：

1. 配置 Linux 测试环境
2. 安装 Docker 或 Podman (rootless mode)
3. 创建最小 rootless container image
4. 配置 seccomp profile（默认 deny）
5. 实现 RootlessContainerSandboxWorker
6. 配置 read-only rootfs + no-new-privileges
7. 配置 network namespace（默认无网络）
8. 配置 cgroups v2
9. 受控 trusted fixture 在容器中运行
10. 不执行不可信代码

---

## 十、命令速查

```bash
# 运行 isolation 测试
python -m pytest tests/test_open_platform/test_sandbox_v2_isolation_*.py tests/test_open_platform/test_sandbox_v2_execution_provider.py -q -v

# 运行全部 sandbox v2 测试
python -m pytest tests/test_open_platform/test_sandbox_v2_*.py -q

# 运行完整 test_open_platform
python -m pytest tests/test_open_platform -q
```
