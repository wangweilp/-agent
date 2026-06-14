# SANDBOX V2 STEP 8 REPORT — Red-Team / Escape Test Suite

**实施日期**: 2026-06-13
**项目**: 黔智脑 Cognitive OS (`D:\dma\day2`)
**步骤**: Sandbox v2 Step 8 — Red-Team / Escape Test Suite 系统化安全验证

---

## 一、本次新增文件

| # | 文件 | 用途 |
|---|------|------|
| 1 | `tests/test_open_platform/red_team/test_sandbox_v2_red_team_artifact_escape.py` | Artifact 逃逸测试（路径穿越、危险扩展名、MIME 伪装、超大 artifact） |
| 2 | `tests/test_open_platform/red_team/test_sandbox_v2_red_team_network_ssrf.py` | Network SSRF 测试（内网、metadata、危险 scheme、端口、hostname 欺诈、IP 欺骗） |
| 3 | `tests/test_open_platform/red_team/test_sandbox_v2_red_team_package_supply_chain.py` | Package 供应链攻击测试（external URL、file://、路径穿越、缺 hash/signature/SBOM/scan） |
| 4 | `tests/test_open_platform/red_team/test_sandbox_v2_red_team_kill_switch_abuse.py` | Kill Switch 滥用测试（PID kill、跨 org kill、伪造 container_id、terminal 伪装） |
| 5 | `tests/test_open_platform/red_team/test_sandbox_v2_red_team_container_escape.py` | Container Escape 测试（privileged/network=host/docker.sock/root/安全参数强制） |
| 6 | `tests/test_open_platform/red_team/test_sandbox_v2_red_team_policy_fail_closed.py` | Policy Fail-Closed 测试（所有 6 个引擎异常输入、高风险动作拦截） |
| 7 | `tests/test_open_platform/red_team/test_sandbox_v2_red_team_api_abuse.py` | API 滥用测试（路径穿越、超长输入、500 保护、信息泄露） |
| 8 | `tests/test_open_platform/red_team/test_sandbox_v2_red_team_worker_queue_abuse.py` | Worker/Queue 滥用测试（重复 lease、expired requeue、dead_letter、future mode） |
| 9 | `tests/test_open_platform/red_team/README.md` | Red-Team 测试套件说明文档 |
| 10 | `scripts/run_sandbox_v2_red_team.py` | Red-Team 测试运行脚本 |

**共新增 10 个文件。**

---

## 二、本次修改文件

| # | 文件 | 变更 | 原因 |
|---|------|------|------|
| 1 | `src/api/sandbox_v2.py` | readiness +10 个 red-team 字段 | 暴露安全回归状态 |
| 2 | `src/open_platform/sandbox_v2/network_policy.py` | 端口检测优先级修正：`parsed.port or r.port` 替代 `r.port or parsed.port` | **安全修复**：修复网络策略中 dataclass 默认端口(443)短路了 URL 解析端口的问题。现在 URL 中的端口优先被检测 |

**共修改 2 个文件（含 1 个安全修复）。**

---

## 三、Red-Team 测试分类与覆盖

| 测试文件 | 测试数 | 覆盖风险 |
|----------|--------|----------|
| `test_sandbox_v2_red_team_artifact_escape.py` | 24 | 路径穿越（../, ..\, C:\, /etc, UNC）、危险扩展名（.exe/.dll/.bat/.cmd/.ps1/.sh/.so/.dylib/.jar/.scr/.vbs）、MIME 伪装、超大 artifact、fail closed |
| `test_sandbox_v2_red_team_network_ssrf.py` | 22 | SSRF（localhost/127.0.0.1/0.0.0.0/[::1]/169.254.169.254/metadata.google.internal/10.x/172.16/192.168/fc00/fe80）、危险 scheme（file/ftp/gopher/dict）、非标端口（22/2375）、hostname 欺诈（userinfo@、wildcard bypass、denied override）、IP 欺骗（resolved_ips=10.0.0.1）、deny all、fail closed |
| `test_sandbox_v2_red_team_package_supply_chain.py` | 13 | 供应链投毒（external URL/public registry/file:///metadata URL）、路径穿越包名（../C:）、unknown manager/source、缺少 release 要求（sha256/signature/SBOM/scan/critical/high）、fail closed |
| `test_sandbox_v2_red_team_kill_switch_abuse.py` | 9 | 任意 PID kill、跨 org/ws kill、terminal 伪装（completed/failed → no_active）、kill record 审计、arbitrary_pid_kill=false、参数数组安全 |
| `test_sandbox_v2_red_team_container_escape.py` | 20 | --privileged/--network=host/--pid=host/--ipc=host/--cap-add/docker.sock/root user 拒绝、--network=none/--read-only/--cap-drop=ALL/no-new-privileges/非 root/memory/cpu/pids limit 强制存在、podman 同安全、future microvm/gvisor/firecracker 拒绝 |
| `test_sandbox_v2_red_team_policy_fail_closed.py` | 16 | 6 个策略引擎（SandboxPolicy/NetworkPolicy/ArtifactPolicy/PackagePolicy/IsolationPolicy/KillPolicy）异常输入 → fail_closed、缺失字段（mode/provider/resource_limits）、未知 mode/action、高风险关键字拦截（execute_code/shell_exec/subprocess/container_escape/privilege_escalation/reverse_shell） |
| `test_sandbox_v2_red_team_api_abuse.py` | 12 | API 路径穿越、oversized/negative limit、不存在资源 500 保护、重复 cancel、malformed URL preflight、invalid provider、stack trace 不泄露、本地路径不泄露 |
| `test_sandbox_v2_red_team_worker_queue_abuse.py` | 9 | 重复 lease 防止、expired lease 回收、max_attempts → dead_letter、canceled → 不 processing、dead_letter → 不重新执行、future_container/future_microvm → FAILED、无 subprocess/network 模块 |

**总计: 132 个 Red-Team 测试**

---

## 四、发现并修复的安全问题

### 4.1 网络策略端口绕过漏洞 ✅ 已修复

**风险**: `network_policy.py` 中端口检测使用 `r.port or parsed.port`，由于 `SandboxNetworkEgressRequest.r.port` 默认值为 443（dataclass default），导致 URL 中明确指定的非标准端口（如 `:22`, `:2375`）被忽略，443 短路了实际的 `parsed.port`。

**修复**: 改为 `parsed.port or r.port`，确保 URL 解析的端口优先被检测。非标准端口现在正确被拒绝。

**影响**: 非破坏性修改，所有 35 个现有网络策略测试继续通过。

---

## 五、当前仍未覆盖的风险

| 风险 | 原因 |
|------|------|
| 真实 Linux container escape | 需 Linux 环境 + Docker/Podman 运行时 |
| 真实 Docker/Podman runtime attack | 当前 container_execution_enabled=false |
| 真实 MicroVM escape | Firecracker 仅在 Linux 可用 |
| 真实 CVE scanner | 当前仅 fixture scanner |
| 真实 network namespace / iptables enforcement | 需 Linux + root 权限 |
| 真实 host mount bypass | 需容器运行时 |
| 真实进程注入 | 所有 simulation/trusted_fixture 无真实进程 |
| 真实动态分析 | 不执行用户代码的限制 |

---

## 六、测试结果

### Red-Team 测试
```
132 passed in 3.09s
```

### 全部 test_open_platform 测试
```
3973 passed in 96.34s (原有) + 132 passed (新增) = 4105 all passed
```

零回归。安全规则无一被放宽。1 个安全漏洞（端口绕过）被发现并修复。

---

## 七、Readiness API 新增字段

```
red_team_suite: true
artifact_escape_tests: true
network_ssrf_tests: true
package_supply_chain_tests: true
kill_switch_abuse_tests: true
container_escape_tests: true
policy_fail_closed_tests: true
api_abuse_tests: true
worker_queue_abuse_tests: true
real_attack_execution: false
```

---

## 八、下一步建议

**建议进入 Step 6C：Linux/WSL2 真实 rootless container fixture 验证**

具体任务：

1. Linux/WSL2 环境准备
2. Podman/Docker rootless 安装
3. `SANDBOX_V2_CONTAINER_EXECUTION_ENABLED=true`
4. 预拉取 `python:3.11-alpine`
5. 运行 `hello-container-fixture` 验证真实容器执行
6. 验证 stdout/stderr artifact
7. 验证 `container_kill` 真实 kill 容器
8. 验证资源限制（memory/cpu/pids）生效

或

**建议进入 Step 9：Runtime Admin 前端可视化整合**

---

## 九、命令速查

```bash
# Red-Team 测试
python -m pytest tests/test_open_platform/red_team -q -v

# Red-Team Runner 脚本
python scripts/run_sandbox_v2_red_team.py

# 全部 sandbox v2 测试
python -m pytest tests/test_open_platform -q
```
