# SANDBOX V2 STEP 6C REPORT — Linux/WSL2 Rootless Container Trusted Fixture 真实验证

**实施日期**: 2026-06-13
**项目**: 黔智脑 Cognitive OS (`D:\dma\day2`)
**步骤**: Sandbox v2 Step 6C — Real Container Trusted Fixture Validation

---

## 一、本次新增文件

| # | 文件 | 用途 |
|---|------|------|
| 1 | `tests/test_open_platform/integration/test_sandbox_v2_real_container_fixture.py` | 集成测试：默认 skip，env+Linux+Docker+image 满足时才运行 |
| 2 | `scripts/run_sandbox_v2_container_fixture_check.py` | 环境预检与验证脚本 |
| 3 | `docs/sandbox-v2-real-container-fixture.md` | 文档：安全边界、环境准备、手动预拉取镜像、API 用法 |

**共新增 3 个文件。**

---

## 二、本次修改文件

| # | 文件 | 变更内容 |
|---|------|----------|
| 1 | `src/open_platform/sandbox_v2/isolation_capabilities.py` | +4 个方法：detect_wsl2, check_local_image_exists, get_container_runtime_info, check_container_execution_preconditions |
| 2 | `src/open_platform/sandbox_v2/container_provider.py` | +run_real_trusted_fixture 方法（完整安全参数、container name 生成、subprocess.run shell=False、超时 kill）+ get_container_runtime_preflight |
| 3 | `src/open_platform/sandbox_v2/service.py` | +2 个方法：get_container_runtime_preflight, run_real_container_trusted_fixture（含 artifact/execution_record/container_result 持久化） |
| 4 | `src/api/sandbox_v2.py` | +2 个 endpoint + readiness +7 个字段 |
| 5 | `tests/test_open_platform/test_sandbox_v2_isolation_capabilities.py` | 适配测试：不再检查 source 中的 "subprocess" 字符串 |

**共修改 5 个文件。**

---

## 三、新增 API 列表

| 方法 | 路径 | 功能 | 新增于 |
|------|------|------|--------|
| `GET` | `/api/runtime/sandbox-v2/isolation/container-runtime/preflight` | 完整前置条件检查（platform/docker/podman/image/env/runnable） | Step 6C |
| `POST` | `/api/runtime/sandbox-v2/isolation/container-plans/{id}/run-real-trusted-fixture` | 运行真实容器 trusted fixture（opt-in） | Step 6C |

Step 1—8 的 58 个端点全部向后兼容。

---

## 四、当前环境 Preflight 结果

```
Platform:                  Windows 11
Is Linux:                  False
Docker available:          False
Podman available:          False
Runtime:                   unavailable
Image (python:3.11-alpine): NOT FOUND
CONTAINER_EXECUTION_ENABLED: False
RUN_CONTAINER_INTEGRATION:   False
CAN RUN REAL FIXTURE:     NO

Reasons:
- Not Linux/WSL2.
- No Docker/Podman found.
- Env vars not set.
- Image not available.
```

---

## 五、是否真实运行了 Container Trusted Fixture？

**否。** 当前环境为 Windows 原生，无 Docker/Podman，无环境变量，无本地镜像。

所有前置条件检查已实现，代码已就绪。当在 Linux/WSL2 环境中设置正确的环境变量并预拉取镜像后，可以运行：

```bash
# 预检
python scripts/run_sandbox_v2_container_fixture_check.py

# 集成测试
python -m pytest tests/test_open_platform/integration/test_sandbox_v2_real_container_fixture.py -q -v
```

---

## 六、新增能力总结

### 6C.1 容器运行时 Preflight ✅

| 能力 | 状态 | 说明 |
|------|------|------|
| OS 检测（Linux/WSL2/Windows） | ✅ | detect_wsl2 + detect_platform |
| Runtime binary 检测 | ✅ | shutil.which |
| Runtime info 检测 | ✅ | docker/podman info，不启动容器 |
| 本地镜像检查 | ✅ | docker/podman image inspect，不 pull |
| env var 检查 | ✅ | SANDBOX_V2_CONTAINER_EXECUTION_ENABLED + SANDBOX_V2_RUN_CONTAINER_INTEGRATION |
| 综合 runnable 判断 | ✅ | 所有条件 AND |

### 6C.2 Real Trusted Fixture 执行 ✅

| 能力 | 状态 | 说明 |
|------|------|------|
| run_real_trusted_fixture | ✅ | 所有安全参数强制存在 |
| 只允许 trusted fixture | ✅ | TRUSTED_CONTAINER_FIXTURES 硬编码 |
| 只允许 allowed_images | ✅ | python:3.11-alpine, busybox:latest |
| 镜像必须本地存在 | ✅ | 不存在 → image_not_found |
| subprocess.run shell=False | ✅ | 参数数组 |
| 容器名称系统生成 | ✅ | sandboxv2-{job_id}-{random} |
| 超时 kill | ✅ | 调用 cancel_execution |
| stdout/stderr artifact | ✅ | 只读 |
| ContainerExecutionResult | ✅ | SQLite 持久化 |
| SandboxExecutionRecord | ✅ | metadata 含 real_container_fixture=true |

---

## 七、测试结果

### 集成测试
```
2 skipped (env vars not set, not Linux)
4 passed (preflight, disabled path, command safety)
```

### 全部 test_open_platform
```
4109 passed, 2 skipped in 95.17s
```

零回归。

---

## 八、当前仍缺什么

| 能力 | 状态 | 原因 |
|------|------|------|
| 真实容器执行验证 | ⚠️ | 需 Linux/WSL2 + Docker/Podman + 显式 env vars + 预拉取镜像 |
| MicroVM (Firecracker) | ❌ | 未实现 |
| gVisor/Kata Containers | ❌ | 未实现 |
| 生产级镜像签名 | ❌ | 未实现 |
| 多租户容器隔离 | ❌ | 未实现 |
| 运行时 seccomp profile 自定义 | ❌ | 未实现 |
| AppArmor/SELinux | ❌ | 未实现 |

---

## 九、下一步建议

**建议进入 Step 9：Runtime Admin 前端可视化整合**

具体任务：

1. Runtime Admin Dashboard 整合 Sandbox v2 所有步骤的状态可视
2. 在 `/admin/runtime` 页面增加 Sandbox v2 tab
3. 展示 Step 1-8 各项能力状态卡片
4. 集成 readiness API 数据到前端
5. 显示 Kill Switch 状态、Red-Team 测试状态
6. 不做大改页面布局，使用现有组件体系

---

## 十、命令速查

```bash
# 环境预检
python scripts/run_sandbox_v2_container_fixture_check.py

# 集成测试（需要 env vars + Linux + Docker + image）
python -m pytest tests/test_open_platform/integration/test_sandbox_v2_real_container_fixture.py -q -v

# 全部测试
python -m pytest tests/test_open_platform -q
```
