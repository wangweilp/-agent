# SANDBOX V2 STEP 6B REPORT — Rootless Container / Podman / Docker 最小隔离执行 PoC

**实施日期**: 2026-06-13
**项目**: 黔智脑 Cognitive OS (`D:\dma\day2`)
**步骤**: Sandbox v2 Step 6B — Rootless Container Provider 最小 PoC

---

## 一、本次新增文件

| # | 文件 | 用途 |
|---|------|------|
| 1 | `src/open_platform/sandbox_v2/container_provider.py` | ContainerCommandBuilder + RootlessContainerExecutionProvider（实现 ExecutionProvider Protocol，默认 disabled） |
| 2 | `tests/test_open_platform/test_sandbox_v2_container_provider.py` | Container Provider 测试（20 项） |
| 3 | `tests/test_open_platform/test_sandbox_v2_container_policy.py` | Container Policy 测试（7 项） |
| 4 | `tests/test_open_platform/test_sandbox_v2_container_service.py` | Container Service 测试（4 项） |
| 5 | `tests/test_open_platform/test_sandbox_v2_container_api.py` | Container API 测试（11 项） |

**共新增 5 个文件。**

---

## 二、本次修改文件

| # | 文件 | 变更内容 |
|---|------|----------|
| 1 | `src/open_platform/sandbox_v2/models.py` | +2 枚举 + 3 数据类 + 2 常量（ContainerRuntime, ContainerExecutionStatus, ContainerRuntimeConfig, ContainerExecutionPlan, ContainerExecutionResult, TRUSTED_CONTAINER_FIXTURES, DEFAULT_ALLOWED_IMAGES）；+2 provider 入 STEP6A |
| 2 | `src/open_platform/sandbox_v2/isolation_policy.py` | +Container provider 特殊检查规则（network disabled 必须、filesystem write disabled 必须） |
| 3 | `src/open_platform/sandbox_v2/store.py` | +7 protocol 方法（container plan/result CRUD） |
| 4 | `src/adapters/sqlite_sandbox_v2_store.py` | +2 个 SQL 表 + 7 个 CRUD 方法 + 2 个 row mapper |
| 5 | `src/open_platform/sandbox_v2/service.py` | +8 个 container 方法 |
| 6 | `src/api/sandbox_v2.py` | +1 Pydantic schema + 6 个 endpoints + readiness +13 字段 |
| 7 | `main.py` | RootlessContainerExecutionProvider 初始化注入（docker+podman，默认 disabled） |
| 8 | `frontend/types/runtime-admin.ts` | +5 个 TypeScript 接口 |
| 9 | `frontend/services/runtime-admin.ts` | +6 个 API client 方法 |
| 10 | `tests/test_open_platform/test_sandbox_v2_isolation_policy.py` | -1 测试用例更新（docker_rootless_future 现在允许通过） |
| 11 | `tests/test_open_platform/test_sandbox_v2_isolation_service.py` | -1 测试用例更新 |

**共修改 11 个文件。**

---

## 三、新增 API 列表

| 方法 | 路径 | 功能 | 新增于 |
|------|------|------|--------|
| `POST` | `/api/runtime/sandbox-v2/isolation/container-plans` | 创建 container execution plan | Step 6B |
| `GET` | `/api/runtime/sandbox-v2/isolation/container-plans` | 列出 container plans | Step 6B |
| `GET` | `/api/runtime/sandbox-v2/isolation/container-plans/{id}` | 查看 container plan | Step 6B |
| `POST` | `/api/runtime/sandbox-v2/isolation/container-plans/{id}/run-trusted-fixture` | 运行 container trusted fixture | Step 6B |
| `GET` | `/api/runtime/sandbox-v2/isolation/container-results` | 列出 container results | Step 6B |
| `GET` | `/api/runtime/sandbox-v2/isolation/container-results/{id}` | 查看 container result | Step 6B |

Step 1/2/3/4/5/6A 的 44 个端点全部向后兼容。

---

## 四、Container Provider 当前完成能力

### 4.1 ContainerCommandBuilder ✅

| 能力 | 状态 | 说明 |
|------|------|------|
| Docker 命令构建 | ✅ | 完整安全参数数组，不使用 shell=True |
| Podman 命令构建 | ✅ | 完整安全参数数组 |
| `--network=none` | ✅ | 强制无网络 |
| `--read-only` | ✅ | 只读 rootfs |
| `--cap-drop=ALL` | ✅ | 丢弃所有 capabilities |
| `--security-opt=no-new-privileges` | ✅ | 禁止提权 |
| `--pids-limit` | ✅ | 进程数限制 |
| `--memory` / `--cpus` | ✅ | 资源限制 |
| `--user=65532:65532` | ✅ | 非 root 用户 |
| `--tmpfs` | ✅ | tmpfs noexec/nosuid |
| 无 `--privileged` | ✅ | 永不使用特权模式 |
| 无 `--network=host` | ✅ | 永不使用主机网络 |
| 无 docker.sock 挂载 | ✅ | 永不挂载 Docker socket |
| 无 shell=True | ✅ | 参数数组形式 |

### 4.2 RootlessContainerExecutionProvider ✅

| 能力 | 状态 | 说明 |
|------|------|------|
| 默认 disabled | ✅ | 需 `SANDBOX_V2_CONTAINER_EXECUTION_ENABLED=true` |
| 只 Linux 真实执行 | ✅ | Windows 返回 unavailable |
| Runtime binary 检查 | ✅ | docker/podman 不存在 → unavailable |
| 本地镜像检查 | ✅ | `docker image inspect`，不 pull |
| 只允许 trusted fixture | ✅ | 4 个内置 fixture |
| 拒绝用户 command | ✅ | 非内置 fixture 一律拒绝 |
| 拒绝非允许 image | ✅ | 默认 python:3.11-alpine, busybox:latest |
| 超时处理 | ✅ | subprocess.TimeoutExpired → timeout 状态 |
| 错误 fail closed | ✅ | 任何异常标记 unhealthy/rejected |
| cancel 不杀进程 | ✅ | 返回 no active process |

---

## 五、当前限制（诚实声明）

| 能力 | 状态 | 原因 |
|------|------|------|
| 真实容器执行 | ⚠️ | 需要 `SANDBOX_V2_CONTAINER_EXECUTION_ENABLED=true` + Linux + Docker/Podman |
| Windows 原生容器 | ❌ | 不支持，返回 unavailable |
| 自动拉取镜像 | ❌ | 本地镜像不存在时返回 unavailable |
| 用户自定义 command | ❌ | 只允许 trusted fixture |
| 用户自定义 image | ❌ | 只在 allowlist 中 |
| 网络访问 | ❌ | `--network=none` |
| gVisor/Kata/Firecracker | ❌ | 继续拒绝 |
| MicroVM | ❌ | 继续拒绝 |
| 分布式 worker 容器 | ❌ | 单机 PoC |

---

## 六、当前环境探测结果

| 能力 | 状态 |
|------|------|
| 平台 | Windows |
| container_provider_abstraction | ✅ True |
| rootless_container_poc | ✅ True |
| container_execution_enabled | ❌ False |
| docker_available | 探测结果 |
| podman_available | 探测结果 |
| rootless_container_available | ❌ False (Windows) |
| microvm_execution | ❌ False |

---

## 七、测试结果

### 新增测试
```
test_sandbox_v2_container_provider.py  20 passed
test_sandbox_v2_container_policy.py     7 passed
test_sandbox_v2_container_service.py    4 passed
test_sandbox_v2_container_api.py       11 passed
```

### 全部 sandbox v2 测试 (Step 1-6B)
```
372 passed in 25.92s
```

### 全部 test_open_platform
```
3938 passed in 157.16s
```

零回归。

---

## 八、测试覆盖清单

1. ✅ 默认 container execution disabled
2. ✅ Windows 环境下 real execution unavailable
3. ✅ 未设置环境变量时拒绝真实执行
4. ✅ 不允许用户 command
5. ✅ 不允许用户 image（不在 allowlist）
6. ✅ 不允许 privileged
7. ✅ 不允许 network host
8. ✅ `--network=none` 存在于命令中
9. ✅ `--read-only` 存在于命令中
10. ✅ `--cap-drop=ALL` 存在于命令中
11. ✅ `--security-opt=no-new-privileges` 存在于命令中
12. ✅ `--user=65532:65532` 存在于命令中
13. ✅ `--pids-limit` / `--memory` / `--cpus` 存在于命令中
14. ✅ 不使用 shell=True（参数数组）
15. ✅ 不挂载 docker.sock
16. ✅ 不包含 `--privileged`
17. ✅ 不包含 `--network=host`
18. ✅ allowed image 以外被拒绝
19. ✅ trusted fixture 以外被拒绝
20. ✅ container plan 写入 SQLite
21. ✅ container result 可写入 SQLite
22. ✅ run-trusted-fixture 在未启用时返回 disabled/unavailable，不 500
23. ✅ readiness 字段正确
24. ✅ 旧 Step 1-6A 测试仍通过

---

## 九、下一步建议

**建议进入 Step 6C：在 Linux/WSL2 rootless Docker 或 Podman 环境中做真实运行验证**

具体任务：

1. Linux/WSL2 环境准备
2. 安装 Docker/Podman rootless
3. 设置 `SANDBOX_V2_CONTAINER_EXECUTION_ENABLED=true`
4. 预拉取 `python:3.11-alpine` 镜像
5. 运行 container trusted fixture 真实容器验证
6. 验证 stdout/stderr artifact 写入
7. 验证执行隔离
8. 记录真实运行测试结果

或

**建议进入 Step 7：Kill Switch 与进程终止能力**

具体任务：

1. 扩展 KillSwitch policy 支持 container process
2. 实现 `docker kill` / `podman kill` 容器的能力
3. 超时自动 kill
4. Kill audit 记录
5. 不假装杀进程（对有真实进程时真正 kill）

---

## 十、命令速查

```bash
# 运行 container 测试
python -m pytest tests/test_open_platform/test_sandbox_v2_container_*.py tests/test_open_platform/test_sandbox_v2_container_policy.py -q -v

# 真实容器运行（需 Linux + SANDBOX_V2_CONTAINER_EXECUTION_ENABLED=true）
python -m pytest tests/test_open_platform/test_sandbox_v2_container_provider.py -q -v

# 运行完整 test_open_platform
python -m pytest tests/test_open_platform -q
```
