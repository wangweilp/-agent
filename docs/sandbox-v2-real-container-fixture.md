# Sandbox v2 — Real Container Trusted Fixture Validation (Step 6C)

## 安全边界

此步骤在 Linux/WSL2 + Docker/Podman 环境中验证 Sandbox v2 的 Rootless Container Provider。

**不做的事：**
- 不执行用户代码/command/script
- 不使用用户 image
- 不自动 pull 镜像
- 不联网
- 不安装包
- 不挂载宿主机目录
- 不挂载 Docker socket（/var/run/docker.sock）
- 不使用 privileged
- 不使用 root 用户
- 不使用 shell=True

**只做：**
- 运行内置 trusted fixture（hello-container-fixture 等）
- 使用 Docker/Podman rootless 安全参数
- 保存 stdout/stderr 为只读 artifact

## 为什么只运行 trusted fixture

trusted fixture 在代码中硬编码，不经过任何用户输入。
这确保容器执行路径完全可控：
- command 固定
- image 固定
- 安全参数固定
- 所有容器操作可审计

## 在 Windows 上

**Windows 原生环境不能真正运行 Linux 容器。**

所有 preflight 检查会返回 `runnable=false`，API 返回 `unavailable`。
需要在 WSL2 或 Linux VM 中运行。

## 环境准备

### 1. 进入 WSL2 或 Linux

```bash
cd /mnt/d/dma/day2  # WSL2 路径
# 或
cd /path/to/dma/day2  # Linux 路径
```

### 2. 安装 Docker 或 Podman

```bash
# Docker (rootless 模式)
dockerd-rootless-setuptool.sh install

# 或 Podman
sudo apt install podman  # Debian/Ubuntu
```

### 3. 预拉取镜像（手动）

```bash
docker pull python:3.11-alpine
# 或
podman pull python:3.11-alpine
```

**不要启用自动 pull。** 如果镜像不存在，Provider 返回 `image_not_found`。

### 4. 设置环境变量

```bash
export SANDBOX_V2_CONTAINER_EXECUTION_ENABLED=true
export SANDBOX_V2_RUN_CONTAINER_INTEGRATION=true
```

### 5. 运行预检

```bash
python scripts/run_sandbox_v2_container_fixture_check.py
```

### 6. 运行集成测试

```bash
python -m pytest tests/test_open_platform/integration/test_sandbox_v2_real_container_fixture.py -q -v
```

## 安全参数清单

每次容器执行强制包含：

| 参数 | 含义 |
|------|------|
| `--rm` | 执行后删除容器 |
| `--network=none` | 无网络 |
| `--read-only` | 只读 rootfs |
| `--cap-drop=ALL` | 丢弃所有 Linux capabilities |
| `--security-opt=no-new-privileges` | 禁止提权 |
| `--pids-limit=64` | 进程数限制 |
| `--memory=256m` | 内存限制 |
| `--cpus=0.5` | CPU 限制 |
| `--user=65532:65532` | 非 root 用户 |
| `--tmpfs=/tmp:rw,noexec,nosuid,size=16m` | tmpfs 带安全挂载选项 |

这些参数不由用户控制，不在 shell 中构建（shell=False）。

## 当前不代表完整生产级沙箱

- 没有 MicroVM（Firecracker）
- 没有 gVisor/Kata Containers
- 没有真实多租户隔离
- 没有生产级镜像签名
- 没有运行时强制策略（仅控制面 policy）
- 没有 seccomp profile 自定义
- 没有 AppArmor/SELinux 配置

这些是未来 Step 的工作。
