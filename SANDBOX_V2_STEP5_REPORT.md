# SANDBOX V2 STEP 5 REPORT — Network Egress 网络访问控制

**实施日期**: 2026-06-13
**项目**: 黔智脑 Cognitive OS (`D:\dma\day2`)
**步骤**: Sandbox v2 Step 5 — Network Egress Policy & Preflight Control Plane

---

## 一、本次新增文件

| # | 文件 | 用途 |
|---|------|------|
| 1 | `src/open_platform/sandbox_v2/network_policy.py` | Network Egress Policy Engine（14 条安全规则：scheme 拦截、loopback 拦截、私有网段拦截、metadata 拦截、域名 allowlist/denylist、端口白名单、IP 策略检查、wildcard domain 匹配） |
| 2 | `src/open_platform/sandbox_v2/network.py` | SandboxNetworkEgressService（preflight 预检、audit 记录、不真实发起网络请求） |
| 3 | `tests/test_open_platform/test_sandbox_v2_network_policy.py` | 网络策略测试（35 项） |
| 4 | `tests/test_open_platform/test_sandbox_v2_network_service.py` | 网络服务测试（5 项） |
| 5 | `tests/test_open_platform/test_sandbox_v2_network_api.py` | 网络 API 测试（13 项） |

**共新增 5 个文件。**

---

## 二、本次修改文件

| # | 文件 | 变更内容 |
|---|------|----------|
| 1 | `src/open_platform/sandbox_v2/models.py` | +2 枚举 + 4 数据类 + 3 常量组（~150 行）：EgressRequest, EgressPolicyDecision, EgressAuditRecord, NetworkPolicyConfig + BLOCKED_NETWORK_SCHEMES/ALLOWED_NETWORK_SCHEMES/PRIVATE_NETWORKS_V4 |
| 2 | `src/open_platform/sandbox_v2/store.py` | +7 protocol 方法（network egress request/audit CRUD） |
| 3 | `src/adapters/sqlite_sandbox_v2_store.py` | +2 个 SQL 表 + 7 个 CRUD 方法 + 2 个 row mapper |
| 4 | `src/open_platform/sandbox_v2/service.py` | 构造函数 +network_service 参数；+6 个 network 方法 |
| 5 | `src/open_platform/sandbox_v2/worker.py` | simulation 过程中 network preflight 调用 |
| 6 | `src/api/sandbox_v2.py` | +2 个 Pydantic schema + 6 个端点 + readiness +12 字段 |
| 7 | `main.py` | SandboxNetworkEgressService 初始化注入 |
| 8 | `frontend/types/runtime-admin.ts` | +7 个 TypeScript 接口 |
| 9 | `frontend/services/runtime-admin.ts` | +6 个 API client 方法 |

**共修改 9 个文件。**

---

## 三、新增 API 列表

| 方法 | 路径 | 功能 | 新增于 |
|------|------|------|--------|
| `POST` | `/api/runtime/sandbox-v2/network/egress-requests` | 创建网络出站请求并评估策略 | Step 5 |
| `GET` | `/api/runtime/sandbox-v2/network/egress-requests` | 列出网络出站请求 | Step 5 |
| `GET` | `/api/runtime/sandbox-v2/network/egress-requests/{id}` | 查看单个出站请求 | Step 5 |
| `GET` | `/api/runtime/sandbox-v2/network/audit-records` | 查看网络审计记录 | Step 5 |
| `POST` | `/api/runtime/sandbox-v2/network/preflight` | 即时策略预检（不持久化、不实际请求） | Step 5 |
| `GET` | `/api/runtime/sandbox-v2/network/readiness` | 网络出站能力状态 | Step 5 |

Step 1/2/3/4 的 31 个原始端点不变，全部向后兼容。

---

## 四、Network Egress 当前完成能力

### 4.1 策略引擎 ✅

| 能力 | 状态 | 说明 |
|------|------|------|
| 默认 deny | ✅ | 空白 URL / allow_network=false 直接拒绝 |
| fail closed | ✅ | 任何异常 → deny |
| http/https only | ✅ | file/ftp/gopher/dict/ssh/smb/ldap/telnet 等全部拦截 |
| localhost 拦截 | ✅ | localhost/127.0.0.1/0.0.0.0/::1 全部拦截 |
| metadata service 拦截 | ✅ | 169.254.169.254 / metadata.google.internal 拦截 |
| 私有网段拦截 | ✅ | 10.0/8, 172.16/12, 192.168/16, fc00::/7, fe80::/10 |
| 端口白名单 | ✅ | 默认仅 80/443 |
| 域名 allowlist | ✅ | 显式配置才允许 |
| 域名 denylist | ✅ | denylist 优先级高于 allowlist |
| wildcard 安全匹配 | ✅ | *.example.com 匹配 a.example.com，不匹配 badexample.com |
| IP 策略检查 | ✅ | resolved_ips 中的私有 IP/loopback/metadata IP 拦截 |
| 无真实 DNS | ✅ | require_dns_preflight 标记 |

### 4.2 预检服务 ✅

| 能力 | 状态 | 说明 |
|------|------|------|
| 不发起真实网络请求 | ✅ | 所有端点 preflight_only |
| 不做真实 DNS 查询 | ✅ | 仅检查传入的 resolved_ips |
| egress request 持久化 | ✅ | SQLite 记录 |
| audit record 持久化 | ✅ | 每次决策记录审计 |
| preflight 即时策略 | ✅ | 不做持久化 |
| Worker 集成 | ✅ | simulation 中触发 preflight |

---

## 五、当前限制（诚实声明）

| 能力 | 状态 | 原因 |
|------|------|------|
| 真实外网访问 | ❌ | 默认 deny，preflight only |
| 真实 DNS 解析 | ❌ | 仅标记 require_dns_preflight |
| egress proxy | ❌ | 未实现代理 |
| iptables/nftables 强制执行 | ❌ | 无运行时网络命名空间 |
| runtime network namespace | ❌ | 无容器隔离 |
| 真实请求审计（连接级） | ❌ | 仅策略层 audit |

---

## 六、为什么这一步仍然不等于生产级网络隔离

1. **preflight only** — 不做真实网络请求，无法验证策略在实际连接中的行为。
2. **无 DNS 解析** — 不做真实 DNS 检查，可能被 DNS rebinding 绕过。
3. **无 iptables 强制** — 策略仅代码层，无 OS 级别防火墙规则。
4. **无 egress proxy** — 无法做真实请求审计和拦截。
5. **无容器网络命名空间** — 无隔离环境。

---

## 七、测试结果

### 新增测试
```
test_sandbox_v2_network_policy.py   35 passed
test_sandbox_v2_network_service.py   5 passed
test_sandbox_v2_network_api.py      13 passed
```

### 全部 sandbox v2 测试 (Step 1-5)
```
271 passed in 16.24s
```

### 全部 test_open_platform
```
3837 passed in 87.73s
```

零回归。

---

## 八、测试覆盖清单

1. ✅ 默认 deny
2. ✅ allow_network=false 时拒绝
3. ✅ http/https 以外 scheme 拒绝
4. ✅ file:// 拒绝
5. ✅ ftp:// 拒绝
6. ✅ localhost 拒绝
7. ✅ 127.0.0.1 拒绝
8. ✅ [::1] 拒绝
9. ✅ 169.254.169.254 metadata 拒绝
10. ✅ 10.0.0.1 私有网段拒绝
11. ✅ 172.16.0.1 私有网段拒绝
12. ✅ 192.168.1.1 私有网段拒绝
13. ✅ fc00::/7 拒绝
14. ✅ fe80::/10 拒绝
15. ✅ 8080 端口默认拒绝
16. ✅ allowed_domains 命中 allowed_preflight
17. ✅ denied_domains 优先于 allowed_domains
18. ✅ wildcard domain 安全匹配
19. ✅ badexample.com 不命中 *.example.com
20. ✅ 传入 private resolved_ips 时拒绝
21. ✅ 传入 public resolved_ips 时允许
22. ✅ egress request 写入 SQLite
23. ✅ audit record 写入 SQLite
24. ✅ preflight 不发起真实网络请求
25. ✅ network readiness 字段正确
26. ✅ 旧 Step 1/2/3/4 测试仍通过

---

## 九、下一步建议

**建议进入 Step 6：Runtime Network Namespace + 最小隔离执行 PoC**

具体任务：

1. Linux 环境准备（Podman/Docker rootless）
2. 最小 rootless container sandbox worker
3. seccomp profile（默认 deny）
4. read-only rootfs + no new privileges
5. 运行时网络/文件系统隔离模板
6. 仍不执行不可信代码，先跑受控的 minimal fixture
7. `SandboxWorker` 从 `DisabledStub` 升级为 `RootlessContainerPoC`

---

## 十、命令速查

```bash
# 运行网络测试
python -m pytest tests/test_open_platform/test_sandbox_v2_network_*.py -q -v

# 运行全部 sandbox v2 测试
python -m pytest tests/test_open_platform/test_sandbox_v2_*.py -q 2>&1 || ...

# 运行完整 test_open_platform
python -m pytest tests/test_open_platform -q
```
