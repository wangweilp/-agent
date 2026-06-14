# SANDBOX V2 STEP 11 REPORT — MicroVM / Firecracker PoC

**实施日期**: 2026-06-13
**项目**: 黔智脑 Cognitive OS (`D:\dma\day2`)
**步骤**: Sandbox v2 Step 11 — MicroVM / Firecracker Provider PoC

---

## 一、本次新增文件

| # | 文件 | 用途 |
|---|------|------|
| 1 | `src/open_platform/sandbox_v2/microvm_policy.py` | MicroVM 策略引擎（12 条安全规则：默认 deny，fail closed） |
| 2 | `src/open_platform/sandbox_v2/microvm_provider.py` | Firecracker MicroVM ExecutionProvider + CommandBuilder（构建配置，不执行） |
| 3 | `scripts/check_sandbox_v2_microvm_preflight.py` | MicroVM preflight 检查脚本（JSON + 人类可读输出） |
| 4 | `docs/sandbox-v2-microvm-firecracker-poc.md` | MicroVM/Firecracker PoC 文档 |
| 5 | `tests/test_open_platform/test_sandbox_v2_microvm_policy.py` | MicroVM 策略测试（14 项） |
| 6 | `tests/test_open_platform/test_sandbox_v2_microvm_provider.py` | MicroVM Provider 测试（16 项） |
| 7 | `tests/test_open_platform/test_sandbox_v2_microvm_service.py` | MicroVM Service 集成测试（14 项） |
| 8 | `tests/test_open_platform/test_sandbox_v2_microvm_api.py` | MicroVM API 测试（11 项） |
| 9 | `tests/test_open_platform/integration/test_sandbox_v2_firecracker_microvm_fixture.py` | 集成测试（默认 skip，需 Linux+KVM） |

**共新增 9 个文件。**

---

## 二、本次修改文件

| # | 文件 | 变更内容 |
|---|------|----------|
| 1 | `src/open_platform/sandbox_v2/models.py` | +3 个枚举（SandboxMicroVMRuntime, SandboxMicroVMExecutionStatus），+4 个数据类（Config/Plan/Result/PreflightResult），+Trusted fixtures 字典，+KillTarget 枚举增加 MICROVM_PLAN/MICROVM，STEP6A_ALLOWED_PROVIDERS 增加 FIRECRACKER_FUTURE/MICROVM_FUTURE |
| 2 | `src/open_platform/sandbox_v2/config.py` | +13 个 MicroVM 配置字段；is_safe_default()/production_blockers()/load_settings() 包含 MicroVM |
| 3 | `src/open_platform/sandbox_v2/isolation_capabilities.py` | +6 个 MicroVM 探测方法（detect_kvm, check_microvm_firecracker_binary, check_microvm_kernel_exists, check_microvm_rootfs_exists, check_microvm_preconditions, get_microvm_readiness_summary） |
| 4 | `src/open_platform/sandbox_v2/isolation_policy.py` | （间接：STEP6A_ALLOWED_PROVIDERS 变更已包含） |
| 5 | `src/open_platform/sandbox_v2/kill_policy.py` | +1 条 MicroVM rule（默认 disabled，No real MicroVM process to kill） |
| 6 | `src/open_platform/sandbox_v2/store.py` | +7 个 MicroVM store 方法签名 |
| 7 | `src/adapters/sqlite_sandbox_v2_store.py` | +2 张 SQLite 表（sandbox_v2_microvm_execution_plans/results）+ 7 个 CRUD 方法 + 2 个 row mapper |
| 8 | `src/api/sandbox_v2.py` | ReadinessResponse +14 MicroVM 字段；+8 个 MicroVM API 端点 |
| 9 | `frontend/types/runtime-admin.ts` | +14 TypeScript MicroVM 字段 |
| 10 | `.env.sandbox-v2.example` | +12 个 MicroVM 环境变量（全部默认安全关闭） |
| 11 | `tests/test_open_platform/test_sandbox_v2_container_policy.py` | 1 个测试更新：firecracker_future 现允许创建 plan |
| 12 | `tests/test_open_platform/test_sandbox_v2_isolation_policy.py` | 2 个测试更新：microvm/firecracker 现允许创建 plan |
| 13 | `tests/test_open_platform/red_team/test_sandbox_v2_red_team_container_escape.py` | 2 个测试更新：执行仍被 microvm_policy 阻止 |

**共修改 13 个文件。**

---

## 三、新增配置项（全部默认安全关闭）

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `SANDBOX_V2_MICROVM_EXECUTION_ENABLED` | **`false`** | 启用 MicroVM 执行 |
| `SANDBOX_V2_RUN_MICROVM_INTEGRATION` | **`false`** | 启用 MicroVM 集成 |
| `SANDBOX_V2_FIRECRACKER_BIN_PATH` | (空) | Firecracker binary 路径 |
| `SANDBOX_V2_FIRECRACKER_KERNEL_PATH` | (空) | MicroVM kernel 路径 |
| `SANDBOX_V2_FIRECRACKER_ROOTFS_PATH` | (空) | MicroVM rootfs 路径 |
| `SANDBOX_V2_FIRECRACKER_JAILER_ENABLED` | `false` | Firecracker jailer |
| `SANDBOX_V2_MICROVM_NETWORK_ENABLED` | **`false`** | MicroVM 网络 |
| `SANDBOX_V2_MICROVM_MAX_MEMORY_MB` | `128` | 最大内存 (MB) |
| `SANDBOX_V2_MICROVM_VCPU_COUNT` | `1` | vCPU 数 |
| `SANDBOX_V2_MICROVM_TIMEOUT_SECONDS` | `10` | 超时秒数 |
| `SANDBOX_V2_MICROVM_ALLOW_USER_KERNEL` | **`false`** | 用户 kernel |
| `SANDBOX_V2_MICROVM_ALLOW_USER_ROOTFS` | **`false`** | 用户 rootfs |
| `SANDBOX_V2_MICROVM_ALLOW_HOST_MOUNTS` | **`false`** | 宿主机挂载 |

**所有危险能力默认 `false`。**

---

## 四、新增 API 列表

| 方法 | 路径 | 功能 |
|------|------|------|
| `GET` | `/api/runtime/sandbox-v2/isolation/microvm/preflight` | MicroVM 前置条件检查 |
| `GET` | `/api/runtime/sandbox-v2/isolation/microvm/readiness` | MicroVM readiness 状态 |
| `POST` | `/api/runtime/sandbox-v2/isolation/microvm-plans` | 创建 MicroVM execution plan |
| `GET` | `/api/runtime/sandbox-v2/isolation/microvm-plans` | 列出 MicroVM plans |
| `GET` | `/api/runtime/sandbox-v2/isolation/microvm-plans/{id}` | 查看 MicroVM plan |
| `POST` | `/api/runtime/sandbox-v2/isolation/microvm-plans/{id}/run-trusted-fixture` | 运行/预检 MicroVM trusted fixture |
| `GET` | `/api/runtime/sandbox-v2/isolation/microvm-results` | 列出 MicroVM results |
| `GET` | `/api/runtime/sandbox-v2/isolation/microvm-results/{id}` | 查看 MicroVM result |

---

## 五、MicroVM Provider 当前能力

| 能力 | 状态 | 说明 |
|------|------|------|
| MicroVM Provider 抽象 | ✅ | 遵循现有 ExecutionProvider 模式 |
| MicroVM Policy Engine | ✅ | 12 条安全规则：默认 deny + fail closed |
| Firecracker CommandBuilder | ✅ | 参数数组，不使用 shell=True |
| Firecracker Config Builder | ✅ | 包含 boot-source/drives/machine-config |
| 能力探测 (Preflight) | ✅ | KVM + binary + kernel + rootfs 检查 |
| Execution Plan CRUD | ✅ | SQLite 表 + store 方法 |
| Execution Result CRUD | ✅ | SQLite 表 + store 方法 |
| Trusted Fixture | ✅ | `hello-microvm-fixture` |
| Kill Switch 集成 | ✅ | Target type MICROVM_PLAN/MICROVM（默认 disabled） |
| API 端点 | ✅ | 8 个端点 |
| Preflight Script | ✅ | `scripts/check_sandbox_v2_microvm_preflight.py` |
| 真实 Firecracker 执行 | ❌ | 未实现（PoC 范围） |
| MicroVM fleet 管理 | ❌ | 未实现 |
| Firecracker jailer | ❌ | Command 构建已实现，真实隔离未验证 |
| Tap 网络隔离 | ❌ | 默认禁用网络 |
| MicroVM 镜像签名 | ❌ | 未实现 |
| 多租户 MicroVM 调度 | ❌ | 未实现 |

---

## 六、MicroVM Preflight 结果（当前 Windows 环境）

```
======================================================================
  Sandbox v2 MicroVM / Firecracker Preflight Check
======================================================================
  Platform: Windows
  Linux: False | Windows: True

  [FAIL] KVM: Not Linux — KVM unavailable.
  [FAIL] Firecracker binary: firecracker binary not found
  [FAIL] Kernel: Kernel path not configured
  [FAIL] Rootfs: Rootfs path not configured

  Execution enabled: False
  Integration enabled: False
  Network disabled: True

  [BLOCKERS] (7):
     - Platform is not Linux
     - /dev/kvm not available
     - Firecracker binary not found
     - MicroVM kernel not found
     - MicroVM rootfs not found
     - SANDBOX_V2_MICROVM_EXECUTION_ENABLED not true
     - SANDBOX_V2_RUN_MICROVM_INTEGRATION not true

  [NOT READY] MicroVM runnable: False
======================================================================
```

**MicroVM 在 Windows 上不可运行。**

---

## 七、是否真实运行了 Firecracker

**❌ 未运行。**

原因：
1. Windows 原生环境无 KVM
2. Firecracker binary 未安装
3. MicroVM kernel/rootfs 未配置
4. `SANDBOX_V2_MICROVM_EXECUTION_ENABLED=false`
5. `SANDBOX_V2_RUN_MICROVM_INTEGRATION=false`

需要通过以下条件在 Linux 上验证：
```bash
export SANDBOX_V2_MICROVM_EXECUTION_ENABLED=true
export SANDBOX_V2_RUN_MICROVM_INTEGRATION=true
# + Linux + KVM + Firecracker + kernel + rootfs
```

---

## 八、测试结果

### MicroVM 新增测试
```
55 passed in 5.84s
```

### 集成测试（默认 skip）
```
7 skipped in 0.24s
```

### 全部 Sandbox v2 测试
```
670 passed, 9 skipped in 39.94s
```

### Red-Team 测试
```
132 passed in 6.49s
```

### Preflight Script
```
EXIT CODE 1 — 7 blockers (Windows, not Linux)
```

### 前端构建
```
✓ Compiled successfully
0 TypeScript errors
```

---

## 九、当前仍缺什么

| 能力 | 状态 | 原因 |
|------|------|------|
| 真实 Linux Firecracker 验证 | [WARN] | Windows 环境无 KVM |
| jailer 真实隔离 | [WARN] | 未验证 |
| MicroVM 镜像签名 | [WARN] | 未实现 |
| MicroVM fleet 调度 | [WARN] | 未实现 |
| tap 网络隔离 | [WARN] | 未实现（默认禁用） |
| 多租户资源调度 | [WARN] | 未实现 |
| 真实攻击面测试 | [WARN] | 需 Linux 环境 |
| 真实 PostgreSQL 集成压测 | [WARN] | Step 13 |
| 真实 Redis 集成压测 | [WARN] | Step 13 |

---

## 十、下一步建议

### 建议 Step 13：真实 PostgreSQL / Redis / MinIO 集成测试

- Linux 环境准备
- PostgreSQL 真实连接与压测
- Redis 真实连接与压测
- MinIO 真实上传/下载测试

### 或 Step 14：权限、多租户和审计强化

- RBAC 权限集成
- 多租户数据隔离
- 审计日志增强

### 或 Step 15：监控、告警与指标

- 监控 dashboard
- 告警规则
- 指标导出

---

## 十一、命令速查

```bash
# MicroVM 测试
python -m pytest tests/test_open_platform/test_sandbox_v2_microvm_*.py -q -v

# 集成测试（需 Linux+KVM，默认 skip）
python -m pytest tests/test_open_platform/integration/test_sandbox_v2_firecracker_microvm_fixture.py -q -v

# Preflight 检查
python scripts/check_sandbox_v2_microvm_preflight.py

# 全部 Sandbox v2 测试
python -m pytest tests/test_open_platform/ -q --ignore=tests/test_open_platform/red_team -k "sandbox_v2"

# Red-Team 测试
python -m pytest tests/test_open_platform/red_team -q

# 前端构建
cd frontend && npm run build
```

---

## 十二、执行原则确认

- [OK] 未执行用户代码
- [OK] 未执行用户 command
- [OK] 未使用用户 kernel/rootfs
- [OK] 未自动下载 kernel/rootfs/Firecracker
- [OK] 未联网
- [OK] 未安装包
- [OK] 未默认启用 MicroVM
- [OK] 未默认启用容器
- [OK] 未使用 shell=True
- [OK] 未挂载宿主机目录
- [OK] 未暴露宿主机网络
- [OK] 未绕过任何 Policy
- [OK] Windows 上正确显示 unavailable
- [OK] 未破坏 Step 1-10、Step 12 已通过测试（670 passed, 132 red-team）  
- [OK] 未大改已有后端核心逻辑
