# Sandbox v2 — Production Hardening Guide

**版本**: Step 10  
**最后更新**: 2026-06-13  
**目标受众**: 运维 / SRE / 安全工程师

---

## 一、安全默认值总览

Sandbox v2 遵循 **fail-closed by default** 原则。所有危险能力默认关闭，必须显式审计和批准后才能开启。

| 配置项 | 默认值 | 生产要求 | 说明 |
|--------|--------|----------|------|
| `SANDBOX_V2_FAIL_CLOSED` | `true` | **必须 `true`** | 未知输入/异常 → deny |
| `SANDBOX_V2_NETWORK_ENABLED` | `false` | **必须 `false`** | 禁止所有外网访问 |
| `SANDBOX_V2_PACKAGE_DOWNLOAD_ENABLED` | `false` | **必须 `false`** | 禁止包下载 |
| `SANDBOX_V2_PACKAGE_INSTALLATION_ENABLED` | `false` | **必须 `false`** | 禁止包安装 |
| `SANDBOX_V2_PUBLIC_REGISTRY_ENABLED` | `false` | **必须 `false`** | 禁止公共 registry |
| `SANDBOX_V2_CONTAINER_EXECUTION_ENABLED` | `false` | **默认 `false`** | 需 Linux + 全面审计 |
| `SANDBOX_V2_USER_COMMAND_EXECUTION` | `false` | **必须 `false`** | 禁止用户自定义命令 |
| `SANDBOX_V2_USER_IMAGE_EXECUTION` | `false` | **必须 `false`** | 禁止用户镜像 |
| `SANDBOX_V2_ARBITRARY_PID_KILL` | `false` | **必须 `false`** | 禁止 kill 系统进程 |
| `SANDBOX_V2_AUTO_PULL_IMAGES` | `false` | **必须 `false`** | 禁止自动 pull 镜像 |
| `SANDBOX_V2_READ_ONLY_ARTIFACTS` | `true` | **必须 `true`** | Artifact 只读 |

---

## 二、必须永久关闭的危险能力

以下能力在生产环境中**必须永久关闭**，无例外：

1. **用户命令执行** (`SANDBOX_V2_USER_COMMAND_EXECUTION=false`)
   - 允许用户在 sandbox 内执行任意命令 → 等同于远程代码执行
   
2. **用户镜像执行** (`SANDBOX_V2_USER_IMAGE_EXECUTION=false`)
   - 允许用户指定任意容器镜像 → 供应链攻击 + 逃逸风险
   
3. **任意 PID Kill** (`SANDBOX_V2_ARBITRARY_PID_KILL=false`)
   - 允许 kill 系统进程 → 拒绝服务 + 权限提升
   
4. **自动 Pull 镜像** (`SANDBOX_V2_AUTO_PULL_IMAGES=false`)
   - 自动 pull 未审计镜像 → 恶意镜像注入风险

---

## 三、启用真实容器执行的前置条件

如果业务需要启用 `SANDBOX_V2_CONTAINER_EXECUTION_ENABLED=true`，以下前置条件必须全部满足：

### 3.1 环境要求
- [ ] 仅 Linux 宿主（Windows/Mac 不可用于生产容器执行）
- [ ] Rootless Docker 或 Rootless Podman（不可使用 root Docker daemon）
- [ ] seccomp profile 已配置（不可使用 unconfined）
- [ ] AppArmor 或 SELinux 已启用并配置
- [ ] User namespace remap 已启用
- [ ] cgroup v2 已配置资源限制

### 3.2 安全审计
- [ ] 所有 Red-Team tests 在目标环境通过（132 tests）
- [ ] 真实容器逃逸测试通过
- [ ] 网络隔离验证通过（容器默认无网络）
- [ ] 文件系统只读验证通过
- [ ] 资源限制 (memory/cpu/pids) 生效验证

### 3.3 镜像管理
- [ ] 所有允许的镜像已手动 pull 到本地
- [ ] 每个镜像已通过漏洞扫描
- [ ] 每个镜像已审计 Dockerfile/SBOM
- [ ] `SANDBOX_V2_ALLOWED_IMAGES` 白名单已明确配置

### 3.4 容器安全参数（强制）
每个容器必须：
- `--network=none`（无网络）
- `--read-only`（只读 rootfs）
- `--cap-drop=ALL`（移除所有 capabilities）
- `--no-new-privileges`（禁止提权）
- `--security-opt=no-new-privileges`
- Non-root user（不可使用 UID 0）
- `--memory` / `--cpus` / `--pids-limit` 资源硬限制

---

## 四、Artifact Root 权限建议

```
# 生产环境推荐
chmod 750 .sandbox_v2_artifacts
chown app:app .sandbox_v2_artifacts

# 禁止 other 读写
find .sandbox_v2_artifacts -type f -exec chmod 640 {} \;
find .sandbox_v2_artifacts -type d -exec chmod 750 {} \;
```

- Artifact root 应位于应用专用数据卷
- 不应与系统关键目录共享文件系统
- 应启用文件系统配额防止磁盘耗尽

---

## 五、Package Quarantine 权限建议

```
# 生产环境推荐
chmod 700 .sandbox_v2_package_quarantine
chown app:app .sandbox_v2_package_quarantine
```

- Quarantine 目录应仅应用进程可访问
- 不应被 Web 服务器直接 serve
- 定期清理过期 quarantine 记录
- 高风险包应保留证据（不要删除）

---

## 六、Network Egress 策略

### 6.1 默认策略：Preflight-Only + Deny All

```
SANDBOX_V2_NETWORK_ENABLED=false
SANDBOX_V2_NETWORK_PREFLIGHT_ONLY=true
SANDBOX_V2_ALLOWED_DOMAINS=
SANDBOX_V2_DENIED_DOMAINS=localhost,127.0.0.1,169.254.169.254
```

### 6.2 阻止清单

- `localhost` / `127.0.0.1` / `[::1]` — 防止 SSRF 到本地
- `0.0.0.0` — 防止 bind-all 绕过
- `169.254.169.254` — 防止 AWS metadata 访问
- `metadata.google.internal` — 防止 GCP metadata 访问
- `10.0.0.0/8` — 防止私有网络访问
- `172.16.0.0/12` — 防止私有网络访问
- `192.168.0.0/16` — 防止私有网络访问
- `fc00::/7` — 防止 IPv6 ULA 访问
- `fe80::/10` — 防止 IPv6 link-local 访问

### 6.3 危险 Scheme 阻止

- `file://` — 防止本地文件读取
- `ftp://` — 防止 FTP 协议滥用
- `gopher://` — 防止 Gopher 协议 SSRF
- `dict://` — 防止 Dict 协议 SSRF

---

## 七、Kill Switch 策略

### 7.1 允许的操作
- Cancel sandbox-managed job
- Cancel queue item
- Cancel execution plan
- Cancel container plan
- Mark active execution handle as cancel_requested

### 7.2 禁止的操作
- Kill 任意系统 PID
- Kill 非 sandbox 管理的对象
- Kill 已完成/已失败的任务
- 跨 organization 的 kill

### 7.3 审计要求
- 每次 kill 请求自动创建 `SandboxKillRecord`
- Kill record 不可删除
- Kill record 包含：时间戳、操作人、目标、动作、结果

---

## 八、Red-Team 测试要求

### 8.1 必须在目标部署环境运行

```bash
# 完整 red-team 套件（132 tests）
python -m pytest tests/test_open_platform/red_team -q

# 必须 100% 通过
# 任何失败都必须修复后才能部署生产
```

### 8.2 Red-Team 覆盖领域

| 领域 | 测试数 | 说明 |
|------|--------|------|
| Artifact Escape | 24 | 路径穿越、危险扩展名、MIME 伪装 |
| Network SSRF | 22 | SSRF、内网、metadata、危险 scheme |
| Package Supply Chain | 13 | 供应链投毒、缺签名/hash/SBOM |
| Kill Switch Abuse | 9 | 任意 PID kill、跨 org kill |
| Container Escape | 20 | privileged、docker.sock、root user |
| Policy Fail-Closed | 16 | 6 引擎异常输入、高风险拦截 |
| API Abuse | 12 | 路径穿越、超长输入、信息泄露 |
| Worker/Queue Abuse | 9 | 重复 lease、expired requeue |

---

## 九、Linux/WSL2 容器验证要求

如果目标部署环境是 Linux：

1. Docker/Podman rootless 安装验证
2. `hello-container-fixture` 真实容器执行验证
3. stdout/stderr artifact 正确性验证
4. `container_kill` 真实 kill 容器验证
5. 资源限制（memory/cpu/pids）生效验证
6. 容器内不应能访问宿主网络
7. 容器内不应能访问宿主文件系统

---

## 十、不允许的能力清单（生产红线）

| 能力 | 状态 | 红线 |
|------|------|------|
| 用户命令执行 | ❌ 不允许 | 远程代码执行 |
| 用户镜像执行 | ❌ 不允许 | 供应链攻击 + 逃逸 |
| 任意 PID kill | ❌ 不允许 | 拒绝服务 + 提权 |
| 自动 pull 镜像 | ❌ 不允许 | 恶意镜像注入 |
| Package 安装 | ❌ 不允许 | 依赖混淆 + 恶意代码 |
| Public registry 下载 | ❌ 不允许 | 供应链攻击 |
| External 包 URL 下载 | ❌ 不允许 | 远程代码注入 |
| External network access | ❌ 不允许 | 数据外泄 |
| MicroVM execution | ⚠️ 未实现 | 待 Step 11 |

---

## 十一、生产部署前检查清单

详见：[sandbox-v2-deployment-checklist.md](./sandbox-v2-deployment-checklist.md)

简要版：

- [ ] 环境变量已按本指南审查
- [ ] 所有 Red-Team tests 在目标环境通过
- [ ] Readiness script 通过（无 blockers）
- [ ] Artifact/Package 目录权限正确
- [ ] Kill Switch 可审计
- [ ] 生产日志与备份策略已配置
- [ ] 容器执行（如启用）已满足所有前置条件
- [ ] Network 策略已验证
