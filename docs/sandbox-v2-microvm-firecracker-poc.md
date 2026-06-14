# Sandbox v2 — MicroVM / Firecracker PoC

**版本**: Step 11  
**最后更新**: 2026-06-13  
**目标受众**: 安全工程师 / SRE / 架构师

---

## 一、Step 11 目标

为 Sandbox v2 增加 MicroVM / Firecracker Provider 的 PoC 基础，包括：
- MicroVM Provider 抽象（遵循现有 ExecutionProvider 接口）
- Firecracker 能力探测 (preflight)
- MicroVM 执行计划和结果管理
- MicroVM 策略引擎（默认 deny，fail closed）
- API 端点
- 前端状态展示
- 默认禁用，显式环境变量开启

---

## 二、为什么 MicroVM 比容器隔离更强

| 对比维度 | 容器 (Docker/Podman) | MicroVM (Firecracker) |
|----------|----------------------|----------------------|
| Kernel | 共享宿主 kernel | 独立 guest kernel |
| Attack surface | 系统调用过滤 (seccomp) | 硬件虚拟化隔离 |
| Escape risk | 较高 (kernel 共享) | 极低 (独立 kernel) |
| 启动速度 | 毫秒级 | 几十毫秒 |
| 内存开销 | 低 | ~5MB+ per VM |
| 适用场景 | 常规隔离 | 高安全隔离 |

---

## 三、当前默认 disabled

MicroVM 执行**默认完全禁用**。以下所有条件必须同时满足才能运行：

1. Linux 宿主
2. KVM 可用 (`/dev/kvm`)
3. Firecracker binary 已安装
4. MicroVM kernel image 已准备
5. MicroVM rootfs image 已准备
6. `SANDBOX_V2_MICROVM_EXECUTION_ENABLED=true`
7. `SANDBOX_V2_RUN_MICROVM_INTEGRATION=true`
8. `SANDBOX_V2_MICROVM_NETWORK_ENABLED=false`
9. 只允许 trusted fixture
10. 不允许用户 kernel/rootfs/command/mounts

---

## 四、为什么不允许用户 kernel/rootfs/command

- **用户 kernel**: 攻击者可加载恶意内核模块，绕过所有隔离
- **用户 rootfs**: 攻击者可在 rootfs 中预置提权脚本
- **用户 command**: 等同于允许任意代码执行
- **网络**: 数据泄露通道
- **Host mounts**: 直接宿主机文件系统访问

所有以上能力在生产中必须**永久关闭**。

---

## 五、Linux 环境前置条件

### 5.1 KVM

```bash
# 检查 KVM
ls -la /dev/kvm
# 加载 KVM 模块
sudo modprobe kvm
sudo modprobe kvm_intel  # or kvm_amd
```

### 5.2 Firecracker

```bash
# 安装（需 Linux）
# https://github.com/firecracker-microvm/firecracker/releases
wget https://github.com/firecracker-microvm/firecracker/releases/download/v1.10.1/firecracker-v1.10.1-x86_64.tgz
tar xzf firecracker-v1.10.1-x86_64.tgz
chmod +x release-v1.10.1-x86_64/firecracker-v1.10.1-x86_64
```

### 5.3 Kernel Image

```bash
# 使用官方 demo kernel
wget https://s3.amazonaws.com/spec.ccfc.min/firecracker-ci/v1.10/x86_64/vmlinux-5.10.225
```

### 5.4 Rootfs

```bash
# 使用官方 demo rootfs
wget https://s3.amazonaws.com/spec.ccfc.min/firecracker-ci/v1.10/x86_64/ubuntu-22.04.ext4
```

---

## 六、环境变量配置

```bash
# 启用 MicroVM（默认 false）
export SANDBOX_V2_MICROVM_EXECUTION_ENABLED=true

# 启用 MicroVM 集成（默认 false）
export SANDBOX_V2_RUN_MICROVM_INTEGRATION=true

# Firecracker binary 路径
export SANDBOX_V2_FIRECRACKER_BIN_PATH=/path/to/firecracker

# Kernel 路径
export SANDBOX_V2_FIRECRACKER_KERNEL_PATH=/path/to/vmlinux

# Rootfs 路径
export SANDBOX_V2_FIRECRACKER_ROOTFS_PATH=/path/to/rootfs.ext4

# 以下必须保持 false
export SANDBOX_V2_MICROVM_NETWORK_ENABLED=false
export SANDBOX_V2_MICROVM_ALLOW_USER_KERNEL=false
export SANDBOX_V2_MICROVM_ALLOW_USER_ROOTFS=false
export SANDBOX_V2_MICROVM_ALLOW_HOST_MOUNTS=false
```

---

## 七、如何运行 Preflight

```bash
# 人类可读输出
python scripts/check_sandbox_v2_microvm_preflight.py

# JSON 输出
python scripts/check_sandbox_v2_microvm_preflight.py --json
```

---

## 八、集成测试

```bash
# 默认 skip 的集成测试
python -m pytest tests/test_open_platform/integration/test_sandbox_v2_firecracker_microvm_fixture.py -q -v
```

仅在所有前置条件满足（见第三节）时才运行真实测试。
否则所有测试自动 skip。

---

## 九、Windows 原生环境为什么不可运行

- KVM 是 Linux 内核模块，Windows 没有 `/dev/kvm`
- Firecracker 依赖 KVM API
- MicroVM 隔离模式只能在 Linux 宿主实现
- WSL2 中 KVM 也有限制（取决于 WSL 版本和配置）

**在 Windows 上 MicroVM 永远是 unavailable。**

---

## 十、当前限制（诚实声明）

| 限制 | 状态 | 说明 |
|------|------|------|
| 真实 Firecracker 执行 | ❌ | PoC 不启动真实 Firecracker |
| MicroVM fleet 管理 | ❌ | 未实现 |
| Jailer 真实隔离 | ❌ | 未实现 |
| Tap 网络隔离 | ❌ | 未实现（默认禁用网络） |
| MicroVM 镜像签名 | ❌ | 未实现 |
| 多租户 MicroVM 调度 | ❌ | 未实现 |
| 真实攻击面测试 | ❌ | 需 Linux 环境 |
| 性能基准测试 | ❌ | 需 Linux 环境 |

---

## 十一、下一步建议

- **Step 13**: 真实 PostgreSQL / Redis / MinIO 集成测试
- **Step 14**: 权限、多租户和审计强化
- **Step 15**: 监控、告警与指标
